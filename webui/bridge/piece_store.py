"""Adding the pieces a TomoVic tool still needs to a TomoVis import.

Each piece has one method. Picked .npy files are checked against the
dataset's footprint and linked (a symlink to the resolved file, never a copy);
parameter runs are copied, because Extract Params with ``overwrite`` writes into
``params/<tag>``. Every write goes through the workspace's atomic writer and
updates dataset.json, the record's origins and links, and the TomoVis revision
when what TomoVis shows changes. Runs are never written.
"""

from __future__ import annotations

import math
import os
import secrets
import shutil
from pathlib import Path

from bridge.array_check         import ArrayCheck, PieceError
from bridge.dataset_record      import DatasetRecord
from bridge.dataset_workspace   import DatasetWorkspace
from tools.sar.geometry_field   import GeometryField
from tools.sar.polarimetry      import PolarimetricArtifact
from tools.sar.track_parameters import TrackParameters
from web_logger                 import WebLogger


class PieceStore:
    """Writes added pieces into an import's run directory.

    Attributes:
        workspace   : Workspace whose writer, inspector and link writer are used.
        check       : Validator of picked files.
        logger      : Console logger.
        PARAM_FILES : Files copied from a parameter run folder when present.
        PROMPTS     : (piece, field) to the sentence shown when that path field is empty.
    """

    PARAM_FILES = ("parameters.npy", "param_extraction_meta.json", "fit_diagnostics.npz")
    PROMPTS     = {
        ("primary", "path")          : "Pick a .npy file for the Primary image.",
        ("dem", "path")              : "Pick a .npy file for the DEM.",
        ("geometry", "run")          : "Pick the TomoVic run to copy the acquisition geometry from.",
        ("passes", "secondaries")    : "Pick the secondaries .npy file of the pass stack.",
        ("passes", "interferograms") : "Pick the interferograms .npy file, or leave that field empty.",
        ("polarimetry", "path")      : "Pick a .npy file for the Polarimetric primary.",
        ("params", "path")           : "Pick a parameter run folder.",
    }

    def __init__(self, workspace: DatasetWorkspace, check: ArrayCheck, logger: WebLogger) -> None:
        """Stores the collaborators.

        Args:
            workspace : Workspace.
            check     : Validator of picked files.
            logger    : Console logger.
        """

        self.workspace = workspace
        self.check     = check
        self.logger    = logger

    def number(self, value) -> bool:
        """Whether a field value is a finite JSON number (not a boolean)."""

        return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)

    def text(self, fields: dict, key: str, piece: str) -> str:
        """Returns a path field, refusing a value that is not a non-empty string.

        Args:
            fields : Request fields of the piece.
            key    : Name of the path field.
            piece  : Piece key.

        Returns:
            The path as sent.

        Raises:
            PieceError : With the piece's prompt from PROMPTS if the field is missing, empty or not a string.
        """

        value = fields.get(key)
        if not isinstance(value, str) or not value:
            raise PieceError(self.PROMPTS[(piece, key)], piece)
        return value

    def footprint(self, record: DatasetRecord, piece: str) -> tuple[int, int]:
        """Returns the dataset's (azimuth, range) footprint.

        Raises:
            PieceError : If the dataset has no tomogram to compare against.
        """

        footprint = self.workspace.inspector.footprint(Path(record.id))
        if footprint is None:
            raise PieceError(f"{record.name} has no tomogram yet, so the {self.check.LABELS[piece]} cannot be checked against it.", piece)
        return footprint

    def link(self, record: DatasetRecord, piece: str, artifact: str, name: str, source: str) -> None:
        """Links a picked file into data/ and names it in dataset.json.

        Args:
            record   : Import record.
            piece    : Piece key, recorded in the origins and links.
            artifact : Artifact key in dataset.json.
            name     : File name under data/.
            source   : Picked file.
        """

        run_dir = Path(record.id)
        self.workspace.writer.symlink(run_dir / "data" / name, Path(source).resolve())
        self.workspace.update_layout(run_dir, {}, {artifact: name})
        record.origins = {**record.origins, piece: "added"}
        record.linked  = {**record.linked, piece: str(Path(source).resolve())}

    def height_range(self, record: DatasetRecord, fields: dict) -> tuple:
        """Stores two heights in metres as the tomogram's height range and rewrites the TomoVis link.

        Raises:
            PieceError : If the heights are not numbers or not in increasing order.
        """

        low  = fields.get("low")
        high = fields.get("high")
        if not self.number(low) or not self.number(high):
            raise PieceError("Both heights must be numbers.", "height_range")
        if not low < high:
            raise PieceError("The lower height must be below the upper height.", "height_range")

        self.workspace.write_height_range(Path(record.id), (low, high))
        record.origins           = {**record.origins, "height_range": "added"}
        record.tomovis_revision += 1
        self.workspace.write_links(record)
        return ()

    def spacing(self, record: DatasetRecord, fields: dict) -> tuple:
        """Stores the azimuth and range pixel spacing as one-track track parameters, replacing a copied geometry.

        Raises:
            PieceError : If a spacing is not a positive number.
        """

        azimuth = fields.get("azimuth")
        rng     = fields.get("range")
        if not self.number(azimuth) or not self.number(rng) or azimuth <= 0 or rng <= 0:
            raise PieceError("Both spacings must be positive numbers of metres.", "spacing")

        run_dir = Path(record.id)
        self.workspace.write_spacing(run_dir, (azimuth, rng))
        (run_dir / "meta" / GeometryField.FILENAME).unlink(missing_ok=True)

        record.origins           = {key: value for key, value in record.origins.items() if key != "geometry"} | {"spacing": "added"}
        record.linked            = {key: value for key, value in record.linked.items() if key != "geometry"}
        record.tomovis_revision += 1
        self.workspace.write_links(record)
        return ()

    def channel(self, record: DatasetRecord, fields: dict) -> tuple:
        """Chooses the channel of a multi-channel cube the tools show; the preparer rewrites the tomogram.

        Returns:
            The preparation steps to run.

        Raises:
            PieceError : If the choice is neither "combined" nor a channel index.
        """

        header   = self.workspace.inspector.header(Path(record.tomovis_cube))
        channels = self.workspace.inspector.channel_count(header)
        choice   = fields.get("choice")
        valid    = choice == "combined" or (isinstance(choice, int) and not isinstance(choice, bool) and 0 <= choice < channels)
        if channels == 1 or not valid:
            raise PieceError(f'Choose "combined" or a channel number from 0 to {channels - 1}.', "channel")

        record.channel = choice
        record.origins = {**record.origins, "channel": "chosen"}
        standin        = record.origins.get("primary") == "stand-in"
        return ("channel", "standin") if standin else ("channel",)

    def primary(self, record: DatasetRecord, fields: dict) -> tuple:
        """Links a picked primary image, or asks the preparer to rebuild the stand-in from the cube.

        Returns:
            The preparation steps to run.

        Raises:
            PieceError : If the choice is unknown or the picked file is refused.
        """

        if fields.get("from") == "cube":
            record.linked = {key: value for key, value in record.linked.items() if key != "primary"}
            return ("standin",)
        if fields.get("from") != "file":
            raise PieceError('Choose "file" or "cube" as the source of the primary image.', "primary")

        path = self.text(fields, "path", "primary")
        self.check.plane(path, "primary", self.footprint(record, "primary"))
        self.link(record, "primary", "primary", "primary.npy", path)
        return ()

    def dem(self, record: DatasetRecord, fields: dict) -> tuple:
        """Links a picked DEM.

        Raises:
            PieceError : If the file is refused.
        """

        path = self.text(fields, "path", "dem")
        self.check.dem(path, self.footprint(record, "dem"))
        self.link(record, "dem", "dem_full", "dem_full.npy", path)
        return ()

    def geometry(self, record: DatasetRecord, fields: dict) -> tuple:
        """Copies a TomoVic run's acquisition geometry: its track parameters, geometry field, crop offsets, pass labels and, when the dataset has none, its DEM.

        Raises:
            PieceError : If the folder is not a run, has no complete track parameters, covers another footprint or names another number of passes than the dataset's pass stack.
        """

        inspector = self.workspace.inspector
        raw       = self.text(fields, "run", "geometry")
        run       = Path(raw).resolve()
        run_dir   = Path(record.id)
        footprint = self.footprint(record, "geometry")

        if not Path(raw).is_absolute() or not (run / "data" / "dataset.json").is_file():
            raise PieceError(f"{raw} is not a TomoVic run: it holds no data/dataset.json.", "geometry")
        tracks_path = run / "meta" / TrackParameters.FILENAME
        if not tracks_path.is_file():
            raise PieceError(f"{run.name} has no meta/track_parameters.json.", "geometry")
        tracks = inspector.read_tracks(tracks_path)
        if tracks["missing"]:
            raise PieceError(f"The track parameters of {run.name} lack {', '.join(tracks['missing'])}, so they cannot place the scene on the globe.", "geometry")

        layout = inspector.read_json(run / "data" / "dataset.json")
        crop   = [int(value) for value in layout["global_crop"]]
        span   = (crop[1] - crop[0], crop[3] - crop[2])
        if span != tuple(footprint):
            raise PieceError(f"{run.name} covers {span[0]} x {span[1]} pixels but {record.name} is {footprint[0]} x {footprint[1]}; geometry can only be copied from a run with the same footprint.", "geometry")

        labels      = layout["pass_labels"]
        secondaries = inspector.header(inspector.artifact(run_dir, "secondaries"))
        if labels is not None and secondaries is not None and secondaries[0][0] + 1 != len(labels):
            stack = Path(record.linked["passes"]).name if "passes" in record.linked else "secondaries.npy"
            raise PieceError(f"The acquisition geometry copied from {run.name} names {len(labels)} passes, so the pass stack must hold {len(labels) - 1} secondaries; {stack} holds {secondaries[0][0]}.", "geometry")

        spacing_before = inspector.spacing(run_dir)
        self.workspace.writer.copy(run_dir / "meta" / TrackParameters.FILENAME, tracks_path)

        field = run / "meta" / GeometryField.FILENAME
        if field.is_file():
            self.workspace.writer.symlink(run_dir / "meta" / GeometryField.FILENAME, field.resolve())
        else:
            (run_dir / "meta" / GeometryField.FILENAME).unlink(missing_ok=True)
        self.workspace.update_layout(run_dir, {"global_crop": crop, "pass_labels": labels}, {})

        copied  = f"copied from {run.name}"
        origins = {"geometry": copied, "spacing": copied}
        run_dem = inspector.artifact(run, "dem_full")
        if inspector.header(inspector.artifact(run_dir, "dem_full")) is None and run_dem is not None and run_dem.is_file():
            self.workspace.writer.symlink(run_dir / "data" / "dem_full.npy", run_dem.resolve())
            self.workspace.update_layout(run_dir, {}, {"dem_full": "dem_full.npy"})
            origins["dem"] = copied
            record.linked  = {**record.linked, "dem": str(run_dem.resolve())}

        record.origins = {**record.origins, **origins}
        record.linked  = {**record.linked, "geometry": str(run)}
        if tracks["spacing"] != spacing_before:
            record.tomovis_revision += 1
            self.workspace.write_links(record)
        return ()

    def passes(self, record: DatasetRecord, fields: dict) -> tuple:
        """Links a picked secondary stack and, optionally, its interferograms.

        Raises:
            PieceError : If a file is refused or the stack disagrees with the pass labels of a copied geometry.
        """

        path    = self.text(fields, "secondaries", "passes")
        run_dir = Path(record.id)
        stack   = self.check.stack(path, self.footprint(record, "passes"))
        extra   = fields.get("interferograms")
        if extra is not None:
            self.check.interferograms(self.text(fields, "interferograms", "passes"), stack)

        labels = self.workspace.inspector.read_json(run_dir / "data" / "dataset.json")["pass_labels"]
        if labels is not None and stack.shape[0] + 1 != len(labels):
            source = Path(record.linked["geometry"]).name
            raise PieceError(f"The acquisition geometry copied from {source} names {len(labels)} passes, so the pass stack must hold {len(labels) - 1} secondaries; {Path(path).name} holds {stack.shape[0]}.", "passes")

        self.link(record, "passes", "secondaries", "secondaries.npy", path)
        if extra is not None:
            self.workspace.writer.symlink(run_dir / "data" / "interferograms.npy", Path(extra).resolve())
            self.workspace.update_layout(run_dir, {}, {"interferograms": "interferograms.npy"})
        else:
            self.workspace.update_layout(run_dir, {}, {"interferograms": None})
            (run_dir / "data" / "interferograms.npy").unlink(missing_ok=True)
        return ()

    def polarimetry(self, record: DatasetRecord, fields: dict) -> tuple:
        """Links a picked polarimetric primary and writes its sidecar with the multilook window.

        Raises:
            PieceError : If the window is not two whole numbers from 1 to 99 or the file is refused.
        """

        window = fields.get("window")
        if not isinstance(window, list) or len(window) != 2 or not all(isinstance(n, int) and not isinstance(n, bool) and 1 <= n <= 99 for n in window):
            raise PieceError("The multilook window must be two whole numbers from 1 to 99.", "polarimetry")

        path = self.text(fields, "path", "polarimetry")
        self.check.polarimetric(path, self.footprint(record, "polarimetry"))
        self.link(record, "polarimetry", PolarimetricArtifact.ARTIFACT_KEY, PolarimetricArtifact.FILENAME, path)
        self.workspace.writer.json(Path(record.id) / "meta" / PolarimetricArtifact.SIDECAR, {"channels": list(PolarimetricArtifact.CHANNELS), "window": [int(window[0]), int(window[1])]})
        return ()

    def tag(self, record: DatasetRecord, name: str) -> str:
        """Returns a free folder name under params/: the picked folder's name, then name_2, name_3 and so on."""

        params = Path(record.id) / "params"
        tag    = name
        number = 2
        while (params / tag).exists():
            tag     = f"{name}_{number}"
            number += 1
        return tag

    def params(self, record: DatasetRecord, fields: dict) -> tuple:
        """Copies a parameter run folder into params/<folder name> (a clashing name gets _2, _3 and so on).

        Raises:
            PieceError : If the folder is refused.
        """

        folder = Path(self.text(fields, "path", "params"))
        self.check.parameters(str(folder), self.footprint(record, "params"))

        tag     = self.tag(record, folder.name)
        staging = record.folder / f".params_{secrets.token_hex(4)}"
        staging.mkdir(parents=True)
        for name in self.PARAM_FILES:
            if (folder / name).is_file():
                shutil.copyfile(folder / name, staging / name)

        target = Path(record.id) / "params" / tag
        target.parent.mkdir(parents=True, exist_ok=True)
        os.rename(staging, target)
        record.origins = {**record.origins, "params": "added"}
        self.logger.info(f"bridge: copied the parameter run {folder} into {target}")
        return ()

    def add(self, record: DatasetRecord, piece: str, fields: dict) -> tuple:
        """Adds one piece to an import.

        Args:
            record : Import record; its origins, links, channel and TomoVis revision are updated in memory.
            piece  : Piece key.
            fields : Request fields of that piece.

        Returns:
            The preparation steps the bridge must run afterwards, empty when none.

        Raises:
            PieceError : With the user's sentence when the piece is refused.
        """

        handlers = {
            "height_range" : self.height_range,
            "spacing"      : self.spacing,
            "channel"      : self.channel,
            "primary"      : self.primary,
            "dem"          : self.dem,
            "geometry"     : self.geometry,
            "passes"       : self.passes,
            "polarimetry"  : self.polarimetry,
            "params"       : self.params,
        }
        if piece not in handlers:
            raise PieceError(f"{piece} is not a piece that can be added.", piece)
        return handlers[piece](record, fields)
