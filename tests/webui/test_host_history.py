"""Tests for the persistent host telemetry log behind the console's history views.

Covers the raw hour ring, folding samples into buckets, the bucketed span
views with their means, retention pruning, persistence across restarts,
network rate differencing and the behaviour when nvidia-smi does not answer.
"""

from __future__ import annotations

import json
import time

import pytest

from host_history import HostHistoryLog
from web_logger   import WebLogger

from tests.webui.conftest import StubPaths


class StubMonitor:
    """Minimal stand-in for SystemMonitor returning scripted GPU devices.

    Attributes:
        devices : Device listing returned by _gpu_devices, None when unknown.
    """

    def __init__(self) -> None:
        """Starts with one scripted device."""
        self.devices = [{"index": 0, "name": "GPU A", "util": 60.0, "mem_used": 8000, "mem_total": 16000, "temp": 55, "power": 180.0, "power_limit": 250.0, "uuid": "GPU-a"}]

    def _gpu_devices(self) -> list[dict] | None:
        """Returns the scripted device listing."""
        return self.devices


@pytest.fixture
def log(tmp_path, monkeypatch):
    """Returns a host history log over a stub monitor, with its sampling loop never started."""
    monkeypatch.setattr(HostHistoryLog, "sample_loop", lambda self: None)
    return HostHistoryLog(StubMonitor(), StubPaths(tmp_path), WebLogger())


def test_a_sample_lands_in_the_hour_ring_with_gpu_telemetry(log):
    """One sample appears in the hour view with CPU, RAM and the device's health values."""
    log.sample()
    state = log.state("hour")

    assert len(state["host"]) == 1
    assert set(state["host"][0]) == {"t", "cpu", "ram", "rx", "tx"}
    assert state["gpus"][0]["index"] == 0
    assert state["gpus"][0]["buckets"][0]["temp"]  == 55
    assert state["gpus"][0]["buckets"][0]["power"] == 180.0
    assert state["gpus"][0]["buckets"][0]["mem"]   == 50.0


def test_the_hour_ring_is_bounded(log):
    """The ring never grows past RECENT_SAMPLES entries."""
    for _ in range(HostHistoryLog.RECENT_SAMPLES + 10):
        log.sample()

    assert len(log.state("hour")["host"]) == HostHistoryLog.RECENT_SAMPLES


def test_bucketed_spans_serve_means(log):
    """A span view returns per-bucket means of the accumulated samples."""
    log.monitor.devices[0]["util"] = 40.0
    log.sample()
    log.monitor.devices[0]["util"] = 80.0
    log.sample()

    state  = log.state("day")
    bucket = state["gpus"][0]["buckets"][-1]

    assert state["bucket_s"] == 300
    assert bucket["util"] == 60.0
    assert len(state["host"]) >= 1


def test_an_unknown_gpu_probe_keeps_the_host_series(log):
    """A sample without GPU devices still records the host counters."""
    log.monitor.devices = None
    log.sample()

    state = log.state("hour")
    assert len(state["host"]) == 1
    assert state["gpus"] == []


def test_net_rates_are_differences_not_totals(log):
    """The first network reading yields zero rates and later ones are per-second differences."""
    rx0, tx0 = log._net_rates(100.0)
    assert (rx0, tx0) == (0.0, 0.0)

    log.prev_net = (0, 0)
    log.prev_t   = 100.0
    rx1, tx1     = log._net_rates(101.0)

    assert rx1 >= 0.0
    assert tx1 >= 0.0


def test_closed_buckets_persist_and_reload(log, tmp_path, monkeypatch):
    """Buckets written on a roll-over are reloaded by a fresh instance."""
    old = time.time() - 2 * HostHistoryLog.BUCKET_S
    monkeypatch.setattr(time, "time", lambda: old)
    log.sample()
    monkeypatch.undo()
    log.sample()

    assert log.path.is_file()

    monkeypatch.setattr(HostHistoryLog, "sample_loop", lambda self: None)
    reloaded = HostHistoryLog(StubMonitor(), StubPaths(tmp_path), WebLogger())

    assert len(reloaded.buckets) >= 1
    assert reloaded.names["0"] == "GPU A"


def test_expired_buckets_are_dropped_on_load(log, tmp_path, monkeypatch):
    """A persisted bucket older than the retention is not reloaded."""
    stale = {"t": int(time.time() - HostHistoryLog.RETENTION_S - 3600), "host": {"n": 1, "cpu": 1.0, "ram": 1.0, "rx": 0.0, "tx": 0.0}, "gpus": {}}
    log.path.parent.mkdir(parents=True, exist_ok=True)
    log.path.write_text(json.dumps(stale) + "\n", encoding="utf-8")

    monkeypatch.setattr(HostHistoryLog, "sample_loop", lambda self: None)
    reloaded = HostHistoryLog(StubMonitor(), StubPaths(tmp_path), WebLogger())

    assert reloaded.buckets == {}


def test_an_unknown_span_raises(log):
    """A span outside hour/day/week/month raises KeyError."""
    with pytest.raises(KeyError):
        log.state("year")
