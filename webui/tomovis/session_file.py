"""The TomoVis session file (.hd5), written and read with the h5py statements of TomoVis.

``saveFileCallBack`` writes the processed cube as dataset ``data`` and one
attribute per metadata key on a group ``metadata``; ``openFileCallBack`` reads
``data``, notes whether ``metadata`` exists, and after re-initialising the
window re-opens the file to read the attributes into a dict. The same calls in
the same order keep files interchangeable between the desktop app and the page.
"""

from __future__ import annotations

import h5py
import numpy as np


class SessionFile:
    """Reads and writes TomoVis session files."""

    def write(self, filename: str, data: np.ndarray, metadata: dict) -> None:
        """Writes a session, overwriting an existing file.

        Args:
            filename : Target path, already ending in .hd5.
            data     : The window's processed cube.
            metadata : getCurrentMetadata() output; insertion order is the attribute order.
        """

        with h5py.File(filename, "w") as h5f:
            h5f.create_dataset("data", data=data)

            meta_group = h5f.create_group("metadata")

            for key, value in metadata.items():
                meta_group.attrs[key] = value

    def read(self, filename: str) -> tuple[np.ndarray, bool]:
        """Reads the cube of a session.

        Args:
            filename : Session path.

        Returns:
            (data, whether a metadata group exists).

        Raises:
            ValueError : If the file has no ``data`` dataset, with the original's message.
        """

        with h5py.File(filename, "r") as h5f:
            if "data" not in h5f:
                raise ValueError("Dataset 'data' not found in file.")

            data         = h5f["data"][:]
            has_metadata = "metadata" in h5f

        return data, has_metadata

    def metadata(self, filename: str) -> dict:
        """Re-opens a session and reads its metadata attributes into a plain dict.

        Args:
            filename : Session path.

        Returns:
            Attribute name to value as h5py returns it.
        """

        with h5py.File(filename, "r") as h5f:
            return {k: h5f["metadata"].attrs[k] for k in h5f["metadata"].attrs.keys()}
