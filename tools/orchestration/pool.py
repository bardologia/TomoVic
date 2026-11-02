"""Process-pool runner that fans jobs out to spawned workers and fails fast.

Used by CPU-bound pipeline stages that need parallelism without the GPU pinning
of the GPU queue.
"""

from __future__ import annotations

import multiprocessing as mp
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from typing             import Any, Callable, Iterable

from tools.monitoring.logger import Logger


class ProcessPoolRunner:
    """Runs a callable over a job list in a spawned process pool.

    Attributes:
        logger      : Logger for per-job completion and failure messages.
        max_workers : Upper bound on pool size; None uses one worker per job.
    """

    def __init__(self, logger: Logger, max_workers: int | None = None) -> None:
        """Initializes the runner with its logger and worker cap."""
        self.logger      = logger
        self.max_workers = max_workers

    def run(self, jobs: Iterable[Any], worker_fn: Callable[[Any], Any], label_fn: Callable[[Any], str]) -> list[tuple[Any, Any]]:
        """Executes worker_fn on every job in parallel and returns the paired results.

        Args:
            jobs      : Job descriptors, each passed whole to worker_fn.
            worker_fn : Picklable callable executed in a spawned worker process.
            label_fn  : Maps a job to the name used in log messages.

        Returns:
            List of (job, result) pairs in completion order.

        Raises:
            Exception : Re-raises the first worker failure after cancelling the queued futures and waiting, with a warning naming them, for those already running.
        """
        job_list = list(jobs)
        workers  = max(1, min(self.max_workers, len(job_list)) if self.max_workers is not None else len(job_list))
        results  : list[tuple[Any, Any]] = []
        started  = time.perf_counter()

        with ProcessPoolExecutor(max_workers=workers, mp_context=mp.get_context("spawn")) as executor:
            futures = {executor.submit(worker_fn, job): job for job in job_list}

            for future in as_completed(futures):
                job = futures[future]

                try:
                    result = future.result()
                except Exception as error:
                    self.logger.error(f"Job {label_fn(job)} failed after {time.perf_counter() - started:.1f} s with {len(results)}/{len(job_list)} jobs already finished: {error}")
                    for other in futures:
                        other.cancel()

                    in_flight = [label_fn(futures[other]) for other in futures if other.running()]
                    if in_flight:
                        self.logger.warning(f"Waiting for {len(in_flight)} in-flight job(s) to finish before re-raising, since a running worker cannot be cancelled: {', '.join(in_flight)}")
                    raise

                results.append((job, result))
                self.logger.subsection(f"Job {label_fn(job)} completed ({len(results)}/{len(job_list)}, {time.perf_counter() - started:.1f} s elapsed)")

        return results
