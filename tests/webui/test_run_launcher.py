"""Tests for the run launcher mediating between the launch form and the console.

Covers interpreter validation and launching versus queueing.
"""
from __future__ import annotations

from run_launcher import RunLauncher
from web_logger   import WebLogger


INTERPRETERS = [
    {"path": "/envs/Dune/bin/python", "name": "Dune"},
    {"path": "/envs/base/bin/python", "name": "base"},
]


class StubPaths:
    """Project paths stand-in serving two fixed interpreters."""

    def discover_interpreters(self) -> list[dict]:
        """Returns the fixed interpreter list."""
        return list(INTERPRETERS)

    def preferred_interpreter(self, interpreters: list[dict], script_key: str = "") -> str:
        """Returns the first interpreter path with the script key appended, marking which script asked."""
        return f"{interpreters[0]['path']}::{script_key}"


class StubResolver:
    """Script config resolver stand-in serving fixed leaves.

    Attributes:
        leaves: Mapping of dotted leaf path to resolved value.
        ok: Whether resolution succeeds.
        calls: (script key, interpreter) pairs seen by resolve.
    """

    def __init__(self, leaves: dict | None = None, ok: bool = True) -> None:
        """Stores the leaves to serve and whether resolution should succeed."""
        self.leaves = leaves or {}
        self.ok     = ok
        self.calls  = []

    def resolve(self, key: str, interpreter: str) -> dict:
        """Records the call and returns either the resolved leaves or a failure payload."""
        self.calls.append((key, interpreter))
        if not self.ok:
            return {"ok": False, "error": "config import failed"}
        return {"ok": True, "leaves": [{"path": path, "value": value} for path, value in self.leaves.items()]}


class StubProcesses:
    """Process manager stand-in recording launch and enqueue calls.

    Attributes:
        launched: Argument tuples passed to launch.
        queued: Argument tuples passed to enqueue.
        ok: Whether the calls report success.
    """

    def __init__(self, ok: bool = True) -> None:
        """Starts with empty launch and queue logs."""
        self.launched = []
        self.queued   = []
        self.ok       = ok

    def launch(self, key, interpreter, overrides, follow_up, detach) -> dict:
        """Records the launch arguments and returns a job id."""
        self.launched.append((key, interpreter, overrides, follow_up, detach))
        return {"ok": self.ok, "job_id": "job-1"}

    def enqueue(self, key, interpreter, overrides, follow_up, detach) -> dict:
        """Records the enqueue arguments and reports the job as queued."""
        self.queued.append((key, interpreter, overrides, follow_up, detach))
        return {"ok": self.ok, "queued": True}


def _launcher(resolver: StubResolver | None = None, processes: StubProcesses | None = None) -> RunLauncher:
    """Returns a RunLauncher wired to the stub paths, resolver and processes."""
    return RunLauncher(StubPaths(), WebLogger(), resolver or StubResolver(), processes or StubProcesses())


def test_the_preferred_interpreter_is_chosen_per_script():
    """The preferred interpreter is asked for per script key."""
    assert _launcher().preferred_interpreter("pre_process") == "/envs/Dune/bin/python::pre_process"


def test_only_a_discovered_interpreter_is_accepted():
    """A discovered interpreter is accepted and any other path is rejected by name."""
    launcher = _launcher()

    assert launcher.interpreter_error("/envs/base/bin/python") == ""
    assert "unknown interpreter '/usr/bin/python3'" in launcher.interpreter_error("/usr/bin/python3")


def test_an_unknown_interpreter_is_refused_before_anything_is_started():
    """An unknown interpreter is refused before any job is launched or queued."""
    processes = StubProcesses()
    result    = _launcher(processes=processes).execute("pre_process", "/usr/bin/python3", {}, None, False, False)

    assert result["ok"] is False
    assert processes.launched == []
    assert processes.queued   == []


def test_execute_launches_and_forwards_every_argument():
    """execute forwards script key, interpreter, overrides, follow-up and detach flag to launch."""
    processes = StubProcesses()
    launcher  = _launcher(StubResolver(), processes)

    result = launcher.execute("pre_process", "/envs/Dune/bin/python", {"entry.win_list": "[3]"}, "analyze_preprocessing", True, False)

    assert result["job_id"] == "job-1"
    assert processes.queued == []
    assert processes.launched == [("pre_process", "/envs/Dune/bin/python", {"entry.win_list": "[3]"}, "analyze_preprocessing", True)]


def test_execute_queues_instead_of_launching_when_asked():
    """execute with queueing requested calls enqueue instead of launch."""
    processes = StubProcesses()
    launcher  = _launcher(StubResolver(), processes)

    result = launcher.execute("pre_process", "/envs/Dune/bin/python", {}, None, False, True)

    assert result["queued"] is True
    assert processes.launched == []
    assert processes.queued   == [("pre_process", "/envs/Dune/bin/python", {}, None, False)]
