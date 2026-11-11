"use strict";

class PgHandle {
  static TYPES = {
    t  : [4, Math.PI / 4],
    f  : [4, Math.PI / 4],
    s  : [4, 0],
    r  : [12, 0],
    sr : [12, 0],
    rf : [12, 0],
  };

  constructor(radius, type, pen, hoverPen) {
    this.radius     = radius;
    this.type       = type;
    this.pen        = PgPen.mk(pen);
    this.hoverPen   = PgPen.mk(hoverPen);
    this.currentPen = this.pen;
    this.isMoving   = false;
    this.rois       = [];
    this.position   = [0, 0];
    this.visible    = true;
    this.z          = 11;
    this.startPos   = null;
    this.cursorOffset = { x: 0, y: 0 };
    const [sides, start] = PgHandle.TYPES[type];
    this.path = [];
    let ang = start;
    for (let i = 0; i < sides; i += 1) {
      this.path.push([radius * Math.cos(ang), radius * Math.sin(ang)]);
      ang += (2 * Math.PI) / sides;
    }
  }

  roi() {
    return this.rois[0];
  }

  setPos(x, y) {
    this.position = [x, y];
  }

  pos() {
    return this.position.slice();
  }

  scenePos() {
    const roi = this.roi();
    const p   = roi.mapToParent(this.position);
    return roi.vb.mapViewToScene(p[0], p[1]);
  }

  devicePoly() {
    const roi = this.roi();
    const vb  = roi.vb;
    const c   = this.scenePos();
    const o   = roi.mapToParent([0, 0]);
    const e   = roi.mapToParent([1, 0]);
    const so  = vb.mapViewToScene(o[0], o[1]);
    const se  = vb.mapViewToScene(e[0], e[1]);
    const va  = Math.atan2(se.y - so.y, se.x - so.x);
    const cos = Math.cos(va);
    const sin = Math.sin(va);
    return this.path.map(([x, y]) => [c.x + x * cos - y * sin, c.y + x * sin + y * cos]);
  }

  hit(x, y) {
    return this.visible && PgGeom.polyContains(this.devicePoly(), x, y);
  }

  hitRect(x0, y0, x1, y1) {
    return this.visible && PgGeom.polyIntersectsRect(this.devicePoly(), x0, y0, x1, y1);
  }

  paint(ctx) {
    const poly = this.devicePoly();
    PgPen.apply(ctx, this.currentPen);
    ctx.beginPath();
    poly.forEach(([x, y], i) => (i === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y)));
    ctx.closePath();
    ctx.stroke();
  }

  update() {
    const roi = this.roi();
    if (roi && roi.vb) roi.vb.update();
  }

  hoverEvent(ev) {
    let hover = false;
    if (!ev.isExit() && ev.acceptDrags("left")) hover = true;
    this.currentPen = hover ? this.hoverPen : this.pen;
    this.update();
  }

  mouseClickEvent(ev) {
    if (ev.button === "right" && this.isMoving) {
      this.isMoving = false;
      this.movePoint(this.startPos, PgMouseEvent.modifiers({}), true);
      ev.accept();
    } else {
      ev.ignore();
    }
  }

  mouseDragEvent(ev) {
    if (ev.button !== "left") return;
    ev.accept();
    if (ev.isFinish()) {
      if (this.isMoving) {
        for (const roi of this.rois) roi.stateChangeFinished();
      }
      this.isMoving   = false;
      this.currentPen = this.pen;
      this.update();
    } else if (ev.isStart()) {
      for (const roi of this.rois) roi.handleMoveStarted();
      this.isMoving     = true;
      this.startPos     = this.scenePos();
      this.cursorOffset = { x: this.startPos.x - ev.buttonDownScenePos.x, y: this.startPos.y - ev.buttonDownScenePos.y };
      this.currentPen   = this.hoverPen;
    }
    if (this.isMoving) {
      const pos = { x: ev.scenePos.x + this.cursorOffset.x, y: ev.scenePos.y + this.cursorOffset.y };
      this.currentPen = this.hoverPen;
      this.movePoint(pos, ev.modifiers, false);
    }
  }

  movePoint(scenePos, modifiers, finish) {
    for (const roi of this.rois) roi.movePoint(this, scenePos, modifiers, finish, "scene");
  }
}

class PgRoi {
  static roundHalfEven(x) {
    const r = Math.round(x);
    if (Math.abs(x % 1) === 0.5) return 2 * Math.round(x / 2);
    return r;
  }

  static rotation(angle) {
    const degrees = ((angle % 360) + 360) % 360;
    if (degrees === 0) return [1, 0];
    if (degrees === 90) return [0, 1];
    if (degrees === 180) return [-1, 0];
    if (degrees === 270) return [0, -1];
    const rad = (degrees * Math.PI) / 180;
    return [Math.cos(rad), Math.sin(rad)];
  }

  static rotate(angle, p) {
    const [cos, sin] = PgRoi.rotation(angle);
    return [cos * p[0] - sin * p[1], sin * p[0] + cos * p[1]];
  }

  constructor({ pos = [0, 0], size = [1, 1], angle = 0, pen = [255, 255, 255], hoverPen = [255, 255, 0], handlePen = [150, 255, 255], handleHoverPen = [255, 255, 0], translateSnap = false, snapSize = 1.0, movable = true, rotatable = true, resizable = true, removable = false, invertible = false } = {}) {
    this.vb             = null;
    this.z              = 10;
    this.visible        = true;
    this.translatable   = movable;
    this.rotatable      = rotatable;
    this.resizable      = resizable;
    this.removable      = removable;
    this.invertible     = invertible;
    this.aspectLocked   = false;
    this.maxBounds      = null;
    this.snapSize       = snapSize;
    this.translateSnap  = translateSnap;
    this.rotateSnap     = false;
    this.rotateSnapAngle = 15.0;
    this.scaleSnap      = false;
    this.scaleSnapSize  = snapSize;
    this.pen            = PgPen.mk(pen);
    this.hoverPen       = PgPen.mk(hoverPen);
    this.handlePen      = handlePen;
    this.handleHoverPen = handleHoverPen;
    this.currentPen     = this.pen;
    this.mouseHovering  = false;
    this.handles        = [];
    this.handleSize     = 5;
    this.freeHandleMoved = false;
    this.isMoving       = false;
    this.preMoveState   = null;
    this.drag           = { mode: null };
    this.state          = { pos: [0, 0], size: [1, 1], angle: 0 };
    this.lastState      = null;
    this.sigRegionChanged        = new PgSignal();
    this.sigRegionChangeFinished = new PgSignal();
    this.sigRegionChangeStarted  = new PgSignal();
    this.setPos(pos, { update: false });
    this.setAngle(angle, { update: false });
    this.setSize(size, { update: false });
    this.stateChanged(true);
  }

  setZValue(z) {
    this.z = z;
    for (const h of this.handles) h.item.z = z + 1;
  }

  setPen(pen) {
    this.pen        = PgPen.mk(pen);
    this.currentPen = this.pen;
    this.update();
  }

  update() {
    if (this.vb) this.vb.update();
  }

  show() {
    this.visible = true;
    if (this.vb) this.vb.itemBoundsChanged(this);
    this.update();
  }

  hide() {
    this.visible = false;
    if (this.vb) this.vb.itemBoundsChanged(this);
    this.update();
  }

  getState() {
    return { pos: this.state.pos.slice(), size: this.state.size.slice(), angle: this.state.angle };
  }

  saveState() {
    return this.getState();
  }

  mapToParent(p) {
    const r = PgRoi.rotate(this.state.angle, p);
    return [r[0] + this.state.pos[0], r[1] + this.state.pos[1]];
  }

  mapFromParent(p) {
    return PgRoi.rotate(-this.state.angle, [p[0] - this.state.pos[0], p[1] - this.state.pos[1]]);
  }

  mapSceneToParent(scenePos) {
    const v = this.vb.mapSceneToView(scenePos.x, scenePos.y);
    return [v.x, v.y];
  }

  sceneToLocal(scenePos) {
    return this.mapFromParent(this.mapSceneToParent(scenePos));
  }

  setPos(pos, { update = true, finish = true } = {}) {
    this.state.pos = [pos[0], pos[1]];
    if (update) this.stateChanged(finish);
  }

  setSize(size, { center = null, centerLocal = null, snap = false, update = true, finish = true } = {}) {
    let s = [size[0], size[1]];
    if (snap) s = [Math.round(s[0] / this.scaleSnapSize) * this.scaleSnapSize, Math.round(s[1] / this.scaleSnapSize) * this.scaleSnapSize];
    let c = center;
    if (centerLocal !== null) {
      const old = [this.state.size[0] === 0 ? 1 : this.state.size[0], this.state.size[1] === 0 ? 1 : this.state.size[1]];
      c = [centerLocal[0] / old[0], centerLocal[1] / old[1]];
    }
    if (c !== null) {
      const a      = this.mapToParent([c[0] * this.state.size[0], c[1] * this.state.size[1]]);
      const b      = this.mapToParent([c[0] * s[0], c[1] * s[1]]);
      const newPos = [this.state.pos[0] + a[0] - b[0], this.state.pos[1] + a[1] - b[1]];
      this.setPos(newPos, { update: false, finish: false });
    }
    this.state.size = s;
    if (update) this.stateChanged(finish);
  }

  setAngle(angle, { center = null, centerLocal = null, snap = false, update = true, finish = true } = {}) {
    let a = angle;
    if (snap) a = Math.round(a / this.rotateSnapAngle) * this.rotateSnapAngle;
    const oldAngle   = this.state.angle;
    let local        = centerLocal;
    if (center !== null) local = [center[0] * this.state.size[0], center[1] * this.state.size[1]];
    if (local !== null) {
      const before = PgRoi.rotate(oldAngle, local);
      const after  = PgRoi.rotate(a, local);
      this.state.angle = a;
      this.translate([before[0] - after[0], before[1] - after[1]], { update: false });
    }
    this.state.angle = a;
    if (update) this.stateChanged(finish);
  }

  translate(d, { snap = null, update = true, finish = true } = {}) {
    let pos  = [this.state.pos[0] + d[0], this.state.pos[1] + d[1]];
    const s  = snap === null ? this.translateSnap : snap;
    if (s !== false) pos = this.getSnapPosition(pos);
    this.setPos(pos, { update, finish });
  }

  getSnapPosition(pos) {
    if (this.snapSize === null) return pos;
    return [PgRoi.roundHalfEven(pos[0] / this.snapSize) * this.snapSize, PgRoi.roundHalfEven(pos[1] / this.snapSize) * this.snapSize];
  }

  addHandle(info) {
    const h = new PgHandle(this.handleSize, info.type, this.handlePen, this.handleHoverPen);
    h.rois.push(this);
    info.item = h;
    h.setPos(info.pos[0] * this.state.size[0], info.pos[1] * this.state.size[1]);
    h.z = this.z + 1;
    this.handles.push(info);
    this.stateChanged(true);
    return h;
  }

  addFreeHandle(pos) {
    return this.addHandle({ name: null, type: "f", pos: [pos[0], pos[1]] });
  }

  addScaleHandle(pos, center) {
    const info = { name: null, type: "s", center: [center[0], center[1]], pos: [pos[0], pos[1]], lockAspect: false };
    if (pos[0] === center[0]) info.xoff = true;
    if (pos[1] === center[1]) info.yoff = true;
    return this.addHandle(info);
  }

  addRotateHandle(pos, center) {
    return this.addHandle({ name: null, type: "r", center: [center[0], center[1]], pos: [pos[0], pos[1]] });
  }

  getHandles() {
    return this.handles.map((h) => h.item);
  }

  indexOfHandle(handle) {
    return this.handles.findIndex((h) => h.item === handle);
  }

  stateKey() {
    const s = this.getState();
    return JSON.stringify([s.pos, s.size, s.angle, this.handles.map((h) => h.item.pos())]);
  }

  stateChanged(finish = true) {
    const key     = this.stateKey();
    const changed = this.lastState === null || key !== this.lastState;
    if (changed) {
      for (const h of this.handles) h.item.setPos(h.pos[0] * this.state.size[0], h.pos[1] * this.state.size[1]);
      this.update();
      if (this.vb) this.vb.itemBoundsChanged(this);
      this.sigRegionChanged.emit(this);
    } else if (this.freeHandleMoved) {
      if (this.vb) this.vb.itemBoundsChanged(this);
      this.sigRegionChanged.emit(this);
    }
    this.freeHandleMoved = false;
    this.lastState       = this.stateKey();
    if (finish) this.stateChangeFinished();
  }

  stateChangeFinished() {
    this.sigRegionChangeFinished.emit(this);
  }

  handleMoveStarted() {
    this.preMoveState = this.getState();
    this.sigRegionChangeStarted.emit(this);
  }

  moveStarted() {
    this.isMoving     = true;
    this.preMoveState = this.getState();
    this.sigRegionChangeStarted.emit(this);
  }

  moveFinished() {
    if (this.isMoving) this.stateChangeFinished();
    this.isMoving = false;
  }

  cancelMove() {
    this.isMoving = false;
    this.setState(this.preMoveState);
  }

  setState(state) {
    this.setPos(state.pos, { update: false });
    this.setSize(state.size, { update: false });
    this.setAngle(state.angle, { update: true });
  }

  static angleBetween(self, a) {
    return ((Math.atan2(self[1], self[0]) - Math.atan2(a[1], a[0])) * 180) / Math.PI;
  }

  movePoint(handle, pos, modifiers = {}, finish = true, coords = "parent") {
    const index    = this.indexOfHandle(handle);
    const h        = this.handles[index];
    const newState = this.getState();
    const p0       = this.mapToParent([h.pos[0] * this.state.size[0], h.pos[1] * this.state.size[1]]);
    const p1       = coords === "scene" ? this.mapSceneToParent(pos) : [pos[0], pos[1]];
    let cs = null;
    let lp0 = null;
    let lp1 = null;
    if (h.center) {
      cs  = [h.center[0] * this.state.size[0], h.center[1] * this.state.size[1]];
      const a = this.mapFromParent(p0);
      const b = this.mapFromParent(p1);
      lp0 = [a[0] - cs[0], a[1] - cs[1]];
      lp1 = [b[0] - cs[0], b[1] - cs[1]];
    }

    if (h.type === "t") {
      this.translate([p1[0] - p0[0], p1[1] - p0[1]], { snap: modifiers.ctrl ? true : null, update: false });
    } else if (h.type === "f") {
      const newPos = this.mapFromParent(p1);
      h.item.setPos(newPos[0], newPos[1]);
      h.pos = newPos;
      this.freeHandleMoved = true;
    } else if (h.type === "s") {
      if (h.center[0] === h.pos[0]) lp1[0] = 0;
      if (h.center[1] === h.pos[1]) lp1[1] = 0;
      if (this.scaleSnap || modifiers.ctrl) lp1 = [Math.round(lp1[0] / this.scaleSnapSize) * this.scaleSnapSize, Math.round(lp1[1] / this.scaleSnapSize) * this.scaleSnapSize];
      if (h.lockAspect || modifiers.alt) {
        const n   = Math.hypot(lp0[0], lp0[1]);
        const b1  = [lp0[0] / n, lp0[1] / n];
        const dot = lp1[0] * b1[0] + lp1[1] * b1[1];
        lp1 = [dot * b1[0], dot * b1[1]];
      }
      const hs = [h.pos[0] - h.center[0], h.pos[1] - h.center[1]];
      if (hs[0] === 0) hs[0] = 1;
      if (hs[1] === 0) hs[1] = 1;
      const newSize = [lp1[0] / hs[0], lp1[1] / hs[1]];
      if (newSize[0] === 0) newSize[0] = newState.size[0];
      if (newSize[1] === 0) newSize[1] = newState.size[1];
      if (!this.invertible) {
        if (newSize[0] < 0) newSize[0] = newState.size[0];
        if (newSize[1] < 0) newSize[1] = newState.size[1];
      }
      if (this.aspectLocked) newSize[0] = newSize[1];
      const s0 = [h.center[0] * this.state.size[0], h.center[1] * this.state.size[1]];
      const s1 = [h.center[0] * newSize[0], h.center[1] * newSize[1]];
      const m  = this.mapToParent([s0[0] - s1[0], s0[1] - s1[1]]);
      const o  = this.mapToParent([0, 0]);
      newState.size = newSize;
      newState.pos  = [newState.pos[0] + m[0] - o[0], newState.pos[1] + m[1] - o[1]];
      this.setPos(newState.pos, { update: false });
      this.setSize(newState.size, { update: false });
    } else if (h.type === "r" || h.type === "rf") {
      if (h.type === "rf") this.freeHandleMoved = true;
      if (!this.rotatable) return;
      if (Math.hypot(lp1[0], lp1[1]) === 0 || Math.hypot(lp0[0], lp0[1]) === 0) return;
      let ang = newState.angle - PgRoi.angleBetween(lp0, lp1);
      if (this.rotateSnap || modifiers.ctrl) ang = Math.round(ang / this.rotateSnapAngle) * this.rotateSnapAngle;
      const before = this.mapToParent(cs);
      const after  = PgRoi.rotate(ang, cs);
      newState.angle = ang;
      newState.pos   = [newState.pos[0] + before[0] - (after[0] + this.state.pos[0]), newState.pos[1] + before[1] - (after[1] + this.state.pos[1])];
      this.setPos(newState.pos, { update: false });
      this.setAngle(ang, { update: false });
    }
    this.stateChanged(finish);
  }

  hoverEvent(ev) {
    let hover = false;
    if (!ev.isExit() && this.translatable && ev.acceptDrags("left")) hover = true;
    if (hover) {
      this.setMouseHover(true);
      ev.acceptClicks("left");
      ev.acceptClicks("right");
      ev.acceptClicks("middle");
    } else {
      this.setMouseHover(false);
    }
  }

  setMouseHover(hover) {
    if (this.mouseHovering === hover) return;
    this.mouseHovering = hover;
    const pen = hover ? this.hoverPen : this.pen;
    if (this.currentPen !== pen) {
      this.currentPen = pen;
      this.update();
    }
  }

  mouseClickEvent(ev) {
    if (ev.button === "right" && this.isMoving) {
      ev.accept();
      this.cancelMove();
    }
    if (ev.button === "right" && this.removable) ev.accept();
    else if (!ev.accepted) ev.ignore();
  }

  mouseDragEvent(ev) {
    if (ev.isStart()) {
      if (ev.button === "left") {
        const mods = { ...ev.modifiers, ctrl: false };
        const none = PgMouseEvent.none(mods);
        if (this.translatable && none) this.drag.mode = "translate";
        else if (this.rotatable && mods.alt && !mods.shift && !mods.meta) this.drag.mode = "rotate";
        else if (this.resizable && mods.shift && !mods.alt && !mods.meta) this.drag.mode = "scale";
        else this.drag.mode = null;
        if (this.drag.mode !== null) {
          this.moveStarted();
          this.drag.startPos     = this.mapSceneToParent(ev.buttonDownScenePos);
          this.drag.startState   = this.saveState();
          this.drag.cursorOffset = [this.state.pos[0] - this.drag.startPos[0], this.state.pos[1] - this.drag.startPos[1]];
          ev.accept();
        } else {
          ev.ignore();
        }
      } else {
        this.drag.mode = null;
        ev.ignore();
      }
    }
    if (ev.isFinish() && this.drag.mode !== null) {
      this.moveFinished();
      return;
    }
    if (!this.isMoving || this.drag.mode === null) return;

    const snap = ev.modifiers.ctrl ? true : null;
    const pos  = this.mapSceneToParent(ev.scenePos);
    if (this.drag.mode === "translate") {
      const newPos = [pos[0] + this.drag.cursorOffset[0], pos[1] + this.drag.cursorOffset[1]];
      this.translate([newPos[0] - this.state.pos[0], newPos[1] - this.state.pos[1]], { snap, finish: false });
    } else if (this.drag.mode === "rotate") {
      const diff  = 0.5 * (ev.scenePos.x - ev.buttonDownScenePos.x);
      const angle = this.drag.startState.angle - diff;
      this.setAngle(angle, { centerLocal: this.sceneToLocal(ev.buttonDownScenePos), snap: snap === true, finish: false });
    } else if (this.drag.mode === "scale") {
      const diff = Math.pow(1.01, -(ev.scenePos.y - ev.buttonDownScenePos.y));
      this.setSize([this.drag.startState.size[0] * diff, this.drag.startState.size[1] * diff], { centerLocal: this.sceneToLocal(ev.buttonDownScenePos), snap: snap === true, finish: false });
    }
  }

  devicePoint(local) {
    const p = this.mapToParent(local);
    return this.vb.mapViewToScene(p[0], p[1]);
  }

  sceneItems() {
    const list = [{ item: this, z: this.z }];
    for (const h of this.handles) {
      if (h.item.visible) list.push({ item: h.item, z: this.z + h.item.z + 0.5 });
    }
    return list;
  }

  paintHandles(ctx) {
    for (const h of this.handles) {
      if (h.item.visible) h.item.paint(ctx);
    }
  }
}

class PgLineSegmentRoi extends PgRoi {
  constructor(positions, options = {}) {
    super({ pos: options.pos || [0, 0], size: [1, 1], ...options });
    for (const p of positions) this.addFreeHandle(p);
  }

  endpoints() {
    return this.handles.map((h) => h.item);
  }

  getState() {
    const state  = super.getState();
    state.points = this.handles.map((h) => h.item.pos());
    return state;
  }

  setState(state) {
    super.setState(state);
    const p1 = [state.points[0][0] + state.pos[0], state.points[0][1] + state.pos[1]];
    const p2 = [state.points[1][0] + state.pos[0], state.points[1][1] + state.pos[1]];
    this.movePoint(this.handles[0].item, p1, {}, false);
    this.movePoint(this.handles[1].item, p2, {}, true);
  }

  devicePoly() {
    const [h1, h2] = this.endpoints().map((h) => this.devicePoint(h.pos()));
    const dx = h2.x - h1.x;
    const dy = h2.y - h1.y;
    const len = Math.hypot(dx, dy);
    if (len === 0) return null;
    const n = [(-dy / len) * 4, (dx / len) * 4];
    return [[h1.x + n[0], h1.y + n[1]], [h2.x + n[0], h2.y + n[1]], [h2.x - n[0], h2.y - n[1]], [h1.x - n[0], h1.y - n[1]]];
  }

  hit(x, y) {
    const poly = this.devicePoly();
    return this.visible && poly !== null && PgGeom.polyContains(poly, x, y);
  }

  hitRect(x0, y0, x1, y1) {
    const poly = this.devicePoly();
    return this.visible && poly !== null && PgGeom.polyIntersectsRect(poly, x0, y0, x1, y1);
  }

  viewBounds() {
    const poly = this.devicePoly();
    if (!poly || !this.vb) return null;
    const pts = poly.map(([x, y]) => this.vb.mapSceneToView(x, y));
    const xs  = pts.map((p) => p.x);
    const ys  = pts.map((p) => p.y);
    return { x: Math.min(...xs), y: Math.min(...ys), w: Math.max(...xs) - Math.min(...xs), h: Math.max(...ys) - Math.min(...ys) };
  }

  paint(ctx) {
    const [h1, h2] = this.endpoints().map((h) => this.devicePoint(h.pos()));
    ctx.save();
    PgPen.apply(ctx, this.currentPen);
    ctx.beginPath();
    ctx.moveTo(h1.x, h1.y);
    ctx.lineTo(h2.x, h2.y);
    ctx.stroke();
    this.paintHandles(ctx);
    ctx.restore();
  }

  clientState() {
    return {
      pos     : this.state.pos.slice(),
      size    : this.state.size.slice(),
      angle   : this.state.angle,
      handles : this.handles.map((h) => ({ pos: h.pos.slice(), item: h.item.pos() })),
    };
  }

  applyServerState(state) {
    this.state.pos   = state.pos.slice();
    this.state.size  = state.size.slice();
    this.state.angle = state.angle;
    state.handles.forEach((h, i) => {
      this.handles[i].pos = h.pos.slice();
      this.handles[i].item.setPos(h.item[0], h.item[1]);
    });
    this.lastState       = this.stateKey();
    this.freeHandleMoved = false;
    if (this.vb) this.vb.itemBoundsChanged(this);
    this.update();
  }
}

class PgRectRoi extends PgRoi {
  constructor(size, options = {}) {
    super({ pos: [0, 0], size: [size, size], ...options });
    this.addScaleHandle([1, 1], [0, 0]);
    this.addRotateHandle([0, 0], [0.5, 0.5]);
  }

  devicePoly() {
    const s = this.state.size;
    return [[0, 0], [s[0], 0], [s[0], s[1]], [0, s[1]]].map((p) => {
      const d = this.devicePoint(p);
      return [d.x, d.y];
    });
  }

  hit(x, y) {
    return this.visible && PgGeom.polyContains(this.devicePoly(), x, y);
  }

  hitRect(x0, y0, x1, y1) {
    return this.visible && PgGeom.polyIntersectsRect(this.devicePoly(), x0, y0, x1, y1);
  }

  viewBounds() {
    const s   = this.state.size;
    const pts = [[0, 0], [s[0], 0], [s[0], s[1]], [0, s[1]]].map((p) => this.mapToParent(p));
    const xs  = pts.map((p) => p[0]);
    const ys  = pts.map((p) => p[1]);
    return { x: Math.min(...xs), y: Math.min(...ys), w: Math.max(...xs) - Math.min(...xs), h: Math.max(...ys) - Math.min(...ys) };
  }

  paint(ctx) {
    const poly = this.devicePoly();
    ctx.save();
    PgPen.apply(ctx, this.currentPen);
    ctx.beginPath();
    poly.forEach(([x, y], i) => (i === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y)));
    ctx.closePath();
    ctx.stroke();
    this.paintHandles(ctx);
    ctx.restore();
  }

  getAffineSliceParams(data) {
    const origin = this.mapToParent([0, 0]);
    const ex     = this.mapToParent([1, 0]);
    const ey     = this.mapToParent([0, 1]);
    const vx     = [ex[0] - origin[0], ex[1] - origin[1]];
    const vy     = [ey[0] - origin[0], ey[1] - origin[1]];
    const sx     = 1.0 / Math.hypot(vx[0], vx[1]);
    const sy     = 1.0 / Math.hypot(vy[0], vy[1]);
    const vectors = [[vx[0] * sx, vx[1] * sx], [vy[0] * sy, vy[1] * sy]];
    const shape   = [Math.abs(this.state.size[0] / sx), Math.abs(this.state.size[1] / sy)];
    return { shape, vectors, origin };
  }

  getArrayRegion(data, shape) {
    const params = this.getAffineSliceParams(data);
    return PgAffineSlice.affineSlice2d(data, shape, params.shape, params.vectors, params.origin);
  }
}

class PgInfiniteLine {
  constructor({ pos = 0, angle = 90, pen = [200, 200, 100], hoverPen = null, movable = false, bounds = null, span = [0, 1], flip = false } = {}) {
    this.vb        = null;
    this.z         = 0;
    this.visible   = true;
    this.angle     = angle;
    this.p         = angle === 90 ? [pos, 0] : [0, pos];
    this.pen       = PgPen.mk(pen);
    this.hoverPen  = hoverPen ? PgPen.mk(hoverPen) : { color: [255, 0, 0, 255], width: this.pen.width, style: "solid" };
    this.currentPen = this.pen;
    this.movable   = movable;
    this.maxRange  = bounds || [null, null];
    this.span      = span;
    this.flip      = flip;
    this.markers   = [];
    this.moving    = false;
    this.mouseHovering = false;
    this.sigPositionChanged        = new PgSignal();
    this.sigPositionChangeFinished = new PgSignal();
    this.sigDragged                = new PgSignal();
  }

  addMarker(marker, position = 0.5, size = 10.0) {
    const polys = [];
    if (marker.includes("<|")) polys.push([[0.5, 0], [0, -0.5], [-0.5, 0]]);
    if (marker.includes("|>")) polys.push([[0.5, 0], [0, 0.5], [-0.5, 0]]);
    this.markers.push({ polys, position, size });
  }

  maxMarkerSize() {
    return this.markers.length ? Math.max(...this.markers.map((m) => m.size / 2)) : 0;
  }

  setPos(value) {
    const newPos = this.angle === 90 ? [value, 0] : [0, value];
    const k      = this.angle === 90 ? 0 : 1;
    if (this.maxRange[0] !== null) newPos[k] = Math.max(newPos[k], this.maxRange[0]);
    if (this.maxRange[1] !== null) newPos[k] = Math.min(newPos[k], this.maxRange[1]);
    if (this.p[0] !== newPos[0] || this.p[1] !== newPos[1]) {
      this.p = newPos;
      if (this.vb) this.vb.update();
      this.sigPositionChanged.emit(this);
    }
  }

  setValue(v) {
    this.setPos(v);
  }

  value() {
    return this.angle === 90 ? this.p[0] : this.p[1];
  }

  show() {
    this.visible = true;
    if (this.vb) {
      this.vb.itemBoundsChanged(this);
      this.vb.update();
    }
  }

  hide() {
    this.visible = false;
    if (this.vb) {
      this.vb.itemBoundsChanged(this);
      this.vb.update();
    }
  }

  setSpan(mn, mx) {
    this.span = [mn, mx];
    if (this.vb) this.vb.update();
  }

  dataBounds(axis) {
    if (this.angle === 0) return axis === 0 ? null : [this.p[1], this.p[1]];
    return axis === 1 ? null : [this.p[0], this.p[0]];
  }

  mapRectToView(rect) {
    return rect;
  }

  endPoints(vb) {
    const vr = vb.viewRect();
    if (this.angle === 0) {
      const left  = vr.x + vr.w * this.span[0];
      const right = vr.x + vr.w * this.span[1];
      return [vb.mapViewToScene(left, this.p[1]), vb.mapViewToScene(right, this.p[1])];
    }
    const bottom = vr.y + vr.h * this.span[0];
    const top    = vr.y + vr.h * this.span[1];
    return [vb.mapViewToScene(this.p[0], bottom), vb.mapViewToScene(this.p[0], top)];
  }

  shapePoly(vb) {
    const [a, b] = this.endPoints(vb);
    const w      = this.maxMarkerSize() + Math.max(this.pen.width / 2, this.hoverPen.width / 2) + 1;
    if (this.angle === 0) return PgGeom.rectPoly(Math.min(a.x, b.x), a.y - w, Math.abs(b.x - a.x), 2 * w);
    return PgGeom.rectPoly(a.x - w, Math.min(a.y, b.y), 2 * w, Math.abs(b.y - a.y));
  }

  hit(x, y) {
    return this.visible && this.vb !== null && PgGeom.polyContains(this.shapePoly(this.vb), x, y);
  }

  hitRect(x0, y0, x1, y1) {
    return this.visible && this.vb !== null && PgGeom.polyIntersectsRect(this.shapePoly(this.vb), x0, y0, x1, y1);
  }

  sceneItems() {
    return this.movable ? [{ item: this, z: this.z }] : [];
  }

  paint(ctx, vb) {
    const [a, b] = this.endPoints(vb);
    const pen    = this.currentPen;
    ctx.save();
    PgPen.apply(ctx, pen);
    ctx.beginPath();
    if (this.angle === 0) {
      const y = PgPen.crisp(a.y, pen.width);
      ctx.moveTo(a.x, y);
      ctx.lineTo(b.x, y);
    } else {
      const x = PgPen.crisp(a.x, pen.width);
      ctx.moveTo(x, a.y);
      ctx.lineTo(x, b.y);
    }
    ctx.stroke();
    if (this.markers.length) {
      const length = Math.hypot(b.x - a.x, b.y - a.y);
      const angle  = Math.atan2(b.y - a.y, b.x - a.x);
      const upSign = this.flip ? (vb.state.yInverted ? 1 : -1) : (vb.state.yInverted ? -1 : 1);
      ctx.translate(a.x, a.y);
      ctx.rotate(angle);
      ctx.scale(1, this.angle === 0 ? upSign : 1);
      ctx.fillStyle = PgPen.css(pen.color);
      for (const marker of this.markers) {
        const x = length * marker.position;
        for (const poly of marker.polys) {
          ctx.beginPath();
          poly.forEach(([px, py], i) => {
            const X = x + px * marker.size;
            const Y = py * marker.size;
            if (i === 0) ctx.moveTo(X, Y);
            else ctx.lineTo(X, Y);
          });
          ctx.closePath();
          ctx.fill();
        }
      }
    }
    ctx.restore();
  }

  hoverEvent(ev) {
    this.setMouseHover(!ev.isExit() && this.movable && ev.acceptDrags("left"));
  }

  setMouseHover(hover) {
    if (this.mouseHovering === hover) return;
    this.mouseHovering = hover;
    this.currentPen    = hover ? this.hoverPen : this.pen;
    if (this.vb) this.vb.update();
  }

  sceneValue(scenePos) {
    const v = this.vb.mapSceneToView(scenePos.x, scenePos.y);
    return this.angle === 0 ? v.y : v.x;
  }

  mouseDragEvent(ev) {
    if (!this.movable || ev.button !== "left") return;
    if (ev.isStart()) {
      this.moving        = true;
      this.cursorOffset  = this.value() - this.sceneValue(ev.buttonDownScenePos);
      this.startPosition = this.value();
    }
    ev.accept();
    if (!this.moving) return;
    this.setPos(this.cursorOffset + this.sceneValue(ev.scenePos));
    this.sigDragged.emit(this);
    if (ev.isFinish()) {
      this.moving = false;
      this.sigPositionChangeFinished.emit(this);
    }
  }

  mouseClickEvent(ev) {
    if (this.moving && ev.button === "right") {
      ev.accept();
      this.setPos(this.startPosition);
      this.moving = false;
      this.sigDragged.emit(this);
      this.sigPositionChangeFinished.emit(this);
    }
  }
}

class PgAffineSlice {
  static affineSlice2d(data, dataShape, shape, vectors, origin) {
    const nx   = Math.ceil(shape[0]);
    const ny   = Math.ceil(shape[1]);
    const w    = dataShape[0];
    const h    = dataShape[1];
    const nch  = dataShape.length === 3 ? dataShape[2] : 1;
    const out  = new Float64Array(nx * ny * nch);
    const coords = new Float64Array(2 * nx * ny);

    for (let i = 0; i < nx; i += 1) {
      for (let j = 0; j < ny; j += 1) {
        const x  = i * vectors[0][0] + j * vectors[1][0] + origin[0];
        const y  = i * vectors[0][1] + j * vectors[1][1] + origin[1];
        const k  = i * ny + j;
        coords[k]           = x;
        coords[nx * ny + k] = y;
        const x0 = Math.floor(x);
        const y0 = Math.floor(y);
        const inside = x0 >= 0 && x <= w - 1 && y0 >= 0 && y <= h - 1;
        if (!inside) continue;
        const dx  = x - x0;
        const dy  = y - y0;
        const xs  = [x0, x0 + 1].map((v) => (v < 0 || v >= w ? 0 : v));
        const ys  = [y0, y0 + 1].map((v) => (v < 0 || v >= h ? 0 : v));
        const wx  = [1 - dx, dx];
        const wy  = [1 - dy, dy];
        for (let c = 0; c < nch; c += 1) {
          const v = (a, b) => data[(xs[a] * h + ys[b]) * nch + c] * (wx[a] * wy[b]);
          out[k * nch + c] = (v(0, 0) + v(1, 0)) + (v(0, 1) + v(1, 1));
        }
      }
    }
    return { data: out, shape: nch > 1 ? [nx, ny, nch] : [nx, ny], coords };
  }
}

window.PgHandle          = PgHandle;
window.PgRoi             = PgRoi;
window.PgLineSegmentRoi  = PgLineSegmentRoi;
window.PgRectRoi         = PgRectRoi;
window.PgInfiniteLine    = PgInfiniteLine;
window.PgAffineSlice     = PgAffineSlice;
