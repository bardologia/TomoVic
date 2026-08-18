"""Tests that the system monitor's process rows report a live thread count per process."""

from __future__ import annotations

import os
import threading


def test_rows_report_thread_counts(monitor):
    """Every process row carries an integer thread count of at least one."""
    rows = monitor._procs({})

    assert rows
    assert all(isinstance(row["threads"], int) and row["threads"] >= 1 for row in rows)


def test_own_process_thread_count_tracks_spawned_threads(monitor):
    """The row for the test process reflects the five threads it just started."""
    release = threading.Event()
    workers = [threading.Thread(target=release.wait, daemon=True) for _ in range(5)]
    for worker in workers:
        worker.start()

    try:
        monitor.PROC_LIMIT = 100000
        row = next(r for r in monitor._procs({}) if r["pid"] == os.getpid())
        assert row["threads"] >= 6
    finally:
        release.set()
        for worker in workers:
            worker.join()
