# TomoVis parity goldens

This folder runs the original PyQt5 desktop viewer TomoVis (the `tomovis` repository next to
this one) headless and records what it computes, so the TomoVis page in TomoVic can be tested
against the real thing. Nothing here imports TomoVic code except `webui/web_logger.py`, and
nothing here runs in TomoVic's own environment: the generator needs the `tomovis` conda
environment (PyQt5 5.15, pyqtgraph 0.14, vispy 0.17, matplotlib 3.11).

```
cd /home/bard/Bard/code/TomoVic
/home/bard/miniconda3/envs/tomovis/bin/python webui/tools/tomovis_parity/generate.py \
    --shots <directory for the screenshots>
```

A full run takes about two minutes for the goldens and one more for the screenshots. Wrap it
in `systemd-run --user --scope -p MemoryMax=6G` when the screenshots are on, because the
realistic cubes hold a few hundred megabytes.

| Flag | Default | Meaning |
|---|---|---|
| `--tomovis` | `../tomovis` | TomoVis source root (holds `Visualizer/`) |
| `--fixtures` | `tests/webui/fixtures/tomovis` | committed fixture root |
| `--figure-reference` | `logs/tomovis_port/golden_figures` | every figure render (gitignored) |
| `--realistic-source` | `../DLR-TomoSAR/test_data/data/tomogram_full.npy` | cube cropped for the screenshots |
| `--realistic-dir` | `logs/tomovis_port/fixtures` | where the crops go (gitignored) |
| `--shots` | `logs/tomovis_port/original_shots` | screenshot directory |
| `--only NAME ...` | all | play only these scenarios (inputs and tables are kept) |
| `--skip-goldens`, `--skip-shots` | off | skip a stage |

A full goldens run deletes `inputs/`, `goldens/`, `figures/`, `sessions/` and `tables/` under
the fixture root and the figure reference directory, then writes them again. The output is
byte-reproducible: gzip carries mtime 0, NPZ entries are dated 1980-01-01, PNGs carry no
timestamp, and every cube comes from a fixed seed.

## How the original is driven

`generate.py` is the entry point. Its bootstrap sets `QT_QPA_PLATFORM=offscreen`, pins the Qt
binding the way `visualizer.py` does (`QT_API`, `PYQTGRAPH_QT_LIB`, `MPLBACKEND`; PySide6 is
also installed in that environment and pyqtgraph would otherwise pick it), turns bytecode
writing off so nothing lands in the TomoVis tree, and puts the TomoVis root on `sys.path`.

`harness.py` holds the driver. `TomoVisSession` builds the QApplication with
`AA_UseSoftwareOpenGL` as `tomoVis()` does, imports `Visualizer.visualizer`, and opens a fresh
`TomoVis` window at 1100x880 for every scenario. Actions go through the widgets a user
touches: menu actions are triggered, buttons and checkboxes are clicked, spin boxes, sliders
and combo boxes take values only while they are enabled, and the ROI is set by typing the six
fields and clicking Set. `DialogStubs` replaces `QFileDialog.exec_`/`selectedFiles` (import
callbacks), `getSaveFileName`/`getOpenFileName` (Save, Open), the static `QMessageBox`
helpers, and `QDialog.exec_` (the Axes dialog, whose two line edits and four spin boxes are
filled the way a user types). Each stub logs the request. `SlotErrors` takes over
`sys.excepthook` while an action runs, so exceptions raised inside Qt slots are recorded with
their innermost frames; outside actions it hands exceptions to the default hook. Printed lines
(the 3D tab prints its state) are captured per step. `StateProbe` then reads the window.

Two harness pieces change what runs, and both are switched per scenario and named in the
scenario's `toolkit_shims` list:

- `RgbLevelsShim`. TomoVis passes per-channel level lists to `ImageView.setLevels` for its RGB
  views. pyqtgraph 0.14 raises `TypeError: unhashable type: 'list'` there, so on the
  `tomovis` environment the RGB top view keeps levels (0, 1) and saturates, the RGB tomogram
  is never computed, and the RGB Plot and Profile fail. With the shim on, those calls go to
  pyqtgraph's own per-channel mechanism (level mode `rgba`, one pair per channel); every
  other call is untouched and TomoVis code runs unmodified. Scenarios ending in `_as_is` and
  the plain `import_npy_channels_*` ones run without it.
- `NumpyLegacyNames`. STEtools' `rrat` uses `np.int` and `srat` uses `np.ctypeslib.array`
  and `np.product`, all gone in numpy 2. The RAT fixture is written with them restored, and
  `import_rat_legacy_numpy` reads it with them restored; `import_rat_numpy2` shows the
  original failing.

## What is written

```
tests/webui/fixtures/tomovis/
  inputs/      synthetic cubes in every import format + manifest.json
  goldens/     <scenario>.json.gz (steps and state) + <scenario>.npz (arrays)
  figures/     PNG renders of the scenarios that commit them
  sessions/    session .hd5 files saved by the original's File > Save
  tables/      tables.json + tables.npz: colortables, pyqtgraph LUTs, colormap lists
```

The synthetic cubes follow the axis order TomoVis's code works with, which differs from the
(Nx, Ny, Nz) its README states: axis 0 is elevation, axis 1 azimuth, axis 2 range (the top
view sums axis 0, the tomogram plots axis 0 against height, the ROI slices axes 1 and 2 and
labels them azimuth and range, the slice slider walks axis 2). The DLR-TomoSAR cubes use the
same order. Multi-channel cubes put the channel first, the
covariance cube puts the two matrix axes first. `inputs/manifest.json` describes every file.

Each golden JSON has `scenario`, `description`, `toolkit_shims`, `window_size` and `steps`.
Step 0 is the fresh window; each later step has:

| Key | Content |
|---|---|
| `action`, `args` | the scripted action, paths written `<fixtures>/...` |
| `result` | what the action returned: `getCurrentMetadata()` for `metadata`, the session file read back for `read_session`, widget geometry and fonts for `layout`, slider values for `tick` |
| `events` | dialog requests: file dialogs with title and filter, message boxes with level, title and text, the Axes dialog with its initial and applied fields |
| `stdout`, `errors` | printed lines; slot exceptions with type, message and frames |
| `state.attributes` | window attributes (`x_label`, `x_min`, `z_range`, `nChannels`, `cmap`, `subplot`, ...), shape and dtype of `img`, `d2`, `aux`, `d2Norm`, `rgbArray`, `z_axis`, and `data_summary` (SHA-1 and magnitude statistics of the loaded cube) |
| `state.controls` | enabled, checked, value, range and text of every control, the current tab and stacked views, the timer, the slice line and the ROI's view |
| `state.roi` | `computeLinePar()`, the clipped line, axis mode, effective resolution |
| `state.views` | per ImageView: image shape and dtype, item levels, histogram levels and range, level mode, view range |
| `state.volume` | 3D tab: camera states, clim, threshold, visuals, colormap names |
| `arrays` | name to key in the NPZ; identical arrays share the key of their first occurrence |
| `figures.plot`, `figures.profile` | figure size and visibility, subplot parameters, per-Axes position, limits, labels, fonts, ticks, images, lines (data in the NPZ), legend, grid; `png` names the render, `png_committed` says whether it is in `figures/` (all renders are in the reference directory) |

The SHA-1 in `data_summary` and in `writer.digest` hashes `str(dtype)`, then `str(shape)`, then
the C-order bytes, so a port can hash its own loaded cube and compare.

Array names in the NPZ: `img`, `d2`, `aux`, `d2Norm`, `rgbArray`, `z_axis`; per view
`imv1_1_render`, `imv1_1_lut` and the same for `imv1_2`, `imv2_1`, `imv2_2` (RGBA uint8
renders in display order, rows top to bottom); per figure `plot_ax<i>_line<k>_x/_y` and
`profile_ax<i>_line<k>_x/_y`.

## Screenshots

`shots.py` crops the DLR-TomoSAR test tomogram (150 x 1000 x 500 complex64, heights -20 m
to 80 m) to 150 x 400 x 200 and writes it as a FuSAR .hd5 with real pixel spacings, and
builds a pseudo-RGB cube from three azimuth windows of the same scene (for the look of the
RGB views only). It grabs the window after every state worth comparing, plus the menus, the
Axes dialog and a warning box. The RGB pass runs twice, as-is (files 50 to 61) and with the
levels shim (files 70 to 81).

## Limits

The 3D tab cannot be rendered here. vispy needs PyOpenGL for 3D textures, the `tomovis`
environment does not have it (`start.sh` does not install it although `requirements.yml`
lists it), and no other copy is available offline. The 3D goldens therefore hold everything
except pixels: the equalized and subsampled volume handed to `renderVolume`, clim, threshold,
camera states, method and colormap of every visual, and the axis gizmo geometry. The 3D
screenshots show the controls next to a black canvas.
