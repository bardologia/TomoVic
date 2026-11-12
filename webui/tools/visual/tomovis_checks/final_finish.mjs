import fs from "node:fs";
import path from "node:path";
import { TomoVisHarness as H, TomoVisCheckRun as R, REPO } from "./harness.mjs";

class FinalFinishChecks {
  static REALISTIC = path.join(REPO, "logs/tomovis_port/fixtures/realistic_traun_hv.hd5");

  static QT = {
    tabs    : [["Slicer", 9, 36, 63, 32], ["Plot", 72, 36, 51, 32], ["Profile", 123, 36, 70, 32], ["3D", 193, 36, 43, 32]],
    menubar : [["File", 6, 0, 33, 25], ["Data", 45, 0, 39, 25]],
    plotRow : {
      names : ["tab2Label1", "tab2ChkBox1", "tab2Label2", "tab2ChkBox2", "tab2Slider", "tab2Label3", "tab2ComboBox", "tab2Label4", "tab2ChkBox3", "tab2SpinBox", "tab2Label5", "tab2ChkBox4", "tab2AxesButton", "tab2PlotButton", "tab2ClearButton"],
      tops  : [0, 12, 0, 12, 12, 0, 3, 0, 12, 5, 0, 12, 5, 5, 5],
      x     : { 1100: [20, 96, 116, 206, 226, 365, 437, 570, 613, 633, 738, 808, 828, 914, 1000], 1244: [20, 96, 116, 206, 226, 437, 509, 648, 691, 711, 816, 886, 906, 992, 1078], 1404: [20, 96, 116, 206, 226, 450, 522, 661, 704, 724, 829, 899, 919, 1005, 1091], 1884: [20, 96, 116, 206, 226, 690, 762, 901, 944, 964, 1069, 1139, 1159, 1245, 1331] },
      combo : { 1100: 127, 1244: 133, 1404: 133, 1884: 133 },
      slider: { 1100: 200, 1244: 200, 1404: 213, 1884: 453 },
    },
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
        return { slicer, slicerHint: QtFontMetrics.widest(names, QtFontMetrics.APP, QtFontMetrics.boundingWidth) + 30, chooser, chooserHint: QtFontMetrics.widest(titles, QtFontMetrics.APP, QtFontMetrics.boundingWidth) + 30 };
      });
      const sources = ["js/tomovis_widgets.js", "js/tomovis_mpl.js", "js/tomovis_pg_export.js"].map((file) => this.source(file)).join("\n");
      const copies  = (sources.match(/Math\.max\([^\n]*(horizontalAdvance|boundingWidth)/g) || []).length;
      const users   = (sources.match(/QtFontMetrics\.widest\(/g) || []).length;

      R.equal([seen.slicer, seen.chooser], [seen.slicerHint, seen.chooserHint], "combo widths against Qt 5.15's bounding width plus 30");
      R.equal([copies, users, sources.includes("comboHint"), sources.includes("COMBO_CHROME")], [0, 3, false, false], "inline width-hint copies, and the combo, spin box and Export list callers of QtFontMetrics.widest");
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

  async lookInPopup() {
    await this.run.check("NEW-1", "the Look in popup opens in Qt's popup mode: 32 px rows, every place listed, the current folder over the combo, the icon and text at Qt's offsets", async () => {
      await this.fresh();
      await H.menu(this.page, "File", "Import", "npy");
      await this.page.waitForSelector(".tv-filedialog[data-dir]");
      await this.page.fill(".tv-filedialog__name", this.inputs);
      await this.page.press(".tv-filedialog__name", "Enter");
      await this.page.waitForFunction((d) => document.querySelector(".tv-filedialog").dataset.dir === d, this.inputs);
      await this.page.click(".tv-filedialog__lookin");
      const seen = await this.T(() => {
        const popup = document.querySelector(".tv-filedialog__lookinpopup");
        const p     = popup.getBoundingClientRect();
        const combo = document.querySelector(".tv-filedialog__lookin").getBoundingClientRect();
        const rows  = [...popup.querySelectorAll(".tv-combo__option")];
        const first = rows[0];
        const range = document.createRange();
        range.selectNodeContents(first.lastChild);
        return { top: Math.round(p.top - combo.top), height: Math.round(p.height), rows: rows.map((r) => Math.round(r.getBoundingClientRect().height)), icon: Math.round(first.querySelector(".tv-filedialog__icon").getBoundingClientRect().left - p.left), text: Math.round(range.getBoundingClientRect().left - p.left), hot: rows.findIndex((r) => r.classList.contains("is-hot")) };
      });
      await this.page.keyboard.press("Escape");
      await this.page.click(".tv-filedialog .tv-filedialog__cancel");

      R.equal([seen.top, seen.hot, seen.rows.every((h) => h === 32), seen.height], [0, 0, true, 32 * seen.rows.length + 2], "popup over the combo with 32 px rows and a 1 px frame");
      R.assert(Math.abs(seen.icon - 13) <= 1 && seen.text === 37, `icon at ${seen.icon} and text at ${seen.text}, Qt's 16 px icon spans 12..27 and its text starts at 37`);
      return `${seen.rows.length} rows of 32 px, ${seen.height} px tall, opened over the combo`;
    });
  }

  async computerPlace() {
    await this.run.check("NEW-2 NEW-3", "after Computer and Cancel the next dialog starts in the launch folder, as Qt's empty lastVisited does; Recent Places is written as the dialog closes and README D-4 says why", async () => {
      await this.fresh();
      await this.T(() => window.localStorage.removeItem("tomovis.fileDialogHistory"));
      await H.menu(this.page, "File", "Import", "npy");
      await this.page.waitForSelector(".tv-filedialog[data-dir]");
      const home = await this.T(() => document.querySelector(".tv-filedialog").dataset.dir);
      await this.page.fill(".tv-filedialog__name", this.inputs);
      await this.page.press(".tv-filedialog__name", "Enter");
      await this.page.waitForFunction((d) => document.querySelector(".tv-filedialog").dataset.dir === d, this.inputs);
      await this.page.click(".tv-filedialog .tv-filedialog__cancel");

      await H.menu(this.page, "File", "Import", "npy");
      await this.page.waitForSelector(".tv-filedialog[data-dir]");
      const afterInputs = await this.T(() => document.querySelector(".tv-filedialog").dataset.dir);
      await this.page.click(".tv-filedialog__lookin");
      const recent = await this.T(() => [...document.querySelectorAll(".tv-filedialog__lookinpopup .tv-combo__option")].map((o) => o.textContent));
      await this.page.keyboard.press("Escape");
      await this.page.locator(".tv-filedialog__place", { hasText: "Computer" }).click();
      await this.page.waitForFunction(() => document.querySelector(".tv-filedialog").dataset.dir === "computer:");
      await this.page.click(".tv-filedialog .tv-filedialog__cancel");

      await H.menu(this.page, "File", "Import", "npy");
      await this.page.waitForSelector(".tv-filedialog[data-dir]");
      const afterComputer = await this.T(() => document.querySelector(".tv-filedialog").dataset.dir);
      await this.page.click(".tv-filedialog .tv-filedialog__cancel");

      const d4 = fs.readFileSync(path.join(REPO, "webui/tomovis/README.md"), "utf-8").split("- **D-4.**")[1].split("- **D-7.**")[0].replace(/\s+/g, " ");
      R.equal([afterInputs, afterComputer], [this.inputs, home], "start folders after a cancel in inputs and after Computer");
      R.equal(recent.slice(recent.indexOf("Recent Places")), ["Recent Places", this.inputs], "Recent Places right after the first dialog closed");
      R.assert(d4.includes("Browsing to Computer") && d4.includes("PyQt deletes it") && !d4.includes("only when the window closes"), "README D-4 explains the Computer start folder and when Qt writes Recent Places");
      return `after inputs: ${afterInputs}; after Computer: ${afterComputer}`;
    });
  }

  async plotRow() {
    await this.run.check("LF-08", "the Plot row is laid out by Qt's grid algorithm with Qt's label widths and a 17 px 133x32 combo: every control at the original's x at 1100, 1244, 1404 and 1884 px", async () => {
      await this.fresh(1180, 916);
      await this.load();
      const style = await this.page.addStyleTag({ content: " " });
      const qt    = FinalFinishChecks.QT.plotRow;
      const off   = [];
      for (const [width, height, vw, vh] of [[1100, 880, 1180, 916], [1244, 880, 1280, 916], [1404, 880, 1440, 916], [1884, 1044, 1920, 1080]]) {
        await style.evaluate((node, size) => { node.textContent = `.tv-window { width: ${size[0]}px !important; height: ${size[1]}px !important; min-height: 0 !important; flex: none !important; }`; }, [width, height]);
        await this.page.setViewportSize({ width: vw, height: vh });
        await this.page.waitForTimeout(300);
        const got = await this.T((names) => {
          const win  = document.querySelector(".tv-window").getBoundingClientRect();
          const row  = document.querySelector("#tv-panel-plot .tv-plot__controls");
          const kids = [...row.children].filter((e) => !e.classList.contains("tv-stretch") && !e.classList.contains("tv-plot__spacer"));
          const top  = row.getBoundingClientRect().top;
          return { x: kids.map((e) => Math.round(e.getBoundingClientRect().left - win.left)), tops: kids.map((e) => Math.round(e.getBoundingClientRect().top - top)), combo: Math.round(document.querySelector('[data-widget="tab2ComboBox"]').getBoundingClientRect().width), comboFont: getComputedStyle(document.querySelector('[data-widget="tab2ComboBox"]')).fontSize, slider: Math.round(document.querySelector('[data-widget="tab2Slider"]').getBoundingClientRect().width), height: Math.round(document.querySelector('[data-widget="tab2ComboBox"]').getBoundingClientRect().height) };
        }, qt.names);
        if (JSON.stringify([got.x, got.tops, got.combo, got.slider, got.height, got.comboFont]) !== JSON.stringify([qt.x[width], qt.tops, qt.combo[width], qt.slider[width], 32, "17px"])) off.push(`${width}: ${JSON.stringify(got)}`);
      }
      await style.evaluate((node) => node.remove());
      R.assert(off.length === 0, off.join("\n"));
      return "x, offsets, combo and slider widths equal the original at four window widths";
    });
  }

  async noDimming() {
    await this.run.check("LS-15", "message boxes and the file dialog dim nothing behind them, as Qt does, and still refuse clicks on the window", async () => {
      await this.fresh();
      const point = await this.T(() => { const r = document.querySelector(".tv-slicer__label").getBoundingClientRect(); return { x: Math.round(r.left + 4), y: Math.round(r.top + r.height / 2) }; });
      const pixel = async () => { const shot = await this.page.screenshot({ clip: { x: point.x, y: point.y, width: 1, height: 1 } }); return shot.toString("base64"); };
      const before = await pixel();
      await this.T(() => { window.TomoVisMessageBox.show({ level: "warning", title: "No data", text: "There is no data loaded to save.", layer: window.app.tomovisPage.ctx.layer }); });
      await this.page.waitForSelector(".tv-messagebox");
      const boxed = { pixel: await pixel(), top: await this.T((p) => document.elementFromPoint(p.x, p.y).className, point), scrim: await this.T(() => getComputedStyle(document.querySelector(".tv-modal__scrim")).backgroundColor) };
      await this.page.keyboard.press("Escape");
      await H.menu(this.page, "File", "Import", "npy");
      await this.page.waitForSelector(".tv-filedialog[data-dir]");
      const dialog = { pixel: await pixel(), top: await this.T((p) => document.elementFromPoint(p.x, p.y).className, point) };
      await this.page.click(".tv-filedialog .tv-filedialog__cancel");

      const css = this.source("css/tomovis.css");
      R.equal([boxed.pixel === before, dialog.pixel === before, boxed.scrim], [true, true, "rgba(0, 0, 0, 0)"], "window pixel unchanged behind the message box and the file dialog");
      R.equal([boxed.top, dialog.top], ["tv-modal__scrim", "tv-modal__scrim"], "the clear scrim still takes the clicks");
      R.equal(css.includes("--tv-scrim"), false, "scrim colour token gone");
      return "nothing dimmed, clicks refused";
    });
  }

  async axisFields() {
    await this.run.check("NEW-4", "a field shows its start when Qt's line edit fits the text and its end when Qt's overflows: -22.11 keeps its sign; 413.62 is 3 px too wide for Qt's 51 px line and scrolls in both", async () => {
      await this.fresh();
      await H.menu(this.page, "File", "Import", "hd5");
      await H.chooseFile(this.page, FinalFinishChecks.REALISTIC);
      const c = await this.T(() => { const iv = window.app.tomovisPage.views[0].views.imv1_1; const q = iv.view.mapViewToScene(60, 40); const r = iv.scene.el.getBoundingClientRect(); return { x: r.left + q.x, y: r.top + q.y }; });
      await this.page.mouse.click(c.x, c.y, { button: "right" });
      await this.page.locator(".tv-menu .tv-menu__item", { hasText: "X axis" }).first().hover();
      await this.page.waitForSelector(".tv-menu .tv-pg-axisctrl");
      await this.page.waitForTimeout(300);
      const fields = await this.T(() => [...document.querySelectorAll(".tv-menu .tv-pg-axisctrl .tv-line")].map((i) => [i.value, i.scrollLeft, Math.round(QtFontMetrics.horizontalAdvance(i.value, QtFontMetrics.APP)), i.offsetWidth]));
      await this.page.locator(".tv-menu").last().screenshot({ path: path.join(this.out, "new4_axis_submenu.png") });
      await this.page.keyboard.press("Escape");
      await this.page.keyboard.press("Escape");

      await this.page.fill('[data-widget="tab1QLineEdit1"]', "123456789.1234");
      await this.page.locator('[data-widget="tab1QLineEdit2"]').focus();
      const roi = await this.T(() => { const i = document.querySelector('[data-widget="tab1QLineEdit1"]'); return [i.value, i.scrollLeft > 0]; });

      const [low, high] = fields;
      R.equal([low[0], low[1], low[2] + 1 <= low[3] - 6], ["-22.11", 0, true], `min field fits in Qt and shows its start: ${JSON.stringify(low)}`);
      R.equal([high[0], high[2] + 1 > high[3] - 6, high[1] > 0], ["413.62", true, true], `max field overflows Qt's line and shows its end: ${JSON.stringify(high)}`);
      R.equal(roi, ["123456789.1234", false], "a typed ROI value keeps the browser's own scrolling while edited");
      return fields.slice(0, 2).map(([value]) => value).join(" / ");
    });
  }

  async exportParams() {
    await this.run.check("NEW-7", "the Export parameter tree shows values as text with a 20x20 reset button, as pyqtgraph's items do, and swaps in the editor only for the selected row; check boxes and colour buttons stay shown", async () => {
      await this.fresh();
      await H.menu(this.page, "File", "Import", "hd5");
      await H.chooseFile(this.page, FinalFinishChecks.REALISTIC);
      const c = await this.T(() => { const iv = window.app.tomovisPage.views[0].views.imv1_1; const q = iv.view.mapViewToScene(60, 40); const r = iv.scene.el.getBoundingClientRect(); return { x: r.left + q.x, y: r.top + q.y }; });
      await this.page.mouse.click(c.x, c.y, { button: "right" });
      await this.page.locator(".tv-menu .tv-menu__item", { hasText: "Export..." }).click();
      await this.page.waitForSelector(".tv-pg-export");
      const rows = () => this.T(() => [...document.querySelectorAll(".tv-pg-export__param")].map((row) => {
        const base   = row.getBoundingClientRect();
        const editor = row.children[1];
        const label  = row.querySelector(".tv-pg-export__display");
        const reset  = row.querySelector(".tv-pg-export__default").getBoundingClientRect();
        return { name: row.children[0].textContent, editor: !editor.hidden, label: label.hidden ? null : label.textContent, reset: [Math.round(reset.left - base.left), Math.round(reset.top - base.top), reset.width, reset.height], selected: row.classList.contains("is-selected") };
      }));
      const formats = {};
      for (const name of ["CSV of original plot data", "Image File (PNG, TIF, JPG, ...)"]) {
        await this.page.locator(".tv-pg-export__formats .tv-pg-export__row", { hasText: name }).click();
        formats[name] = await rows();
      }
      await this.page.locator(".tv-pg-export__param", { hasText: "width" }).click({ position: { x: 30, y: 16 } });
      const selected = await rows();
      await this.page.locator('.tv-pg-export__param:has-text("width") .tv-spin__input').fill("450");
      await this.page.keyboard.press("Enter");
      await this.page.locator(".tv-pg-export__group").click();
      const edited = await rows();
      await this.page.locator('.tv-pg-export__param:has-text("width") .tv-pg-export__default').click();
      const reset = await rows();
      await this.page.locator(".tv-pg-export").screenshot({ path: path.join(this.out, "new7_export_params.png") });
      await this.page.click('.tv-pg-export .tv-button:text-is("Close")');

      const csv   = formats["CSV of original plot data"];
      const image = formats["Image File (PNG, TIF, JPG, ...)"];
      const brief = (list) => list.map((r) => [r.name, r.editor, r.label]);
      R.equal(brief(csv), [["separator", false, "comma"], ["precision", false, "10"], ["columnMode", false, "(x,y) per plot"]], "CSV rows show text, as the original's display labels");
      R.equal(brief(image), [["width", false, "900"], ["height", false, "340"], ["antialias", true, null], ["background", true, null], ["invertValue", true, null]], "Image rows: numbers as text, check boxes and colour button shown");
      R.equal(image.map((r) => r.reset), Array(5).fill([215, 6, 20, 20]), "reset buttons 20x20 at the original's viewport x 215 and 6 px below the row top");
      R.equal([selected[0].selected, selected[0].editor, selected[0].label, selected[1].editor], [true, true, null, false], "the selected width row shows its spin box");
      R.equal([edited[0].label, edited[1].label, edited[0].editor], ["450", "170", false], "width edited to 450, height follows, editor hidden after deselecting");
      R.equal([reset[0].label, reset[1].label], ["900", "340"], "reset puts width back to its default and height follows");
      return `CSV ${csv.map((r) => r.label).join(", ")}; Image ${image[0].label}x${image[1].label}`;
    });
  }

  async checkedTools() {
    await this.run.check("COL-01", "checked matplotlib tools use the same TomoVic tokens as every other checked TomoVis button; a held tool keeps the sunken well", async () => {
      await this.fresh();
      await this.load();
      await this.page.click('[data-widget="tab1PlotButton"]');
      await H.waitIdle(this.page);
      await this.page.click('#tv-panel-plot .tv-mpl-tool[data-method="pan"]');
      await H.waitIdle(this.page);
      await this.page.mouse.move(5, 5);
      await this.page.waitForTimeout(200);
      const looks = await this.T(() => {
        const look = (el) => { const st = getComputedStyle(el); return [st.borderTopColor, st.backgroundColor]; };
        const tool = document.querySelector('#tv-panel-plot .tv-mpl-tool[data-method="pan"]');
        const ref  = document.createElement("button");
        ref.className = "tv-button is-checked";
        document.querySelector("#tv-panel-plot").append(ref);
        const out = { tool: look(tool), button: look(ref), checked: tool.classList.contains("is-checked") };
        ref.remove();
        return out;
      });
      await this.page.click('#tv-panel-plot .tv-mpl-tool[data-method="pan"]');
      await H.waitIdle(this.page);
      R.equal([looks.checked, looks.tool], [true, looks.button], "checked Pan against a checked TomoVis push button");
      R.assert(this.source("css/tomovis_plot.css").includes(".tv-mpl-tool:not(:disabled):active { background: var(--tv-well)"), "held tools keep the sunken well");
      return `border ${looks.tool[0]}, fill ${looks.tool[1]}`;
    });
  }

  async folderFailures() {
    await this.run.check("CR-05", "a Create New Folder or rename that fails on the disk is logged with its cause, and the browser still gets Qt's answers", async () => {
      await this.fresh();
      const scratch = path.join(this.out, "cr05");
      fs.mkdirSync(scratch, { recursive: true });
      const answers = await this.T(async (dir) => {
        const sid  = window.app.tomovisPage.ctx.session.sid;
        const post = (route, body) => fetch(`/api/tomovis/${route}`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ sid, ...body }) }).then((r) => r.json());
        return { mkdir: await post("mkdir", { path: "/" }), rename: await post("rename", { path: dir, old: "missing_entry", new: "renamed" }) };
      }, scratch);
      const lines = (await this.T(() => fetch("/api/server-log?limit=40").then((r) => r.json()))).lines.map((line) => `${line.level} ${line.message}`);

      R.equal([answers.mkdir.ok, answers.rename.ok, answers.rename.title], [false, false, "Invalid filename"], "answers to the browser");
      R.assert(lines.some((line) => line.startsWith("WARN TomoVis: Create New Folder in / failed:") && line.includes("Permission denied")), `mkdir failure not logged: ${lines.slice(-4).join(" | ")}`);
      R.assert(lines.some((line) => line.startsWith(`WARN TomoVis: renaming ${scratch}/missing_entry to renamed failed:`) && line.includes("No such file")), `rename failure not logged: ${lines.slice(-4).join(" | ")}`);
      return "both failures logged at warning level";
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
    if (this.wanted("lookin")) await this.lookInPopup();
    if (this.wanted("computer")) await this.computerPlace();
    if (this.wanted("row")) await this.plotRow();
    if (this.wanted("scrim")) await this.noDimming();
    if (this.wanted("axis")) await this.axisFields();
    if (this.wanted("export")) await this.exportParams();
    if (this.wanted("tools")) await this.checkedTools();
    if (this.wanted("folders")) await this.folderFailures();

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
