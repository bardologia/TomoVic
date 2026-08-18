"""Tests covering the compact integer-range formatter used in report summaries."""

from __future__ import annotations

import pytest

from tools.reporting.ranges import RangeFormatter


def test_single_value():
    """Verifies a lone value renders as itself."""
    assert RangeFormatter.compact([5]) == "5"


def test_two_contiguous():
    """Verifies two consecutive values collapse into one range."""
    assert RangeFormatter.compact([3, 4]) == "3-4"


def test_full_contiguous_run():
    """Verifies a fully contiguous sequence collapses into a single range."""
    assert RangeFormatter.compact([0, 1, 2, 3]) == "0-3"


def test_single_gap_splits_runs():
    """Verifies a gap splits the sequence into two ranges."""
    assert RangeFormatter.compact([0, 1, 3, 4]) == "0-1, 3-4"


def test_isolated_values():
    """Verifies non-adjacent values are listed individually."""
    assert RangeFormatter.compact([0, 2, 4]) == "0, 2, 4"


def test_mixed_runs_and_singletons():
    """Verifies runs and isolated values are rendered side by side."""
    assert RangeFormatter.compact([1, 2, 3, 7, 10, 11]) == "1-3, 7, 10-11"


def test_trailing_singleton():
    """Verifies a trailing isolated value follows the preceding run."""
    assert RangeFormatter.compact([1, 2, 5]) == "1-2, 5"


def test_leading_singleton():
    """Verifies a leading isolated value precedes the following run."""
    assert RangeFormatter.compact([0, 3, 4, 5]) == "0, 3-5"


def test_max_items_truncates_with_ellipsis():
    """Verifies exceeding max_items truncates the list and appends an ellipsis."""
    values = [0, 2, 4, 6, 8, 10, 12, 14]
    out    = RangeFormatter.compact(values, max_items=3)
    assert out == "0, 2, 4, ..."


def test_max_items_exactly_at_boundary_no_ellipsis():
    """Verifies a list exactly at max_items renders without an ellipsis."""
    values = [0, 2, 4]
    assert RangeFormatter.compact(values, max_items=3) == "0, 2, 4"


def test_max_items_default_six():
    """Verifies the default cap of six items truncates a longer sequence."""
    values = list(range(0, 20, 2))
    out    = RangeFormatter.compact(values)
    assert out.endswith("...")
    assert out.count(",") == 6


def test_negative_values():
    """Verifies a contiguous run of negative values renders as a range."""
    assert RangeFormatter.compact([-3, -2, -1]) == "-3--1"


def test_non_increasing_treated_as_break():
    """Verifies a decreasing step breaks the run instead of extending it."""
    assert RangeFormatter.compact([5, 4]) == "5, 4"


def test_duplicate_breaks_run():
    """Verifies a repeated value breaks the run."""
    assert RangeFormatter.compact([1, 1, 2]) == "1, 1-2"


@pytest.mark.real_data
def test_compact_on_contiguous_track_index(track_profiles):
    """Verifies the track index of a real dataset collapses into one contiguous range."""
    keys = sorted(track_profiles.keys())
    assert keys

    indices = list(range(len(keys)))
    out     = RangeFormatter.compact(indices, max_items=len(indices))
    assert out == f"0-{len(indices) - 1}"
