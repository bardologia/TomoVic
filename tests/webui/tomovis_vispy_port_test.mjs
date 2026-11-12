import assert from "node:assert";
import fs from "node:fs";
import path from "node:path";
import vm from "node:vm";
import { fileURLToPath } from "node:url";

const here   = path.dirname(fileURLToPath(import.meta.url));
const webui  = path.join(here, "..", "..", "webui");
const golden = JSON.parse(fs.readFileSync(path.join(here, "fixtures", "tomovis_vispy", "cameras.json"), "utf-8"));
const cmaps  = JSON.parse(fs.readFileSync(path.join(webui, "static", "data", "tomovis_vispy_colormaps.json"), "utf-8"));

class VispyPortSandbox {
  constructor() {
    const context = {
      console, atob, Math, JSON, Float32Array, Float64Array, Uint8Array, Uint16Array, Array, Object, Number, String, Map, Set, Promise, Error, TypeError,
      performance : { now: () => 0 },
      setInterval : () => 1,
      clearInterval : () => undefined,
      setTimeout  : () => 1,
      clearTimeout : () => undefined,
    };
    context.window = context;
    vm.createContext(context);
    for (const name of ["tomovis_vispy.js", "tomovis_volume.js", "tomovis_script_volume.js"]) vm.runInContext(fs.readFileSync(path.join(webui, "static", "js", name), "utf-8"), context, { filename: name });
    this.context   = context;
    this.colormaps = new context.VispyColormaps(cmaps);
  }
}

class VispyRecordComparer {
  constructor(scenario) {
    this.scenario = scenario;
    this.problems = [];
  }

  close(actual, expected, where, rel = 1e-9, abs = 1e-9) {
    if (expected === null || actual === null) {
      if (expected !== actual) this.problems.push(`${where}: got ${actual}, expected ${expected}`);
      return;
    }
    if (Math.abs(actual - expected) > abs + rel * Math.abs(expected)) this.problems.push(`${where}: got ${actual}, expected ${expected}`);
  }

  list(actual, expected, where, rel, abs) {
    if (actual.length !== expected.length) {
      this.problems.push(`${where}: length ${actual.length} vs ${expected.length}`);
      return;
    }
    expected.forEach((e, i) => this.close(actual[i], e, `${where}[${i}]`, rel, abs));
  }

  same(actual, expected, where) {
    if (JSON.stringify(actual) !== JSON.stringify(expected)) this.problems.push(`${where}: got ${JSON.stringify(actual)}, expected ${JSON.stringify(expected)}`);
  }

  record(actual, expected, where) {
    this.same(actual.camera, expected.camera, `${where}.camera`);
    this.same(actual.canvas_size, expected.canvas_size, `${where}.canvas_size`);
    this.list(actual.view_size, expected.view_size, `${where}.view_size`);
    this.same(actual.axis.visible, expected.axis.visible, `${where}.axis.visible`);
    this.list(actual.axis.pos, expected.axis.pos, `${where}.axis.pos`);
    this.list(actual.axis.size, expected.axis.size, `${where}.axis.size`);
    this.same(actual.printed, expected.printed, `${where}.printed`);

    for (const [name, cam] of Object.entries(expected.cameras)) {
      const got = actual.cameras[name];
      const at  = `${where}.cameras.${name}`;
      this.close(got.scale_factor, cam.scale_factor, `${at}.scale_factor`, 1e-9);
      this.list(got.center.value, cam.center.value, `${at}.center`, 1e-7, 1e-7);
      this.same(got.center.kind, cam.center.kind, `${at}.center.kind`);
      this.close(got.fov, cam.fov, `${at}.fov`);
      for (const key of ["ranged", "has_default", "attached"]) this.same(got[key], cam[key], `${at}.${key}`);
      for (const key of ["elevation", "azimuth", "roll"]) if (key in cam) this.close(got[key], cam[key], `${at}.${key}`, 1e-9, 1e-9);
      if ("quaternion" in cam) this.list(got.quaternion, cam.quaternion, `${at}.quaternion`, 1e-9, 1e-9);
      for (const key of ["rotation1", "rotation2", "speed", "acc"]) if (key in cam) this.list(got[key], cam[key], `${at}.${key}`, 1e-7, 1e-9);
      if ("brake" in cam) this.same(got.brake, cam.brake, `${at}.brake`);
      if ("timer_running" in cam) this.same(got.timer_running, cam.timer_running, `${at}.timer_running`);
    }

    expected.points.forEach((p, i) => this.list(actual.points[i], p, `${where}.points[${i}]`, 1e-6, 1e-6));
    expected.axis_points.forEach((p, i) => this.list(actual.axis_points[i], p, `${where}.axis_points[${i}]`, 1e-6, 1e-6));

    if (expected.visuals) {
      expected.visuals.forEach((v, i) => {
        this.same(actual.visuals[i].method, v.method, `${where}.visuals[${i}].method`);
        this.same(actual.visuals[i].visible, v.visible, `${where}.visuals[${i}].visible`);
        this.close(actual.visuals[i].threshold, v.threshold, `${where}.visuals[${i}].threshold`, 1e-12, 1e-12);
        this.list(actual.visuals[i].clim, v.clim, `${where}.visuals[${i}].clim`);
      });
      this.same(actual.colormaps, expected.colormaps, `${where}.colormaps`);
    }
  }
}

class VispyScenarioPlayer {
  static TRACEBACK = "WARNING: Traceback (most recent call last):";

  static lines(entries) {
    return entries.flatMap((entry) => {
      const rows = String(entry).split("\n");
      return rows[0] === VispyScenarioPlayer.TRACEBACK ? [rows[0], rows[rows.length - 1]] : rows;
    });
  }

  constructor(sandbox, scenario) {
    this.sandbox  = sandbox;
    this.scenario = scenario;
    this.printed  = [];
    const ctx     = sandbox.context;
    const data    = Float32Array.from(scenario.volume);
    const print   = (lines) => this.printed.push(...VispyScenarioPlayer.lines(lines));

    if (scenario.kind === "window") {
      this.volume = new ctx.TomoVisVolume({}, sandbox.colormaps, print);
      this.volume.renderVolume(data, scenario.volume_shape);
      this.volume.canvas.setSize([924, 758]);
      this.scene  = this.volume;
      this.tab    = this.handlers(ctx);
    } else {
      const volume2 = data.map((v) => (v > 0.4 ? 1 : 0));
      this.scene = new ctx.TomoVisVolumeScriptScene({}, sandbox.colormaps, print, data, volume2, scenario.volume_shape);
    }
  }

  handlers(ctx) {
    const tab   = Object.create(ctx.TomoVisVolumeTab.prototype);
    const radio = () => ({ checked: false, set(state) { if ("checked" in state) this.checked = state.checked; } });
    tab.volume                    = this.volume;
    tab.print                     = (...lines) => this.printed.push(...VispyScenarioPlayer.lines(lines));
    tab.turntableCameraTab4Button = radio();
    tab.flyCameraTab4Button       = radio();
    tab.arcballCameraTab4Button   = radio();
    tab.turntableCameraTab4Button.checked = true;
    return tab;
  }

  camera(name) {
    for (const [key, radio] of [["Turntable", this.tab.turntableCameraTab4Button], ["Fly", this.tab.flyCameraTab4Button], ["Arcball", this.tab.arcballCameraTab4Button]]) radio.checked = key === name;
    this.tab.cameraTab4RadioButtonClicked();
  }

  apply(step) {
    const canvas = this.scene.canvas;
    const mods   = step.mods || [];
    if (step.op === "press") canvas.mousePress({ pos: step.pos, button: step.button, buttons: step.buttons, modifiers: mods });
    else if (step.op === "move") canvas.mouseMove({ pos: step.pos, buttons: step.buttons, modifiers: mods });
    else if (step.op === "release") canvas.mouseRelease({ pos: step.pos, button: step.button, buttons: step.buttons, modifiers: mods });
    else if (step.op === "wheel") canvas.mouseWheel({ pos: step.pos, delta: step.delta, buttons: step.buttons || [], modifiers: mods });
    else if (step.op === "key_press") canvas.keyPress({ key: step.key, text: step.text, modifiers: mods });
    else if (step.op === "key_release") canvas.keyRelease({ key: step.key, text: step.text, modifiers: mods });
    else if (step.op === "camera") this.camera(step.name);
    else if (step.op === "reset_cameras") this.tab.resetCamerasTab4ButtonClicked();
    else if (step.op === "timer") for (let i = 0; i < step.count; i += 1) this.scene.flyCamera.timer.emit(step.dt);
    else if (step.op === "resize") canvas.setSize(step.size);
    else throw new Error(`unknown step ${step.op}`);
  }

  static kind(center) {
    if (center === null) return "none";
    return center.kind === "list" ? "list" : "tuple";
  }

  cameraRecord(camera) {
    const record = {
      name          : camera.name,
      scale_factor  : camera.scaleFactor,
      center        : { value: [...camera.center.value], kind: VispyScenarioPlayer.kind(camera._center) },
      fov           : camera.fov,
      ranged        : camera.xlim !== null,
      has_default   : camera.defaultState !== null,
      attached      : camera.viewbox !== null,
    };
    if ("elevation" in camera) Object.assign(record, { elevation: camera.elevation, azimuth: camera.azimuth, roll: camera.roll });
    if (camera.quaternion) record.quaternion = camera.quaternion.toArray();
    if (camera.timer) Object.assign(record, { rotation1: camera.rotation1.toArray(), rotation2: camera.rotation2.toArray(), speed: [...camera.speed], acc: [...camera.acc], brake: [...camera.brake], timer_running: camera.timer.running });
    return record;
  }

  record() {
    const scene   = this.scene;
    scene.updateAxisView();
    const cameras = [scene.turntableCamera, scene.arcballCamera, scene.flyCamera, scene.axisCamera];
    const record  = {
      camera      : scene.view.camera.name,
      canvas_size : [...scene.canvas.size],
      view_size   : [...scene.view.size],
      cameras     : Object.fromEntries(cameras.map((c) => [c.name, this.cameraRecord(c)])),
      axis        : { visible: scene.axisView.visible, pos: [...scene.axisView.pos], size: [...scene.axisView.size] },
      points      : golden.points.map((p) => scene.view.mapVisualToCanvas(p)),
      axis_points : golden.axis_points.map((p) => scene.axisView.mapVisualToCanvas(p)),
      printed     : this.printed.splice(0, this.printed.length),
    };
    if (this.scenario.kind === "script") {
      record.visuals   = [scene.visVolume1, scene.visVolume2].map((v) => ({ method: v.method, threshold: v.threshold, visible: v.visible, clim: v.clim }));
      record.colormaps = { opaque: scene.opaqueColormap, translucent: scene.translucentColormap.cls };
    }
    return record;
  }

  play() {
    const records = [];
    for (const step of this.scenario.steps) {
      if (step.op === "record") records.push(this.record());
      else this.apply(step);
    }
    return records;
  }
}

class VispyPortSuite {
  constructor() {
    this.sandbox = new VispyPortSandbox();
    this.passed  = 0;
  }

  test(name, fn) {
    fn();
    this.passed += 1;
    console.log(`ok ${name}`);
  }

  colormaps() {
    const names = this.sandbox.colormaps.names;
    assert.deepStrictEqual(names.slice(0, 4), ["autumn", "blues", "cool", "greens"]);
    assert.strictEqual(names.length, 27);
    const autumn = this.sandbox.colormaps.get("autumn");
    assert.strictEqual(autumn.lut.length, 1024 * 4);
    assert.deepStrictEqual(Array.from(autumn.lut.slice(0, 4)), [1, 0, 0, 1]);
    assert.deepStrictEqual(Array.from(autumn.lut.slice(-4)), [1, 1, 0, 1]);
    const [fire, grays] = this.sandbox.colormaps.translucentMaps();
    assert.ok(fire.es300.includes("max(0.0, t*1.05 - 0.05)"));
    assert.ok(grays.es300.includes("vec4(t, t, t, t*0.05)"));
    assert.ok(fire.repr().startsWith("<Visualizer.visualizer.Volume.initTranslucentColormaps.<locals>.TransFire object at 0x"));
  }

  formatting() {
    const f = this.sandbox.context.VispyPyFormat;
    assert.strictEqual(f.float(0), "0.0");
    assert.strictEqual(f.float(6), "6.0");
    assert.strictEqual(f.float(0.15283591701637653), "0.15283591701637653");
    assert.strictEqual(f.float(1e16), "1e+16");
    assert.strictEqual(f.float(1.5e-5), "1.5e-05");
    assert.strictEqual(f.float(0.0001), "0.0001");
    assert.strictEqual(f.fixed(0.0625, 3), "0.062");
    assert.strictEqual(f.fixed(0.0635, 3), "0.064");
    assert.strictEqual(f.fixed(21.97736194729805, 3), "21.977");
    assert.strictEqual(f.fixed(-0.0, 3), "-0.000");
    assert.strictEqual(f.fixed(2.5, 0), "2");
    assert.strictEqual(f.fixed(3.5, 0), "4");
    assert.strictEqual(f.sequence([0, 0, 0], "list"), "[0.0, 0.0, 0.0]");
    assert.strictEqual(f.sequence([6, 2, 1], "tuple"), "(6.0, 2.0, 1.0)");
  }

  scenarios() {
    for (const scenario of golden.scenarios) {
      this.test(`scenario ${scenario.name}`, () => {
        const records  = new VispyScenarioPlayer(this.sandbox, scenario).play();
        const comparer = new VispyRecordComparer(scenario);
        assert.strictEqual(records.length, scenario.records.length);
        records.forEach((record, i) => comparer.record(record, scenario.records[i], `${scenario.name}[${i}]`));
        if (comparer.problems.length) throw new Error(`${comparer.problems.length} differences:\n${comparer.problems.slice(0, 40).join("\n")}`);
      });
    }
  }

  shaders() {
    const renderer = this.sandbox.context.VispyVolumeRenderer;
    for (const method of renderer.METHODS) {
      const source = renderer.fragment(method, this.sandbox.colormaps.get("grays"));
      assert.ok(source.includes("vec4 vispy_cmap(float t)"), method);
      assert.ok(!source.includes("gl_FragColor"), method);
      assert.ok(!source.includes("$"), method);
    }
  }

  run() {
    this.test("colormaps follow get_colormaps() and the TomoVis translucent maps", () => this.colormaps());
    this.test("Python float formatting", () => this.formatting());
    this.test("fragment shaders are generated for every method", () => this.shaders());
    this.scenarios();
    console.log(`all ${this.passed} passing`);
  }
}

new VispyPortSuite().run();
