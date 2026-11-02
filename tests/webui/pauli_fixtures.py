"""Builders adding a polarimetric primary to the synthetic preprocessing runs.

Writes the three-channel ``primary_polarimetric.npy`` artifact, whose
cross-polar channel is the run's primary SLC itself, its provenance sidecar
under ``meta`` and the ``artifacts`` entry of ``data/dataset.json``, following
the contract the Extract Polarimetry entry writes, and loads such a run into a
cube explorer.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from tests.webui.conftest         import load_cube
from tests.webui.preproc_fixtures import make_preproc_run, open_runs

from cube_explorer import CubeExplorer

PAULI_WINDOW = (2, 2)


def add_polarimetry(run_dir: Path, seed: int = 5) -> np.ndarray:
    """Writes a polarimetric primary over the run's footprint and lists it in the layout.

    Args:
        run_dir : Preprocessing run directory written by ``make_preproc_run``.
        seed    : Seed of the generator filling the co-polar channels.

    Returns:
        The written complex64 stack of shape (3, azimuth, range), ordered HH, cross-polar, VV.
    """
    rng     = np.random.default_rng(seed)
    primary = np.load(run_dir / "data" / "primary.npy")
    shape   = primary.shape

    hh    = rng.normal(size=shape) + 1j * rng.normal(size=shape)
    vv    = rng.normal(size=shape) + 1j * rng.normal(size=shape)
    stack = np.stack([hh, primary, vv]).astype(np.complex64)
    np.save(run_dir / "data" / "primary_polarimetric.npy", stack)

    sidecar = {"channels": ["hh", "xx", "vv"], "loader_channels": ["HH", "HV", "VH", "VV"], "cross_source": "hv+vh", "symmetrised": True, "window": list(PAULI_WINDOW)}
    (run_dir / "meta" / "primary_polarimetric.json").write_text(json.dumps(sidecar))

    layout_path = run_dir / "data" / "dataset.json"
    layout      = json.loads(layout_path.read_text())
    layout["artifacts"]["primary_polarimetric"] = "primary_polarimetric.npy"
    layout_path.write_text(json.dumps(layout))

    return stack


def loaded_polarimetric_run(base: Path, **kwargs) -> tuple[CubeExplorer, str, np.ndarray]:
    """Builds one preprocessing run with a polarimetric primary and loads it.

    Args:
        base     : Parent directory for the generated run.
        **kwargs : Forwarded to ``make_preproc_run``.

    Returns:
        Tuple of the explorer, the loaded cube id and the written polarimetric stack.
    """
    run_dir = make_preproc_run(base, **kwargs)
    stack   = add_polarimetry(run_dir)

    explorer, run_ids = open_runs(base, expected=1)
    load_cube(explorer, run_ids[0])

    return explorer, run_ids[0], stack
