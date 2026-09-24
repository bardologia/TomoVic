"use strict";

class GlobeClipRecorder {
  static CODECS      = ["video/webm;codecs=vp9", "video/webm;codecs=vp8"];
  static SCALE       = 2;
  static MAX_WIDTH   = 3840;
  static FRAME_RATE  = 30;
  static BITS_PER_PX = 0.2;
  static MIN_BITRATE = 16e6;
  static MAX_BITRATE = 48e6;
  static CHUNK_MS    = 250;

  constructor() {
    this.recorder = null;
    this.track    = null;
    this.chunks   = [];
    this.scale    = 1;
    this.frame    = "";
  }

  static codec() {
    if (!window.MediaRecorder) return "";
    return GlobeClipRecorder.CODECS.find((mime) => MediaRecorder.isTypeSupported(mime)) || "";
  }

  _scaleUp(viewer) {
    const room = GlobeClipRecorder.MAX_WIDTH / Math.max(viewer.canvas.clientWidth, 1);

    this.scale = viewer.resolutionScale;
    viewer.resolutionScale = Math.max(1, Math.min(GlobeClipRecorder.SCALE, room));
  }

  _settle(viewer) {
    return new Promise((resolve) => {
      const release = viewer.scene.postRender.addEventListener(() => { release(); resolve(); });
      viewer.scene.requestRender();
    });
  }

  _start(canvas) {
    const stream = canvas.captureStream(0);

    this.chunks   = [];
    this.frame    = `${canvas.width}x${canvas.height}`;
    this.track    = stream.getVideoTracks()[0];
    this.recorder = new MediaRecorder(stream, { mimeType: GlobeClipRecorder.codec(), videoBitsPerSecond: GlobeClipRecorder._bitrate(canvas) });

    this.recorder.addEventListener("dataavailable", (ev) => { if (ev.data.size) this.chunks.push(ev.data); });
    this.recorder.start(GlobeClipRecorder.CHUNK_MS);
  }

  static _bitrate(canvas) {
    const rate = canvas.width * canvas.height * GlobeClipRecorder.FRAME_RATE * GlobeClipRecorder.BITS_PER_PX;
    return Math.round(Math.min(GlobeClipRecorder.MAX_BITRATE, Math.max(GlobeClipRecorder.MIN_BITRATE, rate)));
  }

  _grab() {
    this.track.requestFrame();
  }

  _stop() {
    const recorder = this.recorder;
    this.recorder  = null;
    this.track     = null;

    return new Promise((resolve) => {
      recorder.addEventListener("stop", () => resolve(new Blob(this.chunks, { type: recorder.mimeType })));
      recorder.stop();
    });
  }

  async _upload(clip, cubeId, move) {
    if (!clip.size) return { ok: false, error: "the recorder captured no frames" };
    return await Api.postBlob(`/api/cubes/save_globe_tour?id=${encodeURIComponent(cubeId)}&move=${encodeURIComponent(move)}`, clip);
  }

  async capture(viewer, cubeId, move, play) {
    if (!GlobeClipRecorder.codec()) throw new Error("this browser cannot record WebM video");

    this._scaleUp(viewer);
    await this._settle(viewer);

    this._start(viewer.canvas);
    const release = viewer.scene.postRender.addEventListener(() => this._grab());

    let clip;
    try {
      await play();
    } finally {
      release();
      clip = await this._stop();
      viewer.resolutionScale = this.scale;
    }

    const result = await this._upload(clip, cubeId, move);
    return { ...result, frame: this.frame };
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
        { lead: 3.5, seconds: 10, face: "range",   spin: [ 0,  10], pitch: [-14, -22], zoom: [1.10, 0.90], cut: "range",   sweep: [0, 1] },
        { lead: 3.5, seconds: 11, face: "range",   spin: [35,  35], pitch: [-20, -20], zoom: [0.80, 0.80], cut: "azimuth", sweep: [0, 1], follow: true },
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
    if (!GlobeClipRecorder.codec()) this.recordEl.title = "this browser cannot record WebM video";
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
    this.recordEl.disabled = blocked || !GlobeClipRecorder.codec();
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

  _step(now) {
    if (this.globe.host.view !== "globe" || !this.origin) {
      this.stop();
      return;
    }

    if (this.t0 === null) this.t0 = now;

    const elapsed = now - this.t0;
    const segment = this.plan.segmentAt(elapsed);
    if (segment !== this.cursor) this._enter(segment);

    const step  = segment.step;
    const u     = Math.min((elapsed - segment.start) / segment.span, 1);
    const eased = segment.lead ? 0 : (step.ease ? GlobeTour.smooth(u) : u);

    this._applyPose(segment.lead ? GlobeTour.blend(this.from, this._poseFor(step, 0), GlobeTour.smooth(u)) : this._poseFor(step, eased));
    if (step.sweep) this._cutTo(segment.lead ? GlobeTour.span([1, step.sweep[0]], GlobeTour.smooth(u)) : GlobeTour.span(step.sweep, eased));
    this.globe.viewer.scene.requestRender();

    if (elapsed >= this.plan.total) {
      this.stop();
      return;
    }

    this.frame = requestAnimationFrame((next) => this._step(next));
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
    this.recordEl.textContent = "Recording";

    let result;
    try {
      result = await this.recorder.capture(this.globe.viewer, this.globe.host.selectedId, move, () => this.play());
    } catch (e) {
      result = { ok: false, error: e.message };
    }

    this._setBusy(false);
    this.recordEl.classList.remove("is-recording");
    this.recordEl.textContent = "Record";

    if (!result.ok) {
      Toast.show(result.error || "The globe recording could not be saved.", "error");
      return;
    }

    Toast.show(`Saved ${result.file} (${result.frame}, ${(result.bytes / 1048576).toFixed(1)} MB) → ${result.rel}`, "ok");
  }
}
