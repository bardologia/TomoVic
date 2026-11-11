"""Replays the 59 TomoVis parity scenarios through the copied window and compares every step with the goldens.

Each golden was recorded by driving the original PyQt5 TomoVis headless
(webui/tools/tomovis_parity). The replay performs the same user actions as
API events on a fresh TomoVisWindow and compares, step by step, the controls,
window attributes, ROI geometry, image view levels and ranges, the computed
arrays (exact for integer and uint8 arrays, rtol 1e-6 for floats), the
metadata, the dialogs, the printed lines and the matplotlib figure layout.

Scenarios in which the original crashed are compared with their fixed
targets: the ``*_as_is`` and plain multi-channel imports with the
``rgb_levels_rgba_mode`` twins (D-1), the 4-channel import with
``import_four_channels_as_three`` (E-005), the numpy-2 RAT import with the
legacy-numpy one (E-006), the numeric hd5 attributes with the D-2 values and
the X [m] click on an empty window with E-011's kept state changes. Steps
that only drive the browser (layout, 3D camera, projection, ISO slider and
3D buttons) are skipped.

Figures are compared with tolerances because the goldens were drawn by
matplotlib 3.11.2 and TomoVic runs 3.10.8: layout numbers to 1e-6, tick
locations and labels as recorded, plotted line data exactly.
"""

from __future__ import annotations

import gzip
import hashlib
import json
from pathlib import Path

import h5py
import numpy as np
import pytest

from tests.webui.conftest import REPO_ROOT
from tomovis.window        import TomoVisWindow
from web_logger            import WebLogger

FIXTURES  = REPO_ROOT / "tests" / "webui" / "fixtures" / "tomovis"
SCENARIOS = sorted(path.name[:-len(".json.gz")] for path in (FIXTURES / "goldens").glob("*.json.gz"))


class GoldenFile:
    """One golden scenario: its JSON steps and NPZ arrays.

    Attributes:
        name   : Scenario name.
        doc    : Decoded JSON document.
        arrays : NPZ archive of the scenario's arrays.
    """

    def __init__(self, name: str) -> None:
        """Loads the scenario."""

        self.name   = name
        self.doc    = json.loads(gzip.open(FIXTURES / "goldens" / f"{name}.json.gz").read())
        self.arrays = np.load(FIXTURES / "goldens" / f"{name}.npz")

    @property
    def steps(self) -> list[dict]:
        """The recorded steps, step 0 being the fresh window."""

        return self.doc["steps"]

    def array(self, step: dict, name: str) -> np.ndarray | None:
        """Returns a step's array by name, None when the step has none."""

        key = step["arrays"].get(name)
        return None if key is None else self.arrays[key]


class GoldenReplay:
    """Performs golden actions on a TomoVisWindow through API events.

    Attributes:
        CLIENT_ACTIONS : Actions handled entirely by the browser.
        CLIENT_WIDGETS : Push buttons owned by the browser (3D tab).
        tmp            : Directory receiving the files the scenario saves.
        window         : The window under test.
        dialogs        : Dialog requests of the current step.
        printed        : Printed lines of the current step.
        slot_errors    : Slot exceptions of the current step.
        result         : Result of the current step's action.
    """

    CLIENT_ACTIONS = {"layout", "projection", "camera", "iso"}
    CLIENT_WIDGETS = {"colormapTab4Button", "resetCamerasTab4Button", "channelTab4Button"}
    PLOT_SIZE      = (1042, 649)
    PROFILE_SIZE   = (1042, 660)

    def __init__(self, tmp: Path) -> None:
        """Opens a fresh window sized like the goldens' 1100x880 window.

        Args:
            tmp : Directory for saved sessions.
        """

        self.tmp         = tmp
        self.dialogs     = []
        self.printed     = []
        self.slot_errors = []
        self.result      = None
        self.open_window()

    def open_window(self) -> None:
        """Creates a fresh window with the goldens' figure sizes."""

        self.window = TomoVisWindow(WebLogger("tomovis-test"), has3d=True)
        self.window.tab2Plot.resize(*self.PLOT_SIZE, 1)
        self.window.tab3Plot.resize(*self.PROFILE_SIZE, 1)
        self.window.drain()

    def input_path(self, path: str | None) -> str | None:
        """Maps a golden path to the fixture tree."""

        return None if path is None else path.replace("<fixtures>", str(FIXTURES))

    def output_path(self, path: str | None) -> str | None:
        """Maps a golden save path to the temporary tree, mirroring its sub-directories."""

        if path is None:
            return None
        target = Path(path.replace("<fixtures>", str(self.tmp)))
        if target.parent.name == "sessions":
            target.parent.mkdir(parents=True, exist_ok=True)
        return str(target)

    def send(self, event: dict) -> None:
        """Dispatches one event and collects its output."""

        self.window.handle(event)
        output = self.window.drain()
        self.dialogs.extend(output.dialogs)
        self.printed.extend(output.printed)
        self.slot_errors.extend(output.slot_errors)

    def answer(self, accepted: bool, **fields) -> None:
        """Answers the pending dialog."""

        token = self.window.dialogs.pendingToken()
        self.send({"type": "dialog_result", "token": token, "accepted": accepted, **fields})

    def act_import(self, kind: str, path: str | None, legacy_numpy: bool = False) -> None:
        """File > Import > <kind>, answering the file dialog."""

        action = {"hd5": "openFUSAR", "rat": "openRAT", "h5": "openUAVSAR", "npy": "openNpy"}[kind]
        self.send({"type": "trigger", "widget": action})
        if path is None:
            self.answer(False)
        else:
            self.answer(True, path=self.input_path(path))

    def act_inject(self, path: str, select: list[int] | None = None) -> None:
        """Sets the cube directly and initialises the window, as the parity harness does."""

        array = np.load(self.input_path(path))
        if select is not None:
            array = array[select]
        self.window.data = array
        self.window.setDefaultElevRangeIfMissing()
        self.window.initializeVisualizerWithData()
        output = self.window.drain()
        self.slot_errors.extend(output.slot_errors)

    def act_set_roi(self, ax, ay, angle, length, pos_x, pos_y) -> None:
        """Types the six ROI fields and clicks Set."""

        for index, text in enumerate((ax, ay, angle, length, pos_x, pos_y), start=1):
            getattr(self.window, f"tab1QLineEdit{index}").setText(text)
        self.send({"type": "click", "widget": "tab1SetButton"})

    def act_channel(self, mode: str) -> None:
        """Data > Channel > <mode>."""

        self.send({"type": "trigger", "widget": {"RGB": "allChMenu", "Red": "ch1Menu", "Green": "ch2Menu", "Blue": "ch3Menu"}[mode]})

    def act_check(self, widget: str, checked: bool) -> None:
        """Check box click."""

        self.send({"type": "check", "widget": widget, "checked": checked})

    def act_value(self, widget: str, value) -> None:
        """Slider or spin box value."""

        self.send({"type": "value", "widget": widget, "value": value})

    def act_combo(self, widget: str, index: int | None = None, text: str | None = None) -> None:
        """Combo selection by index or text."""

        combo = getattr(self.window, widget)
        self.send({"type": "index", "widget": widget, "index": index if index is not None else combo.findText(text)})

    def act_click(self, widget: str) -> None:
        """Push button click."""

        self.send({"type": "click", "widget": widget})

    def act_tick(self, count: int) -> None:
        """Play timer ticks."""

        values = []
        for _ in range(count):
            self.send({"type": "tick"})
            values.append(self.window.tab1Slider.value())
        self.result = {"slider_values": values}

    def act_axes(self, values: dict, accept: bool = True, grab=None) -> None:
        """Axes button and its dialog."""

        self.send({"type": "click", "widget": "tab2AxesButton"})
        if accept:
            self.answer(True, values=dict(values))
        else:
            self.answer(False)

    def act_metadata(self) -> None:
        """getCurrentMetadata()."""

        self.result = self.window.metadata()

    def act_save(self, path: str | None, direct: bool = False) -> None:
        """File > Save (or the direct call the disabled action cannot reach)."""

        if direct:
            self.window.boundary.run(self.window.saveFileCallBack, ())
            output = self.window.drain()
            self.dialogs.extend(output.dialogs)
            return
        self.send({"type": "trigger", "widget": "saveFile"})
        if path is None:
            self.answer(False)
        else:
            self.answer(True, path=self.output_path(path))

    def act_open(self, path: str | None) -> None:
        """File > Open; session files are the originals the desktop app wrote."""

        self.send({"type": "trigger", "widget": "openFile"})
        if path is None:
            self.answer(False)
        else:
            self.answer(True, path=self.input_path(path))

    def act_read_session(self, path: str) -> None:
        """Reads back the session file this replay wrote."""

        with h5py.File(self.output_path(path), "r") as h5f:
            attrs = {}
            for key in h5f["metadata"].attrs.keys():
                value      = h5f["metadata"].attrs[key]
                attrs[key] = {"value": SnapshotProbe.plain(value), "type": type(value).__name__, "dtype": str(getattr(value, "dtype", ""))}
            self.result = {"keys": list(h5f.keys()), "data_shape": list(h5f["data"].shape), "data_dtype": str(h5f["data"].dtype), "attrs": attrs}

    def act_fresh_window(self) -> None:
        """Replaces the window, as restarting the app."""

        self.open_window()

    def act_tab(self, index: int) -> None:
        """Tab click."""

        self.send({"type": "tab", "index": index})

    def perform(self, action: str, args: dict) -> bool:
        """Runs one golden action.

        Returns:
            False when the action belongs to the browser and was skipped.
        """

        self.dialogs     = []
        self.printed     = []
        self.slot_errors = []
        self.result      = None
        if action in self.CLIENT_ACTIONS or (action == "click" and args["widget"] in self.CLIENT_WIDGETS):
            return False
        getattr(self, f"act_{action}")(**args)
        return True


class SnapshotProbe:
    """Reads the replayed window in the goldens' format."""

    @staticmethod
    def plain(value):
        """Converts numpy values to plain Python values as the parity harness does."""

        if isinstance(value, (bool, np.bool_)):
            return bool(value)
        if isinstance(value, (int, np.integer)):
            return int(value)
        if isinstance(value, (float, np.floating)):
            return float(value)
        if isinstance(value, bytes):
            return value.decode("utf-8", "replace")
        if isinstance(value, dict):
            return {str(key): SnapshotProbe.plain(item) for key, item in value.items()}
        if isinstance(value, (list, tuple, np.ndarray)):
            return [SnapshotProbe.plain(item) for item in value]
        return value

    @staticmethod
    def sha1(array: np.ndarray) -> str:
        """Hashes a cube as the goldens' data_summary does."""

        digest = hashlib.sha1()
        digest.update(str(array.dtype).encode())
        digest.update(str(array.shape).encode())
        digest.update(np.ascontiguousarray(array).tobytes())
        return digest.hexdigest()

    def roi(self, window: TomoVisWindow) -> dict:
        """The goldens' state.roi record."""

        ax, ay, bx, by, theta, length = window.computeLinePar()
        state  = window.roi_1.getState()
        record = {"Ax": ax, "Ay": ay, "Bx": bx, "By": by, "theta": theta, "length": length, "pos": [state["pos"].x(), state["pos"].y()], "handles": [[h["item"].pos().x(), h["item"].pos().y()] for h in window.roi_1.handles], "image_shape": self.plain(window.getCurrentImageShape())}
        if getattr(window, "img", None) is not None:
            record["effective_line"]       = self.plain(window.getEffectiveROILine())
            record["axis_mode"]            = window.getROIAxisMode()
            record["effective_resolution"] = window.getEffectiveROIResolution()
            record["x_index_of_spinbox"]   = window.xPhysicalToIndex(float(window.tab2SpinBox.value()))
        return record

    def ticks(self, axis) -> dict:
        """Tick locations and labels of one axis."""

        return {"locations": [float(value) for value in axis.get_ticklocs()], "labels": [label.get_text() for label in axis.get_ticklabels()]}

    def figure(self, figure, size_px: list[int]) -> dict:
        """The goldens' figure record at the golden's pixel size."""

        fig = figure.getFigure()
        fig.set_size_inches(size_px[0] / fig.dpi, size_px[1] / fig.dpi)
        figure.canvas.draw()
        params = fig.subplotpars
        record = {"subplotpars": {"left": params.left, "right": params.right, "top": params.top, "bottom": params.bottom, "wspace": params.wspace, "hspace": params.hspace}, "axes": []}
        for ax in fig.axes:
            position = ax.get_position()
            entry    = {
                "position"    : [float(position.x0), float(position.y0), float(position.width), float(position.height)],
                "is_colorbar" : hasattr(ax, "_colorbar"),
                "xlim"        : [float(value) for value in ax.get_xlim()],
                "ylim"        : [float(value) for value in ax.get_ylim()],
                "xlabel"      : ax.get_xlabel(),
                "ylabel"      : ax.get_ylabel(),
                "xlabel_size" : float(ax.xaxis.label.get_fontsize()),
                "ylabel_size" : float(ax.yaxis.label.get_fontsize()),
                "title"       : ax.get_title(),
                "title_size"  : float(ax.title.get_fontsize()),
                "xticks"      : self.ticks(ax.xaxis),
                "yticks"      : self.ticks(ax.yaxis),
                "grid"        : bool(any(line.get_visible() for line in ax.xaxis.get_gridlines())),
                "images"      : [{"extent": [float(value) for value in image.get_extent()], "shape": list(np.asarray(image.get_array()).shape), "dtype": str(np.asarray(image.get_array()).dtype), "cmap": image.get_cmap().name, "clim": [float(value) for value in image.get_clim()], "origin": image.origin} for image in ax.get_images()],
                "lines"       : [(np.asarray(line.get_xdata(), dtype=float), np.asarray(line.get_ydata(), dtype=float), float(line.get_linewidth()), line.get_label()) for line in ax.get_lines()],
                "legend"      : None if ax.get_legend() is None else [text.get_text() for text in ax.get_legend().get_texts()],
            }
            record["axes"].append(entry)
        return record


class GoldenComparison:
    """Compares one replayed step with its golden step and collects every difference.

    Attributes:
        golden      : Golden file of the target state.
        probe       : Snapshot probe.
        differences : Human-readable differences found so far.
    """

    FLOAT_RTOL       = 1e-6
    CLIENT_CONTROLS  = {"turntableCameraTab4Button", "flyCameraTab4Button", "arcballCameraTab4Button", "mipProjectionTab4Button", "isoProjectionTab4Button", "translucentProjectionTab4Button", "additiveProjectionTab4Button"}

    def __init__(self, golden: GoldenFile) -> None:
        """Starts with no differences."""

        self.golden      = golden
        self.probe       = SnapshotProbe()
        self.differences = []

    def close(self, mine, theirs) -> bool:
        """Compares nested values: floats to rtol 1e-6 (absolute 1e-9 near zero), everything else exactly."""

        if isinstance(theirs, float) or isinstance(mine, float):
            if theirs is None or mine is None:
                return theirs is mine
            return bool(np.isclose(float(mine), float(theirs), rtol=self.FLOAT_RTOL, atol=1e-9))
        if isinstance(theirs, list) and isinstance(mine, (list, tuple)):
            return len(mine) == len(theirs) and all(self.close(a, b) for a, b in zip(mine, theirs))
        if isinstance(theirs, dict) and isinstance(mine, dict):
            return all(key in mine and self.close(mine[key], value) for key, value in theirs.items())
        return mine == theirs

    def check(self, where: str, mine, theirs) -> None:
        """Records a difference when the values differ."""

        if not self.close(mine, theirs):
            self.differences.append(f"{where}: port {mine!r} != golden {theirs!r}")

    def controls(self, label: str, window: TomoVisWindow, golden: dict, iso_owned_by_client: bool) -> None:
        """Compares the controls the golden records."""

        mine = window.events.controls()
        for name, fields in golden.items():
            if name in self.CLIENT_CONTROLS or (name == "isoThresholdTab4Slider" and iso_owned_by_client):
                continue
            if name == "roi_1":
                self.check(f"{label} controls.roi_1.view", mine["roi_1"]["view"], fields["view"])
                continue
            for field, value in fields.items():
                self.check(f"{label} controls.{name}.{field}", mine[name].get(field), value)

    def attributes(self, label: str, window: TomoVisWindow, golden: dict) -> None:
        """Compares the window attributes."""

        mine = window.attributes()
        mine["bins"] = SnapshotProbe.plain(getattr(window, "bins", None))
        for name, value in golden.items():
            if name == "data_summary":
                self.check(f"{label} data sha1", self.probe.sha1(window.data), value["sha1"])
                continue
            self.check(f"{label} attributes.{name}", mine.get(name), value)

    def views(self, label: str, window: TomoVisWindow, golden: dict) -> None:
        """Compares image presence, shape, dtype, level mode, levels and the padded histogram range."""

        for name, record in golden.items():
            view = getattr(window, name).snapshot()
            self.check(f"{label} views.{name}.has_image", view["has_image"], record["has_image"])
            if not record["has_image"] or not view["has_image"]:
                continue
            self.check(f"{label} views.{name}.image_shape", view["image_shape"], record["image_shape"])
            self.check(f"{label} views.{name}.image_dtype", view["image_dtype"], record["image_dtype"])
            self.check(f"{label} views.{name}.level_mode", view["level_mode"], record["level_mode"])
            self.check(f"{label} views.{name}.levels", view["levels"], record["item_levels"])
            low, high = view["histogram_range"]
            pad       = 0.1 * (high - low)
            self.check(f"{label} views.{name}.histogram_range", [low - pad, high + pad], record["histogram_range"])

    def arrays(self, label: str, window: TomoVisWindow, step: dict) -> None:
        """Compares the computed arrays: integers exactly, floats to rtol 1e-6."""

        for name in ("img", "d2", "aux", "d2Norm", "rgbArray", "z_axis", "volume_input"):
            theirs = self.golden.array(step, name)
            if theirs is None:
                continue
            mine = window.volume_data if name == "volume_input" else getattr(window, name, None)
            if mine is None:
                self.differences.append(f"{label} arrays.{name}: missing in the port")
                continue
            mine = np.asarray(mine)
            if mine.shape != theirs.shape or mine.dtype != theirs.dtype:
                self.differences.append(f"{label} arrays.{name}: port {mine.shape} {mine.dtype} != golden {theirs.shape} {theirs.dtype}")
                continue
            equal = np.array_equal(mine, theirs) if mine.dtype.kind in "iub" else np.allclose(mine, theirs, rtol=self.FLOAT_RTOL, atol=0.0, equal_nan=True)
            if not equal:
                self.differences.append(f"{label} arrays.{name}: values differ (max abs {np.max(np.abs(mine.astype(float) - theirs.astype(float)))})")

    def figures(self, label: str, window: TomoVisWindow, step: dict) -> None:
        """Compares the Plot and Profile figure layout, labels, images and line data."""

        for tag, figure in (("plot", window.tab2Plot), ("profile", window.tab3Plot)):
            record = step["figures"][tag]
            mine   = self.probe.figure(figure, record["size_px"])
            self.check(f"{label} {tag}.axes count", len(mine["axes"]), len(record["axes"]))
            if len(mine["axes"]) != len(record["axes"]):
                continue
            if record["axes"]:
                self.check(f"{label} {tag}.subplotpars", mine["subplotpars"], record["subplotpars"])
            for index, (axes, golden) in enumerate(zip(mine["axes"], record["axes"])):
                where = f"{label} {tag}.ax{index}"
                for field in ("position", "is_colorbar", "xlim", "ylim", "xlabel", "ylabel", "xlabel_size", "ylabel_size", "title", "title_size", "xticks", "yticks", "grid"):
                    self.check(f"{where}.{field}", axes[field], golden[field])
                for k, (image, theirs) in enumerate(zip(axes["images"], golden["images"])):
                    self.check(f"{where}.image{k}", image, {key: theirs[key] for key in ("extent", "shape", "dtype", "cmap", "clim", "origin")})
                self.check(f"{where}.image count", len(axes["images"]), len(golden["images"]))
                self.check(f"{where}.line count", len(axes["lines"]), len(golden["lines"]))
                for k, ((x, y, width, line_label), theirs) in enumerate(zip(axes["lines"], golden["lines"])):
                    self.check(f"{where}.line{k}.linewidth", width, theirs["linewidth"])
                    self.check(f"{where}.line{k}.label", line_label, theirs["label"])
                    gx = self.golden.array(step, theirs["x_key"])
                    gy = self.golden.array(step, theirs["y_key"])
                    if x.shape != gx.shape or not np.allclose(x, gx, rtol=self.FLOAT_RTOL) or y.shape != gy.shape or not np.allclose(y, gy, rtol=self.FLOAT_RTOL):
                        self.differences.append(f"{where}.line{k}: data differ")
                if golden["legend"] is not None:
                    self.check(f"{where}.legend", axes["legend"], golden["legend"]["texts"])

    def dialogs(self, label: str, mine: list[dict], golden: list[dict], tmp: Path) -> None:
        """Compares dialog requests with the golden's dialog events."""

        mine = [dict(request, text=request["text"].replace(str(tmp), "<fixtures>").replace(str(FIXTURES), "<fixtures>")) if request["kind"] == "message" else request for request in mine]
        self.check(f"{label} dialog count", len(mine), len(golden))
        for request, event in zip(mine, golden):
            where = f"{label} dialog {event['kind']}"
            if event["kind"] == "file_dialog":
                self.check(where, (request["kind"], request["mode"], request["title"], request["filters"]), ("file", "open", event["title"], event["name_filter"]))
            elif event["kind"] in ("save_dialog", "open_dialog"):
                self.check(where, (request["kind"], request["mode"], request["title"], request["filters"]), ("file", event["kind"][:-len("_dialog")], event["title"], [event["name_filter"]]))
            elif event["kind"] == "message_box":
                self.check(where, (request["kind"], request["level"], request["title"], request["text"]), ("message", event["level"], event["title"], event["text"]))
            elif event["kind"] == "axes_dialog":
                initial = event["initial"]
                self.check(where, (request["kind"], request["title"], request["values"]), ("axes", initial["title"], {"x_label": initial["x_label"], "z_label": initial["z_label"], "x_min": initial["x_min"]["value"], "x_max": initial["x_max"]["value"], "z_min": initial["z_min"]["value"], "z_max": initial["z_max"]["value"]}))

    def step(self, label: str, replay: GoldenReplay, step: dict, iso_owned_by_client: bool, compare_dialogs: bool = True) -> None:
        """Compares everything one step records."""

        window = replay.window
        state  = step["state"]
        self.controls(label, window, state["controls"], iso_owned_by_client)
        self.attributes(label, window, state["attributes"])
        self.check(f"{label} roi", self.probe.roi(window), state["roi"])
        self.views(label, window, state["views"])
        self.arrays(label, window, step)
        self.figures(label, window, step)
        if compare_dialogs:
            self.dialogs(label, replay.dialogs, step["events"], replay.tmp)
        if step["action"] in ("metadata", "read_session", "tick"):
            self.check(f"{label} result", SnapshotProbe.plain(replay.result), step["result"])
        self.check(f"{label} printed", replay.printed, [line for line in step["stdout"]])


class FixedTargets:
    """Where the original crashed, the golden whose state is the target of the fix.

    Attributes:
        TWINS : Scenario to (target scenario, step mapping) for scenarios the original ran into E-001..E-006.
    """

    TWINS = {
        "import_npy_channels_2"    : "import_npy_channels_2_levels_fixed",
        "import_npy_channels_3"    : "import_npy_channels_3_levels_fixed",
        "import_npy_covariance_5d" : "import_npy_covariance_5d_levels_fixed",
        "channels_3_modes_as_is"   : "channels_3_modes",
        "import_rat_numpy2"        : "import_rat_legacy_numpy",
    }

    def target(self, name: str) -> GoldenFile:
        """Returns the golden a scenario is compared with."""

        return GoldenFile(self.TWINS.get(name, name))


def replay_scenario(name: str, tmp: Path) -> tuple[GoldenReplay, list[str]]:
    """Replays one scenario and compares every step with its target golden.

    Args:
        name : Scenario name.
        tmp  : Directory for saved files.

    Returns:
        (the replay, differences).
    """

    source  = GoldenFile(name)
    target  = FixedTargets().target(name)
    compare = GoldenComparison(target)
    replay  = GoldenReplay(tmp)

    compare.step(f"{name} step 0", replay, target.steps[0], False)

    iso_owned_by_client = False
    for index, (step, goal) in enumerate(zip(source.steps[1:], target.steps[1:]), start=1):
        ran = replay.perform(step["action"], step["args"])
        if not ran:
            iso_owned_by_client = True
            continue
        label = f"{name} step {index} {step['action']}"
        compare.differences.extend(f"{label}: slot error {error}" for error in replay.slot_errors)
        if name in ("import_fusar_numeric_attrs", "import_npy_channels_4", "channels_4_after_crash"):
            continue
        if name == "startup_empty" and step["action"] == "check":
            goal = dict(goal, events=[])
        compare.step(label, replay, goal, iso_owned_by_client)
    return replay, compare.differences


@pytest.mark.parametrize("name", SCENARIOS)
def test_scenario_replays_like_the_original(name, tmp_path):
    """Every step of the scenario matches the original's recorded state (or the fixed target where it crashed)."""

    _, differences = replay_scenario(name, tmp_path)

    assert differences == []


def test_numeric_hd5_attributes_import_with_the_d2_parser(tmp_path):
    """D-2: numeric hd5 attributes, where eval raised, import with z range [-1, 4] and x_res 0.3."""

    replay, differences = replay_scenario("import_fusar_numeric_attrs", tmp_path)
    window              = replay.window

    assert differences == []
    assert window.z_range == [-1.0, 4.0]
    assert window.x_res == pytest.approx(0.3)
    assert window.img.shape == (12, 10)
    assert window.d2 is not None


def test_four_channel_cube_imports_as_three_channels(tmp_path):
    """E-005: a 4-channel npy import keeps channels 0, 1, 3 with nChannels 3, as import_four_channels_as_three injects it."""

    replay, differences = replay_scenario("import_npy_channels_4", tmp_path)
    target              = GoldenFile("import_four_channels_as_three")
    compare             = GoldenComparison(target)
    replay.dialogs, replay.printed = [], []

    compare.step("4-channel import vs injected", replay, dict(target.steps[1], action="inject"), False, compare_dialogs=False)

    assert differences == []
    assert compare.differences == []
    assert replay.window.metadata()["channel_mode"] == "RGB"


def test_channel_changes_after_a_four_channel_import_do_not_crash(tmp_path):
    """E-005: Red then RGB on the 4-channel cube run without slot errors and show the RGB composite again."""

    replay, differences = replay_scenario("channels_4_after_crash", tmp_path)

    assert differences == []
    assert replay.window.nChannels == 3
    assert replay.window.imv1.currentName() == "imv1_2"
    assert replay.window.aux.shape == (19, 10, 3)


def test_x_line_without_data_keeps_the_state_changes_and_draws_nothing(tmp_path):
    """E-011: ticking X [m] on an empty window enables the spin box at 0.5 and Plot (profile) without raising."""

    replay, differences = replay_scenario("startup_empty", tmp_path)
    window              = replay.window

    assert differences == []
    assert window.tab2SpinBox.isEnabled() and window.tab2SpinBox.value() == 0.5
    assert window.tab2PlotButton.isEnabled()

    replay.perform("click", {"widget": "tab2PlotButton"})

    assert replay.slot_errors == []
    assert window.tabWidget.currentIndex() == 0
    assert not window.tab3ClearButton.isEnabled()
