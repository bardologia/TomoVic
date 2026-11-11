"""Tests of TomoVis's copied helpers: colour tables, normalize, sanitize_for_display, add_dem_to_tomogram."""

from __future__ import annotations

import json

import numpy as np

from tests.webui.conftest import REPO_ROOT
from tomovis.tools        import TomoVisTools

TABLES = REPO_ROOT / "tests" / "webui" / "fixtures" / "tomovis" / "tables"


def test_colortables_equal_the_originals():
    """The 19 colour tables equal the ones recorded from the original, in order and by name."""

    names, tables = TomoVisTools.colortables()
    recorded      = np.load(TABLES / "tables.npz")["colortables"]
    meta          = json.loads((TABLES / "tables.json").read_text())

    assert list(names) == meta["colortable_names"]
    assert np.array_equal(np.array(tables), recorded)
    assert np.array(tables).dtype == np.uint8


def test_colortables_lookup_forms():
    """An index or a name returns (name, table); entry 128 of IDL rainbow (13) is (0, 255, 157)."""

    name, table = TomoVisTools.colortables(9)

    assert name == "IDL rainbow (13)"
    assert table[128].tolist() == [0, 255, 157]
    assert TomoVisTools.colortables("blue-red-yellow")[0] == TomoVisTools.colortables(4)[0]


def test_plot_colormaps_are_the_original_list():
    """The Plot tab offers the 71 matplotlib names of pyplotCmaps in order, jet at index 65."""

    meta = json.loads((TABLES / "tables.json").read_text())

    assert TomoVisTools.PLOT_COLORMAPS == meta["pyplot_cmaps"]
    assert TomoVisTools.PLOT_COLORMAPS.index("jet") == 65


def test_normalize_scales_to_the_range_and_zeroes_constant_input():
    """normalize maps min..max onto a..b; a constant array gives zeros instead of NaN."""

    scaled   = TomoVisTools.normalize(np.array([2.0, 4.0, 6.0]), 0, 255)
    constant = TomoVisTools.normalize(np.array([3.0, 3.0]), 0, 1)

    assert scaled.tolist() == [0.0, 127.5, 255.0]
    assert constant.tolist() == [0.0, 0.0]


def test_sanitize_takes_magnitudes_and_zeroes_non_finite_values():
    """Complex values become magnitudes, NaN and infinities become 0, and the dtype is cast."""

    values = np.array([3 + 4j, np.nan, np.inf], dtype=np.complex64)
    clean  = TomoVisTools.sanitize_for_display(values)

    assert clean.dtype == np.float32
    assert clean.tolist() == [5.0, 0.0, 0.0]


def test_add_dem_to_tomogram_shifts_each_column():
    """Each (i, j) column moves down by (dem - min) / vSampling samples into a taller zero array."""

    tomo = np.arange(1, 1 + 2 * 1 * 2, dtype=float).reshape(2, 1, 2)
    dem  = np.array([[0.0, 2.0]])

    shifted = TomoVisTools.add_dem_to_tomogram(tomo, dem, vSampling=1.0)

    assert shifted.shape == (5, 1, 2)
    assert shifted[:, 0, 0].tolist() == [1.0, 3.0, 0.0, 0.0, 0.0]
    assert shifted[:, 0, 1].tolist() == [0.0, 0.0, 2.0, 4.0, 0.0]
