import fs from "node:fs";
import path from "node:path";
import { TomoVisHarness as H, TomoVisCheckRun as R, REPO } from "../tomovis_checks/harness.mjs";

const BUILDER = "tomovic-ui";
const OUT     = path.join(REPO, "logs/bridge", BUILDER);
const SHOTS   = path.join(OUT, "shots");
const RUN     = "/home/bard/Bard/code/DLR-TomoSAR/test_data";
const EMPTY   = "No current dataset. Open a run in Cube or import a file in TomoVis.";
const STANDIN = "Top view of the tomogram (stand-in for the primary SLC)";

class TomoVicSideChecks {
  constructor(options) {
    this.options  = options;
    this.run      = new R("tomovic_side");
    this.errors   = [];
    this.expected = [];
    this.inputs   = H.fixture("inputs");
    this.fixtures = path.join(OUT, "fixtures");
    this.ids      = {};
  }

  async launch() {
    const opened = await H.launch({ port: this.options.port, gl: this.options.gl, viewport: { width: 1440, height: 1000 } });
    await opened.context.addInitScript((run) => {
      try {
        localStorage.setItem("results-sources", JSON.stringify({ datasets: run, logs: run }));
      } catch (error) {
        console.warn(`results-sources not stored: ${error.message}`);
      }
    }, RUN);
    opened.page.on("console", (message) => {
      if (message.type() !== "error") return;
      const text = message.text();
      if (this.expected.some((pattern) => pattern.test(text))) return;
      this.errors.push(`console: ${text}`);
    });
    opened.page.on("pageerror", (error) => this.errors.push(`pageerror: ${error.message}`));
    this.opened = opened;
    this.page   = opened.page;
    this.base   = opened.base;
  }

  makeFixtures() {
    fs.mkdirSync(this.fixtures, { recursive: true });
    const code = [
      "import sys, numpy as np, h5py",
      "out, source = sys.argv[1], sys.argv[2]",
      "rng = np.random.default_rng(7)",
      "cube = rng.random((6, 1000, 500), dtype=np.float32)",
      "np.save(f'{out}/globe_cube.npy', cube)",
      "np.save(f'{out}/globe_dem.npy', (500.0 + 20.0 * rng.random((1000, 500))).astype(np.float32))",
      "np.save(f'{out}/primary_wrong.npy', np.ones((10, 10), dtype=np.float32))",
      "np.save(f'{out}/primary_fortran.npy', np.asfortranarray(np.ones((1000, 500), dtype=np.float32)))",
      "with h5py.File(source, 'r') as src, h5py.File(f'{out}/fusar_two_key_elev_large.hd5', 'w') as dst:",
      "    dst.attrs.update(dict(src.attrs))",
      "    dst.create_dataset('theta', data=src['theta'][...])",
      "    data = (rng.random((24, 1500, 1000), dtype=np.float32) + 1j * rng.random((24, 1500, 1000), dtype=np.float32)).astype(np.complex64)",
      "    dset = dst.create_dataset('tomogram', data=data)",
      "    dset.attrs.update(dict(src['tomogram'].attrs))",
    ].join("\n");
    H.python(code, this.fixtures, path.join(this.inputs, "fusar_two_key_elev.hd5"));
  }

  T(fn, arg) {
    return this.page.evaluate(fn, arg);
  }

  async shot(name) {
    fs.mkdirSync(SHOTS, { recursive: true });
    await this.page.screenshot({ path: path.join(SHOTS, `${name}.png`) });
  }

  async post(url, body) {
    return this.T(async ([u, b]) => {
      const res = await fetch(u, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(b) });
      return { status: res.status, body: await res.json() };
    }, [url, body]);
  }

  async get(url) {
    return this.T(async (u) => (await fetch(u)).json(), url);
  }

  async current() {
    return this.get("/api/workspace/current");
  }

  async dataset(id) {
    return (await this.get(`/api/workspace/dataset?id=${encodeURIComponent(id)}`)).dataset;
  }

  async route(hash) {
    await this.T((h) => { window.location.hash = h; }, hash);
    await this.page.waitForTimeout(150);
  }

  async importFile(menuLabel, file) {
    await H.openTomoVis(this.page, this.base);
    await H.menu(this.page, "File", "Import", menuLabel);
    await H.chooseFile(this.page, file);
    const state = await this.current();
    R.assert(state.current && state.set_by === "tomovis", `the import did not become the current dataset: ${JSON.stringify({ set_by: state.set_by, error: state.bridge_error })}`);
    return state.current;
  }

  async waitLoaded(id, timeout = 90000) {
    await this.page.waitForFunction((i) => window.tomogramView && window.tomogramView.selectedId === i && window.tomogramView.meta && !window.tomogramView.polling, id, { timeout });
  }

  async waitCompletion(piece) {
    await this.page.waitForSelector(`#cube-complete:not([hidden]) .ds-row[data-piece="${piece}"]`, { timeout: 30000 });
  }

  async saveHeights(host, low, high) {
    const inputs = this.page.locator(`${host} .ds-row[data-piece="height_range"] input`);
    await inputs.nth(0).fill(String(low));
    await inputs.nth(1).fill(String(high));
    await this.page.click(`${host} .ds-row[data-piece="height_range"] .ds-save`);
  }

  async pickFile(file) {
    await this.page.waitForSelector(".ds-picker", { timeout: 10000 });
    await this.page.fill(".ds-picker .ds-picker__path", file);
    await this.page.click(".ds-picker .ds-picker__accept");
    await this.page.waitForSelector(".ds-picker", { state: "detached", timeout: 10000 });
  }

  async openCard() {
    await this.page.click('#cube-dataset-bar [data-details]');
    await this.page.waitForSelector(".ds-card .ds-pieces", { timeout: 10000 });
  }

  async expandStripGroup(name) {
    const dir = this.page.locator("#cube-strip .run-tree__dir", { has: this.page.locator(".run-tree__name", { hasText: new RegExp(`^${name}$`) }) });
    if (!(await dir.evaluate((el) => el.classList.contains("is-open")))) await dir.click();
  }

  async noCurrent() {
    await this.run.check("TC-01", "with no current dataset the nav pill and the Cube bar show the empty sentence", async () => {
      await this.page.goto(`${this.base}/#/home`);
      await this.post("/api/workspace/current", { id: null });
      await this.route("#/cube");
      await this.page.waitForFunction((t) => document.querySelector("#cube-dataset-bar .ds-indicator__name").textContent === t, EMPTY, { timeout: 10000 });
      const nav = await this.page.textContent("#nav-dataset .ds-indicator__name");
      R.equal(nav, EMPTY, "nav pill");
      const links = await this.page.locator("#cube-dataset-bar .ds-indicator__links").isVisible();
      R.assert(!links, "the Cube bar shows links without a current dataset");
      await this.shot("tc01_empty");
      return "nav and bar both read the empty sentence";
    });
  }

  async npyImport() {
    await this.run.check("TC-02", "an npy imported in TomoVis opens on the Cube page, asks for the height range, then loads with the stand-in map", async () => {
      const current = await this.importFile("npy", path.join(this.inputs, "npy_real.npy"));
      this.ids.npyReal = current.id;

      await this.route("#/cube");
      await this.waitCompletion("height_range");
      const title = await this.page.textContent("#cube-complete .ds-completer__title");
      R.equal(title, "The Cube page needs Height range for npy_real.npy.", "completion title");
      const group = await this.page.textContent("#cube-strip .run-tree__dir.is-current .run-tree__name");
      R.equal(group, "workspace", "strip group of the selected dataset");
      await this.expandStripGroup("workspace");
      const active = await this.page.textContent("#cube-strip .cube-run.is-active .run-name");
      R.equal(active, "npy_real.npy", "selected strip row");
      await this.shot("tc02_completion");

      const slice = this.page.waitForResponse((res) => res.url().includes("/api/cubes/slice?") && res.url().includes(encodeURIComponent(current.id)) && res.status() === 200, { timeout: 60000 });
      await this.saveHeights("#cube-complete", -20, 80);
      await this.waitLoaded(current.id);
      await slice;
      const meta = await this.T(() => ({ lo: window.tomogramView.meta.x_min, hi: window.tomogramView.meta.x_max, hidden: document.getElementById("cube-complete").hidden }));
      R.equal([meta.lo, meta.hi, meta.hidden], [-20, 80, true], "heights and completion panel after Save");
      const map = await this.page.textContent("#cube-map .cube-panel-title");
      R.equal(map, STANDIN, "map title");
      R.assert(await this.page.locator("#cube-map .ds-replace").isVisible(), "the stand-in map has no Replace button");
      await this.shot("tc02_loaded");
      return `loaded ${current.id} with heights -20..80 and the stand-in title`;
    });
  }

  async fusarImport() {
    await this.run.check("TC-03", "an hd5 with heights loads on the Cube page with no completion panel once preparation ends", async () => {
      const exact = await this.importFile("hd5", path.join(this.inputs, "fusar_two_key_elev.hd5"));
      await this.route("#/cube");
      await this.waitLoaded(exact.id);
      const small = await this.T(() => ({ lo: window.tomogramView.meta.x_min, hi: window.tomogramView.meta.x_max, hidden: document.getElementById("cube-complete").hidden }));
      R.equal([small.lo, small.hi, small.hidden], [-10, 30, true], "fusar_two_key_elev.hd5 heights and completion panel");

      const large = await this.importFile("hd5", path.join(this.fixtures, "fusar_two_key_elev_large.hd5"));
      await this.T(() => {
        window.__progressLabels = [];
        const label = document.getElementById("cube-progress-label");
        new MutationObserver(() => window.__progressLabels.push(label.textContent)).observe(label, { childList: true, characterData: true, subtree: true });
      });
      await this.route("#/cube");
      await this.waitLoaded(large.id, 120000);
      const labels = await this.T(() => window.__progressLabels);
      const prep   = labels.filter((text) => text.startsWith("Preparing fusar_two_key_elev_large.hd5 for the TomoVic tools: "));
      R.assert(prep.length > 0, `no preparation label was seen: ${JSON.stringify(labels.slice(0, 6))}`);
      const big = await this.T(() => ({ lo: window.tomogramView.meta.x_min, hi: window.tomogramView.meta.x_max, hidden: document.getElementById("cube-complete").hidden }));
      R.equal([big.lo, big.hi, big.hidden], [-10, 30, true], "large hd5 heights and completion panel");
      await this.shot("tc03_loaded");
      return `labels seen: ${[...new Set(prep)].join(" | ")}`;
    });
  }

  async channels() {
    await this.run.check("TC-04", "a 3-channel npy loads the combined channel, and Channel 2 from the card reloads the Cube page", async () => {
      const current = await this.importFile("npy", path.join(this.inputs, "npy_channels_3.npy"));
      this.ids.channels = current.id;
      await this.route("#/cube");
      await this.waitCompletion("height_range");
      await this.saveHeights("#cube-complete", 0, 40);
      await this.waitLoaded(current.id);

      const before = await this.dataset(current.id);
      R.equal(before.channel.chosen, "combined", "default channel");
      const loaded = await this.T(() => window.tomogramView.loadedRevision);
      R.equal(loaded, before.revision, "loaded revision");

      await this.openCard();
      await this.page.click('.ds-card .ds-piece[data-piece="channel"] .ds-piece__toggle');
      const options = await this.page.locator('.ds-card .ds-piece[data-piece="channel"] select option').allTextContents();
      R.equal(options, ["All channels combined (square root of the summed power)", "Channel 1", "Channel 2", "Channel 3"], "channel options");
      await this.page.selectOption('.ds-card .ds-piece[data-piece="channel"] select', { label: "Channel 2" });
      await this.page.click('.ds-card .ds-piece[data-piece="channel"] .ds-save');
      await this.page.waitForFunction((r) => window.tomogramView.loadedRevision > r && window.tomogramView.meta && !window.tomogramView.polling, before.revision, { timeout: 60000 });

      const after = await this.dataset(current.id);
      R.equal(after.channel.chosen, 1, "chosen channel");
      R.assert(after.revision > before.revision, `revision did not go up: ${before.revision} -> ${after.revision}`);
      await this.page.keyboard.press("Escape");
      await this.shot("tc04_channel2");
      return `revision ${before.revision} -> ${after.revision}, Cube reloaded at ${await this.T(() => window.tomogramView.loadedRevision)}`;
    });
  }

  async globe() {
    await this.run.check("TC-05", "a DEM and a geometry copied from test_data turn on the DEM terrain flag and the Globe", async () => {
      const current = await this.importFile("npy", path.join(this.fixtures, "globe_cube.npy"));
      this.ids.globe = current.id;
      await this.route("#/cube");
      await this.waitCompletion("height_range");
      await this.saveHeights("#cube-complete", 0, 30);
      await this.waitLoaded(current.id);

      const globe = this.page.locator('.cube-mode[data-view="globe"]');
      R.assert(await globe.evaluate((el) => !el.hidden && el.classList.contains("is-missing")), "the Globe button is not marked missing");
      R.equal(await globe.getAttribute("title"), "Needs DEM and Acquisition geometry", "Globe title");
      R.assert(await this.page.locator("#cube-dem-add").isVisible(), "Add DEM is not offered next to the DEM terrain flag");

      const loaded = await this.T(() => window.tomogramView.loadedRevision);
      await this.page.click("#cube-dem-add");
      await this.page.click('.ds-popover .ds-row[data-piece="dem"] .ds-pick');
      await this.pickFile(path.join(this.fixtures, "globe_dem.npy"));
      await this.page.waitForSelector(".ds-popover", { state: "detached", timeout: 10000 });
      await this.page.waitForFunction((r) => window.tomogramView.loadedRevision > r && !window.tomogramView.polling, loaded, { timeout: 60000 });
      R.assert(await this.page.locator("#cube-dem-wrap").isVisible(), "the DEM terrain flag is not visible after adding the DEM");
      R.equal(await globe.getAttribute("title"), "Needs Acquisition geometry", "Globe title after the DEM");

      const withDem = await this.T(() => window.tomogramView.loadedRevision);
      await globe.click();
      await this.page.waitForSelector("#cube-missing:not([hidden]) .ds-completer__title", { timeout: 10000 });
      R.equal(await this.page.textContent("#cube-missing .ds-completer__title"), "The Globe needs Acquisition geometry.", "missing panel title");
      await this.shot("tc05_globe_missing");
      await this.page.click('#cube-missing .ds-row[data-piece="geometry"] .ds-geometry');
      await this.page.waitForSelector(".ds-picker", { timeout: 10000 });
      await this.page.fill(".ds-picker .ds-picker__path", RUN);
      await this.page.press(".ds-picker .ds-picker__path", "Enter");
      await this.page.waitForSelector('.ds-picker .ds-picker__entry[data-name="meta"]', { timeout: 10000 });
      R.equal(await this.page.textContent(".ds-picker .ds-picker__accept"), "Use this folder", "folder picker button");
      await this.page.click(".ds-picker .ds-picker__accept");
      await this.page.waitForFunction((r) => window.tomogramView.loadedRevision > r && !window.tomogramView.polling, withDem, { timeout: 90000 });
      await this.page.waitForFunction(() => window.tomogramView.view === "globe" && !document.querySelector('.cube-view[data-view="globe"]').hidden, null, { timeout: 30000 });
      const ready = await this.T(() => ({ available: window.tomogramView.globe.available, missing: document.querySelector('.cube-mode[data-view="globe"]').classList.contains("is-missing") }));
      R.equal([ready.available, ready.missing], [true, false], "Globe after the geometry copy");
      await this.page.waitForFunction(() => {
        const canvas = document.querySelector('.cube-view[data-view="globe"] canvas');
        return canvas && canvas.width > 0 && canvas.getContext && canvas.clientHeight > 0;
      }, null, { timeout: 60000 });
      await this.page.waitForTimeout(2500);
      await this.shot("tc05_globe");

      await this.page.click('.cube-mode[data-view="explorer"]');
      R.assert(await this.page.locator("#cube-dem-wrap").isVisible(), "the DEM terrain flag is not visible on the Cuts view");
      const dataset = await this.dataset(current.id);
      R.equal(dataset.pieces.geometry.value.run, RUN, "geometry source");
      return `Globe opened with its WebGL canvas, DEM flag visible, geometry from ${dataset.pieces.geometry.value.run}`;
    });
  }

  async wrongFiles() {
    await this.run.check("TC-06", "a wrong-shape primary and a Fortran file each show their exact message under the row", async () => {
      this.expected.push(/status of 400/);
      const id = this.ids.globe;
      await this.page.click("#cube-map .ds-replace");
      await this.page.click('.ds-popover .ds-row[data-piece="primary"] .ds-pick');
      await this.pickFile(path.join(this.fixtures, "primary_wrong.npy"));
      const wrong = this.page.locator('.ds-popover .ds-row[data-piece="primary"] .ds-row__error[role="alert"]');
      await wrong.waitFor({ state: "visible", timeout: 10000 });
      R.equal(await wrong.textContent(), "Primary image must be azimuth x range = 1000 x 500 like the tomogram, but primary_wrong.npy has shape 10 x 10.", "wrong-shape message");
      await this.shot("tc06_wrong_shape");
      await this.page.keyboard.press("Escape");

      await this.openCard();
      await this.page.click('.ds-card .ds-piece[data-piece="primary"] .ds-piece__toggle');
      R.equal(await this.page.textContent('.ds-card .ds-piece[data-piece="primary"] .ds-piece__toggle'), "Replace with the primary SLC", "card primary action");
      await this.page.click('.ds-card .ds-piece[data-piece="primary"] .ds-pick');
      await this.pickFile(path.join(this.fixtures, "primary_fortran.npy"));
      const fortran = this.page.locator('.ds-card .ds-piece[data-piece="primary"] .ds-row__error[role="alert"]');
      await fortran.waitFor({ state: "visible", timeout: 10000 });
      R.equal(await fortran.textContent(), "primary_fortran.npy is stored in Fortran order. Save it in C order (numpy.ascontiguousarray) and pick it again.", "Fortran message");
      await this.shot("tc06_fortran");
      await this.page.keyboard.press("Escape");

      const dataset = await this.dataset(id);
      R.equal(dataset.pieces.primary.value.kind, "stand-in", "primary after the refused files");
      return "both messages shown verbatim; the stand-in stays";
    });
  }

  async extractParams() {
    await this.run.check("TC-07", "Fit with Extract Params opens the launch page with the import's base path and filter", async () => {
      const id = this.ids.globe;
      await this.page.waitForSelector("#cube-param-row:not([hidden]) #cube-param-add:not([hidden]) .ds-launch", { timeout: 10000 });
      R.equal(await this.page.textContent("#cube-param-tag"), "none yet", "parameter select");
      const button = this.page.locator("#cube-param-add .ds-launch");
      R.equal(await button.textContent(), "Fit with Extract Params", "launch label");
      R.assert(await button.isEnabled(), "the launch button is disabled although the height range is known");
      R.assert(await this.page.locator("#cube-param-add .ds-params").isVisible(), "Add a parameter run folder is missing for an import");

      await button.click();
      await this.page.waitForFunction(() => window.location.hash === "#/launch/extract_params", null, { timeout: 10000 });
      await this.page.waitForFunction(() => window.app.launchView.config && Object.keys(window.app.launchView.dirty || {}).length > 0, null, { timeout: 30000 });
      const dirty = await this.T(() => window.app.launchView.dirty);
      R.equal(dirty.dataset_base_path, path.dirname(id), "dataset_base_path");
      R.equal(dirty.dataset_filter, `['${path.basename(id)}']`, "dataset_filter");
      await this.page.waitForFunction((name) => [...document.querySelectorAll(".picker__item")].some((row) => row.querySelector(".picker__item-name").textContent === name && row.querySelector("input").checked), path.basename(id), { timeout: 15000 });
      R.equal(await this.page.locator(".ds-card").count(), 0, "dataset cards left open");
      await this.page.waitForTimeout(400);
      await this.shot("tc07_launch");
      return `dataset_base_path ${dirty.dataset_base_path}, dataset_filter ${dirty.dataset_filter} ticked in the picker`;
    });
  }

  async slices() {
    await this.run.check("TC-08", "the Slices page ticks the current dataset on enter and offers Complete on an incomplete one", async () => {
      const incomplete = await this.importFile("hd5", path.join(this.inputs, "fusar_no_attrs.hd5"));
      const used = await this.post("/api/workspace/current", { id: this.ids.globe });
      R.equal(used.status, 200, "POST current");

      await this.route("#/slices");
      await this.page.waitForFunction((i) => window.app.sliceCollectorView.selected.includes(i), this.ids.globe, { timeout: 20000 });
      await this.page.waitForSelector(`#sc-strip .cube-run.is-active[title="${this.ids.globe}"]`, { timeout: 10000 });
      const row = this.page.locator(`#sc-strip .cube-run[title="${incomplete.id}"]`);
      R.equal(await row.locator(".ds-strip-complete").textContent(), "Complete", "incomplete row button");
      R.assert(await this.page.locator(`#sc-strip .cube-run[title="${this.ids.globe}"] .ds-strip-complete`).count() === 0, "a complete dataset offers Complete");
      await this.shot("tc08_slices");

      await row.click();
      await this.page.waitForSelector(".ds-popover .ds-completer__title", { timeout: 10000 });
      R.equal(await this.page.textContent(".ds-popover .ds-completer__title"), "The Slices page needs Height range for fusar_no_attrs.hd5.", "Slices completer title");
      const ticked = await this.T((i) => window.app.sliceCollectorView.selected.includes(i), incomplete.id);
      R.assert(!ticked, "picking an incomplete row ticked it");
      await this.saveHeights(".ds-popover", 0, 12);
      await this.page.waitForFunction((i) => window.app.sliceCollectorView.selected.includes(i), incomplete.id, { timeout: 20000 });
      await this.shot("tc08_completed");
      return "current ticked, incomplete row completed then ticked";
    });
  }

  async run9() {
    await this.run.check("TC-09", "test_data picked in the Cube strip loads as before, with Pauli offered through Run Extract Polarimetry", async () => {
      await this.route("#/cube");
      await this.waitLoaded(this.ids.globe, 120000);
      await this.expandStripGroup("runs");
      await this.page.click(`#cube-strip .cube-run[title="${RUN}"]`);
      await this.waitLoaded(RUN, 120000);
      await this.page.waitForFunction((r) => window.datasetBridge.state && window.datasetBridge.state.current && window.datasetBridge.state.current.id === r, RUN, { timeout: 10000 });

      const views = await this.T(() => Object.fromEntries([...document.querySelectorAll(".cube-mode[data-view]")].map((btn) => [btn.dataset.view, { shown: !btn.hidden, missing: btn.classList.contains("is-missing") }])));
      for (const view of ["explorer", "elevation", "azimuth", "range", "transect", "cloud", "volume", "globe", "passes", "figures"]) {
        R.equal(views[view], { shown: true, missing: false }, `${view} button`);
      }
      R.equal(views.pauli, { shown: true, missing: true }, "pauli button");
      R.assert(await this.T(() => document.getElementById("cube-complete").hidden), "the completion panel shows for a complete run");
      R.equal(await this.page.textContent("#cube-map .cube-panel-title"), "Primary SLC amplitude", "map title of a run");
      R.assert(!(await this.page.locator("#cube-dem-add").isVisible()), "Add DEM shows for a run");

      await this.page.click('.cube-mode[data-view="pauli"]');
      await this.page.waitForSelector("#cube-missing:not([hidden]) .ds-launch", { timeout: 10000 });
      R.equal(await this.page.textContent("#cube-missing .ds-launch"), "Run Extract Polarimetry", "Pauli launch button");
      R.equal(await this.page.textContent("#cube-missing .ds-completer__head"), "test_data is a TomoVic run. The bridge never writes into run folders.", "run header");
      R.assert(await this.page.locator("#cube-missing .ds-launch").isEnabled(), "Run Extract Polarimetry is disabled");
      await this.shot("tc09_pauli_missing");
      await this.page.click('.cube-mode[data-view="explorer"]');
      R.assert(await this.T(() => document.getElementById("cube-missing").hidden && !document.querySelector('.cube-view[data-view="explorer"]').hidden), "Cuts did not come back");
      return "every view of test_data is offered; Pauli opens Run Extract Polarimetry";
    });
  }

  async openInTomoVis() {
    await this.run.check("TC-10", "Open in TomoVis from the Cube bar opens test_data in TomoVis without a file dialog", async () => {
      await this.T(() => {
        window.__tvFileDialogs = 0;
        new MutationObserver((records) => {
          for (const record of records) {
            for (const node of record.addedNodes) {
              if (node.nodeType === 1 && (node.matches(".tv-filedialog") || node.querySelector(".tv-filedialog"))) window.__tvFileDialogs += 1;
            }
          }
        }).observe(document.body, { childList: true, subtree: true });
      });
      await this.page.click('#cube-dataset-bar [data-open="tomovis"]');
      await this.page.waitForFunction(() => window.location.hash === "#/tomovis", null, { timeout: 10000 });
      await this.page.waitForFunction(() => {
        const ctx = window.app.tomovisPage.ctx;
        return ctx && ctx.session.snapshot && JSON.stringify(ctx.session.snapshot.attributes.data_shape) === "[150,1000,500]";
      }, null, { timeout: 120000 });
      await H.waitIdle(this.page);
      const snap = await H.snapshot(this.page);
      const run  = await this.dataset(RUN);
      R.equal(snap.attributes.z_range, [-20, 80], "z_range");
      R.equal([snap.attributes.x_res, snap.attributes.y_res].map((v) => Number(v.toFixed(6))), run.pieces.spacing.value.map((v) => Number(v.toFixed(6))), "spacings");
      R.equal(await this.T(() => window.__tvFileDialogs), 0, "file dialogs attached");
      await this.shot("tc10_tomovis");
      return `data_shape ${JSON.stringify(snap.attributes.data_shape)}, z_range ${JSON.stringify(snap.attributes.z_range)}`;
    });
  }

  async reload() {
    await this.run.check("TC-11", "reloading #/cube loads the same current dataset", async () => {
      await this.route("#/cube");
      const state = await this.current();
      await this.page.reload();
      await this.waitLoaded(state.current.id, 120000);
      R.equal(await this.T(() => window.tomogramView.selectedId), state.current.id, "selected after reload");
      await this.shot("tc11_reload");
      return `reloaded onto ${state.current.name}`;
    });
  }

  async main() {
    fs.mkdirSync(OUT, { recursive: true });
    this.makeFixtures();
    await this.launch();

    const only = this.options.only;
    const steps = [
      ["TC-01", () => this.noCurrent()],
      ["TC-02", () => this.npyImport()],
      ["TC-03", () => this.fusarImport()],
      ["TC-04", () => this.channels()],
      ["TC-05", () => this.globe()],
      ["TC-06", () => this.wrongFiles()],
      ["TC-07", () => this.extractParams()],
      ["TC-08", () => this.slices()],
      ["TC-09", () => this.run9()],
      ["TC-10", () => this.openInTomoVis()],
      ["TC-11", () => this.reload()],
    ];
    for (const [id, step] of steps) {
      if (!only.length || only.includes(id)) await step();
    }

    await this.post("/api/workspace/current", { id: null });
    await this.opened.browser.close();
    const ok = this.run.summary(this.errors);
    fs.writeFileSync(path.join(OUT, "tomovic_side.json"), JSON.stringify({ results: this.run.results, errors: this.errors }, null, 2));
    process.exit(ok ? 0 : 1);
  }
}

const options = H.args(process.argv, "tomovic_side");
await new TomoVicSideChecks(options).main();
