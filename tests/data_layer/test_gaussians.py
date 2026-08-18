"""Tests for Gaussian mixture evaluation, curve reconstruction and parameter clamping."""

from __future__ import annotations

import numpy as np
import pytest

from tools.data.gaussians import GaussianMixture, GaussianReconstructor
def test_safe_sigma_sq_floor():
    """Verifies a zero sigma is lifted to twice the squared sigma floor."""
    out = GaussianMixture.safe_sigma_sq(np.array([0.0]))

    assert out[0] == 2.0 * GaussianMixture.SIGMA_FLOOR ** 2


def test_safe_sigma_sq_value():
    """Verifies the safe denominator is twice the squared sigma."""
    out = GaussianMixture.safe_sigma_sq(np.array([3.0]))

    assert np.isclose(out[0], 18.0)


def test_evaluate_batch_peak_at_mu():
    """Verifies a single Gaussian peaks at its mean with its amplitude over the height axis."""
    h    = np.linspace(-10.0, 10.0, 201).astype(np.float32)
    amps = np.array([[2.0]], dtype=np.float32)
    mus  = np.array([[0.0]], dtype=np.float32)
    sigs = np.array([[2.0]], dtype=np.float32)

    pred = GaussianMixture.evaluate_batch(h, amps, mus, sigs)

    assert pred.shape == (1, 201)
    assert np.isclose(pred[0].max(), 2.0, atol=1e-4)
    assert np.argmax(pred[0]) == 100


def test_evaluate_batch_sums_components():
    """Verifies overlapping components add up at the sampled height."""
    h    = np.array([0.0], dtype=np.float32)
    amps = np.array([[1.0, 3.0]], dtype=np.float32)
    mus  = np.array([[0.0, 0.0]], dtype=np.float32)
    sigs = np.array([[1.0, 1.0]], dtype=np.float32)

    pred = GaussianMixture.evaluate_batch(h, amps, mus, sigs)

    assert np.isclose(pred[0, 0], 4.0, atol=1e-5)


def test_evaluate_slice_matches_manual():
    """Verifies the single-height slice evaluation matches the analytic value per pixel."""
    params = np.zeros((6, 2, 2), dtype=np.float32)
    params[0] = 2.0
    params[1] = 1.0
    params[2] = 2.0

    out = GaussianMixture.evaluate_slice(params, h_val=1.0, n_gaussians=2)

    assert np.allclose(out, 2.0)


def test_evaluate_pixel_total_equals_sum_components():
    """Verifies the per-pixel total equals the sum of its component curves."""
    params = np.array([2.0, 0.0, 1.5, 1.0, 5.0, 2.0], dtype=np.float32)
    h      = np.linspace(-5.0, 10.0, 60)

    total, comps = GaussianMixture.evaluate_pixel(params, h, n_gaussians=2)

    assert len(comps) == 2
    assert np.allclose(total, comps[0] + comps[1])


def test_evaluate_pixel_peak_values():
    """Verifies the per-pixel curve peaks at the Gaussian amplitude."""
    params = np.array([3.0, 0.0, 1.0], dtype=np.float32)
    h      = np.linspace(-5.0, 5.0, 101)

    total, comps = GaussianMixture.evaluate_pixel(params, h, n_gaussians=1)

    assert np.isclose(total.max(), 3.0, atol=1e-4)


def test_reconstruct_batch_shape_and_dtype():
    """Verifies batch reconstruction returns float32 curves of shape (batch, heights)."""
    gauss = np.zeros((4, 2, 3), dtype=np.float32)
    gauss[:, :, 0] = 1.0
    gauss[:, :, 2] = 1.0
    x = np.linspace(-3.0, 3.0, 50).astype(np.float32)

    out = GaussianReconstructor.reconstruct_batch(gauss, x)

    assert out.shape == (4, 50)
    assert out.dtype == np.float32
def test_reconstructor_components_count():
    """Verifies the component list has one curve per Gaussian on the sampling axis."""
    params = np.array([1.0, 0.0, 1.0, 2.0, 3.0, 1.0], dtype=np.float32)
    x      = np.linspace(-5.0, 5.0, 20)

    comps = GaussianReconstructor.components(params, x, n_gaussians=2)

    assert len(comps) == 2
    assert all(c.shape == x.shape for c in comps)
@pytest.mark.real_data
def test_evaluate_slice_on_real_parameters(parameters, param_extraction_meta):
    """Verifies a real parameter window evaluates to a finite non-negative height slice."""
    k_max  = param_extraction_meta["k_max"]
    params = np.asarray(parameters[:, :16, :16]).astype(np.float32)

    out = GaussianMixture.evaluate_slice(params, h_val=10.0, n_gaussians=k_max)

    assert out.shape == (16, 16)
    assert np.all(np.isfinite(out))
    assert np.all(out >= 0.0)


@pytest.mark.real_data
def test_evaluate_pixel_on_real_parameters(parameters, param_extraction_meta):
    """Verifies a real pixel's components sum to the finite total curve."""
    k_max  = param_extraction_meta["k_max"]
    h_min, h_max = param_extraction_meta["height_range"]
    h      = np.linspace(h_min, h_max, 100)
    params = np.asarray(parameters[:, 0, 0]).astype(np.float32)

    total, comps = GaussianMixture.evaluate_pixel(params, h, n_gaussians=k_max)

    assert len(comps)  == k_max
    assert total.shape == (100,)
    assert np.allclose(total, sum(comps))
    assert np.all(np.isfinite(total))


@pytest.mark.real_data
def test_real_parameters_channel_count(parameters, param_extraction_meta):
    """Verifies the real parameter map has three channels per extracted Gaussian."""
    assert parameters.shape[0] == param_extraction_meta["k_max"] * 3
