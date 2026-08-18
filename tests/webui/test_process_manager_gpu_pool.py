"""Tests for the process manager's GPU pool plumbing with no pool-aware scripts.

TomoVic registers no fan-out scripts, so POOL_SCRIPTS is empty and no launch
injects a pool file on its own. The pool mechanics stay exercised through an
explicit gpus_file override: set_gpus validation, parking and the error paths
of gpu_pool all still run against tools/orchestration/gpu_queue.py.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from process_manager import ProcessManager

from tests.webui.conftest import SLEEP_LONG, job_record, wait_for_status, wait_until_finished


@pytest.fixture
def manager(make_manager):
    """Returns a process manager whose scripts are long sleeps."""
    return make_manager({name: SLEEP_LONG for name in ("pre_process", "analyze_preprocessing")})


def test_no_script_is_pool_aware():
    """The pool machinery is inert: no script key is registered for pool injection."""
    assert ProcessManager.POOL_SCRIPTS == ()
    assert ProcessManager.POOL_FIELD   == "gpus_file"


def test_launch_injects_no_pool_file(manager):
    """A launched script gets no pool file and reports the pool and progress as unsupported."""
    result = manager.launch("pre_process", sys.executable)
    job_id = result["job_id"]
    record = job_record(manager, job_id)

    assert "gpus_file" not in record["overrides"]
    assert "--gpus_file" not in record["command"]
    assert manager.gpu_pool(job_id)  == {"ok": True, "supported": False, "live": False}
    assert manager.progress(job_id)  == {"ok": True, "supported": False, "live": False}

    manager.stop(job_id)


def test_set_gpus_refuses_a_job_without_a_pool(manager):
    """set_gpus fails for a job that was launched without a live GPU pool."""
    result = manager.launch("pre_process", sys.executable)
    job_id = result["job_id"]

    assert wait_for_status(manager, job_id, "running")

    applied = manager.set_gpus(job_id, [0, 1])

    assert applied["ok"] is False
    assert "was not launched with a live GPU pool" in applied["error"]

    manager.stop(job_id)


def _pooled_job(manager: ProcessManager, tmp_path: Path) -> tuple[str, Path]:
    """Launches a sleeper with an explicit pool file override and waits until it runs."""
    pool   = tmp_path / "pool.json"
    result = manager.launch("analyze_preprocessing", sys.executable, {"gpus_file": str(pool)})
    job_id = result["job_id"]

    assert wait_for_status(manager, job_id, "running")
    return job_id, pool


def test_launch_keeps_an_explicit_pool_file_override(manager, tmp_path):
    """An explicit gpus_file override is kept in the overrides and on the command line."""
    job_id, pool = _pooled_job(manager, tmp_path)
    record       = job_record(manager, job_id)

    assert record["overrides"]["gpus_file"] == str(pool)
    assert "--gpus_file" in record["command"]
    assert manager.gpu_pool(job_id) == {"ok": True, "supported": True, "live": False, "path": str(pool)}

    manager.stop(job_id)


def test_set_gpus_rewrites_a_live_pool_file(manager, tmp_path):
    """set_gpus rewrites an existing pool file and gpu_pool reads it back."""
    job_id, pool = _pooled_job(manager, tmp_path)
    pool.write_text(json.dumps({"gpus": [0]}))

    applied = manager.set_gpus(job_id, [0, 2, 3])

    assert applied == {"ok": True, "gpus": [0, 2, 3], "parked": False}
    assert json.loads(pool.read_text()) == {"gpus": [0, 2, 3]}
    assert manager.gpu_pool(job_id)["gpus"] == [0, 2, 3]

    manager.stop(job_id)


def test_set_gpus_refuses_a_job_that_seeded_no_pool(manager, tmp_path):
    """set_gpus fails while the running job has not written its pool file yet."""
    job_id, _pool = _pooled_job(manager, tmp_path)

    applied = manager.set_gpus(job_id, [0, 1])

    assert applied["ok"] is False
    assert "no live GPU pool" in applied["error"]
    assert manager.gpu_pool(job_id)["live"] is False

    manager.stop(job_id)


def test_set_gpus_parks_only_when_parking_is_confirmed(manager, tmp_path):
    """An empty selection needs park=True, and a later non-empty selection resumes the job."""
    job_id, pool = _pooled_job(manager, tmp_path)
    pool.write_text(json.dumps({"gpus": [0, 1]}))

    refused = manager.set_gpus(job_id, [])

    assert refused["ok"] is False
    assert "confirm parking" in refused["error"]
    assert json.loads(pool.read_text()) == {"gpus": [0, 1]}

    parked = manager.set_gpus(job_id, [], park=True)

    assert parked == {"ok": True, "gpus": [], "parked": True}
    assert json.loads(pool.read_text()) == {"gpus": []}
    assert manager.gpu_pool(job_id)["gpus"] == []

    resumed = manager.set_gpus(job_id, [2])

    assert resumed == {"ok": True, "gpus": [2], "parked": False}
    assert json.loads(pool.read_text()) == {"gpus": [2]}

    manager.stop(job_id)


@pytest.mark.parametrize("gpus, reason", [
    ([0, 0],       "repeat"),
    ([-1],         "non-negative"),
    (["0"],        "non-negative"),
    ("0,1",        "list"),
])
def test_set_gpus_rejects_an_invalid_selection(manager, tmp_path, gpus, reason):
    """An invalid GPU selection is rejected with a reason and leaves the pool file untouched."""
    job_id, pool = _pooled_job(manager, tmp_path)
    pool.write_text(json.dumps({"gpus": [0]}))

    applied = manager.set_gpus(job_id, gpus)

    assert applied["ok"] is False
    assert reason in applied["error"]
    assert json.loads(pool.read_text()) == {"gpus": [0]}

    manager.stop(job_id)


def test_set_gpus_refuses_a_finished_job(manager, tmp_path):
    """set_gpus refuses a job that is no longer running."""
    job_id, _pool = _pooled_job(manager, tmp_path)
    manager.stop(job_id)

    assert wait_until_finished(manager, job_id)

    applied = manager.set_gpus(job_id, [0, 1])

    assert applied["ok"] is False
    assert applied["error"] == "job is not running"


def test_set_gpus_reports_an_unknown_job(manager):
    """set_gpus and gpu_pool both report an unknown job id."""
    assert manager.set_gpus("nope", [0]) == {"ok": False, "error": "unknown job"}
    assert manager.gpu_pool("nope")      == {"ok": False, "error": "unknown job"}
