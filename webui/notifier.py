"""Push notifications for console jobs and a watcher that fires experiment milestones.

JobNotifier sends start, finish and unit-failure messages to an ntfy topic;
ExperimentProgressWatcher polls the running fan-out jobs and asks the notifier
to push the first ETA, the quarter milestones, and every newly failed unit.
"""

from __future__ import annotations

import json
import re
import socket
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime

from web_logger import WebLogger


class JobNotifier:
    """Pushes job lifecycle notifications to an ntfy topic.

    Settings persist to a JSON file under the logs directory and every send
    happens on a throwaway thread, so a slow or unreachable server never blocks
    the console.

    Attributes:
        paths: Project paths supplying the logs directory.
        logger: Console logger for configuration changes and delivery failures.
        lock: Guards the settings against concurrent readers and writers.
        path: File the settings are persisted to.
        settings: Current enabled flag, topic and server URL.
    """

    SETTINGS_NAME  = "notifier.json"
    TOPIC_PATTERN  = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
    SEND_TIMEOUT_S = 10.0
    DEFAULTS       = {"enabled": False, "topic": "", "server": "https://ntfy.sh"}

    def __init__(self, paths, logger: WebLogger) -> None:
        """Resolves the settings file and loads the persisted notification settings.

        Args:
            paths: Project paths supplying the logs directory.
            logger: Console logger for configuration changes and send failures.
        """
        self.paths    = paths
        self.logger   = logger
        self.lock     = threading.Lock()
        self.path     = paths.logs_dir / self.SETTINGS_NAME
        self.settings = self._load()

    def _load(self) -> dict:
        """Returns the persisted settings, or the defaults when no settings file exists."""
        if not self.path.exists():
            return dict(self.DEFAULTS)
        loaded = json.loads(self.path.read_text())
        return {key: loaded[key] for key in self.DEFAULTS}

    def state(self) -> dict:
        """Returns the current settings together with the path they are stored in."""
        with self.lock:
            return {**self.settings, "settings_path": str(self.path)}

    def configure(self, payload: dict) -> dict:
        """Validates and persists new notification settings.

        Args:
            payload: Request body with "enabled", "topic" and optionally "server".

        Returns:
            The new state under an "ok" flag, or an "ok" of False with an
            "error" when the topic has illegal characters, notifications are
            enabled without a topic, or the server is not an http(s) URL.
        """
        enabled = bool(payload.get("enabled", False))
        topic   = str(payload.get("topic", "")).strip()
        server  = str(payload.get("server", self.DEFAULTS["server"])).strip().rstrip("/")

        if topic and not self.TOPIC_PATTERN.match(topic):
            return {"ok": False, "error": "topic may only contain letters, digits, '-' and '_' (max 64 chars)"}
        if enabled and not topic:
            return {"ok": False, "error": "set a topic before enabling notifications"}
        if not server.startswith(("http://", "https://")):
            return {"ok": False, "error": "server must be an http(s) URL"}

        with self.lock:
            self.settings = {"enabled": enabled, "topic": topic, "server": server}
            self._persist()

        self.logger.ok(f"notifications {'enabled' if enabled else 'disabled'} (topic '{topic}')")
        return {"ok": True, **self.state()}

    def _persist(self) -> None:
        """Writes the current settings to the settings file, creating its directory."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.settings, indent=2) + "\n")

    def test(self) -> dict:
        """Sends a test message synchronously and reports whether it reached the topic.

        Returns:
            Mapping with "ok" True on delivery, or "ok" False with an "error"
            when no topic is set or the send failed.
        """
        with self.lock:
            if not self.settings["topic"]:
                return {"ok": False, "error": "set a topic first"}

        error = self._send("DLR-TomoSAR test notification", f"the console on {socket.gethostname()} can reach you", "default")
        if error is not None:
            return {"ok": False, "error": error}
        return {"ok": True}

    def _runtime_s(self, record: dict) -> float:
        """Returns the seconds elapsed since the job record's start timestamp."""
        started = datetime.fromisoformat(record["started"])
        return max(0.0, (datetime.now() - started).total_seconds())

    def _runtime_label(self, seconds: float) -> str:
        """Returns a duration in seconds as a compact hours, minutes or seconds label."""
        minutes, secs  = divmod(int(seconds), 60)
        hours, minutes = divmod(minutes, 60)
        if hours:
            return f"{hours}h {minutes:02d}m"
        if minutes:
            return f"{minutes}m {secs:02d}s"
        return f"{secs}s"

    def _describe(self, record: dict, runtime_s: float) -> tuple[str, str, str]:
        """Builds the notification for a job that ended.

        Args:
            record: Job record holding the script name, status, exit code,
                stopped flag, progress snapshot and job id.
            runtime_s: Job runtime in seconds.

        Returns:
            Tuple of title, body and ntfy priority; a failed job is "high"
            priority and a stopped or finished job is "default".
        """
        script = record.get("script") or "job"
        code   = record.get("exit_code")

        if record.get("stopped"):
            title    = f"{script} stopped" + (f" (exit {code})" if code is not None else "")
            priority = "default"
        elif record["status"] == "failed":
            title    = f"{script} FAILED" + (f" (exit {code})" if code is not None else "")
            priority = "high"
        else:
            title    = f"{script} finished" + ("" if code == 0 else " (exit status unknown)")
            priority = "default"

        units = self._units_label(record.get("progress"))
        base  = f"runtime {self._runtime_label(runtime_s)} on {socket.gethostname()} (job {record['job_id']})"
        body  = self._with_description(record, f"{units}\n{base}" if units else base)
        return title, body, priority

    def _units_label(self, progress: dict | None) -> str:
        """Returns a "done/total units done" line with any failure count, empty without progress."""
        if not progress:
            return ""

        label = f"{progress['done']}/{progress['total']} units done"
        return label + (f", {progress['failed']} FAILED" if progress["failed"] else "")

    def _clock_label(self, stamp: str) -> str:
        """Returns the HH:MM wall-clock part of an ISO timestamp."""
        return stamp[11:16]

    def _with_description(self, record: dict, body: str) -> str:
        """Returns the body prefixed with the job's description line when it has one."""
        description = record.get("description") or ""
        return f"{description}\n{body}" if description else body

    def _send(self, title: str, body: str, priority: str) -> str | None:
        """Posts one message to the configured topic and returns the failure text, or None.

        Args:
            title: Notification title, sent as the Title header.
            body: Message body, sent as the UTF-8 request payload.
            priority: ntfy priority, sent as the Priority header.

        Returns:
            None when the server accepted the message, otherwise the transport
            error as text.
        """
        with self.lock:
            url = f"{self.settings['server']}/{self.settings['topic']}"

        request = urllib.request.Request(url, data=body.encode("utf-8"), method="POST")
        request.add_header("Title", title)
        request.add_header("Priority", priority)

        try:
            with urllib.request.urlopen(request, timeout=self.SEND_TIMEOUT_S) as response:
                response.read()
            return None
        except (urllib.error.URLError, OSError) as exc:
            return str(exc)

    def _deliver(self, title: str, body: str, priority: str) -> None:
        """Sends one message and logs an error rather than raising when it fails."""
        error = self._send(title, body, priority)
        if error is not None:
            self.logger.error(f"notification '{title}' failed: {error}")

    def _dispatch(self, title: str, body: str, priority: str) -> None:
        """Delivers one message on a daemon thread so the caller never blocks on the network."""
        threading.Thread(target=self._deliver, args=(title, body, priority), daemon=True).start()

    def _enabled(self) -> bool:
        """Returns whether notifications are switched on and a topic is configured."""
        with self.lock:
            return self.settings["enabled"] and bool(self.settings["topic"])

    def job_started(self, record: dict) -> None:
        """Pushes a start notification naming the host, job id and pid.

        Args:
            record: Job record with the script name, job id, pid and description.
        """
        if not self._enabled():
            return

        script = record.get("script") or "job"
        body   = self._with_description(record, f"running on {socket.gethostname()} (job {record['job_id']}, pid {record.get('pid')})")
        self._dispatch(f"{script} started", body, "default")

    def job_finished(self, record: dict) -> None:
        """Pushes an end-of-job notification for a failed or finished job.

        Jobs that ended in any other state are ignored.

        Args:
            record: Job record with status, exit code, start timestamp and
                final progress snapshot.
        """
        if not self._enabled():
            return
        if record["status"] not in ("failed", "finished"):
            return

        runtime_s             = self._runtime_s(record)
        title, body, priority = self._describe(record, runtime_s)
        self._dispatch(title, body, priority)

    def experiment_progress(self, record: dict, progress: dict) -> None:
        """Pushes a fan-out progress notification with completion percentage and ETA.

        Args:
            record: Job record of the running experiment.
            progress: Progress snapshot with done, failed and total unit counts
                plus eta_s, finish_at and average_s once the first units land.
        """
        if not self._enabled():
            return

        script    = record.get("script") or "job"
        completed = progress["done"] + progress["failed"]
        percent   = round(100.0 * completed / progress["total"])
        title     = f"{script} {completed}/{progress['total']} units ({percent}%)"

        if progress["eta_s"] is None:
            detail = "first units still running, no ETA yet"
        else:
            detail = f"ETA {self._runtime_label(progress['eta_s'])} · finish ≈ {self._clock_label(progress['finish_at'])} · avg {self._runtime_label(progress['average_s'])}/unit"

        failed = f" · {progress['failed']} FAILED" if progress["failed"] else ""
        body   = self._with_description(record, f"{detail}{failed} · on {socket.gethostname()}")
        self._dispatch(title, body, "default")

    def experiment_unit_failed(self, record: dict, progress: dict, units: list[str]) -> None:
        """Pushes a high-priority notification naming the units that just failed.

        Args:
            record: Job record of the running experiment.
            progress: Progress snapshot supplying the failed and total counts.
            units: Names of the units that failed since the previous scan.
        """
        if not self._enabled():
            return

        script = record.get("script") or "job"
        title  = f"{script} unit FAILED: {units[-1]}" if len(units) == 1 else f"{script}: {len(units)} units FAILED"
        body   = self._with_description(record, f"{', '.join(units)} — {progress['failed']} of {progress['total']} units failed so far, the experiment continues")
        self._dispatch(title, body, "high")


class ExperimentProgressWatcher:
    """Polls running fan-out jobs and pushes milestone, first-ETA and unit-failure alerts.

    Attributes:
        processes: Process manager whose job list is polled.
        notifier: Notifier the alerts are pushed through.
        logger: Console logger for scan failures.
        tracked: Per-job watch state keyed by job id, holding the last failure
            count, whether an ETA has been pushed, and the milestones crossed.
    """

    INTERVAL_S = 10.0
    MILESTONES = (0.25, 0.50, 0.75)

    def __init__(self, processes, notifier: JobNotifier, logger: WebLogger) -> None:
        """Stores the collaborators and starts with no jobs tracked.

        Args:
            processes: Process manager supplying the running job list.
            notifier: Notifier used to push progress and failure alerts.
            logger: Console logger for scan failures.
        """
        self.processes = processes
        self.notifier  = notifier
        self.logger    = logger
        self.tracked   : dict[str, dict] = {}

    def start(self) -> None:
        """Starts the background polling thread."""
        worker = threading.Thread(target=self._watch, daemon=True)
        worker.start()

    def _watch(self) -> None:
        """Scans on the fixed interval forever, logging any scan failure instead of exiting."""
        while True:
            time.sleep(self.INTERVAL_S)
            try:
                self.scan()
            except Exception as exc:
                self.logger.error(f"progress watcher error: {exc}")

    def _fraction(self, progress: dict) -> float:
        """Returns the fraction of units that have finished or failed, in [0, 1]."""
        return (progress["done"] + progress["failed"]) / max(progress["total"], 1)

    def _baseline(self, progress: dict) -> dict:
        """Returns the initial watch state for a job, treating its current progress as seen."""
        return {
            "failed"     : progress["failed"],
            "eta_pushed" : progress["eta_s"] is not None,
            "milestones" : {milestone for milestone in self.MILESTONES if self._fraction(progress) >= milestone},
        }

    def _evaluate(self, record: dict, progress: dict) -> None:
        """Compares one job's progress against its watch state and pushes what changed.

        A job seen for the first time only records a baseline. Afterwards, newly
        failed units, newly crossed milestones, and the first available ETA each
        trigger one notification.

        Args:
            record: Job record of the running experiment.
            progress: Its current progress snapshot.
        """
        state = self.tracked.get(record["job_id"])
        if state is None:
            self.tracked[record["job_id"]] = self._baseline(progress)
            return

        if progress["failed"] > state["failed"]:
            self.notifier.experiment_unit_failed(record, progress, progress["failed_units"][state["failed"]:])
            state["failed"] = progress["failed"]

        crossed = [milestone for milestone in self.MILESTONES if milestone not in state["milestones"] and self._fraction(progress) >= milestone]

        if crossed:
            state["milestones"].update(crossed)
            state["eta_pushed"] = True
            self.notifier.experiment_progress(record, progress)
        elif not state["eta_pushed"] and progress["eta_s"] is not None:
            state["eta_pushed"] = True
            self.notifier.experiment_progress(record, progress)

    def scan(self) -> None:
        """Evaluates every running job with a progress snapshot and forgets the ones that ended."""
        live = {record["job_id"]: record for record in self.processes.list_jobs() if record["status"] == "running" and record["progress"]}

        for job_id in [job_id for job_id in self.tracked if job_id not in live]:
            self.tracked.pop(job_id)

        for record in live.values():
            self._evaluate(record, record["progress"])
