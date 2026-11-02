"""Command-line entry point for the SAR pre-processing stage.

Expands the configured list of speckle-filter windows into one pre-processing
session each, after sizing the crop to the whole scene when every crop field is
zero, building the tomogram and processing configuration per session and
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

    Measures the whole scene first when every crop field is zero, then builds a
    shared crop region and run identifier, derives a dataset name and
    a full ``ProcessingConfig`` for every window in ``win_list``, refuses any
    dataset directory that already holds a finished dataset, and schedules the
    resulting sessions in order. The entry logger is closed with any escaping
    exception, so a failed launch ends logs/pre_process.log with the ABORTED
    banner rather than skipping the END line.
    """
    EnvironmentPinner.threads()

    from pipelines.processing.generation.artifacts import DatasetDirectoryGuard
    from pipelines.processing.generation.pipeline  import PreProcessScheduler, PreProcessSession
    from tools.sar.scene_extent                    import SceneExtentLauncher

    repo_root = pathlib.Path(__file__).resolve().parent.parent.parent
    config    = ConfigCli(PreProcessEntryConfig(), description="SAR pre-processing, runs win filters as sequential sessions").apply()

    with Logger(log_dir=str(repo_root / "logs"), name="pre_process") as logger:
        run_identifier = RunTag.now()

        if config.spans_full_scene:
            logger.section("Scene extent")

            probe_directory = repo_root / "logs" / "scene_extent" / run_identifier
            probe_config    = TomogramConfig(fusar_project_path=config.fusar_project_path, base_directory=config.base_directory, track_selection=config.track_selection, polarisation=config.polarisation)
            probe_spec      = SceneExtentLauncher.build_spec(probe_config, config.stack_identifier, config.pyrat_directory, probe_directory / "scene_extent.json")
            extent          = SceneExtentLauncher(config.tomogram_env_name, logger).measure(probe_spec, probe_directory / "scene_extent_spec.json")

            config.azimuth_end = extent.n_azimuth
            config.range_end   = extent.n_range

            logger.subsection(f"All crop fields are 0, so the whole scene is processed: {extent.n_azimuth} azimuth lines x {extent.n_range} range samples from {extent.slc_path}")

        global_crop = CropRegion(azimuth_start=config.azimuth_start, azimuth_end=config.azimuth_end, range_start=config.range_start, range_end=config.range_end)

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

                paths                = PathConfig(
                    main_directory   = config.main_directory,
                    pyrat_directory  = config.pyrat_directory,
                    run_subdirectory = dataset_name,
                ),
                dataset_type         = config.dataset_type,
                stack_identifier     = config.stack_identifier,
                tomogram_output_tag  = config.tomogram_output_tag,
                parameter_output_tag = config.parameter_output_tag,
                tomogram_env_name    = config.tomogram_env_name,
            )

            DatasetDirectoryGuard(processing_config.paths.run_directory).check(logger)

            sessions.append(PreProcessSession(index=index, total=len(config.win_list), dataset_name=dataset_name, config=processing_config, entry_config=config))

        scheduler = PreProcessScheduler(sessions=sessions, logger=logger)
        scheduler.run()


if __name__ == "__main__":
    main()
