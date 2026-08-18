"""Thin /proc readers for host memory, CPU counters and per-process statistics.

Every reader returns None or an empty container when the kernel file is
unreadable or a process has already exited, so callers can sample a moving
process table without racing it.
"""

from __future__ import annotations

import os
import pwd
import threading
import time


class MemInfo:
    """Reads host memory totals from /proc/meminfo."""

    @staticmethod
    def fields() -> dict:
        """Returns every /proc/meminfo field in bytes, or an empty dict when unreadable."""
        info = {}
        try:
            for line in open("/proc/meminfo").read().splitlines():
                key, _, rest = line.partition(":")
                info[key]    = int(rest.split()[0]) * 1024
        except (OSError, ValueError, IndexError):
            return {}
        return info

    @staticmethod
    def used_percent() -> float | None:
        """Returns memory in use as a percentage of MemTotal, or None when unreadable."""
        info  = MemInfo.fields()
        total = info.get("MemTotal", 0)
        if total <= 0:
            return None
        return 100.0 * (total - info.get("MemAvailable", 0)) / total


class CpuCounters:
    """Reads the cumulative per-CPU jiffy counters from /proc/stat."""

    @staticmethod
    def read() -> dict:
        """Returns busy and total jiffies per CPU line.

        Idle and iowait jiffies are excluded from the busy figure.

        Returns:
            Mapping from CPU name ("cpu", "cpu0", ...) to a (busy, total)
            jiffy pair; empty when /proc/stat is unreadable.
        """
        counters = {}
        try:
            lines = open("/proc/stat").read().splitlines()
        except OSError:
            return counters

        for line in lines:
            if not line.startswith("cpu"):
                continue
            parts = line.split()
            vals  = [int(v) for v in parts[1:9]]
            busy  = sum(vals) - vals[3] - vals[4]
            counters[parts[0]] = (busy, sum(vals))

        return counters


class PssCache:
    """Caches proportional set size readings, which are expensive to sample per process.

    Attributes:
        lock: Guards the entry table against concurrent samplers.
        entries: Mapping from pid to a (monotonic timestamp, PSS in bytes) pair.
        pruned_t: Monotonic timestamp of the last prune sweep.
    """

    TTL_S   = 5.0
    PRUNE_S = 60.0

    def __init__(self) -> None:
        """Creates an empty cache with no entries and no prune history."""
        self.lock     = threading.Lock()
        self.entries  = {}
        self.pruned_t = 0.0

    def _read(self, pid: int) -> int | None:
        """Returns the process's PSS in bytes from smaps_rollup, or None when unreadable."""
        try:
            for line in open(f"/proc/{pid}/smaps_rollup"):
                if line.startswith("Pss:"):
                    return int(line.split()[1]) * 1024
        except (OSError, ValueError, IndexError):
            return None
        return None

    def _prune(self, now: float) -> None:
        """Drops entries older than the prune window, at most once per window."""
        if now - self.pruned_t < self.PRUNE_S:
            return

        self.pruned_t = now
        self.entries  = {pid: entry for pid, entry in self.entries.items() if now - entry[0] < self.PRUNE_S}

    def value(self, pid: int) -> int | None:
        """Returns the process's PSS in bytes, re-reading /proc only once the TTL expires.

        Args:
            pid: Process id to sample.

        Returns:
            Proportional set size in bytes, or None when the process is gone or
            its smaps_rollup is not readable.
        """
        now = time.monotonic()

        with self.lock:
            entry = self.entries.get(pid)
            if entry is not None and now - entry[0] < self.TTL_S:
                return entry[1]

        pss = self._read(pid)

        with self.lock:
            self.entries[pid] = (time.monotonic(), pss)
            self._prune(now)

        return pss


class ProcStats:
    """Per-process readings taken from /proc, with a shared PSS cache."""

    PAGE  = os.sysconf("SC_PAGE_SIZE")
    CACHE = PssCache()

    @staticmethod
    def username(uid: int) -> str:
        """Returns the account name for a uid, or the uid as text when it has no entry."""
        try:
            return pwd.getpwuid(uid).pw_name
        except KeyError:
            return str(uid)

    @staticmethod
    def stat(pid: int) -> dict | None:
        """Returns the parsed /proc/<pid>/stat fields the console uses.

        Args:
            pid: Process id to read.

        Returns:
            Mapping with the command name, state letter, parent pid, summed
            user and system jiffies, thread count, start time in clock ticks,
            and resident set size in bytes; None when the process is gone.
        """
        try:
            raw    = open(f"/proc/{pid}/stat").read()
            close  = raw.rindex(")")
            fields = raw[close + 2 :].split()
            return {
                "comm"    : raw[raw.index("(") + 1 : close],
                "state"   : fields[0],
                "ppid"    : int(fields[1]),
                "jiffies" : int(fields[11]) + int(fields[12]),
                "threads" : int(fields[17]),
                "started" : fields[19],
                "rss"     : int(fields[21]) * ProcStats.PAGE,
            }
        except (OSError, ValueError, IndexError):
            return None

    @staticmethod
    def pss(pid: int) -> int | None:
        """Returns the cached proportional set size of a process in bytes."""
        return ProcStats.CACHE.value(pid)

    @staticmethod
    def private(pid: int) -> int | None:
        """Returns the process's private (non-shared) resident memory in bytes, or None."""
        try:
            parts    = open(f"/proc/{pid}/statm").read().split()
            resident = int(parts[1])
            shared   = int(parts[2])
        except (OSError, ValueError, IndexError):
            return None
        return max(0, resident - shared) * ProcStats.PAGE

    @staticmethod
    def attributed(pid: int) -> int | None:
        """Returns the memory in bytes fairly charged to a process.

        Prefers proportional set size so shared pages are split between the
        processes mapping them, and falls back to private resident memory when
        smaps_rollup is not readable.
        """
        pss = ProcStats.pss(pid)
        if pss is not None:
            return pss
        return ProcStats.private(pid)

    @staticmethod
    def ppid(pid: int) -> int:
        """Returns the parent pid of a process, or 0 when the process is gone."""
        stat = ProcStats.stat(pid)
        return stat["ppid"] if stat is not None else 0


class ProcSweep:
    """Walks the whole /proc process table in one pass."""

    @staticmethod
    def rows() -> list[dict]:
        """Returns one row per live process on the host.

        Processes that exit mid-sweep are skipped rather than raising.

        Returns:
            List of mappings with "pid", the owning "uid", the parsed "stat"
            fields, and "attributed" memory in bytes.
        """
        rows = []

        for entry in os.listdir("/proc"):
            if not entry.isdigit():
                continue

            pid = int(entry)
            try:
                uid = os.stat(f"/proc/{pid}").st_uid
            except OSError:
                continue

            stat = ProcStats.stat(pid)
            if stat is None:
                continue

            rows.append({"pid": pid, "uid": uid, "stat": stat, "attributed": ProcStats.attributed(pid)})

        return rows
