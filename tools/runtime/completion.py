"""Completion marker written into a run directory once its work finished.

The presence of the marker file is what resume logic reads to decide whether a
unit can be reused, and its payload carries whatever the writer recorded about
the finished run. The stale-output reset clears an earlier run's marker and
artifacts from a reused output directory after warning what is lost.
"""

from __future__ import annotations

import shutil

from pathlib import Path

from tools.data.io           import FileIO
from tools.runtime.git_state import RunProvenance
from tools.runtime.run_tag   import RunTag


class CompletionMarker:
    """Reads and writes the complete.json marker of a run directory.

    Attributes:
        FILENAME : Name of the marker file inside a run directory.
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
        """Writes the marker with a completion timestamp and the writer's provenance merged into the payload.

        Every marker records the commit, host and library versions of the
        process that finished the work, so two outputs can be traced to the
        code that produced them.

        Args:
            directory : Run directory the marker is written into.
            payload   : Fields recorded alongside the completion timestamp.

        Returns:
            Path of the written marker.
        """
        path = CompletionMarker.path(directory)
        FileIO.save_json({"completed_at": RunTag.timestamp(), **payload, "provenance": RunProvenance.collect()}, path)
        return path


class StaleOutputs:
    """Clears an earlier run's artifacts from a reused output directory after warning what is lost.

    A pipeline writing into an explicit output directory may land on a finished
    run, so the completion marker and every generated directory and file about
    to be removed are named first, with the earlier completion time, and the
    loss is on record in the log.

    Attributes:
        directory  : Output directory shared by the earlier and the new run.
        dir_names  : Names of the generated subdirectories to remove.
        file_names : Names of the generated files to remove.
        logger     : Logger receiving the warning.
    """

    def __init__(self, directory: Path, dir_names: tuple, file_names: tuple, logger) -> None:
        """Binds the reset to its directory and the artifact names it owns.

        Args:
            directory  : Output directory shared by the earlier and the new run.
            dir_names  : Names of the generated subdirectories to remove.
            file_names : Names of the generated files to remove.
            logger     : Logger receiving the warning.
        """
        self.directory  = Path(directory)
        self.dir_names  = tuple(dir_names)
        self.file_names = tuple(file_names)
        self.logger     = logger

    def _present(self) -> tuple:
        """Returns the generated directories and files that currently exist."""
        dirs  = [self.directory / name for name in self.dir_names  if (self.directory / name).is_dir()]
        files = [self.directory / name for name in self.file_names if (self.directory / name).is_file()]

        return dirs, files

    def _describe(self, dirs: list, files: list) -> str:
        """Returns the warning naming the earlier run and every artifact about to go.

        Args:
            dirs  : Existing generated directories.
            files : Existing generated files.
        """
        completed = f"completed at {CompletionMarker.payload(self.directory)['completed_at']}" if CompletionMarker.is_complete(self.directory) else "never completed"
        parts     = [f"{path.name}/ ({sum(1 for item in path.rglob('*') if item.is_file())} files)" for path in dirs] + [path.name for path in files]

        return f"Output directory {self.directory} holds an earlier run ({completed}); removing {', '.join(parts) or 'its completion marker'}"

    def clear(self) -> None:
        """Removes the marker and every present artifact, warning first when anything exists."""
        dirs, files = self._present()

        if CompletionMarker.is_complete(self.directory) or dirs or files:
            self.logger.warning(self._describe(dirs, files))

        CompletionMarker.clear(self.directory)

        for path in dirs:
            shutil.rmtree(path)
        for path in files:
            path.unlink()
