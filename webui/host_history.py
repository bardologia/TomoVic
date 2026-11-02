"""Persistent month-long host telemetry: CPU, RAM, network and per-GPU health.

Samples the host in the background, keeps the raw samples of the last hour in
memory for fine-grained strips (per-GPU temperature and power, network
throughput), and folds them into fixed-width buckets persisted as JSONL so the
console can plot a day, a week or a month of host history across restarts.
"""

from __future__ import annotations

import time

from proc_stats    import MemInfo
from telemetry_log import BucketedTelemetryLog, CpuBusyMeter
from web_logger    import WebLogger


class HostHistoryLog(BucketedTelemetryLog):
    """Bucketed, persisted history of host and GPU telemetry.

    Every SAMPLE_PERIOD_S seconds one sample is taken: total CPU busy percent,
    RAM used percent, network receive and transmit rates summed over the
    physical interfaces, and per GPU the utilisation, memory percentage,
    temperature and power draw. Samples land in a bounded in-memory ring (the
    "hour" view) and accumulate into BUCKET_S-wide buckets that are rewritten
    to a JSONL file under the log directory whenever a bucket closes, with
    RETENTION_S of retention. Readers pick a SPANS view that re-buckets the
    records into display buckets sized for that window.

    Attributes:
        monitor   : Host monitor supplying the GPU devices and memory counters.
        logger    : Console logger.
        path      : JSONL file holding the persisted buckets.
        lock      : Guards the ring and the bucket table against concurrent readers.
        recent    : Raw samples of the last hour, oldest first.
        buckets   : Accumulators keyed by bucket start time in epoch seconds.
        names     : Last seen device name, keyed by device index as a string.
        open_at   : Start time of the bucket samples are currently folded into.
        cpu_meter : CPU busy-percentage meter over successive /proc/stat readings.
    """

    RECENT_SAMPLES = 120
    FILE_NAME      = "host_history.jsonl"
    LABEL          = "host history"
    HOST_KEYS      = ("cpu", "ram", "rx", "tx")
    GPU_KEYS       = ("util", "mem", "temp", "power")

    def __init__(self, monitor, paths, logger: WebLogger) -> None:
        """Loads the persisted buckets and prepares the sampling state.

        Args:
            monitor : Host monitor exposing the GPU devices and memory counters.
            paths   : Project paths supplying the log directory.
            logger  : Console logger.
        """
        self.recent    = []
        self.cpu_meter = CpuBusyMeter()
        self.prev_net  = None
        self.prev_t    = None

        super().__init__(monitor, paths, logger)

    def _net_rates(self, now: float) -> tuple[float, float]:
        """Returns the receive and transmit rates in MB/s summed over physical interfaces.

        Args:
            now : Monotonic timestamp of this sample.

        Returns:
            Tuple of (rx, tx) in MB/s; zeros on the first sample or when
            /proc/net/dev cannot be read.
        """
        rx, tx = 0, 0
        try:
            for line in open("/proc/net/dev").read().splitlines()[2:]:
                name, _, counters = line.partition(":")
                name = name.strip()
                if name == "lo" or not counters:
                    continue
                fields = counters.split()
                rx    += int(fields[0])
                tx    += int(fields[8])
        except (OSError, ValueError, IndexError):
            return 0.0, 0.0

        prev          = self.prev_net
        prev_t        = self.prev_t
        self.prev_net = (rx, tx)
        self.prev_t   = now
        if prev is None or prev_t is None or now <= prev_t:
            return 0.0, 0.0

        dt = now - prev_t
        return round(max(0, rx - prev[0]) / dt / (1024.0 ** 2), 3), round(max(0, tx - prev[1]) / dt / (1024.0 ** 2), 3)

    def _gpu_states(self) -> dict:
        """Returns the current telemetry of every device, keyed by index as a string."""
        devices = self.monitor._gpu_devices()
        if devices is None:
            return {}

        states = {}
        for device in devices:
            if device["index"] is None:
                continue

            key         = str(device["index"])
            mem_pct     = round(100.0 * device["mem_used"] / device["mem_total"], 1) if device["mem_total"] and device["mem_used"] is not None else 0.0
            states[key] = {
                "name"  : device["name"],
                "util"  : device["util"] if device["util"] is not None else 0.0,
                "mem"   : mem_pct,
                "temp"  : device["temp"] if device["temp"] is not None else 0.0,
                "power" : device["power"] if device["power"] is not None else 0.0,
            }
        return states

    def _accumulate(self, start: int, sample: dict) -> None:
        """Folds one sample into the bucket starting at the given time.

        Args:
            start  : Bucket start time in epoch seconds.
            sample : Raw sample as appended to the ring.
        """
        bucket = self.buckets.setdefault(start, {"host": {"n": 0, **{key: 0.0 for key in self.HOST_KEYS}}, "gpus": {}})

        bucket["host"]["n"] += 1
        for key in self.HOST_KEYS:
            bucket["host"][key] += sample[key]

        for index, state in sample["gpus"].items():
            entry = bucket["gpus"].setdefault(index, {"name": state["name"], "n": 0, **{key: 0.0 for key in self.GPU_KEYS}})

            entry["name"] = state["name"]
            entry["n"]   += 1
            for key in self.GPU_KEYS:
                entry[key] += state[key]

            self.names[index] = state["name"]

    def sample(self) -> None:
        """Takes one sample, appends it to the ring and folds it into the open bucket."""
        now    = time.time()
        rx, tx = self._net_rates(time.monotonic())
        sample = {
            "t"    : now,
            "cpu"  : self.cpu_meter.percent(),
            "ram"  : MemInfo.used_percent() or 0.0,
            "rx"   : rx,
            "tx"   : tx,
            "gpus" : self._gpu_states(),
        }

        with self.lock:
            self.recent.append(sample)
            del self.recent[: max(0, len(self.recent) - self.RECENT_SAMPLES)]

        self._fold(now, sample)

    def state(self, span: str = "day") -> dict:
        """Returns the host and per-GPU history over one span's window.

        The "hour" span serves the raw in-memory samples; the persisted spans
        re-bucket the accumulators into display buckets and serve their means.

        Args:
            span : One of "hour" or a key of SPANS.

        Returns:
            Payload with the span name, bucket width and window length in
            seconds, the current epoch time, the host series (bucket start,
            cpu and ram percent, rx and tx MB/s) and one entry per device with
            its index, name and buckets (start, util and mem percent,
            temperature and power).

        Raises:
            KeyError : If the span is neither "hour" nor a key of SPANS.
        """
        if span == "hour":
            return self._recent_state()

        window_s, step_s = self.SPANS[span]

        with self.lock:
            now    = time.time()
            cutoff = now - window_s

            host_slots = {}
            gpu_slots  = {}
            for start, bucket in sorted(self.buckets.items()):
                if start + self.BUCKET_S <= cutoff:
                    continue

                slot = int(start // step_s) * step_s
                acc  = host_slots.setdefault(slot, {"n": 0, **{key: 0.0 for key in self.HOST_KEYS}})

                acc["n"] += bucket["host"]["n"]
                for key in self.HOST_KEYS:
                    acc[key] += bucket["host"][key]

                for index, entry in bucket["gpus"].items():
                    gacc = gpu_slots.setdefault(index, {}).setdefault(slot, {"n": 0, **{key: 0.0 for key in self.GPU_KEYS}})

                    gacc["n"] += entry["n"]
                    for key in self.GPU_KEYS:
                        gacc[key] += entry[key]

            host = [{"t": slot, **{key: round(acc[key] / max(acc["n"], 1), 2) for key in self.HOST_KEYS}} for slot, acc in sorted(host_slots.items())]
            gpus = []
            for index, slots in sorted(gpu_slots.items(), key=lambda item: int(item[0])):
                buckets = [{"t": slot, **{key: round(acc[key] / max(acc["n"], 1), 2) for key in self.GPU_KEYS}} for slot, acc in sorted(slots.items())]
                gpus.append({"index": int(index), "name": self.names.get(index, ""), "buckets": buckets})

            return {"span": span, "bucket_s": step_s, "window_s": window_s, "now": now, "host": host, "gpus": gpus}

    def _recent_state(self) -> dict:
        """Returns the raw last-hour samples in the same shape as the bucketed spans."""
        with self.lock:
            samples = list(self.recent)

        now  = time.time()
        host = [{"t": sample["t"], **{key: sample[key] for key in self.HOST_KEYS}} for sample in samples]

        per_gpu = {}
        for sample in samples:
            for index, state in sample["gpus"].items():
                per_gpu.setdefault(index, []).append({"t": sample["t"], **{key: state[key] for key in self.GPU_KEYS}})

        gpus = [{"index": int(index), "name": self.names.get(index, ""), "buckets": buckets} for index, buckets in sorted(per_gpu.items(), key=lambda item: int(item[0]))]
        return {"span": "hour", "bucket_s": self.SAMPLE_PERIOD_S, "window_s": int(self.RECENT_SAMPLES * self.SAMPLE_PERIOD_S), "now": now, "host": host, "gpus": gpus}
