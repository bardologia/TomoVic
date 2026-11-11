"""Directory listing for the TomoVis page's QFileDialog look-alike.

Lists one server directory the way QFileDialog shows it: hidden entries
left out, directories always listed, files only when a name filter pattern
matches (case-insensitively, as QFileDialog's name filters), directories
first and each group sorted case-insensitively by name.
"""

from __future__ import annotations

import fnmatch
import os
from pathlib import Path


class DirectoryLister:
    """Lists server directories for the file dialog."""

    def entry(self, path: Path) -> dict | None:
        """Describes one directory entry.

        Args:
            path : Entry path.

        Returns:
            {name, dir, size, mtime}, None when the entry vanished or cannot be stat-ed.
        """

        try:
            stat = path.stat()
        except OSError:
            return None
        directory = path.is_dir()
        return {"name": path.name, "dir": directory, "size": 0 if directory else stat.st_size, "mtime": stat.st_mtime}

    def list(self, path: str, patterns: list[str]) -> dict:
        """Lists one directory.

        Entries that vanish or cannot be stat-ed between listing and stat
        (broken links, races) are left out of the listing.

        Args:
            path     : Absolute directory path; empty means the server user's home directory.
            patterns : Glob patterns of one name filter, e.g. ["*.npy"]; empty lists every file.

        Returns:
            {ok, path, parent, home, entries} or {ok: False, error} for a path that is not a readable directory.
        """

        home   = str(Path.home())
        target = Path(path) if path else Path(home)
        if not target.is_absolute():
            return {"ok": False, "error": f"'{path}' is not an absolute path"}
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
        parent = str(target.parent) if target.parent != target else None
        return {"ok": True, "path": str(target), "parent": parent, "home": home, "entries": directories + files}
