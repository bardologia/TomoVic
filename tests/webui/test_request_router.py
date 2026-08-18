"""Tests for the HTTP request router and its sub-router route tables.

Covers JSON sanitisation and query accessors on HttpExchange, exact versus
wildcard route resolution, duplicate route and section conflicts, the stable
route inventory of the served router list, same-origin enforcement, body
parsing, and the 404 and 500 fallbacks.
"""
from __future__ import annotations

import ast
from collections import Counter

import pytest

from request_router          import RequestRouter
from routers.cube_routers    import CubeRouter, SliceRouter
from routers.dispatch        import HttpExchange, RouteConflict, RouteTable, SubRouter
from routers.launch_routers  import CatalogRouter, JobRouter, RunConfigRouter, SavedRunRouter
from routers.library_routers import ContentLibraryRouter
from routers.results_routers import DatasetRouter, ResultsRouter
from routers.static_router   import StaticRouter
from routers.system_router   import SystemRouter

from tests.webui.conftest import FakeHandler, WEBUI_ROOT

ROUTE_COUNT   = 56
SECTION_COUNT = 20

RESOLUTIONS = [
    ("GET",  "/",                                StaticRouter),
    ("GET",  "/static/js/app.js",                StaticRouter),
    ("GET",  "/resultsmedia",                    StaticRouter),
    ("GET",  "/api/results/tree",                ResultsRouter),
    ("GET",  "/api/fs/runs",                     DatasetRouter),
    ("GET",  "/api/cubes/plane",                 CubeRouter),
    ("POST", "/api/cubes/save_slices",           CubeRouter),
    ("GET",  "/api/slices/slice",                SliceRouter),
    ("POST", "/api/slices/collect",              SliceRouter),
    ("GET",  "/api/equations",                   ContentLibraryRouter),
    ("GET",  "/api/configs",                     ContentLibraryRouter),
    ("GET",  "/api/project",                     CatalogRouter),
    ("GET",  "/api/scripts/pre_process",         CatalogRouter),
    ("GET",  "/api/scripts/pre_process/config",  CatalogRouter),
    ("POST", "/api/run",                         JobRouter),
    ("GET",  "/api/jobs/job-1/stream",           JobRouter),
    ("GET",  "/api/jobs/job-1/log",              JobRouter),
    ("POST", "/api/saved-runs/abc/delete",       SavedRunRouter),
    ("GET",  "/api/saved-runs",                  SavedRunRouter),
    ("GET",  "/api/run-config",                  RunConfigRouter),
    ("GET",  "/api/run-config/runs",             RunConfigRouter),
    ("GET",  "/api/system",                      SystemRouter),
    ("POST", "/api/system/detach",               SystemRouter),
]


class RecordingLogger:
    """Logger stand-in collecting emitted lines.

    Attributes:
        lines: (level, message) tuples in emission order, with level one of
            INFO, WARN or ERROR.
    """

    def __init__(self) -> None:
        """Starts with an empty line log."""
        self.lines = []

    def info(self, message: str) -> None:
        """Records an INFO line."""
        self.lines.append(("INFO", message))

    def warning(self, message: str) -> None:
        """Records a WARN line."""
        self.lines.append(("WARN", message))

    def error(self, message: str) -> None:
        """Records an ERROR line."""
        self.lines.append(("ERROR", message))


class EchoRouter(SubRouter):
    """Sub-router declaring exact and wildcard echo routes for routing tests.

    Attributes:
        seen: One entry per served GET, holding the wildcard key or None.
        bodies: Parsed request bodies of served POSTs.
    """

    def __init__(self, sections: tuple) -> None:
        """Initialises the request logs, then declares the routes for `sections`."""
        self.seen   = []
        self.bodies = []
        super().__init__(sections)

    def declare(self, table: RouteTable) -> None:
        """Declares GET and POST on /api/echo plus a wildcard GET on /api/echo/<key>/tail."""
        table.add("GET",  "/api/echo", self.plain)
        table.add("POST", "/api/echo", self.posted)
        table.wildcard("GET", "/api/echo/", "/tail", self.tail)

    def plain(self, exchange: HttpExchange) -> None:
        """Records the GET and answers with an ok payload."""
        self.seen.append(None)
        exchange.send_json({"ok": True})

    def posted(self, exchange: HttpExchange) -> None:
        """Records the parsed request body and answers with an ok payload."""
        self.bodies.append(exchange.body)
        exchange.send_json({"ok": True})

    def tail(self, exchange: HttpExchange, key: str) -> None:
        """Records the wildcard key and echoes it back."""
        self.seen.append(key)
        exchange.send_json({"ok": True, "key": key})


class BoomRouter(SubRouter):
    """Sub-router whose only route raises, exercising the 500 fallback."""

    def declare(self, table: RouteTable) -> None:
        """Declares GET /api/boom."""
        table.add("GET", "/api/boom", self.explode)

    def explode(self, exchange: HttpExchange) -> None:
        """Raises RuntimeError to trigger the router's error handling.

        Raises:
            RuntimeError: Always.
        """
        raise RuntimeError("kaboom")


def build_routers() -> list:
    """Returns one instance of every sub-router the server mounts, wired with null dependencies."""
    return [
        StaticRouter(None, None),
        ResultsRouter(None),
        DatasetRouter(None),
        CubeRouter(None),
        SliceRouter(None),
        ContentLibraryRouter("/api/equations", None, "groups"),
        ContentLibraryRouter("/api/flows",     None, "flows"),
        ContentLibraryRouter("/api/pipelines", None, "pipelines"),
        ContentLibraryRouter("/api/repomap",   None, "folders"),
        ContentLibraryRouter("/api/configs",   None, "groups"),
        CatalogRouter(None, None, None, None, None),
        JobRouter(None, None, None),
        SavedRunRouter(None, None, None),
        RunConfigRouter(None),
        SystemRouter(None, None, None, None, None),
    ]


def served_router_names() -> Counter:
    """Returns the sub-router class names passed to RequestRouter in web_ui_server.py, counted by class."""
    tree  = ast.parse((WEBUI_ROOT / "web_ui_server.py").read_text(encoding="utf-8"))
    calls = [node for node in ast.walk(tree) if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "RequestRouter"]

    assert len(calls) == 1

    listing = next(arg for arg in calls[0].args if isinstance(arg, ast.List))

    return Counter(element.func.id for element in listing.elts if isinstance(element, ast.Call) and isinstance(element.func, ast.Name))


def test_jsonsafe_replaces_non_finite_floats():
    """NaN and infinities are replaced by null at every nesting depth."""
    payload = {
        "ok"     : True,
        "value"  : float("nan"),
        "high"   : float("inf"),
        "low"    : float("-inf"),
        "fine"   : 1.5,
        "count"  : 3,
        "name"   : "run",
        "nested" : {"mu": float("nan"), "list": [1.0, float("inf"), {"deep": float("nan")}]},
    }

    safe = HttpExchange.jsonsafe(payload)

    assert safe["ok"] is True
    assert safe["value"] is None
    assert safe["high"] is None
    assert safe["low"] is None
    assert safe["fine"] == 1.5
    assert safe["count"] == 3
    assert safe["name"] == "run"
    assert safe["nested"]["mu"] is None
    assert safe["nested"]["list"] == [1.0, None, {"deep": None}]


def test_jsonsafe_keeps_bools_and_none():
    """Booleans and None survive sanitisation unchanged."""
    assert HttpExchange.jsonsafe({"flag": False, "none": None}) == {"flag": False, "none": None}


def test_query_accessors_apply_defaults():
    """Query accessors coerce values and fall back to the given defaults."""
    exchange = HttpExchange.of(FakeHandler("GET", "/api/cubes/plane?id=run&az=7&frac=0.5&vmax="))

    assert exchange.text("id")             == "run"
    assert exchange.text("space", "phys")  == "phys"
    assert exchange.texts("id")            == ["run"]
    assert exchange.integer("az")          == 7
    assert exchange.number("frac")         == 0.5
    assert exchange.number("keep", "-inf") == float("-inf")
    assert exchange.optional_number("vmax") is None


def test_route_table_prefers_exact_then_wildcard():
    """An exact route wins over the wildcard, and a wildcard is method-specific."""
    router = EchoRouter(("/api/echo",))

    action, key = router.table.action_for("GET", "/api/echo")
    assert key is None and action is not None

    action, key = router.table.action_for("GET", "/api/echo/abc/tail")
    assert key == "abc"

    assert router.table.action_for("POST", "/api/echo/abc/tail") == (None, None)


def test_route_table_rejects_duplicate_declarations():
    """Declaring the same exact or wildcard route twice raises RouteConflict."""
    table = RouteTable()
    table.add("GET", "/api/echo", print)

    with pytest.raises(RouteConflict):
        table.add("GET", "/api/echo", print)

    table.wildcard("GET", "/api/echo/", "/tail", print)

    with pytest.raises(RouteConflict):
        table.wildcard("GET", "/api/echo/", "/tail", print)


def test_router_rejects_two_owners_of_a_section():
    """Two sub-routers claiming the same section raise RouteConflict."""
    with pytest.raises(RouteConflict):
        RequestRouter(None, [EchoRouter(("/api/echo",)), EchoRouter(("/api/echo",))])


def test_route_inventory_is_stable():
    """The declared route count and section count match the recorded inventory, with no raw sections."""
    routers = build_routers()
    router  = RequestRouter(None, routers)

    declared = sum(len(sub.table.exact) + len(sub.table.wildcards) for sub in routers)
    raw      = sum(len(sub.raw_sections) for sub in routers)

    assert declared == ROUTE_COUNT
    assert len(router.sections) == SECTION_COUNT
    assert raw == 0


def test_build_routers_mirrors_the_served_router_list():
    """The routers built here match, class for class, those mounted by web_ui_server.py."""
    built  = Counter(type(sub).__name__ for sub in build_routers())
    served = served_router_names()

    assert built == served


@pytest.mark.parametrize("method,path,owner", RESOLUTIONS)
def test_every_frontend_path_resolves_to_one_sub_router(method, path, owner):
    """Each frontend path is claimed by exactly one sub-router, which also owns its section."""
    routers = build_routers()
    router  = RequestRouter(None, routers)

    owners = [sub for sub in routers if sub.table.action_for(method, path)[0] is not None]

    assert len(owners) == 1, path
    assert type(owners[0]) is owner
    assert router.sections[RequestRouter._section_of(path)] is owners[0]


def test_an_unknown_path_falls_back_to_404():
    """An unclaimed path answers 404 and is logged as a warning."""
    logger = RecordingLogger()
    router = RequestRouter(logger, [EchoRouter(("/api/echo",))])

    missing = FakeHandler("GET", "/api/nope")
    router.route(missing)

    assert missing.status    == 404
    assert missing.payload() == {"error": "not found"}
    assert logger.lines      == [("WARN", "GET /api/nope -> 404: not found")]


def test_the_server_binds_only_the_verbs_the_router_serves():
    """The HTTP server class implements only the GET and POST verbs."""
    tree    = ast.parse((WEBUI_ROOT / "web_ui_server.py").read_text(encoding="utf-8"))
    handler = next(node for node in ast.walk(tree) if isinstance(node, ast.ClassDef) and node.name == "_Handler")
    verbs   = sorted(item.name for item in handler.body if isinstance(item, ast.FunctionDef) and item.name.startswith("do_"))

    assert verbs == ["do_GET", "do_POST"]


def test_a_cross_origin_request_is_refused_before_it_reaches_a_handler():
    """A request with a foreign Origin is refused with 403 before the handler runs."""
    echo   = EchoRouter(("/api/echo",))
    logger = RecordingLogger()
    router = RequestRouter(logger, [echo])

    handler = FakeHandler("GET", "/api/echo", headers={"Host": "127.0.0.1:8765", "Origin": "http://evil.example"})
    router.route(handler)

    assert handler.status == 403
    assert handler.payload() == {"error": "cross-origin request refused"}
    assert echo.seen == []
    assert logger.lines == [("WARN", "GET /api/echo -> 403: cross-origin request refused")]


def test_a_same_origin_request_and_a_headerless_client_are_served():
    """A same-origin browser request and a client sending no Origin are both served."""
    echo   = EchoRouter(("/api/echo",))
    logger = RecordingLogger()
    router = RequestRouter(logger, [echo])

    browser = FakeHandler("GET", "/api/echo", headers={"Host": "127.0.0.1:8765", "Origin": "http://127.0.0.1:8765"})
    router.route(browser)

    tool = FakeHandler("GET", "/api/echo", headers={"Host": "127.0.0.1:8765"})
    router.route(tool)

    assert browser.status == 200
    assert tool.status    == 200
    assert echo.seen      == [None, None]
    assert logger.lines   == []


def test_json_replies_carry_no_wildcard_cors_header():
    """JSON replies carry no wildcard Access-Control-Allow-Origin header."""
    router  = RequestRouter(RecordingLogger(), [EchoRouter(("/api/echo",))])
    handler = FakeHandler("GET", "/api/echo")

    router.route(handler)

    assert "Access-Control-Allow-Origin" not in handler.sent


def test_a_malformed_post_body_is_refused_and_logged():
    """A truncated JSON body answers 400, is logged as a warning and never reaches the handler."""
    echo   = EchoRouter(("/api/echo",))
    logger = RecordingLogger()
    router = RequestRouter(logger, [echo])

    handler = FakeHandler("POST", "/api/echo", b'{"script_key": "pre_proc')
    router.route(handler)

    assert handler.status == 400
    assert handler.payload()["error"].startswith("unreadable request body:")
    assert echo.bodies == []
    assert [level for level, _ in logger.lines] == ["WARN"]
    assert logger.lines[0][1].startswith("POST /api/echo -> 400: unreadable request body:")


def test_a_well_formed_post_body_reaches_the_handler():
    """A valid JSON body is parsed and passed to the handler."""
    echo   = EchoRouter(("/api/echo",))
    router = RequestRouter(RecordingLogger(), [echo])

    handler = FakeHandler("POST", "/api/echo", b'{"script_key": "pre_process"}')
    router.route(handler)

    assert handler.status == 200
    assert echo.bodies == [{"script_key": "pre_process"}]


def test_an_unhandled_handler_error_answers_500_and_logs_the_traceback():
    """A handler exception answers 500 with the message and logs the traceback."""
    logger = RecordingLogger()
    router = RequestRouter(logger, [BoomRouter(("/api/boom",))])

    handler = FakeHandler("GET", "/api/boom")
    router.route(handler)

    assert handler.status    == 500
    assert handler.payload() == {"error": "kaboom"}
    assert logger.lines[0][0] == "ERROR"
    assert "router error on GET /api/boom" in logger.lines[0][1]
    assert "Traceback (most recent call last)" in logger.lines[0][1]
    assert "RuntimeError: kaboom" in logger.lines[0][1]


def test_trailing_slash_and_body_are_normalised():
    """A trailing slash and a query string still resolve to the exact route."""
    echo   = EchoRouter(("/api/echo",))
    router = RequestRouter(RecordingLogger(), [echo])

    handler = FakeHandler("GET", "/api/echo/?x=1")
    router.route(handler)

    assert handler.status == 200
    assert echo.seen == [None]
