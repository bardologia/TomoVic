"""Tests of the pyqtgraph affineSlice port and the LineSegmentROI region extraction.

The parity goldens check the extracted tomograms of every ROI case against
the original (test_tomovis_goldens). These tests pin the port's own
behaviour: pyqtgraph's documented interpolateArray examples, zero outside the
bounds, bilinear agreement with scipy inside them, the sample counts of the
parity cases and the zero-length line fix (E-012).
"""

from __future__ import annotations

import numpy as np
import pytest
from scipy import ndimage

from tomovis.pg_affine  import PgAffineSlice
from tomovis.pg_models  import PgImageViewModel, PgLineSegmentRoiModel, PgPoint
from tomovis.qt_widgets import SlotBoundary


def test_interpolate_array_reproduces_the_pyqtgraph_examples():
    """The docstring examples of pyqtgraph.functions.interpolateArray."""

    data = np.array([[1, 2, 4], [10, 20, 40], [100, 200, 400]])

    assert PgAffineSlice.interpolateArray(data, np.array([(0.5, 0.5)])).tolist() == [8.25]
    assert PgAffineSlice.interpolateArray(data, np.array([(0.5, 0.5), (1.0, 1.0), (1.0, 2.0), (1.5, 0.0)])).tolist() == [8.25, 20.0, 40.0, 55.0]
    assert PgAffineSlice.interpolateArray(data, np.array([[0.5]])).tolist() == [[5.5, 11.0, 22.0]]


def test_interpolate_array_is_zero_outside_and_bilinear_inside():
    """Points with a negative floor or beyond the last index give 0; inside, values equal scipy's order-1 map."""

    rng    = np.random.default_rng(3)
    data   = rng.random((6, 7))
    inside = rng.random((50, 2)) * [5, 6]

    expected = ndimage.map_coordinates(data, inside.T, order=1)

    assert np.allclose(PgAffineSlice.interpolateArray(data, inside), expected, rtol=1e-12)
    assert PgAffineSlice.interpolateArray(data, np.array([(-0.5, 1.0), (5.5, 1.0), (1.0, 6.01)])).tolist() == [0.0, 0.0, 0.0]


def test_affine_slice_keeps_the_other_axes_first():
    """Slicing axes (1, 2) of an (A, B, C) cube along a line gives (A, n) samples."""

    cube   = np.arange(4 * 5 * 6, dtype=float).reshape(4, 5, 6)
    region = PgAffineSlice.affineSlice(cube, shape=(3,), vectors=[(1.0, 0.0)], origin=(1.0, 2.0), axes=(1, 2))

    assert region.shape == (4, 3)
    assert np.array_equal(region, cube[:, 1:4, 2])


def roi_region(points, data: np.ndarray) -> np.ndarray:
    """Extracts a region with a LineSegmentROI model placed on two points."""

    roi = PgLineSegmentRoiModel(points, SlotBoundary(lambda exc, text: None))
    return roi.getArrayRegion(data, PgImageViewModel("imv").imageItem, axes=(1, 2))


@pytest.mark.parametrize("points, samples", [
    ([[0, 0], [17.96875, 23.0]], 29),
    ([[1, 2], [3.856, 0]], 3),
    ([[5, 5], [5.6, 5]], 0),
    ([[0, 0], [31, 0]], 31),
])
def test_line_regions_take_int_length_samples(points, samples):
    """int(length) samples at unit spacing; the end point is never sampled (parity 3.4)."""

    cube = np.ones((16, 32, 24), dtype=np.float32)

    assert roi_region(points, cube).shape == (16, samples)


def test_line_region_starts_at_the_first_endpoint_and_walks_unit_steps():
    """A horizontal line from (2, 10) samples azimuth 2, 3, 4 at range 10 for every elevation."""

    cube = np.arange(3 * 8 * 12, dtype=float).reshape(3, 8, 12)

    assert np.array_equal(roi_region([[2, 10], [5, 10]], cube), cube[:, 2:5, 10])


def test_zero_length_line_samples_nothing_instead_of_raising():
    """E-012: a clipped line reduced to a point gives an empty region, as any line shorter than one sample."""

    assert roi_region([[0, 0], [0, 0]], np.ones((4, 5, 6))).shape == (4, 0)


def test_points_compare_like_qpointf():
    """Point equality is QPointF's fuzzy comparison."""

    assert PgPoint(1.0, 0.0) == PgPoint(1.0 + 1e-14, 1e-13)
    assert PgPoint(1.0, 0.0) != PgPoint(1.0 + 1e-9, 0.0)
