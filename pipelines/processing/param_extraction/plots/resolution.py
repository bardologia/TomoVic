"""Figures for the kz-resolution analysis of a fitted parameter run.

Plots the volume decorrelation of the parametrized profiles, the phase-CRLB height error
and the height-of-ambiguity coverage against the kz axis in rad/m, with the available
secondary passes marked as a rug, plus histograms of the underlying vertical scales.
"""

from __future__ import annotations

from pathlib import Path
from typing  import Dict

import matplotlib.pyplot as plt
import numpy             as np

from tools.monitoring.logger import Logger
from tools.reporting.plotting import PlotBase


class ResolutionPlotter(PlotBase):
    """Renders the kz-resolution figures of a fitted parameter run.

    Attributes:
        logger: Logger for the plotting report.
        fig_dpi: Figure resolution used while rendering.
        save_dpi: Resolution the PNGs are written at.
    """

    def __init__(self, logger: Logger, fig_dpi: int = 150, save_dpi: int = 300) -> None:
        """Configures the resolution plotter.

        Args:
            logger: Logger for the plotting report.
            fig_dpi: Figure resolution used while rendering.
            save_dpi: Resolution the PNGs are written at.
        """
        self.logger   = logger
        self.fig_dpi  = fig_dpi
        self.save_dpi = save_dpi

    def _pass_rug(self, axes: plt.Axes, arrays: dict) -> None:
        """Marks each candidate secondary pass on the kz axis, coloured by flight.

        Args:
            axes: Axes the rug and its legend entries are drawn on.
            arrays: Resolution arrays carrying ``pass_labels`` and ``pass_kz`` in rad/m.
        """
        flights = sorted({str(label).split("_")[0] for label in arrays["pass_labels"]})
        colours = {flight: self.OKABE_ITO[index % len(self.OKABE_ITO)] for index, flight in enumerate(flights)}

        for label, kz in zip(arrays["pass_labels"], arrays["pass_kz"]):
            axes.axvline(float(kz), ymin=0.0, ymax=0.04, color=colours[str(label).split("_")[0]], linewidth=0.9)

        handles = [plt.Line2D([0], [0], color=colour, linewidth=1.4, label=f"{flight} pass") for flight, colour in colours.items()]
        axes.legend(handles=axes.get_legend_handles_labels()[0] + handles, frameon=False)

    def _plot_coherence(self, arrays: dict, out_dir: Path) -> Dict[str, Path]:
        """Saves the median and IQR of the parametrized-profile pair coherence against kz.

        Args:
            arrays: Resolution arrays carrying ``kz_grid`` in rad/m and the coherence quantiles.
            out_dir: Directory the figure is written to.

        Returns:
            Mapping with the ``resolution_coherence`` figure path.
        """
        self._apply_style()
        fig, axes = plt.subplots(figsize=self.figsize(self.FULL_WIDTH))

        kz = arrays["kz_grid"]
        axes.fill_between(kz, arrays["coh_q25"], arrays["coh_q75"], alpha=0.2, color=self.OKABE_ITO[2], linewidth=0)
        axes.plot(kz, arrays["coh_median"], color=self.OKABE_ITO[2], label="median (IQR shaded)")

        axes.set_xlabel(r"$|\Delta k_z|$ vs primary [rad/m]")
        axes.set_ylabel(r"Parametrized pair coherence $|\gamma|$")
        axes.set_title("Volume decorrelation of the parametrized profiles")
        self._pass_rug(axes, arrays)

        return {"resolution_coherence": self._save(fig, out_dir / "coherence_vs_kz.png")}

    def _plot_height_error(self, arrays: dict, summary: dict, out_dir: Path) -> Dict[str, Path]:
        """Saves the phase-CRLB single-pair height error against kz, with the optimum marked.

        Args:
            arrays: Resolution arrays carrying ``kz_grid`` in rad/m and the error quantiles in metres.
            summary: Resolution summary carrying ``kz_optimum`` in rad/m.
            out_dir: Directory the figure is written to.

        Returns:
            Mapping with the ``resolution_height_error`` figure path.
        """
        self._apply_style()
        fig, axes = plt.subplots(figsize=self.figsize(self.FULL_WIDTH))

        kz = arrays["kz_grid"]
        axes.fill_between(kz, arrays["err_q25"], arrays["err_q75"], alpha=0.2, color=self.OKABE_ITO[0], linewidth=0)
        axes.plot(kz, arrays["err_median"], color=self.OKABE_ITO[0], label="median (IQR shaded)")

        axes.axvline(summary["kz_optimum"], color=self.OKABE_ITO[3], linewidth=1.0, linestyle="--", label=rf"optimum $k_z$ = {summary['kz_optimum']:.2f}")
        axes.set_yscale("log")
        axes.set_xlabel(r"$|\Delta k_z|$ vs primary [rad/m]")
        axes.set_ylabel(r"phase-CRLB height error $\sqrt{1-|\gamma|^2}\,/\,(|\gamma|\,k_z)$")
        axes.set_title("Single-pair height error predicted from the parametrized profiles")
        self._pass_rug(axes, arrays)

        return {"resolution_height_error": self._save(fig, out_dir / "height_error_vs_kz.png")}

    def _plot_aliasing(self, arrays: dict, out_dir: Path) -> Dict[str, Path]:
        """Saves the fraction of pixels whose vertical extent exceeds the height of ambiguity.

        Args:
            arrays: Resolution arrays carrying ``kz_grid`` in rad/m and ``aliased_fraction``.
            out_dir: Directory the figure is written to.

        Returns:
            Mapping with the ``resolution_aliasing`` figure path.
        """
        self._apply_style()
        fig, axes = plt.subplots(figsize=self.figsize(self.FULL_WIDTH))

        kz = arrays["kz_grid"]
        axes.plot(kz, arrays["aliased_fraction"], color=self.OKABE_ITO[1], label="aliased fraction")
        axes.axhline(0.05, color="0.5", linewidth=0.8, linestyle=":", label="5% level")

        axes.set_xlabel(r"$|\Delta k_z|$ vs primary [rad/m]")
        axes.set_ylabel(r"pixels with $2\sigma$ extent $> 2\pi/k_z$")
        axes.set_title("Height-of-ambiguity coverage of the parametrized profiles")
        self._pass_rug(axes, arrays)

        return {"resolution_aliasing": self._save(fig, out_dir / "aliased_fraction_vs_kz.png")}

    def _plot_detail_histograms(self, table, out_dir: Path) -> Dict[str, Path]:
        """Saves histograms of the Gaussian widths, adjacent separations and vertical extents.

        Args:
            table: Active-Gaussian table exposing the pooled sigmas, separations and extents.
            out_dir: Directory the figures are written to.

        Returns:
            Mapping from figure name to the saved PNG path, skipping empty samples.
        """
        saved = {}
        for name, sample, x_label in (
            ("sigma_hist",      table.pooled_sigmas(),       r"active Gaussian width $\sigma$ [elevation units]"),
            ("separation_hist", table.adjacent_separations(), r"adjacent scatterer separation $|\Delta\mu|$ [elevation units]"),
            ("extent_hist",     table.vertical_extents(),     r"per-pixel $2\sigma$ vertical extent [elevation units]"),
        ):
            if sample.size == 0:
                continue

            self._apply_style()
            fig, axes = plt.subplots(figsize=self.figsize(self.HALF_WIDTH, aspect=0.75))

            axes.hist(sample, bins=80, color=self.OKABE_ITO[0], alpha=0.85)
            axes.set_xlabel(x_label)
            axes.set_ylabel("count")

            saved[f"resolution_{name}"] = self._save(fig, out_dir / f"{name}.png")

        return saved

    def run(self, arrays: dict, summary: dict, table, images_dir: Path) -> Dict[str, Path]:
        """Renders every resolution figure into a ``resolution`` subdirectory.

        Args:
            arrays: Resolution curve arrays over the kz grid, in rad/m.
            summary: Resolution summary from the analyzer.
            table: Active-Gaussian table the curves were derived from.
            images_dir: Images root the ``resolution`` subdirectory is created under.

        Returns:
            Mapping from figure name to the saved PNG path.
        """
        out_dir = Path(images_dir) / "resolution"
        out_dir.mkdir(parents=True, exist_ok=True)

        saved = {}
        saved.update(self._plot_coherence(arrays, out_dir))
        saved.update(self._plot_height_error(arrays, summary, out_dir))
        saved.update(self._plot_aliasing(arrays, out_dir))
        saved.update(self._plot_detail_histograms(table, out_dir))

        self.logger.subsection(f"-> Resolution plots written: {out_dir} ({len(saved)} figures)")
        return saved
