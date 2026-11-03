# TomoVic control console

A single-page web console for TomoVic. It launches and supervises the `main/` entry
points and browses everything those runs produce: tomogram cubes, the DEM, figures,
reports and logs.

## Run

```bash
webui/run.sh            # http://127.0.0.1:8765
webui/run.sh 9000       # custom port
```

`run.sh` picks the first interpreter that exists among `~/miniconda3/envs/Dune/bin/python`,
`~/miniconda3/bin/python` and the system `python3`, then executes `serve.py --port <port>`.
`serve.py` also takes `--host`, default `127.0.0.1`, and `--root`, the project root the
console operates on (job adoption, logs, runs), default the repository that holds
`serve.py`. Tests point `--root` at a temporary directory so a console booted by the
suite can never see or stop the jobs of the live repository.

Setting `TOMOVIC_ACCESS_KEY` (at least 16 characters from `A-Z a-z 0-9 _ -`) puts the
console behind a key. It then answers only a browser that has opened
`http://<address>:<port>/?key=<key>` once: that request is redirected to the same page
without the key and leaves the key in an HttpOnly cookie named `tomovic_key_<port>`.
Every other request gets a plain-text 403. The key travels in the environment because
every user of a shared server can read a process's command line, and `serve.py`
removes the variable after reading it so launched jobs do not inherit it. Without the
variable, `--host` must be a loopback address and the console answers anyone who can
reach it, which on a shared server means every other user of `127.0.0.1`. The TomoVis
"Open TomoVic" button always starts the console with a fresh key, on `0.0.0.0` when
TomoVis runs over SSH. By hand:

```bash
export TOMOVIC_ACCESS_KEY=$(python -c "import secrets; print(secrets.token_urlsafe(24))")
echo "http://$(hostname -f):8765/?key=$TOMOVIC_ACCESS_KEY"
python webui/serve.py --host 0.0.0.0 --port 8765
```

The HTTP transport is standard library only (`http.server` plus server-sent events), but
the console itself needs the project environment. `web_ui_server.py` imports the cube
explorer and system monitor at boot, and those pull numpy, matplotlib, scipy and psutil.
On a bare interpreter the server fails with an ImportError before it binds the port,
which is why `run.sh` prefers the `Dune` env.

The frontend loads MathJax 3.2.2 (tex-svg), highlight.js 11.9.0, GSAP 3.12.5, Cesium and
xterm.js 5.5.0 with its fit addon from a CDN, so equation typesetting, syntax
highlighting, animation, the globe and the terminal view need a network connection.
`marked` is vendored under `static/vendor/`. Everything degrades to plain text offline.

## Tabs

Navigation is hash-based, `#/<route>`. Each tab is one view module under `static/js/`
talking to one group of JSON endpoints. The nav drawer groups the tabs into four
sections, and the section holding the active tab stays expanded: Reference (Repo Map),
Launch (Scripts, Saved, Configuration), Monitor (Console) and
Results (Results, Cube, Slices).

| Tab | Route | Backed by | What it does |
|---|---|---|---|
| Home | `#/home` | `/api/system`, `/api/jobs`, `/api/gpu-activity`, `/api/host-history`, `/api/server-log`, `/api/impact/*`, `/api/notify/*` | Live host and GPU telemetry, per-user memory attribution, the day/week/month GPU activity timeline, the persisted host history, the server's own log, the neighbour impact card (per-user slice stall, the launch politeness level and auto-throttle switch, the auto-nuke arm), running-job tiles, server detach and shutdown, and the ntfy settings. The kill-front-end button also force-kills every other console server of this user on the same repository root. |
| Repo Map | `#/repomap` | `/api/repomap` | Curated module-level schematics, each with nodes, edges and the artifacts a stage reads and writes. |
| Scripts | `#/scripts` | `/api/scripts` | The entry points as cards, laid out in workflow sections (Data, Analysis) with a search box and per-category counts, including `extract_params` and `analyze_param_extraction`, which fit and audit the parametrized tomogram, and `extract_polarimetry`, which stores the polarimetric primary the Cube tab decomposes. |
| Launch | `#/launch/<key>` | `/api/scripts/<key>/config` | Full-screen launch control per script: config sections grouped by dataclass, typed controls, the override manifest, the command preview and the interpreter. Launch now, queue after the current job, or save for later. The figure at the end of the top bar follows the script through `LaunchView.FIGURES` (`pre_process` `aperture`, `extract_params` `threshold`, `analyze_preprocessing` `slc`, `analyze_param_extraction` `transect`, `compare_*` `balance`, any other key `surface`). |
| Saved | `#/saved` | `/api/saved-runs` | Configurations stored from launch pages, one JSON file each under `logs/saved_runs/`. Each card can be launched, queued or deleted. |
| Configuration | `#/configuration` | `/api/configs` | Every configuration dataclass, field, type and default, parsed live from `configuration/`. |
| Console | `#/console` | `/api/jobs`, `/api/stream` | Real-time stdout of launched jobs with stop control, plus per-unit logs and a progress strip for fan-out jobs. The page opens one server-sent-events channel (`GET /api/stream?channel=<id>`) and subscribes every job tile and every selected sub-run to it through `POST /api/stream/<channel>/subscribe` and `/unsubscribe`, so any number of open tiles costs the browser a single connection out of its six per origin. A dropped channel reconnects and each job stream replays from its last event id (a restarted server, recognised by the `boot` token in the channel's `hello` frame, replays everything); while it is down, a tile takes its status from the polled job list, and a tile whose job the console no longer knows turns `untracked`. Terminals are sized on an off-screen gauge before they open and tiles are fitted one per animation frame. Once a job has ended its tile shows Retry, which reopens the launch page with the overrides, interpreter and detach switch the job was launched with; each job record keeps that request under `request`. |
| Results | `#/results` | `/api/results/*`, `/api/fs/*` | Browse any run or dataset directory: rendered markdown reports, figure galleries with compare pinning, configs, and inline log and text files. |
| Cube | `#/cube` | `/api/cubes/*` | Tomogram explorer over preprocessing runs: live cuts with profiles, axis sweeps, polyline transects with saved lines, a 3D scatterer point cloud, a WebGL2 ray-marched volume with transfer function and clip plane, the DEM grid, the scene on a Cesium globe with flight tracks, beam segment, preset camera moves and a choreographed walkthrough that drives the section cut in step with the camera, either renderable offline frame by frame into a 60 fps MP4 under the run's `figures/globe_tours` (WebCodecs H.264 or VP9, muxed in the browser, every frame waiting for its imagery tiles), selectable colormaps, paper-style figure export and PNG/CSV downloads, a Passes view walking the per-pass SLC amplitude and interferogram phase, a Pauli view of the polarimetric primary that Extract Polarimetry writes (composite, single-component and dominant maps at a chosen multilook window, with a scene balance table, a per-pixel readout and the same maps draped north-up on the globe), a Figures view over the figures saved under the run's `images`, `figures` and `params` trees, with the parametrized tomogram from `params/<tag>` runs as a selectable source. Link copies a `#/cube/<state>` URL that reopens the cube, view, source and locked pixel, and Story records an ordered list of such states to replay, share and snapshot. A run is any directory holding `data/dataset.json`. A load reads the tomogram, the primary SLC, the DEM and the chosen parameter block whole into memory through a process-wide read pool (`NpyReader`, up to 32 threads) that splits each file into 16 MB `pread` chunks, and books the wall time of every stage; the progress bar follows the bytes read against the byte plan of the load and names the files still in flight with their megabytes landed; after five silent seconds it also prints how long the load has been silent and the innermost frames of the load thread, and `kill -USR1 <pid>` dumps every console thread's stack to stderr. The ready line in the console log lists the stage times, the ready payload carries them under `timings`, and the tab shows the total next to the slowest stage. The last eight loaded cubes stay in memory (`CubeExplorer.CUBE_CACHE_ENTRIES`, keyed by run and parameter run tag), and their globe point blobs survive a switch, so going back to one is immediate. |
| Slices | `#/slices` | `/api/slices/*` | Multi-run slice collector: tick any number of cubes, hover the primary SLC map to preview the same cuts from every run side by side, and click the map (or a slice's own button) to put cuts in a basket that persists in the browser. The basket renders into one `slice_collections/<name>/` folder with a `collection.json` manifest, and can be mailed as zip volumes through the report mailer (`REPORT_MAIL_PASSWORD`). |

## Saving figures

The tabs that show images have a figure saver: Results, Cube and Slices. It runs in the
browser over what is already on screen, so the server renders nothing extra and no run
directory is written.

- **One figure.** Hovering a chart, map or plot floats a small save button in its top-right
  corner, and pressing it downloads that figure as a PNG.
- **Every figure.** A dock at the bottom right counts the figures on the view and packs them
  into one ZIP.
- **A subset.** The dock's second button opens the list of those figures, grouped by the card
  they sit in. Each row has its own PNG button and a checkbox, and the selection saves as one
  ZIP. Hovering a row outlines the figure on the page and clicking it scrolls there.

A file name carries the tab, the view's context and the figure, so a single save lands as
`cube_<run>_<source>_<space>_az0413_rg0207_range_cut_full.png` and a batch as
`<tab>_<context>_figures.zip`. Each tab supplies its context through a `figureTag()` method.
A figure takes its label from its `data-fig` attribute, or failing that from its `alt` text,
its caption or the heading above it.

The scanner only sees figures that are visible, so the batch covers the cube view on screen.
Canvases are written at their backing-store resolution over an opaque background. Small
server-rendered maps are upscaled by whole pixels the way the page shows them, and vector
charts are rasterized at twice their layout size with their computed styles inlined.
`figure_export.js` holds the mechanics, including a store-only ZIP writer, and
`figure_saver.js` the scanner and the dock. The cube explorer keeps its own PNG and CSV
buttons and its server-side paper-figure export beside this.

## How launching works

Every `main/*.py` script builds its configuration as `ConfigCli(<EntryConfig>()).apply()`,
with all defaults living in `configuration/` dataclasses. The console mirrors that
contract and never writes to a config file.

- **Resolution.** `ScriptConfigResolver` finds the entry dataclass by parsing the script's
  AST, then resolves its defaults in a subprocess using the preferred project interpreter,
  exactly as `--help-config` would. Results are cached and invalidated when any file under
  `configuration/`, the script itself, or `tools/runtime/config_cli.py` changes mtime.
- **Layout.** `launch_layout.py` decides which fields the launch form exposes and which
  widget each one gets. It is the single source of truth for the form and refuses to build
  a section containing a field it does not claim, so a new config field surfaces as a loud
  failure rather than a silently missing control. `config_descriptions.json` supplies the
  per-field help text under the same strictness. A number widget renders as a numeric
  field even when the field defaults to None, and leaves the unset default out of its
  range and presets.
- **Overrides.** Edited fields are appended to the command as `--<dotted.path> <value>`,
  which `ConfigCli` coerces to the field's type. The command preview always shows exactly
  what will run.
- **Launch.** `ProcessManager` runs the script from the repository root with the selected
  interpreter and streams its output over the page's live-output channel. Exit codes are
  reported as they are.
- **Queue.** Schedule captures the same command but places it in a sequential queue. A
  queued run starts once every running job and every earlier queued run has ended,
  regardless of exit code. Queued runs can be cancelled before they start; an emergency
  stop clears the whole queue.
- **Supervision.** `ContentionMonitor` (`contention_monitor.py`) reports neighbour impact.
  It reads every login user's cgroup slice under `user.slice`: the slice's own pressure
  files say whether that user's tasks are waiting for CPU, memory or disk, `cpu.stat` and
  `memory.stat` give each user's share of the resource, exited children included. An
  alarm needs a neighbour stalled for two samples and is this user's only when this user
  is the dominant consumer; disk has no per-user byte counter, so its ownership falls
  back to this user's own processes' share of the repo disk. Without `/proc/pressure`
  or `user.slice` the monitor stays off and the panel says so. `JobNotifier` pushes start
  and end events over ntfy and carries the monitor's alerts to the same topic.
- **Politeness.** `JobPoliteness` (`politeness.py`) holds the level every local launch
  starts under, persisted in `logs/politeness.json`: `off` runs at nice 0, `polite` (the
  default) prefixes the command with `nice -n 10 ionice -c 2 -n 7`, `background` with
  `nice -n 19 ionice -c 3`. The prefix execs into the interpreter, so the job pid is the
  interpreter's and the job record's command line shows it. `JobThrottle` is the runtime
  lever: with auto-throttle on, the first alarm the contention monitor attributes to
  this user runs `renice -n 19` and `ionice -c 3` over every process this user owns
  except the console's own line, once per alarm until it clears. That reaches jobs
  another console started on the same machine too, so auto-throttle is off by default
  and only an explicit switch on the Home page turns it on. Priorities can only be
  lowered without privileges, so a throttled job stays throttled until it ends. Both are
  set from the Home page (`POST /api/impact/politeness` with `level` and
  `auto_throttle`), and `POST /api/impact/arm` with `armed` arms the automatic nuke,
  which starts disarmed on every console start.
- **Telemetry.** `SystemMonitor` starts two persisted samplers beside its rolling
  history, both on `telemetry_log.py`'s `BucketedTelemetryLog`: `GpuActivityLog`
  (`gpu_activity.py`, `logs/gpu_activity.jsonl`) records per-GPU busy shares split into
  this user's and other users' work, and `HostHistoryLog` (`host_history.py`,
  `logs/host_history.jsonl`) records CPU, RAM, network and per-GPU utilisation, memory,
  temperature and power. Both sample every 30 s into 5-minute buckets kept for 30 days
  and are read back through `GET /api/gpu-activity?range=day|week|month` and
  `GET /api/host-history?range=hour|day|week|month`. `GET /api/server-log?limit=<n>`
  serves the newest lines of `WebLogger`'s in-memory ring. The console reads GPUs and
  never acts on them: it has no GPU guard or GPU schedule.

Scripts expect the F-SAR dataset paths named in the configuration defaults, and the
tomogram and interferogram stages need the PyRAT conda environment. On a machine without
them, a launched job streams its real traceback to the console.

## Architecture

One class per file, no comments, per the vault coding rules.

**Server.** `serve.py` builds and runs the threaded HTTP server in `web_ui_server.py`,
which owns one instance of every collaborator and composes the routing table. Requests
enter `request_router.py`, which refuses cross-origin requests, passes the rest through
the `AccessGate` when the console has an access key, resolves the path's leading
section to exactly one sub-router under `routers/` and delegates: `routers/dispatch.py` carries the shared
`HttpExchange` (query accessors, JSON, PNG, byte and file responses) and the per-router
`RouteTable`; `static_router.py`, `results_routers.py`, `cube_routers.py`,
`library_routers.py`, `launch_routers.py` and `system_router.py` declare the routes of
their own domain and hold only the collaborators they use. A section may be claimed by
one sub-router only; a second claim raises at construction. `project_paths.py` resolves
repository paths and candidate interpreters, `catalog_roots.py` gates filesystem
browsing to roots the user has opened, and `web_logger.py` handles console logging.

**Launching and supervision.** `script_catalog.py`, `script_config_resolver.py`,
`launch_layout.py`, `config_registry.py`, `run_launcher.py`, `process_manager.py`,
`stream_hub.py`, `saved_run_store.py`, `job_describer.py`, `notifier.py`,
`contention_monitor.py`, `politeness.py`, `system_monitor.py`, `telemetry_log.py`,
`gpu_activity.py`, `host_history.py`, `proc_stats.py`.

**Curated content.** Hand-written project documentation served as JSON and kept honest by
tests under `tests/webui/`: `repomap_data.json` with `repomap_library.py` and its drift
checker `repomap_derive.py`, and `config_descriptions.json`.

**Analysis surfaces.** `results_browser.py`, `dataset_browser.py`, and
`cube_explorer.py`, which also carries the slice collector.

**Frontend.** `static/index.html`, `static/css/styles.css`, the vendored
`static/vendor/marked.min.js`, `static/vendor/mp4-muxer.js`,
`static/vendor/thinking-orbs-engine.js`, `static/vendor/hairline-kernel.js` and
`static/vendor/hairline-figures.js`, and 34 modules under `static/js/`. `app.js` and
`router.js` wire the views; one module per tab (`home`, `repomap`, `scripts`, `launch`
with its widget modules (`python_literal`, `form_widgets`, `config_form`) and
`launch_pickers`, `saved_runs`, `configs`, `console`, `results`, `tomogram`,
`slice_collector`); the rest are shared helpers (`api`, `stream_hub` with the page's
single live-output channel, `shared_charts`, `results_sources`, `run_strip`,
`canvas_base`, `figure_export`, `figure_saver`, `diagram`, `gauges`, `globe` with
`globe_tour`, `volume`, `process_anim`, `thinking_orb`, `hairline_figure` with
`hairline_tomosar`, `tomo_anim`). `thinking_orb` defines the `<thinking-orb>` loading
indicator over the vendored thinking-orbs engine (Jakub Antalik, MIT); a dark surface
opts into light ink by setting `--orb-theme: dark`. `hairline_figure` defines
`<hairline-figure name>`, an isometric line drawing that answers the pointer, over the
vendored hairline kernel (Lucas Marques, MIT); `hairline_tomosar` draws the project's own
figures on a shared `HairlineFigureBase`, and the element remounts when its `name`
changes, so a page can swap the figure with what is on screen.
