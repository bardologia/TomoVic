"use strict";

class TomoVisInput {
  static angleDelta(event) {
    if (typeof event.wheelDeltaY === "number" && (event.wheelDeltaY || event.wheelDeltaX)) return { x: event.wheelDeltaX, y: event.wheelDeltaY };
    const scale = event.deltaMode === 1 ? 40 : (event.deltaMode === 2 ? 120 : 1.2);
    return { x: -event.deltaX * scale, y: -event.deltaY * scale };
  }

  static el(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined && text !== null) node.textContent = text;
    return node;
  }

  static mnemonicFree(text) {
    return String(text).replace(/&&/g, "\u0000").replace(/&/g, "").replace(/\u0000/g, "&");
  }

  static place(layer, node, clientX, clientY, { flipBottom = null, flipRight = null } = {}) {
    const origin = layer.getBoundingClientRect();
    node.style.left = `${clientX - origin.left}px`;
    node.style.top  = `${clientY - origin.top}px`;

    const rect   = node.getBoundingClientRect();
    const right  = window.innerWidth - 4;
    const bottom = window.innerHeight - 4;
    let x = clientX;
    let y = clientY;

    if (rect.right > right) x = flipRight !== null ? flipRight - rect.width : Math.max(4, right - rect.width);
    if (rect.bottom > bottom) y = flipBottom !== null && flipBottom - rect.height >= 4 ? flipBottom - rect.height : Math.max(4, bottom - rect.height);

    node.style.left = `${x - origin.left}px`;
    node.style.top  = `${y - origin.top}px`;
  }
}

class QtRegExpValidator {
  constructor(source) {
    this.source = source;
    this.tokens = this.parse(source);
  }

  parse(source) {
    const tokens = [];
    let i = 0;
    while (i < source.length) {
      const [match, next] = this.atom(source, i);
      const [min, max, after] = this.quantifier(source, next);
      tokens.push({ match, min, max });
      i = after;
    }
    return tokens;
  }

  atom(source, i) {
    const ch = source[i];
    if ("()|^$".includes(ch)) throw new Error(`QtRegExpValidator does not support ${ch} in ${source}`);
    if (ch === ".") return [() => true, i + 1];
    if (ch === "\\") return [this.escape(source[i + 1]), i + 2];
    if (ch === "[") return this.charClass(source, i);
    return [(c) => c === ch, i + 1];
  }

  escape(ch) {
    if (ch === "d") return (c) => c >= "0" && c <= "9";
    if (ch === "D") return (c) => !(c >= "0" && c <= "9");
    if (ch === "s") return (c) => /\s/.test(c);
    if (ch === "S") return (c) => !/\s/.test(c);
    if (ch === "w") return (c) => /\w/.test(c);
    if (ch === "W") return (c) => !/\w/.test(c);
    return (c) => c === ch;
  }

  charClass(source, start) {
    let i      = start + 1;
    const negate = source[i] === "^";
    if (negate) i += 1;

    const parts = [];
    while (i < source.length && (source[i] !== "]" || parts.length === 0)) {
      let lo = source[i];
      if (lo === "\\") {
        parts.push(this.escape(source[i + 1]));
        i += 2;
        continue;
      }
      if (source[i + 1] === "-" && source[i + 2] && source[i + 2] !== "]") {
        const hi = source[i + 2];
        parts.push((c) => c >= lo && c <= hi);
        i += 3;
        continue;
      }
      parts.push((c) => c === lo);
      i += 1;
    }
    if (source[i] !== "]") throw new Error(`QtRegExpValidator: unterminated class in ${source}`);
    return [(c) => parts.some((p) => p(c)) !== negate, i + 1];
  }

  quantifier(source, i) {
    const ch = source[i];
    if (ch === "?") return [0, 1, i + 1];
    if (ch === "*") return [0, Infinity, i + 1];
    if (ch === "+") return [1, Infinity, i + 1];
    if (ch === "{") {
      const end  = source.indexOf("}", i);
      const body = source.slice(i + 1, end);
      if (!body.includes(",")) return [Number(body), Number(body), end + 1];
      const [lo, hi] = body.split(",");
      return [lo === "" ? 0 : Number(lo), hi === "" ? Infinity : Number(hi), end + 1];
    }
    return [1, 1, i];
  }

  closure(states) {
    const out   = new Map();
    const stack = [...states];
    while (stack.length) {
      const [index, count] = stack.pop();
      const key = `${index}:${count}`;
      if (out.has(key)) continue;
      out.set(key, [index, count]);
      if (index < this.tokens.length && count >= this.tokens[index].min) stack.push([index + 1, 0]);
    }
    return [...out.values()];
  }

  validate(text) {
    let states = this.closure([[0, 0]]);
    for (const ch of text) {
      const next = [];
      for (const [index, count] of states) {
        if (index < this.tokens.length && count < this.tokens[index].max && this.tokens[index].match(ch)) next.push([index, count + 1]);
      }
      states = this.closure(next);
      if (states.length === 0) return "Invalid";
    }
    return states.some(([index]) => index === this.tokens.length) ? "Acceptable" : "Intermediate";
  }
}

class QtWidgetView {
  constructor(kit, kind, name, options) {
    this.kit      = kit;
    this.kind     = kind;
    this.name     = name;
    this.options  = options;
    this.onChange = options.onChange || null;
    this.enabled  = true;
    this.state    = {};
    this.el       = this.build();
    if (this.name) this.el.dataset.widget = this.name;
    if (options.minWidth) this.el.style.minWidth = `${options.minWidth}px`;
    if (options.maxWidth) this.el.style.maxWidth = `${options.maxWidth}px`;
    if (options.width) this.el.style.width = `${options.width}px`;
    if (options.title) this.el.title = options.title;
  }

  build() {
    return TomoVisInput.el("span");
  }

  set(state) {
    const previous = this.state;
    this.state     = { ...this.state, ...state };
    if ("enabled" in state) this.setEnabled(state.enabled);
    this.apply(this.state, previous);
  }

  apply() {}

  setEnabled(enabled) {
    this.enabled = Boolean(enabled);
    this.el.classList.toggle("is-disabled", !this.enabled);
    this.el.setAttribute("aria-disabled", String(!this.enabled));
    for (const node of this.focusables()) node.disabled = !this.enabled;
  }

  focusables() {
    return [];
  }

  editing() {
    return false;
  }

  changed(value, how) {
    if (this.name) this.kit.dispatch(this, value, how);
    if (this.onChange) this.onChange(value, how, this);
  }
}

class QtCheckBoxView extends QtWidgetView {
  build() {
    const root = TomoVisInput.el("span", "tv-check");
    root.setAttribute("role", "checkbox");
    root.tabIndex = 0;
    this.box = TomoVisInput.el("span", "tv-check__box");
    root.append(this.box);
    if (this.options.text) root.append(TomoVisInput.el("span", "tv-check__text", this.options.text));

    this.checked = false;
    root.addEventListener("click", () => this.toggle("click"));
    root.addEventListener("keydown", (event) => {
      if (event.key !== " ") return;
      event.preventDefault();
      this.toggle("key");
    });
    return root;
  }

  setEnabled(enabled) {
    super.setEnabled(enabled);
    this.el.tabIndex = this.enabled ? 0 : -1;
  }

  apply(state) {
    this.checked = Boolean(state.checked);
    this.el.classList.toggle("is-checked", this.checked);
    this.el.setAttribute("aria-checked", String(this.checked));
  }

  toggle(how) {
    if (!this.enabled) return;
    this.set({ checked: !this.checked });
    this.changed(this.checked, how);
  }
}

class QtSliderView extends QtWidgetView {
  static HANDLE        = 14;
  static REPEAT_DELAY  = 500;
  static REPEAT_PERIOD = 50;

  build() {
    if ((this.options.orientation || "horizontal") !== "horizontal") throw new Error("QtSliderView supports horizontal sliders only, as TomoVis uses");

    const root = TomoVisInput.el("span", "tv-slider");
    root.setAttribute("role", "slider");
    root.tabIndex = 0;
    this.groove = TomoVisInput.el("span", "tv-slider__groove");
    this.fill   = TomoVisInput.el("span", "tv-slider__fill");
    this.handle = TomoVisInput.el("span", "tv-slider__handle");
    this.groove.append(this.fill);
    root.append(this.groove, this.handle);

    this.minimum      = 0;
    this.maximum      = 99;
    this.value        = 0;
    this.singleStep   = 1;
    this.pageStep     = 10;
    this.dragging     = false;
    this.repeatTimer  = null;
    this.accumulated  = 0;
    this.clickOffset  = 0;
    this.pressValue   = 0;
    this.repeatAction = 0;

    root.addEventListener("pointerdown", (event) => this.press(event));
    root.addEventListener("pointermove", (event) => this.move(event));
    root.addEventListener("pointerup", (event) => this.release(event));
    root.addEventListener("pointercancel", (event) => this.release(event));
    root.addEventListener("keydown", (event) => this.key(event));
    root.addEventListener("wheel", (event) => this.wheel(event), { passive: false });
    root.addEventListener("auxclick", (event) => event.preventDefault());
    new ResizeObserver(() => this.render()).observe(root);
    return root;
  }

  setEnabled(enabled) {
    super.setEnabled(enabled);
    this.el.tabIndex = this.enabled ? 0 : -1;
    if (!this.enabled) this.stopRepeat();
  }

  apply(state) {
    if ("minimum" in state) this.minimum = state.minimum;
    if ("maximum" in state) this.maximum = state.maximum;
    if ("singleStep" in state) this.singleStep = state.singleStep;
    if ("pageStep" in state) this.pageStep = state.pageStep;
    if ("value" in state && !(this.name && this.editing() && this.kit.pending(this.name))) this.value = state.value;
    this.el.setAttribute("aria-valuemin", String(this.minimum));
    this.el.setAttribute("aria-valuemax", String(this.maximum));
    this.el.setAttribute("aria-valuenow", String(this.value));
    this.render();
  }

  editing() {
    return this.dragging || Boolean(this.repeatTimer);
  }

  span() {
    return Math.max(0, this.groove.clientWidth - QtSliderView.HANDLE);
  }

  positionFromValue(value) {
    const span = this.span();
    const min  = this.minimum;
    const max  = this.maximum;
    if (span <= 0 || value < min || max <= min) return 0;
    if (value > max) return span;
    const range = max - min;
    const p     = value - min;
    if (range > span) return Math.floor((2 * p * span + range) / (2 * range));
    const div = Math.floor(span / range);
    const mod = span % range;
    return p * div + Math.floor((2 * p * mod + range) / (2 * range));
  }

  valueFromPosition(pos) {
    const span = this.span();
    const min  = this.minimum;
    const max  = this.maximum;
    if (span <= 0 || pos <= 0) return min;
    if (pos >= span) return max;
    const range = max - min;
    if (span > range) return Math.floor((2 * pos * range + span) / (2 * span)) + min;
    const div = Math.floor(range / span);
    const mod = range % span;
    return pos * div + Math.floor((2 * pos * mod + span) / (2 * span)) + min;
  }

  render() {
    const pos = this.positionFromValue(this.value);
    this.handle.style.left = `${pos}px`;
    this.fill.style.width  = `${pos + QtSliderView.HANDLE / 2}px`;
  }

  bound(value) {
    return Math.max(this.minimum, Math.min(this.maximum, Math.round(value)));
  }

  setPosition(value, how) {
    const next = this.bound(value);
    if (next === this.value) return false;
    if (how === "drag" && this.options.onSliderMoved) this.options.onSliderMoved(next, this);
    this.value = next;
    this.el.setAttribute("aria-valuenow", String(this.value));
    this.render();
    this.changed(this.value, how);
    return true;
  }

  pointerPos(event) {
    return event.clientX - this.groove.getBoundingClientRect().left;
  }

  press(event) {
    if (!this.enabled) return;
    this.el.focus();
    const handleLeft = this.positionFromValue(this.value);
    const pos        = this.pointerPos(event);
    const onHandle   = pos >= handleLeft && pos < handleLeft + QtSliderView.HANDLE;

    if (event.button === 1) {
      event.preventDefault();
      this.setPosition(this.valueFromPosition(pos - QtSliderView.HANDLE / 2), "click");
      this.startDrag(event, QtSliderView.HANDLE / 2);
      return;
    }
    if (event.button !== 0) return;
    event.preventDefault();

    if (onHandle) {
      this.startDrag(event, pos - handleLeft);
      return;
    }

    this.pressValue = this.valueFromPosition(pos - QtSliderView.HANDLE / 2);
    if (this.pressValue === this.value) return;
    this.repeatAction = this.pressValue > this.value ? 1 : -1;
    this.el.setPointerCapture(event.pointerId);
    this.setPosition(this.value + this.repeatAction * this.pageStep, "click");
    this.repeatTimer = setTimeout(() => this.repeat(), QtSliderView.REPEAT_DELAY);
  }

  repeat() {
    const next = this.value + this.repeatAction * this.pageStep;
    if (next > this.pressValue - 2 * this.pageStep && next < this.pressValue + 2 * this.pageStep) {
      this.setPosition(this.pressValue, "click");
      this.stopRepeat();
      return;
    }
    this.setPosition(next, "click");
    this.repeatTimer = setTimeout(() => this.repeat(), QtSliderView.REPEAT_PERIOD);
  }

  stopRepeat() {
    clearTimeout(this.repeatTimer);
    this.repeatTimer  = null;
    this.repeatAction = 0;
  }

  startDrag(event, offset) {
    this.dragging    = true;
    this.clickOffset = offset;
    this.el.classList.add("is-down");
    this.el.setPointerCapture(event.pointerId);
  }

  move(event) {
    if (!this.dragging) return;
    this.setPosition(this.valueFromPosition(this.pointerPos(event) - this.clickOffset), "drag");
  }

  release(event) {
    const wasDragging = this.dragging;
    this.stopRepeat();
    this.dragging = false;
    this.el.classList.remove("is-down");
    if (this.el.hasPointerCapture(event.pointerId)) this.el.releasePointerCapture(event.pointerId);
    if (wasDragging && this.options.onSliderReleased) this.options.onSliderReleased(this.value, this);
  }

  key(event) {
    if (!this.enabled) return;
    const steps = { ArrowRight: this.singleStep, ArrowUp: this.singleStep, ArrowLeft: -this.singleStep, ArrowDown: -this.singleStep, PageUp: this.pageStep, PageDown: -this.pageStep };
    if (event.key in steps) {
      event.preventDefault();
      this.setPosition(this.value + steps[event.key], "key");
    } else if (event.key === "Home") {
      event.preventDefault();
      this.setPosition(this.minimum, "key");
    } else if (event.key === "End") {
      event.preventDefault();
      this.setPosition(this.maximum, "key");
    }
  }

  wheel(event) {
    if (!this.enabled) return;
    const angle    = TomoVisInput.angleDelta(event);
    const vertical = angle.y !== 0;
    const delta    = vertical ? angle.y : -angle.x;
    const offset   = delta / 120;
    let steps;

    if (event.ctrlKey || event.shiftKey) {
      steps = Math.max(-this.pageStep, Math.min(this.pageStep, Math.trunc(offset * this.pageStep)));
      this.accumulated = 0;
    } else {
      const stepsF = 3 * offset * this.singleStep;
      if (this.accumulated !== 0 && offset / this.accumulated < 0) this.accumulated = 0;
      this.accumulated += stepsF;
      steps = Math.max(-this.pageStep, Math.min(this.pageStep, Math.trunc(this.accumulated)));
      this.accumulated -= Math.trunc(this.accumulated);
      if (steps === 0) {
        if ((this.accumulated > 0 && this.value < this.maximum) || (this.accumulated < 0 && this.value > this.minimum)) event.preventDefault();
        else this.accumulated = 0;
        return;
      }
    }

    const moved = this.setPosition(this.value + steps, "wheel");
    if (moved) event.preventDefault();
    else this.accumulated = 0;
  }
}

class QtSpinBoxView extends QtWidgetView {
  static REPEAT_DELAY  = 400;
  static REPEAT_PERIOD = 60;

  build() {
    const root = TomoVisInput.el("span", "tv-spin");
    this.input = TomoVisInput.el("input", "tv-spin__input");
    this.input.type         = "text";
    this.input.spellcheck   = false;
    this.input.autocomplete = "off";
    this.input.inputMode    = "decimal";

    const buttons = TomoVisInput.el("span", "tv-spin__buttons");
    this.up   = TomoVisInput.el("button", "tv-spin__up");
    this.down = TomoVisInput.el("button", "tv-spin__down");
    for (const button of [this.up, this.down]) {
      button.type     = "button";
      button.tabIndex = -1;
    }
    this.up.setAttribute("aria-label", "Step up");
    this.down.setAttribute("aria-label", "Step down");
    buttons.append(this.up, this.down);
    root.append(this.input, buttons);

    this.minimum     = 0;
    this.maximum     = 99;
    this.value       = 0;
    this.decimals    = 0;
    this.singleStep  = this.options.step || 1;
    this.wheelRest   = 0;
    this.repeatTimer = null;
    this.before      = { text: "", start: 0, end: 0 };

    this.input.addEventListener("beforeinput", () => this.remember());
    this.input.addEventListener("input", () => this.typed());
    this.input.addEventListener("keydown", (event) => this.key(event));
    this.input.addEventListener("blur", () => this.fixup());
    root.addEventListener("wheel", (event) => this.wheel(event), { passive: false });
    this.up.addEventListener("pointerdown", (event) => this.startRepeat(event, 1));
    this.down.addEventListener("pointerdown", (event) => this.startRepeat(event, -1));
    for (const button of [this.up, this.down]) {
      button.addEventListener("pointerup", () => this.stopRepeat());
      button.addEventListener("pointerleave", () => this.stopRepeat());
      button.addEventListener("pointercancel", () => this.stopRepeat());
    }
    return root;
  }

  focusables() {
    return [this.input, this.up, this.down];
  }

  format(value) {
    return this.decimals > 0 ? Number(value).toFixed(this.decimals) : String(Math.round(value));
  }

  apply(state, previous) {
    if ("decimals" in state) this.decimals = state.decimals;
    if ("minimum" in state) this.minimum = state.minimum;
    if ("maximum" in state) this.maximum = state.maximum;
    if ("singleStep" in state) this.singleStep = state.singleStep;
    this.el.style.setProperty("--tv-spin-chars", String(Math.max(this.format(this.minimum).length, this.format(this.maximum).length)));
    if (!("value" in state)) return;

    const focused = document.activeElement === this.input;
    const echo    = state.value === this.value;
    if (focused && ((this.name && this.kit.pending(this.name)) || echo)) return;

    this.value       = state.value;
    this.input.value = this.format(state.value);
    this.renderSteps();
  }

  editing() {
    return document.activeElement === this.input;
  }

  renderSteps() {
    this.up.disabled   = !this.enabled || this.value >= this.maximum;
    this.down.disabled = !this.enabled || this.value <= this.minimum;
  }

  setEnabled(enabled) {
    super.setEnabled(enabled);
    this.renderSteps();
  }

  remember() {
    this.before = { text: this.input.value, start: this.input.selectionStart, end: this.input.selectionEnd };
  }

  validate(text) {
    const min  = this.minimum;
    const max  = this.maximum;
    const copy = text.trim();
    if (max !== min && (copy === "" || (min < 0 && copy === "-") || (max >= 0 && copy === "+"))) return ["Intermediate", null];

    const pattern = this.decimals > 0 ? /^[+-]?(\d+\.?\d*|\.\d+)$/ : /^[+-]?\d+$/;
    if (!pattern.test(copy)) return ["Invalid", null];
    if (this.decimals > 0 && copy.includes(".") && copy.length - copy.indexOf(".") - 1 > this.decimals) return ["Invalid", null];

    const num = Number(copy);
    if (num >= min && num <= max) return ["Acceptable", num];
    if (max === min) return ["Invalid", null];
    if ((num >= 0 && num > max) || (num < 0 && num < min)) return ["Invalid", null];
    return ["Intermediate", null];
  }

  typed() {
    const [state, num] = this.validate(this.input.value);
    if (state === "Invalid") {
      this.input.value = this.before.text;
      this.input.setSelectionRange(this.before.start, this.before.end);
      return;
    }
    if (state === "Acceptable") this.commit(num, "key");
  }

  commit(num, how) {
    const rounded = this.decimals > 0 ? Number(num.toFixed(this.decimals)) : Math.round(num);
    if (rounded === this.value) return;
    this.value = rounded;
    this.renderSteps();
    this.changed(this.value, how);
  }

  fixup() {
    const [state, num] = this.validate(this.input.value);
    if (state === "Acceptable") this.commit(num, "commit");
    this.input.value = this.format(this.value);
  }

  stepBy(steps, how) {
    if (!this.enabled) return false;
    const next = Math.max(this.minimum, Math.min(this.maximum, this.value + steps * this.singleStep));
    const rounded = this.decimals > 0 ? Number(next.toFixed(this.decimals)) : Math.round(next);
    this.input.value = this.format(rounded);
    if (rounded === this.value) return false;
    this.value = rounded;
    this.renderSteps();
    this.changed(this.value, how);
    return true;
  }

  key(event) {
    const steps = { ArrowUp: 1, ArrowDown: -1, PageUp: 10, PageDown: -10 };
    if (event.key in steps) {
      event.preventDefault();
      this.stepBy(steps[event.key], "key");
    } else if (event.key === "Enter") {
      this.fixup();
      if (this.options.onReturn) this.options.onReturn(this.value, this);
    }
  }

  wheel(event) {
    if (!this.enabled) return;
    event.preventDefault();
    this.wheelRest += TomoVisInput.angleDelta(event).y;
    const steps = Math.trunc(this.wheelRest / 120);
    this.wheelRest -= steps * 120;
    if (steps === 0) return;
    if ((steps > 0 && this.value >= this.maximum) || (steps < 0 && this.value <= this.minimum)) return;
    this.stepBy(event.ctrlKey ? steps * 10 : steps, "wheel");
  }

  startRepeat(event, direction) {
    if (!this.enabled || event.button !== 0) return;
    event.preventDefault();
    this.input.focus();
    this.stepBy(direction, "click");
    const loop = (delay) => {
      this.repeatTimer = setTimeout(() => {
        if (this.stepBy(direction, "click")) loop(QtSpinBoxView.REPEAT_PERIOD);
        else this.stopRepeat();
      }, delay);
    };
    loop(QtSpinBoxView.REPEAT_DELAY);
  }

  stopRepeat() {
    clearTimeout(this.repeatTimer);
    this.repeatTimer = null;
  }
}

class QtDoubleSpinBoxView extends QtSpinBoxView {
  build() {
    const root = super.build();
    this.decimals = this.options.decimals === undefined ? 2 : this.options.decimals;
    this.maximum  = 99.99;
    root.classList.add("tv-spin--double");
    return root;
  }
}

class QtComboBoxView extends QtWidgetView {
  static VISIBLE_ROWS = 10;
  static SEARCH_MS    = 400;

  build() {
    const root = TomoVisInput.el("span", "tv-combo");
    root.setAttribute("role", "combobox");
    root.setAttribute("aria-haspopup", "listbox");
    root.setAttribute("aria-expanded", "false");
    root.tabIndex = 0;
    this.label = TomoVisInput.el("span", "tv-combo__text");
    this.sizer = TomoVisInput.el("span", "tv-combo__sizer");
    this.sizer.setAttribute("aria-hidden", "true");
    root.append(this.label, this.sizer, TomoVisInput.el("span", "tv-combo__arrow"));

    this.items   = [...(this.options.items || [])];
    this.index   = this.items.length ? 0 : -1;
    this.popup   = null;
    this.hot     = -1;
    this.search  = "";
    this.searchT = 0;

    root.addEventListener("click", () => this.togglePopup());
    root.addEventListener("keydown", (event) => this.key(event));
    root.addEventListener("wheel", (event) => this.wheel(event), { passive: false });
    this.render();
    return root;
  }

  setItems(items) {
    this.items = [...items];
    if (this.index >= this.items.length) this.index = this.items.length - 1;
    this.render();
  }

  setEnabled(enabled) {
    super.setEnabled(enabled);
    this.el.tabIndex = this.enabled ? 0 : -1;
    if (!this.enabled) this.closePopup();
  }

  apply(state) {
    if ("items" in state) this.items = [...state.items];
    if ("index" in state) this.index = state.index;
    this.render();
  }

  render() {
    this.label.textContent = this.index >= 0 && this.index < this.items.length ? this.items[this.index] : (this.state.text || "");
    if (this.sized === this.items) return;
    this.sized = this.items;
    this.sizer.replaceChildren(...this.items.map((text) => TomoVisInput.el("span", "", text)));
  }

  get currentText() {
    return this.index >= 0 ? this.items[this.index] : "";
  }

  choose(index, how) {
    if (index < 0 || index >= this.items.length || index === this.index) return;
    this.index = index;
    this.render();
    this.changed(this.index, how);
  }

  key(event) {
    if (!this.enabled) return;
    if (this.popup) {
      this.popupKey(event);
      return;
    }
    const moves = { ArrowUp: -1, ArrowDown: 1, PageUp: -1, PageDown: 1 };
    if (event.key in moves) {
      event.preventDefault();
      if (event.altKey && event.key === "ArrowDown") this.openPopup();
      else this.choose(this.index + moves[event.key], "key");
    } else if (event.key === "Home") {
      event.preventDefault();
      this.choose(0, "key");
    } else if (event.key === "End") {
      event.preventDefault();
      this.choose(this.items.length - 1, "key");
    } else if (event.key === " " || event.key === "F4") {
      event.preventDefault();
      this.openPopup();
    } else if (event.key.length === 1 && !event.ctrlKey && !event.metaKey && !event.altKey) {
      const found = this.keyboardSearch(event.key);
      if (found >= 0) this.choose(found, "key");
    }
  }

  keyboardSearch(ch) {
    const now = performance.now();
    this.search  = now - this.searchT < QtComboBoxView.SEARCH_MS ? this.search + ch.toLowerCase() : ch.toLowerCase();
    this.searchT = now;
    const from   = this.popup ? this.hot : this.index;
    const start  = this.search.length === 1 ? from + 1 : from;
    for (let k = 0; k < this.items.length; k += 1) {
      const i = (start + k) % this.items.length;
      if (this.items[i].toLowerCase().startsWith(this.search)) return i;
    }
    return -1;
  }

  wheel(event) {
    if (!this.enabled || this.popup) return;
    event.preventDefault();
    const delta = TomoVisInput.angleDelta(event).y;
    if (delta === 0) return;
    this.choose(this.index + (delta > 0 ? -1 : 1), "wheel");
  }

  togglePopup() {
    if (!this.enabled) return;
    if (this.popup) this.closePopup();
    else this.openPopup();
  }

  openPopup() {
    if (this.popup || !this.enabled) return;
    const layer = this.kit.layer;
    const list  = TomoVisInput.el("div", "tv-combo__popup");
    list.setAttribute("role", "listbox");
    this.rows = this.items.map((text, i) => {
      const row = TomoVisInput.el("div", "tv-combo__option", text);
      row.setAttribute("role", "option");
      row.addEventListener("pointerenter", () => this.highlight(i, false));
      row.addEventListener("click", () => {
        this.closePopup();
        this.choose(i, "click");
      });
      list.append(row);
      return row;
    });
    layer.append(list);

    const rect = this.el.getBoundingClientRect();
    list.style.minWidth = `${rect.width}px`;
    const rowHeight = this.rows.length ? this.rows[0].getBoundingClientRect().height : 20;
    list.style.maxHeight = `${rowHeight * QtComboBoxView.VISIBLE_ROWS + 4}px`;
    TomoVisInput.place(layer, list, rect.left, rect.bottom, { flipBottom: rect.top });

    this.popup = list;
    this.highlight(this.index, true);
    this.el.setAttribute("aria-expanded", "true");
    this.el.classList.add("is-open");
    this.outside = (event) => {
      if (!list.contains(event.target) && !this.el.contains(event.target)) this.closePopup();
    };
    document.addEventListener("pointerdown", this.outside, true);
  }

  highlight(i, scroll) {
    if (!this.popup) return;
    this.hot = i;
    this.rows.forEach((row, k) => row.classList.toggle("is-hot", k === i));
    if (scroll && this.rows[i]) this.rows[i].scrollIntoView({ block: "nearest" });
  }

  popupKey(event) {
    const moves = { ArrowUp: -1, ArrowDown: 1, PageUp: -(QtComboBoxView.VISIBLE_ROWS - 1), PageDown: QtComboBoxView.VISIBLE_ROWS - 1 };
    if (event.key in moves) {
      event.preventDefault();
      this.highlight(Math.max(0, Math.min(this.items.length - 1, this.hot + moves[event.key])), true);
    } else if (event.key === "Home" || event.key === "End") {
      event.preventDefault();
      this.highlight(event.key === "Home" ? 0 : this.items.length - 1, true);
    } else if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      const chosen = this.hot;
      this.closePopup();
      this.choose(chosen, "key");
    } else if (event.key === "Escape" || event.key === "Tab" || event.key === "F4") {
      event.preventDefault();
      event.stopPropagation();
      this.closePopup();
    } else if (event.key.length === 1 && !event.ctrlKey && !event.metaKey && !event.altKey) {
      const found = this.keyboardSearch(event.key);
      if (found >= 0) this.highlight(found, true);
    }
  }

  closePopup() {
    if (!this.popup) return;
    document.removeEventListener("pointerdown", this.outside, true);
    this.popup.remove();
    this.popup = null;
    this.rows  = [];
    this.el.setAttribute("aria-expanded", "false");
    this.el.classList.remove("is-open");
  }
}

class QtLineEditView extends QtWidgetView {
  build() {
    const input = TomoVisInput.el("input", "tv-line");
    input.type         = "text";
    input.spellcheck   = false;
    input.autocomplete = "off";
    if (this.options.placeholder) input.placeholder = this.options.placeholder;
    this.input     = input;
    this.validator = this.options.validator ? new QtRegExpValidator(this.options.validator) : null;
    this.before    = { text: "", start: 0, end: 0 };
    this.text      = "";

    input.addEventListener("beforeinput", () => {
      this.before = { text: input.value, start: input.selectionStart, end: input.selectionEnd };
    });
    input.addEventListener("input", () => this.typed());
    input.addEventListener("keydown", (event) => {
      if (event.key === "Enter" && this.options.onReturn) this.options.onReturn(this.text, this);
    });
    return input;
  }

  focusables() {
    return [this.input];
  }

  apply(state, previous) {
    if ("placeholder" in state) this.input.placeholder = state.placeholder;
    if (!("text" in state)) return;

    const focused = document.activeElement === this.input;
    const echo    = state.text === this.text;
    if (focused && ((this.name && this.kit.pending(this.name)) || echo)) return;
    this.text        = state.text;
    this.input.value = state.text;
  }

  editing() {
    return document.activeElement === this.input;
  }

  validate(text) {
    return this.validator ? this.validator.validate(text) : "Acceptable";
  }

  typed() {
    if (this.validate(this.input.value) === "Invalid") {
      this.input.value = this.before.text;
      this.input.setSelectionRange(this.before.start, this.before.end);
      return;
    }
    if (this.input.value === this.text) return;
    this.text = this.input.value;
    this.changed(this.text, "key");
  }
}

class QtPushButtonView extends QtWidgetView {
  build() {
    const button = TomoVisInput.el("button", "tv-button");
    button.type = "button";
    if (this.options.icon) {
      const icon = TomoVisInput.el("img", "tv-button__icon");
      icon.src = this.options.icon;
      icon.alt = "";
      button.append(icon);
      button.classList.add("tv-button--icon");
    }
    this.textNode = TomoVisInput.el("span", "tv-button__text", this.options.text || "");
    button.append(this.textNode);
    if (this.options.ariaLabel) button.setAttribute("aria-label", this.options.ariaLabel);
    this.checked = false;
    button.addEventListener("click", () => this.click());
    return button;
  }

  focusables() {
    return [this.el];
  }

  apply(state) {
    if ("text" in state && !this.options.icon) this.textNode.textContent = state.text;
    if ("checked" in state) {
      this.checked = Boolean(state.checked);
      this.el.classList.toggle("is-checked", this.checked);
      this.el.setAttribute("aria-pressed", String(this.checked));
    }
  }

  click() {
    if (!this.enabled) return;
    if (this.options.checkable) this.set({ checked: !this.checked });
    this.changed(this.options.checkable ? this.checked : true, "click");
  }
}

class QtRadioView extends QtWidgetView {
  static ARROWS = new Set(["ArrowUp", "ArrowDown", "ArrowLeft", "ArrowRight"]);

  build() {
    const root = TomoVisInput.el("span", "tv-radio");
    root.setAttribute("role", "radio");
    root.tabIndex = 0;
    root.append(TomoVisInput.el("span", "tv-radio__dot"), TomoVisInput.el("span", "tv-radio__text", this.options.text || ""));
    this.group   = this.options.group || null;
    this.checked = false;
    root.addEventListener("click", () => this.click("click"));
    root.addEventListener("keydown", (event) => this.key(event));
    return root;
  }

  setEnabled(enabled) {
    super.setEnabled(enabled);
    this.el.tabIndex = this.enabled ? 0 : -1;
  }

  apply(state) {
    if ("checked" in state) {
      this.checked = Boolean(state.checked);
      this.el.classList.toggle("is-checked", this.checked);
      this.el.setAttribute("aria-checked", String(this.checked));
      if (this.checked) this.kit.exclusive(this);
    }
    if ("text" in state) this.el.querySelector(".tv-radio__text").textContent = state.text;
  }

  click(how) {
    if (!this.enabled) return;
    this.set({ checked: true });
    this.changed(true, how);
  }

  key(event) {
    if (!this.enabled) return;
    if (event.key === " ") {
      event.preventDefault();
      this.click("key");
      return;
    }
    if (!QtRadioView.ARROWS.has(event.key)) return;
    event.preventDefault();
    const candidate = this.moveTarget(event.key);
    if (!candidate) return;
    if (this.checked) candidate.click("key");
    candidate.el.focus();
  }

  static rect(element) {
    const box    = element.getBoundingClientRect();
    const x      = Math.round(box.left);
    const y      = Math.round(box.top);
    const right  = x + Math.round(box.width) - 1;
    const bottom = y + Math.round(box.height) - 1;
    return { x, y, right, bottom, cx: Math.trunc((x + right) / 2), cy: Math.trunc((y + bottom) / 2) };
  }

  moveTarget(key) {
    const target    = QtRadioView.rect(this.el);
    let   candidate = null;
    let   bestScore = -1;

    for (const button of this.kit.peers(this)) {
      if (button === this || !button.enabled || button.el.hidden || !button.el.isConnected) continue;
      const rect = QtRadioView.rect(button.el);

      let score;
      if (rect.x < target.right && target.x < rect.right && (key === "ArrowUp" || key === "ArrowDown")) {
        score = Math.abs(rect.cy - target.cy) * 65536 + Math.abs(rect.cx - target.cx);
      } else if (rect.y < target.bottom && target.y < rect.bottom && (key === "ArrowLeft" || key === "ArrowRight")) {
        score = Math.abs(rect.cx - target.cx) * 65536 + Math.abs(rect.cy - target.cy);
      } else {
        score = 1073741824 + (rect.cy - target.cy) ** 2 + (rect.cx - target.cx) ** 2;
      }

      if (score > bestScore && candidate) continue;

      const ahead = { ArrowUp: rect.cy < target.cy, ArrowDown: rect.cy > target.cy, ArrowLeft: rect.cx < target.cx, ArrowRight: rect.cx > target.cx }[key];
      if (ahead) {
        candidate = button;
        bestScore = score;
      }
    }
    return candidate;
  }
}

class QtGroupBoxView extends QtWidgetView {
  build() {
    const root = TomoVisInput.el("div", "tv-group");
    this.title = TomoVisInput.el("div", "tv-group__title", this.options.title || "");
    this.body  = TomoVisInput.el("div", "tv-group__body");
    root.append(this.title, this.body);
    return root;
  }

  apply(state) {
    if ("title" in state) this.title.textContent = state.title;
  }
}

class QtLabelView extends QtWidgetView {
  build() {
    return TomoVisInput.el("span", "tv-label", this.options.text || "");
  }

  apply(state) {
    if ("text" in state) this.el.textContent = state.text;
  }
}

class TomoVisMenu {
  static SUBMENU_DELAY = 225;
  static root          = null;

  constructor(ctx, items, { onClose = null, parent = null, ignore = null } = {}) {
    this.ctx        = ctx;
    this.items      = items;
    this.onClose    = onClose;
    this.parent     = parent;
    this.ignore     = ignore;
    this.el         = null;
    this.rows       = [];
    this.active     = -1;
    this.child      = null;
    this.childIndex = -1;
    this.timer      = null;
    this.onKeyOut   = null;
  }

  setItems(items) {
    this.items = items;
    if (this.el) this.render();
  }

  get isOpen() {
    return Boolean(this.el);
  }

  openBelow(element) {
    const rect = element.getBoundingClientRect();
    this.openAt(rect.left, rect.bottom, { flipBottom: rect.top });
  }

  openAt(x, y, flip = {}) {
    if (!this.parent) {
      if (TomoVisMenu.root && TomoVisMenu.root !== this) TomoVisMenu.root.close();
      TomoVisMenu.root = this;
    }
    if (this.el) this.dismiss(false);

    this.el = TomoVisInput.el("div", "tv-menu");
    this.el.setAttribute("role", "menu");
    this.el.tabIndex = -1;
    this.render();
    this.ctx.layer.append(this.el);
    TomoVisInput.place(this.ctx.layer, this.el, x, y, flip);

    this.el.addEventListener("pointerleave", () => {
      if (!this.child) this.setActive(-1, false);
    });
    this.el.addEventListener("keydown", (event) => this.key(event));
    if (!this.parent) {
      this.outside = (event) => {
        if (!this.contains(event.target) && !(this.ignore && this.ignore.contains(event.target))) this.close();
      };
      document.addEventListener("pointerdown", this.outside, true);
    }
    this.el.focus({ preventScroll: true });
  }

  render() {
    this.el.replaceChildren();
    this.rows = this.items.map((item, i) => this.row(item, i));
    this.rows.forEach((row) => this.el.append(row));
  }

  row(item, i) {
    if (item.separator) {
      const line = TomoVisInput.el("div", "tv-menu__separator");
      line.setAttribute("role", "separator");
      return line;
    }

    const row = TomoVisInput.el("div", "tv-menu__item");
    row.setAttribute("role", item.checkable ? (item.radio ? "menuitemradio" : "menuitemcheckbox") : "menuitem");
    const enabled = item.enabled !== false;
    row.classList.toggle("is-disabled", !enabled);
    row.setAttribute("aria-disabled", String(!enabled));
    if (item.checkable) row.setAttribute("aria-checked", String(Boolean(item.checked)));

    const mark = TomoVisInput.el("span", "tv-menu__mark");
    if (item.checkable) mark.classList.add(item.radio ? "is-radio" : "is-check");
    if (item.checkable && item.checked) mark.classList.add("is-on");

    if (item.widget) {
      row.classList.add("tv-menu__item--widget");
      row.append(mark, item.widget);
    } else {
      row.append(mark, TomoVisInput.el("span", "tv-menu__text", TomoVisInput.mnemonicFree(item.text || "")), TomoVisInput.el("span", "tv-menu__shortcut", item.shortcut || ""), TomoVisInput.el("span", item.submenu ? "tv-menu__arrow" : "tv-menu__noarrow"));
    }
    if (item.submenu) row.setAttribute("aria-haspopup", "menu");

    row.addEventListener("pointerenter", () => this.hover(i));
    row.addEventListener("click", (event) => {
      if (item.widget) return;
      event.stopPropagation();
      this.activate(i, true);
    });
    return row;
  }

  selectable(i) {
    const item = this.items[i];
    return item && !item.separator && item.enabled !== false;
  }

  hover(i) {
    clearTimeout(this.timer);
    const item       = this.items[i];
    const selectable = this.selectable(i);
    this.setActive(selectable ? i : -1, false);

    if (this.child && this.childIndex !== i) {
      this.timer = setTimeout(() => {
        this.closeChild();
        if (selectable && item.submenu) this.openChild(i);
      }, TomoVisMenu.SUBMENU_DELAY);
      return;
    }
    if (selectable && item.submenu && !this.child) this.timer = setTimeout(() => this.openChild(i), TomoVisMenu.SUBMENU_DELAY);
  }

  setActive(i, scroll) {
    this.active = i;
    this.rows.forEach((row, k) => row.classList.toggle("is-active", k === i && !this.items[k].separator));
    const item = i >= 0 ? this.items[i] : null;
    this.ctx.bus.emit("status", { text: item && !item.separator ? (item.statusTip || "") : "" });
    if (scroll && this.rows[i]) this.rows[i].scrollIntoView({ block: "nearest" });
  }

  openChild(i) {
    const item = this.items[i];
    if (!item || !item.submenu || item.enabled === false || !this.el) return;
    this.closeChild();
    const rect = this.rows[i].getBoundingClientRect();
    this.child      = new TomoVisMenu(this.ctx, item.submenu, { parent: this });
    this.childIndex = i;
    this.child.openAt(rect.right - 2, rect.top - 4, { flipRight: rect.left + 2 });
    this.child.el.addEventListener("pointerenter", () => {
      clearTimeout(this.timer);
      this.rows.forEach((row, k) => row.classList.toggle("is-active", k === i));
      this.active = i;
    });
    return this.child;
  }

  closeChild() {
    if (!this.child) return;
    this.child.dismiss(false);
    this.child      = null;
    this.childIndex = -1;
  }

  activate(i, byPointer) {
    const item = this.items[i];
    if (!item || item.separator || item.enabled === false) return;
    if (item.submenu) {
      const child = this.openChild(i);
      if (child && !byPointer) child.first();
      return;
    }
    if (item.widget) return;

    let checked = item.checked;
    if (item.checkable) {
      checked = item.radio ? true : !item.checked;
      if (item.radio) this.items.forEach((other) => { if (other.radio && other.radio === item.radio) other.checked = false; });
      item.checked = checked;
    }
    this.close();
    if (item.onTrigger) item.onTrigger(checked, item);
  }

  first() {
    const i = this.items.findIndex((_, k) => this.selectable(k));
    this.setActive(i, true);
    if (this.el) this.el.focus({ preventScroll: true });
  }

  step(direction) {
    const n = this.items.length;
    if (n === 0) return;
    let i = this.active;
    for (let k = 0; k < n; k += 1) {
      i = (i + direction + n) % n;
      if (this.selectable(i)) {
        this.setActive(i, true);
        return;
      }
    }
  }

  key(event) {
    if (this.child && this.child.isOpen) return;
    event.stopPropagation();
    if (event.key === "ArrowDown") {
      event.preventDefault();
      this.step(1);
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      this.step(-1);
    } else if (event.key === "ArrowRight") {
      event.preventDefault();
      const item = this.items[this.active];
      if (item && item.submenu && item.enabled !== false) this.activate(this.active, false);
      else this.keyOut("right");
    } else if (event.key === "ArrowLeft") {
      event.preventDefault();
      if (this.parent) {
        const parent = this.parent;
        parent.closeChild();
        parent.el.focus({ preventScroll: true });
      } else {
        this.keyOut("left");
      }
    } else if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      if (this.active >= 0) this.activate(this.active, false);
    } else if (event.key === "Escape") {
      event.preventDefault();
      if (this.parent) {
        const parent = this.parent;
        parent.closeChild();
        parent.el.focus({ preventScroll: true });
      } else {
        this.close();
      }
    }
  }

  keyOut(direction) {
    let menu = this;
    while (menu.parent) menu = menu.parent;
    if (menu.onKeyOut) menu.onKeyOut(direction);
  }

  contains(target) {
    if (this.el && this.el.contains(target)) return true;
    return Boolean(this.child && this.child.contains(target));
  }

  dismiss(notify) {
    clearTimeout(this.timer);
    this.closeChild();
    if (this.outside) document.removeEventListener("pointerdown", this.outside, true);
    this.outside = null;
    if (this.el) this.el.remove();
    this.el     = null;
    this.rows   = [];
    this.active = -1;
    if (notify && this.onClose) this.onClose();
  }

  close() {
    let menu = this;
    while (menu.parent) menu = menu.parent;
    if (TomoVisMenu.root === menu) TomoVisMenu.root = null;
    menu.dismiss(true);
    this.ctx.bus.emit("status", { text: "" });
  }
}

class TomoVisWidgets {
  static KINDS = {
    checkbox   : QtCheckBoxView,
    slider     : QtSliderView,
    spin       : QtSpinBoxView,
    doubleSpin : QtDoubleSpinBoxView,
    combo      : QtComboBoxView,
    line       : QtLineEditView,
    button     : QtPushButtonView,
    radio      : QtRadioView,
    group      : QtGroupBoxView,
    label      : QtLabelView,
  };

  static SERVER_KINDS = new Set(["checkbox", "slider", "spin", "doubleSpin", "combo", "line", "button"]);

  constructor(ctx) {
    this.ctx    = ctx;
    this.views  = new Map();
    this.groups = new Map();
    ctx.bus.on("snapshot", ({ snapshot }) => this.applySnapshot(snapshot));
  }

  get layer() {
    return this.ctx.layer;
  }

  create(kind, name, options) {
    const View = TomoVisWidgets.KINDS[kind];
    if (!View) throw new Error(`TomoVis widget kit has no kind ${kind}`);
    const view = new View(this, kind, name, options);
    if (kind === "radio" && options.group) {
      if (!this.groups.has(options.group)) this.groups.set(options.group, []);
      this.groups.get(options.group).push(view);
    }
    return view;
  }

  bound(kind, name, options = {}) {
    if (!TomoVisWidgets.SERVER_KINDS.has(kind)) throw new Error(`TomoVis widget kind ${kind} has no server events; use kit.local`);
    const view = this.create(kind, name, options);
    if (!this.views.has(name)) this.views.set(name, []);
    this.views.get(name).push(view);

    const snapshot = this.ctx.session.snapshot;
    if (snapshot) this.applyOne(view, snapshot.controls[name], name);
    return view;
  }

  local(kind, options = {}) {
    return this.create(kind, null, options);
  }

  menu(items, options = {}) {
    return new TomoVisMenu(this.ctx, items, options);
  }

  pending(name) {
    return this.ctx.session.pending(name) > 0;
  }

  peers(radio) {
    return radio.group ? this.groups.get(radio.group) : [radio];
  }

  exclusive(radio) {
    for (const peer of this.peers(radio)) {
      if (peer !== radio && peer.checked) peer.set({ checked: false });
    }
  }

  applySnapshot(snapshot) {
    const missing = [];
    for (const [name, views] of this.views) {
      const state = snapshot.controls[name];
      if (state === undefined) {
        missing.push(name);
        continue;
      }
      views.forEach((view) => this.applyOne(view, state, name));
    }
    if (missing.length) throw new Error(`TomoVis snapshot has no controls for ${missing.join(", ")}`);
  }

  applyOne(view, state, name) {
    if (state === undefined) throw new Error(`TomoVis snapshot has no control ${name}`);
    view.set(state);
  }

  dispatch(view, value, how) {
    const name = view.name;
    const send = (event, coalesce) => this.ctx.session.send(event, { coalesce }).catch((error) => this.ctx.session.raiseUnreported(error));

    if (view.kind === "checkbox") send({ type: "check", widget: name, checked: value }, null);
    else if (view.kind === "slider" || view.kind === "spin" || view.kind === "doubleSpin") send({ type: "value", widget: name, value }, `value:${name}`);
    else if (view.kind === "combo") send({ type: "index", widget: name, index: value }, null);
    else if (view.kind === "line") send({ type: "text", widget: name, text: value }, `text:${name}`);
    else if (view.kind === "button") send({ type: "click", widget: name }, null);
  }
}

window.TomoVisInput        = TomoVisInput;
window.QtRegExpValidator   = QtRegExpValidator;
window.QtWidgetView        = QtWidgetView;
window.QtCheckBoxView      = QtCheckBoxView;
window.QtSliderView        = QtSliderView;
window.QtSpinBoxView       = QtSpinBoxView;
window.QtDoubleSpinBoxView = QtDoubleSpinBoxView;
window.QtComboBoxView      = QtComboBoxView;
window.QtLineEditView      = QtLineEditView;
window.QtPushButtonView    = QtPushButtonView;
window.QtRadioView         = QtRadioView;
window.QtGroupBoxView      = QtGroupBoxView;
window.QtLabelView         = QtLabelView;
window.TomoVisMenu         = TomoVisMenu;
window.TomoVisWidgets      = TomoVisWidgets;
