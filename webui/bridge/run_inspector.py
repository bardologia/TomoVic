"""Read-only inspection of a dataset's run directory: its pieces, what each tool needs, and the Dataset payload.

The inspector reads JSON files and .npy headers only, never whole arrays, and
keeps parsed files keyed by inode, size and modification time, so the pages can
poll a dataset cheaply even when its track parameters are megabytes of JSON.
``RunInspector.TOOLS`` is the one place that says which pieces each TomoVic tool
and TomoVis feature needs; the pages render what the server sends.
"""

from __future__ import annotations

import json
import os
import threading
from pathlib import Path

import numpy as np

from bridge.dataset_record      import DatasetRecord
from bridge.tomovis_link        import TomoVisLink
from cube_explorer              import LoadProgress, NpyReader
from tools.sar.geocoding        import SceneGeocoder
from tools.sar.geometry_field   import GeometryField
from tools.sar.polarimetry      import PolarimetricArtifact
from tools.sar.track_parameters import TrackParameters


class RunInspector:
    """Describes run directories for the bridge's routes.

    Attributes:
        cache              : File path to (stamp, parsed value) of the files read so far.
        lock               : Guards ``cache``.
        headers            : Reader of .npy headers.
        PIECES             : Piece keys, in display order.
        PIECE_LABELS       : Piece key to its label.
        TOOLS              : Tool key to {label, needs, run_only}.
        ORIGIN_LABELS      : Source kind to the origin chip text.
        PREPROCESSING      : Pieces only a preprocessing run writes.
        LAUNCHES           : Piece key to the entry script and button label that create it.
        RUN_ONLY_NOTE      : Note of a tool that needs a preprocessing run, on an import.
        PREPROCESSING_NOTE : Note of a piece or tool a run lacks and only preprocessing writes.
        MOVED_SOURCE       : Error of an import whose linked tomogram file was moved or deleted.
    """

    PIECES       = ("tomogram", "channel", "height_range", "primary", "spacing", "dem", "geometry", "passes", "polarimetry", "params")
    PIECE_LABELS = {
        "tomogram"     : "Tomogram",
        "channel"      : "Channel",
        "height_range" : "Height range",
        "primary"      : "Primary image",
        "spacing"      : "Pixel spacing",
        "dem"          : "DEM",
        "geometry"     : "Acquisition geometry",
        "passes"       : "Pass stack",
        "polarimetry"  : "Polarimetric primary",
        "params"       : "Parameter run",
    }
    TOOLS = {
        "cube"                         : {"label": "Cube page",                    "needs": ("tomogram", "height_range", "primary"), "run_only": False},
        "slices"                       : {"label": "Slices page",                  "needs": ("tomogram", "height_range", "primary"), "run_only": False},
        "cube_dem"                     : {"label": "DEM terrain",                  "needs": ("dem",),                                "run_only": False},
        "cube_metric"                  : {"label": "Metric scale",                 "needs": ("spacing",),                            "run_only": False},
        "cube_globe"                   : {"label": "Globe and tours",              "needs": ("dem", "geometry"),                     "run_only": False},
        "cube_passes"                  : {"label": "Passes view",                  "needs": ("passes",),                             "run_only": False},
        "cube_pauli"                   : {"label": "Pauli view",                   "needs": ("polarimetry",),                        "run_only": False},
        "cube_param"                   : {"label": "Parametrized tomogram",        "needs": ("params",),                             "run_only": False},
        "extract_params"               : {"label": "Extract Params",               "needs": ("tomogram", "height_range"),            "run_only": False},
        "extract_polarimetry"          : {"label": "Extract Polarimetry",          "needs": (),                                      "run_only": True},
        "analyze_preprocessing"        : {"label": "Analyze Preprocessing",        "needs": (),                                      "run_only": True},
        "analyze_param_extraction"     : {"label": "Analyze Param Extraction",     "needs": ("params", "geometry"),                  "run_only": False},
        "compare_preprocessing_trials" : {"label": "Compare Preprocessing Trials", "needs": (),                                      "run_only": True},
        "tomovis"                      : {"label": "TomoVis window",               "needs": (),                                      "run_only": False},
        "tomovis_metres"               : {"label": "TomoVis axes in metres",       "needs": ("height_range", "spacing"),             "run_only": False},
        "tomovis_scripts"              : {"label": "TomoVis scripts",              "needs": ("height_range",),                       "run_only": False},
    }
    ORIGIN_LABELS = {
        "run"     : "TomoVic run",
        "npy"     : "TomoVis import · npy",
        "hd5"     : "TomoVis import · hd5",
        "h5"      : "TomoVis import · h5",
        "rat"     : "TomoVis import · rat",
        "session" : "TomoVis session",
    }
    PREPROCESSING      = ("tomogram", "height_range", "primary", "spacing", "dem", "geometry", "passes")
    LAUNCHES           = {"params": ("extract_params", "Fit with Extract Params"), "polarimetry": ("extract_polarimetry", "Run Extract Polarimetry")}
    RUN_ONLY_NOTE      = "Needs a preprocessing run made from raw F-SAR data; not available for TomoVis imports."
    PREPROCESSING_NOTE = "Missing from this run; rerun Pre Process to create it."
    MOVED_SOURCE       = "{name} was moved or deleted: {path} is gone. Put the file back, or import it again in TomoVis."

    def __init__(self) -> None:
        """Starts with an empty file cache."""

        self.cache   = {}
        self.lock    = threading.Lock()
        self.headers = NpyReader(LoadProgress())

    def stamp(self, path: Path) -> tuple | None:
        """Returns (inode, size, mtime_ns) of a file, following symlinks, or None when it does not exist."""

        try:
            stat = path.stat()
        except FileNotFoundError:
            return None
        return stat.st_ino, stat.st_size, stat.st_mtime_ns

    def cached(self, path: Path, build):
        """Returns a parsed file from the cache, parsing it again when the file changed.

        Args:
            path  : File to parse.
            build : Callable turning the path into the value to keep.

        Returns:
            The value, or None when the file does not exist.
        """

        stamp = self.stamp(path)
        if stamp is None:
            return None

        key = str(path)
        with self.lock:
            hit = self.cache.get(key)
        if hit is not None and hit[0] == stamp:
            return hit[1]

        value = build(path)
        with self.lock:
            self.cache[key] = (stamp, value)
        return value

    def read_json(self, path: Path) -> dict:
        """Parses a JSON file."""

        return json.loads(path.read_text(encoding="utf-8"))

    def read_header(self, path: Path) -> tuple[tuple, str]:
        """Returns (shape, dtype name) from a .npy header."""

        shape, dtype = self.headers.header(path)
        return tuple(int(n) for n in shape), str(dtype)

    def read_tracks(self, path: Path) -> dict:
        """Reduces a track_parameters.json to the facts the bridge needs.

        Args:
            path : Track parameters file.

        Returns:
            {spacing: [ps_az, ps_rg] of the reference track or None, missing: geocoding keys the reference lacks, labels: track labels}.
        """

        params    = TrackParameters.load(path)
        reference = params.parameters[0]
        spacing   = [float(reference["ps_az"]), float(reference["ps_rg"])] if "ps_az" in reference and "ps_rg" in reference else None
        missing   = [key for key in SceneGeocoder.REQUIRED_KEYS if key not in reference]
        return {"spacing": spacing, "missing": missing, "labels": list(params.labels)}

    def layout(self, run_dir: Path) -> dict:
        """Returns the run's data/dataset.json.

        Raises:
            FileNotFoundError : If the run holds no data/dataset.json.
        """

        layout = self.cached(run_dir / "data" / "dataset.json", self.read_json)
        if layout is None:
            raise FileNotFoundError(f"{run_dir} holds no data/dataset.json")
        return layout

    def artifact(self, run_dir: Path, key: str) -> Path | None:
        """Returns the path the layout names for an artifact, None when it names none (the file may not exist)."""

        name = self.layout(run_dir)["artifacts"].get(key)
        return run_dir / "data" / name if name else None

    def header(self, path: Path | None) -> tuple[tuple, str] | None:
        """Returns (shape, dtype) of a .npy file, None when there is no such file."""

        if path is None:
            return None
        return self.cached(path, self.read_header)

    def footprint(self, run_dir: Path) -> tuple[int, int] | None:
        """Returns (azimuth, range) of the run's 3-D tomogram, None until it exists."""

        header = self.header(self.artifact(run_dir, "tomogram_full"))
        if header is None or len(header[0]) != 3:
            return None
        return header[0][1], header[0][2]

    def height_range(self, run_dir: Path) -> list[float] | None:
        """Returns tomogram_config.height_range of meta/config_state.json in metres, None without the file."""

        state = self.cached(run_dir / "meta" / "config_state.json", self.read_json)
        if state is None:
            return None
        return [float(value) for value in state["tomogram_config"]["height_range"]]

    def tracks(self, run_dir: Path) -> dict | None:
        """Returns the track facts of meta/track_parameters.json, None without the file."""

        return self.cached(run_dir / "meta" / TrackParameters.FILENAME, self.read_tracks)

    def spacing(self, run_dir: Path) -> list[float] | None:
        """Returns the reference track's [ps_az, ps_rg] in metres, None when unknown."""

        tracks = self.tracks(run_dir)
        return None if tracks is None else tracks["spacing"]

    def param_tags(self, run_dir: Path) -> list[str]:
        """Returns the sorted parameter runs under params/ that hold a parameters.npy."""

        params = run_dir / "params"
        if not params.is_dir():
            return []
        return sorted(child.name for child in params.iterdir() if (child / "parameters.npy").is_file())

    def problem(self, path: Path | None) -> str:
        """Returns ``file moved or deleted: <target>`` for a broken link, empty otherwise."""

        if path is not None and path.is_symlink() and not path.exists():
            return f"file moved or deleted: {os.readlink(path)}"
        return ""

    def launch(self, run_dir: Path, key: str) -> dict | None:
        """Returns the launch that creates a piece, prefilled for this dataset, or None."""

        if key not in self.LAUNCHES:
            return None
        script, label = self.LAUNCHES[key]
        return {"script": script, "label": label, "overrides": {"dataset_base_path": str(run_dir.parent), "dataset_filter": [run_dir.name]}}

    def cube_header(self, run_dir: Path, record: DatasetRecord | None) -> tuple[tuple, str] | None:
        """Returns the header of the cube TomoVis shows: the record's TomoVis cube, or a run's tomogram."""

        if record is None:
            return self.header(self.artifact(run_dir, "tomogram_full"))
        return self.header(Path(record.tomovis_cube))

    def channel_count(self, cube: tuple[tuple, str] | None) -> int:
        """Returns the number of channels of a TomoVis cube: shape[0] when 4-D, C when 5-D, 1 otherwise."""

        if cube is None or len(cube[0]) < 4:
            return 1
        return cube[0][0]

    def facts(self, run_dir: Path, record: DatasetRecord | None) -> dict:
        """Collects what the pieces are built from.

        Args:
            run_dir : Dataset run directory.
            record  : Its record, None for an unregistered run.

        Returns:
            Dict of the layout, the artifact headers, the footprint, the height range, the track facts and the origins and links of the record.
        """

        layout  = self.layout(run_dir)
        paths   = {key: self.artifact(run_dir, key) for key in ("tomogram_full", "primary", "dem_full", "secondaries", "interferograms", PolarimetricArtifact.ARTIFACT_KEY)}
        imports = record is not None and record.imported

        return {
            "layout"    : layout,
            "paths"     : paths,
            "headers"   : {key: self.header(path) for key, path in paths.items()},
            "footprint" : self.footprint(run_dir),
            "heights"   : self.height_range(run_dir),
            "tracks"    : self.tracks(run_dir),
            "cube"      : self.cube_header(run_dir, record),
            "imported"  : imports,
            "origins"   : record.origins if imports else {},
            "linked"    : record.linked if imports else {},
            "channel"   : record.channel if record is not None else None,
        }

    def piece(self, run_dir: Path, facts: dict, key: str, present: bool, value, problem: str = "") -> dict:
        """Builds one Piece of the payload.

        Args:
            run_dir : Dataset run directory.
            facts   : Output of ``facts``.
            key     : Piece key.
            present : Whether the piece is there and usable.
            value   : The piece's value as the payload states it.
            problem : What is wrong with a piece that is there but unusable.

        Returns:
            {label, present, value, origin, addable, launch, problem, note}.
        """

        imported = facts["imported"]
        if present:
            origin = facts["origins"][key] if imported and key in facts["origins"] else ("" if imported else "preprocessing")
        else:
            origin = ""

        addable = imported and key not in ("tomogram", "channel")
        note    = self.PREPROCESSING_NOTE if not imported and not present and key in self.PREPROCESSING else ""

        return {
            "label"   : self.PIECE_LABELS[key],
            "present" : present,
            "value"   : value,
            "origin"  : origin,
            "addable" : addable,
            "launch"  : self.launch(run_dir, key) if key == "params" or (key == "polarimetry" and not imported) else None,
            "problem" : problem,
            "note"    : note,
        }

    def plane_piece(self, run_dir: Path, facts: dict, key: str, artifact: str, value) -> dict:
        """Builds the Piece of a 2-D (azimuth, range) artifact: present when it exists and covers the footprint."""

        path    = facts["paths"][artifact]
        header  = facts["headers"][artifact]
        problem = self.problem(path)
        present = header is not None and facts["footprint"] is not None and header[0] == facts["footprint"]
        if header is not None and not present and facts["footprint"] is not None:
            problem = f"{path.name} has shape {' x '.join(str(n) for n in header[0])}, but the tomogram covers {facts['footprint'][0]} x {facts['footprint'][1]}"
        return self.piece(run_dir, facts, key, present, value if present else None, problem)

    def pieces(self, run_dir: Path, record: DatasetRecord | None) -> dict:
        """Lists every piece of a dataset.

        Args:
            run_dir : Dataset run directory.
            record  : Its record, None for an unregistered run.

        Returns:
            Piece key to Piece, in PIECES order.
        """

        facts    = self.facts(run_dir, record)
        headers  = facts["headers"]
        paths    = facts["paths"]
        tomogram = headers["tomogram_full"]
        channels = self.channel_count(facts["cube"])
        tracks   = facts["tracks"]
        field    = (run_dir / "meta" / GeometryField.FILENAME).is_file()

        tomogram_ok = tomogram is not None and len(tomogram[0]) == 3
        secondaries = headers["secondaries"]
        passes_ok   = secondaries is not None and len(secondaries[0]) == 3 and facts["footprint"] is not None and secondaries[0][1:] == facts["footprint"]
        sidecar     = self.cached(run_dir / "meta" / PolarimetricArtifact.SIDECAR, self.read_json)
        polar_ok    = headers[PolarimetricArtifact.ARTIFACT_KEY] is not None and sidecar is not None
        tags        = self.param_tags(run_dir)
        primary     = {"kind": "stand-in" if facts["origins"].get("primary") == "stand-in" else ("file" if facts["imported"] else "run")}
        geometry_ok = tracks is not None and not tracks["missing"]

        pieces = {
            "tomogram"     : self.piece(run_dir, facts, "tomogram", tomogram_ok, {"shape": list(tomogram[0]), "dtype": tomogram[1]} if tomogram_ok else None, self.problem(paths["tomogram_full"])),
            "channel"      : self.piece(run_dir, facts, "channel", channels == 1 or tomogram_ok, facts["channel"] if channels > 1 else None),
            "height_range" : self.piece(run_dir, facts, "height_range", facts["heights"] is not None, facts["heights"]),
            "primary"      : self.plane_piece(run_dir, facts, "primary", "primary", primary),
            "spacing"      : self.piece(run_dir, facts, "spacing", tracks is not None and tracks["spacing"] is not None, None if tracks is None else tracks["spacing"]),
            "dem"          : self.plane_piece(run_dir, facts, "dem", "dem_full", None),
            "geometry"     : self.piece(run_dir, facts, "geometry", geometry_ok, {"run": facts["linked"].get("geometry"), "geometry_field": field} if geometry_ok else None),
            "passes"       : self.piece(run_dir, facts, "passes", passes_ok, {"secondaries": secondaries[0][0], "interferograms": headers["interferograms"] is not None} if passes_ok else None, self.problem(paths["secondaries"])),
            "polarimetry"  : self.piece(run_dir, facts, "polarimetry", polar_ok, {"window": list(sidecar["window"])} if polar_ok else None, self.problem(paths[PolarimetricArtifact.ARTIFACT_KEY])),
            "params"       : self.piece(run_dir, facts, "params", bool(tags), {"tags": tags} if tags else None),
        }

        if channels == 1:
            pieces["channel"]["origin"] = "single channel"
        elif tomogram_ok:
            pieces["channel"]["addable"] = facts["imported"]
            pieces["channel"]["origin"]  = facts["origins"].get("channel", "default")
        return pieces

    def tool(self, key: str, pieces: dict, imported: bool, tomovis: dict) -> dict:
        """Says whether one tool can run on the dataset and what it still needs.

        Args:
            key      : Tool key of TOOLS.
            pieces   : Output of ``pieces``.
            imported : Whether the dataset is a TomoVis import.
            tomovis  : The payload's tomovis block.

        Returns:
            {label, ready, missing, actionable, note}.
        """

        spec = self.TOOLS[key]
        if spec["run_only"] and imported:
            return {"label": spec["label"], "ready": False, "missing": [], "actionable": False, "note": self.RUN_ONLY_NOTE}

        missing = [need for need in spec["needs"] if not pieces[need]["present"]]
        if key == "analyze_param_extraction" and pieces["geometry"]["present"] and not pieces["geometry"]["value"]["geometry_field"]:
            missing.append("geometry")

        ready = not missing
        if key in ("tomovis", "tomovis_metres"):
            ready = ready and tomovis["ready"]
        if key == "tomovis_scripts":
            ready = ready and tomovis["scripts_ready"]

        actionable = all(pieces[need]["addable"] or pieces[need]["launch"] is not None for need in missing)
        note       = self.PREPROCESSING_NOTE if not imported and missing and not actionable else ""
        return {"label": spec["label"], "ready": ready, "missing": missing, "actionable": actionable, "note": note}

    def tools(self, pieces: dict, imported: bool, tomovis: dict) -> dict:
        """Returns tool key to Tool for every tool of TOOLS."""

        return {key: self.tool(key, pieces, imported, tomovis) for key in self.TOOLS}

    def link_ready(self, record: DatasetRecord, link: Path) -> bool:
        """Says whether TomoVis can open a dataset now: its link file and the cube the link points into both exist."""

        return link.is_file() and Path(record.tomovis_cube).exists()

    def tomovis(self, record: DatasetRecord | None, links: tuple[Path, Path] | None, pieces: dict) -> dict:
        """Builds the payload's tomovis block.

        Args:
            record : Dataset record, None for an unregistered run.
            links  : (link, scripts link) paths of a registered dataset, None for an unregistered run.
            pieces : Output of ``pieces``.

        Returns:
            {link, scripts_link, revision, ready, scripts_ready}.
        """

        if record is None:
            return {"link": None, "scripts_link": None, "revision": 0, "ready": False, "scripts_ready": False}

        link, scripts = links
        ready         = self.link_ready(record, link)
        scripts_ready = ready and scripts.is_file() and pieces["height_range"]["present"]
        return {"link": str(link), "scripts_link": str(scripts), "revision": record.tomovis_revision, "ready": ready, "scripts_ready": scripts_ready}

    def payload(self, run_dir: Path, record: DatasetRecord | None, progress: tuple[str, float] | None, links: tuple[Path, Path] | None) -> dict:
        """Builds the Dataset payload of the workspace routes.

        Args:
            run_dir  : Dataset run directory, the id.
            record   : Its record, None for an unregistered run.
            progress : (stage, fraction) of a running preparation, None when none runs.
            links    : (link, scripts link) paths, None for an unregistered run.

        Returns:
            The Dataset dict of the design's section 5.4, plus ``note`` on every piece.
        """

        pieces   = self.pieces(run_dir, record)
        imported = record is not None and record.imported
        cube     = self.cube_header(run_dir, record)
        tomogram = pieces["tomogram"]["value"]
        channels = self.channel_count(cube)
        tomovis  = self.tomovis(record, links, pieces)
        state    = "ready" if record is None else record.state
        error    = "" if record is None else record.error
        kind     = "run" if record is None else record.source["kind"]

        if imported and state == "ready" and pieces["tomogram"]["problem"]:
            state = "error"
            error = self.MOVED_SOURCE.format(name=record.name, path=record.source["path"])

        if state == "preparing":
            stage    = progress[0] if progress is not None else record.stage
            fraction = progress[1] if progress is not None else 0.0
        else:
            stage    = "" if record is None else record.stage
            fraction = 1.0 if state == "ready" else 0.0

        footprint = self.footprint(run_dir)
        return {
            "id"           : str(run_dir),
            "registered"   : record is not None,
            "name"         : run_dir.name if record is None else record.name,
            "origin"       : "import" if imported else "run",
            "origin_label" : self.ORIGIN_LABELS[kind],
            "source"       : {"kind": kind, "path": str(run_dir) if record is None else record.source["path"]},
            "folder"       : str(run_dir),
            "revision"     : 0 if record is None else record.revision,
            "state"        : state,
            "stage"        : stage,
            "progress"     : float(fraction),
            "error"        : error,
            "footprint"    : None if footprint is None else list(footprint),
            "cube"         : None if cube is None else {"shape": list(cube[0]), "dtype": cube[1], "channels": channels, "bytes": self.nbytes(cube)},
            "tomogram"     : tomogram,
            "channel"      : None if channels == 1 else {"choices": ["combined"] + list(range(channels)), "chosen": record.channel if record is not None else "combined"},
            "pieces"       : pieces,
            "tools"        : self.tools(pieces, imported, tomovis),
            "tomovis"      : tomovis,
        }

    def nbytes(self, header: tuple[tuple, str]) -> int:
        """Returns the byte size of an array with the given (shape, dtype)."""

        return int(np.prod(header[0], dtype=np.int64)) * np.dtype(header[1]).itemsize
