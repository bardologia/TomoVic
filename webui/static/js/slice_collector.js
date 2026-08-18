"use strict";

class SliceCollectorView {
  static SOURCES = ["full"];
  static LABELS = { full: "capon full" };

  constructor(refs) {
    this.refs = refs;
    this.cubes = [];
    this.infos = new Map();
    this.selected = [];
    this.runStrip = null;
    this.points = [];
    this.axes = new Set(["range"]);
    this.sources = new Set(["full"]);
    this.space = "physical";
    this.shared = true;
    this.debounceTimer = null;
    this.collecting = false;

    refs.azInput.addEventListener("input", () => this._schedule());
    refs.rgInput.addEventListener("input", () => this._schedule());
    refs.addBtn.addEventListener("click", () => this._addPoint());
    refs.clearBtn.addEventListener("click", () => {
      this.points = [];
      this._renderPoints();
    });
    refs.cmapSel.addEventListener("change", () => this._schedule());
    refs.collectBtn.addEventListener("click", () => this._collect());

    refs.axesWrap.querySelectorAll(".cube-space").forEach((btn) => {
      btn.addEventListener("click", () => this._toggleMulti(this.axes, btn, btn.dataset.axis));
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
      });
    });
  }

  enter() {
    this._refresh();
  }

  async _refresh() {
    this.refs.hint.hidden = false;
    this.refs.hint.textContent = "Loading saved cubes…";

    const data = await Api.get(`/api/cubes?base=${encodeURIComponent(ResultsSources.runs())}`);
    this.cubes = (data && data.cubes) || [];
    this.selected = this.selected.filter((id) => this.cubes.some((c) => c.id === id));
    this._renderStrip();

    if (!this.cubes.length) {
      this.refs.hint.textContent = (data && data.error) || "No saved cubes found. Run an inference with save_cubes=True first.";
      this.refs.stage.hidden = true;
      return;
    }

    await this._ensureInfos();
    this._updateHint();
    this._updateControls();
    this._schedule();
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
    await this._ensureInfos();
    this._updateHint();
    this._updateControls();
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
    const n = this.selected.length;
    this.refs.hint.hidden = false;
    this.refs.hint.textContent = n
      ? `${n} run${n === 1 ? "" : "s"} selected · click rows to add or remove them.`
      : "Click runs to select them · every selected run is cut at the same point.";
  }

  _updateControls() {
    const infos = this._activeInfos();
    this.refs.stage.hidden = !infos.length;
    if (!infos.length) return;

    const azMax = Math.min(...infos.map((i) => i.n_az)) - 1;
    const rgMax = Math.min(...infos.map((i) => i.n_rg)) - 1;
    this.refs.azRange.textContent = `0–${azMax}`;
    this.refs.rgRange.textContent = `0–${rgMax}`;
    this.refs.azInput.max = azMax;
    this.refs.rgInput.max = rgMax;
    if (this.refs.azInput.value === "") this.refs.azInput.value = Math.floor((azMax + 1) / 2);
    if (this.refs.rgInput.value === "") this.refs.rgInput.value = Math.floor((rgMax + 1) / 2);

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
    this.debounceTimer = setTimeout(() => this._renderPreview(), 250);
  }

  _renderPreview() {
    const infos = this._activeInfos();
    this.refs.rows.innerHTML = "";
    if (!infos.length) return;

    const az = this._num(this.refs.azInput);
    const rg = this._num(this.refs.rgInput);
    const cmap = this.refs.cmapSel.value;
    const axes = ["range", "azimuth"].filter((a) => this.axes.has(a));
    const sources = SliceCollectorView.SOURCES.filter((s) => this.sources.has(s));

    axes.forEach((axis) => {
      sources.forEach((source) => {
        const carriers = infos.filter((i) => i.sources.includes(source));
        if (!carriers.length) return;

        const clim = this.shared && this.space === "physical" ? this._sharedClim(carriers, source) : null;

        const row = document.createElement("section");
        row.className = "sc-row";

        const title = document.createElement("h3");
        title.className = "sc-row__title";
        const pos = axis === "range" ? `rg ${rg}` : `az ${az}`;
        title.innerHTML =
          `${SharedCharts.esc(axis)} cut &middot; ${SharedCharts.esc(SliceCollectorView.LABELS[source])} ` +
          `<span class="sc-row__sub">${SharedCharts.esc(pos)} &middot; ${SharedCharts.esc(this.space)}${clim ? " &middot; shared scale" : ""}</span>`;
        row.appendChild(title);

        const track = document.createElement("div");
        track.className = "sc-row__track";
        carriers.forEach((info) => {
          const cell = document.createElement("figure");
          cell.className = "sc-cell";

          const img = document.createElement("img");
          let url =
            `/api/slices/slice?id=${encodeURIComponent(info.id)}&source=${source}&axis=${axis}` +
            `&az=${az}&rg=${rg}&space=${this.space}&cmap=${encodeURIComponent(cmap)}`;
          if (clim) url += `&vmin=${clim[0]}&vmax=${clim[1]}`;
          img.src = url;
          img.alt = `${info.run} ${axis} ${source}`;
          img.loading = "lazy";
          cell.appendChild(img);

          const cap = document.createElement("figcaption");
          cap.className = "sc-cell__cap";
          cap.title = info.id;
          cap.innerHTML =
            `<span class="sc-cell__run">${SharedCharts.esc(info.run)}</span>` +
            `<span class="sc-cell__stamp">${SharedCharts.esc(info.stamp)}</span>`;
          cell.appendChild(cap);

          track.appendChild(cell);
        });
        row.appendChild(track);
        this.refs.rows.appendChild(row);
      });
    });
  }

  _sharedClim(infos, source) {
    const pairs = infos.map((i) => i.intensity[source]).filter(Boolean);
    if (!pairs.length) return null;
    const lo = Math.min(...pairs.map((p) => p[0]));
    const hi = Math.max(...pairs.map((p) => p[1]));
    return hi > lo ? [lo, hi] : null;
  }

  _addPoint() {
    const az = this._num(this.refs.azInput);
    const rg = this._num(this.refs.rgInput);
    if (this.points.some((p) => p.az === az && p.rg === rg)) return;
    this.points.push({ az, rg });
    this._renderPoints();
  }

  _renderPoints() {
    this.refs.points.innerHTML = "";
    this.points.forEach((p, idx) => {
      const chip = document.createElement("span");
      chip.className = "fl-pixel";
      chip.innerHTML = `az <b>${p.az}</b> rg <b>${p.rg}</b>`;
      const rm = document.createElement("button");
      rm.type = "button";
      rm.className = "fl-pixel__rm";
      rm.textContent = "×";
      rm.title = "Remove this point";
      rm.addEventListener("click", () => {
        this.points.splice(idx, 1);
        this._renderPoints();
      });
      chip.appendChild(rm);
      this.refs.points.appendChild(chip);
    });
    this.refs.clearBtn.hidden = !this.points.length;
  }

  async _collect() {
    const infos = this._activeInfos();
    if (!infos.length) {
      Toast.show("Select at least one run first.", "warn");
      return;
    }
    if (this.collecting) return;

    const fallback = [{ az: this._num(this.refs.azInput), rg: this._num(this.refs.rgInput) }];
    const body = {
      ids: infos.map((i) => i.id),
      points: this.points.length ? this.points : fallback,
      sources: SliceCollectorView.SOURCES.filter((s) => this.sources.has(s)),
      axes: ["range", "azimuth"].filter((a) => this.axes.has(a)),
      space: this.space,
      cmap: this.refs.cmapSel.value,
      shared: this.shared,
      name: this.refs.nameInput.value.trim(),
    };

    this.collecting = true;
    this.refs.collectBtn.disabled = true;
    this.refs.msg.textContent = "rendering figures…";

    const res = await Api.post("/api/slices/collect", body);

    this.collecting = false;
    this.refs.collectBtn.disabled = false;

    if (!res.ok) {
      this.refs.msg.textContent = res.error || "collection failed";
      Toast.show(res.error || "collection failed", "warn");
      return;
    }

    this.refs.msg.textContent = `${res.files.length} figures → ${res.dir}`;
    let note = `Collected ${res.files.length} slice figures from ${res.runs} runs`;
    if (res.missing && res.missing.length) note += ` · ${res.missing.length} run/source pairs skipped`;
    Toast.show(note, "ok");
  }

  _num(input) {
    const v = parseInt(input.value, 10);
    return Number.isFinite(v) && v >= 0 ? v : 0;
  }

}

window.SliceCollectorView = SliceCollectorView;
