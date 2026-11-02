"""Runs the browser-side stream hub tests under node.

The client half of the live-output channel lives in ``static/js/stream_hub.js``
and is exercised by ``stream_hub_client_test.mjs`` against a fake EventSource
and a recording Api stub. This test runs that script and reports its outcome.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).with_name("stream_hub_client_test.mjs")


def test_the_client_stream_hub_passes_its_node_suite():
    """Every case of the node suite passes; skipped only where node is not installed."""
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is not installed on this machine, so the client hub suite cannot run")

    result = subprocess.run([node, str(SCRIPT)], capture_output=True, text=True, timeout=120)

    assert result.returncode == 0, result.stdout + result.stderr
    assert "all " in result.stdout and " passing" in result.stdout
