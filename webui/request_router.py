"""Top-level HTTP request router for the web UI server.

Indexes the sub-routers by the URL section each one claims, refuses
cross-origin requests, admits only keyed browsers when the console runs behind
an access key, gives raw-path proxies first refusal, and converts unhandled
exceptions into a 500 reply.
"""

from __future__ import annotations

import hmac
import re
import traceback
from http.cookies import SimpleCookie
from urllib.parse import urlencode, urlparse, urlsplit

from routers.dispatch import HttpExchange, RouteConflict, SubRouter
from web_logger       import WebLogger


class AccessGate:
    """Admits only the browsers that opened the console through its keyed link.

    A launcher starts the console with a secret access key and hands the user a
    link carrying that key in the `key` query parameter. A request with the
    right key is answered with a redirect to the same address without the key
    that sets a cookie holding it, so the key leaves the address bar and every
    later request of that browser carries it. Every other request is refused
    with 403.

    The cookie is named after the port in the request's Host header, the port
    the browser itself connected to, because a browser shares cookies across
    all ports of one host. That port is also the right one when the console is
    reached through an SSH tunnel or listens on a Unix socket.

    Attributes:
        key : Secret the link carries, at least 16 URL-safe characters.
    """

    QUERY_NAME = "key"
    KEY_FORMAT = re.compile(r"[A-Za-z0-9_-]{16,}")
    REFUSAL    = "This TomoVic console opens only through the link TomoVis gives. Click Open TomoVic in TomoVis to get a fresh link."

    def __init__(self, key: str) -> None:
        """Stores the key.

        Args:
            key : Secret the console link carries.

        Raises:
            ValueError : If the key is shorter than 16 characters or holds characters outside A-Z, a-z, 0-9, '_' and '-'.
        """
        if not self.KEY_FORMAT.fullmatch(key):
            raise ValueError("the console access key must be at least 16 characters from A-Z, a-z, 0-9, '_' and '-'")

        self.key = key

    def _matches(self, candidate: str) -> bool:
        """Returns whether `candidate` equals the key, compared in constant time."""
        return hmac.compare_digest(candidate.encode("utf-8"), self.key.encode("utf-8"))

    def _cookie_name(self, exchange: HttpExchange) -> str:
        """Returns the name of the key cookie for the port the browser connected to, 80 when the Host header names none."""
        port = urlsplit("//" + exchange.header("Host")).port
        return f"tomovic_key_{port or 80}"

    def _set_cookie(self, exchange: HttpExchange) -> None:
        """Redirects to the requested address without the key parameter, setting the key cookie."""
        rest     = {name: values for name, values in exchange.query.items() if name != self.QUERY_NAME}
        location = exchange.raw_path + ("?" + urlencode(rest, doseq=True) if rest else "")

        exchange.redirect(location, {"Set-Cookie": f"{self._cookie_name(exchange)}={self.key}; Path=/; HttpOnly; SameSite=Lax"})

    def _cookie_value(self, exchange: HttpExchange) -> str:
        """Returns the value of the key cookie the request carries, empty when it carries none."""
        jar = SimpleCookie()
        jar.load(exchange.header("Cookie"))

        morsel = jar.get(self._cookie_name(exchange))
        return "" if morsel is None else morsel.value

    def admit(self, exchange: HttpExchange) -> bool:
        """Returns whether the request may proceed, having answered it with the redirect or the refusal when it may not.

        Args:
            exchange : The request being routed.
        """
        if self._matches(exchange.text(self.QUERY_NAME)):
            self._set_cookie(exchange)
            return False

        if self._matches(self._cookie_value(exchange)):
            return True

        exchange.send_text(self.REFUSAL, 403)
        return False


class RequestRouter:
    """Dispatches HTTP exchanges to the sub-router that owns their URL section.

    Attributes:
        logger: Console logger used for warnings and error reports.
        routers: Sub-routers this router dispatches to.
        gate: Access gate every same-origin request passes first, None when the console admits every request.
        sections: Mapping from URL section prefix to its owning sub-router.
    """

    def __init__(self, logger: WebLogger, routers: list[SubRouter], gate: AccessGate | None = None) -> None:
        """Stores the sub-routers and the access gate and builds the section index.

        Args:
            logger: Console logger for request warnings and router errors.
            routers: Sub-routers whose declared sections must not overlap.
            gate: Access gate for a console started with an access key, None for a console that admits every request.

        Raises:
            RouteConflict: If two sub-routers claim the same section.
        """
        self.logger   = logger
        self.routers  = list(routers)
        self.gate     = gate
        self.sections = self._index()

    def _index(self) -> dict:
        """Returns the section-to-router index, rejecting duplicate section claims.

        Raises:
            RouteConflict: If two sub-routers claim the same section.
        """
        index = {}

        for router in self.routers:
            for section in router.sections:
                owner = index.get(section)
                if owner is not None:
                    raise RouteConflict(f"section '{section}' is claimed by both {type(owner).__name__} and {type(router).__name__}")
                index[section] = router

        return index

    @staticmethod
    def _section_of(path: str) -> str:
        """Returns the routing section of a path: three components under /api, two otherwise."""
        parts = path.split("/")
        depth = 3 if len(parts) > 2 and parts[1] == "api" else 2

        return "/".join(parts[:depth])

    def _proxied(self, exchange: HttpExchange) -> bool:
        """Lets a raw-path claiming router handle the exchange, returning whether one did."""
        for router in self.routers:
            if router.claims_raw(exchange.raw_path):
                router.handle_raw(exchange)
                return True

        return False

    def _dispatch(self, exchange: HttpExchange) -> None:
        """Reads any POST body and hands the exchange to its section's router.

        Replies 400 when a POST body cannot be read and 404 when no router
        claims the section or the owning router declines the request.
        """
        if exchange.method == "POST":
            try:
                exchange.read_body()
            except (ValueError, UnicodeDecodeError) as exc:
                exchange.send_json({"error": f"unreadable request body: {exc}"}, 400)
                return

        router = self.sections.get(self._section_of(exchange.path))
        if router is None or not router.handle(exchange):
            exchange.not_found()

    def _same_origin(self, exchange: HttpExchange) -> bool:
        """Returns whether the request has no Origin header or one matching the Host."""
        origin = exchange.header("Origin")
        if not origin:
            return True

        return urlparse(origin).netloc == exchange.header("Host")

    def _admitted(self, exchange: HttpExchange) -> bool:
        """Returns whether the access gate lets the request through; without a gate every request passes."""
        return self.gate is None or self.gate.admit(exchange)

    def _report(self, exchange: HttpExchange) -> None:
        """Logs a warning for any exchange that finished with a status of 400 or above."""
        if exchange.status < 400:
            return

        detail = f": {exchange.error}" if exchange.error else ""
        self.logger.warning(f"{exchange.method} {exchange.raw_path} -> {exchange.status}{detail}")

    def route(self, handler) -> None:
        """Routes one request end to end, from origin check to error reporting.

        Cross-origin requests get a 403, the access gate answers requests
        without the key, raw-path proxies take precedence over section dispatch,
        a dropped client connection is ignored, and any other exception is
        logged and answered with a 500.

        Args:
            handler: The BaseHTTPRequestHandler serving this request.
        """
        exchange = HttpExchange.of(handler)

        try:
            if not self._same_origin(exchange):
                exchange.send_json({"error": "cross-origin request refused"}, 403)
            elif self._admitted(exchange) and not self._proxied(exchange):
                self._dispatch(exchange)

            self._report(exchange)
        except BrokenPipeError:
            pass
        except Exception as exc:
            self.logger.error(f"router error on {exchange.method} {exchange.raw_path}:\n{traceback.format_exc()}")
            try:
                exchange.send_json({"error": str(exc)}, 500)
            except Exception as reply_exc:
                self.logger.error(f"could not deliver the 500 reply on {exchange.method} {exchange.raw_path}: {reply_exc}")
