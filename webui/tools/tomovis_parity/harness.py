"""Headless driver and state probes for the original PyQt5 TomoVis window.

TomoVisSession builds the real ``TomoVis`` main window under the offscreen Qt
platform and performs user actions through the same widgets and menu actions a
user would touch, so every callback runs exactly as in the desktop app. File,
message and Axes dialogs are replaced by DialogStubs, which answer them and
log what they were asked. Exceptions raised inside Qt slots are recorded by
SlotErrors instead of aborting the process (PyQt5 calls qFatal on an
unhandled slot exception while the default excepthook is installed). The probe
classes read back everything a port must reproduce: the arrays the window
computed, the levels and look-up tables pyqtgraph applied, the pixels it
rendered, the matplotlib figure layout and the state of every control.
"""

from __future__ import annotations

import contextlib
import importlib
import io
import sys
import traceback

import h5py
import numpy as np
from matplotlib.colors import to_rgba
from PyQt5 import QtCore, QtGui, QtWidgets

from fixtures import NumpyLegacyNames


class SlotErrors:
    """Collects exceptions raised inside Qt slots through ``sys.excepthook``.

    Only exceptions raised while ``armed`` is set (during a scripted action)
    are recorded; any other exception is printed by the interpreter's default
    hook, so failures of the generator itself stay visible.

    Attributes:
        records : Exceptions seen since the last drain, each with type, message and the innermost frames.
        armed   : Whether exceptions are currently recorded instead of printed.
    """

    def __init__(self) -> None:
        """Starts disarmed with no records."""

        self.records = []
        self.armed   = False

    def hook(self, exc_type, exc, tb) -> None:
        """Records one exception with its last three frames, or prints it when disarmed.

        Args:
            exc_type : Exception class.
            exc      : Exception instance.
            tb       : Traceback object.
        """

        if not self.armed:
            sys.__excepthook__(exc_type, exc, tb)
            return

        frames = traceback.extract_tb(tb)[-3:]
        self.records.append({
            "type"    : exc_type.__name__,
            "message" : str(exc),
            "frames"  : [f"{frame.name} ({frame.filename.rsplit('/', 1)[-1]}:{frame.lineno})" for frame in frames],
        })

    def install(self) -> None:
        """Makes this recorder the process excepthook."""

        sys.excepthook = self.hook

    def drain(self) -> list[dict]:
        """Returns and clears the records.

        Returns:
            Records collected since the previous drain.
        """

        records, self.records = self.records, []
        return records


class DialogStubs:
    """Replaces the modal dialogs TomoVis opens with scripted answers.

    The import callbacks build a ``QFileDialog`` and call ``exec_`` and
    ``selectedFiles``; Save and Open call the static ``getSaveFileName`` and
    ``getOpenFileName``; the Axes button builds a ``QDialog`` with two line
    edits and four double spin boxes; errors and confirmations go through the
    static ``QMessageBox`` helpers. Each stub logs the request in ``events``.

    Attributes:
        open_path   : Path the next file dialog returns, None to cancel it.
        save_path   : Path the next save dialog returns, None to cancel it.
        axes_values : Values the next Axes dialog receives (x_label, z_label, x_min, x_max, z_min, z_max), each optional.
        axes_accept : Whether the next Axes dialog is accepted.
        axes_grab   : Path where the next Axes dialog is grabbed as an image, None for no grab.
        events      : Dialog requests since the last drain.
    """

    def __init__(self) -> None:
        """Starts with every dialog cancelled and no events."""

        self.open_path   = None
        self.save_path   = None
        self.axes_values = {}
        self.axes_accept = True
        self.axes_grab   = None
        self.events      = []

    def file_dialog_exec(self, dialog) -> int:
        """Answers ``QFileDialog.exec_`` for the import callbacks.

        Args:
            dialog : The QFileDialog the callback built.

        Returns:
            1 when ``open_path`` is set, 0 to mimic Cancel.
        """

        self.events.append({
            "kind"        : "file_dialog",
            "title"       : dialog.windowTitle(),
            "name_filter" : dialog.nameFilters(),
            "native"      : not dialog.testOption(QtWidgets.QFileDialog.DontUseNativeDialog),
            "file_mode"   : int(dialog.fileMode()),
            "returned"    : self.open_path,
        })
        dialog.stub_selection = [] if self.open_path is None else [self.open_path]
        return 0 if self.open_path is None else 1

    def file_dialog_selection(self, dialog) -> list[str]:
        """Answers ``QFileDialog.selectedFiles`` with the scripted path.

        Args:
            dialog : The QFileDialog the callback built.

        Returns:
            One-element list with ``open_path``, or an empty list.
        """

        return list(getattr(dialog, "stub_selection", []))

    def save_name(self, parent, caption, directory, name_filter) -> tuple[str, str]:
        """Answers ``QFileDialog.getSaveFileName``.

        Args:
            parent      : Parent widget passed by the caller.
            caption     : Dialog caption.
            directory   : Start directory.
            name_filter : Filter string.

        Returns:
            (path, filter), with an empty path to mimic Cancel.
        """

        self.events.append({"kind": "save_dialog", "title": caption, "directory": directory, "name_filter": name_filter, "returned": self.save_path})
        return (self.save_path or "", name_filter if self.save_path else "")

    def open_name(self, parent, caption, directory, name_filter) -> tuple[str, str]:
        """Answers ``QFileDialog.getOpenFileName``.

        Args:
            parent      : Parent widget passed by the caller.
            caption     : Dialog caption.
            directory   : Start directory.
            name_filter : Filter string.

        Returns:
            (path, filter), with an empty path to mimic Cancel.
        """

        self.events.append({"kind": "open_dialog", "title": caption, "directory": directory, "name_filter": name_filter, "returned": self.open_path})
        return (self.open_path or "", name_filter if self.open_path else "")

    def message(self, level: str):
        """Builds the stub for one static ``QMessageBox`` helper.

        Args:
            level : "warning", "information" or "critical".

        Returns:
            Function with the helper's signature that logs the call and answers Ok.
        """

        def answer(parent, title, text, *rest):
            self.events.append({"kind": "message_box", "level": level, "title": title, "text": text})
            return QtWidgets.QMessageBox.Ok

        return answer

    def axes_exec(self, dialog) -> int:
        """Answers ``QDialog.exec_`` for the Axes dialog after logging its initial fields.

        Args:
            dialog : The Axes QDialog the callback built.

        Returns:
            ``QDialog.Accepted`` or ``QDialog.Rejected`` per ``axes_accept``.
        """

        edits = [child for child in dialog.children() if isinstance(child, QtWidgets.QLineEdit)]
        spins = [child for child in dialog.children() if isinstance(child, QtWidgets.QDoubleSpinBox)]
        names = ["x_min", "x_max", "z_min", "z_max"]

        initial = {"title": dialog.windowTitle(), "modal": dialog.isModal(), "x_label": edits[0].text(), "z_label": edits[1].text()}
        for name, spin in zip(names, spins):
            initial[name] = {"value": spin.value(), "decimals": spin.decimals(), "minimum": spin.minimum(), "maximum": spin.maximum()}
        initial["labels"] = [child.text() for child in dialog.children() if isinstance(child, QtWidgets.QLabel)]

        if self.axes_grab is not None:
            dialog.show()
            for _ in range(4):
                QtWidgets.QApplication.processEvents()
            dialog.grab().save(self.axes_grab)
            dialog.hide()
            self.axes_grab = None

        if "x_label" in self.axes_values:
            edits[0].setText(self.axes_values["x_label"])
        if "z_label" in self.axes_values:
            edits[1].setText(self.axes_values["z_label"])
        for name, spin in zip(names, spins):
            if name in self.axes_values:
                spin.setValue(float(self.axes_values[name]))

        applied = {"x_label": edits[0].text(), "z_label": edits[1].text()}
        for name, spin in zip(names, spins):
            applied[name] = spin.value()

        self.events.append({"kind": "axes_dialog", "initial": initial, "applied": applied, "accepted": self.axes_accept})
        return QtWidgets.QDialog.Accepted if self.axes_accept else QtWidgets.QDialog.Rejected

    def install(self) -> None:
        """Patches the Qt dialog classes with the stubs."""

        stubs = self
        QtWidgets.QFileDialog.exec_            = lambda dialog: stubs.file_dialog_exec(dialog)
        QtWidgets.QFileDialog.selectedFiles    = lambda dialog: stubs.file_dialog_selection(dialog)
        QtWidgets.QFileDialog.getSaveFileName  = staticmethod(self.save_name)
        QtWidgets.QFileDialog.getOpenFileName  = staticmethod(self.open_name)
        QtWidgets.QMessageBox.warning          = staticmethod(self.message("warning"))
        QtWidgets.QMessageBox.information      = staticmethod(self.message("information"))
        QtWidgets.QMessageBox.critical         = staticmethod(self.message("critical"))
        QtWidgets.QDialog.exec_                = lambda dialog: stubs.axes_exec(dialog)

    def drain(self) -> list[dict]:
        """Returns and clears the logged dialog requests.

        Returns:
            Requests logged since the previous drain.
        """

        events, self.events = self.events, []
        return events


class ImageViewProbe:
    """Reads what a pyqtgraph ImageView shows: levels, histogram range, LUT and rendered pixels."""

    def qimage_to_rgba(self, qimage) -> np.ndarray:
        """Converts a QImage to an RGBA array in display order.

        Args:
            qimage : Image produced by ImageItem.render().

        Returns:
            Uint8 array (rows, cols, 4), row 0 at the top of the view.
        """

        converted = qimage.convertToFormat(QtGui.QImage.Format_RGBA8888)
        width     = converted.width()
        height    = converted.height()
        buffer    = converted.constBits()
        buffer.setsize(converted.byteCount())
        rows      = np.frombuffer(buffer, dtype=np.uint8).reshape(height, converted.bytesPerLine())
        return rows[:, :width * 4].reshape(height, width, 4).copy()

    def capture(self, view) -> tuple[dict, dict]:
        """Captures one ImageView.

        Args:
            view : pyqtgraph ImageView.

        Returns:
            (scalars, arrays): levels, histogram state and view geometry as JSON-ready values; the rendered RGBA image and the applied LUT as arrays.
        """

        item      = view.imageItem
        histogram = view.ui.histogram
        scalars   = {"has_image": view.image is not None}
        arrays    = {}

        if view.image is None:
            return scalars, arrays

        scalars["image_shape"]      = list(view.image.shape)
        scalars["image_dtype"]      = str(view.image.dtype)
        scalars["item_levels"]      = np.asarray(item.levels, dtype=np.float64).tolist() if item.levels is not None else None
        scalars["histogram_levels"] = np.asarray(histogram.getLevels(), dtype=np.float64).tolist()
        scalars["histogram_range"]  = [float(value) for value in histogram.getHistogramRange()]
        scalars["level_mode"]       = histogram.levelMode
        scalars["view_range"]       = [[float(value) for value in pair] for pair in view.view.viewRange()]
        scalars["y_inverted"]       = bool(view.view.yInverted())
        scalars["aspect_locked"]    = bool(view.view.state["aspectLocked"])

        lut = item.lut(item.image, 256) if callable(item.lut) else item.lut
        if lut is not None and (item.image.ndim == 2 or item.image.shape[2] == 1):
            arrays["lut"] = np.asarray(lut)
        scalars["lut_applied"] = "lut" in arrays

        item.render()
        if item.qimage is not None:
            arrays["render"] = self.qimage_to_rgba(item.qimage)
        return scalars, arrays


class FigureProbe:
    """Reads the layout, artists and pixels of a matplotlib figure."""

    def ticks(self, axis) -> dict:
        """Lists the visible major ticks of one axis.

        Args:
            axis : matplotlib XAxis or YAxis.

        Returns:
            Tick locations and their label texts.
        """

        return {"locations": [float(value) for value in axis.get_ticklocs()], "labels": [label.get_text() for label in axis.get_ticklabels()]}

    def axes(self, ax, arrays: dict, prefix: str) -> dict:
        """Describes one Axes and moves its line data into ``arrays``.

        Args:
            ax     : matplotlib Axes.
            arrays : Receives "<prefix>line<k>_x" and "<prefix>line<k>_y" arrays.
            prefix : Key prefix for this Axes' arrays.

        Returns:
            Position, limits, labels, fonts, ticks, images, lines, legend and grid state.
        """

        position = ax.get_position()
        record   = {
            "position"        : [float(position.x0), float(position.y0), float(position.width), float(position.height)],
            "is_colorbar"     : hasattr(ax, "_colorbar"),
            "xlim"            : [float(value) for value in ax.get_xlim()],
            "ylim"            : [float(value) for value in ax.get_ylim()],
            "xlabel"          : ax.get_xlabel(),
            "ylabel"          : ax.get_ylabel(),
            "xlabel_size"     : float(ax.xaxis.label.get_fontsize()),
            "ylabel_size"     : float(ax.yaxis.label.get_fontsize()),
            "title"           : ax.get_title(),
            "title_size"      : float(ax.title.get_fontsize()),
            "xticks"          : self.ticks(ax.xaxis),
            "yticks"          : self.ticks(ax.yaxis),
            "tick_label_size" : float(ax.yaxis.get_ticklabels()[0].get_fontsize()) if ax.yaxis.get_ticklabels() else None,
            "grid"            : bool(any(line.get_visible() for line in ax.xaxis.get_gridlines())),
            "facecolor"       : list(ax.get_facecolor()),
            "images"          : [],
            "lines"           : [],
            "legend"          : None,
        }

        for image in ax.get_images():
            record["images"].append({
                "extent"        : [float(value) for value in image.get_extent()],
                "shape"         : list(np.asarray(image.get_array()).shape),
                "dtype"         : str(np.asarray(image.get_array()).dtype),
                "cmap"          : image.get_cmap().name,
                "clim"          : [float(value) for value in image.get_clim()],
                "origin"        : image.origin,
                "interpolation" : image.get_interpolation(),
                "aspect"        : ax.get_aspect(),
            })

        for index, line in enumerate(ax.get_lines()):
            x_key = f"{prefix}line{index}_x"
            y_key = f"{prefix}line{index}_y"
            arrays[x_key] = np.asarray(line.get_xdata(), dtype=np.float64)
            arrays[y_key] = np.asarray(line.get_ydata(), dtype=np.float64)
            record["lines"].append({
                "x_key"     : x_key,
                "y_key"     : y_key,
                "color"     : [float(value) for value in to_rgba(line.get_color())],
                "linewidth" : float(line.get_linewidth()),
                "label"     : line.get_label(),
                "transform" : "axvline" if line.get_transform() is not ax.transData else "data",
            })

        legend = ax.get_legend()
        if legend is not None:
            record["legend"] = {"texts": [text.get_text() for text in legend.get_texts()], "fontsize": float(legend.get_texts()[0].get_fontsize()) if legend.get_texts() else None}
        return record

    def capture(self, widget, tag: str) -> tuple[dict, dict, np.ndarray | None]:
        """Captures the figure held by a TomoVis MatplotlibWidget.

        Args:
            widget : MatplotlibWidget of the Plot or Profile tab.
            tag    : Key prefix for line arrays ("plot" or "profile").

        Returns:
            (scalars, arrays, render): figure size, canvas visibility, subplot parameters and per-Axes records; line data; the RGBA canvas pixels, None when the figure is empty or its tab is hidden (a hidden canvas keeps matplotlib's default 640x480 until shown).
        """

        figure  = widget.getFigure()
        arrays  = {}
        params  = figure.subplotpars
        scalars = {
            "canvas_visible" : widget.canvas.isVisible(),
            "size_px"        : [int(round(value)) for value in figure.get_size_inches() * figure.dpi],
            "dpi"            : float(figure.dpi),
            "subplotpars"    : {"left": params.left, "right": params.right, "top": params.top, "bottom": params.bottom, "wspace": params.wspace, "hspace": params.hspace},
            "axes"           : [self.axes(ax, arrays, f"{tag}_ax{index}_") for index, ax in enumerate(figure.axes)],
        }

        if not figure.axes or not widget.canvas.isVisible():
            return scalars, arrays, None

        widget.canvas.draw()
        render = np.asarray(widget.canvas.buffer_rgba()).copy()
        scalars["render_shape"] = list(render.shape)
        return scalars, arrays, render


class StateProbe:
    """Reads the TomoVis window's attributes, controls and views after an action.

    Attributes:
        views     : ImageViewProbe used for the four image views.
        figures   : FigureProbe used for the Plot and Profile figures.
        colormaps : vispy colormap name to object, used to name the 3D colormaps.
    """

    ARRAY_ATTRIBUTES = ("img", "d2", "aux", "d2Norm", "rgbArray", "z_axis", "data")
    SCALAR_ATTRIBUTES = ("nChannels", "x_label", "z_label", "x_min", "x_max", "x_label_view", "x_view_min", "x_view_max", "z_range", "z_view_range", "x_res", "y_res", "cmap", "subplot", "roiFlag", "tab2_plotted", "tab3_plotted", "volume_rendered")

    def __init__(self, colormaps: dict) -> None:
        """Creates the view and figure probes.

        Args:
            colormaps : vispy colormap name to object, in get_colormaps() order.
        """

        self.views     = ImageViewProbe()
        self.figures   = FigureProbe()
        self.colormaps = colormaps

    def plain(self, value):
        """Converts numpy, Qt and pyqtgraph values to JSON-ready Python values.

        Args:
            value : Any attribute value.

        Returns:
            The value as bool, int, float, str, None, list or dict.
        """

        if isinstance(value, (bool, np.bool_)):
            return bool(value)
        if isinstance(value, (int, np.integer)):
            return int(value)
        if isinstance(value, (float, np.floating)):
            return float(value)
        if isinstance(value, (str, type(None))):
            return value
        if isinstance(value, bytes):
            return value.decode("utf-8", "replace")
        if isinstance(value, dict):
            return {str(key): self.plain(item) for key, item in value.items()}
        if isinstance(value, (list, tuple, np.ndarray)):
            return [self.plain(item) for item in value]
        if hasattr(value, "x") and hasattr(value, "y") and callable(value.x):
            return [float(value.x()), float(value.y())]
        return repr(value)

    def holder(self, window, item) -> str | None:
        """Names the image view whose ViewBox holds a graphics item.

        Args:
            window : TomoVis window.
            item   : ROI or InfiniteLine.

        Returns:
            "imv1_1", "imv1_2", or None when the item is in no view.
        """

        box = item.getViewBox()
        for name in ("imv1_1", "imv1_2"):
            if box is getattr(window, name).view:
                return name
        return None

    def controls(self, window) -> dict:
        """Reads the state of every menu action and widget a user can touch.

        Args:
            window : TomoVis window.

        Returns:
            Control name to its enabled, checked, value, range or text fields.
        """

        state = {}

        for name in ("openFile", "saveFile", "openFUSAR", "openRAT", "openUAVSAR", "openNpy", "allChMenu", "ch1Menu", "ch2Menu", "ch3Menu"):
            action = getattr(window, name)
            state[name] = {"enabled": action.isEnabled(), "checked": action.isChecked(), "text": action.text(), "shortcut": action.shortcut().toString()}
        state["ChMenu"] = {"enabled": window.ChMenu.isEnabled(), "title": window.ChMenu.title()}

        for name in ("tab1Slider", "tab2Slider", "isoThresholdTab4Slider"):
            slider = getattr(window, name)
            state[name] = {"enabled": slider.isEnabled(), "minimum": slider.minimum(), "maximum": slider.maximum(), "value": slider.value()}

        state["tab1SpinBox"] = {"enabled": window.tab1SpinBox.isEnabled(), "minimum": window.tab1SpinBox.minimum(), "maximum": window.tab1SpinBox.maximum(), "value": window.tab1SpinBox.value()}
        state["tab2SpinBox"] = {"enabled": window.tab2SpinBox.isEnabled(), "minimum": window.tab2SpinBox.minimum(), "maximum": window.tab2SpinBox.maximum(), "value": window.tab2SpinBox.value(), "decimals": window.tab2SpinBox.decimals(), "text": window.tab2SpinBox.text()}

        for name in ("tab1ChkBox", "tab2ChkBox1", "tab2ChkBox2", "tab2ChkBox3", "tab2ChkBox4", "turntableCameraTab4Button", "flyCameraTab4Button", "arcballCameraTab4Button", "mipProjectionTab4Button", "isoProjectionTab4Button", "translucentProjectionTab4Button", "additiveProjectionTab4Button"):
            box = getattr(window, name)
            state[name] = {"enabled": box.isEnabled(), "checked": box.isChecked()}

        for name in ("tab1PlayButton", "tab1SetButton", "tab1PlotButton", "tab2AxesButton", "tab2PlotButton", "tab2ClearButton", "tab3ClearButton", "colormapTab4Button", "resetCamerasTab4Button", "channelTab4Button"):
            button = getattr(window, name)
            state[name] = {"enabled": button.isEnabled(), "text": button.text()}

        for name in ("tab1ComboBox", "tab2ComboBox"):
            combo = getattr(window, name)
            state[name] = {"enabled": combo.isEnabled(), "index": combo.currentIndex(), "text": combo.currentText(), "count": combo.count()}

        for index in range(1, 7):
            edit = getattr(window, f"tab1QLineEdit{index}")
            state[f"tab1QLineEdit{index}"] = {"enabled": edit.isEnabled(), "text": edit.text(), "placeholder": edit.placeholderText()}

        state["tabWidget"] = {"index": window.tabWidget.currentIndex(), "count": window.tabWidget.count(), "titles": [window.tabWidget.tabText(i) for i in range(window.tabWidget.count())]}
        state["imv1"]      = {"current": "imv1_1" if window.imv1.currentWidget() is window.imv1_1 else "imv1_2"}
        state["imv2"]      = {"current": "imv2_1" if window.imv2.currentWidget() is window.imv2_1 else "imv2_2"}
        state["tab1Timer"] = {"active": window.tab1Timer.isActive(), "interval": window.tab1Timer.interval()}
        state["slice_line"] = {"visible": window.slice_line.isVisible(), "value": float(window.slice_line.value()), "view": self.holder(window, window.slice_line)}
        state["roi_1"]      = {"view": self.holder(window, window.roi_1)}
        return state

    def roi(self, window) -> dict:
        """Reads the ROI geometry the way TomoVis derives it.

        Args:
            window : TomoVis window.

        Returns:
            computeLinePar output, ROI state, clipped line, axis mode, effective resolution and the x index of the Plot spin box value.
        """

        ax, ay, bx, by, theta, length = window.computeLinePar()
        roi_state = window.roi_1.getState()
        record    = {
            "Ax"          : ax,
            "Ay"          : ay,
            "Bx"          : bx,
            "By"          : by,
            "theta"       : theta,
            "length"      : length,
            "pos"         : self.plain(roi_state["pos"]),
            "handles"     : [self.plain(handle["item"].pos()) for handle in window.roi_1.handles],
            "image_shape" : self.plain(window.getCurrentImageShape()),
        }

        if getattr(window, "img", None) is not None:
            record["effective_line"]       = self.plain(window.getEffectiveROILine())
            record["axis_mode"]            = window.getROIAxisMode()
            record["effective_resolution"] = window.getEffectiveROIResolution()
            record["x_index_of_spinbox"]   = window.xPhysicalToIndex(float(window.tab2SpinBox.value()))
        return record

    def volume(self, window) -> dict | None:
        """Reads the vispy 3D state once the 3D tab has built its Volume.

        Args:
            window : TomoVis window.

        Returns:
            Camera states, visual settings and colormap selections, or None before the 3D tab was opened.
        """

        volume = window.volume
        if volume is None:
            return None

        names  = {id(cmap): name for name, cmap in self.colormaps.items()}
        record = {
            "camera"              : volume.view.camera.name,
            "volume_center"       : self.plain(volume.volume_center),
            "data_min"            : self.plain(getattr(volume, "dataVolumeMin", None)),
            "data_max"            : self.plain(getattr(volume, "dataVolumeMax", None)),
            "n_channels"          : self.plain(getattr(volume, "nChannels", None)),
            "iso_threshold_init"  : self.plain(getattr(volume, "iso_threshold_init", None)),
            "visible_iterator"    : self.plain(getattr(volume, "volumeVisualVisibleIterator", None)),
            "opaque_cmap"         : volume.opaqueCmap if isinstance(volume.opaqueCmap, str) else names.get(id(volume.opaqueCmap), type(volume.opaqueCmap).__name__),
            "translucent_cmap"    : type(volume.translucentCmap).__name__,
            "axis_view"           : {"visible": bool(volume.axis_view.visible), "pos": self.plain(volume.axis_view.pos), "size": self.plain(volume.axis_view.size)},
            "canvas_size"         : self.plain(volume.canvas.size),
            "cameras"             : {},
            "visuals"             : [],
        }

        for camera in (volume.turntableCamera, volume.arcballCamera, volume.flyCamera, volume.axis_camera):
            record["cameras"][camera.name] = self.plain(camera.get_state())

        for visual in volume.volumeVisual:
            record["visuals"].append({
                "method"             : visual.method,
                "cmap"               : names.get(id(visual.cmap), type(visual.cmap).__name__),
                "clim"               : self.plain(visual.clim),
                "threshold"          : self.plain(visual.threshold),
                "relative_step_size" : self.plain(visual.relative_step_size),
                "interpolation"      : visual.interpolation,
                "visible"            : bool(visual.visible),
                "shape"              : self.plain(visual._vol_shape),
            })
        return record

    def capture(self, window) -> tuple[dict, dict, dict]:
        """Captures the full window state.

        Args:
            window : TomoVis window.

        Returns:
            (state, arrays, figures): JSON-ready state; named arrays; figure records each with an optional "render" array.
        """

        state  = {"attributes": {}, "data": None}
        arrays = {}

        for name in self.SCALAR_ATTRIBUTES:
            state["attributes"][name] = self.plain(getattr(window, name, None))
        state["attributes"]["bins"] = self.plain(getattr(window, "bins", None))

        for name in self.ARRAY_ATTRIBUTES:
            value = getattr(window, name, None)
            if value is None:
                state["attributes"][f"{name}_present"] = False
                continue
            value = np.asarray(value)
            state["attributes"][f"{name}_present"] = True
            state["attributes"][f"{name}_shape"]   = list(value.shape)
            state["attributes"][f"{name}_dtype"]   = str(value.dtype)
            if name != "data" or value.size <= 200000:
                arrays[name] = value

        state["controls"] = self.controls(window)
        state["roi"]      = self.roi(window)
        state["views"]    = {}

        for name in ("imv1_1", "imv1_2", "imv2_1", "imv2_2"):
            scalars, view_arrays = self.views.capture(getattr(window, name))
            state["views"][name] = scalars
            for key, value in view_arrays.items():
                arrays[f"{name}_{key}"] = value

        figures = {}
        for tag, widget in (("plot", window.tab2Plot), ("profile", window.tab3Plot)):
            scalars, figure_arrays, render = self.figures.capture(widget, tag)
            arrays.update(figure_arrays)
            figures[tag] = {"record": scalars, "render": render}

        state["volume"] = self.volume(window)
        return state, arrays, figures


class RgbLevelsShim:
    """Optional toolkit shim for the RGB ``ImageView.setLevels(mins, maxs)`` calls.

    TomoVis passes per-channel level lists to ``ImageView.setLevels`` for its
    RGB views. pyqtgraph 0.14 raises ``TypeError: unhashable type: 'list'``
    there (HistogramLUTItem.setLevels builds ``{min, max}``), so the slot stops
    before the RGB view is made current and before the RGB tomogram is
    computed. When enabled, the shim routes such calls to pyqtgraph's own
    per-channel mechanism, level mode "rgba" with one (min, max) pair per
    channel, and leaves every other call untouched. TomoVis code runs
    unmodified either way.

    Attributes:
        view_class : pyqtgraph ImageView class whose setLevels is wrapped.
        original   : The unwrapped ImageView.setLevels.
        enabled    : Whether list levels are routed to the rgba level mode.
    """

    def __init__(self, view_class) -> None:
        """Stores the class and its original method, disabled.

        Args:
            view_class : pyqtgraph ImageView class.
        """

        self.view_class = view_class
        self.original   = view_class.setLevels
        self.enabled    = False

    def install(self) -> None:
        """Wraps ImageView.setLevels."""

        shim = self

        def set_levels(view, *args, **kwds):
            if shim.enabled and len(args) == 2 and isinstance(args[0], list):
                pairs = [(float(low), float(high)) for low, high in zip(args[0], args[1])]
                view.ui.histogram.setLevelMode("rgba")
                view.ui.histogram.setLevels(rgba=pairs)
                return None
            return shim.original(view, *args, **kwds)

        self.view_class.setLevels = set_levels


class TomoVisSession:
    """Runs the original TomoVis window headless and performs scripted user actions.

    Attributes:
        app            : The QApplication.
        module         : The imported ``Visualizer.visualizer`` module.
        ste_io         : The imported ``Visualizer.ste_io`` module.
        errors         : Slot exception recorder.
        stubs          : Dialog stubs.
        probe          : State probe.
        window         : Current TomoVis window, None between scenarios.
        size           : Window size in pixels (width, height).
        volume_inputs  : Arrays passed to Volume.renderVolume, in call order.
        vispy_maps     : vispy colormap name to object, in get_colormaps() order.
        levels_shim    : Optional RGB levels shim, disabled unless a scenario enables it.
    """

    CHANNEL_ACTIONS = {"RGB": "allChMenu", "Red": "ch1Menu", "Green": "ch2Menu", "Blue": "ch3Menu"}
    IMPORT_ACTIONS  = {"hd5": "openFUSAR", "rat": "openRAT", "h5": "openUAVSAR", "npy": "openNpy"}
    PROJECTIONS     = {"mip": "mipProjectionTab4Button", "iso": "isoProjectionTab4Button", "translucent": "translucentProjectionTab4Button", "additive": "additiveProjectionTab4Button"}
    CAMERAS         = {"Turntable": "turntableCameraTab4Button", "Fly": "flyCameraTab4Button", "Arcball": "arcballCameraTab4Button"}

    def __init__(self, size: tuple[int, int] = (1100, 880)) -> None:
        """Creates the QApplication the way ``tomoVis()`` does, then imports the original app.

        Args:
            size : Window size in pixels (width, height).
        """

        QtCore.QCoreApplication.setAttribute(QtCore.Qt.AA_UseSoftwareOpenGL)
        self.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv[:1])

        self.module = importlib.import_module("Visualizer.visualizer")
        self.ste_io = importlib.import_module("Visualizer.ste_io")
        self.errors = SlotErrors()
        self.stubs  = DialogStubs()
        self.window = None
        self.size   = size

        self.volume_inputs = []
        self.vispy_maps    = dict(self.module.get_colormaps()) if self.module.vispy_installed else {}
        self.probe         = StateProbe(self.vispy_maps)
        self.levels_shim   = RgbLevelsShim(self.module.pg.ImageView)

        self.errors.install()
        self.stubs.install()
        self.levels_shim.install()
        self.record_volume_inputs()

    def record_volume_inputs(self) -> None:
        """Wraps Volume.renderVolume so the array the 3D tab renders is kept."""

        original = self.module.Volume.renderVolume
        session  = self

        def recording(volume, dataVolume):
            session.volume_inputs.append(np.array(dataVolume, copy=True))
            return original(volume, dataVolume)

        self.module.Volume.renderVolume = recording

    def settle(self, rounds: int = 6) -> None:
        """Processes pending Qt events so layouts, resizes and redraws complete.

        Args:
            rounds : Number of processEvents passes.
        """

        for _ in range(rounds):
            self.app.processEvents()

    def open_window(self) -> None:
        """Builds a fresh TomoVis window at ``size`` and shows it offscreen.

        The play timer keeps its start, stop and interval, but its timeout
        signal is blocked so wall-clock time cannot advance the slider between
        steps; the ``tick`` action runs the timeout slot instead.
        """

        self.close_window()
        self.window = self.module.TomoVis()
        self.window.tab1Timer.blockSignals(True)
        self.window.resize(*self.size)
        self.window.show()
        self.settle()
        self.errors.drain()
        self.stubs.drain()

    def close_window(self) -> None:
        """Stops the play timer, closes and deletes the current window."""

        if self.window is None:
            return
        self.window.tab1Timer.stop()
        self.window.close()
        self.window.deleteLater()
        self.window = None
        self.settle()

    def usable(self, widget) -> bool:
        """Tells whether a user could operate a widget right now.

        Args:
            widget : Qt widget or action.

        Returns:
            True when the widget is enabled.
        """

        return widget.isEnabled()

    def act_fresh_window(self) -> dict:
        """Replaces the window by a new TomoVis instance, as when the app is restarted.

        Returns:
            Empty result.
        """

        self.open_window()
        return {}

    def act_import(self, kind: str, path: str | None, legacy_numpy: bool = False) -> dict:
        """Triggers File > Import > <kind> with the dialog answering ``path``.

        Args:
            kind         : "hd5", "rat", "h5" or "npy".
            path         : File the dialog returns, None to cancel.
            legacy_numpy : Restore the numpy 1.x names STEtools needs while the import runs.

        Returns:
            Whether the menu action was enabled.
        """

        self.stubs.open_path = path
        action               = getattr(self.window, self.IMPORT_ACTIONS[kind])
        if legacy_numpy:
            with NumpyLegacyNames():
                action.trigger()
        else:
            action.trigger()
        self.stubs.open_path = None
        return {"triggered": action.isEnabled()}

    def act_inject(self, path: str, select: list[int] | None = None) -> dict:
        """Sets ``window.data`` from a .npy file and calls initializeVisualizerWithData.

        Args:
            path   : .npy file to load.
            select : Channel indices kept from axis 0, None to keep the whole array.

        Returns:
            Shape of the injected array.
        """

        array = np.load(path)
        if select is not None:
            array = array[select]
        self.window.data = array
        self.window.setDefaultElevRangeIfMissing()
        self.window.initializeVisualizerWithData()
        return {"shape": list(array.shape)}

    def act_set_roi(self, ax: str, ay: str, angle: str, length: str, pos_x: str, pos_y: str) -> dict:
        """Types the six ROI fields and clicks Set.

        Args:
            ax     : Text for the Ax field.
            ay     : Text for the Ay field.
            angle  : Text for the Angle [deg] field.
            length : Text for the Length field.
            pos_x  : Text for the Pos x field.
            pos_y  : Text for the Pos y field.

        Returns:
            Whether the Set button was enabled.
        """

        for index, text in enumerate((ax, ay, angle, length, pos_x, pos_y), start=1):
            getattr(self.window, f"tab1QLineEdit{index}").setText(text)
        enabled = self.usable(self.window.tab1SetButton)
        self.window.tab1SetButton.click()
        return {"clicked": enabled}

    def act_channel(self, mode: str) -> dict:
        """Triggers Data > Channel > <mode>.

        Args:
            mode : "RGB", "Red", "Green" or "Blue".

        Returns:
            Whether the action and its menu were enabled.
        """

        action  = getattr(self.window, self.CHANNEL_ACTIONS[mode])
        enabled = action.isEnabled() and self.window.ChMenu.isEnabled()
        if enabled:
            action.trigger()
        return {"triggered": enabled}

    def act_check(self, widget: str, checked: bool) -> dict:
        """Clicks a checkbox when its state differs from ``checked``.

        Args:
            widget  : Attribute name of the QCheckBox.
            checked : Wanted state.

        Returns:
            Whether a click happened.
        """

        box     = getattr(self.window, widget)
        clicked = self.usable(box) and box.isChecked() != checked
        if clicked:
            box.click()
        return {"clicked": clicked}

    def act_value(self, widget: str, value) -> dict:
        """Sets the value of a slider or spin box the user can reach.

        Args:
            widget : Attribute name of the QSlider, QSpinBox or QDoubleSpinBox.
            value  : New value.

        Returns:
            Whether the widget was enabled and the value it holds afterwards.
        """

        control = getattr(self.window, widget)
        enabled = self.usable(control)
        if enabled:
            control.setValue(value)
        return {"applied": enabled, "value": control.value()}

    def act_combo(self, widget: str, index: int | None = None, text: str | None = None) -> dict:
        """Selects an entry of a combo box the user can reach.

        Args:
            widget : Attribute name of the QComboBox.
            index  : Entry index to select.
            text   : Entry text to select, used when ``index`` is None.

        Returns:
            Whether the combo box was enabled and its current text afterwards.
        """

        combo   = getattr(self.window, widget)
        enabled = self.usable(combo)
        if enabled and index is not None:
            combo.setCurrentIndex(index)
        elif enabled:
            combo.setCurrentText(text)
        return {"applied": enabled, "text": combo.currentText()}

    def act_click(self, widget: str) -> dict:
        """Clicks a push or radio button.

        Args:
            widget : Attribute name of the button.

        Returns:
            Whether the button was enabled.
        """

        button  = getattr(self.window, widget)
        enabled = self.usable(button)
        button.click()
        return {"clicked": enabled}

    def act_tick(self, count: int) -> dict:
        """Runs the play timer's timeout slot ``count`` times.

        Args:
            count : Number of 500 ms timer periods to simulate.

        Returns:
            Slider value after each tick.
        """

        values = []
        for _ in range(count):
            self.window.runTab1Slider()
            self.settle(2)
            values.append(self.window.tab1Slider.value())
        return {"slider_values": values}

    def act_axes(self, values: dict, accept: bool = True, grab: str | None = None) -> dict:
        """Clicks Axes with the dialog answering ``values``.

        Args:
            values : Fields to type: x_label, z_label, x_min, x_max, z_min, z_max.
            accept : Whether to press Ok (else Cancel).
            grab   : Path to save an image of the dialog, None for none.

        Returns:
            Whether the Axes button was enabled.
        """

        self.stubs.axes_values = values
        self.stubs.axes_accept = accept
        self.stubs.axes_grab   = grab
        enabled                = self.usable(self.window.tab2AxesButton)
        self.window.tab2AxesButton.click()
        self.stubs.axes_values = {}
        return {"clicked": enabled}

    def act_metadata(self) -> dict:
        """Calls getCurrentMetadata.

        Returns:
            The metadata dictionary as TomoVis builds it.
        """

        return self.probe.plain(self.window.getCurrentMetadata())

    def act_save(self, path: str | None, direct: bool = False) -> dict:
        """Triggers File > Save with the dialog answering ``path``.

        Args:
            path   : Path the save dialog returns, None to cancel.
            direct : Call saveFileCallBack directly, for branches the disabled menu action cannot reach.

        Returns:
            Whether the action was enabled.
        """

        self.stubs.save_path = path
        enabled              = self.window.saveFile.isEnabled()
        if direct:
            self.window.saveFileCallBack()
        else:
            self.window.saveFile.trigger()
        self.stubs.save_path = None
        return {"triggered": enabled, "direct": direct}

    def act_open(self, path: str | None) -> dict:
        """Triggers File > Open with the dialog answering ``path``.

        Args:
            path : Session file the dialog returns, None to cancel.

        Returns:
            Whether the action was enabled.
        """

        self.stubs.open_path = path
        self.window.openFile.trigger()
        self.stubs.open_path = None
        return {"triggered": True}

    def act_read_session(self, path: str) -> dict:
        """Reads back a session file written by saveFileCallBack.

        Args:
            path : Session .hd5 file.

        Returns:
            Dataset shape and dtype, and every metadata attribute with its value and stored type.
        """

        with h5py.File(path, "r") as h5f:
            data  = h5f["data"]
            attrs = {}
            for key in h5f["metadata"].attrs.keys():
                value      = h5f["metadata"].attrs[key]
                attrs[key] = {"value": self.probe.plain(value), "type": type(value).__name__, "dtype": str(getattr(value, "dtype", ""))}
            return {"keys": list(h5f.keys()), "data_shape": list(data.shape), "data_dtype": str(data.dtype), "attrs": attrs}

    def act_layout(self) -> dict:
        """Reads the geometry and font of the window's named widgets at the current size.

        Returns:
            Widget name to visibility, window-relative rectangle [x, y, width, height] and font (requested and resolved family, point size, weight).
        """

        window  = self.window
        widgets = {"window": window, "menuBar": window.mainMenu, "tabWidget": window.tabWidget, "statusBar": window.statusBar()}

        for name in ("imv1", "imv2", "tab2Plot", "tab3Plot", "cameraTab4ButtonBox", "projectionTab4ButtonBox", "fourthTabWidget"):
            widgets[name] = getattr(window, name)
        for name in ("imv1_1", "imv1_2", "imv2_1", "imv2_2"):
            view = getattr(window, name)
            widgets[name]                  = view
            widgets[f"{name}.histogram"]   = view.ui.histogram
            widgets[f"{name}.roiBtn"]      = view.ui.roiBtn
            widgets[f"{name}.menuBtn"]     = view.ui.menuBtn
            widgets[f"{name}.graphicsView"] = view.ui.graphicsView
        for name in ("tab2Plot", "tab3Plot"):
            plot = getattr(window, name)
            widgets[f"{name}.toolbar"] = plot.toolbar
            widgets[f"{name}.canvas"]  = plot.canvas
        for name in dir(window):
            if name.startswith(("tab1", "tab2", "tab3")) or name.endswith("Tab4Button") or name in ("isoThresholdTab4Slider", "tab4Placeholder"):
                value = getattr(window, name, None)
                if isinstance(value, QtWidgets.QWidget) and name not in widgets:
                    widgets[name] = value

        layout = {}
        for name, widget in sorted(widgets.items()):
            if widget is None or isinstance(widget, QtWidgets.QGraphicsItem) or not isinstance(widget, QtWidgets.QWidget):
                continue
            corner = widget.mapTo(window, QtCore.QPoint(0, 0)) if widget is not window else QtCore.QPoint(0, 0)
            font   = widget.font()
            layout[name] = {
                "visible" : widget.isVisible(),
                "rect"    : [corner.x(), corner.y(), widget.width(), widget.height()],
                "font"    : {"family": font.family(), "resolved": QtGui.QFontInfo(font).family(), "point_size": font.pointSizeF(), "weight": font.weight()},
                "text"    : widget.text() if hasattr(widget, "text") and callable(widget.text) else None,
            }
        layout["tab4_layout_items"] = window.fourthTabWidgetLayout.count()
        return layout

    def act_tab(self, index: int) -> dict:
        """Selects a tab of the main QTabWidget.

        Args:
            index : Tab index (0 Slicer, 1 Plot, 2 Profile, 3 3D).

        Returns:
            The current tab index afterwards.
        """

        self.window.tabWidget.setCurrentIndex(index)
        return {"index": self.window.tabWidget.currentIndex()}

    def act_projection(self, name: str) -> dict:
        """Clicks one projection radio button of the 3D tab.

        Args:
            name : "mip", "iso", "translucent" or "additive".

        Returns:
            Whether the button was enabled.
        """

        return self.act_click(self.PROJECTIONS[name])

    def act_camera(self, name: str) -> dict:
        """Clicks one camera radio button of the 3D tab.

        Args:
            name : "Turntable", "Fly" or "Arcball".

        Returns:
            Whether the button was enabled.
        """

        return self.act_click(self.CAMERAS[name])

    def act_iso(self, value: int) -> dict:
        """Drags the ISO threshold slider one position at a time to ``value``, as a mouse drag does.

        Qt emits sliderMoved before it updates value(), and TomoVis reads
        value() in the slot, so each step applies the previous position.

        Args:
            value : Final slider position.

        Returns:
            Whether the slider was enabled, the positions passed and its value afterwards.
        """

        slider  = self.window.isoThresholdTab4Slider
        enabled = self.usable(slider)
        path    = []
        if enabled:
            step = 1 if value >= slider.value() else -1
            path = list(range(slider.value() + step, value + step, step))
            slider.setSliderDown(True)
            for position in path:
                slider.setSliderPosition(position)
            slider.setSliderDown(False)
        return {"applied": enabled, "positions": path, "value": slider.value()}

    def perform(self, action: str, args: dict) -> dict:
        """Runs one action, lets Qt settle and collects what happened.

        Args:
            action : Action name, the suffix of an ``act_`` method.
            args   : Keyword arguments of that method.

        Returns:
            Result of the action, dialog events, captured stdout lines and slot exceptions.
        """

        method = getattr(self, f"act_{action}")
        output = io.StringIO()
        result = None
        self.errors.armed = True
        with contextlib.redirect_stdout(output):
            try:
                result = method(**args)
            except Exception as error:
                self.errors.hook(type(error), error, error.__traceback__)
                self.errors.records[-1]["raised_by_direct_call"] = True
            finally:
                self.settle()
                self.errors.armed = False

        return {
            "result" : result,
            "events" : self.stubs.drain(),
            "stdout" : [line for line in output.getvalue().splitlines() if line.strip()],
            "errors" : self.errors.drain(),
        }
