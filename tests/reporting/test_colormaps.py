"""Tests covering the TAXI phase colormap and its use as the PlotBase phase palette."""

from __future__ import annotations

import matplotlib

matplotlib.use("Agg")
import matplotlib.colors as mcolors
import numpy             as np
import pytest

from tools.reporting.colormaps import PhaseColormap
from tools.reporting.plotting  import PlotBase


def test_channel_tables_have_256_entries():
    """Verifies each RGB channel table holds one entry per colormap level."""
    assert len(PhaseColormap.R) == 256
    assert len(PhaseColormap.G) == 256
    assert len(PhaseColormap.B) == 256


def test_colormap_matches_channel_tables():
    """Verifies the built colormap reproduces the channel tables as opaque RGBA in [0, 1]."""
    cmap   = PhaseColormap.colormap()
    colors = np.asarray(cmap.colors)

    assert cmap.N == 256
    assert colors.shape == (256, 4)

    for index in (0, 63, 127, 191, 255):
        expected = np.array([PhaseColormap.R[index], PhaseColormap.G[index], PhaseColormap.B[index], 255]) / 255.0
        assert colors[index] == pytest.approx(expected)


def test_colormap_endpoints_wrap():
    """Verifies the first and last colours nearly coincide, so phase wraps without a seam."""
    colors = np.asarray(PhaseColormap.colormap().colors)
    assert np.abs(colors[0] - colors[-1]).max() < 0.05


def test_colormap_is_cached_and_registered():
    """Verifies the colormap instance is cached and registered under its matplotlib name."""
    first  = PhaseColormap.colormap()
    second = PhaseColormap.colormap()

    assert first is second
    assert PhaseColormap.NAME in matplotlib.colormaps


def test_plotbase_phase_cmap_returns_taxi():
    """Verifies PlotBase resolves its phase colormap to the shared TAXI instance."""
    cmap = PlotBase._phase_cmap()
    assert isinstance(cmap, mcolors.Colormap)
    assert cmap is PhaseColormap.colormap()
