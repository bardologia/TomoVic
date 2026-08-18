"""Distribution figures for a parameter-extraction run.

Covers the R-squared PDF and CDF, the per-slot amplitude, centroid and width
distributions, their pairwise joint densities, and the model-order ambiguity spread.
"""

from __future__ import annotations

from pathlib import Path
from typing  import Dict, List

import matplotlib

matplotlib.use("Agg")
import matplotlib.cm     as cm
import matplotlib.pyplot as plt
import numpy             as np
from scipy.stats         import gaussian_kde

from tools.reporting.plotting import PlotBase
from tools.monitoring.logger  import Logger


class DistributionPlotter(PlotBase):
    """Renders the distribution figures of a fitted parameter stack.

    Attributes:
        n_gaussians: Number of Gaussian slots in the parameter stack.
        logger: Logger for skip warnings.
        amp_threshold: Amplitude above which a Gaussian slot counts as active.
        fig_dpi: Figure resolution used while rendering.
        save_dpi: Resolution the PNGs are written at.
    """

    def __init__(self, n_gaussians : int, logger : Logger, amp_threshold : float, fig_dpi : int = 150, save_dpi : int = 300) -> None:
        """Configures the distribution plotter.

        Args:
            n_gaussians: Number of Gaussian slots in the parameter stack.
            logger: Logger for skip warnings.
            amp_threshold: Amplitude above which a Gaussian slot counts as active.
            fig_dpi: Figure resolution used while rendering.
            save_dpi: Resolution the PNGs are written at.
        """
        self.n_gaussians   = n_gaussians
        self.logger        = logger
        self.amp_threshold = amp_threshold
        self.fig_dpi       = fig_dpi
        self.save_dpi      = save_dpi

    def plot_r2_distribution(self, r2_map : np.ndarray, summary : dict, out_dir : Path) -> Dict[str, Path]:
        """Saves the R-squared histogram with KDE and its empirical CDF.

        Args:
            r2_map: Per-pixel R-squared of shape (azimuth, range), NaN where unfitted.
            summary: Global summary carrying the R-squared mean, median and negative fraction.
            out_dir: Directory the figures are written to.

        Returns:
            Mapping with the ``r2_pdf`` and ``r2_cdf`` figure paths; empty when no finite
            value exists.
        """
        flat  = r2_map.reshape(-1).astype(np.float64)
        valid = flat[np.isfinite(flat)]

        if valid.size == 0:
            self.logger.warning("R² distribution plots skipped: no finite values")
            return {}

        qs    = [10, 25, 50, 75, 90]
        pvals = np.percentile(valid, qs)
        pcolors  = ["#9467bd", "#1f77b4", "#2ca02c", "#ff7f0e", "#d62728"]
        stats_tx = rf"mean={summary['r2_mean']:.4f},  median={summary['r2_median']:.4f},  neg\_frac={summary['r2_neg_frac']:.3f}"
        saved    : Dict[str, Path] = {}

        fig, ax = plt.subplots(figsize=(6.4, 4.5))
        lo = float(np.percentile(valid, 0.5))
        hi = float(np.percentile(valid, 99.5))
        ax.hist(valid, bins=120, range=(lo, hi), density=True, color="#1f77b4", alpha=0.60, edgecolor="none", label="PDF")

        if valid.size > 2:
            kde = gaussian_kde(valid, bw_method="scott")
            xs  = np.linspace(lo, hi, 600)
            ax.plot(xs, kde(xs), color="black", lw=1.4, label="KDE")

        for q, pv, pc in zip(qs, pvals, pcolors):
            ax.axvline(pv, color=pc, lw=1.1, ls="--", label=f"$p_{{{q}}}={pv:.3f}$")

        ax.set_xlabel(r"coefficient of determination $R^2$")
        ax.set_ylabel(r"probability density")
        ax.set_title(r"$R^2$ distribution across fitted pixels" + "\n" + stats_tx)
        ax.legend(fontsize=8, framealpha=0.90, ncol=2)
        ax.grid(True, which="major", lw=0.3, alpha=0.40)
        fig.tight_layout()

        saved["r2_pdf"] = self._save(fig, out_dir / "r2_pdf.png")

        fig, ax = plt.subplots(figsize=(6.4, 4.5))
        cdf_x = np.sort(valid)
        cdf_y = np.arange(1, valid.size + 1) / valid.size
        ax.plot(cdf_x, cdf_y, color="#1f77b4", lw=1.4)

        for q, pv, pc in zip(qs, pvals, pcolors):
            ax.axvline(pv, color=pc, lw=1.0, ls="--")
            ax.axhline(q / 100.0, color=pc, lw=0.6, ls=":")
            ax.text(pv + 0.005, q / 100.0 + 0.012, f"$p_{{{q}}}$", fontsize=7, color=pc)

        ax.set_xlabel(r"$R^2$")
        ax.set_ylabel(r"cumulative fraction")
        ax.set_title(r"$R^2$ empirical CDF")
        ax.set_ylim(0, 1.05)
        ax.grid(True, which="major", lw=0.3, alpha=0.40)
        fig.tight_layout()

        saved["r2_cdf"] = self._save(fig, out_dir / "r2_cdf.png")

        return saved

    def plot_parameter_distributions(self, parameters_array : np.ndarray, out_dir : Path) -> Dict[str, Path]:
        """Saves one violin figure per parameter family across the Gaussian slots.

        Args:
            parameters_array: Parameter stack of shape (3 * n_gaussians, azimuth, range).
            out_dir: Directory the figures are written to.

        Returns:
            Mapping with the ``amp_dist``, ``mu_dist`` and ``sigma_dist`` figure paths,
            omitting families with no active component.
        """
        specs = [
            ("amp",   r"amplitude $A_k$",             "amp"),
            ("mu",    r"centroid height $\mu_k$ [m]", "mu"),
            ("sigma", r"spread $\sigma_k$ [m]",       "sigma"),
        ]
        saved: Dict[str, Path] = {}

        for tag, ylabel, file_tag in specs:
            fig, ax = plt.subplots(figsize=(max(6, 2.2 * self.n_gaussians), 5))

            data_by_slot : List[np.ndarray] = []
            labels       : List[str]        = []

            for k in range(self.n_gaussians):
                amp_flat = parameters_array[3 * k].reshape(-1)
                active   = amp_flat >= self.amp_threshold
                if tag == "amp":
                    ch_idx = 3 * k
                elif tag == "mu":
                    ch_idx = 3 * k + 1
                else:
                    ch_idx = 3 * k + 2
                vals = parameters_array[ch_idx].reshape(-1)
                vals = vals[active & np.isfinite(vals)]
                data_by_slot.append(vals)
                labels.append(f"$g_{{{k + 1}}}$")

            non_empty = [d for d in data_by_slot if d.size > 0]
            if not non_empty:
                plt.close(fig)
                continue

            palette   = [cm.tab10(i) for i in range(self.n_gaussians)]
            positions = list(range(1, self.n_gaussians + 1))

            self._violin_with_iqr(ax, data_by_slot, palette)

            ax.set_xticks(positions)
            ax.set_xticklabels(labels, fontsize=10)
            ax.set_xlabel("Gaussian slot")
            ax.set_ylabel(ylabel)
            ax.set_title(f"Distribution of {ylabel}  (active pixels only, IQR box + violin)")
            ax.grid(True, axis="y", which="major", lw=0.3, alpha=0.40)
            fig.tight_layout()

            path                  = out_dir / f"{file_tag}_distribution.png"
            saved[f"{tag}_dist"]  = self._save(fig, path)

        return saved

    def plot_param_joint_distributions(self, parameters_array : np.ndarray, out_dir : Path) -> Dict[str, Path]:
        """Saves hexbin densities of the parameter pairs, pooling every slot.

        Args:
            parameters_array: Parameter stack of shape (3 * n_gaussians, azimuth, range).
            out_dir: Directory the figures are written to.

        Returns:
            Mapping with the ``joint_mu_sigma``, ``joint_mu_amp`` and ``joint_sigma_amp``
            figure paths; empty when no component is active.
        """
        amp_pool : List[np.ndarray] = []
        mu_pool  : List[np.ndarray] = []
        sig_pool : List[np.ndarray] = []

        for k in range(self.n_gaussians):
            amp_flat = parameters_array[3 * k].reshape(-1)
            active   = amp_flat >= self.amp_threshold
            amp_pool.append(amp_flat[active])
            mu_pool .append(parameters_array[3 * k + 1].reshape(-1)[active])
            sig_pool.append(parameters_array[3 * k + 2].reshape(-1)[active])

        amps = np.concatenate(amp_pool) if amp_pool else np.empty(0, dtype=np.float32)

        if amps.size == 0:
            self.logger.warning("Joint parameter distribution plots skipped: no active components")
            return {}

        mus      = np.concatenate(mu_pool)
        sigs     = np.concatenate(sig_pool)
        log_amps = np.log10(np.maximum(amps, 1e-12))

        pairs = [
            ("joint_mu_sigma",  mus,  sigs,     r"$\mu$ [m]",    r"$\sigma$ [m]"),
            ("joint_mu_amp",    mus,  log_amps, r"$\mu$ [m]",    r"$\log_{10} A$"),
            ("joint_sigma_amp", sigs, log_amps, r"$\sigma$ [m]", r"$\log_{10} A$"),
        ]

        saved : Dict[str, Path] = {}

        for name, x, y, x_label, y_label in pairs:
            fig, ax = plt.subplots(figsize=(6.4, 4.8))
            xs, ys  = self._paired_subsample([x, y], 400_000)
            hb      = ax.hexbin(xs, ys, gridsize=70, bins="log", cmap="viridis", mincnt=1)
            fig.colorbar(hb, ax=ax, fraction=0.04, pad=0.02).set_label("component count")
            ax.set_xlabel(x_label)
            ax.set_ylabel(y_label)
            ax.set_title(f"{y_label} vs {x_label}  (active components, all slots pooled)")
            fig.tight_layout()

            saved[name] = self._save(fig, out_dir / f"{name}.png")

        return saved

    def plot_k_ambiguity_distribution(self, metrics_dict : dict, per_k_summary : dict, out_dir : Path) -> Dict[str, Path]:
        """Saves the relative selection-margin histogram and its split by selected order.

        Args:
            metrics_dict: Metrics carrying ``k_relative_margin_map`` and ``best_k_map``.
            per_k_summary: Per-order summary carrying the ambiguity threshold and fraction.
            out_dir: Directory the figures are written to.

        Returns:
            Mapping with the ``k_ambiguity_distribution`` and ``k_ambiguity_by_k`` figure
            paths; empty when no finite margin exists.
        """
        rel    = metrics_dict["k_relative_margin_map"].reshape(-1)
        best_k = metrics_dict["best_k_map"].reshape(-1)
        ok     = np.isfinite(rel)

        if int(ok.sum()) == 0:
            self.logger.warning("K-selection ambiguity plots skipped: no data")
            return {}

        log_rel   = np.log10(np.maximum(rel[ok], 1e-9))
        bk_valid  = best_k[ok]
        threshold = float(per_k_summary["ambiguity_threshold"])
        saved     : Dict[str, Path] = {}

        fig, ax = plt.subplots(figsize=(6.4, 4.6))
        sample  = self._subsample(log_rel, 2_000_000)
        ax.hist(sample, bins=120, density=True, color="#1f77b4", alpha=0.65, edgecolor="none")
        ax.axvline(np.log10(threshold),       color="#d62728", lw=1.2, ls="--", label=f"ambiguity threshold ({threshold:.2f})")
        ax.axvline(float(np.median(log_rel)), color="black",   lw=1.2, ls=":",  label="median")
        ax.set_xlabel(r"$\log_{10}$ relative selection margin  $(\mathcal{L}_{2\mathrm{nd}} - \mathcal{L}_{K^*}) / \mathcal{L}_{K^*}$")
        ax.set_ylabel("probability density")
        ax.set_title("K-selection ambiguity distribution")
        ax.legend(framealpha=0.90)
        ax.grid(True, which="major", lw=0.3, alpha=0.40)

        amb_frac = per_k_summary["k_ambiguous_fraction"]
        if np.isfinite(amb_frac):
            ax.text(0.02, 0.98, f"ambiguous fraction: {amb_frac:.3f}", transform=ax.transAxes, fontsize=9, va="top", ha="left", bbox=dict(boxstyle="round,pad=0.3", fc="white", ec="0.5", alpha=0.88))

        fig.tight_layout()
        saved["k_ambiguity_distribution"] = self._save(fig, out_dir / "k_ambiguity_distribution.png")

        fig, ax = plt.subplots(figsize=(6.4, 4.6))
        k_vals  = list(range(1, self.n_gaussians + 1))
        palette = [cm.tab10((k - 1) % 10) for k in k_vals]
        data    = [self._subsample(log_rel[bk_valid == k], 200_000, seed=k) for k in k_vals]
        self._violin_with_iqr(ax, data, palette)
        ax.axhline(np.log10(threshold), color="#d62728", lw=1.0, ls="--")
        ax.set_xticks(k_vals)
        ax.set_xticklabels([f"$K={k}$" for k in k_vals])
        ax.set_xlabel(r"selected model order $K^*$")
        ax.set_ylabel(r"$\log_{10}$ relative selection margin")
        ax.set_title("Ambiguity conditioned on selected model order")
        ax.grid(True, axis="y", which="major", lw=0.3, alpha=0.40)
        fig.tight_layout()

        saved["k_ambiguity_by_k"] = self._save(fig, out_dir / "k_ambiguity_by_k.png")

        return saved
