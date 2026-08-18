"""Repository layout, entry-point script registry and interpreter discovery.

Resolves the directories the web UI writes to, maps every launchable script key
to its file under main/ and its entry config class, and finds the conda
interpreters a job can be launched with.
"""

from __future__ import annotations

import sys
from pathlib import Path


class ProjectPaths:
    """Resolved paths of a TomoVic checkout plus its script and interpreter registry.

    Attributes:
        webui_root: Directory holding this module and the static assets.
        repo_root: Root of the TomoVic repository.
        main_dir: Directory holding the entry-point scripts.
        scripts_dir: Directory holding the auxiliary scripts.
        config_dir: Root of the configuration package.
        static_dir: Directory served as the front end's static assets.
        logs_dir: Directory the web UI writes logs and state files into.
        gpu_pools_dir: Directory holding per-job live GPU pool files.
        saved_runs_dir: Directory holding saved launch configurations.
    """

    REQUIRED_DIRS   = ("main", "configuration", "tools")
    PRIORITY        = ["conda:dlr-cu12", "conda:Dune", "conda:nazaria"]
    SCRIPT_PRIORITY = {
        "generate_tomogram"       : ["conda:stetools"],
        "generate_interferograms" : ["conda:stetools"],
    }

    ENTRY_OVERRIDES = {}

    def __init__(self, root: Path | None = None) -> None:
        """Resolves every project directory and verifies the root is a real checkout.

        Args:
            root: Repository root; defaults to the parent of the webui directory.

        Raises:
            ValueError: If the resolved root lacks any of REQUIRED_DIRS.
        """
        self.webui_root     = Path(__file__).resolve().parent
        self.repo_root      = self.webui_root.parent if root is None else Path(root).resolve()
        self.main_dir       = self.repo_root / "main"
        self.scripts_dir    = self.repo_root / "scripts"
        self.config_dir     = self.repo_root / "configuration"
        self.static_dir     = self.webui_root / "static"
        self.logs_dir       = self.repo_root / "logs"
        self.gpu_pools_dir  = self.logs_dir / "gpu_pools"
        self.saved_runs_dir = self.logs_dir / "saved_runs"

        self._require_repository()

    def _require_repository(self) -> None:
        """Raises ValueError when the repository root is missing a required directory."""
        missing = [name for name in self.REQUIRED_DIRS if not (self.repo_root / name).is_dir()]

        if missing:
            raise ValueError(f"project root {self.repo_root} is not a TomoVic repository: missing {', '.join(missing)}")

    def tree_signature(self, paths) -> tuple:
        """Returns a cache key of (name, mtime_ns) pairs for the given paths.

        Args:
            paths: Iterable of paths to stamp; unreadable entries are skipped.

        Returns:
            Tuple of (file name, modification time in nanoseconds) pairs.
        """
        stamps = []
        for path in paths:
            try:
                stamps.append((path.name, path.stat().st_mtime_ns))
            except OSError:
                continue
        return tuple(stamps)

    def config_signature(self) -> tuple:
        """Returns the mtime signature of every Python file under the configuration package."""
        return self.tree_signature(sorted(self.config_dir.rglob("*.py")))

    SCRIPT_DIRS = {
        "pre_process"                  : "processing",
        "generate_tomogram"            : "processing",
        "generate_interferograms"      : "processing",
        "analyze_preprocessing"        : "analysis",
        "compare_preprocessing_trials" : "analysis",
    }

    def has_script(self, key: str) -> bool:
        """Returns whether the key names a registered entry-point script."""
        return key in self.SCRIPT_DIRS

    def script_entry(self, key: str) -> dict:
        """Returns the absolute path, repo-relative path and entry config class of a script.

        Args:
            key: Registered script key, such as "pre_process".

        Returns:
            Mapping with "path", "rel", "config_module" and "config_class"; the
            two config entries are None for scripts without an entry override.

        Raises:
            KeyError: If the key is not registered in SCRIPT_DIRS.
        """
        override = self.ENTRY_OVERRIDES.get(key, {})
        subdir   = self.SCRIPT_DIRS[key]
        rel      = f"main/{subdir}/{key}.py"

        return {
            "path"          : self.main_dir / subdir / f"{key}.py",
            "rel"           : rel,
            "config_module" : override.get("config_module"),
            "config_class"  : override.get("config_class"),
        }

    def discover_interpreters(self) -> list[dict]:
        """Returns the conda interpreters available on this machine.

        Scans the miniconda, anaconda and .conda installs under the home
        directory for base and per-environment interpreters, and prepends the
        running interpreter when it is not one of them.

        Returns:
            List of entries with "label", "path" and a "current" flag marking
            the interpreter this server runs under.
        """
        found   = []
        seen    = set()
        current = str(Path(sys.executable))

        home  = Path.home()
        bases = [home / "miniconda3", home / "anaconda3", home / ".conda"]
        for base in bases:
            base_py = base / "bin" / "python"
            if base_py.exists() and str(base_py) not in seen:
                found.append({"label": "conda:base", "path": str(base_py), "current": str(base_py) == current})
                seen.add(str(base_py))

            envs_dir = base / "envs"
            if envs_dir.is_dir():
                for env in sorted(envs_dir.iterdir()):
                    env_py = env / "bin" / "python"
                    if env_py.exists() and str(env_py) not in seen:
                        found.append({"label": f"conda:{env.name}", "path": str(env_py), "current": str(env_py) == current})
                        seen.add(str(env_py))

        if current not in seen and Path(current).exists():
            found.insert(0, {"label": "current", "path": current, "current": True})

        return found

    def preferred_interpreter(self, interpreters: list[dict], script_key: str = "") -> str:
        """Returns the interpreter path a script should default to.

        Args:
            interpreters: Discovered interpreter entries as returned by discover_interpreters.
            script_key: Script key whose per-script priority list is consulted first.

        Returns:
            Path of the highest-priority matching interpreter, the first
            discovered one when none match, or the running interpreter when the
            list is empty.
        """
        priority = self.SCRIPT_PRIORITY.get(script_key, []) + self.PRIORITY
        for wanted in priority:
            for item in interpreters:
                if item["label"] == wanted:
                    return item["path"]
        return interpreters[0]["path"] if interpreters else sys.executable
