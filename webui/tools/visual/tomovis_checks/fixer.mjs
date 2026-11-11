import fs from "node:fs";
import path from "node:path";
import { TomoVisHarness as H, TomoVisCheckRun as R, REPO } from "./harness.mjs";

class FixerChecks {
  constructor(options) {
    this.options = options;
    this.run     = new R("fixer");
    this.inputs  = H.fixture("inputs");
    this.out     = H.shotDir("fixer");
    this.errors  = [];
  }

  T(fn, arg) {
    return this.page.evaluate(fn, arg);
  }

  async snapshot() {
    return H.snapshot(this.page);
  }

  async tabIndex() {
    const local  = await this.T(() => window.app.tomovisPage.tabs.current);
    const server = (await this.snapshot()).controls.tabWidget.index;
    return [local, server];
  }

  async widgetCentre(name) {
    return this.T((n) => {
      const box = window.app.tomovisPage.ctx.kit.views.get(n)[0].el.getBoundingClientRect();
      return { x: box.left + box.width / 2, y: box.top + box.height / 2 };
    }, name);
  }

  async clickWidget(name) {
    const point = await this.widgetCentre(name);
    await this.page.mouse.click(point.x, point.y);
    await H.waitIdle(this.page);
  }

  async clickTab(index) {
    await this.page.click(`.tv-tab[data-tab="${index}"]`);
    await H.waitIdle(this.page);
  }

  async key(key) {
    await this.page.keyboard.press(key);
    await H.waitIdle(this.page);
  }

  async importFile(menuLabel, file) {
    await H.menu(this.page, "File", "Import", menuLabel);
    await H.chooseFile(this.page, file);
  }

  async tabKeys() {
    await this.run.check("G-01 F-144", "tab arrow keys stop at the first and last tab, as QTabBar does", async () => {
      await this.T(() => document.querySelector('.tv-tab[data-tab="0"]').focus());
      const seen = [];
      await this.key("ArrowLeft");
      seen.push(await this.tabIndex());
      for (let i = 0; i < 4; i += 1) {
        await this.key("ArrowRight");
        seen.push(await this.tabIndex());
      }
      await this.key("ArrowLeft");
      seen.push(await this.tabIndex());
      const focused = await this.T(() => document.activeElement.dataset.tab);
      R.equal(seen, [[0, 0], [1, 1], [2, 2], [3, 3], [3, 3], [2, 2]], "tab index after Left, Right x4, Left");
      R.equal(focused, "2", "focus follows the current tab");
      await this.clickTab(0);
      return "Left at Slicer stays 0, Right at 3D stays 3";
    });

    await this.run.check("G-01 F-144 follow", "arrow keys move from the current tab after a server tab switch", async () => {
      await this.T(() => document.querySelector('.tv-tab[data-tab="0"]').focus());
      await this.T(() => window.app.tomovisPage.ctx.session.send({ type: "tab", index: 2 }));
      await H.waitIdle(this.page);
      await this.T(() => window.app.tomovisPage.tabs.follow(window.app.tomovisPage.ctx.session.snapshot));
      await this.key("ArrowRight");
      const after = await this.tabIndex();
      await this.clickTab(0);
      R.equal(after, [3, 3], "Right from the server's current tab 2");
      return "Right after a switch to Profile reaches 3D";
    });
  }

  async tabWheel() {
    await this.run.check("G-02 F-140", "the wheel over the tab bar changes tabs one per notch without wrapping", async () => {
      const tab0 = await this.T(() => { const b = document.querySelector('.tv-tab[data-tab="1"]').getBoundingClientRect(); return { x: b.left + b.width / 2, y: b.top + b.height / 2 }; });
      await this.page.mouse.move(tab0.x, tab0.y);
      const seen = [];
      for (const dy of [100, 100, 100, 100, -100]) {
        await this.page.mouse.wheel(0, dy);
        await H.waitIdle(this.page);
        seen.push(await this.tabIndex());
      }
      const scroll = await this.T(() => [window.scrollX, window.scrollY, document.querySelector("#page-tomovis") ? document.querySelector("#page-tomovis").scrollLeft : 0]);
      R.equal(seen, [[1, 1], [2, 2], [3, 3], [3, 3], [2, 2]], "tab index after wheel down x4, up");
      R.equal(scroll, [0, 0, 0], "the page did not scroll");

      const strip = await this.T(() => { const s = document.querySelector("#tv-tabs").getBoundingClientRect(); return { x: s.right - 40, y: s.bottom - 8 }; });
      await this.page.mouse.move(strip.x, strip.y);
      await this.page.mouse.wheel(0, -100);
      await H.waitIdle(this.page);
      const outside = await this.tabIndex();
      R.equal(outside, [2, 2], "the empty part of the strip right of the tabs ignores the wheel");

      await this.clickTab(0);
      return "0 -> 1 -> 2 -> 3 -> 3, up -> 2";
    });
  }

  async volumeRadios() {
    await this.run.check("G-03 F-094/F-095", "3D radios: arrows stop at the ends and Right/Left do nothing in the vertical groups", async () => {
      await this.clickTab(3);
      const names = ["turntableCameraTab4Button", "flyCameraTab4Button", "arcballCameraTab4Button"];
      const state = () => this.T((n) => {
        const tab = window.app.tomovisPage.views[3];
        return [n.find((k) => tab[k].checked), n.find((k) => tab[k].el === document.activeElement)];
      }, names);
      await this.T(() => window.app.tomovisPage.views[3].turntableCameraTab4Button.el.focus());
      const seen = [];
      for (const key of ["ArrowUp", "ArrowDown", "ArrowDown", "ArrowDown", "ArrowRight", "ArrowLeft", "ArrowUp"]) {
        await this.key(key);
        seen.push((await state()).map((n) => n.replace("CameraTab4Button", "")));
      }
      R.equal(seen, [["turntable", "turntable"], ["fly", "fly"], ["arcball", "arcball"], ["arcball", "arcball"], ["arcball", "arcball"], ["arcball", "arcball"], ["fly", "fly"]], "camera radios");

      const projections = ["mipProjectionTab4Button", "isoProjectionTab4Button", "translucentProjectionTab4Button", "additiveProjectionTab4Button"];
      await this.T(() => window.app.tomovisPage.views[3].additiveProjectionTab4Button.el.click());
      await this.T(() => window.app.tomovisPage.views[3].additiveProjectionTab4Button.el.focus());
      const proj = [];
      for (const key of ["ArrowDown", "ArrowRight", "ArrowUp", "ArrowLeft", "ArrowUp", "ArrowUp", "ArrowUp"]) {
        await this.key(key);
        proj.push(await this.T((n) => n.find((k) => window.app.tomovisPage.views[3][k].checked).replace("ProjectionTab4Button", ""), projections));
      }
      R.equal(proj, ["additive", "additive", "translucent", "translucent", "iso", "mip", "mip"], "projection radios");

      await this.T(() => { const t = window.app.tomovisPage.views[3]; t.turntableCameraTab4Button.el.click(); t.mipProjectionTab4Button.el.click(); });
      await this.clickTab(0);
      return "Turntable Up stays, Arcball Down stays, Right/Left inert; Additive Down stays, Up walks to MIP and stops";
    });
  }

  async normalizationRadios() {
    await this.run.check("G-03 F-119", "Normalization radios (one row): Left/Right move and stop at the ends, Up/Down do nothing", async () => {
      await this.importFile("npy", path.join(this.inputs, "npy_real.npy"));
      const pane = '.tv-slicer__pane[data-view="imv2_1"]';
      await this.page.locator(`${pane} .tv-pg-btn`).nth(1).click();
      await this.page.locator(".tv-menu .tv-menu__item", { hasText: "Normalization" }).click();
      const read = () => this.T((p) => {
        const radios = [...document.querySelectorAll(`${p} .tv-pg-normgroup .tv-radio`)];
        const name   = (el) => el ? el.textContent.trim() : null;
        return [name(radios.find((r) => r.classList.contains("is-checked"))), name(radios.find((r) => r === document.activeElement))];
      }, pane);
      await this.page.locator(`${pane} .tv-radio`, { hasText: "Off" }).focus();
      const seen = [];
      for (const key of ["ArrowRight", "ArrowDown", "ArrowUp", "ArrowLeft", "ArrowLeft", "ArrowLeft", "ArrowRight"]) {
        await this.page.keyboard.press(key);
        await this.page.waitForTimeout(40);
        seen.push(await read());
      }
      await this.page.locator(`${pane} .tv-radio`, { hasText: "Off" }).click();
      R.equal(seen, [["Off", "Off"], ["Off", "Off"], ["Off", "Off"], ["Subtract", "Subtract"], ["Divide", "Divide"], ["Divide", "Divide"], ["Subtract", "Subtract"]], "normalization radios as measured on pyqtgraph's ImageView in Qt");
      return "Right at Off and Up/Down inert; Left walks to Divide and stops";
    });
  }

  async profileInk() {
    return this.T(() => {
      const canvas = document.querySelector("#tv-panel-profile .tv-mpl-canvas");
      const data   = canvas.getContext("2d").getImageData(0, 0, canvas.width, canvas.height).data;
      let dark = 0;
      for (let i = 0; i < data.length; i += 4) if (data[i] + data[i + 1] + data[i + 2] < 300) dark += 1;
      return dark;
    });
  }

  async fresh() {
    await this.page.goto("about:blank");
    await H.openTomoVis(this.page);
  }

  async profileAfterE011(showFirst) {
    await this.fresh();
    if (showFirst) {
      await this.clickTab(2);
      await this.page.waitForTimeout(200);
    }
    await this.clickTab(1);
    await this.clickWidget("tab2ChkBox3");
    await this.clickWidget("tab2PlotButton");
    const after = await this.tabIndex();
    await this.clickTab(2);
    await this.page.waitForTimeout(300);
    const ink     = await this.profileInk();
    const options = await this.T(() => window.app.tomovisPage.ctx.session.figure("profile", "options_axes", {}));
    return { after, ink, axes: options.result.axes };
  }

  async profileWithoutData() {
    await this.run.check("G-04 F-070 E-011", "X [m] then Plot (profile) without data: the Profile tab shows the empty 0..1 axes when first opened", async () => {
      const r = await this.profileAfterE011(false);
      await H.shot(this.page, "g04_profile_empty_axes", "fixer", { element: "#tv-window" });
      H.compareShot("g04_profile_empty_axes", path.join(this.options.audit, "e011_original_profile.png"), "fixer");
      R.equal(r.after, [1, 1], "the failed Plot (profile) stays on the Plot tab");
      R.assert(r.ink > 2000, `profile canvas shows axes and ticks (${r.ink} dark pixels)`);
      R.equal(r.axes.length, 1, "one axes on the server");
      return `${r.ink} dark pixels, axes ${JSON.stringify(r.axes)}`;
    });

    await this.run.check("G-04 first show", "after an earlier visit to the Profile tab the same steps leave the old blank frame, as in Qt", async () => {
      const r = await this.profileAfterE011(true);
      await H.shot(this.page, "g04_profile_shown_before", "fixer", { element: "#tv-window" });
      H.compareShot("g04_profile_shown_before", path.join(this.options.audit, "probe_e011_shown_True.png"), "fixer");
      R.equal(r.ink, 0, "blank canvas");
      R.equal(r.axes.length, 1, "one axes on the server, never drawn");
      await this.fresh();
      return "blank, one undrawn axes";
    });
  }

  async volumeErrorLevels() {
    await this.run.check("G-08 F-153", "vispy's callback error lines from the 3D tab reach the server log at error level", async () => {
      await this.fresh();
      await this.importFile("hd5", path.join(this.inputs, "fusar_two_key_elev.hd5"));
      await this.clickTab(3);
      await this.page.waitForFunction(() => { const tab = window.app.tomovisPage.views[3]; return tab.volume && tab.loading === 0; }, null, { timeout: 30000 });
      await this.page.locator("#tv-panel-3d .tv-volume__canvas").focus();
      await this.page.keyboard.down("w");
      await this.page.waitForTimeout(250);
      await this.page.keyboard.up("w");
      await this.page.waitForTimeout(1200);
      const lines  = await this.T(async () => (await (await fetch("/api/server-log?limit=400")).json()).lines);
      const errors = lines.filter((l) => l.message.startsWith("TomoVis: ERROR: Invoking FlyCamera.on_timer"));
      const info   = lines.filter((l) => l.message.startsWith("TomoVis: ") && !l.message.startsWith("TomoVis: ERROR:") && l.level === "INFO");
      R.assert(errors.length > 0, "no fly timer error in the server log");
      R.equal([...new Set(errors.map((l) => l.level))], ["ERROR"], "levels of the error lines");
      await this.clickTab(0);
      return `${errors.length} error lines at ERROR, ${info.length} other TomoVis lines at INFO`;
    });
  }

  async customColors() {
    await this.run.check("G-09 F-115", "custom colours of the colour dialog survive a page reload, as QSettings kept them across runs", async () => {
      await this.fresh();
      await this.T(() => window.localStorage.removeItem("tomovis.customColors"));
      await this.fresh();
      const open = (initial) => this.T((c) => { window.colorResult = window.app.tomovisPage.ctx.dialogs.color({ initial: c }); }, initial);
      const well = () => this.T(() => [...document.querySelectorAll(".tv-colordialog__well")[1].querySelectorAll(".tv-colordialog__cell")].map((cell) => getComputedStyle(cell).backgroundColor));
      await open([12, 34, 56, 255]);
      await this.page.waitForSelector(".tv-colordialog");
      await this.page.locator(".tv-colordialog .tv-button", { hasText: "Add to Custom Colors" }).click();
      await this.page.locator(".tv-colordialog .tv-modal__buttons .tv-button", { hasText: "OK" }).click();
      await this.fresh();
      await open([255, 255, 255, 255]);
      await this.page.waitForSelector(".tv-colordialog");
      const cells = await well();
      await this.page.keyboard.press("Escape");
      R.equal(cells[0], "rgb(12, 34, 56)", "first custom colour after the reload");
      R.equal(cells.slice(1).every((c) => c === "rgb(255, 255, 255)"), true, "the other 15 stay white");
      await this.T(() => window.localStorage.setItem("tomovis.customColors", "{broken"));
      await this.fresh();
      await open([255, 255, 255, 255]);
      await this.page.waitForSelector(".tv-colordialog");
      const reset = await well();
      await this.page.keyboard.press("Escape");
      await this.T(() => window.localStorage.removeItem("tomovis.customColors"));
      R.equal(reset.every((c) => c === "rgb(255, 255, 255)"), true, "an unreadable stored value gives Qt's white defaults");
      return "custom colour 0 kept across the reload";
    });
  }

  async figureSaveFormats() {
    await this.run.check("G-07 F-135", "the figure Save dialog lists matplotlib 3.11.2's 12 filters and writes GIF and AVIF", async () => {
      await this.fresh();
      await this.importFile("npy", path.join(this.inputs, "npy_real.npy"));
      await this.clickWidget("tab1PlotButton");
      const written = [];
      let items = [];
      for (const suffix of ["gif", "avif"]) {
        const target = path.join(this.out, `saved_plot.${suffix}`);
        fs.rmSync(target, { force: true });
        await this.page.click('#tv-panel-plot .tv-mpl-tool[data-method="save_figure"]');
        await this.page.waitForSelector(".tv-filedialog[data-dir]");
        items = await this.T(() => [...document.querySelector(".tv-filedialog__filter .tv-combo__sizer").children].map((c) => c.textContent));
        await H.chooseFile(this.page, target);
        await this.page.waitForTimeout(300);
        written.push(fs.readFileSync(target).subarray(0, 12));
      }
      R.equal(items, ["AV1 Image File Format (*.avif)", "Encapsulated Postscript (*.eps)", "Graphics Interchange Format (*.gif)", "Joint Photographic Experts Group (*.jpeg *.jpg)", "PGF code for LaTeX (*.pgf)", "Portable Document Format (*.pdf)", "Portable Network Graphics (*.png)", "Postscript (*.ps)", "Raw RGBA bitmap (*.raw *.rgba)", "Scalable Vector Graphics (*.svg *.svgz)", "Tagged Image File Format (*.tif *.tiff)", "WebP Image Format (*.webp)"], "filters");
      R.equal(written[0].subarray(0, 6).toString("latin1"), "GIF89a", "GIF header");
      R.equal(written[1].subarray(4, 12).toString("latin1"), "ftypavif", "AVIF header");
      await this.clickTab(0);
      return `${items.length} filters; GIF and AVIF written`;
    });
  }

  async imageFormats() {
    await this.run.check("G-06 F-120", "Menu > Export writes every QImageWriter format; the pixels equal the PNG export", async () => {
      await this.fresh();
      await this.importFile("npy", path.join(this.inputs, "npy_real.npy"));
      const dir = path.join(this.out, "exports");
      fs.mkdirSync(dir, { recursive: true });
      const exported = {};
      for (const suffix of ["png", "ico", "cur", "icns", "pbm", "pgm", "ppm", "xbm", "xpm", "wbmp", "webp", "bmp", "jpg", "tif"]) {
        const target = path.join(dir, `menu_export.${suffix}`);
        fs.rmSync(target, { force: true });
        await this.page.locator('.tv-slicer__pane[data-view="imv1_1"] .tv-pg-btn').nth(1).click();
        await this.page.locator(".tv-menu .tv-menu__item").nth(1).click();
        await this.page.waitForSelector(".tv-filedialog[data-dir]", { timeout: 15000 });
        await this.page.fill(".tv-filedialog .tv-filedialog__name", target);
        await this.page.click(".tv-filedialog .tv-filedialog__accept");
        await this.page.waitForSelector(".tv-filedialog", { state: "detached", timeout: 15000 });
        for (let i = 0; i < 40 && !fs.existsSync(target); i += 1) await this.page.waitForTimeout(100);
        exported[suffix] = fs.existsSync(target) ? fs.readFileSync(target) : null;
      }
      const missing = Object.entries(exported).filter(([, data]) => !data).map(([suffix]) => suffix);
      R.equal(missing, [], "formats not written");
      const code = [
        "import sys, json, numpy as np",
        "from PIL import Image",
        "d = sys.argv[1]",
        "png = np.asarray(Image.open(f'{d}/menu_export.png').convert('RGBA')).astype(int)",
        "out = {}",
        "for s in ['ico', 'cur', 'ppm', 'pgm', 'bmp', 'tif', 'xbm', 'xpm']:",
        "    im = np.asarray(Image.open(f'{d}/menu_export.{s}').convert('RGBA')).astype(int)",
        "    ref = png.copy()",
        "    if s == 'pgm': ref[..., :3] = ((png[..., 0] * 11 + png[..., 1] * 16 + png[..., 2] * 5) // 32)[..., None]",
        "    if s in ('ppm', 'bmp', 'pgm'): ref[..., 3] = 255",
        "    out[s] = 'mono' if s == 'xbm' else int(np.abs(im - ref).max()) if im.shape == ref.shape else str(im.shape)",
        "print(json.dumps({'shape': list(png.shape), **out}))",
      ].join("\n");
      const decoded = JSON.parse(H.python(code, dir));
      R.equal([decoded.ico, decoded.cur, decoded.ppm, decoded.pgm, decoded.bmp, decoded.tif, decoded.xpm], [0, 0, 0, 0, 0, 0, 0], "decoded pixels against the PNG export");
      R.equal(exported.icns.subarray(0, 4).toString("latin1"), "icns", "ICNS magic");
      R.equal(exported.pbm.subarray(0, 2).toString("latin1"), "P4", "PBM magic");
      R.equal([exported.wbmp[0], exported.wbmp[1]], [0, 0], "WBMP type and fixed header");
      await this.clickTab(0);
      return `${Object.keys(exported).length} formats written from a ${decoded.shape.slice(0, 2).join("x")} view`;
    });
  }

  async matplotlibWindows() {
    await this.run.check("G-06 F-113 window", "each Matplotlib Window export opens its own non-modal window; the page stays usable and closing one drops only its figure", async () => {
      await this.fresh();
      await this.importFile("npy", path.join(this.inputs, "npy_real.npy"));
      await this.page.locator('.tv-slicer__pane[data-view="imv1_1"] .tv-pg-btn').nth(0).click();
      await this.page.waitForTimeout(300);
      const plot = await this.T(() => { const r = window.app.tomovisPage.views[0].views.imv1_1.roiPlot.view.el.getBoundingClientRect(); return { x: r.left + r.width / 2, y: r.top + r.height / 2 }; });
      await this.page.mouse.click(plot.x, plot.y, { button: "right" });
      await this.page.locator(".tv-menu .tv-menu__item", { hasText: "Export..." }).click();
      await this.page.locator(".tv-pg-export__formats .tv-pg-export__row", { hasText: "Matplotlib Window" }).click();
      const exportBtn = this.page.locator(".tv-pg-export__buttons .tv-button", { hasText: "Export" });
      await exportBtn.click();
      await this.page.waitForSelector(".tv-pg-mplwindow .tv-mpl-canvas");
      const title = await this.T(() => { const r = document.querySelector(".tv-pg-mplwindow .tv-modal__title").getBoundingClientRect(); return { x: r.left + 60, y: r.top + r.height / 2 }; });
      await this.page.mouse.move(title.x, title.y);
      await this.page.mouse.down();
      await this.page.mouse.move(title.x - 420, title.y - 120, { steps: 6 });
      await this.page.mouse.up();
      await exportBtn.click();
      await this.page.waitForFunction(() => document.querySelectorAll(".tv-pg-mplwindow").length === 2);
      await this.page.waitForTimeout(400);
      await H.shot(this.page, "g06_matplotlib_windows", "fixer", { element: ".page--tomovis" });
      await this.T(() => [...document.querySelectorAll(".tv-pg-export__buttons .tv-button")].find((b) => b.textContent === "Close").click());
      const windows = await this.T(() => [...document.querySelectorAll(".tv-pg-mplwindow")].map((w) => ({ modal: w.getAttribute("aria-modal"), figure: w.querySelector(".tv-mpl-canvaswrap").dataset.figure, title: w.querySelector(".tv-modal__title").firstChild.textContent })));
      const scrims  = await this.T(() => document.querySelectorAll(".tv-modal__scrim").length);

      await this.clickTab(1);
      const tabWhileOpen = await this.tabIndex();
      await this.clickTab(0);
      await this.page.keyboard.press("Escape");
      const afterEscape = await this.T(() => document.querySelectorAll(".tv-pg-mplwindow").length);

      const first = windows[0].figure;
      await this.page.locator(".tv-pg-mplwindow").first().locator(".tv-pg-mplwindow__close").click();
      await H.waitIdle(this.page);
      const left    = await this.T(() => [...document.querySelectorAll(".tv-pg-mplwindow .tv-mpl-canvaswrap")].map((w) => w.dataset.figure));
      const probe   = (name) => this.T(async (n) => (await fetch("/api/tomovis/figure", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ sid: window.app.tomovisPage.ctx.session.sid, figure: n, op: "refresh" }) })).status, name);
      const dropped = await probe(first);
      const alive   = await probe(left[0]);

      R.equal(windows.map((w) => [w.modal, w.title]), [["false", "Matplotlib Window"], ["false", "Matplotlib Window"]], "two non-modal windows");
      R.assert(windows[0].figure !== windows[1].figure, "each window has its own figure");
      R.equal(scrims, 0, "no scrim behind the windows");
      R.equal(tabWhileOpen, [1, 1], "the tab bar works while the windows are open");
      R.equal(afterEscape, 2, "Escape does not close a QMainWindow");
      R.equal(left.length, 1, "one window left after closing the first");
      R.equal([alive, dropped], [200, 404], "the other window's figure answers, the closed one's is gone");
      await this.page.locator(".tv-pg-mplwindow .tv-pg-mplwindow__close").click();
      return `figures ${windows.map((w) => w.figure).join(", ")}; closed one answers ${dropped}`;
    });
  }

  async svgCopy() {
    await this.run.check("G-06 F-113 copy", "Copy of an SVG export puts image/svg+xml on the clipboard, as pyqtgraph's QMimeData did; images go as image/png", async () => {
      await this.page.context().grantPermissions(["clipboard-read", "clipboard-write"], { origin: this.options.base });
      await this.fresh();
      await this.importFile("npy", path.join(this.inputs, "npy_real.npy"));
      const view = await this.T(() => { const iv = window.app.tomovisPage.views[0].views.imv1_1; const p = iv.view.mapViewToScene(20, 10); const r = iv.scene.el.getBoundingClientRect(); return { x: r.left + p.x, y: r.top + p.y }; });
      await this.page.mouse.click(view.x, view.y, { button: "right" });
      await this.page.locator(".tv-menu .tv-menu__item", { hasText: "Export..." }).click();
      const read = () => this.T(async () => { const items = await navigator.clipboard.read(); const out = []; for (const item of items) for (const type of item.types) out.push([type, (await item.getType(type)).size, type === "image/svg+xml" ? (await (await item.getType(type)).text()).startsWith("<svg") : ""]); return out; });
      await this.page.locator(".tv-pg-export__formats .tv-pg-export__row", { hasText: "SVG" }).click();
      await this.page.locator(".tv-pg-export__buttons .tv-button", { hasText: "Copy" }).click();
      await this.page.waitForTimeout(300);
      const svg = await read();
      await this.page.locator(".tv-pg-export__formats .tv-pg-export__row", { hasText: "Image File" }).click();
      await this.page.locator(".tv-pg-export__buttons .tv-button", { hasText: "Copy" }).click();
      await this.page.waitForTimeout(300);
      const png = await read();
      await this.page.locator(".tv-pg-export__buttons .tv-button", { hasText: "Close" }).click();
      R.equal(svg.map((x) => [x[0], x[2]]), [["image/svg+xml", true]], "SVG clipboard (Chrome hands back a sanitised SVG on read)");
      R.equal(png.map((x) => x[0]), ["image/png"], "image clipboard");
      return `SVG ${svg[0][1]} bytes as image/svg+xml, image ${png[0][1]} bytes as image/png`;
    });
  }

  async firstAutoRange() {
    await this.run.check("G-05 F-110", "the first auto-range after an import with the default ROI sticking out converges to pyqtgraph's view range at 900x340", async () => {
      await this.fresh();
      await this.page.addStyleTag({ content: ".tv-panel.tv-slicer { grid-template-rows: 340px 340px auto auto !important; } .tv-slicer__stack { width: 1060px; }" });
      await this.page.waitForTimeout(200);
      await this.importFile("hd5", path.join(this.inputs, "fusar_two_key_elev.hd5"));
      await this.page.waitForTimeout(1500);
      const golden = H.golden("import_fusar_two_key_elev").steps[1].state.views;
      const ours   = await this.T(() => { const t = window.app.tomovisPage.views[0]; return { imv1_1: t.views.imv1_1.view.viewRange(), imv2_1: t.views.imv2_1.view.viewRange(), size: [t.views.imv1_1.view.rect.w, t.views.imv1_1.view.rect.h], pending: t.views.imv1_1.view.needsAutoRange }; });
      const paints = await this.T(() => new Promise((resolve) => { const vb = window.app.tomovisPage.views[0].views.imv1_1.view; let n = 0; const original = vb.updateAutoRange.bind(vb); vb.updateAutoRange = () => { n += 1; original(); }; setTimeout(() => { vb.updateAutoRange = original; resolve(n); }, 600); }));
      R.equal(ours.size, [900, 340], "view size");
      for (const name of ["imv1_1", "imv2_1"]) {
        const flat = ours[name].flat();
        const want = golden[name].view_range.flat();
        flat.forEach((v, k) => R.assert(Math.abs(v - want[k]) < 1e-6, `${name} view range ${JSON.stringify(ours[name])} vs ${JSON.stringify(golden[name].view_range)}`));
      }
      R.equal([ours.pending, paints], [false, 0], "the feedback loop has settled");
      const hits = await this.T(() => {
        const roi  = window.app.tomovisPage.views[0].roi;
        const [a, b] = roi.endpoints().map((h) => roi.devicePoint(h.pos()));
        const len  = Math.hypot(b.x - a.x, b.y - a.y);
        const n    = [-(b.y - a.y) / len, (b.x - a.x) / len];
        const mid  = [(a.x + b.x) / 2, (a.y + b.y) / 2];
        return [3, 10, 14, 15, 17, 20].map((d) => [d, roi.hit(mid[0] + n[0] * d, mid[1] + n[1] * d)]);
      });
      R.equal(hits, [[3, true], [10, true], [14, true], [15, true], [17, false], [20, false]], "ROI hit width across the line, as pyqtgraph's shape measured in the original");
      await this.fresh();
      return `imv1_1 y ${ours.imv1_1[1].map((v) => v.toFixed(6)).join("..")}, golden ${golden.imv1_1.view_range[1].map((v) => v.toFixed(6)).join("..")}; hit width 16 px`;
    });
  }

  async main() {
    const opened = await H.launch({ port: this.options.port, gl: this.options.gl, viewport: { width: 1440, height: 1000 } });
    this.options.base = opened.base;
    this.page = opened.page;
    await H.openTomoVis(this.page);

    if (this.wanted("profile")) await this.profileWithoutData();
    if (this.wanted("tabs")) await this.tabKeys();
    if (this.wanted("wheel")) await this.tabWheel();
    if (this.wanted("radios")) await this.volumeRadios();
    if (this.wanted("norm")) await this.normalizationRadios();
    if (this.wanted("log")) await this.volumeErrorLevels();
    if (this.wanted("colors")) await this.customColors();
    if (this.wanted("save")) await this.figureSaveFormats();
    if (this.wanted("formats")) await this.imageFormats();
    if (this.wanted("mplwindow")) await this.matplotlibWindows();
    if (this.wanted("copy")) await this.svgCopy();
    if (this.wanted("autorange")) await this.firstAutoRange();

    await opened.browser.close();
    const errors = [...opened.errors, ...this.errors].filter((e) => !(this.wanted("mplwindow") && e === "console: Failed to load resource: the server responded with a status of 404 (Not Found)"));
    const ok = this.run.summary(errors);
    fs.writeFileSync(path.join(this.out, "fixer_checks.json"), JSON.stringify({ results: this.run.results, errors }, null, 2));
    process.exit(ok ? 0 : 1);
  }

  wanted(name) {
    return this.options.only.length === 0 || this.options.only.includes(name);
  }
}

const options = H.args(process.argv);
options.audit = process.env.TOMOVIS_AUDIT_DIR || path.join(REPO, "logs/tomovis_port/fixer/originals");
await new FixerChecks(options).main();
