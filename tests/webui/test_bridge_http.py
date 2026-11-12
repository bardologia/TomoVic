"""Tests of the bridge over real HTTP: TomoVis imports seen by the watch, the hand-over, and the workspace routes.

A threaded console serves the TomoVis, workspace and cube routers. The client
sends exactly what the pages send: menu triggers and file dialog answers for
TomoVis, and the workspace and cube requests of the TomoVic pages.
"""

from __future__ import annotations

import pytest

from tests.webui.bridge_fixtures  import INPUTS, SESSIONS, BridgeHarness, BridgeServer, FixtureCopies
from tests.webui.preproc_fixtures import make_preproc_run

from bridge.import_watch import TomoVisImportWatch

DATASET_KEYS = ["id", "registered", "name", "origin", "origin_label", "source", "folder", "revision", "state", "stage", "progress", "error", "footprint", "cube", "tomogram", "channel", "pieces", "tools", "tomovis"]
PIECE_KEYS   = ["label", "present", "value", "origin", "addable", "launch", "problem", "note"]
TOOL_KEYS    = ["label", "ready", "missing", "actionable", "note"]
PIECES       = ["tomogram", "channel", "height_range", "primary", "spacing", "dem", "geometry", "passes", "polarimetry", "params"]
TOOLS        = ["cube", "slices", "cube_dem", "cube_metric", "cube_globe", "cube_passes", "cube_pauli", "cube_param", "extract_params", "extract_polarimetry", "analyze_preprocessing", "analyze_param_extraction", "compare_preprocessing_trials", "tomovis", "tomovis_metres", "tomovis_scripts"]


@pytest.fixture
def served(tmp_path):
    """A bridge console on a free port, closed after the test."""

    server = BridgeServer(BridgeHarness(tmp_path))
    try:
        yield server
    finally:
        server.close()


def assert_dataset_shape(dataset: dict) -> None:
    """Checks a Dataset payload has exactly the keys of the design's section 5.4 (plus a note per piece)."""

    assert list(dataset) == DATASET_KEYS
    assert list(dataset["pieces"]) == PIECES and list(dataset["tools"]) == TOOLS
    assert all(list(piece) == PIECE_KEYS for piece in dataset["pieces"].values())
    assert all(list(tool) == TOOL_KEYS for tool in dataset["tools"].values())
    assert list(dataset["tomovis"]) == ["link", "scripts_link", "revision", "ready", "scripts_ready"]


def test_a_manual_import_registers_with_the_window(served):
    """File > Import > npy registers the file in the same request: current set by TomoVis, the window holds it."""

    client = served.client
    sid    = client.window()
    client.load(sid, "openNpy", INPUTS / "npy_real.npy")
    state  = client.current(sid)

    assert state["set_by"] == "tomovis" and state["serial"] == 1
    assert state["current"]["name"] == "npy_real.npy"
    assert state["tomovis"] == {"held": {"id": state["current"]["id"], "name": "npy_real.npy", "tomovis_revision": 0}, "open": False}


def test_cancels_and_failures_do_not_register(served, tmp_path):
    """A cancelled dialog, a failed import ('Import error') and a failed session open ('Open error') leave the bridge untouched."""

    client = served.client
    sid    = client.window()

    request = client.trigger(sid, "openNpy")
    client.event(sid, {"type": "dialog_result", "token": request["token"], "accepted": False})

    broken = tmp_path / "broken.npy"
    broken.write_bytes(b"not an npy file")
    failed = client.load(sid, "openNpy", broken)
    assert failed["dialogs"][0]["title"] == "Import error"

    opened = client.load(sid, "openFile", INPUTS / "fusar_two_key_elev.hd5")
    assert opened["dialogs"][0]["title"] == "Open error"

    assert client.current(sid) == {"ok": True, "workspace": str(served.harness.root.resolve()), "serial": 0, "set_by": None, "current": None, "bridge_error": "", "tomovis": {"held": None, "open": False}}


def test_a_failed_import_after_a_good_one_keeps_the_dataset(served, tmp_path):
    """An 'Import error' after a successful import keeps TomoVis's previous cube and the bridge's current dataset."""

    client = served.client
    sid    = client.window()
    client.load(sid, "openNpy", INPUTS / "npy_real.npy")
    served.harness.settle()
    before = client.current(sid)

    missing = tmp_path / "gone.npy"
    client.load(sid, "openNpy", missing)

    assert client.current(sid) == before


def test_every_import_kind_registers(served):
    """hd5, h5, rat, npy and a session each register with their own origin label."""

    client = served.client
    sid    = client.window()
    cases  = [("openFUSAR", INPUTS / "fusar_two_key_elev.hd5", "TomoVis import · hd5"), ("openUAVSAR", INPUTS / "uavsar_three_keys.h5", "TomoVis import · h5"), ("openRAT", INPUTS / "rat_complex.rat", "TomoVis import · rat"), ("openNpy", INPUTS / "npy_channels_3.npy", "TomoVis import · npy"), ("openFile", SESSIONS / "mono_profile.hd5", "TomoVis session")]

    for action, path, label in cases:
        client.load(sid, action, path)
        assert client.current(sid)["current"]["origin_label"] == label

    assert len(client.datasets()["datasets"]) == len(cases)


def test_the_hand_over_keeps_current_and_updates_held(served):
    """trigger openFUSAR, then dialog_result with the current dataset's link: TomoVis shows its heights and spacing, and the window now holds it."""

    client = served.client
    other  = client.window()
    client.load(other, "openFUSAR", INPUTS / "fusar_two_key_elev.hd5")
    served.harness.settle()
    dataset = client.current()["current"]
    client.use(dataset["id"])

    sid = client.window()
    assert client.current(sid)["tomovis"] == {"held": None, "open": True}

    request = client.trigger(sid, "openFUSAR")
    answer  = client.event(sid, {"type": "dialog_result", "token": request["token"], "accepted": True, "path": dataset["tomovis"]["link"]})
    state   = client.current(sid)
    attrs   = answer["snapshot"]["attributes"]

    assert answer["dialogs"] == []
    assert attrs["z_range"] == [-10.0, 30.0] and (attrs["x_res"], attrs["y_res"]) == (0.5, 0.75)
    assert (state["current"]["id"], state["set_by"], state["serial"]) == (dataset["id"], "tomovic", 2)
    assert state["tomovis"] == {"held": {"id": dataset["id"], "name": "fusar_two_key_elev.hd5", "tomovis_revision": 0}, "open": False}
    assert len(client.datasets()["datasets"]) == 1


def test_the_full_loop_with_a_run(served, tmp_path):
    """Import, load in Cube, then a TomoVic run made current: the window must open it, the link import follows, and open turns false."""

    client = served.client
    sid    = client.window()
    client.load(sid, "openFUSAR", INPUTS / "fusar_two_key_elev.hd5")
    served.harness.settle()
    imported = client.current(sid)["current"]

    assert imported["tools"]["cube"]["ready"]
    assert client.load_cube(imported["id"])["state"] == "ready"

    run_dir = make_preproc_run(tmp_path / "runs", with_spacing=True)
    assert client.request("GET", f"/api/cubes?base={tmp_path / 'runs'}")[0] == 200
    status, answer = client.use(str(run_dir))
    assert status == 200 and answer["set_by"] == "tomovic"
    assert client.current(sid)["tomovis"]["open"]

    request  = client.trigger(sid, "openFUSAR")
    attrs    = client.event(sid, {"type": "dialog_result", "token": request["token"], "accepted": True, "path": answer["current"]["tomovis"]["link"]})["snapshot"]["attributes"]
    state    = client.current(sid)

    assert attrs["data_shape"] == answer["current"]["tomogram"]["shape"]
    assert attrs["z_range"] == [-10.0, 30.0] and (attrs["x_res"], attrs["y_res"]) == (0.4, 0.6)
    assert state["tomovis"]["held"]["id"] == str(run_dir.resolve()) and not state["tomovis"]["open"]
    assert client.load_cube(str(run_dir))["state"] == "ready"


def test_every_route_answers_its_payload(served, tmp_path):
    """GET current, datasets, dataset and POST current answer the keys of the design; errors carry ok false."""

    client = served.client
    sid    = client.window()
    client.load(sid, "openNpy", INPUTS / "npy_channels_3.npy")
    served.harness.settle()

    state = client.current(sid)
    assert list(state) == ["ok", "workspace", "serial", "set_by", "current", "bridge_error", "tomovis"]
    assert_dataset_shape(state["current"])

    listing = client.datasets(str(tmp_path))
    assert list(listing) == ["ok", "current_id", "datasets"]
    assert list(listing["datasets"][0]) == DATASET_KEYS + ["under_base", "strip"]

    status, single = client.dataset(state["current"]["id"])
    assert status == 200 and list(single) == ["ok", "dataset"]
    assert_dataset_shape(single["dataset"])

    status, used = client.use(state["current"]["id"])
    assert status == 200 and list(used) == ["ok", "serial", "set_by", "current"]

    assert client.dataset(str(tmp_path / "nothing")) == (404, {"ok": False, "error": f"unknown dataset: {tmp_path / 'nothing'}"})
    assert client.use(str(tmp_path / "nothing"))[0] == 400
    assert client.request("POST", "/api/workspace/current", {"name": "x"})[0] == 400
    assert client.request("POST", "/api/workspace/current", {"id": 3})[0] == 400


def test_the_filter_kinds_match_real_trigger_answers(served):
    """Every name filter the watch maps is the one TomoVis's real file request carries, in open mode."""

    client  = served.client
    sid     = client.window()
    actions = {"openFUSAR": "hd5", "openUAVSAR": "h5", "openNpy": "npy", "openRAT": "rat", "openFile": "session"}

    for action, kind in actions.items():
        request = client.trigger(sid, action)
        assert request["mode"] == "open"
        assert TomoVisImportWatch.FILTER_KINDS[request["filters"][0]] == kind
        client.event(sid, {"type": "dialog_result", "token": request["token"], "accepted": False})

    assert sorted(TomoVisImportWatch.FILTER_KINDS.values()) == sorted(actions.values())


def test_a_registration_error_leaves_the_tomovis_answer_intact(served, monkeypatch):
    """When registering fails, TomoVis still answers 200 with its cube and GET current reports bridge_error; the next success clears it."""

    client = served.client
    sid    = client.window()

    def failing(sid, kind, path):
        raise OSError("disk full")

    monkeypatch.setattr(served.harness.bridge, "tomovis_imported", failing)
    answer = client.load(sid, "openNpy", INPUTS / "npy_real.npy")

    assert answer["snapshot"]["attributes"]["data_shape"] == [16, 32, 24]
    assert client.current(sid)["bridge_error"] == "TomoVis opened npy_real.npy, but the TomoVic tools could not take it: disk full"

    monkeypatch.undo()
    client.load(sid, "openNpy", INPUTS / "npy_real.npy")
    assert client.current(sid)["bridge_error"] == ""


def test_a_deleted_import_source_gives_tomovis_its_own_import_error(served, tmp_path):
    """A hand-over of an import whose user file was deleted shows TomoVis's 'Import error' and keeps the window's cube."""

    client = served.client
    source = FixtureCopies(tmp_path / "user").copy(INPUTS / "npy_real.npy")
    sid    = client.window()
    client.load(sid, "openNpy", source)
    served.harness.settle()
    dataset = client.current()["current"]
    client.load(sid, "openNpy", INPUTS / "npy_float64.npy")

    source.unlink()
    request = client.trigger(sid, "openFUSAR")
    answer  = client.event(sid, {"type": "dialog_result", "token": request["token"], "accepted": True, "path": dataset["tomovis"]["link"]})

    assert answer["dialogs"][0]["title"] == "Import error"
    assert answer["snapshot"]["attributes"]["data_shape"] == [8, 12, 10]
    assert not client.dataset(dataset["id"])[1]["dataset"]["tomovis"]["ready"]


def test_the_full_loop_with_an_added_height_range(served, tmp_path):
    """Import npy_real, add its height range, load it in Cube; then a run made current is handed to the window, after which open is false."""

    client = served.client
    sid    = client.window()
    client.load(sid, "openNpy", INPUTS / "npy_real.npy")
    served.harness.settle()
    imported = client.current(sid)["current"]
    assert imported["tools"]["cube"]["missing"] == ["height_range"]

    status, added = client.add(imported["id"], "height_range", {"low": -20, "high": 80})
    assert status == 200 and added["ok"] and added["dataset"]["tools"]["cube"]["ready"]
    assert client.load_cube(imported["id"])["state"] == "ready"
    assert client.current(sid)["tomovis"]["open"]

    request = client.trigger(sid, "openFUSAR")
    attrs   = client.event(sid, {"type": "dialog_result", "token": request["token"], "accepted": True, "path": added["dataset"]["tomovis"]["link"]})["snapshot"]["attributes"]
    assert attrs["z_range"] == [-20.0, 80.0]
    assert not client.current(sid)["tomovis"]["open"]

    run_dir = make_preproc_run(tmp_path / "runs", with_spacing=True)
    client.request("GET", f"/api/cubes?base={tmp_path / 'runs'}")
    status, used = client.use(str(run_dir))
    assert status == 200 and client.current(sid)["tomovis"]["open"]

    request = client.trigger(sid, "openFUSAR")
    client.event(sid, {"type": "dialog_result", "token": request["token"], "accepted": True, "path": used["current"]["tomovis"]["link"]})
    state = client.current(sid)
    assert state["tomovis"]["held"]["id"] == str(run_dir.resolve()) and not state["tomovis"]["open"]


def test_the_add_route_answers(served, tmp_path):
    """POST add: 200 with the dataset, 400 with the piece for a refused piece or a run, 404 for an unknown id, 400 for a malformed body."""

    client = served.client
    sid    = client.window()
    client.load(sid, "openNpy", INPUTS / "npy_real.npy")
    served.harness.settle()
    dataset_id = client.current()["current"]["id"]

    status, answer = client.add(dataset_id, "spacing", {"azimuth": 0.5, "range": 0.75})
    assert status == 200 and list(answer) == ["ok", "dataset"] and answer["dataset"]["pieces"]["spacing"]["value"] == [0.5, 0.75]

    assert client.add(dataset_id, "height_range", {"low": 3, "high": 1}) == (400, {"ok": False, "error": "The lower height must be below the upper height.", "piece": "height_range"})
    assert client.add(str(tmp_path / "x"), "dem", {"path": "/a.npy"}) == (404, {"ok": False, "error": f"unknown dataset: {tmp_path / 'x'}", "piece": "dem"})
    assert client.request("POST", "/api/workspace/add", {"id": dataset_id})[0] == 400

    run_dir = make_preproc_run(tmp_path / "runs")
    client.request("GET", f"/api/cubes?base={tmp_path / 'runs'}")
    assert client.add(str(run_dir), "dem", {"path": "/a.npy"}) == (400, {"ok": False, "error": "run_a is a TomoVic run; the bridge never writes into run folders.", "piece": "dem"})
