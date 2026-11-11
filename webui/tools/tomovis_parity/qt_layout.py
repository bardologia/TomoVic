"""Records how Qt 5.15 sizes the original TomoVis Slicer panes and pyqtgraph's ImageView splitter.

Runs in the tomovis conda environment against the original TomoVis source,
under the offscreen platform. Three scenarios drive the real window: the ROI
buttons of the top and bottom ImageViews toggled at five window sizes, the
Normalization group shown and hidden together with the ROI plot and window
resizes, and the ROI plot splitter handle dragged with mouse events up to and
past both collapse points. Every step stores, for both visible ImageViews, the
height QVBoxLayout gave it, the QSplitter sizes, and the size hint and minimum
size hint the layout used, so the port's qGeomCalc and QSplitter models can be
replayed against them. The bootstrap below sets the platform and the Qt binding
before PyQt5 is imported and adds the TomoVis root to ``sys.path``.

Usage:
    /home/bard/miniconda3/envs/tomovis/bin/python webui/tools/tomovis_parity/qt_layout.py
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]

os.environ["QT_QPA_PLATFORM"]  = "offscreen"
os.environ["QT_API"]           = "pyqt5"
os.environ["PYQTGRAPH_QT_LIB"] = "PyQt5"
os.environ["MPLBACKEND"]       = "Qt5Agg"
sys.dont_write_bytecode        = True

parser = argparse.ArgumentParser(description="Record Qt's Slicer pane and ImageView splitter geometry.")
parser.add_argument("--tomovis", type=Path, default=REPO.parent / "tomovis",                                               help="TomoVis source root (holds Visualizer/)")
parser.add_argument("--cube",    type=Path, default=REPO / "tests" / "webui" / "fixtures" / "tomovis" / "inputs" / "npy_real.npy", help="cube imported before every scenario")
parser.add_argument("--out",     type=Path, default=REPO / "tests" / "webui" / "fixtures" / "tomovis_qt_layout" / "layout.json",   help="fixture file")
options = parser.parse_args()

sys.path.insert(0, str(REPO / "webui"))
sys.path.insert(0, str(options.tomovis.resolve()))

from harness import TomoVisSession
from PyQt5   import QtCore, QtGui


class PaneGeometryProbe:
    """Reads the geometry of the two visible Slicer ImageViews of one window.

    Attributes:
        PANES : Names of the visible single-channel ImageViews, top first.
    """

    PANES = ("imv1_1", "imv2_1")

    def pane(self, view) -> dict:
        """Returns the geometry of one ImageView.

        Args:
            view : pyqtgraph ImageView of the window.

        Returns:
            Height, splitter sizes, size hint and minimum size hint heights in pixels, and whether the Normalization group is shown.
        """

        return {
            "height"          : view.height(),
            "sizes"           : view.ui.splitter.sizes(),
            "sizeHint"        : view.sizeHint().height(),
            "minimumSizeHint" : view.minimumSizeHint().height(),
            "norm"            : view.ui.normGroup.isVisible(),
        }

    def capture(self, window) -> dict:
        """Returns both panes and the window size.

        Args:
            window : Original TomoVis main window.

        Returns:
            Window size and one pane entry per name in PANES.
        """

        return {"window": [window.width(), window.height()], **{name: self.pane(getattr(window, name)) for name in self.PANES}}


class SplitterDragger:
    """Drags the ROI plot handle of an ImageView splitter with Qt mouse events.

    Positions are taken from the splitter, not the handle, because the handle moves while it is dragged.

    Attributes:
        PRESS_Y : Press position inside the 4 px handle widget, in pixels from its top.
        STEPS   : Number of move events per drag.
    """

    PRESS_Y = 2
    STEPS   = 5

    def __init__(self, session: TomoVisSession) -> None:
        """Keeps the session whose events are sent.

        Args:
            session : Headless TomoVis session.
        """

        self.session = session

    def send(self, kind, handle, splitter, point: QtCore.QPoint, button, buttons) -> None:
        """Sends one mouse event to the handle at a splitter position.

        Args:
            kind     : QEvent type.
            handle   : QSplitterHandle receiving the event.
            splitter : QSplitter the position is measured in.
            point    : Position in splitter coordinates.
            button   : Button that changed.
            buttons  : Buttons held.
        """

        screen = splitter.mapToGlobal(point)
        local  = handle.mapFromGlobal(screen)
        event  = QtGui.QMouseEvent(kind, QtCore.QPointF(local), QtCore.QPointF(local), QtCore.QPointF(screen), button, buttons, QtCore.Qt.NoModifier)
        self.session.app.sendEvent(handle, event)

    def drag(self, view, dy: int) -> None:
        """Presses the ROI plot handle, moves it by dy in STEPS events and releases it.

        Args:
            view : pyqtgraph ImageView whose splitter is dragged.
            dy   : Vertical distance in pixels, negative upwards.
        """

        splitter = view.ui.splitter
        handle   = splitter.handle(1)
        start    = handle.mapTo(splitter, QtCore.QPoint(handle.width() // 2, self.PRESS_Y))

        self.send(QtCore.QEvent.MouseButtonPress, handle, splitter, start, QtCore.Qt.LeftButton, QtCore.Qt.LeftButton)
        for k in range(1, self.STEPS + 1):
            self.send(QtCore.QEvent.MouseMove, handle, splitter, start + QtCore.QPoint(0, round(dy * k / self.STEPS)), QtCore.Qt.NoButton, QtCore.Qt.LeftButton)
        self.send(QtCore.QEvent.MouseButtonRelease, handle, splitter, start + QtCore.QPoint(0, dy), QtCore.Qt.LeftButton, QtCore.Qt.NoButton)
        self.session.settle()


class QtLayoutRecorder:
    """Plays the layout scenarios on the original window and writes the fixture.

    Attributes:
        ROI_SIZES  : Window sizes of the ROI toggle scenario.
        ROI_STEPS  : (label, ImageView) toggles of the ROI scenario.
        NORM_STEPS : (label, action, argument) steps of the Normalization scenario.
        DRAGS      : (label, dy) handle drags of the splitter scenario.
        cube       : Cube imported into every fresh window.
        out        : Fixture file.
        probe      : Pane geometry reader.
        session    : Headless TomoVis session.
        dragger    : Splitter handle dragger.
    """

    ROI_SIZES  = ((1100, 880), (1404, 880), (1404, 980), (1100, 1100), (1564, 964))
    ROI_STEPS  = (("top_on", "imv1_1"), ("top_off", "imv1_1"), ("top_on2", "imv1_1"), ("bottom_on", "imv2_1"), ("top_off3", "imv1_1"), ("bottom_off", "imv2_1"))
    NORM_STEPS = (
        ("norm_on", "norm", True), ("roi_on", "roi", None), ("norm_off", "norm", False), ("roi_off", "roi", None), ("roi_on2", "roi", None),
        ("norm_on2", "norm", True), ("resize_980", "resize", (1100, 980)), ("resize_880", "resize", (1100, 880)), ("norm_off2", "norm", False),
        ("resize_1000", "resize", (1100, 1000)), ("slice_5", "slice", 5), ("resize_880b", "resize", (1100, 880)),
    )
    DRAGS      = (("up50", -50), ("down100", 100), ("down30", 30), ("down15", 15), ("down25", 25), ("up30", -30), ("up200", -200), ("up40", -40), ("up70", -70), ("down120", 120), ("down200", 200), ("up100", -100))

    def __init__(self, cube: Path, out: Path) -> None:
        """Starts the headless session.

        Args:
            cube : Cube imported into every fresh window.
            out  : Fixture file.
        """

        self.cube    = cube
        self.out     = out
        self.probe   = PaneGeometryProbe()
        self.session = TomoVisSession()
        self.dragger = SplitterDragger(self.session)

    def fresh(self, size: tuple[int, int]):
        """Opens a fresh window of the given size with the cube imported.

        Args:
            size : Window size (width, height) in pixels.

        Returns:
            The original TomoVis main window.
        """

        self.session.close_window()
        self.session.size = size
        self.session.open_window()
        self.session.perform("import", {"kind": "npy", "path": str(self.cube)})
        return self.session.window

    def step(self, label: str, window) -> dict:
        """Settles the event loop and captures one labelled step.

        Args:
            label  : Step label.
            window : Original TomoVis main window.

        Returns:
            The captured step.
        """

        self.session.settle()
        return {"label": label, **self.probe.capture(window)}

    def roi_scenario(self) -> dict:
        """Toggles the ROI buttons at every size in ROI_SIZES.

        Returns:
            Size label to the list of steps.
        """

        out = {}
        for size in self.ROI_SIZES:
            window = self.fresh(size)
            steps  = [self.step("start", window)]
            for label, name in self.ROI_STEPS:
                getattr(window, name).ui.roiBtn.click()
                steps.append(self.step(label, window))
            out[f"{size[0]}x{size[1]}"] = steps
        return out

    def norm_scenario(self) -> list[dict]:
        """Shows and hides the top Normalization group around ROI toggles, resizes and a slice change.

        Returns:
            The list of steps.
        """

        window = self.fresh((1100, 880))
        view   = window.imv1_1
        steps  = [self.step("start", window)]
        for label, action, argument in self.NORM_STEPS:
            if action == "norm":
                view.normToggled(argument)
            elif action == "roi":
                view.ui.roiBtn.click()
            elif action == "resize":
                window.resize(*argument)
            elif action == "slice":
                window.tab1Slider.setValue(argument)
            steps.append(self.step(label, window))
        return steps

    def drag_scenario(self) -> list[dict]:
        """Drags the top ROI plot handle through DRAGS, then resizes, changes the slice and toggles the ROI.

        Returns:
            The list of steps, each drag carrying its dy.
        """

        window = self.fresh((1100, 880))
        view   = window.imv1_1
        view.ui.roiBtn.click()
        steps  = [self.step("roi_on", window)]
        for label, dy in self.DRAGS:
            self.dragger.drag(view, dy)
            steps.append({**self.step(label, window), "dy": dy})
        for label, size in (("resize_980", (1100, 980)), ("resize_880", (1100, 880))):
            window.resize(*size)
            steps.append(self.step(label, window))
        window.tab1Slider.setValue(5)
        steps.append(self.step("slice_5", window))
        for label in ("roi_off", "roi_on_again"):
            view.ui.roiBtn.click()
            steps.append(self.step(label, window))
        return steps

    def run(self) -> None:
        """Plays the three scenarios and writes the fixture."""

        fixture = {
            "press_y" : SplitterDragger.PRESS_Y,
            "steps"   : SplitterDragger.STEPS,
            "roi"     : self.roi_scenario(),
            "norm"    : self.norm_scenario(),
            "drags"   : self.drag_scenario(),
        }
        self.session.close_window()
        self.out.parent.mkdir(parents=True, exist_ok=True)
        self.out.write_text(json.dumps(fixture, indent=1) + "\n")


QtLayoutRecorder(options.cube, options.out).run()
