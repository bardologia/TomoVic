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
        lock     : Guards the entry table against concurrent samplers.
        entries  : Mapping from pid to a (monotonic timestamp, PSS in bytes) pair.
        pruned_t : Monotonic timestamp of the last prune sweep.
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
            pid : Process id to sample.

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
            pid : Process id to read.

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


class UserSlices:
    """Reads the per-user cgroup v2 slices that systemd keeps under user.slice.

    Every login user owns one `user-<uid>.slice`. Its three pressure files exist
    whatever controllers are delegated, `cpu.stat` reports the slice's summed CPU
    time with exited children included, and `memory.stat` gives the memory charged
    to the user as long as the memory controller is delegated to user.slice.
    """

    ROOT      = "/sys/fs/cgroup/user.slice"
    PSI_ROOT  = "/proc/pressure"
    RESOURCES = (("cpu", "cpu"), ("mem", "memory"), ("io", "io"))

    @staticmethod
    def host_available() -> bool:
        """Returns whether the kernel exposes machine-wide pressure-stall files."""
        return os.path.isfile(os.path.join(UserSlices.PSI_ROOT, "cpu"))

    @staticmethod
    def available() -> bool:
        """Returns whether the user.slice cgroup tree exists on this host."""
        return os.path.isdir(UserSlices.ROOT)

    @staticmethod
    def pressure(path: str) -> dict:
        """Parses one pressure file into its 10-second averages.

        Args:
            path : Path of a `cpu.pressure`, `memory.pressure` or `io.pressure` file.

        Returns:
            Mapping with "some" and "full", the avg10 percentages of time at least one
            task, respectively every task, of the group was stalled.

        Raises:
            OSError   : The file cannot be read.
            ValueError: The file does not carry the expected fields.
        """
        out = {"some": 0.0, "full": 0.0}
        for line in open(path).read().splitlines():
            head, *tokens = line.split()
            fields        = dict(token.split("=") for token in tokens if "=" in token)
            if head in out:
                out[head] = float(fields["avg10"])
        return out

    @staticmethod
    def host_pressure() -> dict:
        """Returns the machine-wide pressure keyed "cpu", "mem" and "io".

        Raises:
            OSError: `/proc/pressure` is unavailable on this kernel.
        """
        return {key: UserSlices.pressure(os.path.join(UserSlices.PSI_ROOT, name)) for key, name in UserSlices.RESOURCES}

    @staticmethod
    def self_slice_uid() -> int | None:
        """Returns the uid of the user slice the calling process lives in, or None when outside user.slice."""
        try:
            line = open("/proc/self/cgroup").read()
        except OSError:
            return None

        marker = "/user.slice/user-"
        start  = line.find(marker)
        if start < 0:
            return None
        digits = line[start + len(marker):].split(".slice", 1)[0]
        return int(digits) if digits.isdigit() else None

    @staticmethod
    def _counter(path: str, keys: tuple) -> dict:
        """Returns the named integer fields of a flat-keyed cgroup file, missing keys as 0."""
        out = {key: 0 for key in keys}
        for line in open(path).read().splitlines():
            key, _, value = line.partition(" ")
            if key in out:
                out[key] = int(value)
        return out

    @staticmethod
    def rows() -> list[dict]:
        """Returns one row per user slice, skipping slices that vanish mid-read.

        Returns:
            List of mappings with the "uid", the cumulative "cpu_usec" of the slice,
            its "mem" in bytes charged as anonymous plus shared memory, and "stall",
            the pressure keyed "cpu", "mem" and "io" as returned by `pressure`.
        """
        rows = []

        for entry in os.listdir(UserSlices.ROOT):
            if not (entry.startswith("user-") and entry.endswith(".slice")):
                continue
            digits = entry[len("user-"):-len(".slice")]
            if not digits.isdigit():
                continue

            base = os.path.join(UserSlices.ROOT, entry)
            try:
                cpu   = UserSlices._counter(os.path.join(base, "cpu.stat"), ("usage_usec",))
                mem   = UserSlices._counter(os.path.join(base, "memory.stat"), ("anon", "shmem"))
                stall = {key: UserSlices.pressure(os.path.join(base, f"{name}.pressure")) for key, name in UserSlices.RESOURCES}
            except OSError:
                continue

            rows.append({"uid": int(digits), "cpu_usec": cpu["usage_usec"], "mem": mem["anon"] + mem["shmem"], "stall": stall})

        return rows
