# DLR-TomoSAR control console

A single-page web console for the DLR-TomoSAR project. It documents the signal model and
the pipelines, launches and supervises the `main/` entry points, and browses everything
those runs produce: metrics, reports, figures, tomogram cubes and TensorBoard curves.

## Run

```bash
webui/run.sh            # http://127.0.0.1:8765
webui/run.sh 9000       # custom port
```

`run.sh` picks the first interpreter that exists among `~/miniconda3/envs/Dune/bin/python`,
`~/miniconda3/bin/python` and the system `python3`, then executes `serve.py --port <port>`.
`serve.py` also takes `--host`, default `127.0.0.1`, and `--root`, the project root the
console operates on (job adoption, logs, GPU pools, runs), default the repository that
holds `serve.py`. Tests point `--root` at a temporary directory so a console booted by the
suite can never see or stop the jobs of the live repository.

The HTTP transport is standard library only (`http.server` plus server-sent events), but
the console itself needs the project environment. `web_ui_server.py` imports the cube
explorer, fit lab, model probe, A/B autopsy, triage board, training-curve reader and
system monitor at boot, and those pull numpy, matplotlib, scipy, torch, scikit-image,
tensorboard and psutil. On a bare interpreter the server fails with an ImportError before
it binds the port, which is why `run.sh` prefers the `Dune` env.

The frontend loads MathJax 3.2.2 (tex-svg), highlight.js 11.9.0, GSAP 3.12.5 and xterm.js
5.5.0 with its fit addon from a CDN, so equation typesetting, syntax highlighting,
animation and the terminal view need a network connection. `marked` is vendored under
`static/vendor/`. Everything degrades to plain text offline.

## Tabs

Navigation is hash-based, `#/<route>`. Each tab is one view module under `static/js/`
talking to one group of JSON endpoints. The nav drawer groups the tabs into five
sections, and the section holding the active tab stays expanded: Reference (Model,
Pipelines, Architectures, Physics Loss, Repo Map), Launch (Scripts, Saved,
Configuration, Feed Tuner), Monitor (Console, TensorBoard, Terrabyte), Results (Results,
Leaderboard, Cube, Slices) and Inspect (Microscope, Survey, Triage, Autopsy, Fit Lab).

| Tab | Route | Backed by | What it does |
|---|---|---|---|
| Home | `#/home` | `/api/system`, `/api/jobs`, `/api/gpu-schedule`, `/api/gpu-guard/history`, `/api/notify/*` | Live host and GPU telemetry, per-user memory attribution, running-job tiles, the GPU guard history, the charity-mode schedule, the neighbour-impact alarm and the ntfy settings. |
| Model | `#/model` | `/api/equations`, `/api/flows` | The curated equation catalog, 9 groups and 141 items, rendered with MathJax, plus the flow walkthroughs: 16 animated step-by-step derivations from preprocessing through training, inference, benchmarking and tuning. |
| Physics Loss | `#/physics` | `/api/physics-loss` | The physics-loss terms in detail: forward operator, coherence re-synthesis, covariance matching, Capon cycle-consistency. |
| Pipelines | `#/pipelines` | `/api/pipelines` | The 16 pipelines as staged flows; each maps to the entry point that runs it. |
| Repo Map | `#/repomap` | `/api/repomap` | Curated module-level schematics, 14 folders and 33 diagrams, each with nodes, edges and the artifacts a stage reads and writes. |
| Architectures | `#/architectures` | `/api/backbones`, `/api/profile-autoencoders`, `/api/image-autoencoders`, `/api/jepa-variants` | The 20 backbones across 5 families plus the autoencoder and JEPA variants, with selection guidance and per-model defaults. |
| Scripts | `#/scripts` | `/api/scripts` | The entry points as cards, laid out in workflow sections (Data, Training, Inference, Analysis, Experiments) with a search box, per-category counts, and topic subgroups inside Analysis (trial rebuilds and comparisons, model diagnostics, exports). `ScriptCatalog` describes 39 of them and folds the per-family variants into 4 groups (train, infer, analyze, compare); group cards link every stage directly and search also matches the folded members. `main/` holds 41 entry scripts across `processing/`, `training/`, `inference/`, `analysis/` and `experiments/`. |
| Launch | `#/launch/<key>` | `/api/scripts/<key>/config` | Full-screen launch control per script: config sections grouped by dataclass, typed controls, the override manifest, the command preview and the interpreter. Launch now, queue after the current job, or save for later. A target switch sends the same configuration to the Terrabyte cluster instead, as a single job or a sweep, after translating the paths and checking the commit is pushed. |
| Ablation | `#/ablation` | `/api/backbones`, `/api/run` | Reached from a script card. Picks the entry, the features to ablate and their order, then launches a cumulative loop that trains the full model and degrades one feature at a time down to the baseline. |
| Saved | `#/saved` | `/api/saved-runs` | Configurations stored from launch pages, one JSON file each under `logs/saved_runs/`. Each card can be launched, queued or deleted. |
| Configuration | `#/configuration` | `/api/configs` | Every configuration dataclass, field, type and default, parsed live from `configuration/`. |
| Console | `#/console` | `/api/jobs`, `/api/jobs/<id>/stream` | Real-time stdout of launched jobs over SSE with stop control. Fan-out experiments add a progress strip from `/api/jobs/<id>/progress`: units done of total, mean unit duration, ETA and projected finish. |
| TensorBoard | `#/tensorboard` | `/api/tensorboard/*` | Starts and supervises a TensorBoard process against any run directory. |
| Terrabyte | `#/terrabyte` | `/api/terrabyte/*` | Observatory for the LRZ Terrabyte cluster over a shared SSH connection: cluster GPU and CPU load, HOME quota, the GPU node grid, partition occupancy, your queue and your last 48 hours of jobs, each with its SLURM log. The runs board lists what sits on cluster scratch and pulls finished runs back to this machine, one at a time or as they complete, with size verification and scratch cleanup. |
| Leaderboard | `#/leaderboard` | `/api/leaderboard`, `/api/curves` | Three modes. Runs: every saved inference `metrics.json` as one sortable, filterable table with run-name axes parsed into dropdowns and a metric plus resolved-config diff; seeded layouts also get one seed-mean row per unit. Trials: seeded runs aggregated to mean-and-std bars. Curves: native overlay of TensorBoard scalars across runs. |
| Results | `#/results` | `/api/results/*`, `/api/fs/*` | Browse any run or dataset directory: rendered markdown reports, figure galleries with compare pinning, configs, and inline log and text files. |
| Cube | `#/cube` | `/api/cubes/*` | Tomogram explorer over saved inference cubes: live cuts with profiles and SSIM, axis sweeps, Gaussian parameter maps with per-pixel slot readout, per-pixel metric overlays with thresholding, arbitrary-line transects, a 3D scatterer point cloud, run-vs-run comparison, selectable colormaps and paper-style figure export. Cross-validation runs add one `all folds` entry per inference split (and per seed) that stitches every fold's cube, parameter block and metric map into a single full-scene mosaic along azimuth; fold inference covers each full fold block, so the mosaic tiles without gaps, while older runs inferred on guard-trimmed regions show blank stripes at the fold boundaries. |
| Slices | `#/slices` | `/api/slices/*` | Multi-run slice collector: tick any number of cubes, set a cut position plus an optional queue of extra points, and preview the same slice from every run side by side on a shared colour scale. Collect renders the figures into one `slice_collections/<name>/` folder with a `collection.json` manifest. |
| Fit Lab | `#/fitlab` | `/api/fitlab/*` | Parameter-extraction playground over a preprocessing dataset: pick pixels on the SLC or tomogram-peak map, then run the real Gaussian-fit stack (`PeakInitialiser` plus `SigmaAdamKernel` on CPU) on just those pixels. Each run is a labelled overlay with a per-K mixture, a per-run K override and a penalised-MSE K sweep. |
| Microscope | `#/microscope` | `/api/probe/*` | Model microscope over a trained run: load the checkpoint with its real dataset, click a pixel, and inspect the predicted profile against ground truth and the raw tomogram, gradient attribution of every output family to every input channel with per-pair spatial maps, feature-map grids along a clickable architecture strip, and live what-if perturbations with per-slot deltas. |
| Survey | `#/survey` | `/api/survey/*` | The microscope's diagnostics averaged over the whole region as a background job with progress and cancel: prediction fit and matched errors, aggregate attribution with mean gradient windows, channel ablation, flip symmetry, noise robustness, occlusion distance profile and accumulated layer vitals. |
| Triage | `#/triage` | `/api/triage/*` | Error triage over a saved inference: the worst blocks ranked by pixel MSE, tagged with dominant failure mode, label fit, seed disagreement and flip disagreement where those cubes exist. Each case opens the cube explorer at its worst pixel and takes a persisted verdict plus a note under `logs/triage/`. |
| Autopsy | `#/autopsy` | `/api/autopsy/*` | Guided A/B comparison of two inferences over the same region: the largest relative metric gaps with an orientation-aware winner per row, plus the blocks where the runs disagree most, each rendered as both predicted profiles against the ground truth. |
| Feed Tuner | `#/feedtuner` | `/api/scripts/tune_dataloader/config`, `/api/run` | Launch surface for the DataLoader sweep with its own result view. |

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
- **Supervision.** `GpuWatchdog`, `ResourceWatchdog` and `ContentionMonitor` guard GPU
  intrusion, host memory and neighbour impact; `JobNotifier` pushes start and end events
  over ntfy.

Scripts expect the F-SAR dataset paths and GPUs named in the configuration defaults. On a
machine without them, a launched job streams its real traceback to the console.

## Architecture

One class per file, no comments, per the vault coding rules.

**Server.** `serve.py` builds and runs the threaded HTTP server in `web_ui_server.py`,
which owns one instance of every collaborator and composes the routing table. Requests
enter `request_router.py`, which resolves the path's leading section to exactly one
sub-router under `routers/` and delegates: `routers/dispatch.py` carries the shared
`HttpExchange` (query accessors, JSON, PNG, byte and file responses) and the per-router
`RouteTable`; `static_router.py`, `results_routers.py`, `cube_routers.py`,
`analysis_routers.py`, `library_routers.py`, `launch_routers.py`, `system_router.py` and
`tensorboard_router.py` declare the routes of their own domain and hold only the
collaborators they use. A section may be claimed by one sub-router only; a second claim
raises at construction. `project_paths.py` resolves repository paths and candidate
interpreters, `catalog_roots.py` gates filesystem browsing to roots the user has opened,
and `web_logger.py` handles console logging.

**Launching and supervision.** `script_catalog.py`, `script_config_resolver.py`,
`launch_layout.py`, `config_registry.py`, `run_launcher.py`, `process_manager.py`,
`saved_run_store.py`, `job_describer.py`, `notifier.py`, `gpu_schedule.py`,
`gpu_watchdog.py`, `resource_watchdog.py`, `contention_monitor.py`, `system_monitor.py`,
`proc_stats.py`, `tensorboard_manager.py`.

**Cluster bridge.** `terrabyte_remote.py` owns the shared SSH connection, `terrabyte_launcher.py`
translates a launch form into an `sbatch` submission through `scripts/submit_terrabyte.py` or
`scripts/sweep_terrabyte.py`, `terrabyte_console.py` reads the queue and the job logs, and
`terrabyte_monitor.py` reports cluster load and pulls finished runs back from scratch.

**Curated content.** Hand-written project documentation served as JSON and kept honest by
tests under `tests/webui/`: `equation_library.py`, `flow_library.py`,
`physics_loss_library.py`, `pipeline_library.py`, `repomap_data.json` with
`repomap_library.py` and its drift checker `repomap_derive.py`,
`config_descriptions.json`, and the model libraries `backbone_model_library.py`,
`profile_autoencoder_model_library.py`, `image_autoencoder_model_library.py` and
`jepa_model_library.py` on the shared `model_library_base.py`.

**Analysis surfaces.** `results_browser.py`, `dataset_browser.py`, `run_leaderboard.py`,
`training_curves.py`, `cube_explorer.py` which also carries the slice collector,
`fit_lab.py`, `model_probe.py`, `triage_board.py`, `ab_autopsy.py`.

**Frontend.** `static/index.html`, `static/css/styles.css`, `static/vendor/marked.min.js`
and 47 modules under `static/js/`. `app.js` and `router.js` wire the views; one module per
tab (`home`, `equations`, `flow_view` with `flow_sketches`, `physics_loss`, `pipelines`,
`repomap`, `models`, `scripts`, `launch` with its widget modules (`python_literal`,
`form_widgets`, `model_panels`, `gpu_pickers`, `experiment_builder`, `config_form`) and
`launch_pickers`, `ablation`, `saved_runs`, `configs`, `console`, `tensorboard`,
`terrabyte`, `leaderboard`, `results`, `tomogram`, `slice_collector`, `fit_lab`,
`microscope`, `survey`, `triage`, `autopsy`, `feed_tuner`); the rest are shared helpers
(`api`, `mathjax`, `shared_charts`, `results_sources`, `run_strip`, `canvas_base`, `diagram`,
`gauges`, `globe`, `process_anim`, `server_anim`, `tomo_anim`).
