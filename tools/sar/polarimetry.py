"""Pauli decomposition of a polarimetric primary SLC.

Provides the artifact contract a preprocessing run follows when it carries the
primary pass in every polarisation, the reordering of a loader's channel stack
into that contract, and the decomposition itself: the Pauli scattering vector,
its multilooked powers, the co-polar powers behind the channel ratios, the
no-data mask, the mechanism fractions and the display composites the Cube tab
renders.
"""

from __future__ import annotations

from typing import Dict, Tuple

import numpy as np

from tools.sar.coherence import ComplexSmoother


class PolarimetricArtifact:
    """Contract of the polarimetric primary artifact a preprocessing run may carry.

    The array holds the primary pass in three Pauli-ready channels, in the order
    of ``CHANNELS``: the co-polar HH and VV channels as delivered, and a
    cross-polar channel scaled so that it equals the third Pauli component
    directly, which is sqrt(2) S_HV under reciprocity. The extraction forms it
    as (HV + VH) / sqrt(2) when the loader delivers both cross-polar channels
    and as sqrt(2) HV when it delivers HV alone.

    Attributes:
        ARTIFACT_KEY : Key of the artifact inside the ``artifacts`` mapping of dataset.json.
        FILENAME     : File name of the complex64 array of shape (3, azimuth, range) under data/.
        SIDECAR      : File name of the provenance sidecar under meta/.
        CHANNELS     : Channel order along the first axis of the array.
        CROSS_SCALE  : Factor turning a plain HV channel into the Pauli cross-polar component.
    """

    ARTIFACT_KEY = "primary_polarimetric"
    FILENAME     = "primary_polarimetric.npy"
    SIDECAR      = "primary_polarimetric.json"
    CHANNELS     = ("hh", "xx", "vv")
    CROSS_SCALE  = float(np.sqrt(2.0))


class ChannelOrdering:
    """Maps a loader's channel stack onto the artifact channel order.

    The loader delivers the cross-polar channel as the separate ``hv`` and
    ``vh`` channels or as ``hv`` alone; both are turned into the Pauli
    cross-polar component sqrt(2) S_HV. A lone ``vh`` is refused on purpose:
    the loader always reads HV, and the extraction's alignment check against
    the dataset's single-polarisation primary needs that channel.

    Attributes:
        labels       : Lower-cased channel labels of the loader stack, in stack order.
        cross_source : How the cross-polar component is formed, "hv+vh" or "hv".
    """

    def __init__(self, labels) -> None:
        """Validates the loader labels and decides how the cross-polar component is formed.

        Args:
            labels : Channel labels of the loader stack, in stack order; case is ignored.

        Raises:
            ValueError : If HH, VV or HV is absent or repeated.
        """
        self.labels = [str(label).lower() for label in labels]

        for required in ("hh", "vv", "hv"):
            if self.labels.count(required) != 1:
                raise ValueError(f"Channel '{required}' must appear exactly once in the loader stack, got labels {self.labels}.")

        if self.labels.count("vh") == 1:
            self.cross_source = "hv+vh"
        elif self.labels.count("vh") == 0:
            self.cross_source = "hv"
        else:
            raise ValueError(f"Channel 'vh' must appear at most once in the loader stack, got labels {self.labels}.")

    @property
    def symmetrised(self) -> bool:
        """Whether the cross-polar component averages the HV and VH channels."""
        return self.cross_source == "hv+vh"

    def _cross(self, stack: np.ndarray) -> np.ndarray:
        """Returns the Pauli cross-polar component formed from the loader stack.

        Args:
            stack : Loader stack of shape (channels, azimuth, range).

        Returns:
            Complex array of shape (azimuth, range) equal to sqrt(2) S_HV under reciprocity.
        """
        if self.cross_source == "hv+vh":
            return (stack[self.labels.index("hv")] + stack[self.labels.index("vh")]) / PolarimetricArtifact.CROSS_SCALE

        return stack[self.labels.index("hv")] * PolarimetricArtifact.CROSS_SCALE

    def canonical(self, stack: np.ndarray) -> np.ndarray:
        """Returns the loader stack in artifact channel order.

        Args:
            stack : Loader stack of shape (channels, azimuth, range), one entry per label.

        Returns:
            Complex64 array of shape (3, azimuth, range) ordered as ``PolarimetricArtifact.CHANNELS``.

        Raises:
            ValueError : If the stack is not three-dimensional or its channel count differs from the label count.
        """
        if stack.ndim != 3 or stack.shape[0] != len(self.labels):
            raise ValueError(f"Loader stack of shape {stack.shape} does not match the {len(self.labels)} labels {self.labels}.")

        hh    = stack[self.labels.index("hh")]
        vv    = stack[self.labels.index("vv")]
        cross = self._cross(stack)

        return np.stack([hh, cross, vv]).astype(np.complex64)


class PauliDecomposer:
    """Forms the Pauli scattering vector of a canonical stack and its multilooked powers.

    Component order follows ``COMPONENTS``: the surface (odd-bounce) term
    (HH + VV) / sqrt(2), the double-bounce (even-bounce) term (HH - VV) / sqrt(2)
    and the volume term, which is the cross-polar channel itself. Powers are
    the squared magnitudes averaged over a boxcar window, trading speckle for
    resolution the same way the covariance window of the tomogram does. The
    basis is unitary, so the three powers sum to the span
    |HH|^2 + 2 |S_HV|^2 + |VV|^2 at every pixel.

    Attributes:
        COMPONENTS : Component keys in vector order.
        RGB_ORDER  : Component keys painted into the red, green and blue channels of the composite.
        DB_FLOOR   : Power floor applied before the logarithm; a window whose span lies at or below it holds no data.
        PERCENTILE : Lower and upper percentiles bounding every colour stretch.
        window     : Boxcar size in pixels as (azimuth, range).
        smoother   : Boxcar averaging the component powers.
    """

    COMPONENTS = ("surface", "double", "volume")
    RGB_ORDER  = ("double", "volume", "surface")
    DB_FLOOR   = 1e-12
    PERCENTILE = (1.0, 99.0)

    def __init__(self, window: Tuple[int, int]) -> None:
        """Builds the decomposer around a multilook window.

        Args:
            window : Boxcar size in pixels as (azimuth, range); (1, 1) keeps single-look powers.
        """
        self.window   = (int(window[0]), int(window[1]))
        self.smoother = ComplexSmoother(self.window)

    @staticmethod
    def vector(stack: np.ndarray) -> np.ndarray:
        """Returns the Pauli scattering vector of a canonical stack.

        Args:
            stack : Complex array of shape (3, azimuth, range) ordered as ``PolarimetricArtifact.CHANNELS``.

        Returns:
            Complex64 array of shape (3, azimuth, range) ordered as ``COMPONENTS``.

        Raises:
            ValueError : If the stack does not carry exactly three channels.
        """
        if stack.ndim != 3 or stack.shape[0] != 3:
            raise ValueError(f"Expected a canonical stack of shape (3, azimuth, range), got {stack.shape}.")

        hh    = stack[0]
        cross = stack[1]
        vv    = stack[2]

        surface = (hh + vv) / PolarimetricArtifact.CROSS_SCALE
        double  = (hh - vv) / PolarimetricArtifact.CROSS_SCALE

        return np.stack([surface, double, cross]).astype(np.complex64)

    def _multilook(self, channels: np.ndarray) -> np.ndarray:
        """Returns the boxcar mean of the squared magnitude of every channel.

        Args:
            channels : Complex array of shape (n, azimuth, range).

        Returns:
            Float32 array of the same shape holding the boxcar-averaged squared magnitudes.
        """
        powers = np.empty(channels.shape, dtype=np.float32)

        for index in range(channels.shape[0]):
            squared       = (channels[index].real ** 2 + channels[index].imag ** 2).astype(np.float32)
            powers[index] = self.smoother.smooth(squared)

        return powers

    def powers(self, stack: np.ndarray) -> np.ndarray:
        """Returns the multilooked power of every Pauli component.

        Args:
            stack : Complex array of shape (3, azimuth, range) ordered as ``PolarimetricArtifact.CHANNELS``.

        Returns:
            Float32 array of shape (3, azimuth, range) holding the boxcar-averaged squared magnitudes, ordered as ``COMPONENTS``.
        """
        return self._multilook(self.vector(stack))

    def copolar_powers(self, stack: np.ndarray) -> np.ndarray:
        """Returns the multilooked power of the two co-polar channels.

        The co-polar ratio HH/VV cannot be recovered from the Pauli powers,
        whose first two entries only carry |HH|^2 + |VV|^2 and the real part of
        HH VV*, so the explorer keeps these two maps next to them.

        Args:
            stack : Complex array of shape (3, azimuth, range) ordered as ``PolarimetricArtifact.CHANNELS``.

        Returns:
            Float32 array of shape (2, azimuth, range) holding the boxcar-averaged |HH|^2 and |VV|^2.

        Raises:
            ValueError : If the stack does not carry exactly three channels.
        """
        if stack.ndim != 3 or stack.shape[0] != 3:
            raise ValueError(f"Expected a canonical stack of shape (3, azimuth, range), got {stack.shape}.")

        return self._multilook(np.stack([stack[0], stack[2]]))

    @classmethod
    def valid(cls, powers: np.ndarray) -> np.ndarray:
        """Returns the mask of pixels whose multilook window holds any non-zero sample.

        Args:
            powers : Float array of shape (3, azimuth, range) of component powers.

        Returns:
            Boolean array of shape (azimuth, range), False over zero-filled scene margins.
        """
        return powers.sum(axis=0) > cls.DB_FLOOR

    @classmethod
    def decibel(cls, powers: np.ndarray) -> np.ndarray:
        """Returns the powers in decibels, floored at ``DB_FLOOR`` before the logarithm."""
        return (10.0 * np.log10(np.maximum(powers, cls.DB_FLOOR))).astype(np.float32)

    @classmethod
    def fractions(cls, powers: np.ndarray) -> np.ndarray:
        """Returns the share of the span each component carries.

        Args:
            powers : Float array of shape (3, azimuth, range) of component powers.

        Returns:
            Float32 array of the same shape whose three entries sum to one where ``valid`` holds and are zero elsewhere.
        """
        span = np.maximum(powers.sum(axis=0, keepdims=True), cls.DB_FLOOR)
        return np.where(span > cls.DB_FLOOR, powers / span, 0.0).astype(np.float32)

    @classmethod
    def dominant(cls, powers: np.ndarray) -> np.ndarray:
        """Returns the index into ``COMPONENTS`` of the strongest component at every pixel.

        Args:
            powers : Float array of shape (3, azimuth, range) of component powers.

        Returns:
            Int8 array of shape (azimuth, range), -1 where the pixel holds no data.
        """
        return np.where(cls.valid(powers), np.argmax(powers, axis=0), -1).astype(np.int8)

    @classmethod
    def stretch_bounds(cls, powers_db: np.ndarray, shared: bool, valid: np.ndarray) -> Dict[str, Tuple[float, float]]:
        """Returns the decibel range every component is stretched over.

        Args:
            powers_db : Float array of shape (3, azimuth, range) of component powers in decibels.
            shared    : Whether one range pooled over all components is used, so the composite hue follows the true power balance; otherwise each component takes its own percentiles.
            valid     : Boolean mask of shape (azimuth, range) of the pixels the percentiles are taken over.

        Returns:
            Mapping of component key to (low, high) decibel bounds; a degenerate range is widened by one decibel.

        Raises:
            ValueError : If no pixel is valid, so there is nothing to stretch over.
        """
        if not np.any(valid):
            raise ValueError("No valid pixel to stretch the Pauli powers over; every multilook window of the map holds no data.")

        pooled = powers_db[:, valid]
        bounds = {}

        if shared:
            low, high = np.percentile(pooled, cls.PERCENTILE)
            for key in cls.COMPONENTS:
                bounds[key] = (float(low), float(high))
        else:
            for index, key in enumerate(cls.COMPONENTS):
                low, high   = np.percentile(pooled[index], cls.PERCENTILE)
                bounds[key] = (float(low), float(high))

        for key, (low, high) in bounds.items():
            if not high > low:
                bounds[key] = (low - 0.5, high + 0.5)

        return bounds

    @classmethod
    def composite(cls, powers_db: np.ndarray, bounds: Dict[str, Tuple[float, float]]) -> np.ndarray:
        """Returns the Pauli RGB composite: red double bounce, green volume, blue surface.

        Args:
            powers_db : Float array of shape (3, azimuth, range) of component powers in decibels.
            bounds    : Decibel range of every component, as returned by ``stretch_bounds``.

        Returns:
            Float32 array of shape (azimuth, range, 3) with values in [0, 1]; a no-data pixel at the decibel floor paints black.
        """
        channels = []

        for key in cls.RGB_ORDER:
            index     = cls.COMPONENTS.index(key)
            low, high = bounds[key]
            channels.append(np.clip((powers_db[index] - low) / (high - low), 0.0, 1.0))

        return np.stack(channels, axis=-1).astype(np.float32)
