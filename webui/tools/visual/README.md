# Console tour recorder

`record_tour.js` renders a short product-style video of the console: the Cube tab opening a
run, the Cuts view with the hover lens and the live range and azimuth cuts, the azimuth
sweep, a transect traced on the SLC map, the Slice collector filling its basket, and the
globe flying a camera tour over the point cloud. Nothing is captured in real time. The
headless shell runs under begin-frame control with virtual time, so the recorder advances
the page clock by exactly one frame interval, sets the scroll position, camera and pointer
for that instant, asks the compositor for one frame, and saves it; every transition, sweep
step and canvas redraw lands on the exact frame no matter how slow the machine is. The
camera is the DevTools viewport override, a sub-pixel transform in the compositor: it stays
still while the page scrolls and pushes in once per shot, anchored on the subject of that
shot. The globe scene leaves the recorder's camera still and drives the globe's own tour
through its offline stepping, one `seek` per frame, waiting for the imagery tiles to settle
before each frame is taken. Frames are 4096x2304 JPEGs (a 1440x810 layout at scale 2.84)
and ffmpeg scales them to a 3840x2160 H.264 MP4 at 30 fps, CRF 15, with a fade in and out.
There is no drawn cursor; hover states come from the pointer path the scene defines, and
clicks are real pointer presses at the pointer's position.

```
tools/visual/record_tour.sh                        # whole tour on port 8765
PORT=8766 OUT=/tmp/tour tools/visual/record_tour.sh --runs /data/runs --run 2026-09-04_lope
tools/visual/record_tour.sh cube globe             # a subset of scenes, in that order
```

The wrapper checks node 18+, installs `playwright-core` and its chromium when missing, finds
an ffmpeg with `libx264` (`TOUR_FFMPEG`, then `PATH`, then the `imageio-ffmpeg` static build,
which it fetches with `pip --target` into the gitignored `tools/visual/.ffmpeg/` when nothing
else is there), starts the console when nothing answers on the port, and records. Budget
about 0.3 s per frame plus a few minutes of 4K encoding: the 52 s tour takes around ten
minutes on a laptop.

`record_tour.js` flags: `--port`, `--out`, `--name` (file stem, default `tour`), `--ffmpeg`
(required), `--runs <dir>` (the runs directory the console scans, written into the browser's
stored Results sources; default the repository's `test_data`), `--run <label>` (the run strip
row to open, default the first), `--move <name>` and `--move-secs <n>` (the globe tour, default
`spiral` for 14 s; names as in the globe's tour menu: orbit, spiral, closein, pullout, along,
nadir, walkthrough), `--gl <backend>` (ANGLE backend for WebGL, default `gl` for the machine's
GPU, `swiftshader` for a machine without one), `--viewport WxH`, `--render WxH`, `--size WxH`,
`--push` (camera push-in per shot, default 0.06), `--fps`, `--crf`, `--preset`, `--quality`,
`--speed <factor>` (above 1 shortens every shot), `--keep-frames`, `--verbose`.

Shot lengths at speed 1: cube 1.6 s to open plus 10 s of cuts, sweep 7 s, transect 7 s,
slices 9 s, globe 2 s plus the tour, about 52 s in all. Scroll targets, pointer paths and
camera anchors are read from the live DOM (the SLC image, the cuts block, the sweep grid,
the transect map and grid, the collector map and preview rows, the globe stage), so the same
script frames any run. The app exposes itself as `window.app` so the recorder can reach the
globe's viewer and tour.

Four mechanics of begin-frame control matter when editing the scenes. Frame timestamps must
start from the renderer's monotonic clock (`/proc/uptime`), or CSS animations started before
the first frame never finish and pages stay at opacity 0. Nothing that waits on a rendered
frame may be awaited without pumping frames: Playwright's `page.mouse` and `locator.click()`
block, so the recorder dispatches raw `Input.dispatchMouseEvent` calls and resolves them after
the frame, and polls readiness between frames. Virtual time is paused between frames, so timers
only fire during `advance()`. WebGL needs a GL backend under begin-frame control: with the GPU
disabled a WebGL canvas never completes a frame and `beginFrame` waits forever, with ANGLE on
the machine's GL or on SwiftShader the globe renders normally. The DevTools viewport override
takes document coordinates in device pixels, so the camera multiplies by the scale factor and
adds the scroll offset; the console's stylesheet asks for smooth scrolling, so the recorder
positions the page with `behavior: "instant"`.

## Setup

```
npm ci
npx playwright-core install chromium
```

`npm ci` installs exactly what `package-lock.json` records, the pinned `playwright-core`. The
browser itself is not in the lock file: `npx playwright-core install chromium` fetches the
build that matches it into `~/.cache/ms-playwright`, and `chromium.js` picks the highest build
present there (`PW_CHROMIUM=/path/to/chrome` overrides it).
