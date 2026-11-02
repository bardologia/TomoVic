"""Tests for the CPU and RAM watchdog guarding the shared machine.

Covers the sustain and clear-margin logic of alerts, the RAM kill switch with
its sustain, cooldown and memory-attribution guard, CPU percentage from
counter deltas, and the bounded event log.
"""
from __future__ import annotations

import time

import pytest

from proc_stats        import CpuCounters
from resource_watchdog import ResourceWatchdog
from web_logger        import WebLogger

from tests.webui.conftest import StubNotifier, StubPaths


class StubProcesses:
    """Process manager stand-in counting stop_all calls.

    Attributes:
        running : Number of jobs the next stop_all reports as terminated.
        calls   : How many times stop_all has been called.
    """

    def __init__(self, running: int = 2) -> None:
        """Starts with `running` jobs and no recorded calls."""
        self.running = running
        self.calls   = 0

    def stop_all(self) -> int:
        """Records the call and returns the number of jobs terminated."""
        self.calls  += 1
        stopped      = self.running
        self.running = 0
        return stopped


class StubContention:
    """Memory contention stand-in serving a fixed attribution share.

    Attributes:
        share : Fraction of used memory attributed to this user, or None when no sample is available.
    """

    def __init__(self, share: float | None = 0.9) -> None:
        """Stores the attribution share served to the watchdog."""
        self.share = share

    def mine_memory_share(self) -> float | None:
        """Returns the configured share of memory attributed to this user."""
        return self.share


@pytest.fixture
def watchdog(tmp_path):
    """Returns a watchdog wired to stub processes reporting two running jobs and a 0.9 memory share."""
    return ResourceWatchdog(StubProcesses(), StubContention(), WebLogger(), StubNotifier(), StubPaths(tmp_path))


def _alert(watchdog: ResourceWatchdog, kind: str) -> dict | None:
    """Returns the active alert of the given kind, or None when it is not raised."""
    return next((entry for entry in watchdog.state()["active"] if entry["kind"] == kind), None)


def _breach(watchdog: ResourceWatchdog, kind: str, times: int, level: str = "warn") -> None:
    """Feeds `times` consecutive breaching samples of the given kind and level."""
    for _ in range(times):
        watchdog._track(kind, level, True, False, f"{kind} is over the line")


def test_an_alert_needs_a_sustained_breach(watchdog):
    """An alert is raised only once the breach has lasted the configured sustain."""
    _breach(watchdog, "cpu", ResourceWatchdog.SUSTAIN["cpu"] - 1)
    assert _alert(watchdog, "cpu") is None

    _breach(watchdog, "cpu", 1)
    assert _alert(watchdog, "cpu")["message"] == "cpu is over the line"


def test_a_single_calm_sample_resets_the_streak(watchdog):
    """One non-breaching sample resets the streak, so the alert never fires."""
    _breach(watchdog, "cpu", ResourceWatchdog.SUSTAIN["cpu"] - 1)
    watchdog._track("cpu", "warn", False, False, "calm")
    _breach(watchdog, "cpu", ResourceWatchdog.SUSTAIN["cpu"] - 1)

    assert _alert(watchdog, "cpu") is None


def test_an_active_alert_is_updated_in_place(watchdog):
    """A raised alert has its level and message updated while keeping its original timestamp."""
    _breach(watchdog, "ram", ResourceWatchdog.SUSTAIN["ram"])
    since = _alert(watchdog, "ram")["since"]

    watchdog._track("ram", "danger", True, False, "ram is critical")
    updated = _alert(watchdog, "ram")

    assert len(watchdog.state()["active"]) == 1
    assert updated["level"]   == "danger"
    assert updated["message"] == "ram is critical"
    assert updated["since"]   == since


def test_an_alert_survives_until_the_clear_margin_is_crossed(watchdog):
    """An alert clears only when the sample falls below the clear margin."""
    _breach(watchdog, "ram", ResourceWatchdog.SUSTAIN["ram"])

    watchdog._track("ram", "warn", False, False, "still elevated")
    assert _alert(watchdog, "ram") is not None

    watchdog._track("ram", "warn", False, True, "back to normal")
    assert _alert(watchdog, "ram") is None


def test_the_ram_kill_needs_the_sustain_before_it_fires(watchdog):
    """The RAM kill fires only after the breach has lasted the ram_kill sustain."""
    watchdog._check_kill(ResourceWatchdog.RAM_KILL + 1.0)

    assert watchdog.processes.calls == 0
    assert watchdog.state()["events"] == []

    watchdog._check_kill(ResourceWatchdog.RAM_KILL + 1.0)
    events = watchdog.state()["events"]

    assert watchdog.processes.calls == 1
    assert len(events)       == 1
    assert events[0]["kind"] == "ram_kill"
    assert "terminated 2 running job(s)" in events[0]["message"]


def test_ram_dropping_below_the_kill_line_resets_the_streak(watchdog):
    """A sample below the kill line resets the kill streak."""
    watchdog._check_kill(ResourceWatchdog.RAM_KILL + 1.0)
    watchdog._check_kill(ResourceWatchdog.RAM_KILL - 10.0)
    watchdog._check_kill(ResourceWatchdog.RAM_KILL + 1.0)

    assert watchdog.processes.calls == 0


def test_a_second_kill_waits_for_the_cooldown(watchdog):
    """A second kill fires only after the cooldown has elapsed."""
    for _ in range(ResourceWatchdog.SUSTAIN["ram_kill"] + 4):
        watchdog._check_kill(ResourceWatchdog.RAM_KILL + 1.0)

    assert watchdog.processes.calls == 1

    watchdog.last_kill = time.monotonic() - ResourceWatchdog.KILL_COOLDOWN - 1.0
    watchdog._check_kill(ResourceWatchdog.RAM_KILL + 1.0)

    assert watchdog.processes.calls == 2


def test_a_kill_with_nothing_running_still_records_the_event(watchdog):
    """A kill with no running jobs still records an event saying so."""
    watchdog.processes.running = 0

    for _ in range(ResourceWatchdog.SUSTAIN["ram_kill"]):
        watchdog._check_kill(ResourceWatchdog.RAM_KILL + 1.0)

    assert "no console jobs were running" in watchdog.state()["events"][0]["message"]


def test_a_neighbours_ram_never_kills_this_users_jobs(watchdog):
    """Memory owned mostly by other users raises a foreign-memory alert instead of killing."""
    watchdog.contention.share = ResourceWatchdog.MINE_SHARE - 0.2

    for _ in range(ResourceWatchdog.SUSTAIN["ram_kill"] + 3):
        watchdog._check_kill(ResourceWatchdog.RAM_KILL + 5.0)

    assert watchdog.processes.calls == 0
    assert watchdog.state()["events"] == []
    assert "attributed to this user" in _alert(watchdog, "ram_foreign")["message"]


def test_the_kill_fires_once_this_user_owns_the_memory(watchdog):
    """The kill fires and the foreign-memory alert clears once this user owns the memory."""
    watchdog.contention.share = ResourceWatchdog.MINE_SHARE - 0.2
    for _ in range(ResourceWatchdog.SUSTAIN["ram_kill"]):
        watchdog._check_kill(ResourceWatchdog.RAM_KILL + 5.0)

    watchdog.contention.share = ResourceWatchdog.MINE_SHARE + 0.1
    watchdog._check_kill(ResourceWatchdog.RAM_KILL + 5.0)

    assert watchdog.processes.calls == 1
    assert _alert(watchdog, "ram_foreign") is None
    assert "attributed to this user" in watchdog.state()["events"][0]["message"]


def test_an_unsampled_attribution_holds_the_kill_back(watchdog):
    """A missing attribution sample holds the kill back and is reported in the alert."""
    watchdog.contention.share = None

    for _ in range(ResourceWatchdog.SUSTAIN["ram_kill"] + 1):
        watchdog._check_kill(ResourceWatchdog.RAM_KILL + 5.0)

    assert watchdog.processes.calls == 0
    assert "no attribution sample" in _alert(watchdog, "ram_foreign")["message"]


def test_calm_ram_clears_the_foreign_memory_alert(watchdog):
    """RAM falling below the kill line clears the foreign-memory alert."""
    watchdog.contention.share = ResourceWatchdog.MINE_SHARE - 0.2
    for _ in range(ResourceWatchdog.SUSTAIN["ram_kill"]):
        watchdog._check_kill(ResourceWatchdog.RAM_KILL + 5.0)

    watchdog._check_kill(ResourceWatchdog.RAM_KILL - 10.0)

    assert _alert(watchdog, "ram_foreign") is None


def test_cpu_percent_is_a_delta_between_two_samples(watchdog, monkeypatch):
    """CPU percentage is None on the first sample and the busy/total delta afterwards."""
    samples = [{"cpu": (100, 200)}, {"cpu": (150, 300)}]
    monkeypatch.setattr(CpuCounters, "read", staticmethod(lambda: samples.pop(0)))

    assert watchdog._cpu_percent() is None
    assert watchdog._cpu_percent() == pytest.approx(50.0)


def test_cpu_percent_ignores_a_stalled_counter(watchdog, monkeypatch):
    """Identical counters between samples yield no CPU percentage."""
    monkeypatch.setattr(CpuCounters, "read", staticmethod(lambda: {"cpu": (100, 200)}))

    assert watchdog._cpu_percent() is None
    assert watchdog._cpu_percent() is None


def test_evaluate_escalates_the_ram_alert_and_kills(watchdog, monkeypatch):
    """A sustained RAM breach warns, then escalates to danger and triggers the kill."""
    monkeypatch.setattr(ResourceWatchdog, "_cpu_percent", lambda self: 10.0)
    monkeypatch.setattr(ResourceWatchdog, "_ram_percent", lambda self: ResourceWatchdog.RAM_WARN + 1.0)

    for _ in range(ResourceWatchdog.SUSTAIN["ram"]):
        watchdog._evaluate()

    assert _alert(watchdog, "ram")["level"] == "warn"
    assert _alert(watchdog, "cpu") is None
    assert watchdog.processes.calls == 0

    monkeypatch.setattr(ResourceWatchdog, "_ram_percent", lambda self: ResourceWatchdog.RAM_KILL + 1.0)
    for _ in range(ResourceWatchdog.SUSTAIN["ram_kill"]):
        watchdog._evaluate()

    assert _alert(watchdog, "ram")["level"] == "danger"
    assert watchdog.processes.calls == 1


def test_state_reports_the_limits_it_enforces(watchdog):
    """State reports the watchdog as unarmed and echoes the thresholds it enforces."""
    limits = watchdog.state()["limits"]

    assert watchdog.state()["armed"] is False
    assert limits["ram_kill"]  == ResourceWatchdog.RAM_KILL
    assert limits["ram_warn"]  == ResourceWatchdog.RAM_WARN
    assert limits["cpu_alert"]  == ResourceWatchdog.CPU_ALERT
    assert limits["cooldown"]   == ResourceWatchdog.KILL_COOLDOWN
    assert limits["mine_share"] == ResourceWatchdog.MINE_SHARE


def test_the_event_log_is_bounded(watchdog):
    """The event log keeps only the most recent 20 entries."""
    for _ in range(60):
        watchdog.last_kill = 0.0
        watchdog.streaks["ram_kill"] = ResourceWatchdog.SUSTAIN["ram_kill"] - 1
        watchdog._check_kill(ResourceWatchdog.RAM_KILL + 1.0)

    assert len(watchdog.state()["events"]) == 20


def test_a_raised_alert_is_pushed_once_through_the_notifier(watchdog):
    """A newly raised alert pushes one notification and a refresh stays silent."""
    _breach(watchdog, "cpu", ResourceWatchdog.SUSTAIN["cpu"] + 2)
    alerts = watchdog.notifier.alerts

    assert len(alerts) == 1
    assert alerts[0][0] == "host alert: cpu"
    assert alerts[0][2] == "default"


def test_a_danger_alert_is_pushed_at_high_priority(watchdog):
    """An alert raised at danger level is pushed with high priority."""
    _breach(watchdog, "ram", ResourceWatchdog.SUSTAIN["ram"], level="danger")

    assert watchdog.notifier.alerts[0][2] == "high"


def test_the_ram_kill_pushes_an_urgent_notification(watchdog):
    """A fired RAM kill pushes one urgent notification naming the terminated jobs."""
    for _ in range(ResourceWatchdog.SUSTAIN["ram_kill"]):
        watchdog._check_kill(ResourceWatchdog.RAM_KILL + 1.0)

    urgent = [alert for alert in watchdog.notifier.alerts if alert[2] == "urgent"]

    assert len(urgent) == 1
    assert urgent[0][0] == "RAM kill fired"
    assert "terminated 2 running job(s)" in urgent[0][1]


def test_low_disk_space_raises_a_sustained_alert(watchdog, monkeypatch):
    """Free space under the warn line raises a disk alert once sustained."""
    monkeypatch.setattr(watchdog, "_disk_free", lambda: (ResourceWatchdog.DISK_WARN - 2.0, 40.0))
    monkeypatch.setattr(watchdog, "_cpu_percent", lambda: 0.0)
    monkeypatch.setattr(watchdog, "_ram_percent", lambda: 0.0)

    for _ in range(ResourceWatchdog.SUSTAIN["disk"]):
        watchdog._evaluate()

    alert = _alert(watchdog, "disk")
    assert alert is not None
    assert alert["level"] == "warn"
    assert "disk almost full" in alert["message"]


def test_critically_low_disk_space_is_a_danger_alert(watchdog, monkeypatch):
    """Free space under the danger line raises the disk alert at danger level and pushes it high."""
    monkeypatch.setattr(watchdog, "_disk_free", lambda: (ResourceWatchdog.DISK_DANGER - 1.0, 8.0))
    monkeypatch.setattr(watchdog, "_cpu_percent", lambda: 0.0)
    monkeypatch.setattr(watchdog, "_ram_percent", lambda: 0.0)

    for _ in range(ResourceWatchdog.SUSTAIN["disk"]):
        watchdog._evaluate()

    assert _alert(watchdog, "disk")["level"] == "danger"
    assert ("host alert: disk", _alert(watchdog, "disk")["message"], "high") in watchdog.notifier.alerts


def test_ample_disk_space_raises_nothing(watchdog, monkeypatch):
    """Free space above the warn line never raises the disk alert."""
    monkeypatch.setattr(watchdog, "_disk_free", lambda: (50.0, 800.0))
    monkeypatch.setattr(watchdog, "_cpu_percent", lambda: 0.0)
    monkeypatch.setattr(watchdog, "_ram_percent", lambda: 0.0)

    for _ in range(4):
        watchdog._evaluate()

    assert _alert(watchdog, "disk") is None
