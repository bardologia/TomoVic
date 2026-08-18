"""Tests that the webui README stays in sync with the served frontend.

Covers the correspondence between navigation routes in index.html and the
README route table, the claimed module count, and the modules actually loaded
by index.html.
"""
from __future__ import annotations

import re

from tests.webui.conftest import WEBUI_ROOT

NAV_ROUTE   = re.compile(r'href="#/([a-z_]+)" data-route="[a-z_]+"')
TABLE_ROUTE = re.compile(r"^\|[^|]+\|\s*`#/([a-z_]+)[^`]*`", re.MULTILINE)
SCRIPT_TAG  = re.compile(r"/static/js/([a-z_]+)\.js")

OFF_NAV_ROUTES = {"launch", "ablation"}


def _index_html() -> str:
    """Returns the text of the served static/index.html."""
    return (WEBUI_ROOT / "static" / "index.html").read_text(encoding="utf-8")


def _readme() -> str:
    """Returns the text of the webui README."""
    return (WEBUI_ROOT / "README.md").read_text(encoding="utf-8")


def _module_stems() -> set[str]:
    """Returns the stems of every JavaScript module under static/js."""
    return {path.stem for path in (WEBUI_ROOT / "static" / "js").glob("*.js")}


def test_every_nav_tab_has_a_readme_row():
    """Every navigation route in index.html has a row in the README route table."""
    nav        = set(NAV_ROUTE.findall(_index_html()))
    documented = set(TABLE_ROUTE.findall(_readme()))

    assert nav
    assert sorted(nav - documented) == []


def test_readme_documents_no_route_the_app_does_not_serve():
    """The README documents no route beyond the navigation ones and the known off-nav routes."""
    nav        = set(NAV_ROUTE.findall(_index_html()))
    documented = set(TABLE_ROUTE.findall(_readme()))

    assert sorted(documented - nav - OFF_NAV_ROUTES) == []


def test_readme_frontend_module_count_matches_the_directory():
    """The module count claimed in the README matches the files under static/js."""
    claimed = int(re.search(r"and (\d+) modules under `static/js/`", _readme()).group(1))

    assert claimed == len(_module_stems())


def test_every_frontend_module_is_loaded_by_index():
    """Every module under static/js is referenced by a script tag in index.html."""
    loaded = set(SCRIPT_TAG.findall(_index_html()))

    assert sorted(_module_stems() - loaded) == []
