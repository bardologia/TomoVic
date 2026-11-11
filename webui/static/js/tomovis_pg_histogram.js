"use strict";

class PgLinearRegion {
  constructor(values, { brush = [0, 0, 255, 50], pen = null, span = [0, 1], swapMode = "block" } = {}) {
    this.vb        = null;
    this.z         = 0;
    this.visible   = true;
    this.span      = span;
    this.swapMode  = swapMode;
    this.brush     = PgPen.color(brush);
    const hover    = this.brush.slice();
    hover[3]       = Math.min(hover[3] * 2, 255);
    this.hoverBrush   = hover;
    this.currentBrush = this.brush;
    this.mouseHovering = false;
    this.moving    = false;
    this.blockLineSignal = false;
    const linePen  = pen === null ? [200, 200, 100] : pen;
    this.lines     = [0, 1].map((i) => new PgInfiniteLine({ pos: values[i], angle: 0, pen: linePen, movable: true, span, flip: true }));
    this.sigRegionChanged        = new PgSignal();
    this.sigRegionChangeFinished = new PgSignal();
    this.lines.forEach((line, i) => {
      line.parentRegion = this;
      line.sigPositionChanged.connect(() => this.lineMoved(i));
      line.sigPositionChangeFinished.connect(() => this.sigRegionChangeFinished.emit(this));
    });
  }

  attach(vb) {
    this.vb = vb;
    for (const line of this.lines) line.vb = vb;
  }

  setVisible(visible) {
    this.visible = visible;
    for (const line of this.lines) line.visible = visible;
    if (this.vb) this.vb.update();
  }

  getRegion() {
    const r = [this.lines[0].value(), this.lines[1].value()];
    return this.swapMode === "sort" ? [Math.min(...r), Math.max(...r)] : r;
  }

  setRegion(rgn) {
    if (this.lines[0].value() === rgn[0] && this.lines[1].value() === rgn[1]) return;
    this.blockLineSignal = true;
    this.lines[0].setValue(rgn[0]);
    this.lines[1].setValue(rgn[1]);
    this.lineMoved(0);
    this.blockLineSignal = false;
    this.lineMoved(1);
    this.sigRegionChangeFinished.emit(this);
  }

  setSpan(mn, mx) {
    if (this.span[0] === mn && this.span[1] === mx) return;
    this.span = [mn, mx];
    for (const line of this.lines) line.setSpan(mn, mx);
    if (this.vb) this.vb.update();
  }

  lineMoved(i) {
    if (this.blockLineSignal) return;
    if (this.lines[0].value() > this.lines[1].value()) {
      if (this.swapMode === "block") this.lines[i].setValue(this.lines[1 - i].value());
      else if (this.swapMode === "push") this.lines[1 - i].setValue(this.lines[i].value());
    }
    if (this.vb) this.vb.update();
    this.sigRegionChanged.emit(this);
  }

  dataBounds(axis) {
    return axis === 1 ? this.getRegion() : null;
  }

  mapRectToView(rect) {
    return rect;
  }

  bandPoly(vb) {
    const vr  = vb.viewRect();
    const rng = this.getRegion();
    const x0  = vr.x + vr.w * this.span[0];
    const x1  = vr.x + vr.w * this.span[1];
    const a   = vb.mapViewToScene(x0, rng[0]);
    const b   = vb.mapViewToScene(x1, rng[1]);
    const r   = PgGeom.normRect(a.x, a.y, b.x, b.y);
    return PgGeom.rectPoly(r.x, r.y, r.w, r.h);
  }

  hit(x, y) {
    return this.visible && this.vb !== null && PgGeom.polyContains(this.bandPoly(this.vb), x, y);
  }

  hitRect(x0, y0, x1, y1) {
    return this.visible && this.vb !== null && PgGeom.polyIntersectsRect(this.bandPoly(this.vb), x0, y0, x1, y1);
  }

  sceneItems() {
    if (!this.visible) return [];
    return [{ item: this, z: this.z }, ...this.lines.map((line) => ({ item: line, z: this.z + 0.25 }))];
  }

  paint(ctx, vb) {
    const poly = this.bandPoly(vb);
    ctx.save();
    ctx.fillStyle = PgPen.css(this.currentBrush);
    ctx.fillRect(poly[0][0], poly[0][1], poly[2][0] - poly[0][0], poly[2][1] - poly[0][1]);
    ctx.restore();
    for (const line of this.lines) line.paint(ctx, vb);
  }

  hoverEvent(ev) {
    const hover = !ev.isExit() && ev.acceptDrags("left");
    if (this.mouseHovering === hover) return;
    this.mouseHovering = hover;
    this.currentBrush  = hover ? this.hoverBrush : this.brush;
    if (this.vb) this.vb.update();
  }

  sceneValue(scenePos) {
    return this.vb.mapSceneToView(scenePos.x, scenePos.y).y;
  }

  mouseDragEvent(ev) {
    if (ev.button !== "left") return;
    ev.accept();
    if (ev.isStart()) {
      const bdp = this.sceneValue(ev.buttonDownScenePos);
      this.cursorOffsets  = this.lines.map((line) => line.value() - bdp);
      this.startPositions = this.lines.map((line) => line.value());
      this.moving         = true;
    }
    if (!this.moving) return;
    this.blockLineSignal = true;
    const v = this.sceneValue(ev.scenePos);
    this.lines.forEach((line, i) => line.setPos(this.cursorOffsets[i] + v));
    this.blockLineSignal = false;
    if (this.vb) this.vb.update();
    if (ev.isFinish()) {
      this.moving = false;
      this.sigRegionChangeFinished.emit(this);
    } else {
      this.sigRegionChanged.emit(this);
    }
  }

  mouseClickEvent(ev) {
    if (this.moving && ev.button === "right") {
      ev.accept();
      this.lines.forEach((line, i) => line.setPos(this.startPositions[i]));
      this.moving = false;
      this.sigRegionChanged.emit(this);
      this.sigRegionChangeFinished.emit(this);
    }
  }
}

class PgGradientTick {
  constructor(editor, lx, color, movable = true) {
    this.editor     = editor;
    this.lx         = lx;
    this.color      = color.slice();
    this.movable    = movable;
    this.visible    = true;
    this.z          = movable ? 1 : 0;
    this.pen        = PgPen.mk("w");
    this.hoverPen   = PgPen.mk([255, 255, 0]);
    this.currentPen = this.pen;
    this.moving     = false;
    this.removeAllowed      = true;
    this.colorChangeAllowed = true;
  }

  poly() {
    const g     = this.editor.geometry();
    const y     = g.y0 - this.lx;
    const apexX = g.barX + g.barW;
    const s     = this.editor.tickSize;
    const half  = s / Math.sqrt(3);
    return [[apexX, y], [apexX + s, y - half], [apexX + s, y + half]];
  }

  hit(x, y) {
    return this.visible && PgGeom.polyContains(this.poly(), x, y);
  }

  hitRect(x0, y0, x1, y1) {
    return this.visible && PgGeom.polyIntersectsRect(this.poly(), x0, y0, x1, y1);
  }

  paint(ctx) {
    const p = this.poly();
    ctx.beginPath();
    ctx.moveTo(p[0][0], p[0][1]);
    ctx.lineTo(p[1][0], p[1][1]);
    ctx.lineTo(p[2][0], p[2][1]);
    ctx.closePath();
    ctx.fillStyle = PgPen.css(this.color);
    ctx.fill();
    PgPen.apply(ctx, this.currentPen);
    ctx.stroke();
  }

  hoverEvent(ev) {
    if (!ev.isExit() && ev.acceptDrags("left")) {
      ev.acceptClicks("left");
      ev.acceptClicks("right");
      this.currentPen = this.hoverPen;
    } else {
      this.currentPen = this.pen;
    }
    this.editor.update();
  }

  localX(scenePos) {
    return this.editor.geometry().y0 - scenePos.y;
  }

  mouseDragEvent(ev) {
    if (!this.movable || ev.button !== "left") return;
    if (ev.isStart()) {
      this.moving        = true;
      this.cursorOffset  = this.lx - this.localX(ev.buttonDownScenePos);
      this.startPosition = this.lx;
    }
    ev.accept();
    if (!this.moving) return;
    const newX = this.cursorOffset + this.localX(ev.scenePos);
    this.lx    = newX;
    this.editor.tickMoved(this, newX);
    if (ev.isFinish()) {
      this.moving = false;
      this.editor.tickMoveFinished(this);
    }
  }

  mouseClickEvent(ev) {
    ev.accept();
    if (ev.button === "right" && this.moving) {
      this.lx     = this.startPosition;
      this.moving = false;
      this.editor.tickMoved(this, this.startPosition);
      this.editor.tickMoveFinished(this);
    } else {
      this.editor.tickClicked(this, ev);
    }
  }
}

class PgGradientEditor {
  static PRESET_GREY = { mode: "rgb", ticks: [[0.0, [0, 0, 0, 255]], [1.0, [255, 255, 255, 255]]] };

  constructor(ctx) {
    this.ctx        = ctx;
    this.rect       = { x: 0, y: 0, w: 30, h: 100 };
    this.scene      = null;
    this.z          = 0;
    this.visible    = true;
    this.tickSize   = 15;
    this.rectSize   = 15;
    this.length     = 100;
    this.ticks      = new Map();
    this.colorMode  = "rgb";
    this.allowAdd   = true;
    this.allowAddBackup = null;
    this.ticksShown = true;
    this.blocked    = false;
    this.currentTick      = null;
    this.currentTickColor = null;
    this.sigGradientChanged       = new PgSignal();
    this.sigGradientChangeFinished = new PgSignal();
    this.addTick(0, [0, 0, 0, 255], true);
    this.addTick(1, [255, 0, 0, 255], true);
    this.setColorMode("rgb");
    this.loadState(PgGradientEditor.PRESET_GREY);
  }

  setGeometry(x, y, w, h) {
    this.rect = { x, y, w, h };
    const wlen = Math.max(40, h);
    this.setLength(wlen - this.tickSize - 2);
  }

  geometry() {
    return { barX: this.rect.x, barW: this.rectSize, y0: this.rect.y + 8.5 + this.length + 1 };
  }

  gradRect() {
    return { x: this.rect.x, y: this.rect.y + 8.5, w: this.rectSize, h: this.length };
  }

  update() {
    if (this.scene) this.scene.update();
  }

  setLength(newLen) {
    for (const [tick, x] of this.ticks) tick.lx = x * newLen + 1;
    this.length = newLen;
    this.ticksChanged();
  }

  listTicks() {
    return [...this.ticks.entries()].sort((a, b) => a[1] - b[1]);
  }

  ticksChanged() {
    if (!this.blocked) this.sigGradientChanged.emit(this);
    this.update();
  }

  ticksChangeFinished() {
    if (!this.blocked) this.sigGradientChangeFinished.emit(this);
  }

  addTick(x, color = null, movable = true, finish = true) {
    const c    = color === null ? this.getColor(x) : color;
    const tick = new PgGradientTick(this, x * this.length, c, movable);
    tick.visible = true;
    this.ticks.set(tick, x);
    this.ticksChanged();
    if (finish) this.ticksChangeFinished();
    return tick;
  }

  removeTick(tick, finish = true) {
    this.ticks.delete(tick);
    this.ticksChanged();
    if (finish) this.ticksChangeFinished();
  }

  tickMoved(tick, lx) {
    const newX = Math.min(Math.max(0, lx), this.length);
    tick.lx    = newX;
    this.ticks.set(tick, newX / this.length);
    this.ticksChanged();
  }

  tickMoveFinished() {
    this.ticksChangeFinished();
  }

  setTickColor(tick, color) {
    tick.color = color.slice();
    this.ticksChanged();
    this.ticksChangeFinished();
  }

  setTickValue(tick, val) {
    const v = Math.min(Math.max(0.0, val), 1.0);
    tick.lx = v * this.length;
    this.ticks.set(tick, v);
    this.update();
    this.ticksChanged();
    this.ticksChangeFinished();
  }

  showTicks(show) {
    for (const tick of this.ticks.keys()) {
      if (show) {
        tick.visible = true;
        if (this.allowAddBackup) this.allowAdd = this.allowAddBackup;
      } else {
        this.allowAddBackup = this.allowAdd;
        this.allowAdd       = false;
        tick.visible        = false;
      }
    }
    this.update();
  }

  setColorMode(mode) {
    this.colorMode = mode;
    this.ticksChanged();
    this.ticksChangeFinished();
  }

  loadState(state) {
    this.blocked = true;
    this.setColorMode(state.mode);
    for (const tick of [...this.ticks.keys()]) this.removeTick(tick, false);
    for (const [pos, color] of state.ticks) this.addTick(pos, color, true, false);
    const first = this.ticks.keys().next().value;
    this.showTicks(state.ticksVisible === undefined ? first.visible : state.ticksVisible);
    this.blocked = false;
    this.ticksChanged();
    this.sigGradientChangeFinished.emit(this);
  }

  setColorMap(pos, colors) {
    this.blocked = true;
    this.setColorMode("rgb");
    for (const tick of [...this.ticks.keys()]) this.removeTick(tick, false);
    for (let i = 0; i < pos.length; i += 1) this.addTick(pos[i], colors[i], true, false);
    this.blocked = false;
    this.ticksChanged();
    this.sigGradientChangeFinished.emit(this);
  }

  static qtHsv(rgb) {
    const r     = (rgb[0] * 0x101) / 65535;
    const g     = (rgb[1] * 0x101) / 65535;
    const b     = (rgb[2] * 0x101) / 65535;
    const max   = Math.max(r, g, b);
    const min   = Math.min(r, g, b);
    const delta = max - min;
    const value = Math.round(max * 65535);
    if (Math.abs(delta) <= 0.00001) return [-1, 0, value >> 8];
    const sat = Math.round((delta / max) * 65535);
    let hue;
    if (Math.abs(r - max) <= 0.00001 * Math.min(Math.abs(r), Math.abs(max)) || r === max) hue = (g - b) / delta;
    else if (Math.abs(g - max) <= 0.00001 * Math.min(Math.abs(g), Math.abs(max)) || g === max) hue = 2.0 + (b - r) / delta;
    else hue = 4.0 + (r - g) / delta;
    hue *= 60.0;
    if (hue < 0.0) hue += 360.0;
    return [Math.trunc(Math.round(hue * 100) / 100), sat >> 8, value >> 8];
  }

  static qtFromHsv(h, s, v) {
    const value = v * 0x101;
    if (s === 0 || h === -1) {
      const c = value >> 8;
      return [c, c, c, 255];
    }
    const hue  = (h % 360) * 100;
    const hh   = hue === 36000 ? 0 : hue / 6000;
    const ss   = (s * 0x101) / 65535;
    const vv   = value / 65535;
    const i    = Math.trunc(hh);
    const f    = hh - i;
    const p    = vv * (1 - ss);
    let rgb;
    if (i & 1) {
      const q = vv * (1 - ss * f);
      rgb = i === 1 ? [q, vv, p] : (i === 3 ? [p, q, vv] : [vv, p, q]);
    } else {
      const t = vv * (1 - ss * (1 - f));
      rgb = i === 0 ? [vv, t, p] : (i === 2 ? [p, vv, t] : [t, p, vv]);
    }
    return [...rgb.map((c) => Math.round(c * 65535) >> 8), 255];
  }

  getColor(x, quantize = true) {
    const ticks = this.listTicks();
    if (ticks.length === 0) return [0, 0, 0, 255];
    if (x <= ticks[0][1]) return ticks[0][0].color.slice();
    if (x >= ticks[ticks.length - 1][1]) return ticks[ticks.length - 1][0].color.slice();
    let x2 = ticks[0][1];
    let x1 = x2;
    let i  = 1;
    for (i = 1; i < ticks.length; i += 1) {
      x1 = x2;
      x2 = ticks[i][1];
      if (x1 <= x && x2 >= x) break;
    }
    if (i >= ticks.length) i = ticks.length - 1;
    const dx = x2 - x1;
    const f  = dx === 0 ? 0.0 : (x - x1) / dx;
    const c1 = ticks[i - 1][0].color;
    const c2 = ticks[i][0].color;
    if (this.colorMode === "rgb") {
      const mix = [0, 1, 2, 3].map((k) => c1[k] * (1.0 - f) + c2[k] * f);
      return quantize ? mix.map((v) => Math.trunc(v)) : mix;
    }
    const a = PgGradientEditor.qtHsv(c1);
    const b = PgGradientEditor.qtHsv(c2);
    const h = a[0] * (1.0 - f) + b[0] * f;
    const s = a[1] * (1.0 - f) + b[1] * f;
    const v = a[2] * (1.0 - f) + b[2] * f;
    return PgGradientEditor.qtFromHsv(Math.trunc(h), Math.trunc(s), Math.trunc(v));
  }

  usesAlpha() {
    return [...this.ticks.keys()].some((tick) => tick.color[3] < 255);
  }

  getLookupTable(nPts, alpha = null) {
    const useAlpha = alpha === null ? this.usesAlpha() : alpha;
    const width    = useAlpha ? 4 : 3;
    const table    = new Uint8Array(nPts * width);
    for (let i = 0; i < nPts; i += 1) {
      const color = this.getColor(i / (nPts - 1), false);
      for (let k = 0; k < width; k += 1) table[i * width + k] = Math.trunc(color[k]);
    }
    return { table, width };
  }

  isLookupTrivial() {
    const ticks = this.listTicks();
    if (ticks.length !== 2) return false;
    if (ticks[0][1] !== 0.0 || ticks[1][1] !== 1.0) return false;
    const c1 = ticks[0][0].color;
    const c2 = ticks[1][0].color;
    return c1.join(",") === "0,0,0,255" && c2.join(",") === "255,255,255,255";
  }

  gradientStops() {
    const ticks = this.listTicks();
    if (this.colorMode === "rgb") return ticks.map(([tick, x]) => [x, tick.color]);
    const stops = [[ticks[0][1], ticks[0][0].color]];
    for (let i = 1; i < ticks.length; i += 1) {
      const x1 = ticks[i - 1][1];
      const x2 = ticks[i][1];
      const dx = (x2 - x1) / 10.0;
      for (let j = 1; j < 10; j += 1) stops.push([x1 + dx * j, this.getColor(x1 + dx * j)]);
      stops.push([x2, this.getColor(x2)]);
    }
    return stops;
  }

  static backdrop() {
    if (PgGradientEditor.pattern) return PgGradientEditor.pattern;
    const c   = document.createElement("canvas");
    c.width   = 8;
    c.height  = 8;
    const ctx = c.getContext("2d");
    ctx.strokeStyle = "#000";
    ctx.lineWidth   = 1;
    ctx.beginPath();
    ctx.moveTo(0, 0);
    ctx.lineTo(8, 8);
    ctx.moveTo(8, 0);
    ctx.lineTo(0, 8);
    ctx.stroke();
    PgGradientEditor.pattern = c;
    return c;
  }

  paint(ctx) {
    if (!this.visible || this.rect.h <= 0) return;
    const r = this.gradRect();
    ctx.save();
    ctx.fillStyle = "#fff";
    ctx.fillRect(r.x, r.y, r.w, r.h);
    ctx.fillStyle = ctx.createPattern(PgGradientEditor.backdrop(), "repeat");
    ctx.fillRect(r.x, r.y, r.w, r.h);
    const bottom = r.y + r.h + 1;
    const grad   = ctx.createLinearGradient(0, bottom, 0, bottom - this.length);
    for (const [x, color] of this.gradientStops()) grad.addColorStop(Math.min(1, Math.max(0, x)), PgPen.css(color));
    ctx.fillStyle = grad;
    ctx.fillRect(r.x, r.y, r.w, r.h);
    ctx.strokeStyle = "#000";
    ctx.lineWidth   = 1;
    ctx.strokeRect(r.x + 0.5, r.y, r.w, r.h);
    for (const tick of this.ticks.keys()) {
      if (tick.visible) tick.paint(ctx);
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
    if (!this.visible) return [];
    const list = [{ item: this, z: this.z }];
    for (const tick of this.ticks.keys()) {
      if (tick.visible) list.push({ item: tick, z: this.z + tick.z });
    }
    return list;
  }

  hoverEvent(ev) {
    if (!ev.isExit() && ev.acceptClicks("left")) ev.acceptClicks("right");
  }

  mouseClickEvent(ev) {
    const g  = this.geometry();
    const lx = g.y0 - ev.scenePos.y;
    const ly = ev.scenePos.x - (g.barX + g.barW);
    if (ev.button === "left" && this.allowAdd) {
      if (lx < 0 || lx > this.length) return;
      if (ly < 0 || ly > this.tickSize) return;
      this.addTick(Math.min(Math.max(lx, 0), this.length) / this.length);
    } else if (ev.button === "right") {
      this.showMenu(ev);
    }
  }

  showMenu(ev) {
    new PgColorMapMenu(this).openAt(ev.screenPos.x, ev.screenPos.y);
  }

  tickClicked(tick, ev) {
    if (ev.button === "left") this.raiseColorDialog(tick);
    else if (ev.button === "right") this.raiseTickContextMenu(tick, ev);
  }

  async raiseColorDialog(tick) {
    if (!tick.colorChangeAllowed) return;
    this.currentTick      = tick;
    this.currentTickColor = tick.color.slice();
    const result = await this.ctx.dialogs.color({ initial: tick.color.slice(), title: "Select Color", alpha: true, live: (color) => {
      if (this.currentTick && this.ticks.has(this.currentTick)) this.setTickColor(this.currentTick, color);
    } });
    if (!this.ticks.has(tick)) return;
    if (result.accepted) this.sigGradientChangeFinished.emit(this);
    else this.setTickColor(tick, this.currentTickColor);
  }

  raiseTickContextMenu(tick, ev) {
    const kit  = this.ctx.kit;
    const spin = kit.local("doubleSpin", { decimals: 2, step: 0.01, onChange: (value) => this.setTickValue(tick, value) });
    spin.set({ minimum: 0.0, maximum: 1.0, value: this.ticks.get(tick) });
    const box  = TomoVisInput.el("span", "tv-pg-tickpos");
    box.append(TomoVisInput.el("span", "tv-label", "Position:"), spin.el);
    for (const name of ["pointerdown", "click", "keydown"]) box.addEventListener(name, (e) => e.stopPropagation());
    const items = [
      { text: "Remove Tick", enabled: tick.removeAllowed && this.ticks.size >= 3, onTrigger: () => this.removeTick(tick) },
      { text: "Set Position", submenu: [{ widget: box }] },
      { text: "Set Color", enabled: tick.colorChangeAllowed, onTrigger: () => this.raiseColorDialog(tick) },
    ];
    kit.menu(items).openAt(ev.screenPos.x, ev.screenPos.y);
  }

  saveState() {
    return { mode: this.colorMode, ticks: [...this.ticks.entries()].map(([tick, x]) => [x, tick.color.slice()]), ticksVisible: this.ticks.keys().next().value.visible };
  }
}

class PgColorMapMenu {
  static data    = null;
  static loading = null;

  static load() {
    if (PgColorMapMenu.data) return Promise.resolve(PgColorMapMenu.data);
    if (!PgColorMapMenu.loading) {
      PgColorMapMenu.loading = fetch("/static/data/tomovis_pg_colormaps.json").then((res) => {
        if (!res.ok) throw new Error(`ColorMaps data request failed with status ${res.status}`);
        return res.json();
      }).then((data) => {
        PgColorMapMenu.data = data;
        return data;
      });
    }
    return PgColorMapMenu.loading;
  }

  static hexColor(hex) {
    return [0, 2, 4, 6].map((i) => parseInt(hex.slice(i, i + 2), 16));
  }

  constructor(editor) {
    this.editor = editor;
  }

  swatch(entry) {
    const canvas  = document.createElement("canvas");
    canvas.width  = entry.swatch.length;
    canvas.height = 1;
    canvas.className = "tv-pg-swatch";
    const ctx  = canvas.getContext("2d");
    const data = new ImageData(entry.swatch.length, 1);
    entry.swatch.forEach((hex, i) => data.data.set(PgColorMapMenu.hexColor(hex), i * 4));
    ctx.putImageData(data, 0, 0);
    return canvas;
  }

  entryWidget(text, entry) {
    const row = TomoVisInput.el("span", "tv-pg-cmapentry");
    row.append(this.swatch(entry), TomoVisInput.el("span", "tv-pg-cmapentry__text", text));
    row.addEventListener("click", () => {
      this.apply(entry);
      if (TomoVisMenu.root) TomoVisMenu.root.close();
    });
    return row;
  }

  apply(entry) {
    const isPreset = Object.keys(PgColorMapMenu.data.maps).find((key) => PgColorMapMenu.data.maps[key] === entry).startsWith("preset-gradient:");
    const ticks    = entry.ticks.map(([pos, hex]) => [pos, PgColorMapMenu.hexColor(hex)]);
    if (isPreset) {
      this.editor.loadState({ mode: entry.mode, ticks });
    } else {
      this.editor.setColorMap(ticks.map((t) => t[0]), ticks.map((t) => t[1]));
      this.editor.showTicks(false);
    }
  }

  items(tree) {
    return tree.map((node) => {
      if (node.separator) return { separator: true };
      if (node.submenu) return { text: node.text, submenu: this.items(node.submenu) };
      if (node.mode) {
        return { text: node.text, checkable: true, checked: this.editor.colorMode === node.mode, onTrigger: () => this.editor.setColorMode(node.mode) };
      }
      if (node.text === "None") return { text: "None", onTrigger: () => this.apply(PgColorMapMenu.data.maps[node.map]) };
      return { widget: this.entryWidget(node.text, PgColorMapMenu.data.maps[node.map]) };
    });
  }

  async openAt(x, y) {
    const data = await PgColorMapMenu.load();
    this.editor.ctx.kit.menu(this.items(data.tree)).openAt(x, y);
  }
}

class PgHistogramLut {
  constructor(ctx, host, imageItem, { levelMode = "mono" } = {}) {
    this.ctx       = ctx;
    this.view      = new PgGraphicsView(host, { onLayout: (w, h) => this.layout(w, h), className: "tv-pg-histogram" });
    this.imageItem = imageItem;
    this.levelMode = levelMode;
    this.lut       = null;
    this.rect      = { x: 0, y: 0, w: 0, h: 0 };
    this.visible   = true;
    this.vb        = new PgViewBox({});
    this.vb.setMouseEnabled(false, true);
    this.vb.attach(this.view);
    this.gradient  = new PgGradientEditor(ctx);
    this.axis      = new PgAxisItem("left", { linkView: this.vb, maxTickLength: -10 });
    this.regions   = [
      new PgLinearRegion([0, 1], { swapMode: "block" }),
      new PgLinearRegion([0, 1], { swapMode: "block", pen: "r", brush: [255, 50, 50, 50], span: [0, 1 / 3] }),
      new PgLinearRegion([0, 1], { swapMode: "block", pen: "g", brush: [50, 255, 50, 50], span: [1 / 3, 2 / 3] }),
      new PgLinearRegion([0, 1], { swapMode: "block", pen: "b", brush: [50, 50, 255, 80], span: [2 / 3, 1] }),
      new PgLinearRegion([0, 1], { swapMode: "block", pen: "w", brush: [255, 255, 255, 50], span: [2 / 3, 1] }),
    ];
    this.region = this.regions[0];
    for (const region of this.regions) {
      region.z = 1000;
      region.attach(this.vb);
      this.vb.addItem(region);
      region.lines[0].addMarker("<|", 0.5);
      region.lines[1].addMarker("|>", 0.5);
      region.sigRegionChanged.connect(() => this.regionChanging());
      region.sigRegionChangeFinished.connect(() => this.regionChanged());
    }
    this.plots = [
      new PgPlotCurve({ pen: [200, 200, 200, 100], rotation: 90 }),
      new PgPlotCurve({ pen: [255, 0, 0, 100], rotation: 90, composition: "plus" }),
      new PgPlotCurve({ pen: [0, 255, 0, 100], rotation: 90, composition: "plus" }),
      new PgPlotCurve({ pen: [0, 0, 255, 100], rotation: 90, composition: "plus" }),
      new PgPlotCurve({ pen: [200, 200, 200, 100], rotation: 90, composition: "plus" }),
    ];
    const fills = [[100, 100, 200, 255], [255, 0, 0, 50], [0, 255, 0, 50], [0, 0, 255, 50], [255, 255, 255, 50]];
    this.plots.forEach((plot, i) => {
      plot.fillLevel = 0.0;
      plot.brush     = fills[i];
      this.vb.addItem(plot);
    });
    this.view.addWidget(this.vb);
    this.view.addWidget(this.gradient);
    this.view.addWidget(this);
    this.view.addWidget(this.axis);
    this.axis.sigSizeChanged.connect(() => requestAnimationFrame(() => this.layout(this.view.width, this.view.height)));
    this.gradient.sigGradientChanged.connect(() => this.gradientChanged());
    this.vb.sigRangeChanged.connect(() => this.view.update());
    this.showRegions();
    this.vb.enableAutoRange(null, true);
    this.imageItem.sigImageChanged.connect(() => this.imageChanged(false));
    this.setImageLookupTable();
    this.regionChanged();
    this.imageChanged(true);
  }

  layout(w, h) {
    const inner = { x: 1, y: 1, w: w - 2, h: h - 2 };
    const axisW = Math.round(this.axis.preferredWidth());
    const gradW = this.gradient.visible ? 30 : 0;
    const vbW   = Math.max(45, Math.min(152, inner.w - axisW - gradW));
    this.axis.setGeometry(inner.x, inner.y, axisW, inner.h);
    this.vb.setGeometry(inner.x + axisW, inner.y, vbW, inner.h);
    this.gradient.setGeometry(inner.x + axisW + vbW, inner.y, gradW, inner.h);
    this.axis.linkedViewChanged(this.vb);
    this.view.update();
  }

  sceneItems() {
    return [];
  }

  paint(ctx) {
    if (this.levelMode !== "mono" || !this.region.visible) return;
    const pen      = this.region.lines[0].currentPen;
    const [mn, mx] = this.getLevels();
    const vr       = this.vb.viewRect();
    const cx       = vr.x + vr.w / 2;
    const a        = this.vb.mapViewToScene(cx, mn);
    const b        = this.vb.mapViewToScene(cx, mx);
    const g        = this.gradient.gradRect();
    const p1mn     = { x: a.x, y: a.y + 5 };
    const p1mx     = { x: b.x, y: b.y - 5 };
    const p2mn     = { x: g.x, y: g.y + g.h };
    const p2mx     = { x: g.x, y: g.y };
    ctx.save();
    for (const [color, width] of [[[0, 0, 0, 100], 3], [pen.color, pen.width]]) {
      ctx.strokeStyle = PgPen.css(color);
      ctx.lineWidth   = width;
      ctx.setLineDash([]);
      ctx.beginPath();
      ctx.moveTo(p1mn.x, p1mn.y);
      ctx.lineTo(p2mn.x, p2mn.y);
      ctx.moveTo(p1mx.x, p1mx.y);
      ctx.lineTo(p2mx.x, p2mx.y);
      ctx.moveTo(g.x, g.y);
      ctx.lineTo(g.x + g.w, g.y);
      ctx.moveTo(g.x, g.y + g.h);
      ctx.lineTo(g.x + g.w, g.y + g.h);
      ctx.stroke();
    }
    ctx.restore();
  }

  setHistogramRange(mn, mx, padding = 0.1) {
    this.vb.enableAutoRange(1, false);
    this.vb.setYRange(mn, mx, padding);
  }

  gradientChanged() {
    this.setImageLookupTable();
    this.lut = null;
    if (this.onLookupTableChanged) this.onLookupTableChanged();
  }

  setImageLookupTable() {
    if (this.gradient.isLookupTrivial()) this.imageItem.setLookupTable(null);
    else this.imageItem.setLookupTable(this.getLookupTable());
  }

  getLookupTable() {
    if (this.levelMode !== "mono") return null;
    if (this.lut === null) {
      const { table, width } = this.gradient.getLookupTable(256);
      const rgb = new Uint8Array(256 * 3);
      for (let i = 0; i < 256; i += 1) {
        for (let k = 0; k < 3; k += 1) rgb[i * 3 + k] = table[i * width + k];
      }
      this.lut = rgb;
    }
    return this.lut;
  }

  regionChanged() {
    this.imageItem.setLevels(this.getLevels());
    if (this.onLevelsChanged) this.onLevelsChanged();
  }

  regionChanging() {
    this.imageItem.setLevels(this.getLevels());
    this.view.update();
    if (this.onLevelsChanged) this.onLevelsChanged();
  }

  imageChanged(autoLevel = false) {
    if (this.levelMode === "mono") {
      for (const plot of this.plots.slice(1)) plot.visible = false;
      this.plots[0].visible = true;
      const h = this.imageItem.getHistogram(false);
      if (h === null) return;
      this.plots[0].setData(h[0], h[1]);
      if (autoLevel) this.region.setRegion([h[0][0], h[0][h[0].length - 1]]);
      else {
        const levels = this.imageItem.getLevels();
        this.region.setRegion(Array.isArray(levels[0]) ? levels[0] : levels);
      }
    } else {
      this.plots[0].visible = false;
      const ch = this.imageItem.getHistogram(true);
      if (ch === null) return;
      for (let i = 1; i < 5; i += 1) {
        if (ch.length >= i) {
          this.plots[i].visible = true;
          this.plots[i].setData(ch[i - 1][0], ch[i - 1][1]);
          if (autoLevel) this.regions[i].setRegion([ch[i - 1][0][0], ch[i - 1][0][ch[i - 1][0].length - 1]]);
        } else {
          this.plots[i].visible = false;
        }
      }
      this.showRegions();
    }
    this.vb.itemBoundsChanged();
    this.view.update();
  }

  getLevels() {
    if (this.levelMode === "mono") return this.region.getRegion();
    const nch = this.imageItem.channels() === null ? 3 : this.imageItem.channels();
    return this.regions.slice(1, nch + 1).map((r) => r.getRegion());
  }

  setLevels({ min = null, max = null, rgba = null } = {}) {
    if ((min === null || max === null) && (rgba === null || rgba[0].includes(null))) throw new Error("Must specify min and max levels");
    if (this.levelMode === "mono") {
      if (min === null) [min, max] = rgba[0];
      this.region.setRegion([min, max]);
    } else {
      const pairs = rgba === null ? [[min, max], [min, max], [min, max], [min, max]] : rgba;
      pairs.forEach((levels, i) => {
        if (this.regions[i + 1]) this.regions[i + 1].setRegion(levels);
      });
    }
  }

  setLevelMode(mode) {
    if (mode !== "mono" && mode !== "rgba") throw new Error(`Level mode must be one of mono, rgba, got ${mode}`);
    if (mode === this.levelMode) return;
    const old = this.getLevels();
    this.levelMode = mode;
    this.showRegions();
    if (mode === "mono") {
      const mean = [0, 1].map((k) => old.reduce((acc, pair) => acc + pair[k], 0) / old.length);
      this.setLevels({ min: mean[0], max: mean[1] });
    } else {
      this.setLevels({ rgba: [old, old, old, old] });
    }
    this.imageItem.setLevels(this.getLevels());
    this.imageChanged(false);
    this.view.update();
  }

  showRegions() {
    for (const region of this.regions) region.setVisible(false);
    if (this.levelMode === "rgba") {
      const ch  = this.imageItem.channels();
      const nch = ch === null ? 3 : ch;
      const dif = 1.0 / nch;
      for (let i = 1; i <= nch && i < this.regions.length; i += 1) {
        this.regions[i].setVisible(true);
        this.regions[i].setSpan((i - 1) * dif, i * dif);
      }
      this.gradient.visible = false;
    } else {
      this.regions[0].setVisible(true);
      this.gradient.visible = true;
    }
    if (this.view.width > 0 && this.view.height > 0) this.layout(this.view.width, this.view.height);
    this.view.update();
  }
}

window.PgLinearRegion   = PgLinearRegion;
window.PgGradientTick   = PgGradientTick;
window.PgGradientEditor = PgGradientEditor;
window.PgColorMapMenu   = PgColorMapMenu;
window.PgHistogramLut   = PgHistogramLut;
