"""Tests of TomoVis window events the parity goldens do not drive: ROI drags, shortcuts, field validation and crash fixes."""

from __future__ import annotations

import pytest

from tests.webui.test_tomovis_goldens import GoldenReplay
from tomovis.events                   import TomoVisEventError


@pytest.fixture
def loaded(tmp_path) -> GoldenReplay:
    """A window with the two-key FuSAR cube imported."""

    replay = GoldenReplay(tmp_path)
    replay.perform("import", {"kind": "hd5", "path": "<fixtures>/inputs/fusar_two_key_elev.hd5"})
    return replay


def drag_state(window, dx: float, dy: float) -> dict:
    """The pyqtgraph state after translating the ROI by (dx, dy), as the browser sends it."""

    roi = window.roi_1
    pos = roi.state["pos"]
    return {"pos": [pos.x() + dx, pos.y() + dy], "size": [1.0, 1.0], "angle": 0.0, "handles": [{"pos": [info["pos"][0], info["pos"][1]], "item": [info["item"].pos().x(), info["item"].pos().y()]} for info in roi.handles]}


def test_roi_drag_updates_the_fields_and_the_tomogram(loaded):
    """A body drag moves the origin; region-changed reruns the extraction and rewrites the six fields (S-2)."""

    window = loaded.window
    before = window.d2.copy()
    loaded.send({"type": "roi", "state": drag_state(window, 2.0, 1.0), "free_handle_moved": False, "finish": False})

    assert [window.tab1QLineEdit1.text(), window.tab1QLineEdit2.text(), window.tab1QLineEdit5.text(), window.tab1QLineEdit6.text()] == ["2.0000", "1.0000", "2.0000", "1.0000"]
    assert window.d2.shape != before.shape or (window.d2 != before).any()
    assert loaded.slot_errors == []


def test_roi_drag_in_slice_mode_leaves_the_tomogram(loaded):
    """In slice mode the ROI no longer drives the tomogram; only the fields follow it (F-042)."""

    window = loaded.window
    loaded.send({"type": "check", "widget": "tab1ChkBox", "checked": True})
    before = window.d2.copy()
    loaded.send({"type": "roi", "state": drag_state(window, 3.0, 0.0), "free_handle_moved": False, "finish": True})

    assert window.tab1QLineEdit5.text() == "3.0000"
    assert (window.d2 == before).all()


def test_free_handle_move_alone_emits_region_changed(loaded):
    """Moving a free handle without changing the state still runs the slots (freeHandleMoved)."""

    window = loaded.window
    state  = drag_state(window, 0.0, 0.0)
    state["handles"][1]["pos"] = [10.0, 10.0]
    state["handles"][1]["item"] = [10.0, 10.0]
    loaded.send({"type": "roi", "state": state, "free_handle_moved": True, "finish": True})

    assert window.tab1QLineEdit4.text() == "14.1421"


def test_ctrl_s_does_nothing_before_data_and_saves_after(tmp_path):
    """F-004: Ctrl+S is inert while Save is disabled; with data it opens the Save File dialog."""

    replay = GoldenReplay(tmp_path)
    replay.send({"type": "shortcut", "keys": "Ctrl+S"})

    assert replay.dialogs == []

    replay.perform("import", {"kind": "npy", "path": "<fixtures>/inputs/npy_real.npy"})
    replay.dialogs = []
    replay.send({"type": "shortcut", "keys": "Ctrl+S"})

    assert (replay.dialogs[0]["kind"], replay.dialogs[0]["mode"], replay.dialogs[0]["title"], replay.dialogs[0]["filters"]) == ("file", "save", "Save File", ["Visualizer (*.hd5)"])


def test_ctrl_f_on_single_channel_data_clears_the_plot_tab(loaded):
    """F-007: Ctrl+F works with the Channel menu disabled: back to Slicer, Plot and Profile cleared."""

    window = loaded.window
    loaded.send({"type": "click", "widget": "tab1PlotButton"})

    assert window.tab2_plotted and window.tabWidget.currentIndex() == 1
    assert not window.ChMenu.isEnabled()

    loaded.send({"type": "shortcut", "keys": "Ctrl+F"})

    assert window.tabWidget.currentIndex() == 0
    assert not window.tab2_plotted and not window.tab2ClearButton.isEnabled()
    assert window.tab2ChkBox3.isEnabled()


def test_ctrl_f_without_data_does_not_crash(tmp_path):
    """E-007: on an empty window Ctrl+F applies the state changes before the display and stops there."""

    replay = GoldenReplay(tmp_path)
    replay.send({"type": "shortcut", "keys": "Ctrl+F"})

    assert replay.slot_errors == []
    assert replay.window.tab2ChkBox3.isEnabled()


def test_trigger_needs_every_parent_menu_enabled(loaded):
    """A menu click on an action inside the disabled Channel menu does nothing."""

    window = loaded.window
    loaded.send({"type": "click", "widget": "tab1PlotButton"})
    loaded.send({"type": "trigger", "widget": "allChMenu"})

    assert window.tabWidget.currentIndex() == 1 and window.tab2_plotted


def test_invalid_field_text_is_refused_and_set_ignores_a_lone_minus(loaded):
    """F-143: Invalid text never reaches the field; E-009: Set with '-' changes nothing."""

    window = loaded.window
    loaded.send({"type": "text", "widget": "tab1QLineEdit1", "text": "1.23456"})

    assert window.tab1QLineEdit1.text() == "0.0000"

    loaded.send({"type": "text", "widget": "tab1QLineEdit1", "text": "-"})
    loaded.send({"type": "click", "widget": "tab1SetButton"})

    assert window.tab1QLineEdit1.text() == "-"
    assert window.computeLinePar()[:4] == (0.0, 0.0, 50.0, 64.0)
    assert loaded.slot_errors == []


def test_roi_touching_the_image_at_one_point_clears_the_tomogram(loaded):
    """E-012: a line leaving the image at its corner clips to a point; the views clear without an exception."""

    loaded.perform("set_roi", {"ax": "0", "ay": "0", "angle": "225", "length": "10", "pos_x": "0", "pos_y": "0"})

    assert loaded.slot_errors == []
    assert loaded.window.d2 is None
    assert not loaded.window.imv2_1.snapshot()["has_image"]


def test_ticks_advance_only_while_playing(loaded):
    """Ticks are ignored while the timer is stopped; Play advances one slice per tick and wraps (F-046)."""

    window = loaded.window
    loaded.send({"type": "tick"})

    assert window.tab1Slider.value() == 12

    loaded.send({"type": "check", "widget": "tab1ChkBox", "checked": True})
    loaded.send({"type": "value", "widget": "tab1SpinBox", "value": 22})
    loaded.send({"type": "click", "widget": "tab1PlayButton"})
    values = []
    for _ in range(3):
        loaded.send({"type": "tick"})
        values.append(window.tab1Slider.value())

    assert values == [23, 0, 1]
    assert window.events.controls()["tab1Timer"] == {"active": True, "interval": 500}


@pytest.mark.parametrize("event", [
    {"type": "value", "widget": "tab1Slider", "value": 1.5},
    {"type": "value", "widget": "tab1Slider", "value": True},
    {"type": "index", "widget": "tab1ComboBox", "index": 40},
    {"type": "tab", "index": 9},
    {"type": "check", "widget": "tab1ChkBox"},
    {"type": "roi", "state": {"pos": [0, 0]}, "free_handle_moved": False, "finish": True},
    {"type": "shortcut", "keys": "Ctrl+Q"},
    "not an object",
])
def test_invalid_events_are_rejected(loaded, event):
    """Events with unknown widgets, wrong types or out-of-range values raise a 400 error."""

    with pytest.raises(TomoVisEventError) as error:
        loaded.window.handle(event)

    assert error.value.status == 400
