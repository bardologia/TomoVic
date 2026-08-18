"""Builders for the synthetic preprocessing runs the cube explorer tests open.

Writes run directories following the ``data/dataset.json`` layout the
preprocessing pipeline produces, with a full tomogram, a primary SLC, an
optional DEM, optional track parameters and optional Gaussian parameter runs
under ``params/<tag>``, and provides helpers that register a runs root and
drive CubeExplorer loading over those runs.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import numpy as np

from tests.webui.conftest import N_AZ, N_ELEV, N_RG, load_cube, make_geo_fields

from cube_explorer import CubeExplorer
from web_logger    import WebLogger

HEIGHT_RANGE = (-10.0, 30.0)


def write_track_parameters(run_dir: Path, with_geo: bool) -> None:
    """Writes meta/track_parameters.json for a three-track stack.

    Args:
        run_dir: Preprocessing run directory receiving the ``meta`` tree.
        with_geo: Whether the geocoding fields of a synthetic track are merged
            into every per-track record.
    """
    per_track = {"T01": {"ps_az": 0.4}, "T02": {"ps_az": 0.41}, "T03": {"ps_az": 0.42}}

    if with_geo:
        fields = make_geo_fields()
        per_track["T01"].update(fields)
        per_track["T02"].update(fields)
        per_track["T03"].update(fields)

    payload = {
        "labels"      : ["T01", "T02", "T03"],
        "reference"   : "T01",
        "shared"      : {"ps_rg": 0.6},
        "per_track"   : per_track,
        "track_files" : [],
    }
    (run_dir / "meta" / "track_parameters.json").write_text(json.dumps(payload))


def make_preproc_run(base: Path, group: str = "group", name: str = "run_a", seed: int = 0, tomogram: np.ndarray | None = None, with_dem: bool = False, with_geo: bool = False, with_spacing: bool = False, pass_labels: tuple | None = ("T01", "T02"), tomogram_tag: str = "capon") -> Path:
    """Writes one synthetic preprocessing run directory.

    Args:
        base: Root the run tree is created under.
        group: Intermediate folder between the root and the run; empty for none.
        name: Run directory name.
        seed: Seed of the generator filling the tomogram and primary.
        tomogram: Cube of shape (N_ELEV, N_AZ, N_RG) written as the full
            tomogram; a random cube when None.
        with_dem: Whether a DEM (with one NaN pixel) is written.
        with_geo: Whether the DEM plus geocoding track parameters are written.
        with_spacing: Whether track parameters without geocoding are written.
        pass_labels: Pass labels recorded in the layout, or None for a run
            without a pass labelling.
        tomogram_tag: Tomogram tag recorded in the layout.

    Returns:
        Path of the created preprocessing run directory.
    """
    rng     = np.random.default_rng(seed)
    run_dir = base / group / name if group else base / name
    (run_dir / "data").mkdir(parents=True)
    (run_dir / "meta").mkdir(parents=True)

    cube = rng.random((N_ELEV, N_AZ, N_RG)).astype(np.float32) if tomogram is None else np.asarray(tomogram, dtype=np.float32)
    np.save(run_dir / "data" / "tomogram_full.npy", cube)

    primary = rng.normal(size=(N_AZ, N_RG)) + 1j * rng.normal(size=(N_AZ, N_RG))
    np.save(run_dir / "data" / "primary.npy", primary)

    if with_dem or with_geo:
        dem       = np.full((N_AZ, N_RG), 680.0, dtype=np.float32)
        dem[2, 3] = np.nan
        np.save(run_dir / "data" / "dem_full.npy", dem)

    layout = {
        "global_crop"        : [0, N_AZ, 0, N_RG],
        "dataset_type"       : "raw",
        "tomogram_tag"       : tomogram_tag,
        "parameter_tag"      : "p1",
        "max_amplitude_clip" : 3.0,
        "pass_labels"        : list(pass_labels) if pass_labels is not None else None,
        "artifacts"          : {
            "tomogram_full"  : "tomogram_full.npy",
            "dem_full"       : "dem_full.npy",
            "primary"        : "primary.npy",
            "secondaries"    : "secondaries.npy",
            "interferograms" : "interferograms.npy",
            "track_profiles" : "track_profiles.npy",
        },
    }
    (run_dir / "data" / "dataset.json").write_text(json.dumps(layout))

    state = {"tomogram_config": {"height_range": list(HEIGHT_RANGE)}}
    (run_dir / "meta" / "config_state.json").write_text(json.dumps(state))

    if with_geo or with_spacing:
        write_track_parameters(run_dir, with_geo)

    return run_dir


def make_param_run(run_dir: Path, tag: str, k: int = 2, seed: int = 1, parameters: np.ndarray | None = None) -> Path:
    """Writes one synthetic Gaussian parameter run under a preprocessing run.

    Follows the on-disk schema of the parameter-extraction pipeline: a
    ``params/<tag>`` directory holding ``parameters.npy``,
    ``param_extraction_meta.json`` and ``fit_diagnostics.npz`` describing the
    parametrized tomogram fitted from the raw data.

    Args:
        run_dir: Preprocessing run directory receiving ``params/<tag>``.
        tag: Name of the parameter run directory.
        k: Number of Gaussian slots when the parameters are generated.
        seed: Seed of the generator filling the parameter cube.
        parameters: Parameter cube of shape (3 * k, N_AZ, N_RG) written as-is
            when given, interleaved per slot as amplitude, mean in metres and
            sigma in metres; its slot count overrides ``k``.

    Returns:
        Path of the created parameter run directory.
    """
    param_dir = run_dir / "params" / tag
    param_dir.mkdir(parents=True)

    if parameters is None:
        rng        = np.random.default_rng(seed)
        parameters = np.zeros((3 * k, N_AZ, N_RG), dtype=np.float32)
        for slot in range(k):
            parameters[3 * slot]     = rng.uniform(0.1, 1.0, (N_AZ, N_RG))
            parameters[3 * slot + 1] = rng.uniform(HEIGHT_RANGE[0], HEIGHT_RANGE[1], (N_AZ, N_RG))
            parameters[3 * slot + 2] = rng.uniform(1.0, 5.0, (N_AZ, N_RG))
    else:
        parameters = np.asarray(parameters, dtype=np.float32)
        k          = parameters.shape[0] // 3

    np.save(param_dir / "parameters.npy", parameters.astype(np.float32))
    np.savez(param_dir / "fit_diagnostics.npz", final_loss=np.zeros((N_AZ, N_RG), dtype=np.float32))

    meta = {
        "timestamp"           : "2026-08-18T00:00:00",
        "processed_data_path" : str(run_dir),
        "source_tomogram"     : str(run_dir / "data" / "tomogram_full.npy"),
        "height_range"        : list(HEIGHT_RANGE),
        "output_directory"    : str(param_dir),
        "output_prefix"       : "params",
        "output_suffix"       : tag,
        "parameters_npy"      : "parameters.npy",
        "diagnostics_npz"     : "fit_diagnostics.npz",
        "k_max"               : int(k),
        "lambda_k"            : 0.01,
        "sigma_init_divisor"  : 4.0,
        "activity_threshold"  : 0.001,
        "threshold_factor"    : 0.25,
        "truncation_index"    : N_ELEV,
        "fit_sigma"           : True,
        "fit_amplitude"       : False,
        "fit_mean"            : False,
        "fitting_method"      : "sigma_adam",
    }
    (param_dir / "param_extraction_meta.json").write_text(json.dumps(meta))

    return param_dir


def open_runs(base: Path, expected: int | None = None) -> tuple[CubeExplorer, list[str]]:
    """Registers a runs root and returns the explorer and the run ids under it.

    Args:
        base: Directory registered as the runs root.
        expected: Asserted number of discovered runs when given.

    Returns:
        Tuple of the explorer and the discovered run directory paths, sorted.
    """
    explorer    = CubeExplorer(WebLogger())
    root, error = explorer.roots.open(str(base))

    assert root is not None, error

    run_ids = sorted(str(marker.parent.parent) for marker in Path(base).rglob("data/dataset.json"))
    if expected is not None:
        assert len(run_ids) == expected, run_ids

    return explorer, run_ids


def loaded_run(base: Path, **kwargs) -> tuple[CubeExplorer, str]:
    """Builds one preprocessing run and returns the explorer with it loaded.

    Args:
        base: Parent directory for the generated run.
        **kwargs: Forwarded to ``make_preproc_run``.

    Returns:
        Tuple of the explorer and the loaded cube id.
    """
    run_dir = make_preproc_run(base, **kwargs)
    explorer, run_ids = open_runs(base, expected=1)

    assert run_ids == [str(run_dir)]
    load_cube(explorer, run_ids[0])

    return explorer, run_ids[0]


def loaded_param_run(base: Path, tag: str = "params_k2", k: int = 2, parameters: np.ndarray | None = None, **kwargs) -> tuple[CubeExplorer, str]:
    """Builds a run with one parameter run and loads both into an explorer.

    Args:
        base: Parent directory for the generated run.
        tag: Name of the parameter run written under the run.
        k: Number of Gaussian slots of the generated parameters.
        parameters: Optional explicit parameter cube of shape (3 * k, N_AZ, N_RG).
        **kwargs: Forwarded to ``make_preproc_run``.

    Returns:
        Tuple of the explorer and the loaded cube id.
    """
    run_dir = make_preproc_run(base, **kwargs)
    make_param_run(run_dir, tag, k=k, parameters=parameters)

    explorer, run_ids = open_runs(base, expected=1)
    assert explorer.start_load(run_ids[0], param_tag=tag)["ok"]

    deadline = time.time() + 30.0
    while explorer.load_status()["state"] == "loading" and time.time() < deadline:
        time.sleep(0.05)

    status = explorer.load_status()
    assert status["state"] == "ready", status

    return explorer, run_ids[0]
