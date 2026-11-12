"""Tests of the current dataset: its persistence, serial and setter, the TomoVis open rule, run registration and listings."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from tests.webui.bridge_fixtures  import INPUTS, BridgeHarness
from tests.webui.preproc_fixtures import make_preproc_run

from bridge.dataset_bridge import BridgeRefusal


def test_nothing_is_written_before_the_first_registration(tmp_path):
    """A started bridge leaves the disk alone until a dataset is registered or the current dataset is set."""

    harness = BridgeHarness(tmp_path)

    assert not harness.root.exists()
    assert harness.bridge.current_payload(None) == {"ok": True, "workspace": str(harness.root.resolve()), "serial": 0, "set_by": None, "current": None, "bridge_error": ""}


def test_the_current_pointer_persists_across_a_new_bridge(tmp_path):
    """current.json carries id, serial and setter to the next console on the same workspace, with a README written once."""

    first  = BridgeHarness(tmp_path)
    record = first.imported("npy", INPUTS / "npy_real.npy")
    second = BridgeHarness(tmp_path)

    assert second.bridge.current == {"id": record.id, "serial": 1, "set_by": "tomovis"}
    assert json.loads((first.root / "current.json").read_text()) == {"id": record.id, "serial": 1, "set_by": "tomovis"}
    assert (first.root / "README.txt").read_text().startswith("TomoVic workspace\n")
    assert second.dataset(record.id)["revision"] == record.revision


def test_serial_and_setter(tmp_path):
    """The serial rises only when the id or the setter changes; use() always sets 'tomovic'."""

    harness = BridgeHarness(tmp_path)
    record  = harness.imported("npy", INPUTS / "npy_real.npy")

    assert harness.bridge.current["serial"] == 1 and harness.bridge.current["set_by"] == "tomovis"

    harness.imported("npy", INPUTS / "npy_real.npy", sid="window-b")
    assert harness.bridge.current["serial"] == 1

    answer = harness.bridge.use(record.id)
    assert (answer["serial"], answer["set_by"], answer["current"]["id"]) == (2, "tomovic", record.id)
    assert harness.bridge.use(record.id)["serial"] == 2

    other = harness.imported("hd5", INPUTS / "fusar_two_key_elev.hd5")
    assert harness.bridge.current == {"id": other.id, "serial": 3, "set_by": "tomovis"}

    cleared = harness.bridge.use(None)
    assert (cleared["serial"], cleared["set_by"], cleared["current"]) == (4, "tomovic", None)


def test_the_open_rule(tmp_path):
    """open is true only for a ready link set from TomoVic that the window does not already hold at its TomoVis revision."""

    harness = BridgeHarness(tmp_path)
    record  = harness.imported("hd5", INPUTS / "fusar_two_key_elev.hd5", sid="importer")
    bridge  = harness.bridge

    assert not bridge.open_for("fresh")
    assert not bridge.open_for("importer")

    bridge.use(record.id)
    assert bridge.open_for("fresh")
    assert not bridge.open_for("importer")

    bridge.tomovis_imported("fresh", "hd5", bridge.payload(record)["tomovis"]["link"])
    assert not bridge.open_for("fresh")
    assert bridge.current["set_by"] == "tomovic"

    record.tomovis_revision += 1
    assert bridge.open_for("fresh") and bridge.open_for("importer")

    Path(bridge.payload(record)["tomovis"]["link"]).unlink()
    assert not bridge.open_for("fresh")


def test_the_current_payload_reports_the_window(tmp_path):
    """With a sid the payload carries what that window holds and the open flag; an unknown sid holds nothing."""

    harness = BridgeHarness(tmp_path)
    record  = harness.imported("npy", INPUTS / "npy_real.npy", sid="importer")
    payload = harness.bridge.current_payload("importer")

    assert payload["tomovis"] == {"held": {"id": record.id, "name": "npy_real.npy", "tomovis_revision": 0}, "open": False}
    assert harness.bridge.current_payload("nobody")["tomovis"] == {"held": None, "open": False}
    assert "tomovis" not in harness.bridge.current_payload(None)


def test_using_a_run_registers_it(tmp_path):
    """The first use of a run writes its record and link in linked/ (never in the run), and later uses keep one record."""

    harness = BridgeHarness(tmp_path)
    run_dir = make_preproc_run(tmp_path / "runs", with_spacing=True)
    before  = sorted(str(path) for path in run_dir.rglob("*"))
    harness.open_runs_root(tmp_path / "runs")

    answer  = harness.bridge.use(str(run_dir))
    dataset = answer["current"]
    link    = Path(dataset["tomovis"]["link"])

    assert dataset["registered"] and dataset["origin"] == "run" and dataset["origin_label"] == "TomoVic run"
    assert link.parent.parent == harness.root.resolve() / "linked" and link.is_file()
    assert dataset["tomovis"]["ready"] and dataset["tomovis"]["scripts_ready"]
    assert harness.cubes.roots.contains(run_dir.resolve())
    assert sorted(str(path) for path in run_dir.rglob("*")) == before

    harness.bridge.use(str(run_dir))
    assert len(harness.workspace.records) == 1


def test_a_changed_run_tomogram_rewrites_the_link(tmp_path):
    """A use after the run's tomogram changed raises both revisions and writes the link again."""

    harness = BridgeHarness(tmp_path)
    run_dir = make_preproc_run(tmp_path / "runs")
    harness.open_runs_root(tmp_path / "runs")
    harness.bridge.use(str(run_dir))
    record = harness.workspace.record(str(run_dir.resolve()))
    link   = Path(harness.bridge.payload(record)["tomovis"]["link"])
    inode  = link.stat().st_ino

    shutil.copyfile(INPUTS / "npy_real.npy", run_dir / "data" / "tomogram_full.npy")
    harness.bridge.use(str(run_dir))

    assert (record.revision, record.tomovis_revision) == (1, 1)
    assert link.stat().st_ino != inode


@pytest.mark.parametrize("case", ["outside", "not_a_run", "relative"])
def test_ids_the_console_may_not_open_are_refused(tmp_path, case):
    """POST current refuses an id outside the runs roots, a folder that is not a run, and a relative path, with 400."""

    harness = BridgeHarness(tmp_path)
    (tmp_path / "runs" / "empty").mkdir(parents=True)
    harness.open_runs_root(tmp_path / "runs")
    ids      = {"outside": str(tmp_path / "elsewhere"), "not_a_run": str(tmp_path / "runs" / "empty"), "relative": "runs/empty"}
    messages = {
        "outside"   : f"{ids['outside']} is outside the runs folders the console has opened.",
        "not_a_run" : f"{ids['not_a_run']} is not a TomoVic run: it holds no data/dataset.json.",
        "relative"  : "runs/empty is outside the runs folders the console has opened.",
    }

    with pytest.raises(BridgeRefusal) as refusal:
        harness.bridge.use(ids[case])
    assert refusal.value.status == 400 and str(refusal.value) == messages[case]


def test_an_unregistered_run_is_described_without_writing(tmp_path):
    """GET dataset of a run under the roots answers registered: false with no link, and writes nothing; anything else is 404."""

    harness = BridgeHarness(tmp_path)
    run_dir = make_preproc_run(tmp_path / "runs")
    harness.open_runs_root(tmp_path / "runs")
    dataset = harness.dataset(str(run_dir))

    assert not dataset["registered"]
    assert dataset["tomovis"] == {"link": None, "scripts_link": None, "revision": 0, "ready": False, "scripts_ready": False}
    assert dataset["tools"]["cube"]["ready"]
    assert not harness.root.exists()

    with pytest.raises(BridgeRefusal) as refusal:
        harness.bridge.dataset_payload(str(tmp_path / "nowhere"))
    assert refusal.value.status == 404 and str(refusal.value) == f"unknown dataset: {tmp_path / 'nowhere'}"


def test_the_dataset_listing(tmp_path):
    """datasets() lists newest opened first with under_base and the Cube strip entry, imports in group 'workspace'."""

    harness = BridgeHarness(tmp_path)
    run_dir = make_preproc_run(tmp_path / "runs")
    harness.open_runs_root(tmp_path / "runs")
    record  = harness.imported("npy", INPUTS / "npy_real.npy")
    record.opened_at = "2000-01-01T00:00:00"
    harness.bridge.use(str(run_dir))

    listing = harness.bridge.datasets_payload(str(tmp_path / "runs"))
    first, second = listing["datasets"]

    assert listing["current_id"] == str(run_dir.resolve())
    assert (first["id"], first["under_base"], first["strip"]) == (str(run_dir.resolve()), True, {"id": str(run_dir.resolve()), "run": "run_a", "group": "other folders", "stamp": ""})
    assert (second["id"], second["under_base"], second["strip"]) == (record.id, False, {"id": record.id, "run": "npy_real.npy", "group": "workspace", "stamp": ""})
    assert [entry["under_base"] for entry in harness.bridge.datasets_payload("")["datasets"]] == [False, False]


def test_a_vanished_current_dataset_becomes_none_at_start(tmp_path):
    """A current id whose folder was deleted by hand is cleared by the next start, and the folder leaves the lists."""

    first  = BridgeHarness(tmp_path)
    record = first.imported("npy", INPUTS / "npy_real.npy")
    shutil.rmtree(record.id)

    second = BridgeHarness(tmp_path)

    assert second.bridge.current["id"] is None and second.bridge.current["serial"] == 2
    assert second.bridge.datasets_payload("")["datasets"] == []


def test_a_folder_deleted_while_the_console_runs_leaves_the_lists(tmp_path):
    """Deleting or moving a dataset folder while the bridge runs drops it from every answer instead of failing, and clears it as current."""

    harness = BridgeHarness(tmp_path)
    kept    = harness.imported("npy", INPUTS / "npy_real.npy")
    gone    = harness.imported("hd5", INPUTS / "fusar_two_key_elev.hd5")
    run_dir = make_preproc_run(tmp_path / "runs")
    harness.open_runs_root(tmp_path / "runs")
    harness.bridge.use(str(run_dir))
    harness.bridge.use(gone.id)

    shutil.rmtree(gone.id)
    run_dir.rename(tmp_path / "runs" / "moved")

    current = harness.bridge.current_payload(None)
    assert current["current"] is None and current["set_by"] is None
    assert [dataset["id"] for dataset in harness.bridge.datasets_payload("")["datasets"]] == [kept.id]

    with pytest.raises(BridgeRefusal) as refusal:
        harness.bridge.use(gone.id)
    assert refusal.value.status == 400
    assert not Path(gone.id).exists()
