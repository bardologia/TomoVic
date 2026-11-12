import fs from "node:fs";
import path from "node:path";
import { TomoVisHarness as H, TomoVisCheckRun as R, REPO } from "./harness.mjs";

class FinalFinishChecks {
  constructor(options) {
    this.options = options;
    this.run     = new R("final-finish");
    this.inputs  = H.fixture("inputs");
    this.out     = H.shotDir("final-finish");
    this.errors  = [];
  }

  T(fn, arg) {
    return this.page.evaluate(fn, arg);
  }

  source(file) {
    return fs.readFileSync(path.join(REPO, "webui/static", file), "utf-8");
  }

  async fresh(width = 1100, height = 880) {
    await this.page.setViewportSize({ width, height });
    await this.page.goto("about:blank");
    await H.openTomoVis(this.page);
  }

  async load(name = "npy_real.npy") {
    await H.menu(this.page, "File", "Import", "npy");
    await H.chooseFile(this.page, path.join(this.inputs, name));
  }

  async widthHints() {
    await this.run.check("CR-03", "combo boxes, the Customize chooser and the Export format list take their width from one Qt width hint", async () => {
      await this.fresh();
      const seen = await this.T(() => {
        const page   = window.app.tomovisPage;
        const names  = page.ctx.tables.colortables.names;
        const slicer = document.querySelector('[data-widget="tab1ComboBox"]').getBoundingClientRect().width;
        const titles = ["Axes 1 (a long axes title)", "Axes 2"];
        const fusion = page.ctx.kit.local("combo", { items: titles, qtFont: QtFontMetrics.APP });
        page.ctx.layer.append(fusion.el);
        const chooser = fusion.el.getBoundingClientRect().width;
        fusion.el.remove();
        return { slicer, slicerHint: QtFontMetrics.widest(names, QtFontMetrics.APP) + 30, chooser, chooserHint: QtFontMetrics.widest(titles, QtFontMetrics.APP) + 27 };
      });
      const sources = ["js/tomovis_widgets.js", "js/tomovis_mpl.js", "js/tomovis_pg_export.js"].map((file) => this.source(file)).join("\n");
      const copies  = (sources.match(/Math\.max\([^\n]*horizontalAdvance/g) || []).length;

      R.equal([seen.slicer, seen.chooser], [seen.slicerHint, seen.chooserHint], "combo widths against the style sheet and Fusion hints");
      R.equal([copies, sources.includes("comboHint"), sources.includes("COMBO_CHROME")], [1, false, false], "width-hint copies besides QtFontMetrics.widest");
      return `Slicer combo ${seen.slicer} px, Fusion combo ${seen.chooser} px; QtFontMetrics.widest is the only copy`;
    });
  }

  async sharedPopup() {
    await this.run.check("CR-01", "the Look in combo and the window combos share one popup class; the colormap list stops at 10 rows and Look in lists every place, as Qt does", async () => {
      await this.fresh();
      await this.load();
      await this.page.click('[data-widget="tab1ComboBox"]');
      const combo = await this.T(() => { const p = document.querySelector(".tv-combo__popup"); return { rows: p.querySelectorAll(".tv-combo__option").length, shown: Math.round(p.clientHeight / p.querySelector(".tv-combo__option").getBoundingClientRect().height), expanded: document.querySelector('[data-widget="tab1ComboBox"]').getAttribute("aria-expanded") }; });
      await this.page.keyboard.press("Escape");

      await H.menu(this.page, "File", "Import", "npy");
      await this.page.waitForSelector(".tv-filedialog[data-dir]");
      await this.page.fill(".tv-filedialog__name", this.inputs);
      await this.page.press(".tv-filedialog__name", "Enter");
      await this.page.waitForFunction((d) => document.querySelector(".tv-filedialog").dataset.dir === d, this.inputs);
      await this.page.click(".tv-filedialog__lookin");
      const look = await this.T(() => { const p = document.querySelector(".tv-filedialog__lookinpopup"); return { cls: p.classList.contains("tv-qt-scroll"), rows: p.querySelectorAll(".tv-combo__option").length, overflow: p.scrollHeight - p.clientHeight, disabled: [...p.querySelectorAll(".tv-combo__option.is-disabled")].map((o) => o.textContent) }; });
      await this.page.keyboard.press("ArrowDown");
      await this.page.keyboard.press("Enter");
      await this.page.waitForFunction((d) => document.querySelector(".tv-filedialog").dataset.dir !== d, this.inputs);
      const moved = await this.T(() => [document.querySelector(".tv-filedialog").dataset.dir, Boolean(document.querySelector(".tv-filedialog__lookinpopup")), document.querySelector(".tv-filedialog__lookin").getAttribute("aria-expanded")]);
      await this.page.click(".tv-filedialog .tv-filedialog__cancel");

      const dialogs = this.source("js/tomovis_dialogs.js");
      R.equal([combo.rows, combo.shown, combo.expanded], [19, 10, "true"], "colormap popup");
      R.equal([look.cls, look.overflow, look.disabled.includes("Recent Places") || look.rows >= 12], [true, 0, true], "Look in popup");
      R.equal(moved, [path.dirname(this.inputs), false, "false"], "ArrowDown and Enter in Look in");
      R.equal([dialogs.includes('"tv-combo__popup'), dialogs.includes("new QtComboPopup")], [false, true], "file dialog builds no popup of its own");
      return `colormap ${combo.shown} of ${combo.rows} rows; Look in ${look.rows} rows, none hidden`;
    });
  }

  async elidedCells() {
    await this.run.check("CR-02", "text is measured only through QtFontMetrics; the file dialog elides with Qt's ElideMiddle rule, so the Size column and Look in show the original's texts", async () => {
      await this.fresh();
      await H.menu(this.page, "File", "Import", "npy");
      await this.page.waitForSelector(".tv-filedialog[data-dir]");
      await this.page.fill(".tv-filedialog__name", this.inputs);
      await this.page.press(".tv-filedialog__name", "Enter");
      await this.page.waitForFunction((d) => document.querySelector(".tv-filedialog").dataset.dir === d, this.inputs);
      const seen = await this.T(() => ({ names: [...document.querySelectorAll(".tv-filedialog__entryname")].map((c) => c.textContent), sizes: [...document.querySelectorAll(".tv-filedialog__cell--size")].map((c) => c.textContent), look: document.querySelector(".tv-filedialog__lookin .tv-combo__text").textContent }));
      await this.page.click(".tv-filedialog .tv-filedialog__cancel");

      const contexts = ["js/tomovis_dialogs.js", "js/tomovis_widgets.js"].map((file) => (this.source(file).match(/createElement\("canvas"\)\.getContext/g) || []).length);
      const reaches  = (this.source("js/tomovis_widgets.js").match(/QtFontMetrics\.context\.(font|measureText)/g) || []).length;
      R.equal(seen.names, ["npy_channels_2.npy", "npy_channels_3.npy", "npy_channels_4.npy", "npy_complex_nan_inf.npy", "npy_covariance_5d.npy", "npy_float64.npy", "npy_one_range_line.npy", "npy_real.npy"], "Name column as the original draws it");
      R.equal(seen.sizes, ["30.13 KiB", "45.13 KiB", "60.13 KiB", "30.13 KiB", "108\u2026KiB", "7.63 KiB", "368\u2026tes", "48.13 KiB"], "Size column as the original draws it");
      R.assert(seen.look.includes("\u2026") && seen.look.endsWith("movis/inputs"), `Look in text not elided in the middle: ${seen.look}`);
      R.equal([...contexts, reaches], [0, 1, 2], "measuring contexts in the dialog and widget modules, and uses of QtFontMetrics.context outside cssMeasure");
      return `${seen.sizes.join(", ")}; Look in ${seen.look}`;
    });
  }

  async main() {
    const opened = await H.launch({ port: this.options.port, gl: this.options.gl, viewport: { width: 1100, height: 880 } });
    this.options.base = opened.base;
    this.context = opened.context;
    this.browser = opened.browser;
    this.page    = opened.page;
    await H.openTomoVis(this.page);

    if (this.wanted("hints")) await this.widthHints();
    if (this.wanted("popup")) await this.sharedPopup();
    if (this.wanted("elide")) await this.elidedCells();

    await opened.browser.close();
    const errors = [...opened.errors, ...this.errors];
    const ok     = this.run.summary(errors);
    fs.writeFileSync(path.join(this.out, "final_finish_checks.json"), JSON.stringify({ results: this.run.results, errors }, null, 2));
    process.exit(ok ? 0 : 1);
  }

  wanted(name) {
    return this.options.only.length === 0 || this.options.only.includes(name);
  }
}

await new FinalFinishChecks(H.args(process.argv, "final-finish")).main();
