"""Tests covering GpuQueue: job dispatch and device assignment, live pool-file resizing, per-unit progress snapshots, and signal-handler restoration."""

from __future__ import annotations

import json
import os
import signal
import sys
import threading
import time
from pathlib import Path

import pytest

from tools.orchestration.gpu_queue import GpuJob, GpuPoolFile, GpuProgressFile, GpuQueue, GpuJobResult

from tests.conftest import SilentLogger


class RecordingLogger(SilentLogger):
    """Silent logger that keeps every message by level.

    Attributes:
        errors: Error messages received.
        warnings: Warning messages received.
        infos: Info messages received.
    """
    def __init__(self) -> None:
        """Creates the empty per-level message buffers."""
        self.errors   = []
        self.warnings = []
        self.infos    = []

    def info(self, message, *a, **k):    self.infos.append(str(message))
    def warning(self, message, *a, **k): self.warnings.append(str(message))
    def error(self, message, *a, **k):   self.errors.append(str(message))


def _ok_command(payload: str = "ok") -> list[str]:
    """Returns a command that prints the given payload and exits cleanly."""
    return [sys.executable, "-c", f"print('{payload}')"]


def _fail_command(code: int = 7) -> list[str]:
    """Returns a command that exits with the given non-zero code."""
    return [sys.executable, "-c", f"import sys; sys.exit({code})"]


def _job(tmp_path: Path, name: str, command: list[str]) -> GpuJob:
    """Returns a GPU job writing its log under a per-name subdirectory of tmp_path."""
    return GpuJob(name=name, command=command, log_path=tmp_path / name / "worker.log")


def test_empty_jobs_returns_empty(logger_stub):
    """Verifies running an empty job list produces no results."""
    queue   = GpuQueue(gpus=[0], logger=logger_stub, poll_interval_s=0.0, handle_signals=False)
    results = queue.run([])

    assert results == []


def test_single_job_succeeds(tmp_path, logger_stub):
    """Verifies a successful job reports DONE with its device, return code, and duration."""
    queue   = GpuQueue(gpus=[0], logger=logger_stub, poll_interval_s=0.0, handle_signals=False)
    results = queue.run([_job(tmp_path, "a", _ok_command())])

    assert len(results) == 1

    result = results[0]
    assert isinstance(result, GpuJobResult)
    assert result.name       == "a"
    assert result.status     == "DONE"
    assert result.returncode == 0
    assert result.gpu        == 0
    assert result.duration_s >= 0.0


def test_failed_job_reports_failed_status(tmp_path, logger_stub):
    """Verifies a non-zero exit is reported as FAILED with the child's return code."""
    queue   = GpuQueue(gpus=[0], logger=logger_stub, poll_interval_s=0.0, handle_signals=False)
    results = queue.run([_job(tmp_path, "boom", _fail_command(7))])

    result = results[0]
    assert result.status     == "FAILED"
    assert result.returncode == 7


def test_log_file_is_written_with_stdout(tmp_path, logger_stub):
    """Verifies the child's stdout lands in the job's log file."""
    queue = GpuQueue(gpus=[0], logger=logger_stub, poll_interval_s=0.0, handle_signals=False)
    queue.run([_job(tmp_path, "a", _ok_command("hello_log"))])

    log_text = (tmp_path / "a" / "worker.log").read_text()
    assert "hello_log" in log_text


def test_gpu_flag_is_appended_to_command(tmp_path, logger_stub):
    """Verifies the assigned device index is appended to the command as --gpu."""
    capture_path = tmp_path / "args.txt"
    command      = [sys.executable, "-c", f"import sys; open(r'{capture_path}','w').write(' '.join(sys.argv[1:]))"]

    queue = GpuQueue(gpus=[3], logger=logger_stub, poll_interval_s=0.0, handle_signals=False)
    queue.run([_job(tmp_path, "a", command)])

    written = capture_path.read_text()
    assert written.endswith("--gpu 3")


def _concurrency_probe_command(counter: Path, peak: Path) -> list[str]:
    """Returns a command that records the peak number of concurrently live children.

    Args:
        counter: File holding the current live count under a file lock.
        peak: File appended with the live count observed at each start.

    Returns:
        Command list running the probe.
    """
    body = (
        "import time, fcntl;"
        f"c=r'{counter}'; p=r'{peak}';"
        "open(c,'a').close();"
        "f=open(c,'r+'); fcntl.flock(f, fcntl.LOCK_EX);"
        "n=int(f.read() or '0')+1; f.seek(0); f.truncate(); f.write(str(n)); f.flush();"
        "g=open(p,'a'); g.write(str(n)+'\\n'); g.close();"
        "fcntl.flock(f, fcntl.LOCK_UN); f.close();"
        "time.sleep(0.2);"
        "f=open(c,'r+'); fcntl.flock(f, fcntl.LOCK_EX);"
        "n=int(f.read() or '1')-1; f.seek(0); f.truncate(); f.write(str(n)); f.flush();"
        "fcntl.flock(f, fcntl.LOCK_UN); f.close()"
    )
    return [sys.executable, "-c", body]


def test_capacity_limit_serialises_jobs_on_one_gpu(tmp_path, logger_stub):
    """Verifies a single-device pool never runs two jobs at once."""
    counter = tmp_path / "live.txt"
    peak    = tmp_path / "peak.txt"
    command = _concurrency_probe_command(counter, peak)

    jobs  = [_job(tmp_path, f"j{i}", [*command]) for i in range(3)]
    queue = GpuQueue(gpus=[0], logger=logger_stub, poll_interval_s=0.0, handle_signals=False)
    queue.run(jobs)

    observed = [int(x) for x in peak.read_text().split()]
    assert max(observed) == 1


def test_two_gpus_run_two_jobs_concurrently(tmp_path, logger_stub):
    """Verifies a two-device pool runs two jobs simultaneously."""
    counter = tmp_path / "live.txt"
    peak    = tmp_path / "peak.txt"
    command = _concurrency_probe_command(counter, peak)

    jobs  = [_job(tmp_path, f"j{i}", [*command]) for i in range(2)]
    queue = GpuQueue(gpus=[0, 1], logger=logger_stub, poll_interval_s=0.0, handle_signals=False)
    queue.run(jobs)

    observed = [int(x) for x in peak.read_text().split()]
    assert max(observed) == 2


def test_device_assignment_uses_lowest_free_gpu_first(tmp_path, logger_stub):
    """Verifies a lone job is placed on the lowest-numbered device in the pool."""
    capture = tmp_path / "gpu_seen.txt"
    body    = f"import sys; open(r'{capture}','a').write(sys.argv[-1]+'\\n')"
    command = [sys.executable, "-c", body]

    queue = GpuQueue(gpus=[2, 5], logger=logger_stub, poll_interval_s=0.0, handle_signals=False)
    queue.run([_job(tmp_path, "solo", [*command])])

    assert capture.read_text().strip() == "2"


def test_released_gpu_is_reused_for_next_job(tmp_path, logger_stub):
    """Verifies a freed device is handed to the next queued job."""
    queue   = GpuQueue(gpus=[4], logger=logger_stub, poll_interval_s=0.0, handle_signals=False)
    results = queue.run([_job(tmp_path, f"j{i}", _ok_command()) for i in range(3)])

    assert {r.gpu for r in results} == {4}
    assert len(results) == 3


def test_all_jobs_complete_no_deadlock(tmp_path, logger_stub):
    """Verifies every job in an oversubscribed queue completes."""
    jobs = [_job(tmp_path, f"j{i}", _ok_command()) for i in range(6)]

    queue   = GpuQueue(gpus=[0, 1], logger=logger_stub, poll_interval_s=0.0, handle_signals=False)
    results = queue.run(jobs)

    assert sorted(r.name for r in results) == sorted(j.name for j in jobs)
    assert all(r.status == "DONE" for r in results)


def test_more_gpus_than_jobs(tmp_path, logger_stub):
    """Verifies a surplus of devices still places the single job on the first one."""
    jobs    = [_job(tmp_path, "only", _ok_command())]
    queue   = GpuQueue(gpus=[0, 1, 2, 3], logger=logger_stub, poll_interval_s=0.0, handle_signals=False)
    results = queue.run(jobs)

    assert len(results) == 1
    assert results[0].gpu == 0


def test_result_log_file_matches_job(tmp_path, logger_stub):
    """Verifies the result carries the job's own log path."""
    job     = _job(tmp_path, "a", _ok_command())
    queue   = GpuQueue(gpus=[0], logger=logger_stub, poll_interval_s=0.0, handle_signals=False)
    results = queue.run([job])

    assert results[0].log_file == str(job.log_path)


def test_mixed_success_and_failure(tmp_path, logger_stub):
    """Verifies success and failure statuses are reported per job in one run."""
    jobs = [
        _job(tmp_path, "good", _ok_command()),
        _job(tmp_path, "bad",  _fail_command(3)),
    ]

    queue   = GpuQueue(gpus=[0, 1], logger=logger_stub, poll_interval_s=0.0, handle_signals=False)
    results = queue.run(jobs)

    by_name = {r.name: r for r in results}
    assert by_name["good"].status     == "DONE"
    assert by_name["bad"].status      == "FAILED"
    assert by_name["bad"].returncode == 3


def _write_pool(path: Path, payload) -> None:
    """Writes a pool payload and bumps its mtime so the queue re-reads it.

    Args:
        path: Pool control file to write.
        payload: Raw text to write verbatim, or a device list to wrap as {'gpus': ...}.
    """
    path.write_text(payload if isinstance(payload, str) else json.dumps({"gpus": payload}))

    stamp = path.stat().st_mtime_ns + 1_000_000
    os.utime(path, ns=(stamp, stamp))


def _pool_queue(tmp_path: Path, gpus: list[int], logger=None, poll_interval_s: float = 0.0):
    """Returns a queue backed by a pool control file inside tmp_path, and that file's path."""
    pool  = tmp_path / "gpu_pool.json"
    queue = GpuQueue(gpus=gpus, logger=logger or SilentLogger(), poll_interval_s=poll_interval_s, handle_signals=False, pool_file=pool)

    return queue, pool


class _DoneProcess:
    """Process stub that reports an immediate clean exit."""
    returncode = 0

    def poll(self) -> int:
        """Returns the exit code zero."""
        return 0


class _NullHandle:
    """Log-handle stub whose close is a no-op."""
    def close(self) -> None:
        """Closes nothing."""
        pass


def test_run_seeds_the_pool_file_with_the_launch_selection(tmp_path, logger_stub):
    """Verifies the run writes the launch device selection into the pool file."""
    queue, pool = _pool_queue(tmp_path, [0, 1])
    queue.run([_job(tmp_path, "a", _ok_command())])

    assert json.loads(pool.read_text()) == {"gpus": [0, 1]}


def test_queue_without_pool_file_writes_no_control_file(tmp_path, logger_stub):
    """Verifies a queue configured without a pool file writes no control file."""
    queue = GpuQueue(gpus=[0], logger=logger_stub, poll_interval_s=0.0, handle_signals=False)
    queue.run([_job(tmp_path, "a", _ok_command())])

    assert not (tmp_path / "gpu_pool.json").exists()


def test_reconcile_adds_requested_gpus_to_the_idle_pool(tmp_path):
    """Verifies devices added to the pool file become idle devices."""
    queue, pool = _pool_queue(tmp_path, [0])
    gpu_pool    = [0]

    _write_pool(pool, [0, 1, 2])
    queue._reconcile(gpu_pool, [])

    assert gpu_pool       == [0, 1, 2]
    assert queue.retiring == set()


def test_reconcile_drops_an_idle_gpu_immediately(tmp_path):
    """Verifies an idle device removed from the pool file leaves the pool at once."""
    queue, pool = _pool_queue(tmp_path, [0, 1])
    gpu_pool    = [0, 1]

    _write_pool(pool, [0])
    queue._reconcile(gpu_pool, [])

    assert gpu_pool       == [0]
    assert queue.retiring == set()


def test_reconcile_retires_a_busy_gpu_instead_of_killing_its_job(tmp_path):
    """Verifies a busy device removed from the pool file is marked retiring, not interrupted."""
    queue, pool   = _pool_queue(tmp_path, [0, 1])
    queue.running = [{"gpu": 1}]
    gpu_pool      = [0]

    _write_pool(pool, [0])
    queue._reconcile(gpu_pool, [])

    assert gpu_pool       == [0]
    assert queue.retiring == {1}


def test_reaped_retiring_gpu_is_not_returned_to_the_pool(tmp_path, logger_stub):
    """Verifies a retiring device is dropped rather than returned when its job is reaped."""
    queue, _pool = _pool_queue(tmp_path, [0, 1])
    record       = {"job": _job(tmp_path, "a", _ok_command()), "gpu": 1, "process": _DoneProcess(), "log_fh": _NullHandle(), "started": time.monotonic()}

    queue.running  = [record]
    queue.retiring = {1}
    gpu_pool       = [0]
    results        = []

    queue._reap(queue.running, gpu_pool, results)

    assert gpu_pool          == [0]
    assert queue.retiring    == set()
    assert results[0].status == "DONE"
    assert results[0].gpu    == 1


def test_re_adding_a_retiring_gpu_cancels_the_drain(tmp_path):
    """Verifies putting a retiring device back in the pool file cancels its drain."""
    queue, pool   = _pool_queue(tmp_path, [0, 1])
    queue.running = [{"gpu": 1}]
    gpu_pool      = [0]

    _write_pool(pool, [0])
    queue._reconcile(gpu_pool, [])
    assert queue.retiring == {1}

    _write_pool(pool, [0, 1])
    queue._reconcile(gpu_pool, [])

    assert queue.retiring == set()
    assert gpu_pool       == [0]


def test_unchanged_pool_file_is_not_re_read(tmp_path):
    """Verifies an untouched pool file is not re-applied over the live pool."""
    queue, pool = _pool_queue(tmp_path, [0])
    gpu_pool    = [0]

    _write_pool(pool, [0, 1])
    queue._reconcile(gpu_pool, [])
    assert gpu_pool == [0, 1]

    gpu_pool.remove(1)
    queue._reconcile(gpu_pool, [])

    assert gpu_pool == [0]


@pytest.mark.parametrize("payload", [
    "not json at all",
    '{"gpus": 3}',
    '{"gpus": [0, "one"]}',
    '{"gpus": [0, -1]}',
    '{"gpus": [0, 0]}',
    '{"gpus": [0, true]}',
    '[0, 1]',
    '{"devices": [0, 1]}',
])
def test_invalid_pool_edit_is_rejected_loudly_and_leaves_the_pool_unchanged(tmp_path, payload):
    """Verifies a malformed pool payload logs an error and leaves the pool untouched."""
    recorder    = RecordingLogger()
    queue, pool = _pool_queue(tmp_path, [0], recorder)
    gpu_pool    = [0]

    _write_pool(pool, payload)
    queue._reconcile(gpu_pool, [])

    assert gpu_pool == [0]
    assert recorder.errors
    assert "unchanged" in recorder.errors[0]


def test_pool_edit_is_applied_after_an_invalid_edit_is_fixed(tmp_path):
    """Verifies a corrected pool file is applied after an earlier malformed edit."""
    recorder    = RecordingLogger()
    queue, pool = _pool_queue(tmp_path, [0], recorder)
    gpu_pool    = [0]

    _write_pool(pool, "{oops")
    queue._reconcile(gpu_pool, [])
    assert gpu_pool == [0]

    _write_pool(pool, [0, 1])
    queue._reconcile(gpu_pool, [])

    assert gpu_pool == [0, 1]


def test_empty_pool_parks_the_queue_and_warns(tmp_path):
    """Verifies an empty pool empties the device list and warns that the queue is parked."""
    recorder    = RecordingLogger()
    queue, pool = _pool_queue(tmp_path, [0], recorder)
    gpu_pool    = [0]

    _write_pool(pool, [])
    queue._reconcile(gpu_pool, [_job(tmp_path, "waiting", _ok_command())])

    assert gpu_pool == []
    assert any("parked" in warning for warning in recorder.warnings)


def _sleeper_command(capture: Path, seconds: float) -> list[str]:
    """Returns a command that records its device argument and then sleeps for the given seconds."""
    body = f"import sys, time; open(r'{capture}','a').write(sys.argv[-1]+'\\n'); time.sleep({seconds})"
    return [sys.executable, "-c", body]


def _await_dispatched(capture: Path, count: int, timeout_s: float = 30.0) -> None:
    """Blocks until the capture file lists at least count dispatched jobs.

    Args:
        capture: File each child appends its device argument to.
        count: Number of dispatched jobs to wait for.
        timeout_s: Maximum seconds to wait.

    Raises:
        TimeoutError: If fewer than count jobs started within the timeout.
    """
    deadline = time.monotonic() + timeout_s

    while time.monotonic() < deadline:
        if capture.is_file() and len(capture.read_text().splitlines()) >= count:
            return
        time.sleep(0.01)

    raise TimeoutError(f"only {len(capture.read_text().splitlines()) if capture.is_file() else 0} of {count} jobs started within {timeout_s}s")


def test_pool_growth_mid_run_dispatches_queued_jobs_to_the_new_gpus(tmp_path):
    """Verifies devices added mid-run pick up queued jobs."""
    capture = tmp_path / "gpu_seen.txt"
    command = _sleeper_command(capture, 0.8)
    jobs    = [_job(tmp_path, f"j{i}", [*command]) for i in range(4)]

    queue, pool = _pool_queue(tmp_path, [0], poll_interval_s=0.02)

    def grow() -> None:
        """Widens the pool file to three devices once the first job has started."""
        _await_dispatched(capture, 1)
        _write_pool(pool, [0, 1, 2])

    thread = threading.Thread(target=grow, daemon=True)
    thread.start()
    results = queue.run(jobs)
    thread.join()

    assert len(results) == 4
    assert all(result.status == "DONE" for result in results)
    assert {1, 2} <= {result.gpu for result in results}


def test_pool_shrink_mid_run_stops_dispatching_to_the_removed_gpu(tmp_path):
    """Verifies later jobs avoid a device removed from the pool mid-run."""
    capture = tmp_path / "gpu_seen.txt"
    command = _sleeper_command(capture, 1.0)
    jobs    = [_job(tmp_path, f"j{i}", [*command]) for i in range(4)]

    queue, pool = _pool_queue(tmp_path, [0, 1], poll_interval_s=0.02)

    def shrink() -> None:
        """Narrows the pool file to one device once both jobs have started."""
        _await_dispatched(capture, 2)
        _write_pool(pool, [0])

    thread = threading.Thread(target=shrink, daemon=True)
    thread.start()
    results = queue.run(jobs)
    thread.join()

    by_name = {result.name: result for result in results}

    assert len(results) == 4
    assert all(result.status == "DONE" for result in results)
    assert by_name["j2"].gpu == 0
    assert by_name["j3"].gpu == 0


def test_parked_pool_holds_queued_jobs_until_a_gpu_returns(tmp_path):
    """Verifies an emptied pool stalls the queue until a device is restored."""
    capture = tmp_path / "gpu_seen.txt"
    command = _sleeper_command(capture, 0.3)
    jobs    = [_job(tmp_path, f"j{i}", [*command]) for i in range(2)]

    queue, pool = _pool_queue(tmp_path, [0], poll_interval_s=0.02)

    def park_then_resume() -> None:
        """Empties the pool file once the first job starts, then restores the device a second later."""
        _await_dispatched(capture, 1)
        _write_pool(pool, [])
        time.sleep(1.0)
        _write_pool(pool, [0])

    thread  = threading.Thread(target=park_then_resume, daemon=True)
    started = time.monotonic()
    thread.start()
    results = queue.run(jobs)
    elapsed = time.monotonic() - started
    thread.join()

    assert len(results) == 2
    assert all(result.status == "DONE" for result in results)
    assert elapsed > 1.15


def _progress_jobs(tmp_path: Path, names: list[str]) -> list[GpuJob]:
    """Returns command-less jobs whose log paths sit under per-name directories."""
    return [GpuJob(name=name, command=[], log_path=tmp_path / name / "worker.log") for name in names]


def _progress_result(tmp_path: Path, name: str, status: str, duration_s: float) -> GpuJobResult:
    """Returns a job result with the given terminal status and duration in seconds."""
    return GpuJobResult(name=name, gpu=0, status=status, returncode=0 if status == "DONE" else 1, duration_s=duration_s, log_file=str(tmp_path / name / "worker.log"))


def _running(tmp_path: Path, name: str, gpu: int, elapsed_s: float) -> dict:
    """Returns a running-unit record with its device and elapsed seconds."""
    return {"name": name, "gpu": gpu, "log": str(tmp_path / name / "worker.log"), "elapsed_s": elapsed_s}


def test_progress_file_resolves_next_to_the_pool_file():
    """Verifies the progress file name is derived from the pool file name."""
    assert GpuProgressFile.resolve(Path("/x/logs/gpu_pools/abc.json")) == Path("/x/logs/gpu_pools/abc_progress.json")


def test_run_writes_a_final_progress_snapshot_next_to_the_pool_file(tmp_path, logger_stub):
    """Verifies the final snapshot reports counts, failed unit names, and zeroed ETA."""
    queue, _pool = _pool_queue(tmp_path, [0])
    queue.run([_job(tmp_path, "a", _ok_command()), _job(tmp_path, "b", _fail_command(3))])

    progress = json.loads((tmp_path / "gpu_pool_progress.json").read_text())

    assert progress["total"]        == 2
    assert progress["done"]         == 1
    assert progress["failed"]       == 1
    assert progress["failed_units"] == ["b"]
    assert progress["queued"]       == 0
    assert progress["running"]      == []
    assert progress["eta_s"]        == 0.0
    assert progress["average_s"]    >= 0.0
    assert progress["total_s"]      >= progress["elapsed_s"]


def test_final_snapshot_lists_every_unit_with_status_and_log(tmp_path, logger_stub):
    """Verifies the final snapshot lists each unit with status, log path, device, and return code."""
    jobs = [_job(tmp_path, "a", _ok_command()), _job(tmp_path, "b", _fail_command(3))]

    queue, _pool = _pool_queue(tmp_path, [0])
    queue.run(jobs)

    units = json.loads((tmp_path / "gpu_pool_progress.json").read_text())["units"]

    by_name = {unit["name"]: unit for unit in units}
    assert [unit["name"] for unit in units] == ["a", "b"]
    assert by_name["a"]["status"]     == "done"
    assert by_name["a"]["log"]        == str(jobs[0].log_path)
    assert by_name["a"]["gpu"]        == 0
    assert by_name["a"]["returncode"] == 0
    assert by_name["b"]["status"]     == "failed"
    assert by_name["b"]["returncode"] == 3


def test_units_move_from_queued_through_running_to_terminal(tmp_path):
    """Verifies a unit's status walks from queued through running to done with its duration."""
    progress = GpuProgressFile(tmp_path / "p.json", jobs=_progress_jobs(tmp_path, ["a", "b"]), logger=SilentLogger())

    queued = progress.snapshot([], queued=2, workers=1)["units"]
    assert [unit["status"] for unit in queued] == ["queued", "queued"]

    running = progress.snapshot([_running(tmp_path, "a", 3, 5.0)], queued=1, workers=1)["units"]
    assert [unit["status"] for unit in running] == ["running", "queued"]
    assert running[0]["gpu"] == 3

    progress.record(_progress_result(tmp_path, "a", "DONE", 10.0))
    done = progress.snapshot([], queued=1, workers=1)["units"]
    assert done[0]["status"]     == "done"
    assert done[0]["duration_s"] == 10.0


def test_colliding_log_paths_fail_loudly(tmp_path):
    """Verifies two jobs sharing a log path are rejected at construction."""
    jobs = [
        GpuJob(name="a__b", command=[], log_path=tmp_path / "a__b.out"),
        GpuJob(name="a/b",  command=[], log_path=tmp_path / "a__b.out"),
    ]

    with pytest.raises(ValueError, match="share log path"):
        GpuProgressFile(tmp_path / "p.json", jobs=jobs, logger=SilentLogger())


def test_recording_an_unregistered_unit_fails_loudly(tmp_path):
    """Verifies recording a result for an unknown unit raises."""
    progress = GpuProgressFile(tmp_path / "p.json", jobs=_progress_jobs(tmp_path, ["a"]), logger=SilentLogger())

    with pytest.raises(KeyError):
        progress.record(_progress_result(tmp_path, "stranger", "DONE", 1.0))


def test_next_stage_carries_prior_units_forward(tmp_path):
    """Verifies a new stage keeps earlier units and their logs alongside its own."""
    first = GpuProgressFile(tmp_path / "p.json", jobs=_progress_jobs(tmp_path, ["a"]), logger=SilentLogger())
    first.record(_progress_result(tmp_path, "a", "DONE", 4.0))
    first.write(first.snapshot([], 0, 1), force=True)

    second = GpuProgressFile(tmp_path / "p.json", jobs=[GpuJob(name="a", command=[], log_path=tmp_path / "a" / "infer.log")], logger=SilentLogger())
    units  = second.snapshot([], queued=1, workers=1)["units"]

    assert [(unit["name"], unit["status"]) for unit in units] == [("a", "done"), ("a", "queued")]
    assert units[0]["log"].endswith("worker.log")
    assert units[1]["log"].endswith("infer.log")


def test_reregistered_log_path_resets_instead_of_duplicating(tmp_path):
    """Verifies a re-registered log path replaces its prior entry rather than duplicating it."""
    first = GpuProgressFile(tmp_path / "p.json", jobs=_progress_jobs(tmp_path, ["a", "b"]), logger=SilentLogger())
    first.record(_progress_result(tmp_path, "a", "DONE", 4.0))
    first.write(first.snapshot([], 1, 1), force=True)

    second = GpuProgressFile(tmp_path / "p.json", jobs=_progress_jobs(tmp_path, ["b"]), logger=SilentLogger())
    units  = second.snapshot([], queued=1, workers=1)["units"]

    assert [(unit["name"], unit["status"]) for unit in units] == [("a", "done"), ("b", "queued")]


def test_prior_units_left_non_terminal_by_a_crash_are_marked_stale(tmp_path):
    """Verifies units left queued or running by a crash are reloaded as stale."""
    first = GpuProgressFile(tmp_path / "p.json", jobs=_progress_jobs(tmp_path, ["a", "b"]), logger=SilentLogger())
    first.write(first.snapshot([_running(tmp_path, "a", 0, 5.0)], queued=1, workers=1), force=True)

    second = GpuProgressFile(tmp_path / "p.json", jobs=_progress_jobs(tmp_path, ["c"]), logger=SilentLogger())
    units  = second.snapshot([], queued=1, workers=1)["units"]

    assert [(unit["name"], unit["status"]) for unit in units] == [("a", "stale"), ("b", "stale"), ("c", "queued")]


def test_progress_file_without_units_is_rejected_loudly(tmp_path):
    """Verifies a progress file predating per-unit tracking is rejected."""
    (tmp_path / "p.json").write_text(json.dumps({"total": 2, "done": 1}))

    with pytest.raises(ValueError, match="predates per-unit tracking"):
        GpuProgressFile(tmp_path / "p.json", jobs=_progress_jobs(tmp_path, ["a"]), logger=SilentLogger())


def test_queue_without_pool_file_writes_no_progress_file(tmp_path, logger_stub):
    """Verifies no progress file is written when the queue has no pool file."""
    queue = GpuQueue(gpus=[0], logger=logger_stub, poll_interval_s=0.0, handle_signals=False)
    queue.run([_job(tmp_path, "a", _ok_command())])

    assert not list(tmp_path.glob("*_progress.json"))


def test_progress_eta_unknown_until_the_first_unit_completes(tmp_path):
    """Verifies ETA, total, and finish time stay unknown before any unit completes."""
    progress = GpuProgressFile(tmp_path / "p.json", jobs=_progress_jobs(tmp_path, ["a", "b", "c", "d"]), logger=SilentLogger())
    snapshot = progress.snapshot([_running(tmp_path, "a", 0, 5.0)], queued=3, workers=1)

    assert snapshot["eta_s"]     is None
    assert snapshot["total_s"]   is None
    assert snapshot["finish_at"] is None


def test_progress_eta_splits_remaining_work_across_workers(tmp_path):
    """Verifies the ETA divides the remaining mean-duration work across the workers."""
    progress = GpuProgressFile(tmp_path / "p.json", jobs=_progress_jobs(tmp_path, ["a", "b", "c", "d", "e", "f", "g", "h"]), logger=SilentLogger())
    progress.record(_progress_result(tmp_path, "a", "DONE", 80.0))
    progress.record(_progress_result(tmp_path, "b", "DONE", 120.0))

    running  = [_running(tmp_path, "c", 0, 40.0), _running(tmp_path, "d", 1, 160.0)]
    snapshot = progress.snapshot(running, queued=3, workers=2)

    assert snapshot["average_s"] == 100.0
    assert snapshot["eta_s"]     == 180.0
    assert snapshot["done"]      == 2
    assert snapshot["failed"]    == 0


def test_progress_eta_is_bounded_below_by_the_longest_running_unit(tmp_path):
    """Verifies the ETA is never shorter than the remaining time of the longest-running unit."""
    progress = GpuProgressFile(tmp_path / "p.json", jobs=_progress_jobs(tmp_path, ["a", "b", "c"]), logger=SilentLogger())
    progress.record(_progress_result(tmp_path, "a", "DONE", 100.0))

    running  = [_running(tmp_path, "b", 0, 10.0), _running(tmp_path, "c", 1, 95.0)]
    snapshot = progress.snapshot(running, queued=0, workers=2)

    assert snapshot["eta_s"] == 90.0


def test_progress_write_is_throttled_between_completions(tmp_path):
    """Verifies repeated writes without a status change are throttled unless forced."""
    progress = GpuProgressFile(tmp_path / "p.json", jobs=_progress_jobs(tmp_path, ["a", "b"]), logger=SilentLogger())

    progress.write(progress.snapshot([], 2, 1))
    stamp = (tmp_path / "p.json").stat().st_mtime_ns

    progress.write(progress.snapshot([], 1, 1))
    assert (tmp_path / "p.json").stat().st_mtime_ns == stamp

    progress.write(progress.snapshot([], 1, 1), force=True)
    assert json.loads((tmp_path / "p.json").read_text())["queued"] == 1


def test_a_unit_status_change_bypasses_the_write_throttle(tmp_path):
    """Verifies a unit changing status forces the snapshot to disk."""
    progress = GpuProgressFile(tmp_path / "p.json", jobs=_progress_jobs(tmp_path, ["a", "b"]), logger=SilentLogger())

    progress.write(progress.snapshot([], 2, 1))
    progress.write(progress.snapshot([_running(tmp_path, "a", 0, 1.0)], 1, 1))

    units = json.loads((tmp_path / "p.json").read_text())["units"]
    assert [unit["status"] for unit in units] == ["running", "queued"]


def test_completion_logs_a_progress_line_with_eta(tmp_path):
    """Verifies each completion logs an indexed progress line, with an ETA once one is known."""
    recorder     = RecordingLogger()
    queue, _pool = _pool_queue(tmp_path, [0], recorder)
    queue.run([_job(tmp_path, f"j{i}", _ok_command()) for i in range(2)])

    lines = [line for line in recorder.infos if line.startswith("[")]
    assert any(line.startswith("[1/2]") for line in lines)
    assert any(line.startswith("[2/2]") and "ETA" in line for line in lines)


def test_signal_handlers_restored_after_run(tmp_path):
    """Verifies SIGTERM and SIGINT handlers are restored once the run ends."""
    before_term = signal.getsignal(signal.SIGTERM)
    before_int  = signal.getsignal(signal.SIGINT)

    queue = GpuQueue(gpus=[0], logger=SilentLogger(), poll_interval_s=0.0, handle_signals=True)
    queue.run([_job(tmp_path, "a", _ok_command())])

    assert signal.getsignal(signal.SIGTERM) is before_term
    assert signal.getsignal(signal.SIGINT)  is before_int
