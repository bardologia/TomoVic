import fs from "node:fs";
import path from "node:path";
import { createRequire } from "node:module";
import { execFileSync } from "node:child_process";
import { fileURLToPath } from "node:url";

const require = createRequire(import.meta.url);
const { chromium } = require("playwright-core");
const { ChromiumResolver } = require("../chromium.js");

const HERE     = path.dirname(fileURLToPath(import.meta.url));
const REPO     = path.resolve(HERE, "../../../..");
const FIXTURES = path.join(REPO, "tests/webui/fixtures/tomovis");
const SHOTS    = path.join(REPO, "logs/tomovis_port");
const PYTHON   = process.env.TOMOVIC_PYTHON || path.join(process.env.HOME, "miniconda3/envs/Dune/bin/python");
const ORIGINAL = process.env.TOMOVIS_ORIGINAL_SHOTS || "";

class TomoVisHarness {
  static GL_ARGS = {
    angle       : ["--use-gl=angle", "--use-angle=gl", "--ignore-gpu-blocklist"],
    swiftshader : ["--use-gl=angle", "--use-angle=swiftshader", "--ignore-gpu-blocklist", "--enable-unsafe-swiftshader"],
  };

  static base  = "http://127.0.0.1:8802";
  static agent = "shell";

  static args(argv, agent = TomoVisHarness.agent) {
    const out = { port: 8802, gl: "angle", agent, only: [] };
    for (let i = 2; i < argv.length; i += 1) {
      if (argv[i] === "--port") out.port = Number(argv[++i]);
      else if (argv[i] === "--gl") out.gl = argv[++i];
      else if (argv[i] === "--agent") out.agent = argv[++i];
      else if (argv[i] === "--only") out.only.push(argv[++i]);
    }
    TomoVisHarness.agent = out.agent;
    return out;
  }

  static async launch({ port, gl = "angle", viewport = { width: 1440, height: 1000 }, webgl = true }) {
    TomoVisHarness.base = `http://127.0.0.1:${port}`;
    const browser = await chromium.launch({ executablePath: new ChromiumResolver().resolve(), args: TomoVisHarness.GL_ARGS[gl], headless: true });
    const context = await browser.newContext({ viewport, deviceScaleFactor: 1 });
    if (!webgl) {
      await context.addInitScript(() => {
        const original = HTMLCanvasElement.prototype.getContext;
        HTMLCanvasElement.prototype.getContext = function (kind, options) {
          if (kind === "webgl2") return null;
          return original.call(this, kind, options);
        };
      });
    }
    const page   = await context.newPage();
    const errors = [];
    page.on("console", (message) => {
      if (message.type() === "error") errors.push(`console: ${message.text()}`);
    });
    page.on("pageerror", (error) => errors.push(`pageerror: ${error.message}`));
    return { browser, context, page, errors, base: `http://127.0.0.1:${port}` };
  }

  static async openTomoVis(page, base = TomoVisHarness.base) {
    await page.goto(`${base}/#/tomovis`);
    await page.waitForFunction(() => window.app && window.app.tomovisPage && window.app.tomovisPage.ctx && window.app.tomovisPage.ctx.session.snapshot && window.app.tomovisPage.views.length > 0, null, { timeout: 30000 });
    await TomoVisHarness.waitIdle(page);
  }

  static async menu(page, ...labels) {
    const [top, ...rest] = labels;
    await page.click(`.tv-menubar__item[data-menu="${top.toLowerCase()}"]`);
    for (const label of rest) {
      const item = page.locator(".tv-menu").last().locator(".tv-menu__item", { has: page.locator(".tv-menu__text", { hasText: new RegExp(`^${label.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}$`) }) });
      await item.hover();
      await item.click();
    }
  }

  static async chooseFile(page, absolutePath) {
    await page.waitForSelector(".tv-filedialog[data-dir]", { timeout: 15000 });
    await page.fill(".tv-filedialog .tv-filedialog__name", absolutePath);
    await page.click(".tv-filedialog .tv-filedialog__accept");
    await page.waitForSelector(".tv-filedialog", { state: "detached", timeout: 15000 });
    await TomoVisHarness.waitIdle(page);
  }

  static async waitIdle(page, timeout = 60000) {
    await page.waitForFunction(() => {
      const ctx = window.app.tomovisPage.ctx || (window.app.tomovisScriptsPage && window.app.tomovisScriptsPage.ctx);
      return ctx && ctx.session.idle();
    }, null, { timeout });
    await page.waitForTimeout(60);
  }

  static async snapshot(page) {
    return page.evaluate(() => window.app.tomovisPage.ctx.session.snapshot);
  }

  static python(code, ...args) {
    return execFileSync(PYTHON, ["-c", code, ...args], { encoding: "utf-8", maxBuffer: 256 * 1024 * 1024 });
  }

  static golden(scenario) {
    const code = "import gzip, json, sys; print(gzip.open(sys.argv[1]).read().decode())";
    return JSON.parse(TomoVisHarness.python(code, path.join(FIXTURES, "goldens", `${scenario}.json.gz`)));
  }

  static goldenArray(scenario, key) {
    const code = "import json, sys, numpy as np; a = np.load(sys.argv[1])[sys.argv[2]]; print(json.dumps({'shape': list(a.shape), 'dtype': str(a.dtype), 'data': a.ravel().tolist()}))";
    return JSON.parse(TomoVisHarness.python(code, path.join(FIXTURES, "goldens", `${scenario}.npz`), key));
  }

  static fixture(relativePath) {
    return path.join(FIXTURES, relativePath);
  }

  static shotDir(agent) {
    const dir = path.join(SHOTS, agent);
    fs.mkdirSync(dir, { recursive: true });
    return dir;
  }

  static async shot(page, name, agent = TomoVisHarness.agent, options = {}) {
    const file = path.join(TomoVisHarness.shotDir(agent), `${name}.png`);
    if (options.element) await page.locator(options.element).screenshot({ path: file });
    else await page.screenshot({ path: file, fullPage: Boolean(options.fullPage) });
    return file;
  }

  static compareShot(name, originalShot, agent = TomoVisHarness.agent) {
    if (!path.isAbsolute(originalShot) && !ORIGINAL) throw new Error("compareShot needs an absolute original shot path or TOMOVIS_ORIGINAL_SHOTS");
    const ours   = path.join(TomoVisHarness.shotDir(agent), `${name}.png`);
    const theirs = path.isAbsolute(originalShot) ? originalShot : path.join(ORIGINAL, originalShot);
    const out  = path.join(TomoVisHarness.shotDir(agent), `${name}__vs__${path.basename(theirs, ".png")}.png`);
    const code = [
      "import sys",
      "from PIL import Image, ImageDraw",
      "a, b = Image.open(sys.argv[1]).convert('RGB'), Image.open(sys.argv[2]).convert('RGB')",
      "h = max(a.height, b.height) + 24",
      "canvas = Image.new('RGB', (a.width + b.width + 16, h), (32, 32, 32))",
      "canvas.paste(a, (0, 24)); canvas.paste(b, (a.width + 16, 24))",
      "draw = ImageDraw.Draw(canvas); draw.text((6, 6), 'TomoVic port', fill=(230, 230, 230)); draw.text((a.width + 22, 6), 'original TomoVis', fill=(230, 230, 230))",
      "canvas.save(sys.argv[3])",
    ].join("\n");
    TomoVisHarness.python(code, ours, theirs, out);
    return out;
  }
}

class TomoVisCheckRun {
  constructor(name) {
    this.name    = name;
    this.results = [];
  }

  async check(id, title, fn) {
    const started = Date.now();
    try {
      const detail = await fn();
      this.results.push({ id, title, ok: true, detail: detail || "", ms: Date.now() - started });
      console.log(`PASS ${id} ${title}${detail ? ` -- ${detail}` : ""}`);
    } catch (error) {
      this.results.push({ id, title, ok: false, detail: error.stack || String(error), ms: Date.now() - started });
      console.log(`FAIL ${id} ${title}\n${error.stack || error}`);
    }
  }

  static assert(condition, message) {
    if (!condition) throw new Error(message);
  }

  static equal(actual, expected, message) {
    const a = JSON.stringify(actual);
    const e = JSON.stringify(expected);
    if (a !== e) throw new Error(`${message}: got ${a}, expected ${e}`);
  }

  summary(errors) {
    const failed = this.results.filter((r) => !r.ok);
    console.log(`\n${this.name}: ${this.results.length - failed.length} passed, ${failed.length} failed, ${errors.length} browser console errors`);
    for (const error of errors) console.log(`  ${error}`);
    return failed.length === 0 && errors.length === 0;
  }
}

export { TomoVisHarness, TomoVisCheckRun, FIXTURES, SHOTS, REPO };
export const launch       = TomoVisHarness.launch;
export const openTomoVis  = TomoVisHarness.openTomoVis;
export const menu         = TomoVisHarness.menu;
export const chooseFile   = TomoVisHarness.chooseFile;
export const waitIdle     = TomoVisHarness.waitIdle;
export const snapshot     = TomoVisHarness.snapshot;
export const golden       = TomoVisHarness.golden;
export const goldenArray  = TomoVisHarness.goldenArray;
export const fixture      = TomoVisHarness.fixture;
export const shot         = TomoVisHarness.shot;
export const compareShot  = TomoVisHarness.compareShot;
