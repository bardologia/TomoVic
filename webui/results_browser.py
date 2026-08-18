"""Filesystem browser for run, dataset and results directories served to the console.

Walks an opened results root, classifies files by suffix into markdown, images,
animations, configs and logs, and renders the payloads the Results tab consumes.
"""

from __future__ import annotations

from pathlib      import Path
from urllib.parse import quote

from catalog_roots  import CatalogRoots
from log_transcript import AnsiTranscript
from web_logger     import WebLogger


class ResultsBrowser:
    """Serves directory trees, folder contents, galleries and catalogs of result roots.

    Attributes:
        logger: Console logger used for open/read diagnostics.
        roots: Registry of roots the browser has opened and is allowed to read from.
    """

    IMAGE_SUFFIXES     = {".png", ".jpg", ".jpeg", ".svg", ".webp"}
    ANIMATION_SUFFIXES = {".gif"}
    CONFIG_SUFFIXES    = {".json", ".yaml", ".yml", ".toml", ".ini"}
    MARKDOWN_SUFFIXES  = {".md"}
    LOG_SUFFIXES       = {".log", ".txt", ".out"}

    SKIPPED_DIRS   = {"__pycache__", ".git", ".ipynb_checkpoints"}
    MAX_DEPTH      = 10
    MAX_TEXT_BYTES = 262144

    STAGE_MARKERS = (
        ("preprocess", ("images/slc", "images/interferograms", "images/dem")),
        ("comparison", ("report.md",)),
    )

    def __init__(self, logger: WebLogger) -> None:
        """Stores the console logger and creates an empty opened-root registry."""
        self.logger = logger
        self.roots  = CatalogRoots()

    def tree(self, raw_path: str) -> dict:
        """Opens a results root and returns its recursive file-count tree.

        Args:
            raw_path: Absolute path of the directory to open.

        Returns:
            Payload with `ok`, the resolved `root`, its `name`, the detected pipeline
            `stage` and the nested `tree` of per-directory file counts, or `ok` False
            with an `error` when the path cannot be opened.
        """
        root, error = self.roots.open(raw_path, "an absolute path is required")
        if error:
            return {"ok": False, "error": error}

        self.logger.info(f"results: opened {root}")

        return {
            "ok"    : True,
            "root"  : str(root),
            "name"  : root.name,
            "stage" : self._stage(root),
            "tree"  : self._node(root, root, 0),
        }

    def folder(self, raw_root: str, rel: str) -> dict:
        """Returns the classified file listing of one folder inside an opened root.

        Args:
            raw_root: Root previously opened through `tree`.
            rel: Path of the folder relative to the root, empty for the root itself.

        Returns:
            Payload with the markdown, images, animations, configs, logs and other
            entries of the folder, or `ok` False with an `error` when the root was not
            opened or the folder escapes it.
        """
        if not self.roots.known(raw_root):
            return {"ok": False, "error": "path not opened"}

        folder = (Path(raw_root) / rel).resolve() if rel else Path(raw_root)
        if not folder.is_relative_to(raw_root) or not folder.is_dir():
            return {"ok": False, "error": "unknown folder"}

        markdown, images, animations, configs, logs, other = [], [], [], [], [], []

        for entry in sorted(folder.iterdir()):
            if not entry.is_file():
                continue

            suffix = entry.suffix.lower()

            if suffix in self.MARKDOWN_SUFFIXES:
                markdown.append({"name": entry.name, "text": self._read_text(entry)})
            elif suffix in self.IMAGE_SUFFIXES:
                images.append({"name": entry.stem, "url": self._url(raw_root, entry)})
            elif suffix in self.ANIMATION_SUFFIXES:
                animations.append({"name": entry.stem, "url": self._url(raw_root, entry)})
            elif suffix in self.CONFIG_SUFFIXES:
                configs.append({"name": entry.name, "kind": suffix.lstrip("."), "text": self._read_text(entry)})
            elif suffix in self.LOG_SUFFIXES:
                logs.append({"name": entry.name, "size": entry.stat().st_size, "text": self._read_log(entry)})
            else:
                other.append({"name": entry.name, "size": entry.stat().st_size})

        return {
            "ok"         : True,
            "root"       : raw_root,
            "rel"        : rel,
            "abs"        : str(folder),
            "markdown"   : markdown,
            "images"     : images,
            "animations" : animations,
            "configs"    : configs,
            "logs"       : logs,
            "other"      : other,
        }

    def catalog(self, datasets_raw: str, logs_raw: str) -> dict:
        """Returns the dataset and run catalogs used to populate the browser pickers.

        Args:
            datasets_raw: Path of the datasets root.
            logs_raw: Path of the runs/logs root.

        Returns:
            Payload with a `datasets` entry (each dataset and its parameter runs) and a
            `runs` entry (run directories, newest first, with their detected stage).
        """
        return {
            "ok"       : True,
            "datasets" : self._catalog_datasets(datasets_raw),
            "runs"     : self._catalog_runs(logs_raw),
        }

    def gallery(self, raw_root: str) -> dict:
        """Collects every image and animation under an opened root, grouped by folder.

        Args:
            raw_root: Root previously opened through `tree`.

        Returns:
            Payload with the total image count and one group per folder holding images.
        """
        if not self.roots.known(raw_root):
            return {"ok": False, "error": "path not opened"}

        root   = Path(raw_root)
        groups = []
        self._collect_gallery(root, root, 0, groups)

        total = sum(len(group["images"]) for group in groups)
        return {"ok": True, "root": raw_root, "total": total, "groups": groups}

    def file_path(self, raw_root: str, raw_path: str) -> Path | None:
        """Returns the media file to serve, or None when it escapes an opened root."""
        if not self.roots.known(raw_root):
            return None

        target = Path(raw_path).resolve()
        if not target.is_relative_to(raw_root):
            return None
        if not target.is_file():
            return None
        return target

    def _catalog_datasets(self, raw: str) -> dict:
        """Returns the dataset directories under `raw` with their parameter sub-runs."""
        root, error = self.roots.resolve(raw, "not set")
        if error:
            return {"error": error, "items": []}

        items = []
        for entry in self._subdirs(root):
            params     = []
            params_dir = entry / "params"
            if params_dir.is_dir():
                params = [{"name": child.name, "path": str(child)} for child in self._subdirs(params_dir)]
            items.append({"name": entry.name, "path": str(entry), "params": params})

        return {"error": "", "items": items}

    def _catalog_runs(self, raw: str) -> dict:
        """Returns the run directories under `raw`, newest first, tagged with their stage."""
        root, error = self.roots.resolve(raw, "not set")
        if error:
            return {"error": error, "items": []}

        dirs = self._subdirs(root)
        dirs.sort(key=lambda d: d.stat().st_mtime, reverse=True)

        return {"error": "", "items": [{"name": d.name, "path": str(d), "stage": self._stage(d)} for d in dirs]}

    def _subdirs(self, directory: Path) -> list:
        """Returns the visible, non-skipped sub-directories of `directory`."""
        entries = self._entries(directory)
        return [entry for entry in entries if entry.is_dir() and entry.name not in self.SKIPPED_DIRS and not entry.name.startswith(".")]

    def _collect_gallery(self, directory: Path, root: Path, depth: int, groups: list) -> None:
        """Appends one gallery group per folder holding images, recursing depth-first."""
        entries = self._entries(directory)

        images = []
        for entry in entries:
            if not entry.is_file():
                continue
            suffix = entry.suffix.lower()
            if suffix in self.IMAGE_SUFFIXES:
                images.append({"name": entry.stem, "url": self._url(str(root), entry), "kind": "img"})
            elif suffix in self.ANIMATION_SUFFIXES:
                images.append({"name": entry.stem, "url": self._url(str(root), entry), "kind": "gif"})

        if images:
            rel = "" if directory == root else str(directory.relative_to(root))
            groups.append({"rel": rel, "images": images})

        for entry in entries:
            if entry.is_dir() and entry.name not in self.SKIPPED_DIRS and not entry.name.startswith(".") and depth < self.MAX_DEPTH:
                self._collect_gallery(entry, root, depth + 1, groups)

    def _node(self, directory: Path, root: Path, depth: int) -> dict:
        """Returns the tree node of `directory`: per-kind file counts plus child nodes."""
        counts   = {"markdown": 0, "images": 0, "animations": 0, "configs": 0, "logs": 0, "other": 0}
        children = []
        entries  = self._entries(directory)

        for entry in entries:
            if entry.is_dir():
                if entry.name in self.SKIPPED_DIRS or entry.name.startswith("."):
                    continue
                if depth < self.MAX_DEPTH:
                    children.append(self._node(entry, root, depth + 1))
                continue

            suffix = entry.suffix.lower()

            if suffix in self.MARKDOWN_SUFFIXES:
                counts["markdown"] += 1
            elif suffix in self.IMAGE_SUFFIXES:
                counts["images"] += 1
            elif suffix in self.ANIMATION_SUFFIXES:
                counts["animations"] += 1
            elif suffix in self.CONFIG_SUFFIXES:
                counts["configs"] += 1
            elif suffix in self.LOG_SUFFIXES:
                counts["logs"] += 1
            else:
                counts["other"] += 1

        rel = "" if directory == root else str(directory.relative_to(root))

        return {
            "name"     : directory.name,
            "rel"      : rel,
            "counts"   : counts,
            "children" : children,
        }

    def _stage(self, root: Path) -> str:
        """Returns the pipeline stage a run directory belongs to from its marker files."""
        for stage, markers in self.STAGE_MARKERS:
            if any((root / marker).exists() for marker in markers):
                return stage
        return "results"

    def _entries(self, directory: Path) -> list:
        """Returns the sorted directory entries, empty when the listing fails."""
        try:
            return sorted(directory.iterdir())
        except OSError as exc:
            self.logger.warning(f"results: cannot list {directory}: {exc}")
            return []

    def _read_text(self, target: Path) -> str:
        """Returns the file text, truncated at MAX_TEXT_BYTES with a truncation notice."""
        raw, error = self._read_bytes(target)
        if error:
            return error

        text = raw[: self.MAX_TEXT_BYTES].decode("utf-8", errors="replace")
        if len(raw) > self.MAX_TEXT_BYTES:
            text += "\n\n[truncated]"
        return text

    def _read_log(self, target: Path) -> str:
        """Returns the ANSI-flattened log head, truncated at MAX_TEXT_BYTES."""
        raw, error = self._read_bytes(target)
        if error:
            return error

        if len(raw) <= self.MAX_TEXT_BYTES:
            return self._clean_log(raw.decode("utf-8", errors="replace"))

        head = self._clean_log(raw[: self.MAX_TEXT_BYTES].decode("utf-8", errors="replace"))
        return head + f"\n\n[truncated: showing the first {self.MAX_TEXT_BYTES // 1024} KB of {len(raw) // 1024} KB]"

    def _read_bytes(self, target: Path) -> tuple[bytes, str]:
        """Returns the file bytes and an empty error, or empty bytes and an error note."""
        try:
            return target.read_bytes(), ""
        except OSError as exc:
            self.logger.warning(f"results: cannot read {target}: {exc}")
            return b"", f"[unreadable: {exc}]"

    def _clean_log(self, text: str) -> str:
        """Returns the log text with ANSI control sequences flattened away."""
        return AnsiTranscript().flatten(text)

    def _url(self, raw_root: str, target: Path) -> str:
        """Returns the /resultsmedia URL that serves `target` from within `raw_root`."""
        return "/resultsmedia?root=" + quote(raw_root) + "&path=" + quote(str(target))
