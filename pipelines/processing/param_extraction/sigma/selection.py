"""Model-order selection and kernel backend choice for sigma fitting.

Picks the best number of Gaussians per pixel under a penalised-MSE criterion and
decides between the jitted single-device and pmapped multi-device Adam kernels.
"""

from __future__ import annotations

import os
from typing import Dict, Tuple

import numpy as np

import jax

from pipelines.processing.param_extraction.metrics import FitBoundCensus
from tools.monitoring.logger                       import Logger

from .kernels import PmapSigmaAdamKernel, SigmaAdamKernel


class BestKSelector:
    """Chooses the mixture order that minimises penalised reconstruction error.

    Attributes:
        k_max : Largest mixture order considered.
    """

    def __init__(self, k_max : int, logger : Logger) -> None:
        """Stores the selection ceiling and the logger.

        Args:
            k_max  : Largest mixture order considered.
            logger : Logger used for section reporting.
        """
        self.k_max  = k_max
        self.logger = logger

    def score(self, gpu_results : Dict[int, tuple], batch_tag : str = "") -> np.ndarray:
        """Stacks the per-K fit errors into one array.

        Scoring runs on the extractor's background thread while the main
        thread opens the next mode's fitting section, so it announces itself
        with a subsection: a section would restart the logger's shared section
        clock and misattribute the '(+duration)' of both threads' sections.

        Args:
            gpu_results : Mapping from K to a fit tuple whose fourth element is the per-pixel MSE of shape (N_act,).
            batch_tag   : Label used in the log section header.

        Returns:
            Per-pixel MSE of shape (N_act, k_max) in float64.
        """
        tag = f"{batch_tag} | " if batch_tag else ""

        self.logger.subsection(f"{tag}Phase 3 — best-K selection")

        mse_all = np.stack([gpu_results[K][3] for K in range(1, self.k_max + 1)], axis=1).astype(np.float64)

        return mse_all

    def select(
        self,
        gpu_results   : Dict[int, tuple],
        mse_all       : np.ndarray,
        scale_all     : np.ndarray,
        lambda_k      : float,
        n_params_out  : int,
        census        : FitBoundCensus,
        batch_tag     : str = "",
    ) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, Dict[str, int]]:
        """Selects the best K per pixel, assembles its flattened parameters and counts the winners on a clamp bound.

        Args:
            gpu_results  : Mapping from K to (normalised amplitudes, means in metres, sigmas in metres, MSE).
            mse_all      : Per-pixel MSE of shape (N_act, k_max).
            scale_all    : Per-pixel peak scale of shape (N_act,) used to restore physical amplitudes.
            lambda_k     : Penalty added per Gaussian in the selection criterion.
            n_params_out : Flattened parameter count 3 * k_max.
            census       : Clamp-bound census built on the fit's height axis and activity threshold.
            batch_tag    : Label used in log lines.

        Returns:
            Tuple of the selected parameters of shape (N_act, n_params_out) with
            amplitude, mean and sigma interleaved per Gaussian, the per-K MSE
            and penalised MSE of shape (N_act, k_max), the zero-based index of
            the winning K of shape (N_act,), and the census counts of the
            selected active slots on a sigma or mean bound.
        """

        N_act = mse_all.shape[0]
        tag   = f"{batch_tag} | " if batch_tag else ""

        penalised_all = mse_all + lambda_k * np.arange(1, self.k_max + 1, dtype=np.float64)[None, :]
        best_K_idx    = penalised_all.argmin(axis=1)

        best_params = np.zeros((N_act, n_params_out), dtype=np.float32)
        for K in range(1, self.k_max + 1):
            mask = best_K_idx == (K - 1)

            if not mask.any():
                continue

            amps_norm, mus, final_sigs, _ = gpu_results[K]
            idx      = np.where(mask)[0]
            amps_out = amps_norm[idx] * scale_all[idx, None]

            best_params[np.ix_(idx, list(range(0, K * 3, 3)))] = amps_out
            best_params[np.ix_(idx, list(range(1, K * 3, 3)))] = mus       [idx]
            best_params[np.ix_(idx, list(range(2, K * 3, 3)))] = final_sigs[idx]

        k_dist       = {K: int((best_K_idx == K - 1).sum()) for K in range(1, self.k_max + 1)}
        bound_counts = census.count_rows(best_params)

        self.logger.subsection(f"{tag}Best-K at lambda_k={lambda_k:g}")
        self.logger.subsection(f"Best-K dist     : {k_dist}")
        self.logger.subsection(f"Mean MSE (best) : {float(mse_all[np.arange(N_act), best_K_idx].mean()):.5f}")
        self.logger.subsection(f"On clamp bounds : sigma at dh {bound_counts['sigma_at_lower']:,}, sigma at h_span/2 {bound_counts['sigma_at_upper']:,}, mean at an axis end {bound_counts['mu_at_bound']:,} of {bound_counts['active_slots']:,} active slots")

        return best_params, mse_all.astype(np.float32), penalised_all.astype(np.float32), best_K_idx.astype(np.int16), bound_counts


class KernelBackendSelector:
    """Picks the fitting kernel matching the available JAX devices.

    Attributes:
        GPU_PLATFORMS     : JAX platform names that count as a GPU.
        require_gpu       : Whether a device list without a GPU is refused instead of fitted on CPU.
        requested_gpu_ids : GPU indices the launch asked for, named in the refusal.
    """

    GPU_PLATFORMS = ("gpu", "cuda", "rocm")

    def __init__(self, require_gpu: bool = False, requested_gpu_ids: list | None = None) -> None:
        """Sets whether a CPU-only JAX is refused and which GPU ids the launch requested.

        Args:
            require_gpu       : Whether to raise when JAX sees no GPU; the entry point sets it because a whole-scene Adam fit on CPU takes days, while tests and in-process callers may fit small crops on CPU.
            requested_gpu_ids : GPU indices the launch asked for, quoted in the refusal message.
        """
        self.require_gpu       = require_gpu
        self.requested_gpu_ids = list(requested_gpu_ids) if requested_gpu_ids is not None else []

    def select(self) -> Tuple[object, int, str, list]:
        """Returns the fitting kernel, device count, backend label and devices.

        GPU devices are preferred over the default device list, more than one
        active device selects the pmapped kernel, and the label names the real
        platform and device count so a CPU fallback shows in every log line
        that prints it.

        Raises:
            RuntimeError : If require_gpu is set and JAX sees no GPU, naming the devices it does see, the CUDA_VISIBLE_DEVICES mask and the requested GPU ids.
        """
        devices        = jax.devices()
        gpu_devices    = [d for d in devices if d.platform in self.GPU_PLATFORMS]
        active_devices = gpu_devices if gpu_devices else devices

        if self.require_gpu and not gpu_devices:
            mask = os.environ.get("CUDA_VISIBLE_DEVICES", "unset")
            raise RuntimeError(f"No GPU is visible to JAX: jax.devices() = {devices}, CUDA_VISIBLE_DEVICES = {mask}, requested gpu_device_ids = {self.requested_gpu_ids}. A whole-scene Adam fit on CPU takes days, so the fallback is refused; install a CUDA-enabled jaxlib or fix the device mask")

        n_devices = len(active_devices)
        platform  = active_devices[0].platform
        kernel    = PmapSigmaAdamKernel(active_devices) if n_devices > 1 else SigmaAdamKernel()
        backend   = f"{'pmap' if n_devices > 1 else 'jit'} ({n_devices} {platform} device{'s' if n_devices > 1 else ''})"

        return kernel, n_devices, backend, active_devices
