"""Regenerates the TomoVis parity fixtures, goldens and reference screenshots.

Runs in the tomovis conda environment (PyQt5, pyqtgraph, vispy) against the
original TomoVis source, under the offscreen Qt platform. The bootstrap below
is the only place that touches ``sys.path``: it adds the TomoVis source root so
``Visualizer`` imports as in the desktop app, and TomoVic's ``webui`` for the
WebLogger. Bytecode writing is switched off so nothing lands in the source tree.

Usage:
    /home/bard/miniconda3/envs/tomovis/bin/python webui/tools/tomovis_parity/generate.py
    ... generate.py --shots <dir> --only roi_oblique plot_rgb --skip-shots
"""

from __future__ import annotations

import argparse
import os
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]

os.environ["QT_QPA_PLATFORM"]  = "offscreen"
os.environ["QT_API"]           = "pyqt5"
os.environ["PYQTGRAPH_QT_LIB"] = "PyQt5"
os.environ["MPLBACKEND"]       = "Qt5Agg"
sys.dont_write_bytecode        = True

parser = argparse.ArgumentParser(description="Regenerate the TomoVis parity fixtures, goldens and screenshots.")
parser.add_argument("--tomovis",          type=Path, default=REPO.parent / "tomovis",                                               help="TomoVis source root (holds Visualizer/)")
parser.add_argument("--fixtures",         type=Path, default=REPO / "tests" / "webui" / "fixtures" / "tomovis",                       help="committed fixture root")
parser.add_argument("--realistic-source", type=Path, default=REPO.parent / "DLR-TomoSAR" / "test_data" / "data" / "tomogram_full.npy", help="DLR-TomoSAR tomogram cropped for the screenshots")
parser.add_argument("--realistic-dir",    type=Path, default=REPO / "logs" / "tomovis_port" / "fixtures",                           help="where the realistic crops are written (gitignored)")
parser.add_argument("--shots",            type=Path, default=REPO / "logs" / "tomovis_port" / "original_shots",                    help="screenshot directory")
parser.add_argument("--figure-reference", type=Path, default=REPO / "logs" / "tomovis_port" / "golden_figures",                    help="gitignored directory receiving every figure render")
parser.add_argument("--only",             nargs="*", default=None,                                                                 help="scenario names to play (default all)")
parser.add_argument("--skip-goldens",     action="store_true",                                                                     help="do not write inputs, tables or goldens")
parser.add_argument("--skip-shots",       action="store_true",                                                                     help="do not take screenshots")
options = parser.parse_args()

sys.path.insert(0, str(REPO / "webui"))
sys.path.insert(0, str(options.tomovis.resolve()))

from fixtures   import FixtureWriter, RealisticCube
from goldens    import GoldenRunner, GoldenWriter, ScenarioBook, TableWriter
from harness    import TomoVisSession
from shots      import ShotRunner
from web_logger import WebLogger


class ParityGenerator:
    """Sequences fixture writing, golden scenarios and screenshots.

    Attributes:
        options : Parsed command-line options.
        logger  : WebLogger for progress lines.
        session : TomoVisSession over the original TomoVis.
        summary : Scenario name to its number of slot exceptions.
    """

    GENERATED = ("inputs", "goldens", "figures", "sessions", "tables")

    def __init__(self, options: argparse.Namespace, logger: WebLogger) -> None:
        """Starts the headless TomoVis session.

        Args:
            options : Parsed command-line options.
            logger  : WebLogger for progress lines.
        """

        self.options = options
        self.logger  = logger
        self.session = TomoVisSession()
        self.summary = {}

    def clear_generated(self) -> None:
        """Removes the generated fixture subdirectories so stale files cannot survive a regeneration."""

        for target in [self.options.fixtures / name for name in self.GENERATED] + [self.options.figure_reference]:
            if target.exists():
                shutil.rmtree(target)

    def write_inputs(self) -> None:
        """Writes the synthetic input cubes in every import format."""

        manifest = FixtureWriter(self.options.fixtures / "inputs", self.session.ste_io).run()
        self.logger.ok(f"{len(manifest)} input fixtures in {self.options.fixtures / 'inputs'}")

    def write_tables(self) -> None:
        """Writes the colortables, pyqtgraph LUTs and colormap lists."""

        path = TableWriter(self.options.fixtures, self.session).run()
        self.logger.ok(f"tables in {path.parent}")

    def write_goldens(self) -> None:
        """Plays the scenarios and writes their goldens."""

        scenarios = ScenarioBook().all()
        if self.options.only:
            scenarios = [scenario for scenario in scenarios if scenario["name"] in self.options.only]
        writer       = GoldenWriter(self.options.fixtures, self.options.figure_reference)
        self.summary = GoldenRunner(self.session, writer, self.options.fixtures, self.logger).run(scenarios)

    def write_shots(self) -> None:
        """Crops the realistic cubes and takes the reference screenshots."""

        realistic = RealisticCube(self.options.realistic_source, self.options.realistic_dir).run()
        ShotRunner(self.session, self.options.shots, realistic, self.logger).run()

    def report_sizes(self) -> None:
        """Logs the size of every generated fixture subdirectory and the total."""

        total = 0
        for name in self.GENERATED:
            size   = sum(path.stat().st_size for path in (self.options.fixtures / name).rglob("*") if path.is_file())
            total += size
            self.logger.info(f"{name:<9} {size / 1024:8.1f} kB")
        self.logger.info(f"{'total':<9} {total / 1024:8.1f} kB")

    def run(self) -> None:
        """Runs the requested stages in order."""

        if not self.options.skip_goldens:
            if not self.options.only:
                self.clear_generated()
                self.write_inputs()
                self.write_tables()
            self.write_goldens()
            self.report_sizes()
        if not self.options.skip_shots:
            self.write_shots()


if __name__ == "__main__":
    ParityGenerator(options, WebLogger("tomovis_parity")).run()
