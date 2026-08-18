"""Containers for airborne track baselines and their along-azimuth profiles.

Holds the per-pass baseline table produced from DLR track files, the full
azimuth-resolved position profiles behind it, and the shared logic that
selects a subset of secondary passes relative to the reference pass.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib     import Path
from typing      import ClassVar

import numpy as np



class SecondarySelection:
    """Resolves requested secondary pass labels into secondary indices."""
    @staticmethod
    def indices(labels: list, secondary_labels) -> list:
        """Returns the indices of the requested secondary passes within the secondary list.

        Args:
            labels: Pass labels, the first entry being the reference pass.
            secondary_labels: Iterable of labels naming the secondary passes to keep.

        Returns:
            Positions of the requested labels inside ``labels[1:]``, in request order.

        Raises:
            ValueError: If the reference pass is requested as a secondary, if a label
                is unknown, or if the request contains duplicates.
        """
        primary     = labels[0]
        secondaries = list(labels[1:])
        requested   = [str(label) for label in secondary_labels]

        if primary in requested:
            raise ValueError(f"Pass {primary} is the reference and is always included; remove it from secondary_labels")

        unknown = [label for label in requested if label not in secondaries]
        if unknown:
            raise ValueError(f"Unknown secondary labels {unknown}; secondaries are {secondaries}")

        if len(set(requested)) != len(requested):
            raise ValueError(f"secondary_labels contains duplicates: {requested}")

        return [secondaries.index(label) for label in requested]


@dataclass
class TrackBaselines:
    """Per-pass baselines of one acquisition stack, relative to the reference pass.

    Attributes:
        labels: Pass labels, the first being the reference pass.
        vertical: Vertical baseline per pass in metres, referenced to pass 0.
        horizontal: Horizontal baseline per pass in metres, referenced to pass 0.
        vertical_std: Along-azimuth standard deviation of the vertical position, in metres.
        horizontal_std: Along-azimuth standard deviation of the horizontal position, in metres.
        vertical_absolute: Mean absolute vertical position per pass in metres.
        horizontal_absolute: Mean absolute horizontal position per pass in metres.
        track_files: Source track file paths, one per pass.
        azimuth_window: Half-open azimuth line range the baselines were averaged over,
            or None when the full track was used.
    """
    labels              : list
    vertical            : list
    horizontal          : list
    vertical_std        : list
    horizontal_std      : list
    vertical_absolute   : list         = field(default_factory=list)
    horizontal_absolute : list         = field(default_factory=list)
    track_files         : list         = field(default_factory=list)
    azimuth_window      : tuple | None = None

    FILENAME : ClassVar[str] = "baselines.json"

    @property
    def reference(self) -> str:
        """Label of the reference pass."""
        return self.labels[0]

    @property
    def n_tracks(self) -> int:
        """Number of passes in the stack, reference included."""
        return len(self.labels)

    def subset(self, secondary_labels) -> "TrackBaselines":
        """Returns a copy holding the reference pass and the requested secondaries.

        Args:
            secondary_labels: Labels of the secondary passes to keep, or None to keep all.

        Returns:
            A new table restricted to the selected passes; ``self`` when nothing is selected.
        """
        if secondary_labels is None:
            return self

        keep = [0] + [1 + index for index in SecondarySelection.indices(self.labels, secondary_labels)]

        def pick(values: list) -> list:
            return [values[index] for index in keep] if values else list(values)

        return TrackBaselines(
            labels              = pick(self.labels),
            vertical            = pick(self.vertical),
            horizontal          = pick(self.horizontal),
            vertical_std        = pick(self.vertical_std),
            horizontal_std      = pick(self.horizontal_std),
            vertical_absolute   = pick(self.vertical_absolute),
            horizontal_absolute = pick(self.horizontal_absolute),
            track_files         = pick(self.track_files),
            azimuth_window      = self.azimuth_window,
        )

    def baselines(self, component: str = "vertical", look_angle_deg: float | None = None) -> tuple:
        """Returns the per-pass baseline of one geometric component, in metres.

        Args:
            component: One of 'vertical', 'horizontal', 'magnitude' or 'perpendicular'.
            look_angle_deg: Radar look angle in degrees, required for 'perpendicular'.

        Returns:
            One baseline value per pass, in metres, ordered as ``labels``.

        Raises:
            ValueError: If the component is unknown, or 'perpendicular' is asked for
                without a look angle.
        """
        if component == "vertical":
            return tuple(self.vertical)
        if component == "horizontal":
            return tuple(self.horizontal)
        if component == "magnitude":
            return tuple(float(np.hypot(v, h)) for v, h in zip(self.vertical, self.horizontal))
        if component == "perpendicular":
            if look_angle_deg is None:
                raise ValueError("Baseline component 'perpendicular' requires look_angle_deg")
            theta = float(np.deg2rad(look_angle_deg))
            return tuple(float(h * np.cos(theta) + v * np.sin(theta)) for v, h in zip(self.vertical, self.horizontal))
        raise ValueError(f"Unknown baseline component '{component}', expected 'vertical', 'horizontal', 'magnitude' or 'perpendicular'")

    def describe(self) -> dict:
        """Returns a printable field-to-string table summarising the baselines."""
        window = "full track" if self.azimuth_window is None else f"[{self.azimuth_window[0]}, {self.azimuth_window[1]})"
        table  = {
            "Tracks"             : self.n_tracks,
            "Reference"          : self.reference,
            "Azimuth window"     : window,
            "Vertical [m]"       : ", ".join(f"{v:.2f}" for v in self.vertical),
            "Horizontal [m]"     : ", ".join(f"{h:.2f}" for h in self.horizontal),
            "Vertical std [m]"   : ", ".join(f"{s:.2f}" for s in self.vertical_std),
            "Horizontal std [m]" : ", ".join(f"{s:.2f}" for s in self.horizontal_std),
        }

        if self.vertical_absolute:
            table["Vertical absolute [m]"]   = ", ".join(f"{v:.2f}" for v in self.vertical_absolute)
            table["Horizontal absolute [m]"] = ", ".join(f"{h:.2f}" for h in self.horizontal_absolute)

        return table

    def to_payload(self) -> dict:
        """Returns the JSON-serialisable payload of this table."""
        return {
            "labels"              : list(self.labels),
            "reference"           : self.reference,
            "vertical"            : [float(v) for v in self.vertical],
            "horizontal"          : [float(h) for h in self.horizontal],
            "vertical_std"        : [float(s) for s in self.vertical_std],
            "horizontal_std"      : [float(s) for s in self.horizontal_std],
            "vertical_absolute"   : [float(v) for v in self.vertical_absolute],
            "horizontal_absolute" : [float(h) for h in self.horizontal_absolute],
            "track_files"         : [str(f) for f in self.track_files],
            "azimuth_window"      : list(self.azimuth_window) if self.azimuth_window is not None else None,
        }

    @classmethod
    def from_payload(cls, payload: dict) -> "TrackBaselines":
        """Rebuilds a table from a payload written by :meth:`to_payload`.

        Args:
            payload: Mapping as produced by :meth:`to_payload`.

        Returns:
            The reconstructed table.
        """
        window = payload["azimuth_window"]
        return cls(
            labels              = list(payload["labels"]),
            vertical            = [float(v) for v in payload["vertical"]],
            horizontal          = [float(h) for h in payload["horizontal"]],
            vertical_std        = [float(s) for s in payload["vertical_std"]],
            horizontal_std      = [float(s) for s in payload["horizontal_std"]],
            vertical_absolute   = [float(v) for v in payload["vertical_absolute"]],
            horizontal_absolute = [float(h) for h in payload["horizontal_absolute"]],
            track_files         = list(payload["track_files"]),
            azimuth_window      = tuple(window) if window is not None else None,
        )

    def save(self, path: str | Path) -> Path:
        """Writes the table as indented JSON and returns the written path."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_payload(), indent=4), encoding="utf-8")
        return path

    @classmethod
    def load(cls, path: str | Path) -> "TrackBaselines":
        """Loads a table from the JSON file written by :meth:`save`."""
        return cls.from_payload(json.loads(Path(path).read_text(encoding="utf-8")))


@dataclass
class TrackProfiles:
    """Along-azimuth position profiles of every pass in an acquisition stack.

    Attributes:
        labels: Pass labels, the first being the reference pass.
        horizontal: Horizontal positions in metres, shape (n_tracks, n_azimuth).
        vertical: Vertical positions in metres, shape (n_tracks, n_azimuth).
        azimuth_start: Azimuth line index the profiles start at.
        track_files: Source track file paths, one per pass.
    """
    labels        : list
    horizontal    : np.ndarray
    vertical      : np.ndarray
    azimuth_start : int
    track_files   : list = field(default_factory=list)

    FILENAME : ClassVar[str] = "track_profiles.npz"

    @property
    def n_tracks(self) -> int:
        """Number of passes in the stack, reference included."""
        return len(self.labels)

    @property
    def n_samples(self) -> int:
        """Number of azimuth samples held per pass."""
        return int(self.horizontal.shape[1])

    @property
    def azimuth_axis(self) -> np.ndarray:
        """Absolute azimuth line indices covered by the profiles, shape (n_azimuth,)."""
        return np.arange(self.azimuth_start, self.azimuth_start + self.n_samples)

    def relative_to_reference(self, component: str = "vertical") -> np.ndarray:
        """Returns the profiles of one component measured against the reference pass.

        Args:
            component: Either 'vertical' or 'horizontal'.

        Returns:
            Profiles in metres with the reference pass subtracted, shape
            (n_tracks, n_azimuth).

        Raises:
            ValueError: If the component is neither 'vertical' nor 'horizontal'.
        """
        if component == "vertical":
            profiles = self.vertical
        elif component == "horizontal":
            profiles = self.horizontal
        else:
            raise ValueError(f"Unknown baseline component '{component}', expected 'vertical' or 'horizontal'")

        return profiles - profiles[0]

    def planar_deviation(self) -> np.ndarray:
        """Returns the per-sample distance in metres from each pass's own mean position, shape (n_tracks, n_azimuth)."""
        h_centered = self.horizontal - np.nanmean(self.horizontal, axis=1, keepdims=True)
        v_centered = self.vertical   - np.nanmean(self.vertical,   axis=1, keepdims=True)
        return np.sqrt(h_centered ** 2 + v_centered ** 2)

    def deviation_radii(self) -> np.ndarray:
        """Returns the RMS deviation radius in metres per pass, shape (n_tracks,)."""
        return np.sqrt(np.nanmean(self.planar_deviation() ** 2, axis=1))

    def position_summary(self) -> dict:
        """Returns per-pass means, spans and deviation statistics of the positions, in metres."""
        deviation = self.planar_deviation()

        return {
            "labels"          : list(self.labels),
            "horizontal_mean" : [float(x) for x in np.nanmean(self.horizontal, axis=1)],
            "vertical_mean"   : [float(x) for x in np.nanmean(self.vertical,   axis=1)],
            "horizontal_span" : [float(x) for x in np.nanmax(self.horizontal, axis=1) - np.nanmin(self.horizontal, axis=1)],
            "vertical_span"   : [float(x) for x in np.nanmax(self.vertical,   axis=1) - np.nanmin(self.vertical,   axis=1)],
            "deviation_rms"   : [float(x) for x in np.sqrt(np.nanmean(deviation ** 2, axis=1))],
            "deviation_max"   : [float(x) for x in np.nanmax(deviation, axis=1)],
            "azimuth_start"   : int(self.azimuth_start),
            "n_samples"       : self.n_samples,
        }

    def subset(self, secondary_labels) -> "TrackProfiles":
        """Returns a copy holding the reference pass and the requested secondaries.

        Args:
            secondary_labels: Labels of the secondary passes to keep, or None to keep all.

        Returns:
            A new profile set restricted to the selected passes; ``self`` when nothing is selected.
        """
        if secondary_labels is None:
            return self

        keep = [0] + [1 + index for index in SecondarySelection.indices(self.labels, secondary_labels)]

        return TrackProfiles(
            labels        = [self.labels[index] for index in keep],
            horizontal    = self.horizontal[keep],
            vertical      = self.vertical[keep],
            azimuth_start = self.azimuth_start,
            track_files   = [self.track_files[index] for index in keep] if self.track_files else [],
        )

    def save(self, path: str | Path) -> Path:
        """Writes the profiles to a compressed npz file and returns the written path."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)

        with path.open("wb") as handle:
            np.savez_compressed(
                handle,
                labels        = np.array(self.labels),
                horizontal    = np.asarray(self.horizontal, dtype=np.float32),
                vertical      = np.asarray(self.vertical,   dtype=np.float32),
                azimuth_start = np.int64(self.azimuth_start),
                track_files   = np.array([str(f) for f in self.track_files]),
            )

        return path

    @classmethod
    def load(cls, path: str | Path) -> "TrackProfiles":
        """Loads profiles from the npz file written by :meth:`save`."""
        with np.load(Path(path)) as data:
            return cls(
                labels        = [str(label) for label in data["labels"]],
                horizontal    = np.asarray(data["horizontal"], dtype=float),
                vertical      = np.asarray(data["vertical"],   dtype=float),
                azimuth_start = int(data["azimuth_start"]),
                track_files   = [str(f) for f in data["track_files"]],
            )

    @classmethod
    def profiles_file(cls, dataset_dir: str | Path) -> Path:
        """Returns the canonical profiles file path inside a dataset directory."""
        return Path(dataset_dir) / "data" / cls.FILENAME
