"""Parsing, validation and storage of per-track F-SAR acquisition parameters.

The parameters come from the STEP processor as idl2xml files, one per pass and
polarisation. They are parsed into plain dictionaries, checked for a right-looking
geometry, and stored as a shared/per-track partition on disk.
"""

from __future__ import annotations

import json
import math
import xml.etree.ElementTree as ElementTree
from dataclasses import dataclass, field
from pathlib     import Path
from typing      import ClassVar

from tools.baselines.reading import PassProductResolver


class StepParameterFile:
    """Parses a STEP idl2xml parameter file into a nested dictionary.

    Attributes:
        path: Path of the XML parameter file.
        INTEGER_TYPES: IDL datatype names coerced to int.
        FLOAT_TYPES: IDL datatype names coerced to float.
    """

    INTEGER_TYPES = ("long", "int", "byte", "uint", "ulong", "short")
    FLOAT_TYPES   = ("double", "float")

    def __init__(self, path: str | Path) -> None:
        """Stores the path of the parameter file to parse."""
        self.path = Path(path)

    def _object_node(self, root: ElementTree.Element) -> ElementTree.Element:
        """Returns the top-level <object> block of the document.

        Args:
            root: Root <idl2xml> element.

        Returns:
            The <object> element holding the parameter list.

        Raises:
            ValueError: If the document has no <object> block.
        """
        node = root.find("object")

        if node is None:
            raise ValueError(f"{self.path} has no <object> parameter block under <idl2xml>")

        return node

    def _parameter(self, parameter_el: ElementTree.Element) -> tuple:
        """Returns the (name, value) pair of one <parameter> element, typed by its datatype."""
        name      = parameter_el.get("name")
        datatype  = parameter_el.find("datatype")
        value_el  = parameter_el.find("value")
        base_type = (datatype.text or "").strip().lower() if datatype is not None else "string"

        return name, self._value(value_el, base_type)

    def _value(self, value_el: ElementTree.Element, base_type: str):
        """Returns the value of a <value> element, recursing into nested objects.

        Args:
            value_el: The <value> element to interpret.
            base_type: IDL datatype name used to coerce scalar text.

        Returns:
            A nested dictionary for grouped values, the unwrapped "ptr" entry for
            single-pointer groups, or a coerced scalar or list.
        """
        nested_objects    = value_el.findall("object")
        nested_parameters = value_el.findall("parameter")

        if nested_objects:
            return self._group(nested_objects[0])

        if nested_parameters:
            group = self._group(value_el)
            return group["ptr"] if list(group) == ["ptr"] else group

        return self._coerce_text(value_el.text or "", base_type)

    def _group(self, object_el: ElementTree.Element) -> dict:
        """Returns the direct <parameter> children of an element as a name-to-value dictionary."""
        return {name: value for name, value in (self._parameter(p) for p in object_el.findall("parameter"))}

    def _coerce_text(self, text: str, base_type: str):
        """Returns the text of a value as a typed scalar, or a list for bracketed text."""
        stripped = text.strip()

        if stripped.startswith("[") and stripped.endswith("]"):
            tokens = [token for token in stripped[1:-1].split(",") if token.strip() != ""]
            return [self._coerce_scalar(token, base_type) for token in tokens]

        return self._coerce_scalar(stripped, base_type)

    def _coerce_scalar(self, token: str, base_type: str):
        """Returns a token as int, float or string according to its IDL datatype."""
        token = token.strip()

        if base_type in self.INTEGER_TYPES:
            return int(token)

        if base_type in self.FLOAT_TYPES:
            return float(token)

        return token

    def parse(self) -> dict:
        """Returns every top-level parameter of the file as a name-to-value dictionary."""
        root        = ElementTree.parse(self.path).getroot()
        object_node = self._object_node(root)

        return {name: value for name, value in (self._parameter(p) for p in object_node.findall("parameter"))}


class StepParameterResolver(PassProductResolver):
    """Locates the STEP parameter file of a pass for a given polarisation.

    Attributes:
        PRODUCT_SUBDIR: Subdirectory of a pass holding the parameter files.
        PRODUCT_PATTERNS: Glob patterns matching parameter files.
    """

    PRODUCT_SUBDIR   = Path("INF") / "INF-RDP"
    PRODUCT_PATTERNS = ("pp_*.xml",)

    def resolve_for_polarisation(self, pass_directory: str | Path, polarisation: str) -> Path:
        """Returns the single parameter file of a pass matching a polarisation.

        Args:
            pass_directory: Root directory of the pass.
            polarisation: Polarisation code, matched case-insensitively.

        Returns:
            Path of the matching pp_*.xml parameter file.

        Raises:
            FileNotFoundError: If no file matches the polarisation.
            ValueError: If more than one file matches.
        """
        directory  = Path(pass_directory) / self.PRODUCT_SUBDIR
        wanted     = polarisation.lower()
        candidates = sorted(directory.glob(self.PRODUCT_PATTERNS[0]))
        matches    = [candidate for candidate in candidates if self._polarisation_of(candidate) == wanted]

        if not matches:
            available = ", ".join(self._polarisation_of(candidate) for candidate in candidates) or "none"
            raise FileNotFoundError(f"No pp_*.xml for polarisation '{wanted}' under {directory} (available: {available})")

        if len(matches) > 1:
            raise ValueError(f"Multiple parameter files for polarisation '{wanted}' under {directory}: {[m.name for m in matches]}")

        return matches[0]


@dataclass
class TrackParameters:
    """Acquisition parameters of every track in a stack, the reference track first.

    Attributes:
        labels: Track labels in stack order, the reference first.
        parameters: Parsed parameter dictionary per track, aligned with labels.
        track_files: Source parameter files per track.
        FILENAME: Canonical file name of a saved parameter collection.
    """

    labels      : list
    parameters  : list
    track_files : list = field(default_factory=list)

    FILENAME : ClassVar[str] = "track_parameters.json"

    @property
    def reference(self) -> str:
        """Label of the reference track."""
        return self.labels[0]

    @property
    def n_tracks(self) -> int:
        """Number of tracks in the collection."""
        return len(self.labels)

    def validate_right_looking(self) -> None:
        """Checks that every track is right-looking.

        Raises:
            ValueError: If any track has antdir <= 0, since the kz formula
                assumes a right-looking geometry.
        """
        left = [label for label, params in zip(self.labels, self.parameters) if params["antdir"] <= 0]

        if left:
            raise ValueError(f"Tracks {left} are left-looking (antdir <= 0); the kz formula assumes a right-looking geometry, so left-looking stacks would train against sign-flipped physics. Left-looking data is not supported.")

    def derived(self) -> list:
        """Returns the derived geometry dictionary of every track, in stack order."""
        return [self._track_geometry(label, params) for label, params in zip(self.labels, self.parameters)]

    def _track_geometry(self, label: str, params: dict) -> dict:
        """Returns look side, angles and ranges derived from one track's raw parameters.

        Args:
            label: Track label, used in error messages.
            params: Raw parameter dictionary of the track.

        Returns:
            Dictionary of look side, depression angle in degrees, wavelength in
            metres, sensor and terrain heights in metres, near/far/reference
            slant ranges in metres, and near/far look angles in degrees.

        Raises:
            ValueError: If the sensor height above terrain is not positive and
                below the nearest slant range.
        """
        slant_range = params["r"]
        height      = params["h0"] - params["terrain"]
        near        = float(slant_range[0])
        far         = float(slant_range[-1])

        self.validate_height_above_terrain(height, min(near, far), label)

        return {
            "look_side"            : "right" if params["antdir"] > 0 else "left",
            "depression_angle_deg" : math.degrees(params["da"]),
            "wavelength_m"         : params["lambda"],
            "sensor_altitude_m"    : params["h0"],
            "terrain_height_m"     : params["terrain"],
            "slant_range_near_m"   : near,
            "slant_range_far_m"    : far,
            "slant_range_ref_m"    : params["rref"],
            "look_angle_near_deg"  : math.degrees(math.acos(height / near)),
            "look_angle_far_deg"   : math.degrees(math.acos(height / far)),
        }

    @staticmethod
    def validate_height_above_terrain(height: float, nearest_slant: float, label: str) -> None:
        """Checks the sensor height above terrain against the nearest slant range.

        Args:
            height: Sensor height above terrain in metres.
            nearest_slant: Shortest slant range of the track in metres.
            label: Track label, used in the error message.

        Raises:
            ValueError: If the height is not positive or reaches the nearest
                slant range, which would yield a zero look angle and infinite kz.
        """
        if height <= 0.0 or height >= nearest_slant:
            raise ValueError(f"Sensor height above terrain {height:.2f} m must be positive and below the nearest slant range {nearest_slant:.2f} m for track '{label}'; h0/terrain in the track parameters are corrupt, and clipping would silently yield a zero look angle and infinite kz.")

    def describe(self) -> dict:
        """Returns a table of stack size, look side, wavelength and per-track angles for logging."""
        geometry = self.derived()

        return {
            "Tracks"              : self.n_tracks,
            "Reference"           : self.reference,
            "Look side"           : geometry[0]["look_side"],
            "Wavelength [m]"      : f"{geometry[0]['wavelength_m']:.4f}",
            "Depression [deg]"    : ", ".join(f"{g['depression_angle_deg']:.2f}" for g in geometry),
            "Slant range ref [m]" : ", ".join(f"{g['slant_range_ref_m']:.1f}" for g in geometry),
            "Look angle [deg]"    : ", ".join(f"{g['look_angle_near_deg']:.1f}-{g['look_angle_far_deg']:.1f}" for g in geometry),
        }

    def _validate_key_sets(self) -> None:
        """Checks that every track carries the same parameter keys as the reference.

        Raises:
            ValueError: If any track has missing or extra keys, which would make
                a lossless shared/per-track partition impossible.
        """
        reference_keys = set(self.parameters[0])

        for label, params in zip(self.labels, self.parameters):
            missing = reference_keys - set(params)
            extra   = set(params) - reference_keys

            if missing or extra:
                raise ValueError(f"Track '{label}' parameter keys differ from reference '{self.reference}': missing {sorted(missing)}, extra {sorted(extra)}; a lossless shared/per-track partition is impossible.")

    def _partition(self) -> tuple:
        """Splits the parameters into values shared by all tracks and per-track values.

        Returns:
            Tuple of the shared parameter dictionary and a label-to-dictionary
            mapping of the parameters that differ between tracks.
        """
        self._validate_key_sets()

        shared       = {}
        varying_keys = []

        for key in self.parameters[0]:
            values = [params[key] for params in self.parameters]

            if all(value == values[0] for value in values):
                shared[key] = values[0]
            else:
                varying_keys.append(key)

        per_track = {label: {key: params[key] for key in varying_keys} for label, params in zip(self.labels, self.parameters)}

        return shared, per_track

    def to_payload(self) -> dict:
        """Returns the JSON payload holding labels, reference and the shared/per-track split."""
        shared, per_track = self._partition()

        return {
            "labels"      : list(self.labels),
            "reference"   : self.reference,
            "shared"      : shared,
            "per_track"   : per_track,
            "track_files" : [str(f) for f in self.track_files],
        }

    @classmethod
    def from_payload(cls, payload: dict) -> "TrackParameters":
        """Rebuilds the collection by merging the shared and per-track parameter blocks."""
        shared     = payload["shared"]
        parameters = [{**shared, **payload["per_track"][label]} for label in payload["labels"]]

        return cls(
            labels      = list(payload["labels"]),
            parameters  = parameters,
            track_files = list(payload["track_files"]),
        )

    def save(self, path: str | Path) -> Path:
        """Writes the payload as indented JSON and returns the written path."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_payload(), indent=4), encoding="utf-8")

        return path

    @classmethod
    def load(cls, path: str | Path) -> "TrackParameters":
        """Returns the parameter collection stored in a JSON file written by save()."""
        return cls.from_payload(json.loads(Path(path).read_text(encoding="utf-8")))


class TrackParameterCollector:
    """Parses the parameter file of every track of a stack into a TrackParameters.

    Attributes:
        track_paths: Mapping of track label to parameter file path.
    """

    def __init__(self, track_paths: dict) -> None:
        """Stores the per-label parameter file paths.

        Args:
            track_paths: Mapping of track label to parameter file path, in stack
                order with the reference first.
        """
        self.track_paths = {label: Path(path) for label, path in track_paths.items()}

    @classmethod
    def from_pass_directories(cls, pass_directories: list, polarisation: str) -> "TrackParameterCollector":
        """Builds a collector by resolving one parameter file per pass directory.

        Args:
            pass_directories: Pass root directories in stack order, reference first.
            polarisation: Polarisation code to resolve within each pass.

        Returns:
            Collector holding one parameter file per resolved track label.

        Raises:
            ValueError: If two pass directories resolve to the same label, which
                would silently drop a track.
        """
        resolver = StepParameterResolver()
        labels   = [resolver.label(str(directory)) for directory in pass_directories]

        duplicates = sorted({label for label in labels if labels.count(label) > 1})
        if duplicates:
            raise ValueError(f"Pass directories resolve to duplicate labels {duplicates}; every pass must map to a unique label or tracks would be silently dropped.")

        track_paths = {label: resolver.resolve_for_polarisation(directory, polarisation) for label, directory in zip(labels, pass_directories)}

        return cls(track_paths)

    def collect(self) -> TrackParameters:
        """Parses every track parameter file and returns the validated collection.

        Returns:
            Track parameters in the order of track_paths.

        Raises:
            ValueError: If any track is left-looking.
        """
        labels     = list(self.track_paths.keys())
        files      = [self.track_paths[label] for label in labels]
        parameters = [StepParameterFile(path).parse() for path in files]

        collected = TrackParameters(labels=labels, parameters=parameters, track_files=[str(f) for f in files])
        collected.validate_right_looking()

        return collected
