"""Tests for the per-pixel metric layers of the cube explorer.

Covers layer discovery and colour ranges, overlay rendering including
thresholded and degenerate ranges, point queries with index clamping and NaN
handling, the colormap whitelist behind the colour bar, and the selective
metrics that recompute scores over the best-covered share of pixels.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

from cube_explorer import CubeExplorer

from tests.webui.conftest import N_AZ, loaded_cube


def _loaded_explorer(base: Path) -> tuple[CubeExplorer, str]:
    """Returns an explorer with a metric-carrying cube loaded, plus its cube id."""
    return loaded_cube(base, with_metrics=True)


def test_meta_lists_metric_layers(tmp_path):
    """Checks both saved metric maps are listed with finite, non-degenerate ranges and a display label."""
    explorer, _ = _loaded_explorer(tmp_path)

    layers = explorer.load_status()["cube"]["metric_maps"]
    keys   = {layer["key"] for layer in layers}

    assert keys == {"pixel_r2", "physics_valid_mask"}
    assert all(np.isfinite(layer["vmin"]) and np.isfinite(layer["vmax"]) and layer["vmax"] > layer["vmin"] for layer in layers)
    assert next(layer for layer in layers if layer["key"] == "pixel_r2")["label"] == "R2"


def test_metric_overlay_png(tmp_path):
    """Checks overlays render for the plain, thresholded and zero-width range cases."""
    explorer, cube_id = _loaded_explorer(tmp_path)

    png = explorer.metric_overlay_png(cube_id, "pixel_r2", vmin=0.0, vmax=1.0, keep_min=float("-inf"), keep_max=float("inf"), alpha=0.75)
    assert png and png[:4] == b"\x89PNG"

    thresholded = explorer.metric_overlay_png(cube_id, "pixel_r2", vmin=0.0, vmax=1.0, keep_min=0.5, keep_max=float("inf"), alpha=1.0)
    assert thresholded and thresholded[:4] == b"\x89PNG"

    degenerate = explorer.metric_overlay_png(cube_id, "pixel_r2", vmin=2.0, vmax=2.0, keep_min=float("-inf"), keep_max=float("inf"), alpha=0.5)
    assert degenerate and degenerate[:4] == b"\x89PNG"


def test_metric_overlay_rejects_unknown_key(tmp_path):
    """Checks unknown layers, misshaped cubes and unloaded cubes yield no overlay."""
    explorer, cube_id = _loaded_explorer(tmp_path)

    assert explorer.metric_overlay_png(cube_id, "banana", 0.0, 1.0, float("-inf"), float("inf"), 0.75) is None
    assert explorer.metric_overlay_png(cube_id, "misshaped", 0.0, 1.0, float("-inf"), float("inf"), 0.75) is None
    assert explorer.metric_overlay_png("wrong", "pixel_r2", 0.0, 1.0, float("-inf"), float("inf"), 0.75) is None


def test_metric_value_at(tmp_path):
    """Checks point queries return the stored value, None for NaN, clamped indices, and fail for unknown layers."""
    explorer, cube_id = _loaded_explorer(tmp_path)

    stamp = Path(cube_id)
    r2    = np.load(stamp / "cubes" / "pixel_r2.npy")

    result = explorer.metric_value_at(cube_id, "pixel_r2", az=2, rg=3)
    assert result["ok"] and result["value"] == float(r2[2, 3])

    nan_result = explorer.metric_value_at(cube_id, "pixel_r2", az=0, rg=0)
    assert nan_result["ok"] and nan_result["value"] is None

    clipped = explorer.metric_value_at(cube_id, "pixel_r2", az=99, rg=-1)
    assert clipped["ok"] and clipped["az"] == N_AZ - 1 and clipped["rg"] == 0

    assert not explorer.metric_value_at(cube_id, "banana", 0, 0)["ok"]


def test_cbar_png_whitelist(tmp_path):
    """Checks the colour bar renders for a whitelisted colormap and refuses an unknown name."""
    explorer, _ = _loaded_explorer(tmp_path)

    assert explorer.cbar_png("viridis")[:4] == b"\x89PNG"
    assert explorer.cbar_png("banana") is None


def test_selective_metrics_keep_low_confidence_share(tmp_path):
    """Checks reducing coverage keeps fewer pixels and improves the R2 of the retained ones."""
    explorer, cube_id = _loaded_explorer(tmp_path)

    full = explorer.selective_metrics(cube_id, "pixel_r2", coverage=1.0)
    half = explorer.selective_metrics(cube_id, "pixel_r2", coverage=0.5)

    assert full["ok"] and half["ok"]
    assert full["n_kept"]  == full["n_total"]
    assert half["n_kept"]  <  full["n_kept"]
    assert half["coverage"] <= 0.6

    r2_full = next(row for row in full["rows"] if row["key"] == "pixel_r2")
    r2_half = next(row for row in half["rows"] if row["key"] == "pixel_r2")

    assert full["direction"] == "high"
    assert r2_full["kept"] == r2_full["full"]
    assert r2_half["kept"] >= r2_half["full"]


def test_selective_metrics_reject_unknown_layer(tmp_path):
    """Checks an unknown layer and an unloaded cube both fail cleanly."""
    explorer, cube_id = _loaded_explorer(tmp_path)

    assert explorer.selective_metrics(cube_id, "banana", coverage=0.5)["ok"] is False
    assert explorer.selective_metrics("wrong", "pixel_r2", coverage=0.5)["ok"] is False
