"""Entry point comparing preprocessing trials that differ by multilook window size.

Resolves the output directory (a fresh timestamp tag under ``_window_comparison`` unless
overridden) and drives ``PreprocessingComparisonPipeline``.
"""

from __future__ import annotations

import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from pathlib import Path

from _bootstrap import EnvironmentPinner

from tools.runtime.run_tag import RunTag


def main() -> None:
    """Runs the multilook-window comparison and logs where the report landed."""
    EnvironmentPinner.threads()

    from configuration.comparison                                import PreprocessingComparisonConfig
    from pipelines.comparison.preprocessing_comparison           import PreprocessingComparisonPipeline
    from tools.runtime.config_cli                                import ConfigCli
    from tools.monitoring.logger                                 import Logger

    config = ConfigCli(PreprocessingComparisonConfig(), description="Compare preprocessing trials differing by multilook window size").apply()

    runs_dir = Path(config.runs_dir)
    base_out = Path(config.output_dir) if config.output_dir else runs_dir / "_window_comparison"
    out_dir  = base_out / RunTag.now()

    with Logger(log_dir=str(out_dir / "logs"), name="compare_preprocessing_trials") as logger:
        logger.section("Preprocessing window comparison")
        logger.kv_table({
            "Runs dir"     : str(runs_dir),
            "Trials"       : len(config.run_tags) if config.run_tags else "auto",
            "Pixel sample" : config.pixel_sample,
            "Block size"   : config.block_size,
            "Output dir"   : str(out_dir),
        }, title="Configuration")

        report = PreprocessingComparisonPipeline(config=config, out_dir=out_dir, logger=logger).run()

        logger.info(f"\nComparison written to: {report.parent}")


if __name__ == "__main__":
    main()
