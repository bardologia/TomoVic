"""Tests TomoGeometry's kz derivation, steering vectors, and outer products.

Covers kz built from baselines or supplied explicitly, the slant and height axis
conventions, the unit-magnitude steering matrix, the Hermitian outer product, and
the describe() summary."""

from __future__ import annotations

import math

import pytest
import torch

from configuration.sar.geometry_config import GeometryConfig
from tools.sar.tomo_geometry           import TomoGeometry


def _cfg(**kwargs) -> GeometryConfig:
    """Returns a GeometryConfig with the default synthetic geometry, overridden by kwargs."""
    base = dict(wavelength=0.23, slant_range=5000.0, baselines=(0.0, 10.0, 20.0))
    base.update(kwargs)
    return GeometryConfig(**base)


def test_kz_from_baselines_matches_hand_computation():
    """Verifies kz equals 4 pi b / (lambda R sin theta) per track in rad/m."""
    cfg   = _cfg(wavelength=0.23, slant_range=5000.0, look_angle_deg=30.0, baselines=(0.0, 10.0, 20.0))
    geom  = TomoGeometry(cfg, torch.linspace(-20.0, 80.0, 150))

    scale    = 4.0 * math.pi / (0.23 * 5000.0 * math.sin(math.radians(30.0)))
    expected = [0.0, scale * 10.0, scale * 20.0]

    assert geom.kz.tolist() == pytest.approx(expected, rel=1e-6)


def test_slant_kz_scale_is_four_pi_over_lambda_r0():
    """Verifies the slant convention drops the sin(look) factor from the kz scale."""
    cfg   = _cfg(wavelength=0.1, slant_range=2000.0, baselines=(0.0, 1.0), height_axis_convention="slant")
    geom  = TomoGeometry(cfg, torch.linspace(0.0, 1.0, 4))

    assert float(geom.kz[1]) == pytest.approx(4.0 * math.pi / (0.1 * 2000.0), rel=1e-6)


def test_height_kz_is_slant_kz_divided_by_sin_look():
    """Verifies height kz equals slant kz divided by sin of the look angle."""
    slant_cfg  = _cfg(wavelength=0.1, slant_range=2000.0, look_angle_deg=35.0, baselines=(0.0, 1.0), height_axis_convention="slant")
    height_cfg = _cfg(wavelength=0.1, slant_range=2000.0, look_angle_deg=35.0, baselines=(0.0, 1.0), height_axis_convention="height")

    x      = torch.linspace(0.0, 1.0, 4)
    slant  = TomoGeometry(slant_cfg,  x)
    height = TomoGeometry(height_cfg, x)

    assert float(height.kz[1]) == pytest.approx(float(slant.kz[1]) / math.sin(math.radians(35.0)), rel=1e-6)


def test_unknown_convention_raises():
    """Verifies an unrecognised height_axis_convention is rejected."""
    cfg = _cfg(height_axis_convention="bogus")

    with pytest.raises(ValueError, match="height_axis_convention"):
        TomoGeometry(cfg, torch.linspace(0.0, 1.0, 4))


def test_explicit_kz_values_ignore_convention_scaling():
    """Verifies explicit kz values are used verbatim under either convention."""
    slant_cfg  = _cfg(kz_values=(0.05, 0.10), height_axis_convention="slant")
    height_cfg = _cfg(kz_values=(0.05, 0.10), height_axis_convention="height")

    x = torch.linspace(0.0, 1.0, 4)

    assert TomoGeometry(slant_cfg, x).kz.tolist() == TomoGeometry(height_cfg, x).kz.tolist()


def test_explicit_kz_values_override_baselines():
    """Verifies explicit kz values take precedence over configured baselines."""
    cfg  = _cfg(kz_values=(0.05, 0.10, 0.15), baselines=(0.0, 999.0, 999.0))
    geom = TomoGeometry(cfg, torch.linspace(-10.0, 10.0, 20))

    assert geom.kz.tolist() == pytest.approx([0.05, 0.10, 0.15], rel=1e-6)


def test_reference_baseline_gives_zero_kz():
    """Verifies a zero baseline yields exactly zero kz."""
    cfg  = _cfg(baselines=(0.0, 5.0))
    geom = TomoGeometry(cfg, torch.linspace(-5.0, 5.0, 8))

    assert float(geom.kz[0]) == 0.0


def test_n_tracks_matches_baseline_count():
    """Verifies the track count and kz length follow the number of baselines."""
    cfg  = _cfg(baselines=(0.0, 1.0, 2.0, 3.0, 4.0))
    geom = TomoGeometry(cfg, torch.linspace(0.0, 1.0, 6))

    assert geom.n_tracks == 5
    assert geom.kz.shape[0] == 5


def test_empty_baselines_and_kz_raises():
    """Verifies a geometry with neither baselines nor kz values is rejected."""
    cfg = GeometryConfig(baselines=(), kz_values=())

    with pytest.raises(ValueError):
        TomoGeometry(cfg, torch.linspace(0.0, 1.0, 4))


def test_steering_unit_magnitude():
    """Verifies every steering entry has unit magnitude."""
    cfg  = _cfg(baselines=(0.0, 7.5, 15.0))
    geom = TomoGeometry(cfg, torch.linspace(-20.0, 80.0, 64))

    mag = geom.steering.abs()

    assert torch.allclose(mag, torch.ones_like(mag), atol=1e-6)


def test_steering_reference_track_is_all_ones():
    """Verifies the zero-kz reference track steers with a constant phase of zero."""
    cfg  = _cfg(baselines=(0.0, 12.0))
    geom = TomoGeometry(cfg, torch.linspace(-20.0, 80.0, 32))

    ref = geom.steering[0]

    assert torch.allclose(ref.real, torch.ones_like(ref.real), atol=1e-6)
    assert torch.allclose(ref.imag, torch.zeros_like(ref.imag), atol=1e-6)


def test_steering_phase_equals_kz_times_x():
    """Verifies the steering phase wraps kz times the elevation axis."""
    x    = torch.linspace(-20.0, 80.0, 50)
    cfg  = _cfg(baselines=(0.0, 9.0))
    geom = TomoGeometry(cfg, x)

    phase    = torch.angle(geom.steering)
    expected = geom.kz.reshape(-1, 1) * x.reshape(1, -1)
    wrapped  = torch.remainder(expected + math.pi, 2.0 * math.pi) - math.pi

    assert torch.allclose(torch.remainder(phase + math.pi, 2.0 * math.pi) - math.pi, wrapped, atol=1e-5)


def test_outer_is_hermitian_per_height():
    """Verifies the per-height outer product matrix is Hermitian."""
    cfg  = _cfg(baselines=(0.0, 5.0, 11.0))
    geom = TomoGeometry(cfg, torch.linspace(-20.0, 80.0, 16))

    outer = geom.outer.permute(2, 0, 1)

    assert torch.allclose(outer, outer.conj().transpose(-1, -2), atol=1e-6)


def test_outer_diagonal_is_unity():
    """Verifies the outer product diagonal has unit magnitude."""
    cfg  = _cfg(baselines=(0.0, 5.0, 11.0))
    geom = TomoGeometry(cfg, torch.linspace(-20.0, 80.0, 16))

    diag = torch.diagonal(geom.outer.permute(2, 0, 1), dim1=-2, dim2=-1)

    assert torch.allclose(diag.abs(), torch.ones_like(diag.abs()), atol=1e-6)


def test_outer_equals_steering_outer_product():
    """Verifies outer equals the steering vector times its conjugate per height bin."""
    cfg  = _cfg(baselines=(0.0, 3.0, 6.0))
    geom = TomoGeometry(cfg, torch.linspace(-20.0, 80.0, 12))

    manual = torch.einsum("ik,jk->ijk", geom.steering, geom.steering.conj())

    assert torch.allclose(geom.outer, manual, atol=1e-6)


def test_describe_reports_kz_source_and_tracks():
    """Verifies describe() reports the track count and a baseline-derived kz source."""
    cfg  = _cfg(baselines=(0.0, 10.0, 20.0))
    geom = TomoGeometry(cfg, torch.linspace(-20.0, 80.0, 30))

    info = geom.describe()

    assert info["Tracks"] == 3
    assert "baselines" in info["kz source"]


def test_describe_kz_source_explicit_when_kz_values_given():
    """Verifies describe() names explicit kz values as the kz source."""
    cfg  = _cfg(kz_values=(0.01, 0.02))
    geom = TomoGeometry(cfg, torch.linspace(-5.0, 5.0, 10))

    assert geom.describe()["kz source"] == "explicit kz_values"


def test_describe_min_max_kz_consistent():
    """Verifies the reported kz extremes match the kz tensor and are labelled in rad/m."""
    cfg  = _cfg(baselines=(0.0, 10.0, 20.0))
    geom = TomoGeometry(cfg, torch.linspace(-20.0, 80.0, 30))

    info  = geom.describe()
    kzmin = float(geom.kz.min())
    kzmax = float(geom.kz.max())

    assert info["kz min"] == f"{kzmin:.4f} rad/m"
    assert info["kz max"] == f"{kzmax:.4f} rad/m"


def test_dtype_and_device_follow_x_axis():
    """Verifies kz adopts the dtype and device of the elevation axis tensor."""
    x    = torch.linspace(-20.0, 80.0, 24, dtype=torch.float64)
    cfg  = _cfg(baselines=(0.0, 8.0))
    geom = TomoGeometry(cfg, x)

    assert geom.kz.dtype == x.dtype
    assert geom.kz.device == x.device
