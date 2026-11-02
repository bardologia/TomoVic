"""Tests for the preprocessing comparison window metrics.

Covers the spurious-peak count computed from a reflectivity profile, the
range-chunk sampling that selects which parts of the scene are measured, the
discovery and scene checks of the trial collector and the per-trial progress
the pipeline logs.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from configuration.comparison                      import PreprocessingComparisonConfig
from pipelines.comparison.preprocessing_comparison import PreprocessingComparisonPipeline, WindowComparisonPlots, WindowMetrics, WindowTrialCollector

from tests.conftest import RecordingLogger


HEIGHT = 32


def _write_dataset(root: Path, name: str, window: list[int], polarisation: str = "hv", tomogram: bool = True) -> Path:
    """Writes a tiny preprocessing run: a complex tomogram cube and the config state naming its window and scene.

    Args:
        root         : Dataset root the run folder is created in.
        name         : Run folder name.
        window       : Multilook window as [height, width].
        polarisation : Polarisation recorded in the config state.
        tomogram     : Whether the tomogram cube is written, False for a run that failed before it.

    Returns:
        Path of the run directory.
    """
    run_dir = root / name
    (run_dir / "data").mkdir(parents=True)
    (run_dir / "meta").mkdir()

    if tomogram:
        rng  = np.random.default_rng(0)
        cube = (rng.standard_normal((8, 6, 6)) + 1j * rng.standard_normal((8, 6, 6))).astype(np.complex64)
        np.save(run_dir / "data" / "tomogram_full.npy", cube)

    state = {
        "crop"             : {"azimuth_start": 0, "azimuth_end": 6, "range_start": 0, "range_end": 6},
        "stack_identifier" : "1",
        "tomogram_config"  : {"polarisation": polarisation, "track_selection": "*", "height_range": [-20.0, 80.0], "filter_arguments": {"win": window}},
    }
    (run_dir / "meta" / "config_state.json").write_text(json.dumps(state), encoding="utf-8")

    return run_dir


def _profile(peaks: list[tuple[float, float]]) -> np.ndarray:
    """Returns a reflectivity profile of shape (HEIGHT, 1, 1) built from Gaussian peaks given as (centre bin, amplitude) pairs."""
    bins  = np.arange(HEIGHT, dtype=np.float64)
    curve = np.zeros(HEIGHT, dtype=np.float64)

    for centre, amplitude in peaks:
        curve += amplitude * np.exp(-0.5 * ((bins - centre) / 2.0) ** 2)

    return curve.astype(np.float32).reshape(HEIGHT, 1, 1)


def _spurious(profile: np.ndarray) -> float:
    """Returns the spurious-peak count of a single-pixel profile of shape (height, 1, 1)."""
    metrics = WindowMetrics.__new__(WindowMetrics)
    return float(metrics._chunk_maps(profile)[2].ravel()[0])


def test_single_scatterer_scores_no_spurious_peak():
    """Verifies a profile holding one peak scores no spurious peak."""
    assert _spurious(_profile([(16.0, 1.0)])) == 0.0


def test_competing_scatterer_is_counted_once():
    """Verifies a second peak above the significance fraction is counted once."""
    assert _spurious(_profile([(16.0, 1.0), (26.0, 0.5)])) == 1.0


def test_peak_below_the_significance_fraction_is_ignored():
    """Verifies a secondary peak below the significance fraction is not counted."""
    assert _spurious(_profile([(16.0, 1.0), (26.0, 0.1)])) == 0.0


def test_empty_profile_scores_no_spurious_peak():
    """Verifies an all-zero profile scores no spurious peak."""
    assert _spurious(np.zeros((HEIGHT, 1, 1), dtype=np.float32)) == 0.0


def test_dominant_peak_on_the_first_bin_still_counts_the_interior_peak():
    """Verifies an interior peak is counted when the dominant sample sits on the first height bin."""
    profile          = _profile([(26.0, 1.0)])
    profile[0, 0, 0] = 2.0

    assert _spurious(profile) == 1.0


def test_dominant_peak_on_the_last_bin_still_counts_the_interior_peak():
    """Verifies an interior peak is counted when the dominant sample sits on the last height bin."""
    profile           = _profile([(6.0, 1.0)])
    profile[-1, 0, 0] = 2.0

    assert _spurious(profile) == 1.0


def _starts(pixel_sample: int, range_chunk: int, ranges: int, azimuths: int) -> list[int]:
    """Returns the sampled range-chunk start indices for a scene of the given range and azimuth extent."""
    metrics              = WindowMetrics.__new__(WindowMetrics)
    metrics.pixel_sample = pixel_sample
    metrics.range_chunk  = range_chunk

    return metrics._range_starts(ranges, azimuths)


def test_single_sampled_chunk_sits_at_the_scene_centre():
    """Verifies a budget covered by one chunk samples the chunk at the scene centre."""
    starts = _starts(pixel_sample=200000, range_chunk=512, ranges=6000, azimuths=5000)

    assert starts == [3072]


def test_sampled_chunks_spread_over_the_range_extent():
    """Verifies several sampled chunks are spread over range and none starts at the scene edge."""
    starts = _starts(pixel_sample=200000, range_chunk=512, ranges=6000, azimuths=100)

    assert starts    == [512, 2048, 3584, 5120]
    assert starts[0] > 0


def test_disabled_pixel_sample_keeps_every_chunk():
    """Verifies a zero pixel budget keeps every range chunk."""
    starts = _starts(pixel_sample=0, range_chunk=512, ranges=2000, azimuths=5000)

    assert starts == [0, 512, 1024, 1536]


def test_auto_discovery_warns_for_each_incomplete_run(tmp_path):
    """Verifies auto mode names every run skipped for lacking its tomogram or config state and ignores the comparison's own output folder."""
    _write_dataset(tmp_path, "ds_small", [2, 2])
    _write_dataset(tmp_path, "ds_failed", [4, 4], tomogram=False)
    (tmp_path / "_window_comparison").mkdir()

    logger = RecordingLogger()
    trials = WindowTrialCollector(tmp_path, [], logger).collect()

    warnings = [message for level, message in logger.messages if level == "warning"]

    assert [trial.name for trial in trials] == ["ds_small"]
    assert any(message.startswith("ds_failed: skipped, no data/tomogram_full.npy") for message in warnings)
    assert any("1 of 2 directories" in message and "ds_failed" in message for message in warnings)
    assert not any("_window_comparison" in message for message in warnings)


def test_collector_logs_the_scene_and_rejects_trials_of_different_scenes(tmp_path):
    """Verifies the per-trial line carries the scene fields and two runs of different polarisation abort, both named."""
    _write_dataset(tmp_path, "ds_hv", [2, 2])
    _write_dataset(tmp_path, "ds_hh", [4, 4], polarisation="hh")

    logger = RecordingLogger()

    with pytest.raises(ValueError, match="polarisation") as excinfo:
        WindowTrialCollector(tmp_path, ["ds_hv", "ds_hh"], logger).collect()

    infos = [message for level, message in logger.messages if level == "info"]

    assert "ds_hv" in str(excinfo.value) and "ds_hh" in str(excinfo.value)
    assert any(message.startswith("ds_hv") and "polarisation=hv" in message and "stack_identifier=1" in message for message in infos)


def test_pipeline_logs_one_line_per_measured_trial_and_names_datasets_in_the_report(tmp_path):
    """Verifies parallel measurement reports every finished trial with a counter under its own section and the report table leads with the dataset."""
    root = tmp_path / "Dataset"
    _write_dataset(root, "ds_small", [2, 2])
    _write_dataset(root, "ds_large", [4, 4])

    config = PreprocessingComparisonConfig(runs_dir=root, run_tags=[], pixel_sample=0, block_size=2, range_chunk=4, workers=2, make_plots=False, output_dir=tmp_path / "out")
    logger = RecordingLogger()

    report = PreprocessingComparisonPipeline(config=config, out_dir=tmp_path / "out", logger=logger).run()

    sections = [message for level, message in logger.messages if level == "section"]
    oks      = [message for level, message in logger.messages if level == "ok"]
    text     = report.read_text(encoding="utf-8")

    assert sections == ["Collecting preprocessing trials", "Measuring trials", "Writing comparison report"]
    assert sorted(message[:5] for message in oks if message.startswith("[")) == ["[1/2]", "[2/2]"]
    assert all("2 of 2 range chunks measured in" in message for message in oks if message.startswith("["))
    assert "| Dataset" in text
    assert "`ds_small`" in text and "`ds_large`" in text


def test_plots_label_every_bar_with_window_and_dataset(tmp_path):
    """Verifies the comparison plots render with the dataset name under each window label."""
    root   = tmp_path / "Dataset"
    trials = []
    for name, window in (("ds_small", [2, 2]), ("ds_large", [4, 4])):
        _write_dataset(root, name, window)
        trials += WindowTrialCollector(root, [name], RecordingLogger()).collect()

    for trial in trials:
        trial.metrics = {key: 1.0 for key, _label, _title in WindowComparisonPlots.PANELS}

    written = WindowComparisonPlots(tmp_path / "out").render(trials)

    assert [path.name for path in written] == [f"{key}.png" for key, _label, _title in WindowComparisonPlots.PANELS]
    assert all(path.is_file() for path in written)
