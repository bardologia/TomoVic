"use strict";

class TomogramSweep {
  static BASE_FRAME_MS = 70;

  constructor(refs, host) {
    this.host = host;
    this.axis = refs.axis;
    this.grid = refs.grid;
    this.atLabel = refs.at;
    this.fill = refs.fill;
    this.input = refs.input;
    this.rangeLabel = refs.range;
    this.playBtn = refs.play;
    this.speedEl = document.getElementById(`cube-${this.axis}-speed`);
    this.panels = refs.panels || [];

    this.idx = 0;
    this.steps = 1;
    this.playing = false;
    this.token = 0;

    if (this.grid)    this.grid.addEventListener("wheel", (ev) => this._onWheel(ev), { passive: false });
    if (this.input)   this.input.addEventListener("change", () => this._onManual());
    if (this.playBtn) this.playBtn.addEventListener("click", () => this.toggle());
    if (this.speedEl) {
      this.speedEl.value = String(host.sweepSpeed);
      this.speedEl.addEventListener("change", () => this.host._setSweepSpeed(Number(this.speedEl.value)));
    }
  }

  syncSpeed() {
    if (this.speedEl) this.speedEl.value = String(this.host.sweepSpeed);
  }

  configure() {
    const meta = this.host.meta;
    this.steps = this._axisSteps(meta);
    this.idx   = Math.floor((this.steps - 1) / 2);

    if (this.input) {
      this.input.min = 1;
      this.input.max = this.steps;
      this.input.value = this.idx + 1;
    }
    if (this.rangeLabel) this.rangeLabel.textContent = this._rangeText(meta);

    this.panels.forEach((panel) => {
      panel.root.hidden = !meta.sources.includes(panel.source) || !this.host.visible.has(panel.source);
      panel.bitmap = null;
    });

    this._syncRows();
    this.stop();
  }

  holds(bitmap) {
    return this.panels.some((panel) => panel.bitmap === bitmap);
  }

  applyVisibility() {
    this.panels.forEach((panel) => {
      panel.root.hidden = !this.host.visible.has(panel.source);
    });

    this._syncRows();
    if (this.host.meta && !this.playing && this.host.view === this.axis) this._renderFrame();
  }

  _syncRows() {
    if (!this.grid) return;
    const shown = this.panels.filter((panel) => !panel.root.hidden).length;
    this.grid.style.setProperty("--cube-rows", String(Math.max(1, shown)));
  }

  syncSpace() {
    if (this.host.meta && !this.playing) this._renderFrame();
  }

  render() {
    if (this.host.meta) this._renderFrame();
  }

  play() {
    if (!this.host.meta || this.playing) return;
    if (this.steps < 2) { this._renderFrame(); return; }
    this.playing = true;
    this._syncPlayBtn();
    this._loop();
  }

  stop() {
    this.playing = false;
    this._syncPlayBtn();
  }

  toggle() {
    if (this.playing) this.stop();
    else this.play();
  }

  async _loop() {
    while (this.playing && this.host.meta && this.host.selectedId) {
      const frame = this._renderFrame();
      const next  = (this.idx + 1) % this.steps;

      this._prefetch(next);
      await Promise.all([frame, this._sleep(TomogramSweep.BASE_FRAME_MS / this.host.sweepSpeed)]);
      if (!this.playing) break;

      this.idx = next;
    }
  }

  _prefetch(idx) {
    if (this.panels.some((panel) => !panel.root.hidden)) this.host.cacheBitmap(this._url(this.host.srcFor(), idx));
  }

  _onWheel(ev) {
    if (!this.host.meta) return;
    ev.preventDefault();
    this.stop();

    const step = ev.deltaY > 0 ? 1 : -1;
    const next = Math.min(this.steps - 1, Math.max(0, this.idx + step));
    if (next === this.idx) return;

    this.idx = next;
    this._renderFrame();
  }

  _onManual() {
    if (!this.host.meta || !this.input) return;
    this.stop();
    this.idx = this.host._clampInt(Number(this.input.value) - 1, this.steps);
    this._renderFrame();
  }

  _renderFrame() {
    if (!this.host.meta) return Promise.resolve();

    this.token += 1;
    const token = this.token;
    this._updateLabels();

    const jobs = this.panels.filter((panel) => !panel.root.hidden).map((panel) => this._fetch(panel, this.idx, token));
    return Promise.all(jobs);
  }

  _updateLabels() {
    const frac = this.steps > 1 ? this.idx / (this.steps - 1) : 0;

    if (this.fill) this.fill.style.width = `${frac * 100}%`;
    if (this.input && document.activeElement !== this.input) this.input.value = this.idx + 1;
    if (this.atLabel) this.atLabel.textContent = this._atText(frac);
  }

  async _fetch(panel, idx, token) {
    const url = this._url(this.host.srcFor(), idx);
    const skeletonTimer = panel.bitmap ? null : setTimeout(() => panel.root.classList.add("is-loading"), 120);

    try {
      const bitmap = await this.host.cacheBitmap(url);
      if (!bitmap || token !== this.token) return;

      panel.bitmap = bitmap;
      this._paint(panel);
    } finally {
      if (skeletonTimer) clearTimeout(skeletonTimer);
      panel.root.classList.remove("is-loading");
    }
  }

  _paint(panel) {
    const bitmap = panel.bitmap;
    const canvas = panel.canvas;

    if (canvas.width !== bitmap.width || canvas.height !== bitmap.height) {
      canvas.width = bitmap.width;
      canvas.height = bitmap.height;
    }

    canvas.getContext("2d").drawImage(bitmap, 0, 0);
  }

  _url(source, idx) {
    const id    = encodeURIComponent(this.host.selectedId);
    const space = this.host.space;

    const cmap = this.host.cmap;

    if (this.axis === "elevation") {
      const frac = this.steps > 1 ? idx / (this.steps - 1) : 0;
      return `/api/cubes/plane?id=${id}&source=${source}&frac=${frac}&space=${space}&cmap=${cmap}`;
    }
    if (this.axis === "azimuth") {
      return `/api/cubes/slice?id=${id}&source=${source}&axis=azimuth&az=${idx}&rg=0&space=${space}&cmap=${cmap}`;
    }
    return `/api/cubes/slice?id=${id}&source=${source}&axis=range&az=0&rg=${idx}&space=${space}&cmap=${cmap}`;
  }

  _axisSteps(meta) {
    if (this.axis === "elevation") {
      return Math.max(1, meta.n_elev[meta.sources[0]] || 1);
    }
    if (this.axis === "azimuth") return Math.max(1, meta.n_az);
    return Math.max(1, meta.n_rg);
  }

  _rangeText(meta) {
    if (this.axis === "elevation") return `1–${this.steps} · ${this.host._fmt(meta.x_min)} … ${this.host._fmt(meta.x_max)}`;
    return `1–${this.steps} · index 0–${this.steps - 1}`;
  }

  _atText(frac) {
    if (this.axis === "elevation") {
      const height = this.host.meta.x_min + frac * (this.host.meta.x_max - this.host.meta.x_min);
      return `elevation ≈ ${this.host._fmt(height)} · bin ${this.idx + 1} / ${this.steps} · scroll or play to sweep`;
    }
    return `${this.axis} index ${this.idx} · bin ${this.idx + 1} / ${this.steps} · scroll or play to sweep`;
  }

  _syncPlayBtn() {
    if (!this.playBtn) return;
    this.playBtn.classList.toggle("is-playing", this.playing);
    this.playBtn.textContent = this.playing ? "Pause" : "Play";
  }

  _sleep(ms) {
    return new Promise((resolve) => setTimeout(resolve, ms));
  }
}

class TomogramTransect {
  constructor(refs, host) {
    this.host = host;
    this.atEl = refs.at;
    this.clearBtn = refs.clear;
    this.printBtn = refs.print;
    this.map = refs.map;
    this.overlay = refs.overlay;
    this.grid = refs.grid;
    this.panels = refs.panels || [];

    this.start = null;
    this.end = null;
    this.token = 0;
    this.saving = false;

    this.map.addEventListener("click", (ev) => this._onClick(ev));
    this.clearBtn.addEventListener("click", () => this._reset());
    this.printBtn.addEventListener("click", () => this._print());
  }

  configure() {
    this._reset();
    this.map.src = `/api/cubes/primary?id=${encodeURIComponent(this.host.selectedId)}`;
  }

  render() {
    this._applyVisibility();
    if (this.start && this.end) this._fetchAll();
  }

  syncSpace() {
    if (this.host.view === "transect" && this.start && this.end) this._fetchAll();
  }

  _applyVisibility() {
    const meta = this.host.meta;
    this.panels.forEach((panel) => {
      panel.root.hidden = !meta || !meta.sources.includes(panel.source) || !this.host.visible.has(panel.source);
    });
  }

  _reset() {
    this.start = null;
    this.end = null;
    this.overlay.innerHTML = "";
    this.grid.hidden = true;
    this.clearBtn.hidden = true;
    this.printBtn.hidden = true;
    this.atEl.textContent = "Click a start point on the map, then an end point, to cut every tomogram along that line.";
  }

  _pointFromEvent(ev) {
    const rect = this.map.getBoundingClientRect();
    const fx = Math.min(1, Math.max(0, (ev.clientX - rect.left) / rect.width));
    const fy = Math.min(1, Math.max(0, (ev.clientY - rect.top) / rect.height));
    return {
      az: Math.min(this.host.meta.n_az - 1, Math.floor(fy * this.host.meta.n_az)),
      rg: Math.min(this.host.meta.n_rg - 1, Math.floor(fx * this.host.meta.n_rg)),
      fx,
      fy,
    };
  }

  _onClick(ev) {
    if (!this.host.meta) return;
    const point = this._pointFromEvent(ev);

    if (!this.start || this.end) {
      this.start = point;
      this.end = null;
      this.grid.hidden = true;
      this.printBtn.hidden = true;
      this.clearBtn.hidden = false;
      this.atEl.textContent = `start az = ${point.az} · rg = ${point.rg} · click the end point`;
      this._drawOverlay();
      return;
    }

    if (point.az === this.start.az && point.rg === this.start.rg) return;

    this.end = point;
    this.printBtn.hidden = false;
    this.atEl.textContent = `transect az ${this.start.az},${this.start.rg} to az ${point.az},${point.rg}`;
    this._drawOverlay();
    this._fetchAll();
  }

  _drawOverlay() {
    let svg = "";
    if (this.start) {
      svg += `<circle cx="${this.start.fx * 100}" cy="${this.start.fy * 100}" r="0.8" class="cube-tdot" />`;
    }
    if (this.start && this.end) {
      svg += `<line x1="${this.start.fx * 100}" y1="${this.start.fy * 100}" x2="${this.end.fx * 100}" y2="${this.end.fy * 100}" class="cube-tline" />`;
      svg += `<circle cx="${this.end.fx * 100}" cy="${this.end.fy * 100}" r="0.8" class="cube-tdot" />`;
    }
    this.overlay.innerHTML = svg;
  }

  _fetchAll() {
    this.grid.hidden = false;
    this._applyVisibility();

    this.token += 1;
    const token = this.token;

    this.panels.forEach((panel) => {
      if (panel.root.hidden) return;
      this._fetch(panel, token);
    });
  }

  async _fetch(panel, token) {
    const url = `/api/cubes/transect?id=${encodeURIComponent(this.host.selectedId)}&source=${this.host.srcFor()}` +
      `&az0=${this.start.az}&rg0=${this.start.rg}&az1=${this.end.az}&rg1=${this.end.rg}&space=${this.host.space}&cmap=${this.host.cmap}`;

    const skeletonTimer = setTimeout(() => panel.root.classList.add("is-loading"), 120);
    try {
      const res = await fetch(url);
      if (!res.ok || token !== this.token) return;

      const bitmap = await createImageBitmap(await res.blob());
      if (token !== this.token) { if (bitmap.close) bitmap.close(); return; }

      const canvas = panel.canvas;
      if (canvas.width !== bitmap.width || canvas.height !== bitmap.height) {
        canvas.width = bitmap.width;
        canvas.height = bitmap.height;
      }
      canvas.getContext("2d").drawImage(bitmap, 0, 0);
    } catch (e) {
    } finally {
      clearTimeout(skeletonTimer);
      panel.root.classList.remove("is-loading");
    }
  }

  async _print() {
    if (!this.start || !this.end || this.saving) return;

    this.saving = true;
    this.printBtn.disabled = true;

    const res = await Api.post("/api/cubes/save_transect", {
      id: this.host.selectedId,
      az0: this.start.az,
      rg0: this.start.rg,
      az1: this.end.az,
      rg1: this.end.rg,
      space: this.host.space,
      cmap: this.host.cmap,
    });

    this.saving = false;
    this.printBtn.disabled = false;

    if (!res || !res.ok) {
      Toast.show((res && res.error) || "Transect figure save failed.", "error");
      return;
    }

    Toast.show(`Saved ${res.files.length} transect figures → ${res.rel}`, "ok");
  }
}

class TomogramLens {
  static SIZE = 180;

  constructor(media, container, host) {
    this.host = host;
    this.media = media;
    this.canvas = document.createElement("canvas");
    this.canvas.className = "cube-lens";
    this.canvas.width = TomogramLens.SIZE;
    this.canvas.height = TomogramLens.SIZE;
    this.canvas.hidden = true;
    container.appendChild(this.canvas);

    media.addEventListener("mousemove", (ev) => this._onMove(ev));
    media.addEventListener("mouseleave", () => { this.canvas.hidden = true; });
  }

  _sourceSize() {
    if (this.media.naturalWidth !== undefined) return { w: this.media.naturalWidth, h: this.media.naturalHeight };
    return { w: this.media.width, h: this.media.height };
  }

  _onMove(ev) {
    const zoom = this.host.lensZoom;
    const { w, h } = this._sourceSize();
    if (!zoom || !w || !h) { this.canvas.hidden = true; return; }

    const rect = this.media.getBoundingClientRect();
    const fx = Math.min(1, Math.max(0, (ev.clientX - rect.left) / rect.width));
    const fy = Math.min(1, Math.max(0, (ev.clientY - rect.top) / rect.height));

    const size = TomogramLens.SIZE;
    const sw = Math.min(w, (size / zoom) * (w / rect.width));
    const sh = Math.min(h, (size / zoom) * (h / rect.height));
    const sx = Math.min(w - sw, Math.max(0, fx * w - sw / 2));
    const sy = Math.min(h - sh, Math.max(0, fy * h - sh / 2));

    const ctx = this.canvas.getContext("2d");
    ctx.imageSmoothingEnabled = false;
    ctx.clearRect(0, 0, size, size);
    ctx.drawImage(this.media, sx, sy, sw, sh, 0, 0, size, size);

    this.canvas.style.left = `${ev.clientX - rect.left - size / 2}px`;
    this.canvas.style.top = `${ev.clientY - rect.top - size / 2}px`;
    this.canvas.hidden = false;
  }
}

class TomogramCloud {
  static VIRIDIS = [[68, 1, 84], [59, 82, 139], [33, 145, 140], [94, 201, 98], [253, 231, 37]];

  constructor(refs, host) {
    this.host = host;
    this.colorEl = refs.color;
    this.thrEl = refs.thr;
    this.thrValEl = refs.thrVal;
    this.maxEl = refs.max;
    this.demWrap = refs.demWrap;
    this.demEl = refs.dem;
    this.scaleWrap = refs.scaleWrap;
    this.scaleEl = refs.scale;
    this.atEl = refs.at;
    this.canvas = refs.canvas;

    this.source = "full";
    this.colorBy = "mu";
    this.points = null;
    this.total = 0;
    this.demGrid = null;
    this.debounceTimer = null;
    this.token = 0;

    this.yaw = 0.7;
    this.pitch = 0.9;
    this.zoom = 1.0;
    this.dragging = null;

    this.colorEl.querySelectorAll(".cube-space").forEach((btn) => {
      btn.addEventListener("click", () => this._setColor(btn.dataset.color));
    });
    this.scaleEl.checked = localStorage.getItem("cube-cloud-scale") === "1";

    this.thrEl.addEventListener("input", () => this._onThreshold());
    this.maxEl.addEventListener("change", () => this._fetch());
    this.demEl.addEventListener("change", () => this._onDem());
    this.scaleEl.addEventListener("change", () => this._onScale());

    this.canvas.addEventListener("mousedown", (ev) => { this.dragging = { x: ev.clientX, y: ev.clientY }; });
    window.addEventListener("mousemove", (ev) => this._onDrag(ev));
    window.addEventListener("mouseup", () => { this.dragging = null; });
    this.canvas.addEventListener("wheel", (ev) => this._onWheel(ev), { passive: false });
    this.canvas.addEventListener("dblclick", () => this._resetView());
  }

  configure(meta) {
    this.available = meta.sources.includes("full");
    this.source = this.host.srcFor();
    this.points = null;
    this.demGrid = null;
    this.demWrap.hidden = !meta.dem;
    this.demEl.checked = false;
    this.scaleWrap.hidden = !meta.spacing;
    this._resetView(false);
    this._syncThresholdLabel();
  }

  render() {
    this._syncBtns();
    if (!this.points) this._fetch();
    else this._draw();
  }

  _setColor(colorBy) {
    if (colorBy === this.colorBy) return;
    this.colorBy = colorBy;
    this._syncBtns();
    this._draw();
  }

  _onThreshold() {
    this._syncThresholdLabel();
    clearTimeout(this.debounceTimer);
    this.debounceTimer = setTimeout(() => this._fetch(), 250);
  }

  async _onDem() {
    if (this.demEl.checked && !this.demGrid) {
      this.demGrid = await this._fetchBinary(`/api/cubes/dem_grid?id=${encodeURIComponent(this.host.selectedId)}`);
    }
    this._draw();
  }

  _onScale() {
    localStorage.setItem("cube-cloud-scale", this.scaleEl.checked ? "1" : "0");
    this._draw();
  }

  static ampFloor(meta, source, frac) {
    const [lo, hi] = meta.intensity[source];
    return lo + frac * (hi - lo);
  }

  static sampleRange(rows, offset, width) {
    const values = [];
    const stride = Math.max(1, Math.floor(rows.length / width / 4096)) * width;
    for (let i = offset; i < rows.length; i += stride) values.push(rows[i]);
    if (!values.length) return [0, 1];

    values.sort((a, b) => a - b);
    const lo = values[Math.floor(values.length * 0.02)];
    const hi = values[Math.floor(values.length * 0.98)];
    return hi > lo ? [lo, hi] : [lo, lo + 1];
  }

  _ampMin() {
    return TomogramCloud.ampFloor(this.host.meta, this.source, Number(this.thrEl.value) / 100);
  }

  _syncThresholdLabel() {
    if (!this.host.meta) return;
    this.thrValEl.textContent = this.host._fmt(this._ampMin());
  }

  _syncBtns() {
    this.colorEl.querySelectorAll(".cube-space").forEach((btn) => {
      btn.classList.toggle("is-active", btn.dataset.color === this.colorBy);
    });
  }

  async _fetchBinary(url) {
    try {
      const res = await fetch(url);
      if (!res.ok) return null;
      const raw = new Float32Array(await res.arrayBuffer());
      return { header: raw.subarray(0, 4), rows: raw.subarray(4) };
    } catch (e) {
      return null;
    }
  }

  async _fetch() {
    if (!this.available) return;

    const url = `/api/cubes/points?id=${encodeURIComponent(this.host.selectedId)}&source=${this.source}` +
      `&amp_min=${this._ampMin()}&max=${this.maxEl.value}`;

    this.token += 1;
    const token = this.token;

    const data = await this._fetchBinary(url);
    if (!data || token !== this.token) return;

    this.points = data.rows;
    this.total = data.header[1];
    this.muRange = this._sampleRange(data.rows, 2);
    this._draw();
  }

  _sampleRange(rows, offset) {
    return TomogramCloud.sampleRange(rows, offset, 4);
  }

  _resetView(draw = true) {
    this.yaw = 0.7;
    this.pitch = 0.9;
    this.zoom = 1.0;
    if (draw) this._draw();
  }

  _onDrag(ev) {
    if (!this.dragging) return;
    this.yaw += (ev.clientX - this.dragging.x) * 0.008;
    this.pitch = Math.min(1.55, Math.max(0.05, this.pitch + (ev.clientY - this.dragging.y) * 0.006));
    this.dragging = { x: ev.clientX, y: ev.clientY };
    this._draw();
  }

  _onWheel(ev) {
    ev.preventDefault();
    this.zoom = Math.min(8, Math.max(0.3, this.zoom * (ev.deltaY > 0 ? 0.9 : 1.11)));
    this._draw();
  }

  static palette(t) {
    const stops = TomogramCloud.VIRIDIS;
    const x = Math.min(0.9999, Math.max(0, t)) * (stops.length - 1);
    const i = Math.floor(x);
    const f = x - i;
    return [
      Math.round(stops[i][0] + (stops[i + 1][0] - stops[i][0]) * f),
      Math.round(stops[i][1] + (stops[i + 1][1] - stops[i][1]) * f),
      Math.round(stops[i][2] + (stops[i + 1][2] - stops[i][2]) * f),
    ];
  }

  _palette(t) {
    return TomogramCloud.palette(t);
  }

  _draw() {
    if (!this.points || this.host.view !== "cloud") return;

    const meta = this.host.meta;
    const stage = this.canvas.parentElement;
    const dpr = window.devicePixelRatio || 1;
    const w = Math.max(320, stage.clientWidth);
    const h = Math.max(320, Math.round(window.innerHeight * 0.62));

    if (this.canvas.width !== Math.round(w * dpr) || this.canvas.height !== Math.round(h * dpr)) {
      this.canvas.width = Math.round(w * dpr);
      this.canvas.height = Math.round(h * dpr);
      this.canvas.style.height = `${h}px`;
    }

    const W = this.canvas.width;
    const H = this.canvas.height;
    const ctx = this.canvas.getContext("2d");
    const image = ctx.createImageData(W, H);
    const buf = new Uint32Array(image.data.buffer);
    buf.fill(0xff1a1510);

    const cx = meta.n_rg / 2;
    const cy = meta.n_az / 2;
    const [muLo, muHi] = this.muRange || [meta.x_min, meta.x_max];
    const zMid = (muLo + muHi) / 2;
    const zSpan = (muHi - muLo) || 1;

    const spacing = this.scaleEl.checked && meta.spacing ? meta.spacing : null;
    const azStep = spacing ? spacing.az : 1;
    const rgStep = spacing ? spacing.rg : 1;
    const zScale = spacing ? 1 : (Math.max(meta.n_az, meta.n_rg) * 0.35) / (zSpan / 2);
    const extent = Math.max(meta.n_az * azStep, meta.n_rg * rgStep);

    const sinY = Math.sin(this.yaw), cosY = Math.cos(this.yaw);
    const sinP = Math.sin(this.pitch), cosP = Math.cos(this.pitch);
    const fit = (Math.min(W, H) / (extent * 1.9)) * this.zoom;

    const plot = (x, y, z, rgb) => {
      const rx = x * cosY - y * sinY;
      const ry = x * sinY + y * cosY;
      const sx = Math.round(W / 2 + rx * fit);
      const sy = Math.round(H / 2 + (ry * cosP - z * sinP) * fit);
      if (sx < 0 || sy < 0 || sx >= W - 1 || sy >= H - 1) return;
      const color = 0xff000000 | (rgb[2] << 16) | (rgb[1] << 8) | rgb[0];
      buf[sy * W + sx] = color;
      buf[sy * W + sx + 1] = color;
      buf[(sy + 1) * W + sx] = color;
      buf[(sy + 1) * W + sx + 1] = color;
    };

    const grid = this.demEl.checked && this.demGrid ? this.demGrid.rows : null;

    if (grid) {
      for (let az = 0; az < meta.n_az; az += 4) {
        for (let rg = 0; rg < meta.n_rg; rg += 4) {
          const g = grid[az * meta.n_rg + rg];
          if (!Number.isFinite(g)) continue;
          plot((rg - cx) * rgStep, (az - cy) * azStep, (g - zMid) * zScale, [110, 116, 122]);
        }
      }
    }

    const rows = this.points;
    const [ampLo, ampHi] = meta.intensity[this.source];

    for (let i = 0; i < rows.length; i += 4) {
      const mu = rows[i + 2];
      const amp = rows[i + 3];

      let z = mu - zMid;
      if (grid) {
        const g = grid[rows[i] * meta.n_rg + rows[i + 1]];
        if (!Number.isFinite(g)) continue;
        z += g;
      }

      const t = this.colorBy === "amp"
        ? (amp - ampLo) / Math.max(ampHi - ampLo, 1e-6)
        : (mu - muLo) / zSpan;
      plot((rows[i + 1] - cx) * rgStep, (rows[i] - cy) * azStep, z * zScale, this._palette(t));
    }

    ctx.putImageData(image, 0, 0);

    const shown = rows.length / 4;
    const scaleNote = spacing
      ? ` · 1:1 in metres · az ${Math.round(meta.n_az * azStep)} m × rg ${Math.round(meta.n_rg * rgStep)} m`
      : "";
    this.atEl.textContent = `${shown.toLocaleString()} of ${Math.round(this.total).toLocaleString()} voxels${scaleNote} · drag to orbit · wheel to zoom · double-click to reset`;
  }
}

class TomogramView {
  static LABELS = { full: "capon full", param: "parametrized" };
  static HOLD_SAVE_MS = 4000;
  static HOLD_HINT_MS = 800;
  static SWEEP_CACHE_BYTES = 192 * 1024 * 1024;

  constructor(refs) {
    this.strip = refs.strip;
    this.pickEl = refs.strip ? refs.strip.closest(".cube-pick") : null;
    this.stage = refs.stage;
    this.deck = refs.deck;
    this.topdown = refs.topdown;
    this.cross = refs.cross;
    this.coords = refs.coords;
    this.back = refs.back;
    this.hint = refs.hint;
    this.panels = refs.panels;
    this.slicesEl = refs.slices;
    this.slicesAt = refs.slicesAt;
    this.profilesEl = refs.profiles;
    this.profAt = refs.profAt;
    this.profModeBtns = refs.profModeBtns;
    this.profPanels = refs.profPanels;
    this.spaceBtns = refs.spaceBtns || [];
    this.modeBtns = refs.modeBtns || [];
    this.viewEls = refs.views || [];
    this.jumpAz = refs.jumpAz;
    this.jumpRg = refs.jumpRg;
    this.jumpGo = refs.jumpGo;
    this.jumpPrint = refs.jumpPrint;
    this.jumpAzRange = refs.jumpAzRange;
    this.jumpRgRange = refs.jumpRgRange;
    this.progress = refs.progress;
    this.progressFill = refs.progressFill;
    this.progressLabel = refs.progressLabel;
    this.paramRow = refs.paramRow;
    this.paramSel = refs.paramSel;
    this.slotsEl = refs.slots;
    this.slotsBody = refs.slotsBody;
    this.srcGroups = refs.srcGroups || [];
    this.cutStacks = refs.cutStacks || [];

    this.atLabels = {
      range   : this.slicesEl.querySelector('.cube-cutgroup__at[data-axis="range"]'),
      azimuth : this.slicesEl.querySelector('.cube-cutgroup__at[data-axis="azimuth"]'),
    };

    this.cubes = [];
    this.selectedId = null;
    this.runStrip = null;
    this.meta = null;
    this.space = "physical";
    this.point = null;
    this.mode = "map";
    this.locked = null;
    this.holdTimer = null;
    this.holdHintTimer = null;
    this.holdHintOn = false;
    this.holdFired = false;
    this.saving = false;
    this.entered = false;
    this.polling = false;
    this.profMode = "raw";
    this.profData = null;
    this.profQueued = null;
    this.profFetching = false;
    this.view = "explorer";
    this.colors = {};
    this.visible = new Set();
    this.paramTags = [];
    this.viewSource = "full";
    this.cmap = localStorage.getItem("cube-cmap") || "jet";
    this.sweepSpeed = Number(localStorage.getItem("cube-sweep-speed")) || 1;
    this.lensZoom = Number(localStorage.getItem("cube-lens-zoom") || 3);
    this.bitmapCache = new Map();
    this.bitmapBytes = 0;

    this.sweeps = (refs.sweeps || []).map((sweep) => new TomogramSweep(sweep, this));
    this.transect = refs.transect ? new TomogramTransect(refs.transect, this) : null;
    this.cloud = refs.cloud ? new TomogramCloud(refs.cloud, this) : null;
    this.globe = refs.globe ? new TomogramGlobe(refs.globe, this) : null;

    this.mapWrap = this.topdown.closest(".cube-map__wrap");

    this.lenses = [new TomogramLens(this.topdown, this.mapWrap, this)];
    this.panels.forEach((panel) => this.lenses.push(new TomogramLens(panel.canvas, panel.canvas.parentElement, this)));

    this.lensZoomSel = document.getElementById("cube-lens-zoom");
    if (this.lensZoomSel) {
      this.lensZoomSel.value = String(this.lensZoom);
      this.lensZoomSel.addEventListener("change", () => {
        this.lensZoom = Number(this.lensZoomSel.value);
        localStorage.setItem("cube-lens-zoom", String(this.lensZoom));
      });
    }

    this.topdown.addEventListener("mousemove", (ev) => this._onMove(ev));
    this.topdown.addEventListener("mousedown", (ev) => this._onHoldStart(ev));
    this.topdown.addEventListener("mouseup", () => this._cancelHold());
    this.topdown.addEventListener("mouseleave", () => this._cancelHold());
    this.topdown.addEventListener("click", (ev) => this._onClick(ev));
    this.topdown.addEventListener("load", () => this.mapWrap.classList.remove("is-loading"));
    this.topdown.addEventListener("error", () => this.mapWrap.classList.remove("is-loading"));

    this.back.addEventListener("click", () => this._exitSlices());
    document.addEventListener("keydown", (ev) => {
      if (ev.key === "Escape" && this.mode === "slices") this._exitSlices();
    });

    this.panels.forEach((panel) => {
      panel.canvas.addEventListener("mousemove", (ev) => this._onSliceMove(panel, ev));
    });

    this.spaceBtns.forEach((btn) => {
      btn.addEventListener("click", () => this._setSpace(btn.dataset.space));
    });
    this.profModeBtns.forEach((btn) => {
      btn.addEventListener("click", () => this._setProfMode(btn.dataset.mode));
    });
    this.modeBtns.forEach((btn) => {
      btn.addEventListener("click", () => this._setView(btn.dataset.view));
    });

    this.cmapSel = refs.cmapSel || null;
    if (this.cmapSel) {
      this.cmapSel.value = this.cmap;
      this.cmapSel.addEventListener("change", () => this._setCmap(this.cmapSel.value));
    }

    if (this.paramSel) this.paramSel.addEventListener("change", () => this._onParamPick());
    this.srcGroups.forEach((group) => {
      group.querySelectorAll(".cube-space").forEach((btn) => {
        btn.addEventListener("click", () => this._setViewSource(btn.dataset.ssource));
      });
    });

    if (this.jumpAz) this.jumpAz.addEventListener("change", () => this._setManualCut());
    if (this.jumpRg) this.jumpRg.addEventListener("change", () => this._setManualCut());
    if (this.jumpGo) this.jumpGo.addEventListener("click", () => this._setManualCut());
    if (this.jumpPrint) this.jumpPrint.addEventListener("click", () => this._printSlices());
  }

  leave() {
    this._stopSweeps();
  }

  async enter() {
    if (this.entered) {
      await this._refreshStrip();
      return;
    }
    this.entered = true;
    await this.refresh();
  }

  async _refreshStrip() {
    const data = await Api.get(`/api/cubes?base=${encodeURIComponent(ResultsSources.runs())}`);
    if (!data || data.error) return;
    this.cubes = data.cubes || [];
    this._renderStrip();
  }

  async refresh() {
    this.hint.hidden = false;
    this.hint.textContent = "Loading saved cubes…";
    this.hint.classList.add("is-loading");

    const data = await Api.get(`/api/cubes?base=${encodeURIComponent(ResultsSources.runs())}`);

    this.hint.classList.remove("is-loading");

    if (data.error) {
      this.hint.textContent = data.error;
      return;
    }

    this.cubes = data.cubes || [];
    this._renderStrip();

    if (!this.cubes.length) {
      this.hint.textContent = data.error || "No saved cubes found under the runs directory.";
      this.hint.hidden = false;
      this.stage.hidden = true;
      return;
    }

    this.hint.textContent = "Select a cube directory to load it into memory.";
    this.hint.hidden = false;
  }

  _renderStrip() {
    if (!this.runStrip) {
      this.runStrip = new RunStrip(this.strip, {
        stateFor : (cube) => cube.id === this.selectedId,
        onPick   : (cube) => this.select(cube.id),
      });
    }
    this.runStrip.render(this.cubes);
  }

  async select(cubeId, force = false) {
    if (this.polling) {
      Toast.show("A cube is still loading.", "warn");
      return;
    }
    if (!force && cubeId === this.selectedId && this.meta) return;

    this._stopSweeps();
    this.selectedId = cubeId;
    if (this.runStrip) this.runStrip.close((this.cubes.find((c) => c.id === cubeId) || {}).group);
    this.meta = null;
    this.point = null;
    this.locked = null;
    this.mode = "map";
    this.panels.forEach((panel) => {
      this._releasePanel(panel);
      panel.marker = 0;
      panel.queued = null;
      panel.fetching = false;
    });
    this.profQueued = null;
    this.profData = null;
    this.deck.dataset.mode = "map";
    this.back.hidden = true;
    this.cross.hidden = true;
    this._hideRefs();
    this.coords.textContent = "Hover the image to cut every tomogram · click to lock the slices";
    this.slicesAt.textContent = "";
    this.profAt.textContent = "Hover a slice to read the profiles at that position.";
    if (this.atLabels.range)   this.atLabels.range.textContent   = "";
    if (this.atLabels.azimuth) this.atLabels.azimuth.textContent = "";
    this.stage.hidden = true;
    this.slicesEl.hidden = true;
    this.slicesEl.classList.remove("is-in");
    this.hint.hidden = true;
    if (this.slotsEl) this.slotsEl.hidden = true;
    this._renderStrip();

    if (!force) await this._syncParamTags();

    const body = { id: cubeId };
    const tag = this._paramTag();
    if (tag) body.param_tag = tag;

    const res = await Api.post("/api/cubes/load", body);
    if (!res.ok) {
      this.hint.textContent = res.error || "Cube load failed.";
      this.hint.hidden = false;
      return;
    }

    this._setProgress(0, "loading");
    this.progress.hidden = false;
    await this._poll();
  }

  async _syncParamTags() {
    const res = await Api.get(`/api/cubes/param_runs?id=${encodeURIComponent(this.selectedId)}`);
    this.paramTags = (res && res.ok && res.tags) || [];
    this._renderParamPicker();
  }

  _paramTag() {
    const stored = localStorage.getItem(`cube-param:${this.selectedId}`) || "";
    return this.paramTags.includes(stored) ? stored : "";
  }

  _renderParamPicker() {
    if (!this.paramRow || !this.paramSel) return;

    this.paramRow.hidden = !this.paramTags.length;
    this.paramSel.innerHTML = "";
    if (!this.paramTags.length) return;

    const none = document.createElement("option");
    none.value = "";
    none.textContent = "none";
    this.paramSel.appendChild(none);

    this.paramTags.forEach((tag) => {
      const option = document.createElement("option");
      option.value = tag;
      option.textContent = tag;
      this.paramSel.appendChild(option);
    });
    this.paramSel.value = this._paramTag();
  }

  _onParamPick() {
    if (!this.selectedId) return;
    if (this.polling) {
      Toast.show("A cube is still loading.", "warn");
      this.paramSel.value = this._paramTag();
      return;
    }

    localStorage.setItem(`cube-param:${this.selectedId}`, this.paramSel.value);
    this.select(this.selectedId, true);
  }

  async _poll() {
    this.polling = true;

    while (true) {
      const st = await Api.get("/api/cubes/status");
      if (st.error) {
        this._failLoad(st.error);
        break;
      }

      if (st.id !== this.selectedId) {
        this.progress.hidden = true;
        break;
      }

      if (st.state === "loading") {
        this._setProgress(st.progress || 0, st.stage || "loading");
        await new Promise((r) => setTimeout(r, 400));
        continue;
      }

      if (st.state === "ready" && st.cube) {
        this._setProgress(1, "ready");
        this._display(st.cube);
        break;
      }

      this._failLoad(st.error || "Cube load failed.");
      break;
    }

    this.polling = false;
  }

  _failLoad(message) {
    this.progress.hidden = true;
    this.hint.textContent = message;
    this.hint.hidden = false;
  }

  _setProgress(frac, stage) {
    const pct = Math.max(0, Math.min(100, Math.round(frac * 100)));
    this.progressFill.style.width = `${pct}%`;
    const label = TomogramView.LABELS[stage] || stage;
    this.progressLabel.textContent = `${label} — ${pct}%`;
  }

  _display(meta) {
    this.meta = meta;
    this.progress.hidden = true;
    this._clearBitmapCache();

    const css = getComputedStyle(this.stage);
    this.colors = {
      full    : css.getPropertyValue("--src-full").trim(),
      param   : css.getPropertyValue("--src-param").trim(),
      range   : css.getPropertyValue("--cut-range").trim(),
      azimuth : css.getPropertyValue("--cut-azimuth").trim(),
    };

    if (!this.paramActive) this.viewSource = "full";
    this._syncSrcBtns();

    this._syncSpaceBtns();
    this._syncProfModeBtns();

    this.visible = new Set(meta.sources);
    this._applyVisibility();

    this.hint.hidden = true;
    this.stage.hidden = false;
    this.mapWrap.classList.add("is-loading");
    this.topdown.src = `/api/cubes/primary?id=${encodeURIComponent(this.selectedId)}`;

    this._initCutBounds();
    this.sweeps.forEach((sweep) => sweep.configure());

    if (this.transect) this.transect.configure();

    if (this.cloud) {
      this.cloud.configure(meta);
      const cloudBtn = this.modeBtns.find((btn) => btn.dataset.view === "cloud");
      if (cloudBtn) cloudBtn.hidden = !this.cloud.available;
      if (!this.cloud.available && this.view === "cloud") this._setView("explorer");
    }

    if (this.globe) {
      this.globe.configure(meta);
      const globeBtn = this.modeBtns.find((btn) => btn.dataset.view === "globe");
      if (globeBtn) globeBtn.hidden = !this.globe.available;
      if (!this.globe.available && this.view === "globe") this._setView("explorer");
    }

    this._follow({ az: Math.floor(meta.n_az / 2), rg: Math.floor(meta.n_rg / 2), fx: 0.5, fy: 0.5 }, true);
    this._consumeFocus();

    const sweep = this._sweepFor(this.view);
    if (sweep) sweep.play();
  }

  openAt(cubeId, az, rg) {
    this.pendingFocus = { az, rg };
    if (cubeId === this.selectedId && this.meta) {
      this._consumeFocus();
      return;
    }
    this.select(cubeId);
  }

  _consumeFocus() {
    if (!this.pendingFocus || !this.meta) return;
    const { az, rg } = this.pendingFocus;
    this.pendingFocus = null;

    const clampedAz = Math.max(0, Math.min(this.meta.n_az - 1, az));
    const clampedRg = Math.max(0, Math.min(this.meta.n_rg - 1, rg));

    this._setView("explorer");
    this._follow({
      az : clampedAz,
      rg : clampedRg,
      fx : this.meta.n_rg > 1 ? clampedRg / (this.meta.n_rg - 1) : 0.5,
      fy : this.meta.n_az > 1 ? clampedAz / (this.meta.n_az - 1) : 0.5,
    }, true);
  }

  _setCmap(cmap) {
    if (cmap === this.cmap) return;
    this.cmap = cmap;
    localStorage.setItem("cube-cmap", cmap);

    if (!this.meta) return;

    this.panels.forEach((panel) => this._releasePanel(panel));

    const sweep = this._sweepFor(this.view);
    if (sweep) sweep.syncSpace();
    if (this.transect) this.transect.syncSpace();
    if (this.point) this._drawSlices(this.point.az, this.point.rg);
  }

  _setSpace(space) {
    if (space === this.space || !["physical", "normalized"].includes(space)) return;
    this.space = space;
    this._syncSpaceBtns();

    if (!this.meta) return;
    const sweep = this._sweepFor(this.view);
    if (sweep) sweep.syncSpace();
    if (this.transect) this.transect.syncSpace();
    if (this.point) this._drawSlices(this.point.az, this.point.rg);
  }

  _setView(view) {
    if (!["explorer", "elevation", "azimuth", "range", "transect", "cloud", "globe"].includes(view) || view === this.view) return;

    this._stopSweeps();
    this.view = view;

    this.modeBtns.forEach((btn) => btn.classList.toggle("is-active", btn.dataset.view === view));
    this.viewEls.forEach((el) => { el.hidden = el.dataset.view !== view; });
    this._syncGlobeChrome();

    if (view === "transect" && this.transect && this.meta) {
      this.transect.render();
      return;
    }
    if (view === "cloud" && this.cloud && this.meta) {
      this.cloud.render();
      return;
    }
    if (view === "globe" && this.globe && this.meta) {
      this.globe.render();
      return;
    }

    const sweep = this._sweepFor(view);
    if (sweep && this.meta) sweep.play();
  }

  _syncGlobeChrome() {
    const collapsed = this.view === "globe";
    if (this.pickEl) this.pickEl.hidden = collapsed;
    this.stage.classList.toggle("is-globe", collapsed);
  }

  _sweepFor(view) {
    return this.sweeps.find((sweep) => sweep.axis === view) || null;
  }

  _stopSweeps() {
    this.sweeps.forEach((sweep) => sweep.stop());
  }

  _setSweepSpeed(speed) {
    this.sweepSpeed = speed;
    localStorage.setItem("cube-sweep-speed", String(speed));
    this.sweeps.forEach((sweep) => sweep.syncSpeed());
  }

  cacheBitmap(url) {
    const hit = this.bitmapCache.get(url);
    if (hit) {
      this.bitmapCache.delete(url);
      this.bitmapCache.set(url, hit);
      return hit.promise;
    }

    const entry = { promise: null, bytes: 0 };
    entry.promise = this._loadBitmap(url, entry);
    this.bitmapCache.set(url, entry);
    return entry.promise;
  }

  async _loadBitmap(url, entry) {
    try {
      const res = await fetch(url);
      if (!res.ok) { this.bitmapCache.delete(url); return null; }

      const bitmap = await createImageBitmap(await res.blob());
      entry.bytes = bitmap.width * bitmap.height * 4;
      this.bitmapBytes += entry.bytes;
      this._trimBitmapCache();
      return bitmap;
    } catch (e) {
      this.bitmapCache.delete(url);
      return null;
    }
  }

  _releasePanel(panel) {
    if (panel.bitmap && panel.bitmap.close) panel.bitmap.close();
    panel.bitmap = null;
    panel.key = null;
    panel.drawnSpace = null;
  }

  _trimBitmapCache() {
    while (this.bitmapBytes > TomogramView.SWEEP_CACHE_BYTES && this.bitmapCache.size > 1) {
      const oldest = this.bitmapCache.keys().next().value;
      this.bitmapBytes -= this.bitmapCache.get(oldest).bytes;
      this._dropBitmap(this.bitmapCache.get(oldest));
      this.bitmapCache.delete(oldest);
    }
  }

  _clearBitmapCache() {
    this.bitmapCache.forEach((entry) => this._dropBitmap(entry));
    this.bitmapCache.clear();
    this.bitmapBytes = 0;
  }

  async _dropBitmap(entry) {
    const bitmap = await entry.promise;
    if (bitmap && bitmap.close && !this.sweeps.some((sweep) => sweep.holds(bitmap))) bitmap.close();
  }

  _setProfMode(mode) {
    if (mode === this.profMode || !["raw", "unit"].includes(mode)) return;
    this.profMode = mode;
    this._syncProfModeBtns();
    this._drawProfiles();
  }

  _applyVisibility() {
    this.panels.forEach((panel) => {
      panel.root.hidden = !this.visible.has(panel.source);
    });
    this.profPanels.forEach((panel) => {
      panel.root.hidden = !this.visible.has(panel.source);
    });
    this.cutStacks.forEach((stack) => stack.classList.toggle("is-split", this.paramActive));

    this.sweeps.forEach((sweep) => sweep.applyVisibility());
  }

  get paramActive() {
    return !!(this.meta && this.meta.sources.includes("param"));
  }

  srcFor() {
    return this.paramActive && this.viewSource === "param" ? "param" : "full";
  }

  _setViewSource(source) {
    if (!["full", "param"].includes(source) || source === this.viewSource) return;

    this.viewSource = source;
    this._syncSrcBtns();
    if (!this.meta) return;

    if (this.cloud) {
      this.cloud.source = this.srcFor();
      this.cloud.points = null;
      this.cloud._syncThresholdLabel();
    }
    if (this.globe) {
      this.globe.source = this.srcFor();
      this.globe.points = null;
      this.globe.muRange = null;
      this.globe._syncThresholdLabel();
    }

    if (this.view === "transect" && this.transect) { this.transect.syncSpace(); return; }
    if (this.view === "cloud" && this.cloud)       { this.cloud.render(); return; }
    if (this.view === "globe" && this.globe)       { this.globe.render(); return; }

    const sweep = this._sweepFor(this.view);
    if (sweep) sweep.render();
  }

  _syncSrcBtns() {
    this.srcGroups.forEach((group) => {
      group.hidden = !this.paramActive;
      group.querySelectorAll(".cube-space").forEach((btn) => {
        btn.classList.toggle("is-active", btn.dataset.ssource === this.viewSource);
      });
    });
  }

  _syncSpaceBtns() {
    this.spaceBtns.forEach((btn) => {
      btn.classList.toggle("is-active", btn.dataset.space === this.space);
    });
  }

  _syncProfModeBtns() {
    this.profModeBtns.forEach((btn) => {
      btn.classList.toggle("is-active", btn.dataset.mode === this.profMode);
    });
  }

  _pointFromEvent(ev) {
    if (!this.meta) return null;

    const rect = this.topdown.getBoundingClientRect();
    const fx = (ev.clientX - rect.left) / rect.width;
    const fy = (ev.clientY - rect.top) / rect.height;

    return {
      az: Math.min(this.meta.n_az - 1, Math.max(0, Math.floor(fy * this.meta.n_az))),
      rg: Math.min(this.meta.n_rg - 1, Math.max(0, Math.floor(fx * this.meta.n_rg))),
      fx,
      fy,
    };
  }

  _onMove(ev) {
    if (this.mode !== "map") return;
    const point = this._pointFromEvent(ev);
    if (!point) return;
    this._follow(point);
  }

  _onClick(ev) {
    if (this.holdFired) {
      this.holdFired = false;
      return;
    }
    if (this.mode !== "map") return;
    const point = this._pointFromEvent(ev);
    if (!point) return;
    this._follow(point, true);
    this._enterSlices(point);
  }

  _onHoldStart(ev) {
    if (this.mode !== "map" || ev.button !== 0 || !this.meta) return;

    ev.preventDefault();
    this.holdFired = false;
    this._cancelHold();

    this.holdHintTimer = setTimeout(() => {
      this.holdHintOn = true;
      this.coords.textContent = "keep holding to save the slice figures…";
    }, TomogramView.HOLD_HINT_MS);

    this.holdTimer = setTimeout(() => this._fireHoldSave(), TomogramView.HOLD_SAVE_MS);
  }

  _cancelHold() {
    clearTimeout(this.holdHintTimer);
    clearTimeout(this.holdTimer);
    this.holdHintTimer = null;
    this.holdTimer = null;
    this.holdHintOn = false;
  }

  async _fireHoldSave() {
    this._cancelHold();
    if (this.mode !== "map" || !this.meta || !this.point) return;

    this.holdFired = true;
    this.holdHintOn = true;

    const { az, rg } = this.point;
    this.coords.textContent = `saving slice figures at az = ${az} · rg = ${rg}…`;

    await this._saveSlices(az, rg);

    this.holdHintOn = false;
    if (this.point) this.coords.textContent = `az = ${this.point.az} · rg = ${this.point.rg} · click to lock`;
  }

  _printSlices() {
    if (!this.meta) return;

    const az = this._clampInt(this.jumpAz ? this.jumpAz.value : 0, this.meta.n_az);
    const rg = this._clampInt(this.jumpRg ? this.jumpRg.value : 0, this.meta.n_rg);

    this._syncCutInputs(az, rg, true);
    this._saveSlices(az, rg);
  }

  async _saveSlices(az, rg) {
    if (!this.meta || !this.selectedId || this.saving) return;

    this.saving = true;
    if (this.jumpPrint) this.jumpPrint.disabled = true;

    const res = await Api.post("/api/cubes/save_slices", { id: this.selectedId, az, rg, space: this.space, cmap: this.cmap });

    this.saving = false;
    if (this.jumpPrint) this.jumpPrint.disabled = false;

    if (!res || !res.ok) {
      Toast.show((res && res.error) || "Slice figure save failed.", "error");
      return;
    }

    Toast.show(`Saved ${res.files.length} slice figures → ${res.rel}`, "ok");
  }

  _setManualCut() {
    if (!this.meta) return;

    const az = this._clampInt(this.jumpAz ? this.jumpAz.value : 0, this.meta.n_az);
    const rg = this._clampInt(this.jumpRg ? this.jumpRg.value : 0, this.meta.n_rg);
    const point = { az, rg, fx: (rg + 0.5) / this.meta.n_rg, fy: (az + 0.5) / this.meta.n_az };

    this._follow(point, true);
    this._enterSlices(point);
    this._syncCutInputs(az, rg, true);
  }

  _syncCutInputs(az, rg, force = false) {
    if (this.jumpAz && (force || document.activeElement !== this.jumpAz)) this.jumpAz.value = az;
    if (this.jumpRg && (force || document.activeElement !== this.jumpRg)) this.jumpRg.value = rg;
  }

  _initCutBounds() {
    if (this.jumpAz) { this.jumpAz.min = 0; this.jumpAz.max = this.meta.n_az - 1; }
    if (this.jumpRg) { this.jumpRg.min = 0; this.jumpRg.max = this.meta.n_rg - 1; }
    if (this.jumpAzRange) this.jumpAzRange.textContent = `0–${this.meta.n_az - 1}`;
    if (this.jumpRgRange) this.jumpRgRange.textContent = `0–${this.meta.n_rg - 1}`;
  }

  _enterSlices(point) {
    this.mode = "slices";
    this.locked = { az: point.az, rg: point.rg };
    this.deck.dataset.mode = "slices";
    this.back.hidden = false;
    this.slicesAt.textContent = `locked at az = ${point.az} · rg = ${point.rg} · hover a slice for profiles · Esc to go back`;
    this._queueProfiles(point.az, point.rg);
  }

  _exitSlices() {
    if (this.mode !== "slices") return;
    this.mode = "map";
    this.locked = null;
    this.deck.dataset.mode = "map";
    this.back.hidden = true;
    this.slicesAt.textContent = "";
    this._hideRefs();
  }

  _hideRefs() {
    this.panels.forEach((panel) => {
      if (panel.ref) panel.ref.hidden = true;
    });
  }

  _onSliceMove(panel, ev) {
    if (this.mode !== "slices" || !this.meta || !this.locked) return;

    const rect = panel.canvas.getBoundingClientRect();
    const frac = Math.min(1, Math.max(0, (ev.clientX - rect.left) / rect.width));
    const n    = panel.axis === "range" ? this.meta.n_az : this.meta.n_rg;
    const idx  = Math.min(n - 1, Math.floor(frac * n));

    this.panels.forEach((p) => {
      if (!p.ref || p.root.hidden) return;
      if (p.axis === panel.axis) {
        p.ref.hidden = false;
        p.ref.style.left = `${frac * 100}%`;
      } else {
        p.ref.hidden = true;
      }
    });

    const az = panel.axis === "range" ? idx : this.locked.az;
    const rg = panel.axis === "range" ? this.locked.rg : idx;
    this._queueProfiles(az, rg);
  }

  _follow(point, force = false) {
    if (!force && this.point && point.az === this.point.az && point.rg === this.point.rg) {
      this._moveCross(point);
      return;
    }

    this.point = point;
    this._moveCross(point);
    if (!this.holdHintOn) this.coords.textContent = `az = ${point.az} · rg = ${point.rg} · click to lock`;
    this._syncCutInputs(point.az, point.rg);

    this._drawSlices(point.az, point.rg);
  }

  _moveCross(point) {
    this.cross.hidden = false;
    this.cross.style.left = `${point.fx * 100}%`;
    this.cross.style.top = `${point.fy * 100}%`;
  }

  _revealSlices() {
    if (!this.slicesEl.hidden) return;
    this.slicesEl.hidden = false;
    requestAnimationFrame(() => requestAnimationFrame(() => this.slicesEl.classList.add("is-in")));
  }

  _drawSlices(az, rg) {
    if (!this.meta) return;

    this._revealSlices();

    if (this.atLabels.range)   this.atLabels.range.textContent   = `rg = ${rg}`;
    if (this.atLabels.azimuth) this.atLabels.azimuth.textContent = `az = ${az}`;

    this.panels.forEach((panel) => {
      if (panel.root.hidden) return;
      this._updatePanel(panel, az, rg);
    });
  }

  _updatePanel(panel, az, rg) {
    const key = panel.axis === "range" ? rg : az;
    panel.marker = panel.axis === "range" ? az / this.meta.n_az : rg / this.meta.n_rg;

    if (panel.bitmap && panel.key === key && panel.drawnSpace === this.space) {
      this._paintSlice(panel);
      return;
    }

    panel.queued = { az, rg, key };
    this._panelPump(panel);
  }

  async _panelPump(panel) {
    if (panel.fetching) return;
    panel.fetching = true;

    while (panel.queued) {
      const job = panel.queued;
      panel.queued = null;
      await this._fetchSlice(panel, job);
    }

    panel.fetching = false;
  }

  async _fetchSlice(panel, job) {
    const space = this.space;
    const url = `/api/cubes/slice?id=${encodeURIComponent(this.selectedId)}&source=${panel.source}&axis=${panel.axis}&az=${job.az}&rg=${job.rg}&space=${space}&cmap=${this.cmap}`;
    const skeletonTimer = panel.bitmap ? null : setTimeout(() => panel.root.classList.add("is-loading"), 120);

    try {
      const res = await fetch(url);
      if (!res.ok) return;

      const bitmap = await createImageBitmap(await res.blob());
      if (panel.bitmap && panel.bitmap.close) panel.bitmap.close();

      panel.bitmap = bitmap;
      panel.key = job.key;
      panel.drawnSpace = space;
      this._paintSlice(panel);
    } catch (e) {
    } finally {
      if (skeletonTimer) clearTimeout(skeletonTimer);
      panel.root.classList.remove("is-loading");
    }
  }

  _paintSlice(panel) {
    const bitmap = panel.bitmap;
    const canvas = panel.canvas;

    if (canvas.width !== bitmap.width || canvas.height !== bitmap.height) {
      canvas.width = bitmap.width;
      canvas.height = bitmap.height;
    }

    const ctx = canvas.getContext("2d");
    ctx.drawImage(bitmap, 0, 0);

    const x = panel.marker * canvas.width;

    ctx.setLineDash([2, 3]);
    ctx.strokeStyle = "rgba(255, 255, 255, 0.9)";
    ctx.lineWidth = 3.2;
    ctx.beginPath();
    ctx.moveTo(x, 0);
    ctx.lineTo(x, canvas.height);
    ctx.stroke();

    ctx.strokeStyle = this.colors[panel.axis] || "#fff";
    ctx.lineWidth = 1.6;
    ctx.beginPath();
    ctx.moveTo(x, 0);
    ctx.lineTo(x, canvas.height);
    ctx.stroke();
    ctx.setLineDash([]);
  }

  _queueProfiles(az, rg) {
    this.profAt.textContent = `profiles at az = ${az} · rg = ${rg}`;
    this.profQueued = { az, rg };
    this._profPump();
  }

  async _profPump() {
    if (this.profFetching || !this.profQueued) return;
    this.profFetching = true;

    while (this.profQueued) {
      const { az, rg } = this.profQueued;
      this.profQueued = null;
      await this._fetchProfiles(az, rg);
    }

    this.profFetching = false;
  }

  async _fetchProfiles(az, rg) {
    const staleTimer = setTimeout(() => {
      this.profPanels.forEach((panel) => panel.root.classList.add("is-stale"));
    }, 180);

    const id = encodeURIComponent(this.selectedId);
    const jobs = [Api.get(`/api/cubes/profiles?id=${id}&az=${az}&rg=${rg}`)];
    if (this.paramActive) jobs.push(Api.get(`/api/cubes/params_at?id=${id}&az=${az}&rg=${rg}`));

    const [data, slots] = await Promise.all(jobs);

    clearTimeout(staleTimer);
    this.profPanels.forEach((panel) => panel.root.classList.remove("is-stale"));

    this._renderSlots(slots);

    if (!data.ok) return;
    this.profData = data;
    this._drawProfiles();
  }

  _renderSlots(slots) {
    if (!this.slotsEl || !this.slotsBody) return;

    if (!this.paramActive || !slots || !slots.ok || !slots.slots) {
      this.slotsEl.hidden = true;
      this.slotsBody.innerHTML = "";
      return;
    }

    this.slotsBody.innerHTML = "";
    slots.slots.forEach((slot, idx) => {
      const row = document.createElement("tr");
      [String(idx + 1), this._fmt(slot.amplitude), this._fmt(slot.mean), this._fmt(slot.sigma)].forEach((text) => {
        const cell = document.createElement("td");
        cell.textContent = text;
        row.appendChild(cell);
      });
      this.slotsBody.appendChild(row);
    });
    this.slotsEl.hidden = false;
  }

  _drawProfiles() {
    if (!this.profData) return;

    this.profPanels.forEach((panel) => {
      if (panel.root.hidden) return;

      const overlays = [panel.source];
      if (panel.source === "full" && this.paramActive) overlays.push("param");

      const seriesList = overlays
        .map((source) => ({ source, series: this.profData.sources[source] }))
        .filter((entry) => entry.series);

      if (seriesList.length) this._drawProfile(panel, seriesList);
    });
  }

  _drawProfile(panel, seriesList) {
    const canvas = panel.canvas;
    const dpr = window.devicePixelRatio || 1;
    const w = canvas.clientWidth || 240;
    const h = canvas.clientHeight || 190;

    if (canvas.width !== Math.round(w * dpr) || canvas.height !== Math.round(h * dpr)) {
      canvas.width = Math.round(w * dpr);
      canvas.height = Math.round(h * dpr);
    }

    const ctx = canvas.getContext("2d");
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, w, h);

    const traces = seriesList
      .map(({ source, series }) => ({ source, heights: series.heights, values: this._scaledValues(series) }))
      .filter((trace) => trace.values.length >= 2);
    if (!traces.length) return;

    const padL = 8, padR = 8, padT = 16, padB = 8;
    const innerW = w - padL - padR;
    const innerH = h - padT - padB;
    const hMin = Math.min(...traces.map((trace) => trace.heights[0]));
    const hMax = Math.max(...traces.map((trace) => trace.heights[trace.heights.length - 1]));
    const span = hMax - hMin || 1;
    const vMax = Math.max(...traces.map((trace) => Math.max(...trace.values))) || 1;

    const xAt = (value) => padL + (value / vMax) * innerW * 0.96;
    const yAt = (height) => padT + (1 - (height - hMin) / span) * innerH;

    ctx.strokeStyle = "rgba(20, 25, 30, 0.07)";
    ctx.lineWidth = 1;
    for (let i = 1; i <= 3; i++) {
      const x = padL + (innerW * i) / 4;
      ctx.beginPath();
      ctx.moveTo(x, padT);
      ctx.lineTo(x, h - padB);
      ctx.stroke();
    }

    traces.forEach((trace, order) => {
      const { heights, values } = trace;
      const n = values.length;
      const color = this.colors[trace.source] || "#555";

      ctx.beginPath();
      ctx.moveTo(xAt(0), yAt(heights[0]));
      for (let i = 0; i < n; i++) ctx.lineTo(xAt(values[i]), yAt(heights[i]));
      ctx.lineTo(xAt(0), yAt(heights[n - 1]));
      ctx.closePath();
      ctx.globalAlpha = 0.12;
      ctx.fillStyle = color;
      ctx.fill();
      ctx.globalAlpha = 1;

      ctx.beginPath();
      for (let i = 0; i < n; i++) {
        if (i === 0) ctx.moveTo(xAt(values[i]), yAt(heights[i]));
        else ctx.lineTo(xAt(values[i]), yAt(heights[i]));
      }
      ctx.strokeStyle = color;
      ctx.lineWidth = 1.6;
      ctx.stroke();

      let peak = 0;
      for (let i = 1; i < n; i++) if (values[i] > values[peak]) peak = i;
      ctx.beginPath();
      ctx.arc(xAt(values[peak]), yAt(heights[peak]), 2.6, 0, Math.PI * 2);
      ctx.fillStyle = color;
      ctx.fill();

      ctx.fillStyle = color;
      ctx.font = "9.5px 'JetBrains Mono', monospace";
      ctx.textAlign = "right";
      ctx.fillText(`peak ${this._fmt(values[peak])} @ ${this._fmt(heights[peak])}`, w - 4, padT - 5 + order * 11);
    });

    ctx.fillStyle = "rgba(20, 25, 30, 0.55)";
    ctx.font = "9.5px 'JetBrains Mono', monospace";
    ctx.textAlign = "left";
    ctx.fillText(this._fmt(hMax), padL + 2, padT - 5);
    ctx.fillText(this._fmt(hMin), padL + 2, h - padB - 3);

    if (traces.length > 1) {
      const entries = traces.map((trace) => ({
        color : this.colors[trace.source] || "#555",
        label : TomogramView.LABELS[trace.source] || trace.source,
      }));
      let x = w - padR - 4 - entries.reduce((sum, entry) => sum + 20 + ctx.measureText(entry.label).width, -20);

      ctx.textAlign = "left";
      entries.forEach((entry) => {
        ctx.fillStyle = entry.color;
        ctx.fillRect(x, h - padB - 11, 8, 8);
        ctx.fillText(entry.label, x + 12, h - padB - 4);
        x += 20 + ctx.measureText(entry.label).width;
      });
    }
  }

  _scaledValues(series) {
    const values = series.values.map((v) => (Number.isFinite(v) ? Math.max(v, 0) : 0));
    if (this.profMode === "raw") return values;

    let area = 0;
    for (let i = 1; i < values.length; i++) {
      const dh = Math.abs(series.heights[i] - series.heights[i - 1]);
      area += 0.5 * (values[i] + values[i - 1]) * dh;
    }

    if (area <= 0) return values.map(() => 0);
    return values.map((v) => v / area);
  }

  _clampInt(value, count) {
    const n = Math.floor(Number(value));
    if (!Number.isFinite(n)) return 0;
    return Math.min(count - 1, Math.max(0, n));
  }

  _fmt(value) {
    const abs = Math.abs(value);
    if (abs >= 1000) return value.toFixed(0);
    if (abs >= 10)   return value.toFixed(1);
    if (abs >= 0.01 || abs === 0) return value.toFixed(2);
    return value.toExponential(1);
  }

}

window.TomogramView = TomogramView;
