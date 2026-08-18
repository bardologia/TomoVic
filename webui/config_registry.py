"""Static inventory of the configuration dataclasses for the web UI config tab.

Parses the configuration package with `ast` instead of importing it, so every
dataclass field is listed with its annotation, default and blank-line grouping,
then joins the result against the curated descriptions file and caches it against
the configuration directory signature.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path

from project_paths import ProjectPaths


class ConfigRegistry:
    """Collects the configuration dataclasses, their fields and their descriptions.

    Attributes:
        paths: Project paths providing the configuration directory and its signature.
        descriptions: Curated section, class and field descriptions loaded from disk.
        collected: Cache of (signature, groups), None until the first collection.
    """

    DESCRIPTIONS_FILE = "config_descriptions.json"

    SECTION_TITLES = {
        "sar"              : "SAR Processing",
        "param_extraction" : "Parameter Extraction",
        "normalization"    : "Normalization",
        "dataset"          : "Dataset",
        "architectures"    : "Model Architectures",
        "training"         : "Training",
        "inference"        : "Inference",
        "benchmark"        : "Benchmark",
        "cross_validation" : "Cross-validation",
        "patch_sweep"      : "Patch Sweep",
        "tuning"           : "Tuning",
        "comparison"       : "Run Comparison",
        "diagnostics"      : "Diagnostics",
    }

    SECTION_ORDER = ["sar", "param_extraction", "normalization", "dataset", "architectures", "training", "inference", "benchmark", "cross_validation", "patch_sweep", "tuning", "comparison", "diagnostics"]

    def __init__(self, paths: ProjectPaths) -> None:
        """Loads the description file and prepares an empty parse cache.

        Args:
            paths: Project paths locating the configuration package.
        """
        self.paths        = paths
        self.descriptions = self._load_descriptions()
        self.collected    = None

    def _load_descriptions(self) -> dict:
        """Returns the parsed config_descriptions.json shipped next to this module."""
        path = Path(__file__).resolve().parent / self.DESCRIPTIONS_FILE
        return json.loads(path.read_text(encoding="utf-8"))

    def _parse_module(self, path: Path) -> list[dict]:
        """Extracts the annotated dataclasses declared at the top level of a module.

        Args:
            path: Python source file inside the configuration package.

        Returns:
            One entry per dataclass carrying at least one annotated field, with the
            class name and its parsed fields.
        """
        tree = ast.parse(path.read_text(encoding="utf-8"))

        classes = []
        for node in tree.body:
            if not isinstance(node, ast.ClassDef):
                continue
            if not self._is_dataclass(node):
                continue
            fields = self._parse_fields(node)
            if not fields:
                continue
            classes.append({"name": node.name, "fields": fields})
        return classes

    def _is_dataclass(self, node: ast.ClassDef) -> bool:
        """Returns whether the class carries a bare or called `dataclass` decorator."""
        for deco in node.decorator_list:
            target = deco.func if isinstance(deco, ast.Call) else deco
            if isinstance(target, ast.Name) and target.id == "dataclass":
                return True
            if isinstance(target, ast.Attribute) and target.attr == "dataclass":
                return True
        return False

    def _parse_fields(self, node: ast.ClassDef) -> list[dict]:
        """Returns the annotated fields of a dataclass, split into source blocks.

        A blank line between two annotated assignments starts a new group, which the
        UI uses to keep the author's visual grouping of related settings.

        Args:
            node: Class definition to inspect.

        Returns:
            One entry per annotated field with its name, unparsed annotation,
            rendered default and zero-based group index.
        """
        fields   = []
        group    = 0
        prev_end = None
        for item in node.body:
            if not isinstance(item, ast.AnnAssign):
                continue
            if not isinstance(item.target, ast.Name):
                continue

            if prev_end is not None and item.lineno - prev_end > 1:
                group += 1
            prev_end = item.end_lineno

            name       = item.target.id
            annotation = self._safe_unparse(item.annotation)
            default    = self._format_default(item.value)

            fields.append({
                "name"    : name,
                "type"    : annotation,
                "default" : default,
                "group"   : group,
            })
        return fields

    def _format_default(self, value: ast.expr | None) -> str:
        """Renders a field default as source text for display.

        Args:
            value: Default expression node, or None for a field without a default.

        Returns:
            "required" when there is no default, the unparsed source of a plain
            default, "<factory>()" for a `field(default_factory=...)`, the unparsed
            source of a `field(default=...)`, or "factory" for any other `field(...)`.
        """
        if value is None:
            return "required"
        if isinstance(value, ast.Call):
            func     = value.func
            is_field = (isinstance(func, ast.Name) and func.id == "field") or (isinstance(func, ast.Attribute) and func.attr == "field")
            if is_field:
                for kw in value.keywords:
                    if kw.arg == "default_factory":
                        inner = self._safe_unparse(kw.value)
                        return f"{inner}()"
                    if kw.arg == "default":
                        return self._safe_unparse(kw.value)
                return "factory"
        return self._safe_unparse(value)

    def _safe_unparse(self, node: ast.expr | None) -> str:
        """Returns the source text of an expression node, empty string for None."""
        if node is None:
            return ""
        return ast.unparse(node)

    def _section_units(self) -> list[tuple[str, list[Path]]]:
        """Groups the configuration package into sections of source files.

        Each subpackage becomes one section holding its modules recursively, and
        each top-level module becomes a section of its own. Sections named in
        SECTION_ORDER come first, in that order, and any others follow.

        Returns:
            List of (section name, module paths) pairs in display order.
        """
        members = sorted(self.paths.config_dir.iterdir())
        dirs    = [p for p in members if p.is_dir()  and not p.name.startswith(("_", "."))]
        files   = [p for p in members if p.is_file() and p.suffix == ".py" and p.name != "__init__.py"]

        units: dict[str, list[Path]] = {}
        for d in dirs:
            units[d.name] = [p for p in sorted(d.rglob("*.py")) if p.name != "__init__.py"]
        for f in files:
            units[f.stem] = [f]

        known = [s for s in self.SECTION_ORDER if s in units]
        extra = [s for s in units if s not in self.SECTION_ORDER]
        return [(s, units[s]) for s in known + extra]

    def _rel_module(self, path: Path) -> str:
        """Returns the module path relative to the configuration directory, suffix stripped."""
        return path.relative_to(self.paths.config_dir).with_suffix("").as_posix()

    def _attach_descriptions(self, cls: dict) -> None:
        """Writes the curated class summary and per-field descriptions into a class entry.

        Args:
            cls: Parsed class entry, already carrying its module path.

        Raises:
            KeyError: If the class or any of its fields is unclaimed in the
                descriptions file, which is how new settings are caught.
        """
        entry       = self.descriptions["configs"][f"{cls['module']}::{cls['name']}"]
        cls["desc"] = entry["summary"]
        field_descs = entry["fields"]
        for field in cls["fields"]:
            field["desc"] = field_descs[field["name"]]

    def _parse_sections(self) -> list[dict]:
        """Parses every section and returns the described class groups.

        Returns:
            One entry per non-empty section with its module name, display title,
            section description and the described dataclasses it contains.
        """
        groups = []
        for section, files in self._section_units():
            classes = []
            for path in files:
                for cls in self._parse_module(path):
                    cls["module"] = self._rel_module(path)
                    self._attach_descriptions(cls)
                    classes.append(cls)
            if not classes:
                continue
            groups.append({
                "module"  : section,
                "title"   : self.SECTION_TITLES.get(section, section.replace("_", " ").title()),
                "desc"    : self.descriptions["sections"][section],
                "classes" : classes,
            })
        return groups

    def collect(self) -> list[dict]:
        """Returns the described config sections, reparsing only when the sources change.

        Returns:
            The section groups from `_parse_sections`, served from cache while the
            configuration directory signature is unchanged.
        """
        signature = self.paths.config_signature()

        if self.collected is not None and self.collected[0] == signature:
            return self.collected[1]

        groups         = self._parse_sections()
        self.collected = (signature, groups)
        return groups
