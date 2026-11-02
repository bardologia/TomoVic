"""Experiment stages that fan worker subprocesses out over a GPU queue.

Provides the shared stage base and the queued training and inference stages,
which reuse units already carrying a completion marker, resume or restart
half-written ones, hand every worker the exact directory of its unit, and
write a per-stage results JSON. The status report lists what each unit holds
before a stage launches anything.
"""

from __future__ import annotations

import shutil
import sys
from dataclasses import asdict
from pathlib     import Path
from typing      import Callable

from tools.data.io            import FileIO
from tools.monitoring.logger  import Logger
from tools.runtime.completion import CompletionMarker

from tools.orchestration.gpu_queue import GpuJob, GpuPoolFile, GpuQueue


class ExperimentStage:
    """Base for stages that dispatch worker subprocesses through a GPU queue.

    Attributes:
        config       : Experiment config supplying gpus, poll interval and paths.
        entry_script : Entry point re-invoked in worker mode, if the stage uses one.
        run_tag      : Tag identifying the experiment run.
        logger       : Logger for stage progress and failures.
        run_dir      : Root directory of the run.
        pool_file    : Live-editable GPU pool file for this run.
    """

    def __init__(self, config, run_tag: str, logger: Logger, entry_script: Path | None = None, run_dir: Path | None = None, pool_file: Path | None = None) -> None:
        """Initializes the stage and resolves its run directory and GPU pool file.

        Args:
            config       : Experiment config with gpus, poll_interval_s, gpus_file and paths.
            run_tag      : Tag identifying the run; also the default run-directory name.
            logger       : Logger for stage messages.
            entry_script : Entry point workers are launched from.
            run_dir      : Run root; defaults to the configured log base directory plus run_tag.
            pool_file    : GPU pool file; defaults to the configured or per-run location.
        """
        self.config       = config
        self.entry_script = entry_script
        self.run_tag      = run_tag
        self.logger       = logger
        self.run_dir      = Path(run_dir) if run_dir is not None else Path(config.paths.log_base_dir) / run_tag
        self._pool_file   = Path(pool_file) if pool_file is not None else None

    @property
    def pool_file(self) -> Path:
        """Live-editable GPU pool file, resolved from the config on first use so a stage that runs no queue never reads gpus_file."""
        if self._pool_file is None:
            self._pool_file = GpuPoolFile.resolve(self.config.gpus_file, self.run_dir)
        return self._pool_file

    def _run_queue(self, jobs: list[GpuJob]) -> list[dict]:
        """Runs the jobs on a GPU queue and returns their results as dictionaries.

        The pool the queue ends with replaces the configured selection, so a
        resize applied while this pass ran governs the stages that follow it
        and the device lists they report.

        Args:
            jobs : Units to dispatch over the pool.

        Returns:
            One result dictionary per job, in completion order.
        """
        queue   = GpuQueue(gpus=self.config.gpus, logger=self.logger, poll_interval_s=self.config.poll_interval_s, pool_file=self.pool_file)
        results = queue.run(jobs)

        self.config.gpus = list(queue.gpus)

        return [asdict(result) for result in results]

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

    Every worker receives the directory of its unit relative to the stage
    directory through ``--run-name``, so a unit whose directory was found by
    its recorded identity keeps that directory whatever the current naming
    scheme would call it.

    Attributes:
        TRAINER_STATE : Name of the rolling trainer state a run resumes from, mirroring ``TrainerState.FILENAME``.
        items         : Unit names, one worker job per name.
        unit_dirs     : Existing directory per unit name, relative to the stage directory, for the units a resume found on disk.
        stage_dir     : Directory holding one subdirectory per unit.
        results_path  : Location of the stage results JSON.
    """

    TRAINER_STATE = "last.pt"

    stage_subdir     : str = "training"
    worker_action    : str = ""
    worker_logname   : str = "worker.log"
    results_filename : str = ""

    def __init__(self, config, entry_script: Path, run_tag: str, items: list[str], logger: Logger, unit_dirs: dict | None = None) -> None:
        """Initializes the stage and derives its stage and results locations.

        Args:
            config       : Experiment config shared with the base stage.
            entry_script : Entry point re-invoked in worker mode.
            run_tag      : Tag identifying the run.
            items        : Unit names to process, one worker job per name.
            logger       : Logger for stage messages.
            unit_dirs    : Existing directory per unit name, relative to the stage directory; units absent from it live under their own name.
        """
        super().__init__(config=config, run_tag=run_tag, logger=logger, entry_script=entry_script)
        self.items        = items
        self.unit_dirs    = dict(unit_dirs or {})
        self.stage_dir    = self.run_dir / self.stage_subdir
        self.results_path = self.run_dir / "pipeline" / self.results_filename

    def unit_name(self, item: str) -> str:
        """Returns the directory of a unit relative to the stage directory: the one found on disk, else the unit's own name."""
        return self.unit_dirs.get(item, item)

    def unit_dir(self, item: str) -> Path:
        """Returns the directory of a unit."""
        return self.stage_dir / self.unit_name(item)

    def _job(self, item: str) -> GpuJob:
        """Returns the worker job that processes one unit."""
        return GpuJob(
            name     = item,
            command  = [sys.executable, str(self.entry_script), "--worker", self.worker_action, self._worker_flag(), self._worker_value(item), "--run-name", self.unit_name(item), "--run-tag", self.run_tag, "--run-dir", str(self.run_dir)],
            log_path = self.unit_dir(item) / self.worker_logname,
        )

    def _worker_flag(self) -> str:
        """Returns the CLI flag that carries the unit identity to the worker."""
        return "--model"

    def _worker_value(self, item: str) -> str:
        """Returns the value passed with the worker flag for this unit."""
        return item

    def _training_complete(self, item: str) -> bool:
        """Returns whether the unit's directory carries a training completion marker."""
        return CompletionMarker.is_complete(self.unit_dir(item))

    def _resumable(self, item: str) -> bool:
        """Returns whether an unfinished unit can continue from its trainer state.

        Args:
            item : Unit name.

        Returns:
            True when the trainer resume is on and the unit directory holds the rolling trainer state.
        """
        return bool(self.config.training.resume) and (self.unit_dir(item) / self.TRAINER_STATE).is_file()

    def _scored_splits(self) -> list[str]:
        """Returns the dataset splits whose inference completion the status report lists."""
        return [self.config.inference.split]

    def _dispatch(self, items: list[str]) -> list[dict]:
        """Runs the given units on the GPU queue and returns their results, marked as run by this launch."""
        if not items:
            return []

        return [{**result, "reused": False} for result in self._run_queue([self._job(item) for item in items])]

    def _reused(self, items: list[str], synthetic: Callable[[str], dict]) -> list[dict]:
        """Returns the results of reused units, keeping the device, duration and return code an earlier launch recorded.

        A reused unit is not run again, so its stand-in result knows neither
        where nor how long it ran; the results file the earlier launch wrote
        does, and is read before this launch replaces it.

        Args:
            items     : Names of the reused units.
            synthetic : Builds the stand-in result of one unit.

        Returns:
            One result per unit, marked reused.
        """
        if not items:
            return []

        earlier = {result["name"]: result for result in FileIO.load_json(self.results_path)} if self.results_path.is_file() else {}
        results = []
        carried = 0

        for item in items:
            result = {**synthetic(item), "reused": True}
            if item in earlier and earlier[item]["status"] == "DONE":
                result["gpu"]        = earlier[item]["gpu"]
                result["duration_s"] = earlier[item]["duration_s"]
                result["returncode"] = earlier[item]["returncode"]
                carried             += 1
            results.append(result)

        self.logger.info(f"{carried} of {len(items)} reused unit(s) keep the GPU and duration recorded in {self.results_path}; {len(items) - carried} have none on record")

        return results

    def _inference_base(self, directory: Path) -> Path:
        """Returns the directory holding a unit's inference stamps."""
        return directory / "inference"

    def status_report(self) -> "UnitStatusReport":
        """Returns the per-unit training and inference status of the stage directory."""
        return UnitStatusReport(
            items          = self.items,
            unit_dir       = self.unit_dir,
            stage_dir      = self.stage_dir,
            splits         = self._scored_splits(),
            inference_base = self._inference_base,
            trainer_resume = bool(self.config.training.resume),
            resume         = bool(self.config.resume),
        )


class QueuedTrainingStage(QueuedStage):
    """Training stage that reuses completed units and resumes or restarts unfinished ones."""

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

        return self._training_complete(item)

    def _purge_unfinished(self, item: str) -> None:
        """Deletes a resumed unit's unfinished directory unless the trainer continues from its state.

        Args:
            item : Unit name.
        """
        item_dir = self.unit_dir(item)
        if not self.config.resume or not item_dir.is_dir():
            return

        if self._resumable(item):
            self.logger.info(f"{item}: unfinished run resumes from {self.TRAINER_STATE} in {item_dir}")
            return

        self.logger.warning(f"{item}: unfinished run detected, deleting {item_dir} and restarting")
        shutil.rmtree(item_dir)

    def _cached_result(self, item: str) -> dict:
        """Returns a synthetic DONE result standing in for a reused training run."""
        return {
            "name"       : item,
            "gpu"        : None,
            "status"     : "DONE",
            "returncode" : 0,
            "duration_s" : None,
            "log_file"   : str(self.unit_dir(item) / self.worker_logname),
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
        directories continue from their trainer state when the trainer resume
        is on and are deleted before their unit is queued again otherwise.

        Returns:
            One result dictionary per unit, in the order the items were given.
        """
        self.logger.section("Training queue")
        self.logger.kv_table(self._config_kv(), title="Configuration")

        self.status_report().log(self.logger, "Unit status")

        cached  = [item for item in self.items if self._is_complete(item)]
        pending = [item for item in self.items if item not in cached]

        for item in cached:
            self.logger.info(f"{item}: completed run reused")

        for item in pending:
            self._purge_unfinished(item)

        reused  = self._reused(cached, self._cached_result)
        ran     = self._dispatch(pending)
        results = self._order_results(ran + reused, self.items)

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

    def _has_inference(self, item: str) -> bool:
        """Returns whether a completed inference for the configured split already exists."""
        if not self.config.resume:
            return False

        inference_dir = self.unit_dir(item) / "inference"
        if not inference_dir.is_dir():
            return False

        completed = [candidate for candidate in inference_dir.iterdir() if candidate.is_dir() and CompletionMarker.is_complete(candidate)]

        return any(CompletionMarker.payload(candidate)["split"] == self.config.inference.split for candidate in completed)

    def _purge_unfinished(self, item: str) -> None:
        """Deletes every unmarked inference output directory of a resumed unit."""
        inference_dir = self.unit_dir(item) / "inference"
        if not self.config.resume or not inference_dir.is_dir():
            return

        for candidate in inference_dir.iterdir():
            if candidate.is_dir() and not CompletionMarker.is_complete(candidate):
                self.logger.warning(f"{item}: unfinished inference '{candidate.name}' deleted before rerun")
                shutil.rmtree(candidate)

    def _static_result(self, item: str, status: str) -> dict:
        """Returns a synthetic result for a unit that was reused or skipped.

        Args:
            item   : Unit name.
            status : Either DONE for a reused inference or SKIPPED for one not run.

        Returns:
            Result dictionary matching the shape produced by the GPU queue.
        """
        return {
            "name"       : item,
            "gpu"        : None,
            "status"     : status,
            "returncode" : 0 if status == "DONE" else None,
            "duration_s" : None,
            "log_file"   : str(self.unit_dir(item) / self.worker_logname),
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

        reused  = self._reused(cached, lambda item: self._static_result(item, "DONE"))
        ran     = self._dispatch(pending)
        results = ran + reused + [{**self._static_result(item, "SKIPPED"), "reused": False} for item in skipped]
        results = self._order_results(results, self.items)

        self._write_results(results, self.results_path)
        self._log_summary(results)

        return results


class UnitStatusReport:
    """Per-unit training and inference status of a stage, listed before anything launches.

    Attributes:
        items          : Unit names in launch order.
        unit_dir       : Callable returning the directory a unit lives or will live in.
        stage_dir      : Stage directory the unit directories are reported relative to.
        splits         : Dataset splits whose inference completion is reported, empty when the stage scores nothing.
        inference_base : Callable returning the directory holding a unit's inference stamps.
        trainer_resume : Whether unfinished units continue from their trainer state.
        resume         : Whether the stage reuses completed units; without it a completed unit refuses to train over its finished run and fails.
        trainer_state  : Name of the rolling trainer state file.
    """

    REFUSED = "complete, refused (resume off)"

    def __init__(self, items: list[str], unit_dir: Callable[[str], Path], stage_dir: Path, splits: list[str], inference_base: Callable[[Path], Path], trainer_resume: bool, resume: bool, trainer_state: str = QueuedStage.TRAINER_STATE) -> None:
        """Binds the report to the units of one stage and the rules that locate their artifacts."""
        self.items          = list(items)
        self.unit_dir       = unit_dir
        self.stage_dir      = Path(stage_dir)
        self.splits         = list(splits)
        self.inference_base = inference_base
        self.trainer_resume = trainer_resume
        self.resume         = resume
        self.trainer_state  = trainer_state

    def _training_status(self, directory: Path) -> str:
        """Returns the training status word of one unit directory."""
        if CompletionMarker.is_complete(directory):
            return "complete" if self.resume else self.REFUSED
        if not directory.is_dir():
            return "new"
        if self.trainer_resume and (directory / self.trainer_state).is_file():
            return "resumes from checkpoint"

        return "restarts"

    def _inference_status(self, directory: Path) -> str:
        """Returns the per-split inference status of one unit directory, or a dash when no split is scored."""
        if not self.splits:
            return "-"

        from pipelines.shared.inference.metadata import CompletedInference

        base  = self.inference_base(directory)
        words = [f"{split} {'done' if CompletedInference.latest(base, split) is not None else 'missing'}" for split in self.splits]

        return ", ".join(words)

    def rows(self) -> list[dict]:
        """Returns one row per unit with its directory, training status and inference status."""
        rows = []
        for item in self.items:
            directory = self.unit_dir(item)
            rows.append({
                "Unit"      : item,
                "Directory" : directory.relative_to(self.stage_dir).as_posix() if directory.is_dir() else "(new)",
                "Training"  : self._training_status(directory),
                "Inference" : self._inference_status(directory),
            })

        return rows

    def log(self, logger: Logger, title: str) -> None:
        """Logs the unit table and a one-line count of what the stage will do, warning about completed units that refuse to train with resume off."""
        rows      = self.rows()
        complete  = sum(1 for row in rows if row["Training"] == "complete")
        refused   = [row["Unit"] for row in rows if row["Training"] == self.REFUSED]
        resumed   = sum(1 for row in rows if row["Training"] == "resumes from checkpoint")
        fresh     = len(rows) - complete - len(refused) - resumed

        logger.subsection(title)
        logger.metrics_table(rows, columns=["Unit", "Directory", "Training", "Inference"])
        logger.info(f"{complete} unit(s) complete, {resumed} resume from their checkpoint, {fresh} train from scratch")

        if refused:
            logger.warning(f"resume is off: {len(refused)} completed unit(s) hold a finished run that is never overwritten in place, so they refuse to train and fail; set resume=True to reuse them or launch under a new run_tag: {', '.join(refused)}")
