"""Tests that the stored geometry kz agrees with the PyRAT tomogram elevation axis.

The real-data cases beamform the measured interferograms against the dataset kz
and check that the resulting peaks land on the PyRAT tomogram height axis, that
the beamforming sign is the one PyRAT uses, and that the height convention fits
at least as well as the slant one."""

from __future__ import annotations

import math

import numpy as np
import pytest

from tools.sar.geometry_field import GeometryField


PYRAT_BEAMFORMING_SIGN = -1.0


def _geometry_field(meta_dir) -> GeometryField:
    """Loads the dataset GeometryField, skipping the test when it is absent.

    Args:
        meta_dir: Dataset meta directory holding the geometry field file.

    Returns:
        The loaded GeometryField.
    """
    path = meta_dir / GeometryField.FILENAME
    if not path.exists():
        pytest.skip(f"{path} not present; re-run preprocessing for this dataset")

    return GeometryField.load(path)


def _height_axis(config_state_json: dict, n_elevation: int) -> np.ndarray:
    """Builds the tomogram elevation axis in metres.

    Args:
        config_state_json: Preprocessing config state holding the tomogram height range.
        n_elevation: Number of elevation bins in the tomogram.

    Returns:
        Array of shape (n_elevation,) with heights in metres.
    """
    height_range = config_state_json["tomogram_config"]["height_range"]
    return np.linspace(float(height_range[0]), float(height_range[1]), n_elevation)


def _clean_pixels(tomogram: np.ndarray, z: np.ndarray, az: np.ndarray, rg: np.ndarray):
    """Selects tomogram pixels whose profile is single-peaked and bright.

    Args:
        tomogram: Complex tomogram of shape (elevation, azimuth, range).
        z: Elevation axis in metres, shape (elevation,).
        az: Azimuth indices to sample.
        rg: Range indices to sample.

    Returns:
        Tuple (ys, xs, peak_z) where ys and xs index the retained pixels within the
        sampled grid and peak_z holds the argmax height in metres for every sampled
        pixel, shape (len(az), len(rg)).
    """
    profile = np.abs(np.asarray(tomogram[:, az][:, :, rg])).astype(np.float64)
    n_elev  = profile.shape[0]

    argmax = profile.argmax(0)
    total  = profile.sum(0)
    peak_z = z[argmax]

    window        = 6
    concentration = np.empty(argmax.shape)
    for i in range(argmax.shape[0]):
        for j in range(argmax.shape[1]):
            a = argmax[i, j]
            concentration[i, j] = profile[max(0, a - window):min(n_elev, a + window + 1), i, j].sum() / max(total[i, j], 1e-12)

    clean = (concentration > 0.55) & (total > np.percentile(total, 40))
    ys, xs = np.where(clean)

    return ys, xs, peak_z


def _beamform_peaks(interferograms: np.ndarray, kz_secondary: np.ndarray, z: np.ndarray, sign: float) -> np.ndarray:
    """Beamforms the interferogram stack and returns the peak height per pixel.

    Args:
        interferograms: Complex secondary interferograms of shape (tracks, pixels).
        kz_secondary: Secondary-track kz in rad/m, shape (tracks, pixels).
        z: Elevation axis in metres, shape (elevation,).
        sign: Sign applied to the steering phase.

    Returns:
        Peak elevation in metres for every pixel, shape (pixels,).
    """
    phase = sign * kz_secondary[:, :, None] * z[None, None, :]
    steer = np.exp(1j * phase)

    spectrum = np.abs((steer * interferograms[:, :, None]).sum(0)) ** 2

    return z[spectrum.argmax(1)]


def _rayleigh(field: GeometryField, convention: str) -> float:
    """Returns the Rayleigh elevation resolution in metres at the scene centre."""
    return 2.0 * math.pi / float(np.ptp(field.kz(convention)[:, field.n_azimuth // 2, field.n_range // 2]))


def _sampled(meta_dir, config_state_json, tomogram_full, interferograms, convention: str, sign: float = PYRAT_BEAMFORMING_SIGN, max_pixels: int = 2000):
    """Beamforms a sampled set of clean pixels and pairs them with the tomogram peaks.

    Args:
        meta_dir: Dataset meta directory holding the geometry field file.
        config_state_json: Preprocessing config state holding the tomogram height range.
        tomogram_full: Complex tomogram of shape (elevation, azimuth, range).
        interferograms: Complex interferogram stack of shape (tracks, azimuth, range).
        convention: kz convention passed to GeometryField.kz, "slant" or "height".
        sign: Sign applied to the beamforming steering phase.
        max_pixels: Upper bound on the number of pixels evaluated.

    Returns:
        Tuple (peaks, reference, field, z) with beamformed peak heights in metres,
        the tomogram peak heights in metres, the geometry field, and the elevation
        axis in metres.
    """
    field  = _geometry_field(meta_dir)
    n_elev = tomogram_full.shape[0]
    z      = _height_axis(config_state_json, n_elev)

    az      = np.arange(0, tomogram_full.shape[1], 8)
    rg      = np.arange(0, tomogram_full.shape[2], 8)

    ys, xs, peak_z = _clean_pixels(tomogram_full, z, az, rg)

    take    = np.linspace(0, len(ys) - 1, min(max_pixels, len(ys))).astype(int)
    ys, xs  = ys[take], xs[take]

    reference = peak_z[ys, xs]

    kz     = field.kz(convention)[:, az][:, :, rg]
    kz_sec = kz[1:, ys, xs]
    ifg    = np.asarray(interferograms[:, az][:, :, rg])[:, ys, xs]

    peaks = _beamform_peaks(ifg, kz_sec, z, sign)

    return peaks, reference, field, z


@pytest.mark.real_data
@pytest.mark.slow
def test_geometry_field_kz_matches_hand_formula(meta_dir):
    """Verifies the stored height kz equals 4 pi b_perp / (lambda R sin theta)."""
    field = _geometry_field(meta_dir)

    scale    = 4.0 * math.pi / field.wavelength
    cos      = np.cos(field.look_angle).reshape(1, 1, -1)
    sin      = np.sin(field.look_angle).reshape(1, 1, -1)
    bperp    = field.baseline_h[:, :, None] * cos + field.baseline_v[:, :, None] * sin
    expected = scale * bperp / (field.slant_range.reshape(1, 1, -1) * sin)

    assert np.allclose(field.kz("height"), expected)


@pytest.mark.real_data
@pytest.mark.slow
def test_reference_track_kz_is_zero(meta_dir):
    """Verifies the reference track of the real dataset carries zero kz."""
    field = _geometry_field(meta_dir)

    assert np.allclose(field.kz("height")[0], 0.0)
    assert np.allclose(field.kz("slant")[0],  0.0)


@pytest.mark.real_data
@pytest.mark.slow
def test_beamformed_peaks_match_pyrat_tomogram_axis(meta_dir, config_state_json, tomogram_full, interferograms):
    """Verifies beamformed peaks agree with the PyRAT tomogram axis within one Rayleigh bin."""
    peaks, reference, field, z = _sampled(meta_dir, config_state_json, tomogram_full, interferograms, "height")

    rayleigh = _rayleigh(field, "height")

    median_error = float(np.median(np.abs(peaks - reference)))
    within_band  = float((np.abs(peaks - reference) < 3.0).mean())

    assert median_error < rayleigh
    assert within_band  > 0.7


@pytest.mark.real_data
@pytest.mark.slow
def test_flipped_beamforming_sign_misses_the_pyrat_tomogram_axis(meta_dir, config_state_json, tomogram_full, interferograms):
    """Verifies flipping the steering sign degrades the peak agreement well past a Rayleigh bin."""
    aligned, reference, field, _ = _sampled(meta_dir, config_state_json, tomogram_full, interferograms, "height")
    flipped, _,         _,     _ = _sampled(meta_dir, config_state_json, tomogram_full, interferograms, "height", sign=-PYRAT_BEAMFORMING_SIGN)

    rayleigh = _rayleigh(field, "height")

    aligned_error = float(np.median(np.abs(aligned - reference)))
    flipped_error = float(np.median(np.abs(flipped - reference)))

    assert aligned_error < rayleigh
    assert flipped_error > rayleigh
    assert flipped_error > 3.0 * aligned_error


@pytest.mark.real_data
@pytest.mark.slow
def test_height_convention_fits_at_least_as_well_as_slant(meta_dir, config_state_json, tomogram_full, interferograms):
    """Verifies the height convention matches the tomogram axis no worse than the slant one."""
    height_peaks, reference, _, _ = _sampled(meta_dir, config_state_json, tomogram_full, interferograms, "height")
    slant_peaks,  _,         _, _ = _sampled(meta_dir, config_state_json, tomogram_full, interferograms, "slant")

    height_error = float(np.median(np.abs(height_peaks - reference)))
    slant_error  = float(np.median(np.abs(slant_peaks  - reference)))

    assert height_error <= slant_error + 0.5


@pytest.mark.real_data
@pytest.mark.slow
def test_tomogram_peaks_reference_terrain_surface(config_state_json, tomogram_full):
    """Verifies the tomogram peak heights cluster around the terrain reference at zero metres."""
    n_elev  = tomogram_full.shape[0]
    z       = _height_axis(config_state_json, n_elev)

    az      = np.arange(0, tomogram_full.shape[1], 8)
    rg      = np.arange(0, tomogram_full.shape[2], 8)

    profile = np.abs(np.asarray(tomogram_full[:, az][:, :, rg])).astype(np.float64)
    peak_z  = z[profile.argmax(0)]

    assert -20.0 <= float(np.median(peak_z)) <= 20.0
    assert float(np.percentile(np.abs(peak_z), 90)) < 40.0
