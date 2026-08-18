"""Tests covering ExtrasRequirementsWriter: flattening the declared optional-dependency groups, the written file's shape, and the Dockerfile consuming it rather than restating pins."""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

from extras_requirements import ExtrasRequirementsWriter


def _writer(repo_root: Path, tmp_path: Path) -> ExtrasRequirementsWriter:
    """Returns a writer reading the repository pyproject and writing into tmp_path."""
    return ExtrasRequirementsWriter(repo_root / "pyproject.toml", tmp_path / "extras.txt")


def test_flattened_extras_cover_every_declared_group(repo_root, tmp_path):
    """Verifies the flattened list contains every requirement of every declared extras group."""
    writer    = _writer(repo_root, tmp_path)
    extras    = writer.read_extras()
    flattened = writer.flatten(extras)

    assert set(extras) == {"processing", "sigma", "dev"}
    assert all(requirement in flattened for group in extras.values() for requirement in group)


def test_written_file_lists_one_requirement_per_line(repo_root, tmp_path):
    """Verifies the written file holds the flattened requirements, deduplicated and sorted."""
    writer = _writer(repo_root, tmp_path)
    path   = writer.build()
    lines  = path.read_text(encoding="utf-8").splitlines()

    assert lines == writer.flatten(writer.read_extras())
    assert lines == sorted(set(lines))


def test_missing_optional_dependencies_raise(tmp_path):
    """Verifies a pyproject without optional dependencies is rejected."""
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text('[project]\nname = "x"\noptional-dependencies = {}\n', encoding="utf-8")

    with pytest.raises(ValueError):
        ExtrasRequirementsWriter(pyproject, tmp_path / "extras.txt").build()


def test_dockerfile_never_restates_an_extra(repo_root, tmp_path):
    """Verifies the Dockerfile installs the generated requirements instead of naming any extra."""
    dockerfile   = (repo_root / "Dockerfile").read_text(encoding="utf-8")
    requirements = _writer(repo_root, tmp_path).flatten(_writer(repo_root, tmp_path).read_extras())
    restated     = [name for name in (re.split(r"[=<>!~\[]", requirement, maxsplit=1)[0] for requirement in requirements) if name in dockerfile]

    assert "extras_requirements.py" in dockerfile
    assert "-r /tmp/build/requirements.txt" in dockerfile
    assert restated == []
