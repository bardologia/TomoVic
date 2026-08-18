"""Tests for the globe view geometry the cube explorer derives from geocoded runs.

Covers the globe metadata (bounding box, anchor, DEM residual, flight lines and
beam segment) built from the track parameters, the graceful path when a stamp
records no track selection or no geocoding at all, and the binary scatterer
point blob served to Cesium, including DEM gap removal, elevation ordering,
amplitude thresholding and the rejection of non-Gaussian sources.
"""

from __future__ import annotations

import json

import numpy as np

from tests.webui.conftest import N_AZ, N_RG, N_SLOTS, load_cube, loaded_cube, make_cube_run, open_explorer


def globe_blob(explorer, cube_id, source="pred", amp_min=0.0, max_points=0):
    """Fetches and unpacks the binary globe point blob.

    Args:
        explorer: Explorer holding the loaded cube.
        cube_id: Identifier of the loaded cube.
        source: Parameter source to render, e.g. ``"pred"`` or ``"reduced"``.
        amp_min: Minimum normalised amplitude a point must carry to be kept.
        max_points: Cap on returned points; zero means no cap.

    Returns:
        Tuple of the four-float header and a row array of shape (points, 5),
        holding an ECEF offset in metres per row plus normalised elevation and
        amplitude, or None when the cube has no globe metadata.
    """
    blob = explorer.globe_points_bin(cube_id, source, amp_min=amp_min, max_points=max_points)
    if blob is None:
        return None

    raw = np.frombuffer(blob, dtype=np.float32)
    return raw[:4], raw[4:].reshape(-1, 5)


def test_globe_meta_present_with_geo(tmp_path):
    """Checks a geocoded run yields a globe with a sub-decimetre DEM residual, a sane bbox and an Earth-radius anchor."""
    explorer, cube_id = loaded_cube(tmp_path, with_params=("pred", "gt"), with_geo=True)
    globe             = explorer.load_status()["cube"]["globe"]

    assert globe is not None
    assert globe["residual_rms_m"] < 0.1
    assert globe["base_height"] == 680.0

    west, south, east, north = globe["bbox"]
    assert west < east and south < north
    assert 12.5 < west < 12.8 and 47.7 < south < 48.0

    anchor = np.array(globe["anchor_ecef"])
    assert 6.3e6 < np.linalg.norm(anchor) < 6.5e6


def test_globe_meta_carries_only_the_run_tracks(tmp_path):
    """Checks flight lines are drawn only for the tracks the stamp selected, at the platform altitude."""
    explorer, cube_id = loaded_cube(tmp_path, with_params=("pred",), with_geo=True)
    globe             = explorer.load_status()["cube"]["globe"]
    tracks            = globe["tracks"]

    assert tracks["labels"] == ["T01", "T02"]
    assert "T03" not in tracks["labels"]
    assert len(tracks["lines"]) == 2
    assert tracks["reference"] == "T01"
    assert tracks["h0"] == [3700.0, 3700.0]

    up = np.array(globe["anchor_ecef"])
    up = up / np.linalg.norm(up)

    for line in tracks["lines"]:
        points = np.array(line)
        assert points.shape == (17, 3)
        assert np.all(np.isfinite(points))
        assert np.all(np.abs(points @ up - 3020.0) < 5.0)


def test_globe_beam_segment_matches_slant_geometry(tmp_path):
    """Checks the beam apex, near and far points reproduce the recorded slant ranges and look angles."""
    explorer, cube_id = loaded_cube(tmp_path, with_params=("pred",), with_geo=True)
    globe             = explorer.load_status()["cube"]["globe"]
    beam              = globe["tracks"]["beam"]

    assert beam["slant_near_m"] == 3300.0
    assert abs(beam["slant_far_m"] - (3300.0 + (N_RG - 1) * 0.6)) < 1e-6
    assert 0.0 < beam["look_near_deg"] < beam["look_far_deg"] < 90.0

    up   = np.array(globe["anchor_ecef"])
    up   = up / np.linalg.norm(up)
    apex = np.array(beam["apex"])
    near = np.array(beam["near"])
    far  = np.array(beam["far"])

    assert abs(float(apex @ up) - 3020.0) < 5.0
    assert abs(float(near @ up)) < 5.0
    assert abs(float(far @ up)) < 5.0

    assert abs(float(np.linalg.norm(apex - near)) - beam["slant_near_m"]) < 5.0
    assert abs(float(np.linalg.norm(apex - far)) - beam["slant_far_m"]) < 5.0


def test_a_stamp_without_a_track_selection_still_loads(tmp_path):
    """Checks a stamp with no track record still builds a globe, with an explanatory note instead of lines."""
    stamp   = make_cube_run(tmp_path, with_params=("pred",), with_geo=True)
    metrics = json.loads((stamp / "metrics.json").read_text(encoding="utf-8"))

    metrics.pop("tracks")
    (stamp / "metrics.json").write_text(json.dumps(metrics), encoding="utf-8")

    explorer, cube_ids = open_explorer(tmp_path, expected=1)
    status             = load_cube(explorer, cube_ids[0])
    globe              = status["cube"]["globe"]

    assert status["cube"]["params"]["sources"] == ["pred"]
    assert globe is not None
    assert globe["tracks"] is None
    assert "no track selection" in globe["tracks_note"]
    assert globe["residual_rms_m"] < 0.1


def test_globe_meta_none_without_geo(tmp_path):
    """Checks a run without geocoding exposes no globe and serves no point blob."""
    explorer, cube_id = loaded_cube(tmp_path, with_params=("pred",), with_spacing=True)

    assert explorer.load_status()["cube"]["globe"] is None
    assert explorer.globe_points_bin(cube_id, "pred", amp_min=0.0, max_points=0) is None


def test_globe_points_drop_nan_dem_pixels(tmp_path):
    """Checks pixels with a NaN DEM height are counted in the header but excluded from the returned points."""
    explorer, cube_id = loaded_cube(tmp_path, with_params=("pred",), with_geo=True)
    header, rows      = globe_blob(explorer, cube_id)

    total = N_SLOTS * N_AZ * N_RG
    assert int(header[1]) == total
    assert rows.shape[0] == total - N_SLOTS

    assert np.all(np.isfinite(rows))
    assert float(np.max(np.abs(rows[:, :3]))) < 100.0


def test_globe_points_offsets_follow_elevation(tmp_path):
    """Checks normalised elevation and amplitude stay in the unit interval and the vertical offset tracks the elevation."""
    explorer, cube_id = loaded_cube(tmp_path, with_params=("pred",), with_geo=True)
    globe             = explorer.load_status()["cube"]["globe"]
    _, rows           = globe_blob(explorer, cube_id)

    mus  = rows[:, 3]
    amps = rows[:, 4]
    assert np.all((mus >= 0.0) & (mus < 1.0))
    assert np.all((amps >= 0.0) & (amps < 1.0))

    up      = np.array(globe["anchor_ecef"])
    up      = up / np.linalg.norm(up)
    up_comp = rows[:, :3] @ up.astype(np.float32)

    assert float(np.corrcoef(mus, up_comp)[0, 1]) > 0.9


def test_globe_points_reduced_source(tmp_path):
    """Checks the reduced source returns only the scatterers above the amplitude threshold."""
    explorer, cube_id = loaded_cube(tmp_path, with_params=("pred",), with_reduced=True, with_geo=True)
    header, rows      = globe_blob(explorer, cube_id, source="reduced", amp_min=0.5)

    assert int(header[0]) == 2
    assert rows.shape[0] == 2


def test_globe_points_reject_bin_axis_and_unknown(tmp_path):
    """Checks the full curve cube, an unknown source and an unloaded cube all yield no blob."""
    explorer, cube_id = loaded_cube(tmp_path, with_params=("pred",), with_geo=True)

    assert explorer.globe_points_bin(cube_id, "full", amp_min=0.0, max_points=0) is None
    assert explorer.globe_points_bin(cube_id, "banana", amp_min=0.0, max_points=0) is None
    assert explorer.globe_points_bin("wrong", "pred", amp_min=0.0, max_points=0) is None
