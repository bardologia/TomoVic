"use strict";

class GlobeClipRecorder {
  static CODECS   = ["video/webm;codecs=vp9", "video/webm;codecs=vp8"];
  static BITRATE  = 12e6;
  static CHUNK_MS = 250;

  constructor() {
    this.recorder = null;
    this.track    = null;
    this.chunks   = [];
  }

  static codec() {
    if (!window.MediaRecorder) return "";
    return GlobeClipRecorder.CODECS.find((mime) => MediaRecorder.isTypeSupported(mime)) || "";
  }

  _start(canvas) {
    const codec = GlobeClipRecorder.codec();
    if (!codec) throw new Error("this browser cannot record WebM video");

    const stream = canvas.captureStream(0);

    this.chunks   = [];
    this.track    = stream.getVideoTracks()[0];
    this.recorder = new MediaRecorder(stream, { mimeType: codec, videoBitsPerSecond: GlobeClipRecorder.BITRATE });

    this.recorder.addEventListener("dataavailable", (ev) => { if (ev.data.size) this.chunks.push(ev.data); });
    this.recorder.start(GlobeClipRecorder.CHUNK_MS);
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
    this._start(viewer.canvas);
    const release = viewer.scene.postRender.addEventListener(() => this._grab());

    await play();
    release();

    const clip = await this._stop();
    return await this._upload(clip, cubeId, move);
  }
}


class GlobeTour {
  static MOVES = {
    orbit:   { label: "orbit",         seconds: 18, spin: [0.0,  1.00], pitch: [-32, -32], zoom: [1.00, 1.00], slide: [ 0.0, 0.0], ease: false },
    spiral:  { label: "spiral in",     seconds: 20, spin: [0.0,  1.00], pitch: [-20, -45], zoom: [2.00, 0.70], slide: [ 0.0, 0.0], ease: true  },
    closein: { label: "zoom in",       seconds: 12, spin: [0.0,  0.10], pitch: [-22, -42], zoom: [2.40, 0.50], slide: [ 0.0, 0.0], ease: true  },
    pullout: { label: "zoom out",      seconds: 12, spin: [0.0, -0.10], pitch: [-42, -22], zoom: [0.50, 2.40], slide: [ 0.0, 0.0], ease: true  },
    along:   { label: "along track",   seconds: 16, spin: [0.0,  0.00], pitch: [-24, -24], zoom: [0.90, 0.90], slide: [-0.9, 0.9], ease: true  },
    nadir:   { label: "tilt to nadir", seconds: 12, spin: [0.0,  0.15], pitch: [ -6, -88], zoom: [1.40, 1.00], slide: [ 0.0, 0.0], ease: true  },
  };

  static MIN_SECONDS = 3;
  static MAX_SECONDS = 60;

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

    this.moveEl.innerHTML = this._options();
    this.moveEl.value     = Object.keys(GlobeTour.MOVES)[0];

    this.moveEl.addEventListener("change", () => this._onMove());
    this.playEl.addEventListener("click", () => this._onPlay());
    this.recordEl.addEventListener("click", () => this.record());

    this.secsEl.value = this._move().seconds;
    if (!GlobeClipRecorder.codec()) this.recordEl.title = "this browser cannot record WebM video";
    this._setBusy(false);
  }

  _options() {
    return Object.entries(GlobeTour.MOVES)
      .map(([key, move]) => `<option value="${SharedCharts.esc(key)}">${SharedCharts.esc(move.label)}</option>`)
      .join("");
  }

  _move() {
    return GlobeTour.MOVES[this.moveEl.value];
  }

  _onMove() {
    this.stop();
    this.secsEl.value = this._move().seconds;
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
    if (!Number.isFinite(asked) || !asked) return this._move().seconds;
    return Math.min(GlobeTour.MAX_SECONDS, Math.max(GlobeTour.MIN_SECONDS, asked));
  }

  _begin() {
    const viewer = this.globe.viewer;
    const sphere = this.globe.sceneSphere();

    this.origin = {
      center : sphere.center,
      radius : sphere.radius,
      range  : sphere.radius * TomogramGlobe.VIEW_RANGE_FACTOR,
      heading: viewer.camera.heading,
      axis   : this.globe.sceneFrame().azimuth,
    };

    this.renderMode = viewer.scene.requestRenderMode;
    viewer.scene.requestRenderMode = false;
  }

  static span(ends, t) {
    return ends[0] + (ends[1] - ends[0]) * t;
  }

  _pose(move, t) {
    const origin = this.origin;
    const eased  = move.ease ? t * t * (3 - 2 * t) : t;
    const slide  = GlobeTour.span(move.slide, eased) * origin.radius;

    const center = new Cesium.Cartesian3(
      origin.center.x + origin.axis.x * slide,
      origin.center.y + origin.axis.y * slide,
      origin.center.z + origin.axis.z * slide,
    );

    const heading = origin.heading + Cesium.Math.TWO_PI * GlobeTour.span(move.spin, eased);
    const pitch   = Cesium.Math.toRadians(GlobeTour.span(move.pitch, eased));
    const range   = origin.range * GlobeTour.span(move.zoom, eased);

    this.globe.viewer.camera.lookAt(center, new Cesium.HeadingPitchRange(heading, pitch, range));
  }

  _step(now) {
    if (this.globe.host.view !== "globe" || !this.origin) {
      this.stop();
      return;
    }

    if (this.t0 === null) this.t0 = now;
    const t = Math.min((now - this.t0) / (this._seconds() * 1000), 1);

    this._pose(this._move(), t);
    this.globe.viewer.scene.requestRender();

    if (t >= 1) {
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

    this.origin     = null;
    this.renderMode = null;
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

    Toast.show(`Saved ${result.file} (${(result.bytes / 1048576).toFixed(1)} MB) → ${result.rel}`, "ok");
  }
}
