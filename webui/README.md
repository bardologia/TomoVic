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
| Home | `#/home` | `/api/system`, `/api/jobs`, `/api/notify/*` | Live host and GPU telemetry, per-user memory attribution, running-job tiles, server detach and shutdown, and the ntfy settings. |
| Repo Map | `#/repomap` | `/api/repomap` | Curated module-level schematics, each with nodes, edges and the artifacts a stage reads and writes. |
| Scripts | `#/scripts` | `/api/scripts` | The entry points as cards, laid out in workflow sections (Data, Analysis) with a search box and per-category counts, including `extract_params` and `analyze_param_extraction`, which fit and audit the parametrized tomogram. |
| Launch | `#/launch/<key>` | `/api/scripts/<key>/config` | Full-screen launch control per script: config sections grouped by dataclass, typed controls, the override manifest, the command preview and the interpreter. Launch now, queue after the current job, or save for later. |
| Saved | `#/saved` | `/api/saved-runs` | Configurations stored from launch pages, one JSON file each under `logs/saved_runs/`. Each card can be launched, queued or deleted. |
| Configuration | `#/configuration` | `/api/configs` | Every configuration dataclass, field, type and default, parsed live from `configuration/`. |
| Console | `#/console` | `/api/jobs`, `/api/jobs/<id>/stream` | Real-time stdout of launched jobs over SSE with stop control, plus per-unit logs and a progress strip for fan-out jobs. |
| Results | `#/results` | `/api/results/*`, `/api/fs/*` | Browse any run or dataset directory: rendered markdown reports, figure galleries with compare pinning, configs, and inline log and text files. |
| Cube | `#/cube` | `/api/cubes/*` | Tomogram explorer over preprocessing runs: live cuts with profiles, axis sweeps, arbitrary-line transects, a 3D scatterer point cloud, the DEM grid, the scene on a Cesium globe with flight tracks and beam segment, selectable colormaps and paper-style figure export, with the parametrized tomogram from `params/<tag>` runs as a selectable source. A run is any directory holding `data/dataset.json`. |
| Slices | `#/slices` | `/api/slices/*` | Multi-run slice collector: tick any number of cubes, set a cut position plus an optional queue of extra points, and preview the same slice from every run side by side on a shared colour scale. Collect renders the figures into one `slice_collections/<name>/` folder with a `collection.json` manifest. |

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
  per-field help text under the same strictness.
- **Overrides.** Edited fields are appended to the command as `--<dotted.path> <value>`,
  which `ConfigCli` coerces to the field's type. The command preview always shows exactly
  what will run.
- **Launch.** `ProcessManager` runs the script from the repository root with the selected
  interpreter and streams its output over SSE. Exit codes are reported as they are.
- **Queue.** Schedule captures the same command but places it in a sequential queue. A
  queued run starts once every running job and every earlier queued run has ended,
  regardless of exit code. Queued runs can be cancelled before they start; an emergency
  stop clears the whole queue.
- **Notifications.** `JobNotifier` pushes start and end events over ntfy.

Scripts expect the F-SAR dataset paths named in the configuration defaults, and the
tomogram and interferogram stages need the PyRAT conda environment. On a machine without
them, a launched job streams its real traceback to the console.

## Architecture

One class per file, no comments, per the vault coding rules.

**Server.** `serve.py` builds and runs the threaded HTTP server in `web_ui_server.py`,
which owns one instance of every collaborator and composes the routing table. Requests
enter `request_router.py`, which resolves the path's leading section to exactly one
sub-router under `routers/` and delegates: `routers/dispatch.py` carries the shared
`HttpExchange` (query accessors, JSON, PNG, byte and file responses) and the per-router
`RouteTable`; `static_router.py`, `results_routers.py`, `cube_routers.py`,
`library_routers.py`, `launch_routers.py` and `system_router.py` declare the routes of
their own domain and hold only the collaborators they use. A section may be claimed by
one sub-router only; a second claim raises at construction. `project_paths.py` resolves
repository paths and candidate interpreters, `catalog_roots.py` gates filesystem
browsing to roots the user has opened, and `web_logger.py` handles console logging.

**Launching and supervision.** `script_catalog.py`, `script_config_resolver.py`,
`launch_layout.py`, `config_registry.py`, `run_launcher.py`, `process_manager.py`,
`saved_run_store.py`, `job_describer.py`, `notifier.py`, `system_monitor.py`,
`proc_stats.py`.

**Curated content.** Hand-written project documentation served as JSON and kept honest by
tests under `tests/webui/`: `repomap_data.json` with `repomap_library.py` and its drift
checker `repomap_derive.py`, and `config_descriptions.json`.

**Analysis surfaces.** `results_browser.py`, `dataset_browser.py`, and
`cube_explorer.py`, which also carries the slice collector.

**Frontend.** `static/index.html`, `static/css/styles.css`, `static/vendor/marked.min.js`
and 27 modules under `static/js/`. `app.js` and `router.js` wire the views; one module per
tab (`home`, `repomap`, `scripts`, `launch` with its widget modules (`python_literal`,
`form_widgets`, `config_form`) and `launch_pickers`, `saved_runs`, `configs`, `console`,
`results`, `tomogram`, `slice_collector`); the rest are shared helpers (`api`,
`shared_charts`, `results_sources`, `run_strip`, `canvas_base`, `diagram`, `gauges`,
`globe`, `process_anim`, `server_anim`, `tomo_anim`).
