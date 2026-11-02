"""Tests for the north-up footprint resampler behind the globe's image drapes.

Covers the rectangle spanned by a rotated footprint, the north-up row order,
transparency outside the footprint, nearest-pixel colours, the width clamp,
pixels without terrain, a mismatched image shape, the per-axis gap tolerance
on an anisotropic radar grid, the width and stride plan, and the reuse of one
lookup by several paints.
"""

from __future__ import annotations

import numpy as np
import pytest

from scipy.ndimage import binary_fill_holes

from globe_drape import FootprintImage

PIXEL_M = 10.0
LON0, LAT0 = 12.6, 47.8
M_PER_DEG_LON = FootprintImage.METRES_PER_DEG_LON * np.cos(np.radians(LAT0))
M_PER_DEG_LAT = FootprintImage.METRES_PER_DEG_LAT


class RotatedGeocoder:
    """Geocoder stub placing pixels on a ground grid rotated by a fixed heading.

    Attributes:
        angle   : Rotation of the azimuth axis from east, in radians.
        pixel_m : Ground metres per pixel along azimuth and range.
    """

    def __init__(self, angle_deg: float, pixel_m: tuple = (PIXEL_M, PIXEL_M)) -> None:
        """Stores the heading of the azimuth axis and the pixel spacings."""
        self.angle   = np.radians(angle_deg)
        self.pixel_m = pixel_m

    def geocode(self, az_px, rg_px, height_m):
        """Returns longitude, latitude and a zero ECEF block for pixels on the rotated ground grid."""
        az    = np.asarray(az_px, dtype=np.float64) * self.pixel_m[0]
        rg    = np.asarray(rg_px, dtype=np.float64) * self.pixel_m[1]
        east  = az * np.cos(self.angle) - rg * np.sin(self.angle)
        north = az * np.sin(self.angle) + rg * np.cos(self.angle)
        lon   = LON0 + east / M_PER_DEG_LON
        lat   = LAT0 + north / M_PER_DEG_LAT
        return lon, lat, np.zeros((lon.size, 3))


def _image(n_az: int, n_rg: int) -> np.ndarray:
    """Returns an image whose red channel encodes the azimuth row and green the range column."""
    image = np.zeros((n_az, n_rg, 3), dtype=np.float32)
    image[..., 0] = np.linspace(0.0, 1.0, n_az)[:, None]
    image[..., 1] = np.linspace(0.0, 1.0, n_rg)[None, :]
    return image


def test_rotated_footprint_is_north_up_and_transparent_outside(tmp_path):
    """Checks a footprint rotated by 45 degrees fills the centre, leaves the rectangle corners clear and keeps north on top."""
    n_az, n_rg = 40, 20
    dem        = np.full((n_az, n_rg), 500.0)
    resampler  = FootprintImage(RotatedGeocoder(45.0), dem, 0, 0)

    rgba, rect = resampler.render(_image(n_az, n_rg), 128, (1, 1))
    west, south, east, north = rect

    assert rgba.shape[2] == 4 and rgba.shape[1] == 128
    assert west < east and south < north
    assert rgba[0, 0, 3] == 0 and rgba[-1, -1, 3] == 0 and rgba[0, -1, 3] == 0 and rgba[-1, 0, 3] == 0
    assert rgba[rgba.shape[0] // 2, rgba.shape[1] // 2, 3] == 255

    lon, lat, _ = resampler.geocoder.geocode(np.array([0, n_az - 1]), np.array([0, n_rg - 1]), np.zeros(2))
    assert west <= lon.min() and east >= lon.max() and south <= lat.min() and north >= lat.max()

    rows_with_colour = np.where(rgba[..., 3].max(axis=1) == 255)[0]
    top_row = rgba[rows_with_colour[0]]
    cols    = np.where(top_row[:, 3] == 255)[0]
    top_pixel = top_row[cols[len(cols) // 2]]
    assert top_pixel[0] > 200 and top_pixel[1] > 200


def test_cells_take_the_nearest_pixel_colour(tmp_path):
    """Checks an axis-aligned footprint reproduces the pixel colours cell by cell."""
    n_az, n_rg = 8, 6
    dem        = np.full((n_az, n_rg), 0.0)
    resampler  = FootprintImage(RotatedGeocoder(90.0), dem, 0, 0)

    rgba, rect = resampler.render(_image(n_az, n_rg), 64, (1, 1))

    opaque = rgba[..., 3] == 255
    assert opaque.mean() > 0.85

    centre = rgba[rgba.shape[0] // 2, rgba.shape[1] // 2]
    assert 60 < centre[0] < 200 and 60 < centre[1] < 200


def test_width_is_clamped_and_shape_is_checked(tmp_path):
    """Checks the width clamp and the refusal of an image off the footprint grid."""
    dem       = np.full((4, 4), 0.0)
    resampler = FootprintImage(RotatedGeocoder(0.0), dem, 0, 0)

    rgba, _ = resampler.render(_image(4, 4), 1, (1, 1))
    assert rgba.shape[1] == FootprintImage.MIN_WIDTH

    with pytest.raises(ValueError, match="footprint grid"):
        resampler.render(_image(5, 4), 64, (1, 1))


def test_pixels_without_terrain_are_skipped(tmp_path):
    """Checks NaN terrain pixels are left out and an all-NaN terrain is refused."""
    dem          = np.full((6, 6), 0.0)
    dem[:3, :]   = np.nan
    resampler    = FootprintImage(RotatedGeocoder(0.0), dem, 0, 0)

    rgba, _ = resampler.render(_image(6, 6), 64, (1, 1))
    assert rgba[..., 3].max() == 255

    with pytest.raises(ValueError, match="finite terrain"):
        FootprintImage(RotatedGeocoder(0.0), np.full((3, 3), np.nan), 0, 0).render(_image(3, 3), 64, (1, 1))


def test_anisotropic_grid_leaves_no_holes_inside_the_footprint(tmp_path):
    """Checks a radar grid whose range step is three times the azimuth step fills every interior cell while the rectangle corners stay clear."""
    n_az, n_rg = 40, 30
    dem        = np.full((n_az, n_rg), 0.0)
    resampler  = FootprintImage(RotatedGeocoder(43.0, pixel_m=(1.0, 3.0)), dem, 0, 0)

    rgba, _ = resampler.render(_image(n_az, n_rg), 1024, (1, 1))
    opaque  = rgba[..., 3] == 255

    assert opaque.any()
    assert not (binary_fill_holes(opaque) & ~opaque).any()
    assert rgba[0, 0, 3] == 0 and rgba[-1, -1, 3] == 0 and rgba[0, -1, 3] == 0 and rgba[-1, 0, 3] == 0


def test_plan_chooses_the_width_and_a_stride_per_axis(tmp_path):
    """Checks the plan caps the cell count, measures the pixel spacing per axis and strides each axis by the pixels one cell covers."""
    wide = FootprintImage(RotatedGeocoder(0.0, pixel_m=(1.0, 3.0)), np.zeros((2000, 1000)), 0, 0).plan(4.0, 128)

    assert wide["width"] == 128
    assert wide["spacing"] == pytest.approx((1.0, 3.0), rel=1e-3)
    assert wide["cell"] == pytest.approx(3.0 * 999 / 127, rel=1e-3)
    assert wide["step"] == (24, 8)

    small = FootprintImage(RotatedGeocoder(0.0), np.zeros((8, 6)), 0, 0).plan(4.0, 4096)

    assert small["width"] == FootprintImage.MIN_WIDTH
    assert small["step"] == (1, 1)


def test_one_lookup_paints_several_images(tmp_path):
    """Checks a lookup built once paints different images onto the same cells with the same transparency."""
    n_az, n_rg = 12, 9
    resampler  = FootprintImage(RotatedGeocoder(30.0), np.zeros((n_az, n_rg)), 0, 0)
    lookup     = resampler.geometry(96, (1, 1))

    first  = resampler.paint(_image(n_az, n_rg), lookup)
    second = resampler.paint(1.0 - _image(n_az, n_rg), lookup)

    assert first.shape == second.shape == lookup["shape"] + (4,)
    np.testing.assert_array_equal(first[..., 3], second[..., 3])
    assert (first[..., :3] != second[..., :3]).any()
    assert lookup["inside"].sum() == (first[..., 3] == 255).sum()
