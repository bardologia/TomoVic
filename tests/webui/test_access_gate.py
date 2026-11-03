"""Tests for the console access key.

Unit tests drive the request router's access gate with stub handlers: the keyed
link is answered with a redirect that drops the key and sets the cookie named
after the port the browser used, a browser holding the cookie is served, and
requests without the key, with a wrong key or with another port's cookie are
refused before any handler runs. Entry tests check that serve.py takes the key
from the environment, removes it there, refuses a non-loopback host without one
and refuses a Unix socket together with a host or port. Live tests start
serve.py on every interface and on a Unix socket behind a key and walk the
browser path over real HTTP.
"""

from __future__ import annotations

import http.client
import os
import socket
import stat
import subprocess
import sys
import time
from pathlib import Path

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
        self.router = RequestRouter(self.logger, [self.echo], AccessGate(KEY))

    def get(self, path: str, headers: dict | None = None, host: str = f"127.0.0.1:{PORT}") -> FakeHandler:
        """Routes a GET for `path` with the given headers and Host header and returns the answered handler."""
        handler = FakeHandler("GET", path, headers={"Host": host, **(headers or {})})
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


@pytest.mark.parametrize("host, cookie", [("127.0.0.1:18765", "tomovic_key_18765"), ("localhost", "tomovic_key_80"), ("[::1]:9000", "tomovic_key_9000")])
def test_the_cookie_is_named_after_the_port_the_browser_connected_to(host, cookie):
    """The cookie name follows the Host header port, so a tunnelled console keys its cookie on the local end."""
    handler = GatedRouter().get(f"/?key={KEY}", host=host)

    assert handler.sent["Set-Cookie"].startswith(f"{cookie}={KEY};")


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
        AccessGate(key)


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

    assert received["access_key"]  == KEY
    assert received["host"]        == "0.0.0.0"
    assert received["port"]        == 8790
    assert received["unix_socket"] is None
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


def test_serve_refuses_a_unix_socket_together_with_a_port(tmp_path):
    """serve.py --unix-socket with --port exits with a usage error, since the two exclude each other."""
    result = subprocess.run([sys.executable, str(WEBUI_ROOT / "serve.py"), "--unix-socket", str(tmp_path / "c.sock"), "--port", "8790"], capture_output=True, text=True, timeout=60)

    assert result.returncode == 2
    assert "--unix-socket replaces --host and --port" in result.stderr


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


def _make_root(path: Path) -> Path:
    """Creates the directories ProjectPaths requires under a temporary root and returns it."""
    for name in ("main", "configuration", "tools"):
        (path / name).mkdir(parents=True)
    return path


def _socket_request(path: Path, target: str, cookie: str = "") -> http.client.HTTPResponse:
    """Sends one GET over the Unix socket, as the far end of an SSH tunnel on port 18765 would, and returns the read response."""
    connection      = http.client.HTTPConnection("127.0.0.1", 18765, timeout=5)
    connection.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    connection.sock.connect(str(path))

    connection.request("GET", target, headers={"Cookie": cookie} if cookie else {})
    response = connection.getresponse()
    response.read()
    connection.close()

    return response


def _start_on_socket(root: Path, path: Path) -> subprocess.Popen:
    """Starts serve.py on the Unix socket behind KEY and returns the process once the socket answers."""
    environment = {**os.environ, serve.ServeEntry.KEY_VARIABLE: KEY}
    proc        = subprocess.Popen([sys.executable, str(WEBUI_ROOT / "serve.py"), "--unix-socket", str(path), "--root", str(root)], env=environment, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)

    deadline = time.monotonic() + 60.0
    while time.monotonic() < deadline:
        try:
            _socket_request(path, "/api/jobs")
            return proc
        except OSError:
            time.sleep(0.5)

    proc.kill()
    pytest.fail("console did not come up on the socket in time")


def test_a_keyed_console_on_a_unix_socket_is_private_and_admits_only_its_link(tmp_path):
    """The socket is created 0600, refuses a bare visit, redirects the link with a cookie for the tunnel port, then serves it."""
    root = _make_root(tmp_path / "project_root")
    path = tmp_path / "tomovic.sock"
    proc = _start_on_socket(root, path)

    try:
        assert stat.S_IMODE(path.stat().st_mode) == 0o600
        assert _socket_request(path, "/api/jobs").status == 403

        link = _socket_request(path, f"/?key={KEY}")
        assert link.status == 303
        assert link.getheader("Set-Cookie").startswith(f"tomovic_key_18765={KEY};")

        cookie = link.getheader("Set-Cookie").split(";")[0]
        assert _socket_request(path, "/api/jobs", cookie).status == 200
    finally:
        proc.terminate()
        proc.wait(timeout=15)


def test_a_socket_left_by_a_dead_console_is_replaced_and_a_live_one_is_not(tmp_path):
    """A console killed without cleanup leaves its socket file, which the next console takes over; a second console beside a live one exits."""
    root  = _make_root(tmp_path / "project_root")
    path  = tmp_path / "tomovic.sock"
    first = _start_on_socket(root, path)

    environment = {**os.environ, serve.ServeEntry.KEY_VARIABLE: KEY}
    second      = subprocess.run([sys.executable, str(WEBUI_ROOT / "serve.py"), "--unix-socket", str(path), "--root", str(root)], env=environment, capture_output=True, text=True, timeout=60)

    assert second.returncode != 0
    assert "another console already answers" in second.stdout + second.stderr

    first.kill()
    first.wait(timeout=15)
    assert path.exists()

    third = _start_on_socket(root, path)
    try:
        assert _socket_request(path, "/api/jobs").status == 403
    finally:
        third.terminate()
        third.wait(timeout=15)
