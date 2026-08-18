"""Discovery of training runs to feed the trial comparison report.

Expands run tags that contain nested `seedN/` directories into one record per
seed run, then aggregates those seed runs back into a single trial carrying
seed means and dispersion.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib     import Path

from pipelines.shared.comparison.trial_collection import SeedRunAggregator, TrialArtifactReader
from pipelines.shared.comparison.trial_collection import TrialRecord as BaseTrialRecord
from tools.monitoring.logger import Logger


@dataclass
class TrialRecord(BaseTrialRecord):
    """Trial record extended with the inference run's figures directory.

    Attributes:
        figures_dir: Directory holding the run's figure subdirectories, or None
            when the trial has no completed inference.
    """

    figures_dir: Path | None = None

    def figure_subdir(self, name: str) -> Path | None:
        """Returns the named figure subdirectory, or None when it is absent."""
        if self.figures_dir is None:
            return None
        path = self.figures_dir / name
        return path if path.is_dir() else None


class TrialCollector(TrialArtifactReader):
    """Collects the run directories named by the comparison configuration.

    Attributes:
        runs_dir: Root directory holding the run tags.
        run_tags: Run tags requested for comparison.
        logger: Logger used for discovery reporting.
        inference_split: Dataset split whose inference run is read.
        seed_dispersion: Per-trial seed statistics filled in by `collect`.
    """

    SEED_DIR_PATTERN = re.compile(r"seed\d+")

    def __init__(self, runs_dir: Path, run_tags: list[str], logger: Logger, inference_split: str) -> None:
        """Binds the collector to a run root and the tags to compare.

        Args:
            runs_dir: Root directory holding the run tags.
            run_tags: Run tags requested for comparison.
            logger: Logger used for discovery reporting.
            inference_split: Dataset split whose inference run is read.
        """
        self.runs_dir        = runs_dir
        self.run_tags        = run_tags
        self.logger          = logger
        self.inference_split = inference_split
        self.seed_dispersion = {}

    def _attach_figures(self, record: TrialRecord, inference_dir: Path) -> None:
        """Points the record at the inference run's figures directory when present."""
        figures_dir = inference_dir / "figures"
        if figures_dir.is_dir():
            record.figures_dir = figures_dir

    def _nested_seed_dirs(self, run_dir: Path) -> list[Path]:
        """Returns the `seedN/` subdirectories of a run directory, sorted by name."""
        if not run_dir.is_dir() or self.SEED_DIR_PATTERN.fullmatch(run_dir.name):
            return []

        return sorted(d for d in run_dir.iterdir() if d.is_dir() and self.SEED_DIR_PATTERN.fullmatch(d.name))

    def _expand_tags(self) -> list[tuple[str, Path]]:
        """Expands seed-swept run tags into one entry per seed run.

        Returns:
            (display name, run directory) pairs, deduplicated by directory and
            keeping the requested tag order.
        """
        expanded = []
        seen     = set()

        for tag in self.run_tags:
            run_dir   = self.runs_dir / tag
            seed_dirs = self._nested_seed_dirs(run_dir)

            if seed_dirs:
                self.logger.ok(f"'{tag}' expanded to {len(seed_dirs)} seed run(s)")

            pairs = [(f"{tag}/{seed_dir.name}", seed_dir) for seed_dir in seed_dirs] if seed_dirs else [(tag, run_dir)]
            for name, path in pairs:
                if str(path) in seen:
                    continue
                seen.add(str(path))
                expanded.append((name, path))

        return expanded

    def collect(self) -> list[TrialRecord]:
        """Reads every requested run and aggregates its seed runs into trials.

        Returns:
            One record per trial, with metrics reported as seed means; missing
            run directories are logged and skipped. `seed_dispersion` is filled
            in as a side effect.
        """
        self.logger.section("Collecting trials")
        records = []

        for tag, run_dir in self._expand_tags():
            if not run_dir.is_dir():
                self.logger.error(f"Run directory not found: {run_dir}")
                continue

            record            = TrialRecord(name=tag, run_dir=run_dir)
            record.checkpoint = self._read_checkpoint(run_dir)
            self._attach_inference(record)

            status = f"inference {record.inference_dir.name}" if record.has_inference else "no inference"
            self.logger.info(f"{record.name:<36} {status}")

            records.append(record)

        aggregator = SeedRunAggregator()
        aggregated = aggregator.aggregate(records)

        self.seed_dispersion = aggregator.seed_dispersion
        if self.seed_dispersion:
            self.logger.ok(f"Aggregated {len(records)} seed run(s) into {len(aggregated)} trial(s), metrics reported as seed means")

        return aggregated
