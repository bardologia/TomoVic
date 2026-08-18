"""Host, GPU and multi-user monitoring behind the console's system panel.

Reads CPU and memory counters from /proc, GPU devices and compute apps from
nvidia-smi, and disk usage from du, then assembles the snapshot the console polls.
Background threads keep a rolling CPU/RAM/GPU history and a per-user activity
table alive between snapshots.
"""

from __future__ import annotations

import os
import shutil
import socket
import subprocess
import threading
import time
from collections import deque

from proc_stats import CpuCounters, MemInfo, ProcStats, ProcSweep
from web_logger import WebLogger


class GpuProbe:
    """Short-lived cache over the two nvidia-smi queries the monitor needs.

    Device and compute-app rows are re-read at most every CACHE_TTL_S seconds, and a
    failing or absent nvidia-smi yields None so callers can treat GPU occupancy as
    unknown rather than empty.

    Attributes:
        logger: Console logger, warned once per failure and once per recovery.
        lock: Guards the cache and the failure flag.
        cache: Raw rows per query flag, with the monotonic time they were read at.
        installed: Whether nvidia-smi is on PATH.
        failed: Whether the last probe failed, used to log state changes only.
    """

    DEVICE_QUERY = "index,name,utilization.gpu,memory.used,memory.total,temperature.gpu,power.draw,power.limit,uuid"
    APP_QUERY    = "pid,used_gpu_memory,gpu_uuid"
    CACHE_TTL_S  = 0.5
    TIMEOUT_S    = 3

    def __init__(self, logger: WebLogger) -> None:
        """Stores the logger, creates the cache and records whether nvidia-smi exists."""
        self.logger    = logger
        self.lock      = threading.Lock()
        self.cache     = {}
        self.installed = shutil.which("nvidia-smi") is not None
        self.failed    = False

    def devices(self) -> list[list[str]] | None:
        """Returns the cached per-device rows, or None when nvidia-smi does not answer."""
        return self._cached(f"--query-gpu={self.DEVICE_QUERY}", 9)

    def apps(self) -> list[list[str]] | None:
        """Returns the cached compute-app rows, or None when nvidia-smi does not answer."""
        return self._cached(f"--query-compute-apps={self.APP_QUERY}", 3)

    def _cached(self, flag: str, width: int) -> list[list[str]] | None:
        """Returns the rows of one query, re-reading them once the cache entry expires."""
        now = time.monotonic()

        with self.lock:
            entry = self.cache.get(flag)
            if entry is not None and now - entry[0] < self.CACHE_TTL_S:
                return entry[1]

        rows = self._rows(flag, width)

        with self.lock:
            self.cache[flag] = (time.monotonic(), rows)

        return rows

    def _rows(self, flag: str, width: int) -> list[list[str]] | None:
        """Runs one nvidia-smi query and returns its rows.

        Args:
            flag: Query flag passed to nvidia-smi.
            width: Minimum number of cells a row must hold to be kept.

        Returns:
            One list of stripped cells per accepted line, an empty list when nvidia-smi
            is not installed, or None when the call fails or exits non-zero.
        """
        if not self.installed:
            return []

        try:
            out = subprocess.run(["nvidia-smi", flag, "--format=csv,noheader,nounits"], capture_output=True, text=True, timeout=self.TIMEOUT_S)
        except (OSError, subprocess.TimeoutExpired) as error:
            self._failed(f"nvidia-smi {flag} did not answer ({error})")
            return None

        if out.returncode != 0:
            self._failed(f"nvidia-smi {flag} exited with code {out.returncode} ({out.stderr.strip() or 'no stderr'})")
            return None

        rows = []
        for line in out.stdout.strip().splitlines():
            cells = [cell.strip() for cell in line.split(",")]
            if len(cells) >= width:
                rows.append(cells)

        self._recovered()
        return rows

    def _failed(self, reason: str) -> None:
        """Marks the probe as failing and logs the reason on the first failure only."""
        with self.lock:
            first       = not self.failed
            self.failed = True

        if first:
            self.logger.error(f"{reason}: GPU occupancy is unknown, so the schedule, charity and intrusion checks stand down until it answers again")

    def _recovered(self) -> None:
        """Clears the failure flag and logs recovery when the probe was failing."""
        with self.lock:
            recovered   = self.failed
            self.failed = False

        if recovered:
            self.logger.ok("nvidia-smi answers again, GPU occupancy is known")


class SystemMonitor:
    """Assembles the host snapshot: CPU, memory, disk, GPUs, processes and users.

    Attributes:
        paths: Project paths providing the repository root measured on disk.
        logger: Console logger.
        lock: Serialises the CPU and process sampling inside a snapshot.
        probe: nvidia-smi probe backing the GPU views.
        prev_cpu: Previous per-core CPU counters, for percentage deltas.
        prev_proc: Previous per-process CPU jiffies, for percentage deltas.
        prev_proc_t: Monotonic time the process counters were last read at.
        uid: Numeric user id owning the console.
        user: Login name of that user.
        clk: Clock ticks per second used to convert jiffies to CPU time.
        page: Memory page size in bytes.
        user_root: Highest ancestor of the repository still owned by this user.
        du_usage: Latest du result in bytes for the user root and the repository.
        history: Rolling CPU, RAM and GPU history sampler.
        users: Per-user activity sampler.
    """

    PROC_LIMIT   = 30
    DU_REFRESH_S = 600.0

    def __init__(self, paths, logger: WebLogger) -> None:
        """Reads the host constants and starts the disk, history and user sampling threads."""
        self.paths       = paths
        self.logger      = logger
        self.lock        = threading.Lock()
        self.probe       = GpuProbe(logger)
        self.prev_cpu    = {}
        self.prev_proc   = {}
        self.prev_proc_t = 0.0
        self.uid         = os.getuid()
        self.user        = ProcStats.username(self.uid)
        self.clk         = os.sysconf("SC_CLK_TCK")
        self.page        = os.sysconf("SC_PAGE_SIZE")
        self.user_root   = self._user_root()
        self.du_usage    = {"user": None, "repo": None}
        self.history     = SystemHistory(self)
        self.users       = ActiveUsers(self)

        threading.Thread(target=self._du_loop, daemon=True).start()
        threading.Thread(target=self.history.sample_loop, daemon=True).start()
        threading.Thread(target=self.users.sample_loop, daemon=True).start()

    def _cpu_percents(self) -> tuple[list[float], float]:
        """Returns the per-core busy percentages and the total, against the previous read."""
        cores = []
        total = 0.0

        for key, (busy, whole) in CpuCounters.read().items():
            prev = self.prev_cpu.get(key)
            self.prev_cpu[key] = (busy, whole)

            pct = 0.0
            if prev is not None and whole > prev[1]:
                pct = round(100.0 * (busy - prev[0]) / (whole - prev[1]), 1)

            if key == "cpu":
                total = pct
            else:
                cores.append(pct)

        return cores, total

    def _procs(self, gpu_mem: dict) -> list[dict]:
        """Returns the PROC_LIMIT busiest processes owned by this user.

        Args:
            gpu_mem: GPU memory in MiB held per pid, from the compute-app query.

        Returns:
            Rows with pid, state, CPU percentage since the previous sweep, RSS, thread
            count, GPU memory, command line and the PSS of the retained top rows, sorted
            by CPU, then GPU memory, then RSS.
        """
        now  = time.monotonic()
        dt   = now - self.prev_proc_t
        rows = []
        seen = set()

        for entry in os.listdir("/proc"):
            if not entry.isdigit():
                continue
            pid = int(entry)
            try:
                if os.stat(f"/proc/{pid}").st_uid != self.uid:
                    continue
            except OSError:
                continue

            stat = ProcStats.stat(pid)
            if stat is None:
                continue

            prev = self.prev_proc.get(pid)
            cpu  = 0.0
            if prev is not None and self.prev_proc_t > 0 and dt > 0:
                cpu = max(0.0, round(100.0 * (stat["jiffies"] - prev) / self.clk / dt, 1))
            self.prev_proc[pid] = stat["jiffies"]
            seen.add(pid)

            cmd = self._pid_cmd(pid)

            rows.append({
                "pid"     : pid,
                "state"   : stat["state"],
                "cpu"     : cpu,
                "rss"     : stat["rss"],
                "threads" : stat["threads"],
                "gpu"     : gpu_mem.get(pid, 0),
                "cmd"     : (cmd or stat["comm"])[:200],
            })

        self.prev_proc_t = now
        self.prev_proc   = {p: j for p, j in self.prev_proc.items() if p in seen}

        rows.sort(key=lambda r: (-r["cpu"], -r["gpu"], -r["rss"]))
        top = rows[: self.PROC_LIMIT]

        for row in top:
            pss         = ProcStats.pss(row["pid"])
            row["pss"]  = pss if pss is not None else row["rss"]

        return top

    def _gpu_devices(self) -> list[dict] | None:
        """Returns one record per GPU device, or None when occupancy is unknown."""
        rows = self.probe.devices()
        if rows is None:
            return None

        devices = []
        for cells in rows:
            devices.append({
                "index"       : self._num(cells[0]),
                "name"        : cells[1],
                "util"        : self._num(cells[2]),
                "mem_used"    : self._num(cells[3]),
                "mem_total"   : self._num(cells[4]),
                "temp"        : self._num(cells[5]),
                "power"       : self._num(cells[6]),
                "power_limit" : self._num(cells[7]),
                "uuid"        : cells[8],
            })
        return devices

    def _compute_apps(self) -> dict | None:
        """Returns the GPU processes grouped by device uuid, or None when unknown."""
        rows = self.probe.apps()
        if rows is None:
            return None

        grouped = {}
        for cells in rows:
            try:
                pid = int(cells[0])
                mem = float(cells[1])
            except ValueError:
                continue

            grouped.setdefault(cells[2], []).append({
                "pid"   : pid,
                "mem"   : mem,
                "owner" : self.pid_owner(pid),
                "cmd"   : self._pid_cmd(pid),
            })

        return grouped

    def pid_owner(self, pid: int) -> str | None:
        """Returns the login name owning a live pid, None when it is gone or a zombie."""
        try:
            uid = os.stat(f"/proc/{pid}").st_uid
        except OSError:
            return None

        stat = ProcStats.stat(pid)
        if stat is None or stat["state"] == "Z":
            return None

        return ProcStats.username(uid)

    def _pid_cmd(self, pid: int) -> str:
        """Returns the full command line of a pid, empty when it cannot be read."""
        try:
            raw = open(f"/proc/{pid}/cmdline", "rb").read()
        except OSError:
            return ""
        return raw.replace(b"\x00", b" ").decode(errors="replace").strip()

    def gpu_occupancy(self) -> list[dict] | None:
        """Returns each GPU device with the processes holding it, None when unknown."""
        apps    = self._compute_apps()
        devices = self._gpu_devices()

        if apps is None or devices is None:
            return None
        return [{**device, "procs": apps.get(device["uuid"], [])} for device in devices]

    def _memory(self) -> dict:
        """Returns total and available memory plus swap totals, in kibibytes."""
        info = MemInfo.fields()
        if not info:
            return {}

        return {
            "total"      : info.get("MemTotal", 0),
            "available"  : info.get("MemAvailable", 0),
            "swap_total" : info.get("SwapTotal", 0),
            "swap_free"  : info.get("SwapFree", 0),
        }

    def _disk(self) -> dict:
        """Returns filesystem totals for the repository plus the latest du usage in bytes."""
        try:
            usage = shutil.disk_usage(self.paths.repo_root)
        except OSError:
            return {}

        return {
            "path"      : str(self.paths.repo_root),
            "total"     : usage.total,
            "used"      : usage.used,
            "free"      : usage.free,
            "user_path" : str(self.user_root),
            "user_used" : self.du_usage["user"],
            "repo_path" : str(self.paths.repo_root),
            "repo_used" : self.du_usage["repo"],
        }

    def _user_root(self):
        """Returns the highest ancestor of the repository still owned by this user."""
        current = self.paths.repo_root.resolve()

        while current != current.parent:
            parent = current.parent
            try:
                if os.stat(parent).st_uid != self.uid:
                    break
            except OSError:
                break
            current = parent

        return current

    def _du_loop(self) -> None:
        """Refreshes the repository and user-root disk usage every DU_REFRESH_S seconds."""
        while True:
            try:
                self.du_usage["repo"] = self._du(self.paths.repo_root)
                self.du_usage["user"] = self._du(self.user_root) if self.user_root != self.paths.repo_root else self.du_usage["repo"]
            except Exception as error:
                self.logger.error(f"disk usage sweep failed: {error}")

            time.sleep(self.DU_REFRESH_S)

    def _du(self, path) -> int | None:
        """Returns the recursive size of a path in bytes, None when du fails."""
        try:
            out = subprocess.run(["du", "-s", "--block-size=1", str(path)], capture_output=True, text=True, timeout=900)
        except (OSError, subprocess.TimeoutExpired):
            return None

        try:
            return int(out.stdout.split()[0])
        except (ValueError, IndexError):
            return None

    def _uptime(self) -> float:
        """Returns the host uptime in seconds, 0.0 when /proc/uptime cannot be read."""
        try:
            return float(open("/proc/uptime").read().split()[0])
        except (OSError, ValueError, IndexError):
            return 0.0

    def _gpu_cards(self, occupancy: list[dict]) -> list[dict]:
        """Returns one card per GPU with its telemetry and who is holding it.

        Args:
            occupancy: Devices with their compute processes, from gpu_occupancy.

        Returns:
            Cards carrying index, name, utilisation, memory, temperature and power, plus
            whether this user holds the card, whether another user does, whether a holder
            process could not be identified, and the list of holder names.
        """
        cards = []
        for device in occupancy:
            mine    = False
            others  = False
            stale   = False
            holders = []

            for proc in device["procs"]:
                owner = proc["owner"]
                if owner is None:
                    stale = True
                elif owner == self.user:
                    mine = True
                    if owner not in holders:
                        holders.append(owner)
                else:
                    others = True
                    if owner not in holders:
                        holders.append(owner)

            cards.append({
                "index"       : device["index"],
                "name"        : device["name"],
                "util"        : device["util"],
                "mem_used"    : device["mem_used"],
                "mem_total"   : device["mem_total"],
                "temp"        : device["temp"],
                "power"       : device["power"],
                "power_limit" : device["power_limit"],
                "mine"        : mine,
                "others"      : others,
                "stale"       : stale,
                "holders"     : holders,
            })
        return cards

    def _gpu_mem_by_pid(self, occupancy: list[dict]) -> dict:
        """Returns the GPU memory in MiB held per pid, summed over devices."""
        usage = {}
        for device in occupancy:
            for proc in device["procs"]:
                usage[proc["pid"]] = usage.get(proc["pid"], 0) + proc["mem"]
        return usage

    def _num(self, raw: str):
        """Returns an nvidia-smi cell as int or float, None when it is not numeric."""
        try:
            value = float(raw)
        except ValueError:
            return None
        return int(value) if value.is_integer() else value

    def snapshot(self) -> dict:
        """Returns the full host snapshot the console polls.

        Returns:
            Payload with host name and user, uptime in seconds, CPU count, total and
            per-core percentages and load averages, memory and disk usage, the GPU cards
            with a `gpus_known` flag that is False when nvidia-smi did not answer, the
            busiest owned processes, the per-user activity table and the rolling history.
        """
        occupancy = self.gpu_occupancy()
        known     = occupancy is not None
        gpu_mem   = self._gpu_mem_by_pid(occupancy) if known else {}

        with self.lock:
            cores, total = self._cpu_percents()
            procs        = self._procs(gpu_mem)

        return {
            "host"       : socket.gethostname(),
            "user"       : self.user,
            "uptime"     : self._uptime(),
            "cpu"        : {"count": os.cpu_count() or len(cores), "total": total, "cores": cores, "load": list(os.getloadavg())},
            "mem"        : self._memory(),
            "disk"       : self._disk(),
            "gpus"       : self._gpu_cards(occupancy) if known else [],
            "gpus_known" : known,
            "procs"      : procs,
            "users"      : self.users.state(),
            "history"    : self.history.state(),
        }


class SystemHistory:
    """Rolling CPU, RAM and per-GPU history sampled in the background.

    Keeps at most MAX_SAMPLES points per series at SAMPLE_PERIOD_S spacing, refreshing
    the GPU devices only every GPU_PERIOD_S seconds.

    Attributes:
        monitor: Host monitor providing the counters.
        lock: Guards the series against concurrent readers.
        prev: Previous aggregate CPU counters, for percentage deltas.
        cpu: Recent total CPU busy percentages.
        ram: Recent used-memory percentages.
        gpus: Per-device utilisation and memory-percentage series, keyed by index.
        devices: Last GPU device read, reused between GPU refreshes.
        devices_at: Monotonic time of that read.
    """

    SAMPLE_PERIOD_S = 0.5
    GPU_PERIOD_S    = 2.0
    MAX_SAMPLES     = 144

    def __init__(self, monitor: SystemMonitor) -> None:
        """Stores the monitor and creates the empty bounded series."""
        self.monitor    = monitor
        self.lock       = threading.Lock()
        self.prev       = None
        self.cpu        = deque(maxlen=self.MAX_SAMPLES)
        self.ram        = deque(maxlen=self.MAX_SAMPLES)
        self.gpus       = {}
        self.devices    = None
        self.devices_at = None

    def _cpu_percent(self) -> float:
        """Returns the total CPU busy percentage since the previous sample."""
        current   = CpuCounters.read().get("cpu")
        prev      = self.prev
        self.prev = current

        if current is None or prev is None or current[1] <= prev[1]:
            return 0.0
        return round(100.0 * (current[0] - prev[0]) / (current[1] - prev[1]), 1)

    def _ram_percent(self) -> float:
        """Returns the used share of total memory as a percentage."""
        mem = self.monitor._memory()
        if not mem.get("total"):
            return 0.0
        return round(100.0 * (mem["total"] - mem["available"]) / mem["total"], 1)

    def _devices(self) -> list[dict] | None:
        """Returns the GPU devices, re-reading them at most every GPU_PERIOD_S seconds."""
        now = time.monotonic()
        if self.devices_at is not None and now - self.devices_at < self.GPU_PERIOD_S:
            return self.devices

        self.devices_at = now
        self.devices    = self.monitor._gpu_devices()
        return self.devices

    def _track(self, key: str) -> dict:
        """Returns the utilisation and memory series of one GPU index, creating them once."""
        return self.gpus.setdefault(key, {"util": deque(maxlen=self.MAX_SAMPLES), "mem": deque(maxlen=self.MAX_SAMPLES)})

    def sample(self) -> None:
        """Appends one CPU, RAM and per-GPU point, padding unseen GPUs with zeros."""
        cpu     = self._cpu_percent()
        ram     = self._ram_percent()
        devices = self._devices()

        with self.lock:
            self.cpu.append(cpu)
            self.ram.append(ram)

            if devices is None:
                return

            sampled = set()
            for device in devices:
                if device["index"] is None:
                    continue

                key   = str(device["index"])
                track = self._track(key)
                util  = device["util"] if device["util"] is not None else 0.0
                mpct  = round(100.0 * device["mem_used"] / device["mem_total"], 1) if device["mem_total"] and device["mem_used"] is not None else 0.0
                track["util"].append(util)
                track["mem"].append(mpct)
                sampled.add(key)

            for key, track in self.gpus.items():
                if key not in sampled:
                    track["util"].append(0.0)
                    track["mem"].append(0.0)

    def state(self) -> dict:
        """Returns the sampling period, capacity and the current CPU, RAM and GPU series."""
        with self.lock:
            return {
                "period_s"    : self.SAMPLE_PERIOD_S,
                "max_samples" : self.MAX_SAMPLES,
                "cpu"         : list(self.cpu),
                "ram"         : list(self.ram),
                "gpus"        : {key: {"util": list(track["util"]), "mem": list(track["mem"])} for key, track in self.gpus.items()},
            }

    def sample_loop(self) -> None:
        """Samples every SAMPLE_PERIOD_S seconds forever, logging any sampling failure."""
        while True:
            try:
                self.sample()
            except Exception as error:
                self.monitor.logger.error(f"system history sampling failed: {error}")

            time.sleep(self.SAMPLE_PERIOD_S)


class ActiveUsers:
    """Per-user activity table sampled in the background from /proc, who and nvidia-smi.

    Attributes:
        monitor: Host monitor providing the process sweep, memory and GPU occupancy.
        lock: Guards the published rows.
        prev: Previous per-process CPU jiffies, for percentage deltas.
        prev_t: Monotonic time those counters were read at.
        rows: Latest published per-user rows.
    """

    SAMPLE_PERIOD_S = 2.0
    MIN_UID         = 1000
    CPU_FLOOR_PCT   = 1.0
    MEM_FLOOR       = 1 << 30

    def __init__(self, monitor: SystemMonitor) -> None:
        """Stores the monitor and creates the empty counters and row list."""
        self.monitor = monitor
        self.lock    = threading.Lock()
        self.prev    = {}
        self.prev_t  = 0.0
        self.rows    = []

    def _scan(self) -> tuple[dict, float]:
        """Sweeps /proc and returns per-uid aggregates with the elapsed sample interval.

        Returns:
            Tuple of the aggregates per uid (process count, attributed memory in bytes,
            CPU jiffies since the previous sweep) and the interval in seconds since that
            sweep.
        """
        now   = time.monotonic()
        dt    = now - self.prev_t
        prev  = self.prev
        cur   = {}
        users = {}

        for row in ProcSweep.rows():
            pid      = row["pid"]
            jiffies  = row["stat"]["jiffies"]
            cur[pid] = jiffies
            agg      = users.setdefault(row["uid"], {"nproc": 0, "mem": 0, "jdelta": 0})

            agg["nproc"] += 1
            agg["mem"]   += row["attributed"] or 0
            if pid in prev:
                agg["jdelta"] += max(0, jiffies - prev[pid])

        self.prev   = cur
        self.prev_t = now
        return users, dt

    def _sessions(self) -> dict:
        """Returns the number of interactive login sessions per user, from who."""
        try:
            out = subprocess.run(["who"], capture_output=True, text=True, timeout=3)
        except (OSError, subprocess.TimeoutExpired):
            return {}

        if out.returncode != 0:
            return {}

        counts = {}
        for line in out.stdout.splitlines():
            parts = line.split()
            if parts:
                counts[parts[0]] = counts.get(parts[0], 0) + 1
        return counts

    def _gpu_by_user(self) -> dict:
        """Returns the GPU memory in MiB and the device indices held per user."""
        occupancy = self.monitor.gpu_occupancy()
        if occupancy is None:
            return {}

        usage = {}
        for device in occupancy:
            for proc in device["procs"]:
                if proc["owner"] is None:
                    continue
                held         = usage.setdefault(proc["owner"], {"mem": 0.0, "gpus": set()})
                held["mem"] += proc["mem"]
                held["gpus"].add(device["index"])
        return usage

    def _rows(self, users: dict, dt: float, sessions: dict, gpu: dict) -> list[dict]:
        """Builds the per-user rows, dropping idle system accounts.

        An account below MIN_UID is kept only when it has a login session, at least
        CPU_FLOOR_PCT of CPU, GPU memory, or MEM_FLOOR bytes of attributed memory.

        Args:
            users: Per-uid aggregates from the process sweep.
            dt: Seconds elapsed since the previous sweep.
            sessions: Login-session count per user name.
            gpu: GPU memory and device indices per user name.

        Returns:
            Rows with user name and uid, whether it is this user, session and process
            counts, CPU percentage, attributed memory and its share of used memory, GPU
            memory and the held device indices, sorted by CPU, then GPU, then memory.
        """
        memory   = self.monitor._memory()
        mem_used = max(0, memory.get("total", 0) - memory.get("available", 0))
        rows     = []

        for uid, agg in users.items():
            name = ProcStats.username(uid)
            held = gpu.get(name, {"mem": 0.0, "gpus": set()})
            sess = sessions.get(name, 0)
            cpu  = round(100.0 * agg["jdelta"] / self.monitor.clk / dt, 1) if dt > 0 else 0.0

            if sess == 0 and uid < self.MIN_UID and cpu < self.CPU_FLOOR_PCT and held["mem"] <= 0 and agg["mem"] < self.MEM_FLOOR:
                continue

            rows.append({
                "user"      : name,
                "uid"       : uid,
                "me"        : uid == self.monitor.uid,
                "sessions"  : sess,
                "nproc"     : agg["nproc"],
                "cpu"       : cpu,
                "mem"       : agg["mem"],
                "mem_share" : min(100.0, round(100.0 * agg["mem"] / mem_used, 1)) if mem_used else 0.0,
                "gpu_mem"   : held["mem"],
                "gpus"      : sorted(index for index in held["gpus"] if index is not None),
            })

        rows.sort(key=lambda r: (-r["cpu"], -r["gpu_mem"], -r["mem"]))
        return rows

    def sample(self) -> None:
        """Rebuilds and publishes the per-user rows from one sweep."""
        users, dt = self._scan()
        rows      = self._rows(users, dt, self._sessions(), self._gpu_by_user())

        with self.lock:
            self.rows = rows

    def state(self) -> list[dict]:
        """Returns a copy of the latest per-user rows."""
        with self.lock:
            return [dict(row) for row in self.rows]

    def sample_loop(self) -> None:
        """Samples every SAMPLE_PERIOD_S seconds forever, logging any sampling failure."""
        while True:
            try:
                self.sample()
            except Exception as error:
                self.monitor.logger.error(f"active users sampling failed: {error}")

            time.sleep(self.SAMPLE_PERIOD_S)
