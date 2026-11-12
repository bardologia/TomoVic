"""Builders for the dataset bridge tests (no tests here).

``BridgeHarness`` puts a workspace in a temporary folder and a started
``DatasetBridge`` over a real ``CubeExplorer`` and ``SliceCollector``.
``BridgeServer`` serves the TomoVis, workspace and cube routers over real HTTP,
as the console does, and ``BridgeClient`` drives them the way the pages do.
"""

from __future__ import annotations

import json
import shutil
import struct
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib     import Path

from tests.webui.conftest import REPO_ROOT

from bridge.cube_preparer     import CubePreparer
from bridge.dataset_bridge    import DatasetBridge
from bridge.dataset_record    import DatasetRecord
from bridge.dataset_workspace import DatasetWorkspace
from bridge.import_watch      import TomoVisImportWatch
from cube_explorer            import CubeExplorer, SliceCollector
from request_router           import RequestRouter
from routers.cube_routers     import CubeRouter
from routers.tomovis_router   import TomoVisRouter
from routers.workspace_router import WorkspaceRouter
from tomovis.session_store    import TomoVisSessions
from web_logger               import WebLogger
from web_ui_server            import _Handler

FIXTURES = REPO_ROOT / "tests" / "webui" / "fixtures" / "tomovis"
INPUTS   = FIXTURES / "inputs"
SESSIONS = FIXTURES / "sessions"


class BridgeHarness:
    """A workspace in a temporary folder and a bridge over a real cube explorer and slice collector.

    Attributes:
        root      : Workspace folder.
        logger    : Logger of every component.
        cubes     : Cube explorer.
        slices    : Slice collector.
        workspace : Workspace.
        bridge    : Dataset bridge.
    """

    def __init__(self, tmp_path: Path, start: bool = True, root: Path | None = None) -> None:
        """Builds the components and, unless told otherwise, starts the bridge.

        Args:
            tmp_path : Test folder.
            start    : Whether ``bridge.start`` runs now.
            root     : Workspace folder; ``<tmp_path>/workspace`` when None.
        """

        self.root      = tmp_path / "workspace" if root is None else root
        self.logger    = WebLogger("bridge-test")
        self.cubes     = CubeExplorer(self.logger)
        self.slices    = SliceCollector(self.cubes, self.logger)
        self.workspace = DatasetWorkspace(self.root, self.cubes.roots, self.logger)
        self.bridge    = DatasetBridge(self.workspace, self.cubes, self.slices, self.logger)
        if start:
            self.bridge.start()

    def imported(self, kind: str, path: Path, sid: str = "window-a") -> DatasetRecord:
        """Reports a successful TomoVis import and waits for its preparation.

        Args:
            kind : Import kind.
            path : Imported file.
            sid  : TomoVis window session id.

        Returns:
            The dataset's record.
        """

        self.bridge.tomovis_imported(sid, kind, str(path))
        self.settle()
        return self.workspace.record(self.bridge.current["id"])

    def settle(self) -> None:
        """Waits up to 30 s until the preparer has no queued or running job."""

        deadline = time.monotonic() + 30.0
        while self.bridge.preparer.jobs.unfinished_tasks:
            assert time.monotonic() < deadline, "the preparations did not end within 30 s"
            time.sleep(0.02)

    def dataset(self, dataset_id: str) -> dict:
        """Returns the Dataset payload of an id."""

        return self.bridge.dataset_payload(dataset_id)["dataset"]

    def open_runs_root(self, base: Path) -> None:
        """Opens a runs root as the Results tab does."""

        assert self.cubes.list_cubes(str(base))["ok"]


class StalledPreparer(CubePreparer):
    """A preparer whose worker never starts, so registrations stay in state "preparing"."""

    def start(self) -> None:
        """Leaves the queue unserved."""

        return


class BridgeClient:
    """HTTP client of a bridge test server, sending what the pages send.

    Attributes:
        base : Server URL.
        seq  : Window event sequence number.
    """

    def __init__(self, port: int) -> None:
        """Points the client at the server."""

        self.base = f"http://127.0.0.1:{port}"
        self.seq  = 0

    def request(self, method: str, path: str, body: dict | None = None) -> tuple[int, dict]:
        """Sends a request; answers JSON as a dict and a TVE1 envelope as its header."""

        data    = None if body is None else json.dumps(body).encode()
        headers = {"Content-Type": "application/json"} if body is not None else {}
        req     = urllib.request.Request(self.base + path, data=data, method=method, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=60) as response:
                status, raw = response.status, response.read()
        except urllib.error.HTTPError as error:
            status, raw = error.code, error.read()

        if raw[:4] == b"TVE1":
            length = struct.unpack("<I", raw[4:8])[0]
            return status, json.loads(raw[8:8 + length])
        return status, json.loads(raw)

    def window(self) -> str:
        """Opens a TomoVis window session and returns its id."""

        return self.request("POST", "/api/tomovis/session", {"kind": "window", "webgl2": True})[1]["sid"]

    def event(self, sid: str, event: dict) -> dict:
        """Sends one window event and returns the answer header."""

        self.seq += 1
        status, header = self.request("POST", "/api/tomovis/event", {"sid": sid, "seq": self.seq, "event": event})
        assert status == 200, (status, header)
        return header

    def trigger(self, sid: str, action: str) -> dict:
        """Clicks a File menu action and returns its file request."""

        return self.event(sid, {"type": "trigger", "widget": action})["dialogs"][0]

    def load(self, sid: str, action: str, path) -> dict:
        """Imports a file through the menu and the file dialog, as a user does."""

        request = self.trigger(sid, action)
        return self.event(sid, {"type": "dialog_result", "token": request["token"], "accepted": True, "path": str(path)})

    def current(self, sid: str | None = None) -> dict:
        """GET /api/workspace/current."""

        status, payload = self.request("GET", "/api/workspace/current" + (f"?sid={sid}" if sid else ""))
        assert status == 200
        return payload

    def dataset(self, dataset_id: str) -> tuple[int, dict]:
        """GET /api/workspace/dataset."""

        return self.request("GET", "/api/workspace/dataset?id=" + urllib.parse.quote(dataset_id))

    def datasets(self, base: str = "") -> dict:
        """GET /api/workspace/datasets."""

        status, payload = self.request("GET", "/api/workspace/datasets?base=" + urllib.parse.quote(base))
        assert status == 200
        return payload

    def use(self, dataset_id: str | None) -> tuple[int, dict]:
        """POST /api/workspace/current."""

        return self.request("POST", "/api/workspace/current", {"id": dataset_id})

    def add(self, dataset_id: str, piece: str, fields: dict) -> tuple[int, dict]:
        """POST /api/workspace/add."""

        return self.request("POST", "/api/workspace/add", {"id": dataset_id, "piece": piece, **fields})

    def load_cube(self, dataset_id: str) -> dict:
        """Loads a dataset in the Cube explorer and waits for the load to end."""

        status, answer = self.request("POST", "/api/cubes/load", {"id": dataset_id})
        assert status == 200 and answer["ok"], answer
        deadline = time.time() + 30.0
        while time.time() < deadline:
            state = self.request("GET", "/api/cubes/status")[1]
            if state["state"] != "loading":
                return state
            time.sleep(0.05)
        raise AssertionError("the cube load did not end")


class BridgeServer:
    """A console with the TomoVis, workspace and cube routers over a bridge harness, on a free port.

    Attributes:
        harness  : The bridge harness.
        sessions : TomoVis page sessions.
        watch    : TomoVis import watch.
        httpd    : HTTP server.
        client   : Client of the server.
    """

    def __init__(self, harness: BridgeHarness) -> None:
        """Builds and starts the server.

        Args:
            harness : Bridge harness the routers serve.
        """

        self.harness  = harness
        self.sessions = TomoVisSessions(harness.logger)
        self.watch    = TomoVisImportWatch(harness.bridge, harness.logger)
        self.httpd    = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
        self.httpd.router = RequestRouter(harness.logger, [TomoVisRouter(self.sessions, self.watch, harness.logger), WorkspaceRouter(harness.bridge), CubeRouter(harness.cubes)])
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
        self.client = BridgeClient(self.httpd.server_address[1])

    def close(self) -> None:
        """Stops the server."""

        self.httpd.shutdown()
        self.httpd.server_close()


class FixtureCopies:
    """Copies TomoVis fixtures into a test folder, for tests that change or delete the source."""

    def __init__(self, folder: Path) -> None:
        """Stores the target folder.

        Args:
            folder : Folder the copies are written to.
        """

        self.folder = folder
        self.folder.mkdir(parents=True, exist_ok=True)

    def copy(self, source: Path, name: str | None = None) -> Path:
        """Copies one fixture and returns the copy's path."""

        target = self.folder / (source.name if name is None else name)
        shutil.copyfile(source, target)
        return target
