"""Interactive server-side backend for the web UI cube explorer tabs.

Opens the raw tomogram cubes written by the preprocessing pipeline together
with their DEM and primary SLC amplitude, optionally alongside the
parametrized tomogram of a Gaussian parameter run reconstructed lazily on the
same elevation axis, and renders slices, planes, transects and geocoded point
clouds as PNG or packed binary payloads. When the run carries a polarimetric
primary it also serves the multilooked Pauli decomposition as maps, pixel
readouts, scene summaries and a north-up drape for the globe. The slice
collector renders a basket of cuts across runs into a folder and can mail it as
zip volumes. Cubes are indexed by elevation bin, azimuth pixel and range pixel;
elevation axes are in metres and geocoded positions in ECEF metres.
"""

from __future__ import annotations

import io
import json
import math
import os
import re
import smtplib
import sys
import threading
import time
import traceback
import zipfile
from concurrent.futures import ThreadPoolExecutor
from datetime      import datetime
from email.message import EmailMessage
from pathlib       import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from catalog_roots                  import CatalogRoots, RunScanner
from globe_drape                    import FootprintImage
from lru_cache                      import LruCache
from tools.data.gaussians           import GaussianMixture
from tools.reporting.plotting       import PlotBase
from tools.runtime.machine_profile  import MachineProfile
from tools.sar.geocoding            import SceneGeocoder
from tools.sar.geometry_field       import GeometryField
from tools.sar.polarimetry          import PauliDecomposer, PolarimetricArtifact
from tools.sar.track_parameters     import TrackParameters
from web_logger                     import WebLogger


class SliceFigureArchiver(PlotBase):
    """Renders publication-styled slice and transect figures to disk.

    Wraps the shared plotting base so every saved cut carries axis labels, an
    elevation axis in metres and a colourbar, using the paper style regardless of
    the style active elsewhere in the process.
    """

    LABELS = {
        "full"  : "Capon full (raw)",
        "param" : "Parametrized tomogram (Gaussian)",
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
            fig = self._imshow_figure(
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
            )
            return self._save(fig, path)
        finally:
            PlotBase.use_style(previous)

    def render_transect(self, data: np.ndarray, heights: np.ndarray, vmin: float, vmax: float, source: str, points: list, space: str, path: Path, cmap: str = "jet") -> Path:
        """Saves an elevation section sampled along an arbitrary azimuth-range polyline.

        Args:
            data    : Cut of shape (elevation bins, samples along the transect).
            heights : Elevation axis in metres, ascending, one entry per row of data.
            vmin    : Lower colour limit.
            vmax    : Upper colour limit.
            source  : Cube key, one of the keys of LABELS.
            points  : Ordered (azimuth, range) vertices of the transect polyline, at least two.
            space   : "normalized" when columns were peak-normalised, else "physical".
            path    : Destination PNG path.
            cmap    : Matplotlib colormap name.

        Returns:
            The path the figure was written to.
        """
        cbar   = "intensity (per-column normalised)" if space == "normalized" else "intensity"
        extent = [0, int(data.shape[1]), float(heights[0]), float(heights[-1])]
        start  = points[0]
        end    = points[-1]
        via    = f" via {len(points) - 2} points" if len(points) > 2 else ""

        previous = PlotBase.style
        PlotBase.use_style("paper")
        try:
            fig = self._imshow_figure(
                data,
                x_label        = "sample along transect",
                y_label        = "elevation [m]",
                title          = f"{self.LABELS[source]} — transect az{start[0]},rg{start[1]} to az{end[0]},rg{end[1]}{via}",
                cmap           = cmap,
                vmin           = vmin,
                vmax           = vmax,
                extent         = extent,
                origin         = "lower",
                colorbar_label = cbar,
                figsize        = self.figsize(self.FULL_WIDTH),
            )
            return self._save(fig, path)
        finally:
            PlotBase.use_style(previous)


class ParametrizedTomogram:
    """Lazy cube view over the parametrized tomogram of a parameter run.

    The parametrized tomogram is the physical product of fitting per-pixel
    Gaussian mixtures to the raw tomogram. This view presents it as a cube of
    shape (elevation, azimuth, range) whose planes, columns and pixel gathers
    are evaluated on demand from the parameter cube, so the reconstruction is
    never materialised whole.

    Attributes:
        params: Parameter cube of shape (3 * n_gaussians, azimuth, range),
            interleaved per slot as amplitude, mean in metres, width in metres.
        x_axis: Elevation axis in metres of shape (elevation bins,).
        n_gaussians: Number of Gaussian slots per pixel.
        shape: Shape of the reconstructed cube, (elevation, azimuth, range).
        dtype: Element type of the evaluated views.
    """

    CLIM_GRID = 128

    def __init__(self, params: np.ndarray, x_axis: np.ndarray, n_gaussians: int) -> None:
        """Stores the parameter cube and the elevation axis it is evaluated on."""
        self.params      = params
        self.x_axis      = np.asarray(x_axis, dtype=np.float64)
        self.n_gaussians = n_gaussians
        self.shape       = (int(self.x_axis.size), int(params.shape[1]), int(params.shape[2]))
        self.dtype       = np.dtype(np.float32)

    @property
    def ndim(self) -> int:
        """Number of axes of the reconstructed cube."""
        return len(self.shape)

    def __len__(self) -> int:
        """Number of elevation planes."""
        return self.shape[0]

    def __getitem__(self, index):
        """Evaluates one view of the parametrized tomogram.

        Args:
            index: Either an integer elevation bin, yielding the (azimuth,
                range) plane at that bin's elevation, or a ``[:, az, rg]``
                triple whose spatial parts may be integers, slices or index
                arrays, yielding the elevation profiles of the addressed pixels.

        Returns:
            Float32 array with the elevation axis first, shaped by the spatial
            parts of the index.

        Raises:
            IndexError: If an integer elevation bin is out of range.
            ValueError: If the index follows neither supported pattern.
        """
        if isinstance(index, (int, np.integer)):
            if not -self.shape[0] <= index < self.shape[0]:
                raise IndexError(f"elevation bin {index} outside the {self.shape[0]} planes of the parametrized tomogram")
            return GaussianMixture.evaluate_slice(self.params, float(self.x_axis[index]), self.n_gaussians)

        if not (isinstance(index, tuple) and len(index) == 3 and index[0] == slice(None)):
            raise ValueError(f"unsupported parametrized-tomogram index: {index!r}")

        pixels = self.params[:, index[1], index[2]]
        flat   = pixels.reshape(self.params.shape[0], -1).T

        profiles = GaussianMixture.evaluate_batch(self.x_axis, flat[:, 0::3], flat[:, 1::3], flat[:, 2::3])
        return profiles.T.reshape((self.shape[0],) + pixels.shape[1:])

    def clim(self) -> tuple[float, float]:
        """Returns the 1st and 99th percentile colour limits of the reconstruction.

        Profiles are evaluated on a decimated pixel grid of at most CLIM_GRID
        samples per spatial axis, so the limits are cheap yet deterministic.
        """
        step_az = max(1, self.shape[1] // self.CLIM_GRID)
        step_rg = max(1, self.shape[2] // self.CLIM_GRID)

        sample = self[:, slice(None, None, step_az), slice(None, None, step_rg)]
        sample = sample[np.isfinite(sample)]

        if sample.size == 0:
            return 0.0, 1.0

        vmin, vmax = np.percentile(sample, [1.0, 99.0])
        return float(vmin), float(vmax)


class LoadProgress:
    """Thread-safe byte counter a cube load reports its file reads through.

    Besides the overall fraction it tracks every file currently in flight with
    its bytes landed so far, so a stalled load names the file it is waiting on.

    Attributes:
        total    : Bytes the load plans to read.
        done     : Bytes read so far.
        files    : Files in flight, keyed by path, each as [bytes done, bytes total].
        listener : Callable receiving the fraction done and the in-flight snapshot after every advance, or None.
    """

    def __init__(self, listener=None) -> None:
        """Starts an empty counter, optionally forwarding progress to a listener."""
        self.lock     = threading.Lock()
        self.total    = 0
        self.done     = 0
        self.files    = {}
        self.listener = listener

    def plan(self, n_bytes: int) -> None:
        """Adds bytes to the planned total."""
        with self.lock:
            self.total += int(n_bytes)

    def begin(self, path: Path, n_bytes: int) -> None:
        """Registers a file whose chunks are about to land."""
        with self.lock:
            self.files[str(path)] = [0, int(n_bytes)]

    def advance(self, path: Path, n_bytes: int) -> None:
        """Books bytes of one file as read and publishes the fraction done."""
        with self.lock:
            key        = str(path)
            self.done += int(n_bytes)
            self.files[key][0] += int(n_bytes)
            if self.files[key][0] >= self.files[key][1]:
                del self.files[key]

            fraction = min(1.0, self.done / self.total) if self.total else 0.0
            reading  = self._snapshot()

        if self.listener is not None:
            self.listener(fraction, reading)

    def _snapshot(self) -> list:
        """Lists the files in flight, most bytes outstanding first, with the caller holding the lock."""
        rows = [{"file": "/".join(Path(key).parts[-5:]), "done": done, "total": total} for key, (done, total) in self.files.items()]
        rows.sort(key=lambda row: row["done"] - row["total"])
        return rows


class NpyReader:
    """Reads ``.npy`` files whole through a shared pool of concurrent chunk reads.

    Every file is split into fixed-size chunks that are pulled with ``pread``
    by a process-wide thread pool, so a large file keeps several requests in
    flight against the mount, and every chunk books its bytes on the load's
    progress counter as it lands. Pool tasks are leaf reads only, so callers
    may wait on them from any thread without deadlock.

    Attributes:
        progress : Counter receiving the byte count of every chunk read.
    """

    CHUNK_BYTES  = 16 * 1024 * 1024
    READ_WORKERS = min(32, os.cpu_count() or 4)
    POOL         = ThreadPoolExecutor(max_workers=READ_WORKERS, thread_name_prefix="npy-read")

    def __init__(self, progress: LoadProgress) -> None:
        """Stores the progress counter the reads report to."""
        self.progress = progress

    def header(self, path: Path) -> tuple[tuple, np.dtype]:
        """Returns the shape and dtype recorded in a ``.npy`` header without reading the data."""
        with open(path, "rb") as handle:
            shape, _, dtype = self._parse_header(handle, path)

        return shape, dtype

    def read(self, path: Path) -> np.ndarray:
        """Reads one whole ``.npy`` file into a fresh C-ordered array.

        Args:
            path : File written by ``np.save``.

        Returns:
            The array with the shape and dtype the header declares.

        Raises:
            ValueError : If the header version is unsupported, the array is Fortran-ordered or the file ends before its data does.
        """
        with open(path, "rb") as handle:
            shape, dtype, offset = self._open_header(handle, path)
            target               = self._target(path, handle, offset, shape, dtype)
            size                 = target["buffer"].nbytes
            chunks               = [(target, start, start, min(self.CHUNK_BYTES, size - start)) for start in range(0, size, self.CHUNK_BYTES)]
            list(self.POOL.map(self._pull, chunks))

        return target["array"]

    def _open_header(self, handle, path: Path) -> tuple[tuple, np.dtype, int]:
        """Parses an open file's header and returns its shape, dtype and data offset, refusing Fortran order."""
        shape, fortran, dtype = self._parse_header(handle, path)
        if fortran:
            raise ValueError(f"{path} is Fortran-ordered; cube files are written C-ordered")

        return shape, dtype, handle.tell()

    def _target(self, path: Path, handle, offset: int, shape: tuple, dtype: np.dtype) -> dict:
        """Allocates the array a file's chunks land in and registers it with the progress counter."""
        array  = np.empty(shape, dtype=dtype)
        buffer = memoryview(array.reshape(-1).view(np.uint8))
        self.progress.begin(path, buffer.nbytes)
        return {"path": path, "fd": handle.fileno(), "offset": offset, "array": array, "buffer": buffer}

    def _pull(self, chunk: tuple) -> None:
        """Reads one chunk with pread into its place in the target buffer and books its bytes.

        Args:
            chunk : Tuple of (target, byte offset into the file's data, byte offset into the buffer, byte count).
        """
        target, src, dst, count = chunk
        done                    = 0
        while done < count:
            got = os.preadv(target["fd"], [target["buffer"][dst + done:dst + count]], target["offset"] + src + done)
            if not got:
                raise ValueError(f"{target['path']} ends after {src + done} data bytes")

            done += got
            self.progress.advance(target["path"], got)

    @staticmethod
    def _parse_header(handle, path: Path) -> tuple[tuple, bool, np.dtype]:
        """Consumes the magic and header of an open ``.npy`` file and returns (shape, fortran, dtype)."""
        version = np.lib.format.read_magic(handle)
        if version == (1, 0):
            return np.lib.format.read_array_header_1_0(handle)
        if version == (2, 0):
            return np.lib.format.read_array_header_2_0(handle)

        raise ValueError(f"{path} uses .npy format version {version}; only 1.0 and 2.0 are read")


class StampReader:
    """Reads the artifacts of one preprocessing run directory.

    A preprocessing run directory holds ``data/dataset.json`` describing the
    global crop and artifact filenames, the artifact cubes under ``data`` and
    the run metadata under ``meta``.

    Attributes:
        run_dir       : Directory of the preprocessing run.
        npy           : Chunked file reader booking every whole-file read on the load's progress counter.
        cached_layout : Parsed dataset layout, filled on first access.
    """

    def __init__(self, run_dir: Path, progress: LoadProgress) -> None:
        """Stores the preprocessing run directory and the load's progress counter."""
        self.run_dir       = run_dir
        self.npy           = NpyReader(progress)
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

    def cache_key(self, param_tag: str | None) -> str:
        """Returns the key under which a load of this run with the given parameter run is kept in memory."""
        return f"{self.run_dir}|{param_tag}"

    def byte_plan(self, param_tag: str | None) -> int:
        """Returns the bytes a load of this run reads whole: the tomogram, the primary SLC, the DEM and the chosen parameter block.

        Args:
            param_tag : Parameter run loaded alongside the raw cube, or None.
        """
        paths = [self.artifact_path(key) for key in ("tomogram_full", "primary", "dem_full")]
        if param_tag is not None:
            paths.append(self.run_dir / "params" / param_tag / "parameters.npy")

        return sum(path.stat().st_size for path in paths if path is not None and path.is_file())

    def tomogram(self, view: bool = False) -> np.ndarray:
        """Reads the full tomogram cube of shape (elevation, azimuth, range).

        The whole file is read into memory in one sequential pass, which is the
        fastest access pattern on the network mounts the runs live on. Callers
        that only touch a few lines of the cube ask for a memory-mapped view.

        Args:
            view : When True the file is memory-mapped instead of read into RAM.

        Raises:
            FileNotFoundError: If the run stores no full tomogram.
        """
        path = self.artifact_path("tomogram_full")
        if path is None:
            raise FileNotFoundError(f"tomogram_full missing in {self.run_dir / 'data'}; rerun preprocessing to regenerate it")

        return np.load(path, mmap_mode="r") if view else self.npy.read(path)

    def dem(self) -> np.ndarray | None:
        """Reads the full DEM of shape (azimuth, range), or None when absent."""
        path = self.artifact_path("dem_full")
        if path is None:
            return None

        return self.npy.read(path)

    def primary(self) -> np.ndarray:
        """Reads the primary SLC image of shape (azimuth, range).

        Raises:
            FileNotFoundError: If the run stores no primary SLC.
        """
        path = self.artifact_path("primary")
        if path is None:
            raise FileNotFoundError(f"primary SLC missing in {self.run_dir / 'data'}; rerun preprocessing to regenerate it")

        return self.npy.read(path)

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

    def param_tags(self) -> list[str]:
        """Lists the parameter runs stored under the run's ``params`` directory.

        Returns:
            Sorted names of the ``params`` subdirectories holding a
            ``parameters.npy``; empty when the run stores no parameter runs.
        """
        params_dir = self.run_dir / "params"
        if not params_dir.is_dir():
            return []

        return sorted(child.name for child in params_dir.iterdir() if (child / "parameters.npy").is_file())

    def param_meta(self, tag: str) -> dict:
        """Returns the ``param_extraction_meta.json`` of one parameter run.

        Args:
            tag: Name of the parameter run under ``params``.

        Raises:
            FileNotFoundError: If that parameter run stores no metadata file.
        """
        path = self.run_dir / "params" / tag / "param_extraction_meta.json"
        if not path.is_file():
            raise FileNotFoundError(f"param_extraction_meta.json missing in {path.parent}; rerun the parameter extraction to regenerate it")

        return json.loads(path.read_text(encoding="utf-8"))

    def param_block(self, tag: str) -> np.ndarray:
        """Loads the Gaussian parameter cube of one parameter run.

        Args:
            tag: Name of the parameter run under ``params``.

        Returns:
            Float32 parameter cube of shape (3 * k_max, azimuth, range),
            interleaved per slot as amplitude, mean in metres, width in metres.

        Raises:
            FileNotFoundError: If that parameter run stores no ``parameters.npy``.
        """
        path = self.run_dir / "params" / tag / "parameters.npy"
        if not path.is_file():
            raise FileNotFoundError(f"parameters.npy missing in {path.parent}; rerun the parameter extraction to regenerate it")

        return np.asarray(self.npy.read(path), dtype=np.float32)


class LoadTimer:
    """Books the wall time of the named stages of one cube load.

    Attributes:
        stages  : Seconds spent per stage, in completion order.
        started : Clock reading when the load began.
        last    : Clock reading at the end of the previous stage.
    """

    def __init__(self) -> None:
        """Starts the clock."""
        self.stages  = {}
        self.started = time.perf_counter()
        self.last    = self.started

    def lap(self, stage: str) -> None:
        """Books the time elapsed since the previous lap under ``stage``."""
        now                = time.perf_counter()
        self.stages[stage] = round(self.stages.get(stage, 0.0) + now - self.last, 3)
        self.last          = now

    def total(self) -> float:
        """Seconds elapsed since the clock started."""
        return time.perf_counter() - self.started

    def summary(self) -> str:
        """Renders the stage times as comma-separated ``stage 1.23 s`` items."""
        return ", ".join(f"{stage} {seconds:.2f} s" for stage, seconds in self.stages.items())


class CubeExplorer:
    """Loads one preprocessing run at a time and serves views of it to the web UI.

    Holds a single loaded cube in memory behind a lock: the raw tomogram, the
    primary SLC amplitude map in dB, the DEM, the geocoding context and, when a
    parameter run tag is given, the lazily reconstructed parametrized tomogram
    of that run. Loading runs in a background thread whose progress is polled
    through ``load_status``; the last few loaded cubes stay in memory so
    switching back to one is immediate.

    Attributes:
        logger: Web logger for load and save reporting.
        archiver: Renderer used when slices are saved to disk.
        roots: Catalogued run roots that bound which cube ids may be opened.
        scanner: Scanner listing preprocessing runs under a root.
        lock: Guards the loaded cube and the load status.
        loaded: Currently loaded cube state, or None.
        load_thread: Background thread of the running load, or None.
        status_at: Clock reading of the last change to the load status.
        cube_cache: Recently loaded cube states keyed by run directory and parameter run tag.
        globe_blobs: Cache of packed globe point blobs keyed by cube id, parameter run tag and request.
        status: Load state machine payload polled by the front end.
    """

    SOURCES              = ("full", "param")
    CLOUD_CURVE_SOURCES  = ("full", "param")
    GLOBE_SOURCES        = ("full", "param")
    GLOBE_CACHE_ENTRIES  = 12
    CUBE_CACHE_ENTRIES   = 8
    STALL_FRAMES         = 4
    GLOBE_BLOB_MAX_BYTES = 32 * 1024 * 1024
    GLOBE_DEFAULT_POINTS = 60000
    GLOBE_TOUR_DIR       = Path("figures") / "globe_tours"
    GLOBE_TOUR_MAX_BYTES = 768 * 1024 * 1024
    GLOBE_TOUR_NAME_RE   = re.compile(r"[^a-z0-9]+")
    LIMIT_SAMPLE         = 1_000_000
    PNG_ENCODE           = {"format": "png", "pil_kwargs": {"compress_level": 1}}

    CMAPS = ("jet", "viridis", "inferno", "turbo", "gray")

    FIGURE_DIRS     = ("images", "figures", "params")
    FIGURE_SUFFIXES = (".png", ".gif", ".jpg", ".jpeg", ".svg")

    PAULI_MODES           = ("rgb", "surface", "double", "volume", "dominant")
    PAULI_LABELS          = {"surface": "surface (odd bounce)", "double": "double bounce", "volume": "volume"}
    PAULI_COLORS          = {"surface": "#3a9ad9", "double": "#d55e00", "volume": "#009e73"}
    PAULI_NODATA          = "#10151a"
    PAULI_WINDOW_MAX      = 99
    PAULI_CACHE_WINDOWS   = 2
    GLOBE_IMAGE_WIDTH     = 2048
    GLOBE_CELLS_PER_PIXEL = 4

    def __init__(self, logger: WebLogger) -> None:
        """Builds the explorer with an idle load status and no cube loaded."""
        self.logger      = logger
        self.archiver    = SliceFigureArchiver()
        self.roots       = CatalogRoots()
        self.scanner     = RunScanner(self.roots)
        self.lock        = threading.Lock()
        self.loaded      = None
        self.load_thread = None
        self.status_at   = time.perf_counter()
        self.cube_cache  = LruCache(self.CUBE_CACHE_ENTRIES)
        self.globe_blobs = LruCache(self.GLOBE_CACHE_ENTRIES)
        self.status      = {"state": "idle", "id": None, "progress": 0.0, "stage": "", "error": ""}

    def forget(self, run_dir: str) -> None:
        """Drops everything held in memory for one run, so its next load reads the files again.

        Discards the cached cube states and globe blobs of the run and, when it
        is the loaded cube, unloads it and returns the status to idle.

        Args:
            run_dir : Run directory path, the cube id.
        """
        prefix = f"{run_dir}|"
        self.cube_cache.discard(lambda key: key.startswith(prefix))
        self.globe_blobs.discard(lambda key: key.startswith(prefix))

        with self.lock:
            if self.loaded is not None and self.loaded["id"] == run_dir:
                self.loaded = None
                self.status = {"state": "idle", "id": None, "progress": 0.0, "stage": "", "error": ""}

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

    def param_runs(self, cube_id: str) -> dict:
        """Lists the parameter runs stored under one preprocessing run.

        Args:
            cube_id: Preprocessing run directory path.

        Returns:
            Dict with ``ok`` and the sorted parameter-run ``tags``, or ``ok``
            False when the id is unknown.
        """
        reader = self._open_source(cube_id)
        if reader is None:
            return {"ok": False, "error": f"unknown cube id: {cube_id}"}

        return {"ok": True, "tags": reader.param_tags()}

    def start_load(self, cube_id: str, param_tag: str | None = None) -> dict:
        """Starts loading a cube in a background thread, or serves it from memory.

        A run loaded recently with the same parameter run is swapped in at
        once; otherwise a background thread reads it and stores the result for
        later switches.

        Args:
            cube_id: Preprocessing run directory path.
            param_tag: Optional parameter run whose parametrized tomogram is
                loaded alongside the raw cube.

        Returns:
            Dict with ``ok`` True once the load was started or the cube is already
            loaded with the same parameter run, otherwise ``ok`` False with the
            reason.
        """
        reader = self._open_source(cube_id, LoadProgress(self._publish_progress))
        if reader is None:
            return {"ok": False, "error": f"unknown cube id: {cube_id}"}

        param_tag = param_tag or None
        if param_tag is not None:
            tags = reader.param_tags()
            if param_tag not in tags:
                return {"ok": False, "error": f"unknown parameter run tag '{param_tag}' for {cube_id}; available: {tags}"}

        cached = self.cube_cache.get(reader.cache_key(param_tag))

        with self.lock:
            if self.status["state"] == "loading":
                return {"ok": False, "error": f"a load is already running for {self.status['id']}"}
            if self.status["state"] == "ready" and self.status["id"] == cube_id and self.loaded is not None and self.loaded["param_tag"] == param_tag:
                return {"ok": True}

            if cached is not None:
                cached["meta"] = {**cached["meta"], "timings": {"total": 0.0, "stages": {"memory": 0.0}}}
                self.loaded    = cached
                self.status    = {"state": "ready", "id": cube_id, "progress": 1.0, "stage": "ready", "error": ""}
            else:
                self.loaded = None
                self.status = {"state": "loading", "id": cube_id, "progress": 0.0, "stage": "scanning sources", "reading": [], "error": ""}

        if cached is not None:
            self.logger.info(f"cube served from memory: {cube_id}")
            return {"ok": True}

        self.status_at   = time.perf_counter()
        self.load_thread = threading.Thread(target=self._load_worker, args=(cube_id, reader, param_tag), daemon=True)
        self.load_thread.start()
        return {"ok": True}

    def _publish_progress(self, fraction: float, reading: list) -> None:
        """Writes the fraction of planned bytes read and the files in flight into the polled load status."""
        with self.lock:
            if self.status["state"] == "loading":
                self.status["progress"] = fraction
                self.status["reading"]  = reading
                self.status_at          = time.perf_counter()

    def load_status(self) -> dict:
        """Returns the current load state, with the cube metadata once ready.

        While a load runs the payload also carries ``stalled_for``, the seconds
        since the status last changed, and ``where``, the innermost frames of
        the load thread, so a load that stops moving names the code it sits in.
        """
        with self.lock:
            payload = dict(self.status)
            if payload["state"] == "ready" and self.loaded is not None:
                payload["cube"] = self.loaded["meta"]
            if payload["state"] == "loading":
                payload["stalled_for"] = round(time.perf_counter() - self.status_at, 1)
                payload["where"]       = self._load_thread_frames()

        return payload

    def _load_thread_frames(self) -> list:
        """Returns the innermost STALL_FRAMES frames of the load thread as ``file:line function`` strings."""
        thread = self.load_thread
        frame  = sys._current_frames().get(thread.ident) if thread is not None else None
        if frame is None:
            return []

        return [f"{Path(entry.filename).name}:{entry.lineno} {entry.name}" for entry in traceback.extract_stack(frame)[-self.STALL_FRAMES:]]

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
            primary = self.loaded["primary"]
            clim    = self.loaded["primary_clim"]

        return self._encode_primary(primary, clim)

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

    def params_at(self, cube_id: str, az: int, rg: int) -> dict:
        """Returns the Gaussian slots of the loaded parameter run at one pixel.

        Args:
            cube_id: Id of the loaded cube.
            az: Azimuth pixel index, clipped into range.
            rg: Range pixel index, clipped into range.

        Returns:
            Dict with ``ok``, the clipped ``az`` and ``rg``, the parameter run
            ``tag`` and the ``slots`` ordered by ascending mean, each holding
            ``amplitude``, ``mean`` in metres and ``sigma`` in metres; inactive
            slots are included with their stored values.
        """
        entry = self._entry(cube_id, "param")
        if entry is None:
            return {"ok": False, "error": "no parameter run is loaded; load the cube with a param_tag first"}

        block = entry["params"]
        az    = int(np.clip(az, 0, block.shape[1] - 1))
        rg    = int(np.clip(rg, 0, block.shape[2] - 1))

        pixel = block[:, az, rg]
        slots = [{"amplitude": float(pixel[3 * k]), "mean": float(pixel[3 * k + 1]), "sigma": float(pixel[3 * k + 2])} for k in range(entry["n_gaussians"])]
        slots.sort(key=lambda slot: slot["mean"])

        return {"ok": True, "az": az, "rg": rg, "tag": entry["tag"], "slots": slots}

    def slice_png(self, cube_id: str, source: str, axis: str, az: int, rg: int, space: str = "physical", cmap: str = "jet", dem: bool = False) -> bytes | None:
        """Renders one elevation slice of a source as a PNG.

        Args:
            cube_id: Id of the loaded cube.
            source: Cube key to render.
            axis: "range" for a fixed range column, "azimuth" for a fixed azimuth row.
            az: Azimuth pixel index, clipped into range.
            rg: Range pixel index, clipped into range.
            space: "normalized" to peak-normalise columns, else "physical".
            cmap: Colormap name; diverging sources always use coolwarm.
            dem: When True and the run carries a DEM, every column is shifted
                vertically by its median-referenced terrain height.

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
        track = self._slice_dem_track(cube_id, axis, az, rg) if dem else None

        return self._cut_png(entry, data, heights, vmin, vmax, cmap, track)

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
        plt.imsave(buf, np.nan_to_num(data, nan=vmin), cmap=self._entry_cmap(entry, cmap), vmin=vmin, vmax=vmax, **self.PNG_ENCODE)
        return buf.getvalue()

    def cbar_png(self, cmap: str) -> bytes | None:
        """Renders a horizontal 256-step colour ramp for one of the allowed colormaps.

        Args:
            cmap: Colormap name.

        Returns:
            PNG bytes of the ramp, or None when the colormap is not allowed.
        """
        if cmap not in ("viridis", "inferno", "coolwarm", "jet", "gray", "twilight"):
            return None

        ramp = np.tile(np.linspace(0.0, 1.0, 256), (12, 1))

        buf = io.BytesIO()
        plt.imsave(buf, ramp, cmap=cmap, vmin=0.0, vmax=1.0, **self.PNG_ENCODE)
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

    VOLUME_MAX_DIM = 192

    def volume_bin(self, cube_id: str, source: str, max_dim: int | None = None) -> bytes | None:
        """Packs a downsampled cube as a quantised volume for the WebGL renderer.

        The cube is strided down until every axis fits max_dim, then mapped to
        uint8 over the entry's display colour range (symmetric for diverging
        sources) with NaN quantised to zero. The parametrized tomogram is
        evaluated only on the strided pixel grid.

        Args:
            cube_id : Id of the loaded cube.
            source  : Cube key to pack.
            max_dim : Largest allowed axis length after striding; VOLUME_MAX_DIM when None, clamped to [2, 256].

        Returns:
            An eight-float32 header (elevation, azimuth and range extents after
            striding, a diverging flag, vmin, vmax, 0, 0) followed by the uint8
            voxels in (elevation, azimuth, range) C order, or None when the
            cube carries no such source.
        """
        entry = self._entry(cube_id, source)
        if entry is None:
            return None

        max_dim = self.VOLUME_MAX_DIM if max_dim is None else int(np.clip(max_dim, 2, 256))
        cube    = entry["cube"]

        strides = tuple(max(1, int(np.ceil(extent / max_dim))) for extent in cube.shape)
        block   = np.asarray(cube[:, ::strides[1], ::strides[2]], dtype=np.float32)[::strides[0]]

        if entry.get("diverging"):
            peak = max(abs(entry["vmin"]), abs(entry["vmax"]), 1e-12)
            vmin, vmax = -peak, peak
        else:
            vmin, vmax = float(entry["vmin"]), float(entry["vmax"])

        norm   = np.clip((np.nan_to_num(block, nan=vmin) - vmin) / max(vmax - vmin, 1e-12), 0.0, 1.0)
        voxels = np.round(norm * 255.0).astype(np.uint8)

        header = np.array([*voxels.shape, 1.0 if entry.get("diverging") else 0.0, vmin, vmax, 0.0, 0.0], dtype=np.float32)
        return header.tobytes() + np.ascontiguousarray(voxels).tobytes()

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

        median = self._dem_median(dem)
        grid   = (dem - median).astype(np.float32)

        header = np.array([dem.shape[0], dem.shape[1], median, 0.0], dtype=np.float32)
        return header.tobytes() + np.ascontiguousarray(grid).tobytes()

    def globe_points_bin(self, cube_id: str, source: str, amp_min: float, max_points: int, pauli_mode: str = "", win_az: int = 1, win_rg: int = 1, shared: bool = False, cmap: str = "viridis") -> bytes | None:
        """Packs a geocoded point cloud as ECEF offsets from the scene anchor.

        Scatterer elevations are added to the DEM terrain height at their pixel
        before geocoding, so points sit above ground on the globe. With a Pauli
        mode every row also carries the colour of its pixel in that Pauli map,
        so the scatterers can be painted by the scattering mechanism of the
        ground they stand on.

        Args:
            cube_id    : Id of the loaded cube.
            source     : Source to draw points from, restricted to GLOBE_SOURCES.
            amp_min    : Minimum amplitude for a point to be kept.
            max_points : Cap on emitted points before the terrain mask is applied.
            pauli_mode : One of PAULI_MODES to append the pixel colour of, or "" for no colour columns.
            win_az     : Multilook window of the Pauli map in azimuth pixels.
            win_rg     : Multilook window of the Pauli map in range pixels.
            shared     : Whether every Pauli component is stretched over one pooled dB range rather than its own percentiles.
            cmap       : Colormap painting a single Pauli component's power, one of CMAPS.

        Returns:
            A four-float32 header (emitted count, pre-mask total, columns per
            row, 0) followed by rows of (ECEF x, y, z offsets in metres,
            elevation in metres, amplitude) plus red, green and blue in [0, 1]
            when a Pauli mode was given, or None when the cube has no
            geocoding, the source is not globe-renderable, or a Pauli mode was
            given without a polarimetric primary or with an unknown mode or
            colormap.
        """
        with self.lock:
            if self.loaded is None or self.loaded["id"] != cube_id:
                return None
            geo       = self.loaded["geo"]
            param_tag = self.loaded["param_tag"]
            pauli     = self.loaded["pauli"]

        if geo is None or source not in self.GLOBE_SOURCES:
            return None
        if pauli_mode and (pauli is None or pauli_mode not in self.PAULI_MODES or cmap not in self.CMAPS):
            return None

        window = self._pauli_window(win_az, win_rg)
        key    = f"{cube_id}|{param_tag}|{source}|{amp_min!r}|{max_points}"
        if pauli_mode:
            key = f"{key}|{pauli_mode}|{window}" + ("" if pauli_mode == "dominant" else f"|{shared}|{cmap}")
        cached = self.globe_blobs.get(key)
        if cached is not None:
            return cached

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

        columns = [offsets, rows[:, 2:3], rows[:, 3:4]]
        if pauli_mode:
            image = self._pauli_raster(self._pauli_powers(pauli, window), pauli_mode, shared, cmap)
            columns.append(image[az_idx, rg_idx])

        globe_rows = np.concatenate(columns, axis=1).astype(np.float32)
        header     = np.array([globe_rows.shape[0], total, globe_rows.shape[1], 0.0], dtype=np.float32)
        blob       = header.tobytes() + np.ascontiguousarray(globe_rows).tobytes()

        if len(blob) <= self.GLOBE_BLOB_MAX_BYTES:
            self.globe_blobs.put(key, blob)
        return blob

    def globe_pauli_png(self, cube_id: str, mode: str, win_az: int, win_rg: int, shared: bool, cmap: str, width: int | None = None) -> tuple | None:
        """Renders one Pauli map as a north-up RGBA image over the scene footprint for the globe drape.

        The map is resampled onto a longitude/latitude grid of square ground
        cells, transparent outside the footprint, so Cesium can drape it as one
        imagery tile. The cell count follows the ground, GLOBE_CELLS_PER_PIXEL
        cells per pixel of the finer axis along the longer side up to the width
        cap, and the multilook window is widened per axis to at least the
        pixels one cell covers, so every cell shows the mean of the pixels it
        stands for rather than a single speckled sample. The footprint lookup
        is cached per cube and width cap, so only the painting repeats per mode
        and scheme.

        Args:
            cube_id : Id of the loaded cube.
            mode    : One of PAULI_MODES.
            win_az  : Multilook window in azimuth pixels.
            win_rg  : Multilook window in range pixels.
            shared  : Whether every component is stretched over one pooled dB range rather than its own percentiles.
            cmap    : Colormap painting a single component's power, one of CMAPS.
            width   : Cap on the cell count along the longer ground side; GLOBE_IMAGE_WIDTH when None.

        Returns:
            Tuple of PNG bytes, the rectangle [west, south, east, north] in
            degrees the image spans and the (azimuth, range) window rendered,
            or None when the cube has no geocoding, no polarimetric primary, or
            the mode or colormap is unknown.
        """
        with self.lock:
            if self.loaded is None or self.loaded["id"] != cube_id:
                return None
            geo = self.loaded["geo"]
            ctx = self.loaded["pauli"]

        if geo is None or ctx is None or mode not in self.PAULI_MODES or cmap not in self.CMAPS:
            return None

        footprint = self._footprint(geo, self.GLOBE_IMAGE_WIDTH if width is None else int(width))
        step      = footprint["plan"]["step"]
        window    = self._pauli_window(max(int(win_az), step[0]), max(int(win_rg), step[1]))

        image = self._pauli_raster(self._pauli_powers(ctx, window), mode, shared, cmap)
        rgba  = footprint["resampler"].paint(image, footprint["geometry"])

        buf = io.BytesIO()
        plt.imsave(buf, rgba, **self.PNG_ENCODE)
        return buf.getvalue(), [float(value) for value in footprint["geometry"]["rect"]], window

    def _footprint(self, geo: dict, width: int) -> dict:
        """Returns the north-up lookup of the loaded cube's footprint for a width cap, building and caching it on first use.

        Args:
            geo   : Geocoding context of the loaded cube.
            width : Cap on the cell count along the longer ground side.

        Returns:
            Dict with the ``resampler`` bound to the footprint, its ``plan`` (width, per-axis step, cell and pixel spacing) and the ``geometry`` lookup.
        """
        cache = geo.setdefault("footprint", {})
        entry = cache.get(width)
        if entry is not None:
            return entry

        resampler = FootprintImage(geo["geocoder"], geo["dem"], geo["az0"], geo["rg0"])
        plan      = resampler.plan(self.GLOBE_CELLS_PER_PIXEL, width)
        entry     = {"resampler": resampler, "plan": plan, "geometry": resampler.geometry(plan["width"], plan["step"])}

        cache.clear()
        cache[width] = entry
        return entry

    def _warm_globe_blobs(self, cube_id: str) -> None:
        """Precomputes the default-view globe blob of every source into the cache.

        Runs after a cube load so the first globe render and subsequent source
        swaps are served from cache instead of rescanning the memory-mapped
        cubes. The warmed requests are exactly the ones the front end issues at
        its default threshold and point budget, because both sides read them from
        the ``globe_defaults`` block of the cube metadata.

        Args:
            cube_id: Id of the freshly loaded cube.
        """
        with self.lock:
            if self.loaded is None or self.loaded["id"] != cube_id:
                return
            defaults = self.loaded["meta"]["globe_defaults"]

        if defaults is None:
            return

        for source, amp_min in defaults["amp_min"].items():
            self.globe_points_bin(cube_id, source, amp_min, defaults["max_points"])

    def save_globe_tour(self, cube_id: str, move: str, clip: bytes) -> dict:
        """Writes a globe camera tour rendered in the browser into the run that owns the cube.

        The clip arrives as the MP4 the front end encoded frame by frame off the
        Cesium canvas and is stored beside the other figures of the run, one
        file per rendering, stamped with the move and the wall-clock time.

        Args:
            cube_id: Id of the loaded cube whose run receives the clip.
            move: Key of the camera move that was rendered, used in the file name.
            clip: Encoded MP4 bytes.

        Returns:
            Dict with ``ok``, the absolute output ``dir``, its path ``rel`` to
            the run, the written ``file`` and its size in ``bytes``, or ``ok``
            False with the reason.
        """
        with self.lock:
            if self.loaded is None or self.loaded["id"] != cube_id:
                return {"ok": False, "error": "cube not loaded"}

        reader = self._open_source(cube_id)
        if reader is None:
            return {"ok": False, "error": f"unknown cube id: {cube_id}"}
        if not clip:
            return {"ok": False, "error": "the recorder uploaded an empty clip"}
        if len(clip) > self.GLOBE_TOUR_MAX_BYTES:
            return {"ok": False, "error": f"the clip is {len(clip) / 1048576:.0f} MB, over the {self.GLOBE_TOUR_MAX_BYTES // 1048576} MB limit"}

        name   = self.GLOBE_TOUR_NAME_RE.sub("_", move.lower()).strip("_") or "tour"
        rel    = self.GLOBE_TOUR_DIR / f"{name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.mp4"
        target = reader.save_dir / rel

        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(clip)

        self.logger.ok(f"saved a {len(clip) / 1048576:.1f} MB globe tour to {target}")
        return {"ok": True, "dir": str(target.parent), "rel": str(rel), "file": target.name, "bytes": len(clip)}

    def list_figures(self, cube_id: str) -> dict:
        """Lists the figure and animation files saved under a preprocessing run.

        Walks the run's FIGURE_DIRS trees: the preprocessing figures under
        ``images``, the cuts printed from this console under ``figures`` and
        the parameter-extraction figures under ``params``.

        Args:
            cube_id : Id of the loaded cube.

        Returns:
            Dict with ``ok`` and ``groups``, one entry per directory holding figures, each with its path relative to the run and its file names.
        """
        with self.lock:
            if self.loaded is None or self.loaded["id"] != cube_id:
                return {"ok": False, "error": "cube not loaded"}

        reader = self._open_source(cube_id)
        if reader is None:
            return {"ok": False, "error": f"unknown cube id: {cube_id}"}

        groups = {}
        for root_name in self.FIGURE_DIRS:
            root = reader.run_dir / root_name
            if not root.is_dir():
                continue

            for path in sorted(root.rglob("*")):
                if not path.is_file() or path.suffix.lower() not in self.FIGURE_SUFFIXES:
                    continue
                rel = path.relative_to(reader.run_dir)
                groups.setdefault(str(rel.parent), []).append(rel.name)

        return {"ok": True, "groups": [{"dir": name, "files": files} for name, files in sorted(groups.items())]}

    def figure_file(self, cube_id: str, rel: str) -> Path | None:
        """Resolves one figure file of the loaded run for serving.

        Args:
            cube_id : Id of the loaded cube.
            rel     : Path of the figure relative to the run directory.

        Returns:
            The absolute file path, or None when the cube is not loaded, the path escapes the run's figure trees or the suffix is not an allowed figure type.
        """
        with self.lock:
            if self.loaded is None or self.loaded["id"] != cube_id:
                return None

        reader = self._open_source(cube_id)
        if reader is None:
            return None

        target = (reader.run_dir / rel).resolve()
        roots  = [(reader.run_dir / name).resolve() for name in self.FIGURE_DIRS]

        if not any(target.is_relative_to(root) for root in roots):
            return None
        if target.suffix.lower() not in self.FIGURE_SUFFIXES or not target.is_file():
            return None

        return target

    def pass_map_png(self, cube_id: str, kind: str, index: int, cmap: str = "gray") -> bytes | None:
        """Renders one acquisition pass of the raw input stack as a PNG.

        Args:
            cube_id : Id of the loaded cube.
            kind    : "amplitude" for the SLC amplitude in dB, "phase" for the interferometric phase against the primary.
            index   : Pass index, 0 being the primary; phase exists for indices 1 and up only.
            cmap    : Colormap for amplitude maps; phase always uses the cyclic twilight map.

        Returns:
            PNG bytes of the (azimuth, range) map, or None when the cube is not loaded, the stack is unavailable or the kind and index do not name a renderable map.
        """
        with self.lock:
            if self.loaded is None or self.loaded["id"] != cube_id:
                return None
            ctx = self.loaded["passes"]

        if ctx is None:
            return None

        index = int(index)

        if kind == "amplitude":
            if index == 0:
                crop = np.asarray(np.load(ctx["primary"], mmap_mode="r"))
            else:
                raw = np.load(ctx["secondaries"], mmap_mode="r")
                if not 1 <= index <= raw.shape[0]:
                    return None
                crop = np.asarray(raw[index - 1])

            db         = 20.0 * np.log10(np.maximum(np.abs(crop).astype(np.float32), 1e-12))
            vmin, vmax = np.percentile(db, [1.0, 99.0])
            data       = db
            palette    = cmap if cmap in self.CMAPS else "gray"
        elif kind == "phase":
            if ctx["interferograms"] is None or index < 1:
                return None
            raw = np.load(ctx["interferograms"], mmap_mode="r")
            if index > raw.shape[0]:
                return None
            data       = np.angle(np.asarray(raw[index - 1]))
            vmin, vmax = -np.pi, np.pi
            palette    = "twilight"
        else:
            return None

        buf = io.BytesIO()
        plt.imsave(buf, data, cmap=palette, vmin=float(vmin), vmax=float(vmax), **self.PNG_ENCODE)
        return buf.getvalue()

    def transect_png(self, cube_id: str, source: str, points: list, space: str = "physical", cmap: str = "jet", dem: bool = False) -> bytes | None:
        """Renders an elevation section along an arbitrary polyline as a PNG.

        Args:
            cube_id : Id of the loaded cube.
            source  : Cube key to render.
            points  : Ordered (azimuth, range) vertices of the polyline, at least two after clipping.
            space   : "normalized" to peak-normalise columns, else "physical".
            cmap    : Colormap name; diverging sources always use coolwarm.
            dem     : When True and the run carries a DEM, every sample column is shifted vertically by its median-referenced terrain height.

        Returns:
            PNG bytes, or None when the cube carries no such source or the
            polyline has fewer than two distinct vertices.
        """
        entry = self._entry(cube_id, source)
        if entry is None:
            return None

        n_elev, n_az, n_rg = entry["cube"].shape
        points = self._clip_points(points, n_az, n_rg)
        if points is None:
            return None

        az_idx, rg_idx = self._path_indices(points)
        data, heights, vmin, vmax = self._transect_cut(entry, az_idx, rg_idx, space)
        track = self._transect_dem_track(cube_id, az_idx, rg_idx) if dem else None

        return self._cut_png(entry, data, heights, vmin, vmax, cmap, track)

    def save_transect(self, cube_id: str, points: list, space: str = "physical", cmap: str = "jet", dem: bool = False) -> dict:
        """Saves one transect figure per loaded source under the run's figures folder.

        Args:
            cube_id : Id of the loaded cube.
            points  : Ordered (azimuth, range) vertices of the polyline, clipped into range.
            space   : "physical" or "normalized".
            cmap    : Colormap name; diverging sources always use coolwarm.
            dem     : When True and the run carries a DEM, every sample column is shifted vertically by its median-referenced terrain height.

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

        points = self._clip_points(points, meta["n_az"], meta["n_rg"])
        if points is None:
            return {"ok": False, "error": "a transect needs at least two distinct points"}

        (az0, rg0), (az1, rg1) = points[0], points[-1]
        via     = f"_via{len(points) - 2}" if len(points) > 2 else ""
        rel     = Path("figures") / "cube_transects" / f"az{az0:04d}_rg{rg0:04d}_to_az{az1:04d}_rg{rg1:04d}{via}"
        out_dir = reader.save_dir / rel

        az_idx, rg_idx = self._path_indices(points)
        track          = self._transect_dem_track(cube_id, az_idx, rg_idx) if dem else None

        files = []
        for source in meta["sources"]:
            entry = entries[source]
            data, heights, vmin, vmax = self._transect_cut(entry, az_idx, rg_idx, space)
            if track is not None:
                data, heights = self._terrain_shift(data, heights, track, fill=self._terrain_fill(entry, vmin))
            saved = self.archiver.render_transect(data, heights, vmin, vmax, source, points, space, out_dir / f"transect_{source}_{space}.png", cmap=self._entry_cmap(entry, cmap))
            files.append(saved.name)

        self.logger.ok(f"saved {len(files)} transect figures to {out_dir}")
        return {"ok": True, "dir": str(out_dir), "rel": str(rel), "files": files}

    @staticmethod
    def _clip_points(points, n_az: int, n_rg: int) -> list | None:
        """Clips polyline vertices into the cube footprint and drops repeats.

        Args:
            points : Iterable of (azimuth, range) pairs.
            n_az   : Azimuth extent of the cube, in pixels.
            n_rg   : Range extent of the cube, in pixels.

        Returns:
            List of clipped integer vertices with consecutive duplicates
            removed, or None when fewer than two distinct vertices remain.
        """
        clipped = []
        for pair in points:
            az = int(np.clip(int(pair[0]), 0, n_az - 1))
            rg = int(np.clip(int(pair[1]), 0, n_rg - 1))
            if not clipped or clipped[-1] != (az, rg):
                clipped.append((az, rg))

        return clipped if len(clipped) >= 2 else None

    @classmethod
    def _path_indices(cls, points: list) -> tuple[np.ndarray, np.ndarray]:
        """Returns the sample indices tracing a polyline segment by segment.

        Args:
            points : Ordered (azimuth, range) vertices, at least two.

        Returns:
            Tuple of the integer azimuth and range index arrays along the whole
            polyline, each interior vertex sampled once.
        """
        az_parts = []
        rg_parts = []
        for (az0, rg0), (az1, rg1) in zip(points[:-1], points[1:]):
            az_idx, rg_idx = cls._line_indices(az0, rg0, az1, rg1)
            if az_parts:
                az_idx = az_idx[1:]
                rg_idx = rg_idx[1:]
            az_parts.append(az_idx)
            rg_parts.append(rg_idx)

        return np.concatenate(az_parts), np.concatenate(rg_parts)

    @classmethod
    def _transect_cut(cls, entry: dict, az_idx: np.ndarray, rg_idx: np.ndarray, space: str) -> tuple[np.ndarray, np.ndarray, float, float]:
        """Samples the cube along precomputed polyline indices.

        Args:
            entry  : Loaded cube entry.
            az_idx : Azimuth pixel index of every sample along the line.
            rg_idx : Range pixel index of every sample along the line.
            space  : "normalized" to peak-normalise columns, else "physical".

        Returns:
            Tuple of the section of shape (elevation bins, samples) ordered by
            ascending elevation, the elevation axis in metres, and the colour
            limits.
        """
        data = entry["cube"][:, az_idx, rg_idx]

        data, vmin, vmax = cls._normalize_cut(entry, data, space)

        order   = np.argsort(entry["x_axis"])
        heights = np.asarray(entry["x_axis"], dtype=np.float64)[order]
        return data[order], heights, float(vmin), float(vmax)

    def save_slices(self, cube_id: str, az: int, rg: int, space: str = "physical", cmap: str = "jet", dem: bool = False) -> dict:
        """Saves the range and azimuth slice of every loaded source at one pixel.

        Args:
            cube_id: Id of the loaded cube.
            az: Azimuth pixel index, clipped into range.
            rg: Range pixel index, clipped into range.
            space: "physical" or "normalized".
            cmap: Colormap name; diverging sources always use coolwarm.
            dem: When True and the run carries a DEM, every column is shifted
                vertically by its median-referenced terrain height.

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

        tracks = {axis: self._slice_dem_track(cube_id, axis, az, rg) for axis in ("range", "azimuth")} if dem else {}

        files = []
        for source in meta["sources"]:
            for axis in ("range", "azimuth"):
                track = tracks.get(axis)
                data, heights, vmin, vmax = self._cut(entries[source], axis, az, rg, space)
                if track is not None:
                    data, heights = self._terrain_shift(data, heights, track, fill=self._terrain_fill(entries[source], vmin))
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

    def _slice_dem_track(self, cube_id: str, axis: str, az: int, rg: int) -> np.ndarray | None:
        """Returns the median-referenced DEM terrain heights along one slice.

        The heights are referenced to the median terrain height, expressing the
        column shifts on the tomogram's elevation axis with the same convention
        as the point-cloud drape grid.

        Args:
            cube_id: Id of the loaded cube.
            axis: "range" for a fixed range column, "azimuth" for a fixed azimuth row.
            az: Azimuth pixel index of the azimuth cut, already clipped.
            rg: Range pixel index of the range cut, already clipped.

        Returns:
            Float64 median-referenced heights in metres, one per sample column of
            the slice, or None when the cube carries no DEM.
        """
        dem = self._dem_relative(cube_id)
        if dem is None:
            return None

        return dem[:, rg] if axis == "range" else dem[az, :]

    def _transect_dem_track(self, cube_id: str, az_idx: np.ndarray, rg_idx: np.ndarray) -> np.ndarray | None:
        """Returns the median-referenced DEM terrain heights along a transect polyline.

        The heights follow the same median reference as the slice tracks.

        Args:
            cube_id : Id of the loaded cube.
            az_idx  : Azimuth pixel index of every sample along the line, already clipped.
            rg_idx  : Range pixel index of every sample along the line, already clipped.

        Returns:
            Float64 median-referenced heights in metres, one per transect sample,
            or None when the cube carries no DEM.
        """
        dem = self._dem_relative(cube_id)
        if dem is None:
            return None

        return dem[az_idx, rg_idx]

    def _dem_relative(self, cube_id: str) -> np.ndarray | None:
        """Returns the loaded cube's DEM referenced to its median terrain height.

        The grid is built once at load time, so slice and transect tracks index
        into it instead of rebuilding it per request.

        Args:
            cube_id: Id of the loaded cube.

        Returns:
            Float64 median-referenced heights in metres of shape (azimuth,
            range), or None when that cube is not loaded or carries no DEM.
        """
        with self.lock:
            if self.loaded is None or self.loaded["id"] != cube_id:
                return None
            return self.loaded["dem_relative"]

    @classmethod
    def _dem_relative_grid(cls, dem: np.ndarray | None) -> np.ndarray | None:
        """Returns a DEM as float64 heights relative to its median, or None for no DEM."""
        if dem is None:
            return None
        return np.asarray(dem, dtype=np.float64) - cls._dem_median(dem)

    @staticmethod
    def _dem_median(dem: np.ndarray) -> float:
        """Returns the median of the DEM's finite heights in metres, 0.0 when none are."""
        finite = np.isfinite(dem)
        return float(np.median(dem[finite])) if finite.any() else 0.0

    @staticmethod
    def _line_indices(az0: int, rg0: int, az1: int, rg1: int) -> tuple[np.ndarray, np.ndarray]:
        """Returns nearest-neighbour (azimuth, range) indices sampling a straight line.

        The line is sampled at one point per pixel of its longer axis.

        Args:
            az0: Azimuth pixel index of the start point.
            rg0: Range pixel index of the start point.
            az1: Azimuth pixel index of the end point.
            rg1: Range pixel index of the end point.

        Returns:
            Tuple of the integer azimuth and range index arrays, both of the same
            length.
        """
        samples = int(max(abs(az1 - az0), abs(rg1 - rg0))) + 1
        az_idx  = np.round(np.linspace(az0, az1, samples)).astype(int)
        rg_idx  = np.round(np.linspace(rg0, rg1, samples)).astype(int)
        return az_idx, rg_idx

    def _cut_png(self, entry: dict, data: np.ndarray, heights: np.ndarray, vmin: float, vmax: float, cmap: str, track: np.ndarray | None) -> bytes:
        """Encodes one vertical cut as PNG bytes, optionally terrain-corrected.

        Args:
            entry: Loaded cube entry, selecting the effective colormap.
            data: Cut of shape (elevation bins, samples), ascending elevation.
            heights: Elevation axis in metres, ascending, one entry per row.
            vmin: Lower colour limit.
            vmax: Upper colour limit.
            cmap: Requested colormap name.
            track: Median-referenced DEM terrain heights in metres, one per
                sample column, shifting each column onto the terrain, or None
                for the plain cut.

        Returns:
            PNG bytes of the cut, top row at the highest elevation. Cells the
            shifted columns leave uncovered carry the entry's background value,
            blending with the empty tomogram background.
        """
        if track is not None:
            data, _ = self._terrain_shift(data, heights, track, fill=self._terrain_fill(entry, vmin))

        buf = io.BytesIO()
        plt.imsave(buf, np.flipud(data), cmap=self._entry_cmap(entry, cmap), vmin=vmin, vmax=vmax, **self.PNG_ENCODE)
        return buf.getvalue()

    @staticmethod
    def _terrain_fill(entry: dict, vmin: float) -> float:
        """Returns the background value uncovered terrain-shift cells take.

        Diverging sources centre on zero, so their empty background is 0; every
        other source fills with the lower colour limit.

        Args:
            entry: Loaded cube entry, whose ``diverging`` flag selects the value.
            vmin: Lower colour limit of the cut.

        Returns:
            The fill value in the cut's value space.
        """
        return 0.0 if entry.get("diverging") else float(vmin)

    @staticmethod
    def _terrain_shift(data: np.ndarray, heights: np.ndarray, track: np.ndarray, fill: float) -> tuple[np.ndarray, np.ndarray]:
        """Shifts every column of a cut vertically by its terrain height.

        Each column moves up by its median-referenced terrain height, rounded to
        whole elevation bins, and the elevation axis is extended to hold the
        shifted span. Cells no column covers take the fill value, and columns
        whose terrain height is NaN are filled entirely.

        Args:
            data: Cut of shape (elevation bins, samples), ascending elevation.
            heights: Elevation axis in metres, ascending, one entry per row.
            track: Median-referenced DEM terrain heights in metres, one per
                sample column.
            fill: Value written into cells the shifted columns leave uncovered,
                typically the cut's background value.

        Returns:
            Tuple of the float32 shifted cut of shape (extended bins, samples)
            and its extended ascending elevation axis in metres, sharing the
            original bin size.
        """
        n_elev = int(data.shape[0])
        if n_elev < 2:
            return np.asarray(data, dtype=np.float32), np.asarray(heights, dtype=np.float64)

        bin_m  = float(heights[-1] - heights[0]) / (n_elev - 1)
        track  = np.asarray(track, dtype=np.float64)
        finite = np.isfinite(track)

        offsets         = np.zeros(track.size, dtype=int)
        offsets[finite] = np.round(track[finite] / bin_m).astype(int)

        lo = int(offsets[finite].min()) if finite.any() else 0
        hi = int(offsets[finite].max()) if finite.any() else 0

        shifted = np.full((n_elev + hi - lo, data.shape[1]), np.float32(fill), dtype=np.float32)

        cols = np.flatnonzero(finite)
        rows = (offsets[cols] - lo)[None, :] + np.arange(n_elev)[:, None]
        shifted[rows, cols[None, :]] = np.asarray(data, dtype=np.float32)[:, cols]

        shifted_heights = float(heights[0]) + (np.arange(shifted.shape[0]) + lo) * bin_m
        return shifted, shifted_heights

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

    def _open_source(self, cube_id: str, progress: LoadProgress | None = None) -> StampReader | None:
        """Resolves a cube id to a preprocessing run reader.

        Args:
            cube_id  : Preprocessing run directory path.
            progress : Byte counter the reader's whole-file reads report to; a silent counter when None.

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
        return StampReader(run_dir, LoadProgress() if progress is None else progress)

    def _load_worker(self, cube_id: str, reader: StampReader, param_tag: str | None) -> None:
        """Loads a cube in the background and publishes the ready or error status.

        Args:
            cube_id: Id being loaded.
            reader: Reader opened for that id.
            param_tag: Parameter run loaded alongside the raw cube, or None.
        """
        try:
            entries, meta, primary, dem, geo, passes, pauli, timer = self._load_all(reader, param_tag)
            clim            = self._primary_clim(primary)
            meta["timings"] = {"total": round(timer.total(), 3), "stages": timer.stages}

            with self.lock:
                self.loaded = {"id": cube_id, "param_tag": param_tag, "entries": entries, "meta": meta, "primary": primary, "primary_clim": clim, "dem": dem, "dem_relative": self._dem_relative_grid(dem), "geo": geo, "passes": passes, "pauli": pauli}
                self.status = {"state": "ready", "id": cube_id, "progress": 1.0, "stage": "ready", "error": ""}
                self.cube_cache.put(reader.cache_key(param_tag), self.loaded)

            self.logger.info(f"cube ready in {timer.total():.1f} s: {cube_id} sources={meta['sources']} ({timer.summary()})")
        except Exception as exc:
            with self.lock:
                self.loaded = None
                self.status = {"state": "error", "id": cube_id, "progress": 0.0, "stage": "", "error": str(exc)}

            self.logger.error(f"cube load failed: {cube_id}: {exc}")
            return

        warm = LoadTimer()
        self._warm_globe_blobs(cube_id)
        self.logger.muted(f"globe point cache warmed in {warm.total():.1f} s: {cube_id}")

    def _load_all(self, reader: StampReader, param_tag: str | None) -> tuple[dict, dict, np.ndarray, np.ndarray | None, dict | None, dict | None, dict | None, LoadTimer]:
        """Reads the tomogram, maps and geometry artifacts of one preprocessing run.

        Every stage books its wall time on a LoadTimer and names itself in the
        load status the front end polls, so a slow load names the stage that
        cost it; the progress fraction itself follows the bytes the reader's
        whole-file reads book against the plan made here.

        Args:
            reader: Preprocessing run reader to pull from.
            param_tag: Parameter run whose parametrized tomogram is loaded as
                the ``param`` source, or None for the raw cube alone.

        Returns:
            Tuple of the per-source entries, the front-end metadata payload, the
            primary amplitude map in dB of shape (azimuth, range), the DEM in
            metres, the geocoding context, the raw pass-stack context, the
            polarimetric context and the stage timer; DEM and geocoding are None
            when the scene cannot be geolocated, the pass context when the run
            stores no secondary stack, the polarimetric context when the run
            lists no polarimetric primary.

        Raises:
            ValueError: If the tomogram is not three-dimensional or its footprint
                disagrees with the recorded global crop.
        """
        timer = LoadTimer()

        def stage(name: str, load):
            """Names the running stage in the load status, runs it and books its time."""
            with self.lock:
                self.status["stage"] = name
                self.status_at       = time.perf_counter()

            result = load()
            timer.lap(name)
            return result

        reader.npy.progress.plan(reader.byte_plan(param_tag))

        full_raw = stage("full", reader.tomogram)
        if full_raw.ndim != 3:
            raise ValueError(f"full tomogram is not a 3D cube: shape={full_raw.shape}")

        n_elev, n_az, n_rg = full_raw.shape

        az_lo, az_hi, rg_lo, rg_hi = reader.global_crop()
        if (az_hi - az_lo, rg_hi - rg_lo) != (n_az, n_rg):
            raise ValueError(f"global_crop {[az_lo, az_hi, rg_lo, rg_hi]} does not match the {n_az}x{n_rg} tomogram footprint")

        x_axis  = self._elevation_axis(reader, n_elev)
        entries = {"full": stage("full", lambda: self._ingest(full_raw, x_axis))}

        if param_tag is not None:
            entries["param"] = stage("param", lambda: self._param_entry(reader, param_tag, n_az, n_rg, x_axis))

        primary = stage("primary",   lambda: self._primary_db(reader, n_az, n_rg))
        dem     = stage("dem",       lambda: self._load_dem(reader, n_az, n_rg))
        geo     = stage("geocoding", lambda: self._load_geo(reader, dem, n_az, n_rg))
        passes  = stage("passes",    lambda: self._load_passes(reader, n_az, n_rg))
        pauli   = stage("pauli",     lambda: self._load_polarimetry(reader, n_az, n_rg))

        meta = {
            "sources"   : [s for s in self.SOURCES if s in entries],
            "n_az"      : n_az,
            "n_rg"      : n_rg,
            "n_elev"    : {s: int(entries[s]["cube"].shape[0]) for s in entries},
            "x_min"     : float(x_axis[0]),
            "x_max"     : float(x_axis[-1]),
            "intensity" : {s: [entries[s]["vmin"], entries[s]["vmax"]] for s in entries},
            "param"     : self._param_meta_payload(entries.get("param")),
            "dem"       : dem is not None,
            "spacing"   : self._load_spacing(reader, n_rg),
            "globe"     : self._globe_meta(geo),
            "passes"    : self._passes_meta(passes),
            "pauli"     : self._pauli_meta(pauli),
        }
        meta["globe_defaults"] = self._globe_defaults(meta)

        return entries, meta, primary, dem, geo, passes, pauli, timer

    def _globe_defaults(self, meta: dict) -> dict | None:
        """Returns the globe request every source is first served with.

        Both the server-side warm and the front end read this block, so the
        default amplitude floor and point budget have one authority and the warmed
        cache entries are the ones the first request looks up.

        Args:
            meta: Cube metadata built so far, carrying the globe block, the source
                list and the per-source intensity ranges.

        Returns:
            Dict with the default ``max_points`` budget and the ``amp_min`` floor
            of every globe-renderable source, or None when the scene has no
            geocoding and the globe cannot be drawn.
        """
        if meta["globe"] is None:
            return None

        amp_min = {source: float(meta["intensity"][source][0]) for source in self.GLOBE_SOURCES if source in meta["sources"]}
        return {"max_points": self.GLOBE_DEFAULT_POINTS, "amp_min": amp_min}

    def _param_entry(self, reader: StampReader, tag: str, n_az: int, n_rg: int, x_axis: np.ndarray) -> dict:
        """Builds the lazily reconstructed parametrized-tomogram entry of one run.

        Args:
            reader: Preprocessing run reader.
            tag: Parameter run tag under the run's ``params`` directory.
            n_az: Azimuth extent of the raw tomogram, in pixels.
            n_rg: Range extent of the raw tomogram, in pixels.
            x_axis: Elevation axis of the raw tomogram in metres.

        Returns:
            Entry with the lazy ``cube``, its ``x_axis``, deterministic colour
            limits from a reconstruction subsample, the raw parameter ``params``
            block, the ``tag``, the ``n_gaussians`` slot count and the recorded
            ``k_max``.

        Raises:
            ValueError: If the parameter cube is misshaped, its footprint
                disagrees with the tomogram or its slot count disagrees with the
                recorded ``k_max``.
        """
        block = reader.param_block(tag)
        meta  = reader.param_meta(tag)

        if block.ndim != 3 or block.shape[0] % 3 != 0:
            raise ValueError(f"parameters.npy of '{tag}' is not a (3*k, azimuth, range) cube: shape={block.shape}")
        if block.shape[1:] != (n_az, n_rg):
            raise ValueError(f"parameters.npy of '{tag}' footprint {block.shape[1:]} does not match the {n_az}x{n_rg} tomogram")

        n_gaussians = block.shape[0] // 3
        k_max       = int(meta["k_max"])
        if n_gaussians != k_max:
            raise ValueError(f"parameters.npy of '{tag}' holds {n_gaussians} slots but its metadata records k_max={k_max}")

        cube       = ParametrizedTomogram(block, x_axis, n_gaussians)
        vmin, vmax = cube.clim()

        return {
            "cube"        : cube,
            "x_axis"      : x_axis,
            "vmin"        : vmin,
            "vmax"        : vmax,
            "params"      : block,
            "tag"         : tag,
            "n_gaussians" : n_gaussians,
            "k_max"       : k_max,
        }

    @staticmethod
    def _param_meta_payload(entry: dict | None) -> dict | None:
        """Serialises the loaded parameter run for the front end.

        Args:
            entry: Loaded ``param`` entry, or None when no parameter run is loaded.

        Returns:
            Dict with the ``tag``, ``n_gaussians``, ``k_max`` and the finite
            value range of each parameter field across all slots, or None.
        """
        if entry is None:
            return None

        block  = entry["params"]
        fields = {}
        for offset, name in enumerate(("amplitude", "mean", "sigma")):
            values       = block[offset::3]
            finite       = values[np.isfinite(values)]
            fields[name] = [float(finite.min()), float(finite.max())] if finite.size else [0.0, 0.0]

        return {
            "tag"         : entry["tag"],
            "n_gaussians" : entry["n_gaussians"],
            "k_max"       : entry["k_max"],
            "fields"      : fields,
        }

    def pauli_png(self, cube_id: str, mode: str, win_az: int, win_rg: int, shared: bool, cmap: str = "viridis") -> bytes | None:
        """Renders the Pauli decomposition of the primary pass as a PNG.

        Args:
            cube_id : Id of the loaded cube.
            mode    : "rgb" for the composite (red double bounce, green volume, blue surface), a component key for its multilooked power in dB, or "dominant" for the strongest mechanism per pixel.
            win_az  : Multilook window in azimuth pixels.
            win_rg  : Multilook window in range pixels.
            shared  : Whether every component is stretched over one pooled dB range rather than its own percentiles.
            cmap    : Colormap painting a single component's power, one of CMAPS.

        Returns:
            PNG bytes of the (azimuth, range) map cropped to the cube footprint, or
            None when the cube is not loaded, carries no polarimetric primary or
            the mode or colormap is unknown.
        """
        ctx = self._pauli_context(cube_id)
        if ctx is None or mode not in self.PAULI_MODES or cmap not in self.CMAPS:
            return None

        entry = self._pauli_powers(ctx, self._pauli_window(win_az, win_rg))
        image = self._pauli_raster(entry, mode, shared, cmap)

        buf = io.BytesIO()
        plt.imsave(buf, image, **self.PNG_ENCODE)
        return buf.getvalue()

    def pauli_value_at(self, cube_id: str, az: int, rg: int, win_az: int, win_rg: int) -> dict:
        """Reads the Pauli powers, mechanism shares and channel ratios at one pixel.

        Args:
            cube_id : Id of the loaded cube.
            az      : Azimuth pixel index, clipped into range.
            rg      : Range pixel index, clipped into range.
            win_az  : Multilook window in azimuth pixels.
            win_rg  : Multilook window in range pixels.

        Returns:
            Dict with ``ok``, the clipped indices, the ``window`` used, whether
            the window holds data (``valid``), the component powers in ``db``,
            their ``fractions`` of the span, the ``dominant`` component key
            (None where the window holds no data), the ``span_db`` and the
            co-polar ``hh_vv_db`` and cross-polar ``hv_hh_db`` ratios in dB.
        """
        ctx = self._pauli_context(cube_id)
        if ctx is None:
            return {"ok": False, "error": "this cube has no polarimetric primary"}

        window = self._pauli_window(win_az, win_rg)
        entry  = self._pauli_powers(ctx, window)
        powers = entry["powers"]

        az = int(np.clip(az, 0, powers.shape[1] - 1))
        rg = int(np.clip(rg, 0, powers.shape[2] - 1))

        fractions = PauliDecomposer.fractions(powers[:, az:az + 1, rg:rg + 1])[:, 0, 0]
        decibel   = entry["db"][:, az, rg]
        dominant  = int(entry["dominant"][az, rg])
        ratios    = self._pauli_ratios(powers[:, az, rg], entry["copolar"][:, az, rg])

        return {
            "ok"        : True,
            "az"        : az,
            "rg"        : rg,
            "window"    : list(window),
            "valid"     : dominant >= 0,
            "db"        : {key: float(decibel[index]) for index, key in enumerate(PauliDecomposer.COMPONENTS)},
            "fractions" : {key: float(fractions[index]) for index, key in enumerate(PauliDecomposer.COMPONENTS)},
            "dominant"  : None if dominant < 0 else PauliDecomposer.COMPONENTS[dominant],
            **ratios,
        }

    def pauli_summary(self, cube_id: str, win_az: int, win_rg: int, shared: bool) -> dict:
        """Summarises the decomposition over the whole cube footprint.

        Args:
            cube_id : Id of the loaded cube.
            win_az  : Multilook window in azimuth pixels.
            win_rg  : Multilook window in range pixels.
            shared  : Whether every component is stretched over one pooled dB range rather than its own percentiles.

        Returns:
            Dict with ``ok``, the ``window`` used, the stretch ``bounds`` per
            component in dB, the ``scene_share`` of the summed span each
            component carries (the normalised diagonal of the scene-averaged
            coherency matrix, which does not depend on the multilook window),
            the ``dominant_share`` of data-holding pixels each component wins,
            their count ``n_pixels``, the count ``n_nodata`` of pixels whose
            window holds no data, and the scene-mean ``span_db``, co-polar
            ``hh_vv_db`` and cross-polar ``hv_hh_db`` in dB.
        """
        ctx = self._pauli_context(cube_id)
        if ctx is None:
            return {"ok": False, "error": "this cube has no polarimetric primary"}

        window   = self._pauli_window(win_az, win_rg)
        entry    = self._pauli_powers(ctx, window)
        valid    = entry["valid"]
        bounds   = PauliDecomposer.stretch_bounds(entry["db"], shared, valid)
        n_pixels = int(np.count_nonzero(valid))

        total   = entry["powers"][:, valid].sum(axis=1, dtype=np.float64)
        copolar = entry["copolar"][:, valid].sum(axis=1, dtype=np.float64)
        share   = total / total.sum()

        return {
            "ok"             : True,
            "window"         : list(window),
            "bounds"         : {key: [bounds[key][0], bounds[key][1]] for key in PauliDecomposer.COMPONENTS},
            "scene_share"    : {key: float(share[index]) for index, key in enumerate(PauliDecomposer.COMPONENTS)},
            "dominant_share" : {key: float(np.count_nonzero(entry["dominant"] == index) / n_pixels) for index, key in enumerate(PauliDecomposer.COMPONENTS)},
            "n_pixels"       : n_pixels,
            "n_nodata"       : int(valid.size - n_pixels),
            **self._pauli_ratios(total / n_pixels, copolar / n_pixels),
        }

    @staticmethod
    def _pauli_ratios(powers: np.ndarray, copolar: np.ndarray) -> dict:
        """Returns the span and the channel ratios of one set of powers in dB.

        Args:
            powers  : Pauli component powers of shape (3,), surface, double bounce and volume.
            copolar : Co-polar powers of shape (2,), |HH|^2 and |VV|^2.

        Returns:
            Dict with ``span_db`` (|HH|^2 + 2 |HV|^2 + |VV|^2), ``hh_vv_db`` (HH over VV) and ``hv_hh_db`` (HV over HH); the volume power is 2 |HV|^2.
        """
        decibel = lambda value: float(PauliDecomposer.decibel(np.asarray([value], dtype=np.float64))[0])

        return {
            "span_db"  : decibel(float(np.sum(powers))),
            "hh_vv_db" : decibel(float(copolar[0])) - decibel(float(copolar[1])),
            "hv_hh_db" : decibel(float(powers[2]) / 2.0) - decibel(float(copolar[0])),
        }

    def _pauli_context(self, cube_id: str) -> dict | None:
        """Returns the polarimetric context of the loaded cube, or None when the id or the artifact is absent."""
        with self.lock:
            if self.loaded is None or self.loaded["id"] != cube_id:
                return None
            return self.loaded["pauli"]

    def _pauli_window(self, win_az: int, win_rg: int) -> tuple:
        """Clamps a requested multilook window into [1, PAULI_WINDOW_MAX] per axis."""
        return (int(np.clip(int(win_az), 1, self.PAULI_WINDOW_MAX)), int(np.clip(int(win_rg), 1, self.PAULI_WINDOW_MAX)))

    def _pauli_powers(self, ctx: dict, window: tuple) -> dict:
        """Returns the decomposition at one window, computing and caching it on first use.

        The boxcar reads up to half a window beyond the cube footprint wherever
        the artifact covers it, so the reflect boundary of the filter only acts
        at the edge of the preprocessing crop. Concurrent requests for the same
        window compute it once: the context lock serialises the miss.

        Args:
            ctx    : Polarimetric context of the loaded cube.
            window : Multilook window as (azimuth, range) pixels.

        Returns:
            Dict with the multilooked ``powers`` of shape (3, azimuth, range) in
            float32, the same in ``db``, the ``dominant`` component index map
            (-1 where the window holds no data), the ``valid`` mask and the
            ``copolar`` powers of shape (2, azimuth, range).
        """
        with ctx["lock"]:
            cached = ctx["cache"].get(window)
            if cached is not None:
                return cached

            az_lo, az_hi, rg_lo, rg_hi = ctx["bounds"]
            raw                        = np.load(ctx["path"], mmap_mode="r")

            pad_az_lo = min(window[0] // 2, az_lo)
            pad_az_hi = min(window[0] - window[0] // 2 - 1, raw.shape[1] - az_hi)
            pad_rg_lo = min(window[1] // 2, rg_lo)
            pad_rg_hi = min(window[1] - window[1] // 2 - 1, raw.shape[2] - rg_hi)

            stack      = np.asarray(raw[:, az_lo - pad_az_lo:az_hi + pad_az_hi, rg_lo - pad_rg_lo:rg_hi + pad_rg_hi])
            decomposer = PauliDecomposer(window)
            core       = (slice(None), slice(pad_az_lo, pad_az_lo + az_hi - az_lo), slice(pad_rg_lo, pad_rg_lo + rg_hi - rg_lo))
            powers     = decomposer.powers(stack)[core]
            copolar    = decomposer.copolar_powers(stack)[core]

            entry = {
                "powers"   : powers,
                "db"       : PauliDecomposer.decibel(powers),
                "dominant" : PauliDecomposer.dominant(powers),
                "valid"    : PauliDecomposer.valid(powers),
                "copolar"  : copolar,
            }
            ctx["cache"].put(window, entry)

            return entry

    @classmethod
    def _pauli_palette(cls) -> np.ndarray:
        """Returns the mechanism colours as a float RGB array of shape (3, 3) in component order."""
        return cls._hex_rgb([cls.PAULI_COLORS[key] for key in PauliDecomposer.COMPONENTS])

    def _pauli_raster(self, entry: dict, mode: str, shared: bool, cmap: str) -> np.ndarray:
        """Paints one Pauli map as a float RGB image.

        Args:
            entry  : Cached decomposition at the requested window.
            mode   : One of PAULI_MODES.
            shared : Whether every component is stretched over one pooled dB range rather than its own percentiles.
            cmap   : Colormap painting a single component's power, one of CMAPS.

        Returns:
            Float32 array of shape (azimuth, range, 3) with values in [0, 1]: the
            composite for "rgb", the mechanism colours for "dominant", the
            colormapped power otherwise; pixels without data paint black in the
            composite and the dominant map and in the map background colour in
            a single-component map.
        """
        valid  = entry["valid"]
        bounds = PauliDecomposer.stretch_bounds(entry["db"], shared, valid)

        if mode == "rgb":
            return PauliDecomposer.composite(entry["db"], bounds)
        if mode == "dominant":
            painted = self._pauli_palette()[np.maximum(entry["dominant"], 0)]
            return np.where(valid[..., None], painted, 0.0).astype(np.float32)

        index     = PauliDecomposer.COMPONENTS.index(mode)
        low, high = bounds[mode]
        norm      = np.clip((entry["db"][index] - low) / (high - low), 0.0, 1.0)
        painted   = plt.get_cmap(cmap)(norm)[..., :3]
        return np.where(valid[..., None], painted, self._hex_rgb([self.PAULI_NODATA])[0]).astype(np.float32)

    def _load_polarimetry(self, reader: StampReader, n_az: int, n_rg: int) -> dict | None:
        """Locates the polarimetric primary of a preprocessing run.

        Args:
            reader : Preprocessing run reader.
            n_az   : Azimuth extent of the tomogram, in pixels.
            n_rg   : Range extent of the tomogram, in pixels.

        Returns:
            Context with the artifact ``path``, the crop ``bounds`` into it, the
            default multilook ``window`` from its sidecar, an empty decomposition
            ``cache`` holding the last PAULI_CACHE_WINDOWS windows and the
            ``lock`` serialising its misses, or None when the run lists no
            polarimetric primary.

        Raises:
            FileNotFoundError : If the layout lists the artifact but the array or its sidecar is missing.
            ValueError        : If the array is not a three-channel stack over the tomogram footprint or the sidecar's channel order differs from the artifact contract.
        """
        name = reader.layout()["artifacts"].get(PolarimetricArtifact.ARTIFACT_KEY)
        if not name:
            return None

        path         = reader.run_dir / "data" / name
        sidecar_path = reader.run_dir / "meta" / PolarimetricArtifact.SIDECAR
        if not path.is_file():
            raise FileNotFoundError(f"dataset.json in {reader.where} lists {PolarimetricArtifact.ARTIFACT_KEY} but {path} is missing")
        if not sidecar_path.is_file():
            raise FileNotFoundError(f"polarimetric primary {path} has no sidecar {sidecar_path}; rerun the Extract Polarimetry entry (main/processing/extract_polarimetry.py) on this run")

        shape = np.load(path, mmap_mode="r").shape
        if len(shape) != 3 or shape[0] != 3:
            raise ValueError(f"polarimetric primary {path} has shape {shape}, expected (3, azimuth, range)")
        if shape[1:] != (n_az, n_rg):
            raise ValueError(f"polarimetric primary {path} footprint {shape[1:]} does not match the {n_az}x{n_rg} tomogram footprint")

        sidecar = json.loads(sidecar_path.read_text(encoding="utf-8"))
        if list(sidecar["channels"]) != list(PolarimetricArtifact.CHANNELS):
            raise ValueError(f"{sidecar_path} orders channels as {sidecar['channels']}, expected {list(PolarimetricArtifact.CHANNELS)}")

        window = self._pauli_window(sidecar["window"][0], sidecar["window"][1])

        return {"path": path, "bounds": (0, n_az, 0, n_rg), "window": window, "cache": LruCache(self.PAULI_CACHE_WINDOWS), "lock": threading.Lock()}

    @classmethod
    def _pauli_meta(cls, ctx: dict | None) -> dict | None:
        """Serialises the polarimetric context for the front end, or None without a polarimetric primary."""
        if ctx is None:
            return None

        components = [{"key": key, "label": cls.PAULI_LABELS[key], "color": cls.PAULI_COLORS[key]} for key in PauliDecomposer.COMPONENTS]
        return {"window": list(ctx["window"]), "window_max": cls.PAULI_WINDOW_MAX, "components": components, "modes": list(cls.PAULI_MODES)}

    def _load_spacing(self, reader: StampReader, n_rg: int) -> dict | None:
        """Returns the reference track's pixel spacings in metres and, with a geometry field, the ground-range spacing over the tomogram.

        Args:
            reader : Preprocessing run reader.
            n_rg   : Range extent of the tomogram, in pixels.

        Returns:
            Dict with the ``az`` and slant ``rg`` spacings, plus ``incidence_deg``
            (mean look angle over the tomogram's range columns) and
            ``ground_rg`` (slant spacing over the sine of that angle) when the
            run saved its geometry field, or None when the run stores no track
            parameters.

        Raises:
            ValueError : If the geometry field does not cover the tomogram's range columns.
        """
        params = reader.track_parameters()
        if params is None:
            return None

        reference = params.parameters[0]
        spacing   = {"az": float(reference["ps_az"]), "rg": float(reference["ps_rg"])}

        field_path = reader.run_dir / "meta" / GeometryField.FILENAME
        if not field_path.is_file():
            return spacing

        field = GeometryField.load(field_path)
        start = reader.global_crop()[2] - field.range_start
        look  = field.look_angle[max(start, 0):start + n_rg]
        if start < 0 or look.size != n_rg:
            raise ValueError(f"{field_path} covers range indices [{field.range_start}, {field.range_start + field.n_range}) but the tomogram needs [{start + field.range_start}, {start + field.range_start + n_rg})")

        incidence = float(np.mean(look))
        spacing["incidence_deg"] = float(np.degrees(incidence))
        spacing["ground_rg"]     = spacing["rg"] / math.sin(incidence)
        return spacing

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
            ECEF anchor of the scene centre, the lon/lat bounding box, the azimuth
            and ground-range scene-axis unit vectors, the flight lines when the
            run records its pass labels, and the beam segment; None when the
            track parameters lack the geocoding keys or the DEM holds no finite
            height.
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
            "axes"        : self._scene_axes(geocoder, az_start, rg_start, n_az, n_rg, base_height),
            "tracks"      : self._track_lines(params, pass_labels, az_start, n_az) if pass_labels is not None else None,
            "beam"        : self._beam_segment(geocoder, reference, dem, base_height, az_start, rg_start, n_az, n_rg),
        }

    @staticmethod
    def _scene_axes(geocoder: SceneGeocoder, az_start: int, rg_start: int, n_az: int, n_rg: int, base_height: float) -> dict:
        """Computes the ECEF unit vectors of the cube's azimuth and ground-range grid axes.

        Args:
            geocoder    : Scene geocoder of the reference track.
            az_start    : Azimuth origin of the cube in full-scene pixels.
            rg_start    : Range origin of the cube in full-scene pixels.
            n_az        : Azimuth extent of the cube, in pixels.
            n_rg        : Range extent of the cube, in pixels.
            base_height : Median terrain height in metres the axes are evaluated at.

        Returns:
            Dict with the ``azimuth`` and ``range`` ECEF unit vectors as float lists of length 3.
        """
        mid_az = az_start + n_az / 2
        mid_rg = rg_start + n_rg / 2

        _, _, az_ends = geocoder.geocode([az_start, az_start + n_az], [mid_rg, mid_rg], [base_height, base_height])
        _, _, rg_ends = geocoder.geocode([mid_az, mid_az], [rg_start, rg_start + n_rg], [base_height, base_height])

        unit = lambda seg: [float(v) for v in seg / np.linalg.norm(seg)]
        return {"azimuth": unit(az_ends[1] - az_ends[0]), "range": unit(rg_ends[1] - rg_ends[0])}

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
            metres, the geocoder's residual RMS in metres, the azimuth and
            ground-range scene-axis ECEF unit vectors and, when the run
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
            "axes"           : geo["axes"],
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

    @staticmethod
    def _hex_rgb(colors) -> np.ndarray:
        """Returns hex colour strings as a float RGB array of shape (len(colors), 3)."""
        rgb = []
        for color in colors:
            rgb.append([int(color[j:j + 2], 16) / 255.0 for j in (1, 3, 5)])
        return np.asarray(rgb, dtype=np.float64)

    def _load_passes(self, reader: StampReader, n_az: int, n_rg: int) -> dict | None:
        """Locates the raw pass stack of a preprocessing run.

        Args:
            reader : Preprocessing run reader.
            n_az   : Azimuth extent of the tomogram, in pixels.
            n_rg   : Range extent of the tomogram, in pixels.

        Returns:
            Context with the primary, secondaries and interferogram paths and the pass labels (primary first), or None when the run stores no secondary stack.

        Raises:
            ValueError : If the secondary or interferogram stack does not match the tomogram footprint or the recorded pass labels do not count the primary plus every secondary.
        """
        primary_path     = reader.artifact_path("primary")
        secondaries_path = reader.artifact_path("secondaries")
        if primary_path is None or secondaries_path is None:
            return None

        secondaries = np.load(secondaries_path, mmap_mode="r")
        if secondaries.ndim != 3 or secondaries.shape[1:] != (n_az, n_rg):
            raise ValueError(f"secondaries shape {secondaries.shape} does not match the {n_az}x{n_rg} tomogram footprint in {reader.where}")

        interferograms_path = reader.artifact_path("interferograms")
        if interferograms_path is not None:
            interferograms = np.load(interferograms_path, mmap_mode="r")
            if interferograms.shape != secondaries.shape:
                raise ValueError(f"interferograms shape {interferograms.shape} does not match the secondaries shape {secondaries.shape} in {reader.where}")

        n_secondaries = int(secondaries.shape[0])
        labels        = reader.layout()["pass_labels"]
        if labels is None:
            labels = ["primary"] + [f"pass {k:02d}" for k in range(1, n_secondaries + 1)]
        if len(labels) != n_secondaries + 1:
            raise ValueError(f"dataset.json records {len(labels)} pass labels but the run stores a primary plus {n_secondaries} secondaries in {reader.where}; rerun preprocessing to regenerate it")

        return {
            "primary"        : primary_path,
            "secondaries"    : secondaries_path,
            "interferograms" : interferograms_path,
            "labels"         : [str(label) for label in labels],
        }

    @staticmethod
    def _passes_meta(ctx: dict | None) -> dict | None:
        """Serialises the pass-stack context for the front end, or None without a stack."""
        if ctx is None:
            return None
        return {"labels": ctx["labels"], "n_passes": len(ctx["labels"]), "phase": ctx["interferograms"] is not None}

    def _ingest(self, raw: np.ndarray, x_axis: np.ndarray) -> dict:
        """Wraps an in-memory cube as a float32 entry with display colour limits.

        Args:
            raw    : Cube of shape (elevation, azimuth, range); complex cubes are reduced to their magnitude.
            x_axis : Elevation axis in metres.

        Returns:
            Entry with the float32 ``cube``, its ``x_axis`` and the 1st and 99th
            percentile colour limits estimated on a bounded subsample.
        """
        cube       = np.abs(raw) if np.iscomplexobj(raw) else np.asarray(raw, dtype=np.float32)
        vmin, vmax = self._colour_limits(cube)

        return {
            "cube"   : cube,
            "x_axis" : x_axis,
            "vmin"   : vmin,
            "vmax"   : vmax,
        }

    @classmethod
    def _colour_limits(cls, raw: np.ndarray) -> tuple[float, float]:
        """Estimates 1st and 99th percentile colour limits on a bounded subsample.

        Args:
            raw : Cube of any shape; complex values are reduced to their magnitude.

        Returns:
            Tuple (vmin, vmax), or (0, 1) when the cube holds no finite value.
        """
        sample = cls._limit_sample(raw)
        sample = np.abs(sample) if np.iscomplexobj(sample) else sample
        if not sample.size:
            return 0.0, 1.0

        vmin, vmax = np.percentile(sample, [1.0, 99.0])
        return float(vmin), float(vmax)

    @classmethod
    def _limit_sample(cls, raw: np.ndarray) -> np.ndarray:
        """Returns at most LIMIT_SAMPLE finite values taken at a fixed stride over the flattened cube."""
        flat   = raw.reshape(-1)
        sample = np.asarray(flat[:: max(1, flat.size // cls.LIMIT_SAMPLE)])

        return sample[np.isfinite(sample)]

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

    @staticmethod
    def _primary_clim(primary: np.ndarray) -> tuple[float, float]:
        """Returns the 1st and 99th percentile of a primary amplitude map, in dB."""
        return tuple(float(v) for v in np.percentile(primary, [1.0, 99.0]))

    @classmethod
    def _encode_primary(cls, primary: np.ndarray, clim: tuple[float, float]) -> bytes:
        """Encodes a primary amplitude map as a greyscale PNG.

        Args:
            primary : Float array of shape (azimuth, range) holding the amplitude in dB.
            clim    : Grey-scale limits (vmin, vmax) in dB.

        Returns:
            PNG bytes of the map, one image pixel per cube pixel.
        """
        buf = io.BytesIO()
        plt.imsave(buf, primary, cmap="gray", vmin=float(clim[0]), vmax=float(clim[1]), **cls.PNG_ENCODE)
        return buf.getvalue()


class SliceCollector:
    """Renders the same slices across many runs for side-by-side comparison.

    Opens preprocessing runs lazily through an LRU cache of lightweight
    contexts, so several runs can be previewed and collected without displacing
    the cube loaded in the Cube tab.

    Attributes:
        cubes       : Explorer supplying the readers, archiver and cut helpers.
        logger      : Web logger for render and collection reporting.
        render_lock : Serialises figure writing during a collection.
        contexts    : LRU cache of opened run contexts, keyed by run directory.
    """

    SOURCES   = ("full", "param")
    AXES      = ("range", "azimuth")
    SPACES    = ("physical", "normalized")
    ITEM_KEYS = ("id", "source", "axis", "az", "rg", "space", "cmap")
    MAX_RUNS  = 24
    MAX_ITEMS = 400
    CACHE_CAP = 16

    def __init__(self, cubes: CubeExplorer, logger: WebLogger) -> None:
        """Stores the explorer and logger and prepares the context cache."""
        self.cubes       = cubes
        self.logger      = logger
        self.render_lock = threading.Lock()
        self.contexts    = LruCache(self.CACHE_CAP)

    def forget(self, run_dir: str) -> None:
        """Drops the opened context of one run, so its next use reads the files again.

        Args:
            run_dir : Run directory path, the cube id.
        """
        self.contexts.discard(lambda key: key == run_dir)

    def info(self, cube_id: str) -> dict:
        """Describes one collectable cube.

        Args:
            cube_id : Preprocessing run directory path.

        Returns:
            Dict with ``ok``, the run id, run, group and tomogram tag names, the cube's
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

    def primary_png(self, cube_id: str) -> bytes | None:
        """Renders the primary SLC amplitude map of a collectable cube as a PNG.

        The map covers the tomogram footprint, so image pixel (row, column) is
        cube pixel (azimuth, range). It is rendered once per context and cached.

        Args:
            cube_id : Preprocessing run directory path.

        Returns:
            Greyscale PNG bytes of the (azimuth, range) amplitude map in dB, or
            None when the cube cannot be opened or its primary SLC is missing;
            the reason is logged.
        """
        try:
            context = self._context(cube_id)
        except Exception as error:
            self.logger.warning(f"primary map for {cube_id} failed while opening the cube: {error}")
            return None

        if context is None:
            self.logger.warning(f"primary map refused: unknown cube id {cube_id}")
            return None

        if context["primary_png"] is None:
            try:
                primary = self.cubes._primary_db(context["reader"], context["n_az"], context["n_rg"])
            except (FileNotFoundError, ValueError) as error:
                self.logger.warning(f"primary map for {cube_id} unavailable: {error}")
                return None
            context["primary_png"] = CubeExplorer._encode_primary(primary, CubeExplorer._primary_clim(primary))

        return context["primary_png"]

    def slice_png(self, cube_id: str, source: str, axis: str, az: int, rg: int, space: str = "physical", cmap: str = "jet", vmin: float | None = None, vmax: float | None = None) -> bytes | None:
        """Renders one slice of a collectable cube as a PNG.

        Args:
            cube_id : Preprocessing run directory path.
            source  : Cube key to render.
            axis    : "range" or "azimuth".
            az      : Azimuth pixel index, clipped into range.
            rg      : Range pixel index, clipped into range.
            space   : "physical" or "normalized".
            cmap    : Colormap name.
            vmin    : Optional lower colour limit, honoured only in physical space.
            vmax    : Optional upper colour limit, honoured only in physical space.

        Returns:
            PNG bytes, or None when the arguments are invalid or the cube carries
            no such source.
        """
        if source not in self.SOURCES or axis not in self.AXES or space not in self.SPACES:
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
        plt.imsave(buf, np.flipud(data), cmap=CubeExplorer._entry_cmap(entry, cmap), vmin=lo, vmax=hi, **CubeExplorer.PNG_ENCODE)
        return buf.getvalue()

    def collect(self, items: list, shared: bool = True, name: str = "", reuse: bool = False) -> dict:
        """Renders and archives a basket of slices, each with its own cut and styling.

        Figures land under ``<runs root>/slice_collections/<name>`` in one folder
        per point and cut, next to a ``collection.json`` manifest that also
        records the validated request.

        Args:
            items  : Basket entries, dicts carrying the ITEM_KEYS; duplicates are dropped, at most MAX_ITEMS entries over at most MAX_RUNS cubes.
            shared : When True, the physical-space figures of one source share the widest colour range across every basket run carrying that source.
            name   : Collection folder name; sanitised, and defaulted to a timestamp.
            reuse  : When True, an existing folder of that name whose manifest records the same basket and scale is returned as it is instead of refused.

        Returns:
            Dict with ``ok``, the output ``dir``, the resolved ``name``, the
            written ``files``, the run-source pairs of basket entries whose run
            lacks that source as ``missing``, the number of runs and whether an
            existing folder was ``reused``, or ``ok`` False with the reason.
        """
        try:
            plan = self._plan(items, name)
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

        items, ids, contexts, labels, title, out_dir = plan
        request = {"items": items, "shared": bool(shared)}

        if out_dir.exists():
            earlier = self._earlier(out_dir, request) if reuse else None
            if earlier is None:
                differs = " for a different basket" if reuse else ""
                return {"ok": False, "error": f"a collection named '{title}' already exists at {out_dir}{differs}; pick another name or delete it first"}
            return earlier

        clims = self._basket_clims(items, contexts) if shared else {}

        files   = []
        entries = []
        missing = []
        with self.render_lock:
            for item in items:
                context = contexts[item["id"]]
                label   = labels[item["id"]]
                entry   = context["entries"].get(item["source"])
                if entry is None:
                    gap = {"label": label, "source": item["source"]}
                    if gap not in missing:
                        missing.append(gap)
                    continue

                az_i = int(np.clip(item["az"], 0, context["n_az"] - 1))
                rg_i = int(np.clip(item["rg"], 0, context["n_rg"] - 1))
                data, heights, vmin, vmax = self._cut(entry, item["axis"], az_i, rg_i, item["space"])

                clim = clims.get(item["source"]) if item["space"] == "physical" else None
                if clim is not None:
                    vmin, vmax = clim

                cut_dir = out_dir / f"az{item['az']:04d}_rg{item['rg']:04d}" / f"{item['axis']}_{item['source']}_{item['space']}_{item['cmap']}"
                saved   = self.cubes.archiver.render(data, heights, vmin, vmax, item["source"], item["axis"], az_i, rg_i, item["space"], cut_dir / f"{label}.png", cmap=CubeExplorer._entry_cmap(entry, item["cmap"]), label=label)
                rel     = str(saved.relative_to(out_dir))

                files.append(rel)
                entries.append({**item, "label": label, "file": rel})

        if not files:
            return {"ok": False, "error": "no figures rendered; none of the basket runs carry the requested sources"}

        manifest = {
            "name"    : title,
            "created" : datetime.now().isoformat(timespec="seconds"),
            "shared"  : bool(shared),
            "clims"   : {source: list(clim) for source, clim in clims.items()},
            "runs"    : [{"id": str(contexts[i]["run_dir"]), "run": contexts[i]["run"], "group": contexts[i]["group"], "stamp": contexts[i]["stamp"], "label": labels[i]} for i in ids],
            "points"  : [{"az": az, "rg": rg} for az, rg in dict.fromkeys((item["az"], item["rg"]) for item in items)],
            "items"   : entries,
            "missing" : missing,
            "files"   : files,
            "request" : request,
        }
        (out_dir / "collection.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")

        self.logger.ok(f"collected {len(files)} slice figures from {len(ids)} runs into {out_dir}")
        return {"ok": True, "dir": str(out_dir), "name": title, "files": files, "missing": missing, "runs": len(ids), "reused": False}

    def _plan(self, raw: list, name: str) -> tuple:
        """Validates a basket and resolves its runs, labels and output folder.

        Args:
            raw  : Basket entries as posted.
            name : Requested collection name.

        Returns:
            Tuple of the validated entries, the cube ids in first-use order,
            their contexts keyed by id, their file labels keyed by id, the
            sanitised collection name and the collection folder.

        Raises:
            ValueError : If an entry is invalid, the basket spans more than MAX_RUNS cubes, or a cube id is unknown.
        """
        items = self._items(raw)
        ids   = list(dict.fromkeys(item["id"] for item in items))
        if len(ids) > self.MAX_RUNS:
            raise ValueError(f"at most {self.MAX_RUNS} runs per collection, got {len(ids)}")

        contexts = {}
        for cube_id in ids:
            context = self._context(cube_id)
            if context is None:
                raise ValueError(f"unknown cube id: {cube_id}")
            contexts[cube_id] = context

        labels  = dict(zip(ids, self._labels([contexts[cube_id] for cube_id in ids])))
        title   = re.sub(r"[^A-Za-z0-9._-]+", "_", name or "").strip("._")
        title   = title or datetime.now().strftime("collection_%Y%m%d_%H%M%S")
        out_dir = contexts[ids[0]]["root"] / "slice_collections" / title

        return items, ids, contexts, labels, title, out_dir

    def _items(self, raw) -> list:
        """Validates and deduplicates the basket entries.

        Args:
            raw : List of dicts carrying the ITEM_KEYS.

        Returns:
            Unique entries in request order, each a dict of the ITEM_KEYS with
            integer ``az`` and ``rg`` and string values otherwise.

        Raises:
            ValueError : If the basket is empty or not a list, exceeds MAX_ITEMS, or an entry lacks a key, names an unknown source, axis, space or colormap, or holds a negative index.
        """
        if not isinstance(raw, list) or not raw:
            raise ValueError("the basket is empty; add slices before exporting")
        if len(raw) > self.MAX_ITEMS:
            raise ValueError(f"at most {self.MAX_ITEMS} slices per collection, got {len(raw)}")

        items = []
        seen  = set()
        for entry in raw:
            absent = [key for key in self.ITEM_KEYS if key not in entry]
            if absent:
                raise ValueError(f"basket entry {entry} lacks {absent}")

            item = {key: str(entry[key]) for key in self.ITEM_KEYS}
            item["az"], item["rg"] = int(entry["az"]), int(entry["rg"])

            if item["source"] not in self.SOURCES:
                raise ValueError(f"unknown source '{item['source']}'; expected one of {self.SOURCES}")
            if item["axis"] not in self.AXES:
                raise ValueError(f"unknown axis '{item['axis']}'; expected one of {self.AXES}")
            if item["space"] not in self.SPACES:
                raise ValueError(f"unknown space '{item['space']}'; expected one of {self.SPACES}")
            if item["cmap"] not in CubeExplorer.CMAPS:
                raise ValueError(f"unknown colormap '{item['cmap']}'; expected one of {CubeExplorer.CMAPS}")
            if item["az"] < 0 or item["rg"] < 0:
                raise ValueError(f"point az={item['az']}, rg={item['rg']} is negative")

            key = tuple(item[k] for k in self.ITEM_KEYS)
            if key in seen:
                continue
            seen.add(key)
            items.append(item)

        return items

    @staticmethod
    def _earlier(out_dir: Path, request: dict) -> dict | None:
        """Returns an existing collection written for exactly this request, or None.

        Args:
            out_dir : Existing collection folder.
            request : Validated basket entries and scale flag of the new request.

        Returns:
            The collect result describing that folder with ``reused`` True, or
            None when it holds no manifest or its manifest records another
            request.
        """
        manifest_path = out_dir / "collection.json"
        if not manifest_path.is_file():
            return None

        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest.get("request") != request:
            return None

        return {"ok": True, "dir": str(out_dir), "name": manifest["name"], "files": manifest["files"], "missing": manifest["missing"], "runs": len(manifest["runs"]), "reused": True}

    def _basket_clims(self, items: list, contexts: dict) -> dict:
        """Returns the shared colour range of every source drawn in physical space.

        Args:
            items    : Validated basket entries.
            contexts : Opened run contexts keyed by cube id.

        Returns:
            Dict from source to its (vmin, vmax) envelope over the basket runs
            whose physical-space entries draw that source; sources without a
            usable envelope are left out.
        """
        clims = {}
        for source in dict.fromkeys(item["source"] for item in items if item["space"] == "physical"):
            ids  = dict.fromkeys(item["id"] for item in items if item["space"] == "physical" and item["source"] == source)
            clim = self._shared_clim([contexts[cube_id] for cube_id in ids], source, "physical")
            if clim is not None:
                clims[source] = clim

        return clims

    @staticmethod
    def _labels(contexts: list) -> list:
        """Builds one unique file label per context.

        Run names are used as-is, prefixed with their group when the name repeats
        and suffixed with the tomogram tag when that is still not unique.

        Args:
            contexts : Opened run contexts, in collection order.

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
            contexts : Opened run contexts.
            source   : Cube key whose limits are merged.
            space    : Only "physical" yields shared limits.

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
            entry : Context entry holding the cube and its elevation axis.
            axis  : "range" for a fixed range column, "azimuth" for a fixed azimuth row.
            az    : Azimuth pixel index, clipped into range.
            rg    : Range pixel index, clipped into range.
            space : "normalized" to peak-normalise columns, else "physical".

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
            cube_id : Preprocessing run directory path.

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
            reader : Reader of the run to open.

        Returns:
            Context with the run directory, its reader and runs root, the run,
            group and tag names, the azimuth and range extents, the lazily held
            ``entries`` per source and an empty ``primary_png`` slot filled on
            the first map request.

        Raises:
            ValueError : If the run lies outside every catalogued runs root or the tomogram is not three-dimensional.
        """
        run_dir = reader.run_dir
        root    = self._root_for(run_dir)
        if root is None:
            raise ValueError(f"{run_dir} is outside every catalogued runs root")

        full_raw = reader.tomogram(view=True)
        if full_raw.ndim != 3:
            raise ValueError(f"full tomogram is not a 3D cube: shape={full_raw.shape}")

        n_elev, n_az, n_rg = full_raw.shape
        x_axis             = self.cubes._elevation_axis(reader, n_elev)

        entries = {"full": self._entry(full_raw, x_axis)}

        tags = reader.param_tags()
        if len(tags) == 1:
            entries["param"] = self.cubes._param_entry(reader, tags[0], n_az, n_rg, x_axis)
        elif len(tags) > 1:
            self.logger.warning(f"{run_dir.name} holds {len(tags)} parameter runs ({', '.join(tags)}); the collector serves none of them — the Cube tab loads a chosen tag explicitly")

        return {
            "run_dir"     : run_dir,
            "reader"      : reader,
            "root"        : root,
            "run"         : run_dir.name,
            "group"       : str(run_dir.relative_to(root).parent),
            "stamp"       : reader.layout()["tomogram_tag"],
            "n_az"        : n_az,
            "n_rg"        : n_rg,
            "entries"     : entries,
            "primary_png" : None,
        }

    @staticmethod
    def _entry(raw: np.ndarray, x_axis: np.ndarray) -> dict:
        """Wraps a cube without materialising it and estimates its colour limits.

        Args:
            raw    : Memory-mapped cube of shape (elevation, azimuth, range).
            x_axis : Elevation axis in metres.

        Returns:
            Entry with the untouched ``cube``, its ``x_axis`` and the 1st and 99th
            percentile colour limits estimated on a bounded subsample.
        """
        vmin, vmax = CubeExplorer._colour_limits(raw)

        return {
            "cube"   : raw,
            "x_axis" : x_axis,
            "vmin"   : vmin,
            "vmax"   : vmax,
        }

    def _root_for(self, run_dir: Path) -> Path | None:
        """Returns the catalogued runs root containing the run, or None."""
        return self.cubes.roots.enclosing(run_dir)


class SliceCollectionMailer:
    """Mails a slice basket as a rendered collection packed into zip attachments.

    The basket is rendered through the collector first, so every mailed
    collection also stays on disk under ``slice_collections``. The folder is then
    packed into size-capped zip volumes under its ``mail`` subfolder and
    submitted over SMTP with SSL, one message per volume, from the sender and
    SMTP endpoint of the machine profile's ``mail`` section, logging in with the
    password held in the PASSWORD_ENV environment variable.

    Attributes:
        collector         : Slice collector rendering the basket.
        logger            : Web logger for packing and submission messages.
        endpoint          : Mail section of the machine profile, carrying ``sender``, ``recipient``, ``smtp_host`` and ``smtp_port``.
        ADDRESS           : Pattern one recipient address must match.
        PASSWORD_ENV      : Environment variable holding the SMTP password, never written to disk by the console.
        SUBJECT_PREFIX    : Prefix of every message subject.
        MAX_ATTACHMENT_MB : Upper bound of one zip volume in megabytes, measured on the uncompressed files.
        SMTP_TIMEOUT_S    : Seconds a blocking SMTP connect, login or upload may stall before the submission fails.
    """

    ADDRESS           = re.compile(r"^[^@\s,;]+@[^@\s,;]+\.[^@\s,;]+$")
    PASSWORD_ENV      = "REPORT_MAIL_PASSWORD"
    SUBJECT_PREFIX    = "TomoVic"
    MAX_ATTACHMENT_MB = 18.0
    SMTP_TIMEOUT_S    = 120.0

    def __init__(self, collector: SliceCollector, logger: WebLogger) -> None:
        """Stores the collector and logger and reads the mail section of the machine profile."""
        self.collector = collector
        self.logger    = logger
        self.endpoint  = MachineProfile.current().mail

    def settings(self) -> dict:
        """Describes the mail defaults the basket form starts from.

        Returns:
            Dict with ``ok``, the default ``recipient``, the ``sender``, whether
            a sender is configured and the SMTP password variable is set
            (``ready``), the variable's name and the attachment cap in
            megabytes.
        """
        return {
            "ok"                : True,
            "recipient"         : self.endpoint["recipient"],
            "sender"            : self.endpoint["sender"],
            "ready"             : bool(self.endpoint["sender"]) and bool(os.environ.get(self.PASSWORD_ENV)),
            "password_env"      : self.PASSWORD_ENV,
            "max_attachment_mb" : self.MAX_ATTACHMENT_MB,
        }

    def _recipients(self, raw: str) -> list:
        """Splits and validates a comma- or semicolon-separated address list.

        Args:
            raw : Address list typed in the basket form.

        Returns:
            The addresses in typed order.

        Raises:
            ValueError : If the list is empty or an address is malformed.
        """
        addresses = [part.strip() for part in re.split(r"[,;]", raw or "") if part.strip()]
        if not addresses:
            raise ValueError("enter at least one recipient address")

        malformed = [address for address in addresses if not self.ADDRESS.match(address)]
        if malformed:
            raise ValueError(f"malformed recipient address: {', '.join(malformed)}")

        return addresses

    def _pack(self, out_dir: Path, result: dict) -> list:
        """Packs the rendered collection and its manifest into zip volumes.

        Volumes are filled in manifest order and a new one starts whenever the
        next file would push the uncompressed total past MAX_ATTACHMENT_MB;
        volumes of an earlier packing of the same folder are deleted first.

        Args:
            out_dir : Collection folder written by the collector.
            result  : Collector result naming the collection and its figures.

        Returns:
            Paths of the written volumes under ``<out_dir>/mail``, whose members
            sit under ``<name>/`` so unpacking every volume rebuilds the folder.

        Raises:
            ValueError : If one figure alone exceeds the attachment cap.
        """
        name      = result["name"]
        mail_dir  = out_dir / "mail"
        max_bytes = int(self.MAX_ATTACHMENT_MB * 1024 * 1024)
        entries   = [(out_dir / "collection.json", f"{name}/collection.json")]
        entries  += [(out_dir / rel, f"{name}/{rel}") for rel in result["files"]]

        volumes = []
        filled  = 0
        for source, arcname in entries:
            size = source.stat().st_size
            if size > max_bytes:
                raise ValueError(f"cannot mail {source}: it is {size / 1048576:.1f} MB on its own, above the {self.MAX_ATTACHMENT_MB:g} MB attachment cap")
            if not volumes or filled + size > max_bytes:
                volumes.append([])
                filled = 0
            volumes[-1].append((source, arcname))
            filled += size

        mail_dir.mkdir(parents=True, exist_ok=True)
        for stale in sorted(mail_dir.glob(f"{name}*.zip")):
            stale.unlink()

        paths = []
        for index, volume in enumerate(volumes, start=1):
            path = mail_dir / (f"{name}.zip" if len(volumes) == 1 else f"{name}_{index:02d}of{len(volumes):02d}.zip")
            with zipfile.ZipFile(path, mode="w", compression=zipfile.ZIP_DEFLATED) as archive:
                for source, arcname in volume:
                    archive.write(source, arcname)
            self.logger.muted(f"packed {path.name}: {len(volume)} file(s), {path.stat().st_size / 1048576:.1f} MB")
            paths.append(path)

        return paths

    def _body(self, out_dir: Path, note: str, volumes: list) -> str:
        """Writes the plain-text message body from the collection manifest.

        Args:
            out_dir : Collection folder holding ``collection.json``.
            note    : Free text typed in the basket form, placed first; may be empty.
            volumes : Written zip volumes.

        Returns:
            The message body.
        """
        manifest = json.loads((out_dir / "collection.json").read_text(encoding="utf-8"))

        lines = [note.strip(), ""] if note.strip() else []
        lines.append(f"Slice collection '{manifest['name']}': {len(manifest['files'])} figures from {len(manifest['runs'])} runs, colour scale {'shared per source' if manifest['shared'] else 'per run'}.")
        lines.append("")
        lines.append("Runs:")
        lines += [f"  {run['label']}  ({run['group']}/{run['run']}, tomogram {run['stamp']})" for run in manifest["runs"]]
        lines.append("")
        lines.append("Points: " + ", ".join(f"az {point['az']} rg {point['rg']}" for point in manifest["points"]))

        if manifest["missing"]:
            lines.append("Skipped, run lacks the source: " + ", ".join(f"{gap['label']} {gap['source']}" for gap in manifest["missing"]))
        if len(volumes) > 1:
            lines.append(f"The collection is split over {len(volumes)} messages; unpack every volume into one folder to rebuild it.")

        lines.append("")
        lines.append(f"Saved on the TomoVic host under {out_dir}")
        return "\n".join(lines)

    def _message(self, recipients: list, subject: str, body: str, volume: Path) -> EmailMessage:
        """Builds one message carrying one zip volume.

        Args:
            recipients : Validated recipient addresses.
            subject    : Message subject line.
            body       : Plain-text message body.
            volume     : Zip volume attached under its file name.

        Returns:
            The assembled message.
        """
        message            = EmailMessage()
        message["From"]    = self.endpoint["sender"]
        message["To"]      = ", ".join(recipients)
        message["Subject"] = subject
        message.set_content(body)
        message.add_attachment(volume.read_bytes(), maintype="application", subtype="zip", filename=volume.name)
        return message

    def _submit(self, messages: list) -> None:
        """Submits the messages over one SMTP SSL session.

        Args:
            messages : Assembled messages, sent in order.

        Raises:
            OSError : If the connect, login or an upload fails or stalls past SMTP_TIMEOUT_S, including smtplib's SMTPException subclasses.
        """
        start = time.monotonic()
        with smtplib.SMTP_SSL(self.endpoint["smtp_host"], int(self.endpoint["smtp_port"]), timeout=self.SMTP_TIMEOUT_S) as smtp:
            smtp.login(self.endpoint["sender"], os.environ[self.PASSWORD_ENV])
            for message in messages:
                smtp.send_message(message)

        self.logger.ok(f"sent {len(messages)} message(s) to {messages[0]['To']} via {self.endpoint['smtp_host']} in {time.monotonic() - start:.1f} s")

    def mail(self, items: list, shared: bool = True, name: str = "", recipient: str = "", note: str = "") -> dict:
        """Renders the basket, packs it and mails it to the given recipients.

        Args:
            items     : Basket entries, as accepted by ``SliceCollector.collect``.
            shared    : Whether physical-space figures of one source share a colour range.
            name      : Collection folder name; sanitised, and defaulted to a timestamp.
            recipient : Comma- or semicolon-separated recipient addresses.
            note      : Free text placed at the top of the message body.

        Returns:
            The collector result extended with the ``recipient`` line and the
            mailed ``volumes`` names, or ``ok`` False with the reason; when
            sending fails after rendering, the result still names the saved
            ``dir``. A basket already saved under the same name is mailed
            from that folder without rendering it again.
        """
        try:
            recipients = self._recipients(recipient)
        except ValueError as exc:
            return {"ok": False, "error": str(exc)}

        if not self.endpoint["sender"]:
            return {"ok": False, "error": f"no mail sender configured: set the mail section of the machine profile ({MachineProfile.location()}) and restart TomoVic"}
        if not os.environ.get(self.PASSWORD_ENV):
            return {"ok": False, "error": f"SMTP password not found: add export {self.PASSWORD_ENV}=<app password> to the machine profile env and restart TomoVic"}

        result = self.collector.collect(items, shared, name, reuse=True)
        if not result["ok"]:
            return result

        out_dir = Path(result["dir"])
        try:
            volumes = self._pack(out_dir, result)
        except ValueError as exc:
            return {"ok": False, "error": f"saved to {out_dir}, but packing failed: {exc}", "dir": str(out_dir)}

        body     = self._body(out_dir, note, volumes)
        messages = []
        for index, volume in enumerate(volumes, start=1):
            suffix = f" [{index}/{len(volumes)}]" if len(volumes) > 1 else ""
            messages.append(self._message(recipients, f"{self.SUBJECT_PREFIX}: slice collection {result['name']}{suffix}", body, volume))

        try:
            self._submit(messages)
        except OSError as exc:
            self.logger.error(f"mailing slice collection {result['name']} failed after rendering: {exc}")
            return {"ok": False, "error": f"saved to {out_dir}, but mailing failed: {exc}", "dir": str(out_dir)}

        return {**result, "recipient": ", ".join(recipients), "volumes": [volume.name for volume in volumes]}
