"""Experiment stages that fan worker subprocesses out over a GPU queue.

Provides the shared stage base and the queued training and inference stages,
which skip units already carrying a completion marker, purge half-written ones,
and write a per-stage results JSON.
"""

from __future__ import annotations

import shutil
import sys
from dataclasses import asdict
from pathlib     import Path

from tools.data.io            import FileIO
from tools.monitoring.logger  import Logger
from tools.runtime.completion import CompletionMarker

from tools.orchestration.gpu_queue import GpuJob, GpuPoolFile, GpuQueue


class ExperimentStage:
    """Base for stages that dispatch worker subprocesses through a GPU queue.

    Attributes:
        config: Experiment config supplying gpus, poll interval and paths.
        entry_script: Entry point re-invoked in worker mode, if the stage uses one.
        run_tag: Tag identifying the experiment run.
        logger: Logger for stage progress and failures.
        run_dir: Root directory of the run.
        pool_file: Live-editable GPU pool file for this run.
    """

    def __init__(self, config, run_tag: str, logger: Logger, entry_script: Path | None = None, run_dir: Path | None = None, pool_file: Path | None = None) -> None:
        """Initializes the stage and resolves its run directory and GPU pool file.

        Args:
            config: Experiment config with gpus, poll_interval_s, gpus_file and paths.
            run_tag: Tag identifying the run; also the default run-directory name.
            logger: Logger for stage messages.
            entry_script: Entry point workers are launched from.
            run_dir: Run root; defaults to the configured log base directory plus run_tag.
            pool_file: GPU pool file; defaults to the configured or per-run location.
        """
        self.config       = config
        self.entry_script = entry_script
        self.run_tag      = run_tag
        self.logger       = logger
        self.run_dir      = Path(run_dir) if run_dir is not None else Path(config.paths.log_base_dir) / run_tag
        self.pool_file    = Path(pool_file) if pool_file is not None else GpuPoolFile.resolve(config.gpus_file, self.run_dir)

    def _run_queue(self, jobs: list[GpuJob]) -> list[dict]:
        """Runs the jobs on a GPU queue and returns their results as dictionaries."""
        queue = GpuQueue(gpus=self.config.gpus, logger=self.logger, poll_interval_s=self.config.poll_interval_s, pool_file=self.pool_file)
        return [asdict(result) for result in queue.run(jobs)]

    def _order_results(self, results: list[dict], names: list[str]) -> list[dict]:
        """Returns the results reordered to follow the requested unit-name order."""
        by_name = {result["name"]: result for result in results}
        return [by_name[name] for name in names if name in by_name]

    def _write_results(self, results, path: Path) -> None:
        """Saves the stage results as indented JSON at the given path."""
        FileIO.save_json(results, path, indent=2)

    def _log_failures(self, failed: list[dict], name_key: str = "name") -> None:
        """Logs one error line per failed unit, pointing at its worker log."""
        for result in failed:
            log_hint = f"  (see {result['log_file']})" if result["log_file"] else ""
            self.logger.error(f"FAILED  {result[name_key]}{log_hint}")


class QueuedStage(ExperimentStage):
    """Stage that turns a list of item names into one worker job each.

    Attributes:
        items: Unit names, one worker job per name.
        stage_dir: Directory holding one subdirectory per unit.
        results_path: Location of the stage results JSON.
    """

    stage_subdir     : str = "training"
    worker_action    : str = ""
    worker_logname   : str = "worker.log"
    results_filename : str = ""

    def __init__(self, config, entry_script: Path, run_tag: str, items: list[str], logger: Logger) -> None:
        """Initializes the stage and derives its stage and results locations.

        Args:
            config: Experiment config shared with the base stage.
            entry_script: Entry point re-invoked in worker mode.
            run_tag: Tag identifying the run.
            items: Unit names to process, one worker job per name.
            logger: Logger for stage messages.
        """
        super().__init__(config=config, run_tag=run_tag, logger=logger, entry_script=entry_script)
        self.items        = items
        self.stage_dir    = self.run_dir / self.stage_subdir
        self.results_path = self.run_dir / "pipeline" / self.results_filename

    def _job(self, item: str) -> GpuJob:
        """Returns the worker job that processes one unit."""
        return GpuJob(
            name     = item,
            command  = [sys.executable, str(self.entry_script), "--worker", self.worker_action, self._worker_flag(), self._worker_value(item), "--run-tag", self.run_tag, "--run-dir", str(self.run_dir)],
            log_path = self.stage_dir / item / self.worker_logname,
        )

    def _worker_flag(self) -> str:
        """Returns the CLI flag that carries the unit identity to the worker."""
        return "--model"

    def _worker_value(self, item: str) -> str:
        """Returns the value passed with the worker flag for this unit."""
        return item


class QueuedTrainingStage(QueuedStage):
    """Training stage that reuses completed units and restarts unfinished ones."""

    worker_action    : str = "train"
    summary_title    : str = "Training summary"
    worker_logname   : str = "worker.log"
    results_filename : str = "training_results.json"

    def _config_kv(self) -> dict:
        """Returns the training configuration summary logged before the queue starts."""
        return {
            "Items"      : len(self.items),
            "Epochs"     : self.config.training.epochs,
            "Batch size" : f"{self.config.training.batch_size} (base; a max_batch probe stage overrides it per model, see each worker's [Loaders] table)",
            "GPUs"       : self.config.gpus,
            "Stage dir"  : str(self.stage_dir),
        }

    def _is_complete(self, item: str) -> bool:
        """Returns whether resume is on and the unit carries a completion marker."""
        if not self.config.resume:
            return False

        return CompletionMarker.is_complete(self.stage_dir / item)

    def _purge_unfinished(self, item: str) -> None:
        """Deletes a resumed unit's directory when it holds no completion marker."""
        item_dir = self.stage_dir / item
        if not self.config.resume or not item_dir.is_dir():
            return

        self.logger.warning(f"{item}: unfinished run detected, deleting and restarting")
        shutil.rmtree(item_dir)

    def _cached_result(self, item: str) -> dict:
        """Returns a synthetic DONE result standing in for a reused training run."""
        return {
            "name"       : item,
            "gpu"        : None,
            "status"     : "DONE",
            "returncode" : 0,
            "duration_s" : None,
            "log_file"   : str(self.stage_dir / item / self.worker_logname),
        }

    def _log_summary(self, results: list[dict]) -> None:
        """Logs the done and failed counts, then one line per failed unit."""
        done   = [r for r in results if r["status"] == "DONE"]
        failed = [r for r in results if r["status"] != "DONE"]

        self.logger.subsection(self.summary_title)
        self.logger.kv_table({
            "Total"  : len(results),
            "Done"   : len(done),
            "Failed" : len(failed),
        }, title=f"{len(done)}/{len(results)} finished")

        self._log_failures(failed)

    def run(self) -> list[dict]:
        """Trains every pending unit on the GPU queue and writes the stage results.

        Units already carrying a completion marker are reused; unfinished
        directories are deleted before their unit is queued again.

        Returns:
            One result dictionary per unit, in the order the items were given.
        """
        self.logger.section("Training queue")
        self.logger.kv_table(self._config_kv(), title="Configuration")

        cached  = [item for item in self.items if self._is_complete(item)]
        pending = [item for item in self.items if item not in cached]

        for item in cached:
            self.logger.info(f"{item}: completed run reused")

        for item in pending:
            self._purge_unfinished(item)

        ran = []
        if pending:
            ran = self._run_queue([self._job(item) for item in pending])

        results = self._order_results(ran + [self._cached_result(item) for item in cached], self.items)

        self._write_results(results, self.results_path)
        self._log_summary(results)

        return results


class QueuedInferenceStage(QueuedStage):
    """Inference stage that skips units whose training never completed."""

    worker_action    : str = "infer"
    summary_title    : str = "Inference summary"
    worker_logname   : str = "inference_worker.log"
    results_filename : str = "inference_results.json"

    def _config_kv(self) -> dict:
        """Returns the inference configuration summary logged before the queue starts."""
        return {
            "Items" : len(self.items),
            "Split" : self.config.inference.split,
            "GPUs"  : self.config.gpus,
        }

    def _training_complete(self, item: str) -> bool:
        """Returns whether the unit's training directory carries a completion marker."""
        return CompletionMarker.is_complete(self.stage_dir / item)

    def _has_inference(self, item: str) -> bool:
        """Returns whether a completed inference for the configured split already exists."""
        if not self.config.resume:
            return False

        inference_dir = self.stage_dir / item / "inference"
        if not inference_dir.is_dir():
            return False

        completed = [candidate for candidate in inference_dir.iterdir() if candidate.is_dir() and CompletionMarker.is_complete(candidate)]

        return any(CompletionMarker.payload(candidate)["split"] == self.config.inference.split for candidate in completed)

    def _purge_unfinished(self, item: str) -> None:
        """Deletes every unmarked inference output directory of a resumed unit."""
        inference_dir = self.stage_dir / item / "inference"
        if not self.config.resume or not inference_dir.is_dir():
            return

        for candidate in inference_dir.iterdir():
            if candidate.is_dir() and not CompletionMarker.is_complete(candidate):
                self.logger.warning(f"{item}: unfinished inference '{candidate.name}' deleted before rerun")
                shutil.rmtree(candidate)

    def _static_result(self, item: str, status: str) -> dict:
        """Returns a synthetic result for a unit that was reused or skipped.

        Args:
            item: Unit name.
            status: Either DONE for a reused inference or SKIPPED for one not run.

        Returns:
            Result dictionary matching the shape produced by the GPU queue.
        """
        return {
            "name"       : item,
            "gpu"        : None,
            "status"     : status,
            "returncode" : 0 if status == "DONE" else None,
            "duration_s" : None,
            "log_file"   : str(self.stage_dir / item / self.worker_logname),
        }

    def _log_summary(self, results: list[dict]) -> None:
        """Logs the done, failed and skipped counts, then one line per failed unit."""
        done   = [r for r in results if r["status"] == "DONE"]
        failed = [r for r in results if r["status"] == "FAILED"]

        self.logger.subsection(self.summary_title)
        self.logger.kv_table({
            "Total"   : len(results),
            "Done"    : len(done),
            "Failed"  : len(failed),
            "Skipped" : len(results) - len(done) - len(failed),
        }, title=f"{len(done)}/{len(results)} finished")

        self._log_failures(failed)

    def run(self) -> list[dict]:
        """Runs inference for every eligible unit and writes the stage results.

        Units without completed training are skipped, units that already hold a
        completed inference for the configured split are reused, and unfinished
        inference directories are deleted before their unit is queued again.

        Returns:
            One result dictionary per unit, in the order the items were given.
        """
        self.logger.section("Batch inference")
        self.logger.kv_table(self._config_kv(), title="Configuration")

        skipped = [item for item in self.items if not self._training_complete(item)]
        cached  = [item for item in self.items if item not in skipped and self._has_inference(item)]
        pending = [item for item in self.items if item not in skipped and item not in cached]

        for item in skipped:
            self.logger.warning(f"{item}: training incomplete, inference skipped")

        for item in cached:
            self.logger.info(f"{item}: existing inference reused")

        for item in pending:
            self._purge_unfinished(item)

        ran = []
        if pending:
            ran = self._run_queue([self._job(item) for item in pending])

        results = ran + [self._static_result(item, "DONE") for item in cached] + [self._static_result(item, "SKIPPED") for item in skipped]
        results = self._order_results(results, self.items)

        self._write_results(results, self.results_path)
        self._log_summary(results)

        return results
