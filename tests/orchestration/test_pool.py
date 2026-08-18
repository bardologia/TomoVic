"""Tests covering ProcessPoolRunner: job/result pairing, worker limits, error propagation, and per-completion logging."""

from __future__ import annotations

import pytest

from tools.orchestration.pool import ProcessPoolRunner

from tests.conftest import SilentLogger


def _square(x):
    """Returns the square of the job value."""
    return x * x


def _identity(x):
    """Returns the job value unchanged."""
    return x


def _raise_on_three(x):
    """Returns the job value, raising for the value three."""
    if x == 3:
        raise ValueError(f"boom at {x}")
    return x


def _const(_x):
    """Returns the constant 42 regardless of the job."""
    return 42


def _label(job):
    """Returns the display label for a job."""
    return f"job {job}"


class RecordingLogger(SilentLogger):
    """Logger stub collecting the subsection and error lines the runner emits.

    Attributes:
        subsections: Per-completion lines received.
        errors: Failure lines received.
    """
    def __init__(self):
        """Creates the empty message buffers."""
        self.subsections = []
        self.errors      = []

    def subsection(self, message, *args, **kwargs):
        """Stores a subsection line."""
        self.subsections.append(str(message))

    def error(self, message, *args, **kwargs):
        """Stores an error line."""
        self.errors.append(str(message))


@pytest.fixture
def logger():
    """Returns a logger that discards every message."""
    return SilentLogger()


def test_empty_jobs_returns_empty(logger):
    """Verifies an empty job list produces no results."""
    runner  = ProcessPoolRunner(logger=logger, max_workers=2)
    results = runner.run([], _square, _label)

    assert results == []


def test_results_pair_job_with_result(logger):
    """Verifies each result is paired with the job that produced it."""
    runner  = ProcessPoolRunner(logger=logger, max_workers=2)
    results = runner.run([1, 2, 4], _square, _label)

    assert dict(results) == {1: 1, 2: 4, 4: 16}


def test_parallel_matches_serial(logger):
    """Verifies parallel execution reproduces the serial mapping exactly."""
    jobs    = list(range(8))
    serial  = {job: _square(job) for job in jobs}

    runner  = ProcessPoolRunner(logger=logger, max_workers=4)
    results = dict(runner.run(jobs, _square, _label))

    assert results == serial


def test_each_job_appears_once(logger):
    """Verifies every submitted job comes back exactly once."""
    jobs    = [10, 20, 30, 40]
    runner  = ProcessPoolRunner(logger=logger, max_workers=3)
    results = runner.run(jobs, _identity, _label)

    returned_jobs = [job for job, _ in results]
    assert sorted(returned_jobs) == sorted(jobs)
    assert len(results) == len(jobs)


def test_error_propagates(logger):
    """Verifies an exception raised inside a worker surfaces to the caller."""
    runner = ProcessPoolRunner(logger=logger, max_workers=2)

    with pytest.raises(ValueError):
        runner.run([1, 2, 3, 4], _raise_on_three, _label)


def test_max_workers_capped_to_job_count(logger):
    """Verifies a worker count above the job count still runs every job."""
    runner = ProcessPoolRunner(logger=logger, max_workers=64)

    assert dict(runner.run([5, 6], _square, _label)) == {5: 25, 6: 36}


def test_single_worker_runs_all_jobs(logger):
    """Verifies a single worker completes the whole job list."""
    runner  = ProcessPoolRunner(logger=logger, max_workers=1)
    results = dict(runner.run([1, 2, 3], _square, _label))

    assert results == {1: 1, 2: 4, 3: 9}


def test_unbounded_workers_when_none(logger):
    """Verifies an unset worker limit runs the jobs to completion."""
    runner  = ProcessPoolRunner(logger=logger, max_workers=None)
    results = dict(runner.run([2, 3], _square, _label))

    assert results == {2: 4, 3: 9}


def test_empty_jobs_with_unbounded_workers_returns_empty(logger):
    """Verifies an empty job list with no worker limit produces no results."""
    runner  = ProcessPoolRunner(logger=logger, max_workers=None)
    results = runner.run([], _square, _label)

    assert results == []


def test_each_completion_is_logged():
    """Verifies one progress line is logged per completed job, carrying the running count."""
    recorder = RecordingLogger()
    runner   = ProcessPoolRunner(logger=recorder, max_workers=2)

    runner.run([1, 2, 3], _square, _label)

    assert len(recorder.subsections) == 3
    assert sorted(line.split(" completed")[0] for line in recorder.subsections) == ["Job job 1", "Job job 2", "Job job 3"]
    assert all("/3," in line for line in recorder.subsections)


def test_failing_job_is_named_in_the_log():
    """Verifies the failing job's label appears in the logged error."""
    recorder = RecordingLogger()
    runner   = ProcessPoolRunner(logger=recorder, max_workers=1)

    with pytest.raises(ValueError):
        runner.run([3], _raise_on_three, _label)

    assert len(recorder.errors) == 1
    assert "job 3" in recorder.errors[0]


def test_iterable_input_is_consumed(logger):
    """Verifies a plain iterator of jobs is consumed and mapped."""
    runner  = ProcessPoolRunner(logger=logger, max_workers=2)
    results = dict(runner.run(iter([1, 2, 3]), _const, _label))

    assert results == {1: 42, 2: 42, 3: 42}
