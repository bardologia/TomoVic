"""Tests of the headless Qt stand-ins the copied TomoVis window runs on.

Covers the Qt semantics TomoVis depends on: emission only on change, signal
order, clamping and range adjustment, QDoubleSpinBox decimal rounding (the
values measured in the original), the ROI field validator states, exclusive
action groups, menu versus shortcut triggering, and the slot boundary that
reports an exception and carries on with the next slot.
"""

from __future__ import annotations

import pytest

from tomovis.qt_widgets import QtAction, QtActionGroup, QtCheckBox, QtComboBox, QtDoubleSpinBox, QtMenu, QtPushButton, QtRegExpValidator, QtSlider, QtSpinBox, QtTabWidget, QtTimer, SlotBoundary


class Recorder:
    """Collects slot calls and reported slot errors.

    Attributes:
        calls  : (tag, arguments) in call order.
        errors : Exceptions the boundary reported.
    """

    def __init__(self) -> None:
        """Starts empty."""

        self.calls  = []
        self.errors = []

    def report(self, exc: Exception, text: str) -> None:
        """Slot boundary reporter."""

        self.errors.append(exc)

    def slot(self, tag: str):
        """Returns a slot recording its arguments under ``tag``."""

        return lambda *args: self.calls.append((tag, args))


@pytest.fixture
def recorder() -> Recorder:
    """A fresh recorder."""

    return Recorder()


@pytest.fixture
def boundary(recorder) -> SlotBoundary:
    """A slot boundary reporting to the recorder."""

    return SlotBoundary(recorder.report)


def test_checkbox_emits_state_changed_before_toggled_only_on_change(recorder, boundary):
    """setChecked emits stateChanged(2|0) then toggled, once per change, also while disabled."""

    box = QtCheckBox(boundary, "box")
    box.stateChanged.connect(recorder.slot("state"))
    box.toggled.connect(recorder.slot("toggled"))
    box.setEnabled(False)

    box.setChecked(True)
    box.setChecked(True)
    box.setChecked(False)

    assert recorder.calls == [("state", (2,)), ("toggled", (True,)), ("state", (0,)), ("toggled", (False,))]


def test_checkbox_click_is_ignored_while_disabled(recorder, boundary):
    """click() does nothing on a disabled box and toggles an enabled one."""

    box = QtCheckBox(boundary, "box")
    box.clicked.connect(recorder.slot("clicked"))
    box.setEnabled(False)
    box.click()

    assert not box.isChecked() and recorder.calls == []

    box.setEnabled(True)
    box.click()

    assert box.isChecked() and recorder.calls == [("clicked", (True,))]


def test_slots_receive_only_the_arguments_they_accept(recorder, boundary):
    """A slot without parameters connected to a signal with arguments is called without them, as PyQt5 does."""

    seen   = []
    widget = QtSpinBox(boundary, "spin")
    widget.valueChanged.connect(lambda: seen.append("no args"))
    widget.valueChanged.connect(lambda value: seen.append(value))
    widget.setValue(5)

    assert seen == ["no args", 5]


def test_slot_boundary_reports_and_continues_with_the_next_slot(recorder, boundary):
    """An exception in one slot is reported and the following slots still run."""

    widget = QtPushButton(boundary, "button", "Go")
    widget.clicked.connect(lambda: 1 / 0)
    widget.clicked.connect(recorder.slot("after"))
    widget.click()

    assert [type(error) for error in recorder.errors] == [ZeroDivisionError]
    assert recorder.calls == [("after", (False,))]


def test_disconnect_removes_every_connection_and_raises_when_none(recorder, boundary):
    """disconnect drops all connections of a slot; disconnecting again raises TypeError (PyQt5)."""

    widget = QtSlider(boundary, "slider")
    slot   = recorder.slot("value")
    widget.valueChanged.connect(slot)
    widget.valueChanged.connect(slot)

    assert widget.valueChanged.receivers() == 2

    widget.valueChanged.disconnect(slot)

    assert widget.valueChanged.receivers() == 0
    with pytest.raises(TypeError):
        widget.valueChanged.disconnect(slot)


def test_blocked_signals_do_not_emit(recorder, boundary):
    """blockSignals suppresses emission and returns the previous state."""

    spin = QtDoubleSpinBox(boundary, "spin")
    spin.valueChanged.connect(recorder.slot("value"))

    assert spin.blockSignals(True) is False
    spin.setValue(3.0)
    assert spin.blockSignals(False) is True
    assert spin.value() == 3.0 and recorder.calls == []


def test_slider_clamps_and_moves_the_other_bound(recorder, boundary):
    """setMaximum below the value clamps it with an emission; setMaximum below the minimum moves the minimum."""

    slider = QtSlider(boundary, "slider")
    slider.valueChanged.connect(recorder.slot("value"))

    assert (slider.minimum(), slider.maximum(), slider.value()) == (0, 99, 0)

    slider.setValue(50)
    slider.setMaximum(20)

    assert slider.value() == 20
    assert recorder.calls == [("value", (50,)), ("value", (20,))]

    slider.setMinimum(30)

    assert (slider.minimum(), slider.maximum(), slider.value()) == (30, 30, 30)


def test_spin_box_default_range_and_clamping(recorder, boundary):
    """QSpinBox starts at 0..99 and clamps values into its range."""

    spin = QtSpinBox(boundary, "spin")
    spin.setValue(150)

    assert spin.value() == 99

    spin.setMaximum(23)

    assert (spin.maximum(), spin.value(), spin.text()) == (23, 23, "23")


@pytest.mark.parametrize("value, rounded", [(0.123456, 0.12), (57.987654, 57.99), (6.875, 6.88), (-0.004, -0.0)])
def test_double_spin_box_rounds_values_to_its_decimals(boundary, value, rounded):
    """Values pass through QString::number(value, 'f', decimals) before clamping."""

    spin = QtDoubleSpinBox(boundary, "spin")
    spin.setRange(-1e5, 1e5)
    spin.setValue(value)

    assert spin.value() == rounded


def test_double_spin_box_rounds_its_range_and_clamps(boundary):
    """A maximum of 13.7477 becomes 13.75, a value of 100 clamps to it, and the text shows two decimals."""

    spin = QtDoubleSpinBox(boundary, "spin")
    spin.setRange(-1e5, 1e5)
    spin.setMinimum(0.0)
    spin.setMaximum(13.7477)
    spin.setValue(100)

    assert (spin.maximum(), spin.value(), spin.text()) == (13.75, 13.75, "13.75")


def test_double_spin_box_six_decimals_as_in_the_axes_dialog(boundary):
    """The Axes dialog's spin boxes keep six decimals: 13.74772708 becomes 13.747727."""

    spin = QtDoubleSpinBox(boundary, "spin")
    spin.setDecimals(6)
    spin.setRange(-1e9, 1e9)
    spin.setValue(13.74772708486752)

    assert spin.value() == 13.747727


def test_combo_emits_index_then_text_on_change(recorder, boundary):
    """setCurrentIndex emits currentIndexChanged then currentTextChanged; setCurrentText finds the item."""

    combo = QtComboBox(boundary, "combo")
    for name in ("a", "b", "c"):
        combo.addItem(name)
    combo.currentIndexChanged.connect(recorder.slot("index"))
    combo.currentTextChanged.connect(recorder.slot("text"))

    combo.setCurrentText("c")
    combo.setCurrentIndex(2)

    assert combo.currentIndex() == 2
    assert recorder.calls == [("index", (2,)), ("text", ("c",))]


@pytest.mark.parametrize("text, state", [
    ("12", "Acceptable"), ("-3.5", "Acceptable"), ("12.", "Acceptable"), ("12.3456", "Acceptable"),
    ("", "Intermediate"), ("-", "Intermediate"),
    (".5", "Invalid"), ("12.34567", "Invalid"), ("a", "Invalid"), ("1-2", "Invalid"),
])
def test_roi_field_validator_states(text, state):
    """The ROI fields' QRegExp -?[0-9]+[.]?[0-9]{,4} accepts, waits on prefixes and refuses the rest."""

    assert QtRegExpValidator("-?[0-9]+[.]?[0-9]{,4}").validate(text) == state


def test_exclusive_action_group_keeps_one_checked_member(recorder, boundary):
    """Triggering a member checks it and unchecks the previous one; triggering the checked one keeps it checked."""

    menu    = QtMenu(boundary, "menu", "&Channel")
    group   = QtActionGroup()
    actions = [QtAction(boundary, name, name, menu, checkable=True) for name in ("rgb", "red")]
    actions[0].setChecked(True)
    for action in actions:
        group.addAction(action)
        action.triggered.connect(recorder.slot(action.name))

    actions[1].trigger()

    assert [action.isChecked() for action in actions] == [False, True]
    assert group.checkedAction() is actions[1]

    actions[1].trigger()

    assert actions[1].isChecked()
    assert recorder.calls == [("red", (True,)), ("red", (True,))]


def test_shortcut_ignores_a_disabled_parent_menu_but_not_a_disabled_action(recorder, boundary):
    """Ctrl+F style activation runs inside a disabled menu (F-007); a disabled action never triggers (F-004)."""

    menu   = QtMenu(boundary, "menu", "&Channel")
    action = QtAction(boundary, "rgb", "&RGB", menu)
    action.triggered.connect(recorder.slot("rgb"))
    menu.setEnabled(False)

    assert not menu.chainEnabled()

    action.activateShortcut()
    action.setEnabled(False)
    action.trigger()

    assert recorder.calls == [("rgb", (False,))]


def test_tab_widget_and_timer(recorder, boundary):
    """Tab changes emit currentChanged once; the timer reports its interval only once started."""

    tabs = QtTabWidget(boundary, "tabs")
    for title in ("Slicer", "Plot"):
        tabs.addTab(title)
    tabs.currentChanged.connect(recorder.slot("tab"))
    tabs.setCurrentIndex(1)
    tabs.setCurrentIndex(1)
    tabs.setCurrentIndex(5)

    timer = QtTimer(boundary, "timer")
    assert (timer.isActive(), timer.interval()) == (False, 0)
    timer.start(500)

    assert recorder.calls == [("tab", (1,))]
    assert (timer.isActive(), timer.interval()) == (True, 500)

