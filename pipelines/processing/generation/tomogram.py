"""Generates the full-stack tomogram by dispatching PyRat beamforming jobs in parallel.

The configured crop is split into azimuth subsections, each beamformed in its own PyRat
worker process, and the resulting HDF5 partials are concatenated back along azimuth into
a single tomogram and DEM. The merge audits the content of every strip, so the stage
result records how many profiles are empty or non-finite and where the valid ones lie.
"""

from __future__ import annotations

import gc
import shutil
import sys
import tempfile
from pathlib import Path
from typing  import Tuple

import h5py
import numpy as np

from configuration.sar.processing_config  import (
    ParallelConfig,
    ProcessingConfig,
    TomogramConfig,
)
from pipelines.processing.generation.base import GeneratorBase
from tools.sar.pyrat_env                  import PyRatEnvironment
from tools.sar.tomogram_worker            import PyRatJob, run_pyrat_job
from tools.data.io                        import FileIO
from tools.orchestration.pool             import ProcessPoolRunner
from tools.monitoring.logger              import Logger
from tools.data.regions                   import CropRegion


class TomogramContentAudit:
    """Counts the empty and non-finite content of a merged tomogram and DEM, one azimuth strip at a time.

    A profile is the height column of the tomogram at one (azimuth, range)
    pixel. The patched PyRAT writes all-zero profiles wherever the stack is
    zero-filled, which is what a whole-scene crop holds at the scene margins,
    so the count of such profiles and the extent of the valid ones say where a
    crop should be tightened. Every azimuth line and range sample is reported
    in scene coordinates.

    Attributes:
        MAX_RUNS_NAMED       : Largest number of azimuth runs spelled out in a warning.
        crop                 : Crop the merged arrays cover.
        voxels               : Tomogram voxels seen so far.
        nonfinite_voxels     : NaN or infinite tomogram voxels seen so far.
        profiles             : Profiles seen so far.
        zero_profiles        : All-zero profiles seen so far.
        dem_nonfinite_pixels : NaN or infinite DEM pixels seen so far.
        dem_min              : Smallest finite DEM height in metres, or None before any finite pixel.
        dem_max              : Largest finite DEM height in metres, or None before any finite pixel.
        zero_profile_lines   : Per azimuth line of the crop, whether it holds an all-zero profile.
        nonfinite_lines      : Per azimuth line of the crop, whether it holds a non-finite voxel.
        dem_nonfinite_lines  : Per azimuth line of the crop, whether it holds a non-finite DEM pixel.
        valid_lines          : Per azimuth line of the crop, whether it holds a finite, non-zero profile.
        valid_samples        : Per range sample of the crop, whether it holds a finite, non-zero profile.
    """

    MAX_RUNS_NAMED = 8

    def __init__(self, crop: CropRegion) -> None:
        """Starts an empty audit over a crop.

        Args:
            crop : Crop the merged tomogram and DEM cover.
        """
        self.crop                 = crop
        self.voxels               = 0
        self.nonfinite_voxels     = 0
        self.profiles             = 0
        self.zero_profiles        = 0
        self.dem_nonfinite_pixels = 0
        self.dem_min              = None
        self.dem_max              = None

        self.zero_profile_lines  = np.zeros(crop.azimuth_size, dtype=bool)
        self.nonfinite_lines     = np.zeros(crop.azimuth_size, dtype=bool)
        self.dem_nonfinite_lines = np.zeros(crop.azimuth_size, dtype=bool)
        self.valid_lines         = np.zeros(crop.azimuth_size, dtype=bool)
        self.valid_samples       = np.zeros(crop.range_size,   dtype=bool)

    def add_strip(self, azimuth_offset: int, dem_chunk: np.ndarray, tomogram_chunk: np.ndarray) -> None:
        """Accounts one azimuth strip of the merge, one height slice at a time to keep the masks small.

        Args:
            azimuth_offset : First azimuth line of the strip, counted from the start of the crop.
            dem_chunk      : DEM strip of shape (azimuth, range), in metres.
            tomogram_chunk : Tomogram strip of shape (height, azimuth, range).
        """
        active    = np.zeros(tomogram_chunk.shape[1:], dtype=bool)
        nonfinite = np.zeros(tomogram_chunk.shape[1:], dtype=bool)

        for height_slice in tomogram_chunk:
            nonfinite_here         = ~np.isfinite(height_slice)
            self.nonfinite_voxels += int(np.count_nonzero(nonfinite_here))
            active                |= height_slice != 0
            nonfinite             |= nonfinite_here

        lines = slice(azimuth_offset, azimuth_offset + tomogram_chunk.shape[1])
        valid = active & ~nonfinite

        self.voxels        += int(tomogram_chunk.size)
        self.profiles      += int(active.size)
        self.zero_profiles += int(np.count_nonzero(~active))

        self.zero_profile_lines[lines] = (~active).any(axis=1)
        self.nonfinite_lines[lines]    = nonfinite.any(axis=1)
        self.valid_lines[lines]        = valid.any(axis=1)
        self.valid_samples            |= valid.any(axis=0)

        dem_finite = np.isfinite(dem_chunk)

        self.dem_nonfinite_pixels      += int(np.count_nonzero(~dem_finite))
        self.dem_nonfinite_lines[lines] = (~dem_finite).any(axis=1)

        if dem_finite.any():
            low  = float(dem_chunk[dem_finite].min())
            high = float(dem_chunk[dem_finite].max())

            self.dem_min = low  if self.dem_min is None else min(self.dem_min, low)
            self.dem_max = high if self.dem_max is None else max(self.dem_max, high)

    @staticmethod
    def _runs(mask: np.ndarray, origin: int) -> list[list[int]]:
        """Returns the half-open [start, end) runs of True entries of a mask, shifted to scene coordinates."""
        padded = np.concatenate(([False], mask, [False]))
        edges  = np.flatnonzero(padded[1:] != padded[:-1])

        return [[int(origin + start), int(origin + end)] for start, end in zip(edges[::2], edges[1::2])]

    @staticmethod
    def _span(mask: np.ndarray, origin: int) -> list[int] | None:
        """Returns the half-open [first, last + 1) bounds of the True entries of a mask in scene coordinates, or None when there are none."""
        hits = np.flatnonzero(mask)

        if hits.size == 0:
            return None

        return [int(origin + hits[0]), int(origin + hits[-1] + 1)]

    def summary(self) -> dict:
        """Returns the counts, the valid extent and the affected azimuth runs as a JSON-ready mapping."""
        return {
            "crop"                       : list(self.crop.as_tuple()),
            "voxels"                     : self.voxels,
            "nonfinite_voxels"           : self.nonfinite_voxels,
            "profiles"                   : self.profiles,
            "zero_profiles"              : self.zero_profiles,
            "zero_profile_fraction"      : self.zero_profiles / self.profiles if self.profiles else 0.0,
            "dem_nonfinite_pixels"       : self.dem_nonfinite_pixels,
            "dem_min_m"                  : self.dem_min,
            "dem_max_m"                  : self.dem_max,
            "valid_azimuth"              : self._span(self.valid_lines,   self.crop.azimuth_start),
            "valid_range"                : self._span(self.valid_samples, self.crop.range_start),
            "zero_profile_azimuth_runs"  : self._runs(self.zero_profile_lines,  self.crop.azimuth_start),
            "nonfinite_azimuth_runs"     : self._runs(self.nonfinite_lines,     self.crop.azimuth_start),
            "dem_nonfinite_azimuth_runs" : self._runs(self.dem_nonfinite_lines, self.crop.azimuth_start),
        }

    @staticmethod
    def format_span(span: list | None) -> str:
        """Returns a half-open span as '[start, end)', or 'none' when no entry qualifies."""
        return "none" if span is None else f"[{span[0]}, {span[1]})"

    @classmethod
    def format_runs(cls, runs: list) -> str:
        """Returns the first MAX_RUNS_NAMED runs as half-open ranges, saying how many more there are."""
        shown = ", ".join(f"[{start}, {end})" for start, end in runs[:cls.MAX_RUNS_NAMED])

        if len(runs) > cls.MAX_RUNS_NAMED:
            shown += f" and {len(runs) - cls.MAX_RUNS_NAMED} more"

        return shown

    @staticmethod
    def format_dem_range(content: dict) -> str:
        """Returns the finite DEM height range of a content summary in metres, or 'none finite'."""
        if content["dem_min_m"] is None:
            return "none finite"

        return f"[{content['dem_min_m']:.1f}, {content['dem_max_m']:.1f}]"

    @classmethod
    def describe(cls, content: dict) -> dict[str, str]:
        """Returns the text metadata entries of a content summary, as written into meta_tomogram_full.txt.

        Args:
            content : Summary as returned by ``summary``, carrying the merged shapes.

        Returns:
            Mapping from metadata key to its string value.
        """
        return {
            "tomogram_shape"       : f"[{', '.join(str(v) for v in content['tomogram_shape'])}]",
            "nonfinite_voxels"     : str(content["nonfinite_voxels"]),
            "zero_profiles"        : f"{content['zero_profiles']} of {content['profiles']} ({content['zero_profile_fraction']:.3%})",
            "dem_nonfinite_pixels" : str(content["dem_nonfinite_pixels"]),
            "dem_range_m"          : cls.format_dem_range(content),
            "valid_azimuth"        : cls.format_span(content["valid_azimuth"]),
            "valid_range"          : cls.format_span(content["valid_range"]),
        }

    @classmethod
    def log_summary(cls, content: dict, logger: Logger) -> None:
        """Prints the content table and warns about every non-zero anomaly count, naming the azimuth lines it affects.

        Args:
            content : Summary as returned by ``summary``, read back from the stage result when called in the parent process.
            logger  : Logger the table and the warnings go to.
        """
        logger.kv_table({
            "Voxels"                : content["voxels"],
            "Non-finite voxels"     : content["nonfinite_voxels"],
            "Profiles"              : content["profiles"],
            "All-zero profiles"     : f"{content['zero_profiles']} ({content['zero_profile_fraction']:.3%})",
            "DEM non-finite pixels" : content["dem_nonfinite_pixels"],
            "DEM range [m]"         : cls.format_dem_range(content),
            "Valid azimuth"         : cls.format_span(content["valid_azimuth"]),
            "Valid range"           : cls.format_span(content["valid_range"]),
        }, title="Tomogram content")

        if content["nonfinite_voxels"] > 0:
            logger.warning(f"Tomogram holds {content['nonfinite_voxels']} non-finite voxels on azimuth lines {cls.format_runs(content['nonfinite_azimuth_runs'])}; parameter extraction and training read them as data")

        if content["zero_profiles"] > 0:
            logger.warning(f"Tomogram holds {content['zero_profiles']} all-zero profiles ({content['zero_profile_fraction']:.3%}) on azimuth lines {cls.format_runs(content['zero_profile_azimuth_runs'])}; valid profiles span azimuth {cls.format_span(content['valid_azimuth'])} x range {cls.format_span(content['valid_range'])} of the crop {tuple(content['crop'])}; zero-filled scene margins are the usual cause, so tighten the crop to the valid extent")

        if content["dem_nonfinite_pixels"] > 0:
            logger.warning(f"DEM holds {content['dem_nonfinite_pixels']} non-finite pixels on azimuth lines {cls.format_runs(content['dem_nonfinite_azimuth_runs'])}")


class TomogramProcessor:
    """Beamforms one crop into a tomogram through parallel PyRat subsection jobs.

    Attributes:
        config : Processing configuration naming the crop, parallelism and paths.
        logger : Logger for the stage report.
    """

    def __init__(self, config: ProcessingConfig, logger: Logger) -> None:
        """Configures the processor and reports the resolved parallel budget.

        Args:
            config : Processing configuration for this stack.
            logger : Logger for initialization and stage output.
        """
        self.config = config
        self.logger = logger

        self.logger.section("[TomogramProcessor Initialization]")
        self.logger.subsection(f"Max Azimuth Width : {self.config.tomogram_config.max_crop_azimuth_width}")
        self.logger.subsection(f"Parallel Effort   : {self.config.parallel.effort}")
        self.logger.subsection(f"Core Budget       : {self.config.parallel.core_budget()}")
        self.logger.subsection(f"Cores Available   : {self.config.parallel.available_cores()}")

    def _create_temp(self) -> Path:
        """Creates and returns a fresh scratch directory for the HDF5 partials."""
        parent = self.config.paths.temporary_directory
        FileIO.ensure_dir(parent)
        temporary_directory = Path(tempfile.mkdtemp(prefix="tomo_", dir=str(parent)))
        return temporary_directory

    def _divide_crop(self, tomogram_config: TomogramConfig) -> list[Tuple[int, int, int, int]]:
        """Splits the crop into azimuth subsections no wider than the configured limit.

        Args:
            tomogram_config : Tomogram configuration carrying the azimuth width limit.

        Returns:
            List of crops as (azimuth_start, azimuth_end, range_start, range_end) in pixels.
        """
        crop      = self.config.crop
        max_width = tomogram_config.max_crop_azimuth_width

        azimuth_start = crop.azimuth_start
        azimuth_end   = crop.azimuth_end
        total_width   = azimuth_end - azimuth_start

        if total_width <= max_width:
            self.logger.subsection(f"Crop width ({total_width}) fits within limit ({max_width}). Single section.")
            return [crop.as_tuple()]

        subsections = [region.as_tuple() for region in crop.subdivide_by_azimuth(max_width)]

        self.logger.subsection(f"Crop subdivided into {len(subsections)} sections.")
        self.logger.metrics_table(
            [{"Section": f"{index:04d}", "Azimuth start": start, "Azimuth end": end} for index, (start, end, _, _) in enumerate(subsections)],
            columns = ("Section", "Azimuth start", "Azimuth end"),
            title   = "Tomogram subsections",
        )

        return subsections

    def _dispatch_workers(
        self,
        subsections         : list[Tuple[int, int, int, int]],
        stack_identifier    : str,
        tomogram_config     : TomogramConfig,
        temporary_directory : Path,
    ) -> None:
        """Runs one PyRat beamforming job per subsection across a process pool.

        Args:
            subsections         : Subsection crops as (azimuth_start, azimuth_end, range_start, range_end).
            stack_identifier    : Identifier of the F-SAR stack being beamformed.
            tomogram_config     : Tomogram configuration passed through to every worker.
            temporary_directory : Scratch directory the workers write their HDF5 partials into.
        """
        PyRatEnvironment.ensure_conda_lib_on_ld_path()

        parallel_config = self.config.parallel
        tasks           = []

        resolved_workers, worker_threads = parallel_config.resolve_plan(len(subsections))

        parent_sys_path = list(sys.path)

        for subsection_index, subsection_crop in enumerate(subsections):
            tasks.append(PyRatJob(
                pyrat_root_path       = str(self.config.paths.pyrat_directory),
                crop_tuple            = subsection_crop,
                suffix                = f"{subsection_index:04d}",
                fusar_project_path    = tomogram_config.fusar_project_path,
                stack_identifier      = stack_identifier,
                base_directory        = tomogram_config.base_directory,
                polarisation          = tomogram_config.polarisation,
                track_selection       = tomogram_config.track_selection,
                height_range          = tomogram_config.height_range,
                filter_method         = tomogram_config.filter_method,
                filter_arguments      = tomogram_config.filter_arguments,
                beamforming_method    = tomogram_config.beamforming_method,
                beamforming_arguments = tomogram_config.beamforming_arguments,
                output_directory      = str(temporary_directory),
                apply_resampling      = tomogram_config.apply_resampling,
                apply_presumming      = tomogram_config.apply_presumming,
                pyrat_threads         = worker_threads,
                parent_sys_path       = parent_sys_path,
            ))

        self.logger.subsection(f"Dispatching {len(tasks)} PyRat jobs across {resolved_workers} workers ({worker_threads} threads each, budget {parallel_config.core_budget()} of {parallel_config.available_cores()} cores)")

        runner = ProcessPoolRunner(logger=self.logger, max_workers=resolved_workers)
        runner.run(tasks, run_pyrat_job, self._job_label)

    @staticmethod
    def _job_label(job: PyRatJob) -> str:
        """Returns the log label of one subsection job, naming its suffix and the azimuth lines it covers."""
        return f"PyRat subsection {job.suffix} az[{job.crop_tuple[0]}, {job.crop_tuple[1]})"

    def _concatenate(self, temporary_directory: Path, subsections: list[Tuple[int, int, int, int]]) -> Tuple[np.ndarray, np.ndarray, dict]:
        """Merges the subsection HDF5 partials back along the azimuth axis and audits their content.

        Args:
            temporary_directory : Scratch directory holding the ``TOMO/TOMO-SR`` partials.
            subsections         : Subsection crops that were dispatched, used as a count check.

        Returns:
            Tuple of the merged DEM of shape (azimuth, range) in metres, the merged
            tomogram of shape (height, azimuth, range) and the content summary of
            ``TomogramContentAudit`` with the merged shapes added.

        Raises:
            RuntimeError : If the number of partials differs from the number of dispatched subsections, or if the merged tomogram or DEM grid differs from the crop extent.
        """
        partial_files_directory = temporary_directory / "TOMO" / "TOMO-SR"
        partial_file_paths      = sorted(partial_files_directory.iterdir())

        if len(partial_file_paths) != len(subsections):
            raise RuntimeError(f"PyRat produced {len(partial_file_paths)} artifacts in {partial_files_directory} but {len(subsections)} subsections were dispatched: {[path.name for path in partial_file_paths]}")

        self.logger.subsection(f"[Concatenation] Merging {len(partial_file_paths)} subsection artifacts")

        dem_shapes      : list[Tuple[int, ...]] = []
        tomogram_shapes : list[Tuple[int, ...]] = []
        dem_dtype      = None
        tomogram_dtype = None

        for partial_file_path in partial_file_paths:
            with h5py.File(str(partial_file_path), "r") as hdf5_file:
                dem_shapes.append(hdf5_file["DEM"].shape)
                tomogram_shapes.append(hdf5_file["tomogram"].shape)
                dem_dtype      = hdf5_file["DEM"].dtype
                tomogram_dtype = hdf5_file["tomogram"].dtype

        AZIMUTH_AXIS = 1

        combined_dem_shape      = (sum(shape[0] for shape in dem_shapes),) + dem_shapes[0][1:]
        combined_tomogram_shape = tomogram_shapes[0][:AZIMUTH_AXIS] + (sum(shape[AZIMUTH_AXIS] for shape in tomogram_shapes),) + tomogram_shapes[0][AZIMUTH_AXIS + 1:]
        expected_grid           = (self.config.crop.azimuth_size, self.config.crop.range_size)

        if tuple(combined_tomogram_shape[1:]) != expected_grid or tuple(combined_dem_shape) != expected_grid:
            flags = f"apply_presumming={self.config.tomogram_config.apply_presumming}, apply_resampling={self.config.tomogram_config.apply_resampling}"
            raise RuntimeError(f"Merged tomogram grid {tuple(combined_tomogram_shape[1:])} and DEM grid {tuple(combined_dem_shape)} must both equal the crop extent {expected_grid} of crop {self.config.crop.as_tuple()} ({flags}); the interferogram stage loads the SLCs on the raw crop, so a tomogram on another grid would not line up with the primary, the secondaries and the geometry field pixel for pixel")

        planned_bytes = int(np.prod(combined_tomogram_shape)) * np.dtype(tomogram_dtype).itemsize + int(np.prod(combined_dem_shape)) * np.dtype(dem_dtype).itemsize
        self.logger.subsection(f"[Concatenation] Allocating {planned_bytes / 1e9:.2f} GB in RAM: tomogram {combined_tomogram_shape} {np.dtype(tomogram_dtype)} plus DEM {combined_dem_shape} {np.dtype(dem_dtype)}")

        combined_dem      = np.empty(combined_dem_shape,      dtype=dem_dtype)
        combined_tomogram = np.empty(combined_tomogram_shape, dtype=tomogram_dtype)

        audit           = TomogramContentAudit(self.config.crop)
        dem_offset      = 0
        tomogram_offset = 0

        for index, partial_file_path in enumerate(partial_file_paths):
            strip_start = self.config.crop.azimuth_start + tomogram_offset
            strip_end   = strip_start + tomogram_shapes[index][AZIMUTH_AXIS]
            self.logger.subsection(f"[Concatenation] {index + 1}/{len(partial_file_paths)} {partial_file_path.name} -> azimuth [{strip_start}, {strip_end})")

            with h5py.File(str(partial_file_path), "r") as hdf5_file:
                dem_chunk      = hdf5_file["DEM"][:]
                tomogram_chunk = hdf5_file["tomogram"][:]

            dem_width      = dem_chunk.shape[0]
            tomogram_width = tomogram_chunk.shape[1]

            combined_dem[dem_offset:dem_offset + dem_width]                 = dem_chunk
            combined_tomogram[:, tomogram_offset:tomogram_offset + tomogram_width] = tomogram_chunk

            audit.add_strip(tomogram_offset, dem_chunk, tomogram_chunk)

            dem_offset      += dem_width
            tomogram_offset += tomogram_width

            del dem_chunk, tomogram_chunk

        self.logger.subsection(f"Combined DEM shape      : {combined_dem.shape}")
        self.logger.subsection(f"Combined Tomogram shape : {combined_tomogram.shape}")

        content = {**audit.summary(), "tomogram_shape": list(combined_tomogram.shape), "dem_shape": list(combined_dem.shape)}
        TomogramContentAudit.log_summary(content, self.logger)

        return combined_dem, combined_tomogram, content

    def _save(self, tomogram_path: Path, dem_path: Path, tomogram_array: np.ndarray, dem_array: np.ndarray) -> None:
        """Writes the merged tomogram and DEM as .npy files.

        Args:
            tomogram_path  : Destination path for the tomogram.
            dem_path       : Destination path for the DEM.
            tomogram_array : Tomogram of shape (height, azimuth, range).
            dem_array      : DEM of shape (azimuth, range), in metres.
        """
        FileIO.ensure_dir(tomogram_path.parent)
        np.save(str(tomogram_path), tomogram_array, allow_pickle=False)
        np.save(str(dem_path),      dem_array,      allow_pickle=False)

    def _cleanup_temp(self, temporary_directory: Path) -> None:
        """Removes the scratch directory, logging an error if it cannot be deleted."""
        if not temporary_directory.exists():
            return

        try:
            shutil.rmtree(temporary_directory)
        except OSError as error:
            self.logger.error(f"Temporary directory NOT removed: {temporary_directory} ({error}); its partial HDF5 sections still occupy the scratch volume and must be deleted by hand")
            return

        self.logger.subsection("Temporary directory cleaned up. \n")

    def run(self, tomogram_path: Path, dem_path: Path, stack_identifier: str, tomogram_config: TomogramConfig) -> dict:
        """Beamforms, merges and saves the tomogram and DEM for the configured crop.

        Args:
            tomogram_path    : Destination .npy path for the tomogram.
            dem_path         : Destination .npy path for the DEM.
            stack_identifier : Identifier of the F-SAR stack being beamformed.
            tomogram_config  : Tomogram configuration driving the subsection jobs.

        Returns:
            Content summary of the merged cube, as returned by ``_concatenate``.
        """
        self.logger.section("[Generating Tomogram]")
        self.logger.subsection(f"Target: {tomogram_path.name}")

        temporary_directory = self._create_temp()

        try:
            subsections = self._divide_crop(tomogram_config)
            self._dispatch_workers(subsections, stack_identifier, tomogram_config, temporary_directory)

            with self.logger.timer("Concatenation"):
                combined_dem, combined_tomogram, content = self._concatenate(temporary_directory, subsections)

            with self.logger.timer("Saving tomogram and DEM"):
                self._save(tomogram_path, dem_path, combined_tomogram, combined_dem)

            self.logger.subsection(f"Tomogram saved : {tomogram_path} ({combined_tomogram.nbytes / 1e9:.2f} GB)")
            self.logger.subsection(f"DEM saved      : {dem_path} ({combined_dem.nbytes / 1e9:.2f} GB)")
        finally:
            self._cleanup_temp(temporary_directory)
            gc.collect()

        return content


class TomogramGenerator(GeneratorBase):
    """Runs the tomogram stage inside the PyRat environment from a JSON spec."""

    def _build_config(self) -> ProcessingConfig:
        """Returns the processing configuration reconstructed from the launcher spec."""
        return ProcessingConfig(
            crop             = CropRegion(*self.spec["crop"]),
            tomogram_config  = self._tomogram_config(),
            parallel         = ParallelConfig(
                effort           = self.spec["effort"],
                tomogram_workers = self.spec["tomogram_workers"],
                pyrat_threads    = self.spec["pyrat_threads"],
            ),
            paths            = self._paths(),
            dataset_type     = self.spec["dataset_type"],
            stack_identifier = self.spec["stack_identifier"],
        )

    def run(self) -> None:
        """Reports the resolved settings, generates the tomogram and DEM and writes the result JSON."""
        config = self._build_config()

        self.logger.section("[Tomogram Generation]")
        self.logger.kv_table({
            "Stack id"        : config.stack_identifier,
            "Track selection" : config.tomogram_config.track_selection,
            "Crop"            : config.crop.as_tuple(),
            "Output"          : self.spec["tomogram_path"],
        })

        content = TomogramProcessor(config, logger=self.logger).run(
            tomogram_path    = Path(self.spec["tomogram_path"]),
            dem_path         = Path(self.spec["dem_path"]),
            stack_identifier = config.stack_identifier,
            tomogram_config  = config.tomogram_config,
        )

        FileIO.save_json({"content": content, "provenance": self.provenance()}, Path(self.spec["result_path"]))

        self.logger.subsection(f"Tomogram result written: {self.spec['result_path']}")
