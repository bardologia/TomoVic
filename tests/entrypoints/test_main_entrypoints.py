"""Tests that every main/ entry script imports cleanly and exposes a working CLI.

Covers deferred heavy imports (no pipelines pulled in at import time), the absence of
module-level environment side effects (thread pinning), the ordering of EnvironmentPinner
calls relative to the numeric stack, and ConfigCli parser construction for every entry
config."""

from __future__ import annotations

import importlib
import os
import subprocess
import sys
from pathlib import Path

import pytest

from configuration.sar.processing_config import PreProcessEntryConfig
from tools.runtime.config_cli            import ConfigCli


_MAIN_DIR = Path(__file__).resolve().parents[2] / "main"
_SUBDIRS  = ("processing", "analysis")

THREAD_KEYS = ("MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS", "OMP_NUM_THREADS")


def _script_path(name):
    """Returns the path of the entry script named `name` under one of the main/ subdirectories."""
    for subdir in _SUBDIRS:
        candidate = _MAIN_DIR / subdir / f"{name}.py"
        if candidate.exists():
            return candidate
    raise FileNotFoundError(f"No entry script named {name}.py under {_MAIN_DIR}")

DEFER_HEAVY_IMPORTS = (
    "generate_interferograms",
    "generate_tomogram",
    "pre_process",
    "extract_params",
    "analyze_preprocessing",
    "analyze_param_extraction",
)

CLI_MODULES = (
    "pre_process",
    "extract_params",
    "analyze_preprocessing",
    "analyze_param_extraction",
    "compare_preprocessing_trials",
)

ENTRY_CONFIGS = {
    "pre_process"                  : ("configuration.sar.processing_config", "PreProcessEntryConfig"),
    "extract_params"               : ("configuration.param_extraction",      "ExtractParamsEntryConfig"),
    "analyze_preprocessing"        : ("configuration.sar.processing_config", "PreprocessInferenceConfig"),
    "analyze_param_extraction"     : ("configuration.param_extraction",      "ParamExtractionInferenceConfig"),
    "compare_preprocessing_trials" : ("configuration.comparison",            "PreprocessingComparisonConfig"),
}

ENTRY_SCRIPTS = sorted(script for subdir in _SUBDIRS for script in (_MAIN_DIR / subdir).glob("*.py") if not script.stem.startswith("_"))


@pytest.fixture
def main_on_path(monkeypatch):
    """Puts main/ and its entry subdirectories on sys.path for the duration of a test."""
    for subdir in _SUBDIRS:
        monkeypatch.syspath_prepend(str(_MAIN_DIR / subdir))
    monkeypatch.syspath_prepend(str(_MAIN_DIR))
    return _MAIN_DIR


@pytest.fixture
def frozen_env():
    """Restores os.environ to its pre-test contents after the test runs."""
    snapshot = dict(os.environ)
    yield
    os.environ.clear()
    os.environ.update(snapshot)


def _import_main(name):
    """Imports the named entry module fresh, dropping any cached copy first."""
    sys.modules.pop(name, None)
    return importlib.import_module(name)


@pytest.mark.parametrize("name", DEFER_HEAVY_IMPORTS)
def test_module_imports_without_error(name, main_on_path, frozen_env):
    """Each deferred-import entry module imports without raising."""
    module = _import_main(name)

    assert module is not None


@pytest.mark.parametrize("name", DEFER_HEAVY_IMPORTS)
def test_module_exposes_main_callable(name, main_on_path, frozen_env):
    """Each deferred-import entry module exposes a callable main."""
    module = _import_main(name)

    assert callable(module.main)


@pytest.mark.parametrize("script", ENTRY_SCRIPTS, ids=lambda script: script.stem)
def test_script_imports_in_launcher_subprocess(script, tmp_path):
    """Every entry script runs to completion under runpy in a fresh subprocess, as the launcher does."""
    code   = f"import runpy; runpy.run_path({str(script)!r}, run_name='launcher_import_check')"
    result = subprocess.run([sys.executable, "-u", "-c", code], cwd=str(tmp_path), capture_output=True, text=True, timeout=120)

    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("name", ("pre_process", "extract_params"))
def test_entry_pins_the_environment_before_the_numeric_stack_loads(name, tmp_path):
    """EnvironmentPinner runs before numpy, scipy or pipelines are imported."""
    script = _script_path(name)
    code   = (
        "import sys\n"
        f"sys.path.insert(0, {str(script.parent)!r})\n"
        f"import {name} as entry\n"
        "from _bootstrap import EnvironmentPinner\n"
        "heavy = {'numpy', 'pipelines', 'scipy'}\n"
        "class Stop(Exception): pass\n"
        "def record(*args, **kwargs):\n"
        "    print(sorted({module.split('.')[0] for module in sys.modules} & heavy))\n"
        "    raise Stop\n"
        "EnvironmentPinner.threads = record\n"
        "EnvironmentPinner.gpu     = record\n"
        "EnvironmentPinner.gpus    = record\n"
        "try:\n"
        "    entry.main()\n"
        "except Stop:\n"
        "    pass\n"
    )
    result = subprocess.run([sys.executable, "-u", "-c", code], cwd=str(tmp_path), capture_output=True, text=True, timeout=120)

    assert result.returncode          == 0, result.stderr
    assert result.stdout.splitlines() == ["[]"]


@pytest.mark.parametrize("name", DEFER_HEAVY_IMPORTS)
def test_import_does_not_pin_threads(name, main_on_path, frozen_env, monkeypatch):
    """Importing entry modules leaves the MKL, NumExpr and OpenMP thread variables unset."""
    for key in THREAD_KEYS:
        monkeypatch.delenv(key, raising=False)

    _import_main(name)

    assert all(key not in os.environ for key in THREAD_KEYS)


@pytest.mark.parametrize("name", CLI_MODULES)
def test_entry_config_constructs_from_defaults(name):
    """Every CLI entry config class constructs from its defaults alone."""
    module_path, class_name = ENTRY_CONFIGS[name]
    config_class = getattr(importlib.import_module(module_path), class_name)

    config = config_class()

    assert config is not None


@pytest.mark.parametrize("name", CLI_MODULES)
def test_config_cli_builds_parser_for_entry_config(name):
    """ConfigCli builds an argument parser for every CLI entry config."""
    module_path, class_name = ENTRY_CONFIGS[name]
    config_class = getattr(importlib.import_module(module_path), class_name)

    cli = ConfigCli(config_class(), description=f"{name} cli")

    assert cli.parser is not None


@pytest.mark.parametrize("name", CLI_MODULES)
def test_config_cli_help_config_exits_zero(name):
    """Passing --help-config exits with status zero for every CLI entry config."""
    module_path, class_name = ENTRY_CONFIGS[name]
    config_class = getattr(importlib.import_module(module_path), class_name)

    cli = ConfigCli(config_class())

    with pytest.raises(SystemExit) as excinfo:
        cli.apply(["--help-config"])

    assert excinfo.value.code == 0


@pytest.mark.parametrize("name", CLI_MODULES)
def test_config_cli_apply_no_args_returns_unmodified_config(name):
    """Applying an empty argument list returns the very same config object."""
    module_path, class_name = ENTRY_CONFIGS[name]
    config_class = getattr(importlib.import_module(module_path), class_name)

    config = config_class()
    result = ConfigCli(config).apply([])

    assert result is config


def test_config_cli_rejects_unknown_override():
    """An unrecognised override flag raises ValueError."""
    cli = ConfigCli(PreProcessEntryConfig())

    with pytest.raises(ValueError):
        cli.apply(["--not-a-real-flag", "1"])
