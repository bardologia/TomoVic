"""Tests that GeometryField reproduces the analytic kz interferometric conventions.

The cases pin the perpendicular-baseline projection, the slant and height kz
formulas, their equivalence in interferometric phase, and the scaling of kz with
baseline magnitude and slant range."""

from __future__ import annotations

import math

import numpy as np
import pytest

from tools.sar.geometry_field import GeometryField


def _field(look_deg=35.0, wavelength=0.2262, slant=3700.0, n_az=4, n_rg=3) -> GeometryField:
    """Builds a small synthetic GeometryField with constant look angle and linear baselines.

    Args:
        look_deg: Look angle in degrees, applied to every range bin.
        wavelength: Radar wavelength in metres.
        slant: Near slant range in metres; the range axis spans slant to slant + 200 m.
        n_az: Number of azimuth samples.
        n_rg: Number of range samples.

    Returns:
        A GeometryField over four tracks with baselines of shape (4, n_az) metres.
    """
    look  = np.full(n_rg, math.radians(look_deg), dtype=np.float64)
    slant = np.linspace(slant, slant + 200.0, n_rg, dtype=np.float64)

    horizontal = np.array([0.0, 10.0, 25.0, 40.0], dtype=np.float64)[:, None] * np.ones((1, n_az))
    vertical   = np.array([0.0, -1.5, 2.0, -3.0],  dtype=np.float64)[:, None] * np.ones((1, n_az))

    return GeometryField(
        labels        = [f"T{i}" for i in range(4)],
        reference     = "T0",
        wavelength    = wavelength,
        azimuth_start = 0,
        range_start   = 0,
        look_angle    = look,
        slant_range   = slant,
        baseline_h    = horizontal,
        baseline_v    = vertical,
    )


def test_perpendicular_baseline_matches_projection_formula():
    """Verifies the perpendicular baseline equals b_h cos(theta) + b_v sin(theta)."""
    field = _field(look_deg=35.0)
    theta = field.look_angle[0]

    bperp    = field.perpendicular_baseline()
    expected = field.baseline_h[:, :, None] * math.cos(theta) + field.baseline_v[:, :, None] * math.sin(theta)

    assert np.allclose(bperp, expected)


def test_slant_kz_equals_four_pi_bperp_over_lambda_r():
    """Verifies slant kz equals 4 pi b_perp / (lambda R) in rad/m."""
    field   = _field()
    kz      = field.kz("slant")

    scale    = 4.0 * math.pi / field.wavelength
    bperp    = field.perpendicular_baseline()
    expected = scale * bperp / field.slant_range.reshape(1, 1, -1)

    assert np.allclose(kz, expected)


def test_height_kz_is_slant_kz_divided_by_sin_theta():
    """Verifies height kz is the slant kz divided by sin of the look angle."""
    field = _field()
    sin   = np.sin(field.look_angle).reshape(1, 1, -1)

    assert np.allclose(field.kz("height"), field.kz("slant") / sin)


def test_interferometric_phase_invariant_across_conventions():
    """Verifies kz times its own axis gives the same phase in slant and height conventions."""
    field = _field(look_deg=35.0)
    sin   = np.sin(field.look_angle).reshape(1, 1, -1)

    elevation = 17.0
    height    = elevation * sin

    phase_slant  = field.kz("slant")  * elevation
    phase_height = field.kz("height") * height

    assert np.allclose(phase_slant, phase_height)


def test_reference_track_has_zero_kz_in_both_conventions():
    """Verifies the zero-baseline reference track carries zero kz under both conventions."""
    field = _field()

    assert np.allclose(field.kz("slant")[0],  0.0)
    assert np.allclose(field.kz("height")[0], 0.0)


def test_kz_grows_with_baseline_magnitude():
    """Verifies kz magnitude increases monotonically with the track baseline."""
    field = _field()
    kz    = field.kz("slant")

    magnitude = np.abs(kz[:, 0, 0])

    assert np.all(np.diff(magnitude) > 0.0)


def test_unknown_convention_raises():
    """Verifies an unrecognised kz convention name is rejected."""
    field = _field()

    with pytest.raises(ValueError):
        field.kz("baseline")


def test_kz_inversely_proportional_to_slant_range():
    """Verifies doubling the slant range halves kz."""
    near = _field(slant=3000.0)
    far  = _field(slant=6000.0)

    ratio = far.kz("slant")[1, 0, 0] / near.kz("slant")[1, 0, 0]

    assert abs(ratio - 0.5) < 1e-9
