"""Tests for the TomoVis page markup in the console's index.html.

Checks that the TomoVis and TomoVis scripts routes sit in the Results nav group after
Slices, that both page sections carry every mount point the TomoVis views bind to (window,
menu bar, tab strip with the four tabs in the original order, panels, status line, popup
layer, script panels), that the 17 TomoVis modules load after slice_collector.js and
before app.js in their dependency order, and that the four TomoVis stylesheets are linked
after styles.css.
"""

from __future__ import annotations

import re
from html.parser import HTMLParser

from tests.webui.conftest import WEBUI_ROOT


INDEX = WEBUI_ROOT / "static" / "index.html"


class MarkupIndex(HTMLParser):
    """Collects every element of index.html with its attributes, text and enclosing elements.

    Attributes:
        elements : One dict per start tag in document order, with keys tag, attrs, text and parents.
        stack    : The elements currently open while parsing.
    """

    VOID = {"meta", "link", "img", "input", "br", "hr", "source", "area", "base", "col", "embed", "param", "track", "wbr"}

    def __init__(self, html: str) -> None:
        """Parses `html` into the element list."""
        super().__init__()
        self.elements = []
        self.stack    = []
        self.feed(html)

    def handle_starttag(self, tag: str, attrs: list) -> None:
        """Records an element and opens it unless it is a void element."""
        element = {"tag": tag, "attrs": dict(attrs), "text": "", "parents": list(self.stack)}
        self.elements.append(element)
        if tag not in self.VOID:
            self.stack.append(element)

    def handle_endtag(self, tag: str) -> None:
        """Closes the innermost open element with this tag."""
        for index in range(len(self.stack) - 1, -1, -1):
            if self.stack[index]["tag"] == tag:
                del self.stack[index:]
                return

    def handle_data(self, data: str) -> None:
        """Appends text to every open element."""
        for element in self.stack:
            element["text"] += data

    def by_id(self, element_id: str) -> dict:
        """Returns the single element with this id."""
        found = [e for e in self.elements if e["attrs"].get("id") == element_id]
        assert len(found) == 1, element_id
        return found[0]

    def select(self, predicate) -> list:
        """Returns every element for which `predicate(element)` is true, in document order."""
        return [e for e in self.elements if predicate(e)]

    @staticmethod
    def classes(element: dict) -> set:
        """Returns the class names of an element."""
        return set((element["attrs"].get("class") or "").split())

    def page(self, name: str) -> dict:
        """Returns the page section whose data-page is `name`."""
        found = self.select(lambda e: e["tag"] == "section" and e["attrs"].get("data-page") == name)
        assert len(found) == 1, name
        return found[0]

    @staticmethod
    def inside(element: dict, ancestor: dict) -> bool:
        """Returns whether `ancestor` encloses `element`."""
        return any(parent is ancestor for parent in element["parents"])


class TestTomoVisPageMarkup:
    """index.html carries the TomoVis navigation, page sections, scripts and stylesheets."""

    MODULES = [
        "tomovis_session.js",
        "tomovis_widgets.js",
        "tomovis_dialogs.js",
        "tomovis_pg_view.js",
        "tomovis_pg_histogram.js",
        "tomovis_pg_roi.js",
        "tomovis_pg_imageview.js",
        "tomovis_mpl.js",
        "tomovis_pg_export.js",
        "tomovis_slicer.js",
        "tomovis_plot.js",
        "tomovis_profile.js",
        "tomovis_vispy.js",
        "tomovis_volume.js",
        "tomovis_script_slicer.js",
        "tomovis_script_volume.js",
        "tomovis_page.js",
    ]

    STYLESHEETS = ["styles.css", "tomovis.css", "tomovis_slicer.css", "tomovis_plot.css", "tomovis_volume.css"]

    PANELS = [("tv-panel-slicer", "0", "Slicer"), ("tv-panel-plot", "1", "Plot"), ("tv-panel-profile", "2", "Profile"), ("tv-panel-3d", "3", "3D")]

    def markup(self) -> MarkupIndex:
        """Returns the parsed index.html."""
        return MarkupIndex(INDEX.read_text(encoding="utf-8"))

    def test_nav_entries_follow_slices_in_the_results_group(self):
        """The Results group lists Results, Cube, Slices, TomoVis and TomoVis scripts in that order."""
        markup = self.markup()
        group  = markup.select(lambda e: e["attrs"].get("data-group") == "results")[0]
        links  = markup.select(lambda e: e["tag"] == "a" and "data-route" in e["attrs"] and markup.inside(e, group))

        assert [(a["attrs"]["href"], a["text"].strip()) for a in links] == [
            ("#/results", "Results"),
            ("#/cube", "Cube"),
            ("#/slices", "Slices"),
            ("#/tomovis", "TomoVis"),
            ("#/tomovis_scripts", "TomoVis scripts"),
        ]

    def test_tomovis_page_holds_the_window_frame(self):
        """The TomoVis page holds the window with title bar, menu bar, tabs, stack and status line."""
        markup = self.markup()
        page   = markup.page("tomovis")

        assert MarkupIndex.classes(page) == {"page", "page--tomovis"}
        for element_id, css in [("tv-window", "tv-window"), ("tv-titlebar", "tv-titlebar"), ("tv-menubar", "tv-menubar"), ("tv-tabs", "tv-tabs"), ("tv-stack", "tv-stack"), ("tv-status", "tv-statusbar"), ("tv-layer", "tv-layer"), ("tv-busy", "tv-titlebar__orb")]:
            element = markup.by_id(element_id)
            assert css in MarkupIndex.classes(element), element_id
            assert markup.inside(element, page), element_id

        assert "TomoVis" in markup.by_id("tv-titlebar")["text"]
        assert markup.by_id("tv-tabs")["attrs"]["role"] == "tablist"
        assert markup.by_id("tv-status")["attrs"]["role"] == "status"
        assert not markup.inside(markup.by_id("tv-layer"), markup.by_id("tv-window"))

    def test_menu_bar_shows_file_and_data(self):
        """The menu bar has exactly the File and Data menus, without mnemonics."""
        markup = self.markup()
        bar    = markup.by_id("tv-menubar")
        items  = markup.select(lambda e: "tv-menubar__item" in MarkupIndex.classes(e) and markup.inside(e, bar))

        assert [(i["attrs"]["data-menu"], i["text"].strip()) for i in items] == [("file", "File"), ("data", "Data")]
        assert "TomoVic" not in bar["text"]

    def test_tabs_and_panels_keep_the_original_order(self):
        """The tab strip reads Slicer, Plot, Profile, 3D with Slicer current, one panel per tab."""
        markup = self.markup()
        strip  = markup.by_id("tv-tabs")
        stack  = markup.by_id("tv-stack")
        tabs   = markup.select(lambda e: "tv-tab" in MarkupIndex.classes(e) and markup.inside(e, strip))

        assert [(t["attrs"]["data-tab"], t["text"].strip(), t["attrs"]["aria-controls"]) for t in tabs] == [(index, title, element_id) for element_id, index, title in self.PANELS]
        assert "is-current" in MarkupIndex.classes(tabs[0])

        for element_id, index, _ in self.PANELS:
            panel = markup.by_id(element_id)
            assert panel["attrs"]["data-tab"] == index
            assert "tv-panel" in MarkupIndex.classes(panel)
            assert markup.inside(panel, stack)

    def test_scripts_page_holds_both_script_panels(self):
        """The scripts page has a TomoVic page head and the two script mount points."""
        markup = self.markup()
        page   = markup.page("tomovis_scripts")

        assert MarkupIndex.classes(page) == {"page", "page--pad", "page--tomovis-scripts"}
        assert markup.select(lambda e: e["tag"] == "h2" and markup.inside(e, page))[0]["text"].strip() == "TomoVis scripts"
        assert markup.select(lambda e: e["tag"] == "hairline-figure" and markup.inside(e, page))[0]["attrs"]["name"] == "voxels"

        for element_id in ("tv-scripts", "tv-script-slicer", "tv-script-volume", "tv-scripts-layer"):
            assert markup.inside(markup.by_id(element_id), page), element_id

        assert "tv-script" in MarkupIndex.classes(markup.by_id("tv-script-slicer"))
        assert "tv-script" in MarkupIndex.classes(markup.by_id("tv-script-volume"))

    def test_modules_load_in_dependency_order_before_app(self):
        """The TomoVis modules load after slice_collector.js, before app.js, in the designed order."""
        loaded = re.findall(r'<script src="/static/js/([\w.]+\.js)"', INDEX.read_text(encoding="utf-8"))
        start  = loaded.index("slice_collector.js") + 1

        assert loaded[start:start + len(self.MODULES)] == self.MODULES
        assert loaded[start + len(self.MODULES)] == "app.js"

    def test_stylesheets_are_linked_after_the_console_stylesheet(self):
        """The four TomoVis stylesheets follow styles.css in order."""
        linked = re.findall(r'<link rel="stylesheet" href="/static/css/([\w.]+\.css)"', INDEX.read_text(encoding="utf-8"))
        start  = linked.index("styles.css")

        assert linked[start:start + len(self.STYLESHEETS)] == self.STYLESHEETS
        for name in self.STYLESHEETS:
            assert (WEBUI_ROOT / "static" / "css" / name).is_file()
