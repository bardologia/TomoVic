"""Tests for the dataset bridge placeholders in the console's index.html.

Checks that every mount point the shared dataset bridge client and the TomoVis
bridge render into sits where the bridge design places it: the nav indicator
right before the backend status pill, the Cube, Slices and TomoVis scripts bars
right after their page heads, the Cube completion, missing-view and add buttons
next to the controls they complete, and the TomoVis caption as the first child of
the TomoVis page outside the window. Also checks that the two bridge modules load
after run_strip.js and before tomogram.js, and that the TomoVis bridge stylesheet
follows tomovis_volume.css.
"""

from __future__ import annotations

import re

from tests.webui.test_tomovis_page_markup import INDEX, MarkupIndex


class TestBridgeMarkup:
    """index.html carries the bridge placeholders, scripts and stylesheet in their designed places."""

    def markup(self) -> MarkupIndex:
        """Returns the parsed index.html."""
        return MarkupIndex(INDEX.read_text(encoding="utf-8"))

    def following(self, markup: MarkupIndex, element: dict) -> dict:
        """Returns the first element after `element` in document order that is not inside it."""
        start = next(index for index, candidate in enumerate(markup.elements) if candidate is element)
        return next(candidate for candidate in markup.elements[start + 1:] if not markup.inside(candidate, element))

    def head_of(self, markup: MarkupIndex, page: dict) -> dict:
        """Returns the page head block of a page section."""
        return markup.select(lambda e: "page__head" in MarkupIndex.classes(e) and markup.inside(e, page))[0]

    def test_nav_dataset_sits_right_before_the_status_pill(self):
        """#nav-dataset is a .nav__dataset inside the nav header, immediately followed by #nav-status."""
        markup  = self.markup()
        dataset = markup.by_id("nav-dataset")

        assert "nav__dataset" in MarkupIndex.classes(dataset)
        assert markup.inside(dataset, markup.by_id("nav"))
        assert self.following(markup, dataset) is markup.by_id("nav-status")

    def test_page_bars_follow_their_page_heads(self):
        """The Cube, Slices and TomoVis scripts bars come right after their page heads."""
        markup = self.markup()

        for page_name, bar_id in (("cube", "cube-dataset-bar"), ("slices", "sc-dataset-bar"), ("tomovis_scripts", "tvs-dataset-bar")):
            page = markup.page(page_name)
            bar  = markup.by_id(bar_id)
            assert "ds-bar" in MarkupIndex.classes(bar), bar_id
            assert markup.inside(bar, page), bar_id
            assert self.following(markup, self.head_of(markup, page)) is bar, bar_id

    def test_cube_bar_precedes_the_cube_picker(self):
        """#cube-dataset-bar is immediately followed by the .cube-pick block."""
        markup = self.markup()
        after  = self.following(markup, markup.by_id("cube-dataset-bar"))

        assert "cube-pick" in MarkupIndex.classes(after)

    def test_cube_completion_and_missing_panels(self):
        """#cube-complete follows #cube-hint inside .cube-pick, and #cube-missing follows #cube-story inside #cube-stage; both start hidden."""
        markup   = self.markup()
        complete = markup.by_id("cube-complete")
        missing  = markup.by_id("cube-missing")
        pick     = markup.select(lambda e: "cube-pick" in MarkupIndex.classes(e) and markup.inside(e, markup.page("cube")))[0]

        assert "ds-complete" in MarkupIndex.classes(complete) and "hidden" in complete["attrs"]
        assert markup.inside(complete, pick)
        assert self.following(markup, markup.by_id("cube-hint")) is complete

        assert "ds-missing" in MarkupIndex.classes(missing) and "hidden" in missing["attrs"]
        assert markup.inside(missing, markup.by_id("cube-stage"))
        assert self.following(markup, markup.by_id("cube-story")) is missing

    def test_cube_add_buttons_sit_next_to_their_flags(self):
        """The Add DEM and Add pixel spacing buttons follow the DEM terrain and scale flags they complete, hidden until offered."""
        markup = self.markup()

        for wrap_id, button_id, text in (("cube-dem-wrap", "cube-dem-add", "Add DEM"), ("cube-cloud-dem-wrap", "cube-cloud-dem-add", "Add DEM"), ("cube-cloud-scale-wrap", "cube-cloud-scale-add", "Add pixel spacing")):
            button = markup.by_id(button_id)
            assert self.following(markup, markup.by_id(wrap_id)) is button, button_id
            assert button["tag"] == "button" and button["attrs"]["type"] == "button", button_id
            assert {"btn", "btn--mini"} <= MarkupIndex.classes(button), button_id
            assert "hidden" in button["attrs"], button_id
            assert button["text"].strip() == text, button_id

        tools = markup.select(lambda e: "cube-modes__tools" in MarkupIndex.classes(e))[0]
        assert markup.inside(markup.by_id("cube-dem-add"), tools)

    def test_param_add_follows_the_parameter_select(self):
        """#cube-param-add is a hidden .ds-inline right after the parameter select inside #cube-param-row."""
        markup = self.markup()
        add    = markup.by_id("cube-param-add")

        assert markup.inside(add, markup.by_id("cube-param-row"))
        assert self.following(markup, markup.by_id("cube-param-tag")) is add
        assert "ds-inline" in MarkupIndex.classes(add) and "hidden" in add["attrs"]

    def test_tomovis_caption_is_the_first_child_outside_the_window(self):
        """#tvb-caption is the first element of the TomoVis section, hidden, before and outside #tv-window."""
        markup  = self.markup()
        page    = markup.page("tomovis")
        caption = markup.by_id("tvb-caption")
        first   = markup.select(lambda e: markup.inside(e, page))[0]

        assert first is caption
        assert "tvb-caption" in MarkupIndex.classes(caption) and "hidden" in caption["attrs"]
        assert not markup.inside(caption, markup.by_id("tv-window"))
        assert self.following(markup, caption) is markup.by_id("tv-window")

    def test_bridge_modules_load_after_run_strip_and_before_tomogram(self):
        """dataset_bridge.js then bridge_tomovis.js load right after run_strip.js and before tomogram.js."""
        loaded = re.findall(r'<script src="/static/js/([\w.]+\.js)"', INDEX.read_text(encoding="utf-8"))
        start  = loaded.index("run_strip.js")

        assert loaded[start + 1:start + 4] == ["dataset_bridge.js", "bridge_tomovis.js", "tomogram.js"]

    def test_bridge_stylesheet_follows_the_tomovis_volume_stylesheet(self):
        """bridge_tomovis.css is linked right after tomovis_volume.css."""
        linked = re.findall(r'<link rel="stylesheet" href="/static/css/([\w.]+\.css)"', INDEX.read_text(encoding="utf-8"))

        assert linked[linked.index("tomovis_volume.css") + 1] == "bridge_tomovis.css"
