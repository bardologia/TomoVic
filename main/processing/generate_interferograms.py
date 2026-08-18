"""Command-line entry point that builds an interferometric stack via pyrat.

Runs inside the pyrat conda environment (for example ``stetools``) and is
invoked with a JSON job spec written by the pre-processing pipeline.
"""

from __future__ import annotations

import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

import argparse
from pathlib import Path

from _bootstrap import EnvironmentPinner


def main() -> None:
    """Builds the interferometric stack described by the ``--spec`` JSON file.

    Pins the thread environment, parses the spec path and runs
    ``InterferogramGenerator``, logging into the spec's own directory.
    """
    EnvironmentPinner.threads()

    parser = argparse.ArgumentParser(description="Build the interferometric stack via pyrat (runs under the pyrat env, e.g. stetools)")
    parser.add_argument("--spec", required=True, help="Path to the interferogram job spec JSON")
    args = parser.parse_args()

    from pipelines.processing.generation.interferogram import InterferogramGenerator
    from tools.monitoring.logger                       import Logger

    spec_path = Path(args.spec)

    with Logger(log_dir=str(spec_path.parent), name="interferograms") as logger:
        InterferogramGenerator.from_spec_file(spec_path, logger).run()


if __name__ == "__main__":
    main()
