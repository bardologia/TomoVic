"""Filesystem discovery of datasets, training runs and extracted parameter files.

Backs the web UI pickers by walking dataset roots and run roots, reporting which
directories look like datasets, which runs carry checkpoints or inference output,
and which parameter-extraction trials are complete.
"""

from __future__ import annotations

import re
from pathlib import Path

from web_logger import WebLogger


class DatasetBrowser:
    """Lists datasets, runs, run groups and parameter files under given roots.

    Every public method returns a JSON-ready dict carrying an ``ok`` flag, so the
    web UI can surface bad paths as errors instead of raising.

    Attributes:
        logger: Web logger used to record what each listing found.
    """

    SEED_DIR        = re.compile(r"seed\d+")
    DATA_MARKER     = "data"
    PARAMS_DIR      = "params"
    PARAM_SUFFIX    = ".npy"
    PARAM_META      = "param_extraction_meta.json"
    PARAM_FILE      = "parameters.npy"
    MAX_DEPTH       = 3
    CHECKPOINT_NAME = "best_model.pt"
    INFERENCE_DIR   = "inference"
    RUN_MARKER      = "meta"
    RUN_MAX_DEPTH   = 6

    def __init__(self, logger: WebLogger) -> None:
        """Stores the logger used to report listing results."""
        self.logger = logger

    def datasets(self, raw_base: str) -> dict:
        """Lists the immediate subdirectories of a dataset root.

        Args:
            raw_base: Absolute path of the directory holding dataset folders.

        Returns:
            Dict with ``ok``, the resolved ``base`` and a ``datasets`` list whose
            entries carry name, path, whether a ``data`` subdirectory exists and
            whether extracted parameter files were found.
        """
        base = self._directory(raw_base)
        if base is None:
            return {"ok": False, "error": f"not a directory: {raw_base}"}

        entries = []
        for entry in sorted(base.iterdir()):
            if not entry.is_dir() or entry.name.startswith("."):
                continue

            has_data   = (entry / self.DATA_MARKER).is_dir()
            params_dir = entry / self.PARAMS_DIR
            has_params = params_dir.is_dir() and self._has_param_files(params_dir)

            entries.append({
                "name"       : entry.name,
                "path"       : str(entry),
                "is_dataset" : has_data,
                "has_params" : has_params,
            })

        self.logger.info(f"datasets: listed {len(entries)} under {base}")
        return {"ok": True, "base": str(base), "datasets": entries}

    def runs(self, raw_bases: list[str], seed_units: bool = False) -> dict:
        """Lists every training run directory found under the given roots.

        A run directory is one containing a ``meta`` subdirectory, searched up to
        ``RUN_MAX_DEPTH`` levels down.

        Args:
            raw_bases: Absolute paths of run roots; unusable ones are dropped.
            seed_units: When True, seed sweep parents are inserted as aggregate
                entries ahead of their individual ``seedN`` runs.

        Returns:
            Dict with ``ok``, a comma-joined ``base`` label and a ``runs`` list of
            entries carrying name, path, checkpoint presence and inference presence.
        """
        roots = [resolved for resolved in (self._directory(raw) for raw in raw_bases) if resolved is not None]
        if not roots:
            return {"ok": False, "error": f"no run roots: {raw_bases}"}

        entries = []
        for base in roots:
            base_entries = []
            for run_dir in self._run_dirs(base):
                base_entries.append({
                    "name"           : str(run_dir.relative_to(base)),
                    "path"           : str(run_dir),
                    "has_checkpoint" : (run_dir / self.CHECKPOINT_NAME).is_file(),
                    "has_inference"  : self._has_inference(run_dir),
                })

            entries += self._with_seed_units(base, base_entries) if seed_units else base_entries

        base_label = ", ".join(str(root) for root in roots)
        self.logger.info(f"runs: listed {len(entries)} under {base_label}")
        return {"ok": True, "base": base_label, "runs": entries}

    def _with_seed_units(self, base: Path, run_entries: list[dict]) -> list[dict]:
        """Inserts one aggregate entry per seed-sweep parent before its seed runs.

        Args:
            base: Run root the entry names are relative to.
            run_entries: Run entries as produced by ``runs``.

        Returns:
            The entries with a synthetic unit entry prepended to each group of
            ``seedN`` siblings; a unit reports a checkpoint or inference only when
            every one of its seeds does, plus ``own_inference`` and ``n_seeds``.
        """
        units = {}
        for entry in run_entries:
            run_dir = Path(entry["path"])
            if self.SEED_DIR.fullmatch(run_dir.name) is None or run_dir.parent == base:
                continue

            parent = str(run_dir.parent)
            if parent not in units:
                units[parent] = {
                    "name"           : str(run_dir.parent.relative_to(base)),
                    "path"           : parent,
                    "has_checkpoint" : True,
                    "has_inference"  : True,
                    "own_inference"  : self._has_inference(run_dir.parent),
                    "n_seeds"        : 0,
                }

            unit = units[parent]
            unit["has_checkpoint"] = unit["has_checkpoint"] and entry["has_checkpoint"]
            unit["has_inference"]  = unit["has_inference"] and entry["has_inference"]
            unit["n_seeds"]       += 1

        merged  = []
        emitted = set()
        for entry in run_entries:
            parent = str(Path(entry["path"]).parent)
            if parent in units and parent not in emitted:
                merged.append(units[parent])
                emitted.add(parent)
            merged.append(entry)

        return merged

    def run_groups(self, raw_bases: list[str]) -> dict:
        """Lists the parent folders that hold nested run directories.

        Args:
            raw_bases: Absolute paths of run roots; unusable ones are dropped.

        Returns:
            Dict with ``ok``, a comma-joined ``base`` label and a ``groups`` list of
            entries carrying name, path and the number of runs inside.
        """
        roots = [resolved for resolved in (self._directory(raw) for raw in raw_bases) if resolved is not None]
        if not roots:
            return {"ok": False, "error": f"no run roots: {raw_bases}"}

        entries = []
        for base in roots:
            groups: dict[Path, int] = {}
            for run_dir in self._run_dirs(base):
                if run_dir.parent != base:
                    groups[run_dir.parent] = groups.get(run_dir.parent, 0) + 1

            for group_dir, n_runs in sorted(groups.items()):
                entries.append({
                    "name"   : str(group_dir.relative_to(base)),
                    "path"   : str(group_dir),
                    "n_runs" : n_runs,
                })

        base_label = ", ".join(str(root) for root in roots)
        self.logger.info(f"run_groups: listed {len(entries)} under {base_label}")
        return {"ok": True, "base": base_label, "groups": entries}

    def params(self, raw_dataset: str) -> dict:
        """Lists the ``.npy`` parameter files stored under a dataset's params folder.

        Args:
            raw_dataset: Absolute path of the dataset directory.

        Returns:
            Dict with ``ok``, the dataset path, the ``params_root`` path and a
            ``files`` list of name/path pairs relative to that root; the list is
            empty when the params folder is absent.
        """
        dataset = self._directory(raw_dataset)
        if dataset is None:
            return {"ok": False, "error": f"not a directory: {raw_dataset}"}

        params_dir = dataset / self.PARAMS_DIR
        if not params_dir.is_dir():
            return {"ok": True, "dataset": str(dataset), "params_root": str(params_dir), "files": []}

        files = []
        for path in sorted(self._param_files(params_dir)):
            files.append({
                "name" : str(path.relative_to(params_dir)),
                "path" : str(path),
            })

        self.logger.info(f"params: found {len(files)} under {params_dir}")
        return {"ok": True, "dataset": str(dataset), "params_root": str(params_dir), "files": files}

    def param_trials(self, raw_base: str) -> dict:
        """Lists completed parameter-extraction trials found anywhere under a root.

        A trial counts as complete when its directory holds both the extraction
        metadata file and ``parameters.npy``.

        Args:
            raw_base: Absolute path searched recursively.

        Returns:
            Dict with ``ok``, the resolved ``base`` and a ``trials`` list of entries
            carrying the relative name, absolute path and owning dataset folder.
        """
        base = self._directory(raw_base)
        if base is None:
            return {"ok": False, "error": f"not a directory: {raw_base}"}

        entries = []
        for marker in sorted(base.rglob(self.PARAM_META)):
            run_dir = marker.parent
            if not (run_dir / self.PARAM_FILE).is_file():
                continue

            rel   = run_dir.relative_to(base)
            parts = rel.parts
            entries.append({
                "name"    : str(rel),
                "path"    : str(run_dir),
                "dataset" : parts[0] if len(parts) > 1 else "",
            })

        self.logger.info(f"param_trials: listed {len(entries)} under {base}")
        return {"ok": True, "base": str(base), "trials": entries}

    def _run_dirs(self, base: Path):
        """Yields every run directory below the given root."""
        yield from self._walk_runs(base, 0)

    def _walk_runs(self, directory: Path, depth: int):
        """Yields directories holding a ``meta`` folder, recursing to the depth cap."""
        for entry in sorted(directory.iterdir()):
            if not entry.is_dir() or entry.name.startswith("."):
                continue

            if (entry / self.RUN_MARKER).is_dir():
                yield entry
            elif depth < self.RUN_MAX_DEPTH:
                yield from self._walk_runs(entry, depth + 1)

    def _has_inference(self, run_dir: Path) -> bool:
        """Returns True when the run holds at least one inference output directory."""
        inference_dir = run_dir / self.INFERENCE_DIR
        if not inference_dir.is_dir():
            return False

        for entry in inference_dir.iterdir():
            if entry.is_dir():
                return True
        return False

    def _directory(self, raw: str) -> Path | None:
        """Returns the resolved path when raw is an absolute existing directory, else None."""
        if not raw or not raw.strip():
            return None

        path = Path(raw).expanduser()
        if not path.is_absolute():
            return None

        path = path.resolve()
        return path if path.is_dir() else None

    def _has_param_files(self, params_dir: Path) -> bool:
        """Returns True when at least one ``.npy`` parameter file lies under the folder."""
        for _ in self._param_files(params_dir):
            return True
        return False

    def _param_files(self, params_dir: Path):
        """Yields every ``.npy`` parameter file below the params folder."""
        yield from self._walk(params_dir, 0)

    def _walk(self, directory: Path, depth: int):
        """Yields ``.npy`` files, descending into visible subfolders up to MAX_DEPTH."""
        entries = sorted(directory.iterdir())

        for entry in entries:
            if entry.is_file() and entry.suffix.lower() == self.PARAM_SUFFIX:
                yield entry
            elif entry.is_dir() and not entry.name.startswith(".") and depth < self.MAX_DEPTH:
                yield from self._walk(entry, depth + 1)
