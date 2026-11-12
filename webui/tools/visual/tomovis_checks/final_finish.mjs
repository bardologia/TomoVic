import fs from "node:fs";
import path from "node:path";
import { TomoVisHarness as H, TomoVisCheckRun as R, REPO } from "./harness.mjs";

class FinalFinishChecks {
  static QT = {
    tabs    : [["Slicer", 9, 36, 63, 32], ["Plot", 72, 36, 51, 32], ["Profile", 123, 36, 70, 32], ["3D", 193, 36, 43, 32]],
    menubar : [["File", 6, 0, 33, 25], ["Data", 45, 0, 39, 25]],
  };

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

  async textSizes() {
    await this.run.check("NEW-5 NEW-6 DOC-01", "text is Qt's size in TomoVic's families: 14 px in the window, 17 px in combo boxes, popups, menus, message boxes and dialogs; the README says so", async () => {
      await this.fresh();
      await this.load();
      const font = (sel) => this.T((s) => { const e = document.querySelector(s); const st = getComputedStyle(e); return `${st.fontSize}|${st.fontFamily.split(",")[0].replace(/"/g, "")}`; }, sel);
      const seen = {};
      for (const [key, sel] of Object.entries({ label: ".tv-slicer__label", button: '[data-widget="tab1SetButton"]', check: ".tv-plot__controls .tv-label", tab: ".tv-tab", menubar: ".tv-menubar__item", status: "#tv-status", line: '[data-widget="tab1QLineEdit1"]', spin: '[data-widget="tab1SpinBox"] .tv-spin__input', readout: "#tv-panel-plot .tv-mpl-toolbar__message", combo1: '[data-widget="tab1ComboBox"]', combo2: '[data-widget="tab2ComboBox"]' })) seen[key] = await font(sel);
      await this.page.click('[data-widget="tab1ComboBox"]');
      seen.popup = await font(".tv-combo__popup .tv-combo__option");
      await this.page.keyboard.press("Escape");
      await this.page.click('.tv-menubar__item[data-menu="file"]');
      seen.menu     = await font(".tv-menu .tv-menu__text");
      seen.shortcut = await font(".tv-menu .tv-menu__shortcut");
      await this.page.keyboard.press("Escape");
      await this.T(() => { window.TomoVisMessageBox.show({ level: "warning", title: "No data", text: "There is no data loaded to save.", layer: window.app.tomovisPage.ctx.layer }); });
      seen.message = await font(".tv-messagebox__text");
      seen.okWidth = await this.T(() => document.querySelector(".tv-messagebox .tv-button").getBoundingClientRect().width);
      await this.page.keyboard.press("Escape");
      await H.menu(this.page, "File", "Import", "npy");
      await this.page.waitForSelector(".tv-filedialog[data-dir]");
      await this.page.fill(".tv-filedialog__name", this.inputs);
      await this.page.press(".tv-filedialog__name", "Enter");
      await this.page.waitForFunction((d) => document.querySelector(".tv-filedialog").dataset.dir === d, this.inputs);
      seen.dialogLabel = await font(".tv-filedialog .tv-label");
      seen.dialogLine  = await font(".tv-filedialog__name");
      seen.dialogCell  = await font(".tv-filedialog__cell--size");
      const cells = await this.T(() => [...document.querySelectorAll(".tv-filedialog__cell--size")].filter((c) => c.textContent).map((c) => { const range = document.createRange(); range.selectNodeContents(c); return [c.textContent, range.getBoundingClientRect().right <= c.getBoundingClientRect().right]; }));
      seen.cancelWidth = await this.T(() => document.querySelector(".tv-filedialog__cancel").getBoundingClientRect().width);
      await this.page.click(".tv-filedialog .tv-filedialog__cancel");

      const readme = fs.readFileSync(path.join(REPO, "webui/tomovis/README.md"), "utf-8").split("\n").find((line) => line.includes("| Colours and fonts") || line.includes("| F-001, F-008")) || "";
      const window14 = ["label", "button", "check", "tab", "menubar", "status", "line", "spin", "readout"].map((k) => seen[k].split("|")[0]);
      const app17    = ["combo1", "combo2", "popup", "menu", "shortcut", "message", "dialogLabel", "dialogLine", "dialogCell"].map((k) => seen[k].split("|")[0]);
      R.equal(window14, Array(9).fill("14px"), "window text sizes");
      R.equal(app17, Array(9).fill("17px"), "application font sizes");
      R.equal(["label", "button", "combo1", "menu", "message", "dialogCell"].map((k) => seen[k].split("|")[1]), Array(6).fill("Archivo"), "Archivo text");
      R.equal(["line", "spin", "status", "shortcut", "readout", "dialogLine"].map((k) => seen[k].split("|")[1]), Array(6).fill("JetBrains Mono"), "monospace fields");
      R.equal([seen.okWidth, seen.cancelWidth, cells.every(([, fits]) => fits)], [80, 80, true], "80 px buttons and Size texts inside their cells");
      R.assert(readme.includes("14 px") && readme.includes("17 px") && !readme.includes("13 px") && !readme.includes("text sizes are TomoVic's"), `README colours and fonts row: ${readme.slice(0, 200)}`);
      return `window ${window14[0]}, application ${app17[0]}; Size cells ${cells.map(([t]) => t).slice(0, 2).join(", ")}`;
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

  async tabsAndMenus() {
    await this.run.check("LS-01", "tabs are contiguous, 32 px tall from y 36 at Qt's widths; menu bar items and menu rows have Qt's geometry, submenus open at the row with a 1 px overlap", async () => {
      await this.fresh();
      const seen = await this.T(() => {
        const win = document.querySelector("#tv-window").getBoundingClientRect();
        const rel = (e) => { const b = e.getBoundingClientRect(); return [Math.round(b.left - win.left), Math.round(b.top - win.top), Math.round(b.width), Math.round(b.height)]; };
        return { tabs: [...document.querySelectorAll(".tv-tab")].filter((t) => t.offsetParent).map((t) => [t.textContent, ...rel(t)]), menubar: [...document.querySelectorAll(".tv-menubar__item")].map((t) => [t.textContent, ...rel(t)]) };
      });
      await this.page.click('.tv-menubar__item[data-menu="file"]');
      await this.page.locator(".tv-menu .tv-menu__item", { hasText: "Import" }).hover();
      await this.page.waitForFunction(() => document.querySelectorAll(".tv-menu").length === 2);
      const menus = await this.T(() => {
        const [file, sub] = document.querySelectorAll(".tv-menu");
        const f = file.getBoundingClientRect();
        const s = sub.getBoundingClientRect();
        const row = [...file.querySelectorAll(".tv-menu__item")].find((r) => r.textContent.includes("Import")).getBoundingClientRect();
        return { rows: [...file.children].map((c) => Math.round(c.getBoundingClientRect().height)), subRows: [...sub.children].map((c) => Math.round(c.getBoundingClientRect().height)), border: file.offsetWidth - file.clientWidth, sub: [Math.round(s.left - f.right), Math.round(s.top - row.top)] };
      });
      await this.page.keyboard.press("Escape");
      await this.page.keyboard.press("Escape");

      R.equal(seen.tabs, FinalFinishChecks.QT.tabs, "tabs against the original's tab rects");
      R.equal(seen.menubar, FinalFinishChecks.QT.menubar, "menu bar items against the original");
      R.equal([menus.rows, menus.subRows, menus.border, menus.sub], [[32, 32, 2, 32], [32, 32, 32, 32], 0, [-1, 0]], "File and Import menu rows, frame, submenu offset");
      return `tabs end at ${seen.tabs.at(-1)[1] + seen.tabs.at(-1)[3]}, menu rows ${menus.rows.join("/")}`;
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
    if (this.wanted("sizes")) await this.textSizes();
    if (this.wanted("elide")) await this.elidedCells();
    if (this.wanted("tabs")) await this.tabsAndMenus();

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
