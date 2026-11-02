"""Command-line entry point that measures the full scene extent of an F-SAR stack via pyrat.

Runs inside the pyrat conda environment (for example ``stetools``) and is
invoked with a JSON job spec written by the pre-processing entry when every
crop field is zero.
"""

from __future__ import annotations

import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

import argparse
from pathlib import Path

from _bootstrap import EnvironmentPinner


def main() -> None:
    """Measures the primary SLC size of the stack described by the ``--spec`` JSON file.

    Pins the thread environment, parses the spec path and runs
    ``SceneExtentGenerator``, logging into the spec's own directory. The generator is
    imported once that log is open, so a failed import in the PyRat
    environment ends the log with its traceback.
    """
    EnvironmentPinner.threads()

    parser = argparse.ArgumentParser(description="Measure the full scene extent via pyrat (runs under the pyrat env, e.g. stetools)")
    parser.add_argument("--spec", required=True, help="Path to the scene extent job spec JSON")
    args = parser.parse_args()

    from tools.monitoring.logger import Logger

    spec_path = Path(args.spec)

    with Logger(log_dir=str(spec_path.parent), name="scene_extent") as logger:
        from pipelines.processing.generation.scene_extent import SceneExtentGenerator

        SceneExtentGenerator.from_spec_file(spec_path, logger).run()


if __name__ == "__main__":
    main()
