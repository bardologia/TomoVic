"""Tests for the polarimetric primary pipeline.

Covers the PyRat loader driven by a fake pyrat module (one single-channel call
per polarisation found on disk, in the call shape preprocessing uses), the
worker generator run against a fake loader (artifact order, sidecar, result
payload, the sqrt 2 scaling of a lone HV channel, the strict HV alignment check
and the reciprocity check between HV and VH), the launcher specification, and
the dataset pipeline verifying, registering, skipping and overwriting the
artifact.
"""

from __future__ import annotations

import json
import sys
import types
from dataclasses import asdict
from pathlib import Path

import numpy as np
import pytest

from configuration.sar.polarimetry_config        import PolarimetryEntryConfig
from configuration.sar.processing_config         import TomogramConfig
from pipelines.processing.polarimetry.extraction import CrossPolarCheck, LoadedChannels, PolarimetricPrimaryGenerator, PolarimetricPrimaryLoader, ReciprocityCheck
from pipelines.processing.polarimetry.pipeline   import DatasetRecord, PolarimetryPipeline
from tools.sar.polarimetry                       import PolarimetricArtifact
from tools.sar.polarimetry_launcher              import PolarimetricLauncher

SHAPE  = (6, 4)
WINDOW = [4, 2]


class RecordingLogger:
    """Logger stub that stores messages by level.

    Attributes:
        infos : Informational messages in emission order.
        oks   : Success messages in emission order.
    """

    def __init__(self) -> None:
        """Initialises the empty message lists."""
        self.infos : list[str] = []
        self.oks   : list[str] = []

    def info(self, message) -> None:
        """Records an informational message."""
        self.infos.append(str(message))

    def ok(self, message) -> None:
        """Records a success message."""
        self.oks.append(str(message))

    def warning(self, message) -> None:
        """Discards a warning message."""
        pass

    def error(self, message) -> None:
        """Discards an error message."""
        pass

    def section(self, message) -> None:
        """Discards a section heading."""
        pass

    def subsection(self, message) -> None:
        """Discards a subsection heading."""
        pass

    def kv_table(self, data, title=None) -> None:
        """Discards a key-value table."""
        pass


class FakeLoader:
    """Loader stub returning a preset channel stack and recording its construction.

    Attributes:
        stack  : Channel stack returned by ``load``.
        labels : Channel labels returned by ``load``.
        built  : Constructor arguments of every instance, as (crop, pyrat_directory, threads).
        loads  : Number of ``load`` calls across instances.
    """

    stack  = None
    labels = None
    built  : list = []
    loads  = 0

    def __init__(self, tomogram_config, stack_identifier, crop, pyrat_directory, threads, logger) -> None:
        """Records the construction arguments."""
        assert isinstance(tomogram_config, TomogramConfig)
        FakeLoader.built.append((tuple(crop), Path(pyrat_directory), int(threads)))

    def load(self) -> LoadedChannels:
        """Returns the preset stack."""
        FakeLoader.loads += 1
        return LoadedChannels(stack=FakeLoader.stack, labels=list(FakeLoader.labels), primary_directory="/fsar/PS02", band="L", product="RGI-SLC")


class InProcessLauncher:
    """Launcher stand-in running the real generator in this process with the fake loader.

    Attributes:
        logger : Logger handed to the generator.
        specs  : Specification paths written, in call order.
    """

    def __init__(self, logger) -> None:
        """Stores the logger and an empty call record."""
        self.logger = logger
        self.specs  : list[Path] = []

    def generate(self, spec: dict, spec_path: Path) -> dict:
        """Writes the spec like the dispatcher does and runs the generator on it."""
        spec_path.parent.mkdir(parents=True, exist_ok=True)
        spec_path.write_text(json.dumps(spec), encoding="utf-8")
        self.specs.append(spec_path)

        return PolarimetricPrimaryGenerator(spec, self.logger, loader_class=FakeLoader).run()


class SilentWorkerLauncher:
    """Launcher stand-in that reports success without writing anything."""

    def generate(self, spec: dict, spec_path: Path) -> dict:
        """Returns a plausible result payload and writes no file."""
        return {"shape": [3, *SHAPE], "loader_channels": ["HH", "HV", "VH", "VV"], "cross_source": "hv+vh", "cross_polar_check": {"match": "exact", "coherence": 1.0, "relative_error": 0.0, "power_ratio": 1.0}, "reciprocity_check": None, "provenance": {}}


class MisalignedWorkerLauncher:
    """Launcher stand-in that writes an array one azimuth line too tall."""

    def generate(self, spec: dict, spec_path: Path) -> dict:
        """Writes a misaligned array and its sidecar, then reports the wrong shape as if correct."""
        rng   = np.random.default_rng(0)
        shape = (3, SHAPE[0] + 1, SHAPE[1])
        np.save(spec["artifact_path"], (rng.normal(size=shape) + 1j * rng.normal(size=shape)).astype(np.complex64))
        Path(spec["sidecar_path"]).write_text("{}", encoding="utf-8")

        return {"shape": list(shape), "loader_channels": ["HH", "HV", "VH", "VV"], "cross_source": "hv+vh", "cross_polar_check": {"match": "exact", "coherence": 1.0, "relative_error": 0.0, "power_ratio": 1.0}, "reciprocity_check": None, "provenance": {}}


def _complex(rng: np.random.Generator) -> np.ndarray:
    """Returns one random complex64 image of the test shape."""
    return (rng.normal(size=SHAPE) + 1j * rng.normal(size=SHAPE)).astype(np.complex64)


def _dataset(base: Path, primary: np.ndarray) -> Path:
    """Writes a minimal dataset directory with a primary SLC, its layout and config state."""
    run = base / "dataset"
    (run / "data").mkdir(parents=True)
    (run / "meta").mkdir()

    np.save(run / "data" / "primary.npy", primary)

    layout = {"global_crop": [0, SHAPE[0], 0, SHAPE[1]], "artifacts": {"primary": "primary.npy", "tomogram_full": "tomogram_full.npy"}, "pass_labels": ["T01"]}
    (run / "data" / "dataset.json").write_text(json.dumps(layout), encoding="utf-8")

    tomogram     = TomogramConfig(fusar_project_path="/fsar/project.csv", base_directory="/fsar/", polarisation="hv", filter_arguments={"win": WINDOW})
    config_state = {"tomogram_config": asdict(tomogram), "stack_identifier": "1", "paths": {"pyrat_directory": "/recorded/pyrat"}}
    (run / "meta" / "config_state.json").write_text(json.dumps(config_state), encoding="utf-8")

    return run


def _config(**overrides) -> PolarimetryEntryConfig:
    """Returns an entry config pointing PyRat at a test root."""
    values = {"pyrat_directory": Path("/test/pyrat"), "pyrat_threads": 2}
    values.update(overrides)
    return PolarimetryEntryConfig(**values)


def _layout(run: Path) -> dict:
    """Reads the dataset layout back."""
    return json.loads((run / "data" / "dataset.json").read_text(encoding="utf-8"))


@pytest.fixture(autouse=True)
def _reset_fake_loader():
    """Clears the fake loader's recorded state before every test."""
    FakeLoader.built = []
    FakeLoader.loads = 0
    yield


def test_pipeline_extracts_verifies_and_registers(tmp_path):
    """Checks the full chain reorders the loader stack, averages HV and VH, writes the sidecar with both checks and registers the artifact."""
    rng     = np.random.default_rng(0)
    hh      = _complex(rng)
    vv      = _complex(rng)
    primary = _complex(rng)
    vh      = primary + 0.1 * _complex(rng)

    FakeLoader.stack  = np.stack([vv, primary, vh, hh])
    FakeLoader.labels = ["VV", "HV", "VH", "HH"]

    run     = _dataset(tmp_path, primary)
    logger  = RecordingLogger()
    config  = _config()
    summary = PolarimetryPipeline(run, config, logger, launcher=InProcessLauncher(logger)).run()

    assert summary["skipped"] is False
    assert summary["shape"] == (3, *SHAPE)
    assert summary["cross_source"] == "hv+vh"
    assert summary["cross_polar_check"]["match"] == "exact"

    written = np.load(run / "data" / PolarimetricArtifact.FILENAME)
    assert written.dtype == np.complex64
    np.testing.assert_allclose(written[0], hh)
    np.testing.assert_allclose(written[1], (primary + vh) / np.sqrt(2.0), rtol=1e-5)
    np.testing.assert_allclose(written[2], vv)

    sidecar = json.loads((run / "meta" / PolarimetricArtifact.SIDECAR).read_text(encoding="utf-8"))
    assert sidecar["channels"] == ["hh", "xx", "vv"]
    assert sidecar["loader_channels"] == ["VV", "HV", "VH", "HH"]
    assert sidecar["cross_source"] == "hv+vh"
    assert sidecar["symmetrised"] is True
    assert sidecar["window"] == WINDOW
    assert sidecar["shape"] == [3, *SHAPE]
    assert sidecar["crop"] == [0, SHAPE[0], 0, SHAPE[1]]
    assert sidecar["cross_polar_check"] == {"match": "exact", "coherence": pytest.approx(1.0), "relative_error": 0.0, "power_ratio": pytest.approx(1.0)}
    assert sidecar["reciprocity_check"]["coherence"] > 0.99
    assert abs(sidecar["reciprocity_check"]["power_ratio_db"]) < 0.2
    assert abs(sidecar["reciprocity_check"]["phase_deg"]) < 5.0
    assert 0.0 < sidecar["reciprocity_check"]["residual"] < 0.05
    assert sidecar["provenance"]["pyrat_directory"] == "/test/pyrat"

    layout = _layout(run)
    assert layout["artifacts"][PolarimetricArtifact.ARTIFACT_KEY] == PolarimetricArtifact.FILENAME
    assert layout["artifacts"]["primary"] == "primary.npy"
    assert layout["pass_labels"] == ["T01"]

    assert (run / "meta" / "polarimetry_spec.json").is_file()
    assert json.loads((run / "meta" / "polarimetry_result.json").read_text(encoding="utf-8"))["shape"] == [3, *SHAPE]
    assert FakeLoader.built == [((0, SHAPE[0], 0, SHAPE[1]), Path("/test/pyrat"), 2)]
    assert len(logger.oks) == 1


def test_generator_scales_lone_hv_and_checks_it_against_the_primary(tmp_path):
    """Checks a plain HV channel is stored as sqrt 2 HV and compared directly with primary.npy."""
    rng     = np.random.default_rng(1)
    primary = _complex(rng)

    FakeLoader.stack  = np.stack([_complex(rng), primary, _complex(rng)])
    FakeLoader.labels = ["hh", "hv", "vv"]

    run    = _dataset(tmp_path, primary)
    logger = RecordingLogger()
    PolarimetryPipeline(run, _config(), logger, launcher=InProcessLauncher(logger)).run()

    written = np.load(run / "data" / PolarimetricArtifact.FILENAME)
    np.testing.assert_allclose(written[1], primary * np.sqrt(2.0), rtol=1e-6)

    sidecar = json.loads((run / "meta" / PolarimetricArtifact.SIDECAR).read_text(encoding="utf-8"))
    assert sidecar["cross_source"] == "hv"
    assert sidecar["symmetrised"] is False
    assert sidecar["cross_polar_check"]["match"] == "exact"
    assert sidecar["reciprocity_check"] is None


def test_generator_symmetrises_hv_and_vh_and_still_checks_hv(tmp_path):
    """Checks HV and VH are averaged into the artifact while the raw HV channel is the one checked."""
    rng     = np.random.default_rng(10)
    primary = _complex(rng)
    vh      = primary + 0.1 * _complex(rng)

    FakeLoader.stack  = np.stack([_complex(rng), primary, vh, _complex(rng)])
    FakeLoader.labels = ["hh", "hv", "vh", "vv"]

    run    = _dataset(tmp_path, primary)
    logger = RecordingLogger()
    PolarimetryPipeline(run, _config(), logger, launcher=InProcessLauncher(logger)).run()

    written = np.load(run / "data" / PolarimetricArtifact.FILENAME)
    np.testing.assert_allclose(written[1], (primary + vh) / np.sqrt(2.0), rtol=1e-5)

    sidecar = json.loads((run / "meta" / PolarimetricArtifact.SIDECAR).read_text(encoding="utf-8"))
    assert sidecar["cross_source"] == "hv+vh"
    assert sidecar["symmetrised"] is True
    assert sidecar["cross_polar_check"]["match"] == "exact"
    assert sidecar["reciprocity_check"]["coherence"] > 0.99
    assert abs(sidecar["reciprocity_check"]["power_ratio_db"]) < 0.2


class FakePyrat:
    """Fake pyrat module recording the single-channel loads the loader issues.

    Attributes:
        calls  : Keyword arguments of every ``load.fsar`` call, in order.
        images : Image returned per polarisation code.
        master : Primary pass directory the fake stack names.
    """

    calls  : list = []
    images : dict = {}
    master = ""

    @classmethod
    def module(cls) -> types.ModuleType:
        """Builds a module object exposing pyrat_init, tomo.FuSARtomo, load.fsar and getdata."""
        module = types.ModuleType("pyrat")

        def pyrat_init(debug=False, nthreads=1):
            cls.calls.append({"init_threads": nthreads})

        class FuSARtomo:
            def __init__(self, **kwargs):
                self.master = cls.master
                self.band   = "L"
                self.crop   = kwargs["crop"]
                self.kwargs = kwargs

        def fsar(master, **kwargs):
            cls.calls.append({"master": master, **kwargs})
            return kwargs["polarisations"]

        module.pyrat_init = pyrat_init
        module.tomo       = types.SimpleNamespace(FuSARtomo=FuSARtomo)
        module.load       = types.SimpleNamespace(fsar=fsar)
        module.getdata    = lambda layer: cls.images[layer]

        return module


def _primary_pass(base: Path, polarisations) -> Path:
    """Writes stub RGI-SLC files of the given polarisations under a pass directory."""
    pass_dir = base / "FL01" / "PS02"
    slc_dir  = pass_dir / "RGI" / "RGI-SR"
    slc_dir.mkdir(parents=True)
    for polarisation in polarisations:
        (slc_dir / f"slc_17sartom0102_L{polarisation}_t01L.rat").write_text("stub")
    return pass_dir


def test_loader_issues_one_single_channel_call_per_polarisation_on_disk(tmp_path, monkeypatch):
    """Checks the loader reads each polarisation found on disk with the exact call preprocessing uses."""
    rng      = np.random.default_rng(11)
    pass_dir = _primary_pass(tmp_path, ("hh", "hv", "vh", "vv"))
    images   = {polarisation: _complex(rng) for polarisation in ("hh", "hv", "vh", "vv")}

    FakePyrat.calls  = []
    FakePyrat.images = images
    FakePyrat.master = str(pass_dir)
    monkeypatch.setitem(sys.modules, "pyrat", FakePyrat.module())
    monkeypatch.setattr(sys, "path", list(sys.path))

    tomogram = TomogramConfig(fusar_project_path="/fsar/project.csv", base_directory="/fsar/", polarisation="hv")
    loaded   = PolarimetricPrimaryLoader(tomogram, "1", (0, SHAPE[0], 0, SHAPE[1]), tmp_path / "pyrat", 2, RecordingLogger()).load()

    assert loaded.labels == ["hh", "hv", "vh", "vv"]
    assert loaded.stack.shape == (4, *SHAPE) and loaded.stack.dtype == np.complex64
    for index, polarisation in enumerate(loaded.labels):
        np.testing.assert_allclose(loaded.stack[index], images[polarisation])
    assert loaded.primary_directory == str(pass_dir) and loaded.band == "L" and loaded.product == "RGI-SLC"

    loads = [call for call in FakePyrat.calls if "master" in call]
    assert [call["polarisations"] for call in loads] == ["hh", "hv", "vh", "vv"]
    for call in loads:
        assert call["master"] == str(pass_dir)
        assert call["product"] == "RGI-SLC"
        assert call["bands"] == "L"
        assert call["crop"] == [0, SHAPE[0], 0, SHAPE[1]]
        assert call["sym"] is True
    assert FakePyrat.calls[0] == {"init_threads": 2}


def test_loader_refuses_a_pass_without_the_co_polar_channels(tmp_path, monkeypatch):
    """Checks a primary pass lacking HH or VV on disk stops the loader before any PyRat load."""
    pass_dir = _primary_pass(tmp_path, ("hv", "vv"))

    FakePyrat.calls  = []
    FakePyrat.images = {}
    FakePyrat.master = str(pass_dir)
    monkeypatch.setitem(sys.modules, "pyrat", FakePyrat.module())
    monkeypatch.setattr(sys, "path", list(sys.path))

    loader = PolarimetricPrimaryLoader(TomogramConfig(), "1", (0, SHAPE[0], 0, SHAPE[1]), tmp_path / "pyrat", 2, RecordingLogger())

    with pytest.raises(FileNotFoundError, match="no RGI-SLC for \\['hh'\\]"):
        loader.load()

    assert not any("master" in call for call in FakePyrat.calls)


def _assert_nothing_written(run: Path) -> None:
    """Asserts neither the artifact, nor its sidecar, nor the layout entry exists."""
    assert not (run / "data" / PolarimetricArtifact.FILENAME).exists()
    assert not (run / "meta" / PolarimetricArtifact.SIDECAR).exists()
    assert PolarimetricArtifact.ARTIFACT_KEY not in _layout(run)["artifacts"]


def test_generator_refuses_unrelated_pixels(tmp_path):
    """Checks a loader stack incoherent with primary.npy stops before anything is written or registered."""
    rng = np.random.default_rng(2)

    FakeLoader.stack  = np.stack([_complex(rng), _complex(rng), _complex(rng)])
    FakeLoader.labels = ["hh", "hv", "vv"]

    run    = _dataset(tmp_path, _complex(rng))
    logger = RecordingLogger()

    with pytest.raises(ValueError, match="crop or the primary pass"):
        PolarimetryPipeline(run, _config(), logger, launcher=InProcessLauncher(logger)).run()

    _assert_nothing_written(run)


def test_generator_refuses_a_coherent_but_inexact_hv(tmp_path):
    """Checks an HV channel that is the same scene but not the same read as primary.npy is refused."""
    rng     = np.random.default_rng(12)
    primary = _complex(rng)
    hv      = primary + 0.2 * _complex(rng)

    FakeLoader.stack  = np.stack([_complex(rng), hv, primary, _complex(rng)])
    FakeLoader.labels = ["hh", "hv", "vh", "vv"]

    run    = _dataset(tmp_path, primary)
    logger = RecordingLogger()

    with pytest.raises(ValueError, match="read differently"):
        PolarimetryPipeline(run, _config(), logger, launcher=InProcessLauncher(logger)).run()

    _assert_nothing_written(run)


def test_generator_refuses_a_vh_unrelated_to_hv(tmp_path):
    """Checks a VH channel that does not describe the same pixels as HV is refused before anything is written."""
    rng     = np.random.default_rng(13)
    primary = _complex(rng)

    FakeLoader.stack  = np.stack([_complex(rng), primary, _complex(rng), _complex(rng)])
    FakeLoader.labels = ["hh", "hv", "vh", "vv"]

    run    = _dataset(tmp_path, primary)
    logger = RecordingLogger()

    with pytest.raises(ValueError, match="hv and vh"):
        PolarimetryPipeline(run, _config(), logger, launcher=InProcessLauncher(logger)).run()

    _assert_nothing_written(run)


def test_cross_polar_check_reports_the_power_ratio_and_refuses_a_scaled_channel():
    """Checks the same read passes with a unit power ratio and a channel off by sqrt 2 is refused with the scale in the message."""
    rng     = np.random.default_rng(3)
    primary = _complex(rng)

    result = CrossPolarCheck(primary, primary.copy()).run()
    assert result == {"match": "exact", "coherence": pytest.approx(1.0), "relative_error": 0.0, "power_ratio": pytest.approx(1.0)}

    with pytest.raises(ValueError, match="power ratio 2.000"):
        CrossPolarCheck(primary, primary * np.sqrt(2.0)).run()


def test_reciprocity_check_measures_agreement_and_refuses_unrelated_channels():
    """Checks identical channels read as perfect reciprocity, a scaled copy reports its ratio, and unrelated channels are refused."""
    rng = np.random.default_rng(14)
    hv  = _complex(rng)

    same = ReciprocityCheck(hv, hv.copy()).run()
    assert same["coherence"] == pytest.approx(1.0)
    assert same["power_ratio_db"] == pytest.approx(0.0, abs=1e-5)
    assert same["phase_deg"] == pytest.approx(0.0, abs=1e-3)
    assert same["residual"] == pytest.approx(0.0, abs=1e-9)

    scaled = ReciprocityCheck(hv, hv * 2.0).run()
    assert scaled["power_ratio_db"] == pytest.approx(10.0 * np.log10(4.0), abs=1e-4)

    with pytest.raises(ValueError, match="hv and vh"):
        ReciprocityCheck(hv, _complex(rng)).run()

    with pytest.raises(ValueError, match="shape"):
        ReciprocityCheck(hv, hv[:3])


def test_cross_polar_check_rejects_shape_mismatch():
    """Checks images of different shapes are refused outright."""
    rng = np.random.default_rng(4)

    with pytest.raises(ValueError, match="shape"):
        CrossPolarCheck(_complex(rng), _complex(rng)[:3])


def test_pipeline_skips_present_artifact_unless_overwritten(tmp_path):
    """Checks a registered artifact with its files is skipped, and extracted again with overwrite."""
    rng     = np.random.default_rng(5)
    primary = _complex(rng)

    FakeLoader.stack  = np.stack([_complex(rng), primary, _complex(rng)])
    FakeLoader.labels = ["hh", "hv", "vv"]

    run    = _dataset(tmp_path, primary)
    logger = RecordingLogger()

    PolarimetryPipeline(run, _config(), logger, launcher=InProcessLauncher(logger)).run()
    assert FakeLoader.loads == 1

    skipped = PolarimetryPipeline(run, _config(), logger, launcher=InProcessLauncher(logger)).run()
    assert skipped == {"skipped": True}
    assert FakeLoader.loads == 1
    assert any("skip" in message for message in logger.infos)

    PolarimetryPipeline(run, _config(overwrite=True), logger, launcher=InProcessLauncher(logger)).run()
    assert FakeLoader.loads == 2


def test_pipeline_refuses_a_worker_that_wrote_nothing(tmp_path):
    """Checks a success report without files on disk is refused and the layout stays untouched."""
    rng = np.random.default_rng(6)
    run = _dataset(tmp_path, _complex(rng))

    with pytest.raises(FileNotFoundError, match="missing"):
        PolarimetryPipeline(run, _config(), RecordingLogger(), launcher=SilentWorkerLauncher()).run()

    assert PolarimetricArtifact.ARTIFACT_KEY not in _layout(run)["artifacts"]


def test_pipeline_refuses_an_array_off_the_primary_grid(tmp_path):
    """Checks an array that does not sit on the primary grid is refused and the layout stays untouched."""
    rng = np.random.default_rng(7)
    run = _dataset(tmp_path, _complex(rng))

    with pytest.raises(RuntimeError, match="primary grid"):
        PolarimetryPipeline(run, _config(), RecordingLogger(), launcher=MisalignedWorkerLauncher()).run()

    assert PolarimetricArtifact.ARTIFACT_KEY not in _layout(run)["artifacts"]


def test_launcher_spec_is_json_serialisable_and_names_its_entry(tmp_path):
    """Checks the spec carries the dataset's stack, crop, window and paths and the launcher names its entry script."""
    rng    = np.random.default_rng(8)
    run    = _dataset(tmp_path, _complex(rng))
    record = DatasetRecord.load(run)

    spec = PolarimetricLauncher.build_spec(
        tomogram_config  = record.tomogram_config,
        stack_identifier = record.stack_identifier,
        crop             = record.crop,
        pyrat_directory  = Path("/test/pyrat"),
        pyrat_threads    = 3,
        window           = record.window,
        primary_path     = record.primary_path,
        artifact_path    = record.artifact_path,
        sidecar_path     = record.sidecar_path,
        result_path      = record.result_path,
    )
    decoded = json.loads(json.dumps(spec))

    assert decoded["tomogram_config"]["fusar_project_path"] == "/fsar/project.csv"
    assert decoded["stack_identifier"] == "1"
    assert decoded["crop"] == [0, SHAPE[0], 0, SHAPE[1]]
    assert decoded["window"] == WINDOW
    assert decoded["pyrat_threads"] == 3
    assert decoded["artifact_path"] == str(run / "data" / PolarimetricArtifact.FILENAME)
    assert decoded["sidecar_path"] == str(run / "meta" / PolarimetricArtifact.SIDECAR)
    assert decoded["result_path"] == str(run / "meta" / "polarimetry_result.json")
    assert PolarimetricLauncher.ENTRY == "main/processing/generate_polarimetric_primary.py"
    assert PolarimetricLauncher.child_log(record.spec_path) == run / "meta" / "polarimetric_primary.log"


def test_loader_puts_the_pyrat_checkout_on_the_import_path(tmp_path, monkeypatch):
    """Checks constructing the loader registers the PyRat root before any import of pyrat can happen."""
    monkeypatch.setattr(sys, "path", list(sys.path))
    root = tmp_path / "pyrat_checkout"
    root.mkdir()

    PolarimetricPrimaryLoader(TomogramConfig(), "1", (0, 4, 0, 4), root, 2, RecordingLogger())

    assert str(root) in sys.path


def test_dataset_record_reads_crop_window_and_paths(tmp_path):
    """Checks the record exposes the crop, window, stack and artifact paths of a dataset."""
    rng = np.random.default_rng(9)
    run = _dataset(tmp_path, _complex(rng))

    record = DatasetRecord.load(run)

    assert record.crop == (0, SHAPE[0], 0, SHAPE[1])
    assert record.window == tuple(WINDOW)
    assert record.stack_identifier == "1"
    assert record.present is False
    assert record.primary_path == run / "data" / "primary.npy"
    assert record.artifact_path == run / "data" / PolarimetricArtifact.FILENAME
    assert record.sidecar_path == run / "meta" / PolarimetricArtifact.SIDECAR
    assert record.spec_path == run / "meta" / "polarimetry_spec.json"
