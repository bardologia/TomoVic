"""Dispatch of the polarimetric primary extraction into the PyRat conda environment."""

from __future__ import annotations

from pathlib import Path

from tools.data.io            import FileIO
from tools.sar.stage_launcher import PyRatStageLauncher


class PolarimetricLauncher(PyRatStageLauncher):
    """Runs the polarimetric primary extraction as a subprocess in a foreign conda environment.

    Attributes:
        ENTRY    : Repository-relative path of the entry script executed remotely.
        LOG_NAME : Stem of the log file the entry script writes next to the spec.
    """

    ENTRY    = "main/processing/generate_polarimetric_primary.py"
    LOG_NAME = "polarimetric_primary"

    @staticmethod
    def build_spec(
        tomogram_config  : dict,
        stack_identifier : str,
        crop             : tuple,
        pyrat_directory  : Path,
        pyrat_threads    : int,
        window           : tuple,
        primary_path     : Path,
        artifact_path    : Path,
        sidecar_path     : Path,
        result_path      : Path,
    ) -> dict:
        """Builds the JSON-serialisable job specification for the entry script.

        Args:
            tomogram_config  : Tomogram configuration of the dataset as recorded in its config state.
            stack_identifier : ID column of the F-SAR project row selecting the stack.
            crop             : Crop as (azimuth_start, azimuth_end, range_start, range_end) in pixels.
            pyrat_directory  : PyRat source directory put on the import path.
            pyrat_threads    : Thread count PyRat uses inside the worker.
            window           : Covariance window of the tomogram as (azimuth, range) pixels, stored as the default multilook of the Pauli view.
            primary_path     : Path of the dataset's single-polarisation primary the extraction is checked against.
            artifact_path    : Output path of the polarimetric primary array.
            sidecar_path     : Output path of the provenance sidecar.
            result_path      : Path the entry script writes its result JSON to.

        Returns:
            Specification dictionary consumed by the entry script.
        """
        return {
            "tomogram_config"  : dict(tomogram_config),
            "stack_identifier" : str(stack_identifier),
            "crop"             : [int(value) for value in crop],
            "pyrat_directory"  : str(pyrat_directory),
            "pyrat_threads"    : int(pyrat_threads),
            "window"           : [int(value) for value in window],
            "primary_path"     : str(primary_path),
            "artifact_path"    : str(artifact_path),
            "sidecar_path"     : str(sidecar_path),
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
