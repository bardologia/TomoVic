"""Tests for run comparison collection and reporting across trials.

Covers how TrialCollector expands and aggregates per-seed run tags, how it picks
the inference directory of the requested split, and how TrialComparisonReport
renders dispersion and per-run figure sections.
"""

from __future__ import annotations

import json
from pathlib import Path

from pipelines.comparison.comparison_report import TrialComparisonReport
from pipelines.comparison.trial_collector   import TrialCollector
from tools.runtime.completion               import CompletionMarker

from tests.conftest import RecordingLogger


def _run_with_metrics(run_dir: Path, rmse: float, split: str = "test", stamp: str = "20260101_000000") -> None:
    """Writes a completed inference directory under run_dir carrying the given curve RMSE and split."""
    inference_dir = run_dir / "inference" / stamp
    inference_dir.mkdir(parents=True)
    (inference_dir / "metrics.json").write_text(json.dumps({"curve_rmse_gt": rmse}))
    (inference_dir / CompletionMarker.FILENAME).write_text(json.dumps({"stage": "inference", "split": split}))


def test_trial_tag_expands_and_aggregates_seed_runs(tmp_path):
    """Verifies a bare trial tag expands to its seed runs and aggregates into one record with dispersion."""
    _run_with_metrics(tmp_path / "trial_a" / "seed0", 2.0)
    _run_with_metrics(tmp_path / "trial_a" / "seed1", 4.0)

    collector = TrialCollector(runs_dir=tmp_path, run_tags=["trial_a"], logger=RecordingLogger(), inference_split="test")
    records   = collector.collect()

    assert [record.name for record in records] == ["trial_a"]
    assert records[0].metrics["curve_rmse_gt"] == 3.0
    assert records[0].has_inference
    assert collector.seed_dispersion["trial_a"]["n_seeds"] == 2
    assert collector.seed_dispersion["trial_a"]["metrics"]["curve_rmse_gt"] is not None


def test_explicit_seed_run_tags_aggregate_into_one_trial(tmp_path):
    """Verifies explicitly listed seed tags of one trial aggregate into a single record."""
    _run_with_metrics(tmp_path / "trial_a" / "seed0", 2.0)
    _run_with_metrics(tmp_path / "trial_a" / "seed1", 4.0)

    collector = TrialCollector(runs_dir=tmp_path, run_tags=["trial_a/seed0", "trial_a/seed1"], logger=RecordingLogger(), inference_split="test")
    records   = collector.collect()

    assert [record.name for record in records] == ["trial_a"]
    assert records[0].metrics["curve_rmse_gt"] == 3.0


def test_duplicate_unit_and_seed_tags_collapse_once(tmp_path):
    """Verifies a trial tag repeated alongside one of its seed tags is collected only once."""
    _run_with_metrics(tmp_path / "trial_a" / "seed0", 2.0)
    _run_with_metrics(tmp_path / "trial_a" / "seed1", 4.0)

    collector = TrialCollector(runs_dir=tmp_path, run_tags=["trial_a", "trial_a/seed0"], logger=RecordingLogger(), inference_split="test")
    records   = collector.collect()

    assert [record.name for record in records] == ["trial_a"]
    assert records[0].metrics["curve_rmse_gt"] == 3.0
    assert collector.seed_dispersion["trial_a"]["n_seeds"] == 2


def test_flat_runs_pass_through_unchanged(tmp_path):
    """Verifies runs without a seed level are kept separate and report no dispersion."""
    _run_with_metrics(tmp_path / "run_x", 1.0)
    _run_with_metrics(tmp_path / "run_y", 2.0)

    collector = TrialCollector(runs_dir=tmp_path, run_tags=["run_x", "run_y"], logger=RecordingLogger(), inference_split="test")
    records   = collector.collect()

    assert [record.name for record in records] == ["run_x", "run_y"]
    assert collector.seed_dispersion == {}


def test_named_output_subdir_of_other_split_does_not_win(tmp_path):
    """Verifies an inference directory of another split is ignored even when named."""
    _run_with_metrics(tmp_path / "run_x", 1.0)
    _run_with_metrics(tmp_path / "run_x", 9.9, split="val", stamp="region_override")

    collector = TrialCollector(runs_dir=tmp_path, run_tags=["run_x"], logger=RecordingLogger(), inference_split="test")
    records   = collector.collect()

    assert records[0].inference_dir.name       == "20260101_000000"
    assert records[0].metrics["curve_rmse_gt"] == 1.0


def test_single_seed_run_tag_stays_identity(tmp_path):
    """Verifies a lone seed tag keeps its full name and reports no dispersion."""
    _run_with_metrics(tmp_path / "trial_a" / "seed0", 2.0)

    collector = TrialCollector(runs_dir=tmp_path, run_tags=["trial_a/seed0"], logger=RecordingLogger(), inference_split="test")
    records   = collector.collect()

    assert [record.name for record in records] == ["trial_a/seed0"]
    assert collector.seed_dispersion == {}


def test_report_annotates_seed_dispersion(tmp_path):
    """Verifies the overview gains a Seeds column and the metric table a plus-minus dispersion term."""
    _run_with_metrics(tmp_path / "trial_a" / "seed0", 2.0)
    _run_with_metrics(tmp_path / "trial_a" / "seed1", 4.0)
    _run_with_metrics(tmp_path / "run_x", 1.0)

    collector = TrialCollector(runs_dir=tmp_path, run_tags=["trial_a", "run_x"], logger=RecordingLogger(), inference_split="test")
    records   = collector.collect()

    out_dir = tmp_path / "comparison"
    report  = TrialComparisonReport(records=records, out_dir=out_dir, compare_images=False, compare_gifs=False, embed_images=False, logger=RecordingLogger(), seed_dispersion=collector.seed_dispersion)
    report.write_all()

    overview = (out_dir / "overview.md").read_text()
    metrics  = (out_dir / "metrics_comparison.md").read_text()

    assert "Seeds" in overview
    assert "±" in metrics


def test_figure_section_marks_figures_absent_from_a_trial(tmp_path):
    """Verifies the figure section lists the union of figure names and marks the ones a run lacks."""
    _run_with_metrics(tmp_path / "run_x", 1.0)
    _run_with_metrics(tmp_path / "run_y", 2.0)

    for tag, names in (("run_x", ["a.png", "b.png"]), ("run_y", ["a.png"])):
        profiles = tmp_path / tag / "inference" / "20260101_000000" / "figures" / "profiles"
        profiles.mkdir(parents=True)
        for name in names:
            (profiles / name).write_bytes(b"")

    out_dir = tmp_path / "comparison"
    out_dir.mkdir()

    collector = TrialCollector(runs_dir=tmp_path, run_tags=["run_x", "run_y"], logger=RecordingLogger(), inference_split="test")
    report    = TrialComparisonReport(records=collector.collect(), out_dir=out_dir, compare_images=True, compare_gifs=False, embed_images=False, logger=RecordingLogger())

    path = report._write_figure_section("profiles", "Profile reconstructions")
    text = path.read_text()

    assert "## `a.png`" in text
    assert "## `b.png`" in text
    assert text.count("_(not in this run)_") == 1
