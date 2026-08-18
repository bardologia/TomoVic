# DLR-TomoSAR

Deep-learning estimation of Gaussian-mixture elevation profiles from F-SAR tomographic
stacks. The repository holds the processing, training and inference pipelines, the
configuration layer that drives them, a local web console for launching and watching
runs, about 5100 tests, and the slide decks under `docs/presentations/`.

This file is the setup guide. Follow it top to bottom on a fresh clone.

## What you need

A Linux machine with an NVIDIA GPU and driver for anything that trains, infers or fits
parameters. The tests and the web console run fine on CPU. You also need conda, and
`tectonic` if you want to rebuild the slide decks.

Two things are deliberately not in the repository: the F-SAR data and the PyRAT
checkout that reads it. Section 5 says where they plug in. Everything up to and
including section 4 works without them.

## 1. Environment

```bash
git clone git@github.com:bardologia/DLR-TomoSAR.git
cd DLR-TomoSAR

conda create -n Dune python=3.11
conda activate Dune

pip install -r requirements.txt
pip install "h5py>=3.11" "jax>=0.4.30" pytest==9.0.3 pyflakes==3.4.0
```

Keep the name `Dune` unless you have a reason not to. `webui/run.sh` looks for
`~/miniconda3/envs/Dune/bin/python` first and only then falls back to conda base and
system `python3`, so a differently named env means the console may start on the wrong
interpreter.

`requirements.txt` pins `torch==2.11.0` but not a CUDA build, so the line above installs
whichever wheel PyPI serves by default. The three environments do not all end up on the
same build, and each one names its own where it is set:

- the reference workstation runs `2.11.0+cu130`,
- the Charliecloud image installs `cu128`, pinned in `Dockerfile`,
- the Terrabyte env installs `cu128`, pinned in `scripts/terrabyte_bootstrap.sh`.

If your driver needs a specific build, install torch from the matching PyTorch index
first and then run the requirements file, which will leave the existing torch alone.
Check which build you ended up with before assuming a CUDA problem is a driver problem.

The second pip line covers the optional extras declared in `pyproject.toml`: `h5py` for
the processing pipeline, `jax` for the sigma-fitting kernel, `pytest` and `pyflakes`
for development.

Check the result:

```bash
python -c "import torch; print(torch.__version__, torch.cuda.is_available())"
```

You do not have to install the project itself. Every entry point puts the repository
root on `sys.path`, so run scripts from the repository root and imports resolve.

## 2. Run the tests

```bash
python -m pytest -q
```

About 5100 tests once parametrization is expanded; `pytest --collect-only -q` prints the
exact number. Anything that needs the real SAR stack is marked `real_data` and skips
itself when `test_data/` is missing, so a clean clone should come out green. That run is
your proof the environment is correct. The markers (`real_data`, `slow`) are declared in
`pyproject.toml` under `[tool.pytest.ini_options]` with `strict_markers`, so a mistyped
marker fails collection instead of quietly running in the wrong lane.

If you were given the real test stack, put it at `test_data/` with `data/`, `meta/` and
`params/params_k5_lam0.01_sig4_sigma/` inside. `tests/conftest.py` looks for
`test_data/data/dataset.json` and unlocks the real-data tests once it exists. The
directory is gitignored and stays roughly 1 GB.

## 3. Point the configuration at your machine

The defaults are the DLR server paths (`/ste/rnd/User/vice_vi/...`), so on any other
machine you override them. There is no config file to edit before a run. Each entry
point builds a configuration dataclass and hands it to `ConfigCli`, which exposes every
leaf field as a command-line flag.

Ask any script what it accepts:

```bash
python main/training/train_backbone.py --help-config
```

Then override what you need:

```bash
python main/training/train_backbone.py \
  --paths.dataset_path /my/dataset \
  --paths.parameters_path /my/dataset/params/params_k2_lam0_sig4_sigma_mu_amp/parameters.npy \
  --logdir /my/runs/backbone \
  --training.epochs 10 \
  --gpu 0
```

Nested fields use dots, values are coerced to the declared type, and an unrecognised
flag stops the run instead of being ignored. Besides the config fields there is a fixed
set of bootstrap flags: `--help-config`, `--detach` (alias `--nohup`), `--gpu`,
`--resume`, `--trial`, `--worker`, `--model`, `--n-trials`, `--study-name`,
`--storage-url`, `--run-tag`, `--run-dir`, `--fold`, `--split`.

To change a default for good, edit the dataclass under `configuration/`. Never put
values in the `main/` scripts.

## 4. Start the web console

```bash
webui/run.sh          # http://127.0.0.1:8765
webui/run.sh 9000     # different port
```

The HTTP layer is standard library only, but the console runs inside the project
environment: the cube explorer, fit lab, model probe and training-curve readers are
imported at boot, so numpy, matplotlib, scipy, torch, scikit-image, tensorboard and
psutil all have to be there. `run.sh` picks the `Dune` interpreter for exactly that
reason. The console lists the `main/` entry points, renders each one's configuration
fields as typed controls, shows the exact command it will run, and streams the output
back live. It also carries the run leaderboard, the results and cube browsers, the fit
lab, and server telemetry. `webui/README.md` documents every tab.

The frontend pulls MathJax, GSAP, highlight.js and xterm.js from a CDN. Offline it still
works, with plain text where the equations would be.

## 5. The data pipeline

With real data present, the order is:

1. `main/processing/pre_process.py` turns an F-SAR SLC stack into a preprocessing
   dataset: an interferometric stack, Capon tomograms and the metadata that describes
   them. This is the only step with an external dependency. It selects the stack with
   `--fusar_project_path` (the F-SAR project CSV) under `--base_directory`, and it
   dispatches `generate_interferograms.py` and `generate_tomogram.py` into a second
   conda environment, `--tomogram_env_name`, default `stetools`. That second env is the
   one carrying PyRAT and its GDAL stack; the checkout path itself is
   `PathConfig.pyrat_directory` in `configuration/sar/processing_config.py`. It also
   carries `STEtools`, which `tools/baselines/reading.py` imports to read the DLR
   reference products. On the DLR server `stetools` already exists. Anywhere else you
   have to build it yourself around your own PyRAT and STEtools checkouts.
2. `main/processing/extract_params.py` runs the GPU Gaussian fit over every profile and
   writes `parameters.npy` together with `param_extraction_meta.json` beside it.
   Downstream code reads `k_max` and the preprocessing constants from that meta file and
   raises if it is absent, so never move a parameters file away from it.
3. `main/training/train_backbone.py` trains on the (dataset, parameters) pair. The same
   shape applies to `train_dual.py`, `train_unrolled.py`, `train_jepa.py` and the two
   autoencoder entries.
4. `main/inference/infer_backbone.py` and its siblings write cubes, `metrics.json` and a
   `report.md` into the run directory, which the console then browses.

If a PyRAT import fails with something that looks like a GDAL error, it is a loader
environment problem, not a missing package. `PyRatEnvironment` puts the conda `lib`
directory on `LD_LIBRARY_PATH` and sets `QT_QPA_PLATFORM=offscreen` before the import,
which only works if you go through the launchers rather than importing PyRAT yourself.

## 6. Rebuild the slide decks

`docs/presentations/` is the tracked copy of the decks. The 50 result figures they use
are vendored into `docs/presentations/figures/`, so this copy compiles in a fresh clone
with no run outputs present.

```bash
cd docs/presentations/full_project_story
tectonic full_project_story.tex      # the full deck, 178 pages
tectonic sub_07_loss_theory.tex      # one of ten thematic sub-decks

cd ../project_status
tectonic project_status.tex          # the short status deck, 17 pages
```

The built PDFs are committed as well, so you can read them without a LaTeX toolchain.
Slides live in `full_project_story/sections/*.tex` and are shared by the full deck and
every sub-deck, so edit them there and never in the wrapper files. `BUILD.md` in that
directory carries the deck structure, the design log and the page count of the last
build, which is the number to check a fresh build against.

The working copy at `presentations/` is gitignored and reads its figures straight out of
`results/`. It is a working copy only, and the two are synchronised by hand in one
direction: `docs/presentations/` is authoritative, `presentations/` is copied from it. A
deck compiled in the working copy after the tracked tree has moved on will contain deleted
sections and placeholder frames. `BUILD.md` in the tracked tree opens with a section saying
which tree it is; if the copy under `presentations/` lacks it, that copy is stale.

## 7. Run on the LRZ Terrabyte cluster

Training and benchmarking also run on the LRZ Terrabyte HPDA cluster through SLURM. This
is optional; nothing above depends on it.

First set up the SSH aliases the tooling expects, `terrabyte` for interactive logins and
`terrabyte-key` for key authentication:

```bash
python scripts/setup_terrabyte_ssh.py --user <lrz-id>
```

On the cluster, build the environment once. Two runtimes are available; pick one, either
the micromamba env or the Charliecloud container:

```bash
scripts/terrabyte_bootstrap.sh Dune      # micromamba env, installs the project editable
scripts/terrabyte_container.sh build     # Charliecloud image from the Dockerfile
scripts/terrabyte_container.sh inject    # run inside a GPU job, adds the NVIDIA driver
```

The image carries the dependencies only, not the source. Jobs read the checkout from the
cluster filesystem, which is why every generated sbatch script sets `#SBATCH -D` to the
repository root; a `ch-run` started from any other directory fails on `import tools`.

Submit one job, or fan a sweep out over the units of an experiment:

```bash
python scripts/submit_terrabyte.py main/training/train_backbone.py --gpus 1 --time 24:00:00
python scripts/sweep_terrabyte.py main/experiments/benchmark.py --limit 0
```

Both take the same config overrides as the local entry points, plus the resource flags
(`--gpus`, `--cpus`, `--mem`, `--time`, `--partition`, `--account`, `--mail`, `--env`,
`--container`, `--log-root`, `--dry-run`). `--dry-run` writes the sbatch script without
submitting it, which is the way to inspect what a submission would do. Runs land on
cluster scratch and the sbatch scripts and job output land under `logs/terrabyte/`.

The console drives all of this from the Terrabyte tab: cluster load, your queue, job logs,
and pulling finished runs back to this machine. A launch page can also target the cluster
instead of the local GPU. That path requires the working tree to be committed and pushed:
it adds a per-commit git worktree on the cluster and runs the job from there, so the code
that ran is always identifiable.

## Repository map

```
main/           entry points, one per verb and model type; nothing but wiring
configuration/  dataclasses holding every default
pipelines/      the pipelines behind the entry points
models/         backbones, heads, blocks
tools/          shared components (logger, training, metrics, SAR, monitoring)
webui/          the control console, stdlib HTTP server plus static frontend
tests/          about 5100 tests, real-data ones skip without test_data/
scripts/        maintenance and migration utilities, plus the Terrabyte submitters
docs/           the tracked presentations
notes/          model and design notes
```

## Housekeeping

`./clean.sh` removes `__pycache__` and `.pytest_cache`, which git never cleans for you.

Generated output stays out of git: `runs/`, `logs/`, `results/`, `test_data/` and the
working `presentations/` are all ignored. Keep run outputs outside the repository.

`scripts/generate_state_dict_baseline.py` regenerates `tests/state_dict_baseline.json`.
Run it only for an intentional architecture change, and commit it on its own.
