"""Shared fixtures for the configuration tests: crop regions and split regions."""

from __future__ import annotations

import dataclasses

from tools.data.regions                import CropRegion, SplitRegions


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
