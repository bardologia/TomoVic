"""Tests for the webui contention monitor that flags the stall this user inflicts on neighbours.

Covers the per-user slice sampling (CPU share from the slice counters, the
worst-stalled neighbour per resource, dominance), the verdicts (a stalled
neighbour is this user's alarm only when this user is the dominant consumer,
host pressure alone raises nothing), the disabled state when a kernel source is
missing, alarm bookkeeping (only alarms attributed to the current user are
logged, escalations are logged once, neighbour alarms clear silently), the
separate full-stall threshold used for I/O, the automatic throttle that fires
once per announced alarm of this user's, and the auto-nuke push.
"""

from __future__ import annotations

import os
import threading

import pytest

from contention_monitor import ContentionMonitor
from politeness         import JobPoliteness
from proc_stats         import UserSlices
from web_logger         import WebLogger

from tests.webui.conftest import StubNotifier, StubPaths


class StubNuke:
    """Stand-in for the process nuker, counting how often it is triggered.

    Attributes:
        fired : Number of nuke invocations.
    """

    def __init__(self) -> None:
        """Initialises the trigger counter at zero."""
        self.fired = 0

    def nuke(self) -> dict:
        """Records a trigger and returns a successful no-op result."""
        self.fired += 1
        return {"ok": True, "signalled": 0, "killed": 0}


class StubThrottle:
    """Stand-in for the job throttle, counting calls and answering a fixed result.

    Attributes:
        calls  : Number of `apply` invocations.
        result : Mapping returned by every `apply`.
    """

    def __init__(self, ok: bool = True) -> None:
        """Starts with no calls and a result of the given success."""
        self.calls  = 0
        self.result = {"ok": ok, "processes": 3, "renice": 0 if ok else 1, "ionice": 0, "error": "" if ok else "renice: failed to set priority"}

    def apply(self) -> dict:
        """Records one call and returns the fixed result."""
        self.calls += 1
        return dict(self.result)


class FakeHost:
    """Writes a fake /proc/pressure directory and user.slice tree.

    Attributes:
        psi    : Directory standing in for /proc/pressure.
        slices : Directory standing in for /sys/fs/cgroup/user.slice.
    """

    def __init__(self, root) -> None:
        """Creates the two directories with quiet host pressure files."""
        self.psi    = root / "pressure"
        self.slices = root / "user.slice"
        self.psi.mkdir()
        self.slices.mkdir()
        for name in ("cpu", "memory", "io"):
            (self.psi / name).write_text(self.pressure(0.0, 0.0))

    @staticmethod
    def pressure(some: float, full: float) -> str:
        """Returns the text of a pressure file with the given avg10 percentages."""
        return f"some avg10={some:.2f} avg60=0.00 avg300=0.00 total=0\nfull avg10={full:.2f} avg60=0.00 avg300=0.00 total=0\n"

    def host(self, resource: str, some: float, full: float = 0.0) -> None:
        """Sets the machine-wide pressure of one resource ("cpu", "memory" or "io")."""
        (self.psi / resource).write_text(self.pressure(some, full))

    def user(self, uid: int, cpu_usec: int, anon: int = 0, cpu: tuple = (0.0, 0.0), mem: tuple = (0.0, 0.0), io: tuple = (0.0, 0.0)) -> None:
        """Writes or rewrites one user slice.

        Args:
            uid      : Numeric user id of the slice.
            cpu_usec : Cumulative CPU time of the slice in microseconds.
            anon     : Anonymous memory charged to the slice in bytes.
            cpu      : (some, full) avg10 percentages of the slice's CPU pressure.
            mem      : (some, full) avg10 percentages of the slice's memory pressure.
            io       : (some, full) avg10 percentages of the slice's I/O pressure.
        """
        base = self.slices / f"user-{uid}.slice"
        base.mkdir(exist_ok=True)
        (base / "cpu.stat").write_text(f"usage_usec {cpu_usec}\nuser_usec {cpu_usec}\nsystem_usec 0\n")
        (base / "memory.stat").write_text(f"anon {anon}\nfile 0\nshmem 0\n")
        (base / "cpu.pressure").write_text(self.pressure(*cpu))
        (base / "memory.pressure").write_text(self.pressure(*mem))
        (base / "io.pressure").write_text(self.pressure(*io))


ME       = os.getuid()
NEIGHBOUR = 424242


@pytest.fixture
def host(tmp_path, monkeypatch):
    """Points the slice reader at a fake host tree and returns its writer."""
    fake = FakeHost(tmp_path)
    monkeypatch.setattr(UserSlices, "PSI_ROOT", str(fake.psi))
    monkeypatch.setattr(UserSlices, "ROOT", str(fake.slices))
    return fake


def _monitor(tmp_path, throttle: StubThrottle | None = None, auto_throttle: bool = False) -> ContentionMonitor:
    """Builds a contention monitor over stub paths with the given or a fresh stub throttle, switching the automatic throttle on when asked."""
    paths      = StubPaths(tmp_path / "repo")
    logger     = WebLogger()
    politeness = JobPoliteness(paths, logger)
    if auto_throttle:
        politeness.configure({"auto_throttle": True})
    return ContentionMonitor(paths, logger, StubNotifier(), StubNuke(), throttle or StubThrottle(), politeness)


@pytest.fixture
def monitor(tmp_path, host):
    """Returns a contention monitor over stub paths, the fake host, a stub nuker and a stub throttle, with the default settings."""
    return _monitor(tmp_path)


@pytest.fixture
def throttling(tmp_path, host):
    """Returns a contention monitor like `monitor` whose automatic throttle was switched on."""
    return _monitor(tmp_path, auto_throttle=True)


def _signals(io_full: float) -> dict:
    """Builds a sample where one neighbour is fully stalled on disk by this user.

    Args:
        io_full : PSI full-stall percentage of the neighbour's I/O pressure.

    Returns:
        Signal dictionary with quiet CPU and memory, a neighbour stalled 99 percent
        of the time on I/O, and the disk throughput entirely driven by this user.
    """
    quiet = {"stall": 0.0, "full": 0.0, "user": None, "n": 0}
    return {
        "psi"    : {"cpu": {"some": 0.0, "full": 0.0}, "mem": {"some": 0.0, "full": 0.0}, "io": {"some": 99.0, "full": io_full}},
        "swap"   : {"in_mbs": 0.0, "out_mbs": 0.0},
        "mem"    : {"used_pct": 10.0, "mine_gb": 1.0, "mine_share": 0.1, "dominant": False},
        "io"     : {"device": "sda", "util": 99.0, "await_ms": 1.0, "read_mbs": 1.0, "write_mbs": 1.0, "total_mbs": 2.0, "mine_mbs": 2.0, "mine_share": 1.0, "dominant": True},
        "cpu"    : {"load_ratio": 0.1, "mine_pct": 1.0, "mine_share": 0.1, "dominant": False},
        "mine"   : {"nproc": 1, "mem_gb": 1.0, "stall": {"cpu": 0.0, "mem": 0.0, "io": 0.0}},
        "leak"   : None,
        "top"    : None,
        "users"  : [],
        "others" : {"cpu": dict(quiet), "mem": dict(quiet), "io": {"stall": 99.0, "full": io_full, "user": "neighbour", "n": 1}},
    }


def _alarm(monitor: ContentionMonitor, kind: str) -> dict | None:
    """Returns the active alarm of the given kind, or None if it is not raised."""
    return next((entry for entry in monitor.state()["active"] if entry["kind"] == kind), None)


def _alarm_events(monitor: ContentionMonitor) -> list[dict]:
    """Returns the recorded events minus the throttle entries the announcements add."""
    return [event for event in monitor.state()["events"] if event["kind"] != "throttle"]


def _advance(monitor: ContentionMonitor, host: FakeHost, me_usec: int, other_usec: int, **pressure) -> dict:
    """Rewrites both slices with the given counters and takes one sample.

    Args:
        monitor    : Monitor under test.
        host       : Fake host tree.
        me_usec    : Cumulative CPU time of this user's slice.
        other_usec : Cumulative CPU time of the neighbour's slice.
        pressure   : Pressure tuples forwarded to the neighbour's slice.

    Returns:
        The sample as returned by `_sample`.
    """
    host.user(ME, me_usec, anon=4 << 30)
    host.user(NEIGHBOUR, other_usec, anon=1 << 30, **pressure)
    return monitor._sample()


def test_slice_rows_carry_cpu_memory_and_stall(host):
    """Checks a slice row reports its counter, its charged memory and its three pressures."""
    host.user(NEIGHBOUR, 5_000_000, anon=3 << 30, cpu=(12.5, 1.0), io=(7.0, 0.0))

    rows = UserSlices.rows()

    assert len(rows) == 1
    assert rows[0]["uid"]      == NEIGHBOUR
    assert rows[0]["cpu_usec"] == 5_000_000
    assert rows[0]["mem"]      == 3 << 30
    assert rows[0]["stall"]    == {"cpu": {"some": 12.5, "full": 1.0}, "mem": {"some": 0.0, "full": 0.0}, "io": {"some": 7.0, "full": 0.0}}


def test_cpu_share_comes_from_the_slice_counters(monitor, host):
    """Checks the CPU share is this slice's delta over the sum of every slice's delta."""
    _advance(monitor, host, 0, 0)
    sample = _advance(monitor, host, 6_000_000, 2_000_000)

    assert sample["cpu"]["mine_share"] == pytest.approx(0.75)
    assert sample["cpu"]["dominant"]  is True
    assert sample["others"]["cpu"]["user"] is not None


def test_the_worst_stalled_neighbour_is_reported_per_resource(monitor, host):
    """Checks the neighbour summary names the stalled user and counts those above the threshold."""
    _advance(monitor, host, 0, 0)
    sample = _advance(monitor, host, 1, 1, cpu=(45.0, 6.0), mem=(2.0, 0.0))

    assert sample["others"]["cpu"] == {"stall": 45.0, "full": 6.0, "user": sample["others"]["cpu"]["user"], "n": 1}
    assert sample["others"]["mem"]["n"] == 0
    assert sample["mine"]["stall"]      == {"cpu": 0.0, "mem": 0.0, "io": 0.0}


def test_a_stalled_neighbour_with_me_dominant_is_my_alarm(monitor, host):
    """Checks a neighbour waiting for CPU while this user holds most of it raises an alarm owned by this user."""
    _advance(monitor, host, 0, 0)
    for step in range(1, ContentionMonitor.SUSTAIN + 1):
        monitor._evaluate(_advance(monitor, host, step * 9_000_000, step * 1_000_000, cpu=(50.0, 0.0)))

    alarm = _alarm(monitor, "cpu")

    assert alarm is not None
    assert alarm["mine"]  is True
    assert alarm["level"] == "warn"
    assert "waited for a core 50%" in alarm["message"]


def test_a_stalled_neighbour_with_another_dominant_is_not_mine(monitor, host):
    """Checks the same neighbour stall is attributed elsewhere when the neighbour holds the CPU."""
    _advance(monitor, host, 0, 0)
    for step in range(1, ContentionMonitor.SUSTAIN + 1):
        monitor._evaluate(_advance(monitor, host, step * 1_000_000, step * 9_000_000, cpu=(50.0, 0.0)))

    alarm = _alarm(monitor, "cpu")

    assert alarm is not None
    assert alarm["mine"] is False
    assert monitor.state()["events"] == []


def test_host_pressure_without_a_stalled_neighbour_raises_nothing(monitor, host):
    """Checks machine-wide pressure alone, with every neighbour's slice quiet, is not an alarm."""
    host.host("cpu", 90.0)
    host.host("io", 90.0, 20.0)
    _advance(monitor, host, 0, 0)
    for step in range(1, ContentionMonitor.SUSTAIN + 2):
        monitor._evaluate(_advance(monitor, host, step * 9_000_000, step * 1_000_000))

    assert monitor.state()["active"] == []


def test_a_fully_stalled_neighbour_escalates_to_danger(monitor, host):
    """Checks the neighbour's full-stall average drives the alarm level."""
    _advance(monitor, host, 0, 0)
    for step in range(1, ContentionMonitor.SUSTAIN + 1):
        monitor._evaluate(_advance(monitor, host, step * 9_000_000, step * 1_000_000, cpu=(60.0, 10.0)))

    assert _alarm(monitor, "cpu")["level"] == "danger"


def test_missing_pressure_files_disable_the_monitor(tmp_path, host, monkeypatch):
    """Checks a kernel without /proc/pressure leaves the monitor off instead of sampling zeros."""
    monkeypatch.setattr(UserSlices, "PSI_ROOT", str(tmp_path / "absent"))
    monitor = _monitor(tmp_path)

    monitor.start()

    assert monitor.state()["sources"]["psi"] is False
    assert monitor.state()["signals"] == {}
    assert "ContentionMonitor" not in [thread.name for thread in threading.enumerate()]


def test_an_alarm_that_becomes_mine_is_recorded_and_logged(monitor):
    """Checks an alarm is logged only once it is attributed to the current user."""
    monitor._raise("mem", "warn", False, "neighbour holds the RAM")

    assert monitor.state()["events"] == []

    monitor._raise("mem", "warn", True, "you hold the RAM")
    events = _alarm_events(monitor)

    assert len(events)         == 1
    assert events[0]["kind"]   == "mem"
    assert _alarm(monitor, "mem")["mine"] is True


def test_an_escalation_to_danger_is_recorded_once(monitor):
    """Checks repeated raises at the same level log nothing and only the escalation is added."""
    monitor._raise("mem", "warn", True, "you hold the RAM")
    monitor._raise("mem", "warn", True, "you hold the RAM")
    monitor._raise("mem", "danger", True, "you hold the RAM and the neighbours are stalling")
    monitor._raise("mem", "danger", True, "you hold the RAM and the neighbours are stalling")

    levels = [event["level"] for event in _alarm_events(monitor)]
    assert levels == ["warn", "danger"]


def test_an_alarm_raised_for_a_neighbour_clears_without_a_log(monitor):
    """Checks a neighbour-owned alarm leaves no event behind when it drops."""
    monitor._raise("io", "warn", False, "neighbour drives the disk")
    monitor._drop("io")

    assert monitor.state()["active"] == []
    assert monitor.state()["events"] == []


def test_io_escalation_uses_its_own_full_threshold(monitor, monkeypatch):
    """Checks the I/O alarm level follows IO_FULL rather than the shared threshold."""
    for _ in range(ContentionMonitor.SUSTAIN):
        monitor._evaluate(_signals(io_full=6.0))

    assert _alarm(monitor, "io")["level"] == "danger"

    monkeypatch.setattr(ContentionMonitor, "IO_FULL", 50.0)
    monitor._evaluate(_signals(io_full=6.0))

    assert _alarm(monitor, "io")["level"] == "warn"


def test_an_announced_alert_is_pushed_through_the_notifier(monitor):
    """An alert attributed to this user is pushed once when it is announced."""
    for _ in range(ContentionMonitor.SUSTAIN):
        monitor._track("io", "warn", True, False, True, "disk stall caused by you")

    pushed = [alert for alert in monitor.notifier.alerts if alert[0].startswith("neighbour impact")]

    assert pushed == [("neighbour impact: io", "disk stall caused by you", "default")]


def test_a_neighbours_alert_is_not_pushed(monitor):
    """An alert another user causes stays out of the push channel."""
    for _ in range(ContentionMonitor.SUSTAIN):
        monitor._track("io", "warn", True, False, False, "disk stall caused by them")

    assert monitor.notifier.alerts == []


def test_announcing_my_alarm_throttles_once(throttling):
    """Checks the first announcement of an alarm this user causes lowers the running jobs once and records it."""
    for _ in range(ContentionMonitor.SUSTAIN):
        throttling._track("cpu", "warn", True, False, True, "cpu stall caused by you")
    throttling._track("cpu", "warn", True, False, True, "cpu stall caused by you")
    throttling._track("cpu", "danger", True, False, True, "cpu stall caused by you, worse")

    events = [event for event in throttling.state()["events"] if event["kind"] == "throttle"]

    assert throttling.throttle.calls == 1
    assert len(events) == 1
    assert "lowered 3 processes" in events[0]["message"]
    assert throttling.state()["throttled"] == ["cpu"]
    assert ("auto-throttle", events[0]["message"], "default") in throttling.notifier.alerts


def test_a_dropped_alarm_can_throttle_again_when_it_returns(throttling):
    """Checks the throttle re-arms only after the alarm has cleared."""
    for _ in range(ContentionMonitor.SUSTAIN):
        throttling._track("mem", "warn", True, False, True, "memory stall caused by you")
    throttling._drop("mem")
    for _ in range(ContentionMonitor.SUSTAIN):
        throttling._track("mem", "warn", True, False, True, "memory stall caused by you")

    assert throttling.throttle.calls == 2
    assert throttling.state()["throttled"] == ["mem"]


def test_a_neighbours_alarm_never_throttles(throttling):
    """Checks an alarm attributed to another user leaves this user's jobs alone."""
    for _ in range(ContentionMonitor.SUSTAIN):
        throttling._track("io", "danger", True, False, False, "disk stall caused by them")

    assert throttling.throttle.calls == 0
    assert throttling.state()["throttled"] == []


def test_a_leak_alarm_never_throttles(throttling):
    """Checks the advisory RAM-growth alarm does not lower priorities."""
    for _ in range(ContentionMonitor.SUSTAIN):
        throttling._track("leak", "warn", True, False, True, "process climbing")

    assert throttling.throttle.calls == 0


def test_a_fresh_console_leaves_the_jobs_alone(monitor):
    """Checks the automatic throttle is off by default, so an alarm this user causes lowers nothing."""
    assert monitor.politeness.auto_throttle() is False
    for _ in range(ContentionMonitor.SUSTAIN):
        monitor._track("cpu", "danger", True, False, True, "cpu stall caused by you")

    assert monitor.throttle.calls == 0
    assert _alarm(monitor, "cpu")["mine"] is True


def test_an_alarm_that_becomes_mine_throttles_at_the_flip(throttling):
    """Checks ownership flipping to this user on a standing alarm triggers the throttle."""
    for _ in range(ContentionMonitor.SUSTAIN):
        throttling._track("cpu", "warn", True, False, False, "cpu stall caused by them")

    assert throttling.throttle.calls == 0

    throttling._track("cpu", "warn", True, False, True, "cpu stall caused by you")

    assert throttling.throttle.calls == 1


def test_a_failed_throttle_is_recorded_as_danger(tmp_path, host):
    """Checks a throttle that could not lower the processes is logged, recorded and pushed high."""
    monitor = _monitor(tmp_path, StubThrottle(ok=False), auto_throttle=True)
    for _ in range(ContentionMonitor.SUSTAIN):
        monitor._track("cpu", "warn", True, False, True, "cpu stall caused by you")

    events = [event for event in monitor.state()["events"] if event["kind"] == "throttle"]

    assert len(events) == 1
    assert events[0]["level"] == "danger"
    assert "throttle FAILED" in events[0]["message"]
    assert ("auto-throttle", events[0]["message"], "high") in monitor.notifier.alerts


def test_the_state_carries_the_politeness_settings(monitor):
    """Checks the UI snapshot includes the launch politeness and its prefix."""
    state = monitor.state()["politeness"]

    assert state["level"]         == "polite"
    assert state["auto_throttle"] is False
    assert state["prefix"]        == "nice -n 10 ionice -c 2 -n 7"


def test_the_auto_nuke_is_disarmed_by_default(monitor):
    """Checks a fresh monitor reports the automatic nuke disarmed until it is armed explicitly."""
    assert monitor.state()["auto_nuke"] is False


def test_the_auto_nuke_pushes_an_urgent_notification(monitor):
    """A fired auto-nuke pushes one urgent notification."""
    monitor.auto_nuke = True
    for _ in range(ContentionMonitor.SUSTAIN):
        monitor._track("mem", "danger", True, False, True, "memory stall caused by you")
    for _ in range(ContentionMonitor.NUKE_SUSTAIN):
        monitor._check_nuke()

    urgent = [alert for alert in monitor.notifier.alerts if alert[2] == "urgent"]

    assert monitor.nuke.fired == 1
    assert len(urgent) == 1
    assert urgent[0][0] == "auto-nuke fired"
