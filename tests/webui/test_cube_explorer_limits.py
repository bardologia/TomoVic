"""Tests of the colour and grey limits the cube explorer estimates."""

from __future__ import annotations

import numpy as np

from cube_explorer import CubeExplorer
from web_logger    import WebLogger


def test_the_limit_sample_visits_every_range_column(monkeypatch):
    """800 values at a budget of 100 give stride 8, which lands on 5 of the 20 range columns; the stride is raised to 9 and visits all."""

    monkeypatch.setattr(CubeExplorer, "LIMIT_SAMPLE", 100)
    cube   = np.broadcast_to(np.arange(20, dtype=np.float32), (4, 10, 20)).copy()
    sample = CubeExplorer._limit_sample(cube)

    assert np.unique(cube.reshape(-1)[::8]).size == 5
    assert np.unique(sample).size == 20
    assert np.array_equal(sample, cube.reshape(-1)[::9])


def test_primary_limits_skip_nan_and_zero_fill():
    """A NaN pixel and 10 percent of zero fill leave the limits at the percentiles of the measured pixels."""

    amplitude        = np.linspace(1.0, 100.0, 400).reshape(20, 20)
    amplitude[:2]    = 0.0
    amplitude[5, 5]  = np.nan
    primary          = (20.0 * np.log10(np.maximum(amplitude, 1e-12))).astype(np.float32)
    measured         = primary[(amplitude > 0.0) & np.isfinite(amplitude)]

    assert CubeExplorer._primary_clim(primary) == tuple(float(v) for v in np.percentile(measured, [1.0, 99.0]))
    assert CubeExplorer._primary_clim(np.full((4, 4), np.nan, dtype=np.float32)) == (0.0, 1.0)


def test_a_real_cube_is_shown_as_its_magnitude():
    """A real cube with negative values enters the Cube tab rectified, as the TomoVis window shows it."""

    raw   = np.linspace(-3.0, 2.0, 60, dtype=np.float32).reshape(3, 4, 5)
    entry = CubeExplorer(WebLogger())._ingest(raw, np.arange(3.0))

    assert entry["cube"].dtype == np.float32
    assert np.array_equal(entry["cube"], np.abs(raw))
    assert entry["vmin"] >= 0.0
