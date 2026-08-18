"""Runs-root registry and run discovery for the web UI result tabs.

`CatalogRoots` validates the directories the user opens and remembers them, so
later requests carrying a path can be confined to already-catalogued roots.
`RunScanner` walks those roots to list inference stamps or checkpointed runs.
"""

from __future__ import annotations

import threading
from pathlib import Path


class CatalogRoots:
    """Thread-safe set of runs roots the user has opened this session.

    Attributes:
        lock: Guards the root set against concurrent request threads.
        roots: Absolute resolved root paths, stored as strings.
    """

    NOT_SET = "set the runs directory in the Results tab first"

    def __init__(self) -> None:
        """Builds an empty catalogue."""
        self.lock  = threading.Lock()
        self.roots = set()

    @staticmethod
    def resolve(raw: str, empty_error: str = NOT_SET) -> tuple[Path | None, str]:
        """Validates a user-supplied directory path without registering it.

        Args:
            raw: Path as typed by the user; blank counts as unset.
            empty_error: Message returned when the path is blank.

        Returns:
            Tuple of the resolved directory and an empty string on success, or
            None and an error message when the path is blank, relative, or not a
            directory.
        """
        raw = (raw or "").strip()
        if not raw:
            return None, empty_error

        root = Path(raw).expanduser()
        if not root.is_absolute():
            return None, "an absolute path is required"

        root = root.resolve()
        if not root.is_dir():
            return None, f"not a directory: {root}"

        return root, ""

    def add(self, root: Path) -> None:
        """Registers a resolved directory as a known runs root."""
        with self.lock:
            self.roots.add(str(root))

    def known(self, raw: str) -> bool:
        """Returns whether the exact path string is already a catalogued root."""
        return raw in self.snapshot()

    def contains(self, target: Path) -> bool:
        """Returns whether the target lies under any catalogued root."""
        return any(target.is_relative_to(root) for root in self.snapshot())

    def enclosing(self, target: Path) -> Path | None:
        """Returns the deepest catalogued root containing the target, or None.

        Args:
            target: Path to locate among the known roots.

        Returns:
            The longest matching root path, or None when no root contains it.
        """
        matches = [root for root in self.snapshot() if target.is_relative_to(root)]
        if not matches:
            return None
        return Path(max(matches, key=len))

    def snapshot(self) -> tuple:
        """Returns a lock-free copy of the catalogued root paths."""
        with self.lock:
            return tuple(self.roots)

    def open(self, raw: str, empty_error: str = NOT_SET) -> tuple[Path | None, str]:
        """Validates a directory path and registers it as a runs root.

        Args:
            raw: Path as typed by the user.
            empty_error: Message returned when the path is blank.

        Returns:
            Tuple of the resolved and registered root and an empty string, or None
            and the validation error.
        """
        root, error = self.resolve(raw, empty_error)
        if error:
            return None, error

        self.add(root)
        return root, ""


class RunScanner:
    """Discovers inference stamps and checkpointed runs beneath a runs root.

    Attributes:
        roots: Catalogue the scanned base directories are registered in.
    """

    STAMP_MARKER = "inference/*/cubes/pred_curves.npy"

    def __init__(self, roots: CatalogRoots) -> None:
        """Binds the scanner to a runs-root catalogue.

        Args:
            roots: Catalogue that validates and remembers the scanned bases.
        """
        self.roots = roots

    @staticmethod
    def _entry(root: Path, run_dir: Path, stamp: str, target: Path) -> dict:
        """Builds one listing entry for a discovered run or stamp.

        Args:
            root: Runs root the listing is relative to.
            run_dir: Directory of the run the target belongs to.
            stamp: Inference stamp name, empty for checkpoint listings.
            target: Path the client sends back to select this entry.

        Returns:
            Dictionary with the target id, run name, parent group path and stamp.
        """
        return {
            "id"    : str(target),
            "run"   : run_dir.name,
            "group" : str(run_dir.relative_to(root).parent),
            "stamp" : stamp,
        }

    def stamps(self, base: str, required: tuple[str, ...] = ()) -> dict:
        """Lists inference stamps under a runs root that saved prediction cubes.

        Args:
            base: Runs root to scan; it is registered in the catalogue on success.
            required: Extra paths, relative to each stamp directory, that must all
                exist for the stamp to be listed.

        Returns:
            Dictionary with "ok"; on success also "root" and "entries" sorted by
            descending path, on failure "error" and an empty "entries" list.
        """
        root, error = self.roots.open(base)
        if error:
            return {"ok": False, "error": error, "entries": []}

        entries = []
        for marker in sorted(root.rglob(self.STAMP_MARKER)):
            stamp_dir = marker.parent.parent
            if any(not (stamp_dir / rel).is_file() for rel in required):
                continue

            run_dir = stamp_dir.parent.parent
            entries.append(self._entry(root, run_dir, stamp_dir.name, stamp_dir))

        entries.sort(key=lambda entry: entry["id"], reverse=True)
        return {"ok": True, "root": str(root), "entries": entries}

    def checkpoint_runs(self, base: str, checkpoint_name: str, config_names: tuple[str, ...]) -> dict:
        """Lists runs under a root that hold a given checkpoint and a resolved config.

        Args:
            base: Runs root to scan; it is registered in the catalogue on success.
            checkpoint_name: Checkpoint filename to search for, e.g. "best_model.pt".
            config_names: Candidate filenames under the run's meta directory; a run
                is listed when at least one of them exists.

        Returns:
            Dictionary with "ok"; on success also "root" and "entries" sorted by
            descending path, on failure "error" and an empty "entries" list.
        """
        root, error = self.roots.open(base)
        if error:
            return {"ok": False, "error": error, "entries": []}

        entries = []
        for marker in sorted(root.rglob(checkpoint_name)):
            run_dir = marker.parent
            if not any((run_dir / "meta" / name).is_file() for name in config_names):
                continue

            entries.append(self._entry(root, run_dir, "", run_dir))

        entries.sort(key=lambda entry: entry["id"], reverse=True)
        return {"ok": True, "root": str(root), "entries": entries}
