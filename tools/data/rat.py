"""Reading of version-2 RAT files without the full PyRAT stack.

Parses the 1000-byte RAT2 header into a shape and dtype, checks it against the
file size, and memory-maps parameter cubes so a window can be read without
loading the whole product.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib     import Path
from typing      import Tuple

import numpy as np


@dataclass
class RatSpec:
    """Array layout declared by a RAT file header.

    Attributes:
        shape: Array shape in NumPy order, slowest axis first.
        dtype: Element dtype the payload is stored in.
        header_size: Payload offset in bytes.
    """
    shape       : Tuple[int, ...]
    dtype       : np.dtype
    header_size : int

    @property
    def n_elements(self) -> int:
        """Total number of elements the array holds."""
        return int(np.prod(self.shape))

    @property
    def payload_size(self) -> int:
        """Payload size in bytes."""
        return self.n_elements * self.dtype.itemsize


class RatHeaderReader:
    """Parses and validates the header of a version-2 RAT file.

    Attributes:
        path: Path of the RAT file.
    """

    MAGIC       = b"RAT2"
    HEADER_SIZE = 1000
    MAX_DIMS    = 8

    NDIM_OFFSET  = 8
    SHAPE_OFFSET = 16
    VAR_OFFSET   = 48

    VAR_DTYPES = {
        1  : "u1",
        2  : "<i2",
        3  : "<i4",
        4  : "<f4",
        5  : "<f8",
        6  : "<c8",
        9  : "<c16",
        12 : "<u2",
        13 : "<u4",
        14 : "<i8",
        15 : "<u8",
    }

    def __init__(self, path: str | Path) -> None:
        """Binds the reader to a RAT file.

        Args:
            path: Path of the RAT file to parse.
        """
        self.path = Path(path)

    def _raw_header(self) -> bytes:
        """Returns the raw header bytes, checking the file length and the RAT2 magic."""
        if not self.path.is_file():
            raise FileNotFoundError(f"No RAT file at {self.path}")

        with open(self.path, "rb") as handle:
            raw = handle.read(self.HEADER_SIZE)

        if len(raw) < self.HEADER_SIZE:
            raise ValueError(f"RAT file {self.path} is {len(raw)} bytes, shorter than the {self.HEADER_SIZE}-byte header")

        if raw[:4] != self.MAGIC:
            raise ValueError(f"RAT file {self.path} starts with {raw[:4]!r}, not the {self.MAGIC.decode()} magic of a version-2 RAT file")

        return raw

    def _n_dimensions(self, raw: bytes) -> int:
        """Returns the declared dimension count, rejecting values outside the format's range."""
        ndim = int(np.frombuffer(raw, dtype="<i4", count=1, offset=self.NDIM_OFFSET)[0])

        if not 1 <= ndim <= self.MAX_DIMS:
            raise ValueError(f"RAT file {self.path} declares {ndim} dimensions, outside the 1..{self.MAX_DIMS} the format allows")

        return ndim

    def _shape(self, raw: bytes, ndim: int) -> Tuple[int, ...]:
        """Returns the array shape in NumPy order, reversing the header's fastest-first axes."""
        declared = np.frombuffer(raw, dtype="<i4", count=self.MAX_DIMS, offset=self.SHAPE_OFFSET)
        sizes    = [int(value) for value in declared[:ndim]]

        if any(size <= 0 for size in sizes):
            raise ValueError(f"RAT file {self.path} declares non-positive axis sizes {sizes}")

        return tuple(reversed(sizes))

    def _dtype(self, raw: bytes) -> np.dtype:
        """Returns the NumPy dtype of the declared variable-type code."""
        var = int(np.frombuffer(raw, dtype="<i4", count=1, offset=self.VAR_OFFSET)[0])

        if var not in self.VAR_DTYPES:
            raise ValueError(f"RAT file {self.path} declares variable type {var}, which is not one of the supported codes {sorted(self.VAR_DTYPES)}")

        return np.dtype(self.VAR_DTYPES[var])

    def _validate_size(self, spec: RatSpec) -> None:
        """Raises when the file size disagrees with the header-declared payload size."""
        expected = self.HEADER_SIZE + spec.payload_size
        actual   = self.path.stat().st_size

        if actual != expected:
            raise ValueError(f"RAT file {self.path} is {actual} bytes but its header describes {spec.shape} of {spec.dtype} which needs exactly {expected} bytes; the header parse and the payload disagree")

    def read(self) -> RatSpec:
        """Parses the header into a validated array layout.

        Returns:
            The declared shape, dtype and payload offset.

        Raises:
            FileNotFoundError: If the file does not exist.
            ValueError: If the magic, dimensions, shape, dtype or file size are inconsistent.
        """
        raw  = self._raw_header()
        ndim = self._n_dimensions(raw)
        spec = RatSpec(shape=self._shape(raw, ndim), dtype=self._dtype(raw), header_size=self.HEADER_SIZE)

        self._validate_size(spec)

        return spec


class RatCube:
    """Windowed reader over a 3-dimensional RAT parameter cube.

    Attributes:
        path: Path of the RAT file.
        spec: Array layout parsed from its header.
    """

    def __init__(self, path: str | Path) -> None:
        """Parses the header and checks the file holds a 3-dimensional cube.

        Args:
            path: Path of the RAT file.

        Raises:
            ValueError: If the array is not (channels, azimuth, range).
        """
        self.path = Path(path)
        self.spec = RatHeaderReader(self.path).read()

        if len(self.spec.shape) != 3:
            raise ValueError(f"RAT file {self.path} holds a {len(self.spec.shape)}-dimensional array of shape {self.spec.shape}; a parameter cube must be 3-dimensional (channels, azimuth, range)")

    @property
    def shape(self) -> Tuple[int, int, int]:
        """Cube shape as (channels, azimuth, range)."""
        return self.spec.shape

    @property
    def n_channels(self) -> int:
        """Number of parameter channels in the cube."""
        return self.spec.shape[0]

    @property
    def azimuth_size(self) -> int:
        """Number of azimuth lines in the cube."""
        return self.spec.shape[1]

    @property
    def range_size(self) -> int:
        """Number of range samples in the cube."""
        return self.spec.shape[2]

    def _memmap(self) -> np.memmap:
        """Returns a read-only memory map over the payload."""
        return np.memmap(str(self.path), dtype=self.spec.dtype, mode="r", offset=self.spec.header_size, shape=self.spec.shape)

    def channel_window(self, channel: int, azimuth: slice, range_: slice) -> np.ndarray:
        """Reads one azimuth-range window of a single channel.

        Args:
            channel: Parameter channel index.
            azimuth: Azimuth line slice to read.
            range_: Range sample slice to read.

        Returns:
            Contiguous float32 window of shape (azimuth span, range span).

        Raises:
            IndexError: If the channel is outside the cube.
        """
        if not 0 <= channel < self.n_channels:
            raise IndexError(f"RAT file {self.path} has {self.n_channels} channels; channel {channel} is out of range")

        return np.ascontiguousarray(self._memmap()[channel, azimuth, range_], dtype=np.float32)
