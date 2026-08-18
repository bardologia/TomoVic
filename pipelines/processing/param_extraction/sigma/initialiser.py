"""Peak-based initial guesses for Gaussian-mixture profile fitting.

Locates prominent peaks in each elevation profile with `scipy.signal.find_peaks`
and turns them into amplitude, mean and sigma starting points, optionally over a
process pool.
"""

from __future__ import annotations

from concurrent.futures import ProcessPoolExecutor
from functools          import partial
from typing             import Tuple

import numpy as np
from scipy.signal import find_peaks


class PeakInitialiser:
    """Builds Gaussian-mixture initialisations from profile peak detection.

    Attributes:
        n_workers: Number of worker processes; 1 keeps the work in-process.
    """

    def __init__(self, n_workers : int = 1) -> None:
        """Creates the initialiser and warms its process pool when parallel.

        Args:
            n_workers: Worker processes to spawn, floored at 1.
        """
        self.n_workers = max(1, int(n_workers))
        self._pool     = None

        if self.n_workers > 1:
            self._pool = ProcessPoolExecutor(max_workers=self.n_workers)
            list(self._pool.map(abs, range(self.n_workers)))

    @staticmethod
    def _prominence_worker(raw_chunk : np.ndarray, height_axis : np.ndarray, K : int, sigma_guess : float, min_dist : int, prominence_frac : float) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Initialises one chunk of profiles from their prominent peaks.

        Peaks are ranked by prominence; when fewer than K are found the
        remaining slots are filled by greedily taking residual maxima, and a
        flat profile falls back to K evenly spaced height bins.

        Args:
            raw_chunk: Raw profiles of shape (chunk_N, H).
            height_axis: Height axis of shape (H,) in metres.
            K: Number of Gaussians to initialise.
            sigma_guess: Initial standard deviation in metres.
            min_dist: Minimum peak separation in height bins.
            prominence_frac: Peak prominence as a fraction of the profile max.

        Returns:
            Tuple of amplitudes, means in metres and sigmas in metres, each of
            shape (chunk_N, K).
        """
        chunk_N, H = raw_chunk.shape
        amps = np.zeros((chunk_N, K), dtype=np.float32)
        mus  = np.zeros((chunk_N, K), dtype=np.float32)
        sigs = np.full ((chunk_N, K), sigma_guess, dtype=np.float32)

        for n in range(chunk_N):
            raw  = raw_chunk[n]
            pmax = raw.max()
            if pmax < 1e-10:
                idxs = np.linspace(0, H - 1, K, dtype=int)
            else:
                peaks, props = find_peaks(raw, prominence=pmax * prominence_frac, distance=min_dist)

                if len(peaks) > 0:
                    peaks = peaks[np.argsort(props["prominences"])[::-1]]

                if len(peaks) >= K:
                    idxs = peaks[:K]

                elif len(peaks) > 0:
                    residual = raw.copy()
                    extra    = []

                    for p in peaks:
                        lo = max(0, p - min_dist)
                        hi = min(H, p + min_dist + 1)
                        residual[lo:hi] = 0.0

                    for _ in range(K - len(peaks)):
                        ei = int(np.argmax(residual))
                        extra.append(ei)
                        lo = max(0, ei - min_dist)
                        hi = min(H, ei + min_dist + 1)
                        residual[lo:hi] = 0.0

                    idxs = np.concatenate([peaks, np.array(extra, dtype=int)])

                else:
                    idxs = np.linspace(0, H - 1, K, dtype=int)

            for g, idx in enumerate(idxs[:K]):
                amps[n, g] = max(float(raw[idx]), 1e-10)
                mus [n, g] = float(height_axis[idx])

        return amps, mus, sigs

    @staticmethod
    def sigma_base(height_axis : np.ndarray, K : int) -> float:
        """Returns the heuristic initial sigma in metres before any division.

        Args:
            height_axis: Height axis of shape (H,) in metres.
            K: Number of Gaussians the height span is shared by.

        Returns:
            The larger of two height bins and one eighth of the span per
            Gaussian, in metres.
        """
        h_span = float(height_axis[-1] - height_axis[0])
        dh     = float(height_axis[1] - height_axis[0])

        return max(2.0 * dh, h_span / (8.0 * K))

    @classmethod
    def sigma_guess(cls, height_axis : np.ndarray, K : int, sigma_divisor : float) -> float:
        """Returns the initial sigma in metres after applying the divisor."""
        return cls.sigma_base(height_axis, K) / max(float(sigma_divisor), 1e-6)

    def run(self, prof_raw : np.ndarray, height_axis : np.ndarray, K : int, prominence_frac : float = 0.05, sigma_divisor : float = 1.0) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Initialises every profile, splitting the work across the pool.

        Args:
            prof_raw: Raw profiles of shape (N, H).
            height_axis: Height axis of shape (H,) in metres.
            K: Number of Gaussians to initialise.
            prominence_frac: Peak prominence as a fraction of the profile max.
            sigma_divisor: Divides the heuristic initial sigma.

        Returns:
            Tuple of amplitudes, means in metres and sigmas in metres, each of
            shape (N, K).
        """
        N, H        = prof_raw.shape
        dh          = float(height_axis[1] - height_axis[0])
        sigma_base  = self.sigma_base(height_axis, K)
        sigma_guess = self.sigma_guess(height_axis, K, sigma_divisor)
        min_dist    = max(1, int(sigma_base / dh))
        raw         = prof_raw.astype(np.float32, copy=False)

        chunk_size = max(1, -(-N // (self.n_workers * 2)))
        chunks     = [raw[i:i + chunk_size] for i in range(0, N, chunk_size)]

        worker_fn  = partial(
            self._prominence_worker,
            height_axis     = height_axis,
            K               = K,
            sigma_guess     = sigma_guess,
            min_dist        = min_dist,
            prominence_frac = prominence_frac,
        )

        chunk_results = list(self._pool.map(worker_fn, chunks)) if self._pool is not None else [worker_fn(chunk) for chunk in chunks]

        amps = np.concatenate([r[0] for r in chunk_results], axis=0)
        mus  = np.concatenate([r[1] for r in chunk_results], axis=0)
        sigs = np.concatenate([r[2] for r in chunk_results], axis=0)

        return amps, mus, sigs

    def close(self) -> None:
        """Shuts the worker pool down, cancelling anything still queued."""
        if self._pool is not None:
            self._pool.shutdown(wait=True, cancel_futures=True)
