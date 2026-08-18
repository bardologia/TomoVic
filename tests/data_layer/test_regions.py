"""Tests for the crop region container and the train/val/test split regions."""

from __future__ import annotations

import pytest

from tools.data.regions import CropRegion, SplitRegions


def test_crop_region_sizes():
    """Verifies the azimuth and range sizes are the extents of the half-open bounds."""
    region = CropRegion(1000, 2000, 500, 1000)

    assert region.azimuth_size == 1000
    assert region.range_size   == 500


def test_crop_region_as_tuple():
    """Verifies the tuple form is the azimuth and range bounds in order."""
    region = CropRegion(10, 20, 30, 40)

    assert region.as_tuple() == (10, 20, 30, 40)


def test_crop_region_identifier_string():
    """Verifies the identifier string joins the four bounds with the 'a' separator."""
    region = CropRegion(1000, 2000, 500, 1000)

    assert region.as_identifier_string() == "1000a2000a500a1000"


def test_crop_region_labeled_string():
    """Verifies the labelled string spells out the azimuth and range bounds."""
    region = CropRegion(1000, 2000, 500, 1000)

    assert region.as_labeled_string() == "az1000-2000_rg500-1000"


def test_crop_region_rejects_bad_azimuth():
    """Verifies an azimuth end before the start is rejected."""
    with pytest.raises(ValueError):
        CropRegion(2000, 1000, 0, 10)


def test_crop_region_rejects_equal_azimuth():
    """Verifies an empty azimuth extent is rejected."""
    with pytest.raises(ValueError):
        CropRegion(5, 5, 0, 10)


def test_crop_region_rejects_bad_range():
    """Verifies a range end before the start is rejected."""
    with pytest.raises(ValueError):
        CropRegion(0, 10, 100, 50)


def test_local_slices_relative_to_global():
    """Verifies local slices are offset by the global crop origin."""
    glob  = CropRegion(1000, 2000, 500, 1000)
    local = CropRegion(1100, 1300, 600, 700)

    az_slice, rg_slice = local.local_slices(glob)

    assert az_slice == slice(100, 300)
    assert rg_slice == slice(100, 200)


def test_local_slices_identity_when_equal():
    """Verifies a region taken against itself yields slices from zero."""
    glob = CropRegion(0, 50, 0, 50)
    az, rg = glob.local_slices(glob)

    assert az == slice(0, 50)
    assert rg == slice(0, 50)


def test_subdivide_by_azimuth_covers_full_range():
    """Verifies azimuth subdivision tiles the region with a short final part."""
    region = CropRegion(0, 1000, 0, 100)
    parts  = region.subdivide_by_azimuth(300)

    assert len(parts) == 4
    assert parts[0].as_tuple()  == (0, 300, 0, 100)
    assert parts[-1].as_tuple() == (900, 1000, 0, 100)
    assert sum(p.azimuth_size for p in parts) == region.azimuth_size


def test_subdivide_exact_multiple():
    """Verifies an exact multiple subdivides into equal parts."""
    region = CropRegion(0, 900, 0, 50)
    parts  = region.subdivide_by_azimuth(300)

    assert len(parts) == 3
    assert all(p.azimuth_size == 300 for p in parts)


def test_subdivide_wider_than_region():
    """Verifies a subdivision width beyond the region yields the region itself."""
    region = CropRegion(0, 200, 0, 50)
    parts  = region.subdivide_by_azimuth(1000)

    assert len(parts) == 1
    assert parts[0].as_tuple() == (0, 200, 0, 50)


def test_split_regions_from_ratios_partitions_azimuth():
    """Verifies the ratios partition the azimuth extent into train, validation and test."""
    glob   = CropRegion(0, 1000, 0, 500)
    splits = SplitRegions.from_ratios(glob, train_ratio=0.7, val_ratio=0.15)

    assert splits.train.as_tuple() == (0,   700,  0, 500)
    assert splits.val.as_tuple()   == (700, 850,  0, 500)
    assert splits.test.as_tuple()  == (850, 1000, 0, 500)


def test_split_regions_from_ratios_contiguous_and_full():
    """Verifies the default ratio splits are contiguous and cover the whole extent."""
    glob   = CropRegion(0, 1000, 0, 500)
    splits = SplitRegions.from_ratios(glob)

    assert splits.train.azimuth_end == splits.val.azimuth_start
    assert splits.val.azimuth_end   == splits.test.azimuth_start
    total = splits.train.azimuth_size + splits.val.azimuth_size + splits.test.azimuth_size
    assert total == glob.azimuth_size


def test_as_list_wraps_single():
    """Verifies a single region is wrapped in a one-element list."""
    region = CropRegion(0, 10, 0, 10)

    assert SplitRegions.as_list(region) == [region]


def test_as_list_passes_through_list():
    """Verifies a list of regions passes through unchanged."""
    a = CropRegion(0, 10, 0, 10)
    b = CropRegion(10, 20, 0, 10)

    assert SplitRegions.as_list([a, b]) == [a, b]


def test_regions_lookup_by_name():
    """Verifies regions are looked up by split name."""
    glob   = CropRegion(0, 1000, 0, 500)
    splits = SplitRegions.from_ratios(glob)

    assert splits.regions("train") == [splits.train]
    assert splits.regions("test")  == [splits.test]


def test_region_rows_single_region_labels():
    """Verifies the report rows are labelled by split name in order."""
    glob   = CropRegion(0, 1000, 0, 500)
    splits = SplitRegions.from_ratios(glob)
    rows   = splits.region_rows()

    labels = [r["Split"] for r in rows]
    assert labels == ["train", "val", "test"]


def test_region_rows_list_region_indexes():
    """Verifies a split holding several regions labels its rows by index."""
    a      = CropRegion(0, 100, 0, 50)
    b      = CropRegion(100, 200, 0, 50)
    splits = SplitRegions(train=[a, b], val=a, test=b)
    rows   = splits.region_rows()

    train_labels = [r["Split"] for r in rows if r["Split"].startswith("train")]
    assert train_labels == ["train[0]", "train[1]"]


@pytest.mark.real_data
def test_crop_region_matches_real_config(config_state_json):
    """Verifies the real preprocessing crop spans 1000 azimuth by 500 range samples."""
    crop   = config_state_json["crop"]
    region = CropRegion(crop["azimuth_start"], crop["azimuth_end"], crop["range_start"], crop["range_end"])

    assert region.azimuth_size == 1000
    assert region.range_size   == 500


@pytest.mark.real_data
def test_real_crop_local_slices_index_data(config_state_json, tomogram_full):
    """Verifies local slices of the real crop index the tomogram window they describe."""
    crop   = config_state_json["crop"]
    glob   = CropRegion(crop["azimuth_start"], crop["azimuth_end"], crop["range_start"], crop["range_end"])
    sub    = CropRegion(crop["azimuth_start"], crop["azimuth_start"] + 32, crop["range_start"], crop["range_start"] + 16)

    az, rg = sub.local_slices(glob)
    window = tomogram_full[:, az, rg]

    assert window.shape == (tomogram_full.shape[0], 32, 16)


def test_overlaps_detects_intersection():
    """Verifies overlap detection is symmetric and requires both axes to intersect."""
    a = CropRegion(0, 100, 0, 50)
    b = CropRegion(50, 150, 20, 80)
    c = CropRegion(100, 200, 0, 50)
    d = CropRegion(0, 100, 50, 100)

    assert a.overlaps(b)
    assert b.overlaps(a)
    assert not a.overlaps(c)
    assert not a.overlaps(d)


def test_validate_disjoint_accepts_disjoint_splits():
    """Verifies disjoint splits pass validation."""
    glob   = CropRegion(0, 1000, 0, 500)
    splits = SplitRegions.from_ratios(glob)

    splits.validate_disjoint()


def test_validate_disjoint_rejects_overlapping_splits():
    """Verifies overlapping splits are rejected."""
    splits = SplitRegions(
        train = CropRegion(0, 120, 0, 50),
        val   = CropRegion(100, 200, 0, 50),
        test  = CropRegion(200, 300, 0, 50),
    )

    with pytest.raises(ValueError, match="overlap"):
        splits.validate_disjoint()


def test_validate_disjoint_rejects_overlap_within_split():
    """Verifies overlap between two regions of the same split names the offending index."""
    a = CropRegion(0, 100, 0, 50)
    splits = SplitRegions(
        train = [a, CropRegion(50, 150, 0, 50)],
        val   = CropRegion(150, 200, 0, 50),
        test  = CropRegion(200, 300, 0, 50),
    )

    with pytest.raises(ValueError, match="train\\[0\\]"):
        splits.validate_disjoint()

def test_contains_true_for_inner_and_equal_regions():
    """Verifies containment holds for inner and identical regions."""
    outer = CropRegion(100, 200, 50, 150)

    assert outer.contains(CropRegion(120, 180, 60, 140))
    assert outer.contains(outer)


def test_contains_false_when_any_edge_escapes():
    """Verifies containment fails when any edge leaves the outer region."""
    outer = CropRegion(100, 200, 50, 150)

    assert not outer.contains(CropRegion(90, 180, 60, 140))
    assert not outer.contains(CropRegion(120, 210, 60, 140))
    assert not outer.contains(CropRegion(120, 180, 40, 140))
    assert not outer.contains(CropRegion(120, 180, 60, 160))


def test_validate_within_accepts_contained_splits():
    """Verifies splits inside the global crop pass validation."""
    glob   = CropRegion(0, 1000, 0, 500)
    splits = SplitRegions.from_ratios(glob)

    splits.validate_within(glob)


def test_validate_within_rejects_region_outside_crop():
    """Verifies a split reaching outside the global crop is rejected by name."""
    glob   = CropRegion(100, 1000, 0, 500)
    stale  = CropRegion(70, 90, 0, 500)
    splits = SplitRegions(train=stale, val=CropRegion(100, 200, 0, 500), test=CropRegion(200, 300, 0, 500))

    with pytest.raises(ValueError, match="'train'.*not contained"):
        splits.validate_within(glob)


def test_validate_within_names_indexed_region_in_lists():
    """Verifies the offending region of a multi-region split is named by index."""
    glob   = CropRegion(0, 1000, 0, 500)
    good   = CropRegion(0, 100, 0, 500)
    bad    = CropRegion(900, 1100, 0, 500)
    splits = SplitRegions(train=[good, bad], val=CropRegion(100, 200, 0, 500), test=CropRegion(200, 300, 0, 500))

    with pytest.raises(ValueError, match=r"'train\[1\]'"):
        splits.validate_within(glob)
