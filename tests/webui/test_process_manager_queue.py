"""Tests for the console launch queue, history pruning and stream fan-out.

Covers serialised execution of queued jobs, cancellation and stop_all, follow-up
chaining, notifier callbacks, the blocker reported on the queued event, and the
JobStream drop marker for slow viewers.
"""
from __future__ import annotations

import sys

import pytest

from process_manager import JobStream

from tests.webui.conftest import ARGS_DUMP, SLEEP_LONG, job_record, wait_for_status

SLEEP_OK   = "import time\ntime.sleep(0.6)\n"
SLEEP_FAIL = "import sys, time\ntime.sleep(0.6)\nsys.exit(3)\n"
WRITER     = "import pathlib, sys\npathlib.Path('order.txt').open('a').write(pathlib.Path(__file__).stem + '\\n')\n"


@pytest.fixture
def manager(make_manager):
    """Returns a process manager with short-lived, failing, long and argv-dumping fake scripts."""
    return make_manager({
        "sleep_ok"   : SLEEP_OK,
        "sleep_fail" : SLEEP_FAIL,
        "sleep_long" : SLEEP_LONG,
        "writer_a"   : WRITER,
        "writer_b"   : WRITER,
        "args_dump"  : ARGS_DUMP,
    })


def test_enqueue_idle_starts_immediately(manager):
    """Enqueueing on an idle console starts the job at once instead of queueing it."""
    result = manager.enqueue("sleep_ok", sys.executable)

    assert result["ok"]
    assert result["queued"] is False
    assert wait_for_status(manager, result["job_id"], "finished")


def test_enqueue_waits_for_running_job(manager):
    """A job enqueued while another runs waits, then runs after the predecessor finishes."""
    running = manager.launch("sleep_ok", sys.executable)
    queued  = manager.enqueue("sleep_ok", sys.executable)

    assert queued["ok"]
    assert queued["queued"] is True
    assert job_record(manager, queued["job_id"])["status"] == "queued"

    assert wait_for_status(manager, queued["job_id"], "finished")
    assert job_record(manager, running["job_id"])["status"] == "finished"


def test_queued_job_starts_after_predecessor_fails(manager):
    """A queued job starts even when its predecessor exits non-zero."""
    failing = manager.launch("sleep_fail", sys.executable)
    queued  = manager.enqueue("sleep_ok", sys.executable)

    assert wait_for_status(manager, queued["job_id"], "finished")
    assert job_record(manager, failing["job_id"])["status"] == "failed"


def test_queued_jobs_run_in_order(manager, tmp_path):
    """Two queued jobs execute in enqueue order."""
    manager.launch("sleep_ok", sys.executable)
    first  = manager.enqueue("writer_a", sys.executable)
    second = manager.enqueue("writer_b", sys.executable)

    assert wait_for_status(manager, first["job_id"], "finished")
    assert wait_for_status(manager, second["job_id"], "finished")
    assert (tmp_path / "order.txt").read_text().splitlines() == ["writer_a", "writer_b"]


def test_queued_launch_keeps_overrides(manager, tmp_path):
    """Overrides given at enqueue time reach the command line when the job finally starts."""
    manager.launch("sleep_ok", sys.executable)
    queued = manager.enqueue("args_dump", sys.executable, {"training.seed": "7"})

    assert wait_for_status(manager, queued["job_id"], "finished")
    assert (tmp_path / "argv.txt").read_text() == "--training.seed 7"


def test_cancelled_queued_job_is_skipped(manager, tmp_path):
    """Stopping a queued job marks it cancelled and skips it without blocking the rest."""
    manager.launch("sleep_ok", sys.executable)
    first  = manager.enqueue("writer_a", sys.executable)
    second = manager.enqueue("writer_b", sys.executable)

    assert manager.stop(first["job_id"])["ok"]
    assert job_record(manager, first["job_id"])["status"] == "cancelled"

    assert wait_for_status(manager, second["job_id"], "finished")
    assert job_record(manager, first["job_id"])["status"] == "cancelled"
    assert (tmp_path / "order.txt").read_text().splitlines() == ["writer_b"]


def test_stop_all_purges_queue(manager):
    """stop_all kills the running job and cancels the queued one without a pid."""
    running = manager.launch("sleep_long", sys.executable)
    queued  = manager.enqueue("sleep_ok", sys.executable)

    assert manager.stop_all() == 1
    assert job_record(manager, queued["job_id"])["status"] == "cancelled"
    assert job_record(manager, queued["job_id"])["pid"] is None

    assert wait_for_status(manager, running["job_id"], "failed")
    assert job_record(manager, queued["job_id"])["status"] == "cancelled"


def test_stop_all_finishes_when_the_history_drops_a_job_mid_stop(manager, monkeypatch):
    """stop_all terminates cleanly when the job record disappears from history mid-stop."""
    running = manager.launch("sleep_long", sys.executable)
    job_id  = running["job_id"]
    signals = manager._signal_group

    def signal_then_prune(pid, sig):
        """Drops the job record from history, then forwards the signal to the real handler."""
        with manager.lock:
            manager.jobs.pop(job_id, None)
        signals(pid, sig)

    monkeypatch.setattr(manager, "_signal_group", signal_then_prune)

    assert manager.stop_all(grace=1.0) == 1
    assert manager._still_running([{"job_id": job_id}]) == []


def test_queue_respects_follow_up_chain(manager, tmp_path):
    """A follow-up job runs after its parent and before the next queue entry finishes the chain."""
    manager.launch("sleep_ok", sys.executable)
    parent = manager.enqueue("writer_a", sys.executable, follow_up="args_dump")
    last   = manager.enqueue("writer_b", sys.executable)

    assert wait_for_status(manager, last["job_id"], "finished")

    follow_id = job_record(manager, parent["job_id"])["follow_up"]
    assert follow_id is not None
    assert job_record(manager, follow_id)["status"] == "finished"

    order = (tmp_path / "order.txt").read_text().splitlines()
    assert order == ["writer_a", "writer_b"]
    assert (tmp_path / "argv.txt").exists()


def test_enqueue_rejects_missing_script(manager):
    """Enqueueing an unknown script name is rejected."""
    result = manager.enqueue("missing", sys.executable)
    assert result == {"ok": False, "error": "script not found"}


def test_notifications_fire_on_start_and_finish_for_direct_and_queued(manager):
    """Start and finish notifications fire in order for both directly launched and queued jobs."""
    events = []
    manager.notifier.job_started  = lambda record: events.append(("started", record["script"]))
    manager.notifier.job_finished = lambda record: events.append(("finished", record["script"]))

    manager.launch("sleep_ok", sys.executable)
    queued = manager.enqueue("writer_a", sys.executable)

    assert wait_for_status(manager, queued["job_id"], "finished")
    assert events == [("started", "sleep_ok"), ("finished", "sleep_ok"), ("started", "writer_a"), ("finished", "writer_a")]


def test_the_console_history_drops_the_oldest_ended_jobs(manager):
    """Pruning keeps the running job and the newest ended jobs up to HISTORY_LIMIT."""
    manager.HISTORY_LIMIT = 2

    live = manager.launch("sleep_long", sys.executable)["job_id"]

    with manager.lock:
        for index in range(4):
            job_id                  = f"job{index}"
            manager.jobs[job_id]    = {"job_id": job_id, "status": "finished", "started": f"2026-07-14T00:0{index + 1}:00"}
            manager.streams[job_id] = JobStream(manager.logger)

    manager._prune_history()

    with manager.lock:
        assert set(manager.jobs)    == {"job2", "job3", live}
        assert set(manager.streams) == {"job2", "job3", live}


def test_a_viewer_that_falls_behind_is_truncated_with_a_marker(manager, monkeypatch):
    """A subscriber over the queue limit gets a truncation marker and still receives the end event."""
    monkeypatch.setattr(JobStream, "QUEUE_LIMIT", 4)
    stream = JobStream(manager.logger)
    sub    = stream.subscribe()

    for index in range(4):
        stream.publish({"type": "chunk", "data": f"line {index}"})

    stream.publish({"type": "end"})

    drained = []
    while not sub.empty():
        drained.append(sub.get_nowait())

    assert stream.dropped == 4
    assert "stream truncated: 4 event(s) dropped" in drained[0]["data"]
    assert drained[-1] == {"type": "end"}


def test_the_queued_event_names_the_job_holding_the_queue(manager):
    """The queued event names the running job that blocks the queue."""
    running = manager.launch("sleep_long", sys.executable)
    queued  = manager.enqueue("sleep_ok", sys.executable)

    events  = list(manager.streams[queued["job_id"]].buffer)
    blocker = next(event["blocker"] for event in events if event.get("status") == "queued")

    assert blocker["job_id"] == running["job_id"]
    assert blocker["script"] == "sleep_long"
    assert blocker["adopted"] is False

    manager.stop(running["job_id"])
    assert wait_for_status(manager, queued["job_id"], "finished")


def test_an_adopted_process_is_named_as_the_queue_blocker(manager):
    """An adopted process is reported as the queue blocker with its script and pid."""
    manager.jobs["adopted1"] = {"job_id": "adopted1", "script": "train_backbone", "status": "running", "pid": 4242, "adopted": True}

    queued  = manager.enqueue("sleep_ok", sys.executable)
    events  = list(manager.streams[queued["job_id"]].buffer)
    blocker = next(event["blocker"] for event in events if event.get("status") == "queued")

    assert queued["queued"]   is True
    assert blocker["adopted"] is True
    assert blocker["script"]  == "train_backbone"
    assert blocker["pid"]     == 4242
