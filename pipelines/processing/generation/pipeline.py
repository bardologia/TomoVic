"""Orchestrates preprocessing: tomogram generation, stack building and geometry field.

The pipeline dispatches the PyRat-bound tomogram and interferogram stages into their own
environment, derives the per-pixel geometry field used by the physics loss, and records
the dataset layout that downstream stages read.
"""

from __future__ import annotations

import gc
from pathlib import Path
from typing  import Tuple

from configuration.sar.processing_config       import ProcessingConfig
from pipelines.processing.generation.artifacts import ArtifactRegistry, MetadataManager
from pipelines.shared.orchestration.session_scheduler import SequentialSessionScheduler
from tools.data.io                             import FileIO
from tools.monitoring.logger                   import Logger
from tools.sar                                 import GeometryField, GeometryFieldBuilder, InterferogramLauncher, TomogramLauncher, TrackParameters
from tools.baselines                           import TrackBaselines, TrackProfiles


class ProcessingPipeline:
    """Produces the full preprocessed dataset for one SAR stack.

    Attributes:
        config: Processing configuration naming the crop, paths and PyRat environment.
        logger: Logger for the stage report.
        artifact_registry: Resolver mapping artifact names to on-disk paths.
        metadata_manager: Writer of the per-stage metadata and the dataset layout.
        tomogram_launcher: Launcher for the tomogram stage in the PyRat environment.
        interferogram_launcher: Launcher for the interferogram stage in the PyRat environment.
    """

    def __init__(self, config: ProcessingConfig, logger: Logger) -> None:
        """Wires the artifact registry, metadata manager and stage launchers.

        Args:
            config: Processing configuration for this stack.
            logger: Logger for initialization and stage output.
        """
        self.config = config
        self.logger = logger

        self.artifact_registry      = ArtifactRegistry   (config, logger=self.logger)
        self.metadata_manager       = MetadataManager    (config, logger=self.logger)
        self.tomogram_launcher      = TomogramLauncher    (config.tomogram_env_name, logger=self.logger)
        self.interferogram_launcher = InterferogramLauncher(config.tomogram_env_name, logger=self.logger)

        self._pass_labels : list | None = None

        self.logger.section("[Pre-Processing Pipeline Initialized]")
        self.logger.subsection(f"Stack ID         : {config.stack_identifier}")
        self.logger.subsection(f"Tomogram Env     : {config.tomogram_env_name}")

    def _stage_tomogram(self) -> Tuple[Path, Path]:
        """Generates the full-stack tomogram and DEM in the PyRat environment.

        Returns:
            Tuple of the tomogram .npy path and the DEM .npy path.
        """
        tomogram_path = self.artifact_registry.artifact_path("tomogram_full")
        dem_path      = self.artifact_registry.artifact_path("dem_full")

        self.logger.subsection(f"[Active] Generating full-stack tomogram in env '{self.config.tomogram_env_name}'")
        spec      = self.tomogram_launcher.build_spec(self.config, tomogram_path, dem_path)
        spec_path = self.config.paths.metadata_directory / "tomogram_spec.json"
        self.tomogram_launcher.generate(spec, spec_path)

        self.metadata_manager.save_stage_metadata(
            stage_name       = "tomogram_full",
            metadata_entries = self.metadata_manager.build_tomogram_metadata(tomogram_path, self.config.stack_identifier, self.config.tomogram_config),
        )

        gc.collect()

        return tomogram_path, dem_path

    def _stage_inputs(self) -> Tuple[Path, Path, Path]:
        """Builds the interferometric stack and records its shapes and pass labels.

        Returns:
            Tuple of the primary, secondaries and interferograms .npy paths.
        """
        primary_path        = self.artifact_registry.artifact_path("primary")
        secondaries_path    = self.artifact_registry.artifact_path("secondaries")
        interferograms_path = self.artifact_registry.artifact_path("interferograms")
        profiles_path       = self.artifact_registry.artifact_path("track_profiles")
        baselines_path      = self.config.paths.metadata_directory / TrackBaselines.FILENAME
        parameters_path     = self.config.paths.metadata_directory / TrackParameters.FILENAME
        result_path         = self.config.paths.metadata_directory / "interferogram_result.json"

        self.logger.subsection(f"[Active] Building interferometric stack in env '{self.config.tomogram_env_name}'")
        spec = self.interferogram_launcher.build_spec(
            self.config,
            primary_path        = primary_path,
            secondaries_path    = secondaries_path,
            interferograms_path = interferograms_path,
            baselines_path      = baselines_path,
            profiles_path       = profiles_path,
            parameters_path     = parameters_path,
            result_path         = result_path,
        )
        spec_path = self.config.paths.metadata_directory / "interferogram_spec.json"
        result    = self.interferogram_launcher.generate(spec, spec_path)

        primary_shape        = tuple(result["primary_shape"])
        secondaries_shape    = tuple(result["secondaries_shape"])
        interferograms_shape = tuple(result["interferograms_shape"])

        self.metadata_manager.save_stage_metadata(
            stage_name       = "inputs",
            metadata_entries = self.metadata_manager.build_inputs_metadata(primary_path, secondaries_path, interferograms_path, primary_shape, secondaries_shape, interferograms_shape),
        )

        self._pass_labels = result["pass_labels"]

        gc.collect()

        return primary_path, secondaries_path, interferograms_path

    def _stage_geometry_field(self) -> Path:
        """Builds the per-pixel geometry field (kz in rad/m and look geometry) and saves it.

        Returns:
            Path of the saved geometry field file.
        """
        parameters_path = self.config.paths.metadata_directory / TrackParameters.FILENAME
        profiles_path   = self.artifact_registry.artifact_path("track_profiles")
        out_path        = self.config.paths.metadata_directory / GeometryField.FILENAME

        self.logger.subsection("[Active] Building per-pixel geometry field for the physics loss")
        parameters = TrackParameters.load(parameters_path)
        profiles   = TrackProfiles.load(profiles_path)
        field      = GeometryFieldBuilder(parameters, profiles, self.config.crop).build()

        field.save(out_path)
        self.logger.kv_table({name: str(value) for name, value in field.describe().items()}, title="Geometry Field")

        gc.collect()

        return out_path

    def run(self) -> dict[str, Path]:
        """Runs every preprocessing stage and writes the dataset layout.

        Returns:
            Mapping from artifact name to its saved path, plus the run directory.
        """
        self.logger.section("[Pre-Processing Pipeline Execution]")

        self.metadata_manager.save_pipeline_configuration()

        full_tomo_path, full_dem_path = self._stage_tomogram()

        primary_path, secondaries_path, interferograms_path = self._stage_inputs()

        geometry_field_path = self._stage_geometry_field()

        self.metadata_manager.save_dataset_layout(pass_labels=self._pass_labels)

        self.logger.section("[Pre-Processing Execution Completed]")

        return {
            "tomogram_full"  : full_tomo_path,
            "dem_full"       : full_dem_path,
            "primary"        : primary_path,
            "secondaries"    : secondaries_path,
            "interferograms" : interferograms_path,
            "geometry_field" : geometry_field_path,
            "run_directory"  : self.config.paths.run_directory,
        }


class PreProcessSession:
    """One schedulable preprocessing run for a single dataset.

    Attributes:
        index: Zero-based position of this session in the scheduled batch.
        total: Number of sessions in the batch.
        dataset_name: Name identifying the dataset being preprocessed.
        config: Processing configuration for this dataset.
    """

    def __init__(self, index: int, total: int, dataset_name: str, config: ProcessingConfig) -> None:
        """Binds the session to a dataset configuration and its batch position.

        Args:
            index: Zero-based position in the scheduled batch.
            total: Number of sessions in the batch.
            dataset_name: Name identifying the dataset.
            config: Processing configuration for this dataset.
        """
        self.index        = index
        self.total        = total
        self.dataset_name = dataset_name
        self.config       = config

    def execute(self) -> dict[str, Path]:
        """Creates the run logger and runs the processing pipeline.

        Returns:
            The artifact mapping returned by ``ProcessingPipeline.run``.
        """
        run_dir = Path(self.config.paths.run_directory)
        log_dir = run_dir / "logs"

        FileIO.ensure_dirs(run_dir, log_dir)

        logger = Logger(log_dir=str(log_dir), name="preprocessing", level="INFO")

        return ProcessingPipeline(self.config, logger=logger).run()


def run_preprocess_session(session: PreProcessSession) -> dict[str, Path]:
    """Module-level entry point so a session can be dispatched by a scheduler."""
    return session.execute()


class PreProcessScheduler(SequentialSessionScheduler):
    """Runs the given preprocessing sessions one after another.

    Attributes:
        sessions: Preprocessing sessions to execute, in order.
    """

    def __init__(self, sessions: list[PreProcessSession], logger: Logger) -> None:
        """Binds the scheduler to a fixed list of preprocessing sessions.

        Args:
            sessions: Sessions to execute, in order.
            logger: Logger shared with the base scheduler.
        """
        super().__init__(logger)
        self.sessions = sessions

    def _sessions(self) -> list[PreProcessSession]:
        """Returns the configured sessions."""
        return self.sessions

    def _session_runner(self):
        """Returns the callable that executes one session."""
        return run_preprocess_session

    def _result_key(self, session) -> str:
        """Returns the dataset name used to key this session's results."""
        return session.dataset_name

    def _completion_message(self, session) -> str:
        """Returns the log line announcing that a session finished."""
        return f"[Session {session.index + 1}/{session.total}] {session.dataset_name} completed"



