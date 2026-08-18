"""Loader for the curated Repo Map content served to the web UI.

The curated diagrams live in a sibling JSON file rather than in code, so the map
can be edited without touching the server.
"""

from __future__ import annotations

import json
from pathlib import Path


class RepoMapLibrary:
    """Reads the curated repository-map document from disk.

    Attributes:
        data: Parsed contents of the curated repo-map JSON file.
    """

    DATA_FILE = "repomap_data.json"

    def __init__(self) -> None:
        """Loads the curated repo-map JSON that ships next to this module."""
        self.data = self._load()

    def _load(self) -> dict:
        """Returns the parsed curated repo-map document."""
        path = Path(__file__).resolve().parent / self.DATA_FILE
        return json.loads(path.read_text(encoding="utf-8"))

    def collect(self) -> list[dict]:
        """Returns the curated per-folder map entries for the Repo Map tab."""
        return self.data["folders"]
