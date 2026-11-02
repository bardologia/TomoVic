"""Tests covering LogMirrorTrimmer: the allocated-size trigger, the kept tail, the writer that carries on and the queue wiring."""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

from tools.orchestration.gpu_queue  import GpuJob, GpuQueue
from tools.orchestration.log_mirror import KILOBYTE, LogMirrorTrimmer

from tests.conftest import SilentLogger


class RecordingLogger(SilentLogger):
    """Silent logger that keeps the info and warning messages."""
    def __init__(self) -> None:
        self.infos    = []
        self.warnings = []

    def info(self, message, *a, **k):    self.infos.append(str(message))
    def warning(self, message, *a, **k): self.warnings.append(str(message))


def _fill(path: Path, size: int) -> None:
    """Writes ``size`` bytes of a repeating line into the file."""
    line = b"redraw line\n"
    with open(path, "wb") as handle:
        handle.write(line * (size // len(line) + 1))


def test_small_mirror_is_left_alone(tmp_path):
    """A mirror under the limit keeps its bytes and gets no tail companion."""
    mirror = tmp_path / "w00.log"
    _fill(mirror, 10 * KILOBYTE)
    trimmer = LogMirrorTrimmer(max_bytes=64 * KILOBYTE, tail_bytes=KILOBYTE, logger=SilentLogger())

    assert trimmer.trim([mirror]) == []
    assert mirror.stat().st_size >= 10 * KILOBYTE
    assert not trimmer.tail_path(mirror).exists()


def test_oversized_mirror_is_emptied_and_its_tail_kept(tmp_path):
    """A mirror past the limit is truncated to zero bytes and its last bytes survive in the .tail companion."""
    mirror = tmp_path / "w00.log"
    _fill(mirror, 256 * KILOBYTE)
    last   = mirror.read_bytes()[-KILOBYTE:]
    logger = RecordingLogger()
    trimmer = LogMirrorTrimmer(max_bytes=64 * KILOBYTE, tail_bytes=KILOBYTE, logger=logger)

    assert trimmer.trim([mirror]) == [mirror]
    assert mirror.stat().st_size == 0
    assert trimmer.tail_path(mirror).read_bytes() == last
    assert len(logger.infos) == 1 and "w00.log" in logger.infos[0]


def test_missing_mirror_is_skipped(tmp_path):
    """A worker that has not opened its mirror yet is not an error."""
    trimmer = LogMirrorTrimmer(max_bytes=KILOBYTE, tail_bytes=KILOBYTE, logger=SilentLogger())

    assert trimmer.trim([tmp_path / "absent.log"]) == []


@pytest.mark.parametrize("max_bytes, tail_bytes", [(0, 1), (1, 0), (-5, 1)])
def test_non_positive_limits_are_rejected(max_bytes, tail_bytes):
    """Both limits must be positive."""
    with pytest.raises(ValueError):
        LogMirrorTrimmer(max_bytes=max_bytes, tail_bytes=tail_bytes, logger=SilentLogger())


def test_writer_carries_on_after_the_trim_and_the_file_goes_sparse(tmp_path):
    """Emptying a mirror under a live writer frees its blocks; the writer keeps its offset, so later bytes land after a hole."""
    mirror = tmp_path / "w00.log"
    handle = open(mirror, "w", encoding="utf-8")
    writer = subprocess.Popen([sys.executable, "-u", "-c", "import sys, time\nfor i in range(400):\n    sys.stdout.write('x' * 1023 + '\\n')\n    sys.stdout.flush()\n    time.sleep(0.002)\nprint('after', flush=True)"], stdout=handle, stderr=subprocess.STDOUT)
    trimmer = LogMirrorTrimmer(max_bytes=128 * KILOBYTE, tail_bytes=KILOBYTE, logger=SilentLogger())
    emptied = []

    while writer.poll() is None:
        emptied += trimmer.trim([mirror])
        time.sleep(0.01)

    handle.close()
    raw = mirror.read_bytes()

    assert emptied, "the writer never crossed the limit"
    assert raw.endswith(b"after\n")
    assert raw.count(b"\0") > 0
    assert LogMirrorTrimmer.allocated(mirror) < raw.__len__()


def test_queue_trims_the_mirrors_of_running_workers(tmp_path):
    """The queue sweeps its trimmer over the in-flight mirrors, so a chatty worker's log is emptied while it runs."""
    logger  = RecordingLogger()
    trimmer = LogMirrorTrimmer(max_bytes=64 * KILOBYTE, tail_bytes=KILOBYTE, logger=logger)
    queue   = GpuQueue(gpus=[0], logger=logger, poll_interval_s=0.01, handle_signals=False, trimmer=trimmer)
    command = [sys.executable, "-u", "-c", "import sys, time\nfor i in range(300):\n    sys.stdout.write('y' * 1023 + '\\n')\n    sys.stdout.flush()\n    time.sleep(0.002)\nprint('end', flush=True)"]
    job     = GpuJob(name="chatty", command=command, log_path=tmp_path / "chatty.log")

    results = queue.run([job])

    assert results[0].status == "DONE"
    assert any("chatty.log" in message for message in logger.infos)
    assert trimmer.tail_path(job.log_path).exists()
    assert job.log_path.read_bytes().endswith(b"end\n")


def test_queue_worker_keeps_its_offset_so_a_trimmed_mirror_keeps_its_size(tmp_path):
    """The queue appends the banner behind an earlier attempt, but the worker writes with its own offset, so a trim leaves a sparse file of full size that a byte-offset tailer can follow."""
    logger  = RecordingLogger()
    trimmer = LogMirrorTrimmer(max_bytes=64 * KILOBYTE, tail_bytes=KILOBYTE, logger=logger)
    queue   = GpuQueue(gpus=[0], logger=logger, poll_interval_s=0.01, handle_signals=False, trimmer=trimmer)
    command = [sys.executable, "-u", "-c", "import sys, time\nfor i in range(300):\n    sys.stdout.write('y' * 1023 + '\\n')\n    sys.stdout.flush()\n    time.sleep(0.002)\nprint('end', flush=True)"]
    job     = GpuJob(name="chatty", command=command, log_path=tmp_path / "chatty.log")

    job.log_path.write_text("earlier attempt traceback\n", encoding="utf-8")
    earlier = job.log_path.stat().st_size

    results = queue.run([job])
    raw     = job.log_path.read_bytes()

    assert results[0].status == "DONE"
    assert any("chatty.log" in message for message in logger.infos)
    assert len(raw) >= earlier + 300 * 1024
    assert raw.count(b"\0") > 0
    assert raw.endswith(b"end\n")


def test_queue_without_a_trimmer_lets_the_mirror_grow(tmp_path):
    """With no trimmer the queue leaves every byte in place, as the local launchers expect."""
    queue   = GpuQueue(gpus=[0], logger=SilentLogger(), poll_interval_s=0.01, handle_signals=False)
    command = [sys.executable, "-c", "print('z' * 200000)"]
    job     = GpuJob(name="plain", command=command, log_path=tmp_path / "plain.log")

    queue.run([job])

    assert job.log_path.stat().st_size > 200000
    assert not LogMirrorTrimmer.tail_path(job.log_path).exists()
