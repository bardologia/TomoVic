"""Fit-quality metrics for a Gaussian parameter-extraction run.

Computes the per-pixel peak-to-floor contrast of the tomographic profiles, the per-pixel
R-squared of the Gaussian reconstruction against the preprocessed profile, the activity
and per-slot parameter maps, and the model-order selection diagnostics.
"""

from __future__ import annotations

import gc
from pathlib import Path
from typing  import Dict, Optional, Tuple

import numpy as np
from scipy.stats import pearsonr, spearmanr

from tools.data.preprocessing import ProfilePreprocessor
from tools.metrics.scoring    import R2
from tools.data.gaussians     import GaussianMixture
from tools.monitoring.logger  import Logger


class ContrastEstimator:
    """Measures the peak-to-floor contrast of tomographic profiles, in dB.

    The floor is the mean of the lowest ``floor_fraction`` of the profile bins, so the
    contrast is an uncalibrated proxy for profile SNR rather than a calibrated SNR.

    Attributes:
        logger: Logger available to the estimator.
        floor_fraction: Fraction of the lowest profile bins averaged into the floor.
        range_chunk: Number of range bins processed per streaming chunk.
    """

    def __init__(self, logger : Logger, floor_fraction : float = 0.25, range_chunk : int = 512) -> None:
        """Configures the contrast estimator.

        Args:
            logger: Logger available to the estimator.
            floor_fraction: Fraction of the lowest profile bins averaged into the floor.
            range_chunk: Number of range bins processed per streaming chunk.
        """
        self.logger         = logger
        self.floor_fraction = floor_fraction
        self.range_chunk    = range_chunk

    @staticmethod
    def contrast_from_amplitude(amp : np.ndarray, floor_fraction : float) -> Tuple[np.ndarray, np.ndarray]:
        """Returns the peak-to-floor contrast and the profile peak of an amplitude block.

        Args:
            amp: Profile amplitude of shape (height, azimuth, range_chunk) or
                (height, ...), with the elevation axis first.
            floor_fraction: Fraction of the lowest bins averaged into the floor.

        Returns:
            Tuple of the contrast in dB and the profile peak amplitude, both shaped like
            ``amp`` with the elevation axis removed; contrast is NaN where the peak or
            floor is not positive.
        """
        n_floor = max(1, int(round(amp.shape[0] * floor_fraction)))

        peak  = amp.max(axis=0)
        floor = np.partition(amp, n_floor - 1, axis=0)[:n_floor].mean(axis=0)
        valid = (peak > 0.0) & (floor > 0.0)

        ratio    = np.maximum(peak, 1e-12) / np.maximum(floor, 1e-12)
        contrast = np.where(valid, 10.0 * np.log10(ratio), np.nan).astype(np.float32)

        return contrast, peak.astype(np.float32)

    def chunk_contrast(self, amp : np.ndarray) -> np.ndarray:
        """Returns the contrast in dB of one amplitude chunk of shape (height, azimuth, range)."""
        contrast, _ = self.contrast_from_amplitude(amp, self.floor_fraction)

        return contrast

    def run(self, tomogram : np.ndarray) -> np.ndarray:
        """Computes the contrast map of a whole tomogram in range chunks.

        Args:
            tomogram: Complex tomogram of shape (height, azimuth, range).

        Returns:
            Peak-to-floor contrast of shape (azimuth, range), in dB.
        """
        H, Az, R    = tomogram.shape
        contrast_db = np.full((Az, R), np.nan, dtype=np.float32)

        for r_start in range(0, R, self.range_chunk):
            r_end = min(r_start + self.range_chunk, R)
            amp   = np.abs(tomogram[:, :, r_start:r_end]).astype(np.float32, copy=False)

            contrast_db[:, r_start:r_end] = self.chunk_contrast(amp)

            del amp

        return contrast_db


class KSelectionDiagnostics:
    """Quantifies how decisively the fitter picked the model order K at each pixel.

    Attributes:
        k_max: Largest model order the fitter evaluated.
        logger: Logger available to the diagnostics.
        ambiguity_threshold: Relative margin below which a pixel counts as ambiguous.
    """

    def __init__(self, k_max : int, logger : Logger, ambiguity_threshold : float = 0.05) -> None:
        """Configures the model-order diagnostics.

        Args:
            k_max: Largest model order the fitter evaluated.
            logger: Logger available to the diagnostics.
            ambiguity_threshold: Relative margin below which a pixel counts as ambiguous.
        """
        self.k_max               = k_max
        self.logger              = logger
        self.ambiguity_threshold = ambiguity_threshold

    def _compute_margin_maps(self, penalised_per_k : np.ndarray, best_k_map : np.ndarray) -> Dict[str, np.ndarray]:
        """Computes how far the winning model order sits from its competitors.

        Args:
            penalised_per_k: Penalised score of shape (k_max, azimuth, range).
            best_k_map: Selected model order of shape (azimuth, range); 0 marks inactive
                pixels.

        Returns:
            Mapping with the margins to K-1, K+1 and the runner-up, plus the runner-up
            margin relative to the winning score, each of shape (azimuth, range) and NaN
            where undefined.
        """
        k_max  = penalised_per_k.shape[0]
        active = best_k_map > 0
        idx    = np.clip(best_k_map.astype(np.int64) - 1, 0, k_max - 1)

        pen_best = np.take_along_axis(penalised_per_k, idx[None, :, :], axis=0)[0]
        pen_prev = np.take_along_axis(penalised_per_k, np.clip(idx - 1, 0, k_max - 1)[None, :, :], axis=0)[0]
        pen_next = np.take_along_axis(penalised_per_k, np.clip(idx + 1, 0, k_max - 1)[None, :, :], axis=0)[0]

        has_prev = active & (best_k_map > 1)
        has_next = active & (best_k_map < k_max)

        margin_prev = np.where(has_prev, pen_prev - pen_best, np.nan).astype(np.float32)
        margin_next = np.where(has_next, pen_next - pen_best, np.nan).astype(np.float32)

        masked = penalised_per_k.copy()
        np.put_along_axis(masked, idx[None, :, :], np.inf, axis=0)

        second        = masked.min(axis=0)
        second_valid  = active & np.isfinite(second)
        margin_second = np.where(second_valid, second - pen_best,                                np.nan).astype(np.float32)
        rel_margin    = np.where(second_valid, margin_second / np.maximum(np.abs(pen_best), 1e-12), np.nan).astype(np.float32)

        del masked

        return {
            "k_margin_prev_map"     : margin_prev,
            "k_margin_next_map"     : margin_next,
            "k_margin_second_map"   : margin_second,
            "k_relative_margin_map" : rel_margin,
        }

    def _compute_per_k_summary(self, mse_per_k : np.ndarray, penalised_per_k : np.ndarray, best_k_map : np.ndarray) -> Dict[str, float]:
        """Summarises the residual, penalty and win rate of each model order.

        Args:
            mse_per_k: Residual MSE of shape (k_max, azimuth, range).
            penalised_per_k: Penalised score of shape (k_max, azimuth, range).
            best_k_map: Selected model order of shape (azimuth, range); 0 marks inactive.

        Returns:
            Mapping from statistic name to scalar, keyed ``k{K}_...`` per model order.
        """
        active   = best_k_map > 0
        n_active = int(active.sum())
        summary  : Dict[str, float] = {"n_active_pixels": float(n_active)}

        for k in range(1, self.k_max + 1):
            mse_k     = mse_per_k      [k - 1][active].astype(np.float64)
            pen_k     = penalised_per_k[k - 1][active].astype(np.float64)
            penalty_k = pen_k - mse_k

            mse_v = mse_k    [np.isfinite(mse_k)]
            pen_v = pen_k    [np.isfinite(pen_k)]
            pty_v = penalty_k[np.isfinite(penalty_k)]
            wins  = int((best_k_map == k).sum())

            summary[f"k{k}_mse_mean"]       = float(mse_v.mean())             if mse_v.size > 0 else float("nan")
            summary[f"k{k}_mse_median"]     = float(np.median(mse_v))         if mse_v.size > 0 else float("nan")
            summary[f"k{k}_mse_p25"]        = float(np.percentile(mse_v, 25)) if mse_v.size > 0 else float("nan")
            summary[f"k{k}_mse_p75"]        = float(np.percentile(mse_v, 75)) if mse_v.size > 0 else float("nan")
            summary[f"k{k}_penalised_mean"] = float(pen_v.mean())             if pen_v.size > 0 else float("nan")
            summary[f"k{k}_penalty_mean"]   = float(pty_v.mean())             if pty_v.size > 0 else float("nan")
            summary[f"k{k}_win_fraction"]   = float(wins) / n_active          if n_active > 0   else float("nan")

        return summary

    def run(self, diagnostics : dict) -> Tuple[Dict[str, np.ndarray], Dict[str, float]]:
        """Derives the margin maps and per-order summary from the fitter diagnostics.

        Args:
            diagnostics: Fitter diagnostics carrying ``mse_per_k``, ``penalised_per_k``
                and ``best_k_map``.

        Returns:
            Tuple of the diagnostic map dictionary and the scalar summary dictionary.
        """
        mse_per_k       = diagnostics["mse_per_k"].astype(np.float32, copy=False)
        penalised_per_k = diagnostics["penalised_per_k"].astype(np.float32, copy=False)
        best_k_map      = diagnostics["best_k_map"]

        margin_maps = self._compute_margin_maps(penalised_per_k, best_k_map)
        summary     = self._compute_per_k_summary(mse_per_k, penalised_per_k, best_k_map)

        rel   = margin_maps["k_relative_margin_map"].reshape(-1)
        rel_v = rel[np.isfinite(rel)]

        summary["k_relative_margin_median"] = float(np.median(rel_v))                            if rel_v.size > 0 else float("nan")
        summary["k_ambiguous_fraction"]     = float((rel_v < self.ambiguity_threshold).mean())   if rel_v.size > 0 else float("nan")
        summary["ambiguity_threshold"]      = float(self.ambiguity_threshold)

        maps = {
            "mse_per_k"       : mse_per_k,
            "penalised_per_k" : penalised_per_k,
            "best_k_map"      : best_k_map,
            **margin_maps,
        }

        return maps, summary


class FittingMetricsCalculator:
    """Scores a fitted parameter stack against the tomogram it was fitted to.

    Attributes:
        n_gaussians: Number of Gaussian slots in the parameter stack.
        logger: Logger for the stage report.
        threshold_factor: Peak fraction below which profile bins were zeroed by the fitter.
        truncation_index: Elevation bin above which the profile was truncated by the fitter.
        amp_threshold: Amplitude above which a Gaussian slot counts as active.
        range_chunk: Number of range bins processed per streaming chunk.
        contrast_estimator: Peak-to-floor contrast estimator.
        k_diagnostics: Model-order selection diagnostics.
    """

    def __init__(self, n_gaussians : int, logger : Logger, threshold_factor : float, truncation_index : int, amp_threshold : float = 1e-3, range_chunk : int = 128) -> None:
        """Configures the metrics calculator to mirror the fitter's preprocessing.

        Args:
            n_gaussians: Number of Gaussian slots in the parameter stack.
            logger: Logger for the stage report.
            threshold_factor: Peak fraction below which profile bins were zeroed.
            truncation_index: Elevation bin above which the profile was truncated.
            amp_threshold: Amplitude above which a Gaussian slot counts as active.
            range_chunk: Number of range bins processed per streaming chunk.
        """
        self.n_gaussians      = n_gaussians
        self.logger           = logger
        self.threshold_factor = threshold_factor
        self.truncation_index = truncation_index
        self.amp_threshold    = amp_threshold
        self.range_chunk      = range_chunk

        self.contrast_estimator = ContrastEstimator(logger=logger, range_chunk=range_chunk)
        self.k_diagnostics      = KSelectionDiagnostics(k_max=n_gaussians, logger=logger)

    @staticmethod
    def _open_tomogram(tomogram_path: Path) -> np.ndarray:
        """Returns the tomogram of shape (height, azimuth, range) as a read-only memory map."""
        return np.load(str(tomogram_path), mmap_mode="r", allow_pickle=False)

    @staticmethod
    def _build_height_axis(height_range: Tuple[float, float], n_elev: int) -> np.ndarray:
        """Returns the elevation axis of ``n_elev`` samples spanning the height range, in metres."""
        return np.linspace(float(height_range[0]), float(height_range[1]), n_elev, dtype=np.float32)

    def _reconstruct_slice(self, parameters_array : np.ndarray, h_val : float) -> np.ndarray:
        """Evaluates the fitted mixture at one height.

        Args:
            parameters_array: Parameter block of shape (3 * n_gaussians, azimuth, range).
            h_val: Elevation the mixture is evaluated at, in metres.

        Returns:
            Mixture value of shape (azimuth, range).
        """
        return GaussianMixture.evaluate_slice(parameters_array, h_val, self.n_gaussians)

    def _contrast_and_r2_maps(self, tomogram : np.ndarray, parameters_array : np.ndarray, height_axis : np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
        """Streams the tomogram to build the contrast and reconstruction-quality maps.

        Args:
            tomogram: Complex tomogram of shape (height, azimuth, range).
            parameters_array: Parameter stack of shape (3 * n_gaussians, azimuth, range).
            height_axis: Elevation axis of shape (height,), in metres.

        Returns:
            Tuple of the peak-to-floor contrast in dB and the per-pixel R-squared of the
            mixture against the preprocessed profile, both of shape (azimuth, range).
        """
        H, Az, R    = tomogram.shape
        contrast_db = np.full ((Az, R), np.nan, dtype=np.float32)
        r2_map      = np.empty((Az, R),         dtype=np.float32)

        for r_start in range(0, R, self.range_chunk):
            r_end = min(r_start + self.range_chunk, R)
            amp   = np.abs(tomogram[:, :, r_start:r_end]).astype(np.float32, copy=False)

            contrast_db[:, r_start:r_end] = self.contrast_estimator.chunk_contrast(amp)

            reference = ProfilePreprocessor.apply(amp, self.threshold_factor, self.truncation_index)
            pred      = np.empty(reference.shape, dtype=np.float32)
            params    = parameters_array[:, :, r_start:r_end]

            for j in range(H):
                pred[j] = self._reconstruct_slice(params, float(height_axis[j]))

            r2_map[:, r_start:r_end] = R2.pixel_map(pred, reference, axis=0)

            del amp, reference, pred

        return contrast_db, r2_map

    def _compute_activity_map(self, parameters_array: np.ndarray) -> np.ndarray:
        """Counts the active Gaussian slots at each pixel.

        Args:
            parameters_array: Parameter stack of shape (3 * n_gaussians, azimuth, range).

        Returns:
            Number of slots above the amplitude threshold, of shape (azimuth, range).
        """
        active = np.zeros(parameters_array.shape[1:], dtype=np.int32)
        for k in range(self.n_gaussians):
            active += (parameters_array[3 * k] >= self.amp_threshold).astype(np.int32)

        return active

    def _compute_per_gaussian_maps(self, parameters_array: np.ndarray) -> Dict[str, np.ndarray]:
        """Splits the parameter stack into per-slot maps masked to active pixels.

        Args:
            parameters_array: Parameter stack of shape (3 * n_gaussians, azimuth, range).

        Returns:
            Mapping with ``amp_k``, ``mu_k`` (metres) and ``sigma_k`` (metres) maps of
            shape (azimuth, range), NaN where the slot is inactive.
        """
        maps: Dict[str, np.ndarray] = {}
        for k in range(self.n_gaussians):
            amp_k  = parameters_array[3 * k    ].astype(np.float32)
            active = amp_k >= self.amp_threshold
            maps[f"amp_{k}"]   = np.where(active, amp_k,                                           np.nan).astype(np.float32)
            maps[f"mu_{k}"]    = np.where(active, parameters_array[3 * k + 1].astype(np.float32),  np.nan).astype(np.float32)
            maps[f"sigma_{k}"] = np.where(active, parameters_array[3 * k + 2].astype(np.float32),  np.nan).astype(np.float32)

        return maps

    def _compute_mu_separation_maps(self, parameters_array: np.ndarray) -> Dict[str, np.ndarray]:
        """Measures the height gap between adjacent Gaussian slots.

        Args:
            parameters_array: Parameter stack of shape (3 * n_gaussians, azimuth, range).

        Returns:
            Mapping with ``mu_sep_k_k+1`` maps of shape (azimuth, range) in metres, NaN
            where either slot is inactive; empty when fewer than two slots exist.
        """
        maps: Dict[str, np.ndarray] = {}
        if self.n_gaussians < 2:
            return maps

        for k in range(self.n_gaussians - 1):
            a_k   = parameters_array[3 * k            ]
            a_kp1 = parameters_array[3 * (k + 1)      ]
            m_k   = parameters_array[3 * k         + 1]
            m_kp1 = parameters_array[3 * (k + 1)   + 1]
            both  = (a_k >= self.amp_threshold) & (a_kp1 >= self.amp_threshold)
            maps[f"mu_sep_{k}_{k + 1}"] = np.where(both, np.abs(m_kp1.astype(np.float32) - m_k.astype(np.float32)), np.nan).astype(np.float32)

        return maps

    def _compute_global_summary(self, r2_map : np.ndarray, activity_map : np.ndarray) -> Dict[str, float]:
        """Summarises fit quality and the distribution of active-slot counts.

        Args:
            r2_map: Per-pixel R-squared of shape (azimuth, range), NaN where unfitted.
            activity_map: Active-slot count of shape (azimuth, range).

        Returns:
            Mapping with pixel counts, R-squared moments and percentiles, and the
            fraction of pixels carrying each active-slot count.
        """
        r2_flat  = r2_map.reshape(-1).astype(np.float64)
        r2_valid = r2_flat[np.isfinite(r2_flat)]
        n_total  = int(r2_map.size)
        act_flat = activity_map.reshape(-1)
        n_fitted = int((act_flat > 0).sum())

        def _pct(q: float) -> float:
            """Returns the q-th percentile of the finite R-squared values, or NaN."""
            return float(np.percentile(r2_valid, q)) if r2_valid.size > 0 else float("nan")

        summary: Dict[str, float] = {
            "n_pixels"    : float(n_total),
            "n_fitted"    : float(n_fitted),
            "n_gaussians" : float(self.n_gaussians),
            "r2_mean"     : float(r2_valid.mean())      if r2_valid.size > 0 else float("nan"),
            "r2_median"   : float(np.median(r2_valid))  if r2_valid.size > 0 else float("nan"),
            "r2_std"      : float(r2_valid.std())       if r2_valid.size > 0 else float("nan"),
            "r2_p10"      : _pct(10),
            "r2_p25"      : _pct(25),
            "r2_p50"      : _pct(50),
            "r2_p75"      : _pct(75),
            "r2_p90"      : _pct(90),
            "r2_neg_frac" : float((r2_valid < 0.0).mean()) if r2_valid.size > 0 else float("nan"),
        }

        for k in range(self.n_gaussians + 1):
            n_k = int((act_flat == k).sum())
            summary[f"frac_{k}_active"] = float(n_k) / n_total if n_total > 0 else float("nan")

        for k in range(1, self.n_gaussians + 1):
            n_k = int((act_flat == k).sum())
            summary[f"frac_{k}_fitted"] = float(n_k) / n_fitted if n_fitted > 0 else float("nan")

        return summary

    def _compute_snr_summary(self, snr_db_map : np.ndarray, r2_map : np.ndarray, best_k_map : Optional[np.ndarray], max_samples : int = 1_000_000) -> Dict[str, float]:
        """Summarises the contrast distribution and its relation to fit quality.

        Args:
            snr_db_map: Peak-to-floor contrast of shape (azimuth, range), in dB.
            r2_map: Per-pixel R-squared of shape (azimuth, range).
            best_k_map: Selected model order of shape (azimuth, range), or None.
            max_samples: Cap on the number of pixels used for the correlations.

        Returns:
            Mapping with contrast moments and percentiles, the Pearson and Spearman
            correlation against R-squared, and the median contrast per selected order.
        """
        snr = snr_db_map.reshape(-1).astype(np.float64)
        r2  = r2_map.reshape(-1).astype(np.float64)
        ok  = np.isfinite(snr) & np.isfinite(r2)
        idx = np.where(ok)[0]

        if idx.size > max_samples:
            rng = np.random.default_rng(0)
            idx = rng.choice(idx, size=max_samples, replace=False)

        s = snr[idx]
        r = r2 [idx]

        summary: Dict[str, float] = {
            "contrast_db_mean"   : float(s.mean())             if s.size > 0 else float("nan"),
            "contrast_db_median" : float(np.median(s))         if s.size > 0 else float("nan"),
            "contrast_db_p10"    : float(np.percentile(s, 10)) if s.size > 0 else float("nan"),
            "contrast_db_p90"    : float(np.percentile(s, 90)) if s.size > 0 else float("nan"),
        }

        if s.size > 2 and s.std() > 0.0 and r.std() > 0.0:
            summary["contrast_r2_pearson"]  = float(pearsonr (s, r)[0])
            summary["contrast_r2_spearman"] = float(spearmanr(s, r)[0])
        else:
            summary["contrast_r2_pearson"]  = float("nan")
            summary["contrast_r2_spearman"] = float("nan")

        if best_k_map is not None:
            contrast_full = snr_db_map.astype(np.float64)
            for k in range(1, self.n_gaussians + 1):
                vals = contrast_full[(best_k_map == k) & np.isfinite(snr_db_map)]
                summary[f"contrast_db_median_k{k}"] = float(np.median(vals)) if vals.size > 0 else float("nan")

        return summary

    def run(self, parameters_array : np.ndarray, metadata : dict, tomogram_path : Path, diagnostics : Optional[dict] = None) -> dict:
        """Computes every fit-quality map and summary for one parameter run.

        Args:
            parameters_array: Parameter stack of shape (3 * n_gaussians, azimuth, range).
            metadata: Run metadata carrying ``height_range`` in metres.
            tomogram_path: Path of the tomogram the fit was performed on.
            diagnostics: Fitter diagnostics; model-order metrics are skipped when absent.

        Returns:
            Dictionary with the R-squared, activity and contrast maps, the elevation
            axis, the global, contrast and per-order summaries, and the per-slot,
            separation and model-order maps.
        """
        self.logger.section("[Fitting Metrics Calculation]")

        self.logger.subsection(f"Loading tomogram : {Path(tomogram_path).name}")
        tomogram     = self._open_tomogram(Path(tomogram_path))
        height_range = tuple(metadata["height_range"])
        height_axis  = self._build_height_axis(height_range, tomogram.shape[0])

        self.logger.subsection(f"Tomogram shape  : {tomogram.shape}")
        self.logger.subsection(f"Height range    : [{height_range[0]:.1f}, {height_range[1]:.1f}] m")

        self.logger.subsection("Computing per-pixel peak-to-floor contrast map (peak over lowest-quartile profile amplitude, uncalibrated proxy)")
        self.logger.subsection(f"Applying fitter preprocessing for R² (threshold_factor={self.threshold_factor}, truncation_index={self.truncation_index})")
        self.logger.subsection(f"Computing per-pixel R² map against thresholded/truncated profile (memory-mapped, range chunks of {self.range_chunk} bins, float32)")
        snr_db_map, r2_map = self._contrast_and_r2_maps(tomogram, parameters_array, height_axis)

        del tomogram
        gc.collect()

        self.logger.subsection("Computing activity and spatial parameter maps")
        activity_map = self._compute_activity_map(parameters_array)

        self.logger.subsection("Masking R² to fitted pixels: pixels with no active Gaussian were never candidates for a fit")
        r2_map = np.where(activity_map > 0, r2_map, np.nan).astype(np.float32)

        gauss_maps   = self._compute_per_gaussian_maps(parameters_array)
        sep_maps     = self._compute_mu_separation_maps(parameters_array)
        summary      = self._compute_global_summary(r2_map, activity_map)

        k_maps    : Dict[str, np.ndarray] = {}
        k_summary : Dict[str, float]      = {}

        if diagnostics is not None and "best_k_map" in diagnostics:
            self.logger.subsection("Computing model-order selection diagnostics")
            k_maps, k_summary = self.k_diagnostics.run(diagnostics)

        best_k_map = k_maps["best_k_map"] if "best_k_map" in k_maps else None

        self.logger.subsection("Computing peak-to-floor contrast statistics and contrast-to-fit-quality relation")
        snr_summary = self._compute_snr_summary(snr_db_map, r2_map, best_k_map)

        self.logger.subsection(f"R² — mean={summary['r2_mean']:.4f} median={summary['r2_median']:.4f} neg_frac={summary['r2_neg_frac']:.4f}")
        self.logger.subsection(f"Peak-to-floor contrast — median={snr_summary['contrast_db_median']:.2f} dB, Spearman(contrast, R²)={snr_summary['contrast_r2_spearman']:.3f}")

        if k_summary:
            self.logger.subsection(f"K selection — median relative margin={k_summary['k_relative_margin_median']:.4f}, ambiguous fraction={k_summary['k_ambiguous_fraction']:.4f}")

        return {
            "r2_map"         : r2_map,
            "activity_map"   : activity_map,
            "snr_db_map"     : snr_db_map,
            "height_axis"    : height_axis,
            "global_summary" : summary,
            "snr_summary"    : snr_summary,
            "per_k_summary"  : k_summary,
            **k_maps,
            **gauss_maps,
            **sep_maps,
        }
