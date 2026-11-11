"""Headless stand-ins for the Qt widgets the TomoVis window drives.

Each class stores the state its Qt counterpart keeps and reproduces the
signal semantics TomoVis relies on: which setter emits which signal, in which
order, only on change, with Qt's clamping and decimal rounding. Signals call
their slots inside a slot boundary that reports an exception and carries on
with the next slot, the way the original behaves under pyqtgraph's
excepthook, so the copied window code runs in the same order with the same
half-applied state after a failing slot.
"""

from __future__ import annotations

import inspect
import itertools
import re
import traceback


class SlotBoundary:
    """Runs slots the way a Qt signal emission does under pyqtgraph's excepthook.

    Attributes:
        reporter : Callable receiving (exception, formatted traceback) for every exception a slot raises.
    """

    def __init__(self, reporter) -> None:
        """Stores the reporter.

        Args:
            reporter : Callable taking an exception and its formatted traceback text.
        """

        self.reporter = reporter

    def run(self, slot, args: tuple) -> None:
        """Calls one slot and reports the exception it raises instead of propagating it.

        Args:
            slot : Callable connected to a signal.
            args : Arguments the slot accepts.
        """

        try:
            slot(*args)
        except Exception as exc:
            self.reporter(exc, traceback.format_exc())


class Signal:
    """A Qt signal: an ordered list of connected slots called on emit.

    Attributes:
        owner : Widget emitting the signal; its blocked flag suppresses emission.
        name  : Signal name, used in error messages.
        slots : Connected (slot, accepted argument count) pairs in connection order, duplicates allowed.
    """

    def __init__(self, owner, name: str) -> None:
        """Creates a signal with no connections.

        Args:
            owner : Widget emitting the signal.
            name  : Signal name.
        """

        self.owner = owner
        self.name  = name
        self.slots = []

    def accepted_arguments(self, slot) -> int | None:
        """Returns how many positional arguments a slot accepts, None for any number.

        PyQt5 drops trailing signal arguments a slot does not accept; this count reproduces that.

        Args:
            slot : Callable to inspect.

        Returns:
            Number of positional parameters, None when the slot takes ``*args``.
        """

        count = 0
        for parameter in inspect.signature(slot).parameters.values():
            if parameter.kind == parameter.VAR_POSITIONAL:
                return None
            if parameter.kind in (parameter.POSITIONAL_ONLY, parameter.POSITIONAL_OR_KEYWORD) and parameter.default is parameter.empty:
                count += 1
        return count

    def connect(self, slot) -> None:
        """Appends a connection, as Qt does without Qt.UniqueConnection.

        Args:
            slot : Callable to call on emit.
        """

        self.slots.append((slot, self.accepted_arguments(slot)))

    def disconnect(self, slot) -> None:
        """Removes every connection to a slot.

        Args:
            slot : Callable connected earlier.

        Raises:
            TypeError : If the slot is not connected, as PyQt5 raises.
        """

        remaining = [entry for entry in self.slots if entry[0] != slot]
        if len(remaining) == len(self.slots):
            raise TypeError(f"disconnect() failed between '{self.name}' and '{getattr(slot, '__name__', slot)}'")
        self.slots = remaining

    def receivers(self) -> int:
        """Returns the number of connections."""

        return len(self.slots)

    def emit(self, *args) -> None:
        """Calls every connected slot in order inside the owner's slot boundary.

        Args:
            args : Signal arguments; each slot receives as many as it accepts.
        """

        if self.owner.signalsBlocked():
            return

        for slot, count in list(self.slots):
            self.owner.boundary.run(slot, args if count is None else args[:count])


class QtWidget:
    """Base of every stand-in: name, enabled state and signal blocking.

    Attributes:
        boundary : Slot boundary every signal of this widget emits through.
        name     : Attribute name of the widget in the window.
        enabled  : Whether the widget accepts user input.
        blocked  : Whether signals are blocked (QObject.blockSignals).
    """

    def __init__(self, boundary: SlotBoundary, name: str) -> None:
        """Creates an enabled widget with unblocked signals.

        Args:
            boundary : Slot boundary for this widget's signals.
            name     : Attribute name in the window.
        """

        self.boundary = boundary
        self.name     = name
        self.enabled  = True
        self.blocked  = False

    def isEnabled(self) -> bool:
        """Returns whether the widget is enabled."""

        return self.enabled

    def setEnabled(self, enabled: bool) -> None:
        """Enables or disables the widget."""

        self.enabled = bool(enabled)

    def blockSignals(self, blocked: bool) -> bool:
        """Blocks or unblocks this widget's signals.

        Returns:
            The previous blocked state, as QObject.blockSignals.
        """

        previous, self.blocked = self.blocked, bool(blocked)
        return previous

    def signalsBlocked(self) -> bool:
        """Returns whether signals are blocked."""

        return self.blocked

    def objectName(self) -> str:
        """Returns the widget's attribute name."""

        return self.name


class QtMenu(QtWidget):
    """A QMenu holding actions; only its title and enabled state matter.

    Attributes:
        title_text : Menu title with its '&' mnemonic.
        parent     : Parent menu, None for a top-level menu.
    """

    def __init__(self, boundary: SlotBoundary, name: str, title: str, parent: QtMenu | None = None) -> None:
        """Creates an enabled menu.

        Args:
            boundary : Slot boundary.
            name     : Attribute name in the window.
            title    : Menu title with its '&' mnemonic.
            parent   : Parent menu, None for a menu-bar menu.
        """

        super().__init__(boundary, name)
        self.title_text = title
        self.parent     = parent

    def title(self) -> str:
        """Returns the title."""

        return self.title_text

    def chainEnabled(self) -> bool:
        """Returns whether this menu and every parent menu are enabled, as needed to click an entry."""

        menu = self
        while menu is not None:
            if not menu.enabled:
                return False
            menu = menu.parent
        return True


class QtAction(QtWidget):
    """A QAction with Qt's trigger, check and exclusive-group semantics.

    Attributes:
        text_value : Action text with its '&' mnemonic.
        menu       : Menu holding the action.
        shortcut   : Shortcut text, empty when none.
        status_tip : Status tip shown while the action is hovered.
        checkable  : Whether the action can be checked.
        checked    : Whether the action is checked.
        group      : Exclusive action group, None when ungrouped.
        triggered  : Signal(bool) emitted by trigger().
        toggled    : Signal(bool) emitted when the checked state changes.
    """

    def __init__(self, boundary: SlotBoundary, name: str, text: str, menu: QtMenu, checkable: bool = False) -> None:
        """Creates an enabled, unchecked action.

        Args:
            boundary  : Slot boundary.
            name      : Attribute name in the window.
            text      : Action text with its '&' mnemonic.
            menu      : Menu holding the action.
            checkable : Whether the action can be checked.
        """

        super().__init__(boundary, name)
        self.text_value = text
        self.menu       = menu
        self.shortcut   = ""
        self.status_tip = ""
        self.checkable  = checkable
        self.checked    = False
        self.group      = None
        self.triggered  = Signal(self, "triggered")
        self.toggled    = Signal(self, "toggled")

    def text(self) -> str:
        """Returns the action text."""

        return self.text_value

    def setShortcut(self, shortcut: str) -> None:
        """Sets the shortcut text."""

        self.shortcut = shortcut

    def setStatusTip(self, tip: str) -> None:
        """Sets the status tip."""

        self.status_tip = tip

    def statusTip(self) -> str:
        """Returns the status tip."""

        return self.status_tip

    def isChecked(self) -> bool:
        """Returns whether the action is checked."""

        return self.checked

    def setChecked(self, checked: bool) -> None:
        """Checks or unchecks the action; the exclusive group unchecks its previous member first.

        Emits toggled only on change, as QAction.setChecked.

        Args:
            checked : Wanted state.
        """

        checked = bool(checked)
        if not self.checkable or self.checked == checked:
            return

        self.checked = checked
        if self.group is not None:
            self.group.actionChanged(self)
        self.toggled.emit(checked)

    def trigger(self) -> None:
        """Activates the action as a menu click does.

        Nothing happens while disabled. A checkable action toggles, except the
        checked member of an exclusive group, which stays checked; triggered
        then carries the checked state.
        """

        if not self.enabled:
            return

        if self.checkable:
            if self.checked and self.group is not None and self.group.checkedAction() is self:
                self.triggered.emit(True)
                return
            self.setChecked(not self.checked)
        self.triggered.emit(self.checked)

    def activateShortcut(self) -> None:
        """Activates the action from its shortcut; the parent menu's enabled state is not consulted (F-007)."""

        self.trigger()


class QtActionGroup:
    """An exclusive QActionGroup.

    Attributes:
        actions : Member actions in insertion order.
        current : The checked member, None when none is checked.
    """

    def __init__(self) -> None:
        """Creates an empty exclusive group."""

        self.actions = []
        self.current = None

    def addAction(self, action: QtAction) -> QtAction:
        """Adds a member; a checked action becomes the group's current one.

        Returns:
            The added action, as QActionGroup.addAction.
        """

        self.actions.append(action)
        action.group = self
        if action.checked:
            self.current = action
        return action

    def actionChanged(self, action: QtAction) -> None:
        """Keeps the group exclusive after a member changed its checked state (QActionGroupPrivate._q_actionChanged).

        Args:
            action : Member whose checked state just changed.
        """

        if action.checked:
            if action is not self.current:
                previous, self.current = self.current, action
                if previous is not None:
                    previous.setChecked(False)
        elif action is self.current:
            self.current = None

    def checkedAction(self) -> QtAction | None:
        """Returns the checked member."""

        return self.current


class QtPushButton(QtWidget):
    """A QPushButton.

    Attributes:
        text_value : Button text.
        icon       : Icon name, empty when none.
        clicked    : Signal(bool) emitted by click().
    """

    def __init__(self, boundary: SlotBoundary, name: str, text: str = "", icon: str = "") -> None:
        """Creates an enabled button.

        Args:
            boundary : Slot boundary.
            name     : Attribute name in the window.
            text     : Button text.
            icon     : Icon name.
        """

        super().__init__(boundary, name)
        self.text_value = text
        self.icon       = icon
        self.clicked    = Signal(self, "clicked")

    def text(self) -> str:
        """Returns the button text."""

        return self.text_value

    def click(self) -> None:
        """Clicks the button; nothing happens while it is disabled."""

        if not self.enabled:
            return
        self.clicked.emit(False)


class QtCheckBox(QtWidget):
    """A QCheckBox.

    Attributes:
        checked      : Whether the box is checked.
        stateChanged : Signal(int) emitted with 0 or 2 when the state changes, before toggled.
        toggled      : Signal(bool) emitted when the state changes.
        clicked      : Signal(bool) emitted by click().
    """

    def __init__(self, boundary: SlotBoundary, name: str) -> None:
        """Creates an enabled, unchecked box.

        Args:
            boundary : Slot boundary.
            name     : Attribute name in the window.
        """

        super().__init__(boundary, name)
        self.checked      = False
        self.stateChanged = Signal(self, "stateChanged")
        self.toggled      = Signal(self, "toggled")
        self.clicked      = Signal(self, "clicked")

    def isChecked(self) -> bool:
        """Returns whether the box is checked."""

        return self.checked

    def setChecked(self, checked: bool) -> None:
        """Sets the state; emits stateChanged then toggled on change, also while disabled.

        Args:
            checked : Wanted state.
        """

        checked = bool(checked)
        if self.checked == checked:
            return

        self.checked = checked
        self.stateChanged.emit(2 if checked else 0)
        self.toggled.emit(checked)

    def click(self) -> None:
        """Toggles the box as a mouse click does; nothing happens while disabled."""

        if not self.enabled:
            return
        self.setChecked(not self.checked)
        self.clicked.emit(self.checked)


class QtRadioButton(QtCheckBox):
    """A QRadioButton of the 3D tab; the browser owns its behaviour, the server keeps its state.

    Attributes:
        text_value : Radio label.
    """

    def __init__(self, boundary: SlotBoundary, name: str, text: str) -> None:
        """Creates an enabled, unchecked radio button.

        Args:
            boundary : Slot boundary.
            name     : Attribute name in the window.
            text     : Radio label.
        """

        super().__init__(boundary, name)
        self.text_value = text

    def text(self) -> str:
        """Returns the label."""

        return self.text_value


class QtSlider(QtWidget):
    """A horizontal QSlider (QAbstractSlider semantics, tracking on).

    Attributes:
        minimum_value : Lower bound.
        maximum_value : Upper bound.
        value_now     : Current value.
        single_step   : Arrow-key and wheel step.
        page_step     : PageUp/PageDown step.
        tick_interval : Tick interval as set by setTickInterval.
        valueChanged  : Signal(int) emitted when the value changes.
        sliderMoved   : Signal(int) emitted only by a user drag, which the browser performs.
    """

    def __init__(self, boundary: SlotBoundary, name: str) -> None:
        """Creates a slider with Qt's default range 0..99 at 0.

        Args:
            boundary : Slot boundary.
            name     : Attribute name in the window.
        """

        super().__init__(boundary, name)
        self.minimum_value = 0
        self.maximum_value = 99
        self.value_now     = 0
        self.single_step   = 1
        self.page_step     = 10
        self.tick_interval = 0
        self.valueChanged  = Signal(self, "valueChanged")
        self.sliderMoved   = Signal(self, "sliderMoved")

    def minimum(self) -> int:
        """Returns the lower bound."""

        return self.minimum_value

    def maximum(self) -> int:
        """Returns the upper bound."""

        return self.maximum_value

    def value(self) -> int:
        """Returns the current value."""

        return self.value_now

    def setRange(self, minimum: int, maximum: int) -> None:
        """Sets both bounds and re-bounds the value, emitting valueChanged when it moves.

        Args:
            minimum : Lower bound.
            maximum : Upper bound; raised to the minimum when smaller.
        """

        self.minimum_value = int(minimum)
        self.maximum_value = max(int(minimum), int(maximum))
        self.setValue(self.value_now)

    def setMinimum(self, minimum: int) -> None:
        """Sets the lower bound, moving the upper bound up when needed."""

        self.setRange(minimum, max(self.maximum_value, int(minimum)))

    def setMaximum(self, maximum: int) -> None:
        """Sets the upper bound, moving the lower bound down when needed."""

        self.setRange(min(self.minimum_value, int(maximum)), maximum)

    def setValue(self, value: int) -> None:
        """Sets the value clamped to the range; emits valueChanged on change.

        Args:
            value : Wanted value.
        """

        value = max(self.minimum_value, min(int(value), self.maximum_value))
        if value == self.value_now:
            return
        self.value_now = value
        self.valueChanged.emit(value)

    def setSliderPosition(self, position: int) -> None:
        """Moves the slider; with tracking on this is setValue."""

        self.setValue(position)

    def setTickInterval(self, interval: int) -> None:
        """Stores the tick interval."""

        self.tick_interval = int(interval)


class QtSpinBox(QtWidget):
    """A QSpinBox.

    Attributes:
        minimum_value : Lower bound.
        maximum_value : Upper bound.
        value_now     : Current value.
        single_step   : Step of the arrows, keys and wheel.
        valueChanged  : Signal(int) emitted when the value changes.
    """

    def __init__(self, boundary: SlotBoundary, name: str) -> None:
        """Creates a spin box with Qt's default range 0..99 at 0.

        Args:
            boundary : Slot boundary.
            name     : Attribute name in the window.
        """

        super().__init__(boundary, name)
        self.minimum_value = 0
        self.maximum_value = 99
        self.value_now     = 0
        self.single_step   = 1
        self.valueChanged  = Signal(self, "valueChanged")

    def minimum(self) -> int:
        """Returns the lower bound."""

        return self.minimum_value

    def maximum(self) -> int:
        """Returns the upper bound."""

        return self.maximum_value

    def value(self) -> int:
        """Returns the current value."""

        return self.value_now

    def text(self) -> str:
        """Returns the displayed text."""

        return str(self.value_now)

    def setSingleStep(self, step: int) -> None:
        """Sets the step."""

        self.single_step = int(step)

    def setRange(self, minimum: int, maximum: int) -> None:
        """Sets both bounds; the maximum never falls below the minimum; the value is re-bounded with emission.

        Args:
            minimum : Lower bound.
            maximum : Upper bound.
        """

        self.minimum_value = int(minimum)
        self.maximum_value = int(maximum) if int(minimum) < int(maximum) else int(minimum)
        self.setValue(self.value_now)

    def setMinimum(self, minimum: int) -> None:
        """Sets the lower bound, moving the upper bound up when needed."""

        self.setRange(minimum, self.maximum_value if self.maximum_value > int(minimum) else minimum)

    def setMaximum(self, maximum: int) -> None:
        """Sets the upper bound, moving the lower bound down when needed."""

        self.setRange(self.minimum_value if self.minimum_value < int(maximum) else maximum, maximum)

    def setValue(self, value: int) -> None:
        """Sets the value clamped to the range; emits valueChanged on change.

        Args:
            value : Wanted value.
        """

        value = max(self.minimum_value, min(int(value), self.maximum_value))
        if value == self.value_now:
            return
        self.value_now = value
        self.valueChanged.emit(value)


class QtDoubleSpinBox(QtWidget):
    """A QDoubleSpinBox with Qt's decimal rounding of values and range ends.

    Attributes:
        decimals_count : Number of decimals.
        actual_minimum : Lower bound as requested, before rounding (QDoubleSpinBoxPrivate.actualMin).
        actual_maximum : Upper bound as requested, before rounding.
        minimum_value  : Rounded lower bound.
        maximum_value  : Rounded upper bound.
        value_now      : Current rounded value.
        single_step    : Step of the arrows, keys and wheel.
        valueChanged   : Signal(float) emitted when the value changes.
    """

    def __init__(self, boundary: SlotBoundary, name: str) -> None:
        """Creates a spin box with Qt's defaults: 2 decimals, range 0..99.99, value 0.

        Args:
            boundary : Slot boundary.
            name     : Attribute name in the window.
        """

        super().__init__(boundary, name)
        self.decimals_count = 2
        self.actual_minimum = 0.0
        self.actual_maximum = 99.99
        self.minimum_value  = 0.0
        self.maximum_value  = 99.99
        self.value_now      = 0.0
        self.single_step    = 1.0
        self.valueChanged   = Signal(self, "valueChanged")

    @staticmethod
    def round_qt(value: float, decimals: int) -> float:
        """Rounds as QDoubleSpinBoxPrivate.round: QString::number(value, 'f', decimals).toDouble().

        Args:
            value    : Number to round.
            decimals : Number of decimals.

        Returns:
            The rounded float.
        """

        return float(format(float(value), f".{decimals}f"))

    def decimals(self) -> int:
        """Returns the number of decimals."""

        return self.decimals_count

    def minimum(self) -> float:
        """Returns the rounded lower bound."""

        return self.minimum_value

    def maximum(self) -> float:
        """Returns the rounded upper bound."""

        return self.maximum_value

    def value(self) -> float:
        """Returns the current value."""

        return self.value_now

    def text(self) -> str:
        """Returns the displayed text with the configured decimals."""

        return format(self.value_now, f".{self.decimals_count}f")

    def setSingleStep(self, step: float) -> None:
        """Sets the step."""

        self.single_step = float(step)

    def applyRange(self, minimum: float, maximum: float) -> None:
        """Stores rounded bounds and re-bounds the value with emission (QAbstractSpinBoxPrivate.setRange).

        Args:
            minimum : Rounded lower bound.
            maximum : Rounded upper bound; the minimum when smaller.
        """

        self.minimum_value = minimum
        self.maximum_value = maximum if minimum < maximum else minimum
        self.applyValue(self.value_now)

    def setDecimals(self, decimals: int) -> None:
        """Sets the decimals and re-applies the requested range with the new rounding."""

        self.decimals_count = max(0, min(int(decimals), 323))
        self.setRange(self.actual_minimum, self.actual_maximum)

    def setRange(self, minimum: float, maximum: float) -> None:
        """Sets both bounds, each rounded to the decimals.

        Args:
            minimum : Lower bound.
            maximum : Upper bound.
        """

        self.actual_minimum = float(minimum)
        self.actual_maximum = float(maximum)
        self.applyRange(self.round_qt(minimum, self.decimals_count), self.round_qt(maximum, self.decimals_count))

    def setMinimum(self, minimum: float) -> None:
        """Sets the rounded lower bound, moving the upper bound up when needed."""

        self.actual_minimum = float(minimum)
        rounded             = self.round_qt(minimum, self.decimals_count)
        self.applyRange(rounded, self.maximum_value if self.maximum_value > rounded else rounded)

    def setMaximum(self, maximum: float) -> None:
        """Sets the rounded upper bound, moving the lower bound down when needed."""

        self.actual_maximum = float(maximum)
        rounded             = self.round_qt(maximum, self.decimals_count)
        self.applyRange(self.minimum_value if self.minimum_value < rounded else rounded, rounded)

    def applyValue(self, value: float) -> None:
        """Clamps an already rounded value into the range and emits valueChanged on change.

        Args:
            value : Rounded value.
        """

        value = max(self.minimum_value, min(value, self.maximum_value))
        if value == self.value_now:
            return
        self.value_now = value
        self.valueChanged.emit(value)

    def setValue(self, value: float) -> None:
        """Rounds the value to the decimals, clamps it and emits valueChanged on change.

        Args:
            value : Wanted value.
        """

        self.applyValue(self.round_qt(value, self.decimals_count))


class QtComboBox(QtWidget):
    """A non-editable QComboBox.

    Attributes:
        items               : Item texts in order.
        index               : Current index, -1 when empty.
        currentIndexChanged : Signal(int) emitted when the index changes.
        currentTextChanged  : Signal(str) emitted after currentIndexChanged.
    """

    def __init__(self, boundary: SlotBoundary, name: str) -> None:
        """Creates an empty combo box.

        Args:
            boundary : Slot boundary.
            name     : Attribute name in the window.
        """

        super().__init__(boundary, name)
        self.items               = []
        self.index               = -1
        self.currentIndexChanged = Signal(self, "currentIndexChanged")
        self.currentTextChanged  = Signal(self, "currentTextChanged")

    def addItem(self, text: str) -> None:
        """Appends an item; the first item of an empty box becomes current."""

        self.items.append(str(text))
        if self.index < 0:
            self.setCurrentIndex(0)

    def count(self) -> int:
        """Returns the number of items."""

        return len(self.items)

    def currentIndex(self) -> int:
        """Returns the current index."""

        return self.index

    def currentText(self) -> str:
        """Returns the current item text, empty when none."""

        return self.items[self.index] if self.index >= 0 else ""

    def findText(self, text: str) -> int:
        """Returns the index of an item text, -1 when absent."""

        return self.items.index(text) if text in self.items else -1

    def setCurrentIndex(self, index: int) -> None:
        """Makes an item current; emits currentIndexChanged then currentTextChanged on change.

        Args:
            index : Item index; out-of-range indices select nothing (-1).
        """

        index = int(index) if 0 <= int(index) < len(self.items) else -1
        if index == self.index:
            return
        self.index = index
        self.currentIndexChanged.emit(index)
        self.currentTextChanged.emit(self.currentText())

    def setCurrentText(self, text: str) -> None:
        """Selects the item with this text; nothing happens when no item has it."""

        index = self.findText(text)
        if index >= 0:
            self.setCurrentIndex(index)


class QtRegExpValidator:
    """QRegExpValidator: full matches are Acceptable, prefixes of possible matches Intermediate.

    Python's re module has no partial matching, so a text counts as a prefix
    of a match when appending at most EXTENSION_LENGTH characters from the
    pattern's alphabet completes a match. For the ROI fields' pattern every
    viable prefix completes within one character.

    Attributes:
        pattern  : Regular expression source.
        compiled : Compiled expression.
    """

    ACCEPTABLE       = "Acceptable"
    INTERMEDIATE     = "Intermediate"
    INVALID          = "Invalid"
    ALPHABET         = "0123456789-."
    EXTENSION_LENGTH = 2

    def __init__(self, pattern: str) -> None:
        """Compiles the pattern.

        Args:
            pattern : Regular expression source in QRegExp syntax shared with Python re.
        """

        self.pattern  = pattern
        self.compiled = re.compile(pattern)

    def extensions(self):
        """Yields every string of at most EXTENSION_LENGTH characters from the alphabet."""

        for length in range(self.EXTENSION_LENGTH + 1):
            for letters in itertools.product(self.ALPHABET, repeat=length):
                yield "".join(letters)

    def validate(self, text: str) -> str:
        """Classifies a text.

        Args:
            text : Field contents.

        Returns:
            ACCEPTABLE, INTERMEDIATE or INVALID.
        """

        if self.compiled.fullmatch(text):
            return self.ACCEPTABLE
        if any(self.compiled.fullmatch(text + extension) for extension in self.extensions()):
            return self.INTERMEDIATE
        return self.INVALID


class QtLineEdit(QtWidget):
    """A QLineEdit with an optional validator.

    Attributes:
        text_value  : Current text.
        placeholder : Placeholder text.
        validator   : Validator applied to typed text, None for none.
    """

    def __init__(self, boundary: SlotBoundary, name: str, text: str = "") -> None:
        """Creates an empty enabled line edit.

        Args:
            boundary : Slot boundary.
            name     : Attribute name in the window.
            text     : Initial text.
        """

        super().__init__(boundary, name)
        self.text_value  = text
        self.placeholder = ""
        self.validator   = None

    def text(self) -> str:
        """Returns the text."""

        return self.text_value

    def setText(self, text: str) -> None:
        """Sets the text without validation, as QLineEdit.setText."""

        self.text_value = str(text)

    def setValidator(self, validator: QtRegExpValidator) -> None:
        """Sets the validator."""

        self.validator = validator

    def placeholderText(self) -> str:
        """Returns the placeholder text."""

        return self.placeholder

    def setPlaceholderText(self, text: str) -> None:
        """Sets the placeholder text."""

        self.placeholder = text


class QtTabWidget(QtWidget):
    """A QTabWidget.

    Attributes:
        titles         : Tab titles in order.
        index          : Current tab index.
        currentChanged : Signal(int) emitted when the current tab changes.
    """

    def __init__(self, boundary: SlotBoundary, name: str) -> None:
        """Creates a tab widget without tabs.

        Args:
            boundary : Slot boundary.
            name     : Attribute name in the window.
        """

        super().__init__(boundary, name)
        self.titles         = []
        self.index          = -1
        self.currentChanged = Signal(self, "currentChanged")

    def addTab(self, title: str) -> int:
        """Appends a tab; the first tab becomes current.

        Returns:
            Index of the new tab.
        """

        self.titles.append(title)
        if self.index < 0:
            self.index = 0
        return len(self.titles) - 1

    def count(self) -> int:
        """Returns the number of tabs."""

        return len(self.titles)

    def tabText(self, index: int) -> str:
        """Returns a tab title."""

        return self.titles[index]

    def currentIndex(self) -> int:
        """Returns the current tab index."""

        return self.index

    def setCurrentIndex(self, index: int) -> None:
        """Selects a tab; emits currentChanged on change.

        Args:
            index : Tab index; out-of-range indices are ignored, as Qt does.
        """

        index = int(index)
        if not 0 <= index < len(self.titles) or index == self.index:
            return
        self.index = index
        self.currentChanged.emit(index)


class QtStackedWidget(QtWidget):
    """A QStackedWidget holding named pages.

    Attributes:
        pages   : Page names in insertion order.
        current : Name of the current page.
    """

    def __init__(self, boundary: SlotBoundary, name: str, pages: list[str]) -> None:
        """Creates the stack with its first page current.

        Args:
            boundary : Slot boundary.
            name     : Attribute name in the window.
            pages    : Page names.
        """

        super().__init__(boundary, name)
        self.pages   = list(pages)
        self.current = self.pages[0]

    def setCurrentWidget(self, page) -> None:
        """Makes a page current.

        Args:
            page : Page object carrying a ``name`` attribute.
        """

        self.current = page.name

    def currentName(self) -> str:
        """Returns the current page name."""

        return self.current


class QtTimer(QtWidget):
    """A QTimer; the browser delivers its timeouts as tick events.

    Attributes:
        interval_ms : Interval in milliseconds, 0 until started.
        active      : Whether the timer runs.
        timeout     : Signal() emitted on every tick while active.
    """

    def __init__(self, boundary: SlotBoundary, name: str) -> None:
        """Creates a stopped timer.

        Args:
            boundary : Slot boundary.
            name     : Attribute name in the window.
        """

        super().__init__(boundary, name)
        self.interval_ms = 0
        self.active      = False
        self.timeout     = Signal(self, "timeout")

    def start(self, interval: int) -> None:
        """Starts the timer with an interval in milliseconds."""

        self.interval_ms = int(interval)
        self.active      = True

    def stop(self) -> None:
        """Stops the timer."""

        self.active = False

    def isActive(self) -> bool:
        """Returns whether the timer runs."""

        return self.active

    def interval(self) -> int:
        """Returns the interval in milliseconds."""

        return self.interval_ms
