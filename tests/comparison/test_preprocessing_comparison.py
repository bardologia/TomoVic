"""Tests for the preprocessing comparison window metrics.

Covers the spurious-peak count computed from a reflectivity profile and the
range-chunk sampling that selects which parts of the scene are measured.
"""

from __future__ import annotations

import numpy as np

from pipelines.comparison.preprocessing_comparison import WindowMetrics


HEIGHT = 32


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
