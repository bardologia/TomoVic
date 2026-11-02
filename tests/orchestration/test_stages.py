"""Tests covering the queued training and inference stages: item ordering, resume semantics against completion markers, purging of unfinished output, and derived run paths."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from types   import SimpleNamespace

import pytest

from tools.orchestration.gpu_queue import GpuJob
from tools.orchestration.stages    import QueuedInferenceStage, QueuedTrainingStage
from tools.runtime.completion      import CompletionMarker

from tests.conftest import SilentLogger


@pytest.fixture
def logger():
    """Returns a logger that discards every message."""
    return SilentLogger()


def _config(tmp_path: Path, resume: bool = False) -> SimpleNamespace:
    """Builds a stage config with two devices, a run log base under tmp_path, and the given resume flag."""
    return SimpleNamespace(
        gpus            = [0, 1],
        gpus_file       = "",
        poll_interval_s = 0.0,
        resume          = resume,
        paths           = SimpleNamespace(log_base_dir=str(tmp_path / "runs")),
        training        = SimpleNamespace(epochs=3, batch_size=8, resume=False),
        inference       = SimpleNamespace(split="val"),
    )


def _mark_complete(directory: Path) -> None:
    """Stamps a completion marker on a directory, creating it if needed."""
    directory.mkdir(parents=True, exist_ok=True)
    CompletionMarker.stamp(directory, {"stage": "test"})


def _mark_inference_complete(directory: Path, split: str) -> None:
    """Stamps an inference completion marker recording the split it covers."""
    directory.mkdir(parents=True, exist_ok=True)
    CompletionMarker.stamp(directory, {"stage": "inference", "split": split})


def _ran_result(name: str, gpu: int = 0, status: str = "DONE", returncode: int = 0) -> dict:
    """Returns a queue result dict for a job of the given name, status, and return code."""
    return {
        "name"       : name,
        "gpu"        : gpu,
        "status"     : status,
        "returncode" : returncode,
        "duration_s" : 1.0,
        "log_file"   : f"/logs/{name}.log",
    }


def _patch_queue(stage, recorder: list):
    """Replaces the stage's queue runner with one that records dispatched job names and reports success.

    Args:
        stage    : Stage whose queue call is replaced.
        recorder : List appended with the job-name list of every dispatch.
    """
    def fake_run_queue(jobs):
        """Records the dispatched job names and reports every job as done."""
        recorder.append([job.name for job in jobs])
        return [_ran_result(job.name) for job in jobs]

    stage._run_queue = fake_run_queue


def test_a_reused_inference_unit_keeps_its_recorded_duration(tmp_path, logger):
    """Verifies the inference stage carries a reused unit's recorded duration as the training stage does."""
    config = _config(tmp_path, resume=True)
    stage  = QueuedInferenceStage(config=config, entry_script=Path("entry.py"), run_tag="t1", items=["model"], logger=logger)

    _mark_complete(stage.stage_dir / "model")
    _mark_inference_complete(stage.stage_dir / "model" / "inference" / "run0", "val")
    stage.results_path.parent.mkdir(parents=True)
    stage.results_path.write_text(json.dumps([{**_ran_result("model", gpu=1), "duration_s": 7.5}]))
    _patch_queue(stage, [])

    results = stage.run()

    assert results[0]["duration_s"] == 7.5
    assert results[0]["gpu"]        == 1
    assert results[0]["reused"]     is True


def test_training_job_hands_the_worker_the_unit_directory(tmp_path, logger):
    """Verifies a unit found under another directory name is handed to the worker as its run name and logs there."""
    config = _config(tmp_path, resume=True)
    stage  = QueuedTrainingStage(config=config, entry_script=Path("entry.py"), run_tag="t1", items=["m"], logger=logger, unit_dirs={"m": "old_label_m"})

    job = stage._job("m")

    assert job.command[job.command.index("--run-name") + 1] == "old_label_m"
    assert job.log_path == stage.stage_dir / "old_label_m" / "worker.log"
    assert stage.unit_dir("m") == stage.stage_dir / "old_label_m"


def test_training_job_defaults_the_run_name_to_the_unit_name(tmp_path, logger):
    """Verifies a fresh unit is handed its own name as the run name."""
    stage = QueuedTrainingStage(config=_config(tmp_path), entry_script=Path("entry.py"), run_tag="t1", items=["m"], logger=logger)

    job = stage._job("m")

    assert job.command[job.command.index("--run-name") + 1] == "m"


def test_trainer_state_name_matches_the_trainer(tmp_path):
    """Verifies the stage looks for the same rolling state file the trainer writes."""
    from tools.training.checkpoint import TrainerState

    assert QueuedTrainingStage.TRAINER_STATE == TrainerState.FILENAME


def test_training_job_command_carries_run_metadata(tmp_path, logger):
    """Verifies the training job command carries the worker mode, model name, and run tag."""
    stage = QueuedTrainingStage(config=_config(tmp_path), entry_script=Path("entry.py"), run_tag="rt", items=["mod"], logger=logger)
    job   = stage._job("mod")

    assert job.name == "mod"
    assert "--worker"  in job.command
    assert "train"     in job.command
    assert "--model"   in job.command
    assert "mod"       in job.command
    assert "--run-tag" in job.command
    assert "rt"        in job.command


def test_inference_skips_items_without_completed_training(tmp_path, logger):
    """Verifies inference skips items whose training never completed."""
    items = ["trained", "interrupted"]
    stage = QueuedInferenceStage(config=_config(tmp_path), entry_script=Path("entry.py"), run_tag="t1", items=items, logger=logger)

    _mark_complete(stage.stage_dir / "trained")

    interrupted_dir = stage.stage_dir / "interrupted"
    interrupted_dir.mkdir(parents=True)
    (interrupted_dir / "best_model.pt").write_text("x")

    recorder = []
    _patch_queue(stage, recorder)

    results = stage.run()

    assert recorder == [["trained"]]

    by_name = {r["name"]: r for r in results}
    assert by_name["trained"]["status"]     == "DONE"
    assert by_name["interrupted"]["status"] == "SKIPPED"
    assert [r["name"] for r in results] == items


def test_inference_reuses_existing_inference_on_resume(tmp_path, logger):
    """Verifies resume reuses an inference output already stamped for the requested split."""
    items  = ["model"]
    config = _config(tmp_path, resume=True)
    stage  = QueuedInferenceStage(config=config, entry_script=Path("entry.py"), run_tag="t1", items=items, logger=logger)

    _mark_complete(stage.stage_dir / "model")
    _mark_inference_complete(stage.stage_dir / "model" / "inference" / "run0", "val")

    recorder = []
    _patch_queue(stage, recorder)

    results = stage.run()

    assert recorder == []
    assert results[0]["status"]     == "DONE"
    assert results[0]["returncode"] == 0


def test_inference_for_another_split_is_not_reused(tmp_path, logger):
    """Verifies an inference stamped for a different split is re-run."""
    items  = ["model"]
    config = _config(tmp_path, resume=True)
    stage  = QueuedInferenceStage(config=config, entry_script=Path("entry.py"), run_tag="t1", items=items, logger=logger)

    _mark_complete(stage.stage_dir / "model")
    _mark_inference_complete(stage.stage_dir / "model" / "inference" / "run0", "test")

    recorder = []
    _patch_queue(stage, recorder)

    stage.run()

    assert recorder == [["model"]]


def test_inference_unfinished_output_is_not_reused_and_gets_purged(tmp_path, logger):
    """Verifies an unmarked inference directory is purged and the item re-dispatched."""
    items  = ["model"]
    config = _config(tmp_path, resume=True)
    stage  = QueuedInferenceStage(config=config, entry_script=Path("entry.py"), run_tag="t1", items=items, logger=logger)

    _mark_complete(stage.stage_dir / "model")

    inf_dir = stage.stage_dir / "model" / "inference" / "run0"
    inf_dir.mkdir(parents=True)
    (inf_dir / "metrics.json").write_text("{}")

    recorder = []
    _patch_queue(stage, recorder)

    stage.run()

    assert recorder == [["model"]]
    assert not inf_dir.exists()


def test_inference_no_resume_reruns_despite_existing_inference(tmp_path, logger):
    """Verifies resume off re-runs inference while leaving the prior output directory."""
    items  = ["model"]
    config = _config(tmp_path, resume=False)
    stage  = QueuedInferenceStage(config=config, entry_script=Path("entry.py"), run_tag="t1", items=items, logger=logger)

    _mark_complete(stage.stage_dir / "model")
    _mark_inference_complete(stage.stage_dir / "model" / "inference" / "run0", "val")

    recorder = []
    _patch_queue(stage, recorder)

    stage.run()
    assert recorder == [["model"]]
    assert (stage.stage_dir / "model" / "inference" / "run0").exists()


def test_inference_mixed_skip_cached_pending(tmp_path, logger):
    """Verifies pending, cached, and untrained items are dispatched, reused, and skipped respectively."""
    items  = ["pending", "cached", "skipped"]
    config = _config(tmp_path, resume=True)
    stage  = QueuedInferenceStage(config=config, entry_script=Path("entry.py"), run_tag="t1", items=items, logger=logger)

    for name in ("pending", "cached"):
        _mark_complete(stage.stage_dir / name)

    _mark_inference_complete(stage.stage_dir / "cached" / "inference" / "r0", "val")

    recorder = []
    _patch_queue(stage, recorder)

    results = stage.run()

    assert recorder == [["pending"]]

    by_name = {r["name"]: r for r in results}
    assert by_name["pending"]["status"] == "DONE"
    assert by_name["cached"]["status"]  == "DONE"
    assert by_name["skipped"]["status"] == "SKIPPED"
    assert [r["name"] for r in results] == items


def test_run_dir_derived_from_config_and_run_tag(tmp_path, logger):
    """Verifies the run directory and results path follow the config log base and the run tag."""
    config = _config(tmp_path)
    stage  = QueuedTrainingStage(config=config, entry_script=Path("entry.py"), run_tag="myrun", items=["a"], logger=logger)

    assert stage.run_dir == Path(config.paths.log_base_dir) / "myrun"
    assert stage.results_path == stage.run_dir / "pipeline" / "training_results.json"


def test_run_queue_hands_the_live_pool_to_the_stages_that_follow(tmp_path, logger):
    """Verifies a pool edited while a stage ran replaces the configured selection, so the next stage inherits it."""
    config = _config(tmp_path)
    stage  = QueuedTrainingStage(config=config, entry_script=Path("entry.py"), run_tag="t1", items=["m"], logger=logger)

    stage.pool_file.parent.mkdir(parents=True, exist_ok=True)
    stage.pool_file.write_text(json.dumps({"gpus": [3]}))

    results = stage._run_queue([GpuJob(name="m", command=[sys.executable, "-c", "pass"], log_path=tmp_path / "m.log")])

    assert config.gpus       == [3]
    assert results[0]["gpu"] == 3
