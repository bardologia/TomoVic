"""Tests for opening preprocessing runs in the cube explorer.

Covers run resolution against the catalogued roots and the ``data/dataset.json``
marker, the metadata a finished load reports, elevation profiles, transect
rendering and figure saving, the colormap selection rules, and the parametrized
tomogram loaded from a Gaussian parameter run: tag listing, source flipping,
lazy reconstruction, the per-pixel slot readout and error handling.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

from cube_explorer import CubeExplorer
from web_logger    import WebLogger

from tests.webui.conftest         import N_AZ, N_ELEV, N_RG, load_cube
from tests.webui.preproc_fixtures import HEIGHT_RANGE, loaded_param_run, loaded_run, make_param_run, make_preproc_run, open_runs


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


def _two_slot_parameters() -> np.ndarray:
    """Returns a two-slot parameter cube with one inactive slot at pixel (1, 2)."""
    parameters = np.zeros((6, N_AZ, N_RG), dtype=np.float32)

    parameters[0] = 0.8
    parameters[1] = 12.0
    parameters[2] = 3.0
    parameters[3] = 0.5
    parameters[4] = -2.0
    parameters[5] = 2.0

    parameters[3, 1, 2] = 0.0
    return parameters


def test_param_runs_listing(tmp_path):
    """Checks tag listing is empty without params, sorted with them, and refuses unknown ids."""
    explorer, cube_id = loaded_run(tmp_path)
    assert explorer.param_runs(cube_id) == {"ok": True, "tags": []}

    make_param_run(Path(cube_id), "params_b", k=2)
    make_param_run(Path(cube_id), "params_a", k=3)
    (Path(cube_id) / "params" / "logs").mkdir()

    assert explorer.param_runs(cube_id) == {"ok": True, "tags": ["params_a", "params_b"]}
    assert not explorer.param_runs(str(tmp_path / "nowhere"))["ok"]


def test_load_with_param_tag_flips_sources(tmp_path):
    """Checks loading with a parameter run adds the param source and its metadata payload."""
    explorer, cube_id = loaded_param_run(tmp_path, tag="params_k2", k=2)
    meta              = explorer.load_status()["cube"]

    assert meta["sources"] == ["full", "param"]
    assert meta["param"]["tag"] == "params_k2"
    assert meta["param"]["n_gaussians"] == 2 and meta["param"]["k_max"] == 2
    assert set(meta["param"]["fields"]) == {"amplitude", "mean", "sigma"}
    assert meta["n_elev"]["param"] == N_ELEV

    vmin, vmax = meta["intensity"]["param"]
    assert vmax > vmin >= 0.0


def test_load_without_param_tag_keeps_full_only(tmp_path):
    """Checks a plain load ignores stored parameter runs and refuses the param source."""
    run_dir = make_preproc_run(tmp_path)
    make_param_run(run_dir, "params_k2")

    explorer, run_ids = open_runs(tmp_path, expected=1)
    load_cube(explorer, run_ids[0])

    meta = explorer.load_status()["cube"]
    assert meta["sources"] == ["full"] and meta["param"] is None
    assert explorer.slice_png(run_ids[0], "param", "range", az=0, rg=0) is None
    assert not explorer.params_at(run_ids[0], az=0, rg=0)["ok"]


def test_unknown_param_tag_is_refused(tmp_path):
    """Checks a load with a tag the run does not hold fails loudly and names the tag."""
    run_dir = make_preproc_run(tmp_path)
    make_param_run(run_dir, "params_k2")

    explorer, run_ids = open_runs(tmp_path, expected=1)
    result            = explorer.start_load(run_ids[0], param_tag="banana")

    assert not result["ok"] and "banana" in result["error"]


def test_param_profile_matches_analytic_mixture(tmp_path):
    """Checks the reconstructed profile at a pixel equals the analytic Gaussian sum of its parameters."""
    parameters        = _two_slot_parameters()
    explorer, cube_id = loaded_param_run(tmp_path, tag="params_k2", parameters=parameters)

    result = explorer.profiles(cube_id, az=2, rg=3)
    assert result["ok"] and set(result["sources"]) == {"full", "param"}

    heights = np.asarray(result["sources"]["param"]["heights"])
    assert np.allclose(heights, np.linspace(HEIGHT_RANGE[0], HEIGHT_RANGE[1], N_ELEV))
    assert result["sources"]["param"]["heights"] == result["sources"]["full"]["heights"]

    pixel    = parameters[:, 2, 3]
    analytic = sum(pixel[3 * k] * np.exp(-((heights - pixel[3 * k + 1]) ** 2) / (2.0 * pixel[3 * k + 2] ** 2)) for k in range(2))
    assert np.allclose(result["sources"]["param"]["values"], analytic, atol=1e-6)


def test_params_at_orders_slots_by_mean(tmp_path):
    """Checks the per-pixel readout returns every slot ordered by mean, inactive ones included."""
    parameters        = _two_slot_parameters()
    explorer, cube_id = loaded_param_run(tmp_path, tag="params_k2", parameters=parameters)

    result = explorer.params_at(cube_id, az=1, rg=2)
    assert result["ok"] and result["tag"] == "params_k2"
    assert result["az"] == 1 and result["rg"] == 2

    assert [slot["mean"] for slot in result["slots"]] == [-2.0, 12.0]
    assert result["slots"][0] == {"amplitude": 0.0, "mean": -2.0, "sigma": 2.0}
    assert np.allclose([result["slots"][1][key] for key in ("amplitude", "mean", "sigma")], [0.8, 12.0, 3.0])

    clipped = explorer.params_at(cube_id, az=999, rg=-5)
    assert clipped["ok"] and clipped["az"] == N_AZ - 1 and clipped["rg"] == 0


def test_param_slice_plane_and_transect_render(tmp_path):
    """Checks the parametrized tomogram renders as slices, planes and transects in both spaces."""
    explorer, cube_id = loaded_param_run(tmp_path)

    assert explorer.slice_png(cube_id, "param", "range", az=1, rg=2)[:4] == b"\x89PNG"
    assert explorer.slice_png(cube_id, "param", "azimuth", az=1, rg=2, space="normalized")[:4] == b"\x89PNG"
    assert explorer.plane_png(cube_id, "param", frac=0.5)[:4] == b"\x89PNG"
    assert explorer.transect_png(cube_id, "param", 0, 0, N_AZ - 1, N_RG - 1)[:4] == b"\x89PNG"


def test_save_slices_include_the_param_source(tmp_path):
    """Checks figure saving writes both the raw and the parametrized cuts once a parameter run is loaded."""
    explorer, cube_id = loaded_param_run(tmp_path)

    result = explorer.save_slices(cube_id, az=1, rg=1)
    assert result["ok"], result

    expected = {"range_full_physical.png", "azimuth_full_physical.png", "range_param_physical.png", "azimuth_param_physical.png"}
    assert set(result["files"]) == expected
