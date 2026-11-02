"""GPU-batched Gaussian-mixture fitting of tomographic elevation profiles.

Drives the three-phase extraction loop: CPU peak initialisation, a JAX Adam
kernel that fits every candidate mixture order K on device, and a background
scoring stage that picks the best K per pixel for each model-order penalty.
"""

from __future__ import annotations

import gc
import os
from concurrent.futures import ThreadPoolExecutor
from dataclasses        import dataclass
from pathlib            import Path
from time               import perf_counter
from typing             import Dict, Optional, Tuple

import numpy as np
import psutil

import jax
import jax.numpy as jnp

from configuration.param_extraction                import FitMode
from pipelines.processing.param_extraction.metrics import FitBoundCensus
from tools.data.gaussians                          import GaussianActivity
from tools.data.preprocessing                      import ProfilePreprocessor
from tools.monitoring.logger                       import Logger

from .initialiser import PeakInitialiser
from .kernels     import SigmaScan
from .selection   import BestKSelector, KernelBackendSelector


@dataclass
class ExtractionOutcome:
    """What one extraction group fitted, recorded into every permutation's run metadata.

    Attributes:
        n_height_bins      : Height bins of the fitted tomogram.
        total_pixels       : Pixels of the azimuth-range grid.
        active_pixels      : Pixels whose preprocessed peak cleared the activity threshold and were fitted.
        truncation_applied : Whether the truncation index lies inside the height axis, so truncation zeroed any bin.
        backend            : Kernel backend label naming the device platform and count.
        devices            : JAX devices the fit ran on, as strings.
        fit_seconds        : Wall-clock seconds of the fitting loop over every batch, mode and K.
    """

    n_height_bins      : int
    total_pixels       : int
    active_pixels      : int
    truncation_applied : bool
    backend            : str
    devices            : list
    fit_seconds        : float

    def to_metadata(self) -> dict:
        """Returns the outcome under the keys the run metadata records."""
        return {
            "n_height_bins"      : self.n_height_bins,
            "total_pixels"       : self.total_pixels,
            "active_pixels"      : self.active_pixels,
            "active_fraction"    : self.active_pixels / self.total_pixels,
            "truncation_applied" : self.truncation_applied,
            "backend"            : self.backend,
            "devices"            : list(self.devices),
            "fit_seconds"        : self.fit_seconds,
        }


class FitProgress:
    """Counts the fitting kernel calls of an extraction, drives its console bar and logs a periodic progress line.

    The unit of work is one kernel call on a chunk of up to gpu_pixel_batch_size
    pixels for one mode and one K. A batch's chunk count is known once the
    batch is loaded, so the total is extrapolated from the loaded batches until
    the last one is in. The console bar advances on every call; the log file
    gets one line per LOG_EVERY_SECONDS, since the bar never reaches it.

    Attributes:
        LOG_EVERY_SECONDS : Minimum seconds between two progress lines in the log.
        logger            : Logger receiving the progress lines.
        progress          : Rich progress handle the bar task lives in.
        task              : Bar task counting kernel calls.
        n_batches         : Number of range batches of the fit.
        planned           : Kernel calls of the batches loaded so far.
        batches_planned   : Number of batches whose kernel-call count is known.
        done              : Kernel calls finished so far.
        started           : perf_counter time the fit started.
        last_line         : perf_counter time of the last progress line.
    """

    LOG_EVERY_SECONDS = 300.0

    def __init__(self, logger: Logger, progress, n_batches: int) -> None:
        """Adds the bar task and starts the clock.

        Args:
            logger    : Logger receiving the progress lines.
            progress  : Rich progress handle from ``Logger.track``.
            n_batches : Number of range batches of the fit.
        """
        self.logger          = logger
        self.progress        = progress
        self.task            = progress.add_task("  [section]Fitting kernel chunks[/section]", total=None)
        self.n_batches       = n_batches
        self.planned         = 0
        self.batches_planned = 0
        self.done            = 0
        self.started         = perf_counter()
        self.last_line       = self.started

    @property
    def total(self) -> int:
        """Kernel calls of the whole fit, extrapolated from the loaded batches while some are still to load."""
        if self.batches_planned == 0:
            return 0

        remaining = self.n_batches - self.batches_planned

        return self.planned + round(self.planned / self.batches_planned * remaining)

    def plan_batch(self, n_active: int, chunk_size: int, n_modes: int, k_max: int) -> int:
        """Adds one loaded batch's kernel calls to the plan.

        Args:
            n_active   : Active pixels of the batch.
            chunk_size : Pixels per kernel call.
            n_modes    : Fit modes run on the batch.
            k_max      : Mixture orders fitted per mode.

        Returns:
            Kernel calls one mode and one K take on this batch.
        """
        n_chunks              = -(-n_active // chunk_size)
        self.planned         += n_chunks * n_modes * k_max
        self.batches_planned += 1

        self.progress.update(self.task, total=self.total)
        return n_chunks

    def advance(self, batch_tag: str, mode: str, K: int, chunk: int, n_chunks: int) -> None:
        """Counts one finished kernel call and logs a progress line once LOG_EVERY_SECONDS have passed.

        Args:
            batch_tag : Label of the range batch.
            mode      : Fit mode of the call.
            K         : Mixture order of the call.
            chunk     : One-based index of the chunk within this mode and K.
            n_chunks  : Chunks this mode and K take on the batch.
        """
        self.done += 1
        self.progress.advance(self.task)

        now = perf_counter()
        if now - self.last_line < self.LOG_EVERY_SECONDS:
            return

        self.last_line = now
        elapsed        = now - self.started
        eta            = elapsed / self.done * (self.total - self.done)

        self.logger.subsection(f"{batch_tag} | mode {mode} | K={K} | chunk {chunk}/{n_chunks} | {self.done:,}/{self.total:,} kernel calls | elapsed {elapsed / 60:.1f} min | ETA {eta / 60:.1f} min")


class AdamConvergence:
    """Sums the Adam loss trajectories and the still-improving pixels of every kernel call, per fit mode and K.

    A pixel counts as still improving when its loss fell by more than
    IMPROVEMENT_RTOL over the last tenth of the Adam steps, from the step
    ``SigmaScan.mark_step`` names to the final loss. The losses are those of
    the peak-normalised profiles the kernel fits.

    Attributes:
        IMPROVEMENT_RTOL     : Relative loss drop over the last tenth of the steps above which a pixel counts as still improving.
        WARN_IMPROVING_SHARE : Share of still-improving pixels at one mode and K above which the results warn that adam_steps may be too few.
        n_steps              : Adam steps per kernel call.
        loss_sum             : Per mode, the per-step loss summed over every fitted pixel, of shape (k_max, n_steps).
        pixels               : Per mode, the fitted pixels per K, of shape (k_max,).
        improving            : Per mode, the still-improving pixels per K, of shape (k_max,).
    """

    IMPROVEMENT_RTOL     = 0.01
    WARN_IMPROVING_SHARE = 0.1

    def __init__(self, modes : list, k_max : int, n_steps : int) -> None:
        """Zeroes the per-mode accumulators.

        Args:
            modes   : Fit modes of the extraction.
            k_max   : Largest mixture order fitted.
            n_steps : Adam steps per kernel call.
        """
        self.n_steps   = n_steps
        self.loss_sum  = {mode: np.zeros((k_max, n_steps), dtype=np.float64) for mode in modes}
        self.pixels    = {mode: np.zeros(k_max, dtype=np.int64) for mode in modes}
        self.improving = {mode: np.zeros(k_max, dtype=np.int64) for mode in modes}

    @classmethod
    def still_improving(cls, loss_mark : np.ndarray, final_mse : np.ndarray) -> int:
        """Returns how many pixels lost more than IMPROVEMENT_RTOL of their loss over the last tenth of the steps.

        Args:
            loss_mark : Per-pixel loss at the start of the last tenth of the steps, of shape (n,).
            final_mse : Per-pixel loss after the last step, of shape (n,).
        """
        return int(((loss_mark - final_mse) > cls.IMPROVEMENT_RTOL * loss_mark).sum())

    def describe(self, loss_curve : np.ndarray, n_pixels : int, n_improving : int) -> str:
        """Returns the mean loss at the first, middle and last step and the still-improving share of one batch, mode and K.

        Args:
            loss_curve  : Per-step loss summed over the pixels, of shape (n_steps,).
            n_pixels    : Pixels the curve sums over.
            n_improving : Pixels still improving at the end.
        """
        mean = loss_curve / max(n_pixels, 1)
        mid  = self.n_steps // 2

        return f"mean loss {mean[0]:.3e} at step 0, {mean[mid]:.3e} at step {mid}, {mean[-1]:.3e} at step {self.n_steps - 1}; {n_improving / max(n_pixels, 1):.1%} of pixels still improving by > {self.IMPROVEMENT_RTOL:.0%} over the last {self.n_steps - SigmaScan.mark_step(self.n_steps)} steps"

    def add(self, mode : str, K : int, loss_curve : np.ndarray, n_pixels : int, n_improving : int) -> None:
        """Adds one batch's sums for a mode and K to the totals.

        Args:
            mode        : Fit mode of the batch.
            K           : Mixture order of the batch.
            loss_curve  : Per-step loss summed over the batch's pixels, of shape (n_steps,).
            n_pixels    : Pixels the batch fitted.
            n_improving : Pixels of the batch still improving at the end.
        """
        self.loss_sum [mode][K - 1] += loss_curve
        self.pixels   [mode][K - 1] += n_pixels
        self.improving[mode][K - 1] += n_improving

    def report(self, logger : Logger) -> None:
        """Logs the still-improving share of every mode and K and warns above WARN_IMPROVING_SHARE.

        Args:
            logger : Logger receiving the lines and warnings.
        """
        for mode, pixels in self.pixels.items():
            shares = self.improving[mode] / np.maximum(pixels, 1)
            logger.subsection(f"Mode {mode} still improving at the last step, per K : {', '.join(f'K={K} {share:.1%}' for K, share in enumerate(shares, start=1))}")

            for K, share in enumerate(shares, start=1):
                if share > self.WARN_IMPROVING_SHARE:
                    logger.warning(f"Mode {mode}, K={K}: {share:.1%} of the fitted pixels still lost more than {self.IMPROVEMENT_RTOL:.0%} of their loss over the last {self.n_steps - SigmaScan.mark_step(self.n_steps)} of {self.n_steps} Adam steps; adam_steps may be too few for this fit to converge")

    def diagnostics(self, mode : str) -> Dict[str, np.ndarray]:
        """Returns a mode's convergence arrays as saved into fit_diagnostics.npz.

        Returns:
            Mapping with ``adam_loss_curve``, the mean per-step loss of shape (k_max, n_steps), and ``adam_improving_frac``, the still-improving share of shape (k_max,).
        """
        pixels = np.maximum(self.pixels[mode], 1)

        return {
            "adam_loss_curve"     : (self.loss_sum[mode] / pixels[:, None]).astype(np.float32),
            "adam_improving_frac" : (self.improving[mode] / pixels).astype(np.float32),
        }


class SigmaFittingExtractor:
    """Fits Gaussian mixtures to every active pixel of a tomogram on GPU.

    Attributes:
        modes               : Fit modes (see `FitMode`) deciding which of amplitude, mean and sigma are free parameters.
        lambda_values       : Model-order penalties applied per extra Gaussian when selecting the best K.
        k_max               : Largest mixture order fitted.
        mode_masks          : Per-mode gradient masks as (amplitude, mean, sigma) scalars.
        backend             : Kernel backend label naming the device platform and count the fit runs on.
        devices             : JAX devices the fit runs on.
        outcome             : Record of the last run's fitted pixels, truncation, backend and duration; None before run().
        bound_shares        : Per (mode, lambda_k) shares of the selected active slots whose sigma or mean ended on a clamp bound, from the last run; empty before run().
        BATCH_COPIES        : Range-batch-sized float32 arrays held at the peak of the load and fit overlap: the current batch's raw, normalised and active-row profiles and the three arrays of the batch loading ahead.
        RAM_WARN_FRACTION   : Share of the available host RAM above which the estimated footprint warns.
        MIN_ACTIVE_FRACTION : Share of the pixels below which an active-pixel count warns, pointing at a zero-filled crop or an activity threshold above the amplitude scale.
    """

    MAX_PENDING_SCORINGS = 2
    BATCH_COPIES         = 6
    RAM_WARN_FRACTION    = 0.8
    MIN_ACTIVE_FRACTION  = 0.5

    def __init__(
        self,
        logger              : Logger,
        modes               : list,
        lambda_values       : list,
        k_max               : int                 = 5,
        threshold_factor    : float               = 0.25,
        truncation_index    : int                 = 170,
        prominence_frac     : float               = 0.05,
        sigma_init_divisor  : float               = 1.0,
        activity_threshold  : float               = 1e-3,
        range_batch_size    : int                 = 256,
        adam_steps          : int                 = 2000,
        adam_lr             : float               = 1e-2,
        adam_b1             : float               = 0.9,
        adam_b2             : float               = 0.999,
        gpu_pixel_batch_size: int                 = 8192,
        init_workers        : Optional[int]       = None,
        peak_initialiser    : Optional[PeakInitialiser] = None,
        kernel_backend      : Optional[tuple]     = None,
    ) -> None:
        """Configures the fitting grid, peak initialiser and JAX kernel backend.

        Args:
            logger               : Logger used for section reporting.
            modes                : Fit-mode names resolved through `FitMode.free_flags`.
            lambda_values        : Model-order penalties, one output permutation each.
            k_max                : Maximum number of Gaussians fitted per pixel.
            threshold_factor     : Relative floor applied by `ProfilePreprocessor`.
            truncation_index     : Height-bin index above which profiles are cut.
            prominence_frac      : Peak prominence as a fraction of the profile max.
            sigma_init_divisor   : Divides the heuristic initial sigma in metres.
            activity_threshold   : Minimum profile peak for a pixel to be fitted.
            range_batch_size     : Number of range bins loaded per batch.
            adam_steps           : Adam iterations run inside the kernel.
            adam_lr              : Adam learning rate.
            adam_b1              : Adam first-moment decay.
            adam_b2              : Adam second-moment decay.
            gpu_pixel_batch_size : Pixels per kernel invocation.
            init_workers         : Process-pool size for peak initialisation; defaults to the CPUs available to this process, capped at 32.
            peak_initialiser     : Externally owned initialiser to reuse; a private one is created and closed by this extractor when omitted.
            kernel_backend       : Externally owned (kernel, n_devices, backend, devices) tuple; selected here when omitted.
        """

        self.logger               = logger
        self.modes                = list(modes)
        self.lambda_values        = [float(lambda_k) for lambda_k in lambda_values]
        self.k_max                = k_max
        self.threshold_factor     = threshold_factor
        self.truncation_index     = truncation_index
        self.prominence_frac      = prominence_frac
        self.sigma_init_divisor   = sigma_init_divisor
        self.activity_threshold   = activity_threshold
        self.range_batch_size     = range_batch_size
        self.adam_steps           = adam_steps
        self.adam_lr              = adam_lr
        self.adam_b1              = adam_b1
        self.adam_b2              = adam_b2
        self.gpu_pixel_batch_size = gpu_pixel_batch_size
        self._init_workers        = min(32, len(os.sched_getaffinity(0))) if init_workers is None else init_workers

        self.mode_masks = {}
        for mode in self.modes:
            fit_sigma, fit_amplitude, fit_mean = FitMode.free_flags(mode)
            self.mode_masks[mode] = (
                jnp.float32(1.0 if fit_amplitude else 0.0),
                jnp.float32(1.0 if fit_mean      else 0.0),
                jnp.float32(1.0 if fit_sigma     else 0.0),
            )

        if peak_initialiser is not None:
            self._peak_initialiser = peak_initialiser
            self._owns_initialiser = False
        else:
            self._peak_initialiser = PeakInitialiser(n_workers=self._init_workers)
            self._owns_initialiser = True

        self._best_k_selector = BestKSelector(k_max=k_max, logger=logger)

        if kernel_backend is not None:
            kernel, n_devices, backend, active_devices = kernel_backend
            self._owns_kernel                          = False
        else:
            kernel, n_devices, backend, active_devices = KernelBackendSelector().select()
            self._owns_kernel                          = True

        self._kernel      = kernel
        self._n_devices   = n_devices
        self.backend      = backend
        self.devices      = list(active_devices)
        self.outcome      : Optional[ExtractionOutcome] = None
        self.bound_shares : Dict[tuple, Dict[str, float]] = {}

        self.logger.section("[GPU Parameter Extractor]")
        self.logger.subsection(f"JAX active devices : {self.devices}")
        self.logger.subsection(f"Backend            : {backend}")
        self.logger.subsection(f"range_batch_size   : {range_batch_size}")
        self.logger.subsection(f"gpu_pixel_batch    : {gpu_pixel_batch_size}")
        self.logger.subsection(f"adam_steps         : {adam_steps}")
        self.logger.subsection(f"adam_lr            : {adam_lr}")
        self.logger.subsection(f"k_max              : {k_max}")
        self.logger.subsection(f"lambda_values      : {self.lambda_values}")
        self.logger.subsection(f"fit modes          : {self.modes}")
        self.logger.subsection(f"sigma_init_divisor : {sigma_init_divisor}")
        self.logger.subsection(f"activity_threshold : {self.activity_threshold}")
        self.logger.subsection(f"init_workers       : {self._peak_initialiser.n_workers} ({'in-process' if self._peak_initialiser.n_workers == 1 else 'process pool'}, {'shared by the entry' if not self._owns_initialiser else 'owned by this extractor'})")
        self.logger.subsection(f"n_devices          : {self._n_devices}")

        available_cpus = len(os.sched_getaffinity(0))
        if self._peak_initialiser.n_workers > available_cpus:
            self.logger.warning(f"The peak initialiser runs {self._peak_initialiser.n_workers} worker processes but only {available_cpus} CPUs are available to this process ({os.cpu_count()} on the host); the workers share those cores and Phase 1 slows down, so set parameter_workers to at most {available_cpus}")

    def _prepare_data(
        self,
        tomogram_path : Path,
        height_range  : Tuple[float, float],
    ) -> tuple:
        """Memory-maps the tomogram and derives the height axis and fit bounds.

        Args:
            tomogram_path : Path to a (height, azimuth, range) tomogram .npy.
            height_range  : Lowest and highest elevation of the height axis, in metres.

        Returns:
            Tuple of memmapped tomogram, its H/Az/R sizes, the numpy and JAX
            height axes in metres, the sigma and mean clamp bounds in metres,
            and the flattened parameter count 3 * k_max.
        """

        n_params_out = 3 * self.k_max

        tomogram_mmap = np.load(str(tomogram_path), mmap_mode="r", allow_pickle=False)
        H, Az, R      = tomogram_mmap.shape
        height_axis   = np.linspace(height_range[0], height_range[1], H, dtype=np.float32)
        height_ax_j   = jnp.array(height_axis)

        h_span = float(height_axis[-1] - height_axis[0])
        dh     = h_span / (H - 1)

        sigma_lower_j = jnp.float32(dh)
        sigma_upper_j = jnp.float32(h_span / 2.0)

        mu_lower_j = jnp.float32(height_axis[0])
        mu_upper_j = jnp.float32(height_axis[-1])

        sigma_guess = PeakInitialiser.sigma_guess(height_axis, self.k_max, self.sigma_init_divisor)
        if sigma_guess < dh:
            erasing_divisor = PeakInitialiser.sigma_base(height_axis, self.k_max) / dh
            self.logger.warning(f"sigma_init_divisor {self.sigma_init_divisor} places the initial sigma at {sigma_guess:.4f}, below the fit lower bound {dh:.4f}; the kernel clamps it, so every divisor above {erasing_divisor:.3f} starts this fit from the same sigma and produces identical parameters")

        if sigma_guess > h_span / 2.0:
            clamping_divisor = PeakInitialiser.sigma_base(height_axis, self.k_max) / (h_span / 2.0)
            self.logger.warning(f"sigma_init_divisor {self.sigma_init_divisor} places the initial sigma at {sigma_guess:.4f}, above the fit upper bound {h_span / 2.0:.4f}; the kernel clamps it, so every divisor below {clamping_divisor:.3f} starts this fit from the same sigma and produces identical parameters")

        self.logger.section("[Data Preparation]")
        self.logger.subsection(f"H            : {H}")
        self.logger.subsection(f"Az           : {Az}")
        self.logger.subsection(f"R            : {R}")
        self.logger.subsection(f"k_max        : {self.k_max}")
        self.logger.subsection(f"Total pixels : {R * Az:,}")
        self.logger.subsection(f"Batches      : {-(-R // self.range_batch_size)}")

        if self.truncation_index < H:
            self.logger.subsection(f"Truncation   : bins >= {self.truncation_index} zeroed ({H - self.truncation_index} of {H})")
        else:
            self.logger.warning(f"truncation_index {self.truncation_index} >= {H} height bins: no elevation bin is truncated on this tomogram, so the setting has no effect and every fit_truncation_index >= {H} produces the same run")

        return (
            tomogram_mmap, H, Az, R,
            height_axis, height_ax_j,
            sigma_lower_j, sigma_upper_j,
            mu_lower_j, mu_upper_j,
            n_params_out,
        )

    def _warmup_kernel(
        self,
        height_ax_j   : jnp.ndarray,
        H             : int,
        sigma_lower_j : jnp.ndarray,
        sigma_upper_j : jnp.ndarray,
        mu_lower_j    : jnp.ndarray,
        mu_upper_j    : jnp.ndarray,
    ) -> None:
        """Triggers JAX compilation of the fitting kernel on dummy inputs.

        Args:
            height_ax_j   : Height axis of shape (H,) in metres.
            H             : Number of height bins.
            sigma_lower_j : Lower sigma clamp in metres.
            sigma_upper_j : Upper sigma clamp in metres.
            mu_lower_j    : Lower mean clamp in metres.
            mu_upper_j    : Upper mean clamp in metres.
        """

        self.logger.section("[Kernel Compilation]")
        self.logger.subsection(f"Compiling JAX kernel (modes: {', '.join(self.modes)}) for K={self.k_max}")

        B = self.gpu_pixel_batch_size
        K = self.k_max

        dummy_s = jnp.ones((B, K),  dtype=jnp.float32) * 5.0
        dummy_p = jnp.ones((B, H),  dtype=jnp.float32)
        dummy_a = jnp.ones((B, K),  dtype=jnp.float32) * 0.5
        dummy_m = jnp.zeros((B, K), dtype=jnp.float32)

        amp_mask, mu_mask, sigma_mask = self.mode_masks[self.modes[0]]
        self._kernel(dummy_a, dummy_m, dummy_s, height_ax_j, dummy_p, amp_mask, mu_mask, sigma_mask, mu_lower_j, mu_upper_j, sigma_lower_j, sigma_upper_j, self.adam_steps, self.adam_lr, self.adam_b1, self.adam_b2)

        self.logger.subsection(f"Kernel compiled (K={K}, batch={B}, n_steps={self.adam_steps})")

    def _log_memory_budget(self, H: int, Az: int, R: int) -> None:
        """Logs the estimated host-RAM footprint of the fit against the available RAM and warns when it comes close.

        The output maps of every (mode, lambda) permutation take 20 * k_max + 2
        bytes per pixel (parameters, per-K MSE and penalised MSE in float32,
        the best-K map in int16) for the whole fit, and the range batches hold
        BATCH_COPIES arrays of range_batch_size x Az x H float32 at the peak of
        the load-ahead overlap. The peak-initialiser workers' copies are not
        counted.

        Args:
            H  : Number of height bins.
            Az : Number of azimuth lines.
            R  : Number of range bins.
        """
        n_permutations = len(self.modes) * len(self.lambda_values)
        maps_gb        = n_permutations * Az * R * (20 * self.k_max + 2) / 1e9
        batch_gb       = self.BATCH_COPIES * min(self.range_batch_size, R) * Az * H * 4 / 1e9
        available_gb   = psutil.virtual_memory().available / 1e9
        budget_gb      = self.RAM_WARN_FRACTION * available_gb

        self.logger.section("[Host Memory Budget]")
        self.logger.kv_table({
            "Output maps"        : f"{maps_gb:.2f} GB ({n_permutations} permutations x {Az} x {R} pixels x {20 * self.k_max + 2} B)",
            "Range batches"      : f"{batch_gb:.2f} GB ({self.BATCH_COPIES} arrays of {min(self.range_batch_size, R)} x {Az} x {H} float32, load-ahead included)",
            "Estimated total"    : f"{maps_gb + batch_gb:.2f} GB",
            "Available host RAM" : f"{available_gb:.2f} GB",
        })

        if maps_gb + batch_gb <= budget_gb:
            return

        per_range_bin_gb = self.BATCH_COPIES * Az * H * 4 / 1e9
        fitting_batch    = int((budget_gb - maps_gb) / per_range_bin_gb)

        if fitting_batch < 1:
            self.logger.warning(f"Estimated host-RAM footprint {maps_gb + batch_gb:.1f} GB exceeds {self.RAM_WARN_FRACTION:.0%} of the {available_gb:.1f} GB available, and the {maps_gb:.1f} GB of output maps alone leave no room for a range batch; fit fewer modes or lambdas per launch or a smaller crop, or the run may be OOM-killed with no error in its logs")
            return

        self.logger.warning(f"Estimated host-RAM footprint {maps_gb + batch_gb:.1f} GB exceeds {self.RAM_WARN_FRACTION:.0%} of the {available_gb:.1f} GB available; a range_batch_size of at most {fitting_batch} fits that budget, or the run may be OOM-killed with no error in its logs")

    def _load_batch(
        self,
        tomogram_mmap : np.ndarray,
        r_start       : int,
        R             : int,
        Az            : int,
        H             : int,
    ) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, int]:
        """Loads one range batch and returns raw, peak-normalised profiles.

        Args:
            tomogram_mmap : Memmapped complex tomogram of shape (H, Az, R).
            r_start       : First range bin of the batch.
            R             : Total number of range bins.
            Az            : Number of azimuth lines.
            H             : Number of height bins.

        Returns:
            Tuple of raw profiles of shape (r_count * Az, H), the same profiles
            divided by their peak, the peak scale of shape (r_count * Az, 1),
            an activity mask of shape (r_count * Az,), and the exclusive end
            range bin.
        """

        r_end = min(r_start + self.range_batch_size, R)
        r_c   = r_end - r_start
        raw   = np.abs(tomogram_mmap[:, :, r_start:r_end]).astype(np.float32, copy=False)
        raw   = ProfilePreprocessor.apply(raw, self.threshold_factor, self.truncation_index)

        pf     = raw.transpose(2, 1, 0).reshape(r_c * Az, H)
        pmax   = pf.max(axis=1, keepdims=True)
        active = GaussianActivity.is_active(pmax[:, 0], self.activity_threshold)
        scale  = np.where(active[:, None], pmax, 1.0).astype(np.float32)
        norm   = pf / scale

        del raw

        return pf, norm, scale, active, r_end

    @staticmethod
    def _pad_rows(arr : np.ndarray, target : int) -> np.ndarray:
        """Zero-pads a 2-D array to exactly `target` rows."""
        pad = target - arr.shape[0]
        if pad == 0:
            return np.ascontiguousarray(arr, dtype=np.float32)
        return np.concatenate([arr.astype(np.float32, copy=False), np.zeros((pad, arr.shape[1]), dtype=np.float32)], axis=0)

    def _fit_all_K(
        self,
        inits         : dict,
        prof_norm_all : np.ndarray,
        scale_all     : np.ndarray,
        height_ax_j   : jnp.ndarray,
        sigma_lower_j : jnp.ndarray,
        sigma_upper_j : jnp.ndarray,
        mu_lower_j    : jnp.ndarray,
        mu_upper_j    : jnp.ndarray,
        N_act         : int,
        mode          : str,
        batch_tag     : str,
        fit_progress  : FitProgress,
        n_chunks      : int,
        convergence   : AdamConvergence,
    ) -> dict:
        """Fits every mixture order from 1 to k_max for one batch and mode.

        Args:
            inits         : Per-K tuple of initial amplitudes, means and sigmas, each of shape (N_act, K).
            prof_norm_all : Peak-normalised profiles of shape (N_act, H).
            scale_all     : Per-pixel peak scale of shape (N_act,).
            height_ax_j   : Height axis of shape (H,) in metres.
            sigma_lower_j : Lower sigma clamp in metres.
            sigma_upper_j : Upper sigma clamp in metres.
            mu_lower_j    : Lower mean clamp in metres.
            mu_upper_j    : Upper mean clamp in metres.
            N_act         : Number of active pixels in the batch.
            mode          : Fit mode selecting which parameters receive gradients.
            batch_tag     : Label used in log sections.
            fit_progress  : Kernel-call counter advanced after every call.
            n_chunks      : Kernel calls one K takes on this batch.
            convergence   : Accumulator of the Adam loss trajectories, logged per K and summed over batches.

        Returns:
            Mapping from K to (amplitudes, means in metres, sigmas in metres,
            per-pixel MSE) with the parameter arrays shaped (N_act, K) and the
            MSE shaped (N_act,).
        """

        gpu_results                   = {}
        B                             = self.gpu_pixel_batch_size
        amp_mask, mu_mask, sigma_mask = self.mode_masks[mode]
        t_mode                        = perf_counter()

        self.logger.section(f"[{batch_tag} | Phase 2 — GPU Fitting (mode {mode})]")

        for K in range(1, self.k_max + 1):
            amps_raw, mus, sigs_init = inits[K]
            amps_norm  = amps_raw / scale_all[:, None]
            final_amps = np.empty((N_act, K), dtype=np.float32)
            final_mus  = np.empty((N_act, K), dtype=np.float32)
            final_sigs = np.empty((N_act, K), dtype=np.float32)
            final_mse  = np.empty(N_act,      dtype=np.float32)
            loss_curve = np.zeros(self.adam_steps, dtype=np.float64)
            improving  = 0

            pending = None
            for i_start in range(0, N_act, B):
                i_end = min(i_start + B, N_act)
                out_a, out_m, out_s, out_e, out_l, out_k = self._kernel.fit(
                    jnp.array(self._pad_rows(amps_norm    [i_start:i_end], B)),
                    jnp.array(self._pad_rows(mus          [i_start:i_end], B)),
                    jnp.array(self._pad_rows(sigs_init    [i_start:i_end], B)),
                    height_ax_j,
                    jnp.array(self._pad_rows(prof_norm_all[i_start:i_end], B)),
                    amp_mask,
                    mu_mask,
                    sigma_mask,
                    mu_lower_j,
                    mu_upper_j,
                    sigma_lower_j,
                    sigma_upper_j,
                    self.adam_steps,
                    self.adam_lr,
                    self.adam_b1,
                    self.adam_b2,
                )

                if pending is not None:
                    chunk_curve, chunk_improving = self._materialize_chunk(pending, final_amps, final_mus, final_sigs, final_mse)
                    loss_curve += chunk_curve
                    improving  += chunk_improving
                pending = (out_a, out_m, out_s, out_e, out_l, out_k, i_start, i_end)

                fit_progress.advance(batch_tag, mode, K, i_start // B + 1, n_chunks)

            if pending is not None:
                chunk_curve, chunk_improving = self._materialize_chunk(pending, final_amps, final_mus, final_sigs, final_mse)
                loss_curve += chunk_curve
                improving  += chunk_improving

            gpu_results[K] = (final_amps, final_mus, final_sigs, final_mse)
            convergence.add(mode, K, loss_curve, N_act, improving)
            self.logger.subsection(f"K={K} done ({n_chunks} kernel calls) | {convergence.describe(loss_curve, N_act, improving)}")

        gc.collect()

        self.logger.subsection(f"Mode {mode} GPU fit elapsed : {perf_counter() - t_mode:.1f}s")

        return gpu_results

    @staticmethod
    def _materialize_chunk(pending : tuple, final_amps : np.ndarray, final_mus : np.ndarray, final_sigs : np.ndarray, final_mse : np.ndarray) -> Tuple[np.ndarray, int]:
        """Copies one pending device chunk into the batch result arrays and returns its convergence sums.

        Args:
            pending    : Tuple of device amplitudes, means, sigmas, MSE, per-step summed loss, per-pixel loss at the start of the last tenth of steps, and the inclusive-exclusive row range they belong to.
            final_amps : Destination amplitudes of shape (N_act, K).
            final_mus  : Destination means of shape (N_act, K), in metres.
            final_sigs : Destination sigmas of shape (N_act, K), in metres.
            final_mse  : Destination per-pixel MSE of shape (N_act,).

        Returns:
            Tuple of the chunk's per-step loss summed over its pixels, of shape (n_steps,), and its count of still-improving pixels; padded rows fit a zero profile at zero loss and add nothing.
        """
        out_a, out_m, out_s, out_e, out_l, out_k, i_start, i_end = pending
        n_chunk = i_end - i_start

        final_amps[i_start:i_end] = np.array(out_a[:n_chunk], dtype=np.float32)
        final_mus [i_start:i_end] = np.array(out_m[:n_chunk], dtype=np.float32)
        final_sigs[i_start:i_end] = np.array(out_s[:n_chunk], dtype=np.float32)
        final_mse [i_start:i_end] = np.array(out_e[:n_chunk], dtype=np.float32)

        return np.array(out_l, dtype=np.float64), AdamConvergence.still_improving(np.array(out_k[:n_chunk], dtype=np.float32), final_mse[i_start:i_end])

    def _init_batch(
        self,
        profiles_flat : np.ndarray,
        profiles_norm : np.ndarray,
        active        : np.ndarray,
        safe_scale    : np.ndarray,
        height_axis   : np.ndarray,
        batch_tag     : str,
    ) -> Optional[tuple]:
        """Runs CPU peak initialisation for the active pixels of one batch.

        Args:
            profiles_flat : Raw profiles of shape (n_total, H).
            profiles_norm : Peak-normalised profiles of shape (n_total, H).
            active        : Boolean activity mask of shape (n_total,).
            safe_scale    : Peak scale of shape (n_total, 1).
            height_axis   : Height axis of shape (H,) in metres.
            batch_tag     : Label used in log sections.

        Returns:
            Tuple of per-K initialisations, active normalised profiles of shape
            (N_act, H), active scales of shape (N_act,), the active row indices
            and their count; None when the batch holds no active pixel.
        """

        active_idx = np.where(active)[0]
        N_act      = len(active_idx)

        if N_act == 0:
            return None

        prof_raw_all  = profiles_flat[active_idx]
        prof_norm_all = profiles_norm[active_idx].astype(np.float32)
        scale_all     = safe_scale[active_idx, 0]

        self.logger.section(f"[{batch_tag} | Phase 1 — CPU Initialisation]")
        self.logger.subsection(f"Active pixels : {N_act}")
        self.logger.subsection(f"K             : {self.k_max} (shared init)")
        self.logger.subsection(f"Workers       : {self._peak_initialiser.n_workers} / {len(os.sched_getaffinity(0))} CPUs available to this process ({os.cpu_count()} on the host)")

        t_init                   = perf_counter()
        amps_km, mus_km, sigs_km = self._peak_initialiser.run(prof_raw_all, height_axis, self.k_max, self.prominence_frac, self.sigma_init_divisor)
        inits = {K: (amps_km[:, :K].copy(), mus_km[:, :K].copy(), sigs_km[:, :K].copy()) for K in range(1, self.k_max + 1)}

        self.logger.subsection(f"Init shared for all {self.k_max} K values and {len(self.modes)} modes")
        self.logger.subsection(f"Init elapsed : {perf_counter() - t_init:.1f}s")

        return inits, prof_norm_all, scale_all, active_idx, N_act

    def _score_and_store(
        self,
        mode          : str,
        gpu_results   : dict,
        scale_all     : np.ndarray,
        active_idx    : np.ndarray,
        n_total       : int,
        n_params_out  : int,
        outputs       : Dict[tuple, dict],
        r_start       : int,
        r_end         : int,
        Az            : int,
        batch_tag     : str,
        census        : FitBoundCensus,
    ) -> None:
        """Selects the best K per pixel, writes the batch into the maps and adds its clamp-bound counts.

        Args:
            mode         : Fit mode the results belong to.
            gpu_results  : Per-K fit results as returned by `_fit_all_K`.
            scale_all    : Active-pixel peak scales of shape (N_act,), used to undo amplitude normalisation.
            active_idx   : Row indices of the active pixels within the batch.
            n_total      : Number of pixels in the batch, active or not.
            n_params_out : Flattened parameter count 3 * k_max.
            outputs      : Destination maps keyed by (mode, lambda_k).
            r_start      : First range bin of the batch.
            r_end        : Exclusive last range bin of the batch.
            Az           : Number of azimuth lines.
            batch_tag    : Label used in log sections.
            census       : Clamp-bound census of the fit, whose counts are summed into each permutation's ``bounds`` entry.
        """

        t_score = perf_counter()
        r_count = r_end - r_start
        mse_all = self._best_k_selector.score(gpu_results, batch_tag=f"{batch_tag} | mode {mode}")

        for lambda_k in self.lambda_values:
            best_params, mse_act, pen_act, best_idx_act, bound_counts = self._best_k_selector.select(gpu_results, mse_all, scale_all, lambda_k, n_params_out, census, batch_tag=f"{batch_tag} | mode {mode}")

            output     = np.zeros((n_total, n_params_out),       dtype=np.float32)
            mse_out    = np.full ((n_total, self.k_max), np.nan, dtype=np.float32)
            pen_out    = np.full ((n_total, self.k_max), np.nan, dtype=np.float32)
            best_k_out = np.zeros(n_total,                       dtype=np.int16)

            output    [active_idx] = best_params
            mse_out   [active_idx] = mse_act
            pen_out   [active_idx] = pen_act
            best_k_out[active_idx] = best_idx_act + 1

            maps = outputs[(mode, lambda_k)]
            maps["params"][:, :, r_start:r_end] = output.reshape(r_count, Az, n_params_out).transpose(2, 1, 0)
            maps["mse"   ][:, :, r_start:r_end] = mse_out.reshape(r_count, Az, self.k_max).transpose(2, 1, 0)
            maps["pen"   ][:, :, r_start:r_end] = pen_out.reshape(r_count, Az, self.k_max).transpose(2, 1, 0)
            maps["best_k"][:,    r_start:r_end] = best_k_out.reshape(r_count, Az).T

            FitBoundCensus.add(maps["bounds"], bound_counts)

        self.logger.subsection(f"{batch_tag} | mode {mode} select+store elapsed : {perf_counter() - t_score:.1f}s")

    @staticmethod
    def _throttle_scorings(futures : list, max_pending : int) -> None:
        """Blocks until fewer than `max_pending` scoring futures are unfinished.

        Args:
            futures     : Scoring futures submitted so far.
            max_pending : Backlog size above which the caller waits.

        Raises:
            Exception : Whatever a completed scoring future raised.
        """
        for future in futures:
            if future.done():
                future.result()

        pending = [future for future in futures if not future.done()]
        while len(pending) >= max_pending:
            pending[0].result()
            pending = [future for future in futures if not future.done()]

    def _run_fitting(
        self,
        tomogram_mmap : np.ndarray,
        height_axis   : np.ndarray,
        height_ax_j   : jnp.ndarray,
        sigma_lower_j : jnp.ndarray,
        sigma_upper_j : jnp.ndarray,
        mu_lower_j    : jnp.ndarray,
        mu_upper_j    : jnp.ndarray,
        Az            : int,
        R             : int,
        H             : int,
        n_params_out  : int,
        outputs       : Dict[tuple, dict],
        census        : FitBoundCensus,
        convergence   : AdamConvergence,
    ) -> int:
        """Streams range batches through load, init, fit and scoring stages.

        Loading runs one batch ahead on its own thread and scoring runs in the
        background so the GPU stays busy while results are written.

        Args:
            tomogram_mmap : Memmapped complex tomogram of shape (H, Az, R).
            height_axis   : Height axis of shape (H,) in metres.
            height_ax_j   : Device copy of the height axis.
            sigma_lower_j : Lower sigma clamp in metres.
            sigma_upper_j : Upper sigma clamp in metres.
            mu_lower_j    : Lower mean clamp in metres.
            mu_upper_j    : Upper mean clamp in metres.
            Az            : Number of azimuth lines.
            R             : Number of range bins.
            H             : Number of height bins.
            n_params_out  : Flattened parameter count 3 * k_max.
            outputs       : Destination maps keyed by (mode, lambda_k).
            census        : Clamp-bound census handed to every scoring job.
            convergence   : Accumulator of the Adam loss trajectories of every kernel call.

        Returns:
            Number of active pixels that were fitted.
        """

        n_batches = -(-R // self.range_batch_size)

        self.logger.section("[Range Bin Loading]")
        self.logger.subsection("Monolithic range batches, scoring runs in background while the next mode fits")
        self.logger.subsection(f"Range batches : {n_batches} x {self.range_batch_size} bins")

        total_attempted = 0
        empty_spans     = []

        with self.logger.track(transient=True) as progress:
            fit_progress = FitProgress(self.logger, progress, n_batches)

            with ThreadPoolExecutor(max_workers=1) as load_pool, ThreadPoolExecutor(max_workers=1) as score_pool:
                r               = 0
                batch_index     = 0
                score_futures   = []
                prefetch_future = load_pool.submit(self._load_batch, tomogram_mmap, r, R, Az, H)

                try:
                    while r < R:
                        t_wait = perf_counter()
                        profiles_flat, profiles_norm, safe_scale, active, r_end = prefetch_future.result()
                        self.logger.subsection(f"Load wait : {perf_counter() - t_wait:.1f}s")

                        r_start = r
                        batch_index += 1
                        batch_tag    = f"Batch {batch_index}/{n_batches}"

                        if r_end < R:
                            prefetch_future = load_pool.submit(self._load_batch, tomogram_mmap, r_end, R, Az, H)

                        total_attempted += int(active.sum())
                        n_chunks         = fit_progress.plan_batch(int(active.sum()), self.gpu_pixel_batch_size, len(self.modes), self.k_max)

                        batch = self._init_batch(profiles_flat, profiles_norm, active, safe_scale, height_axis, batch_tag)

                        if batch is None:
                            empty_spans.append(f"{r_start}-{r_end}")
                        else:
                            inits, prof_norm_all, scale_all, active_idx, N_act = batch
                            n_total                                            = profiles_flat.shape[0]

                            for mode in self.modes:
                                gpu_results = self._fit_all_K(inits, prof_norm_all, scale_all, height_ax_j, sigma_lower_j, sigma_upper_j, mu_lower_j, mu_upper_j, N_act, mode, batch_tag, fit_progress, n_chunks, convergence)

                                t_throttle = perf_counter()
                                self._throttle_scorings(score_futures, self.MAX_PENDING_SCORINGS)
                                throttle_wait = perf_counter() - t_throttle
                                if throttle_wait > 1.0:
                                    self.logger.subsection(f"{batch_tag} | mode {mode} GPU idle on scoring backlog : {throttle_wait:.1f}s")
                                score_futures.append(score_pool.submit(self._score_and_store, mode, gpu_results, scale_all, active_idx, n_total, n_params_out, outputs, r_start, r_end, Az, batch_tag, census))

                        del profiles_flat, profiles_norm, safe_scale, active, batch
                        gc.collect()

                        self.logger.subsection(f"{batch_tag} dispatched — range bins {r_start}-{r_end} of {R}, {fit_progress.done:,}/{fit_progress.total:,} kernel calls, {perf_counter() - fit_progress.started:.1f}s elapsed, process RSS {psutil.Process().memory_info().rss / 1e9:.2f} GB")

                        r = r_end

                    for future in score_futures:
                        future.result()

                except Exception:
                    prefetch_future.cancel()
                    for future in score_futures:
                        future.cancel()
                    raise

        self.logger.subsection(f"Total pixels   : {R * Az:,}")
        self.logger.subsection(f"Active pixels  : {total_attempted:,}")

        if empty_spans:
            self.logger.warning(f"{len(empty_spans)} of {n_batches} range batches held no pixel above activity_threshold {self.activity_threshold} and were not fitted: range bins {', '.join(empty_spans)}")

        return total_attempted

    def run(
        self,
        tomogram_path : Path,
        height_range  : Tuple[float, float],
    ) -> Dict[tuple, Tuple[np.ndarray, Dict[str, np.ndarray]]]:
        """Fits the whole tomogram and returns one parameter map per permutation.

        Args:
            tomogram_path : Path to a (height, azimuth, range) tomogram .npy.
            height_range  : Lowest and highest elevation in metres.

        Returns:
            Mapping from (mode, lambda_k) to a parameter map of shape
            (3 * k_max, Az, R) — amplitude, mean in metres and sigma in metres
            interleaved per Gaussian — and a diagnostics dict holding
            `mse_per_k` and `penalised_per_k` of shape (k_max, Az, R), the
            `best_k_map` of shape (Az, R), the scalar `lambda_k`, the mode's
            mean Adam loss per step `adam_loss_curve` of shape
            (k_max, adam_steps) and its still-improving share
            `adam_improving_frac` of shape (k_max,).

        Raises:
            ValueError : If no pixel cleared the activity threshold, so nothing was fitted.
        """

        (
            tomogram_mmap, H, Az, R,
            height_axis, height_ax_j,
            sigma_lower_j, sigma_upper_j,
            mu_lower_j, mu_upper_j,
            n_params_out,
        ) = self._prepare_data(tomogram_path, height_range)

        self._warmup_kernel(height_ax_j, H, sigma_lower_j, sigma_upper_j, mu_lower_j, mu_upper_j)
        self._log_memory_budget(H, Az, R)

        census      = FitBoundCensus(height_axis, self.activity_threshold)
        convergence = AdamConvergence(self.modes, self.k_max, self.adam_steps)
        outputs     = {}
        for mode in self.modes:
            for lambda_k in self.lambda_values:
                outputs[(mode, lambda_k)] = {
                    "params" : np.zeros((n_params_out, Az, R),        dtype=np.float32),
                    "mse"    : np.full ((self.k_max, Az, R), np.nan,  dtype=np.float32),
                    "pen"    : np.full ((self.k_max, Az, R), np.nan,  dtype=np.float32),
                    "best_k" : np.zeros((Az, R),                      dtype=np.int16),
                    "bounds" : {"active_slots": 0, "sigma_at_lower": 0, "sigma_at_upper": 0, "mu_at_bound": 0},
                }

        t_fit = perf_counter()

        try:
            total_attempted = self._run_fitting(
                tomogram_mmap, height_axis, height_ax_j,
                sigma_lower_j, sigma_upper_j,
                mu_lower_j, mu_upper_j,
                Az, R, H, n_params_out, outputs, census, convergence,
            )
        finally:
            if self._owns_initialiser:
                self._peak_initialiser.close()
            if self._owns_kernel:
                jax.clear_caches()
            gc.collect()

        if total_attempted == 0:
            raise ValueError(f"No pixel of {tomogram_path} has a preprocessed peak above activity_threshold {self.activity_threshold} (threshold_factor {self.threshold_factor}, truncation_index {self.truncation_index}), so nothing was fitted and the all-zero labels are not saved; check the crop against the zero-filled edge of the scene and the threshold against the tomogram's amplitude scale")

        self.outcome = ExtractionOutcome(
            n_height_bins      = int(H),
            total_pixels       = int(R * Az),
            active_pixels      = int(total_attempted),
            truncation_applied = bool(self.truncation_index < H),
            backend            = self.backend,
            devices            = [str(device) for device in self.devices],
            fit_seconds        = perf_counter() - t_fit,
        )

        self.logger.section("[Results]")
        self.logger.subsection(f"Active pixels fitted : {total_attempted:,} / {R * Az:,} ({total_attempted / (R * Az):.1%})")

        if total_attempted / (R * Az) < self.MIN_ACTIVE_FRACTION:
            self.logger.warning(f"Only {total_attempted / (R * Az):.1%} of the pixels cleared activity_threshold {self.activity_threshold}, below {self.MIN_ACTIVE_FRACTION:.0%}; the crop may reach into the zero-filled edge of the scene or the threshold may sit above the tomogram's amplitude scale")
        self.logger.subsection(f"Permutations fitted  : {len(outputs)} ({len(self.modes)} modes x {len(self.lambda_values)} lambdas)")
        self.logger.subsection(f"Backend              : {self.backend} on {self.outcome.devices}")
        self.logger.subsection(f"Fit elapsed          : {self.outcome.fit_seconds:.1f}s")

        convergence.report(self.logger)

        for (mode, lambda_k), maps in outputs.items():
            census.report(maps["bounds"], self.logger, f"mode {mode} | lambda_k={lambda_k:g}")
            self.bound_shares[(mode, lambda_k)] = FitBoundCensus.fractions(maps["bounds"])

        results = {}
        for key, maps in outputs.items():
            mode, lambda_k = key
            diagnostics    = {
                "mse_per_k"       : maps["mse"],
                "penalised_per_k" : maps["pen"],
                "best_k_map"      : maps["best_k"],
                "lambda_k"        : np.float32(lambda_k),
                **convergence.diagnostics(mode),
            }
            results[key] = (maps["params"], diagnostics)

        return results
