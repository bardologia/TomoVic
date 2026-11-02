"""Orchestrates preprocessing: tomogram generation, stack building and geometry field.

The pipeline dispatches the PyRat-bound tomogram and interferogram stages into their own
environment, derives the per-pixel geometry field used by the physics loss, and records
the dataset layout that downstream stages read.
"""

from __future__ import annotations

import gc
import time
from pathlib import Path
from typing  import Any, Callable, Tuple

import numpy as np

from configuration.sar.processing_config       import ProcessingConfig
from pipelines.processing.generation.artifacts import ArtifactRegistry, DatasetDirectoryGuard, MetadataManager
from pipelines.processing.generation.interferogram import SecondaryAmplitudeAudit
from pipelines.processing.generation.tomogram  import TomogramContentAudit
from pipelines.shared.config.resolved_entry_config import ResolvedEntryConfigWriter
from pipelines.shared.orchestration.session_scheduler import SequentialSessionScheduler
from tools.data.io                             import FileIO
from tools.monitoring.logger                   import Logger
from tools.sar.geometry_field                   import GeometryField, GeometryFieldBuilder
from tools.sar.interferogram_launcher           import InterferogramLauncher
from tools.sar.tomogram_launcher                import TomogramLauncher
from tools.sar.track_parameters                 import TrackParameters
from tools.baselines                           import TrackBaselines, TrackProfiles


class ProcessingPipeline:
    """Produces the full preprocessed dataset for one SAR stack.

    Attributes:
        config                 : Processing configuration naming the crop, paths and PyRat environment.
        logger                 : Logger for the stage report.
        artifact_registry      : Resolver mapping artifact names to on-disk paths.
        metadata_manager       : Writer of the per-stage metadata and the dataset layout.
        tomogram_launcher      : Launcher for the tomogram stage in the PyRat environment.
        interferogram_launcher : Launcher for the interferogram stage in the PyRat environment.
    """

    def __init__(self, config: ProcessingConfig, logger: Logger) -> None:
        """Wires the artifact registry, metadata manager and stage launchers.

        Args:
            config : Processing configuration for this stack.
            logger : Logger for initialization and stage output.
        """
        self.config = config
        self.logger = logger

        self.artifact_registry      = ArtifactRegistry   (config, logger=self.logger)
        self.metadata_manager       = MetadataManager    (config, logger=self.logger)
        self.tomogram_launcher      = TomogramLauncher    (config.tomogram_env_name, logger=self.logger)
        self.interferogram_launcher = InterferogramLauncher(config.tomogram_env_name, logger=self.logger)

        self._pass_labels      : list | None      = None
        self._stage_provenance : dict             = {}
        self._stage_seconds    : dict[str, float] = {}

        self.logger.section("[Pre-Processing Pipeline Initialized]")
        self.logger.subsection(f"Stack ID         : {config.stack_identifier}")
        self.logger.subsection(f"Tomogram Env     : {config.tomogram_env_name}")

    def _stage_tomogram(self) -> Tuple[Path, Path]:
        """Generates the full-stack tomogram and DEM in the PyRat environment and records their content audit.

        Returns:
            Tuple of the tomogram .npy path and the DEM .npy path.
        """
        tomogram_path = self.artifact_registry.artifact_path("tomogram_full")
        dem_path      = self.artifact_registry.artifact_path("dem_full")
        result_path   = self.config.paths.metadata_directory / "tomogram_result.json"

        self.logger.subsection(f"[Active] Generating full-stack tomogram in env '{self.config.tomogram_env_name}'")
        spec      = self.tomogram_launcher.build_spec(self.config, tomogram_path, dem_path, result_path)
        spec_path = self.config.paths.metadata_directory / "tomogram_spec.json"
        result    = self.tomogram_launcher.generate(spec, spec_path)

        TomogramContentAudit.log_summary(result["content"], self.logger)
        self._stage_provenance["tomogram_stage"] = result["provenance"]

        self.metadata_manager.save_stage_metadata(
            stage_name       = "tomogram_full",
            metadata_entries = self.metadata_manager.build_tomogram_metadata(tomogram_path, self.config.stack_identifier, self.config.tomogram_config, result["content"]),
        )

        gc.collect()

        return tomogram_path, dem_path

    def _stage_inputs(self) -> Tuple[Path, Path, Path]:
        """Builds the interferometric stack, checks it shares the tomogram grid and records its shapes, INF suffix, amplitude audit and pass labels.

        Returns:
            Tuple of the primary, secondaries and interferograms .npy paths.

        Raises:
            RuntimeError : If the saved tomogram's (azimuth, range) grid differs from the primary SLC grid.
        """
        tomogram_path       = self.artifact_registry.artifact_path("tomogram_full")
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
        tomogram_grid        = tuple(np.load(str(tomogram_path), mmap_mode="r").shape[1:])

        if tomogram_grid != primary_shape:
            raise RuntimeError(f"Tomogram grid {tomogram_grid} in {tomogram_path} differs from the primary SLC grid {primary_shape} of the interferometric stack; the dataset would hold misaligned products, so it is not written")

        self.logger.subsection(f"[FSAR] INF suffix: {result['inf_suffix'] if result['inf_suffix'] else '(none)'} (project options: {result['project_options']!r})")
        SecondaryAmplitudeAudit.log_summary(result["secondary_amplitude"], self.logger)

        self.metadata_manager.save_stage_metadata(
            stage_name       = "inputs",
            metadata_entries = self.metadata_manager.build_inputs_metadata(primary_path, secondaries_path, interferograms_path, primary_shape, secondaries_shape, interferograms_shape, result["secondary_amplitude"], result["project_options"], result["inf_suffix"]),
        )

        self._pass_labels                             = result["pass_labels"]
        self._stage_provenance["interferogram_stage"] = result["provenance"]

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

    def _timed_stage(self, label: str, stage: Callable[[], Any]) -> Any:
        """Runs one stage under the logger's timer and records its wall-clock duration for the completion table.

        Args:
            label : Stage name used in the timer line and as the completion-table key.
            stage : Bound stage method taking no argument.

        Returns:
            Whatever the stage returns.
        """
        started = time.perf_counter()

        with self.logger.timer(label):
            result = stage()

        self._stage_seconds[label] = time.perf_counter() - started
        return result

    def run(self) -> dict[str, Path]:
        """Runs every preprocessing stage and writes the dataset layout with the run's provenance.

        Each stage runs under the logger's timer, and the completion table lists
        the duration of every stage, so the hours of the PyRAT subprocesses are
        read off the run log under their own names.

        Returns:
            Mapping from artifact name to its saved path, plus the run directory.
        """
        provenance = self.metadata_manager.collect_provenance()

        self.logger.section("[Pre-Processing Pipeline Execution]")
        self.logger.kv_table({
            "Run Directory" : str(self.config.paths.run_directory),
            "Stack ID"      : self.config.stack_identifier,
            "Beamforming"   : self.config.tomogram_config.beamforming_method,
            "Commit"        : provenance["git_commit"],
            "PyRAT"         : f"{provenance['pyrat_commit']} at {provenance['pyrat_directory']}",
            "Host"          : provenance["host"],
            "Python"        : provenance["python"],
            "NumPy"         : provenance["numpy"],
        })

        self.metadata_manager.save_pipeline_configuration(provenance)

        full_tomo_path, full_dem_path = self._timed_stage("Tomogram stage (PyRAT)", self._stage_tomogram)

        primary_path, secondaries_path, interferograms_path = self._timed_stage("Interferogram stage (PyRAT)", self._stage_inputs)

        geometry_field_path = self._timed_stage("Geometry field", self._stage_geometry_field)

        self.metadata_manager.save_dataset_layout(pass_labels=self._pass_labels, provenance={**provenance, **self._stage_provenance})

        self.logger.section("[Pre-Processing Execution Completed]")
        self.logger.kv_table({
            "Tomogram Full"  : str(full_tomo_path),
            "Interferograms" : str(interferograms_path),
            "Geometry Field" : str(geometry_field_path),
            "Passes"         : len(self._pass_labels),
            "Run Directory"  : str(self.config.paths.run_directory),
            **{f"{label} [s]": f"{seconds:.1f}" for label, seconds in self._stage_seconds.items()},
        })

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
        index        : Zero-based position of this session in the scheduled batch.
        total        : Number of sessions in the batch.
        dataset_name : Name identifying the dataset being preprocessed.
        config       : Processing configuration for this dataset.
        entry_config : Resolved entry config persisted into the dataset's docs, or None.
    """

    def __init__(self, index: int, total: int, dataset_name: str, config: ProcessingConfig, entry_config=None) -> None:
        """Binds the session to a dataset configuration and its batch position.

        Args:
            index        : Zero-based position in the scheduled batch.
            total        : Number of sessions in the batch.
            dataset_name : Name identifying the dataset.
            config       : Processing configuration for this dataset.
            entry_config : Optional resolved entry config persisted into the dataset directory so the run can be copied from the launch console.
        """
        self.index        = index
        self.total        = total
        self.dataset_name = dataset_name
        self.config       = config
        self.entry_config = entry_config

    def execute(self) -> dict[str, Path]:
        """Refuses a finished dataset directory, creates the run logger, runs the pipeline and persists the entry config.

        The configuration is written only once the pipeline has produced its
        artifacts, the same ordering parameter extraction and external injection
        use, so a failed run leaves no config behind and every dataset the launch
        console offers to copy from is one that really finished. The logger is
        closed with any escaping exception, so a failed run ends its
        logs/preprocessing.log with the ABORTED banner and the traceback rather
        than a clean END.

        Returns:
            The artifact mapping returned by ``ProcessingPipeline.run``.

        Raises:
            FileExistsError : If the dataset directory already holds a finished dataset.
        """
        run_dir   = Path(self.config.paths.run_directory)
        log_dir   = run_dir / "logs"
        guard     = DatasetDirectoryGuard(run_dir)
        leftovers = guard.leftovers()

        FileIO.ensure_dirs(run_dir, log_dir)

        with Logger(log_dir=str(log_dir), name="preprocessing", level="INFO") as logger:
            guard.warn(leftovers, logger)

            artifacts = ProcessingPipeline(self.config, logger=logger).run()

            if self.entry_config is not None:
                ResolvedEntryConfigWriter.save(self.entry_config, run_dir, logger)

            return artifacts


def run_preprocess_session(session: PreProcessSession) -> dict[str, Path]:
    """Module-level entry point so a session can be dispatched by a scheduler."""
    return session.execute()


class PreProcessScheduler(SequentialSessionScheduler):
    """Runs the given preprocessing sessions one after another.

    Attributes:
        sessions : Preprocessing sessions to execute, in order.
    """

    def __init__(self, sessions: list[PreProcessSession], logger: Logger) -> None:
        """Binds the scheduler to a fixed list of preprocessing sessions.

        Args:
            sessions : Sessions to execute, in order.
            logger   : Logger shared with the base scheduler.
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



