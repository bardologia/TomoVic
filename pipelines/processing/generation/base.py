"""Shared base for the generators driven by a JSON specification file."""

from __future__ import annotations

import platform
import socket
import sys
from pathlib import Path

import numpy as np

from configuration.sar.processing_config import PathConfig, TomogramConfig
from tools.data.io                       import FileIO
from tools.monitoring.logger             import Logger
from tools.runtime.git_state             import GitState


class GeneratorBase:
    """Generator configured from a JSON specification dict.

    Attributes:
        spec   : Specification dict holding the directories and the tomogram configuration.
        logger : Logger used by the generator.
    """

    def __init__(self, spec: dict, logger: Logger) -> None:
        """Stores the specification and logger.

        Args:
            spec   : Specification dict.
            logger : Logger used by the generator.
        """
        self.spec   = spec
        self.logger = logger

    @classmethod
    def from_spec_file(cls, spec_path: str | Path, logger: Logger) -> "GeneratorBase":
        """Builds the generator from a specification file on disk.

        Args:
            spec_path : Path of the JSON specification file.
            logger    : Logger used by the generator.

        Returns:
            The generator configured from the file's contents.
        """
        return cls(FileIO.load_json(Path(spec_path)), logger)

    def _paths(self) -> PathConfig:
        """Returns the path configuration named by the specification."""
        return PathConfig(
            main_directory   = Path(self.spec["main_directory"]),
            pyrat_directory  = Path(self.spec["pyrat_directory"]),
            run_subdirectory = self.spec["run_subdirectory"],
        )

    def _tomogram_config(self) -> TomogramConfig:
        """Returns the tomogram configuration carried by the specification."""
        return TomogramConfig(**self.spec["tomogram_config"])

    def provenance(self) -> dict:
        """Returns the interpreter, host, library versions and checkout revisions this generator runs with.

        The interpreter path identifies the conda environment, since the
        dispatcher starts the entry with that environment's python directly
        and CONDA_DEFAULT_ENV still names the launching environment.

        Returns:
            Mapping with executable, python, numpy, host, the git_commit of this repository, and pyrat_directory with its pyrat_commit.
        """
        pyrat_directory = Path(self.spec["pyrat_directory"])

        return {
            "executable"      : sys.executable,
            "python"          : platform.python_version(),
            "numpy"           : np.__version__,
            "host"            : socket.gethostname(),
            "git_commit"      : GitState.commit(),
            "pyrat_directory" : str(pyrat_directory),
            "pyrat_commit"    : GitState.commit(pyrat_directory),
        }
