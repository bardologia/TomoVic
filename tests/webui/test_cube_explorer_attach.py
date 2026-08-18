"""Tests for attaching a second run to a loaded cube in the cube explorer.

Covers the predb and diff sources added on attach and removed on detach, the
symmetric diverging range and colormap override the diff gets, the guards
against self-attachment, unknown cubes and mismatched elevation axes, and the
slice, transect and figure-saving paths that must include the comparison sources.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

from cube_explorer import CubeExplorer

from tests.webui.conftest import N_AZ, N_ELEV, N_RG, load_cube, make_preproc, make_stamp, open_explorer


def _make_run(base: Path, preproc: Path, name: str, seed: int, x_min: float = -10.0) -> Path:
    """Writes one run stamp with random curve cubes.

    Args:
        base: Parent directory receiving the named run.
        preproc: Preprocessing run the stamp points back to.
        name: Run directory name.
        seed: Seed for the random cubes.
        x_min: Lowest elevation of the height axis in metres.

    Returns:
        Path of the created stamp directory.
    """
    return make_stamp(base / name, preproc, np.random.default_rng(seed), x_min=x_min)


def _loaded(base: Path) -> tuple[CubeExplorer, str, str]:
    """Builds two runs sharing a preprocessing tree and loads the first.

    Args:
        base: Parent directory for both runs.

    Returns:
        Tuple of the explorer, the loaded cube id and the second cube id.
    """
    preproc = make_preproc(base)
    stamp_a = _make_run(base, preproc, "run_a", seed=1)
    stamp_b = _make_run(base, preproc, "run_b", seed=2)

    explorer, _ = open_explorer(base, expected=2)
    cube_a      = str(stamp_a)

    load_cube(explorer, cube_a)

    return explorer, cube_a, str(stamp_b)


def test_attach_adds_predb_and_diff(tmp_path):
    """Checks attaching exposes predb and diff sources whose profiles and images match the cube difference."""
    explorer, cube_a, cube_b = _loaded(tmp_path)

    result = explorer.attach_second(cube_a, cube_b)
    assert result["ok"], result

    meta = result["cube"]
    assert meta["sources"] == ["pred", "predb", "diff", "gt"]
    assert meta["attached"]["id"] == cube_b
    assert meta["attached"]["run"] == "run_b"

    pred_a = np.load(Path(cube_a) / "cubes" / "pred_curves.npy")
    pred_b = np.load(Path(cube_b) / "cubes" / "pred_curves.npy")

    profiles = explorer.profiles(cube_a, az=2, rg=3)
    assert set(profiles["sources"]) == {"pred", "predb", "diff", "gt"}

    expected_diff = (pred_a - pred_b)[:, 2, 3]
    order = np.argsort(np.linspace(-10.0, 30.0, N_ELEV))
    assert np.allclose(profiles["sources"]["diff"]["values"], expected_diff[order])

    assert explorer.slice_png(cube_a, "predb", "range", az=0, rg=0)[:4] == b"\x89PNG"
    assert explorer.slice_png(cube_a, "diff",  "range", az=0, rg=0)[:4] == b"\x89PNG"
    assert explorer.plane_png(cube_a, "diff", frac=0.5, space="normalized")[:4] == b"\x89PNG"


def test_diff_range_is_symmetric(tmp_path):
    """Checks the diff source is marked diverging with a colour range centred on zero."""
    explorer, cube_a, cube_b = _loaded(tmp_path)
    explorer.attach_second(cube_a, cube_b)

    entry = explorer._entry(cube_a, "diff")
    assert entry["diverging"] is True
    assert entry["vmin"] == -entry["vmax"]
    assert entry["vmax"] > 0


def test_detach_removes_comparison(tmp_path):
    """Checks detaching restores the original source list and makes predb slices unavailable."""
    explorer, cube_a, cube_b = _loaded(tmp_path)
    explorer.attach_second(cube_a, cube_b)

    result = explorer.detach_second(cube_a)
    assert result["ok"]
    assert result["cube"]["sources"] == ["pred", "gt"]
    assert result["cube"]["attached"] is None
    assert explorer.slice_png(cube_a, "predb", "range", az=0, rg=0) is None


def test_attach_rejects_self_and_unknown(tmp_path):
    """Checks attaching a cube to itself, to an unknown path, or from an unloaded cube fails."""
    explorer, cube_a, _ = _loaded(tmp_path)

    assert not explorer.attach_second(cube_a, cube_a)["ok"]
    assert not explorer.attach_second(cube_a, str(tmp_path / "nowhere"))["ok"]
    assert not explorer.attach_second(str(tmp_path / "other"), cube_a)["ok"]


def test_attach_rejects_mismatched_axis(tmp_path):
    """Checks attaching a run with a different elevation axis is refused with an explanatory error."""
    preproc = make_preproc(tmp_path)
    stamp_a = _make_run(tmp_path, preproc, "run_a", seed=1)
    stamp_c = _make_run(tmp_path, preproc, "run_c", seed=3, x_min=-99.0)

    explorer, _ = open_explorer(tmp_path, expected=2)
    load_cube(explorer, str(stamp_a))

    result = explorer.attach_second(str(stamp_a), str(stamp_c))
    assert not result["ok"] and "elevation axis" in result["error"]


def test_ssim_covers_predb(tmp_path):
    """Checks slice SSIM scores the attached prediction but not the signed difference."""
    explorer, cube_a, cube_b = _loaded(tmp_path)
    explorer.attach_second(cube_a, cube_b)

    result = explorer.slice_ssim(cube_a, az=2, rg=2)
    assert result["ok"]
    assert "predb" in result["range"]
    assert "diff" not in result["range"]


def test_transect_png_samples_line(tmp_path):
    """Checks transects render in both colour spaces and return None for unknown sources or cubes."""
    explorer, cube_a, _ = _loaded(tmp_path)

    png = explorer.transect_png(cube_a, "pred", az0=0, rg0=0, az1=N_AZ - 1, rg1=N_RG - 1)
    assert png and png[:4] == b"\x89PNG"

    normalized = explorer.transect_png(cube_a, "pred", az0=2, rg0=1, az1=2, rg1=4, space="normalized")
    assert normalized and normalized[:4] == b"\x89PNG"

    assert explorer.transect_png(cube_a, "banana", 0, 0, 1, 1) is None
    assert explorer.transect_png("wrong", "pred", 0, 0, 1, 1) is None


def test_transect_cut_geometry(tmp_path):
    """Checks the transect cut spans the longer axis, carries the full height range in metres and starts at the cube corner."""
    explorer, cube_a, _ = _loaded(tmp_path)

    entry = explorer._entry(cube_a, "pred")
    data, heights, vmin, vmax = explorer._transect_cut(entry, 0, 0, N_AZ - 1, N_RG - 1, "physical")

    assert data.shape == (N_ELEV, max(N_AZ, N_RG))
    assert heights[0] == -10.0 and heights[-1] == 30.0
    assert vmin == entry["vmin"] and vmax == entry["vmax"]

    cube = entry["cube"]
    assert np.allclose(data[:, 0], cube[:, 0, 0])


def test_save_transect_writes_figures(tmp_path):
    """Checks saving a transect writes one non-empty figure per source under a coordinate-named directory."""
    explorer, cube_a, _ = _loaded(tmp_path)

    result = explorer.save_transect(cube_a, az0=0, rg0=0, az1=4, rg1=5)
    assert result["ok"], result

    out_dir = Path(result["dir"])
    assert result["rel"] == "figures/cube_transects/az0000_rg0000_to_az0004_rg0005"

    expected = {f"transect_{source}_physical.png" for source in ("pred", "gt")}
    assert set(result["files"]) == expected
    assert all((out_dir / name).stat().st_size > 0 for name in expected)


def test_save_transect_rejects_bad_space_and_unloaded(tmp_path):
    """Checks an unknown colour space and an unloaded cube are both refused."""
    explorer, cube_a, _ = _loaded(tmp_path)

    assert not explorer.save_transect(cube_a, 0, 0, 1, 1, space="banana")["ok"]
    assert not explorer.save_transect(str(tmp_path / "nowhere"), 0, 0, 1, 1)["ok"]


def test_save_slices_includes_comparison_sources(tmp_path):
    """Checks saved slices cover both axes for every source including predb and diff."""
    explorer, cube_a, cube_b = _loaded(tmp_path)
    explorer.attach_second(cube_a, cube_b)

    result = explorer.save_slices(cube_a, az=1, rg=1)
    assert result["ok"]

    expected = {f"{axis}_{source}_physical.png" for source in ("pred", "predb", "diff", "gt") for axis in ("range", "azimuth")}
    assert set(result["files"]) == expected


def test_cmap_selection_and_diverging_override(tmp_path):
    """Checks unknown colormaps fall back to jet, diverging sources force coolwarm, and renders honour the request."""
    explorer, cube_a, cube_b = _loaded(tmp_path)
    explorer.attach_second(cube_a, cube_b)

    pred = explorer._entry(cube_a, "pred")
    diff = explorer._entry(cube_a, "diff")

    assert explorer._entry_cmap(pred, "viridis") == "viridis"
    assert explorer._entry_cmap(pred, "banana") == "jet"
    assert explorer._entry_cmap(diff, "viridis") == "coolwarm"

    assert explorer.slice_png(cube_a, "pred", "range", az=0, rg=0, cmap="viridis")[:4] == b"\x89PNG"
    assert explorer.plane_png(cube_a, "pred", frac=0.5, cmap="gray")[:4] == b"\x89PNG"
    assert explorer.transect_png(cube_a, "pred", 0, 0, 2, 2, cmap="inferno")[:4] == b"\x89PNG"
