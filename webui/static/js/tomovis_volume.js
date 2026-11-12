"use strict";

class TomoVisVolumeLog {
  static FLUSH_MS = 200;

  constructor(session) {
    this.session = session;
    this.lines   = [];
    this.timer   = null;
  }

  write(lines) {
    this.lines.push(...lines);
    if (this.timer === null) this.timer = setTimeout(() => this.flush(), TomoVisVolumeLog.FLUSH_MS);
  }

  flush() {
    this.timer = null;
    if (this.lines.length === 0 || !this.session.sid) return;
    const lines = this.lines.splice(0, this.lines.length);
    this.session.log(lines).then((result) => {
      if (result && result.ok === false) console.warn(`TomoVis 3D log was not delivered: ${result.error}`);
    });
  }
}

class TomoVisVolume {
  constructor(element, colormaps, print, { size = [800, 600], embedded = true, fullscreenTarget = null } = {}) {
    this.view              = null;
    this.canvas            = null;
    this.flyCamera         = null;
    this.turntableCamera   = null;
    this.arcballCamera     = null;
    this.axis              = null;
    this.axisView          = null;
    this.axisCamera        = null;
    this.volumeCenter      = null;
    this.translucentCmaps  = null;
    this.translucentCmap   = null;
    this.opaqueCmaps       = null;
    this.opaqueCmap        = null;
    this.volumeVisual      = [];
    this.colormaps         = colormaps;
    this.print             = print;

    this.canvas = new VispySceneCanvas(element, { size, log: print, embedded, fullscreenTarget });
    this.view   = this.canvas.addView({ pos: [0, 0], size: this.canvas.size, fill: true });

    this.initCameras();
    this.initAxis();
    this.initTranslucentColormaps();
    this.initOpaqueColormaps();
    this.initAxisEvents();
  }

  timerError(error, count) {
    if (!(error instanceof VispyPyError)) throw error;
    if (count === 1) this.print([`WARNING: ${error.traceback}`, "ERROR: Invoking FlyCamera.on_timer for Event"]);
    else if (VispyPyError.reminder(count)) this.print([`ERROR: Invoking FlyCamera.on_timer repeat ${count}`]);
  }

  initCameras() {
    const fov  = 60.0;
    const fail = (error, count) => this.timerError(error, count);
    this.flyCamera       = new VispyFlyCamera({ fov, name: "Fly", timerError: fail });
    this.turntableCamera = new VispyTurntableCamera({ fov, name: "Turntable" });
    this.arcballCamera   = new VispyArcballCamera({ fov, name: "Arcball" });
    [this.flyCamera, this.turntableCamera, this.arcballCamera].forEach((camera) => this.view.addCamera(camera));
    this.view.camera = this.turntableCamera;
  }

  initAxis() {
    this.axisView             = this.canvas.addView({ pos: [0, 0] });
    this.axisView.interactive = false;
    this.axisView.bgcolor     = [0, 0, 0, 0];

    this.axisCamera = new VispyTurntableCamera({ fov: 0.0, name: "AxisCamera" });
    this.axisView.addCamera(this.axisCamera);
    this.axisView.camera = this.axisCamera;
    this.axisCamera.setRange({ x: [-1, 1], y: [-1, 1], z: [-1, 1] });

    this.axis = new VispyAxisGizmo();
    this.axisView.addVisual(this.axis);

    this.placeAxisView();
    this.updateAxisView();
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
    if (currentCamera === this.turntableCamera) {
      this.axisView.visible      = true;
      this.axisCamera.elevation  = this.turntableCamera.elevation;
      this.axisCamera.azimuth    = this.turntableCamera.azimuth;
      this.axisCamera.roll       = this.turntableCamera.roll;
    } else {
      this.axisView.visible = false;
    }
  }

  initAxisEvents() {
    this.canvas.connect("draw", () => this.updateAxisView(), "Volume.on_draw");
    this.canvas.connect("resize", () => this.placeAxisView(), "Volume.on_resize");
  }

  initTranslucentColormaps() {
    this.translucentCmaps = new VispyCycle(this.colormaps.translucentMaps());
    this.translucentCmap  = this.translucentCmaps.next();
  }

  initOpaqueColormaps() {
    this.opaqueCmaps = new VispyCycle(this.colormaps.names);
    this.opaqueCmap  = this.opaqueCmaps.next();
  }

  static slab(data, shape, index) {
    const [s0, s1, s2, s3] = shape;
    const out = new Float32Array(s0 * s1 * s2);
    for (let i = 0; i < s0 * s1 * s2; i += 1) out[i] = data[i * s3 + index];
    return out;
  }

  renderVolume(dataVolume, shape) {
    [this.dataVolumeMin, this.dataVolumeMax] = VispyVolumeVisual.limits(dataVolume);

    const [nx, ny, nz] = shape.slice(0, 3).reverse();
    this.volumeCenter  = [nx / 2, ny / 2, nz / 2];

    this.turntableCamera.center = this.volumeCenter;
    this.arcballCamera.center   = this.volumeCenter;
    this.turntableCamera.setRange();
    this.arcballCamera.setRange();
    this.flyCamera.setRange();

    let volumes;
    if (shape.length === 4) {
      this.nChannels = shape[3];
      volumes = Array.from({ length: this.nChannels }, (_, i) => TomoVisVolume.slab(dataVolume, shape, i));
    } else {
      this.nChannels = 1;
      volumes = [dataVolume];
    }

    this.volumeVisual = [];
    for (let i = 0; i < this.nChannels; i += 1) {
      const vis = new VispyVolumeVisual(volumes[i], shape.slice(0, 3), { clim: [this.dataVolumeMin, this.dataVolumeMax], relativeStepSize: 0.8, colormaps: this.colormaps });
      this.view.addVisual(vis);
      vis.visible = false;
      this.volumeVisual.push(vis);
    }

    this.volumeVisual[0].visible = true;
    this.isoThresholdInit = this.volumeVisual[0].threshold;

    this.volumeVisualVisibleIterator    = new Array(this.nChannels).fill(false);
    this.volumeVisualVisibleIterator[0] = true;
  }

  dispose() {
    this.canvas.dispose();
  }
}

class TomoVisVolumeTab {
  static PLACEHOLDER = "3D view will load when this tab is opened";

  constructor(root, ctx) {
    this.root      = root;
    this.ctx       = ctx;
    this.volume    = null;
    this.serial    = 0;
    this.loading   = 0;
    this.active    = false;
    this.display   = null;
    this.canvasEl  = null;
    this.log       = new TomoVisVolumeLog(ctx.session);

    this.createLayout();
    this.signals();

    this.resizer = new ResizeObserver(() => this.resize());
    this.resizer.observe(this.cell);

    ctx.bus.on("snapshot", ({ snapshot, previous }) => this.follow(snapshot, previous));
    ctx.bus.on("page", ({ active }) => this.pageShown(active));
    if (ctx.session.snapshot) this.follow(ctx.session.snapshot, null);
  }

  createLayout() {
    const kit = this.ctx.kit;
    this.root.classList.add("tv-volume");

    this.cell        = TomoVisInput.el("div", "tv-volume__cell");
    this.placeholder = TomoVisInput.el("span", "tv-volume__placeholder", TomoVisVolumeTab.PLACEHOLDER);
    this.orb         = TomoVisInput.el("div", "tv-volume__orb");
    this.orb.innerHTML = ThinkingOrb.html("working", 64, "Loading the 3D volume");
    this.orb.hidden  = true;
    this.cell.append(this.placeholder, this.orb);

    this.cameraTab4ButtonBox        = kit.local("group", { title: "Camera" });
    this.turntableCameraTab4Button  = kit.local("radio", { text: "Turntable", group: "tv3d-camera" });
    this.flyCameraTab4Button        = kit.local("radio", { text: "Fly", group: "tv3d-camera" });
    this.arcballCameraTab4Button    = kit.local("radio", { text: "Arcball", group: "tv3d-camera" });
    this.turntableCameraTab4Button.set({ checked: true });
    this.cameraTab4ButtonBox.body.append(this.turntableCameraTab4Button.el, this.flyCameraTab4Button.el, this.arcballCameraTab4Button.el);

    this.projectionTab4ButtonBox          = kit.local("group", { title: "Projection" });
    this.mipProjectionTab4Button          = kit.local("radio", { text: "MIP", group: "tv3d-projection" });
    this.isoProjectionTab4Button          = kit.local("radio", { text: "ISO", group: "tv3d-projection" });
    this.translucentProjectionTab4Button  = kit.local("radio", { text: "Translucent", group: "tv3d-projection" });
    this.additiveProjectionTab4Button     = kit.local("radio", { text: "Additive", group: "tv3d-projection" });
    this.mipProjectionTab4Button.projection         = "mip";
    this.isoProjectionTab4Button.projection         = "iso";
    this.translucentProjectionTab4Button.projection = "translucent";
    this.additiveProjectionTab4Button.projection    = "additive";
    this.mipProjectionTab4Button.set({ checked: true });
    this.projectionTab4ButtonBox.body.append(this.mipProjectionTab4Button.el, this.isoProjectionTab4Button.el, this.translucentProjectionTab4Button.el, this.additiveProjectionTab4Button.el);

    this.isoLabel               = kit.local("label", { text: "ISO threshold" });
    this.isoThresholdTab4Slider = kit.local("slider", { maxWidth: 130, onSliderMoved: () => this.isoThresholdTab4SliderMoved() });
    this.isoThresholdTab4Slider.set({ enabled: false });

    this.colormapTab4Button     = kit.local("button", { text: "colormap", maxWidth: 100 });
    this.resetCamerasTab4Button = kit.local("button", { text: "reset cameras", maxWidth: 100 });
    this.channelTab4Button      = kit.local("button", { text: "channel", maxWidth: 100 });

    const buttons = TomoVisInput.el("div", "tv-volume__buttons");
    buttons.append(this.colormapTab4Button.el, this.resetCamerasTab4Button.el, this.channelTab4Button.el);

    this.cameraTab4ButtonBox.el.classList.add("tv-volume__box");
    this.projectionTab4ButtonBox.el.classList.add("tv-volume__box");
    this.isoLabel.el.classList.add("tv-volume__label");
    this.isoThresholdTab4Slider.el.classList.add("tv-volume__slider");

    this.root.append(this.cell, this.cameraTab4ButtonBox.el, this.projectionTab4ButtonBox.el, this.isoLabel.el, this.isoThresholdTab4Slider.el, buttons);
  }

  signals() {
    this.colormapTab4Button.onChange     = () => this.colormapTab4ButtonClicked();
    this.resetCamerasTab4Button.onChange = () => this.resetCamerasTab4ButtonClicked();
    this.channelTab4Button.onChange      = () => this.channelTab4ButtonClicked();

    for (const radio of [this.flyCameraTab4Button, this.arcballCameraTab4Button, this.turntableCameraTab4Button]) radio.onChange = () => this.cameraTab4RadioButtonClicked();
    for (const radio of [this.mipProjectionTab4Button, this.isoProjectionTab4Button, this.additiveProjectionTab4Button, this.translucentProjectionTab4Button]) radio.onChange = (value, how, view) => this.projectionTab4RadioButtonClicked(view);
  }

  print(...lines) {
    this.log.write(lines.map((line) => String(line)));
  }

  follow(snapshot, previous) {
    const volume = snapshot.volume;
    const slider = snapshot.controls.isoThresholdTab4Slider;

    const fresh = previous === null || (volume.serial === 0 && this.serial !== 0);
    if (fresh) this.isoThresholdTab4Slider.set({ minimum: slider.minimum, maximum: slider.maximum, value: slider.value, enabled: slider.enabled });
    else if (!slider.enabled && this.isoThresholdTab4Slider.enabled) this.isoThresholdTab4Slider.set({ enabled: false });

    if (!volume.rendered) this.volume = null;
    if (volume.serial === 0 && this.serial !== 0) this.clear();
    if (volume.rendered && volume.serial !== 0 && volume.serial !== this.serial) this.load(volume.serial);
  }

  clear() {
    this.serial = 0;
    this.volume = null;
    if (this.display) this.display.dispose();
    this.display = null;
    if (this.canvasEl) this.canvasEl.remove();
    this.canvasEl = null;
    this.placeholder.hidden = false;
  }

  async load(serial) {
    this.serial  = serial;
    this.loading += 1;
    this.orb.hidden = false;
    try {
      const [colormaps, payload] = await Promise.all([VispyColormaps.load(), this.ctx.session.fetchVolume(serial)]);
      if (serial !== this.serial) return;
      this.ensure3DLoaded(colormaps, payload);
    } catch (error) {
      if (serial === this.serial && !(error instanceof TomoVisSessionError && error.status === 404)) Toast.show(`TomoVis 3D view: ${error.message}`, "error");
      if (serial === this.serial && !(error instanceof TomoVisSessionError)) throw error;
    } finally {
      this.loading -= 1;
      this.orb.hidden = this.loading === 0;
    }
  }

  ensure3DLoaded(colormaps, payload) {
    if (this.display) this.display.dispose();
    if (this.canvasEl) this.canvasEl.remove();

    this.canvasEl = TomoVisInput.el("canvas", "tv-volume__canvas");
    this.canvasEl.tabIndex = 0;
    this.canvasEl.setAttribute("aria-label", "3D volume view");
    this.cell.insertBefore(this.canvasEl, this.orb);
    this.placeholder.hidden = true;

    this.display = new TomoVisVolume(this.canvasEl, colormaps, (lines) => this.log.write(lines));
    this.display.canvas.renderer = new VispyVolumeRenderer(this.canvasEl);
    this.display.canvas.attachDom();
    this.display.renderVolume(payload.data, payload.shape);
    this.volume = this.display;

    this.isoThresholdTab4Slider.set({ maximum: 100, minimum: 1, value: 1, enabled: true });

    this.resize();
    this.display.canvas.show(this.visible());
    this.display.canvas.update();
  }

  visible() {
    return this.active && this.root.classList.contains("is-current");
  }

  resize() {
    if (!this.display) return;
    const width  = this.cell.clientWidth;
    const height = this.cell.clientHeight;
    if (width === 0 || height === 0) return;
    this.display.canvas.setSize([width, height]);
  }

  pageShown(active) {
    if (!active && this.display) this.display.canvas.show(false);
  }

  activate() {
    this.active = true;
    if (this.display) {
      this.resize();
      this.display.canvas.show(true);
      this.display.canvas.update();
    }
  }

  deactivate() {
    this.active = false;
    if (this.display) this.display.canvas.show(false);
    this.log.flush();
  }

  resetCamerasTab4ButtonClicked() {
    if (this.volume === null) return;

    this.volume.flyCamera.setRange();
    this.volume.turntableCamera.setRange();
    this.volume.arcballCamera.setRange();

    if (this.volume.volumeCenter !== null) {
      const center = this.volume.volumeCenter;
      this.volume.turntableCamera.center = center;
      this.volume.arcballCamera.center   = center;
    }

    this.volume.view.camera = this.volume.turntableCamera;
    this.turntableCameraTab4Button.set({ checked: true });

    this.volume.updateAxisView();
    this.volume.canvas.update();

    this.print("Cameras reset");
  }

  cameraTab4RadioButtonClicked() {
    if (this.volume === null) return;

    if (this.flyCameraTab4Button.checked) {
      this.volume.view.camera = this.volume.flyCamera;
      this.print("Camera: fly");
    } else if (this.arcballCameraTab4Button.checked) {
      this.volume.view.camera = this.volume.arcballCamera;
      this.print("Camera: arcball");
    } else if (this.turntableCameraTab4Button.checked) {
      this.volume.view.camera = this.volume.turntableCamera;
      this.print("Camera: turntable");
    }

    this.volume.updateAxisView();
    this.volume.canvas.update();
    this.print("center turntable");
    const center = this.volume.turntableCamera.center;
    this.print(VispyPyFormat.sequence(center.value, center.kind));
  }

  cameraTab4ButtonClicked() {
    if (this.volume === null) return;

    const camToggle = new Map([[this.volume.turntableCamera, this.volume.arcballCamera], [this.volume.arcballCamera, this.volume.flyCamera], [this.volume.flyCamera, this.volume.turntableCamera]]);
    this.volume.view.camera = camToggle.get(this.volume.view.camera) || this.volume.turntableCamera;
    this.print(`${this.volume.view.camera.name} camera`);
    this.print("center turntable");
    const center = this.volume.turntableCamera.center;
    this.print(VispyPyFormat.sequence(center.value, center.kind));
  }

  renderingMethodTab4ButtonClicked() {
    if (this.volume === null) return;

    const methods = ["mip", "translucent", "iso", "additive"];
    let method    = null;
    for (let i = 0; i < this.volume.nChannels; i += 1) {
      method = methods[(methods.indexOf(this.volume.volumeVisual[i].method) + 1) % 4];
      const cmap = ["mip", "iso"].includes(method) ? this.volume.opaqueCmap : this.volume.translucentCmap;
      this.volume.volumeVisual[i].method = method;
      this.volume.volumeVisual[i].cmap   = cmap;
    }
    this.volume.canvas.update();
    this.print(`Volume render method: ${method}`);
  }

  colormapTab4ButtonClicked() {
    if (this.volume === null) return;

    let cmap;
    if (["mip", "iso"].includes(this.volume.volumeVisual[0].method)) {
      cmap = this.volume.opaqueCmap = this.volume.opaqueCmaps.next();
    } else {
      cmap = this.volume.translucentCmap = this.volume.translucentCmaps.next();
    }
    for (let i = 0; i < this.volume.nChannels; i += 1) this.volume.volumeVisual[i].cmap = cmap;
    this.volume.canvas.update();
    this.print(`Colormap: ${typeof cmap === "string" ? cmap : cmap.repr()}`);
  }

  channelTab4ButtonClicked() {
    if (this.volume === null) return;

    const iterator = this.volume.volumeVisualVisibleIterator;
    this.volume.volumeVisualVisibleIterator = [iterator[iterator.length - 1], ...iterator.slice(0, -1)];
    for (let i = 0; i < this.volume.nChannels; i += 1) this.volume.volumeVisual[i].visible = this.volume.volumeVisualVisibleIterator[i];
    const activeChannel = this.volume.volumeVisualVisibleIterator.indexOf(true);
    this.volume.canvas.update();
    this.print(`Selected channel: ${activeChannel}`);
  }

  projectionTab4RadioButtonClicked(sender) {
    if (this.volume === null) return;

    const method = sender.projection;
    for (let i = 0; i < this.volume.nChannels; i += 1) {
      const cmap = ["mip", "iso"].includes(method) ? this.volume.opaqueCmap : this.volume.translucentCmap;
      this.volume.volumeVisual[i].method = method;
      this.volume.volumeVisual[i].cmap   = cmap;
    }
    this.volume.canvas.update();
    this.print(`Projection method: ${method}`);
  }

  isoThresholdTab4SliderMoved() {
    if (this.volume === null) return;

    let th = null;
    for (let i = 0; i < this.volume.nChannels; i += 1) {
      const sign = Math.sign(this.volume.isoThresholdInit);
      this.volume.volumeVisual[i].threshold = sign * this.isoThresholdTab4Slider.value * this.volume.isoThresholdInit;
      th = this.volume.volumeVisual[i].threshold;
    }
    this.volume.canvas.update();
    this.print(`Isosurface threshold: ${VispyPyFormat.fixed(th, 3)}`);
  }
}

window.TomoVisVolumeLog = TomoVisVolumeLog;
window.TomoVisVolume    = TomoVisVolume;
window.TomoVisVolumeTab = TomoVisVolumeTab;
