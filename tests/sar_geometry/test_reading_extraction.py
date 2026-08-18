"""Tests for track file discovery, RAT track reading, and baseline extraction.

Covers TrackReader validation, TrackFileResolver path and polarisation selection,
and BaselineExtractor relative-baseline arithmetic and azimuth windowing."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from tools.baselines.containers import TrackBaselines, TrackProfiles
from tools.baselines.extraction import BaselineExtractor
from tools.baselines.reading    import TrackFileResolver, TrackReader


def _fake_track(n_azimuth: int = 50, h: float = 5.0, v: float = 3700.0) -> np.ndarray:
    """Builds a synthetic track array in the RAT row layout the extractor expects.

    Args:
        n_azimuth: Number of azimuth samples.
        h: Mean horizontal track position in metres.
        v: Mean vertical track position in metres.

    Returns:
        Array of shape (4, n_azimuth) with the horizontal and vertical rows filled.
    """
    rows = np.zeros((4, n_azimuth), dtype=float)
    rows[BaselineExtractor.HORIZONTAL_ROW] = h + np.linspace(-0.5, 0.5, n_azimuth)
    rows[BaselineExtractor.VERTICAL_ROW]   = v + np.linspace(-0.2, 0.2, n_azimuth)
    return rows


def test_track_reader_passes_custom_reader_through():
    """Verifies an injected reader callable supplies the track array unchanged."""
    reader = TrackReader(lambda path: _fake_track())
    data   = reader.read("anything.rat")

    assert data.shape == (4, 50)


def test_track_reader_rejects_too_few_rows():
    """Verifies a track array without the required rows is rejected."""
    reader = TrackReader(lambda path: np.zeros((2, 10)))

    with pytest.raises(ValueError):
        reader.read("x.rat")


def test_track_reader_rejects_non_2d():
    """Verifies a track array that is not two-dimensional is rejected."""
    reader = TrackReader(lambda path: np.zeros((4, 4, 4)))

    with pytest.raises(ValueError):
        reader.read("x.rat")


def test_resolver_label_from_pass_directory():
    """Verifies a flight/pass directory maps to a FLxx_PSyy label."""
    resolver = TrackFileResolver()

    assert resolver.label("/data/FL01/PS02") == "FL01_PS02"


def test_resolver_label_strips_track_subdir():
    """Verifies the trailing track subdirectory is dropped when building the label."""
    resolver = TrackFileResolver()

    assert resolver.label("/data/FL01/PS02/T01L") == "FL01_PS02"


def test_resolver_resolve_finds_track_file(tmp_path):
    """Verifies the resolver locates the track RAT file under INF/INF-TRACK."""
    track_dir = tmp_path / "PS02" / "INF" / "INF-TRACK"
    track_dir.mkdir(parents=True)
    (track_dir / "track_sar_resa_x.rat").write_text("stub")

    resolved = TrackFileResolver().resolve(tmp_path / "PS02", "hh")

    assert resolved.name == "track_sar_resa_x.rat"


def test_resolver_prefers_resa_pattern(tmp_path):
    """Verifies the resampled 'resa' product wins over other track files."""
    track_dir = tmp_path / "PS02" / "INF" / "INF-TRACK"
    track_dir.mkdir(parents=True)
    (track_dir / "track_other.rat").write_text("stub")
    (track_dir / "track_sar_resa_y.rat").write_text("stub")

    resolved = TrackFileResolver().resolve(tmp_path / "PS02", "hh")

    assert "resa" in resolved.name


def test_resolver_raises_when_missing(tmp_path):
    """Verifies an empty track directory raises FileNotFoundError."""
    (tmp_path / "PS02" / "INF" / "INF-TRACK").mkdir(parents=True)

    with pytest.raises(FileNotFoundError):
        TrackFileResolver().resolve(tmp_path / "PS02", "hh")


def test_resolver_picks_the_requested_polarisation_among_several(tmp_path):
    """Verifies the requested polarisation is selected from several candidates."""
    track_dir = tmp_path / "PS02" / "INF" / "INF-TRACK"
    track_dir.mkdir(parents=True)
    for pol in ("Lhh", "Lhv", "Lvv"):
        (track_dir / f"track_sar_resa_17sartom0102_{pol}_t01L.rat").write_text("stub")

    resolved = TrackFileResolver().resolve(tmp_path / "PS02", "hv")

    assert resolved.name == "track_sar_resa_17sartom0102_Lhv_t01L.rat"


def test_resolver_raises_when_the_polarisation_is_absent(tmp_path):
    """Verifies a missing polarisation is rejected instead of falling back."""
    track_dir = tmp_path / "PS02" / "INF" / "INF-TRACK"
    track_dir.mkdir(parents=True)
    for pol in ("Lhh", "Lvv"):
        (track_dir / f"track_sar_resa_17sartom0102_{pol}_t01L.rat").write_text("stub")

    with pytest.raises(ValueError, match="no single product"):
        TrackFileResolver().resolve(tmp_path / "PS02", "hv")


def test_resolver_raises_when_several_candidates_carry_no_polarisation(tmp_path):
    """Verifies ambiguous candidates without a polarisation tag are rejected."""
    track_dir = tmp_path / "PS02" / "INF" / "INF-TRACK"
    track_dir.mkdir(parents=True)
    (track_dir / "track_sar_resa_first.rat").write_text("stub")
    (track_dir / "track_sar_resa_second.rat").write_text("stub")

    with pytest.raises(ValueError, match="Cannot read polarisation"):
        TrackFileResolver().resolve(tmp_path / "PS02", "hv")


def test_resolve_passes_builds_label_mapping(tmp_path):
    """Verifies resolve_passes returns one entry per pass keyed by its label."""
    for pass_name in ("PS02", "PS04"):
        d = tmp_path / "FL01" / pass_name / "INF" / "INF-TRACK"
        d.mkdir(parents=True)
        (d / "track_sar_resa_z.rat").write_text("stub")

    mapping = TrackFileResolver().resolve_passes([tmp_path / "FL01" / "PS02", tmp_path / "FL01" / "PS04"], "hh")

    assert set(mapping.keys()) == {"FL01_PS02", "FL01_PS04"}


def test_resolve_passes_rejects_duplicate_labels(tmp_path):
    """Verifies two passes resolving to the same label are rejected."""
    d = tmp_path / "FL01" / "PS02" / "INF" / "INF-TRACK"
    d.mkdir(parents=True)
    (d / "track_sar_resa_z.rat").write_text("stub")

    with pytest.raises(ValueError, match="unique label"):
        TrackFileResolver().resolve_passes([tmp_path / "FL01" / "PS02", tmp_path / "FL01" / "PS02"], "hh")


def test_extractor_reference_baselines_are_zero():
    """Verifies the first track's relative baselines are exactly zero."""
    paths = {
        "FL01_PS02": Path("a.rat"),
        "FL01_PS04": Path("b.rat"),
    }
    tracks = {
        "a.rat": _fake_track(h=5.0, v=3700.0),
        "b.rat": _fake_track(h=9.0, v=3699.0),
    }

    extractor = BaselineExtractor(paths, reader=lambda p: tracks[Path(p).name])
    table     = extractor.extract()

    assert table.vertical[0] == pytest.approx(0.0, abs=1e-9)
    assert table.horizontal[0] == pytest.approx(0.0, abs=1e-9)


def test_extractor_relative_equals_absolute_minus_reference():
    """Verifies relative baselines equal absolute positions minus the reference track."""
    paths  = {"FL01_PS02": Path("a.rat"), "FL01_PS04": Path("b.rat")}
    tracks = {
        "a.rat": _fake_track(h=5.0, v=3700.0),
        "b.rat": _fake_track(h=9.0, v=3699.0),
    }

    table = BaselineExtractor(paths, reader=lambda p: tracks[Path(p).name]).extract()

    assert table.horizontal[1] == pytest.approx(table.horizontal_absolute[1] - table.horizontal_absolute[0])
    assert table.vertical[1] == pytest.approx(table.vertical_absolute[1] - table.vertical_absolute[0])


def test_extractor_with_profiles_returns_aligned_arrays():
    """Verifies profile extraction trims every track to the shortest azimuth length."""
    paths  = {"FL01_PS02": Path("a.rat"), "FL01_PS04": Path("b.rat")}
    tracks = {
        "a.rat": _fake_track(n_azimuth=40, h=5.0, v=3700.0),
        "b.rat": _fake_track(n_azimuth=50, h=9.0, v=3699.0),
    }

    table, profiles = BaselineExtractor(paths, reader=lambda p: tracks[Path(p).name]).extract_with_profiles()

    assert isinstance(table, TrackBaselines)
    assert isinstance(profiles, TrackProfiles)
    assert profiles.horizontal.shape == (2, 40)
    assert profiles.vertical.shape == (2, 40)


def test_extractor_azimuth_window_slices():
    """Verifies an azimuth window restricts the profiles and is recorded on the table."""
    paths  = {"FL01_PS02": Path("a.rat")}
    tracks = {"a.rat": _fake_track(n_azimuth=100)}

    table, profiles = BaselineExtractor(paths, azimuth_window=(20, 60), reader=lambda p: tracks[Path(p).name]).extract_with_profiles()

    assert profiles.n_samples == 40
    assert profiles.azimuth_start == 20
    assert table.azimuth_window == (20, 60)


def test_extractor_window_start_beyond_length_raises():
    """Verifies a window starting past the track length is rejected."""
    paths  = {"FL01_PS02": Path("a.rat")}
    tracks = {"a.rat": _fake_track(n_azimuth=30)}

    with pytest.raises(ValueError):
        BaselineExtractor(paths, azimuth_window=(40, 60), reader=lambda p: tracks[Path(p).name]).extract()


def test_extractor_window_end_beyond_length_raises():
    """Verifies a window ending past the track length is rejected."""
    paths  = {"FL01_PS02": Path("a.rat")}
    tracks = {"a.rat": _fake_track(n_azimuth=50)}

    with pytest.raises(ValueError, match="not covered"):
        BaselineExtractor(paths, azimuth_window=(20, 60), reader=lambda p: tracks[Path(p).name]).extract()


def test_extractor_short_secondary_track_raises():
    """Verifies a secondary track shorter than the window is rejected."""
    paths  = {"FL01_PS02": Path("a.rat"), "FL01_PS04": Path("b.rat")}
    tracks = {"a.rat": _fake_track(n_azimuth=100), "b.rat": _fake_track(n_azimuth=50)}

    with pytest.raises(ValueError, match="not covered"):
        BaselineExtractor(paths, azimuth_window=(20, 60), reader=lambda p: tracks[Path(p).name]).extract_with_profiles()
