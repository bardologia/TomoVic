"""Tests of which dataset a TomoVis import is: the four identity rules of the bridge.

Rule 1 maps a link file to the dataset that owns it, rule 2 a file inside an
import folder to that import, rule 3 a run's full tomogram to the run, and rule
4 keys every other file by its kind and resolved path, refreshing the record
when the source changed.
"""

from __future__ import annotations

import os
import re
import time
from pathlib import Path

import numpy as np

from tests.webui.bridge_fixtures  import INPUTS, SESSIONS, BridgeHarness, FixtureCopies
from tests.webui.preproc_fixtures import make_preproc_run


def test_the_same_file_imported_twice_is_one_dataset(tmp_path):
    """Rule 4: a second import of one file finds the same folder and record, named <stem>_<kind>_<hash8>."""

    harness = BridgeHarness(tmp_path)
    first   = harness.imported("npy", INPUTS / "npy_real.npy")
    second  = harness.imported("npy", INPUTS / "npy_real.npy", sid="window-b")

    assert first is second
    assert re.fullmatch(r"npy_real_npy_[0-9a-f]{8}", Path(first.id).name)
    assert Path(first.id).parent == harness.root.resolve() / "imports"
    assert len(harness.workspace.records) == 1


def test_a_changed_source_refreshes_the_record(tmp_path):
    """Rule 4: a source whose size or time changed is prepared again, both revisions go up and the new cube is used."""

    harness = BridgeHarness(tmp_path)
    source  = FixtureCopies(tmp_path / "user").copy(INPUTS / "npy_real.npy", "cube.npy")
    record  = harness.imported("npy", source)
    before  = (record.revision, record.tomovis_revision)

    np.save(source, np.ones((4, 6, 5), dtype=np.float32))
    os.utime(source, ns=(time.time_ns(), time.time_ns() + 10**9))
    again = harness.imported("npy", source)

    assert again is record
    assert again.revision > before[0] and again.tomovis_revision == before[1] + 1
    assert again.state == "ready"
    assert harness.dataset(record.id)["tomogram"]["shape"] == [4, 6, 5]
    assert again.source["size"] == source.stat().st_size


def test_a_link_import_maps_to_its_owner(tmp_path):
    """Rule 1: importing a dataset's link file (as the hand-over does) finds that dataset, no new record."""

    harness = BridgeHarness(tmp_path)
    record  = harness.imported("hd5", INPUTS / "fusar_two_key_elev.hd5")
    link    = harness.dataset(record.id)["tomovis"]["link"]

    assert harness.imported("hd5", Path(link), sid="window-b") is record
    assert len(harness.workspace.records) == 1


def test_a_file_inside_an_import_folder_maps_to_that_import(tmp_path):
    """Rule 2: a file inside imports/<X>/ (even a symlink to the user's file) is dataset X."""

    harness = BridgeHarness(tmp_path)
    record  = harness.imported("npy", INPUTS / "npy_real.npy")
    inside  = Path(record.id) / "data" / "tomogram_full.npy"

    assert inside.is_symlink()
    assert harness.imported("npy", inside, sid="window-b") is record
    assert len(harness.workspace.records) == 1


def test_a_runs_tomogram_maps_to_the_run(tmp_path):
    """Rule 3: importing <run>/data/tomogram_full.npy registers the run itself, not an import."""

    harness = BridgeHarness(tmp_path)
    run_dir = make_preproc_run(tmp_path / "runs", with_spacing=True)
    record  = harness.imported("npy", run_dir / "data" / "tomogram_full.npy")

    assert record.id == str(run_dir.resolve())
    assert record.origin == "run"
    assert not (harness.root / "imports").exists() or not any((harness.root / "imports").iterdir())
    assert harness.cubes.roots.contains(run_dir.resolve())


def test_another_npy_inside_a_run_is_an_import(tmp_path):
    """Rule 3 needs the file the layout names as tomogram_full; another .npy in data/ is an import."""

    harness = BridgeHarness(tmp_path)
    run_dir = make_preproc_run(tmp_path / "runs")
    other   = run_dir / "data" / "extra.npy"
    np.save(other, np.zeros((3, 4, 5), dtype=np.float32))

    record = harness.imported("npy", other)

    assert record.origin == "import" and Path(record.id).name.startswith("extra_npy_")


def test_one_file_as_fusar_and_as_session_gives_two_ids(tmp_path):
    """The kind is part of the key: one .hd5 opened as FuSAR Tomo and as a session is two datasets."""

    harness = BridgeHarness(tmp_path)
    path    = str(SESSIONS / "mono_profile.hd5")

    assert harness.workspace.import_folder("hd5", path) != harness.workspace.import_folder("session", path)
    assert harness.workspace.import_folder("session", path).name.startswith("mono_profile_session_")


def test_a_stem_with_odd_characters_is_made_safe(tmp_path):
    """Characters outside [A-Za-z0-9._-] in the stem become underscores in the folder name."""

    harness = BridgeHarness(tmp_path)
    source  = FixtureCopies(tmp_path / "user").copy(INPUTS / "npy_real.npy", "my cube (v2).npy")
    record  = harness.imported("npy", source)

    assert re.fullmatch(r"my_cube__v2__npy_[0-9a-f]{8}", Path(record.id).name)
