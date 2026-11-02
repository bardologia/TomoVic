"""Command-line entry point that reads a dataset's primary pass in every polarisation via pyrat.

Runs inside the pyrat conda environment (for example ``stetools``) and is
invoked with a JSON job spec written by the polarimetry pipeline.
"""

from __future__ import annotations

import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

import argparse
from pathlib import Path

from _bootstrap import EnvironmentPinner


def main() -> None:
    """Extracts the polarimetric primary described by the ``--spec`` JSON file.

    Pins the thread environment, parses the spec path and runs
    ``PolarimetricPrimaryGenerator``, logging into the spec's own directory. The
    generator is imported once that log is open, so a failed import in the
    PyRat environment ends the log with its traceback.
    """
    EnvironmentPinner.threads()

    parser = argparse.ArgumentParser(description="Read the primary pass in every polarisation via pyrat (runs under the pyrat env, e.g. stetools)")
    parser.add_argument("--spec", required=True, help="Path to the polarimetric primary job spec JSON")
    args = parser.parse_args()

    from tools.monitoring.logger import Logger

    spec_path = Path(args.spec)

    with Logger(log_dir=str(spec_path.parent), name="polarimetric_primary") as logger:
        from pipelines.processing.polarimetry.extraction import PolarimetricPrimaryGenerator

        PolarimetricPrimaryGenerator.from_spec_file(spec_path, logger).run()


if __name__ == "__main__":
    main()
