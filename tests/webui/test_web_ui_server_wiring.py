"""Tests covering how the web UI server composes its routers and serves the library endpoints."""
from __future__ import annotations

import pytest

from request_router          import RequestRouter
from routers.library_routers import BackboneRouter, ContentLibraryRouter, ModelLibraryRouter
from system_monitor          import ActiveUsers, SystemHistory, SystemMonitor
from web_ui_server           import WebUIServer

from tests.webui.conftest import FakeHandler


FRONTEND_PATHS = [
    "/api/equations",
    "/api/physics-loss",
    "/api/flows",
    "/api/pipelines",
    "/api/repomap",
    "/api/configs",
    "/api/backbones",
    "/api/profile-autoencoders",
    "/api/image-autoencoders",
    "/api/jepa-variants",
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
    """Every section is claimed by exactly one sub-router and only the TensorBoard prefix is raw."""
    claimed = [section for sub in server.router.routers for section in sub.sections]
    raw     = [section for sub in server.router.routers for section in sub.raw_sections]

    assert len(claimed) == len(set(claimed))
    assert sorted(claimed) == sorted(server.router.sections)
    assert all(server.router.sections[section] is sub for sub in server.router.routers for section in sub.sections)
    assert raw == ["/tb/"]


@pytest.mark.parametrize("path", FRONTEND_PATHS)
def test_every_library_endpoint_answers_with_content(server, path):
    """Each library endpoint answers 200 with a non-empty payload."""
    status, payload = _get(server, path)

    assert status == 200
    assert payload


def test_the_library_envelopes_match_what_the_frontend_reads(server):
    """The content library envelopes carry the keys the frontend reads."""
    assert list(_get(server, "/api/flows")[1])     == ["flows"]
    assert list(_get(server, "/api/pipelines")[1]) == ["pipelines"]
    assert list(_get(server, "/api/equations")[1]) == ["groups"]
    assert list(_get(server, "/api/repomap")[1])   == ["folders"]
    assert list(_get(server, "/api/configs")[1])   == ["groups"]

    assert sorted(_get(server, "/api/physics-loss")[1]) == ["comparison", "config", "dataset", "intro", "operator", "terms"]


def test_the_model_endpoints_answer_with_families(server):
    """The model endpoints answer with families, backbones adding the head list."""
    assert list(_get(server, "/api/profile-autoencoders")[1]) == ["families"]
    assert list(_get(server, "/api/image-autoencoders")[1])   == ["families"]
    assert list(_get(server, "/api/jepa-variants")[1])        == ["families"]
    assert sorted(_get(server, "/api/backbones")[1])          == ["families", "heads"]


def test_a_model_note_is_served_and_an_unknown_key_is_a_404(server):
    """A known model key serves its markdown note and an unknown key is a 404."""
    status, payload = _get(server, "/api/profile-autoencoders/mlp_ae/note")

    assert status == 200
    assert payload["key"] == "mlp_ae"
    assert payload["markdown"].strip()

    assert _get(server, "/api/profile-autoencoders/no_such_model/note")[0] == 404


def test_every_library_router_is_bound_to_a_real_library(server):
    """Every library router is bound to a library exposing a collect method."""
    routers = [sub for sub in server.router.routers if isinstance(sub, (ContentLibraryRouter, ModelLibraryRouter, BackboneRouter))]

    assert len(routers) == 10
    assert all(sub.library is not None for sub in routers)
    assert all(callable(getattr(sub.library, "collect")) for sub in routers)


def test_an_unknown_endpoint_is_still_a_404(server):
    """An unrouted API path is a 404."""
    assert _get(server, "/api/does-not-exist")[0] == 404


def test_the_router_is_a_request_router(server):
    """The server exposes a RequestRouter and a real repository root."""
    assert isinstance(server.router, RequestRouter)
    assert server.paths.repo_root.is_dir()
