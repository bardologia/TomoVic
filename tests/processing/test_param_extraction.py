"""Tests covering Gaussian parameter extraction from tomographic profiles.

Covers the extraction plan resolver, the JAX Adam fitting kernels and sigma
initialiser, the model-order (K) selection diagnostics, the fitting metrics and
plots, the kz resolution analysis, and the per-run inference pipeline.
"""

from __future__ import annotations

import importlib.util
import json

import matplotlib
matplotlib.use("Agg")

import numpy as np
import pytest

from pathlib import Path

from configuration.param_extraction import ExtractParamsEntryConfig
from pipelines.processing.param_extraction.metrics import (
    FittingMetricsCalculator,
    KSelectionDiagnostics,
    ContrastEstimator,
)
from pipelines.processing.param_extraction.pipeline   import ParameterExtractor
from pipelines.processing.param_extraction.inference  import ParamRunInferencePipeline
from pipelines.processing.param_extraction.queue      import ExtractionPlanResolver
from pipelines.processing.param_extraction.plots      import FittingResultPlotter
from pipelines.processing.param_extraction.resolution import ActiveGaussianTable, KzCoherenceModel, ResolutionAnalyzer
from tools.data.gaussians                             import GaussianMixture
from tools.data.preprocessing                         import ProfilePreprocessor
from tools.monitoring.logger                          import Logger


K_MAX            = 5
LAMBDA_K         = 0.01
HEIGHT_RANGE     = (-20.0, 80.0)
THRESHOLD_FACTOR = 0.25
TRUNCATION_INDEX = 170
ACTIVITY_THRESH  = 0.001

_HAS_JAX = importlib.util.find_spec("jax") is not None


def test_plan_resolver_expands_dataset_k_groups():
    """Verifies the resolver expands datasets and K values into groups holding the mode/lambda cross product."""
    entry = ExtractParamsEntryConfig(
        fit_k_values      = [3, 5],
        fit_lambda_values = [1e-2, 1e-1],
        fit_modes         = ["sigma", "sigma_amp", "sigma_amp_mu"],
    )
    dataset_dirs = [Path("/data/a"), Path("/data/b")]

    groups = ExtractionPlanResolver(entry, dataset_dirs).resolve()

    assert len(groups) == 2 * 2
    assert all(len(group.configs) == 2 * 3 for group in groups)

    configs = [config for group in groups for config in group.configs.values()]
    assert len(configs) == 2 * 2 * 2 * 3

    subdirs = {config.output_subdir_name for config in configs}
    assert len(subdirs) == 2 * 2 * 3


def test_each_k_group_owns_its_extraction_log(tmp_path, monkeypatch):
    """Verifies each K group writes its own param_extraction_k<K>.log file."""
    from pipelines.processing.param_extraction import pipeline as pipeline_module

    (tmp_path / "data").mkdir(parents=True)
    (tmp_path / "meta").mkdir(parents=True)
    np.save(tmp_path / "data" / "tomogram_full.npy", np.zeros((2, 2, 4), dtype=np.float32))
    (tmp_path / "meta" / "config_state.json").write_text(json.dumps({"tomogram_config": {"height_range": [-20.0, 80.0]}}), encoding="utf-8")

    monkeypatch.setattr(pipeline_module, "ParameterExtractor", lambda **kwargs: None)
    monkeypatch.setattr(pipeline_module, "ParameterIO",        lambda **kwargs: None)

    entry  = ExtractParamsEntryConfig(fit_k_values=[3, 5], fit_lambda_values=[1e-2], fit_modes=["sigma"])
    groups = ExtractionPlanResolver(entry, [tmp_path]).resolve()

    pipelines = [pipeline_module.ParamExtractionPipeline(group) for group in groups]

    for built in pipelines:
        built.logger.close()

    written = sorted(path.name for path in (tmp_path / "params" / "logs").iterdir())

    assert written == ["param_extraction_k3.log", "param_extraction_k5.log"]


def test_plan_resolver_group_carries_modes_and_lambdas():
    """Verifies a group exposes its K, modes, lambdas and one config per (mode, lambda) pair."""
    entry = ExtractParamsEntryConfig(fit_k_values=[4], fit_lambda_values=[1e-2, 1e-1], fit_modes=["sigma", "amp_mu"])

    group = ExtractionPlanResolver(entry, [Path("/data/a")]).resolve()[0]

    assert group.k_max         == 4
    assert group.modes         == ["sigma", "amp_mu"]
    assert group.lambda_values == [1e-2, 1e-1]
    assert set(group.configs)  == {("sigma", 1e-2), ("amp_mu", 1e-2), ("sigma", 1e-1), ("amp_mu", 1e-1)}


def test_plan_resolver_maps_modes_to_free_flags():
    """Verifies mode names map onto the fit_sigma/fit_amplitude/fit_mean free-parameter flags."""
    entry = ExtractParamsEntryConfig(fit_k_values=[4], fit_lambda_values=[1e-2], fit_modes=["sigma", "amp_mu", "sigma_amp_mu"])

    group = ExtractionPlanResolver(entry, [Path("/data/a")]).resolve()[0]
    flags = [(c.fit_settings.fit_config.fit_sigma, c.fit_settings.fit_config.fit_amplitude, c.fit_settings.fit_config.fit_mean) for c in (group.configs[(mode, 1e-2)] for mode in group.modes)]

    assert flags == [(True, False, False), (False, True, True), (True, True, True)]


def test_plan_resolver_passes_fit_constants_and_adam_settings():
    """Verifies entry-level fit constants, Adam settings and batch sizes reach the shared plan."""
    entry = ExtractParamsEntryConfig(
        fit_k_values           = [3],
        fit_lambda_values      = [1e-2],
        fit_modes              = ["sigma"],
        fit_threshold_factor   = 0.4,
        fit_truncation_index   = 120,
        fit_prominence_frac    = 0.1,
        fit_activity_threshold = 5e-3,
        fit_sigma_init_divisor = 2.0,
        adam_steps             = 500,
        adam_lr                = 0.05,
        range_batch_size       = 100,
        gpu_pixel_batch_size   = 4096,
    )

    plan    = ExtractionPlanResolver(entry, [Path("/data/a")]).resolve()[0].shared
    fit_cfg = plan.fit_settings.fit_config

    assert fit_cfg.threshold_factor   == 0.4
    assert fit_cfg.truncation_index   == 120
    assert fit_cfg.prominence_frac    == 0.1
    assert fit_cfg.activity_threshold == 5e-3
    assert fit_cfg.sigma_init_divisor == 2.0
    assert plan.adam_steps            == 500
    assert plan.adam_lr               == 0.05
    assert plan.range_batch_size      == 100
    assert plan.gpu_pixel_batch_size  == 4096


def test_plan_resolver_rejects_unknown_mode():
    """Verifies an unrecognised fit mode raises ValueError."""
    entry = ExtractParamsEntryConfig(fit_k_values=[4], fit_lambda_values=[1e-2], fit_modes=["sigma", "quartic"])
    with pytest.raises(ValueError):
        ExtractionPlanResolver(entry, [Path("/data/a")]).resolve()


def test_plan_resolver_rejects_empty_axis():
    """Verifies an empty sweep axis raises ValueError."""
    entry = ExtractParamsEntryConfig(fit_k_values=[])
    with pytest.raises(ValueError):
        ExtractionPlanResolver(entry, [Path("/data/a")]).resolve()


def test_plan_resolver_rejects_fixed_suffix_for_multi_permutation():
    """Verifies a fixed output suffix is refused when the sweep has several permutations."""
    entry = ExtractParamsEntryConfig(fit_k_values=[3, 5], output_suffix="fixed")
    with pytest.raises(ValueError):
        ExtractionPlanResolver(entry, [Path("/data/a")]).resolve()


def test_plan_resolver_allows_fixed_suffix_for_single_permutation():
    """Verifies a single-permutation sweep may keep an explicit output suffix."""
    entry  = ExtractParamsEntryConfig(fit_k_values=[5], fit_lambda_values=[1e-2], fit_modes=["sigma"], output_suffix="fixed")
    groups = ExtractionPlanResolver(entry, [Path("/data/a")]).resolve()
    assert len(groups) == 1
    assert len(groups[0].configs) == 1
    assert groups[0].shared.output_suffix_value == "fixed"


def test_plan_resolver_allows_fixed_suffix_across_datasets():
    """Verifies a fixed suffix is shared across datasets while output directories stay distinct."""
    entry  = ExtractParamsEntryConfig(fit_k_values=[5], fit_lambda_values=[1e-2], fit_modes=["sigma"], output_suffix="fixed")
    groups = ExtractionPlanResolver(entry, [Path("/data/a"), Path("/data/b"), Path("/data/c")]).resolve()

    assert len(groups) == 3
    assert {group.shared.output_suffix_value for group in groups} == {"fixed"}
    assert len({group.shared.output_directory for group in groups}) == 3


def test_sigma_guess_matches_the_initialiser_sigmas():
    """Verifies the standalone sigma guess equals the sigmas the peak initialiser emits and stays below the height step."""
    from pipelines.processing.param_extraction.sigma.initialiser import PeakInitialiser

    height_axis = np.linspace(HEIGHT_RANGE[0], HEIGHT_RANGE[1], 150, dtype=np.float32)
    profiles    = np.zeros((4, 150), dtype=np.float32)

    initialiser = PeakInitialiser(n_workers=1)
    guess       = PeakInitialiser.sigma_guess(height_axis, K_MAX, 4.0)
    _, _, sigs  = initialiser.run(profiles, height_axis, K_MAX, sigma_divisor=4.0)

    assert np.allclose(sigs, np.float32(guess))
    assert guess < float(height_axis[1] - height_axis[0])


@pytest.mark.skipif(not _HAS_JAX, reason="jax not installed in this environment")
def test_clamped_sigma_init_divisor_is_reported(tmp_path):
    """Verifies a sigma_init_divisor clamped during data preparation is reported as a warning."""
    from tests.conftest import SilentLogger
    from pipelines.processing.param_extraction.sigma.extractor   import SigmaFittingExtractor
    from pipelines.processing.param_extraction.sigma.initialiser import PeakInitialiser

    class WarningRecorder(SilentLogger):
        """Silent logger that records warning messages for assertions.

        Attributes:
            warnings: Messages passed to warning().
        """

        def __init__(self):
            """Initialises the empty warning buffer."""
            self.warnings = []

        def warning(self, message):
            """Records a warning message."""
            self.warnings.append(message)

    tomo_path = tmp_path / "tomo.npy"
    np.save(tomo_path, np.zeros((150, 2, 2), dtype=np.float32))

    recorder  = WarningRecorder()
    extractor = SigmaFittingExtractor(
        logger             = recorder,
        modes              = ["sigma"],
        lambda_values      = [LAMBDA_K],
        k_max              = K_MAX,
        sigma_init_divisor = 4.0,
        peak_initialiser   = PeakInitialiser(n_workers=1),
    )
    extractor._prepare_data(tomo_path, HEIGHT_RANGE)

    assert any("sigma_init_divisor 4.0" in message for message in recorder.warnings)


@pytest.mark.skipif(not _HAS_JAX, reason="jax not installed in this environment")
def test_scoring_throttle_reraises_a_failed_future():
    """Verifies the scoring throttle re-raises the exception of a failed background future."""
    from concurrent.futures import ThreadPoolExecutor
    from pipelines.processing.param_extraction.sigma.extractor import SigmaFittingExtractor

    def boom():
        """Raises RuntimeError to produce a failed future."""
        raise RuntimeError("scoring failed")

    with ThreadPoolExecutor(max_workers=1) as pool:
        futures = [pool.submit(boom)]
        futures[0].exception()

        with pytest.raises(RuntimeError, match="scoring failed"):
            SigmaFittingExtractor._throttle_scorings(futures, SigmaFittingExtractor.MAX_PENDING_SCORINGS)


@pytest.mark.skipif(not _HAS_JAX, reason="jax not installed in this environment")
def test_kernel_masks_freeze_parameter_groups():
    """Verifies the Adam kernel masks hold amplitude, mean or sigma fixed while the unmasked groups move."""
    import jax.numpy as jnp
    from pipelines.processing.param_extraction.sigma.kernels import SigmaAdamKernel

    H      = 60
    height = np.linspace(-10.0, 30.0, H, dtype=np.float32)
    target = np.exp(-((height - 5.0) ** 2) / (2.0 * 4.0 ** 2)).astype(np.float32)
    prof   = np.tile(target[None, :], (4, 1))

    amps = np.full((4, 1), 0.6, dtype=np.float32)
    mus  = np.full((4, 1), 2.0, dtype=np.float32)
    sigs = np.full((4, 1), 6.0, dtype=np.float32)

    kernel = SigmaAdamKernel()

    def run(amp_on, mu_on, sigma_on):
        """Runs the Adam kernel with the given amplitude/mean/sigma free flags and returns the fitted arrays.

        Args:
            amp_on: 1.0 to let amplitudes move, 0.0 to freeze them.
            mu_on: 1.0 to let means move, 0.0 to freeze them.
            sigma_on: 1.0 to let sigmas move, 0.0 to freeze them.

        Returns:
            List of amplitudes, means and sigmas of shape (pixels, K) plus per-pixel errors of shape (pixels,).
        """
        out = kernel(
            jnp.array(amps), jnp.array(mus), jnp.array(sigs),
            jnp.array(height), jnp.array(prof),
            jnp.float32(amp_on), jnp.float32(mu_on), jnp.float32(sigma_on),
            jnp.float32(height[0]), jnp.float32(height[-1]),
            jnp.float32(0.5), jnp.float32(20.0),
            50, 0.05, 0.9, 0.999,
        )
        return [np.array(o) for o in out]

    a_f, m_f, s_f, e_f = run(1.0, 1.0, 0.0)
    assert np.allclose(s_f, sigs)
    assert not np.allclose(a_f, amps)
    assert not np.allclose(m_f, mus)
    assert e_f.shape == (4,)
    assert np.all(np.isfinite(e_f))

    a_f, m_f, s_f, e_f = run(0.0, 0.0, 1.0)
    assert np.allclose(a_f, amps)
    assert np.allclose(m_f, mus)
    assert not np.allclose(s_f, sigs)

    a_f, m_f, s_f, e_f = run(0.0, 1.0, 0.0)
    assert np.allclose(a_f, amps)
    assert np.allclose(s_f, sigs)
    assert not np.allclose(m_f, mus)


@pytest.mark.skipif(not _HAS_JAX, reason="jax not installed in this environment")
def test_group_extractor_shares_fits_across_modes_and_lambdas(logger, tmp_path):
    """Verifies one extractor run yields every (mode, lambda) result, with lambda changing only the penalised score."""
    rng      = np.random.default_rng(0)
    H, Az, R = 40, 6, 4
    height   = np.linspace(-10.0, 30.0, H, dtype=np.float32)
    layer    = np.exp(-((height - 8.0) ** 2) / (2.0 * 3.0 ** 2)).astype(np.float32)
    amps     = rng.uniform(0.5, 1.0, size=(Az, R)).astype(np.float32)
    tomo     = layer[:, None, None] * amps[None, :, :]

    tomo_path = tmp_path / "tomo.npy"
    np.save(tomo_path, tomo)

    extractor = ParameterExtractor(
        logger               = logger,
        modes                = ["sigma", "sigma_amp"],
        lambda_values        = [1e-2, 1e-1],
        k_max                = 2,
        threshold_factor     = 0.0,
        truncation_index     = H,
        prominence_frac      = 0.05,
        sigma_init_divisor   = 4.0,
        activity_threshold   = ACTIVITY_THRESH,
        range_batch_size     = 2,
        adam_steps           = 40,
        adam_lr              = 0.1,
        gpu_pixel_batch_size = 64,
        init_workers         = 1,
    )
    results = extractor.run(tomo_path, (-10.0, 30.0))

    assert set(results) == {("sigma", 1e-2), ("sigma", 1e-1), ("sigma_amp", 1e-2), ("sigma_amp", 1e-1)}
    assert all(params.shape == (6, Az, R) for params, _ in results.values())

    for mode in ("sigma", "sigma_amp"):
        lo = results[(mode, 1e-2)][1]
        hi = results[(mode, 1e-1)][1]

        assert np.allclose(lo["mse_per_k"], hi["mse_per_k"], equal_nan=True)
        assert not np.allclose(lo["penalised_per_k"], hi["penalised_per_k"], equal_nan=True)
        assert float(lo["lambda_k"]) == pytest.approx(1e-2)
        assert float(hi["lambda_k"]) == pytest.approx(1e-1)

    sigma_only, sigma_amp = results[("sigma", 1e-2)][1], results[("sigma_amp", 1e-2)][1]
    assert not np.allclose(sigma_only["mse_per_k"], sigma_amp["mse_per_k"], equal_nan=True)


@pytest.fixture(scope="module")
def logger(tmp_path_factory):
    """Yields a module-scoped file Logger writing into a temporary directory."""
    log = Logger(log_dir=str(tmp_path_factory.mktemp("pe_logs")), name="test_pe", level="ERROR")

    yield log

    log.close()


@pytest.fixture
def small_metadata():
    """Returns minimal extraction metadata carrying the height range in metres."""
    return {"height_range": list(HEIGHT_RANGE)}


def _height_axis(H):
    """Returns the elevation axis in metres sampled at H points over HEIGHT_RANGE."""
    return np.linspace(HEIGHT_RANGE[0], HEIGHT_RANGE[1], H, dtype=np.float32)


@pytest.mark.real_data
def test_parameters_layout(parameters, param_extraction_meta):
    """Verifies the stored parameter cube has 3*K channels over the full azimuth/range grid."""
    assert param_extraction_meta["k_max"] == K_MAX
    assert parameters.shape[0]            == 3 * K_MAX
    assert parameters.shape[1:]           == (1000, 500)


@pytest.mark.real_data
def test_diagnostics_layout(fit_diagnostics):
    """Verifies the diagnostics arrays carry per-K maps, a best-K map and the recorded lambda."""
    assert fit_diagnostics["mse_per_k"].shape       == (K_MAX, 1000, 500)
    assert fit_diagnostics["penalised_per_k"].shape == (K_MAX, 1000, 500)
    assert fit_diagnostics["best_k_map"].shape      == (1000, 500)
    assert float(fit_diagnostics["lambda_k"])       == pytest.approx(LAMBDA_K, rel=1e-5)


@pytest.mark.real_data
def test_best_k_in_valid_range(fit_diagnostics):
    """Verifies the best-K map stays within 0 (inactive) and K_MAX."""
    bk = fit_diagnostics["best_k_map"]

    assert bk.min() >= 0
    assert bk.max() <= K_MAX


@pytest.mark.real_data
def test_parameters_finite(parameters):
    """Verifies a parameter window contains only finite values."""
    w = np.array(parameters[:, :300, :300])

    assert np.isfinite(w).all()


@pytest.mark.real_data
def test_active_mu_in_physical_height_range(parameters):
    """Verifies means of active Gaussians lie inside the configured height range in metres."""
    w    = np.array(parameters)
    amps = w[0::3]
    mus  = w[1::3]
    act  = amps > ACTIVITY_THRESH

    assert mus[act].min() >= HEIGHT_RANGE[0] - 1e-2
    assert mus[act].max() <= HEIGHT_RANGE[1] + 1e-2


@pytest.mark.real_data
def test_active_sigma_within_bounds(parameters):
    """Verifies sigmas of active Gaussians lie between the height step and half the height span in metres."""
    H      = 150
    h_span = HEIGHT_RANGE[1] - HEIGHT_RANGE[0]
    dh     = h_span / (H - 1)
    w      = np.array(parameters)
    amps   = w[0::3]
    sigs   = w[2::3]
    act    = amps > ACTIVITY_THRESH

    assert sigs[act].min() >= dh - 1e-3
    assert sigs[act].max() <= h_span / 2.0 + 1e-3


@pytest.mark.real_data
def test_amplitudes_nonnegative(parameters):
    """Verifies all fitted Gaussian amplitudes are non-negative."""
    w    = np.array(parameters)
    amps = w[0::3]

    assert amps.min() >= 0.0


@pytest.mark.real_data
def test_gaussians_sorted_by_mu(parameters):
    """Verifies active Gaussians are stored in ascending order of their means."""
    w    = np.array(parameters)
    amps = w[0::3]
    mus  = w[1::3]

    sort_keys   = np.where(amps > ACTIVITY_THRESH, mus, np.inf)
    finite_pair = np.isfinite(sort_keys[:-1]) & np.isfinite(sort_keys[1:])
    lower       = np.where(finite_pair, sort_keys[:-1], 0.0)
    upper       = np.where(finite_pair, sort_keys[1:],  0.0)
    violations  = (upper - lower < -1e-3) & finite_pair

    assert int(violations.sum()) == 0


@pytest.mark.real_data
def test_penalised_equals_mse_plus_penalty(fit_diagnostics):
    """Verifies the penalised score never falls below the plain MSE on active pixels."""
    mse = fit_diagnostics["mse_per_k"]
    pen = fit_diagnostics["penalised_per_k"]
    bk  = fit_diagnostics["best_k_map"]
    act = bk > 0

    penalty = (pen - mse)[:, act]

    assert np.all(penalty >= -1e-6)


@pytest.mark.real_data
def test_penalty_per_k_bounded_by_lambda(fit_diagnostics):
    """Verifies the per-K penalty never exceeds lambda times K."""
    mse = fit_diagnostics["mse_per_k"]
    pen = fit_diagnostics["penalised_per_k"]
    bk  = fit_diagnostics["best_k_map"]
    act = bk > 0

    for k in range(K_MAX):
        penalty_k = (pen[k] - mse[k])[act]

        assert np.nanmax(penalty_k) <= LAMBDA_K * (k + 1) + 1e-5


@pytest.mark.real_data
def test_k1_penalty_equals_lambda(fit_diagnostics):
    """Verifies the K=1 penalty equals the configured lambda."""
    mse = fit_diagnostics["mse_per_k"]
    pen = fit_diagnostics["penalised_per_k"]
    bk  = fit_diagnostics["best_k_map"]
    act = bk > 0

    penalty_k1 = (pen[0] - mse[0])[act]

    assert np.nanmax(penalty_k1) == pytest.approx(LAMBDA_K, abs=1e-5)


@pytest.mark.real_data
def test_best_k_is_argmin_of_penalised(fit_diagnostics):
    """Verifies the best-K map is the argmin of the penalised score over K on active pixels."""
    pen = fit_diagnostics["penalised_per_k"]
    bk  = fit_diagnostics["best_k_map"]
    act = bk > 0

    argmin = pen[:, act].argmin(axis=0) + 1

    assert np.array_equal(argmin, bk[act])


@pytest.mark.real_data
def test_inactive_pixels_have_zero_best_k_and_nan_mse(fit_diagnostics):
    """Verifies inactive pixels carry best-K zero and NaN MSE for every K."""
    mse   = fit_diagnostics["mse_per_k"]
    bk    = fit_diagnostics["best_k_map"]
    inact = bk == 0

    assert np.all(bk[inact] == 0)
    assert np.isnan(mse[:, inact]).all()


@pytest.mark.real_data
def test_stored_mse_matches_reconstruction_from_params(tomogram_full, parameters, fit_diagnostics):
    """Verifies the stored best-K MSE matches a reconstruction from the saved Gaussian parameters."""
    a0, a1, r0, r1 = 0, 40, 0, 40
    H              = tomogram_full.shape[0]
    height         = _height_axis(H)

    raw = np.abs(np.array(tomogram_full[:, a0:a1, r0:r1])).astype(np.float32)
    raw = ProfilePreprocessor.apply(raw, THRESHOLD_FACTOR, TRUNCATION_INDEX)

    profiles = raw.transpose(2, 1, 0).reshape((r1 - r0) * (a1 - a0), H)
    scale    = profiles.max(axis=1)
    active   = scale > ACTIVITY_THRESH

    parw = np.array(parameters[:, a0:a1, r0:r1])
    amps = parw[0::3].reshape(K_MAX, -1).T
    mus  = parw[1::3].reshape(K_MAX, -1).T
    sigs = parw[2::3].reshape(K_MAX, -1).T

    pred       = GaussianMixture.evaluate_batch(height, amps, mus, sigs)
    safe_scale = np.where(active, scale, 1.0)
    pred_norm  = pred     / safe_scale[:, None]
    prof_norm  = profiles / safe_scale[:, None]
    mse_recon  = ((pred_norm - prof_norm) ** 2).mean(axis=1)

    bk_flat  = fit_diagnostics["best_k_map"][a0:a1, r0:r1].T.reshape(-1)
    mse_w    = fit_diagnostics["mse_per_k"][:, a0:a1, r0:r1].transpose(0, 2, 1).reshape(K_MAX, -1)
    idx      = np.clip(bk_flat - 1, 0, K_MAX - 1)
    mse_best = mse_w[idx, np.arange(len(idx))]

    mask = active & (bk_flat > 0)

    assert mask.sum() > 0
    assert np.nanmedian(np.abs(mse_recon[mask] - mse_best[mask])) < 5e-3


@pytest.mark.real_data
def test_snr_estimator_runs(tomogram_full, logger):
    """Verifies the contrast estimator returns a non-negative per-pixel map over the window."""
    win = np.array(tomogram_full[:, :32, :32])
    snr = ContrastEstimator(logger).run(win)

    assert snr.shape == (32, 32)
    finite = snr[np.isfinite(snr)]
    assert finite.size > 0
    assert finite.min() >= 0.0


def test_r2_statistics_ignore_never_fitted_pixels(logger, tmp_path):
    """Verifies R2 statistics count only pixels that carry a fitted Gaussian."""
    n_elev, n_az, n_rg = 32, 4, 4

    height_axis = np.linspace(HEIGHT_RANGE[0], HEIGHT_RANGE[1], n_elev, dtype=np.float32)
    profile     = np.exp(-0.5 * ((height_axis - 30.0) / 6.0) ** 2).astype(np.float32)

    tomogram = np.tile(profile[:, None, None], (1, n_az, n_rg)).astype(np.complex64)
    params   = np.zeros((3 * K_MAX, n_az, n_rg), dtype=np.float32)

    params[0, 0, 0] = 1.0
    params[1, 0, 0] = 30.0
    params[2, 0, 0] = 6.0

    tomo_path = tmp_path / "tomo.npy"
    np.save(tomo_path, tomogram)

    calc = FittingMetricsCalculator(
        n_gaussians      = K_MAX,
        logger           = logger,
        threshold_factor = THRESHOLD_FACTOR,
        truncation_index = TRUNCATION_INDEX,
        amp_threshold    = ACTIVITY_THRESH,
    )
    out = calc.run(params, {"height_range": list(HEIGHT_RANGE)}, tomo_path)

    r2_map  = out["r2_map"]
    summary = out["global_summary"]

    assert np.isfinite(r2_map[0, 0])
    assert np.isnan(r2_map[1:, :]).all()
    assert summary["n_fitted"] == 1.0
    assert summary["n_pixels"] == float(n_az * n_rg)
    assert summary["r2_mean"] == pytest.approx(float(r2_map[0, 0]), abs=1e-6)
    assert summary["r2_neg_frac"] == 0.0


@pytest.mark.real_data
def test_k_selection_diagnostics_runs(fit_diagnostics, logger):
    """Verifies the K-selection diagnostics emit the margin map and active-pixel summary."""
    diag = {
        "mse_per_k"       : fit_diagnostics["mse_per_k"][:, :64, :64],
        "penalised_per_k" : fit_diagnostics["penalised_per_k"][:, :64, :64],
        "best_k_map"      : fit_diagnostics["best_k_map"][:64, :64],
    }
    maps, summary = KSelectionDiagnostics(k_max=K_MAX, logger=logger).run(diag)

    assert "k_margin_second_map" in maps
    assert "n_active_pixels" in summary
    assert summary["n_active_pixels"] >= 0.0


@pytest.mark.real_data
def test_metrics_calculator_runs_on_window(tomogram_full, parameters, fit_diagnostics, small_metadata, logger, tmp_path):
    """Verifies the metrics calculator returns window-shaped R2 and activity maps with a global summary."""
    a0, a1, r0, r1 = 0, 48, 0, 48

    tomo_win  = np.array(tomogram_full[:, a0:a1, r0:r1])
    tomo_path = tmp_path / "tomo.npy"
    np.save(tomo_path, tomo_win)

    parw = np.ascontiguousarray(np.array(parameters[:, a0:a1, r0:r1]))
    diag = {
        "mse_per_k"       : fit_diagnostics["mse_per_k"][:, a0:a1, r0:r1],
        "penalised_per_k" : fit_diagnostics["penalised_per_k"][:, a0:a1, r0:r1],
        "best_k_map"      : fit_diagnostics["best_k_map"][a0:a1, r0:r1],
        "lambda_k"        : fit_diagnostics["lambda_k"],
    }

    calc = FittingMetricsCalculator(
        n_gaussians      = K_MAX,
        logger           = logger,
        threshold_factor = THRESHOLD_FACTOR,
        truncation_index = TRUNCATION_INDEX,
        amp_threshold    = ACTIVITY_THRESH,
    )
    out = calc.run(parw, small_metadata, tomo_path, diag)

    assert out["r2_map"].shape       == (a1 - a0, r1 - r0)
    assert out["activity_map"].shape == (a1 - a0, r1 - r0)
    assert out["global_summary"]["n_gaussians"] == float(K_MAX)
    assert out["activity_map"].max() <= K_MAX


@pytest.mark.real_data
def test_activity_map_counts_active_components(parameters, logger):
    """Verifies the activity map counts Gaussians whose amplitude reaches the activity threshold."""
    a0, a1, r0, r1 = 0, 60, 0, 60
    parw           = np.array(parameters[:, a0:a1, r0:r1])

    calc = FittingMetricsCalculator(
        n_gaussians      = K_MAX,
        logger           = logger,
        threshold_factor = THRESHOLD_FACTOR,
        truncation_index = TRUNCATION_INDEX,
        amp_threshold    = ACTIVITY_THRESH,
    )
    activity = calc._compute_activity_map(parw)

    expected = (parw[0::3] >= ACTIVITY_THRESH).sum(axis=0)

    assert np.array_equal(activity, expected)


@pytest.mark.real_data
def test_fitting_result_plotter_smoke(tomogram_full, parameters, fit_diagnostics, small_metadata, logger, tmp_path):
    """Verifies the fitting result plotter writes every figure it reports."""
    a0, a1, r0, r1 = 0, 48, 0, 48

    tomo_path = tmp_path / "tomo.npy"
    np.save(tomo_path, np.array(tomogram_full[:, a0:a1, r0:r1]))

    parw = np.ascontiguousarray(np.array(parameters[:, a0:a1, r0:r1]))
    diag = {
        "mse_per_k"       : fit_diagnostics["mse_per_k"][:, a0:a1, r0:r1],
        "penalised_per_k" : fit_diagnostics["penalised_per_k"][:, a0:a1, r0:r1],
        "best_k_map"      : fit_diagnostics["best_k_map"][a0:a1, r0:r1],
        "lambda_k"        : fit_diagnostics["lambda_k"],
    }

    calc = FittingMetricsCalculator(
        n_gaussians      = K_MAX,
        logger           = logger,
        threshold_factor = THRESHOLD_FACTOR,
        truncation_index = TRUNCATION_INDEX,
        amp_threshold    = ACTIVITY_THRESH,
    )
    metrics_dict = calc.run(parw, small_metadata, tomo_path, diag)

    plotter = FittingResultPlotter(
        output_directory = tmp_path / "out",
        n_gaussians      = K_MAX,
        logger           = logger,
        threshold_factor = THRESHOLD_FACTOR,
        truncation_index = TRUNCATION_INDEX,
        fig_dpi          = 40,
        save_dpi         = 40,
        n_fits_per_k     = 2,
        amp_threshold    = ACTIVITY_THRESH,
    )
    saved = plotter.run(parw, metrics_dict, small_metadata, tomo_path)

    assert len(saved) > 0
    assert all(p.is_file() for p in saved.values())


def test_result_plotter_drives_sub_plotters_through_public_methods():
    """Verifies the result plotter never calls private methods of its sub-plotters."""
    import inspect
    import re

    from pipelines.processing.param_extraction.plots.result import FittingResultPlotter

    source  = inspect.getsource(FittingResultPlotter)
    private = re.findall(r"self\.(?:spatial_plotter|distribution_plotter|metrics_bar_plotter|example_fit_plotter)\._\w+", source)

    assert private == []


def _params_with_empty_pixel(k_max):
    """Returns a (3*K, 2, 2) parameter cube whose last pixel holds only a sub-threshold amplitude."""
    params = np.zeros((3 * k_max, 2, 2), dtype=np.float64)

    params[0, ...] = 1.0
    params[1, ...] = 10.0
    params[2, ...] = 2.0
    params[3, ...] = 0.5
    params[4, ...] = 30.0
    params[5, ...] = 3.0

    params[:, 1, 1] = 0.0
    params[0, 1, 1] = ACTIVITY_THRESH / 10.0

    return params


def test_active_gaussian_table_drops_pixels_without_active_gaussians():
    """Verifies the active-Gaussian table drops pixels without active components and reports positive extents."""
    k_max = 2
    table = ActiveGaussianTable(_params_with_empty_pixel(k_max), k_max, ACTIVITY_THRESH)

    assert table.n_pixels     == 3
    assert table.active.shape == (k_max, 3)
    assert table.active.any(axis=0).all()

    extents = table.vertical_extents()

    assert extents.shape == (3,)
    assert np.isfinite(extents).all()
    assert (extents > 0.0).all()


def test_kz_coherence_model_has_no_zero_weight_pixels_after_masking():
    """Verifies modelled coherence magnitudes stay within [0, 1] and peak above 0.5 for every pixel."""
    k_max = 2
    table = ActiveGaussianTable(_params_with_empty_pixel(k_max), k_max, ACTIVITY_THRESH)

    kz_grid    = np.linspace(0.1, 5.0, 32)
    magnitudes = KzCoherenceModel(table).magnitudes(kz_grid, np.arange(table.n_pixels))

    assert np.isfinite(magnitudes).all()
    assert (magnitudes <= 1.0).all()
    assert (magnitudes.max(axis=0) > 0.5).all()


def _resolution_analyzer(tmp_path, logger):
    """Returns a ResolutionAnalyzer over a 2x2 single-Gaussian parameter cube with sigmas 0.5 to 4 m."""
    sigmas = np.array([0.5, 1.0, 2.0, 4.0], dtype=np.float32).reshape(1, 2, 2)
    params = np.concatenate([np.ones((1, 2, 2), dtype=np.float32), np.zeros((1, 2, 2), dtype=np.float32), sigmas], axis=0)

    return ResolutionAnalyzer(params, {"k_max": 1, "activity_threshold": ACTIVITY_THRESH}, tmp_path, logger, kz_grid_max=1.0, kz_grid_points=4)


def test_aliasing_curve_matches_the_broadcast_fraction(tmp_path, logger):
    """Verifies the aliasing curve equals the fraction of vertical extents exceeding the 2*pi/kz ambiguity height."""
    analyzer          = _resolution_analyzer(tmp_path, logger)
    fraction, extents = analyzer.aliasing_curve()

    expected = (extents[None, :] > (2.0 * np.pi / analyzer.kz_grid)[:, None]).mean(axis=1)

    assert fraction.dtype == np.float64
    assert np.allclose(fraction, expected)


@pytest.mark.parametrize("n_pixels", [250_000, 399_999, 400_001, 1_000_000])
def test_pixel_subsample_never_exceeds_the_quantile_cap(tmp_path, logger, n_pixels):
    """Verifies the pixel subsample stays within the quantile-computation cap for any pixel count."""
    analyzer = _resolution_analyzer(tmp_path, logger)
    analyzer.table.n_pixels = n_pixels

    assert analyzer.pixel_subsample().shape[0] <= ResolutionAnalyzer.MAX_QUANTILE_PIXELS


def test_pass_ranking_evaluates_exactly_and_ranks_a_below_floor_pass_last(tmp_path, logger):
    """Verifies pass ranking matches the exact error model and a near-zero-baseline pass ranks last."""
    analyzer      = _resolution_analyzer(tmp_path, logger)
    pixel_indices = analyzer.pixel_subsample()
    pass_table    = {"FL01_PS04": float(analyzer.kz_grid[-2]), "FL02_PS03": float(analyzer.kz_grid[0]) / 5.0}

    ranked = analyzer.pass_ranking(pixel_indices, pass_table)

    kz_values  = np.array(list(pass_table.values()), dtype=np.float64)
    _, errors  = analyzer.error_samples(kz_values, pixel_indices)
    expected   = np.median(errors, axis=1)

    assert [row["label"] for row in ranked] == ["FL01_PS04", "FL02_PS03"]
    assert ranked[0]["predicted_height_error"] == pytest.approx(float(expected[0]))
    assert ranked[1]["predicted_height_error"] == pytest.approx(float(expected[1]))
    assert ranked[1]["predicted_height_error"] > ranked[0]["predicted_height_error"]


def test_pass_ranking_rejects_a_non_positive_kz(tmp_path, logger):
    """Verifies pass ranking raises for a candidate whose mean absolute kz is zero."""
    analyzer      = _resolution_analyzer(tmp_path, logger)
    pixel_indices = analyzer.pixel_subsample()

    with pytest.raises(ValueError, match="non-positive mean absolute kz"):
        analyzer.pass_ranking(pixel_indices, {"FL01_PS09": 0.0})


def test_pass_rug_legend_names_only_the_flights_present(logger):
    """Verifies the pass rug legend lists one entry per flight, not per pass."""
    import matplotlib.pyplot as plt
    from pipelines.processing.param_extraction.plots import ResolutionPlotter

    arrays = {
        "pass_labels" : np.array(["XY07_PS01", "XY07_PS02", "ZZ09_PS03"]),
        "pass_kz"     : np.array([0.5, 1.0, 2.0]),
    }

    fig, axes = plt.subplots()
    ResolutionPlotter(logger=logger)._pass_rug(axes, arrays)
    labels = [text.get_text() for text in axes.get_legend().get_texts()]
    plt.close(fig)

    assert labels == ["XY07 pass", "ZZ09 pass"]


def test_active_gaussian_table_all_empty_raises():
    """Verifies an all-inactive parameter cube raises ValueError."""
    k_max = 2

    with pytest.raises(ValueError, match="No pixel carries an active Gaussian"):
        ActiveGaussianTable(np.zeros((3 * k_max, 2, 2)), k_max, ACTIVITY_THRESH)


def _write_synthetic_geometry_field(dataset_dir):
    """Writes a small three-track GeometryField into the dataset meta directory."""
    from tools.sar.geometry_field import GeometryField

    n_azimuth, n_range = 8, 6
    field = GeometryField(
        labels        = ["FL01_PS02", "FL01_PS04", "FL02_PS03"],
        reference     = "FL01_PS02",
        wavelength    = 0.2262,
        azimuth_start = 0,
        range_start   = 0,
        look_angle    = np.full(n_range, 0.6),
        slant_range   = np.linspace(3600.0, 3900.0, n_range),
        baseline_h    = np.vstack([np.zeros(n_azimuth), np.full(n_azimuth, 15.0), np.full(n_azimuth, 1.6)]),
        baseline_v    = np.vstack([np.zeros(n_azimuth), np.full(n_azimuth, -1.0), np.full(n_azimuth, -0.3)]),
    )
    field.save(dataset_dir / "meta" / GeometryField.FILENAME)


@pytest.mark.real_data
def test_param_run_inference_pipeline_smoke(tomogram_full, parameters, fit_diagnostics, logger, tmp_path):
    """Verifies the per-run inference pipeline writes the metrics summary, resolution curves and plots."""
    a0, a1, r0, r1 = 0, 48, 0, 48

    dataset_dir = tmp_path / "dataset"
    run_dir     = dataset_dir / "params" / "params_run"
    run_dir.mkdir(parents=True)

    _write_synthetic_geometry_field(dataset_dir)

    tomo_path = tmp_path / "tomo.npy"
    np.save(tomo_path, np.array(tomogram_full[:, a0:a1, r0:r1]))

    np.save(run_dir / "parameters.npy", np.ascontiguousarray(np.array(parameters[:, a0:a1, r0:r1])))
    np.savez(
        run_dir / "fit_diagnostics.npz",
        mse_per_k       = fit_diagnostics["mse_per_k"][:, a0:a1, r0:r1],
        penalised_per_k = fit_diagnostics["penalised_per_k"][:, a0:a1, r0:r1],
        best_k_map      = fit_diagnostics["best_k_map"][a0:a1, r0:r1],
        lambda_k        = fit_diagnostics["lambda_k"],
    )

    meta = {
        "parameters_npy"     : "parameters.npy",
        "diagnostics_npz"    : "fit_diagnostics.npz",
        "source_tomogram"    : str(tomo_path),
        "height_range"       : list(HEIGHT_RANGE),
        "k_max"              : K_MAX,
        "activity_threshold" : ACTIVITY_THRESH,
        "threshold_factor"   : THRESHOLD_FACTOR,
        "truncation_index"   : TRUNCATION_INDEX,
    }
    (run_dir / "param_extraction_meta.json").write_text(json.dumps(meta))

    outputs = ParamRunInferencePipeline(run_dir, logger, make_plots=True).run()

    assert (run_dir / "fit_metrics_summary.json").is_file()
    assert (run_dir / "resolution_curves.npz").is_file()
    assert outputs["plots"]
    assert all(p.is_file() for p in outputs["plots"].values())

    summary = json.loads((run_dir / "fit_metrics_summary.json").read_text())
    assert "resolution_summary" in summary
    assert summary["resolution_summary"]["kz_optimum"] > 0.0
    assert len(summary["resolution_summary"]["pass_ranking"]) == 2


@pytest.mark.slow
@pytest.mark.real_data
@pytest.mark.skipif(not _HAS_JAX, reason="jax not installed in this environment")
def test_rerun_extractor_reproduces_best_k(tomogram_full, fit_diagnostics, logger, tmp_path):
    """Verifies a fresh extraction agrees with the stored best-K map on at least 60 percent of active pixels."""
    a0, a1, r0, r1 = 0, 16, 0, 8

    tomo_path = tmp_path / "tomo.npy"
    np.save(tomo_path, np.array(tomogram_full[:, a0:a1, r0:r1]))

    extractor = ParameterExtractor(
        logger               = logger,
        modes                = ["sigma"],
        lambda_values        = [LAMBDA_K],
        k_max                = K_MAX,
        threshold_factor     = THRESHOLD_FACTOR,
        truncation_index     = TRUNCATION_INDEX,
        prominence_frac      = 0.05,
        sigma_init_divisor   = 4.0,
        activity_threshold   = ACTIVITY_THRESH,
        range_batch_size     = 256,
        adam_steps           = 3000,
        adam_lr              = 2e-1,
        adam_b1              = 0.95,
        adam_b2              = 0.999,
        gpu_pixel_batch_size = 8192,
        init_workers         = 4,
    )
    out, diag = extractor.run(tomo_path, HEIGHT_RANGE)[("sigma", LAMBDA_K)]

    assert out.shape  == (3 * K_MAX, a1 - a0, r1 - r0)
    assert diag["best_k_map"].min() >= 0
    assert diag["best_k_map"].max() <= K_MAX

    bk_stored = fit_diagnostics["best_k_map"][a0:a1, r0:r1]
    active    = bk_stored > 0

    assert active.sum() > 0

    agree = (diag["best_k_map"][active] == bk_stored[active]).mean()
    assert agree >= 0.6


def test_stage_save_persists_the_entry_config(tmp_path, monkeypatch):
    """Saving a permutation writes the resolved entry config into its output docs."""
    from pipelines.processing.param_extraction import pipeline as pipeline_module
    from tools.runtime.config_cli              import ConfigCli

    (tmp_path / "data").mkdir(parents=True)
    (tmp_path / "meta").mkdir(parents=True)
    np.save(tmp_path / "data" / "tomogram_full.npy", np.zeros((2, 2, 4), dtype=np.float32))
    (tmp_path / "meta" / "config_state.json").write_text(json.dumps({"tomogram_config": {"height_range": [-20.0, 80.0]}}), encoding="utf-8")

    class _StubIO:
        """Parameter writer stand-in that echoes back the destination paths."""

        def __init__(self, **kwargs):
            """Ignores the writer configuration."""
            pass

        def save_params(self, array, path):
            """Returns the destination path unwritten."""
            return path

        def save_diagnostics(self, diagnostics, path):
            """Returns the destination path unwritten."""
            return path

    class _StubMeta:
        """Metadata manager stand-in that writes nothing."""

        def __init__(self, config, logger=None):
            """Ignores the permutation configuration and logger."""
            pass

        def save_run_metadata(self, npy_path, diag_path, tomogram_path, height_range):
            """Returns the parameter path as the metadata location."""
            return npy_path

    monkeypatch.setattr(pipeline_module, "ParameterExtractor",        lambda **kwargs: None)
    monkeypatch.setattr(pipeline_module, "ParameterIO",               _StubIO)
    monkeypatch.setattr(pipeline_module, "ExtractionMetadataManager", _StubMeta)

    entry = ExtractParamsEntryConfig(fit_k_values=[3], fit_lambda_values=[1e-2], fit_modes=["sigma"])
    group = ExtractionPlanResolver(entry, [tmp_path]).resolve()[0]

    built  = pipeline_module.ParamExtractionPipeline(group, entry_config=entry)
    config = group.configs[("sigma", 1e-2)]
    built._stage_save(config, np.zeros((9, 2, 4), dtype=np.float32), {})
    built.logger.close()

    loaded = ConfigCli.load_resolved(ExtractParamsEntryConfig(), config.output_directory / "docs" / "resolved_entry_config.json")
    assert loaded.fit_k_values == [3]
    assert loaded.fit_modes    == ["sigma"]
