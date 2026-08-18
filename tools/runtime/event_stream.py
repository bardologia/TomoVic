"""Marker-prefixed JSON events written to stdout for a supervising process to parse."""

from __future__ import annotations

import json
import sys


class JsonEventStream:
    """Emits structured events on stdout, each tagged with a recognizable marker.

    Attributes:
        marker: Token opening every event line, used by the reader to tell events
            apart from ordinary log output.
    """

    def __init__(self, marker: str) -> None:
        """Initializes the stream with the marker prefixing every event line."""
        self.marker = marker

    def emit(self, kind: str, payload: dict) -> None:
        """Writes one flushed event line of marker, kind and JSON payload.

        Args:
            kind: Event type name.
            payload: JSON-serializable event body.
        """
        line = f"{self.marker} {kind} {json.dumps(payload)}"
        sys.stdout.write(line + "\n")
        sys.stdout.flush()
