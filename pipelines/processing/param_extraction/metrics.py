"""Fit-quality metrics for a Gaussian parameter-extraction run.

Computes the per-pixel peak-to-floor contrast of the tomographic profiles, the per-pixel
R-squared of the Gaussian reconstruction against the preprocessed profile, the activity
and per-slot parameter maps, and the model-order selection diagnostics.
"""

from __future__ import annotations

import gc
from pathlib import Path
from time    import perf_counter
from typing  import Dict, Optional, Tuple

import numpy as np
from scipy.stats import pearsonr, spearmanr

from tools.data.preprocessing import ProfilePreprocessor
from tools.metrics.scoring    import R2
from tools.data.gaussians     import GaussianActivity, GaussianAxis, GaussianMixture
from tools.monitoring.logger  import Logger


class ContrastEstimator:
    """Measures the peak-to-floor contrast of tomographic profiles, in dB.

    The floor is the mean of the lowest ``floor_fraction`` of the profile bins, so the
    contrast is an uncalibrated proxy for profile SNR rather than a calibrated SNR.

    Attributes:
        logger         : Logger available to the estimator.
        floor_fraction : Fraction of the lowest profile bins averaged into the floor.
        range_chunk    : Number of range bins processed per streaming chunk.
    """

    def __init__(self, logger : Logger, floor_fraction : float = 0.25, range_chunk : int = 512) -> None:
        """Configures the contrast estimator.

        Args:
            logger         : Logger available to the estimator.
            floor_fraction : Fraction of the lowest profile bins averaged into the floor.
            range_chunk    : Number of range bins processed per streaming chunk.
        """
        self.logger         = logger
        self.floor_fraction = floor_fraction
        self.range_chunk    = range_chunk

    @staticmethod
    def contrast_from_amplitude(amp : np.ndarray, floor_fraction : float) -> Tuple[np.ndarray, np.ndarray]:
        """Returns the peak-to-floor contrast and the profile peak of an amplitude block.

        Args:
            amp            : Profile amplitude of shape (height, azimuth, range_chunk) or (height, ...), with the elevation axis first.
            floor_fraction : Fraction of the lowest bins averaged into the floor.

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
            tomogram : Complex tomogram of shape (height, azimuth, range).

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
        k_max               : Largest model order the fitter evaluated.
        logger              : Logger available to the diagnostics.
        ambiguity_threshold : Relative margin below which a pixel counts as ambiguous.
    """

    def __init__(self, k_max : int, logger : Logger, ambiguity_threshold : float = 0.05) -> None:
        """Configures the model-order diagnostics.

        Args:
            k_max               : Largest model order the fitter evaluated.
            logger              : Logger available to the diagnostics.
            ambiguity_threshold : Relative margin below which a pixel counts as ambiguous.
        """
        self.k_max               = k_max
        self.logger              = logger
        self.ambiguity_threshold = ambiguity_threshold

    def _compute_margin_maps(self, penalised_per_k : np.ndarray, best_k_map : np.ndarray) -> Dict[str, np.ndarray]:
        """Computes how far the winning model order sits from its competitors.

        Args:
            penalised_per_k : Penalised score of shape (k_max, azimuth, range).
            best_k_map      : Selected model order of shape (azimuth, range); 0 marks inactive pixels.

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
            mse_per_k       : Residual MSE of shape (k_max, azimuth, range).
            penalised_per_k : Penalised score of shape (k_max, azimuth, range).
            best_k_map      : Selected model order of shape (azimuth, range); 0 marks inactive.

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
            diagnostics : Fitter diagnostics carrying ``mse_per_k``, ``penalised_per_k`` and ``best_k_map``.

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


class ParameterMapBuilder:
    """Derives the per-pixel maps a Gaussian parameter stack carries on its own.

    Every map here needs only the parameter stack and the activity threshold, so the
    builder serves both the fitted-run metrics and the analysis of injected runs
    that carry no fit diagnostics.

    Attributes:
        n_gaussians   : Number of Gaussian slots in the parameter stack.
        amp_threshold : Amplitude above which a Gaussian slot counts as active.
    """

    def __init__(self, n_gaussians : int, amp_threshold : float) -> None:
        """Fixes the slot count and the activity threshold the maps are derived with.

        Args:
            n_gaussians   : Number of Gaussian slots in the parameter stack.
            amp_threshold : Amplitude above which a Gaussian slot counts as active.
        """
        self.n_gaussians   = n_gaussians
        self.amp_threshold = amp_threshold

    def activity_map(self, parameters_array: np.ndarray) -> np.ndarray:
        """Counts the active Gaussian slots at each pixel.

        Args:
            parameters_array : Parameter stack of shape (3 * n_gaussians, azimuth, range).

        Returns:
            Number of slots above the amplitude threshold, of shape (azimuth, range).
        """
        active = np.zeros(parameters_array.shape[1:], dtype=np.int32)
        for k in range(self.n_gaussians):
            active += GaussianActivity.is_active(parameters_array[3 * k], self.amp_threshold).astype(np.int32)

        return active

    def per_gaussian_maps(self, parameters_array: np.ndarray) -> Dict[str, np.ndarray]:
        """Splits the parameter stack into per-slot maps masked to active pixels.

        Args:
            parameters_array : Parameter stack of shape (3 * n_gaussians, azimuth, range).

        Returns:
            Mapping with ``amp_k``, ``mu_k`` (metres) and ``sigma_k`` (metres) maps of
            shape (azimuth, range), NaN where the slot is inactive.
        """
        maps: Dict[str, np.ndarray] = {}
        for k in range(self.n_gaussians):
            amp_k  = parameters_array[3 * k    ].astype(np.float32)
            active = GaussianActivity.is_active(amp_k, self.amp_threshold)
            maps[f"amp_{k}"]   = np.where(active, amp_k,                                           np.nan).astype(np.float32)
            maps[f"mu_{k}"]    = np.where(active, parameters_array[3 * k + 1].astype(np.float32),  np.nan).astype(np.float32)
            maps[f"sigma_{k}"] = np.where(active, parameters_array[3 * k + 2].astype(np.float32),  np.nan).astype(np.float32)

        return maps

    def mu_separation_maps(self, parameters_array: np.ndarray) -> Dict[str, np.ndarray]:
        """Measures the height gap between adjacent Gaussian slots.

        Args:
            parameters_array : Parameter stack of shape (3 * n_gaussians, azimuth, range).

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
            both  = GaussianActivity.is_active(a_k, self.amp_threshold) & GaussianActivity.is_active(a_kp1, self.amp_threshold)
            maps[f"mu_sep_{k}_{k + 1}"] = np.where(both, np.abs(m_kp1.astype(np.float32) - m_k.astype(np.float32)), np.nan).astype(np.float32)

        return maps

    def occupancy_summary(self, activity_map: np.ndarray) -> Dict[str, float]:
        """Summarises how many slots the pixels carry.

        Args:
            activity_map : Active-slot count of shape (azimuth, range).

        Returns:
            Mapping with the pixel count, the count of pixels holding at least one
            active slot, and the fraction of all pixels and of populated pixels
            carrying each active-slot count.
        """
        act_flat    = activity_map.reshape(-1)
        n_total     = int(activity_map.size)
        n_populated = int((act_flat > 0).sum())

        summary: Dict[str, float] = {
            "n_pixels"    : float(n_total),
            "n_fitted"    : float(n_populated),
            "n_gaussians" : float(self.n_gaussians),
        }

        for k in range(self.n_gaussians + 1):
            n_k = int((act_flat == k).sum())
            summary[f"frac_{k}_active"] = float(n_k) / n_total if n_total > 0 else float("nan")

        for k in range(1, self.n_gaussians + 1):
            n_k = int((act_flat == k).sum())
            summary[f"frac_{k}_fitted"] = float(n_k) / n_populated if n_populated > 0 else float("nan")

        return summary


class FitBoundCensus:
    """Counts the active fitted slots whose width or centroid ended on the fitter's clamp bounds.

    The projected Adam fit clips every sigma to [dh, h_span / 2] and every
    mean to the ends of the height axis after each step, where dh is the
    height step and h_span the axis extent. A slot sitting on one of these
    bounds was placed by the clamp rather than by the profile, so the shares
    tell whether a fit setting moves the labels or only the clamp.

    Attributes:
        RELATIVE_TOLERANCE : Distance to a bound, as a fraction of that bound for sigma and of h_span for the mean, within which a slot counts as on it.
        WARN_FRACTION      : Share of active slots on a bound above which the census warns.
        activity_threshold : Amplitude above which a slot counts as active.
        sigma_lower        : Lower sigma bound dh, in metres.
        sigma_upper        : Upper sigma bound h_span / 2, in metres.
        mu_lower           : Lowest elevation of the height axis, in metres.
        mu_upper           : Highest elevation of the height axis, in metres.
        mu_tolerance       : Distance to an axis end within which a mean counts as on it, in metres.
    """

    RELATIVE_TOLERANCE = 1e-4
    WARN_FRACTION      = 0.05

    def __init__(self, height_axis : np.ndarray, activity_threshold : float) -> None:
        """Derives the fitter's clamp bounds from the height axis.

        Args:
            height_axis        : Evenly spaced elevation axis of shape (height,) the fit ran on, in metres.
            activity_threshold : Amplitude above which a slot counts as active, as recorded by the run.
        """
        h_span = float(height_axis[-1] - height_axis[0])

        self.activity_threshold = activity_threshold
        self.sigma_lower        = h_span / (len(height_axis) - 1)
        self.sigma_upper        = h_span / 2.0
        self.mu_lower           = float(height_axis[0])
        self.mu_upper           = float(height_axis[-1])
        self.mu_tolerance       = self.RELATIVE_TOLERANCE * h_span

    def count(self, amplitudes : np.ndarray, means : np.ndarray, sigmas : np.ndarray) -> Dict[str, int]:
        """Counts the active slots and those on each bound.

        Args:
            amplitudes : Physical slot amplitudes of any shape.
            means      : Slot means of the same shape, in metres.
            sigmas     : Slot widths of the same shape, in metres.

        Returns:
            Mapping with ``active_slots``, ``sigma_at_lower``, ``sigma_at_upper`` and ``mu_at_bound`` counts.
        """
        active = GaussianActivity.is_active(amplitudes, self.activity_threshold)

        return {
            "active_slots"   : int(active.sum()),
            "sigma_at_lower" : int((active & (sigmas <= self.sigma_lower * (1.0 + self.RELATIVE_TOLERANCE))).sum()),
            "sigma_at_upper" : int((active & (sigmas >= self.sigma_upper * (1.0 - self.RELATIVE_TOLERANCE))).sum()),
            "mu_at_bound"    : int((active & ((means <= self.mu_lower + self.mu_tolerance) | (means >= self.mu_upper - self.mu_tolerance))).sum()),
        }

    def count_rows(self, parameters : np.ndarray) -> Dict[str, int]:
        """Counts a flattened batch whose rows interleave amplitude, mean and sigma per slot.

        Args:
            parameters : Parameters of shape (pixels, 3 * k_max).
        """
        return self.count(parameters[:, 0::3], parameters[:, 1::3], parameters[:, 2::3])

    def count_stack(self, parameters_array : np.ndarray, n_gaussians : int) -> Dict[str, int]:
        """Counts a parameter stack slot by slot, holding one slot's maps at a time.

        Args:
            parameters_array : Parameter stack of shape (3 * n_gaussians, azimuth, range).
            n_gaussians      : Number of Gaussian slots in the stack.
        """
        totals = {"active_slots": 0, "sigma_at_lower": 0, "sigma_at_upper": 0, "mu_at_bound": 0}

        for k in range(n_gaussians):
            counts = self.count(parameters_array[3 * k], parameters_array[3 * k + 1], parameters_array[3 * k + 2])
            for key in totals:
                totals[key] += counts[key]

        return totals

    @staticmethod
    def add(totals : Dict[str, int], counts : Dict[str, int]) -> None:
        """Adds one batch's counts into running totals in place."""
        for key, value in counts.items():
            totals[key] = totals.get(key, 0) + value

    @staticmethod
    def fractions(counts : Dict[str, int]) -> Dict[str, float]:
        """Returns each bound count as a share of the active slots, NaN when no slot is active.

        Returns:
            Mapping with ``sigma_at_lower_frac``, ``sigma_at_upper_frac`` and ``mu_at_bound_frac``.
        """
        active = counts["active_slots"]

        return {
            f"{key}_frac" : counts[key] / active if active > 0 else float("nan")
            for key in ("sigma_at_lower", "sigma_at_upper", "mu_at_bound")
        }

    def report(self, counts : Dict[str, int], logger : Logger, label : str) -> None:
        """Logs the bound shares and warns for every share above WARN_FRACTION.

        Args:
            counts : Counts as ``count`` returns them, possibly summed over batches.
            logger : Logger receiving the line and the warnings.
            label  : Run or permutation the counts belong to, named in every line.
        """
        shares = self.fractions(counts)

        logger.subsection(f"{label} | slots on a clamp bound of {counts['active_slots']:,} active : sigma at dh={self.sigma_lower:.4f} m {shares['sigma_at_lower_frac']:.2%}, sigma at h_span/2={self.sigma_upper:.2f} m {shares['sigma_at_upper_frac']:.2%}, mean at an axis end {shares['mu_at_bound_frac']:.2%}")

        bounds = {"sigma_at_lower_frac": f"the lower sigma bound dh = {self.sigma_lower:.4f} m", "sigma_at_upper_frac": f"the upper sigma bound h_span/2 = {self.sigma_upper:.2f} m", "mu_at_bound_frac": f"an end of the height axis [{self.mu_lower:.2f}, {self.mu_upper:.2f}] m"}
        for key, where in bounds.items():
            if shares[key] > self.WARN_FRACTION:
                logger.warning(f"{label}: {shares[key]:.1%} of {counts['active_slots']:,} active slots end on {where}, above the {self.WARN_FRACTION:.0%} limit; the clamp, not the profile, sets those labels")


class FittingMetricsCalculator:
    """Scores a fitted parameter stack against the tomogram it was fitted to.

    Attributes:
        n_gaussians        : Number of Gaussian slots in the parameter stack.
        logger             : Logger for the stage report.
        threshold_factor   : Peak fraction below which profile bins were zeroed by the fitter.
        truncation_index   : Elevation bin above which the profile was truncated by the fitter.
        amp_threshold      : Amplitude above which a Gaussian slot counts as active.
        range_chunk        : Number of range bins processed per streaming chunk.
        contrast_estimator : Peak-to-floor contrast estimator.
        k_diagnostics      : Model-order selection diagnostics.
        maps               : Builder of the activity, per-slot and separation maps.
        LOG_EVERY_SECONDS  : Minimum seconds between two progress lines of the streaming loop in the log.
    """

    LOG_EVERY_SECONDS = 120.0

    def __init__(self, n_gaussians : int, logger : Logger, threshold_factor : float, truncation_index : int, amp_threshold : float, range_chunk : int = 128) -> None:
        """Configures the metrics calculator to mirror the fitter's preprocessing.

        Args:
            n_gaussians      : Number of Gaussian slots in the parameter stack.
            logger           : Logger for the stage report.
            threshold_factor : Peak fraction below which profile bins were zeroed.
            truncation_index : Elevation bin above which the profile was truncated.
            amp_threshold    : Amplitude above which a Gaussian slot counts as active, as recorded by the run metadata.
            range_chunk      : Number of range bins processed per streaming chunk.
        """
        self.n_gaussians      = n_gaussians
        self.logger           = logger
        self.threshold_factor = threshold_factor
        self.truncation_index = truncation_index
        self.amp_threshold    = amp_threshold
        self.range_chunk      = range_chunk

        self.contrast_estimator = ContrastEstimator(logger=logger, range_chunk=range_chunk)
        self.k_diagnostics      = KSelectionDiagnostics(k_max=n_gaussians, logger=logger)
        self.maps               = ParameterMapBuilder(n_gaussians=n_gaussians, amp_threshold=amp_threshold)

    @staticmethod
    def _open_tomogram(tomogram_path: Path) -> np.ndarray:
        """Returns the tomogram of shape (height, azimuth, range) as a read-only memory map."""
        return np.load(str(tomogram_path), mmap_mode="r", allow_pickle=False)

    def _reconstruct_slice(self, parameters_array : np.ndarray, h_val : float) -> np.ndarray:
        """Evaluates the fitted mixture at one height.

        Args:
            parameters_array : Parameter block of shape (3 * n_gaussians, azimuth, range).
            h_val            : Elevation the mixture is evaluated at, in metres.

        Returns:
            Mixture value of shape (azimuth, range).
        """
        return GaussianMixture.evaluate_slice(parameters_array, h_val, self.n_gaussians)

    def _contrast_and_r2_maps(self, tomogram : np.ndarray, parameters_array : np.ndarray, height_axis : np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
        """Streams the tomogram to build the contrast and reconstruction-quality maps.

        Args:
            tomogram         : Complex tomogram of shape (height, azimuth, range).
            parameters_array : Parameter stack of shape (3 * n_gaussians, azimuth, range).
            height_axis      : Elevation axis of shape (height,), in metres.

        Returns:
            Tuple of the peak-to-floor contrast in dB and the per-pixel R-squared of the
            mixture against the preprocessed profile, both of shape (azimuth, range).
        """
        H, Az, R    = tomogram.shape
        contrast_db = np.full ((Az, R), np.nan, dtype=np.float32)
        r2_map      = np.empty((Az, R),         dtype=np.float32)
        n_chunks    = -(-R // self.range_chunk)
        started     = perf_counter()
        last_line   = started

        with self.logger.track(transient=True) as progress:
            task = progress.add_task("  [section]Streaming range chunks for contrast and R²[/section]", total=n_chunks)

            for index, r_start in enumerate(range(0, R, self.range_chunk), start=1):
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

                progress.advance(task)

                now = perf_counter()
                if now - last_line >= self.LOG_EVERY_SECONDS:
                    last_line = now
                    self.logger.subsection(f"Range chunk {index}/{n_chunks} (bins up to {r_end} of {R}), {now - started:.0f}s elapsed")

        self.logger.subsection(f"Streamed {n_chunks} range chunks in {perf_counter() - started:.1f}s")
        return contrast_db, r2_map

    def _compute_global_summary(self, r2_map : np.ndarray, activity_map : np.ndarray) -> Dict[str, float]:
        """Summarises fit quality and the distribution of active-slot counts.

        Args:
            r2_map       : Per-pixel R-squared of shape (azimuth, range), NaN where unfitted.
            activity_map : Active-slot count of shape (azimuth, range).

        Returns:
            Mapping with pixel counts, the count of fitted pixels whose R-squared is
            undefined because their reference profile is constant, R-squared moments
            and percentiles over the finite values, and the fraction of pixels
            carrying each active-slot count.
        """
        r2_flat  = r2_map.reshape(-1).astype(np.float64)
        r2_valid = r2_flat[np.isfinite(r2_flat)]
        fitted   = activity_map.reshape(-1) > 0

        def _pct(q: float) -> float:
            """Returns the q-th percentile of the finite R-squared values, or NaN."""
            return float(np.percentile(r2_valid, q)) if r2_valid.size > 0 else float("nan")

        summary: Dict[str, float] = {
            **self.maps.occupancy_summary(activity_map),
            "r2_undefined_count" : float(R2.undefined_count(r2_flat[fitted])),
            "r2_mean"            : float(r2_valid.mean())      if r2_valid.size > 0 else float("nan"),
            "r2_median"          : float(np.median(r2_valid))  if r2_valid.size > 0 else float("nan"),
            "r2_std"             : float(r2_valid.std())       if r2_valid.size > 0 else float("nan"),
            "r2_p10"             : _pct(10),
            "r2_p25"             : _pct(25),
            "r2_p50"             : _pct(50),
            "r2_p75"             : _pct(75),
            "r2_p90"             : _pct(90),
            "r2_neg_frac"        : float((r2_valid < 0.0).mean()) if r2_valid.size > 0 else float("nan"),
        }

        return summary

    def _compute_snr_summary(self, snr_db_map : np.ndarray, r2_map : np.ndarray, best_k_map : Optional[np.ndarray], max_samples : int = 1_000_000) -> Dict[str, float]:
        """Summarises the contrast distribution and its relation to fit quality.

        Args:
            snr_db_map  : Peak-to-floor contrast of shape (azimuth, range), in dB.
            r2_map      : Per-pixel R-squared of shape (azimuth, range).
            best_k_map  : Selected model order of shape (azimuth, range), or None.
            max_samples : Cap on the number of pixels used for the correlations.

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
            parameters_array : Parameter stack of shape (3 * n_gaussians, azimuth, range).
            metadata         : Run metadata carrying ``height_range`` in metres.
            tomogram_path    : Path of the tomogram the fit was performed on.
            diagnostics      : Fitter diagnostics; model-order metrics are skipped when absent.

        Returns:
            Dictionary with the R-squared, activity and contrast maps, the elevation
            axis, the global, contrast and per-order summaries, and the per-slot,
            separation and model-order maps.
        """
        self.logger.section("[Fitting Metrics Calculation]")

        self.logger.subsection(f"Loading tomogram : {Path(tomogram_path).name}")
        tomogram     = self._open_tomogram(Path(tomogram_path))
        height_range = tuple(metadata["height_range"])
        height_axis  = GaussianAxis.build(float(height_range[0]), float(height_range[1]), tomogram.shape[0])

        self.logger.subsection(f"Tomogram shape  : {tomogram.shape}")
        self.logger.subsection(f"Height range    : [{height_range[0]:.1f}, {height_range[1]:.1f}] m")

        n_height   = int(tomogram.shape[0])
        truncation = f"bins >= {self.truncation_index} of {n_height} zeroed" if self.truncation_index < n_height else f"no bin truncated, the index lies beyond the {n_height} height bins"

        self.logger.subsection("Computing per-pixel peak-to-floor contrast map (peak over lowest-quartile profile amplitude, uncalibrated proxy)")
        self.logger.subsection(f"Applying fitter preprocessing for R² (threshold_factor={self.threshold_factor}, truncation_index={self.truncation_index}: {truncation})")
        self.logger.subsection(f"Computing per-pixel R² map against thresholded/truncated profile (memory-mapped, range chunks of {self.range_chunk} bins, float32)")
        snr_db_map, r2_map = self._contrast_and_r2_maps(tomogram, parameters_array, height_axis)

        del tomogram
        gc.collect()

        self.logger.subsection("Computing activity and spatial parameter maps")
        activity_map = self.maps.activity_map(parameters_array)

        self.logger.subsection("Masking R² to fitted pixels: pixels with no active Gaussian were never candidates for a fit")
        r2_map = np.where(activity_map > 0, r2_map, np.nan).astype(np.float32)

        gauss_maps   = self.maps.per_gaussian_maps(parameters_array)
        sep_maps     = self.maps.mu_separation_maps(parameters_array)
        summary      = self._compute_global_summary(r2_map, activity_map)

        self.logger.subsection("Counting active slots on the fitter's clamp bounds")
        census       = FitBoundCensus(height_axis, self.amp_threshold)
        bound_counts = census.count_stack(parameters_array, self.n_gaussians)
        census.report(bound_counts, self.logger, "Fit bounds")
        summary.update(census.fractions(bound_counts))

        k_maps    : Dict[str, np.ndarray] = {}
        k_summary : Dict[str, float]      = {}

        if diagnostics is not None and "best_k_map" in diagnostics:
            self.logger.subsection("Computing model-order selection diagnostics")
            k_maps, k_summary = self.k_diagnostics.run(diagnostics)

        best_k_map = k_maps["best_k_map"] if "best_k_map" in k_maps else None

        self.logger.subsection("Computing peak-to-floor contrast statistics and contrast-to-fit-quality relation")
        snr_summary = self._compute_snr_summary(snr_db_map, r2_map, best_k_map)

        self.logger.subsection(f"R² — mean={summary['r2_mean']:.4f} median={summary['r2_median']:.4f} neg_frac={summary['r2_neg_frac']:.4f} over the fitted pixels with a non-constant reference; {summary['r2_undefined_count']:.0f} fitted pixels have a constant reference profile and no R²")
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
