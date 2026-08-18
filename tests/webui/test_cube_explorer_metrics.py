"""Tests for the binary and image payloads of the cube explorer.

Covers the colormap whitelist behind the colour bar, the median-referenced DEM
grid blob, the radar-coordinate point cloud with its amplitude threshold and
subsampling cap, index clamping in point queries and the primary amplitude map.
"""

from __future__ import annotations

import numpy as np

from tests.webui.conftest         import N_AZ, N_ELEV, N_RG
from tests.webui.preproc_fixtures import loaded_run


def test_cbar_png_whitelist(tmp_path):
    """Checks the colour bar renders for a whitelisted colormap and refuses an unknown name."""
    explorer, _ = loaded_run(tmp_path)

    assert explorer.cbar_png("viridis")[:4] == b"\x89PNG"
    assert explorer.cbar_png("banana") is None


def test_primary_png_serves_for_the_loaded_cube_only(tmp_path):
    """Checks the primary amplitude map renders for the loaded id and refuses others."""
    explorer, cube_id = loaded_run(tmp_path)

    assert explorer.primary_png(cube_id)[:4] == b"\x89PNG"
    assert explorer.primary_png("wrong") is None


def test_dem_grid_bin_is_median_referenced(tmp_path):
    """Checks the DEM blob carries the grid extents, the median height and median-relative values."""
    explorer, cube_id = loaded_run(tmp_path, with_dem=True)

    blob = explorer.dem_grid_bin(cube_id)
    raw  = np.frombuffer(blob, dtype=np.float32)

    header, grid = raw[:4], raw[4:].reshape(N_AZ, N_RG)
    assert int(header[0]) == N_AZ and int(header[1]) == N_RG
    assert header[2] == 680.0

    finite = np.isfinite(grid)
    assert np.isnan(grid[2, 3])
    assert np.all(grid[finite] == 0.0)


def test_dem_grid_none_without_dem(tmp_path):
    """Checks a run without a DEM serves no grid blob."""
    explorer, cube_id = loaded_run(tmp_path)

    assert explorer.dem_grid_bin(cube_id) is None
    assert explorer.dem_grid_bin("wrong") is None


def test_points_bin_threshold_and_cap(tmp_path):
    """Checks the point blob honours the amplitude floor, records the total and subsamples to the cap."""
    sparse          = np.zeros((N_ELEV, N_AZ, N_RG), dtype=np.float32)
    sparse[2, 3, 4] = 2.0
    sparse[4, 5, 1] = 1.0

    explorer, cube_id = loaded_run(tmp_path, tomogram=sparse)

    blob = explorer.points_bin(cube_id, "full", amp_min=0.5, max_points=0)
    raw  = np.frombuffer(blob, dtype=np.float32)

    header, rows = raw[:4], raw[4:].reshape(-1, 4)
    assert int(header[0]) == 2 and int(header[1]) == 2
    assert {(int(r[0]), int(r[1])) for r in rows} == {(3, 4), (5, 1)}
    assert np.all((rows[:, 2] >= -10.0) & (rows[:, 2] <= 30.0))

    capped        = explorer.points_bin(cube_id, "full", amp_min=-1.0, max_points=10)
    capped_header = np.frombuffer(capped, dtype=np.float32)[:4]
    assert int(capped_header[0]) == 10
    assert int(capped_header[1]) == N_ELEV * N_AZ * N_RG


def test_points_bin_rejects_unknown_source_and_unloaded_cube(tmp_path):
    """Checks an unknown source and an unloaded cube both yield no blob."""
    explorer, cube_id = loaded_run(tmp_path)

    assert explorer.points_bin(cube_id, "banana", amp_min=0.0, max_points=0) is None
    assert explorer.points_bin("wrong", "full", amp_min=0.0, max_points=0) is None


def test_profiles_clip_out_of_range_indices(tmp_path):
    """Checks out-of-range pixel indices are clamped into the cube footprint."""
    explorer, cube_id = loaded_run(tmp_path)

    result = explorer.profiles(cube_id, az=99, rg=-1)
    assert result["ok"] and result["az"] == N_AZ - 1 and result["rg"] == 0
