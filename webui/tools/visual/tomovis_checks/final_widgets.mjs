import fs from "node:fs";
import path from "node:path";
import { createRequire } from "node:module";
import { TomoVisHarness as H, TomoVisCheckRun as R, REPO } from "./harness.mjs";

const require              = createRequire(import.meta.url);
const { chromium }         = require("playwright-core");
const { ChromiumResolver } = require("../chromium.js");

class FinalWidgetsChecks {
  static REALISTIC = path.join(REPO, "logs/tomovis_port/fixtures/realistic_traun_hv.hd5");
  static ROI       = ["30", "40", "12", "330", "0", "0"];
  static TOP_PANE  = '.tv-slicer__stack[data-stack="imv1"] .tv-slicer__pane.is-current';

  static ORIGINAL = {
    spinClicks : [[12, 7, 1], [5, 7, 1], [12, 21, -1], [14, 7, 1], [20, 7, 0]],
    row1Before : { chk: [150, 777, 14, 15], slider: [170, 777, 400, 15], spin: [576, 770, 44, 29], play: [626, 773, 28, 24], combo: [732, 769, 187, 32] },
    row1After  : { chk: [150, 777, 14, 15], slider: [170, 777, 400, 15], spin: [576, 770, 52, 29], up: [37, 3, 14, 11], down: [37, 14, 14, 12], edit: [3, 3, 32, 23], play: [634, 773, 28, 24], combo: [740, 769, 187, 32], handle: 193 },
    fields     : {
      1100 : [[144, 85], [259, 85], [414, 85], [558, 85], [691, 85], [823, 85], [914, 80], [1000, 80]],
      1404 : [[144, 90], [264, 90], [424, 90], [573, 90], [711, 90], [848, 90], [1218, 80], [1304, 80]],
    },
    comboPopup : { size: [187, 242], row: 24, visible: 10, scrollbar: 14, font: "17px" },
    validator  : [{"kind": "double", "min": 0, "max": 132.46, "decimals": 2, "suffix": "", "expect": {"": "I:", ".": "I:.", "-": "I:-", "+": "I:+", "-.": "I:-.", "+.": "I:+.", ".5": "A:.5", "-.5": "X", "5.": "A:5.", "-5": "X", "1e2": "A:1e2", "1,000": "X", "1,0": "X", ",5": "X", " 5": "A:5", "nan": "I:nan", "inf": "X", "-0": "A:-0", "99.999": "X", "0.1234567": "X", "100%": "X", "%": "X", "+0": "A:+0"}}, {"kind": "double", "min": -1000000000, "max": 1000000000, "decimals": 6, "suffix": "", "expect": {"": "I:", ".": "I:.", "-": "I:-", "+": "I:+", "-.": "I:-.", "+.": "I:+.", ".5": "A:.5", "-.5": "A:-.5", "5.": "A:5.", "-5": "A:-5", "1e2": "A:1e2", "1,000": "A:1,000", "1,0": "A:1,0", ",5": "X", " 5": "A:5", "nan": "I:nan", "inf": "X", "-0": "A:-0", "99.999": "A:99.999", "0.1234567": "X", "100%": "X", "%": "X", "+0": "A:+0"}}, {"kind": "int", "min": 0, "max": 199, "decimals": 0, "suffix": "", "expect": {"": "I:", ".": "X", "-": "X", "+": "I:+", "-.": "X", "+.": "X", ".5": "X", "-.5": "X", "5.": "X", "-5": "X", "1e2": "X", "1,000": "X", "1,0": "X", ",5": "X", " 5": "A:5", "nan": "X", "inf": "X", "-0": "X", "99.999": "X", "0.1234567": "X", "100%": "X", "%": "X", "+0": "A:+0"}}, {"kind": "int", "min": 1, "max": 100, "decimals": 0, "suffix": "%", "expect": {"": "I:%", ".": "X", "-": "X", "+": "I:+%", "-.": "X", "+.": "X", ".5": "X", "-.5": "X", "5.": "X", "-5": "X", "1e2": "X", "1,000": "X", "1,0": "X", ",5": "X", " 5": "A:5%", "nan": "X", "inf": "X", "-0": "X", "99.999": "X", "0.1234567": "X", "100%": "A:100%", "%": "I:%", "+0": "I:+0%"}}],
    xSpin      : { dot5: ["0.50", 0.5], minus5: ["-", "40.00", 40] },
    norm       : { group: [20, 309, 1060, 110], radios: [174, 324, 475], spins: [[324, 387, 151, 29], [625, 387, 151, 29], [926, 387, 151, 29]], up: [136, 3, 14, 11], rightEdges: [324, 625, 926] },
    histLabels : ["0", "2", "4"],
    histAxis   : { axis: [1, 1, 14.71875], vb: 15.71875, grad: 129, line: 934 },
    roiPlotVb  : { x: 39.703125, w: 1019.296875, h: 122.8 },
    svg        : { params: [900.5, 340.5], shown: ["901", "341"], image: ["900", "340"] },
    exportVb   : { row150: [373, 374, 375, 377, 379, 381, 383, 385, 387, 388, 390, 392, 394, 396, 398, 400, 402, 403, 405, 407, 409, 413, 415, 417], col450: [15, 16, 18, 20, 21, 25, 27, 29, 31, 33, 35, 36, 38, 40, 42, 44] },
    exportDlg  : { body: [262, 367], children: [[11, 11, 240, 24], [11, 35, 240, 85], [11, 120, 240, 24], [11, 144, 240, 85], [11, 229, 240, 24], [11, 253, 240, 71], [11, 324, 240, 32]], rowHeight: 24, formatWidth: 248, group: "params", groupHeight: 26, paramHeight: 32, buttons: [[11, 80], [91, 80], [171, 80]] },
    preset     : { size: [116, 338], row: [116, 26], swatch: [1, 1, 32, 24], text: 39 },
    axisMenu   : { size: [200, 217], percent: "100%", children: [[0, 1, 85, 30], [85, 0, 58, 32], [143, 0, 57, 32], [0, 33, 85, 30], [85, 32, 115, 33], [85, 65, 115, 30], [85, 95, 115, 30], [0, 125, 200, 30], [0, 155, 200, 30], [85, 185, 115, 32]] },
  };

  constructor(options) {
    this.options = options;
    this.run     = new R("final-widgets");
    this.out     = H.shotDir("final-widgets");
  }

  T(fn, arg) {
    return this.page.evaluate(fn, arg);
  }

  async fresh(width = 1100, height = 880) {
    await this.page.setViewportSize({ width, height });
    await this.page.goto("about:blank");
    await H.openTomoVis(this.page);
  }

  async importRealistic() {
    await H.menu(this.page, "File", "Import", "hd5");
    await H.chooseFile(this.page, FinalWidgetsChecks.REALISTIC);
    await H.waitIdle(this.page);
    await this.page.waitForTimeout(600);
  }

  async setRoi() {
    for (let i = 0; i < 6; i += 1) await this.page.fill(`[data-widget="tab1QLineEdit${i + 1}"]`, FinalWidgetsChecks.ROI[i]);
    await H.waitIdle(this.page);
    await this.page.click('[data-widget="tab1SetButton"]');
    await H.waitIdle(this.page);
  }

  async windowRect(selector) {
    return this.T((selector) => {
      const win = document.querySelector("#tv-window").getBoundingClientRect();
      const r   = [...document.querySelectorAll(selector)].at(-1).getBoundingClientRect();
      return [r.left - win.left, r.top - win.top, r.width, r.height].map((v) => Math.round(v * 1000) / 1000);
    }, selector);
  }

  async closeMenus() {
    await this.page.keyboard.press("Escape");
    await this.page.keyboard.press("Escape");
    await this.page.mouse.click(600, 872);
    await this.page.waitForTimeout(150);
  }

  async topViewPoint(x, y) {
    return this.T(([x, y]) => {
      const iv = window.app.tomovisPage.views[0].views.imv1_1;
      const q  = iv.view.mapViewToScene(x, y);
      const r  = iv.scene.el.getBoundingClientRect();
      return { x: r.left + q.x, y: r.top + q.y };
    }, [x, y]);
  }

  async spinColumns(selector) {
    return this.T((selector) => [...document.querySelectorAll(selector)].filter((s) => s.getBoundingClientRect().width > 0).map((s) => {
      const r = s.getBoundingClientRect();
      const u = s.querySelector(".tv-spin__up").getBoundingClientRect();
      const d = s.querySelector(".tv-spin__down").getBoundingClientRect();
      return { w: r.width, h: r.height, up: [u.left - r.left, u.top - r.top, u.width, u.height], down: [d.left - r.left, d.top - r.top, d.width, d.height] };
    }), selector);
  }

  static qtColumn(spin) {
    const h      = spin.h;
    const center = Math.floor(h / 2);
    return { up: [spin.w - 15, 3, 14, center - 3], down: [spin.w - 15, center, 14, h - center - 3] };
  }

  async openNormalization() {
    await this.page.click(`${FinalWidgetsChecks.TOP_PANE} .tv-pg-btn >> nth=1`);
    await this.page.waitForTimeout(200);
    await this.page.locator(".tv-menu .tv-menu__item", { hasText: "Normalization" }).click();
    await H.waitIdle(this.page);
    await this.page.waitForTimeout(300);
  }

  async openAxisMenu() {
    const c = await this.topViewPoint(60, 40);
    await this.page.mouse.click(c.x, c.y, { button: "right" });
    await this.page.waitForTimeout(200);
    await this.page.locator(".tv-menu .tv-menu__item", { hasText: "X axis" }).first().hover();
    await this.page.waitForTimeout(450);
  }

  async openExport(view = "imv1_1", x = 60, y = 40) {
    const c = await this.T(([view, x, y]) => {
      const iv = window.app.tomovisPage.views[0].views[view];
      const q  = iv.view.mapViewToScene(x, y);
      const r  = iv.scene.el.getBoundingClientRect();
      return { x: r.left + q.x, y: r.top + q.y };
    }, [view, x, y]);
    await this.page.mouse.click(c.x, c.y, { button: "right" });
    await this.page.waitForTimeout(200);
    await this.page.locator(".tv-menu .tv-menu__item", { hasText: "Export..." }).click();
    await this.page.waitForSelector(".tv-pg-export");
    await this.page.waitForTimeout(250);
  }

  async pickFormat(label) {
    await this.page.locator(".tv-pg-export__formats .tv-pg-export__row", { hasText: label }).click();
    await this.page.waitForTimeout(150);
  }

  async closeExport() {
    await this.page.locator(".tv-pg-export__buttons .tv-button", { hasText: "Close" }).click();
  }

  async spinButtons() {
    await this.run.check("LS-02 F-043/F-142", "spin boxes keep Qt's 14 px step column at the right edge, and clicks in it step the value as Qt's do", async () => {
      await this.fresh();
      await this.importRealistic();
      await this.page.click('[data-widget="tab1ChkBox"]');
      await H.waitIdle(this.page);
      const spin  = await this.page.locator('[data-widget="tab1SpinBox"]').boundingBox();
      const value = async () => (await H.snapshot(this.page)).controls.tab1SpinBox.value;
      const steps = [];
      for (const [dx, dy] of FinalWidgetsChecks.ORIGINAL.spinClicks.map((c) => c.slice(0, 2))) {
        const before = await value();
        await this.page.mouse.click(spin.x + spin.width - dx, spin.y + dy);
        await H.waitIdle(this.page);
        await this.page.waitForTimeout(120);
        steps.push((await value()) - before);
        await this.page.mouse.click(600, 872);
        await H.waitIdle(this.page);
      }
      const columns = { slice: await this.spinColumns('[data-widget="tab1SpinBox"]') };
      await this.openNormalization();
      columns.normalization = await this.spinColumns(`${FinalWidgetsChecks.TOP_PANE} .tv-pg-normgroup .tv-spin`);
      await this.openAxisMenu();
      columns.axis = await this.spinColumns(".tv-menu .tv-pg-axisctrl .tv-spin");
      await this.closeMenus();
      await this.openExport();
      await this.pickFormat("Image File");
      columns.export = await this.spinColumns(".tv-pg-export__params .tv-spin");
      await this.closeExport();
      await this.setRoi();
      await this.page.click('[data-widget="tab1PlotButton"]');
      await H.waitIdle(this.page);
      columns.plot = await this.spinColumns('[data-widget="tab2SpinBox"]');
      await this.page.click('.tv-tab[data-tab="0"]');
      R.equal(steps, FinalWidgetsChecks.ORIGINAL.spinClicks.map((c) => c[2]), "value steps for clicks 12, 5, 12 (lower), 14 and 20 px from the right edge");
      const seen = [];
      for (const [where, list] of Object.entries(columns)) {
        R.assert(list.length > 0, `${where}: no spin box found`);
        for (const spin of list) {
          const qt = FinalWidgetsChecks.qtColumn(spin);
          R.equal([spin.up, spin.down], [qt.up, qt.down], `${where} spin box ${spin.w}x${spin.h} step column`);
        }
        seen.push(`${where} ${list.map((s) => `${s.w}x${s.h}`).join(",")}`);
      }
      return `steps ${steps.join(" ")}; ${seen.join("; ")}`;
    });
  }

  async sliceRow() {
    await this.run.check("LS-14 F-030", "the slice row has Qt's check box, slider, spin box, Play button and combo geometry before and after data", async () => {
      await this.fresh();
      const row = async () => ({
        chk    : await this.windowRect('[data-widget="tab1ChkBox"]'),
        slider : await this.windowRect('[data-widget="tab1Slider"]'),
        spin   : await this.windowRect('[data-widget="tab1SpinBox"]'),
        play   : await this.windowRect('[data-widget="tab1PlayButton"]'),
        combo  : await this.windowRect('[data-widget="tab1ComboBox"]'),
      });
      const before = await row();
      await this.importRealistic();
      await this.page.click('[data-widget="tab1ChkBox"]');
      await H.waitIdle(this.page);
      const after = await row();
      const parts = await this.T(() => {
        const spin = document.querySelector('[data-widget="tab1SpinBox"]');
        const r    = spin.getBoundingClientRect();
        const rel  = (e) => { const q = e.getBoundingClientRect(); return [q.left - r.left, q.top - r.top, q.width, q.height]; };
        const s    = document.querySelector('[data-widget="tab1Slider"]');
        return { up: rel(spin.querySelector(".tv-spin__up")), down: rel(spin.querySelector(".tv-spin__down")), edit: rel(spin.querySelector(".tv-spin__input")), handle: s.querySelector(".tv-slider__handle").getBoundingClientRect().left - s.getBoundingClientRect().left };
      });
      await H.shot(this.page, "ls14_slice_row", "final-widgets", { element: ".tv-slicer__slices" });
      const b = FinalWidgetsChecks.ORIGINAL.row1Before;
      const a = FinalWidgetsChecks.ORIGINAL.row1After;
      R.equal([before.chk, before.slider, before.spin, before.play, before.combo], [b.chk, b.slider, b.spin, b.play, b.combo], "before data");
      R.equal([after.chk, after.slider, after.spin, after.play, after.combo], [a.chk, a.slider, a.spin, a.play, a.combo], "after data");
      R.equal([parts.up, parts.down, parts.edit, parts.handle], [a.up, a.down, a.edit, a.handle], "spin parts and slider handle at value 100");
      return `spin ${before.spin[2]} -> ${after.spin[2]} px, combo at ${after.combo[0]}, handle at ${parts.handle}`;
    });
  }

  async roiRow() {
    await this.run.check("LS-10/LS-09 F-030", "ROI fields grow to Qt's 90 px maximum on wider windows and their text shares the label baseline", async () => {
      const seen = [];
      for (const [viewport, key] of [[[1100, 880], 1100], [[1440, 900], 1404]]) {
        await this.fresh(viewport[0], viewport[1]);
        await this.importRealistic();
        const got = [];
        for (const name of ["tab1QLineEdit1", "tab1QLineEdit2", "tab1QLineEdit3", "tab1QLineEdit4", "tab1QLineEdit5", "tab1QLineEdit6", "tab1SetButton", "tab1PlotButton"]) {
          const r = await this.windowRect(`[data-widget="${name}"]`);
          got.push([r[0], r[2]]);
        }
        R.equal(got, FinalWidgetsChecks.ORIGINAL.fields[key], `${key} wide window: field and button x and width`);
        seen.push(`${key}: fields ${got[0][1]} px, Plot at ${got[7][0]}`);
      }
      await this.fresh();
      await this.importRealistic();
      const file  = path.join(this.out, "ls09_roi_row.png");
      const label = await this.page.locator(".tv-slicer__roi .tv-slicer__label", { hasText: /^Ax$/ }).boundingBox();
      const field = await this.page.locator('[data-widget="tab1QLineEdit1"]').boundingBox();
      await this.page.screenshot({ path: file });
      const code = [
        "import json, sys",
        "import numpy as np",
        "from PIL import Image",
        "a = np.asarray(Image.open(sys.argv[1]).convert('L')).astype(int)",
        "box = json.loads(sys.argv[2])",
        "def bottom(x0, x1, y0, y1):",
        "    rows = np.nonzero((a[y0:y1, x0:x1] > 90).any(1))[0]",
        "    return int(rows.max() + y0)",
        "print(json.dumps([bottom(*box['label']), bottom(*box['field'])]))",
      ].join("\n");
      const boxes = { label: [Math.round(label.x), Math.round(label.x + label.width), Math.round(label.y - 6), Math.round(label.y + label.height + 6)], field: [Math.round(field.x + 6), Math.round(field.x + field.width - 6), Math.round(field.y + 4), Math.round(field.y + field.height - 4)] };
      const [labelBase, fieldBase] = JSON.parse(H.python(code, file, JSON.stringify(boxes)));
      R.equal(labelBase, fieldBase, "label and field text baselines");
      seen.push(`baselines ${labelBase}/${fieldBase}`);
      return seen.join("; ");
    });
  }

  async comboPopup() {
    await this.run.check("LS-11 F-047", "the Colormap combo has Qt's size and font size, and its 10-row popup has Qt's size and a classic 14 px scrollbar", async () => {
      const browser = await chromium.launch({ executablePath: new ChromiumResolver().resolve(), args: H.GL_ARGS[this.options.gl], headless: true, ignoreDefaultArgs: ["--hide-scrollbars"] });
      const page    = await (await browser.newContext({ viewport: { width: 1100, height: 880 }, deviceScaleFactor: 1 })).newPage();
      await H.openTomoVis(page, this.options.base);
      await H.menu(page, "File", "Import", "hd5");
      await H.chooseFile(page, FinalWidgetsChecks.REALISTIC);
      await page.waitForTimeout(500);
      const combo = await page.evaluate(() => { const e = document.querySelector('[data-widget="tab1ComboBox"]'); const r = e.getBoundingClientRect(); return { size: [r.width, r.height], font: getComputedStyle(e).fontSize }; });
      await page.click('[data-widget="tab1ComboBox"]');
      await page.waitForTimeout(300);
      const popup = await page.evaluate(() => {
        const l    = document.querySelector(".tv-combo__popup");
        const b    = l.getBoundingClientRect();
        const rows = [...l.querySelectorAll(".tv-combo__option")];
        const vis  = rows.filter((row) => { const q = row.getBoundingClientRect(); return q.top >= b.top - 0.5 && q.bottom <= b.bottom + 0.5; });
        const cs   = getComputedStyle(l);
        return { size: [b.width, b.height], row: rows[0].getBoundingClientRect().height, visible: vis.length, hotLast: vis.at(-1).classList.contains("is-hot"), scrollbar: l.offsetWidth - l.clientWidth - parseFloat(cs.borderLeftWidth) - parseFloat(cs.borderRightWidth), font: getComputedStyle(rows[0]).fontSize };
      });
      await page.screenshot({ path: path.join(this.out, "ls11_combo_popup.png") });
      await browser.close();
      const o = FinalWidgetsChecks.ORIGINAL.comboPopup;
      R.equal(combo, { size: [187, 32], font: o.font }, "combo");
      R.equal([popup.size, popup.row, popup.visible, popup.hotLast, popup.scrollbar, popup.font], [o.size, o.row, o.visible, true, o.scrollbar, o.font], "popup");
      return `combo ${combo.size.join("x")} ${combo.font}, popup ${popup.size.join("x")}, rows ${popup.row} px, scrollbar ${popup.scrollbar} px`;
    });
  }

  async validator() {
    await this.run.check("FG-05 F-067/F-142", "spin boxes accept, hold or refuse typed text by QSpinBox and QDoubleSpinBox's rules, and X [m] treats '.5' and '-5' as Qt does", async () => {
      await this.fresh();
      const diffs = await this.T((specs) => {
        const kit = window.app.tomovisPage.ctx.kit;
        const out = [];
        for (const spec of specs) {
          const view = kit.local(spec.kind === "double" ? "doubleSpin" : "spin", { decimals: spec.decimals, suffix: spec.suffix });
          view.set({ decimals: spec.decimals, minimum: spec.min, maximum: spec.max, value: spec.min });
          for (const [text, expect] of Object.entries(spec.expect)) {
            const [state, , fixed] = view.validate(text, text.length);
            const got = state === "Invalid" ? "X" : `${state === "Acceptable" ? "A" : "I"}:${fixed}`;
            if (got !== expect) out.push(`${spec.kind} ${spec.min}..${spec.max} ${JSON.stringify(text)}: ${got} (Qt ${expect})`);
          }
        }
        return out;
      }, FinalWidgetsChecks.ORIGINAL.validator);
      R.equal(diffs, [], "validator states that differ from Qt");
      await this.importRealistic();
      await this.setRoi();
      await this.page.click('[data-widget="tab1PlotButton"]');
      await H.waitIdle(this.page);
      await this.page.click('[data-widget="tab2ChkBox3"]');
      await H.waitIdle(this.page);
      const input = '[data-widget="tab2SpinBox"] input';
      const typeIn = async (text) => {
        await this.page.click(input);
        await this.page.keyboard.press("Control+A");
        await this.page.keyboard.type(text);
        await H.waitIdle(this.page);
        const typed = await this.page.inputValue(input);
        await this.page.keyboard.press("Enter");
        await H.waitIdle(this.page);
        return [typed, await this.page.inputValue(input), (await H.snapshot(this.page)).controls.tab2SpinBox.value];
      };
      const dot5 = await typeIn(".5");
      await typeIn("40");
      const minus5 = await typeIn("-5");
      await this.page.click('.tv-tab[data-tab="0"]');
      const o = FinalWidgetsChecks.ORIGINAL.xSpin;
      R.equal([dot5[1], dot5[2]], o.dot5, "'.5' then Enter");
      R.equal(minus5, o.minus5, "'-5' typed after 40 then Enter");
      return `${FinalWidgetsChecks.ORIGINAL.validator.length} ranges agree; '.5' -> ${dot5[1]}; '-5' shows '${minus5[0]}' and Enter restores ${minus5[1]}`;
    });
  }

  async lineEditScroll() {
    await this.run.check("LF-07 F-069/F-134", "a text field set to a long text shows its end, where the cursor is, as Qt's line edit does; float fields keep their start", async () => {
      await this.fresh();
      await this.importRealistic();
      await this.setRoi();
      await this.page.click('[data-widget="tab1PlotButton"]');
      await H.waitIdle(this.page);
      await this.page.click('[data-widget="tab2AxesButton"]');
      await this.page.waitForSelector(".tv-axes-dialog");
      await this.page.waitForTimeout(300);
      const axes = await this.T(() => { const i = document.querySelector('.tv-axes-dialog [data-field="x_label"]'); return [i.value, i.scrollLeft, i.scrollWidth - i.clientWidth, i.selectionEnd]; });
      await this.page.keyboard.press("Escape");
      await this.page.waitForSelector(".tv-axes-dialog", { state: "detached" });
      await this.page.click('#tv-panel-plot .tv-mpl-tool[data-method="edit_parameters"]');
      await this.page.waitForSelector(".tv-mpl-chooser");
      await this.page.click('.tv-mpl-chooser .tv-button:text-is("OK")');
      await this.page.waitForSelector(".tv-mpl-options");
      await this.page.waitForTimeout(400);
      const options = await this.T(() => [...document.querySelectorAll(".tv-mpl-options .tv-mpl-page:not([hidden]) .tv-mpl-form input.tv-line")].map((i) => [i.value, i.scrollLeft, i.scrollWidth - i.clientWidth]));
      await this.page.keyboard.press("Escape");
      await this.page.click('.tv-tab[data-tab="0"]');
      const label = options.find((o) => o[0].includes("distance"));
      const float = options.find((o) => /^-?\d/.test(o[0]) && o[2] > 0);
      R.assert(axes[2] > 0 && axes[1] === axes[2] && axes[3] === axes[0].length, `Axes dialog X label scroll ${JSON.stringify(axes)}`);
      R.assert(label && label[2] > 0 && label[1] === label[2], `Figure options label scroll ${JSON.stringify(label)}`);
      R.assert(!float || float[1] === 0, `a long float field keeps its start ${JSON.stringify(float)}`);
      return `Axes X label scrolled ${axes[1]} of ${axes[2]} px; options label ${label[1]} of ${label[2]} px`;
    });
  }

  async pressedButton() {
    await this.run.check("LS-06", "a held push button gets a darker, sunken fill and does not move, as Fusion's", async () => {
      await this.fresh();
      await this.importRealistic();
      const set = await this.page.locator('[data-widget="tab1SetButton"]').boundingBox();
      await this.page.mouse.move(set.x + 40, set.y + 14);
      await this.page.waitForTimeout(250);
      const style = () => this.T(() => { const s = getComputedStyle(document.querySelector('[data-widget="tab1SetButton"]')); return [s.backgroundColor, s.transform]; });
      const hover = await style();
      await this.page.mouse.down();
      await this.page.waitForTimeout(250);
      const down = await style();
      await H.shot(this.page, "ls06_set_down", "final-widgets", { element: '[data-widget="tab1SetButton"]' });
      await this.page.mouse.up();
      const well = await this.T(() => { const probe = document.createElement("span"); probe.style.background = "var(--tv-well)"; document.querySelector("#tv-window").append(probe); const c = getComputedStyle(probe).backgroundColor; probe.remove(); return c; });
      R.equal(down, [well, "none"], "fill and transform while held");
      R.assert(down[0] !== hover[0], "held fill differs from the hover fill");
      return `hover ${hover[0]}, held ${down[0]}`;
    });
  }

  async menuChecks() {
    await this.run.check("LS-07 F-115/F-118", "unchecked checkable menu actions draw an empty box, checked ones a ticked box, exclusive ones only a dot", async () => {
      await this.fresh();
      await this.importRealistic();
      await this.page.click(`${FinalWidgetsChecks.TOP_PANE} .tv-pg-btn >> nth=1`);
      await this.page.waitForTimeout(250);
      const marks = () => this.T(() => [...document.querySelectorAll(".tv-menu")].at(-1).querySelectorAll(".tv-menu__item").length && [...[...document.querySelectorAll(".tv-menu")].at(-1).querySelectorAll(".tv-menu__item")].map((row) => {
        const m = row.querySelector(".tv-menu__mark");
        const s = m ? getComputedStyle(m) : null;
        return [row.textContent.trim(), m ? m.classList.contains("is-check") : false, m ? m.classList.contains("is-on") : false, s ? s.borderTopWidth : null, s ? s.width : null];
      }));
      const iv = await marks();
      await H.shot(this.page, "ls07_imageview_menu", "final-widgets", { element: ".tv-menu" });
      await this.closeMenus();
      const hist = await this.page.locator(`${FinalWidgetsChecks.TOP_PANE} .tv-pg-hist canvas`).boundingBox();
      await this.page.mouse.click(hist.x + 136, hist.y + 150, { button: "right" });
      await this.page.waitForTimeout(300);
      const grad = await marks();
      await H.shot(this.page, "ls07_gradient_menu", "final-widgets", { element: ".tv-menu" });
      await this.closeMenus();
      const find = (rows, text) => rows.find((r) => r[0] === text);
      R.equal(find(iv, "Normalization"), ["Normalization", true, false, "2px", "14px"], "Normalization unchecked");
      R.equal(find(grad, "RGB"), ["RGB", true, true, "2px", "14px"], "RGB checked");
      R.equal(find(grad, "HSV"), ["HSV", true, false, "2px", "14px"], "HSV unchecked");
      R.equal(find(iv, "Export")[1], false, "Export is not checkable");
      return "Normalization and HSV show an empty 14 px box, RGB a ticked box";
    });
  }

  async presetSwatches() {
    await this.run.check("LS-12 F-115", "preset gradient rows are 26 px with a 32x24 swatch and the name at Qt's offset, in a 116x338 submenu", async () => {
      await this.fresh();
      await this.importRealistic();
      const hist = await this.page.locator(`${FinalWidgetsChecks.TOP_PANE} .tv-pg-hist canvas`).boundingBox();
      await this.page.mouse.click(hist.x + 136, hist.y + 150, { button: "right" });
      await this.page.waitForTimeout(300);
      await this.page.locator(".tv-menu .tv-menu__item", { hasText: "preset gradient" }).hover();
      await this.page.waitForTimeout(450);
      const sub = await this.T(() => {
        const m = [...document.querySelectorAll(".tv-menu")].at(-1);
        const b = m.getBoundingClientRect();
        return { size: [b.width, b.height], rows: [...m.querySelectorAll(".tv-menu__item")].map((row) => { const r = row.getBoundingClientRect(); const s = row.querySelector(".tv-pg-swatch").getBoundingClientRect(); const t = row.querySelector(".tv-pg-cmapentry__text").getBoundingClientRect(); return { name: row.textContent, row: [r.width, r.height], swatch: [s.left - r.left, s.top - r.top, s.width, s.height], text: t.left - r.left }; }) };
      });
      await H.shot(this.page, "ls12_preset_submenu", "final-widgets", { element: ".tv-menu >> nth=-1" });
      await this.closeMenus();
      const o = FinalWidgetsChecks.ORIGINAL.preset;
      R.equal(sub.size, o.size, "submenu size");
      R.equal(sub.rows.map((r) => r.name), ["thermal", "flame", "yellowy", "bipolar", "spectrum", "cyclic", "greyclip", "grey", "viridis", "inferno", "plasma", "magma", "turbo"], "names");
      for (const r of sub.rows) R.equal([r.row, r.swatch, r.text], [o.row, o.swatch, o.text], `${r.name} row`);
      return `submenu ${sub.size.join("x")}, rows ${o.row.join("x")}, swatch ${o.swatch.slice(2).join("x")}`;
    });
  }

  async axisMenu() {
    await this.run.check("SL-04 F-111", "the X axis submenu is Qt's 200x217 form, its percent box shows 100% with the suffix inside, and long labels are clipped", async () => {
      await this.fresh();
      await this.importRealistic();
      await this.openAxisMenu();
      const form = await this.T(() => {
        const root = [...document.querySelectorAll(".tv-pg-axisctrl")].at(-1);
        const b    = root.getBoundingClientRect();
        const rel  = (e) => { const r = e.getBoundingClientRect(); return [r.left - b.left, r.top - b.top, r.width, r.height]; };
        const kids = [...root.children].filter((e) => !e.classList.contains("tv-label"));
        const vis  = [...root.querySelectorAll(".tv-check")].find((e) => e.textContent === "Visible Data Only");
        return { size: [b.width, b.height], children: kids.map(rel), percent: root.querySelector(".tv-spin input").value, labels: [...root.querySelectorAll(".tv-label")].map((e) => e.textContent), clipped: vis.scrollWidth > vis.clientWidth, menu: [...document.querySelectorAll(".tv-menu")].at(-1).getBoundingClientRect().width };
      });
      await H.shot(this.page, "sl04_x_axis_submenu", "final-widgets", { element: ".tv-menu >> nth=-1" });
      await this.closeMenus();
      const o = FinalWidgetsChecks.ORIGINAL.axisMenu;
      R.equal([form.size, form.menu], [o.size, o.size[0]], "form and submenu width");
      R.equal(form.children, o.children, "control geometry");
      R.equal([form.percent, form.labels], [o.percent, ["Link Axis:"]], "percent text and labels");
      R.assert(form.clipped, "'Visible Data Only' is clipped by its 115 px cell");
      return `form ${form.size.join("x")}, percent '${form.percent}'`;
    });
  }

  async normalization() {
    await this.run.check("LS-04 F-119", "the Normalization group spreads seven equal Qt grid columns with full-width blur spin boxes and right-aligned X, Y, T", async () => {
      await this.fresh();
      await this.importRealistic();
      await this.openNormalization();
      const pane = FinalWidgetsChecks.TOP_PANE;
      const got  = await this.T((pane) => {
        const win  = document.querySelector("#tv-window").getBoundingClientRect();
        const rect = (e) => { const r = e.getBoundingClientRect(); return [r.left - win.left, r.top - win.top, r.width, r.height]; };
        const g    = document.querySelector(`${pane} .tv-pg-normgroup`);
        return {
          group  : rect(g),
          radios : [...g.querySelectorAll(".tv-radio")].map((e) => rect(e)[0]),
          spins  : [...g.querySelectorAll(".tv-spin")].map(rect),
          rights : [...g.querySelectorAll(".tv-pg-normgroup__right")].map((e) => e.getBoundingClientRect().right - win.left),
        };
      }, pane);
      const column = (await this.spinColumns(`${pane} .tv-pg-normgroup .tv-spin`))[0];
      await H.shot(this.page, "ls04_normalization", "final-widgets", { element: `${pane} .tv-pg-normgroup` });
      const o = FinalWidgetsChecks.ORIGINAL.norm;
      R.equal([got.group, got.radios, got.spins, got.rights, column.up], [o.group, o.radios, o.spins, o.rightEdges, o.up], "group, radio, spin box and label geometry");
      return `radios at ${got.radios.join("/")}, spin boxes ${got.spins.map((s) => s[0]).join("/")} (${got.spins[0][2]}x${got.spins[0][3]})`;
    });
  }

  async axisMetrics() {
    await this.run.check("LS-05/LS-13/SL-03 F-114/F-117", "axis labels use Qt's 17 px text metrics: the short histogram labels 0, 2, 4, Qt's fractional axis widths and the ROI plot ViewBox at x 39.70", async () => {
      await this.fresh();
      await this.importRealistic();
      const strip = await this.T(() => {
        const h = window.app.tomovisPage.views[0].views.imv1_1.histogram;
        return { axis: [h.axis.rect.x, h.axis.rect.y, h.axis.rect.w], vb: h.vb.rect.x, grad: h.gradient.rect.x };
      });
      const file = path.join(this.out, "ls13_hist_strip.png");
      await this.page.screenshot({ path: file });
      const code = [
        "import json, sys",
        "import numpy as np",
        "from PIL import Image",
        "a = np.asarray(Image.open(sys.argv[1]).convert('RGB')).astype(int)",
        "row = a[200]",
        "line = [x for x in range(925, 945) if row[x].min() > 120]",
        "bar = [int(v) for v in row[1063]]",
        "print(json.dumps({'line': line, 'bar1063': bar, 'bar1062': [int(v) for v in row[1062]]}))",
      ].join("\n");
      const px = JSON.parse(H.python(code, file));
      await this.setRoi();
      await this.page.locator(`${FinalWidgetsChecks.TOP_PANE} .tv-pg-btn`).nth(0).click();
      await H.waitIdle(this.page);
      await this.page.waitForTimeout(600);
      const roi = await this.T(() => {
        const iv    = window.app.tomovisPage.views[0].views.imv1_1;
        const specs = iv.histogram.axis.drawSpecs(document.createElement("canvas").getContext("2d"));
        return { labels: specs.textSpecs.map((t) => t.text), height: iv.histogram.view.height, vb: { ...iv.roiPlot.vb.rect } };
      });
      await this.page.locator(`${FinalWidgetsChecks.TOP_PANE} .tv-pg-btn`).nth(0).click();
      const o = FinalWidgetsChecks.ORIGINAL;
      R.equal([strip.axis, strip.vb, strip.grad], [o.histAxis.axis, o.histAxis.vb, o.histAxis.grad], "histogram axis, ViewBox and gradient positions");
      R.equal(px.line, [o.histAxis.line], "axis line column on row 200");
      R.assert(px.bar1063.every((v, i) => Math.abs(v - px.bar1062[i]) <= 4), `the gradient bar is solid up to x 1063: ${JSON.stringify([px.bar1062, px.bar1063])}`);
      R.equal([roi.height, roi.labels], [187, o.histLabels], "labels on the 187 px strip with the ROI plot on");
      R.equal([roi.vb.x, roi.vb.w, roi.vb.h], [o.roiPlotVb.x, o.roiPlotVb.w, o.roiPlotVb.h], "ROI plot ViewBox");
      return `axis ${strip.axis[2]} px wide, line at ${px.line}, labels ${roi.labels.join(" ")}, ROI plot ViewBox x ${roi.vb.x}`;
    });
  }

  async exportSizes() {
    await this.run.check("SL-01/SL-02 F-113", "a ViewBox exports pyqtgraph's +0.5 px bounds: the SVG dialog shows 901 x 341, and the PNG keeps Qt's cell edges", async () => {
      await this.fresh();
      await this.importRealistic();
      const state = () => this.T(() => {
        const d = document.querySelector(".tv-pg-export");
        return { shown: [...d.querySelectorAll(".tv-pg-export__params input")].map((i) => i.value) };
      });
      await this.openExport("imv2_1", 40, 70);
      await this.pickFormat("Scalable Vector Graphics");
      const svgParams = await this.T(() => { const v = window.app.tomovisPage.views[0].views.imv2_1.scene.exportDialog; return v.exporter.params.filter((p) => p.name === "width" || p.name === "height").map((p) => p.value); });
      const svg = await state();
      await this.closeExport();
      await this.page.locator(`${FinalWidgetsChecks.TOP_PANE} .tv-pg-btn`).nth(0).click();
      await H.waitIdle(this.page);
      await this.page.waitForTimeout(500);
      await this.openExport("imv2_1", 40, 70);
      await this.pickFormat("Image File");
      const image = await state();
      const file = path.join(this.out, "sl02_viewbox.png");
      fs.rmSync(file, { force: true });
      await this.page.locator(".tv-pg-export__buttons .tv-button", { hasText: "Export" }).click();
      await H.chooseFile(this.page, file);
      await this.page.waitForTimeout(500);
      await this.closeExport();
      const code = [
        "import json, sys",
        "import numpy as np",
        "from PIL import Image",
        "a = np.asarray(Image.open(sys.argv[1]).convert('RGB')).astype(int)",
        "def edges(line):",
        "    d = np.abs(np.diff(line, axis=0)).sum(axis=1)",
        "    return [int(i + 1) for i in np.nonzero(d > 0)[0]]",
        "print(json.dumps({'size': list(a.shape), 'row150': edges(a[150])[:24], 'col450': edges(a[:, 450])[:16]}))",
      ].join("\n");
      const png = JSON.parse(H.python(code, file));
      const o   = FinalWidgetsChecks.ORIGINAL;
      R.equal([svgParams, svg.shown.slice(0, 2)], [o.svg.params, o.svg.shown], "SVG width and height");
      R.equal(image.shown.slice(0, 2), ["900", "313"], "Image File width and height");
      R.equal([png.size, png.row150, png.col450], [[313, 900, 3], o.exportVb.row150, o.exportVb.col450], "exported cell edges");
      return `SVG ${svg.shown.slice(0, 2).join("x")}, PNG ${png.size[1]}x${png.size[0]} with Qt's ${png.row150.length} row edges`;
    });
  }

  async exportDialog() {
    await this.run.check("LS-08 F-113", "the Export dialog has Qt's 262x367 client, an expand arrow on Entire Scene, a bold params row and Qt's scrolling lists", async () => {
      const browser = await chromium.launch({ executablePath: new ChromiumResolver().resolve(), args: H.GL_ARGS[this.options.gl], headless: true, ignoreDefaultArgs: ["--hide-scrollbars"] });
      const page    = await (await browser.newContext({ viewport: { width: 1100, height: 880 }, deviceScaleFactor: 1 })).newPage();
      const saved   = this.page;
      this.page     = page;
      await H.openTomoVis(page, this.options.base);
      await this.importRealistic();
      await this.openExport();
      const read = () => this.T(() => {
        const d    = document.querySelector(".tv-pg-export");
        const body = d.querySelector(".tv-modal__body");
        const b    = body.getBoundingClientRect();
        const rel  = (e) => { const r = e.getBoundingClientRect(); return [r.left - b.left, r.top - b.top, r.width, r.height]; };
        const list = d.querySelector(".tv-pg-export__formats");
        const pt   = d.querySelector(".tv-pg-export__params");
        const fullRows = [...list.querySelectorAll(".tv-pg-export__row")].filter((r) => r.getBoundingClientRect().bottom <= list.getBoundingClientRect().top + 2 + list.clientHeight + 0.5).length;
        return {
          body     : [b.width, b.height],
          children : [...body.children].map(rel),
          rows     : [...d.querySelectorAll(".tv-pg-export__tree .tv-pg-export__row")].map((r) => [r.textContent, r.getBoundingClientRect().height, r.hidden]),
          arrow    : d.querySelector(".tv-pg-export__branch").dataset.kids === "true",
          format   : [list.querySelector(".tv-pg-export__row").getBoundingClientRect().height, list.scrollWidth, list.scrollWidth > list.clientWidth, list.scrollHeight > list.clientHeight, fullRows],
          group    : [pt.querySelector(".tv-pg-export__group").textContent, pt.querySelector(".tv-pg-export__group").getBoundingClientRect().height, getComputedStyle(pt.querySelector(".tv-pg-export__group")).fontWeight],
          params   : [...pt.querySelectorAll(".tv-pg-export__param")].map((r) => r.getBoundingClientRect().height),
          paramsScroll : [pt.scrollWidth > pt.clientWidth, pt.scrollHeight > pt.clientHeight],
          buttons  : [...d.querySelectorAll(".tv-pg-export__buttons .tv-button")].map((e) => [rel(e)[0], rel(e)[2]]),
        };
      });
      const csv = await read();
      await page.screenshot({ path: path.join(this.out, "ls08_export_dialog.png"), clip: await page.locator(".tv-pg-export").boundingBox() });
      await page.locator(".tv-pg-export__tree .tv-pg-export__branch").first().click();
      const collapsed = await read();
      await page.locator(".tv-pg-export__tree .tv-pg-export__branch").first().click();
      await this.pickFormat("Image File");
      const image = await read();
      await page.screenshot({ path: path.join(this.out, "ls08_export_dialog_image.png"), clip: await page.locator(".tv-pg-export").boundingBox() });
      await this.closeExport();
      this.page = saved;
      await browser.close();
      const o = FinalWidgetsChecks.ORIGINAL.exportDlg;
      R.equal([csv.body, csv.children], [o.body, o.children], "client size and layout");
      R.equal([csv.arrow, csv.rows.map((r) => r[1])], [true, [o.rowHeight, o.rowHeight]], "tree arrow and rows");
      R.equal(collapsed.rows.map((r) => r[2]), [false, true], "the arrow collapses ViewBox");
      R.equal([csv.format[0], csv.format[1], csv.format[2], csv.format[3], csv.format[4]], [o.rowHeight, o.formatWidth, true, true, 2], "format list rows, width and scroll bars");
      R.equal([image.group[0], image.group[1], image.group[2]], [o.group, o.groupHeight, "700"], "params group row");
      R.assert(image.params.every((h) => h === o.paramHeight), `parameter rows ${JSON.stringify(image.params)}`);
      R.equal(image.paramsScroll, [true, true], "parameter tree scrolls both ways");
      R.equal(csv.buttons, o.buttons, "buttons");
      return `client ${csv.body.join("x")}, format list ${csv.format[1]} px wide, ${image.params.length} parameter rows`;
    });
  }

  async main() {
    const opened = await H.launch({ port: this.options.port, gl: this.options.gl, viewport: { width: 1100, height: 880 } });
    this.options.base = opened.base;
    this.page = opened.page;
    await H.openTomoVis(this.page);

    if (this.wanted("spin")) await this.spinButtons();
    if (this.wanted("row1")) await this.sliceRow();
    if (this.wanted("row2")) await this.roiRow();
    if (this.wanted("combo")) await this.comboPopup();
    if (this.wanted("validator")) await this.validator();
    if (this.wanted("lineedit")) await this.lineEditScroll();
    if (this.wanted("pressed")) await this.pressedButton();
    if (this.wanted("menus")) await this.menuChecks();
    if (this.wanted("preset")) await this.presetSwatches();
    if (this.wanted("axismenu")) await this.axisMenu();
    if (this.wanted("norm")) await this.normalization();
    if (this.wanted("axes")) await this.axisMetrics();
    if (this.wanted("export")) await this.exportSizes();
    if (this.wanted("dialog")) await this.exportDialog();

    await opened.browser.close();
    const ok = this.run.summary(opened.errors);
    fs.writeFileSync(path.join(this.out, "final_widgets_checks.json"), JSON.stringify({ results: this.run.results, errors: opened.errors }, null, 2));
    process.exit(ok ? 0 : 1);
  }

  wanted(name) {
    return this.options.only.length === 0 || this.options.only.includes(name);
  }
}

await new FinalWidgetsChecks(H.args(process.argv, "final-widgets")).main();
