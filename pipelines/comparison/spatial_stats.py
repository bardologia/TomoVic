"""Spatial dispersion statistics over per-pixel maps.

Provides the block-wise variability measures and the correlation length used to
read the bias-variance trade-off of multilook windows and Gaussian fits.
"""

from __future__ import annotations

import numpy as np


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
