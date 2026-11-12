"""Tests of the server halves of TomoVis's standalone scripts on the fixture files."""

from __future__ import annotations

import h5py
import numpy as np
import pytest

from tests.webui.conftest import REPO_ROOT
from tomovis.scripts       import SlicerMatplotlibScript, VolumeRenderingScript
from tomovis.window        import TomoVisConsole
from web_logger            import WebLogger

INPUTS = REPO_ROOT / "tests" / "webui" / "fixtures" / "tomovis" / "inputs"


@pytest.fixture
def slicer():
    """The SlicerMatplotlib figure on the one-key FuSAR file (range 0..45)."""

    figure = SlicerMatplotlibScript(WebLogger("tomovis-test")).load(str(INPUTS / "fusar_one_key_range.hd5"))
    figure.handle("resize", {"width": 800, "height": 600, "dpr": 1})
    figure.drain("f:")
    return figure


def press(figure, key: str) -> None:
    """Sends one key press with the pointer over the axes."""

    figure.handle("mouse", {"event": {"type": "motion_notify", "x": 400, "y": 300, "button": 0, "buttons": 0, "modifiers": []}})
    figure.handle("key", {"event": {"type": "key_press", "key": "k" + key}})
    figure.handle("key", {"event": {"type": "key_release", "key": "k" + key}})


def test_slicer_normalises_every_column_of_every_slice(slicer):
    """The middle slice is shown with jet, extent [0, azimuth, range0, range1] and per-column [0, 1] values."""

    ax    = slicer.figure.axes[0]
    image = ax.get_images()[0]

    assert image.get_cmap().name == "jet"
    assert list(image.get_extent()) == [0, 32, 0.0, 45.0]
    assert ax.index == 12
    assert np.allclose(ax.volume.min(axis=0), 0.0) and np.allclose(ax.volume.max(axis=0), 1.0)
    assert (ax.get_xlabel(), ax.get_ylabel()) == ("x", "z [m]")
    assert list(ax.get_yticks()) == list(np.linspace(0.0, 45.0, 5))


def test_slicer_keys_step_through_the_slices(slicer):
    """k shows the next slice and j the previous one; k no longer toggles the log x scale."""

    ax = slicer.figure.axes[0]
    press(slicer, "k")
    press(slicer, "k")

    assert ax.index == 14
    assert np.array_equal(ax.get_images()[0].get_array(), ax.volume[..., 14])
    assert ax.get_xscale() == "linear"

    press(slicer, "j")

    assert ax.index == 13


def test_slicer_keeps_the_rest_of_the_default_keymap(slicer):
    """The script figure keeps matplotlib's default keymap: g toggles the grid."""

    press(slicer, "g")
    slicer.canvas.draw()

    assert any(line.get_visible() for line in slicer.figure.axes[0].xaxis.get_gridlines())


@pytest.mark.parametrize("key, message", [("f", "full_screen_toggle"), ("q", "close")])
def test_slicer_window_keys_reach_the_browser(slicer, key, message):
    """f asks for the figure window's full screen toggle and q closes it, as the pyplot window did; other keys send neither."""

    press(slicer, "g")
    quiet, _ = slicer.drain("f:")
    press(slicer, key)
    messages, _ = slicer.drain("f:")
    window      = [entry["type"] for entry in messages if entry["type"] in ("full_screen_toggle", "close")]

    assert [entry["type"] for entry in quiet if entry["type"] in ("full_screen_toggle", "close")] == []
    assert window == [message]


@pytest.mark.parametrize("name, message", [("fusar_no_attrs.hd5", "No attribute 'range'."), ("fusar_three_keys.hd5", "Invalid dataset")])
def test_slicer_reader_errors(name, message):
    """The script's own errors: no range attribute, no tomogram key among several."""

    with pytest.raises(ValueError, match=message.replace("(", r"\(").replace(".", r"\.")):
        SlicerMatplotlibScript(WebLogger("tomovis-test")).read(str(INPUTS / name))


def test_volume_rendering_prepares_both_volumes_and_prints():
    """Volume 1 is the min-max normalised magnitude, volume 2 its > 0.4 mask; the start-up lines are printed."""

    console = TomoVisConsole(WebLogger("tomovis-test"))
    loaded  = VolumeRenderingScript(console).load(str(INPUTS / "fusar_one_key_range.hd5"))
    volume  = loaded["volume_1"]
    with h5py.File(INPUTS / "fusar_one_key_range.hd5", "r") as h5f:
        raw = h5f["tomogram"][:].astype(np.float32)

    assert volume.dtype == np.float32 and volume.min() == 0.0 and volume.max() == 1.0
    assert np.array_equal(loaded["volume_2"], (volume > 0.4).astype(np.float32))
    assert loaded["z_range"] == [0.0, 45.0]
    assert console.drain() == ["HDF5 keys: ['tomogram']", "Original shape: (16, 32, 24)", f"Min / max: {float(raw.min())} {float(raw.max())}", "Volume 1 shape: (16, 32, 24)", "Volume 2 shape: (16, 32, 24)", "Vertical range: [ 0. 45.]"]
