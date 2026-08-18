"""Top-level HTTP request router for the web UI server.

Indexes the sub-routers by the URL section each one claims, refuses
cross-origin requests, gives raw-path proxies first refusal, and converts
unhandled exceptions into a 500 reply.
"""

from __future__ import annotations

import traceback
from urllib.parse import urlparse

from routers.dispatch import HttpExchange, RouteConflict, SubRouter
from web_logger       import WebLogger


class RequestRouter:
    """Dispatches HTTP exchanges to the sub-router that owns their URL section.

    Attributes:
        logger: Console logger used for warnings and error reports.
        routers: Sub-routers this router dispatches to.
        sections: Mapping from URL section prefix to its owning sub-router.
    """

    def __init__(self, logger: WebLogger, routers: list[SubRouter]) -> None:
        """Stores the sub-routers and builds the section index.

        Args:
            logger: Console logger for request warnings and router errors.
            routers: Sub-routers whose declared sections must not overlap.

        Raises:
            RouteConflict: If two sub-routers claim the same section.
        """
        self.logger   = logger
        self.routers  = list(routers)
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

    def _report(self, exchange: HttpExchange) -> None:
        """Logs a warning for any exchange that finished with a status of 400 or above."""
        if exchange.status < 400:
            return

        detail = f": {exchange.error}" if exchange.error else ""
        self.logger.warning(f"{exchange.method} {exchange.raw_path} -> {exchange.status}{detail}")

    def route(self, handler) -> None:
        """Routes one request end to end, from origin check to error reporting.

        Cross-origin requests get a 403, raw-path proxies take precedence over
        section dispatch, a dropped client connection is ignored, and any other
        exception is logged and answered with a 500.

        Args:
            handler: The BaseHTTPRequestHandler serving this request.
        """
        exchange = HttpExchange.of(handler)

        try:
            if not self._same_origin(exchange):
                exchange.send_json({"error": "cross-origin request refused"}, 403)
            elif not self._proxied(exchange):
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
