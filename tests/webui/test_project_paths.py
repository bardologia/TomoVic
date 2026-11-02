"""Tests for repository root validation, the configuration signature and the interpreter default.

Covers acceptance of the real repository layout, the error naming the missing
top-level directories, the stability of the configuration mtime signature, and
the interpreter a job defaults to.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

from project_paths import ProjectPaths

from tests.webui.conftest import REPO_ROOT


def test_the_repository_root_is_accepted():
    """The repository root passes the layout check and is stored unchanged."""
    paths = ProjectPaths(REPO_ROOT)

    assert paths.repo_root == REPO_ROOT


def test_a_root_without_the_repository_layout_is_refused(tmp_path):
    """A root without the expected directories raises ValueError naming the path and all of them."""
    with pytest.raises(ValueError) as excinfo:
        ProjectPaths(tmp_path)

    message = str(excinfo.value)

    assert str(tmp_path) in message
    assert "main" in message and "configuration" in message and "tools" in message


def test_a_root_missing_one_directory_names_only_that_one(tmp_path):
    """A root missing a single directory names only that directory in the error."""
    for name in ("main", "configuration"):
        (tmp_path / name).mkdir()

    with pytest.raises(ValueError) as excinfo:
        ProjectPaths(tmp_path)

    assert "missing tools" in str(excinfo.value)


def test_the_configuration_signature_tracks_file_mtimes(tmp_path):
    """The configuration signature is non-empty and stable between calls without file changes."""
    paths  = ProjectPaths(REPO_ROOT)
    before = paths.config_signature()

    assert before
    assert before == paths.config_signature()


def test_a_priority_environment_is_preferred():
    """An interpreter whose label is in the priority list wins over the others."""
    paths        = ProjectPaths(REPO_ROOT)
    interpreters = [{"label": "conda:base", "path": "/base/bin/python", "current": False}, {"label": "conda:Dune", "path": "/envs/Dune/bin/python", "current": False}]

    assert paths.preferred_interpreter(interpreters) == "/envs/Dune/bin/python"


def test_the_running_interpreter_is_preferred_when_no_priority_environment_exists():
    """Without a priority environment the console defaults jobs to its own interpreter, not to the first one found."""
    paths        = ProjectPaths(REPO_ROOT)
    interpreters = [{"label": "conda:base", "path": "/base/bin/python", "current": False}]

    assert paths.preferred_interpreter(interpreters) == str(Path(sys.executable))
