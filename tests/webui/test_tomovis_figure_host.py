"""Tests of the WebAgg-hosted TomoVis figures: size, navigation, readout, keymap, save, subplots and figure options.

The figures run matplotlib's own NavigationToolbar2 on the WebAgg core, so
these tests drive them with the mouse and key events the browser forwards
and check the resulting matplotlib state and messages.
"""

from __future__ import annotations

import io

import matplotlib as mpl
import numpy as np
import pytest
from PIL import Image

from tests.webui.test_tomovis_goldens import GoldenReplay, replay_scenario
from tomovis.figure_host              import TomoVisFigure
from web_logger                       import WebLogger

PLOT_W, PLOT_H = 1042, 649


@pytest.fixture
def plotted(tmp_path) -> GoldenReplay:
    """A window with the two-key FuSAR cube, the oblique ROI and a Slicer Plot (mono, half height)."""

    replay = GoldenReplay(tmp_path)
    replay.perform("import", {"kind": "hd5", "path": "<fixtures>/inputs/fusar_two_key_elev.hd5"})
    replay.perform("set_roi", {"ax": "1", "ay": "2", "angle": "30", "length": "25", "pos_x": "0", "pos_y": "0"})
    replay.perform("click", {"widget": "tab1PlotButton"})
    replay.window.tab2Plot.drain("figure:plot:")
    return replay


class Mouse:
    """Sends mpl.js-style mouse events to a figure.

    Attributes:
        figure : Target figure.
    """

    def __init__(self, figure: TomoVisFigure) -> None:
        """Binds to a figure."""

        self.figure = figure

    def event(self, kind: str, x: float, y: float, buttons: int, button: int = 0, step: float = 0) -> None:
        """Sends one event through the figure op API (device px from the top-left)."""

        self.figure.handle("mouse", {"event": {"type": kind, "x": x, "y": y, "button": button, "buttons": buttons, "modifiers": [], "step": step}})

    def drag(self, start: tuple, end: tuple, button: int = 0) -> None:
        """Presses, moves in three steps and releases."""

        mask = {0: 1, 2: 2}[button]
        self.event("button_press", *start, mask, button)
        for fraction in (0.33, 0.66, 1.0):
            self.event("motion_notify", start[0] + fraction * (end[0] - start[0]), start[1] + fraction * (end[1] - start[1]), mask, button)
        self.event("button_release", *end, 0, button)


def messages_of(figure: TomoVisFigure) -> list[dict]:
    """Drains a figure and returns its messages."""

    return figure.drain("f:")[0]


def test_resize_follows_css_size_and_device_pixel_ratio():
    """dpi = 100 x ratio and pixels = CSS size x ratio, with a full frame of that size."""

    figure = TomoVisFigure("plot", WebLogger("tomovis-test"))
    figure.getFigure().add_subplot(111).plot([0, 1], [0, 1])
    figure.handle("resize", {"width": 800, "height": 500, "dpr": 2})
    messages, frames = figure.drain("f:")

    assert figure.figure.dpi == 200
    assert figure.canvas.get_width_height(physical=True) == (1600, 1000)
    assert not any(message["type"] in ("refresh", "draw") for message in messages)
    assert Image.open(io.BytesIO(list(frames.values())[-1])).size == (1600, 1000)


def test_zoom_rectangle_changes_limits_and_back_restores(plotted):
    """Zoom mode: a box drag zooms, history enables Back, Back and Home restore the first view."""

    plot  = plotted.window.tab2Plot
    ax    = plot.figure.axes[0]
    first = (ax.get_xlim(), ax.get_ylim())
    plot.handle("toolbar", {"name": "zoom"})
    Mouse(plot).drag((300, 100), (500, 200))
    messages = messages_of(plot)

    assert ax.get_xlim() != first[0] and ax.get_ylim() != first[1]
    assert {"type": "navigate_mode", "mode": "ZOOM"} in messages
    assert {"type": "history_buttons", "Back": True, "Forward": False} in messages
    assert any(message["type"] == "rubberband" and message["x0"] == -1 for message in messages)

    plot.handle("toolbar", {"name": "back"})

    assert (ax.get_xlim(), ax.get_ylim()) == first

    plot.handle("toolbar", {"name": "forward"})
    plot.handle("toolbar", {"name": "home"})

    assert (ax.get_xlim(), ax.get_ylim()) == first


def test_zoom_ignores_a_drag_under_five_pixels(plotted):
    """F-131: a 3-pixel box does not zoom."""

    plot  = plotted.window.tab2Plot
    ax    = plot.figure.axes[0]
    first = ax.get_xlim()
    plot.handle("toolbar", {"name": "zoom"})
    Mouse(plot).drag((300, 100), (303, 103))

    assert ax.get_xlim() == first


def test_pan_moves_the_view_and_x_key_constrains_it(plotted):
    """Pan mode: a left drag shifts the limits; holding x keeps y fixed."""

    plot = plotted.window.tab2Plot
    ax   = plot.figure.axes[0]
    plot.handle("toolbar", {"name": "pan"})
    ylim = ax.get_ylim()
    xlim = ax.get_xlim()
    plot.handle("key", {"event": {"type": "key_press", "key": "kx"}})
    Mouse(plot).drag((400, 150), (440, 190))
    plot.handle("key", {"event": {"type": "key_release", "key": "kx"}})

    assert ax.get_xlim() != xlim
    assert ax.get_ylim() == ylim


def test_cursor_readout_shows_coordinates_and_image_value(plotted):
    """Over the image the label reads '(x, y) = (...)' with the bracketed value on a second line."""

    plot = plotted.window.tab2Plot
    Mouse(plot).event("motion_notify", 400, 150, 0)
    readout = [message["message"] for message in messages_of(plot) if message["type"] == "message"]

    assert readout and readout[-1].startswith("(x, y) = (")
    assert "\n[" in readout[-1]


def test_matplotlib_keymap_is_inactive(plotted):
    """F-136: 'g' does not toggle the grid on the Plot figure, while a figure with the keymap does."""

    def grid_after_g(figure: TomoVisFigure) -> bool:
        Mouse(figure).event("motion_notify", 400, 150, 0)
        figure.handle("key", {"event": {"type": "key_press", "key": "kg"}})
        figure.canvas.draw()
        return any(line.get_visible() for line in figure.figure.axes[0].xaxis.get_gridlines())

    keyed = TomoVisFigure("script_slicer", WebLogger("tomovis-test"), keymap=True)
    keyed.handle("resize", {"width": PLOT_W, "height": PLOT_H, "dpr": 1})
    keyed.getFigure().add_subplot(111).plot([0, 1], [0, 1])

    assert grid_after_g(plotted.window.tab2Plot) is False
    assert grid_after_g(keyed) is True


def test_save_dialog_and_savefig(plotted, tmp_path):
    """Save offers matplotlib's formats sorted by name with PNG preselected, writes the file and remembers the folder."""

    plot  = plotted.window.tab2Plot
    start = plot.handle("save_start", {})

    assert start["title"] == "Choose a filename to save to"
    assert start["file"] == "image.png"
    assert start["selected_filter"] == "Portable Network Graphics (*.png)"
    assert start["filters"] == sorted(start["filters"])
    assert plot.handle("save", {"path": str(tmp_path / "plot.png")}) == {"ok": True}
    assert Image.open(tmp_path / "plot.png").size == (PLOT_W, PLOT_H)
    assert plot.handle("save_start", {})["directory"] == str(tmp_path)

    assert plot.handle("save", {"path": str(tmp_path / "missing" / "plot.png")}) == {"ok": False}
    assert [(dialog["level"], dialog["title"]) for dialog in plot.drainDialogs()] == [("critical", "Error saving file")]


def test_save_dialog_has_the_twelve_filters_of_matplotlib_3_11_2(plotted, tmp_path):
    """F-135: the filters equal NavigationToolbar2QT's under matplotlib 3.11.2 (measured in the tomovis env), and GIF and AVIF are written."""

    plot  = plotted.window.tab2Plot
    start = plot.handle("save_start", {})

    assert start["filters"] == [
        "AV1 Image File Format (*.avif)",
        "Encapsulated Postscript (*.eps)",
        "Graphics Interchange Format (*.gif)",
        "Joint Photographic Experts Group (*.jpeg *.jpg)",
        "PGF code for LaTeX (*.pgf)",
        "Portable Document Format (*.pdf)",
        "Portable Network Graphics (*.png)",
        "Postscript (*.ps)",
        "Raw RGBA bitmap (*.raw *.rgba)",
        "Scalable Vector Graphics (*.svg *.svgz)",
        "Tagged Image File Format (*.tif *.tiff)",
        "WebP Image Format (*.webp)",
    ]
    for suffix, pil_format in (("gif", "GIF"), ("avif", "AVIF")):
        assert plot.handle("save", {"path": str(tmp_path / f"plot.{suffix}")}) == {"ok": True}
        with Image.open(tmp_path / f"plot.{suffix}") as image:
            assert (image.format, image.size) == (pil_format, (PLOT_W, PLOT_H))


def test_subplot_tool_applies_live_resets_and_exports(plotted):
    """Configure subplots: defaults from the figure, live left change, 0.001 gap rule, Reset, Tight layout and Export values."""

    plot  = plotted.window.tab2Plot
    state = plot.handle("subplots_open", {})

    assert state["values"] == {"top": 0.9, "bottom": 0.1, "left": 0.12, "right": 1.0, "hspace": 0.2, "wspace": 0.2}

    plot.handle("subplots_set", {"name": "left", "value": 0.3})

    assert plot.figure.subplotpars.left == 0.3

    state = plot.handle("subplots_set", {"name": "bottom", "value": 0.95})

    assert state["values"]["bottom"] == 0.899
    assert state["ranges"]["top"][0] == pytest.approx(0.9)

    state = plot.handle("subplots_reset", {})

    assert state["values"]["left"] == 0.12 and plot.figure.subplotpars.left == 0.12
    assert plot.handle("subplots_export", {})["text"] == "top=0.9,\nbottom=0.1,\nleft=0.12,\nright=1.0,\nhspace=0.2,\nwspace=0.2"
    assert plot.handle("subplots_tight", {})["values"] != state["values"]


def test_figure_options_list_axes_and_apply_a_halved_maximum(plotted):
    """Customize: the image Axes and the colorbar are listed; halving Max. value rescales the image."""

    plot    = plotted.window.tab2Plot
    choices = plot.handle("options_axes", {})["axes"]

    assert [choice["title"] for choice in choices] == ["Projected distance along ROI [m] - Elevation [m]", "<colorbar>"]

    form     = plot.handle("options_form", {"axes": 0})
    sections = [section["title"] for section in form["sections"]]

    assert form["title"] == "Figure options"
    assert sections == ["Axes", "Images, etc."]

    values = []
    for section in form["sections"]:
        if section["kind"] == "form":
            values.append([field["value"] for field in section["fields"] if field["kind"] not in ("separator", "comment")])
        else:
            values.append([[field["value"] for field in page["fields"] if field["kind"] not in ("separator", "comment")] for page in section["pages"]])

    image_fields = [field for field in form["sections"][1]["pages"][0]["fields"] if field["kind"] not in ("separator", "comment")]
    high_index   = [field["label"] for field in image_fields].index("Max. value")
    high         = float(values[1][0][high_index])
    values[1][0][high_index] = repr(high / 2)

    plot.handle("options_apply", {"axes": 0, "values": values})

    assert plot.figure.axes[0].get_images()[0].get_clim()[1] == pytest.approx(high / 2)


def test_figure_options_without_axes_warn(tmp_path):
    """An empty figure answers Customize with the Qt toolbar's 'There are no Axes to edit.' warning."""

    figure = TomoVisFigure("profile", WebLogger("tomovis-test"))

    assert figure.handle("options_axes", {}) == {"axes": []}
    assert figure.drainDialogs() == [{"kind": "message", "level": "warning", "title": "Error", "text": "There are no Axes to edit."}]


def test_window_draws_once_per_event_with_a_frame(tmp_path):
    """The copied code's repeated draw() calls produce one render per drain, sent as a PNG frame."""

    replay = GoldenReplay(tmp_path)
    replay.perform("import", {"kind": "npy", "path": "<fixtures>/inputs/npy_real.npy"})
    replay.window.handle({"type": "click", "widget": "tab1PlotButton"})
    output = replay.window.drain()

    frames = [message for message in output.figures["plot"] if message["type"] == "frame"]
    assert len(frames) == 1
    assert Image.open(io.BytesIO(output.frames[frames[0]["blob"]])).size == (PLOT_W, PLOT_H)
    assert np.asarray(Image.open(io.BytesIO(output.frames[frames[0]["blob"]]))).shape[2] == 4


def test_figures_ignore_global_rcparams_set_by_other_console_code(tmp_path):
    """Figures follow matplotlib's defaults even while other console code changed the global rcParams (paper style)."""

    paper = {"figure.dpi": 300, "font.family": "serif", "lines.linewidth": 7.0, "axes.prop_cycle": mpl.cycler(color=["black"])}
    with mpl.rc_context(paper):
        _, differences = replay_scenario("plot_xline_profile", tmp_path)
        figure         = TomoVisFigure("plot", WebLogger("tomovis-test"))

        assert mpl.rcParams["figure.dpi"] == 300

    assert differences == []
    assert figure.figure.dpi == 100
