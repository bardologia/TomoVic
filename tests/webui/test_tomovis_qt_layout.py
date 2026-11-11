"""Runs the TomoVis Qt layout port suite under node.

``tomovis_qt_layout_test.mjs`` loads ``tomovis_widgets.js`` into a node sandbox
and replays the geometry recorded from the original TomoVis window by
``webui/tools/tomovis_parity/qt_layout.py`` (``fixtures/tomovis_qt_layout/layout.json``):
the qGeomCalc share of the two Slicer stacks at every recorded step, the
QSplitter sizes of the ImageView ROI plot through drags, collapses, resizes
and setSizes calls, and the splitter size hint Qt caches when the ROI plot is
shown or hidden.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).with_name("tomovis_qt_layout_test.mjs")


def test_the_qt_layout_port_replays_the_recorded_geometry():
    """Every case of the node suite passes; skipped only where node is not installed."""
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is not installed on this machine, so the Qt layout suite cannot run")

    result = subprocess.run([node, str(SCRIPT)], capture_output=True, text=True, timeout=120)

    assert result.returncode == 0, result.stdout + result.stderr
    assert "all 3 passing" in result.stdout
