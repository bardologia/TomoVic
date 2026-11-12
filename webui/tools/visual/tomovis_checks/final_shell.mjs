import fs from "node:fs";
import path from "node:path";
import { TomoVisHarness as H, TomoVisCheckRun as R } from "./harness.mjs";

class FinalShellChecks {
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

  async main() {
    const opened = await H.launch({ port: this.options.port, gl: this.options.gl, viewport: { width: 1100, height: 880 } });
    this.options.base = opened.base;
    this.context = opened.context;
    this.page    = opened.page;
    await H.openTomoVis(this.page);

    if (this.wanted("sessions")) await this.sessionsSurvive();
    if (this.wanted("opengl")) await this.openGlPrint();
    if (this.wanted("shortcuts")) await this.shortcutsInPopups();
    if (this.wanted("status")) await this.statusAfterSubmenu();

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
