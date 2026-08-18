"""Tests for CatalogRoots path validation and RunScanner discovery.

Covers rejection of blank, relative, missing and non-directory paths, symlink
and home-marker resolution, deduplicated recording of opened roots, containment
and deepest-enclosing-root queries, and the scanners that list inference stamps
and checkpoint runs while dropping entries missing their required files.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from catalog_roots import CatalogRoots, RunScanner


@pytest.fixture
def roots():
    """Returns a fresh, empty catalog root registry."""
    return CatalogRoots()


def test_an_empty_path_reports_the_caller_message(roots):
    """Checks a blank path yields no target and the default or caller-supplied message."""
    target, error = roots.resolve("   ")

    assert target is None
    assert error  == CatalogRoots.NOT_SET

    target, error = roots.resolve("", "not set")

    assert target is None
    assert error  == "not set"


def test_a_relative_path_is_refused(roots, tmp_path, monkeypatch):
    """Checks a relative path is refused even when it exists in the working directory."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "runs").mkdir()

    target, error = roots.resolve("runs")

    assert target is None
    assert error  == "an absolute path is required"


def test_a_file_or_a_missing_directory_is_refused(roots, tmp_path):
    """Checks a regular file and a nonexistent path both report not a directory."""
    (tmp_path / "note.md").write_text("x")

    assert roots.resolve(str(tmp_path / "note.md"))[1].startswith("not a directory")
    assert roots.resolve(str(tmp_path / "nowhere"))[1].startswith("not a directory")


def test_resolution_follows_symlinks_and_expands_the_home_marker(roots, tmp_path, monkeypatch):
    """Checks a symlink resolves to its target and a leading tilde expands against HOME."""
    real = tmp_path / "real_runs"
    real.mkdir()
    (tmp_path / "link").symlink_to(real)

    target, error = roots.resolve(str(tmp_path / "link"))

    assert error == ""
    assert target == real.resolve()

    monkeypatch.setenv("HOME", str(tmp_path))
    assert roots.resolve("~/real_runs")[0] == real.resolve()


def test_a_refused_path_is_never_recorded(roots, tmp_path):
    """Checks opening an invalid path leaves the recorded root set empty."""
    roots.open(str(tmp_path / "nowhere"))

    assert roots.snapshot() == ()


def test_open_records_the_resolved_root(roots, tmp_path):
    """Checks the resolved form is recorded and only that exact form is reported known."""
    target, error = roots.open(str(tmp_path) + "/")

    assert error == ""
    assert roots.snapshot() == (str(target),)
    assert roots.known(str(target)) is True
    assert roots.known(str(tmp_path) + "/") is False


def test_containment_covers_nested_paths_only(roots, tmp_path):
    """Checks containment accepts the root and its descendants but not siblings or its parent."""
    runs = tmp_path / "runs"
    (runs / "group" / "run_a").mkdir(parents=True)
    (tmp_path / "runs_backup").mkdir()

    roots.open(str(runs))

    assert roots.contains(runs / "group" / "run_a") is True
    assert roots.contains(runs)                     is True
    assert roots.contains(tmp_path / "runs_backup") is False
    assert roots.contains(tmp_path)                 is False


def test_containment_rejects_a_shared_name_prefix(roots, tmp_path):
    """Checks a sibling directory sharing the root's name prefix is not treated as contained."""
    (tmp_path / "runs").mkdir()
    roots.open(str(tmp_path / "runs"))

    assert roots.contains(Path(str(tmp_path / "runs") + "_backup") / "leak.png") is False


def test_the_enclosing_root_is_the_deepest_match(roots, tmp_path):
    """Checks a path nested under two opened roots resolves to the deeper one, and unknown paths to None."""
    outer = tmp_path / "runs"
    inner = outer / "group"
    inner.mkdir(parents=True)

    roots.open(str(outer))
    roots.open(str(inner))

    assert roots.enclosing(inner / "run_a") == inner.resolve()
    assert roots.enclosing(outer / "run_b") == outer.resolve()
    assert roots.enclosing(tmp_path / "elsewhere") is None


def test_the_same_root_is_recorded_once(roots, tmp_path):
    """Checks equivalent spellings of one directory collapse to a single recorded root."""
    roots.open(str(tmp_path))
    roots.open(str(tmp_path) + "/")
    roots.open(str(tmp_path / "." ))

    assert len(roots.snapshot()) == 1


def _fake_stamp(root: Path, group: str, run: str, stamp: str, extras: tuple = ()) -> Path:
    """Writes a minimal inference stamp directory.

    Args:
        root: Runs root receiving ``<group>/<run>/inference/<stamp>``.
        group: Group directory name.
        run: Run directory name.
        stamp: Stamp directory name.
        extras: Extra stamp-relative files to create alongside the prediction cube.

    Returns:
        Path of the created stamp directory.
    """
    stamp_dir = root / group / run / "inference" / stamp
    cubes     = stamp_dir / "cubes"
    cubes.mkdir(parents=True)

    (cubes / "pred_curves.npy").write_bytes(b"x")
    for rel in extras:
        target = stamp_dir / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"x")

    return stamp_dir


def _fake_checkpoint_run(root: Path, group: str, run: str, config_name: str = "model_config.json") -> Path:
    """Writes a run directory holding a checkpoint and optionally a persisted model config.

    Args:
        root: Runs root receiving ``<group>/<run>``.
        group: Group directory name.
        run: Run directory name.
        config_name: Config file written under ``meta``; empty string writes none.

    Returns:
        Path of the created run directory.
    """
    run_dir = root / group / run
    run_dir.mkdir(parents=True)
    (run_dir / "best_model.pt").write_bytes(b"x")

    if config_name:
        (run_dir / "meta").mkdir()
        (run_dir / "meta" / config_name).write_text("{}")

    return run_dir


def test_stamp_scan_groups_and_sorts_newest_first(tmp_path):
    """Checks discovered stamps are labelled by group and ordered newest first."""
    old  = _fake_stamp(tmp_path, "backbone", "run_a", "2026-01-01_00-00-00")
    new  = _fake_stamp(tmp_path, "backbone", "run_a", "2026-02-01_00-00-00")
    solo = _fake_stamp(tmp_path, ".", "run_b", "2026-01-15_00-00-00")

    out = RunScanner(CatalogRoots()).stamps(str(tmp_path))

    assert out["ok"] is True
    assert [entry["id"] for entry in out["entries"]] == sorted([str(old), str(new), str(solo)], reverse=True)
    assert {entry["group"] for entry in out["entries"]} == {"backbone", "."}
    assert all(entry["stamp"] for entry in out["entries"])


def test_stamp_scan_drops_entries_missing_required_files(tmp_path):
    """Checks a stamp lacking a required file is excluded from the listing."""
    complete = _fake_stamp(tmp_path, "g", "full", "s1", extras=("metrics.json", "cubes/pixel_mse.npy"))
    _fake_stamp(tmp_path, "g", "bare", "s2")

    out = RunScanner(CatalogRoots()).stamps(str(tmp_path), required=("metrics.json", "cubes/pixel_mse.npy"))

    assert [entry["id"] for entry in out["entries"]] == [str(complete)]


def test_stamp_scan_reports_root_errors(tmp_path):
    """Checks scanning a missing root fails with an empty entry list."""
    out = RunScanner(CatalogRoots()).stamps(str(tmp_path / "nowhere"))

    assert out["ok"] is False
    assert out["entries"] == []


def test_checkpoint_scan_requires_the_persisted_config(tmp_path):
    """Checks a checkpoint run without its meta config is excluded from the listing."""
    good = _fake_checkpoint_run(tmp_path, "backbone", "run_ok")
    _fake_checkpoint_run(tmp_path, "backbone", "run_bare", config_name="")

    out = RunScanner(CatalogRoots()).checkpoint_runs(str(tmp_path), "best_model.pt", ("model_config.json",))

    assert out["ok"] is True
    assert [entry["id"] for entry in out["entries"]] == [str(good)]
    assert out["entries"][0]["group"] == "backbone"
    assert out["entries"][0]["stamp"] == ""


def test_checkpoint_scan_accepts_any_of_the_config_names(tmp_path):
    """Checks runs matching any accepted config name are listed and others are dropped."""
    backbone = _fake_checkpoint_run(tmp_path, "backbone", "run_ok")
    dual     = _fake_checkpoint_run(tmp_path, "dual", "run_dual", config_name="dual_model_config.json")
    _fake_checkpoint_run(tmp_path, "profile_ae", "run_ae", config_name="profile_autoencoder_config.json")

    out = RunScanner(CatalogRoots()).checkpoint_runs(str(tmp_path), "best_model.pt", ("model_config.json", "dual_model_config.json"))

    assert out["ok"] is True
    assert [entry["id"] for entry in out["entries"]] == sorted([str(backbone), str(dual)], reverse=True)
