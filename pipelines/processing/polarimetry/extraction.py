"""Reads the primary pass of a dataset in every polarisation inside the PyRat environment.

The generator resolves the dataset's F-SAR stack exactly as preprocessing did,
reads the primary's range-Doppler SLC with one single-channel PyRat call per
polarisation found on disk (HH, HV, VH, VV), lets ChannelOrdering form the Pauli
cross-polar component ((HV + VH) / sqrt 2 when both exist, sqrt 2 HV from a lone
HV), checks the raw HV read against the dataset's single-polarisation primary and
the VH channel against HV for reciprocity, and writes the array, its provenance
sidecar and the result JSON named by the specification.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np

from pipelines.processing.generation.base import GeneratorBase
from tools.data.io                        import FileIO
from tools.monitoring.logger              import Logger
from tools.sar.polarimetry                import ChannelOrdering, PolarimetricArtifact
from tools.sar.pyrat_env                  import PyRatEnvironment
from tools.sar.scene_extent               import PrimarySlcResolver


@dataclass
class LoadedChannels:
    """Polarimetric primary stack as delivered by the loader.

    Attributes:
        stack             : Complex array of shape (channels, azimuth, range).
        labels            : Channel label of every entry along the first axis.
        primary_directory : F-SAR pass directory the stack was read from.
        band              : Frequency band letter of the stack.
        product           : F-SAR product the channels were read from.
    """

    stack             : np.ndarray
    labels            : list
    primary_directory : str
    band              : str
    product           : str


class PolarimetricPrimaryLoader:
    """Reads the primary pass of an F-SAR stack in every polarisation on disk through PyRat.

    The stack is resolved from the F-SAR project CSV, the stack identifier and
    the track selection the dataset was built with, so the primary pass and the
    crop are the ones behind the dataset's own arrays. Every polarisation is
    loaded with the same single-channel call preprocessing uses for its
    primary, one call per channel, so nothing depends on how the PyRat copy in
    use labels or symmetrises multi-channel loads. Which polarisations exist is
    read from the RGI-SLC files of the pass, not from PyRat. Construction puts
    the PyRat checkout on the import path, so every later ``import pyrat`` in
    this class resolves.

    Attributes:
        PRODUCT          : F-SAR product the primary is read from, the range-Doppler SLC preprocessing itself uses.
        POLARISATIONS    : Channels looked for on disk, in load order.
        REQUIRED         : Channels that must exist for a Pauli decomposition.
        tomogram_config  : Tomogram configuration naming the project, base directory, track selection and polarisation.
        stack_identifier : ID column of the F-SAR project row selecting the stack.
        crop             : Crop as (azimuth_start, azimuth_end, range_start, range_end) in pixels.
        pyrat_directory  : Importable PyRat source root.
        threads          : PyRat thread count.
        logger           : Logger for progress reporting.
    """

    PRODUCT       = "RGI-SLC"
    POLARISATIONS = ("hh", "hv", "vh", "vv")
    REQUIRED      = ("hh", "hv", "vv")

    def __init__(self, tomogram_config, stack_identifier: str, crop: tuple, pyrat_directory: Path, threads: int, logger: Logger) -> None:
        """Binds the loader to one stack and crop and puts the PyRat checkout on the import path.

        Args:
            tomogram_config  : Tomogram configuration naming the project, base directory, track selection and polarisation.
            stack_identifier : ID column of the F-SAR project row selecting the stack.
            crop             : Crop as (azimuth_start, azimuth_end, range_start, range_end) in pixels.
            pyrat_directory  : Importable PyRat source root.
            threads          : PyRat thread count.
            logger           : Logger for progress reporting.
        """
        self.tomogram_config  = tomogram_config
        self.stack_identifier = str(stack_identifier)
        self.crop             = tuple(int(value) for value in crop)
        self.pyrat_directory  = Path(pyrat_directory)
        self.threads          = int(threads)
        self.logger           = logger

        PyRatEnvironment.ensure(self.pyrat_directory)

    def _stack(self):
        """Returns the PyRat FuSARtomo object naming the primary pass, band and crop."""
        from pyrat import pyrat_init, tomo

        pyrat_init(debug=False, nthreads=self.threads)

        return tomo.FuSARtomo(
            FuSARproject = self.tomogram_config.fusar_project_path,
            select       = self.tomogram_config.track_selection,
            id           = self.stack_identifier,
            basedir      = self.tomogram_config.base_directory,
            polarisation = self.tomogram_config.polarisation,
            crop         = list(self.crop),
        )

    def _available(self, primary_directory: str) -> list:
        """Returns the polarisations whose RGI-SLC file exists under the primary pass, in load order.

        Args:
            primary_directory : Pass directory of the primary acquisition.

        Returns:
            Lower-case polarisation codes present on disk, ordered as ``POLARISATIONS``.

        Raises:
            FileNotFoundError : If HH, HV or VV is missing, which leaves nothing to decompose.
        """
        on_disk = PrimarySlcResolver().polarisations(primary_directory)
        present = [polarisation for polarisation in self.POLARISATIONS if polarisation in on_disk]
        missing = [polarisation for polarisation in self.REQUIRED if polarisation not in on_disk]

        if missing:
            raise FileNotFoundError(f"The primary pass {primary_directory} has no RGI-SLC for {missing}; found {sorted(on_disk)} under {PrimarySlcResolver.PRODUCT_SUBDIR}, so there is nothing to decompose.")

        return present

    def _channel(self, stack, polarisation: str) -> np.ndarray:
        """Loads one polarisation of the primary with the call preprocessing uses for its single channel.

        Args:
            stack        : PyRat FuSARtomo object naming the primary pass, band and crop.
            polarisation : Two-letter polarisation code to load.

        Returns:
            Complex64 array of shape (azimuth, range).

        Raises:
            ValueError : If PyRat returns anything but a two-dimensional image.
        """
        import pyrat as pyrat_module
        from pyrat import getdata

        layer   = pyrat_module.load.fsar(stack.master, product=self.PRODUCT, polarisations=polarisation, bands=stack.band, crop=stack.crop, sym=True)
        channel = np.asarray(getdata(layer)).astype(np.complex64)

        if channel.ndim != 2:
            raise ValueError(f"PyRat returned shape {channel.shape} for polarisation '{polarisation}' of {stack.master}, expected (azimuth, range)")

        return channel

    def load(self) -> LoadedChannels:
        """Loads every polarisation on disk, one single-channel call each, over the dataset crop.

        Returns:
            The loaded channel stack labelled with the polarisation codes in load order.

        Raises:
            ValueError : If the channels do not share one (azimuth, range) grid.
        """
        stack         = self._stack()
        polarisations = self._available(stack.master)
        self.logger.subsection(f"[FSAR] Loading primary {stack.master} in {', '.join(polarisations)} over crop {self.crop}")

        channels = None

        for index, polarisation in enumerate(polarisations):
            channel = self._channel(stack, polarisation)

            if channels is None:
                channels = np.empty((len(polarisations),) + channel.shape, dtype=np.complex64)
            if channel.shape != channels.shape[1:]:
                raise ValueError(f"Polarisation '{polarisation}' of {stack.master} has shape {channel.shape} but '{polarisations[0]}' has {channels.shape[1:]}; the channels do not share one grid")

            channels[index] = channel
            self.logger.subsection(f"  {polarisation}: shape {channel.shape}")

        return LoadedChannels(stack=channels, labels=list(polarisations), primary_directory=str(stack.master), band=str(stack.band), product=self.PRODUCT)


class CrossPolarCheck:
    """Compares the freshly read HV channel against the dataset's single-polarisation primary.

    The dataset's primary.npy was read by PyRat for one polarisation with the
    single-channel call the loader repeats, so the raw HV channel the generator
    reads must equal it to within ``EXACT_RTOL`` of the primary's peak
    magnitude. Anything else means the two arrays do not describe the same
    pixels the same way: a coherence below ``MIN_COHERENCE`` points at a crop
    or track mismatch, a coherence above it at a pixel offset or another
    processing version of the same scene. Both stop the extraction before
    anything is written. The power ratio of the two arrays is reported so a
    wrongly scaled channel shows up in the message.

    Attributes:
        MIN_COHERENCE : Coherence magnitude separating a crop or track mismatch from a same-scene disagreement in the refusal message.
        EXACT_RTOL    : Largest deviation, relative to the primary's peak magnitude, still accepted as the same read.
        primary       : Single-polarisation primary of shape (azimuth, range).
        cross         : Raw HV channel of shape (azimuth, range) read by the loader.
    """

    MIN_COHERENCE = 0.5
    EXACT_RTOL    = 1e-4

    def __init__(self, primary: np.ndarray, cross: np.ndarray) -> None:
        """Stores the two images to compare.

        Args:
            primary : Single-polarisation primary of shape (azimuth, range).
            cross   : Raw HV channel of shape (azimuth, range) read by the loader.

        Raises:
            ValueError : If the two images differ in shape.
        """
        if primary.shape != cross.shape:
            raise ValueError(f"primary.npy has shape {primary.shape} but the loaded channels have shape {cross.shape}; the crop or the primary pass differs from the dataset's.")

        self.primary = np.asarray(primary, dtype=np.complex64)
        self.cross   = np.asarray(cross, dtype=np.complex64)

    def _relative_error(self) -> float:
        """Returns the largest deviation of the loaded channel from the primary, relative to the primary's peak magnitude."""
        peak = float(np.max(np.abs(self.primary)))
        if peak == 0.0:
            return float("inf")

        return float(np.max(np.abs(self.primary - self.cross)) / peak)

    def _coherence(self) -> float:
        """Returns the magnitude of the complex coherence between the two images over the whole crop."""
        cross_power = float(np.sum(np.abs(self.primary) ** 2)) * float(np.sum(np.abs(self.cross) ** 2))
        if cross_power == 0.0:
            return 0.0

        return float(np.abs(np.sum(self.primary * np.conj(self.cross))) / np.sqrt(cross_power))

    def _power_ratio(self) -> float:
        """Returns the mean power of the loaded channel over the mean power of the primary, infinite for an empty primary."""
        primary_power = float(np.mean(np.abs(self.primary) ** 2))
        if primary_power == 0.0:
            return float("inf")

        return float(np.mean(np.abs(self.cross) ** 2) / primary_power)

    def run(self) -> dict:
        """Verifies the loaded HV channel is the same read as the primary.

        Returns:
            Dict with ``match`` ("exact"), the ``coherence`` magnitude, the ``relative_error`` at the primary's peak and the ``power_ratio`` of the two images.

        Raises:
            ValueError : If the loaded channel deviates from the primary by more than ``EXACT_RTOL`` of its peak.
        """
        coherence = self._coherence()
        error     = self._relative_error()
        ratio     = self._power_ratio()

        if error > self.EXACT_RTOL:
            cause = "the crop or the primary pass does not match the dataset" if coherence < self.MIN_COHERENCE else "the same scene was read differently, such as a pixel offset or another processing version"
            raise ValueError(f"The loaded hv channel is not an exact read of primary.npy: relative error {error:.2e} at the primary's peak, coherence {coherence:.3f}, power ratio {ratio:.3f}; {cause}, so nothing is written.")

        return {"match": "exact", "coherence": coherence, "relative_error": error, "power_ratio": ratio}


class ReciprocityCheck:
    """Measures how well the HV and VH channels agree before they are averaged.

    Under reciprocity the two cross-polar channels image the same scattering,
    so their coherence sits near one and their mean powers agree. The check
    refuses channels that do not describe the same pixels at all; smaller
    disagreements are reported for the sidecar and the log.

    Attributes:
        MIN_COHERENCE  : Lowest coherence magnitude accepted between the two channels.
        WARN_COHERENCE : Coherence magnitude below which the generator warns.
        WARN_RATIO_DB  : Absolute VH over HV power ratio in dB above which the generator warns.
        POWER_FLOOR    : Floor applied to the mean channel powers so an empty channel still yields a finite ratio.
        hv             : HV channel of shape (azimuth, range).
        vh             : VH channel of shape (azimuth, range).
    """

    MIN_COHERENCE  = 0.5
    WARN_COHERENCE = 0.9
    WARN_RATIO_DB  = 1.0
    POWER_FLOOR    = 1e-12

    def __init__(self, hv: np.ndarray, vh: np.ndarray) -> None:
        """Stores the two cross-polar channels.

        Args:
            hv : HV channel of shape (azimuth, range).
            vh : VH channel of shape (azimuth, range).

        Raises:
            ValueError : If the two channels differ in shape.
        """
        if hv.shape != vh.shape:
            raise ValueError(f"The hv channel has shape {hv.shape} but vh has shape {vh.shape}; the channels do not share one grid.")

        self.hv = np.asarray(hv, dtype=np.complex64)
        self.vh = np.asarray(vh, dtype=np.complex64)

    def run(self) -> dict:
        """Measures the agreement of the two channels.

        Returns:
            Dict with the ``coherence`` magnitude, the VH over HV ``power_ratio_db``, the mean ``phase_deg`` between the channels and the ``residual`` power of their difference relative to HV.

        Raises:
            ValueError : If the coherence falls below ``MIN_COHERENCE``.
        """
        hv_power    = max(float(np.mean(np.abs(self.hv) ** 2)), self.POWER_FLOOR)
        vh_power    = max(float(np.mean(np.abs(self.vh) ** 2)), self.POWER_FLOOR)
        cross       = np.sum(self.hv * np.conj(self.vh))
        cross_power = float(np.sum(np.abs(self.hv) ** 2)) * float(np.sum(np.abs(self.vh) ** 2))
        coherence   = float(np.abs(cross) / np.sqrt(cross_power)) if cross_power > 0.0 else 0.0

        if coherence < self.MIN_COHERENCE:
            raise ValueError(f"The hv and vh channels have coherence {coherence:.3f}, below {self.MIN_COHERENCE}; they do not describe the same pixels, so the symmetrised cross-polar channel would be wrong.")

        return {
            "coherence"      : coherence,
            "power_ratio_db" : float(10.0 * np.log10(vh_power / hv_power)),
            "phase_deg"      : float(np.degrees(np.angle(cross))),
            "residual"       : float(np.mean(np.abs(self.hv - self.vh) ** 2) / hv_power),
        }


class PolarimetricPrimaryGenerator(GeneratorBase):
    """Runs the polarimetric primary extraction inside the PyRat environment from a JSON spec.

    Attributes:
        spec         : Specification naming the stack, crop, PyRat root, the dataset's primary and the output paths.
        logger       : Logger used by the generator.
        loader_class : Loader type built from (tomogram_config, stack_identifier, crop, pyrat_directory, threads, logger).
    """

    def __init__(self, spec: dict, logger: Logger, loader_class=PolarimetricPrimaryLoader) -> None:
        """Stores the specification, logger and loader type.

        Args:
            spec         : Specification dict.
            logger       : Logger used by the generator.
            loader_class : Loader type built from (tomogram_config, stack_identifier, crop, pyrat_directory, threads, logger).
        """
        super().__init__(spec, logger)
        self.loader_class = loader_class

    def _load(self) -> LoadedChannels:
        """Loads the primary pass in every polarisation over the dataset crop."""
        loader = self.loader_class(self._tomogram_config(), self.spec["stack_identifier"], tuple(self.spec["crop"]), Path(self.spec["pyrat_directory"]), self.spec["pyrat_threads"], self.logger)
        return loader.load()

    def _canonical(self, loaded: LoadedChannels) -> tuple:
        """Reorders the loaded channels into the artifact order.

        Args:
            loaded : Channel stack as delivered by the loader.

        Returns:
            Tuple of the canonical complex64 stack of shape (3, azimuth, range) and the ordering applied.
        """
        ordering = ChannelOrdering(loaded.labels)
        return ordering.canonical(loaded.stack), ordering

    def _check(self, loaded: LoadedChannels) -> dict:
        """Verifies the raw HV channel is the same read as the dataset's single-polarisation primary.

        Args:
            loaded : Channel stack as delivered by the loader.

        Returns:
            Result of ``CrossPolarCheck``.
        """
        labels  = [label.lower() for label in loaded.labels]
        primary = np.load(self.spec["primary_path"], mmap_mode="r")

        return CrossPolarCheck(np.asarray(primary), loaded.stack[labels.index("hv")]).run()

    def _reciprocity(self, loaded: LoadedChannels) -> dict | None:
        """Measures the agreement of HV and VH when both were read, warning on a weak one.

        Args:
            loaded : Channel stack as delivered by the loader.

        Returns:
            Result of ``ReciprocityCheck``, or None when the loader delivered no VH channel.
        """
        labels = [label.lower() for label in loaded.labels]
        if "vh" not in labels:
            return None

        result = ReciprocityCheck(loaded.stack[labels.index("hv")], loaded.stack[labels.index("vh")]).run()

        if result["coherence"] < ReciprocityCheck.WARN_COHERENCE or abs(result["power_ratio_db"]) > ReciprocityCheck.WARN_RATIO_DB:
            self.logger.warning(f"Weak reciprocity between hv and vh: coherence {result['coherence']:.3f}, VH/HV power {result['power_ratio_db']:+.2f} dB; the symmetrised cross-polar channel averages two channels that disagree.")

        return result

    def _sidecar(self, loaded: LoadedChannels, ordering: ChannelOrdering, check: dict, reciprocity: dict | None, shape: tuple) -> dict:
        """Builds the provenance sidecar written next to the artifact.

        Args:
            loaded      : Channel stack as delivered by the loader.
            ordering    : Channel ordering applied to the loader stack.
            check       : Result of the cross-polar check.
            reciprocity : Result of the reciprocity check, or None without a VH channel.
            shape       : Shape of the written array.

        Returns:
            Sidecar payload.
        """
        return {
            "channels"          : list(PolarimetricArtifact.CHANNELS),
            "loader_channels"   : list(loaded.labels),
            "cross_source"      : ordering.cross_source,
            "symmetrised"       : ordering.symmetrised,
            "product"           : loaded.product,
            "band"              : loaded.band,
            "primary_directory" : loaded.primary_directory,
            "crop"              : [int(value) for value in self.spec["crop"]],
            "shape"             : [int(value) for value in shape],
            "window"            : [int(value) for value in self.spec["window"]],
            "cross_polar_check" : check,
            "reciprocity_check" : reciprocity,
            "provenance"        : self.provenance(),
        }

    def _write(self, canonical: np.ndarray, sidecar: dict) -> None:
        """Writes the array and then its sidecar.

        Args:
            canonical : Canonical complex64 stack of shape (3, azimuth, range).
            sidecar   : Provenance sidecar payload.
        """
        artifact_path = Path(self.spec["artifact_path"])
        sidecar_path  = Path(self.spec["sidecar_path"])

        FileIO.ensure_dirs(artifact_path.parent, sidecar_path.parent)
        np.save(str(artifact_path), canonical, allow_pickle=False)
        FileIO.save_json(sidecar, sidecar_path)

        self.logger.subsection(f"Polarimetric primary saved : {artifact_path} (shape: {canonical.shape}, {canonical.nbytes / 1e6:.1f} MB)")
        self.logger.subsection(f"Sidecar saved              : {sidecar_path}")

    def run(self) -> dict:
        """Loads, orders, checks and writes the polarimetric primary, then writes the result JSON.

        Returns:
            Result payload with the written ``shape``, the ``loader_channels``, the ``cross_source``, the ``cross_polar_check``, the ``reciprocity_check`` and the generator ``provenance``.
        """
        self.logger.section(f"[Polarimetric primary] Crop {tuple(self.spec['crop'])}")

        loaded              = self._load()
        canonical, ordering = self._canonical(loaded)
        check               = self._check(loaded)
        reciprocity         = self._reciprocity(loaded)
        sidecar             = self._sidecar(loaded, ordering, check, reciprocity, canonical.shape)

        reciprocity_row = "n/a (lone hv)" if reciprocity is None else f"coherence {reciprocity['coherence']:.4f}, VH/HV {reciprocity['power_ratio_db']:+.2f} dB, phase {reciprocity['phase_deg']:.1f} deg"
        self.logger.kv_table({
            "Primary"         : loaded.primary_directory,
            "Loader channels" : ", ".join(loaded.labels),
            "Cross source"    : ordering.cross_source,
            "Cross check"     : f"{check['match']} against hv (coherence {check['coherence']:.4f}, relative error {check['relative_error']:.2e}, power ratio {check['power_ratio']:.3f})",
            "Reciprocity"     : reciprocity_row,
            "Shape"           : canonical.shape,
        }, title="Polarimetric primary")

        self._write(canonical, sidecar)

        result = {
            "shape"             : [int(value) for value in canonical.shape],
            "loader_channels"   : list(loaded.labels),
            "cross_source"      : ordering.cross_source,
            "cross_polar_check" : check,
            "reciprocity_check" : reciprocity,
            "provenance"        : sidecar["provenance"],
        }

        FileIO.save_json(result, Path(self.spec["result_path"]))
        self.logger.subsection(f"Polarimetric result written: {self.spec['result_path']}")

        return result
