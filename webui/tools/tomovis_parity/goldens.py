"""Scenario catalogue, golden writer and static tables for the TomoVis port.

ScenarioBook lists every scripted session the original TomoVis is driven
through; GoldenRunner plays each one in a fresh window and GoldenWriter stores
what the window computed after every step: ``goldens/<scenario>.json.gz`` holds
the step list with actions, dialog events, printed lines, slot exceptions,
control states, ROI geometry, view levels, figure layouts and the keys of the
arrays; ``goldens/<scenario>.npz`` holds those arrays; ``figures/<hash>.png``
holds the rendered matplotlib canvases of the scenarios that commit them, and a
gitignored reference directory holds every render. TableWriter stores the
static look-up material: the TomoVis colortables, the 256-entry LUTs pyqtgraph
derives from them, the matplotlib colormap list of the Plot tab and the vispy
colormaps of the 3D tab. Machine paths are written as ``<fixtures>/...``.
"""

from __future__ import annotations

import gzip
import hashlib
import io
import json
import re
import zipfile
from pathlib import Path

import h5py
import matplotlib
import numpy as np
import vispy
from PIL import Image


class GoldenWriter:
    """Stores one scenario's steps as gzipped JSON plus a compressed array archive.

    Arrays are deduplicated by content within a scenario: a repeated array is
    referenced by the key of its first occurrence. The loaded cube (attribute
    ``data``) is never stored; each step records its SHA-1 and summary
    statistics instead, which a port reproduces by hashing its own array.
    Figure renders are written once per content hash to the reference
    directory (gitignored), and also to the committed ``figures`` directory
    for scenarios that set ``commit_figures``. Both archive formats are written
    byte-reproducibly (gzip mtime 0, zip entries dated 1980-01-01).

    Attributes:
        root           : Fixture root, replaced by ``<fixtures>`` in written strings.
        goldens        : Directory of the scenario JSON and NPZ files.
        figures        : Committed directory of figure PNG files.
        reference      : Gitignored directory holding every figure PNG.
        name           : Name of the scenario being written.
        document       : JSON document of the scenario being written.
        arrays         : Array key to array for the scenario being written.
        hashes         : Array content hash to key, for the scenario being written.
        commit_figures : Whether the current scenario's figures are committed.
    """

    ZIP_DATE = (1980, 1, 1, 0, 0, 0)
    ADDRESS  = re.compile(r" at 0x[0-9a-fA-F]+")

    def __init__(self, root: Path, reference: Path) -> None:
        """Creates the output directories.

        Args:
            root      : Fixture root directory.
            reference : Directory receiving every figure PNG (gitignored).
        """

        self.root           = root
        self.goldens        = root / "goldens"
        self.figures        = root / "figures"
        self.reference      = reference
        self.name           = None
        self.document       = None
        self.arrays         = {}
        self.hashes         = {}
        self.commit_figures = False

        self.goldens.mkdir(parents=True, exist_ok=True)
        self.figures.mkdir(parents=True, exist_ok=True)
        self.reference.mkdir(parents=True, exist_ok=True)

    def scrub(self, value):
        """Replaces the fixture root by ``<fixtures>`` and object addresses by ``0xADDRESS`` in every string.

        The 3D tab prints colormap objects whose repr holds a memory address,
        which would otherwise change on every run.

        Args:
            value : JSON-ready value.

        Returns:
            The value with machine paths made relative and addresses masked.
        """

        if isinstance(value, str):
            return self.ADDRESS.sub(" at 0xADDRESS", value.replace(str(self.root), "<fixtures>"))
        if isinstance(value, dict):
            return {key: self.scrub(item) for key, item in value.items()}
        if isinstance(value, list):
            return [self.scrub(item) for item in value]
        return value

    def start(self, scenario: dict, shims: list[str]) -> None:
        """Begins a scenario document.

        Args:
            scenario : Scenario entry from ScenarioBook with name, description, steps and optional flags.
            shims    : Names of the toolkit shims active during the scenario.
        """

        self.name           = scenario["name"]
        self.commit_figures = scenario.get("commit_figures", False)
        self.arrays         = {}
        self.hashes         = {}
        self.document       = {"scenario": self.name, "description": scenario["description"], "toolkit_shims": shims, "window_size": None, "steps": []}

    def digest(self, array: np.ndarray) -> str:
        """Hashes dtype, shape and bytes of an array.

        Args:
            array : Any numpy array.

        Returns:
            Hex SHA-1 of ``str(dtype)``, then ``str(shape)``, then the C-order bytes.
        """

        contiguous = np.ascontiguousarray(array)
        hasher     = hashlib.sha1()
        hasher.update(str(contiguous.dtype).encode())
        hasher.update(str(contiguous.shape).encode())
        hasher.update(contiguous.tobytes())
        return hasher.hexdigest()

    def array(self, step: int, name: str, value: np.ndarray) -> str:
        """Adds an array to the scenario archive unless an identical one is stored.

        Args:
            step  : Step index.
            name  : Array name within the step.
            value : The array.

        Returns:
            Key of the stored array in the scenario NPZ.
        """

        digest = self.digest(value)
        if digest in self.hashes:
            return self.hashes[digest]
        key = f"s{step:02d}_{name}"
        self.arrays[key]    = np.ascontiguousarray(value)
        self.hashes[digest] = key
        return key

    def figure(self, render: np.ndarray) -> dict:
        """Writes a figure render as an RGB PNG to the reference directory, and to ``figures`` when committed.

        Args:
            render : Uint8 RGBA canvas pixels (rows, cols, 4).

        Returns:
            File name of the PNG and whether it is in the committed ``figures`` directory.
        """

        name  = f"{self.digest(render)[:16]}.png"
        image = Image.fromarray(np.ascontiguousarray(render[..., :3]))
        if not (self.reference / name).exists():
            image.save(self.reference / name, optimize=True)
        if self.commit_figures and not (self.figures / name).exists():
            image.save(self.figures / name, optimize=True)
        return {"png": name, "png_committed": self.commit_figures}

    def data_summary(self, value: np.ndarray) -> dict:
        """Summarizes the loaded cube instead of storing it.

        Args:
            value : The window's ``data`` array.

        Returns:
            SHA-1 (as digest()), and the finite min, max and mean of its magnitude with the count of non-finite samples.
        """

        magnitude = np.abs(value).astype(np.float64)
        finite    = np.isfinite(magnitude)
        return {
            "sha1"       : self.digest(value),
            "abs_min"    : float(magnitude[finite].min()) if finite.any() else None,
            "abs_max"    : float(magnitude[finite].max()) if finite.any() else None,
            "abs_mean"   : float(magnitude[finite].mean()) if finite.any() else None,
            "non_finite" : int((~finite).sum()),
        }

    def step(self, index: int, action: str, args: dict, outcome: dict, state: dict, arrays: dict, figures: dict) -> None:
        """Adds one step with its outcome and captured state.

        Args:
            index   : Step index.
            action  : Action name.
            args    : Action arguments as written in the scenario.
            outcome : Result, events, stdout and errors from TomoVisSession.perform.
            state   : State from StateProbe.capture.
            arrays  : Named arrays from StateProbe.capture.
            figures : Figure records and renders from StateProbe.capture.
        """

        keys = {}
        for name, value in sorted(arrays.items()):
            if name == "data":
                state["attributes"]["data_summary"] = self.data_summary(value)
                continue
            keys[name] = self.array(index, name, value)

        figure_records = {}
        for tag, figure in figures.items():
            record = dict(figure["record"])
            if figure["render"] is not None:
                record.update(self.figure(figure["render"]))
            figure_records[tag] = record

        self.document["steps"].append(self.scrub({
            "index"   : index,
            "action"  : action,
            "args"    : args,
            **outcome,
            "state"   : state,
            "arrays"  : keys,
            "figures" : figure_records,
        }))

    def write_npz(self, path: Path) -> None:
        """Writes the scenario arrays as an NPZ archive with fixed entry dates.

        Args:
            path : Destination file.
        """

        with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for key in sorted(self.arrays):
                buffer = io.BytesIO()
                np.lib.format.write_array(buffer, self.arrays[key], allow_pickle=False)
                entry               = zipfile.ZipInfo(f"{key}.npy", date_time=self.ZIP_DATE)
                entry.compress_type = zipfile.ZIP_DEFLATED
                archive.writestr(entry, buffer.getvalue(), compresslevel=9)

    def finish(self, window_size: tuple[int, int]) -> tuple[Path, Path]:
        """Writes the scenario JSON (gzip) and NPZ files.

        Args:
            window_size : Window size the scenario ran at (width, height).

        Returns:
            Paths of the JSON and NPZ files.
        """

        self.document["window_size"] = list(window_size)
        json_path = self.goldens / f"{self.name}.json.gz"
        npz_path  = self.goldens / f"{self.name}.npz"
        payload   = json.dumps(self.document, separators=(",", ":")).encode("utf-8")
        json_path.write_bytes(gzip.compress(payload, compresslevel=9, mtime=0))
        self.write_npz(npz_path)
        return json_path, npz_path


class ScenarioBook:
    """Catalogue of scripted TomoVis sessions, grouped by feature.

    Paths are written with the ``<fixtures>`` placeholder; GoldenRunner
    resolves it before calling the session. A scenario may set
    ``rgb_levels: "rgba_mode"`` to run with RgbLevelsShim enabled (the RGB
    pipeline working, as the port must behave) and ``commit_figures: True`` to
    copy its figure renders into the committed fixtures. Scenarios without
    ``rgb_levels`` show the original exactly as it runs on pyqtgraph 0.14.
    """

    INPUTS   = "<fixtures>/inputs"
    SESSIONS = "<fixtures>/sessions"

    OBLIQUE = ("1", "2", "30", "25", "0", "0")
    AXES    = {"x_label": "Distance [m]", "z_label": "Height [m]", "x_min": 0.5, "x_max": 11.25, "z_min": -5.0, "z_max": 25.0}

    def step(self, action: str, **args) -> dict:
        """Builds one step.

        Args:
            action : Action name understood by TomoVisSession.perform.
            args   : Keyword arguments of the action.

        Returns:
            Step dictionary.
        """

        return {"action": action, "args": args}

    def load(self, kind: str, name: str, **extra) -> dict:
        """Builds an import step for one input fixture.

        Args:
            kind  : Import menu entry: "hd5", "rat", "h5" or "npy".
            name  : File name inside ``inputs``.
            extra : Further import arguments (legacy_numpy).

        Returns:
            Step dictionary.
        """

        return self.step("import", kind=kind, path=f"{self.INPUTS}/{name}", **extra)

    def roi(self, ax: str, ay: str, angle: str, length: str, pos_x: str = "0", pos_y: str = "0") -> dict:
        """Builds a step that types the six ROI fields and clicks Set.

        Args:
            ax     : Ax text.
            ay     : Ay text.
            angle  : Angle text in degrees.
            length : Length text in pixels.
            pos_x  : Pos x text.
            pos_y  : Pos y text.

        Returns:
            Step dictionary.
        """

        return self.step("set_roi", ax=ax, ay=ay, angle=angle, length=length, pos_x=pos_x, pos_y=pos_y)

    def check(self, widget: str, checked: bool) -> dict:
        """Builds a checkbox step.

        Args:
            widget  : Checkbox attribute name.
            checked : Wanted state.

        Returns:
            Step dictionary.
        """

        return self.step("check", widget=widget, checked=checked)

    def value(self, widget: str, value) -> dict:
        """Builds a slider or spin box step.

        Args:
            widget : Widget attribute name.
            value  : New value.

        Returns:
            Step dictionary.
        """

        return self.step("value", widget=widget, value=value)

    def click(self, widget: str) -> dict:
        """Builds a button click step.

        Args:
            widget : Button attribute name.

        Returns:
            Step dictionary.
        """

        return self.step("click", widget=widget)

    def startup(self) -> list[dict]:
        """Scenarios on a window without data.

        Returns:
            Scenario list.
        """

        return [{
            "name"        : "startup_empty",
            "description" : "Fresh window: initial controls, metadata without data, the X [m] checkbox that is enabled at startup (crashes without data), Save with no data called directly (the menu action is disabled), and the four tabs.",
            "steps"       : [
                self.step("layout"),
                self.step("tab", index=1),
                self.step("layout"),
                self.step("tab", index=2),
                self.step("layout"),
                self.step("tab", index=3),
                self.step("layout"),
                self.step("tab", index=0),
                self.step("metadata"),
                self.step("save", path=None, direct=True),
                self.check("tab2ChkBox3", True),
            ],
        }]

    def imports(self) -> list[dict]:
        """Scenarios for every importer and input variant.

        Returns:
            Scenario list.
        """

        cases = [
            ("import_fusar_two_key_elev",   "hd5", "fusar_two_key_elev.hd5",   {}, "FuSAR .hd5 with two keys: key index 1 is read; elevation_limits sets z_range; ps_az and ps_rg set x_res and y_res."),
            ("import_fusar_one_key_range",  "hd5", "fusar_one_key_range.hd5",  {}, "FuSAR .hd5 with one key: key index 0; the range attribute sets z_range."),
            ("import_fusar_both_attrs",     "hd5", "fusar_both_attrs.hd5",     {}, "elevation_limits wins over range."),
            ("import_fusar_no_attrs",       "hd5", "fusar_no_attrs.hd5",       {}, "No z attribute: z_range = [0, shape[-1] - 1] (the range axis length, a quirk)."),
            ("import_fusar_three_keys",     "hd5", "fusar_three_keys.hd5",     {}, "Three keys: key index 1 is read whatever its name."),
            ("import_fusar_bytes_attrs",    "hd5", "fusar_bytes_attrs.hd5",    {}, "Attributes stored as numpy bytes: eval accepts bytes."),
            ("import_fusar_numeric_attrs",  "hd5", "fusar_numeric_attrs.hd5",  {}, "Numeric attributes: eval raises TypeError inside the slot; data and z_range are left half-updated."),
            ("import_uavsar_three_keys",    "h5",  "uavsar_three_keys.h5",     {}, "UAVSAR .h5: key index 2, np.rollaxis(x, 1, 0), default z_range."),
            ("import_npy_real",             "npy", "npy_real.npy",             {}, "float32 .npy."),
            ("import_npy_float64",          "npy", "npy_float64.npy",          {}, "float64 .npy."),
            ("import_npy_complex_nan_inf",  "npy", "npy_complex_nan_inf.npy",  {}, "complex64 .npy with NaN and inf: sanitize_for_display zeroes them in the views."),
            ("import_npy_one_range_line",   "npy", "npy_one_range_line.npy",   {}, "shape[-1] == 1: the slider mid value is 0, valueChanged never fires and nothing is displayed."),
            ("import_rat_numpy2",           "rat", "rat_complex.rat",          {}, "RAT import as the original runs under numpy 2: rrat raises AttributeError (np.int) inside the slot."),
            ("import_rat_legacy_numpy",     "rat", "rat_complex.rat",          {"legacy_numpy": True}, "RAT import with np.int restored: the behaviour the port must reproduce."),
            ("import_npy_channels_2",       "npy", "npy_channels_2.npy",       {}, "Two channels: Blue menu entry disabled, RGB composite with an empty third plane."),
            ("import_npy_channels_3",       "npy", "npy_channels_3.npy",       {}, "Three channels: RGB composite with channels 0 and 1 swapped (index [1, 0, 2])."),
            ("import_npy_channels_4",       "npy", "npy_channels_4.npy",       {}, "Four channels: data keeps channels [0, 1, 3] but nChannels stays 4, so valueChanged raises IndexError inside the slot."),
            ("import_npy_covariance_5d",    "npy", "npy_covariance_5d.npy",    {}, "5-D covariance: np.moveaxis(np.sqrt(data.diagonal()), -1, 0) gives 3 complex channels."),
        ]

        scenarios = []
        for name, kind, file_name, extra, description in cases:
            scenarios.append({"name": name, "description": description, "steps": [self.load(kind, file_name, **extra), self.step("metadata")]})

        for name, file_name in (("import_npy_channels_2_levels_fixed", "npy_channels_2.npy"), ("import_npy_channels_3_levels_fixed", "npy_channels_3.npy"), ("import_npy_covariance_5d_levels_fixed", "npy_covariance_5d.npy")):
            scenarios.append({"name": name, "description": f"{file_name} with the RGB levels shim: the RGB composite, its per-channel levels and the RGB tomogram as the port must show them.", "rgb_levels": "rgba_mode", "steps": [self.load("npy", file_name), self.step("metadata")]})

        scenarios.append({
            "name"        : "import_cancel_and_reload",
            "description" : "Cancelled import changes nothing; importing a cube with a different range axis length, then the first cube again (same slider mid value: no valueChanged signal on reload).",
            "steps"       : [
                self.load("npy", "npy_real.npy"),
                self.step("import", kind="hd5", path=None),
                self.load("hd5", "fusar_one_key_range.hd5"),
                self.load("npy", "npy_real.npy"),
                self.load("hd5", "fusar_two_key_elev.hd5"),
                self.load("hd5", "fusar_two_key_elev.hd5"),
            ],
        })
        scenarios.append({
            "name"        : "import_four_channels_as_three",
            "description" : "Port target for the four-channel crash: the cube TomoVis keeps (channels 0, 1 and 3) injected as a three-channel cube, RGB levels shim on.",
            "rgb_levels"  : "rgba_mode",
            "steps"       : [self.step("inject", path=f"{self.INPUTS}/npy_channels_4.npy", select=[0, 1, 3]), self.roi(*self.OBLIQUE), self.click("tab1PlotButton")],
        })
        return scenarios

    def rois(self) -> list[dict]:
        """Scenarios for ROI geometry cases on a single-channel cube with x_res 0.5 and y_res 0.75.

        Returns:
            Scenario list.
        """

        cases = [
            ("roi_horizontal",          ("2", "10", "0", "20", "0", "0"),    "Horizontal ROI: azimuth axis, x from Ax * x_res."),
            ("roi_horizontal_reversed", ("25", "10", "180", "20", "0", "0"), "Horizontal ROI drawn right to left: samples run from A to B while x_min..x_max ascend."),
            ("roi_vertical",            ("12", "1", "90", "18", "0", "0"),   "Vertical ROI: range axis, x from Ay * y_res."),
            ("roi_oblique",             self.OBLIQUE,                         "Oblique ROI: projected distance with the effective resolution."),
            ("roi_oblique_with_pos",    ("1", "2", "-35", "20", "3", "4"),   "Oblique ROI upward with a non-zero ROI position (handles stored relative to it)."),
            ("roi_partly_outside",      ("-6", "-4", "25", "60", "0", "0"),  "ROI crossing the image border: Liang-Barsky clipping to [0, w-1] x [0, h-1]."),
            ("roi_fully_outside",       ("100", "100", "45", "10", "0", "0"), "ROI outside the image: tomogram views cleared, Plot shows an empty figure."),
            ("roi_zero_length",         ("5", "5", "0", "0", "0", "0"),      "Length 0: Set ignores the input and the ROI keeps its previous geometry."),
            ("roi_subpixel",            ("5", "5", "0", "0.6", "0", "0"),    "Length 0.6: int(length) samples = 0, views cleared."),
            ("roi_image_edge",          ("0", "0", "0", "31", "0", "0"),     "ROI along the first image row, ending exactly at x = w - 1."),
        ]

        scenarios = []
        for name, fields, description in cases:
            scenarios.append({
                "name"        : name,
                "description" : description,
                "steps"       : [self.load("hd5", "fusar_two_key_elev.hd5"), self.roi(*fields), self.click("tab1PlotButton"), self.step("metadata")],
            })
        return scenarios

    def channels(self) -> list[dict]:
        """Scenarios for the Data > Channel menu on multi-channel cubes.

        Returns:
            Scenario list.
        """

        modes = [
            self.load("npy", "npy_channels_3.npy"),
            self.roi(*self.OBLIQUE),
            self.step("channel", mode="Red"),
            self.step("channel", mode="Green"),
            self.step("channel", mode="Blue"),
            self.step("channel", mode="RGB"),
            self.click("tab1PlotButton"),
            self.step("channel", mode="Green"),
            self.click("tab1PlotButton"),
            self.step("metadata"),
        ]

        return [
            {
                "name"        : "channels_3_modes_as_is",
                "description" : "Three channels exactly as the original runs on pyqtgraph 0.14: every RGB setLevels raises, the RGB tomogram is never computed and the RGB Plot fails.",
                "steps"       : modes,
            },
            {
                "name"        : "channels_3_modes",
                "description" : "Three channels with the RGB levels shim: RGB, Red, Green, Blue and back to RGB with an oblique ROI; RGB Plot; a channel change clears the Plot tab; mono Plot of Green.",
                "rgb_levels"  : "rgba_mode",
                "steps"       : modes,
            },
            {
                "name"        : "channels_2_modes",
                "description" : "Two channels with the RGB levels shim: Blue is disabled; RGB tomogram gets a third plane of ones in the view and zeros in the Plot.",
                "rgb_levels"  : "rgba_mode",
                "steps"       : [
                    self.load("npy", "npy_channels_2.npy"),
                    self.roi(*self.OBLIQUE),
                    self.step("channel", mode="Red"),
                    self.step("channel", mode="Green"),
                    self.step("channel", mode="Blue"),
                    self.step("channel", mode="RGB"),
                    self.click("tab1PlotButton"),
                ],
            },
            {
                "name"        : "channels_4_after_crash",
                "description" : "Four channels after the load-time IndexError: channel actions keep failing in displayData.",
                "steps"       : [
                    self.load("npy", "npy_channels_4.npy"),
                    self.step("channel", mode="Red"),
                    self.step("channel", mode="RGB"),
                ],
            },
            {
                "name"        : "channels_covariance_5d",
                "description" : "5-D covariance cube with the RGB levels shim: three channels from the matrix diagonal, Red and RGB, RGB Plot.",
                "rgb_levels"  : "rgba_mode",
                "steps"       : [
                    self.load("npy", "npy_covariance_5d.npy"),
                    self.roi("1", "1", "20", "14", "0", "0"),
                    self.step("channel", mode="Red"),
                    self.step("channel", mode="RGB"),
                    self.click("tab1PlotButton"),
                ],
            },
            {
                "name"        : "channels_slice_mode",
                "description" : "Three channels in slice mode with the RGB levels shim: RGB slice, Red slice, back to RGB, RGB Plot, slice mode off.",
                "rgb_levels"  : "rgba_mode",
                "steps"       : [
                    self.load("npy", "npy_channels_3.npy"),
                    self.check("tab1ChkBox", True),
                    self.value("tab1SpinBox", 3),
                    self.step("channel", mode="Red"),
                    self.step("channel", mode="RGB"),
                    self.click("tab1PlotButton"),
                    self.check("tab1ChkBox", False),
                ],
            },
        ]

    def slices(self) -> list[dict]:
        """Scenarios for the automatic slice controls.

        Returns:
            Scenario list.
        """

        return [
            {
                "name"        : "slice_mode",
                "description" : "Slice checkbox, spin box at both ends, slider drag, play, three timer ticks, stop, slice mode off.",
                "steps"       : [
                    self.load("npy", "npy_real.npy"),
                    self.check("tab1ChkBox", True),
                    self.value("tab1SpinBox", 0),
                    self.value("tab1SpinBox", 23),
                    self.value("tab1Slider", 5),
                    self.click("tab1PlayButton"),
                    self.step("tick", count=3),
                    self.click("tab1PlayButton"),
                    self.check("tab1ChkBox", False),
                ],
            },
            {
                "name"        : "slice_play_wrap",
                "description" : "Play from the second to last slice: the timer wraps to the slider minimum.",
                "steps"       : [
                    self.load("npy", "npy_real.npy"),
                    self.check("tab1ChkBox", True),
                    self.value("tab1SpinBox", 22),
                    self.click("tab1PlayButton"),
                    self.step("tick", count=3),
                    self.click("tab1PlayButton"),
                ],
            },
            {
                "name"           : "slice_mode_plot",
                "description"    : "Slice 7 of a cube with x_res 0.5 plotted: x axis Azimuth from 0 to (nx - 1) * x_res.",
                "commit_figures" : True,
                "steps"          : [
                    self.load("hd5", "fusar_two_key_elev.hd5"),
                    self.check("tab1ChkBox", True),
                    self.value("tab1SpinBox", 7),
                    self.click("tab1PlotButton"),
                    self.step("metadata"),
                ],
            },
        ]

    def colormaps(self) -> list[dict]:
        """Scenario stepping the Slicer colormap combo box through every colortable.

        Returns:
            Scenario list.
        """

        steps = [self.load("hd5", "fusar_two_key_elev.hd5"), self.roi(*self.OBLIQUE)]
        for index in range(19):
            steps.append(self.step("combo", widget="tab1ComboBox", index=index))
        steps.append(self.check("tab1ChkBox", True))
        steps.append(self.step("combo", widget="tab1ComboBox", index=4))
        steps.append(self.step("combo", widget="tab1ComboBox", index=9))
        return [{"name": "tab1_colormaps", "description": "Every Slicer colortable in ROI mode (levels factor 5.0 for index 4, 2.5 otherwise), then index 4 and 9 in slice mode.", "steps": steps}]

    def plots(self) -> list[dict]:
        """Scenarios for the Plot and Profile tabs.

        Returns:
            Scenario list.
        """

        mono = [self.load("hd5", "fusar_two_key_elev.hd5"), self.roi(*self.OBLIQUE), self.click("tab1PlotButton")]
        rgb  = [self.load("npy", "npy_channels_3.npy"), self.roi(*self.OBLIQUE), self.click("tab1PlotButton")]

        return [
            {
                "name"        : "plot_controls",
                "description" : "Full View, Normalize, histogram equalization at 2, 3, 10 and 25 bins, colormap change and Clear.",
                "steps"       : mono + [
                    self.check("tab2ChkBox4", True),
                    self.check("tab2ChkBox1", True),
                    self.check("tab2ChkBox2", True),
                    self.value("tab2Slider", 3),
                    self.value("tab2Slider", 10),
                    self.value("tab2Slider", 25),
                    self.check("tab2ChkBox1", False),
                    self.check("tab2ChkBox2", False),
                    self.step("combo", widget="tab2ComboBox", text="viridis"),
                    self.check("tab2ChkBox4", False),
                    self.click("tab2ClearButton"),
                ],
            },
            {
                "name"           : "plot_xline_profile",
                "commit_figures" : True,
                "description"    : "X line, its spin box, Profile plot, Normalize after profiling, re-profile, Axes dialog applied to both figures, X line off and both Clear buttons.",
                "steps"          : mono + [
                    self.check("tab2ChkBox3", True),
                    self.value("tab2SpinBox", 7.333),
                    self.click("tab2PlotButton"),
                    self.check("tab2ChkBox1", True),
                    self.click("tab2PlotButton"),
                    self.step("axes", values=self.AXES),
                    self.value("tab2SpinBox", 100.0),
                    self.click("tab2PlotButton"),
                    self.step("metadata"),
                    self.check("tab2ChkBox3", False),
                    self.click("tab3ClearButton"),
                    self.click("tab2ClearButton"),
                ],
            },
            {
                "name"        : "plot_axes_dialog",
                "description" : "Axes dialog: Cancel, X min >= X max warning, Z min >= Z max warning, empty labels fall back to x and z.",
                "steps"       : mono + [
                    self.step("axes", values={"x_label": "ignored", "x_min": 1.0, "x_max": 2.0}, accept=False),
                    self.step("axes", values={"x_min": 5.0, "x_max": 5.0}),
                    self.step("axes", values={"z_min": 3.0, "z_max": -3.0}),
                    self.step("axes", values={"x_label": "  ", "z_label": "", "x_min": -1.123456789, "x_max": 3.5, "z_min": -7.0, "z_max": 9.0}),
                ],
            },
            {
                "name"        : "plot_hist_eq_then_xline",
                "description" : "Histogram equalization at 7 bins, then the X line disables the equalization checkbox so the plot falls back to the raw tomogram.",
                "steps"       : mono + [
                    self.check("tab2ChkBox2", True),
                    self.value("tab2Slider", 7),
                    self.check("tab2ChkBox3", True),
                    self.click("tab2PlotButton"),
                    self.check("tab2ChkBox3", False),
                ],
            },
            {
                "name"           : "plot_rgb",
                "description"    : "RGB Plot with the RGB levels shim: colormap and Plot disabled, Normalize, equalization at 4 bins, X line (enabled since startup), RGB Profile, Axes dialog, Clear.",
                "rgb_levels"     : "rgba_mode",
                "commit_figures" : True,
                "steps"          : rgb + [
                    self.check("tab2ChkBox1", True),
                    self.check("tab2ChkBox2", True),
                    self.value("tab2Slider", 4),
                    self.check("tab2ChkBox2", False),
                    self.check("tab2ChkBox3", True),
                    self.click("tab2PlotButton"),
                    self.step("axes", values=self.AXES),
                    self.click("tab2ClearButton"),
                ],
            },
            {
                "name"        : "plot_rgb_two_channels",
                "description" : "Two-channel RGB Plot and Profile with the RGB levels shim (combined panel at subplot 223).",
                "rgb_levels"  : "rgba_mode",
                "steps"       : [self.load("npy", "npy_channels_2.npy"), self.roi(*self.OBLIQUE), self.click("tab1PlotButton"), self.check("tab2ChkBox3", True), self.click("tab2PlotButton")],
            },
            {
                "name"        : "plot_rgb_after_channel_change",
                "description" : "RGB Plot reached after Red then RGB with the RGB levels shim: chChanged re-enabled the X line checkbox.",
                "rgb_levels"  : "rgba_mode",
                "steps"       : [self.load("npy", "npy_channels_3.npy"), self.roi(*self.OBLIQUE), self.step("channel", mode="Red"), self.step("channel", mode="RGB"), self.click("tab1PlotButton"), self.check("tab2ChkBox3", True), self.value("tab2SpinBox", 3.0), self.click("tab2PlotButton")],
            },
        ]

    def sessions(self) -> list[dict]:
        """Scenarios for File > Save and File > Open.

        Returns:
            Scenario list.
        """

        mono_profile = f"{self.SESSIONS}/mono_profile"
        green_plot   = f"{self.SESSIONS}/green_plot.hd5"
        rgb_profile  = f"{self.SESSIONS}/rgb_profile.hd5"
        slice_mode   = f"{self.SESSIONS}/slice_mode.hd5"

        return [
            {
                "name"        : "session_mono_profile",
                "description" : "Single channel with Normalize, Full View, X line and Profile saved (extension appended), read back, then opened in a fresh window.",
                "steps"       : [
                    self.load("hd5", "fusar_two_key_elev.hd5"),
                    self.roi(*self.OBLIQUE),
                    self.click("tab1PlotButton"),
                    self.check("tab2ChkBox1", True),
                    self.check("tab2ChkBox4", True),
                    self.check("tab2ChkBox3", True),
                    self.value("tab2SpinBox", 6.5),
                    self.click("tab2PlotButton"),
                    self.step("save", path=mono_profile),
                    self.step("read_session", path=f"{mono_profile}.hd5"),
                    self.step("fresh_window"),
                    self.step("open", path=f"{mono_profile}.hd5"),
                    self.step("tab", index=1),
                    self.step("tab", index=2),
                    self.step("metadata"),
                ],
            },
            {
                "name"        : "session_green_plot",
                "description" : "Three channels in Green with a Plot saved and reopened (channel restored by applyMetadata), RGB levels shim on.",
                "rgb_levels"  : "rgba_mode",
                "steps"       : [
                    self.load("npy", "npy_channels_3.npy"),
                    self.roi(*self.OBLIQUE),
                    self.step("channel", mode="Green"),
                    self.click("tab1PlotButton"),
                    self.step("combo", widget="tab2ComboBox", text="magma"),
                    self.step("save", path=green_plot),
                    self.step("read_session", path=green_plot),
                    self.step("fresh_window"),
                    self.step("open", path=green_plot),
                    self.step("tab", index=1),
                    self.step("tab", index=2),
                    self.step("metadata"),
                ],
            },
            {
                "name"        : "session_rgb_profile",
                "description" : "Three channels in RGB with Plot, X line and Profile saved and reopened, RGB levels shim on.",
                "rgb_levels"  : "rgba_mode",
                "steps"       : [
                    self.load("npy", "npy_channels_3.npy"),
                    self.roi(*self.OBLIQUE),
                    self.click("tab1PlotButton"),
                    self.check("tab2ChkBox3", True),
                    self.click("tab2PlotButton"),
                    self.step("save", path=rgb_profile),
                    self.step("read_session", path=rgb_profile),
                    self.step("fresh_window"),
                    self.step("open", path=rgb_profile),
                    self.step("tab", index=1),
                    self.step("tab", index=2),
                ],
            },
            {
                "name"        : "session_slice_mode",
                "description" : "Slice mode at slice 9 with colortable 4 and an Axes change saved and reopened; then opened again over the loaded data.",
                "steps"       : [
                    self.load("hd5", "fusar_one_key_range.hd5"),
                    self.step("combo", widget="tab1ComboBox", index=4),
                    self.check("tab1ChkBox", True),
                    self.value("tab1SpinBox", 9),
                    self.click("tab1PlotButton"),
                    self.step("axes", values=self.AXES),
                    self.step("save", path=slice_mode),
                    self.step("read_session", path=slice_mode),
                    self.step("fresh_window"),
                    self.step("open", path=slice_mode),
                    self.step("tab", index=1),
                    self.step("tab", index=2),
                    self.step("open", path=slice_mode),
                ],
            },
            {
                "name"        : "session_errors",
                "description" : "Save cancelled, Save into a missing directory, Open cancelled, Open of an .hd5 without a data dataset, Open of a FuSAR file (no metadata group).",
                "steps"       : [
                    self.load("npy", "npy_real.npy"),
                    self.step("save", path=None),
                    self.step("save", path="<fixtures>/missing_directory/x.hd5"),
                    self.step("open", path=None),
                    self.step("open", path=f"{self.INPUTS}/fusar_one_key_range.hd5"),
                    self.step("open", path=f"{self.SESSIONS}/no_metadata.hd5"),
                ],
            },
        ]

    def volumes(self) -> list[dict]:
        """Scenarios for the 3D tab (vispy state; pixels need PyOpenGL, which the tomovis env lacks).

        Returns:
            Scenario list.
        """

        return [
            {
                "name"        : "volume_single",
                "description" : "3D tab on a single-channel cube: equalized subsampled volume, projections, ISO threshold, colormap cycling, cameras, reset and channel buttons.",
                "steps"       : [
                    self.load("hd5", "fusar_two_key_elev.hd5"),
                    self.step("tab", index=3),
                    self.step("projection", name="iso"),
                    self.step("iso", value=50),
                    self.step("projection", name="translucent"),
                    self.click("colormapTab4Button"),
                    self.click("colormapTab4Button"),
                    self.step("projection", name="additive"),
                    self.step("projection", name="mip"),
                    self.click("colormapTab4Button"),
                    self.step("camera", name="Fly"),
                    self.step("camera", name="Arcball"),
                    self.step("camera", name="Turntable"),
                    self.click("resetCamerasTab4Button"),
                    self.click("channelTab4Button"),
                    self.step("layout"),
                ],
            },
            {
                "name"        : "volume_channels_3",
                "description" : "3D tab on a three-channel cube: [::8, ::8, ::2] keeps channel 0 only and renderVolume splits the last (range) axis into visuals. RGB levels shim on.",
                "rgb_levels"  : "rgba_mode",
                "steps"       : [
                    self.load("npy", "npy_channels_3.npy"),
                    self.step("tab", index=3),
                    self.click("channelTab4Button"),
                    self.click("channelTab4Button"),
                ],
            },
            {
                "name"        : "volume_reload",
                "description" : "Importing new data after the 3D tab was built: a second canvas is added to the same layout cell.",
                "steps"       : [
                    self.load("npy", "npy_real.npy"),
                    self.step("tab", index=3),
                    self.step("tab", index=0),
                    self.load("hd5", "fusar_one_key_range.hd5"),
                    self.step("tab", index=3),
                    self.step("layout"),
                ],
            },
        ]

    def all(self) -> list[dict]:
        """Returns every scenario in catalogue order.

        Returns:
            Scenario list.
        """

        return self.startup() + self.imports() + self.rois() + self.channels() + self.slices() + self.colormaps() + self.plots() + self.sessions() + self.volumes()



class TableWriter:
    """Writes the static look-up material TomoVis renders with.

    Attributes:
        root    : Fixture root; tables go to ``tables/``.
        session : TomoVisSession giving access to the original modules.
    """

    def __init__(self, root: Path, session) -> None:
        """Stores the destination and the session.

        Args:
            root    : Fixture root directory.
            session : TomoVisSession with the original modules imported.
        """

        self.root    = root
        self.session = session
        (root / "tables").mkdir(parents=True, exist_ok=True)

    def colortables(self) -> tuple[list[str], np.ndarray, np.ndarray]:
        """Reads the TomoVis colortables and the LUTs pyqtgraph builds from them.

        Returns:
            (names, tables, luts): colortable names; uint8 (n, 256, 3) tables; uint8 (n, 256, k) LUTs from the ImageView gradient.
        """

        module        = self.session.module
        names, tables = module.colortables()
        view          = module.pg.ImageView()
        luts          = []

        for index in range(len(names)):
            view.setColorMap(module.pg.ColorMap(np.linspace(0.0, 1.0, 256), module.colortables(index)[1]))
            luts.append(np.asarray(view.ui.histogram.getLookupTable(img=np.zeros((2, 2), dtype=np.float32), n=256)))
        view.close()
        return list(names), np.asarray(tables, dtype=np.uint8), np.asarray(luts, dtype=np.uint8)

    def vispy_colormaps(self) -> tuple[list[str], np.ndarray, list[dict]]:
        """Samples every vispy colormap the 3D tab cycles through, as vispy's own indexing does.

        Returns:
            (names, samples, unmappable): names in get_colormaps() order; float32 (n, 256, 4) RGBA samples at 256 evenly spaced positions in [0, 1] (NaN rows for unmappable ones); name and error of each colormap that has no Python mapping.
        """

        names      = list(self.session.vispy_maps.keys())
        samples    = np.full((len(names), 256, 4), np.nan, dtype=np.float32)
        unmappable = []
        positions  = np.linspace(0.0, 1.0, 256)

        for index, name in enumerate(names):
            try:
                samples[index] = np.asarray(self.session.vispy_maps[name][positions].rgba, dtype=np.float32)
            except (NotImplementedError, ValueError, TypeError) as error:
                unmappable.append({"name": name, "error": f"{type(error).__name__}: {error}"})
        return names, samples, unmappable

    def translucent_glsl(self) -> list[dict]:
        """Reads the GLSL of the two translucent colormaps from a fresh Volume.

        Returns:
            Class name and GLSL source of each translucent colormap in cycle order.
        """

        volume  = self.session.module.Volume()
        entries = [volume.translucentCmap, next(volume.translucentCmaps)]
        records = [{"class": type(entry).__name__, "glsl": type(entry).glsl_map} for entry in entries]
        volume.canvas.close()
        return records

    def run(self) -> Path:
        """Writes ``tables/tables.npz`` and ``tables/tables.json``.

        Returns:
            Path of the JSON file.
        """

        names, tables, luts          = self.colortables()
        maps, samples, unmappable    = self.vispy_colormaps()
        module                       = self.session.module

        np.savez_compressed(self.root / "tables" / "tables.npz", colortables=tables, colortable_luts=luts, vispy_colormaps=samples)
        document = {
            "colortable_names"       : names,
            "colortable_default"     : 9,
            "colortable_lut_shape"   : list(luts.shape),
            "pyplot_cmaps"           : list(module.pyplotCmaps),
            "pyplot_cmap_default"    : "jet",
            "vispy_colormaps"        : maps,
            "vispy_unmappable"       : unmappable,
            "vispy_translucent"      : self.translucent_glsl(),
            "versions"               : {"numpy": np.__version__, "matplotlib": matplotlib.__version__, "pyqtgraph": module.pg.__version__, "vispy": vispy.__version__},
        }
        path = self.root / "tables" / "tables.json"
        path.write_text(json.dumps(document, indent=1) + "\n")
        return path


class GoldenRunner:
    """Plays ScenarioBook scenarios in fresh windows and writes their goldens.

    Attributes:
        session : TomoVisSession driving the original window.
        writer  : GoldenWriter storing the results.
        root    : Fixture root resolving the ``<fixtures>`` placeholder.
        logger  : WebLogger for progress lines.
    """

    def __init__(self, session, writer: GoldenWriter, root: Path, logger) -> None:
        """Stores collaborators.

        Args:
            session : TomoVisSession driving the original window.
            writer  : GoldenWriter storing the results.
            root    : Fixture root directory.
            logger  : WebLogger for progress lines.
        """

        self.session = session
        self.writer  = writer
        self.root    = root
        self.logger  = logger

    def resolve(self, value):
        """Replaces ``<fixtures>`` by the fixture root in argument strings.

        Args:
            value : Argument value.

        Returns:
            The value with absolute paths.
        """

        if isinstance(value, str):
            return value.replace("<fixtures>", str(self.root))
        if isinstance(value, dict):
            return {key: self.resolve(item) for key, item in value.items()}
        if isinstance(value, list):
            return [self.resolve(item) for item in value]
        return value

    def prepare_sessions(self) -> None:
        """Creates the sessions directory and the .hd5 without metadata used by session_errors."""

        directory = self.root / "sessions"
        directory.mkdir(parents=True, exist_ok=True)
        with h5py.File(directory / "no_metadata.hd5", "w") as h5f:
            h5f.create_dataset("data", data=np.load(self.root / "inputs" / "npy_float64.npy"))

    def play(self, scenario: dict) -> int:
        """Plays one scenario and writes its goldens.

        Args:
            scenario : Scenario entry from ScenarioBook.

        Returns:
            Number of slot exceptions seen during the scenario.
        """

        shims = ["rgb_levels_rgba_mode"] if scenario.get("rgb_levels") == "rgba_mode" else []
        self.session.levels_shim.enabled = bool(shims)
        self.session.open_window()
        self.writer.start(scenario, shims)
        errors = 0

        state, arrays, figures = self.session.probe.capture(self.session.window)
        self.writer.step(0, "open_window", {}, {"result": {}, "events": [], "stdout": [], "errors": []}, state, arrays, figures)

        for index, step in enumerate(scenario["steps"], start=1):
            outcome                 = self.session.perform(step["action"], self.resolve(step["args"]))
            state, arrays, figures  = self.session.probe.capture(self.session.window)
            errors                 += len(outcome["errors"])
            arrays.update(self.session.volume_arrays())
            self.writer.step(index, step["action"], step["args"], outcome, state, arrays, figures)

        self.writer.finish(self.session.size)
        self.session.close_window()
        self.session.levels_shim.enabled = False
        return errors

    def run(self, scenarios: list[dict]) -> dict:
        """Plays every scenario.

        Args:
            scenarios : Scenario entries to play.

        Returns:
            Scenario name to its number of slot exceptions.
        """

        self.prepare_sessions()
        summary = {}
        for scenario in scenarios:
            summary[scenario["name"]] = self.play(scenario)
            self.logger.info(f"golden {scenario['name']}: {len(scenario['steps'])} steps, {summary[scenario['name']]} slot exceptions")
        return summary
