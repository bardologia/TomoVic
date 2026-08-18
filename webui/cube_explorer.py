"""Interactive server-side backend for the web UI cube explorer tabs.

Opens the tomographic cubes written by inference (prediction, ground truth,
Capon reduced and the full raw tomogram), stitches cross-validation folds into a
single azimuth mosaic, and renders slices, planes, parameter maps, metric
overlays and geocoded point clouds as PNG or packed binary payloads. Cubes are
indexed by elevation bin, azimuth pixel and range pixel; elevation axes are in
metres and geocoded positions in ECEF metres.
"""

from __future__ import annotations

import io
import json
import math
import re
import threading
from datetime import datetime
from pathlib  import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from skimage.metrics import structural_similarity as ssim

from catalog_roots              import CatalogRoots, RunScanner
from lru_cache                  import LruCache
from tools.loss.param_loss      import ParamMatcher
from tools.runtime.completion   import CompletionMarker
from tools.reporting.plotting   import PlotBase
from tools.sar.geocoding        import SceneGeocoder
from tools.sar.track_parameters import TrackParameters
from web_logger                 import WebLogger


class SliceFigureArchiver(PlotBase):
    """Renders publication-styled slice and transect figures to disk.

    Wraps the shared plotting base so every saved cut carries axis labels, an
    elevation axis in metres and a colourbar, using the paper style regardless of
    the style active elsewhere in the process.
    """

    LABELS = {
        "pred"    : "Prediction",
        "predb"   : "Prediction B",
        "diff"    : "Prediction A − B",
        "gt"      : "GT (Gaussian)",
        "reduced" : "Capon reduced",
        "full"    : "Capon full (raw)",
    }

    def render(self, data: np.ndarray, heights: np.ndarray, vmin: float, vmax: float, source: str, axis: str, az: int, rg: int, space: str, path: Path, cmap: str = "jet", label: str | None = None) -> Path:
        """Saves one elevation cut through the cube as a figure.

        Args:
            data: Cut of shape (elevation bins, samples along the free axis).
            heights: Elevation axis in metres, ascending, one entry per row of data.
            vmin: Lower colour limit.
            vmax: Upper colour limit.
            source: Cube key, one of the keys of LABELS.
            axis: "range" for a fixed range column, "azimuth" for a fixed azimuth row.
            az: Azimuth pixel index of the cut.
            rg: Range pixel index of the cut.
            space: "normalized" when columns were peak-normalised, else "physical".
            path: Destination PNG path.
            cmap: Matplotlib colormap name.
            label: Optional run label prefixed to the title.

        Returns:
            The path the figure was written to.
        """
        x_label   = "azimuth index" if axis == "range" else "range index"
        title_pos = f"range = {rg}" if axis == "range" else f"azimuth = {az}"
        y_label   = "elevation bin" if source == "full" else "elevation [m]"
        cbar      = "intensity (per-column normalised)" if space == "normalized" else "intensity"
        extent    = [0, int(data.shape[1]), float(heights[0]), float(heights[-1])]
        title     = f"{self.LABELS[source]} — {title_pos}" if label is None else f"{label} — {self.LABELS[source]} — {title_pos}"

        previous = PlotBase.style
        PlotBase.use_style("paper")
        try:
            return self._imshow_figure(
                data,
                x_label        = x_label,
                y_label        = y_label,
                title          = title,
                cmap           = cmap,
                vmin           = vmin,
                vmax           = vmax,
                extent         = extent,
                origin         = "lower",
                colorbar_label = cbar,
                figsize        = self.figsize(self.FULL_WIDTH),
                path           = path,
            )
        finally:
            PlotBase.use_style(previous)

    def render_transect(self, data: np.ndarray, heights: np.ndarray, vmin: float, vmax: float, source: str, start: tuple, end: tuple, space: str, path: Path, cmap: str = "jet") -> Path:
        """Saves an elevation section sampled along an arbitrary azimuth-range line.

        Args:
            data: Cut of shape (elevation bins, samples along the transect).
            heights: Elevation axis in metres, ascending, one entry per row of data.
            vmin: Lower colour limit.
            vmax: Upper colour limit.
            source: Cube key, one of the keys of LABELS.
            start: (azimuth, range) pixel index where the transect begins.
            end: (azimuth, range) pixel index where the transect ends.
            space: "normalized" when columns were peak-normalised, else "physical".
            path: Destination PNG path.
            cmap: Matplotlib colormap name.

        Returns:
            The path the figure was written to.
        """
        cbar   = "intensity (per-column normalised)" if space == "normalized" else "intensity"
        extent = [0, int(data.shape[1]), float(heights[0]), float(heights[-1])]

        previous = PlotBase.style
        PlotBase.use_style("paper")
        try:
            return self._imshow_figure(
                data,
                x_label        = "sample along transect",
                y_label        = "elevation bin" if source == "full" else "elevation [m]",
                title          = f"{self.LABELS[source]} — transect az{start[0]},rg{start[1]} to az{end[0]},rg{end[1]}",
                cmap           = cmap,
                vmin           = vmin,
                vmax           = vmax,
                extent         = extent,
                origin         = "lower",
                colorbar_label = cbar,
                figsize        = self.figsize(self.FULL_WIDTH),
                path           = path,
            )
        finally:
            PlotBase.use_style(previous)


class StitchedRaw:
    """Lazy elevation-plane view over azimuth blocks belonging to different folds.

    Presents several per-fold cubes as one array of shape (elevation, azimuth,
    range); a plane is materialised only when indexed, and azimuth rows no fold
    covers stay NaN.

    Attributes:
        blocks: Pairs of (azimuth offset into the mosaic, per-fold cube).
        shape: Shape of the stitched cube, (elevation, azimuth, range).
        dtype: Element type of the assembled planes.
    """

    def __init__(self, blocks: list, shape: tuple, dtype: np.dtype) -> None:
        """Stores the fold blocks and the shape of the mosaic they compose."""
        self.blocks = blocks
        self.shape  = shape
        self.dtype  = dtype

    @property
    def ndim(self) -> int:
        """Number of axes of the stitched cube."""
        return len(self.shape)

    def __getitem__(self, index: int) -> np.ndarray:
        """Returns elevation plane `index` of shape (azimuth, range), NaN in gaps."""
        plane = np.full(self.shape[1:], np.nan, dtype=self.dtype)
        for offset, raw in self.blocks:
            plane[offset:offset + raw.shape[1]] = np.asarray(raw[index])
        return plane


class StampReader:
    """Reads the cubes, metrics and metric maps of one inference stamp directory.

    A stamp directory lives at ``<run>/inference/<stamp>`` and holds a ``cubes``
    folder plus ``metrics.json``.

    Attributes:
        stamp_dir: Directory of the completed inference stamp.
    """

    METRIC_EXCLUDED = ("_curves", "params_")

    def __init__(self, stamp_dir: Path) -> None:
        """Stores the inference stamp directory to read from."""
        self.stamp_dir = stamp_dir

    @property
    def run_dir(self) -> Path:
        """Run directory that owns this inference stamp."""
        return self.stamp_dir.parent.parent

    @property
    def save_dir(self) -> Path:
        """Directory figures saved from this cube are written under."""
        return self.run_dir

    @property
    def where(self) -> str:
        """Human-readable location used in error messages."""
        return str(self.stamp_dir)

    def display(self) -> dict:
        """Returns the run and stamp names shown in the web UI."""
        return {"run": self.run_dir.name, "stamp": self.stamp_dir.name}

    def mosaic_meta(self) -> dict | None:
        """Returns None, since a single stamp is not a fold mosaic."""
        return None

    def metrics(self) -> dict:
        """Returns the parsed ``metrics.json`` payload of the stamp.

        Raises:
            FileNotFoundError: If the stamp holds no ``metrics.json``.
        """
        path = self.stamp_dir / "metrics.json"
        if not path.is_file():
            raise FileNotFoundError(f"metrics.json missing in {self.stamp_dir}; rerun inference to regenerate it")

        return json.loads(path.read_text(encoding="utf-8"))

    def curves(self, name: str) -> np.ndarray | None:
        """Memory-maps a curve cube of shape (elevation, azimuth, range).

        Args:
            name: Cube key such as "pred", "gt" or "reduced".

        Returns:
            The memory-mapped cube, or None when the stamp carries no such cube.
        """
        path = self.stamp_dir / "cubes" / f"{name}_curves.npy"
        if not path.is_file():
            return None

        return np.load(path, mmap_mode="r")

    def param_block(self, name: str) -> np.ndarray | None:
        """Loads a Gaussian parameter cube of shape (3 * n_slots, azimuth, range).

        Channels run amplitude, mu in metres and sigma in metres per slot.

        Args:
            name: Parameter source, "pred" or "gt".

        Returns:
            The float32 parameter cube, or None when the stamp stores none.
        """
        path = self.stamp_dir / "cubes" / f"params_{name}.npy"
        if not path.is_file():
            return None

        return np.asarray(np.load(path), dtype=np.float32)

    def metric_maps(self, n_az: int, n_rg: int) -> dict:
        """Loads every per-pixel metric map matching the cube footprint.

        Args:
            n_az: Azimuth extent the map must have, in pixels.
            n_rg: Range extent the map must have, in pixels.

        Returns:
            Mapping from map name to a float32 array of shape (n_az, n_rg); curve
            and parameter cubes are skipped, as are arrays of other shapes.
        """
        maps = {}
        for path in sorted((self.stamp_dir / "cubes").glob("*.npy")):
            if any(marker in path.name for marker in self.METRIC_EXCLUDED):
                continue

            raw = np.load(path, mmap_mode="r")
            if raw.ndim != 2 or raw.shape != (n_az, n_rg):
                continue

            maps[path.stem] = np.asarray(raw, dtype=np.float32)

        return maps


class FoldMosaic:
    """Presents the per-fold inference cubes of one cross-validation run as one cube.

    Exposes the same reader interface as StampReader, stitching the folds along
    azimuth after checking that they agree on elevation axis, range span, tracks
    and preprocessing run.

    Attributes:
        cv_root: Root directory of the cross-validation run.
        split: Split name the fold inferences were run on.
        seed: Seed subdirectory name when the folds are seed sweeps, else None.
        members: Tuples of (fold index, fold directory name, stamp directory).
        plan: Cached mosaic layout, filled on first resolution.
    """

    SEP     = "::cv::"
    FOLD_RE = re.compile(r"(?:^|_)fold_(\d+)$")
    SEED_RE = re.compile(r"^seed\d+$")

    def __init__(self, cv_root: Path, split: str, seed: str | None, members: list) -> None:
        """Stores the fold members of one cross-validation split and seed."""
        self.cv_root = cv_root
        self.split   = split
        self.seed    = seed
        self.members = members
        self.plan    = None

    @classmethod
    def member_of(cls, stamp_dir: Path) -> tuple | None:
        """Classifies a stamp directory as a fold of a cross-validation run.

        Args:
            stamp_dir: Candidate inference stamp directory.

        Returns:
            The (cv root, split, seed) key the stamp belongs to, or None when it
            does not sit under ``<cv root>/folds/fold_N`` or is incomplete.
        """
        run_dir  = stamp_dir.parent.parent
        seed     = run_dir.name if cls.SEED_RE.match(run_dir.name) else None
        fold_dir = run_dir.parent if seed else run_dir

        if stamp_dir.parent.name != "inference":
            return None
        if cls.FOLD_RE.search(fold_dir.name) is None:
            return None
        if fold_dir.parent.name != "folds":
            return None

        cv_root = fold_dir.parent.parent
        if not (cv_root / "pipeline").is_dir():
            return None
        if not CompletionMarker.is_complete(stamp_dir):
            return None

        return cv_root, CompletionMarker.payload(stamp_dir)["split"], seed

    @classmethod
    def catalog(cls, root: Path, entries: list) -> list:
        """Derives the mosaic catalogue entries implied by a list of stamp entries.

        Args:
            root: Runs root the entry names are reported relative to.
            entries: Stamp catalogue entries, each carrying an ``id`` path.

        Returns:
            One catalogue entry per (cv root, split, seed) group found under root,
            sorted by composite id descending.
        """
        groups = {}
        for entry in entries:
            member = cls.member_of(Path(entry["id"]))
            if member is not None:
                groups.setdefault(member, []).append(entry)

        mosaics = []
        for (cv_root, split, seed), members in groups.items():
            if not cv_root.is_relative_to(root):
                continue

            mosaics.append({
                "id"    : cls.compose_id(cv_root, split, seed),
                "run"   : cv_root.name,
                "group" : str(cv_root.relative_to(root).parent),
                "stamp" : cls.label(split, seed),
                "cv"    : {"split": split, "seed": seed, "folds": len(members)},
            })

        mosaics.sort(key=lambda entry: entry["id"], reverse=True)
        return mosaics

    @staticmethod
    def label(split: str, seed: str | None) -> str:
        """Returns the display label of a mosaic over the given split and seed."""
        parts = ["all folds", split] + ([seed] if seed else [])
        return " · ".join(parts)

    @classmethod
    def compose_id(cls, cv_root: Path, split: str, seed: str | None) -> str:
        """Returns the cube id encoding a cv root, split and optional seed."""
        tail = split if seed is None else f"{split}::{seed}"
        return f"{cv_root}{cls.SEP}{tail}"

    @classmethod
    def parse(cls, cube_id: str) -> tuple | None:
        """Decodes a mosaic cube id.

        Args:
            cube_id: Identifier as produced by ``compose_id``.

        Returns:
            The (cv root, split, seed) triple, or None when the id is not a mosaic
            id or is malformed.
        """
        if cls.SEP not in cube_id:
            return None

        head, tail = cube_id.split(cls.SEP, 1)
        parts      = tail.split("::")
        if not head or not parts[0] or len(parts) > 2:
            return None
        if len(parts) == 2 and cls.SEED_RE.match(parts[1]) is None:
            return None

        seed = parts[1] if len(parts) == 2 else None
        return Path(head).resolve(), parts[0], seed

    @classmethod
    def open(cls, cv_root: Path, split: str, seed: str | None) -> "FoldMosaic | None":
        """Builds a mosaic from the latest completed inference of every fold.

        Args:
            cv_root: Root directory of the cross-validation run.
            split: Split name whose fold inferences are gathered.
            seed: Seed subdirectory to descend into, or None for plain folds.

        Returns:
            The mosaic ordered by fold index, or None when the run holds no folds.
        """
        from pipelines.shared.inference.metadata import CompletedInference

        folds_dir = cv_root / "folds"
        if not folds_dir.is_dir():
            return None

        members = []
        for child in sorted(folds_dir.iterdir()):
            match = cls.FOLD_RE.search(child.name)
            if match is None or not child.is_dir():
                continue

            run_dir = child / seed if seed else child
            members.append((int(match.group(1)), child.name, CompletedInference.latest(run_dir / "inference", split)))

        if not members:
            return None

        members.sort()
        return cls(cv_root, split, seed, members)

    @property
    def run_dir(self) -> Path:
        """Run directory of the first fold, used to resolve dataset metadata."""
        return self._resolve()["run_dir"]

    @property
    def save_dir(self) -> Path:
        """Directory figures saved from the mosaic are written under."""
        return self.cv_root

    @property
    def where(self) -> str:
        """Human-readable location used in error messages."""
        return f"{self.cv_root} ({self.label(self.split, self.seed)})"

    def display(self) -> dict:
        """Returns the run and mosaic labels shown in the web UI."""
        return {"run": self.cv_root.name, "stamp": self.label(self.split, self.seed)}

    def mosaic_meta(self) -> dict:
        """Returns the split, seed, fold count and uncovered azimuth gaps."""
        return {"split": self.split, "seed": self.seed, "n_folds": len(self.members), "gaps": self._resolve()["gaps"]}

    def metrics(self) -> dict:
        """Returns the merged metrics payload covering the whole mosaic footprint."""
        return self._resolve()["metrics"]

    def curves(self, name: str) -> StitchedRaw | None:
        """Returns a lazy stitched curve cube over all folds.

        Args:
            name: Cube key such as "pred", "gt" or "reduced".

        Returns:
            A StitchedRaw of shape (elevation, azimuth, range), or None when no
            fold carries the cube.

        Raises:
            ValueError: If only some folds carry the cube, or a fold's cube shape
                does not match its azimuth block or the elevation bin count.
        """
        plan    = self._resolve()
        readers = [(block, StampReader(block["stamp"]).curves(name)) for block in plan["blocks"]]

        missing = [block["name"] for block, raw in readers if raw is None]
        if len(missing) == len(readers):
            return None
        if missing:
            raise ValueError(f"source '{name}' is missing from folds {missing}; regenerate those fold inferences")

        blocks = []
        n_elev = None
        for block, raw in readers:
            extent = (block["az_end"] - block["az_start"], plan["n_rg"])
            if raw.ndim != 3 or raw.shape[1:] != extent:
                raise ValueError(f"fold {block['name']} source '{name}' shape {tuple(raw.shape)} does not match its fold region {extent}")
            if n_elev is None:
                n_elev = int(raw.shape[0])
            elif raw.shape[0] != n_elev:
                raise ValueError(f"fold {block['name']} source '{name}' has {raw.shape[0]} elevation bins but fold {plan['blocks'][0]['name']} has {n_elev}")

            blocks.append((block["az_start"] - plan["az0"], raw))

        dtype = np.result_type(np.float32, *[raw.dtype for _, raw in readers])
        return StitchedRaw(blocks, (n_elev, plan["n_az"], plan["n_rg"]), dtype)

    def param_block(self, name: str) -> np.ndarray | None:
        """Stitches the per-fold Gaussian parameter cubes into one mosaic.

        Args:
            name: Parameter source, "pred" or "gt".

        Returns:
            Float32 array of shape (3 * n_slots, azimuth, range) with NaN in
            uncovered azimuth rows, or None when no fold carries the block.

        Raises:
            ValueError: If only some folds carry the block, the folds disagree on
                the slot count, or a fold's block does not match its azimuth block.
        """
        plan    = self._resolve()
        readers = [(block, StampReader(block["stamp"]).param_block(name)) for block in plan["blocks"]]

        missing = [block["name"] for block, raw in readers if raw is None]
        if len(missing) == len(readers):
            return None
        if missing:
            raise ValueError(f"params_{name} is missing from folds {missing}; regenerate those fold inferences")

        rows = {raw.shape[0] for _, raw in readers}
        if len(rows) > 1:
            raise ValueError(f"folds disagree on the params_{name} slot count: {sorted(rows)}")

        canvas = np.full((rows.pop(), plan["n_az"], plan["n_rg"]), np.nan, dtype=np.float32)
        for block, raw in readers:
            extent = (block["az_end"] - block["az_start"], plan["n_rg"])
            if raw.ndim != 3 or raw.shape[1:] != extent:
                raise ValueError(f"fold {block['name']} params_{name} shape {tuple(raw.shape)} does not match its fold region {extent}")

            offset = block["az_start"] - plan["az0"]
            canvas[:, offset:offset + raw.shape[1]] = raw

        return canvas

    def metric_maps(self, n_az: int, n_rg: int) -> dict:
        """Stitches the per-fold metric maps into mosaic-wide maps.

        Args:
            n_az: Azimuth extent of the mosaic, in pixels.
            n_rg: Range extent of the mosaic, in pixels.

        Returns:
            Mapping from map name to a float32 array of shape (n_az, n_rg), NaN in
            uncovered azimuth rows.

        Raises:
            ValueError: If the folds do not all carry the same set of metric maps.
        """
        plan     = self._resolve()
        per_fold = [(block, StampReader(block["stamp"]).metric_maps(block["az_end"] - block["az_start"], n_rg)) for block in plan["blocks"]]

        keys = set(per_fold[0][1])
        for block, maps in per_fold[1:]:
            if set(maps) != keys:
                raise ValueError(f"fold {block['name']} carries metric maps {sorted(set(maps))} but fold {per_fold[0][0]['name']} carries {sorted(keys)}")

        stitched = {}
        for key in keys:
            canvas = np.full((n_az, n_rg), np.nan, dtype=np.float32)
            for block, maps in per_fold:
                offset = block["az_start"] - plan["az0"]
                canvas[offset:offset + maps[key].shape[0]] = maps[key]
            stitched[key] = canvas

        return stitched

    def _resolve(self) -> dict:
        """Computes and caches the mosaic layout from the fold metrics payloads.

        Returns:
            Dict with the merged ``metrics``, the ordered azimuth ``blocks``, the
            uncovered azimuth ``gaps``, the mosaic origin ``az0``, its ``n_az`` and
            ``n_rg`` extents and the first fold's ``run_dir``.

        Raises:
            FileNotFoundError: If a fold has no completed inference cube.
            ValueError: If folds disagree on elevation axis, range span, tracks or
                preprocessing run, or if their azimuth blocks overlap.
        """
        if self.plan is not None:
            return self.plan

        for _, name, stamp in self.members:
            if stamp is None or not (stamp / "cubes" / "pred_curves.npy").is_file():
                raise FileNotFoundError(f"fold {name} has no completed '{self.split}' inference cube; run cross-validation inference for every fold")

        payloads = [StampReader(stamp).metrics() for _, _, stamp in self.members]

        first   = payloads[0]
        anchor  = self.members[0][1]
        axis    = (float(first["x_axis_min"]), float(first["x_axis_max"]))
        rg_span = tuple(int(v) for v in first["split_region"][2:])
        tracks  = first.get("tracks")

        for (_, name, _), payload in zip(self.members[1:], payloads[1:]):
            if (float(payload["x_axis_min"]), float(payload["x_axis_max"])) != axis:
                raise ValueError(f"fold {name} covers elevation axis [{payload['x_axis_min']}, {payload['x_axis_max']}] but fold {anchor} covers {list(axis)}")
            if tuple(int(v) for v in payload["split_region"][2:]) != rg_span:
                raise ValueError(f"fold {name} covers range span {payload['split_region'][2:]} but fold {anchor} covers {list(rg_span)}")
            if payload.get("tracks") != tracks:
                raise ValueError(f"fold {name} was inferred from different tracks than fold {anchor}")

        placed = sorted(zip(self.members, payloads), key=lambda pair: int(pair[1]["split_region"][0]))

        blocks   = []
        gaps     = []
        previous = None
        for (_, name, stamp), payload in placed:
            az_start, az_end = (int(v) for v in payload["split_region"][:2])
            if previous is not None and az_start < previous:
                raise ValueError(f"fold {name} azimuth block [{az_start}, {az_end}) overlaps the previous fold; the fold plan is inconsistent")
            if previous is not None and az_start > previous:
                gaps.append([previous, az_start])

            previous = az_end
            blocks.append({"name": name, "stamp": stamp, "az_start": az_start, "az_end": az_end})

        preprocs = set()
        for _, name, stamp in self.members:
            path = stamp.parent.parent / "meta" / "dataset_creation_config.json"
            preprocs.add(json.loads(path.read_text(encoding="utf-8"))["preprocessing_run_directory"] if path.is_file() else None)

        if len(preprocs) > 1:
            raise ValueError(f"folds disagree on the preprocessing run: {sorted(str(v) for v in preprocs)}")

        az0 = blocks[0]["az_start"]
        az1 = blocks[-1]["az_end"]

        metrics = {
            "x_axis_min"   : axis[0],
            "x_axis_max"   : axis[1],
            "split_region" : [az0, az1, rg_span[0], rg_span[1]],
        }
        if tracks is not None:
            metrics["tracks"] = tracks

        self.plan = {
            "metrics" : metrics,
            "blocks"  : blocks,
            "gaps"    : gaps,
            "az0"     : az0,
            "n_az"    : az1 - az0,
            "n_rg"    : rg_span[1] - rg_span[0],
            "run_dir" : self.members[0][2].parent.parent,
        }
        return self.plan


class CubeExplorer:
    """Loads one tomographic cube at a time and serves views of it to the web UI.

    Holds a single loaded cube in memory behind a lock: its per-source curve
    cubes, the primary SLC amplitude map in dB, Gaussian parameter blocks, metric
    maps, the cropped DEM and the geocoding context. Loading runs in a background
    thread whose progress is polled through ``load_status``.

    Attributes:
        logger: Web logger for load and save reporting.
        archiver: Renderer used when slices are saved to disk.
        roots: Catalogued run roots that bound which cube ids may be opened.
        scanner: Scanner listing inference stamps under a root.
        lock: Guards the loaded cube and the load status.
        loaded: Currently loaded cube state, or None.
        status: Load state machine payload polled by the front end.
    """

    SOURCES             = ("pred", "predb", "diff", "gt", "reduced", "full")
    PARAM_SOURCES       = ("pred", "gt")
    CLOUD_CURVE_SOURCES = ("reduced", "full")
    GLOBE_SOURCES       = ("pred", "gt", "reduced")
    PARAM_FIELDS        = {"amp": 0, "mu": 1, "sigma": 2}
    PARAM_BAD           = "#10151a"

    CMAPS = ("jet", "viridis", "inferno", "turbo", "gray")

    METRIC_LABELS = {
        "pixel_mse"                : "MSE",
        "pixel_mae"                : "MAE",
        "pixel_r2"                 : "R2",
        "pixel_cos"                : "cosine",
        "pixel_peak"               : "peak shift",
        "physics_coherence_error"  : "coherence err",
        "physics_covariance_error" : "covariance err",
        "physics_valid_mask"       : "valid mask",
        "seed_std_profile"         : "seed std profile",
        "seed_std_amp"             : "seed std amp",
        "seed_std_mu"              : "seed std mu",
        "seed_std_sigma"           : "seed std sigma",
        "label_r2"                 : "label R2",
        "flip_consistency"         : "flip disagreement",
        "failure_mode"             : "failure mode",
        "label_suspect"            : "label suspect",
    }

    def __init__(self, logger: WebLogger) -> None:
        """Builds the explorer with an idle load status and no cube loaded."""
        self.logger   = logger
        self.archiver = SliceFigureArchiver()
        self.roots    = CatalogRoots()
        self.scanner  = RunScanner(self.roots)
        self.lock     = threading.Lock()
        self.loaded   = None
        self.status   = {"state": "idle", "id": None, "progress": 0.0, "stage": "", "error": ""}

    def list_cubes(self, base: str, include_cv: bool = False) -> dict:
        """Lists the inference cubes available under a runs root.

        Args:
            base: Runs root to scan.
            include_cv: When True, cross-validation fold mosaics are prepended to
                the individual fold stamps.

        Returns:
            Dict with ``ok``, the resolved ``root`` and the ``cubes`` catalogue.
        """
        scanned = self.scanner.stamps(base)
        if not scanned["ok"]:
            return {"ok": False, "error": scanned["error"], "cubes": []}

        cubes = scanned["entries"]
        if include_cv:
            cubes = FoldMosaic.catalog(Path(scanned["root"]), cubes) + cubes

        return {"ok": True, "root": scanned["root"], "cubes": cubes}

    def start_load(self, cube_id: str) -> dict:
        """Starts loading a cube in a background thread.

        Args:
            cube_id: Stamp directory path or a fold mosaic composite id.

        Returns:
            Dict with ``ok`` True once the load was started or the cube is already
            loaded, otherwise ``ok`` False with the reason.
        """
        reader = self._open_source(cube_id)
        if reader is None:
            return {"ok": False, "error": f"unknown cube id: {cube_id}"}

        with self.lock:
            if self.status["state"] == "loading":
                return {"ok": False, "error": f"a load is already running for {self.status['id']}"}
            if self.status["state"] == "ready" and self.status["id"] == cube_id and self.loaded is not None:
                return {"ok": True}

            self.loaded = None
            self.status = {"state": "loading", "id": cube_id, "progress": 0.0, "stage": "scanning sources", "error": ""}

        threading.Thread(target=self._load_worker, args=(cube_id, reader), daemon=True).start()
        return {"ok": True}

    def load_status(self) -> dict:
        """Returns the current load state, with the cube metadata once ready."""
        with self.lock:
            payload = dict(self.status)
            if payload["state"] == "ready" and self.loaded is not None:
                payload["cube"] = self.loaded["meta"]
        return payload

    def primary_png(self, cube_id: str) -> bytes | None:
        """Renders the primary SLC amplitude map in dB as a greyscale PNG.

        Args:
            cube_id: Id of the loaded cube.

        Returns:
            PNG bytes of the (azimuth, range) map, or None when that cube is not
            the loaded one.
        """
        with self.lock:
            if self.loaded is None or self.loaded["id"] != cube_id:
                return None
            primary    = self.loaded["primary"]
            vmin, vmax = self.loaded["primary_clim"]

        buf = io.BytesIO()
        plt.imsave(buf, primary, cmap="gray", vmin=float(vmin), vmax=float(vmax), format="png")
        return buf.getvalue()

    def attach_second(self, cube_id: str, other_id: str) -> dict:
        """Attaches a second run's prediction cube for side-by-side comparison.

        Adds a ``predb`` source and a signed ``diff`` source holding
        prediction A minus prediction B.

        Args:
            cube_id: Id of the loaded cube.
            other_id: Id of the cube to compare against.

        Returns:
            Dict with ``ok`` and the updated cube metadata, or ``ok`` False when
            the ids clash or the two cubes disagree on shape or elevation axis.
        """
        with self.lock:
            if self.loaded is None or self.loaded["id"] != cube_id:
                return {"ok": False, "error": "cube not loaded"}
            pred = self.loaded["entries"]["pred"]

        other = self._open_source(other_id)
        if other is None:
            return {"ok": False, "error": f"unknown cube id: {other_id}"}
        if other_id == cube_id:
            return {"ok": False, "error": "pick a different inference result to compare against"}

        try:
            raw = other.curves("pred")
            if raw.shape != pred["cube"].shape:
                return {"ok": False, "error": f"comparison cube shape {tuple(raw.shape)} does not match {tuple(pred['cube'].shape)}"}

            other_axis = self._curve_axis(other, raw.shape[0])
            if not np.allclose(other_axis, pred["x_axis"]):
                return {"ok": False, "error": "comparison cube covers a different elevation axis"}

            predb = self._ingest(raw, pred["x_axis"], lambda: None)
        except (ValueError, FileNotFoundError) as exc:
            return {"ok": False, "error": str(exc)}

        diff = self._diff_entry(pred, predb)

        with self.lock:
            if self.loaded is None or self.loaded["id"] != cube_id:
                return {"ok": False, "error": "cube not loaded"}

            self.loaded["entries"]["predb"] = predb
            self.loaded["entries"]["diff"]  = diff

            meta = dict(self.loaded["meta"])
            meta["sources"]   = [s for s in self.SOURCES if s in self.loaded["entries"]]
            meta["n_elev"]    = {s: int(self.loaded["entries"][s]["cube"].shape[0]) for s in self.loaded["entries"]}
            meta["intensity"] = {s: [e["vmin"], e["vmax"]] for s, e in self.loaded["entries"].items()}
            meta["attached"]  = {"id": other_id, **other.display()}
            self.loaded["meta"] = meta

        self.logger.ok(f"attached comparison cube: {other_id}")
        return {"ok": True, "cube": meta}

    def detach_second(self, cube_id: str) -> dict:
        """Drops the attached comparison cube and its difference source.

        Args:
            cube_id: Id of the loaded cube.

        Returns:
            Dict with ``ok`` and the updated cube metadata, or ``ok`` False when
            that cube is not the loaded one.
        """
        with self.lock:
            if self.loaded is None or self.loaded["id"] != cube_id:
                return {"ok": False, "error": "cube not loaded"}

            self.loaded["entries"].pop("predb", None)
            self.loaded["entries"].pop("diff", None)

            meta = dict(self.loaded["meta"])
            meta["sources"]   = [s for s in self.SOURCES if s in self.loaded["entries"]]
            meta["n_elev"]    = {s: int(self.loaded["entries"][s]["cube"].shape[0]) for s in self.loaded["entries"]}
            meta["intensity"] = {s: [e["vmin"], e["vmax"]] for s, e in self.loaded["entries"].items()}
            meta["attached"]  = None
            self.loaded["meta"] = meta

        return {"ok": True, "cube": meta}

    @staticmethod
    def _diff_entry(pred: dict, predb: dict) -> dict:
        """Builds the signed difference entry between two prediction cubes.

        Args:
            pred: Loaded entry for prediction A.
            predb: Loaded entry for prediction B, on the same elevation axis.

        Returns:
            An entry whose cube is A minus B, with symmetric colour limits set to
            the 99th percentile of the absolute difference over a subsample.
        """
        cube = pred["cube"] - predb["cube"]

        sample = cube[:, :: max(1, cube.shape[1] // 256), :: max(1, cube.shape[2] // 256)]
        sample = np.abs(sample[np.isfinite(sample)])
        peak   = float(np.percentile(sample, 99.0)) if sample.size else 1.0
        peak   = peak if peak > 0.0 else 1.0

        return {
            "cube"      : cube,
            "x_axis"    : pred["x_axis"],
            "vmin"      : -peak,
            "vmax"      : peak,
            "diverging" : True,
        }

    def profiles(self, cube_id: str, az: int, rg: int) -> dict:
        """Returns the elevation profile of every source at one pixel.

        Args:
            cube_id: Id of the loaded cube.
            az: Azimuth pixel index, clipped into range.
            rg: Range pixel index, clipped into range.

        Returns:
            Dict with ``ok``, the clipped ``az`` and ``rg`` and a ``sources`` map
            from source name to ascending ``heights`` in metres and ``values``.
        """
        with self.lock:
            if self.loaded is None or self.loaded["id"] != cube_id:
                return {"ok": False, "error": "cube not loaded"}
            entries = self.loaded["entries"]
            meta    = self.loaded["meta"]

        az = int(np.clip(az, 0, meta["n_az"] - 1))
        rg = int(np.clip(rg, 0, meta["n_rg"] - 1))

        sources = {}
        for source, entry in entries.items():
            order   = np.argsort(entry["x_axis"])
            heights = np.asarray(entry["x_axis"])[order]
            values  = entry["cube"][:, az, rg][order]
            sources[source] = {"heights": heights.tolist(), "values": values.astype(float).tolist()}

        return {"ok": True, "az": az, "rg": rg, "sources": sources}

    def slice_ssim(self, cube_id: str, az: int, rg: int, space: str = "physical") -> dict:
        """Scores each source's range and azimuth slice against the ground truth.

        Args:
            cube_id: Id of the loaded cube.
            az: Azimuth pixel index of the azimuth slice.
            rg: Range pixel index of the range slice.
            space: "normalized" to peak-normalise columns before scoring.

        Returns:
            Dict with ``ok``, the clipped indices and per-source SSIM values under
            ``range`` and ``azimuth``; the score maps are empty when the cube
            carries no ground truth.
        """
        with self.lock:
            if self.loaded is None or self.loaded["id"] != cube_id:
                return {"ok": False, "error": "cube not loaded"}
            entries = self.loaded["entries"]
            meta    = self.loaded["meta"]

        gt = entries.get("gt")
        if gt is None:
            return {"ok": True, "az": int(az), "rg": int(rg), "range": {}, "azimuth": {}}

        az = int(np.clip(az, 0, meta["n_az"] - 1))
        rg = int(np.clip(rg, 0, meta["n_rg"] - 1))

        gt_cube = gt["cube"]
        out     = {"range": {}, "azimuth": {}}

        for source in ("pred", "predb", "reduced", "full"):
            entry = entries.get(source)
            if entry is None or entry["cube"].shape != gt_cube.shape:
                continue

            cube = entry["cube"]
            out["range"][source]   = self._ssim_score(cube[:, :, rg], gt_cube[:, :, rg], space)
            out["azimuth"][source] = self._ssim_score(cube[:, az, :], gt_cube[:, az, :], space)

        return {"ok": True, "az": az, "rg": rg, "range": out["range"], "azimuth": out["azimuth"]}

    @staticmethod
    def _ssim_score(cur: np.ndarray, ref: np.ndarray, space: str) -> float | None:
        """Returns the SSIM of one slice against a reference slice.

        Args:
            cur: Candidate slice of shape (elevation bins, samples).
            ref: Reference slice of the same shape.
            space: "normalized" to peak-normalise columns of both before scoring.

        Returns:
            The SSIM value, or None when the reference is constant, the slice is
            too small for a 3-pixel window or the score is not finite.
        """
        cur = np.nan_to_num(np.asarray(cur, dtype=np.float64))
        ref = np.nan_to_num(np.asarray(ref, dtype=np.float64))

        if space == "normalized":
            cur = cur / np.where((p := cur.max(axis=0, keepdims=True)) > 1e-12, p, 1.0)
            ref = ref / np.where((p := ref.max(axis=0, keepdims=True)) > 1e-12, p, 1.0)

        data_range = float(ref.max() - ref.min())
        if data_range <= 0.0:
            return None

        min_side = min(cur.shape)
        win_size = min(7, min_side if min_side % 2 == 1 else min_side - 1)
        if win_size < 3:
            return None

        value = float(ssim(ref, cur, data_range=data_range, win_size=win_size))
        return value if np.isfinite(value) else None

    def slice_png(self, cube_id: str, source: str, axis: str, az: int, rg: int, space: str = "physical", cmap: str = "jet") -> bytes | None:
        """Renders one elevation slice of a source as a PNG.

        Args:
            cube_id: Id of the loaded cube.
            source: Cube key to render.
            axis: "range" for a fixed range column, "azimuth" for a fixed azimuth row.
            az: Azimuth pixel index, clipped into range.
            rg: Range pixel index, clipped into range.
            space: "normalized" to peak-normalise columns, else "physical".
            cmap: Colormap name; diverging sources always use coolwarm.

        Returns:
            PNG bytes, or None when the cube is not loaded or the axis is unknown.
        """
        entry = self._entry(cube_id, source)
        if entry is None or axis not in ("range", "azimuth"):
            return None

        n_elev, n_az, n_rg = entry["cube"].shape
        az = int(np.clip(az, 0, n_az - 1))
        rg = int(np.clip(rg, 0, n_rg - 1))

        data, heights, vmin, vmax = self._cut(entry, axis, az, rg, space)

        buf = io.BytesIO()
        plt.imsave(buf, np.flipud(data), cmap=self._entry_cmap(entry, cmap), vmin=vmin, vmax=vmax, format="png")
        return buf.getvalue()

    def plane_png(self, cube_id: str, source: str, frac: float, space: str = "physical", cmap: str = "jet") -> bytes | None:
        """Renders one horizontal elevation plane of a source as a PNG.

        Args:
            cube_id: Id of the loaded cube.
            source: Cube key to render.
            frac: Position along the ascending elevation axis, 0 at the bottom bin
                and 1 at the top.
            space: "normalized" to scale the plane by its peak, else "physical".
            cmap: Colormap name; diverging sources always use coolwarm.

        Returns:
            PNG bytes of the (azimuth, range) plane, or None when the cube is not
            loaded or carries no such source.
        """
        entry = self._entry(cube_id, source)
        if entry is None:
            return None

        cube   = entry["cube"]
        n_elev = cube.shape[0]
        order  = np.argsort(entry["x_axis"])
        pos    = int(round(float(np.clip(frac, 0.0, 1.0)) * (n_elev - 1)))
        elev   = int(order[pos])

        data = np.asarray(cube[elev], dtype=np.float32)

        if space == "normalized":
            if entry.get("diverging"):
                peak = float(np.nanmax(np.abs(data))) if np.isfinite(data).any() else 0.0
                data = data / (peak if peak > 1e-12 else 1.0)
                vmin, vmax = -1.0, 1.0
            else:
                peak = float(np.nanmax(data)) if np.isfinite(data).any() else 0.0
                data = data / (peak if peak > 1e-12 else 1.0)
                vmin, vmax = 0.0, 1.0
        else:
            vmin, vmax = entry["vmin"], entry["vmax"]

        buf = io.BytesIO()
        plt.imsave(buf, np.nan_to_num(data, nan=vmin), cmap=self._entry_cmap(entry, cmap), vmin=vmin, vmax=vmax, format="png")
        return buf.getvalue()

    def param_map_png(self, cube_id: str, source: str, field: str, slot: int) -> bytes | None:
        """Renders a Gaussian parameter map or a prediction-truth error map.

        Args:
            cube_id: Id of the loaded cube.
            source: "pred", "gt" or "error".
            field: "amp", "mu", "sigma" or "count".
            slot: Gaussian slot index, ignored for the count field.

        Returns:
            PNG bytes of the (azimuth, range) map with inactive pixels painted as
            bad, or None when the field, source or cube is unavailable.
        """
        resolved = self._param_state(cube_id)
        if resolved is None or field not in (*self.PARAM_FIELDS, "count"):
            return None

        params, meta = resolved

        if source in self.PARAM_SOURCES:
            block = params.get(source)
            if block is None:
                return None
            data, vmin, vmax, cmap = self._param_source_map(block, meta, field, slot)
        elif source == "error":
            if not meta["error"]:
                return None
            data, vmin, vmax, cmap = self._param_error_map(params, meta, field, slot)
        else:
            return None

        palette = plt.get_cmap(cmap).copy()
        palette.set_bad(color=self.PARAM_BAD)

        buf = io.BytesIO()
        plt.imsave(buf, data, cmap=palette, vmin=vmin, vmax=vmax, format="png")
        return buf.getvalue()

    def param_cbar_png(self, cube_id: str, source: str, field: str) -> bytes | None:
        """Renders the colour ramp matching a parameter map.

        Args:
            cube_id: Id of the loaded cube.
            source: "pred", "gt" or "error".
            field: "amp", "mu", "sigma" or "count".

        Returns:
            PNG bytes of the ramp, or None when that combination has no colormap.
        """
        resolved = self._param_state(cube_id)
        if resolved is None or field not in (*self.PARAM_FIELDS, "count"):
            return None

        _, meta = resolved
        cmap    = self._param_cmap(source, field, meta)
        if cmap is None:
            return None

        return self.cbar_png(cmap)

    def cbar_png(self, cmap: str) -> bytes | None:
        """Renders a horizontal 256-step colour ramp for one of the allowed colormaps.

        Args:
            cmap: Colormap name.

        Returns:
            PNG bytes of the ramp, or None when the colormap is not allowed.
        """
        if cmap not in ("viridis", "inferno", "coolwarm", "jet", "gray"):
            return None

        ramp = np.tile(np.linspace(0.0, 1.0, 256), (12, 1))

        buf = io.BytesIO()
        plt.imsave(buf, ramp, cmap=cmap, vmin=0.0, vmax=1.0, format="png")
        return buf.getvalue()

    def params_at(self, cube_id: str, az: int, rg: int) -> dict:
        """Returns every Gaussian slot of every parameter source at one pixel.

        Args:
            cube_id: Id of the loaded cube.
            az: Azimuth pixel index, clipped into range.
            rg: Range pixel index, clipped into range.

        Returns:
            Dict with ``ok``, the clipped indices, the slot count, the activity
            amplitude threshold and per-source slot lists carrying amp, mu in
            metres, sigma in metres and an ``active`` flag.
        """
        resolved = self._param_state(cube_id)
        if resolved is None:
            return {"ok": False, "error": "no parameter cubes are loaded"}

        params, meta = resolved
        n_slots      = meta["n_slots"]
        threshold    = meta["threshold"]

        az = int(np.clip(az, 0, next(iter(params.values())).shape[1] - 1))
        rg = int(np.clip(rg, 0, next(iter(params.values())).shape[2] - 1))

        sources = {}
        for source, block in params.items():
            slots = []
            for k in range(n_slots):
                amp   = float(block[3 * k,     az, rg])
                mu    = float(block[3 * k + 1, az, rg])
                sigma = float(block[3 * k + 2, az, rg])
                slots.append({"amp": amp, "mu": mu, "sigma": sigma, "active": bool(amp >= threshold)})
            sources[source] = slots

        return {"ok": True, "az": az, "rg": rg, "n_slots": n_slots, "threshold": threshold, "sources": sources}

    def _param_state(self, cube_id: str) -> tuple[dict, dict] | None:
        """Returns the loaded parameter blocks and their metadata, or None."""
        with self.lock:
            if self.loaded is None or self.loaded["id"] != cube_id:
                return None
            params = self.loaded["params"]
            meta   = self.loaded["meta"]["params"]

        if meta is None or not params:
            return None
        return params, meta

    def _param_source_map(self, block: np.ndarray, meta: dict, field: str, slot: int) -> tuple[np.ndarray, float, float, str]:
        """Builds the map of one parameter field for a single source.

        Args:
            block: Parameter cube of shape (3 * n_slots, azimuth, range).
            meta: Parameter metadata carrying the threshold, slot count and ranges.
            field: "amp", "mu", "sigma" or "count".
            slot: Gaussian slot index, clipped into range; ignored for "count".

        Returns:
            Tuple of the (azimuth, range) map, its colour limits and the colormap
            name; mu and sigma are NaN where the slot amplitude is below threshold.
        """
        threshold = meta["threshold"]
        n_slots   = meta["n_slots"]

        if field == "count":
            amps = block[0::3]
            data = (amps >= threshold).sum(axis=0).astype(np.float32)
            vmin, vmax = meta["ranges"]["count"]
            return data, vmin, vmax, "viridis"

        slot    = int(np.clip(slot, 0, n_slots - 1))
        channel = np.asarray(block[3 * slot + self.PARAM_FIELDS[field]], dtype=np.float32)

        if field in ("mu", "sigma"):
            active  = block[3 * slot] >= threshold
            channel = np.where(active, channel, np.nan)

        vmin, vmax = meta["ranges"][field]
        return channel, vmin, vmax, "viridis"

    def _param_error_map(self, params: dict, meta: dict, field: str, slot: int) -> tuple[np.ndarray, float, float, str]:
        """Builds the prediction-against-truth error map of one parameter field.

        Args:
            params: Loaded parameter blocks, holding both "pred" and "gt".
            meta: Parameter metadata carrying the threshold, slot count and ranges.
            field: "amp", "mu", "sigma" or "count".
            slot: Gaussian slot index, clipped into range; ignored for "count".

        Returns:
            Tuple of the (azimuth, range) map, its colour limits and the colormap
            name; "count" gives the signed slot-count difference on a diverging
            map, the other fields give absolute differences restricted to pixels
            where both sources have the slot active.
        """
        threshold = meta["threshold"]
        n_slots   = meta["n_slots"]
        pred      = params["pred"]
        gt        = params["gt"]

        if field == "count":
            count_pred = (pred[0::3] >= threshold).sum(axis=0).astype(np.float32)
            count_gt   = (gt[0::3]   >= threshold).sum(axis=0).astype(np.float32)
            vmin, vmax = meta["ranges"]["error_count"]
            return count_pred - count_gt, vmin, vmax, "coolwarm"

        slot   = int(np.clip(slot, 0, n_slots - 1))
        offset = 3 * slot + self.PARAM_FIELDS[field]
        diff   = np.abs(np.asarray(pred[offset], dtype=np.float32) - np.asarray(gt[offset], dtype=np.float32))

        if field in ("mu", "sigma"):
            active = (pred[3 * slot] >= threshold) & (gt[3 * slot] >= threshold)
            diff   = np.where(active, diff, np.nan)

        vmin, vmax = meta["ranges"][f"error_{field}"]
        return diff, vmin, vmax, "inferno"

    def _param_cmap(self, source: str, field: str, meta: dict):
        """Returns the colormap name for a parameter map, or None when unavailable."""
        if source in self.PARAM_SOURCES:
            return "viridis"
        if source == "error" and meta["error"]:
            return "coolwarm" if field == "count" else "inferno"
        return None

    def points_bin(self, cube_id: str, source: str, amp_min: float, max_points: int) -> bytes | None:
        """Packs a scatterer point cloud in radar coordinates as a binary blob.

        Args:
            cube_id: Id of the loaded cube.
            source: Parameter source ("pred", "gt") or curve source
                ("reduced", "full").
            amp_min: Minimum amplitude a point must carry to be emitted.
            max_points: Cap on emitted points; 0 or less emits all of them.

        Returns:
            A four-float32 header (emitted count, total count, 0, 0) followed by
            rows of (azimuth index, range index, elevation in metres, amplitude),
            or None when the cube or source is unavailable.
        """
        resolved = self._point_rows(cube_id, source, amp_min, max_points)
        if resolved is None:
            return None

        rows, total = resolved
        return self._points_blob(rows, total)

    def _point_rows(self, cube_id: str, source: str, amp_min: float, max_points: int) -> tuple[np.ndarray, int] | None:
        """Returns the (rows, total) point cloud of a parameter or curve source."""
        if source in self.PARAM_SOURCES:
            return self._param_rows(cube_id, source, amp_min, max_points)
        if source in self.CLOUD_CURVE_SOURCES:
            entry = self._entry(cube_id, source)
            return None if entry is None else self._curve_rows(entry, amp_min, max_points)
        return None

    def _param_rows(self, cube_id: str, source: str, amp_min: float, max_points: int) -> tuple[np.ndarray, int] | None:
        """Extracts one point per active Gaussian slot of a parameter source.

        Args:
            cube_id: Id of the loaded cube.
            source: Parameter source, "pred" or "gt".
            amp_min: Minimum slot amplitude for a point to be kept.
            max_points: Cap on emitted points, applied by even subsampling.

        Returns:
            Tuple of a float32 array of shape (points, 4) holding azimuth index,
            range index, mu in metres and amplitude, and the unsubsampled count;
            None when the source is not loaded.
        """
        resolved = self._param_state(cube_id)
        if resolved is None:
            return None

        params, _ = resolved
        block     = params.get(source)
        if block is None:
            return None

        amps = block[0::3]
        mus  = block[1::3]
        mask = np.isfinite(amps) & (amps >= amp_min) & np.isfinite(mus)

        k_idx, az_idx, rg_idx = np.nonzero(mask)
        total                 = int(k_idx.size)

        if total > max_points > 0:
            keep   = np.linspace(0, total - 1, max_points).astype(int)
            k_idx  = k_idx[keep]
            az_idx = az_idx[keep]
            rg_idx = rg_idx[keep]

        rows = np.stack([
            az_idx.astype(np.float32),
            rg_idx.astype(np.float32),
            mus[k_idx, az_idx, rg_idx].astype(np.float32),
            amps[k_idx, az_idx, rg_idx].astype(np.float32),
        ], axis=1)

        return rows, total

    @classmethod
    def _curve_rows(cls, entry: dict, amp_min: float, max_points: int) -> tuple[np.ndarray, int]:
        """Extracts one point per bright voxel of a curve cube.

        Args:
            entry: Loaded cube entry whose cube has shape (elevation, azimuth, range).
            amp_min: Minimum voxel intensity for a point to be kept.
            max_points: Cap on emitted points, applied by even subsampling across
                the elevation-major ordering.

        Returns:
            Tuple of a float32 array of shape (points, 4) holding azimuth index,
            range index, elevation in metres and intensity, and the unsubsampled
            count.
        """
        cube   = entry["cube"]
        x_axis = np.asarray(entry["x_axis"], dtype=np.float32)
        n_rg   = cube.shape[2]

        masks  = [np.isfinite(plane) & (plane >= amp_min) for plane in cube]
        counts = np.array([int(mask.sum()) for mask in masks], dtype=np.int64)
        total  = int(counts.sum())
        starts = np.concatenate([[0], np.cumsum(counts)])

        n_keep = min(total, max_points) if max_points > 0 else total
        picks  = np.linspace(0, total - 1, n_keep).astype(np.int64) if total else np.empty(0, dtype=np.int64)

        chunks = []
        for k, plane in enumerate(cube):
            lo, hi = np.searchsorted(picks, [starts[k], starts[k + 1]])
            if lo == hi:
                continue

            hits = np.flatnonzero(masks[k])[picks[lo:hi] - starts[k]]
            vals = plane.ravel()[hits]

            chunks.append(np.stack([
                (hits // n_rg).astype(np.float32),
                (hits %  n_rg).astype(np.float32),
                np.full(hits.size, x_axis[k], dtype=np.float32),
                vals.astype(np.float32),
            ], axis=1))

        rows = np.concatenate(chunks, axis=0) if chunks else np.zeros((0, 4), dtype=np.float32)
        return rows, total

    @staticmethod
    def _points_blob(rows: np.ndarray, total: int) -> bytes:
        """Serialises point rows behind a four-float32 count header."""
        header = np.array([rows.shape[0], total, 0.0, 0.0], dtype=np.float32)
        return header.tobytes() + np.ascontiguousarray(rows).tobytes()

    def dem_grid_bin(self, cube_id: str) -> bytes | None:
        """Packs the cropped DEM as a median-referenced height grid.

        Args:
            cube_id: Id of the loaded cube.

        Returns:
            A four-float32 header (azimuth rows, range columns, median height in
            metres, 0) followed by the float32 grid of heights relative to that
            median, or None when the cube is not loaded or carries no DEM.
        """
        with self.lock:
            if self.loaded is None or self.loaded["id"] != cube_id:
                return None
            dem = self.loaded["dem"]

        if dem is None:
            return None

        finite = np.isfinite(dem)
        median = float(np.median(dem[finite])) if finite.any() else 0.0
        grid   = (dem - median).astype(np.float32)

        header = np.array([dem.shape[0], dem.shape[1], median, 0.0], dtype=np.float32)
        return header.tobytes() + np.ascontiguousarray(grid).tobytes()

    def globe_points_bin(self, cube_id: str, source: str, amp_min: float, max_points: int) -> bytes | None:
        """Packs a geocoded point cloud as ECEF offsets from the scene anchor.

        Scatterer elevations are added to the DEM terrain height at their pixel
        before geocoding, so points sit above ground on the globe.

        Args:
            cube_id: Id of the loaded cube.
            source: Source to draw points from, restricted to GLOBE_SOURCES.
            amp_min: Minimum amplitude for a point to be kept.
            max_points: Cap on emitted points before the terrain mask is applied.

        Returns:
            A four-float32 header (emitted count, pre-mask total, 0, 0) followed by
            rows of (ECEF x, y, z offsets in metres, elevation in metres,
            amplitude), or None when the cube has no geocoding or the source is
            not globe-renderable.
        """
        with self.lock:
            if self.loaded is None or self.loaded["id"] != cube_id:
                return None
            geo = self.loaded["geo"]

        if geo is None or source not in self.GLOBE_SOURCES:
            return None

        resolved = self._point_rows(cube_id, source, amp_min, max_points)
        if resolved is None:
            return None

        rows, total = resolved
        az_idx      = rows[:, 0].astype(np.int64)
        rg_idx      = rows[:, 1].astype(np.int64)

        terrain = geo["dem"][az_idx, rg_idx]
        keep    = np.isfinite(terrain)

        az_idx  = az_idx[keep]
        rg_idx  = rg_idx[keep]
        rows    = rows[keep]
        heights = terrain[keep].astype(np.float64) + rows[:, 2].astype(np.float64)

        _, _, ecef = geo["geocoder"].geocode(az_idx + geo["az0"], rg_idx + geo["rg0"], heights)
        offsets    = (ecef - geo["anchor_ecef"][None, :]).astype(np.float32)

        globe_rows = np.concatenate([offsets, rows[:, 2:3], rows[:, 3:4]], axis=1)
        header     = np.array([globe_rows.shape[0], total, 0.0, 0.0], dtype=np.float32)
        return header.tobytes() + np.ascontiguousarray(globe_rows).tobytes()

    def metric_overlay_png(self, cube_id: str, key: str, vmin: float, vmax: float, keep_min: float, keep_max: float, alpha: float) -> bytes | None:
        """Blends a metric map over the primary amplitude map as a PNG.

        Args:
            cube_id: Id of the loaded cube.
            key: Metric map name.
            vmin: Lower colour limit; ignored when not below vmax, in which case
                the map's own robust range is used.
            vmax: Upper colour limit.
            keep_min: Lowest metric value that is painted.
            keep_max: Highest metric value that is painted.
            alpha: Overlay opacity in [0, 1].

        Returns:
            PNG bytes of the blended RGB image, or None when the map is unknown.
        """
        resolved = self._metric_state(cube_id, key)
        if resolved is None:
            return None

        data, primary, clim = resolved

        if not vmax > vmin:
            vmin, vmax = self._metric_range(data)
        alpha = float(np.clip(alpha, 0.0, 1.0))

        p_lo, p_hi = clim
        base       = (np.clip((primary - p_lo) / max(p_hi - p_lo, 1e-12), 0.0, 1.0))[..., None].repeat(3, axis=2)

        norm    = np.clip((data - vmin) / max(vmax - vmin, 1e-12), 0.0, 1.0)
        colored = plt.get_cmap("viridis")(norm)[..., :3]
        keep    = np.isfinite(data) & (data >= keep_min) & (data <= keep_max)
        blend   = np.where(keep[..., None], base * (1.0 - alpha) + colored * alpha, base)

        buf = io.BytesIO()
        plt.imsave(buf, blend.astype(np.float32), format="png")
        return buf.getvalue()

    def metric_value_at(self, cube_id: str, key: str, az: int, rg: int) -> dict:
        """Reads one metric map at a pixel.

        Args:
            cube_id: Id of the loaded cube.
            key: Metric map name.
            az: Azimuth pixel index, clipped into range.
            rg: Range pixel index, clipped into range.

        Returns:
            Dict with ``ok``, the clipped indices, the map ``key`` and its
            ``value``, which is None where the map is not finite.
        """
        resolved = self._metric_state(cube_id, key)
        if resolved is None:
            return {"ok": False, "error": f"unknown metric map: {key}"}

        data, _primary, _clim = resolved
        az = int(np.clip(az, 0, data.shape[0] - 1))
        rg = int(np.clip(rg, 0, data.shape[1] - 1))

        value = float(data[az, rg])
        return {"ok": True, "az": az, "rg": rg, "key": key, "value": value if np.isfinite(value) else None}

    def _metric_state(self, cube_id: str, key: str) -> tuple[np.ndarray, np.ndarray, tuple[float, float]] | None:
        """Returns the metric map, primary amplitude map and its colour limits."""
        with self.lock:
            if self.loaded is None or self.loaded["id"] != cube_id:
                return None
            data    = self.loaded["metric_maps"].get(key)
            primary = self.loaded["primary"]
            clim    = self.loaded["primary_clim"]

        if data is None:
            return None
        return data, primary, clim

    SELECTIVE_KEYS    = ("pixel_mse", "pixel_mae", "pixel_r2", "pixel_cos", "pixel_peak")
    HIGH_IS_CONFIDENT = ("pixel_r2", "pixel_cos", "label_r2", "physics_valid_mask")

    def selective_metrics(self, cube_id: str, key: str, coverage: float) -> dict:
        """Compares pixel metrics on the most confident pixels against all pixels.

        Pixels are ranked by one confidence layer and the top coverage fraction is
        kept; layers listed in HIGH_IS_CONFIDENT are ranked descending, the rest
        ascending.

        Args:
            cube_id: Id of the loaded cube.
            key: Metric map used as the confidence layer.
            coverage: Fraction of finite pixels to keep, clipped to [0.01, 1].

        Returns:
            Dict with ``ok``, the layer name, the realised coverage, the quantile
            ``threshold``, the ranking ``direction``, kept and total pixel counts,
            and per-metric ``rows`` holding the kept and full-scene means.
        """
        resolved = self._metric_state(cube_id, key)
        if resolved is None:
            return {"ok": False, "error": f"unknown confidence layer: {key}"}

        confidence, _primary, _clim = resolved

        with self.lock:
            if self.loaded is None or self.loaded["id"] != cube_id:
                return {"ok": False, "error": "cube changed while computing"}
            maps = {name: data for name, data in self.loaded["metric_maps"].items() if name in self.SELECTIVE_KEYS}

        if not maps:
            return {"ok": False, "error": "no pixel metric maps are loaded for this cube"}

        coverage = float(np.clip(coverage, 0.01, 1.0))
        finite   = np.isfinite(confidence)

        if not finite.any():
            return {"ok": False, "error": f"confidence layer '{key}' holds no finite value"}

        keep_high = key in self.HIGH_IS_CONFIDENT

        if keep_high:
            threshold = float(np.quantile(confidence[finite], 1.0 - coverage))
            keep      = finite & (confidence >= threshold)
        else:
            threshold = float(np.quantile(confidence[finite], coverage))
            keep      = finite & (confidence <= threshold)

        rows = []
        for name, data in sorted(maps.items()):
            valid = np.isfinite(data)
            kept  = data[keep & valid]
            full  = data[valid]
            if not full.size:
                continue
            rows.append({
                "key"   : name,
                "label" : self.METRIC_LABELS.get(name, name),
                "kept"  : float(kept.mean()) if kept.size else None,
                "full"  : float(full.mean()),
            })

        return {
            "ok"        : True,
            "layer"     : key,
            "coverage"  : float(keep.sum() / max(finite.sum(), 1)),
            "threshold" : threshold,
            "direction" : "high" if keep_high else "low",
            "n_kept"    : int(keep.sum()),
            "n_total"   : int(finite.sum()),
            "rows"      : rows,
        }

    def transect_png(self, cube_id: str, source: str, az0: int, rg0: int, az1: int, rg1: int, space: str = "physical", cmap: str = "jet") -> bytes | None:
        """Renders an elevation section along an arbitrary line as a PNG.

        Args:
            cube_id: Id of the loaded cube.
            source: Cube key to render.
            az0: Azimuth pixel index of the start point.
            rg0: Range pixel index of the start point.
            az1: Azimuth pixel index of the end point.
            rg1: Range pixel index of the end point.
            space: "normalized" to peak-normalise columns, else "physical".
            cmap: Colormap name; diverging sources always use coolwarm.

        Returns:
            PNG bytes, or None when the cube carries no such source.
        """
        entry = self._entry(cube_id, source)
        if entry is None:
            return None

        data, heights, vmin, vmax = self._transect_cut(entry, az0, rg0, az1, rg1, space)

        buf = io.BytesIO()
        plt.imsave(buf, np.flipud(data), cmap=self._entry_cmap(entry, cmap), vmin=vmin, vmax=vmax, format="png")
        return buf.getvalue()

    def save_transect(self, cube_id: str, az0: int, rg0: int, az1: int, rg1: int, space: str = "physical", cmap: str = "jet") -> dict:
        """Saves one transect figure per loaded source under the run's figures folder.

        Args:
            cube_id: Id of the loaded cube.
            az0: Azimuth pixel index of the start point, clipped into range.
            rg0: Range pixel index of the start point, clipped into range.
            az1: Azimuth pixel index of the end point, clipped into range.
            rg1: Range pixel index of the end point, clipped into range.
            space: "physical" or "normalized".
            cmap: Colormap name; diverging sources always use coolwarm.

        Returns:
            Dict with ``ok``, the absolute output ``dir``, its path ``rel`` to the
            run and the written ``files``, or ``ok`` False with the reason.
        """
        with self.lock:
            if self.loaded is None or self.loaded["id"] != cube_id:
                return {"ok": False, "error": "cube not loaded"}
            entries = self.loaded["entries"]
            meta    = self.loaded["meta"]

        reader = self._open_source(cube_id)
        if reader is None:
            return {"ok": False, "error": f"unknown cube id: {cube_id}"}
        if space not in ("physical", "normalized"):
            return {"ok": False, "error": f"unknown space: {space}"}

        az0 = int(np.clip(az0, 0, meta["n_az"] - 1))
        az1 = int(np.clip(az1, 0, meta["n_az"] - 1))
        rg0 = int(np.clip(rg0, 0, meta["n_rg"] - 1))
        rg1 = int(np.clip(rg1, 0, meta["n_rg"] - 1))

        rel     = Path("figures") / "cube_transects" / f"az{az0:04d}_rg{rg0:04d}_to_az{az1:04d}_rg{rg1:04d}"
        out_dir = reader.save_dir / rel

        files = []
        for source in meta["sources"]:
            entry = entries[source]
            data, heights, vmin, vmax = self._transect_cut(entry, az0, rg0, az1, rg1, space)
            saved = self.archiver.render_transect(data, heights, vmin, vmax, source, (az0, rg0), (az1, rg1), space, out_dir / f"transect_{source}_{space}.png", cmap=self._entry_cmap(entry, cmap))
            files.append(saved.name)

        self.logger.ok(f"saved {len(files)} transect figures to {out_dir}")
        return {"ok": True, "dir": str(out_dir), "rel": str(rel), "files": files}

    @classmethod
    def _transect_cut(cls, entry: dict, az0: int, rg0: int, az1: int, rg1: int, space: str) -> tuple[np.ndarray, np.ndarray, float, float]:
        """Samples the cube along a straight azimuth-range line.

        The line is sampled at one point per pixel of its longer axis, with
        nearest-neighbour rounding of the indices.

        Args:
            entry: Loaded cube entry.
            az0: Azimuth pixel index of the start point, clipped into range.
            rg0: Range pixel index of the start point, clipped into range.
            az1: Azimuth pixel index of the end point, clipped into range.
            rg1: Range pixel index of the end point, clipped into range.
            space: "normalized" to peak-normalise columns, else "physical".

        Returns:
            Tuple of the section of shape (elevation bins, samples) ordered by
            ascending elevation, the elevation axis in metres, and the colour
            limits.
        """
        cube               = entry["cube"]
        n_elev, n_az, n_rg = cube.shape

        az0 = int(np.clip(az0, 0, n_az - 1))
        az1 = int(np.clip(az1, 0, n_az - 1))
        rg0 = int(np.clip(rg0, 0, n_rg - 1))
        rg1 = int(np.clip(rg1, 0, n_rg - 1))

        samples = int(max(abs(az1 - az0), abs(rg1 - rg0))) + 1
        az_idx  = np.round(np.linspace(az0, az1, samples)).astype(int)
        rg_idx  = np.round(np.linspace(rg0, rg1, samples)).astype(int)
        data    = cube[:, az_idx, rg_idx]

        data, vmin, vmax = cls._normalize_cut(entry, data, space)

        order   = np.argsort(entry["x_axis"])
        heights = np.asarray(entry["x_axis"], dtype=np.float64)[order]
        return data[order], heights, float(vmin), float(vmax)

    def save_slices(self, cube_id: str, az: int, rg: int, space: str = "physical", cmap: str = "jet") -> dict:
        """Saves the range and azimuth slice of every loaded source at one pixel.

        Args:
            cube_id: Id of the loaded cube.
            az: Azimuth pixel index, clipped into range.
            rg: Range pixel index, clipped into range.
            space: "physical" or "normalized".
            cmap: Colormap name; diverging sources always use coolwarm.

        Returns:
            Dict with ``ok``, the absolute output ``dir``, its path ``rel`` to the
            run, the clipped indices and the written ``files``, or ``ok`` False
            with the reason.
        """
        with self.lock:
            if self.loaded is None or self.loaded["id"] != cube_id:
                return {"ok": False, "error": "cube not loaded"}
            entries = self.loaded["entries"]
            meta    = self.loaded["meta"]

        reader = self._open_source(cube_id)
        if reader is None:
            return {"ok": False, "error": f"unknown cube id: {cube_id}"}
        if space not in ("physical", "normalized"):
            return {"ok": False, "error": f"unknown space: {space}"}

        az = int(np.clip(az, 0, meta["n_az"] - 1))
        rg = int(np.clip(rg, 0, meta["n_rg"] - 1))

        rel     = Path("figures") / "cube_slices" / f"az{az:04d}_rg{rg:04d}"
        out_dir = reader.save_dir / rel

        files = []
        for source in meta["sources"]:
            for axis in ("range", "azimuth"):
                data, heights, vmin, vmax = self._cut(entries[source], axis, az, rg, space)
                saved = self.archiver.render(data, heights, vmin, vmax, source, axis, az, rg, space, out_dir / f"{axis}_{source}_{space}.png", cmap=self._entry_cmap(entries[source], cmap))
                files.append(saved.name)

        self.logger.ok(f"saved {len(files)} slice figures to {out_dir}")
        return {"ok": True, "dir": str(out_dir), "rel": str(rel), "az": az, "rg": rg, "files": files}

    @classmethod
    def _cut(cls, entry: dict, axis: str, az: int, rg: int, space: str) -> tuple[np.ndarray, np.ndarray, float, float]:
        """Extracts one elevation slice from a loaded cube entry.

        Args:
            entry: Loaded cube entry.
            axis: "range" for a fixed range column, "azimuth" for a fixed azimuth row.
            az: Azimuth pixel index used by the azimuth cut.
            rg: Range pixel index used by the range cut.
            space: "normalized" to peak-normalise columns, else "physical".

        Returns:
            Tuple of the slice of shape (elevation bins, samples) ordered by
            ascending elevation, the elevation axis in metres, and the colour
            limits.
        """
        cube = entry["cube"]
        data = cube[:, :, rg] if axis == "range" else cube[:, az, :]

        data, vmin, vmax = cls._normalize_cut(entry, data, space)

        order   = np.argsort(entry["x_axis"])
        heights = np.asarray(entry["x_axis"], dtype=np.float64)[order]
        return data[order], heights, float(vmin), float(vmax)

    @staticmethod
    def _normalize_cut(entry: dict, data: np.ndarray, space: str) -> tuple[np.ndarray, float, float]:
        """Peak-normalises each column of a cut when normalised space is requested.

        Args:
            entry: Loaded cube entry, whose ``diverging`` flag selects symmetric limits.
            data: Cut of shape (elevation bins, samples).
            space: "normalized" to normalise, anything else to pass through.

        Returns:
            Tuple of the cut and its colour limits: the entry's own limits in
            physical space, (0, 1) normalised, or (-1, 1) for diverging sources.
        """
        if space != "normalized":
            return data, entry["vmin"], entry["vmax"]

        peak = np.abs(data).max(axis=0, keepdims=True) if entry.get("diverging") else data.max(axis=0, keepdims=True)
        safe = np.where(peak > 1e-12, peak, 1.0)
        data = (data / safe).astype(np.float32)
        vmin, vmax = (-1.0, 1.0) if entry.get("diverging") else (0.0, 1.0)
        return data, vmin, vmax

    @classmethod
    def _entry_cmap(cls, entry: dict, cmap: str = "jet") -> str:
        """Returns coolwarm for diverging entries, else the requested allowed colormap."""
        if entry.get("diverging"):
            return "coolwarm"
        return cmap if cmap in cls.CMAPS else "jet"

    def _entry(self, cube_id: str, source: str) -> dict | None:
        """Returns the loaded entry of one source, or None when unavailable."""
        with self.lock:
            if self.loaded is None or self.loaded["id"] != cube_id:
                return None
            return self.loaded["entries"].get(source)

    def _open_source(self, cube_id: str) -> StampReader | FoldMosaic | None:
        """Resolves a cube id to a reader.

        Args:
            cube_id: Stamp directory path or a fold mosaic composite id.

        Returns:
            A FoldMosaic for mosaic ids, a StampReader for stamp directories that
            hold ``cubes/pred_curves.npy``, or None when the id is unknown or
            falls outside the catalogued roots.
        """
        if not cube_id:
            return None

        parsed = FoldMosaic.parse(cube_id)
        if parsed is not None:
            cv_root, split, seed = parsed
            if not self.roots.contains(cv_root):
                return None
            return FoldMosaic.open(cv_root, split, seed)

        stamp_dir = Path(cube_id).resolve()
        if not self.roots.contains(stamp_dir):
            return None
        if not (stamp_dir / "cubes" / "pred_curves.npy").is_file():
            return None
        return StampReader(stamp_dir)

    def _load_worker(self, cube_id: str, reader: StampReader | FoldMosaic) -> None:
        """Loads a cube in the background and publishes the ready or error status.

        Args:
            cube_id: Id being loaded.
            reader: Reader opened for that id.
        """
        try:
            entries, meta, primary, params, metric_maps, dem, geo = self._load_all(reader)
            clim = tuple(float(v) for v in np.percentile(primary, [1.0, 99.0]))

            with self.lock:
                self.loaded = {"id": cube_id, "entries": entries, "meta": meta, "primary": primary, "primary_clim": clim, "params": params, "metric_maps": metric_maps, "dem": dem, "geo": geo}
                self.status = {"state": "ready", "id": cube_id, "progress": 1.0, "stage": "ready", "error": ""}

            self.logger.muted(f"cube ready: {cube_id} sources={meta['sources']}")
        except Exception as exc:
            with self.lock:
                self.loaded = None
                self.status = {"state": "error", "id": cube_id, "progress": 0.0, "stage": "", "error": str(exc)}

            self.logger.error(f"cube load failed: {cube_id}: {exc}")

    def _load_all(self, reader: StampReader | FoldMosaic) -> tuple[dict, dict, np.ndarray, dict, dict, np.ndarray | None, dict | None]:
        """Reads every available source, map and geometry artifact of one cube.

        Args:
            reader: Stamp or mosaic reader to pull from.

        Returns:
            Tuple of the per-source entries, the front-end metadata payload, the
            primary amplitude map in dB of shape (azimuth, range), the parameter
            blocks, the metric maps, the cropped DEM in metres and the geocoding
            context; the last two are None when the scene cannot be geolocated.

        Raises:
            ValueError: If the prediction cube is not three-dimensional or another
                source's spatial shape disagrees with it.
        """
        pred_raw = reader.curves("pred")
        if pred_raw.ndim != 3:
            raise ValueError(f"pred_curves.npy is not a 3D cube: shape={pred_raw.shape}")

        n_elev, n_az, n_rg = pred_raw.shape
        curve_axis         = self._curve_axis(reader, n_elev)

        plan = [("pred", pred_raw, curve_axis)]
        for source in ("gt", "reduced"):
            raw = reader.curves(source)
            if raw is not None:
                plan.append((source, raw, curve_axis))

        full_raw = self._full_raw(reader, n_az, n_rg)
        if full_raw is not None:
            plan.append(("full", full_raw, np.arange(full_raw.shape[0], dtype=np.float64)))

        total = sum(raw.shape[0] for _, raw, _ in plan)
        done  = [0]

        def advance(source: str) -> None:
            """Records one more ingested elevation plane in the load status."""
            done[0] += 1
            with self.lock:
                self.status["progress"] = done[0] / total
                self.status["stage"]    = source

        entries = {}
        for source, raw, x_axis in plan:
            if raw.shape[1:] != (n_az, n_rg):
                raise ValueError(f"source '{source}' spatial shape {raw.shape[1:]} does not match pred {(n_az, n_rg)}")
            entries[source] = self._ingest(raw, x_axis, lambda s=source: advance(s))

        primary     = self._primary_db(reader, n_az, n_rg)
        params      = self._load_params(reader, n_az, n_rg)
        metric_maps = reader.metric_maps(n_az, n_rg)
        dem         = self._load_dem(reader, n_az, n_rg)
        geo         = self._load_geo(reader, dem, n_az, n_rg)
        mosaic      = reader.mosaic_meta()

        if mosaic is not None and mosaic["gaps"]:
            self.logger.warning(f"fold mosaic leaves azimuth rows {mosaic['gaps']} uncovered; those stripes render blank because no fold owns them, not because the model failed")

        meta = {
            "sources"     : [s for s in self.SOURCES if s in entries],
            "n_az"        : n_az,
            "n_rg"        : n_rg,
            "n_elev"      : {s: int(entries[s]["cube"].shape[0]) for s in entries},
            "x_min"       : float(curve_axis[0]),
            "x_max"       : float(curve_axis[-1]),
            "intensity"   : {s: [entries[s]["vmin"], entries[s]["vmax"]] for s in entries},
            "params"      : self._params_meta(params, curve_axis),
            "metric_maps" : self._metric_maps_meta(metric_maps),
            "attached"    : None,
            "mosaic"      : mosaic,
            "dem"         : dem is not None,
            "spacing"     : self._load_spacing(reader),
            "globe"       : self._globe_meta(geo),
        }
        return entries, meta, primary, params, metric_maps, dem, geo

    def _load_spacing(self, reader: StampReader | FoldMosaic) -> dict | None:
        """Returns the reference track's azimuth and range pixel spacing in metres.

        Args:
            reader: Stamp or mosaic reader identifying the preprocessing run.

        Returns:
            Dict with ``az`` and ``rg`` spacings, or None when the preprocessing
            run or its track parameters cannot be resolved.
        """
        resolved = self._preproc_layout(reader)
        if resolved is None:
            return None

        preproc_dir, _ = resolved

        params_path = preproc_dir / "meta" / TrackParameters.FILENAME
        if not params_path.is_file():
            return None

        reference = TrackParameters.load(params_path).parameters[0]
        return {"az": float(reference["ps_az"]), "rg": float(reference["ps_rg"])}

    def _load_dem(self, reader: StampReader | FoldMosaic, n_az: int, n_rg: int) -> np.ndarray | None:
        """Crops the preprocessing DEM to the cube footprint.

        Args:
            reader: Stamp or mosaic reader identifying the preprocessing run.
            n_az: Azimuth extent of the cube, in pixels.
            n_rg: Range extent of the cube, in pixels.

        Returns:
            Float32 terrain heights in metres of shape (n_az, n_rg), or None when
            the preprocessing run publishes no full DEM.

        Raises:
            ValueError: If the stored DEM does not cover the cube region.
        """
        resolved = self._preproc_layout(reader)
        if resolved is None:
            return None

        preproc_dir, layout = resolved

        dem_name = layout["artifacts"].get("dem_full")
        if not dem_name:
            return None

        dem_path = preproc_dir / "data" / dem_name
        if not dem_path.is_file():
            return None

        az_lo, az_hi, rg_lo, rg_hi = self._crop_bounds(reader, layout, n_az, n_rg)

        raw = np.load(dem_path, mmap_mode="r")
        if raw.ndim != 2 or az_hi > raw.shape[0] or rg_hi > raw.shape[1] or az_lo < 0 or rg_lo < 0:
            raise ValueError(f"dem_full shape {raw.shape} does not cover the cube region az[{az_lo}:{az_hi}] rg[{rg_lo}:{rg_hi}]")

        return np.asarray(raw[az_lo:az_hi, rg_lo:rg_hi], dtype=np.float32)

    def _load_geo(self, reader: StampReader | FoldMosaic, dem: np.ndarray | None, n_az: int, n_rg: int) -> dict | None:
        """Builds the geocoding context used by the globe view.

        Args:
            reader: Stamp or mosaic reader identifying the preprocessing run.
            dem: Cropped DEM in metres, or None to skip geocoding entirely.
            n_az: Azimuth extent of the cube, in pixels.
            n_rg: Range extent of the cube, in pixels.

        Returns:
            Dict with the scene geocoder, the cube's azimuth and range origins in
            full-scene pixels, the DEM, the median terrain height in metres, the
            ECEF anchor of the scene centre, the lon/lat bounding box, the flight
            lines when the stamp records its track selection, and the beam
            segment; None when the track parameters lack the geocoding keys or the
            DEM holds no finite height.
        """
        if dem is None:
            return None

        resolved = self._preproc_layout(reader)
        if resolved is None:
            return None

        preproc_dir, _ = resolved

        params_path = preproc_dir / "meta" / TrackParameters.FILENAME
        if not params_path.is_file():
            return None

        params    = TrackParameters.load(params_path)
        reference = params.parameters[0]
        if any(key not in reference for key in SceneGeocoder.REQUIRED_KEYS):
            return None

        finite = np.isfinite(dem)
        if not finite.any():
            return None

        geocoder    = SceneGeocoder(reference)
        base_height = float(np.median(dem[finite]))

        metrics                  = reader.metrics()
        az_start, _, rg_start, _ = (int(v) for v in metrics["split_region"])
        used_tracks              = metrics.get("tracks")

        _, _, anchor = geocoder.geocode([az_start + n_az / 2], [rg_start + n_rg / 2], [base_height])

        corner_az   = np.array([az_start, az_start, az_start + n_az, az_start + n_az], dtype=np.float64)
        corner_rg   = np.array([rg_start, rg_start + n_rg, rg_start, rg_start + n_rg], dtype=np.float64)
        lon, lat, _ = geocoder.geocode(corner_az, corner_rg, np.full(4, base_height))

        return {
            "geocoder"    : geocoder,
            "az0"         : az_start,
            "rg0"         : rg_start,
            "dem"         : dem,
            "base_height" : base_height,
            "anchor_ecef" : anchor[0],
            "bbox"        : [float(lon.min()), float(lat.min()), float(lon.max()), float(lat.max())],
            "tracks"      : self._track_lines(params, used_tracks, az_start, n_az) if used_tracks is not None else None,
            "beam"        : self._beam_segment(geocoder, reference, dem, base_height, az_start, rg_start, n_az, n_rg),
        }

    TRACK_LINE_POINTS = 17

    def _track_lines(self, params: TrackParameters, used: dict, az_start: int, n_az: int) -> dict:
        """Geocodes the flight line of every track used by the run.

        Args:
            params: Track parameters of the whole stack.
            used: Track selection recorded by the inference stamp, carrying the
                track ``labels`` and the ``reference`` track.
            az_start: Azimuth origin of the cube in full-scene pixels.
            n_az: Azimuth extent of the cube, in pixels.

        Returns:
            Dict with the ``labels``, the ``reference`` track, one ECEF polyline
            per track sampled at TRACK_LINE_POINTS positions, and the ``h0``
            flight altitudes in metres.

        Raises:
            ValueError: If a used track is absent from the track parameters or the
                run's reference track is not the stack primary.
        """
        labels    = list(used["labels"])
        reference = used["reference"]

        by_label = dict(zip(params.labels, params.parameters))
        missing  = [label for label in labels if label not in by_label]
        if missing:
            raise ValueError(f"run tracks {missing} are absent from track_parameters.json labels {params.labels}")
        if reference != params.reference:
            raise ValueError(f"run reference track '{reference}' does not match the stack primary '{params.reference}'")

        az_grid = np.linspace(az_start, az_start + n_az, self.TRACK_LINE_POINTS)

        lines = []
        for label in labels:
            track      = by_label[label]
            _, _, ecef = SceneGeocoder(track).geocode_track(az_grid, np.full(az_grid.shape, float(track["h0"])))
            lines.append(ecef)

        return {
            "labels"    : labels,
            "reference" : reference,
            "lines"     : lines,
            "h0"        : [float(by_label[label]["h0"]) for label in labels],
        }

    def _beam_segment(self, geocoder: SceneGeocoder, reference: dict, dem: np.ndarray, base_height: float, az_start: int, rg_start: int, n_az: int, n_rg: int) -> dict:
        """Builds the radar beam triangle drawn on the globe.

        Args:
            geocoder: Geocoder of the reference track.
            reference: Reference track parameters, carrying its ``h0`` in metres.
            dem: Cropped DEM in metres.
            base_height: Median terrain height in metres, used where the DEM is
                not finite at the sampled edges.
            az_start: Azimuth origin of the cube in full-scene pixels.
            rg_start: Range origin of the cube in full-scene pixels.
            n_az: Azimuth extent of the cube, in pixels.
            n_rg: Range extent of the cube, in pixels.

        Returns:
            Dict with the ECEF ``apex`` on the flight line, the ``near`` and
            ``far`` ground points at mid-azimuth, their slant ranges in metres and
            their look angles in degrees.
        """
        az_mid = az_start + n_az / 2.0
        near_h = float(dem[n_az // 2, 0])
        far_h  = float(dem[n_az // 2, n_rg - 1])

        near_h = near_h if math.isfinite(near_h) else base_height
        far_h  = far_h  if math.isfinite(far_h)  else base_height

        _, _, apex = geocoder.geocode_track([az_mid], [float(reference["h0"])])
        _, _, feet = geocoder.geocode([az_mid, az_mid], [rg_start, rg_start + n_rg - 1], [near_h, far_h])

        slant_near = geocoder.r0 + rg_start * geocoder.ps_rg
        slant_far  = geocoder.r0 + (rg_start + n_rg - 1) * geocoder.ps_rg

        return {
            "apex"          : apex[0],
            "near"          : feet[0],
            "far"           : feet[1],
            "slant_near_m"  : slant_near,
            "slant_far_m"   : slant_far,
            "look_near_deg" : math.degrees(math.acos(min(1.0, (float(reference["h0"]) - near_h) / slant_near))),
            "look_far_deg"  : math.degrees(math.acos(min(1.0, (float(reference["h0"]) - far_h) / slant_far))),
        }

    def _globe_meta(self, geo: dict | None) -> dict | None:
        """Serialises the geocoding context for the globe front end.

        Args:
            geo: Geocoding context, or None when the scene cannot be geolocated.

        Returns:
            Dict with the ECEF anchor, lon/lat bounding box, base height in
            metres, the geocoder's residual RMS in metres and, when the stamp
            records its tracks, the flight lines and beam expressed as ECEF
            offsets from the anchor; None when geo is None.
        """
        if geo is None:
            return None

        anchor = np.asarray(geo["anchor_ecef"], dtype=np.float64)
        offset = lambda ecef: [round(float(v), 2) for v in np.asarray(ecef, dtype=np.float64) - anchor]
        beam   = geo["beam"]
        tracks = geo["tracks"]

        return {
            "anchor_ecef"    : [float(value) for value in geo["anchor_ecef"]],
            "bbox"           : geo["bbox"],
            "base_height"    : geo["base_height"],
            "residual_rms_m" : geo["geocoder"].residual_rms_m,
            "tracks_note"    : None if tracks is not None else "this inference stamp stores no track selection, so the flight lines cannot be drawn",
            "tracks"         : None if tracks is None else {
                "labels"    : tracks["labels"],
                "reference" : tracks["reference"],
                "h0"        : tracks["h0"],
                "lines"     : [[offset(point) for point in line] for line in tracks["lines"]],
                "beam"      : {
                    "apex"          : offset(beam["apex"]),
                    "near"          : offset(beam["near"]),
                    "far"           : offset(beam["far"]),
                    "slant_near_m"  : beam["slant_near_m"],
                    "slant_far_m"   : beam["slant_far_m"],
                    "look_near_deg" : beam["look_near_deg"],
                    "look_far_deg"  : beam["look_far_deg"],
                },
            },
        }

    def _metric_maps_meta(self, metric_maps: dict) -> list:
        """Describes each metric map with its display label and robust colour range."""
        layers = []
        for key, data in metric_maps.items():
            vmin, vmax = self._metric_range(data)
            layers.append({
                "key"   : key,
                "label" : self.METRIC_LABELS.get(key, key),
                "vmin"  : vmin,
                "vmax"  : vmax,
            })
        return layers

    @staticmethod
    def _metric_range(data: np.ndarray) -> tuple[float, float]:
        """Returns the 1st-to-99th percentile range of a map, widened when degenerate."""
        finite = data[np.isfinite(data)]
        if not finite.size:
            return 0.0, 1.0

        vmin, vmax = (float(v) for v in np.percentile(finite, [1.0, 99.0]))
        if not vmax > vmin:
            vmin, vmax = float(finite.min()), float(finite.max())
        if not vmax > vmin:
            vmax = vmin + 1.0
        return vmin, vmax

    def _load_params(self, reader: StampReader | FoldMosaic, n_az: int, n_rg: int) -> dict:
        """Loads the Gaussian parameter cubes that match the cube footprint.

        Args:
            reader: Stamp or mosaic reader to pull from.
            n_az: Azimuth extent of the cube, in pixels.
            n_rg: Range extent of the cube, in pixels.

        Returns:
            Mapping from parameter source to a (3 * n_slots, n_az, n_rg) block.

        Raises:
            ValueError: If a block is not a (3K, azimuth, range) cube or does not
                match the cube footprint.
        """
        params = {}
        for source in self.PARAM_SOURCES:
            raw = reader.param_block(source)
            if raw is None:
                continue

            if raw.ndim != 3 or raw.shape[0] % 3 != 0 or raw.shape[0] == 0:
                raise ValueError(f"params_{source}.npy is not a (3K, az, rg) cube: shape={raw.shape}")
            if raw.shape[1:] != (n_az, n_rg):
                raise ValueError(f"params_{source}.npy spatial shape {raw.shape[1:]} does not match the {n_az}x{n_rg} cube")

            params[source] = raw

        return params

    def _params_meta(self, params: dict, curve_axis: np.ndarray) -> dict | None:
        """Describes the loaded parameter blocks for the front end.

        Args:
            params: Loaded parameter blocks keyed by source.
            curve_axis: Elevation axis in metres, used as the mu display range.

        Returns:
            Dict with the available ``sources``, the slot count, the activity
            amplitude threshold, whether error maps are possible and the colour
            ``ranges`` for each field and each error field; None when no
            parameter block was loaded.
        """
        if not params:
            return None

        n_slots   = next(iter(params.values())).shape[0] // 3
        threshold = ParamMatcher.ACTIVE_AMP_THR
        has_error = "pred" in params and "gt" in params

        ranges = {
            "amp"   : [0.0, self._field_ceiling(params, 0)],
            "mu"    : [float(curve_axis[0]), float(curve_axis[-1])],
            "sigma" : [0.0, self._field_ceiling(params, 2)],
            "count" : [0.0, float(n_slots)],
        }

        if has_error:
            for field, offset in self.PARAM_FIELDS.items():
                diff = np.abs(params["pred"][offset::3] - params["gt"][offset::3])
                high = float(np.nanpercentile(diff, 99.0)) if diff.size else 1.0
                ranges[f"error_{field}"] = [0.0, high if high > 0.0 else 1.0]
            ranges["error_count"] = [-float(n_slots), float(n_slots)]

        return {
            "sources"   : [s for s in self.PARAM_SOURCES if s in params],
            "n_slots"   : n_slots,
            "threshold" : threshold,
            "error"     : has_error,
            "ranges"    : ranges,
        }

    @staticmethod
    def _field_ceiling(params: dict, offset: int) -> float:
        """Returns the largest 99th percentile of one parameter channel across sources."""
        high = 0.0
        for block in params.values():
            channels = block[offset::3]
            if channels.size:
                high = max(high, float(np.nanpercentile(channels, 99.0)))
        return high if high > 0.0 else 1.0

    def _ingest(self, raw: np.ndarray, x_axis: np.ndarray, advance) -> dict:
        """Materialises a cube plane by plane and derives its display colour limits.

        Args:
            raw: Lazy or memory-mapped cube of shape (elevation, azimuth, range);
                complex planes are reduced to their magnitude.
            x_axis: Elevation axis in metres, or bin indices for the raw tomogram.
            advance: Callback invoked once per ingested elevation plane.

        Returns:
            Entry with the float32 ``cube``, its ``x_axis`` and the 1st and 99th
            percentile colour limits estimated on a decimated subsample.
        """
        cube = np.empty(raw.shape, dtype=np.float32)

        for i in range(raw.shape[0]):
            plane   = np.asarray(raw[i])
            cube[i] = np.abs(plane) if np.iscomplexobj(plane) else plane
            advance()

        sample = cube[:, :: max(1, cube.shape[1] // 256), :: max(1, cube.shape[2] // 256)]
        sample = sample[np.isfinite(sample)]
        vmin, vmax = (np.percentile(sample, [1.0, 99.0]) if sample.size else (0.0, 1.0))

        return {
            "cube"   : cube,
            "x_axis" : x_axis,
            "vmin"   : float(vmin),
            "vmax"   : float(vmax),
        }

    def _curve_axis(self, reader: StampReader | FoldMosaic, n_elev: int) -> np.ndarray:
        """Returns the n_elev evenly spaced elevation bin centres in metres."""
        metrics = reader.metrics()
        return np.linspace(float(metrics["x_axis_min"]), float(metrics["x_axis_max"]), n_elev)

    def _preproc_layout(self, reader: StampReader | FoldMosaic) -> tuple[Path, dict] | None:
        """Resolves the preprocessing run backing a cube and its dataset layout.

        Args:
            reader: Stamp or mosaic reader whose run metadata is read.

        Returns:
            Tuple of the preprocessing run directory and the parsed
            ``data/dataset.json`` layout, or None when either is missing.
        """
        meta_path = reader.run_dir / "meta" / "dataset_creation_config.json"
        if not meta_path.is_file():
            return None

        payload     = json.loads(meta_path.read_text(encoding="utf-8"))
        preproc_dir = Path(payload["preprocessing_run_directory"])
        layout_path = preproc_dir / "data" / "dataset.json"
        if not layout_path.is_file():
            return None

        layout = json.loads(layout_path.read_text(encoding="utf-8"))
        return preproc_dir, layout

    def _crop_bounds(self, reader: StampReader | FoldMosaic, layout: dict, n_az: int, n_rg: int) -> tuple[int, int, int, int]:
        """Maps the cube's split region into indices of the preprocessing arrays.

        Args:
            reader: Stamp or mosaic reader whose metrics carry the split region.
            layout: Dataset layout carrying the global crop applied at preprocessing.
            n_az: Azimuth extent of the cube, in pixels.
            n_rg: Range extent of the cube, in pixels.

        Returns:
            Tuple (azimuth low, azimuth high, range low, range high) of indices
            into the preprocessing arrays.

        Raises:
            KeyError: If the metrics payload carries no split region.
            ValueError: If the split region does not match the cube extents.
        """
        metrics = reader.metrics()
        if "split_region" not in metrics:
            raise KeyError(f"metrics.json in {reader.where} has no split_region; rerun inference to regenerate it")

        az_start, az_end, rg_start, rg_end = (int(v) for v in metrics["split_region"])
        if (az_end - az_start, rg_end - rg_start) != (n_az, n_rg):
            raise ValueError(f"split_region {metrics['split_region']} does not match the {n_az}x{n_rg} cube")

        global_crop = layout["global_crop"]

        az_lo = az_start - global_crop[0]
        az_hi = az_end   - global_crop[0]
        rg_lo = rg_start - global_crop[2]
        rg_hi = rg_end   - global_crop[2]
        return az_lo, az_hi, rg_lo, rg_hi

    def _full_raw(self, reader: StampReader | FoldMosaic, n_az: int, n_rg: int) -> np.ndarray | None:
        """Crops the full Capon tomogram of the preprocessing run to the cube footprint.

        Args:
            reader: Stamp or mosaic reader identifying the preprocessing run.
            n_az: Azimuth extent of the cube, in pixels.
            n_rg: Range extent of the cube, in pixels.

        Returns:
            Memory-mapped view of shape (elevation bins, n_az, n_rg), or None when
            the preprocessing run publishes no full tomogram.

        Raises:
            ValueError: If the tomogram is not three-dimensional or does not cover
                the cube region.
        """
        resolved = self._preproc_layout(reader)
        if resolved is None:
            return None

        preproc_dir, layout = resolved

        tomo_name = layout["artifacts"].get("tomogram_full")
        if not tomo_name:
            return None

        tomo_path = preproc_dir / "data" / tomo_name
        if not tomo_path.is_file():
            return None

        az_lo, az_hi, rg_lo, rg_hi = self._crop_bounds(reader, layout, n_az, n_rg)

        raw = np.load(tomo_path, mmap_mode="r")
        if raw.ndim != 3:
            raise ValueError(f"full tomogram is not a 3D cube: shape={raw.shape}")
        if az_lo < 0 or rg_lo < 0 or az_hi > raw.shape[1] or rg_hi > raw.shape[2]:
            raise ValueError(f"cube region az[{az_lo}:{az_hi}] rg[{rg_lo}:{rg_hi}] falls outside the full tomogram {raw.shape}")

        return raw[:, az_lo:az_hi, rg_lo:rg_hi]

    def _primary_db(self, reader: StampReader | FoldMosaic, n_az: int, n_rg: int) -> np.ndarray:
        """Crops the primary SLC and returns its amplitude in dB.

        Args:
            reader: Stamp or mosaic reader identifying the preprocessing run.
            n_az: Azimuth extent of the cube, in pixels.
            n_rg: Range extent of the cube, in pixels.

        Returns:
            Float32 array of shape (n_az, n_rg) holding 20 log10 of the amplitude,
            floored at 1e-12 before the logarithm.

        Raises:
            FileNotFoundError: If the preprocessing run, its primary artifact
                entry or the primary file itself is missing.
            ValueError: If the primary is not a 2D image or does not cover the
                cube region.
        """
        resolved = self._preproc_layout(reader)
        if resolved is None:
            raise FileNotFoundError(f"cannot resolve the preprocessing run for {reader.where}; the primary SLC is required for the cube map")

        preproc_dir, layout = resolved

        primary_name = layout["artifacts"].get("primary")
        if not primary_name:
            raise FileNotFoundError(f"dataset.json in {preproc_dir} lists no primary artifact")

        primary_path = preproc_dir / "data" / primary_name
        if not primary_path.is_file():
            raise FileNotFoundError(f"primary SLC missing: {primary_path}")

        az_lo, az_hi, rg_lo, rg_hi = self._crop_bounds(reader, layout, n_az, n_rg)

        raw = np.load(primary_path, mmap_mode="r")
        if raw.ndim != 2:
            raise ValueError(f"primary SLC is not a 2D image: shape={raw.shape}")
        if az_lo < 0 or rg_lo < 0 or az_hi > raw.shape[0] or rg_hi > raw.shape[1]:
            raise ValueError(f"cube region az[{az_lo}:{az_hi}] rg[{rg_lo}:{rg_hi}] falls outside the primary SLC {raw.shape}")

        amplitude = np.abs(np.asarray(raw[az_lo:az_hi, rg_lo:rg_hi])).astype(np.float32)
        return 20.0 * np.log10(np.maximum(amplitude, 1e-12))


class SliceCollector:
    """Renders the same slices across many runs for side-by-side comparison.

    Opens stamps lazily through an LRU cache of lightweight contexts, so several
    runs can be previewed and collected without displacing the cube loaded in the
    Cube tab. Fold mosaics are rejected here.

    Attributes:
        cubes: Explorer supplying the readers, archiver and cut helpers.
        logger: Web logger for render and collection reporting.
        render_lock: Serialises figure writing during a collection.
        contexts: LRU cache of opened stamp contexts, keyed by stamp directory.
    """

    SOURCES    = ("pred", "gt", "reduced", "full")
    AXES       = ("range", "azimuth")
    MAX_RUNS   = 24
    MAX_POINTS = 24
    CACHE_CAP  = 16

    def __init__(self, cubes: CubeExplorer, logger: WebLogger) -> None:
        """Stores the explorer and logger and prepares the context cache."""
        self.cubes       = cubes
        self.logger      = logger
        self.render_lock = threading.Lock()
        self.contexts    = LruCache(self.CACHE_CAP)

    def info(self, cube_id: str) -> dict:
        """Describes one collectable cube.

        Args:
            cube_id: Stamp directory path.

        Returns:
            Dict with ``ok``, the stamp id, run, group and stamp names, the cube's
            azimuth and range extents, the available ``sources`` and their
            intensity limits, or ``ok`` False with the reason.
        """
        try:
            context = self._context(cube_id)
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

        if context is None:
            return {"ok": False, "error": f"unknown cube id: {cube_id}"}

        entries = context["entries"]
        return {
            "ok"        : True,
            "id"        : str(context["stamp_dir"]),
            "run"       : context["run"],
            "group"     : context["group"],
            "stamp"     : context["stamp"],
            "n_az"      : context["n_az"],
            "n_rg"      : context["n_rg"],
            "sources"   : [s for s in self.SOURCES if s in entries],
            "intensity" : {s: [entries[s]["vmin"], entries[s]["vmax"]] for s in entries},
        }

    def slice_png(self, cube_id: str, source: str, axis: str, az: int, rg: int, space: str = "physical", cmap: str = "jet", vmin: float | None = None, vmax: float | None = None) -> bytes | None:
        """Renders one slice of a collectable cube as a PNG.

        Args:
            cube_id: Stamp directory path.
            source: Cube key to render.
            axis: "range" or "azimuth".
            az: Azimuth pixel index, clipped into range.
            rg: Range pixel index, clipped into range.
            space: "physical" or "normalized".
            cmap: Colormap name.
            vmin: Optional lower colour limit, honoured only in physical space.
            vmax: Optional upper colour limit, honoured only in physical space.

        Returns:
            PNG bytes, or None when the arguments are invalid or the cube carries
            no such source.
        """
        if source not in self.SOURCES or axis not in self.AXES or space not in ("physical", "normalized"):
            return None

        try:
            context = self._context(cube_id)
        except Exception as error:
            self.logger.warning(f"slice render for {cube_id} failed while opening the cube: {error}")
            return None

        if context is None:
            self.logger.warning(f"slice render refused: unknown cube id {cube_id}")
            return None

        entry = context["entries"].get(source)
        if entry is None:
            self.logger.warning(f"slice render refused: {cube_id} carries no '{source}' cube")
            return None

        data, heights, lo, hi = self._cut(entry, axis, az, rg, space)
        if space == "physical" and vmin is not None and vmax is not None and vmax > vmin:
            lo, hi = float(vmin), float(vmax)

        buf = io.BytesIO()
        plt.imsave(buf, np.flipud(data), cmap=CubeExplorer._entry_cmap(entry, cmap), vmin=lo, vmax=hi, format="png")
        return buf.getvalue()

    def collect(self, ids: list, points: list, sources: list, axes: list, space: str = "physical", cmap: str = "jet", shared: bool = True, name: str = "") -> dict:
        """Renders and archives a grid of slices across runs, points, sources and axes.

        Figures land under ``<runs root>/slice_collections/<name>`` in one folder
        per point and cut, next to a ``collection.json`` manifest.

        Args:
            ids: Stamp directory paths, deduplicated, at most MAX_RUNS.
            points: Dicts with ``az`` and ``rg`` pixel indices, at most MAX_POINTS.
            sources: Cube keys to render, a non-empty subset of SOURCES.
            axes: Cut axes to render, a non-empty subset of AXES.
            space: "physical" or "normalized".
            cmap: Colormap name.
            shared: When True and space is physical, all runs of a source share
                the widest colour range across them.
            name: Collection folder name; sanitised, and defaulted to a timestamp.

        Returns:
            Dict with ``ok``, the output ``dir``, the resolved ``name``, the
            written ``files``, the run-source pairs that were ``missing`` and the
            number of runs, or ``ok`` False with the reason.
        """
        ids     = list(dict.fromkeys(str(i) for i in ids if i))
        sources = list(dict.fromkeys(sources))
        axes    = list(dict.fromkeys(axes))

        if not ids:
            return {"ok": False, "error": "select at least one run"}
        if len(ids) > self.MAX_RUNS:
            return {"ok": False, "error": f"at most {self.MAX_RUNS} runs per collection, got {len(ids)}"}
        if space not in ("physical", "normalized"):
            return {"ok": False, "error": f"unknown space: {space}"}
        if not sources or any(s not in self.SOURCES for s in sources):
            return {"ok": False, "error": f"sources must be a non-empty subset of {self.SOURCES}"}
        if not axes or any(a not in self.AXES for a in axes):
            return {"ok": False, "error": f"axes must be a non-empty subset of {self.AXES}"}

        try:
            points   = self._points(points)
            contexts = []
            for cube_id in ids:
                context = self._context(cube_id)
                if context is None:
                    return {"ok": False, "error": f"unknown cube id: {cube_id}"}
                contexts.append(context)
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

        labels  = self._labels(contexts)
        title   = re.sub(r"[^A-Za-z0-9._-]+", "_", name or "").strip("._")
        title   = title or datetime.now().strftime("collection_%Y%m%d_%H%M%S")
        out_dir = contexts[0]["root"] / "slice_collections" / title

        if out_dir.exists():
            return {"ok": False, "error": f"a collection named '{title}' already exists at {out_dir}; pick another name or delete it first"}

        clims   = {source: self._shared_clim(contexts, source, space) if shared else None for source in sources}
        missing = [{"label": label, "source": source} for source in sources for context, label in zip(contexts, labels) if source not in context["entries"]]

        files = []
        with self.render_lock:
            for az, rg in points:
                point_dir = out_dir / f"az{az:04d}_rg{rg:04d}"
                for source in sources:
                    clim = clims[source]
                    for axis in axes:
                        cut_dir = point_dir / f"{axis}_{source}_{space}"
                        for context, label in zip(contexts, labels):
                            entry = context["entries"].get(source)
                            if entry is None:
                                continue

                            az_i = int(np.clip(az, 0, context["n_az"] - 1))
                            rg_i = int(np.clip(rg, 0, context["n_rg"] - 1))
                            data, heights, vmin, vmax = self._cut(entry, axis, az_i, rg_i, space)
                            if clim is not None:
                                vmin, vmax = clim

                            saved = self.cubes.archiver.render(data, heights, vmin, vmax, source, axis, az_i, rg_i, space, cut_dir / f"{label}.png", cmap=CubeExplorer._entry_cmap(entry, cmap), label=label)
                            files.append(str(saved.relative_to(out_dir)))

        if not files:
            return {"ok": False, "error": "no figures rendered; none of the selected runs carry the requested sources"}

        manifest = {
            "name"    : title,
            "created" : datetime.now().isoformat(timespec="seconds"),
            "space"   : space,
            "cmap"    : cmap,
            "shared"  : bool(shared),
            "axes"    : axes,
            "sources" : sources,
            "points"  : [{"az": az, "rg": rg} for az, rg in points],
            "clims"   : {source: (list(clim) if clim else None) for source, clim in clims.items()},
            "runs"    : [{"id": str(c["stamp_dir"]), "run": c["run"], "group": c["group"], "stamp": c["stamp"], "label": label} for c, label in zip(contexts, labels)],
            "missing" : missing,
            "files"   : files,
        }
        (out_dir / "collection.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")

        self.logger.ok(f"collected {len(files)} slice figures from {len(contexts)} runs into {out_dir}")
        return {"ok": True, "dir": str(out_dir), "name": title, "files": files, "missing": missing, "runs": len(contexts)}

    def _points(self, raw) -> list:
        """Validates and deduplicates the requested collection points.

        Args:
            raw: List of dicts carrying ``az`` and ``rg`` pixel indices.

        Returns:
            List of unique (azimuth, range) pairs in request order.

        Raises:
            ValueError: If the list is empty or not a list, exceeds MAX_POINTS, or
                holds a negative index.
        """
        if not isinstance(raw, list) or not raw:
            raise ValueError("points must be a non-empty list of {az, rg}")
        if len(raw) > self.MAX_POINTS:
            raise ValueError(f"at most {self.MAX_POINTS} points per collection, got {len(raw)}")

        points = []
        seen   = set()
        for entry in raw:
            az, rg = int(entry["az"]), int(entry["rg"])
            if az < 0 or rg < 0:
                raise ValueError(f"point az={az}, rg={rg} is negative")
            if (az, rg) in seen:
                continue
            seen.add((az, rg))
            points.append((az, rg))

        return points

    @staticmethod
    def _labels(contexts: list) -> list:
        """Builds one unique file label per context.

        Run names are used as-is, prefixed with their group when the name repeats
        and suffixed with the stamp name when that is still not unique.

        Args:
            contexts: Opened stamp contexts, in collection order.

        Returns:
            One label per context, in the same order.
        """
        counts = {}
        for context in contexts:
            counts[context["run"]] = counts.get(context["run"], 0) + 1

        grouped = []
        for context in contexts:
            label = context["run"]
            if counts[label] > 1 and context["group"] not in (".", ""):
                label = f"{context['group'].replace('/', '_')}__{label}"
            grouped.append(label)

        labels = []
        for context, label in zip(contexts, grouped):
            if grouped.count(label) > 1:
                label = f"{label}__{context['stamp']}"
            labels.append(label)

        return labels

    @staticmethod
    def _shared_clim(contexts: list, source: str, space: str) -> tuple[float, float] | None:
        """Returns the colour range covering one source across every context.

        Args:
            contexts: Opened stamp contexts.
            source: Cube key whose limits are merged.
            space: Only "physical" yields shared limits.

        Returns:
            The (vmin, vmax) envelope, or None in normalised space, when no
            context carries the source or when the envelope is degenerate.
        """
        if space != "physical":
            return None

        entries = [context["entries"][source] for context in contexts if source in context["entries"]]
        if not entries:
            return None

        vmin = min(entry["vmin"] for entry in entries)
        vmax = max(entry["vmax"] for entry in entries)
        return (vmin, vmax) if vmax > vmin else None

    @staticmethod
    def _cut(entry: dict, axis: str, az: int, rg: int, space: str) -> tuple[np.ndarray, np.ndarray, float, float]:
        """Extracts one elevation slice from a lazily held cube.

        Unlike the explorer's cut, the cube here may still be memory-mapped or
        complex, so the slice is materialised and reduced to magnitude first.

        Args:
            entry: Context entry holding the cube and its elevation axis.
            axis: "range" for a fixed range column, "azimuth" for a fixed azimuth row.
            az: Azimuth pixel index, clipped into range.
            rg: Range pixel index, clipped into range.
            space: "normalized" to peak-normalise columns, else "physical".

        Returns:
            Tuple of the float32 slice of shape (elevation bins, samples) ordered
            by ascending elevation, the elevation axis in metres, and the colour
            limits.
        """
        cube               = entry["cube"]
        n_elev, n_az, n_rg = cube.shape

        az   = int(np.clip(az, 0, n_az - 1))
        rg   = int(np.clip(rg, 0, n_rg - 1))
        data = np.asarray(cube[:, :, rg] if axis == "range" else cube[:, az, :])
        data = np.abs(data).astype(np.float32) if np.iscomplexobj(data) else data.astype(np.float32)

        data, vmin, vmax = CubeExplorer._normalize_cut(entry, data, space)

        order   = np.argsort(entry["x_axis"])
        heights = np.asarray(entry["x_axis"], dtype=np.float64)[order]
        return data[order], heights, float(vmin), float(vmax)

    def _context(self, cube_id: str) -> dict | None:
        """Returns the cached or freshly built context of a stamp.

        Args:
            cube_id: Stamp directory path.

        Returns:
            The stamp context, or None when the id is unknown.

        Raises:
            ValueError: If the id refers to a cross-validation fold mosaic.
        """
        reader = self.cubes._open_source(cube_id)
        if reader is None:
            return None
        if isinstance(reader, FoldMosaic):
            raise ValueError("cross-validation mosaics load in the Cube tab only; pick the individual fold cubes here")

        key    = str(reader.stamp_dir)
        cached = self.contexts.get(key)
        if cached is not None:
            return cached

        context = self._build_context(reader)
        self.contexts.put(key, context)

        return context

    def _build_context(self, reader: StampReader) -> dict:
        """Opens the cubes of a stamp without materialising them.

        Args:
            reader: Reader of the stamp to open.

        Returns:
            Context with the stamp directory, its runs root, the run, group and
            stamp names, the azimuth and range extents and the lazily held
            ``entries`` per source.

        Raises:
            ValueError: If the stamp lies outside every catalogued runs root, the
                prediction cube is not three-dimensional, or a source disagrees
                with it spatially.
        """
        stamp_dir = reader.stamp_dir
        root      = self._root_for(stamp_dir)
        if root is None:
            raise ValueError(f"{stamp_dir} is outside every catalogued runs root")

        pred_raw = reader.curves("pred")
        if pred_raw.ndim != 3:
            raise ValueError(f"pred_curves.npy is not a 3D cube: shape={pred_raw.shape}")

        n_elev, n_az, n_rg = pred_raw.shape
        curve_axis         = self.cubes._curve_axis(reader, n_elev)

        entries = {"pred": self._entry(pred_raw, curve_axis)}
        for source in ("gt", "reduced"):
            raw = reader.curves(source)
            if raw is not None:
                if raw.shape[1:] != (n_az, n_rg):
                    raise ValueError(f"source '{source}' spatial shape {raw.shape[1:]} does not match pred {(n_az, n_rg)}")
                entries[source] = self._entry(raw, curve_axis)

        full_raw = self.cubes._full_raw(reader, n_az, n_rg)
        if full_raw is not None:
            entries["full"] = self._entry(full_raw, np.arange(full_raw.shape[0], dtype=np.float64))

        run_dir = reader.run_dir
        return {
            "stamp_dir" : stamp_dir,
            "root"      : root,
            "run"       : run_dir.name,
            "group"     : str(run_dir.relative_to(root).parent),
            "stamp"     : stamp_dir.name,
            "n_az"      : n_az,
            "n_rg"      : n_rg,
            "entries"   : entries,
        }

    @staticmethod
    def _entry(raw: np.ndarray, x_axis: np.ndarray) -> dict:
        """Wraps a cube without materialising it and estimates its colour limits.

        Args:
            raw: Memory-mapped cube of shape (elevation, azimuth, range).
            x_axis: Elevation axis in metres, or bin indices for the raw tomogram.

        Returns:
            Entry with the untouched ``cube``, its ``x_axis`` and the 1st and 99th
            percentile colour limits estimated on a decimated subsample.
        """
        sample = np.asarray(raw[:, :: max(1, raw.shape[1] // 256), :: max(1, raw.shape[2] // 256)])
        sample = np.abs(sample) if np.iscomplexobj(sample) else sample
        sample = sample[np.isfinite(sample)]
        vmin, vmax = (np.percentile(sample, [1.0, 99.0]) if sample.size else (0.0, 1.0))

        return {
            "cube"   : raw,
            "x_axis" : x_axis,
            "vmin"   : float(vmin),
            "vmax"   : float(vmax),
        }

    def _root_for(self, stamp_dir: Path) -> Path | None:
        """Returns the catalogued runs root containing the stamp, or None."""
        return self.cubes.roots.enclosing(stamp_dir)

