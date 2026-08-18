"""Tests for saving cube slice figures from the cube explorer.

Covers the output directory naming and per-source, per-axis file set, index
clipping in normalized space, restoration of the global plot style, and the
guards for an unknown colour space or an unloaded cube.
"""

from __future__ import annotations

from pathlib import Path

from cube_explorer import CubeExplorer
from web_logger    import WebLogger

from tests.webui.conftest         import N_AZ
from tests.webui.preproc_fixtures import loaded_run, make_preproc_run


def test_save_slices_writes_paper_figures(tmp_path):
    """Checks slices save under a coordinate-named directory with one non-empty figure per source and axis."""
    explorer, cube_id = loaded_run(tmp_path)

    result = explorer.save_slices(cube_id, az=3, rg=2, space="physical")
    assert result["ok"], result

    out_dir = Path(result["dir"])
    assert out_dir == Path(cube_id) / "figures" / "cube_slices" / "az0003_rg0002"
    assert result["rel"] == "figures/cube_slices/az0003_rg0002"

    expected = {f"{axis}_full_physical.png" for axis in ("range", "azimuth")}
    assert set(result["files"]) == expected

    for name in expected:
        target = out_dir / name
        assert target.is_file() and target.stat().st_size > 0


def test_save_slices_normalized_space_clips_indices(tmp_path):
    """Checks out-of-range azimuth and range indices are clamped and the files are tagged normalized."""
    explorer, cube_id = loaded_run(tmp_path)

    result = explorer.save_slices(cube_id, az=999, rg=-5, space="normalized")
    assert result["ok"], result
    assert result["az"] == N_AZ - 1 and result["rg"] == 0
    assert all(name.endswith("_normalized.png") for name in result["files"])
    assert all((Path(result["dir"]) / name).is_file() for name in result["files"])


def test_save_slices_restores_figure_style(tmp_path):
    """Checks saving leaves the shared plot style back on report."""
    explorer, cube_id = loaded_run(tmp_path)

    from tools.reporting.plotting import PlotBase

    assert explorer.save_slices(cube_id, az=1, rg=1)["ok"]
    assert PlotBase.style == "report"


def test_save_slices_rejects_unknown_space(tmp_path):
    """Checks an unknown colour space is refused."""
    explorer, cube_id = loaded_run(tmp_path)

    result = explorer.save_slices(cube_id, az=0, rg=0, space="banana")
    assert not result["ok"]


def test_save_slices_requires_loaded_cube(tmp_path):
    """Checks saving from an explorer with nothing loaded fails."""
    run_dir  = make_preproc_run(tmp_path)
    explorer = CubeExplorer(WebLogger())
    explorer.roots.open(str(tmp_path))

    result = explorer.save_slices(str(run_dir), az=0, rg=0)
    assert not result["ok"]


def test_slice_png_serves_the_full_source(tmp_path):
    """Checks the interactive slice endpoint returns a PNG."""
    explorer, cube_id = loaded_run(tmp_path)

    png = explorer.slice_png(cube_id, "full", "range", az=0, rg=2)
    assert png is not None and png[:8] == b"\x89PNG\r\n\x1a\n"
