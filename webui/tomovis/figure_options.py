"""The matplotlib Qt toolbar's Configure subplots and Figure options dialogs, minus the Qt widgets.

``SubplotTool`` is matplotlib 3.11.2's ``SubplotToolQt`` with its six
QDoubleSpinBoxes replaced by the headless stand-ins, so ranges, the 0.001 gap
rule, 3-decimal rounding and the live ``subplots_adjust`` behave exactly as in
the Qt dialog; the browser draws the dialog from its state.

``FigureOptionsEditor`` is ``qt_editor.figureoptions.figure_edit`` (3.11.2):
the Axes chooser of ``NavigationToolbar2QT.edit_parameters``, the data lists
of the form, and ``apply_callback``. The form is serialised with the field
kinds ``_formlayout.FormWidget.setup`` infers, and the values the browser
returns are converted the way ``FormWidget.get`` reads its widgets.
"""

from __future__ import annotations

import datetime
from ast       import literal_eval
from itertools import chain
from numbers   import Integral, Real

from matplotlib       import cm, colors as mcolors, image as mimage, markers
from matplotlib.dates import DateConverter, num2date
from matplotlib.figure import Figure

from tomovis.events     import TomoVisEventError
from tomovis.qt_widgets import QtDoubleSpinBox, SlotBoundary
from web_logger         import WebLogger


class SubplotTool:
    """SubplotToolQt on headless spin boxes.

    Attributes:
        GROUPS     : (group title, spin box names, button texts) in dialog order.
        figure     : Target figure.
        logger     : Console logger for exceptions in the live update.
        boundary   : Slot boundary of the spin boxes.
        spinboxes  : Name to QtDoubleSpinBox, in the order top, bottom, left, right, hspace, wspace.
        defaults   : Name to the subplot parameter value when the dialog was opened (Reset target).
    """

    GROUPS = [("Borders", ["top", "bottom", "left", "right"], ["Export values"]), ("Spacings", ["hspace", "wspace"], ["Tight layout", "Reset", "Close"])]

    def __init__(self, figure: Figure, logger: WebLogger) -> None:
        """Builds the six spin boxes as SubplotToolQt.__init__ and reads the current parameters.

        Args:
            figure : Target figure.
            logger : Console logger.
        """

        self.figure    = figure
        self.logger    = logger
        self.boundary  = SlotBoundary(self.report)
        self.spinboxes = {}
        self.defaults  = {}

        for _, names, _ in self.GROUPS:
            for name in names:
                self.spinboxes[name] = spinbox = QtDoubleSpinBox(self.boundary, name)
                spinbox.setRange(0, 1)
                spinbox.setDecimals(3)
                spinbox.setSingleStep(0.005)
                spinbox.valueChanged.connect(self._on_value_changed)

        self.update_from_current_subplotpars()

    def report(self, exc: Exception, text: str) -> None:
        """Logs an exception of the live update, as Qt's excepthook would print it."""

        self.logger.error("TomoVis: " + text.rstrip())

    def update_from_current_subplotpars(self) -> None:
        """Takes the figure's current parameters as the Reset values and shows them."""

        self.defaults = {name: getattr(self.figure.subplotpars, name) for name in self.spinboxes}
        self._reset()

    def _export_values(self) -> str:
        """Returns the Export values text, each value rounded to 3 significant digits."""

        return ",\n".join(f"{attr}={spinbox.value():.3}" for attr, spinbox in self.spinboxes.items())

    def _on_value_changed(self) -> None:
        """Re-applies the bottom<top and left<right gaps and all six parameters to the figure."""

        spinboxes = self.spinboxes
        for lower, higher in [("bottom", "top"), ("left", "right")]:
            spinboxes[higher].setMinimum(spinboxes[lower].value() + .001)
            spinboxes[lower].setMaximum(spinboxes[higher].value() - .001)
        self.figure.subplots_adjust(**{attr: spinbox.value() for attr, spinbox in spinboxes.items()})
        self.figure.canvas.draw_idle()

    def _tight_layout(self) -> None:
        """Runs tight_layout and shows the resulting parameters without re-applying them."""

        self.figure.tight_layout()
        for attr, spinbox in self.spinboxes.items():
            spinbox.blockSignals(True)
            spinbox.setValue(getattr(self.figure.subplotpars, attr))
            spinbox.blockSignals(False)
        self.figure.canvas.draw_idle()

    def _reset(self) -> None:
        """Restores the values the dialog opened with, then applies them."""

        for name, value in self.defaults.items():
            spinbox = self.spinboxes[name]
            spinbox.setRange(0, 1)
            spinbox.blockSignals(True)
            spinbox.setValue(value)
            spinbox.blockSignals(False)
        self._on_value_changed()

    def setValue(self, name: str, value: float) -> None:
        """Commits one spin box value as the user typed or stepped it.

        Args:
            name  : Spin box name.
            value : New value; the spin box rounds and clamps it.

        Raises:
            TomoVisEventError : For an unknown name.
        """

        if name not in self.spinboxes:
            raise TomoVisEventError(f"unknown subplot parameter '{name}'")
        self.spinboxes[name].setValue(float(value))

    def state(self) -> dict:
        """Returns what the dialog shows.

        Returns:
            {"values": name to value, "ranges": name to [minimum, maximum], "groups": GROUPS}.
        """

        return {
            "values" : {name: spinbox.value() for name, spinbox in self.spinboxes.items()},
            "ranges" : {name: [spinbox.minimum(), spinbox.maximum()] for name, spinbox in self.spinboxes.items()},
            "groups" : [{"title": title, "names": names, "buttons": buttons} for title, names, buttons in self.GROUPS],
        }


class FigureOptionsForm:
    """One open Figure options dialog: the data lists for one Axes and its apply callback.

    Attributes:
        LINESTYLES        : Line style shorthand to name.
        DRAWSTYLES        : Draw style shorthand to name.
        MARKERS           : Marker shorthand to name.
        BLACKLIST         : Field labels never shown as colour fields.
        axes              : The edited Axes.
        axis_map          : Axis name to Axis.
        axis_converter    : Axis name to its unit converter.
        axis_units        : Axis name to its units.
        labeled_lines     : (label, Line2D) of the editable curves.
        labeled_mappables : (label, mappable) of the editable images.
        has_curve         : Whether a Curves tab exists.
        has_sm            : Whether an Images tab exists.
        datalist          : The fedit data group (Axes, Curves, Images, etc.).
        choice_keys       : Per choice field (in serialisation order) the list of option keys.
    """

    LINESTYLES = {'-': 'Solid', '--': 'Dashed', '-.': 'DashDot', ':': 'Dotted', 'None': 'None'}
    DRAWSTYLES = {'default': 'Default', 'steps-pre': 'Steps (Pre)', 'steps': 'Steps (Pre)', 'steps-mid': 'Steps (Mid)', 'steps-post': 'Steps (Post)'}
    MARKERS    = markers.MarkerStyle.markers
    BLACKLIST  = {"title", "label"}

    def __init__(self, axes) -> None:
        """Builds the data lists exactly as figure_edit does.

        Args:
            axes : The Axes to edit.
        """

        self.axes = axes
        sep       = (None, None)

        def convert_limits(lim, converter):
            if isinstance(converter, DateConverter):
                return map(num2date, lim)
            return map(float, lim)

        axis_map    = axes._axis_map
        axis_limits = {name: tuple(convert_limits(getattr(axes, f'get_{name}lim')(), axis.get_converter())) for name, axis in axis_map.items()}
        general     = [
            ('Title', axes.get_title()),
            sep,
            *chain.from_iterable([
                (
                    (None, f"<b>{name.title()}-Axis</b>"),
                    ('Min', axis_limits[name][0]),
                    ('Max', axis_limits[name][1]),
                    ('Label', axis.label.get_text()),
                    ('Scale', [axis.get_scale(), 'linear', 'log', 'symlog', 'logit']),
                    sep,
                )
                for name, axis in axis_map.items()
            ]),
            ('(Re-)Generate automatic legend', False),
        ]

        self.axis_map       = axis_map
        self.axis_converter = {name: axis.get_converter() for name, axis in axis_map.items()}
        self.axis_units     = {name: axis.get_units() for name, axis in axis_map.items()}

        labeled_lines = []
        for line in axes.get_lines():
            label = line.get_label()
            if label == '_nolegend_':
                continue
            labeled_lines.append((label, line))
        curves = []

        for label, line in labeled_lines:
            color     = mcolors.to_hex(mcolors.to_rgba(line.get_color(), line.get_alpha()), keep_alpha=True)
            ec        = mcolors.to_hex(mcolors.to_rgba(line.get_markeredgecolor(), line.get_alpha()), keep_alpha=True)
            fc        = mcolors.to_hex(mcolors.to_rgba(line.get_markerfacecolor(), line.get_alpha()), keep_alpha=True)
            curvedata = [
                ('Label', label),
                sep,
                (None, '<b>Line</b>'),
                ('Line style', self.prepare_data(self.LINESTYLES, line.get_linestyle())),
                ('Draw style', self.prepare_data(self.DRAWSTYLES, line.get_drawstyle())),
                ('Width', line.get_linewidth()),
                ('Color (RGBA)', color),
                sep,
                (None, '<b>Marker</b>'),
                ('Style', self.prepare_data(self.MARKERS, line.get_marker())),
                ('Size', line.get_markersize()),
                ('Face color (RGBA)', fc),
                ('Edge color (RGBA)', ec)]
            curves.append([curvedata, label, ""])

        labeled_mappables = []
        for mappable in [*axes.images, *axes.collections]:
            label = mappable.get_label()
            if label == '_nolegend_' or mappable.get_array() is None:
                continue
            labeled_mappables.append((label, mappable))
        mappables = []
        cmaps     = [(cmap, name) for name, cmap in sorted(cm._colormaps.items())]
        for label, mappable in labeled_mappables:
            cmap = mappable.get_cmap()
            if cmap.name not in cm._colormaps:
                cmaps = [(cmap, cmap.name), *cmaps]
            low, high    = mappable.get_clim()
            mappabledata = [
                ('Label', label),
                ('Colormap', [cmap.name] + cmaps),
                ('Min. value', low),
                ('Max. value', high),
            ]
            if hasattr(mappable, "get_interpolation"):
                interpolations = [(name, name) for name in sorted(mimage.interpolations_names)]
                mappabledata.append(('Interpolation', [mappable.get_interpolation(), *interpolations]))

                interpolation_stages = ['data', 'rgba', 'auto']
                mappabledata.append(('Interpolation stage', [mappable.get_interpolation_stage(), *interpolation_stages]))

            mappables.append([mappabledata, label, ""])

        self.labeled_lines     = labeled_lines
        self.labeled_mappables = labeled_mappables
        self.has_curve         = bool(curves)
        self.has_sm            = bool(mappables)

        self.datalist = [(general, "Axes", "")]
        if curves:
            self.datalist.append((curves, "Curves", ""))
        if mappables:
            self.datalist.append((mappables, "Images, etc.", ""))

        self.choice_keys = []

    @staticmethod
    def prepare_data(d: dict, init) -> list:
        """Builds a combo entry [initial shorthand, (shorthand, name), ...] sorted by name (figure_edit.prepare_data)."""

        if init not in d:
            d = {**d, init: str(init)}
        name2short     = {name: short for short, name in d.items()}
        short2name     = {short: name for name, short in name2short.items()}
        canonical_init = name2short[d[init]]
        return ([canonical_init] + sorted(short2name.items(), key=lambda short_and_name: short_and_name[1]))

    def serialiseField(self, label, value) -> dict:
        """Serialises one form row with the widget kind FormWidget.setup would build.

        Args:
            label : Row label, None for separators and comments.
            value : Row value.

        Returns:
            Field dict {label, kind, value, choices?}.
        """

        if label is None and value is None:
            return {"label": None, "kind": "separator", "value": None}
        if label is None:
            return {"label": None, "kind": "comment", "value": value}
        if label.lower() not in self.BLACKLIST and mcolors.is_color_like(value):
            return {"label": label, "kind": "color", "value": mcolors.to_hex(mcolors.to_rgba(value), keep_alpha=True)}
        if isinstance(value, str):
            return {"label": label, "kind": "text", "value": value}
        if isinstance(value, (list, tuple)):
            value    = list(value)
            selindex = value.pop(0)
            if isinstance(value[0], (list, tuple)):
                keys   = [key for key, _val in value]
                labels = [val for _key, val in value]
            else:
                keys   = value
                labels = value
            if selindex in labels:
                selected = labels.index(selindex)
            elif selindex in keys:
                selected = keys.index(selindex)
            elif isinstance(selindex, Integral):
                selected = int(selindex)
            else:
                selected = 0
            self.choice_keys.append(keys)
            return {"label": label, "kind": "choice", "value": selected, "choices": [str(item) for item in labels]}
        if isinstance(value, bool):
            return {"label": label, "kind": "bool", "value": value}
        if isinstance(value, Integral):
            return {"label": label, "kind": "int", "value": int(value)}
        if isinstance(value, Real):
            return {"label": label, "kind": "float", "value": repr(float(value))}
        if isinstance(value, (datetime.datetime, datetime.date)):
            return {"label": label, "kind": "text", "value": value.isoformat()}
        return {"label": label, "kind": "literal", "value": repr(value)}

    def serialiseFields(self, data: list) -> list[dict]:
        """Serialises one FormWidget's rows."""

        return [self.serialiseField(label, value) for label, value in data]

    def serialise(self) -> dict:
        """Serialises the whole dialog: one tab per data group, a combo of pages for Curves and Images.

        Returns:
            {"title": "Figure options", "sections": [{"title", "kind": "form", "fields"} or {"title", "kind": "combo", "pages": [{"title", "fields"}]}]}.
        """

        self.choice_keys = []
        sections         = []
        for data, title, _ in self.datalist:
            if len(data[0]) == 3:
                sections.append({"title": title, "kind": "combo", "pages": [{"title": page_title, "fields": self.serialiseFields(page)} for page, page_title, _ in data]})
            else:
                sections.append({"title": title, "kind": "form", "fields": self.serialiseFields(data)})
        return {"title": "Figure options", "sections": sections}

    def readFields(self, data: list, values: list, choices) -> list:
        """Converts the browser's values of one FormWidget as FormWidget.get reads its widgets.

        Args:
            data    : The FormWidget's (label, value) rows.
            values  : One value per non-separator, non-comment row, in order.
            choices : Iterator over choice_keys in serialisation order.

        Returns:
            The value list apply_callback expects.

        Raises:
            TomoVisEventError : If the number of values does not match the rows.
        """

        rows = [(label, value) for label, value in data if label is not None]
        if len(rows) != len(values):
            raise TomoVisEventError("the figure options values do not match the form")

        read = []
        for (label, value), entry in zip(rows, values):
            if label.lower() not in self.BLACKLIST and mcolors.is_color_like(value):
                read.append(str(entry))
            elif isinstance(value, str):
                read.append(str(entry))
            elif isinstance(value, (list, tuple)):
                read.append(next(choices)[int(entry)])
            elif isinstance(value, bool):
                read.append(bool(entry))
            elif isinstance(value, Integral):
                read.append(int(entry))
            elif isinstance(value, Real):
                read.append(float(str(entry)))
            else:
                read.append(literal_eval(str(entry)))
        return read

    def read(self, values: list) -> list:
        """Converts the browser's value tree into fedit's data list.

        Args:
            values : One entry per section: a value list for a form, a list of value lists for a combo.

        Returns:
            The data argument of apply_callback.
        """

        self.serialise()
        choices = iter(self.choice_keys)
        data    = []
        for (group, _, _), section in zip(self.datalist, values):
            if len(group[0]) == 3:
                data.append([self.readFields(page, page_values, choices) for (page, _, _), page_values in zip(group, section)])
            else:
                data.append(self.readFields(group, section, choices))
        return data

    def apply_callback(self, data: list) -> None:
        """Applies the dialog's values (figure_edit.apply_callback, matplotlib 3.11.2)."""

        axes     = self.axes
        axis_map = self.axis_map

        orig_limits = {name: getattr(axes, f"get_{name}lim")() for name in axis_map}

        general   = data.pop(0)
        curves    = data.pop(0) if self.has_curve else []
        mappables = data.pop(0) if self.has_sm else []
        if data:
            raise ValueError("Unexpected field")

        title = general.pop(0)
        axes.title.set_text(title)
        generate_legend = general.pop()

        for i, (name, axis) in enumerate(axis_map.items()):
            axis_min   = general[4*i]
            axis_max   = general[4*i + 1]
            axis_label = general[4*i + 2]
            axis_scale = general[4*i + 3]
            if axis.get_scale() != axis_scale:
                getattr(axes, f"set_{name}scale")(axis_scale)

            axis._set_lim(axis_min, axis_max, auto=False)
            axis.set_label_text(axis_label)

            axis._set_converter(self.axis_converter[name])
            axis.set_units(self.axis_units[name])

        for index, curve in enumerate(curves):
            line = self.labeled_lines[index][1]
            (label, linestyle, drawstyle, linewidth, color, marker, markersize, markerfacecolor, markeredgecolor) = curve
            line.set_label(label)
            line.set_linestyle(linestyle)
            line.set_drawstyle(drawstyle)
            line.set_linewidth(linewidth)
            rgba = mcolors.to_rgba(color)
            line.set_alpha(None)
            line.set_color(rgba)
            if marker != 'none':
                line.set_marker(marker)
                line.set_markersize(markersize)
                line.set_markerfacecolor(markerfacecolor)
                line.set_markeredgecolor(markeredgecolor)

        for index, mappable_settings in enumerate(mappables):
            mappable = self.labeled_mappables[index][1]
            if len(mappable_settings) == 6:
                label, cmap, low, high, interpolation, interpolation_stage = mappable_settings
                mappable.set_interpolation(interpolation)
                mappable.set_interpolation_stage(interpolation_stage)
            elif len(mappable_settings) == 4:
                label, cmap, low, high = mappable_settings
            mappable.set_label(label)
            mappable.set_cmap(cmap)
            mappable.set_clim(*sorted([low, high]))

        if generate_legend:
            draggable = None
            ncols     = 1
            if axes.legend_ is not None:
                old_legend = axes.get_legend()
                draggable  = old_legend._draggable is not None
                ncols      = old_legend._ncols
            new_legend = axes.legend(ncols=ncols)
            if new_legend:
                new_legend.set_draggable(draggable)

        figure = axes.get_figure()
        figure.canvas.draw()
        for name in axis_map:
            if getattr(axes, f"get_{name}lim")() != orig_limits[name]:
                figure.canvas.toolbar.push_current()
                break


class FigureOptionsEditor:
    """The Customize entry of the toolbar for one figure.

    Attributes:
        figure : The figure.
        forms  : Axes index to the open FigureOptionsForm.
    """

    def __init__(self, figure: Figure) -> None:
        """Binds the editor to a figure."""

        self.figure = figure
        self.forms  = {}

    def axesChoices(self) -> list[dict] | None:
        """Lists the Axes as the Select Axes chooser names them (NavigationToolbar2QT.edit_parameters).

        Returns:
            [{"index", "title"}], one entry per Axes; None when the figure has no Axes.
        """

        axes = self.figure.get_axes()
        if not axes:
            return None
        titles = [
            ax.get_label() or
            ax.get_title() or
            ax.get_title("left") or
            ax.get_title("right") or
            " - ".join(filter(None, [ax.get_xlabel(), ax.get_ylabel()])) or
            f"<anonymous {type(ax).__name__}>"
            for ax in axes]
        duplicate_titles = [title for title in titles if titles.count(title) > 1]
        for i, ax in enumerate(axes):
            if titles[i] in duplicate_titles:
                titles[i] += f" (id: {id(ax):#x})"
        return [{"index": index, "title": title} for index, title in enumerate(titles)]

    def axesAt(self, index: int):
        """Returns the Axes at an index.

        Raises:
            TomoVisEventError : If the index is out of range.
        """

        axes = self.figure.get_axes()
        if not isinstance(index, int) or isinstance(index, bool) or not 0 <= index < len(axes):
            raise TomoVisEventError(f"the figure has no Axes {index}")
        return axes[index]

    def form(self, index: int) -> dict:
        """Opens the Figure options form for one Axes.

        Args:
            index : Axes index from axesChoices.

        Returns:
            The serialised form.
        """

        self.forms[index] = FigureOptionsForm(self.axesAt(index))
        return self.forms[index].serialise()

    def apply(self, index: int, values: list) -> dict:
        """Applies the dialog's values (OK or Apply) and reopens the form from the new figure state.

        Args:
            index  : Axes index the form was opened for.
            values : Value tree mirroring the form.

        Returns:
            The refreshed serialised form.

        Raises:
            TomoVisEventError : If no form is open for that Axes or the values do not match it.
        """

        if index not in self.forms:
            raise TomoVisEventError(f"no figure options form is open for Axes {index}")
        if not isinstance(values, list):
            raise TomoVisEventError("figure options values must be a list")
        form = self.forms[index]
        form.apply_callback(form.read(values))
        return self.form(index)
