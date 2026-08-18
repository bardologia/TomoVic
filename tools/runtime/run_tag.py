"""Timestamp tags used to name and identify run directories."""

from __future__ import annotations

from datetime import datetime


class RunTag:
    """Formats and recognises the timestamp tag that names a run directory.

    Attributes:
        TAG_FORMAT: strftime pattern of a run-directory tag (YYYYmmdd_HHMMSS).
        TIMESTAMP_FORMAT: strftime pattern of a human-readable timestamp.
    """

    TAG_FORMAT       = "%Y%m%d_%H%M%S"
    TIMESTAMP_FORMAT = "%Y-%m-%d %H:%M:%S"

    @classmethod
    def now(cls) -> str:
        """Returns the current local time formatted as a run tag."""
        return datetime.now().strftime(cls.TAG_FORMAT)

    @classmethod
    def timestamp(cls) -> str:
        """Returns the current local time as a human-readable timestamp."""
        return datetime.now().strftime(cls.TIMESTAMP_FORMAT)

    @classmethod
    def is_tag(cls, name: str) -> bool:
        """Returns whether a name parses as a run tag in TAG_FORMAT."""
        try:
            datetime.strptime(str(name), cls.TAG_FORMAT)
        except ValueError:
            return False

        return True
