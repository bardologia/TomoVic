import fs from "node:fs";
import path from "node:path";
import { TomoVisHarness as H, TomoVisCheckRun as R, REPO } from "./harness.mjs";

class ShellChecks {
  constructor(options) {
    this.options = options;
    this.run     = new R("shell");
    this.inputs  = H.fixture("inputs");
    this.out     = H.shotDir("shell");
    this.errors  = [];
  }

  async control(name) {
    const snapshot = await H.snapshot(this.page);
    return snapshot.controls[name];
  }

  async send(event) {
    await this.page.evaluate((e) => window.app.tomovisPage.ctx.session.send(e), event);
    await H.waitIdle(this.page);
  }

  async waitDialog(selector = ".tv-modal") {
    await this.page.waitForSelector(selector, { timeout: 15000 });
  }

  async modalTitle() {
    return this.page.textContent(".tv-modal:last-of-type .tv-modal__title");
  }

  async closeMenus() {
    await this.page.keyboard.press("Escape");
    await this.page.evaluate(() => { if (window.TomoVisMenu.root) window.TomoVisMenu.root.close(); });
  }

  async menuTexts() {
    return this.page.locator(".tv-menu").last().evaluate((menu) => [...menu.children].map((row) => {
      if (row.classList.contains("tv-menu__separator")) return "---";
      const text     = row.querySelector(".tv-menu__text").textContent;
      const shortcut = row.querySelector(".tv-menu__shortcut").textContent;
      const flags    = [row.classList.contains("is-disabled") ? "disabled" : "", row.querySelector(".tv-menu__arrow") ? ">" : "", row.querySelector(".tv-menu__mark.is-on") ? "checked" : ""].filter(Boolean).join(",");
      return [text, shortcut, flags].filter(Boolean).join("|");
    }));
  }

  async importFile(menuLabel, file) {
    await H.menu(this.page, "File", "Import", menuLabel);
    await H.chooseFile(this.page, file);
  }

  async testbed(build) {
    await this.page.evaluate((source) => {
      const ctx = window.app.tomovisPage.ctx;
      let box   = document.getElementById("shell-testbed");
      if (box) box.remove();
      box = document.createElement("div");
      box.id = "shell-testbed";
      box.className = "tv-row";
      box.style.cssText = "position:absolute;left:60px;top:210px;padding:10px;background:#141b22;border:2px solid #4f5d6a";
      ctx.layer.append(box);
      window.shellViews = {};
      for (const [key, kind, name, options] of source) {
        const view = ctx.kit.bound(kind, name, options);
        window.shellViews[key] = view;
        box.append(view.el);
      }
    }, build);
  }

  async page01() {
    await this.run.check("F-001", "window title, tab order, Slicer current, minimum size", async () => {
      R.equal(await this.page.title(), "TomoVis", "document title");
      const tabs = await this.page.$$eval(".tv-tab", (nodes) => nodes.filter((n) => !n.hidden).map((n) => [n.textContent, n.classList.contains("is-current")]));
      R.equal(tabs, [["Slicer", true], ["Plot", false], ["Profile", false], ["3D", false]], "tabs");
      const snapshot = await H.snapshot(this.page);
      R.equal(snapshot.controls.tabWidget.titles, ["Slicer", "Plot", "Profile", "3D"], "server tab titles");

      await this.page.setViewportSize({ width: 1000, height: 700 });
      await this.page.waitForTimeout(200);
      const small = await this.page.evaluate(() => {
        const win  = document.getElementById("tv-window").getBoundingClientRect();
        const page = document.querySelector('.page[data-page="tomovis"]');
        return { w: win.width, h: win.height, scrollX: page.scrollWidth > page.clientWidth, scrollY: document.documentElement.scrollHeight > window.innerHeight };
      });
      await this.page.setViewportSize({ width: 1440, height: 1000 });
      await this.page.waitForTimeout(200);
      R.assert(small.w >= 1100 && small.h >= 880, `window shrank to ${small.w}x${small.h}`);
      R.assert(small.scrollX && small.scrollY, "the page does not scroll at 1000x700");
      await H.shot(this.page, "01_startup_frame", "shell");
      H.compareShot("01_startup_frame", path.join(this.options.original, "01_startup_slicer_no_data.png"), "shell");
      return `window ${small.w}x${small.h} at a 1000x700 viewport, page scrolls both ways`;
    });
  }

  async menus() {
    await this.run.check("F-002", "File menu entries", async () => {
      await this.page.click('.tv-menubar__item[data-menu="file"]');
      const texts = await this.menuTexts();
      await H.shot(this.page, "05_menu_file", "shell", { element: ".tv-menu" });
      H.compareShot("05_menu_file", path.join(this.options.original, "05_menu_file.png"), "shell");
      R.equal(texts, ["Open|Ctrl+O", "Save|Ctrl+S|disabled", "---", "Import|>"], "File menu");
      return texts.join(" / ");
    });

    await this.run.check("F-005", "Import submenu entries", async () => {
      await this.page.locator(".tv-menu .tv-menu__item", { hasText: "Import" }).hover();
      await this.page.waitForSelector(".tv-menu >> nth=1");
      const texts = await this.menuTexts();
      await H.shot(this.page, "06_menu_file_import", "shell", { element: ".tv-menu >> nth=1" });
      H.compareShot("06_menu_file_import", path.join(this.options.original, "06_menu_file_import.png"), "shell");
      R.equal(texts, ["hd5", "rat", "h5", "npy"], "Import submenu");
      return texts.join(" / ");
    });

    await this.run.check("F-008", "status tips follow the hovered menu entry", async () => {
      const sub = this.page.locator(".tv-menu").nth(1);
      await sub.locator(".tv-menu__item", { hasText: "npy" }).hover();
      const npy = await this.page.textContent("#tv-status");
      await sub.locator(".tv-menu__item", { hasText: "hd5" }).hover();
      const hd5 = await this.page.textContent("#tv-status");
      await this.page.locator(".tv-menu").first().locator(".tv-menu__item", { hasText: "Open" }).hover();
      const open = await this.page.textContent("#tv-status");
      await this.page.waitForTimeout(400);
      const subOpen = await this.page.locator(".tv-menu").count();
      await this.page.locator(".tv-menu").first().locator(".tv-menu__item", { hasText: "Save" }).hover();
      const save   = await this.page.textContent("#tv-status");
      const lit    = await this.page.locator(".tv-menu .tv-menu__item.is-active").count();
      const box = await this.page.locator(".tv-menu").first().boundingBox();
      await this.page.mouse.move(box.x + box.width + 260, box.y + box.height + 200);
      const away = await this.page.textContent("#tv-status");
      await this.closeMenus();
      const closed = await this.page.textContent("#tv-status");
      R.equal([npy, hd5, open, subOpen, save, lit, away, closed], ["Import npy file", "Import hd5 file", "Open File", 1, "", 0, "", ""], "status line");
      return "npy -> Import npy file, hd5 -> Import hd5 file, Open -> Open File (Import submenu closes after 225 ms), disabled Save -> empty and not highlighted, away and closed -> empty";
    });

    await this.run.check("F-006", "Data > Channel greyed without data", async () => {
      await this.page.click('.tv-menubar__item[data-menu="data"]');
      const texts = await this.menuTexts();
      await H.shot(this.page, "07_menu_data_no_data", "shell", { element: ".tv-menu" });
      H.compareShot("07_menu_data_no_data", path.join(this.options.original, "07_menu_data_no_data.png"), "shell");
      await this.page.locator(".tv-menu .tv-menu__item", { hasText: "Channel" }).hover();
      await this.page.waitForTimeout(400);
      const submenus = await this.page.locator(".tv-menu").count();
      await this.closeMenus();
      R.equal(texts, ["Channel|disabled,>"], "Data menu");
      R.equal(submenus, 1, "disabled Channel opened a submenu");
      return texts.join(" / ");
    });

    await this.run.check("F-002 keys", "menu bar keyboard: Down opens, Right moves to Data, Escape closes", async () => {
      await this.page.mouse.move(1300, 900);
      const active = () => this.page.locator(".tv-menu").first().locator(".tv-menu__item.is-active .tv-menu__text").textContent();
      await this.page.focus('.tv-menubar__item[data-menu="file"]');
      await this.page.keyboard.press("ArrowDown");
      const first = await active();
      await this.page.keyboard.press("ArrowDown");
      const second = await active();
      await this.page.keyboard.press("ArrowRight");
      await this.page.waitForTimeout(100);
      const sub = await this.page.locator(".tv-menu").nth(1).locator(".tv-menu__item.is-active .tv-menu__text").textContent();
      await this.page.keyboard.press("ArrowLeft");
      await this.page.keyboard.press("ArrowRight");
      await this.page.keyboard.press("ArrowLeft");
      await this.page.keyboard.press("ArrowLeft");
      const data = await this.page.locator(".tv-menu").first().locator(".tv-menu__text").first().textContent();
      const menus = await this.page.locator(".tv-menu").count();
      const title = await this.page.$eval(".tv-menubar__item.is-open", (t) => t.textContent);
      await this.page.keyboard.press("Escape");
      const open = await this.page.locator(".tv-menu").count();
      R.equal([first, second, sub, menus, title, data, open], ["Open", "Import", "hd5", 1, "Data", "Channel", 0], "keyboard walk (Save is disabled and skipped)");
      return "Down: Open, Down: Import (Save skipped), Right: hd5 in Import, Left closes it, Left at the top level moves to Data, Escape closes";
    });
  }

  async shortcutsBeforeData() {
    await this.run.check("F-004", "Ctrl+S inert and prevented before data", async () => {
      const prevented = await this.page.evaluate(() => {
        const event = new KeyboardEvent("keydown", { key: "s", ctrlKey: true, bubbles: true, cancelable: true });
        document.body.dispatchEvent(event);
        return event.defaultPrevented;
      });
      await H.waitIdle(this.page);
      const dialogs = await this.page.locator(".tv-modal").count();
      const save    = await this.control("saveFile");
      R.equal([prevented, dialogs, save.enabled], [true, 0, false], "Ctrl+S before data");
      return "keydown default prevented, no dialog, saveFile disabled";
    });

    await this.run.check("F-003", "Ctrl+O opens the TomoVis session chooser", async () => {
      await this.page.keyboard.press("Control+o");
      await this.waitDialog(".tv-filedialog");
      const title  = await this.modalTitle();
      const filter = await this.page.textContent(".tv-filedialog .tv-filedialog__filter .tv-combo__text");
      const accept = await this.page.textContent(".tv-filedialog__accept");
      await H.shot(this.page, "03_open_file_dialog", "shell");
      await this.page.click(".tv-filedialog__cancel");
      await this.page.waitForSelector(".tv-filedialog", { state: "detached" });
      await H.waitIdle(this.page);
      R.equal([title, filter, accept], ["Open File", "Visualizer (*.hd5)", "Open"], "Open dialog");
      return `${title}, ${filter}`;
    });
  }

  async importChooser() {
    await this.run.check("F-010", "Import > npy chooser lists only *.npy and folders; Cancel is inert", async () => {
      const before = await H.snapshot(this.page);
      await H.menu(this.page, "File", "Import", "npy");
      await this.waitDialog(".tv-filedialog");
      await this.page.fill(".tv-filedialog__lookin", this.inputs);
      await this.page.press(".tv-filedialog__lookin", "Enter");
      await this.page.waitForFunction((dir) => document.querySelector(".tv-filedialog").dataset.dir === dir, this.inputs);
      await this.page.waitForTimeout(400);
      const look   = await this.page.inputValue(".tv-filedialog__lookin");
      const names  = await this.page.$$eval(".tv-filedialog tbody tr", (rows) => rows.map((r) => [r.classList.contains("is-dir"), r.querySelector(".tv-filedialog__cell--name").textContent]));
      const title  = await this.modalTitle();
      const filter = await this.page.textContent(".tv-filedialog .tv-filedialog__filter .tv-combo__text");
      await H.shot(this.page, "10_import_npy_chooser", "shell");
      await this.page.click(".tv-filedialog__cancel");
      await this.page.waitForSelector(".tv-filedialog", { state: "detached" });
      await H.waitIdle(this.page);
      const after = await H.snapshot(this.page);

      R.equal([title, filter, look], ["Open File", "Numpy (*.npy)", this.inputs], "dialog title, filter and directory");
      R.assert(names.filter(([dir]) => !dir).length === 8, `expected the 8 npy inputs, got ${JSON.stringify(names)}`);
      R.assert(names.every(([dir, name]) => dir || name.toLowerCase().endsWith(".npy")), `non-npy file listed: ${JSON.stringify(names)}`);
      R.equal(after.controls.saveFile.enabled, before.controls.saveFile.enabled, "Cancel changed the window");
      R.equal(after.attributes, before.attributes, "Cancel changed the attributes");
      return `${names.length} entries, all *.npy: ${names.map((n) => n[1]).join(", ")}`;
    });

    await this.run.check("F-010 nav", "file dialog navigation: Parent, Back, Forward, typed directory", async () => {
      await H.menu(this.page, "File", "Import", "hd5");
      await this.waitDialog(".tv-filedialog");
      await this.page.fill(".tv-filedialog__lookin", this.inputs);
      await this.page.press(".tv-filedialog__lookin", "Enter");
      await this.page.waitForFunction((dir) => document.querySelector(".tv-filedialog").dataset.dir === dir, this.inputs);
      const look = () => this.page.inputValue(".tv-filedialog__lookin");
      await this.page.click(".tv-filedialog__parent");
      await this.page.waitForFunction((dir) => document.querySelector(".tv-filedialog").dataset.dir && document.querySelector(".tv-filedialog").dataset.dir !== dir, this.inputs);
      const parent = await look();
      await this.page.click(".tv-filedialog__back");
      await this.page.waitForFunction((dir) => document.querySelector(".tv-filedialog").dataset.dir === dir, this.inputs);
      await this.page.click(".tv-filedialog__forward");
      await this.page.waitForFunction((dir) => document.querySelector(".tv-filedialog").dataset.dir === dir, parent);
      await this.page.fill(".tv-filedialog__name", "inputs");
      await this.page.press(".tv-filedialog__name", "Enter");
      await this.page.waitForFunction((dir) => document.querySelector(".tv-filedialog").dataset.dir === dir, this.inputs);
      const listed = await this.page.$$eval(".tv-filedialog tbody tr .tv-filedialog__cell--name", (cells) => cells.map((c) => c.textContent));
      await this.page.fill(".tv-filedialog__name", "missing_file.hd5");
      await this.page.press(".tv-filedialog__name", "Enter");
      await this.page.waitForSelector(".tv-messagebox");
      const warning = await this.page.textContent(".tv-messagebox .tv-messagebox__text");
      const warnTitle = await this.page.textContent(".tv-messagebox .tv-modal__title");
      await H.shot(this.page, "10_file_not_found", "shell");
      await this.page.click(".tv-messagebox .tv-button");
      await this.page.keyboard.press("Escape");
      await this.page.waitForSelector(".tv-filedialog", { state: "detached" });
      await H.waitIdle(this.page);
      R.equal(parent, path.dirname(this.inputs), "parent directory");
      R.assert(listed.every((n) => n.endsWith(".hd5")), `hd5 filter listed ${listed.join(", ")}`);
      R.equal([warnTitle, warning], ["Open File", "missing_file.hd5\nFile not found.\nPlease verify the correct file name was given."], "QFileDialog not-found warning");
      return `parent ${parent}; back/forward; typed dir entered; ${listed.length} hd5 files; not-found warning; Escape cancels`;
    });
  }

  async importAndChannels() {
    await this.run.check("F-013 Br", "Import > npy loads a cube through the chooser", async () => {
      await this.importFile("npy", path.join(this.inputs, "npy_real.npy"));
      const snapshot = await H.snapshot(this.page);
      R.equal([snapshot.controls.saveFile.enabled, snapshot.controls.tab1Slider.maximum, snapshot.controls.tab1Slider.value, snapshot.controls.ChMenu.enabled], [true, 23, 12, false], "after npy_real import");
      return "saveFile enabled, slider 12 of 0..23, Channel disabled";
    });

    await this.run.check("F-006 Br", "multi-channel import enables Channel with RGB checked; Red checks Red", async () => {
      await this.importFile("npy", path.join(this.inputs, "npy_channels_3.npy"));
      await this.page.click('.tv-menubar__item[data-menu="data"]');
      await this.page.locator(".tv-menu .tv-menu__item", { hasText: "Channel" }).hover();
      await this.page.waitForSelector(".tv-menu >> nth=1");
      const texts = await this.menuTexts();
      await H.shot(this.page, "73_menu_data_channel", "shell", { element: ".tv-menu >> nth=1" });
      H.compareShot("73_menu_data_channel", path.join(this.options.original, "73_rgb_levels_fixed_menu_data_channel.png"), "shell");
      await this.page.locator(".tv-menu").nth(1).locator(".tv-menu__item", { hasText: "Red" }).click();
      await H.waitIdle(this.page);
      const snapshot = await H.snapshot(this.page);
      R.equal(texts, ["RGB|Ctrl+F|checked", "Red", "Green", "Blue"], "Channel submenu");
      R.equal([snapshot.controls.ch1Menu.checked, snapshot.controls.allChMenu.checked], [true, false], "Red checked, RGB unchecked");
      return texts.join(" / ");
    });

    await this.run.check("F-007 Br", "Ctrl+F reaches the server and selects RGB", async () => {
      await this.page.keyboard.press("Control+f");
      await H.waitIdle(this.page);
      const snapshot = await H.snapshot(this.page);
      R.equal([snapshot.controls.allChMenu.checked, snapshot.controls.tabWidget.index], [true, 0], "after Ctrl+F");
      return "allChMenu checked, Slicer current";
    });
  }

  async sessionDialogs() {
    const target = path.join(this.out, "shell_session_check.hd5");
    if (fs.existsSync(target)) fs.unlinkSync(target);

    await this.run.check("F-020 Br", "File > Save dialog flow writes the session and confirms an overwrite", async () => {
      await this.importFile("npy", path.join(this.inputs, "npy_real.npy"));
      await H.menu(this.page, "File", "Save");
      await this.waitDialog(".tv-filedialog");
      const title  = await this.modalTitle();
      const accept = await this.page.textContent(".tv-filedialog__accept");
      const filter = await this.page.textContent(".tv-filedialog .tv-filedialog__filter .tv-combo__text");
      await H.chooseFile(this.page, target);
      await this.waitDialog(".tv-messagebox");
      const info = [await this.page.textContent(".tv-messagebox .tv-modal__title"), await this.page.textContent(".tv-messagebox .tv-messagebox__text"), await this.page.locator(".tv-messagebox .tv-button").count()];
      await H.shot(this.page, "09_save_successful", "shell");
      await this.page.click(".tv-messagebox .tv-button");

      await this.page.keyboard.press("Control+s");
      await this.waitDialog(".tv-filedialog");
      await this.page.fill(".tv-filedialog .tv-filedialog__name", target);
      await this.page.click(".tv-filedialog .tv-filedialog__accept");
      await this.page.waitForSelector(".tv-messagebox");
      const confirm = [await this.page.textContent(".tv-messagebox .tv-messagebox__text"), await this.page.$$eval(".tv-messagebox .tv-button", (b) => b.map((x) => x.textContent))];
      await H.shot(this.page, "09_overwrite_confirm", "shell");
      await this.page.click(".tv-messagebox .tv-button >> text=Yes");
      await this.page.waitForSelector(".tv-filedialog", { state: "detached" });
      await H.waitIdle(this.page);
      await this.waitDialog(".tv-messagebox");
      await this.page.click(".tv-messagebox .tv-button");
      await H.waitIdle(this.page);

      R.equal([title, accept, filter], ["Save File", "Save", "Visualizer (*.hd5)"], "save dialog");
      R.equal(info, ["Save successful", `File saved successfully:\n${target}`, 1], "save message");
      R.equal(confirm, ["shell_session_check.hd5 already exists.\nDo you want to replace it?", ["Yes", "No"]], "overwrite question");
      R.assert(fs.existsSync(target), "session file not written");
      return `${target} written, overwrite confirmed with Yes`;
    });

    await this.run.check("F-009 Br", "message boxes use the original titles and texts with one OK", async () => {
      await H.menu(this.page, "File", "Open");
      await H.chooseFile(this.page, path.join(this.inputs, "fusar_no_attrs.hd5"));
      await this.waitDialog(".tv-messagebox");
      const box = [await this.page.textContent(".tv-messagebox .tv-modal__title"), await this.page.textContent(".tv-messagebox .tv-messagebox__text"), await this.page.$$eval(".tv-messagebox .tv-button", (b) => b.map((x) => x.textContent)), await this.page.getAttribute(".tv-messagebox", "data-level")];
      await H.shot(this.page, "08_message_open_error", "shell", { element: ".tv-messagebox" });
      H.compareShot("08_message_open_error", path.join(this.options.original, "08_message_no_data_warning.png"), "shell");
      await this.page.keyboard.press("Escape");
      await this.page.waitForSelector(".tv-messagebox", { state: "detached" });
      R.equal(box, ["Open error", "Could not open file:\nDataset 'data' not found in file.", ["OK"], "critical"], "Open error box");
      return `${box[0]}: ${box[1].replace("\n", " / ")}`;
    });
  }

  async timerAndPlay() {
    await this.run.check("F-046 Br", "Play ticks one slice per 500 ms and wraps; F-016 import cancel stops it", async () => {
      await this.importFile("npy", path.join(this.inputs, "npy_real.npy"));
      await this.send({ type: "check", widget: "tab1ChkBox", checked: true });
      await this.send({ type: "value", widget: "tab1SpinBox", value: 22 });
      await this.send({ type: "click", widget: "tab1PlayButton" });
      const started = Date.now();
      const seen = [];
      while (Date.now() - started < 1800) {
        const value = (await this.control("tab1SpinBox")).value;
        if (seen[seen.length - 1] !== value) seen.push(value);
        await this.page.waitForTimeout(50);
      }
      const timer = await this.control("tab1Timer");

      await H.menu(this.page, "File", "Import", "npy");
      await this.waitDialog(".tv-filedialog");
      await this.page.click(".tv-filedialog__cancel");
      await H.waitIdle(this.page);
      const stopped = await this.control("tab1Timer");
      const frozen  = (await this.control("tab1SpinBox")).value;
      await this.page.waitForTimeout(1200);
      const later   = (await this.control("tab1SpinBox")).value;

      R.equal(seen.slice(0, 4), [22, 23, 0, 1], "slices during play");
      R.equal([timer.active, timer.interval], [true, 500], "timer while playing");
      R.equal([stopped.active, frozen === later], [false, true], "timer after the cancelled import");
      return `slices ${seen.join(" -> ")} in 1.8 s; stopped by the cancelled import`;
    });
  }

  async kitAgainstServer() {
    await this.run.check("F-141", "focused slice slider: PageDown -10, PageUp +10, arrows, Home/End reach the server", async () => {
      await this.importFile("npy", path.join(this.inputs, "npy_real.npy"));
      await this.send({ type: "check", widget: "tab1ChkBox", checked: true });
      await this.testbed([["slider", "slider", "tab1Slider", { minWidth: 400 }], ["spin", "spin", "tab1SpinBox", { maxWidth: 180 }], ["combo", "combo", "tab1ComboBox", { items: await this.page.evaluate(() => window.app.tomovisPage.ctx.tables.colortables.names) }], ["line", "line", "tab1QLineEdit1", { validator: "-?[0-9]+[.]?[0-9]{,4}", maxWidth: 90 }]]);
      await this.page.focus("#shell-testbed .tv-slider");
      const values = [];
      for (const key of ["PageDown", "PageUp", "PageUp", "ArrowLeft", "Home", "End"]) {
        await this.page.keyboard.press(key);
        await H.waitIdle(this.page);
        values.push((await this.control("tab1Slider")).value);
      }
      const spin = (await this.control("tab1SpinBox")).value;
      R.equal(values, [2, 12, 22, 21, 0, 23], "server slider values from 12");
      R.equal(spin, 23, "spin box follows the slider (S-5)");
      return values.join(" -> ");
    });

    await this.run.check("F-140", "wheel over slider (3 steps), spin box (1 step) and combo (next entry, no wrap)", async () => {
      await this.send({ type: "value", widget: "tab1Slider", value: 12 });
      const slider = await this.page.locator("#shell-testbed .tv-slider").boundingBox();
      await this.page.mouse.move(slider.x + slider.width / 2, slider.y + slider.height / 2);
      await this.page.mouse.wheel(0, -100);
      await H.waitIdle(this.page);
      const s1 = (await this.control("tab1Slider")).value;
      const spin = await this.page.locator("#shell-testbed .tv-spin").boundingBox();
      await this.page.mouse.move(spin.x + 8, spin.y + 8);
      await this.page.mouse.wheel(0, 100);
      await H.waitIdle(this.page);
      const s2 = (await this.control("tab1SpinBox")).value;
      await this.send({ type: "check", widget: "tab1ChkBox", checked: false });
      const combo = await this.page.locator("#shell-testbed .tv-combo").boundingBox();
      await this.page.mouse.move(combo.x + 8, combo.y + 8);
      await this.page.mouse.wheel(0, 100);
      await H.waitIdle(this.page);
      const c1 = await this.control("tab1ComboBox");
      await this.send({ type: "index", widget: "tab1ComboBox", index: 18 });
      await this.page.mouse.wheel(0, 100);
      await H.waitIdle(this.page);
      const c2 = await this.control("tab1ComboBox");
      R.equal([s1, s2, c1.index, c2.index], [15, 14, 10, 18], "wheel results");
      return `slider 12 -> ${s1}, spin ${s1} -> ${s2}, combo 9 -> ${c1.index} (${c1.text}), at 18 stays ${c2.index}`;
    });

    await this.run.check("F-143", "ROI field validator refuses letters and a fifth decimal; Ctrl+O still works from the field", async () => {
      await this.page.fill("#shell-testbed .tv-line", "");
      await this.page.click("#shell-testbed .tv-line");
      await this.page.keyboard.type("x12.34567y");
      await H.waitIdle(this.page);
      const shown  = await this.page.inputValue("#shell-testbed .tv-line");
      const server = (await this.control("tab1QLineEdit1")).text;
      await this.page.keyboard.press("Control+o");
      await this.waitDialog(".tv-filedialog");
      const title = await this.modalTitle();
      await this.page.keyboard.press("Escape");
      await this.page.waitForSelector(".tv-filedialog", { state: "detached" });
      await H.waitIdle(this.page);
      R.equal([shown, server, title], ["12.3456", "12.3456", "Open File"], "validated text");
      return `typed x12.34567y -> ${shown} (server ${server}); Ctrl+O opened ${title} with the field focused`;
    });

    await this.run.check("F-142", "X [m] double spin box: typing 100 above 0..max is refused; Enter fixes to 2 decimals; arrows step 1", async () => {
      await this.send({ type: "click", widget: "tab1PlotButton" });
      await this.send({ type: "check", widget: "tab2ChkBox3", checked: true });
      await this.testbed([["xspin", "doubleSpin", "tab2SpinBox", { decimals: 2, maxWidth: 180 }]]);
      const range = await this.control("tab2SpinBox");
      await this.page.click("#shell-testbed .tv-spin__input", { clickCount: 3 });
      await this.page.keyboard.type("100");
      await H.waitIdle(this.page);
      const typed = await this.page.inputValue("#shell-testbed .tv-spin__input");
      await this.page.keyboard.press("Enter");
      await H.waitIdle(this.page);
      const fixed = await this.page.inputValue("#shell-testbed .tv-spin__input");
      await this.page.keyboard.press("ArrowUp");
      await H.waitIdle(this.page);
      const stepped = await this.control("tab2SpinBox");
      R.assert(range.maximum < 100, `X [m] maximum ${range.maximum} is not below 100`);
      R.equal([typed, fixed, stepped.value], ["10", "10.00", 11], "X [m] typing");
      return `range ${range.minimum}..${range.maximum}: "100" -> "${typed}", Enter -> "${fixed}", Up -> ${stepped.value}`;
    });

    await this.run.check("F-144", "tab clicks and programmatic switches", async () => {
      await this.page.evaluate(() => document.getElementById("shell-testbed").remove());
      const picks = [];
      for (const index of [2, 1, 0]) {
        await this.page.click(`.tv-tab[data-tab="${index}"]`);
        await H.waitIdle(this.page);
        picks.push((await this.control("tabWidget")).index);
      }
      await this.send({ type: "click", widget: "tab1PlotButton" });
      const plot = (await this.control("tabWidget")).index;
      const shown = await this.page.$eval(".tv-tab.is-current", (t) => t.textContent);
      const panel = await this.page.$eval(".tv-panel.is-current", (p) => p.id);
      R.equal([picks, plot, shown, panel], [[2, 1, 0], 1, "Plot", "tv-panel-plot"], "tabs");
      await this.page.click('.tv-tab[data-tab="0"]');
      await H.waitIdle(this.page);
      return "clicks 2,1,0 echoed by the server; Slicer Plot switched to Plot";
    });
  }

  async colorDialog() {
    await this.run.check("5.4 color", "QColorDialog look-alike: fields follow the colour, live updates, OK returns, Cancel restores", async () => {
      await this.page.evaluate(() => {
        window.colorLive = [];
        window.colorResult = window.app.tomovisPage.ctx.dialogs.color({ initial: [255, 0, 0, 128], live: (c) => window.colorLive.push(c) });
      });
      await this.waitDialog(".tv-colordialog");
      const read = () => this.page.evaluate(() => [...document.querySelectorAll(".tv-colordialog__fields .tv-spin__input, .tv-colordialog__fields .tv-line")].map((n) => n.value));
      const start = await read();
      await this.page.locator(".tv-colordialog__well").first().locator(".tv-colordialog__cell").nth(5).click();
      const picked = await read();
      await H.shot(this.page, "color_dialog", "shell", { element: ".tv-colordialog" });
      await this.page.click(".tv-colordialog .tv-modal__buttons .tv-button >> text=OK");
      const ok = await this.page.evaluate(() => window.colorResult);

      await this.page.evaluate(() => {
        window.colorLive = [];
        window.colorResult = window.app.tomovisPage.ctx.dialogs.color({ initial: [10, 20, 30, 255], live: (c) => window.colorLive.push(c) });
      });
      await this.waitDialog(".tv-colordialog");
      await this.page.locator(".tv-colordialog__well").first().locator(".tv-colordialog__cell").nth(7).click();
      await this.page.keyboard.press("Escape");
      const cancel = await this.page.evaluate(() => window.colorResult);
      const live   = await this.page.evaluate(() => window.colorLive);

      R.equal(start, ["0", "255", "255", "0", "255", "0", "128", "#ff0000"], "fields for 255,0,0,128 (hue, red, sat, green, val, blue, alpha, html)");
      R.equal(picked.slice(1, 6).filter((_, k) => k % 2 === 0).length, 3, "picked fields");
      R.equal([ok.accepted, ok.color.length, ok.color[3]], [true, 4, 128], "OK result");
      R.equal([cancel.accepted, cancel.color], [false, [10, 20, 30, 255]], "Cancel result");
      R.equal(live[live.length - 1], [10, 20, 30, 255], "Cancel restores the initial colour through live");
      return `start ${start.join(",")}; basic colour 5 -> ${picked.join(",")}; OK ${JSON.stringify(ok.color)}; Cancel restores`;
    });
  }

  async expiry() {
    await this.run.check("3.1 expiry", "an expired session opens a fresh window with a warning", async () => {
      const old = await this.page.evaluate(() => window.app.tomovisPage.ctx.session.sid);
      await this.page.evaluate((sid) => fetch("/api/tomovis/close", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ sid }) }), old);
      await this.page.evaluate(() => window.app.tomovisPage.ctx.session.send({ type: "sync" }).catch(() => null));
      await this.page.waitForFunction((sid) => window.app.tomovisPage.ctx.session.sid && window.app.tomovisPage.ctx.session.sid !== sid, old, { timeout: 15000 });
      const toast = await this.page.textContent("#toast");
      const save  = (await this.control("saveFile")).enabled;
      R.equal([toast, save], ["TomoVis session expired; a new window was opened.", false], "expiry");
      this.expectedErrors = (this.expectedErrors || 0) + 1;
      return "new sid, startup state, warning toast";
    });
  }

  async scriptsPage() {
    await this.run.check("D-6 page", "TomoVis scripts page opens a scripts session and mounts both script views", async () => {
      await this.page.goto(`${H.base}/#/tomovis_scripts`);
      await this.page.waitForFunction(() => window.app.tomovisScriptsPage.ctx && window.app.tomovisScriptsPage.ctx.session.sid && window.app.tomovisScriptsPage.views.length === 2, null, { timeout: 30000 });
      const info = await this.page.evaluate(() => ({ kind: window.app.tomovisScriptsPage.ctx.session.kind, title: document.querySelector('[data-page="tomovis_scripts"] .page__title').textContent, views: window.app.tomovisScriptsPage.views.map((v) => v.constructor.name), nav: document.querySelector('a[data-route="tomovis_scripts"]').classList.contains("is-current") }));
      await H.shot(this.page, "d6_scripts_page", "shell");
      await this.page.goto(`${H.base}/#/tomovis`);
      await this.page.waitForTimeout(300);
      R.equal(info, { kind: "scripts", title: "TomoVis scripts", views: ["TomoVisSlicerScript", "TomoVisVolumeScript"], nav: true }, "scripts page");
      return JSON.stringify(info);
    });
  }

  async noWebGL() {
    await this.run.check("F-090", "without WebGL2 the 3D tab is absent and the server has three tabs", async () => {
      const bare = await H.launch({ port: this.options.port, gl: this.options.gl, webgl: false });
      await H.openTomoVis(bare.page);
      const tabs = await bare.page.$$eval(".tv-tab", (nodes) => nodes.filter((n) => !n.hidden).map((n) => n.textContent));
      const panel = await bare.page.$eval("#tv-panel-3d", (p) => p.hidden);
      const snapshot = await H.snapshot(bare.page);
      await H.shot(bare.page, "f090_no_webgl", "shell");
      this.errors.push(...bare.errors);
      await bare.browser.close();
      R.equal([tabs, panel, snapshot.controls.tabWidget.titles, snapshot.tab3d_index], [["Slicer", "Plot", "Profile"], true, ["Slicer", "Plot", "Profile"], null], "no WebGL2");
      return tabs.join(", ");
    });
  }

  async main() {
    const opened = await H.launch({ port: this.options.port, gl: this.options.gl });
    this.page = opened.page;
    await H.openTomoVis(this.page);

    await this.page01();
    await this.menus();
    await this.shortcutsBeforeData();
    await this.importChooser();
    await this.importAndChannels();
    await this.sessionDialogs();
    await this.timerAndPlay();
    await this.kitAgainstServer();
    await this.colorDialog();
    await this.expiry();
    await this.scriptsPage();
    await this.noWebGL();

    await opened.browser.close();
    const errors = [...opened.errors, ...this.errors].filter((e) => !(this.expectedErrors && e.includes("404 (Not Found)")));
    const ok = this.run.summary(errors);
    fs.writeFileSync(path.join(this.out, "shell_checks.json"), JSON.stringify({ results: this.run.results, errors }, null, 2));
    process.exit(ok ? 0 : 1);
  }
}

const options = H.args(process.argv);
options.original = process.env.TOMOVIS_ORIGINAL_SHOTS || path.join(REPO, "logs/tomovis_port/original_shots");
await new ShellChecks(options).main();
