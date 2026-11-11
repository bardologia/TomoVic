"use strict";

class TomoVisVolumeScriptScene {
  static SIZE = [1000, 800];

  constructor(element, colormaps, print, volume1, volume2, shape, fullscreenTarget = null) {
    this.colormaps = colormaps;
    this.print     = print;

    this.canvas = new VispySceneCanvas(element, { size: TomoVisVolumeScriptScene.SIZE, log: print, embedded: false, fullscreenTarget });
    this.view   = this.canvas.addView({ pos: [0, 0], fill: true });

    this.visVolume1 = new VispyVolumeVisual(volume1, shape, { clim: [0.0, 1.0], threshold: 0.5, relativeStepSize: 0.8, colormaps });
    this.view.addVisual(this.visVolume1);
    this.visVolume2 = new VispyVolumeVisual(volume2, shape, { clim: [0.0, 1.0], threshold: 0.5, relativeStepSize: 0.8, colormaps });
    this.view.addVisual(this.visVolume2);
    this.visVolume2.visible = false;

    const fov  = 60.0;
    const fail = (error) => this.timerError(error);
    this.flyCamera       = new VispyFlyCamera({ fov, name: "Fly", timerError: fail });
    this.turntableCamera = new VispyTurntableCamera({ fov, name: "Turntable" });
    this.arcballCamera   = new VispyArcballCamera({ fov, name: "Arcball" });
    [this.flyCamera, this.turntableCamera, this.arcballCamera].forEach((camera) => this.view.addCamera(camera));
    this.view.camera = this.turntableCamera;

    const [nz, ny, nx] = shape;
    this.center = [nx / 2, ny / 2, nz / 2];
    this.turntableCamera.center = this.center;
    this.arcballCamera.center   = this.center;
    this.turntableCamera.setRange();
    this.arcballCamera.setRange();

    this.axisView             = this.canvas.addView({ pos: [0, 0] });
    this.axisView.interactive = false;
    this.axisView.bgcolor     = [0, 0, 0, 0];
    this.axisCamera           = new VispyTurntableCamera({ fov: 0.0, name: "AxisCamera" });
    this.axisView.addCamera(this.axisCamera);
    this.axisView.camera = this.axisCamera;
    this.axisCamera.setRange({ x: [-1, 1], y: [-1, 1], z: [-1, 1] });
    this.axis = new VispyAxisGizmo();
    this.axisView.addVisual(this.axis);
    this.placeAxisView();
    this.updateAxisView();

    this.opaqueColormaps      = new VispyCycle(colormaps.names);
    this.translucentColormaps = new VispyCycle(colormaps.translucentMaps());
    this.opaqueColormap       = this.opaqueColormaps.next();
    this.translucentColormap  = this.translucentColormaps.next();
    this.visVolume1.cmap      = this.opaqueColormap;
    this.visVolume2.cmap      = this.opaqueColormap;

    this.canvas.connect("draw", () => this.updateAxisView(), "on_draw");
    this.canvas.connect("resize", () => this.placeAxisView(), "on_resize");
    this.canvas.connect("key_press", (event) => this.onKeyPress(event), "on_key_press");
    this.canvas.layout();
  }

  timerError(error) {
    if (!(error instanceof VispyPyError)) throw error;
    this.print([`ERROR: Invoking FlyCamera.on_timer for TimerEvent: ${error.line}`]);
  }

  placeAxisView() {
    const margin = 20;
    const size   = 120;
    const [width] = this.canvas.size;
    this.axisView.setPos([Math.fround(width - size - margin), Math.fround(margin)]);
    this.axisView.setSize([size, size]);
  }

  updateAxisView() {
    const currentCamera = this.view.camera;
    if ([this.turntableCamera].includes(currentCamera)) {
      this.axisView.visible     = true;
      this.axisCamera.elevation = currentCamera.elevation;
      this.axisCamera.azimuth   = currentCamera.azimuth;
      this.axisCamera.roll      = currentCamera.roll;
    } else {
      this.axisView.visible = false;
    }
  }

  static bool(value) {
    return value ? "True" : "False";
  }

  onKeyPress(event) {
    const text = event.text;
    if (text === "1") {
      const cameraToggle = new Map([[this.flyCamera, this.turntableCamera], [this.turntableCamera, this.arcballCamera], [this.arcballCamera, this.flyCamera]]);
      this.view.camera = cameraToggle.get(this.view.camera) || this.turntableCamera;
      this.print([`Camera: ${this.view.camera.name}`]);
      this.updateAxisView();
    } else if (text === "2") {
      const methods = ["mip", "translucent", "iso", "additive"];
      const method  = methods[(methods.indexOf(this.visVolume1.method) + 1) % 4];
      this.print([`Volume rendering method: ${method}`]);
      const cmap = ["mip", "iso"].includes(method) ? this.opaqueColormap : this.translucentColormap;
      this.visVolume1.method = method;
      this.visVolume2.method = method;
      this.visVolume1.cmap   = cmap;
      this.visVolume2.cmap   = cmap;
    } else if (text === "3") {
      this.visVolume1.visible = !this.visVolume1.visible;
      this.visVolume2.visible = !this.visVolume1.visible;
      this.print([`Volume 1 visible: ${TomoVisVolumeScriptScene.bool(this.visVolume1.visible)} | Volume 2 visible: ${TomoVisVolumeScriptScene.bool(this.visVolume2.visible)}`]);
    } else if (text === "4") {
      let cmap;
      if (["mip", "iso"].includes(this.visVolume1.method)) cmap = this.opaqueColormap = this.opaqueColormaps.next();
      else cmap = this.translucentColormap = this.translucentColormaps.next();
      this.visVolume1.cmap = cmap;
      this.visVolume2.cmap = cmap;
      this.print(["Colormap changed"]);
    } else if (text === "0") {
      this.flyCamera.setRange();
      this.turntableCamera.setRange();
      this.arcballCamera.setRange();
      this.turntableCamera.center = this.center;
      this.arcballCamera.center   = this.center;
      this.updateAxisView();
      this.print(["Cameras reset"]);
    } else if (text !== "" && "[]".includes(text)) {
      const step = text === "[" ? -0.025 : 0.025;
      this.visVolume1.threshold += step;
      this.visVolume2.threshold += step;
      const threshold = this.visVolume1.visible ? this.visVolume1.threshold : this.visVolume2.threshold;
      this.print([`Isosurface threshold: ${VispyPyFormat.fixed(threshold, 3)}`]);
    }
    this.canvas.update();
  }

  dispose() {
    this.canvas.dispose();
  }
}

class TomoVisVolumeScript {
  static DEFAULT_PATH = "/ste/rnd/User/mart_gs/tomo_16afrisr0502_Lhv_Capon_Afrisar15x40.hd5";
  static FILTER       = "HDF5 (*.hd5)";

  constructor(root, ctx) {
    this.root     = root;
    this.ctx      = ctx;
    this.scene    = null;
    this.canvasEl = null;
    this.active   = false;
    this.log      = new TomoVisVolumeLog(ctx.session);
    this.build();
  }

  build() {
    const kit = this.ctx.kit;
    this.root.classList.add("tv-script-volume");

    const title = TomoVisInput.el("h3", "tv-script-volume__title", "VolumeRendering.py");
    const row   = TomoVisInput.el("div", "tv-row tv-script-volume__row");
    this.path   = kit.local("line", { placeholder: "path of an .hd5 tomogram on the console host" });
    this.path.set({ text: TomoVisVolumeScript.DEFAULT_PATH });
    this.path.el.classList.add("tv-script-volume__path");
    this.path.options.onReturn = () => this.load();
    this.browseButton = kit.local("button", { text: "Browse" });
    this.loadButton   = kit.local("button", { text: "Load" });
    this.browseButton.onChange = () => this.browse();
    this.loadButton.onChange   = () => this.load();
    row.append(kit.local("label", { text: "File" }).el, this.path.el, this.browseButton.el, this.loadButton.el, TomoVisInput.el("span", "tv-stretch"));

    this.error = TomoVisInput.el("p", "tv-script-volume__error");
    this.error.hidden = true;
    this.stage = TomoVisInput.el("div", "tv-script-volume__stage");
    this.empty = TomoVisInput.el("span", "tv-script-volume__empty", "Load an .hd5 tomogram to open the VolumeRendering canvas.");
    this.orb   = TomoVisInput.el("div", "tv-volume__orb");
    this.orb.innerHTML = ThinkingOrb.html("working", 64, "Loading the volume");
    this.orb.hidden    = true;
    this.stage.append(this.empty, this.orb);

    this.root.append(title, row, this.error, this.stage);
    this.resizer = new ResizeObserver(() => this.resize());
    this.resizer.observe(this.stage);
  }

  async browse() {
    const text   = this.path.text.trim();
    const slash  = text.lastIndexOf("/");
    const result = await this.ctx.dialogs.file({ mode: "open", title: "Open File", filters: [TomoVisVolumeScript.FILTER], selected_filter: TomoVisVolumeScript.FILTER, directory: slash > 0 ? text.slice(0, slash) : null, file: null });
    if (result && result.accepted) this.path.set({ text: result.path });
  }

  showError(text) {
    this.error.textContent = text;
    this.error.hidden      = !text;
  }

  async load() {
    const path = this.path.text.trim();
    if (!path) return;
    this.showError("");
    this.orb.hidden = false;
    try {
      const [colormaps, result] = await Promise.all([VispyColormaps.load(), this.ctx.session.scriptVolume(path)]);
      this.open(colormaps, result);
    } catch (error) {
      if (!(error instanceof TomoVisSessionError)) throw error;
      this.showError(`Could not load ${path}: ${error.message}`);
    } finally {
      this.orb.hidden = true;
    }
  }

  open(colormaps, result) {
    if (this.scene) this.scene.dispose();
    if (this.canvasEl) this.canvasEl.remove();

    this.canvasEl = TomoVisInput.el("canvas", "tv-script-volume__canvas");
    this.canvasEl.tabIndex = 0;
    this.canvasEl.setAttribute("aria-label", "VolumeRendering canvas");
    this.stage.insertBefore(this.canvasEl, this.orb);
    this.empty.hidden = true;

    this.scene = new TomoVisVolumeScriptScene(this.canvasEl, colormaps, (lines) => this.log.write(lines), result.volume1, result.volume2, result.header.shape, this.stage);
    this.scene.canvas.renderer = new VispyVolumeRenderer(this.canvasEl);
    this.scene.canvas.attachDom();
    this.resize();
    this.scene.canvas.show(this.active);
    this.scene.canvas.update();
    this.canvasEl.focus({ preventScroll: true });
  }

  resize() {
    if (!this.scene) return;
    const width  = this.canvasEl.clientWidth;
    const height = this.canvasEl.clientHeight;
    if (width === 0 || height === 0) return;
    this.scene.canvas.setSize([width, height]);
  }

  activate() {
    this.active = true;
    if (this.scene) {
      this.scene.canvas.show(true);
      this.scene.canvas.update();
    }
  }

  deactivate() {
    this.active = false;
    if (this.scene) this.scene.canvas.show(false);
    this.log.flush();
  }
}

window.TomoVisVolumeScriptScene = TomoVisVolumeScriptScene;
window.TomoVisVolumeScript      = TomoVisVolumeScript;
