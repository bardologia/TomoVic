"""Predicts the vertical resolution attainable from a fitted profile set against kz.

Treats the fitted Gaussian mixtures as the parametrized vertical reflectivity, computes
the interferometric coherence they would produce at each vertical wavenumber kz (rad/m),
converts it into a phase-CRLB height error in metres, and ranks the candidate secondary
passes of the stack by that predicted error.
"""

from __future__ import annotations

import math

from pathlib import Path

import numpy as np

from tools.monitoring.logger  import Logger
from tools.sar.geometry_field import GeometryField


class ActiveGaussianTable:
    """Flattens a parameter stack into the pixels that carry at least one active Gaussian.

    Attributes:
        k_max: Number of Gaussian slots per pixel.
        n_pixels: Number of retained pixels.
        amplitudes: Slot amplitudes of shape (k_max, n_pixels).
        means: Slot centroid heights of shape (k_max, n_pixels), in metres.
        sigmas: Slot widths of shape (k_max, n_pixels), in metres.
        active: Boolean activity mask of shape (k_max, n_pixels).
    """

    def __init__(self, parameters_array: np.ndarray, k_max: int, amp_threshold: float) -> None:
        """Selects the pixels with an active Gaussian and splits the parameter families.

        Args:
            parameters_array: Parameter stack of shape (3 * k_max, azimuth, range).
            k_max: Number of Gaussian slots per pixel.
            amp_threshold: Amplitude above which a slot counts as active.

        Raises:
            ValueError: If no pixel carries an active Gaussian at that threshold.
        """
        flat   = parameters_array.reshape(3 * k_max, -1)
        active = flat[0::3] >= amp_threshold
        keep   = active.any(axis=0)

        if not keep.any():
            raise ValueError(f"No pixel carries an active Gaussian at amp_threshold {amp_threshold}; the resolution analysis has nothing to measure. Check the extractor output and the activity threshold.")

        self.k_max      = k_max
        self.n_pixels   = int(keep.sum())
        self.amplitudes = flat[0::3][:, keep]
        self.means      = flat[1::3][:, keep]
        self.sigmas     = flat[2::3][:, keep]
        self.active     = active[:, keep]

    def area_weights(self) -> np.ndarray:
        """Returns the area under each active Gaussian, of shape (k_max, n_pixels), zero elsewhere."""
        return np.where(self.active, self.amplitudes * np.abs(self.sigmas), 0.0)

    def pooled_sigmas(self) -> np.ndarray:
        """Returns the widths of every active Gaussian as a flat array, in metres."""
        return np.abs(self.sigmas[self.active])

    def adjacent_separations(self) -> np.ndarray:
        """Returns the centroid gaps between adjacent active slots as a flat array, in metres."""
        separations = []
        for k in range(self.k_max - 1):
            both = self.active[k] & self.active[k + 1]
            separations.append(np.abs(self.means[k + 1, both] - self.means[k, both]))

        return np.concatenate(separations) if separations else np.zeros(0)

    def vertical_extents(self) -> np.ndarray:
        """Returns the per-pixel two-sigma vertical extent of shape (n_pixels,), in metres."""
        lower = np.where(self.active, self.means - 2.0 * np.abs(self.sigmas),  np.inf)
        upper = np.where(self.active, self.means + 2.0 * np.abs(self.sigmas), -np.inf)

        return upper.max(axis=0) - lower.min(axis=0)


class KzCoherenceModel:
    """Evaluates the interferometric coherence a fitted mixture produces at each kz.

    The coherence is the area-weighted Fourier transform of the vertical reflectivity,
    so each Gaussian contributes a Gaussian attenuation in kz and a phase set by its
    centroid height.

    Attributes:
        table: Active-Gaussian table supplying the mixtures.
    """

    CHUNK = 16384

    def __init__(self, table: ActiveGaussianTable) -> None:
        """Binds the model to an active-Gaussian table."""
        self.table = table

    def magnitudes(self, kz_grid: np.ndarray, pixel_indices: np.ndarray) -> np.ndarray:
        """Computes the coherence magnitude of each selected pixel over the kz grid.

        Args:
            kz_grid: Vertical wavenumbers of shape (n_kz,), in rad/m.
            pixel_indices: Indices of shape (n_selected,) into the table's pixel axis.

        Returns:
            Coherence magnitude of shape (n_kz, n_selected), clipped to [0, 1].
        """
        weights = self.table.area_weights()[:, pixel_indices]
        means   = self.table.means[:, pixel_indices]
        sigmas  = np.abs(self.table.sigmas[:, pixel_indices])

        kz     = kz_grid[:, None]
        result = np.empty((kz_grid.shape[0], pixel_indices.shape[0]), dtype=np.float32)

        for start in range(0, pixel_indices.shape[0], self.CHUNK):
            stop        = min(start + self.CHUNK, pixel_indices.shape[0])
            numerator   = np.zeros((kz_grid.shape[0], stop - start), dtype=np.complex64)
            denominator = np.zeros(stop - start, dtype=np.float64)

            for k in range(self.table.k_max):
                w            = weights[k, start:stop]
                attenuation  = np.exp(-0.5 * (kz * sigmas[k, start:stop]) ** 2)
                numerator   += (w * attenuation * np.exp(1j * kz * means[k, start:stop])).astype(np.complex64)
                denominator += w

            result[:, start:stop] = (np.abs(numerator) / np.maximum(denominator, 1e-12)).astype(np.float32)

        return np.clip(result, 0.0, 1.0)


class SecondaryKzTable:
    """Places the stack's candidate secondary passes on the kz axis.

    Attributes:
        path: Geometry field path inside the dataset's ``meta`` directory.
        logger: Logger for the load report.
    """

    FILENAME = GeometryField.FILENAME

    def __init__(self, dataset_dir: Path, logger: Logger) -> None:
        """Binds the table to a preprocessed dataset directory.

        Args:
            dataset_dir: Dataset root holding ``meta/`` with the geometry field.
            logger: Logger for the load report.
        """
        self.path   = Path(dataset_dir) / "meta" / self.FILENAME
        self.logger = logger

    def load(self) -> dict:
        """Returns the scene-mean absolute kz of every secondary pass, in rad/m.

        Returns:
            Mapping from pass label to its mean absolute kz in rad/m, excluding the
            reference pass.

        Raises:
            FileNotFoundError: If the preprocessing geometry field is missing.
        """
        if not self.path.is_file():
            raise FileNotFoundError(f"{self.path} does not exist; the kz-resolution analysis needs the preprocessing geometry field to place the candidate secondaries on the kz axis. Re-run preprocessing to generate it.")

        field   = GeometryField.load(self.path)
        kz_mean = field.kz("height").mean(axis=(1, 2))

        table = {label: abs(float(kz_mean[index])) for index, label in enumerate(field.labels) if label != field.reference}

        self.logger.subsection(f"Candidate secondaries : {len(table)} passes, kz {min(table.values()):.3f} - {max(table.values()):.3f} rad/m")
        return table


class ResolutionAnalyzer:
    """Turns a fitted parameter stack into kz-resolution curves and a pass ranking.

    Attributes:
        logger: Logger for the analysis report.
        noise_coherence: Speckle/SNR coherence ceiling applied on top of the profile coherence.
        table: Active-Gaussian table derived from the parameter stack.
        passes: Loader placing the candidate secondaries on the kz axis.
        kz_grid: Evaluated vertical wavenumbers of shape (kz_grid_points,), in rad/m.
    """

    MAX_QUANTILE_PIXELS = 200000
    QUANTILE_KEYS       = (25, 50, 75, 95)

    def __init__(self, parameters_array: np.ndarray, meta: dict, dataset_dir: Path, logger: Logger, kz_grid_max: float = 5.0, kz_grid_points: int = 256, noise_coherence: float = 0.99) -> None:
        """Builds the active-Gaussian table and the kz grid the analysis runs on.

        Args:
            parameters_array: Parameter stack of shape (3 * k_max, azimuth, range).
            meta: Run metadata carrying ``k_max`` and ``activity_threshold``.
            dataset_dir: Dataset root holding the preprocessing geometry field.
            logger: Logger for the analysis report.
            kz_grid_max: Upper end of the evaluated kz axis, in rad/m.
            kz_grid_points: Number of samples on the kz axis.
            noise_coherence: Speckle/SNR coherence ceiling in (0, 1].

        Raises:
            ValueError: If ``noise_coherence`` lies outside (0, 1].
        """
        if not 0.0 < noise_coherence <= 1.0:
            raise ValueError(f"noise_coherence must lie in (0, 1], got {noise_coherence}; it models the speckle/SNR decorrelation a real pair carries on top of the profile coherence.")

        self.logger          = logger
        self.noise_coherence = noise_coherence
        self.table           = ActiveGaussianTable(parameters_array, int(meta["k_max"]), float(meta["activity_threshold"]))
        self.passes          = SecondaryKzTable(dataset_dir, logger)
        self.kz_grid         = np.linspace(kz_grid_max / kz_grid_points, kz_grid_max, kz_grid_points, dtype=np.float64)

    def pixel_subsample(self) -> np.ndarray:
        """Returns evenly strided pixel indices capped at ``MAX_QUANTILE_PIXELS``."""
        stride = max(1, math.ceil(self.table.n_pixels / self.MAX_QUANTILE_PIXELS))
        return np.arange(0, self.table.n_pixels, stride)

    def coherence_curves(self, pixel_indices: np.ndarray) -> dict:
        """Computes the coherence and phase-CRLB height-error quantiles over the kz grid.

        Args:
            pixel_indices: Indices of shape (n_selected,) into the table's pixel axis.

        Returns:
            Mapping with the median and quartile curves of the coherence magnitude and of
            the height error in metres, each of shape (kz_grid_points,).
        """
        magnitudes, errors = self.error_samples(self.kz_grid, pixel_indices)

        return {
            "coh_median" : np.median(magnitudes, axis=1),
            "coh_q25"    : np.percentile(magnitudes, 25, axis=1),
            "coh_q75"    : np.percentile(magnitudes, 75, axis=1),
            "err_median" : np.median(errors, axis=1),
            "err_q25"    : np.percentile(errors, 25, axis=1),
            "err_q75"    : np.percentile(errors, 75, axis=1),
        }

    def aliasing_curve(self) -> tuple:
        """Measures how often the profile extent exceeds the height of ambiguity.

        Returns:
            Tuple of the aliased pixel fraction of shape (kz_grid_points,) and the
            per-pixel two-sigma vertical extents in metres.
        """
        extents   = self.table.vertical_extents()
        ambiguity = 2.0 * np.pi / self.kz_grid

        ordered  = np.sort(extents)
        fraction = 1.0 - np.searchsorted(ordered, ambiguity, side="right") / ordered.size

        return fraction, extents

    def detail_scales(self, extents: np.ndarray) -> dict:
        """Summarises the vertical scales present and the kz each of them demands.

        Args:
            extents: Per-pixel two-sigma vertical extents of shape (n_pixels,), in metres.

        Returns:
            Mapping with the counts and quantiles of the widths, separations and extents
            in metres, plus the kz in rad/m implied by the median width, median
            separation and the extents at the 50th and 95th percentiles.
        """
        sigmas      = self.table.pooled_sigmas()
        separations = self.table.adjacent_separations()

        scales = {"n_active_gaussians": int(sigmas.shape[0]), "n_separations": int(separations.shape[0])}
        for name, sample in (("sigma", sigmas), ("separation", separations), ("extent", extents)):
            for q in self.QUANTILE_KEYS:
                scales[f"{name}_q{q}"] = float(np.percentile(sample, q)) if sample.size else float("nan")

        scales["kz_width_median"]     = float(1.0 / max(scales["sigma_q50"], 1e-9))
        scales["kz_separation_median"] = float(np.pi / max(scales["separation_q50"], 1e-9)) if separations.size else float("nan")
        scales["kz_unambiguous_p95"]  = float(2.0 * np.pi / max(scales["extent_q95"], 1e-9))
        scales["kz_unambiguous_p50"]  = float(2.0 * np.pi / max(scales["extent_q50"], 1e-9))

        return scales

    def pass_ranking(self, pixel_indices: np.ndarray, pass_table: dict) -> list:
        """Ranks the candidate secondaries by their exact predicted height error.

        Evaluates the coherence model directly at each pass kz rather than interpolating
        the analysis grid, so a near-zero-baseline pass below the grid floor still
        receives its true, very large error and ranks last instead of aborting the run.

        Args:
            pixel_indices: Indices of shape (n_selected,) into the table's pixel axis.
            pass_table: Mapping from pass label to its mean absolute kz, in rad/m.

        Returns:
            List of rows with the pass label, its kz in rad/m and its predicted height
            error in metres, sorted by increasing error.

        Raises:
            ValueError: If a candidate pass has non-positive kz, where the phase-CRLB
                height error is undefined.
        """
        degenerate = {label: kz for label, kz in pass_table.items() if kz <= 0.0}
        if degenerate:
            raise ValueError(f"Candidate secondaries {degenerate} have a non-positive mean absolute kz; the phase-CRLB height error diverges at kz = 0. Inspect the preprocessing geometry field for a duplicated or corrupt pass.")

        labels    = list(pass_table.keys())
        kz_values = np.array([pass_table[label] for label in labels], dtype=np.float64)
        _, errors = self.error_samples(kz_values, pixel_indices)
        medians   = np.median(errors, axis=1)

        ranked = [{"label": label, "kz": float(kz), "predicted_height_error": float(error)} for label, kz, error in zip(labels, kz_values, medians)]
        ranked.sort(key=lambda row: row["predicted_height_error"])
        return ranked

    def error_samples(self, kz_values: np.ndarray, pixel_indices: np.ndarray) -> tuple:
        """Evaluates the coherence model and the phase-CRLB height error at the given kz.

        Args:
            kz_values: Vertical wavenumbers of shape (n_kz,), in rad/m, all positive.
            pixel_indices: Indices of shape (n_selected,) into the table's pixel axis.

        Returns:
            Tuple of the coherence magnitudes and the height errors in metres, each of
            shape (n_kz, n_selected).
        """
        magnitudes = KzCoherenceModel(self.table).magnitudes(kz_values, pixel_indices)

        total  = np.clip(self.noise_coherence * magnitudes, 1e-4, 1.0 - 1e-9)
        errors = np.sqrt(1.0 - total ** 2) / (total * kz_values[:, None])

        return magnitudes, errors

    def run(self) -> tuple:
        """Runs the full kz-resolution analysis.

        Returns:
            Tuple of the summary dictionary, carrying the optimum kz in rad/m, the values
            attained there, the vertical scales and the pass ranking, and the array
            dictionary holding the kz grid and every curve evaluated over it.
        """
        self.logger.subsection("Analysing parametrized-profile vertical resolution against kz")

        pixel_indices    = self.pixel_subsample()
        curves           = self.coherence_curves(pixel_indices)
        aliased, extents = self.aliasing_curve()
        scales           = self.detail_scales(extents)
        pass_table       = self.passes.load()
        ranking          = self.pass_ranking(pixel_indices, pass_table)

        optimum_index = int(np.argmin(curves["err_median"]))

        summary = {
            "n_pixels_used"          : int(pixel_indices.shape[0]),
            "noise_coherence"        : float(self.noise_coherence),
            "kz_grid_max"            : float(self.kz_grid[-1]),
            "kz_grid_points"         : int(self.kz_grid.shape[0]),
            "kz_optimum"             : float(self.kz_grid[optimum_index]),
            "err_at_optimum"         : float(curves["err_median"][optimum_index]),
            "coherence_at_optimum"   : float(curves["coh_median"][optimum_index]),
            "aliased_frac_at_optimum": float(aliased[optimum_index]),
            "best_pass"              : ranking[0]["label"],
            "best_pass_kz"           : ranking[0]["kz"],
            "pass_ranking"           : ranking,
            **scales,
        }

        arrays = {
            "kz_grid"          : self.kz_grid,
            "aliased_fraction" : aliased,
            "pass_labels"      : np.array(list(pass_table.keys())),
            "pass_kz"          : np.array(list(pass_table.values()), dtype=np.float64),
            **curves,
        }

        self.logger.subsection(f"Predicted optimum kz : {summary['kz_optimum']:.3f} rad/m (best candidate pass: {summary['best_pass']} at {summary['best_pass_kz']:.3f})")
        return summary, arrays


class ResolutionArtifactWriter:
    """Persists the kz-resolution curves of a parameter run.

    Attributes:
        run_dir: Parameter run directory the archive is written into.
        logger: Logger for the write confirmation.
    """

    CURVES_FILENAME = "resolution_curves.npz"

    def __init__(self, run_dir: Path, logger: Logger) -> None:
        """Binds the writer to a parameter run directory.

        Args:
            run_dir: Parameter run directory the archive is written into.
            logger: Logger for the write confirmation.
        """
        self.run_dir = Path(run_dir)
        self.logger  = logger

    def save(self, arrays: dict) -> Path:
        """Writes the resolution curve arrays into a compressed .npz archive.

        Args:
            arrays: Mapping from curve name to array over the kz grid, in rad/m.

        Returns:
            Path of the written archive.
        """
        path = self.run_dir / self.CURVES_FILENAME
        np.savez_compressed(path, **arrays)

        self.logger.subsection(f"-> Resolution curves written: {path}")
        return path
