"""Launching, tracking and terminating the console's child processes.

JobStream fans a job's output out to live viewers, LogTailer follows an on-disk
log for jobs that detached from their pipe, ProcessManager owns the job table
and the launch queue, ProcessNuke is the emergency stop for every process this
user owns, and ServerDetacher moves the web server itself off the terminal.
"""

from __future__ import annotations

import codecs
import json
import os
import queue
import re
import shlex
import signal
import subprocess
import sys
import threading
import time
import uuid
from collections import deque
from datetime    import datetime, timedelta
from functools   import partial
from pathlib     import Path
from typing      import Callable

from tools.orchestration.gpu_queue import GpuPoolFile, GpuProgressFile

from job_describer  import JobDescriber
from log_transcript import AnsiTranscript
from notifier       import JobNotifier
from proc_stats     import ProcStats
from project_paths  import ProjectPaths
from web_logger     import WebLogger


class JobStream:
    """Broadcasts one job's output events to every attached console viewer.

    A replay buffer lets a late subscriber catch up, and a viewer whose queue
    fills is truncated rather than allowed to stall the publisher.

    Attributes:
        logger: Console logger warning about truncated viewers.
        buffer: Replay buffer of the most recent events, capped at 4000.
        subscribers: Queues of the currently attached viewers.
        dropped: Total events dropped across all truncations.
        lock: Guards the buffer and the subscriber list.
    """

    QUEUE_LIMIT = 8000

    def __init__(self, logger: WebLogger) -> None:
        """Creates an empty stream with no subscribers.

        Args:
            logger: Console logger for truncation warnings.
        """
        self.logger      = logger
        self.buffer      = deque(maxlen=4000)
        self.subscribers = []
        self.dropped     = 0
        self.lock        = threading.Lock()

    def publish(self, event: dict) -> None:
        """Appends an event to the replay buffer and pushes it to every viewer.

        Args:
            event: Stream event, typically a chunk of output, a status change
                or the terminating end marker.
        """
        with self.lock:
            self.buffer.append(event)
            overflowed = 0
            for sub in list(self.subscribers):
                try:
                    sub.put_nowait(event)
                except queue.Full:
                    overflowed += self._truncate(sub, event)

            self.dropped += overflowed

        if overflowed:
            self.logger.warning(f"a console viewer fell {overflowed} events behind and was truncated; the on-disk log keeps the full output")

    def _truncate(self, sub: queue.Queue, event: dict) -> int:
        """Empties a backed-up viewer queue, marks the gap, and returns how many events were lost.

        Args:
            sub: Queue of the viewer that could not keep up.
            event: Event that overflowed the queue, re-queued after the marker.
        """
        dropped = 0

        while True:
            try:
                sub.get_nowait()
                dropped += 1
            except queue.Empty:
                break

        sub.put_nowait({"type": "chunk", "data": f"\r\n\x1b[2;31m── stream truncated: {dropped} event(s) dropped, this viewer could not keep up; the on-disk log is complete ──\x1b[0m\r\n"})
        sub.put_nowait(event)

        return dropped

    def subscribe(self) -> queue.Queue:
        """Attaches a viewer and returns its queue, pre-filled with the replay buffer."""
        sub = queue.Queue(maxsize=self.QUEUE_LIMIT)
        with self.lock:
            for event in self.buffer:
                sub.put_nowait(event)
            self.subscribers.append(sub)
        return sub

    def unsubscribe(self, sub: queue.Queue) -> None:
        """Detaches a viewer queue, ignoring one that is already gone."""
        with self.lock:
            if sub in self.subscribers:
                self.subscribers.remove(sub)


class LogTailer:
    """Follows a log file and republishes its bytes as stream chunks until the writer exits.

    Attributes:
        path: Log file being followed.
        stream: Stream the decoded text is published to.
        alive: Predicate reporting whether the writing process is still running.
        decoder: Incremental UTF-8 decoder that survives split multi-byte characters.
    """

    POLL_S      = 0.5
    READ_SIZE   = 262144
    CATCHUP_MAX = 1048576

    def __init__(self, path: Path, stream: JobStream, alive: Callable[[], bool]) -> None:
        """Prepares a tailer for one log file.

        Args:
            path: Log file to follow.
            stream: Stream the output chunks are published to.
            alive: Predicate that returns False once the writer has exited.
        """
        self.path    = path
        self.stream  = stream
        self.alive   = alive
        self.decoder = codecs.getincrementaldecoder("utf-8")("replace")

    def _seek_catchup(self, handle) -> None:
        """Positions the handle at most CATCHUP_MAX bytes before the end of the file."""
        size = handle.seek(0, os.SEEK_END)
        handle.seek(max(0, size - self.CATCHUP_MAX))

    def _drain(self, handle) -> None:
        """Reads and publishes everything currently available from the handle."""
        while True:
            block = handle.read(self.READ_SIZE)
            if not block:
                return

            text = self.decoder.decode(block)
            if text:
                self.stream.publish({"type": "chunk", "data": text})

    def follow(self) -> None:
        """Tails the log until the writer exits, draining once more before returning."""
        with open(self.path, "rb") as handle:
            self._seek_catchup(handle)

            while True:
                self._drain(handle)
                if not self.alive():
                    self._drain(handle)
                    return
                time.sleep(self.POLL_S)


class ProcessManager:
    """Owns the console's job table, launch queue and live GPU pools.

    Jobs are launched immediately or queued behind the currently running one,
    can chain a follow-up script on success, and can detach into their own
    session, in which case the manager tracks the surviving pid and tails its
    log. Untracked training processes started outside the console are adopted
    into the same table.

    Attributes:
        paths: Project paths supplying the script registry and pool directory.
        logger: Console logger for launch, exit and adoption messages.
        notifier: Notifier pushed to on job start and finish.
        describer: Builds the human-readable description of a launch.
        jobs: Job records keyed by job id.
        streams: Output stream per job id.
        launch_queue: Job ids waiting for the running job to finish.
        queue_held: Job id currently blocking the queue, or None.
        lock: Guards the job table, streams and queue.
        uid: Effective user id, used to filter the process table.
        clk: Clock ticks per second, used to age processes from /proc.
        orphan_scan_t: Monotonic timestamp of the last orphan sweep.
    """

    OVERRIDE_NAME    = re.compile(r"^[A-Za-z_][A-Za-z0-9_.]*$")
    DETACHED_PID     = re.compile(r"detached .* as pid (\d+)")
    DETACHED_LOG     = re.compile(r"^output: (.+)$", re.M)
    ORPHAN_MIN_AGE_S = 15.0
    ORPHAN_RESCAN_S  = 3.0
    HISTORY_LIMIT    = 50
    LOG_VIEW_BYTES   = 4194304
    ENDED_STATES     = ("finished", "failed", "cancelled")
    POOL_SCRIPTS     = ()
    POOL_FIELD       = "gpus_file"

    def __init__(self, paths: ProjectPaths, logger: WebLogger, notifier: JobNotifier, describer: JobDescriber) -> None:
        """Creates an empty job table and reads the host constants the manager needs.

        Args:
            paths: Project paths supplying the script registry and pool directory.
            logger: Console logger for job lifecycle messages.
            notifier: Notifier pushed to on job start and finish.
            describer: Builds the description shown for each launch.
        """
        self.paths         = paths
        self.logger        = logger
        self.notifier      = notifier
        self.describer     = describer
        self.jobs          = {}
        self.streams       = {}
        self.launch_queue  = deque()
        self.queue_held    = None
        self.lock          = threading.Lock()
        self.uid           = os.getuid()
        self.clk           = os.sysconf("SC_CLK_TCK")
        self.orphan_scan_t = 0.0

    def launch(self, key: str, interpreter: str, overrides: dict | None = None, follow_up: str | None = None, detach: bool = False) -> dict:
        """Starts a script immediately and registers it in the job table.

        Args:
            key: Registered script key to run.
            interpreter: Absolute path of the Python interpreter to run it with.
            overrides: Config overrides passed as --path value argument pairs.
            follow_up: Script key to run once this one exits with code 0;
                ignored for detached launches.
            detach: Whether to pass --detach so the script re-parents itself.

        Returns:
            Mapping with "ok" True and the new "job_id", or "ok" False with an
            "error" when the script or follow-up is missing or the spawn failed.

        Raises:
            ValueError: If an override key is not a valid dotted config path.
        """
        script = self.paths.script_entry(key)["path"]
        if not script.exists():
            return {"ok": False, "error": "script not found"}

        if follow_up and not detach:
            if not self.paths.has_script(follow_up):
                return {"ok": False, "error": f"unknown follow-up script '{follow_up}'"}
            if not self.paths.script_entry(follow_up)["path"].exists():
                return {"ok": False, "error": f"follow-up script '{follow_up}' not found"}

        record = self._make_record(key, interpreter, self._clean_overrides(overrides), detach)
        stream = JobStream(self.logger)

        with self.lock:
            self.jobs[record["job_id"]]    = record
            self.streams[record["job_id"]] = stream

        error = self._start(record, stream)
        if error is not None:
            with self.lock:
                self.jobs.pop(record["job_id"], None)
                self.streams.pop(record["job_id"], None)
            return {"ok": False, "error": error}

        if follow_up and detach:
            self.logger.warning(f"follow-up {follow_up} ignored, {key} launched detached")
        elif follow_up:
            self._schedule(record, follow_up)

        return {"ok": True, "job_id": record["job_id"]}

    def enqueue(self, key: str, interpreter: str, overrides: dict | None = None, follow_up: str | None = None, detach: bool = False) -> dict:
        """Queues a script behind any running job and starts it when the queue advances.

        Args:
            key: Registered script key to run.
            interpreter: Absolute path of the Python interpreter to run it with.
            overrides: Config overrides passed as --path value argument pairs.
            follow_up: Script key to chain after this one; ignored when detached.
            detach: Whether to pass --detach so the script re-parents itself.

        Returns:
            Mapping with "ok" True, the new "job_id", and a "queued" flag that
            is False when the queue advanced far enough to start it right away;
            or "ok" False with an "error" when a script is missing.

        Raises:
            ValueError: If an override key is not a valid dotted config path.
        """
        script = self.paths.script_entry(key)["path"]
        if not script.exists():
            return {"ok": False, "error": "script not found"}

        if follow_up and detach:
            self.logger.warning(f"follow-up {follow_up} ignored, {key} queued detached")
            follow_up = None
        elif follow_up:
            if not self.paths.has_script(follow_up):
                return {"ok": False, "error": f"unknown follow-up script '{follow_up}'"}
            if not self.paths.script_entry(follow_up)["path"].exists():
                return {"ok": False, "error": f"follow-up script '{follow_up}' not found"}

        record                 = self._make_record(key, interpreter, self._clean_overrides(overrides), detach)
        record["status"]       = "queued"
        record["queue_follow"] = follow_up
        stream                 = JobStream(self.logger)

        with self.lock:
            self.jobs[record["job_id"]]    = record
            self.streams[record["job_id"]] = stream
            self.launch_queue.append(record["job_id"])
            position = len(self.launch_queue)
            blocker  = self._blocker()

        stream.publish({"type": "status", "status": "queued", "position": position, "blocker": blocker})
        self.logger.muted(f"queued {key} as job {record['job_id']} at position {position}{self._described(record)}")

        self._advance_queue()

        with self.lock:
            still_queued = record["status"] == "queued"
        return {"ok": True, "job_id": record["job_id"], "queued": still_queued}

    def _make_record(self, key: str, interpreter: str, overrides: dict, detach: bool = False) -> dict:
        """Builds a pending job record with a fresh id, rendered command and description.

        Args:
            key: Registered script key.
            interpreter: Interpreter the script will run under.
            overrides: Validated config overrides, extended with a GPU pool file
                for the scripts that support one.
            detach: Whether the launch will pass --detach.
        """
        job_id    = uuid.uuid4().hex[:12]
        overrides = self._with_pool_file(key, overrides, job_id)

        return {
            "job_id"       : job_id,
            "script"       : key,
            "command"      : self._render_command(interpreter, key, overrides, detach),
            "description"  : self.describer.describe(key, interpreter, overrides),
            "interpreter"  : interpreter,
            "overrides"    : overrides,
            "detach"       : detach,
            "status"       : "pending",
            "pid"          : None,
            "started"      : datetime.now().isoformat(timespec="seconds"),
            "exit_code"    : None,
            "follow_of"    : None,
            "follow_up"    : None,
            "queue_follow" : None,
            "adopted"      : False,
        }

    def _with_pool_file(self, key: str, overrides: dict, job_id: str) -> dict:
        """Adds a per-job live GPU pool file to the overrides of pool-aware scripts.

        Args:
            key: Registered script key.
            overrides: Overrides to extend; returned unchanged when the script
                does not support a pool or the caller already set one.
            job_id: Job id, used as the pool file name.
        """
        if key not in self.POOL_SCRIPTS or overrides.get(self.POOL_FIELD):
            return overrides

        return {**overrides, self.POOL_FIELD: str(self.paths.gpu_pools_dir / f"{job_id}.json")}

    def _runtime_env(self, interpreter: str) -> dict:
        """Builds the child environment: unbuffered coloured output at a fixed terminal size.

        The interpreter's own lib directory is prepended to LD_LIBRARY_PATH so
        environment-local shared objects resolve before the system ones.

        Args:
            interpreter: Absolute path of the interpreter the job will run under.
        """
        env = dict(os.environ)
        env["PYTHONUNBUFFERED"] = "1"
        env["FORCE_COLOR"]      = "1"
        env["COLUMNS"]          = "120"
        env["LINES"]            = "32"
        env.setdefault("QT_QPA_PLATFORM", "offscreen")

        library_dir  = os.path.join(os.path.dirname(os.path.dirname(os.path.realpath(interpreter))), "lib")
        library_path = env.get("LD_LIBRARY_PATH", "")
        if library_dir not in library_path.split(":"):
            env["LD_LIBRARY_PATH"] = library_dir + (":" + library_path if library_path else "")

        return env

    def _start(self, record: dict, stream: JobStream) -> str | None:
        """Spawns the job in its own session and starts pumping its output.

        Args:
            record: Job record to start; updated in place with the pid, the
                running status and a fresh start timestamp.
            stream: Stream the job's output is published to.

        Returns:
            None once the process is running, or the spawn error as text.
        """
        entry = self.paths.script_entry(record["script"])
        argv  = [record["interpreter"], "-u", str(entry["path"])]
        for path, value in record["overrides"].items():
            argv += [f"--{path}", value]
        if record.get("detach"):
            argv.append("--detach")

        env = self._runtime_env(record["interpreter"])

        try:
            process = subprocess.Popen(
                argv,
                cwd               = str(self.paths.repo_root),
                stdout            = subprocess.PIPE,
                stderr            = subprocess.STDOUT,
                env               = env,
                start_new_session = True,
            )
        except OSError as exc:
            return str(exc)

        with self.lock:
            record["status"]  = "running"
            record["pid"]     = process.pid
            record["started"] = datetime.now().isoformat(timespec="seconds")
            snapshot          = dict(record)

        self.logger.ok(f"launched {record['script']} as job {record['job_id']} (pid {process.pid}){self._described(record)}")
        stream.publish({"type": "status", "status": "running", "pid": process.pid})
        self.notifier.job_started(snapshot)

        worker = threading.Thread(target=self._pump, args=(record["job_id"], process, stream), daemon=True)
        worker.start()
        return None

    def _schedule(self, parent: dict, key: str) -> None:
        """Registers a scheduled follow-up job that starts when the parent exits cleanly.

        Args:
            parent: Job record the follow-up is chained to; its follow_up field
                is set to the new job id.
            key: Registered script key of the follow-up.
        """
        record              = self._make_record(key, parent["interpreter"], {})
        record["status"]    = "scheduled"
        record["follow_of"] = parent["job_id"]

        stream = JobStream(self.logger)
        stream.publish({"type": "status", "status": "scheduled", "after": parent["script"]})

        with self.lock:
            parent["follow_up"]            = record["job_id"]
            self.jobs[record["job_id"]]    = record
            self.streams[record["job_id"]] = stream

        self.logger.muted(f"scheduled {key} as job {record['job_id']} after {parent['script']} ({parent['job_id']}){self._described(record)}")

    def _described(self, record: dict) -> str:
        """Returns the job description as a log suffix, or an empty string when it has none."""
        description = record.get("description") or ""
        return f" — {description}" if description else ""

    def _resolve_follow_up(self, follow_id: str, code: int) -> None:
        """Starts or cancels a scheduled follow-up according to the parent's exit code.

        Args:
            follow_id: Job id of the scheduled follow-up.
            code: Exit code of the parent job; anything other than 0 cancels
                the follow-up.
        """
        with self.lock:
            record = self.jobs.get(follow_id)
            stream = self.streams.get(follow_id)
        if record is None or stream is None or record["status"] != "scheduled":
            return

        if code == 0:
            error = self._start(record, stream)
            if error is None:
                return
            with self.lock:
                record["status"] = "failed"
                snapshot         = dict(record)
            stream.publish({"type": "status", "status": "failed", "code": None, "verdict": "error"})
            stream.publish({"type": "end"})
            self.logger.error(f"scheduled job {follow_id} failed to start: {error}")
            self.notifier.job_finished(snapshot)
            return

        with self.lock:
            record["status"] = "cancelled"
        stream.publish({"type": "status", "status": "cancelled", "code": None})
        stream.publish({"type": "end"})
        self.logger.warning(f"scheduled job {follow_id} cancelled, parent exited with code {code}")

    def _advance_queue(self) -> None:
        """Starts the next queued job, or logs which job is holding the queue.

        Jobs that fail to spawn are marked failed and the queue keeps advancing;
        the hold message is logged only when the blocking job changes.
        """
        while True:
            with self.lock:
                blocker = self._blocker()

                if blocker is not None or not self.launch_queue:
                    held            = blocker if blocker is not None and self.launch_queue and self.queue_held != blocker["job_id"] else None
                    self.queue_held = blocker["job_id"] if blocker is not None else None
                    break

                job_id = self.launch_queue.popleft()
                record = self.jobs.get(job_id)
                stream = self.streams.get(job_id)
                if record is None or stream is None or record["status"] != "queued":
                    continue
                record["status"] = "pending"

            error = self._start(record, stream)
            if error is None:
                if record["queue_follow"]:
                    self._schedule(record, record["queue_follow"])
                return

            with self.lock:
                record["status"] = "failed"
                snapshot         = dict(record)
            stream.publish({"type": "status", "status": "failed", "code": None, "verdict": "error"})
            stream.publish({"type": "end"})
            self.logger.error(f"queued job {job_id} failed to start: {error}")
            self.notifier.job_finished(snapshot)

        if held is not None:
            origin = "adopted process" if held["adopted"] else "job"
            where  = f" (pid {held['pid']})" if held["pid"] else ""
            self.logger.muted(f"launch queue held by {origin} {held['script']}{where}")

    def _blocker(self) -> dict | None:
        """Returns a summary of the first pending or running job, or None when the host is free.

        Must be called with the lock held.
        """
        for record in self.jobs.values():
            if record["status"] in ("pending", "running"):
                return {"job_id": record["job_id"], "script": record["script"], "pid": record["pid"], "adopted": record["adopted"]}

        return None

    def _clean_overrides(self, overrides: dict | None) -> dict:
        """Validates override keys as dotted config paths and stringifies their values.

        Args:
            overrides: Raw override mapping, or None for no overrides.

        Raises:
            ValueError: If a key is not a dotted identifier path.
        """
        cleaned = {}
        for path, value in (overrides or {}).items():
            if not isinstance(path, str) or not self.OVERRIDE_NAME.match(path):
                raise ValueError(f"invalid override key '{path}'")
            cleaned[path] = str(value)
        return cleaned

    def _render_command(self, interpreter: str, key: str, overrides: dict, detach: bool = False) -> str:
        """Returns the shell-quoted command line shown for a job in the console."""
        entry = self.paths.script_entry(key)
        parts = [interpreter, "-u", entry["rel"]]
        for path, value in overrides.items():
            parts += [f"--{path}", shlex.quote(value)]
        if detach:
            parts.append("--detach")
        return " ".join(parts)

    def _pump(self, job_id: str, process: subprocess.Popen, stream: JobStream) -> None:
        """Streams a child's output until it exits, then settles the job's fate.

        For a detached launch that announced a surviving pid and exited cleanly,
        the job is handed to the detached tracker instead of being finalised.
        Otherwise the exit code decides the status, any follow-up is resolved,
        the notifier is told, and the queue and history are advanced.

        Args:
            job_id: Job the process belongs to.
            process: The spawned child, with stderr merged into stdout.
            stream: Stream the output is published to.
        """
        fd      = process.stdout.fileno()
        decoder = codecs.getincrementaldecoder("utf-8")("replace")

        with self.lock:
            detached = bool(self.jobs.get(job_id, {}).get("detach"))
        head = ""

        while True:
            chunk = os.read(fd, 4096)
            if not chunk:
                break
            text = decoder.decode(chunk)
            if text:
                stream.publish({"type": "chunk", "data": text})
                if detached and len(head) < 4096:
                    head += text

        tail = decoder.decode(b"", final=True)
        if tail:
            stream.publish({"type": "chunk", "data": tail})
            if detached and len(head) < 4096:
                head += tail

        process.wait()
        code = process.returncode

        detached_pid = self._parse_detached_pid(head) if detached else None
        if detached_pid and code == 0:
            self._adopt_detached(job_id, detached_pid, self._parse_detached_log(head), stream)
            return

        status = "finished" if code == 0 else "failed"

        with self.lock:
            record = self.jobs.get(job_id)
            if record is not None:
                record["status"]    = status
                record["exit_code"] = code
            follow_id = record["follow_up"] if record else None
            snapshot  = dict(record) if record else None

        if follow_id:
            self._resolve_follow_up(follow_id, code)

        verdict = "ok" if code == 0 else "error"
        self.logger.muted(f"job {job_id} exited with code {code}")
        stream.publish({"type": "status", "status": status, "code": code, "verdict": verdict})
        stream.publish({"type": "end"})

        if snapshot is not None:
            snapshot["progress"] = self._final_progress(job_id)
            self.notifier.job_finished(snapshot)

        self._advance_queue()
        self._prune_history()

    def _parse_detached_pid(self, text: str) -> int | None:
        """Returns the pid a detaching script announced in its output, or None."""
        match = self.DETACHED_PID.search(text)
        return int(match.group(1)) if match else None

    def _parse_detached_log(self, text: str) -> Path | None:
        """Returns the existing log file a detaching script announced, or None."""
        match = self.DETACHED_LOG.search(text)
        if match is None:
            return None

        path = Path(match.group(1).strip())
        path = path if path.is_absolute() else self.paths.repo_root / path
        return path if path.is_file() else None

    def _adopt_detached(self, job_id: str, pid: int, log: Path | None, stream: JobStream) -> None:
        """Re-points a job at the process that survived detaching and follows it.

        Args:
            job_id: Job whose record is re-pointed at the surviving process.
            pid: Pid the detaching launcher announced.
            log: Log file to tail, or None when the script announced none.
            stream: Stream the tailed output and status changes are published to.
        """
        token = self._pid_start_token(pid)

        with self.lock:
            record = self.jobs.get(job_id)
            if record is None:
                return
            record["status"]           = "running"
            record["pid"]              = pid
            record["detached_running"] = True
            record["log_path"]         = str(log) if log else None

        self.logger.ok(f"job {job_id} detached, now tracking live pid {pid}{f' and tailing {log}' if log else ''}")
        stream.publish({"type": "status", "status": "running", "pid": pid, "detached": True, "log": str(log) if log else None})

        tailer  = self._start_tailer(log, pid, token, stream)
        watcher = threading.Thread(target=self._watch_detached, args=(job_id, pid, token, stream, tailer), daemon=True)
        watcher.start()

    def _start_tailer(self, log: Path | None, pid: int, token: tuple | None, stream: JobStream) -> threading.Thread | None:
        """Starts a tailer thread for a detached job's log, or returns None when there is none.

        Args:
            log: Log file to follow, or None.
            pid: Pid whose liveness ends the tail.
            token: Start token identifying that exact process incarnation.
            stream: Stream the tailed output is published to.
        """
        if log is None:
            return None

        tailer = LogTailer(log, stream, partial(self._pid_running, pid, token))
        thread = threading.Thread(target=tailer.follow, daemon=True)
        thread.start()
        return thread

    def _watch_detached(self, job_id: str, pid: int, token: tuple | None, stream: JobStream, tailer: threading.Thread | None = None) -> None:
        """Polls a detached or adopted pid and finalises the job once it is gone.

        The exit code of such a process is not observable, so the job finishes
        with a status of "finished" and an unknown verdict.

        Args:
            job_id: Job being watched; the watch stops if its record disappears.
            pid: Pid to poll.
            token: Start token guarding against pid reuse.
            stream: Stream the closing status events are published to.
            tailer: Log tailer thread to join before finalising, if any.
        """
        while self._pid_running(pid, token):
            time.sleep(2.0)
            with self.lock:
                if self.jobs.get(job_id) is None:
                    return

        if tailer is not None:
            tailer.join(timeout=LogTailer.POLL_S * 6)

        with self.lock:
            record = self.jobs.get(job_id)
            if record is None:
                return
            record["status"]    = "finished"
            record["exit_code"] = None
            snapshot            = dict(record)

        self.logger.muted(f"detached job {job_id} (pid {pid}) exited, exit status unknown")
        stream.publish({"type": "status", "status": "finished", "code": None, "verdict": "unknown"})
        stream.publish({"type": "end"})

        snapshot["progress"] = self._final_progress(job_id)
        self.notifier.job_finished(snapshot)

        self._advance_queue()
        self._prune_history()

    def _final_progress(self, job_id: str) -> dict | None:
        """Returns the job's last progress snapshot, or None when it never wrote one."""
        info = self.progress(job_id)
        return info["progress"] if info.get("ok") and "progress" in info else None

    def _prune_history(self) -> None:
        """Drops the oldest ended jobs and their streams beyond the history limit."""
        with self.lock:
            ended   = sorted((record for record in self.jobs.values() if record["status"] in self.ENDED_STATES), key=lambda r: r["started"])
            dropped = ended[: max(0, len(ended) - self.HISTORY_LIMIT)]
            for record in dropped:
                self.jobs.pop(record["job_id"], None)
                self.streams.pop(record["job_id"], None)

        if dropped:
            self.logger.muted(f"dropped {len(dropped)} ended job(s) and their output from the console, keeping the {self.HISTORY_LIMIT} most recent")

    def adopt_orphans(self) -> int:
        """Adopts untracked project processes into the job table, rate-limited by a rescan window.

        Returns:
            Number of processes adopted, and 0 when the rescan window has not
            elapsed since the previous sweep.
        """
        now = time.monotonic()
        with self.lock:
            if now - self.orphan_scan_t < self.ORPHAN_RESCAN_S:
                return 0
            self.orphan_scan_t = now

        orphans = self._orphan_candidates()
        for pid, info in orphans.items():
            self._adopt_orphan(pid, info)
        return len(orphans)

    def _orphan_candidates(self) -> dict:
        """Finds this user's project processes that no tracked job owns.

        A candidate must be a Python process running a script under the main
        directory, older than the minimum age so a job's own children are not
        caught mid-launch, and with no tracked job among its ancestors. Children
        of other candidates are dropped so only the topmost survives.

        Returns:
            Mapping from pid to an info record with the script stem, the joined
            command line, its argument tokens, the interpreter and the age in seconds.
        """
        found   = {}
        running = self._running_pids()
        parents = {}

        for entry in os.listdir("/proc"):
            if not entry.isdigit():
                continue
            pid = int(entry)
            if pid == os.getpid():
                continue

            try:
                if os.stat(f"/proc/{pid}").st_uid != self.uid:
                    continue
                raw = open(f"/proc/{pid}/cmdline", "rb").read()
            except OSError:
                continue

            tokens = [token.decode(errors="replace") for token in raw.split(b"\x00") if token]
            if not tokens or not os.path.basename(tokens[0]).startswith("python"):
                continue

            script = self._orphan_script(pid, tokens)
            if script is None:
                continue

            age = self._pid_age_s(pid)
            if age is None or age < self.ORPHAN_MIN_AGE_S:
                continue
            if self._ancestor_match(pid, running, parents) is not None:
                continue

            found[pid] = {"script": script, "cmd": " ".join(tokens), "tokens": tokens, "interpreter": tokens[0], "age_s": age}

        known = set(found)

        return {pid: info for pid, info in found.items() if self._ancestor_match(self._parent(pid, parents), known, parents) is None}

    def _running_pids(self) -> set:
        """Returns the pids of every job the console currently tracks as running."""
        with self.lock:
            return {record["pid"] for record in self.jobs.values() if record["status"] == "running" and record["pid"] is not None}

    def _parent(self, pid: int, parents: dict) -> int:
        """Returns the parent pid, memoising the /proc lookup in the given cache."""
        if pid not in parents:
            parents[pid] = ProcStats.ppid(pid)

        return parents[pid]

    def _ancestor_match(self, pid: int, known: set, parents: dict) -> int | None:
        """Walks up the process tree for a pid in the known set.

        Args:
            pid: Pid to start from, itself included in the search.
            known: Pids to match against.
            parents: Memoisation cache of pid to parent pid.

        Returns:
            The matching ancestor pid, or None after reaching init or 16 hops.
        """
        hops = 0

        while pid > 1 and hops < 16:
            if pid in known:
                return pid
            pid   = self._parent(pid, parents)
            hops += 1

        return None

    def _orphan_script(self, pid: int, tokens: list[str]) -> str | None:
        """Returns the script stem a process is running, or None when it is not a project script.

        Relative script paths are resolved against the process's own working
        directory, and only paths under the main directory count.

        Args:
            pid: Pid whose working directory anchors a relative script path.
            tokens: The process command line, split into arguments.
        """
        for token in tokens[1:]:
            if not token.endswith(".py"):
                continue

            path = Path(token)
            if not path.is_absolute():
                try:
                    path = Path(os.readlink(f"/proc/{pid}/cwd")) / path
                except OSError:
                    return None

            try:
                path = path.resolve()
            except OSError:
                return None
            return path.stem if path.is_relative_to(self.paths.main_dir) else None
        return None

    def _pid_age_s(self, pid: int) -> float | None:
        """Returns how long a process has been alive in seconds, or None when it is gone."""
        try:
            stat   = open(f"/proc/{pid}/stat").read()
            fields = stat[stat.rindex(")") + 2 :].split()
            uptime = float(open("/proc/uptime").read().split()[0])
            return uptime - int(fields[19]) / self.clk
        except (OSError, ValueError, IndexError):
            return None

    def _orphan_overrides(self, tokens: list[str]) -> dict:
        """Recovers the config overrides an adopted process was launched with.

        Args:
            tokens: The process command line; everything after the script path
                is parsed as --name value pairs, with a bare flag read as "True".
        """
        args = []
        for index, token in enumerate(tokens):
            if token.endswith(".py"):
                args = tokens[index + 1 :]
                break

        overrides = {}
        index     = 0
        while index < len(args):
            if not args[index].startswith("--"):
                index += 1
                continue
            name = args[index][2:]
            if index + 1 < len(args) and not args[index + 1].startswith("--"):
                overrides[name] = args[index + 1]
                index += 2
            else:
                overrides[name] = "True"
                index += 1
        return overrides

    def _pid_log_path(self, pid: int) -> Path | None:
        """Returns the file a process has on stdout, or None when it is not a regular file."""
        try:
            target = Path(os.readlink(f"/proc/{pid}/fd/1"))
        except OSError:
            return None
        return target if target.is_file() else None

    def _adopt_orphan(self, pid: int, info: dict) -> None:
        """Registers an untracked process as an adopted job and starts following it.

        The start timestamp is back-dated by the process's age, the description
        is filled in on a background thread because it can be slow, and the log
        on the process's stdout is tailed when there is one.

        Args:
            pid: Pid of the untracked process.
            info: Candidate record from _orphan_candidates.
        """
        overrides = self._orphan_overrides(info["tokens"])
        log       = self._pid_log_path(pid)
        record = {
            "job_id"           : uuid.uuid4().hex[:12],
            "script"           : info["script"],
            "command"          : info["cmd"],
            "description"      : "",
            "interpreter"      : info["interpreter"],
            "overrides"        : overrides,
            "detach"           : False,
            "status"           : "running",
            "pid"              : pid,
            "started"          : (datetime.now() - timedelta(seconds=info["age_s"])).isoformat(timespec="seconds"),
            "exit_code"        : None,
            "follow_of"        : None,
            "follow_up"        : None,
            "adopted"          : True,
            "detached_running" : True,
            "log_path"         : str(log) if log else None,
        }

        stream = JobStream(self.logger)
        stream.publish({"type": "status", "status": "running", "pid": pid, "adopted": True, "log": str(log) if log else None})

        with self.lock:
            self.jobs[record["job_id"]]    = record
            self.streams[record["job_id"]] = stream

        self.logger.warning(f"adopted untracked process {info['script']} (pid {pid}) into the console{f', tailing {log}' if log else ''}")

        threading.Thread(target=self._describe_adopted, args=(record["job_id"], info, overrides), daemon=True).start()

        token   = self._pid_start_token(pid)
        tailer  = self._start_tailer(log, pid, token, stream)
        watcher = threading.Thread(target=self._watch_detached, args=(record["job_id"], pid, token, stream, tailer), daemon=True)
        watcher.start()

    def _describe_adopted(self, job_id: str, info: dict, overrides: dict) -> None:
        """Fills in an adopted job's description once the describer resolves its config."""
        description = self.describer.describe(info["script"], info["interpreter"], overrides)

        with self.lock:
            record = self.jobs.get(job_id)
            if record is not None:
                record["description"] = description

    def _pid_alive(self, pid: int) -> bool:
        """Returns whether the pid exists and has not become a zombie."""
        try:
            stat = open(f"/proc/{pid}/stat").read()
        except OSError:
            return False
        try:
            return stat[stat.rindex(")") + 2] != "Z"
        except (ValueError, IndexError):
            return False

    def _pid_running(self, pid: int, token: tuple | None) -> bool:
        """Returns whether the pid is alive and is still the same process incarnation."""
        return self._pid_alive(pid) and self._pid_start_token(pid) == token

    def _pid_start_token(self, pid: int) -> tuple | None:
        """Returns a (pid, start time) identity that changes when the pid is reused, or None."""
        try:
            stat = open(f"/proc/{pid}/stat").read()
        except OSError:
            return None
        try:
            fields = stat[stat.rindex(")") + 2 :].split()
            return (pid, fields[19])
        except (ValueError, IndexError):
            return None

    def stop(self, job_id: str) -> dict:
        """Cancels a queued or scheduled job, or sends SIGTERM to a running one's group.

        Args:
            job_id: Job to stop.

        Returns:
            Mapping with "ok" True once the job was cancelled or signalled, or
            "ok" False with an "error" when the job is unknown or already ended.
        """
        with self.lock:
            record = self.jobs.get(job_id)
            stream = self.streams.get(job_id)
        if record is None:
            return {"ok": False, "error": "unknown job"}

        if record["status"] == "queued":
            with self.lock:
                record["status"] = "cancelled"
                if job_id in self.launch_queue:
                    self.launch_queue.remove(job_id)
            if stream is not None:
                stream.publish({"type": "status", "status": "cancelled", "code": None})
                stream.publish({"type": "end"})
            self.logger.warning(f"queued job {job_id} cancelled by user")
            return {"ok": True}

        if record["status"] == "scheduled":
            with self.lock:
                record["status"] = "cancelled"
            if stream is not None:
                stream.publish({"type": "status", "status": "cancelled", "code": None})
                stream.publish({"type": "end"})
            self.logger.warning(f"scheduled job {job_id} cancelled by user")
            return {"ok": True}

        if record["status"] != "running":
            return {"ok": False, "error": "job is not running"}

        with self.lock:
            self.jobs[job_id]["stopped"] = True
        self._signal_group(record["pid"], signal.SIGTERM)
        self.logger.warning(f"stop requested for job {job_id}")
        return {"ok": True}

    def gpu_pool(self, job_id: str) -> dict:
        """Reads the live GPU pool a job dispatches over.

        Args:
            job_id: Job whose pool file is read.

        Returns:
            Mapping with "supported" False when the script has no pool, "live"
            False when the file has not appeared yet, otherwise "gpus" with the
            validated device indices; "ok" is False for an unknown job or an
            unreadable pool file.
        """
        with self.lock:
            record = self.jobs.get(job_id)

        if record is None:
            return {"ok": False, "error": "unknown job"}

        path = record["overrides"].get(self.POOL_FIELD)
        if not path:
            return {"ok": True, "supported": False, "live": False}

        pool = Path(path)
        if not pool.is_file():
            return {"ok": True, "supported": True, "live": False, "path": str(pool)}

        try:
            gpus = GpuPoolFile.validate(json.loads(pool.read_text(encoding="utf-8")))
        except (ValueError, TypeError, json.JSONDecodeError, OSError) as error:
            return {"ok": False, "error": f"unreadable GPU pool file: {error}", "path": str(pool)}

        return {"ok": True, "supported": True, "live": True, "gpus": gpus, "path": str(pool)}

    def progress(self, job_id: str) -> dict:
        """Reads the fan-out progress snapshot a job writes beside its GPU pool.

        Args:
            job_id: Job whose progress file is read.

        Returns:
            Mapping with "supported" False when the script has no pool, "live"
            False when the file is absent or the job has ended, otherwise the
            "progress" snapshot; "ok" is False for an unknown job or an
            unreadable file.
        """
        with self.lock:
            record = self.jobs.get(job_id)

        if record is None:
            return {"ok": False, "error": "unknown job"}

        path = record["overrides"].get(self.POOL_FIELD)
        if not path:
            return {"ok": True, "supported": False, "live": False}

        progress_path = GpuProgressFile.resolve(Path(path))
        if not progress_path.is_file():
            return {"ok": True, "supported": True, "live": False, "path": str(progress_path)}

        try:
            snapshot = json.loads(progress_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as error:
            return {"ok": False, "error": f"unreadable progress file: {error}", "path": str(progress_path)}

        return {"ok": True, "supported": True, "live": record["status"] == "running", "progress": snapshot, "path": str(progress_path)}

    def unit_entry(self, job_id: str, index: int) -> dict:
        """Looks up one unit of a fan-out job in its progress registry.

        Args:
            job_id: Job whose unit registry is read.
            index: Position of the unit in the registry.

        Returns:
            Mapping with "ok" True, the "unit" record and its absolute log
            "path", or "ok" False with an "error" when the job has no snapshot,
            the snapshot predates the unit registry, or the index is out of range.
        """
        info = self.progress(job_id)
        if not info.get("ok"):
            return info
        if "progress" not in info:
            return {"ok": False, "error": "this job has no progress snapshot yet — units appear once the fan-out starts dispatching"}

        units = info["progress"].get("units")
        if units is None:
            return {"ok": False, "error": "this progress snapshot has no unit registry — it was written by an older run"}
        if not 0 <= index < len(units):
            return {"ok": False, "error": f"unit index {index} is out of range, the registry holds {len(units)} units"}

        unit = units[index]
        path = Path(unit["log"])
        path = path if path.is_absolute() else self.paths.repo_root / path
        return {"ok": True, "unit": unit, "path": path}

    def _unit_live(self, job_id: str, index: int, stop: threading.Event) -> bool:
        """Returns whether a unit's log is still worth tailing.

        Args:
            job_id: Job the unit belongs to.
            index: Unit position in the registry.
            stop: Event the viewer sets to abandon the tail.
        """
        if stop.is_set():
            return False

        with self.lock:
            record = self.jobs.get(job_id)
        if record is None or record["status"] != "running":
            return False

        entry = self.unit_entry(job_id, index)
        return entry.get("ok", False) and entry["unit"]["status"] in ("queued", "running")

    def unit_stream(self, job_id: str, index: int) -> dict:
        """Opens a live stream over one fan-out unit's log.

        Args:
            job_id: Job the unit belongs to.
            index: Unit position in the registry.

        Returns:
            Mapping with "ok" True, the "stream" carrying the unit header and
            its output, and a "stop" event the viewer sets to end the tail; a
            unit whose log does not exist yet yields a closed stream. Returns
            the lookup error when the unit cannot be resolved.
        """
        entry = self.unit_entry(job_id, index)
        if not entry.get("ok"):
            return entry

        unit   = entry["unit"]
        path   = entry["path"]
        stream = JobStream(self.logger)
        stop   = threading.Event()

        stream.publish({"type": "unit", "name": unit["name"], "log": str(path), "status": unit["status"], "gpu": unit["gpu"]})

        if not path.is_file():
            stream.publish({"type": "status", "status": unit["status"], "code": None, "missing": True})
            stream.publish({"type": "end"})
            return {"ok": True, "stream": stream, "stop": stop}

        worker = threading.Thread(target=self._follow_unit, args=(job_id, index, path, stream, stop), daemon=True)
        worker.start()
        return {"ok": True, "stream": stream, "stop": stop}

    def _follow_unit(self, job_id: str, index: int, path: Path, stream: JobStream, stop: threading.Event) -> None:
        """Tails one unit's log, then publishes its final status and closes the stream.

        Args:
            job_id: Job the unit belongs to.
            index: Unit position in the registry.
            path: Log file to tail.
            stream: Stream the output and closing events are published to.
            stop: Event the viewer sets to end the tail early.
        """
        LogTailer(path, stream, partial(self._unit_live, job_id, index, stop)).follow()

        entry = self.unit_entry(job_id, index)
        unit  = entry["unit"] if entry.get("ok") else {}
        stream.publish({"type": "status", "status": unit.get("status", "unknown"), "code": unit.get("returncode")})
        stream.publish({"type": "end"})

    def job_log(self, job_id: str, unit: int | None = None) -> dict:
        """Reads the tail of a job's log file, or of one of its fan-out units.

        Args:
            job_id: Job whose log is read.
            unit: Unit index to read instead of the job's own log, or None.

        Returns:
            Mapping with "available" True and the flattened "text" of the last
            LOG_VIEW_BYTES bytes plus the full "size" and a "truncated" flag;
            "available" False with a "reason" when the job writes to a pipe or
            the unit has not started; "ok" False when the job is unknown or the
            log file has disappeared.
        """
        with self.lock:
            record = self.jobs.get(job_id)

        if record is None:
            return {"ok": False, "error": "unknown job"}

        if unit is None:
            path = record.get("log_path")
            if not path:
                return {"ok": True, "available": False, "reason": "this job writes to a pipe or a terminal, not to a log file"}
            target = Path(path)
        else:
            entry = self.unit_entry(job_id, unit)
            if not entry.get("ok"):
                return entry
            target = entry["path"]
            if not target.is_file():
                return {"ok": True, "available": False, "reason": f"{entry['unit']['name']} has not started yet — its log file does not exist"}

        if not target.is_file():
            return {"ok": False, "error": f"log file is gone: {target}", "path": str(target)}

        size = target.stat().st_size
        with open(target, "rb") as handle:
            handle.seek(max(0, size - self.LOG_VIEW_BYTES))
            raw = handle.read()

        return {
            "ok"        : True,
            "available" : True,
            "path"      : str(target),
            "size"      : size,
            "shown"     : len(raw),
            "truncated" : size > self.LOG_VIEW_BYTES,
            "text"      : AnsiTranscript().flatten(raw.decode("utf-8", errors="replace")),
        }

    def set_gpus(self, job_id: str, gpus, park: bool = False) -> dict:
        """Rewrites a running job's live GPU pool, optionally parking it on none.

        Runs already in flight finish on their current device; the new pool only
        governs what the job dispatches next.

        Args:
            job_id: Running job whose pool is rewritten.
            gpus: Requested device indices, validated before being written.
            park: Whether an empty selection is an intentional park rather than
                a mistake.

        Returns:
            Mapping with "ok" True, the written "gpus" and a "parked" flag, or
            "ok" False with an "error" when the job is unknown, not running,
            has no pool, or the selection is invalid.
        """
        with self.lock:
            record = self.jobs.get(job_id)

        if record is None:
            return {"ok": False, "error": "unknown job"}

        if record["status"] != "running":
            return {"ok": False, "error": "job is not running"}

        path = record["overrides"].get(self.POOL_FIELD)
        if not path:
            return {"ok": False, "error": f"{record['script']} was not launched with a live GPU pool"}

        pool = Path(path)
        if not pool.is_file():
            return {"ok": False, "error": "this job has no live GPU pool yet; the pool appears once a fan-out over trials or seeds starts dispatching"}

        try:
            requested = GpuPoolFile.validate({"gpus": gpus})
        except (ValueError, TypeError) as error:
            return {"ok": False, "error": str(error)}

        if not requested and not park:
            return {"ok": False, "error": "select at least one GPU, or confirm parking to hold the experiment"}

        GpuPoolFile(pool, self.logger).write(requested)

        if requested:
            self.logger.ok(f"job {job_id} GPU pool set to {requested}")
        else:
            self.logger.warning(f"job {job_id} parked — no GPUs left in the pool, runs in flight will finish and nothing new starts")

        return {"ok": True, "gpus": requested, "parked": not requested}

    def clear_queue(self) -> int:
        """Cancels every queued job and returns how many were dropped."""
        with self.lock:
            pending = [self.jobs[job_id] for job_id in self.launch_queue if job_id in self.jobs]
            streams = [self.streams.get(record["job_id"]) for record in pending]
            self.launch_queue.clear()
            for record in pending:
                record["status"] = "cancelled"

        for record, stream in zip(pending, streams):
            if stream is not None:
                stream.publish({"type": "status", "status": "cancelled", "code": None})
                stream.publish({"type": "end"})
            self.logger.warning(f"queued job {record['job_id']} cancelled, launch queue cleared")

        return len(pending)

    def stop_all(self, grace: float = 8.0) -> int:
        """Clears the queue and terminates every running job, escalating to SIGKILL.

        Args:
            grace: Seconds to wait after SIGTERM before force-killing whatever
                is still running.

        Returns:
            Number of jobs that were running when the stop began.
        """
        self.clear_queue()

        with self.lock:
            running = [dict(r) for r in self.jobs.values() if r["status"] == "running"]

        if not running:
            return 0

        for record in running:
            with self.lock:
                known = self.jobs.get(record["job_id"])
                if known is not None:
                    known["stopped"] = True
            self._signal_group(record["pid"], signal.SIGTERM)
            self.logger.warning(f"watchdog stop for job {record['job_id']} (pid {record['pid']})")

        deadline = time.monotonic() + grace
        while time.monotonic() < deadline:
            if not self._still_running(running):
                return len(running)
            time.sleep(0.5)

        for record in self._still_running(running):
            self._signal_group(record["pid"], signal.SIGKILL)
            self.logger.error(f"force kill for job {record['job_id']} (pid {record['pid']})")

        return len(running)

    def _still_running(self, snapshot: list[dict]) -> list[dict]:
        """Returns the entries of a job snapshot whose live records are still running."""
        alive = []

        with self.lock:
            for record in snapshot:
                known = self.jobs.get(record["job_id"])
                if known is not None and known["status"] == "running":
                    alive.append(record)

        return alive

    @staticmethod
    def _signal_group(pid: int, sig: signal.Signals) -> None:
        """Signals a job's whole process group, falling back to the single pid.

        Args:
            pid: Session leader of the job, also used as the group id.
            sig: Signal to deliver; a process that is already gone is ignored.
        """
        try:
            os.killpg(pid, sig)
            return
        except (ProcessLookupError, PermissionError):
            pass

        try:
            os.kill(pid, sig)
        except (ProcessLookupError, PermissionError):
            pass

    def list_jobs(self) -> list[dict]:
        """Returns every job record newest first, with a live progress snapshot attached.

        The progress field is filled only for running jobs whose fan-out
        snapshot is present and live, and is None otherwise.
        """
        with self.lock:
            records = [dict(record) for record in sorted(self.jobs.values(), key=lambda r: r["started"], reverse=True)]

        for record in records:
            info               = self.progress(record["job_id"]) if record["status"] == "running" else None
            record["progress"] = info["progress"] if info is not None and info.get("ok") and info.get("live") and "progress" in info else None

        return records

    def get_stream(self, job_id: str) -> JobStream | None:
        """Returns the output stream of a job, or None when the job is unknown."""
        with self.lock:
            return self.streams.get(job_id)


class ProcessNuke:
    """Emergency stop that kills every process this user owns except the server's own line.

    Attributes:
        logger: Console logger for the signal and kill counts.
        uid: Effective user id whose processes are targeted.
    """

    def __init__(self, logger: WebLogger) -> None:
        """Records the logger and the user id whose processes may be killed."""
        self.logger = logger
        self.uid    = os.getuid()

    def _spared_pids(self) -> set[int]:
        """Returns the server process and its whole ancestor chain, which must survive."""
        spared = {0, 1}
        pid    = os.getpid()

        while pid > 1:
            spared.add(pid)
            pid = ProcStats.ppid(pid)

        return spared

    def _targets(self, spared: set[int]) -> list[int]:
        """Returns this user's pids minus the spared ones."""
        return [pid for pid in self._user_pids() if pid not in spared]

    def _user_pids(self) -> list[int]:
        """Returns every pid in /proc owned by this user."""
        pids = []
        for entry in os.listdir("/proc"):
            if not entry.isdigit():
                continue
            pid = int(entry)
            try:
                if os.stat(f"/proc/{pid}").st_uid == self.uid:
                    pids.append(pid)
            except OSError:
                continue
        return pids

    def _terminate(self, targets: list[int], sig: signal.Signals) -> int:
        """Sends a signal to each target and returns how many accepted it."""
        hit = 0
        for pid in targets:
            try:
                os.kill(pid, sig)
                hit += 1
            except (ProcessLookupError, PermissionError):
                continue
        return hit

    def _alive(self, targets: list[int]) -> list[int]:
        """Returns the targets that still have a /proc entry."""
        return [pid for pid in targets if os.path.exists(f"/proc/{pid}")]

    def nuke(self, grace: float = 4.0) -> dict:
        """Terminates every process this user owns, escalating to SIGKILL after the grace period.

        Args:
            grace: Seconds to wait after SIGTERM before force-killing survivors.

        Returns:
            Mapping with "ok" True, the number "signalled" with SIGTERM and the
            number "killed" with SIGKILL.
        """
        spared  = self._spared_pids()
        targets = self._targets(spared)

        if not targets:
            self.logger.muted("nuke requested, no processes to kill")
            return {"ok": True, "signalled": 0, "killed": 0}

        signalled = self._terminate(targets, signal.SIGTERM)
        self.logger.error(f"NUKE: SIGTERM sent to {signalled} of {len(targets)} user processes")

        deadline = time.monotonic() + grace
        while time.monotonic() < deadline:
            if not self._alive(targets):
                return {"ok": True, "signalled": signalled, "killed": 0}
            time.sleep(0.25)

        stubborn = self._alive(targets)
        killed   = self._terminate(stubborn, signal.SIGKILL)
        self.logger.error(f"NUKE: SIGKILL sent to {killed} surviving processes")

        return {"ok": True, "signalled": signalled, "killed": killed}


class ServerDetacher:
    """Moves the web server off its terminal without restarting it.

    The redirection itself must happen on the main thread, so a request thread
    only raises the request flag and waits for the main thread's wait loop to
    apply it.

    Attributes:
        paths: Project paths supplying the logs directory.
        logger: Console logger, silenced once the server is detached.
        log_path: File the server's output continues into after detaching.
        requested: Set to ask the main thread to detach or to shut down.
        applied: Set once the redirection has taken effect.
        stopping: Set to make the wait loop return instead of detaching.
    """

    APPLY_TIMEOUT_S = 5.0
    LOG_NAME        = "webui_server.log"

    def __init__(self, paths: ProjectPaths, logger: WebLogger) -> None:
        """Resolves the detached log path and creates the coordination events.

        Args:
            paths: Project paths supplying the logs directory.
            logger: Console logger, disabled once detaching is applied.
        """
        self.paths     = paths
        self.logger    = logger
        self.log_path  = paths.logs_dir / self.LOG_NAME
        self.requested = threading.Event()
        self.applied   = threading.Event()
        self.stopping  = threading.Event()

    def state(self) -> dict:
        """Returns whether the server has detached, its pid, and the log it writes to."""
        return {"detached": self.applied.is_set(), "pid": os.getpid(), "log_path": str(self.log_path)}

    def detach(self) -> dict:
        """Asks the main thread to detach the server and waits for it to take effect.

        Returns:
            The new state under an "ok" flag, or "ok" False with an "error" when
            the main thread did not apply the detach within the timeout.
        """
        if not self.applied.is_set():
            self.requested.set()
            if not self.applied.wait(self.APPLY_TIMEOUT_S):
                return {"ok": False, "error": "detach was not applied by the main thread"}
        return {"ok": True, **self.state()}

    def shutdown(self) -> None:
        """Wakes the main thread's wait loop and asks it to return so the server can exit."""
        self.stopping.set()
        self.requested.set()

    def _apply(self) -> None:
        """Redirects the server's standard streams to the log file and ignores SIGHUP."""
        self.paths.logs_dir.mkdir(parents=True, exist_ok=True)
        handle = open(self.log_path, "ab", buffering=0)

        signal.signal(signal.SIGHUP, signal.SIG_IGN)
        os.dup2(handle.fileno(), sys.stdout.fileno())
        os.dup2(handle.fileno(), sys.stderr.fileno())
        handle.close()

        devnull = os.open(os.devnull, os.O_RDONLY)
        os.dup2(devnull, sys.stdin.fileno())
        os.close(devnull)

        self.logger.enabled = False

    def wait_loop(self) -> None:
        """Parks the main thread until it is asked to detach the server or to shut down.

        Returns once shutdown is requested; running jobs are their own session
        leaders and survive.
        """
        while True:
            self.requested.wait()
            self.requested.clear()
            if self.stopping.is_set():
                self.logger.warning(f"front end shutdown requested from the console (pid {os.getpid()}); running jobs are their own session leaders and keep going")
                return
            if not self.applied.is_set():
                self._apply()
                self.applied.set()
                self.logger.warning(f"server detached from the terminal (pid {os.getpid()}), output continues in {self.log_path}")
