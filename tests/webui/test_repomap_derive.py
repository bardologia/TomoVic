"""Tests for the derived import graph and repository map skeleton.

Covers internal import edge discovery over the real repository, the folder
skeleton, and the drift report comparing the curated repomap against files on
disk.
"""
from __future__ import annotations

import json

from repomap_derive import ImportGraph, RepoMapDeriver

from tests.webui.conftest import REPO_ROOT, WEBUI_ROOT


def test_import_graph_finds_known_internal_edges():
    """The import graph carries a known pipeline edge and every target is itself a node."""
    graph = ImportGraph(REPO_ROOT).build()

    assert "pipelines.processing.generation.pipeline" in graph
    assert "pipelines.processing.generation.artifacts" in graph["pipelines.processing.generation.pipeline"]
    assert all(target in graph for targets in graph.values() for target in targets)


def test_skeleton_groups_by_top_folder():
    """The skeleton groups modules under the top-level folders and gives pipelines nodes and edges."""
    skeleton = RepoMapDeriver(REPO_ROOT).skeleton()
    folders  = {folder["folder"] for folder in skeleton["folders"]}

    assert {"main", "pipelines", "tools", "configuration", "webui"} <= folders

    pipelines = next(folder for folder in skeleton["folders"] if folder["folder"] == "pipelines")
    assert pipelines["nodes"] and pipelines["edges"]


def test_curated_repomap_references_only_existing_files():
    """The curated repomap references no module file that is absent from the repository."""
    curated = json.loads((WEBUI_ROOT / "repomap_data.json").read_text(encoding="utf-8"))
    drift   = RepoMapDeriver(REPO_ROOT).drift(curated)

    assert drift["missing_files"] == []


def test_drift_reports_vanished_modules():
    """A curated node pointing at a deleted module is reported as a missing file."""
    curated = {"folders": [{"folder": "tools", "diagrams": [{"key": "d", "nodes": [{"id": "gone", "module": "tools/erased_module.py"}]}]}]}
    drift   = RepoMapDeriver(REPO_ROOT).drift(curated)

    assert len(drift["missing_files"]) == 1
    assert drift["missing_files"][0]["module"] == "tools/erased_module.py"


def test_drift_rejects_a_module_path_that_is_only_a_package_directory():
    """A .py path that exists only as a package directory is reported as missing."""
    curated = {"folders": [{"folder": "configuration", "diagrams": [{"key": "d", "nodes": [{"id": "cfg", "module": "configuration/sar.py"}]}]}]}
    drift   = RepoMapDeriver(REPO_ROOT).drift(curated)

    assert (REPO_ROOT / "configuration" / "sar").is_dir()
    assert [entry["module"] for entry in drift["missing_files"]] == ["configuration/sar.py"]


def test_drift_accepts_a_directory_node_without_a_py_suffix():
    """A curated node naming a package directory without a .py suffix is accepted."""
    curated = {"folders": [{"folder": "pipelines", "diagrams": [{"key": "d", "nodes": [{"id": "dir", "module": "pipelines/processing"}]}]}]}
    drift   = RepoMapDeriver(REPO_ROOT).drift(curated)

    assert drift["missing_files"] == []


def test_relative_and_webui_local_imports_resolve():
    """Relative imports and webui-local imports resolve to fully qualified module names."""
    graph = ImportGraph(REPO_ROOT).build()

    assert "tools.sar.track_parameters" in graph["tools.sar.geometry_field"]
    assert "webui.project_paths" in graph["webui.script_config_resolver"]
    assert "webui.routers.dispatch" in graph["webui.request_router"]

    webui_edges = sum(len(targets) for name, targets in graph.items() if name.startswith("webui."))
    assert webui_edges > 30
