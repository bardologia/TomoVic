"""Tests covering the per-pixel geometry field: kz conventions, slicing, IO and its builder."""

from __future__ import annotations

import math

import numpy as np
import pytest

from tools.baselines.containers import TrackProfiles
from tools.data.regions         import CropRegion
from tools.sar.geometry_field   import GeometryField, GeometryFieldBuilder
from tools.sar.track_parameters import TrackParameters


def _field(**kwargs) -> GeometryField:
    """Returns a three-track GeometryField over a 2x2 azimuth/range grid, overridable per field."""
    base = dict(
        labels        = ["REF", "S1", "S2"],
        reference     = "REF",
        wavelength    = 0.2262,
        azimuth_start = 1000,
        range_start   = 500,
        look_angle    = np.array([0.6, 0.7], dtype=np.float64),
        slant_range   = np.array([3600.0, 3900.0], dtype=np.float64),
        baseline_h    = np.array([[0.0, 0.0], [10.0, 12.0], [20.0, 22.0]], dtype=np.float64),
        baseline_v    = np.array([[0.0, 0.0], [1.0, 1.5], [2.0, 2.5]], dtype=np.float64),
    )
    base.update(kwargs)
    return GeometryField(**base)


def test_kz_height_matches_closed_form():
    """Verifies the height-convention kz in rad/m matches 4*pi*bperp / (lambda*R*sin(theta))."""
    gf = _field()
    kz = gf.kz("height")

    i, a, g  = 1, 0, 1
    bperp    = gf.baseline_h[i, a] * math.cos(gf.look_angle[g]) + gf.baseline_v[i, a] * math.sin(gf.look_angle[g])
    expected = 4.0 * math.pi * bperp / (gf.wavelength * gf.slant_range[g] * math.sin(gf.look_angle[g]))

    assert float(kz[i, a, g]) == pytest.approx(expected, rel=1e-9)


def test_kz_slant_matches_closed_form_without_sin_theta():
    """Verifies the slant-convention kz in rad/m matches 4*pi*bperp / (lambda*R)."""
    gf = _field()
    kz = gf.kz("slant")

    i, a, g  = 2, 1, 0
    bperp    = gf.baseline_h[i, a] * math.cos(gf.look_angle[g]) + gf.baseline_v[i, a] * math.sin(gf.look_angle[g])
    expected = 4.0 * math.pi * bperp / (gf.wavelength * gf.slant_range[g])

    assert float(kz[i, a, g]) == pytest.approx(expected, rel=1e-9)


def test_height_equals_slant_over_sin_theta():
    """Verifies the height kz equals the slant kz divided by sin(theta)."""
    gf        = _field()
    sin_theta = np.sin(gf.look_angle).reshape(1, 1, -1)

    assert np.allclose(gf.kz("height"), gf.kz("slant") / sin_theta, rtol=1e-9)


def test_reference_track_kz_is_zero():
    """Verifies the reference track carries zero kz in both conventions."""
    gf = _field()

    assert np.abs(gf.kz("height")[0]).max() == 0.0
    assert np.abs(gf.kz("slant")[0]).max()  == 0.0


def test_kz_shape_is_tracks_azimuth_range():
    """Verifies the kz cube has shape (tracks, azimuth, range)."""
    gf = _field()

    assert gf.kz("height").shape == (gf.n_tracks, gf.n_azimuth, gf.n_range)
    assert (gf.n_tracks, gf.n_azimuth, gf.n_range) == (3, 2, 2)


def test_unknown_convention_raises():
    """Verifies an unknown kz convention raises ValueError."""
    gf = _field()

    with pytest.raises(ValueError):
        gf.kz("geocoded")


def test_slice_offsets_starts_and_arrays():
    """Verifies slicing shifts the azimuth/range starts and cuts the derived kz consistently."""
    gf  = _field()
    cut = gf.slice(slice(1, 2), slice(0, 1))

    assert cut.azimuth_start == 1001
    assert cut.range_start   == 500
    assert cut.n_azimuth == 1
    assert cut.n_range   == 1
    assert np.allclose(cut.kz("height"), gf.kz("height")[:, 1:2, 0:1])


def test_subset_keeps_reference_and_selected_secondaries():
    """Verifies a subset keeps the reference track ahead of the selected secondaries."""
    gf  = _field()
    cut = gf.subset(["S2"])

    assert cut.labels == ["REF", "S2"]
    assert np.allclose(cut.baseline_h[1], gf.baseline_h[2])


def test_save_load_round_trip(tmp_path):
    """Verifies saving and reloading a geometry field preserves every stored field."""
    gf   = _field()
    path = gf.save(tmp_path / GeometryField.FILENAME)
    back = GeometryField.load(path)

    assert back.labels == gf.labels
    assert back.reference == gf.reference
    assert back.wavelength == pytest.approx(gf.wavelength)
    assert back.azimuth_start == gf.azimuth_start
    assert back.range_start == gf.range_start
    assert np.allclose(back.look_angle, gf.look_angle)
    assert np.allclose(back.slant_range, gf.slant_range)
    assert np.allclose(back.baseline_h, gf.baseline_h)
    assert np.allclose(back.baseline_v, gf.baseline_v)


def test_builder_look_angle_from_reference_track():
    """Verifies the builder derives the cropped slant range and arccos look angle from the reference track."""
    parameters = TrackParameters(
        labels     = ["REF", "S1"],
        parameters = [
            {"r": [3600.0, 3700.0, 3800.0, 3900.0], "h0": 3719.0, "terrain": 684.0, "lambda": 0.2262, "antdir": 1},
            {"r": [3600.0, 3700.0, 3800.0, 3900.0], "h0": 3719.0, "terrain": 684.0, "lambda": 0.2262, "antdir": 1},
        ],
    )
    profiles = TrackProfiles(
        labels        = ["REF", "S1"],
        horizontal    = np.array([[0.0, 0.0], [10.0, 12.0]], dtype=np.float64),
        vertical      = np.array([[0.0, 0.0], [1.0, 2.0]],   dtype=np.float64),
        azimuth_start = 1000,
    )
    crop  = CropRegion(azimuth_start=1000, azimuth_end=1002, range_start=1, range_end=3)
    field = GeometryFieldBuilder(parameters, profiles, crop).build()

    height   = 3719.0 - 684.0
    expected = np.arccos(np.clip(height / np.array([3700.0, 3800.0]), -1.0, 1.0))

    assert np.allclose(field.slant_range, [3700.0, 3800.0])
    assert np.allclose(field.look_angle, expected)
    assert np.allclose(field.baseline_h[0], 0.0)
    assert field.range_start == 1
    assert field.azimuth_start == 1000


def test_builder_rejects_uncovered_azimuth():
    """Verifies a crop reaching past the track profile azimuth coverage raises ValueError."""
    parameters = TrackParameters(
        labels     = ["REF"],
        parameters = [{"r": [3600.0, 3700.0], "h0": 3719.0, "terrain": 684.0, "lambda": 0.2262, "antdir": 1}],
    )
    profiles = TrackProfiles(labels=["REF"], horizontal=np.zeros((1, 5)), vertical=np.zeros((1, 5)), azimuth_start=1000)
    crop     = CropRegion(azimuth_start=1000, azimuth_end=1010, range_start=0, range_end=2)

    with pytest.raises(ValueError):
        GeometryFieldBuilder(parameters, profiles, crop).build()


def test_builder_rejects_left_looking_track():
    """Verifies a left-looking track raises ValueError."""
    parameters = TrackParameters(
        labels     = ["REF"],
        parameters = [{"r": [3600.0, 3700.0], "h0": 3719.0, "terrain": 684.0, "lambda": 0.2262, "antdir": -1}],
    )
    profiles = TrackProfiles(labels=["REF"], horizontal=np.zeros((1, 5)), vertical=np.zeros((1, 5)), azimuth_start=1000)
    crop     = CropRegion(azimuth_start=1000, azimuth_end=1002, range_start=0, range_end=2)

    with pytest.raises(ValueError, match="left-looking"):
        GeometryFieldBuilder(parameters, profiles, crop).build()


def test_builder_rejects_height_at_or_above_slant_range():
    """Verifies a platform height at or above the slant range raises ValueError."""
    parameters = TrackParameters(
        labels     = ["REF"],
        parameters = [{"r": [3600.0, 3700.0], "h0": 4400.0, "terrain": 684.0, "lambda": 0.2262, "antdir": 1}],
    )
    profiles = TrackProfiles(labels=["REF"], horizontal=np.zeros((1, 5)), vertical=np.zeros((1, 5)), azimuth_start=1000)
    crop     = CropRegion(azimuth_start=1000, azimuth_end=1002, range_start=0, range_end=2)

    with pytest.raises(ValueError, match="slant range"):
        GeometryFieldBuilder(parameters, profiles, crop).build()


@pytest.mark.real_data
def test_real_geometry_field_matches_builder(meta_dir, data_dir, dataset_json):
    """Verifies rebuilding the geometry field from the real dataset reproduces the stored kz."""
    parameters  = TrackParameters.load(meta_dir / TrackParameters.FILENAME)
    profiles    = TrackProfiles.load(data_dir / TrackProfiles.FILENAME)
    global_crop = dataset_json["global_crop"]
    crop        = CropRegion(global_crop[0], global_crop[1], global_crop[2], global_crop[3])

    built  = GeometryFieldBuilder(parameters, profiles, crop).build()
    stored = GeometryField.load(meta_dir / GeometryField.FILENAME)

    assert built.labels == stored.labels
    assert np.allclose(built.kz("height"), stored.kz("height"))


@pytest.mark.real_data
def test_real_geometry_field_reference_kz_zero_and_mean_baseline(meta_dir, baselines_json):
    """Verifies the real field has zero reference kz and mean perpendicular baselines matching the stored table in metres."""
    gf         = GeometryField.load(meta_dir / GeometryField.FILENAME)
    th_mean    = float(gf.look_angle.mean())
    bperp_mean = gf.perpendicular_baseline().mean(axis=(1, 2))

    expected = np.array([h * math.cos(th_mean) + v * math.sin(th_mean) for v, h in zip(baselines_json["vertical"], baselines_json["horizontal"])])

    assert np.abs(gf.kz("height")[0]).max() == 0.0
    assert np.allclose(bperp_mean, expected, atol=0.1)


def test_validate_extent_accepts_matching_crop():
    """Verifies extent validation accepts the crop the field was built on."""
    gf = _field()
    gf.validate_extent(CropRegion(gf.azimuth_start, gf.azimuth_start + gf.n_azimuth, gf.range_start, gf.range_start + gf.n_range))


def test_validate_extent_rejects_foreign_crop():
    """Verifies extent validation rejects a crop offset from the field."""
    gf = _field()

    with pytest.raises(ValueError, match="different crop"):
        gf.validate_extent(CropRegion(gf.azimuth_start + 1, gf.azimuth_start + 1 + gf.n_azimuth, gf.range_start, gf.range_start + gf.n_range))
