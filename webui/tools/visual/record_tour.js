"use strict";
const fs   = require("fs");
const path = require("path");
const { execFileSync } = require("child_process");
const { ChromiumResolver } = require("./chromium");

class Track {

  constructor(keys) {
    this.keys = keys;
  }

  static smooth(u) {
    return u * u * (3 - 2 * u);
  }

  at(t) {
    const keys = this.keys;
    if (t <= keys[0][0]) return keys[0][1];
    for (let i = 1; i < keys.length; i++) {
      const [t0, a] = keys[i - 1];
      const [t1, b] = keys[i];
      if (t <= t1) return Track.mix(a, b, Track.smooth((t - t0) / (t1 - t0)));
    }
    return keys[keys.length - 1][1];
  }

  static mix(a, b, u) {
    if (typeof a === "number") return a + (b - a) * u;
    const out = {};
    for (const key of Object.keys(a)) out[key] = a[key] + (b[key] - a[key]) * u;
    return out;
  }
}

class FrameClock {

  constructor(client, fps) {
    this.client   = client;
    this.interval = 1000 / fps;
    this.ticks    = FrameClock.uptimeMs() + 5000;
  }

  static uptimeMs() {
    try {
      return Math.round(parseFloat(fs.readFileSync("/proc/uptime", "utf8").split(" ")[0]) * 1000);
    } catch (e) {
      return Date.now();
    }
  }

  async freeze() {
    await this.client.send("Emulation.setVirtualTimePolicy", { policy: "pause" });
  }

  async advance(budget) {
    const expired = new Promise((resolve) => this.client.once("Emulation.virtualTimeBudgetExpired", resolve));
    await this.client.send("Emulation.setVirtualTimePolicy", { policy: "advance", budget: budget || this.interval });
    await expired;
  }

  async frame(screenshot) {
    this.ticks += this.interval;
    const result = await this.client.send("HeadlessExperimental.beginFrame", { frameTimeTicks: this.ticks, interval: this.interval, noDisplayUpdates: false, screenshot });
    return result.screenshotData || null;
  }
}

class Camera {

  constructor(client, viewport, scale) {
    this.client   = client;
    this.viewport = viewport;
    this.scale    = scale;
    this.last     = "";
  }

  static still(x, y) {
    return { x, y, z: 1 };
  }

  async set(view, baseY) {
    const z = Math.max(1, view.z);
    const w = this.viewport.width / z;
    const h = this.viewport.height / z;
    const x = Math.min(Math.max(view.x * (1 - 1 / z), 0), this.viewport.width - w);
    const y = Math.min(Math.max(view.y * (1 - 1 / z), 0), this.viewport.height - h) + (baseY || 0);
    const key = `${x.toFixed(3)},${y.toFixed(3)},${z.toFixed(4)}`;
    if (key === this.last) return;
    this.last = key;
    await this.client.send("Emulation.setDeviceMetricsOverride", { width: this.viewport.width, height: this.viewport.height, deviceScaleFactor: 0, mobile: false, viewport: { x: x * this.scale, y: y * this.scale, width: w, height: h, scale: z } });
  }
}

class VideoEncoder {

  constructor(ffmpeg, framesDir, fps) {
    this.ffmpeg    = ffmpeg;
    this.framesDir = framesDir;
    this.fps       = fps;
  }

  encode(target, size, totalFrames, crf, preset) {
    const total   = totalFrames / this.fps;
    const fadeOut = Math.max(0, total - 0.7).toFixed(2);
    const filters = [
      `scale=${size.width}:${size.height}:flags=lanczos:in_range=pc:out_range=tv`,
      "fade=t=in:st=0:d=0.5",
      `fade=t=out:st=${fadeOut}:d=0.7`,
      "format=yuv420p",
    ];
    const args = ["-hide_banner", "-loglevel", "error", "-y", "-framerate", String(this.fps), "-i", path.join(this.framesDir, "f_%06d.jpg"), "-vf", filters.join(","), "-r", String(this.fps), "-c:v", "libx264", "-preset", preset, "-crf", String(crf), "-profile:v", "high", "-level", "5.1", "-color_range", "tv", "-movflags", "+faststart", target];
    execFileSync(this.ffmpeg, args, { stdio: "inherit" });
    return target;
  }
}

class TourRecorder {

  SCENES = ["cube", "sweep", "transect", "slices", "globe"];

  constructor(argv) {
    this.port       = 8765;
    this.outDir     = "/tmp/tomovic-tour";
    this.name       = "tour";
    this.viewport   = { width: 1440, height: 810 };
    this.render     = { width: 4096, height: 2304 };
    this.size       = { width: 3840, height: 2160 };
    this.fps        = 30;
    this.crf        = 15;
    this.preset     = "medium";
    this.quality    = 95;
    this.push       = 0.06;
    this.speed      = 1.0;
    this.ffmpeg     = "";
    this.gl         = "gl";
    this.repo       = path.resolve(__dirname, "..", "..", "..");
    this.runs       = fs.existsSync(path.join(this.repo, "test_data")) ? fs.realpathSync(path.join(this.repo, "test_data")) : "";
    this.run        = "";
    this.move       = "spiral";
    this.moveSecs   = 14;
    this.keepFrames = false;
    this.verbose    = false;
    this.scenes     = [];
    this.frameIndex = 0;
    this.parse(argv);
    if (!this.scenes.length) this.scenes = this.SCENES;
    if (!this.ffmpeg) throw new Error("--ffmpeg <path to an ffmpeg with libx264> is required");

    const sx = this.render.width / this.viewport.width;
    const sy = this.render.height / this.viewport.height;
    if (Math.abs(sx - sy) > 1e-6) throw new Error(`--render must have the aspect of --viewport (${this.viewport.width}x${this.viewport.height})`);
    this.scale = sx;
  }

  parse(argv) {
    for (let i = 0; i < argv.length; i++) {
      const a = argv[i];
      if      (a === "--port")        this.port       = Number(argv[++i]);
      else if (a === "--out")         this.outDir     = path.resolve(argv[++i]);
      else if (a === "--name")        this.name       = argv[++i];
      else if (a === "--ffmpeg")      this.ffmpeg     = argv[++i];
      else if (a === "--viewport")    this.viewport   = this.parseSize(argv[++i]);
      else if (a === "--render")      this.render     = this.parseSize(argv[++i]);
      else if (a === "--size")        this.size       = this.parseSize(argv[++i]);
      else if (a === "--fps")         this.fps        = Number(argv[++i]);
      else if (a === "--crf")         this.crf        = Number(argv[++i]);
      else if (a === "--preset")      this.preset     = argv[++i];
      else if (a === "--quality")     this.quality    = Number(argv[++i]);
      else if (a === "--push")        this.push       = Number(argv[++i]);
      else if (a === "--speed")       this.speed      = Number(argv[++i]);
      else if (a === "--gl")          this.gl         = argv[++i];
      else if (a === "--runs")        this.runs       = path.resolve(argv[++i]);
      else if (a === "--run")         this.run        = argv[++i];
      else if (a === "--move")        this.move       = argv[++i];
      else if (a === "--move-secs")   this.moveSecs   = Number(argv[++i]);
      else if (a === "--keep-frames") this.keepFrames = true;
      else if (a === "--verbose")     this.verbose    = true;
      else if (a.startsWith("--")) throw new Error("unknown flag: " + a);
      else this.scenes.push(a);
    }
    for (const scene of this.scenes) {
      if (!this.SCENES.includes(scene)) throw new Error("unknown scene: " + scene + " (choose from " + this.SCENES.join(", ") + ")");
    }
  }

  parseSize(text) {
    const match = /^(\d+)x(\d+)$/.exec(text || "");
    if (!match) throw new Error("sizes are WIDTHxHEIGHT, got " + text);
    return { width: Number(match[1]), height: Number(match[2]) };
  }

  log(text) {
    if (this.verbose) console.error("  " + text);
  }

  pt(x, y) {
    return { x, y };
  }

  async route(route) {
    await this.page.evaluate((r) => { window.location.hash = "#/" + r; }, route);
    await this.until(`!!document.querySelector('.page[data-page="${route.split("/")[0]}"].is-active')`, 5);
  }

  async until(expression, seconds) {
    const budget = Math.round(seconds * this.fps);
    for (let i = 0; i < budget; i++) {
      if (this.frozen) await this.clock.advance();
      await this.clock.frame();
      if (await this.page.evaluate(expression)) {
        this.log(`${expression.slice(0, 60)} after ${i} frames`);
        return true;
      }
    }
    console.error(`  ${expression} did not become true within ${seconds} s`);
    return false;
  }

  async hold(label, predicate, seconds) {
    const started = Date.now();
    while (Date.now() - started < seconds * 1000) {
      if (await predicate()) {
        this.log(`${label} after ${((Date.now() - started) / 1000).toFixed(0)} s`);
        return true;
      }
      await this.clock.advance(1000);
      await this.clock.frame();
      await new Promise((resolve) => setTimeout(resolve, 1000));
    }
    console.error(`  ${label}: gave up after ${seconds} s`);
    return false;
  }

  async click(selector) {
    return this.page.evaluate((sel) => { const el = document.querySelector(sel); if (el) el.click(); return !!el; }, selector);
  }

  async clickRun(root) {
    return this.page.evaluate(([r, name]) => {
      const rows = [...document.querySelectorAll(`${r} .cube-run`)];
      const row  = (name ? rows.find((el) => el.textContent.includes(name)) : null) || rows[0];
      if (!row) return null;
      const r0 = row.getBoundingClientRect();
      return { x: r0.left + r0.width / 2, y: r0.top + r0.height / 2, name: row.textContent.trim().slice(0, 40) };
    }, [root, this.run]);
  }

  async topOf(selector, margin) {
    return this.page.evaluate(([sel, m]) => { const el = document.querySelector(sel); return el ? Math.max(0, Math.round(el.getBoundingClientRect().top + window.scrollY - m)) : 0; }, [selector, margin]);
  }

  async rectOf(selector) {
    return this.page.evaluate((sel) => { const el = document.querySelector(sel); if (!el) return null; const r = el.getBoundingClientRect(); return { left: r.left, top: r.top + window.scrollY, width: r.width, height: r.height }; }, selector);
  }

  centerAt(rect, scrollAt, fx, fy) {
    return this.pt(rect.left + rect.width * fx, rect.top + rect.height * fy - scrollAt);
  }

  pointTo(p) {
    return this.client.send("Input.dispatchMouseEvent", { type: "mouseMoved", x: Math.round(p.x), y: Math.round(p.y) });
  }

  press(p) {
    const at = { x: Math.round(p.x), y: Math.round(p.y), button: "left", clickCount: 1 };
    return Promise.all([
      this.client.send("Input.dispatchMouseEvent", { type: "mousePressed", ...at }),
      this.client.send("Input.dispatchMouseEvent", { type: "mouseReleased", ...at }),
    ]);
  }

  pushOn(center, from, to, end, push) {
    const amount = 1 + (push || this.push);
    return new Track([[0, { ...center, z: 1 }], [from, { ...center, z: 1 }], [to, { ...center, z: amount }], [end, { ...center, z: amount }]]);
  }

  async shoot(seconds, tracks, offset, perFrame) {
    const frames = Math.round((seconds * this.fps) / this.speed);
    const clicks = [...(tracks.clicks || [])];
    let scrollY  = tracks.scroll ? 0 : await this.page.evaluate(() => window.scrollY);
    for (let i = 0; i < frames; i++) {
      const t = (offset || 0) + (i / this.fps) * this.speed;
      if (tracks.scroll) {
        scrollY = Math.round(tracks.scroll.at(t));
        await this.page.evaluate((y) => window.scrollTo({ top: y, behavior: "instant" }), scrollY);
      }
      if (perFrame) await perFrame(t);
      if (tracks.cam) await this.camera.set(tracks.cam.at(t), tracks.baseY === undefined ? scrollY : tracks.baseY);
      const pointer = tracks.mouse ? tracks.mouse.at(t) : null;
      const pending = [];
      if (pointer) pending.push(this.pointTo(pointer));
      if (pointer && clicks.length && t >= clicks[0]) {
        clicks.shift();
        pending.push(this.press(pointer));
      }
      await this.clock.advance();
      const data = await this.clock.frame({ format: "jpeg", quality: this.quality });
      await Promise.all(pending);
      if (!data) throw new Error("a frame came back without a screenshot");
      fs.writeFileSync(path.join(this.framesDir, `f_${String(this.frameIndex).padStart(6, "0")}.jpg`), Buffer.from(data, "base64"));
      this.frameIndex += 1;
    }
  }

  async openCube() {
    await this.route("cube");
    await this.until("!!document.querySelector('#cube-strip .cube-run')", 15);
    const row = await this.clickRun("#cube-strip");
    if (!row) throw new Error("the cube page lists no runs; pass --runs <directory>");
    this.log(`opening run ${row.name}`);
    const mouse = new Track([[0, this.pt(1200, 700)], [1.2, this.pt(row.x, row.y)], [1.6, this.pt(row.x + 2, row.y)]]);
    await this.shoot(1.6, { mouse, clicks: [1.3] });
    await this.until("document.getElementById('cube-progress').hidden && document.getElementById('cube-topdown').naturalWidth > 0", 60);
    await this.until("true", 0.3);
  }

  async sceneCube() {
    await this.openCube();
    const strip  = await this.rectOf("#cube-topdown");
    const mapTop = await this.topOf("#cube-map", 30);
    const at     = (fx, fy) => this.centerAt(strip, mapTop, fx, fy);
    const hover  = new Track([[0, this.pt(1300, 780)], [1.5, at(0.14, 0.55)], [3.2, at(0.36, 0.40)], [4.9, at(0.60, 0.62)], [6.4, at(0.78, 0.46)], [6.8, at(0.79, 0.47)]]);
    const settle = new Track([[0, 0], [0.2, 0], [1.2, mapTop], [6.8, mapTop]]);
    await this.shoot(6.8, { scroll: settle, mouse: hover, clicks: [6.6], cam: new Track([[0, Camera.still(720, 500)]]) }, 0);

    const cuts    = (await this.rectOf("#cube-slices")) || { left: 0, top: mapTop + 500, width: 1440, height: 400 };
    const cutsTop = Math.max(mapTop, Math.round(cuts.top - 70));
    const focus   = this.centerAt(cuts, cutsTop, 0.5, Math.min(0.5, 360 / Math.max(cuts.height, 1)));
    const scroll  = new Track([[6.8, mapTop], [7.2, mapTop], [8.6, cutsTop], [10.0, cutsTop]]);
    const parked  = hover.at(6.8);
    const mouse   = new Track([[6.8, parked], [7.2, parked], [8.2, this.pt(1424, 300)], [10.0, this.pt(1424, 420)]]);
    const cam     = this.pushOn(focus, 8.6, 10.0, 10.0, 0.04);
    await this.shoot(3.2, { scroll, mouse, cam }, 6.8);
  }

  async sceneSweep() {
    await this.click('button.cube-mode[data-view="azimuth"]');
    await this.until("!!document.querySelector('#cube-azimuth-grid canvas')", 15);
    await this.page.evaluate(() => { const s = document.getElementById("cube-azimuth-speed"); s.value = "2"; s.dispatchEvent(new Event("change", { bubbles: true })); });
    await this.until("true", 0.2);
    const gridTop = await this.topOf("#cube-azimuth-grid", 150);
    const grid    = await this.rectOf("#cube-azimuth-grid");
    const panel   = this.centerAt(grid, gridTop, 0.5, 0.45);
    await this.click("#cube-azimuth-play");
    const scroll = new Track([[0, gridTop]]);
    const cam    = this.pushOn(panel, 1.5, 7.0, 7.0);
    const mouse  = new Track([[0, this.pt(1320, 720)], [3.0, this.pt(1300, 560)], [7.0, this.pt(1340, 480)]]);
    await this.shoot(7.0, { scroll, cam, mouse });
    await this.click("#cube-azimuth-play");
  }

  async sceneTransect() {
    await this.click('button.cube-mode[data-view="transect"]');
    await this.until("document.getElementById('cube-transect-map').naturalWidth > 0", 15);
    const map    = await this.rectOf("#cube-transect-map");
    const mapTop = Math.round(map.top - 110);
    const at     = (fx, fy) => this.centerAt(map, mapTop, fx, fy);
    const fmax   = Math.min(0.9, (this.viewport.height - 170) / map.height);
    const p1 = at(0.22, fmax * 0.15), p2 = at(0.66, fmax * 0.55), p3 = at(0.38, fmax * 0.92);
    const scroll = new Track([[0, mapTop]]);
    const mouse  = new Track([[0, this.pt(900, 520)], [1.0, p1], [1.3, p1], [2.6, p2], [2.9, p2], [4.2, p3], [4.5, p3], [7.0, this.pt(p3.x + 60, p3.y + 20)]]);
    await this.shoot(3.2, { scroll, mouse, clicks: [1.15, 2.75], cam: new Track([[0, Camera.still(720, 400)]]) }, 0);

    const grid  = (await this.rectOf("#cube-transect-grid")) || { left: 720, top: mapTop + 300, width: 700, height: 300 };
    const focus = this.centerAt(grid, mapTop, 0.5, Math.min(0.5, 400 / Math.max(grid.height, 1)));
    const cam   = this.pushOn(focus, 3.2, 7.0, 7.0);
    await this.shoot(3.8, { scroll, mouse, cam, clicks: [4.35] }, 3.2);
  }

  async sceneSlices() {
    await this.route("slices");
    await this.until("!!document.querySelector('#sc-strip .cube-run')", 15);
    await this.page.evaluate((name) => { const rows = [...document.querySelectorAll("#sc-strip .cube-run")]; const row = (name ? rows.find((el) => el.textContent.includes(name)) : null) || rows[0]; if (row && !row.classList.contains("is-active")) row.click(); }, this.run);
    await this.until("document.getElementById('sc-map-img').naturalWidth > 0", 20);
    await this.page.evaluate(() => { const btn = [...document.querySelectorAll("#sc-axes button")].find((b) => /azimuth/i.test(b.textContent)); if (btn && !btn.classList.contains("is-active")) btn.click(); });
    await this.until("true", 0.5);
    const map    = await this.rectOf("#sc-map-wrap");
    const mapTop = await this.topOf("#sc-map-wrap", 150);
    const at     = (fx, fy) => this.centerAt(map, mapTop, fx, fy);
    const scroll = new Track([[0, 0], [0.2, 0], [1.4, mapTop], [9.0, mapTop]]);
    const mouse  = new Track([[0, this.pt(1300, 780)], [1.8, at(0.30, 0.28)], [4.0, at(0.60, 0.55)], [4.4, at(0.60, 0.55)], [6.5, at(0.42, 0.80)], [6.9, at(0.42, 0.80)], [9.0, at(0.46, 0.78)]]);
    await this.shoot(2.6, { scroll, mouse, cam: new Track([[0, Camera.still(720, 500)]]) }, 0);

    const rows  = (await this.rectOf("#sc-rows")) || { left: 500, top: mapTop + 200, width: 900, height: 300 };
    const focus = this.centerAt(rows, mapTop, 0.45, Math.min(0.5, 300 / Math.max(rows.height, 1)));
    const cam   = this.pushOn(focus, 2.6, 8.5, 9.0);
    await this.shoot(6.4, { scroll, mouse, cam, clicks: [4.2, 6.7] }, 2.6);
  }

  async sceneGlobe() {
    if (!(await this.page.evaluate(() => document.getElementById("cube-topdown").naturalWidth > 0))) await this.openCube();
    else await this.route("cube");
    await this.click('button.cube-mode[data-view="globe"]');
    await this.until("/\\d/.test(document.getElementById('cube-globe-at').textContent)", 90);
    const globe = "window.app.tomogramView.globe";
    await this.hold("globe imagery", () => this.page.evaluate(`${globe}.viewer.scene.globe.tilesLoaded`), 90);

    const stageTop = await this.topOf("#cube-globe-stage", 120);
    await this.page.evaluate(([move, secs]) => { const m = document.getElementById("cube-globe-move"); m.value = move; m.dispatchEvent(new Event("change", { bubbles: true })); const s = document.getElementById("cube-globe-secs"); s.value = String(secs); s.dispatchEvent(new Event("change", { bubbles: true })); }, [this.move, this.moveSecs]);
    await this.page.evaluate((y) => window.scrollTo({ top: y, behavior: "instant" }), stageTop);
    await this.camera.set(Camera.still(0, 0), stageTop);
    await this.until("true", 0.5);
    await this.page.evaluate(`${globe}.tour.beginOffline()`);
    const settle = async () => {
      for (let i = 0; i < 24; i++) {
        if (await this.page.evaluate(`${globe}.viewer.scene.globe.tilesLoaded`)) return;
        await this.clock.frame();
      }
    };
    const seconds = this.moveSecs + 2;
    const scroll  = new Track([[0, stageTop]]);
    const mouse   = new Track([[0, this.pt(1420, 790)]]);
    await this.shoot(seconds, { scroll, mouse }, 0, async (t) => {
      await this.page.evaluate(([g, ms]) => eval(g).tour.seek(ms), [globe, Math.max(0, (t - 1.0) * 1000)]);
      await settle();
    });
    await this.page.evaluate(`${globe}.tour.endOffline()`);
  }

  launchArgs() {
    const backend = this.gl === "swiftshader" ? ["--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader"] : ["--use-gl=angle", `--use-angle=${this.gl}`, "--ignore-gpu-blocklist"];
    return [
      "--no-sandbox", ...backend, "--hide-scrollbars", "--font-render-hinting=none",
      "--enable-begin-frame-control", "--run-all-compositor-stages-before-draw",
      "--disable-threaded-animation", "--disable-threaded-scrolling", "--disable-checker-imaging",
      `--window-size=${this.viewport.width},${this.viewport.height}`, `--force-device-scale-factor=${this.scale}`,
    ];
  }

  async orchestrate() {
    const { chromium } = require("playwright-core");
    this.framesDir = path.join(this.outDir, `${this.name}_frames`);
    fs.rmSync(this.framesDir, { recursive: true, force: true });
    fs.mkdirSync(this.framesDir, { recursive: true });

    const browser = await chromium.launch({ executablePath: new ChromiumResolver().resolve(), args: this.launchArgs() });
    const context = await browser.newContext({ viewport: null });
    this.page     = await context.newPage();
    this.page.on("pageerror", (err) => console.error("pageerror:", err.message));
    const client  = await context.newCDPSession(this.page);
    this.client   = client;
    this.clock    = new FrameClock(client, this.fps);
    this.camera   = new Camera(client, this.viewport, this.scale);
    this.encoder  = new VideoEncoder(this.ffmpeg, this.framesDir, this.fps);

    this.frozen = false;
    await this.page.goto(`http://127.0.0.1:${this.port}/#/home`, { waitUntil: "domcontentloaded" });
    await this.until("!!document.querySelector('.page[data-page=\"home\"].is-active') && !!window.app", 30);
    if (this.runs) await this.page.evaluate((dir) => { const stored = window.ResultsSources.stored(); window.ResultsSources.save({ ...stored, logs: dir, datasets: stored.datasets || dir }); }, this.runs);
    for (let i = 0; i < 2 * this.fps; i++) await this.clock.frame();
    const parked = this.pointTo(this.pt(this.viewport.width - 4, this.viewport.height - 4));
    await this.clock.frame();
    await parked;
    await this.clock.freeze();
    this.frozen = true;

    const started  = Date.now();
    const handlers = {
      cube     : () => this.sceneCube(),
      sweep    : () => this.sceneSweep(),
      transect : () => this.sceneTransect(),
      slices   : () => this.sceneSlices(),
      globe    : () => this.sceneGlobe(),
    };
    for (const scene of this.scenes) {
      const t0 = Date.now();
      const f0 = this.frameIndex;
      await handlers[scene]();
      console.error(`${scene.padEnd(10)} ${String(this.frameIndex - f0).padStart(4)} frames, ${((Date.now() - t0) / 1000).toFixed(1)} s to render`);
    }
    console.error(`total      ${String(this.frameIndex).padStart(4)} frames = ${(this.frameIndex / this.fps).toFixed(1)} s of video, rendered in ${((Date.now() - started) / 1000).toFixed(1)} s`);

    await browser.close();

    console.error(`encoding ${this.size.width}x${this.size.height} at ${this.fps} fps, crf ${this.crf}, preset ${this.preset}`);
    const target = this.encoder.encode(path.join(this.outDir, `${this.name}.mp4`), this.size, this.frameIndex, this.crf, this.preset);
    if (!this.keepFrames) fs.rmSync(this.framesDir, { recursive: true, force: true });
    console.log(target);
  }
}

new TourRecorder(process.argv.slice(2)).orchestrate().catch((err) => {
  console.error(err.stack || err.message || err);
  process.exit(1);
});
