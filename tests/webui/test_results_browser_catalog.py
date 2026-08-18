"""Tests for the results browser tree, catalog, gallery and folder listings.

Covers stage detection from directory markers, the dataset and run catalog,
image grouping in the gallery, the media path allow-list tied to opened roots,
text truncation and the tree depth limit.
"""
from __future__ import annotations

import os
from pathlib      import Path
from urllib.parse import parse_qs, urlparse

import pytest

from results_browser import ResultsBrowser
from web_logger      import WebLogger


@pytest.fixture
def browser():
    """Returns a results browser with a plain web logger."""
    return ResultsBrowser(WebLogger())


def _opened(browser: ResultsBrowser, root: Path) -> ResultsBrowser:
    """Opens `root` in the browser, which registers it as a media root, and returns the browser."""
    assert browser.tree(str(root))["ok"]
    return browser


def test_the_tree_reports_the_stage_it_recognises(browser, tmp_path):
    """A run holding a tensorboard directory is reported as the training stage."""
    run = tmp_path / "train_run"
    (run / "tensorboard").mkdir(parents=True)

    payload = browser.tree(str(run))

    assert payload["ok"]    is True
    assert payload["name"]  == "train_run"
    assert payload["stage"] == "training"
    assert payload["root"]  == str(run)


def test_an_unrecognised_run_falls_back_to_results(browser, tmp_path):
    """A directory with no stage marker falls back to the results stage."""
    (tmp_path / "misc").mkdir()

    assert browser.tree(str(tmp_path / "misc"))["stage"] == "results"


def test_the_earliest_matching_marker_wins(browser, tmp_path):
    """With several markers present, the earliest one in the marker order decides the stage."""
    run = tmp_path / "everything"
    (run / "pipeline").mkdir(parents=True)
    (run / "pipeline" / "resolved_config.json").write_text("{}")
    (run / "tensorboard").mkdir()
    (run / "inference").mkdir()

    assert browser.tree(str(run))["stage"] == "benchmark"


def test_the_catalog_lists_datasets_with_their_parameter_runs(browser, tmp_path):
    """The catalog lists dataset directories with their parameter runs sorted by name, skipping hidden entries and files."""
    datasets = tmp_path / "datasets"
    (datasets / "fl01" / "params" / "k5_l02").mkdir(parents=True)
    (datasets / "fl01" / "params" / "k2_l02").mkdir(parents=True)
    (datasets / "fl02").mkdir()
    (datasets / ".hidden").mkdir()
    (datasets / "readme.md").write_text("x")

    payload = browser.catalog(str(datasets), "")["datasets"]
    items   = {entry["name"]: entry for entry in payload["items"]}

    assert payload["error"] == ""
    assert sorted(items)    == ["fl01", "fl02"]
    assert [entry["name"] for entry in items["fl01"]["params"]] == ["k2_l02", "k5_l02"]
    assert items["fl02"]["params"] == []


def test_the_catalog_orders_runs_by_recency_and_labels_the_stage(browser, tmp_path):
    """The run catalog is ordered newest first and labels each run with its stage."""
    runs = tmp_path / "runs"
    (runs / "old_run" / "tensorboard").mkdir(parents=True)
    (runs / "new_run" / "inference").mkdir(parents=True)

    os.utime(runs / "old_run", (1_000_000, 1_000_000))
    os.utime(runs / "new_run", (2_000_000, 2_000_000))

    payload = browser.catalog("", str(runs))["runs"]

    assert [entry["name"] for entry in payload["items"]] == ["new_run", "old_run"]
    assert payload["items"][0]["stage"] == "inference"
    assert payload["items"][1]["stage"] == "training"


def test_an_unset_catalog_root_reports_itself_without_failing(browser):
    """An unset dataset or run root is reported as not set rather than failing."""
    payload = browser.catalog("", "")

    assert payload["ok"] is True
    assert payload["datasets"] == {"error": "not set", "items": []}
    assert payload["runs"]     == {"error": "not set", "items": []}


def test_the_gallery_needs_the_root_to_be_opened_first(browser, tmp_path):
    """The gallery is refused until the root has been opened by the tree call."""
    (tmp_path / "figure.png").write_bytes(b"\x89PNG")

    assert browser.gallery(str(tmp_path)) == {"ok": False, "error": "path not opened"}
    assert _opened(browser, tmp_path).gallery(str(tmp_path))["ok"] is True


def test_the_gallery_groups_images_by_folder_and_tags_animations(browser, tmp_path):
    """Gallery images are grouped by relative folder and GIFs are tagged as animations."""
    (tmp_path / "figures" / "colormaps").mkdir(parents=True)
    (tmp_path / "overview.png").write_bytes(b"\x89PNG")
    (tmp_path / "figures" / "loss.svg").write_bytes(b"<svg/>")
    (tmp_path / "figures" / "colormaps" / "amp.gif").write_bytes(b"GIF")
    (tmp_path / "figures" / "notes.md").write_text("x")

    payload = _opened(browser, tmp_path).gallery(str(tmp_path))
    groups  = {group["rel"]: group for group in payload["groups"]}

    assert payload["total"] == 3
    assert sorted(groups)   == ["", "figures", "figures/colormaps"]
    assert [image["kind"] for image in groups["figures/colormaps"]["images"]] == ["gif"]
    assert [image["name"] for image in groups["figures"]["images"]]           == ["loss"]
    assert groups[""]["images"][0]["kind"] == "img"


def test_a_gallery_url_round_trips_the_absolute_path(browser, tmp_path):
    """A gallery image URL round trips through file_path back to the absolute file, spaces included."""
    directory = tmp_path / "a b"
    directory.mkdir()
    (directory / "amp map.png").write_bytes(b"\x89PNG")

    payload = _opened(browser, tmp_path).gallery(str(tmp_path))
    url     = payload["groups"][0]["images"][0]["url"]
    query   = parse_qs(urlparse(url).query)
    encoded = query["path"][0]

    assert urlparse(url).path == "/resultsmedia"
    assert query["root"][0]   == str(tmp_path)
    assert Path(encoded)      == directory / "amp map.png"
    assert browser.file_path(query["root"][0], encoded) == directory / "amp map.png"


def test_media_is_only_served_from_an_opened_root(browser, tmp_path):
    """file_path serves only existing regular files under the opened root."""
    inside  = tmp_path / "runs"
    outside = tmp_path / "secrets"
    inside.mkdir()
    outside.mkdir()
    (inside / "figure.png").write_bytes(b"\x89PNG")
    (outside / "id_rsa").write_text("private")

    _opened(browser, inside)

    assert browser.file_path(str(inside), str(inside / "figure.png")) == inside / "figure.png"
    assert browser.file_path(str(inside), str(outside / "id_rsa"))    is None
    assert browser.file_path(str(inside), str(inside / "gone.png"))   is None
    assert browser.file_path(str(inside), str(inside))                is None


def test_media_is_refused_for_a_root_that_was_never_opened(browser, tmp_path):
    """file_path refuses a root that was never opened."""
    inside = tmp_path / "runs"
    inside.mkdir()
    (inside / "figure.png").write_bytes(b"\x89PNG")

    assert browser.file_path(str(inside), str(inside / "figure.png")) is None


def test_media_does_not_leak_across_two_opened_roots(browser, tmp_path):
    """A file under one opened root is not served through another opened root."""
    runs    = tmp_path / "runs"
    secrets = tmp_path / "secrets"
    runs.mkdir()
    secrets.mkdir()
    (secrets / "id_rsa").write_text("private")

    _opened(browser, runs)
    _opened(browser, secrets)

    assert browser.file_path(str(runs), str(secrets / "id_rsa")) is None


def test_a_traversal_out_of_an_opened_root_is_refused(browser, tmp_path):
    """A path escaping the opened root through .. is refused."""
    inside = tmp_path / "runs"
    inside.mkdir()
    (tmp_path / "secret.txt").write_text("private")

    _opened(browser, inside)

    assert browser.file_path(str(inside), str(inside / ".." / "secret.txt")) is None


def test_folder_listing_needs_the_root_to_be_opened_first(browser, tmp_path):
    """The folder listing is refused until the root is opened, then serves markdown with its text."""
    (tmp_path / "report.md").write_text("# hi")

    assert browser.folder(str(tmp_path), "") == {"ok": False, "error": "path not opened"}

    payload = _opened(browser, tmp_path).folder(str(tmp_path), "")
    assert [entry["name"] for entry in payload["markdown"]] == ["report.md"]
    assert payload["markdown"][0]["text"] == "# hi"


def test_folder_listing_refuses_a_relative_escape(browser, tmp_path):
    """A relative path escaping the root, or one that does not exist, is refused."""
    inside = tmp_path / "runs"
    inside.mkdir()

    _opened(browser, inside)

    assert browser.folder(str(inside), "../")["ok"]      is False
    assert browser.folder(str(inside), "missing")["ok"]  is False


def test_a_config_file_is_served_with_its_kind(browser, tmp_path):
    """JSON and YAML config files are served with their kind and contents."""
    (tmp_path / "trainer_config.json").write_text('{"lr": 0.001}')
    (tmp_path / "settings.yaml").write_text("lr: 0.001")

    payload = _opened(browser, tmp_path).folder(str(tmp_path), "")
    configs = {entry["name"]: entry for entry in payload["configs"]}

    assert configs["trainer_config.json"]["kind"] == "json"
    assert configs["settings.yaml"]["kind"]       == "yaml"
    assert configs["trainer_config.json"]["text"] == '{"lr": 0.001}'


def test_a_huge_markdown_file_is_truncated(browser, tmp_path):
    """A markdown file over MAX_TEXT_BYTES is cut and marked as truncated."""
    (tmp_path / "report.md").write_text("A" * (ResultsBrowser.MAX_TEXT_BYTES + 5000))

    payload = _opened(browser, tmp_path).folder(str(tmp_path), "")
    text    = payload["markdown"][0]["text"]

    assert text.endswith("[truncated]")
    assert len(text) == ResultsBrowser.MAX_TEXT_BYTES + len("\n\n[truncated]")


def test_the_tree_stops_descending_at_the_depth_limit(browser, tmp_path):
    """The tree stops descending at MAX_DEPTH levels."""
    deep = tmp_path
    for level in range(ResultsBrowser.MAX_DEPTH + 3):
        deep = deep / f"level_{level}"
    deep.mkdir(parents=True)

    node  = browser.tree(str(tmp_path))["tree"]
    depth = 0
    while node["children"]:
        node   = node["children"][0]
        depth += 1

    assert depth == ResultsBrowser.MAX_DEPTH
