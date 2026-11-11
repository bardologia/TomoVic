"use strict";

class PgSignal {
  constructor() {
    this.slots = [];
  }

  connect(fn) {
    this.slots.push(fn);
    return fn;
  }

  disconnect(fn) {
    const index = this.slots.indexOf(fn);
    if (index >= 0) this.slots.splice(index, 1);
  }

  emit(...args) {
    for (const fn of [...this.slots]) fn(...args);
  }
}

class PgPen {
  static COLORS = {
    w : [255, 255, 255, 255],
    k : [0, 0, 0, 255],
    r : [255, 0, 0, 255],
    g : [0, 255, 0, 255],
    b : [0, 0, 255, 255],
    c : [0, 255, 255, 255],
    m : [255, 0, 255, 255],
    y : [255, 255, 0, 255],
    d : [150, 150, 150, 255],
    l : [200, 200, 200, 255],
    s : [100, 100, 150, 255],
  };

  static color(spec) {
    if (spec === null || spec === undefined) return null;
    if (typeof spec === "string") {
      if (spec in PgPen.COLORS) return [...PgPen.COLORS[spec]];
      if (spec.startsWith("#")) {
        const hex = spec.slice(1);
        const r   = parseInt(hex.slice(0, 2), 16);
        const g   = parseInt(hex.slice(2, 4), 16);
        const b   = parseInt(hex.slice(4, 6), 16);
        const a   = hex.length >= 8 ? parseInt(hex.slice(6, 8), 16) : 255;
        return [r, g, b, a];
      }
      throw new Error(`PgPen cannot read colour ${spec}`);
    }
    if (typeof spec === "number") {
      const v = Math.round(spec * 255);
      return [v, v, v, 255];
    }
    return [spec[0], spec[1], spec[2], spec.length > 3 ? spec[3] : 255];
  }

  static mk(spec, options = {}) {
    if (spec === null) return null;
    if (spec && typeof spec === "object" && !Array.isArray(spec) && "color" in spec) return { color: PgPen.color(spec.color), width: spec.width === undefined ? 1 : spec.width, style: spec.style || "solid" };
    return { color: PgPen.color(spec === undefined ? "d" : spec), width: options.width === undefined ? 1 : options.width, style: options.style || "solid" };
  }

  static css(color, alphaScale = 1) {
    return `rgba(${color[0]}, ${color[1]}, ${color[2]}, ${(color[3] / 255) * alphaScale})`;
  }

  static apply(ctx, pen) {
    ctx.strokeStyle = PgPen.css(pen.color);
    ctx.lineWidth   = pen.width || 1;
    ctx.setLineDash(pen.style === "dash" ? [4 * (pen.width || 1), 2 * (pen.width || 1)] : []);
  }

  static crisp(v, width) {
    return Math.round(width) % 2 === 1 ? Math.floor(v) + 0.5 : Math.round(v);
  }
}

class PgGeom {
  static polyContains(poly, x, y) {
    let inside = false;
    for (let i = 0, j = poly.length - 1; i < poly.length; j = i, i += 1) {
      const [xi, yi] = poly[i];
      const [xj, yj] = poly[j];
      if ((yi > y) !== (yj > y) && x < ((xj - xi) * (y - yi)) / (yj - yi) + xi) inside = !inside;
    }
    return inside;
  }

  static segmentsCross(a, b, c, d) {
    const cross = (p, q, r) => (q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0]);
    const d1    = cross(c, d, a);
    const d2    = cross(c, d, b);
    const d3    = cross(a, b, c);
    const d4    = cross(a, b, d);
    return ((d1 > 0) !== (d2 > 0)) && ((d3 > 0) !== (d4 > 0));
  }

  static polyIntersectsRect(poly, x0, y0, x1, y1) {
    const rect = [[x0, y0], [x1, y0], [x1, y1], [x0, y1]];
    if (rect.some(([x, y]) => PgGeom.polyContains(poly, x, y))) return true;
    if (poly.some(([x, y]) => x >= x0 && x <= x1 && y >= y0 && y <= y1)) return true;
    for (let i = 0; i < poly.length; i += 1) {
      const a = poly[i];
      const b = poly[(i + 1) % poly.length];
      for (let k = 0; k < 4; k += 1) {
        if (PgGeom.segmentsCross(a, b, rect[k], rect[(k + 1) % 4])) return true;
      }
    }
    return false;
  }

  static rectPoly(x, y, w, h) {
    return [[x, y], [x + w, y], [x + w, y + h], [x, y + h]];
  }

  static normRect(x0, y0, x1, y1) {
    return { x: Math.min(x0, x1), y: Math.min(y0, y1), w: Math.abs(x1 - x0), h: Math.abs(y1 - y0) };
  }
}

class PgMouseEvent {
  static BUTTONS = ["left", "middle", "right"];

  static modifiers(event) {
    return { shift: event.shiftKey, ctrl: event.ctrlKey, alt: event.altKey, meta: event.metaKey };
  }

  static none(mods) {
    return !mods.shift && !mods.ctrl && !mods.alt && !mods.meta;
  }

  constructor(fields) {
    Object.assign(this, fields);
    this.accepted    = false;
    this.currentItem = null;
  }

  accept() {
    this.accepted = true;
  }

  ignore() {
    this.accepted = false;
  }

  isStart() {
    return Boolean(this.start);
  }

  isFinish() {
    return Boolean(this.finish);
  }
}

class PgHoverEvent {
  constructor(pos, acceptable, modifiers) {
    this.pos         = pos;
    this.acceptable  = acceptable;
    this.modifiers   = modifiers;
    this.enter       = false;
    this.exit        = false;
    this.currentItem = null;
    this.drags       = new Map();
    this.clicks      = new Map();
  }

  isExit() {
    return this.exit;
  }

  acceptDrags(button) {
    if (!this.acceptable || this.drags.has(button)) return false;
    this.drags.set(button, this.currentItem);
    return true;
  }

  acceptClicks(button) {
    if (!this.acceptable || this.clicks.has(button)) return false;
    this.clicks.set(button, this.currentItem);
    return true;
  }
}

class PgFormat {
  static exact(x) {
    const view = new DataView(new ArrayBuffer(8));
    view.setFloat64(0, Math.abs(x));
    const hi   = view.getUint32(0);
    const lo   = view.getUint32(4);
    const bexp = (hi >>> 20) & 0x7ff;
    let mant   = (BigInt(hi & 0xfffff) << 32n) | BigInt(lo);
    let exp;
    if (bexp === 0) exp = -1074;
    else {
      mant += 1n << 52n;
      exp   = bexp - 1075;
    }
    if (exp >= 0) return { digits: (mant << BigInt(exp)).toString(), scale: 0 };
    return { digits: (mant * 5n ** BigInt(-exp)).toString(), scale: -exp };
  }

  static roundDigits(digits, scale, places) {
    if (scale <= places) return { digits: digits + "0".repeat(places - scale), scale: places };
    const cut  = scale - places;
    const keep = digits.length > cut ? digits.slice(0, digits.length - cut) : "0";
    const rest = digits.length > cut ? digits.slice(digits.length - cut) : digits.padStart(cut, "0");
    let value  = BigInt(keep);
    const half = "5" + "0".repeat(cut - 1);
    if (rest > half || (rest === half && value % 2n === 1n)) value += 1n;
    return { digits: value.toString(), scale: places };
  }

  static place(digits, scale) {
    const padded = digits.padStart(scale + 1, "0");
    if (scale === 0) return padded;
    return `${padded.slice(0, padded.length - scale)}.${padded.slice(padded.length - scale)}`;
  }

  static fixed(x, places) {
    if (!Number.isFinite(x)) return Number.isNaN(x) ? "nan" : (x > 0 ? "inf" : "-inf");
    const { digits, scale } = PgFormat.exact(x);
    const r = PgFormat.roundDigits(digits, scale, places);
    const s = PgFormat.place(r.digits, r.scale);
    return x < 0 || Object.is(x, -0) ? `-${s}` : s;
  }

  static decimalExponent(x, sig) {
    const { digits, scale } = PgFormat.exact(x);
    const trimmed = digits.replace(/^0+/, "");
    let exp = trimmed.length - 1 - scale;
    const r = PgFormat.roundDigits(digits, scale, sig - 1 - exp);
    const rt = r.digits.replace(/^0+/, "");
    if (rt.length - 1 - r.scale > exp) exp += 1;
    return exp;
  }

  static g(x, precision = 6) {
    if (!Number.isFinite(x)) return Number.isNaN(x) ? "nan" : (x > 0 ? "inf" : "-inf");
    if (x === 0) return Object.is(x, -0) ? "-0" : "0";
    const p   = precision === 0 ? 1 : precision;
    const exp = PgFormat.decimalExponent(x, p);
    if (exp >= -4 && exp < p) {
      const s = PgFormat.fixed(x, p - 1 - exp);
      return s.includes(".") ? s.replace(/0+$/, "").replace(/\.$/, "") : s;
    }
    const { digits, scale } = PgFormat.exact(x);
    const r = PgFormat.roundDigits(digits, scale, p - 1 - exp);
    let mant = r.digits.replace(/^0+/, "");
    mant = mant.length > 1 ? `${mant[0]}.${mant.slice(1)}`.replace(/0+$/, "").replace(/\.$/, "") : mant;
    const sign = x < 0 ? "-" : "";
    return `${sign}${mant}e${exp < 0 ? "-" : "+"}${String(Math.abs(exp)).padStart(2, "0")}`;
  }
}

class PgGraphicsView {
  static CLICK_RADIUS  = 2;
  static MOVE_DISTANCE = 5;
  static MIN_DRAG_TIME = 500;

  constructor(host, { background = [0, 0, 0, 255], onLayout = null, className = "" } = {}) {
    this.host        = host;
    this.el          = document.createElement("canvas");
    this.el.className = `tv-pg-canvas ${className}`.trim();
    this.el.tabIndex = 0;
    this.ctx2d       = this.el.getContext("2d");
    this.background  = background;
    this.onLayout    = onLayout;
    this.widgets     = [];
    this.width       = 0;
    this.height      = 0;
    this.dpr         = window.devicePixelRatio || 1;
    this.queued      = false;
    this.focusItem   = null;
    this.clickEvents = [];
    this.dragButtons = [];
    this.dragItem    = null;
    this.lastDrag    = null;
    this.hoverItems  = new Set();
    this.lastHover   = null;
    this.lastPos     = null;
    this.overlays    = [];
    this.sigPrepareForPaint = new PgSignal();
    host.append(this.el);

    this.el.addEventListener("pointerdown", (event) => this.pointerDown(event));
    this.el.addEventListener("pointermove", (event) => this.pointerMove(event));
    this.el.addEventListener("pointerup", (event) => this.pointerUp(event));
    this.el.addEventListener("pointercancel", (event) => this.pointerUp(event));
    this.el.addEventListener("pointerleave", () => this.pointerLeave());
    this.el.addEventListener("wheel", (event) => this.wheel(event), { passive: false });
    this.el.addEventListener("contextmenu", (event) => event.preventDefault());
    this.el.addEventListener("keydown", (event) => this.keyDown(event));
    new ResizeObserver(() => this.resize()).observe(this.el);
  }

  addWidget(widget) {
    widget.scene = this;
    this.widgets.push(widget);
    this.update();
    return widget;
  }

  resize() {
    const width  = this.el.clientWidth;
    const height = this.el.clientHeight;
    const dpr    = window.devicePixelRatio || 1;
    if (width === this.width && height === this.height && dpr === this.dpr) return;
    this.width  = width;
    this.height = height;
    this.dpr    = dpr;
    this.el.width  = Math.max(1, Math.round(width * dpr));
    this.el.height = Math.max(1, Math.round(height * dpr));
    if (this.onLayout) this.onLayout(width, height);
    this.paintNow();
  }

  update() {
    if (this.queued) return;
    this.queued = true;
    requestAnimationFrame(() => {
      this.queued = false;
      this.paintNow();
    });
  }

  visible() {
    return this.width > 0 && this.height > 0 && this.el.offsetParent !== null;
  }

  paintNow() {
    if (this.width === 0 || this.height === 0) return;
    this.sigPrepareForPaint.emit();
    this.render(this.ctx2d, this.dpr, { background: this.background });
  }

  render(ctx, scale, { background, overlays = true }) {
    ctx.save();
    ctx.setTransform(scale, 0, 0, scale, 0, 0);
    ctx.clearRect(0, 0, this.width, this.height);
    this.paintScene(ctx, { background, overlays });
    ctx.restore();
  }

  paintScene(ctx, { background = null, overlays = true } = {}) {
    if (background && background[3] > 0) {
      ctx.fillStyle = PgPen.css(background);
      ctx.fillRect(0, 0, this.width, this.height);
    }
    for (const widget of this.widgets) {
      if (widget.visible !== false) widget.paint(ctx);
    }
    if (overlays) {
      for (const overlay of this.overlays) overlay(ctx);
    }
  }

  sceneItems() {
    const list = [];
    for (const widget of this.widgets) {
      if (widget.visible === false) continue;
      for (const entry of widget.sceneItems()) list.push(entry);
    }
    list.forEach((entry, i) => { entry.order = i; });
    list.sort((a, b) => (b.z - a.z) || (b.order - a.order));
    return list.map((entry) => entry.item);
  }

  itemsNear(x, y, hoverable = false) {
    const r     = PgGraphicsView.CLICK_RADIUS;
    const items = this.sceneItems();
    const at    = items.filter((item) => item.hit(x, y));
    const near  = items.filter((item) => !at.includes(item) && item.hitRect && item.hitRect(x - r, y - r, x + r, y + r));
    const all   = [...at, ...near];
    return hoverable ? all.filter((item) => typeof item.hoverEvent === "function") : all;
  }

  local(event) {
    const rect = this.el.getBoundingClientRect();
    return { x: event.clientX - rect.left, y: event.clientY - rect.top };
  }

  sendHover(pos, acceptable, modifiers, exitOnly = false) {
    const event = new PgHoverEvent(pos, exitOnly ? false : acceptable, modifiers);
    const items = exitOnly ? [] : this.itemsNear(pos.x, pos.y, true);
    const prev  = new Set(this.hoverItems);

    for (const item of items) {
      event.currentItem = item;
      if (!this.hoverItems.has(item)) {
        this.hoverItems.add(item);
        event.enter = true;
      } else {
        prev.delete(item);
        event.enter = false;
      }
      item.hoverEvent(event);
    }
    event.enter = false;
    event.exit  = true;
    for (const item of prev) {
      event.currentItem = item;
      item.hoverEvent(event);
      this.hoverItems.delete(item);
    }
    return event;
  }

  pointerDown(event) {
    const button = PgMouseEvent.BUTTONS[event.button];
    if (!button) return;
    event.preventDefault();
    this.el.setPointerCapture(event.pointerId);
    this.el.focus({ preventScroll: true });

    const pos       = this.local(event);
    const modifiers = PgMouseEvent.modifiers(event);
    if (this.lastHover && (this.lastHover.pos.x !== pos.x || this.lastHover.pos.y !== pos.y)) this.lastHover = this.sendHover(pos, false, modifiers);

    this.clickEvents.push(new PgMouseEvent({ button, scenePos: pos, screenPos: { x: event.clientX, y: event.clientY }, time: performance.now(), modifiers }));
    const focusable = this.itemsNear(pos.x, pos.y).find((item) => item.focusable);
    if (focusable) this.focusItem = focusable;
    this.lastPos = pos;
  }

  pointerMove(event) {
    const pos       = this.local(event);
    const modifiers = PgMouseEvent.modifiers(event);
    const hover     = this.sendHover(pos, event.buttons === 0, modifiers);
    if (event.buttons === 0) this.lastHover = hover;
    this.lastPos = pos;
    if (event.buttons === 0) return;

    const now = performance.now();
    let init  = false;
    for (const [button, mask] of [["left", 1], ["middle", 4], ["right", 2]]) {
      if (!(event.buttons & mask) || this.dragButtons.includes(button)) continue;
      const press = this.clickEvents.find((e) => e.button === button);
      if (!press) continue;
      const dist = Math.hypot(pos.x - press.scenePos.x, pos.y - press.scenePos.y);
      if (dist === 0 || (dist < PgGraphicsView.MOVE_DISTANCE && now - press.time < PgGraphicsView.MIN_DRAG_TIME)) continue;
      init = init || this.dragButtons.length === 0;
      this.dragButtons.push(button);
    }
    if (this.dragButtons.length > 0) this.sendDrag(pos, { x: event.clientX, y: event.clientY }, modifiers, init, false);
  }

  pointerUp(event) {
    const button    = PgMouseEvent.BUTTONS[event.button];
    const pos       = this.local(event);
    const modifiers = PgMouseEvent.modifiers(event);

    if (button && this.dragButtons.includes(button)) {
      this.sendDrag(pos, { x: event.clientX, y: event.clientY }, modifiers, false, true);
      this.dragButtons.splice(this.dragButtons.indexOf(button), 1);
    } else if (button) {
      const press = this.clickEvents.find((e) => e.button === button);
      if (press) {
        press.screenPos = { x: event.clientX, y: event.clientY };
        this.sendClick(press);
        this.clickEvents.splice(this.clickEvents.indexOf(press), 1);
      }
    }
    if (event.buttons === 0) {
      this.dragItem    = null;
      this.dragButtons = [];
      this.clickEvents = [];
      this.lastDrag    = null;
    }
    const hover = this.sendHover(pos, event.buttons === 0, modifiers);
    if (event.buttons === 0) this.lastHover = hover;
  }

  pointerLeave() {
    if (this.dragButtons.length === 0) this.sendHover({ x: -1, y: -1 }, false, {}, true);
  }

  sendDrag(pos, screenPos, modifiers, init, final) {
    const press = this.clickEvents[0];
    if (!press) return false;
    const event = new PgMouseEvent({
      button             : press.button,
      start              : init,
      finish             : final,
      scenePos           : pos,
      screenPos,
      lastScenePos       : this.lastDrag ? this.lastDrag.scenePos : press.scenePos,
      lastScreenPos      : this.lastDrag ? this.lastDrag.screenPos : press.screenPos,
      buttonDownScenePos : press.scenePos,
      buttonDownScreenPos: press.screenPos,
      modifiers,
    });

    if (init && !this.dragItem) {
      const accepted = this.lastHover ? this.lastHover.drags.get(event.button) : null;
      if (accepted && this.sceneItems().includes(accepted)) {
        this.dragItem     = accepted;
        event.currentItem = accepted;
        accepted.mouseDragEvent(event);
      } else {
        for (const item of this.itemsNear(press.scenePos.x, press.scenePos.y)) {
          if (typeof item.mouseDragEvent !== "function") continue;
          event.currentItem = item;
          item.mouseDragEvent(event);
          if (event.accepted) {
            this.dragItem = item;
            if (item.focusable) this.focusItem = item;
            break;
          }
        }
      }
    } else if (this.dragItem) {
      event.currentItem = this.dragItem;
      this.dragItem.mouseDragEvent(event);
    }
    this.lastDrag = event;
    this.update();
    return event.accepted;
  }

  sendClick(press) {
    const event = new PgMouseEvent({ button: press.button, scenePos: press.scenePos, screenPos: press.screenPos, modifiers: press.modifiers, double: false });
    if (this.dragItem && typeof this.dragItem.mouseClickEvent === "function") {
      event.currentItem = this.dragItem;
      this.dragItem.mouseClickEvent(event);
    } else {
      const accepted = this.lastHover ? this.lastHover.clicks.get(event.button) : null;
      if (accepted) {
        event.currentItem = accepted;
        accepted.mouseClickEvent(event);
      } else {
        for (const item of this.itemsNear(press.scenePos.x, press.scenePos.y)) {
          if (typeof item.mouseClickEvent !== "function") continue;
          event.currentItem = item;
          item.mouseClickEvent(event);
          if (event.accepted) {
            if (item.focusable) this.focusItem = item;
            break;
          }
        }
      }
    }
    this.update();
    return event.accepted;
  }

  wheel(event) {
    const pos   = this.local(event);
    const delta = TomoVisInput.angleDelta(event);
    const value = delta.y !== 0 ? delta.y : delta.x;
    const ev    = new PgMouseEvent({ scenePos: pos, delta: value, orientation: delta.y !== 0 ? "vertical" : "horizontal", modifiers: PgMouseEvent.modifiers(event) });
    for (const item of this.sceneItems().filter((it) => it.hit(pos.x, pos.y))) {
      if (typeof item.wheelEvent !== "function") continue;
      ev.accepted = true;
      item.wheelEvent(ev);
      if (ev.accepted) {
        event.preventDefault();
        break;
      }
    }
    this.update();
  }

  keyDown(event) {
    if (!this.focusItem || typeof this.focusItem.keyPressEvent !== "function") return;
    const ev = new PgMouseEvent({ key: event.key, text: event.key.length === 1 ? event.key : "", modifiers: PgMouseEvent.modifiers(event) });
    this.focusItem.keyPressEvent(ev);
    if (ev.accepted) {
      event.preventDefault();
      event.stopPropagation();
      this.update();
    }
  }
}

class PgViewBox {
  static named = new Map();

  constructor({ name = null, invertY = false, lockAspect = false, enableMouse = true, enableMenu = true, defaultPadding = 0.02 } = {}) {
    this.name         = null;
    this.rect         = { x: 0, y: 0, w: 0, h: 0 };
    this.scene        = null;
    this.z            = -100;
    this.visible      = true;
    this.focusable    = true;
    this.items        = [];
    this.addedItems   = [];
    this.axHistory    = [];
    this.axHistoryPointer = -1;
    this.rbScaleBox   = { visible: false, x0: 0, y0: 0, x1: 0, y1: 0 };
    this.linksBlocked = false;
    this.updating     = false;
    this.needsAutoRange = true;
    this.parentMenus  = [];
    this.menu         = null;
    this.state = {
      targetRange     : [[0, 1], [0, 1]],
      viewRange       : [[0, 1], [0, 1]],
      yInverted       : invertY,
      xInverted       : false,
      aspectLocked    : false,
      autoRange       : [true, true],
      autoPan         : [false, false],
      autoVisibleOnly : [false, false],
      linkedViews     : [null, null],
      defaultPadding,
      mouseEnabled    : [enableMouse, enableMouse],
      mouseMode       : "pan",
      enableMenu,
      wheelScaleFactor: -1.0 / 8.0,
      limits          : { xLimits: [-1e307, 1e307], yLimits: [-1e307, 1e307], xRange: [null, null], yRange: [null, null] },
    };
    this.sigRangeChanged        = new PgSignal();
    this.sigXRangeChanged       = new PgSignal();
    this.sigYRangeChanged       = new PgSignal();
    this.sigStateChanged        = new PgSignal();
    this.sigResized             = new PgSignal();
    this.sigRangeChangedManually = new PgSignal();
    this.linkSlots = [null, null];
    this.setAspectLocked(lockAspect);
    this.register(name);
  }

  register(name) {
    if (this.name !== null && PgViewBox.named.get(this.name) === this) PgViewBox.named.delete(this.name);
    this.name = name;
    if (name !== null) PgViewBox.named.set(name, this);
  }

  attach(scene) {
    this.scene = scene;
    scene.sigPrepareForPaint.connect(() => this.prepareForPaint());
  }

  setGeometry(x, y, w, h) {
    const changed = w !== this.rect.w || h !== this.rect.h;
    this.rect = { x, y, w, h };
    if (!changed) return;
    this.linkedChanged(0);
    this.linkedChanged(1);
    this.queueUpdateAutoRange();
    this.updateViewRange();
    this.sigStateChanged.emit(this);
    this.sigResized.emit(this);
  }

  width() {
    return this.rect.w;
  }

  height() {
    return this.rect.h;
  }

  update() {
    if (this.scene) this.scene.update();
  }

  addItem(item, ignoreBounds = false) {
    if (item.z < this.z) item.z = this.z + 1;
    if (item.vb && item.vb !== this) item.vb.removeItem(item);
    item.vb = this;
    if (!this.items.includes(item)) this.items.push(item);
    if (!ignoreBounds && !this.addedItems.includes(item)) this.addedItems.push(item);
    this.queueUpdateAutoRange();
  }

  removeItem(item) {
    const a = this.addedItems.indexOf(item);
    if (a >= 0) this.addedItems.splice(a, 1);
    const i = this.items.indexOf(item);
    if (i >= 0) this.items.splice(i, 1);
    if (item.vb === this) item.vb = null;
    this.queueUpdateAutoRange();
  }

  viewRange() {
    return [this.state.viewRange[0].slice(), this.state.viewRange[1].slice()];
  }

  viewRect() {
    const [[x0, x1], [y0, y1]] = this.state.viewRange;
    return { x: x0, y: y0, w: x1 - x0, h: y1 - y0 };
  }

  targetRect() {
    const [[x0, x1], [y0, y1]] = this.state.targetRange;
    return { x: x0, y: y0, w: x1 - x0, h: y1 - y0 };
  }

  resetTarget() {
    this.state.targetRange = [this.state.viewRange[0].slice(), this.state.viewRange[1].slice()];
  }

  getAspectRatio() {
    const vr = this.viewRect();
    if (this.rect.h === 0 || vr.w === 0 || vr.h === 0) return 1.0;
    return (this.rect.w / this.rect.h) / (vr.w / vr.h);
  }

  setAspectLocked(lock = true, ratio = 1) {
    if (!lock) {
      if (this.state.aspectLocked === false) return;
      this.state.aspectLocked = false;
    } else {
      const current = this.getAspectRatio();
      const value   = ratio === null ? current : ratio;
      if (this.state.aspectLocked === value) return;
      this.state.aspectLocked = value;
      if (value !== current) this.updateViewRange();
    }
    this.queueUpdateAutoRange();
    this.updateViewRange();
    this.sigStateChanged.emit(this);
  }

  setRange({ rect = null, xRange = null, yRange = null, padding = null, disableAutoRange = true } = {}) {
    const changes      = {};
    const setRequested = [false, false];
    if (rect) {
      changes[0] = [rect.x, rect.x + rect.w];
      changes[1] = [rect.y, rect.y + rect.h];
      setRequested[0] = setRequested[1] = true;
    }
    if (xRange) {
      changes[0] = xRange;
      setRequested[0] = true;
    }
    if (yRange) {
      changes[1] = yRange;
      setRequested[1] = true;
    }
    if (Object.keys(changes).length === 0) throw new Error("Must specify at least one of rect, xRange, or yRange.");

    const changed = [false, false];
    if (disableAutoRange) this.enableAutoRangeXY(setRequested[0] ? false : null, setRequested[1] ? false : null);

    const limits = [this.state.limits.xLimits, this.state.limits.yLimits];
    const minRng = [this.state.limits.xRange[0], this.state.limits.yRange[0]];
    const maxRng = [this.state.limits.xRange[1], this.state.limits.yRange[1]];

    for (const key of Object.keys(changes)) {
      const ax  = Number(key);
      const rng = changes[key];
      let mn    = Math.min(rng[0], rng[1]);
      let mx    = Math.max(rng[0], rng[1]);
      let preserve = false;
      if (mn === mx) {
        preserve = true;
        let dy = this.state.viewRange[ax][1] - this.state.viewRange[ax][0];
        if (dy === 0) dy = 1;
        mn -= dy * 0.5;
        mx += dy * 0.5;
      }
      const quantization = (mn + mx) * 1.5e-15;
      if (mx - mn < 2 * quantization) {
        mn -= quantization;
        mx += quantization;
      }
      if (!Number.isFinite(mn) || !Number.isFinite(mx)) throw new Error(`Cannot set range [${mn}, ${mx}]`);
      if (!preserve) {
        const pad = padding === null ? this.suggestPadding(ax) : padding;
        const p   = (mx - mn) * pad;
        mn -= p;
        mx += p;
      }
      if (limits[ax][0] !== null && limits[ax][1] !== null) maxRng[ax] = maxRng[ax] !== null ? Math.min(maxRng[ax], limits[ax][1] - limits[ax][0]) : limits[ax][1] - limits[ax][0];
      if (maxRng[ax] !== null || minRng[ax] !== null) {
        const diff = mx - mn;
        let delta  = 0;
        if (maxRng[ax] !== null && diff > maxRng[ax]) delta = maxRng[ax] - diff;
        else if (minRng[ax] !== null && diff < minRng[ax]) delta = minRng[ax] - diff;
        mn -= delta / 2;
        mx += delta / 2;
      }
      const [lmn, lmx] = limits[ax];
      if (lmn !== null && mn < lmn) {
        const delta = lmn - mn;
        mn = lmn;
        mx += delta;
      } else if (lmx !== null && mx > lmx) {
        const delta = lmx - mx;
        mx = lmx;
        mn += delta;
      }
      const target = this.state.targetRange[ax];
      if (target[0] !== mn || target[1] !== mx) {
        this.state.targetRange[ax] = [mn, mx];
        changed[ax] = true;
      }
    }

    let lockX = setRequested[0];
    let lockY = setRequested[1];
    if (lockX && lockY) {
      lockX = false;
      lockY = false;
    }
    this.updateViewRange(lockX, lockY);
    if (changed[0] || changed[1] || disableAutoRange) {
      if (changed[0] && this.state.autoVisibleOnly[1] && this.state.autoRange[0] !== false) this.needsAutoRange = true;
      else if (changed[1] && this.state.autoVisibleOnly[0] && this.state.autoRange[1] !== false) this.needsAutoRange = true;
      this.sigStateChanged.emit(this);
    }
  }

  setXRange(mn, mx, padding = null) {
    this.setRange({ xRange: [mn, mx], padding });
  }

  setYRange(mn, mx, padding = null) {
    this.setRange({ yRange: [mn, mx], padding });
  }

  autoRange(padding = null) {
    const bounds = this.childrenBoundingRect();
    if (bounds) this.setRange({ rect: bounds, padding });
  }

  suggestPadding(axis) {
    const l   = axis === 0 ? this.rect.w : this.rect.h;
    const def = this.state.defaultPadding;
    if (def === 0) return def;
    const maxPad = Math.max(0.1, def);
    if (l > 0) return Math.min(Math.max(50 * def / Math.sqrt(l), def), maxPad);
    return def;
  }

  scaleBy({ s = null, center = null, x = null, y = null } = {}) {
    if (s !== null) {
      x = s[0];
      y = s[1];
    }
    const affect = [x !== null, y !== null];
    if (!affect[0] && !affect[1]) return;
    const scale = [x === null ? 1.0 : x, y === null ? 1.0 : y];
    if (this.state.aspectLocked !== false) {
      if (x === null) scale[0] = scale[1];
      else if (y === null) scale[1] = scale[0];
      else scale[0] = scale[1];
    }
    const vr = this.targetRect();
    const c  = center || { x: vr.x + vr.w / 2, y: vr.y + vr.h / 2 };
    const tl = { x: c.x + (vr.x - c.x) * scale[0], y: c.y + (vr.y - c.y) * scale[1] };
    const br = { x: c.x + (vr.x + vr.w - c.x) * scale[0], y: c.y + (vr.y + vr.h - c.y) * scale[1] };
    if (!affect[0]) this.setYRange(tl.y, br.y, 0);
    else if (!affect[1]) this.setXRange(tl.x, br.x, 0);
    else this.setRange({ rect: { x: tl.x, y: tl.y, w: br.x - tl.x, h: br.y - tl.y }, padding: 0 });
  }

  translateBy({ x = null, y = null } = {}) {
    const vr = this.targetRect();
    const xr = x !== null ? [vr.x + x, vr.x + vr.w + x] : null;
    const yr = y !== null ? [vr.y + y, vr.y + vr.h + y] : null;
    if (xr || yr) this.setRange({ xRange: xr, yRange: yr, padding: 0 });
  }

  enableAutoRangeXY(x, y) {
    if (x !== null) this.enableAutoRange(0, x);
    if (y !== null) this.enableAutoRange(1, y);
  }

  enableAutoRange(axis = null, enable = true) {
    const value = enable === true ? 1.0 : enable;
    const axes  = axis === null ? [0, 1] : [axis];
    for (const ax of axes) {
      if (this.state.autoRange[ax] !== value) {
        if (value === false && this.needsAutoRange) this.updateAutoRange();
        this.state.autoRange[ax] = value;
        this.needsAutoRange = this.needsAutoRange || value !== false;
        this.update();
      }
    }
    this.sigStateChanged.emit(this);
  }

  disableAutoRange(axis = null) {
    this.enableAutoRange(axis, false);
  }

  autoRangeEnabled() {
    return this.state.autoRange.slice();
  }

  setAutoPan(x = null, y = null) {
    if (x !== null) this.state.autoPan[0] = x;
    if (y !== null) this.state.autoPan[1] = y;
    if (x !== null || y !== null) this.queueUpdateAutoRange();
    this.sigStateChanged.emit(this);
  }

  setAutoVisible(x = null, y = null) {
    if (x !== null) {
      this.state.autoVisibleOnly[0] = x;
      if (x === true) this.state.autoVisibleOnly[1] = false;
    }
    if (y !== null) {
      this.state.autoVisibleOnly[1] = y;
      if (y === true) this.state.autoVisibleOnly[0] = false;
    }
    if (x !== null || y !== null) this.queueUpdateAutoRange();
    this.sigStateChanged.emit(this);
  }

  setMouseEnabled(x = null, y = null) {
    if (x !== null) this.state.mouseEnabled[0] = x;
    if (y !== null) this.state.mouseEnabled[1] = y;
    this.sigStateChanged.emit(this);
  }

  setMouseMode(mode) {
    this.state.mouseMode = mode;
    if (mode === "pan") this.rbScaleBox.visible = false;
    this.sigStateChanged.emit(this);
  }

  invertY(b = true) {
    this.invertAxis(1, b);
  }

  invertX(b = true) {
    this.invertAxis(0, b);
  }

  invertAxis(ax, inv) {
    const key = ax === 0 ? "xInverted" : "yInverted";
    if (this.state[key] === inv) return;
    this.state[key] = inv;
    this.updateViewRange();
    this.update();
    this.sigStateChanged.emit(this);
    if (ax) this.sigYRangeChanged.emit(this, this.state.viewRange[1].slice());
    else this.sigXRangeChanged.emit(this, this.state.viewRange[0].slice());
  }

  queueUpdateAutoRange() {
    this.needsAutoRange = true;
    this.update();
  }

  itemBoundsChanged() {
    if (this.state.autoRange[0] !== false || this.state.autoRange[1] !== false) this.queueUpdateAutoRange();
  }

  prepareForPaint() {
    if (this.needsAutoRange && this.rect.w > 0 && this.rect.h > 0) this.updateAutoRange();
  }

  updateAutoRange() {
    if (this.updating) return;
    this.updating = true;
    try {
      if (!this.state.autoRange.some((v) => v !== false)) return;
      const targetRect = this.viewRange();
      const fraction   = this.state.autoRange.map((v) => (typeof v === "boolean" ? 1.0 : v));
      let childRange   = null;
      const order      = this.state.autoVisibleOnly[0] === true ? [1, 0] : [0, 1];
      const args       = {};
      for (const ax of order) {
        if (this.state.autoRange[ax] === false) continue;
        if (this.state.autoVisibleOnly[ax]) {
          const ortho = [null, null];
          ortho[ax] = targetRect[1 - ax];
          childRange = this.childrenBounds(fraction, ortho);
        } else if (childRange === null) {
          childRange = this.childrenBounds(fraction, [null, null]);
        }
        const xr = childRange[ax];
        if (xr !== null) {
          if (this.state.autoPan[ax]) {
            const c  = (xr[0] + xr[1]) * 0.5;
            const w2 = (targetRect[ax][1] - targetRect[ax][0]) / 2;
            childRange[ax] = [c - w2, c + w2];
          } else {
            const padding = this.suggestPadding(ax);
            const wp      = (xr[1] - xr[0]) * padding;
            childRange[ax] = [xr[0] - wp, xr[1] + wp];
          }
          targetRect[ax] = childRange[ax];
          args[ax === 0 ? "xRange" : "yRange"] = targetRect[ax];
        }
      }
      for (const k of ["xRange", "yRange"]) {
        if (k in args && (!Number.isFinite(args[k][0]) || !Number.isFinite(args[k][1]))) delete args[k];
      }
      if (Object.keys(args).length === 0) return;
      this.setRange({ ...args, padding: 0.0, disableAutoRange: false });
    } finally {
      this.needsAutoRange = false;
      this.updating       = false;
    }
  }

  childrenBounds(frac = [1, 1], orthoRange = [null, null]) {
    const itemBounds = [];
    for (const item of this.addedItems) {
      if (!item.visible || item.vb !== this) continue;
      if (typeof item.dataBounds === "function") {
        let useX = true;
        let useY = true;
        let xr   = item.dataBounds(0, frac[0], orthoRange[0]);
        let yr   = item.dataBounds(1, frac[1], orthoRange[1]);
        const px = typeof item.pixelPadding === "function" ? item.pixelPadding() : 0;
        if (!xr || (xr[0] === null && xr[1] === null) || !Number.isFinite(xr[0]) || !Number.isFinite(xr[1])) {
          useX = false;
          xr   = [0, 0];
        }
        if (!yr || (yr[0] === null && yr[1] === null) || !Number.isFinite(yr[0]) || !Number.isFinite(yr[1])) {
          useY = false;
          yr   = [0, 0];
        }
        if (!useX && !useY) continue;
        let bounds = item.mapRectToView({ x: xr[0], y: yr[0], w: xr[1] - xr[0], h: yr[1] - yr[0] });
        if (useX !== useY) {
          const ang = Math.round(item.rotation || 0);
          if (ang === 90 || ang === 270) [useX, useY] = [useY, useX];
          else if (ang !== 0 && ang !== 180) continue;
        }
        itemBounds.push({ bounds, useX, useY, px });
      } else {
        const bounds = item.viewBounds();
        if (bounds) itemBounds.push({ bounds, useX: true, useY: true, px: 0 });
      }
    }

    const range = [null, null];
    for (const { bounds, useX, useY } of itemBounds) {
      if (useY) range[1] = range[1] ? [Math.min(bounds.y, range[1][0]), Math.max(bounds.y + bounds.h, range[1][1])] : [bounds.y, bounds.y + bounds.h];
      if (useX) range[0] = range[0] ? [Math.min(bounds.x, range[0][0]), Math.max(bounds.x + bounds.w, range[0][1])] : [bounds.x, bounds.x + bounds.w];
    }
    const w = this.rect.w;
    const h = this.rect.h;
    if (w > 0 && range[0]) {
      const pxSize = (range[0][1] - range[0][0]) / w;
      for (const { bounds, useX, px } of itemBounds) {
        if (px === 0 || !useX) continue;
        range[0][0] = Math.min(range[0][0], bounds.x - px * pxSize);
        range[0][1] = Math.max(range[0][1], bounds.x + bounds.w + px * pxSize);
      }
    }
    if (h > 0 && range[1]) {
      const pxSize = (range[1][1] - range[1][0]) / h;
      for (const { bounds, useY, px } of itemBounds) {
        if (px === 0 || !useY) continue;
        range[1][0] = Math.min(range[1][0], bounds.y - px * pxSize);
        range[1][1] = Math.max(range[1][1], bounds.y + bounds.h + px * pxSize);
      }
    }
    return range;
  }

  childrenBoundingRect() {
    const range = this.childrenBounds();
    const tr    = this.state.targetRange;
    if (!range[0]) range[0] = tr[0];
    if (!range[1]) range[1] = tr[1];
    return { x: range[0][0], y: range[1][0], w: range[0][1] - range[0][0], h: range[1][1] - range[1][0] };
  }

  updateViewRange(forceX = false, forceY = false) {
    const viewRange = [this.state.targetRange[0].slice(), this.state.targetRange[1].slice()];
    const aspect    = this.state.aspectLocked;
    const tr        = this.targetRect();
    const bounds    = this.rect;
    const limits    = [this.state.limits.xLimits, this.state.limits.yLimits];
    const minRng    = [this.state.limits.xRange[0], this.state.limits.yRange[0]];
    const maxRng    = [this.state.limits.xRange[1], this.state.limits.yRange[1]];

    for (const axis of [0, 1]) {
      if (limits[axis][0] !== null && limits[axis][1] !== null) maxRng[axis] = maxRng[axis] !== null ? Math.min(maxRng[axis], limits[axis][1] - limits[axis][0]) : limits[axis][1] - limits[axis][0];
    }

    if (aspect !== false && aspect !== 0 && tr.h !== 0 && bounds.h !== 0 && bounds.w !== 0) {
      const targetRatio = tr.h !== 0 ? tr.w / tr.h : 1;
      let viewRatio     = (bounds.h !== 0 ? bounds.w / bounds.h : 1) / aspect;
      viewRatio         = viewRatio === 0 ? 1 : viewRatio;
      const dy          = 0.5 * (tr.w / viewRatio - tr.h);
      const dx          = 0.5 * (tr.h * viewRatio - tr.w);
      const rangeY      = [this.state.targetRange[1][0] - dy, this.state.targetRange[1][1] + dy];
      const rangeX      = [this.state.targetRange[0][0] - dx, this.state.targetRange[0][1] + dx];
      const candidate   = [rangeX, rangeY];
      let ax;
      if (forceX) ax = 0;
      else if (forceY) ax = 1;
      else {
        ax = targetRatio > viewRatio ? 0 : 1;
        const target = ax === 1 ? 0 : 1;
        const diff   = candidate[target][1] - candidate[target][0];
        if ((maxRng[target] !== null && diff > maxRng[target]) || (minRng[target] !== null && diff < minRng[target])) {
          viewRange[ax] = candidate[ax];
          this.state.viewRange[ax] = viewRange[ax];
          this.resetTarget();
          ax = target;
        }
      }
      if (ax === 0) viewRange[1] = rangeY;
      else viewRange[0] = rangeX;
    }

    for (const axis of [0, 1]) {
      const span = viewRange[axis][1] - viewRange[axis][0];
      if (minRng[axis] !== null && minRng[axis] > span) {
        viewRange[axis][1] = viewRange[axis][0] + minRng[axis];
        this.state.targetRange[axis] = viewRange[axis];
      }
      if (maxRng[axis] !== null && maxRng[axis] < span) {
        viewRange[axis][1] = viewRange[axis][0] + maxRng[axis];
        this.state.targetRange[axis] = viewRange[axis];
      }
      if (limits[axis][0] !== null && viewRange[axis][0] < limits[axis][0]) {
        const delta = limits[axis][0] - viewRange[axis][0];
        viewRange[axis][0] += delta;
        viewRange[axis][1] += delta;
        this.state.targetRange[axis] = viewRange[axis];
      }
      if (limits[axis][1] !== null && viewRange[axis][1] > limits[axis][1]) {
        const delta = viewRange[axis][1] - limits[axis][1];
        viewRange[axis][0] -= delta;
        viewRange[axis][1] -= delta;
        this.state.targetRange[axis] = viewRange[axis];
      }
    }

    const changed = [0, 1].map((axis) => {
      const threshold = (viewRange[axis][1] - viewRange[axis][0]) * 1.0e-9;
      return Math.abs(viewRange[axis][0] - this.state.viewRange[axis][0]) > threshold || Math.abs(viewRange[axis][1] - this.state.viewRange[axis][1]) > threshold;
    });
    this.state.viewRange = viewRange;
    if (changed[0] || changed[1]) {
      this.update();
      for (const ax of [0, 1]) {
        if (!changed[ax]) continue;
        const link = this.linkedView(ax);
        if (link) link.linkedViewChanged(this, ax);
      }
      if (changed[0]) this.sigXRangeChanged.emit(this, this.state.viewRange[0].slice());
      if (changed[1]) this.sigYRangeChanged.emit(this, this.state.viewRange[1].slice());
      this.sigRangeChanged.emit(this, this.viewRange(), changed);
    }
  }

  linkedView(ax) {
    const v = this.state.linkedViews[ax];
    return v && typeof v !== "string" ? v : null;
  }

  linkView(axis, view) {
    let target = view;
    if (typeof target === "string") target = target === "" ? null : (PgViewBox.named.get(target) || target);
    const signal = axis === 0 ? "sigXRangeChanged" : "sigYRangeChanged";
    const old    = this.linkedView(axis);
    if (old && this.linkSlots[axis]) {
      old[signal].disconnect(this.linkSlots[axis]);
      old.sigResized.disconnect(this.linkSlots[axis]);
    }
    if (target === null || typeof target === "string") {
      this.state.linkedViews[axis] = target;
      this.linkSlots[axis]         = null;
    } else {
      const slot = () => this.linkedChanged(axis);
      this.state.linkedViews[axis] = target;
      this.linkSlots[axis]         = slot;
      target[signal].connect(slot);
      target.sigResized.connect(slot);
      if (target.autoRangeEnabled()[axis] !== false) {
        this.enableAutoRange(axis, false);
        slot();
      } else if (this.autoRangeEnabled()[axis] === false) {
        slot();
      }
    }
    this.sigStateChanged.emit(this);
  }

  linkedChanged(axis) {
    this.linkedViewChanged(this.linkedView(axis), axis);
  }

  screenGeometry() {
    if (!this.scene) return null;
    const r = this.scene.el.getBoundingClientRect();
    return { x: r.left + this.rect.x, y: r.top + this.rect.y, w: this.rect.w, h: this.rect.h };
  }

  linkedViewChanged(view, axis) {
    if (this.linksBlocked || !view) return;
    const vr = view.viewRect();
    const vg = view.screenGeometry();
    const sg = this.screenGeometry();
    if (!vg || !sg) return;
    view.linksBlocked = true;
    try {
      if (axis === 0) {
        const overlap = Math.min(sg.x + sg.w, vg.x + vg.w) - Math.max(sg.x, vg.x);
        let x1;
        let x2;
        if (overlap < Math.min(vg.w / 3, sg.w / 3)) {
          x1 = vr.x;
          x2 = vr.x + vr.w;
        } else {
          const upp = vr.w / vg.w;
          x1 = this.state.xInverted ? vr.x + (sg.x + sg.w - (vg.x + vg.w)) * upp : vr.x + (sg.x - vg.x) * upp;
          x2 = x1 + sg.w * upp;
        }
        this.enableAutoRange(0, false);
        this.setXRange(x1, x2, 0);
      } else {
        const overlap = Math.min(sg.y + sg.h, vg.y + vg.h) - Math.max(sg.y, vg.y);
        let y1;
        let y2;
        if (overlap < Math.min(vg.h / 3, sg.h / 3)) {
          y1 = vr.y;
          y2 = vr.y + vr.h;
        } else {
          const upp = vr.h / vg.h;
          y2 = this.state.yInverted ? vr.y + vr.h + (sg.y + sg.h - (vg.y + vg.h)) * upp : vr.y + vr.h + (sg.y - vg.y) * upp;
          y1 = y2 - sg.h * upp;
        }
        this.enableAutoRange(1, false);
        this.setYRange(y1, y2, 0);
      }
    } finally {
      view.linksBlocked = false;
    }
  }

  transform() {
    const vr = this.viewRect();
    let sx   = vr.w === 0 ? 1 : this.rect.w / vr.w;
    let sy   = vr.h === 0 ? 1 : this.rect.h / vr.h;
    if (!this.state.yInverted) sy = -sy;
    if (this.state.xInverted) sx = -sx;
    const cx = this.rect.x + this.rect.w / 2;
    const cy = this.rect.y + this.rect.h / 2;
    const vx = vr.x + vr.w / 2;
    const vy = vr.y + vr.h / 2;
    return { sx, sy, tx: cx - sx * vx, ty: cy - sy * vy };
  }

  mapViewToScene(x, y) {
    const t = this.transform();
    return { x: t.sx * x + t.tx, y: t.sy * y + t.ty };
  }

  mapSceneToView(x, y) {
    const t = this.transform();
    return { x: (x - t.tx) / t.sx, y: (y - t.ty) / t.sy };
  }

  viewPixelSize() {
    const t = this.transform();
    return [Math.abs(1 / t.sx), Math.abs(1 / t.sy)];
  }

  mapRectToView(rect) {
    return rect;
  }

  hit(x, y) {
    return x >= this.rect.x && x < this.rect.x + this.rect.w && y >= this.rect.y && y < this.rect.y + this.rect.h;
  }

  hitRect(x0, y0, x1, y1) {
    return x1 >= this.rect.x && x0 < this.rect.x + this.rect.w && y1 >= this.rect.y && y0 < this.rect.y + this.rect.h;
  }

  sceneItems() {
    const list = [{ item: this, z: this.z }];
    for (const item of this.items) {
      if (!item.visible) continue;
      for (const entry of item.sceneItems ? item.sceneItems() : []) list.push({ item: entry.item, z: this.z + entry.z });
    }
    return list;
  }

  paint(ctx) {
    if (this.rect.w <= 0 || this.rect.h <= 0) return;
    ctx.save();
    ctx.beginPath();
    ctx.rect(this.rect.x, this.rect.y, this.rect.w, this.rect.h);
    ctx.clip();
    const sorted = this.items.map((item, i) => ({ item, i })).sort((a, b) => (a.item.z - b.item.z) || (a.i - b.i));
    for (const { item } of sorted) {
      if (item.visible) item.paint(ctx, this);
    }
    if (this.rbScaleBox.visible) this.paintScaleBox(ctx);
    ctx.restore();
  }

  paintScaleBox(ctx) {
    const a = this.mapViewToScene(this.rbScaleBox.x0, this.rbScaleBox.y0);
    const b = this.mapViewToScene(this.rbScaleBox.x1, this.rbScaleBox.y1);
    const r = PgGeom.normRect(a.x, a.y, b.x, b.y);
    ctx.fillStyle   = "rgba(255, 255, 0, 0.392)";
    ctx.fillRect(r.x, r.y, r.w, r.h);
    ctx.strokeStyle = "rgb(255, 255, 100)";
    ctx.lineWidth   = 1;
    ctx.setLineDash([]);
    ctx.strokeRect(PgPen.crisp(r.x, 1), PgPen.crisp(r.y, 1), Math.round(r.w), Math.round(r.h));
  }

  localPos(scenePos) {
    return { x: scenePos.x - this.rect.x, y: scenePos.y - this.rect.y };
  }

  wheelEvent(ev, axis = null) {
    const mask = axis === 0 || axis === 1 ? [axis === 0 && this.state.mouseEnabled[0], axis === 1 && this.state.mouseEnabled[1]] : this.state.mouseEnabled.slice();
    if (!mask[0] && !mask[1]) {
      ev.ignore();
      return;
    }
    const s      = Math.pow(1.02, ev.delta * this.state.wheelScaleFactor);
    const center = this.mapSceneToView(ev.scenePos.x, ev.scenePos.y);
    this.resetTarget();
    this.scaleBy({ x: mask[0] ? s : null, y: mask[1] ? s : null, center });
    ev.accept();
    this.sigRangeChangedManually.emit(mask);
  }

  mouseClickEvent(ev) {
    if (ev.button === "right" && this.state.enableMenu) {
      ev.accept();
      this.raiseContextMenu(ev);
    }
  }

  raiseContextMenu(ev) {
    if (!this.menu) this.menu = new PgViewBoxMenu(this);
    this.menu.popup(ev.screenPos.x, ev.screenPos.y, ev);
  }

  mouseDragEvent(ev, axis = null) {
    ev.accept();
    const pos     = this.localPos(ev.scenePos);
    const lastPos = this.localPos(ev.lastScenePos);
    const dif     = { x: -(pos.x - lastPos.x), y: -(pos.y - lastPos.y) };
    const enabled = this.state.mouseEnabled.map((v) => (v ? 1 : 0));
    const mask    = enabled.slice();
    if (axis !== null) mask[1 - axis] = 0;

    if (ev.button === "left" || ev.button === "middle") {
      if (this.state.mouseMode === "rect" && axis === null) {
        if (ev.isFinish()) {
          this.rbScaleBox.visible = false;
          const a  = this.mapSceneToView(ev.buttonDownScenePos.x, ev.buttonDownScenePos.y);
          const b  = this.mapSceneToView(ev.scenePos.x, ev.scenePos.y);
          const ax = PgGeom.normRect(a.x, a.y, b.x, b.y);
          this.showAxRect(ax);
          this.axHistoryPointer += 1;
          this.axHistory = [...this.axHistory.slice(0, this.axHistoryPointer), ax];
        } else {
          this.updateScaleBox(ev.buttonDownScenePos, ev.scenePos);
        }
      } else {
        const t = this.transform();
        const x = mask[0] === 1 ? (dif.x * mask[0]) / t.sx : null;
        const y = mask[1] === 1 ? (dif.y * mask[1]) / t.sy : null;
        this.resetTarget();
        if (x !== null || y !== null) this.translateBy({ x, y });
        this.sigRangeChangedManually.emit(this.state.mouseEnabled);
      }
    } else if (ev.button === "right") {
      if (this.state.aspectLocked !== false) mask[0] = 0;
      const d  = [-(ev.screenPos.x - ev.lastScreenPos.x), ev.screenPos.y - ev.lastScreenPos.y];
      const s  = [Math.pow(mask[0] * 0.02 + 1, d[0]), Math.pow(mask[1] * 0.02 + 1, d[1])];
      const x  = enabled[0] === 1 ? s[0] : null;
      const y  = enabled[1] === 1 ? s[1] : null;
      const center = this.mapSceneToView(ev.buttonDownScenePos.x, ev.buttonDownScenePos.y);
      this.resetTarget();
      this.scaleBy({ x, y, center });
      this.sigRangeChangedManually.emit(this.state.mouseEnabled);
    }
  }

  keyPressEvent(ev) {
    ev.accept();
    if (ev.text === "-") this.scaleHistory(-1);
    else if (ev.text === "+" || ev.text === "=") this.scaleHistory(1);
    else if (ev.key === "Backspace") this.scaleHistory(this.axHistory.length);
    else ev.ignore();
  }

  scaleHistory(d) {
    if (this.axHistory.length === 0) return;
    const ptr = Math.max(0, Math.min(this.axHistory.length - 1, this.axHistoryPointer + d));
    if (ptr !== this.axHistoryPointer) {
      this.axHistoryPointer = ptr;
      this.showAxRect(this.axHistory[ptr]);
    }
  }

  updateScaleBox(p1, p2) {
    const a = this.mapSceneToView(p1.x, p1.y);
    const b = this.mapSceneToView(p2.x, p2.y);
    this.rbScaleBox = { visible: true, x0: a.x, y0: a.y, x1: b.x, y1: b.y };
    this.update();
  }

  showAxRect(ax) {
    this.setRange({ rect: ax });
    this.sigRangeChangedManually.emit(this.state.mouseEnabled);
  }

  getContextMenus() {
    return this.parentMenus;
  }
}

class PgImageItem {
  constructor() {
    this.vb        = null;
    this.z         = 0;
    this.visible   = true;
    this.image     = null;
    this.shape     = null;
    this.dtype     = null;
    this.levels    = [0, 1];
    this.lut       = null;
    this.canvas    = document.createElement("canvas");
    this.rendered  = false;
    this.sigImageChanged = new PgSignal();
  }

  setImage(data, shape, dtype) {
    const shapeChanged = !this.shape || this.shape.length !== shape.length || this.shape.some((v, i) => v !== shape[i]);
    this.image    = data;
    this.shape    = shape.slice();
    this.dtype    = dtype;
    this.rendered = false;
    if (shapeChanged && this.vb) this.vb.itemBoundsChanged(this);
    if (this.vb) this.vb.update();
    this.sigImageChanged.emit();
  }

  clear() {
    this.image    = null;
    this.shape    = null;
    this.rendered = false;
    if (this.vb) {
      this.vb.itemBoundsChanged(this);
      this.vb.update();
    }
  }

  width() {
    return this.image ? this.shape[0] : null;
  }

  height() {
    return this.image ? this.shape[1] : null;
  }

  channels() {
    if (!this.image) return null;
    return this.shape.length === 3 ? this.shape[2] : 1;
  }

  setLevels(levels) {
    this.levels   = levels;
    this.rendered = false;
    if (this.vb) this.vb.update();
  }

  getLevels() {
    return this.levels;
  }

  setLookupTable(lut) {
    this.lut      = lut;
    this.rendered = false;
    if (this.vb) this.vb.update();
  }

  viewBounds() {
    if (!this.image) return null;
    return { x: 0, y: 0, w: this.shape[0], h: this.shape[1] };
  }

  rgba() {
    const w    = this.shape[0];
    const h    = this.shape[1];
    const out  = new Uint8ClampedArray(w * h * 4);
    const data = this.image;
    const f    = Math.fround;

    if (this.shape.length === 2) {
      const [lo, hi] = this.levels;
      const lut      = this.lut;
      const n        = lut ? lut.length / 3 : 256;
      const rng      = hi - lo === 0 ? 1 : hi - lo;
      const scale    = f((lut ? n : 255.0) / rng);
      const offset   = f(lo);
      for (let x = 0; x < w; x += 1) {
        for (let y = 0; y < h; y += 1) {
          const v = data[x * h + y];
          const o = (y * w + x) * 4;
          if (Number.isNaN(v)) {
            out[o + 3] = 0;
            continue;
          }
          let t = f(f(v - offset) * scale);
          t = t < 0 ? 0 : (t > n - 1 ? n - 1 : t);
          const idx = Math.trunc(t);
          if (lut) {
            out[o]     = lut[idx * 3];
            out[o + 1] = lut[idx * 3 + 1];
            out[o + 2] = lut[idx * 3 + 2];
          } else {
            out[o] = out[o + 1] = out[o + 2] = idx;
          }
          out[o + 3] = 255;
        }
      }
      return out;
    }

    const nch    = this.shape[2];
    const perCh  = Array.isArray(this.levels[0]);
    const scales = [];
    const offs   = [];
    for (let c = 0; c < 3; c += 1) {
      const [lo, hi] = perCh ? this.levels[Math.min(c, this.levels.length - 1)] : this.levels;
      const rng      = hi - lo === 0 ? 1 : hi - lo;
      scales.push(f(255.0 / rng));
      offs.push(f(lo));
    }
    for (let x = 0; x < w; x += 1) {
      for (let y = 0; y < h; y += 1) {
        const base = (x * h + y) * nch;
        const o    = (y * w + x) * 4;
        let nan    = false;
        for (let c = 0; c < 3; c += 1) {
          const v = data[base + c];
          if (Number.isNaN(v)) nan = true;
          let t = f(f(v - offs[c]) * scales[c]);
          t = t < 0 ? 0 : (t > 255 ? 255 : t);
          out[o + c] = Math.trunc(t);
        }
        out[o + 3] = nan ? 0 : 255;
      }
    }
    return out;
  }

  render() {
    if (!this.image) return;
    const w = this.shape[0];
    const h = this.shape[1];
    if (this.canvas.width !== w || this.canvas.height !== h) {
      this.canvas.width  = w;
      this.canvas.height = h;
    }
    const ctx = this.canvas.getContext("2d");
    ctx.putImageData(new ImageData(this.rgba(), w, h), 0, 0);
    this.rendered = true;
  }

  paint(ctx, vb) {
    if (!this.image || this.shape[0] === 0 || this.shape[1] === 0) return;
    if (!this.rendered) this.render();
    const t = vb.transform();
    ctx.save();
    ctx.imageSmoothingEnabled = false;
    ctx.transform(t.sx, 0, 0, t.sy, t.tx, t.ty);
    ctx.drawImage(this.canvas, 0, 0, this.shape[0], this.shape[1]);
    ctx.restore();
  }

  stepData() {
    const s0   = Math.max(1, Math.ceil(this.shape[0] / 200));
    const s1   = Math.max(1, Math.ceil(this.shape[1] / 200));
    const nch  = this.shape.length === 3 ? this.shape[2] : 1;
    const h    = this.shape[1];
    const rows = [];
    for (let x = 0; x < this.shape[0]; x += s0) {
      for (let y = 0; y < this.shape[1]; y += s1) rows.push((x * h + y) * nch);
    }
    return { rows, nch };
  }

  static histogram(values, edges) {
    const counts = new Array(edges.length - 1).fill(0);
    const last   = edges.length - 1;
    for (const v of values) {
      if (v < edges[0] || v > edges[last]) continue;
      let lo = 0;
      let hi = last;
      if (v === edges[last]) {
        counts[last - 1] += 1;
        continue;
      }
      while (hi - lo > 1) {
        const mid = (lo + hi) >> 1;
        if (edges[mid] <= v) lo = mid;
        else hi = mid;
      }
      counts[lo] += 1;
    }
    return counts;
  }

  getHistogram(perChannel = false) {
    if (!this.image || this.shape[0] * this.shape[1] === 0) return null;
    const { rows, nch } = this.stepData();
    const data = this.image;
    let mn = Infinity;
    let mx = -Infinity;
    let any = false;
    for (const base of rows) {
      for (let c = 0; c < nch; c += 1) {
        const v = data[base + c];
        if (Number.isNaN(v)) continue;
        any = true;
        if (v < mn) mn = v;
        if (v > mx) mx = v;
      }
    }
    if (!any) return null;
    if (mx === mn) mx += 1;

    let edges;
    if (this.dtype === "uint8") {
      const step = Math.ceil((mx - mn) / 500.0);
      edges = [];
      if (step > 0) {
        for (let v = mn; v < mx + 1.01 * step; v += step) edges.push(v);
      }
      if (edges.length === 0) edges = [mn, mx];
    } else {
      edges = PgImageItem.linspace(mn, mx, 500);
    }
    const centers = edges.slice(0, -1);

    if (perChannel) {
      const out = [];
      for (let c = 0; c < nch; c += 1) {
        const values = [];
        for (const base of rows) {
          const v = data[base + c];
          if (Number.isFinite(v)) values.push(v);
        }
        out.push([centers, PgImageItem.histogram(values, edges)]);
      }
      return out;
    }
    const values = [];
    for (const base of rows) {
      for (let c = 0; c < nch; c += 1) {
        const v = data[base + c];
        if (Number.isFinite(v)) values.push(v);
      }
    }
    return [centers, PgImageItem.histogram(values, edges)];
  }

  static linspace(start, stop, num) {
    const out  = new Array(num);
    const div  = num - 1;
    const step = (stop - start) / div;
    for (let i = 0; i < num; i += 1) out[i] = i * step + start;
    if (num > 1) out[num - 1] = stop;
    return out;
  }

  toCanvas() {
    if (!this.rendered) this.render();
    return this.canvas;
  }
}

class PgAxisItem {
  static FONT = "15px 'Noto Sans', 'DejaVu Sans', sans-serif";

  constructor(orientation, { linkView = null, maxTickLength = -5, pen = "d", textPen = "d" } = {}) {
    this.orientation = orientation;
    this.rect        = { x: 0, y: 0, w: 0, h: 0 };
    this.scene       = null;
    this.z           = 0;
    this.visible     = true;
    this.range       = [0, 1];
    this.pen         = PgPen.mk(pen);
    this.textPen     = PgPen.mk(textPen);
    this.style       = {
      tickTextOffset      : [5, 2],
      tickLength          : maxTickLength,
      maxTickLevel        : 2,
      maxTextLevel        : 2,
      textFillLimits      : [[0, 0.8], [2, 0.6], [4, 0.4], [6, 0.2]],
      hideOverlappingLabels: orientation === "top" || orientation === "bottom",
    };
    this.textWidth   = 30;
    this.textHeight  = 18;
    this.logMode     = false;
    this.grid        = false;
    this.scale       = 1.0;
    this.label       = "";
    this.sigSizeChanged = new PgSignal();
    this.linked      = null;
    if (linkView) this.linkToView(linkView);
  }

  linkToView(view) {
    this.linked = view;
    const slot  = () => this.linkedViewChanged(view);
    if (this.orientation === "left" || this.orientation === "right") view.sigYRangeChanged.connect(slot);
    else view.sigXRangeChanged.connect(slot);
    view.sigResized.connect(slot);
  }

  linkedViewChanged(view) {
    const vertical = this.orientation === "left" || this.orientation === "right";
    const range    = view.viewRange()[vertical ? 1 : 0];
    const inverted = vertical ? view.state.yInverted : view.state.xInverted;
    this.setRange(...(inverted ? [range[1], range[0]] : range));
  }

  setRange(mn, mx) {
    if (!Number.isFinite(mn) || !Number.isFinite(mx)) throw new Error(`Not setting range to [${mn}, ${mx}]`);
    this.range = [mn, mx];
    if (this.scene) this.scene.update();
  }

  setGeometry(x, y, w, h) {
    this.rect = { x, y, w, h };
  }

  preferredWidth() {
    if (!this.visible) return 0;
    return this.textWidth + this.style.tickTextOffset[0] + Math.max(0, this.style.tickLength) + (this.label ? 18 * 0.8 : 0);
  }

  preferredHeight() {
    if (!this.visible) return 0;
    return this.textHeight + this.style.tickTextOffset[1] + Math.max(0, this.style.tickLength) + (this.label ? 18 * 0.8 : 0);
  }

  tickSpacing(minVal, maxVal, size) {
    const dif = Math.abs(maxVal - minVal);
    if (dif === 0) return [];
    const minIntervals = Math.max(2.25, 2.25 * Math.sqrt(size / 300.0));
    const majorMax     = dif / minIntervals;
    const exp2         = PgAxisItem.frexpExponent(majorMax);
    let p10unit        = Math.pow(10.0, Math.floor((exp2 - 1) / 3.32192809488736) - 1);
    let majorFactor;
    if (100.0 * p10unit <= majorMax) {
      majorFactor = 10;
      p10unit    *= 10.0;
    } else {
      for (majorFactor of [50, 20, 10]) {
        if (majorFactor * p10unit <= majorMax) break;
      }
    }
    const majorInterval = majorFactor * p10unit;
    const levels        = [[majorInterval, 0]];
    let minorInterval   = majorInterval;
    const minorMin      = 2 * dif / size;
    if (this.style.maxTickLevel >= 1) {
      for (const factor of majorFactor === 10 ? [5, 10] : [10, 20, 50]) {
        minorInterval = factor * p10unit;
        if (minorInterval >= minorMin) break;
      }
      levels.push([minorInterval, 0]);
    }
    if (this.style.maxTickLevel >= 2) {
      let trials;
      if (majorFactor === 10) trials = [1, 2, 5, 10];
      else if (majorFactor === 20) trials = [2, 5, 10, 20];
      else trials = [5, 10, 50];
      let extra = minorInterval;
      for (const factor of trials) {
        extra = factor * p10unit;
        if (extra >= minorMin || extra === minorInterval) break;
      }
      if (extra < minorInterval) levels.push([extra, 0]);
    }
    return levels;
  }

  static frexpExponent(value) {
    if (value === 0 || !Number.isFinite(value)) return 0;
    let exp = Math.floor(Math.log2(Math.abs(value))) + 1;
    const m = Math.abs(value) / Math.pow(2, exp);
    if (m >= 1) exp += 1;
    else if (m < 0.5) exp -= 1;
    return exp;
  }

  tickValues(minVal, maxVal, size) {
    let lo = Math.min(minVal, maxVal) * this.scale;
    let hi = Math.max(minVal, maxVal) * this.scale;
    const ticks  = [];
    let all      = [];
    for (const [spacing, offset] of this.tickSpacing(lo, hi, size)) {
      const start = Math.ceil((lo - offset) / spacing) * spacing + offset;
      const num   = Math.trunc((hi - start) / spacing) + 1;
      let values  = [];
      for (let i = 0; i < num; i += 1) values.push((i * spacing + start) / this.scale);
      const tol = spacing / this.scale * 0.01;
      values    = values.filter((v) => !all.some((a) => Math.abs(a - v) <= tol));
      all       = all.concat(values);
      ticks.push([spacing / this.scale, values]);
    }
    if (this.logMode) return this.logTickValues(lo, hi, ticks);
    return ticks;
  }

  logTickValues(minVal, maxVal, stdTicks) {
    const ticks = stdTicks.filter(([spacing]) => spacing >= 1.0);
    if (ticks.length < 3) {
      const v1    = Math.floor(minVal);
      const v2    = Math.ceil(maxVal);
      const minor = [];
      for (let v = v1; v < v2; v += 1) {
        for (let k = 1; k < 10; k += 1) minor.push(v + Math.log10(k));
      }
      ticks.push([null, minor.filter((x) => x > minVal && x < maxVal)]);
    }
    return ticks;
  }

  tickStrings(values, scale, spacing) {
    if (this.logMode) return this.logTickStrings(values, scale, spacing);
    const places = Math.max(0, Math.ceil(-Math.log10(spacing * scale)));
    return values.map((v) => {
      const vs = v * scale;
      if (Math.abs(vs) < 0.001 || Math.abs(vs) >= 10000) return PgFormat.g(vs, 6);
      return PgFormat.fixed(vs, places);
    });
  }

  logTickStrings(values, scale, spacing) {
    const estrings = values.map((x) => PgFormat.g(Math.pow(10, x), 6));
    return estrings;
  }

  span() {
    const r = this.rect;
    if (this.orientation === "left") return [{ x: r.x + r.w - 1, y: r.y - 1 }, { x: r.x + r.w - 1, y: r.y + r.h + 1 }];
    if (this.orientation === "right") return [{ x: r.x + 1, y: r.y - 1 }, { x: r.x + 1, y: r.y + r.h + 1 }];
    if (this.orientation === "top") return [{ x: r.x - 1, y: r.y + r.h - 1 }, { x: r.x + r.w + 1, y: r.y + r.h - 1 }];
    return [{ x: r.x - 1, y: r.y + 1 }, { x: r.x + r.w + 1, y: r.y + 1 }];
  }

  drawSpecs(ctx) {
    const r      = this.rect;
    const span   = this.span();
    const length = Math.hypot(span[1].x - span[0].x, span[1].y - span[0].y);
    if (length === 0) return null;
    const vertical = this.orientation === "left" || this.orientation === "right";
    const axis     = vertical ? 0 : 1;
    let tickStart;
    let tickStop;
    let tickDir;
    if (this.orientation === "left") [tickStart, tickStop, tickDir] = [r.x + r.w, r.x + r.w, -1];
    else if (this.orientation === "right") [tickStart, tickStop, tickDir] = [r.x, r.x, 1];
    else if (this.orientation === "top") [tickStart, tickStop, tickDir] = [r.y + r.h, r.y + r.h, -1];
    else [tickStart, tickStop, tickDir] = [r.y, r.y, 1];

    const tickLevels = this.tickValues(this.range[0], this.range[1], length);
    const dif        = this.range[1] - this.range[0];
    let xScale;
    let offset;
    if (dif === 0) {
      xScale = 1;
      offset = 0;
    } else if (axis === 0) {
      xScale = -r.h / dif;
      offset = this.range[0] * xScale - r.h;
    } else {
      xScale = r.w / dif;
      offset = this.range[0] * xScale;
    }
    const base   = axis === 0 ? r.y : r.x;
    const xRange = this.range.map((x) => x * xScale - offset);
    const xMin   = Math.min(...xRange);
    const xMax   = Math.max(...xRange);

    const tickPositions = [];
    const tickSpecs     = [];
    tickLevels.forEach(([, ticks], i) => {
      tickPositions.push([]);
      const tickLength = this.style.tickLength / (i * 0.5 + 1.0);
      const alpha      = 255 / (i + 1);
      for (const v of ticks) {
        const x = v * xScale - offset;
        if (x < xMin || x > xMax) {
          tickPositions[i].push(null);
          continue;
        }
        tickPositions[i].push(x);
        const p1 = axis === 0 ? { x: tickStart, y: base + x } : { x: base + x, y: tickStart };
        const p2 = axis === 0 ? { x: tickStop + tickLength * tickDir, y: base + x } : { x: base + x, y: tickStop + tickLength * tickDir };
        tickSpecs.push({ alpha, p1, p2 });
      }
    });

    const textSpecs = [];
    ctx.font = PgAxisItem.FONT;
    const textOffset = this.style.tickTextOffset[axis];
    let lastTextSize2 = 0;
    const textRects   = [];
    for (let i = 0; i < Math.min(tickLevels.length, this.style.maxTextLevel + 1); i += 1) {
      const [spacing, values] = tickLevels[i];
      const strings = this.tickStrings(values, this.scale, spacing);
      if (strings.length === 0) continue;
      const rects = strings.map((s, j) => {
        if (tickPositions[i][j] === null) return null;
        const m   = ctx.measureText(s);
        const rect = { w: Math.ceil(m.width), h: Math.ceil((m.fontBoundingBoxAscent + m.fontBoundingBoxDescent) * 0.8) };
        textRects.push(rect);
        return rect;
      });
      const textSize  = textRects.reduce((acc, rect) => acc + (axis === 0 ? rect.h : rect.w), 0);
      const textSize2 = textRects.length ? Math.max(...textRects.map((rect) => (axis === 0 ? rect.w : rect.h))) : 0;
      if (i > 0) {
        const ratio  = textSize / length;
        let finished = false;
        for (const [nTexts, limit] of this.style.textFillLimits) {
          if (textSpecs.length >= nTexts && ratio >= limit) {
            finished = true;
            break;
          }
        }
        if (finished) break;
      }
      lastTextSize2 = textSize2;
      strings.forEach((s, j) => {
        const x = tickPositions[i][j];
        if (x === null) return;
        const rect   = rects[j];
        const offs   = Math.max(0, this.style.tickLength) + textOffset;
        let box;
        let align;
        if (this.orientation === "left") [box, align] = [{ x: tickStop - offs - rect.w, y: base + x - rect.h / 2, w: rect.w, h: rect.h }, "right"];
        else if (this.orientation === "right") [box, align] = [{ x: tickStop + offs, y: base + x - rect.h / 2, w: rect.w, h: rect.h }, "left"];
        else if (this.orientation === "top") [box, align] = [{ x: base + x - rect.w / 2, y: tickStop - offs - rect.h, w: rect.w, h: rect.h }, "center"];
        else [box, align] = [{ x: base + x - rect.w / 2, y: tickStop + offs, w: rect.w, h: rect.h }, "center"];
        if (!this.boundsContain(box)) return;
        textSpecs.push({ box, align, text: s });
      });
    }
    this.updateMaxTextSize(lastTextSize2);
    return { span, tickSpecs, textSpecs };
  }

  boundsContain(box) {
    const m = this.style.hideOverlappingLabels ? 0 : 15;
    const r = this.rect;
    let b;
    if (this.orientation === "left" || this.orientation === "right") b = { x: r.x, y: r.y - m, w: r.w, h: r.h + 2 * m };
    else b = { x: r.x - m, y: r.y, w: r.w + 2 * m, h: r.h };
    return box.x >= b.x - 0.5 && box.y >= b.y - 0.5 && box.x + box.w <= b.x + b.w + 0.5 && box.y + box.h <= b.y + b.h + 0.5;
  }

  updateMaxTextSize(x) {
    const vertical = this.orientation === "left" || this.orientation === "right";
    if (vertical) {
      if (x > this.textWidth || x < this.textWidth - 10) {
        this.textWidth = x;
        this.sigSizeChanged.emit(this);
      }
    } else if (x > this.textHeight || x < this.textHeight - 10) {
      this.textHeight = x;
      this.sigSizeChanged.emit(this);
    }
  }

  paint(ctx) {
    if (!this.visible || this.rect.w <= 0 || this.rect.h <= 0) return;
    const specs = this.drawSpecs(ctx);
    if (!specs) return;
    ctx.save();
    ctx.lineWidth = 1;
    ctx.setLineDash([]);
    ctx.strokeStyle = PgPen.css(this.pen.color);
    ctx.beginPath();
    const vertical = this.orientation === "left" || this.orientation === "right";
    if (vertical) {
      const x = PgPen.crisp(specs.span[0].x, 1);
      ctx.moveTo(x, specs.span[0].y);
      ctx.lineTo(x, specs.span[1].y);
    } else {
      const y = PgPen.crisp(specs.span[0].y, 1);
      ctx.moveTo(specs.span[0].x, y);
      ctx.lineTo(specs.span[1].x, y);
    }
    ctx.stroke();
    for (const tick of specs.tickSpecs) {
      ctx.strokeStyle = PgPen.css([this.pen.color[0], this.pen.color[1], this.pen.color[2], Math.trunc(tick.alpha)]);
      ctx.beginPath();
      if (vertical) {
        const y = PgPen.crisp(tick.p1.y, 1);
        ctx.moveTo(tick.p1.x, y);
        ctx.lineTo(tick.p2.x, y);
      } else {
        const x = PgPen.crisp(tick.p1.x, 1);
        ctx.moveTo(x, tick.p1.y);
        ctx.lineTo(x, tick.p2.y);
      }
      ctx.stroke();
    }
    ctx.font         = PgAxisItem.FONT;
    ctx.fillStyle    = PgPen.css(this.textPen.color);
    ctx.textBaseline = "middle";
    for (const spec of specs.textSpecs) {
      ctx.textAlign = spec.align;
      const x = spec.align === "right" ? spec.box.x + spec.box.w : (spec.align === "left" ? spec.box.x : spec.box.x + spec.box.w / 2);
      ctx.fillText(spec.text, x, spec.box.y + spec.box.h / 2);
    }
    ctx.restore();
  }

  hit(x, y) {
    return this.visible && x >= this.rect.x && x < this.rect.x + this.rect.w && y >= this.rect.y && y < this.rect.y + this.rect.h;
  }

  hitRect(x0, y0, x1, y1) {
    return this.visible && x1 >= this.rect.x && x0 < this.rect.x + this.rect.w && y1 >= this.rect.y && y0 < this.rect.y + this.rect.h;
  }

  sceneItems() {
    return this.visible ? [{ item: this, z: this.z }] : [];
  }

  wheelEvent(ev) {
    const lv = this.linked;
    if (!lv) return;
    if (lv.hit(ev.scenePos.x, ev.scenePos.y)) {
      ev.ignore();
      return;
    }
    lv.wheelEvent(ev, this.orientation === "left" || this.orientation === "right" ? 1 : 0);
    ev.accept();
  }

  mouseDragEvent(ev) {
    const lv = this.linked;
    if (!lv) return;
    if (lv.hit(ev.buttonDownScenePos.x, ev.buttonDownScenePos.y)) {
      ev.ignore();
      return;
    }
    lv.mouseDragEvent(ev, this.orientation === "left" || this.orientation === "right" ? 1 : 0);
  }

  mouseClickEvent(ev) {
    if (this.linked) this.linked.mouseClickEvent(ev);
  }
}

class PgPlotCurve {
  constructor({ pen = "w", brush = null, fillLevel = null, rotation = 0, composition = null, antialias = false, name = null } = {}) {
    this.vb          = null;
    this.z           = 0;
    this.visible     = true;
    this.x           = [];
    this.y           = [];
    this.pen         = PgPen.mk(pen);
    this.brush       = brush ? PgPen.color(brush) : null;
    this.fillLevel   = fillLevel;
    this.rotation    = rotation;
    this.composition = composition;
    this.antialias   = antialias;
    this.alpha       = 1.0;
    this.curveName   = name;
  }

  setData(x, y) {
    this.x = Array.from(x);
    this.y = Array.from(y);
    if (this.vb) this.vb.itemBoundsChanged(this);
    if (this.vb) this.vb.update();
  }

  setPen(pen) {
    this.pen = PgPen.mk(pen);
    if (this.vb) this.vb.update();
  }

  name() {
    return this.curveName;
  }

  getData() {
    return [this.x, this.y];
  }

  mapPoint(x, y) {
    if (this.rotation === 90) return { x: -y, y: x };
    return { x, y };
  }

  mapRectToView(rect) {
    if (this.rotation !== 90) return rect;
    const a = this.mapPoint(rect.x, rect.y);
    const b = this.mapPoint(rect.x + rect.w, rect.y + rect.h);
    return PgGeom.normRect(a.x, a.y, b.x, b.y);
  }

  static percentile(sorted, q) {
    if (sorted.length === 0) return NaN;
    const pos = (sorted.length - 1) * q / 100;
    const lo  = Math.floor(pos);
    const hi  = Math.ceil(pos);
    return sorted[lo] + (sorted[hi] - sorted[lo]) * (pos - lo);
  }

  dataBounds(ax, frac = 1.0, orthoRange = null) {
    if (this.x.length === 0) return null;
    let d  = ax === 0 ? this.x : this.y;
    const d2 = ax === 0 ? this.y : this.x;
    if (orthoRange) d = d.filter((_, i) => d2[i] >= orthoRange[0] && d2[i] <= orthoRange[1]);
    const finite = d.filter((v) => Number.isFinite(v));
    if (finite.length === 0) return null;
    let b;
    if (frac >= 1.0) b = [Math.min(...finite), Math.max(...finite)];
    else {
      const sorted = finite.slice().sort((p, q) => p - q);
      b = [PgPlotCurve.percentile(sorted, 50 * (1 - frac)), PgPlotCurve.percentile(sorted, 50 * (1 + frac))];
    }
    if (ax === 1 && this.fillLevel !== null) b = [Math.min(b[0], this.fillLevel), Math.max(b[1], this.fillLevel)];
    return b;
  }

  pixelPadding() {
    let w = this.pen ? this.pen.width * 0.7072 : 0;
    if (this.antialias) w += 1;
    return w;
  }

  sceneItems() {
    return [];
  }

  paint(ctx, vb) {
    if (this.x.length === 0) return;
    ctx.save();
    if (this.composition === "plus") ctx.globalCompositeOperation = "lighter";
    ctx.globalAlpha = this.alpha;
    const pts = this.x.map((x, i) => {
      const p = this.mapPoint(x, this.y[i]);
      return vb.mapViewToScene(p.x, p.y);
    });
    if (this.brush && this.fillLevel !== null) {
      const first = this.mapPoint(this.x[0], this.fillLevel);
      const last  = this.mapPoint(this.x[this.x.length - 1], this.fillLevel);
      const a     = vb.mapViewToScene(first.x, first.y);
      const b     = vb.mapViewToScene(last.x, last.y);
      ctx.beginPath();
      ctx.moveTo(a.x, a.y);
      for (const p of pts) ctx.lineTo(p.x, p.y);
      ctx.lineTo(b.x, b.y);
      ctx.closePath();
      ctx.fillStyle = PgPen.css(this.brush);
      ctx.fill();
    }
    if (this.pen) {
      PgPen.apply(ctx, this.pen);
      ctx.beginPath();
      let started = false;
      for (const p of pts) {
        if (!Number.isFinite(p.x) || !Number.isFinite(p.y)) {
          started = false;
          continue;
        }
        if (started) ctx.lineTo(p.x, p.y);
        else ctx.moveTo(p.x, p.y);
        started = true;
      }
      ctx.stroke();
    }
    ctx.restore();
  }
}

class PgViewBoxMenu {
  constructor(view) {
    this.view  = view;
    this.menu  = null;
    this.ctrls = [null, null];
    this.view.sigStateChanged.connect(() => this.viewStateChanged());
  }

  ctx() {
    return TomoVisDialogs.current.ctx;
  }

  viewList() {
    const names = [...PgViewBox.named.entries()].filter(([, v]) => v !== this.view).map(([name]) => name).sort();
    return ["", ...names];
  }

  axisWidget(axis) {
    const kit   = this.ctx().kit;
    const view  = this.view;
    const root  = TomoVisInput.el("div", "tv-pg-axisctrl");
    const ctrl  = {};
    const group = `tv-pg-axis-${axis}-${Math.random().toString(36).slice(2)}`;

    ctrl.manual   = kit.local("radio", { group, text: "Manual", onChange: () => view.enableAutoRange(axis, false) });
    ctrl.min      = kit.local("line", {});
    ctrl.max      = kit.local("line", {});
    ctrl.auto     = kit.local("radio", { group, text: "Auto", onChange: () => view.enableAutoRange(axis, ctrl.percent.value * 0.01) });
    ctrl.percent  = kit.local("spin", { onChange: (value) => {
      ctrl.auto.set({ checked: true });
      view.enableAutoRange(axis, value * 0.01);
    } });
    ctrl.visible  = kit.local("checkbox", { text: "Visible Data Only", onChange: (checked) => (axis === 0 ? view.setAutoVisible(checked, null) : view.setAutoVisible(null, checked)) });
    ctrl.pan      = kit.local("checkbox", { text: "Auto Pan Only", onChange: (checked) => (axis === 0 ? view.setAutoPan(checked, null) : view.setAutoPan(null, checked)) });
    ctrl.invert   = kit.local("checkbox", { text: "Invert Axis", onChange: (checked) => (axis === 0 ? view.invertX(checked) : view.invertY(checked)) });
    ctrl.mouse    = kit.local("checkbox", { text: "Mouse Enabled", onChange: (checked) => (axis === 0 ? view.setMouseEnabled(checked, null) : view.setMouseEnabled(null, checked)) });
    ctrl.link     = kit.local("combo", { items: this.viewList(), onChange: (index) => view.linkView(axis, ctrl.link.items[index]) });
    ctrl.percent.set({ minimum: 1, maximum: 100, value: 100 });

    ctrl.manual.el.title  = "Set the range for this axis manually. This disables automatic scaling.";
    ctrl.auto.el.title    = "Automatically resize this axis whenever the displayed data is changed.";
    ctrl.percent.el.title = "Percent of data to be visible when auto-scaling. It may be useful to decrease this value for data with spiky noise.";
    ctrl.min.el.title     = "Minimum value to display for this axis.";
    ctrl.max.el.title     = "Maximum value to display for this axis.";
    ctrl.invert.el.title  = "Inverts the display of this axis. (+y points downward instead of upward)";
    ctrl.mouse.el.title   = "Enables mouse interaction (panning, scaling) for this axis.";
    ctrl.visible.el.title = "When checked, the axis will only auto-scale to data that is visible along the orthogonal axis.";
    ctrl.pan.el.title     = "When checked, the axis will automatically pan to center on the current data, but the scale along this axis will not change.";
    ctrl.link.el.title    = "Links this axis with another view. When linked, both views will display the same data range.";

    for (const field of [ctrl.min, ctrl.max]) {
      field.input.addEventListener("keydown", (event) => {
        if (event.key === "Enter") this.rangeTextChanged(axis);
      });
      field.input.addEventListener("blur", () => this.rangeTextChanged(axis));
    }

    const cell = (node, col, row, span = 1) => {
      node.style.gridColumn = `${col + 1} / span ${span}`;
      node.style.gridRow    = `${row}`;
      root.append(node);
    };
    cell(ctrl.manual.el, 0, 1, 2);
    cell(ctrl.min.el, 2, 1);
    cell(ctrl.max.el, 3, 1);
    cell(ctrl.auto.el, 0, 2, 2);
    const percent = TomoVisInput.el("span", "tv-pg-axisctrl__percent");
    percent.append(ctrl.percent.el, TomoVisInput.el("span", "tv-label", "%"));
    cell(percent, 2, 2, 2);
    cell(ctrl.visible.el, 2, 3, 2);
    cell(ctrl.pan.el, 2, 4, 2);
    cell(ctrl.invert.el, 0, 5, 4);
    cell(ctrl.mouse.el, 0, 6, 4);
    cell(TomoVisInput.el("span", "tv-label", "Link Axis:"), 0, 7, 2);
    cell(ctrl.link.el, 2, 7, 2);
    for (const event of ["pointerdown", "click", "keydown"]) root.addEventListener(event, (e) => e.stopPropagation());
    this.ctrls[axis] = ctrl;
    return root;
  }

  rangeTextChanged(axis) {
    const ctrl = this.ctrls[axis];
    if (!ctrl || this.syncing) return;
    ctrl.manual.set({ checked: true });
    const vals = this.view.viewRange()[axis];
    [ctrl.min, ctrl.max].forEach((field, i) => {
      const v = Number(field.input.value.trim());
      if (field.input.value.trim() !== "" && Number.isFinite(v)) vals[i] = v;
    });
    if (axis === 0) this.view.setXRange(vals[0], vals[1], 0);
    else this.view.setYRange(vals[0], vals[1], 0);
  }

  updateState() {
    const state = this.view.state;
    this.syncing = true;
    for (const i of [0, 1]) {
      const ctrl = this.ctrls[i];
      if (!ctrl) continue;
      const tr = state.targetRange[i];
      if (document.activeElement !== ctrl.min.input) ctrl.min.set({ text: PgFormat.g(tr[0], 5) });
      if (document.activeElement !== ctrl.max.input) ctrl.max.set({ text: PgFormat.g(tr[1], 5) });
      if (state.autoRange[i] !== false) {
        ctrl.auto.set({ checked: true });
        if (state.autoRange[i] !== true) ctrl.percent.set({ value: Math.trunc(state.autoRange[i] * 100) });
      } else {
        ctrl.manual.set({ checked: true });
      }
      ctrl.mouse.set({ checked: state.mouseEnabled[i] });
      const linked = state.linkedViews[i];
      const name   = linked === null ? "" : (typeof linked === "string" ? linked : (linked.name || ""));
      const items  = this.viewList();
      ctrl.link.setItems(items);
      ctrl.link.set({ index: Math.max(0, items.indexOf(name)) });
      ctrl.pan.set({ checked: state.autoPan[i] });
      ctrl.visible.set({ checked: state.autoVisibleOnly[i] });
      ctrl.invert.set({ checked: i === 0 ? state.xInverted : state.yInverted });
    }
    this.syncing = false;
  }

  viewStateChanged() {
    if (this.menu && this.menu.isOpen) this.updateState();
  }

  items(ev) {
    const view  = this.view;
    const items = [
      { text: "View All", onTrigger: () => view.autoRange() },
      { text: "X axis", submenu: [{ widget: this.axisWidget(0) }] },
      { text: "Y axis", submenu: [{ widget: this.axisWidget(1) }] },
      { text: "Mouse Mode", submenu: [
        { text: "3 button", checkable: true, radio: "mouse", checked: view.state.mouseMode === "pan", onTrigger: () => view.setMouseMode("pan") },
        { text: "1 button", checkable: true, radio: "mouse", checked: view.state.mouseMode === "rect", onTrigger: () => view.setMouseMode("rect") },
      ] },
    ];
    const extra = [...view.getContextMenus(ev)];
    if (view.scene && view.scene.exportEntry) extra.push(view.scene.exportEntry(view));
    if (extra.length) items.push({ separator: true }, ...extra);
    return items;
  }

  popup(x, y, ev) {
    this.menu = this.ctx().kit.menu(this.items(ev));
    this.menu.openAt(x, y);
    this.updateState();
  }
}

window.PgSignal       = PgSignal;
window.PgPen          = PgPen;
window.PgFormat       = PgFormat;
window.PgGeom         = PgGeom;
window.PgMouseEvent   = PgMouseEvent;
window.PgHoverEvent   = PgHoverEvent;
window.PgGraphicsView = PgGraphicsView;
window.PgViewBox      = PgViewBox;
window.PgImageItem    = PgImageItem;
window.PgAxisItem     = PgAxisItem;
window.PgPlotCurve    = PgPlotCurve;
window.PgViewBoxMenu  = PgViewBoxMenu;
