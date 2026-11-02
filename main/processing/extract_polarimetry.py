"""Command-line entry point extending preprocessed datasets with the polarimetric primary.

Resolves the queue of preprocessed dataset directories and runs
``PolarimetryPipeline`` on each: the primary pass is read again in every
polarisation inside the PyRat environment, over the dataset's own crop, and
stored as the Pauli-ready ``primary_polarimetric`` artifact the Cube tab
decomposes into surface, double-bounce and volume scattering.
"""

from __future__ import annotations

import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from pathlib import Path

from _bootstrap import EnvironmentPinner

from configuration.sar.polarimetry_config import PolarimetryEntryConfig
from tools.runtime.config_cli             import ConfigCli
from tools.monitoring.logger              import Logger


def main() -> None:
    """Runs the polarimetric extraction over every queued dataset.

    Reads the entry configuration from the command line, resolves the dataset
    queue under the base path and extends the datasets in sequence. The entry
    log closes with the exception and an ABORTED banner when any step raises.
    """
    EnvironmentPinner.threads()

    config = ConfigCli(PolarimetryEntryConfig(), description="Polarimetric primary extraction over preprocessed datasets, dispatched into the PyRat environment").apply()

    from pipelines.processing.polarimetry.pipeline import PolarimetryPipeline
    from pipelines.shared.dataset.dataset_queue    import DatasetQueueResolver

    with Logger(log_dir="logs", name="extract_polarimetry") as logger:
        base_path    = Path(config.dataset_base_path)
        dataset_dirs = DatasetQueueResolver(base_path, config.dataset_filter).resolve()

        logger.section("Polarimetry queue")
        logger.kv_table({
            "Datasets"    : len(dataset_dirs),
            "Queue"       : ", ".join(d.name for d in dataset_dirs),
            "Base path"   : str(base_path),
            "Filter"      : config.dataset_filter or "all dataset directories",
            "Environment" : config.tomogram_env_name,
            "PyRat"       : str(config.pyrat_directory),
            "Threads"     : config.pyrat_threads,
            "Overwrite"   : config.overwrite,
        }, title="Configuration")

        for index, dataset_dir in enumerate(dataset_dirs):
            logger.section(f"[Dataset {index + 1}/{len(dataset_dirs)}] {dataset_dir.name}")
            PolarimetryPipeline(dataset_dir, config, logger).run()


if __name__ == "__main__":
    main()
