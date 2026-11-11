"""Binary response envelope of the TomoVis API ("TVE1").

Layout: the 4 ASCII bytes ``TVE1``, a little-endian uint32 with the byte
length J of the JSON header, J bytes of UTF-8 JSON, zero padding to the next
multiple of 8, then every blob starting at a multiple of 8 in the order of
``header.blobs``. Arrays are C-order little-endian float32 or uint8 exactly
as the server holds them; PNG blobs are matplotlib frames.
"""

from __future__ import annotations

import json
import struct

import numpy as np

from routers.dispatch import HttpExchange


class TomoVisEnvelope:
    """Packs and unpacks TVE1 envelopes.

    Attributes:
        MAGIC     : The four leading bytes.
        ALIGNMENT : Byte alignment of the JSON end and of every blob.
        DTYPES    : Array dtypes the envelope carries, as numpy little-endian codes.
    """

    MAGIC     = b"TVE1"
    ALIGNMENT = 8
    DTYPES    = {"float32": "<f4", "uint8": "|u1"}

    def padding(self, length: int) -> bytes:
        """Returns the zero bytes that bring ``length`` to the next multiple of the alignment."""

        return b"\0" * ((-length) % self.ALIGNMENT)

    def blobBytes(self, value) -> tuple[dict, bytes]:
        """Describes and serialises one blob.

        Args:
            value : numpy array (float32-compatible floats or uint8) or PNG bytes.

        Returns:
            (description without offset, raw bytes).

        Raises:
            TypeError : For an array dtype the envelope does not carry.
        """

        if isinstance(value, bytes):
            return {"kind": "png", "dtype": None, "shape": None}, value

        array = np.asarray(value)
        if array.dtype == np.uint8:
            dtype = "uint8"
        elif array.dtype.kind == "f":
            dtype = "float32"
        else:
            raise TypeError(f"the envelope carries float32 and uint8 arrays, not {array.dtype}")
        data = np.ascontiguousarray(array, dtype=self.DTYPES[dtype]).tobytes()
        return {"kind": "array", "dtype": dtype, "shape": list(array.shape)}, data

    def pack(self, header: dict, blobs: dict) -> bytes:
        """Builds an envelope.

        Args:
            header : JSON-ready header; non-finite floats become null; ``blobs`` is added.
            blobs  : Blob name to array or PNG bytes, in the order they are written.

        Returns:
            The envelope bytes.
        """

        described = []
        payloads  = []
        for name, value in blobs.items():
            description, data = self.blobBytes(value)
            described.append({"name": name, **description, "offset": 0, "nbytes": len(data)})
            payloads.append(data)

        full = dict(header)
        while True:
            full["blobs"] = described
            text          = json.dumps(HttpExchange.jsonsafe(full)).encode("utf-8")
            offset        = 8 + len(text) + len((self.padding(8 + len(text))))
            moved         = False
            for entry, data in zip(described, payloads):
                if entry["offset"] != offset:
                    entry["offset"] = offset
                    moved           = True
                offset += len(data) + len(self.padding(len(data)))
            if not moved:
                break

        parts = [self.MAGIC, struct.pack("<I", len(text)), text, self.padding(8 + len(text))]
        for data in payloads:
            parts.append(data)
            parts.append(self.padding(len(data)))
        return b"".join(parts)

    def unpack(self, envelope: bytes) -> tuple[dict, dict]:
        """Decodes an envelope (used by the tests and tools).

        Args:
            envelope : Bytes produced by pack.

        Returns:
            (header, blob name to numpy array or PNG bytes).

        Raises:
            ValueError : If the magic bytes are wrong.
        """

        if envelope[:4] != self.MAGIC:
            raise ValueError("not a TVE1 envelope")
        length = struct.unpack("<I", envelope[4:8])[0]
        header = json.loads(envelope[8:8 + length].decode("utf-8"))
        blobs  = {}
        for entry in header["blobs"]:
            data = envelope[entry["offset"]:entry["offset"] + entry["nbytes"]]
            if entry["kind"] == "png":
                blobs[entry["name"]] = data
            else:
                blobs[entry["name"]] = np.frombuffer(data, dtype=self.DTYPES[entry["dtype"]]).reshape(entry["shape"])
        return header, blobs
