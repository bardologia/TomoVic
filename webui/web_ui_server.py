"""Composition root of the TomoVic console HTTP server.

Instantiates every console component, wires them into the request router, and
runs the threaded HTTP server together with the background monitors.
"""

from __future__ import annotations

import os
import socket
import socketserver
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib     import Path

from bridge.dataset_bridge    import DatasetBridge
from bridge.dataset_workspace import DatasetWorkspace
from bridge.import_watch      import TomoVisImportWatch
from config_registry        import ConfigRegistry
from contention_monitor     import ContentionMonitor
from cube_explorer          import CubeExplorer, SliceCollectionMailer, SliceCollector
from dataset_browser        import DatasetBrowser
from job_describer          import JobDescriber
from launch_layout          import LaunchLayout
from repomap_library        import RepoMapLibrary
from notifier               import ExperimentProgressWatcher, JobNotifier
from politeness             import JobPoliteness, JobThrottle
from process_manager        import ProcessManager, ProcessNuke, ServerDetacher
from project_paths          import ProjectPaths
from request_router         import AccessGate, RequestRouter
from resource_watchdog      import ResourceWatchdog
from results_browser        import ResultsBrowser
from run_config_reader      import RunConfigReader
from run_launcher           import RunLauncher
from saved_run_store        import SavedRunStore
from script_catalog         import ScriptCatalog
from script_config_resolver import ScriptConfigResolver
from stream_hub             import StreamHub
from system_monitor         import SystemMonitor
from tomovis.session_store  import TomoVisSessions
from web_logger             import WebLogger

from routers.cube_routers    import CubeRouter, SliceRouter
from routers.launch_routers  import CatalogRouter, JobRouter, RunConfigRouter, SavedRunRouter
from routers.library_routers import ContentLibraryRouter
from routers.results_routers import DatasetRouter, ResultsRouter
from routers.static_router   import StaticRouter
from routers.system_router   import SystemRouter
from routers.tomovis_router  import TomoVisRouter
from routers.workspace_router import WorkspaceRouter


class _Server(ThreadingHTTPServer):
    """Threading HTTP server carrying the request router on the server object."""


    request_queue_size = 64
    daemon_threads     = True


class _UnixServer(socketserver.ThreadingUnixStreamServer):
    """Threading HTTP server on a Unix socket, carrying the request router on the server object."""


    request_queue_size = 64
    daemon_threads     = True


class StaleSocketError(RuntimeError):
    """Raised when another console already answers on the Unix socket path."""


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
        host: Interface the HTTP server binds to, unused when it listens on a Unix socket.
        port: TCP port the HTTP server binds to, unused when it listens on a Unix socket.
        unix_socket: Path of the Unix socket the HTTP server listens on instead of a TCP port, None for TCP.
        gate: Access gate admitting only browsers that hold the access key, None when the console has no key.
        logger: Console logger shared by every component.
        paths: Project path resolver rooted at the repository.
        workspace: Dataset bridge workspace, the folder where TomoVis imports become runs the TomoVic tools read.
        bridge: Dataset bridge sharing one current dataset between TomoVis and the TomoVic tools.
        router: Request router holding the ordered route handlers.
    """


    def __init__(self, host: str = "127.0.0.1", port: int = 8765, root: Path | None = None, access_key: str = "", unix_socket: Path | None = None, workspace: Path | None = None) -> None:
        """Constructs every console component and assembles the request router.

        Args:
            host: Interface to bind the HTTP server to.
            port: TCP port to bind the HTTP server to.
            root: Repository root override; discovered from this file when None.
            access_key: Secret a browser must present before the console answers it, empty to answer every request.
            unix_socket: Path of a Unix socket to listen on instead of host and port, None to listen on TCP.
            workspace: Dataset bridge workspace folder; the project's workspace_dir when None.
        """

        self.host        = host
        self.port        = port
        self.unix_socket = unix_socket
        self.gate        = AccessGate(access_key) if access_key else None
        self.logger      = WebLogger()
        self.paths  = ProjectPaths(root)

        self.resolver       = ScriptConfigResolver(self.paths)
        self.catalog        = ScriptCatalog(self.paths, self.resolver)
        self.layout         = LaunchLayout()
        self.configs        = ConfigRegistry(self.paths)
        self.repomap        = RepoMapLibrary()
        self.notifier       = JobNotifier(self.paths, self.logger)
        self.describer      = JobDescriber(self.paths, self.resolver)
        self.politeness     = JobPoliteness(self.paths, self.logger)
        self.processes      = ProcessManager(self.paths, self.logger, self.notifier, self.describer, self.politeness)
        self.stream_hub     = StreamHub(self.logger)
        self.progress_watch = ExperimentProgressWatcher(self.processes, self.notifier, self.logger)
        self.saved_runs     = SavedRunStore(self.paths, self.logger)
        self.nuke           = ProcessNuke(self.logger)
        self.detacher       = ServerDetacher(self.paths, self.logger)
        self.system         = SystemMonitor(self.paths, self.logger)
        self.throttle       = JobThrottle(self.nuke, self.logger)
        self.contention     = ContentionMonitor(self.paths, self.logger, self.notifier, self.nuke, self.throttle, self.politeness)
        self.watchdog       = ResourceWatchdog(self.processes, self.contention, self.logger, self.notifier, self.paths)
        self.results        = ResultsBrowser(self.logger)
        self.cubes          = CubeExplorer(self.logger)
        self.slices         = SliceCollector(self.cubes, self.logger)
        self.slice_mail     = SliceCollectionMailer(self.slices, self.logger)
        self.datasets       = DatasetBrowser(self.logger)
        self.launcher       = RunLauncher(self.paths, self.logger, self.resolver, self.processes)
        self.run_configs    = RunConfigReader(self.logger)
        self.tomovis        = TomoVisSessions(self.logger)
        self.workspace      = DatasetWorkspace(self.paths.workspace_dir if workspace is None else workspace, self.cubes.roots, self.logger)
        self.bridge         = DatasetBridge(self.workspace, self.cubes, self.slices, self.logger)
        self.import_watch   = TomoVisImportWatch(self.bridge, self.logger)

        self.router = RequestRouter(self.logger, [
            StaticRouter(self.paths, self.results),
            ResultsRouter(self.results),
            DatasetRouter(self.datasets),
            CubeRouter(self.cubes),
            SliceRouter(self.slices, self.slice_mail),
            ContentLibraryRouter("/api/repomap",   self.repomap,   "folders"),
            ContentLibraryRouter("/api/configs",   self.configs,   "groups"),
            CatalogRouter(self.paths, self.catalog, self.resolver, self.layout, self.launcher),
            JobRouter(self.paths, self.processes, self.launcher, self.stream_hub),
            SavedRunRouter(self.paths, self.saved_runs, self.launcher),
            RunConfigRouter(self.run_configs),
            SystemRouter(self.system, self.watchdog, self.contention, self.detacher, self.notifier, self.nuke, self.processes, self.logger),
            TomoVisRouter(self.tomovis, self.import_watch, self.logger),
            WorkspaceRouter(self.bridge),
        ], self.gate)

    def _report_ready(self) -> None:
        """Prints the startup banner with the URL, script count and interpreters."""

        scripts      = self.catalog.list_scripts()
        interpreters = self.paths.discover_interpreters()
        preferred    = self.paths.preferred_interpreter(interpreters)

        self.logger.banner("TomoVic Console", [
            f"URL          unix socket {self.unix_socket}" if self.unix_socket else f"URL          http://{self.host}:{self.port}",
            f"access       {'key required' if self.gate else 'no key'}",
            f"repo root    {self.paths.repo_root}",
            f"scripts      {len(scripts)} entry points",
            f"interpreter  {preferred}",
            f"envs found   {len(interpreters)}",
            f"workspace    {self.workspace.root}",
        ])

    def _bind_unix_socket(self) -> _UnixServer:
        """Binds the HTTP server to the Unix socket, readable and writable by this user only.

        A socket file left behind by a console that died is removed first. The
        umask is narrowed around the bind so the socket is created with mode
        0600 and no other user of the machine can ever connect to it.

        Raises:
            StaleSocketError : If another console already answers on the socket path.
        """
        if self.unix_socket.exists():
            probe = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            try:
                probe.connect(str(self.unix_socket))
                answered = True
            except (ConnectionRefusedError, FileNotFoundError):
                answered = False
            probe.close()

            if answered:
                raise StaleSocketError(f"another console already answers on {self.unix_socket}")
            self.unix_socket.unlink()

        previous = os.umask(0o177)
        try:
            server = _UnixServer(str(self.unix_socket), _Handler)
        finally:
            os.umask(previous)

        return server

    def serve(self) -> None:
        """Serves the console until interrupted, then stops the background workers.

        Starts the contention monitor, the progress watcher and the dataset
        bridge, runs the HTTP server on a worker thread, and blocks in the
        detacher wait loop until a keyboard interrupt or detach request arrives.
        A Unix socket is removed again when the server stops.
        """

        server        = self._bind_unix_socket() if self.unix_socket else _Server((self.host, self.port), _Handler)
        server.router = self.router

        self._report_ready()
        self.contention.start()
        self.watchdog.start()
        self.progress_watch.start()
        self.bridge.start()

        worker = threading.Thread(target=server.serve_forever, name="HttpServer", daemon=True)
        worker.start()

        try:
            self.detacher.wait_loop()
        except KeyboardInterrupt:
            self.logger.warning("shutting down")
        finally:
            server.shutdown()
            server.server_close()
            if self.unix_socket:
                self.unix_socket.unlink(missing_ok=True)
