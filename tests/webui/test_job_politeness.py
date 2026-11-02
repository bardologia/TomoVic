"""Tests for the launch politeness level and the runtime job throttle.

Covers the prefix each level renders, the persisted settings round trip and
its loud failure on a malformed file, the validation of configuration
requests, the throttle's command lines over the nuke's targets with the
priority tools stubbed, its outcome reporting on failures and a missing tool,
the nuke's target enumeration, and one real run that lowers a child process's
nice value and I/O class through the installed tools.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys

import pytest

from politeness      import JobPoliteness, JobThrottle
from process_manager import ProcessNuke
from web_logger      import WebLogger

from tests.webui.conftest import StubPaths


class StubNuke:
    """Nuke stand-in answering a fixed list of target pids.

    Attributes:
        pids : Pids returned by `targets`.
    """

    def __init__(self, pids: list[int]) -> None:
        """Stores the pids to report."""
        self.pids = pids

    def targets(self) -> list[int]:
        """Returns the fixed pid list."""
        return list(self.pids)


class RecordingRun:
    """Replacement for subprocess.run recording every command and answering scripted results.

    Attributes:
        calls   : Argument lists in call order.
        results : Scripted (returncode, stderr) pairs consumed in order.
    """

    def __init__(self, results: list[tuple[int, str]]) -> None:
        """Stores the scripted results."""
        self.calls   = []
        self.results = list(results)

    def __call__(self, argv, **kwargs) -> subprocess.CompletedProcess:
        """Records the call and returns the next scripted result."""
        self.calls.append(list(argv))
        code, err = self.results.pop(0)
        return subprocess.CompletedProcess(argv, code, stdout="", stderr=err)


@pytest.fixture
def politeness(tmp_path):
    """Returns a politeness object over a throwaway logs directory."""
    return JobPoliteness(StubPaths(tmp_path), WebLogger())


def _nice_of(pid: int) -> int:
    """Returns a process's nice value from /proc/<pid>/stat."""
    raw = open(f"/proc/{pid}/stat").read()
    return int(raw[raw.rindex(")") + 2:].split()[16])


def test_the_default_level_is_polite(politeness):
    """Checks a fresh console launches at nice 10 with best-effort I/O 7 and auto-throttle off."""
    assert politeness.level()         == "polite"
    assert politeness.auto_throttle() is False
    assert politeness.prefix()        == ["nice", "-n", "10", "ionice", "-c", "2", "-n", "7"]


@pytest.mark.parametrize("level, prefix", [
    ("off",        []),
    ("polite",     ["nice", "-n", "10", "ionice", "-c", "2", "-n", "7"]),
    ("background", ["nice", "-n", "19", "ionice", "-c", "3"]),
])
def test_each_level_renders_its_prefix(politeness, level, prefix):
    """Checks every level maps to the documented nice and ionice arguments."""
    politeness.configure({"level": level})

    assert politeness.prefix() == prefix
    assert politeness.state()["prefix"] == " ".join(prefix)


def test_configure_persists_and_a_new_instance_reads_it_back(tmp_path, politeness):
    """Checks the settings survive a restart through the JSON file."""
    result = politeness.configure({"level": "background", "auto_throttle": False})

    assert result["ok"] is True
    assert json.loads(politeness.path.read_text()) == {"level": "background", "auto_throttle": False}

    again = JobPoliteness(StubPaths(tmp_path), WebLogger())

    assert again.level()         == "background"
    assert again.auto_throttle() is False


def test_configure_keeps_the_other_setting_when_only_one_is_sent(politeness):
    """Checks a partial payload changes only the key it carries."""
    politeness.configure({"auto_throttle": True})

    assert politeness.level()         == "polite"
    assert politeness.auto_throttle() is True

    politeness.configure({"level": "off"})

    assert politeness.level()         == "off"
    assert politeness.auto_throttle() is True


def test_configure_rejects_an_unknown_level_and_changes_nothing(politeness):
    """Checks a bad level is answered with an error and leaves the settings and file untouched."""
    result = politeness.configure({"level": "turbo"})

    assert result["ok"] is False
    assert "turbo" in result["error"]
    assert politeness.level() == "polite"
    assert not politeness.path.exists()


def test_the_state_describes_the_level(politeness):
    """Checks the UI snapshot carries the nice value, the label, the level list and the settings path."""
    state = politeness.state()

    assert state["nice"]          == 10
    assert state["label"]         == "nice 10, ionice best-effort 7"
    assert state["levels"]        == ["off", "polite", "background"]
    assert state["settings_path"] == str(politeness.path)


def test_a_malformed_settings_file_fails_loudly(tmp_path):
    """Checks a file naming an unknown level, or missing a key, raises instead of silently defaulting."""
    paths = StubPaths(tmp_path)
    path  = paths.logs_dir / JobPoliteness.SETTINGS_NAME
    path.parent.mkdir(parents=True, exist_ok=True)

    path.write_text(json.dumps({"level": "turbo", "auto_throttle": True}))
    with pytest.raises(ValueError):
        JobPoliteness(paths, WebLogger())

    path.write_text(json.dumps({"level": "polite"}))
    with pytest.raises(KeyError):
        JobPoliteness(paths, WebLogger())


def test_the_throttle_runs_renice_and_ionice_over_the_targets(monkeypatch):
    """Checks both priority tools are called once with every target pid and the result counts them."""
    run = RecordingRun([(0, ""), (0, "")])
    monkeypatch.setattr(subprocess, "run", run)
    throttle = JobThrottle(StubNuke([101, 202, 303]), WebLogger())

    result = throttle.apply()

    assert run.calls == [["renice", "-n", "19", "-p", "101", "202", "303"], ["ionice", "-c", "3", "-p", "101", "202", "303"]]
    assert result == {"ok": True, "processes": 3, "renice": 0, "ionice": 0, "error": ""}


def test_the_throttle_with_no_targets_runs_nothing(monkeypatch):
    """Checks an idle user triggers no priority command."""
    run = RecordingRun([])
    monkeypatch.setattr(subprocess, "run", run)

    result = JobThrottle(StubNuke([]), WebLogger()).apply()

    assert run.calls == []
    assert result["ok"] is True
    assert result["processes"] == 0


def test_a_failing_renice_is_reported_and_ionice_still_runs(monkeypatch):
    """Checks a non-zero renice yields ok False with its stderr tail while ionice is still attempted."""
    run = RecordingRun([(1, "renice: failed to set priority for 101 (process ID): Permission denied"), (0, "")])
    monkeypatch.setattr(subprocess, "run", run)

    result = JobThrottle(StubNuke([101]), WebLogger()).apply()

    assert len(run.calls) == 2
    assert result["ok"]     is False
    assert result["renice"] == 1
    assert result["ionice"] == 0
    assert "Permission denied" in result["error"]


def test_a_missing_tool_is_reported_as_exit_127(monkeypatch):
    """Checks an absent binary does not raise but comes back as a failed throttle."""
    def missing(argv, **kwargs):
        raise FileNotFoundError(f"No such file or directory: {argv[0]!r}")

    monkeypatch.setattr(subprocess, "run", missing)

    result = JobThrottle(StubNuke([101]), WebLogger()).apply()

    assert result["ok"]     is False
    assert result["renice"] == 127
    assert result["ionice"] == 127
    assert "renice" in result["error"] or "ionice" in result["error"]


def test_the_nuke_targets_a_child_but_spares_the_console_line():
    """Checks the target list holds a spawned child and never this process or its ancestors."""
    child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
    try:
        targets = ProcessNuke(WebLogger()).targets()

        assert child.pid in targets
        assert os.getpid() not in targets
        assert os.getppid() not in targets
    finally:
        child.kill()
        child.wait()


@pytest.mark.skipif(shutil.which("renice") is None or shutil.which("ionice") is None, reason="renice and ionice are not installed")
def test_the_throttle_lowers_a_real_child_process():
    """Checks a real run leaves a child at nice 19 in the idle I/O class."""
    child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
    try:
        result = JobThrottle(StubNuke([child.pid]), WebLogger()).apply()
        shown  = subprocess.run(["ionice", "-p", str(child.pid)], capture_output=True, text=True).stdout

        assert result["ok"] is True
        assert _nice_of(child.pid) == 19
        assert shown.strip().startswith("idle")
    finally:
        child.kill()
        child.wait()
