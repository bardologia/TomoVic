import fs from "node:fs";
import path from "node:path";
import { createRequire } from "node:module";
import { TomoVisHarness as H, TomoVisCheckRun as R } from "./harness.mjs";

const require              = createRequire(import.meta.url);
const { chromium }         = require("playwright-core");
const { ChromiumResolver } = require("../chromium.js");

class Fixer2Checks {
  static ORIGINAL = {
    startupRgb : [[-1.3235294117647058, 1.3235294117647058], [-0.5, 0.5]],
    importTop  : [[-75.33801160219518, 125.3380116021952], [-5.905471049718186, 69.90547104971819]],
    linkX      : {
      imv2_1 : [[-23.47338131807989, 23.47338131807989], [-0.8677218312746247, 16.867721831274626]],
      imv2_2 : [[-23.47338131807989, 23.47338131807989], [-8.867721831274626, 8.867721831274626]],
    },
    outside    : {
      imv1_1 : [[-1011.2235029909192, 2056.8628312836727], [-56.7077545499348, 1102.3470828426887]],
      imv2_1 : [[-23.47338131807989, 23.47338131807989], [-8.867721831274626, 8.867721831274626]],
    },
    enterOnSet : ["10", "5", "90", "30", "0", "0"],
    spaceOnSet : ["10.0000", "5.0000", "90.0000", "30.0000", "0.0000", "0.0000"],
    panes      : { start: [340, 340], roi: [367, 313], split: [219, 146] },
    canvases   : { pane: [900, 340], plot: [1042, 649], profile: [1042, 660] },
  };

  constructor(options) {
    this.options = options;
    this.run     = new R("fixer-2");
    this.inputs  = H.fixture("inputs");
    this.out     = H.shotDir("fixer-2");
    this.input   = path.join(this.inputs, "fusar_two_key_elev.hd5");
  }

  T(fn, arg) {
    return this.page.evaluate(fn, arg);
  }

  async fresh(width = 1100, height = 880) {
    await this.page.setViewportSize({ width, height });
    await this.page.goto("about:blank");
    await H.openTomoVis(this.page);
  }

  async importInput() {
    await H.menu(this.page, "File", "Import", "hd5");
    await H.chooseFile(this.page, this.input);
    await this.page.waitForSelector(".tv-filedialog", { state: "detached" });
    await H.waitIdle(this.page);
    await this.page.waitForTimeout(600);
  }

  async fields() {
    return this.T(() => [1, 2, 3, 4, 5, 6].map((i) => document.querySelector(`[data-widget="tab1QLineEdit${i}"]`).value));
  }

  async typeRoi(values) {
    for (let i = 0; i < 6; i += 1) await this.page.fill(`[data-widget="tab1QLineEdit${i + 1}"]`, values[i]);
    await H.waitIdle(this.page);
  }

  async ranges() {
    return this.T(() => {
      const views = window.app.tomovisPage.views[0].views;
      const out   = {};
      for (const name of ["imv1_1", "imv1_2", "imv2_1", "imv2_2"]) out[name] = views[name].view.viewRange();
      return out;
    });
  }

  static close(actual, expected) {
    return actual.every((range, i) => range.every((v, j) => Math.abs(v - expected[i][j]) <= 1e-6 * Math.max(1, Math.abs(expected[i][j]))));
  }

  async enterOnButtons() {
    await this.run.check("FG-01 F-035/F-049", "Enter on a focused Set or Slicer Plot button does nothing, Space clicks it, as for Qt's non-autoDefault main-window buttons", async () => {
      await this.fresh();
      await this.importInput();
      await this.typeRoi(["10", "5", "90", "30", "0", "0"]);
      await this.page.focus('[data-widget="tab1SetButton"]');
      await this.page.keyboard.press("Enter");
      await H.waitIdle(this.page);
      const afterEnter = await this.fields();
      await this.page.focus('[data-widget="tab1PlotButton"]');
      await this.page.keyboard.press("Enter");
      await H.waitIdle(this.page);
      const tabEnter = (await H.snapshot(this.page)).controls.tabWidget.index;
      const roiBtn   = this.page.locator('.tv-slicer__stack[data-stack="imv1"] .tv-slicer__pane.is-current .tv-pg-btn').nth(0);
      await roiBtn.focus();
      await this.page.keyboard.press("Enter");
      const roiEnter = await roiBtn.getAttribute("aria-pressed");
      await this.page.focus('[data-widget="tab1SetButton"]');
      await this.page.keyboard.press("Space");
      await H.waitIdle(this.page);
      const afterSpace = await this.fields();
      await this.page.focus('[data-widget="tab1PlotButton"]');
      await this.page.keyboard.press("Space");
      await H.waitIdle(this.page);
      const tabSpace = (await H.snapshot(this.page)).controls.tabWidget.index;
      R.equal(afterEnter, Fixer2Checks.ORIGINAL.enterOnSet, "fields after Enter on Set");
      R.equal(tabEnter, 0, "tab after Enter on Plot");
      R.equal(roiEnter, "false", "ROI button after Enter");
      R.equal(afterSpace, Fixer2Checks.ORIGINAL.spaceOnSet, "fields after Space on Set");
      R.equal(tabSpace, 1, "tab after Space on Plot");
      return `Enter: fields ${afterEnter.join(" ")}, tab ${tabEnter}; Space: fields ${afterSpace.join(" ")}, tab ${tabSpace}`;
    });
  }

  async navOverlap() {
    await this.run.check("FG-02 F-001", "TomoVic's nav bar never covers the menu bar or the tabs, and its hover edge stops at the window's outer frame", async () => {
      const seen = [];
      for (const [width, height] of [[900, 700], [800, 600]]) {
        await this.fresh(width, height);
        const hits = await this.T(() => {
          const own = (el) => {
            const r = el.getBoundingClientRect();
            const e = document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2);
            return Boolean(e && el.contains(e));
          };
          const items = [...document.querySelectorAll(".tv-menubar__item"), ...document.querySelectorAll("#tv-tabs .tv-tab")];
          return { own: items.map(own), top: document.querySelector("#tv-window").getBoundingClientRect().top, nav: document.querySelector("#nav").getBoundingClientRect().bottom };
        });
        R.assert(hits.own.every(Boolean), `${width}x${height}: menu items and tabs under the pointer ${JSON.stringify(hits.own)}`);
        R.assert(hits.top >= hits.nav, `${width}x${height}: window top ${hits.top} below the nav bar ${hits.nav}`);
        await this.page.click('.tv-menubar__item[data-menu="file"]');
        R.assert(await this.T(() => Boolean(document.querySelector(".tv-menu"))), `${width}x${height}: File opens its menu`);
        await this.page.keyboard.press("Escape");
        seen.push(`${width}x${height} window top ${hits.top}`);
      }
      for (const width of [1100, 1112, 1124, 1440]) {
        await this.fresh(width, 900);
        const edge = await this.T(() => {
          const e = document.querySelector("#nav-edge").getBoundingClientRect();
          const w = document.querySelector("#tv-window").getBoundingClientRect();
          return { right: e.right, winLeft: w.left };
        });
        if (edge.winLeft === 0) R.equal(edge.right, 2, `${width}: 2 px edge when the window touches the left side`);
        else R.assert(edge.right <= edge.winLeft, `${width}: edge ends at ${edge.right}, window client starts at ${edge.winLeft}`);
        seen.push(`${width} edge ${edge.right} / window ${edge.winLeft}`);
      }
      return seen.join("; ");
    });
  }

  async wheelScroll() {
    await this.run.check("FG-03 F-140/F-001", "the wheel over a label or a matplotlib figure does not scroll the page, which has no footer while TomoVis is shown", async () => {
      await this.fresh();
      await this.importInput();
      const label = await this.page.locator(".tv-label", { hasText: "ROI (Manual):" }).first().boundingBox();
      await this.page.mouse.move(label.x + 5, label.y + 5);
      await this.page.mouse.wheel(0, 240);
      await this.page.waitForTimeout(300);
      const overLabel = await this.T(() => window.scrollY);
      await this.page.click('[data-widget="tab1PlotButton"]');
      await H.waitIdle(this.page);
      await this.page.waitForTimeout(400);
      const centre = await this.T(() => {
        const r = window.app.tomovisPage.views[1].figure.canvas.getBoundingClientRect();
        return { x: r.left + r.width / 2, y: r.top + r.height / 2 };
      });
      await this.page.mouse.move(centre.x, centre.y);
      await this.page.mouse.wheel(0, 240);
      await this.page.waitForTimeout(300);
      const overFigure = await this.T(() => window.scrollY);
      const page       = await this.T(() => ({ footer: getComputedStyle(document.querySelector(".footer")).display, height: document.documentElement.scrollHeight, inner: window.innerHeight }));
      await this.page.click('.tv-tab[data-tab="0"]');
      R.equal([overLabel, overFigure], [0, 0], "page scroll after the wheel");
      R.equal(page.footer, "none", "footer hidden");
      R.equal(page.height, page.inner, "document height");
      return `scrollY ${overLabel} over a label, ${overFigure} over the Plot figure; document ${page.height} px tall`;
    });
  }

  async paneGeometry() {
    await this.run.check("FG-04/FG-05 F-030/F-060/F-117", "at 1100x880 the panes, ROI plot split and figure canvases have Qt's measured sizes", async () => {
      await this.fresh();
      await this.importInput();
      const stacks = () => this.T(() => [...document.querySelectorAll(".tv-slicer__stack")].map((s) => s.getBoundingClientRect().height));
      const pane   = await this.T(() => { const r = document.querySelector('.tv-slicer__pane[data-view="imv1_1"] .tv-pg-gv').getBoundingClientRect(); return [r.width, r.height]; });
      const start  = await stacks();
      const roiBtn = this.page.locator('.tv-slicer__pane[data-view="imv1_1"] .tv-pg-btn').nth(0);
      await roiBtn.click();
      await H.waitIdle(this.page);
      await this.page.waitForTimeout(300);
      const roi   = await stacks();
      const split = await this.T(() => ["tv-pg-main", "tv-pg-roiplot"].map((c) => document.querySelector(`.tv-slicer__pane[data-view="imv1_1"] .${c}`).getBoundingClientRect().height));
      await H.shot(this.page, "fg04_roi_plot_1100x880", "fixer-2", { element: "#tv-window" });
      await roiBtn.click();
      await H.waitIdle(this.page);
      const off = await stacks();
      const canvas = async (tab, panel) => {
        await this.page.click(`.tv-tab[data-tab="${tab}"]`);
        await H.waitIdle(this.page);
        await this.page.waitForTimeout(300);
        return this.T((p) => { const r = document.querySelector(`#${p} canvas`).getBoundingClientRect(); return [r.width, r.height]; }, panel);
      };
      const plot    = await canvas(1, "tv-panel-plot");
      const profile = await canvas(2, "tv-panel-profile");
      await this.page.click('.tv-tab[data-tab="0"]');
      const ranges = await this.ranges();
      const o      = Fixer2Checks.ORIGINAL;
      R.equal(pane, o.canvases.pane, "top pane view size");
      R.equal([start, roi, split, off], [o.panes.start, o.panes.roi, o.panes.split, o.panes.start], "stack heights without, with and after the ROI plot, and the ROI plot split");
      R.equal([plot, profile], [o.canvases.plot, o.canvases.profile], "Plot and Profile canvases");
      R.assert(Fixer2Checks.close(ranges.imv1_1, o.importTop), `first top view range ${JSON.stringify(ranges.imv1_1)}`);
      return `pane ${pane.join("x")}, stacks ${start.join("/")} -> ${roi.join("/")} (split ${split.join("/")}), canvases ${plot.join("x")} and ${profile.join("x")}`;
    });
  }

  async linkAxis() {
    await this.run.check("FG-06 F-111", "the never-imaged RGB panes keep pyqtgraph's empty-image range, so Link Axis to ImageView gives the original's ranges", async () => {
      await this.fresh();
      const startup = await this.ranges();
      await this.importInput();
      const named = await this.T(() => { const v = window.app.tomovisPage.views[0].views; return Object.keys(v).filter((k) => v[k].view === PgViewBox.named.get("ImageView")); });
      const box   = await this.page.locator('.tv-slicer__pane[data-view="imv2_1"] canvas.tv-pg-main-canvas').boundingBox();
      await this.page.mouse.click(box.x + 60, box.y + 60, { button: "right" });
      await this.page.locator(".tv-menu .tv-menu__item", { hasText: "X axis" }).hover();
      await this.page.waitForTimeout(300);
      await this.page.locator(".tv-menu").last().locator(".tv-pg-axisctrl .tv-combo").last().click();
      await this.page.locator(".tv-combo__popup .tv-combo__option", { hasText: /^ImageView$/ }).click();
      await this.page.waitForTimeout(300);
      await this.page.keyboard.press("Escape");
      await this.page.keyboard.press("Escape");
      await this.page.waitForTimeout(300);
      const linked = await this.ranges();
      const o      = Fixer2Checks.ORIGINAL;
      R.equal(named, ["imv2_2"], "the view named ImageView");
      R.assert(Fixer2Checks.close(startup.imv1_2, o.startupRgb) && Fixer2Checks.close(startup.imv2_2, o.startupRgb), `startup RGB ranges ${JSON.stringify([startup.imv1_2, startup.imv2_2])}`);
      R.assert(Fixer2Checks.close(linked.imv2_1, o.linkX.imv2_1), `imv2_1 after the link ${JSON.stringify(linked.imv2_1)}`);
      R.assert(Fixer2Checks.close(linked.imv2_2, o.linkX.imv2_2), `imv2_2 after the link ${JSON.stringify(linked.imv2_2)}`);
      return `imv2_1 x ${linked.imv2_1[0].map((v) => v.toFixed(4)).join("..")}, imv2_2 y ${linked.imv2_2[1].map((v) => v.toFixed(4)).join("..")}`;
    });

    await this.run.check("FG-06 clear", "a ROI line outside the image clears the tomogram, whose empty bounds recentre its view at the origin, and the top view takes in the line", async () => {
      await this.fresh();
      await this.importInput();
      await this.typeRoi(["1000", "1000", "45", "10", "0", "0"]);
      await this.page.click('[data-widget="tab1SetButton"]');
      await H.waitIdle(this.page);
      await this.page.waitForTimeout(500);
      const ranges = await this.ranges();
      const o      = Fixer2Checks.ORIGINAL;
      R.assert(Fixer2Checks.close(ranges.imv2_1, o.outside.imv2_1), `tomogram view ${JSON.stringify(ranges.imv2_1)}`);
      R.assert(Fixer2Checks.close(ranges.imv1_1, o.outside.imv1_1), `top view ${JSON.stringify(ranges.imv1_1)}`);
      return `tomogram x ${ranges.imv2_1[0].map((v) => v.toFixed(4)).join("..")}, top x ${ranges.imv1_1[0].map((v) => v.toFixed(1)).join("..")}`;
    });
  }

  async classicScrollbars() {
    await this.run.check("GL-01 F-001", "with classic 15 px scrollbars a 1100 px viewport holds the whole window, and popups keep their width inside the client area", async () => {
      const browser = await chromium.launch({ executablePath: new ChromiumResolver().resolve(), args: H.GL_ARGS[this.options.gl], headless: true, ignoreDefaultArgs: ["--hide-scrollbars"] });
      const seen    = [];
      for (const [width, height] of [[1100, 880], [1100, 800], [1440, 700]]) {
        const page = await (await browser.newContext({ viewport: { width, height }, deviceScaleFactor: 1 })).newPage();
        await H.openTomoVis(page, this.options.base);
        await page.waitForTimeout(400);
        const fit = await page.evaluate(() => {
          const doc  = document.documentElement;
          const win  = document.querySelector("#tv-window").getBoundingClientRect();
          const sect = document.querySelector(".page--tomovis");
          return { client: doc.clientWidth, scrollbar: innerWidth - doc.clientWidth, win: [win.left, win.right], section: [sect.scrollWidth, sect.clientWidth] };
        });
        const button = page.locator('.tv-slicer__stack[data-stack="imv1"] .tv-slicer__pane.is-current .tv-pg-btn').nth(1);
        const b      = await button.boundingBox();
        await page.mouse.click(Math.min(b.x + b.width - 2, fit.client - 3), b.y + b.height / 2);
        await page.waitForTimeout(250);
        const menu = await page.evaluate(() => { const m = [...document.querySelectorAll(".tv-menu")].pop(); const r = m.getBoundingClientRect(); return { right: r.right, width: r.width, natural: m.scrollWidth + 4 }; });
        await page.screenshot({ path: path.join(this.out, `gl01_scrollbars_${width}x${height}.png`) });
        await page.close();
        R.assert(fit.win[0] >= 0 && fit.win[1] <= fit.client, `${width}x${height}: window ${JSON.stringify(fit.win)} inside the ${fit.client} px client width`);
        R.equal(fit.section[0], fit.section[1], `${width}x${height}: no sideways scrolling`);
        R.assert(menu.right <= fit.client - 4, `${width}x${height}: Menu popup right edge ${menu.right} inside ${fit.client - 4}`);
        R.equal(menu.width, menu.natural, `${width}x${height}: Menu popup width`);
        seen.push(`${width}x${height}: scrollbar ${fit.scrollbar}, window ${fit.win[1] - fit.win[0]} px, menu ends at ${menu.right}`);
      }
      await browser.close();
      R.assert(seen[1].includes("scrollbar 15"), "the 1100x800 page shows a classic scrollbar");
      return seen.join("; ");
    });
  }

  async colourTokens() {
    await this.run.check("GL-10", "the scrim, list wells, shadows and colour picker cross take their colours from the TomoVis tokens", async () => {
      await this.fresh(1440, 900);
      await H.menu(this.page, "File", "Import", "npy");
      await this.page.waitForSelector(".tv-filedialog[data-dir]");
      const styles = await this.T(() => {
        const css   = (selector, property) => getComputedStyle(document.querySelector(selector))[property];
        const cross = document.createElement("div");
        cross.className = "tv-colordialog__cross";
        document.querySelector("#tv-layer").append(cross);
        const out = { scrim: css(".tv-modal__scrim", "backgroundColor"), well: css(".tv-filedialog__list", "backgroundColor"), modal: css(".tv-modal", "boxShadow"), cross: getComputedStyle(cross).backgroundImage, splitter: css(".tv-pg-splitter__handle", "backgroundColor") };
        cross.remove();
        return out;
      });
      await this.page.keyboard.press("Escape");
      R.equal(styles.scrim, "rgba(5, 8, 11, 0.42)", "scrim");
      R.equal(styles.well, "rgba(0, 0, 0, 0.22)", "file list well");
      R.equal(styles.modal, "rgba(0, 0, 0, 0.5) 0px 26px 64px 0px", "modal shadow");
      R.equal(styles.cross, "linear-gradient(rgb(0, 0, 0), rgb(0, 0, 0)), linear-gradient(rgb(0, 0, 0), rgb(0, 0, 0))", "colour picker cross");
      R.equal(styles.splitter, "rgb(128, 128, 128)", "splitter handle");
      return Object.values(styles).join(" | ");
    });
  }

  async main() {
    const opened = await H.launch({ port: this.options.port, gl: this.options.gl, viewport: { width: 1100, height: 880 } });
    this.options.base = opened.base;
    this.page = opened.page;
    await H.openTomoVis(this.page);

    if (this.wanted("enter")) await this.enterOnButtons();
    if (this.wanted("nav")) await this.navOverlap();
    if (this.wanted("wheel")) await this.wheelScroll();
    if (this.wanted("geometry")) await this.paneGeometry();
    if (this.wanted("link")) await this.linkAxis();
    if (this.wanted("scrollbars")) await this.classicScrollbars();
    if (this.wanted("tokens")) await this.colourTokens();

    await opened.browser.close();
    const ok = this.run.summary(opened.errors);
    fs.writeFileSync(path.join(this.out, "fixer2_checks.json"), JSON.stringify({ results: this.run.results, errors: opened.errors }, null, 2));
    process.exit(ok ? 0 : 1);
  }

  wanted(name) {
    return this.options.only.length === 0 || this.options.only.includes(name);
  }
}

await new Fixer2Checks(H.args(process.argv)).main();
