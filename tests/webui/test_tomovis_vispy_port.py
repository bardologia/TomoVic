"""Runs the TomoVis 3D port's vispy replay suite under node.

``tomovis_vispy_port_test.mjs`` loads ``tomovis_vispy.js``, ``tomovis_volume.js``
and ``tomovis_script_volume.js`` into a node sandbox and replays the scenarios
recorded from the original TomoVis and vispy 0.17 by
``webui/tools/tomovis_vispy_goldens.py`` (``fixtures/tomovis_vispy/cameras.json``):
turntable, arcball and fly camera interactions, the reset and camera handlers,
the axis gizmo, the 4-D channel volume and the VolumeRendering script keys. Every
recorded camera state, canvas-pixel mapping and printed line must match. The
suite also checks the exported colormaps, the Python float formatting and the
generated fragment shaders.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).with_name("tomovis_vispy_port_test.mjs")


def test_the_vispy_port_replays_the_recorded_scenarios():
    """Every case of the node suite passes; skipped only where node is not installed."""
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is not installed on this machine, so the vispy port suite cannot run")

    result = subprocess.run([node, str(SCRIPT)], capture_output=True, text=True, timeout=120)

    assert result.returncode == 0, result.stdout + result.stderr
    assert "all " in result.stdout and " passing" in result.stdout
