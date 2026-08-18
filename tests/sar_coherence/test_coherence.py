"""Tests covering boxcar complex smoothing and interferometric coherence estimation."""

from __future__ import annotations

import numpy as np
import pytest

from tools.sar.coherence import ComplexSmoother, CoherenceEstimator


@pytest.fixture
def rng():
    """Returns a seeded NumPy random generator."""
    return np.random.default_rng(0)


@pytest.fixture
def slc(rng):
    """Returns a 48x48 complex64 SLC of circular Gaussian noise."""
    real = rng.normal(size=(48, 48))
    imag = rng.normal(size=(48, 48))
    return (real + 1j * imag).astype(np.complex64)


def test_smooth_real_matches_uniform_filter(rng):
    """Verifies smoothing a real field equals a uniform boxcar filter of the same window."""
    from scipy.ndimage import uniform_filter

    field    = rng.normal(size=(32, 32)).astype(np.float32)
    smoothed = ComplexSmoother((5, 5)).smooth(field)

    assert np.allclose(smoothed, uniform_filter(field, (5, 5)))


def test_smooth_complex_filters_real_and_imag_separately(slc):
    """Verifies complex smoothing filters the real and imaginary parts independently."""
    smoother = ComplexSmoother((5, 5))
    smoothed = smoother.smooth(slc)

    assert np.iscomplexobj(smoothed)
    assert np.allclose(smoothed.real, smoother.smooth(slc.real.copy()))
    assert np.allclose(smoothed.imag, smoother.smooth(slc.imag.copy()))


def test_identical_slcs_give_unit_coherence_zero_phase(slc):
    """Verifies a pair of identical SLCs yields unit coherence magnitude and zero phase."""
    magnitude, phase = CoherenceEstimator((7, 7)).estimate(slc, slc)

    assert magnitude.min() > 0.999
    assert np.abs(phase).max() < 1e-5


def test_constant_phase_offset_recovered(slc):
    """Verifies a constant phase offset in radians is recovered at unit coherence."""
    offset           = 0.8
    secondary        = (slc * np.exp(-1j * offset)).astype(np.complex64)
    magnitude, phase = CoherenceEstimator((7, 7)).estimate(slc, secondary)

    assert magnitude.min() > 0.999
    assert phase == pytest.approx(np.full_like(phase, offset), abs=1e-5)


def test_flattening_phase_removes_ramp(slc):
    """Verifies supplying the flattening phase removes a range phase ramp before averaging."""
    ramp             = np.linspace(0.0, 4.0 * np.pi, slc.shape[1])[None, :] * np.ones((slc.shape[0], 1))
    secondary        = (slc * np.exp(-1j * ramp)).astype(np.complex64)
    magnitude, phase = CoherenceEstimator((7, 7)).estimate(slc, secondary, flattening_phase=ramp)

    assert magnitude.min() > 0.99
    assert np.abs(phase).max() < 1e-4


def test_independent_noise_gives_low_coherence(rng, slc):
    """Verifies independent SLCs give low coherence away from the window border."""
    other = (rng.normal(size=slc.shape) + 1j * rng.normal(size=slc.shape)).astype(np.complex64)

    magnitude, _ = CoherenceEstimator((7, 7)).estimate(slc, other)
    interior     = magnitude[8:-8, 8:-8]

    assert interior.mean() < 0.5


def test_magnitude_bounded_zero_one(rng, slc):
    """Verifies coherence magnitude stays within [0, 1]."""
    other = (rng.normal(size=slc.shape) + 1j * rng.normal(size=slc.shape)).astype(np.complex64)

    magnitude, _ = CoherenceEstimator((3, 3)).estimate(slc, other)

    assert magnitude.min() >= 0.0
    assert magnitude.max() <= 1.0


def test_zero_amplitude_pixels_are_masked(slc):
    """Verifies pixels with zero secondary amplitude yield zero magnitude and phase."""
    secondary          = slc.copy()
    secondary[10, :]   = 0.0
    magnitude, phase   = CoherenceEstimator((5, 5)).estimate(slc, secondary)

    assert np.all(magnitude[10, :] == 0.0)
    assert np.all(phase[10, :]     == 0.0)


def test_all_zero_inputs_give_zero_coherence():
    """Verifies an all-zero pair yields zero magnitude and phase instead of NaN."""
    zeros = np.zeros((16, 16), dtype=np.complex64)

    magnitude, phase = CoherenceEstimator((5, 5)).estimate(zeros, zeros)

    assert np.all(magnitude == 0.0)
    assert np.all(phase     == 0.0)


def test_estimate_flattened_matches_deramped_pair(slc, rng):
    """Verifies estimating from amplitude plus flattened interferogram matches the SLC-pair estimate."""
    ramp          = np.linspace(0.0, 2.0 * np.pi, slc.shape[1])[None, :] * np.ones((slc.shape[0], 1))
    secondary     = (0.7 * slc * np.exp(-1j * ramp) + 0.3 * (rng.normal(size=slc.shape) + 1j * rng.normal(size=slc.shape))).astype(np.complex64)

    phasor        = slc * np.conj(secondary * np.exp(1j * ramp))
    phasor        = phasor / (np.abs(phasor) + 1e-30)
    interferogram = (np.abs(secondary) * phasor).astype(np.complex64)

    estimator                      = CoherenceEstimator((7, 7))
    magnitude, phase               = estimator.estimate_flattened(np.abs(slc).astype(np.float32), interferogram)
    reference_mag, reference_phase = estimator.estimate(slc, secondary, flattening_phase=ramp)

    assert magnitude == pytest.approx(reference_mag,   abs=1e-4)
    assert phase     == pytest.approx(reference_phase, abs=1e-3)
