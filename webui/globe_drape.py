"""North-up rasters of radar-grid images over the scene footprint, for draping on the globe.

A radar image sits on an (azimuth, range) grid whose footprint is a rotated
quadrilateral on the ground. Cesium drapes imagery as north-up rectangles, so
the image is resampled here onto a regular longitude/latitude grid of square
ground cells: pixels are forward-geocoded at their terrain height on a stride
chosen per axis so that about one sample falls into every cell, every cell
takes the colour of its nearest geocoded sample, and cells farther from every
sample than the larger of the two axis spacings allows stay transparent. The
lookup depends only on the footprint, so it is built once and reused for every
image painted over it.
"""

from __future__ import annotations

import math

import numpy as np
from scipy.spatial import cKDTree


class FootprintImage:
    """Resamples an (azimuth, range) colour image onto a north-up longitude/latitude grid.

    Attributes:
        METRES_PER_DEG_LAT : Ground metres per degree of latitude.
        METRES_PER_DEG_LON : Ground metres per degree of longitude at the equator.
        GAP_FACTOR         : Multiple of the larger per-axis sample spacing beyond which a cell is left transparent.
        GAP_PERCENTILE     : Percentile of the gaps between lattice neighbours taken as an axis's spacing, so rows stretched by terrain still fill.
        MIN_WIDTH          : Smallest accepted cell count along the longer side.
        MAX_WIDTH          : Largest accepted cell count along the longer side.
        geocoder           : Scene geocoder mapping (azimuth, range, height) to longitude and latitude.
        dem                : Terrain heights of the footprint in metres, shape (azimuth, range); NaN pixels are skipped.
        az0                : Absolute azimuth index of the footprint's first row.
        rg0                : Absolute range index of the footprint's first column.
    """

    METRES_PER_DEG_LAT = 110574.0
    METRES_PER_DEG_LON = 111320.0
    GAP_FACTOR         = 1.5
    GAP_PERCENTILE     = 99.0
    MIN_WIDTH          = 64
    MAX_WIDTH          = 4096

    def __init__(self, geocoder, dem: np.ndarray, az0: int, rg0: int) -> None:
        """Binds the resampler to one footprint.

        Args:
            geocoder : Scene geocoder whose ``geocode(az, rg, height)`` returns longitude, latitude and ECEF positions.
            dem      : Terrain heights of the footprint in metres, shape (azimuth, range).
            az0      : Absolute azimuth index of the footprint's first row.
            rg0      : Absolute range index of the footprint's first column.
        """
        self.geocoder = geocoder
        self.dem      = np.asarray(dem, dtype=np.float64)
        self.az0      = int(az0)
        self.rg0      = int(rg0)

    def plan(self, cells_per_pixel: float, max_width: int) -> dict:
        """Chooses the cell count and the per-axis pixel stride for the footprint.

        The ground spacing of a pixel along each axis comes from geocoding the
        footprint's first pixel and its two neighbours at the median terrain
        height; the longer side of the north-up box around the four corners
        sets the cell size for the chosen width, and the stride is the number
        of pixels one cell covers along each axis.

        Args:
            cells_per_pixel : Cells laid per pixel of the finer axis along the longer side, before the width cap.
            max_width       : Cap on the cell count along the longer side.

        Returns:
            Dict with the ``width`` in cells along the longer side, clamped into [MIN_WIDTH, MAX_WIDTH], the ``step`` (azimuth, range) in pixels per cell, the ``cell`` size in metres and the ``spacing`` (azimuth, range) of one pixel in ground metres.
        """
        n_az, n_rg = self.dem.shape
        height     = float(np.nanmedian(self.dem))
        last_az    = self.az0 + n_az - 1
        last_rg    = self.rg0 + n_rg - 1

        az          = np.array([self.az0, self.az0 + 1, self.az0, self.az0, last_az, self.az0, last_az], dtype=np.int64)
        rg          = np.array([self.rg0, self.rg0, self.rg0 + 1, self.rg0, self.rg0, last_rg, last_rg], dtype=np.int64)
        lon, lat, _ = self.geocoder.geocode(az, rg, np.full(az.size, height))
        lon         = np.asarray(lon, dtype=np.float64)
        lat         = np.asarray(lat, dtype=np.float64)

        scale_lon, scale_lat = self._local_frame(lon[3:], lat[3:])
        x = lon * scale_lon
        y = lat * scale_lat

        spacing_az = max(float(math.hypot(x[1] - x[0], y[1] - y[0])), 1e-6)
        spacing_rg = max(float(math.hypot(x[2] - x[0], y[2] - y[0])), 1e-6)
        longer     = max(float(x[3:].max() - x[3:].min()), float(y[3:].max() - y[3:].min()), 1.0)

        width = int(np.clip(min(int(max_width), math.ceil(cells_per_pixel * longer / min(spacing_az, spacing_rg))), self.MIN_WIDTH, self.MAX_WIDTH))
        cell  = longer / max(width - 1, 1)
        step  = (max(1, math.ceil(cell / spacing_az - 1e-9)), max(1, math.ceil(cell / spacing_rg - 1e-9)))

        return {"width": width, "step": step, "cell": cell, "spacing": (spacing_az, spacing_rg)}

    def _geocoded_grid(self, step: tuple) -> tuple:
        """Geocodes every (azimuth stride, range stride)-th pixel with a finite terrain height.

        Args:
            step : Pixel stride of the geocoded lattice as (azimuth, range).

        Returns:
            Tuple of azimuth indices, range indices, longitudes and latitudes in degrees, the lattice row and column of every kept sample, each of shape (n,), and the lattice shape.

        Raises:
            ValueError : If no pixel of the lattice has a finite terrain height.
        """
        n_az, n_rg = self.dem.shape

        az_grid, rg_grid = np.meshgrid(np.arange(0, n_az, step[0]), np.arange(0, n_rg, step[1]), indexing="ij")
        rows, cols       = np.meshgrid(np.arange(az_grid.shape[0]), np.arange(az_grid.shape[1]), indexing="ij")
        shape            = az_grid.shape

        az_idx = az_grid.ravel()
        rg_idx = rg_grid.ravel()
        rows   = rows.ravel()
        cols   = cols.ravel()

        heights = self.dem[az_idx, rg_idx]
        keep    = np.isfinite(heights)
        if not keep.any():
            raise ValueError("No pixel of the footprint has a finite terrain height, so nothing can be geocoded")

        az_idx = az_idx[keep]
        rg_idx = rg_idx[keep]

        lon, lat, _ = self.geocoder.geocode(az_idx + self.az0, rg_idx + self.rg0, heights[keep])

        return az_idx, rg_idx, np.asarray(lon, dtype=np.float64), np.asarray(lat, dtype=np.float64), rows[keep], cols[keep], shape

    def _local_frame(self, lon: np.ndarray, lat: np.ndarray) -> tuple:
        """Returns the metres-per-degree scales of a local equirectangular frame around the footprint."""
        lat_mid = float(np.mean(lat))
        return self.METRES_PER_DEG_LON * math.cos(math.radians(lat_mid)), self.METRES_PER_DEG_LAT

    def _grid(self, lon: np.ndarray, lat: np.ndarray, width: int) -> tuple:
        """Lays a regular longitude/latitude grid of square ground cells over the geocoded samples.

        Args:
            lon   : Longitudes of the geocoded samples in degrees.
            lat   : Latitudes of the geocoded samples in degrees.
            width : Cell count along the longer ground side.

        Returns:
            Tuple of the cell-centre longitudes (W,), the cell-centre latitudes from north to south (H,), the cell size in metres and the rectangle [west, south, east, north] in degrees the grid spans; the outermost cell centres sit on the extreme samples, so the rectangle pads them by half a cell.
        """
        scale_lon, scale_lat = self._local_frame(lon, lat)

        extent_east  = (float(lon.max()) - float(lon.min())) * scale_lon
        extent_north = (float(lat.max()) - float(lat.min())) * scale_lat
        cell         = max(extent_east, extent_north, 1.0) / max(width - 1, 1)

        n_cols = int(math.ceil(extent_east / cell - 1e-9)) + 1
        n_rows = int(math.ceil(extent_north / cell - 1e-9)) + 1

        west  = float(lon.min()) - 0.5 * cell / scale_lon
        south = float(lat.min()) - 0.5 * cell / scale_lat
        east  = west + n_cols * cell / scale_lon
        north = south + n_rows * cell / scale_lat

        centre_lon = west + (np.arange(n_cols) + 0.5) * cell / scale_lon
        centre_lat = north - (np.arange(n_rows) + 0.5) * cell / scale_lat

        return centre_lon, centre_lat, cell, [west, south, east, north]

    def _spacing(self, points: np.ndarray, rows: np.ndarray, cols: np.ndarray, shape: tuple) -> float:
        """Returns the larger of the two per-axis sample spacings in metres.

        Each axis's spacing is the ``GAP_PERCENTILE`` of the distances between
        neighbouring samples along that axis of the strided lattice, so the
        range direction, whose ground step is several times the azimuth step on
        a side-looking radar, sets the gap tolerance.

        Args:
            points : Metric coordinates of the geocoded samples, shape (n, 2).
            rows   : Lattice row of every sample, shape (n,).
            cols   : Lattice column of every sample, shape (n,).
            shape  : Lattice shape as (rows, columns).

        Returns:
            Spacing in metres, 0.0 when no axis holds two finite neighbours.
        """
        lattice             = np.full(tuple(shape) + (2,), np.nan)
        lattice[rows, cols] = points
        spacing             = 0.0

        for axis in (0, 1):
            gaps   = np.linalg.norm(np.diff(lattice, axis=axis), axis=2)
            finite = gaps[np.isfinite(gaps)]
            if finite.size:
                spacing = max(spacing, float(np.percentile(finite, self.GAP_PERCENTILE)))

        return spacing

    def geometry(self, width: int, step: tuple) -> dict:
        """Builds the north-up lookup of the footprint: which pixel colours every cell and which cells lie inside.

        Args:
            width : Cell count along the longer ground side, clamped into [MIN_WIDTH, MAX_WIDTH].
            step  : Pixel stride of the geocoded lattice as (azimuth, range); cells take the colour of the nearest sample.

        Returns:
            Dict with the ``az`` and ``rg`` pixel indices (int32, one per inside cell), the ``inside`` mask over all cells in row-major order, the raster ``shape`` as (rows, columns), the ``rect`` [west, south, east, north] in degrees, the ``cell`` size and the gap ``tolerance`` in metres.

        Raises:
            ValueError : If no pixel of the footprint has a finite terrain height.
        """
        width = int(np.clip(int(width), self.MIN_WIDTH, self.MAX_WIDTH))
        step  = (max(1, int(step[0])), max(1, int(step[1])))

        az_idx, rg_idx, lon, lat, rows, cols, shape = self._geocoded_grid(step)
        centre_lon, centre_lat, cell, rect          = self._grid(lon, lat, width)
        scale_lon, scale_lat                        = self._local_frame(lon, lat)

        points    = np.column_stack([lon * scale_lon, lat * scale_lat])
        tolerance = self.GAP_FACTOR * max(self._spacing(points, rows, cols, shape), cell)

        grid_lon, grid_lat = np.meshgrid(centre_lon, centre_lat)
        queries            = np.column_stack([grid_lon.ravel() * scale_lon, grid_lat.ravel() * scale_lat])
        distance, nearest  = cKDTree(points).query(queries, distance_upper_bound=tolerance, workers=-1)
        inside             = np.isfinite(distance)

        return {
            "az"        : az_idx[nearest[inside]].astype(np.int32),
            "rg"        : rg_idx[nearest[inside]].astype(np.int32),
            "inside"    : inside,
            "shape"     : (int(centre_lat.size), int(centre_lon.size)),
            "rect"      : rect,
            "cell"      : cell,
            "tolerance" : tolerance,
        }

    def paint(self, image: np.ndarray, geometry: dict) -> np.ndarray:
        """Paints the image onto the north-up grid described by a lookup.

        Args:
            image    : Float colour image of shape (azimuth, range, 3) with values in [0, 1].
            geometry : Lookup returned by ``geometry`` for this footprint.

        Returns:
            RGBA uint8 array of shape (rows, columns, 4), north at the top, transparent outside the footprint.

        Raises:
            ValueError : If the image does not sit on the footprint's grid.
        """
        if image.shape[:2] != self.dem.shape or image.ndim != 3 or image.shape[2] != 3:
            raise ValueError(f"Image of shape {image.shape} does not sit on the footprint grid {self.dem.shape} with three colour channels")

        inside = geometry["inside"]
        colour = image[geometry["az"], geometry["rg"]]

        rgba            = np.zeros((inside.size, 4), dtype=np.uint8)
        rgba[inside, :3] = np.clip(np.round(colour * 255.0), 0, 255).astype(np.uint8)
        rgba[inside, 3]  = 255

        return rgba.reshape(geometry["shape"] + (4,))

    def render(self, image: np.ndarray, width: int, step: tuple) -> tuple:
        """Builds the lookup and paints the image in one go.

        Args:
            image : Float colour image of shape (azimuth, range, 3) with values in [0, 1].
            width : Cell count along the longer ground side, clamped into [MIN_WIDTH, MAX_WIDTH].
            step  : Pixel stride of the geocoded lattice as (azimuth, range).

        Returns:
            Tuple of the RGBA uint8 raster, north at the top and transparent outside the footprint, and the rectangle [west, south, east, north] in degrees it spans.
        """
        lookup = self.geometry(width, step)
        return self.paint(image, lookup), lookup["rect"]
