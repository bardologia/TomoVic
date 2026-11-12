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
| `qt_image_writer.py` | `QImage.save` for the 16 image formats QImageWriter offered (Qt 5.15.15): its PBM/PGM/XBM/XPM/WBMP/ICO/ICNS writers, mono dithering and smooth scaling, and Pillow with Qt's settings for BMP, JPEG, PPM, TIFF and WebP |
| `directory_lister.py` | listing for the file dialog with Qt's Type column and the Computer place, Create New Folder and the in-place rename |
| `scripts.py` | server halves of `Scripts/SlicerMatplotlib.py` and `Scripts/VolumeRendering.py` |
| `events.py` | event validation and dispatch, snapshot controls |
| `envelope.py` | TVE1 binary responses |
| `session_store.py` | page sessions, each kept until its page closes it or stops sending heartbeats; one lock per page |

The router is `webui/routers/tomovis_router.py` (`/api/tomovis`).

## Behaviour decisions

- **D-1.** RGB views get per-channel levels through pyqtgraph's `rgba` level mode, one `(lo, hi)` pair
  per channel. The original's `setLevels(list, list)` raises in pyqtgraph 0.14. This fixes E-001, E-002
  and E-004, and E-003 goes away with them.
- **D-2.** hd5 attributes are parsed with the scripts' `parse_h5_attr`, not with `eval`: bytes are
  decoded, strings go through `ast.literal_eval`, and any other value passes through.
- **D-3.** Imports are atomic. A read failure shows the critical message `Import error` /
  `Could not import file:\n<error>` and keeps the previous cube. Files are always closed.
- **D-4.** File dialogs browse the server, and every save writes on the server. As Qt's file dialog does
  within one run of TomoVis, a dialog opened without a folder of its own starts in the last folder any
  dialog of the page browsed to, also when that dialog was cancelled or its save failed. The first dialog
  of a page starts in the server user's home folder, where the original starts in the folder TomoVis was
  launched from. A reload starts over, as a new start of TomoVis does. The dialog is Qt's non-native
  QFileDialog at its 645x436 size: a Look in drop-down (the folder, its ancestors, Computer, then Recent
  Places), Back, Forward, Parent Directory, Create New Folder (`New Folder`, `New Folder2`, ... renamed in
  place), List View and Detail View, the Computer and home places, and the columns Name, Size, Type and
  Date Modified (`M/d/yy h:mm AP`). Recent Places and the view mode live in the browser's `localStorage`
  and are written when a dialog closes. Qt keeps them in `QtProject.conf` and writes them when a dialog is
  destroyed, which for TomoVis's four import dialogs happens only when the window closes, because they
  stay alive as children of the window. Not carried over: the list's right-click menu (Rename, Delete,
  Show hidden files, New Folder), resizing the columns and the sidebar, file name completion, and
  bookmarking folders by dragging them onto the sidebar.
- **D-7.** Every `print` of TomoVis goes to the console log with the prefix `TomoVis: `. The startup 3D check
  that `visualizer.py` prints when it is imported is printed once per window session: the browser's WebGL2
  probe stands in for `has_usable_opengl()`, so the line is `OpenGL context OK, version=(2, 0), profile=0`
  when a WebGL2 context (version 2.0, no profiles) can be created and `QOpenGLContext.create() failed` when
  it cannot, in which case the 3D tab is left out as F-090 says. Lines the browser
  posts to `log` keep vispy's level: `ERROR: ...` lines are logged at error, `WARNING: ...` at warning, the
  rest at info (`TomoVisConsole.relay`). A browser-side vispy callback error is logged as vispy's
  `_handle_exception` logs it: one multi-line `WARNING: Traceback (most recent call last): ...` entry, then
  `ERROR: Invoking <callback> for <EventClass>`. The fly camera's timer keeps vispy's "reminders" policy:
  later failures log only `ERROR: Invoking FlyCamera.on_timer repeat <n>` when n is a power of two. A
  failing scene mouse callback is logged as `SceneCanvas._process_mouse_event for MouseEvent` after a
  chained `TypeError: SceneMouseEvent type '<type>' has no scale`, because vispy 0.17 raises while it builds
  the registry key from `repr(event)`; the rest of that mouse event's processing is skipped, as there.
- **D-8.** A TomoVis window keeps its state until it is closed, however many other windows open. Each
  page holds one session on the server and sends a heartbeat every 60 s, also while the tab is hidden.
  The session ends when the page closes (its `pagehide` beacon) or when the page has sent nothing for
  20 minutes, which only happens when the tab crashed, was killed, or was frozen by the browser that long.
  A request on a dropped session opens a fresh window with the warning
  `TomoVis session expired; a new window was opened.`
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
| E-010 | Normalization on an RGB (uint8) pane: pyqtgraph 0.14's `ImageView.normalize` keeps a uint8 copy for Subtract, so Subtract with Frame, Time range or ROI raised `UFuncTypeError: Cannot cast ufunc 'subtract' output from dtype('float64') to dtype('uint8')` and left the pane unchanged. `PgImageView.normalize` (`tomovis_pg_imageview.js`) computes every mode except Off in float32, so these combinations work and the levels follow each channel. The only other effect: Subtract with no mean source ticked returns float32 instead of uint8, with the same values. Divide was float32 in both already |
| E-011 | X [m] / Plot (profile) / histogram equalization without a tomogram: state changes are kept and the draw is skipped. Plot (profile) does not switch tabs; in the mono branch it leaves the empty 0..1 axes the original's `add_subplot(111)` created, which renders when the Profile tab is first shown (a figure renders on its tab's first show, as a Qt canvas does on its first resize event) |
| E-012 | A clipped ROI of length zero samples nothing instead of raising `ZeroDivisionError` in `Point.norm` |

Known divergences from the original, kept on purpose or not verifiable here:

| F-ids | Divergence |
|---|---|
| F-001, F-008, F-009, F-069, F-132, F-133, F-134 | Colours and fonts, kept on purpose so the window fits inside TomoVic. The window, its menus, popups and dialogs use TomoVic's dark palette and accent (the dark frost panel, light text, the lavender highlight with dark text, toolbar icons inverted to light), not Qt Fusion's light palette (window `#efefef`, white panes, black text, the `#308cc6` highlight with white text, black icons). The font families are TomoVic's: Archivo for text, and JetBrains Mono for line edits, spin boxes, the status line, menu shortcuts and the Matplotlib cursor readout. The original sets `QFont('Serif', 10, QFont.ExtraLight)` on the window (Noto Serif on the test machine, which has no ExtraLight face, so it renders at regular weight) and draws menus, popups, combo boxes, message boxes and dialogs, which do not inherit the window font, in the application font (Noto Sans 12 pt). The text sizes are Qt's: 14 px for the window's labels, buttons, check boxes, tabs, menu bar, status line, line edits, spin boxes and cursor readout, and 17 px for combo boxes and their popups, menus, message boxes, every dialog and the Matplotlib windows (the sizes Qt gives 10 pt and 12 pt on the test machine). TomoVic loads both families only from weight 600 up, so text that Qt draws at regular weight shows at 600, and the texts Qt draws bold (the pyqtgraph Normalization labels and Export parameter groups) at 700. Widget and dialog geometry, spacing, layout, states and behaviour follow the original; where Qt sizes a widget by its text (tab and menu bar widths, the Slicer row labels, combo box and spin box widths, list widths), the size is measured with Qt's fonts, and text that is elided or wrapped breaks where TomoVic's fonts put it |
| F-061, F-062, F-081, F-082, F-133, F-134, F-150 | matplotlib version. The console's Dune environment, shared with DLR-TomoSAR and kept as it is, has matplotlib 3.10.8 with FreeType 2.6.1; the original's `tomovis` environment has matplotlib 3.11.2 with FreeType 2.14.3. The figure code, data and layout are the same: replaying the original's own `plotTomogram` calls on its `d2Norm` gives a canvas pixel-identical to the original under 3.11.2 and pixel-identical to the port under 3.10.8. What changes is drawing: glyph edges in tick labels, axis labels, titles and colorbar text rasterise 1 to 2 px differently, image resampling differs by up to 29 levels on about 9 % of the image pixels (mostly 1 or 2 levels), Tight layout from a fresh Plot gives hspace 0.307 instead of 0.310, and the Colormap list on the Images, etc. page of Figure options has 180 entries instead of 182, without `okabe_ito` and `okabe_ito_r`, which are new in 3.11. The 71-name Plot colormap combo is not affected |
| F-135 | Save as AVIF (`*.avif` in the Matplotlib save dialog) writes the file in the port, because the Dune environment's Pillow 12.1.1 has the AVIF plugin. In the original's `tomovis` environment Pillow 13.0.0 has no AVIF plugin, so matplotlib raises `The installed pillow version does not support avif. Full avif support has been added in pillow 11.3.` and the toolbar shows `Error saving file`. The original's `print_avif` is copied unchanged; only the Pillow build differs, and TomoVis does not pin Pillow, so a fresh install of the original could do either |
| F-153 | The traceback before a vispy callback error lists the browser's JavaScript frames (V8's `at ...` lines, at most `Error.stackTraceLimit` of them, most recent last) and its final `<Type>: <message>` line, not Python frames. vispy's `<< caught exception here: >>` caller stack is not reproduced. The callback is named `<Class>.<method>` (`FlyCamera.on_timer`), not by the bound method's repr, which carried a memory address. Key and mouse callback errors are logged in full every time. In Qt their events' reprs include the native Qt event object and the pointer position, so vispy's reminders registry seldom sees the same key twice for them, but it could when an event repeats a position and Python reuses a wrapper's address |
| F-113, F-120 | Image exports have the pixels of Qt's files, but not always its bytes. TIFF carries Pillow's tags, not libtiff's: Qt writes an Orientation tag and a 4 MB RowsPerStrip and puts the strip before the IFD. The PNG inside an ICNS comes from Pillow, not libpng. ICO and CUR write zeros in the AND-mask alignment padding, which Qt leaves uninitialised. In scaled ICO and ICNS, translucent pixels can differ by 1, because Qt's SSE4.1 unpremultiply uses the CPU's `rcpps` approximation and the port the scalar `qUnpremultiply` |
| F-009, F-010, F-020 | The browser has no window manager, so every dialog draws its own title bar above Qt's client area, and the window behind a modal dialog is dimmed with TomoVic's scrim colour (Qt dims nothing; clicks on the window are refused either way). Message boxes follow `QMessageBox::updateSize`: 11 px margins, the 32 px icon, the label at x = 62, buttons 80 x 32; the box is as wide as its widest line, and a box that would be wider than half the screen (at most 500 px) wraps its text at that width, after spaces, hyphens and `/` as Qt's line breaker does; a title wider than the box widens it. The screen is `window.screen.availWidth`, so the same text wraps at 400 px on the original's 800 px offscreen screen and at 500 px on a desktop, in both. The text uses the window font (see the colours and fonts row), so line breaks fall where that font puts them |
| F-003, F-004, F-007 | On macOS Qt maps Ctrl+O, Ctrl+S and Ctrl+F to Cmd. `tomovis_page.js` accepts `metaKey` for the three shortcuts, but this has not been run on a Mac |

## API

Every route is under `/api/tomovis/`. JSON requests use `Content-Type: application/json`. Binary responses
use `application/octet-stream` and are TVE1 envelopes. Errors come back as JSON `{"error": "..."}`, or as
`{"ok": false, "error"}` for the write routes.

| Route | Request | Answer |
|---|---|---|
| POST `session` | `{kind: "window" \| "scripts", webgl2: bool}` | envelope `{sid, snapshot}` (`snapshot` is null for scripts); 400 for a bad kind |
| POST `close` | `{sid}` | `{ok: true}` |
| POST `alive` | `{sid}` (the page's heartbeat, sent with `sendBeacon` every 60 s) | `{ok: true}`; 404 unknown session |
| POST `event` | `{sid, seq, event}` | envelope, header below; 404 unknown session, 400 invalid event, 409 stale dialog token |
| POST `figure` | `{sid, seq, figure, op, ...}` | envelope `{seq, figure, messages, result, dialogs}`; 404 unknown figure |
| GET `tables` | | `{colortables: {names[19], tables[19][256][3], default: 9, blue_red_yellow: 4}, plot_colormaps: {names[71], default: "jet"}}` |
| GET `volume?sid=&serial=` | | envelope `{serial, shape, dtype: "float32"}` with blob `volume`; 404 for a stale serial |
| GET `metadata?sid=` | | `getCurrentMetadata()` |
| GET `fs?path=&pattern=*.npy&pattern=...` | empty path means home | `{ok, path, computer: false, parent, home, writable, entries: [{name, dir, size, mtime, type}]}` (`parent` is `""`, meaning Computer, for `/`); `{ok: false, error}` for a folder that is missing or cannot be read; 400 for a relative path |
| GET `computer` | | the Computer place: `{ok, path: null, computer: true, parent: null, home, writable: false, entries: [/ as a "Drive"]}` |
| POST `mkdir` | `{sid, path}` | `{ok, name, entry}` with the first free name of `New Folder`, `New Folder2`, ...; `{ok: false, error}` when it cannot be made |
| POST `rename` | `{sid, path, old, new}` | `{ok, entry}`; `{ok: false, title: "Invalid filename", text}` (QFileSystemModel's rich text) for an empty, taken or invalid name |
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

The figures are `plot` and `profile` (window sessions), `export:<n>` (one per Matplotlib Window, numbered by
the browser) and `script_slicer` (scripts sessions).

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
| `export_matplotlib` | `plot` (figures `export:<n>` only) | null; builds a new figure under that id |
| `export_close` | (figures `export:<n>` only) | answers `{ok: true}` as JSON and drops the figure when its window closes |

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
