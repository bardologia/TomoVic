"""Tests for adoption of untracked runs started outside the console.

Covers which live processes qualify as orphans of the repository's main/ tree,
de-duplication against already tracked or already adopted processes, and
stopping an adopted job.
"""
from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

import pytest

SLEEPER = "import time\ntime.sleep(120)\n"
SPAWNER = "import os, subprocess, sys, time\nsubprocess.Popen([sys.executable, os.path.join(os.path.dirname(__file__), 'fake_sleep.py')])\ntime.sleep(120)\n"


@pytest.fixture
def manager(make_manager):
    """Returns a process manager with the orphan age and rescan delays disabled."""
    instance                  = make_manager({})
    instance.ORPHAN_MIN_AGE_S = 0.0
    instance.ORPHAN_RESCAN_S  = 0.0
    return instance


@pytest.fixture
def spawned():
    """Yields a list of Popen handles killed and reaped at teardown."""
    procs = []
    yield procs
    for proc in procs:
        proc.kill()
        proc.wait()


def _spawn(procs: list, script: Path) -> subprocess.Popen:
    """Starts `script` in its own session, records the handle and gives it time to appear in /proc."""
    proc = subprocess.Popen([sys.executable, str(script)], start_new_session=True)
    procs.append(proc)
    time.sleep(0.3)
    return proc


def test_orphan_under_main_is_adopted(manager, spawned, tmp_path):
    """A process running a script under main/ is adopted once as a running job."""
    script = tmp_path / "main" / "analysis" / "fake_sleep.py"
    script.write_text(SLEEPER)
    proc = _spawn(spawned, script)

    assert manager.adopt_orphans() == 1

    record = manager.list_jobs()[0]
    assert record["script"]  == "fake_sleep"
    assert record["pid"]     == proc.pid
    assert record["status"]  == "running"
    assert record["adopted"] is True

    assert manager.adopt_orphans() == 0


def test_process_outside_main_is_ignored(manager, spawned, tmp_path):
    """A process running a script outside main/ is not adopted."""
    script = tmp_path / "loose_sleep.py"
    script.write_text(SLEEPER)
    _spawn(spawned, script)

    assert manager.adopt_orphans() == 0


def test_child_of_matching_process_is_not_adopted_twice(manager, spawned, tmp_path):
    """Only the parent is adopted when a matching process spawns a matching child."""
    (tmp_path / "main" / "analysis" / "fake_sleep.py").write_text(SLEEPER)
    spawner = tmp_path / "main" / "analysis" / "parent_spawn.py"
    spawner.write_text(SPAWNER)
    parent = _spawn(spawned, spawner)
    time.sleep(1.0)

    assert manager.adopt_orphans() == 1
    assert manager.list_jobs()[0]["pid"] == parent.pid

    subprocess.run(["pkill", "-TERM", "-P", str(parent.pid)])


def test_tracked_job_is_not_readopted(manager, spawned, tmp_path):
    """A pid already present in the job table is not adopted again."""
    script = tmp_path / "main" / "analysis" / "fake_sleep.py"
    script.write_text(SLEEPER)
    proc = _spawn(spawned, script)

    with manager.lock:
        manager.jobs["known"] = {"job_id": "known", "status": "running", "pid": proc.pid, "started": "2026-07-14T00:00:00"}

    assert manager.adopt_orphans() == 0


def test_stop_kills_adopted_process(manager, spawned, tmp_path):
    """Stopping an adopted job kills the process and the record turns to finished."""
    script = tmp_path / "main" / "analysis" / "fake_sleep.py"
    script.write_text(SLEEPER)
    proc = _spawn(spawned, script)

    assert manager.adopt_orphans() == 1
    job_id = manager.list_jobs()[0]["job_id"]

    assert manager.stop(job_id)["ok"]
    assert proc.wait(timeout=5) != 0

    deadline = time.monotonic() + 6.0
    while time.monotonic() < deadline:
        if manager.list_jobs()[0]["status"] == "finished":
            break
        time.sleep(0.2)
    assert manager.list_jobs()[0]["status"] == "finished"
