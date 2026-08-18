"""Resolution of an entry point's configuration dataclass into editable leaves.

Detects which configuration class an entry instantiates by parsing its source,
then runs a bootstrap snippet under the target interpreter that instantiates the
class and prints every leaf with its rendered value, type, editability and enum
choices. Results are cached against a signature of the configuration tree so a
config edit invalidates them, and concurrent requests for the same entry share a
single subprocess.
"""

from __future__ import annotations

import ast
import json
import subprocess
import threading

from project_paths import ProjectPaths


class ScriptConfigResolver:
    """Resolves and caches the config leaves of each entry point.

    Attributes:
        paths: Project paths providing entry points and the configuration tree.
        cache: Resolved results keyed by entry point and interpreter, with the config
            tree signature they were produced under.
        entries: Detected config module and class per entry point, keyed by source mtime.
        inflight: Pending resolutions shared by concurrent callers.
        lock: Guards the caches and the in-flight registry.
    """

    BOOTSTRAP = (
        "import json, sys\n"
        "repo = sys.argv[1]\n"
        "sys.path.insert(0, repo)\n"
        "from enum import Enum\n"
        "from pathlib import Path\n"
        "from tools.runtime.config_cli import ConfigCli\n"
        "module = __import__(sys.argv[2], fromlist=[sys.argv[3]])\n"
        "config = getattr(module, sys.argv[3])()\n"
        "def clean(value):\n"
        "    if isinstance(value, Enum):\n"
        "        return value.value\n"
        "    if isinstance(value, Path):\n"
        "        return str(value)\n"
        "    if isinstance(value, dict):\n"
        "        return {clean(key): clean(item) for key, item in value.items()}\n"
        "    if isinstance(value, (list, tuple)):\n"
        "        return [clean(item) for item in value]\n"
        "    return value\n"
        "leaves = []\n"
        "for path, value, section, section_class in ConfigCli.detailed_leaves(config):\n"
        "    editable = ConfigCli.is_editable(value)\n"
        "    if isinstance(value, Path):\n"
        "        rendered = str(value)\n"
        "    elif isinstance(value, Enum):\n"
        "        rendered = str(value.value)\n"
        "    elif isinstance(value, (tuple, list, dict)):\n"
        "        rendered = str(clean(value))\n"
        "    elif value is None:\n"
        "        rendered = 'None'\n"
        "    else:\n"
        "        rendered = str(value)\n"
        "    kind = 'none' if value is None else type(value).__name__\n"
        "    choices = [e.value for e in type(value)] if isinstance(value, Enum) else None\n"
        "    leaves.append({'path': path, 'value': rendered, 'type': kind, 'editable': editable, 'choices': choices, 'section': section, 'section_class': section_class})\n"
        "print(json.dumps(leaves))\n"
    )

    def __init__(self, paths: ProjectPaths) -> None:
        """Stores the project paths and creates the empty caches and lock."""
        self.paths    = paths
        self.cache    = {}
        self.entries  = {}
        self.inflight = {}
        self.lock     = threading.Lock()

    def entry_config(self, key: str) -> dict | None:
        """Returns the configuration module and class an entry point uses.

        Takes the declared module and class when the entry registry names them, and
        otherwise parses the entry source, caching the detection against its mtime.

        Args:
            key: Entry-point key.

        Returns:
            Mapping with `module` and `class`, or None when the entry file is unreadable
            or instantiates no configuration through ConfigCli.
        """
        entry = self.paths.script_entry(key)

        if entry["config_module"] and entry["config_class"]:
            return {"module": entry["config_module"], "class": entry["config_class"]}

        path = entry["path"]
        try:
            stamp = path.stat().st_mtime_ns
        except OSError:
            return None

        with self.lock:
            hit = self.entries.get(key)
            if hit is not None and hit[0] == stamp:
                return hit[1]

        detected = self._detect_entry_config(path)

        with self.lock:
            self.entries[key] = (stamp, detected)
        return detected

    def _detect_entry_config(self, path) -> dict | None:
        """Returns the config module and class an entry source imports and hands to ConfigCli."""
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (OSError, SyntaxError):
            return None

        used = self._config_cli_class(tree)
        if used is None:
            return None

        located = self._locate_import(tree, used)
        if located is None:
            return None

        module, real_name = located
        return {"module": module, "class": real_name}

    def _config_cli_class(self, tree: ast.Module) -> str | None:
        """Returns the name of the class instantiated inside the first ConfigCli call."""
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            if not isinstance(node.func, ast.Name) or node.func.id != "ConfigCli":
                continue
            if not node.args:
                continue

            first = node.args[0]
            if isinstance(first, ast.Call) and isinstance(first.func, ast.Name):
                return first.func.id
        return None

    def _locate_import(self, tree: ast.Module, used: str) -> tuple[str, str] | None:
        """Returns the configuration module and real class name behind a used local name."""
        for node in ast.walk(tree):
            if not isinstance(node, ast.ImportFrom):
                continue
            if not node.module or not node.module.startswith("configuration"):
                continue
            for alias in node.names:
                if (alias.asname or alias.name) == used:
                    return node.module, alias.name
        return None

    def _signature(self, key: str) -> tuple:
        """Returns the change signature of the configuration tree, the entry and config_cli."""
        watched = sorted(self.paths.config_dir.rglob("*.py"))
        watched.append(self.paths.script_entry(key)["path"])
        watched.append(self.paths.repo_root / "tools" / "runtime" / "config_cli.py")

        return self.paths.tree_signature(watched)

    def _run_bootstrap(self, entry: dict, interpreter: str) -> dict:
        """Instantiates the configuration under an interpreter and returns its leaves.

        Args:
            entry: Mapping with the configuration `module` and `class`.
            interpreter: Python interpreter to run the bootstrap snippet under.

        Returns:
            Result with `module`, `config_class` and the `leaves` list, or `ok` False
            with the tail of the subprocess stderr when the import or run fails.
        """
        argv = [interpreter, "-c", self.BOOTSTRAP, str(self.paths.repo_root), entry["module"], entry["class"]]

        try:
            proc = subprocess.run(argv, cwd=str(self.paths.repo_root), capture_output=True, text=True, timeout=180)
        except (OSError, subprocess.TimeoutExpired) as exc:
            return {"ok": False, "error": f"config resolution failed under {interpreter}: {exc}"}

        if proc.returncode != 0:
            tail = "\n".join(proc.stderr.strip().splitlines()[-4:])
            return {"ok": False, "error": f"config resolution failed under {interpreter}:\n{tail}"}

        try:
            leaves = json.loads(proc.stdout.strip().splitlines()[-1])
        except (ValueError, IndexError):
            return {"ok": False, "error": "config resolution produced no output"}

        return {"ok": True, "module": entry["module"], "config_class": entry["class"], "leaves": leaves}

    def resolve(self, key: str, interpreter: str) -> dict:
        """Returns an entry point's config leaves, cached against the configuration tree.

        Serves the cached result while the configuration signature is unchanged. A first
        caller runs the bootstrap subprocess and later callers wait on the same result;
        only successful results enter the cache.

        Args:
            key: Entry-point key.
            interpreter: Python interpreter to resolve under.

        Returns:
            The resolution result, or `ok` False with an error when no configuration is
            detected or the bootstrap fails.

        Raises:
            BaseException: Re-raises whatever the leading resolution raised, in the
                waiting callers as well.
        """
        entry = self.entry_config(key)
        if entry is None:
            return {"ok": False, "error": "no entry configuration detected"}

        signature    = self._signature(key)
        cache_key    = (key, interpreter)
        inflight_key = (key, interpreter, signature)

        with self.lock:
            hit = self.cache.get(cache_key)
            if hit is not None and hit[0] == signature:
                return hit[1]

            pending = self.inflight.get(inflight_key)
            leader  = pending is None
            if leader:
                pending                     = {"event": threading.Event(), "result": None, "failure": None}
                self.inflight[inflight_key] = pending

        if not leader:
            pending["event"].wait()
            if pending["failure"] is not None:
                raise pending["failure"]
            return pending["result"]

        try:
            result            = self._run_bootstrap(entry, interpreter)
            pending["result"] = result
        except BaseException as exc:
            pending["failure"] = exc
            raise
        finally:
            with self.lock:
                self.inflight.pop(inflight_key, None)
            pending["event"].set()

        if result.get("ok"):
            with self.lock:
                self.cache[cache_key] = (signature, result)

        return result
