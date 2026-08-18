"""Artifact naming and metadata writing for the preprocessing run.

ArtifactRegistry fixes where each generated cube lives inside a run directory;
MetadataManager writes the per-stage text metadata, the serialized configuration
state and the dataset layout other pipelines read the run through.
"""

from __future__ import annotations

from dataclasses import asdict
from pathlib     import Path
from typing      import Literal, Tuple

from configuration.sar.processing_config import ProcessingConfig, TomogramConfig
from tools.data.io                       import FileIO
from tools.monitoring.logger             import Logger
from tools.baselines                     import TrackProfiles


ArtifactType = Literal["tomogram_full", "dem_full", "primary", "secondaries", "interferograms", "track_profiles"]


class ArtifactRegistry:
    """Names and locates the cubes a preprocessing run writes.

    Attributes:
        config: Processing configuration holding the run's directory layout.
        logger: Logger reporting the ensured directories.
    """

    def __init__(self, config: ProcessingConfig, logger: Logger) -> None:
        """Initializes the registry.

        Args:
            config: Processing configuration.
            logger: Logger for the directory validation messages.
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
            artifact_type: Artifact identifier, one of the ArtifactType literals.

        Returns:
            The artifact path.
        """
        filenames = self.artifact_filenames()
        return self.config.paths.data_directory / filenames[artifact_type]


class MetadataManager:
    """Writes the metadata, configuration state and layout of a preprocessing run.

    Attributes:
        config: Processing configuration of the run.
        logger: Logger for the metadata write messages.
        registry: Artifact registry supplying directories and filenames.
    """

    def __init__(self, config: ProcessingConfig, logger: Logger) -> None:
        """Initializes the metadata manager and logs the run identity.

        Args:
            config: Processing configuration of the run.
            logger: Logger for the metadata write messages.
        """
        self.config   = config
        self.logger   = logger
        self.registry = ArtifactRegistry(config, logger)

        self.logger.section("[MetadataManager Initialization]")
        self.logger.subsection(f"Run Directory : {config.paths.run_directory}")
        self.logger.subsection(f"Tomogram Tag  : {config.tomogram_tag}")
        self.logger.subsection(f"Parameter Tag : {config.parameter_tag}")

    def build_tomogram_metadata(self, output_path: Path, stack_identifier: str, cfg: TomogramConfig) -> dict[str, str]:
        """Builds the text metadata entries describing a generated tomogram.

        Args:
            output_path: Path of the written tomogram cube.
            stack_identifier: Identifier of the SAR stack the tomogram was formed from.
            cfg: Tomogram configuration holding the project, polarisation, track
                selection, height range in metres, filter and beamforming settings.

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
        }

    def build_inputs_metadata(self, primary_path: Path, secondaries_path: Path, interferograms_path: Path, primary_shape: Tuple[int, ...], secondaries_shape: Tuple[int, ...], interferograms_shape: Tuple[int, ...]) -> dict[str, str]:
        """Builds the text metadata entries describing the generated input stack.

        Args:
            primary_path: Path of the primary SLC cube.
            secondaries_path: Path of the secondary SLC cube.
            interferograms_path: Path of the interferogram cube.
            primary_shape: Shape of the primary SLC as (azimuth, range).
            secondaries_shape: Shape of the secondaries as (track, azimuth, range).
            interferograms_shape: Shape of the interferograms as (track, azimuth, range).

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
        }

    def save_stage_metadata(self, stage_name: str, metadata_entries: dict[str, str]) -> Path:
        """Writes one stage's metadata entries to meta_<stage_name>.txt.

        Args:
            stage_name: Stage identifier used in the filename.
            metadata_entries: Mapping from metadata key to its string value.

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

    def save_pipeline_configuration(self) -> Path:
        """Serializes the full processing configuration to meta/config_state.json.

        Returns:
            Path of the written configuration state file.
        """
        self.registry.ensure_directory_structure()

        dump_path = self.config.paths.metadata_directory / "config_state.json"

        config_dict = asdict(self.config)

        self.logger.section("[Saving Configuration State]")
        FileIO.save_json(config_dict, dump_path)

        self.logger.subsection(f"Configuration preserved at: {dump_path}")
        return dump_path

    def save_dataset_layout(self, pass_labels: list | None = None) -> Path:
        """Writes data/dataset.json, the entry point downstream pipelines read the run through.

        Args:
            pass_labels: Track labels in acquisition order, primary first; None when
                the run carries no pass labelling.

        Returns:
            Path of the written layout file, recording the global crop, dataset type,
            tomogram and parameter tags, amplitude clip and artifact filenames.
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
        }

        out_path = self.config.paths.data_directory / "dataset.json"
        FileIO.save_json(layout, out_path, indent=2)

        self.logger.section(f"[Dataset Layout Saved] {out_path}")
        return out_path
