"""Tests for the cube explorer's Pauli decomposition view.

Covers the polarimetric block published with the cube, every map mode and
stretch, the pixel readout against a direct decomposition including the
channel ratios, the scene summary and its window-invariant span shares, the
reflect boundary at the edge of the run's footprint, the per-context cache,
window clamping, no-data margins, the absence of the block without the
artifact, the loud load failure when the artifact is listed but half written
or covers another footprint, the load stage booked for it, the slant and
ground spacings the map's aspect is drawn from, and the decomposition of the
real test_data run when its preprocessing carries a polarimetric primary.
"""

from __future__ import annotations

import io
import json
import threading
import time

import matplotlib.pyplot as plt
import numpy as np
import pytest

from scipy.ndimage import uniform_filter

from cube_explorer                import CubeExplorer, LoadProgress, StampReader
from tests.webui.conftest         import N_AZ, N_RG, load_cube
from tests.webui.pauli_fixtures   import PAULI_WINDOW, add_polarimetry, loaded_polarimetric_run
from tests.webui.preproc_fixtures import loaded_run, make_preproc_run, open_runs
from tools.sar.geometry_field     import GeometryField
from tools.sar.polarimetry        import PauliDecomposer
from web_logger                   import WebLogger


def _failed_load(explorer, cube_id: str) -> dict:
    """Starts a load, waits for it to settle and returns the final status."""
    assert explorer.start_load(cube_id)["ok"]

    deadline = time.time() + 30
    while explorer.load_status()["state"] == "loading" and time.time() < deadline:
        time.sleep(0.05)

    return explorer.load_status()


def test_pauli_meta(tmp_path):
    """Checks the polarimetric block names the sidecar window, the components with colours and the modes."""
    explorer, _, _ = loaded_polarimetric_run(tmp_path)

    pauli = explorer.load_status()["cube"]["pauli"]

    assert pauli["window"] == list(PAULI_WINDOW)
    assert pauli["window_max"] == explorer.PAULI_WINDOW_MAX
    assert [component["key"] for component in pauli["components"]] == ["surface", "double", "volume"]
    assert all(component["color"].startswith("#") and component["label"] for component in pauli["components"])
    assert pauli["modes"] == ["rgb", "surface", "double", "volume", "dominant"]


def test_pauli_load_books_its_own_stage(tmp_path):
    """Checks the load timer names the Pauli stage beside the other artifact reads."""
    explorer, _, _ = loaded_polarimetric_run(tmp_path)

    stages = explorer.load_status()["cube"]["timings"]["stages"]

    assert set(stages) == {"full", "primary", "dem", "geocoding", "passes", "pauli"}


def test_pauli_map_renders_every_mode_and_guards(tmp_path):
    """Checks every mode renders under both stretches and unknown modes or cubes yield nothing."""
    explorer, cube_id, _ = loaded_polarimetric_run(tmp_path)

    for mode in explorer.PAULI_MODES:
        for shared in (True, False):
            png = explorer.pauli_png(cube_id, mode, 2, 2, shared)
            assert png and png[:4] == b"\x89PNG", (mode, shared)

    assert explorer.pauli_png(cube_id, "banana", 2, 2, True) is None
    assert explorer.pauli_png("wrong", "rgb", 2, 2, True) is None


def test_pauli_value_matches_direct_decomposition(tmp_path):
    """Checks the pixel readout equals a direct decomposition of the fixture stack at the same window."""
    explorer, cube_id, stack = loaded_polarimetric_run(tmp_path)

    powers = PauliDecomposer((3, 1)).powers(stack)
    db     = PauliDecomposer.decibel(powers)
    az, rg = 4, 2

    value = explorer.pauli_value_at(cube_id, az, rg, 3, 1)

    assert value["ok"] and value["window"] == [3, 1] and (value["az"], value["rg"]) == (az, rg)
    for index, key in enumerate(PauliDecomposer.COMPONENTS):
        assert value["db"][key] == pytest.approx(float(db[index, az, rg]), abs=1e-4)
        assert value["fractions"][key] == pytest.approx(float(powers[index, az, rg] / powers[:, az, rg].sum()), abs=1e-5)
    assert value["dominant"] == PauliDecomposer.COMPONENTS[int(np.argmax(powers[:, az, rg]))]
    assert value["valid"] is True
    assert sum(value["fractions"].values()) == pytest.approx(1.0, abs=1e-5)

    hh_power = uniform_filter((np.abs(stack[0]) ** 2).astype(np.float32), (3, 1))
    vv_power = uniform_filter((np.abs(stack[2]) ** 2).astype(np.float32), (3, 1))
    decibel  = lambda power: 10.0 * np.log10(power)
    assert value["span_db"] == pytest.approx(decibel(powers[:, az, rg].sum()), abs=1e-3)
    assert value["hh_vv_db"] == pytest.approx(decibel(hh_power[az, rg]) - decibel(vv_power[az, rg]), abs=1e-3)
    assert value["hv_hh_db"] == pytest.approx(decibel(powers[2, az, rg] / 2.0) - decibel(hh_power[az, rg]), abs=1e-3)

    clipped = explorer.pauli_value_at(cube_id, 999, -5, 3, 1)
    assert (clipped["az"], clipped["rg"]) == (N_AZ - 1, 0)


def test_pauli_footprint_corner_uses_the_reflect_boundary(tmp_path):
    """Checks the corner of a run, where the artifact holds no neighbours beyond the footprint, matches the decomposition of the whole stack."""
    explorer, cube_id, stack = loaded_polarimetric_run(tmp_path)

    decomposer = PauliDecomposer((3, 3))
    full       = decomposer.decibel(decomposer.powers(stack))

    for az, rg in ((0, 0), (N_AZ - 1, N_RG - 1), (1, 1)):
        value = explorer.pauli_value_at(cube_id, az, rg, 3, 3)
        for index, key in enumerate(PauliDecomposer.COMPONENTS):
            assert value["db"][key] == pytest.approx(float(full[index, az, rg]), abs=1e-4), (az, rg, key)


def test_pauli_summary_reports_balance_and_bounds(tmp_path):
    """Checks the summary's span shares equal the normalised Pauli energies, barely move with the window, and the stretch bounds follow the requested mode."""
    explorer, cube_id, stack = loaded_polarimetric_run(tmp_path)

    shared = explorer.pauli_summary(cube_id, 2, 2, True)

    assert shared["ok"] and shared["n_pixels"] == N_AZ * N_RG and shared["n_nodata"] == 0 and shared["window"] == [2, 2]
    assert sum(shared["scene_share"].values()) == pytest.approx(1.0, abs=1e-5)
    assert sum(shared["dominant_share"].values()) == pytest.approx(1.0, abs=1e-6)
    assert shared["bounds"]["surface"] == shared["bounds"]["double"] == shared["bounds"]["volume"]
    assert all(np.isfinite(shared[key]) for key in ("span_db", "hh_vv_db", "hv_hh_db"))

    energy = (np.abs(PauliDecomposer.vector(stack)) ** 2).sum(axis=(1, 2))
    single = explorer.pauli_summary(cube_id, 1, 1, True)
    assert [single["scene_share"][key] for key in PauliDecomposer.COMPONENTS] == pytest.approx(energy / energy.sum(), abs=1e-5)

    looked = explorer.pauli_summary(cube_id, 3, 3, True)
    assert [looked["scene_share"][key] for key in PauliDecomposer.COMPONENTS] == pytest.approx([single["scene_share"][key] for key in PauliDecomposer.COMPONENTS], abs=1e-3)

    per_channel = explorer.pauli_summary(cube_id, 2, 2, False)
    assert all(low < high for low, high in per_channel["bounds"].values())


def test_pauli_cache_keeps_recent_windows_and_computes_a_window_once(tmp_path, monkeypatch):
    """Checks the per-context cache evicts the least recently used window and concurrent requests for one window decompose it once."""
    explorer, cube_id, _ = loaded_polarimetric_run(tmp_path)
    ctx                  = explorer.loaded["pauli"]

    for window in ((2, 2), (3, 1), (4, 4)):
        explorer.pauli_summary(cube_id, window[0], window[1], True)

    assert ctx["cache"].size() == explorer.PAULI_CACHE_WINDOWS
    assert ctx["cache"].get((3, 1)) is not None and ctx["cache"].get((4, 4)) is not None
    assert ctx["cache"].get((2, 2)) is None

    ctx["cache"].clear()
    calls    = []
    original = PauliDecomposer.powers

    def counting(self, stack):
        calls.append(self.window)
        time.sleep(0.05)
        return original(self, stack)

    monkeypatch.setattr(PauliDecomposer, "powers", counting)

    threads = [threading.Thread(target=lambda: explorer.pauli_summary(cube_id, 5, 5, True)), threading.Thread(target=lambda: explorer.pauli_png(cube_id, "rgb", 5, 5, True))]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert calls == [(5, 5)]


def test_pauli_window_is_clamped(tmp_path):
    """Checks a window below one or above the maximum is clamped per axis."""
    explorer, cube_id, _ = loaded_polarimetric_run(tmp_path)

    assert explorer.pauli_value_at(cube_id, 0, 0, 0, 500)["window"] == [1, explorer.PAULI_WINDOW_MAX]


def test_pauli_absent_without_artifact(tmp_path):
    """Checks a run that lists no polarimetric primary publishes no block and answers nothing."""
    explorer, cube_id = loaded_run(tmp_path, with_passes=True, pass_labels=("T01", "T02", "T03"))

    assert explorer.load_status()["cube"]["pauli"] is None
    assert explorer.pauli_png(cube_id, "rgb", 1, 1, True) is None
    assert explorer.pauli_value_at(cube_id, 0, 0, 1, 1)["ok"] is False
    assert explorer.pauli_summary(cube_id, 1, 1, True)["ok"] is False


def test_pauli_listed_without_sidecar_fails_the_load(tmp_path):
    """Checks an artifact listed in the layout but missing its sidecar fails the cube load loudly."""
    run_dir = make_preproc_run(tmp_path)
    add_polarimetry(run_dir)
    (run_dir / "meta" / "primary_polarimetric.json").unlink()

    explorer, run_ids = open_runs(tmp_path, expected=1)
    status            = _failed_load(explorer, run_ids[0])

    assert status["state"] == "error"
    assert "sidecar" in status["error"]


def test_pauli_on_another_footprint_fails_the_load(tmp_path):
    """Checks a polarimetric primary whose grid differs from the tomogram footprint fails the load instead of misaligning the maps."""
    run_dir = make_preproc_run(tmp_path)
    stack   = add_polarimetry(run_dir)
    np.save(run_dir / "data" / "primary_polarimetric.npy", stack[:, 1:, :])

    explorer, run_ids = open_runs(tmp_path, expected=1)
    status            = _failed_load(explorer, run_ids[0])

    assert status["state"] == "error"
    assert "footprint" in status["error"]


def test_pauli_map_colormap_guard(tmp_path):
    """Checks a single component renders with any allowed colormap and refuses an unknown one."""
    explorer, cube_id, _ = loaded_polarimetric_run(tmp_path)

    for cmap in explorer.CMAPS:
        assert explorer.pauli_png(cube_id, "volume", 2, 2, True, cmap)[:4] == b"\x89PNG"
    assert explorer.pauli_png(cube_id, "volume", 2, 2, True, "rainbow") is None


def test_pauli_no_data_margin_is_masked(tmp_path):
    """Checks zero-filled columns count as no data: excluded from the summary counts, reported as no dominant mechanism and painted black in the dominant map."""
    run_dir = make_preproc_run(tmp_path)
    stack   = add_polarimetry(run_dir)
    stack[:, :, N_RG - 2:] = 0.0
    np.save(run_dir / "data" / "primary_polarimetric.npy", stack)

    explorer, run_ids = open_runs(tmp_path, expected=1)
    cube_id           = run_ids[0]
    load_cube(explorer, cube_id)

    summary = explorer.pauli_summary(cube_id, 1, 1, False)
    assert summary["n_pixels"] == N_AZ * (N_RG - 2)
    assert summary["n_nodata"] == N_AZ * 2
    assert sum(summary["scene_share"].values()) == pytest.approx(1.0, abs=1e-5)
    assert sum(summary["dominant_share"].values()) == pytest.approx(1.0, abs=1e-6)
    assert all(low > -100.0 for low, _ in summary["bounds"].values())

    margin = explorer.pauli_value_at(cube_id, 0, N_RG - 1, 1, 1)
    assert margin["valid"] is False and margin["dominant"] is None
    assert sum(margin["fractions"].values()) == 0.0

    interior = explorer.pauli_value_at(cube_id, 0, 0, 1, 1)
    assert interior["valid"] is True and interior["dominant"] in PauliDecomposer.COMPONENTS

    image = plt.imread(io.BytesIO(explorer.pauli_png(cube_id, "dominant", 1, 1, False)))
    assert image[:, N_RG - 1, :3].max() == 0.0
    assert image[:, 0, :3].max() > 0.0


def test_spacing_without_geometry_field_is_slant_only(tmp_path):
    """Checks a run with track parameters but no geometry field publishes the slant spacings without a ground spacing."""
    explorer, _ = loaded_run(tmp_path, with_spacing=True)

    assert explorer.load_status()["cube"]["spacing"] == {"az": 0.4, "rg": 0.6}


def test_spacing_adds_incidence_and_ground_range_from_the_geometry_field(tmp_path):
    """Checks a saved geometry field yields the mean incidence over the run's range columns and the ground-range spacing."""
    run_dir = make_preproc_run(tmp_path, with_spacing=True)
    look    = np.linspace(0.5, 0.7, N_RG)
    field   = GeometryField(labels=["T01"], reference="T01", wavelength=0.23, azimuth_start=0, range_start=0, look_angle=look, slant_range=np.full(N_RG, 3300.0), baseline_h=np.zeros((1, N_AZ)), baseline_v=np.zeros((1, N_AZ)))
    field.save(run_dir / "meta" / GeometryField.FILENAME)

    explorer, run_ids = open_runs(tmp_path, expected=1)
    load_cube(explorer, run_ids[0])
    spacing = explorer.load_status()["cube"]["spacing"]

    assert spacing["az"] == 0.4 and spacing["rg"] == 0.6
    assert spacing["incidence_deg"] == pytest.approx(np.degrees(look.mean()))
    assert spacing["ground_rg"] == pytest.approx(0.6 / np.sin(look.mean()))


def test_spacing_reads_the_look_angles_of_the_cropped_columns(tmp_path):
    """Checks a geometry field covering a wider scene is indexed at the run's global crop, and one that misses the crop fails the load."""
    run_dir = make_preproc_run(tmp_path, with_spacing=True)
    layout  = json.loads((run_dir / "data" / "dataset.json").read_text())
    layout["global_crop"] = [0, N_AZ, 3, 3 + N_RG]
    (run_dir / "data" / "dataset.json").write_text(json.dumps(layout))

    look  = np.linspace(0.4, 0.8, N_RG + 5)
    field = GeometryField(labels=["T01"], reference="T01", wavelength=0.23, azimuth_start=0, range_start=1, look_angle=look, slant_range=np.full(N_RG + 5, 3300.0), baseline_h=np.zeros((1, N_AZ)), baseline_v=np.zeros((1, N_AZ)))
    field.save(run_dir / "meta" / GeometryField.FILENAME)

    explorer, run_ids = open_runs(tmp_path, expected=1)
    load_cube(explorer, run_ids[0])

    assert explorer.load_status()["cube"]["spacing"]["incidence_deg"] == pytest.approx(np.degrees(look[2:2 + N_RG].mean()))

    short = GeometryField(labels=["T01"], reference="T01", wavelength=0.23, azimuth_start=0, range_start=1, look_angle=look[:N_RG], slant_range=np.full(N_RG, 3300.0), baseline_h=np.zeros((1, N_AZ)), baseline_v=np.zeros((1, N_AZ)))
    short.save(run_dir / "meta" / GeometryField.FILENAME)

    fresh, fresh_ids = open_runs(tmp_path, expected=1)
    status           = _failed_load(fresh, fresh_ids[0])

    assert status["state"] == "error"
    assert "geometry_field" in status["error"]


@pytest.mark.real_data
def test_real_run_decomposes_its_polarimetric_primary(test_data_dir, dataset_json):
    """Checks the test_data run's polarimetric primary decomposes into a balanced scene summary; skips when that run carries none."""
    if "primary_polarimetric" not in dataset_json["artifacts"]:
        pytest.skip("the test_data run carries no polarimetric primary; run Extract Polarimetry on it to enable this test")

    explorer = CubeExplorer(WebLogger())
    reader   = StampReader(test_data_dir, LoadProgress())
    shape    = np.load(reader.artifact_path("primary"), mmap_mode="r").shape
    ctx      = explorer._load_polarimetry(reader, shape[0], shape[1])
    entry    = explorer._pauli_powers(ctx, ctx["window"])

    assert entry["powers"].shape == (3, shape[0], shape[1])
    assert np.count_nonzero(entry["valid"]) > 0.5 * entry["valid"].size
    assert np.all(np.isfinite(entry["db"][:, entry["valid"]]))
