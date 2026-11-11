import fs from "node:fs";
import path from "node:path";
import { execFileSync } from "node:child_process";

import { TomoVisHarness as H, TomoVisCheckRun as Run, REPO } from "./harness.mjs";

class PlotProfileChecks {
  static AGENT        = "plotprofile";
  static FIXTURES     = path.join(REPO, "logs/tomovis_port/fixtures");
  static OBLIQUE      = ["30", "40", "12", "330", "0", "0"];
  static VIEWPORT     = { width: 1180, height: 916 };
  static WINDOW       = ".tv-window { width: 1100px !important; height: 880px !important; min-height: 0 !important; flex: none !important; }";
  static ROW          = ["Normalize", "tab2ChkBox1", "Histogram\nequalization", "tab2ChkBox2", "tab2Slider", "spacer", "Colormap", "tab2ComboBox", "X [m]", "tab2ChkBox3", "tab2SpinBox", "Full View", "tab2ChkBox4", "tab2AxesButton", "tab2PlotButton", "tab2ClearButton", "stretch"];
  static TOOLS        = ["Home", "Back", "Forward", "Pan", "Zoom", "Subplots", "Customize", "Save"];
  static TOOLTIPS     = ["Reset original view", "Back to previous view", "Forward to next view", "Left button pans, Right button zooms\nx/y fixes axis, CTRL fixes aspect", "Zoom to rectangle\nx/y fixes axis", "Configure subplots", "Edit axis, curve and image parameters", "Save the figure"];
  static QT_PYTHON    = process.env.TOMOVIS_PYTHON || path.join(process.env.HOME, "miniconda3/envs/tomovis/bin/python");
  static FLOATS       = ["", "-", "+", "1", "1.", ".5", ".", "1e", "1e5", "1E-3", "-2.5e+3", "1,000", ",1", "1,000.5", "1.5,0", "1.2.3", "1e5e", "e5", "abc", "1 ", " 1", "0x10", "--1", "1-", "inf", "1e999", "+.5e-2"];
  static COLORS       = ["red", "Red", "C0", "C13", "tab:orange", "tab:grey", "k", "w", "#abc", "#abcd", "#11223344", "#1234567", "0.5", "0.25", "1", "1.5", "none", "rebeccapurple", "notacolor", "#0f0", "darkslategrey", ""];
  static QT_CODE      = [
    "import json, os, sys, warnings",
    "os.environ['QT_QPA_PLATFORM'] = 'offscreen'",
    "warnings.simplefilter('ignore')",
    "from PyQt5 import QtCore, QtGui, QtWidgets",
    "app = QtWidgets.QApplication([])",
    "import matplotlib.colors as mcolors",
    "from matplotlib.backends.qt_editor import _formlayout",
    "edit = QtWidgets.QLineEdit()",
    "validator = QtGui.QDoubleValidator(edit)",
    "validator.setLocale(QtCore.QLocale('C'))",
    "states = {0: 'Invalid', 1: 'Intermediate', 2: 'Acceptable'}",
    "floats = [states[int(validator.validate(text, 0)[0])] for text in json.loads(sys.argv[1])]",
    "colors = [mcolors.to_hex(_formlayout.to_qcolor(text).getRgbF(), keep_alpha=True) for text in json.loads(sys.argv[2])]",
    "print(json.dumps({'floats': floats, 'colors': colors}))",
  ].join("\n");
  static EXPECTED_400 = ["/api/tomovis/script/slicer", "/api/tomovis/fs?path=%2Ftomovis_port_missing_directory&"];
  static PLOT_ROW     = ["tab2ChkBox1", "tab2ChkBox2", "tab2Slider", "tab2ComboBox", "tab2ChkBox3", "tab2SpinBox", "tab2ChkBox4", "tab2AxesButton", "tab2PlotButton", "tab2ClearButton"];

  constructor(options) {
    this.options = options;
    this.run     = new Run("plot");
    this.errors  = [];
    this.pages   = [];
  }

  async open(route = "tomovis") {
    const launched = await H.launch({ port: this.options.port, gl: this.options.gl, viewport: PlotProfileChecks.VIEWPORT });
    this.pages.push(launched);
    const page = launched.page;
    page.on("response", (response) => {
      if (response.status() >= 400) launched.failures.push(`${response.status()} ${response.url()}`);
    });
    launched.failures = [];
    if (route !== "tomovis") {
      await page.goto(`${launched.base}/#/${route}`);
      return page;
    }
    await H.openTomoVis(page);
    await page.addStyleTag({ content: PlotProfileChecks.WINDOW });
    await page.evaluate(() => {
      window.__mplOps = [];
      const ctx      = window.app.tomovisPage.ctx;
      const original = ctx.session.figure.bind(ctx.session);
      ctx.session.figure = (id, op, payload, options) => {
        window.__mplOps.push({ id, op, payload });
        return original(id, op, payload, options);
      };
    });
    return page;
  }

  async instrumentScripts(page) {
    await page.waitForFunction(() => window.app.tomovisScriptsPage && window.app.tomovisScriptsPage.ctx && window.app.tomovisScriptsPage.views.length > 0, null, { timeout: 30000 });
    await page.evaluate(() => {
      window.__mplOps = [];
      const ctx      = window.app.tomovisScriptsPage.ctx;
      const original = ctx.session.figure.bind(ctx.session);
      ctx.session.figure = (id, op, payload, options) => {
        window.__mplOps.push({ id, op, payload });
        return original(id, op, payload, options);
      };
    });
  }

  async settle(page) {
    await H.waitIdle(page);
    await page.evaluate(async () => {
      const owner = window.app.tomovisPage.views.length ? window.app.tomovisPage : window.app.tomovisScriptsPage;
      for (const view of owner.views) {
        if (view && view.figure) await view.figure.drawing;
      }
    });
    await page.waitForTimeout(80);
  }

  async send(page, event) {
    await page.evaluate((e) => window.app.tomovisPage.ctx.session.send(e), event);
    await this.settle(page);
  }

  async state(page, which) {
    return page.evaluate((id) => {
      const owner = id === "script_slicer" ? window.app.tomovisScriptsPage : window.app.tomovisPage;
      const view  = owner.views.map((v) => v && v.figure).find((f) => f && f.id === id);
      const data  = view.canvas.width && view.canvas.height ? view.context.getImageData(0, 0, view.canvas.width, view.canvas.height).data : new Uint8ClampedArray(0);
      let hash    = 2166136261;
      let white   = true;
      for (let i = 0; i < data.length; i += 1) {
        hash = Math.imul(hash ^ data[i], 16777619);
        if (data[i] !== 255) white = false;
      }
      const band = view.band.context.getImageData(0, 0, view.band.canvas.width, view.band.canvas.height).data;
      let banded = 0;
      for (let i = 3; i < band.length; i += 4) banded += band[i] ? 1 : 0;
      const tools = view.toolbar ? view.toolbar.buttons : {};
      return {
        frames  : view.frames,
        hash    : (hash >>> 0).toString(16),
        white,
        width   : view.canvas.width,
        height  : view.canvas.height,
        wrap    : [view.wrap.clientWidth, view.wrap.clientHeight],
        message : view.toolbar ? view.toolbar.label.textContent : null,
        back    : tools.back ? !tools.back.disabled : null,
        forward : tools.forward ? !tools.forward.disabled : null,
        pan     : tools.pan ? tools.pan.classList.contains("is-checked") : null,
        zoom    : tools.zoom ? tools.zoom.classList.contains("is-checked") : null,
        cursor  : view.wrap.style.cursor,
        banded,
      };
    }, which);
  }

  async controls(page) {
    return page.evaluate((names) => {
      const controls = window.app.tomovisPage.ctx.session.snapshot.controls;
      return Object.fromEntries(names.map((name) => [name, controls[name]]));
    }, [...PlotProfileChecks.PLOT_ROW, "tab3ClearButton", "tabWidget"]);
  }

  async canvasBox(page, panel) {
    return page.locator(`${panel} .tv-mpl-canvaswrap`).boundingBox();
  }

  async hover(page, panel, fx, fy) {
    const box = await this.canvasBox(page, panel);
    await page.mouse.move(box.x + box.width * fx - 2, box.y + box.height * fy);
    await page.mouse.move(box.x + box.width * fx, box.y + box.height * fy);
    await this.settle(page);
    return (await this.state(page, panel === "#tv-panel-plot" ? "plot" : "profile")).message;
  }

  async drag(page, panel, from, to, button = "left", inspect = null) {
    const box = await this.canvasBox(page, panel);
    await page.mouse.move(box.x + box.width * from[0], box.y + box.height * from[1]);
    await page.mouse.down({ button });
    await page.mouse.move(box.x + box.width * (from[0] + to[0]) / 2, box.y + box.height * (from[1] + to[1]) / 2, { steps: 4 });
    await page.mouse.move(box.x + box.width * to[0], box.y + box.height * to[1], { steps: 4 });
    await this.settle(page);
    const during = inspect ? await inspect() : null;
    await page.mouse.up({ button });
    await this.settle(page);
    return during;
  }

  async shot(page, name, original, element = ".tv-window") {
    await this.settle(page);
    await H.shot(page, name, PlotProfileChecks.AGENT, { element });
    if (original && process.env.TOMOVIS_ORIGINAL_SHOTS) H.compareShot(name, original, PlotProfileChecks.AGENT);
  }

  async importRealistic(page, kind, file) {
    await H.menu(page, "File", "Import", kind);
    await H.chooseFile(page, path.join(PlotProfileChecks.FIXTURES, file));
    for (const [i, text] of PlotProfileChecks.OBLIQUE.entries()) await this.send(page, { type: "text", widget: `tab1QLineEdit${i + 1}`, text });
    await this.send(page, { type: "click", widget: "tab1SetButton" });
    await this.send(page, { type: "click", widget: "tab1PlotButton" });
  }

  async click(page, selector) {
    await page.click(selector);
    await this.settle(page);
  }

  async layout(page) {
    await this.run.check("F-060", "Plot row holds the original controls in order, only X [m] enabled at start (Q-040)", async () => {
      const row = await page.evaluate(() => [...document.querySelector(".tv-plot__controls").children].map((el) => el.dataset.widget || (el.classList.contains("tv-plot__spacer") ? "spacer" : el.classList.contains("tv-stretch") ? "stretch" : el.textContent)));
      Run.equal(row, PlotProfileChecks.ROW, "row order");
      const controls = await this.controls(page);
      const enabled  = PlotProfileChecks.PLOT_ROW.filter((name) => controls[name].enabled);
      Run.equal(enabled, ["tab2ChkBox3"], "enabled at start");
      const greyed = await page.evaluate(() => [...document.querySelectorAll(".tv-plot__controls [data-widget]")].filter((el) => el.classList.contains("is-disabled") || el.disabled).map((el) => el.dataset.widget));
      Run.equal(greyed, ["tab2ChkBox1", "tab2ChkBox2", "tab2Slider", "tab2ComboBox", "tab2SpinBox", "tab2ChkBox4", "tab2AxesButton", "tab2PlotButton", "tab2ClearButton"], "greyed widgets");
      const texts = await page.evaluate(() => ["tab2AxesButton", "tab2PlotButton", "tab2ClearButton"].map((name) => document.querySelector(`[data-widget="${name}"]`).textContent));
      Run.equal(texts, ["Axes", "Plot", "Clear"], "button texts");
      await this.click(page, '.tv-tab[data-tab="1"]');
      await this.shot(page, "02_startup_plot_no_data", "02_startup_plot_no_data.png");
      const state = await this.state(page, "plot");
      Run.assert(state.white && state.width === state.wrap[0] && state.height === state.wrap[1], `empty white canvas at its CSS size ${JSON.stringify(state)}`);
      return `row ${row.length} items, canvas ${state.width}x${state.height}`;
    });

    await this.run.check("F-130", "Toolbar icons, Qt tooltips, separators, Back/Forward disabled at start", async () => {
      const toolbar = await page.evaluate(() => {
        const bar = document.querySelector("#tv-panel-plot .tv-mpl-toolbar");
        return [...bar.children].map((el) => el.classList.contains("tv-mpl-toolbar__sep") ? "|" : el.classList.contains("tv-mpl-tool") ? [el.getAttribute("aria-label"), el.title, el.disabled] : "label");
      });
      const tools = toolbar.filter((item) => Array.isArray(item));
      Run.equal(tools.map((item) => item[0]), PlotProfileChecks.TOOLS, "tool order");
      Run.equal(tools.map((item) => item[1]), PlotProfileChecks.TOOLTIPS, "tooltips");
      Run.equal(toolbar.map((item) => Array.isArray(item) ? "b" : item).join(""), "bbb|bbbb|blabel", "separators and label");
      Run.equal(tools.filter((item) => item[2]).map((item) => item[0]), ["Back", "Forward"], "disabled at start");
      return "8 tools";
    });

    await this.run.check("F-134 form", "Float fields validate as Qt's QDoubleValidator (C locale) and colour texts normalise as ColorLayout does", async () => {
      const qt = JSON.parse(execFileSync(PlotProfileChecks.QT_PYTHON, ["-c", PlotProfileChecks.QT_CODE, JSON.stringify(PlotProfileChecks.FLOATS), JSON.stringify(PlotProfileChecks.COLORS)], { encoding: "utf-8" }));
      const js = await page.evaluate(([floats, colors]) => ({
        floats : floats.map((text) => new MplDoubleValidator().validate(text)),
        colors : colors.map((text) => {
          const parsed = MplColors.toRgba(text);
          return MplColors.toHex(parsed ? MplColors.quantize(parsed) : MplColors.INVALID);
        }),
      }), [PlotProfileChecks.FLOATS, PlotProfileChecks.COLORS]);
      Run.equal(js.floats, qt.floats, "QDoubleValidator states");
      Run.equal(js.colors, qt.colors, "ColorLayout texts");
      return `${qt.floats.length} float texts, ${qt.colors.length} colour texts`;
    });

    await this.run.check("F-080", "Profile tab: figure and a right-aligned Clear, disabled at start", async () => {
      await this.click(page, '.tv-tab[data-tab="2"]');
      const clear = await page.evaluate(() => {
        const button = document.querySelector('[data-widget="tab3ClearButton"]');
        const panel  = document.querySelector("#tv-panel-profile").getBoundingClientRect();
        const rect   = button.getBoundingClientRect();
        return { text: button.textContent, disabled: button.disabled, gap: Math.round(panel.right - rect.right) };
      });
      Run.assert(clear.text === "Clear" && clear.disabled && clear.gap < 16, `clear ${JSON.stringify(clear)}`);
      await this.shot(page, "03_startup_profile_no_data", "03_startup_profile_no_data.png");
      await this.click(page, '.tv-tab[data-tab="0"]');
      return JSON.stringify(clear);
    });
  }

  async singleSequence(page) {
    await this.run.check("F-061", "Slicer Plot on the realistic crop draws the mono plot at canvas size (shot 20)", async () => {
      await this.importRealistic(page, "hd5", "realistic_traun_hv.hd5");
      const controls = await this.controls(page);
      Run.equal(controls.tabWidget.index, 1, "Plot tab current");
      const state = await this.state(page, "plot");
      Run.assert(state.frames > 1 && !state.white && state.width === state.wrap[0], `frame ${JSON.stringify(state)}`);
      await this.shot(page, "20_plot_half_height", "20_plot_half_height.png");
      return `${state.frames} frames, ${state.width}x${state.height}`;
    });

    await this.run.check("F-068", "Full View fills the figure (shot 21)", async () => {
      const before = await this.state(page, "plot");
      await this.click(page, '[data-widget="tab2ChkBox4"]');
      const after = await this.state(page, "plot");
      Run.assert(after.hash !== before.hash, "figure changed");
      await this.shot(page, "21_plot_full_view", "21_plot_full_view.png");
    });

    await this.run.check("F-064", "Normalize rescales every column (shot 22)", async () => {
      await this.click(page, '[data-widget="tab2ChkBox1"]');
      await this.shot(page, "22_plot_normalized", "22_plot_normalized.png");
      Run.equal((await this.controls(page)).tab2ChkBox1.checked, true, "Normalize checked");
    });

    await this.run.check("F-065", "Histogram equalization with 6 bins from the slider keys (shot 23)", async () => {
      await this.click(page, '[data-widget="tab2ChkBox2"]');
      await page.focus('[data-widget="tab2Slider"]');
      for (let i = 0; i < 4; i += 1) await page.keyboard.press("ArrowRight");
      await this.settle(page);
      const controls = await this.controls(page);
      Run.equal([controls.tab2ChkBox2.checked, controls.tab2Slider.enabled, controls.tab2Slider.value], [true, true, 6], "equalization, slider");
      await this.shot(page, "23_plot_hist_eq_6_bins", "23_plot_hist_eq_6_bins.png");
    });

    await this.run.check("F-067", "X [m] puts the spin box at the midpoint, greys equalization, draws the white line (shot 24)", async () => {
      await this.click(page, '[data-widget="tab2ChkBox2"]');
      await this.click(page, '[data-widget="tab2ChkBox3"]');
      const controls = await this.controls(page);
      const text     = await page.inputValue('[data-widget="tab2SpinBox"] input');
      Run.assert(controls.tab2SpinBox.enabled && controls.tab2PlotButton.enabled && !controls.tab2ChkBox2.enabled, `enables ${JSON.stringify(controls)}`);
      Run.equal(text, controls.tab2SpinBox.value.toFixed(2), "spin text");
      Run.equal(Number(text), Number(((controls.tab2SpinBox.minimum + controls.tab2SpinBox.maximum) / 2).toFixed(2)), "midpoint");
      await this.shot(page, "24_plot_x_line", "24_plot_x_line.png");
      return `X [m] ${text} in ${controls.tab2SpinBox.minimum}..${controls.tab2SpinBox.maximum}`;
    });

    await this.run.check("F-069", "Axes Settings dialog fields, 6 decimals, new labels redraw (shots 25, 26)", async () => {
      await page.click('[data-widget="tab2AxesButton"]');
      await page.waitForSelector(".tv-axes-dialog");
      const dialog = await page.evaluate(() => {
        const el = document.querySelector(".tv-axes-dialog");
        return {
          title   : el.querySelector(".tv-modal__title").textContent,
          labels  : [...el.querySelectorAll(".tv-axes-dialog__grid > label")].map((l) => l.textContent),
          values  : [...el.querySelectorAll("[data-field] input, input[data-field]")].map((i) => i.value),
          fields  : [...el.querySelectorAll("[data-field]")].map((f) => f.dataset.field),
          buttons : [...el.querySelectorAll(".tv-modal__buttons button")].map((b) => b.textContent),
          focused : document.activeElement === el.querySelector('[data-field="x_label"]'),
        };
      });
      Run.equal(dialog.title, "Axes Settings", "title");
      Run.equal(dialog.labels, ["X label", "Z label", "X min", "X max", "Z min", "Z max"], "labels");
      Run.equal(dialog.buttons, ["OK", "Cancel"], "buttons");
      Run.assert(dialog.values[0] === "Projected distance along ROI [m]" && dialog.values[1] === "Elevation [m]", `labels ${dialog.values}`);
      Run.assert(dialog.values.slice(2).every((v) => /^-?\d+\.\d{6}$/.test(v)), `six decimals ${dialog.values}`);
      Run.assert(dialog.focused, "X label focused");
      await page.fill('.tv-axes-dialog [data-field="x_label"]', "Distance [m]");
      await page.fill('.tv-axes-dialog [data-field="z_label"]', "Height [m]");
      await H.shot(page, "25_axes_dialog", PlotProfileChecks.AGENT, { element: ".tv-axes-dialog" });
      if (process.env.TOMOVIS_ORIGINAL_SHOTS) H.compareShot("25_axes_dialog", "25_axes_dialog.png", PlotProfileChecks.AGENT);
      await page.click('.tv-axes-dialog .tv-modal__buttons button:text-is("OK")');
      await this.settle(page);
      const attributes = await page.evaluate(() => window.app.tomovisPage.ctx.session.snapshot.attributes);
      Run.equal([attributes.x_label_view, attributes.z_label], ["Distance [m]", "Height [m]"], "labels applied");
      await this.shot(page, "26_plot_after_axes", "26_plot_after_axes.png");
      return dialog.values.join(" | ");
    });

    await this.run.check("F-066", "Colormap viridis from the popup with X [m] on does not replot (Q-042, shot 27)", async () => {
      const before = await this.state(page, "plot");
      await page.click('[data-widget="tab2ComboBox"]');
      await page.locator(".tv-combo__popup .tv-combo__option", { hasText: /^viridis$/ }).click();
      await this.settle(page);
      const after    = await this.state(page, "plot");
      const controls = await this.controls(page);
      Run.equal([controls.tab2ComboBox.text, after.hash === before.hash], ["viridis", true], "viridis selected, figure unchanged");
      await this.shot(page, "27_plot_viridis", "27_plot_viridis.png");
    });

    await this.run.check("F-070", "Plot (profile) opens the Profile tab with the normalized profile (shot 30)", async () => {
      await this.click(page, '[data-widget="tab2PlotButton"]');
      const controls = await this.controls(page);
      const state    = await this.state(page, "profile");
      Run.assert(controls.tabWidget.index === 2 && controls.tab3ClearButton.enabled && !state.white, `profile ${JSON.stringify(controls.tabWidget)}`);
      await this.shot(page, "30_profile_single_normalized", "30_profile_single_normalized.png");
    });

    await this.run.check("F-081", "Raw profile after Normalize off (shot 31)", async () => {
      await this.click(page, '.tv-tab[data-tab="1"]');
      const before = await this.state(page, "profile");
      await this.click(page, '[data-widget="tab2ChkBox1"]');
      await this.click(page, '[data-widget="tab2PlotButton"]');
      const after = await this.state(page, "profile");
      Run.assert(after.hash !== before.hash, "profile redrawn");
      await this.shot(page, "31_profile_single_raw", "31_profile_single_raw.png");
      await this.click(page, '.tv-tab[data-tab="1"]');
    });
  }

  async navigation(page) {
    const panel = "#tv-panel-plot";
    const tool  = (method) => `${panel} .tv-mpl-tool[data-method="${method}"]`;
    const point = [0.45, 0.5];

    await this.run.check("F-132", "Cursor readout: two lines over the image, empty outside the Axes", async () => {
      const inside  = await this.hover(page, panel, ...point);
      const outside = await this.hover(page, panel, 0.02, 0.03);
      Run.assert(/^\(x, y\) = \(.+, .+\)\n\[.+\]$/.test(inside), `inside ${JSON.stringify(inside)}`);
      Run.equal(outside, "", "outside");
      return JSON.stringify(inside);
    });

    await this.run.check("F-130 zoom", "Zoom box with the dashed rubber band, Back, Forward and Home", async () => {
      const home = await this.hover(page, panel, ...point);
      await this.click(page, tool("zoom"));
      await this.hover(page, panel, ...point);
      let state = await this.state(page, "plot");
      Run.equal([state.zoom, state.pan, state.cursor], [true, false, "crosshair"], "zoom checked, crosshair");

      const banded = await this.drag(page, panel, [0.3, 0.3], [0.6, 0.6], "left", async () => (await this.state(page, "plot")).banded);
      state = await this.state(page, "plot");
      Run.assert(banded > 100 && state.banded === 0, `rubber band drawn ${banded} then removed ${state.banded}`);
      Run.equal([state.back, state.forward], [true, false], "history after zoom");
      const zoomed = await this.hover(page, panel, ...point);
      Run.assert(zoomed !== home, "readout changed by the zoom");

      await this.click(page, tool("back"));
      state = await this.state(page, "plot");
      Run.equal([state.back, state.forward, await this.hover(page, panel, ...point)], [false, true, home], "Back");
      await this.click(page, tool("forward"));
      Run.equal(await this.hover(page, panel, ...point), zoomed, "Forward");
      await this.click(page, tool("home"));
      Run.equal(await this.hover(page, panel, ...point), home, "Home");
      await this.click(page, tool("zoom"));
      state = await this.state(page, "plot");
      Run.equal([state.zoom, state.pan], [false, false], "zoom off");
      return `${home.split("\n")[0]} -> ${zoomed.split("\n")[0]}`;
    });

    await this.run.check("F-131", "Zoom ignores a 3 px drag; Pan drags and right-drag zooms", async () => {
      await this.click(page, tool("home"));
      const home = await this.hover(page, panel, ...point);
      await this.click(page, tool("zoom"));
      const before = await this.state(page, "plot");
      const box    = await this.canvasBox(page, panel);
      await page.mouse.move(box.x + box.width * 0.4, box.y + box.height * 0.4);
      await page.mouse.down();
      await page.mouse.move(box.x + box.width * 0.4 + 3, box.y + box.height * 0.4 + 2, { steps: 2 });
      await page.mouse.up();
      await this.settle(page);
      const after = await this.state(page, "plot");
      Run.equal([after.back, await this.hover(page, panel, ...point)], [before.back, home], "3 px drag ignored");
      await this.click(page, tool("zoom"));

      await this.click(page, tool("pan"));
      await this.hover(page, panel, ...point);
      let state = await this.state(page, "plot");
      Run.equal([state.pan, state.zoom, state.cursor], [true, false, "move"], "pan checked, move cursor");
      await this.drag(page, panel, [0.4, 0.4], [0.5, 0.45]);
      const panned = await this.hover(page, panel, ...point);
      Run.assert(panned !== home, "pan moved the view");
      await this.drag(page, panel, [0.5, 0.5], [0.6, 0.55], "right");
      const scaled = await this.hover(page, panel, ...point);
      Run.assert(scaled !== panned, "right drag zoomed");
      await this.click(page, tool("home"));
      await this.click(page, tool("pan"));
      state = await this.state(page, "plot");
      Run.equal([state.pan, await this.hover(page, panel, ...point)], [false, home], "pan off, home view");
    });

    await this.run.check("F-136", "Keys never reach the Plot figure (NoFocus canvas, no matplotlib keymap)", async () => {
      await this.hover(page, panel, ...point);
      const before = await this.state(page, "plot");
      await page.evaluate(() => { window.__mplOps.length = 0; });
      for (const key of ["g", "k", "l", "x", "h", "o"]) await page.keyboard.press(key);
      await this.settle(page);
      const ops   = await page.evaluate(() => window.__mplOps.filter((o) => o.op === "key").length);
      const after = await this.state(page, "plot");
      Run.equal([ops, after.hash === before.hash], [0, true], "no key op, figure unchanged");
    });

    await this.run.check("frames", "Diff frames composite to the server's full frame", async () => {
      const before = await this.state(page, "plot");
      await page.evaluate(() => window.app.tomovisPage.views[1].figure.refresh());
      await this.settle(page);
      const after = await this.state(page, "plot");
      Run.assert(after.frames > before.frames && after.hash === before.hash, `refresh frame ${before.hash} vs ${after.hash}`);
    });
  }

  async dialogs(page) {
    const tool = (method) => `#tv-panel-plot .tv-mpl-tool[data-method="${method}"]`;

    await this.run.check("F-133", "Configure subplots: Qt groups, keyboard tracking off, live apply, Reset, Export values, Tight layout", async () => {
      await page.click(tool("configure_subplots"));
      await page.waitForSelector(".tv-mpl-subplots .tv-mpl-form input");
      await this.settle(page);
      const read = () => page.evaluate(() => [...document.querySelectorAll(".tv-mpl-subplots .tv-mpl-form input")].map((i) => i.value));
      const opened = await page.evaluate(() => ({
        groups  : [...document.querySelectorAll(".tv-mpl-subplots .tv-group__title")].map((t) => t.textContent),
        labels  : [...document.querySelectorAll(".tv-mpl-subplots .tv-mpl-form__label")].map((t) => t.textContent),
        buttons : [...document.querySelectorAll(".tv-mpl-subplots .tv-button")].map((b) => b.textContent),
        focus   : document.activeElement.textContent,
      }));
      Run.equal(opened.groups, ["Borders", "Spacings"], "groups");
      Run.equal(opened.labels, ["top", "bottom", "left", "right", "hspace", "wspace"], "labels");
      Run.equal(opened.buttons, ["Export values", "Tight layout", "Reset", "Close"], "buttons");
      Run.equal(opened.focus, "Close", "Close focused");
      Run.equal(await read(), ["0.900", "0.100", "0.120", "1.000", "0.200", "0.200"], "values of a mono plot");
      await H.shot(page, "f133_subplots_dialog", PlotProfileChecks.AGENT, { element: ".tv-mpl-subplots" });

      const before = await this.state(page, "plot");
      const left   = page.locator(".tv-mpl-subplots .tv-mpl-form input").nth(2);
      await page.evaluate(() => { window.__mplOps.length = 0; });
      await left.click();
      await page.keyboard.press("Control+A");
      await page.keyboard.type("0.3");
      await this.settle(page);
      const typedOps = await page.evaluate(() => window.__mplOps.filter((o) => o.op === "subplots_set").length);
      await page.keyboard.press("Enter");
      await this.settle(page);
      const moved = await this.state(page, "plot");
      Run.equal([typedOps, (await read())[2], moved.hash !== before.hash], [0, "0.300", true], "no op while typing, live apply on Enter");

      await page.click('.tv-mpl-subplots .tv-button:text-is("Reset")');
      await this.settle(page);
      Run.equal([(await read())[2], (await this.state(page, "plot")).hash], ["0.120", before.hash], "Reset restores values and figure");

      await page.click('.tv-mpl-subplots .tv-button:text-is("Export values")');
      await page.waitForSelector(".tv-mpl-export__text");
      const text = await page.inputValue(".tv-mpl-export__text");
      Run.equal(text, "top=0.9,\nbottom=0.1,\nleft=0.12,\nright=1.0,\nhspace=0.2,\nwspace=0.2", "export text");
      await page.click('.tv-mpl-export .tv-button:text-is("Close")');

      await page.click('.tv-mpl-subplots .tv-button:text-is("Tight layout")');
      await this.settle(page);
      const tight = await read();
      Run.assert(tight[2] !== "0.120", `tight layout moved left ${tight}`);
      await page.click('.tv-mpl-subplots .tv-button:text-is("Reset")');
      await this.settle(page);
      await page.click('.tv-mpl-subplots .tv-button:text-is("Close")');
      await page.waitForSelector(".tv-mpl-subplots", { state: "detached" });
      return `tight ${tight.join(" ")}`;
    });

    await this.run.check("F-134", "Customize: Select Axes chooser, Figure options tabs, float validation, Max. value halves", async () => {
      await page.click(tool("edit_parameters"));
      await page.waitForSelector(".tv-mpl-chooser");
      const chooser = await page.evaluate(() => ({
        title : document.querySelector(".tv-mpl-chooser .tv-modal__title").textContent,
        label : document.querySelector(".tv-mpl-chooser .tv-label").textContent,
        items : window.app.tomovisPage.ctx.kit && [...document.querySelector(".tv-mpl-chooser .tv-combo__sizer").children].map((c) => c.textContent),
      }));
      Run.equal([chooser.title, chooser.label, chooser.items], ["Customize", "Select Axes:", ["Distance [m] - Height [m]", "<colorbar>"]], "chooser");
      await page.click('.tv-mpl-chooser .tv-button:text-is("OK")');
      await page.waitForSelector(".tv-mpl-options");
      await this.settle(page);
      const options = await page.evaluate(() => ({
        title   : document.querySelector(".tv-mpl-options .tv-modal__title").textContent,
        tabs    : [...document.querySelectorAll(".tv-mpl-options .tv-mpl-tabs .tv-tab")].map((t) => t.textContent),
        labels  : [...document.querySelectorAll(".tv-mpl-options .tv-mpl-page:not([hidden]) .tv-mpl-form__label")].map((t) => t.textContent).filter((t) => t.trim()),
        buttons : [...document.querySelectorAll(".tv-mpl-options .tv-modal__buttons button")].map((b) => b.textContent),
        scrim   : document.querySelectorAll(".tv-modal__scrim").length,
      }));
      Run.equal(options.title, "Figure options", "title");
      Run.equal(options.tabs, ["Axes", "Curves", "Images, etc."], "tabs (the white X line is a curve)");
      Run.equal(options.labels, ["Title", "Min", "Max", "Label", "Scale", "Min", "Max", "Label", "Scale", "(Re-)Generate automatic legend"], "Axes tab rows");
      Run.equal([options.buttons, options.scrim], [["OK", "Cancel", "Apply"], 0], "buttons, modeless");
      await H.shot(page, "f134_figure_options", PlotProfileChecks.AGENT, { element: ".tv-mpl-options" });

      const xmin = page.locator(".tv-mpl-options .tv-mpl-page:not([hidden]) .tv-mpl-form input.tv-line").nth(1);
      const kept = await xmin.inputValue();
      await xmin.fill("1e");
      const blocked = await page.evaluate(() => [...document.querySelectorAll(".tv-mpl-options .tv-modal__buttons button")].map((b) => b.disabled));
      await xmin.click();
      await page.keyboard.press("End");
      await page.keyboard.type("x");
      const refused = await xmin.inputValue();
      await xmin.fill(kept);
      Run.equal([blocked, refused], [[true, false, true], "1e"], "Intermediate disables OK and Apply, an invalid key is refused");

      await page.click('.tv-mpl-options .tv-mpl-tabs .tv-tab:text-is("Images, etc.")');
      const image = await page.evaluate(() => {
        const page  = document.querySelector(".tv-mpl-options .tv-mpl-page:not([hidden])");
        const label = [...page.querySelectorAll(".tv-mpl-form__label")].map((l) => l.textContent);
        return { label, combo: page.querySelectorAll(".tv-combo .tv-combo__text")[1].textContent };
      });
      Run.equal(image.label, ["Label", "Colormap", "Min. value", "Max. value", "Interpolation", "Interpolation stage"], "image rows");
      const maxField = page.locator(".tv-mpl-options .tv-mpl-page:not([hidden]) .tv-mpl-form .tv-line").nth(2);
      const maximum  = Number(await maxField.inputValue());
      const before   = await this.state(page, "plot");
      await maxField.fill(String(maximum / 2));
      await page.click('.tv-mpl-options .tv-modal__buttons button:text-is("Apply")');
      await this.settle(page);
      const after = await this.state(page, "plot");
      Run.assert(after.hash !== before.hash && (await page.$(".tv-mpl-options")), "Apply redraws and keeps the dialog");
      await this.shot(page, "f134_max_value_halved", null);
      await page.click('.tv-mpl-options .tv-modal__buttons button:text-is("Cancel")');
      await page.waitForSelector(".tv-mpl-options", { state: "detached" });
      return `Max. value ${maximum} -> ${maximum / 2}, colormap ${image.combo}`;
    });

    await this.run.check("F-135", "Save: Qt filters and start name, PNG written on the server, Error saving file", async () => {
      const target = path.join(H.shotDir(PlotProfileChecks.AGENT), "saved_plot.png");
      fs.rmSync(target, { force: true });
      await page.click(tool("save_figure"));
      await page.waitForSelector(".tv-filedialog[data-dir]");
      const dialog = await page.evaluate(() => ({
        title  : document.querySelector(".tv-filedialog .tv-modal__title").textContent,
        name   : document.querySelector(".tv-filedialog__name").value,
        filter : document.querySelector(".tv-filedialog__filter .tv-combo__text").textContent,
        items  : [...document.querySelector(".tv-filedialog__filter .tv-combo__sizer").children].map((c) => c.textContent),
        accept : document.querySelector(".tv-filedialog__accept").textContent,
      }));
      Run.equal([dialog.title, dialog.name, dialog.filter, dialog.accept], ["Choose a filename to save to", "image.png", "Portable Network Graphics (*.png)", "Save"], "dialog");
      await H.chooseFile(page, target);
      await this.settle(page);
      const head = fs.readFileSync(target).subarray(0, 8).toString("hex");
      Run.equal(head, "89504e470d0a1a0a", "PNG written");

      await page.click(tool("save_figure"));
      await H.chooseFile(page, "/tomovis_port_missing_directory/plot.png");
      await page.waitForSelector(".tv-messagebox");
      const box = await page.evaluate(() => ({ title: document.querySelector(".tv-messagebox .tv-modal__title").textContent, level: document.querySelector(".tv-messagebox").dataset.level }));
      Run.equal(box, { title: "Error saving file", level: "critical" }, "error box");
      await page.click('.tv-messagebox .tv-button:text-is("OK")');
      return `${dialog.items.length} filters`;
    });

    await this.run.check("F-069 warnings", "Axes dialog: Cancel changes nothing, the two warnings, Enter accepts", async () => {
      const before = await page.evaluate(() => window.app.tomovisPage.ctx.session.snapshot.attributes);
      await page.click('[data-widget="tab2AxesButton"]');
      await page.waitForSelector(".tv-axes-dialog");
      await page.fill('.tv-axes-dialog [data-field="x_label"]', "Ignored");
      await page.click('.tv-axes-dialog .tv-modal__buttons button:text-is("Cancel")');
      await this.settle(page);
      const cancelled = await page.evaluate(() => window.app.tomovisPage.ctx.session.snapshot.attributes.x_label_view);
      Run.equal(cancelled, before.x_label_view, "Cancel");

      const warnings = [];
      for (const [field, other] of [["x_max", "x_min"], ["z_max", "z_min"]]) {
        await page.click('[data-widget="tab2AxesButton"]');
        await page.waitForSelector(".tv-axes-dialog");
        const value = await page.inputValue(`.tv-axes-dialog [data-field="${other}"] input`);
        const input = page.locator(`.tv-axes-dialog [data-field="${field}"] input`);
        await input.click();
        await page.keyboard.press("Control+A");
        await page.keyboard.type(value);
        await page.keyboard.press("Enter");
        await page.waitForSelector(".tv-messagebox");
        warnings.push(await page.evaluate(() => [document.querySelector(".tv-messagebox .tv-modal__title").textContent, document.querySelector(".tv-messagebox__text").textContent]));
        await page.click('.tv-messagebox .tv-button:text-is("OK")');
        await this.settle(page);
      }
      Run.equal(warnings, [["Invalid axis limits", "X min must be smaller than X max."], ["Invalid axis limits", "Z min must be smaller than Z max."]], "warnings");
      const after = await page.evaluate(() => window.app.tomovisPage.ctx.session.snapshot.attributes);
      Run.equal([after.x_view_min, after.x_view_max, after.z_view_range], [before.x_view_min, before.x_view_max, before.z_view_range], "limits unchanged");
    });

    await this.run.check("F-071", "Plot Clear greys every Plot control but Full View and blanks both figures (Q-043)", async () => {
      await this.click(page, '[data-widget="tab2ClearButton"]');
      const controls = await this.controls(page);
      const enabled  = PlotProfileChecks.PLOT_ROW.filter((name) => controls[name].enabled);
      const plot     = await this.state(page, "plot");
      const profile  = await this.state(page, "profile");
      Run.equal([enabled, controls.tab2ChkBox4.checked, controls.tab3ClearButton.enabled, plot.white, profile.white], [["tab2ChkBox4"], true, false, true, true], "after Clear");
      await this.shot(page, "f071_after_clear", null);
    });

    await this.run.check("F-140 wheel", "A wheel notch over the Plot colormap selects the next map and replots", async () => {
      await this.send(page, { type: "click", widget: "tab1PlotButton" });
      const before = await this.state(page, "plot");
      const index  = (await this.controls(page)).tab2ComboBox.index;
      await page.hover('[data-widget="tab2ComboBox"]');
      await page.mouse.wheel(0, 120);
      await this.settle(page);
      const after = await this.state(page, "plot");
      Run.equal([(await this.controls(page)).tab2ComboBox.index, after.hash !== before.hash], [index + 1, true], "next colormap, replotted");
    });
  }

  async rgbSequence() {
    const page = await this.open();
    await this.run.check("F-062", "RGB plot without colorbar, normalized, x line (shots 77, 78, 79)", async () => {
      await this.importRealistic(page, "npy", "realistic_pseudo_rgb.npy");
      Run.equal((await this.controls(page)).tabWidget.index, 1, "Plot tab");
      await this.shot(page, "77_rgb_plot", "77_rgb_levels_fixed_rgb_plot.png");
      await this.click(page, '[data-widget="tab2ChkBox1"]');
      await this.shot(page, "78_rgb_plot_normalized", "78_rgb_levels_fixed_rgb_plot_normalized.png");
      await this.click(page, '[data-widget="tab2ChkBox3"]');
      await this.shot(page, "79_rgb_plot_x_line", "79_rgb_levels_fixed_rgb_plot_x_line.png");
    });
    await this.run.check("F-082", "RGB profile: three channel panels and the stacked legend panel (shot 80)", async () => {
      await this.click(page, '[data-widget="tab2PlotButton"]');
      Run.equal((await this.controls(page)).tabWidget.index, 2, "Profile tab");
      await this.shot(page, "80_rgb_profile", "80_rgb_levels_fixed_rgb_profile.png");
    });
  }

  async withoutData() {
    const page = await this.open();
    await this.run.check("Q-040", "X [m] without data enables the spin box at 0.50 and Plot; Plot draws nothing and stays (E-011)", async () => {
      await this.click(page, '.tv-tab[data-tab="1"]');
      await this.click(page, '[data-widget="tab2ChkBox3"]');
      let controls = await this.controls(page);
      Run.equal([controls.tab2SpinBox.enabled, controls.tab2SpinBox.value, controls.tab2PlotButton.enabled, controls.tab2ChkBox2.enabled], [true, 0.5, true, false], "state");
      Run.equal(await page.inputValue('[data-widget="tab2SpinBox"] input'), "0.50", "spin text");
      await this.click(page, '[data-widget="tab2PlotButton"]');
      controls = await this.controls(page);
      Run.equal([controls.tabWidget.index, controls.tab3ClearButton.enabled, (await this.state(page, "profile")).white], [1, false, true], "no switch, nothing drawn");
    });
  }

  async scripts() {
    const page = await this.open("tomovis_scripts");
    await this.instrumentScripts(page);
    const root = "#tv-script-slicer";

    await this.run.check("F-150", "SlicerMatplotlib panel: inline error, load, j/k step, keymap Save", async () => {
      await page.click(`${root} .tv-button:text-is("Browse")`);
      await page.waitForSelector(".tv-filedialog[data-dir]");
      const browse = await page.evaluate(() => [document.querySelector(".tv-filedialog .tv-modal__title").textContent, document.querySelector(".tv-filedialog__filter .tv-combo__text").textContent]);
      Run.equal(browse, ["Open File", "HDF5 (*.hd5)"], "Browse dialog");
      await page.click(".tv-filedialog__cancel");

      await page.fill(`${root} .tv-script-slicer__path`, H.fixture("inputs/fusar_no_attrs.hd5"));
      await page.click(`${root} .tv-button:text-is("Load")`);
      await page.waitForSelector(`${root} .tv-script-slicer__error:not([hidden])`);
      const error = await page.textContent(`${root} .tv-script-slicer__error`);
      Run.equal(error, "No attribute 'range'.", "inline error");

      await page.fill(`${root} .tv-script-slicer__path`, H.fixture("inputs/fusar_one_key_range.hd5"));
      await page.press(`${root} .tv-script-slicer__path`, "Enter");
      await page.waitForFunction(() => window.app.tomovisScriptsPage.views[0].figure.attached);
      await this.settle(page);
      const loaded = await this.state(page, "script_slicer");
      Run.assert(loaded.width === 800 && loaded.height === 600 && !loaded.white, `figure ${JSON.stringify(loaded)}`);
      Run.equal(await page.evaluate(() => document.activeElement.dataset.figure), "script_slicer", "canvas focused");
      await this.shot(page, "f150_slicer_script", null, root);

      await page.keyboard.press("k");
      await this.settle(page);
      const next = await this.state(page, "script_slicer");
      await page.keyboard.press("j");
      await this.settle(page);
      const back = await this.state(page, "script_slicer");
      Run.assert(next.hash !== loaded.hash && back.hash === loaded.hash, "k steps forward, j steps back");

      await page.keyboard.press("s");
      await page.waitForSelector(".tv-filedialog[data-dir]");
      const save = await page.textContent(".tv-filedialog .tv-modal__title");
      await page.click(".tv-filedialog__cancel");
      Run.equal(save, "Choose a filename to save to", "keymap s opens Save");
      const keyOps = await page.evaluate(() => window.__mplOps.filter((o) => o.op === "key").map((o) => o.payload.event.key));
      Run.equal(keyOps, ["kk", "kk", "kj", "kj", "ks", "ks"], "key press and release ops");
      return `${loaded.frames} -> ${back.frames} frames`;
    });
  }

  unexpected(launched) {
    let expected = launched.failures.filter((failure) => failure.startsWith("400 ") && PlotProfileChecks.EXPECTED_400.some((part) => failure.includes(part))).length;
    for (const failure of launched.failures) console.log(`  response ${failure}`);
    return launched.errors.filter((error) => {
      if (expected > 0 && error.includes("status of 400")) {
        expected -= 1;
        return false;
      }
      return true;
    });
  }

  async main() {
    const page = await this.open();
    await this.layout(page);
    await this.singleSequence(page);
    await this.navigation(page);
    await this.dialogs(page);
    await this.rgbSequence();
    await this.withoutData();
    await this.scripts();

    for (const launched of this.pages) {
      this.errors.push(...this.unexpected(launched));
      await launched.browser.close();
    }
    const ok = this.run.summary(this.errors);
    fs.writeFileSync(path.join(H.shotDir(PlotProfileChecks.AGENT), "plot_checks.json"), JSON.stringify({ results: this.run.results, errors: this.errors }, null, 2));
    process.exit(ok ? 0 : 1);
  }
}

await new PlotProfileChecks(H.args(process.argv)).main();
