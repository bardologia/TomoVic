"""Command-line entry point for the Gaussian parameter-extraction sweep.

Resolves the queue of preprocessed dataset directories, expands it into
extraction groups over the requested K, lambda and fit-mode permutations, and
runs ``ParamExtractionPipeline`` once per group so that each group shares a
single tomogram load and peak initialisation.
"""

from __future__ import annotations

import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from pathlib import Path

from _bootstrap import EnvironmentPinner

from configuration.param_extraction import ExtractParamsEntryConfig
from tools.runtime.config_cli       import ConfigCli
from tools.monitoring.logger        import Logger


def main() -> None:
    """Runs the parameter-extraction sweep over every queued dataset group.

    Reads the entry configuration from the command line, pins the requested
    GPUs, builds the extraction groups and executes them in sequence, logging
    the saved output paths of every permutation.
    """
    config = ConfigCli(ExtractParamsEntryConfig(), description="Gaussian parameter extraction sweep over datasets, K values, lambda values, and fit modes").apply()

    EnvironmentPinner.gpus(config.gpu_device_ids)

    from pipelines.processing.param_extraction.pipeline           import ParamExtractionPipeline
    from pipelines.processing.param_extraction.queue              import ExtractionPlanResolver
    from pipelines.processing.param_extraction.sigma.initialiser  import PeakInitialiser
    from pipelines.processing.param_extraction.sigma.selection    import KernelBackendSelector
    from pipelines.shared.dataset.dataset_queue                   import DatasetQueueResolver

    logger       = Logger(log_dir="logs", name="extract_params")
    base_path    = Path(config.dataset_base_path)
    dataset_dirs = DatasetQueueResolver(base_path, config.dataset_filter).resolve()
    groups       = ExtractionPlanResolver(config, dataset_dirs).resolve()
    permutations = sum(len(group.configs) for group in groups)

    peak_initialiser = PeakInitialiser(n_workers=config.parameter_workers)
    kernel_backend   = KernelBackendSelector().select()

    logger.section("Extraction queue")
    logger.kv_table({
        "Datasets"      : len(dataset_dirs),
        "Queue"         : ", ".join(d.name for d in dataset_dirs),
        "K values"      : config.fit_k_values,
        "Lambda values" : config.fit_lambda_values,
        "Fit modes"     : config.fit_modes,
        "Groups"        : len(groups),
        "Permutations"  : permutations,
        "Base path"     : str(base_path),
        "Filter"        : config.dataset_filter or "all dataset directories",
        "GPUs"          : config.gpu_device_ids,
    }, title="Configuration")

    try:
        for index, group in enumerate(groups):
            logger.section(f"[Group {index + 1}/{len(groups)}] {group.processed_data_path.name} :: k{group.k_max} ({len(group.configs)} permutations, one shared load + init)")

            pipeline = ParamExtractionPipeline(group, peak_initialiser=peak_initialiser, kernel_backend=kernel_backend, entry_config=config)
            saved    = pipeline.run()

            for key, outputs in saved.items():
                logger.kv_table({name: str(path) for name, path in outputs.items()}, title=f"Outputs {group.configs[key].output_subdir_name}")
    finally:
        peak_initialiser.close()

    logger.close()


if __name__ == "__main__":
    main()
