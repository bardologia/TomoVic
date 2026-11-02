"""Fits multi-Gaussian elevation profiles to a tomogram and persists the results.

One pipeline instance covers an extraction group: a single k_max sharing the tomogram
load and the peak initialisation across every fit mode and lambda permutation.
"""

from __future__ import annotations

import gc
from contextlib import nullcontext
from pathlib    import Path
from typing     import Dict, Tuple

import numpy as np
from rich.markup import escape

from configuration.param_extraction                import ExtractionConfig
from pipelines.processing.param_extraction.io      import ExtractionMetadataManager, ParameterIO, ParameterRunDirectory
from pipelines.processing.param_extraction.queue   import ExtractionGroup
from pipelines.shared.config.resolved_entry_config import ResolvedEntryConfigWriter
from tools.data.gaussians                          import GaussianSlotSorter
from tools.monitoring.logger                       import Logger
from tools.monitoring.resource_monitor             import ResourceMonitor


class ParameterExtractor:
    """Drives the JAX GPU fitter and sorts the fitted slots by centroid height.

    Attributes:
        logger             : Logger for the extraction report.
        k_max              : Largest model order the fitter evaluates.
        activity_threshold : Profile peak above which a pixel is fitted; the same value is recorded as the slot activity threshold of the run.
    """

    def __init__(
        self,
        logger               : Logger,
        modes                : list,
        lambda_values        : list,
        k_max                : int         = 5,
        threshold_factor     : float       = 0.25,
        truncation_index     : int         = 170,
        prominence_frac      : float       = 0.05,
        sigma_init_divisor   : float       = 1.0,
        activity_threshold   : float       = 1e-3,
        range_batch_size     : int         = 256,
        adam_steps           : int         = 800,
        adam_lr              : float       = 1e-2,
        adam_b1              : float       = 0.9,
        adam_b2              : float       = 0.999,
        gpu_pixel_batch_size : int         = 8192,
        init_workers         : int | None  = None,
        peak_initialiser     : object | None = None,
        kernel_backend       : tuple | None  = None,
    ) -> None:
        """Builds the GPU fitting backend for a set of fit modes and lambda values.

        Args:
            logger               : Logger for the extraction report.
            modes                : Fit mode names selecting which parameters are free.
            lambda_values        : Model-order penalty weights to fit in parallel.
            k_max                : Largest model order the fitter evaluates.
            threshold_factor     : Peak fraction below which profile bins are zeroed.
            truncation_index     : Elevation bin above which the profile is truncated.
            prominence_frac      : Minimum peak prominence, as a fraction of the profile peak.
            sigma_init_divisor   : Divisor applied to the initial Gaussian widths.
            activity_threshold   : Profile peak above which a pixel is fitted; the same value is recorded as the slot activity threshold of the run.
            range_batch_size     : Number of range bins loaded per batch.
            adam_steps           : Adam iterations per fit.
            adam_lr              : Adam learning rate.
            adam_b1              : Adam first-moment decay.
            adam_b2              : Adam second-moment decay.
            gpu_pixel_batch_size : Number of pixels optimised per GPU batch.
            init_workers         : Worker processes used for the peak initialisation.
            peak_initialiser     : Override for the peak initialiser, or None for the default.
            kernel_backend       : Override for the fitting kernel backend, or None for the default.
        """
        from pipelines.processing.param_extraction.sigma import SigmaFittingExtractor

        self.logger             = logger
        self.k_max              = k_max
        self.activity_threshold = activity_threshold

        self._gpu_extractor = SigmaFittingExtractor(
            logger               = logger,
            modes                = modes,
            lambda_values        = lambda_values,
            k_max                = k_max,
            threshold_factor     = threshold_factor,
            truncation_index     = truncation_index,
            prominence_frac      = prominence_frac,
            sigma_init_divisor   = sigma_init_divisor,
            activity_threshold   = activity_threshold,
            range_batch_size     = range_batch_size,
            adam_steps           = adam_steps,
            adam_lr              = adam_lr,
            adam_b1              = adam_b1,
            adam_b2              = adam_b2,
            gpu_pixel_batch_size = gpu_pixel_batch_size,
            init_workers         = init_workers,
            peak_initialiser     = peak_initialiser,
            kernel_backend       = kernel_backend,
        )

        self.logger.section("[Parameter Extractor Initialized]")
        self.logger.subsection(f"Backend : JAX {self._gpu_extractor.backend} (modes: {', '.join(modes)})")
        self.logger.subsection(f"Lambdas : {list(lambda_values)}")

    @property
    def outcome(self):
        """Returns the fitter's record of what the last run fitted, or None before run()."""
        return self._gpu_extractor.outcome

    @property
    def bound_shares(self) -> Dict[tuple, Dict[str, float]]:
        """Returns the per (mode, lambda) shares of active slots that ended on a clamp bound in the last run."""
        return self._gpu_extractor.bound_shares

    def run(self, tomogram_path: Path, height_range: Tuple[float, float]) -> Dict[tuple, Tuple[np.ndarray, dict]]:
        """Fits every mode/lambda permutation and sorts each result by centroid height.

        Args:
            tomogram_path : Path of the tomogram of shape (height, azimuth, range).
            height_range  : Elevation axis limits as (minimum, maximum), in metres.

        Returns:
            Mapping from (mode, lambda) to the parameter stack of shape
            (3 * k_max, azimuth, range) and its fit diagnostics.
        """
        self.logger.section(f"[Extraction Start] Source: {tomogram_path.name}")

        results        = self._gpu_extractor.run(tomogram_path, height_range)
        sorted_results = {key: (GaussianSlotSorter.by_mean(params, self.k_max, self.activity_threshold), diagnostics) for key, (params, diagnostics) in results.items()}

        self.logger.subsection("[Extraction Complete]")
        return sorted_results


class ParamExtractionPipeline:
    """Runs one extraction group end to end and saves every permutation's output.

    Attributes:
        group               : Extraction group naming the k_max, modes, lambdas and per-permutation configs.
        shared              : Extraction configuration shared by every permutation in the group.
        tomogram_path       : Tomogram discovered for the group's dataset.
        height_range        : Elevation axis limits as (minimum, maximum), in metres.
        height_range_source : Where the height range came from, and whether an override agrees with the dataset's own record.
        owns_logger         : Whether the pipeline created the logger and must close it.
        group_log_path      : File of the owned group logger, recorded in every permutation's metadata; None when the logger was passed in.
        group_log_offset    : Byte size the group log had before this launch appended to it, where this launch's record starts.
        logger              : Logger for the stage report.
        parameter_extractor : Fitter driving the group's permutations.
        parameter_io        : Writer for the parameter stacks and diagnostics.
        entry_config        : Resolved entry config persisted into every permutation's docs, or None.
        overwrite           : Whether a permutation may delete and replace an existing run in its output directory.
        resources           : Resource-monitor configuration sampled while the group runs, or None to run unmonitored.
    """

    def __init__(self, group: ExtractionGroup, logger: Logger | None = None, peak_initialiser: object | None = None, kernel_backend: tuple | None = None, entry_config=None, overwrite: bool = False, resources=None) -> None:
        """Discovers the group's tomogram and builds its extractor and writers.

        Args:
            group            : Extraction group to run.
            logger           : Logger to reuse; when None, a run-scoped logger is created and owned.
            peak_initialiser : Override for the peak initialiser, or None for the default.
            kernel_backend   : Override for the fitting kernel backend, or None for the default.
            entry_config     : Optional resolved entry config persisted into every permutation's output directory so the sweep can be copied from the launch console.
            overwrite        : Whether a permutation may delete and replace an existing run in its output directory; off, saving over one raises.
            resources        : Resource-monitor configuration block whose sampler runs while the group fits and saves, logging threshold warnings and peaks into the group log; None runs unmonitored.
        """
        self.group         = group
        self.shared        = group.shared
        self.entry_config  = entry_config
        self.overwrite     = overwrite
        self.resources     = resources
        self.tomogram_path = self.shared.discover_tomogram_path()
        self.height_range  = self.shared.discover_height_range()

        log_dir  = Path(self.shared.processed_data_path) / "params" / "logs"
        log_name = f"param_extraction_k{group.k_max}"
        log_file = log_dir / f"{log_name}.log"
        log_dir.mkdir(parents=True, exist_ok=True)

        self.owns_logger      = logger is None
        self.group_log_offset = log_file.stat().st_size if log_file.is_file() else 0
        self.logger           = logger or Logger(log_dir = str(log_dir), name = log_name, level = "INFO")
        self.group_log_path   = Path(self.logger.log_dir) / f"{self.logger.name}.log" if self.owns_logger else None

        fit_cfg = self.shared.fit_settings.fit_config

        self.parameter_extractor = ParameterExtractor(
            logger               = self.logger,
            modes                = group.modes,
            lambda_values        = group.lambda_values,
            k_max                = group.k_max,
            threshold_factor     = fit_cfg.threshold_factor,
            truncation_index     = fit_cfg.truncation_index,
            prominence_frac      = fit_cfg.prominence_frac,
            sigma_init_divisor   = fit_cfg.sigma_init_divisor,
            activity_threshold   = fit_cfg.activity_threshold,
            range_batch_size     = self.shared.range_batch_size,
            adam_steps           = self.shared.adam_steps,
            adam_lr              = self.shared.adam_lr,
            adam_b1              = self.shared.adam_b1,
            adam_b2              = self.shared.adam_b2,
            gpu_pixel_batch_size = self.shared.gpu_pixel_batch_size,
            init_workers         = self.shared.parameter_workers,
            peak_initialiser     = peak_initialiser,
            kernel_backend       = kernel_backend,
        )
        self.parameter_io        = ParameterIO(logger=self.logger)
        self.height_range_source = self._height_range_source()

        self.logger.section("[Param Extraction Pipeline Initialized]")
        self.logger.kv_table({
            "Source Tomogram" : str(self.tomogram_path),
            "Height Range"    : f"{self.height_range} from {self.height_range_source}",
            "K Max"           : group.k_max,
            "Fit Modes"       : str(group.modes),
            "Lambda Values"   : str(group.lambda_values),
            "Permutations"    : len(group.configs),
        })

    def _height_range_source(self) -> str:
        """Names where the height range came from and warns when an override disagrees with the dataset's record.

        An override applies to every dataset of the sweep, so a dataset whose
        meta/config_state.json records another tomogram height range gets
        centroids and widths in the wrong metres unless the override is a
        deliberate correction; the warning names both ranges.

        Returns:
            ``meta/config_state.json``, or the override with how it compares to the dataset's record.
        """
        recorded = self.shared.recorded_height_range()

        if self.shared.height_range is None:
            return "meta/config_state.json"

        if recorded is None:
            return "height_range override; the dataset records none"

        if recorded != tuple(float(value) for value in self.shared.height_range):
            self.logger.warning(f"height_range override {self.height_range} differs from the tomogram height range {recorded} recorded in {self.shared.metadata_directory / 'config_state.json'}; the labels of {self.group.processed_data_path.name} are fitted on the override's axis, so their centroids and widths are in the wrong metres unless the override corrects a wrong record")
            return f"height_range override, differing from the {recorded} in meta/config_state.json"

        return "height_range override, matching meta/config_state.json"

    def _resource_monitor(self):
        """Returns the resource monitor sampling this group, or a no-op context when none is configured."""
        if self.resources is None:
            return nullcontext()

        return ResourceMonitor(config=self.resources, logger=self.logger)

    def _stage_extract(self) -> Dict[tuple, Tuple[np.ndarray, dict]]:
        """Fits every permutation in the group.

        Returns:
            Mapping from (mode, lambda) to the parameter stack of shape
            (3 * k_max, azimuth, range) and its fit diagnostics.
        """
        self.logger.subsection("Extracting multi-Gaussian parameters (shared load + init across modes and lambdas)")
        return self.parameter_extractor.run(tomogram_path = self.tomogram_path, height_range = self.height_range)

    def _run_record(self) -> dict:
        """Returns the fit outcome of the group joined with the pipeline's own facts about the run.

        Returns:
            The extractor outcome keys plus ``extraction_log``, the group log file or None, and ``height_range_source``.
        """
        return {
            **self.parameter_extractor.outcome.to_metadata(),
            "extraction_log"      : None if self.group_log_path is None else str(self.group_log_path),
            "height_range_source" : self.height_range_source,
        }

    def _stage_save(self, config: ExtractionConfig, parameters_array: np.ndarray, diagnostics: dict, record: dict) -> dict[str, Path]:
        """Saves one permutation's parameters, diagnostics and run metadata.

        Args:
            config           : Extraction configuration of this permutation, naming its output paths.
            parameters_array : Parameter stack of shape (3 * k_max, azimuth, range).
            diagnostics      : Fit diagnostics arrays for this permutation.
            record           : Fit outcome keys recorded into the run metadata, from ``_run_record``, joined with this permutation's clamp-bound shares.

        Returns:
            Mapping with the parameter, diagnostics and metadata paths, the output
            directory and the source tomogram path.

        Raises:
            FileExistsError : If the output directory already holds a run and overwriting is off.
        """
        metadata = ExtractionMetadataManager(config, logger=self.logger)
        ParameterRunDirectory(self.logger).prepare(config.output_directory, self.overwrite, metadata.settings())

        npy_path  = self.parameter_io.save_params(parameters_array, config.parameters_npy_path)
        diag_path = self.parameter_io.save_diagnostics(diagnostics, config.diagnostics_npz_path)
        meta_path = metadata.save_run_metadata(npy_path, diag_path, self.tomogram_path, self.height_range, record)

        if self.entry_config is not None:
            ResolvedEntryConfigWriter.save(self.entry_config, config.output_directory, self.logger)

        return {
            "parameters_npy"   : npy_path,
            "diagnostics_npz"  : diag_path,
            "metadata"         : meta_path,
            "output_directory" : config.output_directory,
            "source_tomogram"  : self.tomogram_path,
        }

    def _copy_group_log(self, saved: Dict[tuple, dict]) -> None:
        """Copies this launch's part of the closed group log into every saved permutation's logs/ directory.

        The group log is shared by every launch on the dataset at this k_max
        and appended to, so only the bytes from this launch's RUN banner to its
        END or ABORTED banner are copied; the run directory then carries the
        timings, devices and warnings of its own fit wherever it is mailed.

        Args:
            saved : Mapping from (mode, lambda) to the saved-artifact paths, naming each output directory.
        """
        with open(self.group_log_path, "rb") as handle:
            handle.seek(self.group_log_offset)
            excerpt = handle.read()

        for paths in saved.values():
            target = Path(paths["output_directory"]) / "logs" / self.group_log_path.name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(excerpt)

    def run(self) -> Dict[tuple, dict]:
        """Fits and saves every permutation in the group.

        The configured resource monitor samples host RAM, swap, /dev/shm, CPU
        and GPU counters for the whole of the fit and the saves, so the group
        log records threshold warnings and peaks. An exception ends the group
        log with the error, naming the dataset, the k_max and how many
        permutations were saved, and an owned logger closes with the ABORTED
        banner and the traceback in place of END. Once an owned logger is
        closed, this launch's part of the group log is copied into every saved
        permutation's logs/ directory.

        Returns:
            Mapping from (mode, lambda) to that permutation's saved-artifact paths.

        Raises:
            BaseException : Whatever the extraction or a save raised, re-raised after the log recorded it.
        """
        saved = {}
        error = None

        try:
            with self._resource_monitor():
                self.logger.section("[Param Extraction Pipeline Execution]")

                results = self._stage_extract()
                record  = self._run_record()

                for key, (parameters_array, diagnostics) in results.items():
                    config     = self.group.configs[key]
                    self.logger.section(f"[Saving] {config.output_subdir_name}")
                    saved[key] = self._stage_save(config, parameters_array, diagnostics, {**record, **self.parameter_extractor.bound_shares[key]})

                del results
                gc.collect()

                self.logger.section("[Param Extraction Completed]")
                self.logger.kv_table({
                    "Permutations Saved" : len(saved),
                    "Output Base Dir"    : str(Path(self.shared.processed_data_path) / "params"),
                })

                return saved
        except BaseException as exc:
            error = exc
            self.logger.error(f"[Group Aborted] {self.group.processed_data_path.name} :: k{self.group.k_max} failed with {len(saved)} of {len(self.group.configs)} permutations saved: {type(exc).__name__}: {escape(str(exc))}")
            raise
        finally:
            if self.owns_logger:
                self.logger.close(error)
                self._copy_group_log(saved)
