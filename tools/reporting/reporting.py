"""Asset linking and metric grouping used when assembling inference reports.

Holds the image-reference helper that either links figures relatively or embeds
them as data URIs, and the grouper that sorts flat metric names into the report's
thematic sections.
"""

from __future__ import annotations

import base64
import os
import re
from pathlib import Path
from typing  import List

from tools.runtime.run_tag import RunTag


class ReportAssets:
    """Builds Markdown image references relative to a report's base directory.

    Attributes:
        base: Directory the report is written to, relative links point from here.
        embed_images: Inlines existing images as base64 data URIs when True.
        timestamp: Stamp printed in the report header.
        MIME: Suffix to MIME type map used when embedding.
    """

    MIME = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".gif": "image/gif"}

    def __init__(self, base: Path, embed_images: bool = False, timestamp: str | None = None) -> None:
        """Initializes the asset helper for one report.

        Args:
            base: Directory relative links are computed against.
            embed_images: Inlines images as data URIs when True.
            timestamp: Header stamp; defaults to the current run timestamp.
        """
        self.base         = Path(base)
        self.embed_images = embed_images
        self.timestamp    = timestamp if timestamp is not None else RunTag.timestamp()

    def rel(self, target: Path) -> str:
        """Returns the target as a POSIX path relative to the report's base directory."""
        return Path(os.path.relpath(Path(target).resolve(), self.base.resolve())).as_posix()

    def src(self, path: Path) -> str:
        """Returns the image source, a base64 data URI when embedding, else a relative link."""
        path = Path(path)
        if self.embed_images and path.exists():
            mime = self.MIME.get(path.suffix.lower(), "image/png")
            data = base64.b64encode(path.read_bytes()).decode("ascii")
            return f"data:{mime};base64,{data}"
        return self.rel(path)

    def image(self, label: str, path: Path) -> List[str]:
        """Returns the Markdown lines embedding one labelled image."""
        return [f"![{label}]({self.src(path)})", ""]

    def images(self, label: str, paths) -> List[str]:
        """Returns the Markdown lines for one image or a sequence of them.

        Args:
            label: Alt text used when a single path is given.
            paths: One path, or an iterable of paths labelled by their stems.

        Returns:
            The Markdown lines for the requested images.
        """
        if isinstance(paths, (str, Path)):
            return self.image(label, Path(paths))

        out: List[str] = []
        for path in paths:
            out += self.image(Path(path).stem, Path(path))
        return out

    @staticmethod
    def natural_key(name: str) -> list:
        """Returns a sort key that orders embedded digit runs numerically."""
        return [int(token) if token.isdigit() else token for token in re.split(r"(\d+)", name)]

    def header(self, title: str) -> List[str]:
        """Returns the report's title heading and generation-timestamp line."""
        return [f"# {title}", f"\n_Generated {self.timestamp}_\n"]


class MetricSectionGrouper:
    """Sorts flat metric names into the report's thematic sections.

    Attributes:
        PER_BIN_PATTERN: Matches per-bin metric suffixes, which are excluded from
            the scalar table.
        METRIC_SECTIONS: Section titles paired with the pattern claiming their keys,
            applied in order so each key lands in its first matching section.
        LEFTOVER_TITLE: Section holding keys no pattern claimed.
    """

    PER_BIN_PATTERN = re.compile(r"_\d+$")

    METRIC_SECTIONS = [
        ("Dataset Statistics",           re.compile(r"^(n_pixels|n_elevation|x_axis_|gt_|pred_)")),
        ("Curve-Level",                  re.compile(r"^(curve_|overall_r2|psnr_)")),
        ("SSIM",                         re.compile(r"^ssim_")),
        ("Per-Pixel MSE and MAE",        re.compile(r"^pixel_(mse|mae)_")),
        ("Per-Pixel R² and Cosine",      re.compile(r"^pixel_(r2|cosine)_")),
        ("Peak Location Error",          re.compile(r"^pixel_peak_")),
        ("Per-Elevation-Bin Aggregates", re.compile(r"^elev_")),
        ("Slot Occupancy",               re.compile(r"^slot_")),
        ("Matched Gaussian (Permutation-Invariant)", re.compile(r"^matched_")),
        ("Label Quality",                re.compile(r"^label_")),
        ("Normalization Health",         re.compile(r"^(norm_in_|clamp_)")),
        ("Flip Consistency",             re.compile(r"^flip_")),
        ("Stratified Errors",            re.compile(r"^strat")),
        ("Failure Modes",                re.compile(r"^failure_")),
        ("Presence Calibration",         re.compile(r"^presence_")),
    ]

    LEFTOVER_TITLE = "Other Metrics"

    @classmethod
    def scalar_keys(cls, records) -> list[str]:
        """Returns the sorted scalar metric names present across records.

        Args:
            records: Objects exposing a metrics mapping.

        Returns:
            Sorted names of the numeric metrics, excluding per-bin entries.
        """
        return sorted({
            key
            for record in records
            for key, value in record.metrics.items()
            if isinstance(value, (int, float)) and not cls.PER_BIN_PATTERN.search(key)
        })

    def group(self, keys: list[str]) -> list[tuple[str, list[str]]]:
        """Partitions metric names into report sections.

        Args:
            keys: Metric names to distribute.

        Returns:
            List of (section title, keys) pairs in section order, ending with the
            leftover section when any key went unclaimed. Sections with no
            matching key are omitted.
        """
        all_keys = list(keys)
        claimed  : set[str]                    = set()
        sections : list[tuple[str, list[str]]] = []

        for title, pattern in self.METRIC_SECTIONS:
            matched = [key for key in all_keys if key not in claimed and pattern.search(key)]
            if not matched:
                continue
            claimed.update(matched)
            sections.append((title, matched))

        leftover = [key for key in all_keys if key not in claimed]
        if leftover:
            sections.append((self.LEFTOVER_TITLE, leftover))

        return sections
