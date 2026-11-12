"""Tests of the /api/tomovis routes over real HTTP.

A threaded HTTP server with the console's request handler and a router
holding only the TomoVis sub-router serves every route once or more: page
sessions and their LRU, window events with the TVE1 envelope, figure
operations, tables, the 3D volume, metadata, directory listings, written
exports, HDF5 export, browser log lines and both scripts, plus the 400, 404
and 409 answers.
"""

from __future__ import annotations

import io
import json
import struct
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

import h5py
import numpy as np
import pytest
from PIL import Image

from bridge.dataset_bridge    import DatasetBridge
from bridge.dataset_workspace import DatasetWorkspace
from bridge.import_watch      import TomoVisImportWatch
from cube_explorer            import CubeExplorer, SliceCollector
from request_router           import RequestRouter
from routers.tomovis_router   import TomoVisRouter
from tests.webui.conftest     import REPO_ROOT
from tomovis.envelope         import TomoVisEnvelope
from tomovis.session_store    import TomoVisSessions
from web_logger               import WebLogger
from web_ui_server            import _Handler

INPUTS = REPO_ROOT / "tests" / "webui" / "fixtures" / "tomovis" / "inputs"


class TomoVisClient:
    """HTTP client of a test server.

    Attributes:
        base     : Base URL of the API.
        envelope : Envelope decoder.
    """

    def __init__(self, port: int) -> None:
        """Points the client at the server."""

        self.base     = f"http://127.0.0.1:{port}/api/tomovis/"
        self.envelope = TomoVisEnvelope()

    def request(self, method: str, path: str, body: bytes | None = None, content_type: str = "application/json") -> tuple[int, bytes]:
        """Sends one request and returns (status, body) for any status."""

        request = urllib.request.Request(self.base + path, data=body, method=method, headers={"Content-Type": content_type} if body is not None else {})
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                return response.status, response.read()
        except urllib.error.HTTPError as error:
            return error.code, error.read()

    def post(self, path: str, payload: dict) -> tuple[int, bytes]:
        """POSTs JSON."""

        return self.request("POST", path, json.dumps(payload).encode())

    def unpack(self, raw: bytes) -> tuple[dict, dict]:
        """Decodes an envelope."""

        return self.envelope.unpack(raw)

    def session(self, kind: str = "window") -> str:
        """Opens a session and returns its id."""

        status, raw = self.post("session", {"kind": kind, "webgl2": True})
        assert status == 200
        return self.unpack(raw)[0]["sid"]

    def event(self, sid: str, event: dict) -> tuple[dict, dict]:
        """Sends a window event and decodes the answer."""

        status, raw = self.post("event", {"sid": sid, "seq": 1, "event": event})
        assert status == 200, raw
        return self.unpack(raw)

    def load(self, sid: str, action: str, path) -> tuple[dict, dict]:
        """Imports one file through the menu and the file dialog."""

        header, _ = self.event(sid, {"type": "trigger", "widget": action})
        return self.event(sid, {"type": "dialog_result", "token": header["dialogs"][0]["token"], "accepted": True, "path": str(path)})


@pytest.fixture
def server(tmp_path):
    """A TomoVis-only console on a free port, its import watch over a bridge in a temporary workspace, shut down after the test."""

    logger   = WebLogger("tomovis-test")
    sessions = TomoVisSessions(logger)
    cubes    = CubeExplorer(logger)
    bridge   = DatasetBridge(DatasetWorkspace(tmp_path / "workspace", cubes.roots, logger), cubes, SliceCollector(cubes, logger), logger)
    httpd    = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    bridge.start()
    httpd.router = RequestRouter(logger, [TomoVisRouter(sessions, TomoVisImportWatch(bridge, logger), logger)])
    worker   = threading.Thread(target=httpd.serve_forever, daemon=True)
    worker.start()
    try:
        yield TomoVisClient(httpd.server_address[1]), logger, sessions
    finally:
        httpd.shutdown()
        httpd.server_close()


def test_session_event_and_envelope_layout(server):
    """An import answers with an aligned TVE1 envelope carrying the two view images and the snapshot."""

    client, _, _ = server
    sid          = client.session()
    header, _    = client.event(sid, {"type": "trigger", "widget": "openNpy"})
    request      = header["dialogs"][0]

    assert (request["kind"], request["title"], request["filters"]) == ("file", "Open File", ["Numpy (*.npy)"])

    status, raw = client.post("event", {"sid": sid, "seq": 7, "event": {"type": "dialog_result", "token": request["token"], "accepted": True, "path": str(INPUTS / "npy_real.npy")}})
    length      = struct.unpack("<I", raw[4:8])[0]
    header, blobs = client.unpack(raw)

    assert status == 200 and raw[:4] == b"TVE1"
    assert all(entry["offset"] % 8 == 0 for entry in header["blobs"])
    assert header["blobs"][0]["offset"] == 8 + length + (-(8 + length) % 8)
    assert header["seq"] == 7
    assert header["views"] == {"imv1_1": "view:imv1_1", "imv2_1": "view:imv2_1"}
    assert blobs["view:imv1_1"].shape == (32, 24) and blobs["view:imv1_1"].dtype == np.float32
    assert header["snapshot"]["controls"]["tab1Slider"]["maximum"] == 23
    assert header["slot_errors"] == [] and header["printed"] == []


def test_event_errors(server):
    """Unknown session 404, invalid events 400, stale dialog token 409."""

    client, _, _ = server
    sid          = client.session()

    assert client.post("event", {"sid": "nope", "seq": 1, "event": {"type": "sync"}})[0] == 404
    assert client.post("event", {"sid": sid, "seq": 1, "event": {"type": "explode"}})[0] == 400
    assert client.post("event", {"sid": sid, "seq": 1, "event": {"type": "click", "widget": "colormapTab4Button"}})[0] == 400
    assert client.post("event", {"sid": sid, "seq": 1, "event": {"type": "value", "widget": "tab1Slider", "value": "x"}})[0] == 400
    assert client.post("event", {"sid": sid, "seq": 1, "event": {"type": "dialog_result", "token": "stale", "accepted": True}})[0] == 409
    assert client.post("session", {"kind": "other"})[0] == 400
    assert client.request("POST", "event", b"[1, 2]")[0] == 400


def test_sync_resends_every_current_image(server):
    """A sync event answers with every image the window shows, for a browser that lost them."""

    client, _, _ = server
    sid          = client.session()
    client.load(sid, "openNpy", INPUTS / "npy_real.npy")
    header, blobs = client.event(sid, {"type": "sync"})

    assert sorted(header["views"]) == ["imv1_1", "imv2_1"]
    assert sorted(blobs) == ["view:imv1_1", "view:imv2_1"]


def test_figure_operations_and_frames(server):
    """Resize answers with a full PNG frame of the requested size; unknown figures 404, bad ops 400."""

    client, _, _ = server
    sid          = client.session()
    client.load(sid, "openNpy", INPUTS / "npy_real.npy")
    client.event(sid, {"type": "click", "widget": "tab1PlotButton"})

    status, raw    = client.post("figure", {"sid": sid, "seq": 2, "figure": "plot", "op": "resize", "width": 600, "height": 400, "dpr": 1})
    header, blobs  = client.unpack(raw)
    frame          = next(message["blob"] for message in header["messages"] if message["type"] == "frame")

    assert status == 200 and header["figure"] == "plot"
    assert Image.open(io.BytesIO(blobs[frame])).size == (600, 400)
    assert client.post("figure", {"sid": sid, "figure": "nothing", "op": "refresh"})[0] == 404
    assert client.post("figure", {"sid": sid, "figure": "plot", "op": "explode"})[0] == 400
    assert client.post("figure", {"sid": sid, "figure": "plot", "op": "resize", "width": 0, "height": 1, "dpr": 1})[0] == 400

    status, raw = client.post("figure", {"sid": sid, "figure": "plot", "op": "save_start"})

    assert client.unpack(raw)[0]["result"]["file"] == "image.png"


def test_matplotlib_window_export(server):
    """export_matplotlib draws the curves into a new export figure."""

    client, _, _ = server
    sid          = client.session()
    plot         = {"curves": [{"x": [0, 1, 2], "y": [1, 3, 2], "pen": {"color": [1, 1, 1, 1], "width": 1, "style": "solid"}, "symbol": None, "symbolSize": 10, "symbolPen": [0.8, 0.8, 0.8, 1], "symbolBrush": [0.4, 0.4, 0.4, 1]}], "xlabel": "x", "ylabel": "y", "title": "", "xrange": [0, 2], "yrange": [1, 3]}

    status, raw = client.post("figure", {"sid": sid, "figure": "export:1", "op": "export_matplotlib", "plot": plot})
    header, blobs = client.unpack(raw)

    assert status == 200 and header["figure"] == "export:1"
    assert any(message["type"] == "frame" for message in header["messages"])


def test_matplotlib_windows_are_independent_and_close(server):
    """Each export opens its own figure, as pyqtgraph opened a new MatplotlibWindow; closing one drops only that figure."""

    client, _, _ = server
    sid          = client.session()
    plot         = {"curves": [{"x": [0, 1], "y": [0, 1], "pen": {"color": [1, 1, 1, 1], "width": 1, "style": "solid"}}], "xrange": [0, 1], "yrange": [0, 1]}

    assert client.post("figure", {"sid": sid, "figure": "export:1", "op": "export_matplotlib", "plot": plot})[0] == 200
    assert client.post("figure", {"sid": sid, "figure": "export:2", "op": "export_matplotlib", "plot": plot})[0] == 200
    assert client.post("figure", {"sid": sid, "figure": "export:1", "op": "export_close"})[0] == 200
    assert client.post("figure", {"sid": sid, "figure": "export:1", "op": "refresh"})[0] == 404
    assert client.post("figure", {"sid": sid, "figure": "export:2", "op": "refresh"})[0] == 200
    assert client.post("figure", {"sid": sid, "figure": "export", "op": "export_matplotlib", "plot": plot})[0] == 404
    assert client.post("figure", {"sid": sid, "figure": "plot", "op": "export_close"})[0] == 400


def test_tables_metadata_and_volume(server):
    """Tables list 19 colour tables and 71 colour maps; metadata is getCurrentMetadata; the 3D tab prepares the volume."""

    client, _, _ = server
    tables       = json.loads(client.request("GET", "tables")[1])

    assert len(tables["colortables"]["names"]) == 19 and len(tables["colortables"]["tables"][9]) == 256
    assert tables["plot_colormaps"]["names"][65] == "jet"

    sid = client.session()
    client.load(sid, "openFUSAR", INPUTS / "fusar_two_key_elev.hd5")
    metadata = json.loads(client.request("GET", f"metadata?sid={sid}")[1])

    assert metadata["app_name"] == "TomoVis" and metadata["x_res"] == 0.5

    header, _ = client.event(sid, {"type": "tab", "index": 3})
    volume    = header["snapshot"]["volume"]

    assert volume == {"serial": 1, "rendered": True, "shape": [2, 4, 12]}
    assert header["snapshot"]["controls"]["isoThresholdTab4Slider"] == {"enabled": True, "minimum": 1, "maximum": 100, "value": 1}

    status, raw    = client.request("GET", f"volume?sid={sid}&serial=1")
    vheader, blobs = client.unpack(raw)

    assert status == 200 and vheader["shape"] == [2, 4, 12]
    assert blobs["volume"].dtype == np.float32
    assert client.request("GET", f"volume?sid={sid}&serial=5")[0] == 404
    assert client.request("GET", "metadata?sid=missing")[0] == 404


def test_directory_listing(server, tmp_path):
    """Folders first, then files matching the filter case-insensitively; hidden entries and other files left out."""

    client, _, _ = server
    for name in ("b.NPY", "a.npy", ".hidden.npy", "c.txt"):
        (tmp_path / name).write_text("x")
    (tmp_path / "sub").mkdir()

    listing = json.loads(client.request("GET", f"fs?path={tmp_path}&pattern=*.npy")[1])

    assert listing["ok"] and listing["parent"] == str(tmp_path.parent)
    assert [(entry["name"], entry["dir"]) for entry in listing["entries"]] == [("sub", True), ("a.npy", False), ("b.NPY", False)]
    assert client.request("GET", "fs?path=relative/path")[0] == 400
    assert json.loads(client.request("GET", "fs")[1])["path"] == listing["home"]


def test_write_route(server, tmp_path):
    """PNG is written as sent, JPEG re-encoded, raw bytes as is; unknown extensions and relative paths are refused."""

    client, _, _ = server
    sid          = client.session()
    png          = io.BytesIO()
    Image.new("RGBA", (64, 48), (255, 0, 0, 255)).save(png, format="png")

    assert client.request("POST", f"write?sid={sid}&path={tmp_path}/a.png&kind=image", png.getvalue(), "image/png")[0] == 200
    assert client.request("POST", f"write?sid={sid}&path={tmp_path}/a.jpg&kind=image", png.getvalue(), "image/png")[0] == 200
    assert client.request("POST", f"write?sid={sid}&path={tmp_path}/a.csv&kind=bytes", b"x,y\n1,2\n", "application/octet-stream")[0] == 200
    assert client.request("POST", f"write?sid={sid}&path={tmp_path}/a.xyz&kind=image", png.getvalue(), "image/png")[0] == 400
    assert client.request("POST", f"write?sid={sid}&path=rel.png&kind=image", png.getvalue(), "image/png")[0] == 400

    assert (tmp_path / "a.png").read_bytes() == png.getvalue()
    assert Image.open(tmp_path / "a.jpg").format == "JPEG"
    assert (tmp_path / "a.csv").read_text() == "x,y\n1,2\n"


def test_hdf5_export(server, tmp_path):
    """Equal-length curves become one dataset in the column mode; ragged curves a group of datasets."""

    client, _, _ = server
    sid          = client.session()
    curves       = [{"x": [0, 1, 2], "y": [3, 4, 5]}, {"x": [0, 1, 2], "y": [6, 7, 8]}]

    assert client.post("export_hdf5", {"sid": sid, "path": str(tmp_path / "p.h5"), "name": "Export", "column_mode": "(x,y) per plot", "curves": curves})[0] == 200
    assert client.post("export_hdf5", {"sid": sid, "path": str(tmp_path / "p.h5"), "name": "All", "column_mode": "(x,y,y,y) for all plots", "curves": curves})[0] == 200
    assert client.post("export_hdf5", {"sid": sid, "path": str(tmp_path / "p.h5"), "name": "Ragged", "column_mode": "(x,y) per plot", "curves": [curves[0], {"x": [0], "y": [1]}]})[0] == 200
    assert client.post("export_hdf5", {"sid": sid, "path": str(tmp_path / "p.h5"), "name": "X", "column_mode": "bad", "curves": curves})[0] == 400

    with h5py.File(tmp_path / "p.h5", "r") as h5f:
        assert h5f["Export"].shape == (4, 3)
        assert h5f["All"][:].tolist() == [[0, 1, 2], [3, 4, 5], [6, 7, 8]]
        assert sorted(h5f["Ragged"].keys()) == ["0", "1"]


def test_log_lines_reach_the_console_log(server):
    """Browser prints are logged with the TomoVis prefix."""

    client, logger, _ = server
    sid               = client.session()

    assert client.post("log", {"sid": sid, "lines": ["Camera: fly"]})[0] == 200
    assert any(record["message"] == "TomoVis: Camera: fly" for record in logger.recent())
    assert client.post("log", {"sid": sid, "lines": "no"})[0] == 400


def test_log_lines_keep_vispy_error_levels(server):
    """Browser lines carrying vispy's "ERROR:" or "WARNING:" level, the multi-line traceback entry included, are logged at that level, others at info (D-7, F-153)."""

    client, logger, _ = server
    sid               = client.session()
    traceback         = "WARNING: Traceback (most recent call last):\n  at VispyFlyCamera.onTimer (tomovis_vispy.js:1:1)\nTypeError: x"
    lines             = [traceback, "ERROR: Invoking FlyCamera.on_timer for Event", "ERROR: Invoking FlyCamera.on_timer repeat 2", "WARNING: y", "ISO threshold: 2.0", "Camera: ERROR"]

    assert client.post("log", {"sid": sid, "lines": lines})[0] == 200
    levels = {record["message"]: record["level"] for record in logger.recent()}
    assert [levels["TomoVis: " + line] for line in lines] == ["WARN", "ERROR", "ERROR", "WARN", "INFO", "INFO"]


def test_scripts_routes(server):
    """SlicerMatplotlib answers with its figure frames; VolumeRendering with both volumes and its prints."""

    client, _, _ = server
    sid          = client.session("scripts")

    status, raw   = client.post("script/slicer", {"sid": sid, "path": str(INPUTS / "fusar_one_key_range.hd5")})
    header, blobs = client.unpack(raw)

    assert status == 200 and header["figure"] == "script_slicer" and any(name.startswith("figure:script_slicer:") for name in blobs)
    assert client.post("script/slicer", {"sid": sid, "path": str(INPUTS / "fusar_no_attrs.hd5")})[0] == 400

    status, raw   = client.request("GET", f"script/volume?sid={sid}&path={INPUTS / 'fusar_two_key_elev.hd5'}")
    header, blobs = client.unpack(raw)

    assert status == 200 and header["shape"] == [16, 32, 24]
    assert blobs["volume_1"].shape == (16, 32, 24) and set(np.unique(blobs["volume_2"])) <= {0.0, 1.0}
    assert header["printed"][0] == "HDF5 keys: ['theta', 'tomogram']"
    assert client.post("script/slicer", {"sid": client.session(), "path": "x"})[0] == 400


def test_close_and_least_recently_used_eviction(server):
    """Closing drops a session; a fifth session drops the least recently used one."""

    client, _, _ = server
    first        = client.session()
    others       = [client.session() for _ in range(3)]

    assert client.post("event", {"sid": first, "seq": 1, "event": {"type": "sync"}})[0] == 200

    client.session()

    assert client.post("event", {"sid": others[0], "seq": 1, "event": {"type": "sync"}})[0] == 404
    assert client.post("event", {"sid": first, "seq": 1, "event": {"type": "sync"}})[0] == 200
    assert client.post("close", {"sid": first})[0] == 200
    assert client.post("event", {"sid": first, "seq": 1, "event": {"type": "sync"}})[0] == 404
    assert client.post("close", {"sid": "unknown"})[0] == 200
