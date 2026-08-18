"use strict";

class LaunchWidgetDom {
  static mini(label, onClick) {
    const btn       = document.createElement("button");
    btn.type        = "button";
    btn.className   = "btn btn--mini";
    btn.textContent = label;
    btn.addEventListener("click", onClick);
    return btn;
  }
}


class NumberField {

  constructor(view, leaf, short, spec = null) {
    this.view    = view;
    this.leaf    = leaf;
    this.short   = short || leaf.path.split(".").pop();
    this.integer = leaf.type === "int";
    this.default = Number.isFinite(Number(leaf.value)) ? Number(leaf.value) : 0;
    this.log     = false;
    this.range   = this._resolve(spec);
    this.input   = null;
    this.chips   = new Map();
    this.reset   = () => this._paint();
  }

  build() {
    const el     = document.createElement("div");
    el.className = "numfield";

    const top     = document.createElement("div");
    top.className = "numfield__top";

    const input      = document.createElement("input");
    input.className  = "cfg-edit__input numfield__input";
    input.type       = "number";
    input.step       = this.integer ? "1" : "any";
    input.spellcheck = false;
    this.input       = input;

    input.addEventListener("input", () => {
      const raw     = input.value;
      const invalid = this.integer && !/^-?\d+$/.test(raw);

      input.classList.toggle("is-invalid", raw !== "" && invalid);
      input.title = raw !== "" && invalid ? "not a whole number; this field takes an integer" : "";

      if (raw === "" || invalid) this.view._unsetValue(this.leaf);
      else this.view._setValue(this.leaf, Number(raw) === this.default ? this.leaf.value : raw);
      this._mark();
    });
    top.appendChild(input);
    el.appendChild(top);

    const presets     = document.createElement("div");
    presets.className = "numfield__presets";
    this.range.presets.forEach((value) => presets.appendChild(this._chip(value)));
    top.appendChild(presets);

    this._paint();
    return { el, input, reset: this.reset };
  }

  _resolve(spec) {
    const r = spec
      ? { min: spec.min, max: spec.max, step: spec.step || 1, log: Boolean(spec.log), presets: spec.presets ? spec.presets.slice() : this._spanPresets(spec) }
      : this._fallback();

    this.log = r.log;
    r.min = Math.min(r.min, this.default);
    r.max = Math.max(r.max, this.default);
    r.presets.push(this.default);
    r.presets = this._cleanPresets(r.presets, r);
    return r;
  }

  _spanPresets(spec) {
    const step = spec.step || 1;
    const span = spec.max - spec.min;
    const snap = (x) => spec.min + Math.round((x - spec.min) / step) * step;
    return [0, 0.25, 0.5, 0.75, 1].map((f) => snap(spec.min + span * f));
  }

  _fallback() {
    if (!this.integer && this.default > 0 && this.default <= 1) {
      return { min: 0, max: 1, step: 0.01, log: false, presets: [0, 0.25, 0.5, 0.75, 1] };
    }
    const base    = Math.abs(this.default) || (this.integer ? 10 : 1);
    const max     = this._nice(base * 4);
    const min     = this.default < 0 ? -max : 0;
    const span    = max - min || 1;
    const step    = this.integer ? 1 : Math.pow(10, Math.floor(Math.log10(span)) - 2) || 0.01;
    const presets = [min, min + span * 0.25, min + span * 0.5, min + span * 0.75, max].map((x) => (this.integer ? Math.round(x) : this._nice(x)));
    return { min, max, step, log: false, presets };
  }

  _nice(x) {
    if (x === 0) return 0;
    const unit = Math.pow(10, Math.floor(Math.log10(Math.abs(x)))) / 10;
    return Math.round(x / unit) * unit;
  }

  _cleanPresets(list, r) {
    const within = list.filter((x) => Number.isFinite(x) && x >= r.min - 1e-9 && x <= r.max + 1e-9);
    const seen   = new Map();
    within.forEach((x) => {
      const key = this.integer ? String(Math.round(x)) : this._fmt(x);
      if (!seen.has(key)) seen.set(key, Number(key));
    });
    return [...seen.values()].sort((a, b) => a - b).slice(0, 8);
  }

  _fmt(v) {
    if (this.integer) return String(Math.round(v));
    if (v === 0) return "0";
    return String(Number(v.toPrecision(this.log ? 2 : 6)));
  }

  _chip(value) {
    const chip       = document.createElement("button");
    chip.type        = "button";
    chip.className   = "numfield__chip";
    chip.textContent = this._fmt(value);
    chip.title       = `set ${this.short} = ${this._fmt(value)}`;
    chip.addEventListener("click", () => {
      this.input.value = this._fmt(value);
      const out = value === this.default ? this.leaf.value : this._fmt(value);
      this.view._setValue(this.leaf, out);
      this._mark();
    });
    this.chips.set(value, chip);
    return chip;
  }

  _mark() {
    const cur   = Number(this.view._effective(this.leaf));
    const dirty = this.view.dirty[this.leaf.path] !== undefined;
    this.input.classList.toggle("is-dirty", dirty);
    this.chips.forEach((chip, key) => {
      const tol = this.integer ? 0.5 : Math.max(1e-12, Math.abs(cur) * 1e-6);
      chip.classList.toggle("is-active", Number.isFinite(cur) && Math.abs(Number(key) - cur) < tol);
    });
  }

  _paint() {
    const eff = this.view._effective(this.leaf);
    this.input.value = eff === "None" ? "" : eff;
    this.input.classList.remove("is-invalid");
    this.input.title = "";
    this._mark();
  }
}


class MultiValueField {
  constructor(view, leaf, spec) {
    this.view  = view;
    this.leaf  = leaf;
    this.spec  = spec;
    this.el    = null;
    this.chips = null;
    this.input = null;
    this.count = null;
    this.hint  = null;
    this.reset = () => this._paint();
  }

  build() {
    this.el           = document.createElement("div");
    this.el.className = "picker multivalue" + (this.spec.wide ? " multivalue--wide" : "");

    const chips     = document.createElement("div");
    chips.className = "multivalue__chips";
    this.chips      = chips;
    this.el.appendChild(chips);

    if (this.spec.choices && this.spec.choiceGate) {
      const hint       = document.createElement("p");
      hint.className   = "multivalue__hint";
      hint.textContent = this.spec.choiceGate.hint;
      hint.hidden      = true;
      this.hint        = hint;
      this.el.appendChild(hint);
      this.view.repainters.push(this.reset);
    }

    if (!this.spec.choices) {
      const entry     = document.createElement("input");
      entry.className = "cfg-edit__input multivalue__entry" + (this.spec.wide ? " multivalue__entry--wide" : "");
      entry.type      = "text";
      entry.spellcheck = false;
      entry.placeholder = this.spec.placeholder || "add value, Enter";
      entry.addEventListener("keydown", (event) => this._onKey(event));
      entry.addEventListener("blur", () => this._commitEntry());
      this.input = entry;
      this.el.appendChild(entry);
    }

    const note     = document.createElement("p");
    note.className = "picker__note";
    this.count     = note;
    this.el.appendChild(note);

    this._paint();
    return { el: this.el, input: this.input || this.el, reset: this.reset };
  }

  _values() {
    try {
      const parsed = PythonLiteral.parse(this.view._effective(this.leaf));
      return Array.isArray(parsed) ? parsed.slice() : [];
    } catch (e) {
      return [];
    }
  }

  _cast(token) {
    if (!this.spec.numeric) return token;
    const value = Number(token);
    if (!Number.isFinite(value)) return null;
    return this.spec.integer ? Math.trunc(value) : value;
  }

  _emit(values) {
    this.view._setValue(this.leaf, PythonLiteral.render(values));
    this._paint();
  }

  _onKey(event) {
    if (event.key !== "Enter" && event.key !== ",") return;
    event.preventDefault();
    this._commitEntry();
  }

  _commitEntry() {
    if (!this.input) return;
    const tokens = this.input.value.split(",").map((part) => part.trim()).filter(Boolean);
    if (!tokens.length) return;

    const values = this._values();
    tokens.forEach((token) => {
      const cast = this._cast(token);
      if (cast !== null && !values.some((existing) => existing === cast)) values.push(cast);
    });

    this.input.value = "";
    this._emit(values);
  }

  _toggleChoice(value) {
    const values = this._values();
    const index  = values.indexOf(value);
    if (index >= 0) values.splice(index, 1);
    else            values.push(value);

    const ordered = this.spec.choices.map((choice) => choice.value).filter((choice) => values.includes(choice));
    this._emit(ordered);
  }

  _removeValue(value) {
    this._emit(this._values().filter((existing) => existing !== value));
  }

  _paint() {
    const values = this._values();
    this.chips.innerHTML = "";

    if (this.spec.choices) {
      const gate    = this.spec.choiceGate || null;
      const locked  = gate ? this.view._whenHolds(gate.when) : false;
      let   invalid = false;

      this.spec.choices.forEach((choice) => {
        const on      = values.includes(choice.value);
        const allowed = !locked || gate.only.includes(choice.value);
        invalid       = invalid || (on && !allowed);

        const chip      = document.createElement("button");
        chip.type       = "button";
        chip.className  = "multivalue__choice" + (on ? " is-on" : "") + (allowed ? "" : " is-locked");
        chip.disabled   = !allowed && !on;
        chip.textContent = choice.label;
        chip.title      = allowed ? `--${this.leaf.path} · ${choice.value}` : gate.hint;
        chip.setAttribute("aria-pressed", String(on));
        chip.addEventListener("click", () => this._toggleChoice(choice.value));
        this.chips.appendChild(chip);
      });

      if (this.hint) this.hint.hidden = !locked;
      if (this.count) this.count.classList.toggle("is-warn", invalid);
    } else {
      values.forEach((value) => {
        const chip      = document.createElement("span");
        chip.className  = "multivalue__chip";
        chip.title      = String(value);
        const label     = document.createElement("span");
        label.className = "multivalue__label";
        label.textContent = String(value);
        const remove    = document.createElement("button");
        remove.type     = "button";
        remove.className = "multivalue__x";
        remove.innerHTML = "&times;";
        remove.title    = "remove";
        remove.addEventListener("click", () => this._removeValue(value));
        chip.appendChild(label);
        chip.appendChild(remove);
        this.chips.appendChild(chip);
      });
    }

    if (this.count) {
      this.count.textContent = values.length
        ? `${values.length} value${values.length === 1 ? "" : "s"} · ${PythonLiteral.render(values)}`
        : (this.spec.empty || "select at least one value");
      this.count.classList.toggle("is-dirty", this.view.dirty[this.leaf.path] !== undefined);
    }
  }
}

window.LaunchWidgetDom = LaunchWidgetDom;
window.NumberField     = NumberField;
window.MultiValueField = MultiValueField;
