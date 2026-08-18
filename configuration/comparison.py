"""Configuration dataclass for the preprocessing comparison entry point.

Drives the report comparing preprocessed dataset variants that differ by
multilook window size.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib     import Path
from typing      import List, Optional


@dataclass
class PreprocessingComparisonConfig:
    """Settings of the report comparing preprocessed dataset variants.

    Attributes:
        runs_dir: Directory holding the preprocessed dataset variants.
        run_tags: Dataset folder names taking part in the comparison.
        pixel_sample: Number of pixels sampled for the statistics.
        block_size: Side length in pixels of the blocks used for spatial statistics.
        range_chunk: Number of range lines read per chunk.
        workers: Worker processes reading the datasets in parallel.
        make_plots: Whether comparison figures are produced.
        output_dir: Destination of the report; ``None`` derives it from the inputs.
    """

    runs_dir : Path      = Path("/ste/rnd/User/vice_vi/Dataset")
    run_tags : List[str] = field(default_factory=list)

    pixel_sample : int = 200000
    block_size   : int = 8
    range_chunk  : int = 512
    workers      : int = 4

    make_plots : bool           = True
    output_dir : Optional[Path] = None
