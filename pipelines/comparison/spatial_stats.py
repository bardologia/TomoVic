"""Spatial dispersion and profile contrast statistics over per-pixel maps.

Provides the block-wise variability measures and the correlation length used to
read the bias-variance trade-off of multilook windows and Gaussian fits.
"""

from __future__ import annotations

import numpy as np

from typing import Tuple

from tools.monitoring.logger import Logger


class SpatialDispersion:
    """Block-wise and autocorrelation statistics of a two-dimensional field."""

    EPSILON = 1e-9

    @staticmethod
    def _blocks(field: np.ndarray, block: int) -> np.ndarray:
        """Tiles a field into flattened square blocks.

        Args:
            field: Per-pixel map of shape (azimuth, range).
            block: Side length in pixels of the square tiles; the trailing
                partial tiles are cropped away.

        Returns:
            Array of shape (n_tiles, block * block) holding each tile's pixels.
        """
        rows = field.shape[0] // block
        cols = field.shape[1] // block

        cropped = field[:rows * block, :cols * block]
        tiled   = cropped.reshape(rows, block, cols, block).transpose(0, 2, 1, 3)

        return tiled.reshape(rows * cols, block * block)

    @staticmethod
    def block_cv(field: np.ndarray, block: int) -> float:
        """Returns the median within-block coefficient of variation.

        Args:
            field: Per-pixel map of shape (azimuth, range).
            block: Side length in pixels of the square tiles.

        Returns:
            Median over tiles of standard deviation divided by mean, with tiles
            whose mean is at or below EPSILON excluded.
        """
        tiles = SpatialDispersion._blocks(field, block)

        mean = np.nanmean(tiles, axis=1)
        std  = np.nanstd(tiles, axis=1)

        valid = mean > SpatialDispersion.EPSILON
        cv    = np.where(valid, std / np.where(valid, mean, 1.0), np.nan)

        return float(np.nanmedian(cv))

    @staticmethod
    def block_std(field: np.ndarray, block: int) -> float:
        """Returns the median within-block standard deviation.

        Args:
            field: Per-pixel map of shape (azimuth, range), in the field's own
                units (metres for a height map).
            block: Side length in pixels of the square tiles.

        Returns:
            Median over tiles of the within-tile standard deviation.
        """
        tiles = SpatialDispersion._blocks(field, block)
        return float(np.nanmedian(np.nanstd(tiles, axis=1)))

    @staticmethod
    def autocorr_length(field: np.ndarray, axis: int = 0, max_lines: int = 256) -> float:
        """Returns the 1/e correlation length of a field along one axis.

        The autocorrelation is computed by FFT over mean-removed lines, averaged
        across lines, and read at the first lag whose normalised value falls
        below exp(-1).

        Args:
            field: Per-pixel map of shape (azimuth, range).
            axis: Axis along which the correlation length is measured.
            max_lines: Maximum number of lines subsampled for the estimate.

        Returns:
            Correlation length in pixels; the full extent when the
            autocorrelation never drops below exp(-1), NaN when every line is
            constant.
        """
        moved  = np.moveaxis(field, axis, 0)
        length = moved.shape[0]

        columns = moved.reshape(length, -1)
        count   = columns.shape[1]

        if count > max_lines:
            picks   = np.linspace(0, count - 1, max_lines).astype(np.int64)
            columns = columns[:, picks]

        centred = columns.astype(np.float64) - np.nanmean(columns, axis=0, keepdims=True)
        centred = np.nan_to_num(centred, nan=0.0)

        spectrum = np.fft.rfft(centred, n=2 * length, axis=0)
        acf      = np.fft.irfft(np.abs(spectrum) ** 2, axis=0)[:length]

        zero_lag = acf[0]
        valid    = zero_lag > SpatialDispersion.EPSILON
        acf      = acf[:, valid] / zero_lag[valid]

        if acf.shape[1] == 0:
            return float("nan")

        mean_acf = acf.mean(axis=1)
        below    = np.where(mean_acf < np.exp(-1.0))[0]

        return float(below[0]) if below.size > 0 else float(length)


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
