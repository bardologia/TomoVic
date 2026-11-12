import fs from "node:fs";
import path from "node:path";
import { TomoVisHarness as H, TomoVisCheckRun as R, REPO } from "./harness.mjs";

class FinalFiguresChecks {
  static AGENT     = "final-figures";
  static REALISTIC = path.join(REPO, "logs/tomovis_port/fixtures/realistic_traun_hv.hd5");
  static OBLIQUE   = ["30", "40", "12", "330", "0", "0"];
  static VIEWPORT  = { width: 1180, height: 916 };
  static WINDOW    = ".tv-window { width: 1100px !important; height: 880px !important; min-height: 0 !important; flex: none !important; }";
  static ORIGINAL  = {
    toolbar   : { tools: [[4, 4, 33, 32], [38, 4, 33, 32], [72, 4, 33, 32], [113, 4, 33, 32], [147, 4, 33, 32], [181, 4, 33, 32], [215, 4, 33, 32], [256, 4, 33, 32]], separators: [[106, 10, 6, 20], [249, 10, 6, 20]], label: [290, 748] },
    subplots  : { client: [354, 261], spins: [[89, 50, 73, 33], [89, 89, 73, 33], [89, 128, 73, 33], [89, 167, 73, 33], [258, 50, 73, 33], [258, 89, 73, 33]], buttons: [[11, 218, 163, 32], [180, 142, 163, 32], [180, 180, 163, 32], [180, 218, 163, 32]], frames: [[11, 39], [180, 39]] },
    export    : { client: [278, 181], text: [11, 11, 256, 159], value: "top=0.9,\nbottom=0.1,\nleft=0.12,\nright=1.0,\nhspace=0.2,\nwspace=0.2" },
    chooser   : { client: [429, 122], label: [11, 11, 407, 24], combo: [11, 41, 407, 32], buttons: [[252, 79, 80, 32], [338, 79, 80, 32]] },
    axes      : { client: [276, 286], fields: [[70, 11, 195, 32], [70, 49, 195, 32], [70, 87, 195, 33], [70, 126, 195, 33], [70, 165, 195, 33], [70, 204, 195, 33]], buttons: [[99, 243, 80, 32], [185, 243, 80, 32]] },
    options   : { client: [463, 634], buttons: [[200, 591, 80, 32], [286, 591, 80, 32], [372, 591, 80, 32]], separators: { Axes: [94, 306, 518], "Images, etc.": [], Curves: [132, 344] } },
    rows      : { spin: { plain: 99, xline: 71 }, sliderMin: 200, margin: 20 },
  };

  constructor(options) {
    this.options = options;
    this.run     = new R("final-figures");
    this.out     = H.shotDir(FinalFiguresChecks.AGENT);
  }

  T(fn, arg) {
    return this.page.evaluate(fn, arg);
  }

  async settle() {
    await H.waitIdle(this.page);
    await this.T(async () => {
      for (const view of window.app.tomovisPage.views) if (view && view.figure) await view.figure.drawing;
    });
    await this.page.waitForTimeout(150);
  }

  async windowSize(width, height, viewport) {
    await this.style.evaluate((node, size) => { node.textContent = `.tv-window { width: ${size[0]}px !important; height: ${size[1]}px !important; min-height: 0 !important; flex: none !important; }`; }, [width, height]);
    await this.page.setViewportSize(viewport);
    await this.page.waitForTimeout(400);
    await this.settle();
  }

  async plotted() {
    await this.page.setViewportSize(FinalFiguresChecks.VIEWPORT);
    await this.page.goto("about:blank");
    await H.openTomoVis(this.page);
    this.style = await this.page.addStyleTag({ content: FinalFiguresChecks.WINDOW });
    await H.menu(this.page, "File", "Import", "hd5");
    await H.chooseFile(this.page, FinalFiguresChecks.REALISTIC);
    for (const [i, text] of FinalFiguresChecks.OBLIQUE.entries()) await this.page.fill(`input[data-widget="tab1QLineEdit${i + 1}"]`, text);
    await this.settle();
    await this.page.click('[data-widget="tab1SetButton"]');
    await this.settle();
    await this.page.click('[data-widget="tab1PlotButton"]');
    await this.settle();
    await this.page.mouse.move(1170, 910);
    await this.settle();
  }

  async describe(selector) {
    return this.T((sel) => {
      const dialog = [...document.querySelectorAll(sel)].pop();
      const outer  = dialog.getBoundingClientRect();
      const title  = dialog.querySelector(":scope > .tv-modal__title");
      const top    = title.getBoundingClientRect().bottom;
      const left   = outer.left + dialog.clientLeft;
      const rect   = (el) => {
        const r = el.getBoundingClientRect();
        return [Math.round(r.left - left), Math.round(r.top - top), Math.round(r.width), Math.round(r.height)];
      };
      const all = (query) => [...dialog.querySelectorAll(query)].filter((el) => el.getClientRects().length && getComputedStyle(el).visibility === "visible").map(rect);
      return {
        client    : [dialog.clientWidth, Math.round(outer.bottom - dialog.clientTop - top)],
        modal     : dialog.getAttribute("aria-modal"),
        scrims    : document.querySelectorAll(".tv-modal__scrim").length,
        buttons   : all(".tv-button"),
        spins     : all(".tv-spin"),
        lines     : all(".tv-line"),
        labels    : all(".tv-label"),
        combos    : all(".tv-combo"),
        frames    : all(".tv-group__body").map((r) => r.slice(0, 2)),
        separators: all(".tv-mpl-form > .tv-mpl-form__sep:not(.tv-mpl-form__label)").map((r) => [r[1], r[3]]),
        text      : all("textarea"),
      };
    }, selector);
  }

  async subplotDialog() {
    await this.run.check("LF-03 subplots", "Configure subplots has the original's 354x261 client area, 73x33 spin boxes, group frames and buttons at Qt's positions", async () => {
      await this.page.click('#tv-panel-plot .tv-mpl-tool[data-method="configure_subplots"]');
      await this.page.waitForSelector(".tv-mpl-subplots .tv-spin");
      await this.settle();
      const got = await this.describe(".tv-mpl-subplots");
      const ori = FinalFiguresChecks.ORIGINAL.subplots;
      await this.page.locator(".tv-mpl-subplots").screenshot({ path: path.join(this.out, "lf03_subplots.png") });
      R.equal(got.client, ori.client, "client size");
      R.equal(got.spins, ori.spins, "spin boxes");
      R.equal(got.buttons, ori.buttons, "buttons");
      R.equal(got.frames, ori.frames, "group frame corners");
      return `client ${got.client.join("x")}`;
    });
  }

  async exportValues() {
    await this.run.check("FG-04", "Export values opens a plain non-modal window without scrim or buttons; the subplot dialog stays usable, the window is blocked until that dialog closes", async () => {
      await this.page.click('.tv-mpl-subplots .tv-button:text-is("Export values")');
      await this.page.waitForSelector(".tv-mpl-export");
      await this.page.waitForTimeout(200);
      const got = await this.describe(".tv-mpl-export");
      const ori = FinalFiguresChecks.ORIGINAL.export;
      const value = await this.page.inputValue(".tv-mpl-export__text");
      await this.page.screenshot({ path: path.join(this.out, "fg04_export_over_subplots.png") });

      const text = await this.page.locator(".tv-mpl-export__text").boundingBox();
      await this.page.mouse.click(text.x + 40, text.y + 30);
      const blockedFocus = await this.T(() => document.activeElement.classList.contains("tv-mpl-export__text"));
      const title = await this.page.locator(".tv-mpl-export > .tv-modal__title").boundingBox();
      await this.dragExport(title);
      const moved = await this.page.locator(".tv-mpl-export").boundingBox();
      await this.page.click('.tv-mpl-subplots .tv-button:text-is("Export values")');
      await this.page.waitForTimeout(200);
      const replaced = await this.page.locator(".tv-mpl-export").count();
      await this.dragExport(await this.page.locator(".tv-mpl-export > .tv-modal__title").boundingBox());

      const before = await this.T(() => [...document.querySelectorAll(".tv-mpl-subplots .tv-spin__input")].map((i) => i.value));
      await this.page.click('.tv-mpl-subplots .tv-button:text-is("Tight layout")');
      await this.settle();
      const tight = await this.T(() => [...document.querySelectorAll(".tv-mpl-subplots .tv-spin__input")].map((i) => i.value));
      await this.page.click('.tv-mpl-subplots .tv-button:text-is("Reset")');
      await this.settle();
      await this.page.click('.tv-mpl-subplots .tv-button:text-is("Close")');
      await this.page.waitForSelector(".tv-mpl-subplots", { state: "detached" });
      const stays = await this.page.locator(".tv-mpl-export").count();
      await this.page.locator(".tv-mpl-export__text").click();
      const freeFocus = await this.T(() => document.activeElement.classList.contains("tv-mpl-export__text"));
      await this.page.keyboard.press("Escape");
      const afterEscape = await this.page.locator(".tv-mpl-export").count();

      R.equal([got.modal, got.scrims, got.buttons.length], ["false", 1, 0], "aria-modal, scrims (the subplot dialog's only), buttons");
      R.equal(got.client, ori.client, "client size");
      R.equal(got.text[0], ori.text, "text box");
      R.equal(value, ori.value, "text");
      R.equal(blockedFocus, false, "the text takes no click while the subplot dialog is open");
      R.assert(moved.x < title.x - 300, `the window moves by its title bar while blocked (x ${moved.x})`);
      R.equal(replaced, 1, "a second Export values replaces the window, as Qt drops the previous QDialog");
      R.assert(JSON.stringify(tight) !== JSON.stringify(before), `Tight layout works with the window open (${tight})`);
      R.equal([stays, freeFocus, afterEscape], [1, true, 0], "window stays after the dialog closes, takes clicks, closes on Escape");
      return `client ${got.client.join("x")}, scrims ${got.scrims}, tight ${tight.join(" ")}`;
    });
  }

  async dragExport(title) {
    await this.page.mouse.move(title.x + 30, title.y + title.height / 2);
    await this.page.mouse.down();
    await this.page.mouse.move(title.x - 330, title.y + title.height / 2, { steps: 4 });
    await this.page.mouse.up();
  }

  async chooserAndOptions(panel, tag, tabs) {
    await this.page.click(`${panel} .tv-mpl-tool[data-method="edit_parameters"]`);
    await this.page.waitForTimeout(500);
    let chooser = null;
    if (await this.page.locator(".tv-mpl-chooser").count()) {
      chooser = await this.describe(".tv-mpl-chooser");
      await this.page.locator(".tv-mpl-chooser").screenshot({ path: path.join(this.out, `lf03_${tag}_chooser.png`) });
      await this.page.click('.tv-mpl-chooser .tv-modal__buttons .tv-button:text-is("OK")');
    }
    await this.page.waitForSelector(".tv-mpl-options");
    await this.settle();
    const pages = {};
    for (const name of tabs) {
      await this.page.click(`.tv-mpl-options .tv-mpl-tabs .tv-tab:text-is("${name}")`);
      await this.page.waitForTimeout(200);
      pages[name] = await this.describe(".tv-mpl-options");
      await this.page.locator(".tv-mpl-options").screenshot({ path: path.join(this.out, `lf06_${tag}_${name.replace(/\W+/g, "_")}.png`) });
    }
    await this.page.click('.tv-mpl-options .tv-modal__buttons .tv-button:text-is("Cancel")');
    await this.settle();
    return { chooser, pages };
  }

  async plotCustomize() {
    let result = null;
    await this.run.check("LF-03 chooser", "the Customize chooser has Qt's margins, 24 px label row, 32 px combo, 80x32 buttons and the original's 429x122 size", async () => {
      result = await this.chooserAndOptions("#tv-panel-plot", "plot", ["Axes", "Images, etc."]);
      const got = result.chooser;
      const ori = FinalFiguresChecks.ORIGINAL.chooser;
      R.equal(got.client, ori.client, "client size");
      R.equal(got.labels[0], ori.label, "label");
      R.equal(got.combos[0], ori.combo, "combo");
      R.equal(got.buttons, ori.buttons, "buttons");
      return `client ${got.client.join("x")}`;
    });
    await this.run.check("LF-06 plot", "Figure options keeps 463x634 on every tab, separator rows are 24 px at Qt's rows, OK/Cancel/Apply never move", async () => {
      const ori = FinalFiguresChecks.ORIGINAL.options;
      for (const [name, got] of Object.entries(result.pages)) {
        R.equal(got.client, ori.client, `${name} client size`);
        R.equal(got.buttons, ori.buttons, `${name} buttons`);
        R.equal(got.separators, ori.separators[name].map((y) => [y, 24]), `${name} separators`);
      }
      return Object.entries(result.pages).map(([name, got]) => `${name} ${got.client.join("x")}`).join(", ");
    });
  }

  async axesDialog() {
    await this.run.check("LF-03 axes", "Axes Settings has the original's 276x286 client area with fields and buttons at Qt's positions", async () => {
      await this.page.click('[data-widget="tab2AxesButton"]');
      await this.page.waitForSelector(".tv-axes-dialog");
      await this.page.waitForTimeout(300);
      const got = await this.describe(".tv-axes-dialog");
      const ori = FinalFiguresChecks.ORIGINAL.axes;
      await this.page.locator(".tv-axes-dialog").screenshot({ path: path.join(this.out, "lf03_axes_dialog.png") });
      await this.page.click('.tv-axes-dialog .tv-modal__buttons .tv-button:text-is("Cancel")');
      await this.settle();
      const fields = [...got.lines, ...got.spins].sort((a, b) => a[1] - b[1]);
      R.equal(got.client, ori.client, "client size");
      R.equal(fields, ori.fields, "fields");
      R.equal(got.buttons, ori.buttons, "buttons");
      return `client ${got.client.join("x")}`;
    });
  }

  async toolbarItems() {
    return this.T(() => {
      const bar = document.querySelector("#tv-panel-plot .tv-mpl-toolbar");
      const b   = bar.getBoundingClientRect();
      const rel = (el) => {
        const r = el.getBoundingClientRect();
        return [Math.round(r.left - b.left), Math.round(r.top - b.top), Math.round(r.width), Math.round(r.height)];
      };
      const label = bar.querySelector(".tv-mpl-toolbar__message");
      return {
        tools      : [...bar.querySelectorAll(".tv-mpl-tool")].map(rel),
        separators : [...bar.querySelectorAll(".tv-mpl-toolbar__sep")].map(rel),
        label      : [rel(label)[0], rel(label)[2]],
        opacity    : [...bar.querySelectorAll(".tv-mpl-tool")].map((el) => [el.getAttribute("aria-label"), el.disabled, getComputedStyle(el).opacity]),
        readout    : [getComputedStyle(label).fontSize, getComputedStyle(document.querySelector("#tv-panel-plot .tv-plot__controls .tv-label")).fontSize, getComputedStyle(label).textAlign],
      };
    });
  }

  async toolLook(method, name) {
    const tool = this.page.locator(`#tv-panel-plot .tv-mpl-tool[data-method="${method}"]`);
    await tool.screenshot({ path: path.join(this.out, `${name}.png`) });
    return this.T((m) => {
      const s = getComputedStyle(document.querySelector(`#tv-panel-plot .tv-mpl-tool[data-method="${m}"]`));
      return { border: `${s.borderTopWidth} ${s.borderTopColor}`, background: s.backgroundImage !== "none" ? "gradient" : s.backgroundColor, shadow: s.boxShadow };
    }, method);
  }

  async toolbar() {
    await this.run.check("LF-04", "disabled Back and Forward draw exactly like enabled tools, as matplotlib 3.11.2's icon engine draws them", async () => {
      const items = await this.toolbarItems();
      const back  = this.page.locator('#tv-panel-plot .tv-mpl-tool[data-method="back"]');
      const off   = await back.screenshot({ path: path.join(this.out, "lf04_back_disabled.png") });
      await this.T(() => { document.querySelector('#tv-panel-plot .tv-mpl-tool[data-method="back"]').disabled = false; });
      const on    = await back.screenshot({ path: path.join(this.out, "lf04_back_enabled.png") });
      await this.T(() => { document.querySelector('#tv-panel-plot .tv-mpl-tool[data-method="back"]').disabled = true; });
      R.equal(items.opacity.slice(1, 3), [["Back", true, "1"], ["Forward", true, "1"]], "Back and Forward disabled at full opacity");
      R.assert(off.equals(on), "the disabled Back button's pixels equal the enabled button's");
      return `${off.length} byte grabs identical`;
    });

    await this.run.check("LF-05", "toolbar pitch, 6 px separators, raised hover, sunken checked look and the readout at the window font size", async () => {
      const items = await this.toolbarItems();
      const ori   = FinalFiguresChecks.ORIGINAL.toolbar;
      const tokens = await this.T(() => {
        const css = getComputedStyle(document.querySelector(".page--tomovis"));
        const probe = document.createElement("span");
        document.body.append(probe);
        const color = (value) => { probe.style.color = value; return getComputedStyle(probe).color; };
        const out = { strong: color(css.getPropertyValue("--line-strong")), accent: color(css.getPropertyValue("--accent")) };
        probe.remove();
        return out;
      });
      await this.page.locator("#tv-panel-plot .tv-mpl-toolbar").screenshot({ path: path.join(this.out, "lf05_toolbar_idle.png") });
      const idle = await this.toolLook("pan", "lf05_pan_idle");
      await this.page.hover('#tv-panel-plot .tv-mpl-tool[data-method="pan"]');
      await this.page.waitForTimeout(150);
      const hover = await this.toolLook("pan", "lf05_pan_hover");
      await this.page.click('#tv-panel-plot .tv-mpl-tool[data-method="pan"]');
      await this.settle();
      await this.page.mouse.move(1170, 910);
      await this.page.waitForTimeout(150);
      const checked = await this.toolLook("pan", "lf05_pan_checked");
      await this.page.locator("#tv-panel-plot .tv-mpl-toolbar").screenshot({ path: path.join(this.out, "lf05_toolbar_pan_checked.png") });
      await this.page.click('#tv-panel-plot .tv-mpl-tool[data-method="pan"]');
      await this.settle();
      await this.page.mouse.move(1170, 910);

      R.equal(items.tools, ori.tools, "tool rects");
      R.equal(items.separators, ori.separators, "separator rects");
      R.equal(items.label, ori.label, "readout label x and width");
      R.equal(idle.border.split(" ")[0], "1px", "1 px tool frame");
      R.equal([hover.border, hover.background], [`1px ${tokens.strong}`, "gradient"], "hover is a raised panel");
      R.equal(checked.border, `1px ${tokens.strong}`, "checked frame");
      R.assert(checked.shadow.includes("inset") && !checked.border.includes(tokens.accent), `checked is sunken, not an accent outline (${checked.shadow})`);
      R.equal([items.readout[0] === items.readout[1], items.readout[2]], [true, "right"], "readout at the window label size, right aligned");
      return `hover ${hover.border}, checked ${checked.shadow}, readout ${items.readout[0]}`;
    });
  }

  async rowGeometry() {
    return this.T(() => {
      const win = document.querySelector(".tv-window").getBoundingClientRect();
      const get = (name) => document.querySelector(`[data-widget="${name}"]`);
      const slider  = get("tab2Slider");
      const stretch = document.querySelector("#tv-panel-plot .tv-plot__controls > .tv-stretch");
      const clear   = get("tab2ClearButton").getBoundingClientRect();
      const s       = slider.getBoundingClientRect();
      return {
        window  : Math.round(win.width),
        slider  : Math.round(s.width),
        layout  : Math.round(s.width + parseFloat(getComputedStyle(slider).marginRight)),
        stretch : Math.round(stretch.getBoundingClientRect().width),
        spin    : Math.round(get("tab2SpinBox").getBoundingClientRect().width),
        clear   : Math.round(clear.right - win.left),
      };
    });
  }

  async plotRow() {
    await this.run.check("LF-08", "the bins slider and the row's end stretch share free space as Qt's grid does: slider at least 200 px, equal to the stretch once both fit, and running under the Colormap label when the row is short", async () => {
      const seen = [];
      for (const xline of [false, true]) {
        const checked = await this.T(() => document.querySelector('[data-widget="tab2ChkBox3"]').classList.contains("is-checked"));
        if (checked !== xline) {
          await this.page.click('[data-widget="tab2ChkBox3"]');
          await this.settle();
        }
        for (const [width, height, viewport] of [[1100, 880, { width: 1180, height: 916 }], [1244, 880, { width: 1280, height: 916 }], [1404, 880, { width: 1440, height: 916 }], [1884, 1044, { width: 1920, height: 1080 }]]) {
          await this.windowSize(width, height, viewport);
          const ori   = FinalFiguresChecks.ORIGINAL.rows;
          const row   = await this.rowGeometry();
          const share = row.layout + row.stretch;
          const tag   = `${width} ${xline ? "X [m] on" : "X [m] off"}`;
          await this.page.locator("#tv-panel-plot .tv-plot__controls").screenshot({ path: path.join(this.out, `lf08_row_${width}_${xline ? "xline" : "plain"}.png`) });
          R.assert(Math.abs(row.slider - Math.max(ori.sliderMin, share / 2)) <= 1, `${tag}: slider ${row.slider} is max(200, ${share} / 2)`);
          if (share >= 2 * ori.sliderMin) R.assert(Math.abs(row.slider - row.stretch) <= 1, `${tag}: slider ${row.slider} equals stretch ${row.stretch}`);
          if (share < ori.sliderMin) R.equal([row.slider, row.layout < ori.sliderMin, row.stretch, row.clear], [ori.sliderMin, true, 0, width - ori.margin], `${tag}: short row keeps its end, the 200 px slider runs ${ori.sliderMin - share} px past its ${share} px cell`);
          R.equal(row.spin, xline ? ori.spin.xline : ori.spin.plain, `${tag}: X [m] spin box width from its range`);
          seen.push(`${tag}: slider ${row.slider} (layout ${row.layout}) stretch ${row.stretch} clear ${row.clear}`);
        }
      }
      await this.windowSize(1100, 880, FinalFiguresChecks.VIEWPORT);
      return seen.join("; ");
    });
  }

  async avifSave() {
    await this.run.check("FG-03", "Save as AVIF still writes an AVIF file in the port (the tomovis env's Pillow lacks AVIF, so the original fails there)", async () => {
      const file = path.join(this.out, "fg03_plot.avif");
      fs.rmSync(file, { force: true });
      await this.page.click('#tv-panel-plot .tv-mpl-tool[data-method="save_figure"]');
      await this.page.waitForSelector(".tv-filedialog[data-dir]");
      const filters = await this.T(() => [...document.querySelectorAll(".tv-filedialog__filter .tv-combo__sizer > span")].map((s) => s.textContent));
      await H.chooseFile(this.page, file);
      await this.settle();
      const boxes = await this.page.locator(".tv-messagebox").count();
      const head  = fs.readFileSync(file).subarray(4, 12).toString("latin1");
      R.assert(filters.includes("AV1 Image File Format (*.avif)"), `AVIF filter offered (${filters.length} filters)`);
      R.equal([boxes, head], [0, "ftypavif"], "no error box, AVIF signature");
      return `${fs.statSync(file).size} bytes`;
    });
  }

  async scriptKeys() {
    await this.run.check("FG-06", "SlicerMatplotlib page: f toggles the figure window full screen and q closes it, as in the original's pyplot window", async () => {
      await this.page.setViewportSize({ width: 1280, height: 900 });
      await this.page.goto("about:blank");
      await this.page.goto(`${H.base}/#/tomovis_scripts`);
      await this.page.waitForFunction(() => window.app && window.app.tomovisScriptsPage && window.app.tomovisScriptsPage.ctx && window.app.tomovisScriptsPage.ctx.session.sid, null, { timeout: 30000 });
      await this.page.fill(".tv-script-slicer__path", H.fixture("inputs/fusar_one_key_range.hd5"));
      await this.page.click('.tv-script-slicer .tv-button:text-is("Load")');
      await this.page.waitForSelector(".tv-script-slicer__figure:not([hidden]) .tv-mpl-canvas");
      await H.waitIdle(this.page);
      const wrap = this.page.locator(".tv-script-slicer__figure .tv-mpl-canvaswrap");
      const box  = await wrap.boundingBox();
      await this.page.mouse.click(box.x + box.width / 2, box.y + box.height / 2);
      await H.waitIdle(this.page);

      const size = () => this.T(() => {
        const host = document.querySelector(".tv-script-slicer__figure");
        const el   = host.querySelector(".tv-mpl");
        const w    = host.querySelector(".tv-mpl-canvaswrap");
        const c    = host.querySelector(".tv-mpl-canvas");
        return { full: document.fullscreenElement === el, wrap: [w.clientWidth, w.clientHeight], canvas: [c.width, c.height], hidden: host.hidden, empty: !document.querySelector(".tv-script-slicer__empty").hidden };
      });
      const start = await size();
      await this.page.keyboard.press("f");
      await this.page.waitForFunction(() => document.fullscreenElement !== null);
      await H.waitIdle(this.page);
      await this.page.waitForTimeout(400);
      await H.waitIdle(this.page);
      const full = await size();
      await this.page.screenshot({ path: path.join(this.out, "fg06_full_screen.png") });
      await this.page.keyboard.press("f");
      await this.page.waitForFunction(() => document.fullscreenElement === null);
      await H.waitIdle(this.page);
      await this.page.waitForTimeout(400);
      await H.waitIdle(this.page);
      const back = await size();
      await this.page.keyboard.press("q");
      await H.waitIdle(this.page);
      const closed = await size();
      await this.page.screenshot({ path: path.join(this.out, "fg06_after_q.png") });
      await this.page.click('.tv-script-slicer .tv-button:text-is("Load")');
      await this.page.waitForSelector(".tv-script-slicer__figure:not([hidden]) .tv-mpl-canvas");
      await H.waitIdle(this.page);
      const reloaded = await size();
      const viewport = this.page.viewportSize();

      R.equal([start.full, start.wrap, start.canvas], [false, [800, 600], [800, 600]], "start");
      R.equal(full.full, true, "f makes the figure window full screen");
      R.equal(full.wrap[0], viewport.width, "full screen canvas spans the screen width");
      R.assert(full.canvas.every((value, i) => Math.abs(value - full.wrap[i]) <= 1), `the server re-rendered the figure at the full screen size (${full.canvas} for ${full.wrap}; Agg truncates the inch size)`);
      R.equal([back.full, back.wrap, back.canvas], [false, [800, 600], [800, 600]], "f again leaves full screen");
      R.equal([closed.hidden, closed.empty], [true, true], "q closes the figure window");
      R.equal([reloaded.hidden, reloaded.canvas], [false, [800, 600]], "Load opens the figure again");
      return `full screen canvas ${full.canvas.join("x")}`;
    });
  }

  async main() {
    const opened = await H.launch({ port: this.options.port, gl: this.options.gl, viewport: FinalFiguresChecks.VIEWPORT });
    this.page = opened.page;

    if (this.wanted("plot")) {
      await this.plotted();
      await this.toolbar();
      await this.subplotDialog();
      await this.exportValues();
      await this.plotCustomize();
      await this.axesDialog();
      await this.avifSave();
      await this.plotRow();
      await this.page.click('[data-widget="tab2PlotButton"]');
      await this.settle();
      await this.run.check("LF-06 profile", "Profile Figure options: 463x634 on Axes and Curves with Qt's separator rows", async () => {
        const result = await this.chooserAndOptions("#tv-panel-profile", "profile", ["Axes", "Curves"]);
        const ori    = FinalFiguresChecks.ORIGINAL.options;
        for (const [name, got] of Object.entries(result.pages)) {
          R.equal(got.client, ori.client, `${name} client size`);
          R.equal(got.buttons, ori.buttons, `${name} buttons`);
          R.equal(got.separators, ori.separators[name].map((y) => [y, 24]), `${name} separators`);
        }
        return Object.entries(result.pages).map(([name, got]) => `${name} ${got.client.join("x")}`).join(", ");
      });
    }
    if (this.wanted("scripts")) await this.scriptKeys();

    await opened.browser.close();
    const ok = this.run.summary(opened.errors);
    fs.writeFileSync(path.join(this.out, "final_figures_checks.json"), JSON.stringify({ results: this.run.results, errors: opened.errors }, null, 2));
    process.exit(ok ? 0 : 1);
  }

  wanted(name) {
    return this.options.only.length === 0 || this.options.only.includes(name);
  }
}

await new FinalFiguresChecks(H.args(process.argv, FinalFiguresChecks.AGENT)).main();
