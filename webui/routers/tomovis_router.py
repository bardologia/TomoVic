"""API routes of the TomoVis page (/api/tomovis).

Opens and closes page sessions, applies window events and figure operations
and answers with TVE1 envelopes, serves the colour tables, the prepared 3D
volume, the session metadata and directory listings, writes exported files
on the server, records browser-side prints, and runs the two standalone
scripts' server halves. The API is documented in webui/tomovis/README.md.
"""

from __future__ import annotations

import re

from routers.dispatch         import HttpExchange, RouteTable, SubRouter
from tomovis.directory_lister import DirectoryLister
from tomovis.envelope         import TomoVisEnvelope
from tomovis.events           import TomoVisEventError
from tomovis.exporters        import ExportWriter, Hdf5PlotExporter, MatplotlibPlotExporter
from tomovis.figure_host      import TomoVisFigure
from tomovis.scripts          import SlicerMatplotlibScript, VolumeRenderingScript
from tomovis.session_store    import TomoVisSessionEntry, TomoVisSessions
from tomovis.tools            import TomoVisTools
from tomovis.window           import TomoVisConsole
from web_logger               import WebLogger


class TomoVisRouter(SubRouter):
    """Routes /api/tomovis onto the TomoVis page sessions.

    Attributes:
        sessions          : Page session store.
        logger            : Console logger.
        envelope          : Envelope packer.
        lister            : Directory lister for the file dialog.
        writer            : Writer of exported files.
        hdf5              : HDF5 plot exporter.
        matplotlib_export : Matplotlib Window exporter.
        tools             : TomoVis tables.
        EXPORT_FIGURE     : Pattern of Matplotlib Window figure ids, one per export.
    """

    EXPORT_FIGURE = re.compile(r"export:[1-9][0-9]{0,8}")

    def __init__(self, sessions: TomoVisSessions, logger: WebLogger) -> None:
        """Stores the session store and declares the routes.

        Args:
            sessions : Page session store.
            logger   : Console logger.
        """

        self.sessions          = sessions
        self.logger            = logger
        self.envelope          = TomoVisEnvelope()
        self.lister            = DirectoryLister()
        self.writer            = ExportWriter()
        self.hdf5              = Hdf5PlotExporter()
        self.matplotlib_export = MatplotlibPlotExporter()
        self.tools             = TomoVisTools()

        super().__init__(("/api/tomovis",))

    def declare(self, table: RouteTable) -> None:
        """Registers the /api/tomovis routes."""

        table.add("POST", "/api/tomovis/session",       self.session)
        table.add("POST", "/api/tomovis/close",         self.close)
        table.add("POST", "/api/tomovis/event",         self.event)
        table.add("POST", "/api/tomovis/figure",        self.figure)
        table.add("GET",  "/api/tomovis/tables",        self.tables)
        table.add("GET",  "/api/tomovis/volume",        self.volume)
        table.add("GET",  "/api/tomovis/metadata",      self.metadata)
        table.add("GET",  "/api/tomovis/fs",            self.fs)
        table.add("POST", "/api/tomovis/write",         self.write)
        table.add("POST", "/api/tomovis/export_hdf5",   self.export_hdf5)
        table.add("POST", "/api/tomovis/log",           self.log)
        table.add("POST", "/api/tomovis/script/slicer", self.script_slicer)
        table.add("GET",  "/api/tomovis/script/volume", self.script_volume)

    def handle(self, exchange: HttpExchange) -> bool:
        """Refuses POST bodies that are not JSON objects with 400, then dispatches through the route table."""

        if exchange.method == "POST" and not isinstance(exchange.body, dict):
            exchange.send_json({"error": "the request body must be a JSON object"}, 400)
            return True
        return super().handle(exchange)

    def entry(self, exchange: HttpExchange, sid, kind: str | None = None) -> TomoVisSessionEntry | None:
        """Looks a session up, answering 404 (unknown) or 400 (wrong kind) when it fails.

        Args:
            exchange : The request.
            sid      : Session id from the body or the query.
            kind     : Required session kind, None for any.

        Returns:
            The entry, or None once an error was sent.
        """

        if not isinstance(sid, str):
            exchange.send_json({"error": "missing session id"}, 400)
            return None
        try:
            entry = self.sessions.get(sid)
        except KeyError:
            exchange.send_json({"error": "unknown TomoVis session"}, 404)
            return None
        if kind is not None and entry.kind != kind:
            exchange.send_json({"error": f"this request needs a {kind} session"}, 400)
            return None
        return entry

    def session(self, exchange: HttpExchange) -> None:
        """Opens a page session: a fresh window, or a scripts session."""

        kind   = exchange.body.get("kind")
        webgl2 = exchange.body.get("webgl2", True)
        if kind not in TomoVisSessions.KINDS or not isinstance(webgl2, bool):
            exchange.send_json({"error": "kind must be 'window' or 'scripts' and webgl2 a boolean"}, 400)
            return

        entry = self.sessions.create(kind, webgl2)
        with entry.lock:
            snapshot = entry.window.snapshot() if entry.window is not None else None
        exchange.send_bytes(self.envelope.pack({"sid": entry.sid, "snapshot": snapshot}, {}))

    def close(self, exchange: HttpExchange) -> None:
        """Closes a page session (sendBeacon on pagehide); unknown ids are fine."""

        sid = exchange.body.get("sid")
        if isinstance(sid, str):
            self.sessions.close(sid)
        exchange.send_json({"ok": True})

    def event(self, exchange: HttpExchange) -> None:
        """Applies one window event and answers with the snapshot, changed images, figure messages and dialogs."""

        entry = self.entry(exchange, exchange.body.get("sid"), "window")
        if entry is None:
            return

        with entry.lock:
            window = entry.window
            try:
                window.handle(exchange.body.get("event"))
            except TomoVisEventError as error:
                exchange.send_json({"error": str(error)}, error.status)
                return

            output = window.drain()
            blobs  = {f"view:{name}": image for name, image in output.views.items()}
            blobs.update(output.frames)
            header = {
                "seq"         : exchange.body.get("seq"),
                "snapshot"    : window.snapshot(),
                "views"       : {name: f"view:{name}" for name in output.views},
                "figures"     : output.figures,
                "dialogs"     : output.dialogs,
                "printed"     : output.printed,
                "slot_errors" : output.slot_errors,
            }
            exchange.send_bytes(self.envelope.pack(header, blobs))

    def figureOf(self, entry: TomoVisSessionEntry, name, op: str) -> TomoVisFigure:
        """Returns the figure an op addresses, creating a Matplotlib Window figure for export_matplotlib.

        Every Matplotlib Window export opens its own window, as pyqtgraph's
        MatplotlibExporter does, so the browser names each one ``export:<n>``.

        Raises:
            KeyError : If the session has no such figure.
        """

        if op == "export_matplotlib" and isinstance(name, str) and self.EXPORT_FIGURE.fullmatch(name):
            entry.figures[name] = TomoVisFigure(name, self.logger)
        return entry.figure(name)

    def figure(self, exchange: HttpExchange) -> None:
        """Runs one figure operation and answers with the figure's messages, frames, result and dialogs."""

        body  = exchange.body
        entry = self.entry(exchange, body.get("sid"))
        if entry is None:
            return

        name = body.get("figure")
        op   = body.get("op")
        with entry.lock:
            try:
                figure = self.figureOf(entry, name, op)
            except (KeyError, TypeError):
                exchange.send_json({"error": f"unknown figure '{name}'"}, 404)
                return
            try:
                if op == "export_matplotlib":
                    if not isinstance(body.get("plot"), dict):
                        raise TomoVisEventError("export_matplotlib needs a plot")
                    self.matplotlib_export.export(figure, body["plot"])
                    result = None
                elif op == "export_close":
                    if not self.EXPORT_FIGURE.fullmatch(name):
                        raise TomoVisEventError("export_close closes Matplotlib Window figures only")
                    del entry.figures[name]
                    exchange.send_json({"ok": True})
                    return
                else:
                    result = figure.handle(op, body)
            except TomoVisEventError as error:
                exchange.send_json({"error": str(error)}, error.status)
                return

            messages, frames = figure.drain(f"figure:{name}:")
            header = {"seq": body.get("seq"), "figure": name, "messages": messages, "result": result, "dialogs": figure.drainDialogs()}
            exchange.send_bytes(self.envelope.pack(header, frames))

    def tables(self, exchange: HttpExchange) -> None:
        """Answers with the 19 colour tables and the 71 Plot-tab colour map names."""

        names, tables = self.tools.colortables()
        exchange.send_json({
            "colortables"    : {"names": list(names), "tables": [table.tolist() for table in tables], "default": 9, "blue_red_yellow": 4},
            "plot_colormaps" : {"names": list(self.tools.PLOT_COLORMAPS), "default": "jet"},
        })

    def volume(self, exchange: HttpExchange) -> None:
        """Answers with the prepared 3D volume of a window, 404 for a stale serial."""

        entry = self.entry(exchange, exchange.text("sid"), "window")
        if entry is None:
            return
        try:
            serial = exchange.integer("serial", "-1")
        except ValueError:
            exchange.send_json({"error": "serial must be an integer"}, 400)
            return

        with entry.lock:
            payload = entry.window.volumePayload(serial)
            if payload is None:
                exchange.send_json({"error": "no volume with this serial"}, 404)
                return
            header, data = payload
            exchange.send_bytes(self.envelope.pack(header, {"volume": data}))

    def metadata(self, exchange: HttpExchange) -> None:
        """Answers with getCurrentMetadata() of a window."""

        entry = self.entry(exchange, exchange.text("sid"), "window")
        if entry is None:
            return
        with entry.lock:
            exchange.send_json(entry.window.metadata())

    def fs(self, exchange: HttpExchange) -> None:
        """Answers with one directory listing for the file dialog."""

        exchange.send_result(self.lister.list(exchange.text("path"), exchange.texts("pattern")))

    def write(self, exchange: HttpExchange) -> None:
        """Writes an exported image (PNG body) or text file (raw body) on the server."""

        entry = self.entry(exchange, exchange.text("sid"))
        if entry is None:
            return
        path = exchange.text("path")
        kind = exchange.text("kind")
        if kind not in ("image", "bytes") or not exchange.blob:
            exchange.send_json({"ok": False, "error": "kind must be 'image' or 'bytes' with a binary body"}, 400)
            return
        try:
            target = self.writer.writeImage(path, exchange.blob) if kind == "image" else self.writer.writeBytes(path, exchange.blob)
        except TomoVisEventError as error:
            self.logger.warning(f"TomoVis: export not written: {error}")
            exchange.send_json({"ok": False, "error": str(error)}, 400)
            return
        exchange.send_json({"ok": True, "path": str(target)})

    def export_hdf5(self, exchange: HttpExchange) -> None:
        """Appends the ImageView ROI plot's curves to an HDF5 file (pyqtgraph's HDF5 exporter)."""

        body  = exchange.body
        entry = self.entry(exchange, body.get("sid"))
        if entry is None:
            return
        curves = body.get("curves")
        if not isinstance(curves, list) or not all(isinstance(curve, dict) and isinstance(curve.get("x"), list) and isinstance(curve.get("y"), list) for curve in curves):
            exchange.send_json({"ok": False, "error": "curves must be a list of {x, y} lists"}, 400)
            return
        if not isinstance(body.get("name"), str) or not isinstance(body.get("path"), str):
            exchange.send_json({"ok": False, "error": "path and name must be strings"}, 400)
            return
        try:
            target = self.writer.target(body["path"])
            self.hdf5.export(str(target), body["name"], body.get("column_mode"), curves)
        except TomoVisEventError as error:
            exchange.send_json({"ok": False, "error": str(error)}, 400)
            return
        exchange.send_json({"ok": True, "path": str(target)})

    def log(self, exchange: HttpExchange) -> None:
        """Logs lines the browser printed (3D tab, volume script) with the TomoVis prefix, vispy's error lines at error level."""

        entry = self.entry(exchange, exchange.body.get("sid"))
        if entry is None:
            return
        lines = exchange.body.get("lines")
        if not isinstance(lines, list) or not all(isinstance(line, str) for line in lines):
            exchange.send_json({"error": "lines must be a list of strings"}, 400)
            return
        TomoVisConsole(self.logger).relay(lines)
        exchange.send_json({"ok": True})

    def script_slicer(self, exchange: HttpExchange) -> None:
        """Loads a file into the SlicerMatplotlib script figure."""

        body  = exchange.body
        entry = self.entry(exchange, body.get("sid"), "scripts")
        if entry is None:
            return
        path = body.get("path")
        if not isinstance(path, str):
            exchange.send_json({"error": "path must be a string"}, 400)
            return

        with entry.lock:
            try:
                figure = SlicerMatplotlibScript(self.logger).load(path)
            except (OSError, ValueError, KeyError) as error:
                exchange.send_json({"error": str(error)}, 400)
                return
            entry.figures["script_slicer"] = figure
            messages, frames = figure.drain("figure:script_slicer:")
            header = {"figure": "script_slicer", "messages": messages, "printed": []}
            exchange.send_bytes(self.envelope.pack(header, frames))

    def script_volume(self, exchange: HttpExchange) -> None:
        """Runs the VolumeRendering script's data half and answers with both volumes."""

        entry = self.entry(exchange, exchange.text("sid"), "scripts")
        if entry is None:
            return

        console = TomoVisConsole(self.logger)
        with entry.lock:
            try:
                loaded = VolumeRenderingScript(console).load(exchange.text("path"))
            except (OSError, ValueError, KeyError) as error:
                exchange.send_json({"error": str(error)}, 400)
                return
            header = {key: loaded[key] for key in ("shape", "z_range", "ps_az", "ps_rg", "resolution")}
            header["printed"] = console.drain()
            exchange.send_bytes(self.envelope.pack(header, {"volume_1": loaded["volume_1"], "volume_2": loaded["volume_2"]}))
