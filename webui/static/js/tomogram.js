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
      return `/api/cubes/slice?id=${id}&source=${source}&axis=azimuth&az=${idx}&rg=0&space=${space}&cmap=${cmap}&dem=${this.host.demOn()}`;
    }
    return `/api/cubes/slice?id=${id}&source=${source}&axis=range&az=0&rg=${idx}&space=${space}&cmap=${cmap}&dem=${this.host.demOn()}`;
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
  static PROMPT = "Click points on the map to trace a polyline; every segment is cut through the tomograms.";

  constructor(refs, host) {
    this.host = host;
    this.atEl = refs.at;
    this.undoBtn = refs.undo;
    this.clearBtn = refs.clear;
    this.printBtn = refs.print;
    this.downloadBtn = refs.download || null;
    this.nameEl = refs.name;
    this.saveBtn = refs.save;
    this.savedSel = refs.saved;
    this.removeBtn = refs.remove;
    this.map = refs.map;
    this.overlay = refs.overlay;
    this.grid = refs.grid;
    this.panels = refs.panels || [];

    this.points = [];
    this.token = 0;
    this.saving = false;

    this.map.addEventListener("click", (ev) => this._onClick(ev));
    if (this.undoBtn) this.undoBtn.addEventListener("click", () => this._undo());
    this.clearBtn.addEventListener("click", () => this._reset());
    this.printBtn.addEventListener("click", () => this._print());
    if (this.downloadBtn) this.downloadBtn.addEventListener("click", () => this._download());
    if (this.saveBtn) this.saveBtn.addEventListener("click", () => this._saveLine());
    if (this.savedSel) this.savedSel.addEventListener("change", () => this._loadLine());
    if (this.removeBtn) this.removeBtn.addEventListener("click", () => this._deleteLine());
  }

  configure() {
    this._reset();
    this.map.src = `/api/cubes/primary?id=${encodeURIComponent(this.host.selectedId)}`;
    this._renderSaved();
  }

  render() {
    this._applyVisibility();
    if (this.points.length >= 2) this._fetchAll();
  }

  syncSpace() {
    if (this.host.view === "transect" && this.points.length >= 2) this._fetchAll();
  }

  _applyVisibility() {
    const meta = this.host.meta;
    this.panels.forEach((panel) => {
      panel.root.hidden = !meta || !meta.sources.includes(panel.source) || !this.host.visible.has(panel.source);
    });
  }

  _reset() {
    this.points = [];
    this.overlay.innerHTML = "";
    this.grid.hidden = true;
    this._syncButtons();
    this.atEl.textContent = TomogramTransect.PROMPT;
  }

  _syncButtons() {
    const some = this.points.length >= 1;
    const line = this.points.length >= 2;
    if (this.undoBtn) this.undoBtn.hidden = !some;
    this.clearBtn.hidden = !some;
    this.printBtn.hidden = !line;
    if (this.downloadBtn) this.downloadBtn.hidden = !line;
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

    const last = this.points[this.points.length - 1];
    if (last && last.az === point.az && last.rg === point.rg) return;

    this.points.push(point);
    this._afterChange();
  }

  _undo() {
    if (!this.points.length) return;
    this.points.pop();
    this._afterChange();
  }

  _afterChange() {
    this._drawOverlay();
    this._syncButtons();

    if (this.points.length < 2) {
      this.grid.hidden = true;
      const tail = this.points[this.points.length - 1];
      this.atEl.textContent = tail ? `start az = ${tail.az} · rg = ${tail.rg} · click the next point` : TomogramTransect.PROMPT;
      return;
    }

    const head = this.points[0];
    const tail = this.points[this.points.length - 1];
    this.atEl.textContent = `transect az ${head.az},${head.rg} to az ${tail.az},${tail.rg} · ${this.points.length} points · click to extend`;
    this._fetchAll();
  }

  _pts() {
    return this.points.map((p) => `${p.az},${p.rg}`).join(";");
  }

  _drawOverlay() {
    let svg = "";
    this.points.forEach((point, index) => {
      if (index > 0) {
        const prev = this.points[index - 1];
        svg += `<line x1="${prev.fx * 100}" y1="${prev.fy * 100}" x2="${point.fx * 100}" y2="${point.fy * 100}" class="cube-tline" />`;
      }
      svg += `<circle cx="${point.fx * 100}" cy="${point.fy * 100}" r="0.8" class="cube-tdot" />`;
    });
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
      `&pts=${encodeURIComponent(this._pts())}&space=${this.host.space}&cmap=${this.host.cmap}&dem=${this.host.demOn()}`;

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

  _storeKey() {
    const meta = this.host.meta;
    return `cube-transects:${meta.n_az}x${meta.n_rg}`;
  }

  _stored() {
    try {
      return JSON.parse(localStorage.getItem(this._storeKey()) || "[]");
    } catch (e) {
      return [];
    }
  }

  _renderSaved() {
    if (!this.savedSel || !this.host.meta) return;

    const stored = this._stored();
    this.savedSel.innerHTML = `<option value="">saved lines…</option>` +
      stored.map((entry) => `<option value="${SharedCharts.esc(entry.name)}">${SharedCharts.esc(entry.name)} (${entry.points.length} pts)</option>`).join("");
    if (this.removeBtn) this.removeBtn.hidden = true;
  }

  _saveLine() {
    if (this.points.length < 2) {
      Toast.show("Trace a line with at least two points first.", "warn");
      return;
    }

    const name = (this.nameEl && this.nameEl.value.trim()) || `line ${this._stored().length + 1}`;
    const stored = this._stored().filter((entry) => entry.name !== name);
    stored.push({ name, points: this.points.map((p) => [p.az, p.rg]) });

    localStorage.setItem(this._storeKey(), JSON.stringify(stored));
    if (this.nameEl) this.nameEl.value = "";
    this._renderSaved();
    this.savedSel.value = name;
    if (this.removeBtn) this.removeBtn.hidden = false;
    Toast.show(`Saved transect '${name}' for every cube with this footprint.`, "ok");
  }

  _loadLine() {
    const name = this.savedSel.value;
    if (this.removeBtn) this.removeBtn.hidden = !name;
    if (!name) return;

    const entry = this._stored().find((candidate) => candidate.name === name);
    if (!entry || !this.host.meta) return;

    const meta = this.host.meta;
    this.points = entry.points.map(([az, rg]) => ({
      az: Math.min(meta.n_az - 1, Math.max(0, az)),
      rg: Math.min(meta.n_rg - 1, Math.max(0, rg)),
      fx: (Math.min(meta.n_rg - 1, Math.max(0, rg)) + 0.5) / meta.n_rg,
      fy: (Math.min(meta.n_az - 1, Math.max(0, az)) + 0.5) / meta.n_az,
    }));
    this._afterChange();
  }

  _deleteLine() {
    const name = this.savedSel.value;
    if (!name) return;

    localStorage.setItem(this._storeKey(), JSON.stringify(this._stored().filter((entry) => entry.name !== name)));
    this._renderSaved();
    Toast.show(`Deleted saved transect '${name}'.`, "ok");
  }

  _download() {
    if (this.points.length < 2) return;

    const head = this.points[0];
    const tail = this.points[this.points.length - 1];
    const tag = `${this.host.fileTag()}_transect_az${head.az}_rg${head.rg}_to_az${tail.az}_rg${tail.rg}`;
    let count = 0;

    this.panels.forEach((panel) => {
      if (panel.root.hidden || !panel.canvas.width) return;
      FigureExport.saveCanvas(panel.canvas, `${tag}_${this.host.srcFor()}_${this.host.space}.png`);
      count += 1;
    });

    if (!count) Toast.show("No rendered transect panel to download.", "warn");
  }

  async _print() {
    if (this.points.length < 2 || this.saving) return;

    this.saving = true;
    this.printBtn.disabled = true;

    const res = await Api.post("/api/cubes/save_transect", {
      id: this.host.selectedId,
      pts: this.points.map((p) => [p.az, p.rg]),
      space: this.host.space,
      cmap: this.host.cmap,
      dem: this.host.demOn() === 1,
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
    this.canvas.dataset.nofig = "";
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
  static SWEEP_MS = 9000;
  static CUT_NAMES = { az: "azimuth", rg: "range", mu: "elevation" };
  static CUT_MESH_STEP = 8;

  constructor(refs, host) {
    this.host = host;
    this.colorEl = refs.color;
    this.thrEl = refs.thr;
    this.thrValEl = refs.thrVal;
    this.maxEl = refs.max;
    this.cutAxisEl = refs.cutAxis;
    this.cutPosEl = refs.cutPos;
    this.cutSweepEl = refs.cutSweep;
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
    this.muBounds = null;
    this.demGrid = null;
    this.demBounds = null;
    this.debounceTimer = null;
    this.token = 0;
    this.sweepFrame = null;
    this.sweepT0 = null;

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
    this.cutAxisEl.addEventListener("change", () => this._onCutAxis());
    this.cutPosEl.addEventListener("input", () => this._onCutPos());
    this.cutSweepEl.addEventListener("change", () => this._onCutSweep());

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
    this.muBounds = null;
    this.demGrid = null;
    this.demBounds = null;
    this.demWrap.hidden = !meta.dem;
    this.demEl.checked = false;
    this.scaleWrap.hidden = !meta.spacing;
    this._stopSweep();
    this._resetView(false);
    this._syncThresholdLabel();
  }

  render() {
    this._syncBtns();
    if (!this.points) this._fetch();
    else this._draw();
    if (this.cutSweepEl.checked && this.sweepFrame === null) this._startSweep();
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
      this.demBounds = this.demGrid ? TomogramCloud.valueBounds(this.demGrid.rows, 0, 1) : null;
    }
    this._draw();
  }

  _onScale() {
    localStorage.setItem("cube-cloud-scale", this.scaleEl.checked ? "1" : "0");
    this._draw();
  }

  _onCutAxis() {
    if (this.cutAxisEl.value === "off") {
      this.cutSweepEl.checked = false;
      this._stopSweep();
    }
    this._draw();
  }

  _onCutPos() {
    if (!this._cutRaf) {
      this._cutRaf = requestAnimationFrame(() => {
        this._cutRaf = null;
        this._draw();
      });
    }
  }

  _onCutSweep() {
    if (this.cutSweepEl.checked && this.cutAxisEl.value === "off") this.cutAxisEl.value = "az";
    if (this.cutSweepEl.checked) this._startSweep();
    else this._stopSweep();
  }

  _startSweep() {
    this._stopSweep();
    this.sweepFrame = requestAnimationFrame((now) => this._sweepStep(now));
  }

  _stopSweep() {
    if (this.sweepFrame !== null) cancelAnimationFrame(this.sweepFrame);
    this.sweepFrame = null;
    this.sweepT0 = null;
  }

  _sweepStep(now) {
    if (this.host.view !== "cloud" || !this.cutSweepEl.checked || this.cutAxisEl.value === "off") {
      this._stopSweep();
      return;
    }

    if (this.sweepT0 === null) this.sweepT0 = now - (Number(this.cutPosEl.value) / 100) * (TomogramCloud.SWEEP_MS / 2);
    const phase = ((now - this.sweepT0) % TomogramCloud.SWEEP_MS) / TomogramCloud.SWEEP_MS;
    const tri = phase < 0.5 ? phase * 2 : 2 - phase * 2;

    this.cutPosEl.value = String(Math.round(tri * 100));
    this._draw();
    this.sweepFrame = requestAnimationFrame((next) => this._sweepStep(next));
  }

  leave() {
    this._stopSweep();
  }

  _cutSpec() {
    const axis = this.cutAxisEl.value;
    if (axis === "off" || !this.host.meta || !this.muBounds) return null;

    const meta = this.host.meta;
    const frac = Number(this.cutPosEl.value) / 100;
    const lo = axis === "mu" ? this.muBounds[0] : 0;
    const hi = axis === "az" ? meta.n_az : axis === "rg" ? meta.n_rg : this.muBounds[1];
    return { axis, frac, threshold: lo + frac * (hi - lo) };
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

  static valueBounds(rows, offset, width) {
    let lo = Infinity, hi = -Infinity;
    for (let i = offset; i < rows.length; i += width) {
      const v = rows[i];
      if (!Number.isFinite(v)) continue;
      if (v < lo) lo = v;
      if (v > hi) hi = v;
    }
    return hi >= lo ? [lo, hi] : null;
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
    this.muBounds = TomogramCloud.valueBounds(data.rows, 2, 4);
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
    if (!this._dragRaf) {
      this._dragRaf = requestAnimationFrame(() => {
        this._dragRaf = null;
        this._draw();
      });
    }
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

    const cut = this._cutSpec();

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
        if (cut && cut.axis === "az" && az > cut.threshold) continue;
        for (let rg = 0; rg < meta.n_rg; rg += 4) {
          if (cut && cut.axis === "rg" && rg > cut.threshold) continue;
          const g = grid[az * meta.n_rg + rg];
          if (!Number.isFinite(g)) continue;
          plot((rg - cx) * rgStep, (az - cy) * azStep, (g - zMid) * zScale, [110, 116, 122]);
        }
      }
    }

    const rows = this.points;
    const [ampLo, ampHi] = meta.intensity[this.source];

    const cutOffset = cut ? { az: 0, rg: 1, mu: 2 }[cut.axis] : 0;
    let drawn = 0;

    for (let i = 0; i < rows.length; i += 4) {
      if (cut && rows[i + cutOffset] > cut.threshold) continue;
      drawn += 1;

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
    if (cut) {
      const [gLo, gHi] = grid && this.demBounds ? this.demBounds : [0, 0];
      const zLo = (this.muBounds[0] - zMid + gLo) * zScale;
      const zHi = (this.muBounds[1] - zMid + gHi) * zScale;
      this._drawCutPlane(ctx, cut, { meta, grid, cx, cy, azStep, rgStep, zMid, zScale, zLo, zHi, W, H, fit, sinY, cosY, sinP, cosP });
    }

    const shown = cut ? drawn : rows.length / 4;
    const scaleNote = spacing
      ? ` · 1:1 in metres · az ${Math.round(meta.n_az * azStep)} m × rg ${Math.round(meta.n_rg * rgStep)} m`
      : "";
    const cutNote = cut ? ` · cut ${TomogramCloud.CUT_NAMES[cut.axis]} @ ${Math.round(cut.frac * 100)}%` : "";
    this.atEl.textContent = `${shown.toLocaleString()} of ${Math.round(this.total).toLocaleString()} voxels${scaleNote}${cutNote} · drag to orbit · wheel to zoom · double-click to reset`;
  }

  _drawCutPlane(ctx, cut, g) {
    if (cut.axis === "mu" && g.grid) {
      this._drawDrapedCut(ctx, cut, g);
      return;
    }

    const zLo = g.zLo;
    const zHi = g.zHi;
    const x0 = (0 - g.cx) * g.rgStep, x1 = (g.meta.n_rg - g.cx) * g.rgStep;
    const y0 = (0 - g.cy) * g.azStep, y1 = (g.meta.n_az - g.cy) * g.azStep;

    let corners;
    if (cut.axis === "az") {
      const y = (cut.threshold - g.cy) * g.azStep;
      corners = [[x0, y, zLo], [x1, y, zLo], [x1, y, zHi], [x0, y, zHi]];
    } else if (cut.axis === "rg") {
      const x = (cut.threshold - g.cx) * g.rgStep;
      corners = [[x, y0, zLo], [x, y1, zLo], [x, y1, zHi], [x, y0, zHi]];
    } else {
      const z = (cut.threshold - g.zMid) * g.zScale;
      corners = [[x0, y0, z], [x1, y0, z], [x1, y1, z], [x0, y1, z]];
    }

    const pts = corners.map(([x, y, z]) => {
      const rx = x * g.cosY - y * g.sinY;
      const ry = x * g.sinY + y * g.cosY;
      return [g.W / 2 + rx * g.fit, g.H / 2 + (ry * g.cosP - z * g.sinP) * g.fit];
    });

    ctx.beginPath();
    ctx.moveTo(pts[0][0], pts[0][1]);
    pts.slice(1).forEach(([x, y]) => ctx.lineTo(x, y));
    ctx.closePath();
    ctx.fillStyle = "rgba(255, 209, 102, 0.10)";
    ctx.strokeStyle = "rgba(255, 209, 102, 0.55)";
    ctx.lineWidth = Math.max(1, window.devicePixelRatio || 1);
    ctx.fill();
    ctx.stroke();
  }

  _drawDrapedCut(ctx, cut, g) {
    const step = TomogramCloud.CUT_MESH_STEP;
    const meta = g.meta;

    const project = (az, rg) => {
      const height = g.grid[az * meta.n_rg + rg];
      if (!Number.isFinite(height)) return null;
      const x = (rg - g.cx) * g.rgStep;
      const y = (az - g.cy) * g.azStep;
      const z = (cut.threshold - g.zMid + height) * g.zScale;
      const rx = x * g.cosY - y * g.sinY;
      const ry = x * g.sinY + y * g.cosY;
      return [g.W / 2 + rx * g.fit, g.H / 2 + (ry * g.cosP - z * g.sinP) * g.fit];
    };

    ctx.beginPath();
    for (let az = 0; az < meta.n_az - 1; az += step) {
      const az1 = Math.min(az + step, meta.n_az - 1);
      for (let rg = 0; rg < meta.n_rg - 1; rg += step) {
        const rg1 = Math.min(rg + step, meta.n_rg - 1);
        const quad = [project(az, rg), project(az, rg1), project(az1, rg1), project(az1, rg)];
        if (quad.some((corner) => corner === null)) continue;
        ctx.moveTo(quad[0][0], quad[0][1]);
        quad.slice(1).forEach(([x, y]) => ctx.lineTo(x, y));
        ctx.closePath();
      }
    }

    ctx.fillStyle = "rgba(255, 209, 102, 0.10)";
    ctx.strokeStyle = "rgba(255, 209, 102, 0.25)";
    ctx.lineWidth = Math.max(1, window.devicePixelRatio || 1);
    ctx.fill();
    ctx.stroke();
  }
}

class TomogramPasses {
  constructor(refs, host) {
    this.host = host;
    this.kindEl = refs.kind;
    this.playBtn = refs.play;
    this.input = refs.input;
    this.rangeEl = refs.range;
    this.atEl = refs.at;
    this.media = refs.media;
    this.canvas = refs.canvas;
    this.cbar = refs.cbar;
    this.minEl = refs.min;
    this.maxEl = refs.max;

    this.meta = null;
    this.kind = "amplitude";
    this.idx = 0;
    this.token = 0;
    this.playing = false;

    this.kindEl.querySelectorAll(".cube-space").forEach((btn) => {
      btn.addEventListener("click", () => this._setKind(btn.dataset.kind));
    });
    this.media.addEventListener("wheel", (ev) => this._onWheel(ev), { passive: false });
    this.input.addEventListener("change", () => this._onManual());
    this.playBtn.addEventListener("click", () => this._togglePlay());
  }

  get available() {
    return !!this.meta;
  }

  configure(meta) {
    this.meta = meta.passes || null;
    this.kind = "amplitude";
    this.idx = 0;
    this._stopPlay();

    if (!this.meta) return;

    this.input.min = 1;
    this.input.max = this.meta.n_passes;
    this.input.value = 1;
    this.rangeEl.textContent = `1–${this.meta.n_passes}`;
  }

  render() {
    if (!this.meta) return;
    this._syncBtns();
    this._fetch();
  }

  leave() {
    this._stopPlay();
  }

  _setKind(kind) {
    if (kind === this.kind) return;
    if (kind === "phase" && !this.meta.phase) {
      Toast.show("This preprocessing run stores no interferogram cube.", "warn");
      return;
    }

    this.kind = kind;
    if (kind === "phase" && this.idx === 0) this.idx = Math.min(1, this.meta.n_passes - 1);
    this.render();
  }

  _syncBtns() {
    this.kindEl.querySelectorAll(".cube-space").forEach((btn) => {
      btn.classList.toggle("is-active", btn.dataset.kind === this.kind);
      if (btn.dataset.kind === "phase") btn.disabled = !this.meta.phase;
    });
  }

  _onWheel(ev) {
    if (!this.meta) return;
    ev.preventDefault();
    this._stopPlay();

    const lowest = this.kind === "phase" ? 1 : 0;
    const next = Math.min(this.meta.n_passes - 1, Math.max(lowest, this.idx + (ev.deltaY > 0 ? 1 : -1)));
    if (next === this.idx) return;

    this.idx = next;
    this._fetch();
  }

  _onManual() {
    if (!this.meta) return;
    this._stopPlay();

    const lowest = this.kind === "phase" ? 1 : 0;
    this.idx = Math.min(this.meta.n_passes - 1, Math.max(lowest, Math.floor(Number(this.input.value)) - 1 || 0));
    this._fetch();
  }

  _togglePlay() {
    if (this.playing) this._stopPlay();
    else this._startPlay();
  }

  _startPlay() {
    if (!this.meta || this.meta.n_passes < 2) return;
    this.playing = true;
    this.playBtn.textContent = "Pause";
    this.playBtn.classList.add("is-playing");
    this._loop();
  }

  _stopPlay() {
    this.playing = false;
    this.playBtn.textContent = "Play";
    this.playBtn.classList.remove("is-playing");
  }

  async _loop() {
    while (this.playing && this.meta && this.host.view === "passes") {
      const lowest = this.kind === "phase" ? 1 : 0;
      await this._fetch();
      await new Promise((resolve) => setTimeout(resolve, 550));
      if (!this.playing) break;
      this.idx = this.idx + 1 > this.meta.n_passes - 1 ? lowest : this.idx + 1;
    }
    this._stopPlay();
  }

  _url(idx) {
    return `/api/cubes/pass_map?id=${encodeURIComponent(this.host.selectedId)}&kind=${this.kind}&idx=${idx}&cmap=gray`;
  }

  async _fetch() {
    this.token += 1;
    const token = this.token;

    if (document.activeElement !== this.input) this.input.value = this.idx + 1;
    const label = this.meta.labels[this.idx] || `pass ${this.idx}`;
    const what = this.kind === "phase" ? "interferometric phase vs primary" : "SLC amplitude";
    this.atEl.textContent = `${label} · ${what} · pass ${this.idx + 1} / ${this.meta.n_passes}`;

    if (this.kind === "phase") {
      this.cbar.src = "/api/cubes/cbar?cmap=twilight";
      this.minEl.textContent = "−π";
      this.maxEl.textContent = "+π";
    } else {
      this.cbar.src = "/api/cubes/cbar?cmap=gray";
      this.minEl.textContent = "p1";
      this.maxEl.textContent = "p99 dB";
    }

    if (this.idx + 1 < this.meta.n_passes) this.host.cacheBitmap(this._url(this.idx + 1));

    const bitmap = await this.host.cacheBitmap(this._url(this.idx));
    if (!bitmap || token !== this.token) return;

    if (this.canvas.width !== bitmap.width || this.canvas.height !== bitmap.height) {
      this.canvas.width = bitmap.width;
      this.canvas.height = bitmap.height;
    }
    this.canvas.getContext("2d").drawImage(bitmap, 0, 0);
  }
}

class TomogramPauli {
  static MODE_LABELS = { rgb: "Pauli composite", surface: "surface power", double: "double-bounce power", volume: "volume power", dominant: "dominant mechanism" };
  static HINT = "Hover the map to read the mechanism balance under the cursor; click to lock a pixel.";
  static ASPECTS = ["px", "slant", "ground"];
  static ASPECT_KEY = "cube-pauli-aspect";

  constructor(refs, host) {
    this.host = host;
    this.modeEl = refs.mode;
    this.stretchEl = refs.stretch;
    this.winAz = refs.winAz;
    this.winRg = refs.winRg;
    this.aspectEl = refs.aspect;
    this.atEl = refs.at;
    this.media = refs.media;
    this.canvas = refs.canvas;
    this.cross = refs.cross;
    this.cbar = refs.cbar;
    this.minEl = refs.min;
    this.maxEl = refs.max;
    this.classesEl = refs.classes;
    this.noteEl = refs.note;
    this.summaryEl = refs.summary;
    this.coordsEl = refs.coords;
    this.readoutEl = refs.readout;
    this.downloadBtn = refs.download;

    this.meta = null;
    this.mode = "rgb";
    this.stretch = "channel";
    this.aspect = "px";
    this.win = null;
    this.summary = null;
    this.picked = null;
    this.adopted = -1;
    this.token = 0;
    this.hoverQueued = null;
    this.hoverFetching = false;

    this.modeEl.querySelectorAll(".cube-space").forEach((btn) => btn.addEventListener("click", () => this._setMode(btn.dataset.mode)));
    this.stretchEl.querySelectorAll(".cube-space").forEach((btn) => btn.addEventListener("click", () => this._setStretch(btn.dataset.stretch)));
    this.aspectEl.querySelectorAll(".cube-space").forEach((btn) => btn.addEventListener("click", () => this._setAspect(btn.dataset.aspect)));
    this.winAz.addEventListener("change", () => this.render());
    this.winRg.addEventListener("change", () => this.render());
    this.media.addEventListener("mousemove", (ev) => this._onHover(ev));
    this.media.addEventListener("mouseleave", () => this._onLeave());
    this.media.addEventListener("click", (ev) => this._onClick(ev));
    this.downloadBtn.addEventListener("click", () => this._download());
  }

  get available() {
    return !!this.meta;
  }

  configure(meta) {
    this.meta = meta.pauli || null;
    this.mode = "rgb";
    this.stretch = "channel";
    this.win = null;
    this.summary = null;
    this.picked = null;
    this.adopted = -1;
    this.cross.hidden = true;
    this.readoutEl.innerHTML = "";
    this.summaryEl.innerHTML = "";
    this.noteEl.textContent = "";
    this.coordsEl.textContent = TomogramPauli.HINT;
    if (!this.meta) return;

    this.winAz.max = this.meta.window_max;
    this.winRg.max = this.meta.window_max;
    this.winAz.value = this.meta.window[0];
    this.winRg.value = this.meta.window[1];
    this.win = { az: this.meta.window[0], rg: this.meta.window[1] };

    const offered = this._aspects();
    let stored = null;
    try { stored = localStorage.getItem(TomogramPauli.ASPECT_KEY); } catch (e) { stored = null; }
    this.aspect = offered.includes(stored) ? stored : offered[offered.length - 1];
    this.aspectEl.querySelectorAll(".cube-space").forEach((btn) => { btn.hidden = !offered.includes(btn.dataset.aspect); });
    this._applyAspect();
  }

  _aspects() {
    const spacing = this.host.meta.spacing;
    const offered = ["px"];
    if (spacing) offered.push("slant");
    if (spacing && spacing.ground_rg) offered.push("ground");
    return offered;
  }

  _setAspect(aspect) {
    if (aspect === this.aspect || !this._aspects().includes(aspect)) return;
    this.aspect = aspect;
    try { localStorage.setItem(TomogramPauli.ASPECT_KEY, aspect); } catch (e) { return; }
    this._syncBtns();
    this._applyAspect();
    this._syncAt();
  }

  _rangeSpacing() {
    const spacing = this.host.meta.spacing;
    if (!spacing || this.aspect === "px") return null;
    return this.aspect === "ground" ? spacing.ground_rg : spacing.rg;
  }

  _applyAspect() {
    const rg = this._rangeSpacing();
    const meta = this.host.meta;
    this.canvas.style.aspectRatio = rg ? `${meta.n_rg * rg} / ${meta.n_az * meta.spacing.az}` : "";
  }

  _syncAt() {
    if (!this.meta || !this.win) return;
    const meta = this.host.meta;
    const rg = this._rangeSpacing();
    let extent = " · pixel grid";
    if (rg && this.aspect === "slant") extent = ` · ${Math.round(meta.n_az * meta.spacing.az)} m az × ${Math.round(meta.n_rg * rg)} m slant rg`;
    if (rg && this.aspect === "ground") extent = ` · ${Math.round(meta.n_az * meta.spacing.az)} m az × ${Math.round(meta.n_rg * rg)} m ground rg · incidence ${meta.spacing.incidence_deg.toFixed(0)}°`;
    this.atEl.textContent = `${TomogramPauli.MODE_LABELS[this.mode]} · window ${this.win.az} × ${this.win.rg} px${extent}`;
  }

  applyState(state) {
    if (!this.meta) return;
    let changed = false;

    if (state.pwin) {
      const [az, rg] = state.pwin.split("x").map(Number);
      if (Number.isFinite(az) && Number.isFinite(rg)) {
        this.winAz.value = az;
        this.winRg.value = rg;
        changed = true;
      }
    }
    if (this.meta.modes.includes(state.pmode) && state.pmode !== this.mode) {
      this.mode = state.pmode;
      changed = true;
    }
    if (["channel", "shared"].includes(state.pstretch) && state.pstretch !== this.stretch) {
      this.stretch = state.pstretch;
      changed = true;
    }

    if (changed && this.host.view === "pauli") this.render();
  }

  render() {
    if (!this.meta) return;
    this._syncBtns();
    this._fetch();
  }

  leave() {
    this.hoverQueued = null;
  }

  _setMode(mode) {
    if (mode === this.mode) return;
    this.mode = mode;
    this.render();
  }

  _setStretch(stretch) {
    if (stretch === this.stretch) return;
    this.stretch = stretch;
    this.render();
  }

  _syncBtns() {
    this.modeEl.querySelectorAll(".cube-space").forEach((btn) => btn.classList.toggle("is-active", btn.dataset.mode === this.mode));
    this.stretchEl.querySelectorAll(".cube-space").forEach((btn) => btn.classList.toggle("is-active", btn.dataset.stretch === this.stretch));
    this.aspectEl.querySelectorAll(".cube-space").forEach((btn) => btn.classList.toggle("is-active", btn.dataset.aspect === this.aspect));
    this.stretchEl.hidden = this.mode === "dominant";
  }

  _window() {
    const clamp = (el) => Math.min(this.meta.window_max, Math.max(1, Math.floor(Number(el.value)) || 1));
    return { az: clamp(this.winAz), rg: clamp(this.winRg) };
  }

  _query(win) {
    return `id=${encodeURIComponent(this.host.selectedId)}&win_az=${win.az}&win_rg=${win.rg}&stretch=${this.stretch}`;
  }

  _url(win) {
    return `/api/cubes/pauli_map?${this._query(win)}&mode=${this.mode}`;
  }

  async _fetch() {
    this.token += 1;
    const token = this.token;
    const win = this._window();
    this.winAz.value = win.az;
    this.winRg.value = win.rg;
    this.atEl.textContent = `${TomogramPauli.MODE_LABELS[this.mode]} · window ${win.az} × ${win.rg} px`;

    const [summary, bitmap] = await Promise.all([
      Api.get(`/api/cubes/pauli_summary?${this._query(win)}`),
      this.host.cacheBitmap(this._url(win)),
    ]);
    if (token !== this.token || !bitmap) return;

    this.win = win;
    this.summary = summary && summary.ok ? summary : null;
    if (this.canvas.width !== bitmap.width || this.canvas.height !== bitmap.height) {
      this.canvas.width = bitmap.width;
      this.canvas.height = bitmap.height;
    }
    this.canvas.getContext("2d").drawImage(bitmap, 0, 0);
    this._applyAspect();
    this._syncAt();

    this._legend();
    this._summaryTable();
    this._adoptFocus();
  }

  _swatches(keys, range = () => "") {
    return keys.map((key) => {
      const component = this.meta.components.find((item) => item.key === key);
      return `<span class="cube-cat"><i style="background:${component.color}"></i>${SharedCharts.esc(component.label)}${range(key)}</span>`;
    }).join("");
  }

  _legend() {
    const single = this.mode !== "rgb" && this.mode !== "dominant";
    this.cbar.hidden = !single;
    this.minEl.hidden = !single;
    this.maxEl.hidden = !single;
    this.classesEl.hidden = single;

    if (single) {
      this.cbar.src = "/api/cubes/cbar?cmap=viridis";
      const bounds = this.summary ? this.summary.bounds[this.mode] : null;
      this.minEl.textContent = bounds ? `${bounds[0].toFixed(1)} dB` : "";
      this.maxEl.textContent = bounds ? `${bounds[1].toFixed(1)} dB` : "";
      this.classesEl.innerHTML = "";
      return;
    }

    const order = this.mode === "rgb" ? ["double", "volume", "surface"] : ["surface", "double", "volume"];
    const prefix = this.mode === "rgb" ? `<span class="cube-cat">red · green · blue =</span>` : "";
    const bounds = this.mode === "rgb" && this.summary ? this.summary.bounds : null;
    const shared = !!bounds && this.stretch === "shared";
    const span = (key) => ` ${bounds[key][0].toFixed(1)} to ${bounds[key][1].toFixed(1)} dB`;
    const range = bounds && !shared ? span : () => "";
    const scale = shared ? `<span class="cube-cat">one scale${span("surface")}</span>` : "";
    this.classesEl.innerHTML = prefix + this._swatches(order, range) + scale;
  }

  _summaryTable() {
    if (!this.summary) {
      this.summaryEl.innerHTML = "";
      this.noteEl.textContent = "";
      return;
    }

    const pct = (value) => `${(100 * value).toFixed(1)}%`;
    let html = `<table class="cube-metrics cube-metrics--params"><thead><tr><th scope="col">mechanism</th><th scope="col" title="Share of the scene's summed span this mechanism carries: its power summed over every pixel holding data, divided by the summed span; independent of the multilook window">span share</th><th scope="col" title="Share of the pixels holding data where this mechanism has the largest multilooked power">dominant</th></tr></thead><tbody>`;
    this.meta.components.forEach((component) => {
      html += `<tr><th scope="row">${SharedCharts.esc(component.label)}</th><td>${pct(this.summary.scene_share[component.key])}</td><td>${pct(this.summary.dominant_share[component.key])}</td></tr>`;
    });
    html += `</tbody></table>`;

    this.summaryEl.innerHTML = html;
    const scale = this.stretch === "shared" ? "one dB scale for all components" : "each component on its own dB scale";
    const nodata = this.summary.n_nodata > 0 ? ` · ${this.summary.n_nodata.toLocaleString()} no-data pixels left out` : "";
    const ratios = `span ${this.summary.span_db.toFixed(1)} dB · HH/VV ${this.summary.hh_vv_db.toFixed(1)} dB · HV/HH ${this.summary.hv_hh_db.toFixed(1)} dB`;
    this.noteEl.textContent = `${this.summary.n_pixels.toLocaleString()} pixels · multilook ${this.summary.window[0]} × ${this.summary.window[1]} px · ${scale} · scene means ${ratios}${nodata} · span share = summed power / summed span · dominant = share of pixels won`;
  }

  _pointFromEvent(ev) {
    const rect = this.canvas.getBoundingClientRect();
    const fx = (ev.clientX - rect.left) / rect.width;
    const fy = (ev.clientY - rect.top) / rect.height;
    return {
      az: Math.min(this.host.meta.n_az - 1, Math.max(0, Math.floor(fy * this.host.meta.n_az))),
      rg: Math.min(this.host.meta.n_rg - 1, Math.max(0, Math.floor(fx * this.host.meta.n_rg))),
      fx,
      fy,
    };
  }

  _onHover(ev) {
    if (!this.meta || !this.host.meta || this.picked) return;
    this.hoverQueued = this._pointFromEvent(ev);
    this._hoverPump();
  }

  _onLeave() {
    if (this.picked) return;
    this.hoverQueued = null;
    this.coordsEl.textContent = TomogramPauli.HINT;
  }

  async _hoverPump() {
    if (this.hoverFetching) return;
    this.hoverFetching = true;

    while (this.hoverQueued) {
      const { az, rg } = this.hoverQueued;
      this.hoverQueued = null;
      const data = await this._valueAt(az, rg);
      if (data && !this.picked) this.coordsEl.textContent = `az = ${data.az} · rg = ${data.rg} · ${this._balance(data)}`;
    }

    this.hoverFetching = false;
  }

  _valueAt(az, rg) {
    return Api.get(`/api/cubes/pauli_at?${this._query(this.win)}&az=${az}&rg=${rg}`).then((data) => (data && data.ok ? data : null));
  }

  _balance(data) {
    if (!data.valid) return "no data under this window";
    const parts = this.meta.components.map((component) => `${component.key} ${(100 * data.fractions[component.key]).toFixed(0)}%`);
    return `span share ${parts.join(" · ")} · dominant ${data.dominant}`;
  }

  _onClick(ev) {
    if (!this.meta || !this.host.meta) return;

    if (this.picked) {
      this.picked = null;
      this.cross.hidden = true;
      this.readoutEl.innerHTML = "";
      this.coordsEl.textContent = TomogramPauli.HINT;
      return;
    }

    const point = this._pointFromEvent(ev);
    this.host.setFocus(point.az, point.rg);
    this.adopted = this.host.focusSeq;
    this._lock(point);
  }

  _lock(point) {
    this.picked = point;
    this.cross.hidden = false;
    this.cross.style.left = `${point.fx * 100}%`;
    this.cross.style.top = `${point.fy * 100}%`;
    this.coordsEl.textContent = `locked at az = ${point.az} · rg = ${point.rg} · click again to unlock`;
    this._fetchReadout(point.az, point.rg);
  }

  _adoptFocus() {
    if (this.host.focusSeq === this.adopted) {
      if (this.picked) this._fetchReadout(this.picked.az, this.picked.rg);
      return;
    }

    const point = this.host.focusPoint();
    if (!point) return;
    this.adopted = this.host.focusSeq;
    this._lock(point);
  }

  async _fetchReadout(az, rg) {
    const data = await this._valueAt(az, rg);
    if (!data || !this.picked || this.picked.az !== az || this.picked.rg !== rg) return;

    if (!data.valid) {
      this.readoutEl.innerHTML = `<p class="cube-hint">no data under this window</p>`;
      return;
    }

    let html = `<table class="cube-metrics cube-metrics--params"><thead><tr><th scope="col">mechanism</th><th scope="col" title="Multilooked power of the Pauli component">power</th><th scope="col" title="Share of this pixel's span the component carries">span share</th></tr></thead><tbody>`;
    this.meta.components.forEach((component) => {
      const dominant = component.key === data.dominant;
      html += `<tr${dominant ? ' class="is-dominant"' : ""}><th scope="row">${SharedCharts.esc(component.label)}</th><td>${data.db[component.key].toFixed(1)} dB</td><td>${(100 * data.fractions[component.key]).toFixed(1)}%</td></tr>`;
    });
    html += `</tbody></table>`;

    const ratios = [
      ["span", "Total power |HH|² + 2|HV|² + |VV|²", data.span_db],
      ["HH/VV", "Co-polar ratio of the multilooked powers", data.hh_vv_db],
      ["HV/HH", "Cross-polar ratio of the multilooked powers", data.hv_hh_db],
    ];
    html += `<table class="cube-metrics cube-metrics--params"><thead><tr><th scope="col">channel</th><th scope="col">dB</th></tr></thead><tbody>`;
    ratios.forEach(([label, title, value]) => {
      html += `<tr><th scope="row" title="${title}">${label}</th><td>${value.toFixed(1)} dB</td></tr>`;
    });
    html += `</tbody></table>`;

    this.readoutEl.innerHTML = html;
  }

  async _download() {
    if (!this.meta || !this.host.selectedId) return;
    const win = this.win;
    const res = await fetch(this._url(win));
    if (!res.ok) {
      Toast.show("Pauli map download failed.", "warn");
      return;
    }
    const scale = this.mode === "dominant" ? "" : `_${this.stretch}`;
    FigureExport.download(`${this.host.fileTag()}_pauli_${this.mode}_w${win.az}x${win.rg}${scale}.png`, await res.blob());
  }
}

class TomogramFigures {
  constructor(refs, host) {
    this.host = host;
    this.root = refs.root;
    this.loadedFor = null;
  }

  configure() {
    this.loadedFor = null;
    this.root.innerHTML = ThinkingOrb.panel("composing", "Loading figures…");
  }

  async render() {
    if (this.loadedFor === this.host.selectedId) return;

    const cubeId = this.host.selectedId;
    const data = await Api.get(`/api/cubes/figures?id=${encodeURIComponent(cubeId)}`);
    if (cubeId !== this.host.selectedId) return;

    this.loadedFor = cubeId;

    if (!data || !data.ok) {
      this.root.innerHTML = `<p class="cube-hint">${SharedCharts.esc((data && data.error) || "Figure listing failed.")}</p>`;
      return;
    }
    if (!data.groups.length) {
      this.root.innerHTML = `<p class="cube-hint">This run holds no saved figures.</p>`;
      return;
    }

    const total = data.groups.reduce((sum, group) => sum + group.files.length, 0);
    let html = `<p class="cube-hint">${total.toLocaleString()} saved figures in ${data.groups.length} folders — click a thumbnail to open it full size.</p>`;

    data.groups.forEach((group, index) => {
      const items = group.files.map((file) => {
        const rel = `${group.dir}/${file}`;
        const url = `/api/cubes/figure?id=${encodeURIComponent(cubeId)}&rel=${encodeURIComponent(rel)}`;
        return `<a class="cube-fig" href="${url}" target="_blank" rel="noopener" title="${SharedCharts.esc(rel)}">` +
          `<img src="${url}" loading="lazy" alt="${SharedCharts.esc(file)}" /><span>${SharedCharts.esc(file)}</span></a>`;
      }).join("");

      html += `<details class="cube-figgroup"${index === 0 ? " open" : ""}>` +
        `<summary>${SharedCharts.esc(group.dir)} <em>${group.files.length}</em></summary>` +
        `<div class="cube-figgrid">${items}</div></details>`;
    });

    this.root.innerHTML = html;
  }
}

class TomogramView {
  static LABELS = { full: "capon full", param: "parametrized" };
  static SLOT_COLORS = ["#e45756", "#4c78a8", "#54a24b", "#b279a2", "#eeca3b", "#72b7b2", "#f58518", "#9d755d"];
  static HOLD_SAVE_MS = 4000;
  static STATUS_TIMEOUT_MS = 15000;
  static STALL_AFTER_S = 5;
  static HOLD_HINT_MS = 800;
  static SWEEP_CACHE_BYTES = 192 * 1024 * 1024;
  static DEM_VIEWS = ["explorer", "azimuth", "range", "transect"];

  constructor(refs) {
    this.strip = refs.strip;
    this.pickEl = refs.strip ? refs.strip.closest(".cube-pick") : null;
    this.stage = refs.stage;
    this.page = refs.stage.closest(".page");
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
    this.focus = null;
    this.focusSeq = 0;
    this.cutsAdopted = 0;
    this.holdTimer = null;
    this.holdHintTimer = null;
    this.holdHintOn = false;
    this.holdFired = false;
    this.saving = false;
    this.entered = false;
    this.polling = false;
    this.profMode = "raw";
    this.profData = null;
    this.profSlots = null;
    this.profMix = false;
    this.profQueued = null;
    this.profFetching = false;
    this.view = "explorer";
    this.colors = {};
    this.visible = new Set();
    this.paramTags = [];
    this.viewSource = "full";
    this.cmap = localStorage.getItem("cube-cmap") || "jet";
    this.dem = localStorage.getItem("cube-dem") === "1";
    this.sweepSpeed = Number(localStorage.getItem("cube-sweep-speed")) || 1;
    this.lensZoom = Number(localStorage.getItem("cube-lens-zoom") || 3);
    this.bitmapCache = new Map();
    this.bitmapBytes = 0;

    this.sweeps = (refs.sweeps || []).map((sweep) => new TomogramSweep(sweep, this));
    this.transect = refs.transect ? new TomogramTransect(refs.transect, this) : null;
    this.cloud = refs.cloud ? new TomogramCloud(refs.cloud, this) : null;
    this.globe = refs.globe ? new TomogramGlobe(refs.globe, this) : null;
    this.figures = refs.figures && refs.figures.root ? new TomogramFigures(refs.figures, this) : null;
    this.passes = refs.passes && refs.passes.canvas ? new TomogramPasses(refs.passes, this) : null;
    this.pauli = refs.pauli && refs.pauli.canvas ? new TomogramPauli(refs.pauli, this) : null;
    this.volume = refs.volume && refs.volume.canvas && window.TomogramVolume ? new window.TomogramVolume(refs.volume, this) : null;

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
    this.profMixWrap = refs.profMixWrap || null;
    this.profMixChk = refs.profMix || null;
    if (this.profMixChk) this.profMixChk.addEventListener("change", () => this._setProfMix(this.profMixChk.checked));
    this.modeBtns.forEach((btn) => {
      btn.addEventListener("click", () => this._setView(btn.dataset.view));
    });

    this.cmapSel = refs.cmapSel || null;
    if (this.cmapSel) {
      this.cmapSel.value = this.cmap;
      this.cmapSel.addEventListener("change", () => this._setCmap(this.cmapSel.value));
    }

    this.demWrap = refs.demWrap || null;
    this.demChk = refs.demChk || null;
    if (this.demChk) {
      this.demChk.checked = this.dem;
      this.demChk.addEventListener("change", () => this._setDem(this.demChk.checked));
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

    this.pendingState = null;
    this.storySnapshots = {};
    this.storyTimer = null;

    this.linkBtn = refs.linkBtn || null;
    if (this.linkBtn) this.linkBtn.addEventListener("click", () => this._copyLink());

    const story = refs.story || {};
    this.storyPanel = story.panel || null;
    this.storyName = story.name || null;
    this.storyPlayBtn = story.play || null;
    this.storyHint = story.hint || null;
    this.storyList = story.list || null;
    if (this.storyPanel) {
      if (story.toggle) story.toggle.addEventListener("click", () => this._toggleStoryPanel());
      if (story.add) story.add.addEventListener("click", () => this._storyAdd());
      if (this.storyPlayBtn) this.storyPlayBtn.addEventListener("click", () => this._storyTogglePlay());
      if (story.export) story.export.addEventListener("click", () => this._storyExport());
      if (story.clear) story.clear.addEventListener("click", () => this._storyClear());
    }

    this.jumpDownload = refs.jumpDownload || null;
    this.jumpCsv = refs.jumpCsv || null;
    if (this.jumpDownload) this.jumpDownload.addEventListener("click", () => this._downloadCuts());
    if (this.jumpCsv) this.jumpCsv.addEventListener("click", () => this._downloadProfilesCsv());
  }

  fileTag() {
    const cube = this.cubes.find((c) => c.id === this.selectedId);
    const raw = cube ? [cube.run, cube.stamp].filter(Boolean).join("_") : "cube";
    return raw.replace(/[^A-Za-z0-9._-]+/g, "_");
  }

  figureTag() {
    const parts = [this.fileTag(), this.srcFor(), this.space];
    if (this.point) parts.push(`az${String(this.point.az).padStart(4, "0")}_rg${String(this.point.rg).padStart(4, "0")}`);

    return parts.filter(Boolean).join("_");
  }

  _downloadCuts() {
    if (!this.meta || !this.point) {
      Toast.show("Hover or lock a cut first.", "warn");
      return;
    }

    const az = String(this.point.az).padStart(4, "0");
    const rg = String(this.point.rg).padStart(4, "0");
    const tag = this.fileTag();

    let count = 0;
    this.panels.forEach((panel) => {
      if (panel.root.hidden || !panel.bitmap) return;
      FigureExport.saveBitmap(panel.bitmap, `${tag}_az${az}_rg${rg}_${panel.axis}_${panel.source}_${this.space}.png`);
      count += 1;
    });

    if (!count) Toast.show("No rendered cut to download.", "warn");
  }

  _downloadProfilesCsv() {
    if (!this.profData) {
      Toast.show("Lock a pixel first so the profiles are loaded.", "warn");
      return;
    }

    const az = String(this.profData.az).padStart(4, "0");
    const rg = String(this.profData.rg).padStart(4, "0");
    const lines = ["source,height_m,value"];

    Object.entries(this.profData.sources).forEach(([source, series]) => {
      series.heights.forEach((height, i) => lines.push(`${source},${height},${series.values[i]}`));
    });

    FigureExport.download(`${this.fileTag()}_profiles_az${az}_rg${rg}.csv`, new Blob([lines.join("\n")], { type: "text/csv" }));
  }

  leave() {
    this._stopSweeps();
    this._storyStopPlay();
    if (this.cloud) this.cloud.leave();
    if (this.globe) this.globe.leave();
    if (this.passes) this.passes.leave();
    if (this.pauli) this.pauli.leave();
  }

  async enter(param = null) {
    const state = this._parseState(param);
    if (state) this.pendingState = state;

    if (this.entered) {
      await this._refreshStrip();
      this._applyPendingState();
      return;
    }
    this.entered = true;
    await this.refresh();
    this._applyPendingState();
  }

  _parseState(param) {
    if (!param) return null;

    try {
      const query = new URLSearchParams(decodeURIComponent(param));
      if (!query.get("id")) return null;
      return {
        id       : query.get("id"),
        view     : query.get("view"),
        az       : query.has("az") ? Number(query.get("az")) : null,
        rg       : query.has("rg") ? Number(query.get("rg")) : null,
        source   : query.get("source"),
        tag      : query.get("tag") ?? "",
        space    : query.get("space"),
        cmap     : query.get("cmap"),
        pmode    : query.get("pmode"),
        pstretch : query.get("pstretch"),
        pwin     : query.get("pwin"),
      };
    } catch (e) {
      return null;
    }
  }

  stateParam() {
    const query = new URLSearchParams();
    query.set("id", this.selectedId);
    query.set("view", this.view);
    query.set("source", this.srcFor());
    query.set("tag", this._loadedTag());
    query.set("space", this.space);
    query.set("cmap", this.cmap);

    const point = this.locked || this.point;
    if (point) {
      query.set("az", String(point.az));
      query.set("rg", String(point.rg));
    }
    if (this.view === "pauli" && this.pauli && this.pauli.available) {
      query.set("pmode", this.pauli.mode);
      query.set("pstretch", this.pauli.stretch);
      query.set("pwin", `${this.pauli.win.az}x${this.pauli.win.rg}`);
    }

    return encodeURIComponent(query.toString());
  }

  _applyPendingState() {
    const state = this.pendingState;
    if (!state) return;

    if (state.id !== this.selectedId || !this.meta) {
      if (this.cubes.some((cube) => cube.id === state.id)) {
        localStorage.setItem(`cube-param:${state.id}`, state.tag);
        this.select(state.id);
      } else if (this.cubes.length) {
        Toast.show("The linked cube is not in the current runs root.", "warn");
        this.pendingState = null;
      }
      return;
    }

    if (state.tag !== this._loadedTag()) {
      if (!state.tagReloaded && (state.tag === "" || this.paramTags.includes(state.tag))) {
        state.tagReloaded = true;
        localStorage.setItem(`cube-param:${state.id}`, state.tag);
        this.select(state.id, true);
        return;
      }
      Toast.show(`Parameter run '${state.tag}' is not available for this cube.`, "warn");
    }

    this.pendingState = null;
    this._applyState(state);
  }

  _loadedTag() {
    return (this.meta && this.meta.param && this.meta.param.tag) || "";
  }

  _applyState(state) {
    if (state.cmap && this.cmapSel && [...this.cmapSel.options].some((option) => option.value === state.cmap)) {
      this.cmapSel.value = state.cmap;
      this._setCmap(state.cmap);
    }
    if (state.space) this._setSpace(state.space);
    if (state.source === "param" && !this.paramActive) {
      Toast.show("The linked view shows a parameter run that is not loaded; showing Capon instead.", "warn");
    }
    if (state.source) this._setViewSource(state.source);

    if (Number.isFinite(state.az) && Number.isFinite(state.rg)) {
      const az = Math.max(0, Math.min(this.meta.n_az - 1, state.az));
      const rg = Math.max(0, Math.min(this.meta.n_rg - 1, state.rg));
      const point = { az, rg, fx: (rg + 0.5) / this.meta.n_rg, fy: (az + 0.5) / this.meta.n_az };
      if (this.view !== "explorer") this._setView("explorer");
      this._follow(point, true);
      this._enterSlices(point);
    }

    if (this.pauli) this.pauli.applyState(state);
    if (state.view) {
      const btn = this.modeBtns.find((candidate) => candidate.dataset.view === state.view);
      if (btn && !btn.hidden) this._setView(state.view);
      else if (btn) Toast.show(`This cube has no ${btn.textContent.trim()} view; the link opened without it.`, "warn");
    }
  }

  _copyLink() {
    if (!this.selectedId || !this.meta) {
      Toast.show("Load a cube first.", "warn");
      return;
    }

    const url = `${location.origin}${location.pathname}#/cube/${this.stateParam()}`;
    navigator.clipboard.writeText(url)
      .then(() => Toast.show("View link copied to the clipboard.", "ok"))
      .catch(() => Toast.show(url, "ok"));
  }

  _storyStore() {
    try {
      return JSON.parse(localStorage.getItem("cube-story") || "[]");
    } catch (e) {
      return [];
    }
  }

  _storySave(steps) {
    localStorage.setItem("cube-story", JSON.stringify(steps));
  }

  _toggleStoryPanel() {
    this.storyPanel.hidden = !this.storyPanel.hidden;
    if (!this.storyPanel.hidden) this._storyRender();
  }

  _snapshotDataUrl() {
    const active = this.viewEls.find((el) => !el.hidden);
    if (!active) return null;

    const canvas = [...active.querySelectorAll("canvas")].find((c) => c.width > 0);
    if (canvas) {
      try { return canvas.toDataURL("image/png"); } catch (e) { return null; }
    }

    const img = active.querySelector("img");
    if (img && img.naturalWidth) {
      const copy = document.createElement("canvas");
      copy.width = img.naturalWidth;
      copy.height = img.naturalHeight;
      try {
        copy.getContext("2d").drawImage(img, 0, 0);
        return copy.toDataURL("image/png");
      } catch (e) {
        return null;
      }
    }
    return null;
  }

  _storyAdd() {
    if (!this.selectedId || !this.meta) {
      Toast.show("Load a cube first.", "warn");
      return;
    }

    const steps = this._storyStore();
    const step = {
      id    : `${Date.now()}_${Math.floor(Math.random() * 1e6)}`,
      name  : (this.storyName.value || "").trim() || `step ${steps.length + 1}`,
      param : this.stateParam(),
    };

    const snapshot = this._snapshotDataUrl();
    if (snapshot) this.storySnapshots[step.id] = snapshot;

    steps.push(step);
    this._storySave(steps);
    this.storyName.value = "";
    this._storyRender();
    Toast.show(`Story step '${step.name}' recorded.`, "ok");
  }

  _storyRender() {
    const steps = this._storyStore();
    this.storyHint.textContent = steps.length ? `${steps.length} steps · snapshots live only until the page reloads` : "No steps yet — set up a view and press Add step.";

    this.storyList.innerHTML = "";
    steps.forEach((step, index) => {
      const item = document.createElement("li");

      const label = document.createElement("span");
      label.className = "cube-story__name";
      label.textContent = `${index + 1}. ${step.name}`;
      item.appendChild(label);

      const go = document.createElement("button");
      go.type = "button";
      go.className = "btn btn--mini";
      go.textContent = "Go";
      go.addEventListener("click", () => this._storyGo(step));
      item.appendChild(go);

      const copy = document.createElement("button");
      copy.type = "button";
      copy.className = "btn btn--mini";
      copy.textContent = "Copy link";
      copy.addEventListener("click", () => {
        const url = `${location.origin}${location.pathname}#/cube/${step.param}`;
        navigator.clipboard.writeText(url).then(() => Toast.show("Step link copied.", "ok")).catch(() => Toast.show(url, "ok"));
      });
      item.appendChild(copy);

      const remove = document.createElement("button");
      remove.type = "button";
      remove.className = "btn btn--mini";
      remove.textContent = "Remove";
      remove.addEventListener("click", () => {
        this._storySave(this._storyStore().filter((entry) => entry.id !== step.id));
        delete this.storySnapshots[step.id];
        this._storyRender();
      });
      item.appendChild(remove);

      this.storyList.appendChild(item);
    });
  }

  _storyGo(step) {
    const state = this._parseState(step.param);
    if (!state) return;
    this.pendingState = state;
    this._applyPendingState();
  }

  _storyTogglePlay() {
    if (this.storyTimer !== null) {
      this._storyStopPlay();
      return;
    }

    const steps = this._storyStore();
    if (!steps.length) {
      Toast.show("The story has no steps yet.", "warn");
      return;
    }

    let index = 0;
    this.storyPlayBtn.textContent = "Stop";
    const advance = () => {
      this._storyGo(steps[index]);
      index += 1;
      if (index >= steps.length) {
        this._storyStopPlay();
        return;
      }
      this.storyTimer = setTimeout(advance, 2600);
    };
    this.storyTimer = setTimeout(advance, 10);
  }

  _storyStopPlay() {
    if (this.storyTimer !== null) clearTimeout(this.storyTimer);
    this.storyTimer = null;
    if (this.storyPlayBtn) this.storyPlayBtn.textContent = "Play";
  }

  _storyExport() {
    const steps = this._storyStore();
    let count = 0;

    steps.forEach((step, index) => {
      const snapshot = this.storySnapshots[step.id];
      if (!snapshot) return;
      FigureExport.download(`story_${String(index + 1).padStart(2, "0")}_${FigureExport.slug(step.name)}.png`, snapshot);
      count += 1;
    });

    if (!count) Toast.show("No snapshots in memory — snapshots are taken when a step is added and last until reload.", "warn");
  }

  _storyClear() {
    this._storySave([]);
    this.storySnapshots = {};
    this._storyRender();
  }

  async _refreshStrip() {
    const data = await Api.get(`/api/cubes?base=${encodeURIComponent(ResultsSources.runs())}`);
    if (!data || data.error) return;
    this.cubes = data.cubes || [];
    this._renderStrip();
  }

  async refresh() {
    this.hint.hidden = false;
    this.hint.innerHTML = ThinkingOrb.busy("searching", "Loading saved cubes…");

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
      this._showStage(false);
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
    this.focus = null;
    this.cutsAdopted = this.focusSeq;
    this.mode = "map";
    this.panels.forEach((panel) => {
      this._releasePanel(panel);
      panel.marker = 0;
      panel.queued = null;
      panel.fetching = false;
    });
    this.profQueued = null;
    this.profData = null;
    this.profSlots = null;
    this.deck.dataset.mode = "map";
    this.back.hidden = true;
    this.cross.hidden = true;
    this._hideRefs();
    this.coords.textContent = "Hover the image to cut every tomogram · click to lock the slices";
    this.slicesAt.textContent = "";
    this.profAt.textContent = "Hover a slice to read the profiles at that position.";
    if (this.atLabels.range)   this.atLabels.range.textContent   = "";
    if (this.atLabels.azimuth) this.atLabels.azimuth.textContent = "";
    this._showStage(false);
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
      const st = await Api.get("/api/cubes/status", TomogramView.STATUS_TIMEOUT_MS);
      if (st.error) {
        this._failLoad(st.error);
        break;
      }

      if (st.id !== this.selectedId) {
        this.progress.hidden = true;
        break;
      }

      if (st.state === "loading") {
        this._setProgress(st.progress || 0, st.stage || "loading", st.reading || [], st.stalled_for || 0, st.where || []);
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

  _slowestStage(timings) {
    const [stage, seconds] = Object.entries(timings.stages).sort((a, b) => b[1] - a[1])[0];
    return `${stage} ${seconds.toFixed(1)} s`;
  }

  _failLoad(message) {
    this.progress.hidden = true;
    this.hint.textContent = message;
    this.hint.hidden = false;
  }

  _setProgress(frac, stage, reading = [], stalledFor = 0, where = []) {
    const pct = Math.max(0, Math.min(100, Math.round(frac * 100)));
    this.progressFill.style.width = `${pct}%`;
    const label = TomogramView.LABELS[stage] || stage;
    const mb = (bytes) => (bytes / 1048576).toFixed(0);
    const inFlight = reading.slice(0, 2).map((row) => `${row.file} ${mb(row.done)}/${mb(row.total)} MB`).join(", ");
    const tail = reading.length ? ` · ${reading.length} file${reading.length === 1 ? "" : "s"} in flight: ${inFlight}` : "";
    const stall = stalledFor >= TomogramView.STALL_AFTER_S ? ` · no progress for ${Math.round(stalledFor)} s, worker at ${where.slice(-2).join(" < ") || "unknown"}` : "";
    this.progressLabel.textContent = `${label} — ${pct}%${tail}${stall}`;
  }

  _display(meta) {
    this.meta = meta;
    this.progress.hidden = true;
    this.coords.textContent = `loaded in ${meta.timings.total.toFixed(1)} s (${this._slowestStage(meta.timings)}) · hover the image to cut every tomogram · click to lock the slices`;
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
    if (this.profMixWrap) this.profMixWrap.hidden = !this.paramActive;

    this._syncSpaceBtns();
    this._syncProfModeBtns();

    this._syncDemToggle();
    if (this.demChk) this.demChk.checked = this.dem;

    this.visible = new Set(meta.sources);
    this._applyVisibility();

    this.hint.hidden = true;
    this._showStage(true);
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

    if (this.volume) {
      this.volume.configure(meta);
      const volumeBtn = this.modeBtns.find((btn) => btn.dataset.view === "volume");
      if (volumeBtn) volumeBtn.hidden = !this.volume.available;
      if (!this.volume.available && this.view === "volume") this._setView("explorer");
      else if (this.view === "volume") this.volume.render();
    }

    if (this.globe) {
      this.globe.configure(meta);
      const globeBtn = this.modeBtns.find((btn) => btn.dataset.view === "globe");
      if (globeBtn) globeBtn.hidden = !this.globe.available;
      if (!this.globe.available && this.view === "globe") this._setView("explorer");
    }

    if (this.passes) {
      this.passes.configure(meta);
      const passesBtn = this.modeBtns.find((btn) => btn.dataset.view === "passes");
      if (passesBtn) passesBtn.hidden = !this.passes.available;
      if (!this.passes.available && this.view === "passes") this._setView("explorer");
      else if (this.view === "passes") this.passes.render();
    }

    if (this.pauli) {
      this.pauli.configure(meta);
      const pauliBtn = this.modeBtns.find((btn) => btn.dataset.view === "pauli");
      if (pauliBtn) pauliBtn.hidden = !this.pauli.available;
      if (!this.pauli.available && this.view === "pauli") this._setView("explorer");
      else if (this.view === "pauli") this.pauli.render();
    }

    if (this.figures) {
      this.figures.configure();
      if (this.view === "figures") this.figures.render();
    }

    this._follow({ az: Math.floor(meta.n_az / 2), rg: Math.floor(meta.n_rg / 2), fx: 0.5, fy: 0.5 }, true);
    this._consumeFocus();
    this._applyPendingState();

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
    this._refreshCuts(true);
  }

  demOn() {
    return this.dem && this.meta && this.meta.dem ? 1 : 0;
  }

  _setDem(on) {
    this.dem = !!on;
    localStorage.setItem("cube-dem", this.dem ? "1" : "0");
    this._refreshCuts(true);
  }

  _setSpace(space) {
    if (space === this.space || !["physical", "normalized"].includes(space)) return;
    this.space = space;
    this._syncSpaceBtns();
    this._refreshCuts(false);
  }

  _refreshCuts(release) {
    if (!this.meta) return;

    if (release) this.panels.forEach((panel) => this._releasePanel(panel));

    const sweep = this._sweepFor(this.view);
    if (sweep) sweep.syncSpace();
    if (this.transect) this.transect.syncSpace();
    if (this.point) this._drawSlices(this.point.az, this.point.rg);
  }

  _setView(view) {
    if (!["explorer", "elevation", "azimuth", "range", "transect", "cloud", "volume", "globe", "figures", "passes", "pauli"].includes(view) || view === this.view) return;

    this._stopSweeps();
    this.view = view;

    this.modeBtns.forEach((btn) => btn.classList.toggle("is-active", btn.dataset.view === view));
    this.viewEls.forEach((el) => { el.hidden = el.dataset.view !== view; });
    this._syncDemToggle();
    this._syncGlobeChrome();

    if (view === "transect" && this.transect && this.meta) {
      this.transect.render();
      return;
    }
    if (view === "cloud" && this.cloud && this.meta) {
      this.cloud.render();
      return;
    }
    if (view === "volume" && this.volume && this.meta) {
      this.volume.render();
      return;
    }
    if (view === "globe" && this.globe && this.meta) {
      this.globe.render();
      return;
    }
    if (view === "figures" && this.figures && this.meta) {
      this.figures.render();
      return;
    }
    if (view === "passes" && this.passes && this.meta) {
      this.passes.render();
      return;
    }
    if (view === "pauli" && this.pauli && this.meta) {
      this.pauli.render();
      return;
    }

    if (view === "explorer" && this.meta && this.focus && this.cutsAdopted !== this.focusSeq) {
      const point = this.focusPoint();
      this._follow(point, true);
      this._enterSlices(point);
      return;
    }

    const sweep = this._sweepFor(view);
    if (sweep && this.meta) sweep.play();
  }

  _syncDemToggle() {
    if (!this.demWrap) return;
    const carried = !!(this.meta && this.meta.dem);
    this.demWrap.hidden = !carried || !TomogramView.DEM_VIEWS.includes(this.view);
  }

  _syncGlobeChrome() {
    const collapsed = this.view === "globe";
    if (this.pickEl) this.pickEl.hidden = collapsed;
    this.stage.classList.toggle("is-globe", collapsed);
    this._syncStageChrome();
  }

  _showStage(shown) {
    this.stage.hidden = !shown;
    this._syncStageChrome();
  }

  _syncStageChrome() {
    const staged = !this.stage.hidden;
    const globe  = staged && this.stage.classList.contains("is-globe");
    this.page.classList.toggle("is-staged", staged);
    this.page.classList.toggle("is-globe-stage", globe);
    document.body.classList.toggle("is-globe-stage", globe);
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
    if (this.view === "volume" && this.volume)     { this.volume.render(); return; }
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
    this.coords.innerHTML = ThinkingOrb.busy("composing", `saving slice figures at az = ${az} · rg = ${rg}…`);

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

    const res = await Api.post("/api/cubes/save_slices", { id: this.selectedId, az, rg, space: this.space, cmap: this.cmap, dem: this.demOn() === 1 });

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

  setFocus(az, rg) {
    this.focus = { az, rg };
    this.focusSeq += 1;
  }

  focusPoint() {
    if (!this.focus || !this.meta) return null;
    const az = Math.max(0, Math.min(this.meta.n_az - 1, this.focus.az));
    const rg = Math.max(0, Math.min(this.meta.n_rg - 1, this.focus.rg));
    return { az, rg, fx: (rg + 0.5) / this.meta.n_rg, fy: (az + 0.5) / this.meta.n_az };
  }

  _enterSlices(point) {
    this.mode = "slices";
    this.locked = { az: point.az, rg: point.rg };
    this.setFocus(point.az, point.rg);
    this.cutsAdopted = this.focusSeq;
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
    const url = `/api/cubes/slice?id=${encodeURIComponent(this.selectedId)}&source=${panel.source}&axis=${panel.axis}&az=${job.az}&rg=${job.rg}&space=${space}&cmap=${this.cmap}&dem=${this.demOn()}`;
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
    this.profSlots = this.paramActive && slots && slots.ok ? slots : null;

    if (!data.ok) return;
    this.profData = data;
    this._drawProfiles();
  }

  _setProfMix(on) {
    this.profMix = !!on;
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

    ctx.strokeStyle = "rgba(220, 235, 245, 0.1)";
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

    ctx.fillStyle = "rgba(220, 235, 245, 0.86)";
    ctx.font = "600 9.5px 'JetBrains Mono', monospace";
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

    if (panel.source === "full") this._drawSlotStems(ctx, xAt, yAt);
  }

  _drawSlotStems(ctx, xAt, yAt) {
    if (!this.profMix || !this.profSlots || !this.profData) return;
    if (this.profSlots.az !== this.profData.az || this.profSlots.rg !== this.profData.rg) return;

    const slots = this.profSlots.slots.filter((slot) => slot.amplitude > 0 && Number.isFinite(slot.mean) && Number.isFinite(slot.amplitude));
    if (!slots.length) return;

    let factor = 1;
    const mixture = this.profData.sources.param;
    if (this.profMode === "unit" && mixture) {
      const values = mixture.values.map((v) => (Number.isFinite(v) ? Math.max(v, 0) : 0));
      let area = 0;
      for (let i = 1; i < values.length; i++) area += 0.5 * (values[i] + values[i - 1]) * Math.abs(mixture.heights[i] - mixture.heights[i - 1]);
      factor = area > 0 ? 1 / area : 0;
    }

    slots.forEach((slot, index) => {
      const y = yAt(slot.mean);
      const x = xAt(slot.amplitude * factor);
      const color = TomogramView.SLOT_COLORS[index % TomogramView.SLOT_COLORS.length];

      ctx.strokeStyle = color;
      ctx.lineWidth = 1.4;
      ctx.beginPath();
      ctx.moveTo(xAt(0), y);
      ctx.lineTo(x, y);
      ctx.stroke();

      ctx.fillStyle = color;
      ctx.beginPath();
      ctx.arc(x, y, 2.2, 0, Math.PI * 2);
      ctx.fill();
    });
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
