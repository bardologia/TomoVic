"""Composition root of the TomoVic console HTTP server.

Instantiates every console component, wires them into the request router, and
runs the threaded HTTP server together with the background monitors.
"""

from __future__ import annotations

import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib     import Path

from config_registry        import ConfigRegistry
from cube_explorer          import CubeExplorer, SliceCollector
from dataset_browser        import DatasetBrowser
from equation_library       import EquationLibrary
from flow_library           import FlowLibrary
from job_describer          import JobDescriber
from launch_layout          import LaunchLayout
from pipeline_library       import PipelineLibrary
from repomap_library        import RepoMapLibrary
from notifier               import ExperimentProgressWatcher, JobNotifier
from process_manager        import ProcessManager, ProcessNuke, ServerDetacher
from project_paths          import ProjectPaths
from request_router         import RequestRouter
from results_browser        import ResultsBrowser
from run_config_reader      import RunConfigReader
from run_launcher           import RunLauncher
from saved_run_store        import SavedRunStore
from script_catalog         import ScriptCatalog
from script_config_resolver import ScriptConfigResolver
from system_monitor         import SystemMonitor
from web_logger             import WebLogger

from routers.cube_routers    import CubeRouter, SliceRouter
from routers.launch_routers  import CatalogRouter, JobRouter, RunConfigRouter, SavedRunRouter
from routers.library_routers import ContentLibraryRouter
from routers.results_routers import DatasetRouter, ResultsRouter
from routers.static_router   import StaticRouter
from routers.system_router   import SystemRouter


class _Server(ThreadingHTTPServer):
    """Threading HTTP server carrying the request router on the server object."""


    request_queue_size = 64
    daemon_threads     = True


class _Handler(BaseHTTPRequestHandler):
    """HTTP/1.1 request handler that delegates every method to the router."""


    protocol_version = "HTTP/1.1"

    def do_GET(self) -> None:
        """Routes a GET request through the server's request router."""

        self.server.router.route(self)

    def do_POST(self) -> None:
        """Routes a POST request through the server's request router."""

        self.server.router.route(self)

    def log_message(self, fmt: str, *args) -> None:
        """Suppresses the default per-request access logging."""

        return


class WebUIServer:
    """Builds and runs the console: components, routes and background loops.

    Attributes:
        host: Interface the HTTP server binds to.
        port: TCP port the HTTP server binds to.
        logger: Console logger shared by every component.
        paths: Project path resolver rooted at the repository.
        router: Request router holding the ordered route handlers.
    """


    def __init__(self, host: str = "127.0.0.1", port: int = 8765, root: Path | None = None) -> None:
        """Constructs every console component and assembles the request router.

        Args:
            host: Interface to bind the HTTP server to.
            port: TCP port to bind the HTTP server to.
            root: Repository root override; discovered from this file when None.
        """

        self.host   = host
        self.port   = port
        self.logger = WebLogger()
        self.paths  = ProjectPaths(root)

        self.resolver       = ScriptConfigResolver(self.paths)
        self.catalog        = ScriptCatalog(self.paths, self.resolver)
        self.layout         = LaunchLayout()
        self.configs        = ConfigRegistry(self.paths)
        self.equations      = EquationLibrary()
        self.flows          = FlowLibrary()
        self.pipelines      = PipelineLibrary()
        self.repomap        = RepoMapLibrary()
        self.notifier       = JobNotifier(self.paths, self.logger)
        self.describer      = JobDescriber(self.paths, self.resolver)
        self.processes      = ProcessManager(self.paths, self.logger, self.notifier, self.describer)
        self.progress_watch = ExperimentProgressWatcher(self.processes, self.notifier, self.logger)
        self.saved_runs     = SavedRunStore(self.paths, self.logger)
        self.nuke           = ProcessNuke(self.logger)
        self.detacher       = ServerDetacher(self.paths, self.logger)
        self.system         = SystemMonitor(self.paths, self.logger)
        self.results        = ResultsBrowser(self.logger)
        self.cubes          = CubeExplorer(self.logger)
        self.slices         = SliceCollector(self.cubes, self.logger)
        self.datasets       = DatasetBrowser(self.logger)
        self.launcher       = RunLauncher(self.paths, self.logger, self.resolver, self.processes)
        self.run_configs    = RunConfigReader(self.logger)

        self.router = RequestRouter(self.logger, [
            StaticRouter(self.paths, self.results),
            ResultsRouter(self.results),
            DatasetRouter(self.datasets),
            CubeRouter(self.cubes),
            SliceRouter(self.slices),
            ContentLibraryRouter("/api/equations", self.equations, "groups"),
            ContentLibraryRouter("/api/flows",     self.flows,     "flows"),
            ContentLibraryRouter("/api/pipelines", self.pipelines, "pipelines"),
            ContentLibraryRouter("/api/repomap",   self.repomap,   "folders"),
            ContentLibraryRouter("/api/configs",   self.configs,   "groups"),
            CatalogRouter(self.paths, self.catalog, self.resolver, self.layout, self.launcher),
            JobRouter(self.paths, self.processes, self.launcher),
            SavedRunRouter(self.paths, self.saved_runs, self.launcher),
            RunConfigRouter(self.run_configs),
            SystemRouter(self.system, self.detacher, self.notifier, self.nuke, self.processes),
        ])

    def _report_ready(self) -> None:
        """Prints the startup banner with the URL, script count and interpreters."""

        scripts      = self.catalog.list_scripts()
        interpreters = self.paths.discover_interpreters()
        preferred    = self.paths.preferred_interpreter(interpreters)

        self.logger.banner("TomoVic Console", [
            f"URL          http://{self.host}:{self.port}",
            f"repo root    {self.paths.repo_root}",
            f"scripts      {len(scripts)} entry points",
            f"interpreter  {preferred}",
            f"envs found   {len(interpreters)}",
        ])

    def serve(self) -> None:
        """Serves the console until interrupted, then stops the background workers.

        Starts the progress watcher, runs the HTTP server on a worker thread, and
        blocks in the detacher wait loop until a keyboard interrupt or detach
        request arrives.
        """

        server        = _Server((self.host, self.port), _Handler)
        server.router = self.router

        self._report_ready()
        self.progress_watch.start()

        worker = threading.Thread(target=server.serve_forever, name="HttpServer", daemon=True)
        worker.start()

        try:
            self.detacher.wait_loop()
        except KeyboardInterrupt:
            self.logger.warning("shutting down")
        finally:
            server.shutdown()
            server.server_close()
