"""The bridge's workspace folder: dataset records, identity rules and the files the bridge writes.

The workspace (by default ``<repo root>/workspace``) is the only place the
bridge writes. ``imports/<stem>_<kind>_<hash8>/`` is one run directory per file
imported in TomoVis; ``linked/<run name>_<hash8>/`` holds the record and the
TomoVis link of a TomoVic run, whose own folder is never written;
``current.json`` names the current dataset. Nothing is created on disk until a
dataset is registered or the current dataset is first set.
"""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import re
from datetime import datetime
from pathlib  import Path

import numpy as np

from bridge.dataset_record      import AtomicWriter, CurrentPointer, DatasetRecord
from bridge.run_inspector       import RunInspector
from bridge.tomovis_link        import TomoVisLink
from catalog_roots              import CatalogRoots
from tools.sar.track_parameters import TrackParameters
from web_logger                 import WebLogger


class WorkspaceBusyError(RuntimeError):
    """Raised when a console starts on a workspace another console already uses."""


class DatasetWorkspace:
    """Owns the workspace folder and the in-memory index of its dataset records.

    Attributes:
        root        : Resolved workspace folder.
        roots       : The cube explorer's catalogued runs roots, which the workspace and every registered run join.
        logger      : Console logger.
        writer      : Atomic writer of every workspace file.
        link        : TomoVis link writer.
        inspector   : Read-only run inspector.
        records     : Dataset id to its record.
        claimed     : File descriptor holding the console's lock on the workspace folder, None until ``claim``.
        KINDS       : Import kinds.
        SAFE        : Characters replaced by ``_`` in folder names.
        TRACK_LABEL : Track label of a spacing-only track parameters file.
        README_TEXT : Content of the workspace README.txt.
    """

    KINDS       = ("npy", "hd5", "h5", "rat", "session")
    SAFE        = re.compile(r"[^A-Za-z0-9._-]")
    TRACK_LABEL = "bridge"
    README_TEXT = (
        "TomoVic workspace\n"
        "\n"
        "This folder holds what the TomoVic console adds to your data so that TomoVis and the TomoVic tools work on the same datasets.\n"
        "\n"
        "imports/  One folder per file you opened in TomoVis. Each one is a run folder the Cube, Slices and launch pages can read. Your .npy files are linked, not copied. hd5, h5, rat and TomoVis session files are converted once to tomovis_cube.npy here. Pieces you add (height range, primary image, DEM and so on) are stored in the same folder: picked .npy files are linked, parameter runs are copied.\n"
        "\n"
        "linked/  One folder per TomoVic run you opened, holding the file TomoVis opens that run through. The run folder itself is never written.\n"
        "\n"
        "current.json  The dataset that is current in every tool.\n"
        "\n"
        "Deleting a folder here removes that dataset from the lists. Your own files are never touched.\n"
    )

    def __init__(self, root: Path, roots: CatalogRoots, logger: WebLogger) -> None:
        """Binds the workspace folder without touching the disk.

        Args:
            root   : Workspace folder; it is created on the first write.
            roots  : The cube explorer's runs-root catalogue.
            logger : Console logger.
        """

        self.root      = Path(root).expanduser().resolve()
        self.roots     = roots
        self.logger    = logger
        self.writer    = AtomicWriter()
        self.link      = TomoVisLink(self.writer)
        self.inspector = RunInspector()
        self.records   = {}
        self.claimed   = None

    @property
    def imports_dir(self) -> Path:
        """Folder of the import run directories."""

        return self.root / "imports"

    @property
    def linked_dir(self) -> Path:
        """Folder of the records and links of TomoVic runs."""

        return self.root / "linked"

    @property
    def current_path(self) -> Path:
        """Path of current.json."""

        return self.root / "current.json"

    def pointer(self) -> CurrentPointer:
        """Returns the current-dataset pointer of this workspace."""

        return CurrentPointer(self.current_path, self.writer)

    def ensure(self) -> None:
        """Creates the workspace folders and writes README.txt once."""

        self.imports_dir.mkdir(parents=True, exist_ok=True)
        self.linked_dir.mkdir(parents=True, exist_ok=True)
        readme = self.root / "README.txt"
        if not readme.is_file():
            self.writer.text(readme, self.README_TEXT)

    def claim(self) -> None:
        """Locks the workspace folder for this console until the process ends, creating the folder when missing.

        Each console keeps its own index of the records and its own current
        dataset, so two consoles on one workspace would overwrite each other's
        records and current.json. The lock is an exclusive ``flock`` on the
        folder itself.

        Raises:
            WorkspaceBusyError : If another console holds the workspace.
        """

        self.root.mkdir(parents=True, exist_ok=True)
        handle = os.open(self.root, os.O_RDONLY)
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            os.close(handle)
            raise WorkspaceBusyError(f"another TomoVic console uses the workspace {self.root}; stop it, or start this console with --workspace <another folder>") from None
        self.claimed = handle

    def scan(self) -> list[DatasetRecord]:
        """Reads every record in the workspace into the index, leaving out folders that lost their dataset.

        Returns:
            The records kept, in folder order.
        """

        self.records = {}
        found        = []
        for folder in sorted(self.imports_dir.iterdir()) if self.imports_dir.is_dir() else []:
            if folder.name.startswith("."):
                continue
            path = folder / "bridge" / DatasetRecord.FILENAME
            if not path.is_file():
                self.logger.warning(f"bridge: {folder} holds no bridge/{DatasetRecord.FILENAME}; it is left out of the dataset lists")
                continue
            found.append(DatasetRecord.load(path, self.writer))

        for folder in sorted(self.linked_dir.iterdir()) if self.linked_dir.is_dir() else []:
            if folder.name.startswith("."):
                continue
            path = folder / DatasetRecord.FILENAME
            if not path.is_file():
                self.logger.warning(f"bridge: {folder} holds no {DatasetRecord.FILENAME}; it is left out of the dataset lists")
                continue
            found.append(DatasetRecord.load(path, self.writer))

        for record in found:
            if self.gone(record):
                self.logger.warning(f"bridge: the dataset folder {record.id} was deleted; it is left out of the dataset lists")
                continue
            self.records[record.id] = record
        return list(self.records.values())

    def prune(self) -> None:
        """Drops from the index the datasets whose folder was deleted or moved while the console runs."""

        for record in [record for record in self.records.values() if self.gone(record)]:
            self.logger.warning(f"bridge: the dataset folder {record.id} was deleted or moved; it is left out of the dataset lists")
            del self.records[record.id]

    def gone(self, record: DatasetRecord) -> bool:
        """Says whether a dataset lost its record file or its data/dataset.json.

        Args:
            record : Dataset record.

        Returns:
            True when the record file or the dataset folder's data/dataset.json no longer exists.
        """

        return not record.path.is_file() or not (Path(record.id) / "data" / "dataset.json").is_file()

    def add_root(self, run_dir: Path) -> None:
        """Lets the Cube and Slices pages open a run folder outside the runs roots the user opened."""

        self.roots.add(Path(run_dir))

    def register_roots(self) -> None:
        """Adds the workspace and the folder of every registered run to the catalogued runs roots."""

        self.add_root(self.root)
        for record in self.records.values():
            if not record.imported:
                self.add_root(Path(record.id))

    def record(self, dataset_id: str) -> DatasetRecord | None:
        """Returns the record of a dataset id, None when the dataset is not registered."""

        return self.records.get(dataset_id)

    def located(self, path: str) -> Path:
        """Returns a typed path made absolute with its folder resolved and its own name kept (a link stays a link)."""

        typed = Path(os.path.abspath(path))
        return Path(os.path.realpath(typed.parent)) / typed.name

    def link_paths(self, record: DatasetRecord) -> tuple[Path, Path]:
        """Returns (link, scripts link) of a dataset; the scripts link is the link itself for a 3-D TomoVis cube."""

        link   = record.folder / TomoVisLink.NAME
        header = self.inspector.header(Path(record.tomovis_cube))
        if header is not None and len(header[0]) != 3:
            return link, record.folder / TomoVisLink.SCRIPTS_NAME
        return link, link

    def owner_of(self, path: str) -> str | None:
        """Applies rules 1 and 2 of the dataset identity: a link file of a record, or a file inside an import folder.

        Args:
            path : Path TomoVis accepted, as typed.

        Returns:
            The owning dataset id, None when neither rule applies.
        """

        located = self.located(path)
        for record in self.records.values():
            if located in (record.folder / TomoVisLink.NAME, record.folder / TomoVisLink.SCRIPTS_NAME):
                return record.id

        if not located.is_relative_to(self.imports_dir):
            return None
        parts = located.relative_to(self.imports_dir).parts
        if not parts:
            return None
        candidate = str(self.imports_dir / parts[0])
        return candidate if candidate in self.records else None

    def run_of(self, kind: str, path: str) -> str | None:
        """Applies rule 3: an npy import of ``<R>/data/<name>`` where R's dataset.json names it the full tomogram.

        Args:
            kind : Import kind.
            path : Path TomoVis accepted, tested without resolving symlinks.

        Returns:
            The run id R (resolved), None when the rule does not apply.
        """

        typed = Path(os.path.abspath(path))
        if kind != "npy" or typed.parent.name != "data":
            return None

        run_dir = typed.parent.parent
        layout  = run_dir / "data" / "dataset.json"
        if not layout.is_file():
            return None
        if json.loads(layout.read_text(encoding="utf-8"))["artifacts"].get("tomogram_full") != typed.name:
            return None
        return str(run_dir.resolve())

    def import_folder(self, kind: str, path: str) -> Path:
        """Applies rule 4: the import folder keyed by the kind and the resolved path.

        Args:
            kind : Import kind.
            path : Path TomoVis accepted.

        Returns:
            ``<workspace>/imports/<stem>_<kind>_<first 8 hex of sha1(kind:resolved path)>``.
        """

        typed  = Path(os.path.abspath(path))
        digest = hashlib.sha1(f"{kind}:{typed.resolve()}".encode("utf-8")).hexdigest()
        return self.imports_dir / f"{self.SAFE.sub('_', typed.stem)}_{kind}_{digest[:8]}"

    def stamp(self, path: Path) -> dict:
        """Returns {size, mtime_ns} of a file."""

        stat = Path(path).stat()
        return {"size": stat.st_size, "mtime_ns": stat.st_mtime_ns}

    def differs(self, stamp: dict, record: DatasetRecord) -> bool:
        """Says whether a file stamp differs from the size and modification time a record holds for its source.

        Args:
            stamp  : {size, mtime_ns} of the file now.
            record : Dataset record.

        Returns:
            True when the size or the modification time changed.
        """

        return (stamp["size"], stamp["mtime_ns"]) != (record.source["size"], record.source["mtime_ns"])

    def needs_conversion(self, kind: str, path: Path) -> bool:
        """Says whether TomoVis's cube must be converted to a C-ordered native .npy before the tools can use it.

        Args:
            kind : Import kind.
            path : Resolved source file.

        Returns:
            True for every kind but npy, and for an npy that is Fortran-ordered, in non-native byte order or in a header version other than 1.0 and 2.0.
        """

        if kind != "npy":
            return True

        with open(path, "rb") as handle:
            version = np.lib.format.read_magic(handle)
        array = np.load(path, mmap_mode="r")
        return version not in ((1, 0), (2, 0)) or bool(np.isfortran(array)) or not array.dtype.isnative

    def now(self) -> str:
        """Returns the local time as an ISO string to the second."""

        return datetime.now().isoformat(timespec="seconds")

    def create_import(self, kind: str, source: str) -> DatasetRecord:
        """Writes the skeleton of a new import: dataset.json, the record and, for a C-ordered npy, the TomoVis link.

        Args:
            kind   : Import kind.
            source : Path TomoVis accepted.

        Returns:
            The new record, in state "preparing".
        """

        typed    = Path(os.path.abspath(source))
        resolved = typed.resolve()
        folder   = self.import_folder(kind, source)
        convert  = self.needs_conversion(kind, resolved)
        cube     = folder / "data" / "tomovis_cube.npy" if convert else resolved

        self.ensure()
        (folder / "meta").mkdir(parents=True, exist_ok=True)
        self.writer.json(folder / "data" / "dataset.json", {"global_crop": None, "artifacts": {"tomogram_full": "tomogram_full.npy"}, "tomogram_tag": f"tomovis_{kind}", "pass_labels": None, "dataset_type": "TomoVis import"})

        record = DatasetRecord(folder / "bridge" / DatasetRecord.FILENAME, {
            "id"               : str(folder),
            "origin"           : "import",
            "name"             : typed.name,
            "source"           : {"kind": kind, "path": str(resolved), **self.stamp(resolved)},
            "opened_at"        : self.now(),
            "revision"         : 0,
            "tomovis_revision" : 0,
            "tomovis_cube"     : str(cube),
            "channel"          : None,
            "origins"          : {},
            "linked"           : {},
            "state"            : "preparing",
            "stage"            : "",
            "error"            : "",
        }, self.writer)
        record.save()
        self.records[record.id] = record

        if not convert:
            self.write_links(record)
        self.logger.info(f"bridge: registered the TomoVis import {typed} as {folder}")
        return record

    def source_changed(self, record: DatasetRecord) -> bool:
        """Says whether an import's source file changed size or modification time since its record was written."""

        return self.differs(self.stamp(Path(record.source["path"])), record)

    def refresh(self, record: DatasetRecord) -> None:
        """Points an import at its changed source again: new stamp, TomoVis cube and link, both revisions raised, state "preparing".

        Args:
            record : Import record whose source changed.
        """

        source  = Path(record.source["path"])
        convert = self.needs_conversion(record.source["kind"], source)
        written = Path(record.id) / "data" / "tomovis_cube.npy"

        record.source            = {**record.source, **self.stamp(source)}
        record.tomovis_cube      = str(written if convert else source)
        record.revision         += 1
        record.tomovis_revision += 1
        record.state             = "preparing"
        record.stage             = ""
        record.error             = ""
        record.save()

        if not convert:
            written.unlink(missing_ok=True)
            self.write_links(record)
        self.logger.info(f"bridge: {source} changed; preparing {record.id} again")

    def link_run(self, run_dir: Path) -> DatasetRecord:
        """Registers a TomoVic run: its record and TomoVis link in linked/, and its folder as a runs root.

        Args:
            run_dir : Resolved run directory holding data/dataset.json.

        Returns:
            The new record, in state "ready".
        """

        run_dir  = Path(run_dir)
        digest   = hashlib.sha1(str(run_dir).encode("utf-8")).hexdigest()
        folder   = self.linked_dir / f"{self.SAFE.sub('_', run_dir.name)}_{digest[:8]}"
        tomogram = self.inspector.artifact(run_dir, "tomogram_full")
        stamp    = self.stamp(tomogram) if tomogram is not None and tomogram.is_file() else {"size": 0, "mtime_ns": 0}

        self.ensure()
        record = DatasetRecord(folder / DatasetRecord.FILENAME, {
            "id"               : str(run_dir),
            "origin"           : "run",
            "name"             : run_dir.name,
            "source"           : {"kind": "run", "path": str(run_dir), **stamp},
            "opened_at"        : self.now(),
            "revision"         : 0,
            "tomovis_revision" : 0,
            "tomovis_cube"     : str(tomogram if tomogram is not None else run_dir / "data" / "tomogram_full.npy"),
            "channel"          : None,
            "origins"          : {},
            "linked"           : {},
            "state"            : "ready",
            "stage"            : "",
            "error"            : "",
        }, self.writer)
        record.save()
        self.records[record.id] = record

        self.write_links(record)
        self.add_root(run_dir)
        self.logger.info(f"bridge: registered the TomoVic run {run_dir}")
        return record

    def update_layout(self, run_dir: Path, changes: dict, artifacts: dict) -> None:
        """Rewrites an import's data/dataset.json with some top-level keys and artifact names changed.

        Args:
            run_dir   : Import run directory.
            changes   : Top-level keys to set.
            artifacts : Artifact key to file name under data/ to set, or to None to remove the artifact.
        """

        path   = Path(run_dir) / "data" / "dataset.json"
        layout = json.loads(path.read_text(encoding="utf-8"))
        merged = {**layout["artifacts"], **artifacts}
        layout.update(changes)
        layout["artifacts"] = {key: name for key, name in merged.items() if name is not None}
        self.writer.json(path, layout)

    def write_height_range(self, run_dir: Path, height_range) -> None:
        """Writes meta/config_state.json with tomogram_config.height_range in metres."""

        self.writer.json(Path(run_dir) / "meta" / "config_state.json", {"tomogram_config": {"height_range": [float(height_range[0]), float(height_range[1])]}})

    def write_spacing(self, run_dir: Path, spacing) -> None:
        """Writes meta/track_parameters.json with one track holding the azimuth and range pixel spacing in metres."""

        params = TrackParameters(labels=[self.TRACK_LABEL], parameters=[{"ps_az": float(spacing[0]), "ps_rg": float(spacing[1])}], track_files=[])
        self.writer.json(Path(run_dir) / "meta" / TrackParameters.FILENAME, params.to_payload())

    def write_links(self, record: DatasetRecord) -> None:
        """Writes a dataset's TomoVis link and, for a multi-channel cube, its scripts link, with the dataset's current heights and spacing.

        Nothing is written while the TomoVis cube does not exist yet (an import
        still converting, a run without a tomogram); the payload then reports
        the link as not ready.

        Args:
            record : Dataset record.
        """

        cube = Path(record.tomovis_cube)
        if not cube.is_file():
            return

        run_dir       = Path(record.id)
        heights       = self.inspector.height_range(run_dir)
        spacing       = self.inspector.spacing(run_dir)
        link, scripts = self.link_paths(record)
        self.link.write(link, cube, heights, spacing)

        tomogram = self.inspector.artifact(run_dir, "tomogram_full")
        header   = self.inspector.header(tomogram)
        if scripts != link and header is not None and len(header[0]) == 3:
            self.link.write(scripts, tomogram, heights, spacing)
