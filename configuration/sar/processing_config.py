"""Configuration for the SAR preprocessing that produces a tomogram dataset.

Covers the PyRAT beamforming settings, the CPU parallelism plan shared between
tomogram workers and PyRAT threads, the on-disk run layout, and the entry-point
config that turns a crop and a window list into named dataset runs.
"""

from __future__ import annotations

import math
import os
from dataclasses import dataclass, field
from pathlib     import Path
from typing      import ClassVar, Dict, List, Optional, Tuple

from tools.runtime.run_tag import RunTag
from tools.data.regions    import CropRegion


@dataclass
class TomogramConfig:
    """PyRAT beamforming settings producing the tomographic cube.

    Attributes:
        fusar_project_path: F-SAR project CSV describing the available passes.
        base_directory: Root under which the raw campaign data lives.
        polarisation: Polarimetric channel processed, e.g. "hv".
        track_selection: Glob selecting which tracks enter the stack.
        height_range: Elevation axis extent of the tomogram in metres.
        filter_method: Covariance estimation filter, e.g. "Boxcar".
        filter_arguments: Keyword arguments of that filter; "win" is the per-axis window in (azimuth, range) pixels.
        beamforming_method: Spectral estimator inverting the stack, e.g. "Capon".
        beamforming_arguments: Positional arguments of the beamformer.
        max_crop_azimuth_width: Azimuth width in pixels of each processed subsection.
        apply_resampling: Whether the stack is resampled before beamforming.
        apply_presumming: Whether the stack is presummed before beamforming.
        max_amplitude_clip: Multiple of the mean amplitude at which the tomogram is clipped.
    """

    fusar_project_path     : str                 = ""
    base_directory         : str                 = "/ste/rnd/"
    polarisation           : str                 = "hv"
    track_selection        : str                 = "*"
    height_range           : Tuple[float, float] = (-20.0, 80.0)
    filter_method          : str                 = "Boxcar"
    filter_arguments       : Dict                = field(default_factory=lambda: {"win": [20, 10]})
    beamforming_method     : str                 = "Capon"
    beamforming_arguments  : List                = field(default_factory=list)
    max_crop_azimuth_width : int                 = 1000
    apply_resampling       : bool                = False
    apply_presumming       : bool                = False
    max_amplitude_clip     : float               = 1.25


@dataclass
class ParallelConfig:
    """CPU budget split between tomogram worker processes and PyRAT threads.

    Attributes:
        effort: Fraction of the machine claimed, one of "low", "medium" or "high".
        tomogram_workers: Fixed worker count, or None to solve for one.
        pyrat_threads: Fixed thread count per worker, or None to solve for one.
        EFFORT_FRACTIONS: Core fraction claimed by each effort level.
        THREAD_CAP: Largest thread count a solved plan assigns to one worker.
    """

    effort           : str           = "high"
    tomogram_workers : Optional[int] = None
    pyrat_threads    : Optional[int] = None

    EFFORT_FRACTIONS : ClassVar[Dict[str, float]] = {"low": 0.25, "medium": 0.5, "high": 0.8}
    THREAD_CAP       : ClassVar[int]              = 16

    @staticmethod
    def available_cores() -> int:
        """Returns the number of CPU cores this process may run on."""
        try:
            return len(os.sched_getaffinity(0))
        except AttributeError:
            return os.cpu_count() or 1

    def core_budget(self) -> int:
        """Returns the core count claimed at the configured effort level.

        Raises:
            ValueError: If the effort level is unknown.
        """
        if self.effort not in self.EFFORT_FRACTIONS:
            raise ValueError(f"Unknown effort '{self.effort}', expected one of {sorted(self.EFFORT_FRACTIONS)}")
        return max(1, int(self.available_cores() * self.EFFORT_FRACTIONS[self.effort]))

    def interferogram_threads(self) -> int:
        """Returns the thread count for interferogram generation, which runs unsharded."""
        if self.pyrat_threads is not None:
            return max(1, self.pyrat_threads)
        return self.core_budget()

    def resolve_plan(self, subsection_count: int) -> Tuple[int, int]:
        """Solves for the worker and thread counts processing the subsections.

        Any count the user fixed is respected and the other is derived from the
        core budget. When neither is fixed the plan minimising the number of
        sequential waves wins, breaking ties toward more threads per worker.

        Args:
            subsection_count: Number of azimuth subsections to process.

        Returns:
            The number of concurrent tomogram workers and the PyRAT threads each gets.

        Raises:
            ValueError: If the subsection count is below one.
        """
        if subsection_count < 1:
            raise ValueError(f"resolve_plan needs at least one subsection, got {subsection_count}")

        budget = self.core_budget()

        if self.tomogram_workers is not None and self.pyrat_threads is not None:
            return max(1, min(subsection_count, self.tomogram_workers)), max(1, self.pyrat_threads)

        if self.tomogram_workers is not None:
            workers = max(1, min(subsection_count, self.tomogram_workers))
            return workers, max(1, min(self.THREAD_CAP, budget // workers))

        if self.pyrat_threads is not None:
            threads = max(1, self.pyrat_threads)
            return max(1, min(subsection_count, budget // threads)), threads

        best_plan  = None
        best_waves = None

        for workers in range(1, min(subsection_count, budget) + 1):
            threads = max(1, min(self.THREAD_CAP, budget // workers))
            waves   = math.ceil(subsection_count / workers)

            if best_plan is None or waves < best_waves or (waves == best_waves and threads > best_plan[1]):
                best_plan, best_waves = (workers, threads), waves

        return best_plan


@dataclass
class PathConfig:
    """On-disk layout of a preprocessing run.

    Attributes:
        main_directory: Root holding all dataset runs.
        pyrat_directory: PyRAT source directory used by the workers.
        data_subdirectory: Subdirectory receiving the processed arrays.
        metadata_subdirectory: Subdirectory receiving the run metadata.
        temporary_subdirectory: Subdirectory receiving intermediate products.
        run_subdirectory: Name of this run's directory, filled in when absent.
    """

    main_directory         : Path          = field(default_factory=lambda: Path("/ste/rnd/User/vice_vi/Dataset"))
    pyrat_directory        : Path          = field(default_factory=lambda: Path("/ste/rnd/User/vice_vi/pyrat"))
    data_subdirectory      : str           = "data"
    metadata_subdirectory  : str           = "meta"
    temporary_subdirectory : str           = "tmp"
    run_subdirectory       : Optional[str] = None

    @property
    def run_directory(self) -> Path:
        """Directory of this run, or the main directory when no run name is set."""
        if self.run_subdirectory is None:
            return self.main_directory
        return self.main_directory / self.run_subdirectory

    @property
    def data_directory(self) -> Path:
        """Directory receiving the processed arrays of this run."""
        return self.run_directory / self.data_subdirectory

    @property
    def metadata_directory(self) -> Path:
        """Directory receiving the metadata of this run."""
        return self.run_directory / self.metadata_subdirectory

    @property
    def temporary_directory(self) -> Path:
        """Directory receiving the intermediate products of this run."""
        return self.run_directory / self.temporary_subdirectory


@dataclass
class ProcessingConfig:
    """Resolved settings of one preprocessing run over a scene crop.

    Attributes:
        crop: Azimuth and range extent of the scene being processed.
        tomogram_config: PyRAT beamforming settings.
        parallel: CPU budget split between workers and threads.
        paths: On-disk layout of the run.
        dataset_type: Sensor family of the source data, e.g. "FSAR".
        stack_identifier: Identifier distinguishing stacks of the same crop.
        tomogram_output_tag: PyRAT output tag of the tomogram product.
        parameter_output_tag: PyRAT output tag of the parameter product.
        tomogram_env_name: Conda environment providing PyRAT to the workers.
    """

    crop            : CropRegion
    tomogram_config : TomogramConfig = field(default_factory=TomogramConfig)
    parallel        : ParallelConfig = field(default_factory=ParallelConfig)
    paths           : PathConfig     = field(default_factory=PathConfig)

    dataset_type         : str = "FSAR"
    stack_identifier     : str = "1"
    tomogram_output_tag  : str = "Xtomo_id2X"
    parameter_output_tag : str = "Xparams_id2X"
    tomogram_env_name    : str = "stetools"

    @property
    def tomogram_tag(self) -> str:
        """PyRAT output tag identifying the tomogram of this crop and stack."""
        return f"{self.crop.as_identifier_string()}_{self.stack_identifier}_{self.tomogram_output_tag}"

    @property
    def parameter_tag(self) -> str:
        """PyRAT output tag identifying the parameters of this crop and stack."""
        return f"{self.crop.as_identifier_string()}_{self.stack_identifier}_{self.parameter_output_tag}"

    def __post_init__(self) -> None:
        """Names the run subdirectory from the tomogram tag and current timestamp."""
        if self.paths.run_subdirectory is None:
            timestamp = RunTag.now()
            self.paths.run_subdirectory = f"run_{self.tomogram_tag}_{timestamp}"

@dataclass
class PreProcessEntryConfig:
    """Entry-point settings turning a crop and a window list into dataset runs.

    One run is produced per multilook window in `win_list`.

    Attributes:
        azimuth_start: First azimuth line of the crop.
        azimuth_end: Last azimuth line of the crop.
        range_start: First range sample of the crop.
        range_end: Last range sample of the crop.
        fusar_project_path: F-SAR project CSV describing the available passes.
        base_directory: Root under which the raw campaign data lives.
        track_selection: Glob selecting which tracks enter the stack.
        polarisation: Polarimetric channel processed, e.g. "hv".
        beamforming_method: Spectral estimator inverting the stack.
        filter_method: Covariance estimation filter.
        height_range: Elevation axis extent of the tomogram in metres.
        win_list: Multilook windows swept, each as (azimuth, range) pixels.
        max_crop_azimuth_width: Azimuth width in pixels of each processed subsection.
        apply_resampling: Whether the stack is resampled before beamforming.
        apply_presumming: Whether the stack is presummed before beamforming.
        max_amplitude_clip: Multiple of the mean amplitude at which the tomogram is clipped.
        effort: Fraction of the machine claimed by the parallel plan.
        tomogram_workers: Fixed worker count, or None to solve for one.
        pyrat_threads: Fixed thread count per worker, or None to solve for one.
        dataset_name: Explicit dataset name, or None to derive one from the crop.
        dataset_type: Sensor family of the source data.
        stack_identifier: Identifier distinguishing stacks of the same crop.
        tomogram_output_tag: PyRAT output tag of the tomogram product.
        parameter_output_tag: PyRAT output tag of the parameter product.
        tomogram_env_name: Conda environment providing PyRAT to the workers.
    """

    azimuth_start : int = 1000
    azimuth_end   : int = 16000
    range_start   : int = 500
    range_end     : int = 4000

    fusar_project_path : str = "/ste/rnd/User/sera_se/17sartom-traun_L.csv"
    base_directory     : str = "/ste/rnd/"
    track_selection    : str = "*"
    polarisation       : str = "hv"

    beamforming_method : str   = "Capon"
    filter_method      : str   = "Boxcar"
    height_range       : tuple = (-20.0, 80.0)
    win_list           : list  = field(default_factory=lambda: [[20, 10]])

    max_crop_azimuth_width : int   = 1000
    apply_resampling       : bool  = False
    apply_presumming       : bool  = False
    max_amplitude_clip     : float = 1.25

    effort           : str           = "high"
    tomogram_workers : Optional[int] = None
    pyrat_threads    : Optional[int] = None

    dataset_name         : Optional[str] = None
    dataset_type         : str           = "FSAR"
    stack_identifier     : str           = "1"
    tomogram_output_tag  : str           = "Xtomo_id2X"
    parameter_output_tag : str           = "Xparams_id2X"
    tomogram_env_name    : str           = "stetools"

    def resolve_dataset_name(self, win: List[int], run_identifier: str) -> str:
        """Builds the dataset directory name for one multilook window.

        An explicit name is used as given, suffixed with the window only when
        several windows are swept; otherwise the name is derived from the
        project file, the crop, the window, the polarisation and the stack.

        Args:
            win: Multilook window as (azimuth, range) pixels.
            run_identifier: Timestamp or tag disambiguating repeated runs.

        Returns:
            The dataset directory name for this window.
        """
        win_string = "_".join(str(value) for value in win)

        if self.dataset_name:
            return self.dataset_name if len(self.win_list) == 1 else f"{self.dataset_name}_w{win_string}"

        crop   = CropRegion(azimuth_start=self.azimuth_start, azimuth_end=self.azimuth_end, range_start=self.range_start, range_end=self.range_end)
        source = Path(self.fusar_project_path).stem

        return f"{source}_{crop.as_labeled_string()}_w{win_string}_{self.polarisation}_{self.stack_identifier}_{run_identifier}"


@dataclass
class PreprocessInferenceConfig:
    """Settings for the analysis pass over already-preprocessed dataset runs.

    Attributes:
        runs_dir: Root directory holding the dataset runs.
        run_tags: Run directory names to analyse; empty selects all.
    """

    runs_dir : Path = Path("/ste/rnd/User/vice_vi/Dataset")
    run_tags : list = field(default_factory=list)
