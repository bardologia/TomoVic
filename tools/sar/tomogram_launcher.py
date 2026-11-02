"""Dispatch of Capon/beamforming tomogram generation into the PyRat conda environment."""

from __future__ import annotations

from dataclasses import asdict
from pathlib     import Path
from typing      import TYPE_CHECKING

from tools.data.io            import FileIO
from tools.sar.stage_launcher import PyRatStageLauncher

if TYPE_CHECKING:
    from configuration.sar.processing_config import ProcessingConfig


class TomogramLauncher(PyRatStageLauncher):
    """Runs tomogram generation as a subprocess in a foreign conda environment.

    Attributes:
        ENTRY    : Repository-relative path of the entry script executed remotely.
        LOG_NAME : Stem of the log file the entry script writes next to the spec.
    """

    ENTRY    = "main/processing/generate_tomogram.py"
    LOG_NAME = "tomogram"

    @staticmethod
    def build_spec(config: "ProcessingConfig", tomogram_path: Path, dem_path: Path, result_path: Path) -> dict:
        """Builds the JSON-serialisable job specification for the entry script.

        Args:
            config        : Processing configuration supplying the stack identity, paths, parallelism and crop.
            tomogram_path : Output path of the generated tomogram.
            dem_path      : Output path of the DEM produced alongside the tomogram.
            result_path   : Path the entry script writes its result JSON to, carrying the content audit of the merged cube.

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
            "result_path"      : str(result_path),
        }

    def generate(self, spec: dict, spec_path: Path) -> dict:
        """Runs the entry script on a specification and returns its result payload.

        Args:
            spec      : Specification produced by build_spec.
            spec_path : Path the specification is written to for the subprocess.

        Returns:
            Result JSON written by the entry script at spec["result_path"].
        """
        self._dispatch(spec, spec_path)
        return FileIO.load_json(Path(spec["result_path"]))
