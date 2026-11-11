"""Validation and dispatch of the TomoVis page's window events.

The browser reports each user action on a server-owned TomoVis control as
the Qt operation the user performed (click, check, value, index, text,
trigger, shortcut, tab, roi, tick, dialog_result). This module checks the
event against the window's widget table and performs that operation on the
headless widgets, so the copied slots run exactly as in Qt. It also reads
the controls back for the snapshot, keyed like the parity goldens'
``state.controls``.
"""

from __future__ import annotations

import numbers

from tomovis.qt_widgets import QtRegExpValidator


class TomoVisEventError(Exception):
    """An event the window cannot accept.

    Attributes:
        status : HTTP status the router answers with (400 invalid, 409 stale dialog token).
    """

    def __init__(self, message: str, status: int = 400) -> None:
        """Stores the message and status.

        Args:
            message : Error text sent to the browser.
            status  : HTTP status.
        """

        super().__init__(message)
        self.status = status


class TomoVisEvents:
    """Maps API events onto widget operations of one TomoVisWindow.

    Attributes:
        ACTIONS      : Menu action names.
        SHORTCUTS    : Shortcut text to action name.
        BUTTONS      : Push buttons the server owns.
        CHECKBOXES   : Check boxes the server owns.
        VALUES       : Sliders and spin boxes the server owns, with the number type their value takes.
        COMBOS       : Combo boxes the server owns.
        LINE_EDITS   : The six ROI fields.
        RADIOS       : 3D radio buttons (browser-owned, reported read-only).
        TAB4_BUTTONS : 3D push buttons (browser-owned, reported read-only).
        window       : The window the events act on.
    """

    ACTIONS      = ("openFile", "saveFile", "openFUSAR", "openRAT", "openUAVSAR", "openNpy", "allChMenu", "ch1Menu", "ch2Menu", "ch3Menu")
    SHORTCUTS    = {"Ctrl+O": "openFile", "Ctrl+S": "saveFile", "Ctrl+F": "allChMenu"}
    BUTTONS      = ("tab1PlayButton", "tab1SetButton", "tab1PlotButton", "tab2AxesButton", "tab2PlotButton", "tab2ClearButton", "tab3ClearButton")
    CHECKBOXES   = ("tab1ChkBox", "tab2ChkBox1", "tab2ChkBox2", "tab2ChkBox3", "tab2ChkBox4")
    VALUES       = {"tab1Slider": int, "tab2Slider": int, "tab1SpinBox": int, "tab2SpinBox": float}
    COMBOS       = ("tab1ComboBox", "tab2ComboBox")
    LINE_EDITS   = ("tab1QLineEdit1", "tab1QLineEdit2", "tab1QLineEdit3", "tab1QLineEdit4", "tab1QLineEdit5", "tab1QLineEdit6")
    RADIOS       = ("turntableCameraTab4Button", "flyCameraTab4Button", "arcballCameraTab4Button", "mipProjectionTab4Button", "isoProjectionTab4Button", "translucentProjectionTab4Button", "additiveProjectionTab4Button")
    TAB4_BUTTONS = ("colormapTab4Button", "resetCamerasTab4Button", "channelTab4Button")

    def __init__(self, window) -> None:
        """Binds the dispatcher to a window.

        Args:
            window : TomoVisWindow.
        """

        self.window = window

    def field(self, event: dict, name: str, kinds):
        """Returns one event field after checking its type.

        Args:
            event : Event dict.
            name  : Field name.
            kinds : Accepted type or tuple of types.

        Returns:
            The field value.

        Raises:
            TomoVisEventError : If the field is missing or has the wrong type (bools never count as numbers).
        """

        if name not in event:
            raise TomoVisEventError(f"event field '{name}' is missing")
        value = event[name]
        if isinstance(value, bool) and bool not in (kinds if isinstance(kinds, tuple) else (kinds,)):
            raise TomoVisEventError(f"event field '{name}' must not be a boolean")
        if not isinstance(value, kinds):
            raise TomoVisEventError(f"event field '{name}' has the wrong type")
        return value

    def widget(self, event: dict, names) -> object:
        """Returns the window widget an event names after checking it is in ``names``.

        Raises:
            TomoVisEventError : If the name is not one of ``names``.
        """

        name = self.field(event, "widget", str)
        if name not in names:
            raise TomoVisEventError(f"'{name}' is not a widget this event applies to")
        return getattr(self.window, name)

    def onTrigger(self, event: dict) -> None:
        """Menu click: triggers the action when it and every parent menu are enabled."""

        action = self.widget(event, self.ACTIONS)
        if action.isEnabled() and action.menu.chainEnabled():
            action.trigger()

    def onShortcut(self, event: dict) -> None:
        """Shortcut: activates the action owning the key sequence when the action is enabled (F-004, F-007)."""

        keys = self.field(event, "keys", str)
        if keys not in self.SHORTCUTS:
            raise TomoVisEventError(f"unknown shortcut '{keys}'")
        action = getattr(self.window, self.SHORTCUTS[keys])
        if action.isEnabled():
            action.activateShortcut()

    def onClick(self, event: dict) -> None:
        """Push button click; a disabled button ignores it."""

        self.widget(event, self.BUTTONS).click()

    def onCheck(self, event: dict) -> None:
        """Check box click toward the wanted state; ignored while disabled or already in that state."""

        box     = self.widget(event, self.CHECKBOXES)
        checked = self.field(event, "checked", bool)
        if box.isEnabled() and checked != box.isChecked():
            box.click()

    def onValue(self, event: dict) -> None:
        """Slider or spin box value; Qt clamps and rounds; ignored while disabled."""

        name    = self.field(event, "widget", str)
        control = self.widget(event, tuple(self.VALUES))
        value   = self.field(event, "value", numbers.Real)
        if self.VALUES[name] is int and float(value) != int(value):
            raise TomoVisEventError(f"'{name}' takes integer values")
        if control.isEnabled():
            control.setValue(self.VALUES[name](value))

    def onIndex(self, event: dict) -> None:
        """Combo box selection; ignored while disabled."""

        combo = self.widget(event, self.COMBOS)
        index = self.field(event, "index", int)
        if not 0 <= index < combo.count():
            raise TomoVisEventError(f"index {index} is outside the combo box")
        if combo.isEnabled():
            combo.setCurrentIndex(index)

    def onText(self, event: dict) -> None:
        """ROI field text; refused by the validator when Invalid, ignored while disabled."""

        edit = self.widget(event, self.LINE_EDITS)
        text = self.field(event, "text", str)
        if edit.isEnabled() and edit.validator.validate(text) != QtRegExpValidator.INVALID:
            edit.setText(text)

    def onTab(self, event: dict) -> None:
        """Tab click."""

        index = self.field(event, "index", int)
        if not 0 <= index < self.window.tabWidget.count():
            raise TomoVisEventError(f"tab {index} does not exist")
        self.window.tabWidget.setCurrentIndex(index)

    def point(self, value, name: str) -> list[float]:
        """Checks a two-number list.

        Raises:
            TomoVisEventError : If the value is not two finite numbers.
        """

        if not isinstance(value, list) or len(value) != 2 or not all(isinstance(entry, numbers.Real) and not isinstance(entry, bool) for entry in value):
            raise TomoVisEventError(f"'{name}' must be a list of two numbers")
        return [float(entry) for entry in value]

    def onRoi(self, event: dict) -> None:
        """ROI drag step: stores the browser's pyqtgraph state and runs ROI.stateChanged."""

        state   = self.field(event, "state", dict)
        handles = state.get("handles")
        if not isinstance(handles, list) or len(handles) != 2 or not all(isinstance(handle, dict) for handle in handles):
            raise TomoVisEventError("'state.handles' must hold two handles")
        angle = state.get("angle")
        if not isinstance(angle, numbers.Real) or isinstance(angle, bool):
            raise TomoVisEventError("'state.angle' must be a number")

        clean = {
            "pos"     : self.point(state.get("pos"), "state.pos"),
            "size"    : self.point(state.get("size"), "state.size"),
            "angle"   : float(angle),
            "handles" : [{"pos": self.point(handle.get("pos"), "handle.pos"), "item": self.point(handle.get("item"), "handle.item")} for handle in handles],
        }
        moved  = self.field(event, "free_handle_moved", bool)
        finish = self.field(event, "finish", bool)

        self.window.roi_1.applyClientState(clean, moved)
        self.window.roi_1.stateChanged(finish=finish)

    def onTick(self, event: dict) -> None:
        """Play timer period: emits timeout while the timer is active."""

        if self.window.tab1Timer.isActive():
            self.window.tab1Timer.timeout.emit()

    def onDialogResult(self, event: dict) -> None:
        """Answer to a file or Axes dialog."""

        token    = self.field(event, "token", str)
        accepted = self.field(event, "accepted", bool)
        result   = {"accepted": accepted}
        if accepted and "path" in event:
            result["path"] = self.field(event, "path", str)
        if accepted and "values" in event:
            values = self.field(event, "values", dict)
            for name in ("x_label", "z_label"):
                if name in values and not isinstance(values[name], str):
                    raise TomoVisEventError(f"'values.{name}' must be a string")
            for name in ("x_min", "x_max", "z_min", "z_max"):
                if name in values and (not isinstance(values[name], numbers.Real) or isinstance(values[name], bool)):
                    raise TomoVisEventError(f"'values.{name}' must be a number")
            result["values"] = values
        self.window.dialogs.resolve(token, result)

    def onSync(self, event: dict) -> None:
        """Resynchronisation: the next response carries every current image."""

        self.window.resendViews()

    def dispatch(self, event: dict) -> None:
        """Runs one event.

        Args:
            event : {"type": ..., ...}.

        Raises:
            TomoVisEventError : For an unknown type or invalid fields.
        """

        if not isinstance(event, dict):
            raise TomoVisEventError("event must be an object")
        handlers = {
            "sync"          : self.onSync,
            "trigger"       : self.onTrigger,
            "shortcut"      : self.onShortcut,
            "click"         : self.onClick,
            "check"         : self.onCheck,
            "value"         : self.onValue,
            "index"         : self.onIndex,
            "text"          : self.onText,
            "tab"           : self.onTab,
            "roi"           : self.onRoi,
            "tick"          : self.onTick,
            "dialog_result" : self.onDialogResult,
        }
        kind = event.get("type")
        if kind not in handlers:
            raise TomoVisEventError(f"unknown event type '{kind}'")
        handlers[kind](event)

    def controls(self) -> dict:
        """Reads every control the way the parity goldens record them, plus what the browser needs.

        Returns:
            Control name to its state dict.
        """

        window = self.window
        state  = {}

        for name in self.ACTIONS:
            action      = getattr(window, name)
            state[name] = {"enabled": action.isEnabled(), "checked": action.isChecked(), "text": action.text(), "shortcut": action.shortcut, "statusTip": action.statusTip(), "checkable": action.checkable}
        state["ChMenu"] = {"enabled": window.ChMenu.isEnabled(), "title": window.ChMenu.title()}

        for name in ("tab1Slider", "tab2Slider", "isoThresholdTab4Slider"):
            slider      = getattr(window, name)
            state[name] = {"enabled": slider.isEnabled(), "minimum": slider.minimum(), "maximum": slider.maximum(), "value": slider.value()}

        state["tab1SpinBox"] = {"enabled": window.tab1SpinBox.isEnabled(), "minimum": window.tab1SpinBox.minimum(), "maximum": window.tab1SpinBox.maximum(), "value": window.tab1SpinBox.value(), "text": window.tab1SpinBox.text()}
        state["tab2SpinBox"] = {"enabled": window.tab2SpinBox.isEnabled(), "minimum": window.tab2SpinBox.minimum(), "maximum": window.tab2SpinBox.maximum(), "value": window.tab2SpinBox.value(), "decimals": window.tab2SpinBox.decimals(), "text": window.tab2SpinBox.text()}

        for name in self.CHECKBOXES + self.RADIOS:
            box         = getattr(window, name)
            state[name] = {"enabled": box.isEnabled(), "checked": box.isChecked()}

        for name in self.BUTTONS + self.TAB4_BUTTONS:
            button      = getattr(window, name)
            state[name] = {"enabled": button.isEnabled(), "text": button.text()}

        for name in self.COMBOS:
            combo       = getattr(window, name)
            state[name] = {"enabled": combo.isEnabled(), "index": combo.currentIndex(), "text": combo.currentText(), "count": combo.count()}

        for name in self.LINE_EDITS:
            edit        = getattr(window, name)
            state[name] = {"enabled": edit.isEnabled(), "text": edit.text(), "placeholder": edit.placeholderText()}

        state["tabWidget"]  = {"index": window.tabWidget.currentIndex(), "count": window.tabWidget.count(), "titles": list(window.tabWidget.titles)}
        state["imv1"]       = {"current": window.imv1.currentName()}
        state["imv2"]       = {"current": window.imv2.currentName()}
        state["tab1Timer"]  = {"active": window.tab1Timer.isActive(), "interval": window.tab1Timer.interval()}
        state["slice_line"] = window.slice_line.snapshot()
        state["roi_1"]      = window.roi_1.snapshot()
        return state
