"""Tests that a preprocessing run's config_state.json still matches the dataclasses.

Covers the tomogram, parallel and path sections plus the crop and height range,
checking each stored key is still a field and each section rebuilds its config.
"""

from __future__ import annotations

import dataclasses

import pytest

from configuration.sar.processing_config import (
    TomogramConfig,
    ParallelConfig,
    PathConfig,
    ProcessingConfig,
)
from tests.configuration._helpers        import make_crop
from tools.data.regions                  import CropRegion


@pytest.mark.real_data
def test_config_state_top_level_keys_present(config_state_json):
    """Verifies the stored state carries the crop, tomogram, parallel and path sections."""
    for key in ("crop", "tomogram_config", "parallel", "paths"):
        assert key in config_state_json


@pytest.mark.real_data
def test_config_state_tomogram_fields_match_dataclass(config_state_json):
    """Verifies every stored tomogram key is still a field of TomogramConfig."""
    state       = config_state_json["tomogram_config"]
    field_names = {f.name for f in dataclasses.fields(TomogramConfig)}
    for key in state:
        assert key in field_names


@pytest.mark.real_data
def test_config_state_tomogram_round_trips(config_state_json):
    """Verifies the stored tomogram section rebuilds a config carrying the same polarisation, height range and filter arguments."""
    state = config_state_json["tomogram_config"]

    rebuilt = TomogramConfig(
        fusar_project_path     = state["fusar_project_path"],
        base_directory         = state["base_directory"],
        polarisation           = state["polarisation"],
        track_selection        = state["track_selection"],
        height_range           = tuple(state["height_range"]),
        filter_method          = state["filter_method"],
        filter_arguments       = state["filter_arguments"],
        beamforming_method     = state["beamforming_method"],
        beamforming_arguments  = state["beamforming_arguments"],
        max_crop_azimuth_width = state["max_crop_azimuth_width"],
        apply_resampling       = state["apply_resampling"],
        apply_presumming       = state["apply_presumming"],
        max_amplitude_clip     = state["max_amplitude_clip"],
    )

    assert rebuilt.polarisation       == state["polarisation"]
    assert list(rebuilt.height_range) == state["height_range"]
    assert rebuilt.filter_arguments   == state["filter_arguments"]


@pytest.mark.real_data
def test_config_state_parallel_fields_match_dataclass(config_state_json):
    """Verifies the stored parallel section rebuilds ParallelConfig from its own keys."""
    state       = config_state_json["parallel"]
    field_names = {f.name for f in dataclasses.fields(ParallelConfig)}
    for key in state:
        assert key in field_names

    rebuilt = ParallelConfig(**state)
    assert rebuilt.effort == state["effort"]


@pytest.mark.real_data
def test_config_state_paths_fields_match_dataclass(config_state_json):
    """Verifies every stored path key is still a field of PathConfig."""
    state       = config_state_json["paths"]
    field_names = {f.name for f in dataclasses.fields(PathConfig)}
    for key in state:
        assert key in field_names


@pytest.mark.real_data
def test_config_state_processing_top_level_fields(config_state_json):
    """Verifies the stored dataset and output tags match the current ProcessingConfig defaults."""
    field_names = {f.name for f in dataclasses.fields(ProcessingConfig)}
    for key in ("dataset_type", "stack_identifier", "tomogram_output_tag", "parameter_output_tag"):
        assert key in config_state_json
        assert key in field_names
        assert config_state_json[key] == getattr(ProcessingConfig(crop=make_crop()), key)


@pytest.mark.real_data
def test_config_state_crop_round_trips_through_processing(config_state_json):
    """Verifies the stored crop rebuilds a CropRegion carried unchanged by ProcessingConfig."""
    crop_state = config_state_json["crop"]
    crop       = CropRegion(**crop_state)
    cfg        = ProcessingConfig(crop=crop)

    assert cfg.crop.azimuth_start == crop_state["azimuth_start"]
    assert cfg.crop.range_end     == crop_state["range_end"]
