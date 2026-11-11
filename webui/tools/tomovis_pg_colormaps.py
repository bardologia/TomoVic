"""Records pyqtgraph's gradient ColorMaps menu for the TomoVis page.

TomoVis's image panes carry pyqtgraph's GradientEditorItem, whose right-click
menu (``pyqtgraph.widgets.ColorMapMenu``) offers preset gradients, the bundled
maps, the CET maps and the matplotlib maps. The browser port cannot import
pyqtgraph, so this development tool walks the same menu tree in the tomovis
conda environment and records, for every entry, exactly what pyqtgraph does
when the entry is chosen: it feeds the entry's ColorMap to a real
GradientEditorItem through ``colorMapMenuClicked`` and stores the editor's
saved state (colour mode, tick positions and colours, tick visibility) plus the
32-entry swatch the menu shows. The result is
``webui/static/data/tomovis_pg_colormaps.json``. Run it once after a pyqtgraph
upgrade; TomoVic itself never imports pyqtgraph.

Usage:
    /home/bard/miniconda3/envs/tomovis/bin/python webui/tools/tomovis_pg_colormaps.py
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

os.environ["QT_QPA_PLATFORM"]  = "offscreen"
os.environ["PYQTGRAPH_QT_LIB"] = "PyQt5"
sys.dont_write_bytecode        = True

from PyQt5 import QtWidgets

import pyqtgraph as pg
from pyqtgraph import colormap
from pyqtgraph.graphicsItems.GradientEditorItem import GradientEditorItem
from pyqtgraph.graphicsItems.GradientPresets import Gradients
from pyqtgraph.widgets import ColorMapMenu as menu_module


class PgColorMapRecorder:
    """Walks pyqtgraph's ColorMaps menu and records each entry's effect on a GradientEditorItem.

    Attributes:
        output : JSON file written by ``run``.
        maps   : Entry id to its recorded gradient state and swatch.
        editor : The GradientEditorItem every entry is applied to.
    """

    def __init__(self, output: Path) -> None:
        """Creates the recorder and the gradient editor it applies entries to.

        Args:
            output : Path of the JSON file to write.
        """

        self.output = output
        self.maps   = {}
        self.editor = GradientEditorItem(orientation="right")

    @staticmethod
    def hexColor(rgba) -> str:
        """Returns an ``rrggbbaa`` string for an (r, g, b, a) tuple of 0..255 integers."""

        return "".join(f"{int(value):02x}" for value in rgba)

    def record(self, name: str, source) -> str:
        """Applies one menu entry to the editor and stores what the editor holds afterwards.

        Args:
            name   : Entry name as the menu shows it, None for the "None" entry.
            source : ColorMapMenu source ("preset-gradient", "matplotlib", None for local files, ...).

        Returns:
            The entry id under which the state was stored.
        """

        cmap  = menu_module.ColorMapMenu.actionDataToColorMap(menu_module.PrivateActionData(name, source))
        entry = f"{source}:{name}"
        self.editor.colorMapMenuClicked(cmap)
        state = self.editor.saveState()

        if source == "preset-gradient":
            swatch_map = menu_module.preset_gradient_to_colormap(name)
        else:
            swatch_map = cmap
        swatch = swatch_map.getLookupTable(nPts=32, alpha=True)

        self.maps[entry] = {
            "mode"         : state["mode"],
            "ticks"        : [[float(pos), self.hexColor(color)] for pos, color in state["ticks"]],
            "ticksVisible" : bool(state["ticksVisible"]),
            "swatch"       : [self.hexColor(color) for color in swatch],
        }
        return entry

    def entries(self, names, source) -> list:
        """Records a list of entries and returns their menu items.

        Args:
            names  : Entry names in menu order.
            source : Their ColorMapMenu source.

        Returns:
            Menu items ``{"text", "map"}``; entries pyqtgraph cannot load are left out, as the menu leaves them out.
        """

        items = []
        for name in names:
            try:
                entry = self.record(name, source)
            except ValueError:
                continue
            items.append({"text": name, "map": entry})
        return items

    def presetMenu(self) -> list:
        """Returns the "preset gradient" submenu in GradientPresets order."""

        return self.entries(list(Gradients.keys()), "preset-gradient")

    def localMenu(self) -> list:
        """Returns the "local" submenu: bundled maps without the CET and PAL-relaxed files, naturally sorted."""

        names = colormap.listMaps(source=None)
        names = [x for x in names if not x.startswith("CET")]
        names = [x for x in names if not x.startswith("PAL-relaxed")]
        return self.entries(menu_module.sorted_filenames(names), None)

    def cetMenu(self) -> list:
        """Returns the "cet (local)" submenu with its six category submenus."""

        items = []
        for cet_type in ["Linear", "Divergent", "Rainbow", "Cyclic", "Isoluminant", "Color Blind"]:
            names = [x for x in colormap.listMaps(source=None) if x.startswith("CET")]
            if cet_type.endswith("Blind"):
                names = [x for x in names if x[4:6] == "CB"]
            else:
                names = [x for x in names if x[4] == cet_type[0] and x[5].isdigit()]
            items.append({"text": cet_type, "submenu": self.entries(menu_module.sorted_filenames(names), None)})
        return items

    def matplotlibMenu(self) -> list:
        """Returns the "matplotlib" submenu: the categories after the first, then "Others" when leftovers exist."""

        items = []
        for category, names in menu_module.MATPLOTLIB_CMAPS[1:]:
            items.append({"text": category, "submenu": self.entries(names, "matplotlib")})
        leftovers = menu_module.find_mpl_leftovers()
        if leftovers:
            items.append({"text": "Others", "submenu": self.entries(menu_module.sorted_filenames(leftovers), "matplotlib")})
        return items

    def tree(self) -> list:
        """Returns the whole ColorMaps menu as GradientEditorItem builds it, ending with the RGB and HSV modes."""

        none_entry = self.record(None, None)
        return [
            {"text": "None", "map": none_entry},
            {"separator": True},
            {"text": "preset gradient", "submenu": self.presetMenu()},
            {"text": "local", "submenu": self.localMenu()},
            {"text": "cet (local)", "submenu": self.cetMenu()},
            {"text": "matplotlib", "submenu": self.matplotlibMenu()},
            {"separator": True},
            {"text": "RGB", "mode": "rgb"},
            {"text": "HSV", "mode": "hsv"},
        ]

    def run(self) -> None:
        """Builds the tree, records every entry and writes the JSON file."""

        tree = self.tree()
        data = {"pyqtgraph": pg.__version__, "title": "ColorMaps", "tree": tree, "maps": self.maps}
        self.output.parent.mkdir(parents=True, exist_ok=True)
        self.output.write_text(json.dumps(data, separators=(",", ":")))


if __name__ == "__main__":
    application = QtWidgets.QApplication(sys.argv)
    PgColorMapRecorder(Path(__file__).resolve().parents[1] / "static" / "data" / "tomovis_pg_colormaps.json").run()
