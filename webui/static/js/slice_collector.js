"use strict";

class SliceCollectorView {
  static SOURCES = ["full", "param"];
  static AXES = ["range", "azimuth"];
  static LABELS = { full: "capon full", param: "parametrized" };
  static ITEM_KEYS = ["id", "source", "axis", "az", "rg", "space", "cmap"];
  static MAP_MAX_VH = 52;
  static BASKET_KEY = "slice-basket";
  static MAIL_TO_KEY = "slice-mail-to";
  static CONFIRM_MS = 3000;

  constructor(refs) {
    this.refs = refs;
    this.cubes = [];
    this.infos = new Map();
    this.selected = [];
    this.runStrip = null;
    this.axes = new Set(["range"]);
    this.sources = new Set(["full"]);
    this.space = "physical";
    this.shared = true;
    this.mapId = null;
    this.mapOk = false;
    this.focus = null;
    this.hover = null;
    this.hoverFrom = null;
    this.rows = [];
    this.cells = [];
    this.colors = null;
    this.debounceTimer = null;
    this.inputTimer = null;
    this.basket = this._loadBasket();
    this.basketOpen = false;
    this.mailSettings = null;
    this.exporting = false;
    this.clearTimer = null;

    refs.mapWrap.addEventListener("mousemove", (ev) => this._onMapMove(ev));
    refs.mapWrap.addEventListener("mouseleave", () => this._setHover(null, null));
    refs.mapWrap.addEventListener("click", (ev) => this._onMapClick(ev));
    refs.mapImg.addEventListener("load", () => this._onMapLoad());
    refs.mapImg.addEventListener("error", () => this._onMapError());
    refs.mapRunSel.addEventListener("change", () => this._setMapRun(refs.mapRunSel.value));

    refs.azInput.addEventListener("input", () => this._scheduleInputs());
    refs.rgInput.addEventListener("input", () => this._scheduleInputs());
    refs.addBtn.addEventListener("click", () => this._addCuts(this.focus));
    refs.cmapSel.addEventListener("change", () => this._schedule());

    refs.basketTog.addEventListener("click", () => this._toggleBasket());
    refs.basketClear.addEventListener("click", () => this._confirmClear());
    refs.collectBtn.addEventListener("click", () => this._export("save"));
    refs.mailBtn.addEventListener("click", () => this._export("mail"));
    refs.mailTo.addEventListener("change", () => localStorage.setItem(SliceCollectorView.MAIL_TO_KEY, refs.mailTo.value.trim()));

    refs.axesWrap.querySelectorAll(".cube-space").forEach((btn) => {
      btn.addEventListener("click", () => this._toggleMulti(this.axes, btn, btn.dataset.axis));
    });
    refs.sourcesWrap.querySelectorAll(".cube-space").forEach((btn) => {
      btn.addEventListener("click", () => this._toggleMulti(this.sources, btn, btn.dataset.source));
    });
    refs.spaceWrap.querySelectorAll(".cube-space").forEach((btn) => {
      btn.addEventListener("click", () => {
        refs.spaceWrap.querySelectorAll(".cube-space").forEach((b) => b.classList.toggle("is-active", b === btn));
        this.space = btn.dataset.space;
        this._schedule();
      });
    });
    refs.sharedWrap.querySelectorAll(".cube-space").forEach((btn) => {
      btn.addEventListener("click", () => {
        refs.sharedWrap.querySelectorAll(".cube-space").forEach((b) => b.classList.toggle("is-active", b === btn));
        this.shared = btn.dataset.scale === "shared";
        this._schedule();
        this._renderBasket();
      });
    });

    this._renderBasket();
  }

  enter() {
    this._refresh();
    this._loadMailSettings();
  }

  figureTag() {
    const point = this.focus || { az: 0, rg: 0 };
    return `az${String(point.az).padStart(4, "0")}_rg${String(point.rg).padStart(4, "0")}_${this.space}`;
  }

  _loadBasket() {
    try {
      const items = JSON.parse(localStorage.getItem(SliceCollectorView.BASKET_KEY) || "[]");
      return Array.isArray(items) ? items : [];
    } catch (e) {
      return [];
    }
  }

  async _refresh() {
    this.refs.hint.hidden = false;
    this.refs.hint.innerHTML = ThinkingOrb.busy("searching", "Loading saved cubes…");

    const data = await Api.get(`/api/cubes?base=${encodeURIComponent(ResultsSources.runs())}`);
    this.cubes = (data && data.cubes) || [];
    this.infos.clear();
    this.selected = this.selected.filter((id) => this.cubes.some((c) => c.id === id));
    this._renderStrip();
    this._renderBasket();

    if (!this.cubes.length) {
      this.refs.hint.textContent = (data && data.error) || "No preprocessing runs found under this base.";
      this.refs.stage.hidden = true;
      return;
    }

    await this._selectionChanged();
  }

  async _loadMailSettings() {
    if (this.mailSettings) return;

    const data = await Api.get("/api/slices/mail_settings");
    if (!data || !data.ok) {
      this.refs.mailBtn.title = `Mail settings unavailable: ${(data && data.error) || "no answer"}`;
      return;
    }

    this.mailSettings = data;
    if (!this.refs.mailTo.value) this.refs.mailTo.value = localStorage.getItem(SliceCollectorView.MAIL_TO_KEY) || data.recipient;
    this._syncExport();
  }

  _renderStrip() {
    if (!this.runStrip) {
      this.runStrip = new RunStrip(this.refs.strip, {
        multi    : true,
        stateFor : (cube) => this.selected.includes(cube.id),
        onPick   : (cube) => this._togglePick(cube.id),
      });
    }
    this.runStrip.render(this.cubes);
  }

  async _togglePick(id) {
    const at = this.selected.indexOf(id);
    if (at >= 0) this.selected.splice(at, 1);
    else this.selected.push(id);

    this._renderStrip();
    await this._selectionChanged();
  }

  async _selectionChanged() {
    await this._ensureInfos();
    this._updateHint();
    this._updateControls();
    this._syncMapRun();
    this._schedule();
  }

  async _ensureInfos() {
    const need = this.selected.filter((id) => !this.infos.has(id));
    await Promise.all(
      need.map(async (id) => {
        const info = await Api.get(`/api/slices/info?id=${encodeURIComponent(id)}`);
        if (info && info.ok) this.infos.set(id, info);
        else Toast.show((info && info.error) || "failed to read run info", "warn");
      })
    );
  }

  _activeInfos() {
    return this.selected.map((id) => this.infos.get(id)).filter(Boolean);
  }

  _updateHint() {
    const infos = this._activeInfos();
    const n = this.selected.length;
    this.refs.hint.hidden = false;

    if (!n) {
      this.refs.hint.textContent = "Click runs to select them · every selected run is cut at the same point.";
      return;
    }

    const extents = new Set(infos.map((i) => `${i.n_az}x${i.n_rg}`));
    let text = `${n} run${n === 1 ? "" : "s"} selected · click rows to add or remove them.`;
    if (extents.size > 1) text += " Runs differ in extent, so a cut beyond a smaller run is clamped to its edge.";
    this.refs.hint.textContent = text;
  }

  _updateControls() {
    this._syncStage();
  }

  _syncStage() {
    const picked = this._activeInfos().length > 0;
    this.refs.stage.hidden = !picked && !(this.basket.length && this.cubes.length);
    this.refs.mapWrap.closest(".sc-deck").hidden = !picked;
  }

  _syncMapRun() {
    const infos = this._activeInfos();
    const sel = this.refs.mapRunSel;

    sel.innerHTML = "";
    infos.forEach((info) => {
      const option = document.createElement("option");
      option.value = info.id;
      option.textContent = `${info.run} · ${info.stamp}`;
      sel.appendChild(option);
    });
    sel.hidden = infos.length < 2;

    if (!infos.length) {
      this.mapId = null;
      return;
    }

    const keep = infos.some((i) => i.id === this.mapId) ? this.mapId : infos[0].id;
    sel.value = keep;
    if (keep !== this.mapId) this._setMapRun(keep);
  }

  _setMapRun(id) {
    const info = this.infos.get(id);
    if (!info) return;

    this.mapId = id;
    this.mapOk = false;
    this.refs.mapWrap.style.width = `min(100%, ${((SliceCollectorView.MAP_MAX_VH * info.n_rg) / info.n_az).toFixed(2)}vh)`;
    this.refs.mapWrap.style.aspectRatio = `${info.n_rg} / ${info.n_az}`;
    this.refs.mapWrap.classList.remove("is-failed");
    this.refs.mapWrap.classList.add("is-loading");
    this.refs.mapImg.src = `/api/slices/primary?id=${encodeURIComponent(id)}`;

    this.refs.azInput.max = info.n_az - 1;
    this.refs.rgInput.max = info.n_rg - 1;
    this.refs.azRange.textContent = `0–${info.n_az - 1}`;
    this.refs.rgRange.textContent = `0–${info.n_rg - 1}`;

    const focus = this.focus || { az: Math.floor(info.n_az / 2), rg: Math.floor(info.n_rg / 2) };
    this._setFocus({ az: Math.min(focus.az, info.n_az - 1), rg: Math.min(focus.rg, info.n_rg - 1) });
  }

  _onMapLoad() {
    this.mapOk = true;
    this.refs.mapWrap.classList.remove("is-loading");
    this.refs.mapWrap.style.aspectRatio = "";
    this._renderMarks();
    this._show();
  }

  _onMapError() {
    if (!this.mapId) return;
    this.mapOk = false;
    this.refs.mapWrap.classList.remove("is-loading");
    this.refs.mapWrap.classList.add("is-failed");
    this.refs.cross.hidden = true;
    this.refs.coords.textContent = "This run has no primary SLC map (the console log names the reason) · type az and rg below instead.";
  }

  _toggleMulti(set, btn, key) {
    if (set.has(key)) {
      if (set.size === 1) return;
      set.delete(key);
      btn.classList.remove("is-active");
    } else {
      set.add(key);
      btn.classList.add("is-active");
    }
    this._schedule();
  }

  _schedule() {
    clearTimeout(this.debounceTimer);
    this.debounceTimer = setTimeout(() => {
      this._buildRows();
      this._show();
    }, 250);
  }

  _buildRows() {
    this.cells.forEach((cell) => {
      if (cell.bitmap && cell.bitmap.close) cell.bitmap.close();
    });
    this.rows = [];
    this.cells = [];
    this.refs.rows.innerHTML = "";
    this.colors = this._readColors();

    const infos = this._activeInfos();
    const axes = SliceCollectorView.AXES.filter((a) => this.axes.has(a));
    const sources = SliceCollectorView.SOURCES.filter((s) => this.sources.has(s));

    axes.forEach((axis) => {
      sources.forEach((source) => {
        const carriers = infos.filter((i) => i.sources.includes(source));
        if (!carriers.length) return;

        const clim = this.shared && this.space === "physical" ? this._sharedClim(carriers, source) : null;
        const row = { axis, source, clim, cells: [] };

        const root = document.createElement("section");
        root.className = "sc-row";

        const head = document.createElement("div");
        head.className = "sc-row__head";
        const title = document.createElement("h3");
        title.className = "sc-row__title";
        title.innerHTML = `${SharedCharts.esc(axis)} cut &middot; ${SharedCharts.esc(SliceCollectorView.LABELS[source])} `;
        row.sub = document.createElement("span");
        row.sub.className = "sc-row__sub";
        title.appendChild(row.sub);
        head.appendChild(title);

        row.addBtn = document.createElement("button");
        row.addBtn.type = "button";
        row.addBtn.className = "btn btn--mini";
        row.addBtn.addEventListener("click", () => this._toggleRow(row));
        head.appendChild(row.addBtn);
        root.appendChild(head);

        const track = document.createElement("div");
        track.className = "sc-row__track";
        carriers.forEach((info) => track.appendChild(this._buildCell(row, info, source, axis, clim)));
        root.appendChild(track);

        this.rows.push(row);
        this.refs.rows.appendChild(root);
      });
    });
  }

  _readColors() {
    const css = getComputedStyle(this.refs.stage);
    return {
      range   : css.getPropertyValue("--cut-range").trim(),
      azimuth : css.getPropertyValue("--cut-azimuth").trim(),
    };
  }

  _sharedClim(infos, source) {
    const pairs = infos.map((i) => i.intensity[source]).filter(Boolean);
    if (!pairs.length) return null;
    const lo = Math.min(...pairs.map((p) => p[0]));
    const hi = Math.max(...pairs.map((p) => p[1]));
    return hi > lo ? [lo, hi] : null;
  }

  _buildCell(row, info, source, axis, clim) {
    const root = document.createElement("figure");
    root.className = "sc-cell";

    const media = document.createElement("div");
    media.className = "sc-cell__media";
    const canvas = document.createElement("canvas");
    canvas.setAttribute("aria-label", `${info.run} ${axis} cut ${source}`);
    media.appendChild(canvas);

    const pick = document.createElement("button");
    pick.type = "button";
    pick.className = "sc-pick";
    media.appendChild(pick);
    root.appendChild(media);

    const cap = document.createElement("figcaption");
    cap.className = "sc-cell__cap";
    cap.title = info.id;
    cap.innerHTML =
      `<span class="sc-cell__run">${SharedCharts.esc(info.run)}</span>` +
      `<span class="sc-cell__stamp">${SharedCharts.esc(info.stamp)}</span>`;
    root.appendChild(cap);

    const cell = { info, source, axis, clim, root, canvas, pick, bitmap: null, drawnUrl: null, queued: null, fetching: false, marker: 0 };
    canvas.addEventListener("mousemove", (ev) => this._onCellMove(cell, ev));
    canvas.addEventListener("mouseleave", () => this._setHover(null, null));
    canvas.addEventListener("click", () => {
      if (this.hover) this._setFocus(this.hover);
    });
    pick.addEventListener("click", () => this._toggleCell(cell));

    row.cells.push(cell);
    this.cells.push(cell);
    return root;
  }

  _mapInfo() {
    return this.mapId ? this.infos.get(this.mapId) : null;
  }

  _onMapMove(ev) {
    const point = this._pointFromEvent(ev);
    if (point) this._setHover(point, "map");
  }

  _onMapClick(ev) {
    const point = this._pointFromEvent(ev);
    if (!point) return;
    if (!ev.target.closest(".sc-mark")) this._addCuts(point);
    this._setFocus(point);
  }

  _pointFromEvent(ev) {
    const info = this._mapInfo();
    if (!info || !this.mapOk) return null;

    const mark = ev.target.closest(".sc-mark");
    if (mark) return this._basketPoints()[Number(mark.dataset.idx)];

    const rect = this.refs.mapImg.getBoundingClientRect();
    const fx = (ev.clientX - rect.left) / rect.width;
    const fy = (ev.clientY - rect.top) / rect.height;

    return {
      az: Math.min(info.n_az - 1, Math.max(0, Math.floor(fy * info.n_az))),
      rg: Math.min(info.n_rg - 1, Math.max(0, Math.floor(fx * info.n_rg))),
    };
  }

  _onCellMove(cell, ev) {
    if (!this.focus) return;

    const rect = cell.canvas.getBoundingClientRect();
    const frac = Math.min(1, Math.max(0, (ev.clientX - rect.left) / rect.width));
    const n = cell.axis === "range" ? cell.info.n_az : cell.info.n_rg;
    const idx = Math.min(n - 1, Math.floor(frac * n));

    const point = cell.axis === "range" ? { az: idx, rg: this.focus.rg } : { az: this.focus.az, rg: idx };
    this._setHover(point, "slice");
  }

  _setHover(point, from) {
    if (point && this.hover && point.az === this.hover.az && point.rg === this.hover.rg) return;
    if (!point && !this.hover) return;
    this.hover = point;
    this.hoverFrom = from;
    this._show();
  }

  _scheduleInputs() {
    clearTimeout(this.inputTimer);
    this.inputTimer = setTimeout(() => {
      const info = this._mapInfo();
      if (!info) return;
      const az = Math.min(info.n_az - 1, this._num(this.refs.azInput));
      const rg = Math.min(info.n_rg - 1, this._num(this.refs.rgInput));
      this._setFocus({ az, rg }, false);
    }, 250);
  }

  _setFocus(point, syncInputs = true) {
    this.focus = { az: point.az, rg: point.rg };
    if (syncInputs) {
      this.refs.azInput.value = point.az;
      this.refs.rgInput.value = point.rg;
    }
    this._renderMarks();
    this._show();
  }

  _show() {
    const point = this.hover || this.focus;
    if (!point) return;

    this._placeCross(point);
    this._writeCoords(point);

    this.rows.forEach((row) => {
      const pos = row.axis === "range" ? `rg ${point.rg}` : `az ${point.az}`;
      row.sub.textContent = `${pos} · ${this.space}${row.clim ? " · shared scale" : ""}`;
    });
    this.cells.forEach((cell) => this._updateCell(cell, point));
    this._syncPicks(point);
  }

  _placeCross(point) {
    const info = this._mapInfo();
    if (!info || !this.mapOk) {
      this.refs.cross.hidden = true;
      return;
    }

    this.refs.cross.hidden = false;
    this.refs.cross.style.left = `${((Math.min(point.rg, info.n_rg - 1) + 0.5) / info.n_rg) * 100}%`;
    this.refs.cross.style.top = `${((Math.min(point.az, info.n_az - 1) + 0.5) / info.n_az) * 100}%`;
  }

  _writeCoords(point) {
    if (!this.mapOk && this.mapId && this.refs.mapWrap.classList.contains("is-failed")) return;

    const at = `az = ${point.az} · rg = ${point.rg}`;
    const held = this._basketPoints().findIndex((p) => p.az === point.az && p.rg === point.rg);
    const coords = this.refs.coords;
    coords.classList.toggle("is-pinned", !this.hover);

    if (this.hover && this.hoverFrom === "map") {
      coords.textContent = held >= 0 ? `${at} · point ${held + 1} is in the basket` : `${at} · click to put these cuts in the basket`;
    } else if (this.hover) {
      coords.textContent = `${at} · click to move the cuts here`;
    } else {
      coords.textContent = held >= 0 ? `showing ${at} · basket point ${held + 1}` : `showing ${at} · not in the basket`;
    }
  }

  _updateCell(cell, point) {
    const n = cell.axis === "range" ? cell.info.n_az : cell.info.n_rg;
    const at = cell.axis === "range" ? point.az : point.rg;
    cell.marker = (Math.min(at, n - 1) + 0.5) / n;

    const url = this._sliceUrl(cell.info.id, cell.source, cell.axis, point, this.space, this.refs.cmapSel.value, cell.clim);
    if (url === cell.drawnUrl) {
      this._paintCell(cell);
      return;
    }

    cell.queued = url;
    this._pump(cell);
  }

  _sliceUrl(id, source, axis, point, space, cmap, clim) {
    const az = axis === "azimuth" ? point.az : 0;
    const rg = axis === "range" ? point.rg : 0;

    let url = `/api/slices/slice?id=${encodeURIComponent(id)}&source=${source}&axis=${axis}&az=${az}&rg=${rg}&space=${space}&cmap=${encodeURIComponent(cmap)}`;
    if (clim) url += `&vmin=${clim[0]}&vmax=${clim[1]}`;
    return url;
  }

  async _pump(cell) {
    if (cell.fetching) return;
    cell.fetching = true;

    try {
      while (cell.queued) {
        const url = cell.queued;
        cell.queued = null;
        await this._fetchCell(cell, url);
      }
    } finally {
      cell.fetching = false;
    }
  }

  async _fetchCell(cell, url) {
    const skeleton = cell.bitmap ? null : setTimeout(() => cell.root.classList.add("is-loading"), 120);

    try {
      const res = await fetch(url).catch(() => null);
      const ok  = Boolean(res && res.ok);
      cell.root.classList.toggle("is-failed", !ok);
      if (!ok) {
        this._clearCell(cell);
        return;
      }

      const bitmap = await createImageBitmap(await res.blob());
      if (cell.bitmap && cell.bitmap.close) cell.bitmap.close();

      cell.bitmap = bitmap;
      cell.drawnUrl = url;
      this._paintCell(cell);
    } finally {
      clearTimeout(skeleton);
      cell.root.classList.remove("is-loading");
    }
  }

  _clearCell(cell) {
    if (cell.bitmap && cell.bitmap.close) cell.bitmap.close();
    cell.bitmap   = null;
    cell.drawnUrl = null;
    cell.canvas.getContext("2d").clearRect(0, 0, cell.canvas.width, cell.canvas.height);
  }

  _paintCell(cell) {
    const bitmap = cell.bitmap;
    const canvas = cell.canvas;
    if (!bitmap) return;

    if (canvas.width !== bitmap.width || canvas.height !== bitmap.height) {
      canvas.width = bitmap.width;
      canvas.height = bitmap.height;
    }

    const ctx = canvas.getContext("2d");
    ctx.drawImage(bitmap, 0, 0);

    const kx = canvas.width / Math.max(1, canvas.clientWidth);
    const ky = canvas.height / Math.max(1, canvas.clientHeight);
    const x = cell.marker * canvas.width;

    ctx.setLineDash([2 * ky, 3 * ky]);
    ctx.strokeStyle = "rgba(255, 255, 255, 0.9)";
    ctx.lineWidth = 3.2 * kx;
    ctx.beginPath();
    ctx.moveTo(x, 0);
    ctx.lineTo(x, canvas.height);
    ctx.stroke();

    ctx.strokeStyle = this.colors[cell.axis];
    ctx.lineWidth = 1.6 * kx;
    ctx.beginPath();
    ctx.moveTo(x, 0);
    ctx.lineTo(x, canvas.height);
    ctx.stroke();
    ctx.setLineDash([]);
  }

  _syncPicks(point) {
    const held = new Set(this.basket.map((item) => this._itemKey(item)));

    this.cells.forEach((cell) => {
      const inBasket = held.has(this._itemKey(this._item(cell.info, cell.source, cell.axis, point)));
      cell.pick.classList.toggle("is-in", inBasket);
      cell.pick.textContent = inBasket ? "in basket" : "+ basket";
      cell.pick.title = inBasket ? "Remove this slice from the basket" : "Put this slice in the basket";
    });

    this.rows.forEach((row) => {
      const all = row.cells.every((cell) => cell.pick.classList.contains("is-in"));
      row.addBtn.textContent = all ? "Remove row from basket" : "Add row to basket";
    });
  }

  _item(info, source, axis, point) {
    return { id: info.id, run: info.run, stamp: info.stamp, source, axis, az: point.az, rg: point.rg, space: this.space, cmap: this.refs.cmapSel.value };
  }

  _itemKey(item) {
    return SliceCollectorView.ITEM_KEYS.map((key) => item[key]).join("|");
  }

  _addCuts(point) {
    if (!point) return;

    const items = [];
    this._activeInfos().forEach((info) => {
      SliceCollectorView.SOURCES.filter((s) => this.sources.has(s) && info.sources.includes(s)).forEach((source) => {
        SliceCollectorView.AXES.filter((a) => this.axes.has(a)).forEach((axis) => items.push(this._item(info, source, axis, point)));
      });
    });

    const held = new Set(this.basket.map((item) => this._itemKey(item)));
    const fresh = items.filter((item) => !held.has(this._itemKey(item)));
    if (fresh.length) this._setBasket(this.basket.concat(fresh));
  }

  _toggleCell(cell) {
    const point = this.hover || this.focus;
    if (!point) return;
    this._toggleItems([this._item(cell.info, cell.source, cell.axis, point)]);
  }

  _toggleRow(row) {
    const point = this.hover || this.focus;
    if (!point) return;
    this._toggleItems(row.cells.map((cell) => this._item(cell.info, cell.source, cell.axis, point)));
  }

  _toggleItems(items) {
    const keys = new Set(items.map((item) => this._itemKey(item)));
    const held = new Set(this.basket.map((item) => this._itemKey(item)));
    const all = [...keys].every((key) => held.has(key));

    if (all) {
      this._setBasket(this.basket.filter((item) => !keys.has(this._itemKey(item))));
      return;
    }
    this._setBasket(this.basket.concat(items.filter((item) => !held.has(this._itemKey(item)))));
  }

  _setBasket(items) {
    this.basket = items;
    localStorage.setItem(SliceCollectorView.BASKET_KEY, JSON.stringify(items));

    this._renderBasket();
    this._renderMarks();
    this._show();
  }

  _basketPoints() {
    const seen = new Map();
    this.basket.forEach((item) => {
      const key = `${item.az}|${item.rg}`;
      if (!seen.has(key)) seen.set(key, { az: item.az, rg: item.rg });
    });
    return [...seen.values()];
  }

  _renderMarks() {
    const info = this._mapInfo();
    const focus = this.focus;
    this.refs.marks.innerHTML = "";
    if (!info) return;

    this._basketPoints().forEach((p, idx) => {
      const mark = document.createElement("i");
      mark.className = "sc-mark";
      mark.classList.toggle("is-active", Boolean(focus) && p.az === focus.az && p.rg === focus.rg);
      mark.dataset.idx = String(idx);
      mark.textContent = String(idx + 1);
      mark.title = `Basket point ${idx + 1} · az ${p.az} · rg ${p.rg} · click to show its cuts`;
      mark.style.left = `${((Math.min(p.rg, info.n_rg - 1) + 0.5) / info.n_rg) * 100}%`;
      mark.style.top = `${((Math.min(p.az, info.n_az - 1) + 0.5) / info.n_az) * 100}%`;
      this.refs.marks.appendChild(mark);
    });
  }

  _confirmClear() {
    if (!this.clearTimer) {
      this.refs.basketClear.textContent = "Click again to empty";
      this.refs.basketClear.classList.add("is-armed");
      this.clearTimer = setTimeout(() => this._disarmClear(), SliceCollectorView.CONFIRM_MS);
      return;
    }

    this._disarmClear();
    this._setBasket([]);
  }

  _disarmClear() {
    clearTimeout(this.clearTimer);
    this.clearTimer = null;
    this.refs.basketClear.textContent = "Empty basket";
    this.refs.basketClear.classList.remove("is-armed");
  }

  _toggleBasket() {
    this.basketOpen = !this.basketOpen;
    this._renderBasket();
  }

  _renderBasket() {
    const n = this.basket.length;
    const points = this._basketPoints();
    const runs = new Set(this.basket.map((item) => item.id));
    const listed = new Set(this.cubes.map((cube) => cube.id));
    const unlisted = this.cubes.length ? this.basket.filter((item) => !listed.has(item.id)).length : 0;

    let sum = "empty · click the map, or a slice's + basket button, to add cuts";
    if (n) {
      sum = `${n} slice${n === 1 ? "" : "s"} at ${points.length} point${points.length === 1 ? "" : "s"} from ${runs.size} run${runs.size === 1 ? "" : "s"}`;
      sum += ` · ${this.shared ? "shared" : "per-run"} colour scale`;
      if (unlisted) sum += ` · ${unlisted} from runs not listed under this runs root`;
    }
    this.refs.basketSum.textContent = sum;
    this.refs.basketSum.classList.toggle("is-warn", unlisted > 0);
    this.refs.basketCount.textContent = String(n);
    this.refs.basketCount.classList.toggle("is-full", n > 0);
    this.refs.basketClear.hidden = !n;
    this.refs.basketTog.hidden = !n;
    this.refs.basketTog.textContent = this.basketOpen ? "Hide slices" : "Show slices";
    this.refs.basketTog.setAttribute("aria-expanded", String(this.basketOpen));
    this.refs.basketBody.hidden = !this.basketOpen || !n;

    this._syncStage();
    this._syncExport();
    if (!this.basketOpen || !n) return;

    this.refs.basketBody.innerHTML = "";
    points.forEach((point, idx) => {
      const items = this.basket.filter((item) => item.az === point.az && item.rg === point.rg).sort((a, b) => this._itemOrder(a, b));
      this.refs.basketBody.appendChild(this._basketGroup(point, idx, items, listed));
    });
  }

  _itemOrder(a, b) {
    const axes = SliceCollectorView.AXES;
    const sources = SliceCollectorView.SOURCES;
    return (
      axes.indexOf(a.axis) - axes.indexOf(b.axis) ||
      sources.indexOf(a.source) - sources.indexOf(b.source) ||
      a.space.localeCompare(b.space) ||
      a.cmap.localeCompare(b.cmap) ||
      a.run.localeCompare(b.run) ||
      a.id.localeCompare(b.id)
    );
  }

  _basketGroup(point, idx, items, listed) {
    const group = document.createElement("div");
    group.className = "sc-bgroup";

    const head = document.createElement("div");
    head.className = "sc-bgroup__head";

    const at = document.createElement("button");
    at.type = "button";
    at.className = "sc-bgroup__at";
    at.title = "Show the cuts at this point";
    at.innerHTML = `<i class="sc-chip__n">${idx + 1}</i>az <b>${point.az}</b> rg <b>${point.rg}</b> <span>${items.length} slice${items.length === 1 ? "" : "s"}</span>`;
    at.addEventListener("click", () => this._setFocus(point));
    head.appendChild(at);

    const drop = document.createElement("button");
    drop.type = "button";
    drop.className = "fl-pixel__rm";
    drop.textContent = "×";
    drop.title = "Remove every slice at this point";
    drop.addEventListener("click", () => this._setBasket(this.basket.filter((item) => item.az !== point.az || item.rg !== point.rg)));
    head.appendChild(drop);
    group.appendChild(head);

    const list = document.createElement("div");
    list.className = "sc-bgroup__items";
    items.forEach((item) => list.appendChild(this._basketItem(item, listed)));
    group.appendChild(list);

    return group;
  }

  _basketItem(item, listed) {
    const fig = document.createElement("figure");
    fig.className = "sc-bitem";
    fig.dataset.nofig = "";
    fig.classList.toggle("is-stale", this.cubes.length > 0 && !listed.has(item.id));
    fig.title = item.id;

    const img = document.createElement("img");
    img.loading = "lazy";
    img.alt = "";
    img.src = this._sliceUrl(item.id, item.source, item.axis, item, item.space, item.cmap, null);
    fig.appendChild(img);

    const cap = document.createElement("figcaption");
    cap.innerHTML =
      `<span class="sc-bitem__run">${SharedCharts.esc(item.run)}</span>` +
      `<span class="sc-bitem__what">${SharedCharts.esc(item.axis)} · ${SharedCharts.esc(SliceCollectorView.LABELS[item.source])} · ${SharedCharts.esc(item.space)} · ${SharedCharts.esc(item.cmap)}</span>`;
    fig.appendChild(cap);

    const rm = document.createElement("button");
    rm.type = "button";
    rm.className = "fl-pixel__rm sc-bitem__rm";
    rm.textContent = "×";
    rm.title = "Remove this slice from the basket";
    rm.addEventListener("click", () => {
      const key = this._itemKey(item);
      this._setBasket(this.basket.filter((other) => this._itemKey(other) !== key));
    });
    fig.appendChild(rm);

    return fig;
  }

  _syncExport() {
    const empty = !this.basket.length;
    const ready = Boolean(this.mailSettings && this.mailSettings.ready);

    this.refs.collectBtn.disabled = empty || this.exporting;
    this.refs.mailBtn.disabled = empty || this.exporting || !ready;
    this.refs.mailBtn.title = this.mailSettings && !ready
      ? `Mailing needs ${this.mailSettings.password_env} in the machine profile env; add it and restart the console`
      : "Render the basket into a folder, zip it and mail it";
  }

  async _export(mode) {
    if (!this.basket.length || this.exporting) return;

    const body = {
      items: this.basket.map((item) => Object.fromEntries(SliceCollectorView.ITEM_KEYS.map((key) => [key, item[key]]))),
      shared: this.shared,
      name: this.refs.nameInput.value.trim(),
    };
    if (mode === "mail") {
      body.recipient = this.refs.mailTo.value.trim();
      body.note = this.refs.mailNote.value.trim();
    }

    this.exporting = true;
    this._syncExport();
    this.refs.msg.innerHTML = ThinkingOrb.busy("composing", mode === "mail" ? "rendering and mailing…" : "rendering figures…");

    const res = await Api.post(mode === "mail" ? "/api/slices/mail" : "/api/slices/collect", body);

    this.exporting = false;
    this._syncExport();

    if (!res.ok) {
      this.refs.msg.textContent = res.error || "export failed";
      Toast.show(res.error || "export failed", "warn");
      return;
    }

    const skipped = res.missing && res.missing.length ? ` · ${res.missing.length} run/source pairs skipped` : "";
    if (mode === "mail") {
      const split = res.volumes.length > 1 ? ` in ${res.volumes.length} messages` : "";
      const where = res.reused ? `sent from the saved folder ${res.dir}` : `saved to ${res.dir}`;
      this.refs.msg.textContent = `mailed ${res.files.length} figures to ${res.recipient}${split} · ${where}`;
      Toast.show(`Mailed ${res.files.length} slice figures to ${res.recipient}${skipped}`, "ok");
      return;
    }

    this.refs.msg.textContent = `${res.files.length} figures → ${res.dir}`;
    Toast.show(`Saved ${res.files.length} slice figures from ${res.runs} runs${skipped}`, "ok");
  }

  _num(input) {
    const v = parseInt(input.value, 10);
    return Number.isFinite(v) && v >= 0 ? v : 0;
  }
}

window.SliceCollectorView = SliceCollectorView;
