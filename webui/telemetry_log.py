"""Shared machinery of the background telemetry collectors.

Provides the sampling loop every collector runs, the CPU busy-percentage meter
derived from successive /proc/stat readings, and the bucketed JSONL log that
folds samples into fixed-width buckets persisted atomically across restarts.
"""

from __future__ import annotations

import json
import threading
import time

from proc_stats import CpuCounters
from web_logger import WebLogger


class CpuBusyMeter:
    """Total CPU busy percentage between successive /proc/stat readings.

    Attributes:
        prev : Previous aggregate CPU counters, None before the first reading.
    """

    def __init__(self) -> None:
        """Starts without a previous reading."""
        self.prev = None

    def percent(self) -> float:
        """Returns the total CPU busy percentage since the previous call, 0.0 on the first."""
        current   = CpuCounters.read().get("cpu")
        prev      = self.prev
        self.prev = current

        if current is None or prev is None or current[1] <= prev[1]:
            return 0.0
        return round(100.0 * (current[0] - prev[0]) / (current[1] - prev[1]), 1)


class TelemetrySampler:
    """Background sampling loop shared by the telemetry collectors.

    Subclasses provide a sample method, a SAMPLE_PERIOD_S class attribute, a
    LABEL naming the collector in failure log lines, and a logger attribute.
    """

    def sample_loop(self) -> None:
        """Samples every SAMPLE_PERIOD_S seconds forever, logging any sampling failure."""
        while True:
            try:
                self.sample()
            except Exception as error:
                self.logger.error(f"{self.LABEL} sampling failed: {error}")

            time.sleep(self.SAMPLE_PERIOD_S)


class BucketedTelemetryLog(TelemetrySampler):
    """Fixed-width bucket table persisted as JSONL, shared by the telemetry logs.

    Samples fold into BUCKET_S-wide buckets keyed by their start time, pruned
    to RETENTION_S of retention. Whenever a bucket closes the table is written
    to a staging file and atomically renamed over the JSONL file, so a crash
    mid-write can never leave a truncated file behind for the next start.
    Each persisted record carries the bucket start under "t" plus the bucket
    payload, whose "gpus" entry maps device indices to named accumulators for
    the collectors that watch devices. Subclasses build one sample, hand it to
    _fold, and implement _accumulate to merge it into the payload of the open
    bucket.

    Attributes:
        monitor : Host monitor supplying the telemetry.
        logger  : Console logger.
        path    : JSONL file holding the persisted buckets.
        lock    : Guards the bucket table against concurrent readers.
        buckets : Bucket payloads keyed by bucket start time in epoch seconds.
        names   : Last seen device name, keyed by device index as a string.
        open_at : Start time of the bucket samples are currently folded into.
    """

    SAMPLE_PERIOD_S = 30.0
    BUCKET_S        = 300
    RETENTION_S     = 30 * 86400

    SPANS = {
        "day"   : (86400,      300),
        "week"  : (7 * 86400,  3600),
        "month" : (30 * 86400, 4 * 3600),
    }

    def __init__(self, monitor, paths, logger: WebLogger) -> None:
        """Loads the persisted buckets and prepares the bucket table.

        Args:
            monitor : Host monitor supplying the telemetry.
            paths   : Project paths supplying the log directory.
            logger  : Console logger.
        """
        self.monitor = monitor
        self.logger  = logger
        self.path    = paths.logs_dir / self.FILE_NAME
        self.lock    = threading.Lock()
        self.buckets = {}
        self.names   = {}
        self.open_at = None

        self._load()

    def _load(self) -> None:
        """Reads the persisted buckets, dropping any that fall outside the window."""
        if not self.path.is_file():
            return

        cutoff = time.time() - self.RETENTION_S
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue

            record = json.loads(line)
            if record["t"] < cutoff:
                continue

            self.buckets[record["t"]] = {key: value for key, value in record.items() if key != "t"}
            self._adopt(record)

    def _adopt(self, record: dict) -> None:
        """Takes the device names out of one reloaded bucket.

        Collectors whose buckets hold no per-device table override this with a
        no-op.

        Args:
            record : One persisted bucket, its start time under "t".
        """
        for key, entry in record["gpus"].items():
            self.names[key] = entry["name"]

    def _prune(self, now: float) -> None:
        """Drops every bucket that starts before the retention covering the given time."""
        cutoff = now - self.RETENTION_S
        for start in [start for start in self.buckets if start < cutoff]:
            del self.buckets[start]

    def _persist(self) -> None:
        """Atomically rewrites the JSONL file with the buckets currently held in memory."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        lines   = [json.dumps({"t": start, **bucket}) for start, bucket in sorted(self.buckets.items())]
        staging = self.path.with_suffix(".tmp")
        staging.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
        staging.replace(self.path)

    def _fold(self, now: float, sample) -> None:
        """Folds one sample into the bucket covering now, persisting on a roll-over.

        Args:
            now    : Wall-clock time of the sample in epoch seconds.
            sample : Sample payload handed to the subclass's _accumulate.
        """
        start  = int(now // self.BUCKET_S) * self.BUCKET_S
        rolled = self.open_at is not None and start != self.open_at

        with self.lock:
            self._accumulate(start, sample)
            self._prune(now)
            self.open_at = start

            if rolled:
                self._persist()
