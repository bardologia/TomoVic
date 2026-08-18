"""Tests for reflectivity profile thresholding, truncation and unit-area normalization."""

from __future__ import annotations

import numpy as np
import pytest

from tools.data.preprocessing import ProfileNormalizer, ProfilePreprocessor


def test_preprocess_no_op_when_threshold_zero_and_no_truncation():
    """Verifies a zero threshold and an out-of-range truncation leave the profile untouched."""
    profile = np.array([[1.0], [2.0], [3.0]], dtype=np.float32)
    out     = ProfilePreprocessor.apply(profile, threshold_factor=0.0, truncation_index=10)

    assert np.array_equal(out, profile)


def test_preprocess_threshold_zeros_small_values():
    """Verifies values below the threshold fraction of the column maximum are zeroed."""
    profile = np.array([[1.0], [10.0], [4.0], [2.0]], dtype=np.float32)
    out     = ProfilePreprocessor.apply(profile, threshold_factor=0.5, truncation_index=100)

    assert out[0, 0] == 0.0
    assert out[1, 0] == 10.0
    assert out[2, 0] == 0.0
    assert out[3, 0] == 0.0


def test_preprocess_threshold_keeps_max():
    """Verifies the column maximum survives even a high threshold fraction."""
    profile = np.array([[5.0], [10.0], [8.0]], dtype=np.float32)
    out     = ProfilePreprocessor.apply(profile, threshold_factor=0.9, truncation_index=100)

    assert out[1, 0] == 10.0


def test_preprocess_truncation_zeros_tail():
    """Verifies heights at and beyond the truncation index are zeroed."""
    profile = np.array([[1.0], [2.0], [3.0], [4.0], [5.0]], dtype=np.float32)
    out     = ProfilePreprocessor.apply(profile, threshold_factor=0.0, truncation_index=3)

    assert np.array_equal(out[:3, 0], [1.0, 2.0, 3.0])
    assert np.array_equal(out[3:, 0], [0.0, 0.0])


def test_preprocess_does_not_mutate_input():
    """Verifies the input profile array is not modified in place."""
    profile = np.array([[1.0], [10.0], [3.0]], dtype=np.float32)
    before  = profile.copy()
    ProfilePreprocessor.apply(profile, threshold_factor=0.5, truncation_index=2)

    assert np.array_equal(profile, before)


def test_preprocess_threshold_and_truncation_combined():
    """Verifies thresholding and truncation are both applied to the same profile."""
    profile = np.array([[1.0], [10.0], [9.0], [8.0]], dtype=np.float32)
    out     = ProfilePreprocessor.apply(profile, threshold_factor=0.5, truncation_index=3)

    assert out[0, 0] == 0.0
    assert out[1, 0] == 10.0
    assert out[2, 0] == 9.0
    assert out[3, 0] == 0.0


def test_preprocess_multi_column_independent_max():
    """Verifies each column is thresholded against its own maximum."""
    profile = np.array([[10.0, 1.0], [2.0, 8.0]], dtype=np.float32)
    out     = ProfilePreprocessor.apply(profile, threshold_factor=0.5, truncation_index=100)

    assert out[0, 0] == 10.0
    assert out[1, 0] == 0.0
    assert out[0, 1] == 0.0
    assert out[1, 1] == 8.0


def test_preprocess_rejects_non_positive_truncation_index():
    """Verifies a truncation index of zero or below is rejected."""
    profile = np.array([[1.0], [2.0], [3.0]], dtype=np.float32)

    with pytest.raises(ValueError, match="truncation_index"):
        ProfilePreprocessor.apply(profile, threshold_factor=0.0, truncation_index=0)

    with pytest.raises(ValueError, match="truncation_index"):
        ProfilePreprocessor.apply(profile, threshold_factor=0.0, truncation_index=-2)


def test_preprocess_rejects_out_of_range_threshold_factor():
    """Verifies a threshold factor outside [0, 1) is rejected."""
    profile = np.array([[1.0], [2.0], [3.0]], dtype=np.float32)

    with pytest.raises(ValueError, match="threshold_factor"):
        ProfilePreprocessor.apply(profile, threshold_factor=1.0, truncation_index=3)

    with pytest.raises(ValueError, match="threshold_factor"):
        ProfilePreprocessor.apply(profile, threshold_factor=-0.1, truncation_index=3)


def test_normalizer_unit_area_sums_to_one():
    """Verifies unit-area normalization yields a float32 profile summing to one."""
    cube = np.array([[2.0], [4.0], [4.0]], dtype=np.float32)
    out  = ProfileNormalizer.unit_area(cube)

    assert np.isclose(out.sum(), 1.0)
    assert out.dtype == np.float32


def test_normalizer_proportions_preserved():
    """Verifies normalization preserves the relative weight of each height bin."""
    cube = np.array([[1.0], [3.0]], dtype=np.float32)
    out  = ProfileNormalizer.unit_area(cube)

    assert np.isclose(out[0, 0], 0.25)
    assert np.isclose(out[1, 0], 0.75)


def test_normalizer_zero_column_no_nan():
    """Verifies an all-zero column normalizes to zeros without producing NaNs."""
    cube = np.zeros((4, 1), dtype=np.float32)
    out  = ProfileNormalizer.unit_area(cube)

    assert np.all(np.isfinite(out))
    assert np.all(out == 0.0)


def test_normalizer_per_column_sums():
    """Verifies normalization along axis 0 makes every column sum to one."""
    cube = np.array([[1.0, 2.0], [1.0, 6.0]], dtype=np.float32)
    out  = ProfileNormalizer.unit_area(cube, axis=0)

    assert np.allclose(out.sum(axis=0), 1.0)


def test_normalizer_axis_argument():
    """Verifies normalization along axis 1 makes every row sum to one."""
    cube = np.array([[1.0, 1.0, 2.0]], dtype=np.float32)
    out  = ProfileNormalizer.unit_area(cube, axis=1)

    assert np.isclose(out.sum(axis=1)[0], 1.0)


@pytest.mark.real_data
def test_normalizer_on_real_tomogram_column(tomogram_full):
    """Verifies a real tomogram column normalizes to a non-negative unit-area profile."""
    column = np.abs(np.asarray(tomogram_full[:, 0, 0])).astype(np.float32)[:, None]
    out    = ProfileNormalizer.unit_area(column)

    assert out.shape == column.shape
    assert np.isclose(out.sum(), 1.0)
    assert np.all(out >= 0.0)


@pytest.mark.real_data
def test_preprocess_on_real_profile_truncates(tomogram_full):
    """Verifies truncating a real profile zeroes the tail and preserves the head."""
    profile = np.abs(np.asarray(tomogram_full[:, 0, 0])).astype(np.float32)[:, None]
    trunc   = profile.shape[0] // 2
    out     = ProfilePreprocessor.apply(profile, threshold_factor=0.0, truncation_index=trunc)

    assert np.all(out[trunc:] == 0.0)
    assert np.array_equal(out[:trunc], profile[:trunc])
