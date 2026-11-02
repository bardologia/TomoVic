"""Tests for the Pauli routes of the cube router.

Covers the ``stretch`` query parameter (absent means the per-channel stretch
both views default to, "shared" pools the components, and any other value is
refused instead of silently rendering a different map), the pixel readout and
map routes, and the headers the globe drape route carries: the lon/lat
rectangle and the rendered window.
"""

from __future__ import annotations

from urllib.parse import quote

import pytest

from routers.cube_routers       import CubeRouter
from routers.dispatch           import HttpExchange
from tests.webui.conftest       import FakeHandler
from tests.webui.pauli_fixtures import loaded_polarimetric_run


def _answer(explorer, route: str, cube_id: str, query: str) -> FakeHandler:
    """Answers one GET request on a Pauli route through the router and returns the handler."""
    handler = FakeHandler("GET", f"/api/cubes/{route}?id={quote(cube_id, safe='')}{query}")
    getattr(CubeRouter(explorer), route)(HttpExchange.of(handler))
    return handler


def test_stretch_defaults_to_per_channel_and_refuses_unknown_values(tmp_path):
    """Checks a request without stretch gets per-channel bounds, "shared" pools them and a typo raises."""
    explorer, cube_id, _ = loaded_polarimetric_run(tmp_path)

    default = _answer(explorer, "pauli_summary", cube_id, "&win_az=2&win_rg=2").payload()
    assert default["ok"]
    assert default["bounds"]["surface"] != default["bounds"]["volume"]

    shared = _answer(explorer, "pauli_summary", cube_id, "&win_az=2&win_rg=2&stretch=shared").payload()
    assert shared["bounds"]["surface"] == shared["bounds"]["double"] == shared["bounds"]["volume"]

    with pytest.raises(ValueError, match="stretch"):
        _answer(explorer, "pauli_summary", cube_id, "&win_az=2&win_rg=2&stretch=chanel")


def test_pauli_map_and_readout_routes_answer(tmp_path):
    """Checks the map route serves a PNG, the readout route a pixel payload, and an unknown mode answers 404."""
    explorer, cube_id, _ = loaded_polarimetric_run(tmp_path)

    mapped = _answer(explorer, "pauli_map", cube_id, "&mode=dominant&win_az=2&win_rg=2")
    assert mapped.status == 200 and mapped.wfile.getvalue()[:4] == b"\x89PNG"

    value = _answer(explorer, "pauli_at", cube_id, "&az=1&rg=2&win_az=3&win_rg=1").payload()
    assert value["ok"] and (value["az"], value["rg"]) == (1, 2) and value["window"] == [3, 1]

    assert _answer(explorer, "pauli_map", cube_id, "&mode=banana").status == 404


def test_globe_pauli_reports_the_rectangle_and_the_rendered_window(tmp_path):
    """Checks the drape route sends the PNG with its rectangle and the window it rendered in headers, and 404 without geocoding."""
    explorer, cube_id, _ = loaded_polarimetric_run(tmp_path, with_geo=True)

    handler = _answer(explorer, "globe_pauli", cube_id, "&mode=rgb&win_az=2&win_rg=3")

    assert handler.status == 200
    assert handler.wfile.getvalue()[:4] == b"\x89PNG"
    assert len(handler.sent["X-Rectangle"].split(",")) == 4
    assert handler.sent["X-Window"] == "2,3"

    flat, flat_id, _ = loaded_polarimetric_run(tmp_path / "flat")
    assert _answer(flat, "globe_pauli", flat_id, "&mode=rgb").status == 404
