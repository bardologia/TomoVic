"""Keeps the console mirrors of in-flight workers from filling the disk they live on.

A worker's merged stdout and stderr land in a log file that the console tiles tail.
Rich redraws its progress bars eight times a second with cursor-control sequences, so a
worker that runs for days writes gigabytes into that mirror while the durable record,
one line per finished trial or epoch, goes through the logger's file handler into the
run directory. On the cluster the mirrors live in a 100 GB HOME quota and a twenty-unit
bundle filled it in about a week.

The trimmer empties a mirror whose allocated blocks have grown past a limit. The writer
keeps its own file offset, so after the truncation it carries on into a file that is
sparse up to that offset: the blocks are freed, the apparent size does not move, and a
tailer reading by byte offset is not disturbed. The last bytes are copied into a
``.tail`` companion first so the latest console state survives the cut.
"""

from __future__ import annotations

import os
from pathlib import Path

from tools.monitoring.logger import Logger

MEGABYTE   = 1024 * 1024
KILOBYTE   = 1024
BLOCK_SIZE = 512


class LogMirrorTrimmer:
    """Empties the console mirrors whose allocated blocks have outgrown a limit.

    Attributes:
        max_bytes  : Allocated size a mirror may reach before it is emptied.
        tail_bytes : Bytes copied into the ``.tail`` companion before the mirror is emptied.
        logger     : Logger reporting each trim.
    """

    def __init__(self, max_bytes: int, tail_bytes: int, logger: Logger) -> None:
        """Stores the two size limits and the logger.

        Args:
            max_bytes  : Allocated size a mirror may reach before it is emptied.
            tail_bytes : Bytes kept in the ``.tail`` companion of each emptied mirror.
            logger     : Logger reporting each trim.

        Raises:
            ValueError : If either limit is not positive.
        """
        if max_bytes <= 0 or tail_bytes <= 0:
            raise ValueError(f"LogMirrorTrimmer needs positive limits, got max_bytes={max_bytes} and tail_bytes={tail_bytes}.")

        self.max_bytes  = max_bytes
        self.tail_bytes = tail_bytes
        self.logger     = logger

    @staticmethod
    def allocated(path: Path) -> int:
        """Returns the bytes a file occupies on disk, which for a sparse file is less than its size."""
        return os.stat(path).st_blocks * BLOCK_SIZE

    @staticmethod
    def tail_path(path: Path) -> Path:
        """Returns the companion file that keeps the last bytes of an emptied mirror."""
        return path.with_name(path.name + ".tail")

    def trim(self, paths: list[Path]) -> list[Path]:
        """Empties every mirror in the list that has outgrown the limit and returns those emptied.

        A mirror that does not exist yet is skipped: the worker may not have
        opened it. The tail copy is best effort, because a full disk is the
        case this class exists for and there the copy fails while the
        truncation is what frees the space.

        Args:
            paths : Mirrors of the workers currently in flight.

        Returns:
            The mirrors that were emptied in this sweep.
        """
        emptied = []

        for path in paths:
            if not path.is_file():
                continue

            before = self.allocated(path)

            if before <= self.max_bytes:
                continue

            self._keep_tail(path)
            os.truncate(path, 0)
            emptied.append(path)

            self.logger.info(f"emptied the console mirror of {path.name}: {before / MEGABYTE:,.0f} MB freed, last {self.tail_bytes / KILOBYTE:.0f} KB kept in {self.tail_path(path).name}")

        return emptied

    def _keep_tail(self, path: Path) -> None:
        """Copies the last ``tail_bytes`` of the mirror into its companion, warning instead of failing."""
        size  = os.stat(path).st_size
        start = max(0, size - self.tail_bytes)

        try:
            with open(path, "rb") as source:
                source.seek(start)
                chunk = source.read(self.tail_bytes)

            self.tail_path(path).write_bytes(chunk)
        except OSError as error:
            self.logger.warning(f"could not keep the tail of {path.name} before emptying it: {error}")
