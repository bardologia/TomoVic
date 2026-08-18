"""Tests covering how the web UI server composes its routers and serves the library endpoints."""
from __future__ import annotations

import pytest

from request_router          import RequestRouter
from routers.library_routers import ContentLibraryRouter
from system_monitor          import ActiveUsers, SystemHistory, SystemMonitor
from web_ui_server           import WebUIServer

from tests.webui.conftest import FakeHandler


FRONTEND_PATHS = [
    "/api/repomap",
    "/api/configs",
]


@pytest.fixture(scope="module")
def server():
    """Returns a server whose background sampling loops are disabled."""
    original = (SystemMonitor._du_loop, SystemHistory.sample_loop, ActiveUsers.sample_loop)

    SystemMonitor._du_loop      = lambda self: None
    SystemHistory.sample_loop   = lambda self: None
    ActiveUsers.sample_loop     = lambda self: None
    try:
        yield WebUIServer(host="127.0.0.1", port=0)
    finally:
        SystemMonitor._du_loop, SystemHistory.sample_loop, ActiveUsers.sample_loop = original


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
    """The catalog endpoint lists exactly the three console entry points."""
    status, payload = _get(server, "/api/scripts")

    assert status == 200
    assert {entry["key"] for entry in payload["scripts"]} == {"pre_process", "analyze_preprocessing", "compare_preprocessing_trials"}


def test_an_unknown_endpoint_is_still_a_404(server):
    """An unrouted API path is a 404."""
    assert _get(server, "/api/does-not-exist")[0] == 404


def test_the_router_is_a_request_router(server):
    """The server exposes a RequestRouter and a real repository root."""
    assert isinstance(server.router, RequestRouter)
    assert server.paths.repo_root.is_dir()
