"""Shared fixtures for the configuration tests: crop regions, split regions and Gaussian settings."""

from __future__ import annotations

import dataclasses

from tools.data.regions                import CropRegion, SplitRegions
from configuration.sar.gaussian_config import GaussianConfig


def make_crop() -> CropRegion:
    """Returns a crop region spanning azimuth 1000-2000 and range 500-1000 in pixels."""
    return CropRegion(azimuth_start=1000, azimuth_end=2000, range_start=500, range_end=1000)


def make_split_regions() -> SplitRegions:
    """Returns contiguous train, validation and test crops over the same range extent."""
    return SplitRegions(
        train = CropRegion(azimuth_start=1000, azimuth_end=1300, range_start=500, range_end=1000),
        val   = CropRegion(azimuth_start=1300, azimuth_end=1450, range_start=500, range_end=1000),
        test  = CropRegion(azimuth_start=1450, azimuth_end=1600, range_start=500, range_end=1000),
    )


def make_gaussian() -> GaussianConfig:
    """Returns a Gaussian config with five slots over a height range of -20 to 80 metres."""
    return GaussianConfig(n_default_gaussians=5, x_min=-20.0, x_max=80.0)


def is_dataclass_type(obj) -> bool:
    """Returns whether the object is a dataclass class rather than an instance."""
    return dataclasses.is_dataclass(obj) and isinstance(obj, type)
