"""Tests the PyRAT launcher specs, worker job container, and environment setup.

Covers the JSON specs the tomogram and interferogram launchers hand to their
entry scripts, the child log every launcher names in the parent's log, the
entry scripts writing an import failure into that log, the PyRatJob dataclass
fields, and PyRatEnvironment's mutation of LD_LIBRARY_PATH, sys.path, and the
Qt platform."""

from __future__ import annotations

import dataclasses
import importlib
import json
import os
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

from configuration.sar.processing_config import PreProcessEntryConfig, ProcessingConfig, TomogramConfig
from tools.data.regions                  import CropRegion
from tools.sar.interferogram_launcher    import InterferogramLauncher
from tools.sar.pyrat_env                 import PyRatEnvironment
from tools.sar.scene_extent              import SceneExtent, SceneExtentLauncher
from tools.sar.tomogram_launcher         import TomogramLauncher
from tools.sar.tomogram_worker           import PyRatJob, PyRatWorker

from tests.conftest import SilentLogger


REPO_ROOT = Path(__file__).resolve().parents[2]


def _config() -> ProcessingConfig:
    """Returns a ProcessingConfig cropped to a fixed azimuth and range window."""
    crop = CropRegion(azimuth_start=1000, azimuth_end=2000, range_start=500, range_end=1000)
    return ProcessingConfig(crop=crop)


def test_tomogram_build_spec_carries_paths_and_crop():
    """Verifies the tomogram spec records output paths, crop bounds, and stack identifier."""
    config = _config()
    spec   = TomogramLauncher.build_spec(config, Path("/out/tomo.npy"), Path("/out/dem.npy"), Path("/out/meta/tomogram_result.json"))

    assert spec["tomogram_path"] == "/out/tomo.npy"
    assert spec["dem_path"] == "/out/dem.npy"
    assert spec["result_path"] == "/out/meta/tomogram_result.json"
    assert spec["crop"] == [1000, 2000, 500, 1000]
    assert spec["stack_identifier"] == config.stack_identifier


def test_tomogram_build_spec_forwards_worker_plan():
    """Verifies the configured worker count and PyRAT thread count reach the spec."""
    config = _config()
    config.parallel.tomogram_workers = 2
    config.parallel.pyrat_threads    = 8

    spec = TomogramLauncher.build_spec(config, Path("/a"), Path("/b"), Path("/r"))

    assert spec["tomogram_workers"] == 2
    assert spec["pyrat_threads"] == 8


def test_tomogram_build_spec_serialises_tomogram_config():
    """Verifies the beamforming method and height range are serialised into the spec."""
    spec = TomogramLauncher.build_spec(_config(), Path("/a"), Path("/b"), Path("/r"))

    assert spec["tomogram_config"]["beamforming_method"] == "Capon"
    assert tuple(spec["tomogram_config"]["height_range"]) == (-20.0, 80.0)


def test_tomogram_build_spec_is_json_serialisable():
    """Verifies the tomogram spec survives a JSON round trip."""
    spec = TomogramLauncher.build_spec(_config(), Path("/a"), Path("/b"), Path("/r"))

    assert json.loads(json.dumps(spec))["dem_path"] == "/b"


def test_tomogram_launcher_returns_the_written_result(tmp_path):
    """Verifies generate reads back the content audit the dispatched entry wrote at the spec's result path."""
    result = tmp_path / "tomogram_result.json"
    spec   = TomogramLauncher.build_spec(_config(), tmp_path / "tomo.npy", tmp_path / "dem.npy", result)

    class _Dispatcher:
        def dispatch(self, entry, payload, spec_path):
            result.write_text(json.dumps({"content": {"zero_profiles": 3}}))

    launcher            = TomogramLauncher.__new__(TomogramLauncher)
    launcher.logger     = SilentLogger()
    launcher.dispatcher = _Dispatcher()

    assert launcher.generate(spec, tmp_path / "spec.json") == {"content": {"zero_profiles": 3}}


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


def _write_slc(pass_directory: Path, name: str, n_azimuth: int, n_range: int) -> Path:
    """Writes a complex64 RAT2 file of shape (n_azimuth, n_range) under the pass's RGI-SR directory."""
    directory = pass_directory / "RGI" / "RGI-SR"
    directory.mkdir(parents=True, exist_ok=True)

    header = np.zeros(1000, dtype=np.uint8)
    header[:4] = np.frombuffer(b"RAT2", dtype=np.uint8)
    header[8:12]  = np.frombuffer(np.array([2], dtype="<i4").tobytes(), dtype=np.uint8)
    header[16:24] = np.frombuffer(np.array([n_range, n_azimuth], dtype="<i4").tobytes(), dtype=np.uint8)
    header[48:52] = np.frombuffer(np.array([6], dtype="<i4").tobytes(), dtype=np.uint8)

    path = directory / name
    path.write_bytes(header.tobytes() + np.zeros((n_azimuth, n_range), dtype=np.complex64).tobytes())
    return path


def test_scene_extent_reads_azimuth_and_range_from_the_primary_slc(tmp_path):
    """Verifies the extent comes from the RGI-SLC header in (azimuth, range) order."""
    primary = tmp_path / "FL06" / "PS02" / "T01L"
    slc     = _write_slc(primary, "slc_16afrisr0602_Lhh_t01L.rat", n_azimuth=7, n_range=5)

    extent = SceneExtent.from_slc(primary, "hh")

    assert (extent.n_azimuth, extent.n_range) == (7, 5)
    assert extent.slc_path == str(slc)
    assert extent.as_crop().as_tuple() == (0, 7, 0, 5)


def test_scene_extent_picks_the_slc_of_the_requested_polarisation(tmp_path):
    """Verifies several polarisations in RGI-SR are disambiguated by the requested code."""
    primary = tmp_path / "PS02" / "T01L"
    _write_slc(primary, "slc_16afrisr0602_Lhv_t01L.rat", n_azimuth=3, n_range=3)
    _write_slc(primary, "slc_16afrisr0602_Lhh_t01L.rat", n_azimuth=9, n_range=4)

    assert SceneExtent.from_slc(primary, "hh").n_azimuth == 9


def test_scene_extent_fails_loudly_without_an_slc(tmp_path):
    """Verifies a pass without an RGI-SLC product raises instead of guessing a size."""
    with pytest.raises(FileNotFoundError):
        SceneExtent.from_slc(tmp_path, "hh")


def test_scene_extent_spec_is_json_serialisable():
    """Verifies the scene extent spec carries the project settings and the result path."""
    config = TomogramConfig(fusar_project_path="/p.csv", polarisation="hh")
    spec   = SceneExtentLauncher.build_spec(config, "1", Path("/pyrat"), Path("/r/scene_extent.json"))

    decoded = json.loads(json.dumps(spec))

    assert decoded["tomogram_config"]["fusar_project_path"] == "/p.csv"
    assert decoded["tomogram_config"]["polarisation"] == "hh"
    assert decoded["result_path"] == "/r/scene_extent.json"
    assert SceneExtentLauncher.ENTRY == "main/processing/measure_scene_extent.py"


def test_scene_extent_launcher_returns_the_written_result(tmp_path):
    """Verifies measure reads back the extent the dispatched entry wrote."""
    result = tmp_path / "scene_extent.json"
    spec   = SceneExtentLauncher.build_spec(TomogramConfig(), "1", Path("/pyrat"), result)

    class _Dispatcher:
        def dispatch(self, entry, payload, spec_path):
            result.write_text(json.dumps({"n_azimuth": 64000, "n_range": 16000, "primary": "/pass", "slc_path": "/pass/slc.rat"}))

    launcher            = SceneExtentLauncher.__new__(SceneExtentLauncher)
    launcher.logger     = SilentLogger()
    launcher.dispatcher = _Dispatcher()

    extent = launcher.measure(spec, tmp_path / "spec.json")

    assert (extent.n_azimuth, extent.n_range) == (64000, 16000)


@pytest.mark.parametrize("crop, expected", [((0, 0, 0, 0), True), ((0, 100, 0, 0), False), ((1000, 16000, 500, 4000), False)])
def test_full_scene_is_selected_only_when_every_crop_field_is_zero(crop, expected):
    """Verifies the full-scene switch needs all four crop fields at zero."""
    config = PreProcessEntryConfig(azimuth_start=crop[0], azimuth_end=crop[1], range_start=crop[2], range_end=crop[3])

    assert config.spans_full_scene is expected


class _DispatchRecorder(SilentLogger):
    """Silent logger that records subsections and errors.

    Attributes:
        subsections : Messages passed to subsection().
        errors      : Messages passed to error().
    """

    def __init__(self):
        """Initialises the empty buffers."""
        self.subsections = []
        self.errors      = []

    def subsection(self, message):
        """Records a subsection heading."""
        self.subsections.append(message)

    def error(self, message):
        """Records an error."""
        self.errors.append(message)


class _FailingDispatcher:
    """Dispatcher stand-in whose entry script exits with status 1."""

    def dispatch(self, entry, payload, spec_path):
        """Raises the error subprocess.run raises for a non-zero exit."""
        raise subprocess.CalledProcessError(1, ["python", entry, "--spec", str(spec_path)])


@pytest.mark.parametrize("launcher_class, log_name", ((TomogramLauncher, "tomogram"), (InterferogramLauncher, "interferograms"), (SceneExtentLauncher, "scene_extent")))
def test_launcher_child_log_sits_next_to_the_spec(launcher_class, log_name):
    """Every launcher names the log its entry script writes beside the spec file."""
    assert launcher_class.child_log(Path("/run/meta/x_spec.json")) == Path(f"/run/meta/{log_name}.log")


def test_tomogram_launcher_names_the_child_log_and_reports_a_failed_entry(tmp_path):
    """The parent's log names the child log before dispatching and again, with the exit status, when the entry fails."""
    spec_path = tmp_path / "meta" / "tomogram_spec.json"
    recorder  = _DispatchRecorder()

    launcher            = TomogramLauncher.__new__(TomogramLauncher)
    launcher.logger     = recorder
    launcher.dispatcher = _FailingDispatcher()

    with pytest.raises(subprocess.CalledProcessError):
        launcher.generate({"result_path": str(tmp_path / "meta" / "tomogram_result.json")}, spec_path)

    child_log = tmp_path / "meta" / "tomogram.log"

    assert recorder.subsections == [f"Child log: {child_log}"]
    assert recorder.errors      == [f"main/processing/generate_tomogram.py exited with status 1; its traceback is in {child_log}"]


def test_scene_extent_launcher_reports_a_failed_entry(tmp_path):
    """The scene-extent probe names its child log when its entry fails."""
    recorder = _DispatchRecorder()

    launcher            = SceneExtentLauncher.__new__(SceneExtentLauncher)
    launcher.logger     = recorder
    launcher.dispatcher = _FailingDispatcher()

    with pytest.raises(subprocess.CalledProcessError):
        launcher.measure({"result_path": str(tmp_path / "scene_extent.json")}, tmp_path / "scene_extent_spec.json")

    assert str(tmp_path / "scene_extent.log") in recorder.errors[0]


@pytest.mark.parametrize("launcher_class, generator_module", (
    (TomogramLauncher,      "pipelines.processing.generation.tomogram"),
    (InterferogramLauncher, "pipelines.processing.generation.interferogram"),
    (SceneExtentLauncher,   "pipelines.processing.generation.scene_extent"),
))
def test_entry_script_writes_a_generator_import_failure_into_the_child_log(launcher_class, generator_module, tmp_path, monkeypatch):
    """An entry whose generator fails to import ends the child log the launcher names with the ABORTED banner and the import error."""
    entry_name = Path(launcher_class.ENTRY).stem
    spec_path  = tmp_path / "meta" / "spec.json"

    spec_path.parent.mkdir()
    monkeypatch.setattr(sys, "path", list(sys.path))
    monkeypatch.syspath_prepend(str(REPO_ROOT / "main" / "processing"))
    monkeypatch.setitem(sys.modules, generator_module, None)
    monkeypatch.delitem(sys.modules, entry_name, raising=False)

    module = importlib.import_module(entry_name)

    monkeypatch.setattr(module.EnvironmentPinner, "threads", classmethod(lambda cls, count=4: None))
    monkeypatch.setattr(sys, "argv", [entry_name, "--spec", str(spec_path)])

    with pytest.raises(ImportError):
        module.main()

    log_text = launcher_class.child_log(spec_path).read_text()

    assert f"ABORTED {launcher_class.LOG_NAME}" in log_text
    assert "ModuleNotFoundError" in log_text
    assert generator_module in log_text
