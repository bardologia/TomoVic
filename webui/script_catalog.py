"""Curated metadata of every console entry point.

Holds the title, category and purpose text shown for each entry, the analysis
topic each one belongs to, and the groups that fold several stage-specific entries
into one console card with variant tabs.
"""

from __future__ import annotations

from project_paths          import ProjectPaths
from script_config_resolver import ScriptConfigResolver


class ScriptCatalog:
    """Lists the entry points that exist on disk, with their metadata and grouping.

    Attributes:
        paths: Project paths resolving each entry key to a file.
        resolver: Config resolver providing each entry's configuration class name.
    """

    META = {
        "pre_process": {
            "title"     : "Pre-process",
            "category"  : "Data",
            "purpose"   : "Ingest raw F-SAR products, beamform the tomogram, and form interferograms.",
        },
        "extract_params": {
            "title"     : "Extract Parameters",
            "category"  : "Data",
            "purpose"   : "Fit per-pixel Gaussian mixtures to the focused tomogram, producing the parametrized tomogram stored as a parameter run inside each dataset. Sweeps every permutation of the selected datasets, K values, lambda values, and fit modes.",
        },
        "analyze_preprocessing": {
            "title"     : "Analyze Preprocessing",
            "category"  : "Analysis",
            "purpose"   : "Render the stack-overview plots (SLC amplitudes, flattened interferograms, DEM) for one or more preprocessing trials, decoupled from the tomogram/interferogram generation step.",
        },
        "analyze_param_extraction": {
            "title"     : "Analyze Param Extraction",
            "category"  : "Analysis",
            "purpose"   : "Recompute the Gaussian-fit metrics, summary, and diagnostic plots for one or more parametrized-tomogram runs, decoupled from the GPU fitting step.",
        },
        "compare_preprocessing_trials": {
            "title"     : "Compare Preprocessing",
            "category"  : "Analysis",
            "purpose"   : "Compare preprocessing trials that differ by multilook window size. Surfaces the bias-variance trade-off per window (contrast, residual speckle, spurious peaks, azimuth correlation length) as descriptive tables and plots, without forcing a single winner.",
        },
    }

    TOPICS = {
        "analyze_preprocessing"        : "trials",
        "analyze_param_extraction"     : "trials",
        "compare_preprocessing_trials" : "trials",
    }

    GROUPS = {}

    def __init__(self, paths: ProjectPaths, resolver: ScriptConfigResolver) -> None:
        """Stores the project paths and the configuration resolver."""
        self.paths    = paths
        self.resolver = resolver

    def _group_of(self, key: str) -> tuple[str | None, dict | None, str | None]:
        """Returns the group key, group and variant label of an entry, or a triple of None."""
        for group_key, group in self.GROUPS.items():
            for member_key, label in group["members"]:
                if member_key == key:
                    return group_key, group, label
        return None, None, None

    def _variants(self, group: dict) -> list[dict]:
        """Returns the group members whose entry file exists on disk."""
        variants = []
        for member_key, label in group["members"]:
            if self.paths.script_entry(member_key)["path"].exists():
                variants.append({"key": member_key, "label": label})
        return variants

    def list_scripts(self) -> list[dict]:
        """Returns one catalog record per entry point present on disk.

        Each record carries the entry key and relative file, its title, category and
        purpose, the detected configuration class, the analysis topic, and the group,
        variant label and sibling variants when the entry belongs to a group.
        """
        entries = []
        for key in self.META:
            spec = self.paths.script_entry(key)
            if not spec["path"].exists():
                continue

            meta  = self.META[key]
            entry = self.resolver.entry_config(key)

            group_key, group, label = self._group_of(key)

            entries.append({
                "key"            : key,
                "file"           : spec["rel"],
                "title"          : meta["title"],
                "category"       : meta["category"],
                "purpose"        : meta["purpose"],
                "config_class"   : entry["class"] if entry else None,
                "topic"          : self.TOPICS.get(key),
                "group"          : group_key,
                "variant"        : label,
                "group_title"    : group["title"] if group else None,
                "group_category" : group["category"] if group else None,
                "group_purpose"  : group["purpose"] if group else None,
                "variants"       : self._variants(group) if group else [],
            })
        return entries

    def get_script(self, key: str) -> dict | None:
        """Returns one entry point's full detail, source text included.

        Args:
            key: Entry-point key.

        Returns:
            Record with the catalog metadata, the entry source, the shell command, the
            preferred interpreter and the group variants, or None when the entry file
            does not exist.
        """
        spec = self.paths.script_entry(key)
        if not spec["path"].exists():
            return None

        meta    = self.META.get(key, {"title": key, "category": "Other", "purpose": ""})
        source  = spec["path"].read_text(encoding="utf-8")
        entry   = self.resolver.entry_config(key)
        command = f"python {spec['rel']}"

        group_key, group, label = self._group_of(key)

        return {
            "key"          : key,
            "file"         : spec["rel"],
            "title"        : meta["title"],
            "category"     : meta["category"],
            "purpose"      : meta["purpose"],
            "source"       : source,
            "language"     : "python",
            "config_class" : entry["class"] if entry else None,
            "command"      : command,
            "preferred"    : self.paths.preferred_interpreter(self.paths.discover_interpreters(), key),
            "group"        : group_key,
            "group_title"  : group["title"] if group else None,
            "variant"      : label,
            "variants"     : self._variants(group) if group else [],
        }
