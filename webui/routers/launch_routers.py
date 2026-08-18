"""API routes for browsing entry points, launching runs and replaying saved runs.

Covers the project/script catalog with resolved configuration layouts, the job
list with log streaming and GPU-pool control across local and cluster backends,
and the saved-run store.
"""

from __future__ import annotations

import json
import queue

from backbone_model_library import BackboneModelLibrary
from launch_layout          import LaunchLayout, LayoutError
from process_manager        import ProcessManager
from project_paths          import ProjectPaths
from routers.dispatch       import HttpExchange, RouteTable, SubRouter
from run_config_reader      import RunConfigReader
from run_launcher           import RunLauncher
from saved_run_store        import SavedRunStore
from script_catalog         import ScriptCatalog
from script_config_resolver import ScriptConfigResolver
from terrabyte_console      import TerrabyteJobManager


class CatalogRouter(SubRouter):
    """Serves the project card, the entry-point catalog and each entry's config layout.

    Attributes:
        paths: Project paths used to check that an entry point exists.
        catalog: Script catalog holding the entry-point metadata.
        resolver: Resolver that imports each entry's config dataclass into leaves.
        layout: Layout builder turning config leaves into console panels.
        models: Backbone model library, used for the project model count.
        launcher: Run launcher providing the preferred interpreter per entry.
    """

    PROJECT = {
        "name"        : "DLR-TomoSAR",
        "tagline"     : "Neural SAR tomography control console",
        "description" : "Supervised deep learning that replaces per-pixel iterative optimisation in SAR tomographic parameter estimation, inferring all 3K Gaussian-mixture parameters of the elevation spectrum in one forward pass.",
        "pipelines"   : ["Processing", "Parameter Extraction", "Dataset", "Training", "Inference", "Tuning"],
    }

    def __init__(self, paths: ProjectPaths, catalog: ScriptCatalog, resolver: ScriptConfigResolver, layout: LaunchLayout, models: BackboneModelLibrary, launcher: RunLauncher) -> None:
        """Stores the catalog collaborators and declares the routes."""
        self.paths    = paths
        self.catalog  = catalog
        self.resolver = resolver
        self.layout   = layout
        self.models   = models
        self.launcher = launcher

        super().__init__(("/api/project", "/api/scripts"))

    def declare(self, table: RouteTable) -> None:
        """Registers the project card, script listing, detail and config routes."""
        table.add("GET", "/api/project", self.project)
        table.add("GET", "/api/scripts", self.scripts)
        table.wildcard("GET", "/api/scripts/", "/config", self.script_config)
        table.wildcard("GET", "/api/scripts/", "",        self.script_detail)

    def project(self, exchange: HttpExchange) -> None:
        """Answers with the project card: models, repo root, interpreters and counts."""
        interpreters = self.paths.discover_interpreters()
        model_names  = [model["name"] for family in self.models.collect() for model in family["models"]]

        exchange.send_json({
            **self.PROJECT,
            "models"       : model_names,
            "repo_root"    : str(self.paths.repo_root),
            "interpreters" : interpreters,
            "preferred"    : self.paths.preferred_interpreter(interpreters),
            "counts"       : {
                "scripts"   : len(self.catalog.list_scripts()),
                "models"    : len(model_names),
                "pipelines" : len(self.PROJECT["pipelines"]),
            },
        })

    def scripts(self, exchange: HttpExchange) -> None:
        """Answers with the catalog of available entry points."""
        exchange.send_json({"scripts": self.catalog.list_scripts()})

    def script_config(self, exchange: HttpExchange, key: str) -> None:
        """Answers with one entry point's resolved config leaves and console layout.

        Args:
            exchange: Request being answered.
            key: Entry-point key taken from the wildcard path segment.

        Returns:
            None. Answers 404 for an unknown entry point and a failed result when the
            layout cannot be built from the resolved leaves.
        """
        if not self.paths.has_script(key):
            exchange.send_json({"error": f"unknown script '{key}'"}, 404)
            return

        result = self.resolver.resolve(key, self.launcher.preferred_interpreter(key))
        if result.get("ok"):
            try:
                result = {**result, "layout": self.layout.build(key, result["leaves"])}
            except LayoutError as exc:
                result = {"ok": False, "error": str(exc)}

        exchange.send_result(result)

    def script_detail(self, exchange: HttpExchange, key: str) -> None:
        """Answers with one entry point's metadata and source, or 404 when unknown."""
        if not self.paths.has_script(key):
            exchange.send_json({"error": f"unknown script '{key}'"}, 404)
            return

        detail = self.catalog.get_script(key)
        if detail is None:
            exchange.not_found()
            return

        exchange.send_json(detail)


class RunConfigRouter(SubRouter):
    """Serves the resolved configs of finished runs for the copy-from-run control.

    Attributes:
        reader: Reader locating and rendering resolved config files in run directories.
    """

    def __init__(self, reader: RunConfigReader) -> None:
        """Stores the run-config reader and declares the routes."""
        self.reader = reader

        super().__init__(("/api/run-config",))

    def declare(self, table: RouteTable) -> None:
        """Registers the copyable-run listing and the per-run config route."""
        table.add("GET", "/api/run-config/runs", self.runs)
        table.add("GET", "/api/run-config",      self.config)

    def runs(self, exchange: HttpExchange) -> None:
        """Answers with the runs below `base` that hold a resolved config file."""
        exchange.send_result(self.reader.list_runs(exchange.text("base")))

    def config(self, exchange: HttpExchange) -> None:
        """Answers with the rendered resolved config of the run directory in `path`."""
        exchange.send_result(self.reader.read(exchange.text("path")))


class JobRouter(SubRouter):
    """Serves the job list and the per-job control endpoints of both job backends.

    Local jobs are handled by the process manager and cluster jobs by the Terrabyte
    console, selected from the job id prefix.

    Attributes:
        paths: Project paths used to validate entry-point keys.
        processes: Local process manager.
        launcher: Run launcher executing and queueing local runs.
        cluster: Terrabyte job manager owning the cluster jobs.
    """

    def __init__(self, paths: ProjectPaths, processes: ProcessManager, launcher: RunLauncher, cluster: TerrabyteJobManager) -> None:
        """Stores the job backends and launcher, then declares the routes."""
        self.paths     = paths
        self.processes = processes
        self.launcher  = launcher
        self.cluster   = cluster

        super().__init__(("/api/run", "/api/jobs"))

    def declare(self, table: RouteTable) -> None:
        """Registers the job listing, launch and per-job control routes."""
        table.add("GET",  "/api/jobs", self.jobs)
        table.add("POST", "/api/run",  self.run)
        table.wildcard("GET",  "/api/jobs/", "/gpus",        self.gpu_pool)
        table.wildcard("GET",  "/api/jobs/", "/progress",    self.progress)
        table.wildcard("GET",  "/api/jobs/", "/log",         self.log)
        table.wildcard("GET",  "/api/jobs/", "/stream",      self.stream)
        table.wildcard("POST", "/api/jobs/", "/stop",        self.stop)
        table.wildcard("POST", "/api/jobs/", "/gpus",        self.set_gpus)
        table.wildcard("POST", "/api/jobs/", "/tensorboard", self.tensorboard_bridge)

    def jobs(self, exchange: HttpExchange) -> None:
        """Adopts orphaned processes and answers with local and cluster jobs, newest first."""
        self.processes.adopt_orphans()

        merged = self.processes.list_jobs() + self.cluster.list_jobs()
        merged.sort(key=lambda record: record["started"], reverse=True)

        exchange.send_json({"jobs": merged})

    def run(self, exchange: HttpExchange) -> None:
        """Launches or queues the entry point described in the request body."""
        body = exchange.body
        key  = body.get("script_key", "")

        if not self.paths.has_script(key):
            exchange.send_json({"error": f"unknown script '{key}'"}, 404)
            return

        interpreter = body.get("interpreter") or self.launcher.preferred_interpreter(key)
        result      = self.launcher.execute(key, interpreter, body.get("overrides", {}), body.get("follow_up") or None, bool(body.get("detach")), bool(body.get("queue")))
        exchange.send_result(result)

    def gpu_pool(self, exchange: HttpExchange, job_id: str) -> None:
        """Answers with the GPU pool currently assigned to one job."""
        exchange.send_result(self._backend(job_id).gpu_pool(job_id))

    def progress(self, exchange: HttpExchange, job_id: str) -> None:
        """Answers with the progress and ETA of one job."""
        exchange.send_result(self._backend(job_id).progress(job_id))

    def log(self, exchange: HttpExchange, job_id: str) -> None:
        """Answers with one job's log, or the log of the requested sub-unit."""
        unit = self._unit_index(exchange)
        if unit == "invalid":
            return

        exchange.send_result(self._backend(job_id).job_log(job_id, unit))

    def stream(self, exchange: HttpExchange, job_id: str) -> None:
        """Streams one job's log as server-sent events until it ends or the client leaves.

        Args:
            exchange: Request being answered.
            job_id: Job identifier taken from the wildcard path segment.

        Returns:
            None. Answers 404 when the job or the requested sub-unit has no open stream.
        """
        unit = self._unit_index(exchange)
        if unit == "invalid":
            return

        backend = self._backend(job_id)

        if unit is not None:
            opened = backend.unit_stream(job_id, unit)
            if not opened.get("ok"):
                exchange.send_json(opened, 404)
                return
            self._pump_stream(exchange, opened["stream"], opened["stop"])
            return

        stream = backend.get_stream(job_id)
        if stream is None:
            exchange.send_json({"error": "unknown job"}, 404)
            return

        self._pump_stream(exchange, stream, None)

    def _unit_index(self, exchange: HttpExchange) -> int | str | None:
        """Returns the requested sub-unit index, None when absent, "invalid" after answering 400."""
        raw = exchange.text("unit")
        if not raw:
            return None

        try:
            return int(raw)
        except ValueError:
            exchange.send_json({"ok": False, "error": f"invalid unit index '{raw}'"}, 400)
            return "invalid"

    def _pump_stream(self, exchange: HttpExchange, stream, stop) -> None:
        """Forwards events from a log stream to the client as server-sent events.

        Sends a keepalive comment every 15 seconds of silence, stops on the stream's end
        event or a broken connection, and always unsubscribes and sets `stop`.

        Args:
            exchange: Request being answered, carrying the raw handler.
            stream: Event stream to subscribe to.
            stop: Event set on teardown to release a sub-unit tail, or None.
        """
        handler = exchange.handler
        handler.send_response(200)
        handler.send_header("Content-Type", "text/event-stream")
        handler.send_header("Cache-Control", "no-cache")
        handler.send_header("Connection", "keep-alive")
        handler.end_headers()

        sub = stream.subscribe()
        try:
            while True:
                try:
                    event = sub.get(timeout=15)
                except queue.Empty:
                    handler.wfile.write(b": keepalive\n\n")
                    handler.wfile.flush()
                    continue

                payload = json.dumps(event)
                handler.wfile.write(f"data: {payload}\n\n".encode("utf-8"))
                handler.wfile.flush()

                if event.get("type") == "end":
                    break
        except (BrokenPipeError, ConnectionResetError):
            pass
        finally:
            stream.unsubscribe(sub)
            if stop is not None:
                stop.set()

    def stop(self, exchange: HttpExchange, job_id: str) -> None:
        """Stops the job addressed by the wildcard id."""
        exchange.send_result(self._backend(job_id).stop(job_id))

    def set_gpus(self, exchange: HttpExchange, job_id: str) -> None:
        """Resizes one job's GPU pool, optionally parking it off the GPUs."""
        exchange.send_result(self._backend(job_id).set_gpus(job_id, exchange.body.get("gpus"), park=bool(exchange.body.get("park"))))

    def _backend(self, job_id: str):
        """Returns the cluster manager for Terrabyte job ids and the process manager otherwise."""
        return self.cluster if job_id.startswith(TerrabyteJobManager.PREFIX) else self.processes

    def tensorboard_bridge(self, exchange: HttpExchange, job_id: str) -> None:
        """Opens a TensorBoard bridge onto a cluster job, refusing local job ids."""
        if not job_id.startswith(TerrabyteJobManager.PREFIX):
            exchange.send_json({"ok": False, "error": "local training runs start tensorboard automatically; this bridge mirrors terrabyte runs only"}, 400)
            return

        exchange.send_result(self.cluster.tensorboard_bridge(job_id, self.launcher.preferred_interpreter("train_backbone")))


class SavedRunRouter(SubRouter):
    """Serves the saved-run store: listing, saving, relaunching and deleting entries.

    Attributes:
        paths: Project paths used to validate entry-point keys.
        saved_runs: Store holding the saved run definitions.
        launcher: Run launcher validating interpreters and executing relaunches.
    """

    def __init__(self, paths: ProjectPaths, saved_runs: SavedRunStore, launcher: RunLauncher) -> None:
        """Stores the saved-run store and launcher, then declares the routes."""
        self.paths      = paths
        self.saved_runs = saved_runs
        self.launcher   = launcher

        super().__init__(("/api/saved-runs",))

    def declare(self, table: RouteTable) -> None:
        """Registers the saved-run listing, save, launch and delete routes."""
        table.add("GET",  "/api/saved-runs", self.listing)
        table.add("POST", "/api/saved-runs", self.save)
        table.wildcard("POST", "/api/saved-runs/", "/run",    self.launch)
        table.wildcard("POST", "/api/saved-runs/", "/delete", self.remove)

    def listing(self, exchange: HttpExchange) -> None:
        """Answers with every saved run, newest first."""
        exchange.send_json(self.saved_runs.list())

    def save(self, exchange: HttpExchange) -> None:
        """Saves the run definition in the body, filling in the preferred interpreter."""
        body        = exchange.body
        key         = body.get("script_key", "")
        interpreter = body.get("interpreter", "")

        if not interpreter and self.paths.has_script(key):
            interpreter = self.launcher.preferred_interpreter(key)

        error = self.launcher.interpreter_error(interpreter)
        if error:
            exchange.send_json({"ok": False, "error": error}, 400)
            return

        exchange.send_result(self.saved_runs.save({**body, "interpreter": interpreter}))

    def launch(self, exchange: HttpExchange, saved_id: str) -> None:
        """Relaunches a saved run, optionally through the queue.

        Args:
            exchange: Request being answered, its body carrying the `queue` flag.
            saved_id: Identifier of the saved run, from the wildcard path segment.

        Returns:
            None. Answers 404 when the entry is unknown or points at entry points that
            no longer exist.
        """
        entry = self.saved_runs.get(saved_id)
        if entry is None:
            exchange.send_json({"ok": False, "error": "saved run not found"}, 404)
            return

        missing = [key for key in (entry["script"], entry["follow_up"]) if key and not self.paths.has_script(key)]
        if missing:
            exchange.send_json({"ok": False, "error": f"saved run points at removed entry point(s): {', '.join(missing)}"}, 404)
            return

        result = self.launcher.execute(entry["script"], entry["interpreter"], entry["overrides"], entry["follow_up"], entry["detach"], bool(exchange.body.get("queue")))
        exchange.send_result(result)

    def remove(self, exchange: HttpExchange, saved_id: str) -> None:
        """Deletes the saved run addressed by the wildcard id."""
        exchange.send_result(self.saved_runs.delete(saved_id))
