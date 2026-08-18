"""Entry point recomputing metrics, summaries and plots for parameter-extraction trials."""

from __future__ import annotations

import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from _bootstrap import EnvironmentPinner


def main() -> None:
    """Parses the CLI overrides, logs the queue and runs parameter-extraction inference."""
    EnvironmentPinner.threads()

    from configuration.param_extraction                         import ParamExtractionInferenceConfig
    from pipelines.processing.param_extraction.inference        import ParamExtractionInferenceScheduler
    from tools.runtime.config_cli                               import ConfigCli
    from tools.monitoring.logger                                import Logger

    config = ConfigCli(ParamExtractionInferenceConfig(), description="Recompute Gaussian-fit metrics, summaries, and plots for one or more parameter-extraction trials").apply()
    logger = Logger(log_dir="logs", name="analyze_param_extraction")

    logger.section("Parameter-extraction inference queue")
    logger.kv_table({
        "Params dir" : str(config.params_dir),
        "Trials"     : len(config.run_tags) if config.run_tags else "auto",
        "Make plots" : config.make_plots,
        "kz grid"    : f"{config.kz_grid_points} points to {config.kz_grid_max} rad/m",
    }, title="Configuration")

    ParamExtractionInferenceScheduler(config, logger).run()

    logger.close()


if __name__ == "__main__":
    main()
