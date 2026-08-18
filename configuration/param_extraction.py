"""Configuration for fitting Gaussian mixtures to tomographic elevation profiles.

Covers the fit hyperparameters and Adam settings of the extraction itself, the
sweep entry point that runs it over a dataset tree, the analysis entry point
that reads the resulting parameter runs, and the injection of externally
produced parameter cubes into the same layout.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib     import Path
from typing      import Optional, Tuple


@dataclass
class FitConfig:
    """Hyperparameters of the per-pixel Gaussian mixture fit.

    Attributes:
        threshold_factor: Fraction of the profile maximum below which samples are ignored.
        truncation_index: Elevation bin above which the profile is truncated.
        k_max: Maximum number of Gaussian components fitted per pixel.
        lambda_k: Penalty weight discouraging additional components.
        prominence_frac: Peak prominence, as a fraction of the profile range, required to seed a component.
        sigma_init_divisor: Divisor turning a peak's half-width into the initial sigma in metres.
        activity_threshold: Amplitude below which a fitted component counts as inactive.
        fit_sigma: Whether component widths are free parameters.
        fit_amplitude: Whether component amplitudes are free parameters.
        fit_mean: Whether component means are free parameters.
    """

    threshold_factor   : float = 0.25
    truncation_index   : int   = 170
    k_max              : int   = 5
    lambda_k           : float = 1e-2
    prominence_frac    : float = 0.05
    sigma_init_divisor : float = 4.0
    activity_threshold : float = 1e-3
    fit_sigma          : bool  = True
    fit_amplitude      : bool  = False
    fit_mean           : bool  = False


class FitMode:
    """Parser for the underscore-joined fit mode naming the free components.

    Attributes:
        COMPONENTS: Component names in the order the returned flags follow.
    """

    COMPONENTS = ("sigma", "amp", "mu")

    @classmethod
    def free_flags(cls, mode: str) -> Tuple[bool, bool, bool]:
        """Returns which of sigma, amplitude and mean are free in a fit mode.

        Args:
            mode: Distinct component names joined with "_", e.g. "sigma_amp_mu".

        Returns:
            One boolean per entry of `COMPONENTS`, True when that component is free.

        Raises:
            ValueError: If the mode is empty, repeats a component, or names an unknown one.
        """
        parts = mode.split("_") if mode else []

        if not parts or len(set(parts)) != len(parts) or any(part not in cls.COMPONENTS for part in parts):
            raise ValueError(f"Unknown fit mode '{mode}'. A mode joins distinct components from {', '.join(cls.COMPONENTS)} with '_', e.g. 'sigma', 'amp_mu', 'sigma_amp_mu'")

        return tuple(component in parts for component in cls.COMPONENTS)


class ChannelOrder:
    """Parser for the component ordering of an external parameter cube.

    Attributes:
        COMPONENTS: Component names in the canonical internal channel order.
    """

    COMPONENTS = ("amp", "mu", "sigma")

    @classmethod
    def positions(cls, order: str) -> Tuple[int, int, int]:
        """Returns where each canonical component sits in a foreign channel order.

        Args:
            order: Permutation of the component names joined with "_", e.g. "mu_sigma_amp".

        Returns:
            The source channel index of amplitude, mean and sigma, in that order.

        Raises:
            ValueError: If the string is not a permutation of `COMPONENTS`.
        """
        parts = order.split("_") if order else []

        if sorted(parts) != sorted(cls.COMPONENTS):
            raise ValueError(f"Unknown channel order '{order}'. An order is a permutation of {', '.join(cls.COMPONENTS)} joined with '_', e.g. 'mu_sigma_amp'")

        return tuple(parts.index(component) for component in cls.COMPONENTS)


@dataclass
class FitSettings:
    """Wrapper exposing the fit mode implied by the fit toggles.

    Attributes:
        fit_config: Hyperparameters of the per-pixel Gaussian mixture fit.
    """

    fit_config : FitConfig = field(default_factory=FitConfig)

    @property
    def free_parameters(self) -> Tuple[str, ...]:
        """Names of the free components, in canonical order.

        Raises:
            ValueError: If no component is free.
        """
        cfg   = self.fit_config
        flags = {"sigma": cfg.fit_sigma, "amp": cfg.fit_amplitude, "mu": cfg.fit_mean}
        names = tuple(name for name in FitMode.COMPONENTS if flags[name])

        if not names:
            raise ValueError("No free parameters: enable at least one of fit_sigma, fit_amplitude, fit_mean")

        return names

    @property
    def fitting_method(self) -> str:
        """Identifier of the fit, joining the free components with the optimizer."""
        return "_".join(self.free_parameters) + "_adam"


@dataclass
class ExtractionConfig:
    """Settings for one parameter-extraction run over a processed dataset.

    The output directory name encodes the fit hyperparameters so that different
    extractions of the same tomogram stay side by side.

    Attributes:
        processed_data_path: Root of the processed dataset holding data/ and meta/.
        pyrat_directory: PyRAT source directory used to read the tomogram.
        output_prefix: Leading token of the parameter run directory name.
        output_suffix: Explicit suffix, or None to derive one from the fit settings.
        height_range: Elevation axis extent in metres, or None to read it from the dataset metadata.
        fit_settings: Fit hyperparameters and the implied fit mode.
        parameter_workers: CPU worker processes writing the parameter chunks.
        range_batch_size: Number of range lines loaded per batch.
        gpu_pixel_batch_size: Number of pixels fitted per GPU batch.
        adam_steps: Adam iterations per pixel batch.
        adam_lr: Adam learning rate.
        adam_b1: Adam first-moment decay.
        adam_b2: Adam second-moment decay.
    """

    processed_data_path : Path
    pyrat_directory     : Path                          = field(default_factory=lambda: Path("/ste/rnd/User/vice_vi/pyrat"))
    output_prefix       : str                           = "params"
    output_suffix       : Optional[str]                 = None
    height_range        : Optional[Tuple[float, float]] = None
    fit_settings        : FitSettings                   = field(default_factory=FitSettings)
    parameter_workers   : int                           = 20

    range_batch_size     : int   = 3500
    gpu_pixel_batch_size : int   = 24576
    adam_steps           : int   = 3000
    adam_lr              : float = 2e-1
    adam_b1              : float = 0.95
    adam_b2              : float = 0.999


    @property
    def data_directory(self) -> Path:
        """Directory holding the processed tomogram arrays."""
        return Path(self.processed_data_path) / "data"

    @property
    def metadata_directory(self) -> Path:
        """Directory holding the dataset metadata JSON files."""
        return Path(self.processed_data_path) / "meta"

    @property
    def output_suffix_value(self) -> str:
        """Suffix identifying the fit, explicit or derived from the fit settings."""
        if self.output_suffix:
            return self.output_suffix

        cfg     = self.fit_settings.fit_config
        lam_tag = f"{cfg.lambda_k:g}"
        div_tag = f"{cfg.sigma_init_divisor:g}"
        free    = "_".join(self.fit_settings.free_parameters)

        return f"k{cfg.k_max}_lam{lam_tag}_sig{div_tag}_{free}"

    @property
    def output_subdir_name(self) -> str:
        """Name of the parameter run directory under params/."""
        return f"{self.output_prefix}_{self.output_suffix_value}"

    @property
    def output_directory(self) -> Path:
        """Directory this extraction writes its parameter run into."""
        return Path(self.processed_data_path) / "params" / self.output_subdir_name

    @property
    def parameters_npy_path(self) -> Path:
        """Path of the fitted parameter cube written by this extraction."""
        return self.output_directory / "parameters.npy"

    @property
    def diagnostics_npz_path(self) -> Path:
        """Path of the per-pixel fit diagnostics archive."""
        return self.output_directory / "fit_diagnostics.npz"

    def discover_tomogram_path(self) -> Path:
        """Returns the path of the full tomogram cube to be fitted.

        Returns:
            Path of tomogram_full.npy inside the dataset data directory.

        Raises:
            FileNotFoundError: If the tomogram file is absent.
        """
        tomogram_path = self.data_directory / "tomogram_full.npy"

        if not tomogram_path.is_file():
            raise FileNotFoundError(f"No tomogram_full.npy in {self.data_directory}")

        return tomogram_path

    def discover_height_range(self) -> Tuple[float, float]:
        """Returns the elevation axis extent of the tomogram.

        The configured override wins; otherwise the range is read from the
        dataset config_state.json.

        Returns:
            The (minimum, maximum) elevation in metres.

        Raises:
            FileNotFoundError: If no override is set and the metadata does not carry a tomogram height range.
        """
        if self.height_range is not None:
            return tuple(self.height_range)

        meta_dir   = self.metadata_directory
        state_path = meta_dir / "config_state.json"
        if state_path.is_file():
            with open(state_path, "r", encoding="utf-8") as f:
                state = json.load(f)

            hr = state["tomogram_config"]["height_range"]
            if isinstance(hr, (list, tuple)) and len(hr) == 2:
                return (float(hr[0]), float(hr[1]))

        raise FileNotFoundError(f"No height_range override given and no config_state.json with a tomogram height_range under {meta_dir}")


@dataclass
class ExtractParamsEntryConfig:
    """Sweep settings for extracting parameters across a tree of datasets.

    Each combination of k, lambda and fit mode becomes a separate extraction
    run, fanned out over the configured GPUs.

    Attributes:
        dataset_base_path: Root directory scanned for processed datasets.
        dataset_filter: Substrings a dataset directory name must contain to be selected; empty selects all.
        pyrat_directory: PyRAT source directory used to read the tomograms.
        output_prefix: Leading token of each parameter run directory name.
        output_suffix: Explicit suffix, or None to derive one per combination.
        height_range: Elevation axis extent in metres, or None to read it per dataset.
        fit_k_values: Maximum component counts swept.
        fit_lambda_values: Component-count penalty weights swept.
        fit_modes: Fit modes swept, each naming the free components.
        fit_sigma_init_divisor: Divisor turning a peak half-width into the initial sigma in metres.
        fit_threshold_factor: Fraction of the profile maximum below which samples are ignored.
        fit_truncation_index: Elevation bin above which profiles are truncated.
        fit_prominence_frac: Peak prominence fraction required to seed a component.
        fit_activity_threshold: Amplitude below which a fitted component counts as inactive.
        adam_steps: Adam iterations per pixel batch.
        adam_lr: Adam learning rate.
        gpu_device_ids: GPU device indices available to the extraction workers.
        range_batch_size: Number of range lines loaded per batch.
        gpu_pixel_batch_size: Number of pixels fitted per GPU batch.
        parameter_workers: CPU worker processes writing the parameter chunks.
    """

    dataset_base_path : Path = Path("/ste/rnd/User/vice_vi/Dataset")
    dataset_filter    : list = field(default_factory=list)
    pyrat_directory   : Path = Path("/ste/rnd/User/vice_vi/pyrat")

    output_prefix : str          = "params"
    output_suffix : str | None   = None
    height_range  : tuple | None = None

    fit_k_values           : list  = field(default_factory=lambda: [5])
    fit_lambda_values      : list  = field(default_factory=lambda: [1e-2])
    fit_modes              : list  = field(default_factory=lambda: ["sigma", "sigma_amp", "sigma_amp_mu"])
    fit_sigma_init_divisor : float = 4.0
    fit_threshold_factor   : float = 0.25
    fit_truncation_index   : int   = 170
    fit_prominence_frac    : float = 0.05
    fit_activity_threshold : float = 1e-3

    adam_steps : int   = 3000
    adam_lr    : float = 2e-1

    gpu_device_ids       : list = field(default_factory=lambda: [0, 1, 2, 3])
    range_batch_size     : int  = 3500
    gpu_pixel_batch_size : int  = 24576
    parameter_workers    : int  = field(default_factory=lambda: min(64, os.cpu_count() or 16))


@dataclass
class ParamExtractionInferenceConfig:
    """Settings for analysing already-extracted parameter runs.

    Attributes:
        params_dir: Root directory holding the datasets whose parameter runs are analysed.
        run_tags: Parameter run directory names to analyse; empty selects all.
        make_plots: Whether the analysis figures are rendered.
        kz_grid_max: Upper end of the kz axis, in rad/m, of the resolution analysis.
        kz_grid_points: Number of kz samples on that axis.
        noise_coherence: Coherence used as the noise floor in the analytic resolution model.
    """

    params_dir : Path = Path("/ste/rnd/User/vice_vi/Dataset")
    run_tags   : list = field(default_factory=list)

    make_plots : bool = True

    kz_grid_max     : float = 5.0
    kz_grid_points  : int   = 256
    noise_coherence : float = 0.99


@dataclass
class InjectExternalParamsEntryConfig:
    """Settings for importing externally fitted parameter cubes into a dataset.

    Attributes:
        dataset_base_path: Root directory scanned for target datasets.
        dataset_filter: Substrings a dataset directory name must contain to be selected; empty selects all.
        source_files: Parameter arrays to import, in mosaic order.
        source_windows: Per-source crop windows locating each array in the dataset grid.
        source_order: Component order of the source channels, e.g. "mu_sigma_amp".
        output_prefix: Leading token of the written parameter run directory name.
        output_suffix: Suffix of the written parameter run directory name.
        origin_note: Free-text provenance recorded in the run metadata.
        k_slots: Number of Gaussian slots per pixel, or 0 to infer it from the sources.
        activity_threshold: Amplitude below which an imported component counts as inactive.
        overwrite: Whether an existing parameter run of the same name is replaced.
    """

    dataset_base_path : Path = Path("/ste/rnd/User/vice_vi/Dataset")
    dataset_filter    : list = field(default_factory=list)

    source_files   : list = field(default_factory=list)
    source_windows : list = field(default_factory=list)
    source_order   : str  = "mu_sigma_amp"

    output_prefix : str = "params"
    output_suffix : str = "external"
    origin_note   : str = ""

    k_slots            : int   = 0
    activity_threshold : float = 1e-3
    overwrite          : bool  = False
