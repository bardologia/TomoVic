"""Tests covering how the web UI server composes its routers and serves the library endpoints."""
from __future__ import annotations

import pytest

from bridge.dataset_workspace import WorkspaceBusyError
from gpu_activity             import GpuActivityLog
from host_history             import HostHistoryLog
from request_router           import RequestRouter
from routers.library_routers  import ContentLibraryRouter
from system_monitor           import ActiveUsers, SystemHistory, SystemMonitor
from web_ui_server            import WebUIServer

from tests.webui.conftest import FakeHandler


FRONTEND_PATHS = [
    "/api/repomap",
    "/api/configs",
]


@pytest.fixture(scope="module")
def server():
    """Returns a server whose background sampling loops are disabled."""
    original = (SystemMonitor._du_loop, SystemHistory.sample_loop, ActiveUsers.sample_loop, GpuActivityLog.sample_loop, HostHistoryLog.sample_loop)

    SystemMonitor._du_loop      = lambda self: None
    SystemHistory.sample_loop   = lambda self: None
    ActiveUsers.sample_loop     = lambda self: None
    GpuActivityLog.sample_loop  = lambda self: None
    HostHistoryLog.sample_loop  = lambda self: None
    try:
        yield WebUIServer(host="127.0.0.1", port=0)
    finally:
        SystemMonitor._du_loop, SystemHistory.sample_loop, ActiveUsers.sample_loop, GpuActivityLog.sample_loop, HostHistoryLog.sample_loop = original


def _get(server: WebUIServer, path: str) -> tuple[int, object]:
    """Routes a GET through the server and returns the status and payload."""
    handler = FakeHandler("GET", path)
    server.router.route(handler)
    return handler.status, handler.payload()


def test_the_composed_router_owns_every_section_once(server):
    """Every section is claimed by exactly one sub-router and no section is raw."""
    claimed = [section for sub in server.router.routers for section in sub.sections]
    raw     = [section for sub in server.router.routers for section in sub.raw_sections]

    assert len(claimed) == len(set(claimed))
    assert sorted(claimed) == sorted(server.router.sections)
    assert all(server.router.sections[section] is sub for sub in server.router.routers for section in sub.sections)
    assert raw == []


@pytest.mark.parametrize("path", FRONTEND_PATHS)
def test_every_library_endpoint_answers_with_content(server, path):
    """Each library endpoint answers 200 with a non-empty payload."""
    status, payload = _get(server, path)

    assert status == 200
    assert payload


def test_the_library_envelopes_match_what_the_frontend_reads(server):
    """The content library envelopes carry the keys the frontend reads."""
    assert list(_get(server, "/api/repomap")[1])   == ["folders"]
    assert list(_get(server, "/api/configs")[1])   == ["groups"]


def test_every_library_router_is_bound_to_a_real_library(server):
    """Every library router is bound to a library exposing a collect method."""
    routers = [sub for sub in server.router.routers if isinstance(sub, ContentLibraryRouter)]

    assert len(routers) == len(FRONTEND_PATHS)
    assert all(sub.library is not None for sub in routers)
    assert all(callable(getattr(sub.library, "collect")) for sub in routers)


def test_the_script_catalog_lists_every_console_entry(server):
    """The catalog endpoint lists exactly the six console entry points."""
    status, payload = _get(server, "/api/scripts")

    assert status == 200
    assert {entry["key"] for entry in payload["scripts"]} == {"pre_process", "extract_params", "extract_polarimetry", "analyze_preprocessing", "analyze_param_extraction", "compare_preprocessing_trials"}


def test_the_workspace_section_is_claimed_once(server):
    """/api/workspace belongs to exactly one router, and the default workspace is <repo root>/workspace."""
    claimed = [section for sub in server.router.routers for section in sub.sections]

    assert claimed.count("/api/workspace") == 1
    assert server.workspace.root == (server.paths.repo_root / "workspace").resolve()


def test_building_a_server_writes_no_workspace(server, tmp_path):
    """A server built with --workspace uses that folder and creates nothing in it until a dataset is registered."""
    built = WebUIServer(host="127.0.0.1", port=0, workspace=tmp_path / "ws")

    assert built.workspace.root == (tmp_path / "ws").resolve()
    assert not (tmp_path / "ws").exists()


def test_the_workspace_answers_before_the_bridge_started(server):
    """GET /api/workspace/current answers 200 with no current dataset on a freshly built server."""
    status, payload = _get(server, "/api/workspace/current")

    assert status == 200
    assert payload["ok"] and "current" in payload


def test_an_unknown_endpoint_is_still_a_404(server):
    """An unrouted API path is a 404."""
    assert _get(server, "/api/does-not-exist")[0] == 404


def test_the_router_is_a_request_router(server):
    """The server exposes a RequestRouter and a real repository root."""
    assert isinstance(server.router, RequestRouter)
    assert server.paths.repo_root.is_dir()


def test_a_second_console_on_one_workspace_is_refused(server, tmp_path):
    """Claiming a workspace another console holds raises WorkspaceBusyError naming the folder; another folder is free."""
    first  = WebUIServer(host="127.0.0.1", port=0, workspace=tmp_path / "ws")
    second = WebUIServer(host="127.0.0.1", port=0, workspace=tmp_path / "ws")
    other  = WebUIServer(host="127.0.0.1", port=0, workspace=tmp_path / "other")
    first.workspace.claim()

    with pytest.raises(WorkspaceBusyError) as busy:
        second.workspace.claim()
    other.workspace.claim()

    assert str(busy.value) == f"another TomoVic console uses the workspace {(tmp_path / 'ws').resolve()}; stop it, or start this console with --workspace <another folder>"
