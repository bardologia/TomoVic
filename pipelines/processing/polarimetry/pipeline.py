"""Extends a preprocessed dataset with its polarimetric primary.

The pipeline reads what the dataset recorded at preprocessing, dispatches the
extraction into the PyRat environment over the dataset's own crop, verifies the
written array against the dataset's primary grid and lists the artifact in
data/dataset.json, which is what makes the Cube tab offer the Pauli view.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np

from configuration.sar.polarimetry_config import PolarimetryEntryConfig
from tools.data.io                        import FileIO
from tools.monitoring.logger              import Logger
from tools.sar.polarimetry                import PolarimetricArtifact
from tools.sar.polarimetry_launcher       import PolarimetricLauncher


@dataclass
class DatasetRecord:
    """What the extraction needs to know about one dataset, read from its config state and layout.

    Attributes:
        run_directory    : Dataset run directory.
        tomogram_config  : ``tomogram_config`` block of meta/config_state.json.
        stack_identifier : ID column of the F-SAR project row selecting the stack.
        crop             : Global crop as (azimuth_start, azimuth_end, range_start, range_end) in pixels.
        window           : Covariance window of the tomogram as (azimuth, range) pixels, the default multilook of the Pauli view.
        layout           : Parsed data/dataset.json.
    """

    run_directory    : Path
    tomogram_config  : dict
    stack_identifier : str
    crop             : tuple
    window           : tuple
    layout           : dict

    @property
    def primary_path(self) -> Path:
        """Path of the single-polarisation primary SLC the dataset was built from."""
        return self.run_directory / "data" / self.layout["artifacts"]["primary"]

    @property
    def artifact_path(self) -> Path:
        """Path the polarimetric primary artifact is written to."""
        return self.run_directory / "data" / PolarimetricArtifact.FILENAME

    @property
    def sidecar_path(self) -> Path:
        """Path of the provenance sidecar of the polarimetric primary artifact."""
        return self.run_directory / "meta" / PolarimetricArtifact.SIDECAR

    @property
    def layout_path(self) -> Path:
        """Path of the dataset layout file."""
        return self.run_directory / "data" / "dataset.json"

    @property
    def spec_path(self) -> Path:
        """Path the worker specification is written to."""
        return self.run_directory / "meta" / "polarimetry_spec.json"

    @property
    def result_path(self) -> Path:
        """Path the worker writes its result JSON to."""
        return self.run_directory / "meta" / "polarimetry_result.json"

    @property
    def present(self) -> bool:
        """Whether the artifact is listed in the layout with its array and sidecar on disk."""
        listed = self.layout["artifacts"].get(PolarimetricArtifact.ARTIFACT_KEY) == PolarimetricArtifact.FILENAME
        return listed and self.artifact_path.is_file() and self.sidecar_path.is_file()

    @classmethod
    def load(cls, run_directory: Path) -> "DatasetRecord":
        """Reads the config state and layout of a dataset.

        Args:
            run_directory : Dataset run directory holding meta/config_state.json and data/dataset.json.

        Returns:
            The dataset record.
        """
        run_directory = Path(run_directory)
        config_state  = FileIO.load_json(run_directory / "meta" / "config_state.json")
        layout        = FileIO.load_json(run_directory / "data" / "dataset.json")
        tomogram      = config_state["tomogram_config"]

        return cls(
            run_directory    = run_directory,
            tomogram_config  = tomogram,
            stack_identifier = str(config_state["stack_identifier"]),
            crop             = tuple(int(value) for value in layout["global_crop"]),
            window           = tuple(int(value) for value in tomogram["filter_arguments"]["win"]),
            layout           = layout,
        )


class PolarimetryPipeline:
    """Extracts, verifies and registers the polarimetric primary of one dataset.

    Attributes:
        dataset_directory : Dataset run directory being extended.
        config            : Entry configuration naming the PyRat root, threads, environment and overwrite policy.
        logger            : Logger for progress reporting.
        launcher          : Launcher dispatching the extraction into the PyRat environment.
    """

    def __init__(self, dataset_directory: Path, config: PolarimetryEntryConfig, logger: Logger, launcher: PolarimetricLauncher | None = None) -> None:
        """Binds the pipeline to one dataset.

        Args:
            dataset_directory : Dataset run directory.
            config            : Entry configuration.
            logger            : Logger for progress reporting.
            launcher          : Launcher to dispatch with, or None to build one for the configured environment.
        """
        self.dataset_directory = Path(dataset_directory)
        self.config            = config
        self.logger            = logger
        self.launcher          = PolarimetricLauncher(config.tomogram_env_name, logger) if launcher is None else launcher

    def _record(self) -> DatasetRecord:
        """Reads the dataset's config state and layout."""
        return DatasetRecord.load(self.dataset_directory)

    def _spec(self, record: DatasetRecord) -> dict:
        """Builds the worker specification for the dataset."""
        return PolarimetricLauncher.build_spec(
            tomogram_config  = record.tomogram_config,
            stack_identifier = record.stack_identifier,
            crop             = record.crop,
            pyrat_directory  = self.config.pyrat_directory,
            pyrat_threads    = self.config.pyrat_threads,
            window           = record.window,
            primary_path     = record.primary_path,
            artifact_path    = record.artifact_path,
            sidecar_path     = record.sidecar_path,
            result_path      = record.result_path,
        )

    def _verify(self, record: DatasetRecord, result: dict) -> tuple:
        """Checks the written array sits on the dataset's primary grid and the sidecar exists.

        Args:
            record : Dataset the artifact belongs to.
            result : Result payload of the worker.

        Returns:
            Shape of the written array.

        Raises:
            FileNotFoundError : If the array or the sidecar the worker reported is missing.
            RuntimeError      : If the array is not a three-channel stack on the primary grid or differs from the reported shape.
        """
        if not record.artifact_path.is_file():
            raise FileNotFoundError(f"The worker reported success but {record.artifact_path} is missing")
        if not record.sidecar_path.is_file():
            raise FileNotFoundError(f"The worker reported success but {record.sidecar_path} is missing")

        shape        = tuple(int(value) for value in np.load(record.artifact_path, mmap_mode="r").shape)
        primary_grid = tuple(int(value) for value in np.load(record.primary_path, mmap_mode="r").shape)

        if shape != (3,) + primary_grid:
            raise RuntimeError(f"Polarimetric primary {record.artifact_path} has shape {shape}, expected (3, {primary_grid[0]}, {primary_grid[1]}) on the primary grid; the dataset would hold misaligned products, so the artifact is not registered")
        if shape != tuple(result["shape"]):
            raise RuntimeError(f"Polarimetric primary {record.artifact_path} has shape {shape} but the worker reported {tuple(result['shape'])}")

        return shape

    def _register(self, record: DatasetRecord) -> None:
        """Lists the artifact in data/dataset.json, rewriting the layout atomically."""
        layout = dict(record.layout)
        layout["artifacts"] = dict(record.layout["artifacts"])
        layout["artifacts"][PolarimetricArtifact.ARTIFACT_KEY] = PolarimetricArtifact.FILENAME

        FileIO.save_json(layout, record.layout_path, atomic=True)

    def run(self) -> dict:
        """Extracts, verifies and registers the polarimetric primary of the dataset.

        Returns:
            Dict with ``skipped`` and, after an extraction, the written ``shape``, the ``cross_source`` and the ``cross_polar_check`` of the worker.
        """
        record = self._record()

        if record.present and not self.config.overwrite:
            self.logger.info(f"skip {record.artifact_path} already present (set overwrite to extract again)")
            return {"skipped": True}

        self.logger.kv_table({
            "Dataset"     : record.run_directory,
            "Crop"        : record.crop,
            "Stack"       : record.stack_identifier,
            "Window"      : record.window,
            "Environment" : self.config.tomogram_env_name,
            "PyRat"       : self.config.pyrat_directory,
        }, title="Polarimetric extraction")

        spec   = self._spec(record)
        result = self.launcher.generate(spec, record.spec_path)
        shape  = self._verify(record, result)

        self._register(record)

        check = result["cross_polar_check"]
        self.logger.ok(f"registered {PolarimetricArtifact.ARTIFACT_KEY} {shape} in {record.layout_path} (cross-polar check {check['match']}, coherence {check['coherence']:.4f}, power ratio {check['power_ratio']:.3f})")

        return {"skipped": False, "shape": shape, "cross_source": result["cross_source"], "cross_polar_check": check}
