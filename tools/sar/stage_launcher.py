"""Shared dispatch of a PyRat stage entry script into the PyRat conda environment.

Every PyRat stage runs as a subprocess whose output the dispatcher does not
capture, and whose entry script writes its own log next to the job spec. The
launcher names that log in the parent's log before the run and again when the
subprocess fails, so the parent's record points at the file holding the
child's traceback.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing  import Optional

from tools.monitoring.logger import Logger
from tools.runtime.conda_env import CondaJobDispatcher


class PyRatStageLauncher:
    """Runs one repository entry script as a subprocess in a foreign conda environment and names its log.

    Attributes:
        ENTRY      : Repository-relative path of the entry script, set by each subclass.
        LOG_NAME   : Name the entry script gives its Logger, the stem of the log file it writes next to the spec, set by each subclass.
        logger     : Logger the dispatch and failure lines go to.
        dispatcher : Conda job dispatcher that runs the entry script.
    """

    ENTRY    = ""
    LOG_NAME = ""

    def __init__(self, env_name: str, logger: Logger, repo_root: Optional[Path] = None) -> None:
        """Builds the launcher around a conda environment.

        Args:
            env_name  : Name of the conda environment holding PyRat.
            logger    : Logger for dispatch output.
            repo_root : Repository root passed to the dispatcher, or None to let the dispatcher resolve it.
        """
        self.logger     = logger
        self.dispatcher = CondaJobDispatcher(env_name, logger, repo_root)

    @classmethod
    def child_log(cls, spec_path: Path) -> Path:
        """Returns the log file the entry script writes for a spec, next to the spec file."""
        return Path(spec_path).parent / f"{cls.LOG_NAME}.log"

    def _dispatch(self, spec: dict, spec_path: Path) -> None:
        """Runs the entry script on a spec, naming its log before the run and again on failure.

        Args:
            spec      : Job specification serialized for the entry script.
            spec_path : Path the specification is written to for the subprocess.

        Raises:
            subprocess.CalledProcessError : If the entry script exits non-zero, after the error line naming its log.
        """
        child_log = self.child_log(spec_path)

        self.logger.subsection(f"Child log: {child_log}")

        try:
            self.dispatcher.dispatch(self.ENTRY, spec, spec_path)
        except subprocess.CalledProcessError as error:
            self.logger.error(f"{self.ENTRY} exited with status {error.returncode}; its traceback is in {child_log}")
            raise
