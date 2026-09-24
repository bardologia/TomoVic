"""Tests for the globe view geometry the cube explorer derives from geocoded runs.

Covers the globe metadata (bounding box, anchor, DEM residual, flight lines and
beam segment) built from the track parameters, the graceful path when a run
records no pass labels or no geocoding at all, and the binary scatterer point
blob served to Cesium, including DEM gap removal, elevation ordering, amplitude
thresholding and the rejection of unknown sources.
"""

from __future__ import annotations

import numpy as np

from tests.webui.conftest         import N_AZ, N_ELEV, N_RG, load_cube
from tests.webui.preproc_fixtures import HEIGHT_RANGE, loaded_param_run, loaded_run, make_preproc_run, open_runs


def globe_blob(explorer, cube_id, source="full", amp_min=0.0, max_points=0):
    """Fetches and unpacks the binary globe point blob.

    Args:
        explorer: Explorer holding the loaded cube.
        cube_id: Identifier of the loaded cube.
        source: Curve source to render.
        amp_min: Minimum amplitude a point must carry to be kept.
        max_points: Cap on returned points; zero means no cap.

    Returns:
        Tuple of the four-float header and a row array of shape (points, 5),
        holding an ECEF offset in metres per row plus elevation in metres and
        amplitude, or None when the cube has no globe metadata.
    """
    blob = explorer.globe_points_bin(cube_id, source, amp_min=amp_min, max_points=max_points)
    if blob is None:
        return None

    raw = np.frombuffer(blob, dtype=np.float32)
    return raw[:4], raw[4:].reshape(-1, 5)


def test_globe_meta_present_with_geo(tmp_path):
    """Checks a geocoded run yields a globe with a sub-decimetre DEM residual, a sane bbox and an Earth-radius anchor."""
    explorer, cube_id = loaded_run(tmp_path, with_geo=True)
    globe             = explorer.load_status()["cube"]["globe"]

    assert globe is not None
    assert globe["residual_rms_m"] < 0.1
    assert globe["base_height"] == 680.0

    west, south, east, north = globe["bbox"]
    assert west < east and south < north
    assert 12.5 < west < 12.8 and 47.7 < south < 48.0

    anchor = np.array(globe["anchor_ecef"])
    assert 6.3e6 < np.linalg.norm(anchor) < 6.5e6


def test_globe_meta_carries_only_the_run_passes(tmp_path):
    """Checks flight lines are drawn only for the passes the run recorded, at the platform altitude."""
    explorer, cube_id = loaded_run(tmp_path, with_geo=True)
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
    explorer, cube_id = loaded_run(tmp_path, with_geo=True)
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


def test_a_run_without_pass_labels_still_loads(tmp_path):
    """Checks a run without pass labels still builds a globe, with an explanatory note instead of lines."""
    explorer, cube_id = loaded_run(tmp_path, with_geo=True, pass_labels=None)
    globe             = explorer.load_status()["cube"]["globe"]

    assert globe is not None
    assert globe["tracks"] is None
    assert "no pass labels" in globe["tracks_note"]
    assert globe["residual_rms_m"] < 0.1


def test_globe_meta_none_without_geo(tmp_path):
    """Checks a run without geocoding exposes no globe and serves no point blob."""
    explorer, cube_id = loaded_run(tmp_path, with_spacing=True)

    assert explorer.load_status()["cube"]["globe"] is None
    assert explorer.globe_points_bin(cube_id, "full", amp_min=0.0, max_points=0) is None


def test_globe_points_drop_nan_dem_pixels(tmp_path):
    """Checks pixels with a NaN DEM height are counted in the header but excluded from the returned points."""
    explorer, cube_id = loaded_run(tmp_path, with_geo=True)
    header, rows      = globe_blob(explorer, cube_id)

    total = N_ELEV * N_AZ * N_RG
    assert int(header[1]) == total
    assert rows.shape[0] == total - N_ELEV

    assert np.all(np.isfinite(rows))
    assert float(np.max(np.abs(rows[:, :3]))) < 100.0


def test_globe_points_offsets_follow_elevation(tmp_path):
    """Checks elevations stay inside the height range and the vertical offset tracks the elevation."""
    explorer, cube_id = loaded_run(tmp_path, with_geo=True)
    globe             = explorer.load_status()["cube"]["globe"]
    _, rows           = globe_blob(explorer, cube_id)

    elevations = rows[:, 3]
    amplitudes = rows[:, 4]
    assert np.all((elevations >= HEIGHT_RANGE[0]) & (elevations <= HEIGHT_RANGE[1]))
    assert np.all((amplitudes >= 0.0) & (amplitudes < 1.0))

    up      = np.array(globe["anchor_ecef"])
    up      = up / np.linalg.norm(up)
    up_comp = rows[:, :3] @ up.astype(np.float32)

    assert float(np.corrcoef(elevations, up_comp)[0, 1]) > 0.9


def test_globe_points_honour_the_amplitude_threshold(tmp_path):
    """Checks only the voxels above the amplitude floor are emitted."""
    sparse           = np.zeros((N_ELEV, N_AZ, N_RG), dtype=np.float32)
    sparse[2, 3, 4]  = 2.0
    sparse[4, 5, 1]  = 1.0

    explorer, cube_id = loaded_run(tmp_path, with_geo=True, tomogram=sparse)
    header, rows      = globe_blob(explorer, cube_id, amp_min=0.5)

    assert int(header[0]) == 2
    assert rows.shape[0] == 2


def test_globe_points_serve_the_parametrized_tomogram(tmp_path):
    """Checks the geocoded point cloud also renders from the reconstructed param source."""
    explorer, cube_id = loaded_param_run(tmp_path, with_geo=True)
    header, rows      = globe_blob(explorer, cube_id, source="param", max_points=100)

    assert int(header[0]) > 0
    assert np.all(np.isfinite(rows))
    assert np.all((rows[:, 3] >= HEIGHT_RANGE[0]) & (rows[:, 3] <= HEIGHT_RANGE[1]))


def test_globe_points_reject_unknown_source_and_unloaded_cube(tmp_path):
    """Checks an unknown source and an unloaded cube both yield no blob."""
    explorer, cube_id = loaded_run(tmp_path, with_geo=True)

    assert explorer.globe_points_bin(cube_id, "banana", amp_min=0.0, max_points=0) is None
    assert explorer.globe_points_bin("wrong", "full", amp_min=0.0, max_points=0) is None


def test_a_repeated_globe_request_is_served_from_the_blob_cache(tmp_path):
    """Checks a second identical point request returns the very object the first one cached."""
    explorer, cube_id = loaded_run(tmp_path, with_geo=True)

    first  = explorer.globe_points_bin(cube_id, "full", amp_min=0.0, max_points=100)
    cached = explorer.globe_blobs.get(f"{cube_id}|full|{0.0!r}|100")

    assert first is cached
    assert explorer.globe_points_bin(cube_id, "full", amp_min=0.0, max_points=100) is first


def test_the_warmed_blobs_serve_the_published_default_request(tmp_path):
    """Checks the warm fills the cache with exactly the requests the published globe defaults describe."""
    explorer, cube_id = loaded_param_run(tmp_path, with_geo=True)
    defaults          = explorer.load_status()["cube"]["globe_defaults"]

    assert set(defaults["amp_min"]) == {"full", "param"}
    assert defaults["max_points"] == explorer.GLOBE_DEFAULT_POINTS

    explorer.globe_blobs.clear()
    explorer._warm_globe_blobs(cube_id)

    assert explorer.globe_blobs.size() == len(defaults["amp_min"])

    for source, amp_min in defaults["amp_min"].items():
        warmed = explorer.globe_blobs.get(f"{cube_id}|{source}|{amp_min!r}|{defaults['max_points']}")
        assert warmed is not None
        assert explorer.globe_points_bin(cube_id, source, amp_min, defaults["max_points"]) is warmed


def test_globe_defaults_are_absent_without_geocoding(tmp_path):
    """Checks a run that cannot be geolocated publishes no globe defaults and warms nothing."""
    explorer, cube_id = loaded_run(tmp_path)

    assert explorer.load_status()["cube"]["globe_defaults"] is None

    explorer._warm_globe_blobs(cube_id)
    assert explorer.globe_blobs.size() == 0


def test_loading_another_cube_drops_the_previous_blobs(tmp_path):
    """Checks the blob cache is emptied when a different cube is loaded."""
    make_preproc_run(tmp_path, name="run_a", with_geo=True)
    make_preproc_run(tmp_path, name="run_b", with_geo=True)

    explorer, run_ids = open_runs(tmp_path, expected=2)
    defaults          = load_cube(explorer, run_ids[0])["cube"]["globe_defaults"]

    explorer._warm_globe_blobs(run_ids[0])
    key = f"{run_ids[0]}|full|{defaults['amp_min']['full']!r}|{defaults['max_points']}"

    assert explorer.globe_blobs.get(key) is not None

    load_cube(explorer, run_ids[1])
    assert explorer.globe_blobs.get(key) is None
