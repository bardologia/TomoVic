"""Entry point rendering stack overviews and value distributions for preprocessing trials."""

from __future__ import annotations

import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from _bootstrap import EnvironmentPinner


def main() -> None:
    """Parses the CLI overrides, logs the queue and runs preprocessing inference."""
    EnvironmentPinner.threads()

    from configuration.sar.processing_config           import PreprocessInferenceConfig
    from pipelines.processing.generation.inference      import PreprocessingInferenceScheduler
    from tools.runtime.config_cli                       import ConfigCli
    from tools.monitoring.logger                        import Logger

    config = ConfigCli(PreprocessInferenceConfig(), description="Render stack-overview plots and amplitude/phase/DEM value distributions for one or more preprocessing trials").apply()
    logger = Logger(log_dir="logs", name="analyze_preprocessing")

    logger.section("Preprocessing inference queue")
    logger.kv_table({
        "Runs dir" : str(config.runs_dir),
        "Trials"   : len(config.run_tags) if config.run_tags else "auto",
    }, title="Configuration")

    PreprocessingInferenceScheduler(config, logger).run()

    logger.close()


if __name__ == "__main__":
    main()
