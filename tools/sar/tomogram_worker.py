"""Worker-process wrapper that runs a PyRat FuSAR tomography job.

The job description is a plain dataclass so it can be pickled into a worker
process, where the PyRat import environment is set up before PyRat is imported.
"""

from __future__ import annotations

import gc
import sys
from dataclasses import dataclass
from typing      import Dict, List, Optional, Tuple

from tools.sar.pyrat_env import PyRatEnvironment


@dataclass
class PyRatJob:
    """Picklable description of one PyRat fusartomo invocation.

    Attributes:
        pyrat_root_path: Directory holding the importable PyRat package.
        crop_tuple: Scene crop as (azimuth_start, azimuth_end, range_start, range_end).
        suffix: Suffix appended to the output product names.
        fusar_project_path: Path of the FuSAR project file.
        stack_identifier: Identifier of the stack inside the project.
        base_directory: Base directory of the input products.
        polarisation: Polarisation channel to process.
        track_selection: PyRat track-selection expression.
        height_range: Inclusive height axis limits in metres, as (min, max).
        filter_method: Name of the covariance filter method.
        filter_arguments: Keyword arguments of the filter method.
        beamforming_method: Name of the beamforming or spectral estimator.
        beamforming_arguments: Positional arguments of the beamforming method.
        output_directory: Directory the tomogram products are written to.
        apply_resampling: Whether PyRat resamples the stack.
        apply_presumming: Whether PyRat presums the stack.
        pyrat_threads: Thread count passed to pyrat_init.
        parent_sys_path: sys.path of the parent process to replay in the worker,
            or None to keep the worker's own path.
    """

    pyrat_root_path       : str
    crop_tuple            : Tuple[int, int, int, int]
    suffix                : str
    fusar_project_path    : str
    stack_identifier      : str
    base_directory        : str
    polarisation          : str
    track_selection       : str
    height_range          : Tuple[float, float]
    filter_method         : str
    filter_arguments      : Dict
    beamforming_method    : str
    beamforming_arguments : List
    output_directory      : str
    apply_resampling      : bool
    apply_presumming      : bool
    pyrat_threads         : int
    parent_sys_path       : Optional[list] = None


class PyRatWorker:
    """Executes a PyRatJob inside the current process.

    Attributes:
        job: Job description to execute.
    """

    def __init__(self, job: PyRatJob) -> None:
        """Stores the job to execute."""
        self.job = job

    def _prepare_environment(self) -> None:
        """Replays the parent sys.path when given and sets up the PyRat import environment."""
        if self.job.parent_sys_path is not None:
            sys.path[:] = self.job.parent_sys_path

        PyRatEnvironment.ensure(self.job.pyrat_root_path)

    def run(self) -> int:
        """Initialises PyRat, runs fusartomo for the job and returns 0 on completion."""
        self._prepare_environment()

        from pyrat import pyrat_init, tomo
        pyrat_init(debug=True, nthreads=self.job.pyrat_threads, silent=True)

        tomo.fusartomo(
            FuSARproject = self.job.fusar_project_path,
            id           = self.job.stack_identifier,
            basedir      = self.job.base_directory,
            polarisation = self.job.polarisation,
            select       = self.job.track_selection,
            presum       = self.job.apply_presumming,
            crop         = self.job.crop_tuple,
            range        = list(self.job.height_range),
            filter       = self.job.filter_method,
            filargs      = self.job.filter_arguments,
            method       = self.job.beamforming_method,
            args         = self.job.beamforming_arguments,
            suffix       = self.job.suffix,
            dir          = self.job.output_directory,
            resampling   = self.job.apply_resampling,
        )

        gc.collect()

        return 0


def run_pyrat_job(job: PyRatJob) -> int:
    """Runs a PyRat job in the calling process, as the process-pool entry point."""
    return PyRatWorker(job).run()
