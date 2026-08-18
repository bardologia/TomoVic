"""Completion marker written into a run directory once its work finished.

The presence of the marker file is what resume logic reads to decide whether a
unit can be reused, and its payload carries whatever the writer recorded about
the finished run.
"""

from __future__ import annotations

from pathlib import Path

from tools.data.io         import FileIO
from tools.runtime.run_tag import RunTag


class CompletionMarker:
    """Reads and writes the complete.json marker of a run directory.

    Attributes:
        FILENAME: Name of the marker file inside a run directory.
    """

    FILENAME = "complete.json"

    @staticmethod
    def path(directory: Path) -> Path:
        """Returns the marker path inside the given directory."""
        return Path(directory) / CompletionMarker.FILENAME

    @staticmethod
    def is_complete(directory: Path) -> bool:
        """Returns whether the directory carries a completion marker."""
        return CompletionMarker.path(directory).is_file()

    @staticmethod
    def payload(directory: Path) -> dict:
        """Returns the decoded marker payload of a completed directory."""
        return FileIO.load_json(CompletionMarker.path(directory))

    @staticmethod
    def clear(directory: Path) -> None:
        """Removes the marker if present, so the directory counts as unfinished."""
        CompletionMarker.path(directory).unlink(missing_ok=True)

    @staticmethod
    def stamp(directory: Path, payload: dict) -> Path:
        """Writes the marker with a completion timestamp merged into the payload.

        Args:
            directory: Run directory the marker is written into.
            payload: Fields recorded alongside the completion timestamp.

        Returns:
            Path of the written marker.
        """
        path = CompletionMarker.path(directory)
        FileIO.save_json({"completed_at": RunTag.timestamp(), **payload}, path)
        return path
