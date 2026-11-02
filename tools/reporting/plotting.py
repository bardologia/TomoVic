"""Shared matplotlib base class for the project's publication-quality figures.

Fixes the serif rcParams, the report and paper style variants, colour-limit
conventions and the subsampling and panel helpers that every plotting module in
the project inherits.
"""

from __future__ import annotations

from pathlib import Path
from typing  import List, Tuple

import matplotlib
import matplotlib.colors as mcolors
import matplotlib.pyplot as plt
import numpy             as np

matplotlib.use("Agg")

from tools.reporting.colormaps import PhaseColormap


class PlotBase:
    """Base class carrying the project's figure style and plotting helpers.

    Attributes:
        PHASE_TICKS   : Radian tick positions spanning one phase cycle.
        PHASE_LABELS  : LaTeX labels matching PHASE_TICKS.
        FULL_WIDTH    : Full text-column figure width in inches.
        HALF_WIDTH    : Half text-column figure width in inches.
        OKABE_ITO     : Colour-blind-safe categorical palette used in the paper and slide styles.
        SCIENTIFIC_RC : rcParams shared by every style.
        REPORT_RC     : Larger-type rcParams for screen reports.
        PAPER_RC      : Smaller-type rcParams for camera-ready figures.
        SLIDE_RC      : Paper-style rcParams for figures drawn at the exact size they print on a slide, saved without trimming.
        STYLE_RC      : Style name to rcParams mapping.
        PRINT_STYLES  : Styles that save at PAPER_DPI and write figures holding no image as vector PDF.
        PAPER_DPI     : Raster resolution used in the paper and slide styles.
        style         : Active style name, shared across all subclasses.
        fig_dpi       : Display resolution used in report style.
        save_dpi      : Save resolution used in report style.
    """

    PHASE_TICKS  = [-np.pi, -np.pi / 2, 0.0, np.pi / 2, np.pi]
    PHASE_LABELS = [r"$-\pi$", r"$-\pi/2$", r"$0$", r"$\pi/2$", r"$\pi$"]

    FULL_WIDTH : float = 5.5
    HALF_WIDTH : float = 2.65

    OKABE_ITO = ["#0072B2", "#D55E00", "#009E73", "#E69F00", "#CC79A7", "#56B4E9", "#F0E442", "#000000"]

    SCIENTIFIC_RC: dict = {
        "font.family"         : "serif",
        "font.serif"          : ["Times New Roman", "STIXGeneral", "DejaVu Serif"],
        "axes.linewidth"      : 0.8,
        "xtick.direction"     : "in",
        "ytick.direction"     : "in",
        "xtick.top"           : True,
        "ytick.right"         : True,
        "xtick.minor.visible" : True,
        "ytick.minor.visible" : True,
        "image.interpolation" : "nearest",
        "savefig.bbox"        : "tight",
        "pdf.fonttype"        : 42,
        "ps.fonttype"         : 42,
    }

    REPORT_RC: dict = {
        "font.size"        : 11,
        "axes.titlesize"   : 12,
        "axes.labelsize"   : 11,
        "xtick.labelsize"  : 10,
        "ytick.labelsize"  : 10,
        "legend.fontsize"  : 9,
        "mathtext.fontset" : "dejavuserif",
        "lines.linewidth"  : 1.5,
        "lines.markersize" : 6.0,
    }

    PAPER_RC: dict = {
        "font.size"        : 9,
        "axes.titlesize"   : 9,
        "axes.labelsize"   : 9,
        "xtick.labelsize"  : 8,
        "ytick.labelsize"  : 8,
        "legend.fontsize"  : 8,
        "mathtext.fontset" : "stix",
        "lines.linewidth"  : 1.2,
        "lines.markersize" : 4.0,
    }

    SLIDE_RC: dict = {
        "font.size"                       : 7,
        "axes.titlesize"                  : 7,
        "axes.labelsize"                  : 7,
        "xtick.labelsize"                 : 6,
        "ytick.labelsize"                 : 6,
        "legend.fontsize"                 : 6,
        "mathtext.fontset"                : "stix",
        "axes.linewidth"                  : 0.6,
        "xtick.major.width"               : 0.6,
        "ytick.major.width"               : 0.6,
        "xtick.minor.width"               : 0.4,
        "ytick.minor.width"               : 0.4,
        "xtick.major.size"                : 2.5,
        "ytick.major.size"                : 2.5,
        "xtick.minor.size"                : 1.5,
        "ytick.minor.size"                : 1.5,
        "xtick.major.pad"                 : 2.0,
        "ytick.major.pad"                 : 2.0,
        "axes.labelpad"                   : 2.0,
        "lines.linewidth"                 : 0.9,
        "lines.markersize"                : 2.5,
        "legend.handlelength"             : 1.6,
        "figure.constrained_layout.use"   : True,
        "figure.constrained_layout.w_pad" : 0.02,
        "figure.constrained_layout.h_pad" : 0.02,
        "savefig.bbox"                    : "standard",
    }

    STYLE_RC = {"report": REPORT_RC, "paper": PAPER_RC, "slide": SLIDE_RC}

    PRINT_STYLES = ("paper", "slide")

    PAPER_DPI: int = 300

    style: str = "report"

    fig_dpi  : int = 150
    save_dpi : int = 150

    @classmethod
    def use_style(cls, style: str) -> None:
        """Selects the figure style used by every plotter.

        Args:
            style : One of 'report', 'paper' or 'slide'.

        Raises:
            ValueError : If the style name is not registered.
        """
        if style not in PlotBase.STYLE_RC:
            raise ValueError(f"unknown figure style '{style}', expected one of {sorted(PlotBase.STYLE_RC)}")
        PlotBase.style = style

    @classmethod
    def figsize(cls, width: float, aspect: float = 0.62) -> Tuple[float, float]:
        """Returns a (width, height) figure size in inches for the given aspect ratio."""
        return (width, width * aspect)

    def _apply_style(self) -> None:
        """Installs the scientific rcParams plus the active style's overrides."""
        plt.rcParams.update(self.SCIENTIFIC_RC)
        plt.rcParams.update(self.STYLE_RC[PlotBase.style])

        if PlotBase.style in self.PRINT_STYLES:
            plt.rcParams["axes.prop_cycle"] = plt.cycler(color=self.OKABE_ITO)
            plt.rcParams["figure.dpi"]      = self.PAPER_DPI
            plt.rcParams["savefig.dpi"]     = self.PAPER_DPI
        else:
            plt.rcParams["axes.prop_cycle"] = plt.rcParamsDefault["axes.prop_cycle"]
            plt.rcParams["figure.dpi"]      = self.fig_dpi
            plt.rcParams["savefig.dpi"]     = self.save_dpi

    @staticmethod
    def _save(fig: plt.Figure, path: Path) -> Path:
        """Saves and closes a figure, returning the path actually written.

        In the paper and slide styles a raster target holding no images is
        redirected to PDF so vector content stays vector.

        Args:
            fig  : Figure to write and close.
            path : Requested output path.

        Returns:
            The path the figure was written to.
        """
        if PlotBase.style in PlotBase.PRINT_STYLES and path.suffix == ".png" and not any(ax.images for ax in fig.axes):
            path = path.with_suffix(".pdf")

        path.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(path)
        plt.close(fig)
        return path

    @staticmethod
    def _lattice_step(sample: np.ndarray, max_multiple: int = 8, share: float = 0.5) -> float:
        """Returns the coarsest value spacing that carries most of a sample's mass.

        Parameters read off a discrete height axis take only multiples of that axis'
        step, and a sample can mix several such lattices: a quantity built from one
        grid value alone sits on the base step, one built from a sum of several sits
        on a multiple of it. The base spacing is the smallest gap between distinct
        values, and the returned step is the largest multiple of it that at least
        ``share`` of the values still lie on.

        Args:
            sample       : Values to inspect, of any shape, assumed finite.
            max_multiple : Largest multiple of the base spacing considered.
            share        : Fraction of values that must sit on a multiple for it to be accepted.

        Returns:
            The spacing in the sample's own units, or zero when the values are continuous.
        """
        flat  = np.asarray(sample, dtype=float).reshape(-1)
        scale = float(np.abs(flat).max()) if flat.size else 0.0

        if scale <= 0.0:
            return 0.0

        gaps = np.diff(np.unique(flat))
        gaps = gaps[gaps > 1e-6 * scale]

        if gaps.size == 0:
            return 0.0

        base = float(gaps.min())
        step = base

        for multiple in range(2, max_multiple + 1):
            candidate = base * multiple
            quotient  = flat / candidate

            if float(np.mean(np.abs(quotient - np.round(quotient)) < 1e-6)) >= share:
                step = candidate

        return step

    @staticmethod
    def _quantised_bins(sample: np.ndarray, target_bins: int = 64, span: Tuple[float, float] = (0.5, 99.5)) -> np.ndarray:
        """Returns histogram edges aligned to the value grid the sample lives on.

        Parameters read off a discrete height axis take only multiples of that axis'
        step, so bin edges that are not a whole number of steps wide catch alternating
        numbers of grid values and comb the histogram. The spacing is measured by
        :meth:`_lattice_step`, the bin width is raised to a multiple of it, and the
        first edge is offset half a step so every bin spans the same number of grid
        values. A continuous sample reports no spacing and keeps plain equal-width bins.

        Args:
            sample      : Values to be histogrammed, of any shape, assumed finite.
            target_bins : Bin count aimed for before the width is snapped to the grid.
            span        : Percentiles the edges cover, trimming the heavy tails.

        Returns:
            Monotonic bin edges of shape (n_bins + 1,).

        Raises:
            ValueError : If the sample holds no values.
        """
        flat = np.asarray(sample).reshape(-1)

        if flat.size == 0:
            raise ValueError("_quantised_bins received an empty sample; cannot derive bin edges")

        low, high = (float(value) for value in np.percentile(flat, span))

        if not high > low:
            return np.linspace(low, low + 1.0, target_bins + 1)

        width = (high - low) / target_bins
        step  = PlotBase._lattice_step(flat[(flat >= low) & (flat <= high)])

        if step > 0.0 and step > 1e-3 * (high - low):
            width = max(int(np.ceil(width / step)), 1) * step
            low   = np.floor(low / step) * step - 0.5 * step

        return np.arange(low, high + width, width)

    @staticmethod
    def _shared_clim(*arrays: np.ndarray, q_low: float = 1.0, q_high: float = 99.0) -> Tuple[float, float]:
        """Returns a percentile colour range shared by several arrays.

        Args:
            *arrays : Arrays of any shape, pooled after flattening.
            q_low   : Lower percentile mapped to vmin.
            q_high  : Upper percentile mapped to vmax.

        Returns:
            Tuple of (vmin, vmax).

        Raises:
            ValueError : If no finite values are present.
        """
        flat = np.concatenate([a.reshape(-1) for a in arrays])
        flat = flat[np.isfinite(flat)]
        if flat.size == 0:
            raise ValueError("_shared_clim received no finite values; cannot derive a colour scale from an empty or all-NaN field")
        return float(np.percentile(flat, q_low)), float(np.percentile(flat, q_high))

    @staticmethod
    def _amplitude_clim(*arrays: np.ndarray) -> Tuple[float, float]:
        """Returns the project's amplitude colour range, zero to three times the mean.

        Args:
            *arrays : Amplitude arrays of any shape, pooled after flattening.

        Returns:
            Tuple of (0.0, 3 * mean amplitude).

        Raises:
            ValueError : If no finite values are present or the mean is not positive.
        """
        flat = np.concatenate([np.asarray(a).reshape(-1) for a in arrays])
        flat = flat[np.isfinite(flat)]
        if flat.size == 0:
            raise ValueError("_amplitude_clim received no finite values; cannot derive an amplitude scale from an empty or all-NaN field")

        vmax = 3.0 * float(flat.mean())
        if vmax <= 0.0:
            raise ValueError("_amplitude_clim requires a positive mean amplitude; got a non-positive field")

        return 0.0, vmax

    @staticmethod
    def _cmap_with_bad(name: str, bad_color: str = "0.88") -> mcolors.Colormap:
        """Returns a copy of the named colormap that paints NaNs in bad_color."""
        cmap = plt.get_cmap(name).copy()
        cmap.set_bad(color=bad_color)
        return cmap

    @staticmethod
    def _phase_cmap() -> mcolors.Colormap:
        """Returns the cyclic TAXI phase colormap."""
        return PhaseColormap.colormap()

    @staticmethod
    def _normalize_01(arr: np.ndarray) -> np.ndarray:
        """Rescales an array to [0, 1] using its finite minimum and maximum.

        Args:
            arr : Array of any shape.

        Returns:
            Float32 array of the same shape scaled to [0, 1].

        Raises:
            ValueError : If the field is constant or degenerate.
        """
        lo, hi = float(np.nanmin(arr)), float(np.nanmax(arr))
        if hi - lo < 1e-12:
            raise ValueError("_normalize_01 received a constant or degenerate field; refusing to flatten it silently to a single colour")
        return ((arr - lo) / (hi - lo)).astype(np.float32)

    def _imshow_figure(
        self,
        data           : np.ndarray,
        *,
        x_label        : str,
        y_label        : str,
        title          : str,
        cmap,
        vmin           : float | None        = None,
        vmax           : float | None        = None,
        extent         : list | None         = None,
        origin         : str                 = "upper",
        colorbar_label : str                 = "",
        interpolation  : str | None          = "nearest",
        aspect         : str                 = "auto",
        figsize        : Tuple[float, float] = (6.2, 4.4),
        discrete       : bool                = False,
        levels         : List[int] | None    = None,
        text_overlay   : str | None          = None,
        path           : Path | None         = None,
    ):
        """Renders one labelled image panel with a colorbar.

        Args:
            data           : Field of shape (rows, columns) to display.
            x_label        : Horizontal axis label, including units.
            y_label        : Vertical axis label, including units.
            title          : Axes title.
            cmap           : Colormap used in continuous mode.
            vmin           : Lower colour limit, or None to autoscale.
            vmax           : Upper colour limit, or None to autoscale.
            extent         : Data coordinates of the image edges, or None for pixel indices.
            origin         : Row origin, 'upper' or 'lower'.
            colorbar_label : Colorbar label, including units.
            interpolation  : Image interpolation mode.
            aspect         : Axes aspect handling.
            figsize        : Figure size in inches.
            discrete       : Draws integer class levels with a boundary norm when True.
            levels         : Integer levels shown in discrete mode; inferred from the data maximum when omitted.
            text_overlay   : Optional annotation drawn in the upper-left corner.
            path           : Output path; the figure is returned instead when omitted.

        Returns:
            The written path when path is given, otherwise the open figure.
        """
        self._apply_style()

        if not discrete and np.issubdtype(np.asarray(data).dtype, np.floating):
            data = np.asarray(data, dtype=np.float64)

        fig, ax = plt.subplots(figsize=figsize)

        if discrete:
            level_list = list(levels) if levels is not None else list(range(int(np.nanmax(data)) + 1))
            palette    = plt.get_cmap("tab10", len(level_list))
            disc_cmap  = mcolors.ListedColormap([palette(i) for i in range(len(level_list))])
            bounds     = [value - 0.5 for value in level_list] + [level_list[-1] + 0.5]
            norm       = mcolors.BoundaryNorm(bounds, disc_cmap.N)

            im = ax.imshow(data, cmap=disc_cmap, norm=norm, extent=extent, aspect=aspect, origin=origin, interpolation=interpolation)

            cbar = fig.colorbar(im, ax=ax, fraction=0.045, pad=0.02, ticks=level_list, boundaries=bounds)
            cbar.set_label(colorbar_label)
            cbar.ax.set_yticklabels([str(value) for value in level_list])
        else:
            im = ax.imshow(data, cmap=cmap, vmin=vmin, vmax=vmax, extent=extent, aspect=aspect, origin=origin, interpolation=interpolation)

            fig.colorbar(im, ax=ax, fraction=0.045, pad=0.02).set_label(colorbar_label)

        ax.set_title(title)
        ax.set_xlabel(x_label)
        ax.set_ylabel(y_label)

        if text_overlay is not None:
            ax.text(0.02, 0.98, text_overlay, transform=ax.transAxes, fontsize=8, va="top", ha="left", bbox=dict(boxstyle="round,pad=0.3", fc="white", ec="0.5", alpha=0.88))

        fig.tight_layout()

        if path is not None:
            return self._save(fig, path)

        return fig

    @staticmethod
    def _subsample(values: np.ndarray, n_max: int, seed: int = 0) -> np.ndarray:
        """Returns at most n_max finite values, drawn without replacement.

        Args:
            values : Array of any shape holding the candidate values.
            n_max  : Maximum number of values to keep.
            seed   : Seed of the sampling generator.

        Returns:
            One-dimensional array of finite values, at most n_max long.
        """
        vals = values[np.isfinite(values)]
        if vals.size > n_max:
            rng  = np.random.default_rng(seed)
            vals = rng.choice(vals, size=n_max, replace=False)
        return vals

    @staticmethod
    def _paired_subsample(arrays: List[np.ndarray], n_max: int, seed: int = 0) -> List[np.ndarray]:
        """Subsamples several co-registered arrays on a shared set of finite indices.

        Args:
            arrays : Arrays of identical size, flattened before sampling.
            n_max  : Maximum number of elements to keep.
            seed   : Seed of the sampling generator.

        Returns:
            One flattened array per input, all indexed by the same positions.
        """
        flats = [a.reshape(-1) for a in arrays]
        ok    = np.ones(flats[0].size, dtype=bool)

        for flat in flats:
            ok &= np.isfinite(flat)

        idx = np.where(ok)[0]
        if idx.size > n_max:
            rng = np.random.default_rng(seed)
            idx = rng.choice(idx, size=n_max, replace=False)

        return [flat[idx] for flat in flats]

    @staticmethod
    def _binned_median(x: np.ndarray, y: np.ndarray, n_bins: int = 30, min_count: int = 50) -> Tuple[np.ndarray, np.ndarray]:
        """Computes the median of y inside equal-width bins of x.

        Args:
            x         : One-dimensional binning variable.
            y         : One-dimensional response variable aligned with x.
            n_bins    : Number of equal-width bins spanning the range of x.
            min_count : Minimum samples a bin needs before its median is reported.

        Returns:
            Tuple of (bin centres, medians), both of length n_bins, with NaN in
            bins that hold fewer than min_count samples.
        """
        edges   = np.linspace(float(x.min()), float(x.max()), n_bins + 1)
        centers = 0.5 * (edges[:-1] + edges[1:])
        medians = np.full(n_bins, np.nan)
        which   = np.digitize(x, edges[1:-1])

        for b in range(n_bins):
            sel = which == b
            if int(sel.sum()) >= min_count:
                medians[b] = float(np.median(y[sel]))

        return centers, medians

    @staticmethod
    def _violin_with_iqr(ax, data_by_slot: List[np.ndarray], palette: List) -> None:
        """Draws one violin per slot with an interquartile bar and median marker.

        Empty slots are annotated 'n=0' instead of being drawn, and slots with
        fewer than four samples get a violin but no quartile overlay.

        Args:
            ax           : Axes to draw on.
            data_by_slot : One flat sample array per slot, in slot order.
            palette      : Colour per slot, aligned with data_by_slot.
        """
        drawn_positions = [i + 1 for i, d in enumerate(data_by_slot) if d.size > 0]
        drawn_data      = [d     for    d in data_by_slot           if d.size > 0]
        drawn_colors    = [palette[i] for i, d in enumerate(data_by_slot) if d.size > 0]

        if drawn_data:
            parts = ax.violinplot(drawn_data, positions=drawn_positions, showmedians=True, showextrema=False, widths=0.7)

            for body, color in zip(parts["bodies"], drawn_colors):
                body.set_facecolor(color)
                body.set_alpha(0.60)

            parts["cmedians"].set_color("black")
            parts["cmedians"].set_linewidth(1.8)

        y_lo, y_hi = ax.get_ylim()
        for i, (slot_data, color) in enumerate(zip(data_by_slot, palette)):
            if slot_data.size == 0:
                ax.text(i + 1, y_lo + 0.02 * (y_hi - y_lo), "n=0", ha="center", va="bottom", fontsize=8, color="0.45", rotation=90)
                continue
            if slot_data.size < 4:
                continue
            q25, q50, q75 = np.percentile(slot_data, [25, 50, 75])
            ax.vlines(i + 1, q25, q75, color=color, lw=3.0, zorder=3)
            ax.scatter(i + 1, q50, color="white", s=22, zorder=5, edgecolors=color, linewidths=1.2)

    @staticmethod
    def _render_panels(
        fig,
        axes,
        panels         : List[Tuple[np.ndarray, str, str, float, float]],
        *,
        x_label        : str,
        extent         : list,
        origin         : str,
        interpolation  : str | None = None,
        title_size     : int | None = None,
        label_size     : int | None = None,
        colorbar_label = None,
    ) -> None:
        """Draws one image per axes from a list of panel specifications.

        Args:
            fig            : Figure owning the axes, used to attach the colorbars.
            axes           : Axes to fill, paired with panels in order.
            panels         : Tuples of (data of shape (rows, columns), title, colormap, vmin, vmax).
            x_label        : Horizontal axis label shared by every panel, including units.
            extent         : Data coordinates of the image edges.
            origin         : Row origin, 'upper' or 'lower'.
            interpolation  : Image interpolation mode.
            title_size     : Font size of the panel titles.
            label_size     : Font size of the axis labels.
            colorbar_label : Callable mapping a panel's colormap to its colorbar label, or None to leave the colorbars unlabelled.
        """

        for ax_i, (data, label, cm_used, vlo, vhi) in zip(axes, panels):
            im = ax_i.imshow(data, cmap=cm_used, vmin=vlo, vmax=vhi, extent=extent, aspect="auto", origin=origin, interpolation=interpolation)

            ax_i.set_title(label, fontsize=title_size)
            ax_i.set_xlabel(x_label, fontsize=label_size)

            cbar = fig.colorbar(im, ax=ax_i, fraction=0.045, pad=0.02)
            if colorbar_label is not None:
                cbar.set_label(colorbar_label(cm_used))

    @staticmethod
    def _triple_panel(
        fig,
        axes,
        panels    : List[Tuple[np.ndarray, str, str, float, float]],
        x_label   : str,
        int_label : str,
        extent    : list,
        origin    : str,
    ) -> None:
        """Draws a reference, prediction and error triple sharing one axis label.

        Panels whose colormap matches the first panel's are labelled with
        int_label; the remaining ones are labelled '|error|'.

        Args:
            fig       : Figure owning the axes.
            axes      : Axes to fill, paired with panels in order.
            panels    : Tuples of (data of shape (rows, columns), title, colormap, vmin, vmax).
            x_label   : Horizontal axis label shared by every panel, including units.
            int_label : Colorbar label for the panels sharing the first colormap.
            extent    : Data coordinates of the image edges.
            origin    : Row origin, 'upper' or 'lower'.
        """

        PlotBase._render_panels(
            fig, axes, panels,
            x_label        = x_label,
            extent         = extent,
            origin         = origin,
            colorbar_label = lambda cm_used: int_label if cm_used == panels[0][2] else "|error|",
        )
