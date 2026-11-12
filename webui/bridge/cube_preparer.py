"""Background preparation of TomoVis imports for the TomoVic tools.

One daemon thread runs one job at a time, so at most one extra cube is in
memory at any moment, and it never takes a TomoVis lock. A job runs, each only
when needed and in this order: convert (read the source with TomoVis's own
readers and write ``data/tomovis_cube.npy``), check (the cube must be 3-D, 4-D
with channels first, or 5-D covariance), channel (write the float32
``data/tomogram_full.npy`` of a multi-channel cube slab by slab, or link a 3-D
cube) and standin (the primary-image stand-in TomoVis shows as its top view).
"""

from __future__ import annotations

import os
import queue
import threading
import time
import traceback
from pathlib import Path

import numpy as np

from bridge.dataset_record    import DatasetRecord
from bridge.dataset_workspace import DatasetWorkspace
from bridge.tomovis_link      import TomoVisLink
from tomovis.cube_readers     import CubeReaders
from tomovis.session_file     import SessionFile
from web_logger               import WebLogger


class PreparationJob:
    """One preparation request.

    Attributes:
        dataset_id  : Dataset id.
        record_path : Path of its record.json.
        steps       : Steps to run, a subset of CubePreparer.STEPS in that order.
    """

    def __init__(self, dataset_id: str, record_path: Path, steps: tuple) -> None:
        """Stores the request.

        Args:
            dataset_id  : Dataset id.
            record_path : Path of its record.json.
            steps       : Steps to run.
        """

        self.dataset_id  = dataset_id
        self.record_path = Path(record_path)
        self.steps       = tuple(step for step in CubePreparer.STEPS if step in steps)


class CubePreparer:
    """Runs preparation jobs one at a time on a daemon thread.

    Every file is written atomically. ``on_change(dataset_id, changes)``
    receives the record fields a step changed (``stage``, ``tomovis_cube``,
    ``channel``, ``origins`` to merge, and finally ``state`` with ``error``), so
    the bridge applies them under its lock, raises the revision when a job ends
    ready and drops the caches of the dataset.

    Attributes:
        workspace  : Workspace the datasets live in.
        logger     : Console logger.
        on_change  : Callback receiving (dataset id, changed record fields).
        jobs       : Queue of pending jobs.
        lock       : Guards ``running``.
        running    : Dataset id to (stage, fraction) of queued and running jobs.
        thread     : The worker thread once started.
        readers    : TomoVis's import readers.
        sessions   : TomoVis's session file reader.
        STEPS      : Step names in run order.
        SLAB_BYTES : Input bytes read per slab along azimuth.
    """

    STEPS      = ("convert", "check", "channel", "standin")
    SLAB_BYTES = 64 * 1024 * 1024

    def __init__(self, workspace: DatasetWorkspace, logger: WebLogger, on_change) -> None:
        """Builds an idle preparer.

        Args:
            workspace : Workspace the datasets live in.
            logger    : Console logger.
            on_change : Callable(dataset_id, changes) applying record changes.
        """

        self.workspace = workspace
        self.logger    = logger
        self.on_change = on_change
        self.jobs      = queue.Queue()
        self.lock      = threading.Lock()
        self.running   = {}
        self.thread    = None
        self.readers   = CubeReaders(logger)
        self.sessions  = SessionFile()

    def start(self) -> None:
        """Starts the worker thread."""

        self.thread = threading.Thread(target=self.loop, name="CubePreparer", daemon=True)
        self.thread.start()

    def submit(self, job: PreparationJob) -> None:
        """Queues a job; its dataset reports progress from now on.

        Args:
            job : The job.
        """

        with self.lock:
            self.running[job.dataset_id] = ("", 0.0)
        self.jobs.put(job)

    def progress(self, dataset_id: str) -> tuple[str, float] | None:
        """Returns (stage, fraction done) of a queued or running job, None when the dataset has none."""

        with self.lock:
            return self.running.get(dataset_id)

    def settle(self, timeout: float) -> bool:
        """Waits until no job is queued or running.

        Args:
            timeout : Seconds to wait at most.

        Returns:
            Whether the preparer became idle in time.
        """

        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self.jobs.unfinished_tasks == 0:
                return True
            time.sleep(0.02)
        return False

    def report(self, dataset_id: str, stage: str, fraction: float) -> None:
        """Publishes a job's progress; a new stage text is also saved in the record."""

        with self.lock:
            previous                 = self.running.get(dataset_id)
            self.running[dataset_id] = (stage, float(fraction))
        if previous is None or previous[0] != stage:
            self.on_change(dataset_id, {"stage": stage})

    def read_source(self, kind: str, path: str) -> tuple[np.ndarray, list | None, list | None, str]:
        """Reads a source file with TomoVis's own reader.

        Args:
            kind : Import kind.
            path : Source file.

        Returns:
            (cube, height range or None, (azimuth, range) spacing or None, origin text of those facts).
        """

        if kind == "hd5":
            cube    = self.readers.fusar(path)
            heights = None if cube.z_range is None else [float(cube.z_range[0]), float(cube.z_range[1])]
            spacing = None if cube.x_res is None or cube.y_res is None else [float(cube.x_res), float(cube.y_res)]
            return cube.data, heights, spacing, "hd5 attributes"
        if kind == "h5":
            return self.readers.uavsar(path), None, None, ""
        if kind == "rat":
            return self.readers.rat(path), None, None, ""
        if kind == "npy":
            return self.readers.npy(path), None, None, ""

        data, has_metadata = self.sessions.read(path)
        meta               = self.sessions.metadata(path) if has_metadata else {}
        heights            = [float(meta["z_min"]), float(meta["z_max"])] if "z_min" in meta and "z_max" in meta else None
        spacing            = [float(meta["x_res"]), float(meta["y_res"])] if "x_res" in meta and "y_res" in meta else None
        if heights == self.sample_heights(data):
            heights = None
        if spacing == list(TomoVisLink.DEFAULT_SPACING):
            spacing = None
        return data, heights, spacing, "TomoVis session"

    def sample_heights(self, data: np.ndarray) -> list[float]:
        """Returns the elevation range TomoVis sets after an import that brings no heights (F-015): 0 to the last axis's length minus one.

        A session saved with this range, or with TomoVis's default 1.0 x 1.0
        spacing, holds TomoVis's defaults rather than measured values, so the
        dataset still asks for them like the file the session came from.

        Args:
            data : Session cube, the last axis being range.

        Returns:
            [0.0, shape[-1] - 1].
        """

        return [0.0, float(data.shape[-1] - 1)]

    def convert(self, record: DatasetRecord) -> None:
        """Writes the source as data/tomovis_cube.npy with its height range and spacing, then the TomoVis link.

        Args:
            record : Working copy of the dataset record; its ``tomovis_cube`` is updated.
        """

        kind    = record.source["kind"]
        run_dir = Path(record.id)
        target  = run_dir / "data" / "tomovis_cube.npy"
        self.report(record.id, f"converting {kind} to npy", 0.0)

        data, heights, spacing, origin = self.read_source(kind, record.source["path"])
        self.workspace.writer.array(target, np.ascontiguousarray(data, dtype=data.dtype.newbyteorder("=")))
        del data

        origins = {}
        if heights is not None:
            self.workspace.write_height_range(run_dir, heights)
            origins["height_range"] = origin
        if spacing is not None:
            self.workspace.write_spacing(run_dir, spacing)
            origins["spacing"] = origin

        record.tomovis_cube = str(target)
        self.on_change(record.id, {"tomovis_cube": str(target), "origins": origins})
        self.workspace.write_links(record)
        self.report(record.id, f"converting {kind} to npy", 1.0)

    def shape(self, record: DatasetRecord) -> tuple:
        """Returns the shape of the dataset's TomoVis cube from its header."""

        return self.workspace.inspector.read_header(Path(record.tomovis_cube))[0]

    def check(self, record: DatasetRecord) -> None:
        """Refuses a cube the tools cannot read, sets the footprint in dataset.json and the default channel.

        Args:
            record : Working copy of the dataset record; its ``channel`` is updated.

        Raises:
            ValueError : If the cube is not 3-D, 4-D or 5-D with a square channel pair.
        """

        shape = self.shape(record)
        if len(shape) not in (3, 4, 5) or (len(shape) == 5 and shape[0] != shape[1]):
            raise ValueError(f"TomoVic tools need a 3-D cube (elevation, azimuth, range) or a multi-channel cube; {record.name} has shape {' x '.join(str(n) for n in shape)}.")

        run_dir    = Path(record.id)
        n_az, n_rg = shape[-2], shape[-1]
        crop       = self.workspace.inspector.read_json(run_dir / "data" / "dataset.json")["global_crop"]
        if crop is None or (crop[1] - crop[0], crop[3] - crop[2]) != (n_az, n_rg):
            self.workspace.update_layout(run_dir, {"global_crop": [0, n_az, 0, n_rg]}, {})

        if len(shape) > 3 and record.channel is None:
            record.channel = "combined"
            self.on_change(record.id, {"channel": "combined"})

    def slabs(self, n_az: int, line_bytes: int) -> list[tuple[int, int]]:
        """Splits the azimuth axis into slabs of about SLAB_BYTES input bytes.

        Args:
            n_az       : Azimuth extent.
            line_bytes : Input bytes of one azimuth line.

        Returns:
            (start, stop) azimuth ranges covering [0, n_az).
        """

        step = max(1, self.SLAB_BYTES // max(1, line_bytes))
        return [(start, min(start + step, n_az)) for start in range(0, n_az, step)]

    def magnitude(self, block: np.ndarray) -> np.ndarray:
        """Returns |block| as float64, casting real values before the absolute value so integer minima cannot overflow."""

        if np.iscomplexobj(block):
            return np.abs(block).astype(np.float64)
        return np.abs(block.astype(np.float64))

    def channel_slab(self, cube: np.ndarray, choice, start: int, stop: int) -> np.ndarray:
        """Computes one azimuth slab of the channel cube.

        Args:
            cube   : 4-D (C, elevation, azimuth, range) or 5-D (C, C, elevation, azimuth, range) memmap.
            choice : "combined" or a channel index.
            start  : First azimuth line.
            stop   : Azimuth line after the last.

        Returns:
            Float32 (elevation, stop - start, range): |x[c]| or sqrt(sum_c |x[c]|^2) for 4-D, sqrt(|x[c, c]|) or sqrt(sum_c |x[c, c]|) for 5-D.
        """

        if cube.ndim == 4:
            if choice == "combined":
                return np.sqrt(np.sum(self.magnitude(cube[:, :, start:stop, :]) ** 2, axis=0)).astype(np.float32)
            return self.magnitude(cube[choice, :, start:stop, :]).astype(np.float32)

        if choice == "combined":
            total = sum(self.magnitude(cube[c, c, :, start:stop, :]) for c in range(cube.shape[0]))
            return np.sqrt(total).astype(np.float32)
        return np.sqrt(self.magnitude(cube[choice, choice, :, start:stop, :])).astype(np.float32)

    def channel(self, record: DatasetRecord) -> None:
        """Makes data/tomogram_full.npy: a link to a 3-D TomoVis cube, or the chosen channel of a multi-channel one.

        Args:
            record : Working copy of the dataset record.
        """

        run_dir = Path(record.id)
        target  = run_dir / "data" / "tomogram_full.npy"
        cube    = np.load(record.tomovis_cube, mmap_mode="r")

        if cube.ndim == 3:
            source = Path(record.tomovis_cube).resolve()
            if not (target.is_symlink() and os.readlink(target) == str(source)):
                self.workspace.writer.symlink(target, source)
            self.on_change(record.id, {"origins": {"tomogram": "TomoVis cube"}})
            return

        choice = record.channel
        label  = "the combined channel" if choice == "combined" else f"channel {choice + 1}"
        stage  = f"building {label}"
        self.report(record.id, stage, 0.0)

        n_az              = cube.shape[-2]
        slabs             = self.slabs(n_az, cube.nbytes // n_az)
        temporary, output = self.workspace.writer.memmap(target, cube.shape[-3:], np.float32)
        for index, (start, stop) in enumerate(slabs):
            output[:, start:stop, :] = self.channel_slab(cube, choice, start, stop)
            self.report(record.id, stage, (index + 1) / len(slabs))
        output.flush()
        del output, cube

        self.workspace.writer.commit(temporary, target)
        self.on_change(record.id, {"origins": {"tomogram": "combined channel" if choice == "combined" else f"channel {choice + 1}"}})
        self.workspace.write_links(record)

    def standin(self, record: DatasetRecord) -> None:
        """Writes data/primary.npy as sqrt(sum over elevation of |tomogram|), non-finite samples counted as 0.

        Args:
            record : Working copy of the dataset record.
        """

        run_dir = Path(record.id)
        stage   = "building the stand-in primary image"
        self.report(record.id, stage, 0.0)

        tomogram   = np.load(run_dir / "data" / "tomogram_full.npy", mmap_mode="r")
        n_az, n_rg = tomogram.shape[1:]
        primary    = np.empty((n_az, n_rg), dtype=np.float32)
        slabs      = self.slabs(n_az, tomogram.nbytes // n_az)

        for index, (start, stop) in enumerate(slabs):
            block = self.magnitude(tomogram[:, start:stop, :])
            block[~np.isfinite(block)] = 0.0
            primary[start:stop] = np.sqrt(np.sum(block, axis=0))
            self.report(record.id, stage, (index + 1) / len(slabs))
        del tomogram

        self.workspace.writer.array(run_dir / "data" / "primary.npy", primary)
        self.workspace.update_layout(run_dir, {}, {"primary": "primary.npy"})
        self.on_change(record.id, {"origins": {"primary": "stand-in"}})

    def finish(self, dataset_id: str, changes: dict) -> None:
        """Hands the final state to the bridge, then stops reporting progress for the dataset."""

        self.on_change(dataset_id, changes)
        with self.lock:
            self.running.pop(dataset_id, None)

    def run(self, job: PreparationJob) -> None:
        """Runs the steps of one job; any failure leaves the dataset in state "error" with its cause, logged with the traceback.

        Args:
            job : The job.
        """

        try:
            record = DatasetRecord.load(job.record_path, self.workspace.writer)
            for step in job.steps:
                getattr(self, step)(record)
        except Exception as error:
            self.logger.error(f"bridge: preparing {job.dataset_id} failed: {error}\n{traceback.format_exc()}")
            self.finish(job.dataset_id, {"state": "error", "stage": "", "error": str(error)})
            return

        self.finish(job.dataset_id, {"state": "ready", "stage": "", "error": ""})
        self.logger.info(f"bridge: {job.dataset_id} is ready for the TomoVic tools")

    def loop(self) -> None:
        """Worker thread: takes jobs off the queue forever and runs them one at a time."""

        while True:
            job = self.jobs.get()
            try:
                self.run(job)
            finally:
                self.jobs.task_done()
