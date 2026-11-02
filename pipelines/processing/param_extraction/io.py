"""Persistence for parameter-extraction runs: metadata, parameter stacks and diagnostics.

Also carries the guard that distinguishes runs fitted by ``extract_params`` from runs
whose parameters were injected from external files and therefore carry no diagnostics,
and the guard that keeps a new fit from silently replacing an existing run.
"""

from __future__ import annotations

import shutil
from datetime import datetime
from pathlib  import Path

import numpy as np

from configuration.param_extraction import ExtractionConfig
from tools.data.io                  import FileIO
from tools.runtime.git_state        import GitState
from tools.sar.geometry_field       import GeometryField
from tools.monitoring.logger        import Logger


class ParameterRunMeta:
    """Names the run files and classifies runs by their parameter source.

    Attributes:
        FILENAME            : Name of the run metadata file.
        PARAMETERS_FILENAME : Name of the parameter stack every run holds.
        EXTERNAL_SOURCE     : Metadata ``source`` value marking an injected run.
    """

    FILENAME            = "param_extraction_meta.json"
    PARAMETERS_FILENAME = "parameters.npy"
    EXTERNAL_SOURCE     = "external"

    @classmethod
    def is_external(cls, run_dir: Path) -> bool:
        """Returns whether the run's parameters were injected from external files."""
        meta_path = Path(run_dir) / cls.FILENAME

        if not meta_path.is_file():
            return False

        return FileIO.load_json(meta_path).get("source") == cls.EXTERNAL_SOURCE

    @classmethod
    def holds_run(cls, run_dir: Path) -> bool:
        """Returns whether a directory already holds a parameter run, judged by its metadata or its parameter stack."""
        run_dir = Path(run_dir)

        return (run_dir / cls.FILENAME).is_file() or (run_dir / cls.PARAMETERS_FILENAME).is_file()

    @classmethod
    def describe(cls, run_dir: Path) -> str:
        """Returns the source and timestamp of the run a directory holds, or names the bare parameter stack.

        Args:
            run_dir : Parameter run directory that ``holds_run`` reported as occupied.

        Returns:
            ``fitted <timestamp>`` or ``injected <timestamp>`` read from the metadata, or ``parameters.npy without metadata``.
        """
        meta_path = Path(run_dir) / cls.FILENAME

        if not meta_path.is_file():
            return f"{cls.PARAMETERS_FILENAME} without metadata"

        meta   = FileIO.load_json(meta_path)
        source = "injected" if meta.get("source") == cls.EXTERNAL_SOURCE else "fitted"

        return f"{source} {meta['timestamp']}"

    @classmethod
    def dataset_dir(cls, run_dir: Path) -> Path:
        """Returns the dataset root above the ``params`` directory holding a run.

        Args:
            run_dir : Parameter run directory of the form ``<dataset>/params/<run>``.

        Raises:
            ValueError : If the run directory does not sit under a ``params`` directory, so the dataset root holding the geometry field cannot be located.
        """
        for parent in Path(run_dir).parents:
            if parent.name == "params":
                return parent.parent

        raise ValueError(f"Parameter run {run_dir} does not sit under a 'params' directory, so the dataset root holding meta/{GeometryField.FILENAME} cannot be located.")

    @classmethod
    def reject_external(cls, run_dir: Path, action: str) -> None:
        """Raises if the run was injected rather than fitted here.

        Args:
            run_dir : Parameter run directory to check.
            action  : Phrase completing "cannot ..." in the error message.

        Raises:
            ValueError : If the run carries externally injected parameters.
        """
        if cls.is_external(run_dir):
            raise ValueError(f"Parameter run {run_dir} was injected from external files, not fitted here, so it carries no fit diagnostics and cannot {action}. Point this step at a run produced by extract_params.")


class ExtractionMetadataManager:
    """Writes the run metadata describing how a parameter stack was fitted.

    Attributes:
        config : Extraction configuration whose settings are recorded.
        logger : Logger for the write confirmation.
    """

    def __init__(self, config: ExtractionConfig, logger: Logger) -> None:
        """Binds the manager to one extraction configuration.

        Args:
            config : Extraction configuration whose settings are recorded.
            logger : Logger for the write confirmation.
        """
        self.config = config
        self.logger = logger

    def settings(self) -> dict:
        """Returns the fit settings of the configuration as the metadata records them.

        These are the keys a rerun can differ in while landing on the same run
        name, so they are what a replacement is compared on.
        """
        cfg = self.config.fit_settings.fit_config

        return {
            "k_max"                : cfg.k_max,
            "lambda_k"             : cfg.lambda_k,
            "sigma_init_divisor"   : cfg.sigma_init_divisor,
            "prominence_frac"      : cfg.prominence_frac,
            "activity_threshold"   : cfg.activity_threshold,
            "threshold_factor"     : cfg.threshold_factor,
            "truncation_index"     : cfg.truncation_index,
            "adam_steps"           : self.config.adam_steps,
            "adam_lr"              : self.config.adam_lr,
            "adam_b1"              : self.config.adam_b1,
            "adam_b2"              : self.config.adam_b2,
            "range_batch_size"     : self.config.range_batch_size,
            "gpu_pixel_batch_size" : self.config.gpu_pixel_batch_size,
            "fit_sigma"            : cfg.fit_sigma,
            "fit_amplitude"        : cfg.fit_amplitude,
            "fit_mean"             : cfg.fit_mean,
            "fitting_method"       : self.config.fit_settings.fitting_method,
        }

    def save_run_metadata(self, npy_path: Path, diagnostics_path: Path, tomogram_path: Path, height_range: tuple, fit_outcome: dict) -> Path:
        """Writes the run metadata JSON for a completed fit.

        Beside the fit settings, the record names the commit the fitter ran
        from and what the fit did: the height bins, the active and total
        pixels, whether truncation applied, the backend and devices, the
        duration, the group log, where the height range came from and the
        shares of active slots whose sigma or mean ended on a clamp bound, so the run can be judged from its own
        directory after the shared group log has moved on.

        Args:
            npy_path         : Path of the saved parameter stack.
            diagnostics_path : Path of the saved fit diagnostics archive.
            tomogram_path    : Path of the tomogram the fit was performed on.
            height_range     : Elevation axis limits as (minimum, maximum), in metres.
            fit_outcome      : Outcome keys of the fit, as ``ExtractionOutcome.to_metadata`` returns them, plus the pipeline's ``extraction_log`` and ``height_range_source`` and the permutation's ``FitBoundCensus.fractions``.

        Returns:
            Path of the written metadata JSON.
        """
        meta_path = self.config.output_directory / ParameterRunMeta.FILENAME

        payload = {
            "timestamp"            : datetime.now().isoformat(timespec="seconds"),
            "git_commit"           : GitState.commit(),
            "processed_data_path"  : str(self.config.processed_data_path),
            "source_tomogram"      : str(tomogram_path),
            "height_range"         : list(height_range),
            "output_directory"     : str(self.config.output_directory),
            "output_prefix"        : self.config.output_prefix,
            "output_suffix"        : self.config.output_suffix_value,
            "parameters_npy"       : npy_path.name,
            "diagnostics_npz"      : diagnostics_path.name,
            **self.settings(),
            **fit_outcome,
        }

        FileIO.save_json(payload, meta_path)

        self.logger.subsection(f"-> Metadata written: {meta_path}")
        return meta_path


class ParameterRunDirectory:
    """Prepares the directory a parameter run is written into, replacing an earlier run only on request.

    Attributes:
        logger : Logger for the replacement warning.
    """

    def __init__(self, logger: Logger) -> None:
        """Binds the guard to a logger."""
        self.logger = logger

    @staticmethod
    def _changed_settings(run_dir: Path, settings: dict) -> str:
        """Describes the fit settings on which the new run differs from the metadata of the run it replaces.

        Args:
            run_dir  : Directory of the run being replaced.
            settings : Fit settings of the new run, as ``ExtractionMetadataManager.settings`` returns them.

        Returns:
            A clause listing ``key old -> new`` pairs, or one saying the settings match or that the old run has no metadata.
        """
        meta_path = Path(run_dir) / ParameterRunMeta.FILENAME

        if not meta_path.is_file():
            return "the replaced run carries no metadata to compare settings against"

        old     = FileIO.load_json(meta_path)
        changed = [f"{key} {old[key]!r} -> {value!r}" for key, value in settings.items() if key in old and old[key] != value]

        if not changed:
            return "the fit settings match the replaced run"

        return "settings that differ from the replaced run: " + ", ".join(changed)

    def prepare(self, output_directory: Path, overwrite: bool, settings: dict) -> None:
        """Creates the run directory, deleting an existing run first when overwriting was requested.

        Args:
            output_directory : Directory the new run is written into.
            overwrite        : Whether an existing run there may be deleted and replaced.
            settings         : Fit settings of the new run, compared against the replaced run's metadata in the warning.

        Raises:
            FileExistsError : If the directory already holds a run and overwrite is off.
        """
        output_directory = Path(output_directory)

        if not ParameterRunMeta.holds_run(output_directory):
            output_directory.mkdir(parents=True, exist_ok=True)
            return

        description = ParameterRunMeta.describe(output_directory)

        if not overwrite:
            raise FileExistsError(f"Parameter run {output_directory} already exists ({description}); set overwrite=True to delete and refit it, or change the sweep so the run name differs")

        self.logger.warning(f"Replacing existing parameter run {output_directory} ({description}); its labels, diagnostics and every analysis beside them are deleted, and {self._changed_settings(output_directory, settings)}")

        shutil.rmtree(output_directory)
        output_directory.mkdir(parents=True)


class ParameterIO:
    """Reads and writes the parameter stacks, diagnostics and metadata of a fit.

    Attributes:
        logger : Logger for the read and write reports.
    """

    def __init__(self, logger : Logger) -> None:
        """Binds the reader/writer to a logger."""
        self.logger = logger

    def save_params(self, parameters_array : np.ndarray, npy_path : Path) -> Path:
        """Saves the fitted parameter stack as a contiguous .npy file.

        Args:
            parameters_array : Parameter stack of shape (3 * k_max, azimuth, range), interleaved as amplitude, mean in metres and sigma in metres per slot.
            npy_path         : Destination .npy path.

        Returns:
            The destination path.
        """
        npy_path.parent.mkdir(parents=True, exist_ok=True)

        self.logger.subsection(f"Saving parameter stack of shape {parameters_array.shape} to disk")
        np.save(str(npy_path), np.ascontiguousarray(parameters_array), allow_pickle=False)

        return npy_path

    def load_params(self, npy_path : Path) -> np.ndarray:
        """Loads a parameter stack of shape (3 * k_max, azimuth, range) as float32."""
        self.logger.subsection("Loading saved parameters for metrics and plots")
        return np.load(str(npy_path)).astype(np.float32, copy=False)

    def save_diagnostics(self, diagnostics : dict, npz_path : Path) -> Path:
        """Saves the fit diagnostics arrays into a single .npz archive.

        Args:
            diagnostics : Mapping from diagnostic name to array, such as the per-K MSE of shape (k_max, azimuth, range) and the selected-K map.
            npz_path    : Destination .npz path.

        Returns:
            The destination path.
        """
        npz_path.parent.mkdir(parents=True, exist_ok=True)

        self.logger.subsection(f"Saving fit diagnostics ({', '.join(diagnostics.keys())}) to disk")
        np.savez(str(npz_path), **diagnostics)

        return npz_path

    def load_diagnostics(self, npz_path : Path) -> dict:
        """Returns every array stored in the fit diagnostics .npz archive."""
        self.logger.subsection("Loading fit diagnostics for metrics and plots")
        with np.load(str(npz_path)) as data:
            return {key: data[key] for key in data.files}

    def load_metadata(self, meta_path : Path) -> dict:
        """Returns the run metadata dictionary read from the given JSON path."""
        return FileIO.load_json(meta_path)
