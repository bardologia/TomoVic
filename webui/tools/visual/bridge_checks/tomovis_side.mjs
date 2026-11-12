import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { TomoVisHarness as H, TomoVisCheckRun as R, REPO } from "../tomovis_checks/harness.mjs";

const BUILDER   = "tomovis-ui";
const OUT       = path.join(REPO, "logs/bridge", BUILDER);
const SHOTS     = path.join(OUT, "shots");
const RUN       = "/home/bard/Bard/code/DLR-TomoSAR/test_data";
const RUN_SHAPE = [150, 1000, 500];

class TomoVisSideChecks {
  constructor(options) {
    this.options  = options;
    this.run      = new R("tomovis_side");
    this.errors   = [];
    this.inputs   = H.fixture("inputs");
    this.fixtures = path.join(OUT, "fixtures", `${Date.now()}`);
    this.ids      = {};
    this.shapes   = {};
  }

  async launch() {
    const opened = await H.launch({ port: this.options.port, gl: this.options.gl, viewport: { width: 1440, height: 1000 } });
    await opened.context.addInitScript(([run]) => {
      window.__tvbFileDialogs = 0;
      new MutationObserver((records) => {
        for (const record of records) {
          for (const node of record.addedNodes) {
            if (node.nodeType === 1 && (node.matches(".tv-filedialog") || node.querySelector(".tv-filedialog"))) window.__tvbFileDialogs += 1;
          }
        }
      }).observe(document, { childList: true, subtree: true });
      try {
        localStorage.setItem("results-sources", JSON.stringify({ datasets: run, logs: run }));
      } catch (error) {
        console.warn(`results-sources not stored: ${error.message}`);
      }
    }, [RUN]);
    return opened;
  }

  watch(page, label) {
    page.on("console", (message) => {
      if (message.type() === "error") this.errors.push(`${label} console: ${message.text()}`);
    });
    page.on("pageerror", (error) => this.errors.push(`${label} pageerror: ${error.message}`));
  }

  T(fn, arg, page = this.page) {
    return page.evaluate(fn, arg);
  }

  async shot(name, page = this.page) {
    fs.mkdirSync(SHOTS, { recursive: true });
    await page.screenshot({ path: path.join(SHOTS, `${name}.png`) });
  }

  async post(url, body, page = this.page) {
    return this.T(async ([u, b]) => {
      const res = await fetch(u, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(b) });
      return { status: res.status, body: await res.json() };
    }, [url, body], page);
  }

  async get(url, page = this.page) {
    return this.T(async (u) => (await fetch(u)).json(), url, page);
  }

  async sid(page = this.page) {
    return this.T(() => window.app.tomovisPage.ctx.session.sid, null, page);
  }

  async current(page = this.page) {
    const sid = await this.sid(page);
    return this.get(`/api/workspace/current?sid=${encodeURIComponent(sid)}`, page);
  }

  async dataset(id) {
    return (await this.get(`/api/workspace/dataset?id=${encodeURIComponent(id)}`)).dataset;
  }

  async use(id, page = this.page) {
    const answer = await this.post("/api/workspace/current", { id }, page);
    R.equal(answer.status, 200, `POST current ${id}`);
    return answer.body;
  }

  async settle(page = this.page, timeout = 90000) {
    await page.waitForTimeout(200);
    await page.waitForFunction(() => {
      const p = window.app.tomovisPage;
      return p.ctx && p.bridge.ctx && !p.bridge.running && p.bridge.timer === null && p.ctx.session.idle() && !p.ctx.session.snapshot.pending_dialog;
    }, null, { timeout });
    await page.waitForTimeout(150);
  }

  async openTomoVis(page = this.page) {
    await page.goto(`${this.options.base}/#/tomovis`);
    await page.reload();
    await H.openTomoVis(page, this.options.base);
    await this.settle(page);
  }

  async importFile(label, file, page = this.page) {
    await H.menu(page, "File", "Import", label);
    await H.chooseFile(page, file);
    await this.settle(page);
  }

  async attributes(page = this.page) {
    return this.T(() => window.app.tomovisPage.ctx.session.snapshot.attributes, null, page);
  }

  async waitShape(shape, page = this.page, timeout = 90000) {
    await page.waitForFunction((wanted) => {
      const a = window.app.tomovisPage.ctx.session.snapshot.attributes;
      return JSON.stringify(a.data_shape) === JSON.stringify(wanted);
    }, shape, { timeout });
    await this.settle(page);
  }

  async caption(page = this.page) {
    return this.T(() => {
      const host    = document.querySelector("#tvb-caption");
      const notice  = host.querySelector(".ds-indicator__notice");
      const text    = notice.querySelector(".ds-indicator__text");
      const rect    = host.getBoundingClientRect();
      const visible = !host.hidden && getComputedStyle(host).display !== "none" && rect.height > 0;
      return {
        visible,
        rect    : [rect.left, rect.top, rect.width, rect.height],
        name    : host.querySelector(".ds-indicator__name").textContent.trim(),
        origin  : host.querySelector(".ds-indicator__origin").textContent.trim(),
        notice  : notice.hidden || !text ? "" : text.textContent.trim(),
        actions : notice.hidden ? [] : [...notice.querySelectorAll("button")].map((b) => b.textContent.trim()),
      };
    }, null, page);
  }

  async waitNotice(text, page = this.page, timeout = 30000) {
    await page.waitForFunction((t) => {
      const notice = document.querySelector("#tvb-caption .ds-indicator__notice .ds-indicator__text");
      return notice && notice.textContent.includes(t);
    }, text, { timeout });
    return this.caption(page);
  }

  async action(label, page = this.page) {
    await page.locator("#tvb-caption .ds-indicator__notice button", { hasText: label }).click();
  }

  async dialogs(page = this.page) {
    return this.T(() => window.__tvbFileDialogs, null, page);
  }

  async toast(page = this.page) {
    return this.T(() => document.getElementById("toast").textContent, null, page);
  }

  async completeTwo(first, second) {
    const box    = this.page.locator(".ds-completer").last();
    await box.waitFor({ state: "visible", timeout: 15000 });
    const inputs = box.locator("input");
    await inputs.nth(0).fill(String(first));
    await inputs.nth(1).fill(String(second));
    await box.locator("button", { hasText: /^Save$/ }).click();
  }

  async views(page = this.page) {
    return this.T(() => {
      const snapshot = window.app.tomovisPage.ctx.session.snapshot;
      const slicer   = window.app.tomovisPage.views[0];
      const out      = { nChannels: snapshot.attributes.nChannels, views: {}, arrays: {}, rgba: {} };
      const hash     = (bytes) => {
        let h = 2166136261;
        for (let i = 0; i < bytes.length; i += 1) h = Math.imul(h ^ bytes[i], 16777619) >>> 0;
        return [bytes.length, h];
      };
      for (const name of ["imv1_1", "imv1_2", "imv2_1", "imv2_2"]) {
        const view = { ...snapshot.views[name] };
        delete view.image_serial;
        delete view.apply_serial;
        out.views[name] = view;
        const item = slicer.views[name].imageItem;
        out.arrays[name] = item.image ? [item.shape, item.dtype, hash(new Uint8Array(item.image.buffer, item.image.byteOffset, item.image.byteLength))] : null;
        out.rgba[name]   = item.image ? hash(item.rgba()) : null;
      }
      return out;
    }, null, page);
  }

  fixture(name, source) {
    fs.mkdirSync(this.fixtures, { recursive: true });
    const target = path.join(this.fixtures, name);
    fs.copyFileSync(source, target);
    return target;
  }

  async manualImport() {
    await this.run.check("TV-02", "a manual hd5 import becomes the current dataset set by TomoVis and the caption names it", async () => {
      await this.use(null);
      await this.openTomoVis();
      await this.importFile("hd5", path.join(this.inputs, "fusar_two_key_elev.hd5"));
      const state = await this.current();
      const cap   = await this.caption();
      await this.shot("tv02_manual_import");
      R.equal([state.current.name, state.set_by, state.tomovis.held.id, state.tomovis.open], ["fusar_two_key_elev.hd5", "tomovis", state.current.id, false], "current, set_by, held and open");
      R.equal([cap.visible, cap.name, cap.origin, cap.notice], [true, "fusar_two_key_elev.hd5", "TomoVis import · hd5", ""], "caption");
      this.ids.fusar    = state.current.id;
      this.shapes.fusar = state.current.cube.shape;
      return `${state.current.id} ${JSON.stringify(state.current.cube.shape)}`;
    });
  }

  async layout() {
    await this.run.check("TV-01", "the TomoVis window keeps its rect with a current dataset; the caption lives in the top band only when it is 16 px or more", async () => {
      const rows = [];
      for (const [width, height, visible] of [[1100, 880, false], [1440, 900, false], [1136, 916, true], [1440, 1000, true]]) {
        await this.page.setViewportSize({ width, height });
        const measure = () => this.T(() => {
          const win  = document.querySelector("#tv-window").getBoundingClientRect();
          const host = document.querySelector("#tvb-caption");
          const cap  = host.getBoundingClientRect();
          return { win: [win.left, win.top, win.width, win.height], caption: !host.hidden && getComputedStyle(host).display !== "none" && cap.height > 0, cap: [cap.left, cap.top, cap.width, cap.height], doc: document.documentElement.scrollHeight, inner: window.innerHeight };
        });

        await this.use(null);
        await this.openTomoVis();
        const without = await measure();
        await this.use(this.ids.fusar);
        await this.openTomoVis();
        await this.waitShape(this.shapes.fusar);
        const withDataset = await measure();
        await this.shot(`tv01_${width}x${height}`);

        R.equal(withDataset.win, without.win, `${width}x${height} window rect with and without a current dataset`);
        R.equal([without.caption, withDataset.caption], [false, visible], `${width}x${height} caption visibility without and with a current dataset`);
        if (withDataset.caption) {
          const [x, y, w, h] = withDataset.cap;
          const [wx, wy, ww, wh] = withDataset.win;
          R.assert(x + w <= wx || wx + ww <= x || y + h <= wy || wy + wh <= y, `${width}x${height} caption ${JSON.stringify(withDataset.cap)} intersects the window ${JSON.stringify(withDataset.win)}`);
          R.assert(h >= 16, `${width}x${height} caption band is ${h} px`);
        }
        R.equal([without.doc, withDataset.doc], [height, height], `${width}x${height} document height`);
        rows.push(`${width}x${height} win ${withDataset.win.join(",")} caption ${withDataset.caption ? withDataset.cap.join(",") : "hidden"}`);
      }
      await this.page.setViewportSize({ width: 1440, height: 1000 });
      return rows.join("; ");
    });
  }

  async runHandOver() {
    await this.run.check("TV-03", "a TomoVic use of the test_data run opens it on #/tomovis with no file dialog", async () => {
      await this.T(async (base) => fetch(`/api/cubes?base=${encodeURIComponent(base)}`), RUN);
      await this.page.goto(`${this.options.base}/#/results`);
      const used    = await this.use(RUN);
      const dataset = used.current;
      const before  = await this.dialogs();
      await this.page.goto(`${this.options.base}/#/tomovis`);
      await this.waitShape(RUN_SHAPE);
      const a     = await this.attributes();
      const toast = await this.toast();
      const after = await this.current();
      await this.shot("tv03_run_hand_over");
      R.equal(await this.dialogs(), before, "file dialogs attached during the hand-over");
      R.equal(a.z_range, dataset.pieces.height_range.value, "z_range is the run's height range");
      R.equal([a.x_res, a.y_res], dataset.pieces.spacing.value, "x_res and y_res are the run's spacings");
      R.equal(toast, "TomoVis opened test_data, the current dataset.", "toast");
      R.equal([after.tomovis.open, after.tomovis.held.id, after.set_by], [false, dataset.id, "tomovic"], "open, held and set_by after the hand-over");
      return `z ${JSON.stringify(a.z_range)} res ${a.x_res} ${a.y_res}`;
    });
  }

  async reloadAfterTomoVis() {
    await this.run.check("TV-04", "after a TomoVis import a reload leaves the window empty and the caption opens the dataset on request", async () => {
      await this.use(null);
      await this.openTomoVis();
      await this.importFile("hd5", path.join(this.inputs, "fusar_two_key_elev.hd5"));
      await this.openTomoVis();
      const empty = await this.attributes();
      const cap   = await this.waitNotice("is not open in this window.");
      await this.shot("tv04_reload_empty");
      R.equal([empty.data_present, cap.notice, cap.actions], [false, "fusar_two_key_elev.hd5 is not open in this window.", ["Open in TomoVis"]], "empty window and caption action");
      await this.action("Open in TomoVis");
      await this.waitShape(this.shapes.fusar);
      const a     = await this.attributes();
      const state = await this.current();
      R.equal([a.z_range, state.set_by, state.tomovis.held.id], [[-10, 30], "tomovic", this.ids.fusar], "opened with the hd5 heights");
      R.equal(await this.dialogs(), 0, "no file dialog since the reload");
      return `z ${JSON.stringify(a.z_range)}`;
    });
  }

  async reloadAfterTomoVic() {
    await this.run.check("TV-05", "after a TomoVic use a reload of #/tomovis opens the current dataset by itself", async () => {
      await this.use(null);
      await this.openTomoVis();
      await this.use(this.ids.fusar);
      await this.openTomoVis();
      await this.waitShape(this.shapes.fusar);
      const a = await this.attributes();
      R.equal([a.z_range, await this.toast()], [[-10, 30], "TomoVis opened fusar_two_key_elev.hd5, the current dataset."], "z_range and toast");
      R.equal(await this.dialogs(), 0, "no file dialog since the reload");
      return `shape ${JSON.stringify(a.data_shape)}`;
    });
  }

  async addHeights() {
    await this.run.check("TV-06", "an npy import without heights offers Add height range, and TomoVis reopens with them", async () => {
      const file = this.fixture("heights.npy", path.join(this.inputs, "npy_real.npy"));
      await this.use(null);
      await this.openTomoVis();
      await this.importFile("npy", file);
      const cap = await this.waitNotice("Elevation is shown in samples.");
      R.equal([cap.notice, cap.actions], ["Elevation is shown in samples.", ["Add height range"]], "notice before");
      const id = (await this.current()).current.id;
      await this.action("Add height range");
      await this.completeTwo(0, 50);
      await this.page.waitForFunction(() => JSON.stringify(window.app.tomovisPage.ctx.session.snapshot.attributes.z_range) === "[0,50]", null, { timeout: 30000 });
      await this.settle();
      const dataset = await this.dataset(id);
      const after   = await this.caption();
      await this.shot("tv06_heights_added");
      R.equal([dataset.pieces.height_range.present, dataset.pieces.height_range.value], [true, [0, 50]], "height_range piece");
      R.equal([after.notice, after.actions], ["Distances are shown in pixels.", ["Add pixel spacing"]], "notice after");
      this.ids.heights = id;
      return `${id} z [0, 50]`;
    });
  }

  async dialogGuard() {
    await this.run.check("TV-07", "no hand-over while a TomoVis file dialog is open; cancelling it lets the hand-over run", async () => {
      await this.use(this.ids.heights);
      await this.openTomoVis();
      await this.waitShape([16, 32, 24]);
      await H.menu(this.page, "File", "Import", "hd5");
      await this.page.waitForSelector(".tv-filedialog[data-dir]", { timeout: 15000 });
      await this.use(RUN);
      await this.T(() => window.dispatchEvent(new Event("focus")));
      await this.page.waitForTimeout(1500);
      const during = await this.attributes();
      const open   = await this.T(() => Boolean(document.querySelector(".tv-filedialog")));
      R.equal([open, during.data_shape], [true, [16, 32, 24]], "dialog still open and window unchanged");
      await this.page.click(".tv-filedialog .tv-filedialog__cancel");
      await this.waitShape(RUN_SHAPE);
      R.equal(await this.toast(), "TomoVis opened test_data, the current dataset.", "toast after the cancel");
      return "held back for 1.5 s, ran after Cancel";
    });
  }

  async channels() {
    await this.run.check("TV-08", "the hand-over of a three-channel import gives the views of the manual import", async () => {
      await this.use(null);
      await this.openTomoVis();
      await this.importFile("npy", path.join(this.inputs, "npy_channels_3.npy"));
      const manual = await this.views();
      const shape  = (await this.attributes()).data_shape;
      const id     = (await this.current()).current.id;
      await this.use(id);
      await this.openTomoVis();
      await this.waitShape(shape);
      const handed = await this.views();
      await this.shot("tv08_channels_hand_over");
      R.equal([handed.nChannels, handed.views.imv1_2.level_mode], [3, "rgba"], "three channels and an RGB imv1_2");
      R.equal(handed.views, manual.views, "view snapshots");
      const shown = Object.entries(handed.views).filter(([, view]) => view.has_image).map(([name]) => name);
      R.assert(shown.length >= 2 && shown.every((name) => handed.arrays[name] !== null), `view arrays of the views with an image ${JSON.stringify(handed.arrays)}`);
      R.equal(handed.arrays, manual.arrays, "view arrays");
      R.equal(handed.rgba, manual.rgba, "rendered view pixels");
      return JSON.stringify(handed.arrays);
    });
  }

  async scriptsPage() {
    await this.run.check("TV-09", "the scripts page fills both path fields after a TomoVic use and only on request after a TomoVis import", async () => {
      const used = await this.use(RUN);
      const link = used.current.tomovis.scripts_link;
      await this.page.goto(`${this.options.base}/#/tomovis_scripts`);
      await this.page.reload();
      await this.page.waitForFunction(() => window.app.tomovisScriptsPage && window.app.tomovisScriptsPage.views.length === 2, null, { timeout: 30000 });
      await this.page.waitForFunction((l) => window.app.tomovisScriptsPage.views.every((v) => v.path.input.value === l), link, { timeout: 15000 });
      const notice = await this.T(() => document.querySelector("#tvs-dataset-bar .ds-indicator__notice").textContent.replace(/\s+/g, " ").trim());
      R.assert(notice.includes("This cube is 572 MB; both scripts read it whole and the volume script sends it to the browser."), `size warning in ${JSON.stringify(notice)}`);
      await this.page.click("#tv-script-slicer .tv-button:has-text('Load')");
      await this.page.waitForFunction(() => window.app.tomovisScriptsPage.views[0].figure.attached && window.app.tomovisScriptsPage.views[0].figure.frames > 0, null, { timeout: 120000 });
      await this.page.waitForTimeout(500);
      await this.shot("tv09_scripts_filled");
      const frames = await this.T(() => window.app.tomovisScriptsPage.views[0].figure.frames);

      await this.use(null);
      await this.openTomoVis();
      await this.importFile("hd5", path.join(this.inputs, "fusar_two_key_elev.hd5"));
      const state = await this.current();
      R.equal(state.set_by, "tomovis", "set_by after the import");
      await this.page.goto(`${this.options.base}/#/tomovis_scripts`);
      await this.page.reload();
      await this.page.waitForFunction(() => window.app.tomovisScriptsPage && window.app.tomovisScriptsPage.views.length === 2, null, { timeout: 30000 });
      await this.page.waitForSelector("#tvs-dataset-bar .ds-indicator__notice button", { timeout: 15000 });
      const empty = await this.T(() => window.app.tomovisScriptsPage.views.map((v) => v.path.input.value));
      R.equal(empty, ["", ""], "fields stay empty after a TomoVis import");
      await this.page.locator("#tvs-dataset-bar .ds-indicator__notice button", { hasText: "Use the current dataset" }).click();
      const filled = await this.T(() => window.app.tomovisScriptsPage.views.map((v) => v.path.input.value));
      R.equal(filled, [state.current.tomovis.scripts_link, state.current.tomovis.scripts_link], "fields after Use the current dataset");
      await this.page.goto(`${this.options.base}/#/results`);
      return `${link}, slicer drew ${frames} frames`;
    });
  }

  async twoPages() {
    await this.run.check("TV-10", "an import in a second page leaves the first window alone and its caption offers to follow", async () => {
      await this.use(this.ids.fusar);
      await this.openTomoVis();
      await this.waitShape(this.shapes.fusar);
      const other = await this.context.newPage();
      this.watch(other, "page B");
      await H.openTomoVis(other, this.options.base);
      await this.settle(other);
      await this.importFile("npy", path.join(this.inputs, "npy_real.npy"), other);
      const imported = (await this.current(other)).current;

      await this.page.bringToFront();
      await this.T(() => window.dispatchEvent(new Event("focus")));
      const cap = await this.waitNotice("This window shows");
      const a   = await this.attributes();
      await this.shot("tv10_other_page");
      R.equal(a.data_shape, this.shapes.fusar, "page A window unchanged");
      R.equal([cap.notice, cap.actions], [`This window shows fusar_two_key_elev.hd5. Current dataset: ${imported.name}.`, [`Open ${imported.name} here`]], "page A caption");
      await this.action(`Open ${imported.name} here`);
      await this.waitShape(imported.cube.shape);
      const held = (await this.current()).tomovis.held;
      await other.close();
      R.equal(held.id, imported.id, "page A holds the import");
      return imported.name;
    });
  }

  async brokenSource() {
    await this.run.check("TV-11", "a hand-over TomoVis cannot read shows TomoVis's Import error once and keeps the previous cube; a deleted source is never handed over", async () => {
      const file = this.fixture("gone.npy", path.join(this.inputs, "npy_real.npy"));
      await this.use(null);
      await this.openTomoVis();
      await this.importFile("npy", file);
      const gone = (await this.current()).current;
      await this.importFile("hd5", path.join(this.inputs, "fusar_two_key_elev.hd5"));

      fs.chmodSync(file, 0o000);
      await this.use(gone.id);
      await this.T(() => window.dispatchEvent(new Event("focus")));
      const box = this.page.locator(".tv-modal", { has: this.page.locator(".tv-modal__title", { hasText: "Import error" }) });
      await box.waitFor({ state: "visible", timeout: 30000 });
      await this.shot("tv11_import_error");
      const kept = await this.attributes();
      R.equal(kept.data_shape, this.shapes.fusar, "previous cube kept");
      await box.locator("button", { hasText: "OK" }).click();
      await this.page.waitForTimeout(1500);
      const again = await this.T(() => document.querySelectorAll(".tv-modal").length);
      R.equal(again, 0, "no second attempt after the box was closed");
      R.assert(!(await this.toast()).startsWith("TomoVis opened gone.npy"), "no success toast");
      const refused = await this.caption();
      R.equal([refused.notice, refused.actions], [`This window shows fusar_two_key_elev.hd5. Current dataset: gone.npy.`, ["Open gone.npy here"]], "caption after the refusal");

      fs.chmodSync(file, 0o644);
      fs.rmSync(file);
      await this.use(null);
      await this.use(gone.id);
      const dialogs = await this.dialogs();
      await this.T(() => window.dispatchEvent(new Event("focus")));
      const cap   = await this.waitNotice("gone.npy was moved or deleted");
      const state = await this.current();
      await this.page.waitForTimeout(800);
      await this.shot("tv11_deleted");
      R.equal([state.current.tomovis.ready, state.tomovis.open], [false, false], "a deleted source is not ready");
      R.equal([state.current.state, cap.notice, cap.actions], ["error", state.current.error, []], "the caption shows the dataset's error with no action");
      R.equal([(await this.attributes()).data_shape, await this.dialogs(), await this.T(() => document.querySelectorAll(".tv-modal").length)], [this.shapes.fusar, dialogs, 0], "window, dialogs and boxes unchanged");
      return cap.notice;
    });
  }

  async main() {
    fs.mkdirSync(OUT, { recursive: true });
    const opened  = await this.launch();
    this.context  = opened.context;
    this.page     = opened.page;
    this.options.base = opened.base;
    this.watch(this.page, "page A");
    await this.page.goto(`${opened.base}/#/results`);

    await this.manualImport();
    await this.layout();
    await this.runHandOver();
    await this.reloadAfterTomoVis();
    await this.reloadAfterTomoVic();
    await this.addHeights();
    await this.dialogGuard();
    await this.channels();
    await this.scriptsPage();
    await this.twoPages();
    await this.brokenSource();

    await this.use(null);
    await opened.browser.close();
    const ok = this.run.summary(this.errors);
    fs.writeFileSync(path.join(OUT, "tomovis_side.json"), JSON.stringify({ results: this.run.results, errors: this.errors }, null, 2));
    return ok;
  }
}

export { TomoVisSideChecks };

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  const ok = await new TomoVisSideChecks(H.args(process.argv, BUILDER)).main();
  process.exit(ok ? 0 : 1);
}
