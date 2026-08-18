"""Extraction of per-pass baselines from DLR track files.

Reads the horizontal and vertical position rows of each pass's track product,
restricts them to a common azimuth window, and reduces them into a baseline
table plus the full along-azimuth position profiles.
"""
from __future__ import annotations

from pathlib import Path
from typing  import Callable

import numpy as np

from tools.baselines.containers import TrackBaselines, TrackProfiles
from tools.baselines.reading    import TrackFileResolver, TrackReader


class BaselineExtractor:
    """Turns per-pass track files into baselines and azimuth position profiles.

    Attributes:
        track_paths: Mapping of pass label to track file path, reference first.
        azimuth_window: Half-open azimuth line range to average over, or None for the full track.
        reader: Reader used to load the raw track arrays.
    """
    HORIZONTAL_ROW = 2
    VERTICAL_ROW   = 3

    def __init__(self, track_paths: dict, azimuth_window: tuple | None = None, reader: Callable | None = None):
        """Stores the track files and the azimuth window the baselines are measured over.

        Args:
            track_paths: Mapping of pass label to track file path; the first entry is the reference.
            azimuth_window: Half-open (start, end) azimuth line range, or None for the full track.
            reader: Callable reading a track file into an array, or None for the STEtools reader.
        """
        self.track_paths    = {label: Path(path) for label, path in track_paths.items()}
        self.azimuth_window = azimuth_window
        self.reader         = TrackReader(reader)

    @classmethod
    def from_pass_directories(cls, pass_directories: list, polarisation: str, azimuth_window: tuple | None = None, reader: Callable | None = None) -> "BaselineExtractor":
        """Builds an extractor by resolving one track file per pass directory.

        Args:
            pass_directories: Pass directories, the first being the reference pass.
            polarisation: Two-letter polarisation code used to disambiguate products.
            azimuth_window: Half-open (start, end) azimuth line range, or None for the full track.
            reader: Callable reading a track file into an array, or None for the STEtools reader.

        Returns:
            An extractor bound to the resolved track files.
        """
        track_paths = TrackFileResolver().resolve_passes(pass_directories, polarisation)
        return cls(track_paths, azimuth_window=azimuth_window, reader=reader)

    def _window_slice(self, n_samples: int) -> slice:
        """Returns the azimuth slice to read, validating it against the track length."""
        if self.azimuth_window is None:
            return slice(0, n_samples)

        start, end = int(self.azimuth_window[0]), int(self.azimuth_window[1])
        if start < 0 or end > n_samples:
            raise ValueError(f"Azimuth window [{start}, {end}) is not covered by the track file ({n_samples} samples); the requested crop exceeds this track's extent.")

        return slice(start, end)

    def _windowed_components(self, raw: np.ndarray) -> tuple:
        """Returns the windowed horizontal and vertical rows in metres plus the window start index."""
        window     = self._window_slice(raw.shape[1])
        horizontal = np.asarray(raw[self.HORIZONTAL_ROW, window], dtype=float)
        vertical   = np.asarray(raw[self.VERTICAL_ROW,   window], dtype=float)

        return horizontal, vertical, int(window.start)

    def extract_with_profiles(self) -> tuple:
        """Extracts the baseline table together with the along-azimuth position profiles.

        Passes are truncated to the shortest common azimuth extent, averaged over the
        window, and referenced to the first pass.

        Returns:
            A tuple of the baseline table and the position profiles, both in metres.
        """
        labels     = list(self.track_paths.keys())
        files      = [self.track_paths[label] for label in labels]
        components = [self._windowed_components(self.reader.read(path)) for path in files]

        n_common   = min(component[0].shape[0] for component in components)
        horizontal = np.stack([component[0][:n_common] for component in components])
        vertical   = np.stack([component[1][:n_common] for component in components])

        h_mean = [float(np.nanmean(row)) for row in horizontal]
        h_std  = [float(np.nanstd(row))  for row in horizontal]
        v_mean = [float(np.nanmean(row)) for row in vertical]
        v_std  = [float(np.nanstd(row))  for row in vertical]

        reference_h = h_mean[0]
        reference_v = v_mean[0]

        table = TrackBaselines(
            labels              = labels,
            vertical            = [v - reference_v for v in v_mean],
            horizontal          = [h - reference_h for h in h_mean],
            vertical_std        = v_std,
            horizontal_std      = h_std,
            vertical_absolute   = v_mean,
            horizontal_absolute = h_mean,
            track_files         = [str(f) for f in files],
            azimuth_window      = tuple(self.azimuth_window) if self.azimuth_window is not None else None,
        )

        profiles = TrackProfiles(
            labels        = labels,
            horizontal    = horizontal,
            vertical      = vertical,
            azimuth_start = components[0][2],
            track_files   = [str(f) for f in files],
        )

        return table, profiles

    def extract(self) -> TrackBaselines:
        """Returns only the baseline table, discarding the position profiles."""
        table, _ = self.extract_with_profiles()
        return table
