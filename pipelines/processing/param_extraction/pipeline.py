"""Fits multi-Gaussian elevation profiles to a tomogram and persists the results.

One pipeline instance covers an extraction group: a single k_max sharing the tomogram
load and the peak initialisation across every fit mode and lambda permutation.
"""

from __future__ import annotations

import gc
from pathlib import Path
from typing  import Dict, Tuple

import numpy as np

from configuration.param_extraction              import ExtractionConfig
from pipelines.processing.param_extraction.io    import ExtractionMetadataManager, ParameterIO
from pipelines.processing.param_extraction.queue import ExtractionGroup
from tools.data.gaussians                        import GaussianSlotSorter
from tools.monitoring.logger                     import Logger
from tools.runtime.config_cli                    import ConfigCli


class ParameterExtractor:
    """Drives the JAX GPU fitter and sorts the fitted slots by centroid height.

    Attributes:
        logger: Logger for the extraction report.
        k_max: Largest model order the fitter evaluates.
        activity_threshold: Amplitude above which a Gaussian slot counts as active.
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
            logger: Logger for the extraction report.
            modes: Fit mode names selecting which parameters are free.
            lambda_values: Model-order penalty weights to fit in parallel.
            k_max: Largest model order the fitter evaluates.
            threshold_factor: Peak fraction below which profile bins are zeroed.
            truncation_index: Elevation bin above which the profile is truncated.
            prominence_frac: Minimum peak prominence, as a fraction of the profile peak.
            sigma_init_divisor: Divisor applied to the initial Gaussian widths.
            activity_threshold: Amplitude above which a slot counts as active.
            range_batch_size: Number of range bins loaded per batch.
            adam_steps: Adam iterations per fit.
            adam_lr: Adam learning rate.
            adam_b1: Adam first-moment decay.
            adam_b2: Adam second-moment decay.
            gpu_pixel_batch_size: Number of pixels optimised per GPU batch.
            init_workers: Worker processes used for the peak initialisation.
            peak_initialiser: Override for the peak initialiser, or None for the default.
            kernel_backend: Override for the fitting kernel backend, or None for the default.
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
        self.logger.subsection(f"Backend : JAX GPU (modes: {', '.join(modes)})")
        self.logger.subsection(f"Lambdas : {list(lambda_values)}")

    def run(self, tomogram_path: Path, height_range: Tuple[float, float]) -> Dict[tuple, Tuple[np.ndarray, dict]]:
        """Fits every mode/lambda permutation and sorts each result by centroid height.

        Args:
            tomogram_path: Path of the tomogram of shape (height, azimuth, range).
            height_range: Elevation axis limits as (minimum, maximum), in metres.

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
        group: Extraction group naming the k_max, modes, lambdas and per-permutation configs.
        shared: Extraction configuration shared by every permutation in the group.
        tomogram_path: Tomogram discovered for the group's dataset.
        height_range: Elevation axis limits as (minimum, maximum), in metres.
        owns_logger: Whether the pipeline created the logger and must close it.
        logger: Logger for the stage report.
        parameter_extractor: Fitter driving the group's permutations.
        parameter_io: Writer for the parameter stacks and diagnostics.
        entry_config: Resolved entry config persisted into every permutation's docs, or None.
    """

    def __init__(self, group: ExtractionGroup, logger: Logger | None = None, peak_initialiser: object | None = None, kernel_backend: tuple | None = None, entry_config=None) -> None:
        """Discovers the group's tomogram and builds its extractor and writers.

        Args:
            group: Extraction group to run.
            logger: Logger to reuse; when None, a run-scoped logger is created and owned.
            peak_initialiser: Override for the peak initialiser, or None for the default.
            kernel_backend: Override for the fitting kernel backend, or None for the default.
            entry_config: Optional resolved entry config persisted into every
                permutation's output directory so the sweep can be copied from
                the launch console.
        """
        self.group         = group
        self.shared        = group.shared
        self.entry_config  = entry_config
        self.tomogram_path = self.shared.discover_tomogram_path()
        self.height_range  = self.shared.discover_height_range()

        log_dir = Path(self.shared.processed_data_path) / "params" / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)

        self.owns_logger = logger is None
        self.logger      = logger or Logger(log_dir = str(log_dir), name = f"param_extraction_k{group.k_max}", level = "INFO")

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
        self.parameter_io = ParameterIO(logger=self.logger)

        self.logger.section("[Param Extraction Pipeline Initialized]")
        self.logger.subsection(f"Source tomogram : {self.tomogram_path}")
        self.logger.subsection(f"Height range    : {self.height_range}")
        self.logger.subsection(f"k_max           : {group.k_max}")
        self.logger.subsection(f"Fit modes       : {group.modes}")
        self.logger.subsection(f"Lambda values   : {group.lambda_values}")
        self.logger.subsection(f"Permutations    : {len(group.configs)}")

    def _stage_extract(self) -> Dict[tuple, Tuple[np.ndarray, dict]]:
        """Fits every permutation in the group.

        Returns:
            Mapping from (mode, lambda) to the parameter stack of shape
            (3 * k_max, azimuth, range) and its fit diagnostics.
        """
        self.logger.subsection("Extracting multi-Gaussian parameters (shared load + init across modes and lambdas)")
        return self.parameter_extractor.run(tomogram_path = self.tomogram_path, height_range = self.height_range)

    def _stage_save(self, config: ExtractionConfig, parameters_array: np.ndarray, diagnostics: dict) -> dict[str, Path]:
        """Saves one permutation's parameters, diagnostics and run metadata.

        Args:
            config: Extraction configuration of this permutation, naming its output paths.
            parameters_array: Parameter stack of shape (3 * k_max, azimuth, range).
            diagnostics: Fit diagnostics arrays for this permutation.

        Returns:
            Mapping with the parameter, diagnostics and metadata paths, the output
            directory and the source tomogram path.
        """
        npy_path  = self.parameter_io.save_params(parameters_array, config.parameters_npy_path)
        diag_path = self.parameter_io.save_diagnostics(diagnostics, config.diagnostics_npz_path)
        meta_path = ExtractionMetadataManager(config, logger=self.logger).save_run_metadata(npy_path, diag_path, self.tomogram_path, self.height_range)

        if self.entry_config is not None:
            resolved_path = ConfigCli.save_resolved(self.entry_config, config.output_directory / "docs" / "resolved_entry_config.json")
            self.logger.subsection(f"Resolved entry config saved: {resolved_path}")

        return {
            "parameters_npy"   : npy_path,
            "diagnostics_npz"  : diag_path,
            "metadata"         : meta_path,
            "output_directory" : config.output_directory,
            "source_tomogram"  : self.tomogram_path,
        }

    def run(self) -> Dict[tuple, dict]:
        """Fits and saves every permutation in the group.

        Returns:
            Mapping from (mode, lambda) to that permutation's saved-artifact paths.
        """
        self.logger.section("[Param Extraction Pipeline Execution]")

        results = self._stage_extract()

        saved = {}
        for key, (parameters_array, diagnostics) in results.items():
            config     = self.group.configs[key]
            self.logger.section(f"[Saving] {config.output_subdir_name}")
            saved[key] = self._stage_save(config, parameters_array, diagnostics)

        del results
        gc.collect()

        self.logger.section("[Param Extraction Completed]")

        if self.owns_logger:
            self.logger.close()

        return saved
