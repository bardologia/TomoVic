"""Records vispy 0.17's camera, gizmo and key behavior inside the original TomoVis.

Runs in the tomovis conda environment against the unmodified TomoVis source,
under the offscreen Qt platform, and writes
``tests/webui/fixtures/tomovis_vispy/cameras.json``. The node suite
``tests/webui/tomovis_vispy_port_test.mjs`` replays the same scenarios on the
browser port (``tomovis_vispy.js``, ``tomovis_volume.js``) and compares every
recorded state.

Each scenario builds the real TomoVis window (or the VolumeRendering script
scene), opens the 3D tab and then drives the vispy canvas the way Qt does:
mouse presses, moves and releases through the canvas backend (the 10 ms move
throttle is bypassed so every scripted move arrives), wheel and key events
through the canvas emitters, the fly camera's timer by explicit ticks of a
fixed ``dt``, and the 3D tab's buttons and radios through their Qt widgets.
After each step the generator records every camera's state, the fly camera's
thrusters, the axis gizmo, the printed lines, and where a fixed set of volume
and gizmo points land in canvas pixels. vispy cannot draw 3D textures here
(PyOpenGL is missing), so the record is numeric; the draw-time
``updateAxisView`` hook is called explicitly before each record.

The bootstrap below is the only place that touches ``sys.path``: it adds the
TomoVis source root so ``Visualizer`` imports as in the desktop app, and
TomoVic's ``webui`` for the WebLogger.

Usage:
    /home/bard/miniconda3/envs/tomovis/bin/python webui/tools/tomovis_vispy_goldens.py
"""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import os
import sys
import types
from itertools import cycle
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]

os.environ["QT_QPA_PLATFORM"]  = "offscreen"
os.environ["QT_API"]           = "pyqt5"
os.environ["PYQTGRAPH_QT_LIB"] = "PyQt5"
os.environ["MPLBACKEND"]       = "Qt5Agg"
sys.dont_write_bytecode        = True

parser = argparse.ArgumentParser(description="Record vispy camera behavior inside the original TomoVis.")
parser.add_argument("--tomovis",  type=Path, default=REPO.parent / "tomovis",                                         help="TomoVis source root (holds Visualizer/)")
parser.add_argument("--goldens",  type=Path, default=REPO / "tests" / "webui" / "fixtures" / "tomovis" / "goldens",     help="parity goldens holding the volume inputs")
parser.add_argument("--out",      type=Path, default=REPO / "tests" / "webui" / "fixtures" / "tomovis_vispy" / "cameras.json", help="output JSON file")
options = parser.parse_args()

sys.path.insert(0, str(REPO / "webui"))
sys.path.insert(0, str(options.tomovis.resolve()))

import numpy as np
from PyQt5 import QtWidgets
from vispy import scene
from vispy.color import BaseColormap, get_colormaps
from vispy.util import keys
from web_logger import WebLogger

APP = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)


class VispyCallbackErrors:
    """Replaces vispy's callback error logger with one marker line per failing callback.

    vispy's EventEmitter catches every exception raised by a callback and logs
    it to stderr; the original app keeps running. The marker line printed here
    (``ERROR: Invoking <Class>.<method> for <EventClass>: <Type>: <message>``)
    lands in the recorded stdout, so the record shows which callback failed and
    the browser port can be checked against it. Failures of
    ``SceneCanvas.on_draw`` are left out: they come from this recording
    environment, whose vispy cannot upload 3D textures without PyOpenGL.
    """

    @staticmethod
    def handle(ignore_callback_errors, print_callback_errors, obj, cb_event=None, node=None) -> None:
        """Prints the marker line for the exception being handled."""

        error_type, error, _ = sys.exc_info()
        if cb_event is None:
            print(f"ERROR: Drawing node {node}: {error_type.__name__}: {error}")
            return
        cb, event = cb_event
        owner = type(cb.__self__).__name__ if hasattr(cb, "__self__") else ""
        name  = f"{owner}.{cb.__name__}" if owner else getattr(cb, "__name__", repr(cb))
        if name == "SceneCanvas.on_draw":
            return
        print(f"ERROR: Invoking {name} for {type(event).__name__}: {error_type.__name__}: {error}")

    @classmethod
    def install(cls) -> None:
        """Routes vispy's emitters to ``handle``."""

        import vispy.util.event

        vispy.util.event._handle_exception = cls.handle


VispyCallbackErrors.install()

from Visualizer import visualizer


class VispyStateRecorder:
    """Turns the live vispy objects of one scene into JSON-ready records.

    Attributes:
        POINTS      : Volume-space points mapped to canvas pixels in every record.
        AXIS_POINTS : Gizmo-space points mapped to canvas pixels in every record.
    """

    POINTS      = [[0.0, 0.0, 0.0], [-0.5, -0.5, -0.5], [11.5, 3.5, 1.5], [6.0, 2.0, 1.0], [12.0, 0.0, 2.0], [3.0, 4.0, 0.0]]
    AXIS_POINTS = [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]]

    @staticmethod
    def quaternion(q) -> list:
        """Returns [w, x, y, z]."""

        return [float(q.w), float(q.x), float(q.y), float(q.z)]

    @staticmethod
    def center(camera) -> dict:
        """Returns the camera centre and the Python type it is held in (list or tuple)."""

        raw = camera._center
        return {"value": [float(v) for v in camera.center], "kind": "none" if raw is None else type(raw).__name__}

    def camera(self, camera) -> dict:
        """Returns the state of one vispy camera."""

        record = {
            "name"          : camera.name,
            "scale_factor"  : None if camera._scale_factor is None else float(camera._scale_factor),
            "center"        : self.center(camera),
            "fov"           : float(camera.fov),
            "ranged"        : camera._xlim is not None,
            "has_default"   : camera._default_state is not None,
            "attached"      : camera._viewbox is not None,
        }
        if isinstance(camera, scene.cameras.TurntableCamera):
            record.update({"elevation": float(camera.elevation), "azimuth": float(camera.azimuth), "roll": float(camera.roll)})
        if isinstance(camera, scene.cameras.ArcballCamera):
            record["quaternion"] = self.quaternion(camera._quaternion)
        if isinstance(camera, scene.cameras.FlyCamera):
            record.update({
                "rotation1"     : self.quaternion(camera._rotation1),
                "rotation2"     : self.quaternion(camera._rotation2),
                "speed"         : [float(v) for v in camera._speed],
                "acc"           : [float(v) for v in camera._acc],
                "brake"         : [int(v) for v in camera._brake],
                "timer_running" : bool(camera._timer.running),
            })
        return record

    def mapped(self, node, points) -> list:
        """Returns ``points`` mapped from ``node``'s visual frame to canvas pixels, divided by w."""

        mapped = node.get_transform("visual", "canvas").map(np.asarray(points, dtype=float))
        return [[float(v) for v in (row[:3] / row[3])] for row in mapped]

    def scene_record(self, canvas, view, cameras, axis_view, axis_camera, axis, visual, printed) -> dict:
        """Returns the full record of one scene state."""

        return {
            "camera"      : view.camera.name,
            "canvas_size" : [int(v) for v in canvas.size],
            "view_size"   : [float(v) for v in view.size],
            "cameras"     : {camera.name: self.camera(camera) for camera in cameras + [axis_camera]},
            "axis"        : {"visible": bool(axis_view.visible), "pos": [float(v) for v in axis_view.pos], "size": [float(v) for v in axis_view.size]},
            "points"      : self.mapped(visual, self.POINTS),
            "axis_points" : self.mapped(axis, self.AXIS_POINTS),
            "printed"     : printed,
        }


class VispyEventDriver:
    """Delivers Qt-like mouse, wheel and key events to one vispy canvas.

    Attributes:
        canvas : vispy SceneCanvas being driven.
    """

    MODIFIERS = {"shift": keys.SHIFT, "control": keys.CONTROL, "alt": keys.ALT, "meta": keys.META}

    def __init__(self, canvas) -> None:
        """Stores the canvas.

        Args:
            canvas : vispy SceneCanvas.
        """

        self.canvas = canvas

    def modifiers(self, names) -> tuple:
        """Returns the vispy modifier keys for ``names``."""

        return tuple(self.MODIFIERS[name] for name in names)

    def key(self, name: str):
        """Returns the vispy key for a Qt key name (``W``, ``Backspace``, ``Space``, ``1``)."""

        named = {"Backspace": keys.BACKSPACE, "Space": keys.SPACE, "Up": keys.UP, "Down": keys.DOWN, "Left": keys.LEFT, "Right": keys.RIGHT, "F11": keys.F11, "Escape": keys.ESCAPE}
        return named[name] if name in named else keys.Key(name.upper())

    def apply(self, step: dict) -> None:
        """Delivers one scripted input step."""

        backend = self.canvas._backend
        op      = step["op"]
        mods    = self.modifiers(step.get("mods", []))
        if op == "press":
            backend._vispy_mouse_press(pos=step["pos"], button=step["button"], buttons=step["buttons"], modifiers=mods)
        elif op == "move":
            backend._last_time = 0.0
            backend._vispy_mouse_move(pos=step["pos"], buttons=step["buttons"], modifiers=mods)
        elif op == "release":
            backend._vispy_mouse_release(pos=step["pos"], button=step["button"], buttons=step["buttons"], modifiers=mods)
        elif op == "wheel":
            self.canvas.events.mouse_wheel(delta=step["delta"], pos=step["pos"], buttons=step.get("buttons", []), modifiers=mods)
        elif op in ("key_press", "key_release"):
            emitter = self.canvas.events.key_press if op == "key_press" else self.canvas.events.key_release
            emitter(key=self.key(step["key"]), text=step.get("text", ""), modifiers=mods)
        else:
            raise ValueError(f"unknown input op {op}")


class VispyTimerTicks:
    """Fires a fly camera's timer callback the way vispy's timer emitter does.

    vispy's EventEmitter catches an exception raised by a callback, logs it and
    keeps the timer running; the tick prints one marker line per failure so the
    record shows which ticks failed.

    Attributes:
        camera : vispy FlyCamera whose ``on_timer`` is fired.
    """

    def __init__(self, camera) -> None:
        """Stores the camera.

        Args:
            camera : vispy FlyCamera.
        """

        self.camera = camera

    def tick(self, dt: float, count: int) -> None:
        """Fires ``count`` timer events of interval ``dt`` seconds."""

        for _ in range(count):
            try:
                self.camera.on_timer(types.SimpleNamespace(dt=dt))
            except Exception as error:
                print(f"ERROR: Invoking FlyCamera.on_timer for TimerEvent: {type(error).__name__}: {error}")


class WindowScene:
    """The original TomoVis window with its 3D tab open on one volume.

    Attributes:
        window : visualizer.TomoVis instance.
        volume : The window's visualizer.Volume.
        driver : VispyEventDriver on the volume canvas.
    """

    def __init__(self, data: np.ndarray) -> None:
        """Loads ``data`` as the window's cube volume and opens the 3D tab.

        Args:
            data : Volume handed to ``renderVolume`` (the goldens' ``volume_input``), 3-D or 4-D float32.
        """

        self.window = visualizer.TomoVis()
        self.window.resize(1100, 880)
        self.window.show()
        APP.processEvents()

        self.window.data = np.zeros((16, 16, 16), dtype=np.float32)
        self.window.setDefaultElevRangeIfMissing()
        self.window.initializeVisualizerWithData()
        self.window.ensure3DLoaded = self.ensure3DLoaded(data)
        self.window.tabWidget.setCurrentIndex(self.window.tab3d_index)
        APP.processEvents()

        self.volume = self.window.volume
        self.driver = VispyEventDriver(self.volume.canvas)

    def ensure3DLoaded(self, data: np.ndarray):
        """Returns a stand-in for ``ensure3DLoaded`` that renders ``data`` exactly as the original's data half would."""

        window = self.window

        def load():
            window.volume = visualizer.Volume()
            if window.tab4Placeholder is not None:
                window.fourthTabWidgetLayout.removeWidget(window.tab4Placeholder)
                window.tab4Placeholder.deleteLater()
                window.tab4Placeholder = None
            window.fourthTabWidgetLayout.addWidget(window.volume.canvas.native, 0, 0, -1, 1)
            window.volume.renderVolume(data)
            window.isoThresholdTab4Slider.setMaximum(100)
            window.isoThresholdTab4Slider.setMinimum(1)
            window.isoThresholdTab4Slider.setValue(1)
            window.isoThresholdTab4Slider.setEnabled(True)
            window.volume_rendered = True

        return load

    def apply(self, step: dict) -> None:
        """Runs one scripted step on the window."""

        op = step["op"]
        if op == "camera":
            button = {"Turntable": self.window.turntableCameraTab4Button, "Fly": self.window.flyCameraTab4Button, "Arcball": self.window.arcballCameraTab4Button}[step["name"]]
            button.click()
        elif op == "reset_cameras":
            self.window.resetCamerasTab4Button.click()
        elif op == "timer":
            VispyTimerTicks(self.volume.flyCamera).tick(step["dt"], step["count"])
        elif op == "resize":
            self.volume.canvas.native.setFixedSize(*step["size"])
            APP.processEvents()
        else:
            self.driver.apply(step)

    def record(self, recorder: VispyStateRecorder, printed: list) -> dict:
        """Returns the scene record after calling the draw-time gizmo update."""

        volume = self.volume
        volume.updateAxisView()
        cameras = [volume.turntableCamera, volume.arcballCamera, volume.flyCamera]
        return recorder.scene_record(volume.canvas, volume.view, cameras, volume.axis_view, volume.axis_camera, volume.axis, volume.volumeVisual[0], printed)


class ScriptScene:
    """The VolumeRendering.py scene, built by the script's own statements.

    Attributes:
        canvas, view, vis_volume_1, vis_volume_2, fly_camera, turntable_camera, arcball_camera, axis_view, axis_camera, axis : The script's objects.
        center : Volume centre the script resets to.
        driver : VispyEventDriver on the canvas.
    """

    def __init__(self, volume_1: np.ndarray) -> None:
        """Builds the scene as the script does for ``volume_1``.

        Args:
            volume_1 : Min-max normalised float32 volume (z, y, x).
        """

        volume_2 = (volume_1 > 0.4).astype(np.float32)

        self.canvas = scene.SceneCanvas(keys="interactive", size=(1000, 800), show=True)
        grid        = self.canvas.central_widget.add_grid()
        self.view   = grid.add_view(row=0, col=0, border_color=None)

        self.vis_volume_1 = scene.visuals.Volume(volume_1, parent=self.view.scene, clim=(0.0, 1.0), threshold=0.5, relative_step_size=0.8)
        self.vis_volume_2 = scene.visuals.Volume(volume_2, parent=self.view.scene, clim=(0.0, 1.0), threshold=0.5, relative_step_size=0.8)
        self.vis_volume_2.visible = False

        fov = 60.0
        self.fly_camera       = scene.cameras.FlyCamera(parent=self.view.scene, fov=fov, name="Fly")
        self.turntable_camera = scene.cameras.TurntableCamera(parent=self.view.scene, fov=fov, name="Turntable")
        self.arcball_camera   = scene.cameras.ArcballCamera(parent=self.view.scene, fov=fov, name="Arcball")
        self.view.camera      = self.turntable_camera

        nz, ny, nx  = volume_1.shape
        self.center = (nx / 2, ny / 2, nz / 2)
        self.turntable_camera.center = self.center
        self.arcball_camera.center   = self.center
        self.turntable_camera.set_range()
        self.arcball_camera.set_range()

        self.axis_view             = scene.widgets.ViewBox(parent=self.canvas.scene)
        self.axis_view.interactive = False
        self.axis_view.bgcolor     = (0, 0, 0, 0)
        self.axis_camera           = scene.cameras.TurntableCamera(parent=self.axis_view.scene, fov=0.0, name="AxisCamera")
        self.axis_view.camera      = self.axis_camera
        self.axis_camera.set_range(x=(-1, 1), y=(-1, 1), z=(-1, 1))
        self.axis = scene.visuals.XYZAxis(parent=self.axis_view.scene)
        self.place_axis_view()
        self.update_axis_view()

        class TransFire(BaseColormap):
            glsl_map = """
            vec4 translucent_fire(float t) {
                return vec4(pow(t, 0.5), t, t*t, max(0, t*1.05 - 0.05));
            }
            """

        class TransGrays(BaseColormap):
            glsl_map = """
            vec4 translucent_grays(float t) {
                return vec4(t, t, t, t*0.05);
            }
            """

        self.opaque_colormaps      = cycle(get_colormaps())
        self.translucent_colormaps = cycle([TransFire(), TransGrays()])
        self.opaque_colormap       = next(self.opaque_colormaps)
        self.translucent_colormap  = next(self.translucent_colormaps)
        self.vis_volume_1.cmap     = self.opaque_colormap
        self.vis_volume_2.cmap     = self.opaque_colormap

        self.canvas.events.draw.connect(lambda event: self.update_axis_view())
        self.canvas.events.resize.connect(lambda event: self.place_axis_view())
        self.canvas.events.key_press.connect(self.on_key_press)
        APP.processEvents()
        self.driver = VispyEventDriver(self.canvas)

    def place_axis_view(self) -> None:
        """Copy of the script's ``place_axis_view``."""

        margin = 20
        size   = 120
        width, height = self.canvas.size
        self.axis_view.pos  = (width - size - margin, margin)
        self.axis_view.size = (size, size)

    def update_axis_view(self) -> None:
        """Copy of the script's ``update_axis_view``."""

        current_camera = self.view.camera
        if current_camera in (self.turntable_camera,):
            self.axis_view.visible = True
            if hasattr(current_camera, "elevation"):
                self.axis_camera.elevation = current_camera.elevation
            if hasattr(current_camera, "azimuth"):
                self.axis_camera.azimuth = current_camera.azimuth
            if hasattr(current_camera, "roll"):
                self.axis_camera.roll = current_camera.roll
        else:
            self.axis_view.visible = False

    def on_key_press(self, event) -> None:
        """Copy of the script's ``on_key_press``."""

        if event.text == "1":
            camera_toggle = {self.fly_camera: self.turntable_camera, self.turntable_camera: self.arcball_camera, self.arcball_camera: self.fly_camera}
            self.view.camera = camera_toggle.get(self.view.camera, self.turntable_camera)
            print(f"Camera: {self.view.camera.name}")
            self.update_axis_view()
        elif event.text == "2":
            methods = ["mip", "translucent", "iso", "additive"]
            method  = methods[(methods.index(self.vis_volume_1.method) + 1) % 4]
            print("Volume rendering method:", method)
            cmap = self.opaque_colormap if method in ["mip", "iso"] else self.translucent_colormap
            self.vis_volume_1.method = method
            self.vis_volume_2.method = method
            self.vis_volume_1.cmap   = cmap
            self.vis_volume_2.cmap   = cmap
        elif event.text == "3":
            self.vis_volume_1.visible = not self.vis_volume_1.visible
            self.vis_volume_2.visible = not self.vis_volume_1.visible
            print("Volume 1 visible:", self.vis_volume_1.visible, "| Volume 2 visible:", self.vis_volume_2.visible)
        elif event.text == "4":
            if self.vis_volume_1.method in ["mip", "iso"]:
                cmap = self.opaque_colormap = next(self.opaque_colormaps)
            else:
                cmap = self.translucent_colormap = next(self.translucent_colormaps)
            self.vis_volume_1.cmap = cmap
            self.vis_volume_2.cmap = cmap
            print("Colormap changed")
        elif event.text == "0":
            self.fly_camera.set_range()
            self.turntable_camera.set_range()
            self.arcball_camera.set_range()
            self.turntable_camera.center = self.center
            self.arcball_camera.center   = self.center
            self.update_axis_view()
            print("Cameras reset")
        elif event.text != "" and event.text in "[]":
            step = -0.025 if event.text == "[" else 0.025
            self.vis_volume_1.threshold += step
            self.vis_volume_2.threshold += step
            threshold = self.vis_volume_1.threshold if self.vis_volume_1.visible else self.vis_volume_2.threshold
            print(f"Isosurface threshold: {threshold:0.3f}")

    def apply(self, step: dict) -> None:
        """Runs one scripted step on the script scene."""

        if step["op"] == "timer":
            VispyTimerTicks(self.fly_camera).tick(step["dt"], step["count"])
        else:
            self.driver.apply(step)

    def cmap_name(self, cmap) -> str:
        """Returns the opaque colormap's name or the translucent class name."""

        return cmap if isinstance(cmap, str) else type(cmap).__name__

    def record(self, recorder: VispyStateRecorder, printed: list) -> dict:
        """Returns the scene record plus both visuals' method, colormap, threshold and visibility."""

        self.update_axis_view()
        cameras = [self.turntable_camera, self.arcball_camera, self.fly_camera]
        record  = recorder.scene_record(self.canvas, self.view, cameras, self.axis_view, self.axis_camera, self.axis, self.vis_volume_1, printed)
        record["visuals"] = [{"method": v.method, "threshold": float(v.threshold), "visible": bool(v.visible), "clim": [float(c) for c in v.clim]} for v in (self.vis_volume_1, self.vis_volume_2)]
        record["colormaps"] = {"opaque": self.cmap_name(self.opaque_colormap), "translucent": self.cmap_name(self.translucent_colormap)}
        return record


class VispyScenarioBook:
    """The scripted scenarios, as plain step lists shared with the node suite."""

    @staticmethod
    def drag(button: int, path: list, mods: list = ()) -> list:
        """Returns press, moves and release steps along ``path``."""

        mods  = list(mods)
        steps = [{"op": "press", "pos": path[0], "button": button, "buttons": [button], "mods": mods}]
        steps += [{"op": "move", "pos": pos, "buttons": [button], "mods": mods} for pos in path[1:]]
        steps.append({"op": "release", "pos": path[-1], "button": button, "buttons": [], "mods": mods})
        return steps

    @staticmethod
    def key(name: str, text: str = "", mods: list = ()) -> list:
        """Returns a key press and release."""

        return [{"op": "key_press", "key": name, "text": text, "mods": list(mods)}, {"op": "key_release", "key": name, "text": text, "mods": list(mods)}]

    def turntable(self) -> list:
        """Turntable orbit, zoom, wheel, translate, fov, ignored modifiers, Backspace, reset cameras and resize."""

        rec = {"op": "record"}
        return [
            rec,
            *self.drag(1, [[400, 300], [420, 310], [450, 330]]), rec,
            *self.drag(2, [[500, 400], [500, 380], [500, 350]]), rec,
            {"op": "wheel", "pos": [300, 300], "delta": [0, 1]}, rec,
            {"op": "wheel", "pos": [300, 300], "delta": [0, -2.5]}, rec,
            *self.drag(1, [[400, 300], [380, 320], [350, 340]], ["shift"]), rec,
            *self.drag(2, [[400, 300], [400, 280], [400, 270]], ["shift"]), rec,
            *self.drag(1, [[400, 300], [440, 300]], ["control"]), rec,
            *self.drag(3, [[400, 300], [440, 360]]), rec,
            *self.drag(1, [[100, 100], [100, 400], [100, 600]]), rec,
            *self.key("Backspace"), rec,
            {"op": "reset_cameras"}, rec,
            *self.drag(1, [[200, 200], [-300, 100]]), rec,
            {"op": "resize", "size": [700, 500]}, rec,
            {"op": "reset_cameras"}, rec,
        ]

    def arcball(self) -> list:
        """Arcball attach, incremental rotation, wheel, translate, zoom, Backspace and switching back and forth."""

        rec = {"op": "record"}
        return [
            {"op": "camera", "name": "Arcball"}, rec,
            *self.drag(1, [[462, 379], [470, 380], [490, 385], [520, 400], [600, 450]]), rec,
            *self.drag(1, [[100, 100], [900, 700]]), rec,
            {"op": "wheel", "pos": [300, 300], "delta": [0, 1.5]}, rec,
            *self.drag(1, [[400, 300], [380, 320], [350, 340]], ["shift"]), rec,
            *self.drag(2, [[500, 400], [500, 380], [500, 450]]), rec,
            *self.key("Backspace"), rec,
            {"op": "camera", "name": "Turntable"}, rec,
            {"op": "camera", "name": "Arcball"}, rec,
            {"op": "reset_cameras"}, rec,
        ]

    def fly(self) -> list:
        """Fly thrusters while detached and attached, mouse look, auto-roll, fov, wheel, brake, keys, Backspace."""

        rec = {"op": "record"}
        return [
            {"op": "key_press", "key": "W", "text": "w", "mods": []}, {"op": "timer", "dt": 0.01, "count": 5}, rec,
            {"op": "key_release", "key": "W", "text": "w", "mods": []}, {"op": "timer", "dt": 0.01, "count": 30}, rec,
            {"op": "camera", "name": "Fly"}, rec,
            {"op": "key_press", "key": "W", "text": "w", "mods": []}, {"op": "timer", "dt": 0.01, "count": 20},
            {"op": "key_release", "key": "W", "text": "w", "mods": []}, {"op": "timer", "dt": 0.012, "count": 20}, rec,
            {"op": "press", "pos": [400, 300], "button": 1, "buttons": [1], "mods": []},
            {"op": "move", "pos": [450, 320], "buttons": [1], "mods": []}, {"op": "timer", "dt": 0.01, "count": 1}, rec,
            {"op": "move", "pos": [520, 260], "buttons": [1], "mods": []}, {"op": "timer", "dt": 0.01, "count": 1}, rec,
            {"op": "release", "pos": [520, 260], "button": 1, "buttons": [], "mods": []}, rec,
            {"op": "timer", "dt": 0.01, "count": 40}, rec,
            *self.drag(2, [[400, 300], [400, 250]], ["control"]), {"op": "timer", "dt": 0.01, "count": 1}, rec,
            {"op": "wheel", "pos": [300, 300], "delta": [0, 1]}, {"op": "timer", "dt": 0.01, "count": 3}, rec,
            {"op": "wheel", "pos": [300, 300], "delta": [0, 2], "mods": ["shift"]}, rec,
            {"op": "key_press", "key": "Space", "text": " ", "mods": []}, {"op": "timer", "dt": 0.01, "count": 5},
            {"op": "key_release", "key": "Space", "text": " ", "mods": []}, rec,
            {"op": "key_press", "key": "I", "text": "i", "mods": []}, {"op": "key_press", "key": "J", "text": "j", "mods": []},
            {"op": "key_press", "key": "Q", "text": "q", "mods": []}, {"op": "key_press", "key": "D", "text": "d", "mods": []},
            {"op": "key_press", "key": "F", "text": "f", "mods": []}, {"op": "timer", "dt": 0.01, "count": 12},
            {"op": "key_release", "key": "I", "text": "i", "mods": []}, {"op": "key_release", "key": "J", "text": "j", "mods": []},
            {"op": "key_release", "key": "Q", "text": "q", "mods": []}, {"op": "key_release", "key": "D", "text": "d", "mods": []},
            {"op": "key_release", "key": "F", "text": "f", "mods": []}, {"op": "timer", "dt": 0.01, "count": 12}, rec,
            *self.key("Backspace"), rec,
            {"op": "reset_cameras"}, rec,
        ]

    def script(self) -> list:
        """The VolumeRendering keys: camera cycle, methods, volume toggle, colormaps, thresholds, reset."""

        rec = {"op": "record"}
        return [
            rec,
            *self.key("1", "1"), rec,
            *self.key("1", "1"), rec,
            *self.drag(1, [[400, 300], [450, 320]]), rec,
            *self.key("1", "1"), rec,
            *self.drag(1, [[400, 300], [480, 260]]), rec,
            *self.key("0", "0"), rec,
            *self.key("2", "2"), rec,
            *self.key("4", "4"), rec,
            *self.key("2", "2"), rec,
            *self.key("4", "4"), *self.key("4", "4"), rec,
            *self.key("3", "3"), rec,
            *self.key("[", "["), *self.key("[", "["), rec,
            *self.key("3", "3"), *self.key("]", "]"), rec,
            *self.key("2", "2"), *self.key("2", "2"), rec,
        ]


class VispyGoldenWriter:
    """Plays every scenario and writes the fixture.

    Attributes:
        goldens  : Parity goldens directory holding the volume inputs.
        out      : Output JSON path.
        logger   : WebLogger for progress lines.
        book     : VispyScenarioBook.
        recorder : VispyStateRecorder.
    """

    def __init__(self, goldens: Path, out: Path, logger: WebLogger) -> None:
        """Stores the paths and helpers.

        Args:
            goldens : Parity goldens directory.
            out     : Output JSON path.
            logger  : WebLogger for progress lines.
        """

        self.goldens  = goldens
        self.out      = out
        self.logger   = logger
        self.book     = VispyScenarioBook()
        self.recorder = VispyStateRecorder()

    def volume_input(self, scenario: str, key: str) -> np.ndarray:
        """Returns one ``volume_input`` array of the parity goldens."""

        return np.load(self.goldens / f"{scenario}.npz")[key]

    def script_volume(self) -> np.ndarray:
        """Returns a script-normalised volume built from the single-channel golden input."""

        volume = self.volume_input("volume_single", "s02_volume_input").astype(np.float32)
        vmin, vmax = float(volume.min()), float(volume.max())
        return (volume - vmin) / (vmax - vmin)

    def play(self, scene, steps: list) -> list:
        """Runs ``steps`` on ``scene`` and returns the records, each with the lines printed since the previous one."""

        records = []
        printed = io.StringIO()
        for step in steps:
            if step["op"] == "record":
                lines = [line for line in printed.getvalue().splitlines()]
                records.append(scene.record(self.recorder, lines))
                printed = io.StringIO()
                continue
            with contextlib.redirect_stdout(printed):
                scene.apply(step)
        return records

    def scenario(self, name: str, scene, steps: list, volume: np.ndarray, kind: str) -> dict:
        """Plays one scenario and returns its fixture entry."""

        records = self.play(scene, steps)
        self.logger.info(f"{name}: {len(steps)} steps, {len(records)} records")
        return {"name": name, "kind": kind, "volume_shape": list(volume.shape), "volume": [float(v) for v in volume.ravel()], "steps": steps, "records": records}

    def run(self) -> None:
        """Plays all scenarios and writes the JSON fixture."""

        single   = self.volume_input("volume_single", "s02_volume_input")
        channels = self.volume_input("volume_channels_3", "s02_volume_input")
        script   = self.script_volume()

        scenarios = [
            self.scenario("window_turntable", WindowScene(single), self.book.turntable(), single, "window"),
            self.scenario("window_arcball", WindowScene(single), self.book.arcball(), single, "window"),
            self.scenario("window_fly", WindowScene(single), self.book.fly(), single, "window"),
            self.scenario("window_channels", WindowScene(channels), [{"op": "record"}, {"op": "reset_cameras"}, {"op": "record"}], channels, "window"),
            self.scenario("script", ScriptScene(script), self.book.script(), script, "script"),
        ]
        document = {
            "generator" : "webui/tools/tomovis_vispy_goldens.py",
            "points"    : VispyStateRecorder.POINTS,
            "axis_points": VispyStateRecorder.AXIS_POINTS,
            "scenarios" : scenarios,
        }
        self.out.parent.mkdir(parents=True, exist_ok=True)
        self.out.write_text(json.dumps(document) + "\n")
        self.logger.info(f"wrote {self.out}")


if __name__ == "__main__":
    VispyGoldenWriter(options.goldens, options.out, WebLogger("tomovis_vispy")).run()
