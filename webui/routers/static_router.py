"""Routes serving the console's static assets and result media files."""

from __future__ import annotations

from urllib.parse import unquote

from project_paths    import ProjectPaths
from results_browser  import ResultsBrowser
from routers.dispatch import HttpExchange, RouteTable, SubRouter


class StaticRouter(SubRouter):
    """Serves the console page, its static assets and result media under path guards.

    Attributes:
        paths: Project paths providing the static asset directory.
        results: Results browser used to validate media paths against opened roots.
    """

    def __init__(self, paths: ProjectPaths, results: ResultsBrowser) -> None:
        """Stores the project paths and results browser, then declares the routes."""
        self.paths   = paths
        self.results = results

        super().__init__(("/", "/static", "/resultsmedia"))

    def declare(self, table: RouteTable) -> None:
        """Registers the index, result-media and static asset routes."""
        table.add("GET", "/",             self.index)
        table.add("GET", "/resultsmedia", self.media)
        table.wildcard("GET", "/static/", "", self.asset)

    def index(self, exchange: HttpExchange) -> None:
        """Serves the console index page."""
        self.serve(exchange, "index.html")

    def media(self, exchange: HttpExchange) -> None:
        """Serves one result file, or 404 when it escapes an opened results root."""
        target = self.results.file_path(exchange.text("root"), exchange.text("path"))
        if target is None:
            exchange.not_found()
            return

        exchange.send_file(target, "max-age=60")

    def asset(self, exchange: HttpExchange, relative: str) -> None:
        """Serves the static asset addressed by the wildcard path segment."""
        self.serve(exchange, relative)

    def serve(self, exchange: HttpExchange, relative: str) -> None:
        """Serves a file from the static directory.

        Args:
            exchange: Request being answered.
            relative: Percent-encoded path of the asset relative to the static directory.

        Returns:
            None. Answers 403 when the resolved path escapes the static directory and
            404 when no such file exists.
        """
        target = (self.paths.static_dir / unquote(relative)).resolve()

        if not target.is_relative_to(self.paths.static_dir.resolve()):
            exchange.send_json({"error": "forbidden"}, 403)
            return

        if not target.is_file():
            exchange.not_found()
            return

        exchange.send_file(target, "no-cache")
