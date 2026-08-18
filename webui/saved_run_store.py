"""On-disk store of reusable run definitions saved from the console launcher.

Each saved run is one JSON file named after its identifier, holding the entry
point, interpreter, config overrides, follow-up entry and detach flag.
"""

from __future__ import annotations

import json
import re
import threading
import uuid
from datetime import datetime

from web_logger import WebLogger


class SavedRunStore:
    """Persists, lists, reads and deletes saved run definitions.

    Attributes:
        paths: Project paths providing the store directory and entry-point checks.
        logger: Console logger.
        lock: Guards the directory against concurrent readers and writers.
        directory: Directory holding one JSON file per saved run.
    """

    ID_PATTERN = re.compile(r"^[0-9a-f]{12}$")

    def __init__(self, paths, logger: WebLogger) -> None:
        """Stores the paths and logger and creates the saved-runs directory."""
        self.paths     = paths
        self.logger    = logger
        self.lock      = threading.Lock()
        self.directory = paths.saved_runs_dir
        self.directory.mkdir(parents=True, exist_ok=True)

    def save(self, payload: dict) -> dict:
        """Writes one saved run built from a launcher payload.

        Args:
            payload: Launcher form contents with `script_key`, `interpreter`, optional
                `title`, `name`, `overrides`, `follow_up` and `detach`.

        Returns:
            Result carrying the stored entry, or `ok` False with an error when the entry
            point, follow-up entry or interpreter is missing or unknown.
        """
        key = str(payload.get("script_key", ""))
        if not self.paths.has_script(key):
            return {"ok": False, "error": f"unknown script '{key}'"}

        interpreter = str(payload.get("interpreter", "")).strip()
        if not interpreter:
            return {"ok": False, "error": "no interpreter given"}

        follow_up = str(payload.get("follow_up") or "").strip()
        if follow_up and not self.paths.has_script(follow_up):
            return {"ok": False, "error": f"unknown follow-up script '{follow_up}'"}

        overrides = {str(path): str(value) for path, value in dict(payload.get("overrides") or {}).items()}

        entry = {
            "saved_id"    : uuid.uuid4().hex[:12],
            "script"      : key,
            "title"       : str(payload.get("title", "")).strip() or key,
            "name"        : str(payload.get("name", "")).strip(),
            "interpreter" : interpreter,
            "overrides"   : overrides,
            "follow_up"   : follow_up or None,
            "detach"      : bool(payload.get("detach")),
            "saved_at"    : datetime.now().isoformat(timespec="seconds"),
        }

        with self.lock:
            self._path(entry["saved_id"]).write_text(json.dumps(entry, indent=2) + "\n", encoding="utf-8")

        self.logger.ok(f"saved run '{entry['name'] or entry['title']}' ({entry['saved_id']}) for {key}")
        return {"ok": True, "entry": entry}

    def list(self) -> dict:
        """Returns every saved entry, newest first by save time and identifier."""
        with self.lock:
            entries = [json.loads(path.read_text(encoding="utf-8")) for path in self.directory.glob("*.json")]

        entries.sort(key=lambda entry: (entry["saved_at"], entry["saved_id"]), reverse=True)
        return {"saved": entries}

    def get(self, saved_id: str) -> dict | None:
        """Returns one saved entry, or None when the identifier is malformed or absent."""
        if not self.ID_PATTERN.match(saved_id):
            return None

        with self.lock:
            path = self._path(saved_id)
            if not path.is_file():
                return None
            return json.loads(path.read_text(encoding="utf-8"))

    def delete(self, saved_id: str) -> dict:
        """Deletes one saved entry, or reports that it was not found."""
        if not self.ID_PATTERN.match(saved_id):
            return {"ok": False, "error": "saved run not found"}

        with self.lock:
            path = self._path(saved_id)
            if not path.is_file():
                return {"ok": False, "error": "saved run not found"}
            entry = json.loads(path.read_text(encoding="utf-8"))
            path.unlink()

        self.logger.muted(f"deleted saved run '{entry['name'] or entry['title']}' ({saved_id})")
        return {"ok": True}

    def _path(self, saved_id: str):
        """Returns the JSON file path holding the saved run with this identifier."""
        return self.directory / f"{saved_id}.json"
