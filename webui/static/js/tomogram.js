"use strict";

class TomogramSweep {
  constructor(refs, host) {
    this.host = host;
    this.axis = refs.axis;
    this.grid = refs.grid;
    this.atLabel = refs.at;
    this.fill = refs.fill;
    this.input = refs.input;
    this.rangeLabel = refs.range;
    this.playBtn = refs.play;
    this.panels = refs.panels || [];

    this.idx = 0;
    this.steps = 1;
    this.playing = false;
    this.token = 0;
    this.frameMs = 70;

    if (this.grid)    this.grid.addEventListener("wheel", (ev) => this._onWheel(ev), { passive: false });
    if (this.input)   this.input.addEventListener("change", () => this._onManual());
    if (this.playBtn) this.playBtn.addEventListener("click", () => this.toggle());
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
      await Promise.all([frame, this._sleep(this.frameMs)]);
      if (!this.playing) break;

      this.idx = next;
    }
  }

  _prefetch(idx) {
    this.panels.filter((panel) => !panel.root.hidden).forEach((panel) => this.host.cacheBitmap(this._url(panel.source, idx)));
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
    const url = this._url(panel.source, idx);
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
      const primary = meta.sources.includes("pred") ? "pred" : meta.sources[0];
      return Math.max(1, meta.n_elev[primary] || 1);
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

class TomogramParams {
  static SOURCE_LABELS = { pred: "pred", gt: "gt", error: "|pred − gt|" };
  static FIELD_LABELS  = { amp: "amplitude", mu: "mu [m]", sigma: "sigma [m]", count: "active slots" };

  constructor(refs, host) {
    this.host = host;
    this.sourceEl = refs.source;
    this.fieldEl = refs.field;
    this.slotEl = refs.slot;
    this.atEl = refs.at;
    this.canvas = refs.canvas;
    this.cross = refs.cross;
    this.cbar = refs.cbar;
    this.minEl = refs.min;
    this.maxEl = refs.max;
    this.coordsEl = refs.coords;
    this.tableEl = refs.table;
    this.openBtn = refs.open;

    this.meta = null;
    this.source = "pred";
    this.field = "amp";
    this.slot = 0;
    this.token = 0;
    this.picked = null;

    this.fieldEl.querySelectorAll(".cube-space").forEach((btn) => {
      btn.addEventListener("click", () => this._setField(btn.dataset.field));
    });

    this.canvas.addEventListener("click", (ev) => this._onClick(ev));
    this.openBtn.addEventListener("click", () => this._openCuts());
  }

  configure(meta) {
    this.meta = meta.params || null;
    this.picked = null;
    this.cross.hidden = true;
    this.openBtn.hidden = true;
    this.tableEl.innerHTML = "";
    this.coordsEl.textContent = "Click the map to read every Gaussian slot at that pixel.";

    if (!this.meta) return;

    const sources = [...this.meta.sources, ...(this.meta.error ? ["error"] : [])];
    if (!sources.includes(this.source)) this.source = sources[0];
    this.slot = Math.min(this.slot, this.meta.n_slots - 1);

    this._renderSourceBtns(sources);
    this._renderSlotBtns();
  }

  render() {
    if (!this.meta) return;
    this._syncBtns();
    this._fetchMap();
    this._updateLegend();
    if (this.picked) this._fetchPixel(this.picked.az, this.picked.rg);
  }

  _setSource(source) {
    if (source === this.source) return;
    this.source = source;
    this.render();
  }

  _setField(field) {
    if (field === this.field) return;
    this.field = field;
    this.render();
  }

  _setSlot(slot) {
    if (slot === this.slot) return;
    this.slot = slot;
    this.render();
  }

  _renderSourceBtns(sources) {
    this.sourceEl.innerHTML = "";
    sources.forEach((source) => {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "cube-space";
      btn.dataset.source = source;
      btn.textContent = TomogramParams.SOURCE_LABELS[source] || source;
      btn.addEventListener("click", () => this._setSource(source));
      this.sourceEl.appendChild(btn);
    });
  }

  _renderSlotBtns() {
    this.slotEl.innerHTML = "";
    for (let k = 0; k < this.meta.n_slots; k++) {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "cube-space";
      btn.dataset.slot = String(k);
      btn.textContent = `slot ${k}`;
      btn.addEventListener("click", () => this._setSlot(k));
      this.slotEl.appendChild(btn);
    }
  }

  _syncBtns() {
    this.sourceEl.querySelectorAll(".cube-space").forEach((btn) => {
      btn.classList.toggle("is-active", btn.dataset.source === this.source);
    });
    this.fieldEl.querySelectorAll(".cube-space").forEach((btn) => {
      btn.classList.toggle("is-active", btn.dataset.field === this.field);
    });
    this.slotEl.querySelectorAll(".cube-space").forEach((btn) => {
      btn.classList.toggle("is-active", Number(btn.dataset.slot) === this.slot);
      btn.disabled = this.field === "count";
    });

    const slotText = this.field === "count" ? "all slots" : `slot ${this.slot}`;
    this.atEl.textContent = `${TomogramParams.SOURCE_LABELS[this.source]} · ${TomogramParams.FIELD_LABELS[this.field]} · ${slotText}`;
  }

  async _fetchMap() {
    this.token += 1;
    const token = this.token;
    const url = `/api/cubes/param_map?id=${encodeURIComponent(this.host.selectedId)}&source=${this.source}&field=${this.field}&slot=${this.slot}`;

    try {
      const res = await fetch(url);
      if (!res.ok || token !== this.token) return;

      const bitmap = await createImageBitmap(await res.blob());
      if (token !== this.token) { if (bitmap.close) bitmap.close(); return; }

      if (this.canvas.width !== bitmap.width || this.canvas.height !== bitmap.height) {
        this.canvas.width = bitmap.width;
        this.canvas.height = bitmap.height;
      }
      this.canvas.getContext("2d").drawImage(bitmap, 0, 0);
    } catch (e) {
    }
  }

  _updateLegend() {
    const key = this.source === "error" ? `error_${this.field}` : this.field;
    const range = this.meta.ranges[key];
    if (!range) return;

    this.cbar.src = `/api/cubes/param_cbar?id=${encodeURIComponent(this.host.selectedId)}&source=${this.source}&field=${this.field}`;
    this.minEl.textContent = this.host._fmt(range[0]);
    this.maxEl.textContent = this.host._fmt(range[1]);
  }

  _onClick(ev) {
    if (!this.meta || !this.host.meta) return;

    const rect = this.canvas.getBoundingClientRect();
    const fx = (ev.clientX - rect.left) / rect.width;
    const fy = (ev.clientY - rect.top) / rect.height;
    const az = Math.min(this.host.meta.n_az - 1, Math.max(0, Math.floor(fy * this.host.meta.n_az)));
    const rg = Math.min(this.host.meta.n_rg - 1, Math.max(0, Math.floor(fx * this.host.meta.n_rg)));

    this.picked = { az, rg, fx, fy };
    this.cross.hidden = false;
    this.cross.style.left = `${fx * 100}%`;
    this.cross.style.top = `${fy * 100}%`;

    this._fetchPixel(az, rg);
  }

  async _fetchPixel(az, rg) {
    const data = await Api.get(`/api/cubes/params_at?id=${encodeURIComponent(this.host.selectedId)}&az=${az}&rg=${rg}`);
    if (!data || !data.ok) return;

    this.coordsEl.textContent = `az = ${data.az} · rg = ${data.rg} · threshold ${data.threshold}`;
    this.openBtn.hidden = false;
    this._renderTable(data);
  }

  _renderTable(data) {
    const sources = Object.keys(data.sources);

    let html = `<table class="cube-metrics cube-metrics--params"><thead><tr><th scope="col">slot</th>`;
    sources.forEach((source) => { html += `<th scope="col" colspan="3">${SharedCharts.esc(source)}</th>`; });
    html += `</tr><tr><th></th>`;
    sources.forEach(() => { html += `<th>amp</th><th>mu</th><th>sigma</th>`; });
    html += `</tr></thead><tbody>`;

    for (let k = 0; k < data.n_slots; k++) {
      html += `<tr><th scope="row">${k}</th>`;
      sources.forEach((source) => {
        const slot = data.sources[source][k];
        const cls = slot.active ? "" : ` class="is-inactive"`;
        const amp = slot.amp === null ? "–" : this.host._fmt(slot.amp);
        const mu = slot.active && slot.mu !== null ? this.host._fmt(slot.mu) : "–";
        const sigma = slot.active && slot.sigma !== null ? this.host._fmt(slot.sigma) : "–";
        html += `<td${cls}>${amp}</td><td${cls}>${mu}</td><td${cls}>${sigma}</td>`;
      });
      html += `</tr>`;
    }

    html += `</tbody></table>`;
    this.tableEl.innerHTML = html;
  }

  _openCuts() {
    if (!this.picked) return;
    this.host._setView("explorer");
    this.host._follow(this.picked, true);
    this.host._enterSlices(this.picked);
  }
}

class TomogramMetrics {
  constructor(refs, host) {
    this.host = host;
    this.layerEl = refs.layer;
    this.vminEl = refs.vmin;
    this.vmaxEl = refs.vmax;
    this.resetEl = refs.reset;
    this.modeEl = refs.mode;
    this.thrEl = refs.thr;
    this.thrValEl = refs.thrVal;
    this.alphaEl = refs.alpha;
    this.img = refs.img;
    this.cross = refs.cross;
    this.cbar = refs.cbar;
    this.minEl = refs.min;
    this.maxEl = refs.max;
    this.coordsEl = refs.coords;
    this.readoutEl = refs.readout;
    this.openBtn = refs.open;
    this.selCovEl = refs.selCov;
    this.selValEl = refs.selVal;
    this.selTabEl = refs.selTab;

    this.layers = [];
    this.layer = null;
    this.mode = "all";
    this.alpha = 0.75;
    this.picked = null;
    this.debounceTimer = null;
    this.hoverQueued = null;
    this.hoverFetching = false;
    this.selectiveTimer = null;

    if (this.selCovEl) this.selCovEl.addEventListener("input", () => this._onCoverage());

    this.vminEl.addEventListener("change", () => this._refresh());
    this.vmaxEl.addEventListener("change", () => this._refresh());
    this.resetEl.addEventListener("click", () => this._resetRange());
    this.modeEl.addEventListener("change", () => this._setMode(this.modeEl.value));
    this.thrEl.addEventListener("input", () => this._onThreshold());
    this.alphaEl.addEventListener("input", () => this._onAlpha());
    this.img.addEventListener("mousemove", (ev) => this._onHover(ev));
    this.img.addEventListener("click", (ev) => this._onClick(ev));
    this.openBtn.addEventListener("click", () => this._openCuts());
  }

  configure(meta) {
    this.layers = meta.metric_maps || [];
    this.picked = null;
    this.cross.hidden = true;
    this.openBtn.hidden = true;
    this.readoutEl.innerHTML = "";
    this.coordsEl.textContent = "Hover the map to read the value under the cursor; click to lock a pixel and read every layer.";

    if (!this.layers.length) {
      this.layer = null;
      return;
    }

    if (!this.layer || !this.layers.some((l) => l.key === this.layer.key)) this.layer = this.layers[0];
    else this.layer = this.layers.find((l) => l.key === this.layer.key);

    this._renderLayerBtns();
    this._resetControls();
  }

  render() {
    if (!this.layer) return;
    this._syncBtns();
    this._refresh();
    this._onCoverage();
  }

  _setLayer(key) {
    if (this.layer && key === this.layer.key) return;
    this.layer = this.layers.find((l) => l.key === key);
    this._resetControls();
    if (this.selTabEl) this.selTabEl.innerHTML = "";
    this.render();
    this._onCoverage();
  }

  _onCoverage() {
    if (!this.selCovEl || !this.layer) return;
    const pct = Number(this.selCovEl.value);
    this.selValEl.textContent = `${pct}%`;

    clearTimeout(this.selectiveTimer);
    this.selectiveTimer = setTimeout(() => this._fetchSelective(pct / 100), 220);
  }

  async _fetchSelective(coverage) {
    if (!this.layer) return;

    const data = await Api.get(
      `/api/cubes/selective?id=${encodeURIComponent(this.host.selectedId)}&key=${encodeURIComponent(this.layer.key)}&coverage=${coverage}`
    );
    if (!data.ok) {
      this.selTabEl.innerHTML = `<p class="cube-hint">${SharedCharts.esc(data.error || "selective metrics unavailable")}</p>`;
      return;
    }

    let html = `<table class="cube-metrics cube-metrics--params"><thead><tr>` +
      `<th scope="col">metric</th><th scope="col">kept ${(data.coverage * 100).toFixed(0)}%</th><th scope="col">full</th></tr></thead><tbody>`;
    data.rows.forEach((row) => {
      const kept = row.kept === null ? "–" : this.host._fmt(row.kept);
      html += `<tr><td>${row.label}</td><td>${kept}</td><td>${this.host._fmt(row.full)}</td></tr>`;
    });
    html += `</tbody></table>`;

    const cmp = data.direction === "high" ? "≥" : "≤";
    html += `<p class="cube-hint">${data.n_kept.toLocaleString()} of ${data.n_total.toLocaleString()} pixels kept (layer ${cmp} ${this.host._fmt(data.threshold)})</p>`;
    this.selTabEl.innerHTML = html;
  }

  _setMode(mode) {
    this.mode = mode;
    this.thrEl.disabled = mode === "all";
    this._syncThresholdLabel();
    this._refresh();
  }

  _resetControls() {
    this.vminEl.value = this._round(this.layer.vmin);
    this.vmaxEl.value = this._round(this.layer.vmax);
    this.mode = "all";
    this.modeEl.value = "all";
    this.thrEl.disabled = true;
    this.thrEl.value = 500;
    this._syncThresholdLabel();
  }

  _resetRange() {
    this.vminEl.value = this._round(this.layer.vmin);
    this.vmaxEl.value = this._round(this.layer.vmax);
    this._refresh();
  }

  _onThreshold() {
    this._syncThresholdLabel();
    this._refresh();
  }

  _onAlpha() {
    this.alpha = Number(this.alphaEl.value) / 100;
    this._refresh();
  }

  _threshold() {
    const frac = Number(this.thrEl.value) / 1000;
    return this.layer.vmin + frac * (this.layer.vmax - this.layer.vmin);
  }

  _syncThresholdLabel() {
    if (this.mode === "all") {
      this.thrValEl.textContent = "";
      return;
    }
    this.thrValEl.textContent = `${this.mode} ${this.host._fmt(this._threshold())}`;
  }

  _keepWindow() {
    if (this.mode === "below") return { keep_min: "-inf", keep_max: this._threshold() };
    if (this.mode === "above") return { keep_min: this._threshold(), keep_max: "inf" };
    return { keep_min: "-inf", keep_max: "inf" };
  }

  _renderLayerBtns() {
    this.layerEl.innerHTML = "";
    this.layers.forEach((layer) => {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "cube-space";
      btn.dataset.key = layer.key;
      btn.textContent = layer.label;
      btn.title = layer.key;
      btn.addEventListener("click", () => this._setLayer(layer.key));
      this.layerEl.appendChild(btn);
    });
  }

  _syncBtns() {
    this.layerEl.querySelectorAll(".cube-space").forEach((btn) => {
      btn.classList.toggle("is-active", this.layer && btn.dataset.key === this.layer.key);
    });
  }

  _refresh() {
    clearTimeout(this.debounceTimer);
    this.debounceTimer = setTimeout(() => this._draw(), 160);
  }

  _draw() {
    if (!this.layer) return;

    const { keep_min, keep_max } = this._keepWindow();
    const vmin = Number(this.vminEl.value);
    const vmax = Number(this.vmaxEl.value);

    const query = `id=${encodeURIComponent(this.host.selectedId)}&key=${encodeURIComponent(this.layer.key)}` +
      `&vmin=${vmin}&vmax=${vmax}&keep_min=${keep_min}&keep_max=${keep_max}&alpha=${this.alpha}`;
    this.img.src = `/api/cubes/metric_map?${query}`;

    this.cbar.src = `/api/cubes/cbar?cmap=viridis`;
    this.minEl.textContent = this.host._fmt(vmin);
    this.maxEl.textContent = this.host._fmt(vmax);
  }

  _pointFromEvent(ev) {
    const rect = this.img.getBoundingClientRect();
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
    if (!this.layer || !this.host.meta || this.picked) return;
    const point = this._pointFromEvent(ev);
    this.hoverQueued = point;
    this._hoverPump();
  }

  async _hoverPump() {
    if (this.hoverFetching) return;
    this.hoverFetching = true;

    while (this.hoverQueued) {
      const { az, rg } = this.hoverQueued;
      this.hoverQueued = null;
      const data = await Api.get(`/api/cubes/metric_at?id=${encodeURIComponent(this.host.selectedId)}&key=${encodeURIComponent(this.layer.key)}&az=${az}&rg=${rg}`);
      if (data && data.ok && !this.picked) {
        this.coordsEl.textContent = `az = ${data.az} · rg = ${data.rg} · ${this.layer.label} = ${data.value === null ? "–" : this.host._fmt(data.value)}`;
      }
    }

    this.hoverFetching = false;
  }

  _onClick(ev) {
    if (!this.layer || !this.host.meta) return;

    if (this.picked) {
      this.picked = null;
      this.cross.hidden = true;
      this.openBtn.hidden = true;
      this.readoutEl.innerHTML = "";
      this.coordsEl.textContent = "Hover the map to read the value under the cursor; click to lock a pixel and read every layer.";
      return;
    }

    const point = this._pointFromEvent(ev);
    this.picked = point;
    this.cross.hidden = false;
    this.cross.style.left = `${point.fx * 100}%`;
    this.cross.style.top = `${point.fy * 100}%`;
    this.coordsEl.textContent = `locked at az = ${point.az} · rg = ${point.rg} · click again to unlock`;
    this.openBtn.hidden = false;

    this._fetchReadout(point.az, point.rg);
  }

  async _fetchReadout(az, rg) {
    const jobs = this.layers.map((layer) =>
      Api.get(`/api/cubes/metric_at?id=${encodeURIComponent(this.host.selectedId)}&key=${encodeURIComponent(layer.key)}&az=${az}&rg=${rg}`)
    );
    const results = await Promise.all(jobs);

    let html = `<table class="cube-metrics cube-metrics--params"><tbody>`;
    this.layers.forEach((layer, i) => {
      const data = results[i];
      const value = data && data.ok && data.value !== null ? this.host._fmt(data.value) : "–";
      html += `<tr><th scope="row">${SharedCharts.esc(layer.label)}</th><td>${value}</td></tr>`;
    });
    html += `</tbody></table>`;

    this.readoutEl.innerHTML = html;
  }

  _openCuts() {
    if (!this.picked) return;
    this.host._setView("explorer");
    this.host._follow(this.picked, true);
    this.host._enterSlices(this.picked);
  }

  _round(value) {
    return Number(Number(value).toPrecision(5));
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
    const url = `/api/cubes/transect?id=${encodeURIComponent(this.host.selectedId)}&source=${panel.source}` +
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

class TomogramCloud {
  static VIRIDIS = [[68, 1, 84], [59, 82, 139], [33, 145, 140], [94, 201, 98], [253, 231, 37]];
  static CURVE_SOURCES = ["reduced", "full"];
  static MISSING = {
    gt      : "This run has no ground-truth parameter cube.",
    reduced : "This run has no Capon reduced cube.",
    full    : "The raw Capon tomogram is not available for this run.",
  };

  constructor(refs, host) {
    this.host = host;
    this.sourceEl = refs.source;
    this.colorEl = refs.color;
    this.thrEl = refs.thr;
    this.thrLabel = refs.thrLabel;
    this.thrValEl = refs.thrVal;
    this.maxEl = refs.max;
    this.demWrap = refs.demWrap;
    this.demEl = refs.dem;
    this.scaleWrap = refs.scaleWrap;
    this.scaleEl = refs.scale;
    this.atEl = refs.at;
    this.canvas = refs.canvas;

    this.source = "pred";
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

    this.sourceEl.querySelectorAll(".cube-space").forEach((btn) => {
      btn.addEventListener("click", () => this._setSource(btn.dataset.source));
    });
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
    const sources = this._sources(meta);
    this.available = sources.length > 0;
    if (!sources.includes(this.source)) this.source = sources[0] || "pred";
    this.points = null;
    this.demGrid = null;
    this.demWrap.hidden = !meta.dem;
    this.demEl.checked = false;
    this.scaleWrap.hidden = !meta.spacing;
    this._resetView(false);
    this._syncThresholdLabel();
  }

  _sources(meta = this.host.meta) {
    const out = meta.params ? meta.params.sources.slice() : [];
    TomogramCloud.CURVE_SOURCES.forEach((s) => { if (meta.sources.includes(s)) out.push(s); });
    return out;
  }

  _isParam() {
    return this.source === "pred" || this.source === "gt";
  }

  render() {
    this._syncBtns();
    if (!this.points) this._fetch();
    else this._draw();
  }

  _setSource(source) {
    if (source === this.source) return;
    if (!this._sources().includes(source)) {
      Toast.show(TomogramCloud.MISSING[source] || "This source is not available.", "warn");
      return;
    }
    this.source = source;
    this._syncBtns();
    this._syncThresholdLabel();
    this._fetch();
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
    if (source === "pred" || source === "gt") {
      const params = meta.params;
      const top = Math.max(params.ranges.amp[1], params.threshold * 10);
      return params.threshold * Math.pow(top / params.threshold, frac);
    }

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
    const meta = this.host.meta;
    if (!meta || (this._isParam() && !meta.params)) return;
    this.thrLabel.textContent = this._isParam() ? "amp ≥" : "int ≥";
    this.thrValEl.textContent = this.host._fmt(this._ampMin());
  }

  _syncBtns() {
    const sources = this._sources();
    this.sourceEl.querySelectorAll(".cube-space").forEach((btn) => {
      btn.classList.toggle("is-active", btn.dataset.source === this.source);
      btn.disabled = !sources.includes(btn.dataset.source);
    });
    this.colorEl.querySelectorAll(".cube-space").forEach((btn) => {
      btn.classList.toggle("is-active", btn.dataset.color === this.colorBy);
    });

    const binAxis = this.source === "full";
    this.scaleEl.disabled = binAxis;
    this.demEl.disabled = binAxis;
    this.scaleWrap.title = binAxis ? "The raw Capon cube has a bin elevation axis; 1:1 applies to metric sources only" : "Metres on all three axes — no height exaggeration";
    this.demWrap.title = binAxis ? "The DEM drape needs a metric elevation axis" : "Drape the cloud on the terrain: point height = DEM + elevation";
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

    const spacing = this.scaleEl.checked && !this.scaleEl.disabled && meta.spacing ? meta.spacing : null;
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

    const grid = this.demEl.checked && !this.demEl.disabled && this.demGrid ? this.demGrid.rows : null;

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
    const logAmp = this._isParam();
    let ampLo, ampHi;
    if (logAmp) {
      const params = meta.params;
      ampLo = Math.log(Math.max(params.threshold, 1e-6));
      ampHi = Math.log(Math.max(params.ranges.amp[1], params.threshold * 10));
    } else {
      [ampLo, ampHi] = meta.intensity[this.source];
    }

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
        ? ((logAmp ? Math.log(Math.max(amp, 1e-6)) : amp) - ampLo) / Math.max(ampHi - ampLo, 1e-6)
        : (mu - muLo) / zSpan;
      plot((rows[i + 1] - cx) * rgStep, (rows[i] - cy) * azStep, z * zScale, this._palette(t));
    }

    ctx.putImageData(image, 0, 0);

    const shown = rows.length / 4;
    const unit = logAmp ? "scatterers" : "voxels";
    const scaleNote = spacing
      ? ` · 1:1 in metres · az ${Math.round(meta.n_az * azStep)} m × rg ${Math.round(meta.n_rg * rgStep)} m`
      : "";
    this.atEl.textContent = `${shown.toLocaleString()} of ${Math.round(this.total).toLocaleString()} ${unit}${scaleNote} · drag to orbit · wheel to zoom · double-click to reset`;
  }
}

class TomogramView {
  static LABELS = { pred: "pred", predb: "pred B", diff: "A − B", gt: "gt", reduced: "capon reduced", full: "capon full" };
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
    this.sourcesEl = refs.sources;
    this.profilesEl = refs.profiles;
    this.profAt = refs.profAt;
    this.profMetricsEl = refs.profMetrics;
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
    this.ssimQueued = null;
    this.ssimFetching = false;
    this.view = "explorer";
    this.colors = {};
    this.visible = new Set();
    this.cmap = localStorage.getItem("cube-cmap") || "jet";
    this.bitmapCache = new Map();
    this.bitmapBytes = 0;

    this.sweeps = (refs.sweeps || []).map((sweep) => new TomogramSweep(sweep, this));
    this.params = refs.params ? new TomogramParams(refs.params, this) : null;
    this.metrics = refs.metrics ? new TomogramMetrics(refs.metrics, this) : null;
    this.transect = refs.transect ? new TomogramTransect(refs.transect, this) : null;
    this.cloud = refs.cloud ? new TomogramCloud(refs.cloud, this) : null;
    this.globe = refs.globe ? new TomogramGlobe(refs.globe, this) : null;

    this.mapWrap = this.topdown.closest(".cube-map__wrap");

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
    const data = await Api.get(`/api/cubes?base=${encodeURIComponent(ResultsSources.runs())}&cv=1`);
    if (!data || data.error) return;
    this.cubes = data.cubes || [];
    this._renderStrip();
  }

  async refresh() {
    this.hint.hidden = false;
    this.hint.textContent = "Loading saved cubes…";
    this.hint.classList.add("is-loading");

    const data = await Api.get(`/api/cubes?base=${encodeURIComponent(ResultsSources.runs())}&cv=1`);

    this.hint.classList.remove("is-loading");

    if (data.error) {
      this.hint.textContent = data.error;
      return;
    }

    this.cubes = data.cubes || [];
    this._renderStrip();

    if (!this.cubes.length) {
      this.hint.textContent = data.error || "No saved cubes found. Run an inference with save_cubes=True first.";
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
        extras   : (cube) => this._stripExtras(cube),
      });
    }
    this.runStrip.render(this.cubes);
  }

  _stripExtras(cube) {
    if (!this.meta || cube.id === this.selectedId) return [];

    const attached = this.meta.attached && this.meta.attached.id === cube.id;
    const vs = document.createElement("span");
    vs.className = "cube-run__vs" + (attached ? " is-on" : "");
    vs.setAttribute("role", "button");
    vs.title = attached ? "Detach this comparison" : "Compare against the loaded cube";
    vs.textContent = attached ? "detach" : "vs";
    vs.addEventListener("click", (ev) => {
      ev.stopPropagation();
      this._toggleAttach(cube.id);
    });
    return [vs];
  }

  async select(cubeId) {
    if (this.polling) {
      Toast.show("A cube is still loading.", "warn");
      return;
    }
    if (cubeId === this.selectedId && this.meta) return;

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
      if (panel.metric) panel.metric.textContent = "";
    });
    this.profQueued = null;
    this.profData = null;
    this.ssimQueued = null;
    this._clearProfMetrics();
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
    this._renderStrip();

    const res = await Api.post("/api/cubes/load", { id: cubeId });
    if (!res.ok) {
      this.hint.textContent = res.error || "Cube load failed.";
      this.hint.hidden = false;
      return;
    }

    this._setProgress(0, "loading");
    this.progress.hidden = false;
    await this._poll();
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
      pred    : css.getPropertyValue("--src-pred").trim(),
      predb   : css.getPropertyValue("--src-predb").trim(),
      diff    : css.getPropertyValue("--src-diff").trim(),
      gt      : css.getPropertyValue("--src-gt").trim(),
      reduced : css.getPropertyValue("--src-reduced").trim(),
      full    : css.getPropertyValue("--src-full").trim(),
      range   : css.getPropertyValue("--cut-range").trim(),
      azimuth : css.getPropertyValue("--cut-azimuth").trim(),
    };

    this._syncSpaceBtns();
    this._syncProfModeBtns();

    const kept = meta.sources.filter((s) => this.visible.has(s));
    this.visible = new Set(kept.length ? kept : meta.sources);
    this._renderSourceToggles();
    this._applyVisibility();

    this.hint.hidden = true;
    this.stage.hidden = false;
    this.mapWrap.classList.add("is-loading");
    this.topdown.src = `/api/cubes/primary?id=${encodeURIComponent(this.selectedId)}`;

    this._initCutBounds();
    this.sweeps.forEach((sweep) => sweep.configure());

    if (this.params) {
      this.params.configure(meta);
      const paramsBtn = this.modeBtns.find((btn) => btn.dataset.view === "params");
      if (paramsBtn) paramsBtn.hidden = !meta.params;
      if (!meta.params && this.view === "params") this._setView("explorer");
    }

    if (this.metrics) {
      this.metrics.configure(meta);
      const hasMaps = (meta.metric_maps || []).length > 0;
      const metricsBtn = this.modeBtns.find((btn) => btn.dataset.view === "metrics");
      if (metricsBtn) metricsBtn.hidden = !hasMaps;
      if (!hasMaps && this.view === "metrics") this._setView("explorer");
    }

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

    if (meta.mosaic && meta.mosaic.gaps.length) {
      const spans = meta.mosaic.gaps.map((gap) => `${gap[0]}-${gap[1]}`).join(", ");
      Toast.show(`no fold covers azimuth rows ${spans}: those stripes are blank for lack of data, not model failure`, "error");
    }

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

  async _toggleAttach(otherId) {
    if (!this.meta || !this.selectedId) return;

    const attached = this.meta.attached && this.meta.attached.id === otherId;
    const res = attached
      ? await Api.post("/api/cubes/detach", { id: this.selectedId })
      : await Api.post("/api/cubes/attach", { id: this.selectedId, other: otherId });

    if (!res || !res.ok) {
      Toast.show((res && res.error) || "Comparison attach failed.", "error");
      return;
    }

    this._refreshSources(res.cube);
    this._renderStrip();
    Toast.show(attached ? "Comparison detached." : "Comparison attached — pred B and A − B sources enabled.", "ok");
  }

  _refreshSources(meta) {
    this.meta = meta;
    this._clearBitmapCache();

    const kept = meta.sources.filter((s) => this.visible.has(s));
    this.visible = new Set(kept.length ? kept : meta.sources);
    ["predb", "diff"].forEach((source) => {
      if (meta.sources.includes(source)) this.visible.add(source);
    });

    this.panels.forEach((panel) => this._releasePanel(panel));

    this._renderSourceToggles();
    this._applyVisibility();
    this.sweeps.forEach((sweep) => sweep.configure());

    const sweep = this._sweepFor(this.view);
    if (sweep) sweep.render();
    if (this.point) this._drawSlices(this.point.az, this.point.rg);
    if (this.locked) this._queueProfiles(this.locked.az, this.locked.rg);
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
    if (!["explorer", "elevation", "azimuth", "range", "params", "metrics", "transect", "cloud", "globe"].includes(view) || view === this.view) return;

    this._stopSweeps();
    this.view = view;

    this.modeBtns.forEach((btn) => btn.classList.toggle("is-active", btn.dataset.view === view));
    this.viewEls.forEach((el) => { el.hidden = el.dataset.view !== view; });
    this._syncGlobeChrome();

    if (view === "params" && this.params && this.meta) {
      this.params.render();
      return;
    }
    if (view === "metrics" && this.metrics && this.meta) {
      this.metrics.render();
      return;
    }
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

  _renderSourceToggles() {
    this.sourcesEl.innerHTML = "";
    this.meta.sources.forEach((source) => {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "cube-source";
      btn.dataset.source = source;
      btn.innerHTML = `<i class="cube-dot" data-source="${source}"></i>${TomogramView.LABELS[source]}`;
      btn.addEventListener("click", () => this._toggleSource(source));
      this.sourcesEl.appendChild(btn);
    });
  }

  _toggleSource(source) {
    if (this.visible.has(source)) {
      if (this.visible.size === 1) {
        Toast.show("At least one source must stay visible.", "warn");
        return;
      }
      this.visible.delete(source);
    } else {
      this.visible.add(source);
    }

    this._applyVisibility();
    if (this.point) this._drawSlices(this.point.az, this.point.rg);
    this._drawProfiles();
  }

  _applyVisibility() {
    this.panels.forEach((panel) => {
      panel.root.hidden = !this.visible.has(panel.source);
    });
    this.profPanels.forEach((panel) => {
      panel.root.hidden = !this.visible.has(panel.source);
    });
    this.sourcesEl.querySelectorAll(".cube-source").forEach((btn) => {
      btn.classList.toggle("is-active", this.visible.has(btn.dataset.source));
    });
    if (this.profMetricsEl) {
      this.profMetricsEl.querySelectorAll("tr[data-source]").forEach((row) => {
        row.hidden = !this.visible.has(row.dataset.source);
      });
    }
    this.slicesEl.style.setProperty("--cube-rows", String(this.visible.size));

    this.sweeps.forEach((sweep) => sweep.applyVisibility());
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

    this._queueSsim(az, rg);
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

  _queueSsim(az, rg) {
    this.ssimQueued = { az, rg };
    this._ssimPump();
  }

  async _ssimPump() {
    if (this.ssimFetching || !this.ssimQueued) return;
    this.ssimFetching = true;

    while (this.ssimQueued) {
      const { az, rg } = this.ssimQueued;
      this.ssimQueued = null;
      await this._fetchSsim(az, rg);
    }

    this.ssimFetching = false;
  }

  async _fetchSsim(az, rg) {
    const space = this.space;

    const data = await Api.get(`/api/cubes/ssim?id=${encodeURIComponent(this.selectedId)}&az=${az}&rg=${rg}&space=${space}`);

    if (!data.ok) return;
    this._applySsim(data);
  }

  _applySsim(data) {
    this.panels.forEach((panel) => {
      if (!panel.metric) return;

      if (panel.source === "gt") {
        panel.metric.textContent = "reference";
        return;
      }

      const group = data[panel.axis] || {};
      const value = group[panel.source];
      panel.metric.textContent = value === undefined || value === null ? "SSIM –" : `SSIM ${value.toFixed(3)}`;
    });
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

    const data = await Api.get(`/api/cubes/profiles?id=${encodeURIComponent(this.selectedId)}&az=${az}&rg=${rg}`);

    clearTimeout(staleTimer);
    this.profPanels.forEach((panel) => panel.root.classList.remove("is-stale"));

    if (!data.ok) return;
    this.profData = data;
    this._drawProfiles();
  }

  _drawProfiles() {
    if (!this.profData) return;

    let shared = null;
    if (this.profMode === "unit") {
      shared = 0;
      this.profPanels.forEach((panel) => {
        if (panel.root.hidden) return;
        const series = this.profData.sources[panel.source];
        if (series) shared = Math.max(shared, ...this._scaledValues(series));
      });
      if (!shared) shared = 1;
    }

    this.profPanels.forEach((panel) => {
      if (panel.root.hidden) return;
      const series = this.profData.sources[panel.source];
      if (series) this._drawProfile(panel, series, shared);
    });

    this._fillProfMetrics();
  }

  _fillProfMetrics() {
    if (!this.profMetricsEl) return;

    const gt = this.profData && this.profData.sources.gt;

    ["pred", "predb", "reduced"].forEach((source) => {
      const row = this.profMetricsEl.querySelector(`tr[data-source="${source}"]`);
      if (!row) return;

      const series = this.profData && this.profData.sources[source];
      const scores = gt && series ? this._scoreCurve(series.values, gt.values) : null;

      ["mae", "mse", "r2"].forEach((key) => {
        const cell = row.querySelector(`td[data-k="${key}"]`);
        if (cell) cell.textContent = scores ? this._fmtMetric(scores[key], key) : "–";
      });
    });
  }

  _scoreCurve(values, ref) {
    const n = Math.min(values.length, ref.length);
    if (!n) return null;

    let sumAbs = 0, sumSq = 0, sumRef = 0;
    for (let i = 0; i < n; i++) {
      const d = values[i] - ref[i];
      sumAbs += Math.abs(d);
      sumSq  += d * d;
      sumRef += ref[i];
    }

    const mean = sumRef / n;
    let ssTot = 0;
    for (let i = 0; i < n; i++) ssTot += (ref[i] - mean) ** 2;

    return { mae: sumAbs / n, mse: sumSq / n, r2: 1 - sumSq / (ssTot + 1e-12) };
  }

  _fmtMetric(value, key) {
    if (!Number.isFinite(value)) return "–";
    if (key === "r2") return value.toFixed(3);
    return this._fmt(value);
  }

  _clearProfMetrics() {
    if (!this.profMetricsEl) return;
    this.profMetricsEl.querySelectorAll("td[data-k]").forEach((cell) => { cell.textContent = "–"; });
  }

  _drawProfile(panel, series, shared) {
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

    const heights = series.heights;
    const values = this._scaledValues(series);
    const n = values.length;
    if (n < 2) return;

    const padL = 8, padR = 8, padT = 16, padB = 8;
    const innerW = w - padL - padR;
    const innerH = h - padT - padB;
    const hMin = heights[0];
    const hMax = heights[n - 1];
    const span = hMax - hMin || 1;
    const vMax = shared || Math.max(...values) || 1;

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

    ctx.beginPath();
    ctx.moveTo(xAt(0), yAt(heights[0]));
    for (let i = 0; i < n; i++) ctx.lineTo(xAt(values[i]), yAt(heights[i]));
    ctx.lineTo(xAt(0), yAt(heights[n - 1]));
    ctx.closePath();
    ctx.globalAlpha = 0.12;
    ctx.fillStyle = this.colors[panel.source] || "#555";
    ctx.fill();
    ctx.globalAlpha = 1;

    ctx.beginPath();
    for (let i = 0; i < n; i++) {
      if (i === 0) ctx.moveTo(xAt(values[i]), yAt(heights[i]));
      else ctx.lineTo(xAt(values[i]), yAt(heights[i]));
    }
    ctx.strokeStyle = this.colors[panel.source] || "#555";
    ctx.lineWidth = 1.6;
    ctx.stroke();

    let peak = 0;
    for (let i = 1; i < n; i++) if (values[i] > values[peak]) peak = i;
    ctx.beginPath();
    ctx.arc(xAt(values[peak]), yAt(heights[peak]), 2.6, 0, Math.PI * 2);
    ctx.fillStyle = this.colors[panel.source] || "#555";
    ctx.fill();

    ctx.fillStyle = "rgba(20, 25, 30, 0.55)";
    ctx.font = "9.5px 'JetBrains Mono', monospace";
    ctx.textAlign = "left";
    ctx.fillText(this._fmt(hMax), padL + 2, padT - 5);
    ctx.fillText(this._fmt(hMin), padL + 2, h - padB - 3);
    ctx.textAlign = "right";
    ctx.fillText(`peak ${this._fmt(values[peak])} @ ${this._fmt(heights[peak])}`, w - 4, padT - 5);
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
