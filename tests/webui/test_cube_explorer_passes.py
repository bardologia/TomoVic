"""Tests for the cube explorer's raw pass browser.

Covers the pass metadata published with the cube, amplitude and interferometric
phase rendering with index guards, generated labels for a run without a pass
labelling, the refusal of a labelling that does not count every pass, and the
absence of the block when the run stores no secondary stack.
"""

from __future__ import annotations

import time

from tests.webui.preproc_fixtures import loaded_run, make_preproc_run, open_runs


def test_passes_meta(tmp_path):
    """Checks the pass block lists the labels, count and phase availability."""
    explorer, _ = loaded_run(tmp_path, with_passes=True, pass_labels=("T01", "T02", "T03"))

    passes = explorer.load_status()["cube"]["passes"]
    assert passes == {"labels": ["T01", "T02", "T03"], "n_passes": 3, "phase": True}


def test_pass_map_renders_amplitude_and_phase(tmp_path):
    """Checks amplitude renders for every pass and phase for the secondaries only."""
    explorer, cube_id = loaded_run(tmp_path, with_passes=True, pass_labels=("T01", "T02", "T03"))

    for index in range(3):
        png = explorer.pass_map_png(cube_id, "amplitude", index)
        assert png and png[:4] == b"\x89PNG"

    assert explorer.pass_map_png(cube_id, "phase", 1)[:4] == b"\x89PNG"
    assert explorer.pass_map_png(cube_id, "phase", 0) is None
    assert explorer.pass_map_png(cube_id, "phase", 3) is None
    assert explorer.pass_map_png(cube_id, "amplitude", 3) is None
    assert explorer.pass_map_png(cube_id, "banana", 0) is None
    assert explorer.pass_map_png("wrong", "amplitude", 0) is None


def test_passes_generate_labels_without_labelling(tmp_path):
    """Checks a run recording no pass labels publishes generated labels, primary first."""
    explorer, _ = loaded_run(tmp_path, with_passes=True, pass_labels=None)

    assert explorer.load_status()["cube"]["passes"]["labels"] == ["primary", "pass 01", "pass 02"]


def test_passes_refuse_miscounted_labels(tmp_path):
    """Checks a labelling that does not count the primary plus every secondary fails the load."""
    make_preproc_run(tmp_path, with_passes=True, pass_labels=("T01", "T02"))
    explorer, run_ids = open_runs(tmp_path, expected=1)

    assert explorer.start_load(run_ids[0])["ok"]

    deadline = time.time() + 30.0
    while explorer.load_status()["state"] == "loading" and time.time() < deadline:
        time.sleep(0.05)

    status = explorer.load_status()
    assert status["state"] == "error"
    assert "pass labels" in status["error"]


def test_passes_absent_without_stack(tmp_path):
    """Checks a run that stores no secondaries publishes no pass block."""
    explorer, cube_id = loaded_run(tmp_path)

    assert explorer.load_status()["cube"]["passes"] is None
    assert explorer.pass_map_png(cube_id, "amplitude", 0) is None


def test_cbar_serves_the_phase_colormap(tmp_path):
    """Checks the colour bar whitelist carries the cyclic phase colormap."""
    explorer, _ = loaded_run(tmp_path)

    assert explorer.cbar_png("twilight")[:4] == b"\x89PNG"
