"""Markdown reports comparing several training trials side by side.

Renders an overview with leaderboards, a full metric comparison table, and
per-subdirectory figure and animation galleries built from each trial's latest
completed inference run.
"""

from __future__ import annotations

import re
from pathlib import Path

from pipelines.comparison.trial_collector          import TrialRecord
from pipelines.shared.comparison.comparison_report import ComparisonReportBase
from tools.metrics.scoring                         import FiniteScalar, MetricOrientation
from tools.reporting.markdown                      import MarkdownTable, ScalarFormatter
from tools.reporting.reporting                     import MetricSectionGrouper, ReportAssets
from tools.monitoring.logger                       import Logger


class TrialComparisonReport(ComparisonReportBase):
    """Writes the markdown comparison of a set of collected trials.

    Attributes:
        records: One record per trial, already seed-aggregated.
        out_dir: Directory the markdown files and assets are written to.
        compare_images: Whether per-figure gallery pages are produced.
        compare_gifs: Whether the animation gallery page is produced.
        logger: Logger used for progress reporting.
        seed_dispersion: Per-trial seed statistics keyed by trial name.
        has_seed_sweep: True when at least one trial aggregates several seeds.
        assets: Resolver for image links and report headers.
    """

    FIGURE_SUBDIRS = [
        ("tracks",              "Passes and interferograms"),
        ("input_channels",      "Input channels"),
        ("profiles",            "Profile reconstructions"),
        ("pixel_maps",          "Per-pixel metric maps"),
        ("histograms",          "Metric distributions"),
        ("param_distributions", "Parameter distributions"),
        ("param_scatter",       "Parameter scatter plots"),
        ("param_error_maps",    "Parameter error maps"),
        ("param_error_hists",   "Parameter error histograms"),
        ("slots",               "Slot diagnostics"),
        ("ssim",                "SSIM curves (denorm)"),
        ("ssim_norm",           "SSIM curves (unit-area)"),
        ("elev_metrics",        "Per-elevation-bin metrics"),
        ("slices",              "Tomogram slices"),
        ("slices_norm",         "Tomogram slices (unit-area)"),
        ("reduced",             "Classical baseline"),
    ]

    HEADLINE_METRICS = [
        ("curve_rmse_gt",                "RMSE"),
        ("curve_mae_gt",                 "MAE"),
        ("overall_r2_gt",                "R²"),
        ("psnr_db_gt",                   "PSNR"),
        ("pixel_r2_gt_mean",             "Pixel R²"),
        ("pixel_cosine_gt_mean",         "Cosine"),
        ("ssim_gt_elev_mean",            "SSIM elev"),
        ("ssim_norm_elev_mean",          "SSIM norm"),
        ("pixel_peak_err_units_mean_gt", "Peak err"),
        ("relative_mse_reduction",       "vs Capon"),
    ]

    COUNT_METRICS = [
        ("count_exact_frac", "Exact"),
        ("count_under_frac", "Under"),
        ("count_over_frac",  "Over"),
    ]

    HEADLINE_GROUPS = [
        ("Curve error",           ["curve_rmse_gt", "curve_mae_gt", "psnr_db_gt"]),
        ("Variance explained",    ["overall_r2_gt", "pixel_r2_gt_mean"]),
        ("Structural similarity", ["ssim_gt_elev_mean", "ssim_norm_elev_mean"]),
        ("Shape (cosine)",        ["pixel_cosine_gt_mean"]),
        ("Peak location",         ["pixel_peak_err_units_mean_gt"]),
        ("Gain vs Capon",         ["relative_mse_reduction"]),
    ]

    PRECISION_BUCKET_PATTERN = re.compile(r"^matched_precision_gt(\d+)$")
    RECALL_BUCKET_PATTERN    = re.compile(r"^matched_recall_gt(\d+)$")

    def __init__(
        self,
        records         : list[TrialRecord],
        out_dir         : Path,
        compare_images  : bool,
        compare_gifs    : bool,
        embed_images    : bool,
        logger          : Logger,
        seed_dispersion : dict | None = None,
    ) -> None:
        """Binds the report to the collected trials and output directory.

        Args:
            records: Collected trial records to compare.
            out_dir: Directory the markdown files are written to.
            compare_images: Whether to emit per-subdirectory figure galleries.
            compare_gifs: Whether to emit the animation gallery.
            embed_images: Whether images are inlined rather than linked.
            logger: Logger used for progress reporting.
            seed_dispersion: Per-trial seed statistics keyed by trial name.
        """
        self.records         = records
        self.out_dir         = Path(out_dir)
        self.compare_images  = compare_images
        self.compare_gifs    = compare_gifs
        self.logger          = logger
        self.seed_dispersion = seed_dispersion or {}
        self.has_seed_sweep  = any(entry["n_seeds"] > 1 for entry in self.seed_dispersion.values())
        self.assets          = ReportAssets(base=self.out_dir, embed_images=embed_images)

    def _n_seeds(self, name: str) -> int:
        """Returns the number of seed runs aggregated into a trial."""
        return self.seed_dispersion.get(name, {}).get("n_seeds", 1)

    def _write_overview(self) -> Path:
        """Writes the run table and leaderboards to `overview.md`.

        Returns:
            Path of the written overview file.
        """
        lines  = self.assets.header("Trial Comparison Overview")
        lines += ["## Runs\n"]

        if self.has_seed_sweep:
            lines += ["Seed-swept trials aggregate their seed runs: metrics and losses are seed means (± sample std), while the inference run, figures, and report link come from one representative seed.\n"]

        headers = ["Run", "Seeds", "Inference run", "Checkpoint", "Best val loss", "Epochs", "Report"] if self.has_seed_sweep else ["Run", "Inference run", "Checkpoint", "Best val loss", "Epochs", "Report"]
        table   = MarkdownTable(tuple(headers))

        for r in self.records:
            inference  = f"`{r.inference_dir.name}`" if r.has_inference else "_(no inference)_"
            epoch      = ScalarFormatter.format_scalar(r.checkpoint.get("epoch"))
            best_epoch = ScalarFormatter.format_scalar(r.checkpoint.get("best_epoch"))
            best_std   = self.seed_dispersion.get(r.name, {}).get("best_val_loss_std")
            best_loss  = ScalarFormatter.with_std(ScalarFormatter.format_scalar(r.checkpoint.get("best_val_loss")), best_std)
            n_epochs   = ScalarFormatter.format_scalar(r.checkpoint.get("n_train_epochs"))
            report_lnk = f"[report.md]({self.assets.rel(r.report_path)})" if r.report_path else "—"

            cells = [f"`{r.name}`", inference, f"{epoch} (best {best_epoch})", best_loss, n_epochs, report_lnk]
            if self.has_seed_sweep:
                cells.insert(1, str(self._n_seeds(r.name)))
            table.add_row(*cells)

        lines += table.render()
        lines.append("")
        lines += self._leaderboard()

        out = self.out_dir / "overview.md"
        out.write_text("\n".join(lines), encoding="utf-8")
        return out

    def _leaderboard(self) -> list[str]:
        """Returns the markdown lines of every leaderboard section.

        Covers the headline metrics, the correlation-grouped variant, matched
        precision and recall per ground-truth scatterer count, and the count
        calibration table.
        """
        scored = [r for r in self.records if r.metrics]
        if not scored:
            return ["## Leaderboard\n", "_No inference metrics available._\n"]

        headline_intro = (
            "`Score` is a magnitude-aware composite in [0, 1] (per metric, 1 = best and 0 = worst by min-max, then "
            "averaged; missing metrics score 0). `Mean rank` is the tie-averaged ordinal rank (1 = best; missing "
            "metrics rank last), `Wins` counts metrics where the trial is best, `Δ` is the score gap to the leader. "
            "Trials are ordered by `Score`. Per-metric cells show the rank; the best is in **bold**."
        )
        grouped_intro = (
            "Correlated headline metrics are averaged within a group first, so the curve-error metrics (RMSE / MAE / "
            "PSNR) do not outvote the independent axes. `Grouped score` averages the group scores with equal weight; "
            "each cell is the group score with its group rank in parentheses (best in **bold**)."
        )
        precision_intro = (
            "Matched (permutation-invariant) precision per GT scatterer count `k` — the share of predicted scatterers "
            "that hit a true scatterer where the pixel truly holds `k`. Precision rewards under-prediction, so read it "
            "alongside the recall leaderboard, never on its own."
        )
        recall_intro = (
            "Matched (permutation-invariant) recall per GT scatterer count `k` — the share of true scatterers in "
            "`k`-scatterer pixels that the model recovers. This is the scatterer-recovery metric; rank trials on it "
            "rather than on precision."
        )
        count_intro = (
            "Count calibration: `Exact` is the pixel share where the predicted active scatterer count equals GT "
            "(higher better), `Under` / `Over` are the shares where the model predicts too few / too many (lower "
            "better). Permutation-invariant."
        )

        lines  = self._rank_section("Run",    "Leaderboard",            headline_intro,  self.HEADLINE_METRICS,           scored)
        lines += self._grouped_section("Run", "Grouped Leaderboard",    grouped_intro,   self.HEADLINE_GROUPS,            scored)
        lines += self._rank_section("Run",    "Per-Gaussian Precision", precision_intro, self._precision_metrics(scored), scored)
        lines += self._rank_section("Run",    "Per-Gaussian Recall",    recall_intro,    self._recall_metrics(scored),    scored)
        lines += self._rank_section("Run",    "Count Calibration",      count_intro,     self.COUNT_METRICS,              scored)
        return lines

    def _precision_metrics(self, scored: list[TrialRecord]) -> list[tuple[str, str]]:
        """Returns the (metric key, column label) pairs for matched precision."""
        buckets = self._bucket_indices(scored, self.PRECISION_BUCKET_PATTERN)

        metrics = [("matched_precision", "Overall")]
        metrics += [(f"matched_precision_gt{k}", f"k={k}") for k in buckets]
        return metrics

    def _recall_metrics(self, scored: list[TrialRecord]) -> list[tuple[str, str]]:
        """Returns the (metric key, column label) pairs for matched recall."""
        buckets = self._bucket_indices(scored, self.RECALL_BUCKET_PATTERN)

        metrics = [("matched_recall", "Overall")]
        metrics += [(f"matched_recall_gt{k}", f"k={k}") for k in buckets]
        return metrics

    def _bucket_indices(self, scored: list[TrialRecord], pattern: re.Pattern) -> list[int]:
        """Returns the sorted scatterer counts present in the trials' metric keys.

        Args:
            scored: Trials carrying inference metrics.
            pattern: Regex whose first group captures the scatterer count.

        Returns:
            Ascending list of ground-truth scatterer counts k found in any trial.
        """
        buckets: set[int] = set()
        for r in scored:
            for key in r.metrics:
                match = pattern.match(key)
                if match:
                    buckets.add(int(match.group(1)))

        return sorted(buckets)

    def _write_metrics(self) -> Path:
        """Writes the grouped scalar-metric comparison to `metrics_comparison.md`.

        Returns:
            Path of the written metrics file.
        """
        scored = [r for r in self.records if r.metrics]

        lines  = self.assets.header("Metrics Comparison")
        lines += ["> Best value per metric in **bold** (↓ lower is better, ↑ higher is better). Per-bin array metrics are excluded.\n"]
        lines += [
            "> **Reading guide.** Gaussian accuracy is reported by the *Matched Gaussian "
            "(Permutation-Invariant)* section, which Hungarian-matches predicted Gaussians to GT before "
            "scoring. `count_acc_gt{k}` is exact-count agreement (calibration), not scatterer recovery — use "
            "`matched_recall_gt{k}`. Precision and F1 reward under-prediction (a model that collapses slots has "
            "few false positives), so do not rank trials on them; read them alongside recall.\n"
        ]

        if not scored:
            lines += ["_No inference metrics available._\n"]
        else:
            all_keys = MetricSectionGrouper.scalar_keys(scored)
            for title, keys in MetricSectionGrouper().group(all_keys):
                lines += [f"## {title}\n", *self._metric_table(keys, scored)]

        out = self.out_dir / "metrics_comparison.md"
        out.write_text("\n".join(lines), encoding="utf-8")
        return out

    def _metric_table(self, keys: list[str], scored: list[TrialRecord]) -> list[str]:
        """Renders one trial-by-metric table with the best value bolded.

        Args:
            keys: Metric keys forming the table columns.
            scored: Trials carrying inference metrics, one per row.

        Returns:
            Markdown lines of the table followed by a blank line.
        """
        headers = ["Run"]
        best    : dict[str, float | None] = {}

        for key in keys:
            direction = MetricOrientation.direction(key)
            arrow     = {"higher": " ↑", "lower": " ↓", None: ""}[direction]
            headers.append(f"`{key}`{arrow}")

            numeric = [v for v in (FiniteScalar.coerce(r.metrics.get(key)) for r in scored) if v is not None]
            best[key] = (max(numeric) if direction == "higher" else min(numeric)) if direction is not None and numeric else None

        table = MarkdownTable(headers)

        for r in scored:
            cells = [f"`{r.name}`"]
            for key in keys:
                value  = r.metrics.get(key)
                cell   = ScalarFormatter.format_scalar(value)
                finite = FiniteScalar.coerce(value)
                if best[key] is not None and finite is not None and finite == best[key]:
                    cell = f"**{cell}**"
                cells.append(ScalarFormatter.with_std(cell, self._metric_seed_std(r.name, key)))
            table.add_row(*cells)

        return [*table.render(), ""]

    def _write_figure_section(self, subdir: str, title: str) -> Path | None:
        """Writes one figure gallery pairing the same figure across trials.

        Args:
            subdir: Name of the figure subdirectory inside each inference run.
            title: Human-readable section title.

        Returns:
            Path of the written gallery, or None when no trial holds figures
            in that subdirectory.
        """
        resolved = [(r, r.figure_subdir(subdir)) for r in self.records if r.has_inference]
        scored   = [(r, path, {p.name for p in path.glob("*.png")}) for r, path in resolved if path is not None]

        all_names = {name for _record, _path, names in scored for name in names}
        if not all_names:
            return None

        sorted_names = sorted(all_names, key=ReportAssets.natural_key)

        lines  = self.assets.header(f"Figure Comparison – {title}")
        lines += [f"> Figures from the `{subdir}/` directory. Only trials with a completed inference run are shown.\n"]

        for name in sorted_names:
            lines.append(f"## `{name}`\n")
            for record, path, names in scored:
                if name in names:
                    lines.append(f"*{record.name}*  \n![]({self.assets.src(path / name)})\n")
                else:
                    lines.append(f"*{record.name}* — _(not in this run)_\n")
            lines.append("")

        slug = re.sub(r"[^a-z0-9]+", "_", subdir.lower()).strip("_")
        out  = self.out_dir / f"figures_{slug}.md"
        out.write_text("\n".join(lines), encoding="utf-8")
        return out

    def _write_gifs(self) -> Path | None:
        """Writes the animation gallery to `gif_comparison.md`.

        Returns:
            Path of the written gallery, or None when no trial has animations.
        """
        scored = [r for r in self.records if r.has_inference and r.animations]
        if not scored:
            return None

        all_names: set[str] = set()
        for r in scored:
            all_names.update(p.name for p in r.animations)

        sorted_names = sorted(all_names, key=ReportAssets.natural_key)

        lines  = self.assets.header("Animation Comparison")
        lines += ["> GIF animations from each trial’s latest inference run. Only trials with animations are shown.\n"]

        for name in sorted_names:
            lines.append(f"## `{name}`\n")
            for r in scored:
                gif_path = r.inference_dir / "animations" / name
                if gif_path.exists():
                    lines.append(f"*{r.name}*  \n![]({self.assets.src(gif_path)})\n")
                else:
                    lines.append(f"*{r.name}* — _(not in this run)_\n")
            lines.append("")

        out = self.out_dir / "gif_comparison.md"
        out.write_text("\n".join(lines), encoding="utf-8")
        return out

    def write_all(self) -> list[Path]:
        """Writes every enabled report section and returns their paths.

        Returns:
            Paths of the overview, the metric comparison, and any figure or
            animation galleries that were produced.
        """
        self.out_dir.mkdir(parents=True, exist_ok=True)

        self.logger.section("Writing comparison reports")

        written = [self._write_overview(), self._write_metrics()]
        self.logger.info(f"Overview and metrics written")

        if self.compare_images:
            for subdir, title in self.FIGURE_SUBDIRS:
                path = self._write_figure_section(subdir, title)
                if path:
                    self.logger.info(f"Figures [{subdir}] : {path.name}")
                    written.append(path)

        if self.compare_gifs:
            path = self._write_gifs()
            if path:
                self.logger.info(f"Animations : {path.name}")
                written.append(path)

        return written
