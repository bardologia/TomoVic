"""Resolution of the preprocessing-run queue a pipeline should iterate over."""

from __future__ import annotations

from pathlib import Path


class DatasetQueueResolver:
    """Selects the preprocessing run directories to process, in a stable order.

    Attributes:
        base_path      : Directory holding one sub-directory per preprocessing run.
        dataset_filter : Explicit run names to select; empty selects every run.
    """

    def __init__(self, base_path: Path, dataset_filter: list) -> None:
        """Stores the queue root and the optional explicit dataset selection."""
        self.base_path      = base_path
        self.dataset_filter = dataset_filter

    def resolve(self) -> list[Path]:
        """Returns the sorted dataset directories of the queue.

        Returns:
            One path per selected preprocessing run, each verified to contain a
            data/ sub-directory.

        Raises:
            TypeError          : `dataset_filter` is not a list or tuple of names.
            NotADirectoryError : The base path is missing, or a selected entry has no data/ sub-directory.
            FileNotFoundError  : The base path holds no dataset directory, so the queue would run as an empty no-op.
        """
        if not isinstance(self.dataset_filter, (list, tuple)):
            raise TypeError(f"dataset_filter must be a list of dataset names, got {type(self.dataset_filter).__name__}: {self.dataset_filter!r}")

        if not self.base_path.is_dir():
            raise NotADirectoryError(f"dataset_base_path does not exist: {self.base_path}")

        dataset_dirs = sorted(
            [d for d in self.base_path.iterdir() if d.is_dir()]
            if not self.dataset_filter
            else [self.base_path / str(name) for name in self.dataset_filter]
        )

        if not dataset_dirs:
            raise FileNotFoundError(f"dataset_base_path {self.base_path} holds no dataset directory, so the queue is empty; check that the share is mounted and that the machine profile points at the dataset root")

        invalid = [d for d in dataset_dirs if not (d / "data").is_dir()]
        if invalid:
            names = ", ".join(d.name for d in invalid)
            raise NotADirectoryError(f"Queue entries without a data/ directory under {self.base_path}: {names}")

        return dataset_dirs
