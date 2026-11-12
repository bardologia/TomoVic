"""Directory listing and folder edits for the TomoVis page's QFileDialog look-alike.

Lists one server directory the way QFileDialog shows it: hidden entries
left out, directories always listed, files only when a name filter pattern
matches (case-insensitively, as QFileDialog's name filters), directories
first and each group sorted case-insensitively by name. Each entry carries
the Type column's text (Qt 5.15's QFileSystemModel in the TomoVis
environment: "Folder", "<suffix> File", "File", and "Drive" for the root).
The "Computer" place lists the root. Create New Folder and the in-place
rename follow QFileDialog and QFileSystemModel.
"""

from __future__ import annotations

import fnmatch
import os
from pathlib import Path


class DirectoryLister:
    """Lists server directories for the file dialog and creates and renames folders in them.

    Attributes:
        NEW_FOLDER   : Name QFileDialog gives a new folder; later ones get 2, 3, ... appended.
        INVALID_NAME : QFileSystemModel's message when a rename fails, as (title, rich text with %1 for the name).
    """

    NEW_FOLDER   = "New Folder"
    INVALID_NAME = ("Invalid filename", "<b>The name \"%1\" cannot be used.</b><p>Try using another name, with fewer characters or no punctuation marks.")

    def kind(self, path: Path, directory: bool) -> str:
        """Returns the Type column's text of one entry.

        Args:
            path      : Entry path.
            directory : Whether the entry is a directory (links followed).

        Returns:
            "Drive" for the root, "Folder" for a directory, "<suffix> File" for a file with a suffix, "File" otherwise.
        """

        if str(path) == "/":
            return "Drive"
        if directory:
            return "Folder"
        suffix = path.name.rsplit(".", 1)[1] if "." in path.name else ""
        return f"{suffix} File" if suffix else "File"

    def entry(self, path: Path, name: str | None = None) -> dict | None:
        """Describes one directory entry.

        Args:
            path : Entry path.
            name : Name to show, the path's own name when None.

        Returns:
            {name, dir, size, mtime, type}, None when the entry vanished or cannot be stat-ed.
        """

        try:
            stat = path.stat()
        except OSError:
            return None
        directory = path.is_dir()
        return {"name": name if name is not None else path.name, "dir": directory, "size": 0 if directory else stat.st_size, "mtime": stat.st_mtime, "type": self.kind(path, directory)}

    def computer(self) -> dict:
        """Lists the "Computer" place: the file system root, as QFileSystemModel's myComputer() node on Unix.

        Returns:
            {ok, path: None, computer: True, parent: None, home, writable: False, entries}.
        """

        return {"ok": True, "path": None, "computer": True, "parent": None, "home": str(Path.home()), "writable": False, "entries": [self.entry(Path("/"), "/")]}

    def list(self, path: str, patterns: list[str]) -> dict:
        """Lists one directory.

        Entries that vanish or cannot be stat-ed between listing and stat
        (broken links, races) are left out of the listing. The parent of the
        root is the "Computer" place, as in QFileDialog's Parent Directory.

        Args:
            path     : Absolute directory path; empty means the server user's home directory.
            patterns : Glob patterns of one name filter, e.g. ["*.npy"]; empty lists every file.

        Returns:
            {ok, path, computer: False, parent, home, writable, entries} or {ok: False, error} for a path that is not a readable directory; parent is "" for the root, meaning Computer.

        Raises:
            ValueError : For a relative path.
        """

        home   = str(Path.home())
        target = Path(path) if path else Path(home)
        if not target.is_absolute():
            raise ValueError(f"'{path}' is not an absolute path")
        if not target.is_dir():
            return {"ok": False, "error": f"'{target}' is not a directory"}
        if not os.access(target, os.R_OK | os.X_OK):
            return {"ok": False, "error": f"'{target}' cannot be read"}

        lowered     = [pattern.lower() for pattern in patterns]
        directories = []
        files       = []
        for child in target.iterdir():
            if child.name.startswith("."):
                continue
            described = self.entry(child)
            if described is None:
                continue
            if described["dir"]:
                directories.append(described)
            elif not lowered or any(fnmatch.fnmatchcase(child.name.lower(), pattern) for pattern in lowered):
                files.append(described)

        directories.sort(key=lambda item: item["name"].lower())
        files.sort(key=lambda item: item["name"].lower())
        parent = str(target.parent) if target.parent != target else ""
        return {"ok": True, "path": str(target), "computer": False, "parent": parent, "home": home, "writable": os.access(target, os.W_OK), "entries": directories + files}

    def mkdir(self, path: str) -> dict:
        """Creates a new folder as QFileDialog's Create New Folder does: "New Folder", or "New Folder2", "New Folder3", ... when taken.

        Args:
            path : Absolute directory to create the folder in.

        Returns:
            {ok, name, entry} or {ok: False, error} when the directory is not absolute, missing or the folder cannot be made.
        """

        target = Path(path)
        if not target.is_absolute() or not target.is_dir():
            return {"ok": False, "error": f"'{path}' is not an absolute directory"}

        name   = self.NEW_FOLDER
        suffix = 2
        while (target / name).exists():
            name    = f"{self.NEW_FOLDER}{suffix}"
            suffix += 1
        try:
            (target / name).mkdir()
        except OSError as error:
            return {"ok": False, "error": str(error)}
        return {"ok": True, "name": name, "entry": self.entry(target / name)}

    def rename(self, path: str, old: str, new: str) -> dict:
        """Renames one entry of a directory as QFileSystemModel.setData does.

        An unchanged name succeeds without touching the disk. An empty name,
        a name with "/", an existing target or a failing rename answer with
        QFileSystemModel's "Invalid filename" message, which the browser shows
        as an information box.

        Args:
            path : Absolute directory holding the entry.
            old  : Current name.
            new  : Name typed by the user.

        Returns:
            {ok, entry} or {ok: False, title, text} with the message box's title and rich text.
        """

        target      = Path(path)
        title, text = self.INVALID_NAME
        refused     = {"ok": False, "title": title, "text": text.replace("%1", new)}
        if not target.is_absolute() or not old or "/" in old or old in (".", ".."):
            return {"ok": False, "title": title, "text": text.replace("%1", old)}
        if new == old:
            return {"ok": True, "entry": self.entry(target / old)}
        if not new or "/" in new or (target / new).exists() or (target / new).is_symlink():
            return refused
        try:
            (target / old).rename(target / new)
        except OSError:
            return refused
        return {"ok": True, "entry": self.entry(target / new)}
