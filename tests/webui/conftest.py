"""Shared fixtures and builders for the webui test suite.

Puts the ``webui`` package on ``sys.path`` and provides HTTP-handler and path
stubs, synthetic preprocessing runs, inference stamps and cross-validation fold
trees on disk, plus helpers that drive CubeExplorer loading and that build a
ProcessManager over throwaway scripts.
"""

from __future__ import annotations

import io
import json
import math
import sys
import time
from pathlib import Path

import numpy as np
import pytest

from tools.runtime.completion import CompletionMarker
from tools.sar.geocoding      import Wgs84

REPO_ROOT  = Path(__file__).resolve().parents[2]
WEBUI_ROOT = REPO_ROOT / "webui"

if str(WEBUI_ROOT) not in sys.path:
    sys.path.insert(0, str(WEBUI_ROOT))

from cube_explorer   import CubeExplorer
from notifier        import JobNotifier
from process_manager import ProcessManager
from system_monitor  import ActiveUsers, SystemHistory, SystemMonitor
from web_logger      import WebLogger

N_ELEV, N_AZ, N_RG, N_SLOTS = 5, 8, 6, 2

SLEEP_LONG = "import time\ntime.sleep(30)\n"
ARGS_DUMP  = "import pathlib, sys\npathlib.Path('argv.txt').write_text(' '.join(sys.argv[1:]))\n"


class FakeHandler:
    """Stand-in for a BaseHTTPRequestHandler capturing the response it is sent.

    Attributes:
        command: HTTP method of the simulated request.
        path: Request path including any query string.
        headers: Request headers, always carrying Content-Length.
        rfile: Readable stream over the request body.
        wfile: Writable stream collecting the response body.
        status: Status code passed to send_response.
        sent: Response headers passed to send_header, keyed by name.
    """

    def __init__(self, command: str, path: str, body: bytes = b"", headers: dict | None = None) -> None:
        """Builds a simulated request.

        Args:
            command: HTTP method, e.g. ``"GET"`` or ``"POST"``.
            path: Request path.
            body: Raw request body.
            headers: Extra request headers merged over Content-Length.
        """
        self.command = command
        self.path    = path
        self.headers = {"Content-Length": str(len(body)), **(headers or {})}
        self.rfile   = io.BytesIO(body)
        self.wfile   = io.BytesIO()
        self.status  = 0
        self.sent    = {}

    def send_response(self, status: int) -> None:
        """Records the response status code."""
        self.status = status

    def send_header(self, name: str, value: str) -> None:
        """Records a response header."""
        self.sent[name] = value

    def end_headers(self) -> None:
        """Ends the header block, which the fake does not need to act on."""
        return

    def payload(self) -> dict:
        """Returns the response body decoded as JSON."""
        return json.loads(self.wfile.getvalue().decode("utf-8"))


class StubPaths:
    """Minimal stand-in for the webui path registry rooted at a temporary directory.

    Attributes:
        repo_root: Root of the fake repository.
        main_dir: Directory holding entry-point scripts.
        logs_dir: Root of the log tree.
        gpu_guard_dir: Directory for GPU guard state files.
        gpu_pools_dir: Directory for GPU pool state files.
        saved_runs_dir: Directory for saved run definitions.
    """

    def __init__(self, root: Path) -> None:
        """Derives the standard subdirectories from a root path."""
        self.repo_root      = root
        self.main_dir       = root / "main"
        self.logs_dir       = root / "logs"
        self.gpu_guard_dir  = root / "logs" / "gpu_guard"
        self.gpu_pools_dir  = root / "logs" / "gpu_pools"
        self.saved_runs_dir = root / "logs" / "saved_runs"

    def has_script(self, key: str) -> bool:
        """Returns whether an analysis script exists for the given catalog key."""
        return (self.main_dir / "analysis" / f"{key}.py").exists()

    def script_entry(self, key: str) -> dict:
        """Returns the absolute path and repo-relative path of an analysis script."""
        path = self.main_dir / "analysis" / f"{key}.py"
        return {"path": path, "rel": f"main/analysis/{key}.py"}


class StubDescriber:
    """Job describer stand-in returning a fixed sentence per catalog key."""

    def describe(self, key: str, interpreter: str, overrides: dict | None) -> str:
        """Returns a constant description mentioning the catalog key."""
        return f"stub description for {key}"


def job_record(manager: ProcessManager, job_id: str) -> dict:
    """Returns a snapshot copy of a job record taken under the manager lock."""
    with manager.lock:
        return dict(manager.jobs[job_id])


def wait_for_status(manager: ProcessManager, job_id: str, status: str, timeout: float = 10.0) -> bool:
    """Polls until a job reaches a given status.

    Args:
        manager: Process manager owning the job.
        job_id: Identifier of the job to poll.
        status: Status value being waited for.
        timeout: Maximum wait in seconds.

    Returns:
        True if the status was observed before the timeout.
    """
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if job_record(manager, job_id)["status"] == status:
            return True
        time.sleep(0.05)
    return False


def wait_until_finished(manager: ProcessManager, job_id: str, timeout: float = 10.0) -> bool:
    """Polls until a job leaves the running state.

    Args:
        manager: Process manager owning the job.
        job_id: Identifier of the job to poll.
        timeout: Maximum wait in seconds.

    Returns:
        True if the job stopped running before the timeout.
    """
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if job_record(manager, job_id)["status"] != "running":
            return True
        time.sleep(0.05)
    return False


def make_geo_fields() -> dict:
    """Builds consistent geocoding metadata for a synthetic track.

    Projects the four scene corners from slant range and azimuth through an ENU
    frame anchored at 12.65 E, 47.85 N to WGS84 longitude and latitude.

    Returns:
        Dictionary with platform altitude ``h0`` and terrain height in metres,
        ``heading`` and ``squint`` in degrees, antenna direction, the per-sample
        slant ranges in metres and a ``geo_poly`` mapping four pixel corners to
        lon/lat/height triples.
    """
    heading, squint, h0, height = 43.0, -1.35, 3700.0, 680.0

    corner_rg = np.array([0.0, N_RG, N_RG, 0.0])
    corner_az = np.array([0.0, 0.0, N_AZ, N_AZ])

    slant  = 3300.0 + corner_rg * 0.6
    along  = corner_az * 0.4 + slant * math.sin(math.radians(squint))
    ground = np.sqrt(slant * slant - (h0 - height) ** 2)

    head_e = math.sin(math.radians(heading))
    head_n = math.cos(math.radians(heading))
    east   = along * head_e + ground * head_n
    north  = along * head_n - ground * head_e

    origin_x, origin_y, origin_z = Wgs84.geodetic_to_ecef(12.65, 47.85, 0.0)
    east_axis, north_axis, _     = Wgs84.enu_axes(12.65, 47.85)

    ecef        = np.array([float(origin_x), float(origin_y), float(origin_z)])[None, :] + np.outer(east, east_axis) + np.outer(north, north_axis)
    lon, lat, _ = Wgs84.ecef_to_geodetic(ecef[:, 0], ecef[:, 1], ecef[:, 2])

    return {
        "h0"       : h0,
        "heading"  : heading,
        "squint"   : squint,
        "antdir"   : 1,
        "r"        : [3300.0 + 0.6 * i for i in range(N_RG)],
        "geo_poly" : {
            "pixels" : np.stack([corner_rg, corner_az], axis=1).ravel().tolist(),
            "lonlat" : np.stack([lon, lat, np.full(4, height)], axis=1).ravel().tolist(),
        },
    }


def make_preproc(base: Path, rng: np.random.Generator | None = None, with_spacing: bool = False, with_geo: bool = False, n_az: int = N_AZ) -> Path:
    """Writes a synthetic preprocessing run directory.

    Args:
        base: Parent directory receiving the ``preproc`` tree.
        rng: Generator for the complex primary image; seeded default when None.
        with_spacing: Whether track_parameters.json with pixel spacings is written.
        with_geo: Whether a DEM (with one NaN pixel) and geocoding fields are added.
        n_az: Number of azimuth samples in the primary image.

    Returns:
        Path of the created preprocessing run directory.
    """
    rng     = np.random.default_rng(0) if rng is None else rng
    preproc = base / "preproc"
    (preproc / "data").mkdir(parents=True)

    primary = rng.normal(size=(n_az, N_RG)) + 1j * rng.normal(size=(n_az, N_RG))
    np.save(preproc / "data" / "primary.npy", primary)

    artifacts = {"primary": "primary.npy"}

    if with_geo:
        dem       = np.full((n_az, N_RG), 680.0, dtype=np.float32)
        dem[2, 3] = np.nan
        np.save(preproc / "data" / "dem_full.npy", dem)
        artifacts["dem_full"] = "dem_full.npy"

    layout = {"global_crop": [0, n_az, 0, N_RG], "artifacts": artifacts}
    (preproc / "data" / "dataset.json").write_text(json.dumps(layout))

    if with_spacing or with_geo:
        per_track = {"T01": {"ps_az": 0.4}, "T02": {"ps_az": 0.41}, "T03": {"ps_az": 0.42}}

        if with_geo:
            fields = make_geo_fields()
            per_track["T01"].update(fields)
            per_track["T02"].update(fields)
            per_track["T03"].update(fields)

        payload = {
            "labels"      : ["T01", "T02", "T03"],
            "reference"   : "T01",
            "shared"      : {"ps_rg": 0.6},
            "per_track"   : per_track,
            "track_files" : [],
        }
        (preproc / "meta").mkdir()
        (preproc / "meta" / "track_parameters.json").write_text(json.dumps(payload))

    return preproc


def make_stamp(run: Path, preproc: Path, rng: np.random.Generator, sources: tuple = ("pred", "gt"), x_min: float = -10.0, shape: tuple = (N_ELEV, N_AZ, N_RG), name: str = "stamp_1", region: list | None = None) -> Path:
    """Writes an inference stamp with random curve cubes and its metrics file.

    Args:
        run: Run directory receiving ``inference/<name>`` and ``meta``.
        preproc: Preprocessing run the dataset config points back to.
        rng: Generator for the random curve cubes.
        sources: Cube prefixes to write, each as ``<source>_curves.npy``.
        x_min: Lowest height of the elevation axis in metres.
        shape: Cube shape as (elevation, azimuth, range).
        name: Stamp directory name.
        region: Split region as [az_start, az_end, rg_start, rg_end]; defaults to
            the whole scene.

    Returns:
        Path of the created stamp directory.
    """
    stamp = run / "inference" / name
    (stamp / "cubes").mkdir(parents=True)
    (run / "meta").mkdir(parents=True, exist_ok=True)

    region = [0, N_AZ, 0, N_RG] if region is None else region

    (run / "meta" / "dataset_creation_config.json").write_text(json.dumps({"preprocessing_run_directory": str(preproc)}))
    (stamp / "metrics.json").write_text(json.dumps({"x_axis_min": x_min, "x_axis_max": 30.0, "split_region": region, "tracks": {"labels": ["T01", "T02"], "reference": "T01"}}))

    for source in sources:
        np.save(stamp / "cubes" / f"{source}_curves.npy", rng.random(shape).astype(np.float32))

    return stamp


def make_cube_run(base: Path, sources: tuple = ("pred", "gt"), with_spacing: bool = False, with_reduced: bool = False, with_params: tuple = (), with_metrics: bool = False, with_geo: bool = False) -> Path:
    """Writes a complete single-run cube tree for the explorer to discover.

    Args:
        base: Parent directory receiving the preprocessing and run trees.
        sources: Curve cube prefixes to write.
        with_spacing: Whether pixel spacing metadata is written.
        with_reduced: Whether a sparse reduced-curve cube is added.
        with_params: Sources for which a parameter block of shape
            (3 * N_SLOTS, N_AZ, N_RG) is written, its second amplitude zeroed.
        with_metrics: Whether pixel R2 (with one NaN), a physics validity mask
            and a deliberately misshaped cube are added.
        with_geo: Whether DEM and geocoding metadata are written.

    Returns:
        Path of the created stamp directory.
    """
    rng     = np.random.default_rng(0)
    preproc = make_preproc(base, rng, with_spacing, with_geo)
    stamp   = make_stamp(base / "group" / "run_a", preproc, rng, sources)

    if with_reduced:
        reduced          = np.zeros((N_ELEV, N_AZ, N_RG), dtype=np.float32)
        reduced[2, 3, 4] = 2.0
        reduced[4, 5, 1] = 1.0
        np.save(stamp / "cubes" / "reduced_curves.npy", reduced)

    for source in with_params:
        block    = rng.random((3 * N_SLOTS, N_AZ, N_RG)).astype(np.float32)
        block[3] = 0.0
        np.save(stamp / "cubes" / f"params_{source}.npy", block)

    if with_metrics:
        r2       = rng.random((N_AZ, N_RG)).astype(np.float32)
        r2[0, 0] = np.nan
        np.save(stamp / "cubes" / "pixel_r2.npy", r2)
        np.save(stamp / "cubes" / "physics_valid_mask.npy", rng.random((N_AZ, N_RG)) > 0.5)
        np.save(stamp / "cubes" / "misshaped.npy", rng.random((3, 3)).astype(np.float32))

    return stamp


N_FOLDS, FOLD_AZ, FOLD_GAP = 3, 4, 1


def make_cv_run(base: Path, splits: tuple = ("test",), seed: str | None = None, sources: tuple = ("pred", "gt"), with_params: tuple = (), with_metrics: bool = False, gap: int = FOLD_GAP) -> Path:
    """Writes a cross-validation tree of N_FOLDS contiguous azimuth folds.

    Each fold covers FOLD_AZ azimuth lines separated by ``gap`` guard lines, and
    its cubes are filled with the constant fold index plus one so mosaics can be
    checked pixel by pixel.

    Args:
        base: Parent directory receiving the preprocessing and cross-validation trees.
        splits: Splits for which a completed stamp is written per fold.
        seed: Optional seed subdirectory inserted under each fold run.
        sources: Curve cube prefixes to write.
        with_params: Sources for which a constant parameter block is written.
        with_metrics: Whether a constant pixel R2 map is written.
        gap: Guard lines between consecutive folds.

    Returns:
        Path of the cross-validation root directory.
    """
    rng      = np.random.default_rng(0)
    span     = FOLD_AZ + gap
    total_az = N_FOLDS * span - gap
    preproc  = make_preproc(base, rng, n_az=total_az)
    cv_root  = base / "cross_validation" / "20260810_120000"

    (cv_root / "pipeline").mkdir(parents=True)

    for index in range(N_FOLDS):
        run_dir = cv_root / "folds" / f"resunet_a_fold_{index}"
        if seed:
            run_dir = run_dir / seed

        az0 = index * span
        for split in splits:
            stamp = make_stamp(run_dir, preproc, rng, sources, name=f"stamp_{split}", shape=(N_ELEV, FOLD_AZ, N_RG), region=[az0, az0 + FOLD_AZ, 0, N_RG])
            CompletionMarker.stamp(stamp, {"stage": "inference", "split": split})
            np.save(stamp / "cubes" / "pred_curves.npy", np.full((N_ELEV, FOLD_AZ, N_RG), float(index + 1), dtype=np.float32))

            for source in with_params:
                np.save(stamp / "cubes" / f"params_{source}.npy", np.full((3 * N_SLOTS, FOLD_AZ, N_RG), float(index + 1), dtype=np.float32))

            if with_metrics:
                np.save(stamp / "cubes" / "pixel_r2.npy", np.full((FOLD_AZ, N_RG), float(index + 1), dtype=np.float32))

    return cv_root


def open_explorer(base: Path, expected: int | None = None) -> tuple[CubeExplorer, list[str]]:
    """Lists the cubes under a directory and returns the explorer and their ids.

    Args:
        base: Directory scanned for cubes.
        expected: Asserted number of discovered cubes when given.

    Returns:
        Tuple of the explorer and the discovered cube ids.
    """
    explorer = CubeExplorer(WebLogger())
    listing  = explorer.list_cubes(str(base))

    assert listing["ok"], listing
    if expected is not None:
        assert len(listing["cubes"]) == expected, listing

    return explorer, [cube["id"] for cube in listing["cubes"]]


def load_cube(explorer: CubeExplorer, cube_id: str, timeout: float = 30.0) -> dict:
    """Starts a cube load and blocks until it reports ready.

    Args:
        explorer: Explorer performing the load.
        cube_id: Identifier of the cube to load.
        timeout: Maximum wait in seconds.

    Returns:
        Final load status payload.
    """
    assert explorer.start_load(cube_id)["ok"]

    deadline = time.time() + timeout
    while explorer.load_status()["state"] == "loading" and time.time() < deadline:
        time.sleep(0.05)

    status = explorer.load_status()
    assert status["state"] == "ready", status
    return status


def loaded_cube(base: Path, **kwargs) -> tuple[CubeExplorer, str]:
    """Builds a single cube run and returns the explorer with that cube loaded.

    Args:
        base: Parent directory for the generated run.
        **kwargs: Forwarded to ``make_cube_run``.

    Returns:
        Tuple of the explorer and the loaded cube id.
    """
    make_cube_run(base, **kwargs)
    explorer, cube_ids = open_explorer(base, expected=1)
    load_cube(explorer, cube_ids[0])

    return explorer, cube_ids[0]


@pytest.fixture
def monitor(tmp_path, monkeypatch):
    """Yields a SystemMonitor with its disk-usage and sampling loops disabled."""
    monkeypatch.setattr(SystemMonitor, "_du_loop", lambda self: None)
    monkeypatch.setattr(SystemHistory, "sample_loop", lambda self: None)
    monkeypatch.setattr(ActiveUsers, "sample_loop", lambda self: None)
    return SystemMonitor(StubPaths(tmp_path), WebLogger())


@pytest.fixture
def make_manager(tmp_path):
    """Yields a factory building a ProcessManager over named throwaway scripts, stopping all jobs on teardown."""
    built = []

    def build(scripts: dict) -> ProcessManager:
        directory = tmp_path / "main" / "analysis"
        directory.mkdir(parents=True)

        for name, body in scripts.items():
            (directory / f"{name}.py").write_text(body)

        paths   = StubPaths(tmp_path)
        logger  = WebLogger()
        manager = ProcessManager(paths, logger, JobNotifier(paths, logger), StubDescriber())
        built.append(manager)

        return manager

    yield build

    for manager in built:
        manager.stop_all()
