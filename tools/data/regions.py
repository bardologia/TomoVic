"""Azimuth-range crop regions and the train/val/test splits built from them.

A region is a half-open rectangle in radar coordinates. Splits are collections
of such regions that must stay disjoint and inside the preprocessing crop, so
no pixel is shared between training and evaluation.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing      import Tuple


@dataclass
class CropRegion:
    """Half-open rectangle in azimuth-range radar coordinates.

    Attributes:
        azimuth_start: First azimuth line, inclusive.
        azimuth_end: Last azimuth line, exclusive.
        range_start: First range sample, inclusive.
        range_end: Last range sample, exclusive.
    """
    azimuth_start : int
    azimuth_end   : int
    range_start   : int
    range_end     : int

    def __post_init__(self) -> None:
        """Rejects empty or inverted regions.

        Raises:
            ValueError: If either axis does not start strictly before it ends.
        """
        if self.azimuth_start >= self.azimuth_end:
            raise ValueError(f"azimuth_start ({self.azimuth_start}) must be < azimuth_end ({self.azimuth_end})")
        if self.range_start   >= self.range_end:
            raise ValueError(f"range_start ({self.range_start}) must be < range_end ({self.range_end})")

    def as_tuple(self) -> Tuple[int, int, int, int]:
        """Returns the region as (azimuth_start, azimuth_end, range_start, range_end)."""
        return (self.azimuth_start, self.azimuth_end, self.range_start, self.range_end)

    def as_identifier_string(self) -> str:
        """Returns the region as a compact 'a'-joined identifier string."""
        return "a".join(str(value) for value in self.as_tuple())

    def as_labeled_string(self) -> str:
        """Returns the region as an axis-labelled string for file names."""
        return f"az{self.azimuth_start}-{self.azimuth_end}_rg{self.range_start}-{self.range_end}"

    @property
    def azimuth_size(self) -> int:
        """Extent of the region in azimuth lines."""
        return self.azimuth_end - self.azimuth_start

    @property
    def range_size(self) -> int:
        """Extent of the region in range samples."""
        return self.range_end - self.range_start

    def overlaps(self, other: "CropRegion") -> bool:
        """Returns whether this region shares any pixel with another."""
        azimuth_overlap = self.azimuth_start < other.azimuth_end and other.azimuth_start < self.azimuth_end
        range_overlap   = self.range_start   < other.range_end   and other.range_start   < self.range_end
        return azimuth_overlap and range_overlap

    def contains(self, other: "CropRegion") -> bool:
        """Returns whether another region lies entirely inside this one."""
        azimuth_inside = self.azimuth_start <= other.azimuth_start and other.azimuth_end <= self.azimuth_end
        range_inside   = self.range_start   <= other.range_start   and other.range_end   <= self.range_end
        return azimuth_inside and range_inside

    def local_slices(self, global_crop: "CropRegion") -> Tuple[slice, slice]:
        """Returns this region as slices into an array cropped to ``global_crop``.

        Args:
            global_crop: Region the array was cropped to.

        Returns:
            The azimuth and range slices addressing this region within that array.
        """
        azimuth_slice = slice(self.azimuth_start - global_crop.azimuth_start, self.azimuth_end - global_crop.azimuth_start)
        range_slice   = slice(self.range_start   - global_crop.range_start,   self.range_end   - global_crop.range_start)
        return azimuth_slice, range_slice

    def subdivide_by_azimuth(self, max_width: int) -> list["CropRegion"]:
        """Splits the region into consecutive azimuth strips.

        Args:
            max_width: Largest azimuth extent of a strip, in lines.

        Returns:
            The strips covering this region, in azimuth order; the last may be shorter.
        """
        subsections = []
        current     = self.azimuth_start

        while current < self.azimuth_end:
            next_azimuth = min(current + max_width, self.azimuth_end)
            subsections.append(CropRegion(current, next_azimuth, self.range_start, self.range_end))
            current = next_azimuth

        return subsections


@dataclass
class SplitRegions:
    """Train, validation and test regions of one dataset.

    Attributes:
        train: Training region or list of regions.
        val: Validation region or list of regions.
        test: Test region or list of regions.
    """
    train : CropRegion | list[CropRegion]
    val   : CropRegion | list[CropRegion]
    test  : CropRegion | list[CropRegion]

    @staticmethod
    def as_list(value) -> list[CropRegion]:
        """Returns the value as a list of regions, wrapping a single region."""
        if isinstance(value, (list, tuple)):
            return list(value)
        return [value]

    def items(self):
        """Returns the (split name, value) pairs in train, val, test order."""
        return [("train", self.train), ("val", self.val), ("test", self.test)]

    def region_lists(self):
        """Returns the (split name, region list) pairs in train, val, test order."""
        return [(name, self.as_list(value)) for name, value in self.items()]

    def regions(self, split_name: str) -> list[CropRegion]:
        """Returns the regions of one split as a list."""
        return self.as_list(dict(self.items())[split_name])

    def region_rows(self) -> list[dict]:
        """Returns one table row per region with its label, crop and extent in lines and samples."""
        rows = []
        for name, regions in self.region_lists():
            for index, region in enumerate(regions):
                label = name if len(regions) == 1 else f"{name}[{index}]"
                rows.append({"Split": label, "Crop": str(region.as_tuple()), "Azimuth (lines)": region.azimuth_size, "Range (samples)": region.range_size})
        return rows

    def validate_disjoint(self) -> None:
        """Checks that no two split regions overlap.

        Raises:
            ValueError: If any pair of regions shares a pixel.
        """
        labeled = []
        for name, regions in self.region_lists():
            for index, region in enumerate(regions):
                label = name if len(regions) == 1 else f"{name}[{index}]"
                labeled.append((label, region))

        for i in range(len(labeled)):
            for j in range(i + 1, len(labeled)):
                name_a, region_a = labeled[i]
                name_b, region_b = labeled[j]
                if region_a.overlaps(region_b):
                    raise ValueError(f"Split regions '{name_a}' {region_a.as_tuple()} and '{name_b}' {region_b.as_tuple()} overlap; all train/val/test regions must be spatially disjoint.")

    def validate_within(self, global_crop: CropRegion) -> None:
        """Checks that every split region lies inside the preprocessing crop.

        Args:
            global_crop: Region the preprocessed data covers.

        Raises:
            ValueError: If a split region is not contained in that crop.
        """
        for name, regions in self.region_lists():
            for index, region in enumerate(regions):
                if not global_crop.contains(region):
                    label = name if len(regions) == 1 else f"{name}[{index}]"
                    raise ValueError(f"Split region '{label}' {region.as_tuple()} is not contained in the preprocessing global crop {global_crop.as_tuple()}; out-of-crop coordinates would silently wrap or truncate when sliced, loading pixels from the wrong area.")

    @classmethod
    def from_ratios(cls, global_crop: CropRegion, train_ratio: float = 0.70, val_ratio: float = 0.15) -> "SplitRegions":
        """Splits a crop into three contiguous azimuth bands.

        Args:
            global_crop: Region to divide.
            train_ratio: Share of the azimuth extent given to training.
            val_ratio: Share of the azimuth extent given to validation.

        Returns:
            The train, validation and test bands, in azimuth order, spanning the full range extent.
        """
        total_az  = global_crop.azimuth_end - global_crop.azimuth_start
        train_end = global_crop.azimuth_start + int(total_az * train_ratio)
        val_end   = train_end + int(total_az * val_ratio)

        return cls(
            train = CropRegion(global_crop.azimuth_start, train_end,               global_crop.range_start, global_crop.range_end),
            val   = CropRegion(train_end,                 val_end,                 global_crop.range_start, global_crop.range_end),
            test  = CropRegion(val_end,                   global_crop.azimuth_end, global_crop.range_start, global_crop.range_end),
        )
