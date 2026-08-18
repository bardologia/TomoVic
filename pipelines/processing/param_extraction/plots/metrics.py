"""Bar and density figures summarising the fit metrics of a parameter-extraction run.

Covers the R-squared percentiles, the active-slot count distribution, the per-order
residual and penalty decomposition, and the relation between profile contrast, fit
quality and model-order ambiguity.
"""

from __future__ import annotations

from pathlib import Path
from typing  import Dict, Optional

import matplotlib

matplotlib.use("Agg")
import matplotlib.cm     as cm
import matplotlib.pyplot as plt
import numpy             as np
from scipy.stats         import pearsonr, spearmanr

from tools.reporting.plotting import PlotBase
from tools.monitoring.logger  import Logger


class MetricsBarPlotter(PlotBase):
    """Renders the summary and contrast-relation figures of a fitted run.

    Attributes:
        n_gaussians: Number of Gaussian slots, i.e. the largest model order.
        logger: Logger for skip warnings.
        fig_dpi: Figure resolution used while rendering.
        save_dpi: Resolution the PNGs are written at.
    """

    def __init__(self, n_gaussians : int, logger : Logger, fig_dpi : int = 150, save_dpi : int = 300) -> None:
        """Configures the metrics plotter.

        Args:
            n_gaussians: Number of Gaussian slots, i.e. the largest model order.
            logger: Logger for skip warnings.
            fig_dpi: Figure resolution used while rendering.
            save_dpi: Resolution the PNGs are written at.
        """
        self.n_gaussians = n_gaussians
        self.logger      = logger
        self.fig_dpi     = fig_dpi
        self.save_dpi    = save_dpi

    def _plot_r2_percentiles(self, summary : dict, out_dir : Path) -> Dict[str, Path]:
        """Saves a bar chart of the R-squared percentiles with the mean marked.

        Args:
            summary: Global summary carrying the R-squared percentiles and mean.
            out_dir: Directory the figure is written to.

        Returns:
            Mapping with the ``r2_percentiles`` figure path; empty when every percentile
            is non-finite.
        """
        qs      = [10, 25, 50, 75, 90]
        pvals   = [summary[f"r2_p{q}"] for q in qs]
        finite  = [value for value in pvals if np.isfinite(value)]
        pcolors = ["#9467bd", "#1f77b4", "#2ca02c", "#ff7f0e", "#d62728"]

        if not finite:
            self.logger.warning("R² percentile plot skipped: no finite values")
            return {}

        fig, ax = plt.subplots(figsize=(6.4, 5))
        bars    = ax.bar(range(len(qs)), pvals, color=pcolors, alpha=0.80, edgecolor="white", lw=0.5)
        ax.set_xticks(range(len(qs)))
        ax.set_xticklabels([f"$p_{{{q}}}$" for q in qs])
        ax.set_ylabel(r"$R^2$")
        ax.set_ylim(bottom=min(0.0, min(finite)) - 0.05)
        ax.set_title(r"$R^2$ percentiles across fitted pixels")
        r2_mean = summary["r2_mean"]

        if np.isfinite(r2_mean):
            ax.axhline(r2_mean, color="black", lw=1.0, ls="--", label=f"mean $= {r2_mean:.4f}$")
            ax.legend(framealpha=0.90)

        ax.grid(True, axis="y", which="major", lw=0.3, alpha=0.40)

        for bar, val in zip(bars, pvals):
            if np.isfinite(val):
                ax.text(bar.get_x() + bar.get_width() / 2, val + 0.01, f"{val:.3f}", ha="center", va="bottom", fontsize=8)

        fig.tight_layout()

        return {"r2_percentiles": self._save(fig, out_dir / "r2_percentiles.png")}

    def _plot_active_count_distribution(self, summary : dict, out_dir : Path) -> Dict[str, Path]:
        """Saves the share of fitted pixels carrying each active-Gaussian count.

        Args:
            summary: Global summary carrying the per-count fractions and fitted-pixel count.
            out_dir: Directory the figure is written to.

        Returns:
            Mapping with the ``active_count_distribution`` figure path.
        """
        fig, ax = plt.subplots(figsize=(6.4, 5))
        n_K     = self.n_gaussians
        k_vals  = list(range(1, n_K + 1))
        fracs   = [summary[f"frac_{k}_fitted"] for k in k_vals]
        cols    = [cm.tab10((k - 1) % 10) for k in k_vals]
        bars    = ax.bar(k_vals, fracs, color=cols, alpha=0.80, edgecolor="white", lw=0.5)

        frac_unfitted = summary["frac_0_active"]
        n_fitted      = summary["n_fitted"]

        ax.set_xticks(k_vals)
        ax.set_xticklabels([f"$K={k}$" for k in k_vals])
        ax.set_ylabel("fraction of fitted pixels")
        ax.set_ylim(0, 1.08)
        ax.set_title("Active-Gaussian count distribution over fitted pixels")
        ax.grid(True, axis="y", which="major", lw=0.3, alpha=0.40)

        for bar, val in zip(bars, fracs):
            if np.isfinite(val):
                ax.text(bar.get_x() + bar.get_width() / 2, val + 0.01, f"{val:.3f}", ha="center", va="bottom", fontsize=8)

        if np.isfinite(frac_unfitted):
            note = f"unfitted ($K=0$) share of all pixels $= {frac_unfitted:.3f}$"
            if np.isfinite(n_fitted):
                note = f"{note}\nfitted pixels $= {int(n_fitted)}$"
            ax.text(0.98, 0.98, note, transform=ax.transAxes, fontsize=8, va="top", ha="right", bbox=dict(boxstyle="round,pad=0.3", fc="white", ec="0.5", alpha=0.88))

        fig.tight_layout()

        return {"active_count_distribution": self._save(fig, out_dir / "active_count_distribution.png")}

    def plot_global_metrics_summary(self, summary : dict, out_dir : Path) -> Dict[str, Path]:
        """Saves the R-squared percentile and active-count figures.

        Args:
            summary: Global summary from the metrics stage.
            out_dir: Directory the figures are written to.

        Returns:
            Mapping from figure name to the saved PNG path.
        """
        saved : Dict[str, Path] = {}

        saved.update(self._plot_r2_percentiles(summary, out_dir))
        saved.update(self._plot_active_count_distribution(summary, out_dir))

        return saved

    def plot_mse_penalty_per_k(self, mse_per_k : np.ndarray, per_k_summary : dict, out_dir : Path) -> Dict[str, Path]:
        """Saves the per-order residual spread, penalty decomposition and win rate.

        Args:
            mse_per_k: Residual MSE of shape (k_max, azimuth, range).
            per_k_summary: Per-order summary carrying the mean MSE, penalty and win fraction.
            out_dir: Directory the figures are written to.

        Returns:
            Mapping with the ``mse_per_k_distribution``, ``penalised_score_decomposition``
            and ``selected_k_distribution`` figure paths.
        """
        k_vals  = list(range(1, self.n_gaussians + 1))
        palette = [cm.tab10((k - 1) % 10) for k in k_vals]
        saved   : Dict[str, Path] = {}

        fig, ax = plt.subplots(figsize=(6.4, 4.8))
        data    = [np.log10(np.maximum(self._subsample(mse_per_k[k - 1].reshape(-1), 200_000, seed=k), 1e-12)) for k in k_vals]
        self._violin_with_iqr(ax, data, palette)
        ax.set_xticks(k_vals)
        ax.set_xticklabels([f"$K={k}$" for k in k_vals])
        ax.set_xlabel(r"model order $K$")
        ax.set_ylabel(r"$\log_{10}\,\mathrm{MSE}$")
        ax.set_title("Residual MSE distribution per model order")
        ax.grid(True, axis="y", which="major", lw=0.3, alpha=0.40)
        fig.tight_layout()

        saved["mse_per_k_distribution"] = self._save(fig, out_dir / "mse_per_k_distribution.png")

        fig, ax   = plt.subplots(figsize=(6.4, 4.8))
        mse_means = [per_k_summary[f"k{k}_mse_mean"]       for k in k_vals]
        pty_means = [per_k_summary[f"k{k}_penalty_mean"]   for k in k_vals]
        tot_means = [per_k_summary[f"k{k}_penalised_mean"] for k in k_vals]
        ax.bar(k_vals, mse_means,                   color="#1f77b4", alpha=0.78, edgecolor="white", lw=0.5, label="mean MSE (peak-normalised profile)")
        ax.bar(k_vals, pty_means, bottom=mse_means, color="#d62728", alpha=0.78, edgecolor="white", lw=0.5, label=r"mean penalty $\lambda_K K$")
        ax.plot(k_vals, tot_means, color="black", lw=1.3, ls="--", marker="o", ms=4, label="mean penalised score")
        ax.set_xticks(k_vals)
        ax.set_xticklabels([f"$K={k}$" for k in k_vals])
        ax.set_xlabel(r"model order $K$")
        ax.set_ylabel("score (peak-normalised profile units)")
        ax.set_title("Penalised score decomposition per model order")
        ax.legend(framealpha=0.90)
        ax.grid(True, axis="y", which="major", lw=0.3, alpha=0.40)
        fig.tight_layout()

        saved["penalised_score_decomposition"] = self._save(fig, out_dir / "penalised_score_decomposition.png")

        fig, ax = plt.subplots(figsize=(6.4, 4.8))
        wins = [per_k_summary[f"k{k}_win_fraction"] for k in k_vals]
        bars = ax.bar(k_vals, wins, color=palette, alpha=0.80, edgecolor="white", lw=0.5)
        ax.set_xticks(k_vals)
        ax.set_xticklabels([f"$K={k}$" for k in k_vals])
        ax.set_xlabel(r"model order $K$")
        ax.set_ylabel("fraction of active pixels")
        ax.set_ylim(0, 1.08)
        ax.set_title("Selected model order distribution")
        ax.grid(True, axis="y", which="major", lw=0.3, alpha=0.40)

        for bar, val in zip(bars, wins):
            if np.isfinite(val):
                ax.text(bar.get_x() + bar.get_width() / 2, val + 0.01, f"{val:.3f}", ha="center", va="bottom", fontsize=8)

        fig.tight_layout()
        saved["selected_k_distribution"] = self._save(fig, out_dir / "selected_k_distribution.png")

        return saved

    def _plot_snr_vs_r2(self, snr_db_map: np.ndarray, r2_map: np.ndarray, out_dir: Path) -> Dict[str, Path]:
        """Saves the hexbin density of fit quality against profile contrast.

        Args:
            snr_db_map: Peak-to-floor contrast of shape (azimuth, range), in dB.
            r2_map: Per-pixel R-squared of the same shape, floored at -1 for plotting.
            out_dir: Directory the figure is written to.

        Returns:
            Mapping with the ``snr_vs_r2`` figure path; empty when no pixel has both
            quantities finite.
        """
        s, r = self._paired_subsample([snr_db_map, np.maximum(r2_map, -1.0)], 400_000)

        if s.size == 0:
            self.logger.warning("Contrast-vs-R² plot skipped: no pixel has both a finite contrast and a finite R²")
            return {}

        fig, ax = plt.subplots(figsize=(6.4, 4.8))
        hb      = ax.hexbin(s, r, gridsize=70, bins="log", cmap="magma", mincnt=1)
        fig.colorbar(hb, ax=ax, fraction=0.04, pad=0.02).set_label("pixel count")

        centers, medians = self._binned_median(s, r)
        ax.plot(centers, medians, color="cyan", lw=1.6, label=r"binned median $R^2$")
        ax.set_xlabel("peak-to-floor contrast [dB]")
        ax.set_ylabel(r"$R^2$  (floored at $-1$)")
        ax.set_title("Fit quality vs peak-to-floor contrast  (uncalibrated proxy, not calibrated SNR)")
        ax.legend(loc="lower right", framealpha=0.90)

        pearson  = float(pearsonr(s, r)[0])  if s.size > 1 else float("nan")
        spearman = float(spearmanr(s, r)[0]) if s.size > 1 else float("nan")
        ax.text(0.98, 0.12, f"Pearson $r$ = {pearson:.3f}\nSpearman $\\rho$ = {spearman:.3f}\n(on plotted, $-1$-floored $R^2$)", transform=ax.transAxes, fontsize=9, va="bottom", ha="right", bbox=dict(boxstyle="round,pad=0.3", fc="white", ec="0.5", alpha=0.88))

        fig.tight_layout()

        return {"snr_vs_r2": self._save(fig, out_dir / "snr_vs_r2.png")}

    def _plot_snr_by_k(self, snr_db_map: np.ndarray, best_k_map: np.ndarray, out_dir: Path) -> Dict[str, Path]:
        """Saves the contrast distribution split by selected model order.

        Args:
            snr_db_map: Peak-to-floor contrast of shape (azimuth, range), in dB.
            best_k_map: Selected model order of the same shape.
            out_dir: Directory the figure is written to.

        Returns:
            Mapping with the ``snr_by_selected_k`` figure path.
        """
        fig, ax = plt.subplots(figsize=(6.4, 4.8))
        k_vals  = list(range(1, self.n_gaussians + 1))
        palette = [cm.tab10((k - 1) % 10) for k in k_vals]
        snr_f   = snr_db_map.reshape(-1)
        bk_f    = best_k_map.reshape(-1)
        data    = [self._subsample(snr_f[bk_f == k], 200_000, seed=k) for k in k_vals]
        self._violin_with_iqr(ax, data, palette)
        ax.set_xticks(k_vals)
        ax.set_xticklabels([f"$K={k}$" for k in k_vals])
        ax.set_xlabel(r"selected model order $K^*$")
        ax.set_ylabel("peak-to-floor contrast [dB]")
        ax.set_title("Peak-to-floor contrast conditioned on selected model order  (uncalibrated proxy, not calibrated SNR)")
        ax.grid(True, axis="y", which="major", lw=0.3, alpha=0.40)
        fig.tight_layout()

        return {"snr_by_selected_k": self._save(fig, out_dir / "snr_by_selected_k.png")}

    def _plot_snr_vs_ambiguity(self, snr_db_map: np.ndarray, rel_margin_map: np.ndarray, out_dir: Path) -> Dict[str, Path]:
        """Saves the hexbin density of model-order ambiguity against profile contrast.

        Args:
            snr_db_map: Peak-to-floor contrast of shape (azimuth, range), in dB.
            rel_margin_map: Relative selection margin of the same shape.
            out_dir: Directory the figure is written to.

        Returns:
            Mapping with the ``snr_vs_k_ambiguity`` figure path; empty when no pixel has
            both quantities finite.
        """
        s_m, rel = self._paired_subsample([snr_db_map, rel_margin_map], 400_000)

        if s_m.size == 0:
            self.logger.warning("Contrast-vs-ambiguity plot skipped: no pixel has both a finite contrast and a finite selection margin")
            return {}

        fig, ax = plt.subplots(figsize=(6.4, 4.8))
        log_rel = np.log10(np.maximum(rel, 1e-9))
        hb      = ax.hexbin(s_m, log_rel, gridsize=70, bins="log", cmap="magma", mincnt=1)
        fig.colorbar(hb, ax=ax, fraction=0.04, pad=0.02).set_label("pixel count")

        centers, medians = self._binned_median(s_m, log_rel)
        ax.plot(centers, medians, color="cyan", lw=1.6, label="binned median margin")
        ax.set_xlabel("peak-to-floor contrast [dB]")
        ax.set_ylabel(r"$\log_{10}$ relative selection margin")
        ax.set_title("K-selection ambiguity vs peak-to-floor contrast  (uncalibrated proxy, not calibrated SNR)")
        ax.legend(loc="lower right", framealpha=0.90)
        fig.tight_layout()

        return {"snr_vs_k_ambiguity": self._save(fig, out_dir / "snr_vs_k_ambiguity.png")}

    def plot_snr_vs_fit_quality(
        self,
        snr_db_map     : np.ndarray,
        r2_map         : np.ndarray,
        best_k_map     : Optional[np.ndarray],
        rel_margin_map : Optional[np.ndarray],
        snr_summary    : dict,
        out_dir        : Path,
    ) -> Dict[str, Path]:
        """Saves every figure relating profile contrast to fit quality and ambiguity.

        Args:
            snr_db_map: Peak-to-floor contrast of shape (azimuth, range), in dB.
            r2_map: Per-pixel R-squared of the same shape.
            best_k_map: Selected model order of the same shape, or None to skip that split.
            rel_margin_map: Relative selection margin of the same shape, or None to skip.
            snr_summary: Contrast summary from the metrics stage.
            out_dir: Directory the figures are written to.

        Returns:
            Mapping from figure name to the saved PNG path.
        """
        saved : Dict[str, Path] = {}

        saved.update(self._plot_snr_vs_r2(snr_db_map, r2_map, out_dir))

        if best_k_map is not None:
            saved.update(self._plot_snr_by_k(snr_db_map, best_k_map, out_dir))

        if rel_margin_map is not None:
            saved.update(self._plot_snr_vs_ambiguity(snr_db_map, rel_margin_map, out_dir))

        return saved
