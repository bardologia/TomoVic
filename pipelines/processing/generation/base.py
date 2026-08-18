"""Shared base for the generators driven by a JSON specification file."""

from __future__ import annotations

from pathlib import Path

from configuration.sar.processing_config import PathConfig, TomogramConfig
from tools.data.io                       import FileIO
from tools.monitoring.logger             import Logger


class GeneratorBase:
    """Generator configured from a JSON specification dict.

    Attributes:
        spec: Specification dict holding the directories and the tomogram configuration.
        logger: Logger used by the generator.
    """

    def __init__(self, spec: dict, logger: Logger) -> None:
        """Stores the specification and logger.

        Args:
            spec: Specification dict.
            logger: Logger used by the generator.
        """
        self.spec   = spec
        self.logger = logger

    @classmethod
    def from_spec_file(cls, spec_path: str | Path, logger: Logger) -> "GeneratorBase":
        """Builds the generator from a specification file on disk.

        Args:
            spec_path: Path of the JSON specification file.
            logger: Logger used by the generator.

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
