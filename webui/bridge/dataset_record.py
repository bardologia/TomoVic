"""Atomic workspace writes, dataset records and the current-dataset pointer of the bridge.

Every file the bridge writes goes to a hidden temporary name in the target's
folder and is then moved in place with ``os.replace``, so a TomoVis link read
or a Cube memmap never sees a partial file and replacing a symlink never
writes through it. A ``record.json`` describes one dataset the bridge knows,
and ``current.json`` names the dataset that is current in every tool.
"""

from __future__ import annotations

import json
import os
import secrets
import shutil
from pathlib import Path

import numpy as np


class AtomicWriter:
    """Writes files under a temporary name next to the target, then replaces the target in one rename."""

    def temporary(self, target: Path) -> Path:
        """Returns a hidden temporary path in the target's folder, creating the folder.

        Args:
            target : Final path of the file.

        Returns:
            A path ``.<name>.<random>.tmp`` beside the target.
        """

        target.parent.mkdir(parents=True, exist_ok=True)
        return target.parent / f".{target.name}.{secrets.token_hex(4)}.tmp"

    def commit(self, temporary: Path, target: Path) -> Path:
        """Moves a finished temporary file over the target.

        Args:
            temporary : Fully written temporary file.
            target    : Final path; an existing file or symlink there is replaced.

        Returns:
            The target path.
        """

        os.replace(temporary, target)
        return target

    def text(self, target: Path, text: str) -> Path:
        """Writes a UTF-8 text file atomically.

        Args:
            target : Final path.
            text   : File content.

        Returns:
            The target path.
        """

        temporary = self.temporary(target)
        temporary.write_text(text, encoding="utf-8")
        return self.commit(temporary, target)

    def json(self, target: Path, payload) -> Path:
        """Writes an indented JSON file atomically.

        Args:
            target  : Final path.
            payload : JSON-serialisable value.

        Returns:
            The target path.
        """

        return self.text(target, json.dumps(payload, indent=2))

    def symlink(self, target: Path, source: Path) -> Path:
        """Places a symlink at ``target`` pointing to ``source``, replacing whatever was there.

        Args:
            target : Path of the link.
            source : Absolute path the link points to.

        Returns:
            The target path.
        """

        temporary = self.temporary(target)
        os.symlink(source, temporary)
        return self.commit(temporary, target)

    def array(self, target: Path, array: np.ndarray) -> Path:
        """Saves an array as a C-ordered .npy file atomically.

        Args:
            target : Final .npy path.
            array  : Array to store.

        Returns:
            The target path.
        """

        temporary = self.temporary(target)
        with open(temporary, "wb") as handle:
            np.save(handle, np.ascontiguousarray(array))
        return self.commit(temporary, target)

    def memmap(self, target: Path, shape: tuple, dtype) -> tuple[Path, np.memmap]:
        """Opens a writable .npy memmap under a temporary name, for arrays filled slab by slab.

        Args:
            target : Final .npy path; ``commit`` moves the temporary file there.
            shape  : Array shape.
            dtype  : Array dtype.

        Returns:
            (temporary path, writable memmap of that shape and dtype).
        """

        temporary = self.temporary(target)
        return temporary, np.lib.format.open_memmap(temporary, mode="w+", dtype=dtype, shape=shape)

    def copy(self, target: Path, source: Path) -> Path:
        """Copies a file's bytes atomically.

        Args:
            target : Final path.
            source : File to copy.

        Returns:
            The target path.
        """

        temporary = self.temporary(target)
        shutil.copyfile(source, temporary)
        return self.commit(temporary, target)


class RecordField:
    """Exposes one key of a record's JSON document as a readable and writable attribute.

    Attributes:
        name : Key of the document, the attribute name.
    """

    def __set_name__(self, owner, name: str) -> None:
        """Takes the attribute name as the document key."""

        self.name = name

    def __get__(self, record, owner):
        """Returns the document value, or the descriptor itself on the class."""

        if record is None:
            return self
        return record.data[self.name]

    def __set__(self, record, value) -> None:
        """Stores a value in the document; ``save`` writes it."""

        record.data[self.name] = value


class DatasetRecord:
    """One ``record.json``: what the bridge knows about a dataset.

    Imports keep it in ``<dataset>/bridge/record.json``, runs in
    ``<workspace>/linked/<run name>_<hash8>/record.json``; the link files sit in
    the same folder.

    Attributes:
        path             : Path of the record file.
        data             : The JSON document, one key per field.
        writer           : Atomic writer used by ``save``.
        id               : Absolute path of the dataset's run directory.
        origin           : "import" or "run".
        name             : Display name, the imported file's name or the run directory's name.
        source           : {kind, path, size, mtime_ns} of the imported file, or of a run's tomogram.
        opened_at        : ISO time the dataset last became current.
        revision         : Raised on every change to the dataset.
        tomovis_revision : Raised when what TomoVis would show changes (heights, spacing, source).
        tomovis_cube     : The .npy file the TomoVis link points into.
        channel          : "combined" or a channel index for multi-channel cubes, None otherwise.
        origins          : Piece key to where the piece came from.
        linked           : Piece key to the user file it links.
        state            : "preparing", "ready" or "error".
        stage            : Preparation stage shown to the user, empty when idle.
        error            : Plain cause of a failed preparation, empty otherwise.
        FILENAME         : File name of a record.
        FIELDS           : Keys every record holds, in order.
    """

    FILENAME = "record.json"
    FIELDS   = ("id", "origin", "name", "source", "opened_at", "revision", "tomovis_revision", "tomovis_cube", "channel", "origins", "linked", "state", "stage", "error")

    id               = RecordField()
    origin           = RecordField()
    name             = RecordField()
    source           = RecordField()
    opened_at        = RecordField()
    revision         = RecordField()
    tomovis_revision = RecordField()
    tomovis_cube     = RecordField()
    channel          = RecordField()
    origins          = RecordField()
    linked           = RecordField()
    state            = RecordField()
    stage            = RecordField()
    error            = RecordField()

    def __init__(self, path: Path, data: dict, writer: AtomicWriter) -> None:
        """Wraps a record document.

        Args:
            path   : Record file path.
            data   : Document holding exactly FIELDS.
            writer : Atomic writer.

        Raises:
            ValueError : If the document's keys are not exactly FIELDS.
        """

        if set(data) != set(self.FIELDS):
            raise ValueError(f"{path} holds the keys {sorted(data)}, but a dataset record holds {list(self.FIELDS)}")

        self.path   = Path(path)
        self.data   = {key: data[key] for key in self.FIELDS}
        self.writer = writer

    @classmethod
    def load(cls, path: Path, writer: AtomicWriter) -> DatasetRecord:
        """Reads a record file.

        Args:
            path   : Record file path.
            writer : Atomic writer for later saves.

        Returns:
            The record.
        """

        return cls(path, json.loads(Path(path).read_text(encoding="utf-8")), writer)

    @property
    def folder(self) -> Path:
        """Folder holding the record and the dataset's TomoVis link files."""

        return self.path.parent

    @property
    def imported(self) -> bool:
        """Whether the dataset is a TomoVis import (the bridge may write its folder)."""

        return self.origin == "import"

    def save(self) -> None:
        """Writes the record atomically."""

        self.writer.json(self.path, self.data)


class CurrentPointer:
    """The workspace's ``current.json``: the current dataset id, a change serial and who set it.

    Attributes:
        path   : Path of current.json.
        writer : Atomic writer.
        EMPTY  : Pointer value while no file exists.
    """

    EMPTY = {"id": None, "serial": 0, "set_by": None}

    def __init__(self, path: Path, writer: AtomicWriter) -> None:
        """Stores the file path.

        Args:
            path   : Path of current.json.
            writer : Atomic writer.
        """

        self.path   = Path(path)
        self.writer = writer

    def read(self) -> dict:
        """Returns {id, serial, set_by}, the empty pointer when the file does not exist."""

        if not self.path.is_file():
            return dict(self.EMPTY)

        stored = json.loads(self.path.read_text(encoding="utf-8"))
        return {"id": stored["id"], "serial": int(stored["serial"]), "set_by": stored["set_by"]}

    def write(self, dataset_id: str | None, serial: int, set_by: str | None) -> None:
        """Writes the pointer atomically.

        Args:
            dataset_id : Current dataset id, None for none.
            serial     : Change serial.
            set_by     : "tomovis", "tomovic" or None.
        """

        self.writer.json(self.path, {"id": dataset_id, "serial": int(serial), "set_by": set_by})
