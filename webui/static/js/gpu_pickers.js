"use strict";

class GpuCardSelect {
  constructor(host, opts = {}) {
    this.host       = host;
    this.multi      = Boolean(opts.multi);
    this.allowEmpty = Boolean(opts.allowEmpty);
    this.onChange   = typeof opts.onChange === "function" ? opts.onChange : () => {};
    this.selected   = new Set((opts.initial || []).map(Number).filter(Number.isFinite));
    this.gpus       = [];
    this.chips      = new Map();
    this.manual     = null;
    this.loaded     = false;
  }

  async load() {
    const payload = await Api.get("/api/system");

    this.gpus   = Array.isArray(payload.gpus) ? payload.gpus : [];
    this.loaded = true;
    this._render();
    return this;
  }

  value() {
    return [...this.selected].sort((a, b) => a - b);
  }

  set(indices) {
    this.selected = new Set((indices || []).map(Number).filter(Number.isFinite));
    if (this.loaded) this._render();
  }

  _indices() {
    const detected = this.gpus.map((gpu) => Number(gpu.index)).filter(Number.isFinite);
    const merged   = new Set([...detected, ...this.selected]);
    return [...merged].sort((a, b) => a - b);
  }

  _render() {
    this.host.innerHTML = "";
    this.chips.clear();
    this.host.classList.add("gpu-picker__board");

    const indices = this._indices();
    if (!indices.length) {
      this._renderManual();
      return;
    }

    this.host.classList.add("gpu-picker__board--chips");
    indices.forEach((index) => this.host.appendChild(this._chip(index)));
    this._paint();
  }

  _chip(index) {
    const info = this.gpus.find((gpu) => Number(gpu.index) === index) || null;

    const chip        = document.createElement("button");
    chip.type         = "button";
    chip.className    = "gpu-chip";
    chip.title        = `cuda:${index}`;
    chip.dataset.tone = info ? (info.others ? "busy" : info.mine ? "mine" : "free") : "offline";

    const name = info ? info.name : "not detected";
    const meta = [];
    if (info && info.util != null)      meta.push(`${info.util}%`);
    if (info && info.mem_total != null) meta.push(`${Math.round(info.mem_used || 0)}/${Math.round(info.mem_total)} MiB`);

    chip.innerHTML =
      `<span class="gpu-chip__id">GPU ${index}</span>` +
      `<span class="gpu-chip__name">${name}</span>` +
      `<span class="gpu-chip__meta">${meta.join("  ·  ")}</span>`;

    chip.addEventListener("click", () => this._toggle(index));
    this.chips.set(index, chip);
    return chip;
  }

  _toggle(index) {
    if (!this.multi) {
      this.selected = new Set([index]);
    } else if (this.selected.has(index)) {
      if (!this.allowEmpty && this.selected.size <= 1) return;
      this.selected.delete(index);
    } else {
      this.selected.add(index);
    }
    this._paint();
    this.onChange(this.value());
  }

  _paint() {
    this.chips.forEach((chip, index) => {
      const on = this.selected.has(index);
      chip.classList.toggle("is-on", on);
      chip.setAttribute("aria-pressed", String(on));
    });
  }

  _renderManual() {
    this.host.classList.remove("gpu-picker__board--chips");

    const input      = document.createElement("input");
    input.className  = "cfg-edit__input";
    input.value      = this.value().join(", ");
    input.spellcheck = false;
    input.title      = this.multi
      ? "no GPUs detected on this host — enter device indices, e.g. 0, 1"
      : "no GPUs detected on this host — enter a device index, e.g. 0";
    input.addEventListener("input", () => {
      const parts = input.value.split(",").map((token) => Number(token.trim())).filter(Number.isFinite);
      this.selected = new Set(this.multi ? parts : parts.slice(0, 1));
      this.onChange(this.value());
    });

    this.manual = input;
    this.host.appendChild(input);
  }
}


class GpuPicker {
  constructor(view, leaf) {
    this.view     = view;
    this.leaf     = leaf;
    this.multi    = leaf.type === "list";
    this.el       = null;
    this.note     = null;
    this.cards    = null;
    this.inactive = false;
    this.why      = "";
    this.reset    = () => this._syncFromLeaf();
  }

  build() {
    this.el           = document.createElement("div");
    this.el.className  = "picker gpu-picker";

    const board = document.createElement("div");
    this.el.appendChild(board);

    const note     = document.createElement("p");
    note.className = "picker__note";
    note.textContent = "detecting GPUs...";
    this.note      = note;
    this.el.appendChild(note);

    this.cards = new GpuCardSelect(board, {
      multi    : this.multi,
      initial  : this._parse(this.view._effective(this.leaf)),
      onChange : (indices) => this._emit(indices),
    });
    this.cards.load().then(() => this._paintNote());

    return { el: this.el, input: this.el, reset: this.reset, setInactive: (on, why) => this.setInactive(on, why) };
  }

  setInactive(on, why) {
    this.inactive = Boolean(on);
    this.why      = why || "";
    if (this.el) this.el.classList.toggle("is-inactive", this.inactive);
    this._paintNote();
  }

  _parse(raw) {
    if (this.multi) {
      try {
        const parsed = PythonLiteral.parse(raw);
        return Array.isArray(parsed) ? parsed.map(Number).filter(Number.isFinite) : [];
      } catch (e) {
        return [];
      }
    }
    const value = Number(raw);
    return Number.isFinite(value) ? [value] : [];
  }

  _emit(indices) {
    const value = this.multi ? PythonLiteral.render(indices) : (indices.length ? String(indices[0]) : "");
    this.view._setValue(this.leaf, value);
    this._paintNote();
  }

  _syncFromLeaf() {
    if (this.cards) this.cards.set(this._parse(this.leaf.value));
    this._paintNote();
  }

  _paintNote() {
    if (!this.note) return;

    if (this.inactive) {
      this.note.textContent = this.why;
      this.note.classList.remove("is-dirty");
      return;
    }

    const ordered = this.cards ? this.cards.value() : [];
    const head    = this.multi ? `${ordered.length} GPU${ordered.length === 1 ? "" : "s"}` : `GPU ${ordered[0]}`;
    this.note.textContent = ordered.length
      ? `${head} selected · CUDA_VISIBLE_DEVICES=${ordered.join(",")}`
      : (this.multi ? "select at least one GPU" : "select a GPU");
    this.note.classList.toggle("is-dirty", this.view.dirty[this.leaf.path] !== undefined);
  }
}

window.GpuCardSelect = GpuCardSelect;
window.GpuPicker     = GpuPicker;
