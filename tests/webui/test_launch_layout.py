"""Tests that every launch page layout matches the config it is supposed to expose.

Each entry point config is flattened into leaves and fed to LaunchLayout, which
refuses any field it does not claim exactly once. The remaining tests pin the
widget declarations of the pages and exercise the validation paths that
reject unknown fields, duplicate claims, unclaimed leaves, malformed gate
conditions and unbounded number widgets.
"""

from __future__ import annotations

from importlib import import_module

import pytest

from launch_layout          import LaunchLayout, LayoutError
from project_paths          import ProjectPaths
from script_catalog         import ScriptCatalog
from script_config_resolver import ScriptConfigResolver

from tools.runtime.config_cli import ConfigCli

from configuration.comparison            import PreprocessingComparisonConfig
from configuration.param_extraction      import ExtractParamsEntryConfig, ParamExtractionInferenceConfig
from configuration.sar.processing_config import PreProcessEntryConfig, PreprocessInferenceConfig

_DISPATCH_ONLY = {"generate_tomogram", "generate_interferograms"}

_PAGES = [
    ("pre_process",                  PreProcessEntryConfig),
    ("extract_params",               ExtractParamsEntryConfig),
    ("analyze_preprocessing",        PreprocessInferenceConfig),
    ("analyze_param_extraction",     ParamExtractionInferenceConfig),
    ("compare_preprocessing_trials", PreprocessingComparisonConfig),
]


def _leaves(entry_config):
    """Returns the layout leaves of an entry config class, one per dotted path."""
    return [{"path": path} for path, _value in ConfigCli._leaves(entry_config())]


@pytest.mark.parametrize("key, entry_config", _PAGES)
def test_every_page_layout_claims_every_config_field_exactly_once(key, entry_config):
    """Every launch page layout claims each field of its entry config exactly once."""
    LaunchLayout().build(key, _leaves(entry_config))


@pytest.mark.parametrize("key", sorted(key for key in ProjectPaths.SCRIPT_DIRS if key not in _DISPATCH_ONLY))
def test_every_script_layout_builds_against_its_entry_config(key):
    """Every registered script except the dispatch-only ones builds a layout against its resolved entry config."""
    entry  = ScriptConfigResolver(ProjectPaths()).entry_config(key)
    config = getattr(import_module(entry["module"]), entry["class"])()
    leaves = [{"path": path} for path, _value in ConfigCli._leaves(config)]

    LaunchLayout().build(key, leaves)


def test_every_registered_script_is_reachable_from_the_catalog():
    """Every registered script except the dispatch-only ones appears in the catalog and has a layout."""
    members = {member for group in ScriptCatalog.GROUPS.values() for member, _label in group["members"]}
    pages   = set(ScriptCatalog.META) | members

    assert set(ProjectPaths.SCRIPT_DIRS) - _DISPATCH_ONLY == pages
    assert pages <= set(LaunchLayout.LAYOUTS)


def test_the_declared_layouts_cover_exactly_the_launchable_scripts():
    """LAYOUTS declares one page per launchable script and nothing else."""
    assert set(LaunchLayout.LAYOUTS) == set(ProjectPaths.SCRIPT_DIRS) - _DISPATCH_ONLY


@pytest.mark.parametrize("key, entry_config", _PAGES)
def test_every_page_renders_in_single_mode(key, entry_config):
    """Each page holds one section and no essentials, so it renders in single mode."""
    layout = LaunchLayout().build(key, _leaves(entry_config))

    assert layout["mode"] == "single"
    assert layout["essentials"] == []
    assert len(layout["sections"]) == 1


def test_the_run_pickers_read_their_runs_dir_field():
    """The analysis pages expose run_tags through a multi dataset picker rooted at their runs root."""
    analyze = LaunchLayout().build("analyze_preprocessing",        _leaves(PreprocessInferenceConfig))
    compare = LaunchLayout().build("compare_preprocessing_trials", _leaves(PreprocessingComparisonConfig))
    params  = LaunchLayout().build("analyze_param_extraction",     _leaves(ParamExtractionInferenceConfig))

    assert analyze["widgets"]["run_tags"] == {"kind": "dataset", "mode": "runs",         "multi": True, "baseFrom": "runs_dir"}
    assert compare["widgets"]["run_tags"] == {"kind": "dataset", "mode": "runs_compare", "multi": True, "baseFrom": "runs_dir"}
    assert params["widgets"]["run_tags"]  == {"kind": "dataset", "mode": "param_trials", "multi": True, "baseFrom": "params_dir"}


def test_the_extraction_sweep_exposes_its_grid_widgets():
    """The extraction page renders the dataset filter as a picker and the K, lambda and mode grids as multi fields."""
    layout = LaunchLayout().build("extract_params", _leaves(ExtractParamsEntryConfig))

    assert layout["widgets"]["dataset_filter"]    == LaunchLayout.PICK_DATASETS
    assert layout["widgets"]["fit_k_values"]      == LaunchLayout.MULTI_K
    assert layout["widgets"]["fit_lambda_values"] == LaunchLayout.MULTI_LAMBDA
    assert layout["widgets"]["fit_modes"]         == LaunchLayout.MULTI_FIT_MODES
    assert layout["widgets"]["gpu_device_ids"]    == LaunchLayout.MULTI_GPUS
    assert layout["widgets"]["parameter_workers"] == LaunchLayout.NUM_WORKERS


def test_the_workers_widget_is_a_bounded_number():
    """The comparison workers field renders as an integer number widget with bounds and presets."""
    layout = LaunchLayout().build("compare_preprocessing_trials", _leaves(PreprocessingComparisonConfig))
    widget = layout["widgets"]["workers"]

    assert widget == LaunchLayout.NUM_WORKERS
    assert widget["int"] is True
    assert "min" in widget and "max" in widget


def test_an_unknown_layout_key_is_rejected():
    """Building a page that is not declared fails with a LayoutError."""
    with pytest.raises(LayoutError):
        LaunchLayout().build("no_such_page", [])


def test_a_claim_on_an_unknown_field_is_rejected():
    """A layout naming a config path that does not exist fails validation."""
    engine = LaunchLayout()
    layout = engine._expand("pre_process")

    layout["sections"][0]["panels"][0]["groups"][0]["fields"].append({"path": "no_such_field"})

    with pytest.raises(LayoutError, match="unknown fields"):
        engine._validate("pre_process", layout, _leaves(PreProcessEntryConfig))


def test_a_field_claimed_twice_is_rejected():
    """A layout claiming the same config path in two places fails validation."""
    engine = LaunchLayout()
    layout = engine._expand("pre_process")

    layout["sections"][0]["panels"][0]["groups"][0]["fields"].append({"path": "azimuth_start"})

    with pytest.raises(LayoutError, match="twice"):
        engine._validate("pre_process", layout, _leaves(PreProcessEntryConfig))


def test_an_unclaimed_config_field_is_rejected():
    """A resolved config leaf the layout never claims fails validation."""
    engine = LaunchLayout()
    layout = engine._expand("pre_process")
    leaves = _leaves(PreProcessEntryConfig) + [{"path": "brand_new_field"}]

    with pytest.raises(LayoutError, match="unclaimed"):
        engine._validate("pre_process", layout, leaves)


def test_a_section_gate_on_an_unknown_field_is_rejected():
    """A section when clause naming a config field that does not exist fails validation."""
    engine = LaunchLayout()
    layout = engine._expand("compare_preprocessing_trials")

    layout["sections"][0]["when"] = {"field": "no_such_field", "set": True}

    with pytest.raises(LayoutError, match="gates on unknown field"):
        engine._validate("compare_preprocessing_trials", layout, _leaves(PreprocessingComparisonConfig))


def test_a_when_condition_with_both_in_and_set_is_rejected():
    """A section condition carrying both in and set fails validation."""
    engine = LaunchLayout()
    layout = engine._expand("compare_preprocessing_trials")

    layout["sections"][0]["when"] = {"field": "make_plots", "set": True, "in": ["x"]}

    with pytest.raises(LayoutError, match="exactly one of 'in' or 'set'"):
        engine._validate("compare_preprocessing_trials", layout, _leaves(PreprocessingComparisonConfig))


def test_a_value_gate_on_an_unknown_field_is_rejected():
    """A field gate naming a config field that does not exist fails validation."""
    engine = LaunchLayout()
    layout = engine._expand("pre_process")
    group  = layout["sections"][0]["panels"][0]["groups"][0]

    group["fields"][0] = {"gateOn": {"field": "no_such_field", "set": True}, "fields": [group["fields"][0]]}

    with pytest.raises(LayoutError, match="value-gates on unknown field"):
        engine._validate("pre_process", layout, _leaves(PreProcessEntryConfig))


def test_a_number_widget_without_bounds_is_rejected():
    """A number widget missing its min or max bound fails validation."""
    engine = LaunchLayout()
    layout = engine._expand("compare_preprocessing_trials")

    layout["widgets"]["workers"] = {"kind": "number", "int": True}

    with pytest.raises(LayoutError, match="lacks min/max bounds"):
        engine._validate("compare_preprocessing_trials", layout, _leaves(PreprocessingComparisonConfig))
