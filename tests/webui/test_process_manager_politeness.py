"""Tests for the politeness prefix on local launches.

Covers the rendered command line of a job record and the real nice value of a
launched child at each level, read once the pid the manager records has exec'd
through nice and ionice into the interpreter.
"""

from __future__ import annotations

import os
import sys
import time

import pytest


SLEEPER = "import time\ntime.sleep(20)\n"


def _nice_of(pid: int) -> int:
    """Returns a process's nice value from /proc/<pid>/stat."""
    raw = open(f"/proc/{pid}/stat").read()
    return int(raw[raw.rindex(")") + 2:].split()[16])


def _comm_of(pid: int) -> str:
    """Returns a process's command name from /proc/<pid>/stat."""
    raw = open(f"/proc/{pid}/stat").read()
    return raw[raw.index("(") + 1:raw.rindex(")")]


def _launched(manager, level: str | None = None) -> dict:
    """Launches the sleeper, at the given level when one is named, and returns its job record.

    Args:
        manager : Process manager under test.
        level   : Politeness level to set before the launch, or None to keep the current one.

    Returns:
        The job record, which carries the interpreter's pid once `launch` returns.
    """
    if level is not None:
        manager.politeness.configure({"level": level})

    job = manager.launch("sleeper", sys.executable)
    assert job["ok"] is True, job

    with manager.lock:
        record = dict(manager.jobs[job["job_id"]])
    assert record["pid"], record
    _wait_for_interpreter(record["pid"])
    return record


def _wait_for_interpreter(pid: int, timeout: float = 5.0) -> None:
    """Polls until the pid has exec'd through nice and ionice into the interpreter.

    Args:
        pid     : Pid the manager recorded.
        timeout : Seconds to wait before failing.
    """
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if _comm_of(pid).startswith("python"):
            return
        time.sleep(0.02)
    raise AssertionError(f"pid {pid} is still {_comm_of(pid)!r} after {timeout} s")


@pytest.fixture
def manager(make_manager):
    """Returns a manager over one sleeping script."""
    return make_manager({"sleeper": SLEEPER})


def test_the_rendered_command_carries_the_prefix(manager):
    """Checks the job record's command line starts with the level's nice and ionice words."""
    record = manager._make_record("sleeper", sys.executable, {"a": "1"})

    assert record["command"].startswith("nice -n 10 ionice -c 2 -n 7 ")
    assert record["command"].endswith(f"{sys.executable} -u main/analysis/sleeper.py --a 1")


def test_the_rendered_command_has_no_prefix_when_off(manager):
    """Checks the off level leaves the command line bare."""
    manager.politeness.configure({"level": "off"})
    record = manager._make_record("sleeper", sys.executable, {})

    assert record["command"] == f"{sys.executable} -u main/analysis/sleeper.py"


@pytest.mark.parametrize("level, nice", [("polite", 10), ("background", 19)])
def test_a_launched_child_runs_at_the_levels_nice_value(manager, level, nice):
    """Checks the spawned interpreter really carries the nice value and is the pid the manager records."""
    record = _launched(manager, level)

    assert _nice_of(record["pid"]) == nice
    assert _comm_of(record["pid"]).startswith("python")


def test_a_launched_child_inherits_the_console_nice_when_off(manager):
    """Checks the off level spawns the interpreter at this process's own nice value."""
    record = _launched(manager, "off")

    assert _nice_of(record["pid"]) == _nice_of(os.getpid())


def test_changing_the_level_affects_only_later_launches(manager):
    """Checks a running job keeps its priority when the level changes after its start."""
    first  = _launched(manager)
    second = _launched(manager, "background")

    assert _nice_of(first["pid"])  == 10
    assert _nice_of(second["pid"]) == 19
