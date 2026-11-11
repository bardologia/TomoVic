import fs from "node:fs";
import path from "node:path";
import { TomoVisHarness as H, TomoVisCheckRun as R, REPO } from "./harness.mjs";

class VolumeProbe {
  static install() {
    window.__tvLog = [];
    const session = window.app.tomovisPage.ctx.session;
    const send    = session.log.bind(session);
    session.log   = (lines) => {
      window.__tvLog.push(...lines);
      return send(lines);
    };

    window.__tvCpu = (tab, px, py) => {
      const M      = window.VispyMatrix;
      const volume = tab.volume;
      const camera = volume.view.camera;
      const visual = volume.volumeVisual.find((v) => v.visible);
      const size   = volume.canvas.size;
      const inv    = M.inverse(camera.clipTransform);
      const x      = (px + 0.5) / size[0] * 2 - 1;
      const y      = 1 - (py + 0.5) / size[1] * 2;
      const unproject = (z) => {
        const p = M.map(inv, [x, y, z]);
        return [p[0] / p[3], p[1] / p[3], p[2] / p[3]];
      };
      const sub   = (a, b) => a.map((v, i) => v - b[i]);
      const add   = (a, b) => a.map((v, i) => v + b[i]);
      const mul   = (a, s) => a.map((v) => v * s);
      const dot   = (a, b) => a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
      const norm  = (a) => mul(a, 1 / Math.hypot(a[0], a[1], a[2]));
      const near  = unproject(-1);
      const far   = unproject(1);
      const ray   = norm(sub(far, near));
      const [nz, ny, nx] = visual.shape;
      const shape = [nx, ny, nz];

      let tmin = -Infinity;
      let tmax = Infinity;
      for (let a = 0; a < 3; a += 1) {
        const t0 = (-0.5 - near[a]) / ray[a];
        const t1 = (shape[a] - 0.5 - near[a]) / ray[a];
        tmin = Math.max(tmin, Math.min(t0, t1));
        tmax = Math.min(tmax, Math.max(t0, t1));
      }
      if (!(tmax > tmin) || tmax < 0) return null;
      const vpos = add(near, mul(ray, tmax));

      const sample = (loc) => {
        const idx = [0, 1, 2].map((a) => {
          const p  = loc[a] * shape[a] - 0.5;
          const i0 = Math.floor(p);
          return [Math.min(Math.max(i0, 0), shape[a] - 1), Math.min(Math.max(i0 + 1, 0), shape[a] - 1), p - i0];
        });
        let v = 0;
        for (const [zi, wz] of [[idx[2][0], 1 - idx[2][2]], [idx[2][1], idx[2][2]]]) {
          for (const [yi, wy] of [[idx[1][0], 1 - idx[1][2]], [idx[1][1], idx[1][2]]]) {
            for (const [xi, wx] of [[idx[0][0], 1 - idx[0][2]], [idx[0][1], idx[0][2]]]) v += wz * wy * wx * visual.scaled[(zi * ny + yi) * nx + xi];
          }
        }
        return v;
      };
      const clim = visual.climNormalized;
      const cmap = (t) => {
        const c = visual.cmap;
        if (c.name === "grays") return [t, t, t, 1];
        if (c.cls === "TransFire") return [Math.pow(t, 0.5), t, t * t, Math.max(0, t * 1.05 - 0.05)];
        if (c.cls === "TransGrays") return [t, t, t, t * 0.05];
        return c.sample(t);
      };
      const apply = (v) => {
        const t = (Math.min(Math.max(v, Math.min(clim[0], clim[1])), Math.max(clim[0], clim[1])) - clim[0]) / (clim[1] - clim[0]);
        return cmap(Math.pow(t, visual.gamma));
      };

      let distance = dot(sub(near, vpos), ray);
      for (let a = 0; a < 3; a += 1) distance = Math.max(distance, Math.min((-0.5 - vpos[a]) / ray[a], (shape[a] - 0.5 - vpos[a]) / ray[a]));
      const front  = add(vpos, mul(ray, distance));
      const nsteps = Math.trunc(-distance / visual.relativeStepSize + 0.5);
      if (nsteps < 1) return null;
      const step  = mul(sub(vpos, front).map((v, a) => v / shape[a]), 1 / nsteps);
      const start = front.map((v, a) => (v + 0.5) / shape[a]);

      let out = null;
      if (visual.method === "mip") {
        let maxval = -3.4028234663852886e38;
        let maxi   = -1;
        let loc    = start;
        for (let iter = 0; iter < nsteps; iter += 1) {
          const val = sample(loc);
          if (val > maxval) {
            maxval = val;
            maxi   = iter;
            if (maxval >= clim[1]) break;
          }
          loc = add(loc, step);
        }
        if (maxi < 0) return null;
        const refine = add(start, mul(step, maxi - 0.5));
        let maxcolor = sample(add(start, mul(step, maxi)));
        loc = refine;
        for (let i = 0; i < 10; i += 1) {
          const val = sample(loc);
          if (val > maxval) {
            maxval   = val;
            maxcolor = val;
          }
          loc = add(loc, mul(step, 0.1));
        }
        out = apply(maxcolor);
      } else if (visual.method === "translucent" || visual.method === "additive") {
        let ic  = [0, 0, 0, 0];
        let loc = start;
        for (let iter = 0; iter < nsteps; iter += 1) {
          const c = apply(sample(loc));
          if (visual.method === "translucent") {
            const a1    = ic[3];
            const a2    = c[3] * (1 - a1);
            const alpha = Math.max(a1 + a2, 0.001);
            ic = ic.map((v, i) => v * (a1 / alpha) + c[i] * a2 / alpha);
            ic[3] = alpha;
            if (alpha > 0.99) break;
          } else {
            ic = ic.map((v, i) => 1 - (1 - v) * (1 - c[i]));
          }
          loc = add(loc, step);
        }
        out = ic;
      } else {
        return { skip: true };
      }
      const a = Math.min(Math.max(out[3], 0), 1);
      return [0, 1, 2].map((i) => Math.round(Math.min(Math.max(out[i] * a, 0), 1) * 255));
    };

    window.__tvGpu = (tab, px, py) => {
      const volume = tab.volume;
      const gl     = volume.canvas.renderer.gl;
      const ratio  = window.devicePixelRatio || 1;
      volume.canvas.draw();
      const pixel = new Uint8Array(4);
      gl.readPixels(Math.floor((px + 0.5) * ratio), Math.floor((volume.canvas.size[1] - py - 0.5) * ratio), 1, 1, gl.RGBA, gl.UNSIGNED_BYTE, pixel);
      return Array.from(pixel.slice(0, 3));
    };
  }
}

class VolumeChecks {
  constructor(options) {
    this.options = options;
    this.run     = new R("volume");
    this.inputs  = H.fixture("inputs");
    this.out     = H.shotDir("volume");
    this.errors  = [];
  }

  async tab() {
    return this.page.evaluateHandle(() => window.app.tomovisPage.views[3]);
  }

  async state() {
    return this.page.evaluate(() => {
      const tab = window.app.tomovisPage.views[3];
      const v   = tab.volume;
      const cam = (c) => c && ({ name: c.name, scale: c.scaleFactor, center: c.center.value, kind: c._center ? c._center.kind : "none", elevation: c.elevation, azimuth: c.azimuth, roll: c.roll, fov: c.fov });
      return {
        hasVolume   : Boolean(v),
        placeholder : !tab.placeholder.hidden,
        canvas      : Boolean(tab.canvasEl),
        slider      : { enabled: tab.isoThresholdTab4Slider.enabled, minimum: tab.isoThresholdTab4Slider.minimum, maximum: tab.isoThresholdTab4Slider.maximum, value: tab.isoThresholdTab4Slider.value },
        radios      : { turntable: tab.turntableCameraTab4Button.checked, fly: tab.flyCameraTab4Button.checked, arcball: tab.arcballCameraTab4Button.checked, mip: tab.mipProjectionTab4Button.checked, iso: tab.isoProjectionTab4Button.checked, translucent: tab.translucentProjectionTab4Button.checked, additive: tab.additiveProjectionTab4Button.checked },
        camera      : v ? v.view.camera.name : null,
        turntable   : v ? cam(v.turntableCamera) : null,
        arcball     : v ? cam(v.arcballCamera) : null,
        fly         : v ? cam(v.flyCamera) : null,
        axisCam     : v ? cam(v.axisCamera) : null,
        axis        : v ? { visible: v.axisView.visible, pos: v.axisView.pos, size: v.axisView.size } : null,
        canvasSize  : v ? v.canvas.size : null,
        cell        : [tab.cell.clientWidth, tab.cell.clientHeight],
        visuals     : v ? v.volumeVisual.map((x) => ({ method: x.method, cmap: x.cmap.name, cls: x.cmap.cls, threshold: x.threshold, visible: x.visible, shape: x.shape, clim: x.clim })) : [],
        nChannels   : v ? v.nChannels : null,
        init        : v ? v.isoThresholdInit : null,
        serial      : tab.serial,
        fullscreen  : v ? v.canvas.fullscreen : null,
      };
    });
  }

  async logLines(count, timeout = 4000) {
    await this.page.waitForFunction((n) => window.__tvLog.length >= n, count, { timeout }).catch(() => null);
    await this.page.waitForTimeout(260);
    return this.page.evaluate(() => window.__tvLog.splice(0, window.__tvLog.length));
  }

  static masked(lines) {
    return lines.map((line) => line.replace(/0x[0-9a-f]+/g, "0xADDRESS"));
  }

  async clickTab(index) {
    await this.page.click(`.tv-tab[data-tab="${index}"]`);
    await H.waitIdle(this.page);
  }

  async waitVolume(serial) {
    await this.page.waitForFunction((s) => {
      const tab = window.app.tomovisPage.views[3];
      return tab.volume && tab.serial === s && tab.loading === 0;
    }, serial, { timeout: 30000 });
    await this.page.waitForTimeout(150);
  }

  async radio(text) {
    await this.page.locator("#tv-panel-3d .tv-radio", { hasText: new RegExp(`^${text}$`) }).click();
  }

  async button(text) {
    await this.page.locator("#tv-panel-3d .tv-button", { hasText: new RegExp(`^${text}$`) }).click();
  }

  async drag(from, to, steps, button = "left") {
    await this.page.mouse.move(from[0], from[1]);
    await this.page.mouse.down({ button });
    for (let i = 1; i <= steps; i += 1) {
      await this.page.waitForTimeout(16);
      await this.page.mouse.move(from[0] + (to[0] - from[0]) * i / steps, from[1] + (to[1] - from[1]) * i / steps);
    }
    await this.page.waitForTimeout(16);
    await this.page.mouse.up({ button });
  }

  async importFile(menuLabel, file) {
    await H.menu(this.page, "File", "Import", menuLabel);
    await H.chooseFile(this.page, file);
  }

  async placeholder() {
    await this.run.check("F-091a", "3D tab before data: centred placeholder, no canvas, ISO slider disabled", async () => {
      await this.clickTab(3);
      const s = await this.state();
      await H.shot(this.page, "04_3d_placeholder", "volume", { element: "#tv-window" });
      H.compareShot("04_3d_placeholder", path.join(this.options.original, "04_startup_3d_placeholder.png"), "volume");
      const text = await this.page.textContent("#tv-panel-3d .tv-volume__placeholder");
      const box  = await this.page.evaluate(() => {
        const cell = document.querySelector(".tv-volume__cell").getBoundingClientRect();
        const ph   = document.querySelector(".tv-volume__placeholder").getBoundingClientRect();
        const col  = document.querySelector("#tv-panel-3d .tv-volume__box").getBoundingClientRect();
        return { cell: [cell.width, cell.height], centred: Math.abs((ph.left + ph.width / 2) - (cell.left + cell.width / 2)) < 2, column: col.width };
      });
      R.equal(text, "3D view will load when this tab is opened", "placeholder text");
      R.equal([s.placeholder, s.canvas, s.slider.enabled, s.hasVolume], [true, false, false, false], "placeholder state");
      R.assert(box.centred, "placeholder not centred");
      R.equal(box.column, 130, "right column width");
      return `cell ${box.cell.join("x")}, column ${box.column}px`;
    });

    await this.run.check("Q-052a", "radios toggle without a volume and print nothing", async () => {
      await this.radio("Fly");
      await this.radio("ISO");
      const s     = await this.state();
      const lines = await this.logLines(0, 300);
      await this.radio("Turntable");
      await this.radio("MIP");
      R.equal([s.radios.fly, s.radios.turntable, s.radios.iso, s.radios.mip], [true, false, true, false], "radio states");
      R.equal(lines, [], "printed lines");
      return "Fly and ISO checked, nothing printed";
    });
  }

  async singleVolume() {
    const goldenSteps = H.golden("volume_single").steps;
    const input       = H.goldenArray("volume_single", "s02_volume_input");

    await this.run.check("F-091b", "import hd5 then open 3D: the server volume arrives and renders once", async () => {
      await this.importFile("hd5", path.join(this.inputs, "fusar_two_key_elev.hd5"));
      await this.clickTab(3);
      const snapshot = await H.snapshot(this.page);
      await this.waitVolume(snapshot.volume.serial);
      const s    = await this.state();
      const data = await this.page.evaluate(() => {
        const v = window.app.tomovisPage.views[3].volume.volumeVisual[0];
        return { shape: v.shape };
      });
      const fetched = await this.page.evaluate(async (serial) => {
        const payload = await window.app.tomovisPage.ctx.session.fetchVolume(serial);
        return { shape: payload.shape, data: Array.from(payload.data) };
      }, snapshot.volume.serial);
      R.equal(fetched.shape, input.shape, "volume shape");
      const maxDiff = Math.max(...fetched.data.map((v, i) => Math.abs(v - input.data[i])));
      R.assert(maxDiff === 0, `volume differs from the golden volume_input by ${maxDiff}`);
      R.equal(data.shape, [2, 4, 12], "visual shape");
      R.equal(s.slider, { enabled: true, minimum: 1, maximum: 100, value: 1 }, "ISO slider after render");
      R.equal([s.placeholder, s.canvas, s.camera], [false, true, "Turntable"], "canvas state");
      const golden = goldenSteps[2].state.volume;
      R.assert(Math.abs(s.turntable.scale - golden.cameras.Turntable.scale_factor) < 1e-9, `turntable scale ${s.turntable.scale}`);
      R.equal([s.turntable.center, s.turntable.kind, s.turntable.elevation, s.turntable.azimuth, s.turntable.fov], [[0, 0, 0], "list", 30, 30, 60], "turntable start (Q-056)");
      R.equal(s.arcball.center, golden.cameras.Arcball.center, "arcball centre");
      R.equal([s.visuals[0].method, s.visuals[0].cmap, s.visuals[0].clim], ["mip", "grays", [golden.data_min, golden.data_max]], "visual defaults");
      R.assert(Math.abs(s.init - golden.iso_threshold_init) < 1e-12, `threshold init ${s.init} vs ${golden.iso_threshold_init}`);
      R.equal(s.axis, { visible: true, pos: [s.canvasSize[0] - 140, 20], size: [120, 120] }, "axis gizmo placement");
      R.equal(s.canvasSize, s.cell, "canvas follows the cell");
      await H.shot(this.page, "40_3d_single", "volume", { element: "#tv-window" });
      H.compareShot("40_3d_single", path.join(this.options.original, "40_3d_single_without_pyopengl.png"), "volume");
      return `volume ${fetched.shape.join("x")} equal to the golden, canvas ${s.canvasSize.join("x")}, scale ${s.turntable.scale.toFixed(4)}`;
    });

    await this.run.check("F-104/fly", "fly keys before the fly camera is ever selected log vispy's timer error, as the original", async () => {
      await this.page.locator("#tv-panel-3d .tv-volume__canvas").focus();
      await this.page.keyboard.down("w");
      await this.page.waitForTimeout(250);
      await this.page.keyboard.up("w");
      await this.page.waitForTimeout(900);
      const errors = (await this.logLines(1)).filter((l) => l.startsWith("ERROR: Invoking FlyCamera.on_timer"));
      R.assert(errors.length > 0, "no fly timer error logged before the fly camera was attached");
      R.equal(errors[0], "ERROR: Invoking FlyCamera.on_timer for TimerEvent: TypeError: unsupported operand type(s) for *: 'float' and 'NoneType'", "timer error text");
      const s = await this.state();
      R.equal([s.fly.scale, s.camera], [null, "Turntable"], "fly camera untouched");
      return `${errors.length} timer errors logged while W was held and the speed decayed`;
    });

    await this.run.check("F-102", "shader probes: GPU pixels equal a CPU ray cast for MIP, translucent and additive", async () => {
      await this.page.evaluate(() => {
        const v = window.app.tomovisPage.views[3].volume;
        const t = v.turntableCamera;
        window.__tvSaved = { center: t._center, scale: t._scaleFactor, elevation: t._elevation, azimuth: t._azimuth, roll: t._roll };
        v.turntableCamera.center      = v.volumeCenter;
        v.turntableCamera.scaleFactor = 14;
        v.turntableCamera.elevation   = 25;
        v.turntableCamera.azimuth     = 40;
      });
      const report = [];
      for (const [method, cmap] of [["mip", "grays"], ["mip", "autumn"], ["translucent", "TransFire"], ["additive", "TransFire"], ["translucent", "TransGrays"]]) {
        const result = await this.page.evaluate(([m, c]) => {
          const tab = window.app.tomovisPage.views[3];
          const v   = tab.volume;
          const vis = v.volumeVisual[0];
          vis.method = m;
          vis.cmap   = c.startsWith("Trans") ? v.colormaps.translucentMaps().find((x) => x.cls === c) : c;
          const [w, h] = v.canvas.size;
          const pixels = [];
          for (let j = 0; j < 9; j += 1) for (let i = 0; i < 9; i += 1) pixels.push([Math.round(w * (0.3 + 0.05 * i)), Math.round(h * (0.3 + 0.05 * j))]);
          let hits = 0;
          let worst = 0;
          for (const [px, py] of pixels) {
            const cpu = window.__tvCpu(tab, px, py);
            const gpu = window.__tvGpu(tab, px, py);
            const ref = cpu === null ? [0, 0, 0] : cpu;
            if (cpu !== null) hits += 1;
            worst = Math.max(worst, ...ref.map((x, k) => Math.abs(x - gpu[k])));
          }
          return { hits, worst, total: pixels.length };
        }, [method, cmap]);
        report.push(`${method}/${cmap}: ${result.hits} hits, max diff ${result.worst}`);
        R.assert(result.hits > 10, `${method}/${cmap}: too few volume pixels (${result.hits})`);
        R.assert(result.worst <= 4, `${method}/${cmap}: GPU differs from the CPU ray cast by ${result.worst}`);
      }
      await this.page.evaluate(() => {
        const v   = window.app.tomovisPage.views[3].volume;
        const vis = v.volumeVisual[0];
        const t   = v.turntableCamera;
        const old = window.__tvSaved;
        vis.method     = "mip";
        vis.cmap       = "grays";
        t._center      = old.center;
        t._scaleFactor = old.scale;
        t._elevation   = old.elevation;
        t._azimuth     = old.azimuth;
        t._roll        = old.roll;
        t.viewChanged();
        v.canvas.update();
      });
      return report.join("; ");
    });

    await this.run.check("F-102/R16F", "half-float fallback (no OES_texture_float_linear) still matches the CPU ray cast", async () => {
      const result = await this.page.evaluate(() => {
        const tab = window.app.tomovisPage.views[3];
        const v   = tab.volume;
        const r   = v.canvas.renderer;
        const vis = v.volumeVisual[0];
        const t   = v.turntableCamera;
        const saved = { center: t._center, scale: t._scaleFactor, elevation: t._elevation, azimuth: t._azimuth };
        t.center = v.volumeCenter;
        t.scaleFactor = 14;
        r.floatLinear = false;
        r.luts.clear();
        vis.textureDirty = true;
        const [w, h] = v.canvas.size;
        let worst = 0;
        let hits  = 0;
        for (const cmap of ["grays", "autumn"]) {
          vis.cmap = cmap;
          for (let j = 0; j < 7; j += 1) for (let i = 0; i < 7; i += 1) {
            const px  = Math.round(w * (0.32 + 0.06 * i));
            const py  = Math.round(h * (0.32 + 0.06 * j));
            const cpu = window.__tvCpu(tab, px, py);
            const gpu = window.__tvGpu(tab, px, py);
            if (cpu !== null) hits += 1;
            worst = Math.max(worst, ...(cpu || [0, 0, 0]).map((x, k) => Math.abs(x - gpu[k])));
          }
        }
        r.floatLinear = Boolean(r.gl.getExtension("OES_texture_float_linear"));
        r.luts.clear();
        vis.textureDirty = true;
        vis.cmap = "grays";
        t._center = saved.center;
        t._scaleFactor = saved.scale;
        t._elevation = saved.elevation;
        t._azimuth = saved.azimuth;
        t.viewChanged();
        return { worst, hits };
      });
      R.assert(result.hits > 10 && result.worst <= 4, `R16F: ${result.hits} hits, max diff ${result.worst}`);
      return `${result.hits} hits, max diff ${result.worst}`;
    });

    await this.run.check("F-095/F-096/F-097", "volume_single sequence: projection, ISO drag, colormaps, prints as the golden", async () => {
      await this.page.evaluate(() => window.__tvLog.splice(0));
      await this.radio("ISO");
      const iso = await this.logLines(1);
      R.equal(iso, goldenSteps[3].stdout, "ISO print");
      const afterIso = await this.state();
      R.equal([afterIso.visuals[0].method, afterIso.visuals[0].cmap], ["iso", "autumn"], "Q-053 first ISO click applies autumn");
      await H.shot(this.page, "3d_iso_autumn", "volume", { element: "#tv-panel-3d" });

      const handle = await this.page.locator("#tv-panel-3d .tv-slider__handle").boundingBox();
      const target = await this.page.evaluate(() => {
        const view   = window.app.tomovisPage.views[3].isoThresholdTab4Slider;
        const groove = view.groove.getBoundingClientRect();
        return groove.left + view.positionFromValue(50) + 7;
      });
      const startX = handle.x + handle.width / 2;
      const y      = handle.y + handle.height / 2;
      await this.page.mouse.move(startX, y);
      await this.page.mouse.down();
      await this.page.mouse.move(target, y, { steps: Math.max(1, Math.round(target - startX)) });
      await this.page.mouse.up();
      const lines = await this.logLines(49);
      const s     = await this.state();
      R.equal(s.slider.value, 50, "slider value after the drag");
      R.equal(lines, goldenSteps[4].stdout, "ISO threshold prints (one-step lag, Q-054)");
      R.assert(Math.abs(s.visuals[0].threshold - 49 * s.init) < 1e-12, `threshold ${s.visuals[0].threshold}`);

      await this.page.locator("#tv-panel-3d .tv-slider").focus();
      await this.page.keyboard.press("ArrowRight");
      const keyLines = await this.logLines(0, 400);
      const afterKey = await this.state();
      R.equal([keyLines, afterKey.slider.value, afterKey.visuals[0].threshold], [[], 51, s.visuals[0].threshold], "keys move the slider but not the threshold (Q-054)");
      await H.shot(this.page, "3d_iso_threshold_50", "volume", { element: "#tv-panel-3d" });

      const sequence = [
        ["radio", "Translucent", 5], ["button", "colormap", 6], ["button", "colormap", 7], ["radio", "Additive", 8],
        ["radio", "MIP", 9], ["button", "colormap", 10], ["radio", "Fly", 11], ["radio", "Arcball", 12], ["radio", "Turntable", 13],
        ["button", "reset cameras", 14], ["button", "channel", 15],
      ];
      const shots = { Translucent: "3d_translucent_transfire", 6: "3d_translucent_transgrays", Additive: "3d_additive", 10: "3d_mip_blues", Fly: "3d_fly_no_gizmo", 14: "3d_reset_cameras" };
      for (const [kind, label, step] of sequence) {
        if (kind === "radio") await this.radio(label);
        else await this.button(label);
        const got = VolumeChecks.masked(await this.logLines(goldenSteps[step].stdout.length));
        R.equal(got, goldenSteps[step].stdout, `${label} prints`);
        const name = shots[label] || shots[step];
        if (name) {
          await this.page.waitForTimeout(120);
          await H.shot(this.page, name, "volume", { element: "#tv-panel-3d" });
        }
      }
      const end    = await this.state();
      const golden = goldenSteps[15].state.volume;
      R.equal([end.visuals[0].method, end.visuals[0].cmap, end.camera, end.radios.turntable], ["mip", "blues", "Turntable", true], "end state");
      R.equal(end.turntable.center, golden.cameras.Turntable.center, "reset centre");
      R.equal(end.turntable.kind, "tuple", "reset centre is a tuple");
      return "every print equals the golden; ISO drag printed 49 lagged thresholds";
    });

    await this.run.check("F-094/F-100", "camera radios: gizmo only with the turntable, each camera keeps its state", async () => {
      const before = await this.state();
      await this.radio("Arcball");
      await this.logLines(3);
      const arc = await this.state();
      await this.radio("Turntable");
      await this.logLines(3);
      const back = await this.state();
      R.equal([arc.camera, arc.axis.visible, back.camera, back.axis.visible], ["Arcball", false, "Turntable", true], "gizmo visibility");
      R.equal(back.turntable, before.turntable, "turntable state kept across the switch");
      return "gizmo hidden for Arcball, turntable state unchanged on return";
    });

    await this.run.check("F-104", "mouse on the canvas: orbit, wheel zoom, right-drag zoom, Shift translate; gizmo follows", async () => {
      const box = await this.page.locator("#tv-panel-3d .tv-volume__canvas").boundingBox();
      const cx  = box.x + box.width / 2;
      const cy  = box.y + box.height / 2;
      const s0  = await this.state();
      await this.drag([cx, cy], [cx + 40, cy + 20], 4);
      const s1 = await this.state();
      R.equal([s1.turntable.azimuth, s1.turntable.elevation], [s0.turntable.azimuth - 20, s0.turntable.elevation + 10], "orbit: 0.5 degree per pixel");
      R.equal([s1.axisCam.azimuth, s1.axisCam.elevation], [s1.turntable.azimuth, s1.turntable.elevation], "gizmo copies the turntable angles");

      await this.page.mouse.move(cx, cy);
      await this.page.mouse.wheel(0, -100);
      await this.page.waitForTimeout(100);
      const s2 = await this.state();
      const delta = await this.page.evaluate(() => 100 * 1.2 / 120);
      R.assert(Math.abs(s2.turntable.scale - s1.turntable.scale * Math.pow(1.1, -delta)) < 1e-9, `wheel zoom ${s2.turntable.scale} from ${s1.turntable.scale}`);

      await this.drag([cx, cy], [cx, cy - 30], 3, "right");
      const s3 = await this.state();
      R.assert(Math.abs(s3.turntable.scale - s2.turntable.scale * Math.pow(1.007, -30)) < 1e-9, `right-drag zoom ${s3.turntable.scale}`);

      await this.page.keyboard.down("Shift");
      await this.drag([cx, cy], [cx - 30, cy], 3);
      await this.page.keyboard.up("Shift");
      const s4 = await this.state();
      R.assert(s4.turntable.kind === "tuple" && s4.turntable.center.some((v, i) => Math.abs(v - s3.turntable.center[i]) > 1e-6), "Shift drag moved the centre");
      await H.shot(this.page, "3d_after_orbit", "volume", { element: "#tv-panel-3d" });
      return `azimuth ${s1.turntable.azimuth}, scale ${s3.turntable.scale.toFixed(3)}, centre ${s4.turntable.center.map((v) => v.toFixed(2)).join(", ")}`;
    });

    await this.run.check("F-104/fly2", "after selecting Fly, W moves the fly camera", async () => {
      await this.radio("Fly");
      await this.logLines(3);
      const f0 = await this.state();
      await this.page.locator("#tv-panel-3d .tv-volume__canvas").focus();
      await this.page.keyboard.down("w");
      await this.page.waitForTimeout(300);
      await this.page.keyboard.up("w");
      await this.page.waitForTimeout(600);
      const f1 = await this.state();
      R.assert(f1.fly.center.some((v, i) => Math.abs(v - f0.fly.center[i]) > 1e-3), "W did not move the fly camera");
      await H.shot(this.page, "3d_fly_moved", "volume", { element: "#tv-panel-3d" });
      await this.radio("Turntable");
      await this.logLines(3);
      return `fly centre ${f0.fly.center.map((v) => v.toFixed(2)).join(", ")} -> ${f1.fly.center.map((v) => v.toFixed(2)).join(", ")}`;
    });

    await this.run.check("GL", "a lost WebGL context is restored and the volume draws again", async () => {
      const result = await this.page.evaluate(async () => {
        const tab  = window.app.tomovisPage.views[3];
        const r    = tab.volume.canvas.renderer;
        const ext  = r.gl.getExtension("WEBGL_lose_context");
        const wait = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
        const grid = () => {
          const [w, h] = tab.volume.canvas.size;
          let lit = 0;
          for (let j = 1; j < 8; j += 1) for (let i = 1; i < 8; i += 1) if (Math.max(...window.__tvGpu(tab, Math.round(w * i / 8), Math.round(h * j / 8))) > 0) lit += 1;
          return lit;
        };
        const before = grid();
        ext.loseContext();
        await wait(150);
        const lost = r.lost;
        ext.restoreContext();
        await wait(400);
        return { before, lost, restored: !r.lost, after: grid() };
      });
      R.equal([result.lost, result.restored], [true, true], "context lost and restored");
      R.assert(result.after > 0 && result.after === result.before, `lit pixels ${result.before} before, ${result.after} after`);
      return `${result.after} of 49 probe pixels lit before and after the restore`;
    });

    await this.run.check("F-103", "F11 on the embedded canvas toggles vispy's flag only, as Qt does for a child widget", async () => {
      await this.page.locator("#tv-panel-3d .tv-volume__canvas").focus();
      const before = await this.state();
      await this.page.keyboard.press("F11");
      const after = await this.state();
      const fullscreen = await this.page.evaluate(() => Boolean(document.fullscreenElement));
      await this.page.keyboard.press("F11");
      const again = await this.state();
      R.equal([before.fullscreen, after.fullscreen, again.fullscreen, fullscreen], [false, true, false, false], "fullscreen flag");
      R.equal(after.canvasSize, before.canvasSize, "canvas size unchanged");
      return "flag toggled, geometry unchanged (measured in the original: QRect unchanged after F11)";
    });

    await this.run.check("F-098", "Backspace resets every attached camera to its default state", async () => {
      await this.page.locator("#tv-panel-3d .tv-volume__canvas").focus();
      await this.page.keyboard.press("Backspace");
      const s = await this.state();
      R.equal([s.turntable.center, s.turntable.kind, s.turntable.elevation, s.turntable.azimuth], [[0, 0, 0], "tuple", 30, 30], "turntable default state");
      await this.button("reset cameras");
      await this.logLines(1);
      return "turntable back to its first state (0, 0, 0), 30, 30";
    });
  }

  async channels() {
    await this.run.check("F-099", "three-channel cube: 16 slab visuals, channel steps through them (Q-050)", async () => {
      await this.importFile("npy", path.join(this.inputs, "npy_channels_3.npy"));
      const s0 = await this.state();
      R.equal([s0.hasVolume, s0.slider.enabled], [false, false], "import drops the volume and disables the ISO slider");
      await this.clickTab(3);
      const snapshot = await H.snapshot(this.page);
      await this.waitVolume(snapshot.volume.serial);
      const s = await this.state();
      R.equal([s.nChannels, s.visuals[0].shape, s.visuals.filter((v) => v.visible).length], [16, [1, 2, 12], 1], "slabs");
      await this.page.evaluate(() => window.__tvLog.splice(0));
      await this.button("channel");
      await this.button("channel");
      const lines = await this.logLines(2);
      R.equal(lines, ["Selected channel: 1", "Selected channel: 2"], "channel prints (golden volume_channels_3)");
      const after = await this.state();
      R.equal(after.visuals.map((v) => v.visible).indexOf(true), 2, "visible slab");
      const golden = H.golden("volume_channels_3").steps[2].state.volume;
      R.equal(after.arcball.center, golden.volume_center, "volume centre");
      await H.shot(this.page, "3d_channels_slab2", "volume", { element: "#tv-panel-3d" });
      return `${s.nChannels} visuals, slab 2 visible`;
    });

    await this.run.check("F-091c", "re-import while a view exists: the next 3D visit builds a new view (volume_reload)", async () => {
      const first = await this.state();
      await this.clickTab(0);
      await this.importFile("hd5", path.join(this.inputs, "fusar_one_key_range.hd5"));
      await this.clickTab(3);
      const snapshot = await H.snapshot(this.page);
      await this.waitVolume(snapshot.volume.serial);
      const s = await this.state();
      R.assert(s.serial > first.serial, "serial did not advance");
      R.equal([s.slider.value, s.slider.enabled, s.visuals[0].shape, s.camera], [1, true, snapshot.volume.shape, "Turntable"], "new view");
      R.equal([s.radios.turntable, s.radios.mip], [true, true], "radios kept as they were (Q-052)");
      const canvases = await this.page.$$eval("#tv-panel-3d .tv-volume__canvas", (nodes) => nodes.length);
      R.equal(canvases, 1, "the old canvas is replaced, not stacked");
      return `volume ${s.visuals[0].shape.join("x")}`;
    });
  }

  async realistic() {
    const file = path.join(REPO, "logs/tomovis_port/fixtures/realistic_traun_hv.hd5");
    if (!fs.existsSync(file)) return;
    await this.run.check("look", "realistic crop: translucent view next to Doc/04.jpg", async () => {
      await this.clickTab(0);
      await this.importFile("hd5", file);
      await this.clickTab(3);
      const snapshot = await H.snapshot(this.page);
      await this.waitVolume(snapshot.volume.serial);
      await this.button("reset cameras");
      await this.radio("Translucent");
      await this.page.waitForTimeout(400);
      await H.shot(this.page, "3d_realistic_translucent", "volume", { element: "#tv-window" });
      H.compareShot("3d_realistic_translucent", path.join(REPO, "../tomovis/Visualizer/Doc/04.jpg"), "volume");
      await this.radio("MIP");
      await this.page.waitForTimeout(300);
      await H.shot(this.page, "3d_realistic_mip", "volume", { element: "#tv-window" });
      await this.radio("ISO");
      await this.page.waitForTimeout(300);
      await H.shot(this.page, "3d_realistic_iso", "volume", { element: "#tv-window" });
      const s = await this.state();
      return `volume ${s.visuals[0].shape.join("x")}`;
    });
  }

  async logRoute() {
    await this.run.check("F-153", "3D prints reach the console log with the TomoVis prefix", async () => {
      await this.page.waitForTimeout(500);
      const text = fs.readFileSync(path.join(REPO, "logs/tomovis_port/volume/console_8805.log"), "utf-8");
      for (const line of ["TomoVis: Projection method: iso", "TomoVis: Cameras reset", "TomoVis: Selected channel: 1"]) R.assert(text.includes(line), `console log lacks ${line}`);
      return "Projection, reset and channel prints found in the console log";
    });
  }

  async script() {
    await this.run.check("F-151", "VolumeRendering panel: load, keys 1 2 3 4 0 [ ], prints as the original script", async () => {
      await this.page.goto(`${H.base}/#/tomovis_scripts`);
      await this.page.waitForFunction(() => window.app.tomovisScriptsPage && window.app.tomovisScriptsPage.views.length === 2, null, { timeout: 30000 });
      await this.page.evaluate(() => {
        window.__tvLog = [];
        const session = window.app.tomovisScriptsPage.ctx.session;
        const send    = session.log.bind(session);
        session.log   = (lines) => {
          window.__tvLog.push(...lines);
          return send(lines);
        };
      });
      await this.page.fill("#tv-script-volume .tv-script-volume__path", path.join(this.inputs, "fusar_two_key_elev.hd5"));
      await this.page.locator("#tv-script-volume .tv-button", { hasText: /^Load$/ }).click();
      await this.page.waitForFunction(() => window.app.tomovisScriptsPage.views[1].scene !== null, null, { timeout: 30000 });
      await this.page.waitForTimeout(300);
      const canvas = this.page.locator("#tv-script-volume .tv-script-volume__canvas");
      const size   = await canvas.evaluate((c) => [c.clientWidth, c.clientHeight]);
      R.equal(size, [1000, 800], "canvas size");
      await H.shot(this.page, "script_volume_loaded", "volume", { element: "#tv-script-volume" });
      await canvas.focus();
      const keys = ["1", "1", "1", "2", "4", "2", "3", "[", "]", "3", "0"];
      for (const key of keys) await this.page.keyboard.press(key);
      await this.page.waitForTimeout(400);
      const lines = await this.page.evaluate(() => window.__tvLog.splice(0));
      const expected = ["Camera: Arcball", "Camera: Fly", "Camera: Turntable", "Volume rendering method: translucent", "Colormap changed", "Volume rendering method: iso", "Volume 1 visible: False | Volume 2 visible: True", "Isosurface threshold: 0.475", "Isosurface threshold: 0.500", "Volume 1 visible: True | Volume 2 visible: False", "Cameras reset"];
      R.equal(lines, expected, "script prints");
      const state = await this.page.evaluate(() => {
        const sc = window.app.tomovisScriptsPage.views[1].scene;
        return { method: sc.visVolume1.method, cmap: sc.visVolume1.cmap.name, threshold: sc.visVolume1.threshold, camera: sc.view.camera.name, gizmo: sc.axisView.visible };
      });
      R.equal([state.method, state.cmap, state.camera, state.gizmo], ["iso", "autumn", "Turntable", true], "script state");
      await H.shot(this.page, "script_volume_iso", "volume", { element: "#tv-script-volume" });
      return lines.join(" | ");
    });
  }

  async noWebGL() {
    await this.run.check("F-090", "without WebGL2 there is no 3D tab", async () => {
      const bare = await H.launch({ port: this.options.port, gl: this.options.gl, webgl: false });
      await H.openTomoVis(bare.page);
      const tabs = await bare.page.$$eval(".tv-tab", (nodes) => nodes.filter((n) => !n.hidden).map((n) => n.textContent));
      const view = await bare.page.evaluate(() => window.app.tomovisPage.views[3]);
      this.errors.push(...bare.errors);
      await bare.browser.close();
      R.equal([tabs, view], [["Slicer", "Plot", "Profile"], null], "tabs");
      return tabs.join(", ");
    });
  }

  async main() {
    const opened = await H.launch({ port: this.options.port, gl: this.options.gl });
    this.page    = opened.page;
    await H.openTomoVis(this.page);
    await this.page.evaluate(VolumeProbe.install);

    await this.placeholder();
    await this.singleVolume();
    await this.channels();
    await this.realistic();
    await this.logRoute();
    await this.script();
    await this.noWebGL();

    await opened.browser.close();
    const errors = [...opened.errors, ...this.errors];
    const ok     = this.run.summary(errors);
    fs.writeFileSync(path.join(this.out, "volume_checks.json"), JSON.stringify({ results: this.run.results, errors }, null, 2));
    process.exit(ok ? 0 : 1);
  }
}

const options = H.args(process.argv);
options.original = process.env.TOMOVIS_ORIGINAL_SHOTS || path.join(REPO, "logs/tomovis_port/original_shots");
await new VolumeChecks(options).main();
