"""Tests for the console access key.

Unit tests drive the request router's access gate with stub handlers: the keyed
link is answered with a redirect that drops the key and sets the cookie, a
browser holding the cookie is served, and requests without the key, with a wrong
key or with another port's cookie are refused before any handler runs. Entry
tests check that serve.py takes the key from the environment, removes it there,
and refuses a non-loopback host without one. A live test starts serve.py on every
interface behind a key and walks the browser path over real HTTP.
"""

from __future__ import annotations

import http.client
import os
import socket
import subprocess
import sys
import time

import pytest

import serve
from request_router import AccessGate, RequestRouter

from tests.webui.conftest            import WEBUI_ROOT, FakeHandler
from tests.webui.test_request_router import EchoRouter, RecordingLogger

KEY  = "k3y-For_The-Console-0123456789"
PORT = 8765


class GatedRouter:
    """A request router with one echo section behind an access gate on PORT.

    Attributes:
        echo   : Echo sub-router recording what reaches it.
        logger : Recording logger collecting the router's warnings.
        router : Request router holding the echo section and the gate.
    """

    def __init__(self) -> None:
        """Builds the echo section, the logger and the gated router."""
        self.echo   = EchoRouter(("/api/echo",))
        self.logger = RecordingLogger()
        self.router = RequestRouter(self.logger, [self.echo], AccessGate(KEY, PORT))

    def get(self, path: str, headers: dict | None = None) -> FakeHandler:
        """Routes a GET for `path` with the given headers and returns the answered handler."""
        handler = FakeHandler("GET", path, headers={"Host": f"127.0.0.1:{PORT}", **(headers or {})})
        self.router.route(handler)
        return handler


def test_the_keyed_link_redirects_without_the_key_and_sets_the_cookie():
    """A GET carrying the key is answered 303 to the same address without it, setting an HttpOnly cookie."""
    gated   = GatedRouter()
    handler = gated.get(f"/api/echo?key={KEY}&view=cube")

    assert handler.status             == 303
    assert handler.sent["Location"]   == "/api/echo?view=cube"
    assert handler.sent["Set-Cookie"] == f"tomovic_key_{PORT}={KEY}; Path=/; HttpOnly; SameSite=Lax"
    assert gated.echo.seen            == []


def test_the_keyed_link_to_the_root_redirects_to_the_bare_root():
    """The link as the launcher hands it out lands on / with no query left."""
    handler = GatedRouter().get(f"/?key={KEY}")

    assert handler.status           == 303
    assert handler.sent["Location"] == "/"


def test_a_browser_holding_the_cookie_is_served():
    """A request carrying the key cookie, among other cookies, reaches its handler."""
    gated   = GatedRouter()
    handler = gated.get("/api/echo", {"Cookie": f"theme=dark; tomovic_key_{PORT}={KEY}"})

    assert handler.status     == 200
    assert gated.echo.seen    == [None]
    assert gated.logger.lines == []


@pytest.mark.parametrize("headers, path", [
    ({},                                                     "/api/echo"),
    ({"Cookie": f"tomovic_key_{PORT}=wrong-key-value-0000"}, "/api/echo"),
    ({"Cookie": f"tomovic_key_9999={KEY}"},                  "/api/echo"),
    ({},                                                     "/api/echo?key=wrong-key-value-0000"),
])
def test_requests_without_the_key_are_refused_before_any_handler(headers, path):
    """No key, a wrong key, another port's cookie and a wrong link key all answer 403 in plain text."""
    gated   = GatedRouter()
    handler = gated.get(path, headers)

    assert handler.status                    == 403
    assert handler.sent["Content-Type"]      == "text/plain; charset=utf-8"
    assert handler.wfile.getvalue().decode() == AccessGate.REFUSAL
    assert gated.echo.seen                   == []
    assert gated.logger.lines                == [("WARN", f"GET /api/echo -> 403: {AccessGate.REFUSAL}")]


def test_a_cross_origin_request_is_refused_even_with_the_cookie():
    """The origin check still runs first, so a foreign page cannot ride on the cookie."""
    gated   = GatedRouter()
    handler = gated.get("/api/echo", {"Origin": "http://evil.example", "Cookie": f"tomovic_key_{PORT}={KEY}"})

    assert handler.status    == 403
    assert handler.payload() == {"error": "cross-origin request refused"}
    assert gated.echo.seen   == []


@pytest.mark.parametrize("key", ["", "short-key", "has spaces in it 0123", "semi;colon-0123456789"])
def test_a_weak_or_cookie_unsafe_key_is_rejected(key):
    """Keys shorter than 16 characters or holding characters a cookie cannot carry raise ValueError."""
    with pytest.raises(ValueError):
        AccessGate(key, PORT)


def test_serve_takes_the_key_from_the_environment_and_removes_it(monkeypatch):
    """serve.py hands TOMOVIC_ACCESS_KEY to the server and deletes it, so launched jobs do not inherit it."""
    received = {}

    class RecordingServer:
        """Stand-in for WebUIServer recording its constructor arguments."""

        def __init__(self, **kwargs) -> None:
            """Records the keyword arguments."""
            received.update(kwargs)

        def serve(self) -> None:
            """Returns at once instead of serving."""
            return

    monkeypatch.setattr(serve, "WebUIServer", RecordingServer)
    monkeypatch.setattr(sys, "argv", ["serve.py", "--host", "0.0.0.0", "--port", "8790"])
    monkeypatch.setenv(serve.ServeEntry.KEY_VARIABLE, KEY)

    serve.ServeEntry().run()

    assert received["access_key"] == KEY
    assert received["host"]       == "0.0.0.0"
    assert serve.ServeEntry.KEY_VARIABLE not in os.environ


@pytest.mark.parametrize("host, loopback", [("127.0.0.1", True), ("localhost", True), ("0.0.0.0", False)])
def test_loopback_detection(host, loopback):
    """Loopback addresses and localhost count as local, the wildcard address does not."""
    assert serve.ServeEntry()._loopback(host) is loopback


def _free_port() -> int:
    """Returns a TCP port the operating system currently reports as free on every interface."""
    with socket.socket() as sock:
        sock.bind(("0.0.0.0", 0))
        return sock.getsockname()[1]


def _request(port: int, path: str, cookie: str = "") -> http.client.HTTPResponse:
    """Sends one GET to the local console without following redirects and returns the read response."""
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    headers    = {"Cookie": cookie} if cookie else {}

    connection.request("GET", path, headers=headers)
    response = connection.getresponse()
    response.read()
    connection.close()

    return response


def test_serve_refuses_a_network_host_without_a_key(tmp_path):
    """serve.py --host 0.0.0.0 without TOMOVIC_ACCESS_KEY exits with a usage error naming the variable."""
    environment = {name: value for name, value in os.environ.items() if name != serve.ServeEntry.KEY_VARIABLE}
    result      = subprocess.run([sys.executable, str(WEBUI_ROOT / "serve.py"), "--host", "0.0.0.0", "--port", str(_free_port())], env=environment, capture_output=True, text=True, timeout=60)

    assert result.returncode == 2
    assert serve.ServeEntry.KEY_VARIABLE in result.stderr


def test_a_keyed_console_on_every_interface_admits_only_its_link(tmp_path):
    """A live console behind a key refuses a bare visit, redirects its link with the cookie, then serves that cookie."""
    root = tmp_path / "project_root"
    for name in ("main", "configuration", "tools"):
        (root / name).mkdir(parents=True)

    port        = _free_port()
    environment = {**os.environ, serve.ServeEntry.KEY_VARIABLE: KEY}
    proc        = subprocess.Popen([sys.executable, str(WEBUI_ROOT / "serve.py"), "--host", "0.0.0.0", "--port", str(port), "--root", str(root)], env=environment, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)

    try:
        deadline = time.monotonic() + 60.0
        bare     = None
        while bare is None and time.monotonic() < deadline:
            try:
                bare = _request(port, "/api/jobs")
            except OSError:
                time.sleep(0.5)

        assert bare is not None, "server did not come up in time"
        assert bare.status == 403

        link = _request(port, f"/?key={KEY}")
        assert link.status == 303
        assert link.getheader("Location") == "/"

        cookie = link.getheader("Set-Cookie").split(";")[0]
        assert _request(port, "/api/jobs", cookie).status == 200
        assert _request(port, "/", cookie).status         == 200
    finally:
        proc.terminate()
        proc.wait(timeout=15)
