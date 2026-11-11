"""Exports vispy 0.17's volume colormaps for the TomoVis 3D port.

Runs once in the tomovis conda environment, where vispy and the original
TomoVis source are installed, and writes
``webui/static/data/tomovis_vispy_colormaps.json``. The browser's ray caster
(``tomovis_vispy.js``) reads that file instead of depending on vispy.

For every name of ``vispy.color.get_colormaps()``, in that order, the file
holds the GLSL ``glsl_map`` vispy compiles into the volume shader (with the
``$color_i`` templates and the bad, low and high colour checks already
inserted) and, for the texture-backed ``Colormap`` maps, the 1024 x 4 float32
``texture_map_data`` lookup table, base64 encoded little-endian. The two
translucent maps of ``Volume.initTranslucentColormaps`` are taken from the
original TomoVis ``Volume`` instance, so their GLSL is exactly what TomoVis
handed to vispy.

The ``es300`` text of each map is the same GLSL made valid for WebGL2's GLSL
ES 3.00, which has no implicit int-to-float conversion and no ``texture2D``:
``texture2D(`` becomes ``texture(``, ``max(0, `` becomes ``max(0.0, ``,
``1 - t`` becomes ``1.0 - t``, and ``//`` line remarks are dropped. The
function is renamed to ``vispy_cmap`` so the shader can call any map by one
name. Values computed by the GLSL are unchanged.

The bootstrap below is the only place that touches ``sys.path``: it adds the
TomoVis source root so ``Visualizer`` imports as in the desktop app, and
TomoVic's ``webui`` for the WebLogger.

Usage:
    /home/bard/miniconda3/envs/tomovis/bin/python webui/tools/tomovis_vispy_colormaps.py
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]

os.environ["QT_QPA_PLATFORM"]  = "offscreen"
os.environ["QT_API"]           = "pyqt5"
os.environ["PYQTGRAPH_QT_LIB"] = "PyQt5"
os.environ["MPLBACKEND"]       = "Qt5Agg"
sys.dont_write_bytecode        = True

parser = argparse.ArgumentParser(description="Export vispy's volume colormaps for the TomoVis 3D port.")
parser.add_argument("--tomovis", type=Path, default=REPO.parent / "tomovis",                                       help="TomoVis source root (holds Visualizer/)")
parser.add_argument("--out",     type=Path, default=REPO / "webui" / "static" / "data" / "tomovis_vispy_colormaps.json", help="output JSON file")
options = parser.parse_args()

sys.path.insert(0, str(REPO / "webui"))
sys.path.insert(0, str(options.tomovis.resolve()))

import numpy as np
import vispy
from PyQt5 import QtWidgets
from vispy.color import get_colormap, get_colormaps
from web_logger import WebLogger


class GlslEs300:
    """Rewrites one vispy colormap GLSL function for GLSL ES 3.00.

    Attributes:
        name : Name the rewritten function gets.
    """

    SIGNATURE    = re.compile(r"vec4\s+(\w+)\s*\(\s*float\s+t\s*\)")
    REMARK       = re.compile(r"//[^\n]*")
    REPLACEMENTS = (("texture2D(", "texture("), ("max(0, ", "max(0.0, "), ("1 - t", "1.0 - t"))

    def __init__(self, name: str = "vispy_cmap") -> None:
        """Stores the function name.

        Args:
            name : Name the rewritten function gets.
        """

        self.name = name

    def function_name(self, glsl: str) -> str:
        """Returns the name of the colormap function in ``glsl``.

        Raises:
            ValueError : When the text holds no ``vec4 name(float t)`` function.
        """

        match = self.SIGNATURE.search(glsl)
        if match is None:
            raise ValueError(f"no colormap function in GLSL: {glsl!r}")
        return match.group(1)

    def convert(self, glsl: str) -> str:
        """Returns ``glsl`` with the ES 3.00 replacements applied and the function renamed.

        Args:
            glsl : vispy's processed ``glsl_map`` text.

        Returns:
            GLSL ES 3.00 text defining ``vec4 vispy_cmap(float t)``.
        """

        text = self.REMARK.sub("", glsl)
        for old, new in self.REPLACEMENTS:
            text = text.replace(old, new)
        name = self.function_name(glsl)
        text = re.sub(rf"\b{name}\s*\(\s*float\s+t\s*\)", f"{self.name}(float t)", text, count=1)
        lines = [line.rstrip() for line in text.strip("\n").splitlines()]
        return "\n".join(line for line in lines if line.strip())


class VispyColormapExporter:
    """Collects vispy's opaque colormaps and TomoVis's translucent ones and writes the JSON.

    Attributes:
        out    : Output JSON path.
        logger : WebLogger for the summary line.
        glsl   : GlslEs300 rewriting each map.
        record : Document being built.
    """

    def __init__(self, out: Path, logger: WebLogger) -> None:
        """Prepares an empty document.

        Args:
            out    : Output JSON path.
            logger : WebLogger for the summary line.
        """

        self.out    = out
        self.logger = logger
        self.glsl   = GlslEs300()
        self.record = {}

    def entry(self, name: str, cmap) -> dict:
        """Returns the JSON entry of one colormap.

        Args:
            name : Name the map is known by.
            cmap : vispy BaseColormap instance.

        Returns:
            {"name", "class", "glsl", "es300", "lut" (base64 float32, 1024 x 4) or None, "lut_len"}.
        """

        lut = None
        if cmap.texture_map_data is not None:
            table = np.ascontiguousarray(cmap.texture_map_data.reshape(-1, 4), dtype="<f4")
            lut   = base64.b64encode(table.tobytes()).decode("ascii")
        return {
            "name"    : name,
            "class"   : type(cmap).__name__,
            "glsl"    : cmap.glsl_map,
            "es300"   : self.glsl.convert(cmap.glsl_map),
            "lut"     : lut,
            "lut_len" : None if cmap.texture_map_data is None else int(cmap.texture_map_data.shape[0]),
        }

    def opaque(self) -> list:
        """Returns the entries of ``get_colormaps()`` in its iteration order."""

        return [self.entry(name, get_colormap(name)) for name in get_colormaps()]

    def translucent(self) -> list:
        """Returns the entries of TomoVis's TransFire and TransGrays, in their cycle order."""

        from Visualizer import visualizer

        app    = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)
        volume = visualizer.Volume()
        first  = volume.translucentCmap
        second = next(volume.translucentCmaps)
        app.processEvents()
        return [self.entry(type(cmap).__name__, cmap) for cmap in (first, second)]

    def run(self) -> None:
        """Builds the document and writes it."""

        self.record = {
            "vispy"       : vispy.__version__,
            "default"     : "grays",
            "opaque"      : self.opaque(),
            "translucent" : self.translucent(),
        }
        self.out.parent.mkdir(parents=True, exist_ok=True)
        self.out.write_text(json.dumps(self.record, indent=1) + "\n")
        self.logger.info(f"wrote {self.out} ({len(self.record['opaque'])} opaque, {len(self.record['translucent'])} translucent maps)")


if __name__ == "__main__":
    VispyColormapExporter(options.out, WebLogger("tomovis_vispy")).run()
