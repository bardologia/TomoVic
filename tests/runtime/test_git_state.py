"""Tests the revision provenance recorded beside run outputs.

Covers how GitState judges a checkout clean or dirty, the saved diff of a dirty
checkout, the unavailable report outside a checkout, and the fields
RunProvenance gathers."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from tools.runtime.git_state import GitState, RunProvenance


def _git(repo, *args):
    """Runs one git command with a throwaway identity inside the given repository."""
    subprocess.run(["git", "-c", "user.email=test@example.org", "-c", "user.name=test", *args], cwd=repo, check=True, capture_output=True)


@pytest.fixture
def checkout(tmp_path, monkeypatch):
    """Returns a one-commit git repository that GitState is pointed at."""
    _git(tmp_path, "init", "-q")
    (tmp_path / "tracked.py").write_text("value = 1\n")
    _git(tmp_path, "add", "tracked.py")
    _git(tmp_path, "commit", "-q", "-m", "init")
    monkeypatch.setattr(GitState, "REPO_ROOT", tmp_path)
    return tmp_path


def test_clean_checkout_reports_the_bare_hash(checkout):
    """Verifies a checkout without changes reports a 12-character hash and nothing else."""
    commit = GitState.commit()

    assert len(commit) == 12
    assert "(" not in commit


def test_untracked_files_do_not_make_the_checkout_dirty(checkout):
    """Verifies untracked outputs inside the checkout leave it clean."""
    (checkout / "notes.md").write_text("scratch\n")

    assert "(dirty working tree)" not in GitState.commit()


def test_tracked_changes_make_the_checkout_dirty(checkout):
    """Verifies an uncommitted edit to a tracked file is reported."""
    (checkout / "tracked.py").write_text("value = 2\n")

    assert GitState.commit().endswith("(dirty working tree)")


def test_snapshot_saves_the_diff_of_tracked_changes(checkout, tmp_path_factory):
    """Verifies a dirty checkout's diff is written next to the run and names the changed line."""
    (checkout / "tracked.py").write_text("value = 2\n")
    target = tmp_path_factory.mktemp("meta")

    path = GitState.snapshot(target)

    assert path == target / GitState.DIFF_FILE
    assert "+value = 2" in path.read_text()


def test_snapshot_of_a_clean_checkout_writes_nothing(checkout, tmp_path_factory):
    """Verifies a clean checkout produces no diff file."""
    target = tmp_path_factory.mktemp("meta")

    assert GitState.snapshot(target) is None
    assert not (target / GitState.DIFF_FILE).exists()


def test_outside_a_checkout_the_commit_is_unavailable(tmp_path, monkeypatch):
    """Verifies a directory that is not a checkout yields an unavailable report naming the reason."""
    monkeypatch.setattr(GitState, "REPO_ROOT", tmp_path)

    assert GitState.commit().startswith("unavailable (")


def test_provenance_carries_the_sources_of_the_parsed_command_line(monkeypatch):
    """Verifies the configuration sources are None without a parsed command line and the ConfigCli mapping with one."""
    from dataclasses import dataclass

    from tools.runtime.config_cli      import ConfigCli
    from tools.runtime.machine_profile import MachineProfile

    @dataclass
    class EntryConfig:
        """One-leaf config standing in for an entry configuration."""
        seed : int = 1

    monkeypatch.setattr(ConfigCli, "parsed", None)

    assert RunProvenance.collect()["config_sources"] is None

    cli = ConfigCli(EntryConfig(), profile=MachineProfile(None))
    cli.apply(["--seed", "5"])
    monkeypatch.setattr(ConfigCli, "parsed", cli)

    sources = RunProvenance.collect()["config_sources"]

    assert sources["machine_profile"] == {"path": None, "state": "disabled"}
    assert sources["leaves"]          == [{"path": "seed", "origin": "command line", "before": 1, "after": 5}]


def test_provenance_reads_only_imported_libraries(monkeypatch):
    """Verifies RunProvenance reports None for a library the process never imported."""
    import sys

    monkeypatch.delitem(sys.modules, "torch", raising=False)

    provenance = RunProvenance.collect()

    assert provenance["torch"] is None
    assert provenance["cuda"] is None
    assert provenance["python"]


def test_commit_reads_a_named_checkout(checkout, tmp_path_factory):
    """A checkout other than this repository, such as PyRAT, is read by path with the same clean and dirty annotations."""
    other = tmp_path_factory.mktemp("other")

    _git(other, "init", "-q")
    (other / "specan.py").write_text("handler = 'original'\n")
    _git(other, "add", "specan.py")
    _git(other, "commit", "-q", "-m", "init")

    clean = GitState.commit(other)

    assert len(clean) == 12
    assert clean != GitState.commit()

    (other / "specan.py").write_text("handler = 'patched in place'\n")

    assert GitState.commit(other) == f"{clean} {GitState.DIRTY_SUFFIX}"
    assert GitState.commit(tmp_path_factory.mktemp("plain")).startswith("unavailable (")
    assert GitState.commit(Path("/nonexistent/pyrat")) == "unavailable (no such directory: /nonexistent/pyrat)"


def test_status_timeout_reports_an_unknown_working_tree(checkout, monkeypatch):
    """A git status that times out on a slow checkout reports the commit with an unknown tree state instead of raising."""
    calls = []
    real  = GitState._git

    def _slow_status(*args, repo_root=None):
        calls.append(args[0])
        if args[0] == "status":
            raise subprocess.TimeoutExpired(cmd="git status", timeout=10)
        return real(*args, repo_root=repo_root)

    monkeypatch.setattr(GitState, "_git", staticmethod(_slow_status))

    assert GitState.commit(checkout).endswith("(working tree state unknown)")
    assert calls == ["rev-parse", "status"]
