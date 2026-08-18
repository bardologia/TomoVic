"""Location and reading of the per-pass track products behind baseline extraction.

Resolves one track file per acquisition pass under the DLR product layout and
reads it into the raw position array the baseline extractor consumes.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing  import Callable

import numpy as np


class TrackReader:
    """Reads a track file into a validated position array."""
    MIN_ROWS = 4

    def __init__(self, reader: Callable | None = None):
        """Stores the reader used for track files.

        Args:
            reader: Callable mapping a path string to an array, or None for the STEtools reader.
        """
        self._reader = reader

    def read(self, path: str | Path) -> np.ndarray:
        """Reads one track file and checks it carries the expected position rows.

        Args:
            path: Path of the track file.

        Returns:
            Raw track array of shape (>= 4, n_azimuth); rows 2 and 3 hold the
            horizontal and vertical positions in metres.

        Raises:
            ValueError: If the file is not 2-dimensional or has too few rows.
        """
        reader = self._reader if self._reader is not None else self._default_reader()
        data   = np.asarray(reader(str(path)))

        if data.ndim != 2 or data.shape[0] < self.MIN_ROWS:
            raise ValueError(f"Track file {path} has shape {data.shape}, expected (>= {self.MIN_ROWS}, n_azimuth)")

        return data

    @staticmethod
    def _default_reader() -> Callable:
        """Returns the STEtools RAT reader used when no reader was injected."""
        from STEtools.ste_io import rrat
        return rrat


class PassProductResolver:
    """Resolves a single product file inside a pass directory.

    Subclasses declare the product subdirectory and the file name patterns they
    look for; polarisation disambiguates when several candidates match.
    """
    PRODUCT_SUBDIR       = Path(".")
    PRODUCT_PATTERNS     = ()
    TRACK_DIR_PATTERN    = re.compile(r"[Tt]\d+\w*")
    POLARISATION_PATTERN = re.compile(r"_[A-Za-z]*?([hvHV]{2})_[Tt][0-9A-Za-z]+$")

    def label(self, pass_directory: str | Path) -> str:
        """Returns the flight-qualified label of a pass directory."""
        node   = self._pass_node(pass_directory)
        flight = node.parent.name
        return f"{flight}_{node.name}" if flight else node.name

    def _pass_node(self, pass_directory: str | Path) -> Path:
        """Returns the pass directory itself, stepping up out of a track subdirectory."""
        path = Path(pass_directory)
        return path.parent if self.TRACK_DIR_PATTERN.fullmatch(path.name) else path

    def _polarisation_of(self, product_file: Path) -> str:
        """Returns the two-letter polarisation code parsed from a product file name."""
        match = self.POLARISATION_PATTERN.search(product_file.stem)

        if match is None:
            raise ValueError(f"Cannot read polarisation from file name '{product_file.name}'")

        return match.group(1).lower()

    def _single_candidate(self, candidates: list, directory: Path, polarisation: str) -> Path:
        """Returns the single candidate, disambiguating several by polarisation."""
        if len(candidates) == 1:
            return candidates[0]

        wanted  = polarisation.lower()
        matches = [candidate for candidate in candidates if self._polarisation_of(candidate) == wanted]

        if len(matches) != 1:
            raise ValueError(f"{len(candidates)} files match {self.PRODUCT_PATTERNS} under {directory}: {[candidate.name for candidate in candidates]}; {len(matches)} of them carry polarisation '{wanted}', so no single product can be selected without guessing.")

        return matches[0]

    def resolve(self, pass_directory: str | Path, polarisation: str) -> Path:
        """Resolves the product file of one pass directory.

        Args:
            pass_directory: Directory of the acquisition pass.
            polarisation: Two-letter polarisation code used to disambiguate candidates.

        Returns:
            Path of the selected product file.

        Raises:
            FileNotFoundError: If no file matches the configured patterns.
            ValueError: If no single candidate can be selected.
        """
        directory = Path(pass_directory) / self.PRODUCT_SUBDIR

        for pattern in self.PRODUCT_PATTERNS:
            candidates = sorted(directory.glob(pattern))
            if candidates:
                return self._single_candidate(candidates, directory, polarisation)

        raise FileNotFoundError(f"No file matching {self.PRODUCT_PATTERNS} under {directory}")

    def resolve_passes(self, pass_directories: list, polarisation: str) -> dict:
        """Resolves one product file per pass directory, keyed by pass label.

        Args:
            pass_directories: Directories of the acquisition passes, reference first.
            polarisation: Two-letter polarisation code used to disambiguate candidates.

        Returns:
            Mapping of pass label to resolved product path, in input order.

        Raises:
            ValueError: If two pass directories resolve to the same label.
        """
        mapping = {}

        for directory in pass_directories:
            label = self.label(directory)
            if label in mapping:
                raise ValueError(f"Pass directory {directory} resolves to label '{label}' which is already taken; every pass must map to a unique label or tracks would be silently dropped.")

            mapping[label] = self.resolve(directory, polarisation)

        return mapping


class TrackFileResolver(PassProductResolver):
    """Resolves the INF-TRACK position product of a pass directory."""
    PRODUCT_SUBDIR   = Path("INF") / "INF-TRACK"
    PRODUCT_PATTERNS = ("track_sar_resa_*.rat", "track_*.rat")
