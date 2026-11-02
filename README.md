# TomoVic

TomoVic, the Tomography Visualization Console, is a preprocessing pipeline and web
console for SAR tomography data. It was lifted out of a working research codebase and stripped of everything related to machine
learning: what is left is the tooling to turn an F-SAR stack into a tomographic cube via
PyRAT, and a local web console to explore the result: cube slices, transects, the DEM,
the SLC amplitude, the acquisition geometry on a 3D globe, and the figures and reports
the pipeline writes.

## What you need

A Linux machine with conda. Nothing here needs a GPU. Tomogram and interferogram
generation run inside a separate conda environment that has PyRAT installed (the
`stetools` environment on the reference machine); everything else, including the console
and the tests, runs in the project environment.

## 1. Environment

```bash
conda create -n Dune python=3.11
conda activate Dune

python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m pip install pytest==9.0.3 pyflakes==3.4.0
```

Use `python -m pip`, not the bare `pip` command: on shared machines `pip` can resolve to
the system pip even inside an activated env, and the system Python then rejects the pins.
The pins need Python 3.11 or newer: `numpy==2.4.3` publishes no wheels for older Pythons,
so an install attempt from Python 3.10 or below fails with "No matching distribution
found for numpy". Two symptoms identify that situation: pip printing "Defaulting to user
installation because normal site-packages is not writeable", and `python -V` inside the
env not reporting 3.11. In the second case the env lacks its own Python; recreate it with
the version pinned as above.

Keep the name `Dune` unless you have a reason not to: `webui/run.sh` and
`ProjectPaths.PRIORITY` in `webui/project_paths.py` look for that environment first when
picking the console interpreter. The PyRAT environment name is a config field
(`--processing.tomogram_env_name`), so point it at whatever environment holds your PyRAT
install.

You do not have to install the project itself. Every entry point puts the repository
root on `sys.path`, so run scripts from the repository root and imports resolve.

## 2. Preprocess a stack

```bash
python main/processing/pre_process.py \
    --processing.fusar_project_path /path/to/fsar/project \
    --processing.stack_identifier   <stack> \
    --entry.crop.azimuth_start 1000 --entry.crop.azimuth_end 3000 \
    --entry.crop.range_start   500  --entry.crop.range_end   1500
```

Every config field is a CLI flag; `--help-config` prints the full tree. The pipeline
runs three stages: Capon beamforming of the tomogram (in the PyRAT environment, split
into azimuth subsections and concatenated), interferogram generation with the DEM phase
removed, and the per-pixel acquisition geometry. The output is a run directory whose
`data/dataset.json` lists the artifacts: `tomogram_full.npy`, `dem_full.npy`,
`primary.npy`, the secondaries and interferograms, and the track metadata under `meta/`.
Leave all four crop fields at zero to process the whole scene; the pipeline measures the
extent of the primary SLC and crops to it.

`main/analysis/analyze_preprocessing.py` re-renders the overview figures and value
distributions of an existing run, and `main/analysis/compare_preprocessing_trials.py`
compares runs that differ by multilook window.

`main/processing/extract_params.py` fits per-pixel Gaussian mixtures to the tomogram
profiles, producing a parametrized tomogram: `params/<tag>/parameters.npy` under the
run, holding amplitude, mean and width per component. The fit kernels run on jax
(`pip install "tomovic[fitting]"`, CPU is fine), and
`main/analysis/analyze_param_extraction.py` renders its figures and fit report.

`main/processing/extract_polarimetry.py` reads the primary pass of each selected run
again in every polarisation through PyRAT, over the crop the run was built from, and
stores it as the `primary_polarimetric` artifact. That artifact is what the Cube tab's
Pauli view decomposes. It needs the PyRAT environment, like the tomogram stage.

## 3. The console

```bash
webui/run.sh            # or: python webui/serve.py --port 8765
```

Open the printed URL. The Cube tab is the main viewer: open a preprocessing run
directory (anything holding `data/dataset.json`) and browse elevation, azimuth and range
slices, plane cuts, transects, the DEM grid, the point cloud, and the scene on a Cesium
globe with the flight tracks drawn from the acquisition geometry. When the run holds a
parameter extraction, the parametrized tomogram appears as a second source next to the
raw Capon cube, with the fitted components readable per pixel. When the run holds the
polarimetric artifact, the Pauli view shows the decomposition map with per-pixel
readouts and the scene balance, and the globe can drape the Pauli map on the terrain and
colour the scatterers by scattering mechanism. The Slices tab picks points on the primary
SLC map, collects slices across runs into a basket, and exports the basket to a folder
or by mail. Results browses the figures, reports and logs a run wrote. Scripts, Launch
and Console launch and monitor the entry points from the browser, with the same config
form the CLI exposes; a finished or failed job can be relaunched with its request from
the Retry button on its console tile. Home shows the machine: CPU, memory, storage and
GPU readings with their history, the console's own log, the resource watchdog, and the
neighbour-impact panel that measures how much your processes stall other users. Jobs
launched from the console run at the chosen politeness level ("polite" by default).
Automatic throttling of your processes when you cause stall is off by default, because
it renices every process you own on the machine; switch it on from Home if you want it.
The Repo Map and Configuration tabs are curated documentation of the processing flow
and every config field.

## 4. Tests

```bash
python -m pytest
```

Most tests run on synthetic data. Tests marked `real_data` expect a preprocessed run
under `test_data/` (gitignored); they skip when it is absent. To use one, symlink or
copy a run directory there so that `test_data/data/dataset.json` exists.
