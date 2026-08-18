"""Tests for run discovery in the webui dataset browser.

Covers recursive discovery of run directories at any depth, the relative names
and checkpoint/inference flags reported for each, the pruning at run boundaries
and skipping of hidden directories, the aggregate rows offered for multi-seed
trials, and the grouping listing that counts runs per parent directory.
"""

from __future__ import annotations

from pathlib import Path

from dataset_browser import DatasetBrowser
from web_logger      import WebLogger


def _make_run(directory: Path, checkpoint: bool = False, inference: bool = False) -> None:
    """Writes a minimal run directory.

    Args:
        directory: Run directory to create, always given a meta model config.
        checkpoint: Whether a best_model.pt placeholder is written.
        inference: Whether an inference subdirectory is created.
    """
    (directory / "meta").mkdir(parents=True)
    (directory / "meta" / "model_config.json").write_text("{}")
    if checkpoint:
        (directory / "best_model.pt").write_text("x")
    if inference:
        (directory / "inference" / "sub").mkdir(parents=True)


def test_runs_are_discovered_at_any_depth(tmp_path):
    """Checks runs nested at different depths are all found and empty groups are ignored."""
    runs = tmp_path / "runs"
    _make_run(runs / "run_top", checkpoint=True)
    _make_run(runs / "group_a" / "run_a1")
    _make_run(runs / "group_a" / "deep" / "run_a2", inference=True)
    (runs / "empty_group").mkdir(parents=True)

    result = DatasetBrowser(WebLogger()).runs([str(runs)])

    assert result["ok"] is True
    names = sorted(entry["name"] for entry in result["runs"])
    assert names == ["group_a/deep/run_a2", "group_a/run_a1", "run_top"]


def test_run_names_are_relative_to_base_and_expose_flags(tmp_path):
    """Checks run names are relative to the opened base and carry accurate checkpoint, inference and path fields."""
    runs = tmp_path / "runs"
    _make_run(runs / "group_a" / "run_a1")
    _make_run(runs / "group_a" / "deep" / "run_a2", checkpoint=True, inference=True)

    entries = {entry["name"]: entry for entry in DatasetBrowser(WebLogger()).runs([str(runs)])["runs"]}

    assert entries["group_a/run_a1"]["has_checkpoint"] is False
    assert entries["group_a/run_a1"]["has_inference"] is False
    assert entries["group_a/deep/run_a2"]["has_checkpoint"] is True
    assert entries["group_a/deep/run_a2"]["has_inference"] is True
    assert Path(entries["group_a/deep/run_a2"]["path"]) == runs / "group_a" / "deep" / "run_a2"


def test_walk_prunes_at_run_boundary_and_skips_hidden(tmp_path):
    """Checks the walk does not descend into meta or inference and ignores dot-prefixed directories."""
    runs = tmp_path / "runs"
    _make_run(runs / "run_top", inference=True)
    hidden = runs / ".hidden_run"
    hidden.mkdir()
    (hidden / "meta").mkdir()

    names = [entry["name"] for entry in DatasetBrowser(WebLogger()).runs([str(runs)])["runs"]]

    assert names == ["run_top"]
    assert not any("meta" in name.split("/")[-1] for name in names)
    assert not any("inference" in name for name in names)


def test_seed_units_are_offered_with_aggregate_flags(tmp_path):
    """Checks multi-seed trials gain an aggregate row whose flags hold only when every seed qualifies."""
    runs = tmp_path / "runs"
    _make_run(runs / "group_a" / "trial_x" / "seed0", checkpoint=True, inference=True)
    _make_run(runs / "group_a" / "trial_x" / "seed1", checkpoint=True, inference=True)
    _make_run(runs / "group_a" / "trial_y" / "seed0", checkpoint=True)
    _make_run(runs / "group_a" / "trial_y" / "seed1", checkpoint=True, inference=True)
    _make_run(runs / "run_top", checkpoint=True)

    result  = DatasetBrowser(WebLogger()).runs([str(runs)], seed_units=True)
    entries = {entry["name"]: entry for entry in result["runs"]}

    assert entries["group_a/trial_x"]["n_seeds"] == 2
    assert entries["group_a/trial_x"]["has_inference"] is True
    assert entries["group_a/trial_x"]["has_checkpoint"] is True
    assert entries["group_a/trial_y"]["has_inference"] is False
    assert "n_seeds" not in entries["run_top"]


def test_seed_units_report_their_own_inference(tmp_path):
    """Checks a trial with its own inference directory is distinguished from one that only has per-seed inference."""
    runs = tmp_path / "runs"
    _make_run(runs / "trial_x" / "seed0", inference=True)
    _make_run(runs / "trial_y" / "seed0", inference=True)
    (runs / "trial_x" / "inference" / "seed_comparison").mkdir(parents=True)

    entries = {entry["name"]: entry for entry in DatasetBrowser(WebLogger()).runs([str(runs)], seed_units=True)["runs"]}

    assert entries["trial_x"]["own_inference"] is True
    assert entries["trial_y"]["own_inference"] is False


def test_seed_unit_rows_precede_their_seed_runs(tmp_path):
    """Checks the aggregate row is listed before the individual seed runs."""
    runs = tmp_path / "runs"
    _make_run(runs / "trial_x" / "seed0")
    _make_run(runs / "trial_x" / "seed1")

    names = [entry["name"] for entry in DatasetBrowser(WebLogger()).runs([str(runs)], seed_units=True)["runs"]]

    assert names == ["trial_x", "trial_x/seed0", "trial_x/seed1"]


def test_seed_units_absent_by_default_and_for_base_level_seeds(tmp_path):
    """Checks aggregate rows appear only when requested and never for a seed sitting directly at the base."""
    runs = tmp_path / "runs"
    _make_run(runs / "trial_x" / "seed0")
    _make_run(runs / "seed0")

    default_names = [entry["name"] for entry in DatasetBrowser(WebLogger()).runs([str(runs)])["runs"]]
    unit_names    = [entry["name"] for entry in DatasetBrowser(WebLogger()).runs([str(runs)], seed_units=True)["runs"]]

    assert default_names == ["seed0", "trial_x/seed0"]
    assert unit_names    == ["seed0", "trial_x", "trial_x/seed0"]


def test_run_groups_lists_parent_dirs_of_runs_with_counts(tmp_path):
    """Checks the group listing names each run parent with its run count and path, skipping top-level runs."""
    runs = tmp_path / "runs"
    _make_run(runs / "group_a" / "seed0")
    _make_run(runs / "group_a" / "seed1")
    _make_run(runs / "group_b" / "seed0")
    _make_run(runs / "run_top")

    result  = DatasetBrowser(WebLogger()).run_groups([str(runs)])
    entries = {entry["name"]: entry for entry in result["groups"]}

    assert result["ok"] is True
    assert sorted(entries) == ["group_a", "group_b"]
    assert entries["group_a"]["n_runs"] == 2
    assert entries["group_b"]["n_runs"] == 1
    assert Path(entries["group_a"]["path"]) == runs / "group_a"
