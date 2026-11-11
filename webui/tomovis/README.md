# TomoVis on the server

This package holds the server half of the TomoVis page (`#/tomovis`) and of the TomoVis scripts page
(`#/tomovis_scripts`). TomoVis is DLR's PyQt5 desktop viewer for SAR tomograms
(`../tomovis/Visualizer/visualizer.py`). Its window class is copied here almost line for line. Qt widgets
become headless stand-ins, and the pyqtgraph objects become small state models. The two matplotlib figures
run on matplotlib's WebAgg core. The browser draws everything and reports user actions as Qt operations.
The server runs the copied slots in the original order with the original numpy code.

| File | Content |
|---|---|
| `window.py` | `TomoVisWindow`: the copied `class TomoVis` (`visualizer.py:139-2252`, without the 3D handlers), plus `TomoVisConsole` (stands in for `print`), `DialogQueue` and `WindowOutput` |
| `qt_widgets.py` | Qt stand-ins with Qt's signal order, clamping and decimal rounding. `SlotBoundary` reports a slot exception and lets emission go on, as pyqtgraph's excepthook did |
| `pg_models.py` | ImageView, LineSegmentROI (pyqtgraph's `stateChanged` with QPointF fuzzy compare), InfiniteLine, ColorMap, Point |
| `pg_affine.py` | pyqtgraph 0.14 `affineSlice` and order-1 `interpolateArray` |
| `tools.py` | `normalize`, the 19 `colortables` (verbatim), `sanitize_for_display`, `add_dem_to_tomogram`, the 71 Plot colormap names |
| `rat_file.py` | STEtools RAT 1.0/2.0 read path |
| `cube_readers.py` | read halves of the four imports |
| `session_file.py` | session `.hd5` writer and reader |
| `figure_host.py` | `TomoVisFigure`: Figure + `FigureCanvasWebAggCore` + navigation toolbar + message collector, figure ops, Save |
| `figure_options.py` | `SubplotTool` (SubplotToolQt on stand-in spin boxes), `FigureOptionsEditor` (figure_edit) |
| `exporters.py` | writers for pyqtgraph Export dialog files, the HDF5 exporter and the Matplotlib Window exporter |
| `directory_lister.py` | listing for the file dialog |
| `scripts.py` | server halves of `Scripts/SlicerMatplotlib.py` and `Scripts/VolumeRendering.py` |
| `events.py` | event validation and dispatch, snapshot controls |
| `envelope.py` | TVE1 binary responses |
| `session_store.py` | page sessions (LRU of 4, one lock per page) |

The router is `webui/routers/tomovis_router.py` (`/api/tomovis`).

## Behaviour decisions

- **D-1.** RGB views get per-channel levels through pyqtgraph's `rgba` level mode, one `(lo, hi)` pair
  per channel. The original's `setLevels(list, list)` raises in pyqtgraph 0.14. This fixes E-001, E-002
  and E-004, and E-003 goes away with them.
- **D-2.** hd5 attributes are parsed with the scripts' `parse_h5_attr`, not with `eval`: bytes are
  decoded, strings go through `ast.literal_eval`, and any other value passes through.
- **D-3.** Imports are atomic. A read failure shows the critical message `Import error` /
  `Could not import file:\n<error>` and keeps the previous cube. Files are always closed.
- **D-4.** File dialogs browse the server, and every save writes on the server.
- **D-7.** Every `print` of TomoVis goes to the console log with the prefix `TomoVis: `.
- **matplotlib defaults.** TomoVis ran with matplotlib's default rcParams. In the console, the cube
  explorer's figure archiver changes the global rcParams (300 dpi, serif) whenever it saves. Every
  TomoVis figure operation therefore runs under `matplotlib.style.context("default")`, behind one
  lock (`TomoVisRc` in `figure_host.py`).

Crash fixes (the original printed a traceback and kept a half-applied state):

| Id | Fix |
|---|---|
| E-005 | `nChannels = 3` after a 4-channel cube drops channel 2 |
| E-006 | RAT read: `np.int` -> `int`, `int(x[0])`, `tobytes`, `np.prod` |
| E-007 | Ctrl+F with no data: `chChanged` stops before `displayData` |
| E-008 | D-3 |
| E-009 | Set with a field that is not a number (`-`) does nothing |
| E-011 | X [m] / Plot (profile) / histogram equalization without a tomogram: state changes are kept and the draw is skipped. Plot (profile) does not switch tabs |
| E-012 | A clipped ROI of length zero samples nothing instead of raising `ZeroDivisionError` in `Point.norm` |

## API

Every route is under `/api/tomovis/`. JSON requests use `Content-Type: application/json`. Binary responses
use `application/octet-stream` and are TVE1 envelopes. Errors come back as JSON `{"error": "..."}`, or as
`{"ok": false, "error"}` for the write routes.

| Route | Request | Answer |
|---|---|---|
| POST `session` | `{kind: "window" \| "scripts", webgl2: bool}` | envelope `{sid, snapshot}` (`snapshot` is null for scripts); 400 for a bad kind |
| POST `close` | `{sid}` | `{ok: true}` |
| POST `event` | `{sid, seq, event}` | envelope, header below; 404 unknown session, 400 invalid event, 409 stale dialog token |
| POST `figure` | `{sid, seq, figure, op, ...}` | envelope `{seq, figure, messages, result, dialogs}`; 404 unknown figure |
| GET `tables` | | `{colortables: {names[19], tables[19][256][3], default: 9, blue_red_yellow: 4}, plot_colormaps: {names[71], default: "jet"}}` |
| GET `volume?sid=&serial=` | | envelope `{serial, shape, dtype: "float32"}` with blob `volume`; 404 for a stale serial |
| GET `metadata?sid=` | | `getCurrentMetadata()` |
| GET `fs?path=&pattern=*.npy&pattern=...` | empty path means home | `{ok, path, parent, home, entries: [{name, dir, size, mtime}]}`; 400 `{ok: false, error}` |
| POST `write?sid=&path=&kind=image\|bytes` | body `image/png` or `application/octet-stream` | `{ok, path}`; 400 `{ok: false, error}` (unknown image extension, missing directory, relative path) |
| POST `export_hdf5` | `{sid, path, name, column_mode, curves: [{x, y, name?}]}` | `{ok, path}` |
| POST `log` | `{sid, lines: [str]}` | `{ok: true}` |
| POST `script/slicer` | `{sid, path}` (scripts session) | envelope `{figure: "script_slicer", messages, printed}`; 400 `{error}` with the script's message |
| GET `script/volume?sid=&path=` | scripts session | envelope `{shape, z_range, ps_az, ps_rg, resolution, printed}`, blobs `volume_1`, `volume_2` (float32) |

### Envelope

```
"TVE1" | uint32 LE J | J bytes JSON | zero pad to 8 | blob 0 | pad to 8 | blob 1 | ...
header.blobs = [{name, kind: "array" | "png", dtype: "float32" | "uint8" | null, shape, offset, nbytes}]
```

The arrays are C order, little endian, exactly as the server holds them: a top view `(N1, N2)` arrives as
`(N1, N2)`, and pyqtgraph's column-major display is the browser's job.

### Window events

| `type` | Fields | Effect |
|---|---|---|
| `sync` | | none; the next answer carries every current image |
| `trigger` | `widget`: action name | menu click; runs only when the action and its parent menus are enabled |
| `shortcut` | `keys`: `Ctrl+O` / `Ctrl+S` / `Ctrl+F` | the action's shortcut (ignored while the action is disabled; Ctrl+F works with the Channel menu disabled) |
| `click` | `widget`: push button | `click()` (no-op while disabled) |
| `check` | `widget`, `checked` | check box click toward `checked` |
| `value` | `widget`, `value` | `setValue` (Qt clamps; `tab2SpinBox` rounds to 2 decimals) |
| `index` | `widget`, `index` | combo `setCurrentIndex` |
| `text` | `widget`, `text` | ROI field `setText` unless the validator says Invalid |
| `tab` | `index` | `tabWidget.setCurrentIndex` |
| `roi` | `state: {pos, size, angle, handles: [{pos, item}] x2}`, `free_handle_moved`, `finish` | stores pyqtgraph's ROI state, then `stateChanged(finish)` |
| `tick` | | one `tab1Timer` timeout while the timer is active |
| `dialog_result` | `token`, `accepted`, `path` (file) or `values` (axes) | the dialog's continuation; a cancel runs nothing |

Widget names: actions `openFile saveFile openFUSAR openRAT openUAVSAR openNpy allChMenu ch1Menu ch2Menu
ch3Menu`; buttons `tab1PlayButton tab1SetButton tab1PlotButton tab2AxesButton tab2PlotButton
tab2ClearButton tab3ClearButton`; check boxes `tab1ChkBox tab2ChkBox1..4`; values `tab1Slider tab2Slider
tab1SpinBox tab2SpinBox`; combos `tab1ComboBox tab2ComboBox`; line edits `tab1QLineEdit1..6`. The 3D radios,
3D buttons and the ISO slider belong to the browser; the snapshot reports the server's resets of the ISO
slider.

### Event answer and snapshot

```
{seq, snapshot, views: {imv1_1: "view:imv1_1", ...}, figures: {plot: [Message], profile: [Message]},
 dialogs: [DialogRequest], printed: [str], slot_errors: [{type, message}], blobs}

snapshot = {
  controls:   goldens' state.controls keys; actions add statusTip and checkable; spin boxes add text;
              roi_1 = {view, pos, size, angle, handles: [{pos, item}], serial};
              slice_line = {view, value, visible}; imv1/imv2 = {current}; tab1Timer = {active, interval};
              tabWidget = {index, count, titles}
  views:      {imv1_1 | imv1_2 | imv2_1 | imv2_2: {has_image, image_shape, image_dtype, image_serial,
              apply_serial, colortable, level_mode: "mono" | "rgba", levels: [lo, hi] | [[lo, hi] x 3],
              histogram_range: [mn, mx] (raw; pad by 10 % of the span as pyqtgraph does)}}
  attributes: x_label, x_min, x_max, x_label_view, x_view_min, x_view_max, z_label, z_range, z_view_range,
              x_res, y_res, nChannels, cmap, subplot, roiFlag, tab2_plotted, tab3_plotted,
              volume_rendered, <array>_present/_shape/_dtype
  volume:     {serial, rendered, shape}
  figures:    {plot: {plotted}, profile: {plotted}}
  tab3d_index, pending_dialog
}
```

`apply_serial` changes on every ImageView call that TomoVis makes. The browser then re-applies LUT,
histogram range and levels, and the user's own edits are dropped (Q-020). `roi_1.serial` changes when the
server moves the ROI (Set, session restore).

### Dialog requests

```
{kind: "message", level: "information" | "warning" | "critical", title, text}
{kind: "file", token, mode: "open" | "save", title, filters: ["Numpy (*.npy)"], selected_filter, directory: null, file: null}
{kind: "axes", token, title: "Axes Settings", values: {x_label, z_label, x_min, x_max, z_min, z_max}, decimals: 6, range: [-1e9, 1e9], step: 1.0}
```

The answer is `{type: "dialog_result", token, accepted, path}` or `{..., values}`. The server pushes the
Axes values through 6-decimal spin boxes, as Qt does. Keys missing from `values` keep the dialog's
initial values.

### Figure operations (`POST figure`)

The figures are `plot` and `profile` (window sessions), `export` (Matplotlib Window) and `script_slicer`
(scripts sessions).

| `op` | Fields | `result` |
|---|---|---|
| `resize` | `width`, `height` (CSS px), `dpr` | null; dpi = 100 x dpr, pixels = CSS x dpr, full frame |
| `mouse` | `event: {type, x, y, button, buttons, modifiers, step}` as mpl.js sends it (device px from the top-left) | null |
| `key` | `event: {type: key_press \| key_release, key}` (mpl.js key strings: `"k" + key` with `ctrl+`, `alt+`, `shift+` prefixes) | null |
| `toolbar` | `name`: home, back, forward, pan, zoom | null |
| `refresh` | | null; full frame, history buttons and navigate mode |
| `subplots_open` | | SubplotState |
| `subplots_set` | `name`, `value` | SubplotState (live `subplots_adjust` of all six values, Qt's 0.001 gap rule) |
| `subplots_tight` | | SubplotState |
| `subplots_reset` | | SubplotState (the values from when the dialog opened) |
| `subplots_export` | | `{text}` (`top=0.9,\nbottom=0.1,...`) |
| `options_axes` | | `{axes: [{index, title}]}`; with no Axes, `axes` is empty and `dialogs` holds `Error` / `There are no Axes to edit.` |
| `options_form` | `axes` | Form |
| `options_apply` | `axes`, `values` | `{form}`: the Form re-read from the figure (OK and Apply both send this) |
| `save_start` | | `{title: "Choose a filename to save to", directory, file: "image.png", filters, selected_filter}` |
| `save` | `path` | `{ok}`; a failure adds the critical dialog `Error saving file` |
| `export_matplotlib` | `plot` (figure `export` only) | null; builds a new `export` figure |

`SubplotState = {values: {top, bottom, left, right, hspace, wspace}, ranges: {name: [min, max]}, groups:
[{title: "Borders", names: [top, bottom, left, right], buttons: ["Export values"]}, {title: "Spacings",
names: [hspace, wspace], buttons: ["Tight layout", "Reset", "Close"]}]}`. The spin boxes have 3 decimals
and step 0.005.

Form:

```
{title: "Figure options", sections: [
  {title: "Axes", kind: "form", fields: [Field...]},
  {title: "Curves" | "Images, etc.", kind: "combo", pages: [{title, fields: [Field...]}]}]}
Field = {label, kind, value, choices?}
  kind "separator" (label null)       empty row
  kind "comment"   (label null)       value is rich text such as "<b>X-Axis</b>"
  kind "text"                         value str
  kind "color"                        value "#rrggbbaa" (line edit + colour button)
  kind "float"                        value str (repr of the float; Qt's QDoubleValidator in the C locale)
  kind "int"                          value int (spin box, range +-1e9)
  kind "bool"                         value bool (check box)
  kind "choice"                       value = selected index, choices = [label...]
  kind "literal"                      value str (Python literal)
values = one entry per section: for "form" a list with one value per field other than separator and
comment, in order; for "combo" a list of such lists, one per page. A choice is answered with its index.
```

`export_matplotlib`'s `plot`: `{curves: [{x, y, pen: {color: [r, g, b, a] (0..1), width, style: "solid" |
"none"}, symbol (pyqtgraph name or null), symbolSize, symbolPen: [r, g, b, a], symbolBrush: [r, g, b, a],
fillLevel?, fillBrush?}], xlabel, ylabel, title, xrange: [lo, hi], yrange: [lo, hi], xscale?, yscale?}`.

Messages, in order: `{type: "image_mode", mode}`, `{type: "frame", blob}` (PNG; diff frames are drawn
over the last frame), `{type: "message", message}` (cursor readout, can contain `\n`),
`{type: "cursor", cursor}`, `{type: "rubberband", x0, y0, x1, y1}` (device px, origin at the bottom left,
all -1 to remove), `{type: "history_buttons", Back, Forward}`, `{type: "navigate_mode", mode}`,
`{type: "resize", size, forward}`, `{type: "figure_label", label}`. matplotlib's `draw` and `refresh`
requests are answered on the server.
