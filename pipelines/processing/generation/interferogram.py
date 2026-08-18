"""Builds the DEM-flattened interferometric stack from an F-SAR project via PyRat.

Loads the primary and secondary SLCs, removes the DEM-induced phase ramp from each
secondary, and writes the primary, the secondary stack and the flattened
interferograms alongside the extracted track baselines, profiles and acquisition
parameters.
"""

from __future__ import annotations

import gc
from pathlib import Path
from typing  import Tuple

import numpy as np

from configuration.sar.processing_config  import (
    ParallelConfig,
    ProcessingConfig,
)
from tools.sar.pyrat_env                  import PyRatEnvironment
from tools.data.io                        import FileIO
from tools.monitoring.logger              import Logger
from tools.data.regions                   import CropRegion
from pipelines.processing.generation.base import GeneratorBase
from tools.baselines                      import BaselineExtractor, TrackBaselines, TrackProfiles
from tools.sar                            import TrackParameterCollector, TrackParameters


class InterferogramProcessor:
    """Assembles the flattened interferometric stack for one F-SAR crop.

    Attributes:
        config: Processing configuration naming the F-SAR project, crop and paths.
        logger: Logger for the stage report.
        track_baselines: Baseline table of the loaded passes, or None before ``build``.
        track_profiles: Per-azimuth baseline profiles, or None before ``build``.
        track_parameters: Acquisition parameters of the loaded passes, or None before ``build``.
    """

    def __init__(self, config: ProcessingConfig, logger: Logger) -> None:
        """Configures the processor and puts the PyRat root on ``sys.path``.

        Args:
            config: Processing configuration for this stack.
            logger: Logger for initialization and stage output.
        """
        self.config           = config
        self.logger           = logger
        self.track_baselines  = None
        self.track_profiles   = None
        self.track_parameters = None

        self.logger.section("[InterferogramProcessor Initialization]")
        self.logger.subsection(f"Dataset Type  : {self.config.dataset_type}")
        self.logger.subsection(f"PyRat Threads : {self.config.parallel.interferogram_threads()}")

        PyRatEnvironment.ensure_root_on_sys_path(str(self.config.paths.pyrat_directory))

    def _build_from_fsar(self, crop_tuple: Tuple[int, int, int, int]) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Builds the stack from an F-SAR project and records its track metadata.

        Args:
            crop_tuple: Crop as (azimuth_start, azimuth_end, range_start, range_end) in pixels.

        Returns:
            Tuple of the primary SLC of shape (azimuth, range), the secondary stack of
            shape (secondaries, azimuth, range) and the flattened interferograms of the
            same shape, all complex64.
        """
        from pyrat import pyrat_init, tomo

        self.logger.subsection("Initializing PyRat for FSAR...")
        pyrat_init(debug=False, nthreads=self.config.parallel.interferogram_threads())
        tomogram_config = self.config.tomogram_config

        tomography_object = tomo.FuSARtomo(
            FuSARproject = tomogram_config.fusar_project_path,
            select       = tomogram_config.track_selection,
            id           = self.config.stack_identifier,
            basedir      = tomogram_config.base_directory,
            polarisation = tomogram_config.polarisation,
            crop         = list(crop_tuple),
        )

        self.logger.subsection(f"[FSAR] Master: {tomography_object.master}")
        self.logger.subsection(f"[FSAR] Slaves ({len(tomography_object.slaves)}):")

        for slave_index, slave in enumerate(tomography_object.slaves, start=1):
            self.logger.subsection(f"  - [{slave_index}] {slave}")

        pass_directories = [tomography_object.master, *tomography_object.slaves]

        self.track_baselines, self.track_profiles = self._extract_baselines(pass_directories, crop_tuple, tomogram_config.polarisation)
        self.track_parameters                     = self._extract_parameters(pass_directories, tomogram_config.polarisation)

        primary, secondaries, interferograms = self._compute_interferograms(tomography_object)
        self.logger.subsection(f"FSAR stack built — primary: {primary.shape}, secondaries: {secondaries.shape}, interferograms: {interferograms.shape}")
        return primary, secondaries, interferograms

    def _extract_baselines(self, pass_directories: list, crop_tuple: Tuple[int, int, int, int], polarisation: str) -> Tuple[TrackBaselines, TrackProfiles]:
        """Extracts the baseline table and per-azimuth baseline profiles of the passes.

        Args:
            pass_directories: Pass directories, primary first, then the secondaries.
            crop_tuple: Crop as (azimuth_start, azimuth_end, range_start, range_end) in pixels.
            polarisation: Polarisation channel the baselines are read for.

        Returns:
            Tuple of the baseline table and the per-azimuth baseline profiles.
        """
        azimuth_window  = (crop_tuple[0], crop_tuple[1])
        extractor       = BaselineExtractor.from_pass_directories([str(p) for p in pass_directories], polarisation, azimuth_window=azimuth_window)
        table, profiles = extractor.extract_with_profiles()

        self.logger.kv_table(table.describe(), title="Track Baselines")
        return table, profiles

    def _extract_parameters(self, pass_directories: list, polarisation: str) -> TrackParameters:
        """Collects the acquisition parameters of the loaded passes.

        Args:
            pass_directories: Pass directories, primary first, then the secondaries.
            polarisation: Polarisation channel the parameters are read for.

        Returns:
            Acquisition parameters (wavelength, incidence, ranges) of every pass.
        """
        parameters = TrackParameterCollector.from_pass_directories([str(p) for p in pass_directories], polarisation).collect()

        self.logger.kv_table(parameters.describe(), title="Track Parameters")
        return parameters

    def _compute_interferograms(self, tomography_object) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Loads every SLC and forms the DEM-flattened interferograms.

        Each interferogram carries the clipped secondary amplitude and the phase of the
        primary against the DEM-deramped secondary.

        Args:
            tomography_object: PyRat ``FuSARtomo`` object naming the primary and secondaries.

        Returns:
            Tuple of the primary SLC of shape (azimuth, range), the secondary stack of
            shape (secondaries, azimuth, range) and the flattened interferograms of the
            same shape, all complex64.
        """
        import pyrat as pyrat_module
        from pyrat import getdata

        raw_options  = tomography_object.project.get("options", "")
        options_list = [opt.split("=") for opt in raw_options.split(",") if opt]
        options      = {opt[0].lower().strip(): True if len(opt) == 1 else opt[1].strip() for opt in options_list}
        suffix       = options.get("suffix", "")

        if not suffix:
            self.logger.subsection("[FSAR] Project options declare no 'suffix' entry — loading INF products without a coregistration suffix")

        self.logger.subsection("[FSAR] Loading primary SLC")
        primary_slc = getdata(
            pyrat_module.load.fsar(
                tomography_object.master,
                product       = "RGI-SLC",
                polarisations = tomography_object.polarisation,
                bands         = tomography_object.band,
                crop          = tomography_object.crop,
                sym           = True,
            )
        )
        primary = primary_slc.astype(np.complex64)

        n_secondaries = len(tomography_object.slaves)

        secondaries    = np.empty((n_secondaries,) + primary.shape, dtype=np.complex64)
        interferograms = np.empty((n_secondaries,) + primary.shape, dtype=np.complex64)

        for secondary_index, secondary in enumerate(tomography_object.slaves):
            self.logger.subsection(f"[FSAR] Loading secondary SLC {secondary_index + 1}/{n_secondaries}: {secondary}")

            secondary_slc = getdata(
                pyrat_module.load.fsar(
                    secondary,
                    product       = "INF-SLC",
                    polarisations = tomography_object.polarisation,
                    bands         = tomography_object.band,
                    crop          = tomography_object.crop,
                    suffix        = suffix,
                    sym           = True,
                )
            )

            dem_phase = getdata(
                pyrat_module.load.fsar_phadem(
                    secondary,
                    bands  = tomography_object.band,
                    crop   = tomography_object.crop,
                    suffix = suffix,
                )
            )

            secondaries[secondary_index] = secondary_slc

            secondary_amplitude = np.clip(np.abs(secondary_slc), 0.0, self.config.tomogram_config.max_amplitude_clip)
            phasor              = self._compute_phasor(primary_slc, secondary_slc, dem_phase)

            interferograms[secondary_index] = secondary_amplitude * phasor

            del secondary_slc, dem_phase, phasor, secondary_amplitude

        return primary, secondaries, interferograms

    def _compute_phasor(self, primary_slc: np.ndarray, secondary_slc: np.ndarray, dem_phase: np.ndarray) -> np.ndarray:
        """Returns the unit-modulus DEM-flattened interferometric phasor.

        Args:
            primary_slc: Primary SLC of shape (azimuth, range), complex.
            secondary_slc: Secondary SLC of the same shape, complex.
            dem_phase: DEM-induced phase of the same shape, in radians.

        Returns:
            Complex phasor of shape (azimuth, range) with unit magnitude, carrying the
            flattened interferometric phase in radians.
        """
        deramped_secondary = secondary_slc * np.exp(1.0j * dem_phase)
        phasor             = primary_slc * np.conj(deramped_secondary)
        phasor            /= (np.abs(phasor) + 1e-30)

        return phasor

    def build(self, crop_tuple: Tuple[int, int, int, int]) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Builds the interferometric stack for the requested crop.

        Args:
            crop_tuple: Crop as (azimuth_start, azimuth_end, range_start, range_end) in pixels.

        Returns:
            Tuple of the primary SLC of shape (azimuth, range), the secondary stack of
            shape (secondaries, azimuth, range) and the flattened interferograms of the
            same shape.

        Raises:
            NotImplementedError: If the configured dataset type is not ``FSAR``.
        """
        self.logger.section(f"[Building Stack] Crop parameters: {crop_tuple}")

        if self.config.dataset_type != "FSAR":
            raise NotImplementedError(f"Dataset type '{self.config.dataset_type}' is not supported. Only 'FSAR' is implemented.")

        primary, secondaries, interferograms = self._build_from_fsar(crop_tuple)

        gc.collect()

        return primary, secondaries, interferograms

    def run(
        self,
        crop_tuple           : Tuple[int, int, int, int],
        primary_path         : Path,
        secondaries_path     : Path,
        interferograms_path  : Path,
    ) -> Tuple[Tuple[int, ...], Tuple[int, ...], Tuple[int, ...]]:
        """Builds the stack and saves the three arrays as .npy files.

        Args:
            crop_tuple: Crop as (azimuth_start, azimuth_end, range_start, range_end) in pixels.
            primary_path: Destination .npy path for the primary SLC.
            secondaries_path: Destination .npy path for the secondary stack.
            interferograms_path: Destination .npy path for the flattened interferograms.

        Returns:
            Tuple of the primary, secondary and interferogram array shapes.
        """
        primary, secondaries, interferograms = self.build(crop_tuple)

        FileIO.ensure_dirs(primary_path.parent, secondaries_path.parent, interferograms_path.parent)

        np.save(str(primary_path),        primary,        allow_pickle=False)
        np.save(str(secondaries_path),    secondaries,    allow_pickle=False)
        np.save(str(interferograms_path), interferograms, allow_pickle=False)

        self.logger.subsection(f"Primary saved        : {primary_path}        (shape: {primary.shape})")
        self.logger.subsection(f"Secondaries saved    : {secondaries_path}    (shape: {secondaries.shape})")
        self.logger.subsection(f"Interferograms saved : {interferograms_path} (shape: {interferograms.shape})")

        shapes = tuple(primary.shape), tuple(secondaries.shape), tuple(interferograms.shape)
        del primary, secondaries, interferograms
        gc.collect()

        return shapes


class InterferogramGenerator(GeneratorBase):
    """Runs the interferogram stage inside the PyRat environment from a JSON spec."""

    def _build_config(self) -> ProcessingConfig:
        """Returns the processing configuration reconstructed from the launcher spec."""
        return ProcessingConfig(
            crop             = CropRegion(*self.spec["crop"]),
            tomogram_config  = self._tomogram_config(),
            parallel         = ParallelConfig(effort=self.spec["effort"], pyrat_threads=self.spec["pyrat_threads"]),
            paths            = self._paths(),
            dataset_type     = self.spec["dataset_type"],
            stack_identifier = self.spec["stack_identifier"],
        )

    def run(self) -> None:
        """Builds the stack, saves the track metadata and writes the result JSON."""
        config    = self._build_config()
        processor = InterferogramProcessor(config, logger=self.logger)

        primary_shape, secondaries_shape, interferograms_shape = processor.run(
            crop_tuple          = config.crop.as_tuple(),
            primary_path        = Path(self.spec["primary_path"]),
            secondaries_path    = Path(self.spec["secondaries_path"]),
            interferograms_path = Path(self.spec["interferograms_path"]),
        )

        pass_labels = None

        if processor.track_baselines is not None:
            baselines_path = Path(self.spec["baselines_path"])
            FileIO.ensure_dir(baselines_path.parent)
            processor.track_baselines.save(baselines_path)
            pass_labels = list(processor.track_baselines.labels)

        if processor.track_profiles is not None:
            profiles_path = Path(self.spec["profiles_path"])
            FileIO.ensure_dir(profiles_path.parent)
            processor.track_profiles.save(profiles_path)

        if processor.track_parameters is not None:
            parameters_path = Path(self.spec["parameters_path"])
            FileIO.ensure_dir(parameters_path.parent)
            processor.track_parameters.save(parameters_path)

        result = {
            "primary_shape"        : list(primary_shape),
            "secondaries_shape"    : list(secondaries_shape),
            "interferograms_shape" : list(interferograms_shape),
            "pass_labels"          : pass_labels,
        }

        FileIO.save_json(result, Path(self.spec["result_path"]))

        self.logger.subsection(f"Interferogram result written: {self.spec['result_path']}")
