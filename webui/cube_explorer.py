"""Interactive server-side backend for the web UI cube explorer tabs.

Opens the raw tomogram cubes written by the preprocessing pipeline together
with their DEM and primary SLC amplitude, and renders slices, planes,
transects and geocoded point clouds as PNG or packed binary payloads. Cubes
are indexed by elevation bin, azimuth pixel and range pixel; elevation axes
are in metres and geocoded positions in ECEF metres.
"""

from __future__ import annotations

import io
import json
import math
import re
import threading
from datetime import datetime
from pathlib  import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from catalog_roots              import CatalogRoots, RunScanner
from lru_cache                  import LruCache
from tools.reporting.plotting   import PlotBase
from tools.sar.geocoding        import SceneGeocoder
from tools.sar.track_parameters import TrackParameters
from web_logger                 import WebLogger


class SliceFigureArchiver(PlotBase):
    """Renders publication-styled slice and transect figures to disk.

    Wraps the shared plotting base so every saved cut carries axis labels, an
    elevation axis in metres and a colourbar, using the paper style regardless of
    the style active elsewhere in the process.
    """

    LABELS = {
        "full" : "Capon full (raw)",
    }

    def render(self, data: np.ndarray, heights: np.ndarray, vmin: float, vmax: float, source: str, axis: str, az: int, rg: int, space: str, path: Path, cmap: str = "jet", label: str | None = None) -> Path:
        """Saves one elevation cut through the cube as a figure.

        Args:
            data: Cut of shape (elevation bins, samples along the free axis).
            heights: Elevation axis in metres, ascending, one entry per row of data.
            vmin: Lower colour limit.
            vmax: Upper colour limit.
            source: Cube key, one of the keys of LABELS.
            axis: "range" for a fixed range column, "azimuth" for a fixed azimuth row.
            az: Azimuth pixel index of the cut.
            rg: Range pixel index of the cut.
            space: "normalized" when columns were peak-normalised, else "physical".
            path: Destination PNG path.
            cmap: Matplotlib colormap name.
            label: Optional run label prefixed to the title.

        Returns:
            The path the figure was written to.
        """
        x_label   = "azimuth index" if axis == "range" else "range index"
        title_pos = f"range = {rg}" if axis == "range" else f"azimuth = {az}"
        cbar      = "intensity (per-column normalised)" if space == "normalized" else "intensity"
        extent    = [0, int(data.shape[1]), float(heights[0]), float(heights[-1])]
        title     = f"{self.LABELS[source]} — {title_pos}" if label is None else f"{label} — {self.LABELS[source]} — {title_pos}"

        previous = PlotBase.style
        PlotBase.use_style("paper")
        try:
            return self._imshow_figure(
                data,
                x_label        = x_label,
                y_label        = "elevation [m]",
                title          = title,
                cmap           = cmap,
                vmin           = vmin,
                vmax           = vmax,
                extent         = extent,
                origin         = "lower",
                colorbar_label = cbar,
                figsize        = self.figsize(self.FULL_WIDTH),
                path           = path,
            )
        finally:
            PlotBase.use_style(previous)

    def render_transect(self, data: np.ndarray, heights: np.ndarray, vmin: float, vmax: float, source: str, start: tuple, end: tuple, space: str, path: Path, cmap: str = "jet") -> Path:
        """Saves an elevation section sampled along an arbitrary azimuth-range line.

        Args:
            data: Cut of shape (elevation bins, samples along the transect).
            heights: Elevation axis in metres, ascending, one entry per row of data.
            vmin: Lower colour limit.
            vmax: Upper colour limit.
            source: Cube key, one of the keys of LABELS.
            start: (azimuth, range) pixel index where the transect begins.
            end: (azimuth, range) pixel index where the transect ends.
            space: "normalized" when columns were peak-normalised, else "physical".
            path: Destination PNG path.
            cmap: Matplotlib colormap name.

        Returns:
            The path the figure was written to.
        """
        cbar   = "intensity (per-column normalised)" if space == "normalized" else "intensity"
        extent = [0, int(data.shape[1]), float(heights[0]), float(heights[-1])]

        previous = PlotBase.style
        PlotBase.use_style("paper")
        try:
            return self._imshow_figure(
                data,
                x_label        = "sample along transect",
                y_label        = "elevation [m]",
                title          = f"{self.LABELS[source]} — transect az{start[0]},rg{start[1]} to az{end[0]},rg{end[1]}",
                cmap           = cmap,
                vmin           = vmin,
                vmax           = vmax,
                extent         = extent,
                origin         = "lower",
                colorbar_label = cbar,
                figsize        = self.figsize(self.FULL_WIDTH),
                path           = path,
            )
        finally:
            PlotBase.use_style(previous)


class StitchedRaw:
    """Lazy elevation-plane view over azimuth blocks belonging to different runs.

    Presents several per-block cubes as one array of shape (elevation, azimuth,
    range); a plane is materialised only when indexed, and azimuth rows no block
    covers stay NaN.

    Attributes:
        blocks: Pairs of (azimuth offset into the mosaic, per-block cube).
        shape: Shape of the stitched cube, (elevation, azimuth, range).
        dtype: Element type of the assembled planes.
    """

    def __init__(self, blocks: list, shape: tuple, dtype: np.dtype) -> None:
        """Stores the blocks and the shape of the mosaic they compose."""
        self.blocks = blocks
        self.shape  = shape
        self.dtype  = dtype

    @property
    def ndim(self) -> int:
        """Number of axes of the stitched cube."""
        return len(self.shape)

    def __getitem__(self, index: int) -> np.ndarray:
        """Returns elevation plane `index` of shape (azimuth, range), NaN in gaps."""
        plane = np.full(self.shape[1:], np.nan, dtype=self.dtype)
        for offset, raw in self.blocks:
            plane[offset:offset + raw.shape[1]] = np.asarray(raw[index])
        return plane


class StampReader:
    """Reads the artifacts of one preprocessing run directory.

    A preprocessing run directory holds ``data/dataset.json`` describing the
    global crop and artifact filenames, the artifact cubes under ``data`` and
    the run metadata under ``meta``.

    Attributes:
        run_dir: Directory of the preprocessing run.
        cached_layout: Parsed dataset layout, filled on first access.
    """

    def __init__(self, run_dir: Path) -> None:
        """Stores the preprocessing run directory to read from."""
        self.run_dir       = run_dir
        self.cached_layout = None

    @property
    def save_dir(self) -> Path:
        """Directory figures saved from this cube are written under."""
        return self.run_dir

    @property
    def where(self) -> str:
        """Human-readable location used in error messages."""
        return str(self.run_dir)

    def layout(self) -> dict:
        """Returns the parsed ``data/dataset.json`` layout of the run.

        Raises:
            FileNotFoundError: If the run holds no ``data/dataset.json``.
        """
        if self.cached_layout is not None:
            return self.cached_layout

        path = self.run_dir / "data" / "dataset.json"
        if not path.is_file():
            raise FileNotFoundError(f"dataset.json missing in {self.run_dir / 'data'}; rerun preprocessing to regenerate it")

        self.cached_layout = json.loads(path.read_text(encoding="utf-8"))
        return self.cached_layout

    def display(self) -> dict:
        """Returns the run and tomogram tag shown in the web UI."""
        return {"run": self.run_dir.name, "stamp": self.layout()["tomogram_tag"]}

    def global_crop(self) -> tuple[int, int, int, int]:
        """Returns the run's crop as (azimuth start, azimuth end, range start, range end)."""
        return tuple(int(v) for v in self.layout()["global_crop"])

    def artifact_path(self, key: str) -> Path | None:
        """Resolves one artifact of the run to an existing file.

        Args:
            key: Artifact key inside the layout's ``artifacts`` block.

        Returns:
            The artifact path, or None when the layout lists no such artifact or
            the file does not exist.
        """
        name = self.layout()["artifacts"].get(key)
        if not name:
            return None

        path = self.run_dir / "data" / name
        return path if path.is_file() else None

    def tomogram(self) -> np.ndarray:
        """Memory-maps the full tomogram cube of shape (elevation, azimuth, range).

        Raises:
            FileNotFoundError: If the run stores no full tomogram.
        """
        path = self.artifact_path("tomogram_full")
        if path is None:
            raise FileNotFoundError(f"tomogram_full missing in {self.run_dir / 'data'}; rerun preprocessing to regenerate it")

        return np.load(path, mmap_mode="r")

    def dem(self) -> np.ndarray | None:
        """Memory-maps the full DEM of shape (azimuth, range), or None when absent."""
        path = self.artifact_path("dem_full")
        if path is None:
            return None

        return np.load(path, mmap_mode="r")

    def primary(self) -> np.ndarray:
        """Memory-maps the primary SLC image of shape (azimuth, range).

        Raises:
            FileNotFoundError: If the run stores no primary SLC.
        """
        path = self.artifact_path("primary")
        if path is None:
            raise FileNotFoundError(f"primary SLC missing in {self.run_dir / 'data'}; rerun preprocessing to regenerate it")

        return np.load(path, mmap_mode="r")

    def height_range(self) -> tuple[float, float]:
        """Returns the tomogram's elevation axis extent in metres.

        Raises:
            FileNotFoundError: If the run holds no ``meta/config_state.json``.
        """
        path = self.run_dir / "meta" / "config_state.json"
        if not path.is_file():
            raise FileNotFoundError(f"config_state.json missing in {self.run_dir / 'meta'}; rerun preprocessing to regenerate it")

        state = json.loads(path.read_text(encoding="utf-8"))
        low, high = state["tomogram_config"]["height_range"]
        return float(low), float(high)

    def track_parameters(self) -> TrackParameters | None:
        """Loads the run's track parameters, or None when the file is absent."""
        path = self.run_dir / "meta" / TrackParameters.FILENAME
        if not path.is_file():
            return None

        return TrackParameters.load(path)


class CubeExplorer:
    """Loads one preprocessing run at a time and serves views of it to the web UI.

    Holds a single loaded cube in memory behind a lock: the raw tomogram, the
    primary SLC amplitude map in dB, the DEM and the geocoding context. Loading
    runs in a background thread whose progress is polled through ``load_status``.

    Attributes:
        logger: Web logger for load and save reporting.
        archiver: Renderer used when slices are saved to disk.
        roots: Catalogued run roots that bound which cube ids may be opened.
        scanner: Scanner listing preprocessing runs under a root.
        lock: Guards the loaded cube and the load status.
        loaded: Currently loaded cube state, or None.
        status: Load state machine payload polled by the front end.
    """

    SOURCES             = ("full",)
    CLOUD_CURVE_SOURCES = ("full",)
    GLOBE_SOURCES       = ("full",)

    CMAPS = ("jet", "viridis", "inferno", "turbo", "gray")

    def __init__(self, logger: WebLogger) -> None:
        """Builds the explorer with an idle load status and no cube loaded."""
        self.logger   = logger
        self.archiver = SliceFigureArchiver()
        self.roots    = CatalogRoots()
        self.scanner  = RunScanner(self.roots)
        self.lock     = threading.Lock()
        self.loaded   = None
        self.status   = {"state": "idle", "id": None, "progress": 0.0, "stage": "", "error": ""}

    def list_cubes(self, base: str) -> dict:
        """Lists the preprocessing runs available under a runs root.

        Args:
            base: Runs root to scan.

        Returns:
            Dict with ``ok``, the resolved ``root`` and the ``cubes`` catalogue.
        """
        scanned = self.scanner.stamps(base)
        if not scanned["ok"]:
            return {"ok": False, "error": scanned["error"], "cubes": []}

        return {"ok": True, "root": scanned["root"], "cubes": scanned["entries"]}

    def start_load(self, cube_id: str) -> dict:
        """Starts loading a cube in a background thread.

        Args:
            cube_id: Preprocessing run directory path.

        Returns:
            Dict with ``ok`` True once the load was started or the cube is already
            loaded, otherwise ``ok`` False with the reason.
        """
        reader = self._open_source(cube_id)
        if reader is None:
            return {"ok": False, "error": f"unknown cube id: {cube_id}"}

        with self.lock:
            if self.status["state"] == "loading":
                return {"ok": False, "error": f"a load is already running for {self.status['id']}"}
            if self.status["state"] == "ready" and self.status["id"] == cube_id and self.loaded is not None:
                return {"ok": True}

            self.loaded = None
            self.status = {"state": "loading", "id": cube_id, "progress": 0.0, "stage": "scanning sources", "error": ""}

        threading.Thread(target=self._load_worker, args=(cube_id, reader), daemon=True).start()
        return {"ok": True}

    def load_status(self) -> dict:
        """Returns the current load state, with the cube metadata once ready."""
        with self.lock:
            payload = dict(self.status)
            if payload["state"] == "ready" and self.loaded is not None:
                payload["cube"] = self.loaded["meta"]
        return payload

    def primary_png(self, cube_id: str) -> bytes | None:
        """Renders the primary SLC amplitude map in dB as a greyscale PNG.

        Args:
            cube_id: Id of the loaded cube.

        Returns:
            PNG bytes of the (azimuth, range) map, or None when that cube is not
            the loaded one.
        """
        with self.lock:
            if self.loaded is None or self.loaded["id"] != cube_id:
                return None
            primary    = self.loaded["primary"]
            vmin, vmax = self.loaded["primary_clim"]

        buf = io.BytesIO()
        plt.imsave(buf, primary, cmap="gray", vmin=float(vmin), vmax=float(vmax), format="png")
        return buf.getvalue()

    def profiles(self, cube_id: str, az: int, rg: int) -> dict:
        """Returns the elevation profile of every source at one pixel.

        Args:
            cube_id: Id of the loaded cube.
            az: Azimuth pixel index, clipped into range.
            rg: Range pixel index, clipped into range.

        Returns:
            Dict with ``ok``, the clipped ``az`` and ``rg`` and a ``sources`` map
            from source name to ascending ``heights`` in metres and ``values``.
        """
        with self.lock:
            if self.loaded is None or self.loaded["id"] != cube_id:
                return {"ok": False, "error": "cube not loaded"}
            entries = self.loaded["entries"]
            meta    = self.loaded["meta"]

        az = int(np.clip(az, 0, meta["n_az"] - 1))
        rg = int(np.clip(rg, 0, meta["n_rg"] - 1))

        sources = {}
        for source, entry in entries.items():
            order   = np.argsort(entry["x_axis"])
            heights = np.asarray(entry["x_axis"])[order]
            values  = entry["cube"][:, az, rg][order]
            sources[source] = {"heights": heights.tolist(), "values": values.astype(float).tolist()}

        return {"ok": True, "az": az, "rg": rg, "sources": sources}

    def slice_png(self, cube_id: str, source: str, axis: str, az: int, rg: int, space: str = "physical", cmap: str = "jet") -> bytes | None:
        """Renders one elevation slice of a source as a PNG.

        Args:
            cube_id: Id of the loaded cube.
            source: Cube key to render.
            axis: "range" for a fixed range column, "azimuth" for a fixed azimuth row.
            az: Azimuth pixel index, clipped into range.
            rg: Range pixel index, clipped into range.
            space: "normalized" to peak-normalise columns, else "physical".
            cmap: Colormap name; diverging sources always use coolwarm.

        Returns:
            PNG bytes, or None when the cube is not loaded or the axis is unknown.
        """
        entry = self._entry(cube_id, source)
        if entry is None or axis not in ("range", "azimuth"):
            return None

        n_elev, n_az, n_rg = entry["cube"].shape
        az = int(np.clip(az, 0, n_az - 1))
        rg = int(np.clip(rg, 0, n_rg - 1))

        data, heights, vmin, vmax = self._cut(entry, axis, az, rg, space)

        buf = io.BytesIO()
        plt.imsave(buf, np.flipud(data), cmap=self._entry_cmap(entry, cmap), vmin=vmin, vmax=vmax, format="png")
        return buf.getvalue()

    def plane_png(self, cube_id: str, source: str, frac: float, space: str = "physical", cmap: str = "jet") -> bytes | None:
        """Renders one horizontal elevation plane of a source as a PNG.

        Args:
            cube_id: Id of the loaded cube.
            source: Cube key to render.
            frac: Position along the ascending elevation axis, 0 at the bottom bin
                and 1 at the top.
            space: "normalized" to scale the plane by its peak, else "physical".
            cmap: Colormap name; diverging sources always use coolwarm.

        Returns:
            PNG bytes of the (azimuth, range) plane, or None when the cube is not
            loaded or carries no such source.
        """
        entry = self._entry(cube_id, source)
        if entry is None:
            return None

        cube   = entry["cube"]
        n_elev = cube.shape[0]
        order  = np.argsort(entry["x_axis"])
        pos    = int(round(float(np.clip(frac, 0.0, 1.0)) * (n_elev - 1)))
        elev   = int(order[pos])

        data = np.asarray(cube[elev], dtype=np.float32)

        if space == "normalized":
            if entry.get("diverging"):
                peak = float(np.nanmax(np.abs(data))) if np.isfinite(data).any() else 0.0
                data = data / (peak if peak > 1e-12 else 1.0)
                vmin, vmax = -1.0, 1.0
            else:
                peak = float(np.nanmax(data)) if np.isfinite(data).any() else 0.0
                data = data / (peak if peak > 1e-12 else 1.0)
                vmin, vmax = 0.0, 1.0
        else:
            vmin, vmax = entry["vmin"], entry["vmax"]

        buf = io.BytesIO()
        plt.imsave(buf, np.nan_to_num(data, nan=vmin), cmap=self._entry_cmap(entry, cmap), vmin=vmin, vmax=vmax, format="png")
        return buf.getvalue()

    def cbar_png(self, cmap: str) -> bytes | None:
        """Renders a horizontal 256-step colour ramp for one of the allowed colormaps.

        Args:
            cmap: Colormap name.

        Returns:
            PNG bytes of the ramp, or None when the colormap is not allowed.
        """
        if cmap not in ("viridis", "inferno", "coolwarm", "jet", "gray"):
            return None

        ramp = np.tile(np.linspace(0.0, 1.0, 256), (12, 1))

        buf = io.BytesIO()
        plt.imsave(buf, ramp, cmap=cmap, vmin=0.0, vmax=1.0, format="png")
        return buf.getvalue()

    def points_bin(self, cube_id: str, source: str, amp_min: float, max_points: int) -> bytes | None:
        """Packs a scatterer point cloud in radar coordinates as a binary blob.

        Args:
            cube_id: Id of the loaded cube.
            source: Curve source to draw voxels from, restricted to
                CLOUD_CURVE_SOURCES.
            amp_min: Minimum amplitude a point must carry to be emitted.
            max_points: Cap on emitted points; 0 or less emits all of them.

        Returns:
            A four-float32 header (emitted count, total count, 0, 0) followed by
            rows of (azimuth index, range index, elevation in metres, amplitude),
            or None when the cube or source is unavailable.
        """
        resolved = self._point_rows(cube_id, source, amp_min, max_points)
        if resolved is None:
            return None

        rows, total = resolved
        return self._points_blob(rows, total)

    def _point_rows(self, cube_id: str, source: str, amp_min: float, max_points: int) -> tuple[np.ndarray, int] | None:
        """Returns the (rows, total) point cloud of a curve source."""
        if source not in self.CLOUD_CURVE_SOURCES:
            return None

        entry = self._entry(cube_id, source)
        return None if entry is None else self._curve_rows(entry, amp_min, max_points)

    @classmethod
    def _curve_rows(cls, entry: dict, amp_min: float, max_points: int) -> tuple[np.ndarray, int]:
        """Extracts one point per bright voxel of a curve cube.

        Args:
            entry: Loaded cube entry whose cube has shape (elevation, azimuth, range).
            amp_min: Minimum voxel intensity for a point to be kept.
            max_points: Cap on emitted points, applied by even subsampling across
                the elevation-major ordering.

        Returns:
            Tuple of a float32 array of shape (points, 4) holding azimuth index,
            range index, elevation in metres and intensity, and the unsubsampled
            count.
        """
        cube   = entry["cube"]
        x_axis = np.asarray(entry["x_axis"], dtype=np.float32)
        n_rg   = cube.shape[2]

        masks  = [np.isfinite(plane) & (plane >= amp_min) for plane in cube]
        counts = np.array([int(mask.sum()) for mask in masks], dtype=np.int64)
        total  = int(counts.sum())
        starts = np.concatenate([[0], np.cumsum(counts)])

        n_keep = min(total, max_points) if max_points > 0 else total
        picks  = np.linspace(0, total - 1, n_keep).astype(np.int64) if total else np.empty(0, dtype=np.int64)

        chunks = []
        for k, plane in enumerate(cube):
            lo, hi = np.searchsorted(picks, [starts[k], starts[k + 1]])
            if lo == hi:
                continue

            hits = np.flatnonzero(masks[k])[picks[lo:hi] - starts[k]]
            vals = plane.ravel()[hits]

            chunks.append(np.stack([
                (hits // n_rg).astype(np.float32),
                (hits %  n_rg).astype(np.float32),
                np.full(hits.size, x_axis[k], dtype=np.float32),
                vals.astype(np.float32),
            ], axis=1))

        rows = np.concatenate(chunks, axis=0) if chunks else np.zeros((0, 4), dtype=np.float32)
        return rows, total

    @staticmethod
    def _points_blob(rows: np.ndarray, total: int) -> bytes:
        """Serialises point rows behind a four-float32 count header."""
        header = np.array([rows.shape[0], total, 0.0, 0.0], dtype=np.float32)
        return header.tobytes() + np.ascontiguousarray(rows).tobytes()

    def dem_grid_bin(self, cube_id: str) -> bytes | None:
        """Packs the DEM as a median-referenced height grid.

        Args:
            cube_id: Id of the loaded cube.

        Returns:
            A four-float32 header (azimuth rows, range columns, median height in
            metres, 0) followed by the float32 grid of heights relative to that
            median, or None when the cube is not loaded or carries no DEM.
        """
        with self.lock:
            if self.loaded is None or self.loaded["id"] != cube_id:
                return None
            dem = self.loaded["dem"]

        if dem is None:
            return None

        finite = np.isfinite(dem)
        median = float(np.median(dem[finite])) if finite.any() else 0.0
        grid   = (dem - median).astype(np.float32)

        header = np.array([dem.shape[0], dem.shape[1], median, 0.0], dtype=np.float32)
        return header.tobytes() + np.ascontiguousarray(grid).tobytes()

    def globe_points_bin(self, cube_id: str, source: str, amp_min: float, max_points: int) -> bytes | None:
        """Packs a geocoded point cloud as ECEF offsets from the scene anchor.

        Scatterer elevations are added to the DEM terrain height at their pixel
        before geocoding, so points sit above ground on the globe.

        Args:
            cube_id: Id of the loaded cube.
            source: Source to draw points from, restricted to GLOBE_SOURCES.
            amp_min: Minimum amplitude for a point to be kept.
            max_points: Cap on emitted points before the terrain mask is applied.

        Returns:
            A four-float32 header (emitted count, pre-mask total, 0, 0) followed by
            rows of (ECEF x, y, z offsets in metres, elevation in metres,
            amplitude), or None when the cube has no geocoding or the source is
            not globe-renderable.
        """
        with self.lock:
            if self.loaded is None or self.loaded["id"] != cube_id:
                return None
            geo = self.loaded["geo"]

        if geo is None or source not in self.GLOBE_SOURCES:
            return None

        resolved = self._point_rows(cube_id, source, amp_min, max_points)
        if resolved is None:
            return None

        rows, total = resolved
        az_idx      = rows[:, 0].astype(np.int64)
        rg_idx      = rows[:, 1].astype(np.int64)

        terrain = geo["dem"][az_idx, rg_idx]
        keep    = np.isfinite(terrain)

        az_idx  = az_idx[keep]
        rg_idx  = rg_idx[keep]
        rows    = rows[keep]
        heights = terrain[keep].astype(np.float64) + rows[:, 2].astype(np.float64)

        _, _, ecef = geo["geocoder"].geocode(az_idx + geo["az0"], rg_idx + geo["rg0"], heights)
        offsets    = (ecef - geo["anchor_ecef"][None, :]).astype(np.float32)

        globe_rows = np.concatenate([offsets, rows[:, 2:3], rows[:, 3:4]], axis=1)
        header     = np.array([globe_rows.shape[0], total, 0.0, 0.0], dtype=np.float32)
        return header.tobytes() + np.ascontiguousarray(globe_rows).tobytes()

    def transect_png(self, cube_id: str, source: str, az0: int, rg0: int, az1: int, rg1: int, space: str = "physical", cmap: str = "jet") -> bytes | None:
        """Renders an elevation section along an arbitrary line as a PNG.

        Args:
            cube_id: Id of the loaded cube.
            source: Cube key to render.
            az0: Azimuth pixel index of the start point.
            rg0: Range pixel index of the start point.
            az1: Azimuth pixel index of the end point.
            rg1: Range pixel index of the end point.
            space: "normalized" to peak-normalise columns, else "physical".
            cmap: Colormap name; diverging sources always use coolwarm.

        Returns:
            PNG bytes, or None when the cube carries no such source.
        """
        entry = self._entry(cube_id, source)
        if entry is None:
            return None

        data, heights, vmin, vmax = self._transect_cut(entry, az0, rg0, az1, rg1, space)

        buf = io.BytesIO()
        plt.imsave(buf, np.flipud(data), cmap=self._entry_cmap(entry, cmap), vmin=vmin, vmax=vmax, format="png")
        return buf.getvalue()

    def save_transect(self, cube_id: str, az0: int, rg0: int, az1: int, rg1: int, space: str = "physical", cmap: str = "jet") -> dict:
        """Saves one transect figure per loaded source under the run's figures folder.

        Args:
            cube_id: Id of the loaded cube.
            az0: Azimuth pixel index of the start point, clipped into range.
            rg0: Range pixel index of the start point, clipped into range.
            az1: Azimuth pixel index of the end point, clipped into range.
            rg1: Range pixel index of the end point, clipped into range.
            space: "physical" or "normalized".
            cmap: Colormap name; diverging sources always use coolwarm.

        Returns:
            Dict with ``ok``, the absolute output ``dir``, its path ``rel`` to the
            run and the written ``files``, or ``ok`` False with the reason.
        """
        with self.lock:
            if self.loaded is None or self.loaded["id"] != cube_id:
                return {"ok": False, "error": "cube not loaded"}
            entries = self.loaded["entries"]
            meta    = self.loaded["meta"]

        reader = self._open_source(cube_id)
        if reader is None:
            return {"ok": False, "error": f"unknown cube id: {cube_id}"}
        if space not in ("physical", "normalized"):
            return {"ok": False, "error": f"unknown space: {space}"}

        az0 = int(np.clip(az0, 0, meta["n_az"] - 1))
        az1 = int(np.clip(az1, 0, meta["n_az"] - 1))
        rg0 = int(np.clip(rg0, 0, meta["n_rg"] - 1))
        rg1 = int(np.clip(rg1, 0, meta["n_rg"] - 1))

        rel     = Path("figures") / "cube_transects" / f"az{az0:04d}_rg{rg0:04d}_to_az{az1:04d}_rg{rg1:04d}"
        out_dir = reader.save_dir / rel

        files = []
        for source in meta["sources"]:
            entry = entries[source]
            data, heights, vmin, vmax = self._transect_cut(entry, az0, rg0, az1, rg1, space)
            saved = self.archiver.render_transect(data, heights, vmin, vmax, source, (az0, rg0), (az1, rg1), space, out_dir / f"transect_{source}_{space}.png", cmap=self._entry_cmap(entry, cmap))
            files.append(saved.name)

        self.logger.ok(f"saved {len(files)} transect figures to {out_dir}")
        return {"ok": True, "dir": str(out_dir), "rel": str(rel), "files": files}

    @classmethod
    def _transect_cut(cls, entry: dict, az0: int, rg0: int, az1: int, rg1: int, space: str) -> tuple[np.ndarray, np.ndarray, float, float]:
        """Samples the cube along a straight azimuth-range line.

        The line is sampled at one point per pixel of its longer axis, with
        nearest-neighbour rounding of the indices.

        Args:
            entry: Loaded cube entry.
            az0: Azimuth pixel index of the start point, clipped into range.
            rg0: Range pixel index of the start point, clipped into range.
            az1: Azimuth pixel index of the end point, clipped into range.
            rg1: Range pixel index of the end point, clipped into range.
            space: "normalized" to peak-normalise columns, else "physical".

        Returns:
            Tuple of the section of shape (elevation bins, samples) ordered by
            ascending elevation, the elevation axis in metres, and the colour
            limits.
        """
        cube               = entry["cube"]
        n_elev, n_az, n_rg = cube.shape

        az0 = int(np.clip(az0, 0, n_az - 1))
        az1 = int(np.clip(az1, 0, n_az - 1))
        rg0 = int(np.clip(rg0, 0, n_rg - 1))
        rg1 = int(np.clip(rg1, 0, n_rg - 1))

        samples = int(max(abs(az1 - az0), abs(rg1 - rg0))) + 1
        az_idx  = np.round(np.linspace(az0, az1, samples)).astype(int)
        rg_idx  = np.round(np.linspace(rg0, rg1, samples)).astype(int)
        data    = cube[:, az_idx, rg_idx]

        data, vmin, vmax = cls._normalize_cut(entry, data, space)

        order   = np.argsort(entry["x_axis"])
        heights = np.asarray(entry["x_axis"], dtype=np.float64)[order]
        return data[order], heights, float(vmin), float(vmax)

    def save_slices(self, cube_id: str, az: int, rg: int, space: str = "physical", cmap: str = "jet") -> dict:
        """Saves the range and azimuth slice of every loaded source at one pixel.

        Args:
            cube_id: Id of the loaded cube.
            az: Azimuth pixel index, clipped into range.
            rg: Range pixel index, clipped into range.
            space: "physical" or "normalized".
            cmap: Colormap name; diverging sources always use coolwarm.

        Returns:
            Dict with ``ok``, the absolute output ``dir``, its path ``rel`` to the
            run, the clipped indices and the written ``files``, or ``ok`` False
            with the reason.
        """
        with self.lock:
            if self.loaded is None or self.loaded["id"] != cube_id:
                return {"ok": False, "error": "cube not loaded"}
            entries = self.loaded["entries"]
            meta    = self.loaded["meta"]

        reader = self._open_source(cube_id)
        if reader is None:
            return {"ok": False, "error": f"unknown cube id: {cube_id}"}
        if space not in ("physical", "normalized"):
            return {"ok": False, "error": f"unknown space: {space}"}

        az = int(np.clip(az, 0, meta["n_az"] - 1))
        rg = int(np.clip(rg, 0, meta["n_rg"] - 1))

        rel     = Path("figures") / "cube_slices" / f"az{az:04d}_rg{rg:04d}"
        out_dir = reader.save_dir / rel

        files = []
        for source in meta["sources"]:
            for axis in ("range", "azimuth"):
                data, heights, vmin, vmax = self._cut(entries[source], axis, az, rg, space)
                saved = self.archiver.render(data, heights, vmin, vmax, source, axis, az, rg, space, out_dir / f"{axis}_{source}_{space}.png", cmap=self._entry_cmap(entries[source], cmap))
                files.append(saved.name)

        self.logger.ok(f"saved {len(files)} slice figures to {out_dir}")
        return {"ok": True, "dir": str(out_dir), "rel": str(rel), "az": az, "rg": rg, "files": files}

    @classmethod
    def _cut(cls, entry: dict, axis: str, az: int, rg: int, space: str) -> tuple[np.ndarray, np.ndarray, float, float]:
        """Extracts one elevation slice from a loaded cube entry.

        Args:
            entry: Loaded cube entry.
            axis: "range" for a fixed range column, "azimuth" for a fixed azimuth row.
            az: Azimuth pixel index used by the azimuth cut.
            rg: Range pixel index used by the range cut.
            space: "normalized" to peak-normalise columns, else "physical".

        Returns:
            Tuple of the slice of shape (elevation bins, samples) ordered by
            ascending elevation, the elevation axis in metres, and the colour
            limits.
        """
        cube = entry["cube"]
        data = cube[:, :, rg] if axis == "range" else cube[:, az, :]

        data, vmin, vmax = cls._normalize_cut(entry, data, space)

        order   = np.argsort(entry["x_axis"])
        heights = np.asarray(entry["x_axis"], dtype=np.float64)[order]
        return data[order], heights, float(vmin), float(vmax)

    @staticmethod
    def _normalize_cut(entry: dict, data: np.ndarray, space: str) -> tuple[np.ndarray, float, float]:
        """Peak-normalises each column of a cut when normalised space is requested.

        Args:
            entry: Loaded cube entry, whose ``diverging`` flag selects symmetric limits.
            data: Cut of shape (elevation bins, samples).
            space: "normalized" to normalise, anything else to pass through.

        Returns:
            Tuple of the cut and its colour limits: the entry's own limits in
            physical space, (0, 1) normalised, or (-1, 1) for diverging sources.
        """
        if space != "normalized":
            return data, entry["vmin"], entry["vmax"]

        peak = np.abs(data).max(axis=0, keepdims=True) if entry.get("diverging") else data.max(axis=0, keepdims=True)
        safe = np.where(peak > 1e-12, peak, 1.0)
        data = (data / safe).astype(np.float32)
        vmin, vmax = (-1.0, 1.0) if entry.get("diverging") else (0.0, 1.0)
        return data, vmin, vmax

    @classmethod
    def _entry_cmap(cls, entry: dict, cmap: str = "jet") -> str:
        """Returns coolwarm for diverging entries, else the requested allowed colormap."""
        if entry.get("diverging"):
            return "coolwarm"
        return cmap if cmap in cls.CMAPS else "jet"

    def _entry(self, cube_id: str, source: str) -> dict | None:
        """Returns the loaded entry of one source, or None when unavailable."""
        with self.lock:
            if self.loaded is None or self.loaded["id"] != cube_id:
                return None
            return self.loaded["entries"].get(source)

    def _open_source(self, cube_id: str) -> StampReader | None:
        """Resolves a cube id to a preprocessing run reader.

        Args:
            cube_id: Preprocessing run directory path.

        Returns:
            A StampReader for run directories that hold ``data/dataset.json``, or
            None when the id is unknown or falls outside the catalogued roots.
        """
        if not cube_id:
            return None

        run_dir = Path(cube_id).resolve()
        if not self.roots.contains(run_dir):
            return None
        if not (run_dir / "data" / "dataset.json").is_file():
            return None
        return StampReader(run_dir)

    def _load_worker(self, cube_id: str, reader: StampReader) -> None:
        """Loads a cube in the background and publishes the ready or error status.

        Args:
            cube_id: Id being loaded.
            reader: Reader opened for that id.
        """
        try:
            entries, meta, primary, dem, geo = self._load_all(reader)
            clim = tuple(float(v) for v in np.percentile(primary, [1.0, 99.0]))

            with self.lock:
                self.loaded = {"id": cube_id, "entries": entries, "meta": meta, "primary": primary, "primary_clim": clim, "dem": dem, "geo": geo}
                self.status = {"state": "ready", "id": cube_id, "progress": 1.0, "stage": "ready", "error": ""}

            self.logger.muted(f"cube ready: {cube_id} sources={meta['sources']}")
        except Exception as exc:
            with self.lock:
                self.loaded = None
                self.status = {"state": "error", "id": cube_id, "progress": 0.0, "stage": "", "error": str(exc)}

            self.logger.error(f"cube load failed: {cube_id}: {exc}")

    def _load_all(self, reader: StampReader) -> tuple[dict, dict, np.ndarray, np.ndarray | None, dict | None]:
        """Reads the tomogram, maps and geometry artifacts of one preprocessing run.

        Args:
            reader: Preprocessing run reader to pull from.

        Returns:
            Tuple of the per-source entries, the front-end metadata payload, the
            primary amplitude map in dB of shape (azimuth, range), the DEM in
            metres and the geocoding context; the last two are None when the
            scene cannot be geolocated.

        Raises:
            ValueError: If the tomogram is not three-dimensional or its footprint
                disagrees with the recorded global crop.
        """
        full_raw = reader.tomogram()
        if full_raw.ndim != 3:
            raise ValueError(f"full tomogram is not a 3D cube: shape={full_raw.shape}")

        n_elev, n_az, n_rg = full_raw.shape

        az_lo, az_hi, rg_lo, rg_hi = reader.global_crop()
        if (az_hi - az_lo, rg_hi - rg_lo) != (n_az, n_rg):
            raise ValueError(f"global_crop {[az_lo, az_hi, rg_lo, rg_hi]} does not match the {n_az}x{n_rg} tomogram footprint")

        x_axis = self._elevation_axis(reader, n_elev)

        total = n_elev
        done  = [0]

        def advance(source: str) -> None:
            """Records one more ingested elevation plane in the load status."""
            done[0] += 1
            with self.lock:
                self.status["progress"] = done[0] / total
                self.status["stage"]    = source

        entries = {"full": self._ingest(full_raw, x_axis, lambda: advance("full"))}

        primary = self._primary_db(reader, n_az, n_rg)
        dem     = self._load_dem(reader, n_az, n_rg)
        geo     = self._load_geo(reader, dem, n_az, n_rg)

        meta = {
            "sources"   : [s for s in self.SOURCES if s in entries],
            "n_az"      : n_az,
            "n_rg"      : n_rg,
            "n_elev"    : {s: int(entries[s]["cube"].shape[0]) for s in entries},
            "x_min"     : float(x_axis[0]),
            "x_max"     : float(x_axis[-1]),
            "intensity" : {s: [entries[s]["vmin"], entries[s]["vmax"]] for s in entries},
            "dem"       : dem is not None,
            "spacing"   : self._load_spacing(reader),
            "globe"     : self._globe_meta(geo),
        }
        return entries, meta, primary, dem, geo

    def _load_spacing(self, reader: StampReader) -> dict | None:
        """Returns the reference track's azimuth and range pixel spacing in metres.

        Args:
            reader: Preprocessing run reader.

        Returns:
            Dict with ``az`` and ``rg`` spacings, or None when the run stores no
            track parameters.
        """
        params = reader.track_parameters()
        if params is None:
            return None

        reference = params.parameters[0]
        return {"az": float(reference["ps_az"]), "rg": float(reference["ps_rg"])}

    def _load_dem(self, reader: StampReader, n_az: int, n_rg: int) -> np.ndarray | None:
        """Loads the preprocessing DEM matching the tomogram footprint.

        Args:
            reader: Preprocessing run reader.
            n_az: Azimuth extent of the cube, in pixels.
            n_rg: Range extent of the cube, in pixels.

        Returns:
            Float32 terrain heights in metres of shape (n_az, n_rg), or None when
            the run publishes no full DEM.

        Raises:
            ValueError: If the stored DEM does not match the tomogram footprint.
        """
        raw = reader.dem()
        if raw is None:
            return None

        if raw.ndim != 2 or raw.shape != (n_az, n_rg):
            raise ValueError(f"dem_full shape {raw.shape} does not match the {n_az}x{n_rg} tomogram footprint")

        return np.asarray(raw, dtype=np.float32)

    def _load_geo(self, reader: StampReader, dem: np.ndarray | None, n_az: int, n_rg: int) -> dict | None:
        """Builds the geocoding context used by the globe view.

        Args:
            reader: Preprocessing run reader.
            dem: DEM in metres, or None to skip geocoding entirely.
            n_az: Azimuth extent of the cube, in pixels.
            n_rg: Range extent of the cube, in pixels.

        Returns:
            Dict with the scene geocoder, the cube's azimuth and range origins in
            full-scene pixels, the DEM, the median terrain height in metres, the
            ECEF anchor of the scene centre, the lon/lat bounding box, the flight
            lines when the run records its pass labels, and the beam segment;
            None when the track parameters lack the geocoding keys or the DEM
            holds no finite height.
        """
        if dem is None:
            return None

        params = reader.track_parameters()
        if params is None:
            return None

        reference = params.parameters[0]
        if any(key not in reference for key in SceneGeocoder.REQUIRED_KEYS):
            return None

        finite = np.isfinite(dem)
        if not finite.any():
            return None

        geocoder    = SceneGeocoder(reference)
        base_height = float(np.median(dem[finite]))

        az_start, _, rg_start, _ = reader.global_crop()
        pass_labels              = reader.layout()["pass_labels"]

        _, _, anchor = geocoder.geocode([az_start + n_az / 2], [rg_start + n_rg / 2], [base_height])

        corner_az   = np.array([az_start, az_start, az_start + n_az, az_start + n_az], dtype=np.float64)
        corner_rg   = np.array([rg_start, rg_start + n_rg, rg_start, rg_start + n_rg], dtype=np.float64)
        lon, lat, _ = geocoder.geocode(corner_az, corner_rg, np.full(4, base_height))

        return {
            "geocoder"    : geocoder,
            "az0"         : az_start,
            "rg0"         : rg_start,
            "dem"         : dem,
            "base_height" : base_height,
            "anchor_ecef" : anchor[0],
            "bbox"        : [float(lon.min()), float(lat.min()), float(lon.max()), float(lat.max())],
            "tracks"      : self._track_lines(params, pass_labels, az_start, n_az) if pass_labels is not None else None,
            "beam"        : self._beam_segment(geocoder, reference, dem, base_height, az_start, rg_start, n_az, n_rg),
        }

    TRACK_LINE_POINTS = 17

    def _track_lines(self, params: TrackParameters, labels: list, az_start: int, n_az: int) -> dict:
        """Geocodes the flight line of every pass of the run.

        Args:
            params: Track parameters of the whole stack.
            labels: Pass labels recorded by the run, primary first.
            az_start: Azimuth origin of the cube in full-scene pixels.
            n_az: Azimuth extent of the cube, in pixels.

        Returns:
            Dict with the ``labels``, the ``reference`` track, one ECEF polyline
            per track sampled at TRACK_LINE_POINTS positions, and the ``h0``
            flight altitudes in metres.

        Raises:
            ValueError: If a recorded pass is absent from the track parameters.
        """
        labels    = list(labels)
        reference = params.reference

        by_label = dict(zip(params.labels, params.parameters))
        missing  = [label for label in labels if label not in by_label]
        if missing:
            raise ValueError(f"run passes {missing} are absent from track_parameters.json labels {params.labels}")

        az_grid = np.linspace(az_start, az_start + n_az, self.TRACK_LINE_POINTS)

        lines = []
        for label in labels:
            track      = by_label[label]
            _, _, ecef = SceneGeocoder(track).geocode_track(az_grid, np.full(az_grid.shape, float(track["h0"])))
            lines.append(ecef)

        return {
            "labels"    : labels,
            "reference" : reference,
            "lines"     : lines,
            "h0"        : [float(by_label[label]["h0"]) for label in labels],
        }

    def _beam_segment(self, geocoder: SceneGeocoder, reference: dict, dem: np.ndarray, base_height: float, az_start: int, rg_start: int, n_az: int, n_rg: int) -> dict:
        """Builds the radar beam triangle drawn on the globe.

        Args:
            geocoder: Geocoder of the reference track.
            reference: Reference track parameters, carrying its ``h0`` in metres.
            dem: DEM in metres.
            base_height: Median terrain height in metres, used where the DEM is
                not finite at the sampled edges.
            az_start: Azimuth origin of the cube in full-scene pixels.
            rg_start: Range origin of the cube in full-scene pixels.
            n_az: Azimuth extent of the cube, in pixels.
            n_rg: Range extent of the cube, in pixels.

        Returns:
            Dict with the ECEF ``apex`` on the flight line, the ``near`` and
            ``far`` ground points at mid-azimuth, their slant ranges in metres and
            their look angles in degrees.
        """
        az_mid = az_start + n_az / 2.0
        near_h = float(dem[n_az // 2, 0])
        far_h  = float(dem[n_az // 2, n_rg - 1])

        near_h = near_h if math.isfinite(near_h) else base_height
        far_h  = far_h  if math.isfinite(far_h)  else base_height

        _, _, apex = geocoder.geocode_track([az_mid], [float(reference["h0"])])
        _, _, feet = geocoder.geocode([az_mid, az_mid], [rg_start, rg_start + n_rg - 1], [near_h, far_h])

        slant_near = geocoder.r0 + rg_start * geocoder.ps_rg
        slant_far  = geocoder.r0 + (rg_start + n_rg - 1) * geocoder.ps_rg

        return {
            "apex"          : apex[0],
            "near"          : feet[0],
            "far"           : feet[1],
            "slant_near_m"  : slant_near,
            "slant_far_m"   : slant_far,
            "look_near_deg" : math.degrees(math.acos(min(1.0, (float(reference["h0"]) - near_h) / slant_near))),
            "look_far_deg"  : math.degrees(math.acos(min(1.0, (float(reference["h0"]) - far_h) / slant_far))),
        }

    def _globe_meta(self, geo: dict | None) -> dict | None:
        """Serialises the geocoding context for the globe front end.

        Args:
            geo: Geocoding context, or None when the scene cannot be geolocated.

        Returns:
            Dict with the ECEF anchor, lon/lat bounding box, base height in
            metres, the geocoder's residual RMS in metres and, when the run
            records its pass labels, the flight lines and beam expressed as ECEF
            offsets from the anchor; None when geo is None.
        """
        if geo is None:
            return None

        anchor = np.asarray(geo["anchor_ecef"], dtype=np.float64)
        offset = lambda ecef: [round(float(v), 2) for v in np.asarray(ecef, dtype=np.float64) - anchor]
        beam   = geo["beam"]
        tracks = geo["tracks"]

        return {
            "anchor_ecef"    : [float(value) for value in geo["anchor_ecef"]],
            "bbox"           : geo["bbox"],
            "base_height"    : geo["base_height"],
            "residual_rms_m" : geo["geocoder"].residual_rms_m,
            "tracks_note"    : None if tracks is not None else "this preprocessing run stores no pass labels, so the flight lines cannot be drawn",
            "tracks"         : None if tracks is None else {
                "labels"    : tracks["labels"],
                "reference" : tracks["reference"],
                "h0"        : tracks["h0"],
                "lines"     : [[offset(point) for point in line] for line in tracks["lines"]],
                "beam"      : {
                    "apex"          : offset(beam["apex"]),
                    "near"          : offset(beam["near"]),
                    "far"           : offset(beam["far"]),
                    "slant_near_m"  : beam["slant_near_m"],
                    "slant_far_m"   : beam["slant_far_m"],
                    "look_near_deg" : beam["look_near_deg"],
                    "look_far_deg"  : beam["look_far_deg"],
                },
            },
        }

    def _ingest(self, raw: np.ndarray, x_axis: np.ndarray, advance) -> dict:
        """Materialises a cube plane by plane and derives its display colour limits.

        Args:
            raw: Lazy or memory-mapped cube of shape (elevation, azimuth, range);
                complex planes are reduced to their magnitude.
            x_axis: Elevation axis in metres.
            advance: Callback invoked once per ingested elevation plane.

        Returns:
            Entry with the float32 ``cube``, its ``x_axis`` and the 1st and 99th
            percentile colour limits estimated on a decimated subsample.
        """
        cube = np.empty(raw.shape, dtype=np.float32)

        for i in range(raw.shape[0]):
            plane   = np.asarray(raw[i])
            cube[i] = np.abs(plane) if np.iscomplexobj(plane) else plane
            advance()

        sample = cube[:, :: max(1, cube.shape[1] // 256), :: max(1, cube.shape[2] // 256)]
        sample = sample[np.isfinite(sample)]
        vmin, vmax = (np.percentile(sample, [1.0, 99.0]) if sample.size else (0.0, 1.0))

        return {
            "cube"   : cube,
            "x_axis" : x_axis,
            "vmin"   : float(vmin),
            "vmax"   : float(vmax),
        }

    def _elevation_axis(self, reader: StampReader, n_elev: int) -> np.ndarray:
        """Returns the n_elev evenly spaced elevation bin centres in metres."""
        low, high = reader.height_range()
        return np.linspace(low, high, n_elev)

    def _primary_db(self, reader: StampReader, n_az: int, n_rg: int) -> np.ndarray:
        """Loads the primary SLC and returns its amplitude in dB.

        Args:
            reader: Preprocessing run reader.
            n_az: Azimuth extent of the cube, in pixels.
            n_rg: Range extent of the cube, in pixels.

        Returns:
            Float32 array of shape (n_az, n_rg) holding 20 log10 of the amplitude,
            floored at 1e-12 before the logarithm.

        Raises:
            FileNotFoundError: If the run stores no primary SLC.
            ValueError: If the primary is not a 2D image or does not match the
                tomogram footprint.
        """
        raw = reader.primary()
        if raw.ndim != 2:
            raise ValueError(f"primary SLC is not a 2D image: shape={raw.shape}")
        if raw.shape != (n_az, n_rg):
            raise ValueError(f"primary SLC shape {raw.shape} does not match the {n_az}x{n_rg} tomogram footprint in {reader.where}")

        amplitude = np.abs(np.asarray(raw)).astype(np.float32)
        return 20.0 * np.log10(np.maximum(amplitude, 1e-12))


class SliceCollector:
    """Renders the same slices across many runs for side-by-side comparison.

    Opens preprocessing runs lazily through an LRU cache of lightweight
    contexts, so several runs can be previewed and collected without displacing
    the cube loaded in the Cube tab.

    Attributes:
        cubes: Explorer supplying the readers, archiver and cut helpers.
        logger: Web logger for render and collection reporting.
        render_lock: Serialises figure writing during a collection.
        contexts: LRU cache of opened run contexts, keyed by run directory.
    """

    SOURCES    = ("full",)
    AXES       = ("range", "azimuth")
    MAX_RUNS   = 24
    MAX_POINTS = 24
    CACHE_CAP  = 16

    def __init__(self, cubes: CubeExplorer, logger: WebLogger) -> None:
        """Stores the explorer and logger and prepares the context cache."""
        self.cubes       = cubes
        self.logger      = logger
        self.render_lock = threading.Lock()
        self.contexts    = LruCache(self.CACHE_CAP)

    def info(self, cube_id: str) -> dict:
        """Describes one collectable cube.

        Args:
            cube_id: Preprocessing run directory path.

        Returns:
            Dict with ``ok``, the run id, run, group and tag names, the cube's
            azimuth and range extents, the available ``sources`` and their
            intensity limits, or ``ok`` False with the reason.
        """
        try:
            context = self._context(cube_id)
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

        if context is None:
            return {"ok": False, "error": f"unknown cube id: {cube_id}"}

        entries = context["entries"]
        return {
            "ok"        : True,
            "id"        : str(context["run_dir"]),
            "run"       : context["run"],
            "group"     : context["group"],
            "stamp"     : context["stamp"],
            "n_az"      : context["n_az"],
            "n_rg"      : context["n_rg"],
            "sources"   : [s for s in self.SOURCES if s in entries],
            "intensity" : {s: [entries[s]["vmin"], entries[s]["vmax"]] for s in entries},
        }

    def slice_png(self, cube_id: str, source: str, axis: str, az: int, rg: int, space: str = "physical", cmap: str = "jet", vmin: float | None = None, vmax: float | None = None) -> bytes | None:
        """Renders one slice of a collectable cube as a PNG.

        Args:
            cube_id: Preprocessing run directory path.
            source: Cube key to render.
            axis: "range" or "azimuth".
            az: Azimuth pixel index, clipped into range.
            rg: Range pixel index, clipped into range.
            space: "physical" or "normalized".
            cmap: Colormap name.
            vmin: Optional lower colour limit, honoured only in physical space.
            vmax: Optional upper colour limit, honoured only in physical space.

        Returns:
            PNG bytes, or None when the arguments are invalid or the cube carries
            no such source.
        """
        if source not in self.SOURCES or axis not in self.AXES or space not in ("physical", "normalized"):
            return None

        try:
            context = self._context(cube_id)
        except Exception as error:
            self.logger.warning(f"slice render for {cube_id} failed while opening the cube: {error}")
            return None

        if context is None:
            self.logger.warning(f"slice render refused: unknown cube id {cube_id}")
            return None

        entry = context["entries"].get(source)
        if entry is None:
            self.logger.warning(f"slice render refused: {cube_id} carries no '{source}' cube")
            return None

        data, heights, lo, hi = self._cut(entry, axis, az, rg, space)
        if space == "physical" and vmin is not None and vmax is not None and vmax > vmin:
            lo, hi = float(vmin), float(vmax)

        buf = io.BytesIO()
        plt.imsave(buf, np.flipud(data), cmap=CubeExplorer._entry_cmap(entry, cmap), vmin=lo, vmax=hi, format="png")
        return buf.getvalue()

    def collect(self, ids: list, points: list, sources: list, axes: list, space: str = "physical", cmap: str = "jet", shared: bool = True, name: str = "") -> dict:
        """Renders and archives a grid of slices across runs, points, sources and axes.

        Figures land under ``<runs root>/slice_collections/<name>`` in one folder
        per point and cut, next to a ``collection.json`` manifest.

        Args:
            ids: Preprocessing run directory paths, deduplicated, at most MAX_RUNS.
            points: Dicts with ``az`` and ``rg`` pixel indices, at most MAX_POINTS.
            sources: Cube keys to render, a non-empty subset of SOURCES.
            axes: Cut axes to render, a non-empty subset of AXES.
            space: "physical" or "normalized".
            cmap: Colormap name.
            shared: When True and space is physical, all runs of a source share
                the widest colour range across them.
            name: Collection folder name; sanitised, and defaulted to a timestamp.

        Returns:
            Dict with ``ok``, the output ``dir``, the resolved ``name``, the
            written ``files``, the run-source pairs that were ``missing`` and the
            number of runs, or ``ok`` False with the reason.
        """
        ids     = list(dict.fromkeys(str(i) for i in ids if i))
        sources = list(dict.fromkeys(sources))
        axes    = list(dict.fromkeys(axes))

        if not ids:
            return {"ok": False, "error": "select at least one run"}
        if len(ids) > self.MAX_RUNS:
            return {"ok": False, "error": f"at most {self.MAX_RUNS} runs per collection, got {len(ids)}"}
        if space not in ("physical", "normalized"):
            return {"ok": False, "error": f"unknown space: {space}"}
        if not sources or any(s not in self.SOURCES for s in sources):
            return {"ok": False, "error": f"sources must be a non-empty subset of {self.SOURCES}"}
        if not axes or any(a not in self.AXES for a in axes):
            return {"ok": False, "error": f"axes must be a non-empty subset of {self.AXES}"}

        try:
            points   = self._points(points)
            contexts = []
            for cube_id in ids:
                context = self._context(cube_id)
                if context is None:
                    return {"ok": False, "error": f"unknown cube id: {cube_id}"}
                contexts.append(context)
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

        labels  = self._labels(contexts)
        title   = re.sub(r"[^A-Za-z0-9._-]+", "_", name or "").strip("._")
        title   = title or datetime.now().strftime("collection_%Y%m%d_%H%M%S")
        out_dir = contexts[0]["root"] / "slice_collections" / title

        if out_dir.exists():
            return {"ok": False, "error": f"a collection named '{title}' already exists at {out_dir}; pick another name or delete it first"}

        clims   = {source: self._shared_clim(contexts, source, space) if shared else None for source in sources}
        missing = [{"label": label, "source": source} for source in sources for context, label in zip(contexts, labels) if source not in context["entries"]]

        files = []
        with self.render_lock:
            for az, rg in points:
                point_dir = out_dir / f"az{az:04d}_rg{rg:04d}"
                for source in sources:
                    clim = clims[source]
                    for axis in axes:
                        cut_dir = point_dir / f"{axis}_{source}_{space}"
                        for context, label in zip(contexts, labels):
                            entry = context["entries"].get(source)
                            if entry is None:
                                continue

                            az_i = int(np.clip(az, 0, context["n_az"] - 1))
                            rg_i = int(np.clip(rg, 0, context["n_rg"] - 1))
                            data, heights, vmin, vmax = self._cut(entry, axis, az_i, rg_i, space)
                            if clim is not None:
                                vmin, vmax = clim

                            saved = self.cubes.archiver.render(data, heights, vmin, vmax, source, axis, az_i, rg_i, space, cut_dir / f"{label}.png", cmap=CubeExplorer._entry_cmap(entry, cmap), label=label)
                            files.append(str(saved.relative_to(out_dir)))

        if not files:
            return {"ok": False, "error": "no figures rendered; none of the selected runs carry the requested sources"}

        manifest = {
            "name"    : title,
            "created" : datetime.now().isoformat(timespec="seconds"),
            "space"   : space,
            "cmap"    : cmap,
            "shared"  : bool(shared),
            "axes"    : axes,
            "sources" : sources,
            "points"  : [{"az": az, "rg": rg} for az, rg in points],
            "clims"   : {source: (list(clim) if clim else None) for source, clim in clims.items()},
            "runs"    : [{"id": str(c["run_dir"]), "run": c["run"], "group": c["group"], "stamp": c["stamp"], "label": label} for c, label in zip(contexts, labels)],
            "missing" : missing,
            "files"   : files,
        }
        (out_dir / "collection.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")

        self.logger.ok(f"collected {len(files)} slice figures from {len(contexts)} runs into {out_dir}")
        return {"ok": True, "dir": str(out_dir), "name": title, "files": files, "missing": missing, "runs": len(contexts)}

    def _points(self, raw) -> list:
        """Validates and deduplicates the requested collection points.

        Args:
            raw: List of dicts carrying ``az`` and ``rg`` pixel indices.

        Returns:
            List of unique (azimuth, range) pairs in request order.

        Raises:
            ValueError: If the list is empty or not a list, exceeds MAX_POINTS, or
                holds a negative index.
        """
        if not isinstance(raw, list) or not raw:
            raise ValueError("points must be a non-empty list of {az, rg}")
        if len(raw) > self.MAX_POINTS:
            raise ValueError(f"at most {self.MAX_POINTS} points per collection, got {len(raw)}")

        points = []
        seen   = set()
        for entry in raw:
            az, rg = int(entry["az"]), int(entry["rg"])
            if az < 0 or rg < 0:
                raise ValueError(f"point az={az}, rg={rg} is negative")
            if (az, rg) in seen:
                continue
            seen.add((az, rg))
            points.append((az, rg))

        return points

    @staticmethod
    def _labels(contexts: list) -> list:
        """Builds one unique file label per context.

        Run names are used as-is, prefixed with their group when the name repeats
        and suffixed with the tomogram tag when that is still not unique.

        Args:
            contexts: Opened run contexts, in collection order.

        Returns:
            One label per context, in the same order.
        """
        counts = {}
        for context in contexts:
            counts[context["run"]] = counts.get(context["run"], 0) + 1

        grouped = []
        for context in contexts:
            label = context["run"]
            if counts[label] > 1 and context["group"] not in (".", ""):
                label = f"{context['group'].replace('/', '_')}__{label}"
            grouped.append(label)

        labels = []
        for context, label in zip(contexts, grouped):
            if grouped.count(label) > 1:
                label = f"{label}__{context['stamp']}"
            labels.append(label)

        return labels

    @staticmethod
    def _shared_clim(contexts: list, source: str, space: str) -> tuple[float, float] | None:
        """Returns the colour range covering one source across every context.

        Args:
            contexts: Opened run contexts.
            source: Cube key whose limits are merged.
            space: Only "physical" yields shared limits.

        Returns:
            The (vmin, vmax) envelope, or None in normalised space, when no
            context carries the source or when the envelope is degenerate.
        """
        if space != "physical":
            return None

        entries = [context["entries"][source] for context in contexts if source in context["entries"]]
        if not entries:
            return None

        vmin = min(entry["vmin"] for entry in entries)
        vmax = max(entry["vmax"] for entry in entries)
        return (vmin, vmax) if vmax > vmin else None

    @staticmethod
    def _cut(entry: dict, axis: str, az: int, rg: int, space: str) -> tuple[np.ndarray, np.ndarray, float, float]:
        """Extracts one elevation slice from a lazily held cube.

        Unlike the explorer's cut, the cube here may still be memory-mapped or
        complex, so the slice is materialised and reduced to magnitude first.

        Args:
            entry: Context entry holding the cube and its elevation axis.
            axis: "range" for a fixed range column, "azimuth" for a fixed azimuth row.
            az: Azimuth pixel index, clipped into range.
            rg: Range pixel index, clipped into range.
            space: "normalized" to peak-normalise columns, else "physical".

        Returns:
            Tuple of the float32 slice of shape (elevation bins, samples) ordered
            by ascending elevation, the elevation axis in metres, and the colour
            limits.
        """
        cube               = entry["cube"]
        n_elev, n_az, n_rg = cube.shape

        az   = int(np.clip(az, 0, n_az - 1))
        rg   = int(np.clip(rg, 0, n_rg - 1))
        data = np.asarray(cube[:, :, rg] if axis == "range" else cube[:, az, :])
        data = np.abs(data).astype(np.float32) if np.iscomplexobj(data) else data.astype(np.float32)

        data, vmin, vmax = CubeExplorer._normalize_cut(entry, data, space)

        order   = np.argsort(entry["x_axis"])
        heights = np.asarray(entry["x_axis"], dtype=np.float64)[order]
        return data[order], heights, float(vmin), float(vmax)

    def _context(self, cube_id: str) -> dict | None:
        """Returns the cached or freshly built context of a preprocessing run.

        Args:
            cube_id: Preprocessing run directory path.

        Returns:
            The run context, or None when the id is unknown.
        """
        reader = self.cubes._open_source(cube_id)
        if reader is None:
            return None

        key    = str(reader.run_dir)
        cached = self.contexts.get(key)
        if cached is not None:
            return cached

        context = self._build_context(reader)
        self.contexts.put(key, context)

        return context

    def _build_context(self, reader: StampReader) -> dict:
        """Opens the tomogram of a run without materialising it.

        Args:
            reader: Reader of the run to open.

        Returns:
            Context with the run directory, its runs root, the run, group and
            tag names, the azimuth and range extents and the lazily held
            ``entries`` per source.

        Raises:
            ValueError: If the run lies outside every catalogued runs root or the
                tomogram is not three-dimensional.
        """
        run_dir = reader.run_dir
        root    = self._root_for(run_dir)
        if root is None:
            raise ValueError(f"{run_dir} is outside every catalogued runs root")

        full_raw = reader.tomogram()
        if full_raw.ndim != 3:
            raise ValueError(f"full tomogram is not a 3D cube: shape={full_raw.shape}")

        n_elev, n_az, n_rg = full_raw.shape
        x_axis             = self.cubes._elevation_axis(reader, n_elev)

        entries = {"full": self._entry(full_raw, x_axis)}

        return {
            "run_dir" : run_dir,
            "root"    : root,
            "run"     : run_dir.name,
            "group"   : str(run_dir.relative_to(root).parent),
            "stamp"   : reader.layout()["tomogram_tag"],
            "n_az"    : n_az,
            "n_rg"    : n_rg,
            "entries" : entries,
        }

    @staticmethod
    def _entry(raw: np.ndarray, x_axis: np.ndarray) -> dict:
        """Wraps a cube without materialising it and estimates its colour limits.

        Args:
            raw: Memory-mapped cube of shape (elevation, azimuth, range).
            x_axis: Elevation axis in metres.

        Returns:
            Entry with the untouched ``cube``, its ``x_axis`` and the 1st and 99th
            percentile colour limits estimated on a decimated subsample.
        """
        sample = np.asarray(raw[:, :: max(1, raw.shape[1] // 256), :: max(1, raw.shape[2] // 256)])
        sample = np.abs(sample) if np.iscomplexobj(sample) else sample
        sample = sample[np.isfinite(sample)]
        vmin, vmax = (np.percentile(sample, [1.0, 99.0]) if sample.size else (0.0, 1.0))

        return {
            "cube"   : raw,
            "x_axis" : x_axis,
            "vmin"   : float(vmin),
            "vmax"   : float(vmax),
        }

    def _root_for(self, run_dir: Path) -> Path | None:
        """Returns the catalogued runs root containing the run, or None."""
        return self.cubes.roots.enclosing(run_dir)
