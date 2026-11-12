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

  static plainPushButton(button) {
    button.addEventListener("keydown", (event) => {
      if (event.key === "Enter") event.preventDefault();
    });
    return button;
  }

  static noFocusButton(button) {
    button.tabIndex = -1;
    button.addEventListener("mousedown", (event) => event.preventDefault());
    return button;
  }

  static mnemonicFree(text) {
    return String(text).replace(/&&/g, "\u0000").replace(/&/g, "").replace(/\u0000/g, "&");
  }

  static viewport() {
    const root = document.documentElement;
    return { width: root.clientWidth, height: root.clientHeight };
  }

  static place(layer, node, clientX, clientY, { flipBottom = null, flipRight = null } = {}) {
    const origin = layer.getBoundingClientRect();
    node.style.left = "0px";
    node.style.top  = "0px";

    const size   = node.getBoundingClientRect();
    const view   = TomoVisInput.viewport();
    const right  = view.width - 4;
    const bottom = view.height - 4;
    let x = clientX;
    let y = clientY;

    if (clientX + size.width > right) x = flipRight !== null ? flipRight - size.width : Math.max(4, right - size.width);
    if (clientY + size.height > bottom) y = flipBottom !== null && flipBottom - size.height >= 4 ? flipBottom - size.height : Math.max(4, bottom - size.height);

    node.style.left = `${x - origin.left}px`;
    node.style.top  = `${y - origin.top}px`;
  }
}

class QtFontMetrics {
  static WINDOW  = { family: "'Noto Serif', serif", px: 14 };
  static APP     = { family: "'Noto Sans', sans-serif", px: 17 };
  static context = null;
  static ratios  = new Map();

  static css(font, px = font.px) {
    return `${px}px ${font.family}`;
  }

  static measure(text, font, px = font.px) {
    if (!QtFontMetrics.context) QtFontMetrics.context = document.createElement("canvas").getContext("2d");
    QtFontMetrics.context.font = QtFontMetrics.css(font, px);
    return QtFontMetrics.context.measureText(text);
  }

  static advance(text, font) {
    let floored = 0;
    let plain   = 0;
    for (const ch of text) {
      const width  = QtFontMetrics.measure(ch, font).width;
      plain       += width;
      floored     += Math.floor(width * 64 + 1e-6) / 64;
    }
    return floored + QtFontMetrics.measure(text, font).width - plain;
  }

  static horizontalAdvance(text, font) {
    return Math.round(QtFontMetrics.advance(text, font));
  }

  static widest(texts, font) {
    return Math.max(0, ...texts.map((text) => QtFontMetrics.horizontalAdvance(text, font)));
  }

  static labelWidth(text, font) {
    const m = QtFontMetrics.measure(text, font);
    return Math.ceil(Math.max(m.width, m.actualBoundingBoxRight) - 1e-6);
  }

  static height(font) {
    if (!QtFontMetrics.ratios.has(font.family)) {
      const m = QtFontMetrics.measure("0", font, 1000);
      QtFontMetrics.ratios.set(font.family, [m.fontBoundingBoxAscent / 1000, m.fontBoundingBoxDescent / 1000]);
    }
    const [ascent, descent] = QtFontMetrics.ratios.get(font.family);
    return Math.ceil(ascent * font.px - 1e-6) + Math.ceil(descent * font.px - 1e-6);
  }
}

class QtLocaleNumber {
  static DECIMAL = ".";
  static GROUP   = ",";

  static cLocale(text) {
    let idx = 0;
    let l   = text.length;
    while (idx < l && /\s/.test(text[idx])) idx += 1;
    if (idx === l) return null;
    while (idx < l && /\s/.test(text[l - 1])) l -= 1;

    let out         = "";
    let decimal     = -1;
    let lastGroup   = -1;
    let startDigits = -1;
    let exponent    = -1;
    while (idx < l) {
      const ch = text[idx];
      let c    = null;
      if (ch >= "0" && ch <= "9") c = ch;
      else if (ch === "+") c = "+";
      else if (ch === "-" || ch === "−") c = "-";
      else if (ch === QtLocaleNumber.DECIMAL) c = ".";
      else if (ch === QtLocaleNumber.GROUP) c = ",";
      else if (ch === "e" || ch === "E") c = "e";
      else if (ch === ";") c = ";";
      else if (ch === "%") c = "%";
      else if (/[A-Za-z]/.test(ch)) c = ch.toLowerCase();
      else break;

      if (c === ".") {
        if (decimal !== -1 || exponent !== -1) return null;
        decimal = idx;
      } else if (c === "e") {
        exponent = idx;
      }

      if (startDigits === -1 && c >= "0" && c <= "9") {
        startDigits = idx;
      } else if (c === ",") {
        if (decimal !== -1 || exponent !== -1) return null;
        if (lastGroup !== -1 && idx - lastGroup !== 4) return null;
        if (lastGroup === -1 && (startDigits === -1 || idx - startDigits > 3)) return null;
        lastGroup = idx;
        idx += 1;
        continue;
      } else if (c === "." || c === "e") {
        if (lastGroup !== -1 && idx - lastGroup !== 4) return null;
        lastGroup = -1;
      }
      out += c;
      idx += 1;
    }
    if (lastGroup + 1 === idx) return null;
    if (lastGroup !== -1 && idx - lastGroup !== 4) return null;
    return idx === l ? out : null;
  }

  static toDouble(text) {
    const c = QtLocaleNumber.cLocale(text);
    if (c === null || c === "") return { ok: false, value: 0 };
    if (c === "nan") return { ok: true, value: NaN };
    if (c === "inf" || c === "+inf") return { ok: true, value: Infinity };
    if (c === "-inf") return { ok: true, value: -Infinity };
    if (!/^[+-]?(\d+\.?\d*|\.\d+)(e[+-]?\d+)?$/.test(c)) return { ok: false, value: 0 };
    const value = Number(c);
    if (!Number.isFinite(value)) return { ok: false, value };
    if (value === 0 && /[1-9]/.test(c.split("e")[0])) return { ok: false, value: 0 };
    return { ok: true, value };
  }

  static toInt(text) {
    const c = QtLocaleNumber.cLocale(text);
    if (c === null || !/^[+-]?\d+$/.test(c)) return { ok: false, value: 0 };
    const value = Number(c);
    if (value < -2147483648 || value > 2147483647) return { ok: false, value: 0 };
    return { ok: true, value: value === 0 ? 0 : value };
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

class QtLayoutStruct {
  static MAX = 524287;

  constructor({ stretch = 0, sizeHint = 0, minimumSize = 0, maximumSize = QtLayoutStruct.MAX, expansive = false, empty = true, spacing = 0 } = {}) {
    this.stretch     = stretch;
    this.sizeHint    = sizeHint;
    this.minimumSize = minimumSize;
    this.maximumSize = maximumSize;
    this.expansive   = expansive;
    this.empty       = empty;
    this.spacing     = spacing;
    this.done        = false;
    this.pos         = 0;
    this.size        = 0;
  }

  smartSizeHint() {
    return this.stretch > 0 ? this.minimumSize : this.sizeHint;
  }

  effectiveSpacer(uniformSpacer) {
    return uniformSpacer >= 0 ? uniformSpacer : this.spacing;
  }
}

class QtLayoutEngine {
  static toFixed(i) {
    return i * 256;
  }

  static fRound(i) {
    return (i % 256 < 128) ? Math.trunc(i / 256) : 1 + Math.trunc(i / 256);
  }

  static geomCalc(chain, start, count, pos, space, spacer = -1) {
    let cHint              = 0;
    let cMin               = 0;
    let sumStretch         = 0;
    let sumSpacing         = 0;
    let expandingCount     = 0;
    let allEmptyNonstretch = true;
    let pendingSpacing     = -1;
    let spacerCount        = 0;

    for (let i = start; i < start + count; i += 1) {
      const data = chain[i];
      data.done   = false;
      cHint      += data.smartSizeHint();
      cMin       += data.minimumSize;
      sumStretch += data.stretch;
      if (!data.empty) {
        if (pendingSpacing >= 0) {
          sumSpacing += pendingSpacing;
          spacerCount += 1;
        }
        pendingSpacing = data.effectiveSpacer(spacer);
      }
      if (data.expansive) expandingCount += 1;
      allEmptyNonstretch = allEmptyNonstretch && data.empty && !data.expansive && data.stretch <= 0;
    }

    let extraspace = 0;

    if (space < cMin + sumSpacing) {
      const minSize = cMin + sumSpacing;
      if (spacer >= 0) {
        spacer     = minSize > 0 ? Math.trunc(spacer * space / minSize) : 0;
        sumSpacing = spacer * spacerCount;
      }

      const minimumSizes = chain.slice(start, start + count).map((data) => data.minimumSize).sort((a, b) => a - b);
      const spaceLeft    = space - sumSpacing;

      let sum       = 0;
      let idx       = 0;
      let spaceUsed = 0;
      let current   = 0;
      while (idx < count && spaceUsed < spaceLeft) {
        current   = minimumSizes[idx];
        spaceUsed = sum + current * (count - idx);
        sum      += current;
        idx      += 1;
      }
      idx -= 1;

      const deficit        = spaceUsed - spaceLeft;
      const items          = count - idx;
      const deficitPerItem = Math.trunc(deficit / items);
      const remainder      = deficit % items;
      const maxval         = current - deficitPerItem;

      let rest = 0;
      for (let i = start; i < start + count; i += 1) {
        let maxv = maxval;
        rest += remainder;
        if (rest >= items) {
          maxv -= 1;
          rest -= items;
        }
        const data = chain[i];
        data.size = Math.min(data.minimumSize, maxv);
        data.done = true;
      }
    } else if (space < cHint + sumSpacing) {
      let n          = count;
      let spaceLeft  = space - sumSpacing;
      let overdraft  = cHint - spaceLeft;

      for (let i = start; i < start + count; i += 1) {
        const data = chain[i];
        if (!data.done && data.minimumSize >= data.smartSizeHint()) {
          data.size  = data.smartSizeHint();
          data.done  = true;
          spaceLeft -= data.smartSizeHint();
          n         -= 1;
        }
      }

      let finished = n === 0;
      while (!finished) {
        finished = true;
        const fpOver = QtLayoutEngine.toFixed(overdraft);
        let   fpW    = 0;
        for (let i = start; i < start + count; i += 1) {
          const data = chain[i];
          if (data.done) continue;
          fpW += Math.trunc(fpOver / n);
          const w = QtLayoutEngine.fRound(fpW);
          data.size = data.smartSizeHint() - w;
          fpW      -= QtLayoutEngine.toFixed(w);
          if (data.size < data.minimumSize) {
            data.done  = true;
            data.size  = data.minimumSize;
            finished   = false;
            overdraft -= data.smartSizeHint() - data.minimumSize;
            n         -= 1;
            break;
          }
        }
      }
    } else {
      let n         = count;
      let spaceLeft = space - sumSpacing;

      for (let i = start; i < start + count; i += 1) {
        const data = chain[i];
        if (!data.done && (data.maximumSize <= data.smartSizeHint() || (!allEmptyNonstretch && data.empty && !data.expansive && data.stretch === 0))) {
          data.size   = data.smartSizeHint();
          data.done   = true;
          spaceLeft  -= data.size;
          sumStretch -= data.stretch;
          if (data.expansive) expandingCount -= 1;
          n -= 1;
        }
      }
      extraspace = spaceLeft;

      let surplus;
      let deficit;
      do {
        surplus = 0;
        deficit = 0;
        const fpSpace = QtLayoutEngine.toFixed(spaceLeft);
        let   fpW     = 0;
        for (let i = start; i < start + count; i += 1) {
          const data = chain[i];
          if (data.done) continue;
          extraspace = 0;
          if (sumStretch > 0) fpW += Math.trunc((fpSpace * data.stretch) / sumStretch);
          else if (expandingCount > 0) fpW += Math.trunc((fpSpace * (data.expansive ? 1 : 0)) / expandingCount);
          else fpW += Math.trunc(fpSpace / n);
          const w = QtLayoutEngine.fRound(fpW);
          data.size = w;
          fpW      -= QtLayoutEngine.toFixed(w);
          if (w < data.smartSizeHint()) deficit += data.smartSizeHint() - w;
          else if (w > data.maximumSize) surplus += w - data.maximumSize;
        }
        if (deficit > 0 && surplus <= deficit) {
          for (let i = start; i < start + count; i += 1) {
            const data = chain[i];
            if (!data.done && data.size < data.smartSizeHint()) {
              data.size   = data.smartSizeHint();
              data.done   = true;
              spaceLeft  -= data.smartSizeHint();
              sumStretch -= data.stretch;
              if (data.expansive) expandingCount -= 1;
              n -= 1;
            }
          }
        }
        if (surplus > 0 && surplus >= deficit) {
          for (let i = start; i < start + count; i += 1) {
            const data = chain[i];
            if (!data.done && data.size > data.maximumSize) {
              data.size   = data.maximumSize;
              data.done   = true;
              spaceLeft  -= data.maximumSize;
              sumStretch -= data.stretch;
              if (data.expansive) expandingCount -= 1;
              n -= 1;
            }
          }
        }
      } while (n > 0 && surplus !== deficit);
      if (n === 0) extraspace = spaceLeft;
    }

    const extra = Math.trunc(extraspace / (spacerCount + 2));
    let   p     = pos + extra;
    for (let i = start; i < start + count; i += 1) {
      const data = chain[i];
      data.pos = p;
      p       += data.size;
      if (!data.empty) p += data.effectiveSpacer(spacer) + extra;
    }
  }
}

class QtSplitterModel {
  static HANDLE_MARGIN = 1;
  static WIDGET_MAX    = 16777215;

  constructor(handleSize, widgets) {
    this.handleSize  = handleSize;
    this.length      = 0;
    this.collapsible = true;
    this.items       = widgets.map((widget) => ({
      minimum      : widget.minimum,
      maximum      : QtSplitterModel.WIDGET_MAX,
      sizer        : widget.hint,
      hidden       : Boolean(widget.hidden),
      collapsed    : false,
      handleHidden : true,
      pos          : 0,
      size         : 0,
    }));
    this.recalc();
  }

  setLength(length) {
    this.length = length;
    this.doResize();
  }

  setHidden(index, hidden) {
    if (this.items[index].hidden === hidden) return false;
    this.items[index].hidden = hidden;
    this.recalc();
    return true;
  }

  setSizes(sizes) {
    this.items.forEach((item, i) => {
      item.collapsed = false;
      item.sizer     = Math.max(sizes[i] === undefined ? 0 : sizes[i], 0);
      if (item.sizer === 0) {
        if (this.collapsible && item.minimum > 0) item.collapsed = true;
        else item.sizer = item.minimum;
      } else if (item.sizer < item.minimum) {
        item.sizer = item.minimum;
      }
    });
    this.doResize();
  }

  sizes() {
    return this.items.map((item) => (item.hidden ? 0 : item.size));
  }

  recalc() {
    let first        = true;
    let allInvisible = this.items.length !== 0;
    for (const item of this.items) {
      if (allInvisible && !item.hidden && !item.collapsed) allInvisible = false;
      item.handleHidden = first || item.hidden;
      if (!item.hidden) first = false;
    }
    if (allInvisible) {
      const shown = this.items.find((item) => !item.hidden);
      if (shown) shown.collapsed = false;
    }
    this.doResize();
  }

  doResize() {
    const chain = [];
    for (const item of this.items) {
      const handle = new QtLayoutStruct();
      if (item.handleHidden) handle.maximumSize = 0;
      else Object.assign(handle, { sizeHint: this.handleSize, minimumSize: this.handleSize, maximumSize: this.handleSize, empty: false });
      chain.push(handle);

      const widget = new QtLayoutStruct();
      if (item.hidden || item.collapsed) widget.maximumSize = 0;
      else Object.assign(widget, { minimumSize: item.minimum, maximumSize: item.maximum, empty: false, stretch: item.sizer, sizeHint: item.minimum, expansive: true });
      chain.push(widget);
    }
    QtLayoutEngine.geomCalc(chain, 0, chain.length, 0, this.length, 0);
    this.items.forEach((item, i) => this.setGeo(item, chain[i * 2 + 1].pos, chain[i * 2 + 1].size, false));
  }

  setGeo(item, pos, size, allowCollapse) {
    item.pos  = pos;
    item.size = size;
    if (allowCollapse) item.collapsed = size <= 0 && item.minimum > 0 && !item.hidden;
  }

  handleTop(index) {
    return this.items[index].pos - this.handleSize - QtSplitterModel.HANDLE_MARGIN;
  }

  addContribution(index, range, mayCollapse) {
    const item = this.items[index];
    if (item.hidden) return;
    if (!item.handleHidden) {
      range.min += this.handleSize;
      range.max += this.handleSize;
    }
    if (mayCollapse || !item.collapsed) range.min += item.minimum;
    range.max += item.maximum;
  }

  findWidgetJustBeforeOrJustAfter(index, delta) {
    let i = delta < 0 ? index + delta : index;
    do {
      const item = this.items[i];
      if (!item.hidden) return { index: i, collapsibleSize: this.collapsible ? item.minimum : 0 };
      i += delta;
    } while (i >= 0 && i < this.items.length);
    return { index: -1, collapsibleSize: 0 };
  }

  getRange(index) {
    const before = this.findWidgetJustBeforeOrJustAfter(index, -1);
    const after  = this.findWidgetJustBeforeOrJustAfter(index, +1);
    const lower  = { min: 0, max: 0 };
    const upper  = { min: 0, max: 0 };
    for (let i = 0; i < index; i += 1) this.addContribution(i, lower, i === before.index);
    for (let i = index; i < this.items.length; i += 1) this.addContribution(i, upper, i === after.index);

    const size           = this.length;
    const smartMinBefore = Math.max(lower.min, size - upper.max);
    const smartMaxBefore = Math.min(lower.max, size - upper.min);
    const min            = smartMinBefore;
    const max            = smartMaxBefore;
    let   farMin         = min;
    let   farMax         = max;
    if (lower.min - before.collapsibleSize >= size - upper.max) farMin -= before.collapsibleSize;
    if (size - (upper.min - after.collapsibleSize) <= lower.max) farMax += after.collapsibleSize;
    return { farMin, min, max, farMax };
  }

  adjustPos(pos, index) {
    const threshold = 40;
    const range     = this.getRange(index);
    let   adjusted;
    if (pos >= range.min) {
      if (pos <= range.max) {
        adjusted = pos;
      } else {
        const delta = pos - range.max;
        const width = range.farMax - range.max;
        adjusted = delta > Math.trunc(width / 2) && delta >= Math.min(threshold, width) ? range.farMax : range.max;
      }
    } else {
      const delta = range.min - pos;
      const width = range.min - range.farMin;
      adjusted = delta > Math.trunc(width / 2) && delta >= Math.min(threshold, width) ? range.farMin : range.min;
    }
    return { pos: adjusted, range };
  }

  doMove(backwards, hPos, index, delta, mayCollapse, positions, widths) {
    if (index < 0 || index >= this.items.length) return;
    const item   = this.items[index];
    const nextId = backwards ? index - delta : index + delta;
    if (item.hidden) {
      this.doMove(backwards, hPos, nextId, delta, this.collapsible, positions, widths);
      return;
    }
    const hs = item.handleHidden ? 0 : this.handleSize;
    let   ws = backwards ? hPos - item.pos : (item.pos + item.size - 1) - hPos - hs + 1;
    if (ws > 0 || (!item.collapsed && !mayCollapse)) {
      ws = Math.min(ws, item.maximum);
      ws = Math.max(ws, item.minimum);
    } else {
      ws = 0;
    }
    positions[index] = backwards ? hPos - ws : hPos + hs;
    widths[index]    = ws;
    this.doMove(backwards, backwards ? hPos - ws - hs : hPos + hs + ws, nextId, delta, this.collapsible, positions, widths);
  }

  moveSplitter(pos, index) {
    const adjusted  = this.adjustPos(pos, index);
    const positions = new Array(this.items.length).fill(0);
    const widths    = new Array(this.items.length).fill(0);
    const target    = adjusted.pos;
    this.doMove(false, target, index, +1, this.collapsible && target > adjusted.range.max, positions, widths);
    this.doMove(true, target, index - 1, +1, this.collapsible && target < adjusted.range.min, positions, widths);
    this.items.forEach((item, i) => {
      if (!item.hidden) this.setGeo(item, positions[i], widths[i], true);
    });
    for (const item of this.items) item.sizer = item.size;
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
  static HANDLE        = 15;
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
  static CHROME        = 23;

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

    this.double      = false;
    this.minimum     = 0;
    this.maximum     = 99;
    this.value       = 0;
    this.decimals    = 0;
    this.prefix      = this.options.prefix || "";
    this.suffix      = this.options.suffix || "";
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
    this.renderHint();
    return root;
  }

  focusables() {
    return [this.input, this.up, this.down];
  }

  textFromValue(value) {
    return this.decimals > 0 ? Number(value).toFixed(this.decimals) : String(Math.round(value));
  }

  format(value) {
    return `${this.prefix}${this.textFromValue(value)}${this.suffix}`;
  }

  sizeHint(font) {
    const fixed = `${this.prefix}${this.suffix} `;
    const texts = [this.minimum, this.maximum].map((value) => this.textFromValue(value).slice(0, 18) + fixed);
    return QtFontMetrics.widest(texts, font) + 2 + QtSpinBoxView.CHROME;
  }

  renderHint() {
    const root = this.input.parentElement;
    root.style.setProperty("--tv-spin-hint-window", `${this.sizeHint(QtFontMetrics.WINDOW)}px`);
    root.style.setProperty("--tv-spin-hint-app", `${this.sizeHint(QtFontMetrics.APP)}px`);
  }

  apply(state, previous) {
    if ("decimals" in state) this.decimals = state.decimals;
    if ("minimum" in state) this.minimum = state.minimum;
    if ("maximum" in state) this.maximum = state.maximum;
    if ("singleStep" in state) this.singleStep = state.singleStep;
    this.renderHint();
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

  stripped(text, pos) {
    let middle  = text;
    let changed = false;
    let from    = 0;
    let size    = middle.length;
    if (this.prefix && middle.startsWith(this.prefix)) {
      from    += this.prefix.length;
      size    -= from;
      changed  = true;
    }
    if (this.suffix && middle.endsWith(this.suffix)) {
      size    -= this.suffix.length;
      changed  = true;
    }
    if (changed) middle = middle.slice(from, from + Math.max(0, size));
    const before = middle.length;
    middle       = middle.trim();
    return [middle, pos - (before - middle.length)];
  }

  interpretInt(copy) {
    const min = this.minimum;
    const max = this.maximum;
    if (max !== min && (copy === "" || (min < 0 && copy === "-") || (max >= 0 && copy === "+"))) return ["Intermediate", null];
    if (copy.startsWith("-") && min >= 0) return ["Invalid", null];

    let parsed = QtLocaleNumber.toInt(copy);
    if (!parsed.ok && (max >= 1000 || min <= -1000)) {
      const group = QtLocaleNumber.GROUP;
      if (copy.includes(group) && !copy.includes(group + group)) parsed = QtLocaleNumber.toInt(copy.split(group).join(""));
    }
    return this.ranged(parsed);
  }

  interpretDouble(copy, pos) {
    const min     = this.minimum;
    const max     = this.maximum;
    const plus    = max >= 0;
    const minus   = min <= 0;
    const decimal = QtLocaleNumber.DECIMAL;
    const group   = QtLocaleNumber.GROUP;
    const len     = copy.length;

    if (len === 0) return [max !== min ? "Intermediate" : "Invalid", null, copy];
    if (len === 1 && (copy === decimal || (plus && copy === "+") || (minus && copy === "-"))) return ["Intermediate", null, copy];
    if (len === 2 && copy[1] === decimal && ((plus && copy[0] === "+") || (minus && copy[0] === "-"))) return ["Intermediate", null, copy];

    if (copy[0] === group) return ["Invalid", null, copy];
    if (len > 1) {
      const dec = copy.indexOf(decimal);
      if (dec !== -1) {
        if (dec + 1 < copy.length && copy[dec + 1] === decimal && pos === dec + 1) copy = copy.slice(0, dec + 1) + copy.slice(dec + 2);
        if (copy.length - dec > this.decimals + 1) return ["Invalid", null, copy];
        for (let i = dec + 1; i < copy.length; i += 1) {
          if (/\s/.test(copy[i]) || copy[i] === group) return ["Invalid", null, copy];
        }
      } else {
        const last       = copy[len - 1];
        const secondLast = copy[len - 2];
        if ((last === group || /\s/.test(last)) && (secondLast === group || /\s/.test(secondLast))) return ["Invalid", null, copy];
        if (/\s/.test(last) && (!/\s/.test(group) || /\s/.test(secondLast))) return ["Invalid", null, copy];
      }
    }

    let parsed = QtLocaleNumber.toDouble(copy);
    if (!parsed.ok) {
      if (max < 1000 && min > -1000 && copy.includes(group)) return ["Invalid", null, copy];
      if (copy.includes(group + group)) return ["Invalid", null, copy];
      parsed = QtLocaleNumber.toDouble(copy.split(group).join(""));
    }
    return [...this.ranged(parsed), copy];
  }

  ranged(parsed) {
    const min = this.minimum;
    const max = this.maximum;
    const num = parsed.value;
    if (!parsed.ok) return ["Invalid", null];
    if (num >= min && num <= max) return ["Acceptable", num];
    if (max === min) return ["Invalid", null];
    if ((num >= 0 && num > max) || (num < 0 && num < min)) return ["Invalid", null];
    return ["Intermediate", null];
  }

  validate(text, pos = text.length) {
    let input = text;
    let at    = pos;
    if (this.prefix && !input.startsWith(this.prefix)) {
      input  = this.prefix + input;
      at    += this.prefix.length;
    }
    if (this.suffix && !input.endsWith(this.suffix)) input += this.suffix;

    const [stripped, moved] = this.stripped(input, at);
    let copy                = stripped;
    let state;
    let num;
    if (this.double) [state, num, copy] = this.interpretDouble(copy, moved);
    else [state, num] = this.interpretInt(copy);
    const fixed = `${this.prefix}${copy}${this.suffix}`;
    return [state, num, fixed, Math.max(0, Math.min(fixed.length, moved))];
  }

  typed() {
    const [state, num, fixed, pos] = this.validate(this.input.value, this.input.selectionStart);
    if (state === "Invalid") {
      this.input.value = this.before.text;
      this.input.setSelectionRange(this.before.start, this.before.end);
      return;
    }
    if (fixed !== this.input.value) {
      this.input.value = fixed;
      this.input.setSelectionRange(pos, pos);
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
    const text       = this.input.value;
    let [state, num] = this.validate(text);
    if (state !== "Acceptable") {
      const removed = text.split(QtLocaleNumber.GROUP).join("");
      if (removed !== text) [state, num] = this.validate(removed);
    }
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
    this.double   = true;
    this.decimals = this.options.decimals === undefined ? 2 : this.options.decimals;
    this.maximum  = 99.99;
    root.classList.add("tv-spin--double");
    this.renderHint();
    return root;
  }
}

class QtComboPopup {
  static VISIBLE_ROWS = 10;

  constructor(anchor, layer, items, { className = "", capped = true, onPick, onClose }) {
    this.anchor  = anchor;
    this.layer   = layer;
    this.items   = items;
    this.capped  = capped;
    this.onPick  = onPick;
    this.onClose = onClose;
    this.hot     = -1;
    this.list    = TomoVisInput.el("div", `tv-combo__popup tv-qt-scroll ${className}`.trim());
    this.list.setAttribute("role", "listbox");
    this.rows    = items.map((item, i) => this.row(item, i));
    this.outside = (event) => {
      if (!this.list.contains(event.target) && !this.anchor.contains(event.target)) this.close();
    };
  }

  row(item, i) {
    const row = TomoVisInput.el("div", "tv-combo__option");
    row.setAttribute("role", "option");
    row.classList.toggle("is-disabled", !item.enabled);
    if (item.icon) row.append(TomoVisInput.el("span", item.icon));
    row.append(document.createTextNode(item.text));
    row.addEventListener("pointerenter", () => this.highlight(i, false));
    row.addEventListener("click", () => this.pick(i));
    this.list.append(row);
    return row;
  }

  open(current) {
    this.layer.append(this.list);
    const rect = this.anchor.getBoundingClientRect();
    this.list.style.minWidth = `${rect.width}px`;
    if (this.capped) this.cap();
    TomoVisInput.place(this.layer, this.list, rect.left, rect.bottom, { flipBottom: rect.top });
    this.highlight(current, true);
    this.anchor.setAttribute("aria-expanded", "true");
    this.anchor.classList.add("is-open");
    document.addEventListener("pointerdown", this.outside, true);
  }

  cap() {
    const rowHeight = this.rows.length ? this.rows[0].getBoundingClientRect().height : 20;
    const frame     = this.list.offsetHeight - this.list.clientHeight;
    this.list.style.maxHeight = `${rowHeight * QtComboPopup.VISIBLE_ROWS + frame}px`;
  }

  highlight(i, scroll) {
    if (!this.items[i] || !this.items[i].enabled) return;
    this.hot = i;
    this.rows.forEach((row, k) => row.classList.toggle("is-hot", k === i));
    if (scroll) this.rows[i].scrollIntoView({ block: "nearest" });
  }

  step(offset) {
    let i = this.hot;
    do {
      i += offset;
    } while (i >= 0 && i < this.items.length && !this.items[i].enabled);
    this.highlight(i, true);
  }

  pick(i) {
    if (!this.items[i] || !this.items[i].enabled) return;
    this.close();
    this.onPick(i);
  }

  close() {
    document.removeEventListener("pointerdown", this.outside, true);
    this.list.remove();
    this.anchor.setAttribute("aria-expanded", "false");
    this.anchor.classList.remove("is-open");
    this.onClose();
  }
}

class QtComboBoxView extends QtWidgetView {
  static SEARCH_MS          = 400;
  static STYLE_SHEET_CHROME = 30;
  static FUSION_CHROME      = 27;

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
    if (this.options.qtFont) this.label.parentElement.style.width = `${this.sizeHint()}px`;
    else this.sizer.replaceChildren(...this.items.map((text) => TomoVisInput.el("span", "", text)));
  }

  sizeHint() {
    return QtFontMetrics.widest(this.items, this.options.qtFont) + (this.options.styleSheet ? QtComboBoxView.STYLE_SHEET_CHROME : QtComboBoxView.FUSION_CHROME);
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
    const from   = this.popup ? this.popup.hot : this.index;
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
    const items = this.items.map((text) => ({ text, icon: null, enabled: true }));
    const popup = new QtComboPopup(this.el, this.kit.layer, items, {
      className : this.options.styleSheet ? "tv-combo__popup--qt" : "",
      onPick    : (i) => this.choose(i, "click"),
      onClose   : () => { this.popup = null; },
    });
    this.popup = popup;
    popup.open(this.index);
  }

  popupKey(event) {
    const popup = this.popup;
    const moves = { ArrowUp: -1, ArrowDown: 1, PageUp: -(QtComboPopup.VISIBLE_ROWS - 1), PageDown: QtComboPopup.VISIBLE_ROWS - 1 };
    if (event.key in moves) {
      event.preventDefault();
      popup.highlight(Math.max(0, Math.min(this.items.length - 1, popup.hot + moves[event.key])), true);
    } else if (event.key === "Home" || event.key === "End") {
      event.preventDefault();
      popup.highlight(event.key === "Home" ? 0 : this.items.length - 1, true);
    } else if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      const chosen = popup.hot;
      popup.close();
      this.choose(chosen, "key");
    } else if (event.key === "Escape" || event.key === "Tab" || event.key === "F4") {
      event.preventDefault();
      event.stopPropagation();
      popup.close();
    } else if (event.key.length === 1 && !event.ctrlKey && !event.metaKey && !event.altKey) {
      const found = this.keyboardSearch(event.key);
      if (found >= 0) popup.highlight(found, true);
    }
  }

  closePopup() {
    if (this.popup) this.popup.close();
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
    new ResizeObserver(() => this.revealCursor()).observe(input);
    return input;
  }

  revealCursor() {
    const input = this.input;
    const width = input.clientWidth;
    if (width === 0) return;
    const style  = getComputedStyle(input);
    const inner  = width - parseFloat(style.paddingLeft) - parseFloat(style.paddingRight);
    const font   = `${style.fontStyle} ${style.fontWeight} ${style.fontSize} ${style.fontFamily}`;
    if (!QtFontMetrics.context) QtFontMetrics.context = document.createElement("canvas").getContext("2d");
    QtFontMetrics.context.font = font;
    const cursorX = QtFontMetrics.context.measureText(input.value.slice(0, input.selectionEnd)).width;
    if (cursorX - input.scrollLeft >= inner) input.scrollLeft = Math.ceil(cursorX - inner + 1);
    else if (cursorX < input.scrollLeft) input.scrollLeft = Math.floor(cursorX);
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
    this.input.setSelectionRange(state.text.length, state.text.length);
    this.revealCursor();
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
    return TomoVisInput.plainPushButton(button);
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
    this.el.classList.toggle("tv-menu--plain", this.items.length > 0 && this.items.every((item) => item.widget && item.plain));
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

    if (item.widget && item.plain) {
      row.classList.add("tv-menu__item--plain");
      row.append(item.widget);
    } else if (item.widget) {
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
    if (this.parent && this.active >= 0) this.ctx.bus.emit("status", { text: "" });
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
window.QtLayoutStruct      = QtLayoutStruct;
window.QtLayoutEngine      = QtLayoutEngine;
window.QtSplitterModel     = QtSplitterModel;
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
