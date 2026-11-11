"""Tests of the QImage.save port against files Qt 5.15.15 wrote in the tomovis environment (F-113, F-120).

The fixture comes from ``webui/tools/tomovis_parity/qt_image_formats.py``:
seven test images saved by Qt in every format pyqtgraph's image export
offered, recorded as SHA-256 digests, plus the decoded pixels of the
smooth-scaled ICO files and of the ICNS files.
"""

from __future__ import annotations

import hashlib
import io
import json
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from tomovis.exporters       import ExportWriter
from tomovis.events          import TomoVisEventError
from tomovis.qt_image_writer import QtImageWriter, QtPixels, QtSmoothScale

FIXTURE  = Path(__file__).parent / "fixtures" / "tomovis" / "qt_image_formats"
MANIFEST = json.loads((FIXTURE / "manifest.json").read_text())
DECODED  = np.load(FIXTURE / "decoded.npz")
CASES    = sorted(MANIFEST["cases"])
EXACT    = ("bmp", "jpeg", "jpg", "pbm", "pgm", "ppm", "wbmp", "webp", "xbm", "xpm")


def source(case: str) -> bytes:
    """The PNG Qt wrote for a case, standing in for the browser's PNG."""

    return (FIXTURE / f"{case}.png").read_bytes()


def rgba(case: str) -> np.ndarray:
    """The decoded RGBA pixels of a case."""

    with Image.open(FIXTURE / f"{case}.png") as image:
        return np.asarray(image.convert("RGBA")).copy()


def masked_ico(data: bytes) -> bytes:
    """ICO bytes with the AND mask's alignment bytes zeroed, as the fixture digests them."""

    width    = data[6] or 256
    height   = data[7] or 256
    start    = 6 + 16 + 40 + width * height * 4
    used     = (width + 7) // 8
    mask_bpl = ((width + 31) // 32) * 4
    out      = bytearray(data)
    for row in range(height):
        for col in range(used, mask_bpl):
            out[start + row * mask_bpl + col] = 0
    return bytes(out)


def assert_close_where_translucent(ours: np.ndarray, qt: np.ndarray) -> None:
    """Equal pixels, except at most 1 apart where 0 < alpha < 255 (Qt's SSE4.1 unpremultiply rounds a float reciprocal)."""

    assert ours.shape == qt.shape
    differ = (ours != qt).any(axis=-1)
    assert np.abs(ours.astype(int) - qt.astype(int)).max() <= 1
    assert ((qt[..., 3] > 0) & (qt[..., 3] < 255))[differ].all()


def test_the_fixture_lists_the_original_writers():
    """QImageWriter in the original environment offered exactly the 16 formats the port writes."""

    assert sorted(MANIFEST["writers"]) == sorted(QtImageWriter.FORMATS)


@pytest.mark.parametrize("case", CASES)
@pytest.mark.parametrize("suffix", EXACT)
def test_byte_exact_formats_equal_qt(case, suffix):
    """BMP, JPEG, PBM, PGM, PPM, WBMP, WebP, XBM and XPM are byte for byte what Qt wrote."""

    data = QtImageWriter().encode(suffix, source(case))

    assert len(data) == MANIFEST["cases"][case][suffix]["size"]
    assert hashlib.sha256(data).hexdigest() == MANIFEST["cases"][case][suffix]["sha256"]


@pytest.mark.parametrize("case", CASES)
def test_ico_and_cur_equal_qt(case):
    """ICO and CUR carry the same bytes; unscaled ones equal Qt's apart from the uninitialised mask padding, scaled ones decode to Qt's pixels."""

    writer = QtImageWriter()
    ico    = writer.encode("ico", source(case))
    record = MANIFEST["cases"][case]

    assert writer.encode("cur", source(case)) == ico
    assert record["ico"]["sha256_masked"] == record["cur"]["sha256_masked"]
    assert len(ico) == record["ico"]["size"]
    if max(rgba(case).shape[:2]) <= 256 or (rgba(case)[..., 3] == 255).all():
        assert hashlib.sha256(masked_ico(ico)).hexdigest() == record["ico"]["sha256_masked"]
    else:
        with Image.open(io.BytesIO(ico)) as image:
            ours = np.asarray(image.convert("RGBA"))
        assert_close_where_translucent(ours, DECODED[f"{case}_ico"])


@pytest.mark.parametrize("case", CASES)
def test_icns_equals_qt(case):
    """ICNS: one PNG icon at the square power-of-two size Qt picks, with Qt's pixels and a consistent header."""

    data       = QtImageWriter().encode("icns", source(case))
    qt_pixels  = DECODED[f"{case}_icns"]
    with Image.open(io.BytesIO(data[32:])) as image:
        ours = np.asarray(image.convert("RGBA"))
    pow2 = qt_pixels.shape[0].bit_length() - 1

    assert data[:4] == b"icns" and int.from_bytes(data[4:8], "big") == len(data)
    assert data[8:16] == b"TOC " + (16).to_bytes(4, "big")
    assert data[16:20] == data[24:28] == (b"icp%d" % pow2)
    assert_close_where_translucent(ours, qt_pixels)


@pytest.mark.parametrize("case", CASES)
def test_tiff_keeps_the_pixels(case):
    """TIFF stores the RGBA pixels unchanged; Qt's file differs only in its strip and orientation tags."""

    with Image.open(io.BytesIO(QtImageWriter().encode("tif", source(case)))) as image:
        assert (np.asarray(image.convert("RGBA")) == rgba(case)).all()
        assert image.info["dpi"] == (96, 96)


def test_smooth_scale_reproduces_each_kernel():
    """qSmoothScaleImage for shrinking both ways, shrinking one way and growing both ways, checked through the ICNS sizes Qt picked."""

    scaler = QtSmoothScale()

    assert scaler.scaledSize(300, 120, 256, 256, keep_aspect=True) == (256, 102)
    assert scaler.scaledSize(64, 300, 256, 256, keep_aspect=True) == (54, 256)
    assert scaler.scaledSize(300, 16, 256, 256, keep_aspect=True) == (256, 13)
    assert scaler.scale(rgba("tiny"), 16, 16).shape == (16, 16, 4)
    assert QtSmoothScale.points(10, 16)[:4] == [0, 0, 1, 1]


def test_mono_dither_and_wbmp_width_quirk():
    """Floyd-Steinberg mono follows dither_to_Mono; a WBMP width that is a multiple of 128 loses its zero low byte, as writeMultiByteInt does."""

    writer = QtImageWriter()
    flat   = np.full((1, 2, 4), 100, dtype=np.uint8)

    assert QtPixels.monoBits(flat).tolist() == [[1, 0]]
    assert writer.multiByte(300) == bytes([0x82, 0x2C])
    assert writer.multiByte(256) == bytes([0x82])
    assert writer.multiByte(127) == bytes([0x7F])


def test_unknown_or_missing_extensions_are_refused(tmp_path):
    """QImage.save returns False without a writer for the extension; the export route answers 400 there."""

    writer = ExportWriter()

    assert not QtImageWriter().write(tmp_path / "a.xyz", source("small"))
    assert not QtImageWriter().write(tmp_path / "noext", source("small"))
    with pytest.raises(TomoVisEventError):
        writer.writeImage(str(tmp_path / "a.gif"), source("small"))
    assert writer.writeImage(str(tmp_path / "A.XPM"), source("small")).read_bytes().startswith(b"/* XPM */\nstatic char *dummy[]={\n")
