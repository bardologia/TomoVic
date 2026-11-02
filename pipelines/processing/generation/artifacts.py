"""Artifact naming and metadata writing for the preprocessing run.

DatasetDirectoryGuard refuses to run preprocessing into a directory that already
holds a finished dataset; ArtifactRegistry fixes where each generated cube lives
inside a run directory; MetadataManager writes the per-stage text metadata, the
serialized configuration state and the dataset layout other pipelines read the
run through.
"""

from __future__ import annotations

from dataclasses import asdict
from pathlib     import Path
from typing      import Literal, Tuple

from configuration.sar.processing_config           import ProcessingConfig, TomogramConfig
from pipelines.processing.generation.interferogram import SecondaryAmplitudeAudit
from pipelines.processing.generation.tomogram      import TomogramContentAudit
from pipelines.shared.config.resolved_entry_config import ResolvedEntryConfigWriter
from tools.data.io                                 import FileIO
from tools.monitoring.logger                       import Logger
from tools.runtime.git_state                       import GitState, RunProvenance
from tools.baselines                               import TrackProfiles


ArtifactType = Literal["tomogram_full", "dem_full", "primary", "secondaries", "interferograms", "track_profiles"]


class DatasetDirectoryGuard:
    """Refuses to run preprocessing into a directory that already holds a finished dataset.

    A directory counts as a finished dataset when it carries the dataset layout,
    the resolved entry config or parameter runs under params/. Each of these
    means later stages have already read, or been fitted to, the arrays a rerun
    would replace in place, and nothing downstream could tell the old and the
    new arrays apart afterwards. A directory left behind by an unfinished run
    carries none of them and is reused with a warning.

    Attributes:
        LAYOUT_RELPATH : Dataset layout the pipeline writes last, relative to the dataset directory.
        PARAMS_DIRNAME : Directory holding the dataset's parameter-extraction runs.
        run_dir        : Dataset directory the guard inspects.
    """

    LAYOUT_RELPATH = Path("data") / "dataset.json"
    PARAMS_DIRNAME = "params"

    def __init__(self, run_dir: Path) -> None:
        """Binds the guard to a dataset directory.

        Args:
            run_dir : Dataset directory a preprocessing session is about to write into.
        """
        self.run_dir = Path(run_dir)

    def finished_markers(self) -> list[str]:
        """Returns the relative paths of the finished-dataset files present in the directory."""
        markers = []

        for relative in (self.LAYOUT_RELPATH, ResolvedEntryConfigWriter.RELATIVE_PATH):
            if (self.run_dir / relative).is_file():
                markers.append(str(relative))

        return markers

    def parameter_runs(self) -> list[str]:
        """Returns the names of the parameter runs held under params/, sorted."""
        params_dir = self.run_dir / self.PARAMS_DIRNAME

        if not params_dir.is_dir():
            return []

        return sorted(child.name for child in params_dir.iterdir() if child.is_dir())

    def leftovers(self) -> list[str]:
        """Refuses a finished dataset directory and returns what an unfinished run left in it.

        Called before a session creates anything in the directory, so the
        returned names are an earlier run's, never the session's own logs.

        Returns:
            Sorted names of the directory's entries; empty for an absent or empty directory.

        Raises:
            FileExistsError : If the directory holds a dataset layout, a resolved entry config or parameter runs.
        """
        if not self.run_dir.exists():
            return []

        markers = self.finished_markers()
        runs    = [f"{self.PARAMS_DIRNAME}/{run}" for run in self.parameter_runs()]

        if markers or runs:
            held = ", ".join(markers + runs)
            raise FileExistsError(f"Dataset directory {self.run_dir} already holds a finished dataset ({held}); preprocessing refuses to overwrite it because its parameter runs and training runs were fitted to the arrays in it. Choose another dataset_name or remove the directory by hand.")

        return sorted(child.name for child in self.run_dir.iterdir())

    def warn(self, contents: list[str], logger: Logger) -> None:
        """Warns that an unfinished run's leftovers are overwritten; silent when there are none.

        Args:
            contents : Entries the directory held before the session started, as leftovers returns them.
            logger   : Logger receiving the warning.
        """
        if contents:
            logger.warning(f"Dataset directory {self.run_dir} exists without a finished dataset (contents: {contents}); the leftovers of an unfinished run are overwritten")

    def check(self, logger: Logger) -> None:
        """Refuses a finished dataset directory and warns about an unfinished leftover one.

        Args:
            logger : Logger receiving the leftover warning.

        Raises:
            FileExistsError : If the directory holds a dataset layout, a resolved entry config or parameter runs.
        """
        self.warn(self.leftovers(), logger)


class ArtifactRegistry:
    """Names and locates the cubes a preprocessing run writes.

    Attributes:
        config : Processing configuration holding the run's directory layout.
        logger : Logger reporting the ensured directories.
    """

    def __init__(self, config: ProcessingConfig, logger: Logger) -> None:
        """Initializes the registry.

        Args:
            config : Processing configuration.
            logger : Logger for the directory validation messages.
        """
        self.config = config
        self.logger = logger

    def ensure_directory_structure(self) -> None:
        """Creates the run's data, metadata and temporary directories if absent."""
        paths = self.config.paths
        self.logger.section("[Directory Validation]")
        for directory in (paths.data_directory, paths.metadata_directory, paths.temporary_directory):
            target_dir = FileIO.ensure_dir(directory.resolve())
            self.logger.subsection(f"Ensured path : {target_dir}")

    def artifact_filenames(self) -> dict[str, str]:
        """Returns the filename of each artifact type within the run's data directory."""
        return {
            "tomogram_full"  : "tomogram_full.npy",
            "dem_full"       : "dem_full.npy",
            "primary"        : "primary.npy",
            "secondaries"    : "secondaries.npy",
            "interferograms" : "interferograms.npy",
            "track_profiles" : TrackProfiles.FILENAME,
        }

    def artifact_path(self, artifact_type: ArtifactType) -> Path:
        """Returns the full path of one artifact inside the run's data directory.

        Args:
            artifact_type : Artifact identifier, one of the ArtifactType literals.

        Returns:
            The artifact path.
        """
        filenames = self.artifact_filenames()
        return self.config.paths.data_directory / filenames[artifact_type]


class MetadataManager:
    """Writes the metadata, configuration state, provenance and layout of a preprocessing run.

    Attributes:
        config   : Processing configuration of the run.
        logger   : Logger for the metadata write messages.
        registry : Artifact registry supplying directories and filenames.
    """

    def __init__(self, config: ProcessingConfig, logger: Logger) -> None:
        """Initializes the metadata manager and logs the run identity.

        Args:
            config : Processing configuration of the run.
            logger : Logger for the metadata write messages.
        """
        self.config   = config
        self.logger   = logger
        self.registry = ArtifactRegistry(config, logger)

        self.logger.section("[MetadataManager Initialization]")
        self.logger.subsection(f"Run Directory : {config.paths.run_directory}")
        self.logger.subsection(f"Tomogram Tag  : {config.tomogram_tag}")
        self.logger.subsection(f"Parameter Tag : {config.parameter_tag}")

    def collect_provenance(self) -> dict:
        """Returns the commit, host, interpreter and library versions of this process together with the PyRAT checkout revision.

        PyRAT is read as a checkout of its own, so a dataset records the PyRAT
        revision and whether its tree was patched in place, which is what tells
        datasets made before and after such a patch apart.

        Returns:
            Mapping with the RunProvenance fields plus pyrat_directory and pyrat_commit.
        """
        pyrat_directory = self.config.paths.pyrat_directory

        return {**RunProvenance.collect(), "pyrat_directory": str(pyrat_directory), "pyrat_commit": GitState.commit(pyrat_directory)}

    def build_tomogram_metadata(self, output_path: Path, stack_identifier: str, cfg: TomogramConfig, content: dict) -> dict[str, str]:
        """Builds the text metadata entries describing a generated tomogram and its content audit.

        Args:
            output_path      : Path of the written tomogram cube.
            stack_identifier : Identifier of the SAR stack the tomogram was formed from.
            cfg              : Tomogram configuration holding the project, polarisation, track selection, height range in metres, filter and beamforming settings.
            content          : Content summary of the merged cube from the tomogram stage result, with the merged shapes.

        Returns:
            Mapping from metadata key to its string value.
        """
        return {
            "tomo_full"    : str(output_path),
            "crop"         : f"[{', '.join(str(v) for v in self.config.crop.as_tuple())}]",
            "FuSARproject" : cfg.fusar_project_path,
            "id"           : stack_identifier,
            "basedir"      : cfg.base_directory,
            "polarisation" : cfg.polarisation,
            "select"       : cfg.track_selection,
            "range"        : f"[{', '.join(str(v) for v in cfg.height_range)}]",
            "filter"       : cfg.filter_method,
            "method"       : cfg.beamforming_method,
            "win"          : f"[{', '.join(str(v) for v in cfg.filter_arguments['win'])}]",
            **TomogramContentAudit.describe(content),
        }

    def build_inputs_metadata(self, primary_path: Path, secondaries_path: Path, interferograms_path: Path, primary_shape: Tuple[int, ...], secondaries_shape: Tuple[int, ...], interferograms_shape: Tuple[int, ...], secondary_amplitude: dict, project_options: str, inf_suffix: str) -> dict[str, str]:
        """Builds the text metadata entries describing the generated input stack, the INF products it loaded and its secondary amplitude audit.

        Args:
            primary_path         : Path of the primary SLC cube.
            secondaries_path     : Path of the secondary SLC cube.
            interferograms_path  : Path of the interferogram cube.
            primary_shape        : Shape of the primary SLC as (azimuth, range).
            secondaries_shape    : Shape of the secondaries as (track, azimuth, range).
            interferograms_shape : Shape of the interferograms as (track, azimuth, range).
            secondary_amplitude  : Per-pass amplitude audit from the interferogram stage result, as built by SecondaryAmplitudeAudit.summary.
            project_options      : Raw Options string of the F-SAR project row the stage read.
            inf_suffix           : Coregistration suffix that selected the INF-SLC and phadem products, empty when the row declares none.

        Returns:
            Mapping from metadata key to its string value.
        """
        cfg = self.config.tomogram_config
        return {
            "primary_path"         : str(primary_path),
            "secondaries_path"     : str(secondaries_path),
            "interferograms_path"  : str(interferograms_path),
            "primary_shape"        : f"[{', '.join(str(v) for v in primary_shape)}]",
            "secondaries_shape"    : f"[{', '.join(str(v) for v in secondaries_shape)}]",
            "interferograms_shape" : f"[{', '.join(str(v) for v in interferograms_shape)}]",
            "crop"                 : f"[{', '.join(str(v) for v in self.config.crop.as_tuple())}]",
            "FuSARproject"         : cfg.fusar_project_path,
            "id"                   : self.config.stack_identifier,
            "basedir"              : cfg.base_directory,
            "polarisation"         : cfg.polarisation,
            "select"               : cfg.track_selection,
            "data_type"            : self.config.dataset_type,
            "project_options"      : project_options if project_options else "(empty)",
            "inf_suffix"           : inf_suffix if inf_suffix else "(none)",
            **SecondaryAmplitudeAudit.describe(secondary_amplitude),
        }

    def save_stage_metadata(self, stage_name: str, metadata_entries: dict[str, str]) -> Path:
        """Writes one stage's metadata entries to meta_<stage_name>.txt.

        Args:
            stage_name       : Stage identifier used in the filename.
            metadata_entries : Mapping from metadata key to its string value.

        Returns:
            Path of the written metadata file.
        """
        self.registry.ensure_directory_structure()
        meta_filename = f"meta_{stage_name}.txt"
        meta_path     = self.config.paths.metadata_directory / meta_filename

        self.logger.section(f"[Saving Metadata] Stage: {stage_name}")
        FileIO.save_text_metadata(metadata_entries, meta_path)

        self.logger.subsection(f"Metadata written: {meta_path}")
        return meta_path

    def save_pipeline_configuration(self, provenance: dict) -> Path:
        """Serializes the full processing configuration and the run's provenance to meta/config_state.json.

        Args:
            provenance : Provenance block, written under the 'provenance' key next to the configuration fields.

        Returns:
            Path of the written configuration state file.
        """
        self.registry.ensure_directory_structure()

        dump_path = self.config.paths.metadata_directory / "config_state.json"

        config_dict = {**asdict(self.config), "provenance": provenance}

        self.logger.section("[Saving Configuration State]")
        FileIO.save_json(config_dict, dump_path)

        self.logger.subsection(f"Configuration preserved at: {dump_path}")
        return dump_path

    def save_dataset_layout(self, pass_labels: list | None, provenance: dict) -> Path:
        """Writes data/dataset.json, the entry point downstream pipelines read the run through.

        Args:
            pass_labels : Track labels in acquisition order, primary first; None when the run carries no pass labelling.
            provenance  : Provenance of this process and of the two PyRAT stages, written under the 'provenance' key.

        Returns:
            Path of the written layout file, recording the global crop, dataset type,
            tomogram and parameter tags, amplitude clip, pass labels, artifact
            filenames and provenance.
        """
        self.registry.ensure_directory_structure()

        layout = {
            "global_crop"        : list(self.config.crop.as_tuple()),
            "dataset_type"       : self.config.dataset_type,
            "tomogram_tag"       : self.config.tomogram_tag,
            "parameter_tag"      : self.config.parameter_tag,
            "max_amplitude_clip" : self.config.tomogram_config.max_amplitude_clip,
            "pass_labels"        : list(pass_labels) if pass_labels is not None else None,
            "artifacts"          : self.registry.artifact_filenames(),
            "provenance"         : provenance,
        }

        out_path = self.config.paths.data_directory / "dataset.json"
        FileIO.save_json(layout, out_path, indent=2)

        self.logger.section(f"[Dataset Layout Saved] {out_path}")
        return out_path
