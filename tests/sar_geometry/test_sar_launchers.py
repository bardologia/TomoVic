"""Tests the PyRAT launcher specs, worker job container, and environment setup.

Covers the JSON specs the tomogram and interferogram launchers hand to their
entry scripts, the PyRatJob dataclass fields, and PyRatEnvironment's mutation of
LD_LIBRARY_PATH, sys.path, and the Qt platform."""

from __future__ import annotations

import dataclasses
import json
import os
import sys
from pathlib import Path

from configuration.sar.processing_config import ProcessingConfig
from tools.data.regions                  import CropRegion
from tools.sar.interferogram_launcher    import InterferogramLauncher
from tools.sar.pyrat_env                 import PyRatEnvironment
from tools.sar.tomogram_launcher         import TomogramLauncher
from tools.sar.tomogram_worker           import PyRatJob, PyRatWorker


def _config() -> ProcessingConfig:
    """Returns a ProcessingConfig cropped to a fixed azimuth and range window."""
    crop = CropRegion(azimuth_start=1000, azimuth_end=2000, range_start=500, range_end=1000)
    return ProcessingConfig(crop=crop)


def test_tomogram_build_spec_carries_paths_and_crop():
    """Verifies the tomogram spec records output paths, crop bounds, and stack identifier."""
    config = _config()
    spec   = TomogramLauncher.build_spec(config, Path("/out/tomo.npy"), Path("/out/dem.npy"))

    assert spec["tomogram_path"] == "/out/tomo.npy"
    assert spec["dem_path"] == "/out/dem.npy"
    assert spec["crop"] == [1000, 2000, 500, 1000]
    assert spec["stack_identifier"] == config.stack_identifier


def test_tomogram_build_spec_forwards_worker_plan():
    """Verifies the configured worker count and PyRAT thread count reach the spec."""
    config = _config()
    config.parallel.tomogram_workers = 2
    config.parallel.pyrat_threads    = 8

    spec = TomogramLauncher.build_spec(config, Path("/a"), Path("/b"))

    assert spec["tomogram_workers"] == 2
    assert spec["pyrat_threads"] == 8


def test_tomogram_build_spec_serialises_tomogram_config():
    """Verifies the beamforming method and height range are serialised into the spec."""
    spec = TomogramLauncher.build_spec(_config(), Path("/a"), Path("/b"))

    assert spec["tomogram_config"]["beamforming_method"] == "Capon"
    assert tuple(spec["tomogram_config"]["height_range"]) == (-20.0, 80.0)


def test_tomogram_build_spec_is_json_serialisable():
    """Verifies the tomogram spec survives a JSON round trip."""
    spec = TomogramLauncher.build_spec(_config(), Path("/a"), Path("/b"))

    assert json.loads(json.dumps(spec))["dem_path"] == "/b"


def test_interferogram_build_spec_all_paths_present():
    """Verifies every interferogram output path appears in the spec as a string."""
    spec = InterferogramLauncher.build_spec(
        _config(),
        primary_path        = Path("/p.npy"),
        secondaries_path    = Path("/s.npy"),
        interferograms_path = Path("/i.npy"),
        baselines_path      = Path("/bl.json"),
        profiles_path       = Path("/pr.npz"),
        parameters_path     = Path("/pp.json"),
        result_path         = Path("/r.json"),
    )

    assert spec["primary_path"] == "/p.npy"
    assert spec["secondaries_path"] == "/s.npy"
    assert spec["interferograms_path"] == "/i.npy"
    assert spec["baselines_path"] == "/bl.json"
    assert spec["profiles_path"] == "/pr.npz"
    assert spec["parameters_path"] == "/pp.json"
    assert spec["result_path"] == "/r.json"


def test_interferogram_build_spec_includes_pyrat_threads():
    """Verifies the interferogram spec carries the PyRAT thread count and effort level."""
    spec = InterferogramLauncher.build_spec(
        _config(),
        primary_path        = Path("/p"),
        secondaries_path    = Path("/s"),
        interferograms_path = Path("/i"),
        baselines_path      = Path("/bl"),
        profiles_path       = Path("/pr"),
        parameters_path     = Path("/pp"),
        result_path         = Path("/r"),
    )

    assert "pyrat_threads" in spec
    assert spec["effort"] == "high"


def test_interferogram_build_spec_is_json_serialisable():
    """Verifies the interferogram spec survives a JSON round trip with its crop."""
    spec = InterferogramLauncher.build_spec(
        _config(),
        primary_path        = Path("/p"),
        secondaries_path    = Path("/s"),
        interferograms_path = Path("/i"),
        baselines_path      = Path("/bl"),
        profiles_path       = Path("/pr"),
        parameters_path     = Path("/pp"),
        result_path         = Path("/r"),
    )

    assert json.loads(json.dumps(spec))["crop"] == [1000, 2000, 500, 1000]


def test_launcher_entry_points():
    """Verifies both launchers point at their processing entry scripts."""
    assert TomogramLauncher.ENTRY == "main/processing/generate_tomogram.py"
    assert InterferogramLauncher.ENTRY == "main/processing/generate_interferograms.py"


def test_pyrat_job_is_dataclass_with_expected_fields():
    """Verifies PyRatJob declares the fields the worker consumes."""
    names = {f.name for f in dataclasses.fields(PyRatJob)}

    assert {"pyrat_root_path", "crop_tuple", "height_range", "beamforming_method", "pyrat_threads"} <= names


def test_pyrat_worker_holds_job():
    """Verifies PyRatWorker keeps the job instance it was constructed with."""
    job    = PyRatJob(
        pyrat_root_path       = "/pyrat",
        crop_tuple            = (0, 10, 0, 10),
        suffix                = "x",
        fusar_project_path    = "/f.csv",
        stack_identifier      = "1",
        base_directory        = "/base",
        polarisation          = "hv",
        track_selection       = "*",
        height_range          = (-20.0, 80.0),
        filter_method         = "Boxcar",
        filter_arguments      = {"win": [20, 10]},
        beamforming_method    = "Capon",
        beamforming_arguments = [],
        output_directory      = "/out",
        apply_resampling      = False,
        apply_presumming      = False,
        pyrat_threads         = 4,
    )
    worker = PyRatWorker(job)

    assert worker.job is job


def test_env_adds_conda_lib_to_ld_path(monkeypatch):
    """Verifies the conda lib directory is added when LD_LIBRARY_PATH is unset."""
    monkeypatch.setattr(sys, "prefix", "/fake/prefix")
    monkeypatch.delenv("LD_LIBRARY_PATH", raising=False)

    PyRatEnvironment.ensure_conda_lib_on_ld_path()

    assert os.environ["LD_LIBRARY_PATH"] == "/fake/prefix/lib"


def test_env_does_not_duplicate_conda_lib(monkeypatch):
    """Verifies an already present conda lib entry is not added twice."""
    monkeypatch.setattr(sys, "prefix", "/fake/prefix")
    monkeypatch.setenv("LD_LIBRARY_PATH", "/fake/prefix/lib:/other")

    PyRatEnvironment.ensure_conda_lib_on_ld_path()

    assert os.environ["LD_LIBRARY_PATH"].count("/fake/prefix/lib") == 1


def test_env_prepends_to_existing_ld_path(monkeypatch):
    """Verifies the conda lib directory is prepended to an existing LD_LIBRARY_PATH."""
    monkeypatch.setattr(sys, "prefix", "/fake/prefix")
    monkeypatch.setenv("LD_LIBRARY_PATH", "/existing")

    PyRatEnvironment.ensure_conda_lib_on_ld_path()

    assert os.environ["LD_LIBRARY_PATH"] == "/fake/prefix/lib:/existing"


def test_env_adds_pyrat_root_to_sys_path(monkeypatch):
    """Verifies the PyRAT root is inserted at the front of sys.path."""
    monkeypatch.setattr(sys, "path", list(sys.path))

    PyRatEnvironment.ensure_root_on_sys_path("/unique/pyrat/root")

    assert sys.path[0] == "/unique/pyrat/root"


def test_env_does_not_duplicate_sys_path_entry(monkeypatch):
    """Verifies an already present PyRAT root is not inserted a second time."""
    monkeypatch.setattr(sys, "path", ["/unique/pyrat/root"] + list(sys.path))

    PyRatEnvironment.ensure_root_on_sys_path("/unique/pyrat/root")

    assert sys.path.count("/unique/pyrat/root") == 1


def test_env_ensure_sets_offscreen_platform(monkeypatch):
    """Verifies the full setup forces the offscreen Qt platform."""
    monkeypatch.setattr(sys, "path", list(sys.path))
    monkeypatch.delenv("QT_QPA_PLATFORM", raising=False)

    PyRatEnvironment.ensure("/some/pyrat")

    assert os.environ["QT_QPA_PLATFORM"] == "offscreen"
