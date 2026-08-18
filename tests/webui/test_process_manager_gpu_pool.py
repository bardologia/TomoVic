"""Tests for the live GPU pool file the process manager injects into fan-out runs.

Covers which launch scripts receive a per-job pool file, honouring an explicit
gpus_file override, and the validation, parking and error paths of set_gpus
and gpu_pool.
"""
from __future__ import annotations

import json
import sys
from dataclasses import fields
from pathlib     import Path

import pytest

from process_manager import ProcessManager

from configuration.benchmark.general        import BenchmarkConfig
from configuration.cross_validation.general import CrossValidationConfig
from configuration.inference                import BackboneInferenceEntryConfig, DualInferenceEntryConfig, ImageAeInferenceEntryConfig, ProfileAeInferenceEntryConfig, UnrolledInferenceEntryConfig
from configuration.patch_sweep.general      import PatchSweepConfig
from configuration.training                 import BackboneEntryConfig, DualEntryConfig, ImageAeEntryConfig, JepaEntryConfig, ProfileAeEntryConfig, UnrolledEntryConfig
from configuration.tuning.general           import TuningEntryConfig

from tests.webui.conftest import SLEEP_LONG, wait_for_status, wait_until_finished

_SCHEDULING_PAGES = [
    ("train_backbone",            BackboneEntryConfig),
    ("train_dual",                DualEntryConfig),
    ("train_jepa",                JepaEntryConfig),
    ("train_profile_autoencoder", ProfileAeEntryConfig),
    ("train_image_autoencoder",   ImageAeEntryConfig),
    ("train_unrolled",            UnrolledEntryConfig),
    ("benchmark",                 BenchmarkConfig),
    ("cross_validate",            CrossValidationConfig),
    ("sweep_patches",             PatchSweepConfig),
    ("tune",                      TuningEntryConfig),
    ("infer_backbone",            BackboneInferenceEntryConfig),
    ("infer_profile_autoencoder", ProfileAeInferenceEntryConfig),
    ("infer_image_autoencoder",   ImageAeInferenceEntryConfig),
    ("infer_unrolled",            UnrolledInferenceEntryConfig),
    ("infer_dual",                DualInferenceEntryConfig),
]


@pytest.fixture
def manager(make_manager):
    """Returns a process manager whose fan-out and tuning scripts are long sleeps."""
    return make_manager({name: SLEEP_LONG for name in ("train_backbone", "train_dual", "sweep_patches", "train_jepa", "tune_dataloader")})


def _pool_path(manager: ProcessManager, job_id: str) -> Path:
    """Returns the GPU pool file path injected into the job's overrides."""
    with manager.lock:
        return Path(manager.jobs[job_id]["overrides"]["gpus_file"])


def test_pool_scripts_match_the_configs_exposing_a_pool_file():
    """POOL_SCRIPTS matches exactly the launch pages whose config exposes a gpus_file field."""
    capable = {key for key, config in _SCHEDULING_PAGES if "gpus_file" in {field.name for field in fields(config())}}

    assert set(ProcessManager.POOL_SCRIPTS) == capable


def test_launch_injects_a_per_job_pool_file_for_fan_out_scripts(manager):
    """A fan-out script gets a per-job pool file under gpu_pools_dir passed on the command line."""
    result = manager.launch("train_backbone", sys.executable)
    job_id = result["job_id"]

    with manager.lock:
        record = dict(manager.jobs[job_id])

    assert record["overrides"]["gpus_file"] == str(manager.paths.gpu_pools_dir / f"{job_id}.json")
    assert f"--gpus_file" in record["command"]

    manager.stop(job_id)


def test_launch_leaves_other_scripts_without_a_pool_file(manager):
    """A non-fan-out script gets no pool file and reports the pool as unsupported."""
    result = manager.launch("tune_dataloader", sys.executable)

    with manager.lock:
        record = dict(manager.jobs[result["job_id"]])

    assert "gpus_file" not in record["overrides"]
    assert manager.gpu_pool(result["job_id"]) == {"ok": True, "supported": False, "live": False}

    manager.stop(result["job_id"])


def test_launch_keeps_an_explicit_pool_file_override(manager, tmp_path):
    """An explicit gpus_file override is kept instead of the per-job default."""
    chosen = tmp_path / "mine.json"
    result = manager.launch("train_backbone", sys.executable, {"gpus_file": str(chosen)})

    with manager.lock:
        record = dict(manager.jobs[result["job_id"]])

    assert record["overrides"]["gpus_file"] == str(chosen)

    manager.stop(result["job_id"])


def test_set_gpus_writes_the_pool_file_of_a_running_fan_out(manager):
    """set_gpus rewrites the pool file of a running fan-out job and gpu_pool reads it back."""
    result = manager.launch("train_backbone", sys.executable)
    job_id = result["job_id"]

    assert wait_for_status(manager, job_id, "running")

    pool = _pool_path(manager, job_id)
    pool.parent.mkdir(parents=True, exist_ok=True)
    pool.write_text(json.dumps({"gpus": [0]}))

    applied = manager.set_gpus(job_id, [0, 2, 3])

    assert applied == {"ok": True, "gpus": [0, 2, 3], "parked": False}
    assert json.loads(pool.read_text()) == {"gpus": [0, 2, 3]}
    assert manager.gpu_pool(job_id)["gpus"] == [0, 2, 3]

    manager.stop(job_id)


def test_set_gpus_refuses_a_job_that_seeded_no_pool(manager):
    """set_gpus fails when the running job has not written a pool file yet."""
    result = manager.launch("train_backbone", sys.executable)
    job_id = result["job_id"]

    assert wait_for_status(manager, job_id, "running")

    applied = manager.set_gpus(job_id, [0, 1])

    assert applied["ok"] is False
    assert "no live GPU pool" in applied["error"]
    assert manager.gpu_pool(job_id)["live"] is False

    manager.stop(job_id)


def test_set_gpus_parks_only_when_parking_is_confirmed(manager):
    """An empty selection needs park=True, and a later non-empty selection resumes the job."""
    result = manager.launch("train_backbone", sys.executable)
    job_id = result["job_id"]

    assert wait_for_status(manager, job_id, "running")

    pool = _pool_path(manager, job_id)
    pool.parent.mkdir(parents=True, exist_ok=True)
    pool.write_text(json.dumps({"gpus": [0, 1]}))

    refused = manager.set_gpus(job_id, [])

    assert refused["ok"] is False
    assert "confirm parking" in refused["error"]
    assert json.loads(pool.read_text()) == {"gpus": [0, 1]}

    parked = manager.set_gpus(job_id, [], park=True)

    assert parked == {"ok": True, "gpus": [], "parked": True}
    assert json.loads(pool.read_text()) == {"gpus": []}
    assert manager.gpu_pool(job_id)["gpus"] == []

    resumed = manager.set_gpus(job_id, [2])

    assert resumed == {"ok": True, "gpus": [2], "parked": False}
    assert json.loads(pool.read_text()) == {"gpus": [2]}

    manager.stop(job_id)


@pytest.mark.parametrize("gpus, reason", [
    ([0, 0],       "repeat"),
    ([-1],         "non-negative"),
    (["0"],        "non-negative"),
    ("0,1",        "list"),
])
def test_set_gpus_rejects_an_invalid_selection(manager, gpus, reason):
    """An invalid GPU selection is rejected with a reason and leaves the pool file untouched."""
    result = manager.launch("train_backbone", sys.executable)
    job_id = result["job_id"]

    assert wait_for_status(manager, job_id, "running")

    pool = _pool_path(manager, job_id)
    pool.parent.mkdir(parents=True, exist_ok=True)
    pool.write_text(json.dumps({"gpus": [0]}))

    applied = manager.set_gpus(job_id, gpus)

    assert applied["ok"] is False
    assert reason in applied["error"]
    assert json.loads(pool.read_text()) == {"gpus": [0]}

    manager.stop(job_id)


def test_set_gpus_refuses_a_finished_job(manager):
    """set_gpus refuses a job that is no longer running."""
    result = manager.launch("train_backbone", sys.executable)
    job_id = result["job_id"]

    assert wait_for_status(manager, job_id, "running")
    manager.stop(job_id)

    assert wait_until_finished(manager, job_id)

    applied = manager.set_gpus(job_id, [0, 1])

    assert applied["ok"] is False
    assert applied["error"] == "job is not running"


def test_set_gpus_reports_an_unknown_job(manager):
    """set_gpus and gpu_pool both report an unknown job id."""
    assert manager.set_gpus("nope", [0]) == {"ok": False, "error": "unknown job"}
    assert manager.gpu_pool("nope")      == {"ok": False, "error": "unknown job"}
