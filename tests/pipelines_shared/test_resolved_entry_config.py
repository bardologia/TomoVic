"""Tests the resolved entry config writer, which records a run's configuration beside the provenance of the process that wrote it."""

from __future__ import annotations

import json
from dataclasses import dataclass

from pipelines.shared.config.resolved_entry_config import ResolvedEntryConfigWriter
from tools.monitoring.logger                       import NullLogger


@dataclass
class _Entry:
    """Minimal entry configuration with one leaf."""

    epochs : int = 3


def test_save_writes_the_config_and_a_provenance_record(tmp_path):
    """Verifies the resolved config lands under docs/ with a provenance file naming the commit and host beside it."""
    written    = ResolvedEntryConfigWriter.save(_Entry(), tmp_path, NullLogger())
    provenance = json.loads(ResolvedEntryConfigWriter.provenance_path_for(tmp_path).read_text())

    assert written == tmp_path / "docs" / "resolved_entry_config.json"
    assert written.is_file()
    assert provenance["written_at"]
    assert provenance["git_commit"]
    assert provenance["host"]
