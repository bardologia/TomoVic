import fs from "node:fs";
import path from "node:path";
import { TomoVisHarness as H, TomoVisCheckRun as R, REPO } from "./harness.mjs";

const LONG_PATH = "/home/bard/Bard/code/TomoVic/logs/tomovis_port/final_verify/shell-verify/sessions/ui_session.hd5";

class FinalShellChecks {
  static DIALOG = {
    body    : [645, 436],
    lookin  : [117, 11, 289, 32],
    back    : [412, 11, 32, 32],
    forward : [450, 11, 32, 32],
    parent  : [488, 11, 32, 32],
    folder  : [526, 11, 32, 32],
    list    : [564, 11, 32, 32],
    detail  : [602, 11, 32, 32],
    sidebar : [11, 49, 111, 300],
    frame   : [126, 49, 508, 300],
    name    : [117, 355, 431, 32],
    accept  : [554, 355, 80, 32],
    filter  : [117, 393, 431, 32],
    cancel  : [554, 393, 80, 32],
    header  : [["Name", 347, 28], ["Size", 81, 28], ["Type", 87, 28], ["Date Modified", 144, 28]],
    row     : 26,
    place   : 27,
  };

  static TYPES = [["sub", "", "Folder"], ["a.npy", "10 bytes", "npy File"], ["b.hd5", "10 bytes", "hd5 File"], ["c.h5", "10 bytes", "h5 File"], ["d.rat", "10 bytes", "rat File"], ["e.txt", "10 bytes", "txt File"], ["f", "10 bytes", "File"], ["g.png", "10 bytes", "png File"], ["h.json", "10 bytes", "json File"], ["i.HD5", "10 bytes", "HD5 File"], ["j.npz", "10 bytes", "npz File"], ["k.npy", "4.00 KiB", "npy File"]];

  static BOXES = {
    warning     : { spec: { level: "warning", title: "No data", text: "There is no data loaded to save." }, qt: { size: [326, 92], label: [62, 11, 253, 24], ok: [235, 49] } },
    information : { spec: { level: "information", title: "Save successful", text: `File saved successfully:\n${LONG_PATH}` }, qt: { size: [400, 160], label: [62, 11, 327, 94], ok: [309, 117] } },
    critical    : { spec: { level: "critical", title: "Import error", text: "Could not import file:\n[Errno 2] Unable to synchronously open file (unable to open file: name = 'x', errno = 2, error message = 'No such file or directory', flags = 0, o_flags = 0)" }, qt: { size: [400, 183], label: [62, 11, 327, 117], ok: [309, 140] } },
    title       : { spec: { level: "information", title: "A very long window title that is wider than the text", text: "Hi" }, qt: { size: [450, 92], label: [62, 11, 377, 24], ok: [359, 49] } },
    invalid     : { spec: { level: "information", title: "Invalid filename", text: '<b>The name "renamed" cannot be used.</b><p>Try using another name, with fewer characters or no punctuation marks.', rich: true }, qt: { size: [400, 149], label: [62, 11, 327, 83], ok: [309, 106] } },
    notfound    : { spec: { level: "warning", title: "Open File", text: "missing_file.hd5\nFile not found.\nPlease verify the correct file name was given." }, qt: { size: [400, 161], label: [62, 11, 327, 95], ok: [309, 118] } },
    replace     : { spec: { level: "warning", title: "Save File", text: "s.hd5 already exists.\nDo you want to replace it?", buttons: ["Yes", "No"] }, qt: { size: [280, 114], label: [62, 11, 207, 48], ok: [189, 71] } },
  };

  static OPENGL_OK     = "TomoVis: OpenGL context OK, version=(2, 0), profile=0";
  static OPENGL_FAILED = "TomoVis: QOpenGLContext.create() failed";

  constructor(options) {
    this.options = options;
    this.run     = new R("final-shell");
    this.inputs  = H.fixture("inputs");
    this.out     = H.shotDir("final-shell");
    this.errors  = [];
  }

  T(fn, arg) {
    return this.page.evaluate(fn, arg);
  }

  async fresh(width = 1100, height = 880) {
    await this.page.setViewportSize({ width, height });
    await this.page.goto("about:blank");
    await H.openTomoVis(this.page);
  }

  async serverLog() {
    const answer = await this.page.evaluate(() => fetch("/api/server-log?limit=400").then((r) => r.json()));
    return answer.lines.map((line) => line.message);
  }

  async sessionsSurvive() {
    await this.run.check("SH-01", "opening more TomoVis and scripts pages keeps a loaded window's session", async () => {
      await this.fresh();
      await H.menu(this.page, "File", "Import", "npy");
      await H.chooseFile(this.page, path.join(this.inputs, "npy_real.npy"));
      const before = await this.T(() => ({ sid: window.app.tomovisPage.ctx.session.sid, data: window.app.tomovisPage.ctx.session.snapshot.attributes.data_present, save: window.app.tomovisPage.ctx.session.snapshot.controls.saveFile.enabled, beat: window.app.tomovisPage.ctx.session.heartbeat !== null }));

      const others = [];
      for (let i = 0; i < 3; i += 1) {
        const other = await this.context.newPage();
        await H.openTomoVis(other);
        await other.goto(`${H.base}/#/tomovis_scripts`);
        await other.waitForFunction(() => window.app.tomovisScriptsPage.ctx && window.app.tomovisScriptsPage.ctx.session.sid, null, { timeout: 30000 });
        others.push(other);
      }

      await this.page.bringToFront();
      await this.page.click('[data-widget="tab1PlotButton"]');
      await H.waitIdle(this.page);
      await this.page.waitForTimeout(800);
      await H.waitIdle(this.page);
      const after = await this.T(() => ({ sid: window.app.tomovisPage.ctx.session.sid, data: window.app.tomovisPage.ctx.session.snapshot.attributes.data_present, save: window.app.tomovisPage.ctx.session.snapshot.controls.saveFile.enabled, tab: window.app.tomovisPage.ctx.session.snapshot.controls.tabWidget.index, toast: document.querySelector("#toast") ? document.querySelector("#toast").textContent : "" }));
      const alive = await this.T((sid) => fetch("/api/tomovis/alive", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ sid }) }).then((r) => r.status), after.sid);
      for (const other of others) await other.close();

      R.equal(before, { sid: before.sid, data: true, save: true, beat: true }, "window A loaded with its heartbeat armed");
      R.equal([after.sid, after.data, after.save, after.tab, alive], [before.sid, true, true, 1, 200], "window A after six more page sessions");
      R.assert(!after.toast.includes("expired"), `expiry toast shown: ${after.toast}`);
      return `sid ${before.sid.slice(0, 8)} kept with data after 6 more sessions; Plot went to tab 1; heartbeat route answers 200`;
    });
  }

  async openGlPrint() {
    await this.run.check("C-02", "each window session prints the startup OpenGL check line to the console log", async () => {
      const start = (await this.serverLog()).length;
      await this.fresh();
      const withGl = (await this.serverLog()).slice(start).filter((line) => line.includes("OpenGL") || line.includes("QOpenGLContext"));

      const bare = await H.launch({ port: this.options.port, gl: this.options.gl, webgl: false });
      await H.openTomoVis(bare.page);
      this.errors.push(...bare.errors);
      await bare.browser.close();
      const all     = await this.serverLog();
      const without = all.slice(all.lastIndexOf(withGl[withGl.length - 1]) + 1).filter((line) => line.includes("OpenGL") || line.includes("QOpenGLContext"));

      R.equal([withGl, without], [[FinalShellChecks.OPENGL_OK], [FinalShellChecks.OPENGL_FAILED]], "OpenGL check lines");
      return `${withGl[0]} | ${without[0]}`;
    });
  }

  async menuState() {
    return this.T(() => ({ menus: document.querySelectorAll(".tv-menu").length, modal: window.TomoVisModal.stack.length ? document.querySelector(".tv-modal:last-of-type .tv-modal__title").textContent : null, tab: window.app.tomovisPage.tabs.current, status: document.querySelector("#tv-status").textContent }));
  }

  async shortcutsInPopups() {
    await this.run.check("SH-04", "Ctrl+O and Ctrl+F do nothing while a menu or combo popup is open, as in the original", async () => {
      await this.fresh();
      await H.menu(this.page, "File", "Import", "npy");
      await H.chooseFile(this.page, path.join(this.inputs, "npy_real.npy"));
      await this.page.click('[data-widget="tab1PlotButton"]');
      await H.waitIdle(this.page);
      const seen = {};
      for (const [menu, keys] of [["file", "Control+o"], ["data", "Control+o"], ["file", "Control+f"], ["data", "Control+f"]]) {
        await this.page.click(`.tv-menubar__item[data-menu="${menu}"]`);
        await this.page.keyboard.press(keys);
        await this.page.waitForTimeout(300);
        await H.waitIdle(this.page);
        seen[`${menu} ${keys}`] = await this.menuState();
        await this.page.keyboard.press("Escape");
      }
      await this.page.click('[data-widget="tab2ComboBox"]');
      await this.page.keyboard.press("Control+o");
      await this.page.waitForTimeout(300);
      seen["combo Control+o"] = { ...(await this.menuState()), popup: await this.T(() => document.querySelectorAll(".tv-combo__popup").length) };
      await this.page.keyboard.press("Escape");
      await this.page.keyboard.press("Control+o");
      await this.page.waitForSelector(".tv-filedialog");
      seen["no popup Control+o"] = await this.menuState();
      await this.page.keyboard.press("Escape");
      await this.page.waitForSelector(".tv-filedialog", { state: "detached" });
      await H.waitIdle(this.page);

      for (const key of ["file Control+o", "data Control+o", "file Control+f", "data Control+f"]) R.equal([seen[key].menus, seen[key].modal, seen[key].tab], [1, null, 1], `${key} with the menu open`);
      R.equal([seen["combo Control+o"].popup, seen["combo Control+o"].modal, seen["combo Control+o"].tab], [1, null, 1], "Ctrl+O with the colormap combo open");
      R.equal([seen["no popup Control+o"].menus, seen["no popup Control+o"].modal], [0, "Open File"], "control case without a popup");
      return "menu stays open, no dialog, tab stays Plot; without a popup Ctrl+O opens Open File";
    });
  }

  async statusAfterSubmenu() {
    await this.run.check("SH-05", "the status tip clears when ArrowLeft or Escape leaves the Import submenu", async () => {
      await this.fresh();
      const sequences = {
        left           : ["ArrowDown", "ArrowDown", "ArrowRight", "ArrowDown", "ArrowDown", "ArrowLeft"],
        escape         : ["ArrowDown", "ArrowDown", "ArrowRight", "ArrowDown", "ArrowDown", "Escape"],
        left_then_down : ["ArrowDown", "ArrowDown", "ArrowRight", "ArrowDown", "ArrowDown", "ArrowLeft", "ArrowUp"],
      };
      const seen = {};
      for (const [name, keys] of Object.entries(sequences)) {
        await this.page.click('.tv-menubar__item[data-menu="file"]');
        const steps = [(await this.menuState()).status];
        for (const key of keys) {
          await this.page.keyboard.press(key);
          steps.push((await this.menuState()).status);
        }
        const active = await this.T(() => [...document.querySelectorAll(".tv-menu")].map((m) => { const row = m.querySelector(".tv-menu__item.is-active .tv-menu__text"); return row ? row.textContent : null; }));
        seen[name] = { steps, active };
        await this.closeMenus();
      }
      const original = ["", "Open File", "", "Import hd5 file", "Import rat file", "Import h5 file"];
      R.equal(seen.left, { steps: [...original, ""], active: ["Import"] }, "Left");
      R.equal(seen.escape, { steps: [...original, ""], active: ["Import"] }, "Escape");
      R.equal(seen.left_then_down.steps, [...original, "", "Open File"], "Left then Up");
      return "status tips match the original's sequences, '' after leaving the submenu";
    });
  }

  async closeMenus() {
    await this.T(() => { if (window.TomoVisMenu.root) window.TomoVisMenu.root.close(); });
  }

  async dialogDir() {
    await this.page.waitForSelector(".tv-filedialog[data-dir]", { timeout: 15000 });
    return this.T(() => document.querySelector(".tv-filedialog").dataset.dir);
  }

  async browseTo(dir) {
    await this.page.fill(".tv-filedialog__name", dir);
    await this.page.press(".tv-filedialog__name", "Enter");
    await this.page.waitForFunction((d) => document.querySelector(".tv-filedialog").dataset.dir === d, dir, { timeout: 10000 });
  }

  async cancelDialog() {
    await this.page.click(".tv-filedialog__cancel");
    await this.page.waitForSelector(".tv-filedialog", { state: "detached" });
    await H.waitIdle(this.page);
  }

  async lastVisited() {
    await this.run.check("SH-03", "the chooser reopens the last folder browsed to, also after Cancel and after a failed save, for this page only", async () => {
      await this.fresh();
      const home     = await this.T(() => fetch("/api/tomovis/fs").then((r) => r.json()).then((l) => l.home));
      const sessions = path.join(this.out, "sessions");
      fs.mkdirSync(sessions, { recursive: true });
      const seen = {};

      await H.menu(this.page, "File", "Import", "npy");
      seen.first = await this.dialogDir();
      await this.browseTo(this.inputs);
      await this.cancelDialog();
      await H.menu(this.page, "File", "Import", "npy");
      seen.second = await this.dialogDir();
      await this.page.fill(".tv-filedialog__name", "npy_real.npy");
      await this.page.click(".tv-filedialog__accept");
      await this.page.waitForSelector(".tv-filedialog", { state: "detached" });
      await H.waitIdle(this.page);

      await H.menu(this.page, "File", "Save");
      seen.save = await this.dialogDir();
      await this.browseTo(sessions);
      await this.page.fill(".tv-filedialog__name", path.join(sessions, "no_such_folder", "x.hd5"));
      await this.page.click(".tv-filedialog__accept");
      await this.page.waitForSelector(".tv-messagebox");
      seen.error = await this.T(() => document.querySelector(".tv-messagebox .tv-modal__title").textContent);
      await this.page.click('.tv-messagebox .tv-button:text-is("OK")');
      await H.waitIdle(this.page);
      await H.menu(this.page, "File", "Import", "npy");
      seen.afterFailedSave = await this.dialogDir();
      await this.cancelDialog();

      await this.page.reload();
      await H.openTomoVis(this.page);
      await H.menu(this.page, "File", "Import", "npy");
      seen.afterReload = await this.dialogDir();
      await this.cancelDialog();

      R.equal(seen, { first: home, second: this.inputs, save: this.inputs, error: "Save error", afterFailedSave: sessions, afterReload: home }, "start folders");
      return JSON.stringify(seen);
    });
  }

  async dialogGeometry() {
    return this.T(() => {
      const body = document.querySelector(".tv-filedialog .tv-modal__body").getBoundingClientRect();
      const rect = (selector) => { const b = document.querySelector(selector).getBoundingClientRect(); return [Math.round(b.left - body.left), Math.round(b.top - body.top), Math.round(b.width), Math.round(b.height)]; };
      return {
        body    : [Math.round(body.width), Math.round(body.height)],
        lookin  : rect(".tv-filedialog__lookin"),
        back    : rect(".tv-filedialog__back"),
        forward : rect(".tv-filedialog__forward"),
        parent  : rect(".tv-filedialog__parent"),
        folder  : rect(".tv-filedialog__newfolder"),
        list    : rect(".tv-filedialog__listmode"),
        detail  : rect(".tv-filedialog__detailmode"),
        sidebar : rect(".tv-filedialog__sidebar"),
        frame   : rect(".tv-filedialog__list"),
        name    : rect(".tv-filedialog__name"),
        accept  : rect(".tv-filedialog__accept"),
        filter  : rect(".tv-filedialog__filter"),
        cancel  : rect(".tv-filedialog__cancel"),
        header  : [...document.querySelectorAll(".tv-filedialog__table th")].map((th) => [th.textContent, Math.round(th.getBoundingClientRect().width), Math.round(th.getBoundingClientRect().height)]),
        row     : Math.round(document.querySelector(".tv-filedialog__table tbody tr").getBoundingClientRect().height),
        place   : Math.round(document.querySelector(".tv-filedialog__place").getBoundingClientRect().height),
      };
    });
  }

  async dialogParts() {
    return this.T(() => {
      const dialog = document.querySelector(".tv-filedialog");
      return {
        tools   : [...dialog.querySelectorAll(".tv-filedialog__top .tv-button--tool")].map((b) => [b.title, !b.disabled, b.classList.contains("is-checked")]),
        places  : [...dialog.querySelectorAll(".tv-filedialog__place")].map((r) => [r.textContent, r.classList.contains("is-selected")]),
        lookin  : dialog.querySelector(".tv-filedialog__lookin").dataset.path,
        rows    : [...dialog.querySelectorAll(".tv-filedialog__table tbody tr")].map((r) => [...r.children].map((c) => c.textContent)),
        items   : [...dialog.querySelectorAll(".tv-filedialog__item")].map((r) => [r.textContent, Math.round(r.getBoundingClientRect().left), Math.round(r.getBoundingClientRect().top)]),
        view    : dialog.dataset.view,
        labels  : [...dialog.querySelectorAll(".tv-label")].map((l) => l.textContent),
      };
    });
  }

  async popupItems() {
    await this.page.click(".tv-filedialog__lookin");
    await this.page.waitForSelector(".tv-filedialog__lookinpopup");
    const items = await this.T(() => [...document.querySelectorAll(".tv-filedialog__lookinpopup .tv-combo__option")].map((o) => [o.textContent, !o.classList.contains("is-disabled")]));
    return items;
  }

  async fileDialogParts() {
    const types = path.join(this.out, "types");
    fs.rmSync(types, { recursive: true, force: true });
    fs.mkdirSync(path.join(types, "sub"), { recursive: true });
    for (const name of ["a.npy", "b.hd5", "c.h5", "d.rat", "e.txt", "f", "g.png", "h.json", "i.HD5", "j.npz"]) fs.writeFileSync(path.join(types, name), "x".repeat(10));
    fs.writeFileSync(path.join(types, "k.npy"), Buffer.alloc(4096));

    await this.run.check("SH-02 parts", "the file dialog has Qt's geometry, tool buttons, places sidebar, Type column and Date Modified format", async () => {
      await this.fresh();
      await this.T(() => { window.localStorage.removeItem("tomovis.fileDialogHistory"); window.localStorage.removeItem("tomovis.fileDialogViewMode"); });
      await H.menu(this.page, "File", "Import", "npy");
      await this.dialogDir();
      await this.browseTo(this.inputs);
      const geometry = await this.dialogGeometry();
      const parts    = await this.dialogParts();
      await H.shot(this.page, "sh02_import_dialog", "final-shell", { element: ".tv-filedialog" });
      const home = await this.T(() => fetch("/api/tomovis/fs").then((r) => r.json()).then((l) => l.home));
      await this.cancelDialog();

      const typed = await this.allFiles(types);
      await this.cancelDialog();

      R.equal(geometry, FinalShellChecks.DIALOG, "dialog geometry against Qt's 645x436 non-native dialog");
      R.equal(parts.tools, [["Back", true, false], ["Forward", false, false], ["Parent Directory", true, false], ["Create New Folder", true, false], ["List View", true, false], ["Detail View", true, true]], "tool buttons: title, enabled, down");
      R.equal(parts.places, [["Computer", false], [path.basename(home), false]], "places sidebar");
      R.equal(parts.labels, ["Look in:", "File name:", "Files of type:"], "labels");
      R.assert(parts.rows.length > 0 && parts.rows.every((r) => r[2] === "npy File"), `npy rows: ${JSON.stringify(parts.rows)}`);
      R.equal(typed.rows.map((r) => [r[0], r[1], r[2]]), FinalShellChecks.TYPES, "Name, Size and Type columns against Qt");
      R.assert(typed.rows.every((r) => /^\d{1,2}\/\d{1,2}\/(\d{2} \d{1,2}|\u2026)?:?\d{2} (AM|PM)$/.test(r[3])), `Date Modified not in Qt's M/d/yy h:mm AP, elided in the middle where Qt elides it: ${typed.rows.map((r) => r[3]).join(", ")}`);
      return `geometry equal to Qt's; ${typed.rows.length} typed rows equal; dates like ${typed.rows[0][3]}`;
    });
  }

  async allFiles(directory) {
    await this.T((dir) => { window.app.tomovisPage.ctx.dialogs.file({ mode: "open", title: "Open File", filters: [], directory: dir }); }, directory);
    await this.page.waitForFunction((dir) => document.querySelector(".tv-filedialog") && document.querySelector(".tv-filedialog").dataset.dir === dir, directory, { timeout: 10000 });
    return this.dialogParts();
  }

  ancestors(dir) {
    const out = [];
    for (let at = dir; ; at = path.dirname(at)) {
      out.push([at, true]);
      if (at === "/") break;
    }
    return [...out, ["Computer", true]];
  }

  async lookInHistory() {
    const types = path.join(this.out, "types");
    await this.run.check("SH-02 look in", "Look in is a drop-down of the folder, its ancestors, Computer and Qt's Recent Places from earlier dialogs", async () => {
      await this.fresh();
      await this.T(() => window.localStorage.removeItem("tomovis.fileDialogHistory"));
      const sub = path.join(types, "sub");
      await this.allFiles(sub);
      const first   = await this.popupItems();
      const editable = await this.T(() => document.querySelector(".tv-filedialog__lookin").tagName);
      await this.page.click(`.tv-filedialog__lookinpopup .tv-combo__option >> nth=1`);
      await this.page.waitForFunction((d) => document.querySelector(".tv-filedialog").dataset.dir === d, types);
      const back = await this.T(() => !document.querySelector(".tv-filedialog__back").disabled);
      await this.cancelDialog();

      await this.allFiles(this.inputs);
      const second = await this.popupItems();
      await this.page.keyboard.press("Escape");
      const stillOpen = await this.T(() => Boolean(document.querySelector(".tv-filedialog")) && !document.querySelector(".tv-filedialog__lookinpopup"));
      await this.cancelDialog();

      const missing = path.join(this.out, "no_such_place");
      await this.T((m) => window.localStorage.setItem("tomovis.fileDialogHistory", JSON.stringify([m])), missing);
      await this.allFiles(this.inputs);
      const items = await this.popupItems();
      await this.page.click(`.tv-filedialog__lookinpopup .tv-combo__option >> nth=${items.length - 1}`);
      await this.page.waitForSelector(".tv-messagebox");
      const warning = await this.T(() => [document.querySelector(".tv-messagebox .tv-modal__title").textContent, document.querySelector(".tv-messagebox__text").textContent]);
      await this.page.click('.tv-messagebox .tv-button:text-is("OK")');
      const dir = await this.dialogDir();
      await this.cancelDialog();

      R.equal(editable, "DIV", "Look in is not editable");
      R.equal(first, this.ancestors(sub), "first dialog: folder, ancestors and Computer, no Recent Places");
      R.equal(back, true, "choosing an ancestor is a navigation Back can undo");
      R.equal(second, [...this.ancestors(this.inputs), ["Recent Places", false], [types, true]], "second dialog lists the first dialog's folder under Recent Places");
      R.equal(stillOpen, true, "Escape closes the popup, not the dialog");
      R.equal([warning, dir], [["Open File", `${missing}\nDirectory not found.\nPlease verify the correct directory name was given.`], this.inputs], "a missing recent place warns and stays");
      return `${first.length} items, then Recent Places [${types}]; missing place warns`;
    });
  }

  async computerPlace() {
    await this.run.check("SH-02 computer", "the Computer place lists the root as a Drive; Parent of / goes to Computer", async () => {
      await this.fresh();
      await this.allFiles(this.inputs);
      await this.page.click(".tv-filedialog__place >> nth=0");
      await this.page.waitForFunction(() => document.querySelector(".tv-filedialog").dataset.dir === "computer:");
      const computer = await this.dialogParts();
      await H.shot(this.page, "sh02_computer", "final-shell", { element: ".tv-filedialog" });
      await this.page.dblclick(".tv-filedialog__table tbody tr");
      await this.page.waitForFunction(() => document.querySelector(".tv-filedialog").dataset.dir === "/");
      const root = await this.dialogParts();
      await this.page.click(".tv-filedialog__parent");
      await this.page.waitForFunction(() => document.querySelector(".tv-filedialog").dataset.dir === "computer:");
      await this.page.click(".tv-filedialog__place >> nth=1");
      await this.page.waitForFunction(() => document.querySelector(".tv-filedialog").dataset.dir !== "computer:");
      const home = await this.dialogParts();
      await this.cancelDialog();

      R.equal([computer.lookin, computer.rows.map((r) => r.slice(0, 3)), computer.tools[2][1], computer.tools[3][1], computer.places.map((p) => p[1])], ["computer:", [["/", "", "Drive"]], false, false, [true, false]], "Computer: one Drive row, Parent and New Folder disabled, Computer selected");
      R.equal([root.tools[2][1], root.tools[3][1]], [true, false], "at /: Parent enabled, New Folder disabled (not writable)");
      R.equal(home.places.map((p) => p[1]), [false, true], "home place selected after clicking it");
      return "Computer, /, Parent, home";
    });
  }

  async newFolder() {
    await this.run.check("SH-02 new folder", "Create New Folder names folders as Qt does, edits the name in place, and a session saves into the new folder", async () => {
      const made = path.join(this.out, "mk");
      fs.rmSync(made, { recursive: true, force: true });
      fs.mkdirSync(made, { recursive: true });
      const disk = () => fs.readdirSync(made).sort();
      await this.fresh();
      await this.allFiles(made);

      await this.page.click(".tv-filedialog__newfolder");
      await this.page.waitForSelector(".tv-filedialog__editor");
      const editing = await this.T(() => { const e = document.querySelector(".tv-filedialog__editor"); return [e.value, e.selectionStart, e.selectionEnd, document.activeElement === e, Boolean(document.querySelector(".tv-filedialog__table tbody tr.is-selected .tv-filedialog__editor"))]; });
      await H.shot(this.page, "sh02_new_folder_editing", "final-shell", { element: ".tv-filedialog" });
      await this.page.keyboard.type("renamed");
      await this.page.keyboard.press("Enter");
      await this.page.waitForFunction(() => !document.querySelector(".tv-filedialog__editor"));
      await H.waitIdle(this.page);
      await this.page.waitForTimeout(300);
      const first = disk();
      const selected = await this.T(() => document.querySelector(".tv-filedialog__table tbody tr.is-selected").textContent.slice(0, 7));

      await this.page.click(".tv-filedialog__newfolder");
      await this.page.waitForSelector(".tv-filedialog__editor");
      await this.page.keyboard.press("Escape");
      await this.page.waitForFunction(() => !document.querySelector(".tv-filedialog__editor"));
      const dialogOpen = await this.T(() => Boolean(document.querySelector(".tv-filedialog")));
      await this.page.click(".tv-filedialog__newfolder");
      await this.page.waitForSelector(".tv-filedialog__editor");
      await this.page.keyboard.press("Enter");
      await this.page.waitForFunction(() => !document.querySelector(".tv-filedialog__editor"));
      await this.page.waitForTimeout(300);
      const three = disk();

      await this.page.click(".tv-filedialog__newfolder");
      await this.page.waitForSelector(".tv-filedialog__editor");
      await this.page.keyboard.type("renamed");
      await this.page.keyboard.press("Enter");
      await this.page.waitForSelector(".tv-messagebox");
      const box = await this.T(() => [document.querySelector(".tv-messagebox").dataset.level, document.querySelector(".tv-messagebox .tv-modal__title").textContent, document.querySelector(".tv-messagebox__text b").textContent, document.querySelector(".tv-messagebox__text p").textContent]);
      await H.shot(this.page, "sh02_invalid_name", "final-shell");
      await this.page.click('.tv-messagebox .tv-button:text-is("OK")');
      await this.page.waitForTimeout(300);
      const clash = disk();
      await this.cancelDialog();

      await H.menu(this.page, "File", "Import", "npy");
      await H.chooseFile(this.page, path.join(this.inputs, "npy_real.npy"));
      await H.menu(this.page, "File", "Save");
      await this.dialogDir();
      await this.browseTo(made);
      await this.page.click(".tv-filedialog__newfolder");
      await this.page.waitForSelector(".tv-filedialog__editor");
      await this.page.keyboard.type("brand_new");
      await this.page.keyboard.press("Enter");
      await this.page.waitForFunction(() => !document.querySelector(".tv-filedialog__editor"));
      await this.page.waitForTimeout(300);
      await this.page.fill(".tv-filedialog__name", "brand_new/s.hd5");
      await this.page.click(".tv-filedialog__accept");
      await this.page.waitForSelector(".tv-messagebox");
      const saved = await this.T(() => document.querySelector(".tv-messagebox .tv-modal__title").textContent);
      await this.page.click('.tv-messagebox .tv-button:text-is("OK")');
      await H.waitIdle(this.page);

      R.equal(editing, ["New Folder", 0, 10, true, true], "editor on the selected new folder with its name selected");
      R.equal([first, selected], [["renamed"], "renamed"], "Enter renames and keeps the folder selected");
      R.equal([dialogOpen, three], [true, ["New Folder", "New Folder2", "renamed"]], "Escape keeps New Folder and the dialog; the next is New Folder2");
      R.equal(box, ["information", "Invalid filename", 'The name "renamed" cannot be used.', "Try using another name, with fewer characters or no punctuation marks."], "QFileSystemModel's message on a taken name");
      R.equal(clash, ["New Folder", "New Folder2", "New Folder3", "renamed"], "folders after the refused rename, as in the original");
      R.equal([saved, fs.existsSync(path.join(made, "brand_new", "s.hd5"))], ["Save successful", true], "a session saves into a folder made in the Save dialog");
      return `${clash.join(", ")}, brand_new/s.hd5`;
    });
  }

  async viewModes() {
    await this.run.check("SH-02 views", "List View lays the entries out top to bottom in columns; the view mode carries to the next dialog", async () => {
      const types = path.join(this.out, "types");
      await this.fresh();
      await this.allFiles(types);
      await this.page.click(".tv-filedialog__listmode");
      const list = await this.dialogParts();
      await H.shot(this.page, "sh02_list_view", "final-shell", { element: ".tv-filedialog" });
      await this.cancelDialog();
      await this.allFiles(types);
      const next = await this.dialogParts();
      await this.page.click(".tv-filedialog__detailmode");
      const detail = await this.dialogParts();
      await this.cancelDialog();

      const columns = [...new Set(list.items.map((i) => i[1]))];
      const firstColumn = list.items.filter((i) => i[1] === columns[0]).map((i) => i[0]);
      R.equal([list.view, list.tools[4][2], list.tools[5][2]], ["List", true, false], "List View down");
      R.assert(columns.length >= 1 && list.items.every((item, k) => k === 0 || item[1] > list.items[k - 1][1] || item[2] === list.items[k - 1][2] + 27), `items do not flow top to bottom in 27 px rows: ${JSON.stringify(list.items)}`);
      R.equal(firstColumn[0], "sub", "folders first");
      R.equal([next.view, detail.view, detail.rows.length], ["List", "Detail", 12], "view mode remembered, Detail restores the table");
      return `${list.items.length} items in ${columns.length} column(s)`;
    });
  }

  async messageBox(page, spec) {
    await page.evaluate((s) => { window.TomoVisMessageBox.show({ ...s, layer: window.app.tomovisPage.ctx.layer }); }, spec);
    await page.waitForSelector(".tv-messagebox");
    const box = await page.evaluate(() => {
      const el    = document.querySelector(".tv-messagebox");
      const body  = el.querySelector(".tv-modal__body").getBoundingClientRect();
      const foot  = el.querySelector(".tv-modal__buttons").getBoundingClientRect();
      const label = el.querySelector(".tv-messagebox__text");
      const rect  = label.getBoundingClientRect();
      const last  = [...el.querySelectorAll(".tv-modal__buttons .tv-button")].pop().getBoundingClientRect();
      return { size: [Math.round(body.width), Math.round(foot.bottom - body.top)], label: [Math.round(rect.left - body.left), Math.round(rect.top - body.top), Math.round(rect.width), Math.round(rect.height)], ok: [Math.round(last.left - body.left), Math.round(last.top - body.top)], lineHeight: parseFloat(getComputedStyle(label).lineHeight) || 23, title: Boolean(el.querySelector(".tv-modal__title")), wrapped: label.classList.contains("is-wrapped"), breaks: label.querySelectorAll("wbr").length };
    });
    await page.keyboard.press("Escape");
    await page.waitForSelector(".tv-messagebox", { state: "detached" });
    return box;
  }

  async messageBoxes() {
    await this.run.check("LS-15 Qt", "message boxes follow QMessageBox's size rules: with Qt's font and an 800 px screen they match the original within 3 px", async () => {
      const context = await this.browser.newContext({ viewport: { width: 1100, height: 880 }, screen: { width: 800, height: 600 }, deviceScaleFactor: 1 });
      const page    = await context.newPage();
      page.on("pageerror", (error) => this.errors.push(`pageerror: ${error.message}`));
      await H.openTomoVis(page);
      await page.addStyleTag({ content: '.tv-messagebox, .tv-messagebox .tv-modal__title, .tv-messagebox .tv-button { font-family: "Noto Sans"; font-size: 17px; font-weight: 400; line-height: normal; }' });
      const seen = {};
      for (const [key, { spec }] of Object.entries(FinalShellChecks.BOXES)) seen[key] = await this.messageBox(page, spec);
      await context.close();

      const off = [];
      for (const [key, { qt }] of Object.entries(FinalShellChecks.BOXES)) {
        const got = seen[key];
        const pairs = [...got.size.map((v, i) => [v, qt.size[i]]), ...got.label.map((v, i) => [v, qt.label[i]]), ...got.ok.map((v, i) => [v, qt.ok[i]])];
        if (pairs.some(([a, b]) => Math.abs(a - b) > 3)) off.push(`${key}: ${JSON.stringify(got)} vs ${JSON.stringify(qt)}`);
        const lines = Math.round(got.label[3] / 23);
        const qtLines = Math.round(qt.label[3] / 23);
        if (lines !== qtLines) off.push(`${key}: ${lines} lines vs Qt's ${qtLines}`);
      }
      R.assert(off.length === 0, off.join("\n"));
      return Object.entries(seen).map(([k, v]) => `${k} ${v.size.join("x")}`).join(", ");
    });

    await this.run.check("LS-15 port", "with TomoVic's font the boxes are sized to their text, wrap paths after '/', and keep the title bar as the window frame", async () => {
      await this.fresh();
      const screen = await this.T(() => window.screen.availWidth);
      const soft   = Math.min(screen / 2, 500);
      const warn   = await this.messageBox(this.page, FinalShellChecks.BOXES.warning.spec);
      const info   = await this.messageBox(this.page, FinalShellChecks.BOXES.information.spec);
      const crit   = await this.messageBox(this.page, FinalShellChecks.BOXES.critical.spec);
      await this.T((s) => { window.TomoVisMessageBox.show({ ...s, layer: window.app.tomovisPage.ctx.layer }); }, FinalShellChecks.BOXES.critical.spec);
      await this.page.waitForSelector(".tv-messagebox");
      await H.shot(this.page, "ls15_critical", "final-shell", { element: ".tv-messagebox" });
      await this.page.keyboard.press("Escape");

      R.assert(warn.size[0] < 300 && warn.size[0] === warn.label[2] + 73 && !warn.wrapped, `warning box not sized to its text: ${JSON.stringify(warn)}`);
      R.equal([info.size[0], info.wrapped, info.breaks > 5, crit.size[0], crit.wrapped], [soft, true, true, soft, true], "long texts wrap at Qt's soft limit");
      R.assert(crit.label[3] > 2 * crit.lineHeight, `critical text not wrapped onto three or more lines: ${JSON.stringify(crit)}`);
      R.equal([warn.title, info.ok[0], info.size[1] - info.ok[1]], [true, soft - 91, 43], "title bar, OK button 11 px from the right and bottom");
      return `warning ${warn.size.join("x")}, information ${info.size.join("x")}, critical ${crit.size.join("x")}`;
    });
  }

  async normalizeRgb() {
    await this.run.check("SH-07 E-010", "Subtract with Frame, Time range or ROI on the RGB pane works in float32, where the original raised UFuncTypeError", async () => {
      const seen = {};
      for (const [op, mean] of [["Subtract", null], ["Subtract", "Frame"], ["Subtract", "Time range"], ["Subtract", "ROI"], ["Divide", "Frame"]]) {
        await this.fresh();
        await H.menu(this.page, "File", "Import", "npy");
        await H.chooseFile(this.page, path.join(this.inputs, "npy_channels_3.npy"));
        const pane = '.tv-slicer__pane[data-view="imv1_2"]';
        await this.page.locator(`${pane} .tv-pg-btn`).nth(1).click();
        await this.page.locator(".tv-menu .tv-menu__item", { hasText: "Normalization" }).click();
        if (mean) await this.page.locator(`${pane} .tv-check`, { hasText: mean }).click();
        const before = this.pageErrors.length;
        await this.page.locator(`${pane} .tv-radio`, { hasText: op }).click();
        await this.page.waitForTimeout(250);
        const view = await this.T(() => { const iv = window.app.tomovisPage.views[0].views.imv1_2; return { dtype: iv.imageDisp ? iv.imageDisp.dtype : null, shape: iv.imageDisp ? iv.imageDisp.shape : null }; });
        seen[`${op}${mean ? ` + ${mean}` : ""}`] = { ...view, errors: this.pageErrors.length - before };
      }
      R.assert(Object.values(seen).every((v) => v.dtype === "float32" && v.errors === 0), JSON.stringify(seen));
      return Object.entries(seen).map(([k, v]) => `${k}: ${v.dtype}`).join(", ");
    });
  }

  async readmeDocuments() {
    await this.run.check("docs", "the package README lists E-010, the colours and fonts, the matplotlib version and the AVIF divergence", async () => {
      const readme = fs.readFileSync(path.join(REPO, "webui/tomovis/README.md"), "utf-8");
      const rows   = readme.split("\n").filter((line) => line.startsWith("| "));
      const row    = (needle) => rows.find((line) => line.includes(needle)) || "";
      const fonts  = row("Colours and fonts");
      const mpl    = row("matplotlib version");
      const avif   = row("Save as AVIF");
      R.assert(row("| E-010 |").includes("UFuncTypeError") && row("| E-010 |").includes("float32"), "E-010 crash-fix row");
      R.assert(["Fusion", "#efefef", "Archivo", "JetBrains Mono", "Serif", "Noto Sans"].every((word) => fonts.includes(word)), `colours and fonts row: ${fonts}`);
      R.assert(["3.10.8", "3.11.2", "FreeType 2.6.1", "FreeType 2.14.3", "okabe_ito", "1 to 2 px"].every((word) => mpl.includes(word)), `matplotlib row: ${mpl}`);
      R.assert(avif.includes("writes the file in the port") && avif.includes("does not support avif"), `AVIF row: ${avif}`);
      R.assert(!/original (wrote|writes) AVIF/i.test(readme), "README still claims the original wrote AVIF");
      return "rows present";
    });
  }

  async main() {
    const opened = await H.launch({ port: this.options.port, gl: this.options.gl, viewport: { width: 1100, height: 880 } });
    this.options.base = opened.base;
    this.context = opened.context;
    this.browser = opened.browser;
    this.page    = opened.page;
    this.pageErrors = opened.errors;
    await H.openTomoVis(this.page);

    if (this.wanted("sessions")) await this.sessionsSurvive();
    if (this.wanted("opengl")) await this.openGlPrint();
    if (this.wanted("shortcuts")) await this.shortcutsInPopups();
    if (this.wanted("status")) await this.statusAfterSubmenu();
    if (this.wanted("lastdir")) await this.lastVisited();
    if (this.wanted("dialog")) await this.fileDialogParts();
    if (this.wanted("lookin")) await this.lookInHistory();
    if (this.wanted("computer")) await this.computerPlace();
    if (this.wanted("newfolder")) await this.newFolder();
    if (this.wanted("views")) await this.viewModes();
    if (this.wanted("messages")) await this.messageBoxes();
    if (this.wanted("normalize")) await this.normalizeRgb();
    if (this.wanted("docs")) await this.readmeDocuments();

    await opened.browser.close();
    const errors = [...opened.errors, ...this.errors];
    const ok     = this.run.summary(errors);
    fs.writeFileSync(path.join(this.out, "final_shell_checks.json"), JSON.stringify({ results: this.run.results, errors }, null, 2));
    process.exit(ok ? 0 : 1);
  }

  wanted(name) {
    return this.options.only.length === 0 || this.options.only.includes(name);
  }
}

await new FinalShellChecks(H.args(process.argv, "final-shell")).main();
