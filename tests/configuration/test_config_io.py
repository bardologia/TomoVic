"""Tests for persisting and reloading model configurations.

Covers the backbone, profile-autoencoder and image-autoencoder config IO helpers:
the round trip of every registered config, the head recovered alongside it, and
the failure modes when the stored file is missing.
"""

from __future__ import annotations

import dataclasses

import pytest

from pipelines.shared.config.config_persistence import (
    BackboneModelConfigIO,
    ProfileAutoencoderConfigIO,
    ImageAutoencoderConfigIO,
)
from models.backbone                            import BACKBONE_CONFIG_REGISTRY
from models.profile_autoencoder                 import PROFILE_AE_CONFIG_REGISTRY
from models.image_autoencoder                   import IMAGE_AE_CONFIG_REGISTRY
from tools.data.io                              import FileIO


BACKBONE_CASES = [pytest.param(name, id=name) for name in BACKBONE_CONFIG_REGISTRY]
PROFILE_CASES  = [pytest.param(name, id=name) for name in PROFILE_AE_CONFIG_REGISTRY]
IMAGE_CASES    = [pytest.param(name, id=name) for name in IMAGE_AE_CONFIG_REGISTRY]


@pytest.mark.parametrize("name", BACKBONE_CASES)
def test_backbone_config_io_round_trips(tmp_path, name):
    """Verifies a saved backbone config reloads with its type, registry name and non-excluded fields intact."""
    config = BACKBONE_CONFIG_REGISTRY[name]()
    BackboneModelConfigIO.save(config, name, tmp_path)

    assert BackboneModelConfigIO.exists(tmp_path)

    loaded, raw_name = BackboneModelConfigIO.load(tmp_path)
    assert raw_name == name
    assert type(loaded) is type(config)

    for f in dataclasses.fields(config):
        if f.name in BackboneModelConfigIO.EXCLUDED:
            continue
        assert getattr(loaded, f.name) == getattr(config, f.name)


@pytest.mark.parametrize("head", ["multihead", "per_gaussian", "set_pred"])
def test_backbone_config_io_round_trips_the_head_into_a_loadable_model(tmp_path, head):
    """Verifies the persisted head rebuilds a model whose state dict accepts the trained weights."""
    from models.backbone import get_backbone

    trained, config = get_backbone("unet", head=head, features=[8, 16], bottleneck_factor=1)
    BackboneModelConfigIO.save(config, "unet", tmp_path)

    loaded, raw_name = BackboneModelConfigIO.load(tmp_path)
    assert loaded.head == head

    rebuilt, _ = get_backbone(raw_name, config=loaded)
    rebuilt.load_state_dict(trained.state_dict())


@pytest.mark.parametrize("name", PROFILE_CASES)
def test_profile_ae_config_io_round_trips(tmp_path, name):
    """Verifies a saved profile-autoencoder config reloads identically."""
    config = PROFILE_AE_CONFIG_REGISTRY[name]()
    ProfileAutoencoderConfigIO.save(config, name, tmp_path)

    loaded, raw_name = ProfileAutoencoderConfigIO.load(tmp_path)
    assert raw_name == name
    assert type(loaded) is type(config)
    assert dataclasses.asdict(loaded) == dataclasses.asdict(config)


@pytest.mark.parametrize("name", IMAGE_CASES)
def test_image_ae_config_io_round_trips(tmp_path, name):
    """Verifies a saved image-autoencoder config reloads identically."""
    config = IMAGE_AE_CONFIG_REGISTRY[name]()
    ImageAutoencoderConfigIO.save(config, name, tmp_path)

    loaded, raw_name = ImageAutoencoderConfigIO.load(tmp_path)
    assert raw_name == name
    assert type(loaded) is type(config)
    assert dataclasses.asdict(loaded) == dataclasses.asdict(config)


def test_config_io_exists_false_when_missing(tmp_path):
    """Verifies existence is False for a directory holding no stored config."""
    assert BackboneModelConfigIO.exists(tmp_path) is False


def test_config_io_load_missing_raises(tmp_path):
    """Verifies loading from a directory without a stored config raises."""
    with pytest.raises(FileNotFoundError):
        BackboneModelConfigIO.load(tmp_path)


def test_backbone_config_io_normalizes_name(tmp_path):
    """Verifies a differently cased model name resolves to the right config class while the raw name is preserved."""
    config = BACKBONE_CONFIG_REGISTRY["resunet"]()
    BackboneModelConfigIO.save(config, "ResUNet", tmp_path)

    loaded, raw_name = BackboneModelConfigIO.load(tmp_path)
    assert raw_name == "ResUNet"
    assert type(loaded) is type(config)


def test_backbone_config_io_excludes_shape_logger_types(tmp_path):
    """Verifies the shape-logger types are excluded from the persisted payload."""
    config = BACKBONE_CONFIG_REGISTRY["unet"]()
    BackboneModelConfigIO.save(config, "unet", tmp_path)

    payload = FileIO.load_json(tmp_path / BackboneModelConfigIO.FILENAME)
    assert "shape_logger_types" not in payload["config"]
