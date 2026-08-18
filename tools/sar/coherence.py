"""Boxcar-averaged interferometric coherence estimation from complex SAR images."""

from __future__ import annotations

from typing import Optional, Tuple

import numpy as np

from scipy.ndimage import uniform_filter


class ComplexSmoother:
    """Applies a boxcar (uniform) filter to real or complex-valued arrays.

    Attributes:
        window: Per-axis boxcar size in pixels, as (azimuth, range).
    """

    def __init__(self, window: Tuple[int, int]) -> None:
        """Stores the per-axis boxcar window.

        Args:
            window: Boxcar size in pixels per axis, as (azimuth, range).
        """
        self.window = tuple(int(w) for w in window)

    def smooth(self, array: np.ndarray) -> np.ndarray:
        """Returns the boxcar average of an array, filtering real and imaginary parts separately.

        Args:
            array: Real or complex array of shape (azimuth, range).

        Returns:
            Smoothed array of the same shape and dtype family as the input.
        """
        if np.iscomplexobj(array):
            return uniform_filter(array.real, self.window) + 1j * uniform_filter(array.imag, self.window)
        return uniform_filter(array, self.window)


class CoherenceEstimator:
    """Estimates interferometric coherence magnitude and phase over a boxcar window.

    Attributes:
        smoother: Boxcar smoother applied to the cross-correlation and the powers.
    """

    def __init__(self, window: Tuple[int, int] = (7, 7)) -> None:
        """Builds the estimator around a boxcar estimation window.

        Args:
            window: Coherence estimation window in pixels, as (azimuth, range).
        """
        self.smoother = ComplexSmoother(window)

    def _complex_coherence(self, primary: np.ndarray, secondary: np.ndarray, flattening_phase: Optional[np.ndarray]) -> np.ndarray:
        """Returns the complex coherence of two co-registered images, zeroed where either image is zero.

        Args:
            primary: Complex primary image of shape (azimuth, range).
            secondary: Complex secondary image of shape (azimuth, range).
            flattening_phase: Phase in radians of shape (azimuth, range) removed
                from the cross-correlation before smoothing, or None.

        Returns:
            Complex coherence of shape (azimuth, range).
        """
        cross = primary * np.conj(secondary)
        if flattening_phase is not None:
            cross = cross * np.exp(-1j * flattening_phase)

        numerator   = self.smoother.smooth(cross)
        denominator = np.sqrt(self.smoother.smooth(np.abs(primary) ** 2) * self.smoother.smooth(np.abs(secondary) ** 2))

        with np.errstate(all="ignore"):
            coherence = numerator / denominator

        coherence[np.abs(primary * secondary) == 0] = 0
        return coherence

    def estimate(self, primary: np.ndarray, secondary: np.ndarray, flattening_phase: Optional[np.ndarray] = None) -> Tuple[np.ndarray, np.ndarray]:
        """Returns coherence magnitude and phase for a pair of co-registered images.

        Args:
            primary: Complex primary image of shape (azimuth, range).
            secondary: Complex secondary image of shape (azimuth, range).
            flattening_phase: Phase in radians of shape (azimuth, range) removed
                before smoothing, or None.

        Returns:
            Tuple of magnitude clipped to [0, 1] and phase in radians, both of
            shape (azimuth, range).
        """
        coherence = self._complex_coherence(primary, secondary, flattening_phase)

        magnitude = np.clip(np.nan_to_num(np.abs(coherence)), 0.0, 1.0)
        phase     = np.nan_to_num(np.angle(coherence))

        return magnitude, phase

    def estimate_flattened(self, primary_amplitude: np.ndarray, interferogram: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
        """Returns coherence for an already flattened interferogram and its primary image.

        Args:
            primary_amplitude: Complex primary image of shape (azimuth, range).
            interferogram: Flattened complex interferogram of shape (azimuth, range).

        Returns:
            Tuple of coherence magnitude in [0, 1] and phase in radians, both of
            shape (azimuth, range).
        """
        return self.estimate(primary_amplitude, np.conj(interferogram))
