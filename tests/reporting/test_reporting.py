"""Tests covering report assets and metric section grouping for markdown reports."""

from __future__ import annotations

import base64
import re
from pathlib import Path
from types   import SimpleNamespace


from tools.reporting.reporting import MetricSectionGrouper, ReportAssets


def _record(**metrics):
    """Returns a record-like namespace whose metrics dictionary holds the given values."""
    return SimpleNamespace(metrics=dict(metrics))


def test_assets_default_timestamp_format():
    """Verifies the default timestamp uses the ISO-like date and time format."""
    assets = ReportAssets(base=Path("/tmp"))
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}", assets.timestamp)


def test_assets_custom_timestamp():
    """Verifies an explicit timestamp is kept verbatim."""
    assets = ReportAssets(base=Path("/tmp"), timestamp="FIXED")
    assert assets.timestamp == "FIXED"


def test_assets_rel_path_relative(tmp_path):
    """Verifies paths under the base directory render as forward-slash relative paths."""
    assets = ReportAssets(base=tmp_path)
    target = tmp_path / "figs" / "a.png"
    assert assets.rel(target) == "figs/a.png"


def test_assets_rel_path_parent(tmp_path):
    """Verifies paths outside the base directory render with parent traversal."""
    base = tmp_path / "sub"
    base.mkdir()
    assets = ReportAssets(base=base)
    target = tmp_path / "a.png"
    assert assets.rel(target) == "../a.png"


def test_assets_src_not_embedded_returns_rel(tmp_path):
    """Verifies image sources stay relative paths when embedding is off."""
    assets = ReportAssets(base=tmp_path, embed_images=False)
    target = tmp_path / "x.png"
    target.write_bytes(b"data")
    assert assets.src(target) == "x.png"


def test_assets_src_embedded_returns_data_uri(tmp_path):
    """Verifies embedding renders the file bytes as a base64 PNG data URI."""
    img = tmp_path / "pic.png"
    img.write_bytes(b"\x89PNG\r\n")
    assets = ReportAssets(base=tmp_path, embed_images=True)
    src    = assets.src(img)

    assert src.startswith("data:image/png;base64,")
    payload = src.split(",", 1)[1]
    assert base64.b64decode(payload) == b"\x89PNG\r\n"


def test_assets_src_embedded_uses_mime_for_suffix(tmp_path):
    """Verifies the data URI MIME type follows the file suffix."""
    img = tmp_path / "pic.jpg"
    img.write_bytes(b"jpegbytes")
    assets = ReportAssets(base=tmp_path, embed_images=True)
    assert assets.src(img).startswith("data:image/jpeg;base64,")


def test_assets_src_embedded_unknown_suffix_defaults_png(tmp_path):
    """Verifies an unknown suffix falls back to the PNG MIME type."""
    img = tmp_path / "pic.bmp"
    img.write_bytes(b"bmp")
    assets = ReportAssets(base=tmp_path, embed_images=True)
    assert assets.src(img).startswith("data:image/png;base64,")


def test_assets_src_embedded_missing_file_falls_back_to_rel(tmp_path):
    """Verifies a missing file yields a relative link instead of a data URI."""
    assets  = ReportAssets(base=tmp_path, embed_images=True)
    missing = tmp_path / "gone.png"
    assert assets.src(missing) == "gone.png"


def test_assets_image_markdown_lines(tmp_path):
    """Verifies a single image renders as a markdown image line followed by a blank line."""
    assets = ReportAssets(base=tmp_path)
    target = tmp_path / "fig.png"
    target.write_bytes(b"x")
    lines = assets.image("Caption", target)

    assert lines == ["![Caption](fig.png)", ""]


def test_assets_images_single_path(tmp_path):
    """Verifies a single Path argument renders under the supplied label."""
    assets = ReportAssets(base=tmp_path)
    target = tmp_path / "single.png"
    target.write_bytes(b"x")
    lines = assets.images("Lbl", target)
    assert lines == ["![Lbl](single.png)", ""]


def test_assets_images_single_string_path(tmp_path):
    """Verifies a string path is accepted like a Path."""
    assets = ReportAssets(base=tmp_path)
    target = tmp_path / "s.png"
    target.write_bytes(b"x")
    lines = assets.images("Lbl", str(target))
    assert lines[0] == "![Lbl](s.png)"


def test_assets_images_list_uses_stem_labels(tmp_path):
    """Verifies a list of paths labels each image by its file stem."""
    assets = ReportAssets(base=tmp_path)
    paths  = []
    for name in ("alpha.png", "beta.png"):
        p = tmp_path / name
        p.write_bytes(b"x")
        paths.append(p)

    lines = assets.images("ignored", paths)
    assert "![alpha](alpha.png)" in lines
    assert "![beta](beta.png)" in lines


def test_assets_header_structure():
    """Verifies the header emits the title as a level-one heading and a generation timestamp line."""
    assets = ReportAssets(base=Path("/tmp"), timestamp="T0")
    header = assets.header("My Report")
    assert header[0] == "# My Report"
    assert "T0" in header[1]
    assert "Generated" in header[1]


def test_natural_key_numeric_ordering():
    """Verifies the natural sort key orders embedded numbers numerically."""
    names   = ["item10", "item2", "item1"]
    ordered = sorted(names, key=ReportAssets.natural_key)
    assert ordered == ["item1", "item2", "item10"]


def test_natural_key_mixed_tokens():
    """Verifies the natural sort key splits a name into text and integer tokens."""
    key = ReportAssets.natural_key("epoch_12_step")
    assert 12 in key
    assert "epoch_" in key


def test_grouper_scalar_keys_filters_non_numeric():
    """Verifies only numeric metric keys are collected."""
    records = [_record(loss=0.5, name="x", curve_r2=0.9)]
    keys    = MetricSectionGrouper.scalar_keys(records)
    assert "loss"     in keys
    assert "curve_r2" in keys
    assert "name"     not in keys


def test_grouper_scalar_keys_excludes_per_bin():
    """Verifies per-bin metric variants are excluded from the scalar keys."""
    records = [_record(elev_mse=0.1, elev_mse_3=0.2)]
    keys    = MetricSectionGrouper.scalar_keys(records)
    assert "elev_mse"   in keys
    assert "elev_mse_3" not in keys


def test_grouper_scalar_keys_sorted_unique():
    """Verifies the scalar keys are sorted and free of duplicates."""
    records = [_record(b=1, a=2), _record(a=3, c=4)]
    keys    = MetricSectionGrouper.scalar_keys(records)
    assert keys == sorted(keys)
    assert len(keys) == len(set(keys))


def test_grouper_bool_excluded():
    """Verifies boolean metrics are not treated as numeric scalars."""
    records = [_record(flag=True, score=1.0)]
    keys    = MetricSectionGrouper.scalar_keys(records)
    assert "score" in keys


def test_grouper_assigns_known_sections():
    """Verifies known metric prefixes land in their dedicated report sections."""
    grouper = MetricSectionGrouper()
    keys    = ["ssim_mean", "curve_mse", "n_pixels"]
    titles  = dict(grouper.group(keys))

    assert "SSIM"                in titles and "ssim_mean" in titles["SSIM"]
    assert "Curve-Level"         in titles and "curve_mse" in titles["Curve-Level"]
    assert "Dataset Statistics"  in titles and "n_pixels"  in titles["Dataset Statistics"]


def test_grouper_each_key_claimed_once():
    """Verifies every key is assigned to exactly one section."""
    grouper = MetricSectionGrouper()
    keys    = ["pixel_mse_mean", "pixel_r2_mean", "gauss_mu_err"]
    groups  = grouper.group(keys)
    flat    = [k for _, ks in groups for k in ks]
    assert sorted(flat) == sorted(keys)
    assert len(flat) == len(set(flat))


def test_grouper_leftover_bucket():
    """Verifies unmatched keys fall into the leftover section."""
    grouper = MetricSectionGrouper()
    keys    = ["totally_unmatched_metric"]
    groups  = grouper.group(keys)
    assert groups == [(MetricSectionGrouper.LEFTOVER_TITLE, ["totally_unmatched_metric"])]


def test_grouper_no_empty_sections():
    """Verifies sections without keys are dropped from the grouping."""
    grouper = MetricSectionGrouper()
    keys    = ["ssim_a"]
    groups  = grouper.group(keys)
    assert all(ks for _, ks in groups)
    assert len(groups) == 1


def test_grouper_section_order_follows_definition():
    """Verifies sections appear in their declared order."""
    grouper = MetricSectionGrouper()
    keys    = ["matched_mu_mae", "n_pixels", "ssim_y"]
    titles  = [t for t, _ in grouper.group(keys)]

    def idx(prefix):
        """Returns the position of the first section title starting with the given prefix."""
        return next(i for i, t in enumerate(titles) if t.startswith(prefix))

    assert idx("Dataset Statistics") < idx("SSIM")
    assert idx("SSIM") < idx("Matched Gaussian")
