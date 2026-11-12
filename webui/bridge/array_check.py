"""Header-only validation of the files a user picks to complete a dataset.

Every check opens the .npy as a read-only memmap, so even a large file is
judged by its header; only a DEM is read (it is 2-D) to make sure it holds a
finite height. A failed check raises ``PieceError`` with the exact sentence the
page shows under the piece's row.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from bridge.run_inspector import RunInspector


class PieceError(ValueError):
    """A piece the user tried to add was refused, with the sentence shown under its row.

    Attributes:
        piece : Key of the piece the error is about.
    """

    def __init__(self, message: str, piece: str) -> None:
        """Stores the message and the piece.

        Args:
            message : Plain sentence for the user.
            piece   : Piece key.
        """

        super().__init__(message)
        self.piece = piece


class ArrayCheck:
    """Validates picked .npy files against a dataset's footprint.

    Attributes:
        LABELS : Piece key to the label used in the messages.
    """

    LABELS = RunInspector.PIECE_LABELS

    def shape_text(self, shape: tuple) -> str:
        """Writes a shape as ``a x b x c``."""

        return " x ".join(str(int(n)) for n in shape)

    def reason(self, error: Exception) -> str:
        """Returns the plain cause of a read failure, without a closing period."""

        text = error.strerror if isinstance(error, OSError) and error.strerror else str(error)
        return text.rstrip(".")

    def npy(self, path: str, piece: str) -> np.ndarray:
        """Opens a picked .npy file read-only and checks it holds numbers in C order.

        Args:
            path  : Absolute path the user picked.
            piece : Piece key, for the messages.

        Returns:
            A read-only memmap of the file.

        Raises:
            PieceError : If the file is not a .npy, cannot be read, is Fortran-ordered or holds no real or complex numbers.
        """

        target = Path(path)
        name   = target.name
        if target.suffix.lower() != ".npy":
            raise PieceError(f"Pick a .npy file; {name} is not one.", piece)
        if not target.is_absolute():
            raise PieceError(f"Could not read {name}: the path is not absolute.", piece)

        try:
            array = np.load(target, mmap_mode="r")
        except (OSError, ValueError) as error:
            raise PieceError(f"Could not read {name}: {self.reason(error)}.", piece) from error

        if np.isfortran(array):
            raise PieceError(f"{name} is stored in Fortran order. Save it in C order (numpy.ascontiguousarray) and pick it again.", piece)
        if array.dtype.kind not in "iufc":
            raise PieceError(f"{name} holds {array.dtype} values; {self.LABELS[piece]} needs real or complex numbers.", piece)
        return array

    def plane(self, path: str, piece: str, footprint: tuple[int, int]) -> np.ndarray:
        """Checks a picked (azimuth, range) image covers the tomogram footprint.

        Args:
            path      : Absolute path the user picked.
            piece     : Piece key.
            footprint : (azimuth, range) of the tomogram.

        Returns:
            A read-only memmap of the file.

        Raises:
            PieceError : As ``npy``, or when the shape is not the footprint.
        """

        array = self.npy(path, piece)
        if tuple(array.shape) != tuple(footprint):
            raise PieceError(f"{self.LABELS[piece]} must be azimuth x range = {footprint[0]} x {footprint[1]} like the tomogram, but {Path(path).name} has shape {self.shape_text(array.shape)}.", piece)
        return array

    def dem(self, path: str, footprint: tuple[int, int]) -> np.ndarray:
        """Checks a picked DEM: real heights over the footprint, at least one of them finite.

        Args:
            path      : Absolute path the user picked.
            footprint : (azimuth, range) of the tomogram.

        Returns:
            A read-only memmap of the file.

        Raises:
            PieceError : As ``plane``, or when the DEM is complex or holds no finite height.
        """

        name  = Path(path).name
        array = self.npy(path, "dem")
        if array.dtype.kind == "c":
            raise PieceError(f"A DEM holds heights in metres, so it must be real; {name} is {array.dtype}.", "dem")

        array = self.plane(path, "dem", footprint)
        if not np.isfinite(array).any():
            raise PieceError(f"{name} holds no finite height.", "dem")
        return array

    def stack(self, path: str, footprint: tuple[int, int]) -> np.ndarray:
        """Checks a picked secondary stack: passes x azimuth x range over the footprint.

        Args:
            path      : Absolute path the user picked.
            footprint : (azimuth, range) of the tomogram.

        Returns:
            A read-only memmap of the file.

        Raises:
            PieceError : As ``npy``, or when the stack is not (n >= 1, azimuth, range).
        """

        array = self.npy(path, "passes")
        if array.ndim != 3 or array.shape[0] < 1 or tuple(array.shape[1:]) != tuple(footprint):
            raise PieceError(f"The pass stack must be passes x azimuth x range with azimuth x range = {footprint[0]} x {footprint[1]}; {Path(path).name} has shape {self.shape_text(array.shape)}.", "passes")
        return array

    def interferograms(self, path: str, secondaries: np.ndarray) -> np.ndarray:
        """Checks picked interferograms have the shape of the secondaries.

        Args:
            path        : Absolute path the user picked.
            secondaries : The checked secondary stack.

        Returns:
            A read-only memmap of the file.

        Raises:
            PieceError : As ``npy``, or when the shapes differ.
        """

        array = self.npy(path, "passes")
        if array.shape != secondaries.shape:
            raise PieceError(f"The interferograms must have the shape of the secondaries {self.shape_text(secondaries.shape)}; {Path(path).name} has shape {self.shape_text(array.shape)}.", "passes")
        return array

    def polarimetric(self, path: str, footprint: tuple[int, int]) -> np.ndarray:
        """Checks a picked polarimetric primary: complex, 3 x azimuth x range.

        Args:
            path      : Absolute path the user picked.
            footprint : (azimuth, range) of the tomogram.

        Returns:
            A read-only memmap of the file.

        Raises:
            PieceError : As ``npy``, or when the shape or the dtype is wrong.
        """

        name  = Path(path).name
        array = self.npy(path, "polarimetry")
        if tuple(array.shape) != (3, footprint[0], footprint[1]):
            raise PieceError(f"The polarimetric primary must be 3 x azimuth x range = 3 x {footprint[0]} x {footprint[1]} (channels HH, cross, VV); {name} has shape {self.shape_text(array.shape)}.", "polarimetry")
        if array.dtype.kind != "c":
            raise PieceError(f"The polarimetric primary must be complex; {name} is {array.dtype}.", "polarimetry")
        return array

    def parameters(self, folder: str, footprint: tuple[int, int]) -> int:
        """Checks a picked parameter run folder: parameters.npy (3k, azimuth, range) and a matching param_extraction_meta.json.

        Args:
            folder    : Absolute folder path the user picked.
            footprint : (azimuth, range) of the tomogram.

        Returns:
            k, the number of Gaussians.

        Raises:
            PieceError : If a file is missing, parameters.npy is not real, not (3k, azimuth, range) over the footprint, or k_max disagrees.
        """

        root = Path(folder)
        if not (root / "parameters.npy").is_file():
            raise PieceError(f"{root.name} holds no parameters.npy.", "params")
        if not (root / "param_extraction_meta.json").is_file():
            raise PieceError(f"{root.name} holds no param_extraction_meta.json.", "params")

        array = self.npy(str(root / "parameters.npy"), "params")
        if array.dtype.kind == "c":
            raise PieceError(f"parameters.npy holds {array.dtype} values; {self.LABELS['params']} needs real numbers.", "params")
        if array.ndim != 3 or array.shape[0] == 0 or array.shape[0] % 3 or tuple(array.shape[1:]) != tuple(footprint):
            raise PieceError(f"parameters.npy must be 3k x azimuth x range with azimuth x range = {footprint[0]} x {footprint[1]}; it has shape {self.shape_text(array.shape)}.", "params")

        k    = array.shape[0] // 3
        meta = json.loads((root / "param_extraction_meta.json").read_text(encoding="utf-8"))
        if int(meta["k_max"]) != k:
            raise PieceError(f"param_extraction_meta.json says k_max = {meta['k_max']}, but parameters.npy holds {k} Gaussians.", "params")
        return k
