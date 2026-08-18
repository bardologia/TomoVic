"""HTTP request/response plumbing and route dispatch shared by every sub-router.

Holds the per-request exchange object (query parsing, JSON body reading, typed
response senders), the route table with exact and wildcard entries, and the
SubRouter base class each console API section derives from.
"""

from __future__ import annotations

import json
import math
import mimetypes
from pathlib      import Path
from urllib.parse import parse_qs, urlparse


class HttpExchange:
    """One HTTP request together with the helpers used to answer it.

    Attributes:
        handler: The BaseHTTPRequestHandler serving this request.
        method: HTTP verb of the request.
        raw_path: Request path exactly as received, query string included.
        path: Normalised path with the trailing slash stripped, used for routing.
        query: Parsed query string as name to list-of-values.
        body: Decoded JSON request body, empty until read_body runs.
        status: HTTP status of the response once sent, 0 before that.
        error: Error message carried by a JSON response, empty when there is none.
    """

    def __init__(self, handler, method: str, raw_path: str, path: str, query: dict) -> None:
        """Stores the handler and the parsed request line for the response helpers."""
        self.handler  = handler
        self.method   = method
        self.raw_path = raw_path
        self.path     = path
        self.query    = query
        self.body     = {}
        self.status   = 0
        self.error    = ""

    @classmethod
    def of(cls, handler) -> HttpExchange:
        """Builds an exchange from a request handler by parsing its path and query."""
        parsed = urlparse(handler.path)
        return cls(handler, handler.command, parsed.path, parsed.path.rstrip("/") or "/", parse_qs(parsed.query))

    @classmethod
    def jsonsafe(cls, value):
        """Returns `value` with non-finite floats replaced by None, recursing into containers."""
        if isinstance(value, dict):
            return {key: cls.jsonsafe(child) for key, child in value.items()}
        if isinstance(value, list):
            return [cls.jsonsafe(child) for child in value]
        if isinstance(value, float) and not math.isfinite(value):
            return None
        return value

    def text(self, name: str, default: str = "") -> str:
        """Returns the first value of query parameter `name`, or `default`."""
        return (self.query.get(name) or [default])[0]

    def texts(self, name: str) -> list[str]:
        """Returns every value of the repeated query parameter `name`."""
        return self.query.get(name) or []

    def integer(self, name: str, default: str = "0") -> int:
        """Returns query parameter `name` parsed as an integer."""
        return int(self.text(name, default))

    def number(self, name: str, default: str = "0") -> float:
        """Returns query parameter `name` parsed as a float."""
        return float(self.text(name, default))

    def optional_number(self, name: str) -> float | None:
        """Returns query parameter `name` as a float, or None when it is absent."""
        raw = self.text(name)
        return float(raw) if raw else None

    def header(self, name: str, default: str = "") -> str:
        """Returns request header `name`, or `default` when it is absent."""
        return self.handler.headers.get(name) or default

    def read_body(self) -> None:
        """Reads Content-Length bytes from the request and decodes them as the JSON body."""
        length = int(self.handler.headers.get("Content-Length", 0) or 0)
        if length <= 0:
            self.body = {}
            return

        self.body = json.loads(self.handler.rfile.read(length).decode("utf-8"))

    def send_json(self, payload: dict, status: int = 200) -> None:
        """Sends `payload` as a JSON response under `status`, recording status and error."""
        data = json.dumps(self.jsonsafe(payload)).encode("utf-8")

        self.status = status
        self.error  = str(payload.get("error", ""))

        self.handler.send_response(status)
        self.handler.send_header("Content-Type", "application/json")
        self.handler.send_header("Content-Length", str(len(data)))
        self.handler.end_headers()
        self.handler.wfile.write(data)

    def send_result(self, result: dict, error: int = 400) -> None:
        """Sends a result payload as 200 when its `ok` flag is set, `error` otherwise."""
        self.send_json(result, 200 if result.get("ok") else error)

    def not_found(self) -> None:
        """Sends a 404 JSON response."""
        self.send_json({"error": "not found"}, 404)

    def send_png(self, png: bytes | None) -> None:
        """Sends PNG bytes uncached, or 404 when the renderer produced nothing."""
        if png is None:
            self.not_found()
            return

        self.send_payload("image/png", png, "no-cache")

    def send_bytes(self, blob: bytes | None) -> None:
        """Sends a binary blob uncached, or 404 when the producer returned nothing."""
        if blob is None:
            self.not_found()
            return

        self.send_payload("application/octet-stream", blob, "no-cache")

    def send_file(self, target: Path, cache: str) -> None:
        """Sends the file at `target` with a guessed content type and `cache` header."""
        data = target.read_bytes()
        self.send_payload(mimetypes.guess_type(str(target))[0] or "application/octet-stream", data, cache)

    def send_payload(self, content_type: str, data: bytes, cache: str) -> None:
        """Writes a 200 response carrying `data` under the given content type and cache policy."""
        self.status = 200

        self.handler.send_response(200)
        self.handler.send_header("Content-Type", content_type)
        self.handler.send_header("Content-Length", str(len(data)))
        self.handler.send_header("Cache-Control", cache)
        self.handler.end_headers()
        self.handler.wfile.write(data)


class RouteConflict(RuntimeError):
    """Raised when the same method and path are declared by two routes."""
    pass


class RouteTable:
    """Maps method and path to the action that answers the request.

    Attributes:
        exact: Actions keyed by the exact (method, path) pair.
        wildcards: Prefix/suffix entries whose middle segment is passed to the action.
    """

    def __init__(self) -> None:
        """Creates an empty exact-route map and wildcard list."""
        self.exact     = {}
        self.wildcards = []

    def add(self, method: str, path: str, action) -> None:
        """Registers an exact route.

        Args:
            method: HTTP verb the route answers.
            path: Normalised request path.
            action: Callable taking the exchange.

        Raises:
            RouteConflict: If the same method and path are already registered.
        """
        if (method, path) in self.exact:
            raise RouteConflict(f"{method} {path} is declared twice")

        self.exact[(method, path)] = action

    def wildcard(self, method: str, prefix: str, suffix: str, action) -> None:
        """Registers a route matching `prefix`<key>`suffix`, passing the key to the action.

        Args:
            method: HTTP verb the route answers.
            prefix: Required leading part of the path.
            suffix: Required trailing part of the path, possibly empty.
            action: Callable taking the exchange and the extracted key.

        Raises:
            RouteConflict: If the same method, prefix and suffix are already registered.
        """
        if any(entry[:3] == (method, prefix, suffix) for entry in self.wildcards):
            raise RouteConflict(f"{method} {prefix}*{suffix} is declared twice")

        self.wildcards.append((method, prefix, suffix, action))

    def action_for(self, method: str, path: str) -> tuple:
        """Returns the matching action and wildcard key, or (None, None) when nothing matches."""
        action = self.exact.get((method, path))
        if action is not None:
            return action, None

        for candidate, prefix, suffix, action in self.wildcards:
            if candidate != method or not path.startswith(prefix) or not path.endswith(suffix):
                continue

            return action, path[len(prefix):len(path) - len(suffix)]

        return None, None

    def dispatch(self, exchange: HttpExchange) -> bool:
        """Runs the action matching the exchange, returning whether one was found."""
        action, key = self.action_for(exchange.method, exchange.path)
        if action is None:
            return False

        if key is None:
            action(exchange)
        else:
            action(exchange, key)

        return True


class SubRouter:
    """Base class of every console API section, owning its own route table.

    Attributes:
        sections: Path prefixes this router answers under after normalisation.
        raw_sections: Path prefixes handled from the unparsed request path, used for
            proxy-style passthrough routes.
        table: Route table filled in by `declare`.
    """

    def __init__(self, sections: tuple, raw_sections: tuple = ()) -> None:
        """Records the claimed path prefixes and builds the route table via `declare`."""
        self.sections     = sections
        self.raw_sections = raw_sections
        self.table        = RouteTable()

        self.declare(self.table)

    def declare(self, table: RouteTable) -> None:
        """Registers this router's routes on `table`.

        Raises:
            NotImplementedError: Always, unless a subclass overrides it.
        """
        raise NotImplementedError

    def claims_raw(self, raw_path: str) -> bool:
        """Returns whether the unparsed request path falls under a raw section."""
        return bool(self.raw_sections) and raw_path.startswith(self.raw_sections)

    def handle_raw(self, exchange: HttpExchange) -> None:
        """Answers a raw-section request.

        Raises:
            NotImplementedError: Always, unless a subclass declaring raw sections overrides it.
        """
        raise NotImplementedError

    def handle(self, exchange: HttpExchange) -> bool:
        """Dispatches the exchange through this router's table, returning whether it matched."""
        return self.table.dispatch(exchange)
