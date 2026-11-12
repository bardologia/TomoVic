"""TomoVis link files: FuSAR Tomo hd5 files whose one dataset is stored in a .npy file.

TomoVis opens a TomoVic dataset through its own File > Import > hd5 route. The
link file holds a single dataset ``tomogram`` whose bytes live in the dataset's
C-ordered .npy (HDF5 external storage at the npy header offset, nothing is
copied), the height range as the dataset attributes ``elevation_limits`` and
``range`` that TomoVis and its scripts read, and the pixel spacing as the root
attributes ``ps_az`` and ``ps_rg``.
"""

from __future__ import annotations

from pathlib import Path

import h5py
import numpy as np

from bridge.dataset_record import AtomicWriter


class TomoVisLink:
    """Writes TomoVis link files.

    Attributes:
        writer          : Atomic writer the link is committed with.
        NAME            : File name of a dataset's link into its TomoVis cube.
        SCRIPTS_NAME    : File name of the link into the 3-D tomogram that the TomoVis scripts read, for multi-channel cubes.
        DATASET         : Name of the one dataset of a link file.
        DEFAULT_SPACING : Pixel spacing written when the dataset has none, TomoVis's own default.
    """

    NAME            = "tomovis.hd5"
    SCRIPTS_NAME    = "tomovis_scripts.hd5"
    DATASET         = "tomogram"
    DEFAULT_SPACING = (1.0, 1.0)

    def __init__(self, writer: AtomicWriter) -> None:
        """Stores the atomic writer.

        Args:
            writer : Atomic writer.
        """

        self.writer = writer

    def write(self, target: Path, cube: Path, height_range, spacing) -> Path:
        """Writes one link file atomically.

        Args:
            target       : Path of the link file.
            cube         : C-ordered .npy the link's dataset is stored in.
            height_range : (low, high) elevation in metres, or None when unknown (no z attributes are written).
            spacing      : (azimuth, range) pixel spacing in metres, or None for TomoVis's default 1.0 x 1.0.

        Returns:
            The target path.

        Raises:
            ValueError : If the cube is stored in Fortran order.
        """

        array = np.load(cube, mmap_mode="r")
        if np.isfortran(array):
            raise ValueError(f"{cube} is stored in Fortran order; a TomoVis link needs a C-ordered .npy")

        ps_az, ps_rg = self.DEFAULT_SPACING if spacing is None else spacing
        external     = [(str(Path(cube).resolve()), int(array.offset), int(array.nbytes))]
        temporary    = self.writer.temporary(target)

        with h5py.File(temporary, "w") as h5f:
            dataset = h5f.create_dataset(self.DATASET, shape=array.shape, dtype=array.dtype, external=external)
            if height_range is not None:
                limits = repr([float(height_range[0]), float(height_range[1])])
                dataset.attrs["elevation_limits"] = limits
                dataset.attrs["range"]            = limits
            h5f.attrs["ps_az"] = repr(float(ps_az))
            h5f.attrs["ps_rg"] = repr(float(ps_rg))

        return self.writer.commit(temporary, target)
