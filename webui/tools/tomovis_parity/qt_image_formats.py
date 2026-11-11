"""Records what Qt 5.15's QImage.save writes for every format pyqtgraph's image export offered.

Runs in the tomovis conda environment (PyQt5 with Qt 5.15.15 and its image
format plugins) under the offscreen platform. Each test image is built from a
fixed seed, turned into an ARGB32 ``QImage`` at 96 dpi (Qt's logical DPI on a
Linux desktop; the offscreen platform would give 100) and saved in all 16
formats. The fixture keeps the input PNG, the SHA-256 and size of every file
Qt wrote (for ICO and CUR also with the uninitialised alignment bytes of the
mask zeroed), and the decoded RGBA pixels of the smooth-scaled ICO files and
of the ICNS files, whose bytes TomoVic does not reproduce exactly. The bootstrap below sets the
offscreen platform before PyQt5 is imported.

Usage:
    /home/bard/miniconda3/envs/tomovis/bin/python webui/tools/tomovis_parity/qt_image_formats.py
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.dont_write_bytecode       = True

import numpy as np
from PIL import Image
from PyQt5 import QtGui, QtWidgets


class QtFormatCases:
    """The test images: sizes, transparency and texture chosen to reach every writer and scaler path.

    Attributes:
        CASES : Name to (width, height, transparent patches, random blue channel).
        SEED  : Seed of the random channel.
    """

    CASES = {
        "small"  : (40, 30, False, True),
        "alpha"  : (40, 30, True, True),
        "walpha" : (300, 120, True, False),
        "w256"   : (256, 10, False, True),
        "flat"   : (300, 16, True, False),
        "tiny"   : (10, 8, True, True),
        "tall"   : (64, 300, True, False),
    }
    SEED = 3

    def build(self) -> dict[str, np.ndarray]:
        """Returns name to (H, W, 4) uint8 RGBA image, in CASES order."""

        rng    = np.random.default_rng(self.SEED)
        images = {}
        for name, (width, height, alpha, noise) in self.CASES.items():
            y, x = np.mgrid[0:height, 0:width]
            rgba = np.zeros((height, width, 4), np.uint8)
            rgba[..., 0] = x * 255 // max(width - 1, 1)
            rgba[..., 1] = y * 255 // max(height - 1, 1)
            rgba[..., 2] = rng.integers(0, 256, (height, width)) if noise else ((x + y) % 7) * 36
            rgba[..., 3] = 255
            if alpha:
                rgba[: height // 4, : width // 4, 3]                                = 0
                rgba[height // 4 : height // 2, : width // 4, 3]                    = 128
                rgba[height // 2 : height // 2 + 3, width // 2 : width // 2 + 5, 3] = 37
            images[name] = rgba
        return images


class QtFormatRecorder:
    """Saves the test images with QImage.save and writes the fixture.

    Attributes:
        FORMATS : Extensions QImageWriter offered in the original environment.
        DECODED : Formats whose decoded pixels are stored: ICO when Qt smooth-scaled it (over 256 px), ICNS always.
        DPM     : Dots per metre of 96 dpi.
        out     : Fixture directory.
    """

    FORMATS = ("bmp", "cur", "icns", "ico", "jpeg", "jpg", "pbm", "pgm", "ppm", "tif", "tiff", "wbmp", "webp", "xbm", "xpm")
    DECODED = ("icns", "ico")
    DPM     = 3780

    def __init__(self, out: Path) -> None:
        """Prepares the output directory.

        Args:
            out : Fixture directory, created when missing.
        """

        self.out = out
        self.out.mkdir(parents=True, exist_ok=True)

    def qimage(self, rgba: np.ndarray) -> QtGui.QImage:
        """Builds the ARGB32 QImage pyqtgraph's ImageExporter would hold, at 96 dpi."""

        height, width = rgba.shape[:2]
        argb          = np.ascontiguousarray(rgba[..., [2, 1, 0, 3]])
        image         = QtGui.QImage(argb.tobytes(), width, height, 4 * width, QtGui.QImage.Format_ARGB32).copy()
        image.setDotsPerMeterX(self.DPM)
        image.setDotsPerMeterY(self.DPM)
        return image

    def maskedIco(self, data: bytes) -> bytes:
        """Returns ICO bytes with the AND mask's alignment bytes zeroed; QImage::fill leaves them uninitialised."""

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

    def decode(self, data: bytes, suffix: str) -> np.ndarray:
        """Decodes a written file to RGBA; ICNS by its embedded PNG."""

        payload = data[32:] if suffix == "icns" else data
        with Image.open(io.BytesIO(payload)) as image:
            return np.asarray(image.convert("RGBA")).copy()

    def record(self, images: dict[str, np.ndarray]) -> None:
        """Writes ``<case>.png``, ``manifest.json`` and ``decoded.npz``.

        Args:
            images : Name to RGBA image.
        """

        manifest = {"writers": [bytes(f).decode() for f in QtGui.QImageWriter.supportedImageFormats()], "cases": {}}
        decoded  = {}
        with tempfile.TemporaryDirectory() as scratch:
            for name, rgba in images.items():
                image = self.qimage(rgba)
                if not image.save(str(self.out / f"{name}.png")):
                    raise RuntimeError(f"Qt could not write {name}.png")
                entry = {}
                for suffix in self.FORMATS:
                    path = Path(scratch) / f"{name}.{suffix}"
                    if not image.save(str(path)):
                        raise RuntimeError(f"Qt could not write {path.name}")
                    data          = path.read_bytes()
                    entry[suffix] = {"sha256": hashlib.sha256(data).hexdigest(), "size": len(data)}
                    if suffix in ("ico", "cur"):
                        entry[suffix]["sha256_masked"] = hashlib.sha256(self.maskedIco(data)).hexdigest()
                    if suffix in self.DECODED and (suffix == "icns" or max(rgba.shape[:2]) > 256):
                        decoded[f"{name}_{suffix}"] = self.decode(data, suffix)
                manifest["cases"][name] = entry
        (self.out / "manifest.json").write_text(json.dumps(manifest, indent=1, sort_keys=True) + "\n")
        np.savez_compressed(self.out / "decoded.npz", **decoded)

    def run(self, cases: QtFormatCases) -> None:
        """Builds the images under a QApplication and records them."""

        app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv[:1])
        self.record(cases.build())
        app.processEvents()


parser = argparse.ArgumentParser(description="Record QImage.save output for every image export format.")
parser.add_argument("--out", type=Path, default=REPO / "tests" / "webui" / "fixtures" / "tomovis" / "qt_image_formats", help="fixture directory")
options = parser.parse_args()

QtFormatRecorder(options.out).run(QtFormatCases())
