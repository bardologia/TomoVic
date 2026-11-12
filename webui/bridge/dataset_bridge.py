"""The dataset bridge facade: one current dataset per console, shared by TomoVis and the TomoVic tools.

``DatasetBridge`` is what the workspace router and the TomoVis import watch
call. It registers a file imported in TomoVis as a workspace run in the same
request as the import, registers a TomoVic run on its first use, keeps the
current dataset with who set it, remembers which dataset each TomoVis window
holds, and computes for a window whether the page should open the current
dataset through its TomoVis link.
"""

from __future__ import annotations

import threading
from pathlib import Path

from bridge.array_check       import ArrayCheck
from bridge.cube_preparer     import CubePreparer, PreparationJob
from bridge.dataset_record    import DatasetRecord
from bridge.dataset_workspace import DatasetWorkspace
from bridge.piece_store       import PieceStore
from catalog_roots            import CatalogRoots
from cube_explorer            import CubeExplorer, SliceCollector
from lru_cache                import LruCache
from web_logger               import WebLogger


class BridgeRefusal(Exception):
    """A request the bridge answers with an error status and a plain message.

    Attributes:
        status : HTTP status of the answer (400, 404 or 409).
        piece  : Piece key the refusal is about, None for none.
    """

    def __init__(self, message: str, status: int, piece: str | None = None) -> None:
        """Stores the message, status and piece.

        Args:
            message : Text shown to the user.
            status  : HTTP status.
            piece   : Piece key, None for none.
        """

        super().__init__(message)
        self.status = status
        self.piece  = piece


class DatasetBridge:
    """Facade of the bridge for the routers and the TomoVis import watch.

    Attributes:
        workspace     : Workspace holding the records.
        cubes         : Cube explorer whose roots and caches the bridge maintains.
        slices        : Slice collector whose contexts the bridge drops.
        logger        : Console logger.
        inspector     : Read-only run inspector.
        lock          : Guards the records, the current pointer and the held map.
        pointer       : current.json of the workspace.
        current       : {id, serial, set_by} of the current dataset.
        held          : TomoVis window sid to {id, name, tomovis_revision} of the dataset it opened.
        preparer      : Background preparation of imports.
        store         : Writer of the pieces added to imports.
        bridge_error  : Last registration error of a TomoVis import, cleared by the next success.
        HELD_CAPACITY : Number of TomoVis windows whose held dataset is remembered.
    """

    HELD_CAPACITY = 64

    def __init__(self, workspace: DatasetWorkspace, cubes: CubeExplorer, slices: SliceCollector, logger: WebLogger) -> None:
        """Wires the bridge without touching the disk; ``start`` reads the workspace.

        Args:
            workspace : Workspace holding the records.
            cubes     : Cube explorer.
            slices    : Slice collector.
            logger    : Console logger.
        """

        self.workspace    = workspace
        self.cubes        = cubes
        self.slices       = slices
        self.logger       = logger
        self.inspector    = workspace.inspector
        self.lock         = threading.RLock()
        self.pointer      = workspace.pointer()
        self.current      = dict(self.pointer.EMPTY)
        self.held         = LruCache(self.HELD_CAPACITY)
        self.preparer     = CubePreparer(workspace, logger, self.prepared)
        self.store        = PieceStore(workspace, ArrayCheck(), logger)
        self.bridge_error = ""

    def job(self, record: DatasetRecord, steps: tuple | None = None) -> PreparationJob:
        """Builds the preparation job of an import.

        Args:
            record : Import record.
            steps  : Steps to run; None for a full preparation from the source file (convert when the TomoVis cube is a workspace file, check, channel, and the stand-in primary while the dataset has no other primary).

        Returns:
            The job.
        """

        if steps is None:
            converted = Path(record.tomovis_cube) != Path(record.source["path"])
            standin   = "primary" not in self.inspector.read_json(Path(record.id) / "data" / "dataset.json")["artifacts"] or record.origins.get("primary") == "stand-in"
            steps     = (("convert",) if converted else ()) + ("check", "channel") + (("standin",) if standin else ())
        return PreparationJob(record.id, record.path, steps)

    def set_current(self, dataset_id: str | None, set_by: str | None) -> None:
        """Changes the current dataset, raising the serial when the id or the setter changed.

        Args:
            dataset_id : New current id, None for none.
            set_by     : "tomovis", "tomovic" or None.
        """

        if dataset_id == self.current["id"] and set_by == self.current["set_by"]:
            return
        self.current = {"id": dataset_id, "serial": self.current["serial"] + 1, "set_by": set_by}
        self.workspace.ensure()
        self.pointer.write(dataset_id, self.current["serial"], set_by)

    def prune(self) -> None:
        """Forgets the datasets whose folder was deleted or moved, and clears the current dataset when it was one of them."""

        self.workspace.prune()
        if self.current["id"] is not None and self.workspace.record(self.current["id"]) is None:
            self.logger.warning(f"bridge: the current dataset {self.current['id']} no longer exists; no dataset is current")
            self.set_current(None, None)

    def start(self) -> None:
        """Reads the workspace, registers the runs roots, resubmits interrupted preparations and starts the preparer."""

        with self.lock:
            records      = self.workspace.scan()
            self.current = self.pointer.read()
            self.prune()

            self.workspace.register_roots()
            for record in records:
                if record.state == "preparing":
                    self.logger.info(f"bridge: preparing {record.id} again after a restart")
                    self.preparer.submit(self.job(record))

        self.preparer.start()
        self.logger.info(f"bridge: workspace {self.workspace.root} holds {len(records)} datasets")

    def forget(self, run_dir: str) -> None:
        """Drops what the Cube and Slices pages hold in memory for a dataset."""

        self.cubes.forget(run_dir)
        self.slices.forget(run_dir)

    def prepared(self, dataset_id: str, changes: dict) -> None:
        """Applies the record fields a preparation step changed; a finished job raises the revision and drops the caches.

        Args:
            dataset_id : Dataset id.
            changes    : Record fields to set; ``origins`` is merged into the record's origins.
        """

        with self.lock:
            record = self.workspace.record(dataset_id)
            if record is None:
                self.logger.warning(f"bridge: {dataset_id} was removed while it was being prepared")
                return

            for key, value in changes.items():
                setattr(record, key, {**record.origins, **value} if key == "origins" else value)
            if "state" in changes and changes["state"] == "ready":
                record.revision += 1
            record.save()

        if "state" in changes:
            self.forget(dataset_id)

    def payload(self, record: DatasetRecord) -> dict:
        """Returns the Dataset payload of a registered dataset."""

        return self.inspector.payload(Path(record.id), record, self.preparer.progress(record.id), self.workspace.link_paths(record))

    def open_for(self, sid: str) -> bool:
        """Says whether the TomoVis window ``sid`` should open the current dataset now.

        True when a dataset is current, its link is ready, a TomoVic page set
        it, and the window holds another dataset, nothing, or this dataset at an
        older TomoVis revision.

        Args:
            sid : TomoVis window session id.

        Returns:
            The open rule of the design's section 3.2.
        """

        with self.lock:
            record = None if self.current["id"] is None else self.workspace.record(self.current["id"])
            if record is None or self.current["set_by"] != "tomovic":
                return False
            if not self.inspector.link_ready(record, self.workspace.link_paths(record)[0]):
                return False

            held = self.held.get(sid)
            return held is None or held["id"] != record.id or held["tomovis_revision"] != record.tomovis_revision

    def current_payload(self, sid: str | None) -> dict:
        """Answers GET /api/workspace/current.

        Args:
            sid : TomoVis window session id, None when the page is not a TomoVis window.

        Returns:
            {ok, workspace, serial, set_by, current, bridge_error} and, with a sid, tomovis {held, open}.
        """

        with self.lock:
            self.prune()
            record  = None if self.current["id"] is None else self.workspace.record(self.current["id"])
            payload = {
                "ok"           : True,
                "workspace"    : str(self.workspace.root),
                "serial"       : self.current["serial"],
                "set_by"       : self.current["set_by"],
                "current"      : None if record is None else self.payload(record),
                "bridge_error" : self.bridge_error,
            }
            if sid is not None:
                payload["tomovis"] = {"held": self.held.get(sid), "open": self.open_for(sid)}
        return payload

    def datasets_payload(self, base: str) -> dict:
        """Answers GET /api/workspace/datasets: every registered dataset, newest opened first.

        Args:
            base : Runs root of the Results tab, may be empty; ``under_base`` says whether a dataset lies under it.

        Returns:
            {ok, current_id, datasets}, each dataset with ``under_base`` and its Cube strip entry.
        """

        root, _ = CatalogRoots.resolve(base) if base else (None, "")
        with self.lock:
            self.prune()
            records  = sorted(self.workspace.records.values(), key=lambda record: record.opened_at, reverse=True)
            datasets = []
            for record in records:
                group   = "workspace" if record.imported else "other folders"
                payload = self.payload(record)
                payload["under_base"] = root is not None and Path(record.id).is_relative_to(root)
                payload["strip"]      = {"id": record.id, "run": record.name, "group": group, "stamp": ""}
                datasets.append(payload)
            return {"ok": True, "current_id": self.current["id"], "datasets": datasets}

    def run_problem(self, dataset_id: str) -> str:
        """Says why an unregistered id is not a run the console may open, empty when it is one.

        Args:
            dataset_id : Id as sent by a page.

        Returns:
            The refusal message, or an empty string.
        """

        run_dir = Path(dataset_id).resolve()
        if not Path(dataset_id).is_absolute() or not self.cubes.roots.contains(run_dir) or run_dir.is_relative_to(self.workspace.root):
            return f"{dataset_id} is outside the runs folders the console has opened."
        if not (run_dir / "data" / "dataset.json").is_file():
            return f"{dataset_id} is not a TomoVic run: it holds no data/dataset.json."
        return ""

    def record_of(self, dataset_id: str) -> DatasetRecord | None:
        """Returns the record of an absolute id as a page sends it (resolved first), None when unregistered or relative."""

        return self.workspace.record(str(Path(dataset_id).resolve())) if dataset_id and Path(dataset_id).is_absolute() else None

    def dataset_payload(self, dataset_id: str) -> dict:
        """Answers GET /api/workspace/dataset, never writing.

        Args:
            dataset_id : Dataset id; an unregistered run under the runs roots is described with ``registered: false``.

        Returns:
            {ok, dataset}.

        Raises:
            BridgeRefusal : 404 for an id that is neither registered nor a run under the runs roots.
        """

        with self.lock:
            self.prune()
            record = self.record_of(dataset_id)
            if record is not None:
                return {"ok": True, "dataset": self.payload(record)}

        if not dataset_id or self.run_problem(dataset_id):
            raise BridgeRefusal(f"unknown dataset: {dataset_id}", 404)
        return {"ok": True, "dataset": self.inspector.payload(Path(dataset_id).resolve(), None, None, None)}

    def recheck_run(self, record: DatasetRecord) -> None:
        """Rewrites a run's link when its tomogram changed size or time (raising both revisions and dropping its caches) or the link is missing.

        Args:
            record : Run record.
        """

        tomogram = Path(record.tomovis_cube)
        stamp    = self.workspace.stamp(tomogram) if tomogram.is_file() else {"size": 0, "mtime_ns": 0}
        changed  = self.workspace.differs(stamp, record)

        if changed:
            record.source            = {**record.source, **stamp}
            record.revision         += 1
            record.tomovis_revision += 1
            record.save()
            self.forget(record.id)
            self.logger.info(f"bridge: the tomogram of {record.id} changed; its TomoVis link is written again")
        if changed or not self.workspace.link_paths(record)[0].is_file():
            self.workspace.write_links(record)

    def use(self, dataset_id: str | None) -> dict:
        """Answers POST /api/workspace/current: makes a dataset current from a TomoVic page.

        A run is registered on its first use (record, link, runs root) and its
        tomogram is re-checked on every use. ``set_by`` always becomes
        "tomovic" and ``opened_at`` is updated.

        Args:
            dataset_id : Dataset id, None to clear the current dataset.

        Returns:
            {ok, serial, set_by, current}.

        Raises:
            BridgeRefusal : 400 for an id that is neither registered nor a run under the runs roots.
        """

        with self.lock:
            self.prune()
            record = None
            if dataset_id is not None:
                record = self.record_of(dataset_id)
                if record is None:
                    problem = self.run_problem(dataset_id)
                    if problem:
                        raise BridgeRefusal(problem, 400)
                    record = self.workspace.link_run(Path(dataset_id).resolve())
                elif not record.imported:
                    self.recheck_run(record)
                record.opened_at = self.workspace.now()
                record.save()

            self.set_current(None if record is None else record.id, "tomovic")
            return {"ok": True, "serial": self.current["serial"], "set_by": self.current["set_by"], "current": None if record is None else self.payload(record)}

    def refuse_busy(self, record: DatasetRecord, piece: str) -> None:
        """Refuses an add while the dataset is being prepared or the Cube page is loading it.

        Raises:
            BridgeRefusal : 409 in either case.
        """

        if record.state == "preparing":
            raise BridgeRefusal(f"{record.name} is still being prepared for the TomoVic tools.", 409, piece)
        with self.cubes.lock:
            loading = self.cubes.status["state"] == "loading" and self.cubes.status["id"] is not None and str(Path(self.cubes.status["id"]).resolve()) == record.id
        if loading:
            raise BridgeRefusal(f"The Cube page is still loading {record.name}. Add the piece when it is ready.", 409, piece)

    def add(self, dataset_id: str, piece: str, fields: dict) -> dict:
        """Answers POST /api/workspace/add: adds one piece to an import.

        After a successful add the revision rises, the record is saved, the
        Cube and Slices caches of the dataset are dropped, and when it is the
        current dataset ``set_by`` becomes "tomovic" so TomoVis windows reopen it
        with what changed. A channel choice or a rebuilt stand-in leaves the
        dataset preparing.

        Args:
            dataset_id : Dataset id.
            piece      : Piece key.
            fields     : The piece's request fields.

        Returns:
            {ok, dataset}.

        Raises:
            BridgeRefusal : 404 for an unknown id, 400 for a run, 409 while busy.
            PieceError    : 400 with the user's sentence when the piece is refused.
        """

        with self.lock:
            self.prune()
            record = self.record_of(dataset_id)
            if record is None and dataset_id and not self.run_problem(dataset_id):
                raise BridgeRefusal(f"{Path(dataset_id).name} is a TomoVic run; the bridge never writes into run folders.", 400, piece)
            if record is None:
                raise BridgeRefusal(f"unknown dataset: {dataset_id}", 404, piece)
            if not record.imported:
                raise BridgeRefusal(f"{record.name} is a TomoVic run; the bridge never writes into run folders.", 400, piece)
            self.refuse_busy(record, piece)

            steps            = self.store.add(record, piece, fields)
            record.revision += 1
            if steps:
                record.state = "preparing"
                record.stage = ""
            record.save()
            self.forget(record.id)
            if steps:
                self.preparer.submit(self.job(record, steps))
            if self.current["id"] == record.id:
                self.set_current(record.id, "tomovic")

            self.logger.info(f"bridge: added the {piece} piece to {record.id}")
            return {"ok": True, "dataset": self.payload(record)}

    def registered(self, kind: str, path: str) -> DatasetRecord:
        """Finds or creates the dataset a TomoVis import is (identity rules 1 to 4), preparing it when needed.

        Args:
            kind : Import kind.
            path : Path TomoVis accepted.

        Returns:
            The dataset's record.
        """

        owner = self.workspace.owner_of(path)
        if owner is not None:
            return self.workspace.record(owner)

        run = self.workspace.run_of(kind, path)
        if run is not None:
            return self.workspace.record(run) or self.workspace.link_run(Path(run))

        record = self.workspace.record(str(self.workspace.import_folder(kind, path)))
        if record is None:
            record = self.workspace.create_import(kind, path)
            self.preparer.submit(self.job(record))
        elif self.workspace.source_changed(record):
            self.workspace.refresh(record)
            self.forget(record.id)
            self.preparer.submit(self.job(record))
        elif record.state == "error":
            record.state = "preparing"
            record.error = ""
            record.save()
            self.preparer.submit(self.job(record))
        return record

    def tomovis_imported(self, sid: str, kind: str, path: str) -> None:
        """Registers a successful TomoVis import, records what the window holds and makes the dataset current when it is another one.

        Args:
            sid  : TomoVis window session id.
            kind : Import kind.
            path : Path TomoVis accepted.
        """

        with self.lock:
            self.prune()
            record = self.registered(kind, path)
            self.held.put(sid, {"id": record.id, "name": record.name, "tomovis_revision": record.tomovis_revision})
            if self.current["id"] != record.id:
                record.opened_at = self.workspace.now()
                record.save()
                self.set_current(record.id, "tomovis")
            self.bridge_error = ""
