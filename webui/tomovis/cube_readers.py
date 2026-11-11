"""Read halves of TomoVis's four File > Import callbacks.

The statements are those of ``importFuSARCallBack``, ``importUAVSARCallBack``,
``importNpyCallBack`` and ``importRATCallBack`` in TomoVis's visualizer.py, up
to the point where the window takes the data. Two sanctioned divergences:
hd5 attributes are parsed by the standalone scripts' ``parse_h5_attr``
(bytes decoded, strings through ``ast.literal_eval``, anything else passed
through) instead of ``eval`` (D-2), and the readers return values instead of
assigning window attributes, so the window commits a cube only when the whole
read succeeded and files are always closed (D-3).
"""

from __future__ import annotations

import ast

import h5py
import numpy as np

from tomovis.rat_file import RatReader
from web_logger       import WebLogger


class H5Attributes:
    """Parser of the string-encoded HDF5 attributes TomoVis files carry."""

    @staticmethod
    def parse(value):
        """Converts an attribute stored as bytes or a string into a Python object (parse_h5_attr).

        Args:
            value : Attribute value as h5py returns it.

        Returns:
            The literal the string holds, or the value itself when it is not text.
        """

        if isinstance(value, bytes):
            value = value.decode()
        if isinstance(value, str):
            return ast.literal_eval(value)
        return value


class FusarCube:
    """What a FuSAR Tomo .hd5 import yields.

    Attributes:
        data    : The cube as stored, dtype preserved.
        z_range : Elevation limits from ``elevation_limits`` or ``range``, None when neither attribute exists.
        x_res   : Azimuth pixel spacing from the root attribute ``ps_az``, None when absent.
        y_res   : Range pixel spacing from the root attribute ``ps_rg``, None when absent.
    """

    def __init__(self, data: np.ndarray, z_range, x_res, y_res) -> None:
        """Stores the read values."""

        self.data    = data
        self.z_range = z_range
        self.x_res   = x_res
        self.y_res   = y_res


class CubeReaders:
    """Reads the four import formats.

    Attributes:
        rat_reader : RAT reader.
    """

    def __init__(self, logger: WebLogger) -> None:
        """Builds the RAT reader.

        Args:
            logger : Console logger for the RAT reader's error lines.
        """

        self.rat_reader = RatReader(logger)

    def fusar(self, name: str) -> FusarCube:
        """Reads a FuSAR Tomo .hd5 file.

        The dataset is the second key, or the only one; elevation limits come
        from the dataset attribute ``elevation_limits``, else ``range``; pixel
        spacings from the root attributes ``ps_az`` and ``ps_rg``.

        Args:
            name : File path.

        Returns:
            The cube and its optional attributes.
        """

        with h5py.File(name, 'r') as h5f:
            index = 1
            if len(list(h5f.keys())) == 1:
                index = 0
            dataset = h5f[list(h5f.keys())[index]]
            data    = dataset[:]

            z_range = None
            if 'elevation_limits' in dataset.attrs:
                z_range = H5Attributes.parse(dataset.attrs['elevation_limits'])
            elif 'range' in dataset.attrs:
                z_range = H5Attributes.parse(dataset.attrs['range'])

            x_res = None
            if 'ps_az' in h5f.attrs:
                x_res = H5Attributes.parse(h5f.attrs['ps_az'])

            y_res = None
            if 'ps_rg' in h5f.attrs:
                y_res = H5Attributes.parse(h5f.attrs['ps_rg'])

        return FusarCube(data, z_range, x_res, y_res)

    def uavsar(self, name: str) -> np.ndarray:
        """Reads a UAVSAR Tomo .h5 file: the third key with axes 0 and 1 swapped.

        Args:
            name : File path.

        Returns:
            ``np.rollaxis(h5f[keys[2]][:], 1, 0)``.
        """

        with h5py.File(name, 'r') as h5f:
            return np.rollaxis(h5f[list(h5f.keys())[2]][:], 1, 0)

    def npy(self, name: str) -> np.ndarray:
        """Reads a .npy file with numpy's defaults (no pickles).

        Args:
            name : File path.

        Returns:
            The stored array.
        """

        return np.load(name)

    def rat(self, name: str) -> np.ndarray:
        """Reads a RAT 1.0 or 2.0 file.

        Args:
            name : File path.

        Returns:
            The stored array.
        """

        return self.rat_reader.rrat(name)
