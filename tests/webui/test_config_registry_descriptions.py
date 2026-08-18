"""Tests that every configuration dataclass exposed in the webui is documented.

Walks the parsed configuration tree and asserts each section, class and field
carries a description, that no description survives for a class or field that
was removed, that collection re-parses only when the tree signature changes, and
that the text stays within plain ASCII the frontend can render.
"""

from __future__ import annotations

import pytest

from config_registry import ConfigRegistry
from project_paths   import ProjectPaths


@pytest.fixture(scope="module")
def registry():
    """Returns a module-scoped config registry over the real project paths."""
    return ConfigRegistry(ProjectPaths())


@pytest.fixture(scope="module")
def groups(registry):
    """Returns the registry's collected section groups, computed once per module."""
    return registry.collect()


def _classes(groups):
    """Yields ``(group, class)`` pairs for every documented config class."""
    for group in groups:
        for cls in group["classes"]:
            yield group, cls


def test_collect_succeeds_and_is_non_empty(groups):
    """Checks collection yields sections and none of them is empty."""
    assert groups
    assert all(group["classes"] for group in groups)


def test_every_section_has_a_general_description(groups):
    """Checks each configuration section carries a general description."""
    for group in groups:
        assert group.get("desc"), f"section {group['module']} is missing a general description"


def test_every_class_has_a_summary(groups):
    """Checks each config dataclass carries a summary."""
    for _group, cls in _classes(groups):
        assert cls.get("desc"), f"{cls['module']}::{cls['name']} is missing a summary"


def test_every_field_has_a_description(groups):
    """Checks each config field carries a description."""
    for _group, cls in _classes(groups):
        for field in cls["fields"]:
            assert field.get("desc"), f"{cls['module']}::{cls['name']}.{field['name']} has no description"


def test_no_stale_config_entries(registry):
    """Checks no documented class or field remains after the dataclass or field is gone."""
    reachable = {}
    for _section, files in registry._section_units():
        for path in files:
            module = registry._rel_module(path)
            for cls in registry._parse_module(path):
                reachable[f"{module}::{cls['name']}"] = {field["name"] for field in cls["fields"]}

    configs       = registry.descriptions["configs"]
    stale_classes = [key for key in configs if key not in reachable]
    assert not stale_classes, f"stale config entries with no dataclass: {stale_classes}"

    stale_fields = []
    for key, entry in configs.items():
        for name in entry["fields"]:
            if name not in reachable[key]:
                stale_fields.append(f"{key}.{name}")
    assert not stale_fields, f"stale field descriptions with no field: {stale_fields}"


def test_section_map_matches_rendered_sections(registry, groups):
    """Checks every rendered section has a non-blank general description."""
    sections = registry.descriptions["sections"]
    rendered = {group["module"] for group in groups}
    missing  = rendered - set(sections)
    assert not missing, f"rendered sections without a general description: {missing}"
    for key, text in sections.items():
        assert text and text.strip(), f"empty section description for {key}"


def test_collect_reparses_only_when_the_configuration_tree_changes(monkeypatch):
    """Checks a repeat collect is served from cache until the tree signature changes."""
    fresh = ConfigRegistry(ProjectPaths())
    fresh.collect()

    parses = []
    monkeypatch.setattr(fresh, "_parse_sections", lambda: parses.append(1) or [])

    fresh.collect()
    assert not parses

    monkeypatch.setattr(fresh.paths, "config_signature", lambda: ("touched",))
    fresh.collect()

    assert len(parses) == 1


def test_descriptions_are_plain_ascii(groups):
    """Checks class and field descriptions avoid symbols above the arrows block."""
    for _group, cls in _classes(groups):
        blobs = [cls["desc"]] + [field["desc"] for field in cls["fields"]]
        for text in blobs:
            assert all(ord(ch) < 0x2190 for ch in text), f"non-ascii symbol in {cls['name']}: {text!r}"
