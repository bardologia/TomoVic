"""Tests for the slice collector that exports elevation-profile slices across several runs.

Covers cube inspection (dimensions, available sources, intensity ranges), single-slice PNG
rendering with and without a colour-limit override, and the multi-run collect operation:
directory layout, run label disambiguation, shared colour limits, normalized-space output,
input validation and restoration of the global plot style.
"""

from __future__ import annotations

import json
from pathlib import Path

from cube_explorer import SliceCollector
from web_logger    import WebLogger

from tests.webui.conftest         import N_AZ, N_RG
from tests.webui.preproc_fixtures import make_param_run, make_preproc_run, open_runs


def _collector(base: Path) -> tuple[SliceCollector, list]:
    """Returns a collector over the runs catalogued under ``base`` and their run ids."""
    cubes, run_ids = open_runs(base)

    return SliceCollector(cubes, WebLogger()), run_ids


def test_info_reports_dims_sources_and_intensity(tmp_path):
    """Cube info reports azimuth and range extents, the available sources and a non-degenerate intensity range each."""
    make_preproc_run(tmp_path, "group", "run_a")
    collector, ids = _collector(tmp_path)

    info = collector.info(ids[0])
    assert info["ok"], info
    assert info["n_az"] == N_AZ and info["n_rg"] == N_RG
    assert info["run"] == "run_a" and info["group"] == "group"
    assert info["stamp"] == "capon"
    assert info["sources"] == ["full"]
    assert set(info["intensity"]) == {"full"}
    assert all(pair[1] > pair[0] for pair in info["intensity"].values())


def test_info_rejects_ids_outside_catalogued_roots(tmp_path):
    """A run id from a tree that was never catalogued is refused."""
    make_preproc_run(tmp_path / "runs", "group", "run_a")
    foreign = make_preproc_run(tmp_path / "foreign", "group", "run_b")

    collector, _ = _collector(tmp_path / "runs")
    assert not collector.info(str(foreign))["ok"]


def test_slice_png_serves_with_and_without_clim_override(tmp_path):
    """Range and azimuth slices render as PNG with or without explicit colour limits, while unknown source or axis returns nothing."""
    make_preproc_run(tmp_path, "group", "run_a")
    collector, ids = _collector(tmp_path)

    plain  = collector.slice_png(ids[0], "full", "range", az=3, rg=2)
    scaled = collector.slice_png(ids[0], "full", "azimuth", az=3, rg=2, vmin=0.0, vmax=2.0)
    assert plain is not None and plain[:8] == b"\x89PNG\r\n\x1a\n"
    assert scaled is not None and scaled[:8] == b"\x89PNG\r\n\x1a\n"

    assert collector.slice_png(ids[0], "pred", "range", az=0, rg=0) is None
    assert collector.slice_png(ids[0], "full", "diagonal", az=0, rg=0) is None


def test_a_refused_slice_explains_itself_in_the_log(tmp_path, capsys):
    """An unknown run id logs the reason the slice was refused."""
    make_preproc_run(tmp_path / "runs", "group", "run_a")
    foreign = make_preproc_run(tmp_path / "foreign", "group", "run_b")

    collector, _ = _collector(tmp_path / "runs")
    capsys.readouterr()

    assert collector.slice_png(str(foreign), "full", "range", az=0, rg=0) is None

    logged = capsys.readouterr().out
    assert "unknown cube id" in logged


def test_collector_serves_the_param_source_of_a_single_tag_run(tmp_path):
    """A run with exactly one parameter run lists and renders the parametrized tomogram."""
    run_dir = make_preproc_run(tmp_path, "group", "run_a")
    make_param_run(run_dir, "params_k2")

    collector, ids = _collector(tmp_path)

    info = collector.info(ids[0])
    assert info["ok"], info
    assert info["sources"] == ["full", "param"]
    assert set(info["intensity"]) == {"full", "param"}

    png = collector.slice_png(ids[0], "param", "range", az=1, rg=1)
    assert png is not None and png[:8] == b"\x89PNG\r\n\x1a\n"


def test_collector_skips_param_when_several_tags_exist(tmp_path):
    """A run with several parameter runs lists only the raw source, since no tag can be chosen here."""
    run_dir = make_preproc_run(tmp_path, "group", "run_a")
    make_param_run(run_dir, "params_a")
    make_param_run(run_dir, "params_b")

    collector, ids = _collector(tmp_path)

    info = collector.info(ids[0])
    assert info["ok"] and info["sources"] == ["full"]
    assert collector.slice_png(ids[0], "param", "range", az=0, rg=0) is None


def test_collect_refuses_an_existing_collection_name(tmp_path):
    """Reusing a collection name is refused instead of overwriting the earlier export."""
    make_preproc_run(tmp_path, "group", "run_a", seed=0)
    collector, ids = _collector(tmp_path)

    assert collector.collect(ids, [{"az": 0, "rg": 0}], ["full"], ["range"], name="twice")["ok"]

    again = collector.collect(ids, [{"az": 1, "rg": 1}], ["full"], ["range"], name="twice")
    assert again["ok"] is False
    assert "already exists" in again["error"]


def test_collect_writes_figures_grouped_by_cut(tmp_path):
    """Figures land under point/axis/source folders, one file per run, and the manifest mirrors them."""
    make_preproc_run(tmp_path, "group", "run_a", seed=0)
    make_preproc_run(tmp_path, "group", "run_b", seed=1)
    collector, ids = _collector(tmp_path)

    result = collector.collect(ids, [{"az": 3, "rg": 2}], ["full"], ["range", "azimuth"], name="my test")
    assert result["ok"], result
    assert result["runs"] == 2 and not result["missing"]

    out_dir = Path(result["dir"])
    assert out_dir == tmp_path / "slice_collections" / "my_test"

    expected = {
        f"az0003_rg0002/{axis}_full_physical/{run}.png"
        for axis in ("range", "azimuth")
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
    make_preproc_run(tmp_path, "group", "run_a", seed=0)
    make_preproc_run(tmp_path, "group", "run_b", seed=1)
    collector, ids = _collector(tmp_path)

    intensities = [collector.info(i)["intensity"]["full"] for i in ids]
    result      = collector.collect(ids, [{"az": 0, "rg": 0}], ["full"], ["range"], shared=True, name="clim")
    assert result["ok"], result

    manifest = json.loads((Path(result["dir"]) / "collection.json").read_text())
    assert manifest["clims"]["full"] == [min(p[0] for p in intensities), max(p[1] for p in intensities)]

    per_run = collector.collect(ids, [{"az": 0, "rg": 0}], ["full"], ["range"], shared=False, name="perrun")
    assert json.loads((Path(per_run["dir"]) / "collection.json").read_text())["clims"]["full"] is None


def test_collect_normalized_space_and_multiple_points(tmp_path):
    """Normalized-space collection writes one folder per requested azimuth/range point."""
    make_preproc_run(tmp_path, "group", "run_a")
    collector, ids = _collector(tmp_path)

    points = [{"az": 1, "rg": 1}, {"az": 4, "rg": 2}]
    result = collector.collect(ids, points, ["full"], ["range"], space="normalized", name="norm")
    assert result["ok"], result
    assert set(result["files"]) == {"az0001_rg0001/range_full_normalized/run_a.png", "az0004_rg0002/range_full_normalized/run_a.png"}


def test_collect_disambiguates_duplicate_run_names(tmp_path):
    """Runs sharing a name are labelled with their parent group."""
    make_preproc_run(tmp_path, "group_a", "run", seed=0)
    make_preproc_run(tmp_path, "group_b", "run", seed=1)
    collector, ids = _collector(tmp_path)

    result = collector.collect(ids, [{"az": 0, "rg": 0}], ["full"], ["range"], name="dupes")
    assert result["ok"], result

    labels = {r["label"] for r in json.loads((Path(result["dir"]) / "collection.json").read_text())["runs"]}
    assert labels == {"group_a__run", "group_b__run"}


def test_collect_rejects_bad_inputs(tmp_path):
    """Empty selections, unknown sources, unknown axes, unknown spaces and negative indices are all refused."""
    make_preproc_run(tmp_path, "group", "run_a")
    collector, ids = _collector(tmp_path)

    assert not collector.collect([], [{"az": 0, "rg": 0}], ["full"], ["range"])["ok"]
    assert not collector.collect(ids, [], ["full"], ["range"])["ok"]
    assert not collector.collect(ids, [{"az": 0, "rg": 0}], [], ["range"])["ok"]
    assert not collector.collect(ids, [{"az": 0, "rg": 0}], ["banana"], ["range"])["ok"]
    assert not collector.collect(ids, [{"az": 0, "rg": 0}], ["full"], ["diagonal"])["ok"]
    assert not collector.collect(ids, [{"az": 0, "rg": 0}], ["full"], ["range"], space="banana")["ok"]
    assert not collector.collect(ids, [{"az": -1, "rg": 0}], ["full"], ["range"])["ok"]


def test_collect_restores_figure_style(tmp_path):
    """Collecting leaves the global plot style back on report after rendering."""
    make_preproc_run(tmp_path, "group", "run_a")
    collector, ids = _collector(tmp_path)

    from tools.reporting.plotting import PlotBase

    assert collector.collect(ids, [{"az": 0, "rg": 0}], ["full"], ["range"], name="style")["ok"]
    assert PlotBase.style == "report"
