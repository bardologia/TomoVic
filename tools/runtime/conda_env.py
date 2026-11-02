"""Dispatch of entry points into a sibling conda environment.

Locates the interpreter of a named environment and runs a repository entry point
under it with a JSON spec file, which is how PyRAT-dependent steps are executed
from the main environment.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing  import List, Optional

from tools.data.io           import FileIO
from tools.monitoring.logger import Logger


class CondaEnv:
    """Locates the Python interpreter of a named conda environment."""

    @staticmethod
    def _candidates(env_name: str) -> List[Path]:
        """Returns the interpreter paths to try, siblings of the running one first."""
        executable = Path(sys.executable).resolve()
        candidates : List[Path] = []

        for parent in executable.parents:
            if parent.name == "envs":
                candidates.append(parent / env_name / "bin" / "python")
                break

        for base in (Path.home() / "miniconda3", Path.home() / "anaconda3", Path.home() / ".conda"):
            candidates.append(base / "envs" / env_name / "bin" / "python")

        return candidates

    @staticmethod
    def interpreter(env_name: str) -> Path:
        """Returns the first existing interpreter of the named environment.

        Args:
            env_name : Conda environment name.

        Returns:
            Path of the environment's python executable.

        Raises:
            FileNotFoundError : If no candidate location holds an interpreter.
        """
        candidates = CondaEnv._candidates(env_name)

        for candidate in candidates:
            if candidate.exists():
                return candidate

        searched = ", ".join(str(candidate) for candidate in candidates)
        raise FileNotFoundError(f"Conda environment '{env_name}' interpreter not found (searched: {searched}); it is required to run pyrat for the reduced tomogram.")


class CondaJobDispatcher:
    """Runs a repository entry point inside another conda environment.

    Attributes:
        env_name  : Environment the entry point is executed in.
        logger    : Logger recording the dispatched command.
        repo_root : Repository root used as the working directory and path base.
    """

    def __init__(self, env_name: str, logger: Logger, repo_root: Optional[Path] = None) -> None:
        """Initializes the dispatcher, defaulting the repository root to this checkout."""
        self.env_name  = env_name
        self.logger    = logger
        self.repo_root = repo_root if repo_root is not None else Path(__file__).resolve().parents[2]

    @staticmethod
    def _library_dir(interpreter: Path) -> str:
        """Returns the lib directory of the environment owning the interpreter."""
        return str(interpreter.parent.parent / "lib")

    @classmethod
    def _already_on_path(cls, interpreter: Path) -> bool:
        """Whether the environment's lib directory is on this process's LD_LIBRARY_PATH already."""
        return cls._library_dir(interpreter) in os.environ.get("LD_LIBRARY_PATH", "").split(":")

    @classmethod
    def _runtime_env(cls, interpreter: Path) -> dict:
        """Returns the environment with the target env's lib directory on LD_LIBRARY_PATH."""
        env          = dict(os.environ)
        library_dir  = cls._library_dir(interpreter)
        library_path = env.get("LD_LIBRARY_PATH", "")

        if not cls._already_on_path(interpreter):
            env["LD_LIBRARY_PATH"] = library_dir + (":" + library_path if library_path else "")

        return env

    def dispatch(self, entry_relative_path: str, spec_payload: dict, spec_path: Path) -> None:
        """Writes the spec and runs the entry point in the target environment.

        The log names the library path the child starts with, since a loader
        failure in the child (the PyRAT GDAL error that hides an osgeo
        ImportError) is reproduced by hand with exactly that path, and the
        directory beside the spec where the child writes its own log.

        Args:
            entry_relative_path : Entry script path relative to the repository root.
            spec_payload        : Job specification serialized to JSON for the entry point.
            spec_path           : Location the specification is written to.

        Raises:
            subprocess.CalledProcessError : If the dispatched process exits non-zero.
        """
        FileIO.save_json(spec_payload, spec_path)

        interpreter = CondaEnv.interpreter(self.env_name)
        entry       = self.repo_root / entry_relative_path
        command     = [str(interpreter), str(entry), "--spec", str(spec_path)]
        env         = self._runtime_env(interpreter)
        state       = "already on LD_LIBRARY_PATH" if self._already_on_path(interpreter) else "prepended to LD_LIBRARY_PATH"

        self.logger.subsection(f"Dispatching '{entry_relative_path}' in env '{self.env_name}': {' '.join(command)}")
        self.logger.info(f"{self._library_dir(interpreter)} {state}; the child runs with LD_LIBRARY_PATH={env['LD_LIBRARY_PATH']} and writes its own log beside the spec in {spec_path.parent}")
        subprocess.run(command, check=True, cwd=str(self.repo_root), env=env)
