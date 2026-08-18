"""Tests covering the dataset generation pipeline of the processing stage.

Exercises stack consistency of the generated SAR artifacts, interferogram
formation and clipping, metadata and layout serialisation, the stack plotting
and distribution analysers, and the tomogram tiling/concatenation logic.
"""

from __future__ import annotations

import json

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

    out_path = manager.save_dataset_layout(pass_labels=dataset_json["pass_labels"])
    loaded   = json.loads(out_path.read_text())

    assert loaded["global_crop"]  == list(crop_from_state.as_tuple())
    assert loaded["dataset_type"] == "FSAR"
    assert loaded["pass_labels"]  == dataset_json["pass_labels"]
    assert loaded["artifacts"]    == dataset_json["artifacts"]


@pytest.mark.real_data
def test_config_state_roundtrip(tmp_path, crop_from_state, logger):
    """Verifies the dumped pipeline configuration keeps the crop, amplitude clip and dataset type."""
    paths   = PathConfig(main_directory=tmp_path, run_subdirectory="run")
    config  = ProcessingConfig(crop=crop_from_state, paths=paths)
    manager = MetadataManager(config, logger)

    dump_path = manager.save_pipeline_configuration()
    loaded    = json.loads(dump_path.read_text())

    assert loaded["crop"]["azimuth_start"]                 == crop_from_state.azimuth_start
    assert loaded["tomogram_config"]["max_amplitude_clip"] == CLIP
    assert loaded["dataset_type"]                          == "FSAR"


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
    )
    meta_path = manager.save_stage_metadata("inputs", entries)

    assert meta_path.is_file()
    text = meta_path.read_text()
    assert "primary_shape" in text


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
    assert result["statistics"]["count"] == values.size
    assert result["statistics"]["min"] <= result["statistics"]["median"] <= result["statistics"]["max"]


def test_value_distribution_honours_fixed_range_and_nonfinite():
    """Verifies a fixed value range pins the bin edges and non-finite samples are counted apart."""
    values = np.array([-np.pi, 0.0, np.pi / 2, np.nan], dtype=np.float32)
    result = ValueDistribution(values, scale="linear", n_bins=8, value_range=(-np.pi, np.pi)).compute()
    edges  = result["histogram"]["bin_edges"]

    assert result["statistics"]["n_nonfinite"] == 1
    assert result["statistics"]["count"]       == 3
    assert edges[0]  == pytest.approx(-np.pi)
    assert edges[-1] == pytest.approx(np.pi)


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


def _write_tomo_partial(directory, suffix: str, dem_chunk: np.ndarray, tomogram_chunk: np.ndarray) -> None:
    """Writes one partial tomogram HDF5 chunk with DEM and tomogram datasets.

    Args:
        directory: Destination directory for the partial file.
        suffix: Zero-padded index used in the partial filename.
        dem_chunk: DEM slab of shape (azimuth_chunk, range).
        tomogram_chunk: Complex tomogram slab of shape (height, azimuth_chunk, range).
    """
    import h5py

    directory.mkdir(parents=True, exist_ok=True)

    with h5py.File(str(directory / f"partial_{suffix}.h5"), "w") as handle:
        handle.create_dataset("DEM",      data=dem_chunk)
        handle.create_dataset("tomogram", data=tomogram_chunk)


class _CleanupRecorder(SilentLogger):
    """Silent logger that records error and subsection messages for assertions.

    Attributes:
        errors: Messages passed to error().
        subsections: Messages passed to subsection().
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

    combined_dem, combined_tomogram = processor._concatenate(tmp_path / "tomo_tmp", subsections)

    np.testing.assert_array_equal(combined_dem,      dem)
    np.testing.assert_array_equal(combined_tomogram, tomogram)


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
