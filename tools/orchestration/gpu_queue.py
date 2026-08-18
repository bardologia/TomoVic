"""Scheduler that runs subprocess jobs across a live-editable pool of GPUs.

Holds the job and result records, the JSON pool file that lets an operator
resize the device set while an experiment runs, the progress file consumed by
the web UI, and the queue itself, which launches one worker per free device and
reaps them as they exit.
"""

from __future__ import annotations

import json
import signal
import subprocess
import sys
import time
from collections import Counter
from dataclasses import dataclass
from datetime    import datetime, timedelta
from pathlib     import Path

from tools.data.io           import FileIO
from tools.monitoring.logger import Logger


@dataclass
class GpuJob:
    """One queued subprocess to run on a single GPU.

    Attributes:
        name: Unit name used in logs and results.
        command: Argument vector; the queue appends --gpu <id> at launch.
        log_path: File that receives the worker's merged stdout and stderr.
    """

    name     : str
    command  : list[str]
    log_path : Path


@dataclass
class GpuJobResult:
    """Outcome of one finished GPU job.

    Attributes:
        name: Unit name of the job.
        gpu: Device index the job ran on.
        status: Either DONE or FAILED.
        returncode: Process exit code.
        duration_s: Wall-clock runtime in seconds.
        log_file: Path of the worker log, used as the job's identity key.
    """

    name       : str
    gpu        : int
    status     : str
    returncode : int
    duration_s : float
    log_file   : str


class GpuPoolFile:
    """JSON file through which the GPU pool can be resized while jobs run.

    Attributes:
        path: Location of the pool file.
        logger: Logger used to announce the file and reject malformed edits.
        stamp: Modification time in nanoseconds of the last payload this object read.
    """

    FILE_NAME = "gpu_pool.json"

    def __init__(self, path: Path, logger: Logger) -> None:
        """Initializes the pool file handle with no observed modification stamp."""
        self.path   = Path(path)
        self.logger = logger
        self.stamp  : int | None = None

    @classmethod
    def resolve(cls, configured: str, run_dir: Path) -> Path:
        """Returns the configured pool path, or the default file inside the run directory."""
        return Path(configured) if configured else Path(run_dir) / cls.FILE_NAME

    def _stamp(self) -> int | None:
        """Returns the file's modification time in nanoseconds, or None when absent."""
        return self.path.stat().st_mtime_ns if self.path.exists() else None

    def write(self, gpus: list[int]) -> None:
        """Atomically writes the device list and remembers the resulting stamp."""
        FileIO.save_json({"gpus": list(gpus)}, self.path, indent=2, atomic=True)
        self.stamp = self._stamp()

    def seed(self, gpus: list[int]) -> None:
        """Writes the initial device list and tells the operator the file is editable."""
        self.write(gpus)
        self.logger.info(f"GPU pool is live-editable at {self.path} — write {{\"gpus\": [...]}} to resize this experiment while it runs")

    @staticmethod
    def validate(payload) -> list[int]:
        """Returns the device list held by a pool payload after checking its shape.

        Args:
            payload: Object decoded from the pool file.

        Returns:
            The requested device indices in the order given.

        Raises:
            ValueError: If the payload is not an object with a 'gpus' list of
                distinct non-negative integers.
        """
        if not isinstance(payload, dict) or "gpus" not in payload:
            raise ValueError(f"expected an object holding a 'gpus' key, got {payload!r}")

        requested = payload["gpus"]

        if not isinstance(requested, list):
            raise ValueError(f"'gpus' must be a list of device ids, got {requested!r}")

        invalid = [gpu for gpu in requested if isinstance(gpu, bool) or not isinstance(gpu, int) or gpu < 0]
        if invalid:
            raise ValueError(f"'gpus' must hold non-negative integers, got {invalid}")

        duplicates = sorted({gpu for gpu in requested if requested.count(gpu) > 1})
        if duplicates:
            raise ValueError(f"'gpus' must not repeat a device, duplicated: {duplicates}")

        return list(requested)

    def requested(self) -> list[int] | None:
        """Returns the device list from a newly modified pool file, else None.

        Returns:
            The validated device indices when the file changed since the last
            read, or None when it is unchanged, missing, or the edit was rejected.
        """
        stamp = self._stamp()

        if stamp is None or stamp == self.stamp:
            return None

        self.stamp = stamp

        try:
            return self.validate(FileIO.load_json(self.path))
        except (ValueError, TypeError, json.JSONDecodeError, OSError) as error:
            self.logger.error(f"Rejected the GPU pool edit in {self.path}: {error}. The pool is unchanged; fix the file to resize the experiment.")
            return None


class GpuProgressFile:
    """Per-unit progress ledger written beside the pool file for live monitoring.

    Tracks how many units are done or failed, averages their durations to project
    an ETA, and carries forward entries from a previous launch that are no longer
    part of the current job list.

    Attributes:
        path: Location of the progress JSON.
        total: Number of units in the current launch.
        units: Per-unit state keyed by log path.
        prior_units: Entries retained from an earlier progress file.
        durations: Completed unit runtimes in seconds.
        done: Count of units that exited successfully.
        failed: Count of units that exited non-zero.
        failed_units: Names of the failed units.
    """

    SUFFIX           = "_progress.json"
    WRITE_INTERVAL_S = 15.0
    TERMINAL         = ("done", "failed", "stale")

    def __init__(self, path: Path, jobs: list[GpuJob], logger: Logger) -> None:
        """Seeds a queued entry per job and folds in any prior progress file.

        Args:
            path: Location the progress JSON is written to.
            jobs: Units of this launch; their log paths key the ledger.
            logger: Logger used for the periodic progress lines.

        Raises:
            ValueError: If two jobs share a log path, or the existing progress
                file predates per-unit tracking.
        """
        self.path          = Path(path)
        self.total         = len(jobs)
        self.logger        = logger
        self.started_mono  = time.monotonic()
        self.started_at    = datetime.now()
        self.durations     : list[float] = []
        self.done          = 0
        self.failed        = 0
        self.failed_units  : list[str] = []
        self.last_write    = float("-inf")
        self.written_units = None

        self._reject_duplicate_logs(jobs)

        self.units       = {str(job.log_path): self._fresh_unit(job) for job in jobs}
        self.prior_units = self._load_prior(set(self.units))

    @staticmethod
    def _reject_duplicate_logs(jobs: list[GpuJob]) -> None:
        """Raises when two queued units would write to the same log path.

        Args:
            jobs: Units about to be queued.

        Raises:
            ValueError: If any log path is claimed by more than one unit.
        """
        counts     = Counter(str(job.log_path) for job in jobs)
        duplicates = sorted(log for log, count in counts.items() if count > 1)

        if duplicates:
            raise ValueError(f"Queued units share log path(s): {', '.join(duplicates)}. Two units writing the same log file would overwrite each other's output and collapse into a single progress entry — rename the runs so their log paths differ")

    @classmethod
    def resolve(cls, pool_file: Path) -> Path:
        """Returns the progress path derived from the pool file's stem."""
        pool = Path(pool_file)
        return pool.with_name(pool.stem + cls.SUFFIX)

    @staticmethod
    def _fresh_unit(job: GpuJob) -> dict:
        """Returns the queued-state ledger entry for a job."""
        return {"name": job.name, "log": str(job.log_path), "status": "queued", "gpu": None, "duration_s": None, "returncode": None}

    def _load_prior(self, current: set[str]) -> list[dict]:
        """Returns entries of an earlier progress file that this launch does not cover.

        Args:
            current: Log paths owned by the current launch.

        Returns:
            Prior unit entries, with any non-terminal status rewritten to 'stale'.

        Raises:
            ValueError: If the existing file lacks the 'units' key.
        """
        if not self.path.exists():
            return []

        payload = FileIO.load_json(self.path)
        if "units" not in payload:
            raise ValueError(f"progress file {self.path} predates per-unit tracking — delete it and relaunch")

        prior = [dict(unit) for unit in payload["units"] if unit["log"] not in current]
        for unit in prior:
            if unit["status"] not in self.TERMINAL:
                unit["status"] = "stale"

        return prior

    @property
    def completed(self) -> int:
        """Number of units that have finished, successfully or not."""
        return self.done + self.failed

    def record(self, result: GpuJobResult) -> None:
        """Folds one finished job into the ledger, counters and duration history.

        Args:
            result: Outcome whose log_file identifies the ledger entry to update.
        """
        unit               = self.units[result.log_file]
        unit["status"]     = "done" if result.status == "DONE" else "failed"
        unit["gpu"]        = result.gpu
        unit["duration_s"] = round(result.duration_s, 1)
        unit["returncode"] = result.returncode

        if result.status == "DONE":
            self.done += 1
        else:
            self.failed += 1
            self.failed_units.append(result.name)

        self.durations.append(result.duration_s)

    def _average_s(self) -> float | None:
        """Returns the mean runtime of finished units in seconds, or None when none finished."""
        return sum(self.durations) / len(self.durations) if self.durations else None

    def _eta_s(self, running: list[dict], queued: int, workers: int) -> float | None:
        """Projects the seconds left from the mean unit runtime and the in-flight elapsed times.

        Args:
            running: In-flight unit snapshots carrying an elapsed_s field.
            queued: Number of units not yet started.
            workers: Effective parallelism used to spread the remaining work.

        Returns:
            Estimated seconds to completion, or None before any unit has finished.
        """
        average = self._average_s()
        if average is None:
            return None

        remaining = [max(average - unit["elapsed_s"], 0.0) for unit in running]
        pooled    = (queued * average + sum(remaining)) / max(workers, 1)

        return max(pooled, max(remaining, default=0.0))

    def _unit_states(self, running: list[dict]) -> list[dict]:
        """Returns prior plus current unit entries, promoting in-flight units to 'running'."""
        live = {unit["log"]: unit for unit in running}

        states = []
        for log, unit in self.units.items():
            state = dict(unit)
            if state["status"] == "queued" and log in live:
                state["status"] = "running"
                state["gpu"]    = live[log]["gpu"]
            states.append(state)

        return self.prior_units + states

    def snapshot(self, running: list[dict], queued: int, workers: int) -> dict:
        """Builds the progress payload published for monitors.

        Args:
            running: In-flight unit snapshots with name, gpu, log and elapsed_s.
            queued: Number of units not yet started.
            workers: Effective parallelism used for the ETA.

        Returns:
            Mapping with the counters, per-unit states, average and elapsed
            seconds, ETA, and ISO timestamps for start, projected finish and update.
        """
        elapsed = time.monotonic() - self.started_mono
        eta     = self._eta_s(running, queued, workers)

        return {
            "total"        : self.total,
            "done"         : self.done,
            "failed"       : self.failed,
            "queued"       : queued,
            "running"      : running,
            "workers"      : workers,
            "units"        : self._unit_states(running),
            "failed_units" : list(self.failed_units),
            "average_s"    : self._average_s(),
            "elapsed_s"    : elapsed,
            "eta_s"        : eta,
            "total_s"      : elapsed + eta if eta is not None else None,
            "started_at"   : self.started_at.isoformat(timespec="seconds"),
            "finish_at"    : (datetime.now() + timedelta(seconds=eta)).isoformat(timespec="seconds") if eta is not None else None,
            "updated_at"   : datetime.now().isoformat(timespec="seconds"),
        }

    def _label(self, seconds: float) -> str:
        """Returns a duration rendered as hours and minutes, minutes, or '<1 min'."""
        minutes, _     = divmod(int(seconds), 60)
        hours, minutes = divmod(minutes, 60)

        if hours:
            return f"{hours}h {minutes:02d}m"
        if minutes:
            return f"{minutes} min"
        return "<1 min"

    def log_progress(self, snapshot: dict) -> None:
        """Logs the completed share with the average unit time, ETA and finish clock time.

        Args:
            snapshot: Payload returned by snapshot.
        """
        share  = f"[{self.completed}/{self.total}]"
        failed = f" · {self.failed} FAILED" if self.failed else ""

        if snapshot["eta_s"] is None:
            self.logger.info(f"{share} units finished{failed}")
            return

        average = self._label(snapshot["average_s"])
        eta     = self._label(snapshot["eta_s"])
        finish  = snapshot["finish_at"][11:16]

        self.logger.info(f"{share} avg {average}/unit · ETA {eta} · finish ≈ {finish}{failed}")

    def write(self, snapshot: dict, force: bool = False) -> None:
        """Writes the snapshot unless the unit states are unchanged inside the write interval.

        Args:
            snapshot: Payload returned by snapshot.
            force: Writes regardless of the throttle when True.
        """
        signature = tuple((unit["log"], unit["status"]) for unit in snapshot["units"])
        now       = time.monotonic()

        if not force and signature == self.written_units and now - self.last_write < self.WRITE_INTERVAL_S:
            return

        self.last_write    = now
        self.written_units = signature
        FileIO.save_json(snapshot, self.path, indent=2, atomic=True)


class GpuQueue:
    """Runs a job list across a GPU pool, one subprocess per free device.

    Attributes:
        gpus: Device indices the pool starts with.
        logger: Logger for launch, completion and pool-resize messages.
        poll_interval_s: Seconds between reap and dispatch sweeps.
        handle_signals: Whether SIGTERM and SIGINT are trapped to kill workers.
        terminate_deadline_s: Grace period before a worker is killed outright.
        pool: Optional live-editable pool file, or None for a fixed pool.
        progress: Progress ledger, created once jobs are queued.
        running: In-flight records holding the job, gpu, process, log handle and start time.
        retiring: Devices removed from the pool that still hold a job in flight.
    """

    EMPTY_POOL_MESSAGE = "at least one GPU id is required; an empty gpus list would poll forever without launching any job"

    def __init__(self, gpus: list[int], logger: Logger, poll_interval_s: float = 5.0, handle_signals: bool = True, terminate_deadline_s: float = 30.0, pool_file: Path | None = None) -> None:
        """Initializes the scheduler over a non-empty device pool.

        Args:
            gpus: Device indices available at launch.
            logger: Logger for scheduling messages.
            poll_interval_s: Seconds slept between scheduling sweeps.
            handle_signals: Traps SIGTERM and SIGINT to terminate workers when True.
            terminate_deadline_s: Seconds a worker gets to exit before being killed.
            pool_file: Path of the live-editable pool file, or None to keep the pool fixed.

        Raises:
            ValueError: If gpus is empty, which would poll forever without launching.
        """
        if not gpus:
            raise ValueError(f"GpuQueue requires {self.EMPTY_POOL_MESSAGE}.")

        self.gpus                 = list(gpus)
        self.logger               = logger
        self.poll_interval_s      = poll_interval_s
        self.handle_signals       = handle_signals
        self.terminate_deadline_s = terminate_deadline_s
        self.pool                 = GpuPoolFile(pool_file, logger) if pool_file is not None else None
        self.progress             : GpuProgressFile | None = None
        self.running              : list[dict] = []
        self.retiring             : set[int] = set()

    def _install_signal_handlers(self) -> dict:
        """Traps SIGTERM and SIGINT and returns the handlers that were replaced."""
        previous = {
            signal.SIGTERM : signal.getsignal(signal.SIGTERM),
            signal.SIGINT  : signal.getsignal(signal.SIGINT),
        }

        signal.signal(signal.SIGTERM, self._terminate_running)
        signal.signal(signal.SIGINT,  self._terminate_running)

        return previous

    def _shutdown_running(self) -> int:
        """Terminates every in-flight worker, killing those past the deadline.

        Returns:
            Number of workers that were shut down.
        """
        for record in self.running:
            if record["process"].poll() is None:
                record["process"].terminate()

        deadline = time.time() + self.terminate_deadline_s
        for record in self.running:
            try:
                record["process"].wait(timeout=max(0.1, deadline - time.time()))
            except subprocess.TimeoutExpired:
                record["process"].kill()

            record["log_fh"].close()

        terminated   = len(self.running)
        self.running = []

        return terminated

    def _terminate_running(self, signum, frame) -> None:
        """Signal handler that stops all workers and exits with 128 plus the signal number.

        Args:
            signum: Signal number received.
            frame: Interrupted stack frame, unused.

        Raises:
            SystemExit: Always, with status 128 + signum.
        """
        terminated = self._shutdown_running()

        self.logger.warning(f"Received signal {signum} — terminated {terminated} workers, resume with --resume")

        sys.exit(128 + signum)

    def _reap(self, running: list[dict], gpu_pool: list[int], results: list[GpuJobResult]) -> None:
        """Collects exited workers, appends their results and frees their devices.

        Args:
            running: In-flight records, mutated in place as workers finish.
            gpu_pool: Free device list, extended with each released device unless
                that device is retiring.
            results: Result list appended to for every finished job.
        """
        finished = [record for record in running if record["process"].poll() is not None]

        for record in finished:
            running.remove(record)
            record["log_fh"].close()

            job        = record["job"]
            returncode = record["process"].returncode
            status     = "DONE" if returncode == 0 else "FAILED"
            duration_s = time.monotonic() - record["started"]

            if returncode == 0:
                self.logger.info(f"[GPU {record['gpu']}] finished  {job.name}  ({duration_s / 60:.1f} min)")
            else:
                self.logger.error(f"[GPU {record['gpu']}] failed    {job.name}  (exit {returncode}, see {job.log_path})")

            results.append(GpuJobResult(
                name       = job.name,
                gpu        = record["gpu"],
                status     = status,
                returncode = returncode,
                duration_s = duration_s,
                log_file   = str(job.log_path),
            ))

            if record["gpu"] in self.retiring:
                self.retiring.discard(record["gpu"])
                self.logger.info(f"[GPU {record['gpu']}] drained — released from the pool")
                continue

            gpu_pool.append(record["gpu"])

    def _reconcile(self, gpu_pool: list[int], queue: list[GpuJob]) -> None:
        """Applies a pending pool-file edit to the free pool and the retiring set.

        Args:
            gpu_pool: Free device list, mutated to match the requested pool.
            queue: Pending jobs, used only for the resize log lines.
        """
        if self.pool is None:
            return

        requested = self.pool.requested()
        if requested is None:
            return

        busy    = [record["gpu"] for record in self.running]
        active  = set(gpu_pool) | set(busy)
        added   = sorted(set(requested) - active)
        removed = sorted(active - set(requested))

        gpu_pool.extend(added)
        gpu_pool.sort()

        for gpu in removed:
            if gpu in gpu_pool:
                gpu_pool.remove(gpu)

        self.retiring |= set(removed) & set(busy)
        self.retiring -= set(requested)

        self._log_resize(added, removed, gpu_pool, queue)

    def _log_resize(self, added: list[int], removed: list[int], gpu_pool: list[int], queue: list[GpuJob]) -> None:
        """Reports which devices joined, were released immediately, or are draining.

        Args:
            added: Devices newly admitted to the pool.
            removed: Devices dropped from the pool.
            gpu_pool: Free device list after the resize.
            queue: Pending jobs, reported when the pool has gone empty.
        """
        if not added and not removed:
            return

        if added:
            self.logger.info(f"GPU pool grew by {added} — {len(queue)} jobs still queued")

        draining = sorted(self.retiring)
        released = [gpu for gpu in removed if gpu not in self.retiring]

        if released:
            self.logger.info(f"GPU pool released {released} — idle, no longer used")

        if draining:
            self.logger.info(f"GPU pool retiring {draining} — released once the job in flight finishes")

        if not gpu_pool and not self.running:
            self.logger.warning(f"GPU pool is empty — {len(queue)} jobs parked until a device is added back to {self.pool.path}")

    def _launch(self, job: GpuJob, gpu_id: int) -> dict:
        """Starts one worker subprocess pinned to a device.

        Args:
            job: Unit to run; its command receives --gpu <gpu_id>.
            gpu_id: Device index passed to the worker.

        Returns:
            In-flight record with the job, gpu, process, open log handle and
            monotonic start time.
        """
        job.log_path.parent.mkdir(parents=True, exist_ok=True)

        command = job.command + ["--gpu", str(gpu_id)]
        log_fh  = open(job.log_path, "w", encoding="utf-8")

        try:
            process = subprocess.Popen(command, stdout=log_fh, stderr=log_fh)
        except BaseException:
            log_fh.close()
            raise

        self.logger.info(f"[GPU {gpu_id}] started   {job.name}")

        return {"job": job, "gpu": gpu_id, "process": process, "log_fh": log_fh, "started": time.monotonic()}

    def _publish_progress(self, queue: list[GpuJob], gpu_pool: list[int], results: list[GpuJobResult]) -> None:
        """Records newly finished jobs and writes a progress snapshot.

        Args:
            queue: Jobs still waiting for a device.
            gpu_pool: Free devices, counted towards the effective worker count.
            results: All results so far; those past the ledger's count are recorded.
        """
        if self.progress is None:
            return

        announce = len(results) > self.progress.completed
        for result in results[self.progress.completed:]:
            self.progress.record(result)

        running  = [{"name": record["job"].name, "gpu": record["gpu"], "log": str(record["job"].log_path), "elapsed_s": round(time.monotonic() - record["started"], 1)} for record in self.running]
        workers  = max(1, len(gpu_pool) + len(self.running) - len(self.retiring))
        snapshot = self.progress.snapshot(running, len(queue), workers)

        if announce:
            self.progress.log_progress(snapshot)

        self.progress.write(snapshot, force=announce)

    def _restore_signal_handlers(self, previous: dict) -> None:
        """Reinstates the signal handlers that were in place before the run."""
        for signum, handler in previous.items():
            signal.signal(signum, handler)

    def run(self, jobs: list[GpuJob]) -> list[GpuJobResult]:
        """Schedules every job across the pool and returns their outcomes.

        Reaps finished workers, honours pool-file resizes, dispatches queued jobs
        onto free devices and publishes progress once per poll interval, until
        nothing is queued or in flight. Any worker still running when the loop
        aborts is terminated so no unsupervised job keeps holding a GPU.

        Args:
            jobs: Units to run, dispatched in list order.

        Returns:
            One result per job, in completion order.
        """
        queue    = list(jobs)
        gpu_pool = list(self.gpus)
        results  : list[GpuJobResult] = []

        self.running  = []
        self.retiring = set()

        if self.pool is not None and jobs:
            self.pool.seed(self.gpus)
            self.progress = GpuProgressFile(GpuProgressFile.resolve(self.pool.path), jobs, self.logger)

        previous_handlers = self._install_signal_handlers() if self.handle_signals else {}

        try:
            while queue or self.running:
                self._reap(self.running, gpu_pool, results)
                self._reconcile(gpu_pool, queue)

                while queue and gpu_pool:
                    job    = queue.pop(0)
                    gpu_id = gpu_pool.pop(0)
                    self.running.append(self._launch(job, gpu_id))

                self._publish_progress(queue, gpu_pool, results)

                if queue or self.running:
                    time.sleep(self.poll_interval_s)
        finally:
            if self.running:
                terminated = self._shutdown_running()
                self.logger.error(f"Scheduler aborted with {terminated} workers still in flight — terminated them so no unsupervised job keeps holding a GPU; resume with --resume")

            self._restore_signal_handlers(previous_handlers)

        return results
