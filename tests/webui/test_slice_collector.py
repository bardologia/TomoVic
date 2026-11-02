"""Tests for the slice collector that exports elevation-profile slices across several runs.

Covers cube inspection (dimensions, available sources, intensity ranges), the primary SLC
map, single-slice PNG rendering with and without a colour-limit override, the parametrized
source of a single-tag run, the basket collect operation (directory layout, per-item styling,
run label disambiguation, shared colour limits, input validation, restoration of the global
plot style, reuse of a saved basket) and mailing a basket as zip attachments through a
stand-in SMTP server.
"""

from __future__ import annotations

import io
import json
import smtplib
import zipfile
from email   import message_from_bytes, policy
from pathlib import Path

import numpy as np
from PIL import Image

import cube_explorer
from cube_explorer import SliceCollectionMailer, SliceCollector
from web_logger    import WebLogger

from tests.webui.conftest         import N_AZ, N_RG
from tests.webui.preproc_fixtures import make_param_run, make_preproc_run, open_runs

MAIL_SECTION = {"sender": "console@example.org", "recipient": "team@example.org", "smtp_host": "smtp.example.org", "smtp_port": 465}


def _collector(base: Path) -> tuple[SliceCollector, list]:
    """Returns a collector over the runs catalogued under ``base`` and their run ids."""
    cubes, run_ids = open_runs(base)

    return SliceCollector(cubes, WebLogger()), run_ids


def _basket(ids: list, points: list, sources: tuple = ("full",), axes: tuple = ("range",), space: str = "physical", cmap: str = "jet") -> list:
    """Returns the basket entries a map click adds: every run, source and axis at every point.

    Args:
        ids     : Run ids of the basket runs.
        points  : (azimuth, range) pixel pairs.
        sources : Cube sources to cut.
        axes    : Cut axes.
        space   : Value space of every entry.
        cmap    : Colormap of every entry.

    Returns:
        List of basket entry dicts in point, source, axis, run order.
    """
    return [
        {"id": cube_id, "source": source, "axis": axis, "az": az, "rg": rg, "space": space, "cmap": cmap}
        for az, rg in points
        for source in sources
        for axis in axes
        for cube_id in ids
    ]


class FakeSmtp:
    """Stand-in for smtplib.SMTP_SSL recording the login and every submitted message.

    Attributes:
        sent      : Messages submitted across every instance, as bytes.
        logins    : (user, password) pairs used across every instance.
        endpoints : (host, port) pairs connected to across every instance.
        fail      : Whether sending raises an SMTP error instead of recording.
    """

    sent      = []
    logins    = []
    endpoints = []
    fail      = False

    def __init__(self, host: str, port: int, timeout: float) -> None:
        """Records the endpoint connected to."""
        FakeSmtp.endpoints.append((host, port))
        self.timeout = timeout

    def __enter__(self):
        """Returns the connection itself."""
        return self

    def __exit__(self, *exc) -> None:
        """Closes nothing."""

    def login(self, user: str, password: str) -> None:
        """Records the login pair."""
        FakeSmtp.logins.append((user, password))

    def send_message(self, message) -> None:
        """Records the message, or raises when the class is set to fail."""
        if FakeSmtp.fail:
            raise smtplib.SMTPServerDisconnected("connection dropped")
        FakeSmtp.sent.append(message.as_bytes())


def _mailer(base: Path, monkeypatch, password: str = "app-password", fail: bool = False, mail: dict | None = None) -> tuple[SliceCollectionMailer, list]:
    """Returns a basket mailer over ``base`` reading a temporary machine profile, whose SMTP connection is a FakeSmtp, and the run ids.

    Args:
        base        : Root the runs were written under.
        monkeypatch : Pytest fixture used to swap the SMTP class, the profile location and the password variable.
        password    : Value of the password variable; empty unsets it.
        fail        : Whether the fake SMTP server refuses to send.
        mail        : Mail section written to the profile; MAIL_SECTION when None.

    Returns:
        The mailer and the catalogued run ids.
    """
    FakeSmtp.sent, FakeSmtp.logins, FakeSmtp.endpoints, FakeSmtp.fail = [], [], [], fail
    monkeypatch.setattr(cube_explorer.smtplib, "SMTP_SSL", FakeSmtp)

    profile = base / "machine.json"
    profile.write_text(json.dumps({"schema": 1, "mail": MAIL_SECTION if mail is None else mail}))
    monkeypatch.setenv("TOMOSAR_MACHINE_PROFILE", str(profile))

    collector, ids = _collector(base)
    mailer         = SliceCollectionMailer(collector, WebLogger())
    if password:
        monkeypatch.setenv(mailer.PASSWORD_ENV, password)
    else:
        monkeypatch.delenv(mailer.PASSWORD_ENV, raising=False)

    return mailer, ids


def test_info_reports_dims_sources_and_intensity(tmp_path):
    """Cube info reports azimuth and range extents, the available sources and a non-degenerate intensity range each."""
    make_preproc_run(tmp_path, "group", "run_a")
    collector, ids = _collector(tmp_path)

    info = collector.info(ids[0])
    assert info["ok"], info
    assert info["id"] == ids[0]
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


def test_primary_map_matches_the_cube_grid_and_is_cached(tmp_path):
    """The primary map is one image pixel per cube pixel, azimuth down and range across, and repeat requests reuse the rendered bytes."""
    make_preproc_run(tmp_path, "group", "run_a")
    collector, ids = _collector(tmp_path)

    png = collector.primary_png(ids[0])
    assert png is not None and png[:8] == b"\x89PNG\r\n\x1a\n"
    assert Image.open(io.BytesIO(png)).size == (N_RG, N_AZ)
    assert collector.primary_png(ids[0]) is png


def test_primary_map_off_the_tomogram_footprint_explains_itself(tmp_path, capsys):
    """A run whose primary SLC does not cover the tomogram footprint serves no map and logs why."""
    run_dir = make_preproc_run(tmp_path, "group", "run_a")
    np.save(run_dir / "data" / "primary.npy", np.ones((N_AZ - 1, N_RG), dtype=np.complex64))

    collector, ids = _collector(tmp_path)
    capsys.readouterr()

    assert collector.primary_png(ids[0]) is None
    assert "primary map for" in capsys.readouterr().out


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

    assert collector.collect(_basket(ids, [(0, 0)]), name="twice")["ok"]

    again = collector.collect(_basket(ids, [(1, 1)]), name="twice")
    assert again["ok"] is False
    assert "already exists" in again["error"]


def test_collect_writes_figures_grouped_by_cut(tmp_path):
    """Figures land under point/axis/source/space/colormap folders, one file per run, and the manifest mirrors them."""
    make_preproc_run(tmp_path, "group", "run_a", seed=0)
    make_preproc_run(tmp_path, "group", "run_b", seed=1)
    collector, ids = _collector(tmp_path)

    result = collector.collect(_basket(ids, [(3, 2)], ("full",), ("range", "azimuth")), name="my test")
    assert result["ok"], result
    assert result["runs"] == 2 and not result["missing"] and result["reused"] is False

    out_dir = Path(result["dir"])
    assert out_dir == tmp_path / "slice_collections" / "my_test"

    expected = {
        f"az0003_rg0002/{axis}_full_physical_jet/{run}.png"
        for axis in ("range", "azimuth")
        for run in ("run_a", "run_b")
    }
    assert set(result["files"]) == expected
    assert all((out_dir / rel).is_file() and (out_dir / rel).stat().st_size > 0 for rel in expected)

    manifest = json.loads((out_dir / "collection.json").read_text())
    assert {r["label"] for r in manifest["runs"]} == {"run_a", "run_b"}
    assert {r["id"] for r in manifest["runs"]} == set(ids)
    assert manifest["points"] == [{"az": 3, "rg": 2}]
    assert set(manifest["files"]) == expected
    assert {item["file"] for item in manifest["items"]} == expected


def test_collect_keeps_each_items_own_cut_space_and_colormap(tmp_path):
    """Basket entries of one run at different points, spaces and colormaps each land in their own folder, and repeated entries render once."""
    make_preproc_run(tmp_path, "group", "run_a")
    collector, ids = _collector(tmp_path)

    items  = _basket(ids, [(1, 1)]) + _basket(ids, [(4, 2)], space="normalized", cmap="viridis") + _basket(ids, [(1, 1)])
    result = collector.collect(items, name="mixed")
    assert result["ok"], result
    assert set(result["files"]) == {"az0001_rg0001/range_full_physical_jet/run_a.png", "az0004_rg0002/range_full_normalized_viridis/run_a.png"}


def test_collect_shared_clim_spans_all_runs(tmp_path):
    """Shared colour limits span the intensity ranges of every basket run, and are absent when per-run scaling is asked for."""
    make_preproc_run(tmp_path, "group", "run_a", seed=0)
    make_preproc_run(tmp_path, "group", "run_b", seed=1)
    collector, ids = _collector(tmp_path)

    intensities = [collector.info(i)["intensity"]["full"] for i in ids]
    result      = collector.collect(_basket(ids, [(0, 0)]), shared=True, name="clim")
    assert result["ok"], result

    manifest = json.loads((Path(result["dir"]) / "collection.json").read_text())
    assert manifest["clims"]["full"] == [min(p[0] for p in intensities), max(p[1] for p in intensities)]

    per_run = collector.collect(_basket(ids, [(0, 0)]), shared=False, name="perrun")
    assert json.loads((Path(per_run["dir"]) / "collection.json").read_text())["clims"] == {}


def test_collect_disambiguates_duplicate_run_names(tmp_path):
    """Runs sharing a name are labelled with their parent group."""
    make_preproc_run(tmp_path, "group_a", "run", seed=0)
    make_preproc_run(tmp_path, "group_b", "run", seed=1)
    collector, ids = _collector(tmp_path)

    result = collector.collect(_basket(ids, [(0, 0)]), name="dupes")
    assert result["ok"], result

    labels = {r["label"] for r in json.loads((Path(result["dir"]) / "collection.json").read_text())["runs"]}
    assert labels == {"group_a__run", "group_b__run"}


def test_collect_skips_runs_missing_a_source(tmp_path):
    """A run without a parametrized tomogram is reported as missing that source, and a basket no run can draw is refused."""
    with_param = make_preproc_run(tmp_path, "group", "run_a", seed=0)
    make_param_run(with_param, "params_k2")
    make_preproc_run(tmp_path, "group", "run_b", seed=1)
    collector, ids = _collector(tmp_path)

    result = collector.collect(_basket(ids, [(0, 0)], ("param",)), name="partial")
    assert result["ok"], result
    assert result["files"] == ["az0000_rg0000/range_param_physical_jet/run_a.png"]
    assert result["missing"] == [{"label": "run_b", "source": "param"}]

    empty = collector.collect(_basket(ids[1:], [(0, 0)], ("param",)), name="empty")
    assert not empty["ok"]


def test_collect_rejects_bad_inputs(tmp_path):
    """An empty basket, entries lacking a key, unknown sources, axes, spaces or colormaps, negative indices and unknown runs are all refused."""
    make_preproc_run(tmp_path, "group", "run_a")
    collector, ids = _collector(tmp_path)

    good = _basket(ids, [(0, 0)])[0]

    assert not collector.collect([])["ok"]
    assert "lacks" in collector.collect([{k: v for k, v in good.items() if k != "cmap"}])["error"]
    assert not collector.collect([{**good, "source": "pred"}])["ok"]
    assert not collector.collect([{**good, "axis": "diagonal"}])["ok"]
    assert not collector.collect([{**good, "space": "banana"}])["ok"]
    assert not collector.collect([{**good, "cmap": "rainbow"}])["ok"]
    assert not collector.collect([{**good, "az": -1}])["ok"]
    assert not collector.collect([{**good, "id": str(tmp_path / "nowhere")}])["ok"]


def test_collect_restores_figure_style(tmp_path):
    """Collecting leaves the global plot style back on report after rendering."""
    make_preproc_run(tmp_path, "group", "run_a")
    collector, ids = _collector(tmp_path)

    from tools.reporting.plotting import PlotBase

    assert collector.collect(_basket(ids, [(0, 0)]), name="style")["ok"]
    assert PlotBase.style == "report"


def test_mail_settings_report_the_profile_recipient_and_password_state(tmp_path, monkeypatch):
    """The form defaults carry the profile's recipient and sender and whether the password variable is set."""
    make_preproc_run(tmp_path, "group", "run_a")

    mailer, _ = _mailer(tmp_path, monkeypatch)
    settings  = mailer.settings()
    assert settings["recipient"] == MAIL_SECTION["recipient"]
    assert settings["sender"] == MAIL_SECTION["sender"]
    assert settings["ready"] is True

    monkeypatch.delenv(mailer.PASSWORD_ENV)
    assert mailer.settings()["ready"] is False


def test_mail_sends_the_rendered_collection_as_one_zip(tmp_path, monkeypatch):
    """Mailing renders the basket to disk, zips it under the collection name and sends one message to every recipient."""
    make_preproc_run(tmp_path, "group", "run_a", seed=0)
    make_preproc_run(tmp_path, "group", "run_b", seed=1)
    mailer, ids = _mailer(tmp_path, monkeypatch)

    result = mailer.mail(_basket(ids, [(3, 2)], ("full",), ("range", "azimuth")), name="for the group", recipient="a@example.org; b@example.org", note="Cuts through the forest edge.")
    assert result["ok"], result
    assert result["recipient"] == "a@example.org, b@example.org"
    assert result["volumes"] == ["for_the_group.zip"]

    assert FakeSmtp.endpoints == [(MAIL_SECTION["smtp_host"], MAIL_SECTION["smtp_port"])]
    assert FakeSmtp.logins == [(MAIL_SECTION["sender"], "app-password")]
    assert len(FakeSmtp.sent) == 1

    message = message_from_bytes(FakeSmtp.sent[0], policy=policy.default)
    assert message["To"] == "a@example.org, b@example.org"
    assert message["From"] == MAIL_SECTION["sender"]
    assert message["Subject"] == f"{mailer.SUBJECT_PREFIX}: slice collection for_the_group"

    parts = [part for part in message.walk() if part.get_filename()]
    body  = next(part for part in message.walk() if part.get_content_type() == "text/plain").get_content()
    assert body.startswith("Cuts through the forest edge.")
    assert "4 figures from 2 runs" in body and "az 3 rg 2" in body

    archive = zipfile.ZipFile(io.BytesIO(parts[0].get_payload(decode=True)))
    assert set(archive.namelist()) == {"for_the_group/collection.json"} | {f"for_the_group/{rel}" for rel in result["files"]}
    assert (Path(result["dir"]) / "mail" / "for_the_group.zip").is_file()


def test_mail_splits_a_large_collection_over_numbered_volumes(tmp_path, monkeypatch):
    """A collection above the attachment cap is packed into numbered volumes, one message each, that together hold every file."""
    make_preproc_run(tmp_path, "group", "run_a")
    mailer, ids = _mailer(tmp_path, monkeypatch)

    saved   = mailer.collector.collect(_basket(ids, [(1, 1), (2, 2), (3, 3)]), name="split")
    largest = max((Path(saved["dir"]) / rel).stat().st_size for rel in saved["files"])
    monkeypatch.setattr(SliceCollectionMailer, "MAX_ATTACHMENT_MB", 1.5 * largest / (1024 * 1024))

    result = mailer.mail(_basket(ids, [(1, 1), (2, 2), (3, 3)]), name="split", recipient="a@example.org")
    assert result["ok"], result
    assert len(result["volumes"]) > 1 and result["volumes"][0] == f"split_01of{len(result['volumes']):02d}.zip"
    assert len(FakeSmtp.sent) == len(result["volumes"])

    members = set()
    for name in result["volumes"]:
        members |= set(zipfile.ZipFile(Path(result["dir"]) / "mail" / name).namelist())
    assert members == {"split/collection.json"} | {f"split/{rel}" for rel in result["files"]}


def test_mail_refuses_before_rendering_without_recipient_sender_or_password(tmp_path, monkeypatch):
    """A malformed recipient, a profile without a sender or an unset password variable is refused before any figure is written."""
    make_preproc_run(tmp_path, "group", "run_a")

    mailer, ids = _mailer(tmp_path, monkeypatch)
    assert "malformed" in mailer.mail(_basket(ids, [(0, 0)]), recipient="not-an-address")["error"]
    assert "at least one" in mailer.mail(_basket(ids, [(0, 0)]), recipient=" , ")["error"]

    mailer, ids = _mailer(tmp_path, monkeypatch, password="")
    assert "SMTP password not found" in mailer.mail(_basket(ids, [(0, 0)]), recipient="a@example.org")["error"]

    mailer, ids = _mailer(tmp_path, monkeypatch, mail={**MAIL_SECTION, "sender": ""})
    assert "no mail sender" in mailer.mail(_basket(ids, [(0, 0)]), recipient="a@example.org")["error"]
    assert mailer.settings()["ready"] is False

    assert not (tmp_path / "slice_collections").exists()
    assert FakeSmtp.sent == []


def test_mail_failure_after_rendering_keeps_the_collection(tmp_path, monkeypatch):
    """When the SMTP server drops the message, the error names the saved folder, which stays on disk."""
    make_preproc_run(tmp_path, "group", "run_a")
    mailer, ids = _mailer(tmp_path, monkeypatch, fail=True)

    result = mailer.mail(_basket(ids, [(0, 0)]), name="dropped", recipient="a@example.org")
    assert result["ok"] is False
    assert "mailing failed" in result["error"]
    assert (Path(result["dir"]) / "collection.json").is_file()


def test_mail_reuses_a_basket_saved_under_the_same_name(tmp_path, monkeypatch):
    """Mailing a basket already saved under its name sends that folder without rendering it again, while another basket under the name is refused."""
    make_preproc_run(tmp_path, "group", "run_a")
    mailer, ids = _mailer(tmp_path, monkeypatch)

    basket = _basket(ids, [(1, 1)], ("full",), ("range", "azimuth"))
    saved  = mailer.collector.collect(basket, name="meeting")
    assert saved["ok"] and saved["reused"] is False

    figure = Path(saved["dir"]) / saved["files"][0]
    stamp  = figure.stat().st_mtime_ns

    mailed = mailer.mail(basket, name="meeting", recipient="a@example.org")
    assert mailed["ok"], mailed
    assert mailed["reused"] is True
    assert mailed["files"] == saved["files"]
    assert figure.stat().st_mtime_ns == stamp
    assert len(FakeSmtp.sent) == 1

    other = mailer.mail(_basket(ids, [(2, 2)]), name="meeting", recipient="a@example.org")
    assert other["ok"] is False
    assert "for a different basket" in other["error"]
    assert len(FakeSmtp.sent) == 1
