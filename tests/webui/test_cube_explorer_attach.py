"""Tests for opening preprocessing runs in the cube explorer.

Covers run resolution against the catalogued roots and the ``data/dataset.json``
marker, the metadata a finished load reports, elevation profiles, transect
rendering and figure saving, and the colormap selection rules.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

from cube_explorer import CubeExplorer
from web_logger    import WebLogger

from tests.webui.conftest         import N_AZ, N_ELEV, N_RG, load_cube
from tests.webui.preproc_fixtures import loaded_run, make_preproc_run, open_runs


def test_load_reports_run_metadata(tmp_path):
    """Checks a loaded run exposes the full source, its extents, the metre axis and a sane intensity range."""
    explorer, cube_id = loaded_run(tmp_path)
    meta              = explorer.load_status()["cube"]

    assert meta["sources"] == ["full"]
    assert meta["n_az"] == N_AZ and meta["n_rg"] == N_RG
    assert meta["n_elev"] == {"full": N_ELEV}
    assert meta["x_min"] == -10.0 and meta["x_max"] == 30.0

    vmin, vmax = meta["intensity"]["full"]
    assert vmax > vmin


def test_open_rejects_unknown_and_uncatalogued_runs(tmp_path):
    """Checks paths without a dataset layout or outside the catalogued roots are refused."""
    make_preproc_run(tmp_path / "runs")
    foreign = make_preproc_run(tmp_path / "foreign")

    explorer, run_ids = open_runs(tmp_path / "runs", expected=1)

    assert not explorer.start_load(str(foreign))["ok"]
    assert not explorer.start_load(str(tmp_path / "runs" / "nowhere"))["ok"]
    assert not explorer.start_load("")["ok"]
    assert explorer.start_load(run_ids[0])["ok"]


def test_load_fails_loudly_without_tomogram(tmp_path):
    """Checks a run whose tomogram file is missing reports an error status instead of loading."""
    run_dir = make_preproc_run(tmp_path)
    (run_dir / "data" / "tomogram_full.npy").unlink()

    explorer, run_ids = open_runs(tmp_path, expected=1)
    assert explorer.start_load(run_ids[0])["ok"]

    import time
    deadline = time.time() + 30.0
    while explorer.load_status()["state"] == "loading" and time.time() < deadline:
        time.sleep(0.05)

    status = explorer.load_status()
    assert status["state"] == "error"
    assert "tomogram_full" in status["error"]


def test_profiles_follow_the_stored_cube(tmp_path):
    """Checks the elevation profile at a pixel matches the stored tomogram along the ascending axis."""
    explorer, cube_id = loaded_run(tmp_path)

    cube   = np.load(Path(cube_id) / "data" / "tomogram_full.npy")
    result = explorer.profiles(cube_id, az=2, rg=3)

    assert result["ok"]
    assert set(result["sources"]) == {"full"}

    profile = result["sources"]["full"]
    assert profile["heights"][0] == -10.0 and profile["heights"][-1] == 30.0
    assert np.allclose(profile["values"], cube[:, 2, 3])


def test_transect_png_samples_line(tmp_path):
    """Checks transects render in both colour spaces and return None for unknown sources or cubes."""
    explorer, cube_id = loaded_run(tmp_path)

    png = explorer.transect_png(cube_id, "full", az0=0, rg0=0, az1=N_AZ - 1, rg1=N_RG - 1)
    assert png and png[:4] == b"\x89PNG"

    normalized = explorer.transect_png(cube_id, "full", az0=2, rg0=1, az1=2, rg1=4, space="normalized")
    assert normalized and normalized[:4] == b"\x89PNG"

    assert explorer.transect_png(cube_id, "banana", 0, 0, 1, 1) is None
    assert explorer.transect_png("wrong", "full", 0, 0, 1, 1) is None


def test_transect_cut_geometry(tmp_path):
    """Checks the transect cut spans the longer axis, carries the full height range in metres and starts at the cube corner."""
    explorer, cube_id = loaded_run(tmp_path)

    entry = explorer._entry(cube_id, "full")
    data, heights, vmin, vmax = explorer._transect_cut(entry, 0, 0, N_AZ - 1, N_RG - 1, "physical")

    assert data.shape == (N_ELEV, max(N_AZ, N_RG))
    assert heights[0] == -10.0 and heights[-1] == 30.0
    assert vmin == entry["vmin"] and vmax == entry["vmax"]

    cube = entry["cube"]
    assert np.allclose(data[:, 0], cube[:, 0, 0])


def test_save_transect_writes_figures(tmp_path):
    """Checks saving a transect writes one non-empty figure per source under a coordinate-named directory."""
    explorer, cube_id = loaded_run(tmp_path)

    result = explorer.save_transect(cube_id, az0=0, rg0=0, az1=4, rg1=5)
    assert result["ok"], result

    out_dir = Path(result["dir"])
    assert out_dir == Path(cube_id) / "figures" / "cube_transects" / "az0000_rg0000_to_az0004_rg0005"
    assert result["rel"] == "figures/cube_transects/az0000_rg0000_to_az0004_rg0005"

    expected = {"transect_full_physical.png"}
    assert set(result["files"]) == expected
    assert all((out_dir / name).stat().st_size > 0 for name in expected)


def test_save_transect_rejects_bad_space_and_unloaded(tmp_path):
    """Checks an unknown colour space and an unloaded cube are both refused."""
    explorer, cube_id = loaded_run(tmp_path)

    assert not explorer.save_transect(cube_id, 0, 0, 1, 1, space="banana")["ok"]
    assert not explorer.save_transect(str(tmp_path / "nowhere"), 0, 0, 1, 1)["ok"]


def test_reload_of_the_same_run_is_a_no_op(tmp_path):
    """Checks asking to load the already loaded run succeeds without restarting the load."""
    explorer, cube_id = loaded_run(tmp_path)

    assert explorer.start_load(cube_id)["ok"]
    assert explorer.load_status()["state"] == "ready"


def test_cmap_selection(tmp_path):
    """Checks unknown colormaps fall back to jet and renders honour the request."""
    explorer, cube_id = loaded_run(tmp_path)

    entry = explorer._entry(cube_id, "full")
    assert explorer._entry_cmap(entry, "viridis") == "viridis"
    assert explorer._entry_cmap(entry, "banana") == "jet"

    assert explorer.slice_png(cube_id, "full", "range", az=0, rg=0, cmap="viridis")[:4] == b"\x89PNG"
    assert explorer.plane_png(cube_id, "full", frac=0.5, cmap="gray")[:4] == b"\x89PNG"
    assert explorer.transect_png(cube_id, "full", 0, 0, 2, 2, cmap="inferno")[:4] == b"\x89PNG"


def test_second_explorer_requires_its_own_load(tmp_path):
    """Checks saving from an explorer with nothing loaded fails even for a known run."""
    run_dir = make_preproc_run(tmp_path)

    explorer = CubeExplorer(WebLogger())
    explorer.roots.open(str(tmp_path))

    assert not explorer.save_slices(str(run_dir), az=0, rg=0)["ok"]

    load_cube(explorer, str(run_dir))
    assert explorer.save_slices(str(run_dir), az=0, rg=0)["ok"]
