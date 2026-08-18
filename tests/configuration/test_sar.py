"""Tests for the SAR configuration dataclasses."""

from __future__ import annotations

import dataclasses

import pytest

from configuration.sar.processing_config import (
    TomogramConfig,
    ParallelConfig,
    PathConfig,
    ProcessingConfig,
    PreProcessEntryConfig,
)

from tests.configuration._helpers import make_crop
def test_tomogram_config_defaults():
    """Verifies TomogramConfig defaults carry an ordered height range and container-typed arguments."""
    cfg = TomogramConfig()
    assert cfg.height_range[1] > cfg.height_range[0]
    assert cfg.max_crop_azimuth_width > 0
    assert cfg.max_amplitude_clip > 0
    assert isinstance(cfg.filter_arguments, dict)
    assert isinstance(cfg.beamforming_arguments, list)


def test_tomogram_config_asdict_round_trips():
    """Verifies TomogramConfig survives a dataclasses.asdict round trip."""
    cfg     = TomogramConfig()
    payload = dataclasses.asdict(cfg)
    assert TomogramConfig(**payload) == cfg


def test_tomogram_config_default_factories_are_independent():
    """Verifies each TomogramConfig instance owns its own mutable filter arguments."""
    a = TomogramConfig()
    b = TomogramConfig()
    a.filter_arguments["win"].append(99)
    assert b.filter_arguments["win"] == [20, 10]


@pytest.mark.parametrize("effort", ["low", "medium", "high"])
def test_parallel_config_core_budget_valid(effort):
    """Verifies every effort level yields a core budget of at least one core."""
    cfg = ParallelConfig(effort=effort)
    assert cfg.core_budget() >= 1


def test_parallel_config_unknown_effort_raises():
    """Verifies an unknown effort level raises when the core budget is computed."""
    cfg = ParallelConfig(effort="extreme")
    with pytest.raises(ValueError):
        cfg.core_budget()


def test_parallel_config_resolve_plan_returns_positive_pair():
    """Verifies the parallel plan returns positive worker and thread counts."""
    cfg              = ParallelConfig(effort="high")
    workers, threads = cfg.resolve_plan(8)
    assert workers >= 1
    assert threads >= 1


def test_parallel_config_resolve_plan_rejects_empty_subsections():
    """Verifies planning for zero subsections is rejected."""
    cfg = ParallelConfig(effort="high")
    with pytest.raises(ValueError, match="at least one subsection"):
        cfg.resolve_plan(0)


def test_parallel_config_effort_fractions_increase():
    """Verifies the effort fractions are strictly increasing from low to high."""
    fractions = ParallelConfig.EFFORT_FRACTIONS
    assert fractions["low"] < fractions["medium"] < fractions["high"]


def test_path_config_directory_properties():
    """Verifies the path properties are named after their configured subdirectories."""
    cfg = PathConfig(run_subdirectory="run_x")
    assert cfg.run_directory.name       == "run_x"
    assert cfg.data_directory.name      == cfg.data_subdirectory
    assert cfg.metadata_directory.name  == cfg.metadata_subdirectory
    assert cfg.temporary_directory.name == cfg.temporary_subdirectory


def test_path_config_run_directory_defaults_to_main():
    """Verifies the run directory falls back to the main directory when no subdirectory is set."""
    cfg = PathConfig()
    assert cfg.run_directory == cfg.main_directory


def test_processing_config_requires_crop_and_builds_tags():
    """Verifies the tomogram and parameter tags embed the stack identifier and output tags."""
    cfg = ProcessingConfig(crop=make_crop())
    assert cfg.stack_identifier in cfg.tomogram_tag
    assert cfg.tomogram_output_tag in cfg.tomogram_tag
    assert cfg.parameter_output_tag in cfg.parameter_tag


def test_processing_config_post_init_sets_run_subdirectory():
    """Verifies __post_init__ assigns a run_ prefixed run subdirectory."""
    cfg = ProcessingConfig(crop=make_crop())
    assert cfg.paths.run_subdirectory is not None
    assert cfg.paths.run_subdirectory.startswith("run_")


def test_processing_config_subconfig_factories():
    """Verifies the processing subconfigurations are built by their default factories."""
    cfg = ProcessingConfig(crop=make_crop())
    assert isinstance(cfg.tomogram_config, TomogramConfig)
    assert isinstance(cfg.parallel, ParallelConfig)
    assert isinstance(cfg.paths, PathConfig)


def test_preprocess_entry_config_defaults():
    """Verifies PreProcessEntryConfig defaults carry ordered crop bounds and a window list."""
    cfg = PreProcessEntryConfig()
    assert cfg.azimuth_end > cfg.azimuth_start
    assert cfg.range_end > cfg.range_start
    assert cfg.height_range[1] > cfg.height_range[0]
    assert isinstance(cfg.win_list, list)


def test_preprocess_entry_resolve_dataset_name_single_win():
    """Verifies the resolved dataset name embeds the boxcar window and the stack identifier."""
    cfg  = PreProcessEntryConfig()
    name = cfg.resolve_dataset_name([20, 10], "abc")
    assert "w20_10" in name
    assert "abc" in name


def test_preprocess_entry_resolve_dataset_name_explicit_single():
    """Verifies an explicit dataset_name overrides the derived name."""
    cfg  = PreProcessEntryConfig(dataset_name="mydata")
    name = cfg.resolve_dataset_name([20, 10], "abc")
    assert name == "mydata"
