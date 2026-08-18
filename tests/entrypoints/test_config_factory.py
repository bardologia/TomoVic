"""Tests that ConfigFactory derives dataset, inference and trainer configs from a benchmark config.

Covers the secondary-track label list, the input representation choices, the crop and azimuth
split regions read from the dataset JSON, loader settings propagation, and the trainer config
fields (logdir, epochs, warmup, abort flag, snapshot cadence, learning-rate batch scaling).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from configuration.benchmark                import BenchmarkConfig
from configuration.dataset                  import Representation
from configuration.inference                import InferenceConfig
from configuration.training                 import BackboneTrainerConfig
from pipelines.shared.config.config_factory import ConfigFactory
from tools.data.regions                     import CropRegion


@pytest.fixture
def factory(test_data_dir):
    """Builds a ConfigFactory over a benchmark config pointed at the real test dataset."""
    config                       = BenchmarkConfig()
    config.paths.dataset_path    = str(test_data_dir)
    config.paths.parameters_path = test_data_dir / "params" / "params_k5_lam0.01_sig4_sigma" / "parameters.npy"
    return ConfigFactory(config)


@pytest.fixture
def bare_factory():
    """Builds a ConfigFactory over an untouched default benchmark config."""
    return ConfigFactory(BenchmarkConfig())


def test_secondary_labels_returns_tuple(bare_factory):
    """Secondary track labels come back as a tuple of strings."""
    labels = bare_factory._secondary_labels()

    assert isinstance(labels, tuple)
    assert all(isinstance(label, str) for label in labels)


def test_secondary_labels_none_when_empty():
    """An empty secondary label list resolves to None rather than an empty tuple."""
    config = BenchmarkConfig()
    config.paths.secondary_labels = ()

    assert ConfigFactory(config)._secondary_labels() is None


def test_benchmark_input_config_uses_expected_representations(bare_factory):
    """Benchmark inputs enable all three channel groups with magnitude and phase representations."""
    input_config = bare_factory.benchmark_input_config()

    assert input_config.use_primary        is True
    assert input_config.use_secondaries    is True
    assert input_config.use_interferograms is True
    assert input_config.primary_representation        == Representation.MAG_ONLY
    assert input_config.secondaries_representation    == Representation.MAG_ONLY
    assert input_config.interferograms_representation == Representation.ANGLE_ONLY


@pytest.mark.real_data
def test_global_crop_reads_dataset_json(factory, dataset_json):
    """The global crop is read back from the dataset JSON as a CropRegion."""
    crop = factory.global_crop()

    assert isinstance(crop, CropRegion)
    assert list(crop.as_tuple()) == dataset_json["global_crop"]


@pytest.mark.real_data
def test_training_dataset_config_uses_global_crop_range(factory, dataset_json):
    """The train split inherits its range bounds from the dataset global crop."""
    dataset_config = factory.training_dataset_config()
    crop           = dataset_json["global_crop"]

    train = dataset_config.split_regions.train
    assert train.range_start == crop[2]
    assert train.range_end   == crop[3]


@pytest.mark.real_data
def test_training_dataset_config_azimuth_from_training(factory):
    """Train, validation and test azimuth bounds come from the training config."""
    training       = factory.config.training
    dataset_config = factory.training_dataset_config()

    train = dataset_config.split_regions.train
    val   = dataset_config.split_regions.val
    test  = dataset_config.split_regions.test

    assert (train.azimuth_start, train.azimuth_end) == tuple(training.train_azimuth)
    assert (val.azimuth_start,   val.azimuth_end)   == tuple(training.val_azimuth)
    assert (test.azimuth_start,  test.azimuth_end)  == tuple(training.test_azimuth)


@pytest.mark.real_data
def test_training_dataset_config_propagates_loader_settings(factory):
    """Batch size, worker count and prefetch factor reach the dataset config with shuffling and pinning on."""
    training       = factory.config.training
    dataset_config = factory.training_dataset_config()

    assert dataset_config.batch_size      == training.batch_size
    assert dataset_config.num_workers     == training.num_workers
    assert dataset_config.prefetch_factor == training.prefetch_factor
    assert dataset_config.shuffle_train   is True
    assert dataset_config.pin_memory      is True


@pytest.mark.real_data
def test_training_dataset_config_propagates_patch_padding(factory):
    """The symmetric-padding switch reaches the patch section of the dataset config."""
    factory.config.training.use_symmetric_padding = False

    dataset_config = factory.training_dataset_config()

    assert dataset_config.patch.use_symmetric_padding is False


def test_inference_config_propagates_run_directory(bare_factory, tmp_path):
    """The inference config carries the run directory with no output subdir and the cuda device."""
    run_directory = tmp_path / "run"

    config = bare_factory.inference_config(run_directory)

    assert isinstance(config, InferenceConfig)
    assert config.run_directory == run_directory
    assert config.output_subdir is None
    assert config.device        == "cuda"


def test_inference_config_propagates_inference_fields(bare_factory, tmp_path):
    """Checkpoint name, split, workers, stitch window and gif axes reach the inference config."""
    inference = bare_factory.config.inference

    config = bare_factory.inference_config(tmp_path / "run")

    assert config.checkpoint_name == inference.checkpoint_name
    assert config.split           == inference.split
    assert config.num_workers     == inference.num_workers
    assert config.stitch_window   == inference.stitch_window
    assert config.gif_axes        == list(inference.gif_axes)


@pytest.mark.real_data
def test_training_trainer_config_logdir(factory, tmp_path):
    """The trainer config is a BackboneTrainerConfig whose io logdir is the requested directory."""
    trainer_config = factory.training_trainer_config(tmp_path / "logdir")

    assert isinstance(trainer_config, BackboneTrainerConfig)
    assert trainer_config.io.logdir == str(tmp_path / "logdir")


@pytest.mark.real_data
def test_training_trainer_config_epochs_propagate(factory, tmp_path):
    """The epoch count reaches the trainer config training section."""
    training       = factory.config.training
    trainer_config = factory.training_trainer_config(tmp_path / "logdir")

    assert trainer_config.training.epochs == training.epochs


@pytest.mark.real_data
def test_training_trainer_config_warmup_propagates(factory, tmp_path):
    """Warmup enablement and step count reach the trainer config warmup section."""
    training                = factory.config.training
    training.warmup_enabled = False
    training.warmup_steps   = 42

    trainer_config = factory.training_trainer_config(tmp_path / "logdir")

    assert trainer_config.warmup.warmup_enabled is False
    assert trainer_config.warmup.warmup_steps   == 42


@pytest.mark.real_data
def test_training_trainer_config_abort_flag_propagates(factory, tmp_path):
    """The abort-on-nonfinite-loss flag reaches the trainer config."""
    factory.config.training.abort_on_nonfinite_loss = False

    trainer_config = factory.training_trainer_config(tmp_path / "logdir")

    assert trainer_config.training.abort_on_nonfinite_loss is False


@pytest.mark.real_data
def test_training_trainer_config_snapshot_cadence_propagates(factory, tmp_path):
    """The snapshot epoch cadence reaches the trainer config."""
    factory.config.training.snapshot_every_n_epochs = 5

    trainer_config = factory.training_trainer_config(tmp_path / "logdir")

    assert trainer_config.training.snapshot_every_n_epochs == 5


@pytest.mark.real_data
def test_training_trainer_config_lr_scale_with_batch(factory, tmp_path):
    """Enabling batch scaling sets lr_scale to the batch size over the reference batch size."""
    training = factory.config.training
    training.scale_lr_with_batch = True

    trainer_config = factory.training_trainer_config(tmp_path / "logdir")

    expected = training.batch_size / training.lr_reference_batch_size
    assert trainer_config.optimizer.lr_scale == pytest.approx(expected)


@pytest.mark.real_data
def test_training_trainer_config_lr_scale_disabled(factory, tmp_path):
    """Disabling batch scaling leaves lr_scale at unity."""
    factory.config.training.scale_lr_with_batch = False

    trainer_config = factory.training_trainer_config(tmp_path / "logdir")

    assert trainer_config.optimizer.lr_scale == pytest.approx(1.0)
