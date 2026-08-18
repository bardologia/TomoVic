"""Command-line entry point for the SAR pre-processing stage.

Expands the configured list of speckle-filter windows into one pre-processing
session each, building the tomogram and processing configuration per session and
handing the whole queue to ``PreProcessScheduler``, which runs the sessions
sequentially.
"""

from __future__ import annotations

import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from _bootstrap import EnvironmentPinner

from tools.runtime.run_tag import RunTag

from configuration.sar.processing_config import (
    CropRegion,
    ParallelConfig,
    PathConfig,
    PreProcessEntryConfig,
    ProcessingConfig,
    TomogramConfig,
)
from tools.runtime.config_cli import ConfigCli
from tools.monitoring.logger  import Logger


def main() -> None:
    """Runs one pre-processing session per configured filter window.

    Builds a shared crop region and run identifier, derives a dataset name and
    a full ``ProcessingConfig`` for every window in ``win_list``, and schedules
    the resulting sessions in order.
    """
    EnvironmentPinner.threads()

    from pipelines.processing.generation.pipeline import PreProcessScheduler, PreProcessSession

    config = ConfigCli(PreProcessEntryConfig(), description="SAR pre-processing, runs win filters as sequential sessions").apply()
    logger = Logger(log_dir="logs", name="pre_process")

    global_crop    = CropRegion(azimuth_start=config.azimuth_start, azimuth_end=config.azimuth_end, range_start=config.range_start, range_end=config.range_end)
    run_identifier = RunTag.now()

    logger.section("Pre-processing queue")
    logger.kv_table({
        "Win filters"  : ", ".join(str(win) for win in config.win_list),
        "Runs"         : len(config.win_list),
        "Crop"         : global_crop.as_tuple(),
    }, title="Configuration")

    sessions = []

    for index, win in enumerate(config.win_list):
        filter_arguments = {"win": list(win)}
        dataset_name     = config.resolve_dataset_name(win, run_identifier)

        logger.subsection(f"[Session {index + 1}/{len(config.win_list)}] {dataset_name} queued with filter arguments {filter_arguments}")

        tomogram_config = TomogramConfig(
            fusar_project_path     = config.fusar_project_path,
            base_directory         = config.base_directory,
            track_selection        = config.track_selection,
            polarisation           = config.polarisation,
            beamforming_method     = config.beamforming_method,
            filter_method          = config.filter_method,
            filter_arguments       = filter_arguments,
            height_range           = tuple(config.height_range),
            max_crop_azimuth_width = config.max_crop_azimuth_width,
            apply_resampling       = config.apply_resampling,
            apply_presumming       = config.apply_presumming,
            max_amplitude_clip     = config.max_amplitude_clip,
        )

        processing_config = ProcessingConfig(
            crop            = global_crop,
            tomogram_config = tomogram_config,

            parallel = ParallelConfig(effort=config.effort, tomogram_workers=config.tomogram_workers, pyrat_threads=config.pyrat_threads),

            paths                = PathConfig(run_subdirectory=dataset_name),
            dataset_type         = config.dataset_type,
            stack_identifier     = config.stack_identifier,
            tomogram_output_tag  = config.tomogram_output_tag,
            parameter_output_tag = config.parameter_output_tag,
            tomogram_env_name    = config.tomogram_env_name,
        )

        sessions.append(PreProcessSession(index=index, total=len(config.win_list), dataset_name=dataset_name, config=processing_config))

    scheduler = PreProcessScheduler(sessions=sessions, logger=logger)
    scheduler.run()

    logger.close()


if __name__ == "__main__":
    main()
