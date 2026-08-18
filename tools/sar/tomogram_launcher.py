"""Dispatch of Capon/beamforming tomogram generation into the PyRat conda environment."""

from __future__ import annotations

from dataclasses import asdict
from pathlib     import Path
from typing      import Optional, Tuple, TYPE_CHECKING

from tools.runtime.conda_env import CondaJobDispatcher
from tools.monitoring.logger import Logger

if TYPE_CHECKING:
    from configuration.sar.processing_config import ProcessingConfig


class TomogramLauncher:
    """Runs tomogram generation as a subprocess in a foreign conda environment.

    Attributes:
        logger: Logger the dispatcher writes progress to.
        dispatcher: Conda job dispatcher that runs the entry script.
        ENTRY: Repository-relative path of the entry script executed remotely.
    """

    ENTRY = "main/processing/generate_tomogram.py"

    def __init__(self, env_name: str, logger: Logger, repo_root: Optional[Path] = None) -> None:
        """Builds the launcher around a conda environment.

        Args:
            env_name: Name of the conda environment holding PyRat.
            logger: Logger for dispatch output.
            repo_root: Repository root passed to the dispatcher, or None to let
                the dispatcher resolve it.
        """
        self.logger     = logger
        self.dispatcher = CondaJobDispatcher(env_name, logger, repo_root)

    @staticmethod
    def build_spec(config: "ProcessingConfig", tomogram_path: Path, dem_path: Path) -> dict:
        """Builds the JSON-serialisable job specification for the entry script.

        Args:
            config: Processing configuration supplying the stack identity,
                paths, parallelism and crop.
            tomogram_path: Output path of the generated tomogram.
            dem_path: Output path of the DEM produced alongside the tomogram.

        Returns:
            Specification dictionary consumed by the entry script.
        """
        return {
            "tomogram_config"  : asdict(config.tomogram_config),
            "stack_identifier" : config.stack_identifier,
            "dataset_type"     : config.dataset_type,
            "pyrat_directory"  : str(config.paths.pyrat_directory),
            "main_directory"   : str(config.paths.main_directory),
            "run_subdirectory" : config.paths.run_subdirectory,
            "effort"           : config.parallel.effort,
            "tomogram_workers" : config.parallel.tomogram_workers,
            "pyrat_threads"    : config.parallel.pyrat_threads,
            "crop"             : list(config.crop.as_tuple()),
            "tomogram_path"    : str(tomogram_path),
            "dem_path"         : str(dem_path),
        }

    def generate(self, spec: dict, spec_path: Path) -> Tuple[Path, Path]:
        """Runs the entry script on a specification and returns the written product paths.

        Args:
            spec: Specification produced by build_spec.
            spec_path: Path the specification is written to for the subprocess.

        Returns:
            Tuple of the tomogram path and the DEM path.
        """
        self.dispatcher.dispatch(self.ENTRY, spec, spec_path)
        return Path(spec["tomogram_path"]), Path(spec["dem_path"])
