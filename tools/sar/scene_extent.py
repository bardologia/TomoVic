"""Measurement of the full scene extent of an F-SAR stack.

Resolves the primary pass's RGI-SLC product, reads its RAT header into an
azimuth and range size, and dispatches that measurement into the PyRat conda
environment, where the F-SAR project file names the primary pass.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib     import Path
from typing      import TYPE_CHECKING

from tools.baselines.reading  import PassProductResolver
from tools.data.io            import FileIO
from tools.data.rat           import RatHeaderReader
from tools.data.regions       import CropRegion
from tools.sar.stage_launcher import PyRatStageLauncher

if TYPE_CHECKING:
    from configuration.sar.processing_config import TomogramConfig


class PrimarySlcResolver(PassProductResolver):
    """Resolves the RGI-SLC product of a pass directory."""
    PRODUCT_SUBDIR   = Path("RGI") / "RGI-SR"
    PRODUCT_PATTERNS = ("slc_*.rat",)


@dataclass
class SceneExtent:
    """Azimuth and range size of the primary SLC of a stack.

    Attributes:
        n_azimuth : Number of azimuth lines of the primary SLC.
        n_range   : Number of range samples of the primary SLC.
        primary   : Pass directory of the primary acquisition.
        slc_path  : RGI-SLC file whose header gave the size.
    """

    n_azimuth : int
    n_range   : int
    primary   : str
    slc_path  : str

    @classmethod
    def from_slc(cls, primary: str | Path, polarisation: str) -> "SceneExtent":
        """Measures the extent from the RAT header of a pass's RGI-SLC product.

        Args:
            primary      : Pass directory of the primary acquisition.
            polarisation : Two-letter polarisation code selecting the SLC.

        Returns:
            The azimuth and range size of the SLC.

        Raises:
            ValueError : If the SLC is not a two-dimensional (azimuth, range) array.
        """
        slc_path = PrimarySlcResolver().resolve(primary, polarisation)
        shape    = RatHeaderReader(slc_path).read().shape

        if len(shape) != 2:
            raise ValueError(f"Primary SLC {slc_path} has shape {shape}, expected two axes (azimuth, range)")

        return cls(n_azimuth=shape[0], n_range=shape[1], primary=str(primary), slc_path=str(slc_path))

    def as_crop(self) -> CropRegion:
        """Returns the crop covering the whole scene."""
        return CropRegion(azimuth_start=0, azimuth_end=self.n_azimuth, range_start=0, range_end=self.n_range)


class SceneExtentLauncher(PyRatStageLauncher):
    """Runs the scene extent measurement as a subprocess in the PyRat conda environment.

    Attributes:
        ENTRY    : Repository-relative path of the entry script executed remotely.
        LOG_NAME : Stem of the log file the entry script writes next to the spec.
    """

    ENTRY    = "main/processing/measure_scene_extent.py"
    LOG_NAME = "scene_extent"

    @staticmethod
    def build_spec(tomogram_config: "TomogramConfig", stack_identifier: str, pyrat_directory: Path, result_path: Path) -> dict:
        """Builds the JSON-serialisable job specification for the entry script.

        Args:
            tomogram_config  : Tomogram configuration naming the project, base directory, track selection and polarisation.
            stack_identifier : ID column of the F-SAR project row that selects the stack.
            pyrat_directory  : PyRat source directory put on the import path.
            result_path      : Path the entry script writes the measured extent to.

        Returns:
            Specification dictionary consumed by the entry script.
        """
        return {
            "tomogram_config"  : asdict(tomogram_config),
            "stack_identifier" : stack_identifier,
            "pyrat_directory"  : str(pyrat_directory),
            "result_path"      : str(result_path),
        }

    def measure(self, spec: dict, spec_path: Path) -> SceneExtent:
        """Runs the entry script on a specification and returns the measured extent.

        Args:
            spec      : Specification produced by build_spec.
            spec_path : Path the specification is written to for the subprocess.

        Returns:
            The azimuth and range size of the primary SLC.
        """
        self._dispatch(spec, spec_path)
        return SceneExtent(**FileIO.load_json(Path(spec["result_path"])))
