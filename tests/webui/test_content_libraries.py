"""Tests for the curated webui content libraries: equations, flows and pipelines.

Asserts each catalog is internally consistent: unique group and item names,
filled-in tex and legends, MathJax-renderable macros, flow nodes and steps that
reference only declared ids and known vocabulary, and pipeline cards naming
launchable scripts.
"""

from __future__ import annotations

import re

import pytest

from equation_library       import EquationLibrary
from flow_library           import FlowLibrary
from pipeline_library       import PipelineLibrary
from project_paths          import ProjectPaths
from script_catalog         import ScriptCatalog
from script_config_resolver import ScriptConfigResolver

from tests.webui.conftest   import WEBUI_ROOT


NODE_ROLES = {"measured", "calculated", "intermediate", "final"}
NODE_KINDS = {"scalar", "vector", "matrix", "tensor", "set"}


@pytest.fixture(scope="module")
def equations():
    """Returns the collected equation catalog."""
    return EquationLibrary().collect()


@pytest.fixture(scope="module")
def flows():
    """Returns the collected flow-animation catalog."""
    return FlowLibrary().collect()


@pytest.fixture(scope="module")
def pipelines():
    """Returns the collected pipeline card catalog."""
    return PipelineLibrary().collect()


@pytest.fixture(scope="module")
def script_keys():
    """Returns the set of catalog keys the console can launch."""
    paths = ProjectPaths()
    return {entry["key"] for entry in ScriptCatalog(paths, ScriptConfigResolver(paths)).list_scripts()}


def test_equation_groups_are_named_once_and_carry_items(equations):
    """Checks equation groups have unique names and each carries a blurb and items."""
    names = [group["group"] for group in equations]

    assert equations
    assert sorted(names) == sorted(set(names))
    assert all(group["blurb"] and group["items"] for group in equations)


def test_every_equation_title_is_unique_inside_its_group(equations):
    """Checks no group repeats an equation title."""
    pairs = [(group["group"], item["title"]) for group in equations for item in group["items"]]

    assert sorted(pairs) == sorted(set(pairs))


def test_every_equation_has_tex_and_a_legend(equations):
    """Checks each equation has tex, a note and fully described legend symbols."""
    for group in equations:
        for item in group["items"]:
            assert item["tex"].strip(),  f"{item['title']} has no tex"
            assert item["note"].strip(), f"{item['title']} has no note"

            for variable in item["vars"]:
                assert variable["sym"].strip(),  item["title"]
                assert variable["desc"].strip(), item["title"]


def test_no_equation_uses_a_macro_the_renderer_cannot_draw(equations):
    """Checks no equation uses boldsymbol, which the MathJax setup cannot render."""
    offenders = [item["title"] for group in equations for item in group["items"] if "\\boldsymbol" in item["tex"]]

    assert not offenders, f"MathJax renders \\mathbf, not \\boldsymbol: {offenders}"


def test_the_flow_catalog_and_the_pipeline_catalog_agree(flows, pipelines):
    """Checks flows and pipeline cards expose the same keys in the same order."""
    assert [flow["key"] for flow in flows] == [pipeline["key"] for pipeline in pipelines]


def test_pipeline_scripts_point_at_real_entry_points(pipelines, script_keys):
    """Checks every script named by a pipeline card exists in the launch catalog."""
    named   = [pipeline["script"] for pipeline in pipelines if pipeline["script"]]
    missing = [key for key in named if key not in script_keys]

    assert not missing, f"pipeline cards naming scripts the console cannot launch: {missing}"


def test_every_pipeline_card_is_filled_in(pipelines):
    """Checks pipeline keys are unique and each card has a name, blurb and at least three stages."""
    keys = [pipeline["key"] for pipeline in pipelines]

    assert sorted(keys) == sorted(set(keys))
    for pipeline in pipelines:
        assert pipeline["name"] and pipeline["blurb"]
        assert len(pipeline["stages"]) >= 3, pipeline["key"]


def test_flow_node_ids_are_unique_within_a_flow(flows):
    """Checks each flow has a name, a blurb and no repeated node id."""
    for flow in flows:
        ids = [node["id"] for node in flow["nodes"]]

        assert flow["name"] and flow["blurb"]
        assert sorted(ids) == sorted(set(ids)), flow["key"]


def test_flow_nodes_use_the_known_vocabulary(flows):
    """Checks every node uses a known role and kind and declares tex, description and shape."""
    for flow in flows:
        for node in flow["nodes"]:
            assert node["role"] in NODE_ROLES, (flow["key"], node["id"], node["role"])
            assert node["kind"] in NODE_KINDS, (flow["key"], node["id"], node["kind"])
            assert node["tex"] and node["desc"] and node["shape"]


def test_every_flow_step_references_declared_nodes(flows):
    """Checks no walkthrough step reads or writes a node the flow never declared."""
    dangling = []

    for flow in flows:
        ids = {node["id"] for node in flow["nodes"]}
        for step in flow["steps"]:
            for reference in list(step["inputs"]) + list(step["outputs"]):
                if reference not in ids:
                    dangling.append((flow["key"], step["id"], reference))

    assert not dangling, f"walkthrough steps pointing at undeclared nodes: {dangling}"


def test_flow_steps_are_unique_and_produce_something(flows):
    """Checks step ids are unique and each step has a title, phase, note, outputs and lines."""
    for flow in flows:
        ids = [step["id"] for step in flow["steps"]]

        assert flow["steps"], flow["key"]
        assert sorted(ids) == sorted(set(ids)), flow["key"]

        for step in flow["steps"]:
            assert step["title"] and step["phase"] and step["note"]
            assert step["outputs"], (flow["key"], step["id"])
            assert step["lines"],   (flow["key"], step["id"])


def test_every_flow_sketch_matches_a_declared_step(flows):
    """Checks every sketch defined in flow_sketches.js corresponds to a declared flow step."""
    text  = (WEBUI_ROOT / "static" / "js" / "flow_sketches.js").read_text()
    keys  = set(re.findall(r"^  (\w+): \{$", text, re.M))
    steps = {step["id"] for flow in flows for step in flow["steps"]}

    assert keys <= steps, f"sketches without a flow step: {sorted(keys - steps)}"

