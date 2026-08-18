"""Tests covering the queued training and inference stages: item ordering, resume semantics against completion markers, purging of unfinished output, and derived run paths."""

from __future__ import annotations

import json
from pathlib import Path
from types   import SimpleNamespace

import pytest

from tools.orchestration.stages import QueuedInferenceStage, QueuedTrainingStage
from tools.runtime.completion   import CompletionMarker

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
        training        = SimpleNamespace(epochs=3, batch_size=8),
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
        stage: Stage whose queue call is replaced.
        recorder: List appended with the job-name list of every dispatch.
    """
    def fake_run_queue(jobs):
        """Records the dispatched job names and reports every job as done."""
        recorder.append([job.name for job in jobs])
        return [_ran_result(job.name) for job in jobs]

    stage._run_queue = fake_run_queue


def test_training_runs_all_items_in_declared_order(tmp_path, logger):
    """Verifies training dispatches every item in declaration order."""
    items = ["m_c", "m_a", "m_b"]
    stage = QueuedTrainingStage(config=_config(tmp_path), entry_script=Path("entry.py"), run_tag="t1", items=items, logger=logger)

    recorder = []
    _patch_queue(stage, recorder)

    results = stage.run()

    assert recorder == [items]
    assert [r["name"] for r in results] == items


def test_training_results_ordered_by_items_not_completion(tmp_path, logger):
    """Verifies results are re-ordered to match the item list, not completion order."""
    items = ["x", "y", "z"]
    stage = QueuedTrainingStage(config=_config(tmp_path), entry_script=Path("entry.py"), run_tag="t1", items=items, logger=logger)

    def shuffled_run_queue(jobs):
        """Returns results in an order that does not match the item list."""
        return [_ran_result("z"), _ran_result("x"), _ran_result("y")]

    stage._run_queue = shuffled_run_queue

    results = stage.run()
    assert [r["name"] for r in results] == items


def test_training_writes_results_json(tmp_path, logger):
    """Verifies the stage persists its results to the results JSON in item order."""
    items = ["a", "b"]
    stage = QueuedTrainingStage(config=_config(tmp_path), entry_script=Path("entry.py"), run_tag="t1", items=items, logger=logger)
    _patch_queue(stage, [])

    stage.run()

    saved = json.loads(stage.results_path.read_text())
    assert [r["name"] for r in saved] == items


def test_training_skips_completed_items_on_resume(tmp_path, logger):
    """Verifies resume dispatches only unfinished items and reports the cached ones without a duration."""
    items  = ["done_model", "todo_model"]
    config = _config(tmp_path, resume=True)
    stage  = QueuedTrainingStage(config=config, entry_script=Path("entry.py"), run_tag="t1", items=items, logger=logger)

    _mark_complete(stage.stage_dir / "done_model")

    recorder = []
    _patch_queue(stage, recorder)

    results = stage.run()

    assert recorder == [["todo_model"]]

    by_name = {r["name"]: r for r in results}
    assert by_name["done_model"]["status"]     == "DONE"
    assert by_name["done_model"]["duration_s"] is None
    assert by_name["todo_model"]["duration_s"] == 1.0
    assert [r["name"] for r in results] == items


def test_training_checkpoint_without_marker_is_not_finished(tmp_path, logger):
    """Verifies a checkpoint without a completion marker does not count as finished."""
    items  = ["m"]
    config = _config(tmp_path, resume=True)
    stage  = QueuedTrainingStage(config=config, entry_script=Path("entry.py"), run_tag="t1", items=items, logger=logger)

    item_dir = stage.stage_dir / "m"
    item_dir.mkdir(parents=True)
    (item_dir / "best_model.pt").write_text("x")

    recorder = []
    _patch_queue(stage, recorder)

    stage.run()
    assert recorder == [["m"]]


def test_training_purges_unfinished_run_dir_on_resume(tmp_path, logger):
    """Verifies an unfinished run directory is deleted before the item is re-dispatched."""
    items  = ["m"]
    config = _config(tmp_path, resume=True)
    stage  = QueuedTrainingStage(config=config, entry_script=Path("entry.py"), run_tag="t1", items=items, logger=logger)

    item_dir = stage.stage_dir / "m"
    (item_dir / "tensorboard").mkdir(parents=True)
    (item_dir / "best_model.pt").write_text("x")
    (item_dir / "last.pt").write_text("x")

    recorder = []
    _patch_queue(stage, recorder)

    stage.run()

    assert recorder == [["m"]]
    assert not item_dir.exists()


def test_training_no_resume_ignores_completion_marker_and_keeps_dir(tmp_path, logger):
    """Verifies resume off re-runs a completed item and leaves its directory in place."""
    items  = ["m"]
    config = _config(tmp_path, resume=False)
    stage  = QueuedTrainingStage(config=config, entry_script=Path("entry.py"), run_tag="t1", items=items, logger=logger)

    _mark_complete(stage.stage_dir / "m")

    recorder = []
    _patch_queue(stage, recorder)

    stage.run()

    assert recorder == [["m"]]
    assert (stage.stage_dir / "m").exists()


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


def test_no_pending_items_does_not_invoke_queue(tmp_path, logger):
    """Verifies the queue is never invoked when every item is already complete."""
    items  = ["only"]
    config = _config(tmp_path, resume=True)
    stage  = QueuedTrainingStage(config=config, entry_script=Path("entry.py"), run_tag="t1", items=items, logger=logger)

    _mark_complete(stage.stage_dir / "only")

    recorder = []
    _patch_queue(stage, recorder)

    stage.run()
    assert recorder == []


def test_run_dir_derived_from_config_and_run_tag(tmp_path, logger):
    """Verifies the run directory and results path follow the config log base and the run tag."""
    config = _config(tmp_path)
    stage  = QueuedTrainingStage(config=config, entry_script=Path("entry.py"), run_tag="myrun", items=["a"], logger=logger)

    assert stage.run_dir == Path(config.paths.log_base_dir) / "myrun"
    assert stage.results_path == stage.run_dir / "pipeline" / "training_results.json"
