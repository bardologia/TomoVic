"use strict";

class GlobeClipRecorder {
  static FPS            = 60;
  static FRAME_WIDTH    = 1920;
  static FRAME_HEIGHT   = 1080;
  static SCALE          = 2;
  static BITS_PER_PX    = 0.12;
  static MIN_BITRATE    = 12e6;
  static MAX_BITRATE    = 80e6;
  static KEYFRAME_EVERY = 120;
  static QUEUE_LIMIT    = 6;
  static SETTLE_MAX_MS  = 5000;
  static CODECS         = [
    { codec: "avc1.640034",    container: "avc", extra: { avc: { format: "avc" } } },
    { codec: "vp09.00.51.08", container: "vp9", extra: {} },
  ];

  constructor() {
    this.scale   = 1;
    this.frame   = "";
    this.failure = null;
    this.pinned  = "";
    this.stage   = document.createElement("canvas");
  }

  static available() {
    return Boolean(window.VideoEncoder && window.VideoFrame && window.Mp4Muxer);
  }

  _pin(container) {
    this.pinned = container.style.cssText;
    container.style.flex   = "none";
    container.style.width  = `${GlobeClipRecorder.FRAME_WIDTH}px`;
    container.style.height = `${GlobeClipRecorder.FRAME_HEIGHT}px`;
  }

  _scaleUp(viewer) {
    this.scale = viewer.resolutionScale;
    viewer.resolutionScale = GlobeClipRecorder.SCALE;
  }

  _unpin(container) {
    container.style.cssText = this.pinned;
  }

  _stageSize(canvas) {
    this.stage.width  = canvas.width & ~1;
    this.stage.height = canvas.height & ~1;
    this.frame        = `${this.stage.width}x${this.stage.height}`;
  }

  static _bitrate(width, height) {
    const rate = width * height * GlobeClipRecorder.FPS * GlobeClipRecorder.BITS_PER_PX;
    return Math.round(Math.min(GlobeClipRecorder.MAX_BITRATE, Math.max(GlobeClipRecorder.MIN_BITRATE, rate)));
  }

  async _pickCodec(width, height) {
    for (const entry of GlobeClipRecorder.CODECS) {
      const config = { codec: entry.codec, width, height, bitrate: GlobeClipRecorder._bitrate(width, height), framerate: GlobeClipRecorder.FPS, latencyMode: "quality", ...entry.extra };
      const probe  = await VideoEncoder.isConfigSupported(config);
      if (probe.supported) return { config, container: entry.container };
    }
    throw new Error("this browser has neither an H.264 nor a VP9 encoder for offline rendering");
  }

  async _settled(viewer) {
    const t0 = performance.now();
    while (true) {
      viewer.render();
      if (!viewer.scene.globe || viewer.scene.globe.tilesLoaded || performance.now() - t0 > GlobeClipRecorder.SETTLE_MAX_MS) return;
      await new Promise((resolve) => requestAnimationFrame(resolve));
    }
  }

  _grab(viewer, index) {
    const size = `${viewer.canvas.width & ~1}x${viewer.canvas.height & ~1}`;
    if (size !== this.frame) throw new Error(`the globe canvas changed size while rendering (${this.frame} to ${size})`);

    const ctx = this.stage.getContext("2d");
    ctx.drawImage(viewer.canvas, 0, 0, this.stage.width, this.stage.height, 0, 0, this.stage.width, this.stage.height);

    const tick = 1e6 / GlobeClipRecorder.FPS;
    return new VideoFrame(this.stage, { timestamp: Math.round(index * tick), duration: Math.round(tick) });
  }

  async _drain(encoder) {
    while (encoder.encodeQueueSize > GlobeClipRecorder.QUEUE_LIMIT) {
      await new Promise((resolve) => encoder.addEventListener("dequeue", resolve, { once: true }));
    }
    if (this.failure) throw this.failure;
  }

  async _upload(clip, cubeId, move) {
    if (!clip.size) return { ok: false, error: "the renderer produced no frames" };
    return await Api.postBlob(`/api/cubes/save_globe_tour?id=${encodeURIComponent(cubeId)}&move=${encodeURIComponent(move)}`, clip);
  }

  async render(viewer, tour, cubeId, move, onProgress) {
    if (!GlobeClipRecorder.available()) throw new Error("this browser cannot encode video offline (WebCodecs is missing)");

    this.failure = null;
    this._pin(viewer.container);
    this._scaleUp(viewer);

    let frames = 0;
    let config, muxer, encoder;
    try {
      viewer.render();
      this._stageSize(viewer.canvas);

      const picked = await this._pickCodec(this.stage.width, this.stage.height);
      config  = picked.config;
      muxer   = new Mp4Muxer.Muxer({ target: new Mp4Muxer.ArrayBufferTarget(), video: { codec: picked.container, width: this.stage.width, height: this.stage.height, frameRate: GlobeClipRecorder.FPS }, fastStart: "in-memory" });
      encoder = new VideoEncoder({ output: (chunk, meta) => muxer.addVideoChunk(chunk, meta), error: (err) => { this.failure = err; } });
      encoder.configure(config);

      tour.beginOffline();
      frames = tour.frameCount(GlobeClipRecorder.FPS);
      for (let i = 0; i < frames; i += 1) {
        tour.seek((i * 1000) / GlobeClipRecorder.FPS);
        await this._settled(viewer);

        const frame = this._grab(viewer, i);
        encoder.encode(frame, { keyFrame: i % GlobeClipRecorder.KEYFRAME_EVERY === 0 });
        frame.close();

        await this._drain(encoder);
        onProgress(i + 1, frames);
      }
      await encoder.flush();
    } finally {
      tour.endOffline();
      if (encoder && encoder.state !== "closed") encoder.close();
      viewer.resolutionScale = this.scale;
      this._unpin(viewer.container);
    }

    muxer.finalize();
    const clip   = new Blob([muxer.target.buffer], { type: "video/mp4" });
    const result = await this._upload(clip, cubeId, move);
    return { ...result, frame: this.frame, frames, codec: config.codec };
  }
}


class GlobeTourPlan {
  constructor(steps, seconds) {
    const base  = steps.reduce((total, step) => total + step.lead + step.seconds, 0);
    const scale = (seconds * 1000) / base;

    this.steps    = steps;
    this.segments = [];

    let start = 0;
    steps.forEach((step, index) => {
      if (step.lead > 0) {
        this.segments.push({ lead: true, step, index, start, span: step.lead * scale });
        start += step.lead * scale;
      }

      step.span = step.seconds * scale;
      this.segments.push({ lead: false, step, index, start, span: step.span });
      start += step.span;
    });

    this.total = start;
  }

  segmentAt(ms) {
    for (let i = this.segments.length - 1; i > 0; i -= 1) {
      if (ms >= this.segments[i].start) return this.segments[i];
    }
    return this.segments[0];
  }
}


class GlobeTour {
  static MOVES = {
    orbit:   { label: "orbit",         seconds: 18, spin: [0,  360], pitch: [-32, -32], zoom: [1.00, 1.00], slide: [ 0.0, 0.0], ease: false },
    spiral:  { label: "spiral in",     seconds: 20, spin: [0,  360], pitch: [-20, -45], zoom: [2.00, 0.70], slide: [ 0.0, 0.0], ease: true  },
    closein: { label: "zoom in",       seconds: 12, spin: [0,   36], pitch: [-22, -42], zoom: [2.40, 0.50], slide: [ 0.0, 0.0], ease: true  },
    pullout: { label: "zoom out",      seconds: 12, spin: [0,  -36], pitch: [-42, -22], zoom: [0.50, 2.40], slide: [ 0.0, 0.0], ease: true  },
    along:   { label: "along track",   seconds: 16, spin: [0,    0], pitch: [-24, -24], zoom: [0.90, 0.90], slide: [-0.9, 0.9], ease: true  },
    nadir:   { label: "tilt to nadir", seconds: 12, spin: [0,   54], pitch: [ -6, -88], zoom: [1.40, 1.00], slide: [ 0.0, 0.0], ease: true  },
  };

  static SEQUENCES = {
    walkthrough: {
      label  : "cut walkthrough",
      seconds: 55,
      steps  : [
        { lead: 2.5, seconds:  9, face: "azimuth", spin: [ 0,   8], pitch: [-88, -88], zoom: [1.20, 1.05], cut: "height",  sweep: [0, 1] },
        { lead: 3.5, seconds: 10, face: "range",   spin: [180, 170], pitch: [-14, -22], zoom: [1.10, 0.90], cut: "range",   sweep: [0, 1] },
        { lead: 3.5, seconds: 11, face: "range",   spin: [ 35,  35], pitch: [-20, -20], zoom: [0.80, 0.80], cut: "azimuth", sweep: [0, 1], follow: true },
        { lead: 3.5, seconds: 12, face: "azimuth", spin: [ 0, 270], pitch: [-46, -24], zoom: [1.70, 1.00], cut: "off", tracks: true, fly: true, ease: false },
      ],
    },
  };

  static MIN_SECONDS = 3;
  static MAX_SECONDS = 120;

  constructor(refs, globe) {
    this.globe    = globe;
    this.moveEl   = refs.move;
    this.secsEl   = refs.secs;
    this.playEl   = refs.play;
    this.recordEl = refs.record;

    this.recorder   = new GlobeClipRecorder();
    this.busy       = false;
    this.frame      = null;
    this.t0         = null;
    this.origin     = null;
    this.settle     = null;
    this.renderMode = null;
    this.plan       = null;
    this.cursor     = null;
    this.from       = null;
    this.center     = null;

    this.moveEl.innerHTML = this._options();
    this.moveEl.value     = Object.keys(GlobeTour.MOVES)[0];

    this.moveEl.addEventListener("change", () => this._onMove());
    this.playEl.addEventListener("click", () => this._onPlay());
    this.recordEl.addEventListener("click", () => this.record());

    this.secsEl.value = this._entry().seconds;
    if (!GlobeClipRecorder.available()) this.recordEl.title = "this browser cannot encode video offline (WebCodecs is missing)";
    this._setBusy(false);
  }

  static group(label, table) {
    const options = Object.entries(table)
      .map(([key, entry]) => `<option value="${SharedCharts.esc(key)}">${SharedCharts.esc(entry.label)}</option>`)
      .join("");

    return `<optgroup label="${label}">${options}</optgroup>`;
  }

  _options() {
    return GlobeTour.group("moves", GlobeTour.MOVES) + GlobeTour.group("sequences", GlobeTour.SEQUENCES);
  }

  _entry() {
    return GlobeTour.MOVES[this.moveEl.value] || GlobeTour.SEQUENCES[this.moveEl.value];
  }

  static filled(step) {
    return {
      lead   : step.lead || 0,
      seconds: step.seconds,
      face   : step.face || "",
      spin   : step.spin || [0, 0],
      pitch  : step.pitch,
      zoom   : step.zoom,
      slide  : step.slide || [0, 0],
      follow : !!step.follow,
      cut    : step.cut === undefined ? null : step.cut,
      sweep  : step.sweep || null,
      tracks : !!step.tracks,
      fly    : !!step.fly,
      ease   : step.ease === undefined ? true : step.ease,
      span   : 0,
    };
  }

  _steps() {
    const entry = this._entry();
    return (entry.steps || [entry]).map((step) => GlobeTour.filled(step));
  }

  _onMove() {
    this.stop();
    this.secsEl.value = this._entry().seconds;
  }

  _setBusy(on) {
    const blocked = on || !this.globe.available;

    this.busy = on;

    this.moveEl.disabled   = blocked;
    this.secsEl.disabled   = blocked;
    this.playEl.disabled   = blocked;
    this.recordEl.disabled = blocked || !GlobeClipRecorder.available();
  }

  sync() {
    this.stop();
    this._setBusy(false);
  }

  _seconds() {
    const asked = Number(this.secsEl.value);
    if (!Number.isFinite(asked) || !asked) return this._entry().seconds;
    return Math.min(GlobeTour.MAX_SECONDS, Math.max(GlobeTour.MIN_SECONDS, asked));
  }

  static bearing(axis, frame) {
    return Math.atan2(Cesium.Cartesian3.dot(axis, frame.east), Cesium.Cartesian3.dot(axis, frame.north));
  }

  _begin() {
    const viewer = this.globe.viewer;
    const sphere = this.globe.sceneSphere();
    const frame  = this.globe.sceneFrame();

    this.origin = {
      center  : sphere.center,
      radius  : sphere.radius,
      range   : sphere.radius * TomogramGlobe.VIEW_RANGE_FACTOR,
      heading : viewer.camera.heading,
      axis    : frame.azimuth,
      bearings: { azimuth: GlobeTour.bearing(frame.azimuth, frame), range: GlobeTour.bearing(frame.range, frame) },
    };

    this.center = sphere.center;
    this.plan   = new GlobeTourPlan(this._steps(), this._seconds());
    this.cursor = null;

    this.renderMode = viewer.scene.requestRenderMode;
    viewer.scene.requestRenderMode = false;
  }

  _currentPose() {
    const camera = this.globe.viewer.camera;
    const center = this.center;

    return { heading: camera.heading, pitch: camera.pitch, range: Cesium.Cartesian3.distance(camera.positionWC, center), center };
  }

  static opening(step) {
    return { cut: step.cut, tracks: false, fly: false, span: 0 };
  }

  _stage(step) {
    const globe = this.globe;

    globe.cutSweepEl.checked = false;
    globe._stopSweep();

    if (globe.cutAxisEl.value !== step.cut) {
      globe.cutAxisEl.value = step.cut;
      globe._rebuildCut();
    }

    globe.tracksEl.checked = step.tracks && !globe.tracksEl.disabled;
    globe.flyEl.checked    = step.fly && !globe.flyEl.disabled;
    globe.flightPeriod     = step.span || TomogramGlobe.FLIGHT_PERIOD_MS;
    globe._redrawTracks();
    globe._syncStatus();
  }

  _enter(segment) {
    this.cursor = segment;
    this.from   = this._currentPose();

    if (segment.step.cut === null) return;
    this._stage(segment.lead ? GlobeTour.opening(segment.step) : segment.step);
  }

  static span(ends, t) {
    return ends[0] + (ends[1] - ends[0]) * t;
  }

  static smooth(t) {
    return t * t * (3 - 2 * t);
  }

  static wrap(angle) {
    const turn = Math.PI * 2;
    return angle - turn * Math.round(angle / turn);
  }

  static blend(from, to, t) {
    return {
      heading: from.heading + GlobeTour.wrap(to.heading - from.heading) * t,
      pitch  : from.pitch + (to.pitch - from.pitch) * t,
      range  : from.range + (to.range - from.range) * t,
      center : new Cesium.Cartesian3(
        from.center.x + (to.center.x - from.center.x) * t,
        from.center.y + (to.center.y - from.center.y) * t,
        from.center.z + (to.center.z - from.center.z) * t,
      ),
    };
  }

  _reference(step) {
    return step.face ? this.origin.bearings[step.face] : this.origin.heading;
  }

  _cutOffset(step, eased) {
    const range = this.globe.cutRange;
    if (!range || !step.sweep) return 0;

    const mid = (range[0] + range[1]) / 2;
    return range[0] + GlobeTour.span(step.sweep, eased) * (range[1] - range[0]) - mid;
  }

  _poseFor(step, eased) {
    const origin = this.origin;
    const axis   = step.follow && this.globe.cutDir ? this.globe.cutDir : origin.axis;
    const along  = step.follow ? this._cutOffset(step, eased) : GlobeTour.span(step.slide, eased) * origin.radius;

    return {
      heading: this._reference(step) + Cesium.Math.toRadians(GlobeTour.span(step.spin, eased)),
      pitch  : Cesium.Math.toRadians(GlobeTour.span(step.pitch, eased)),
      range  : origin.range * GlobeTour.span(step.zoom, eased),
      center : new Cesium.Cartesian3(origin.center.x + axis.x * along, origin.center.y + axis.y * along, origin.center.z + axis.z * along),
    };
  }

  _applyPose(pose) {
    this.center = pose.center;
    this.globe.viewer.camera.lookAt(pose.center, new Cesium.HeadingPitchRange(pose.heading, pose.pitch, pose.range));
  }

  _cutTo(fraction) {
    if (!this.globe.cutOrder) return;

    this.globe.cutPosEl.value = String(Math.round(fraction * 100));
    this.globe._applyCut();
    this.globe._syncStatus();
  }

  _advance(elapsed) {
    const segment = this.plan.segmentAt(elapsed);
    if (segment !== this.cursor) this._enter(segment);

    const step  = segment.step;
    const u     = Math.min((elapsed - segment.start) / segment.span, 1);
    const eased = segment.lead ? 0 : (step.ease ? GlobeTour.smooth(u) : u);

    this._applyPose(segment.lead ? GlobeTour.blend(this.from, this._poseFor(step, 0), GlobeTour.smooth(u)) : this._poseFor(step, eased));
    if (step.sweep) this._cutTo(segment.lead ? GlobeTour.span([1, step.sweep[0]], GlobeTour.smooth(u)) : GlobeTour.span(step.sweep, eased));
    if (this.globe.offline) this.globe.flightTick(elapsed);

    return elapsed >= this.plan.total;
  }

  _step(now) {
    if (this.globe.host.view !== "globe" || !this.origin) {
      this.stop();
      return;
    }

    if (this.t0 === null) this.t0 = now;

    const done = this._advance(now - this.t0);
    this.globe.viewer.scene.requestRender();

    if (done) {
      this.stop();
      return;
    }

    this.frame = requestAnimationFrame((next) => this._step(next));
  }

  frameCount(fps) {
    return Math.ceil((this.plan.total / 1000) * fps) + 1;
  }

  beginOffline() {
    this.stop();
    this._begin();
    this.globe.offline = true;
    this.globe.viewer.scene.requestRenderMode = true;
  }

  seek(elapsed) {
    if (this.globe.host.view !== "globe" || !this.origin) throw new Error("the globe view was left while rendering");
    this._advance(Math.min(elapsed, this.plan.total));
  }

  endOffline() {
    this.globe.offline = false;
    this.stop();
  }

  _end() {
    const viewer = this.globe.viewer;

    viewer.camera.lookAtTransform(Cesium.Matrix4.IDENTITY);
    viewer.scene.requestRenderMode = this.renderMode;
    viewer.scene.requestRender();

    this.globe.flightPeriod = TomogramGlobe.FLIGHT_PERIOD_MS;
    this.origin     = null;
    this.renderMode = null;
    this.plan       = null;
    this.cursor     = null;
  }

  stop() {
    if (this.frame !== null) cancelAnimationFrame(this.frame);
    this.frame = null;
    this.t0    = null;

    if (this.origin) this._end();

    const settle = this.settle;
    this.settle  = null;
    if (settle) settle();
  }

  play() {
    if (!this.globe.viewer || !this.globe.available) return Promise.resolve();

    this.stop();
    this._begin();

    return new Promise((resolve) => {
      this.settle = resolve;
      this.frame  = requestAnimationFrame((now) => this._step(now));
    });
  }

  async _onPlay() {
    if (this.busy) return;

    this._setBusy(true);
    await this.play();
    this._setBusy(false);
  }

  async record() {
    if (this.busy || !this.globe.viewer || !this.globe.available) return;

    const move = this.moveEl.value;

    this._setBusy(true);
    this.recordEl.classList.add("is-recording");
    this.recordEl.innerHTML = ThinkingOrb.busy("composing", "Rendering 0%");

    const onProgress = (done, total) => { this.recordEl.innerHTML = ThinkingOrb.busy("composing", `Rendering ${Math.round((100 * done) / total)}%`); };

    let result;
    try {
      result = await this.recorder.render(this.globe.viewer, this, this.globe.host.selectedId, move, onProgress);
    } catch (e) {
      result = { ok: false, error: e.message };
    }

    this._setBusy(false);
    this.recordEl.classList.remove("is-recording");
    this.recordEl.textContent = "Record";

    if (!result.ok) {
      Toast.show(result.error || "The globe rendering could not be saved.", "error");
      return;
    }

    Toast.show(`Saved ${result.file} (${result.frame}, ${result.frames} frames at ${GlobeClipRecorder.FPS} fps, ${result.codec}, ${(result.bytes / 1048576).toFixed(1)} MB) → ${result.rel}`, "ok");
  }
}
