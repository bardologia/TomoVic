import fs from "node:fs";
import path from "node:path";
import { TomoVisHarness as H, TomoVisCheckRun as R, REPO } from "./harness.mjs";

class SlicerChecks {
  static ORIGINAL_SEQUENCE = [
    ["10_single_loaded_default_roi", null],
    ["11_single_roi_oblique", ["30", "40", "12", "330", "0", "0"]],
    ["12_single_roi_horizontal", ["10", "100", "0", "380", "0", "0"]],
  ];

  constructor(options) {
    this.options = options;
    this.run     = new R("slicer");
    this.out     = H.shotDir("slicer");
    this.exports = path.join(this.out, "exports");
    this.errors  = [];
    fs.mkdirSync(this.exports, { recursive: true });
    for (const file of fs.readdirSync(this.exports)) fs.rmSync(path.join(this.exports, file));
  }

  T(fn, arg) {
    return this.page.evaluate(fn, arg);
  }

  async fresh(file = "inputs/npy_real.npy") {
    await this.page.goto("about:blank");
    await H.openTomoVis(this.page);
    if (file) await this.importFile(file);
  }

  async importFile(file) {
    const menu = file.endsWith(".hd5") ? "hd5" : "npy";
    await H.menu(this.page, "File", "Import", menu);
    await H.chooseFile(this.page, path.isAbsolute(file) ? file : H.fixture(file));
    await this.page.waitForTimeout(150);
  }

  async snapshot() {
    return H.snapshot(this.page);
  }

  async scr(view, x, y) {
    return this.T(([view, x, y]) => {
      const iv = window.app.tomovisPage.views[0].views[view];
      const p  = iv.view.mapViewToScene(x, y);
      const r  = iv.scene.el.getBoundingClientRect();
      return { x: r.left + p.x, y: r.top + p.y };
    }, [view, x, y]);
  }

  async roiPoint(frac) {
    return this.T((frac) => {
      const t      = window.app.tomovisPage.views[0];
      const [a, b] = t.roi.endpoints().map((h) => t.roi.devicePoint(h.pos()));
      const r      = t.roi.vb.scene.el.getBoundingClientRect();
      return { x: r.left + a.x + (b.x - a.x) * frac, y: r.top + a.y + (b.y - a.y) * frac };
    }, frac);
  }

  async drag(a, b, { button = "left", mods = [], cancel = false, steps = 10 } = {}) {
    await this.page.mouse.move(a.x, a.y);
    for (const m of mods) await this.page.keyboard.down(m);
    await this.page.mouse.down({ button });
    for (let i = 1; i <= steps; i += 1) await this.page.mouse.move(a.x + (b.x - a.x) * i / steps, a.y + (b.y - a.y) * i / steps);
    if (cancel) await this.page.mouse.click(b.x, b.y, { button: "right" });
    await this.page.mouse.up({ button });
    for (const m of mods) await this.page.keyboard.up(m);
    await H.waitIdle(this.page);
  }

  async setRoi(values) {
    for (let i = 0; i < 6; i += 1) await this.page.fill(`[data-widget="tab1QLineEdit${i + 1}"]`, values[i]);
    await H.waitIdle(this.page);
    await this.page.click('[data-widget="tab1SetButton"]');
    await H.waitIdle(this.page);
  }

  async menuTexts() {
    return this.T(() => [...document.querySelectorAll(".tv-menu")].at(-1) ? [...[...document.querySelectorAll(".tv-menu")].at(-1).children].map((row) => (row.classList.contains("tv-menu__separator") ? "---" : row.textContent.trim())) : []);
  }

  async closeMenus() {
    await this.page.keyboard.press("Escape");
    await this.T(() => { if (window.TomoVisMenu.root) window.TomoVisMenu.root.close(); });
  }

  async saveAs(file) {
    await this.page.waitForSelector(".tv-filedialog[data-dir]", { timeout: 15000 });
    await this.page.fill(".tv-filedialog .tv-filedialog__name", file);
    await this.page.click(".tv-filedialog .tv-filedialog__accept");
    await this.page.waitForSelector(".tv-filedialog", { state: "detached", timeout: 15000 });
    await this.page.waitForTimeout(500);
  }

  imageSize(file) {
    return JSON.parse(H.python("import json, sys; from PIL import Image; im = Image.open(sys.argv[1]); print(json.dumps([im.size[0], im.size[1]]))", file));
  }

  async compareRender(view, scenario, key) {
    const golden = H.goldenArray(scenario, key);
    const ours   = await this.T((view) => Array.from(window.app.tomovisPage.views[0].views[view].imageItem.rgba()), view);
    R.equal(ours.length, golden.data.length, `${view} render length`);
    let diff = 0;
    for (let i = 0; i < ours.length; i += 1) if (ours[i] !== golden.data[i]) diff += 1;
    R.equal(diff, 0, `${view} render differs from ${scenario}/${key}`);
    return `${view} ${golden.shape.join("x")} pixel-exact`;
  }

  async layout() {
    await this.run.check("F-030", "Slicer layout: two stacked ImageViews and the two control rows in the original order", async () => {
      await this.fresh(null);
      const rows = await this.T(() => [...document.querySelectorAll(".tv-slicer__row")].map((row) => [...row.children].map((c) => (c.classList.contains("tv-label") ? c.textContent : (c.dataset.widget || c.className.split(" ")[0])))));
      R.equal(rows[0], ["Slices (Automatic):", "tab1ChkBox", "tab1Slider", "tab1SpinBox", "tab1PlayButton", "Colormap", "tab1ComboBox", "tv-stretch"], "row 1");
      R.equal(rows[1], ["ROI (Manual):", "Ax", "tab1QLineEdit1", "Ay", "tab1QLineEdit2", "Angle [°]", "tab1QLineEdit3", "Length", "tab1QLineEdit4", "Pos x", "tab1QLineEdit5", "Pos y", "tab1QLineEdit6", "tv-stretch", "tab1SetButton", "tab1PlotButton"], "row 2");
      const panes = await this.T(() => [...document.querySelectorAll(".tv-slicer__pane")].map((p) => [p.dataset.view, p.classList.contains("is-current"), [...p.querySelectorAll(".tv-pg-btn")].map((b) => b.textContent)]));
      R.equal(panes, [["imv1_1", false, ["ROI", "Menu"]], ["imv1_2", true, ["ROI", "Menu"]], ["imv2_1", false, ["ROI", "Menu"]], ["imv2_2", true, ["ROI", "Menu"]]], "panes");
      const icon = await this.T(() => document.querySelector('[data-widget="tab1PlayButton"] img').getAttribute("src"));
      R.equal(icon, "/static/img/tomovis/play.png", "Play icon");
      const strip = await this.T(() => { const h = window.app.tomovisPage.views[0].views.imv1_2.histogram; return [h.view.width, h.gradient.rect.w, h.vb.rect.w > 44, h.axis.rect.w > 0]; });
      R.equal(strip, [160, 30, true, true], "histogram strip");
      await H.shot(this.page, "01_startup_slicer_no_data", "slicer", { element: "#tv-window" });
      H.compareShot("01_startup_slicer_no_data", path.join(this.options.original, "01_startup_slicer_no_data.png"));
      return "rows, panes, ROI/Menu buttons, 160 px strip";
    });
  }

  async renders() {
    await this.run.check("F-031/F-038/F-116", "Mono top view and tomogram render pixel-exact with the gradient LUT", async () => {
      await this.fresh();
      const a = await this.compareRender("imv1_1", "import_npy_real", "s01_imv1_1_render");
      const b = await this.compareRender("imv2_1", "import_npy_real", "s01_imv2_1_render");
      const lut = H.goldenArray("import_npy_real", "s01_imv1_1_lut");
      const ours = await this.T(() => Array.from(window.app.tomovisPage.views[0].views.imv1_1.histogram.getLookupTable()));
      R.equal(ours, lut.data, "gradient LUT");
      const golden = H.golden("import_npy_real").steps[1].state.views.imv1_1;
      const state  = await this.T(() => { const h = window.app.tomovisPage.views[0].views.imv1_1.histogram; return [h.getLevels(), h.vb.viewRange()[1]]; });
      R.equal(state, [golden.histogram_levels, golden.histogram_range], "levels and padded histogram range");
      return `${a}; ${b}; LUT and levels equal the golden`;
    });

    await this.run.check("F-032/F-039", "RGB composite and RGB tomogram render pixel-exact with per-channel levels (D-1)", async () => {
      await this.importFile("inputs/npy_channels_3.npy");
      const a = await this.compareRender("imv1_2", "channels_3_modes", "s01_imv1_2_render");
      const b = await this.compareRender("imv2_2", "channels_3_modes", "s01_imv2_2_render");
      const golden = H.golden("channels_3_modes").steps[1].state.views.imv1_2;
      const state  = await this.T(() => { const h = window.app.tomovisPage.views[0].views.imv1_2.histogram; return [h.levelMode, h.getLevels(), h.vb.viewRange()[1], h.gradient.visible, h.regions.map((r) => r.visible)]; });
      R.equal(state, ["rgba", golden.histogram_levels, golden.histogram_range, false, [false, true, true, true, false]], "rgba strip");
      await H.shot(this.page, "70_rgb_loaded", "slicer", { element: "#tv-window" });
      H.compareShot("70_rgb_loaded", path.join(this.options.original, "70_rgb_levels_fixed_loaded_default_roi.png"));
      return `${a}; ${b}; three regions, gradient hidden`;
    });
  }

  async viewRanges() {
    await this.run.check("F-110 auto-range", "At the original 900x340 view size the auto-range after Set equals the golden view ranges", async () => {
      await H.openTomoVis(this.page);
      await this.page.addStyleTag({ content: ".tv-panel.tv-slicer { grid-template-rows: 340px 340px auto auto !important; } .tv-slicer__stack { width: 1060px; }" });
      await this.page.waitForTimeout(200);
      await this.importFile("inputs/fusar_two_key_elev.hd5");
      await this.setRoi(["2", "10", "0", "20", "0", "0"]);
      await this.page.waitForTimeout(200);
      const golden = H.golden("roi_horizontal").steps[2].state.views;
      const ours   = await this.T(() => { const t = window.app.tomovisPage.views[0]; return [t.views.imv1_1.view.viewRange(), t.views.imv2_1.view.viewRange(), t.views.imv1_1.view.rect.w, t.views.imv1_1.view.rect.h]; });
      R.equal(ours[2], 900, "view width");
      R.equal(ours[3], 340, "view height");
      for (const [i, name] of [[0, "imv1_1"], [1, "imv2_1"]]) {
        const flat = ours[i].flat();
        const want = golden[name].view_range.flat();
        flat.forEach((v, k) => R.assert(Math.abs(v - want[k]) < 1e-9, `${name} view range ${JSON.stringify(ours[i])} vs ${JSON.stringify(golden[name].view_range)}`));
      }
      await this.page.reload();
      return `imv1_1 ${JSON.stringify(ours[0])}, imv2_1 ${JSON.stringify(ours[1])}`;
    });
  }

  async roiLine() {
    await this.run.check("F-110 follow", "While auto-range is on the view follows the ROI bounds during a handle drag", async () => {
      await this.fresh();
      const r0 = await this.T(() => window.app.tomovisPage.views[0].views.imv1_1.view.viewRange());
      await this.drag(await this.scr("imv1_1", 50, 64), await this.scr("imv1_1", 20, 15));
      const r1 = await this.T(() => window.app.tomovisPage.views[0].views.imv1_1.view.viewRange());
      R.assert(r1[1][1] - r1[1][0] < r0[1][1] - r0[1][0], `view followed ${JSON.stringify(r0)} -> ${JSON.stringify(r1)}`);
      return `y span ${(r0[1][1] - r0[1][0]).toFixed(2)} -> ${(r1[1][1] - r1[1][0]).toFixed(2)}`;
    });

    await this.run.check("F-033/F-121 handles", "Handle hover turns yellow; a handle drags freely and the server rewrites the fields", async () => {
      await this.fresh();
      const c = await this.scr("imv1_1", 16, 12);
      await this.page.mouse.click(c.x, c.y, { button: "right" });
      await this.page.locator(".tv-menu .tv-menu__item", { hasText: "View All" }).click();
      const h1 = await this.scr("imv1_1", 50, 64);
      await this.page.mouse.move(h1.x, h1.y);
      await this.page.waitForTimeout(60);
      const pens = await this.T(() => window.app.tomovisPage.views[0].roi.handles.map((h) => h.item.currentPen.color.join(",")));
      R.equal(pens, ["255,255,255,255", "255,255,0,255"], "hover pens");
      const target = await this.scr("imv1_1", 20, 15);
      await this.drag(h1, target);
      const s = await this.snapshot();
      const handle = s.controls.roi_1.handles[1].pos;
      R.assert(Math.abs(handle[0] - 20) < 0.2 && Math.abs(handle[1] - 15) < 0.2 && handle[0] % 1 !== 0, `free handle at ${handle}`);
      R.equal([s.controls.tab1QLineEdit3.text, s.controls.tab1QLineEdit4.text], ["36.8699", "25.0000"], "fields");
      R.assert(s.attributes.d2_shape[0] === Math.trunc(Math.hypot(handle[0], handle[1])), `tomogram width ${s.attributes.d2_shape} for a line of length ${Math.hypot(handle[0], handle[1])} (affineSlice takes int(length))`);
      return `handle ${handle.map((v) => v.toFixed(3))}, Angle ${s.controls.tab1QLineEdit3.text}, Length ${s.controls.tab1QLineEdit4.text}, d2 ${s.attributes.d2_shape}`;
    });

    await this.run.check("F-121 body snap", "Dragging the line body by fractional pixels moves its origin in whole-pixel steps", async () => {
      const a = await this.roiPoint(0.5);
      await this.drag(a, { x: a.x + 23.3, y: a.y + 7.9 }, { steps: 7 });
      const s = await this.snapshot();
      R.assert(s.controls.roi_1.pos.every((v) => Number.isInteger(v)) && s.controls.roi_1.pos.some((v) => v !== 0), `pos ${s.controls.roi_1.pos}`);
      R.equal([s.controls.tab1QLineEdit5.text, s.controls.tab1QLineEdit6.text], s.controls.roi_1.pos.map((v) => v.toFixed(4)), "Pos fields");
      return `pos ${s.controls.roi_1.pos}`;
    });

    await this.run.check("F-121 cancel", "A right click during a body drag restores the pre-drag state", async () => {
      const before = await this.T(() => window.app.tomovisPage.views[0].roi.clientState());
      const a = await this.roiPoint(0.5);
      await this.drag(a, { x: a.x + 40, y: a.y + 30 }, { cancel: true });
      const after  = await this.T(() => window.app.tomovisPage.views[0].roi.clientState());
      const server = (await this.snapshot()).controls.roi_1;
      const flat = (state) => [...state.pos, ...state.size, state.angle, ...state.handles.flatMap((h) => [...h.pos, ...h.item])];
      const gap  = Math.max(...flat(after).map((v, i) => Math.abs(v - flat(before)[i])));
      R.assert(gap < 1e-9, `client state ${JSON.stringify(after)} vs ${JSON.stringify(before)} (setState goes through parent coordinates, so the last bit may differ)`);
      R.equal(server.pos, before.pos, "server pos");
      return "restored on both sides";
    });

    await this.run.check("F-121/Q-024 rotate", "Alt+drag rotates the drawn line; the Angle field ignores the rotation", async () => {
      const angleBefore = (await this.snapshot()).controls.tab1QLineEdit3.text;
      const a = await this.roiPoint(0.5);
      await this.drag(a, { x: a.x + 30, y: a.y }, { mods: ["Alt"] });
      const s = await this.snapshot();
      R.equal(s.controls.roi_1.angle, -15, "angle");
      R.equal(s.controls.tab1QLineEdit3.text, angleBefore, "Angle field");
      const b = await this.roiPoint(0.5);
      await this.drag(b, { x: b.x, y: b.y - 20 }, { mods: ["Shift"] });
      const size = (await this.snapshot()).controls.roi_1.size;
      R.assert(Math.abs(size[0] - Math.pow(1.01, 20)) < 1e-9, `Shift scale ${size}`);
      const quirk = await this.T(() => {
        const roi   = window.app.tomovisPage.views[0].roi;
        const saved = roi.clientState();
        roi.state.pos   = [-17.140841185107476, 3.361211754417866];
        roi.state.size  = [1.220190039947967, 1.220190039947967];
        roi.state.angle = -15;
        roi.handles[1].pos = [50, 64];
        roi.handles[1].item.setPos(50 * 1.220190039947967, 64 * 1.220190039947967);
        roi.handles[0].pos = [0, 0];
        roi.handles[0].item.setPos(0, 0);
        roi.setState(roi.getState());
        const out = roi.handles[1].pos.slice();
        roi.applyServerState({ ...saved, handles: saved.handles });
        return out;
      });
      R.assert(Math.abs(quirk[0] - 38.71891468541344) < 1e-6 && Math.abs(quirk[1] - 91.22165769339857) < 1e-6, `rotated setState quirk ${quirk}`);
      return `angle -15, Angle field ${angleBefore}, scale ${size[0].toFixed(4)}, cancel-after-rotation quirk equals pyqtgraph (38.7189, 91.2217)`;
    });

    await this.run.check("F-035/F-040/Q-025", "Set places the line; a line fully outside clears both tomogram panes and keeps the strip", async () => {
      await this.fresh();
      await this.setRoi(["10", "5", "90", "30", "0", "0"]);
      const s = await this.snapshot();
      const ends = await this.T(() => { const r = window.app.tomovisPage.views[0].roi; return r.endpoints().map((h) => r.mapToParent(h.pos())); });
      R.equal(ends.map((p) => p.map((v) => Math.round(v * 1e6) / 1e6)), [[10, 5], [10, 35]], "endpoints");
      R.equal(s.attributes.x_label, "Range [m]", "x label");
      await this.setRoi(["100", "100", "45", "10", "0", "0"]);
      const cleared = await this.T(() => { const t = window.app.tomovisPage.views[0]; return [t.views.imv2_1.imageItem.image === null, t.views.imv2_1.histogram.plots[0].x.length > 0]; });
      R.equal(cleared, [true, true], "tomogram cleared, histogram kept");
      await H.shot(this.page, "f040_roi_outside", "slicer", { element: "#tv-window" });
      return "line (10,5)-(10,35), Range [m]; outside: pane black";
    });
  }

  async sliceMode() {
    await this.run.check("F-042/F-045/F-122", "Slice mode shows a 3 px white horizontal line at the slice that cannot be dragged", async () => {
      await this.fresh();
      await this.page.click('[data-widget="tab1ChkBox"]');
      await H.waitIdle(this.page);
      await this.page.fill('[data-widget="tab1SpinBox"] input', "10");
      await this.page.press('[data-widget="tab1SpinBox"] input', "Enter");
      await H.waitIdle(this.page);
      const line = await this.T(() => { const t = window.app.tomovisPage.views[0]; return [t.sliceLine.value(), t.sliceLine.visible, t.sliceLine.pen.width, t.sliceLine.pen.color.join(","), t.lineView, t.sliceLine.movable]; });
      R.equal(line, [10, true, 3, "255,255,255,255", "imv1_1", false], "slice line");
      const p = await this.scr("imv1_1", 26, 10);
      await this.drag(p, { x: p.x, y: p.y + 40 });
      const after = await this.T(() => window.app.tomovisPage.views[0].sliceLine.value());
      R.equal(after, 10, "line not movable");
      await H.shot(this.page, "f045_slice_line", "slicer", { element: "#tv-window" });
      return "line at y=10 in imv1_1, drag pans the view instead";
    });

    await this.run.check("F-046", "Play toggles the 500 ms timer and disables the colormap combo and spin box", async () => {
      await this.page.click('[data-widget="tab1PlayButton"]');
      await H.waitIdle(this.page);
      const s = await this.snapshot();
      R.equal([s.controls.tab1Timer.active, s.controls.tab1Timer.interval, s.controls.tab1ComboBox.enabled, s.controls.tab1SpinBox.enabled], [true, 500, false, false], "playing");
      await this.page.waitForTimeout(1200);
      await this.page.click('[data-widget="tab1PlayButton"]');
      await H.waitIdle(this.page);
      const t = await this.snapshot();
      R.assert(t.controls.tab1SpinBox.value > 10, `slice advanced to ${t.controls.tab1SpinBox.value}`);
      return `advanced to ${t.controls.tab1SpinBox.value}`;
    });
  }

  async colormaps() {
    await this.run.check("F-047", "bw linear greys both mono panes; blue-red-yellow doubles the tomogram's upper level", async () => {
      await this.fresh();
      const level = await this.T(() => window.app.tomovisPage.views[0].views.imv2_1.histogram.getLevels()[1]);
      await this.page.click('[data-widget="tab1ComboBox"]');
      await this.page.locator(".tv-combo__option", { hasText: /^bw linear$/ }).click();
      await H.waitIdle(this.page);
      const grey = await this.T(() => { const v = window.app.tomovisPage.views[0].views; return [v.imv1_1, v.imv2_1].map((iv) => { const lut = iv.histogram.getLookupTable(); return lut[0] === 0 && lut[255 * 3] === 255 && lut[128 * 3] === lut[128 * 3 + 1] && lut[128 * 3 + 1] === lut[128 * 3 + 2]; }); });
      R.equal(grey, [true, true], "grey LUTs");
      await this.page.click('[data-widget="tab1ComboBox"]');
      await this.page.locator(".tv-combo__option", { hasText: /^blue-red-yellow$/ }).click();
      await H.waitIdle(this.page);
      const doubled = await this.T(() => window.app.tomovisPage.views[0].views.imv2_1.histogram.getLevels()[1]);
      R.assert(Math.abs(doubled - 2 * level) < 1e-6, `level ${doubled} vs 2 x ${level}`);
      return `upper level ${level.toFixed(4)} -> ${doubled.toFixed(4)}`;
    });
  }

  async navigation() {
    await this.run.check("F-110", "Wheel zooms 1.346x per notch about the pointer, left drag pans, right drag zooms, the view survives image updates", async () => {
      await this.fresh();
      const c = await this.scr("imv1_1", 16, 12);
      const r0 = await this.T(() => window.app.tomovisPage.views[0].views.imv1_1.view.viewRange());
      await this.page.mouse.move(c.x, c.y);
      await this.page.mouse.wheel(0, -100);
      await this.page.waitForTimeout(150);
      const r1 = await this.T(() => window.app.tomovisPage.views[0].views.imv1_1.view.viewRange());
      const ratio = (r0[0][1] - r0[0][0]) / (r1[0][1] - r1[0][0]);
      R.assert(Math.abs(ratio - Math.pow(1.02, 15)) < 1e-6, `zoom ratio ${ratio}`);
      await this.drag(c, { x: c.x + 50, y: c.y });
      const r2 = await this.T(() => window.app.tomovisPage.views[0].views.imv1_1.view.viewRange());
      R.assert(r2[0][0] < r1[0][0], "pan moved the range");
      await this.drag(c, { x: c.x, y: c.y + 20 }, { button: "right" });
      const r3 = await this.T(() => window.app.tomovisPage.views[0].views.imv1_1.view.viewRange());
      R.assert(r3[1][1] - r3[1][0] > r2[1][1] - r2[1][0], "right drag down zooms out");
      await this.setRoi(["2", "3", "30", "25", "0", "0"]);
      const r4 = await this.T(() => window.app.tomovisPage.views[0].views.imv1_1.view.viewRange());
      R.equal(r4, r3, "user view kept across updates");
      return `wheel ${ratio.toFixed(4)}x, pan, right-drag zoom, view kept`;
    });

    await this.run.check("F-111", "ViewBox menu entries; View All refits; Y axis Invert Axis flips the view", async () => {
      const c = await this.scr("imv1_1", 6, 20);
      await this.page.mouse.click(c.x, c.y, { button: "right" });
      const texts = await this.menuTexts();
      R.equal(texts, ["View All", "X axis", "Y axis", "Mouse Mode", "---", "Export..."], "menu");
      await this.page.locator(".tv-menu .tv-menu__item", { hasText: "Y axis" }).hover();
      await this.page.waitForTimeout(350);
      const widgets = await this.T(() => [...document.querySelectorAll(".tv-menu")].at(-1).querySelector(".tv-pg-axisctrl").innerText.split("\n").map((s) => s.trim()).filter(Boolean));
      await H.shot(this.page, "f111_y_axis_menu", "slicer", { element: ".page--tomovis" });
      await this.page.locator(".tv-menu").last().locator(".tv-check", { hasText: "Invert Axis" }).click();
      const inverted = await this.T(() => window.app.tomovisPage.views[0].views.imv1_1.view.state.yInverted);
      R.equal(inverted, false, "y inverted after unchecking");
      await this.closeMenus();
      await this.page.mouse.click(c.x, c.y, { button: "right" });
      await this.page.locator(".tv-menu .tv-menu__item", { hasText: "View All" }).click();
      const auto = await this.T(() => window.app.tomovisPage.views[0].views.imv1_1.view.viewRange());
      R.assert(auto[1][0] < 0 && auto[1][1] > 24, `View All ${JSON.stringify(auto)}`);
      return `menu ${texts.join(" | ")}; Y axis panel: ${widgets.join(", ")}`;
    });

    await this.run.check("F-112", "1 button mode zooms to the dragged box; - and + walk the zoom history", async () => {
      const c = await this.scr("imv1_1", 6, 20);
      await this.page.mouse.click(c.x, c.y, { button: "right" });
      await this.page.locator(".tv-menu .tv-menu__item", { hasText: "Mouse Mode" }).hover();
      await this.page.waitForTimeout(350);
      await this.page.locator(".tv-menu").last().locator(".tv-menu__item", { hasText: "1 button" }).click();
      const a1 = await this.scr("imv1_1", 2, 2);
      const b1 = await this.scr("imv1_1", 26, 20);
      await this.drag(b1, a1);
      const z1 = await this.T(() => window.app.tomovisPage.views[0].views.imv1_1.view.viewRange());
      const a2 = await this.scr("imv1_1", 4, 14);
      const b2 = await this.scr("imv1_1", 10, 19);
      await this.drag(a2, b2);
      await this.page.keyboard.press("-");
      await this.page.waitForTimeout(60);
      const back = await this.T(() => window.app.tomovisPage.views[0].views.imv1_1.view.viewRange());
      R.equal(back, z1, "history back");
      await this.page.keyboard.press("+");
      const fwd = await this.T(() => window.app.tomovisPage.views[0].views.imv1_1.view.viewRange());
      R.assert(fwd[0][1] - fwd[0][0] < z1[0][1] - z1[0][0], "history forward");
      return "box zoom, - back, + forward";
    });
  }

  async histogram() {
    await this.run.check("F-114", "Dragging a level line updates the image live; the region and connecting lines follow", async () => {
      await this.fresh();
      const p = await this.T(() => {
        const iv = window.app.tomovisPage.views[0].views.imv2_1;
        const vb = iv.histogram.vb;
        const vr = vb.viewRect();
        const q  = vb.mapViewToScene(vr.x + vr.w * 0.3, iv.histogram.getLevels()[1]);
        const r  = iv.histogram.view.el.getBoundingClientRect();
        return { x: r.left + q.x, y: r.top + q.y };
      });
      await this.page.mouse.move(p.x, p.y);
      await this.page.mouse.down();
      const seen = [];
      for (let i = 1; i <= 5; i += 1) {
        await this.page.mouse.move(p.x, p.y - i * 8);
        seen.push(await this.T(() => window.app.tomovisPage.views[0].views.imv2_1.imageItem.levels[1]));
      }
      await this.page.mouse.up();
      R.assert(seen.every((v, i) => i === 0 || v > seen[i - 1]), `levels during drag ${seen}`);
      await H.shot(this.page, "f114_level_drag", "slicer", { element: "#tv-window" });
      await this.setRoi(["2", "3", "30", "25", "0", "0"]);
      const reset = await this.T(() => window.app.tomovisPage.views[0].views.imv2_1.histogram.getLevels()[1]);
      const server = (await this.snapshot()).views.imv2_1.levels[1];
      R.equal(reset, server, "Q-020 level edit dropped on the next update");
      return `upper level rose live ${seen.map((v) => v.toFixed(3)).join(" < ")}; Set re-applied ${server.toFixed(4)}`;
    });

    await this.run.check("F-115", "ColorMaps menu tree, grey preset until the ROI moves (Q-020), tick add/drag/menu/colour", async () => {
      const grad = (frac, zone) => this.T(([frac, zone]) => {
        const iv = window.app.tomovisPage.views[0].views.imv1_1;
        const r  = iv.histogram.view.el.getBoundingClientRect();
        const g  = iv.histogram.gradient.geometry();
        return { x: r.left + g.barX + (zone === "tick" ? 22 : 7), y: r.top + g.y0 - frac * iv.histogram.gradient.length };
      }, [frac, zone]);
      const bar = await grad(0.5, "bar");
      await this.page.mouse.click(bar.x, bar.y, { button: "right" });
      await this.page.waitForSelector(".tv-menu");
      const tree = await this.menuTexts();
      R.equal(tree, ["None", "---", "preset gradient", "local", "cet (local)", "matplotlib", "---", "RGB", "HSV"], "ColorMaps menu");
      await this.page.locator(".tv-menu .tv-menu__item", { hasText: "preset gradient" }).hover();
      await this.page.waitForTimeout(350);
      await H.shot(this.page, "f115_colormaps_menu", "slicer", { element: ".page--tomovis" });
      await this.page.locator(".tv-menu").last().locator(".tv-pg-cmapentry", { hasText: /^grey$/ }).click();
      const trivial = await this.T(() => window.app.tomovisPage.views[0].views.imv1_1.histogram.gradient.isLookupTrivial());
      R.equal(trivial, true, "grey preset");
      const tick = await grad(0.5, "tick");
      await this.page.mouse.click(tick.x, tick.y);
      const ticks = await this.T(() => window.app.tomovisPage.views[0].views.imv1_1.histogram.gradient.listTicks().map(([t, x]) => [Number(x.toFixed(3)), t.color]));
      R.equal(ticks[1], [0.5, [127, 127, 127, 255]], "added tick");
      await this.drag({ x: tick.x + 2, y: tick.y }, { x: tick.x + 2, y: tick.y + 50 }, { steps: 5 });
      const moved = await this.T(() => window.app.tomovisPage.views[0].views.imv1_1.histogram.gradient.listTicks()[1][1]);
      R.assert(moved < 0.5, `dragged tick at ${moved}`);
      const top = await grad(1.0, "tick");
      await this.page.mouse.click(top.x, top.y + 3, { button: "right" });
      const tickMenu = await this.menuTexts();
      R.equal(tickMenu, ["Remove Tick", "Set Position", "Set Color"], "tick menu");
      await this.page.locator(".tv-menu .tv-menu__item", { hasText: "Set Color" }).click();
      await this.page.waitForSelector(".tv-colordialog");
      await this.page.locator(".tv-colordialog__cell").nth(5).click();
      const live = await this.T(() => window.app.tomovisPage.views[0].views.imv1_1.histogram.gradient.listTicks().at(-1)[0].color.join(","));
      await this.page.locator(".tv-colordialog .tv-modal__buttons .tv-button", { hasText: "OK" }).click();
      await this.setRoi(["3", "3", "30", "25", "0", "0"]);
      const count = await this.T(() => window.app.tomovisPage.views[0].views.imv1_1.histogram.gradient.ticks.size);
      R.equal(count, 256, "colortable re-applied");
      return `tick added at 0.5 (127 grey), dragged to ${moved.toFixed(3)}, colour applied live (${live}), 256 ticks after Set`;
    });
  }

  async imageViewButtons() {
    await this.run.check("F-117", "ROI button shows a 10x10 rect with scale and rotate handles and a 60/40 plot that follows it", async () => {
      await this.fresh();
      await this.page.locator('.tv-slicer__pane[data-view="imv1_1"] .tv-pg-btn').nth(0).click();
      await this.page.waitForTimeout(200);
      const info = await this.T(() => { const iv = window.app.tomovisPage.views[0].views.imv1_1; return [iv.roi.visible, iv.roi.getState(), iv.roi.handles.map((h) => h.type), iv.roiCurves.length, iv.roiCurves[0].rawY.length, Math.round(iv.gvHost.clientHeight / (iv.gvHost.clientHeight + iv.plotHost.clientHeight) * 100)]; });
      R.equal(info.slice(0, 5), [true, { pos: [0, 0], size: [10, 10], angle: 0 }, ["s", "r"], 1, 10], "PlotROI");
      R.assert(Math.abs(info[5] - 60) <= 1, `split ${info[5]}`);
      const before = await this.T(() => window.app.tomovisPage.views[0].views.imv1_1.roiCurves[0].rawY.slice());
      const a = await this.scr("imv1_1", 5, 5);
      await this.drag(a, { x: a.x + 60, y: a.y + 30 });
      const after = await this.T(() => window.app.tomovisPage.views[0].views.imv1_1.roiCurves[0].rawY.slice());
      R.assert(JSON.stringify(after) !== JSON.stringify(before), "curve follows");
      await H.shot(this.page, "17_imageview_roi_button", "slicer", { element: "#tv-window" });
      return `curve of ${after.length} points follows the rect`;
    });

    await this.run.check("F-113", "Export dialog: tree, five formats, params; PNG at 800 px, CSV, HDF5 and SVG of the ROI plot written on the server; CSV of a ViewBox is refused", async () => {
      const plot = await this.T(() => { const r = window.app.tomovisPage.views[0].views.imv1_1.roiPlot.view.el.getBoundingClientRect(); return { x: r.left + r.width / 2, y: r.top + r.height / 2 }; });
      await this.page.mouse.click(plot.x, plot.y, { button: "right" });
      const menu = await this.menuTexts();
      R.equal(menu, ["View All", "X axis", "Y axis", "Mouse Mode", "---", "Plot Options", "Export..."], "plot menu");
      await this.page.locator(".tv-menu .tv-menu__item", { hasText: "Export..." }).click();
      const rows = await this.T(() => [...document.querySelectorAll(".tv-pg-export__row")].map((e) => e.textContent + (e.classList.contains("is-selected") ? "*" : "")));
      R.equal(rows, ["Entire Scene", "Plot*", "ViewBox", "CSV of original plot data*", "HDF5 Export: plot (x,y)", "Image File (PNG, TIF, JPG, ...)", "Matplotlib Window", "Scalable Vector Graphics (SVG)"], "dialog rows");
      const exportBtn = this.page.locator(".tv-pg-export__buttons .tv-button", { hasText: "Export" });
      await exportBtn.click();
      await this.saveAs(path.join(this.exports, "roi_plot.csv"));
      await this.page.locator(".tv-pg-export__formats .tv-pg-export__row", { hasText: "HDF5" }).click();
      await exportBtn.click();
      await this.saveAs(path.join(this.exports, "roi_plot.h5"));
      await this.page.locator(".tv-pg-export__formats .tv-pg-export__row", { hasText: "SVG" }).click();
      await exportBtn.click();
      await this.saveAs(path.join(this.exports, "roi_plot.svg"));
      await this.page.locator(".tv-pg-export__formats .tv-pg-export__row", { hasText: "Image File" }).click();
      await this.page.locator(".tv-pg-export__param", { hasText: "width" }).click({ position: { x: 30, y: 16 } });
      await this.page.fill(".tv-pg-export__params .tv-spin__input >> nth=0", "800");
      await this.page.press(".tv-pg-export__params .tv-spin__input >> nth=0", "Enter");
      await exportBtn.click();
      await this.saveAs(path.join(this.exports, "roi_plot"));
      await H.shot(this.page, "f113_export_dialog", "slicer", { element: ".page--tomovis" });
      await this.page.locator(".tv-pg-export__buttons .tv-button", { hasText: "Close" }).click();
      const csv = fs.readFileSync(path.join(this.exports, "roi_plot.csv"), "utf-8").split("\r\n");
      R.equal(csv[0], "x0000,y0000", "CSV header");
      R.equal(csv[1].split(",")[0], "0.", "CSV first x");
      const size = this.imageSize(path.join(this.exports, "roi_plot.png"));
      R.equal(size[0], 800, "PNG width");
      const h5 = JSON.parse(H.python("import h5py, json, sys; f = h5py.File(sys.argv[1]); print(json.dumps(list(f['Export'].shape)))", path.join(this.exports, "roi_plot.h5")));
      R.equal(h5, [2, 10], "HDF5 dataset");
      const svg = fs.readFileSync(path.join(this.exports, "roi_plot.svg"), "utf-8");
      R.assert(svg.includes("<title>pyqtgraph SVG export</title>") && svg.includes("<path"), "SVG content");
      const view = await this.scr("imv1_1", 20, 10);
      await this.page.mouse.click(view.x, view.y, { button: "right" });
      await this.page.locator(".tv-menu .tv-menu__item", { hasText: "Export..." }).click();
      await exportBtn.click();
      await this.page.waitForTimeout(300);
      const dialogs = await this.T(() => document.querySelectorAll(".tv-filedialog").length);
      R.equal(dialogs, 0, "CSV of a ViewBox opens no save dialog");
      await this.page.locator(".tv-pg-export__buttons .tv-button", { hasText: "Close" }).click();
      return `CSV ${csv.length - 2} rows, PNG ${size.join("x")} (extension .png appended), HDF5 2x10, SVG ${svg.length} bytes`;
    });

    await this.run.check("F-118/F-119/F-120", "Menu button: Normalization panel (Divide resets levels to min/max) and Export writes the rendered image", async () => {
      await this.page.locator('.tv-slicer__pane[data-view="imv2_1"] .tv-pg-btn').nth(1).click();
      const texts = await this.menuTexts();
      R.equal(texts, ["Normalization", "Export"], "Menu button popup");
      await this.page.locator(".tv-menu .tv-menu__item", { hasText: "Normalization" }).click();
      const pane = '.tv-slicer__pane[data-view="imv2_1"]';
      const labels = await this.T((pane) => document.querySelector(`${pane} .tv-pg-normgroup`).innerText.split("\n").map((s) => s.trim()).filter(Boolean), pane);
      await this.page.locator(`${pane} .tv-radio`, { hasText: "Divide" }).click();
      const lv = await this.T(() => { const iv = window.app.tomovisPage.views[0].views.imv2_1; return [iv.histogram.getLevels(), iv.imageLevels[0]]; });
      R.equal(lv[0], lv[1], "levels at min/max");
      await H.shot(this.page, "f119_normalization", "slicer", { element: "#tv-window" });
      await this.page.locator(`${pane} .tv-radio`, { hasText: "Off" }).click();
      await this.page.locator('.tv-slicer__pane[data-view="imv1_1"] .tv-pg-btn').nth(1).click();
      await this.page.locator(".tv-menu .tv-menu__item").nth(1).click();
      await this.saveAs(path.join(this.exports, "menu_export.png"));
      const size = this.imageSize(path.join(this.exports, "menu_export.png"));
      R.equal(size, [32, 24], "Menu > Export size");
      return `panel ${labels.join(" ")}; Divide levels ${lv[0].map((v) => v.toFixed(4))}; export 32x24`;
    });

    await this.run.check("F-119 E-010", "Subtract on an RGB pane computes in float instead of raising", async () => {
      await this.importFile("inputs/npy_channels_3.npy");
      const pane = '.tv-slicer__pane[data-view="imv1_2"]';
      await this.page.locator(`${pane} .tv-pg-btn`).nth(1).click();
      await this.page.locator(".tv-menu .tv-menu__item", { hasText: "Normalization" }).click();
      await this.page.locator(`${pane} .tv-check`, { hasText: "Frame" }).click();
      await this.page.locator(`${pane} .tv-radio`, { hasText: "Subtract" }).click();
      const state = await this.T(() => { const iv = window.app.tomovisPage.views[0].views.imv1_2; return [iv.imageDisp.dtype, iv.histogram.getLevels().length, iv.histogram.getLevels()[0][0] < 0]; });
      R.equal(state, ["float32", 3, true], "float subtract with per-channel levels");
      return "float32, three channel levels below zero";
    });
  }

  async originalSequence() {
    await this.run.check("F-030 look", "Original screenshot sequence 10-18 with the realistic crop, side by side", async () => {
      const crop = path.join(REPO, "logs/tomovis_port/fixtures/realistic_traun_hv.hd5");
      if (!fs.existsSync(crop)) throw new Error(`realistic crop missing: ${crop}`);
      await this.page.setViewportSize({ width: 1136, height: 916 });
      await this.fresh(crop);
      for (const [name, roi] of SlicerChecks.ORIGINAL_SEQUENCE) {
        if (roi) await this.setRoi(roi);
        await this.page.waitForTimeout(200);
        await H.shot(this.page, name, "slicer", { element: "#tv-window" });
        H.compareShot(name, path.join(this.options.original, `${name}.png`));
      }
      await this.page.click('[data-widget="tab1ChkBox"]');
      await H.waitIdle(this.page);
      await this.page.fill('[data-widget="tab1SpinBox"] input', "100");
      await this.page.press('[data-widget="tab1SpinBox"] input', "Enter");
      await H.waitIdle(this.page);
      await H.shot(this.page, "13_single_slice_mode", "slicer", { element: "#tv-window" });
      H.compareShot("13_single_slice_mode", path.join(this.options.original, "13_single_slice_mode.png"));
      await this.page.click('[data-widget="tab1ChkBox"]');
      await H.waitIdle(this.page);
      await this.setRoi(["30", "40", "12", "330", "0", "0"]);
      for (const [index, name] of [["bw linear", "15_single_colortable_bw_linear"], ["blue-red-yellow", "16_single_colortable_blue_red_yellow"]]) {
        await this.page.click('[data-widget="tab1ComboBox"]');
        await this.page.locator(".tv-combo__option", { hasText: new RegExp(`^${index}$`) }).click();
        await H.waitIdle(this.page);
        await H.shot(this.page, name, "slicer", { element: "#tv-window" });
        H.compareShot(name, path.join(this.options.original, `${name}.png`));
      }
      await this.page.click('[data-widget="tab1ComboBox"]');
      await this.page.locator(".tv-combo__option", { hasText: /^IDL rainbow \(13\)$/ }).click();
      await H.waitIdle(this.page);
      await this.page.locator('.tv-slicer__pane[data-view="imv1_1"] .tv-pg-btn').nth(0).click();
      await this.page.waitForTimeout(300);
      await H.shot(this.page, "17_single_imageview_roi_button", "slicer", { element: "#tv-window" });
      H.compareShot("17_single_imageview_roi_button", path.join(this.options.original, "17_single_imageview_roi_button.png"));
      await this.page.locator('.tv-slicer__pane[data-view="imv1_1"] .tv-pg-btn').nth(0).click();
      await this.page.locator('.tv-slicer__pane[data-view="imv1_1"] .tv-pg-btn').nth(1).click();
      await this.page.waitForTimeout(200);
      await H.shot(this.page, "18_single_imageview_menu_button", "slicer", { element: ".page--tomovis" });
      H.compareShot("18_single_imageview_menu_button", path.join(this.options.original, "18_single_imageview_menu_button.png"));
      await this.closeMenus();
      await this.page.setViewportSize({ width: 1440, height: 1000 });
      return "10, 11, 12, 13, 15, 16, 17, 18 written with __vs__ side by sides";
    });
  }

  async main() {
    const opened = await H.launch({ port: this.options.port, gl: this.options.gl });
    this.page = opened.page;

    await this.layout();
    await this.renders();
    await this.viewRanges();
    await this.roiLine();
    await this.sliceMode();
    await this.colormaps();
    await this.navigation();
    await this.histogram();
    await this.imageViewButtons();
    await this.originalSequence();

    await opened.browser.close();
    const errors = [...opened.errors, ...this.errors].filter((e) => !this.options.ignore.some((text) => e.includes(text)));
    const ok = this.run.summary(errors);
    fs.writeFileSync(path.join(this.out, "slicer_checks.json"), JSON.stringify({ results: this.run.results, errors, ignored: this.options.ignore }, null, 2));
    process.exit(ok ? 0 : 1);
  }
}

const options = H.args(process.argv, "slicer");
options.original = process.env.TOMOVIS_ORIGINAL_SHOTS || path.join(REPO, "logs/tomovis_port/original_shots");
options.ignore   = (process.env.TOMOVIS_IGNORE_ERRORS || "").split("|").filter(Boolean);
await new SlicerChecks(options).main();
