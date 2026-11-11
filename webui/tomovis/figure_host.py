"""Matplotlib figures of the TomoVis page, hosted on matplotlib's WebAgg core.

TomoVis embedded two matplotlib figures (Plot and Profile) in Qt widgets
with the Qt navigation toolbar. Here each figure lives on a
``FigureCanvasWebAggCore`` with a ``NavigationToolbar2WebAgg`` subclass, so
pan, zoom, the view history, the rubber band and the cursor readout are
matplotlib's own code driven by the mouse and key events the browser
forwards. A ``FigureMessages`` collector stands in for WebAgg's web socket
and records the ordered messages and PNG frames for the HTTP response. The
copied window code reaches a figure through the ``MatplotlibWidget`` API it
used (``getFigure``, ``draw``). The Qt toolbar's Save entry is rebuilt here
from ``NavigationToolbar2QT.save_figure`` (matplotlib 3.11.2), with the save
directory remembered per page session.
"""

from __future__ import annotations

import itertools
import os

import matplotlib as mpl
from matplotlib.backends.backend_webagg_core import FigureCanvasWebAggCore, FigureManagerWebAgg, NavigationToolbar2WebAgg
from matplotlib.figure                       import Figure

from tomovis.events         import TomoVisEventError
from tomovis.figure_options import FigureOptionsEditor, SubplotTool
from web_logger             import WebLogger


class FigureMessages:
    """Collects what WebAgg would send over its web socket.

    Attributes:
        messages : Ordered JSON messages; a binary frame appears as {"type": "frame", "index": i}.
        frames   : PNG frames in order.
    """

    def __init__(self) -> None:
        """Starts empty."""

        self.messages = []
        self.frames   = []

    def send_json(self, content: dict) -> None:
        """Records one JSON message."""

        self.messages.append(dict(content))

    def send_binary(self, blob: bytes) -> None:
        """Records one PNG frame and its position in the message order."""

        self.messages.append({"type": "frame", "index": len(self.frames)})
        self.frames.append(blob)

    def drain(self) -> tuple[list[dict], list[bytes]]:
        """Returns and clears the messages and frames."""

        messages, frames = self.messages, self.frames
        self.messages    = []
        self.frames      = []
        return messages, frames


class TomoVisToolbar(NavigationToolbar2WebAgg):
    """matplotlib's navigation toolbar driven over WebAgg events.

    Pan and zoom announce the navigation mode, history changes announce the
    Back and Forward states, and the cursor readout, cursor shape and rubber
    band are sent as messages, all from NavigationToolbar2's own code.
    """


class TomoVisFigureManager(FigureManagerWebAgg):
    """WebAgg figure manager that builds the TomoVis toolbar."""

    _toolbar2_class = TomoVisToolbar


class TomoVisFigure:
    """One matplotlib figure of the page with its toolbar, frames and save dialog.

    Attributes:
        NUMBERS           : Manager numbers, unique per process; no figure is registered with pyplot.
        name              : Figure id used by the API ("plot", "profile", "export", "script_slicer").
        logger            : Console logger.
        figure            : The matplotlib Figure TomoVis draws into.
        canvas            : WebAgg core canvas.
        manager           : WebAgg figure manager owning the toolbar.
        toolbar           : Navigation toolbar.
        socket            : Message collector registered as the manager's only web socket.
        pending_draw      : Whether a render is due before the next drain.
        savefig_directory : Start directory of the next Save dialog, remembered after each save.
        dialogs           : Message boxes requested by figure operations since the last drain.
        subplot_tool      : The Configure subplots dialog, built on first use and kept, as the Qt toolbar keeps it.
        options           : The Customize (figure options) editor.
        MOUSE_TYPES       : Mouse event types mpl.js sends.
        KEY_TYPES         : Key event types mpl.js sends.
        TOOLBAR_BUTTONS   : Toolbar methods the browser may run.
    """

    MOUSE_TYPES     = ("button_press", "button_release", "dblclick", "motion_notify", "scroll", "figure_enter", "figure_leave")
    KEY_TYPES       = ("key_press", "key_release")
    TOOLBAR_BUTTONS = ("home", "back", "forward", "pan", "zoom")

    NUMBERS = itertools.count(1)

    def __init__(self, name: str, logger: WebLogger, keymap: bool = False) -> None:
        """Builds the figure, canvas, manager and toolbar.

        Without ``keymap`` the manager's key and mouse-button shortcut handlers
        are disconnected: TomoVis's canvases had no figure manager, so
        matplotlib's default keymap was inactive there (F-136). Ctrl, x and y
        still constrain pan and zoom through the canvas' key tracking.

        Args:
            name   : Figure id.
            logger : Console logger.
            keymap : Keep matplotlib's default key bindings (the SlicerMatplotlib script figure).
        """

        self.name              = name
        self.logger            = logger
        self.figure            = Figure()
        self.canvas            = FigureCanvasWebAggCore(self.figure)
        self.manager           = TomoVisFigureManager(self.canvas, next(self.NUMBERS))
        self.toolbar           = self.manager.toolbar
        self.socket            = FigureMessages()
        self.pending_draw      = False
        self.savefig_directory = os.path.expanduser(mpl.rcParams['savefig.directory'])
        self.dialogs           = []
        self.subplot_tool      = None
        self.options           = FigureOptionsEditor(self.figure)

        self.manager.set_window_title("")
        if not keymap:
            self.canvas.mpl_disconnect(self.manager.key_press_handler_id)
            self.canvas.mpl_disconnect(self.manager.button_press_handler_id)

        self.manager.add_web_socket(self.socket)
        self.canvas.handle_event({"type": "refresh"})

    def getFigure(self) -> Figure:
        """Returns the figure (MatplotlibWidget.getFigure)."""

        return self.figure

    def draw(self) -> None:
        """Requests a render (MatplotlibWidget.draw); the frame is produced once per request at drain time."""

        self.pending_draw = True

    def resize(self, width: int, height: int, dpr: float) -> None:
        """Sizes the figure as the browser canvas: dpi 100 x ratio, pixels = CSS size x ratio.

        Args:
            width  : CSS width in pixels.
            height : CSS height in pixels.
            dpr    : Browser devicePixelRatio.
        """

        self.canvas.handle_event({"type": "set_device_pixel_ratio", "device_pixel_ratio": dpr})
        self.canvas.handle_event({"type": "resize", "width": int(width), "height": int(height)})
        self.canvas.handle_event({"type": "refresh"})

    def mouse(self, event: dict) -> None:
        """Forwards one mouse event in mpl.js form to the canvas.

        Args:
            event : {type, x, y, button, buttons, modifiers, step}; x and y in device pixels from the top-left.
        """

        self.canvas.handle_event(dict(event))

    def key(self, event: dict) -> None:
        """Forwards one key event in mpl.js form ("k" + key with modifier prefixes) to the canvas.

        Args:
            event : {type: "key_press" | "key_release", key}.
        """

        self.canvas.handle_event(dict(event))

    def toolbarButton(self, name: str) -> None:
        """Runs a toolbar button: home, back, forward, pan or zoom.

        Args:
            name : Toolbar method name.
        """

        getattr(self.toolbar, name)()

    def refresh(self) -> None:
        """Resends a full frame, the history button states and the navigation mode."""

        self.canvas.handle_event({"type": "refresh"})
        self.canvas.send_event("navigate_mode", mode=self.toolbar.mode.name)

    def saveStart(self) -> dict:
        """Describes the Save dialog as NavigationToolbar2QT.save_figure builds it.

        Returns:
            Dialog title, start directory and file name, name filters sorted by format name, and the default filter.
        """

        filetypes        = self.canvas.get_supported_filetypes_grouped()
        sorted_filetypes = sorted(filetypes.items())
        default_filetype = self.canvas.get_default_filetype()

        filters        = []
        selectedFilter = None
        for name, exts in sorted_filetypes:
            exts_list = " ".join(['*.%s' % ext for ext in exts])
            filter    = f'{name} ({exts_list})'
            if default_filetype in exts:
                selectedFilter = filter
            filters.append(filter)

        return {
            "title"           : "Choose a filename to save to",
            "directory"       : self.savefig_directory,
            "file"            : self.canvas.get_default_filename(),
            "filters"         : filters,
            "selected_filter" : selectedFilter,
        }

    def save(self, fname: str) -> bool:
        """Saves the figure as the Qt toolbar does, remembering the directory.

        A failure is reported with the Qt toolbar's critical message box.

        Args:
            fname : Target path on the server.

        Returns:
            Whether the file was written.
        """

        if not fname:
            return False

        if self.savefig_directory != "":
            self.savefig_directory = os.path.dirname(fname)
        try:
            self.canvas.figure.savefig(fname)
        except Exception as e:
            self.dialogs.append({"kind": "message", "level": "critical", "title": "Error saving file", "text": str(e)})
            self.logger.warning(f"TomoVis: could not save the {self.name} figure to {fname}: {e}")
            return False
        return True

    def subplotTool(self) -> SubplotTool:
        """Returns the subplot dialog, building it on first use."""

        if self.subplot_tool is None:
            self.subplot_tool = SubplotTool(self.figure, self.logger)
        return self.subplot_tool

    def number(self, payload: dict, name: str) -> float:
        """Returns a numeric op field.

        Raises:
            TomoVisEventError : If the field is missing or not a number.
        """

        value = payload.get(name)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise TomoVisEventError(f"figure op field '{name}' must be a number")
        return float(value)

    def checkedEvent(self, payload: dict, types: tuple) -> dict:
        """Returns the op's event dict after checking its type and the fields WebAgg reads.

        Raises:
            TomoVisEventError : For a missing event, an unknown type or missing fields.
        """

        event = payload.get("event")
        if not isinstance(event, dict) or event.get("type") not in types:
            raise TomoVisEventError("figure op 'event' has an unknown type")
        if types is self.MOUSE_TYPES:
            for name in ("x", "y", "button", "buttons"):
                self.number(event, name)
            if not isinstance(event.get("modifiers", []), list):
                raise TomoVisEventError("figure op event 'modifiers' must be a list")
            event = {**event, "modifiers": event.get("modifiers", [])}
            if event["type"] == "scroll":
                self.number(event, "step")
        elif not isinstance(event.get("key"), str) or "k" not in event["key"]:
            raise TomoVisEventError("figure op event 'key' must be an mpl.js key string")
        return event

    def handle(self, op: str, payload: dict) -> dict | None:
        """Runs one figure operation of the API.

        Args:
            op      : Operation name (resize, mouse, key, toolbar, refresh, subplots_*, options_*, save_start, save).
            payload : Operation fields.

        Returns:
            The operation result, None for operations without one.

        Raises:
            TomoVisEventError : For an unknown operation or invalid fields.
        """

        if op == "resize":
            width  = self.number(payload, "width")
            height = self.number(payload, "height")
            dpr    = self.number(payload, "dpr")
            if width < 1 or height < 1 or dpr <= 0:
                raise TomoVisEventError("figure sizes must be positive")
            self.resize(int(width), int(height), dpr)
            return None
        if op == "mouse":
            self.mouse(self.checkedEvent(payload, self.MOUSE_TYPES))
            return None
        if op == "key":
            self.key(self.checkedEvent(payload, self.KEY_TYPES))
            return None
        if op == "toolbar":
            if payload.get("name") not in self.TOOLBAR_BUTTONS:
                raise TomoVisEventError("unknown toolbar button")
            self.toolbarButton(payload["name"])
            return None
        if op == "refresh":
            self.refresh()
            return None
        if op == "subplots_open":
            tool = self.subplotTool()
            tool.update_from_current_subplotpars()
            return tool.state()
        if op == "subplots_set":
            if not isinstance(payload.get("name"), str):
                raise TomoVisEventError("figure op field 'name' must be a string")
            tool = self.subplotTool()
            tool.setValue(payload["name"], self.number(payload, "value"))
            return tool.state()
        if op == "subplots_tight":
            tool = self.subplotTool()
            tool._tight_layout()
            return tool.state()
        if op == "subplots_reset":
            tool = self.subplotTool()
            tool._reset()
            return tool.state()
        if op == "subplots_export":
            return {"text": self.subplotTool()._export_values()}
        if op == "options_axes":
            choices = self.options.axesChoices()
            if choices is None:
                self.dialogs.append({"kind": "message", "level": "warning", "title": "Error", "text": "There are no Axes to edit."})
            return {"axes": choices or []}
        if op == "options_form":
            return self.options.form(payload.get("axes"))
        if op == "options_apply":
            return {"form": self.options.apply(payload.get("axes"), payload.get("values"))}
        if op == "save_start":
            return self.saveStart()
        if op == "save":
            if not isinstance(payload.get("path"), str):
                raise TomoVisEventError("figure op field 'path' must be a string")
            return {"ok": self.save(payload["path"])}
        raise TomoVisEventError(f"unknown figure op '{op}'")

    def drain(self, prefix: str) -> tuple[list[dict], dict]:
        """Renders when due and returns the ordered messages with named PNG frames.

        WebAgg's ``draw`` requests (from ``draw_idle``) are answered here with a
        render and its ``refresh`` requests with a refresh, as mpl.js answers
        them; neither leaves the server.

        Args:
            prefix : Blob name prefix for this figure's frames.

        Returns:
            (messages, frames): messages with frames referenced as {"type": "frame", "blob": name}; blob name to PNG bytes.
        """

        messages = []
        frames   = {}
        while True:
            batch, pngs = self.socket.drain()
            for message in batch:
                if message["type"] == "draw":
                    self.pending_draw = True
                elif message["type"] == "refresh":
                    self.canvas.handle_event({"type": "refresh"})
                elif message["type"] == "frame":
                    blob         = f"{prefix}{len(frames)}"
                    frames[blob] = pngs[message["index"]]
                    messages.append({"type": "frame", "blob": blob})
                else:
                    messages.append(message)

            if not self.pending_draw:
                break
            self.pending_draw = False
            self.canvas.draw()

        return messages, frames

    def drainDialogs(self) -> list[dict]:
        """Returns and clears the message boxes requested by figure operations."""

        dialogs, self.dialogs = self.dialogs, []
        return dialogs
