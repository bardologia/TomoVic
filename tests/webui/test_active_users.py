"""Tests for the ActiveUsers panel of the webui system monitor.

Covers per-user process, CPU, memory and GPU attribution, the filtering that
hides idle system accounts unless they hold a session, the row ordering, the
memory share computed against used RAM, and the isolation of returned state.
"""

from __future__ import annotations

import os

import pytest

from proc_stats     import ProcStats
from system_monitor import ActiveUsers


@pytest.fixture
def users(monitor, monkeypatch):
    """Yields an ActiveUsers panel with login sessions and GPU attribution stubbed empty."""
    instance = ActiveUsers(monitor)
    monkeypatch.setattr(instance, "_sessions", lambda: {})
    monkeypatch.setattr(instance, "_gpu_by_user", lambda: {})
    return instance


def test_sample_reports_current_user(users, monitor):
    """Checks the calling user appears with plausible process, memory, CPU and share values."""
    users.sample()
    users.sample()

    row = next(r for r in users.state() if r["uid"] == monitor.uid)
    assert row["me"] is True
    assert row["user"] == monitor.user
    assert row["nproc"] >= 1
    assert row["mem"] > 0
    assert row["cpu"] >= 0.0
    assert 0.0 <= row["mem_share"] <= 100.0


def test_gpu_usage_is_attributed_to_owner(users, monitor, monkeypatch):
    """Checks reported GPU memory and sorted device indices land on the owning user's row."""
    monkeypatch.setattr(users, "_gpu_by_user", lambda: {monitor.user: {"mem": 2048.0, "gpus": {1, 0}}})
    users.sample()

    row = next(r for r in users.state() if r["uid"] == monitor.uid)
    assert row["gpu_mem"] == 2048.0
    assert row["gpus"] == [0, 1]


def test_idle_system_user_is_filtered(users):
    """Checks a system account with no CPU time and no session is dropped from the table."""
    rows = users._rows({0: {"nproc": 3, "mem": 4096, "jdelta": 0}}, 2.0, {}, {})

    assert rows == []


def test_session_keeps_idle_system_user(users):
    """Checks an idle system account is kept, with its session count, when it has a login session."""
    rows = users._rows({0: {"nproc": 3, "mem": 4096, "jdelta": 0}}, 2.0, {"root": 2}, {})

    assert len(rows) == 1
    assert rows[0]["user"] == "root"
    assert rows[0]["sessions"] == 2


def test_busy_system_user_is_kept(users):
    """Checks a system account burning a full core is kept and reported near 100 percent CPU."""
    jdelta = int(2.0 * users.monitor.clk)
    rows   = users._rows({0: {"nproc": 1, "mem": 0, "jdelta": jdelta}}, 2.0, {}, {})

    assert len(rows) == 1
    assert rows[0]["cpu"] == pytest.approx(100.0, abs=1.0)


def test_rows_sorted_by_cpu_then_gpu_then_mem(users):
    """Checks rows order by CPU first, then GPU memory, then resident memory."""
    table = {
        65001: {"nproc": 1, "mem": 100, "jdelta": 0},
        65002: {"nproc": 1, "mem": 200, "jdelta": 0},
        65003: {"nproc": 1, "mem": 300, "jdelta": int(users.monitor.clk)},
    }
    gpu = {"65002": {"mem": 512.0, "gpus": {0}}}

    rows = users._rows(table, 1.0, {}, gpu)

    assert [r["uid"] for r in rows] == [65003, 65002, 65001]


def test_attributed_memory_never_exceeds_rss(users):
    """Checks the attributed memory of the running process is positive and bounded by its RSS."""
    pid      = os.getpid()
    page     = os.sysconf("SC_PAGE_SIZE")
    resident = int(open(f"/proc/{pid}/statm").read().split()[1]) * page

    attributed = ProcStats.attributed(pid)
    assert attributed is not None
    assert 0 < attributed <= resident


def test_mem_share_is_fraction_of_used_ram(users, monkeypatch):
    """Checks memory share is measured against used RAM rather than total RAM."""
    gib = 1 << 30
    monkeypatch.setattr(users.monitor, "_memory", lambda: {"total": 100 * gib, "available": 50 * gib})

    rows = users._rows({65001: {"nproc": 1, "mem": 25 * gib, "jdelta": 0}}, 1.0, {}, {})
    assert rows[0]["mem_share"] == 50.0


def test_mem_share_is_clamped_to_hundred(users, monkeypatch):
    """Checks a user holding more than the used RAM is reported at 100 percent."""
    gib = 1 << 30
    monkeypatch.setattr(users.monitor, "_memory", lambda: {"total": 100 * gib, "available": 50 * gib})

    rows = users._rows({65001: {"nproc": 1, "mem": 60 * gib, "jdelta": 0}}, 1.0, {}, {})
    assert rows[0]["mem_share"] == 100.0


def test_state_returns_copies(users):
    """Checks mutating a returned row does not alter the panel's stored state."""
    users.sample()

    state = users.state()
    if state:
        state[0]["user"] = "mutated"
        assert users.state()[0]["user"] != "mutated"


def test_snapshot_embeds_users(monitor):
    """Checks the monitor snapshot carries a users list."""
    snapshot = monitor.snapshot()

    assert "users" in snapshot
    assert isinstance(snapshot["users"], list)
