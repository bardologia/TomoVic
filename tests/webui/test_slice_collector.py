"""Tests for the slice collector that exports elevation-profile slices across several runs.

Covers cube inspection (dimensions, available sources, intensity ranges), single-slice PNG
rendering with and without a colour-limit override, and the multi-run collect operation:
directory layout, run label disambiguation, shared colour limits, normalized-space output,
input validation and restoration of the global plot style.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from cube_explorer import SliceCollector
from web_logger    import WebLogger

from tests.webui.conftest import N_AZ, N_ELEV, N_RG, open_explorer


def _make_run(base: Path, group: str, name: str, stamp: str = "stamp_1", sources: tuple = ("pred", "gt", "reduced"), seed: int = 0) -> Path:
    """Creates an inference stamp holding random curve cubes and returns the stamp directory.

    Args:
        base: Root the run tree is created under.
        group: Optional intermediate folder between the root and the run.
        name: Run folder name.
        stamp: Inference stamp folder name.
        sources: Cube sources written, each as ``<source>_curves.npy`` of shape
            (elevation bins, azimuth samples, range samples).
        seed: Seed of the random generator filling the cubes.

    Returns:
        Path of the created ``inference/<stamp>`` directory.
    """
    rng       = np.random.default_rng(seed)
    run       = base / group / name if group else base / name
    stamp_dir = run / "inference" / stamp
    (stamp_dir / "cubes").mkdir(parents=True)

    (stamp_dir / "metrics.json").write_text(json.dumps({"x_axis_min": -10.0, "x_axis_max": 30.0}))
    for source in sources:
        np.save(stamp_dir / "cubes" / f"{source}_curves.npy", rng.random((N_ELEV, N_AZ, N_RG)).astype(np.float32))

    return stamp_dir


def _collector(base: Path) -> tuple[SliceCollector, list]:
    """Returns a collector over the cubes catalogued under ``base`` and their cube ids."""
    cubes, cube_ids = open_explorer(base)

    return SliceCollector(cubes, WebLogger()), cube_ids


def test_info_reports_dims_sources_and_intensity(tmp_path):
    """Cube info reports azimuth and range extents, the available sources and a non-degenerate intensity range each."""
    _make_run(tmp_path, "group", "run_a")
    collector, ids = _collector(tmp_path)

    info = collector.info(ids[0])
    assert info["ok"], info
    assert info["n_az"] == N_AZ and info["n_rg"] == N_RG
    assert info["sources"] == ["pred", "gt", "reduced"]
    assert set(info["intensity"]) == {"pred", "gt", "reduced"}
    assert all(pair[1] > pair[0] for pair in info["intensity"].values())


def test_info_rejects_ids_outside_catalogued_roots(tmp_path):
    """A cube id from a tree that was never catalogued is refused."""
    _make_run(tmp_path / "runs", "group", "run_a")
    foreign = _make_run(tmp_path / "foreign", "group", "run_b")

    collector, _ = _collector(tmp_path / "runs")
    assert not collector.info(str(foreign))["ok"]


def test_slice_png_serves_with_and_without_clim_override(tmp_path):
    """Range and azimuth slices render as PNG with or without explicit colour limits, while unknown source or axis returns nothing."""
    _make_run(tmp_path, "group", "run_a")
    collector, ids = _collector(tmp_path)

    plain  = collector.slice_png(ids[0], "pred", "range", az=3, rg=2)
    scaled = collector.slice_png(ids[0], "pred", "azimuth", az=3, rg=2, vmin=0.0, vmax=2.0)
    assert plain is not None and plain[:8] == b"\x89PNG\r\n\x1a\n"
    assert scaled is not None and scaled[:8] == b"\x89PNG\r\n\x1a\n"

    assert collector.slice_png(ids[0], "full", "range", az=0, rg=0) is None
    assert collector.slice_png(ids[0], "pred", "diagonal", az=0, rg=0) is None


def test_a_refused_slice_explains_itself_in_the_log(tmp_path, capsys):
    """An unknown cube id and a missing source each log the reason the slice was refused."""
    _make_run(tmp_path / "runs", "group", "run_a", sources=("pred",))
    foreign = _make_run(tmp_path / "foreign", "group", "run_b")

    collector, ids = _collector(tmp_path / "runs")
    capsys.readouterr()

    assert collector.slice_png(str(foreign), "pred", "range", az=0, rg=0) is None
    assert collector.slice_png(ids[0], "gt", "range", az=0, rg=0) is None

    logged = capsys.readouterr().out
    assert "unknown cube id" in logged
    assert "carries no 'gt' cube" in logged


def test_collect_refuses_an_existing_collection_name(tmp_path):
    """Reusing a collection name is refused instead of overwriting the earlier export."""
    _make_run(tmp_path, "group", "run_a", seed=0)
    collector, ids = _collector(tmp_path)

    assert collector.collect(ids, [{"az": 0, "rg": 0}], ["pred"], ["range"], name="twice")["ok"]

    again = collector.collect(ids, [{"az": 1, "rg": 1}], ["pred"], ["range"], name="twice")
    assert again["ok"] is False
    assert "already exists" in again["error"]


def test_collect_writes_figures_grouped_by_cut(tmp_path):
    """Figures land under point/axis/source folders, one file per run, and the manifest mirrors them."""
    _make_run(tmp_path, "group", "run_a", seed=0)
    _make_run(tmp_path, "group", "run_b", seed=1)
    collector, ids = _collector(tmp_path)

    result = collector.collect(ids, [{"az": 3, "rg": 2}], ["pred", "gt"], ["range", "azimuth"], name="my test")
    assert result["ok"], result
    assert result["runs"] == 2 and not result["missing"]

    out_dir = Path(result["dir"])
    assert out_dir == tmp_path / "slice_collections" / "my_test"

    expected = {
        f"az0003_rg0002/{axis}_{source}_physical/{run}.png"
        for axis in ("range", "azimuth")
        for source in ("pred", "gt")
        for run in ("run_a", "run_b")
    }
    assert set(result["files"]) == expected
    assert all((out_dir / rel).is_file() and (out_dir / rel).stat().st_size > 0 for rel in expected)

    manifest = json.loads((out_dir / "collection.json").read_text())
    assert {r["label"] for r in manifest["runs"]} == {"run_a", "run_b"}
    assert manifest["points"] == [{"az": 3, "rg": 2}]
    assert set(manifest["files"]) == expected


def test_collect_shared_clim_spans_all_runs(tmp_path):
    """Shared colour limits span the intensity ranges of every run, and are absent when per-run scaling is asked for."""
    _make_run(tmp_path, "group", "run_a", seed=0)
    _make_run(tmp_path, "group", "run_b", seed=1)
    collector, ids = _collector(tmp_path)

    intensities = [collector.info(i)["intensity"]["pred"] for i in ids]
    result      = collector.collect(ids, [{"az": 0, "rg": 0}], ["pred"], ["range"], shared=True, name="clim")
    assert result["ok"], result

    manifest = json.loads((Path(result["dir"]) / "collection.json").read_text())
    assert manifest["clims"]["pred"] == [min(p[0] for p in intensities), max(p[1] for p in intensities)]

    per_run = collector.collect(ids, [{"az": 0, "rg": 0}], ["pred"], ["range"], shared=False, name="perrun")
    assert json.loads((Path(per_run["dir"]) / "collection.json").read_text())["clims"]["pred"] is None


def test_collect_normalized_space_and_multiple_points(tmp_path):
    """Normalized-space collection writes one folder per requested azimuth/range point."""
    _make_run(tmp_path, "group", "run_a")
    collector, ids = _collector(tmp_path)

    points = [{"az": 1, "rg": 1}, {"az": 4, "rg": 2}]
    result = collector.collect(ids, points, ["pred"], ["range"], space="normalized", name="norm")
    assert result["ok"], result
    assert set(result["files"]) == {"az0001_rg0001/range_pred_normalized/run_a.png", "az0004_rg0002/range_pred_normalized/run_a.png"}


def test_collect_disambiguates_duplicate_run_names(tmp_path):
    """Runs sharing a name are labelled with their parent group."""
    _make_run(tmp_path, "group_a", "run", seed=0)
    _make_run(tmp_path, "group_b", "run", seed=1)
    collector, ids = _collector(tmp_path)

    result = collector.collect(ids, [{"az": 0, "rg": 0}], ["pred"], ["range"], name="dupes")
    assert result["ok"], result

    labels = {r["label"] for r in json.loads((Path(result["dir"]) / "collection.json").read_text())["runs"]}
    assert labels == {"group_a__run", "group_b__run"}


def test_collect_disambiguates_stamps_of_the_same_run(tmp_path):
    """Two stamps of one run are labelled with their stamp name."""
    _make_run(tmp_path, "group", "run", stamp="stamp_1", seed=0)
    _make_run(tmp_path, "group", "run", stamp="stamp_2", seed=1)
    collector, ids = _collector(tmp_path)

    result = collector.collect(ids, [{"az": 0, "rg": 0}], ["pred"], ["range"], name="stamps")
    assert result["ok"], result

    labels = {r["label"] for r in json.loads((Path(result["dir"]) / "collection.json").read_text())["runs"]}
    assert labels == {"group__run__stamp_1", "group__run__stamp_2"}


def test_collect_skips_runs_missing_a_source(tmp_path):
    """Runs lacking the requested source are reported as missing, and a collection with no figures fails."""
    _make_run(tmp_path, "group", "run_a", sources=("pred", "gt"), seed=0)
    _make_run(tmp_path, "group", "run_b", sources=("pred",), seed=1)
    collector, ids = _collector(tmp_path)

    result = collector.collect(ids, [{"az": 0, "rg": 0}], ["gt"], ["range"], name="partial")
    assert result["ok"], result
    assert result["files"] == ["az0000_rg0000/range_gt_physical/run_a.png"]
    assert result["missing"] == [{"label": "run_b", "source": "gt"}]

    empty = collector.collect(ids, [{"az": 0, "rg": 0}], ["reduced"], ["range"], name="empty")
    assert not empty["ok"]


def test_collect_rejects_bad_inputs(tmp_path):
    """Empty selections, unknown sources, unknown axes, unknown spaces and negative indices are all refused."""
    _make_run(tmp_path, "group", "run_a")
    collector, ids = _collector(tmp_path)

    assert not collector.collect([], [{"az": 0, "rg": 0}], ["pred"], ["range"])["ok"]
    assert not collector.collect(ids, [], ["pred"], ["range"])["ok"]
    assert not collector.collect(ids, [{"az": 0, "rg": 0}], [], ["range"])["ok"]
    assert not collector.collect(ids, [{"az": 0, "rg": 0}], ["banana"], ["range"])["ok"]
    assert not collector.collect(ids, [{"az": 0, "rg": 0}], ["pred"], ["diagonal"])["ok"]
    assert not collector.collect(ids, [{"az": 0, "rg": 0}], ["pred"], ["range"], space="banana")["ok"]
    assert not collector.collect(ids, [{"az": -1, "rg": 0}], ["pred"], ["range"])["ok"]


def test_collect_restores_figure_style(tmp_path):
    """Collecting leaves the global plot style back on report after rendering."""
    _make_run(tmp_path, "group", "run_a")
    collector, ids = _collector(tmp_path)

    from tools.reporting.plotting import PlotBase

    assert collector.collect(ids, [{"az": 0, "rg": 0}], ["pred"], ["range"], name="style")["ok"]
    assert PlotBase.style == "report"
