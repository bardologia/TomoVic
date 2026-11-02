"""Tests for the persistent GPU activity log behind the console's activity card.

Covers folding samples into time buckets, separating own work from other users' work,
dropping buckets that fall out of the retention, the day, week and month span views,
persistence across restarts and the behaviour when nvidia-smi does not answer.
"""

from __future__ import annotations

import json
import time

import pytest

from gpu_activity import GpuActivityLog
from web_logger   import WebLogger

from tests.webui.conftest import StubPaths


def occupancy(util_a: float, owner_a: str | None, util_b: float = 0.0) -> list[dict]:
    """Returns a two-device occupancy listing, the first device held by one owner."""
    procs = [{"pid": 10, "mem": 512.0, "owner": owner_a, "cmd": "train"}] if owner_a is not None else []
    return [
        {"index": 0, "name": "GPU A", "util": util_a, "mem_used": 8000, "mem_total": 16000, "uuid": "GPU-a", "procs": procs},
        {"index": 1, "name": "GPU B", "util": util_b, "mem_used": 0,    "mem_total": 16000, "uuid": "GPU-b", "procs": []},
    ]


class StubMonitor:
    """Minimal stand-in for SystemMonitor returning a scripted GPU occupancy.

    Attributes:
        user    : Login name the log treats as the console owner.
        reading : Occupancy listing returned by gpu_occupancy, None when unknown.
    """

    def __init__(self, user: str = "me") -> None:
        """Stores the console user and starts with an empty occupancy."""
        self.user    = user
        self.reading = []

    def gpu_occupancy(self) -> list[dict] | None:
        """Returns the scripted occupancy listing."""
        return self.reading


@pytest.fixture
def log(tmp_path, monkeypatch):
    """Returns an activity log over a stub monitor, with its sampling loop never started."""
    monkeypatch.setattr(GpuActivityLog, "sample_loop", lambda self: None)
    return GpuActivityLog(StubMonitor(), StubPaths(tmp_path), WebLogger())


def test_a_busy_sample_is_attributed_to_this_user(log):
    """A device held by the console user records own work at full share."""
    log.monitor.reading = occupancy(80.0, "me")
    log.sample()

    gpus = {gpu["index"]: gpu for gpu in log.state()["gpus"]}
    bucket = gpus[0]["buckets"][-1]

    assert bucket["busy"]    == 1.0
    assert bucket["mine"]    == 1.0
    assert bucket["others"]  == 0.0
    assert bucket["util"]    == 80.0
    assert bucket["holders"] == ["me"]


def test_work_by_another_user_is_kept_apart(log):
    """A device held by a different login records other work, not own work."""
    log.monitor.reading = occupancy(60.0, "neighbour")
    log.sample()

    gpus = {gpu["index"]: gpu for gpu in log.state()["gpus"]}
    bucket = gpus[0]["buckets"][-1]

    assert bucket["mine"]    == 0.0
    assert bucket["others"]  == 1.0
    assert bucket["holders"] == ["neighbour"]


def test_an_idle_device_records_an_idle_bucket(log):
    """A device with no processes and utilisation below the threshold is not busy."""
    log.monitor.reading = occupancy(80.0, "me", util_b=1.0)
    log.sample()

    gpus = {gpu["index"]: gpu for gpu in log.state()["gpus"]}
    bucket = gpus[1]["buckets"][-1]

    assert bucket["busy"]    == 0.0
    assert bucket["holders"] == []


def test_samples_within_one_bucket_average(log):
    """Two samples in the same bucket, one busy and one idle, average to a half share."""
    log.monitor.reading = occupancy(80.0, "me")
    log.sample()
    log.monitor.reading = occupancy(0.0, None)
    log.sample()

    gpus = {gpu["index"]: gpu for gpu in log.state()["gpus"]}
    assert len(gpus[0]["buckets"]) == 1
    assert gpus[0]["buckets"][0]["busy"] == 0.5
    assert gpus[0]["buckets"][0]["util"] == 40.0


def test_buckets_older_than_the_retention_are_dropped(log):
    """A bucket seeded a month and a half back is pruned by the next sample."""
    stale = int((log.state()["now"] - 1.5 * GpuActivityLog.RETENTION_S) // GpuActivityLog.BUCKET_S) * GpuActivityLog.BUCKET_S
    log.buckets[stale] = {"gpus": {"0": {"name": "GPU A", "n": 1, "busy": 1, "mine": 1, "others": 0, "util": 90.0, "holders": ["me"]}}}

    log.monitor.reading = occupancy(80.0, "me")
    log.sample()

    assert stale not in log.buckets


def test_week_span_merges_raw_buckets_into_hour_slots(log):
    """Two raw buckets inside the same hour merge into one hour-wide display bucket."""
    now  = int(time.time())
    slot = int(now // 3600) * 3600
    log.buckets[slot]       = {"gpus": {"0": {"name": "GPU A", "n": 1, "busy": 1, "mine": 1, "others": 0, "util": 80.0, "holders": ["me"]}}}
    log.buckets[slot + 300] = {"gpus": {"0": {"name": "GPU A", "n": 1, "busy": 0, "mine": 0, "others": 0, "util": 0.0,  "holders": []}}}
    log.names["0"] = "GPU A"

    state  = log.state("week")
    bucket = state["gpus"][0]["buckets"][-1]

    assert state["bucket_s"] == 3600
    assert state["window_s"] == 7 * 86400
    assert bucket["t"]       == slot
    assert bucket["busy"]    == 0.5
    assert bucket["util"]    == 40.0
    assert bucket["holders"] == ["me"]


def test_day_span_hides_what_the_month_span_keeps(log):
    """A bucket from three days ago is absent from the day view but present in the month view."""
    old = int((time.time() - 3 * 86400) // GpuActivityLog.BUCKET_S) * GpuActivityLog.BUCKET_S
    log.buckets[old] = {"gpus": {"0": {"name": "GPU A", "n": 1, "busy": 1, "mine": 1, "others": 0, "util": 90.0, "holders": ["me"]}}}
    log.names["0"] = "GPU A"

    assert log.state("day")["gpus"] == [] or all(b["t"] != old for b in log.state("day")["gpus"][0]["buckets"])
    assert any(b["t"] == int(old // (4 * 3600)) * (4 * 3600) for b in log.state("month")["gpus"][0]["buckets"])


def test_an_unknown_span_breaks_loudly(log):
    """A span outside SPANS raises instead of silently falling back to a default."""
    with pytest.raises(KeyError):
        log.state("year")


def test_closed_buckets_survive_a_restart(log, tmp_path, monkeypatch):
    """A bucket persisted when the next one opens is read back by a fresh log."""
    log.monitor.reading = occupancy(80.0, "me")
    log.sample()
    log.open_at -= GpuActivityLog.BUCKET_S
    log.sample()

    reloaded = GpuActivityLog(StubMonitor(), StubPaths(tmp_path), WebLogger())
    records  = [json.loads(line) for line in log.path.read_text(encoding="utf-8").splitlines()]

    assert records
    assert {gpu["index"] for gpu in reloaded.state()["gpus"]} == {0, 1}


def test_an_interrupted_rewrite_leaves_the_previous_file_intact(log, monkeypatch):
    """A write that dies mid-file never truncates the persisted log, thanks to the staging rename."""
    log.monitor.reading = occupancy(80.0, "me")
    log.sample()
    log._persist()
    before = log.path.read_text(encoding="utf-8")

    def broken(path, text, encoding=None):
        path.write_bytes(text[: len(text) // 2].encode())
        raise OSError("disk full")

    log.monitor.reading = occupancy(20.0, "me")
    log.sample()

    with monkeypatch.context() as patched:
        patched.setattr(type(log.path), "write_text", broken)
        with pytest.raises(OSError):
            log._persist()

    assert log.path.read_text(encoding="utf-8") == before

    reloaded = GpuActivityLog(StubMonitor(), StubPaths(log.path.parent.parent), WebLogger())
    assert {gpu["index"] for gpu in reloaded.state()["gpus"]} == {0, 1}


def test_an_unreadable_probe_records_nothing(log):
    """A None occupancy leaves the buckets untouched instead of writing zeros."""
    log.monitor.reading = None
    log.sample()

    assert log.state()["gpus"] == []
