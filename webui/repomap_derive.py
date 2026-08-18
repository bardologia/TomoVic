"""Derives the repository import graph and checks the curated Repo Map against it.

Parses every source module under the tracked roots, keeps only intra-repository
imports, and reports which curated map nodes point at files that no longer exist
and which real modules the curated map does not cover.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path


class ImportGraph:
    """Builds the module-to-module import graph of the repository.

    Attributes:
        repo_root: Root of the repository whose sources are parsed.
    """

    ROOTS = ("main", "pipelines", "tools", "configuration", "webui")

    def __init__(self, repo_root: Path) -> None:
        """Stores the repository root the graph is built from."""
        self.repo_root = Path(repo_root)

    def _modules(self) -> list[Path]:
        """Returns every source file under the tracked roots, sorted by path.

        Raises:
            FileNotFoundError: If one of the tracked source roots is missing.
        """
        modules = []
        for root in self.ROOTS:
            base = self.repo_root / root
            if not base.is_dir():
                raise FileNotFoundError(f"Source root {base} does not exist; the import graph cannot cover {root}")
            modules += [path for path in base.rglob("*.py") if "__pycache__" not in path.parts and "node_modules" not in path.parts]

        return sorted(modules)

    def _module_name(self, path: Path) -> str:
        """Returns the dotted module name of a source path relative to the repository root."""
        return str(path.relative_to(self.repo_root).with_suffix("")).replace("/", ".")

    @staticmethod
    def _package_parts(module_name: str) -> list[str]:
        """Returns the package components of a dotted module name, dropping the module itself."""
        return module_name.split(".")[:-1]

    def _imports_of(self, path: Path, module_name: str) -> set[str]:
        """Returns the dotted names a module imports, resolving relative imports.

        Args:
            path: Source file to parse.
            module_name: Dotted name of that module, used to anchor relative imports.

        Returns:
            Set of absolute dotted names imported by the module.
        """
        tree    = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        imports = set()

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                if node.level == 0 and node.module:
                    imports.add(node.module)
                elif node.level > 0:
                    package = self._package_parts(module_name)
                    base    = package[: len(package) - (node.level - 1)]
                    if not base:
                        continue
                    if node.module:
                        imports.add(".".join(base + node.module.split(".")))
                    else:
                        imports.update(".".join(base + [alias.name]) for alias in node.names)

        return imports

    def build(self) -> dict[str, list[str]]:
        """Returns the intra-repository import graph.

        Imports are attributed to the deepest existing module along the dotted
        name, webui modules imported by bare name are qualified, and
        self-imports are dropped.

        Returns:
            Mapping from dotted module name to the sorted dotted names it imports.
        """
        modules  = self._modules()
        by_name  = {self._module_name(path): path for path in modules}
        prefixes = tuple(f"{root}." for root in self.ROOTS)

        graph = {}
        for name, path in by_name.items():
            internal = set()
            for imported in self._imports_of(path, name):
                if name.startswith("webui.") and not imported.startswith(prefixes) and f"webui.{imported}" in by_name:
                    imported = f"webui.{imported}"

                if not (imported in by_name or imported.startswith(prefixes) or imported in self.ROOTS):
                    continue

                target = imported
                while target and target not in by_name:
                    target = target.rpartition(".")[0]
                if target:
                    internal.add(target)

            graph[name] = sorted(internal - {name})

        return graph


class RepoMapDeriver:
    """Turns the derived import graph into a map skeleton and audits the curated map.

    Attributes:
        repo_root: Root of the repository being mapped.
        graph: Import graph builder over that repository.
    """

    def __init__(self, repo_root: Path) -> None:
        """Stores the repository root and prepares its import graph builder."""
        self.repo_root = Path(repo_root)
        self.graph     = ImportGraph(repo_root)

    def skeleton(self) -> dict:
        """Returns an auto-derived map grouping modules and intra-folder edges by top folder.

        Returns:
            Mapping with "folders", each entry holding the folder name, its
            module nodes, and the import edges whose target lives in the same folder.
        """
        edges   = self.graph.build()
        folders = {}

        for module, targets in edges.items():
            folder = module.split(".")[0]
            entry  = folders.setdefault(folder, {"folder": folder, "nodes": [], "edges": []})

            entry["nodes"].append({"id": module, "module": module.replace(".", "/") + ".py"})
            entry["edges"] += [{"from": module, "to": target} for target in targets if target.split(".")[0] == folder]

        return {"folders": [folders[name] for name in sorted(folders)]}

    def drift(self, curated: dict) -> dict:
        """Compares the curated map against the real source tree.

        Args:
            curated: Curated map document with folders, diagrams and nodes.

        Returns:
            Mapping with "missing_files", the curated nodes whose module path no
            longer exists, and "uncovered_modules", the real modules outside
            webui and package initialisers that no curated node references.
        """
        missing_files = []
        for folder in curated["folders"]:
            for diagram in folder["diagrams"]:
                for node in diagram["nodes"]:
                    module = node.get("module")
                    if not module:
                        continue

                    path  = self.repo_root / module
                    found = path.is_file() if module.endswith(".py") else path.is_dir()

                    if not found:
                        missing_files.append({"folder": folder["folder"], "diagram": diagram["key"], "node": node["id"], "module": module})

        curated_modules = {
            node.get("module")
            for folder in curated["folders"]
            for diagram in folder["diagrams"]
            for node in diagram["nodes"]
            if node.get("module")
        }

        uncovered = []
        for module in self.graph.build():
            path = module.replace(".", "/") + ".py"
            top  = module.split(".")[0]
            if top == "webui" or module.endswith("__init__"):
                continue
            if path not in curated_modules:
                uncovered.append(path)

        return {"missing_files": missing_files, "uncovered_modules": sorted(uncovered)}

    def write_skeleton(self, output_path: Path) -> Path:
        """Writes the derived skeleton as indented JSON and returns the file path."""
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(self.skeleton(), indent=2), encoding="utf-8")

        return output_path
