"""Tests for the cube explorer's saved-figure browser.

Covers listing the figure trees of a loaded preprocessing run, path-guarded
serving of individual files and a run without any figure tree.
"""

from __future__ import annotations

from tests.webui.conftest         import load_cube
from tests.webui.preproc_fixtures import loaded_run, make_preproc_run, open_runs


def _with_figures(base):
    """Builds a run with a small figure tree and returns the loaded explorer, id and run directory."""
    run_dir = make_preproc_run(base)

    (run_dir / "images" / "slc").mkdir(parents=True)
    (run_dir / "images" / "slc" / "primary.png").write_bytes(b"\x89PNG_fake")
    (run_dir / "images" / "notes.txt").write_text("not a figure")
    (run_dir / "figures" / "cube_slices" / "az0001_rg0002").mkdir(parents=True)
    (run_dir / "figures" / "cube_slices" / "az0001_rg0002" / "range_full.png").write_bytes(b"\x89PNG_fake")
    (run_dir / "params" / "params_k2" / "images").mkdir(parents=True)
    (run_dir / "params" / "params_k2" / "images" / "walk.gif").write_bytes(b"GIF89a_fake")

    explorer, run_ids = open_runs(base, expected=1)
    load_cube(explorer, run_ids[0])
    return explorer, run_ids[0], run_dir


def test_list_figures_groups_by_directory(tmp_path):
    """Checks figures group by folder across the figure trees and non-figure files are skipped."""
    explorer, cube_id, _ = _with_figures(tmp_path)

    listing = explorer.list_figures(cube_id)
    assert listing["ok"]

    groups = {group["dir"]: group["files"] for group in listing["groups"]}
    assert groups == {
        "images/slc"                        : ["primary.png"],
        "figures/cube_slices/az0001_rg0002" : ["range_full.png"],
        "params/params_k2/images"           : ["walk.gif"],
    }


def test_figure_file_is_path_guarded(tmp_path):
    """Checks serving resolves only figure files inside the run's figure trees."""
    explorer, cube_id, run_dir = _with_figures(tmp_path)

    assert explorer.figure_file(cube_id, "images/slc/primary.png") == (run_dir / "images" / "slc" / "primary.png").resolve()
    assert explorer.figure_file(cube_id, "images/../data/dataset.json") is None
    assert explorer.figure_file(cube_id, "images/notes.txt") is None
    assert explorer.figure_file(cube_id, "data/tomogram_full.npy") is None
    assert explorer.figure_file("wrong", "images/slc/primary.png") is None


def test_list_figures_refuses_unloaded_cube(tmp_path):
    """Checks listing is refused for an id that is not the loaded cube."""
    explorer, _ = loaded_run(tmp_path)

    assert explorer.list_figures("wrong")["ok"] is False


def test_list_figures_empty_run(tmp_path):
    """Checks a run without figure trees lists zero groups."""
    explorer, cube_id = loaded_run(tmp_path)

    listing = explorer.list_figures(cube_id)
    assert listing["ok"] and listing["groups"] == []
