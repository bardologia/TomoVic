"""Persistent month-long record of which GPUs were busy and who was holding them.

Samples the live GPU occupancy in the background, folds the samples into fixed-width
time buckets and keeps them on disk so the console can show a day, a week or a month
of GPU activity even across restarts of the web server.
"""

from __future__ import annotations

import time

from telemetry_log import BucketedTelemetryLog


class GpuActivityLog(BucketedTelemetryLog):
    """Bucketed history of per-GPU occupancy over the last RETENTION_S seconds.

    Every SAMPLE_PERIOD_S seconds the live occupancy of each device is folded into the
    bucket covering the current wall-clock time. A bucket records how large a share of
    its samples saw the device busy, split into work owned by this user and work owned
    by others, together with the mean utilisation and the holder names seen. Closed
    buckets are written to a JSONL file under the log directory and re-read on start.
    Readers pick one of the SPANS views, which re-bucket the raw records into display
    buckets sized for that window.

    Attributes:
        monitor : Host monitor supplying the GPU occupancy.
        logger  : Console logger.
        path    : JSONL file holding the persisted buckets.
        lock    : Guards the bucket table against concurrent readers.
        buckets : Accumulators keyed by bucket start time in epoch seconds.
        names   : Last seen device name, keyed by device index as a string.
        open_at : Start time of the bucket samples are currently folded into.
    """

    BUSY_UTIL = 5.0
    FILE_NAME = "gpu_activity.jsonl"
    LABEL     = "gpu activity"

    def _states(self) -> list[dict] | None:
        """Returns the busy state of every device now, None when nvidia-smi did not answer.

        Returns:
            One record per device with its index, name, utilisation percentage, whether it
            is busy at all, whether this user holds it, whether another user does, and the
            holder login names.
        """
        occupancy = self.monitor.gpu_occupancy()
        if occupancy is None:
            return None

        states = []
        for device in occupancy:
            if device["index"] is None:
                continue

            holders = []
            mine    = False
            others  = False

            for proc in device["procs"]:
                owner = proc["owner"]
                if owner is None:
                    continue

                if owner == self.monitor.user:
                    mine = True
                else:
                    others = True

                if owner not in holders:
                    holders.append(owner)

            util = device["util"] if device["util"] is not None else 0.0
            states.append({
                "index"   : device["index"],
                "name"    : device["name"],
                "util"    : util,
                "busy"    : bool(device["procs"]) or util >= self.BUSY_UTIL,
                "mine"    : mine,
                "others"  : others,
                "holders" : holders,
            })
        return states

    def _accumulate(self, start: int, states: list[dict]) -> None:
        """Folds one round of device states into the bucket starting at the given time.

        Args:
            start  : Bucket start time in epoch seconds.
            states : Device states returned by _states.
        """
        bucket = self.buckets.setdefault(start, {"gpus": {}})
        for state in states:
            key   = str(state["index"])
            entry = bucket["gpus"].setdefault(key, {"name": state["name"], "n": 0, "busy": 0, "mine": 0, "others": 0, "util": 0.0, "holders": []})

            entry["name"]    = state["name"]
            entry["n"]      += 1
            entry["busy"]   += 1 if state["busy"] else 0
            entry["mine"]   += 1 if state["mine"] else 0
            entry["others"] += 1 if state["others"] else 0
            entry["util"]   += state["util"]

            for holder in state["holders"]:
                if holder not in entry["holders"]:
                    entry["holders"].append(holder)

            self.names[key] = state["name"]

    def sample(self) -> None:
        """Folds one occupancy reading into the current bucket, persisting closed buckets."""
        states = self._states()
        if states is None:
            return

        self._fold(time.time(), states)

    def state(self, span: str = "day") -> dict:
        """Returns the bucketed activity of every known device over one span's window.

        Args:
            span : View name from SPANS, one of "day", "week" or "month".

        Returns:
            Payload with the span name, the display bucket width and window length in
            seconds, the current epoch time, and one entry per device carrying its index,
            name and the display buckets that hold samples, each with its start time,
            busy, own-work and other-work shares in the range 0 to 1, mean utilisation
            percentage and the holder names.

        Raises:
            KeyError : If the span is not a key of SPANS.
        """
        window_s, step_s = self.SPANS[span]

        with self.lock:
            now    = time.time()
            cutoff = now - window_s

            merged = {}
            for start, bucket in sorted(self.buckets.items()):
                if start + self.BUCKET_S <= cutoff:
                    continue

                slot = int(start // step_s) * step_s
                for key, entry in bucket["gpus"].items():
                    acc = merged.setdefault(key, {}).setdefault(slot, {"n": 0, "busy": 0, "mine": 0, "others": 0, "util": 0.0, "holders": []})

                    acc["n"]      += entry["n"]
                    acc["busy"]   += entry["busy"]
                    acc["mine"]   += entry["mine"]
                    acc["others"] += entry["others"]
                    acc["util"]   += entry["util"]

                    for holder in entry["holders"]:
                        if holder not in acc["holders"]:
                            acc["holders"].append(holder)

            devices = {}
            for key, slots in merged.items():
                for slot, acc in sorted(slots.items()):
                    count = acc["n"] or 1
                    devices.setdefault(key, []).append({
                        "t"       : slot,
                        "busy"    : round(acc["busy"] / count, 3),
                        "mine"    : round(acc["mine"] / count, 3),
                        "others"  : round(acc["others"] / count, 3),
                        "util"    : round(acc["util"] / count, 1),
                        "holders" : list(acc["holders"]),
                    })

            return {
                "span"     : span,
                "bucket_s" : step_s,
                "window_s" : window_s,
                "now"      : now,
                "gpus"     : [{"index": int(key), "name": self.names.get(key, ""), "buckets": buckets} for key, buckets in sorted(devices.items(), key=lambda item: int(item[0]))],
            }
