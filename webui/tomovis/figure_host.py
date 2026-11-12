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

TomoVis ran with matplotlib's default rcParams. The console process also
hosts code that changes the global rcParams (the cube explorer's figure
archiver switches to a 300 dpi serif paper style while it saves), so every
TomoVis figure operation runs under matplotlib's "default" style through
``TomoVisRc``, serialised by one lock so that concurrent pages never restore
each other's parameters.
"""

from __future__ import annotations

import functools
import itertools
import os
import threading

import matplotlib as mpl
import matplotlib.style
from matplotlib.backends.backend_webagg_core import FigureCanvasWebAggCore, FigureManagerWebAgg, NavigationToolbar2WebAgg
from matplotlib.figure                       import Figure
from PIL                                     import features

from tomovis.events         import TomoVisEventError
from tomovis.figure_options import FigureOptionsEditor, SubplotTool
from web_logger             import WebLogger


class TomoVisRc:
    """Runs TomoVis figure code under matplotlib's default rcParams.

    Attributes:
        LOCK : Re-entrant lock held while the default style is active.
    """

    LOCK = threading.RLock()

    @classmethod
    def styled(cls, method):
        """Decorates a method so it runs under the lock and matplotlib's "default" style.

        Args:
            method : Function to wrap.

        Returns:
            The wrapped function.
        """

        @functools.wraps(method)
        def wrapper(*args, **kwargs):
            """Calls the wrapped method with the class lock held and matplotlib's "default" style active."""
            with cls.LOCK, mpl.style.context("default"):
                return method(*args, **kwargs)

        return wrapper


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


class TomoVisCanvas(FigureCanvasWebAggCore):
    """WebAgg core canvas that also offers GIF and AVIF, as TomoVis's matplotlib 3.11.2 Agg canvas did.

    TomoVic runs matplotlib 3.10.8, whose Agg canvas has no GIF or AVIF
    writer, so the Qt Save dialog lost those two filters. ``print_gif`` and
    ``print_avif`` are copied from 3.11.2's FigureCanvasAgg and the two file
    types are added to this class only, leaving every other canvas of the
    console unchanged. Whether AVIF is written depends on Pillow's AVIF
    plugin: the tomovis environment's Pillow 13.0.0 lacks it, so the
    original raises the RuntimeError below and shows "Error saving file",
    while the Dune environment's Pillow 12.1.1 has it, so the port writes
    the file.

    Attributes:
        filetypes            : matplotlib 3.10.8's file types plus 'gif' and 'avif' with 3.11.2's descriptions.
        PRINT_FIGURE_OPTIONS : Keywords print_figure passes that matplotlib's own print methods drop when they do not take them.
    """

    filetypes            = {**FigureCanvasWebAggCore.filetypes, "gif": "Graphics Interchange Format", "avif": "AV1 Image File Format"}
    PRINT_FIGURE_OPTIONS = {"dpi", "facecolor", "edgecolor", "orientation", "bbox_inches_restore"}

    def checkPrintOptions(self, options: dict) -> None:
        """Drops print_figure's renderer keywords as matplotlib does for its own print methods.

        Raises:
            TypeError : For any other keyword, as a Python call with an unexpected keyword would.
        """

        unknown = set(options) - self.PRINT_FIGURE_OPTIONS
        if unknown:
            raise TypeError(f"unexpected keyword arguments {sorted(unknown)}")

    def print_gif(self, filename_or_obj, *, metadata=None, pil_kwargs=None, **options):
        """Writes the figure to a GIF file (matplotlib 3.11.2 FigureCanvasAgg.print_gif)."""

        self.checkPrintOptions(options)
        self._print_pil(filename_or_obj, "gif", pil_kwargs, metadata)

    def print_avif(self, filename_or_obj, *, metadata=None, pil_kwargs=None, **options):
        """Writes the figure to an AVIF file (matplotlib 3.11.2 FigureCanvasAgg.print_avif).

        Raises:
            RuntimeError : If the installed Pillow cannot write AVIF.
        """

        self.checkPrintOptions(options)
        if not features.check("avif"):
            raise RuntimeError("The installed pillow version does not support avif. Full avif support has been added in pillow 11.3.")
        self._print_pil(filename_or_obj, "avif", pil_kwargs, metadata)


class TomoVisToolbar(NavigationToolbar2WebAgg):
    """matplotlib's navigation toolbar driven over WebAgg events.

    Pan and zoom announce the navigation mode, history changes announce the
    Back and Forward states, and the cursor readout, cursor shape and rubber
    band are sent as messages, all from NavigationToolbar2's own code.
    """


class TomoVisFigureManager(FigureManagerWebAgg):
    """WebAgg figure manager that builds the TomoVis toolbar and stands in for a figure window.

    A Qt figure window toggles full screen and closes itself; here the
    manager sends those two window requests to the browser, which owns the
    window.
    """

    _toolbar2_class = TomoVisToolbar

    def full_screen_toggle(self) -> None:
        """Asks the browser to toggle the figure window's full screen state (keymap.fullscreen)."""

        self._send_event("full_screen_toggle")

    def destroy(self) -> None:
        """Tells the browser that the figure window closed, as Gcf.destroy closes a pyplot figure's window."""

        self._send_event("close")


class TomoVisFigure:
    """One matplotlib figure of the page with its toolbar, frames and save dialog.

    Attributes:
        NUMBERS           : Manager numbers, unique per process; no figure is registered with pyplot.
        name              : Figure id used by the API ("plot", "profile", "export", "script_slicer").
        logger            : Console logger.
        figure            : The matplotlib Figure TomoVis draws into.
        canvas            : WebAgg core canvas with the GIF and AVIF writers (TomoVisCanvas).
        manager           : WebAgg figure manager owning the toolbar.
        toolbar           : Navigation toolbar.
        socket            : Message collector registered as the manager's only web socket.
        pending_draw      : Whether a render is due before the next drain.
        shown             : Whether the figure's tab page has been shown once.
        savefig_directory : Start directory of the next Save dialog, remembered after each save.
        dialogs           : Message boxes requested by figure operations since the last drain.
        subplot_tool      : The Configure subplots dialog, built on first use and kept, as the Qt toolbar keeps it.
        handlers          : Objects whose bound methods are connected to the canvas; matplotlib only keeps weak references to them.
        options           : The Customize (figure options) editor.
        MOUSE_TYPES       : Mouse event types mpl.js sends.
        KEY_TYPES         : Key event types mpl.js sends.
        TOOLBAR_BUTTONS   : Toolbar methods the browser may run.
    """

    MOUSE_TYPES     = ("button_press", "button_release", "dblclick", "motion_notify", "scroll", "figure_enter", "figure_leave")
    KEY_TYPES       = ("key_press", "key_release")
    TOOLBAR_BUTTONS = ("home", "back", "forward", "pan", "zoom")

    NUMBERS = itertools.count(1)

    @TomoVisRc.styled
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
        self.canvas            = TomoVisCanvas(self.figure)
        self.manager           = TomoVisFigureManager(self.canvas, next(self.NUMBERS))
        self.toolbar           = self.manager.toolbar
        self.socket            = FigureMessages()
        self.pending_draw      = False
        self.shown             = False
        self.savefig_directory = os.path.expanduser(mpl.rcParams['savefig.directory'])
        self.dialogs           = []
        self.subplot_tool      = None
        self.handlers          = []
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

    def showEvent(self) -> None:
        """Renders on the first show of the figure's tab page.

        A Qt canvas in a tab page that was never shown gets its first resize
        event when the page appears, and FigureCanvasQT.resizeEvent ends in
        ``draw_idle``. Changes the window left undrawn before that, such as the
        Profile axes of E-011, therefore appear when the tab is first opened.
        """

        if self.shown:
            return
        self.shown        = True
        self.pending_draw = True

    @TomoVisRc.styled
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

    @TomoVisRc.styled
    def mouse(self, event: dict) -> None:
        """Forwards one mouse event in mpl.js form to the canvas.

        Args:
            event : {type, x, y, button, buttons, modifiers, step}; x and y in device pixels from the top-left.
        """

        self.canvas.handle_event(dict(event))

    @TomoVisRc.styled
    def key(self, event: dict) -> None:
        """Forwards one key event in mpl.js form ("k" + key with modifier prefixes) to the canvas.

        Args:
            event : {type: "key_press" | "key_release", key}.
        """

        self.canvas.handle_event(dict(event))

    @TomoVisRc.styled
    def toolbarButton(self, name: str) -> None:
        """Runs a toolbar button: home, back, forward, pan or zoom.

        Args:
            name : Toolbar method name.
        """

        getattr(self.toolbar, name)()

    @TomoVisRc.styled
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

    @TomoVisRc.styled
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

    @TomoVisRc.styled
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

    @TomoVisRc.styled
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
