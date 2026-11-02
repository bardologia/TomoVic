"""Per-pixel example figures for a parameter run.

Samples pixels grouped by a per-pixel order map and, for each, draws the raw
elevation profile together with the Gaussian mixture the parameters describe, its
components and the residual. The fitted route groups by selected model order and
adds the fitter's target profile and R-squared; the injected route groups by
active-slot count and draws the parameters as they came, since no fit of ours
took place.
"""

from __future__ import annotations

import gc
from pathlib import Path
from typing  import Dict, List, Tuple

import matplotlib

matplotlib.use("Agg")
import matplotlib.cm     as cm
import matplotlib.pyplot as plt
import numpy             as np

from tools.reporting.plotting import PlotBase
from tools.data.preprocessing import ProfilePreprocessor
from tools.data.gaussians     import GaussianActivity, GaussianMixture
from tools.monitoring.logger  import Logger


class PixelExampleBase(PlotBase):
    """Shared sampling, profile reading and drawing of per-pixel example figures.

    Attributes:
        n_gaussians   : Number of Gaussian slots in the parameter stack.
        logger        : Logger for the plotting report.
        n_fits_per_k  : Number of example pixels sampled per group.
        amp_threshold : Amplitude above which a Gaussian component is drawn.
        fig_dpi       : Figure resolution used while rendering.
        save_dpi      : Resolution the PNGs are written at.
    """

    SEED = 42

    def __init__(self, n_gaussians : int, logger : Logger, n_fits_per_k : int, amp_threshold : float, fig_dpi : int = 150, save_dpi : int = 300) -> None:
        """Fixes the slot count, the sample size per group and the drawing threshold.

        Args:
            n_gaussians   : Number of Gaussian slots in the parameter stack.
            logger        : Logger for the plotting report.
            n_fits_per_k  : Number of example pixels sampled per group.
            amp_threshold : Amplitude above which a Gaussian component is drawn.
            fig_dpi       : Figure resolution used while rendering.
            save_dpi      : Resolution the PNGs are written at.
        """
        self.n_gaussians   = n_gaussians
        self.logger        = logger
        self.n_fits_per_k  = n_fits_per_k
        self.amp_threshold = amp_threshold
        self.fig_dpi       = fig_dpi
        self.save_dpi      = save_dpi

    def _select_pixels_by_group(self, group_map : np.ndarray, eligible : np.ndarray) -> Dict[int, np.ndarray]:
        """Samples example pixel coordinates for every group value from 1 to the slot count.

        Args:
            group_map : Integer group of every pixel, of shape (azimuth, range).
            eligible  : Boolean mask of the same shape; pixels outside it are never sampled.

        Returns:
            Mapping from group value to an array of shape (n_selected, 2) holding the
            (azimuth, range) indices of the sampled pixels.
        """
        rng    = np.random.default_rng(self.SEED)
        flat_g = group_map.reshape(-1)
        flat_e = eligible.reshape(-1)
        W      = group_map.shape[1]

        groups : Dict[int, np.ndarray] = {}

        for K in range(1, self.n_gaussians + 1):
            idx = np.where(flat_e & (flat_g == K))[0]

            if idx.size == 0:
                groups[K] = np.empty((0, 2), dtype=np.int32)
                continue

            chosen    = rng.choice(idx, size=min(self.n_fits_per_k, idx.size), replace=False)
            groups[K] = np.stack([(chosen // W).astype(np.int32), (chosen % W).astype(np.int32)], axis=1)

        return groups

    @staticmethod
    def _all_pixels(pixels_by_group : Dict[int, np.ndarray]) -> np.ndarray:
        """Concatenates the sampled pixels of every group into one (n_pixels, 2) array."""
        non_empty = [px for px in pixels_by_group.values() if px.shape[0] > 0]

        return np.concatenate(non_empty, axis=0) if non_empty else np.empty((0, 2), dtype=np.int32)

    def _read_raw_profiles(self, tomogram_path : Path, all_pixels : np.ndarray) -> Dict[Tuple[int, int], np.ndarray]:
        """Reads the raw amplitude profile of each sampled pixel from the memory-mapped tomogram.

        Args:
            tomogram_path : Path of the tomogram of shape (height, azimuth, range).
            all_pixels    : Pixel indices of shape (n_pixels, 2) as (azimuth, range).

        Returns:
            Mapping from (azimuth, range) to the raw amplitude profile of shape (height,).
        """
        tomogram_mmap = np.load(str(tomogram_path), mmap_mode="r")

        raw_profiles : Dict[Tuple[int, int], np.ndarray] = {}
        for az, rg in all_pixels.tolist():
            raw_profiles[(az, rg)] = np.abs(np.array(tomogram_mmap[:, az, rg])).astype(np.float32)

        del tomogram_mmap
        gc.collect()

        return raw_profiles

    def _reconstruct_pixel(self, params : np.ndarray, height_axis : np.ndarray) -> Tuple[np.ndarray, List[np.ndarray]]:
        """Evaluates one pixel's mixture and its individual components.

        Args:
            params      : Parameter vector of shape (3 * n_gaussians,) for a single pixel.
            height_axis : Elevation axis of shape (height,), in metres.

        Returns:
            Tuple of the mixture of shape (height,) and the per-component profiles.
        """
        return GaussianMixture.evaluate_pixel(params, height_axis, self.n_gaussians)

    def _draw_components(self, ax : plt.Axes, height_axis : np.ndarray, comps : List[np.ndarray], params : np.ndarray, comp_colors : list) -> None:
        """Fills and outlines every component whose amplitude clears the drawing threshold.

        Args:
            ax          : Axes the components are drawn on.
            height_axis : Elevation axis of shape (height,), in metres.
            comps       : Per-component profiles, each of shape (height,).
            params      : Parameter vector of shape (3 * n_gaussians,) for this pixel.
            comp_colors : Colour per Gaussian slot.
        """
        for k, comp in enumerate(comps):
            if GaussianActivity.is_active(float(params[3 * k]), self.amp_threshold):
                ax.fill_between(height_axis, comp, alpha=0.20, color=comp_colors[k], zorder=2)
                ax.plot(height_axis, comp, color=comp_colors[k], lw=0.9, alpha=0.85, label=f"$g_{{{k + 1}}}$")

    def _plot_pixel_residual(self, height_axis : np.ndarray, residual : np.ndarray, title : str, ylabel : str, path : Path) -> Path:
        """Saves one pixel's signed residual against elevation.

        Args:
            height_axis : Elevation axis of shape (height,), in metres.
            residual    : Signed residual of shape (height,).
            title       : Figure title.
            ylabel      : Label of the residual axis.
            path        : Destination of the figure.

        Returns:
            The saved figure path.
        """
        fig, ax = plt.subplots(figsize=(5.6, 2.8))
        ax.plot(height_axis, residual, color="0.35", lw=0.9, zorder=3)
        ax.axhline(0.0, color="black", lw=0.7)
        ax.fill_between(height_axis, residual, 0.0, where=residual >= 0, color="#1f77b4", alpha=0.25, zorder=2)
        ax.fill_between(height_axis, residual, 0.0, where=residual < 0,  color="#d62728", alpha=0.25, zorder=2)

        ax.set_title(title, fontsize=10)
        ax.set_xlabel(r"height $h$ [m]")
        ax.set_ylabel(ylabel)
        ax.grid(True, which="major", lw=0.25, alpha=0.40)
        fig.tight_layout()

        return self._save(fig, path)

    @staticmethod
    def _group_dir(out_dir : Path, K : int) -> Path:
        """Creates and returns the ``k<K>`` subdirectory the group's figures are written to."""
        k_dir = out_dir / f"k{K}"
        k_dir.mkdir(parents=True, exist_ok=True)

        return k_dir


class ExampleFitPlotter(PixelExampleBase):
    """Renders example elevation-profile fits sampled per selected model order.

    Attributes:
        threshold_factor : Peak fraction below which profile bins were zeroed by the fitter.
        truncation_index : Elevation bin above which the profile was truncated by the fitter.
    """

    def __init__(
        self,
        n_gaussians      : int,
        logger           : Logger,
        threshold_factor : float,
        truncation_index : int,
        n_fits_per_k     : int,
        amp_threshold    : float,
        fig_dpi          : int = 150,
        save_dpi         : int = 300,
    ) -> None:
        """Configures the example fit plotter to mirror the fitter's preprocessing.

        Args:
            n_gaussians      : Number of Gaussian slots in the parameter stack.
            logger           : Logger for the plotting report.
            threshold_factor : Peak fraction below which profile bins were zeroed.
            truncation_index : Elevation bin above which the profile was truncated.
            n_fits_per_k     : Number of example pixels sampled per selected model order.
            amp_threshold    : Amplitude above which a Gaussian component is drawn.
            fig_dpi          : Figure resolution used while rendering.
            save_dpi         : Resolution the PNGs are written at.
        """
        super().__init__(n_gaussians, logger, n_fits_per_k, amp_threshold, fig_dpi, save_dpi)

        self.threshold_factor = threshold_factor
        self.truncation_index = truncation_index

    def _extract_pixel_profiles(self, tomogram_path : Path, all_pixels : np.ndarray) -> Dict[Tuple[int, int], Tuple[np.ndarray, np.ndarray]]:
        """Reads the raw and preprocessed elevation profile of each sampled pixel.

        Args:
            tomogram_path : Path of the tomogram of shape (height, azimuth, range).
            all_pixels    : Pixel indices of shape (n_pixels, 2) as (azimuth, range).

        Returns:
            Mapping from (azimuth, range) to the raw amplitude profile and the
            thresholded/truncated fit target, both of shape (height,).
        """
        raw_profiles = self._read_raw_profiles(tomogram_path, all_pixels)

        return {pixel: (raw, ProfilePreprocessor.apply(raw, self.threshold_factor, self.truncation_index)) for pixel, raw in raw_profiles.items()}

    def _plot_pixel_fit(self, height_axis, raw, profile, total, comps, params, comp_colors, k_color, k_label, az, rg, r2_val, k_dir) -> Path:
        """Saves one pixel's fit figure with the raw profile, target, mixture and components.

        Args:
            height_axis : Elevation axis of shape (height,), in metres.
            raw         : Raw amplitude profile of shape (height,).
            profile     : Thresholded/truncated fit target of shape (height,).
            total       : Fitted mixture of shape (height,).
            comps       : Per-component profiles, each of shape (height,).
            params      : Parameter vector of shape (3 * n_gaussians,) for this pixel.
            comp_colors : Colour per Gaussian slot.
            k_color     : Colour used for the mixture curve.
            k_label     : Title fragment naming the selected model order.
            az          : Azimuth index of the pixel.
            rg          : Range index of the pixel.
            r2_val      : R-squared of this pixel's fit.
            k_dir       : Directory the figure is written to.

        Returns:
            The saved figure path.
        """
        fig, ax = plt.subplots(figsize=(5.6, 4.4))
        ax.plot(height_axis, raw,     color="0.62",    lw=1.0, label="raw profile", zorder=3)
        ax.plot(height_axis, profile, color="black",   lw=1.5, label="fit target", zorder=4)
        ax.plot(height_axis, total,   color=k_color,   lw=1.4, ls="--", label="fit", zorder=5)

        self._draw_components(ax, height_axis, comps, params, comp_colors)

        ax.set_title(f"Example fit — {k_label}\naz={az},  rg={rg},  $R^2={r2_val:.3f}$", fontsize=10)
        ax.set_xlabel(r"height $h$ [m]")
        ax.set_ylabel(r"backscatter intensity")
        ax.grid(True, which="major", lw=0.25, alpha=0.40)
        ax.legend(fontsize=8, framealpha=0.90, ncol=2)
        fig.tight_layout()

        return self._save(fig, k_dir / f"az{az}_rg{rg}_fit.png")

    def _plot_example_fits(
        self,
        parameters_array : np.ndarray,
        pixel_profiles   : Dict[Tuple[int, int], Tuple[np.ndarray, np.ndarray]],
        height_axis      : np.ndarray,
        pixels_by_k      : Dict[int, np.ndarray],
        r2_map           : np.ndarray,
        out_dir          : Path,
    ) -> Dict[str, Path]:
        """Saves the fit and residual figures of every sampled pixel, grouped by order.

        Args:
            parameters_array : Parameter stack of shape (3 * n_gaussians, azimuth, range).
            pixel_profiles   : Mapping from (azimuth, range) to the raw and target profiles.
            height_axis      : Elevation axis of shape (height,), in metres.
            pixels_by_k      : Sampled pixel indices per selected model order.
            r2_map           : Per-pixel R-squared of shape (azimuth, range).
            out_dir          : Directory the per-order subdirectories are created under.

        Returns:
            Mapping from figure name to the saved PNG path.
        """
        comp_colors = [cm.tab10(i) for i in range(self.n_gaussians)]
        saved       : Dict[str, Path] = {}

        for K, pixels in pixels_by_k.items():
            if pixels.shape[0] == 0:
                continue

            k_color = cm.tab10((K - 1) % 10)
            k_label = rf"$K^*={K}$  ({K} Gaussian{'s' if K > 1 else ''})"
            k_dir   = self._group_dir(out_dir, K)

            for az, rg in pixels.tolist():
                raw, profile = pixel_profiles[(az, rg)]
                raw          = raw.astype(np.float64)
                profile      = profile.astype(np.float64)
                params       = parameters_array[:, az, rg].astype(np.float64)
                total, comps = self._reconstruct_pixel(params, height_axis.astype(np.float64))
                residual     = profile - total
                r2_val       = float(r2_map[az, rg]) if np.isfinite(r2_map[az, rg]) else float("nan")

                residual_title = f"Fit residual — az={az},  rg={rg},  $R^2={r2_val:.3f}$"
                residual_label = r"$\varepsilon = \mathrm{data} - \mathrm{fit}$"

                saved[f"k{K}_az{az}_rg{rg}_fit"]      = self._plot_pixel_fit(height_axis, raw, profile, total, comps, params, comp_colors, k_color, k_label, az, rg, r2_val, k_dir)
                saved[f"k{K}_az{az}_rg{rg}_residual"] = self._plot_pixel_residual(height_axis, residual, residual_title, residual_label, k_dir / f"az{az}_rg{rg}_residual.png")

        return saved

    def run(
        self,
        parameters_array : np.ndarray,
        best_k_map       : np.ndarray,
        r2_map           : np.ndarray,
        height_axis      : np.ndarray,
        tomogram_path    : Path,
        out_dir          : Path,
    ) -> Dict[str, Path]:
        """Samples pixels per model order and renders their fit and residual figures.

        Args:
            parameters_array : Parameter stack of shape (3 * n_gaussians, azimuth, range).
            best_k_map       : Selected model order of shape (azimuth, range).
            r2_map           : Per-pixel R-squared of the same shape; non-finite pixels are skipped.
            height_axis      : Elevation axis of shape (height,), in metres.
            tomogram_path    : Path of the tomogram of shape (height, azimuth, range).
            out_dir          : Directory the per-order subdirectories are created under.

        Returns:
            Mapping from figure name to the saved PNG path.
        """
        self.logger.subsection("Loading tomogram for example fit plots (memory-mapped)")

        pixels_by_k = self._select_pixels_by_group(best_k_map, np.isfinite(r2_map))
        all_pixels  = self._all_pixels(pixels_by_k)

        self.logger.subsection(f"Extracting {all_pixels.shape[0]} pixel profiles for example fits")
        pixel_profiles = self._extract_pixel_profiles(tomogram_path, all_pixels)

        self.logger.subsection(f"Plotting example fits  ({self.n_fits_per_k} pixels, up to {self.n_gaussians} K groups)")
        return self._plot_example_fits(parameters_array, pixel_profiles, height_axis, pixels_by_k, r2_map, out_dir)


class InjectedExamplePlotter(PixelExampleBase):
    """Renders example pixels of an injected run: raw profile, injected mixture and components.

    Pixels are grouped by their active-slot count, the quantity an injected run has
    in place of a selected model order. No fit target or R-squared is drawn, because
    the preprocessing and scoring of the external fitter are unknown here.
    """

    def _plot_pixel_mixture(self, height_axis, raw, total, comps, params, comp_colors, k_color, k_label, az, rg, k_dir) -> Path:
        """Saves one pixel's figure with the raw profile, the injected mixture and its components.

        Args:
            height_axis : Elevation axis of shape (height,), in metres.
            raw         : Raw amplitude profile of shape (height,).
            total       : Injected mixture of shape (height,).
            comps       : Per-component profiles, each of shape (height,).
            params      : Parameter vector of shape (3 * n_gaussians,) for this pixel.
            comp_colors : Colour per Gaussian slot.
            k_color     : Colour used for the mixture curve.
            k_label     : Title fragment naming the active-slot count.
            az          : Azimuth index of the pixel.
            rg          : Range index of the pixel.
            k_dir       : Directory the figure is written to.

        Returns:
            The saved figure path.
        """
        fig, ax = plt.subplots(figsize=(5.6, 4.4))
        ax.plot(height_axis, raw,   color="0.62",  lw=1.0, label="raw profile", zorder=3)
        ax.plot(height_axis, total, color=k_color, lw=1.4, ls="--", label="injected mixture", zorder=5)

        self._draw_components(ax, height_axis, comps, params, comp_colors)

        ax.set_title(f"Injected mixture — {k_label}\naz={az},  rg={rg}", fontsize=10)
        ax.set_xlabel(r"height $h$ [m]")
        ax.set_ylabel(r"backscatter intensity")
        ax.grid(True, which="major", lw=0.25, alpha=0.40)
        ax.legend(fontsize=8, framealpha=0.90, ncol=2)
        fig.tight_layout()

        return self._save(fig, k_dir / f"az{az}_rg{rg}_mixture.png")

    def _plot_example_mixtures(
        self,
        parameters_array : np.ndarray,
        raw_profiles     : Dict[Tuple[int, int], np.ndarray],
        height_axis      : np.ndarray,
        pixels_by_k      : Dict[int, np.ndarray],
        out_dir          : Path,
    ) -> Dict[str, Path]:
        """Saves the mixture and residual figures of every sampled pixel, grouped by active-slot count.

        Args:
            parameters_array : Parameter stack of shape (3 * n_gaussians, azimuth, range).
            raw_profiles     : Mapping from (azimuth, range) to the raw amplitude profile.
            height_axis      : Elevation axis of shape (height,), in metres.
            pixels_by_k      : Sampled pixel indices per active-slot count.
            out_dir          : Directory the per-count subdirectories are created under.

        Returns:
            Mapping from figure name to the saved PNG path.
        """
        comp_colors = [cm.tab10(i) for i in range(self.n_gaussians)]
        saved       : Dict[str, Path] = {}

        for K, pixels in pixels_by_k.items():
            if pixels.shape[0] == 0:
                continue

            k_color = cm.tab10((K - 1) % 10)
            k_label = rf"$n_{{\mathrm{{active}}}}={K}$  ({K} active slot{'s' if K > 1 else ''})"
            k_dir   = self._group_dir(out_dir, K)

            for az, rg in pixels.tolist():
                raw          = raw_profiles[(az, rg)].astype(np.float64)
                params       = parameters_array[:, az, rg].astype(np.float64)
                total, comps = self._reconstruct_pixel(params, height_axis.astype(np.float64))
                residual     = raw - total

                residual_title = f"Profile minus injected mixture — az={az},  rg={rg}"
                residual_label = r"$\varepsilon = \mathrm{raw} - \mathrm{mixture}$"

                saved[f"k{K}_az{az}_rg{rg}_mixture"]  = self._plot_pixel_mixture(height_axis, raw, total, comps, params, comp_colors, k_color, k_label, az, rg, k_dir)
                saved[f"k{K}_az{az}_rg{rg}_residual"] = self._plot_pixel_residual(height_axis, residual, residual_title, residual_label, k_dir / f"az{az}_rg{rg}_residual.png")

        return saved

    def run(
        self,
        parameters_array : np.ndarray,
        activity_map     : np.ndarray,
        height_axis      : np.ndarray,
        tomogram_path    : Path,
        out_dir          : Path,
    ) -> Dict[str, Path]:
        """Samples pixels per active-slot count and renders their mixture and residual figures.

        Args:
            parameters_array : Parameter stack of shape (3 * n_gaussians, azimuth, range).
            activity_map     : Active-slot count per pixel, of shape (azimuth, range); pixels with no active slot are never sampled.
            height_axis      : Elevation axis of shape (height,), in metres.
            tomogram_path    : Path of the tomogram of shape (height, azimuth, range).
            out_dir          : Directory the per-count subdirectories are created under.

        Returns:
            Mapping from figure name to the saved PNG path.
        """
        self.logger.subsection("Loading tomogram for example mixture plots (memory-mapped)")

        pixels_by_k = self._select_pixels_by_group(activity_map.astype(np.int64), np.ones(activity_map.shape, dtype=bool))
        all_pixels  = self._all_pixels(pixels_by_k)

        self.logger.subsection(f"Extracting {all_pixels.shape[0]} pixel profiles for example mixtures")
        raw_profiles = self._read_raw_profiles(tomogram_path, all_pixels)

        self.logger.subsection(f"Plotting example mixtures  ({self.n_fits_per_k} pixels, up to {self.n_gaussians} active-slot groups)")
        return self._plot_example_mixtures(parameters_array, raw_profiles, height_axis, pixels_by_k, out_dir)
