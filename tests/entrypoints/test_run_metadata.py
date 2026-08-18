"""Tests that TrainingRunMetadata lays out a run directory and persists its configuration.

Covers run-directory naming, creation of the tensorboard, docs, logs and metadata
subdirectories, ownership of the SummaryWriter and Logger, serialisation of the trainer config
and run summary, and writer shutdown through the context manager."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from configuration.benchmark                import BenchmarkConfig
from pipelines.shared.config.config_factory import ConfigFactory
from pipelines.shared.config.run_metadata   import TrainingRunMetadata
from tools.monitoring.logger                import Logger


@pytest.fixture
def trainer_config(test_data_dir, tmp_path):
    """Builds a backbone trainer config from the real test dataset, logging into a seed subdirectory."""
    config                       = BenchmarkConfig()
    config.paths.dataset_path    = str(test_data_dir)
    config.paths.parameters_path = test_data_dir / "params" / "params_k5_lam0.01_sig4_sigma" / "parameters.npy"
    return ConfigFactory(config).training_trainer_config(tmp_path / "seed_logdir")


@pytest.fixture
def metadata(trainer_config, tmp_path):
    """Yields a TrainingRunMetadata for run 'unit_run' and closes it afterwards."""
    meta = TrainingRunMetadata(
        trainer_config = trainer_config,
        model_name     = "resunet",
        base_logdir    = tmp_path / "runs",
        run_name       = "unit_run",
    )
    yield meta
    meta.close()


@pytest.mark.real_data
def test_run_directory_uses_run_name(metadata, tmp_path):
    """The run directory is the base logdir joined with the explicit run name."""
    assert metadata.run_directory == tmp_path / "runs" / "unit_run"


@pytest.mark.real_data
def test_subdirectories_created(metadata):
    """Run, tensorboard, docs, logs and metadata directories all exist after construction."""
    assert metadata.run_directory.is_dir()
    assert metadata.tensorboard_dir.is_dir()
    assert metadata.docs_directory.is_dir()
    assert metadata.logs_directory.is_dir()
    assert metadata.metadata_directory.is_dir()


@pytest.mark.real_data
def test_subdirectories_nested_under_run_directory(metadata):
    """The tensorboard, docs and metadata directories sit directly inside the run directory."""
    assert metadata.tensorboard_dir.parent    == metadata.run_directory
    assert metadata.docs_directory.parent     == metadata.run_directory
    assert metadata.metadata_directory.parent == metadata.run_directory


@pytest.mark.real_data
def test_writer_owned_by_metadata_not_the_config(metadata, trainer_config):
    """The SummaryWriter lives on the metadata object while the config only carries the logdir string."""
    assert metadata.writer is not None
    assert not hasattr(trainer_config.io, "writer")
    assert trainer_config.io.logdir == str(metadata.run_directory)


@pytest.mark.real_data
def test_default_run_name_includes_model(trainer_config, tmp_path):
    """Without an explicit run name the directory is named run_<model>_<timestamp>."""
    meta = TrainingRunMetadata(
        trainer_config = trainer_config,
        model_name     = "unet",
        base_logdir    = tmp_path / "runs",
    )
    try:
        assert meta.run_directory.name.startswith("run_unet_")
    finally:
        meta.close()


@pytest.mark.real_data
def test_save_trainer_config_serializes_without_writer(metadata):
    """The saved trainer config lands in docs/ and carries no writer entry in its io section."""
    out_path = metadata.save_trainer_config()

    assert out_path == metadata.docs_directory / "trainer_config.json"
    payload = json.loads(out_path.read_text())
    assert "writer" not in payload["io"]


@pytest.mark.real_data
def test_save_run_summary_payload(metadata):
    """The run summary records model name, channel counts, axis length, framework and run directory."""
    out_path = metadata.save_run_summary(
        model_name    = "resunet",
        in_channels   = 9,
        out_channels  = 15,
        x_axis_length = 256,
    )

    payload = json.loads(out_path.read_text())
    assert payload["model_name"]    == "resunet"
    assert payload["in_channels"]   == 9
    assert payload["out_channels"]  == 15
    assert payload["x_axis_length"] == 256
    assert payload["framework"]     == "pytorch"
    assert payload["run_directory"] == str(metadata.run_directory)


@pytest.mark.real_data
def test_context_manager_closes_writer(trainer_config, tmp_path):
    """Leaving the context closes the writer and leaves one non-empty tfevents file behind."""
    with TrainingRunMetadata(trainer_config, "resunet", tmp_path / "runs", run_name="ctx") as meta:
        meta.writer.add_scalar("probe/value", 1.0, 0)
        assert meta.writer.all_writers

    assert meta.writer.all_writers is None

    events = list(meta.tensorboard_dir.glob("events.out.tfevents.*"))
    assert len(events) == 1
    assert events[0].stat().st_size > 0


@pytest.mark.real_data
def test_owns_logger_when_none_passed(metadata):
    """The metadata owns the logger it created itself."""
    assert metadata._owns_logger is True


@pytest.mark.real_data
def test_does_not_own_external_logger(trainer_config, tmp_path):
    """A logger passed in from outside is used but not owned."""
    logger = Logger(log_dir=str(tmp_path / "ext_logs"), name="external")
    try:
        meta = TrainingRunMetadata(trainer_config, "resunet", tmp_path / "runs", run_name="ext", logger=logger)
        assert meta._owns_logger is False
        assert meta.logger is logger
        meta.close()
    finally:
        logger.close()
