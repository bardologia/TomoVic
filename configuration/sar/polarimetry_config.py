"""Entry-point settings of the polarimetric primary extraction over preprocessed datasets."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib     import Path


@dataclass
class PolarimetryEntryConfig:
    """Entry-point settings extending preprocessed datasets with the polarimetric primary.

    Every selected dataset has its primary pass read again in every
    polarisation, over the crop the dataset was built from, and stored as the
    Pauli-ready ``primary_polarimetric`` artifact the Cube tab decomposes.

    Attributes:
        dataset_base_path : Root directory holding one preprocessed dataset per sub-directory.
        dataset_filter    : Exact dataset directory names under the base path to extend; empty selects every dataset.
        pyrat_directory   : PyRAT checkout put on the import path of the worker.
        pyrat_threads     : Thread count PyRAT uses inside the worker.
        tomogram_env_name : Conda environment providing PyRAT to the worker.
        overwrite         : Whether a dataset that already carries the artifact is extracted again.
    """

    dataset_base_path : Path = field(default_factory=lambda: Path("/ste/rnd/User/vice_vi/Dataset"))
    dataset_filter    : list = field(default_factory=list)
    pyrat_directory   : Path = field(default_factory=lambda: Path("/ste/rnd/User/vice_vi/pyrat"))
    pyrat_threads     : int  = 4
    tomogram_env_name : str  = "stetools"
    overwrite         : bool = False
