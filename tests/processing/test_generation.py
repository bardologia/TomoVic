"""Tests covering the dataset generation pipeline of the processing stage.

Exercises stack consistency of the generated SAR artifacts, interferogram
formation and clipping, metadata and layout serialisation, the stack plotting
and distribution analysers, and the tomogram tiling/concatenation logic.
"""

from __future__ import annotations

import contextlib
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")

import numpy as np
import pytest

from configuration.sar.processing_config           import ProcessingConfig, PathConfig
from pipelines.processing.generation.plots         import StackPlotter
from pipelines.processing.generation.artifacts     import ArtifactRegistry, MetadataManager
from pipelines.processing.generation.inference     import StackInferencePipeline
from pipelines.processing.generation.distributions import ValueDistribution, StackDistributionAnalyzer
from tools.data.regions                            import CropRegion
from tools.monitoring.logger                       import Logger

from tests.conftest import SilentLogger


CLIP = 1.25


@pytest.fixture(scope="module")
def logger(tmp_path_factory):
    """Yields a module-scoped file Logger writing into a temporary directory."""
    log = Logger(log_dir=str(tmp_path_factory.mktemp("gen_logs")), name="test_gen", level="ERROR")

    yield log

    log.close()


@pytest.fixture
def crop_from_state(config_state_json):
    """Returns the CropRegion recorded in the stored pipeline configuration state."""
    c = config_state_json["crop"]
    return CropRegion(c["azimuth_start"], c["azimuth_end"], c["range_start"], c["range_end"])


@pytest.mark.real_data
def test_shapes_consistent_across_inputs(primary, secondaries, interferograms, dem_full):
    """Verifies primary, secondaries, interferograms and DEM share the azimuth/range grid."""
    Az, R = primary.shape

    assert dem_full.shape       == (Az, R)
    assert secondaries.shape    == (28, Az, R)
    assert interferograms.shape == (28, Az, R)


@pytest.mark.real_data
def test_input_dtypes(primary, secondaries, interferograms, dem_full):
    """Verifies the SLC stacks are complex64 and the DEM is float32."""
    assert primary.dtype        == np.complex64
    assert secondaries.dtype    == np.complex64
    assert interferograms.dtype == np.complex64
    assert dem_full.dtype       == np.float32


@pytest.mark.real_data
def test_interferogram_amplitude_is_clipped_secondary(secondaries, interferograms, small_window):
    """Verifies interferogram amplitude equals the secondary amplitude clipped at CLIP."""
    az, rg = small_window

    for s in range(interferograms.shape[0]):
        ifg_amp = np.abs(np.array(interferograms[s][az, rg]))
        sec_amp = np.abs(np.array(secondaries[s][az, rg]))
        clipped = np.clip(sec_amp, 0.0, CLIP)

        assert np.allclose(ifg_amp, clipped, atol=1e-5)


@pytest.mark.real_data
def test_interferogram_amplitude_never_exceeds_clip(interferograms, small_window):
    """Verifies no interferogram sample exceeds the configured amplitude clip."""
    az, rg = small_window

    for s in range(interferograms.shape[0]):
        amp = np.abs(np.array(interferograms[s][az, rg]))

        assert amp.max() <= CLIP + 1e-5


@pytest.mark.real_data
def test_interferogram_phase_within_pi(interferograms, small_window):
    """Verifies interferogram phase stays inside (-pi, pi] radians."""
    az, rg = small_window
    phase  = np.angle(np.array(interferograms[0][az, rg]))

    assert phase.min() >= -np.pi - 1e-5
    assert phase.max() <=  np.pi + 1e-5


@pytest.mark.real_data
def test_interferogram_phasor_unit_magnitude_where_active(secondaries, interferograms, small_window):
    """Verifies the interferogram carries a unit-magnitude phasor scaled by the clipped secondary amplitude."""
    az, rg  = small_window
    ifg     = np.array(interferograms[0][az, rg])
    sec_amp = np.clip(np.abs(np.array(secondaries[0][az, rg])), 0.0, CLIP)
    active  = sec_amp > 1e-6

    recovered_phasor_mag = np.abs(ifg[active]) / sec_amp[active]

    assert np.allclose(recovered_phasor_mag, 1.0, atol=1e-4)


@pytest.mark.real_data
def test_artifact_filenames_match_dataset_json(dataset_json, crop_from_state, logger):
    """Verifies ArtifactRegistry reproduces the artifact filenames stored in dataset.json."""
    config   = ProcessingConfig(crop=crop_from_state, paths=PathConfig(run_subdirectory="x"))
    registry = ArtifactRegistry(config, logger)

    assert registry.artifact_filenames() == dataset_json["artifacts"]


@pytest.mark.real_data
def test_dataset_layout_roundtrip(tmp_path, dataset_json, crop_from_state, logger):
    """Verifies the saved dataset layout records the crop, dataset type, pass labels and artifacts."""
    paths   = PathConfig(main_directory=tmp_path, run_subdirectory="run")
    config  = ProcessingConfig(crop=crop_from_state, paths=paths)
    manager = MetadataManager(config, logger)

    out_path = manager.save_dataset_layout(pass_labels=dataset_json["pass_labels"], provenance={"git_commit": "abc", "tomogram_stage": {"pyrat_commit": "def"}})
    loaded   = json.loads(out_path.read_text())

    assert loaded["global_crop"]  == list(crop_from_state.as_tuple())
    assert loaded["dataset_type"] == "FSAR"
    assert loaded["pass_labels"]  == dataset_json["pass_labels"]
    assert loaded["artifacts"]    == dataset_json["artifacts"]
    assert loaded["provenance"]   == {"git_commit": "abc", "tomogram_stage": {"pyrat_commit": "def"}}


@pytest.mark.real_data
def test_config_state_roundtrip(tmp_path, crop_from_state, logger):
    """Verifies the dumped pipeline configuration keeps the crop, amplitude clip and dataset type."""
    paths   = PathConfig(main_directory=tmp_path, run_subdirectory="run")
    config  = ProcessingConfig(crop=crop_from_state, paths=paths)
    manager = MetadataManager(config, logger)

    dump_path = manager.save_pipeline_configuration(provenance={"git_commit": "abc", "pyrat_commit": "def"})
    loaded    = json.loads(dump_path.read_text())

    assert loaded["crop"]["azimuth_start"]                 == crop_from_state.azimuth_start
    assert loaded["tomogram_config"]["max_amplitude_clip"] == CLIP
    assert loaded["dataset_type"]                          == "FSAR"
    assert loaded["provenance"]                            == {"git_commit": "abc", "pyrat_commit": "def"}


def test_metadata_manager_provenance_names_the_pyrat_checkout(tmp_path):
    """The run provenance carries this process's commit and libraries plus the PyRAT directory and its revision."""
    paths   = PathConfig(main_directory=tmp_path, pyrat_directory=tmp_path / "pyrat", run_subdirectory="run")
    config  = ProcessingConfig(crop=CropRegion(0, 4, 0, 4), paths=paths)
    manager = MetadataManager(config, SilentLogger())

    provenance = manager.collect_provenance()

    assert {"git_commit", "host", "python", "numpy", "pyrat_directory", "pyrat_commit"} <= set(provenance)
    assert provenance["pyrat_directory"] == str(tmp_path / "pyrat")
    assert provenance["pyrat_commit"]    == f"unavailable (no such directory: {tmp_path / 'pyrat'})"
    assert provenance["numpy"]           == np.__version__


def test_generator_provenance_names_the_interpreter_and_the_pyrat_checkout(tmp_path):
    """A stage generator records the interpreter it runs under, its library versions and the PyRAT revision it imports."""
    import platform
    import sys
    from pipelines.processing.generation.base import GeneratorBase

    provenance = GeneratorBase({"pyrat_directory": str(tmp_path / "nowhere")}, SilentLogger()).provenance()

    assert provenance["executable"]   == sys.executable
    assert provenance["python"]       == platform.python_version()
    assert provenance["numpy"]        == np.__version__
    assert provenance["pyrat_commit"] == f"unavailable (no such directory: {tmp_path / 'nowhere'})"
    assert isinstance(provenance["git_commit"], str)


@pytest.mark.real_data
def test_inputs_metadata_roundtrip(tmp_path, crop_from_state, logger):
    """Verifies stage metadata for the input arrays is written and records their shapes."""
    paths   = PathConfig(main_directory=tmp_path, run_subdirectory="run")
    config  = ProcessingConfig(crop=crop_from_state, paths=paths)
    manager = MetadataManager(config, logger)

    entries = manager.build_inputs_metadata(
        primary_path         = tmp_path / "p.npy",
        secondaries_path     = tmp_path / "s.npy",
        interferograms_path  = tmp_path / "i.npy",
        primary_shape        = (1000, 500),
        secondaries_shape    = (28, 1000, 500),
        interferograms_shape = (28, 1000, 500),
        secondary_amplitude  = {"clip": CLIP, "passes": [{"pass": "PS04", "samples": 500000, "clipped": 94, "zero": 0, "nonfinite": 0}]},
        project_options      = "suffix=_coreg",
        inf_suffix           = "_coreg",
    )
    meta_path = manager.save_stage_metadata("inputs", entries)

    assert meta_path.is_file()
    text = meta_path.read_text()
    assert "primary_shape" in text
    assert "secondary_PS04: clipped 0.0188%, zero 0.0000%, nonfinite 0 of 500000" in text
    assert "inf_suffix: _coreg" in text


@pytest.mark.real_data
def test_stackplotter_smoke(tmp_path, primary, secondaries, interferograms, dem_full, crop_from_state, pass_labels, logger):
    """Verifies StackPlotter writes primary, DEM and per-secondary coherence figures."""
    az, rg = slice(0, 24), slice(0, 24)

    data_dir = tmp_path / "data"
    data_dir.mkdir(parents=True)

    primary_path        = data_dir / "primary.npy"
    secondaries_path    = data_dir / "secondaries.npy"
    interferograms_path = data_dir / "interferograms.npy"
    dem_path            = data_dir / "dem.npy"

    np.save(primary_path,        np.array(primary[az, rg]))
    np.save(secondaries_path,    np.array(secondaries[:3, az, rg]))
    np.save(interferograms_path, np.array(interferograms[:3, az, rg]))
    np.save(dem_path,            np.array(dem_full[az, rg]))

    plotter = StackPlotter(tmp_path / "run", CLIP, logger, fig_dpi=40, save_dpi=40)

    saved = plotter.run(primary_path, secondaries_path, interferograms_path, dem_path, pass_labels=pass_labels[:4])

    assert "primary" in saved
    assert "dem_full" in saved
    assert all(p.is_file() for p in saved.values())

    for index in range(3):
        assert f"coherence_{index:02d}_magnitude" in saved
        assert f"coherence_{index:02d}_phase"     in saved


def test_value_distribution_log_conserves_counts():
    """Verifies log-scaled histograms keep every sample and report consistent statistics."""
    rng    = np.random.default_rng(0)
    values = rng.gamma(shape=1.0, scale=0.1, size=(32, 32)).astype(np.float32)

    result = ValueDistribution(values, scale="log", n_bins=16).compute()

    assert result["histogram"]["scale"] == "log"
    assert len(result["histogram"]["bin_edges"]) == 17
    assert len(result["histogram"]["counts"]) == 16
    assert sum(result["histogram"]["counts"]) == values.size
    assert result["histogram"]["n_excluded"]  == 0
    assert result["statistics"]["count"] == values.size
    assert result["statistics"]["min"] <= result["statistics"]["median"] <= result["statistics"]["max"]


def test_value_distribution_log_counts_the_zero_values_left_out_of_the_bins():
    """A log-scale histogram cannot bin zero amplitudes, so it reports how many finite values the bars leave out."""
    values = np.array([0.0, 0.0, 0.0, 0.1, 0.2, 0.4, np.nan], dtype=np.float32)

    result = ValueDistribution(values, scale="log", n_bins=4).compute()

    assert result["statistics"]["count"]       == 6
    assert result["statistics"]["n_nonfinite"] == 1
    assert result["histogram"]["n_excluded"]   == 3
    assert sum(result["histogram"]["counts"])  == 3


def test_value_distribution_honours_fixed_range_and_nonfinite():
    """Verifies a fixed value range pins the bin edges and non-finite samples are counted apart."""
    values = np.array([-np.pi, 0.0, np.pi / 2, np.nan], dtype=np.float32)
    result = ValueDistribution(values, scale="linear", n_bins=8, value_range=(-np.pi, np.pi)).compute()
    edges  = result["histogram"]["bin_edges"]

    assert result["statistics"]["n_nonfinite"] == 1
    assert result["statistics"]["count"]       == 3
    assert edges[0]  == pytest.approx(-np.pi)
    assert edges[-1] == pytest.approx(np.pi)


def _synthetic_stack(directory, secondary_fill):
    """Saves a 6 x 6 primary, two secondaries, two interferograms and a DEM, and returns their paths.

    Args:
        directory      : Directory receiving the four .npy files.
        secondary_fill : Callable taking the secondary cube of shape (2, 6, 6) and modifying it in place.
    """
    rng         = np.random.default_rng(7)
    primary     = (rng.normal(size=(6, 6)) + 1j * rng.normal(size=(6, 6))).astype(np.complex64)
    secondaries = (rng.normal(size=(2, 6, 6)) + 1j * rng.normal(size=(2, 6, 6))).astype(np.complex64)
    dem         = rng.normal(500.0, 10.0, size=(6, 6)).astype(np.float32)

    secondary_fill(secondaries)

    paths = [directory / name for name in ("primary.npy", "secondaries.npy", "interferograms.npy", "dem.npy")]
    for path, array in zip(paths, (primary, secondaries, secondaries * np.conj(primary), dem)):
        np.save(path, array)

    return paths


def test_stack_distribution_analyzer_tables_nonfinite_and_unbinned_fields(tmp_path):
    """Zero-filled margins and NaN samples are named per field in one table and counted in one warning at the end of the run."""
    def zero_margin_and_nan(secondaries):
        """Zero-fills the first azimuth line of the first secondary and puts one NaN into the second."""
        secondaries[0, 0, :] = 0.0
        secondaries[1, 2, 2] = np.nan

    paths    = _synthetic_stack(tmp_path, zero_margin_and_nan)
    recorder = _LogRecorder()
    analyzer = StackDistributionAnalyzer(tmp_path / "run", CLIP, recorder, n_bins=8, fig_dpi=40, save_dpi=40)

    analyzer.run(*paths, pass_labels=["PS02", "PS04", "PS06"])

    title, rows = recorder.tables[-1]
    by_field    = {row["Field"]: row for row in rows}
    unbinned    = sum(1 for row in rows if row["Not binned"] > 0)

    assert title == "Fields with non-finite or unbinned values"
    assert by_field["Secondary SLC amplitude — PS04"]["Not binned"] == 6
    assert by_field["Interferogram amplitude — PS02 / PS04"]["Not binned"] == 6
    assert by_field["Secondary SLC amplitude — PS06"]["Non-finite"] == 1
    assert "Primary SLC amplitude — PS02" not in by_field
    assert len(recorder.warnings) == 1
    assert recorder.warnings[0].startswith(f"4 of {len(analyzer.coverage)} fields hold non-finite values and {unbinned} histograms leave finite values out of their bins")


def test_stack_distribution_analyzer_is_quiet_for_a_clean_stack(tmp_path):
    """A stack without non-finite or zero samples ends the run with one line and no warning."""
    paths    = _synthetic_stack(tmp_path, lambda secondaries: None)
    recorder = _LogRecorder()
    analyzer = StackDistributionAnalyzer(tmp_path / "run", CLIP, recorder, n_bins=8, fig_dpi=40, save_dpi=40)

    analyzer.run(*paths, pass_labels=["PS02", "PS04", "PS06"])

    assert recorder.warnings    == []
    assert recorder.subsections[-1] == f"All {len(analyzer.coverage)} fields are finite and fully binned"


@pytest.mark.real_data
def test_stack_distribution_analyzer_smoke(tmp_path, primary, secondaries, interferograms, dem_full, pass_labels, logger):
    """Verifies the distribution analyser writes per-pass JSON entries and one PNG per distribution."""
    az, rg = slice(0, 24), slice(0, 24)

    data_dir = tmp_path / "data"
    data_dir.mkdir(parents=True)

    primary_path        = data_dir / "primary.npy"
    secondaries_path    = data_dir / "secondaries.npy"
    interferograms_path = data_dir / "interferograms.npy"
    dem_path            = data_dir / "dem.npy"

    np.save(primary_path,        np.array(primary[az, rg]))
    np.save(secondaries_path,    np.array(secondaries[:3, az, rg]))
    np.save(interferograms_path, np.array(interferograms[:3, az, rg]))
    np.save(dem_path,            np.array(dem_full[az, rg]))

    analyzer = StackDistributionAnalyzer(tmp_path / "run", CLIP, logger, n_bins=32, fig_dpi=40, save_dpi=40)

    saved   = analyzer.run(primary_path, secondaries_path, interferograms_path, dem_path, pass_labels=pass_labels[:4])
    payload = json.loads(saved["value_distributions_json"].read_text())

    assert saved["value_distributions_json"].is_file()
    assert payload["reference_pass"] == pass_labels[0]
    assert payload["interferogram_amplitude_clip"] == CLIP
    assert list(payload["passes"].keys())         == list(pass_labels[:4])
    assert list(payload["interferograms"].keys()) == list(pass_labels[1:4])
    assert set(payload["dem"]["height"].keys())   == {"statistics", "histogram"}

    primary_entry = payload["passes"][pass_labels[0]]
    assert primary_entry["role"] == "primary"
    assert {"amplitude", "phase"} <= set(primary_entry.keys())
    assert primary_entry["phase"]["histogram"]["bin_edges"][0] == pytest.approx(-np.pi)

    pngs = list((tmp_path / "run" / "images" / "distributions").rglob("*.png"))
    assert len(pngs) == 4 * 2 + 3 * 2 + 1
    assert all(p.is_file() for p in pngs)


@pytest.mark.real_data
def test_stack_inference_pipeline_smoke(tmp_path, primary, secondaries, interferograms, dem_full, pass_labels, logger):
    """Verifies the stack inference pipeline reads dataset.json and produces figures."""
    az, rg = slice(0, 24), slice(0, 24)

    run_dir  = tmp_path / "trial"
    data_dir = run_dir / "data"
    data_dir.mkdir(parents=True)

    np.save(data_dir / "primary.npy",        np.array(primary[az, rg]))
    np.save(data_dir / "secondaries.npy",    np.array(secondaries[:3, az, rg]))
    np.save(data_dir / "interferograms.npy", np.array(interferograms[:3, az, rg]))
    np.save(data_dir / "dem_full.npy",       np.array(dem_full[az, rg]))

    layout = {
        "max_amplitude_clip" : CLIP,
        "pass_labels"        : pass_labels[:4],
        "artifacts"          : {
            "tomogram_full"  : "tomogram_full.npy",
            "dem_full"       : "dem_full.npy",
            "primary"        : "primary.npy",
            "secondaries"    : "secondaries.npy",
            "interferograms" : "interferograms.npy",
            "track_profiles" : "track_profiles.npz",
        },
    }
    (data_dir / "dataset.json").write_text(json.dumps(layout))

    outputs = StackInferencePipeline(run_dir, logger).run()

    assert (run_dir / "images").is_dir()
    assert outputs["figures"] > 0


def _fail_like_pyrat(job):
    """Worker that dies inside a spawned process the way a PyRAT job does.

    Raises:
        np.linalg.LinAlgError : Always, naming the job.
    """
    raise np.linalg.LinAlgError(f"Singular matrix in subsection {job}")


def test_failed_pool_job_leaves_the_remote_traceback_in_the_stage_log(tmp_path):
    """A PyRAT job that dies in its worker process leaves the worker's frames, not just the message, in the stage log file."""
    from tools.orchestration.pool import ProcessPoolRunner

    with pytest.raises(np.linalg.LinAlgError):
        with Logger(log_dir=str(tmp_path), name="tomogram", level="INFO") as logger:
            ProcessPoolRunner(logger=logger, max_workers=1).run(["0016"], _fail_like_pyrat, lambda job: f"PyRat subsection {job}")

    log_text = (tmp_path / "tomogram.log").read_text()

    assert "Job PyRat subsection 0016 failed" in log_text
    assert "ABORTED tomogram" in log_text
    assert "_fail_like_pyrat" in log_text
    assert "LinAlgError: Singular matrix in subsection 0016" in log_text


def _write_tomo_partial(directory, suffix: str, dem_chunk: np.ndarray, tomogram_chunk: np.ndarray) -> None:
    """Writes one partial tomogram HDF5 chunk with DEM and tomogram datasets.

    Args:
        directory      : Destination directory for the partial file.
        suffix         : Zero-padded index used in the partial filename.
        dem_chunk      : DEM slab of shape (azimuth_chunk, range).
        tomogram_chunk : Complex tomogram slab of shape (height, azimuth_chunk, range).
    """
    import h5py

    directory.mkdir(parents=True, exist_ok=True)

    with h5py.File(str(directory / f"partial_{suffix}.h5"), "w") as handle:
        handle.create_dataset("DEM",      data=dem_chunk)
        handle.create_dataset("tomogram", data=tomogram_chunk)


class _CleanupRecorder(SilentLogger):
    """Silent logger that records error and subsection messages for assertions.

    Attributes:
        errors      : Messages passed to error().
        subsections : Messages passed to subsection().
    """

    def __init__(self):
        """Initialises the empty message buffers."""
        self.errors      = []
        self.subsections = []

    def error(self, message):
        """Records an error message."""
        self.errors.append(message)

    def subsection(self, message):
        """Records a subsection message."""
        self.subsections.append(message)


def _cleanup_processor(tmp_path):
    """Returns a TomogramProcessor on a 4x4 crop together with its recording logger."""
    from pipelines.processing.generation.tomogram import TomogramProcessor

    config   = ProcessingConfig(crop=CropRegion(0, 4, 0, 4), paths=PathConfig(main_directory=tmp_path, run_subdirectory="run"))
    recorder = _CleanupRecorder()

    return TomogramProcessor(config, recorder), recorder


def test_temp_cleanup_reports_a_failed_removal(tmp_path, monkeypatch):
    """Verifies a failed temporary-directory removal is reported as an error and not announced as cleaned."""
    from pipelines.processing.generation import tomogram as tomogram_module

    def refuse(path):
        """Raises OSError to simulate an undeletable temporary directory."""
        raise OSError("device or resource busy")

    processor, recorder = _cleanup_processor(tmp_path)
    temporary_directory = tmp_path / "tomo_stuck"
    temporary_directory.mkdir()

    monkeypatch.setattr(tomogram_module.shutil, "rmtree", refuse)
    processor._cleanup_temp(temporary_directory)

    assert any("NOT removed" in message for message in recorder.errors)
    assert not any("cleaned up" in message for message in recorder.subsections)


def test_temp_cleanup_announces_only_a_real_removal(tmp_path):
    """Verifies a successful removal deletes the tree and logs a cleanup subsection without errors."""
    processor, recorder = _cleanup_processor(tmp_path)
    temporary_directory = tmp_path / "tomo_gone"
    (temporary_directory / "nested").mkdir(parents=True)

    processor._cleanup_temp(temporary_directory)

    assert not temporary_directory.exists()
    assert recorder.errors == []
    assert any("cleaned up" in message for message in recorder.subsections)


def test_tomogram_concatenate_roundtrip(tmp_path, logger):
    """Verifies azimuth tiling plus concatenation reassembles the exact DEM and tomogram."""
    from pipelines.processing.generation.tomogram import TomogramProcessor

    rng      = np.random.default_rng(0)
    dem      = rng.normal(size=(30, 8)).astype(np.float32)
    tomogram = (rng.normal(size=(5, 30, 8)) + 1j * rng.normal(size=(5, 30, 8))).astype(np.complex64)

    crop      = CropRegion(0, 30, 0, 8)
    config    = ProcessingConfig(crop=crop, paths=PathConfig(main_directory=tmp_path, run_subdirectory="run"))
    processor = TomogramProcessor(config, logger)

    config.tomogram_config.max_crop_azimuth_width = 12
    subsections = processor._divide_crop(config.tomogram_config)

    assert [s[:2] for s in subsections] == [(0, 12), (12, 24), (24, 30)]

    partials_dir = tmp_path / "tomo_tmp" / "TOMO" / "TOMO-SR"

    for index, (azimuth_start, azimuth_end, _, _) in enumerate(subsections):
        _write_tomo_partial(partials_dir, f"{index:04d}", dem[azimuth_start:azimuth_end], tomogram[:, azimuth_start:azimuth_end])

    combined_dem, combined_tomogram, content = processor._concatenate(tmp_path / "tomo_tmp", subsections)

    np.testing.assert_array_equal(combined_dem,      dem)
    np.testing.assert_array_equal(combined_tomogram, tomogram)

    assert content["tomogram_shape"] == [5, 30, 8]
    assert content["dem_shape"]      == [30, 8]
    assert content["zero_profiles"]  == 0
    assert content["valid_azimuth"]  == [0, 30]
    assert content["valid_range"]    == [0, 8]


def _margin_content():
    """Returns the content summary of a 10 x 6 crop with zero-filled margins, one NaN voxel and one NaN DEM pixel, fed as two strips."""
    from pipelines.processing.generation.tomogram import TomogramContentAudit

    tomogram = np.ones((3, 10, 6), dtype=np.complex64)
    dem      = np.arange(60, dtype=np.float32).reshape(10, 6)

    tomogram[:, :2, :] = 0.0
    tomogram[:, :, 5]  = 0.0
    tomogram[1, 4, 2]  = np.nan
    dem[7, 3]          = np.nan

    audit = TomogramContentAudit(CropRegion(100, 110, 50, 56))
    audit.add_strip(0, dem[:6], tomogram[:, :6])
    audit.add_strip(6, dem[6:], tomogram[:, 6:])

    return {**audit.summary(), "tomogram_shape": [3, 10, 6], "dem_shape": [10, 6]}


def test_content_audit_counts_margins_nonfinite_and_the_valid_extent():
    """Zero-filled lines and samples, a NaN voxel and a NaN DEM pixel are counted and located in scene coordinates."""
    content = _margin_content()

    assert content["voxels"]                     == 180
    assert content["profiles"]                   == 60
    assert content["zero_profiles"]              == 20
    assert content["zero_profile_fraction"]      == pytest.approx(20 / 60)
    assert content["nonfinite_voxels"]           == 1
    assert content["dem_nonfinite_pixels"]       == 1
    assert content["dem_min_m"]                  == 0.0
    assert content["dem_max_m"]                  == 59.0
    assert content["valid_azimuth"]              == [102, 110]
    assert content["valid_range"]                == [50, 55]
    assert content["zero_profile_azimuth_runs"]  == [[100, 110]]
    assert content["nonfinite_azimuth_runs"]     == [[104, 105]]
    assert content["dem_nonfinite_azimuth_runs"] == [[107, 108]]


def test_content_audit_warns_about_every_anomaly_and_describes_them():
    """The summary table is printed, one warning names each non-zero count with its azimuth lines, and the text entries read back the counts."""
    from pipelines.processing.generation.tomogram import TomogramContentAudit

    content  = _margin_content()
    recorder = _LogRecorder()

    TomogramContentAudit.log_summary(content, recorder)

    assert recorder.kv_tables[0][0] == "Tomogram content"
    assert recorder.kv_tables[0][1]["Valid azimuth"] == "[102, 110)"
    assert len(recorder.warnings) == 3
    assert "1 non-finite voxels on azimuth lines [104, 105)" in recorder.warnings[0]
    assert "20 all-zero profiles (33.333%) on azimuth lines [100, 110)" in recorder.warnings[1]
    assert "valid profiles span azimuth [102, 110) x range [50, 55)" in recorder.warnings[1]
    assert "DEM holds 1 non-finite pixels on azimuth lines [107, 108)" in recorder.warnings[2]

    described = TomogramContentAudit.describe(content)

    assert described["zero_profiles"]  == "20 of 60 (33.333%)"
    assert described["valid_range"]    == "[50, 55)"
    assert described["dem_range_m"]    == "[0.0, 59.0]"
    assert described["tomogram_shape"] == "[3, 10, 6]"


def test_content_audit_is_quiet_for_a_full_cube():
    """A cube without empty or non-finite content prints the table and no warning."""
    from pipelines.processing.generation.tomogram import TomogramContentAudit

    audit = TomogramContentAudit(CropRegion(0, 4, 0, 4))
    audit.add_strip(0, np.zeros((4, 4), np.float32), np.ones((2, 4, 4), np.complex64))

    recorder = _LogRecorder()
    TomogramContentAudit.log_summary({**audit.summary(), "tomogram_shape": [2, 4, 4], "dem_shape": [4, 4]}, recorder)

    assert recorder.warnings == []
    assert recorder.kv_tables[0][1]["All-zero profiles"] == "0 (0.000%)"


def _strip_partials(tmp_path, processor, config, dem, tomogram):
    """Writes one HDF5 partial per azimuth strip of the processor's crop and returns the strips and the scratch root."""
    subsections  = processor._divide_crop(config.tomogram_config)
    partials_dir = tmp_path / "tomo_tmp" / "TOMO" / "TOMO-SR"

    for index, (azimuth_start, azimuth_end, _, _) in enumerate(subsections):
        local = slice(azimuth_start - config.crop.azimuth_start, azimuth_end - config.crop.azimuth_start)
        _write_tomo_partial(partials_dir, f"{index:04d}", dem[local], tomogram[:, local])

    return subsections, tmp_path / "tomo_tmp"


def test_concatenate_reports_allocation_and_per_strip_progress(tmp_path):
    """The merge announces the planned allocation and one line per partial with the azimuth lines it fills."""
    from pipelines.processing.generation.tomogram import TomogramProcessor

    rng      = np.random.default_rng(2)
    dem      = rng.normal(size=(30, 8)).astype(np.float32)
    tomogram = (rng.normal(size=(5, 30, 8)) + 1j * rng.normal(size=(5, 30, 8))).astype(np.complex64)

    config    = ProcessingConfig(crop=CropRegion(100, 130, 0, 8), paths=PathConfig(main_directory=tmp_path, run_subdirectory="run"))
    recorder  = _LogRecorder()
    processor = TomogramProcessor(config, recorder)

    config.tomogram_config.max_crop_azimuth_width = 12
    subsections, scratch = _strip_partials(tmp_path, processor, config, dem, tomogram)

    processor._concatenate(scratch, subsections)

    allocation = [line for line in recorder.subsections if "Allocating" in line]
    progress   = [line for line in recorder.subsections if "] 1/3 " in line or "] 2/3 " in line or "] 3/3 " in line]

    assert len(allocation) == 1
    assert f"{(tomogram.nbytes + dem.nbytes) / 1e9:.2f} GB" in allocation[0]
    assert "(5, 30, 8) complex64" in allocation[0]
    assert [line.split("-> ")[1] for line in progress] == ["azimuth [100, 112)", "azimuth [112, 124)", "azimuth [124, 130)"]


def test_tomogram_run_times_the_merge_and_the_save(tmp_path, monkeypatch):
    """TomogramProcessor.run wraps the merge and the .npy writes in timers and reports the written sizes."""
    from pipelines.processing.generation.tomogram import TomogramProcessor

    rng      = np.random.default_rng(3)
    dem      = rng.normal(size=(30, 8)).astype(np.float32)
    tomogram = (rng.normal(size=(5, 30, 8)) + 1j * rng.normal(size=(5, 30, 8))).astype(np.complex64)

    config    = ProcessingConfig(crop=CropRegion(0, 30, 0, 8), paths=PathConfig(main_directory=tmp_path, run_subdirectory="run"))
    recorder  = _LogRecorder()
    processor = TomogramProcessor(config, recorder)

    config.tomogram_config.max_crop_azimuth_width = 12

    def write_partials(subsections, stack_identifier, tomogram_config, temporary_directory):
        """Stands in for the PyRAT pool by writing the partials the workers would have produced."""
        partials_dir = temporary_directory / "TOMO" / "TOMO-SR"
        for index, (azimuth_start, azimuth_end, _, _) in enumerate(subsections):
            _write_tomo_partial(partials_dir, f"{index:04d}", dem[azimuth_start:azimuth_end], tomogram[:, azimuth_start:azimuth_end])

    monkeypatch.setattr(processor, "_dispatch_workers", write_partials)

    tomogram_path = tmp_path / "run" / "data" / "tomogram_full.npy"
    dem_path      = tmp_path / "run" / "data" / "dem_full.npy"

    processor.run(tomogram_path, dem_path, "1", config.tomogram_config)

    np.testing.assert_array_equal(np.load(tomogram_path), tomogram)
    assert recorder.timers == ["Concatenation", "Saving tomogram and DEM"]
    assert any("Tomogram saved" in line and "GB" in line for line in recorder.subsections)


def test_interferogram_run_times_the_stack_save(tmp_path, monkeypatch):
    """InterferogramProcessor.run wraps the three .npy writes in one timer and reports their sizes."""
    import sys
    from pipelines.processing.generation.interferogram import InterferogramProcessor

    monkeypatch.setattr(sys, "path", list(sys.path))

    config    = ProcessingConfig(crop=CropRegion(0, 4, 0, 4), paths=PathConfig(main_directory=tmp_path, run_subdirectory="run"))
    recorder  = _LogRecorder()
    processor = InterferogramProcessor(config, recorder)

    primary        = np.ones((4, 4), dtype=np.complex64)
    secondaries    = np.ones((2, 4, 4), dtype=np.complex64)
    interferograms = np.ones((2, 4, 4), dtype=np.complex64)

    monkeypatch.setattr(processor, "build", lambda crop_tuple: (primary, secondaries, interferograms))

    shapes = processor.run((0, 4, 0, 4), tmp_path / "p.npy", tmp_path / "s.npy", tmp_path / "i.npy")

    assert shapes == ((4, 4), (2, 4, 4), (2, 4, 4))
    assert recorder.timers == ["Saving interferometric stack"]
    assert any("Interferograms saved" in line and "GB" in line for line in recorder.subsections)


def test_secondary_amplitude_audit_counts_clipped_zero_and_nonfinite_samples():
    """The audit counts, per pass, the samples above the absolute ceiling, the zero samples and the non-finite samples."""
    from pipelines.processing.generation.interferogram import SecondaryAmplitudeAudit

    audit = SecondaryAmplitudeAudit(clip=1.0)
    audit.add_pass("PS04", np.array([[0.0, 0.5, 2.0], [np.nan, np.inf, 1.0]], dtype=np.float32))
    audit.add_pass("PS06", np.full((2, 3), 0.5, dtype=np.float32))

    summary = audit.summary()

    assert summary["clip"]   == 1.0
    assert summary["passes"] == [
        {"pass": "PS04", "samples": 6, "clipped": 2, "zero": 1, "nonfinite": 2},
        {"pass": "PS06", "samples": 6, "clipped": 0, "zero": 0, "nonfinite": 0},
    ]


def test_secondary_amplitude_audit_tables_every_pass_and_warns_about_saturation_and_nonfinite():
    """The summary prints one row per pass under the ceiling's title and warns only for a pass clipped above 1% or holding non-finite samples."""
    from pipelines.processing.generation.interferogram import SecondaryAmplitudeAudit

    content = {"clip": 1.25, "passes": [
        {"pass": "PS04", "samples": 10000, "clipped": 2,   "zero": 50, "nonfinite": 0},
        {"pass": "PS06", "samples": 10000, "clipped": 300, "zero": 0,  "nonfinite": 0},
        {"pass": "PS08", "samples": 10000, "clipped": 0,   "zero": 0,  "nonfinite": 7},
    ]}
    recorder = _LogRecorder()

    SecondaryAmplitudeAudit.log_summary(content, recorder)

    title, rows = recorder.tables[-1]

    assert title == "Secondary amplitude (clip 1.25)"
    assert [(row["Pass"], row["Clipped %"], row["Zero %"], row["Non-finite"]) for row in rows] == [("PS04", "0.0200", "0.5000", 0), ("PS06", "3.0000", "0.0000", 0), ("PS08", "0.0000", "0.0000", 7)]
    assert len(recorder.warnings) == 2
    assert "PS06: 3.00% of its amplitude samples exceed the ceiling 1.25" in recorder.warnings[0]
    assert "PS08: 7 of 10000 samples are non-finite" in recorder.warnings[1]


def _fake_pyrat(slcs, loads):
    """Returns a stand-in for the pyrat module whose loaders serve fixed SLCs and a zero DEM phase.

    Args:
        slcs  : Mapping from pass directory to its complex SLC of shape (azimuth, range).
        loads : List receiving one (loader, pass directory, suffix) tuple per load call.
    """
    import types
    from types import SimpleNamespace

    def fsar(path, product, polarisations, bands, crop, sym, suffix=None):
        """Records the load and returns the pass's SLC."""
        loads.append(("fsar", path, suffix))
        return slcs[path]

    def fsar_phadem(path, bands, crop, suffix):
        """Records the load and returns a zero DEM phase."""
        loads.append(("fsar_phadem", path, suffix))
        return np.zeros(slcs[path].shape, dtype=np.float32)

    module         = types.ModuleType("pyrat")
    module.getdata = lambda data: data
    module.load    = SimpleNamespace(fsar=fsar, fsar_phadem=fsar_phadem)

    return module


def _fake_tomography(options):
    """Returns a stand-in for a PyRat FuSARtomo object with one primary and two secondaries over a 2 x 3 crop.

    Args:
        options : Raw Options string of the F-SAR project row.
    """
    from types import SimpleNamespace

    slcs = {
        "/campaign/PS02" : np.ones((2, 3), dtype=np.complex64),
        "/campaign/PS04" : np.array([[0.0, 0.5, 2.0], [1.0, 3.0, 0.5]], dtype=np.complex64),
        "/campaign/PS06" : np.full((2, 3), 0.5, dtype=np.complex64),
    }
    tomography = SimpleNamespace(project={"options": options}, master="/campaign/PS02", slaves=["/campaign/PS04", "/campaign/PS06"], polarisation="hv", band="L", crop=[0, 2, 0, 3])

    return tomography, slcs


def test_compute_interferograms_audits_every_secondary_amplitude(tmp_path, monkeypatch):
    """Forming the interferograms keeps the per-pass amplitude audit under the pass labels and clips the interferogram amplitude at the ceiling."""
    import sys
    from pipelines.processing.generation.interferogram import InterferogramProcessor

    monkeypatch.setattr(sys, "path", list(sys.path))

    tomography, slcs = _fake_tomography("")
    monkeypatch.setitem(sys.modules, "pyrat", _fake_pyrat(slcs, []))

    config    = ProcessingConfig(crop=CropRegion(0, 2, 0, 3), paths=PathConfig(main_directory=tmp_path, run_subdirectory="run"))
    recorder  = _LogRecorder()
    processor = InterferogramProcessor(config, recorder)

    config.tomogram_config.max_amplitude_clip = 1.0
    primary, secondaries, interferograms = processor._compute_interferograms(tomography, ["PS04", "PS06"])

    assert processor.secondary_amplitude == {"clip": 1.0, "passes": [
        {"pass": "PS04", "samples": 6, "clipped": 2, "zero": 1, "nonfinite": 0},
        {"pass": "PS06", "samples": 6, "clipped": 0, "zero": 0, "nonfinite": 0},
    ]}
    assert float(np.abs(interferograms).max()) <= 1.0 + 1e-6
    assert recorder.tables[-1][0] == "Secondary amplitude (clip 1)"
    assert any("PS04: 33.33%" in warning for warning in recorder.warnings)


def test_compute_interferograms_logs_and_keeps_the_inf_suffix(tmp_path, monkeypatch):
    """The project row's options and the INF suffix they name are logged, kept for the stage result and passed to every INF load."""
    import sys
    from pipelines.processing.generation.interferogram import InterferogramProcessor

    monkeypatch.setattr(sys, "path", list(sys.path))

    loads            = []
    tomography, slcs = _fake_tomography("suffix=_coreg, nodem")
    monkeypatch.setitem(sys.modules, "pyrat", _fake_pyrat(slcs, loads))

    config    = ProcessingConfig(crop=CropRegion(0, 2, 0, 3), paths=PathConfig(main_directory=tmp_path, run_subdirectory="run"))
    recorder  = _LogRecorder()
    processor = InterferogramProcessor(config, recorder)

    processor._compute_interferograms(tomography, ["PS04", "PS06"])

    project_row = dict(recorder.kv_tables)["FSAR project row"]

    assert processor.project_options == "suffix=_coreg, nodem"
    assert processor.inf_suffix      == "_coreg"
    assert project_row["INF suffix"] == "_coreg"
    assert project_row["Bands"]      == "L"
    assert {suffix for loader, path, suffix in loads if path != "/campaign/PS02"} == {"_coreg"}


def test_compute_interferograms_names_a_missing_inf_suffix(tmp_path, monkeypatch):
    """A project row without a suffix option is logged as such and leaves an empty suffix for the stage result."""
    import sys
    from pipelines.processing.generation.interferogram import InterferogramProcessor

    monkeypatch.setattr(sys, "path", list(sys.path))

    tomography, slcs = _fake_tomography("")
    monkeypatch.setitem(sys.modules, "pyrat", _fake_pyrat(slcs, []))

    config    = ProcessingConfig(crop=CropRegion(0, 2, 0, 3), paths=PathConfig(main_directory=tmp_path, run_subdirectory="run"))
    recorder  = _LogRecorder()
    processor = InterferogramProcessor(config, recorder)

    processor._compute_interferograms(tomography, ["PS04", "PS06"])

    project_row = dict(recorder.kv_tables)["FSAR project row"]

    assert processor.inf_suffix      == ""
    assert project_row["Options"]    == "(empty)"
    assert project_row["INF suffix"].startswith("(none")


def test_divide_crop_tables_the_subsection_azimuth_ranges(tmp_path):
    """The subsection table lists every strip with its azimuth bounds in scene coordinates."""
    from pipelines.processing.generation.tomogram import TomogramProcessor

    config    = ProcessingConfig(crop=CropRegion(100, 130, 0, 8), paths=PathConfig(main_directory=tmp_path, run_subdirectory="run"))
    recorder  = _LogRecorder()
    processor = TomogramProcessor(config, recorder)

    config.tomogram_config.max_crop_azimuth_width = 12
    processor._divide_crop(config.tomogram_config)

    title, rows = recorder.tables[-1]

    assert title == "Tomogram subsections"
    assert [(row["Section"], row["Azimuth start"], row["Azimuth end"]) for row in rows] == [("0000", 100, 112), ("0001", 112, 124), ("0002", 124, 130)]


def test_job_label_names_the_azimuth_lines():
    """A subsection job is labelled with its suffix and the azimuth lines it covers, so completion and failure lines carry both."""
    from pipelines.processing.generation.tomogram import TomogramProcessor
    from tools.sar.tomogram_worker                 import PyRatJob

    job = PyRatJob(
        pyrat_root_path       = "/pyrat",
        crop_tuple            = (16000, 17000, 500, 4000),
        suffix                = "0016",
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

    assert TomogramProcessor._job_label(job) == "PyRat subsection 0016 az[16000, 17000)"


def test_tomogram_concatenate_rejects_missing_partial(tmp_path, logger):
    """Verifies concatenation raises when a partial tomogram artifact is absent."""
    from pipelines.processing.generation.tomogram import TomogramProcessor

    rng      = np.random.default_rng(1)
    dem      = rng.normal(size=(30, 8)).astype(np.float32)
    tomogram = (rng.normal(size=(5, 30, 8)) + 1j * rng.normal(size=(5, 30, 8))).astype(np.complex64)

    crop      = CropRegion(0, 30, 0, 8)
    config    = ProcessingConfig(crop=crop, paths=PathConfig(main_directory=tmp_path, run_subdirectory="run"))
    processor = TomogramProcessor(config, logger)

    config.tomogram_config.max_crop_azimuth_width = 12
    subsections = processor._divide_crop(config.tomogram_config)

    partials_dir = tmp_path / "tomo_tmp" / "TOMO" / "TOMO-SR"

    for index, (azimuth_start, azimuth_end, _, _) in enumerate(subsections[:-1]):
        _write_tomo_partial(partials_dir, f"{index:04d}", dem[azimuth_start:azimuth_end], tomogram[:, azimuth_start:azimuth_end])

    with pytest.raises(RuntimeError, match="artifacts"):
        processor._concatenate(tmp_path / "tomo_tmp", subsections)


def test_session_persists_the_entry_config(tmp_path, monkeypatch):
    """A preprocessing session writes the resolved entry config into the dataset's docs."""
    from configuration.sar.processing_config     import PreProcessEntryConfig
    from pipelines.processing.generation         import pipeline as pipeline_module
    from tools.runtime.config_cli                import ConfigCli
    from types                                   import SimpleNamespace

    class _StubPipeline:
        """Processing pipeline stand-in that produces no artifacts."""

        def __init__(self, config, logger=None):
            """Ignores the configuration and logger."""
            pass

        def run(self):
            """Returns an empty artifact mapping."""
            return {}

    monkeypatch.setattr(pipeline_module, "ProcessingPipeline", _StubPipeline)

    entry               = PreProcessEntryConfig()
    entry.azimuth_start = 123

    config  = SimpleNamespace(paths=SimpleNamespace(run_directory=tmp_path / "ds"))
    session = pipeline_module.PreProcessSession(index=0, total=1, dataset_name="ds", config=config, entry_config=entry)

    assert session.execute() == {}

    loaded = ConfigCli.load_resolved(PreProcessEntryConfig(), tmp_path / "ds" / "docs" / "resolved_entry_config.json")
    assert loaded.azimuth_start == 123


def test_session_writes_no_entry_config_when_the_pipeline_fails(tmp_path, monkeypatch):
    """A crashed preprocessing run leaves no copyable config behind.

    Parameter extraction and external injection both persist the entry config
    only after their outputs exist; generation follows the same ordering, so the
    launch console never offers to copy from a run that never finished.
    """
    from configuration.sar.processing_config     import PreProcessEntryConfig
    from pipelines.processing.generation         import pipeline as pipeline_module
    from types                                   import SimpleNamespace

    class _FailingPipeline:
        """Processing pipeline stand-in that fails partway through."""

        def __init__(self, config, logger=None):
            """Ignores the configuration and logger."""
            pass

        def run(self):
            """Fails the way a broken preprocessing run does.

            Raises:
                RuntimeError : Always.
            """
            raise RuntimeError("beamforming failed")

    monkeypatch.setattr(pipeline_module, "ProcessingPipeline", _FailingPipeline)

    config  = SimpleNamespace(paths=SimpleNamespace(run_directory=tmp_path / "ds"))
    session = pipeline_module.PreProcessSession(index=0, total=1, dataset_name="ds", config=config, entry_config=PreProcessEntryConfig())

    with pytest.raises(RuntimeError, match="beamforming failed"):
        session.execute()

    assert not (tmp_path / "ds" / "docs" / "resolved_entry_config.json").exists()

    log_text = (tmp_path / "ds" / "logs" / "preprocessing.log").read_text()

    assert "ABORTED preprocessing" in log_text
    assert "RuntimeError: beamforming failed" in log_text
    assert "Traceback (most recent call last)" in log_text
    assert "END preprocessing" not in log_text


def test_inference_session_log_records_the_failure(tmp_path, monkeypatch):
    """A failed analysis ends the dataset's preprocessing_inference.log with the ABORTED banner and the traceback."""
    from pipelines.processing.generation import inference as inference_module

    class _FailingPipeline:
        """Stack inference pipeline stand-in that fails on an all-zero field."""

        def __init__(self, run_dir, logger=None):
            """Ignores the run directory and logger."""
            pass

        def run(self):
            """Fails the way the log-scale histogram does on an all-zero secondary.

            Raises:
                ValueError : Always.
            """
            raise ValueError("log-scale histogram requires strictly positive values")

    monkeypatch.setattr(inference_module, "StackInferencePipeline", _FailingPipeline)

    with pytest.raises(ValueError, match="strictly positive"):
        inference_module.StackInferenceSession(tmp_path / "trial").execute()

    log_text = (tmp_path / "trial" / "logs" / "preprocessing_inference.log").read_text()

    assert "ABORTED preprocessing_inference" in log_text
    assert "ValueError: log-scale histogram requires strictly positive values" in log_text
    assert "Traceback (most recent call last)" in log_text


def test_trial_discovery_names_and_counts_directories_without_a_dataset_layout(tmp_path):
    """Auto-discovery keeps only directories with data/dataset.json and warns about every other directory, naming it."""
    from pipelines.processing.generation.inference import StackInferenceTrialCollector

    (tmp_path / "finished" / "data").mkdir(parents=True)
    (tmp_path / "finished" / "data" / "dataset.json").write_text("{}")
    (tmp_path / "failed" / "logs").mkdir(parents=True)
    (tmp_path / "running").mkdir()
    (tmp_path / "notes.txt").write_text("")

    recorder  = _LogRecorder()
    collector = StackInferenceTrialCollector(tmp_path, [], recorder)

    assert collector.collect() == [tmp_path / "finished"]
    assert collector.skipped   == ["failed", "running"]
    assert recorder.warnings   == [f"Skipped 2 directories under {tmp_path} without data/dataset.json (preprocessing failed or still running): failed, running"]


def test_trial_discovery_shortens_a_long_skipped_list(tmp_path):
    """More skipped directories than the named limit are summarised with a count of the rest."""
    from pipelines.processing.generation.inference import StackInferenceTrialCollector

    for index in range(StackInferenceTrialCollector.MAX_SKIPPED_NAMED + 3):
        (tmp_path / f"run{index:02d}").mkdir()

    recorder = _LogRecorder()
    StackInferenceTrialCollector(tmp_path, [], recorder).collect()

    assert recorder.warnings[0].endswith("run09 and 3 more")
    assert recorder.errors == [f"No preprocessing trials found under {tmp_path}"]


class _KvRecorder(SilentLogger):
    """Silent logger that records every kv_table mapping for assertions.

    Attributes:
        tables : Mappings passed to kv_table(), in call order.
    """

    def __init__(self):
        """Initialises the empty table buffer."""
        self.tables = []

    def kv_table(self, data, *args, **kwargs):
        """Records one kv_table mapping."""
        self.tables.append(dict(data))


class _LogRecorder(SilentLogger):
    """Silent logger that records warnings, errors, subsections, tables and timer labels.

    Attributes:
        warnings    : Messages passed to warning().
        errors      : Messages passed to error().
        subsections : Messages passed to subsection().
        kv_tables   : (title, mapping) pairs passed to kv_table().
        tables      : (title, rows) pairs passed to metrics_table().
        timers      : Labels of the timer() blocks opened.
    """

    def __init__(self):
        """Initialises the empty buffers."""
        self.warnings    = []
        self.errors      = []
        self.subsections = []
        self.kv_tables   = []
        self.tables      = []
        self.timers      = []

    def warning(self, message):
        """Records a warning."""
        self.warnings.append(message)

    def error(self, message):
        """Records an error."""
        self.errors.append(message)

    def subsection(self, message):
        """Records a subsection heading."""
        self.subsections.append(message)

    def kv_table(self, data, title=None, **kwargs):
        """Records a key-value table with its title."""
        self.kv_tables.append((title, dict(data)))

    def metrics_table(self, rows, columns=None, title=None, **kwargs):
        """Records a metrics table with its title."""
        self.tables.append((title, [dict(row) for row in rows]))

    @contextlib.contextmanager
    def timer(self, label):
        """Records the timer label and yields."""
        self.timers.append(label)
        yield


def _finished_dataset_dir(tmp_path, marker):
    """Returns a dataset directory carrying one finished-dataset marker, a relative file path or a params/<run> directory."""
    run_dir = tmp_path / "ds"
    target  = run_dir / marker

    if marker.startswith("params/"):
        target.mkdir(parents=True)
    else:
        target.parent.mkdir(parents=True)
        target.write_text("{}")

    return run_dir


@pytest.mark.parametrize("marker", ("data/dataset.json", "docs/resolved_entry_config.json", "params/params_k5_lam0.01_sig4_sigma"))
def test_directory_guard_refuses_a_finished_dataset(tmp_path, marker):
    """A dataset layout, a resolved entry config or a parameter run makes the guard refuse the directory, naming what it holds."""
    from pipelines.processing.generation.artifacts import DatasetDirectoryGuard

    run_dir  = _finished_dataset_dir(tmp_path, marker)
    recorder = _LogRecorder()

    with pytest.raises(FileExistsError, match=marker.replace(".", r"\.")):
        DatasetDirectoryGuard(run_dir).check(recorder)

    assert recorder.warnings == []


def test_directory_guard_warns_about_an_unfinished_leftover(tmp_path):
    """A directory without finished-dataset markers is accepted with a warning naming its contents."""
    from pipelines.processing.generation.artifacts import DatasetDirectoryGuard

    run_dir = tmp_path / "ds"
    (run_dir / "logs").mkdir(parents=True)
    (run_dir / "meta").mkdir()
    (run_dir / "meta" / "config_state.json").write_text("{}")

    recorder = _LogRecorder()
    DatasetDirectoryGuard(run_dir).check(recorder)

    assert len(recorder.warnings) == 1
    assert "['logs', 'meta']" in recorder.warnings[0]


def test_directory_guard_is_silent_for_a_new_directory(tmp_path):
    """A directory that does not exist yet passes without a warning."""
    from pipelines.processing.generation.artifacts import DatasetDirectoryGuard

    recorder = _LogRecorder()
    DatasetDirectoryGuard(tmp_path / "ds").check(recorder)

    assert recorder.warnings == []


def test_session_refuses_a_finished_dataset_directory(tmp_path, monkeypatch):
    """A relaunch into a directory holding data/dataset.json fails before the pipeline is built."""
    from pipelines.processing.generation import pipeline as pipeline_module
    from types                           import SimpleNamespace

    built = []

    class _CountingPipeline:
        """Processing pipeline stand-in that records its construction."""

        def __init__(self, config, logger=None):
            """Records that the pipeline was built."""
            built.append(config)

        def run(self):
            """Returns an empty artifact mapping."""
            return {}

    monkeypatch.setattr(pipeline_module, "ProcessingPipeline", _CountingPipeline)

    run_dir = _finished_dataset_dir(tmp_path, "data/dataset.json")
    config  = SimpleNamespace(paths=SimpleNamespace(run_directory=run_dir))
    session = pipeline_module.PreProcessSession(index=0, total=1, dataset_name="ds", config=config)

    with pytest.raises(FileExistsError, match="already holds a finished dataset"):
        session.execute()

    assert built == []


def _install_stage_stubs(monkeypatch, tomogram_shape):
    """Stubs the PyRat launchers and the geometry builder of the pipeline module and returns the pass labels the stack stub reports.

    Args:
        monkeypatch    : Pytest monkeypatch fixture.
        tomogram_shape : Shape of the tomogram cube the tomogram stub saves, as (height, azimuth, range).
    """
    from types                                    import SimpleNamespace
    from pipelines.processing.generation          import pipeline as pipeline_module
    from pipelines.processing.generation.tomogram import TomogramContentAudit

    pass_labels = ["PS02", "PS04", "PS06"]

    class _StubTomogramLauncher:
        """Tomogram launcher stand-in that saves a cube of ones and returns its content audit."""

        def __init__(self, env_name, logger=None):
            """Ignores the environment name and logger."""
            pass

        def build_spec(self, config, tomogram_path, dem_path, result_path):
            """Returns the output paths as the real spec does."""
            return {"tomogram_path": str(tomogram_path), "dem_path": str(dem_path), "result_path": str(result_path)}

        def generate(self, spec, spec_path):
            """Saves the cube and DEM and returns the result the real stage writes."""
            tomogram = np.ones(tomogram_shape, np.complex64)
            dem      = np.zeros(tomogram_shape[1:], np.float32)

            Path(spec["tomogram_path"]).parent.mkdir(parents=True, exist_ok=True)
            np.save(spec["tomogram_path"], tomogram)
            np.save(spec["dem_path"],      dem)

            audit = TomogramContentAudit(CropRegion(0, tomogram_shape[1], 0, tomogram_shape[2]))
            audit.add_strip(0, dem, tomogram)

            return {"content": {**audit.summary(), "tomogram_shape": list(tomogram_shape), "dem_shape": list(tomogram_shape[1:])}, "provenance": {"executable": "/envs/stetools/bin/python", "pyrat_commit": "abc123def456"}}

    class _StubInterferogramLauncher:
        """Interferogram launcher stand-in returning fixed shapes and pass labels."""

        def __init__(self, env_name, logger=None):
            """Ignores the environment name and logger."""
            pass

        def build_spec(self, config, **paths):
            """Returns an empty spec."""
            return {}

        def generate(self, spec, spec_path):
            """Returns the result mapping the real stage reads."""
            amplitude = {"clip": 1.25, "passes": [{"pass": label, "samples": 16, "clipped": 0, "zero": 0, "nonfinite": 0} for label in pass_labels[1:]]}

            return {"primary_shape": [4, 4], "secondaries_shape": [2, 4, 4], "interferograms_shape": [2, 4, 4], "pass_labels": pass_labels, "secondary_amplitude": amplitude, "project_options": "suffix=_coreg", "inf_suffix": "_coreg", "provenance": {"executable": "/envs/stetools/bin/python"}}

    class _StubGeometryFieldBuilder:
        """Geometry field builder stand-in producing a field that saves an empty file."""

        def __init__(self, parameters, profiles, crop):
            """Ignores the track parameters, profiles and crop."""
            pass

        def build(self):
            """Returns a field stand-in with save() and describe()."""
            return SimpleNamespace(save=lambda path: path.write_bytes(b""), describe=lambda: {"shape": (4, 4)})

    monkeypatch.setattr(pipeline_module, "TomogramLauncher",      _StubTomogramLauncher)
    monkeypatch.setattr(pipeline_module, "InterferogramLauncher", _StubInterferogramLauncher)
    monkeypatch.setattr(pipeline_module, "GeometryFieldBuilder",  _StubGeometryFieldBuilder)
    monkeypatch.setattr(pipeline_module.TrackParameters, "load", staticmethod(lambda path: None))
    monkeypatch.setattr(pipeline_module.TrackProfiles,   "load", staticmethod(lambda path: None))

    return pass_labels


def test_processing_pipeline_run_reaches_the_dataset_layout(tmp_path, monkeypatch):
    """Runs the real ProcessingPipeline.run with stubbed PyRat launchers and geometry builder, so the entry and completion tables are exercised end to end."""
    from pipelines.processing.generation import pipeline as pipeline_module

    pass_labels = _install_stage_stubs(monkeypatch, tomogram_shape=(2, 4, 4))

    config   = ProcessingConfig(crop=CropRegion(0, 4, 0, 4), paths=PathConfig(main_directory=tmp_path, pyrat_directory=tmp_path / "pyrat", run_subdirectory="run"))
    recorder = _KvRecorder()

    artifacts = pipeline_module.ProcessingPipeline(config, logger=recorder).run()

    layout        = json.loads((config.paths.data_directory / "dataset.json").read_text())
    state         = json.loads((config.paths.metadata_directory / "config_state.json").read_text())
    tomogram_meta = (config.paths.metadata_directory / "meta_tomogram_full.txt").read_text()
    inputs_meta   = (config.paths.metadata_directory / "meta_inputs.txt").read_text()

    assert artifacts["run_directory"] == config.paths.run_directory
    assert layout["pass_labels"]      == pass_labels
    assert recorder.tables[0]["Beamforming"] == config.tomogram_config.beamforming_method
    assert recorder.tables[0]["PyRAT"].startswith("unavailable (no such directory")
    assert recorder.tables[-1]["Passes"]     == len(pass_labels)
    assert any(table.get("All-zero profiles") == "0 (0.000%)" for table in recorder.tables)
    assert "zero_profiles: 0 of 16 (0.000%)" in tomogram_meta
    assert "valid_azimuth: [0, 4)" in tomogram_meta
    assert "amplitude_clip: 1.25" in inputs_meta
    assert "inf_suffix: _coreg" in inputs_meta
    assert "project_options: suffix=_coreg" in inputs_meta
    assert "secondary_PS06: clipped 0.0000%, zero 0.0000%, nonfinite 0 of 16" in inputs_meta

    assert layout["provenance"]["pyrat_directory"]                   == str(tmp_path / "pyrat")
    assert layout["provenance"]["tomogram_stage"]["pyrat_commit"]    == "abc123def456"
    assert layout["provenance"]["interferogram_stage"]["executable"] == "/envs/stetools/bin/python"
    assert state["provenance"]["git_commit"]                         == layout["provenance"]["git_commit"]


def test_processing_pipeline_times_every_stage_into_the_completion_table(tmp_path, monkeypatch):
    """Each stage runs under its own timer and the completion table lists every stage's duration in seconds."""
    from pipelines.processing.generation import pipeline as pipeline_module

    _install_stage_stubs(monkeypatch, tomogram_shape=(2, 4, 4))

    config   = ProcessingConfig(crop=CropRegion(0, 4, 0, 4), paths=PathConfig(main_directory=tmp_path, run_subdirectory="run"))
    recorder = _LogRecorder()

    pipeline_module.ProcessingPipeline(config, logger=recorder).run()

    stages     = ["Tomogram stage (PyRAT)", "Interferogram stage (PyRAT)", "Geometry field"]
    completion = recorder.kv_tables[-1][1]

    assert recorder.timers == stages
    assert [key for key in completion if key.endswith(" [s]")] == [f"{stage} [s]" for stage in stages]
    assert all(float(completion[f"{stage} [s]"]) >= 0.0 for stage in stages)


def test_processing_pipeline_refuses_a_tomogram_off_the_stack_grid(tmp_path, monkeypatch):
    """A saved tomogram whose (azimuth, range) grid differs from the primary SLC grid stops the run before the dataset layout is written."""
    from pipelines.processing.generation import pipeline as pipeline_module

    _install_stage_stubs(monkeypatch, tomogram_shape=(2, 5, 4))

    config = ProcessingConfig(crop=CropRegion(0, 4, 0, 4), paths=PathConfig(main_directory=tmp_path, run_subdirectory="run"))

    with pytest.raises(RuntimeError, match=r"Tomogram grid \(5, 4\) .* differs from the primary SLC grid \(4, 4\)"):
        pipeline_module.ProcessingPipeline(config, logger=_KvRecorder()).run()

    assert not (config.paths.data_directory / "dataset.json").exists()


def test_tomogram_concatenate_rejects_a_grid_off_the_crop(tmp_path, logger):
    """Partials whose range extent differs from the crop make the merge raise, naming the crop and the resampling flags."""
    from pipelines.processing.generation.tomogram import TomogramProcessor

    rng      = np.random.default_rng(4)
    dem      = rng.normal(size=(30, 8)).astype(np.float32)
    tomogram = (rng.normal(size=(5, 30, 8)) + 1j * rng.normal(size=(5, 30, 8))).astype(np.complex64)

    config    = ProcessingConfig(crop=CropRegion(0, 30, 0, 6), paths=PathConfig(main_directory=tmp_path, run_subdirectory="run"))
    processor = TomogramProcessor(config, logger)

    config.tomogram_config.max_crop_azimuth_width = 12
    subsections, scratch = _strip_partials(tmp_path, processor, config, dem, tomogram)

    with pytest.raises(RuntimeError, match=r"crop extent \(30, 6\) of crop \(0, 30, 0, 6\) \(apply_presumming=False, apply_resampling=False\)"):
        processor._concatenate(scratch, subsections)


class _StubProcessingPipeline:
    """Stands in for ProcessingPipeline: logs one line and returns an empty artifact mapping."""

    def __init__(self, config, logger) -> None:
        """Keeps the logger the session hands over."""
        self.logger = logger

    def run(self) -> dict:
        """Returns no artifacts."""
        self.logger.info("stub pipeline ran")
        return {}


def test_session_on_a_new_directory_logs_no_leftover_warning(tmp_path, monkeypatch):
    """A session on a directory that did not exist writes no leftover warning, although it creates logs/ before its logger opens."""
    from types import SimpleNamespace

    import pipelines.processing.generation.pipeline as generation_pipeline

    monkeypatch.setattr(generation_pipeline, "ProcessingPipeline", _StubProcessingPipeline)

    run_dir = tmp_path / "fresh_ds"
    session = generation_pipeline.PreProcessSession(index=0, total=1, dataset_name="fresh_ds", config=SimpleNamespace(paths=SimpleNamespace(run_directory=run_dir)))

    session.execute()

    contents = (run_dir / "logs" / "preprocessing.log").read_text(encoding="utf-8")

    assert "stub pipeline ran" in contents
    assert "exists without a finished dataset" not in contents


def test_session_refuses_a_finished_dataset_before_writing_into_it(tmp_path, monkeypatch):
    """A session on a finished dataset raises before it creates logs/ or appends to the dataset's own log."""
    from types import SimpleNamespace

    import pipelines.processing.generation.pipeline as generation_pipeline

    monkeypatch.setattr(generation_pipeline, "ProcessingPipeline", _StubProcessingPipeline)

    run_dir = _finished_dataset_dir(tmp_path, "data/dataset.json")
    session = generation_pipeline.PreProcessSession(index=0, total=1, dataset_name="ds", config=SimpleNamespace(paths=SimpleNamespace(run_directory=run_dir)))

    with pytest.raises(FileExistsError, match="already holds a finished dataset"):
        session.execute()

    assert not (run_dir / "logs").exists()
