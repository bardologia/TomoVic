"""Measures the full scene extent of an F-SAR project inside the PyRat environment.

PyRat's ``FuSARtomo`` reads the project file and names the primary pass; the
primary's RGI-SLC header then gives the azimuth and range size, which is written
to the result path of the specification.
"""

from __future__ import annotations

from dataclasses import asdict
from pathlib     import Path

from pipelines.processing.generation.base import GeneratorBase
from tools.data.io                        import FileIO
from tools.sar.pyrat_env                  import PyRatEnvironment
from tools.sar.scene_extent               import SceneExtent


class SceneExtentGenerator(GeneratorBase):
    """Measures the primary SLC size of the stack named by a JSON specification."""

    def _primary_pass(self) -> str:
        """Returns the pass directory PyRat selects as the primary of the project.

        Returns:
            Directory of the primary acquisition.
        """
        PyRatEnvironment.ensure_root_on_sys_path(self.spec["pyrat_directory"])

        from pyrat import pyrat_init, tomo

        pyrat_init(debug=False, nthreads=1)
        tomogram_config = self._tomogram_config()

        stack = tomo.FuSARtomo(
            FuSARproject = tomogram_config.fusar_project_path,
            select       = tomogram_config.track_selection,
            id           = self.spec["stack_identifier"],
            basedir      = tomogram_config.base_directory,
            polarisation = tomogram_config.polarisation,
        )

        self.logger.subsection(f"[FSAR] Master: {stack.master}")
        return stack.master

    def run(self) -> SceneExtent:
        """Measures the scene extent and writes it to the specification's result path.

        Returns:
            The azimuth and range size of the primary SLC.
        """
        self.logger.section("[Scene extent]")

        primary = self._primary_pass()
        extent  = SceneExtent.from_slc(primary, self._tomogram_config().polarisation)

        self.logger.kv_table({
            "Primary SLC"   : extent.slc_path,
            "Azimuth lines" : extent.n_azimuth,
            "Range samples" : extent.n_range,
        }, title="Scene extent")

        FileIO.save_json(asdict(extent), Path(self.spec["result_path"]))
        return extent
