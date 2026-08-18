"""Tests that every main/ entry script imports cleanly and exposes a working CLI.

Covers deferred heavy imports (no torch, pipelines or models pulled in at import time), the
absence of module-level environment side effects (thread pinning, CUDA_VISIBLE_DEVICES), the
ordering of EnvironmentPinner calls relative to the numeric stack, ConfigCli parser construction
for every entry config, the seed-sweep fan-out wiring, and worker-mode argument validation."""

from __future__ import annotations

import importlib
import os
import subprocess
import sys
from pathlib import Path

import pytest

from configuration.inference  import BackboneInferenceEntryConfig
from tools.runtime.config_cli import ConfigCli


_MAIN_DIR = Path(__file__).resolve().parents[2] / "main"
_SUBDIRS  = ("processing", "training", "inference", "experiments", "analysis")

THREAD_KEYS = ("MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS", "OMP_NUM_THREADS")


def _script_path(name):
    """Returns the path of the entry script named `name` under one of the main/ subdirectories."""
    for subdir in _SUBDIRS:
        candidate = _MAIN_DIR / subdir / f"{name}.py"
        if candidate.exists():
            return candidate
    raise FileNotFoundError(f"No entry script named {name}.py under {_MAIN_DIR}")

DEFER_HEAVY_IMPORTS = (
    "train_backbone",
    "train_jepa",
    "train_profile_autoencoder",
    "train_image_autoencoder",
    "train_unrolled",
    "train_dual",
    "infer_backbone",
    "infer_profile_autoencoder",
    "infer_image_autoencoder",
    "infer_unrolled",
    "infer_dual",
    "generate_interferograms",
    "generate_tomogram",
    "tune",
    "benchmark",
    "cross_validate",
    "sweep_patches",
    "tune_dataloader",
    "pre_process",
    "extract_params",
    "inject_external_params",
    "analyze_preprocessing",
    "analyze_param_extraction",
    "export_tensorboard_plots",
    "collect_reports",
)

CLI_MODULES = (
    "infer_backbone",
    "infer_profile_autoencoder",
    "infer_image_autoencoder",
    "infer_unrolled",
    "infer_dual",
    "analyze_preprocessing",
    "analyze_param_extraction",
    "pre_process",
    "extract_params",
    "inject_external_params",
    "tune",
    "tune_dataloader",
    "benchmark",
    "cross_validate",
    "sweep_patches",
    "compare_runs",
    "compare_trials",
    "compare_param_extraction_trials",
    "compare_preprocessing_trials",
    "export_tensorboard_plots",
    "collect_reports",
)

ENTRY_CONFIGS = {
    "infer_backbone"                  : ("configuration.inference",          "BackboneInferenceEntryConfig"),
    "infer_profile_autoencoder"       : ("configuration.inference",          "ProfileAeInferenceEntryConfig"),
    "infer_image_autoencoder"         : ("configuration.inference",          "ImageAeInferenceEntryConfig"),
    "infer_unrolled"                  : ("configuration.inference",          "UnrolledInferenceEntryConfig"),
    "infer_dual"                      : ("configuration.inference",          "DualInferenceEntryConfig"),
    "pre_process"                     : ("configuration.sar.processing_config",        "PreProcessEntryConfig"),
    "extract_params"                  : ("configuration.param_extraction", "ExtractParamsEntryConfig"),
    "inject_external_params"          : ("configuration.param_extraction", "InjectExternalParamsEntryConfig"),
    "analyze_preprocessing"           : ("configuration.sar.processing_config", "PreprocessInferenceConfig"),
    "analyze_param_extraction"        : ("configuration.param_extraction",      "ParamExtractionInferenceConfig"),
    "tune"                            : ("configuration.tuning",                       "TuningEntryConfig"),
    "tune_dataloader"                 : ("configuration.benchmark.dataloader_tuning",  "DataLoaderTuningEntryConfig"),
    "benchmark"                       : ("configuration.benchmark",                    "BenchmarkConfig"),
    "cross_validate"                  : ("configuration.cross_validation",             "CrossValidationConfig"),
    "sweep_patches"                   : ("configuration.patch_sweep",                  "PatchSweepConfig"),
    "compare_runs"                    : ("configuration.comparison",                   "ComparisonEntryConfig"),
    "compare_trials"                  : ("configuration.comparison",                   "TrialComparisonConfig"),
    "compare_param_extraction_trials" : ("configuration.comparison",             "ParamExtractionComparisonConfig"),
    "compare_preprocessing_trials"    : ("configuration.comparison",             "PreprocessingComparisonConfig"),
    "export_tensorboard_plots"        : ("configuration.diagnostics",                  "TensorboardExportEntryConfig"),
    "collect_reports"                 : ("configuration.diagnostics",                  "ReportCollectionEntryConfig"),
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


def test_every_gpu_pin_asks_for_the_same_allocator():
    """No entry pins a GPU without requesting expandable_segments, so VRAM fragments identically everywhere."""
    offenders = []

    for path in sorted(_MAIN_DIR.rglob("*.py")):
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if "EnvironmentPinner.gpu(" in line and "expandable_segments=True" not in line:
                offenders.append(f"{path.relative_to(_MAIN_DIR)}:{number}")

    assert offenders == [], f"these entries pin a GPU without expandable_segments, so the same workload fragments VRAM differently depending on which entry launched it: {offenders}"


def test_import_does_not_set_cuda_visible_devices(main_on_path, frozen_env, monkeypatch):
    """Importing entry modules never assigns CUDA_VISIBLE_DEVICES."""
    monkeypatch.delenv("CUDA_VISIBLE_DEVICES", raising=False)

    for name in DEFER_HEAVY_IMPORTS:
        _import_main(name)

    assert "CUDA_VISIBLE_DEVICES" not in os.environ


@pytest.mark.parametrize("name", ("train_jepa", "train_profile_autoencoder", "train_image_autoencoder"))
def test_seed_sweep_entries_hand_their_script_to_the_fanout(name, main_on_path, frozen_env, monkeypatch):
    """Seed-sweep training entries pass their own script path to SeedSweepLauncher and run it."""
    import pipelines.shared.training.training_launcher as training_launcher

    captured = {}

    class _RecordingLauncher:
        """Stand-in for SeedSweepLauncher that records the keyword arguments it was built with."""
        def __init__(self, *args, **kwargs):
            """Records the construction keyword arguments in the enclosing capture dict."""
            captured.update(kwargs)

        def run(self):
            """Marks the capture dict to show the launcher was run."""
            captured["ran"] = True

    module = _import_main(name)

    monkeypatch.setattr(training_launcher, "SeedSweepLauncher", _RecordingLauncher)
    monkeypatch.setattr(module.EnvironmentPinner, "gpu", lambda *args, **kwargs: None)
    monkeypatch.setattr(sys, "argv", [f"{name}.py"])

    module.main()

    assert captured["ran"]          is True
    assert captured["entry_script"] == _script_path(name)


@pytest.mark.parametrize("name", ("train_backbone", "train_jepa", "train_profile_autoencoder", "train_image_autoencoder", "train_unrolled", "train_dual"))
def test_train_main_defers_heavy_imports(name, tmp_path):
    """Importing a training entry loads no torch, pipelines or models module."""
    script = _script_path(name)
    code   = f"import sys; sys.path.insert(0, {str(script.parent)!r}); import {name}; print(sorted(module for module in sys.modules if module.split('.')[0] in {{'pipelines', 'models', 'torch'}}))"
    result = subprocess.run([sys.executable, "-u", "-c", code], cwd=str(tmp_path), capture_output=True, text=True, timeout=120)

    assert result.returncode     == 0, result.stderr
    assert result.stdout.strip() == "[]"


@pytest.mark.parametrize("name", ("pre_process", "tune_dataloader", "extract_params"))
def test_entry_pins_the_environment_before_the_numeric_stack_loads(name, tmp_path):
    """EnvironmentPinner runs before numpy, torch, scipy, jax, pipelines or models are imported."""
    script = _script_path(name)
    code   = (
        "import sys\n"
        f"sys.path.insert(0, {str(script.parent)!r})\n"
        f"import {name} as entry\n"
        "from _bootstrap import EnvironmentPinner\n"
        "heavy = {'numpy', 'torch', 'pipelines', 'models', 'scipy', 'jax'}\n"
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


def test_compare_runs_has_no_module_level_side_effects(main_on_path, monkeypatch):
    """Importing compare_runs leaves the thread-count environment variables unset."""
    for key in THREAD_KEYS:
        monkeypatch.delenv(key, raising=False)

    sys.modules.pop("compare_runs", None)
    importlib.import_module("compare_runs")

    assert all(key not in os.environ for key in THREAD_KEYS)


def test_compare_runs_exposes_main_callable(main_on_path, frozen_env):
    """The compare_runs module exposes a callable main."""
    module = _import_main("compare_runs")

    assert callable(module.main)


def _comparison_config(base, run_tag=None):
    """Returns a ComparisonEntryConfig whose log base directory is `base`."""
    from configuration.comparison import ComparisonEntryConfig

    config = ComparisonEntryConfig(run_tag=run_tag)
    config.paths.log_base_dir = str(base)

    return config


def _benchmark_run(base, tag):
    """Creates a benchmark run directory `tag` with a training subdirectory under `base`."""
    (base / tag / "training").mkdir(parents=True)


def test_compare_runs_picks_the_newest_timestamp_tag(main_on_path, frozen_env, tmp_path):
    """With only timestamp-shaped tags present, the newest one is chosen automatically."""
    module = _import_main("compare_runs")

    for tag in ("20260810_120000", "20260814_090000", "20260812_235959"):
        _benchmark_run(tmp_path, tag)

    assert module._resolve_run_tag(_comparison_config(tmp_path)) == "20260814_090000"


def test_compare_runs_refuses_to_guess_among_custom_tags(main_on_path, frozen_env, tmp_path):
    """Non-timestamp tags force an explicit --run-tag, which is then honoured."""
    module = _import_main("compare_runs")

    for tag in ("zz_manual_rerun", "physics_sweep"):
        _benchmark_run(tmp_path, tag)

    with pytest.raises(SystemExit, match="--run-tag"):
        module._resolve_run_tag(_comparison_config(tmp_path))

    assert module._resolve_run_tag(_comparison_config(tmp_path, run_tag="zz_manual_rerun")) == "zz_manual_rerun"


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
    cli = ConfigCli(BackboneInferenceEntryConfig())

    with pytest.raises(ValueError):
        cli.apply(["--not-a-real-flag", "1"])


def test_infer_worker_requires_run_dir_and_config(main_on_path, frozen_env, monkeypatch):
    """The backbone inference worker exits when the run directory is given without a config."""
    module = _import_main("infer_backbone")
    monkeypatch.setattr(sys, "argv", ["infer_backbone.py", "--worker", "--run-dir", "x"])

    with pytest.raises(SystemExit):
        module.main()


def test_tune_worker_requires_model(main_on_path, frozen_env, monkeypatch):
    """The tuning worker exits when no model is named."""
    module = _import_main("tune")
    monkeypatch.setattr(sys, "argv", ["tune.py", "--worker"])

    with pytest.raises(SystemExit):
        module.main()


def test_benchmark_worker_requires_model_and_run_tag(main_on_path, frozen_env, monkeypatch):
    """The benchmark train worker exits when the model and run tag are missing."""
    module = _import_main("benchmark")
    monkeypatch.setattr(sys, "argv", ["benchmark.py", "--worker", "train"])

    with pytest.raises(SystemExit):
        module.main()


def test_cross_validate_worker_requires_fold(main_on_path, frozen_env, monkeypatch):
    """The cross-validation train worker exits when no fold index is given."""
    module = _import_main("cross_validate")
    monkeypatch.setattr(sys, "argv", ["cross_validate.py", "--worker", "train"])

    with pytest.raises(SystemExit):
        module.main()


def test_cross_validate_infer_worker_requires_run_tag(main_on_path, frozen_env, monkeypatch):
    """The cross-validation inference worker exits when the run tag is missing."""
    module = _import_main("cross_validate")
    monkeypatch.setattr(sys, "argv", ["cross_validate.py", "--worker", "infer", "--fold", "0"])

    with pytest.raises(SystemExit):
        module.main()
