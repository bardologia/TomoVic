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

  async main() {
    const opened = await H.launch({ port: this.options.port, gl: this.options.gl, viewport: { width: 1100, height: 880 } });
    this.options.base = opened.base;
    this.context = opened.context;
    this.browser = opened.browser;
    this.page    = opened.page;
    await H.openTomoVis(this.page);

    if (this.wanted("hints")) await this.widthHints();

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
