"""Tests for the frontend figure saver that exports the console's on-screen images.

Covers the load order of the two new modules, the single home of the browser
download helper, the tab registry and the per-tab filename context it calls,
the labelling attributes the scanner reads, and the ZIP writer itself, which is
executed under node and read back with the standard library when node is
available.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import zipfile

import pytest

from tests.webui.conftest import WEBUI_ROOT


JS_DIR = WEBUI_ROOT / "static" / "js"
INDEX  = WEBUI_ROOT / "static" / "index.html"

CLASS_HEAD  = re.compile(r"^class\s+(\w+)(?:\s+extends\s+(\w+))?\s*\{", re.M)
FIGURE_TABS = re.compile(r"_figureTabs\(\)\s*\{\s*return\s*\{(.*?)\};", re.S)
TAB_ENTRY   = re.compile(r"(\w+)\s*:\s*this\.(\w+)\s*,")
VIEW_BIND   = re.compile(r"this\.(\w+)\s*=\s*new\s+window\.(\w+)\(")


def _loaded_scripts() -> list:
    """Returns the JavaScript file names index.html loads, in document order."""
    return re.findall(r'<script src="/static/js/([\w.]+\.js)', INDEX.read_text(encoding="utf-8"))


def _classes() -> dict:
    """Returns every top-level frontend class as name to (body, base class name)."""
    found = {}

    for path in JS_DIR.glob("*.js"):
        text  = path.read_text(encoding="utf-8")
        heads = list(CLASS_HEAD.finditer(text))

        for index, head in enumerate(heads):
            stop = heads[index + 1].start() if index + 1 < len(heads) else len(text)
            found[head.group(1)] = (text[head.start():stop], head.group(2))

    return found


def _defines(classes: dict, name: str, method: str) -> bool:
    """Reports whether the class or one of its bases declares the given method."""
    while name in classes:
        body, base = classes[name]
        if re.search(rf"^\s+{method}\(", body, re.M): return True
        name = base

    return False


def _figure_tabs() -> dict:
    """Returns the dock's route to view-property registry parsed from app.js."""
    block = FIGURE_TABS.search((JS_DIR / "app.js").read_text(encoding="utf-8"))
    assert block, "app.js no longer declares a _figureTabs registry"

    return dict(TAB_ENTRY.findall(block.group(1)))


def test_the_figure_modules_load_before_their_users():
    """Both saver modules are served and precede every module that calls into them."""
    loaded = _loaded_scripts()

    for module in ("figure_export.js", "figure_saver.js"):
        assert module in loaded

    for user in ("app.js", "tomogram.js"):
        assert loaded.index("figure_export.js") < loaded.index(user)
        assert loaded.index("figure_saver.js") < loaded.index(user)


def test_the_browser_download_helper_lives_in_one_module():
    """No module builds its own download anchor outside figure_export.js."""
    holders = [path.name for path in JS_DIR.glob("*.js") if re.search(r"\.download\s*=", path.read_text(encoding="utf-8"))]

    assert holders == ["figure_export.js"]


def test_the_cube_explorer_delegates_its_downloads():
    """The cube explorer's PNG, CSV and story exports all run through the shared exporter."""
    text = (JS_DIR / "tomogram.js").read_text(encoding="utf-8")

    for call in ("FigureExport.download(", "FigureExport.saveCanvas(", "FigureExport.saveBitmap("):
        assert call in text

    assert "canvas.toBlob(" not in text
    assert "downloadBlob(" not in text


def test_every_registered_figure_tab_supplies_a_filename_context():
    """Each route the dock mounts on names a view whose class declares figureTag."""
    classes = _classes()
    binds   = dict(VIEW_BIND.findall((JS_DIR / "app.js").read_text(encoding="utf-8")))
    tabs    = _figure_tabs()

    assert set(tabs) == {"cube", "slices", "results"}

    for route, prop in tabs.items():
        assert prop in binds, f"{route} points at an unbound view property"
        assert _defines(classes, binds[prop], "figureTag"), f"{binds[prop]} defines no figureTag"


def test_the_cube_panels_label_every_slice_plane_and_profile():
    """Every cube figure carries the label its file name needs, with axis and source on the cut panels."""
    html = INDEX.read_text(encoding="utf-8")

    assert len(re.findall(r'class="cube-slice" data-axis="\w+" data-source="\w+" data-fig="\w+ cut \w+"', html)) == 4
    assert len(re.findall(r'class="cube-prof" data-source="\w+" data-fig="vertical profile"', html))             == 1
    assert len(re.findall(r'class="cube-eplane" data-source="\w+" data-fig="\w+ plane"', html))                  == 4

    for canvas in ("cube-cloud-canvas", "cube-volume-canvas", "cube-pass-canvas"):
        assert re.search(rf'<canvas id="{canvas}" data-fig="[^"]+"', html), canvas


def test_the_cube_lens_stays_out_of_the_scan():
    """The hover magnifier is transient chrome, so its canvas opts out of the figure scan."""
    text = (JS_DIR / "tomogram.js").read_text(encoding="utf-8")

    assert re.search(r'this\.canvas\.className = "cube-lens";\s*this\.canvas\.dataset\.nofig = "";', text)


def test_the_volume_view_keeps_its_drawing_buffer():
    """The WebGL volume canvas stays readable so it can be captured like any other figure."""
    assert "preserveDrawingBuffer: true" in (JS_DIR / "volume.js").read_text(encoding="utf-8")


@pytest.mark.skipif(shutil.which("node") is None, reason="node is needed to execute the frontend ZIP writer")
def test_the_zip_writer_produces_an_archive_the_standard_library_reads(tmp_path):
    """Running ZipArchive under node yields a valid store-only archive with intact payloads."""
    script = tmp_path / "build_zip.cjs"
    target = tmp_path / "built.zip"
    script.write_text(
        "const vm = require('node:vm');\n"
        "const fs = require('node:fs');\n"
        f"const source = fs.readFileSync({str(JS_DIR / 'figure_export.js')!r}, 'utf8');\n"
        "const context = vm.createContext({ window: {}, Blob, TextEncoder, URL, console });\n"
        "vm.runInContext(source, context);\n"
        "(async () => {\n"
        "  const archive = new context.window.ZipArchive();\n"
        "  archive.add('plain.png', new TextEncoder().encode('payload one'));\n"
        "  archive.add('nested/deep name.png', new Uint8Array([0, 1, 2, 250, 255, 128]));\n"
        "  archive.add('unicode \\u00fc.png', new TextEncoder().encode('x'.repeat(4096)));\n"
        f"  fs.writeFileSync({str(target)!r}, Buffer.from(await archive.blob().arrayBuffer()));\n"
        "})();\n",
        encoding="utf-8",
    )

    subprocess.run(["node", str(script)], check=True, capture_output=True)

    with zipfile.ZipFile(target) as archive:
        assert archive.testzip() is None
        assert archive.namelist() == ["plain.png", "nested/deep name.png", "unicode ü.png"]
        assert archive.read("plain.png")            == b"payload one"
        assert list(archive.read("nested/deep name.png")) == [0, 1, 2, 250, 255, 128]
        assert len(archive.read("unicode ü.png"))   == 4096

        for info in archive.infolist():
            assert info.compress_type == zipfile.ZIP_STORED
            assert info.flag_bits & 0x800
