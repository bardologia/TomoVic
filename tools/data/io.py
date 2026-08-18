"""Filesystem helpers for run directories, JSON payloads and text metadata."""
from __future__ import annotations

import json
import os
from pathlib import Path


class FileIO:
    """Directory creation and JSON/text serialisation used across the pipelines."""
    @staticmethod
    def ensure_dir(path: Path) -> Path:
        """Creates a directory and its parents, returning it."""
        Path(path).mkdir(parents=True, exist_ok=True)
        return Path(path)

    @staticmethod
    def ensure_dirs(*paths: Path) -> None:
        """Creates every given directory and its parents."""
        for path in paths:
            Path(path).mkdir(parents=True, exist_ok=True)

    @staticmethod
    def save_json(payload: dict, path: Path, indent: int = 4, atomic: bool = False) -> Path:
        """Writes a payload as JSON and returns the destination path.

        Args:
            payload: Mapping to serialise; unknown objects fall back to ``str``.
            path: Destination file; its parent is created.
            indent: JSON indentation width.
            atomic: Whether to write to a pid-suffixed temporary file and rename it into place.

        Returns:
            The destination path.
        """
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)

        target = path.with_name(f"{path.name}.{os.getpid()}.tmp") if atomic else path
        with open(target, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=indent, default=str)

        if atomic:
            os.replace(target, path)

        return path

    @staticmethod
    def load_json(path: Path) -> dict:
        """Loads and returns the JSON payload at the given path."""
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    @staticmethod
    def save_text_metadata(entries: dict, path: Path) -> Path:
        """Writes one 'key: value' line per entry and returns the destination path."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)

        with open(path, "w", encoding="utf-8") as f:
            for key, value in entries.items():
                f.write(f"{key}: {value}\n")

        return path

