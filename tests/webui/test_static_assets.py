"""Tests for the console's static asset layout and front-end module hygiene.

Checks that every JavaScript module on disk is loaded by index.html exactly once and in
dependency order, that shared helpers (MathJax bootstrap, HTML escaper, results roots,
network layer) are each defined in a single module, and that launch widget modules hold
the expected number of classes.
"""

from __future__ import annotations

import re

from tests.webui.conftest import WEBUI_ROOT


JS_DIR = WEBUI_ROOT / "static" / "js"
INDEX  = WEBUI_ROOT / "static" / "index.html"


def _loaded_scripts() -> list:
    """Returns the JavaScript file names index.html loads, in document order."""
    html = INDEX.read_text()
    return [name for name in re.findall(r'<script src="/static/js/([\w.]+\.js)', html)]


def test_every_module_is_loaded_by_the_page_exactly_once():
    """The set of loaded scripts matches the modules on disk, with no duplicate tags."""
    loaded = _loaded_scripts()
    on_disk = sorted(path.name for path in JS_DIR.glob("*.js"))

    assert sorted(loaded) == on_disk
    assert len(loaded) == len(set(loaded))


def test_shared_helpers_load_before_their_users():
    """Helper modules appear in the page ahead of every module that depends on them."""
    loaded = _loaded_scripts()

    for helper in ("api.js", "results_sources.js", "shared_charts.js", "canvas_base.js"):
        assert loaded.index(helper) < loaded.index("app.js")

    assert loaded.index("shared_charts.js") < loaded.index("home.js")
    assert loaded.index("canvas_base.js") < loaded.index("gauges.js")


def test_static_assets_carry_no_hand_written_cache_tags():
    """index.html contains no manual ?v= cache-busting query strings."""
    assert "?v=" not in INDEX.read_text()


def test_the_html_escaper_is_defined_once():
    """No module keeps a private _esc helper; the single escaper lives on the shared charts class."""
    definitions = [path.name for path in JS_DIR.glob("*.js") if re.search(r"\b_esc\s*\(", path.read_text())]
    assert definitions == []

    escapers = [path.name for path in JS_DIR.glob("*.js") if "static esc(" in path.read_text()]
    assert escapers == ["shared_charts.js"]


def test_the_results_roots_are_declared_once():
    """The results root path and its storage key are declared only in results_sources.js."""
    holders = [path.name for path in JS_DIR.glob("*.js") if "/ste/rnd/User/vice_vi" in path.read_text()]
    assert holders == ["results_sources.js"]

    readers = [path.name for path in JS_DIR.glob("*.js") if '"results-sources"' in path.read_text()]
    assert readers == ["results_sources.js"]


def test_the_network_layer_is_reached_through_its_class():
    """No module calls the old window-level api or toast helpers; the Api class is the entry point."""
    for path in JS_DIR.glob("*.js"):
        text = path.read_text()
        assert "window.apiGet(" not in text, path.name
        assert "window.apiPost(" not in text, path.name
        assert "window.toast(" not in text, path.name

    assert "class Api {" in (JS_DIR / "api.js").read_text()


def test_launch_widget_modules_hold_one_class_family_each():
    """Each launch widget module declares its expected class count and the merged module is gone."""
    counts = {path.name: len(re.findall(r"^class ", path.read_text(), re.M)) for path in JS_DIR.glob("*.js")}

    assert counts["python_literal.js"] == 1
    assert counts["config_form.js"] == 1
    assert counts["form_widgets.js"] == 3
    assert "launch_widgets.js" not in counts
