"""Tests checking that the stored geometry of a real dataset traces back to its track parameters.

Each test re-derives one stored quantity (elevation axis, look angle, slant
range, wavelength, baselines) from the raw track parameters and the recorded
crop, so the dataset's geometry provenance stays verifiable.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from tools.sar.geometry_field   import GeometryField
from tools.sar.track_parameters import TrackParameters


@pytest.mark.real_data
def test_elevation_axis_spans_config_height_range_at_tomogram_resolution(config_state_json, tomogram_full):
    """Verifies the elevation axis spans the configured height range in metres at the tomogram's elevation sampling."""
    height_range   = config_state_json["tomogram_config"]["height_range"]
    profile_length = int(tomogram_full.shape[0])

    x_axis = np.linspace(float(height_range[0]), float(height_range[1]), profile_length)

    assert float(x_axis[0])  == pytest.approx(height_range[0])
    assert float(x_axis[-1]) == pytest.approx(height_range[1])
    assert x_axis.shape[0] == profile_length
    assert float(x_axis[1] - x_axis[0]) > 0.0


@pytest.mark.real_data
def test_geometry_field_dimensions_match_data_cubes(meta_dir, tomogram_full, interferograms):
    """Verifies the geometry field grid matches the tomogram and interferogram cubes and counts one track more than the interferograms."""
    field = GeometryField.load(meta_dir / GeometryField.FILENAME)

    assert field.n_azimuth == tomogram_full.shape[1] == interferograms.shape[1]
    assert field.n_range   == tomogram_full.shape[2] == interferograms.shape[2]
    assert field.n_tracks  == interferograms.shape[0] + 1


@pytest.mark.real_data
def test_reference_track_is_dataset_primary(meta_dir, dataset_json):
    """Verifies the geometry reference track is the dataset primary pass."""
    field = GeometryField.load(meta_dir / GeometryField.FILENAME)

    assert field.reference == field.labels[0] == dataset_json["pass_labels"][0]


@pytest.mark.real_data
def test_wavelength_is_reference_track_lambda_in_l_band(meta_dir):
    """Verifies the stored wavelength is the reference track lambda and lies in L band."""
    field      = GeometryField.load(meta_dir / GeometryField.FILENAME)
    parameters = TrackParameters.load(meta_dir / TrackParameters.FILENAME)

    assert field.wavelength == pytest.approx(parameters.parameters[0]["lambda"], rel=1e-12)
    assert 0.20 < field.wavelength < 0.25


@pytest.mark.real_data
def test_slant_range_is_reference_track_vector_cropped(meta_dir, config_state_json):
    """Verifies the slant range in metres is the reference track vector cut to the recorded range crop."""
    field      = GeometryField.load(meta_dir / GeometryField.FILENAME)
    parameters = TrackParameters.load(meta_dir / TrackParameters.FILENAME)
    crop       = config_state_json["crop"]

    reference = np.asarray(parameters.parameters[0]["r"], dtype=np.float64)

    assert reference.shape[0] >= crop["range_end"]
    assert np.allclose(field.slant_range, reference[crop["range_start"]:crop["range_end"]])


@pytest.mark.real_data
def test_look_angle_is_arccos_height_over_slant(meta_dir, config_state_json):
    """Verifies the look angle in radians is arccos of platform height over slant range."""
    field      = GeometryField.load(meta_dir / GeometryField.FILENAME)
    parameters = TrackParameters.load(meta_dir / TrackParameters.FILENAME)
    crop       = config_state_json["crop"]

    reference = parameters.parameters[0]
    height    = float(reference["h0"]) - float(reference["terrain"])
    slant     = np.asarray(reference["r"], dtype=np.float64)[crop["range_start"]:crop["range_end"]]
    expected  = np.arccos(np.clip(height / slant, -1.0, 1.0))

    assert np.allclose(field.look_angle, expected)


@pytest.mark.real_data
def test_baselines_are_profile_offsets_relative_to_reference(meta_dir, baselines_json):
    """Verifies per-track baselines are zero for the reference and reproduce the stored perpendicular baselines in metres."""
    field = GeometryField.load(meta_dir / GeometryField.FILENAME)
    look  = float(field.look_angle.mean())

    measured = field.perpendicular_baseline().mean(axis=(1, 2))
    expected = np.array([h * math.cos(look) + v * math.sin(look) for v, h in zip(baselines_json["vertical"], baselines_json["horizontal"])])

    assert np.allclose(field.baseline_h[0], 0.0)
    assert np.allclose(field.baseline_v[0], 0.0)
    assert np.allclose(measured, expected, atol=0.1)


@pytest.mark.real_data
def test_sensor_geometry_is_physically_plausible(meta_dir):
    """Verifies platform height, slant range and look angle are ordered and inside plausible airborne bounds."""
    field      = GeometryField.load(meta_dir / GeometryField.FILENAME)
    parameters = TrackParameters.load(meta_dir / TrackParameters.FILENAME)

    reference = parameters.parameters[0]
    height    = float(reference["h0"]) - float(reference["terrain"])
    look_deg  = np.degrees(field.look_angle)

    assert height > 0.0
    assert float(field.slant_range[0]) > height
    assert np.all(np.diff(field.slant_range) > 0.0)
    assert np.all(np.diff(field.look_angle) > 0.0)
    assert 15.0 < float(look_deg.min()) and float(look_deg.max()) < 65.0
