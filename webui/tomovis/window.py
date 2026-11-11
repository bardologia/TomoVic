"""The TomoVis main window, copied from TomoVis's Visualizer/visualizer.py (class TomoVis).

Every method keeps its original name, statements and order; widget names are
the original attribute names, so the snapshot and the parity goldens share
their keys and the original line numbers stay the cross-reference. What
changed, and only where it had to:

- Qt widgets are the headless stand-ins of ``tomovis.qt_widgets`` and the
  pyqtgraph objects the state models of ``tomovis.pg_models``; layout calls,
  fonts, sizes, icons and style sheets belong to the browser.
- Modal dialogs are split at ``exec_``: the first half asks the
  ``DialogQueue`` and returns, the browser answers, and the second half runs
  the code that followed ``exec_`` (``*Accepted`` methods).
- ``print`` goes to ``TomoVisConsole`` (the console log, D-7); message boxes
  go to the ``DialogQueue``.
- The 3D tab's handlers and the vispy ``Volume`` run in the browser; the
  server keeps the volume preparation of ``ensure3DLoaded``.
- Crash fixes E-001 to E-012 (see the package README) and decisions D-2/D-3.

Exceptions inside slots are reported by the slot boundary and the window
keeps its half-applied state, as the original did under pyqtgraph's
excepthook.
"""

from __future__ import annotations

import math
import secrets
import warnings

import matplotlib.cm as cm
import numpy as np
from PIL     import Image
from skimage import exposure

from tomovis.cube_readers import CubeReaders
from tomovis.events       import TomoVisEventError, TomoVisEvents
from tomovis.figure_host  import TomoVisFigure, TomoVisRc
from tomovis.pg_models    import PgColorMap, PgImageViewModel, PgInfiniteLineModel, PgLineSegmentRoiModel
from tomovis.qt_widgets   import QtAction, QtActionGroup, QtCheckBox, QtComboBox, QtDoubleSpinBox, QtLineEdit, QtMenu, QtPushButton, QtRadioButton, QtRegExpValidator, QtSlider, QtSpinBox, QtStackedWidget, QtTabWidget, QtTimer, SlotBoundary
from tomovis.session_file import SessionFile
from tomovis.tools        import TomoVisTools
from web_logger           import WebLogger


class TomoVisConsole:
    """Replacement of ``print``: each line goes to the console log with the TomoVis prefix (D-7).

    Attributes:
        logger : Console logger.
        lines  : Lines printed since the last drain.
    """

    def __init__(self, logger: WebLogger) -> None:
        """Starts with no lines.

        Args:
            logger : Console logger.
        """

        self.logger = logger
        self.lines  = []

    def print(self, *args, level: str = "info") -> None:
        """Joins the arguments as print does and logs the line.

        Args:
            args  : Values to print.
            level : WebLogger method: "info", "warning" or "error".
        """

        line = " ".join(str(argument) for argument in args)
        self.lines.append(line)
        getattr(self.logger, level)(TomoVisTools.TERMINAL_PREFIX + line)

    def drain(self) -> list[str]:
        """Returns and clears the printed lines."""

        lines, self.lines = self.lines, []
        return lines


class DialogQueue:
    """Modal dialogs as requests to the browser, with the continuation of the dialog that waits for an answer.

    Message boxes need no answer: the code after a message box in TomoVis is
    always a return or the end of the method. File and Axes dialogs carry a
    token; the browser answers with a dialog_result event and the stored
    continuation runs inside the slot boundary. Timer ticks and other events
    stay allowed while a dialog is pending, as Qt's nested event loop keeps
    them running during ``exec_``.

    Attributes:
        boundary : Slot boundary the continuation runs in.
        requests : Dialog requests since the last drain.
        pending  : (token, continuation) of the dialog awaiting an answer, None when none.
    """

    def __init__(self, boundary: SlotBoundary) -> None:
        """Starts with no requests.

        Args:
            boundary : Slot boundary.
        """

        self.boundary = boundary
        self.requests = []
        self.pending  = None

    def message(self, level: str, title: str, text: str) -> None:
        """Requests a message box with one OK button.

        Args:
            level : "information", "warning" or "critical".
            title : Window title.
            text  : Message text, line breaks kept.
        """

        self.requests.append({"kind": "message", "level": level, "title": title, "text": text})

    def request(self, kind: str, payload: dict, continuation) -> str:
        """Requests a dialog that needs an answer; a newer request replaces a pending one.

        Args:
            kind         : "file" or "axes".
            payload      : Dialog description.
            continuation : Callable receiving the browser's result dict when the dialog is accepted.

        Returns:
            The token the answer must carry.
        """

        token        = secrets.token_hex(8)
        self.pending = (token, continuation)
        self.requests.append({"kind": kind, "token": token, **payload})
        return token

    def resolve(self, token: str, result: dict) -> None:
        """Runs the pending continuation for an accepted dialog; a cancelled one runs nothing.

        Args:
            token  : Token of the answered dialog.
            result : {"accepted": bool, ...} with "path" for file dialogs or "values" for the Axes dialog.

        Raises:
            TomoVisEventError : If no dialog with this token is pending (409).
        """

        if self.pending is None or self.pending[0] != token:
            raise TomoVisEventError("no pending dialog with this token", 409)

        continuation = self.pending[1]
        self.pending = None
        if result.get("accepted"):
            self.boundary.run(continuation, (result,))

    def pendingToken(self) -> str | None:
        """Returns the token of the pending dialog, None when none."""

        return self.pending[0] if self.pending is not None else None

    def drain(self) -> list[dict]:
        """Returns and clears the requests."""

        requests, self.requests = self.requests, []
        return requests


class WindowOutput:
    """Everything an event produced besides the snapshot.

    Attributes:
        dialogs     : Dialog requests in order.
        figures     : Figure id to its ordered messages.
        frames      : Blob name to PNG bytes.
        views       : View name to the image array whose content changed.
        printed     : Lines printed during the event.
        slot_errors : {"type", "message"} of every exception a slot raised.
    """

    def __init__(self, dialogs: list, figures: dict, frames: dict, views: dict, printed: list, slot_errors: list) -> None:
        """Stores the parts."""

        self.dialogs     = dialogs
        self.figures     = figures
        self.frames      = frames
        self.views       = views
        self.printed     = printed
        self.slot_errors = slot_errors


class TomoVisWindow:
    """The copied TomoVis window.

    Attributes:
        logger         : Console logger.
        has3d          : Whether the browser offers WebGL2, the analogue of vispy plus a usable OpenGL context (F-090).
        boundary       : Slot boundary of every signal.
        console        : print replacement.
        dialogs        : Dialog queue.
        tools          : TomoVis helpers and tables.
        readers        : Import readers.
        session_file   : Session file reader and writer.
        events         : Event dispatcher of the API.
        slot_errors    : Slot exceptions since the last drain.
        sent_serials   : View name to the image serial last sent to the browser.
        volume_present : Analogue of ``self.volume is not None``: the browser holds a 3D view for this cube.
        volume_data    : Equalised, subsampled float32 volume handed to the 3D view.
        volume_serial  : Bumped whenever a new volume is prepared.
    """

    @TomoVisRc.styled
    def __init__(self, logger: WebLogger, has3d: bool = True, **kwargs) -> None:
        """Builds the window as TomoVis.__init__ does.

        Args:
            logger : Console logger.
            has3d  : Whether the 3D tab exists.
            kwargs : Ignored, as in TomoVis.
        """

        self.logger       = logger
        self.has3d        = has3d
        self.boundary     = SlotBoundary(self.reportSlotError)
        self.console      = TomoVisConsole(logger)
        self.dialogs      = DialogQueue(self.boundary)
        self.tools        = TomoVisTools()
        self.readers      = CubeReaders(logger)
        self.session_file = SessionFile()
        self.events       = TomoVisEvents(self)
        self.slot_errors  = []
        self.sent_serials = {}

        self.name = "TomoVis"

        self.nChannels = 1

        self.x_label = "Azimuth [m]"
        self.z_label = "Elevation [m]"

        self.x_min = 0.0
        self.x_max = 1.0
        self.x_label_view = self.x_label
        self.x_view_min = self.x_min
        self.x_view_max = self.x_max

        self.z_axis = None
        self.z_range = [-20.0, 20.0]
        self.z_view_range = [-20.0, 20.0]

        self.x_res = 1.0
        self.y_res = 1.0

        self.data = None
        self.d2Norm = None
        self.naz = 0
        self.cmap = 9
        self.color = PgColorMap(np.linspace(0.0, 1.0, 256), self.tools.colortables(self.cmap)[1], self.cmap)
        self.subplot = 211

        self.minW = 1100
        self.minH = 880
        self.widthButton = 100
        self.widthSl1 = 400
        self.widthSl2 = 200
        self.width01 = 180
        self.widthQline = 90

        self.tab1Timer = QtTimer(self.boundary, "tab1Timer")

        self.roiFlag = False

        self.volume_present = False
        self.volume_rendered = False
        self.volume_data = None
        self.volume_serial = 0
        self.tab3d_index = None

        self.tab2_plotted = False
        self.tab3_plotted = False

        self.createLayout()

        self.slice_line = PgInfiniteLineModel(pos=0, angle=0)

        self.imv1_1.addItem(self.slice_line)

        self.slice_line.hide()

        self.signals()

    def reportSlotError(self, exc: Exception, text: str) -> None:
        """Logs a slot exception with its traceback and records it for the response.

        Args:
            exc  : The exception.
            text : Formatted traceback.
        """

        self.logger.error(TomoVisTools.TERMINAL_PREFIX + text.rstrip())
        self.slot_errors.append({"type": type(exc).__name__, "message": str(exc)})

    def createLayout(self):
        """Creates the menus, actions, widgets and models of the four tabs (visualizer.py:220)."""

        self.reg_ex01 = "-?[0-9]+[.]?[0-9]{,4}"

        self.fileMenu = QtMenu(self.boundary, "fileMenu", "&File")

        self.saveFile = QtAction(self.boundary, "saveFile", "&Save", self.fileMenu)
        self.saveFile.setShortcut("Ctrl+S")
        self.saveFile.setStatusTip("Save File")
        self.saveFile.setEnabled(False)
        self.saveFile.triggered.connect(self.saveFileCallBack)

        self.openFile = QtAction(self.boundary, "openFile", "&Open", self.fileMenu)
        self.openFile.setShortcut("Ctrl+O")
        self.openFile.setStatusTip("Open File")
        self.openFile.triggered.connect(self.openFileCallBack)

        self.importMenu = QtMenu(self.boundary, "importMenu", "&Import", self.fileMenu)

        self.openFUSAR = QtAction(self.boundary, "openFUSAR", "&hd5", self.importMenu)
        self.openFUSAR.setStatusTip("Import hd5 file")
        self.openFUSAR.triggered.connect(self.importFuSARCallBack)

        self.openRAT = QtAction(self.boundary, "openRAT", "&rat", self.importMenu)
        self.openRAT.setStatusTip("Import rat file")
        self.openRAT.triggered.connect(self.importRATCallBack)

        self.openUAVSAR = QtAction(self.boundary, "openUAVSAR", "&h5", self.importMenu)
        self.openUAVSAR.setStatusTip("Import h5 file")
        self.openUAVSAR.triggered.connect(self.importUAVSARCallBack)

        self.openNpy = QtAction(self.boundary, "openNpy", "&npy", self.importMenu)
        self.openNpy.setStatusTip("Import npy file")
        self.openNpy.triggered.connect(self.importNpyCallBack)

        self.dataMenu = QtMenu(self.boundary, "dataMenu", "&Data")
        self.ChMenu = QtMenu(self.boundary, "ChMenu", "&Channel", self.dataMenu)
        self.ChMenu.setEnabled(False)

        self.allChMenu = QtAction(self.boundary, "allChMenu", "&RGB", self.ChMenu, checkable=True)
        self.allChMenu.setShortcut("Ctrl+F")
        self.allChMenu.setStatusTip("All channels")
        self.allChMenu.triggered.connect(self.chChanged)
        self.allChMenu.setChecked(True)

        self.ch1Menu = QtAction(self.boundary, "ch1Menu", "&Red", self.ChMenu, checkable=True)
        self.ch1Menu.setStatusTip("First channel")
        self.ch1Menu.triggered.connect(self.chChanged)

        self.ch2Menu = QtAction(self.boundary, "ch2Menu", "&Green", self.ChMenu, checkable=True)
        self.ch2Menu.setStatusTip("Second channel")
        self.ch2Menu.triggered.connect(self.chChanged)

        self.ch3Menu = QtAction(self.boundary, "ch3Menu", "&Blue", self.ChMenu, checkable=True)
        self.ch3Menu.setStatusTip("Third channel")
        self.ch3Menu.triggered.connect(self.chChanged)

        self.chOpt = {self.ch1Menu: 0, self.ch2Menu: 1, self.ch3Menu: 2}

        self.ag = QtActionGroup()
        self.ag.addAction(self.allChMenu)
        self.ag.addAction(self.ch1Menu)
        self.ag.addAction(self.ch2Menu)
        self.ag.addAction(self.ch3Menu)

        self.imv1_1 = PgImageViewModel("imv1_1")
        self.imv1_2 = PgImageViewModel("imv1_2")
        self.imv1 = QtStackedWidget(self.boundary, "imv1", ["imv1_1", "imv1_2"])

        self.roi_1 = PgLineSegmentRoiModel(
            [[0, 0], [50, 64]],
            self.boundary,
            pen=((255, 255, 255), 3),
            hoverPen=((255, 255, 255), 3),
            handlePen=(255, 255, 255),
            handleHoverPen=(255, 255, 0),
            translateSnap=True, removable=False
        )

        self.imv2_1 = PgImageViewModel("imv2_1")
        self.imv2_2 = PgImageViewModel("imv2_2")
        self.imv2 = QtStackedWidget(self.boundary, "imv2", ["imv2_1", "imv2_2"])

        self.tab1Slider = QtSlider(self.boundary, "tab1Slider")
        self.tab1Slider.setMinimum(0)
        self.tab1Slider.setMaximum(1)
        self.tab1Slider.setEnabled(False)

        self.tab1ChkBox = QtCheckBox(self.boundary, "tab1ChkBox")
        self.tab1ChkBox.setChecked(False)
        self.tab1ChkBox.setEnabled(False)

        self.tab1SpinBox = QtSpinBox(self.boundary, "tab1SpinBox")
        self.tab1SpinBox.setSingleStep(1)
        self.tab1SpinBox.setEnabled(False)

        self.tab1PlayButton = QtPushButton(self.boundary, "tab1PlayButton", "", "play")
        self.tab1PlayButton.setEnabled(False)

        self.tab1ComboBox = QtComboBox(self.boundary, "tab1ComboBox")
        for cmaps in self.tools.colortables()[0]:
            self.tab1ComboBox.addItem(cmaps)
        self.tab1ComboBox.setCurrentIndex(self.cmap)
        self.tab1ComboBox.setEnabled(False)

        self.tab1QLineEdit1 = QtLineEdit(self.boundary, "tab1QLineEdit1")
        self.tab1QLineEdit1.setValidator(QtRegExpValidator(self.reg_ex01))
        self.tab1QLineEdit1.setEnabled(False)

        self.tab1QLineEdit2 = QtLineEdit(self.boundary, "tab1QLineEdit2")
        self.tab1QLineEdit2.setValidator(QtRegExpValidator(self.reg_ex01))
        self.tab1QLineEdit2.setEnabled(False)

        self.tab1QLineEdit3 = QtLineEdit(self.boundary, "tab1QLineEdit3")
        self.tab1QLineEdit3.setValidator(QtRegExpValidator(self.reg_ex01))
        self.tab1QLineEdit3.setEnabled(False)

        self.tab1QLineEdit4 = QtLineEdit(self.boundary, "tab1QLineEdit4")
        self.tab1QLineEdit4.setValidator(QtRegExpValidator(self.reg_ex01))
        self.tab1QLineEdit4.setEnabled(False)

        self.tab1QLineEdit5 = QtLineEdit(self.boundary, "tab1QLineEdit5")
        self.tab1QLineEdit5.setValidator(QtRegExpValidator(self.reg_ex01))
        self.tab1QLineEdit5.setEnabled(False)

        self.tab1QLineEdit6 = QtLineEdit(self.boundary, "tab1QLineEdit6")
        self.tab1QLineEdit6.setValidator(QtRegExpValidator(self.reg_ex01))
        self.tab1QLineEdit6.setEnabled(False)

        Ax, Ay, Bx, By, theta, d = self.computeLinePar()

        self.tab1QLineEdit1.setPlaceholderText('%.4f' % Ax)
        self.tab1QLineEdit2.setPlaceholderText('%.4f' % Ay)
        self.tab1QLineEdit3.setPlaceholderText('%.4f' % math.degrees(theta))
        self.tab1QLineEdit4.setPlaceholderText('%.4f' % d)
        self.tab1QLineEdit5.setPlaceholderText('%.4f' % self.roi_1.getState()['pos'][0])
        self.tab1QLineEdit6.setPlaceholderText('%.4f' % self.roi_1.getState()['pos'][1])

        self.tab1SetButton = QtPushButton(self.boundary, "tab1SetButton", "Set")
        self.tab1SetButton.setEnabled(False)

        self.tab1PlotButton = QtPushButton(self.boundary, "tab1PlotButton", "Plot")
        self.tab1PlotButton.setEnabled(False)

        self.imv1.setCurrentWidget(self.imv1_2)
        self.imv2.setCurrentWidget(self.imv2_2)

        self.tab2Plot = TomoVisFigure("plot", self.logger)

        self.tab2ChkBox1 = QtCheckBox(self.boundary, "tab2ChkBox1")
        self.tab2ChkBox1.setChecked(False)
        self.tab2ChkBox1.setEnabled(False)

        self.tab2ChkBox2 = QtCheckBox(self.boundary, "tab2ChkBox2")
        self.tab2ChkBox2.setChecked(False)
        self.tab2ChkBox2.setEnabled(False)

        self.tab2Slider = QtSlider(self.boundary, "tab2Slider")
        self.tab2Slider.setMinimum(2)
        self.tab2Slider.setMaximum(25)
        self.tab2Slider.setValue(2)
        self.tab2Slider.setEnabled(False)

        self.tab2ComboBox = QtComboBox(self.boundary, "tab2ComboBox")
        for cmaps in self.tools.PLOT_COLORMAPS:
            self.tab2ComboBox.addItem(cmaps)
        self.tab2ComboBox.setCurrentText('jet')
        self.tab2ComboBox.setEnabled(False)

        self.tab2ChkBox3 = QtCheckBox(self.boundary, "tab2ChkBox3")
        self.tab2ChkBox3.setChecked(False)

        self.tab2SpinBox = QtDoubleSpinBox(self.boundary, "tab2SpinBox")
        self.tab2SpinBox.setDecimals(2)
        self.tab2SpinBox.setSingleStep(1.0)
        self.tab2SpinBox.setRange(-1e5, 1e5)
        self.tab2SpinBox.setEnabled(False)

        self.tab2ChkBox4 = QtCheckBox(self.boundary, "tab2ChkBox4")
        self.tab2ChkBox4.setChecked(False)
        self.tab2ChkBox4.setEnabled(False)

        self.tab2AxesButton = QtPushButton(self.boundary, "tab2AxesButton", "Axes")
        self.tab2AxesButton.setEnabled(False)

        self.tab2PlotButton = QtPushButton(self.boundary, "tab2PlotButton", "Plot")
        self.tab2PlotButton.setEnabled(False)

        self.tab2ClearButton = QtPushButton(self.boundary, "tab2ClearButton", "Clear")
        self.tab2ClearButton.setEnabled(False)

        self.tab3Plot = TomoVisFigure("profile", self.logger)

        self.tab3ClearButton = QtPushButton(self.boundary, "tab3ClearButton", "Clear")
        self.tab3ClearButton.setEnabled(False)

        self.colormapTab4Button = QtPushButton(self.boundary, "colormapTab4Button", "colormap")
        self.colormapTab4Button.setEnabled(True)

        self.resetCamerasTab4Button = QtPushButton(self.boundary, "resetCamerasTab4Button", "reset cameras")
        self.resetCamerasTab4Button.setEnabled(True)

        self.channelTab4Button = QtPushButton(self.boundary, "channelTab4Button", "channel")
        self.channelTab4Button.setEnabled(True)

        self.turntableCameraTab4Button = QtRadioButton(self.boundary, "turntableCameraTab4Button", "Turntable")
        self.turntableCameraTab4Button.setChecked(True)
        self.flyCameraTab4Button = QtRadioButton(self.boundary, "flyCameraTab4Button", "Fly")
        self.arcballCameraTab4Button = QtRadioButton(self.boundary, "arcballCameraTab4Button", "Arcball")

        self.mipProjectionTab4Button = QtRadioButton(self.boundary, "mipProjectionTab4Button", "MIP")
        self.mipProjectionTab4Button.setChecked(True)
        self.isoProjectionTab4Button = QtRadioButton(self.boundary, "isoProjectionTab4Button", "ISO")
        self.translucentProjectionTab4Button = QtRadioButton(self.boundary, "translucentProjectionTab4Button", "Translucent")
        self.additiveProjectionTab4Button = QtRadioButton(self.boundary, "additiveProjectionTab4Button", "Additive")

        self.isoThresholdTab4Slider = QtSlider(self.boundary, "isoThresholdTab4Slider")
        self.isoThresholdTab4Slider.setEnabled(False)

        self.tabWidget = QtTabWidget(self.boundary, "tabWidget")
        self.tabWidget.addTab("Slicer")
        self.tabWidget.addTab("Plot")
        self.tabWidget.addTab("Profile")
        if self.has3d:
            self.tab3d_index = self.tabWidget.addTab("3D")

    def getCurrentMetadata(self):
        """Returns the 36 session metadata values (F-021) (visualizer.py:683)."""

        Ax, Ay, Bx, By, theta, d = self.computeLinePar()

        metadata = {
            "app_name": self.name,
            "x_label": self.x_label,
            "z_label": self.z_label,
            "x_min": float(self.x_min),
            "x_max": float(self.x_max),
            "x_label_view": str(self.x_label_view),
            "x_view_min": float(self.x_view_min),
            "x_view_max": float(self.x_view_max),
            "z_min": float(self.z_range[0]),
            "z_max": float(self.z_range[1]),
            "z_view_min": float(self.z_view_range[0]),
            "z_view_max": float(self.z_view_range[1]),
            "x_res": float(self.x_res),
            "y_res": float(self.y_res),
            "cmap_index": int(self.cmap),
            "cmap_name_tab1": str(self.tab1ComboBox.currentText()),
            "cmap_name_tab2": str(self.tab2ComboBox.currentText()),
            "slice_checkbox": bool(self.tab1ChkBox.isChecked()),
            "slice_index": int(self.tab1SpinBox.value()),
            "full_view": bool(self.tab2ChkBox4.isChecked()),
            "normalize": bool(self.tab2ChkBox1.isChecked()),
            "hist_eq": bool(self.tab2ChkBox2.isChecked()),
            "hist_bins": int(self.tab2Slider.value()),
            "x_line_enabled": bool(self.tab2ChkBox3.isChecked()),
            "x_line_value_m": float(self.tab2SpinBox.value()),
            "tab2_plotted": bool(self.tab2_plotted),
            "tab3_plotted": bool(self.tab3_plotted),
            "roi_Ax": float(Ax),
            "roi_Ay": float(Ay),
            "roi_Bx": float(Bx),
            "roi_By": float(By),
            "roi_angle_deg": float(math.degrees(theta)),
            "roi_length": float(d),
            "roi_pos_x": float(self.roi_1.getState()['pos'][0]),
            "roi_pos_y": float(self.roi_1.getState()['pos'][1]),
        }

        if self.nChannels > 1:
            checked_action = self.ag.checkedAction()
            if checked_action == self.allChMenu:
                metadata["channel_mode"] = "RGB"
            elif checked_action == self.ch1Menu:
                metadata["channel_mode"] = "Red"
            elif checked_action == self.ch2Menu:
                metadata["channel_mode"] = "Green"
            elif checked_action == self.ch3Menu:
                metadata["channel_mode"] = "Blue"
            else:
                metadata["channel_mode"] = "Unknown"
        else:
            metadata["channel_mode"] = "Single"

        return metadata

    def fileDialog(self, mode: str, title: str, name_filter: str, continuation) -> None:
        """Asks the browser for the QFileDialog TomoVis opened.

        Args:
            mode         : "open" (existing file) or "save".
            title        : Dialog title.
            name_filter  : The single name filter.
            continuation : Accepted half receiving the chosen path.
        """

        payload = {"mode": mode, "title": title, "filters": [name_filter], "selected_filter": name_filter, "directory": None, "file": None}
        self.dialogs.request("file", payload, lambda result: continuation(str(result.get("path") or "")))

    def saveFileCallBack(self):
        """File > Save: stops Play and asks for the target file (F-020) (visualizer.py:741)."""

        if self.tab1Timer.isActive():
            self.tab1Timer.stop()

        if self.data is None:
            self.dialogs.message(
                "warning",
                "No data",
                "There is no data loaded to save."
            )
            return

        self.fileDialog("save", "Save File", "Visualizer (*.hd5)", self.saveFileAccepted)

    def saveFileAccepted(self, filename):
        """Writes the session to the chosen file and reports the outcome (visualizer.py:741)."""

        if not filename:
            return

        if not filename.lower().endswith(".hd5"):
            filename += ".hd5"

        try:
            self.session_file.write(filename, self.data, self.getCurrentMetadata())

            self.dialogs.message(
                "information",
                "Save successful",
                f"File saved successfully:\n{filename}"
            )

        except Exception as e:
            self.dialogs.message(
                "critical",
                "Save error",
                f"Could not save file:\n{str(e)}"
            )

    def openFileCallBack(self):
        """File > Open: stops Play and asks for a session file (F-022) (visualizer.py:791)."""

        if self.tab1Timer.isActive():
            self.tab1Timer.stop()

        self.fileDialog("open", "Open File", "Visualizer (*.hd5)", self.openFileAccepted)

    def openFileAccepted(self, filename):
        """Restores a session file: cube, metadata, ROI, plots (visualizer.py:791)."""

        if not filename:
            return

        try:
            self.data, has_metadata = self.session_file.read(filename)

            self.initializeVisualizerWithData()

            if has_metadata:
                meta_dict = self.session_file.metadata(filename)
                self.applyMetadata(meta_dict)
                self.updatePositionROI()
                self.updateTomogram()

                tab2_was_plotted = bool(meta_dict.get("tab2_plotted", False))
                tab3_was_plotted = bool(meta_dict.get("tab3_plotted", False))

                self.tab2_plotted = False
                self.tab3_plotted = False

                if tab2_was_plotted:
                    self.restoreTab2ControlsFromMetadata(meta_dict)
                    self.plotTomogram(self.d2)
                    self.tab2ClearButton.setEnabled(True)
                    self.tab2AxesButton.setEnabled(True)

                    if tab3_was_plotted and self.tab2ChkBox3.isChecked():
                        self.updateProfilePlot()
                        self.tab3ClearButton.setEnabled(True)
                    else:
                        self.tab3ClearButtonClicked()
                else:
                    self.tab2ClearButtonClicked()
                    self.tab3ClearButtonClicked()

        except Exception as e:
            self.dialogs.message(
                "critical",
                "Open error",
                f"Could not open file:\n{str(e)}"
            )

    def importFailed(self, name, error):
        """Reports a failed import read without touching the loaded cube (D-3).

        Args:
            name  : File the reader failed on.
            error : The reader's exception.
        """

        self.console.print(f"Import error: {name}: {type(error).__name__}: {error}", level="warning")
        self.dialogs.message("critical", "Import error", f"Could not import file:\n{str(error)}")

    def importFuSARCallBack(self):
        """File > Import > hd5: stops Play and asks for the file (F-011) (visualizer.py:856)."""

        if self.tab1Timer.isActive():
            self.tab1Timer.stop()
        self.fileDialog("open", "Open File", "FuSAR Tomo (*.hd5)", self.importFuSARAccepted)

    def importFuSARAccepted(self, name):
        """Imports the chosen FuSAR Tomo file (visualizer.py:856)."""

        if name != '':
            try:
                cube = self.readers.fusar(name)
            except Exception as error:
                self.importFailed(name, error)
                return
            self.data = cube.data
            if cube.z_range is not None:
                self.z_range = cube.z_range
            else:
                self.setDefaultElevRangeIfMissing()
            if cube.x_res is not None:
                self.x_res = cube.x_res
            if cube.y_res is not None:
                self.y_res = cube.y_res

            self.initializeVisualizerWithData()

    def importUAVSARCallBack(self):
        """File > Import > h5: stops Play and asks for the file (F-012) (visualizer.py:891)."""

        if self.tab1Timer.isActive():
            self.tab1Timer.stop()
        self.fileDialog("open", "Open File", "UAVSAR Tomo (*.h5)", self.importUAVSARAccepted)

    def importUAVSARAccepted(self, name):
        """Imports the chosen UAVSAR Tomo file (visualizer.py:891)."""

        if name != '':
            try:
                data = self.readers.uavsar(name)
            except Exception as error:
                self.importFailed(name, error)
                return
            self.data = data
            self.setDefaultElevRangeIfMissing()
            self.initializeVisualizerWithData()

    def importNpyCallBack(self):
        """File > Import > npy: stops Play and asks for the file (F-013) (visualizer.py:909)."""

        if self.tab1Timer.isActive():
            self.tab1Timer.stop()
        self.fileDialog("open", "Open File", "Numpy (*.npy)", self.importNpyAccepted)

    def importNpyAccepted(self, name):
        """Imports the chosen .npy file (visualizer.py:909)."""

        if name != '':
            try:
                data = self.readers.npy(name)
            except Exception as error:
                self.importFailed(name, error)
                return
            self.data = data
            self.setDefaultElevRangeIfMissing()
            self.initializeVisualizerWithData()

    def importRATCallBack(self):
        """File > Import > rat: stops Play and asks for the file (F-014) (visualizer.py:925)."""

        if self.tab1Timer.isActive():
            self.tab1Timer.stop()
        self.fileDialog("open", "Open File", "RAT file (*.rat)", self.importRATAccepted)

    def importRATAccepted(self, name):
        """Imports the chosen RAT file (visualizer.py:925)."""

        if name != '':
            try:
                data = self.readers.rat(name)
            except Exception as error:
                self.importFailed(name, error)
                return
            self.data = data
            self.setDefaultElevRangeIfMissing()
            self.initializeVisualizerWithData()

    def setDefaultElevRangeIfMissing(self):
        """Sets the elevation range to [0, shape[-1] - 1] (F-015, Q-001) (visualizer.py:941)."""

        if self.data is None:
            return
        nz = self.data.shape[-1]
        self.z_range = [0, (nz - 1)]

    def initializeVisualizerWithData(self):
        """Initialises controls and views for a newly loaded cube (F-017, F-018) (visualizer.py:947)."""

        self.volume_present = False
        self.volume_rendered = False
        self.tab2_plotted = False
        self.tab3_plotted = False

        if hasattr(self, "slice_line"):
            self.imv1_1.removeItem(self.slice_line)
            self.imv1_2.removeItem(self.slice_line)
            self.slice_line.hide()

        if self.data is not None:
            self.saveFile.setEnabled(True)
            self.tab1Slider.setEnabled(False)
            self.tab1ChkBox.setEnabled(False)
            self.tab1ChkBox.setChecked(False)
            self.tab1ChkBox.setEnabled(True)
            self.tab1PlotButton.setEnabled(True)
            self.tab1SetButton.setEnabled(True)
            self.tab1QLineEdit1.setEnabled(True)
            self.tab1QLineEdit2.setEnabled(True)
            self.tab1QLineEdit3.setEnabled(True)
            self.tab1QLineEdit4.setEnabled(True)
            self.tab1QLineEdit5.setEnabled(True)
            self.tab1QLineEdit6.setEnabled(True)

            if self.data.ndim == 5:
                self.data = np.moveaxis(np.sqrt(self.data[:, :, ...].diagonal()), -1, 0)

            if self.data.ndim > 3:
                self.nChannels = self.data.shape[0]
                if self.nChannels == 2:
                    self.ch3Menu.setEnabled(False)
                elif self.nChannels == 4:
                    self.data = self.data[[0, 1, 3], ...]
                    self.nChannels = 3
                self.tab1ComboBox.setEnabled(False)
                self.ChMenu.setEnabled(True)
                self.allChMenu.setChecked(True)
                self.imv1_2.addItem(self.roi_1)

                if hasattr(self, "slice_line"):
                    self.imv1_2.addItem(self.slice_line)

            else:
                self.nChannels = 1
                self.tab1ComboBox.setEnabled(True)
                self.ChMenu.setEnabled(False)
                self.imv1_1.addItem(self.roi_1)

                if hasattr(self, "slice_line"):
                    self.imv1_1.addItem(self.slice_line)

            nz = self.data.shape[-1]
            self.z_axis = np.linspace(float(self.z_range[0]), float(self.z_range[1]), num=nz)
            self.z_range = [float(self.z_axis[0]), float(self.z_axis[-1])]
            self.z_view_range = [float(self.z_range[0]), float(self.z_range[1])]

            self.tabWidget.setCurrentIndex(0)
            mid = nz // 2
            self.tab1Slider.setMaximum(nz - 1)
            self.tab1Slider.setValue(mid)
            self.tab1SpinBox.setMaximum(self.tab1Slider.maximum())
            self.tab1SpinBox.setValue(mid)

            if hasattr(self, "slice_line"):
                self.slice_line.setPos(self.tab1SpinBox.value())
                self.slice_line.hide()

            self.updatePositionROI()
            self.updateTomogram()
            self.updateXAxisLimits()

            self.isoThresholdTab4Slider.setEnabled(False)
        else:
            self.tab1Slider.setMaximum(1)

    def ensure3DLoaded(self):
        """Prepares the 3D volume when the 3D tab is shown for a new cube (F-091, F-092) (visualizer.py:1034)."""

        if not self.has3d:
            return

        if self.data is None:
            return

        if not self.volume_present:
            self.volume_present = True

        if not self.volume_rendered:
            dataV = exposure.equalize_hist(np.abs(self.data), 2048).astype(np.float32)

            dataV = dataV[::8, ::8, ::2]

            self.volume_data = np.ascontiguousarray(dataV)
            self.volume_serial += 1

            self.isoThresholdTab4Slider.setMaximum(100)
            self.isoThresholdTab4Slider.setMinimum(1)
            self.isoThresholdTab4Slider.setValue(1)
            self.isoThresholdTab4Slider.setTickInterval(-1)
            self.isoThresholdTab4Slider.setEnabled(True)

            self.volume_rendered = True

    def onTabChanged(self, index):
        """Loads the 3D view when its tab becomes current (visualizer.py:1068)."""

        if self.tab3d_index is not None and index == self.tab3d_index:
            self.ensure3DLoaded()

    def signals(self):
        """Connects the slots of the non-3D widgets (visualizer.py:1072)."""

        self.roi_1.sigRegionChanged.connect(self.updateTomogram)
        self.roi_1.sigRegionChanged.connect(self.updatePositionROI)
        self.tab1Timer.timeout.connect(self.runTab1Slider)
        self.tab1ComboBox.currentTextChanged.connect(self.tab1UpdateColormap)
        self.tab1SetButton.clicked.connect(self.tab1SetButtonClicked)
        self.tab1PlayButton.clicked.connect(self.tab1PlayButtonClicked)
        self.tab1ChkBox.stateChanged.connect(self.tab1ChkBoxChanged)
        self.tab1Slider.valueChanged.connect(self.tab1SliderChanged)
        self.tab1SpinBox.valueChanged.connect(self.tab1SpinBoxChanged)
        self.tab1PlotButton.clicked.connect(self.tab1PlotButtonClicked)

        self.tab2ComboBox.currentTextChanged.connect(self.tab2ChkBox2Changed)
        self.tab2ClearButton.clicked.connect(self.tab2ClearButtonClicked)
        self.tab2ChkBox2.stateChanged.connect(self.tab2ChkBox2Changed)
        self.tab2Slider.valueChanged.connect(self.tab2SliderChanged)
        self.tab2ChkBox3.stateChanged.connect(self.tab2ChkBox3Changed)
        self.tab2ChkBox4.stateChanged.connect(self.tab2ChkBox4Changed)
        self.tab2SpinBox.valueChanged.connect(self.tab2SpinBoxChanged)
        self.tab2PlotButton.clicked.connect(self.tab2PlotButtonClicked)
        self.tab2ChkBox1.stateChanged.connect(self.tab2ChkBox1Changed)
        self.tab2AxesButton.clicked.connect(self.tab2AxesButtonClicked)

        self.tab3ClearButton.clicked.connect(self.tab3ClearButtonClicked)
        self.tabWidget.currentChanged.connect(self.onTabChanged)

    def moveSliceLineTo(self, target_view):
        """Moves the slice line into another top view (visualizer.py:1111)."""

        if not hasattr(self, "slice_line"):
            return

        current_scene = self.slice_line.scene()
        target_scene = target_view.scene

        if current_scene is not None and current_scene is not target_scene:
            current_scene.removeItem(self.slice_line)

        if self.slice_line.scene() is None:
            target_view.addItem(self.slice_line)

    def chChanged(self):
        """Data > Channel: switches the displayed channel (F-048), stopping before the display without data (E-007) (visualizer.py:1124)."""

        if self.tab1Timer.isActive():
            self.tab1Timer.stop()

        self.tabWidget.setCurrentIndex(0)
        self.tab2ClearButtonClicked()
        self.tab2ChkBox3.setEnabled(True)

        if self.nChannels > 1 and self.allChMenu.isChecked() is False and self.roiFlag is False:
            self.imv1_2.removeItem(self.roi_1)
            self.imv1_1.addItem(self.roi_1)

            self.moveSliceLineTo(self.imv1_1)
            self.slice_line.hide()

            self.roiFlag = True

        elif self.nChannels > 1 and self.allChMenu.isChecked() is True and self.roiFlag is True:
            self.imv1_1.removeItem(self.roi_1)
            self.imv1_2.addItem(self.roi_1)

            self.moveSliceLineTo(self.imv1_2)
            self.slice_line.hide()

            self.roiFlag = False

        if self.data is None:
            return

        self.displayData()

        if self.tab1ChkBox.isChecked() is True:
            if hasattr(self, "slice_line"):
                self.slice_line.setPos(self.tab1SpinBox.value())
                self.slice_line.show()
            self.valueChanged()
        else:
            if hasattr(self, "slice_line"):
                self.slice_line.hide()
            self.updateTomogram()

        if self.nChannels > 1 and self.allChMenu.isChecked() is True:
            self.tab1ComboBox.setEnabled(False)
        else:
            self.tab1ComboBox.setEnabled(True)

    def displayData(self):
        """Shows the top view: mono sqrt-sum or RGB composite (F-031, F-032) (visualizer.py:1168)."""

        if self.nChannels > 1 and self.allChMenu.isChecked() is True:
            data = [(np.sum(np.abs(self.data[0]), axis=0) ** 2).T]
            for i in range(1, self.nChannels):
                data.append((np.sum(np.abs(self.data[i]), axis=0) ** 2).T)
            if self.nChannels == 2:
                data.append(np.zeros(data[0].shape, dtype=np.float32))

            img01 = np.rollaxis(np.rollaxis(np.array(data), 2, 0), 2, 1)
            aux = np.zeros(img01.shape, dtype='uint8')
            index = [1, 0, 2]
            for i in range(0, self.nChannels):
                aux[..., i] = self.tools.normalize(img01[..., index[i]], 0, 255)

            img = Image.fromarray(aux, mode='RGB')
            self.img = self.tools.sanitize_for_display(np.array(img), dtype=np.uint8)

            self.imv1_2.setImage(self.img, autoRange=False, autoLevels=False, autoHistogramRange=False)

            mins = []
            maxs = []
            for i in range(self.img.shape[2]):
                low, high = np.percentile(self.img[..., i], [1, 99])
                mins.append(low)
                maxs.append(high)

            self.imv1_2.setHistogramRange(min(mins), max(maxs))
            self.imv1_2.setLevels(mins, maxs)
            self.imv1.setCurrentWidget(self.imv1_2)
            return

        elif self.nChannels > 1:
            img = np.sum(np.abs(self.data[self.chOpt[self.ag.checkedAction()]]), axis=0) ** 0.5
        else:
            img = np.sum(np.abs(self.data), axis=0) ** 0.5

        img = self.tools.sanitize_for_display(img, dtype=np.float32)

        self.img = img

        self.imv1_1.setImage(self.img, autoRange=False, autoLevels=False, autoHistogramRange=False)
        self.imv1_1.setColorMap(self.color)

        low, high = np.percentile(self.img, [1, 99])
        self.imv1_1.setHistogramRange(low, high)
        self.imv1_1.setLevels(low, high)
        self.imv1.setCurrentWidget(self.imv1_1)

    def displayTomogram(self):
        """Shows the tomogram view: mono or RGB (F-038, F-039) (visualizer.py:1216)."""

        if self.nChannels > 1 and self.allChMenu.isChecked() is True:
            d2 = np.zeros([self.aux.shape[0], self.aux.shape[1], self.aux.shape[2]], dtype='uint8')
            self.d2 = np.zeros([self.aux.shape[0], self.aux.shape[1], self.aux.shape[2]], dtype=np.float32)
            index = [1, 0, 2]

            for i in range(0, self.nChannels):
                d2[..., i] = self.tools.normalize(self.aux[..., index[i]], 0, 255)
                self.d2[..., i] = self.tools.sanitize_for_display(self.aux[..., index[i]], dtype=np.float32)

            if self.nChannels == 2:
                rgb = np.ones([d2.shape[0], d2.shape[1], 3], dtype='uint8')
                rgb[..., 0:2] = d2
                d2 = rgb

            img = Image.fromarray(d2, mode='RGB')
            img_np = self.tools.sanitize_for_display(np.array(img), dtype=np.uint8)

            self.imv2_2.setImage(img_np, autoRange=False, autoLevels=False, autoHistogramRange=False)
            self.imv2_2.setHistogramRange(0.0, 20 * np.mean(d2))

            min_vals = [0.0]
            max_vals = [2.5 * np.mean(d2[..., 0])]
            for i in range(1, self.nChannels):
                min_vals.append(0.0)
                max_vals.append(2.5 * np.mean(d2[..., i]))

            self.imv2_2.setLevels(min_vals, max_vals)
            self.imv2.setCurrentWidget(self.imv2_2)
            return

        else:
            self.d2 = self.tools.sanitize_for_display(self.d2, dtype=np.float32)
            self.imv2_1.setImage(self.d2, autoRange=False, autoLevels=False, autoHistogramRange=False)

        self.imv2_1.setColorMap(self.color)
        fak = 5.0 if self.cmap == 4 else 2.5
        self.imv2_1.setHistogramRange(0.0, 20 * np.mean(self.d2))
        self.imv2_1.setLevels(0.0 * np.mean(self.d2), fak * np.mean(self.d2))
        self.imv2.setCurrentWidget(self.imv2_1)

    def clearTomogramViews(self):
        """Clears the tomogram and both tomogram views (F-040) (visualizer.py:1257)."""

        self.d2 = None
        self.aux = None

        self.imv2_1.clear()

        self.imv2_2.clear()

    def updateTomogram(self):
        """Extracts the tomogram along the clipped ROI line and redraws both panes (F-037) (visualizer.py:1271)."""

        line = self.getEffectiveROILine()
        if line is None:
            self.clearTomogramViews()
            return

        if self.nChannels > 1 and self.allChMenu.isChecked() is True:
            target_view = self.imv1_2
            image_item = self.imv1_2.imageItem
        else:
            target_view = self.imv1_1
            image_item = self.imv1_1.imageItem

        clipped_roi = self.createClippedROI(target_view)
        if clipped_roi is None:
            self.clearTomogramViews()
            return

        try:
            if self.nChannels > 1 and self.allChMenu.isChecked() is True:
                region0 = clipped_roi.getArrayRegion(
                    self.data[0],
                    image_item,
                    axes=(1, 2)
                )

                if region0 is None:
                    self.clearTomogramViews()
                    return

                region0 = np.rot90(region0, 3)

                if region0.shape[0] == 0 or region0.shape[1] == 0:
                    self.clearTomogramViews()
                    return

                self.aux = np.zeros(
                    (region0.shape[0], region0.shape[1], self.nChannels),
                    dtype=np.float32
                )

                for i in range(self.nChannels):
                    region_i = clipped_roi.getArrayRegion(
                        np.abs(self.data[i]),
                        image_item,
                        axes=(1, 2)
                    )

                    if region_i is None:
                        self.clearTomogramViews()
                        return

                    region_i = np.rot90(region_i, 3)

                    if region_i.shape[0] == 0 or region_i.shape[1] == 0:
                        self.clearTomogramViews()
                        return

                    self.aux[:, :, i] = region_i

            elif self.nChannels > 1:
                region = clipped_roi.getArrayRegion(
                    np.abs(self.data[self.chOpt[self.ag.checkedAction()]]),
                    image_item,
                    axes=(1, 2)
                )

                if region is None:
                    self.clearTomogramViews()
                    return

                self.d2 = np.rot90(region, 3)

                if self.d2.shape[0] == 0 or self.d2.shape[1] == 0:
                    self.clearTomogramViews()
                    return

            else:
                region = clipped_roi.getArrayRegion(
                    np.abs(self.data),
                    image_item,
                    axes=(1, 2)
                )

                if region is None:
                    self.clearTomogramViews()
                    return

                self.d2 = np.rot90(region, 3)

                if self.d2.shape[0] == 0 or self.d2.shape[1] == 0:
                    self.clearTomogramViews()
                    return

            self.updateXAxisLimits()
            self.displayData()
            self.displayTomogram()

        finally:
            target_view.removeItem(clipped_roi)

    def valueChanged(self):
        """Extracts the slice tomogram at the spin box index and redraws (F-044) (visualizer.py:1375)."""

        if self.nChannels > 1 and self.allChMenu.isChecked() is True:
            self.aux = np.zeros(
                [
                    np.rot90(self.data[0, :, :, self.tab1SpinBox.value()], 3).shape[0],
                    np.rot90(self.data[0, :, :, self.tab1SpinBox.value()], 3).shape[1],
                    self.nChannels
                ]
            )
            for i in range(self.nChannels):
                self.aux[:, :, i] = np.rot90(np.abs(self.data[i, :, :, self.tab1SpinBox.value()]), 3)
        elif self.nChannels > 1:
            self.d2 = np.rot90(np.abs(self.data[self.chOpt[self.ag.checkedAction()], ..., self.tab1SpinBox.value()]), 3)
        else:
            self.d2 = np.rot90(np.abs(self.data[..., self.tab1SpinBox.value()]), 3)
        self.updateXAxisLimits()
        self.displayData()
        self.displayTomogram()

    def plotTomogram(self, d2toPlot):
        """Draws the Plot tab image (F-061, F-062, F-063) (visualizer.py:1394)."""

        if d2toPlot is None:
            self.tab2_plotted = False
            mv = self.tab2Plot.getFigure()
            mv.clear()
            self.tab2Plot.draw()
            return

        self.rgbArray = None
        self.d2Norm = None

        extent = [self.x_view_min, self.x_view_max, self.z_view_range[0], self.z_view_range[1]]

        mv = self.tab2Plot.getFigure()
        mv.clear()
        plot = mv.add_subplot(self.subplot)

        if self.nChannels > 1 and self.allChMenu.isChecked() is True:
            self.rgbArray = np.zeros((d2toPlot.T[0].shape[0], d2toPlot.T[0].shape[1], 3))
            rgbArray = np.zeros((d2toPlot.T[0].shape[0], d2toPlot.T[0].shape[1], 3), dtype='uint8')

            for j in range(self.nChannels):
                if self.tab2ChkBox1.isChecked() is True:
                    for i in range(d2toPlot.T.shape[-1]):
                        self.rgbArray[:, i, j] = self.tools.normalize(d2toPlot[i, :, j].T, 0, 1)
                        rgbArray[:, i, j] = self.tools.normalize(self.rgbArray[:, i, j], 0, 255)
                else:
                    self.rgbArray[..., j] = d2toPlot[..., j].T
                    rgbArray[..., j] = self.tools.normalize(self.rgbArray[..., j], 0, 255)

            plot.imshow(rgbArray, aspect='auto', extent=extent)

            if self.tab2SpinBox.isEnabled() is True:
                x_line = float(self.tab2SpinBox.value())
                plot.axvline(x=x_line, color='white', linewidth=5)

            mv.subplots_adjust(left=0.09, right=0.97, top=0.9, bottom=0.1)

        else:
            self.d2Norm = np.zeros(d2toPlot.T.shape)

            if self.tab2ChkBox1.isChecked() is True:
                for i in range(d2toPlot.T.shape[-1]):
                    self.d2Norm[:, i] = self.tools.normalize(d2toPlot.T[:, i], 0, 1)
            else:
                self.d2Norm = d2toPlot.T

            cmap_obj = getattr(cm, self.tab2ComboBox.currentText())
            cax = plot.imshow(self.d2Norm, cmap=cmap_obj, aspect='auto', extent=extent)

            if self.tab2SpinBox.isEnabled() is True:
                x_line = float(self.tab2SpinBox.value())
                plot.axvline(x=x_line, color='white', linewidth=5)

            cbar = mv.colorbar(cax)
            cbar.ax.tick_params(labelsize=18)
            mv.subplots_adjust(left=0.12, right=1.0, top=0.9, bottom=0.1)

        plot.set_xlabel(self.x_label_view, fontsize=20)
        plot.set_ylabel(self.z_label, fontsize=20)
        plot.tick_params(labelsize=18)
        self.tab2_plotted = True
        self.tab2Plot.draw()

    def restoreTab2ControlsFromMetadata(self, metadata_attrs):
        """Restores the Plot tab controls from session metadata (F-024) (visualizer.py:1458)."""

        self.tab2ClearButton.setEnabled(True)
        self.tab2AxesButton.setEnabled(True)

        self.tab2ChkBox2.setEnabled(True)
        self.tab2Slider.setEnabled(True)
        self.tab2ChkBox1.setEnabled(True)
        self.tab2ChkBox4.setEnabled(True)

        if self.nChannels > 1 and self.allChMenu.isChecked() is True:
            self.tab2ComboBox.setEnabled(False)
            self.tab2PlotButton.setEnabled(False)
        else:
            self.tab2ComboBox.setEnabled(True)
            self.tab2ChkBox3.setEnabled(True)

        if "normalize" in metadata_attrs:
            self.tab2ChkBox1.setChecked(bool(metadata_attrs["normalize"]))

        if "hist_eq" in metadata_attrs:
            self.tab2ChkBox2.setChecked(bool(metadata_attrs["hist_eq"]))

        if "hist_bins" in metadata_attrs:
            self.tab2Slider.setValue(int(metadata_attrs["hist_bins"]))

        if "full_view" in metadata_attrs:
            self.tab2ChkBox4.setChecked(bool(metadata_attrs["full_view"]))

        if "cmap_name_tab2" in metadata_attrs:
            cmap_tab2 = str(metadata_attrs["cmap_name_tab2"])
            idx = self.tab2ComboBox.findText(cmap_tab2)
            if idx >= 0:
                self.tab2ComboBox.setCurrentIndex(idx)

        if "x_line_enabled" in metadata_attrs:
            x_line_enabled = bool(metadata_attrs["x_line_enabled"])
            self.tab2ChkBox3.setChecked(x_line_enabled)

            if x_line_enabled:
                self.tab2SpinBox.setMinimum(float(min(self.x_view_min, self.x_view_max)))
                self.tab2SpinBox.setMaximum(float(max(self.x_view_min, self.x_view_max)))
                self.tab2SpinBox.setEnabled(True)
                self.tab2ChkBox2.setEnabled(False)
                self.tab2PlotButton.setEnabled(True)
            else:
                self.tab2SpinBox.setEnabled(False)
                self.tab2PlotButton.setEnabled(False)

        if "x_line_value_m" in metadata_attrs:
            self.tab2SpinBox.setValue(float(metadata_attrs["x_line_value_m"]))

    def tab1PlotButtonClicked(self):
        """Slicer Plot: resets the Plot tab controls and plots the tomogram (F-049) (visualizer.py:1509)."""

        if self.tab1Timer.isActive() is True:
            self.tab1Timer.stop()

        self.tabWidget.setCurrentIndex(1)
        self.tab2ClearButton.setEnabled(True)
        self.tab2AxesButton.setEnabled(True)

        self.tab2ChkBox2.setChecked(False)
        self.tab2ChkBox2.setEnabled(True)
        self.tab2Slider.setEnabled(True)
        self.tab2ChkBox1.setChecked(False)
        self.tab2ChkBox1.setEnabled(True)
        self.tab2ChkBox4.setChecked(False)
        self.tab2ChkBox4.setEnabled(True)
        self.tab2ChkBox3.setChecked(False)

        if self.nChannels > 1 and self.allChMenu.isChecked() is True:
            self.tab2ComboBox.setEnabled(False)
            self.tab2PlotButton.setEnabled(False)
        else:
            self.tab2ChkBox3.setEnabled(True)
            self.tab2ComboBox.setEnabled(True)

        self.updateXAxisLimits()
        self.syncXViewToAuto()
        self.plotTomogram(self.d2)

    def tab1UpdateColormap(self):
        """Slicer Colormap: rebuilds the colour map and redraws (F-047) (visualizer.py:1537)."""

        self.cmap = self.tab1ComboBox.currentIndex()
        self.color = PgColorMap(np.linspace(0.0, 1.0, 256), self.tools.colortables(self.cmap)[1], self.cmap)
        if self.tab1ChkBox.isChecked() is True:
            self.valueChanged()
        else:
            self.updateTomogram()

    def tab1ChkBoxChanged(self):
        """Slices (Automatic): switches between slice and ROI mode (F-042) (visualizer.py:1545)."""

        if self.tab1ChkBox.isEnabled() is True:
            if self.tab1Timer.isActive():
                self.tab1Timer.stop()

            if self.tab1ChkBox.isChecked() is True:
                self.tab1PlayButton.setEnabled(True)
                self.tab1Slider.setEnabled(True)
                self.tab1SpinBox.setEnabled(True)

                if hasattr(self, "slice_line"):
                    self.slice_line.setPos(self.tab1SpinBox.value())
                    self.slice_line.show()

                if any(slot == self.updateTomogram for slot, _ in self.roi_1.sigRegionChanged.slots):
                    self.roi_1.sigRegionChanged.disconnect(self.updateTomogram)

                self.valueChanged()

            else:
                self.tab1PlayButton.setEnabled(False)
                self.tab1Slider.setEnabled(False)
                self.tab1SpinBox.setEnabled(False)

                if hasattr(self, "slice_line"):
                    self.slice_line.hide()

                self.roi_1.sigRegionChanged.connect(self.updateTomogram)

                self.updateTomogram()

    def tab1SliderChanged(self):
        """Slice slider: forwards its value to the spin box (F-043) (visualizer.py:1581)."""

        self.tab1SpinBox.setValue(self.tab1Slider.value())

    def tab1SpinBoxChanged(self):
        """Slice spin box: moves the slider and slice line and extracts the slice (F-043) (visualizer.py:1584)."""

        self.tab1Slider.setSliderPosition(self.tab1SpinBox.value())

        if hasattr(self, "slice_line"):
            self.slice_line.setPos(self.tab1SpinBox.value())
            self.slice_line.show()

        self.valueChanged()

    def tab1PlayButtonClicked(self):
        """Play: starts or stops the 500 ms slice timer (F-046) (visualizer.py:1594)."""

        if self.tab1Timer.isActive():
            self.tab1Timer.stop()
            if self.nChannels == 1 or (self.nChannels > 1 and self.allChMenu.isChecked()):
                self.tab1ComboBox.setEnabled(True)
            self.tab1SpinBox.setEnabled(True)
        else:
            self.tab1Timer.start(500)
            self.tab1ComboBox.setEnabled(False)
            self.tab1SpinBox.setEnabled(False)

    def computeLinePar(self):
        """Returns the ROI endpoints, angle and length from its origin and handles (Q-024) (visualizer.py:1605)."""

        state = self.roi_1.getState()
        roi_pos_x = float(state['pos'][0])
        roi_pos_y = float(state['pos'][1])

        h0 = self.roi_1.handles[0]['item'].pos()
        h1 = self.roi_1.handles[1]['item'].pos()

        Ax = float(h0.x()) + roi_pos_x
        Ay = float(h0.y()) + roi_pos_y
        Bx = float(h1.x()) + roi_pos_x
        By = float(h1.y()) + roi_pos_y

        dx = Bx - Ax
        dy = By - Ay
        d = math.sqrt(dx ** 2 + dy ** 2)
        theta = math.atan2(dy, dx)

        return Ax, Ay, Bx, By, theta, d

    def clipLineToImage(self, Ax, Ay, Bx, By, width, height):
        """Clips a segment to the image box with Liang-Barsky (F-036) (visualizer.py:1625)."""

        xmin, xmax = 0.0, float(width - 1)
        ymin, ymax = 0.0, float(height - 1)

        dx = Bx - Ax
        dy = By - Ay

        p = [-dx, dx, -dy, dy]
        q = [Ax - xmin, xmax - Ax, Ay - ymin, ymax - Ay]

        u1, u2 = 0.0, 1.0

        for pi, qi in zip(p, q):
            if abs(pi) < 1e-12:
                if qi < 0:
                    return None
            else:
                r = qi / pi
                if pi < 0:
                    u1 = max(u1, r)
                else:
                    u2 = min(u2, r)

        if u1 > u2:
            return None

        x0 = Ax + u1 * dx
        y0 = Ay + u1 * dy
        x1 = Ax + u2 * dx
        y1 = Ay + u2 * dy

        return x0, y0, x1, y1

    def getCurrentImageShape(self):
        """Returns (width, height) of the top view image (visualizer.py:1658)."""

        if getattr(self, "img", None) is None:
            return None, None

        if self.img.ndim == 2:
            h, w = self.img.shape
        else:
            h, w = self.img.shape[:2]
        return w, h

    def getEffectiveROILine(self):
        """Returns the ROI line clipped to the top view, None when it misses (visualizer.py:1668)."""

        h, w = self.getCurrentImageShape()
        if h is None or w is None:
            return None

        Ax, Ay, Bx, By, _, _ = self.computeLinePar()

        clipped = self.clipLineToImage(Ax, Ay, Bx, By, w, h)
        if clipped is None:
            return None

        x0, y0, x1, y1 = clipped

        dx = x1 - x0
        dy = y1 - y0
        d_eff = math.sqrt(dx ** 2 + dy ** 2)
        theta_eff = math.atan2(dy, dx)

        return x0, y0, x1, y1, theta_eff, d_eff

    def createClippedROI(self, target_view):
        """Adds a temporary ROI on the clipped line to a view (visualizer.py:1688)."""

        line = self.getEffectiveROILine()
        if line is None:
            return None

        x0, y0, x1, y1, _, _ = line

        roi = PgLineSegmentRoiModel(
            [[x0, y0], [x1, y1]],
            self.boundary,
            pen=((255, 255, 255, 0), 1),
            hoverPen=((255, 255, 255, 0), 1),
            handlePen=(255, 255, 255, 0),
            handleHoverPen=(255, 255, 255, 0),
            translateSnap=True,
            removable=False
        )

        target_view.addItem(roi)
        return roi

    def getROIAxisMode(self):
        """Classifies the clipped line as azimuth, range or distance (visualizer.py:1708)."""

        line = self.getEffectiveROILine()
        if line is None:
            return "distance"

        _, _, _, _, theta_eff, _ = line

        dx = math.cos(theta_eff)
        dy = math.sin(theta_eff)
        eps = 1e-12

        if abs(dy) < eps:
            return "azimuth"

        if abs(dx) < eps:
            return "range"

        return "distance"

    def getEffectiveROIResolution(self):
        """Returns the metres per sample along the clipped line (visualizer.py:1729)."""

        line = self.getEffectiveROILine()
        if line is None:
            return self.x_res

        _, _, _, _, theta_eff, _ = line

        return math.sqrt(
            (self.x_res * math.cos(theta_eff)) ** 2 +
            (self.y_res * math.sin(theta_eff)) ** 2
        )

    def xPhysicalToIndex(self, x_value):
        """Maps a plotted x value to a tomogram column, round half to even (F-083) (visualizer.py:1741)."""

        if self.data is None:
            return 0

        if self.nChannels > 1 and self.allChMenu.isChecked() is True:
            if getattr(self, "aux", None) is None:
                return 0
            nx = self.aux.shape[0]
        else:
            if getattr(self, "d2", None) is None:
                return 0
            nx = self.d2.shape[0]

        if nx <= 0:
            return 0

        if nx == 1:
            return 0

        x0 = float(self.x_view_min)
        x1 = float(self.x_view_max)

        if abs(x1 - x0) < 1e-12:
            return 0

        idx = int(round((x_value - x0) * (nx - 1) / (x1 - x0)))
        idx = max(0, min(idx, nx - 1))
        return idx

    def syncXViewToAuto(self):
        """Copies the automatic x label and limits to the plotted ones (visualizer.py:1770)."""

        self.x_label_view = self.x_label
        self.x_view_min = self.x_min
        self.x_view_max = self.x_max

    def updateXAxisLimits(self):
        """Derives the automatic x label and limits (F-041) (visualizer.py:1775)."""

        if self.data is None:
            self.x_label = "Azimuth [m]"
            self.x_min = 0.0
            self.x_max = 1.0
            return

        nx = 0
        if self.nChannels > 1 and self.allChMenu.isChecked():
            if getattr(self, "aux", None) is not None:
                nx = self.aux.shape[0]
        else:
            if getattr(self, "d2", None) is not None:
                nx = self.d2.shape[0]

        if nx <= 0:
            self.x_label = "Azimuth [m]"
            self.x_min = 0.0
            self.x_max = 1.0
            return

        if self.tab1ChkBox.isChecked():
            self.x_label = "Azimuth [m]"
            self.x_min = 0.0
            self.x_max = (nx - 1) * self.x_res if nx > 1 else 0.0
            return

        line = self.getEffectiveROILine()
        if line is None:
            self.x_label = "Azimuth [m]"
            self.x_min = 0.0
            self.x_max = 1.0
            return

        x0, y0, x1, y1, theta_eff, _ = line
        mode = self.getROIAxisMode()
        roi_res = self.getEffectiveROIResolution()

        if mode == "azimuth":
            self.x_label = "Azimuth [m]"

            xmin_pix = min(x0, x1)
            xmax_pix = max(x0, x1)

            self.x_min = xmin_pix * self.x_res
            self.x_max = xmax_pix * self.x_res

        elif mode == "range":
            self.x_label = "Range [m]"

            ymin_pix = min(y0, y1)
            ymax_pix = max(y0, y1)

            self.x_min = ymin_pix * self.y_res
            self.x_max = ymax_pix * self.y_res

        else:
            self.x_label = "Projected distance along ROI [m]"

            self.x_min = 0.0
            self.x_max = (nx - 1) * roi_res if nx > 1 else 0.0

    def updatePositionROI(self):
        """Writes the ROI geometry into the six ROI fields (F-034) (visualizer.py:1843)."""

        Ax, Ay, Bx, By, theta, d = self.computeLinePar()

        self.tab1QLineEdit1.setText('%.4f' % Ax)
        self.tab1QLineEdit2.setText('%.4f' % Ay)
        self.tab1QLineEdit3.setText('%.4f' % math.degrees(theta))
        self.tab1QLineEdit4.setText('%.4f' % d)
        self.tab1QLineEdit5.setText('%.4f' % self.roi_1.getState()['pos'][0])
        self.tab1QLineEdit6.setText('%.4f' % self.roi_1.getState()['pos'][1])

    def applyMetadata(self, metadata_attrs):
        """Restores labels, ranges, colour map, ROI, channel and slice from session metadata (F-023) (visualizer.py:1853)."""

        try:

            if "x_label" in metadata_attrs:
                self.x_label = str(metadata_attrs["x_label"])

            if "x_min" in metadata_attrs:
                self.x_min = float(metadata_attrs["x_min"])

            if "x_max" in metadata_attrs:
                self.x_max = float(metadata_attrs["x_max"])

            if "x_label_view" in metadata_attrs:
                self.x_label_view = str(metadata_attrs["x_label_view"])
            else:
                self.x_label_view = self.x_label

            if "x_view_min" in metadata_attrs and "x_view_max" in metadata_attrs:
                self.x_view_min = float(metadata_attrs["x_view_min"])
                self.x_view_max = float(metadata_attrs["x_view_max"])
            else:
                self.x_view_min = float(self.x_min)
                self.x_view_max = float(self.x_max)

            if "z_label" in metadata_attrs:
                self.z_label = str(metadata_attrs["z_label"])

            if "z_min" in metadata_attrs and "z_max" in metadata_attrs:
                self.z_range = [
                    float(metadata_attrs["z_min"]),
                    float(metadata_attrs["z_max"])
                ]

            if "x_res" in metadata_attrs:
                self.x_res = float(metadata_attrs["x_res"])

            if "y_res" in metadata_attrs:
                self.y_res = float(metadata_attrs["y_res"])

            if "cmap_index" in metadata_attrs:
                self.cmap = int(metadata_attrs["cmap_index"])
                self.tab1ComboBox.setCurrentIndex(self.cmap)
                self.color = PgColorMap(
                    np.linspace(0.0, 1.0, 256),
                    self.tools.colortables(self.cmap)[1],
                    self.cmap
                )

            if all(k in metadata_attrs for k in ["roi_Ax", "roi_Ay", "roi_Bx", "roi_By", "roi_pos_x", "roi_pos_y"]):
                Ax = float(metadata_attrs["roi_Ax"])
                Ay = float(metadata_attrs["roi_Ay"])
                Bx = float(metadata_attrs["roi_Bx"])
                By = float(metadata_attrs["roi_By"])
                pos_x = float(metadata_attrs["roi_pos_x"])
                pos_y = float(metadata_attrs["roi_pos_y"])

                self.roi_1.setPos((pos_x, pos_y), update=False)

                self.roi_1.handles[0]['item'].setPos(Ax - pos_x, Ay - pos_y)
                self.roi_1.handles[1]['item'].setPos(Bx - pos_x, By - pos_y)

                self.roi_1.handles[0]['pos'] = (Ax - pos_x, Ay - pos_y)
                self.roi_1.handles[1]['pos'] = (Bx - pos_x, By - pos_y)

                self.roi_1.serial += 1
                self.roi_1.stateChanged(finish=True)

            if "channel_mode" in metadata_attrs and self.nChannels > 1:
                ch_mode = str(metadata_attrs["channel_mode"])

                if ch_mode == "RGB":
                    self.allChMenu.setChecked(True)
                elif ch_mode == "Red":
                    self.ch1Menu.setChecked(True)
                elif ch_mode == "Green":
                    self.ch2Menu.setChecked(True)
                elif ch_mode == "Blue":
                    self.ch3Menu.setChecked(True)

                self.chChanged()

            if "slice_checkbox" in metadata_attrs:
                self.tab1ChkBox.setChecked(bool(metadata_attrs["slice_checkbox"]))

            if "slice_index" in metadata_attrs:
                idx = int(metadata_attrs["slice_index"])
                idx = max(0, min(idx, self.tab1SpinBox.maximum()))
                self.tab1SpinBox.setValue(idx)

            if "z_view_min" in metadata_attrs and "z_view_max" in metadata_attrs:
                self.z_view_range = [
                    float(metadata_attrs["z_view_min"]),
                    float(metadata_attrs["z_view_max"])
                ]
            else:
                self.z_view_range = [float(self.z_range[0]), float(self.z_range[1])]

        except Exception as e:
            self.console.print("Metadata restore warning:", e, level="warning")

    def fieldsParse(self, texts):
        """Tells whether every ROI field holds a number (crash fix E-009).

        The validator lets "-" and "" stand as intermediate input, which
        ``float`` cannot convert; every Acceptable text is a decimal number.

        Args:
            texts : The six field texts.

        Returns:
            True when every text is Acceptable to the fields' validator.
        """

        return all(self.tab1QLineEdit1.validator.validate(text) == QtRegExpValidator.ACCEPTABLE for text in texts)

    def tab1SetButtonClicked(self):
        """Set: places the ROI from the six fields (F-035, E-009) (visualizer.py:1953)."""

        if (self.tab1QLineEdit1.text() != '' and self.tab1QLineEdit2.text() != '' and
            self.tab1QLineEdit3.text() != '' and self.tab1QLineEdit4.text() != '' and
            self.tab1QLineEdit5.text() != '' and self.tab1QLineEdit6.text() != '' and
            self.fieldsParse([self.tab1QLineEdit1.text(), self.tab1QLineEdit2.text(), self.tab1QLineEdit3.text(), self.tab1QLineEdit4.text(), self.tab1QLineEdit5.text(), self.tab1QLineEdit6.text()])):

            Ax = float(self.tab1QLineEdit1.text())
            Ay = float(self.tab1QLineEdit2.text())
            angle = float(self.tab1QLineEdit3.text())
            length = float(self.tab1QLineEdit4.text())
            pos_x = float(self.tab1QLineEdit5.text())
            pos_y = float(self.tab1QLineEdit6.text())

            Bx = Ax + (length * math.cos(math.radians(angle)))
            By = Ay + (length * math.sin(math.radians(angle)))

            if not (Ax == Bx and Ay == By):
                self.roi_1.setPos((pos_x, pos_y), update=False)

                self.roi_1.handles[0]['item'].setPos(Ax - pos_x, Ay - pos_y)
                self.roi_1.handles[1]['item'].setPos(Bx - pos_x, By - pos_y)

                self.roi_1.handles[0]['pos'] = (Ax - pos_x, Ay - pos_y)
                self.roi_1.handles[1]['pos'] = (Bx - pos_x, By - pos_y)

                self.roi_1.serial += 1
                self.roi_1.stateChanged(finish=True)

                self.updatePositionROI()
                if self.tab1ChkBox.isChecked() is False:
                    self.updateTomogram()

    def runTab1Slider(self):
        """Play timer tick: advances the slice slider and wraps at the end (F-046) (visualizer.py:1983)."""

        if self.tab1Slider.isEnabled() is True:
            if self.tab1Slider.value() == self.tab1Slider.maximum():
                self.tab1Slider.setValue(self.tab1Slider.minimum())
                return
            self.tab1Slider.setValue(self.tab1Slider.value() + 1)

    def plotProfile(self):
        """Draws the profile and switches to the Profile tab; returns False when nothing was drawn (E-011) (visualizer.py:1990)."""

        if not self.updateProfilePlot():
            return False
        self.tabWidget.setCurrentIndex(2)
        return True

    def updateProfilePlot(self):
        """Draws the Profile tab (F-081, F-082); returns False without a plotted tomogram (E-011) (visualizer.py:1995)."""

        mv = self.tab3Plot.getFigure()
        mv.clear()

        x_phys = float(self.tab2SpinBox.value())
        x_idx = self.xPhysicalToIndex(x_phys)

        if self.nChannels > 1 and self.allChMenu.isChecked() is True:
            if getattr(self, "rgbArray", None) is None:
                return False
            z = np.linspace(self.z_view_range[0], self.z_view_range[1], num=self.rgbArray.shape[0])
            h = []
            for j in range(self.nChannels):
                plot = mv.add_subplot(221 + j)
                line, = plot.plot(
                    z,
                    np.flipud(self.rgbArray[:, x_idx, j]),
                    linewidth=3,
                    label='Ch' + str(j + 1)
                )
                plot.legend(handles=[line], fontsize=10)

                if self.tab2ChkBox1.isChecked() is True:
                    plot.set_ylabel('Normalized Pseudo-Power', fontsize=20)
                else:
                    plot.set_ylabel('Pseudo-Power', fontsize=20)

                plot.set_xlabel(self.z_label, fontsize=20)
                plot.tick_params(labelsize=18)
                plot.grid()

                plot = mv.add_subplot(221 + self.nChannels)
                line, = plot.plot(
                    z,
                    np.flipud(self.rgbArray[:, x_idx, j]),
                    linewidth=3,
                    label='Ch' + str(j + 1)
                )
                h.append(line)

            plot.legend(handles=h, fontsize=20)
            plot.set_title(f'{self.x_label_view} = {x_phys:.2f}', fontsize=16)
            mv.subplots_adjust(hspace=0.3, wspace=0.3)
            plot.tick_params(labelsize=18)

        else:
            if self.d2Norm is None:
                return False
            plot = mv.add_subplot(111)
            z = np.linspace(self.z_view_range[0], self.z_view_range[1], num=self.d2Norm.shape[0])
            plot.plot(z, np.flipud(self.d2Norm[..., x_idx]), linewidth=3)
            plot.tick_params(labelsize=18)

            if self.tab2ChkBox1.isChecked() is True:
                plot.set_ylabel('Normalized Pseudo-Power', fontsize=20)
            else:
                plot.set_ylabel('Pseudo-Power', fontsize=20)

            plot.set_xlabel(self.z_label, fontsize=20)
            plot.set_title(f'{self.x_label_view} = {x_phys:.2f}', fontsize=16)
            plot.grid()

        self.tab3Plot.draw()
        self.tab3_plotted = True
        return True

    def rePlot(self):
        """Redraws the Plot tab with or without histogram equalization (F-072, E-011) (visualizer.py:2056)."""

        if self.tab2ChkBox2.isChecked() is True and self.tab2ChkBox2.isEnabled() is True:
            self.tab2Slider.setEnabled(True)
            self.bins = self.tab2Slider.value()
            if getattr(self, "d2", None) is None:
                return
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                d2toPlot = np.zeros(self.d2.shape)
                if self.nChannels > 1 and self.allChMenu.isChecked() is True:
                    for j in range(self.nChannels):
                        d2toPlot[..., j] = exposure.equalize_hist(self.d2[..., j], nbins=self.bins)
                else:
                    d2toPlot = exposure.equalize_hist(self.d2, nbins=self.bins)
            self.plotTomogram(d2toPlot)
        else:
            self.tab2Slider.setEnabled(False)
            if not hasattr(self, "d2"):
                return
            self.plotTomogram(self.d2)

    def tab2ChkBox2Changed(self):
        """Histogram equalization or Plot colormap changed: replots while equalization is enabled (F-065, F-066) (visualizer.py:2073)."""

        if self.tab2ChkBox2.isEnabled() is True:
            self.rePlot()

    def tab2ChkBox3Changed(self):
        """X [m]: shows or hides the x line and replots (F-067) (visualizer.py:2077)."""

        if self.tab2ChkBox3.isEnabled() is True:
            if self.tab2ChkBox3.isChecked() is True:
                self.tab2SpinBox.setMinimum(float(min(self.x_view_min, self.x_view_max)))
                self.tab2SpinBox.setMaximum(float(max(self.x_view_min, self.x_view_max)))
                self.tab2SpinBox.setValue((float(self.x_view_min) + float(self.x_view_max)) / 2.0)

                self.tab2SpinBox.setEnabled(True)
                self.tab2ChkBox2.setEnabled(False)
                self.tab2PlotButton.setEnabled(True)
            else:
                self.tab2SpinBox.setEnabled(False)
                self.tab2SpinBox.setValue(0.0)
                self.tab2ChkBox2.setEnabled(True)
                self.tab2PlotButton.setEnabled(False)

            self.rePlot()

    def tab2ChkBox4Changed(self):
        """Full View: switches between half and full height and replots (F-068) (visualizer.py:2095)."""

        if self.tab2ChkBox4.isEnabled() is True:
            self.subplot = 111 if self.tab2ChkBox4.isChecked() is True else 211
            self.rePlot()

    def tab2ChkBox1Changed(self):
        """Normalize: replots (F-064) (visualizer.py:2100)."""

        if self.tab2ChkBox1.isEnabled() is True:
            self.rePlot()

    def tab2SliderChanged(self):
        """Equalization bins: replots (F-065) (visualizer.py:2104)."""

        if self.tab2Slider.isEnabled() is True:
            self.rePlot()

    def tab2SpinBoxChanged(self):
        """X [m] value: replots (F-067) (visualizer.py:2108)."""

        if self.tab2SpinBox.isEnabled() is True:
            self.rePlot()

    def tab2AxesButtonClicked(self):
        """Axes: asks for the Axes Settings dialog (F-069) (visualizer.py:2112)."""

        xLabelEdit = QtLineEdit(self.boundary, "xLabelEdit", self.x_label_view)

        zLabelEdit = QtLineEdit(self.boundary, "zLabelEdit", self.z_label)

        xMinSpin = QtDoubleSpinBox(self.boundary, "xMinSpin")
        xMinSpin.setDecimals(6)
        xMinSpin.setRange(-1e9, 1e9)
        xMinSpin.setValue(float(self.x_view_min))

        xMaxSpin = QtDoubleSpinBox(self.boundary, "xMaxSpin")
        xMaxSpin.setDecimals(6)
        xMaxSpin.setRange(-1e9, 1e9)
        xMaxSpin.setValue(float(self.x_view_max))

        zMinSpin = QtDoubleSpinBox(self.boundary, "zMinSpin")
        zMinSpin.setDecimals(6)
        zMinSpin.setRange(-1e9, 1e9)
        zMinSpin.setValue(float(self.z_view_range[0]))

        zMaxSpin = QtDoubleSpinBox(self.boundary, "zMaxSpin")
        zMaxSpin.setDecimals(6)
        zMaxSpin.setRange(-1e9, 1e9)
        zMaxSpin.setValue(float(self.z_view_range[1]))

        fields = (xLabelEdit, zLabelEdit, xMinSpin, xMaxSpin, zMinSpin, zMaxSpin)
        values = {"x_label": xLabelEdit.text(), "z_label": zLabelEdit.text(), "x_min": xMinSpin.value(), "x_max": xMaxSpin.value(), "z_min": zMinSpin.value(), "z_max": zMaxSpin.value()}
        payload = {"title": "Axes Settings", "values": values, "decimals": 6, "range": [-1e9, 1e9], "step": 1.0}

        self.dialogs.request("axes", payload, lambda result: self.tab2AxesAccepted(result, *fields))

    def tab2AxesAccepted(self, result, xLabelEdit, zLabelEdit, xMinSpin, xMaxSpin, zMinSpin, zMaxSpin):
        """Applies the Axes Settings dialog's values (visualizer.py:2112)."""

        values = result.get("values") or {}
        if "x_label" in values:
            xLabelEdit.setText(str(values["x_label"]))
        if "z_label" in values:
            zLabelEdit.setText(str(values["z_label"]))
        for name, spin in (("x_min", xMinSpin), ("x_max", xMaxSpin), ("z_min", zMinSpin), ("z_max", zMaxSpin)):
            if name in values:
                spin.setValue(float(values[name]))

        x_min = xMinSpin.value()
        x_max = xMaxSpin.value()
        z_min = zMinSpin.value()
        z_max = zMaxSpin.value()

        if x_min >= x_max:
            self.dialogs.message(
                "warning",
                "Invalid axis limits",
                "X min must be smaller than X max."
            )
            return

        if z_min >= z_max:
            self.dialogs.message(
                "warning",
                "Invalid axis limits",
                "Z min must be smaller than Z max."
            )
            return

        self.x_label_view = xLabelEdit.text().strip() or "x"
        self.z_label = zLabelEdit.text().strip() or "z"
        self.x_view_min = x_min
        self.x_view_max = x_max
        self.z_view_range = [z_min, z_max]

        if self.tab2ChkBox3.isChecked():
            self.tab2SpinBox.blockSignals(True)
            self.tab2SpinBox.setMinimum(float(min(self.x_view_min, self.x_view_max)))
            self.tab2SpinBox.setMaximum(float(max(self.x_view_min, self.x_view_max)))

            x_curr = self.tab2SpinBox.value()
            x_curr = max(float(min(self.x_view_min, self.x_view_max)),
                         min(x_curr, float(max(self.x_view_min, self.x_view_max))))
            self.tab2SpinBox.setValue(x_curr)
            self.tab2SpinBox.blockSignals(False)

        if self.tab2ClearButton.isEnabled():
            self.plotTomogram(self.d2)

        if self.tab3ClearButton.isEnabled():
            self.updateProfilePlot()

    def tab2PlotButtonClicked(self):
        """Plot (profile): draws the profile (F-070) (visualizer.py:2220)."""

        if not self.plotProfile():
            return
        self.tab3ClearButton.setEnabled(True)

    def tab2ClearButtonClicked(self):
        """Plot Clear: resets the Plot tab and clears both figures (F-071) (visualizer.py:2224)."""

        self.tab2_plotted = False
        self.tab3_plotted = False

        self.tab2ClearButton.setEnabled(False)
        self.tab2AxesButton.setEnabled(False)

        self.tab2Slider.setEnabled(False)
        self.tab2Slider.setValue(2)
        self.tab2ChkBox2.setEnabled(False)
        self.tab2ChkBox2.setChecked(False)
        self.tab2ComboBox.setEnabled(False)
        self.tab2PlotButton.setEnabled(False)
        self.tab2ChkBox3.setEnabled(False)
        self.tab2ChkBox3.setChecked(False)
        self.tab2SpinBox.setEnabled(False)
        self.tab2SpinBox.setValue(0)
        self.tab2ChkBox1.setEnabled(False)
        self.tab2ChkBox1.setChecked(False)
        self.tab3ClearButtonClicked()
        self.tab2Plot.getFigure().clear()
        self.tab2Plot.draw()

    def tab3ClearButtonClicked(self):
        """Profile Clear: clears the profile figure (F-084) (visualizer.py:2247)."""

        self.tab3_plotted = False
        self.tab3Plot.getFigure().clear()
        self.tab3Plot.draw()
        self.tab3ClearButton.setEnabled(False)

    @TomoVisRc.styled
    def handle(self, event: dict) -> None:
        """Applies one browser event as the Qt widget operation it stands for.

        Args:
            event : Event dict of the API (section 3.3 of the design).

        Raises:
            TomoVisEventError : For an invalid event or a stale dialog token.
        """

        self.events.dispatch(event)

    def resendViews(self) -> None:
        """Forgets which images the browser holds, so the next drain sends every current image."""

        self.sent_serials = {}

    def figures(self) -> dict:
        """Returns the figure id to TomoVisFigure map of the window."""

        return {"plot": self.tab2Plot, "profile": self.tab3Plot}

    @TomoVisRc.styled
    def drain(self) -> WindowOutput:
        """Collects everything produced since the previous drain.

        Returns:
            Dialog requests, figure messages and frames, changed view images, printed lines and slot errors.
        """

        figures = {}
        frames  = {}
        for name, figure in self.figures().items():
            messages, pngs = figure.drain(f"figure:{name}:")
            if messages:
                figures[name] = messages
            frames.update(pngs)

        views = {}
        for view in (self.imv1_1, self.imv1_2, self.imv2_1, self.imv2_2):
            if self.sent_serials.get(view.name) != view.image_serial:
                self.sent_serials[view.name] = view.image_serial
                if view.image is not None:
                    views[view.name] = view.image

        slot_errors, self.slot_errors = self.slot_errors, []
        return WindowOutput(self.dialogs.drain(), figures, frames, views, self.console.drain(), slot_errors)

    def snapshot(self) -> dict:
        """Returns the full window state the browser renders.

        Returns:
            controls (keyed like the goldens' state.controls), views, attributes, volume, figure flags, the 3D tab index and the pending dialog token.
        """

        return {
            "controls"       : self.events.controls(),
            "views"          : {view.name: view.snapshot() for view in (self.imv1_1, self.imv1_2, self.imv2_1, self.imv2_2)},
            "attributes"     : self.attributes(),
            "volume"         : {"serial": self.volume_serial, "rendered": self.volume_rendered, "shape": list(self.volume_data.shape) if self.volume_data is not None else None},
            "figures"        : {"plot": {"plotted": self.tab2_plotted}, "profile": {"plotted": self.tab3_plotted}},
            "tab3d_index"    : self.tab3d_index,
            "pending_dialog" : self.dialogs.pendingToken(),
        }

    def attributes(self) -> dict:
        """Returns the window attributes under the goldens' state.attributes names.

        Returns:
            Scalars and labels, plus the shape and dtype of every array attribute that exists.
        """

        record = {
            "nChannels"       : int(self.nChannels),
            "x_label"         : self.x_label,
            "z_label"         : self.z_label,
            "x_min"           : float(self.x_min),
            "x_max"           : float(self.x_max),
            "x_label_view"    : self.x_label_view,
            "x_view_min"      : float(self.x_view_min),
            "x_view_max"      : float(self.x_view_max),
            "z_range"         : [float(value) for value in self.z_range],
            "z_view_range"    : [float(value) for value in self.z_view_range],
            "x_res"           : float(self.x_res),
            "y_res"           : float(self.y_res),
            "cmap"            : int(self.cmap),
            "subplot"         : int(self.subplot),
            "roiFlag"         : bool(self.roiFlag),
            "tab2_plotted"    : bool(self.tab2_plotted),
            "tab3_plotted"    : bool(self.tab3_plotted),
            "volume_rendered" : bool(self.volume_rendered),
        }
        for name in ("img", "d2", "aux", "d2Norm", "rgbArray", "z_axis", "data"):
            value = getattr(self, name, None)
            record[f"{name}_present"] = value is not None
            if value is not None:
                record[f"{name}_shape"] = list(np.shape(value))
                record[f"{name}_dtype"] = str(np.asarray(value).dtype)
        return record

    def metadata(self) -> dict:
        """Returns getCurrentMetadata() for the metadata route."""

        return self.getCurrentMetadata()

    def volumePayload(self, serial: int) -> tuple[dict, np.ndarray] | None:
        """Returns the prepared 3D volume when ``serial`` is the current one.

        Args:
            serial : Volume serial the browser saw in a snapshot.

        Returns:
            ({"serial", "shape", "dtype"}, float32 array), or None for a stale serial or no volume.
        """

        if self.volume_data is None or serial != self.volume_serial:
            return None
        return {"serial": self.volume_serial, "shape": list(self.volume_data.shape), "dtype": "float32"}, self.volume_data
