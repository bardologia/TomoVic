"use strict";

class HairlineGeometry {
  static roundedSector(theta, half, radius, apex, roundApex, roundRim, steps) {
    const points = [[apex * Math.cos(theta), apex * Math.sin(theta)]];
    for (let k = 0; k <= steps; k++) {
      const phi = theta - half + (2 * half * k) / steps;
      points.push([radius * Math.cos(phi), radius * Math.sin(phi)]);
    }
    const radii = points.map((_, i) => (i === 0 ? roundApex : i === 1 || i === points.length - 1 ? roundRim : 0));
    return HairlineGeometry.samples(HL.fillet(points, radii, 4));
  }

  static samples(points) {
    const kept = points.filter((p, i) => {
      const prev = points[(i + points.length - 1) % points.length];
      return Math.hypot(p[0] - prev[0], p[1] - prev[1]) > 1e-6;
    });
    const cu = kept.reduce((sum, p) => sum + p[0], 0) / kept.length;
    const cv = kept.reduce((sum, p) => sum + p[1], 0) / kept.length;
    return kept.map((p, i) => {
      const prev = kept[(i + kept.length - 1) % kept.length];
      const next = kept[(i + 1) % kept.length];
      const tu   = next[0] - prev[0];
      const tv   = next[1] - prev[1];
      const len  = Math.hypot(tu, tv);
      const out  = tv * (p[0] - cu) - tu * (p[1] - cv) >= 0 ? 1 : -1;
      return { u: p[0], v: p[1], nu: (out * tv) / len, nv: (-out * tu) / len };
    });
  }

  static backPlate(P, x0, x1, height, y, thick) {
    const arc  = 5;
    const face = HL.fillet([[x1, 0], [x1, height], [x0, height], [x0, 0]], [0.6, 4, 4, 0.6], arc);
    const at   = (depth) => face.map(([x, z]) => P(x, depth, z));
    return { sil: HL.poly(HL.hull(at(y).concat(at(y + thick)))), crease: HL.open(at(y + thick).slice(arc, 3 * (arc + 1))) };
  }

  static faceCircle(P, x, cy, cz, r) {
    const points = [];
    for (let k = 0; k < 28; k++) {
      const a = (k / 28) * Math.PI * 2;
      points.push(P(x, cy + r * Math.cos(a), cz + r * Math.sin(a)));
    }
    return HL.poly(points);
  }

  static inside(hull, p) {
    let sign = 0;
    for (let i = 0; i < hull.length; i++) {
      const a     = hull[i];
      const b     = hull[(i + 1) % hull.length];
      const cross = (b[0] - a[0]) * (p[1] - a[1]) - (b[1] - a[1]) * (p[0] - a[0]);
      if (Math.abs(cross) < 1e-9) continue;
      if (sign === 0) sign = Math.sign(cross);
      else if (Math.sign(cross) !== sign) return false;
    }
    return true;
  }
}

class HairlineFigureBase {
  constructor(svg, amount, scale) {
    this.amount = amount;
    this.chosen = null;
    this.C      = HL.Cam(45, 0.5, scale);
    this.g      = HL.mk("g", {}, svg);
  }

  static nearest(values, target) {
    let best = 0;
    for (let i = 1; i < values.length; i++) if (Math.abs(values[i] - target) < Math.abs(values[best] - target)) best = i;
    return best;
  }

  _camera(points, cy) {
    HL.fit(this.C, points, 200, cy);
    this.P     = HL.proj(this.C);
    this.front = HL.facing(this.C);
  }

  _shifted(dx, dy, dz) {
    return (x, y, z) => this.P(x + dx, y + dy, z + dz);
  }

  _height(pts) {
    const P  = HL.proj(this.C);
    const ys = pts.map(([x, y, z]) => P(x, y, z)[1]);
    return Math.max(...ys) - Math.min(...ys);
  }

  _onScreen(r, d) {
    return [(r + d) * Math.SQRT1_2, (d - r) * Math.SQRT1_2];
  }

  _screenBox(r0, d0, r1, d1, radius) {
    const corners = [[r1, d0], [r1, d1], [r0, d1], [r0, d0]].map(([r, d]) => this._onScreen(r, d));
    return HairlineGeometry.samples(HL.fillet(corners, [radius, radius, radius, radius], 4));
  }

  _plinth(x0, y0, x1, y1, r, depth) {
    const [ring, inner] = HL.rings(x0, y0, x1, y1, r, 2.2);
    HL.put(HL.solid(this.g), HL.prism(this.P, this.front, ring, inner, -depth, 0));
  }

  _start(stage, svg) {
    this.bag  = HL.disposer();
    this.loop = HL.register(stage, (dt, now) => this._tick(dt, now));
    this.bag.add(this.loop.unregister);
    this.bag.add(HL.pointer(stage, { move: (p) => this._move(p), leave: () => this._leave() }));
    this.bag.add(() => svg.replaceChildren());
  }

  _advance(items, now) {
    let moving = false;
    for (const item of items) {
      const value = HL.tval(item.tw, now);
      if (!HL.tdone(item.tw, now)) moving = true;
      if (value === item.drawn) continue;
      item.drawn = value;
      this._draw(item, value);
    }
    return moving;
  }

  _leave() {
    this._choose(null);
  }

  _choose(key) {
    if (key === this.chosen) return;
    this.chosen = key;
    this._retarget(performance.now());
  }

  set(value) {
    this.amount = value;
    this._retarget(performance.now());
  }

  destroy() {
    this.bag.dispose();
  }
}

class VoxelColumnFigure extends HairlineFigureBase {
  static RANGE     = [10, 20, 32];
  static BINS      = 12;
  static SLAB      = 8;
  static STEP      = 10.4;
  static PLINTH    = 42;
  static AXIS      = [-38, 38];
  static REACH     = 2.6;
  static STAGGER   = 45;
  static REST_PULL = 0.4;

  constructor({ stage, svg }, value) {
    super(svg, value, 1.8);
    this.widths  = Array.from({ length: VoxelColumnFigure.BINS }, (_, i) => this._width(i));
    this.restBin = this._restBin();
    this._camera(this._extent(), 162);
    this._plinth(-VoxelColumnFigure.PLINTH, -VoxelColumnFigure.PLINTH, VoxelColumnFigure.PLINTH, VoxelColumnFigure.PLINTH, 9, 5);
    this._buildAxis();
    this._buildSlabs();
    this._start(stage, svg);
  }

  _width(i) {
    return 9 + 19 * Math.exp(-((i / 1.1) ** 2)) + 17 * Math.exp(-(((i - 7.6) / 2) ** 2));
  }

  _restBin() {
    let best = 4;
    for (let i = 4; i < VoxelColumnFigure.BINS; i++) if (this.widths[i] > this.widths[best]) best = i;
    return best;
  }

  _extent() {
    const edge = VoxelColumnFigure.PLINTH;
    const top  = VoxelColumnFigure.BINS * VoxelColumnFigure.STEP;
    const out  = this.widths[this.restBin] + VoxelColumnFigure.RANGE[2] * Math.SQRT1_2;
    return [[-edge, -edge, -5], [edge, edge, -5], [edge, -edge, -5], [-edge, edge, -5], [0, 0, top], [out, -out, top * 0.75], [...VoxelColumnFigure.AXIS, top]];
  }

  _buildAxis() {
    const [ax, ay] = VoxelColumnFigure.AXIS;
    const top      = VoxelColumnFigure.BINS * VoxelColumnFigure.STEP;
    HL.mk("path", { d: HL.seg(this.P(ax, ay, 0), this.P(ax, ay, top)), class: "dash nf" }, this.g);
    this.ticks = this.widths.map((_, i) => {
      const tick = HL.flatDot(this.g, this.C, 0.9, "dot off");
      HL.place(tick, this.P(ax, ay, i * VoxelColumnFigure.STEP + VoxelColumnFigure.SLAB / 2));
      return tick;
    });
  }

  _buildSlabs() {
    this.slabs = this.widths.map((w, i) => {
      const [ring, inner] = HL.rings(-w, -w, w, w, 3.2, 1.3);
      const z0            = i * VoxelColumnFigure.STEP;
      const z1            = z0 + VoxelColumnFigure.SLAB;
      const rest          = i === this.restBin ? this.amount * VoxelColumnFigure.REST_PULL : 0;
      const el            = HL.solid(this.g);
      el.sil.classList.toggle("hi", i === this.restBin);
      return { i, ring, inner, z0, z1, el, tw: HL.tween(rest), drawn: NaN, restY: this.P(0, 0, (z0 + z1) / 2)[1] };
    });
  }

  _tick(dt, now) {
    return this._advance(this.slabs, now);
  }

  _draw(slab, out) {
    const moved = this._shifted(out * Math.SQRT1_2, -out * Math.SQRT1_2, 0);
    HL.put(slab.el, HL.prism(moved, this.front, slab.ring, slab.inner, slab.z0, slab.z1));
  }

  _move(p) {
    this._choose(HairlineFigureBase.nearest(this.slabs.map((slab) => slab.restY), p[1]));
  }

  _retarget(now) {
    const anchor = this.chosen === null ? this.restBin : this.chosen;
    for (const slab of this.slabs) {
      const distance = Math.abs(slab.i - anchor);
      const reach    = Math.max(0, 1 - distance / VoxelColumnFigure.REACH) ** 2;
      const target   = this.chosen === null ? (slab.i === this.restBin ? this.amount * VoxelColumnFigure.REST_PULL : 0) : this.amount * reach;
      HL.tset(slab.tw, target, now, distance * VoxelColumnFigure.STAGGER);
      slab.el.sil.classList.toggle("hi", slab.i === anchor);
      this.ticks[slab.i].setAttribute("class", slab.i === this.chosen ? "dot m" : "dot off");
    }
    this.loop.wake();
  }
}

class CovarianceFigure extends HairlineFigureBase {
  static RANGE     = [6, 12, 20];
  static N         = 6;
  static CELL      = 16;
  static FOOT      = 12.4;
  static DIAG      = 20;
  static FLOOR     = 2.2;
  static DECAY     = 0.5;
  static REST      = [1, 4];
  static REST_LIFT = 0.4;

  constructor({ stage, svg }, value) {
    super(svg, value, 2.3);
    const span = CovarianceFigure.N * CovarianceFigure.CELL;
    this._camera(this._extent(span), 166);
    this._plinth(-4, -4, span + 4, span + 4, 7, 4);
    this._buildTiles();
    this._start(stage, svg);
  }

  _extent(span) {
    const top = CovarianceFigure.DIAG + CovarianceFigure.RANGE[2];
    return [[-4, -4, -4], [span + 4, span + 4, -4], [span + 4, -4, -4], [-4, span + 4, -4], [0, span, top], [span, 0, top]];
  }

  _buildTiles() {
    const n     = CovarianceFigure.N;
    const cells = [];
    for (let r = 0; r < n; r++) for (let c = 0; c < n; c++) cells.push([r, c]);
    cells.sort((a, b) => (a[1] + n - 1 - a[0]) - (b[1] + n - 1 - b[0]));
    this.tiles  = cells.map(([r, c]) => this._buildTile(r, c));
    this.byCell = new Map(this.tiles.map((tile) => [`${tile.r},${tile.c}`, tile]));
  }

  _buildTile(r, c) {
    const n             = CovarianceFigure.N;
    const inset         = (CovarianceFigure.CELL - CovarianceFigure.FOOT) / 2;
    const x0            = c * CovarianceFigure.CELL + inset;
    const y0            = (n - 1 - r) * CovarianceFigure.CELL + inset;
    const [ring, inner] = HL.rings(x0, y0, x0 + CovarianceFigure.FOOT, y0 + CovarianceFigure.FOOT, 2.4, 1);
    const h             = CovarianceFigure.FLOOR + (CovarianceFigure.DIAG - CovarianceFigure.FLOOR) * CovarianceFigure.DECAY ** Math.abs(r - c);
    const group         = HL.mk("g", {}, this.g);
    const el            = HL.solid(group);
    const dot           = r === c ? HL.flatDot(group, this.C, 1.1, "dot m") : null;
    const lit           = this._inPair(r, c, CovarianceFigure.REST);
    const hull          = HL.hull(HL.ringAt(this.P, ring, 0).concat(HL.ringAt(this.P, ring, h)));
    el.sil.classList.toggle("hi", lit);
    return { r, c, h, ring, inner, el, dot, hull, centre: [x0 + CovarianceFigure.FOOT / 2, y0 + CovarianceFigure.FOOT / 2], tw: HL.tween(lit ? this.amount * CovarianceFigure.REST_LIFT : 0), drawn: NaN };
  }

  _inPair(r, c, pair) {
    return (r === pair[0] && c === pair[1]) || (r === pair[1] && c === pair[0]);
  }

  _tick(dt, now) {
    return this._advance(this.tiles, now);
  }

  _draw(tile, up) {
    HL.put(tile.el, HL.prism(this.P, this.front, tile.ring, tile.inner, 0, tile.h + up));
    if (tile.dot) HL.place(tile.dot, this.P(tile.centre[0], tile.centre[1], tile.h + up));
  }

  _move(p) {
    for (let i = this.tiles.length - 1; i >= 0; i--) {
      if (HairlineGeometry.inside(this.tiles[i].hull, p)) return this._choose(this.tiles[i]);
    }
    const [x, y] = HL.unproj(this.C, p[0], p[1], 0);
    const c      = Math.floor(x / CovarianceFigure.CELL);
    const r      = CovarianceFigure.N - 1 - Math.floor(y / CovarianceFigure.CELL);
    this._choose(this.byCell.get(`${r},${c}`) || null);
  }

  _retarget(now) {
    const pair = this.chosen === null ? CovarianceFigure.REST : [this.chosen.r, this.chosen.c];
    const lift = this.chosen === null ? this.amount * CovarianceFigure.REST_LIFT : this.amount;
    for (const tile of this.tiles) {
      const lit = this._inPair(tile.r, tile.c, pair);
      HL.tset(tile.tw, lit ? lift : 0, now, 0);
      tile.el.sil.classList.toggle("hi", lit);
    }
    this.loop.wake();
  }
}

class PhysicsProfile {
  static power(t, canopy) {
    return 0.06 + 0.9 * Math.exp(-(((t - 0.04) / 0.11) ** 2)) + 0.75 * Math.exp(-(((t - canopy) / 0.15) ** 2));
  }

  static sampled(n, canopy) {
    const values = Array.from({ length: n }, (_, i) => PhysicsProfile.power(i / (n - 1), canopy));
    const peak   = Math.max(...values);
    return values.map((value) => value / peak);
  }

  static blurred(values, width) {
    const out  = values.map((_, i) => {
      let sum    = 0;
      let weight = 0;
      values.forEach((value, j) => {
        const w = Math.exp(-(((i - j) / width) ** 2));
        sum    += w * value;
        weight += w;
      });
      return sum / weight;
    });
    const peak = Math.max(...out);
    return out.map((value) => value / peak);
  }
}

class PowerCupFigure extends HairlineFigureBase {
  static RANGE  = [2, 4, 7];
  static BINS   = 9;
  static BIN    = 5.4;
  static DISC   = 2.2;
  static RMAX   = 8;
  static RMIN   = 1.6;
  static CANOPY = 0.68;
  static COLUMN = -19;
  static CUP    = 21;
  static CUP_R  = 10;
  static CUP_H  = 30;
  static FULL   = 0.84;
  static TARGET = 0.74;
  static TICKS  = 5;
  static REST   = 5;

  constructor({ stage, svg }, value) {
    super(svg, value, 4.2);
    this.column = this._onScreen(PowerCupFigure.COLUMN, 0);
    this.cup    = this._onScreen(PowerCupFigure.CUP, 0);
    this.radii  = PhysicsProfile.sampled(PowerCupFigure.BINS, PowerCupFigure.CANOPY).map((p) => PowerCupFigure.RMIN + (PowerCupFigure.RMAX - PowerCupFigure.RMIN) * p);
    this.total  = this.radii.reduce((sum, r) => sum + r, 0);
    this._camera(this._extent(), 166);
    this._buildBoard();
    this._buildColumn();
    this._buildCup();
    this.level      = HL.tween(PowerCupFigure.REST + 0.5);
    this.drawnLevel = NaN;
    this._start(stage, svg);
    this._retarget(performance.now());
  }

  _extent() {
    const top = (PowerCupFigure.BINS - 1) * PowerCupFigure.BIN + PowerCupFigure.DISC;
    const r0  = PowerCupFigure.COLUMN - 14;
    const r1  = PowerCupFigure.CUP + 15;
    return [[...this._onScreen(r0, -15), -3], [...this._onScreen(r1, -15), -3], [...this._onScreen(r0, 15), -3], [...this._onScreen(r1, 15), -3], [...this.column, top], [...this.cup, PowerCupFigure.CUP_H]];
  }

  _buildBoard() {
    const r0 = PowerCupFigure.COLUMN - 14;
    const r1 = PowerCupFigure.CUP + 15;
    HL.put(HL.solid(this.g), HL.prism(this.P, this.front, this._screenBox(r0, -15, r1, 15, 6), this._screenBox(r0 + 2.2, -12.8, r1 - 2.2, 12.8, 4), -3, 0));
  }

  _buildColumn() {
    const at  = this._shifted(this.column[0], this.column[1], 0);
    const top = (PowerCupFigure.BINS - 1) * PowerCupFigure.BIN + PowerCupFigure.DISC + 4;
    HL.mk("path", { d: HL.seg(at(0, 0, 0), at(0, 0, top)), class: "dash nf" }, this.g);
    this.discs = this.radii.map((r, i) => {
      const group = HL.mk("g", {}, this.g);
      const ghost = HL.mk("path", { class: "nf lo" }, group);
      const el    = HL.solid(group);
      const z0    = i * PowerCupFigure.BIN;
      return { i, r, z0, group, ghost, el, ring: HL.circ(r, 40), tw: HL.tween(0), drawn: "", restY: at(0, 0, z0 + PowerCupFigure.DISC / 2)[1] };
    });
    this.pour = HL.mk("path", { class: "dash nf" }, this.g);
  }

  _buildCup() {
    const at    = this._shifted(this.cup[0], this.cup[1], 0);
    const R     = PowerCupFigure.CUP_R;
    const H     = PowerCupFigure.CUP_H;
    const outer = HL.circ(R, 64);
    this.liquid = HL.solid(this.g);
    HL.mk("path", { d: HL.poly(HL.ringAt(at, HL.circ(R - 1.2, 64), H * PowerCupFigure.TARGET)), class: "dash nf" }, this.g);
    HL.mk("path", { d: HL.poly(HL.hull(HL.ringAt(at, outer, 0).concat(HL.ringAt(at, outer, H)))), class: "nf" }, this.g);
    HL.mk("path", { d: HL.poly(HL.ringAt(at, outer, H)) + HL.poly(HL.ringAt(at, HL.circ(R - 1.2, 64), H)), class: "nf" }, this.g);
    const side  = HL.extremes(at, outer)[0];
    const index = outer.indexOf(side);
    const arc   = Array.from({ length: 7 }, (_, k) => outer[(index + k - 1 + outer.length) % outer.length]);
    const ticks = Array.from({ length: PowerCupFigure.TICKS }, (_, k) => HL.open(HL.ringAt(at, arc, (H * (k + 1)) / (PowerCupFigure.TICKS + 1)))).join("");
    HL.mk("path", { d: ticks, class: "nf lo" }, this.g);
  }

  _tick(dt, now) {
    const level = HL.tval(this.level, now);
    let moving  = !HL.tdone(this.level, now);
    for (const disc of this.discs) {
      const slide = HL.tval(disc.tw, now);
      if (!HL.tdone(disc.tw, now)) moving = true;
      const share = HL.clamp(level - disc.i, 0, 1);
      const key   = `${share}|${slide}`;
      if (key === disc.drawn) continue;
      disc.drawn = key;
      this._drawDisc(disc, share, slide);
    }
    if (level !== this.drawnLevel) {
      this.drawnLevel = level;
      this._drawFill(level);
    }
    this._drawPour(level, now);
    return moving;
  }

  _drawDisc(disc, share, slide) {
    const home  = this._shifted(this.column[0], this.column[1], 0);
    const [x, y] = this._onScreen(slide, 0);
    const moved = this._shifted(this.column[0] + x, this.column[1] + y, 0);
    const z1    = disc.z0 + PowerCupFigure.DISC;
    const left  = 1 - share;
    disc.ghost.setAttribute("d", share > 0 ? HL.poly(HL.ringAt(home, disc.ring, z1)) : "");
    if (left < 0.03) {
      HL.put(disc.el, { sil: "", crease: "" });
      return;
    }
    const r = disc.r * Math.sqrt(left);
    HL.put(disc.el, HL.prism(moved, this.front, HL.circ(r, 40), HL.circ(Math.max(0.4, r - 0.8), 40), disc.z0, z1));
  }

  _drawFill(level) {
    const poured = this.discs.reduce((sum, disc) => sum + HL.clamp(level - disc.i, 0, 1) * disc.r, 0);
    const height = PowerCupFigure.FULL * PowerCupFigure.CUP_H * (poured / this.total);
    const at     = this._shifted(this.cup[0], this.cup[1], 0);
    const R      = PowerCupFigure.CUP_R - 1.2;
    if (height < 0.8) {
      HL.put(this.liquid, { sil: "", crease: "" });
      return;
    }
    HL.put(this.liquid, HL.prism(at, this.front, HL.circ(R, 64), HL.circ(R - 1, 64), 0.4, height));
  }

  _drawPour(level, now) {
    const i = Math.floor(level);
    const share = level - i;
    if (i < 0 || i >= this.discs.length || share <= 0.02 || share >= 0.98) {
      this.pour.setAttribute("d", "");
      return;
    }
    const disc   = this.discs[i];
    const slide  = HL.tval(disc.tw, now);
    const r      = disc.r * Math.sqrt(1 - share);
    const [x, y] = this._onScreen(slide + r, 0);
    const start  = this.P(this.column[0] + x, this.column[1] + y, disc.z0 + PowerCupFigure.DISC);
    const end    = this.P(this.cup[0], this.cup[1], PowerCupFigure.CUP_H + 1);
    const lift   = Math.min(start[1], end[1]) - 26;
    const mid    = [(start[0] + end[0]) / 2, lift];
    this.pour.setAttribute("d", `M${HL.r2(start[0])} ${HL.r2(start[1])}Q${HL.r2(mid[0])} ${HL.r2(mid[1])} ${HL.r2(end[0])} ${HL.r2(end[1])}`);
  }

  _move(p) {
    this._choose(HairlineFigureBase.nearest(this.discs.map((disc) => disc.restY), p[1]));
  }

  _retarget(now) {
    const pick = this.chosen === null ? PowerCupFigure.REST : this.chosen;
    HL.tset(this.level, pick + 0.5, now, 0);
    for (const disc of this.discs) {
      HL.tset(disc.tw, disc.i === pick ? this.amount : 0, now, 0);
      disc.el.sil.classList.toggle("hi", disc.i === pick);
    }
    this.loop.wake();
  }
}

class MomentsBeamFigure extends HairlineFigureBase {
  static RANGE  = [0.08, 0.15, 0.24];
  static BARS   = 11;
  static PITCH  = 7.4;
  static BAR    = 4.8;
  static WIDE   = 7;
  static HMAX   = 30;
  static HMIN   = 1.8;
  static BEAM   = 2.6;
  static PIVOT  = 15;
  static CANOPY = 0.68;
  static OFFSET = 5;

  constructor({ stage, svg }, value) {
    super(svg, value, 3);
    const mid     = (MomentsBeamFigure.BARS - 1) / 2;
    this.half     = mid * MomentsBeamFigure.PITCH;
    this.heights  = PhysicsProfile.sampled(MomentsBeamFigure.BARS, MomentsBeamFigure.CANOPY).map((p) => MomentsBeamFigure.HMIN + (MomentsBeamFigure.HMAX - MomentsBeamFigure.HMIN) * p);
    this.us       = this.heights.map((_, i) => (i - mid) * MomentsBeamFigure.PITCH);
    const mass    = this.heights.reduce((sum, h) => sum + h, 0);
    this.centroid = this.heights.reduce((sum, h, i) => sum + h * this.us[i], 0) / mass;
    this.spread   = Math.sqrt(this.heights.reduce((sum, h, i) => sum + h * this.us[i] ** 2, 0) / mass - this.centroid ** 2);
    this._camera(this._extent(), 166);
    this._plinth(-this.half - 12, -13, this.half + 12, 16, 7, 4);
    this._buildMark();
    this._buildFulcrum();
    this._buildBeam();
    this._buildSpread();
    this.pivot = HL.spring(this.centroid, { k: 40, c: 11 });
    this.tilt  = HL.spring(0, { k: 50, c: 8 });
    this.drawn = "";
    this._start(stage, svg);
  }

  _extent() {
    const reach = this.half + 12;
    const rise  = (this.half + 6) * Math.sin(MomentsBeamFigure.RANGE[2]);
    const top   = MomentsBeamFigure.PIVOT + MomentsBeamFigure.BEAM + MomentsBeamFigure.HMAX + rise;
    return [[-reach, -13, -4], [reach, 16, -4], [reach, -13, -4], [-reach, 16, -4], [-this.half, 0, top], [this.half, 0, top], [this.half + 6, 0, MomentsBeamFigure.PIVOT - rise]];
  }

  _buildMark() {
    const a = this.centroid + MomentsBeamFigure.OFFSET;
    const v = MomentsBeamFigure.WIDE / 2 + 7;
    HL.mk("path", { d: HL.seg(this.P(a, -v, 0), this.P(a, v, 0)), class: "dash nf" }, this.g);
    HL.place(HL.flatDot(this.g, this.C, 1.1, "dot off"), this.P(a, v, 0));
  }

  _buildFulcrum() {
    this.fulcrum = HL.solid(this.g);
    this.fulcrum.sil.classList.add("hi");
  }

  _buildBeam() {
    const half     = this.half + 6;
    const wide     = MomentsBeamFigure.WIDE / 2 + 1.5;
    this.beam      = HL.solid(this.g);
    this.beamRing  = HL.rrect(-half, -wide, half, wide, 1.6, 4);
    this.beamInner = HL.rrect(-half + 0.9, -wide + 0.9, half - 0.9, wide - 0.9, 1, 4);
    this.bars      = this.heights.map((h, i) => {
      const u = this.us[i];
      const b = MomentsBeamFigure.BAR / 2;
      const w = MomentsBeamFigure.WIDE / 2;
      return { h, el: HL.solid(this.g), ring: HL.rrect(u - b, -w, u + b, w, 1.2, 4), inner: HL.rrect(u - b + 0.6, -w + 0.6, u + b - 0.6, w - 0.6, 0.6, 4) };
    });
  }

  _buildSpread() {
    this.span = HL.mk("path", { class: "dash nf" }, this.g);
    this.ends = [HL.flatDot(this.g, this.C, 1, "dot m"), HL.flatDot(this.g, this.C, 1, "dot m")];
  }

  _tick(dt) {
    let moving  = HL.stepS(this.pivot, dt);
    this.tilt.t = HL.clamp(((this.pivot.x - this.centroid) / this.spread) * 0.7, -1, 1) * this.amount;
    moving      = HL.stepS(this.tilt, dt) || moving;
    const key   = `${this.pivot.x}|${this.tilt.x}`;
    if (key !== this.drawn) {
      this.drawn = key;
      this._drawScale(this.pivot.x, this.tilt.x);
    }
    return moving;
  }

  _drawScale(f, theta) {
    const c    = Math.cos(theta);
    const s    = Math.sin(theta);
    const at   = (u, v, w) => this.P(f + (u - f) * c - w * s, v, MomentsBeamFigure.PIVOT + (u - f) * s + w * c);
    const keep = (q) => this.front({ nu: q.nu * c, nv: q.nv });
    const box  = (ring, inner, w0, w1) => ({ sil: HL.poly(HL.hull(ring.map((q) => at(q.u, q.v, w0)).concat(ring.map((q) => at(q.u, q.v, w1))))), crease: HL.open(HL.run(inner, keep).map((q) => at(q.u, q.v, w1))) });

    const foot = [-5.5, 5.5].flatMap((da) => [-4, 4].map((v) => this.P(f + da, v, 0)));
    const apex = [-4, 4].map((v) => this.P(f, v, MomentsBeamFigure.PIVOT));
    HL.put(this.fulcrum, { sil: HL.poly(HL.hull(foot.concat(apex))), crease: HL.seg(apex[1], this.P(f + 5.5, 4, 0)) });

    HL.put(this.beam, box(this.beamRing, this.beamInner, 0, MomentsBeamFigure.BEAM));
    for (const bar of this.bars) HL.put(bar.el, box(bar.ring, bar.inner, MomentsBeamFigure.BEAM, MomentsBeamFigure.BEAM + bar.h));

    const edge = MomentsBeamFigure.WIDE / 2 + 1.5;
    const lo   = at(this.centroid - this.spread, edge, MomentsBeamFigure.BEAM);
    const hi   = at(this.centroid + this.spread, edge, MomentsBeamFigure.BEAM);
    this.span.setAttribute("d", HL.seg(lo, hi));
    HL.place(this.ends[0], lo);
    HL.place(this.ends[1], hi);
  }

  _move(p) {
    const left   = this.P(-this.half, 0, MomentsBeamFigure.PIVOT)[0];
    const right  = this.P(this.half, 0, MomentsBeamFigure.PIVOT)[0];
    this.chosen  = true;
    this.pivot.t = HL.clamp(-this.half + ((p[0] - left) / (right - left)) * 2 * this.half, -this.half, this.half);
    this.loop.wake();
  }

  _leave() {
    this.chosen  = null;
    this.pivot.t = this.centroid;
    this.loop.wake();
  }

  _retarget() {
    if (this.chosen === null) this.pivot.t = this.centroid;
    this.loop.wake();
  }
}

class CoherencePhasorFigure extends HairlineFigureBase {
  static RANGE  = [3, 6, 10];
  static BINS   = 9;
  static BIN    = 5.6;
  static DISC   = 2;
  static RMAX   = 6.5;
  static RMIN   = 1.4;
  static SPOKE  = 4.5;
  static TURNS  = [0.3, 0.65, 1.1, 1.6];
  static CANOPY = [0.68, 0.76];
  static DIAL   = 8.5;
  static FIRST  = 26;
  static PITCH  = 18.5;
  static LANE   = 2;
  static REST   = 1;

  constructor({ stage, svg }, value) {
    super(svg, value, 3.1);
    this.power = PhysicsProfile.sampled(CoherencePhasorFigure.BINS, CoherencePhasorFigure.CANOPY[0]);
    this.top   = (CoherencePhasorFigure.BINS - 1) * CoherencePhasorFigure.BIN + CoherencePhasorFigure.DISC;
    this.end   = CoherencePhasorFigure.FIRST + (CoherencePhasorFigure.TURNS.length - 1) * CoherencePhasorFigure.PITCH + CoherencePhasorFigure.DIAL + 5;
    this._camera(this._extent(), 164);
    this._plinth(-14, -14, this.end, 14, 7, 4);
    this._buildColumn();
    this._buildDials();
    this.turns      = HL.tween(CoherencePhasorFigure.TURNS[CoherencePhasorFigure.REST]);
    this.drawnTurns = NaN;
    this._start(stage, svg);
  }

  _extent() {
    const lift  = CoherencePhasorFigure.RANGE[2] + 2;
    const reach = CoherencePhasorFigure.RMAX + CoherencePhasorFigure.SPOKE;
    return [[-14, -14, -4], [this.end, 14, -4], [this.end, -14, -4], [-14, 14, -4], [-reach, -reach, this.top + 1], [this.end - 5, CoherencePhasorFigure.LANE, lift]];
  }

  _buildColumn() {
    HL.mk("path", { d: HL.seg(this.P(0, 0, 0), this.P(0, 0, this.top + 5)), class: "dash nf" }, this.g);
    this.bins = this.power.map((p, i) => {
      const r  = CoherencePhasorFigure.RMIN + (CoherencePhasorFigure.RMAX - CoherencePhasorFigure.RMIN) * p;
      const z0 = i * CoherencePhasorFigure.BIN;
      HL.put(HL.solid(this.g), HL.prism(this.P, this.front, HL.circ(r, 40), HL.circ(Math.max(0.4, r - 0.8), 40), z0, z0 + CoherencePhasorFigure.DISC));
      return { t: i / (CoherencePhasorFigure.BINS - 1), r, z: z0 + CoherencePhasorFigure.DISC, spoke: HL.mk("path", { class: "nf" }, this.g), tip: HL.flatDot(this.g, this.C, 0.9, "dot m") };
    });
  }

  _coherence(power, turns) {
    let re = 0;
    let im = 0;
    let m0 = 0;
    power.forEach((p, i) => {
      const phase = 2 * Math.PI * turns * (i / (power.length - 1));
      re += p * Math.cos(phase);
      im += p * Math.sin(phase);
      m0 += p;
    });
    return [re / m0, im / m0];
  }

  _buildDials() {
    const reference = PhysicsProfile.sampled(CoherencePhasorFigure.BINS, CoherencePhasorFigure.CANOPY[1]);
    this.dials = CoherencePhasorFigure.TURNS.map((turns, k) => {
      const centre = [CoherencePhasorFigure.FIRST + k * CoherencePhasorFigure.PITCH, CoherencePhasorFigure.LANE];
      const group  = HL.mk("g", {}, this.g);
      const el     = HL.solid(group);
      const ghost  = HL.mk("path", { class: "dash nf" }, group);
      const needle = HL.mk("path", { class: "nf" }, group);
      const tip    = HL.flatDot(group, this.C, 1, "dot m");
      return { k, centre, el, ghost, needle, tip, gamma: this._coherence(this.power, turns), target: this._coherence(reference, turns), tw: HL.tween(k === CoherencePhasorFigure.REST ? this.amount : 0), drawn: NaN, restX: this.P(...centre, 0)[0] };
    });
    this.dials[CoherencePhasorFigure.REST].el.sil.classList.add("hi");
  }

  _tick(dt, now) {
    const moving = this._advance(this.dials, now);
    const turns  = HL.tval(this.turns, now);
    if (turns !== this.drawnTurns) {
      this.drawnTurns = turns;
      this._drawSpokes(turns);
    }
    return moving || !HL.tdone(this.turns, now);
  }

  _drawSpokes(turns) {
    for (const bin of this.bins) {
      const phase = 2 * Math.PI * turns * bin.t;
      const reach = bin.r + CoherencePhasorFigure.SPOKE;
      const tip   = this.P(reach * Math.cos(phase), reach * Math.sin(phase), bin.z);
      bin.spoke.setAttribute("d", HL.seg(this.P(0, 0, bin.z), tip));
      HL.place(bin.tip, tip);
    }
  }

  _draw(dial, lift) {
    const at       = this._shifted(dial.centre[0], dial.centre[1], 0);
    const R        = CoherencePhasorFigure.DIAL;
    const z        = lift + 1.6;
    const reach    = R - 1.3;
    const [gx, gy] = dial.gamma;
    const [tx, ty] = dial.target;
    HL.put(dial.el, HL.prism(at, this.front, HL.circ(R, 48), HL.circ(R - 1, 48), lift, z));
    dial.needle.setAttribute("d", HL.seg(at(0, 0, z), at(reach * gx, reach * gy, z)));
    dial.ghost.setAttribute("d", HL.seg(at(0, 0, z), at(reach * tx, reach * ty, z)));
    HL.place(dial.tip, at(reach * gx, reach * gy, z));
  }

  _move(p) {
    this._choose(HairlineFigureBase.nearest(this.dials.map((dial) => dial.restX), p[0]));
  }

  _retarget(now) {
    const pick = this.chosen === null ? CoherencePhasorFigure.REST : this.chosen;
    HL.tset(this.turns, CoherencePhasorFigure.TURNS[pick], now, 0);
    for (const dial of this.dials) {
      HL.tset(dial.tw, dial.k === pick ? this.amount : 0, now, 0);
      dial.el.sil.classList.toggle("hi", dial.k === pick);
    }
    this.loop.wake();
  }
}

class CaponCycleFigure extends HairlineFigureBase {
  static RANGE   = [2, 4, 7];
  static BINS    = 9;
  static BIN     = 5;
  static DISC    = 2;
  static RMAX    = 6.5;
  static RMIN    = 1.4;
  static STUB    = 1;
  static CANOPY  = [0.68, 0.72];
  static BLUR    = 1.1;
  static LEFT    = -40;
  static RIGHT   = 40;
  static N       = 4;
  static CELL    = 7;
  static FOOT    = 5.8;
  static DIAG    = 9;
  static FLOOR   = 1.6;
  static LOAD    = 1.6;
  static STAGGER = 40;
  static REST    = 6;

  constructor({ stage, svg }, value) {
    super(svg, value, 3.2);
    this.left  = this._onScreen(CaponCycleFigure.LEFT, 0);
    this.right = this._onScreen(CaponCycleFigure.RIGHT, 0);
    this.top   = (CaponCycleFigure.BINS - 1) * CaponCycleFigure.BIN + CaponCycleFigure.DISC;
    this._camera(this._extent(), 166);
    this._buildBoard();
    this._buildLeft();
    this._buildMatrix();
    this._buildRight();
    this.beam = HL.mk("path", { class: "dash nf" }, this.g);
    this.hit  = HL.flatDot(this.g, this.C, 1, "dot m");
    this.scan = HL.tween(CaponCycleFigure.REST);
    this._start(stage, svg);
    this._retarget(performance.now());
  }

  _radius(p) {
    return CaponCycleFigure.RMIN + (CaponCycleFigure.RMAX - CaponCycleFigure.RMIN) * p;
  }

  _extent() {
    const r0 = CaponCycleFigure.LEFT - 13;
    const r1 = CaponCycleFigure.RIGHT + 13 + CaponCycleFigure.RANGE[2];
    return [[...this._onScreen(r0, -14), -3], [...this._onScreen(r1, -14), -3], [...this._onScreen(r0, 14), -3], [...this._onScreen(r1, 14), -3], [...this.left, this.top], [...this.right, this.top]];
  }

  _buildBoard() {
    const r0 = CaponCycleFigure.LEFT - 13;
    const r1 = CaponCycleFigure.RIGHT + 13;
    HL.put(HL.solid(this.g), HL.prism(this.P, this.front, this._screenBox(r0, -14, r1, 14, 6), this._screenBox(r0 + 2.2, -11.8, r1 - 2.2, 11.8, 4), -3, 0));
    const span = (CaponCycleFigure.N * CaponCycleFigure.CELL) / 2;
    const lead = (r0, r1) => HL.seg(this.P(...this._onScreen(r0, 0), 0), this.P(...this._onScreen(r1, 0), 0));
    HL.mk("path", { d: lead(CaponCycleFigure.LEFT + 9, -span * Math.SQRT2 - 3) + lead(span * Math.SQRT2 + 3, CaponCycleFigure.RIGHT - 9), class: "dash nf" }, this.g);
  }

  _buildLeft() {
    const at    = this._shifted(this.left[0], this.left[1], 0);
    const power = PhysicsProfile.sampled(CaponCycleFigure.BINS, CaponCycleFigure.CANOPY[0]);
    power.forEach((p, i) => {
      const r  = this._radius(p);
      const z0 = i * CaponCycleFigure.BIN;
      HL.put(HL.solid(this.g), HL.prism(at, this.front, HL.circ(r, 40), HL.circ(Math.max(0.4, r - 0.8), 40), z0, z0 + CaponCycleFigure.DISC));
    });
  }

  _buildMatrix() {
    const n     = CaponCycleFigure.N;
    const span  = n * CaponCycleFigure.CELL;
    const inset = (CaponCycleFigure.CELL - CaponCycleFigure.FOOT) / 2;
    const cells = [];
    for (let r = 0; r < n; r++) for (let c = 0; c < n; c++) cells.push([r, c]);
    cells.sort((a, b) => (a[1] + n - 1 - a[0]) - (b[1] + n - 1 - b[0]));
    for (const [r, c] of cells) {
      const x0            = c * CaponCycleFigure.CELL + inset - span / 2;
      const y0            = (n - 1 - r) * CaponCycleFigure.CELL + inset - span / 2;
      const [ring, inner] = HL.rings(x0, y0, x0 + CaponCycleFigure.FOOT, y0 + CaponCycleFigure.FOOT, 1.2, 0.7);
      const h             = CaponCycleFigure.FLOOR + (CaponCycleFigure.DIAG - CaponCycleFigure.FLOOR) * 0.5 ** Math.abs(r - c) + (r === c ? CaponCycleFigure.LOAD : 0);
      HL.put(HL.solid(this.g), HL.prism(this.P, this.front, ring, inner, 0, h));
    }
    this.source = this.P(0, 0, CaponCycleFigure.DIAG + CaponCycleFigure.LOAD);
  }

  _buildRight() {
    const home      = this._shifted(this.right[0], this.right[1], 0);
    const estimate  = PhysicsProfile.blurred(PhysicsProfile.sampled(CaponCycleFigure.BINS, CaponCycleFigure.CANOPY[0]), CaponCycleFigure.BLUR);
    const reference = PhysicsProfile.blurred(PhysicsProfile.sampled(CaponCycleFigure.BINS, CaponCycleFigure.CANOPY[1]), CaponCycleFigure.BLUR);
    this.bins = estimate.map((p, i) => {
      const z0    = i * CaponCycleFigure.BIN;
      const group = HL.mk("g", {}, this.g);
      const ghost = HL.mk("path", { class: "dash nf" }, group);
      ghost.setAttribute("d", HL.poly(HL.ringAt(home, HL.circ(this._radius(reference[i]) + 0.6, 48), z0 + CaponCycleFigure.DISC)));
      const el    = HL.solid(group);
      return { i, z0, full: this._radius(p), el, size: HL.tween(CaponCycleFigure.STUB), slide: HL.tween(0), drawn: "", restY: home(0, 0, z0 + CaponCycleFigure.DISC / 2)[1] };
    });
  }

  _tick(dt, now) {
    let moving = !HL.tdone(this.scan, now);
    for (const bin of this.bins) {
      const r     = HL.tval(bin.size, now);
      const slide = HL.tval(bin.slide, now);
      if (!HL.tdone(bin.size, now) || !HL.tdone(bin.slide, now)) moving = true;
      const key = `${r}|${slide}`;
      if (key === bin.drawn) continue;
      bin.drawn = key;
      const [x, y] = this._onScreen(slide, 0);
      const at     = this._shifted(this.right[0] + x, this.right[1] + y, 0);
      HL.put(bin.el, HL.prism(at, this.front, HL.circ(r, 40), HL.circ(Math.max(0.4, r - 0.8), 40), bin.z0, bin.z0 + CaponCycleFigure.DISC));
    }
    this._drawBeam(HL.tval(this.scan, now), now);
    return moving;
  }

  _drawBeam(level, now) {
    const i      = HL.clamp(Math.round(level), 0, this.bins.length - 1);
    const bin    = this.bins[i];
    const z      = HL.lerp(this.bins[0].z0, this.bins[this.bins.length - 1].z0, level / (this.bins.length - 1)) + CaponCycleFigure.DISC / 2;
    const r      = HL.tval(bin.size, now);
    const slide  = HL.tval(bin.slide, now);
    const [x, y] = this._onScreen(slide - r, 0);
    const end    = this.P(this.right[0] + x, this.right[1] + y, z);
    this.beam.setAttribute("d", HL.seg(this.source, end));
    HL.place(this.hit, end);
  }

  _move(p) {
    this._choose(HairlineFigureBase.nearest(this.bins.map((bin) => bin.restY), p[1]));
  }

  _retarget(now) {
    const pick = this.chosen === null ? CaponCycleFigure.REST : this.chosen;
    HL.tset(this.scan, pick, now, 0);
    for (const bin of this.bins) {
      const delay = Math.abs(bin.i - pick) * CaponCycleFigure.STAGGER;
      HL.tset(bin.size, bin.i <= pick ? bin.full : CaponCycleFigure.STUB, now, delay);
      HL.tset(bin.slide, bin.i === pick ? this.amount : 0, now, 0);
      bin.el.sil.classList.toggle("hi", bin.i === pick);
    }
    this.loop.wake();
  }
}

class CvFoldsFigure extends HairlineFigureBase {
  static RANGE     = [6, 12, 18];
  static FOLDS     = 5;
  static RADIUS    = 44;
  static HEIGHT    = 15;
  static GAP       = 1.4;
  static PLATE     = 64;
  static SPIN      = -57;
  static REST      = 1;
  static REST_PULL = 0.45;
  static CENTRE    = 6;

  constructor({ stage, svg }, value) {
    super(svg, value, 2.1);
    this._camera(this._extent(), 166);
    this._buildPlate();
    this._buildFolds();
    this._start(stage, svg);
  }

  _extent() {
    const rim = HL.circ(CvFoldsFigure.PLATE, 32);
    return rim.map((q) => [q.u, q.v, -4]).concat(rim.map((q) => [q.u * 0.7, q.v * 0.7, CvFoldsFigure.HEIGHT]));
  }

  _buildPlate() {
    const ring  = HL.circ(CvFoldsFigure.PLATE, 96);
    const inner = HL.circ(CvFoldsFigure.PLATE - 2.2, 96);
    HL.put(HL.solid(this.g), HL.prism(this.P, this.front, ring, inner, -4, 0));
  }

  _buildFolds() {
    const half  = Math.PI / CvFoldsFigure.FOLDS;
    const inset = 1.2;
    const folds = [];
    for (let k = 0; k < CvFoldsFigure.FOLDS; k++) {
      const theta = HL.rad(CvFoldsFigure.SPIN + (360 * k) / CvFoldsFigure.FOLDS);
      const dir   = [Math.cos(theta), Math.sin(theta)];
      const ring  = HairlineGeometry.roundedSector(theta, half, CvFoldsFigure.RADIUS, 0, 2, 3, 18);
      const inner = HairlineGeometry.roundedSector(theta, half, CvFoldsFigure.RADIUS - inset, inset / Math.sin(half), 1.2, 2, 18);
      folds.push({ k, theta, dir, ring, inner, depth: this.P(dir[0], dir[1], 0)[1] });
    }
    folds.sort((a, b) => a.depth - b.depth);
    this.folds = folds.map((fold) => this._buildFold(fold));
  }

  _buildFold(fold) {
    const group = HL.mk("g", {}, this.g);
    const el    = HL.solid(group);
    const dots  = [];
    for (let j = 0; j <= fold.k; j++) {
      const phi = fold.theta + HL.rad((j - fold.k / 2) * 6.5);
      const at  = [(CvFoldsFigure.RADIUS - 9) * Math.cos(phi), (CvFoldsFigure.RADIUS - 9) * Math.sin(phi)];
      dots.push({ at, el: HL.flatDot(group, this.C, 1.15, "dot m") });
    }
    const lit = fold.k === CvFoldsFigure.REST;
    this._light(el, dots, lit);
    return { ...fold, el, dots, tw: HL.tween(lit ? this.amount * CvFoldsFigure.REST_PULL : 0), drawn: NaN };
  }

  _light(el, dots, lit) {
    el.sil.classList.toggle("hi", lit);
    for (const dot of dots) dot.el.setAttribute("class", lit ? "dot" : "dot m");
  }

  _tick(dt, now) {
    return this._advance(this.folds, now);
  }

  _draw(fold, out) {
    const shift = CvFoldsFigure.GAP + out;
    const moved = this._shifted(fold.dir[0] * shift, fold.dir[1] * shift, 0);
    HL.put(fold.el, HL.prism(moved, this.front, fold.ring, fold.inner, 0, CvFoldsFigure.HEIGHT));
    for (const dot of fold.dots) HL.place(dot.el, moved(dot.at[0], dot.at[1], CvFoldsFigure.HEIGHT));
  }

  _move(p) {
    const [x, y] = HL.unproj(this.C, p[0], p[1], CvFoldsFigure.HEIGHT);
    if (Math.hypot(x, y) < CvFoldsFigure.CENTRE) return;
    const step  = 360 / CvFoldsFigure.FOLDS;
    const angle = (((Math.atan2(y, x) * 180) / Math.PI - CvFoldsFigure.SPIN) % 360 + 360) % 360;
    this._choose(Math.round(angle / step) % CvFoldsFigure.FOLDS);
  }

  _retarget(now) {
    const held = this.chosen === null ? CvFoldsFigure.REST : this.chosen;
    const pull = this.chosen === null ? this.amount * CvFoldsFigure.REST_PULL : this.amount;
    for (const fold of this.folds) {
      HL.tset(fold.tw, fold.k === held ? pull : 0, now, 0);
      this._light(fold.el, fold.dots, fold.k === held);
    }
    this.loop.wake();
  }
}

class AblationTowerFigure extends HairlineFigureBase {
  static RANGE     = [8, 14, 22];
  static LEVELS    = 9;
  static WIDTH     = 8.6;
  static GAP       = 0.7;
  static HEIGHT    = 6.2;
  static GAP_Z     = 0.5;
  static REST      = 5;
  static REST_PULL = 0.45;

  constructor({ stage, svg }, value) {
    super(svg, value, 3.1);
    this.span = 3 * AblationTowerFigure.WIDTH + 2 * AblationTowerFigure.GAP;
    this._camera(this._extent(), 164);
    this._plinth(-8, -8, this.span + 8, this.span + 8, 7, 4);
    this._buildLevels();
    this._start(stage, svg);
  }

  _extent() {
    const span = this.span;
    const top  = AblationTowerFigure.LEVELS * (AblationTowerFigure.HEIGHT + AblationTowerFigure.GAP_Z);
    const far  = span + AblationTowerFigure.RANGE[2];
    return [[-8, -8, -4], [span + 8, span + 8, -4], [span + 8, -8, -4], [-8, span + 8, -4], [0, 0, top], [span, span, top], [far, span / 2, top * 0.6], [span / 2, far, top * 0.6]];
  }

  _buildLevels() {
    this.blocks = [];
    this.levels = [];
    for (let i = 0; i < AblationTowerFigure.LEVELS; i++) {
      const z0    = i * (AblationTowerFigure.HEIGHT + AblationTowerFigure.GAP_Z);
      const z1    = z0 + AblationTowerFigure.HEIGHT;
      const level = [0, 1, 2].map((b) => this._block(i, b, z0, z1));
      level.sort((a, b) => a.depth - b.depth);
      for (const block of level) {
        block.el = HL.solid(this.g);
        this.blocks.push(block);
      }
      const middle = level.find((block) => block.b === 1);
      middle.tw    = HL.tween(i === AblationTowerFigure.REST ? this.amount * AblationTowerFigure.REST_PULL : 0);
      middle.el.sil.classList.toggle("hi", i === AblationTowerFigure.REST);
      this.levels.push({ middle, y: this.P(this.span / 2, this.span / 2, (z0 + z1) / 2)[1] });
    }
  }

  _block(i, b, z0, z1) {
    const width   = AblationTowerFigure.WIDTH;
    const across  = b * (width + AblationTowerFigure.GAP);
    const jitter  = b === 1 ? 0 : 1.1 * Math.sin(i * 2.3 + b * 1.7);
    const alongX  = i % 2 === 0;
    const box     = alongX ? [jitter, across, this.span + jitter, across + width] : [across, jitter, across + width, this.span + jitter];
    const [ring, inner] = HL.rings(box[0], box[1], box[2], box[3], 1.6, 0.7);
    return { b, ring, inner, z0, z1, dir: alongX ? [1, 0] : [0, 1], depth: box[0] + box[1] + box[2] + box[3], tw: HL.tween(0), drawn: NaN };
  }

  _tick(dt, now) {
    return this._advance(this.blocks, now);
  }

  _draw(block, out) {
    HL.put(block.el, HL.prism(this._shifted(block.dir[0] * out, block.dir[1] * out, 0), this.front, block.ring, block.inner, block.z0, block.z1));
  }

  _move(p) {
    this._choose(HairlineFigureBase.nearest(this.levels.map((level) => level.y), p[1]));
  }

  _retarget(now) {
    const pulled = this.chosen === null ? AblationTowerFigure.REST : this.chosen;
    const out    = this.chosen === null ? this.amount * AblationTowerFigure.REST_PULL : this.amount;
    this.levels.forEach((level, i) => {
      HL.tset(level.middle.tw, i === pulled ? out : 0, now, 0);
      level.middle.el.sil.classList.toggle("hi", i === pulled);
    });
    this.loop.wake();
  }
}

class SliceLoafFigure extends HairlineFigureBase {
  static RANGE     = [8, 14, 22];
  static SLICES    = 11;
  static THICK     = 3.4;
  static GAP       = 1.1;
  static DEPTH     = 40;
  static REACH     = 1.8;
  static STAGGER   = 40;
  static REST      = 7;
  static REST_PULL = 0.45;

  constructor({ stage, svg }, value) {
    super(svg, value, 3.0);
    this.length = SliceLoafFigure.SLICES * (SliceLoafFigure.THICK + SliceLoafFigure.GAP) - SliceLoafFigure.GAP;
    this._camera(this._extent(), 168);
    this._plinth(-6, -6, this.length + 6, SliceLoafFigure.DEPTH + 6, 6, 4);
    this._buildSlices();
    this._start(stage, svg);
  }

  _height(k) {
    return 12 + 14 * Math.exp(-(((k - 3) / 2.2) ** 2)) + 10 * Math.exp(-(((k - 8) / 1.5) ** 2));
  }

  _extent() {
    const length = this.length;
    const depth  = SliceLoafFigure.DEPTH;
    const far    = depth + SliceLoafFigure.RANGE[2];
    return [[-6, -6, -4], [length + 6, depth + 6, -4], [length + 6, -6, -4], [-6, depth + 6, -4], [0, 0, 30], [length, 0, 30], [0, far, 30], [length, far, 25]];
  }

  _buildSlices() {
    this.slices = Array.from({ length: SliceLoafFigure.SLICES }, (_, k) => {
      const x0            = k * (SliceLoafFigure.THICK + SliceLoafFigure.GAP);
      const [ring, inner] = HL.rings(x0, 0, x0 + SliceLoafFigure.THICK, SliceLoafFigure.DEPTH, 1.2, 0.55);
      const el            = HL.solid(this.g);
      const lit           = k === SliceLoafFigure.REST;
      el.sil.classList.toggle("hi", lit);
      return { k, ring, inner, h: this._height(k), el, tw: HL.tween(lit ? this.amount * SliceLoafFigure.REST_PULL : 0), drawn: NaN, restX: this.P(x0 + SliceLoafFigure.THICK / 2, SliceLoafFigure.DEPTH / 2, 0)[0] };
    });
  }

  _tick(dt, now) {
    return this._advance(this.slices, now);
  }

  _draw(slice, out) {
    HL.put(slice.el, HL.prism(this._shifted(0, out, 0), this.front, slice.ring, slice.inner, 0, slice.h));
  }

  _move(p) {
    this._choose(HairlineFigureBase.nearest(this.slices.map((slice) => slice.restX), p[0]));
  }

  _retarget(now) {
    const anchor = this.chosen === null ? SliceLoafFigure.REST : this.chosen;
    for (const slice of this.slices) {
      const distance = Math.abs(slice.k - anchor);
      const reach    = Math.max(0, 1 - distance / SliceLoafFigure.REACH) ** 2;
      const target   = this.chosen === null ? (slice.k === SliceLoafFigure.REST ? this.amount * SliceLoafFigure.REST_PULL : 0) : this.amount * reach;
      HL.tset(slice.tw, target, now, distance * SliceLoafFigure.STAGGER);
      slice.el.sil.classList.toggle("hi", slice.k === anchor);
    }
    this.loop.wake();
  }
}

class NormalizationFigure extends HairlineFigureBase {
  static RANGE   = [1, 2.5, 5];
  static RAW     = [7, 11, 6, 19, 48, 13, 9, 28, 66, 12, 8, 16];
  static PITCH   = 7.6;
  static EDGE    = 7;
  static FOOT    = 5.4;
  static DEPTH   = 26;
  static PLATE_Y = 3;
  static PLATE_T = 2.2;
  static PLATE_H = 72;
  static BAR_Y   = 12;
  static STAGGER = 35;

  constructor({ stage, svg }, value) {
    super(svg, value, 2.35);
    this.length = 2 * NormalizationFigure.EDGE + (NormalizationFigure.RAW.length - 1) * NormalizationFigure.PITCH;
    this.norm   = NormalizationFigure.RAW.map((v) => 9 * Math.log1p(v / 6));
    this.peak   = NormalizationFigure.RAW.indexOf(Math.max(...NormalizationFigure.RAW));
    this._camera(this._extent(), 164);
    this._plinth(0, 0, this.length, NormalizationFigure.DEPTH, 6, 4);
    this._buildPlate();
    this._buildBars();
    this._start(stage, svg);
  }

  _extent() {
    const length = this.length;
    const top    = NormalizationFigure.PLATE_H;
    const depth  = NormalizationFigure.DEPTH;
    return [[0, 0, -4], [length, 0, -4], [0, depth, -4], [length, depth, -4], [0, NormalizationFigure.PLATE_Y, top], [length, NormalizationFigure.PLATE_Y, top]];
  }

  _buildPlate() {
    const y = NormalizationFigure.PLATE_Y;
    const t = NormalizationFigure.PLATE_T;
    HL.put(HL.solid(this.g), HairlineGeometry.backPlate(this.P, 2, this.length - 2, NormalizationFigure.PLATE_H, y, t));
    const sorted = [...this.norm].sort((a, b) => a - b);
    const band   = [sorted[Math.floor(sorted.length * 0.25)], sorted[Math.floor(sorted.length * 0.75)]];
    const at     = (x, z) => this.P(x, y + t, z);
    HL.mk("path", { class: "dash nf", d: band.map((z) => HL.seg(at(5, z), at(this.length - 5, z))).join("") }, this.g);
  }

  _buildBars() {
    const half = NormalizationFigure.FOOT / 2;
    const y0   = NormalizationFigure.BAR_Y;
    this.bars  = NormalizationFigure.RAW.map((raw, i) => {
      const x             = NormalizationFigure.EDGE + i * NormalizationFigure.PITCH;
      const [ring, inner] = HL.rings(x - half, y0, x + half, y0 + NormalizationFigure.FOOT, 1.4, 0.6);
      const el            = HL.solid(this.g);
      el.sil.classList.toggle("hi", i === this.peak);
      return { i, raw, norm: this.norm[i], ring, inner, el, tw: HL.tween(0), drawn: NaN, restX: this.P(x, y0 + half, 0)[0] };
    });
  }

  _tick(dt, now) {
    return this._advance(this.bars, now);
  }

  _draw(bar, blend) {
    HL.put(bar.el, HL.prism(this.P, this.front, bar.ring, bar.inner, 0, HL.lerp(bar.raw, bar.norm, blend)));
  }

  _move(p) {
    this._choose(HairlineFigureBase.nearest(this.bars.map((bar) => bar.restX), p[0]));
  }

  _retarget(now) {
    const anchor = this.chosen === null ? this.peak : this.chosen;
    for (const bar of this.bars) {
      const distance = Math.abs(bar.i - this.chosen);
      const blend    = this.chosen === null ? 0 : HL.clamp(1 - distance / (this.amount + 1), 0, 1);
      HL.tset(bar.tw, blend, now, this.chosen === null ? 0 : distance * NormalizationFigure.STAGGER);
      bar.el.sil.classList.toggle("hi", bar.i === anchor);
    }
    this.loop.wake();
  }
}

class GaussianSlotsFigure extends HairlineFigureBase {
  static RANGE     = [6, 12, 20];
  static AMPLITUDE = [26, 0, 15];
  static SIGMA     = [0.9, 1.4, 2.0];
  static FINS      = 7;
  static FIN_PITCH = 2.6;
  static FIN_WIDTH = 1.5;
  static TRAY      = 21;
  static TRAY_GAP  = 5;
  static FLOOR     = 2.2;
  static STAGGER   = 45;
  static REST      = 1;

  constructor({ stage, svg }, value) {
    super(svg, value, 3.6);
    this.length = 8 + 3 * GaussianSlotsFigure.TRAY + 2 * GaussianSlotsFigure.TRAY_GAP;
    this._camera(this._extent(), 170);
    this._plinth(0, 0, this.length, 20, 6, 4);
    this._buildSlots();
    this._start(stage, svg);
  }

  _extent() {
    const length = this.length;
    const top    = GaussianSlotsFigure.FLOOR + Math.max(...GaussianSlotsFigure.AMPLITUDE) + GaussianSlotsFigure.RANGE[2] + 1;
    return [[0, 0, -4], [length, 0, -4], [0, 20, -4], [length, 20, -4], [length * 0.25, 10, top], [length * 0.75, 10, 30]];
  }

  _buildSlots() {
    this.fins  = [];
    this.slots = GaussianSlotsFigure.AMPLITUDE.map((amplitude, k) => {
      const x0            = 4 + k * (GaussianSlotsFigure.TRAY + GaussianSlotsFigure.TRAY_GAP);
      const [ring, inner] = HL.rings(x0, 4, x0 + GaussianSlotsFigure.TRAY, 16, 2.4, 1);
      const tray          = HL.solid(this.g);
      HL.put(tray, HL.prism(this.P, this.front, ring, inner, 0, GaussianSlotsFigure.FLOOR));
      tray.sil.classList.toggle("hi", k === GaussianSlotsFigure.REST);
      const centre = x0 + GaussianSlotsFigure.TRAY / 2;
      for (let j = 0; j < GaussianSlotsFigure.FINS; j++) this.fins.push(this._fin(k, j, centre, amplitude));
      return { k, tray, restX: this.P(centre, 10, 0)[0] };
    });
  }

  _fin(k, j, centre, amplitude) {
    const half          = GaussianSlotsFigure.FIN_WIDTH / 2;
    const x             = centre + (j - (GaussianSlotsFigure.FINS - 1) / 2) * GaussianSlotsFigure.FIN_PITCH;
    const [ring, inner] = HL.rings(x - half, 6.5, x + half, 13.5, 0.7, 0.3);
    const offset        = j - (GaussianSlotsFigure.FINS - 1) / 2;
    const shape         = Math.exp(-((offset / GaussianSlotsFigure.SIGMA[k]) ** 2));
    return { k, offset, shape, ring, inner, el: HL.solid(this.g), tw: HL.tween(amplitude * shape), drawn: NaN };
  }

  _tick(dt, now) {
    return this._advance(this.fins, now);
  }

  _draw(fin, height) {
    HL.put(fin.el, HL.prism(this.P, this.front, fin.ring, fin.inner, 0, GaussianSlotsFigure.FLOOR + 0.8 + height));
  }

  _move(p) {
    this._choose(HairlineFigureBase.nearest(this.slots.map((slot) => slot.restX), p[0]));
  }

  _retarget(now) {
    const lit = this.chosen === null ? GaussianSlotsFigure.REST : this.chosen;
    for (const fin of this.fins) {
      const amplitude = GaussianSlotsFigure.AMPLITUDE[fin.k] + (fin.k === this.chosen ? this.amount : 0);
      HL.tset(fin.tw, amplitude * fin.shape, now, Math.abs(fin.offset) * GaussianSlotsFigure.STAGGER);
    }
    for (const slot of this.slots) slot.tray.sil.classList.toggle("hi", slot.k === lit);
    this.loop.wake();
  }
}

class FlightTracksFigure extends HairlineFigureBase {
  static RANGE   = [40, 100, 220];
  static TRACKS  = 6;
  static LENGTH  = 96;
  static LOW     = 34;
  static STEP    = 7.5;
  static OFFSETS = [0, 1.6, -1.2, 0.8, -0.6, 1.2];
  static SCENE   = [14, 44];
  static REST    = 1;
  static REST_X  = 0.35;

  constructor({ stage, svg }, value) {
    super(svg, value, 2.45);
    this._camera(this._extent(), 160);
    this._buildScene();
    this._buildTracks();
    this._buildCraft();
    this._start(stage, svg);
  }

  _extent() {
    const length = FlightTracksFigure.LENGTH;
    const top    = FlightTracksFigure.LOW + (FlightTracksFigure.TRACKS - 1) * FlightTracksFigure.STEP + 3;
    const [y0, y1] = FlightTracksFigure.SCENE;
    return [[0, -4, top], [length, -4, top], [0, y1, -3], [length, y1, -3], [0, y0, -3], [length, -4, FlightTracksFigure.LOW - 3]];
  }

  _buildScene() {
    const [y0, y1]      = FlightTracksFigure.SCENE;
    const [ring, inner] = HL.rings(6, y0, FlightTracksFigure.LENGTH - 6, y1, 6, 2);
    HL.put(HL.solid(this.g), HL.prism(this.P, this.front, ring, inner, -3, 0));
    this.foot = HL.flatDot(this.g, this.C, 1.6, "dot m");
  }

  _buildTracks() {
    const tracks = Array.from({ length: FlightTracksFigure.TRACKS }, (_, k) => {
      const y             = FlightTracksFigure.OFFSETS[k];
      const z             = FlightTracksFigure.LOW + k * FlightTracksFigure.STEP;
      const [ring, inner] = HL.rings(0, y - 1.6, FlightTracksFigure.LENGTH, y + 1.6, 1.4, 0.6);
      return { k, y, z, ring, inner, depth: 0.612 * y + 0.5 * z };
    });
    for (const track of [...tracks].sort((a, b) => a.depth - b.depth)) {
      track.group = HL.mk("g", {}, this.g);
      track.el    = HL.solid(track.group);
      HL.put(track.el, HL.prism(this.P, this.front, track.ring, track.inner, track.z - 1.6, track.z + 1.6));
    }
    this.tracks = tracks;
  }

  _buildCraft() {
    const rest       = this.tracks[FlightTracksFigure.REST];
    this.craftGroup  = HL.mk("g", {}, this.g);
    this.sight       = HL.mk("path", { class: "dash nf" }, this.craftGroup);
    this.craft       = HL.solid(this.craftGroup);
    this.craftRings  = HL.rings(-5.5, -3, 5.5, 3, 2.4, 1);
    this.along       = HL.spring(FlightTracksFigure.LENGTH * FlightTracksFigure.REST_X, { k: this.amount });
    this.lane        = { y: HL.tween(rest.y), z: HL.tween(rest.z) };
    this.drawnCraft  = null;
    rest.group.after(this.craftGroup);
    rest.el.sil.classList.add("hi");
  }

  _tick(dt, now) {
    const moving = HL.stepS(this.along, dt);
    const y      = HL.tval(this.lane.y, now);
    const z      = HL.tval(this.lane.z, now);
    const key    = `${this.along.x}|${y}|${z}`;
    if (key !== this.drawnCraft) {
      this.drawnCraft = key;
      this._drawCraft(this.along.x, y, z);
    }
    return moving || !HL.tdone(this.lane.y, now) || !HL.tdone(this.lane.z, now);
  }

  _drawCraft(x, y, z) {
    const [ring, inner] = this.craftRings;
    const ground        = (FlightTracksFigure.SCENE[0] + FlightTracksFigure.SCENE[1]) / 2;
    HL.put(this.craft, HL.prism(this._shifted(x, y, 0), this.front, ring, inner, z - 2.4, z + 2.4));
    this.sight.setAttribute("d", HL.seg(this.P(x, y, z - 2.4), this.P(x, ground, 0)));
    HL.place(this.foot, this.P(x, ground, 0));
  }

  _move(p) {
    const ys    = this.tracks.map((track) => this.P(FlightTracksFigure.LENGTH / 2, track.y, track.z)[1]);
    const track = this.tracks[HairlineFigureBase.nearest(ys, p[1])];
    const a     = this.P(0, track.y, track.z);
    const b     = this.P(FlightTracksFigure.LENGTH, track.y, track.z);
    const t     = ((p[0] - a[0]) * (b[0] - a[0]) + (p[1] - a[1]) * (b[1] - a[1])) / ((b[0] - a[0]) ** 2 + (b[1] - a[1]) ** 2);
    this.along.t = HL.clamp(t, 0.06, 0.94) * FlightTracksFigure.LENGTH;
    this._choose(track.k);
    this.loop.wake();
  }

  _retarget(now) {
    const track  = this.tracks[this.chosen === null ? FlightTracksFigure.REST : this.chosen];
    this.along.k = this.amount;
    if (this.chosen === null) this.along.t = FlightTracksFigure.LENGTH * FlightTracksFigure.REST_X;
    HL.tset(this.lane.y, track.y, now, 0);
    HL.tset(this.lane.z, track.z, now, 0);
    track.group.after(this.craftGroup);
    for (const other of this.tracks) other.el.sil.classList.toggle("hi", other === track);
    this.loop.wake();
  }
}

class ExpressionTreeFigure extends HairlineFigureBase {
  static RANGE    = [6, 12, 20];
  static CHILDREN = { 0: [1, 2], 1: [3, 4], 2: [5, 6], 6: [7, 8] };
  static LEAF_GAP = 13;
  static ROW      = 16;
  static STAGGER  = 60;
  static REST     = 6;
  static REST_LIFT = 0.45;

  constructor({ stage, svg }, value) {
    super(svg, value, 3.4);
    this.nodes = this._layout();
    this._camera(this._extent(), 168);
    this._plinth(-10, -10, 62, 58, 7, 4);
    this._buildEdges();
    this._buildNodes();
    this._start(stage, svg);
  }

  _layout() {
    const nodes = Array.from({ length: 9 }, (_, i) => ({ i, children: ExpressionTreeFigure.CHILDREN[i] || [], depth: 0, x: 0 }));
    let leaf    = 0;
    const place = (node, depth) => {
      node.depth = depth;
      for (const child of node.children) place(nodes[child], depth + 1);
      node.x = node.children.length ? node.children.reduce((sum, child) => sum + nodes[child].x, 0) / node.children.length : leaf++ * ExpressionTreeFigure.LEAF_GAP;
      node.y = depth * ExpressionTreeFigure.ROW;
    };
    place(nodes[0], 0);
    return nodes;
  }

  _extent() {
    const top = 7 + ExpressionTreeFigure.RANGE[2];
    return [[-10, -10, -4], [62, 58, -4], [62, -10, -4], [-10, 58, -4], [0, 0, top], [52, 48, top]];
  }

  _buildEdges() {
    this.edges      = HL.mk("path", { class: "nf" }, this.g);
    this.edgesDirty = false;
  }

  _buildNodes() {
    const order = [...this.nodes].sort((a, b) => a.x + a.y - (b.x + b.y));
    const rest  = this._subtree(ExpressionTreeFigure.REST);
    for (const node of order) {
      const leaf    = node.children.length === 0;
      const circle  = HL.circ(3.6, 40).map((q) => ({ ...q, u: q.u + node.x, v: q.v + node.y }));
      const inner   = HL.circ(2.8, 40).map((q) => ({ ...q, u: q.u + node.x, v: q.v + node.y }));
      const rings   = leaf ? [circle, inner] : HL.rings(node.x - 4, node.y - 4, node.x + 4, node.y + 4, 1.8, 0.8);
      const group   = HL.mk("g", {}, this.g);
      node.ring     = rings[0];
      node.inner    = rings[1];
      node.height   = leaf ? 3 : 7;
      node.el       = HL.solid(group);
      node.dot      = leaf ? null : HL.flatDot(group, this.C, 1.1, "dot m");
      node.tw       = HL.tween(rest.has(node.i) ? this.amount * ExpressionTreeFigure.REST_LIFT : 0);
      node.drawn    = NaN;
      node.screen   = this.P(node.x, node.y, node.height / 2);
      node.el.sil.classList.toggle("hi", rest.has(node.i));
    }
  }

  _subtree(root) {
    const found = new Set([root]);
    for (const child of this.nodes[root].children) for (const i of this._subtree(child)) found.add(i);
    return found;
  }

  _tick(dt, now) {
    const moving = this._advance(this.nodes, now);
    if (this.edgesDirty) this._drawEdges();
    return moving;
  }

  _draw(node, lift) {
    HL.put(node.el, HL.prism(this.P, this.front, node.ring, node.inner, lift, lift + node.height));
    if (node.dot) HL.place(node.dot, this.P(node.x, node.y, lift + node.height));
    this.edgesDirty = true;
  }

  _drawEdges() {
    const middle = (node) => this.P(node.x, node.y, node.drawn + node.height / 2);
    const lines  = [];
    for (const node of this.nodes) for (const child of node.children) lines.push(HL.seg(middle(node), middle(this.nodes[child])));
    this.edges.setAttribute("d", lines.join(""));
    this.edgesDirty = false;
  }

  _move(p) {
    const distance = this.nodes.map((node) => Math.hypot(node.screen[0] - p[0], node.screen[1] - p[1]));
    this._choose(HairlineFigureBase.nearest(distance, 0));
  }

  _retarget(now) {
    const root  = this.chosen === null ? ExpressionTreeFigure.REST : this.chosen;
    const tree  = this._subtree(root);
    const lift  = this.chosen === null ? this.amount * ExpressionTreeFigure.REST_LIFT : this.amount;
    const depth = this.nodes[root].depth;
    for (const node of this.nodes) {
      HL.tset(node.tw, tree.has(node.i) ? lift : 0, now, tree.has(node.i) ? (node.depth - depth) * ExpressionTreeFigure.STAGGER : 0);
      node.el.sil.classList.toggle("hi", tree.has(node.i));
    }
    this.loop.wake();
  }
}

class GpuShelfFigure extends HairlineFigureBase {
  static RANGE     = [8, 14, 22];
  static THICK     = 4;
  static GAP       = 3.2;
  static DEPTH     = 34;
  static HEIGHT    = 26;
  static FAN       = 6;
  static BLADES    = 3;
  static DEVICES   = [["busy", 70], ["busy", 55], ["idle", 0], ["busy", 85], ["idle", 0], ["idle", 0]];
  static LIGHT     = { mine: "dot", others: "dot m", stale: "dot m", busy: "dot m", idle: "dot off" };
  static SPIN      = [0.5, 10];
  static REACH     = 1.6;
  static STAGGER   = 45;
  static REST      = 2;
  static REST_LIFT = 0.45;

  constructor({ stage, svg }, value) {
    super(svg, value, 3.3);
    this.devices = GpuShelfFigure.DEVICES.map(([holder, util]) => ({ holder, util }));
    this.rest    = GpuShelfFigure.REST;
    this._layout();
    this._start(stage, svg);
  }

  _scale(count) {
    const span = count * (GpuShelfFigure.THICK + GpuShelfFigure.GAP) - GpuShelfFigure.GAP + 12;
    return 3.3 * Math.min(1.4, (96 / (span + 44)) ** 0.8);
  }

  _layout() {
    this.g.replaceChildren();
    this.C      = HL.Cam(45, 0.5, this._scale(this.devices.length));
    this.length = this.devices.length * (GpuShelfFigure.THICK + GpuShelfFigure.GAP) - GpuShelfFigure.GAP;
    this._camera(this._extent(), 166);
    this._plinth(-6, -5, this.length + 6, GpuShelfFigure.DEPTH + 5, 5, 4);
    this._buildCards();
  }

  _extent() {
    const length = this.length;
    const top    = GpuShelfFigure.HEIGHT + GpuShelfFigure.RANGE[2];
    return [[-6, -5, -4], [length + 6, GpuShelfFigure.DEPTH + 5, -4], [length + 6, -5, -4], [-6, GpuShelfFigure.DEPTH + 5, -4], [0, 0, top], [length, GpuShelfFigure.DEPTH, top]];
  }

  _buildCards() {
    this.cards = this.devices.map((device, k) => {
      const x0            = k * (GpuShelfFigure.THICK + GpuShelfFigure.GAP);
      const [ring, inner] = HL.rings(x0, 0, x0 + GpuShelfFigure.THICK, GpuShelfFigure.DEPTH, 1.3, 0.6);
      const group         = HL.mk("g", {}, this.g);
      const el            = HL.solid(group);
      const fans          = HL.mk("path", { class: "nf lo" }, group);
      const led           = HL.flatDot(group, this.C, 0.9, GpuShelfFigure.LIGHT[device.holder]);
      const lit           = k === this.rest;
      el.sil.classList.toggle("hi", lit);
      return { k, x0, ring, inner, el, fans, led, phase: k * 0.7, spin: HL.spring(this._spin(device.util), { k: 6, c: 5, eps: 0.01 }), tw: HL.tween(lit ? this.amount * GpuShelfFigure.REST_LIFT : 0), drawn: NaN, restX: this.P(x0 + GpuShelfFigure.THICK / 2, GpuShelfFigure.DEPTH / 2, 0)[0] };
    });
  }

  _spin(util) {
    const [idle, full] = GpuShelfFigure.SPIN;
    return idle + (full - idle) * HL.clamp((util || 0) / 100, 0, 1);
  }

  _tick(dt, now) {
    this._advance(this.cards, now);
    for (const card of this.cards) {
      HL.stepS(card.spin, dt);
      card.phase = (card.phase + card.spin.x * dt) % (Math.PI * 2);
      this._drawFans(card, Number.isFinite(card.drawn) ? card.drawn : 0);
    }
    return true;
  }

  _draw(card, lift) {
    HL.put(card.el, HL.prism(this.P, this.front, card.ring, card.inner, lift, lift + GpuShelfFigure.HEIGHT));
    HL.place(card.led, this.P(card.x0 + GpuShelfFigure.THICK / 2, GpuShelfFigure.DEPTH - 3, lift + GpuShelfFigure.HEIGHT));
  }

  _drawFans(card, lift) {
    const face = card.x0 + GpuShelfFigure.THICK;
    const cz   = lift + GpuShelfFigure.HEIGHT * 0.55;
    const r    = GpuShelfFigure.FAN;
    const at   = (cy, a, radius) => this.P(face, cy + radius * Math.cos(a), cz + radius * Math.sin(a));
    let d      = "";
    for (const share of [0.3, 0.7]) {
      const cy = GpuShelfFigure.DEPTH * share;
      d       += HairlineGeometry.faceCircle(this.P, face, cy, cz, r);
      for (let j = 0; j < GpuShelfFigure.BLADES; j++) {
        const a = card.phase + (j * Math.PI * 2) / GpuShelfFigure.BLADES;
        d      += HL.seg(at(cy, a, 1.2), at(cy, a + 0.5, r * 0.82));
      }
    }
    card.fans.setAttribute("d", d);
  }

  _move(p) {
    this._choose(HairlineFigureBase.nearest(this.cards.map((card) => card.restX), p[0]));
  }

  _restCard() {
    const rank = (device) => (device.holder === "mine" ? 1000 : device.holder === "idle" ? 0 : 500) + (device.util || 0);
    let best = 0;
    this.devices.forEach((device, k) => { if (rank(device) > rank(this.devices[best])) best = k; });
    return best;
  }

  setState(state) {
    const devices = (state && state.devices) || [];
    if (!devices.length) throw new Error("gpus figure: state.devices must list at least one device");
    const recount = devices.length !== this.devices.length;
    this.devices  = devices.map((device) => ({ holder: GpuShelfFigure.LIGHT[device.holder] ? device.holder : "idle", util: device.util || 0 }));
    this.rest     = this._restCard();
    if (recount) {
      this.chosen = null;
      this._layout();
    }
    this.cards.forEach((card, k) => {
      card.led.setAttribute("class", GpuShelfFigure.LIGHT[this.devices[k].holder]);
      card.spin.t = this._spin(this.devices[k].util);
    });
    this._retarget(performance.now());
  }

  _retarget(now) {
    const anchor = this.chosen === null ? this.rest : this.chosen;
    const amount = this.cards.length === 1 ? this.amount * GpuShelfFigure.REST_LIFT : this.amount;
    for (const card of this.cards) {
      const distance = Math.abs(card.k - anchor);
      const reach    = Math.max(0, 1 - distance / GpuShelfFigure.REACH) ** 2;
      const target   = this.chosen === null ? (card.k === this.rest ? amount * GpuShelfFigure.REST_LIFT : 0) : amount * reach;
      HL.tset(card.tw, target, now, distance * GpuShelfFigure.STAGGER);
      card.el.sil.classList.toggle("hi", card.k === anchor);
    }
    this.loop.wake();
  }
}

class GpuGuardFigure extends HairlineFigureBase {
  static RANGE     = [6, 11, 18];
  static CARDS     = 4;
  static THICK     = 4;
  static GAP       = 3.4;
  static DEPTH     = 26;
  static HEIGHT    = 21;
  static TRAY      = [5, 3.5, 2];
  static APRON     = 22;
  static BARRIER   = 8;
  static POST      = [3.6, 9];
  static ARM       = 2;
  static PIVOT     = 7;
  static PUCK      = [3.4, 5.4];
  static OPEN      = 1.3;
  static REST_LIFT = 0.4;
  static REACH     = 1.6;
  static STAGGER   = 45;
  static PATROL_MS = 1500;
  static ENTER_MS  = 2600;

  constructor({ stage, svg }, value) {
    super(svg, value, 2.6);
    this.count   = GpuGuardFigure.CARDS;
    this.invaded = null;
    this.target  = null;
    this.dead    = false;
    this._layout();
    this._start(stage, svg);
    this._retarget(performance.now());
  }

  _layout() {
    const [mx, my, tz] = GpuGuardFigure.TRAY;
    this.g.replaceChildren();
    this.len   = this.count * GpuGuardFigure.THICK + (this.count - 1) * GpuGuardFigure.GAP;
    this.gx    = this.len / 2;
    this.trayY = GpuGuardFigure.DEPTH + my;
    this.yb    = this.trayY + GpuGuardFigure.BARRIER;
    this.far   = this.trayY + GpuGuardFigure.APRON;
    this.postX = this.len + mx + GpuGuardFigure.POST[0] / 2 + 1.5;
    this.reach = this.postX - GpuGuardFigure.POST[0] / 2 + mx + 1;
    this.C     = HL.Cam(45, 0.5, 3.3 * Math.min(1.2, (40 / (this.len + 2 * mx)) ** 0.6));
    this._camera(this._extent(), 164);
    this.face  = HL.facing(this.C);
    this._plinth(-mx - 4, -my - 4, this.postX + GpuGuardFigure.POST[0] + 4, this.far + 3, 6, 4);
    HL.mk("path", { d: HL.seg(this.P(-mx, this.yb, 0), this.P(this.postX, this.yb, 0)), class: "dash nf" }, this.g);

    this.back  = HL.mk("g", {}, this.g);
    this.inner = HL.mk("g", {}, this.g);
    this.fore  = HL.mk("g", {}, this.g);
    this.outer = HL.mk("g", {}, this.g);
    const [ring, inner] = HL.rings(-mx, -my, this.len + mx, this.trayY, 3, 1.4);
    HL.put(HL.solid(this.back), HL.prism(this.P, this.face, ring, inner, 0, tz));
    this._buildCards();
    this._buildBarrier();
    this._buildPuck();

    this.swing     = HL.spring(0, { k: 46, c: 6.5, eps: 0.002 });
    this.armDrawn  = NaN;
    this.walk      = HL.tween(0, GpuGuardFigure.PATROL_MS);
    this.walkDrawn = NaN;
    this._route();
  }

  _extent() {
    const [mx, my] = GpuGuardFigure.TRAY;
    const top      = Math.max(GpuGuardFigure.HEIGHT + GpuGuardFigure.RANGE[2], GpuGuardFigure.PIVOT + this.reach * Math.sin(GpuGuardFigure.OPEN));
    return [[-mx - 4, -my - 4, -4], [this.postX + GpuGuardFigure.POST[0] + 4, this.far + 3, -4], [this.postX + GpuGuardFigure.POST[0] + 4, -my - 4, -4], [-mx - 4, this.far + 3, -4], [0, 0, top], [this.len, GpuGuardFigure.DEPTH, top], [this.postX, this.yb, top]];
  }

  _buildCards() {
    const tz = GpuGuardFigure.TRAY[2];
    this.cards = Array.from({ length: this.count }, (_, k) => {
      const x0            = k * (GpuGuardFigure.THICK + GpuGuardFigure.GAP);
      const [ring, inner] = HL.rings(x0, 0, x0 + GpuGuardFigure.THICK, GpuGuardFigure.DEPTH, 1.3, 0.6);
      const group         = HL.mk("g", {}, this.back);
      const el            = HL.solid(group);
      const fans          = HL.mk("path", { class: "nf lo" }, group);
      const led           = HL.flatDot(group, this.C, 1, "dot m");
      return { k, x0, z0: tz, ring, inner, el, fans, led, tw: HL.tween(0), drawn: NaN, restX: this.P(x0 + GpuGuardFigure.THICK / 2, GpuGuardFigure.DEPTH / 2, 0)[0] };
    });
  }

  _buildBarrier() {
    const side          = GpuGuardFigure.POST[0] / 2;
    const [ring, inner] = HL.rings(this.postX - side, this.yb - side, this.postX + side, this.yb + side, 1, 0.5);
    HL.put(HL.solid(this.fore), HL.prism(this.P, this.face, ring, inner, 0, GpuGuardFigure.POST[1]));
    this.arm     = HL.solid(this.fore);
    this.armTip  = HL.flatDot(this.fore, this.C, 1, "dot m");
    this.armRing = HL.rrect(-GpuGuardFigure.ARM / 2, -GpuGuardFigure.ARM / 2, GpuGuardFigure.ARM / 2, GpuGuardFigure.ARM / 2, 0.6, 3);
  }

  _buildPuck() {
    this.puck    = HL.mk("g", {}, this.outer);
    this.puckEl  = HL.solid(this.puck);
    this.puckDot = HL.flatDot(this.puck, this.C, 1.1, "dot off");
  }

  _armAt(theta) {
    const c  = Math.cos(theta);
    const s  = Math.sin(theta);
    const px = this.postX - GpuGuardFigure.POST[0] / 2;
    return (u, v, z) => this.P(px - z * c - v * s, this.yb + u, GpuGuardFigure.PIVOT + z * s + v * c);
  }

  _drawArm(theta) {
    const at = this._armAt(theta);
    HL.put(this.arm, HL.prism(at, this.face, this.armRing, null, 0, this.reach));
    HL.place(this.armTip, at(0, GpuGuardFigure.ARM / 2, this.reach - 1.4));
  }

  _route() {
    const r     = GpuGuardFigure.PUCK[0];
    const start = this.far - r - 1.5;
    const touch = this.yb + r + 1.1;
    const dock  = this.trayY + r + 1.2;
    const card  = this.target === null ? this.gx : this.cards[this.target].x0 + GpuGuardFigure.THICK / 2;
    this.points = [[this.gx, start], [this.gx, touch], [this.gx, this.yb - r - 1], [card, dock]];

    const legs  = this.points.slice(1).map((q, i) => Math.hypot(q[0] - this.points[i][0], q[1] - this.points[i][1]));
    const total = legs.reduce((a, b) => a + b, 0);
    this.cum    = [0];
    for (const leg of legs) this.cum.push(this.cum[this.cum.length - 1] + leg / total);
    this.touch  = this.cum[1];
  }

  _along(s) {
    let i = 1;
    while (i < this.cum.length - 1 && s > this.cum[i]) i++;
    const span = this.cum[i] - this.cum[i - 1] || 1;
    const f    = HL.clamp((s - this.cum[i - 1]) / span, 0, 1);
    const a    = this.points[i - 1];
    const b    = this.points[i];
    return [HL.lerp(a[0], b[0], f), HL.lerp(a[1], b[1], f)];
  }

  _tick(dt, now) {
    this._advance(this.cards, now);
    this._patrol(now);

    HL.stepS(this.swing, dt);
    if (this.swing.x !== this.armDrawn) {
      this.armDrawn = this.swing.x;
      this._drawArm(Math.max(0, this.swing.x));
    }

    const s = HL.tval(this.walk, now);
    if (s !== this.walkDrawn) {
      this.walkDrawn = s;
      this._drawPuck(s);
    }
    return true;
  }

  _patrol(now) {
    if (this.invaded !== null || !HL.tdone(this.walk, now)) return;
    this.walk.dur = GpuGuardFigure.PATROL_MS;
    if (HL.tval(this.walk, now) > 0) {
      this.swing.v += 1.5;
      HL.tset(this.walk, 0, now, 260);
    } else {
      HL.tset(this.walk, this.touch, now, 700);
    }
  }

  _drawPuck(s) {
    const [x, y] = this._along(s);
    const [r, h] = GpuGuardFigure.PUCK;
    const inside = y < this.yb;
    const [ring, inner] = [HL.circ(r, 40), HL.circ(r - 1, 40)].map((c) => c.map((q) => ({ ...q, u: q.u + x, v: q.v + y })));
    const home   = inside ? this.inner : this.outer;
    if (this.puck.parentNode !== home) home.appendChild(this.puck);

    HL.put(this.puckEl, HL.prism(this.P, this.face, ring, inner, 0, h));
    HL.place(this.puckDot, this.P(x, y, h));

    const arrived = this.invaded !== null && s > this.cum[this.cum.length - 2];
    this.puckEl.sil.classList.toggle("hi", arrived);
    this.puckDot.setAttribute("class", arrived ? "dot" : inside ? "dot m" : "dot off");
  }

  _draw(card, lift) {
    const z0   = card.z0 + lift;
    const face = card.x0 + GpuGuardFigure.THICK;
    const fanZ = z0 + GpuGuardFigure.HEIGHT * 0.52;
    HL.put(card.el, HL.prism(this.P, this.face, card.ring, card.inner, z0, z0 + GpuGuardFigure.HEIGHT));
    card.fans.setAttribute("d", [0.3, 0.7].map((at) => HairlineGeometry.faceCircle(this.P, face, GpuGuardFigure.DEPTH * at, fanZ, 5.2)).join(""));
    HL.place(card.led, this.P(card.x0 + GpuGuardFigure.THICK / 2, GpuGuardFigure.DEPTH - 3, z0 + GpuGuardFigure.HEIGHT));
  }

  _move(p) {
    this._choose(HairlineFigureBase.nearest(this.cards.map((card) => card.restX), p[0]));
  }

  setState(state) {
    const count   = Math.max(1, Math.round(state.gpus));
    const invaded = state.invaded === null ? null : HL.clamp(Math.round(state.invaded), 0, count - 1);
    const now     = performance.now();
    if (!Number.isFinite(count)) throw new Error("guard figure: state.gpus must be a number");

    if (count !== this.count) {
      this.count   = count;
      this.chosen  = null;
      this.invaded = null;
      this.target  = null;
      this._layout();
    }

    const was    = this.invaded;
    this.invaded = invaded;
    this.dead    = !!state.critical;
    if (invaded !== was) {
      if (invaded !== null) this.target = invaded;
      this._route();
      this.walk.dur = GpuGuardFigure.ENTER_MS;
      HL.tset(this.walk, invaded === null ? 0 : 1, now, 0);
      this.walkDrawn = NaN;
    }
    this.swing.t = invaded === null ? 0 : GpuGuardFigure.OPEN;
    this._retarget(now);
  }

  _retarget(now) {
    const rest   = this.invaded === null ? Math.floor((this.count - 1) / 2) : this.invaded;
    const anchor = this.chosen === null ? rest : this.chosen;
    for (const card of this.cards) {
      const distance = Math.abs(card.k - anchor);
      const reach    = Math.max(0, 1 - distance / GpuGuardFigure.REACH) ** 2;
      const target   = this.chosen === null ? (card.k === rest ? this.amount * GpuGuardFigure.REST_LIFT : 0) : this.amount * reach;
      HL.tset(card.tw, target, now, distance * GpuGuardFigure.STAGGER);
      card.el.sil.classList.toggle("hi", card.k === anchor);
      card.led.setAttribute("class", card.k === this.invaded ? (this.dead ? "dot off" : "dot") : "dot m");
    }
    this.loop.wake();
  }
}
class CanopyPlotFigure extends HairlineFigureBase {
  static RANGE = [12, 20, 32];
  static GRID  = 5;
  static PITCH = 16;
  static LIFT  = 15;

  constructor({ stage, svg }, value) {
    super(svg, value, 2.75);
    this.span    = (CanopyPlotFigure.GRID - 1) * CanopyPlotFigure.PITCH;
    this.over    = null;
    this.trees   = this._layout();
    this.tallest = this.trees.reduce((a, b) => (b.h > a.h ? b : a));
    this.tallest.h += 8;
    this._camera(this._extent(), 170);
    this._plinth(-9, -9, this.span + 9, this.span + 9, 8, 4);
    this._buildTrees();
    this._start(stage, svg);
  }

  _layout() {
    const n     = CanopyPlotFigure.GRID;
    const trees = [];
    for (let i = 0; i < n; i++) {
      for (let j = 0; j < n; j++) {
        const u = i / (n - 1);
        const v = j / (n - 1);
        const h = 16 + 16 * Math.exp(-((u - 0.3) ** 2 + (v - 0.7) ** 2) / 0.09) + 9 * Math.exp(-((u - 0.78) ** 2 + (v - 0.28) ** 2) / 0.05) + 3 * Math.sin(i * 2.1 + j * 0.7);
        const r = 3.4 + 1.4 * (0.5 + 0.5 * Math.sin(i * 1.9 + j * 2.3));
        trees.push({ x: i * CanopyPlotFigure.PITCH + 2.2 * Math.sin(i * 3.1 + j * 1.3), y: j * CanopyPlotFigure.PITCH + 2.2 * Math.cos(i * 1.7 + j * 2.9), h, r });
      }
    }
    return trees;
  }

  _extent() {
    const span = this.span;
    const top  = this.tallest.h + CanopyPlotFigure.LIFT;
    return [[-9, -9, -4], [span + 9, span + 9, -4], [span + 9, -9, -4], [-9, span + 9, -4], [this.tallest.x, this.tallest.y, top], [0, 0, 40], [span, 0, 40]];
  }

  _buildTrees() {
    for (const tree of [...this.trees].sort((a, b) => a.x + a.y - (b.x + b.y))) {
      const group  = HL.mk("g", {}, this.g);
      const trunk  = HL.circ(1.1, 20).map((q) => ({ ...q, u: q.u + tree.x, v: q.v + tree.y }));
      tree.ring    = HL.circ(tree.r, 36).map((q) => ({ ...q, u: q.u + tree.x, v: q.v + tree.y }));
      tree.inner   = HL.circ(tree.r - 0.9, 36).map((q) => ({ ...q, u: q.u + tree.x, v: q.v + tree.y }));
      tree.base    = tree.h * 0.66;
      HL.put(HL.solid(group), HL.prism(this.P, this.front, trunk, null, 0, tree.base + 0.5));
      tree.crown   = HL.solid(group);
      tree.sp      = HL.spring(0, { eps: 0.03 });
      tree.drawn   = NaN;
      tree.crown.sil.classList.toggle("hi", tree === this.tallest);
    }
  }

  _tick(dt) {
    let moving = false;
    for (const tree of this.trees) {
      if (HL.stepS(tree.sp, dt)) moving = true;
      if (tree.sp.x === tree.drawn) continue;
      tree.drawn = tree.sp.x;
      HL.put(tree.crown, HL.prism(this.P, this.front, tree.ring, tree.inner, tree.base + tree.sp.x, tree.h + tree.sp.x));
    }
    return moving;
  }

  _move(p) {
    const at     = HL.unproj(this.C, p[0], p[1], 0);
    const inside = at[0] > -9 && at[1] > -9 && at[0] < this.span + 9 && at[1] < this.span + 9;
    this.over    = inside ? at : null;
    this.chosen  = inside ? this.trees[HairlineFigureBase.nearest(this.trees.map((tree) => Math.hypot(tree.x - at[0], tree.y - at[1])), 0)] : null;
    this._retarget();
  }

  _leave() {
    this.over   = null;
    this.chosen = null;
    this._retarget();
  }

  _retarget() {
    const lit = this.chosen === null ? this.tallest : this.chosen;
    for (const tree of this.trees) {
      const distance = this.over === null ? Infinity : Math.hypot(tree.x - this.over[0], tree.y - this.over[1]);
      tree.sp.t      = CanopyPlotFigure.LIFT * Math.max(0, 1 - (distance / this.amount) ** 2) ** 2;
      tree.crown.sil.classList.toggle("hi", tree === lit);
    }
    this.loop.wake();
  }
}

class BackboneBenchFigure extends HairlineFigureBase {
  static RANGE   = [5, 9, 14];
  static BOARD   = [0, 0, 96, 52];
  static SHELF   = 11;
  static LANE    = 38;
  static BAYS    = [13, 30.5, 48, 65.5, 83];
  static SOCKET  = 48;
  static INPUT   = 12;
  static OUTPUT  = 84;
  static HALF    = 5.5;
  static BASE    = 1.5;
  static PINS    = [[7, 4, 9.5], [8, 5.5, 8], [6, 4, 10.5], [7.5, 3, 9], [4, 3, 5]];
  static STAGGER = 160;
  static REST    = 0;

  constructor({ stage, svg }, value) {
    super(svg, value, 3.1);
    this.seated = BackboneBenchFigure.REST;
    this._camera(this._extent(), 166);
    const [x0, y0, x1, y1] = BackboneBenchFigure.BOARD;
    this._plinth(x0, y0, x1, y1, 9, 4);
    this._buildShelf();
    this.shelfLayer = HL.mk("g", {}, this.g);
    this._buildLane();
    this.laneLayer  = HL.mk("g", {}, this.g);
    this.airLayer   = HL.mk("g", {}, this.g);
    this._buildModules();
    this._buildOutput();
    this.bays  = BackboneBenchFigure.BAYS.map((x) => this.P(x, BackboneBenchFigure.SHELF, 0)[0]);
    this._start(stage, svg);
  }

  _extent() {
    const [x0, y0, x1, y1] = BackboneBenchFigure.BOARD;
    const top              = BackboneBenchFigure.BASE + 12 + BackboneBenchFigure.RANGE[2];
    return [[x0, y0, -4], [x1, y1, -4], [x1, y0, -4], [x0, y1, -4], [BackboneBenchFigure.BAYS[0], BackboneBenchFigure.SHELF, 14], [BackboneBenchFigure.SOCKET, 24, top], [BackboneBenchFigure.BAYS[4], BackboneBenchFigure.SHELF, 14]];
  }

  _buildShelf() {
    const y             = BackboneBenchFigure.SHELF;
    const [ring, inner] = HL.rings(4, y - 8, 92, y + 8, 4, 1.6);
    HL.put(HL.solid(this.g), HL.prism(this.P, this.front, ring, inner, 0, BackboneBenchFigure.BASE));
    const h     = BackboneBenchFigure.HALF + 0.8;
    const slots = BackboneBenchFigure.BAYS.map((x) => HL.poly(HL.ringAt(this.P, HL.rrect(x - h, y - h, x + h, y + h, 2), BackboneBenchFigure.BASE)));
    HL.mk("path", { class: "dash nf", d: slots.join("") }, this.g);
  }

  _buildLane() {
    const y = BackboneBenchFigure.LANE;
    HL.mk("path", { class: "dash nf", d: HL.seg(this.P(BackboneBenchFigure.INPUT, y, 0), this.P(BackboneBenchFigure.OUTPUT, y, 0)) }, this.g);
    const x            = BackboneBenchFigure.INPUT;
    const [tile, edge] = HL.rings(x - 7, y - 7, x + 7, y + 7, 2, 0.8);
    HL.put(HL.solid(this.g), HL.prism(this.P, this.front, tile, edge, 0, 1.4));
    const lines = [];
    for (let u = -5, k = 0; u < 5.5; u += 2.6 - 0.3 * k, k++) lines.push(HL.seg(this.P(x + u, y - 5.5, 1.4), this.P(x + u, y + 5.5, 1.4)));
    HL.mk("path", { class: "nf", d: lines.join("") }, this.g);
    const s            = BackboneBenchFigure.SOCKET;
    const [pad, rim]   = HL.rings(s - 8.5, y - 8.5, s + 8.5, y + 8.5, 3, 1.4);
    HL.put(HL.solid(this.g), HL.prism(this.P, this.front, pad, rim, 0, BackboneBenchFigure.BASE));
  }

  _buildModules() {
    const shapes = [() => this._unet(), () => this._tokens(), () => this._pyramid(), () => this._ridges(), () => this._column()];
    this.modules = shapes.map((shape, k) => {
      const group  = HL.mk("g", {}, this.shelfLayer);
      const parts  = shape().map((part) => ({ ...part, el: HL.solid(group) }));
      const [x, y] = this._home(k, BackboneBenchFigure.REST);
      return { k, group, parts, tx: HL.tween(x), ty: HL.tween(y), drawn: null, place: null };
    });
    this._light(BackboneBenchFigure.REST);
  }

  _home(k, seated) {
    return k === seated ? [BackboneBenchFigure.SOCKET, BackboneBenchFigure.LANE] : [BackboneBenchFigure.BAYS[k], BackboneBenchFigure.SHELF];
  }

  _box(x0, y0, x1, y1, z0, z1, r) {
    return { rings: HL.rings(x0, y0, x1, y1, r, Math.min(0.8, r / 2)), z0, z1 };
  }

  _unet() {
    const h = BackboneBenchFigure.HALF;
    return [this._box(-h, -h, h, h, 0, 3, 1.6), this._box(-h, -h, -h + 3.4, h, 3, 11, 1.2), this._box(h - 3.4, -h, h, h, 3, 11, 1.2)];
  }

  _tokens() {
    const h     = BackboneBenchFigure.HALF;
    const parts = [this._box(-h, -h, h, h, 0, 1.4, 1.6)];
    for (let i = -1; i <= 1; i++) for (let j = -1; j <= 1; j++) parts.push({ ...this._box(i * 3.6 - 1.4, j * 3.6 - 1.4, i * 3.6 + 1.4, j * 3.6 + 1.4, 1.4, 4.4 + 2.2 * Math.abs(Math.sin(i * 2.1 + j * 1.3)), 0.7), depth: i + j });
    return parts.sort((a, b) => (a.depth ?? -9) - (b.depth ?? -9));
  }

  _pyramid() {
    return [[5.5, 0, 3], [4, 3.6, 6.6], [2.5, 7.2, 10.2]].map(([h, z0, z1]) => this._box(-h, -h, h, h, z0, z1, 1.4));
  }

  _ridges() {
    const h = BackboneBenchFigure.HALF;
    return [this._box(-h, -h, h, h, 0, 4, 1.6)].concat([-3, 0, 3].map((x) => this._box(x - 0.7, -h + 1, x + 0.7, h - 1, 4, 7, 0.5)));
  }

  _column() {
    return [this._box(-3, -3, 3, 3, 0, 1.4, 1.2), this._box(-1.5, -1.5, 1.5, 1.5, 1.4, 12, 0.8)];
  }

  _buildOutput() {
    const x           = BackboneBenchFigure.OUTPUT;
    const y           = BackboneBenchFigure.LANE;
    const [dish, lip] = HL.rings(x - 7, y - 4, x + 7, y + 4, 2, 0.8);
    HL.put(HL.solid(this.g), HL.prism(this.P, this.front, dish, lip, 0, 1.4));
    this.pins = BackboneBenchFigure.PINS[BackboneBenchFigure.REST].map((h, j) => {
      const px = x + (j - 1) * 4.4;
      return { rings: HL.rings(px - 1.4, y - 1.4, px + 1.4, y + 1.4, 0.8, 0.4), el: HL.solid(this.g), j, tw: HL.tween(h), drawn: NaN };
    });
  }

  _light(seated) {
    for (const module of this.modules) for (const part of module.parts) part.el.sil.classList.toggle("hi", module.k === seated);
  }

  _tick(dt, now) {
    let moving = false;
    for (const module of this.modules) {
      if (!HL.tdone(module.tx, now) || !HL.tdone(module.ty, now)) moving = true;
      const x    = HL.tval(module.tx, now);
      const y    = HL.tval(module.ty, now);
      const span = module.ty.to - module.ty.from;
      const hop  = span ? this.amount * Math.sin(Math.PI * HL.clamp((y - module.ty.from) / span, 0, 1)) : 0;
      if (module.drawn && module.drawn[0] === x && module.drawn[1] === y && module.drawn[2] === hop) continue;
      module.drawn = [x, y, hop];
      this._drawModule(module, x, y, hop);
    }
    for (const pin of this.pins) {
      const h = HL.tval(pin.tw, now);
      if (!HL.tdone(pin.tw, now)) moving = true;
      if (h === pin.drawn) continue;
      pin.drawn = h;
      HL.put(pin.el, HL.prism(this.P, this.front, pin.rings[0], pin.rings[1], 1.4, 1.4 + h));
    }
    return moving;
  }

  _drawModule(module, x, y, hop) {
    const place = hop > 0.5 ? this.airLayer : y > (BackboneBenchFigure.SHELF + BackboneBenchFigure.LANE) / 2 ? this.laneLayer : this.shelfLayer;
    if (place !== module.place) {
      module.place = place;
      const after  = [...place.children].find((group) => this.modules.find((other) => other.group === group).k > module.k);
      place.insertBefore(module.group, after || null);
    }
    const moved = this._shifted(x, y, BackboneBenchFigure.BASE + hop);
    for (const part of module.parts) HL.put(part.el, HL.prism(moved, this.front, part.rings[0], part.rings[1], part.z0, part.z1));
  }

  _move(p) {
    this._choose(HairlineFigureBase.nearest(this.bays, p[0]));
  }

  _retarget(now) {
    const seated = this.chosen === null ? BackboneBenchFigure.REST : this.chosen;
    if (seated === this.seated) return;
    const leaving  = this.modules[this.seated];
    const arriving = this.modules[seated];
    const [lx, ly] = this._home(leaving.k, seated);
    const [ax, ay] = this._home(arriving.k, seated);
    this.seated    = seated;
    HL.tset(leaving.tx, lx, now, 0);
    HL.tset(leaving.ty, ly, now, 0);
    HL.tset(arriving.tx, ax, now, BackboneBenchFigure.STAGGER);
    HL.tset(arriving.ty, ay, now, BackboneBenchFigure.STAGGER);
    for (const pin of this.pins) HL.tset(pin.tw, BackboneBenchFigure.PINS[seated][pin.j], now, 3 * BackboneBenchFigure.STAGGER);
    this._light(seated);
    this.loop.wake();
  }
}

class RepoCityFigure extends HairlineFigureBase {
  static RANGE     = [4, 8, 14];
  static SIZES     = [106, 102, 72, 22, 11, 9];
  static PITCH     = 7;
  static BLOCK     = 5.4;
  static GAP       = 6;
  static STAGGER   = 40;
  static REST      = 1;

  constructor({ stage, svg }, value) {
    super(svg, value, 2.75);
    this.block  = 3 * RepoCityFigure.PITCH + RepoCityFigure.GAP;
    this.blocks = this._layout();
    this._camera(this._extent(), 168);
    this._plinth(-5, -5, 3 * this.block - RepoCityFigure.GAP + 4, 2 * this.block - RepoCityFigure.GAP + 4, 7, 4);
    this._buildBlocks();
    this._start(stage, svg);
  }

  _layout() {
    const largest = Math.sqrt(RepoCityFigure.SIZES[0]);
    const blocks  = [];
    RepoCityFigure.SIZES.forEach((lines, d) => {
      const ox    = (d % 3) * this.block;
      const oy    = Math.floor(d / 3) * this.block;
      const scale = Math.sqrt(lines) / largest;
      for (let a = 0; a < 3; a++) {
        for (let b = 0; b < 3; b++) {
          const seed = 0.5 + 0.5 * Math.sin(d * 7.1 + a * 3.3 + b * 5.7);
          if (0.5 + 0.5 * Math.sin(d * 2.9 + a * 6.1 + b * 1.3) < 0.12) continue;
          blocks.push({ d, a, b, x: ox + a * RepoCityFigure.PITCH, y: oy + b * RepoCityFigure.PITCH, h: 3 + 24 * scale * (0.35 + 0.65 * seed) });
        }
      }
    });
    return blocks;
  }

  _extent() {
    const w   = 3 * this.block - RepoCityFigure.GAP + 4;
    const dep = 2 * this.block - RepoCityFigure.GAP + 4;
    return [[-5, -5, -4], [w, dep, -4], [w, -5, -4], [-5, dep, -4], [0, 0, 27 + RepoCityFigure.RANGE[2]], [w * 0.4, 0, 27 + RepoCityFigure.RANGE[2]]];
  }

  _buildBlocks() {
    const half = RepoCityFigure.BLOCK / 2;
    this.blocks.sort((a, b) => a.x + a.y - (b.x + b.y));
    for (const block of this.blocks) {
      const [ring, inner] = HL.rings(block.x - half, block.y - half, block.x + half, block.y + half, 1.3, 0.55);
      block.ring  = ring;
      block.inner = inner;
      block.el    = HL.solid(this.g);
      block.tw    = HL.tween(0);
      block.drawn = NaN;
      block.hull  = HL.hull(HL.ringAt(this.P, ring, 0).concat(HL.ringAt(this.P, ring, block.h)));
      block.el.sil.classList.toggle("hi", block.d === RepoCityFigure.REST);
    }
  }

  _tick(dt, now) {
    return this._advance(this.blocks, now);
  }

  _draw(block, lift) {
    HL.put(block.el, HL.prism(this.P, this.front, block.ring, block.inner, 0, block.h + lift));
  }

  _move(p) {
    for (let i = this.blocks.length - 1; i >= 0; i--) {
      if (HairlineGeometry.inside(this.blocks[i].hull, p)) return this._choose(this.blocks[i].d);
    }
    const [x, y] = HL.unproj(this.C, p[0], p[1], 0);
    const col    = Math.floor((x + RepoCityFigure.PITCH / 2) / this.block);
    const row    = Math.floor((y + RepoCityFigure.PITCH / 2) / this.block);
    this._choose(col >= 0 && col < 3 && row >= 0 && row < 2 ? row * 3 + col : null);
  }

  _retarget(now) {
    const lit = this.chosen === null ? RepoCityFigure.REST : this.chosen;
    for (const block of this.blocks) {
      const chosen = block.d === this.chosen;
      HL.tset(block.tw, chosen ? this.amount : 0, now, chosen ? (Math.abs(block.a - 1) + Math.abs(block.b - 1)) * RepoCityFigure.STAGGER : 0);
      block.el.sil.classList.toggle("hi", block.d === lit);
    }
    this.loop.wake();
  }
}

class LossLandscapeFigure extends HairlineFigureBase {
  static RANGE = [30, 60, 120];
  static GRID  = 9;
  static CELL  = 10;
  static FOOT  = 8.2;
  static BALL  = 4.2;

  constructor({ stage, svg }, value) {
    super(svg, value, 2.3);
    this.heights = this._surface();
    this.low     = Math.min(...this.heights.flat());
    this.high    = Math.max(...this.heights.flat());
    this.minimum = this._minimum();
    this._camera(this._extent(), 168);
    this._plinth(-3, -3, LossLandscapeFigure.GRID * LossLandscapeFigure.CELL + 3, LossLandscapeFigure.GRID * LossLandscapeFigure.CELL + 3, 7, 4);
    this._buildPillars();
    this._buildBall();
    this._start(stage, svg);
  }

  _surface() {
    const n = LossLandscapeFigure.GRID;
    return Array.from({ length: n }, (_, i) => Array.from({ length: n }, (_, j) => {
      const u = i / (n - 1);
      const v = j / (n - 1);
      const h = 3 + 30 * ((u - 0.72) ** 2 + (v - 0.72) ** 2) + 6 * Math.exp(-((u - 0.4) ** 2 + (v - 0.55) ** 2) / 0.015) - 3 * Math.exp(-((u - 0.3) ** 2 + (v - 0.85) ** 2) / 0.01);
      return Math.max(1.5, h);
    }));
  }

  _minimum() {
    let best = [0, 0];
    this.heights.forEach((row, i) => row.forEach((h, j) => { if (h < this.heights[best[0]][best[1]]) best = [i, j]; }));
    return this._centre(best[0], best[1]);
  }

  _centre(i, j) {
    return [(i + 0.5) * LossLandscapeFigure.CELL, (j + 0.5) * LossLandscapeFigure.CELL];
  }

  _extent() {
    const span = LossLandscapeFigure.GRID * LossLandscapeFigure.CELL;
    return [[-3, -3, -4], [span + 3, span + 3, -4], [span + 3, -3, -4], [-3, span + 3, -4], [0, 0, this.high + 6], [span, 0, this.high], [0, span, this.high]];
  }

  _buildPillars() {
    const n     = LossLandscapeFigure.GRID;
    const inset = (LossLandscapeFigure.CELL - LossLandscapeFigure.FOOT) / 2;
    this.pillars = [];
    for (let s = 0; s <= 2 * (n - 1); s++) {
      for (let i = 0; i < n; i++) {
        const j = s - i;
        if (j < 0 || j >= n) continue;
        const x0            = i * LossLandscapeFigure.CELL + inset;
        const y0            = j * LossLandscapeFigure.CELL + inset;
        const [ring, inner] = HL.rings(x0, y0, x0 + LossLandscapeFigure.FOOT, y0 + LossLandscapeFigure.FOOT, 2.2, 0.9);
        const el            = HL.solid(this.g);
        HL.put(el, HL.prism(this.P, this.front, ring, inner, 0, this.heights[i][j]));
        this.pillars.push({ i, j, el });
      }
    }
    this.byCell = new Map(this.pillars.map((pillar) => [`${pillar.i},${pillar.j}`, pillar]));
  }

  _buildBall() {
    this.ballGroup = HL.mk("g", {}, this.g);
    this.ball      = HL.mk("ellipse", { class: "hi", rx: HL.r2(LossLandscapeFigure.BALL * this.C.S), ry: HL.r2(LossLandscapeFigure.BALL * this.C.S) }, this.ballGroup);
    this.equator   = HL.mk("path", { class: "nf" }, this.ballGroup);
    this.equatorRing = HL.run(HL.circ(LossLandscapeFigure.BALL, 40), this.front);
    this.sx        = HL.spring(this.minimum[0], { k: this.amount });
    this.sy        = HL.spring(this.minimum[1], { k: this.amount });
    this.cell      = null;
    this.drawnBall = null;
  }

  _height(x, y) {
    const n  = LossLandscapeFigure.GRID;
    const fx = HL.clamp(x / LossLandscapeFigure.CELL - 0.5, 0, n - 1);
    const fy = HL.clamp(y / LossLandscapeFigure.CELL - 0.5, 0, n - 1);
    const i  = Math.min(n - 2, Math.floor(fx));
    const j  = Math.min(n - 2, Math.floor(fy));
    const tx = fx - i;
    const ty = fy - j;
    const h  = this.heights;
    return HL.lerp(HL.lerp(h[i][j], h[i + 1][j], tx), HL.lerp(h[i][j + 1], h[i + 1][j + 1], tx), ty);
  }

  _tick(dt) {
    const moving = HL.stepS(this.sx, dt) | HL.stepS(this.sy, dt);
    const x      = this.sx.x;
    const y      = this.sy.x;
    const key    = `${x}|${y}`;
    if (key !== this.drawnBall) {
      this.drawnBall = key;
      this._drawBall(x, y);
    }
    return Boolean(moving);
  }

  _drawBall(x, y) {
    const n    = LossLandscapeFigure.GRID;
    const z    = this._height(x, y) + LossLandscapeFigure.BALL;
    const i    = HL.clamp(Math.floor(x / LossLandscapeFigure.CELL), 0, n - 1);
    const j    = HL.clamp(Math.floor(y / LossLandscapeFigure.CELL), 0, n - 1);
    const cell = this.byCell.get(`${i},${j}`);
    if (cell !== this.cell) {
      this.cell = cell;
      cell.el.g.after(this.ballGroup);
    }
    HL.place(this.ball, this.P(x, y, z));
    this.equator.setAttribute("d", HL.open(this.equatorRing.map((q) => this.P(x + q.u, y + q.v, z))));
  }

  _move(p) {
    const span   = LossLandscapeFigure.GRID * LossLandscapeFigure.CELL;
    const [x, y] = HL.unproj(this.C, p[0], p[1], (this.low + this.high) / 2);
    this.sx.t    = HL.clamp(x, 2, span - 2);
    this.sy.t    = HL.clamp(y, 2, span - 2);
    this.loop.wake();
  }

  _leave() {
    this.sx.t = this.minimum[0];
    this.sy.t = this.minimum[1];
    this.loop.wake();
  }

  _retarget() {
    this.sx.k = this.amount;
    this.sy.k = this.amount;
    this.loop.wake();
  }
}

class GaussianSurfaceFigure extends HairlineFigureBase {
  static RANGE   = [20, 30, 42];
  static LX      = 96;
  static LY      = 64;
  static SLICES  = 18;
  static SAMPLES = 44;
  static FLOOR   = 2.4;
  static TRACK   = [[12, 10], [84, 54]];
  static PEAKS   = [1, 0.62];
  static SIGMA   = [7.5, 10.5];
  static REST    = [0.24, 0.74];
  static SPACE   = 0.38;

  constructor({ stage, svg }, value) {
    super(svg, value, 2.45);
    this.dy     = GaussianSurfaceFigure.LY / (GaussianSurfaceFigure.SLICES - 1);
    this.pos    = GaussianSurfaceFigure.REST.map((s) => HL.spring(s, { k: 26, c: 8, eps: 0.0005 }));
    this.drawn  = [NaN, NaN, NaN];
    this.chosen = null;
    this._camera(this._extent(), 168);
    this._plinth(-6, -6, GaussianSurfaceFigure.LX + 6, GaussianSurfaceFigure.LY + 6, 6, 4);
    this._buildSlices();
    this._buildPeaks();
    this._start(stage, svg);
    this._retarget();
  }

  _extent() {
    const [a, b] = GaussianSurfaceFigure.TRACK;
    const top    = GaussianSurfaceFigure.FLOOR + GaussianSurfaceFigure.RANGE[2];
    const lx     = GaussianSurfaceFigure.LX + 6;
    const ly     = GaussianSurfaceFigure.LY + 6;
    return [[-6, -6, -4], [lx, ly, -4], [lx, -6, -4], [-6, ly, -4], [a[0], a[1], top], [b[0], b[1], top], [0, 0, GaussianSurfaceFigure.FLOOR], [GaussianSurfaceFigure.LX, GaussianSurfaceFigure.LY, GaussianSurfaceFigure.FLOOR]];
  }

  _buildSlices() {
    this.slices = Array.from({ length: GaussianSurfaceFigure.SLICES }, (_, k) => {
      const group = HL.mk("g", {}, this.g);
      const fill  = HL.mk("path", { class: "fo" }, group);
      const line  = HL.mk("path", { class: "nf" }, group);
      const track = HL.mk("path", { class: "dash nf" }, group);
      return { k, y: k * this.dy, group, fill, line, track };
    });
  }

  _buildPeaks() {
    this.peaks = GaussianSurfaceFigure.PEAKS.map(() => HL.flatDot(this.g, this.C, 1.2, "dot m"));
  }

  _centre(s) {
    const [a, b] = GaussianSurfaceFigure.TRACK;
    return [HL.lerp(a[0], b[0], s), HL.lerp(a[1], b[1], s)];
  }

  _height(x, y, centres) {
    let h = GaussianSurfaceFigure.FLOOR;
    centres.forEach(([cx, cy], j) => {
      const sigma = GaussianSurfaceFigure.SIGMA[j];
      h += this.amount * GaussianSurfaceFigure.PEAKS[j] * Math.exp(-((x - cx) ** 2 + (y - cy) ** 2) / (2 * sigma * sigma));
    });
    return h;
  }

  _tick(dt) {
    const moving = this.pos.map((sp) => HL.stepS(sp, dt)).some(Boolean);
    const now    = [this.pos[0].x, this.pos[1].x, this.amount];
    if (now.every((v, i) => v === this.drawn[i])) return moving;
    this.drawn = now;
    this._drawSurface();
    return moving;
  }

  _drawSurface() {
    const centres = this.pos.map((sp) => this._centre(sp.x));
    const n       = GaussianSurfaceFigure.SAMPLES;
    const [a, b]  = GaussianSurfaceFigure.TRACK;
    const lead    = this._lead();

    for (const slice of this.slices) {
      const top = [];
      for (let i = 0; i <= n; i++) {
        const x = (i / n) * GaussianSurfaceFigure.LX;
        top.push(this.P(x, slice.y, this._height(x, slice.y, centres)));
      }
      const base = [this.P(GaussianSurfaceFigure.LX, slice.y, 0), this.P(0, slice.y, 0)];
      slice.fill.setAttribute("d", HL.poly(top.concat(base)));
      slice.line.setAttribute("d", HL.open(top));

      const y0 = slice.y;
      const y1 = Math.min(GaussianSurfaceFigure.LY, slice.y + this.dy);
      const t0 = HL.clamp((y0 - a[1]) / (b[1] - a[1]), 0, 1);
      const t1 = HL.clamp((y1 - a[1]) / (b[1] - a[1]), 0, 1);
      const pts = [];
      if (t1 > t0) {
        for (let q = 0; q <= 6; q++) {
          const t = HL.lerp(t0, t1, q / 6);
          const [x, y] = this._centre(t);
          pts.push(this.P(x, y, this._height(x, y, centres) + 0.4));
        }
      }
      slice.track.setAttribute("d", pts.length ? HL.open(pts) : "");
    }

    centres.forEach(([cx, cy], j) => {
      const k     = HL.clamp(Math.floor(cy / this.dy), 0, GaussianSurfaceFigure.SLICES - 1);
      const group = this.slices[k].group;
      if (this.peaks[j].parentNode !== group) group.appendChild(this.peaks[j]);
      HL.place(this.peaks[j], this.P(cx, cy, this._height(cx, cy, centres)));
      this.peaks[j].setAttribute("class", j === lead ? "dot" : "dot m");
    });

    const ridge = Math.round(centres[lead][1] / this.dy);
    for (const slice of this.slices) slice.line.classList.toggle("hi", slice.k === ridge);
  }

  _lead() {
    return this.chosen === null ? 0 : this.chosen.j;
  }

  _along(p) {
    const [a, b] = GaussianSurfaceFigure.TRACK;
    const [x, y] = HL.unproj(this.C, p[0], p[1], 0);
    const dx     = b[0] - a[0];
    const dy     = b[1] - a[1];
    return HL.clamp(((x - a[0]) * dx + (y - a[1]) * dy) / (dx * dx + dy * dy), 0, 1);
  }

  _move(p) {
    const s = this._along(p);
    const j = this.chosen === null ? (Math.abs(s - this.pos[0].x) <= Math.abs(s - this.pos[1].x) ? 0 : 1) : this.chosen.j;
    this.chosen = { j, s };
    this._retarget();
  }

  _leave() {
    this.chosen = null;
    this._retarget();
  }

  _retarget() {
    if (this.chosen === null) {
      this.pos.forEach((sp, j) => { sp.t = GaussianSurfaceFigure.REST[j]; });
    } else {
      const { j, s } = this.chosen;
      const other    = 1 - j;
      const space    = GaussianSurfaceFigure.SPACE;
      this.pos[j].t  = s;
      const side     = this.pos[other].x >= s ? 1 : -1;
      let away       = s + side * space;
      if (away > 1 || away < 0) away = s - side * space;
      this.pos[other].t = Math.abs(this.pos[other].x - s) < space ? HL.clamp(away, 0, 1) : this.pos[other].t;
    }
    this.drawn = [NaN, NaN, NaN];
    this.loop.wake();
  }
}

class BalanceFigure extends HairlineFigureBase {
  static RANGE  = [0.1, 0.2, 0.32];
  static ARM    = 34;
  static POST   = 40;
  static STRING = 18;
  static PAN    = 9;
  static REST   = -0.4;
  static ALONG  = [Math.SQRT1_2, -Math.SQRT1_2];
  static ACROSS = [Math.SQRT1_2, Math.SQRT1_2];
  static STACK  = 4;
  static WEIGHT = [3, 1.5, 1.9];
  static FULL   = 0.3;
  static SWAY   = 0.6;

  constructor({ stage, svg }, value) {
    super(svg, value, 2.8);
    this.bias    = BalanceFigure.REST;
    this.sway    = 1;
    this.weights = [0, 0];
    this.alarm   = false;
    this._camera(this._extent(), 150);
    this._buildStand();
    this._buildPans();
    this._buildBeam();
    this.tilt  = HL.spring(BalanceFigure.REST * this.amount, { k: 60, c: 9 });
    this.drawn = NaN;
    this._start(stage, svg);
  }

  _extent() {
    const reach = BalanceFigure.ARM + BalanceFigure.PAN;
    const [ax, ay] = BalanceFigure.ALONG;
    const low = BalanceFigure.POST - BalanceFigure.STRING - BalanceFigure.ARM * Math.sin(BalanceFigure.RANGE[2]) - 2;
    return [[-14, -14, -4], [14, 14, -4], [ax * reach, ay * reach, low], [-ax * reach, -ay * reach, low], [ax * reach, ay * reach, BalanceFigure.POST + 14], [-ax * reach, -ay * reach, BalanceFigure.POST + 14]];
  }

  _buildStand() {
    HL.put(HL.solid(this.g), HL.prism(this.P, this.front, HL.circ(14, 64), HL.circ(12.6, 64), -4, 0));
    const [ring, inner] = HL.rings(-1.8, -1.8, 1.8, 1.8, 1.2, 0.5);
    HL.put(HL.solid(this.g), HL.prism(this.P, this.front, ring, inner, 0, BalanceFigure.POST));
  }

  _buildPans() {
    this.pans = [-1, 1].map((side, k) => {
      const group   = HL.mk("g", {}, this.g);
      const strings = HL.mk("path", { class: "nf" }, group);
      const el      = HL.solid(group);
      const dots    = Array.from({ length: k + 1 }, (_, j) => ({ off: (j - k / 2) * 2.4, el: HL.flatDot(group, this.C, 0.9, "dot m") }));
      const stack   = Array.from({ length: BalanceFigure.STACK }, () => HL.solid(group));
      return { side, k, strings, el, dots, stack };
    });
  }

  _buildBeam() {
    this.beam      = HL.solid(this.g);
    this.beamRing  = HL.rrect(-BalanceFigure.ARM - 3, -2.2, BalanceFigure.ARM + 3, 2.2, 1.6, 4);
    this.beamInner = HL.rrect(-BalanceFigure.ARM - 2.2, -1.4, BalanceFigure.ARM + 2.2, 1.4, 1, 4);
  }

  _tick(dt) {
    const moving = HL.stepS(this.tilt, dt);
    if (this.tilt.x !== this.drawn) {
      this.drawn = this.tilt.x;
      this._drawScale(this.tilt.x);
    }
    return moving;
  }

  _drawScale(theta) {
    const [dx, dy] = BalanceFigure.ALONG;
    const [ex, ey] = BalanceFigure.ACROSS;
    const c        = Math.cos(theta);
    const s        = Math.sin(theta);
    const pivot    = BalanceFigure.POST + 2;
    const at       = (u, v, w) => this.P(u * c * dx + v * ex - w * s * dx, u * c * dy + v * ey - w * s * dy, pivot + u * s + w * c);
    const keep     = (q) => this.front({ nu: q.nu * dx + q.nv * ex, nv: q.nu * dy + q.nv * ey });
    const top      = this.beamRing.map((q) => at(q.u, q.v, 1.4));
    const bottom   = this.beamRing.map((q) => at(q.u, q.v, -1.4));
    HL.put(this.beam, { sil: HL.poly(HL.hull(top.concat(bottom))), crease: HL.open(HL.run(this.beamInner, keep).map((q) => at(q.u, q.v, 1.4))) });

    const heavier = theta > 0 ? -1 : 1;
    for (const pan of this.pans) {
      const u    = pan.side * BalanceFigure.ARM;
      const ex0  = u * c * dx;
      const ey0  = u * c * dy;
      const ez   = pivot + u * s - BalanceFigure.STRING;
      const ring = HL.circ(BalanceFigure.PAN, 48).map((q) => ({ ...q, u: q.u + ex0, v: q.v + ey0 }));
      const rim  = (side) => this.P(ex0 + side * BalanceFigure.PAN * 0.85 * dx, ey0 + side * BalanceFigure.PAN * 0.85 * dy, ez);
      HL.put(pan.el, HL.prism(this.P, this.front, ring, null, ez - 1.4, ez));
      pan.strings.setAttribute("d", HL.seg(at(u, 0, -1.4), rim(-1)) + HL.seg(at(u, 0, -1.4), rim(1)));
      for (const dot of pan.dots) HL.place(dot.el, this.P(ex0 + dot.off * ex, ey0 + dot.off * ey, ez));
      pan.el.sil.classList.toggle("hi", pan.side === heavier);
      for (const dot of pan.dots) dot.el.setAttribute("class", pan.side === heavier ? "dot" : "dot m");
      this._drawStack(pan, ex0 - 0.5 * BalanceFigure.PAN * ex, ey0 - 0.5 * BalanceFigure.PAN * ey, ez);
    }
  }

  _drawStack(pan, x, y, z) {
    const [radius, thick, pitch] = BalanceFigure.WEIGHT;
    const ring                   = HL.circ(radius, 32).map((q) => ({ ...q, u: q.u + x, v: q.v + y }));
    const lit                    = this.alarm && pan.k === 0;
    pan.stack.forEach((weight, i) => {
      HL.put(weight, i < this.weights[pan.k] ? HL.prism(this.P, this.front, ring, null, z + i * pitch, z + i * pitch + thick) : { sil: "", crease: "" });
      weight.sil.classList.toggle("hi", lit);
    });
  }

  _move(p) {
    const centre = this.P(0, 0, BalanceFigure.POST)[0];
    const push   = HL.clamp((centre - p[0]) / 110, -1, 1);
    this.chosen  = true;
    this.tilt.t  = HL.clamp(this.sway === 1 ? push : this.bias + this.sway * push, -1, 1) * this.amount;
    this.loop.wake();
  }

  _leave() {
    this.chosen = null;
    this.tilt.t = this.bias * this.amount;
    this.loop.wake();
  }

  setState(state) {
    const mine   = Math.max(0, state.mine);
    const others = Math.max(0, state.others);
    const total  = mine + others;
    const heavy  = Math.max(mine, others);
    if (!Number.isFinite(total)) throw new Error("balance figure: state.mine and state.others must be numbers");
    this.sway    = BalanceFigure.SWAY;
    this.alarm   = !!state.alarm;
    this.bias    = total > 0 ? ((mine - others) / total) * Math.min(1, total / BalanceFigure.FULL) : 0;
    this.weights = total < 0.005 ? [1, 1] : [mine, others].map((w) => Math.round((BalanceFigure.STACK * w) / heavy));
    this.drawn   = NaN;
    this._retarget();
  }

  _retarget() {
    this.tilt.t = this.chosen === null ? this.bias * this.amount : HL.clamp(this.tilt.t, -this.amount, this.amount);
    this.loop.wake();
  }
}

class AutoencoderFigure extends HairlineFigureBase {
  static RANGE     = [6, 11, 18];
  static WIDTHS    = [30, 24, 18, 12, 6.5, 12, 18, 24, 30];
  static LATENT    = 4;
  static PLATE     = 3;
  static STEP      = 6.2;
  static STAGGER   = 40;
  static REST_GAP  = 0.4;

  constructor({ stage, svg }, value) {
    super(svg, value, 2.35);
    this._camera(this._extent(), 166);
    this._buildBase();
    this._buildPlates();
    this._start(stage, svg);
  }

  _outline(half, inset) {
    if (this.constructor.ROUND) return HL.circ(half - inset, 64);
    return HL.rrect(-half + inset, -half + inset, half - inset, half - inset, Math.max(0.6, 3 - inset), 4);
  }

  _extent() {
    const top = AutoencoderFigure.WIDTHS.length * AutoencoderFigure.STEP + AutoencoderFigure.RANGE[2];
    return [[-38, -38, -4], [38, 38, -4], [38, -38, -4], [-38, 38, -4], [0, 0, top], [30, -30, top * 0.7], [-30, 30, top * 0.7]];
  }

  _buildBase() {
    HL.put(HL.solid(this.g), HL.prism(this.P, this.front, this._outline(38, 0), this._outline(38, 2.2), -4, 0));
  }

  _buildPlates() {
    this.plates = AutoencoderFigure.WIDTHS.map((half, i) => {
      const el    = HL.solid(this.g);
      const z0    = 1 + i * AutoencoderFigure.STEP;
      const above = i > AutoencoderFigure.LATENT;
      el.sil.classList.toggle("hi", i === AutoencoderFigure.LATENT);
      return { i, ring: this._outline(half, 0), inner: this._outline(half, 1.2), z0, el, tw: HL.tween(above ? this.amount * AutoencoderFigure.REST_GAP : 0), drawn: NaN, restY: this.P(0, 0, z0 + AutoencoderFigure.PLATE / 2)[1] };
    });
  }

  _tick(dt, now) {
    return this._advance(this.plates, now);
  }

  _draw(plate, gap) {
    HL.put(plate.el, HL.prism(this.P, this.front, plate.ring, plate.inner, plate.z0 + gap, plate.z0 + gap + AutoencoderFigure.PLATE));
  }

  _move(p) {
    this._choose(HairlineFigureBase.nearest(this.plates.map((plate) => plate.restY), p[1]));
  }

  _retarget(now) {
    const split = this.chosen === null ? AutoencoderFigure.LATENT : this.chosen;
    const gap   = this.chosen === null ? this.amount * AutoencoderFigure.REST_GAP : this.amount;
    for (const plate of this.plates) {
      HL.tset(plate.tw, plate.i > split ? gap : 0, now, Math.max(0, plate.i - split - 1) * AutoencoderFigure.STAGGER);
      plate.el.sil.classList.toggle("hi", plate.i === split);
    }
    this.loop.wake();
  }
}

class ProfileAutoencoderFigure extends AutoencoderFigure {
  static ROUND = true;
}

class ImageAutoencoderFigure extends AutoencoderFigure {
  static ROUND = false;
}

class JepaEmbeddingFigure extends HairlineFigureBase {
  static RANGE   = [40, 100, 220];
  static BOARD   = [8, 4, 88, 50];
  static TOWERS  = [26, 70];
  static ROW     = 20;
  static FRONT   = 40;
  static LAYERS  = [[9, 0, 5], [8, 6, 11], [7, 12, 17]];
  static TARGET  = [7, 10.5, 4.5, 8.5];
  static START   = [3, 5, 10.5, 2.5];
  static PITCH   = 4.4;
  static PIN     = 1.5;
  static REST    = 0.55;

  constructor({ stage, svg }, value) {
    super(svg, value, 3.6);
    this._camera(this._extent(), 168);
    const [x0, y0, x1, y1] = JepaEmbeddingFigure.BOARD;
    this._plinth(x0, y0, x1, y1, 9, 4);
    const [left, right] = JepaEmbeddingFigure.TOWERS;
    this._buildTower(left);
    this.predicted = this._buildComb(left, true);
    this._buildTower(right);
    this.target    = this._buildComb(right, false);
    this._buildImage(left);
    this._buildProfile(right);
    this.sweep     = [this.P(x0, y1, 0)[0], this.P(x1, y0, 0)[0]];
    this.progress  = HL.spring(JepaEmbeddingFigure.REST, { k: this.amount });
    this.drawn     = NaN;
    this._start(stage, svg);
  }

  _extent() {
    const [x0, y0, x1, y1] = JepaEmbeddingFigure.BOARD;
    const top              = 18.2 + Math.max(...JepaEmbeddingFigure.TARGET, ...JepaEmbeddingFigure.START);
    const [left, right]    = JepaEmbeddingFigure.TOWERS;
    return [[x0, y0, -4], [x1, y1, -4], [x1, y0, -4], [x0, y1, -4], [left, JepaEmbeddingFigure.ROW, top], [right, JepaEmbeddingFigure.ROW, top]];
  }

  _buildTower(x) {
    const at = this._shifted(x, JepaEmbeddingFigure.ROW, 0);
    for (const [half, z0, z1] of JepaEmbeddingFigure.LAYERS) {
      const [ring, inner] = HL.rings(-half, -half, half, half, 2.4, 1);
      HL.put(HL.solid(this.g), HL.prism(at, this.front, ring, inner, z0, z1));
    }
  }

  _buildComb(x, lit) {
    const at            = this._shifted(x, JepaEmbeddingFigure.ROW, 0);
    const [ring, inner] = HL.rings(-9.5, -3.6, 9.5, 3.6, 1.6, 0.7);
    HL.put(HL.solid(this.g), HL.prism(at, this.front, ring, inner, 17, 18.2));
    const heights = lit ? JepaEmbeddingFigure.START : JepaEmbeddingFigure.TARGET;
    return heights.map((h, j) => {
      const dx            = (j - (heights.length - 1) / 2) * JepaEmbeddingFigure.PITCH;
      const [pin, crease] = HL.rings(dx - JepaEmbeddingFigure.PIN, -JepaEmbeddingFigure.PIN, dx + JepaEmbeddingFigure.PIN, JepaEmbeddingFigure.PIN, 0.8, 0.4);
      if (lit) HL.mk("path", { class: "dash nf", d: HL.prism(at, this.front, pin, null, 18.2, 18.2 + JepaEmbeddingFigure.TARGET[j]).sil }, this.g);
      const el            = HL.solid(this.g);
      el.sil.classList.toggle("hi", lit);
      if (!lit) HL.put(el, HL.prism(at, this.front, pin, crease, 18.2, 18.2 + h));
      return { at, pin, crease, el };
    });
  }

  _buildImage(x) {
    const y             = JepaEmbeddingFigure.FRONT;
    const [ring, inner] = HL.rings(x - 7.5, y - 7.5, x + 7.5, y + 7.5, 2, 0.8);
    HL.put(HL.solid(this.g), HL.prism(this.P, this.front, ring, inner, 0, 1.4));
    const lines = [];
    for (let u = -5.5, k = 0; u < 6; u += 2.6 - 0.25 * k, k++) lines.push(HL.seg(this.P(x + u, y - 6, 1.4), this.P(x + u, y + 6, 1.4)));
    HL.mk("path", { class: "nf", d: lines.join("") }, this.g);
  }

  _buildProfile(x) {
    const at = this._shifted(x, JepaEmbeddingFigure.FRONT, 0);
    for (let k = 0; k < 6; k++) {
      const r = 2.2 + 3.8 * Math.exp(-((k / 1.1) ** 2)) + 3.2 * Math.exp(-(((k - 4.2) / 1) ** 2));
      HL.put(HL.solid(this.g), HL.prism(at, this.front, HL.circ(r, 40), HL.circ(Math.max(0.6, r - 0.8), 40), k * 3.1, k * 3.1 + 2.3));
    }
  }

  _tick(dt) {
    const moving = HL.stepS(this.progress, dt);
    const t      = HL.clamp(this.progress.x, 0, 1);
    if (t !== this.drawn) {
      this.drawn = t;
      const ease = t * t * (3 - 2 * t);
      this.predicted.forEach((pin, j) => {
        const h = HL.lerp(JepaEmbeddingFigure.START[j], JepaEmbeddingFigure.TARGET[j], ease);
        HL.put(pin.el, HL.prism(pin.at, this.front, pin.pin, pin.crease, 18.2, 18.2 + h));
      });
    }
    return moving;
  }

  _move(p) {
    const [x0, x1]   = this.sweep;
    this.progress.t  = HL.clamp((p[0] - x0) / (x1 - x0), 0, 1);
    this.loop.wake();
  }

  _leave() {
    this.progress.t = JepaEmbeddingFigure.REST;
    this.loop.wake();
  }

  _retarget() {
    this.progress.k = this.amount;
    this.loop.wake();
  }
}

class PodiumFigure extends HairlineFigureBase {
  static RANGE   = [4, 8, 14];
  static RANKS   = [4, 2, 1, 3, 5];
  static HEIGHTS = { 1: 24, 2: 18, 3: 13, 4: 9, 5: 6 };
  static WIDTH   = 14;
  static GAP     = 1.2;
  static DEPTH   = 16;
  static REACH   = 1.6;
  static STAGGER = 45;

  constructor({ stage, svg }, value) {
    super(svg, value, 3.9);
    this.span = PodiumFigure.RANKS.length * (PodiumFigure.WIDTH + PodiumFigure.GAP) - PodiumFigure.GAP;
    this._camera(this._extent(), 168);
    this._buildBase();
    this._buildSteps();
    this._start(stage, svg);
  }

  _extent() {
    const half = this.span / 2 + 6;
    const top  = PodiumFigure.HEIGHTS[1] + PodiumFigure.RANGE[2];
    return [[...this._onScreen(-half, -6), -4], [...this._onScreen(half, -6), -4], [...this._onScreen(-half, PodiumFigure.DEPTH + 6), -4], [...this._onScreen(half, PodiumFigure.DEPTH + 6), -4], [...this._onScreen(0, 0), top], [...this._onScreen(-half, 0), 16]];
  }

  _buildBase() {
    const half  = this.span / 2 + 6;
    const ring  = this._screenBox(-half, -6, half, PodiumFigure.DEPTH + 6, 6);
    const inner = this._screenBox(-half + 2.2, -3.8, half - 2.2, PodiumFigure.DEPTH + 3.8, 4);
    HL.put(HL.solid(this.g), HL.prism(this.P, this.front, ring, inner, -4, 0));
  }

  _buildSteps() {
    const pitch = PodiumFigure.WIDTH + PodiumFigure.GAP;
    this.steps  = PodiumFigure.RANKS.map((rank, k) => {
      const r0    = -this.span / 2 + k * pitch;
      const r1    = r0 + PodiumFigure.WIDTH;
      const group = HL.mk("g", {}, this.g);
      const el    = HL.solid(group);
      const dots  = Array.from({ length: rank }, (_, j) => ({ at: this._onScreen((r0 + r1) / 2 + (j - (rank - 1) / 2) * 2.2, PodiumFigure.DEPTH / 2), el: HL.flatDot(group, this.C, 0.8, "dot m") }));
      el.sil.classList.toggle("hi", rank === 1);
      return { k, rank, el, dots, h: PodiumFigure.HEIGHTS[rank], ring: this._screenBox(r0, 0, r1, PodiumFigure.DEPTH, 2), inner: this._screenBox(r0 + 1, 1, r1 - 1, PodiumFigure.DEPTH - 1, 1.2), tw: HL.tween(0), drawn: NaN, restX: this.P(...this._onScreen((r0 + r1) / 2, PodiumFigure.DEPTH / 2), 0)[0] };
    });
  }

  _tick(dt, now) {
    return this._advance(this.steps, now);
  }

  _draw(step, lift) {
    HL.put(step.el, HL.prism(this.P, this.front, step.ring, step.inner, 0, step.h + lift));
    for (const dot of step.dots) HL.place(dot.el, this.P(dot.at[0], dot.at[1], step.h + lift));
  }

  _move(p) {
    this._choose(HairlineFigureBase.nearest(this.steps.map((step) => step.restX), p[0]));
  }

  _retarget(now) {
    const anchor = this.chosen === null ? 2 : this.chosen;
    for (const step of this.steps) {
      const distance = Math.abs(step.k - anchor);
      const reach    = this.chosen === null ? 0 : Math.max(0, 1 - distance / PodiumFigure.REACH) ** 2;
      HL.tset(step.tw, this.amount * reach, now, distance * PodiumFigure.STAGGER);
      step.el.sil.classList.toggle("hi", step.k === anchor);
      for (const dot of step.dots) dot.el.setAttribute("class", step.k === anchor ? "dot" : "dot m");
    }
    this.loop.wake();
  }
}

class MetricTilesFigure extends HairlineFigureBase {
  static RANGE     = [4, 8, 13];
  static COLS      = 8;
  static ROWS      = 6;
  static CELL      = 11;
  static FOOT      = 9.6;
  static SEAM      = 3;
  static REST      = [5, 2];
  static REST_LIFT = 0.4;
  static STAGGER   = 45;

  constructor({ stage, svg }, value) {
    super(svg, value, 2.55);
    this.width = MetricTilesFigure.COLS * MetricTilesFigure.CELL;
    this.depth = MetricTilesFigure.ROWS * MetricTilesFigure.CELL;
    this._camera(this._extent(), 168);
    this._plinth(-3, -3, this.width + 3, this.depth + 3, 6, 4);
    this._buildTiles();
    this._start(stage, svg);
  }

  _metric(i, j) {
    const u = i / (MetricTilesFigure.COLS - 1);
    const v = j / (MetricTilesFigure.ROWS - 1);
    return 1.5 + 11 * Math.exp(-((u - 0.7) ** 2 + (v - 0.35) ** 2) / 0.05) + 4.5 * Math.exp(-((u - 0.2) ** 2 + (v - 0.75) ** 2) / 0.08) + (i === MetricTilesFigure.SEAM ? 2.4 : 0);
  }

  _extent() {
    const top = 16 + MetricTilesFigure.RANGE[2];
    return [[-3, -3, -4], [this.width + 3, this.depth + 3, -4], [this.width + 3, -3, -4], [-3, this.depth + 3, -4], [0, 0, top], [this.width, 0, top]];
  }

  _buildTiles() {
    const inset = (MetricTilesFigure.CELL - MetricTilesFigure.FOOT) / 2;
    const cells = [];
    for (let i = 0; i < MetricTilesFigure.COLS; i++) for (let j = 0; j < MetricTilesFigure.ROWS; j++) cells.push([i, j]);
    cells.sort((a, b) => a[0] + a[1] - (b[0] + b[1]));
    this.tiles = cells.map(([i, j]) => {
      const x0            = i * MetricTilesFigure.CELL + inset;
      const y0            = j * MetricTilesFigure.CELL + inset;
      const [ring, inner] = HL.rings(x0, y0, x0 + MetricTilesFigure.FOOT, y0 + MetricTilesFigure.FOOT, 1.8, 0.7);
      const h             = this._metric(i, j);
      const el            = HL.solid(this.g);
      return { i, j, h, ring, inner, el, tw: HL.tween(0), drawn: NaN, hull: HL.hull(HL.ringAt(this.P, ring, 0).concat(HL.ringAt(this.P, ring, h))) };
    });
    this.byCell = new Map(this.tiles.map((tile) => [`${tile.i},${tile.j}`, tile]));
    this._lift(this.byCell.get(MetricTilesFigure.REST.join(",")), this.amount * MetricTilesFigure.REST_LIFT, 0);
  }

  _lift(centre, amount, now) {
    for (const tile of this.tiles) {
      const ring = Math.max(Math.abs(tile.i - centre.i), Math.abs(tile.j - centre.j));
      HL.tset(tile.tw, ring === 0 ? amount : ring === 1 ? amount * 0.55 : 0, now, ring * MetricTilesFigure.STAGGER);
      tile.el.sil.classList.toggle("hi", ring === 0);
    }
  }

  _tick(dt, now) {
    return this._advance(this.tiles, now);
  }

  _draw(tile, lift) {
    HL.put(tile.el, HL.prism(this.P, this.front, tile.ring, tile.inner, 0, tile.h + lift));
  }

  _move(p) {
    for (let k = this.tiles.length - 1; k >= 0; k--) {
      if (HairlineGeometry.inside(this.tiles[k].hull, p)) return this._choose(this.tiles[k]);
    }
    const [x, y] = HL.unproj(this.C, p[0], p[1], 0);
    this._choose(this.byCell.get(`${Math.floor(x / MetricTilesFigure.CELL)},${Math.floor(y / MetricTilesFigure.CELL)}`) || null);
  }

  _retarget(now) {
    if (this.chosen === null) this._lift(this.byCell.get(MetricTilesFigure.REST.join(",")), this.amount * MetricTilesFigure.REST_LIFT, now);
    else this._lift(this.chosen, this.amount, now);
    this.loop.wake();
  }
}

class TransectFigure extends HairlineFigureBase {
  static RANGE     = [6, 11, 18];
  static COLUMNS   = 9;
  static PITCH     = 13;
  static BINS      = 7;
  static BIN       = 4;
  static DISC      = 2;
  static REACH     = 1.6;
  static STAGGER   = 45;
  static REST      = 5;
  static REST_PULL = 0.45;

  constructor({ stage, svg }, value) {
    super(svg, value, 2.55);
    this.length = (TransectFigure.COLUMNS - 1) * TransectFigure.PITCH;
    this._camera(this._extent(), 168);
    this._plinth(-9, -9, this.length + 9, 9 + TransectFigure.RANGE[2], 7, 4);
    HL.mk("path", { class: "dash nf", d: HL.seg(this.P(-5, 0, 0), this.P(this.length + 5, 0, 0)) }, this.g);
    this._buildColumns();
    this._start(stage, svg);
  }

  _extent() {
    const far = 9 + TransectFigure.RANGE[2];
    const top = TransectFigure.BINS * TransectFigure.BIN;
    return [[-9, -9, -4], [this.length + 9, far, -4], [this.length + 9, -9, -4], [-9, far, -4], [0, 0, top], [this.length, 0, top]];
  }

  _radius(bin, canopy) {
    return 1.3 + 4.4 * Math.exp(-((bin / 0.8) ** 2)) + 4.2 * Math.exp(-(((bin - canopy) / 1.2) ** 2));
  }

  _buildColumns() {
    this.columns = Array.from({ length: TransectFigure.COLUMNS }, (_, k) => {
      const x      = k * TransectFigure.PITCH;
      const canopy = 3.2 + 1.8 * Math.sin((k / (TransectFigure.COLUMNS - 1)) * Math.PI);
      const group  = HL.mk("g", {}, this.g);
      const lit    = k === TransectFigure.REST;
      const discs  = Array.from({ length: TransectFigure.BINS }, (_, b) => {
        const r  = this._radius(b, canopy);
        const el = HL.solid(group);
        el.sil.classList.toggle("hi", lit);
        return { b, el, ring: HL.circ(r, 40).map((q) => ({ ...q, u: q.u + x })), inner: HL.circ(Math.max(0.4, r - 0.8), 40).map((q) => ({ ...q, u: q.u + x })) };
      });
      return { k, discs, tw: HL.tween(lit ? this.amount * TransectFigure.REST_PULL : 0), drawn: NaN, restX: this.P(x, 0, 0)[0] };
    });
  }

  _tick(dt, now) {
    return this._advance(this.columns, now);
  }

  _draw(column, out) {
    const moved = this._shifted(0, out, 0);
    for (const disc of column.discs) HL.put(disc.el, HL.prism(moved, this.front, disc.ring, disc.inner, disc.b * TransectFigure.BIN, disc.b * TransectFigure.BIN + TransectFigure.DISC));
  }

  _move(p) {
    this._choose(HairlineFigureBase.nearest(this.columns.map((column) => column.restX), p[0]));
  }

  _retarget(now) {
    const anchor = this.chosen === null ? TransectFigure.REST : this.chosen;
    for (const column of this.columns) {
      const distance = Math.abs(column.k - anchor);
      const reach    = Math.max(0, 1 - distance / TransectFigure.REACH) ** 2;
      const target   = this.chosen === null ? (column.k === TransectFigure.REST ? this.amount * TransectFigure.REST_PULL : 0) : this.amount * reach;
      HL.tset(column.tw, target, now, distance * TransectFigure.STAGGER);
      for (const disc of column.discs) disc.el.sil.classList.toggle("hi", column.k === anchor);
    }
    this.loop.wake();
  }
}

class FilmStripFigure extends HairlineFigureBase {
  static RANGE     = [5, 9, 15];
  static FRAMES    = 5;
  static WIDTH     = 15;
  static GAP       = 2.4;
  static THICK     = 1.6;
  static HEIGHT    = 21;
  static REACH     = 1.6;
  static STAGGER   = 45;
  static LATEST    = FilmStripFigure.FRAMES - 1;
  static REST_LIFT = 0.45;

  constructor({ stage, svg }, value) {
    super(svg, value, 3.9);
    this.span = FilmStripFigure.FRAMES * (FilmStripFigure.WIDTH + FilmStripFigure.GAP) - FilmStripFigure.GAP;
    this._camera(this._extent(), 168);
    this._buildRail();
    this._buildFrames();
    this._start(stage, svg);
  }

  _extent() {
    const half = this.span / 2 + 5;
    const top  = FilmStripFigure.HEIGHT + FilmStripFigure.RANGE[2];
    return [[...this._onScreen(-half, -6), -3], [...this._onScreen(half, -6), -3], [...this._onScreen(-half, 7), -3], [...this._onScreen(half, 7), -3], [...this._onScreen(-half, 0), top], [...this._onScreen(half, 0), top]];
  }

  _buildRail() {
    const half = this.span / 2 + 5;
    HL.put(HL.solid(this.g), HL.prism(this.P, this.front, this._screenBox(-half, -6, half, 7, 3), this._screenBox(-half + 1.6, -4.4, half - 1.6, 5.4, 2), -3, 0));
    const line = (r) => this.P(...this._onScreen(r, 4), 0);
    HL.mk("path", { class: "dash nf", d: HL.seg(line(-this.span / 2), line(this.span / 2)) }, this.g);
    this.ticks = Array.from({ length: FilmStripFigure.FRAMES }, (_, k) => {
      const tick = HL.flatDot(this.g, this.C, 0.8, "dot off");
      HL.place(tick, line(-this.span / 2 + k * (FilmStripFigure.WIDTH + FilmStripFigure.GAP) + FilmStripFigure.WIDTH / 2));
      return tick;
    });
  }

  _buildFrames() {
    const pitch = FilmStripFigure.WIDTH + FilmStripFigure.GAP;
    const t     = FilmStripFigure.THICK / 2;
    this.frames = Array.from({ length: FilmStripFigure.FRAMES }, (_, k) => {
      const r0    = -this.span / 2 + k * pitch;
      const r1    = r0 + FilmStripFigure.WIDTH;
      const group = HL.mk("g", {}, this.g);
      const el    = HL.solid(group);
      const face  = HL.mk("path", { class: "nf lo" }, group);
      const lit   = k === FilmStripFigure.LATEST;
      el.sil.classList.toggle("hi", lit);
      return { k, r0, r1, el, face, ring: this._screenBox(r0, -t, r1, t, 0.5), sharp: 0.35 + (0.65 * k) / (FilmStripFigure.FRAMES - 1), tw: HL.tween(lit ? this.amount * FilmStripFigure.REST_LIFT : 0), drawn: NaN, restX: this.P(...this._onScreen((r0 + r1) / 2, 0), 0)[0] };
    });
  }

  _tick(dt, now) {
    return this._advance(this.frames, now);
  }

  _draw(frame, lift) {
    const z0   = 1 + lift;
    const at   = (r, z) => this.P(...this._onScreen(r, FilmStripFigure.THICK / 2), z);
    const edge = [[frame.r0 + 1.4, z0 + 1.4], [frame.r1 - 1.4, z0 + 1.4], [frame.r1 - 1.4, z0 + FilmStripFigure.HEIGHT - 1.4], [frame.r0 + 1.4, z0 + FilmStripFigure.HEIGHT - 1.4]];
    const h     = FilmStripFigure.HEIGHT;
    const curve = Array.from({ length: 17 }, (_, i) => {
      const s = i / 16;
      const r = HL.lerp(frame.r0 + 2.4, frame.r1 - 2.4, s);
      return at(r, z0 + h * (0.19 + 0.23 * Math.exp(-(((s - 0.12) / 0.09) ** 2)) + 0.5 * frame.sharp * Math.exp(-(((s - 0.62) / (0.3 - 0.18 * frame.sharp)) ** 2))));
    });
    HL.put(frame.el, HL.prism(this.P, this.front, frame.ring, null, z0, z0 + FilmStripFigure.HEIGHT));
    frame.face.setAttribute("d", HL.poly(edge.map(([r, z]) => at(r, z))) + HL.open(curve));
  }

  _move(p) {
    this._choose(HairlineFigureBase.nearest(this.frames.map((frame) => frame.restX), p[0]));
  }

  _retarget(now) {
    const anchor = this.chosen === null ? FilmStripFigure.LATEST : this.chosen;
    for (const frame of this.frames) {
      const distance = Math.abs(frame.k - anchor);
      const reach    = Math.max(0, 1 - distance / FilmStripFigure.REACH) ** 2;
      const target   = this.chosen === null ? (frame.k === FilmStripFigure.LATEST ? this.amount * FilmStripFigure.REST_LIFT : 0) : this.amount * reach;
      HL.tset(frame.tw, target, now, distance * FilmStripFigure.STAGGER);
      frame.el.sil.classList.toggle("hi", frame.k === anchor);
      this.ticks[frame.k].setAttribute("class", frame.k === anchor ? "dot m" : "dot off");
    }
    this.loop.wake();
  }
}

class ReportTrayFigure extends HairlineFigureBase {
  static RANGE     = [8, 14, 22];
  static SHEETS    = 7;
  static WIDTH     = 30;
  static DEPTH     = 22;
  static THICK     = 0.9;
  static STEP      = 2.4;
  static STAGGER   = 45;
  static REST_PULL = 0.4;

  constructor({ stage, svg }, value) {
    super(svg, value, 5.0);
    this.top = ReportTrayFigure.SHEETS - 1;
    this._camera(this._extent(), 166);
    this._plinth(-6, -6, ReportTrayFigure.WIDTH + 6, ReportTrayFigure.DEPTH + 6, 5, 3);
    this._buildSheets();
    this._start(stage, svg);
  }

  _extent() {
    const w   = ReportTrayFigure.WIDTH;
    const d   = ReportTrayFigure.DEPTH;
    const top = 1 + ReportTrayFigure.SHEETS * ReportTrayFigure.STEP + 2;
    return [[-6, -6, -3], [w + 6, d + 6, -3], [w + 6, -6, -3], [-6, d + 6, -3], [0, 0, top], [w + ReportTrayFigure.RANGE[2], d / 2, top * 0.6]];
  }

  _buildSheets() {
    this.sheets = Array.from({ length: ReportTrayFigure.SHEETS }, (_, k) => {
      const x0            = 0.9 * Math.sin(k * 2.3);
      const y0            = 0.9 * Math.cos(k * 1.7);
      const z0            = 1 + k * ReportTrayFigure.STEP;
      const [ring, inner] = HL.rings(x0, y0, x0 + ReportTrayFigure.WIDTH, y0 + ReportTrayFigure.DEPTH, 1.2, 0.5);
      const group         = HL.mk("g", {}, this.g);
      const el            = HL.solid(group);
      const mark          = HL.mk("path", { class: "nf lo" }, group);
      const lit           = k === this.top;
      el.sil.classList.toggle("hi", lit);
      return { k, x0, y0, z0, ring, inner, el, mark, tw: HL.tween(lit ? this.amount * ReportTrayFigure.REST_PULL : 0), drawn: NaN, restY: this.P(x0 + ReportTrayFigure.WIDTH / 2, y0 + ReportTrayFigure.DEPTH / 2, z0)[1] };
    });
  }

  _tick(dt, now) {
    return this._advance(this.sheets, now);
  }

  _draw(sheet, out) {
    const moved = this._shifted(out, 0, 0);
    const z     = sheet.z0 + ReportTrayFigure.THICK;
    const axes  = [[sheet.x0 + 5, sheet.y0 + 4], [sheet.x0 + 5, sheet.y0 + ReportTrayFigure.DEPTH - 4], [sheet.x0 + ReportTrayFigure.WIDTH - 4, sheet.y0 + ReportTrayFigure.DEPTH - 4]];
    const curve = Array.from({ length: 11 }, (_, i) => {
      const s = i / 10;
      return [sheet.x0 + 6 + s * (ReportTrayFigure.WIDTH - 11), sheet.y0 + ReportTrayFigure.DEPTH - 5 - 11 * Math.exp(-(((s - 0.3 - 0.06 * sheet.k) / 0.22) ** 2))];
    });
    HL.put(sheet.el, HL.prism(moved, this.front, sheet.ring, sheet.inner, sheet.z0, z));
    sheet.mark.setAttribute("d", HL.open(axes.map(([x, y]) => moved(x, y, z))) + HL.open(curve.map(([x, y]) => moved(x, y, z))));
  }

  _move(p) {
    this._choose(HairlineFigureBase.nearest(this.sheets.map((sheet) => sheet.restY), p[1]));
  }

  _retarget(now) {
    const anchor = this.chosen === null ? this.top : this.chosen;
    for (const sheet of this.sheets) {
      const distance = Math.abs(sheet.k - anchor);
      const target   = this.chosen === null ? (sheet.k === this.top ? this.amount * ReportTrayFigure.REST_PULL : 0) : sheet.k === anchor ? this.amount : 0;
      HL.tset(sheet.tw, target, now, distance * ReportTrayFigure.STAGGER);
      sheet.el.sil.classList.toggle("hi", sheet.k === anchor);
    }
    this.loop.wake();
  }
}

class UnrolledFigure extends HairlineFigureBase {
  static RANGE   = [5, 9, 15];
  static STAGES  = 7;
  static SIZE    = 8;
  static GAP     = 3.2;
  static BASE    = 7.5;
  static CLIMB   = 2.1;
  static PENDING = 3;
  static STAGGER = 70;
  static REST    = 3;

  constructor({ stage, svg }, value) {
    super(svg, value, 3.9);
    this.span    = UnrolledFigure.STAGES * (UnrolledFigure.SIZE + UnrolledFigure.GAP) - UnrolledFigure.GAP;
    this.reached = UnrolledFigure.REST;
    this._camera(this._extent(), 168);
    this._buildBase();
    this._buildStages();
    this._start(stage, svg);
  }

  _height(k, amount) {
    return UnrolledFigure.BASE + UnrolledFigure.CLIMB * amount * (1 - Math.exp(-k / 1.8));
  }

  _extent() {
    const half = this.span / 2 + 6;
    const top  = this._height(UnrolledFigure.STAGES, UnrolledFigure.RANGE[2]);
    return [[...this._onScreen(-half, -9), -4], [...this._onScreen(half, -9), -4], [...this._onScreen(-half, 9), -4], [...this._onScreen(half, 9), -4], [...this._onScreen(half, 0), top], [...this._onScreen(-half, 0), UnrolledFigure.BASE]];
  }

  _buildBase() {
    const half = this.span / 2 + 6;
    HL.put(HL.solid(this.g), HL.prism(this.P, this.front, this._screenBox(-half, -9, half, 9, 5), this._screenBox(-half + 2.2, -6.8, half - 2.2, 6.8, 3), -4, 0));
    const line = (r) => this.P(...this._onScreen(r, 0), 0);
    HL.mk("path", { class: "dash nf", d: HL.seg(line(-this.span / 2), line(this.span / 2)) }, this.g);
  }

  _buildStages() {
    const pitch = UnrolledFigure.SIZE + UnrolledFigure.GAP;
    const half  = UnrolledFigure.SIZE / 2;
    this.stages = Array.from({ length: UnrolledFigure.STAGES }, (_, k) => {
      const centre = -this.span / 2 + half + k * pitch;
      const el     = HL.solid(this.g);
      el.sil.classList.toggle("hi", k === this.reached);
      return { k, el, ring: this._screenBox(centre - half, -half, centre + half, half, 2), inner: this._screenBox(centre - half + 0.8, -half + 0.8, centre + half - 0.8, half - 0.8, 1.2), tw: HL.tween(this._target(k)), drawn: NaN, restX: this.P(...this._onScreen(centre, 0), 0)[0] };
    });
  }

  _target(k) {
    return k <= this.reached ? this._height(k, this.amount) : UnrolledFigure.PENDING;
  }

  _tick(dt, now) {
    return this._advance(this.stages, now);
  }

  _draw(stage, h) {
    HL.put(stage.el, HL.prism(this.P, this.front, stage.ring, stage.inner, 0, h));
  }

  _move(p) {
    this._choose(HairlineFigureBase.nearest(this.stages.map((stage) => stage.restX), p[0]));
  }

  _retarget(now) {
    const before = this.reached;
    this.reached = this.chosen === null ? UnrolledFigure.REST : this.chosen;
    for (const stage of this.stages) {
      const grows   = stage.k > before && stage.k <= this.reached;
      const shrinks = stage.k > this.reached && stage.k <= before;
      const delay   = grows ? (stage.k - before - 1) * UnrolledFigure.STAGGER : shrinks ? (before - stage.k) * UnrolledFigure.STAGGER : 0;
      HL.tset(stage.tw, this._target(stage.k), now, delay);
      stage.el.sil.classList.toggle("hi", stage.k === this.reached);
    }
    this.loop.wake();
  }
}

class JepaMasksFigure extends HairlineFigureBase {
  static RANGE  = [5, 9, 15];
  static GRID   = 6;
  static CELL   = 12;
  static FOOT   = 10.4;
  static HEIGHT = 4;
  static MASKED = ["0,4", "1,4", "1,5", "4,0", "5,1", "3,5"];
  static REST   = [3, 1];

  constructor({ stage, svg }, value) {
    super(svg, value, 2.75);
    this.span = JepaMasksFigure.GRID * JepaMasksFigure.CELL;
    this._camera(this._extent(), 168);
    this._plinth(-4, -4, this.span + 4, this.span + 4, 7, 4);
    this._buildPatches();
    this._start(stage, svg);
  }

  _extent() {
    const top = JepaMasksFigure.HEIGHT + JepaMasksFigure.RANGE[2];
    return [[-4, -4, -4], [this.span + 4, this.span + 4, -4], [this.span + 4, -4, -4], [-4, this.span + 4, -4], [0, 0, top], [this.span, 0, top]];
  }

  _buildPatches() {
    const inset = (JepaMasksFigure.CELL - JepaMasksFigure.FOOT) / 2;
    const cells = [];
    for (let i = 0; i < JepaMasksFigure.GRID; i++) for (let j = 0; j < JepaMasksFigure.GRID; j++) cells.push([i, j]);
    cells.sort((a, b) => a[0] + a[1] - (b[0] + b[1]));
    this.patches = cells.map(([i, j]) => {
      const x0            = i * JepaMasksFigure.CELL + inset;
      const y0            = j * JepaMasksFigure.CELL + inset;
      const [ring, inner] = HL.rings(x0, y0, x0 + JepaMasksFigure.FOOT, y0 + JepaMasksFigure.FOOT, 2, 0.8);
      const masked        = JepaMasksFigure.MASKED.includes(`${i},${j}`);
      return { i, j, ring, inner, h: masked ? 0.8 : JepaMasksFigure.HEIGHT, el: HL.solid(this.g), tw: HL.tween(0), drawn: NaN };
    });
    this._place(JepaMasksFigure.REST, this.amount * 0.4, 0);
  }

  _place(corner, lift, now) {
    for (const patch of this.patches) {
      const inside = patch.i >= corner[0] && patch.i <= corner[0] + 1 && patch.j >= corner[1] && patch.j <= corner[1] + 1;
      HL.tset(patch.tw, inside ? lift : 0, now, inside ? ((patch.i - corner[0]) + (patch.j - corner[1])) * 50 : 0);
      patch.el.sil.classList.toggle("hi", inside);
    }
  }

  _tick(dt, now) {
    return this._advance(this.patches, now);
  }

  _draw(patch, lift) {
    HL.put(patch.el, HL.prism(this.P, this.front, patch.ring, patch.inner, 0, patch.h + lift));
  }

  _move(p) {
    const [x, y] = HL.unproj(this.C, p[0], p[1], JepaMasksFigure.HEIGHT);
    const i      = HL.clamp(Math.round(x / JepaMasksFigure.CELL - 1), 0, JepaMasksFigure.GRID - 2);
    const j      = HL.clamp(Math.round(y / JepaMasksFigure.CELL - 1), 0, JepaMasksFigure.GRID - 2);
    this._choose(i * JepaMasksFigure.GRID + j);
  }

  _retarget(now) {
    if (this.chosen === null) this._place(JepaMasksFigure.REST, this.amount * 0.4, now);
    else this._place([Math.floor(this.chosen / JepaMasksFigure.GRID), this.chosen % JepaMasksFigure.GRID], this.amount, now);
    this.loop.wake();
  }
}

class CheckpointShelfFigure extends HairlineFigureBase {
  static RANGE     = [6, 11, 18];
  static HEIGHTS   = [18, 21, 17, 22, 19, 24, 20, 23];
  static WIDTH     = 4.4;
  static GAP       = 1.4;
  static DEPTH     = 14;
  static BEST      = 5;
  static REACH     = 1.5;
  static STAGGER   = 45;
  static REST_PULL = 0.45;

  constructor({ stage, svg }, value) {
    super(svg, value, 3.4);
    this.length = CheckpointShelfFigure.HEIGHTS.length * (CheckpointShelfFigure.WIDTH + CheckpointShelfFigure.GAP) - CheckpointShelfFigure.GAP;
    this._camera(this._extent(), 166);
    this._plinth(-4, -4, this.length + 4, CheckpointShelfFigure.DEPTH + 4 + CheckpointShelfFigure.RANGE[2], 4, 3);
    HL.put(HL.solid(this.g), HairlineGeometry.backPlate(this.P, -2, this.length + 2, 30, -4, 2));
    this._buildCartridges();
    this._start(stage, svg);
  }

  _extent() {
    const far = CheckpointShelfFigure.DEPTH + 4 + CheckpointShelfFigure.RANGE[2];
    return [[-4, -4, -3], [this.length + 4, -4, -3], [-4, far, -3], [this.length + 4, far, -3], [0, -4, 30], [this.length, -4, 30]];
  }

  _buildCartridges() {
    this.cartridges = CheckpointShelfFigure.HEIGHTS.map((h, k) => {
      const x0            = k * (CheckpointShelfFigure.WIDTH + CheckpointShelfFigure.GAP);
      const [ring, inner] = HL.rings(x0, 0, x0 + CheckpointShelfFigure.WIDTH, CheckpointShelfFigure.DEPTH, 1.2, 0.5);
      const group         = HL.mk("g", {}, this.g);
      const el            = HL.solid(group);
      const notch         = HL.flatDot(group, this.C, 0.8, "dot off");
      const best          = k === CheckpointShelfFigure.BEST;
      el.sil.classList.toggle("hi", best);
      if (best) notch.setAttribute("class", "dot");
      return { k, h, x0, ring, inner, el, notch, tw: HL.tween(best ? this.amount * CheckpointShelfFigure.REST_PULL : 0), drawn: NaN, restX: this.P(x0 + CheckpointShelfFigure.WIDTH / 2, CheckpointShelfFigure.DEPTH / 2, 0)[0] };
    });
  }

  _tick(dt, now) {
    return this._advance(this.cartridges, now);
  }

  _draw(cartridge, out) {
    const moved = this._shifted(0, out, 0);
    HL.put(cartridge.el, HL.prism(moved, this.front, cartridge.ring, cartridge.inner, 0, cartridge.h));
    HL.place(cartridge.notch, moved(cartridge.x0 + CheckpointShelfFigure.WIDTH / 2, CheckpointShelfFigure.DEPTH - 3, cartridge.h));
  }

  _move(p) {
    this._choose(HairlineFigureBase.nearest(this.cartridges.map((cartridge) => cartridge.restX), p[0]));
  }

  _retarget(now) {
    const anchor = this.chosen === null ? CheckpointShelfFigure.BEST : this.chosen;
    for (const cartridge of this.cartridges) {
      const distance = Math.abs(cartridge.k - anchor);
      const reach    = Math.max(0, 1 - distance / CheckpointShelfFigure.REACH) ** 2;
      const target   = this.chosen === null ? (cartridge.k === CheckpointShelfFigure.BEST ? this.amount * CheckpointShelfFigure.REST_PULL : 0) : this.amount * reach;
      HL.tset(cartridge.tw, target, now, distance * CheckpointShelfFigure.STAGGER);
      cartridge.el.sil.classList.toggle("hi", cartridge.k === anchor);
      cartridge.notch.setAttribute("class", cartridge.k === anchor ? "dot" : cartridge.k === CheckpointShelfFigure.BEST ? "dot m" : "dot off");
    }
    this.loop.wake();
  }
}

class LrDialFigure extends HairlineFigureBase {
  static RANGE   = [40, 90, 160];
  static DETENTS = 9;
  static SWEEP   = 270;
  static KNOB    = 16;
  static HEIGHT  = 9;
  static TICKS   = 24;
  static REST    = 3;

  constructor({ stage, svg }, value) {
    super(svg, value, 5.0);
    this._camera(this._extent(), 168);
    this._buildBase();
    this._buildKnob();
    this.turn  = HL.spring(this._angle(LrDialFigure.REST), { k: this.amount });
    this.drawn = NaN;
    this._start(stage, svg);
  }

  _angle(k) {
    return HL.rad(45 - LrDialFigure.SWEEP / 2 + (LrDialFigure.SWEEP * k) / (LrDialFigure.DETENTS - 1));
  }

  _extent() {
    const r = LrDialFigure.TICKS + 4;
    return [[-r, -r, -4], [r, r, -4], [r, -r, -4], [-r, r, -4], [0, 0, LrDialFigure.HEIGHT + 2]];
  }

  _buildBase() {
    const r = LrDialFigure.TICKS + 4;
    HL.put(HL.solid(this.g), HL.prism(this.P, this.front, HL.circ(r, 96), HL.circ(r - 2.2, 96), -4, 0));
    this.ticks = Array.from({ length: LrDialFigure.DETENTS }, (_, k) => {
      const a   = this._angle(k);
      const dot = HL.flatDot(this.g, this.C, 1.1, k === LrDialFigure.REST ? "dot" : k < LrDialFigure.REST ? "dot m" : "dot off");
      HL.place(dot, this.P(LrDialFigure.TICKS * Math.cos(a), LrDialFigure.TICKS * Math.sin(a), 0));
      return dot;
    });
  }

  _buildKnob() {
    HL.put(HL.solid(this.g), HL.prism(this.P, this.front, HL.circ(LrDialFigure.KNOB, 72), HL.circ(LrDialFigure.KNOB - 1.6, 72), 0, LrDialFigure.HEIGHT));
    this.needle = HL.mk("path", { class: "nf hi" }, this.g);
    this.detent = null;
  }

  _tick(dt) {
    const moving = HL.stepS(this.turn, dt);
    if (this.turn.x !== this.drawn) {
      this.drawn = this.turn.x;
      const a    = this.turn.x;
      const z    = LrDialFigure.HEIGHT;
      this.needle.setAttribute("d", HL.seg(this.P(3 * Math.cos(a), 3 * Math.sin(a), z), this.P((LrDialFigure.KNOB - 3) * Math.cos(a), (LrDialFigure.KNOB - 3) * Math.sin(a), z)));
    }
    return moving;
  }

  _move(p) {
    const [x, y] = HL.unproj(this.C, p[0], p[1], LrDialFigure.HEIGHT);
    if (Math.hypot(x, y) < 3) return;
    const a      = Math.atan2(y, x);
    const angles = Array.from({ length: LrDialFigure.DETENTS }, (_, k) => this._angle(k));
    const gap    = angles.map((b) => Math.abs(Math.atan2(Math.sin(a - b), Math.cos(a - b))));
    this._choose(HairlineFigureBase.nearest(gap, 0));
  }

  _retarget() {
    const k      = this.chosen === null ? LrDialFigure.REST : this.chosen;
    this.turn.k  = this.amount;
    this.turn.t  = this._angle(k);
    this.ticks.forEach((dot, i) => dot.setAttribute("class", i === k ? "dot" : i < k ? "dot m" : "dot off"));
    this.loop.wake();
  }
}

class ApertureFigure extends HairlineFigureBase {
  static RANGE   = [40, 100, 220];
  static LENGTH  = 100;
  static EDGE    = 4;
  static HEIGHT  = 40;
  static SCENE   = [14, 48];
  static TARGET  = [52, 31];
  static BEAM    = 15;
  static REST_X  = 0.4;

  constructor({ stage, svg }, value) {
    super(svg, value, 2.5);
    this._camera(this._extent(), 160);
    this._buildScene();
    this._buildTrack();
    this.along = HL.spring(ApertureFigure.LENGTH * ApertureFigure.REST_X, { k: this.amount });
    this.drawn = NaN;
    this._start(stage, svg);
  }

  _extent() {
    const [y0, y1] = ApertureFigure.SCENE;
    return [[0, -4, ApertureFigure.HEIGHT + 4], [ApertureFigure.LENGTH, -4, ApertureFigure.HEIGHT + 4], [0, y1, -3], [ApertureFigure.LENGTH, y1, -3], [0, y0, -3]];
  }

  _buildScene() {
    const [y0, y1]      = ApertureFigure.SCENE;
    const [ring, inner] = HL.rings(ApertureFigure.EDGE, y0, ApertureFigure.LENGTH - ApertureFigure.EDGE, y1, 6, 2);
    HL.put(HL.solid(this.g), HL.prism(this.P, this.front, ring, inner, -3, 0));
    this.beam   = HL.mk("path", { class: "dash nf" }, this.g);
    this.target = HL.flatDot(this.g, this.C, 1.8, "dot m");
    HL.place(this.target, this.P(...ApertureFigure.TARGET, 0));
  }

  _buildTrack() {
    const [ring, inner] = HL.rings(0, -1.5, ApertureFigure.LENGTH, 1.5, 1.3, 0.55);
    HL.put(HL.solid(this.g), HL.prism(this.P, this.front, ring, inner, ApertureFigure.HEIGHT - 1.5, ApertureFigure.HEIGHT + 1.5));
    const x  = ApertureFigure.TARGET[0];
    const sa = HL.rings(x - ApertureFigure.BEAM, -2.1, x + ApertureFigure.BEAM, 2.1, 1.6, 0.7);
    this.span = HL.solid(this.g);
    HL.put(this.span, HL.prism(this.P, this.front, sa[0], sa[1], ApertureFigure.HEIGHT - 2.1, ApertureFigure.HEIGHT + 2.1));
    this.craft      = HL.solid(this.g);
    this.craftRings = HL.rings(-6, -3.4, 6, 3.4, 2.6, 1.1);
  }

  _tick(dt) {
    const moving = HL.stepS(this.along, dt);
    if (this.along.x !== this.drawn) {
      this.drawn = this.along.x;
      this._drawPass(this.along.x);
    }
    return moving;
  }

  _drawPass(x) {
    const [ring, inner] = this.craftRings;
    const z             = ApertureFigure.HEIGHT;
    const [y0, y1]      = ApertureFigure.SCENE;
    const near          = (y0 + y1) / 2;
    const corners       = [[x - ApertureFigure.BEAM, near - 9], [x + ApertureFigure.BEAM, near - 9], [x + ApertureFigure.BEAM, near + 9], [x - ApertureFigure.BEAM, near + 9]];
    const sees          = Math.abs(x - ApertureFigure.TARGET[0]) <= ApertureFigure.BEAM;
    HL.put(this.craft, HL.prism(this._shifted(x, 0, 0), this.front, ring, inner, z - 2.6, z + 2.6));
    this.beam.setAttribute("d", HL.poly(corners.map(([cx, cy]) => this.P(cx, cy, 0))) + HL.seg(this.P(x, 0, z - 2.6), this.P(x - ApertureFigure.BEAM, near - 9, 0)) + HL.seg(this.P(x, 0, z - 2.6), this.P(x + ApertureFigure.BEAM, near - 9, 0)));
    this.target.setAttribute("class", sees ? "dot" : "dot m");
    this.span.sil.classList.toggle("hi", sees);
    this.craft.sil.classList.toggle("hi", !sees);
  }

  _move(p) {
    const a = this.P(0, 0, ApertureFigure.HEIGHT);
    const b = this.P(ApertureFigure.LENGTH, 0, ApertureFigure.HEIGHT);
    const t = ((p[0] - a[0]) * (b[0] - a[0]) + (p[1] - a[1]) * (b[1] - a[1])) / ((b[0] - a[0]) ** 2 + (b[1] - a[1]) ** 2);
    const lo     = ApertureFigure.EDGE + ApertureFigure.BEAM;
    this.along.t = HL.clamp(t * ApertureFigure.LENGTH, lo, ApertureFigure.LENGTH - lo);
    this.loop.wake();
  }

  _leave() {
    this.along.t = ApertureFigure.LENGTH * ApertureFigure.REST_X;
    this.loop.wake();
  }

  _retarget() {
    this.along.k = this.amount;
    this.loop.wake();
  }
}

class SlcStackFigure extends HairlineFigureBase {
  static RANGE     = [6, 11, 18];
  static PLATES    = 8;
  static HALF      = 22;
  static THICK     = 1.2;
  static STEP      = 4.5;
  static PRIMARY   = 1;
  static STAGGER   = 40;
  static REST_OPEN = 0.45;

  constructor({ stage, svg }, value) {
    super(svg, value, 2.9);
    this._camera(this._extent(), 168);
    this._plinth(-28, -28, 28, 28, 7, 4);
    this._buildPlates();
    this._start(stage, svg);
  }

  _extent() {
    const top = SlcStackFigure.PLATES * SlcStackFigure.STEP + SlcStackFigure.RANGE[2];
    return [[-28, -28, -4], [28, 28, -4], [28, -28, -4], [-28, 28, -4], [0, 0, top], [22, -22, top], [-22, 22, top]];
  }

  _buildPlates() {
    const half = SlcStackFigure.HALF;
    this.plates = Array.from({ length: SlcStackFigure.PLATES }, (_, k) => {
      const [ring, inner] = HL.rings(-half, -half, half, half, 3, 1.2);
      const group         = HL.mk("g", {}, this.g);
      const el            = HL.solid(group);
      const fringes       = HL.mk("path", { class: "nf lo" }, group);
      const lit           = k === SlcStackFigure.PRIMARY;
      const z0            = 1 + k * SlcStackFigure.STEP;
      el.sil.classList.toggle("hi", lit);
      return { k, ring, inner, el, fringes, z0, spacing: 20 / (k + 2), tw: HL.tween(k > SlcStackFigure.PRIMARY ? this.amount * SlcStackFigure.REST_OPEN : 0), drawn: NaN, restY: this.P(0, 0, z0)[1] };
    });
  }

  _tick(dt, now) {
    return this._advance(this.plates, now);
  }

  _draw(plate, lift) {
    const z     = plate.z0 + lift + SlcStackFigure.THICK;
    const edge  = SlcStackFigure.HALF - 4;
    const lines = [];
    for (let x = -edge + plate.spacing / 2; x < edge; x += plate.spacing) lines.push(HL.seg(this.P(x, -edge, z), this.P(x, edge, z)));
    HL.put(plate.el, HL.prism(this.P, this.front, plate.ring, plate.inner, plate.z0 + lift, z));
    plate.fringes.setAttribute("d", lines.join(""));
  }

  _move(p) {
    this._choose(HairlineFigureBase.nearest(this.plates.map((plate) => plate.restY), p[1]));
  }

  _retarget(now) {
    const split = this.chosen === null ? SlcStackFigure.PRIMARY : this.chosen;
    const gap   = this.chosen === null ? this.amount * SlcStackFigure.REST_OPEN : this.amount;
    for (const plate of this.plates) {
      HL.tset(plate.tw, plate.k > split ? gap : 0, now, Math.max(0, plate.k - split - 1) * SlcStackFigure.STAGGER);
      plate.el.sil.classList.toggle("hi", plate.k === split);
    }
    this.loop.wake();
  }
}

class ThresholdFigure extends HairlineFigureBase {
  static RANGE = [40, 100, 220];
  static COLS  = 8;
  static ROWS  = 6;
  static CELL  = 10;
  static FOOT  = 7.6;
  static FLOOR = 6;
  static REST  = 0.45;

  constructor({ stage, svg }, value) {
    super(svg, value, 2.7);
    this.width   = ThresholdFigure.COLS * ThresholdFigure.CELL;
    this.depth   = ThresholdFigure.ROWS * ThresholdFigure.CELL;
    this.pillars = this._layout();
    this.peak    = Math.max(...this.pillars.map((pillar) => pillar.h));
    this._camera(this._extent(), 168);
    this._plinth(-4, -4, this.width + 4, this.depth + 4, 7, 4);
    this.plane = HL.mk("path", { class: "dash nf" }, this.g);
    this._buildPillars();
    this.level = HL.spring(this.peak * ThresholdFigure.REST, { k: this.amount });
    this.drawn = NaN;
    this._start(stage, svg);
  }

  _layout() {
    const pillars = [];
    for (let i = 0; i < ThresholdFigure.COLS; i++) {
      for (let j = 0; j < ThresholdFigure.ROWS; j++) {
        const u = i / (ThresholdFigure.COLS - 1);
        const v = j / (ThresholdFigure.ROWS - 1);
        const h = 2.5 + 2 * (0.5 + 0.5 * Math.sin(i * 4.1 + j * 2.7)) + 24 * Math.exp(-((u - 0.68) ** 2 + (v - 0.4) ** 2) / 0.04) + 13 * Math.exp(-((u - 0.22) ** 2 + (v - 0.72) ** 2) / 0.03);
        pillars.push({ i, j, h });
      }
    }
    return pillars.sort((a, b) => a.i + a.j - (b.i + b.j));
  }

  _extent() {
    return [[-4, -4, -4], [this.width + 4, this.depth + 4, -4], [this.width + 4, -4, -4], [-4, this.depth + 4, -4], [0, 0, this.peak + 2], [this.width, 0, this.peak + 2]];
  }

  _buildPillars() {
    const inset = (ThresholdFigure.CELL - ThresholdFigure.FOOT) / 2;
    for (const pillar of this.pillars) {
      const x0            = pillar.i * ThresholdFigure.CELL + inset;
      const y0            = pillar.j * ThresholdFigure.CELL + inset;
      const [ring, inner] = HL.rings(x0, y0, x0 + ThresholdFigure.FOOT, y0 + ThresholdFigure.FOOT, 1.8, 0.7);
      pillar.ring         = ring;
      pillar.inner        = inner;
      pillar.el           = HL.solid(this.g);
      pillar.cap          = HL.solid(this.g);
      pillar.above        = false;
      pillar.cap.sil.classList.add("hi");
      HL.put(pillar.el, HL.prism(this.P, this.front, ring, inner, 0, pillar.h));
    }
    this.top    = this.P(this.width / 2, this.depth / 2, this.peak)[1];
    this.bottom = this.P(this.width / 2, this.depth / 2, 0)[1];
  }

  _tick(dt) {
    const moving = HL.stepS(this.level, dt);
    if (this.level.x !== this.drawn) {
      this.drawn = this.level.x;
      this._drawLevel(this.level.x);
    }
    return moving;
  }

  _drawLevel(z) {
    const corners = [[-2, -2], [this.width + 2, -2], [this.width + 2, this.depth + 2], [-2, this.depth + 2]];
    this.plane.setAttribute("d", HL.poly(corners.map(([x, y]) => this.P(x, y, z))));
    for (const pillar of this.pillars) {
      const above = pillar.h > z;
      if (!above && !pillar.above) continue;
      pillar.above = above;
      HL.put(pillar.cap, above ? HL.prism(this.P, this.front, pillar.ring, pillar.inner, z, pillar.h) : { sil: "", crease: "" });
    }
  }

  _move(p) {
    const share  = HL.clamp((this.bottom - p[1]) / (this.bottom - this.top), 0, 1);
    this.level.t = HL.lerp(ThresholdFigure.FLOOR, this.peak - 1.5, share);
    this.loop.wake();
  }

  _leave() {
    this.level.t = this.peak * ThresholdFigure.REST;
    this.loop.wake();
  }

  _retarget() {
    this.level.k = this.amount;
    this.loop.wake();
  }
}

class SortedSlotsFigure extends HairlineFigureBase {
  static RANGE   = [500, 700, 1100];
  static HEIGHTS = [14, 26, 7, 19];
  static PITCH   = 17;
  static DISC    = 5.5;
  static STAGGER = 70;

  constructor({ stage, svg }, value) {
    super(svg, value, 4.3);
    this.order  = SortedSlotsFigure.HEIGHTS.map((_, k) => k).sort((a, b) => SortedSlotsFigure.HEIGHTS[a] - SortedSlotsFigure.HEIGHTS[b]);
    this.tallest = this.order[this.order.length - 1];
    this._camera(this._extent(), 170);
    this._buildRail();
    this._buildSlots();
    this._start(stage, svg);
  }

  _slot(rank) {
    return (rank - (SortedSlotsFigure.HEIGHTS.length - 1) / 2) * SortedSlotsFigure.PITCH;
  }

  _extent() {
    const half = this._slot(SortedSlotsFigure.HEIGHTS.length - 1) + 12;
    const top  = Math.max(...SortedSlotsFigure.HEIGHTS) + 4;
    return [[...this._onScreen(-half, -10), -4], [...this._onScreen(half, -10), -4], [...this._onScreen(-half, 10), -4], [...this._onScreen(half, 10), -4], [...this._onScreen(0, 0), top], [...this._onScreen(half, 0), top]];
  }

  _buildRail() {
    const half = this._slot(SortedSlotsFigure.HEIGHTS.length - 1) + 12;
    HL.put(HL.solid(this.g), HL.prism(this.P, this.front, this._screenBox(-half, -10, half, 10, 5), this._screenBox(-half + 2.2, -7.8, half - 2.2, 7.8, 3), -4, 0));
    const line = (r) => this.P(...this._onScreen(r, 0), 0);
    HL.mk("path", { class: "dash nf", d: HL.seg(line(-half + 6), line(half - 6)) }, this.g);
    this.centreX = line(0)[0];
  }

  _buildSlots() {
    this.slots = SortedSlotsFigure.HEIGHTS.map((h, k) => {
      const group = HL.mk("g", {}, this.g);
      const stem  = HL.solid(group);
      const disc  = HL.solid(group);
      const dots  = Array.from({ length: k + 1 }, (_, j) => ({ off: (j - k / 2) * 2.2, el: HL.flatDot(group, this.C, 0.75, "dot m") }));
      const lit   = k === this.tallest;
      stem.sil.classList.toggle("hi", lit);
      disc.sil.classList.toggle("hi", lit);
      return { k, h, stem, disc, dots, tw: HL.tween(this._slot(k), 700), drawn: NaN };
    });
    this.stemRings = HL.rings(-1.5, -1.5, 1.5, 1.5, 1, 0.4);
  }

  _tick(dt, now) {
    return this._advance(this.slots, now);
  }

  _draw(slot, r) {
    const span          = slot.tw.to - slot.tw.from;
    const progress      = span ? HL.clamp((r - slot.tw.from) / span, 0, 1) : 1;
    const hop           = Math.min(10, Math.abs(span) * 0.25) * Math.sin(Math.PI * progress);
    const [x, y]        = this._onScreen(r, 0);
    const moved         = this._shifted(x, y, 0);
    const [ring, inner] = this.stemRings;
    HL.put(slot.stem, HL.prism(moved, this.front, ring, inner, hop, hop + slot.h));
    HL.put(slot.disc, HL.prism(moved, this.front, HL.circ(SortedSlotsFigure.DISC, 40), HL.circ(SortedSlotsFigure.DISC - 0.9, 40), hop + slot.h, hop + slot.h + 2));
    for (const dot of slot.dots) HL.place(dot.el, moved(...this._onScreen(dot.off, 0), hop + slot.h + 2));
  }

  _move(p) {
    this._choose(p[0] > this.centreX);
  }

  _retarget(now) {
    const sorted = this.chosen === true;
    for (const slot of this.slots) {
      const rank = sorted ? this.order.indexOf(slot.k) : slot.k;
      slot.tw.dur = this.amount;
      HL.tset(slot.tw, this._slot(rank), now, slot.k * SortedSlotsFigure.STAGGER);
    }
    this.loop.wake();
  }
}

class DataPullFigure extends HairlineFigureBase {
  static RANGE  = [0.05, 0.1, 0.18];
  static LENGTH = 62;
  static LANES  = [-6.5, 6.5];
  static CRATES = 5;
  static CRATE  = 4.6;
  static SLOW   = 0.25;
  static IDLE   = 0.14;
  static BOOST  = 1.3;
  static REST   = 1;
  static DOWN   = 1;
  static QUEUE  = 5;
  static METER  = 5;

  constructor({ stage, svg }, value) {
    super(svg, value, 3.5);
    this.data = null;
    this._camera(this._extent(), 166);
    this._buildEnds();
    this._buildLanes();
    this._buildGauges();
    this.phase = [0, 0.37];
    this._start(stage, svg);
    this._retarget();
  }

  _extent() {
    const half = DataPullFigure.LENGTH / 2 + 18;
    return [[...this._onScreen(-half, -14), -3], [...this._onScreen(half, -14), -3], [...this._onScreen(-half, 14), -3], [...this._onScreen(half, 14), -3], [...this._onScreen(-half + 6, 0), 32]];
  }

  _buildEnds() {
    const half = DataPullFigure.LENGTH / 2;
    HL.put(HL.solid(this.g), HL.prism(this.P, this.front, this._screenBox(-half - 18, -14, half + 18, 14, 6), this._screenBox(-half - 15.8, -11.8, half + 15.8, 11.8, 4), -3, 0));
    this.rack  = HL.solid(this.g);
    HL.put(this.rack, HL.prism(this.P, this.front, this._screenBox(-half - 15, -11, -half - 3, 11, 2.4), this._screenBox(-half - 14.2, -10.2, -half - 3.8, 10.2, 1.6), 0, 30));
    this.local = HL.solid(this.g);
    HL.put(this.local, HL.prism(this.P, this.front, this._screenBox(half + 3, -9, half + 14, 9, 2.4), this._screenBox(half + 3.8, -8.2, half + 13.2, 8.2, 1.6), 0, 11));
  }

  _buildLanes() {
    const half = DataPullFigure.LENGTH / 2;
    this.lanes = DataPullFigure.LANES.map((d, n) => {
      const belt = HL.solid(this.g);
      HL.put(belt, HL.prism(this.P, this.front, this._screenBox(-half, d - 3, half, d + 3, 2), null, 0, 1.2));
      const crates = Array.from({ length: DataPullFigure.CRATES }, () => {
        const el  = HL.solid(this.g);
        const dot = n === DataPullFigure.DOWN ? HL.flatDot(this.g, this.C, 0.9, "dot off") : null;
        return { el, dot };
      });
      return { n, d, belt, crates, speed: HL.spring(0, { k: 20, c: 9, eps: 0.0005 }), screenY: this.P(...this._onScreen(0, d), 0)[1] };
    });
    this.crateRings = HL.rings(-DataPullFigure.CRATE / 2, -DataPullFigure.CRATE / 2, DataPullFigure.CRATE / 2, DataPullFigure.CRATE / 2, 1.3, 0.5);
  }

  _buildGauges() {
    const half   = DataPullFigure.LENGTH / 2;
    this.queued  = Array.from({ length: DataPullFigure.QUEUE }, (_, i) => {
      const dot = HL.flatDot(this.g, this.C, 0.9, "dot off");
      HL.place(dot, this.P(...this._onScreen(-half - 9, -6.4 + i * 3.2), 30));
      return dot;
    });
    this.meter = Array.from({ length: DataPullFigure.METER }, (_, i) => {
      const dot = HL.flatDot(this.g, this.C, 0.8, "dot off");
      HL.place(dot, this.P(...this._onScreen(half + 8.5, -4.8 + i * 2.4), 11));
      return dot;
    });
  }

  setState(state) {
    this.data = { running: state.running, queued: state.queued, pct: state.pct };
    const lit = this.data.running > 0 && this.data.pct !== null ? Math.round((this.data.pct / 100) * DataPullFigure.METER) : 0;
    this.queued.forEach((dot, i) => dot.setAttribute("class", i < this.data.queued ? "dot m" : "dot off"));
    this.meter.forEach((dot, i) => dot.setAttribute("class", i < lit ? "dot" : "dot off"));
    this._retarget();
  }

  _tick(dt) {
    const half    = DataPullFigure.LENGTH / 2;
    const pulling = this.data !== null && this.data.running > 0;
    for (const lane of this.lanes) {
      HL.stepS(lane.speed, dt);
      this.phase[lane.n] = (this.phase[lane.n] + lane.speed.x * dt) % 1;
      lane.crates.forEach((crate, i) => {
        const s      = (this.phase[lane.n] + i / DataPullFigure.CRATES) % 1;
        const r      = lane.n === 0 ? half - s * DataPullFigure.LENGTH : -half + s * DataPullFigure.LENGTH;
        const h      = DataPullFigure.CRATE * HL.clamp(Math.min(s, 1 - s) / 0.1, 0, 1);
        const [x, y] = this._onScreen(r, lane.d);
        const [ring, inner] = this.crateRings;
        HL.put(crate.el, h < 0.2 ? { sil: "", crease: "" } : HL.prism(this._shifted(x, y, 0), this.front, ring, inner, 1.2, 1.2 + h));
        if (!crate.dot) return;
        crate.dot.setAttribute("visibility", h < 0.2 ? "hidden" : "visible");
        crate.dot.setAttribute("class", pulling ? "dot" : "dot off");
        HL.place(crate.dot, this.P(x, y, 1.2 + h));
      });
    }
    return true;
  }

  _move(p) {
    this._choose(HairlineFigureBase.nearest(this.lanes.map((lane) => lane.screenY), p[1]));
  }

  _speed(lane, fast) {
    if (this.data === null) return lane.n === fast ? this.amount : this.amount * DataPullFigure.SLOW;
    const base = lane.n === DataPullFigure.DOWN && this.data.running > 0 ? this.amount : this.amount * DataPullFigure.IDLE;
    return lane.n === this.chosen ? base * DataPullFigure.BOOST : base;
  }

  _retarget() {
    const fast = this.chosen === null ? DataPullFigure.REST : this.chosen;
    for (const lane of this.lanes) {
      lane.speed.t = this._speed(lane, fast);
      lane.belt.sil.classList.toggle("hi", lane.n === fast);
    }
    this.loop.wake();
  }
}

class SchedulerFigure extends HairlineFigureBase {
  static RANGE   = [3, 6, 10];
  static RACK    = [22, 30, 34];
  static STEPS   = 5;
  static STEP_W  = 11;
  static STEP_Y  = [3, 27];
  static TOP     = 28;
  static DROP    = 5.5;
  static FLOOR   = 82.5;
  static CRATE   = 3.6;
  static CRATE_Z = 7;
  static HOP     = 7;
  static SOCKETS = [[6, 8], [16, 8], [6, 22], [16, 22]];
  static BLADES  = [7, 14, 21, 28];
  static REST    = 0.35;

  constructor({ stage, svg }, value) {
    super(svg, value, 3.3);
    this.crates = new Map();
    this.lead   = null;
    this._camera(this._extent(), 168);
    this._plinth(-6, -5, SchedulerFigure.FLOOR + 6.5, SchedulerFigure.RACK[1] + 5, 6, 4);
    this._buildRack();
    this._buildSteps();
    this.ring = HL.rings(-SchedulerFigure.CRATE, -SchedulerFigure.CRATE, SchedulerFigure.CRATE, SchedulerFigure.CRATE, 1.5, 0.7);
    this._start(stage, svg);
    this._retarget(performance.now());
  }

  _extent() {
    const [, depth, height] = SchedulerFigure.RACK;
    const top               = height + SchedulerFigure.CRATE_Z + SchedulerFigure.RANGE[2];
    return [[-6, -5, -4], [SchedulerFigure.FLOOR + 6.5, depth + 5, -4], [SchedulerFigure.FLOOR + 6.5, -5, -4], [-6, depth + 5, -4], [0, 0, top], [22, depth, top]];
  }

  _buildRack() {
    const [width, depth, height] = SchedulerFigure.RACK;
    const [ring, inner]          = HL.rings(0, 0, width, depth, 3, 1.4);
    this.rack                    = HL.solid(this.g);
    HL.put(this.rack, HL.prism(this.P, this.front, ring, inner, 0, height));
    const sockets = HL.mk("path", { class: "nf lo" }, this.g);
    sockets.setAttribute("d", SchedulerFigure.SOCKETS.map(([x, y]) => HL.poly(HL.ringAt(this.P, HL.rrect(x - 4.4, y - 4.4, x + 4.4, y + 4.4, 1.6, 4), height))).join(""));
    const blades = HL.mk("path", { class: "nf lo" }, this.g);
    blades.setAttribute("d", SchedulerFigure.BLADES.map((z) => HL.seg(this.P(2.5, depth, z), this.P(width - 2.5, depth, z))).join(""));
    this.leds = SchedulerFigure.BLADES.map((z) => {
      const led = HL.mk("circle", { r: 1.1, class: "dot off" }, this.g);
      HL.place(led, this.P(width - 5, depth, z - 3.2));
      return led;
    });
    this.rackLayer = HL.mk("g", {}, this.g);
    this.rackX     = this.P(width / 2, depth / 2, height)[0];
  }

  _buildSteps() {
    const [y0, y1] = SchedulerFigure.STEP_Y;
    this.steps     = Array.from({ length: SchedulerFigure.STEPS }, (_, i) => {
      const x0            = SchedulerFigure.RACK[0] + i * SchedulerFigure.STEP_W;
      const top           = SchedulerFigure.TOP - i * SchedulerFigure.DROP;
      const [ring, inner] = HL.rings(x0, y0, x0 + SchedulerFigure.STEP_W, y1, 1.6, 0.8);
      const layer         = HL.mk("g", {}, this.g);
      const el            = HL.solid(layer);
      HL.put(el, HL.prism(this.P, this.front, ring, inner, 0, top));
      const crates        = HL.mk("g", {}, layer);
      return { i, el, crates, top, centre: [x0 + SchedulerFigure.STEP_W / 2, (y0 + y1) / 2], screenX: this.P(x0 + SchedulerFigure.STEP_W / 2, (y0 + y1) / 2, top)[0] };
    });
    this.floorLayer = HL.mk("g", {}, this.g);
    this.floorX     = this.P(SchedulerFigure.FLOOR, 15, 0)[0];
  }

  _pose(slot) {
    if (slot.kind === "socket") {
      const [x, y] = SchedulerFigure.SOCKETS[slot.index];
      return [x, y, SchedulerFigure.RACK[2]];
    }
    if (slot.kind === "step") return [...this.steps[slot.index].centre, this.steps[slot.index].top];
    return [SchedulerFigure.FLOOR, 15, 0];
  }

  _rank(slot) {
    if (slot.kind === "socket") return -1;
    if (slot.kind === "step") return slot.index;
    return SchedulerFigure.STEPS;
  }

  _layer(rank) {
    if (rank < 0) return this.rackLayer;
    if (rank >= SchedulerFigure.STEPS) return this.floorLayer;
    return this.steps[rank].crates;
  }

  _slots(jobs) {
    const slots   = new Map();
    const running = jobs.filter((job) => job.running).slice(0, SchedulerFigure.SOCKETS.length);
    running.forEach((job, index) => slots.set(job.id, { kind: "socket", index }));

    const waiting = jobs.filter((job) => !job.running).map((job) => ({ id: job.id, share: job.position == null ? 0 : 1 - (job.position - 1) / Math.max(1, job.of - 1) }));
    waiting.sort((a, b) => b.share - a.share);
    let last = -1;
    for (const job of waiting) {
      const own  = Math.round((1 - HL.clamp(job.share, 0, 1)) * (SchedulerFigure.STEPS - 1));
      const step = Math.max(own, last + 1);
      if (step > SchedulerFigure.STEPS) break;
      last = step;
      slots.set(job.id, step === SchedulerFigure.STEPS ? { kind: "floor", index: 0 } : { kind: "step", index: step });
    }
    this.lead = waiting.length && slots.has(waiting[0].id) ? waiting[0].id : null;
    return slots;
  }

  setState(state) {
    const now   = performance.now();
    const slots = this._slots(state.jobs);
    for (const [id, crate] of this.crates) {
      if (slots.has(id) || crate.leaving) continue;
      crate.leaving = true;
      HL.tset(crate.grow, 0, now, 0);
    }
    for (const [id, slot] of slots) {
      const crate = this.crates.get(id) || this._crate(id, slot, now);
      if (crate.leaving) {
        crate.leaving = false;
        HL.tset(crate.grow, 1, now, 0);
      }
      this._send(crate, slot, now);
    }
    const running = state.jobs.filter((job) => job.running).length;
    this.leds.forEach((led, k) => led.setAttribute("class", k < running ? "dot" : "dot off"));
    this._order();
    this._retarget(now);
  }

  _crate(id, slot, now) {
    const group = HL.mk("g", {}, this._layer(this._rank(slot)));
    const pose  = this._pose(slot);
    const crate = { id, group, el: HL.solid(group), slot, rank: this._rank(slot), from: pose, to: pose, travel: HL.tween(1), grow: HL.tween(0), lift: HL.tween(0), leaving: false, drawn: "" };
    HL.tset(crate.grow, 1, now, 0);
    this.crates.set(id, crate);
    return crate;
  }

  _send(crate, slot, now) {
    const to = this._pose(slot);
    if (to.every((v, k) => v === crate.to[k])) return;
    crate.from   = this._at(crate, now);
    crate.to     = to;
    crate.slot   = slot;
    crate.travel = HL.tween(0);
    HL.tset(crate.travel, 1, now, 0);
    crate.rank   = Math.max(crate.rank, this._rank(slot));
  }

  _at(crate, now) {
    const t = HL.tval(crate.travel, now);
    return crate.from.map((v, k) => HL.lerp(v, crate.to[k], t));
  }

  _order() {
    const sockets = [...this.crates.values()].filter((crate) => crate.rank < 0).sort((a, b) => a.to[0] + a.to[1] - (b.to[0] + b.to[1]));
    for (const crate of sockets) this.rackLayer.appendChild(crate.group);
    for (const crate of this.crates.values()) if (crate.rank >= 0) this._layer(crate.rank).appendChild(crate.group);
  }

  _tick(dt, now) {
    let moving = false;
    for (const crate of [...this.crates.values()]) {
      const t    = HL.tval(crate.travel, now);
      const grow = HL.tval(crate.grow, now);
      const lift = HL.tval(crate.lift, now);
      if (!HL.tdone(crate.travel, now) || !HL.tdone(crate.grow, now) || !HL.tdone(crate.lift, now)) moving = true;
      if (HL.tdone(crate.travel, now) && crate.rank !== this._rank(crate.slot)) {
        crate.rank = this._rank(crate.slot);
        this._order();
      }
      if (crate.leaving && HL.tdone(crate.grow, now)) {
        crate.group.remove();
        this.crates.delete(crate.id);
        continue;
      }
      const key = `${t}|${grow}|${lift}`;
      if (key === crate.drawn) continue;
      crate.drawn = key;
      this._draw(crate, t, grow, lift);
    }
    return moving;
  }

  _draw(crate, t, grow, lift) {
    const [x, y, z]     = crate.from.map((v, k) => HL.lerp(v, crate.to[k], t));
    const hop           = crate.from === crate.to ? 0 : SchedulerFigure.HOP * Math.sin(Math.PI * t);
    const base          = z + hop + lift;
    const height        = SchedulerFigure.CRATE_Z * grow;
    const [ring, inner] = this.ring;
    HL.put(crate.el, height < 0.2 ? { sil: "", crease: "" } : HL.prism(this._shifted(x, y, 0), this.front, ring, inner, base, base + height));
  }

  _move(p) {
    const targets = [this.rackX, ...this.steps.map((step) => step.screenX), this.floorX];
    this._choose(HairlineFigureBase.nearest(targets, p[0]) - 1);
  }

  _onTarget(crate, target) {
    if (target < 0) return crate.slot.kind === "socket";
    if (target >= SchedulerFigure.STEPS) return crate.slot.kind === "floor";
    return crate.slot.kind === "step" && crate.slot.index === target;
  }

  _retarget(now) {
    let lit = null;
    if (this.chosen === null) {
      lit = this.lead !== null ? this.crates.get(this.lead).el : this.rack;
      for (const crate of this.crates.values()) HL.tset(crate.lift, crate.id === this.lead ? this.amount * SchedulerFigure.REST : 0, now, 0);
    } else {
      const picked = [...this.crates.values()].filter((crate) => !crate.leaving && this._onTarget(crate, this.chosen));
      for (const crate of this.crates.values()) HL.tset(crate.lift, picked.includes(crate) ? this.amount * (this.chosen < 0 ? 0.6 : 1) : 0, now, 0);
      if (this.chosen < 0) lit = this.rack;
      else if (picked.length) lit = picked[0].el;
      else if (this.chosen < SchedulerFigure.STEPS) lit = this.steps[this.chosen].el;
    }
    this.rack.sil.classList.toggle("hi", lit === this.rack);
    for (const step of this.steps) step.el.sil.classList.toggle("hi", lit === step.el);
    for (const crate of this.crates.values()) crate.el.sil.classList.toggle("hi", lit === crate.el);
    this.loop.wake();
  }
}

class LrzPylonsFigure extends HairlineFigureBase {
  static RANGE  = [4, 8, 13];
  static LENGTH = 84;
  static PITCH  = 28;
  static SCALE  = 2.95;
  static PLATE  = 12;
  static WIDTH  = 15;
  static FOOT   = 3;
  static MAST   = 42;
  static ARM_AT = 0.78;
  static ARM    = 10;
  static R0     = 3;
  static R1     = 1;
  static TICKS  = [0.26, 0.5];
  static SAG    = 3;
  static SLACK  = { ok: 0, notice: 2, disrupted: 6, down: 11 };
  static HOP    = { ok: 0, notice: 3, disrupted: 6, down: 8 };
  static EVERY  = { ok: 0, notice: 2.8, disrupted: 1.9, down: 1.4 };
  static AIR    = 0.55;
  static LAMP   = { ok: "dot off", notice: "dot m", disrupted: "dot", down: "dot" };
  static ORDER  = ["ok", "notice", "disrupted", "down"];
  static REST   = 0.35;
  static ALONG  = [Math.SQRT1_2, -Math.SQRT1_2];
  static PACKET = 2.2;
  static TRIP   = 2.4;
  static PAUSE  = 1.1;

  constructor({ stage, svg }, value) {
    super(svg, value, LrzPylonsFigure.SCALE);
    this.clock    = Math.random() * 10;
    this.next     = this.clock + LrzPylonsFigure.PAUSE;
    this.outbound = false;
    this.statuses = ["ok", "ok", "ok", "ok"];
    this.wired    = true;
    this._build();
    this._start(stage, svg);
    this._retarget(performance.now());
  }

  _extent() {
    const half = this.length / 2 + LrzPylonsFigure.PLATE;
    const w    = LrzPylonsFigure.WIDTH;
    const top  = LrzPylonsFigure.FOOT + LrzPylonsFigure.MAST + LrzPylonsFigure.RANGE[2];
    return [[-half, -w, -3], [half, w, -3], [half, -w, -3], [-half, w, -3], [-half + LrzPylonsFigure.PLATE, 0, top], [half - LrzPylonsFigure.PLATE, 0, top]];
  }

  _frame(n) {
    const span  = LrzPylonsFigure.LENGTH + 2 * LrzPylonsFigure.PLATE;
    this.length = Math.max(LrzPylonsFigure.LENGTH, LrzPylonsFigure.PITCH * (n - 1));
    this.C      = HL.Cam(45, 0.5, (LrzPylonsFigure.SCALE * span) / (this.length + 2 * LrzPylonsFigure.PLATE));
    this._camera(this._extent(), 172);
    const o     = this.P(0, 0, 0);
    const dd    = this.P(LrzPylonsFigure.ALONG[0], LrzPylonsFigure.ALONG[1], 0);
    this.SH     = Math.hypot(dd[0] - o[0], dd[1] - o[1]);
  }

  _build() {
    const n = this.statuses.length;
    this.g.replaceChildren();
    this._frame(n);
    const half = this.length / 2 + LrzPylonsFigure.PLATE;
    this._plinth(-half, -LrzPylonsFigure.WIDTH, half, LrzPylonsFigure.WIDTH, 6, 3);
    this.backCables  = HL.mk("path", { class: "nf lo" }, this.g);
    this.backDot     = HL.mk("circle", { r: 0, class: "dot" }, this.g);
    this.pylons      = this.statuses.map((status, k) => this._pylon(k, n === 1 ? 0 : -this.length / 2 + (k * this.length) / (n - 1), status));
    this.frontCables = HL.mk("path", { class: "nf lo" }, this.g);
    this.frontDot    = HL.mk("circle", { r: 0, class: "dot" }, this.g);
    this.packet      = null;
  }

  _pylon(k, x, status) {
    const group = HL.mk("g", {}, this.g);
    const foot  = HL.solid(group);
    const back  = HL.solid(group);
    const mast  = HL.solid(group);
    const ahead = HL.solid(group);
    const lamp  = HL.mk("circle", { r: 1.6, class: LrzPylonsFigure.LAMP[status] }, group);
    return { k, x, status, foot, back, mast, ahead, lamp, rings: HL.rings(x - 4.5, -4.5, x + 4.5, 4.5, 1.8, 0.9), phase: Math.random() * 3, grow: HL.tween(0), drawn: "", screenX: this.P(x, 0, 0)[0] };
  }

  setState(state) {
    const wired    = state.systems !== null;
    const statuses = wired ? state.systems.map((status) => this._status(status)) : this.statuses.map(() => "ok");
    if (!statuses.length) throw new Error("pylons: an LRZ reading with no systems");
    const rebuild  = statuses.length !== this.statuses.length;
    this.statuses  = statuses;
    this.wired     = wired;
    if (rebuild) this._build();
    if (!wired) this._drop();
    this.pylons.forEach((pylon, k) => {
      pylon.status = statuses[k];
      pylon.lamp.setAttribute("class", wired ? LrzPylonsFigure.LAMP[pylon.status] : "dot off");
      pylon.drawn  = "";
    });
    this.chosen = null;
    this._retarget(performance.now());
  }

  _status(status) {
    if (!(status in LrzPylonsFigure.HOP)) throw new Error(`pylons: unknown LRZ state "${status}"`);
    return status;
  }

  _hop(pylon) {
    const height = LrzPylonsFigure.HOP[pylon.status];
    if (!this.wired || !height) return 0;
    const t = ((this.clock + pylon.phase) % LrzPylonsFigure.EVERY[pylon.status]) / LrzPylonsFigure.AIR;
    return t >= 1 ? 0 : height * 4 * t * (1 - t);
  }

  _along(pylon, lift, l) {
    return [pylon.x, 0, lift + LrzPylonsFigure.FOOT + l];
  }

  _tips(pylon, lift, length) {
    const centre = this._along(pylon, lift, length * LrzPylonsFigure.ARM_AT);
    return { centre, back: [centre[0], centre[1] - LrzPylonsFigure.ARM, centre[2]], ahead: [centre[0], centre[1] + LrzPylonsFigure.ARM, centre[2]] };
  }

  _disc(p, r) {
    return Array.from({ length: 20 }, (_, k) => [p[0] + r * this.SH * Math.cos((k * Math.PI) / 10), p[1] + r * this.SH * Math.sin((k * Math.PI) / 10)]);
  }

  _rod(a, b, ra, rb) {
    return HL.poly(HL.hull(this._disc(a, ra).concat(this._disc(b, rb))));
  }

  _tick(dt, now) {
    this.clock += dt;
    let moving  = false;
    for (const pylon of this.pylons) {
      if (!HL.tdone(pylon.grow, now)) moving = true;
      if (this.wired && pylon.status !== "ok") moving = true;
      const lift   = this._hop(pylon);
      const length = LrzPylonsFigure.MAST + HL.tval(pylon.grow, now);
      const key    = `${lift}|${length}`;
      if (key === pylon.drawn) continue;
      pylon.drawn  = key;
      this._drawPylon(pylon, lift, length);
    }
    if (!this.wired) {
      this._drawCables(null);
      return moving;
    }

    const tips = this.pylons.map((pylon) => this._tips(pylon, this._hop(pylon), LrzPylonsFigure.MAST + HL.tval(pylon.grow, now)));
    this._drawCables(tips);
    if (this.packet) this._carry(dt, tips);
    else if (this.clock >= this.next) this._launch();
    return true;
  }

  _drawPylon(pylon, lift, length) {
    const base  = this.P(...this._along(pylon, lift, 0));
    const top   = this.P(...this._along(pylon, lift, length));
    const tips  = this._tips(pylon, lift, length);
    const mid   = this.P(...tips.centre);
    const dir   = [top[0] - base[0], top[1] - base[1]];
    const len   = Math.hypot(dir[0], dir[1]);
    const n     = [-dir[1] / len, dir[0] / len];
    const ticks = LrzPylonsFigure.TICKS.map((at) => {
      const knot = this.P(...this._along(pylon, lift, length * at));
      const w    = HL.lerp(LrzPylonsFigure.R0, LrzPylonsFigure.R1, at) * this.SH - 1.1;
      return HL.seg([knot[0] + n[0] * w, knot[1] + n[1] * w], [knot[0] - n[0] * w, knot[1] - n[1] * w]);
    }).join("");
    HL.put(pylon.foot, HL.prism(this.P, this.front, pylon.rings[0], pylon.rings[1], lift, lift + LrzPylonsFigure.FOOT));
    HL.put(pylon.back, { sil: this._rod(mid, this.P(...tips.back), 1, 0.7), crease: "" });
    HL.put(pylon.mast, { sil: this._rod(base, top, LrzPylonsFigure.R0, LrzPylonsFigure.R1), crease: ticks });
    HL.put(pylon.ahead, { sil: this._rod(mid, this.P(...tips.ahead), 1, 0.7), crease: "" });
    HL.place(pylon.lamp, this.P(...this._along(pylon, lift, length + 1.8)));
  }

  _drawCables(tips) {
    if (!tips) {
      this.backCables.setAttribute("d", "");
      this.frontCables.setAttribute("d", "");
      return;
    }
    const span = (side) => this.pylons.slice(1).map((_, k) => HL.open(Array.from({ length: 13 }, (__, j) => this._cable(tips, k, side, j / 12)))).join("");
    this.backCables.setAttribute("d", span("back"));
    this.frontCables.setAttribute("d", span("ahead"));
  }

  _cable(tips, k, side, t) {
    const a     = tips[k][side];
    const b     = tips[k + 1][side];
    const slack = LrzPylonsFigure.SAG + Math.max(LrzPylonsFigure.SLACK[this.pylons[k].status], LrzPylonsFigure.SLACK[this.pylons[k + 1].status]);
    return this.P(HL.lerp(a[0], b[0], t), HL.lerp(a[1], b[1], t), HL.lerp(a[2], b[2], t) - 4 * slack * t * (1 - t));
  }

  _launch() {
    this.next     = this.clock + LrzPylonsFigure.PAUSE;
    this.outbound = !this.outbound;
    const last    = this.pylons.length - 1;
    const from    = this.outbound ? 0 : last;
    const step    = this.outbound ? 1 : -1;
    if (last < 1 || this.pylons[from].status === "down") return;

    let to = from + step;
    while (to !== from + step * last && this.pylons[to].status !== "down") to += step;
    this.packet = { side: this.outbound ? "ahead" : "back", from, to, t: 0 };
  }

  _carry(dt, tips) {
    const packet = this.packet;
    const spans  = Math.abs(packet.to - packet.from);
    packet.t     = Math.min(1, packet.t + dt / ((LrzPylonsFigure.TRIP * spans) / (this.pylons.length - 1)));
    const ease   = packet.t * packet.t * (3 - 2 * packet.t);
    const at     = HL.lerp(packet.from, packet.to, ease);
    const k      = Math.min(Math.floor(at), this.pylons.length - 2);
    const dot    = packet.side === "ahead" ? this.frontDot : this.backDot;
    HL.place(dot, this._cable(tips, k, packet.side, at - k));
    dot.setAttribute("r", String(LrzPylonsFigure.PACKET));
    if (packet.t < 1) return;

    this._drop();
    this.next = this.clock + LrzPylonsFigure.PAUSE;
  }

  _drop() {
    this.packet = null;
    this.frontDot.setAttribute("r", "0");
    this.backDot.setAttribute("r", "0");
  }

  _worst() {
    let worst = Math.min(1, this.pylons.length - 1);
    let rank  = 0;
    this.pylons.forEach((pylon, k) => {
      const level = this.wired ? LrzPylonsFigure.ORDER.indexOf(pylon.status) : 0;
      if (level > rank) {
        rank  = level;
        worst = k;
      }
    });
    return worst;
  }

  _move(p) {
    this._choose(HairlineFigureBase.nearest(this.pylons.map((pylon) => pylon.screenX), p[0]));
  }

  _retarget(now) {
    const lit = this.chosen === null ? this._worst() : this.chosen;
    for (const pylon of this.pylons) {
      const target = pylon.k !== lit ? 0 : this.chosen === null ? this.amount * LrzPylonsFigure.REST : this.amount;
      HL.tset(pylon.grow, target, now, 0);
      pylon.mast.sil.classList.toggle("hi", pylon.k === lit);
    }
    this.loop.wake();
  }
}

class PatchSamplerFigure extends HairlineFigureBase {
  static RANGE     = [6, 12, 20];
  static N         = 4;
  static CELL      = 15;
  static TILE      = 12.6;
  static DEPTH     = 3;
  static BATCH     = [70, 20];
  static SHEETS    = 3;
  static REST      = 10;
  static REST_LIFT = 1.2;

  constructor({ stage, svg }, value) {
    super(svg, value, 3.1);
    this.span = PatchSamplerFigure.N * PatchSamplerFigure.CELL;
    this._camera(this._extent(), 166);
    this._plinth(-4, -4, this.span + 4, this.span + 4, 7, 4);
    this._buildSockets();
    this.ground = HL.mk("g", {}, this.g);
    this._buildTiles();
    this._buildBatch();
    this.air = HL.mk("g", {}, this.g);
    this._start(stage, svg);
  }

  _extent() {
    const span     = this.span;
    const [bx, by] = PatchSamplerFigure.BATCH;
    const edge     = PatchSamplerFigure.TILE + 2;
    const top      = PatchSamplerFigure.DEPTH + PatchSamplerFigure.RANGE[2];
    return [[-4, -4, -4], [span + 4, span + 4, -4], [span + 4, -4, -4], [-4, span + 4, -4], [bx + edge, by + edge, -2], [0, 0, top], [span, 0, top], [0, span, top]];
  }

  _fringes(x0, y0, z, from) {
    const tile  = PatchSamplerFigure.TILE;
    const phase = (x) => 0.12 * x + 0.002 * x * x;
    const lines = [];
    for (let n = Math.ceil(phase(from + 1.5)); n <= Math.floor(phase(from + tile - 1.5)); n++) {
      const x = x0 - from + (-0.12 + Math.sqrt(0.0144 + 0.008 * n)) / 0.004;
      lines.push(HL.seg(this.P(x, y0 + 1.5, z), this.P(x, y0 + tile - 1.5, z)));
    }
    return lines.join("");
  }

  _buildSockets() {
    const n      = PatchSamplerFigure.N;
    const inset  = (PatchSamplerFigure.CELL - PatchSamplerFigure.TILE) / 2;
    const square = [];
    for (let i = 0; i < n; i++) {
      for (let j = 0; j < n; j++) {
        const x0 = i * PatchSamplerFigure.CELL + inset + 0.6;
        const y0 = j * PatchSamplerFigure.CELL + inset + 0.6;
        square.push(HL.poly(HL.ringAt(this.P, HL.rrect(x0, y0, x0 + PatchSamplerFigure.TILE - 1.2, y0 + PatchSamplerFigure.TILE - 1.2, 1.6), 0)));
      }
    }
    HL.mk("path", { class: "dash nf", d: square.join("") }, this.g);
  }

  _buildTiles() {
    const n     = PatchSamplerFigure.N;
    const inset = (PatchSamplerFigure.CELL - PatchSamplerFigure.TILE) / 2;
    const cells = [];
    for (let i = 0; i < n; i++) for (let j = 0; j < n; j++) cells.push([i, j]);
    cells.sort((a, b) => a[0] + a[1] - (b[0] + b[1]));
    this.tiles = cells.map(([i, j], rank) => {
      const x0            = i * PatchSamplerFigure.CELL + inset;
      const y0            = j * PatchSamplerFigure.CELL + inset;
      const [ring, inner] = HL.rings(x0, y0, x0 + PatchSamplerFigure.TILE, y0 + PatchSamplerFigure.TILE, 2.2, 0.9);
      const group         = HL.mk("g", {}, this.ground);
      const el            = HL.solid(group);
      const marks         = HL.mk("path", { class: "nf" }, group);
      const key           = i * n + j;
      const lit           = key === PatchSamplerFigure.REST;
      el.sil.classList.toggle("hi", lit);
      return { key, rank, x0, y0, ring, inner, group, el, marks, airborne: false, tw: HL.tween(lit ? this.amount * PatchSamplerFigure.REST_LIFT : 0), drawn: NaN };
    });
  }

  _buildBatch() {
    const [x0, y0]      = PatchSamplerFigure.BATCH;
    const tile          = PatchSamplerFigure.TILE;
    const [ring, inner] = HL.rings(x0 - 2, y0 - 2, x0 + tile + 2, y0 + tile + 2, 3, 1.2);
    HL.put(HL.solid(this.g), HL.prism(this.P, this.front, ring, inner, -2, 0));
    for (let k = 0; k < PatchSamplerFigure.SHEETS; k++) {
      const dx            = 0.8 * Math.sin(k * 2.1);
      const [sheet, edge] = HL.rings(x0 + dx, y0 - dx, x0 + dx + tile, y0 - dx + tile, 2.2, 0.9);
      const z0            = k * 1.8;
      const group         = HL.mk("g", {}, this.g);
      HL.put(HL.solid(group), HL.prism(this.P, this.front, sheet, edge, z0, z0 + 1.2));
      HL.mk("path", { class: "nf", d: this._fringes(x0 + dx, y0 - dx, z0 + 1.2, 6 + 17 * k) }, group);
    }
  }

  _tick(dt, now) {
    return this._advance(this.tiles, now);
  }

  _draw(tile, lift) {
    const airborne = lift > PatchSamplerFigure.DEPTH * 0.5;
    if (airborne !== tile.airborne) {
      tile.airborne = airborne;
      this._place(tile, airborne ? this.air : this.ground);
    }
    HL.put(tile.el, HL.prism(this.P, this.front, tile.ring, tile.inner, lift, lift + PatchSamplerFigure.DEPTH));
    tile.marks.setAttribute("d", this._fringes(tile.x0, tile.y0, lift + PatchSamplerFigure.DEPTH, tile.x0));
  }

  _place(tile, holder) {
    const after = [...holder.children].find((group) => this.tiles.find((other) => other.group === group).rank > tile.rank);
    holder.insertBefore(tile.group, after || null);
  }

  _move(p) {
    const [x, y] = HL.unproj(this.C, p[0], p[1], PatchSamplerFigure.DEPTH);
    const i      = Math.floor(x / PatchSamplerFigure.CELL);
    const j      = Math.floor(y / PatchSamplerFigure.CELL);
    const inside = i >= 0 && j >= 0 && i < PatchSamplerFigure.N && j < PatchSamplerFigure.N;
    this._choose(inside ? i * PatchSamplerFigure.N + j : null);
  }

  _retarget(now) {
    const key  = this.chosen === null ? PatchSamplerFigure.REST : this.chosen;
    const lift = this.chosen === null ? this.amount * PatchSamplerFigure.REST_LIFT : this.amount;
    for (const tile of this.tiles) {
      HL.tset(tile.tw, tile.key === key ? lift : 0, now, 0);
      tile.el.sil.classList.toggle("hi", tile.key === key);
    }
    this.loop.wake();
  }
}

class FeedLineFigure extends HairlineFigureBase {
  static RANGE      = [4, 8, 13];
  static REST_STATE = { workers: 4, prefetch: 4, wait: 0.02, util: 96, feed: 1.4 };
  static MAX_LANES  = 16;
  static MAX_SLOTS  = 8;
  static BAND       = 24;
  static WORKER_X   = -62;
  static WORKER     = 8;
  static WORKER_H   = 9;
  static BELT       = 1.2;
  static CRATE      = 4.6;
  static CRATES     = 3;
  static FADE       = 0.12;
  static SLOT       = 6.6;
  static TRAY_W     = 4.6;
  static TRAY_H     = 2.2;
  static TRAY_END   = 23;
  static GPU        = [35, 57];
  static GPU_D      = 15;
  static GPU_H      = 11;
  static FAN        = 6;
  static WAIT_EMPTY = 0.5;
  static REST_LIFT  = 0.4;

  constructor({ stage, svg }, value) {
    super(svg, value, 2.5);
    this.data      = FeedLineFigure.REST_STATE;
    this.counts    = null;
    this.lanePhase = 0;
    this.trayPhase = 0;
    this.fanAngle  = 0;
    this.laneSpeed = HL.spring(0, { k: 20, c: 9, eps: 0.0005 });
    this.traySpeed = HL.spring(0, { k: 20, c: 9, eps: 0.0005 });
    this.fanSpeed  = HL.spring(0, { k: 20, c: 9, eps: 0.0005 });
    this._camera(this._extent(), 166);
    this._plinth(FeedLineFigure.WORKER_X - 5, -FeedLineFigure.BAND - 6, FeedLineFigure.GPU[1] + 5, FeedLineFigure.BAND + 6, 7, 3);
    this.laneLayer = HL.mk("g", {}, this.g);
    this.railLayer = HL.mk("g", {}, this.g);
    this.trayLayer = HL.mk("g", {}, this.g);
    this.gpuLayer  = HL.mk("g", {}, this.g);
    this._buildGpu();
    this._layout();
    this._start(stage, svg);
    this._retarget(performance.now());
  }

  _extent() {
    const x0  = FeedLineFigure.WORKER_X - 5;
    const x1  = FeedLineFigure.GPU[1] + 5;
    const y   = FeedLineFigure.BAND + 6;
    const top = FeedLineFigure.GPU_H + FeedLineFigure.RANGE[2];
    return [[x0, -y, -3], [x1, y, -3], [x1, -y, -3], [x0, y, -3], [FeedLineFigure.GPU[0], -FeedLineFigure.GPU_D, top], [FeedLineFigure.WORKER_X, -FeedLineFigure.BAND, FeedLineFigure.WORKER_H + FeedLineFigure.RANGE[2]]];
  }

  _buildGpu() {
    const [x0, x1]      = FeedLineFigure.GPU;
    const d             = FeedLineFigure.GPU_D;
    const mid           = (x0 + x1) / 2;
    const [ring, inner] = HL.rings(x0, -d, x1, d, 2.6, 1.2);
    const group         = HL.mk("g", {}, this.gpuLayer);
    this.gpu            = { key: "gpu", ring, inner, el: HL.solid(group), rims: HL.mk("path", { class: "nf lo" }, group), blades: HL.mk("path", { class: "nf" }, group), led: HL.flatDot(group, this.C, 1.1, "dot m"), fans: [[mid, -d / 2], [mid, d / 2]], tw: HL.tween(0), drawn: NaN };
  }

  _counts(state) {
    const lanes = HL.clamp(Math.round(state.workers), 0, FeedLineFigure.MAX_LANES);
    const slots = HL.clamp(Math.round(state.prefetch), 1, FeedLineFigure.MAX_SLOTS);
    const share = 1 - HL.clamp(state.wait / FeedLineFigure.WAIT_EMPTY, 0, 1);
    return { lanes: Math.max(1, lanes), slots, filled: Math.round(slots * share) };
  }

  _layout() {
    const counts   = this._counts(this.data);
    this.counts    = counts;
    this.trayStart = FeedLineFigure.TRAY_END - counts.slots * FeedLineFigure.SLOT;
    this.railX     = this.trayStart - FeedLineFigure.SLOT - 3;
    this.beltFrom  = FeedLineFigure.WORKER_X + FeedLineFigure.WORKER + 1.5;
    this.beltTo    = this.railX - 1;
    this.laneLayer.replaceChildren();
    this.railLayer.replaceChildren();
    this.trayLayer.replaceChildren();
    this._buildLanes(counts.lanes);
    this._buildRail();
    this._buildTray(counts.slots, counts.filled);
    this.items = [...this.lanes, this.tray, this.gpu];
  }

  _buildLanes(n) {
    const pitch = (2 * FeedLineFigure.BAND) / n;
    const belt  = Math.min(5.2, pitch * 0.62);
    const crate = Math.min(FeedLineFigure.CRATE, pitch * 0.66);
    const block = Math.min(7, pitch * 0.8);
    const x0    = FeedLineFigure.WORKER_X;
    const x1    = x0 + FeedLineFigure.WORKER;
    this.crateSize  = crate;
    this.crateRings = HL.rings(-crate / 2, -crate / 2, crate / 2, crate / 2, Math.min(1.3, crate * 0.28), Math.min(0.5, crate * 0.12));
    this.lanes      = Array.from({ length: n }, (_, k) => {
      const y             = -FeedLineFigure.BAND + pitch * (k + 0.5);
      const group         = HL.mk("g", {}, this.laneLayer);
      const [ring, inner] = HL.rings(x0, y - block / 2, x1, y + block / 2, Math.min(2.2, block * 0.3), Math.min(1, block * 0.2));
      const el            = HL.solid(group);
      const led           = HL.flatDot(group, this.C, Math.min(0.9, block * 0.16), "dot m");
      const beltEl        = HL.solid(group);
      HL.put(beltEl, HL.prism(this.P, this.front, HL.rings(this.beltFrom, y - belt / 2, this.beltTo, y + belt / 2, Math.min(2, belt / 2), 0.2)[0], null, 0, FeedLineFigure.BELT));
      const crates        = Array.from({ length: FeedLineFigure.CRATES }, () => HL.solid(group));
      return { key: k, y, ring, inner, el, led, crates, tw: HL.tween(0), drawn: NaN };
    });
  }

  _buildRail() {
    const y             = FeedLineFigure.BAND + 2;
    const [ring, inner] = HL.rings(this.railX, -y, this.railX + 3, y, 1.4, 0.7);
    HL.put(HL.solid(this.railLayer), HL.prism(this.P, this.front, ring, inner, 0, 3));
  }

  _buildTray(slots, filled) {
    const group         = HL.mk("g", {}, this.trayLayer);
    const w             = FeedLineFigure.TRAY_W;
    const c             = FeedLineFigure.CRATE / 2;
    const [ring, inner] = HL.rings(this.trayStart, -w, FeedLineFigure.TRAY_END, w, 2, 1);
    const el            = HL.solid(group);
    const wells         = Array.from({ length: slots }, (_, j) => ({ x: FeedLineFigure.TRAY_END - FeedLineFigure.SLOT * (j + 0.5), el: HL.flatDot(group, this.C, 0.9, "dot off") }));
    const feeder        = HL.rings(FeedLineFigure.TRAY_END + 0.6, -2.4, FeedLineFigure.GPU[0] - 0.4, 2.4, 1.2, 0.2)[0];
    HL.put(HL.solid(group), HL.prism(this.P, this.front, feeder, null, 0, FeedLineFigure.BELT));
    const crates        = Array.from({ length: filled > 0 ? filled + 1 : 0 }, () => HL.solid(group));
    this.tray           = { key: "tray", ring, inner, el, wells, crates, rings: HL.rings(-c, -c, c, c, 1.3, 0.5), tw: HL.tween(0), drawn: NaN };
  }

  setState(state) {
    const next = state === null ? FeedLineFigure.REST_STATE : state;
    for (const key of ["workers", "prefetch", "wait", "util", "feed"]) {
      if (!Number.isFinite(next[key])) throw new Error(`feed figure: state.${key} must be a finite number, got ${next[key]}`);
    }
    const before = this.counts;
    const after  = this._counts(next);
    this.data    = next;
    if (after.lanes !== before.lanes || after.slots !== before.slots || after.filled !== before.filled) {
      this._layout();
      if (typeof this.chosen === "number" && this.chosen >= this.lanes.length) this.chosen = null;
    }
    this._retarget(performance.now());
  }

  _rest() {
    return this.data.wait <= 0.1 ? "gpu" : "tray";
  }

  _tick(dt, now) {
    HL.stepS(this.laneSpeed, dt);
    HL.stepS(this.traySpeed, dt);
    HL.stepS(this.fanSpeed, dt);
    this.lanePhase = (this.lanePhase + this.laneSpeed.x * dt) % 1;
    this.trayPhase = (this.trayPhase + this.traySpeed.x * dt) % 1;
    this.fanAngle  = (this.fanAngle + this.fanSpeed.x * dt) % (Math.PI * 2);
    this._advance(this.items, now);
    this._drawLaneCrates();
    this._drawTrayCrates();
    this._drawFans();
    return true;
  }

  _draw(item, lift) {
    if (item.key === "tray") return this._drawTray(lift);
    if (item.key === "gpu") return this._drawGpu(lift);
    HL.put(item.el, HL.prism(this.P, this.front, item.ring, item.inner, lift, lift + FeedLineFigure.WORKER_H));
    HL.place(item.led, this.P(FeedLineFigure.WORKER_X + FeedLineFigure.WORKER / 2, item.y, lift + FeedLineFigure.WORKER_H));
  }

  _drawTray(lift) {
    const tray = this.tray;
    HL.put(tray.el, HL.prism(this.P, this.front, tray.ring, tray.inner, lift, lift + FeedLineFigure.TRAY_H));
    for (const well of tray.wells) HL.place(well.el, this.P(well.x, 0, lift + FeedLineFigure.TRAY_H));
  }

  _drawGpu(lift) {
    const gpu = this.gpu;
    const top = lift + FeedLineFigure.GPU_H;
    HL.put(gpu.el, HL.prism(this.P, this.front, gpu.ring, gpu.inner, lift, top));
    HL.place(gpu.led, this.P(FeedLineFigure.GPU[1] - 3, FeedLineFigure.GPU_D - 3, top));
    gpu.rims.setAttribute("d", gpu.fans.map(([x, y]) => HL.poly(HL.ringAt(this._shifted(x, y, 0), HL.circ(FeedLineFigure.FAN, 32), top))).join(""));
  }

  _drawFans() {
    const gpu    = this.gpu;
    const top    = (Number.isNaN(gpu.drawn) ? 0 : gpu.drawn) + FeedLineFigure.GPU_H;
    const reach  = FeedLineFigure.FAN * 0.82;
    const blades = [];
    for (const [x, y] of gpu.fans) {
      for (let b = 0; b < 3; b++) {
        const a = this.fanAngle + (b * 2 * Math.PI) / 3;
        blades.push(HL.seg(this.P(x, y, top), this.P(x + reach * Math.cos(a), y + reach * Math.sin(a), top)));
      }
    }
    gpu.blades.setAttribute("d", blades.join(""));
  }

  _drawLaneCrates() {
    const length        = this.beltTo - this.beltFrom;
    const [ring, inner] = this.crateRings;
    for (const lane of this.lanes) {
      const offset = (lane.key * 0.618) % 1;
      const boost  = lane.key === this.chosen ? 1.8 : 1;
      lane.crates.forEach((crate, i) => {
        const s = (this.lanePhase * boost + offset + i / FeedLineFigure.CRATES) % 1;
        const h = this.crateSize * HL.clamp(Math.min(s, 1 - s) / FeedLineFigure.FADE, 0, 1);
        HL.put(crate, h < 0.2 ? { sil: "", crease: "" } : HL.prism(this._shifted(this.beltFrom + s * length, lane.y, 0), this.front, ring, inner, FeedLineFigure.BELT, FeedLineFigure.BELT + h));
      });
    }
  }

  _drawTrayCrates() {
    const tray          = this.tray;
    const [ring, inner] = tray.rings;
    const filled        = tray.crates.length - 1;
    const base          = (Number.isNaN(tray.drawn) ? 0 : tray.drawn) + FeedLineFigure.TRAY_H;
    const exitFrom      = FeedLineFigure.TRAY_END - FeedLineFigure.SLOT / 2;
    const exitTo        = FeedLineFigure.GPU[0] - FeedLineFigure.CRATE / 2;
    tray.crates.forEach((crate, k) => {
      const s      = k - this.trayPhase;
      const grow   = s > filled - 1 ? HL.clamp(filled - s, 0, 1) : 1;
      const shrink = s < 0 ? HL.clamp((1 + s) / 0.3, 0, 1) : 1;
      const h      = FeedLineFigure.CRATE * Math.min(grow, shrink);
      const x      = s < 0 ? HL.lerp(exitFrom, exitTo, -s) : FeedLineFigure.TRAY_END - FeedLineFigure.SLOT * (s + 0.5);
      const z      = s < 0 ? HL.lerp(base, FeedLineFigure.BELT, HL.clamp(-s / 0.4, 0, 1)) : base;
      HL.put(crate, h < 0.2 ? { sil: "", crease: "" } : HL.prism(this._shifted(x, 0, 0), this.front, ring, inner, z, z + h));
    });
  }

  _move(p) {
    const [x, y] = HL.unproj(this.C, p[0], p[1], 4);
    if (x < this.railX + 1.5) return this._choose(HairlineFigureBase.nearest(this.lanes.map((lane) => lane.y), y));
    this._choose(x < FeedLineFigure.GPU[0] - 3 ? "tray" : "gpu");
  }

  _retarget(now) {
    const util       = HL.clamp(this.data.util, 0, 100) / 100;
    const anchor     = this.chosen === null ? this._rest() : this.chosen;
    const lift       = this.chosen === null ? this.amount * FeedLineFigure.REST_LIFT : this.amount;
    this.laneSpeed.t = 0.07 + 0.11 * HL.clamp(this.data.feed, 0, 2);
    this.traySpeed.t = 0.2 + 1.1 * util;
    this.fanSpeed.t  = 0.8 + 11 * util;
    for (const item of this.items) {
      const lit = item.key === anchor;
      HL.tset(item.tw, lit ? lift : 0, now, 0);
      item.el.sil.classList.toggle("hi", lit);
    }
    for (const lane of this.lanes) lane.led.setAttribute("class", lane.key === anchor ? "dot" : "dot m");
    this.gpu.led.setAttribute("class", anchor === "gpu" ? "dot" : util >= 0.5 ? "dot m" : "dot off");
    this.loop.wake();
  }
}

class ReceptiveFieldFigure extends HairlineFigureBase {
  static RANGE   = [2, 4, 7];
  static N       = 9;
  static CELL    = 8.6;
  static TILE    = 7.2;
  static DEPTH   = 2;
  static LAYERS  = [18, 27, 36, 45];
  static POLE    = -10;
  static SHADE   = 6.5;
  static STAGGER = 45;
  static REST    = 1;

  constructor({ stage, svg }, value) {
    super(svg, value, 2.5);
    this.span   = ReceptiveFieldFigure.N * ReceptiveFieldFigure.CELL;
    this.centre = this.span / 2;
    this.pole   = [ReceptiveFieldFigure.POLE, this.span - ReceptiveFieldFigure.POLE];
    this.layer  = ReceptiveFieldFigure.REST;
    this._camera(this._extent(), 166);
    this._plinth(-4, -4, this.span + 4, this.span + 4, 7, 4);
    this._buildPole();
    this._buildTiles();
    this._buildLamp();
    this._start(stage, svg);
  }

  _extent() {
    const span     = this.span;
    const [px, py] = this.pole;
    const top      = ReceptiveFieldFigure.LAYERS[ReceptiveFieldFigure.LAYERS.length - 1] + 12;
    return [[-4, -4, -4], [span + 4, span + 4, -4], [span + 4, -4, -4], [-4, span + 4, -4], [px - 5, py + 5, 0], [px, py, top], [this.centre, this.centre, top]];
  }

  _buildPole() {
    const [px, py] = this.pole;
    const at       = this._shifted(px, py, 0);
    const top      = ReceptiveFieldFigure.LAYERS[ReceptiveFieldFigure.LAYERS.length - 1] + 12;
    HL.put(HL.solid(this.g), HL.prism(at, this.front, HL.circ(5.5, 48), HL.circ(4.6, 48), 0, 1.6));
    HL.put(HL.solid(this.g), HL.prism(at, this.front, HL.circ(1.5, 24), null, 1.6, top));
    for (const z of ReceptiveFieldFigure.LAYERS) HL.put(HL.solid(this.g), HL.prism(at, this.front, HL.circ(2.6, 32), HL.circ(2, 32), z + 6.2, z + 7.4));
  }

  _buildTiles() {
    const n     = ReceptiveFieldFigure.N;
    const mid   = (n - 1) / 2;
    const inset = (ReceptiveFieldFigure.CELL - ReceptiveFieldFigure.TILE) / 2;
    const cells = [];
    for (let i = 0; i < n; i++) for (let j = 0; j < n; j++) cells.push([i, j]);
    cells.sort((a, b) => a[0] + a[1] - (b[0] + b[1]));
    this.tiles = cells.map(([i, j]) => {
      const x0            = i * ReceptiveFieldFigure.CELL + inset;
      const y0            = j * ReceptiveFieldFigure.CELL + inset;
      const [ring, inner] = HL.rings(x0, y0, x0 + ReceptiveFieldFigure.TILE, y0 + ReceptiveFieldFigure.TILE, 1.8, 0.7);
      const el            = HL.solid(this.g);
      const reach         = Math.max(Math.abs(i - mid), Math.abs(j - mid));
      return { reach, ring, inner, el, tw: HL.tween(this._lift(reach, ReceptiveFieldFigure.REST)), drawn: NaN };
    });
    this.tiles.forEach((tile) => tile.el.sil.classList.toggle("hi", tile.reach === ReceptiveFieldFigure.REST));
  }

  _lift(reach, layer) {
    return reach <= layer ? this.amount * (1 - 0.15 * reach) : 0;
  }

  _buildLamp() {
    this.beam       = HL.mk("path", { class: "dash nf" }, this.g);
    this.bulb       = HL.flatDot(this.g, this.C, 1.2, "dot m");
    this.shade      = HL.solid(this.g);
    this.arm        = HL.solid(this.g);
    this.level      = HL.tween(ReceptiveFieldFigure.REST);
    this.drawnLevel = NaN;
    this.headY      = ReceptiveFieldFigure.LAYERS.map((z) => this.P(this.centre, this.centre, z)[1]);
  }

  _tick(dt, now) {
    const moving = this._advance(this.tiles, now);
    const level  = HL.tval(this.level, now);
    if (level !== this.drawnLevel) {
      this.drawnLevel = level;
      this._drawLamp(level);
    }
    return moving || !HL.tdone(this.level, now);
  }

  _draw(tile, lift) {
    HL.put(tile.el, HL.prism(this.P, this.front, tile.ring, tile.inner, 0, ReceptiveFieldFigure.DEPTH + lift));
  }

  _drawLamp(level) {
    const layers   = ReceptiveFieldFigure.LAYERS;
    const low      = Math.min(layers.length - 2, Math.floor(level));
    const z        = HL.lerp(layers[low], layers[low + 1], level - low);
    const c        = this.centre;
    const head     = this._shifted(c, c, 0);
    const foot     = HL.circ(ReceptiveFieldFigure.SHADE, 48);
    const crown    = HL.circ(2.4, 32);
    const [px, py] = this.pole;
    const r0       = (px - py) * Math.SQRT1_2;
    const d        = (c + c) * Math.SQRT1_2;
    const half     = (level + 0.5) * ReceptiveFieldFigure.CELL - (ReceptiveFieldFigure.CELL - ReceptiveFieldFigure.TILE) / 2;
    const ground   = ReceptiveFieldFigure.DEPTH + this.amount;
    const rim      = ReceptiveFieldFigure.SHADE * Math.SQRT1_2;
    const lines    = [[-1, -1], [1, -1], [1, 1], [-1, 1]].map(([sx, sy]) => HL.seg(this.P(c + sx * rim, c + sy * rim, z), this.P(c + sx * half, c + sy * half, ground)));
    this.beam.setAttribute("d", lines.join(""));
    HL.put(this.arm, HL.prism(this.P, this.front, this._screenBox(r0, d - 1.1, 0, d + 1.1, 1), null, z + 6.2, z + 7.4));
    HL.put(this.shade, { sil: HL.poly(HL.hull(HL.ringAt(head, foot, z).concat(HL.ringAt(head, crown, z + 6.2)))), crease: HL.open(HL.ringAt(head, HL.run(HL.circ(1.7, 32), this.front), z + 6.2)) });
    HL.place(this.bulb, this.P(c, c, z - 0.6));
  }

  _move(p) {
    this._choose(HairlineFigureBase.nearest(this.headY, p[1]));
  }

  _retarget(now) {
    const layer = this.chosen === null ? ReceptiveFieldFigure.REST : this.chosen;
    const grows = layer > this.layer;
    this.layer  = layer;
    HL.tset(this.level, layer, now, 0);
    for (const tile of this.tiles) {
      const delay = grows ? tile.reach * ReceptiveFieldFigure.STAGGER : Math.max(0, ReceptiveFieldFigure.N - tile.reach) * ReceptiveFieldFigure.STAGGER * 0.5;
      HL.tset(tile.tw, this._lift(tile.reach, layer), now, delay);
      tile.el.sil.classList.toggle("hi", tile.reach === layer);
    }
    this.loop.wake();
  }
}

class WatchdogFigure extends HairlineFigureBase {
  static RANGE    = [0.5, 0.9, 1.4];
  static RING     = 29;
  static PLINTH   = 40;
  static PUCK     = 5.2;
  static RISE     = [1.5, 5, 1.3];
  static SPOT     = 6.5;
  static POLE     = 36;
  static PIVOT    = 2.6;
  static BODY     = [6.4, 5.6, 5, 8];
  static LENS     = [2.2, 2.2];
  static DROOP    = 1.25;
  static LINGER   = [0.3, 0.45];
  static CATCH    = 0.05;
  static HOLD_MS  = 2600;
  static SAMPLE   = [0.42, 0.55, 0.62, 0.58];
  static LIMITS   = [0.9, 0.8, 0.8, 0.9];
  static ANGLES   = [-0.75 * Math.PI, -0.25 * Math.PI, 0.25 * Math.PI, 0.75 * Math.PI];
  static LEVEL_MS = 700;

  constructor({ stage, svg }, value) {
    super(svg, value, 3.5);
    this.armed  = true;
    this.alerts = WatchdogFigure.SAMPLE.map(() => false);
    this.seen   = null;
    this.tip    = [0, 0];
    this.hold   = null;
    this.passed = null;
    this._camera(this._extent(), 178);
    this._buildPlinth();
    this._buildTargets();
    this._buildCamera();
    this.turn  = HL.spring(WatchdogFigure.ANGLES[0] - 0.6, { k: 40, c: 12, eps: 0.001 });
    this.pitch = HL.spring(this._aimPitch(), { k: 40, c: 12, eps: 0.001 });
    this._start(stage, svg);
    this._retarget();
  }

  _extent() {
    const r = WatchdogFigure.PLINTH;
    return WatchdogFigure.ANGLES.map((a) => [r * Math.cos(a), r * Math.sin(a), -3]).concat([[0, 0, WatchdogFigure.POLE + WatchdogFigure.PIVOT + 5]]);
  }

  _buildPlinth() {
    const ring  = WatchdogFigure.RING;
    const patrol = Array.from({ length: 97 }, (_, k) => this.P(ring * Math.cos((2 * Math.PI * k) / 96), ring * Math.sin((2 * Math.PI * k) / 96), 0));
    HL.put(HL.solid(this.g), HL.prism(this.P, this.front, HL.circ(WatchdogFigure.PLINTH, 96), HL.circ(WatchdogFigure.PLINTH - 2.2, 96), -3, 0));
    HL.mk("path", { d: HL.open(patrol), class: "dash nf" }, this.g);
    this.spot = HL.mk("path", { class: "nf" }, this.g);
  }

  _buildTargets() {
    this.ring    = HL.circ(WatchdogFigure.PUCK, 48);
    this.inner   = HL.circ(WatchdogFigure.PUCK - 1, 48);
    this.targets = WatchdogFigure.ANGLES.map((a, k) => {
      const x = WatchdogFigure.RING * Math.cos(a);
      const y = WatchdogFigure.RING * Math.sin(a);
      return { k, a, x, y, P: this._shifted(x, y, 0), level: HL.tween(WatchdogFigure.SAMPLE[k] / WatchdogFigure.LIMITS[k], WatchdogFigure.LEVEL_MS), drawn: NaN };
    });
    for (const target of [...this.targets].sort((p, q) => p.x + p.y - (q.x + q.y))) {
      const group  = HL.mk("g", {}, this.g);
      target.puck  = HL.solid(group);
      target.rings = HL.mk("path", { class: "nf lo" }, group);
      target.dot   = HL.flatDot(group, this.C, 1, "dot off");
    }
  }

  _buildCamera() {
    HL.put(HL.solid(this.g), HL.prism(this.P, this.front, HL.circ(3.6, 40), HL.circ(2.6, 40), 0, 1.2));
    HL.put(HL.solid(this.g), HL.prism(this.P, this.front, HL.rrect(-1, -1, 1, 1, 0.4, 2), null, 1.2, WatchdogFigure.POLE));
    HL.put(HL.solid(this.g), HL.prism(this.P, this.front, HL.circ(1.8, 24), null, WatchdogFigure.POLE - 0.4, WatchdogFigure.POLE + 0.8));

    this.lensBack  = HL.mk("g", {}, this.g);
    this.body      = HL.solid(this.g);
    this.lensFront = HL.mk("g", {}, this.g);
    this.lensGroup = HL.mk("g", {}, this.lensFront);
    this.cone      = HL.mk("path", { class: "dash nf" }, this.lensGroup);
    this.lens      = HL.solid(this.lensGroup);
    this.eye       = HL.flatDot(this.lensGroup, this.C, 0.9, "dot");
  }

  _aimPitch() {
    return Math.atan2(WatchdogFigure.POLE + WatchdogFigure.PIVOT, WatchdogFigure.RING);
  }

  _tick(dt, now) {
    for (const target of this.targets) {
      const level = HL.tval(target.level, now);
      if (level === target.drawn) continue;
      target.drawn = level;
      this._drawTarget(target, level);
    }
    this._steer(dt, now);
    HL.stepS(this.pitch, dt);
    this._drawCamera(this.turn.x, this.pitch.x);
    this._drawBeam();
    this._spotTargets();
    return true;
  }

  _drawTarget(target, level) {
    const [base, rise, cap] = WatchdogFigure.RISE;
    const h                 = base + rise * Math.min(cap, level);
    const rings             = [3.2, 1.6].map((radius) => HL.poly(HL.circ(radius, 32).map((q) => target.P(q.u, q.v, h)))).join("");
    HL.put(target.puck, HL.prism(target.P, this.front, this.ring, this.inner, 0, h));
    target.rings.setAttribute("d", rings);
    HL.place(target.dot, target.P(0, 0, h));
  }

  _steer(dt, now) {
    this._catch(now);
    const goal = this._goal();
    if (goal !== null) {
      this.turn.t = this.turn.x + this._wrap(goal - this.turn.x);
      HL.stepS(this.turn, dt);
      return;
    }

    const [floor, width] = WatchdogFigure.LINGER;
    const near           = Math.min(...this.targets.map((target) => Math.abs(this._wrap(target.a - this.turn.x))));
    const speed          = this.amount * (floor + (1 - floor) * HL.clamp(near / width, 0, 1));
    this.turn.x         += speed * dt;
    this.turn.t          = this.turn.x;
    this.turn.v          = speed;
  }

  _catch(now) {
    if (this.hold !== null && (now >= this.hold.until || !this.alerts[this.hold.k])) {
      this.passed = this.hold.k;
      this.hold   = null;
    }
    if (this.passed !== null && Math.abs(this._wrap(this.targets[this.passed].a - this.turn.x)) > WatchdogFigure.LINGER[1]) this.passed = null;
    if (this.hold !== null || this.chosen !== null || !this.armed) return;

    const caught = this.targets.find((target) => this.alerts[target.k] && target.k !== this.passed && Math.abs(this._wrap(target.a - this.turn.x)) < WatchdogFigure.CATCH);
    if (caught) this.hold = { k: caught.k, until: now + WatchdogFigure.HOLD_MS };
  }

  _goal() {
    if (!this.armed) return this.turn.x;
    if (this.chosen !== null) return this.targets[this.chosen].a;
    if (this.hold !== null) return this.targets[this.hold.k].a;
    return null;
  }

  _wrap(angle) {
    return Math.atan2(Math.sin(angle), Math.cos(angle));
  }

  _drawCamera(yaw, pitch) {
    const at                  = this._cameraAt(yaw, pitch);
    const [w, h, back, front] = WatchdogFigure.BODY;
    const [radius, length]    = WatchdogFigure.LENS;
    const home                = Math.cos(yaw) + Math.sin(yaw) < 0 ? this.lensBack : this.lensFront;
    HL.put(this.body, HL.prism(at, this.front, HL.rrect(-w / 2, -h / 2, w / 2, h / 2, 1.1, 3), null, -back, front));
    HL.put(this.lens, HL.prism(at, this.front, HL.circ(radius, 24), null, front, front + length));
    this.tip = at(0, 0, front + length);
    HL.place(this.eye, this.tip);
    if (this.lensGroup.parentNode !== home) home.appendChild(this.lensGroup);
  }

  _cameraAt(yaw, pitch) {
    const forward = [Math.cos(yaw) * Math.cos(pitch), Math.sin(yaw) * Math.cos(pitch), -Math.sin(pitch)];
    const right   = [-Math.sin(yaw), Math.cos(yaw), 0];
    const up      = [Math.cos(yaw) * Math.sin(pitch), Math.sin(yaw) * Math.sin(pitch), Math.cos(pitch)];
    const z0      = WatchdogFigure.POLE + WatchdogFigure.PIVOT;
    return (u, v, w) => this.P(u * right[0] + v * up[0] + w * forward[0], u * right[1] + v * up[1] + w * forward[1], z0 + v * up[2] + w * forward[2]);
  }

  _drawBeam() {
    if (!this.armed) {
      this.spot.setAttribute("d", "");
      this.cone.setAttribute("d", "");
      return;
    }

    const cx     = WatchdogFigure.RING * Math.cos(this.turn.x);
    const cy     = WatchdogFigure.RING * Math.sin(this.turn.x);
    const spot   = Array.from({ length: 33 }, (_, k) => this.P(cx + WatchdogFigure.SPOT * Math.cos((2 * Math.PI * k) / 32), cy + WatchdogFigure.SPOT * Math.sin((2 * Math.PI * k) / 32), 0));
    const angles = spot.map((p) => Math.atan2(p[1] - this.tip[1], p[0] - this.tip[0]));
    const left   = spot[angles.indexOf(Math.min(...angles))];
    const right  = spot[angles.indexOf(Math.max(...angles))];
    const locked = this.chosen === null && this.hold !== null;
    this.spot.setAttribute("d", HL.open(spot));
    this.cone.setAttribute("d", HL.seg(this.tip, left) + HL.seg(this.tip, right));
    this.spot.setAttribute("class", locked ? "nf hi" : "nf");
    this.cone.setAttribute("class", locked ? "nf hi" : "dash nf");
  }

  _spotTargets() {
    const reach = (WatchdogFigure.SPOT + 0.6 * WatchdogFigure.PUCK) / WatchdogFigure.RING;
    const hit   = this.targets.find((target) => Math.abs(this._wrap(target.a - this.turn.x)) < reach);
    const seen  = this.armed && hit ? hit.k : null;
    if (seen === this.seen) return;
    this.seen = seen;
    this._paint();
  }

  _paint() {
    for (const target of this.targets) {
      target.puck.sil.classList.toggle("hi", target.k === this.seen);
      target.dot.setAttribute("class", this.alerts[target.k] ? "dot" : target.k === this.seen ? "dot m" : "dot off");
    }
    this.eye.setAttribute("class", this.armed ? "dot" : "dot off");
  }

  _move(p) {
    const [x, y] = HL.unproj(this.C, p[0], p[1], 0);
    if (Math.hypot(x, y) < 8) return;
    const angle = Math.atan2(y, x);
    this._choose(HairlineFigureBase.nearest(this.targets.map((target) => Math.abs(this._wrap(target.a - angle))), 0));
  }

  setState(state) {
    if (!Array.isArray(state.gauges) || state.gauges.length !== this.targets.length) throw new Error(`watchdog figure: state.gauges must hold ${this.targets.length} gauges`);
    const now   = performance.now();
    this.armed  = !!state.armed;
    this.alerts = state.gauges.map((reading) => !!reading.alert);
    state.gauges.forEach((reading, k) => HL.tset(this.targets[k].level, Math.max(0, reading.level) / reading.limit, now, 0));
    this._retarget();
  }

  _retarget() {
    this.pitch.t = this.armed ? this._aimPitch() : WatchdogFigure.DROOP;
    this._paint();
    this.loop.wake();
  }
}

class NotifyFigure extends HairlineFigureBase {
  static RANGE      = [3, 5, 8];
  static PLINTH     = [-28, -16, 26, 14];
  static TOWER      = [-24, -14, -10, -2, 24];
  static DOCK       = [5, 3, 23, 10, 3];
  static HANDSET    = [6.5, 5.1, 21.5, 7.9, 26];
  static SLOTS      = 3;
  static CARD       = [5.7, 4.6, 0.8];
  static PITCH      = 6.4;
  static ENVELOPE   = [2.8, 1.9, 0.6];
  static ARC        = 8;
  static REST       = 1;
  static CADENCE_MS = 3400;
  static FLIGHT_MS  = 1400;

  constructor({ stage, svg }, value) {
    super(svg, value, 4.4);
    this.armed = true;
    this.next  = 0;
    this.clock = performance.now();
    this._camera(this._extent(), 162);
    const [x0, y0, x1, y1] = NotifyFigure.PLINTH;
    this._plinth(x0, y0, x1, y1, 6, 3);
    this._buildParts();
    this._buildEnvelope();
    this.cards = [this._card(1, 1), this._card(0, 1)];
    this._start(stage, svg);
    this._retarget(performance.now());
  }

  _extent() {
    const [x0, y0, x1, y1]       = NotifyFigure.PLINTH;
    const [tx0, ty0, tx1, ty1, th] = NotifyFigure.TOWER;
    const [hx0, hy0, hx1, hy1, hh] = NotifyFigure.HANDSET;
    const lift                   = NotifyFigure.RANGE[2];
    const apex                   = NotifyFigure.DOCK[4] + hh + NotifyFigure.ARC + NotifyFigure.ENVELOPE[1] + 1.5;
    return [[x0, y0, -3], [x1, y1, -3], [x1, y0, -3], [x0, y1, -3], [tx0, ty0, th + lift], [tx1, ty1, th + lift], [hx0, hy0, NotifyFigure.DOCK[4] + hh + lift], [hx1, hy1, NotifyFigure.DOCK[4] + hh + lift], [(tx0 + tx1 + hx0 + hx1) / 4, (ty0 + ty1 + hy0 + hy1) / 4, apex]];
  }

  _buildParts() {
    const [tx0, ty0, tx1, ty1] = NotifyFigure.TOWER;
    const [dx0, dy0, dx1, dy1, dh] = NotifyFigure.DOCK;
    const [hx0, hy0, hx1, hy1] = NotifyFigure.HANDSET;
    const server = { k: 0, group: HL.mk("g", {}, this.g), tw: HL.tween(0), drawn: NaN, cx: (tx0 + tx1) / 2, cy: (ty0 + ty1) / 2 };
    const phone  = { k: 1, group: HL.mk("g", {}, this.g), tw: HL.tween(0), drawn: NaN, cx: (hx0 + hx1) / 2, cy: (hy0 + hy1) / 2 };
    server.restX  = this.P(server.cx, server.cy, 0)[0];
    phone.restX   = this.P(phone.cx, phone.cy, 0)[0];
    server.rings  = HL.rings(tx0, ty0, tx1, ty1, 1.6, 1);
    server.main   = HL.solid(server.group);
    server.lines  = HL.mk("path", { class: "nf lo" }, server.group);
    server.led    = HL.flatDot(server.group, this.C, 0.9, "dot m");
    HL.put(HL.solid(phone.group), HL.prism(this.P, this.front, ...HL.rings(dx0, dy0, dx1, dy1, 1.4, 0.8), 0, dh));
    phone.rings   = HL.rings(hx0, hy0, hx1, hy1, 1.2, 0.6);
    phone.main    = HL.solid(phone.group);
    phone.screen  = HL.mk("path", { class: "nf lo" }, phone.group);
    this.cardBox  = HL.mk("g", {}, phone.group);
    this.parts    = [server, phone];
  }

  _buildEnvelope() {
    this.envelope = { el: HL.solid(this.g), flap: HL.mk("path", { class: "nf lo" }, this.g), t0: null };
  }

  _card(slot, grow) {
    const el    = HL.solid(this.cardBox);
    const lines = HL.mk("path", { class: "nf lo" }, this.cardBox);
    return { el, lines, slot: HL.tween(slot, 520), grow: HL.tween(grow, 420) };
  }

  _tick(dt, now) {
    this.clock          = now;
    this.parts[1].drawn = NaN;
    this._send(now);
    this._advance(this.parts, now);
    this._fly(now);
    return true;
  }

  _send(now) {
    if (!this.armed || now < this.next || this.envelope.t0 !== null) return;
    this.next        = now + NotifyFigure.CADENCE_MS;
    this.envelope.t0 = now;
  }

  _draw(part, lift) {
    if (part.k === 0) this._drawServer(part, lift);
    if (part.k === 1) this._drawPhone(part, lift);
  }

  _drawServer(part, lift) {
    const [x0, , x1, y1, h] = NotifyFigure.TOWER;
    HL.put(part.main, HL.prism(this.P, this.front, ...part.rings, lift, lift + h));
    part.lines.setAttribute("d", [6, 11.5, 17].map((z) => HL.seg(this.P(x0 + 1.6, y1, lift + z), this.P(x1 - 1.6, y1, lift + z))).join(""));
    HL.place(part.led, this.P(x1 - 2.4, y1, lift + h - 3));
  }

  _drawPhone(part, lift) {
    const [x0, , x1, y1, h] = NotifyFigure.HANDSET;
    const z0                = NotifyFigure.DOCK[4] + lift;
    HL.put(part.main, HL.prism(this.P, this.front, ...part.rings, z0, z0 + h));
    part.screen.setAttribute("d", HL.poly([this.P(x0 + 1.4, y1, z0 + 2.6), this.P(x1 - 1.4, y1, z0 + 2.6), this.P(x1 - 1.4, y1, z0 + h - 2.2), this.P(x0 + 1.4, y1, z0 + h - 2.2)]));
    this._drawCards(z0 + h - 4, this.clock);
  }

  _drawCards(top, now) {
    const [w, h, t] = NotifyFigure.CARD;
    const [x0, , x1, y1] = NotifyFigure.HANDSET;
    const cx        = (x0 + x1) / 2;
    const ring      = HL.rings(cx - w, y1, cx + w, y1 + t, 0.5, 0.2)[0];
    const face      = (x, z) => this.P(x, y1 + t, z);
    for (const card of this.cards) {
      const grow = HL.tval(card.grow, now);
      const z1   = top - HL.tval(card.slot, now) * NotifyFigure.PITCH;
      const z0   = z1 - h * grow;
      HL.put(card.el, grow < 0.05 ? { sil: "", crease: "" } : HL.prism(this.P, this.front, ring, null, z0, z1));
      card.lines.setAttribute("d", grow < 0.9 ? "" : HL.seg(face(cx - w + 1.3, z1 - 1.5), face(cx + w - 4.6, z1 - 1.5)) + HL.seg(face(cx - w + 1.3, z1 - 3.2), face(cx + w - 1.3, z1 - 3.2)));
    }
    this._prune(now);
  }

  _prune(now) {
    const gone = this.cards.filter((card) => card.grow.to === 0 && HL.tdone(card.grow, now));
    for (const card of gone) {
      card.el.g.remove();
      card.lines.remove();
    }
    this.cards = this.cards.filter((card) => !gone.includes(card));
  }

  _fly(now) {
    const envelope = this.envelope;
    if (envelope.t0 === null) return;
    const s = (now - envelope.t0) / NotifyFigure.FLIGHT_MS;
    if (s >= 1) {
      envelope.t0 = null;
      this._hide();
      this._deliver(now);
      return;
    }
    this._drawEnvelope(this._along(now, 0.5 - 0.5 * Math.cos(Math.PI * s)));
  }

  _along(now, f) {
    const [server, phone] = this.parts;
    const a               = [server.cx, server.cy, NotifyFigure.TOWER[4] + HL.tval(server.tw, now) + 1.5];
    const b               = [phone.cx, phone.cy, NotifyFigure.DOCK[4] + NotifyFigure.HANDSET[4] + HL.tval(phone.tw, now) + 1.5];
    const m               = [(a[0] + b[0]) / 2, (a[1] + b[1]) / 2, Math.max(a[2], b[2]) + NotifyFigure.ARC];
    const w               = 1 - f;
    return [0, 1, 2].map((i) => w * w * a[i] + 2 * w * f * m[i] + f * f * b[i]);
  }

  _drawEnvelope(at) {
    const [w, h, t] = NotifyFigure.ENVELOPE;
    const P         = this._shifted(at[0], at[1], at[2]);
    HL.put(this.envelope.el, HL.prism(P, this.front, HL.rings(-w, -t, w, t, 0.3, 0.1)[0], null, -h, h));
    this.envelope.flap.setAttribute("d", HL.open([P(-w + 0.3, t, h - 0.2), P(0, t, -0.2), P(w - 0.3, t, h - 0.2)]));
  }

  _hide() {
    HL.put(this.envelope.el, { sil: "", crease: "" });
    this.envelope.flap.setAttribute("d", "");
  }

  _deliver(now) {
    for (const card of this.cards) {
      HL.tset(card.slot, card.slot.to + 1, now, 0);
      if (card.slot.to >= NotifyFigure.SLOTS) HL.tset(card.grow, 0, now, 0);
    }
    const card = this._card(0, 0);
    HL.tset(card.grow, 1, now, 80);
    this.cards.push(card);
  }

  _move(p) {
    this._choose(HairlineFigureBase.nearest(this.parts.map((part) => part.restX), p[0]));
  }

  setState(state) {
    const armed = !!state.armed;
    if (armed === this.armed) return;
    const now  = performance.now();
    this.armed = armed;
    this.next  = now + 700;
    this.parts[0].led.setAttribute("class", armed ? "dot m" : "dot off");
    if (!armed) {
      this.envelope.t0 = null;
      this._hide();
      for (const card of this.cards) HL.tset(card.grow, 0, now, 0);
    }
    this.loop.wake();
  }

  _retarget(now) {
    const anchor = this.chosen === null ? NotifyFigure.REST : this.chosen;
    for (const part of this.parts) {
      HL.tset(part.tw, this.chosen !== null && part.k === anchor ? this.amount : 0, now, 0);
      part.main.sil.classList.toggle("hi", part.k === anchor);
    }
    this.loop.wake();
  }
}

class NukeFigure extends HairlineFigureBase {
  static RANGE      = [3, 5, 8];
  static PLINTH     = [-17, -11, 12, 11];
  static BOX        = [-10, 4, 4, 3.5, 6];
  static ROD        = [0.9, 8];
  static HANDLE     = [4, 0.9, 1.5];
  static DRUM       = [3, -2, 6.5, 12];
  static BANDS      = [0.42, 0.56];
  static TREFOIL    = [1.1, 2, 4.8, 30];
  static CLOUD      = [2.6, 8.5, 11, 16];
  static WAVE       = [6.5, 24];
  static WIRE       = [[-6, 5], [-1.5, 8.5], [3, 4.6]];
  static PRESS_MS   = 260;
  static PULSE_MS   = 450;
  static WAVE_MS    = 1000;
  static HOLD_MS    = 2200;
  static BLINK_MS   = 1600;
  static ids        = 0;

  constructor({ stage, svg }, value) {
    super(svg, value, 7.4);
    this.firing   = false;
    this.fired    = null;
    this.released = null;
    this.down     = false;
    this.wave     = null;
    this.cloud    = HL.tween(0, 700);
    this.plunger  = HL.spring(1, { k: 50, c: 11, eps: 0.002 });
    const pts = this._extent();
    this._camera(pts, 320 - this._height(pts) / 2 - 6);
    this._buildPlinth(svg);
    this._buildWire();
    this._buildDrum();
    this._buildDetonator();
    this._buildCloud();
    this.parts = [this.det, this.drum];
    this._start(stage, svg);
    this._retarget(performance.now());
  }

  _extent() {
    const [r0, d0, r1, d1]  = NukeFigure.PLINTH;
    const [br, bd, , , bh]  = NukeFigure.BOX;
    const [dr, dd, R, H]    = NukeFigure.DRUM;
    const lift              = NukeFigure.RANGE[2];
    const top               = bh + 1.5 + NukeFigure.ROD[1] + NukeFigure.HANDLE[2] + lift;
    const cap               = NukeFigure.CLOUD[1];
    const crown             = H + NukeFigure.CLOUD[3];
    const floor             = [[r0, d0], [r1, d0], [r0, d1], [r1, d1]].map(([r, d]) => [...this._onScreen(r, d), -3]);
    const cloud             = [[dr - cap, dd], [dr + cap, dd], [dr, dd - cap], [dr, dd + cap]].map(([r, d]) => [...this._onScreen(r, d), crown]);
    return floor.concat([[...this._onScreen(br, bd), top], [...this._onScreen(dr, dd), H + lift]], cloud);
  }

  _buildPlinth(svg) {
    const [r0, d0, r1, d1] = NukeFigure.PLINTH;
    const ring             = this._screenBox(r0, d0, r1, d1, 6);
    HL.put(HL.solid(this.g), HL.prism(this.P, this.front, ring, this._screenBox(r0 + 2.2, d0 + 2.2, r1 - 2.2, d1 - 2.2, 4), -3, 0));
    const id   = `nk-top-${++NukeFigure.ids}`;
    const clip = HL.mk("clipPath", { id }, HL.mk("defs", {}, svg));
    HL.mk("path", { d: HL.poly(HL.ringAt(this.P, ring, 0)) }, clip);
    this.clip = `url(#${id})`;
  }

  _buildWire() {
    const [a, m, b] = NukeFigure.WIRE;
    const pts       = Array.from({ length: 17 }, (_, k) => {
      const f = k / 16;
      const w = 1 - f;
      return [w * w * a[0] + 2 * w * f * m[0] + f * f * b[0], w * w * a[1] + 2 * w * f * m[1] + f * f * b[1]];
    });
    const cum = [0];
    for (let i = 1; i < pts.length; i++) cum.push(cum[i - 1] + Math.hypot(pts[i][0] - pts[i - 1][0], pts[i][1] - pts[i - 1][1]));
    this.wire = { pts, cum };
    HL.mk("path", { d: HL.open(pts.map(([r, d]) => this.P(...this._onScreen(r, d), 0.3))), class: "nf lo" }, this.g);
    this.ripple = HL.mk("path", { class: "nf hi", "clip-path": this.clip }, this.g);
    this.pulse  = HL.flatDot(this.g, this.C, 1.2, "dot");
    this.pulse.setAttribute("display", "none");
  }

  _alongWire(f) {
    const { pts, cum } = this.wire;
    const s            = HL.clamp(f, 0, 1) * cum[cum.length - 1];
    let i              = 1;
    while (i < cum.length - 1 && cum[i] < s) i++;
    const t = (s - cum[i - 1]) / (cum[i] - cum[i - 1]);
    return [HL.lerp(pts[i - 1][0], pts[i][0], t), HL.lerp(pts[i - 1][1], pts[i][1], t)];
  }

  _buildDrum() {
    const [r, d, R] = NukeFigure.DRUM;
    const [x, y]    = this._onScreen(r, d);
    const group     = HL.mk("g", {}, this.g);
    const el        = HL.solid(group);
    this.drum = { k: 1, x, y, el, sils: [el], ring: HL.circ(R, 48), inner: HL.circ(R - 1, 48), bands: HL.mk("path", { class: "dash nf" }, group), trefoil: HL.mk("path", { class: "nf" }, group), hub: HL.mk("path", { class: "nf" }, group), live: false, tw: HL.tween(0), drawn: null, restX: this.P(x, y, 0)[0] };
  }

  _buildDetonator() {
    const [r, d] = NukeFigure.BOX;
    const [x, y] = this._onScreen(r, d);
    const group  = HL.mk("g", {}, this.g);
    const el     = HL.solid(group);
    const rod    = HL.solid(group);
    const handle = HL.solid(group);
    this.det = { k: 0, x, y, el, rod, handle, sils: [el, rod, handle], lamp: HL.flatDot(group, this.C, 0.8, "dot m"), cls: "dot m", tw: HL.tween(0), drawn: null, restX: this.P(x, y, 0)[0] };
  }

  _buildCloud() {
    const group = HL.mk("g", {}, this.g);
    this.stem   = HL.solid(group);
    this.cap    = HL.solid(group);
    this.cloudDrawn = null;
  }

  _tick(dt, now) {
    this._sequence(now);
    HL.stepS(this.plunger, dt);
    this._drawDrum(now);
    this._drawDetonator(now);
    this._drawCloud(now);
    this._drawWave(now);
    return true;
  }

  _sequence(now) {
    if (this.fired === null) return;
    const t   = now - this.fired;
    const p0  = NukeFigure.PRESS_MS;
    const p1  = p0 + NukeFigure.PULSE_MS;
    const fly = !this.down && t >= p0 && t < p1 && !HL.reducedMotion();
    if (fly) {
      HL.place(this.pulse, this.P(...this._onScreen(...this._alongWire((t - p0) / NukeFigure.PULSE_MS)), 0.3));
      this.pulse.removeAttribute("display");
    } else {
      this.pulse.setAttribute("display", "none");
    }
    if (!this.down && t >= p1) {
      this.down = true;
      this.wave = now;
      HL.tset(this.cloud, 1, now, 0);
    }
    const settled = this.down && t >= p1 + NukeFigure.HOLD_MS && this.released !== null && now - this.released >= 400;
    if (settled) {
      this.fired     = null;
      this.down      = false;
      this.plunger.k = 50;
      this.plunger.c = 11;
      this.plunger.t = 1;
      HL.tset(this.cloud, 0, now, 0);
    }
  }

  _drawDrum(now) {
    const drum = this.drum;
    const lift = HL.tval(drum.tw, now);
    const key  = lift.toFixed(3);
    if (key !== drum.drawn) {
      drum.drawn = key;
      const [, , , H]          = NukeFigure.DRUM;
      const [hub, ri, ro, half] = NukeFigure.TREFOIL;
      const P                   = this._shifted(drum.x, drum.y, lift);
      const face                = HL.run(drum.ring, this.front);
      HL.put(drum.el, HL.prism(P, this.front, drum.ring, drum.inner, 0, H));
      drum.bands.setAttribute("d", NukeFigure.BANDS.map((at) => HL.open(HL.ringAt(P, face, H * at))).join(""));
      drum.trefoil.setAttribute("d", [90, 210, 330].map((a0) => {
        const pts = [];
        for (let k = 0; k <= 6; k++) {
          const a = HL.rad(a0 - half + (2 * half * k) / 6);
          pts.push(P(ri * Math.cos(a), ri * Math.sin(a), H));
        }
        for (let k = 6; k >= 0; k--) {
          const a = HL.rad(a0 - half + (2 * half * k) / 6);
          pts.push(P(ro * Math.cos(a), ro * Math.sin(a), H));
        }
        return HL.poly(pts);
      }).join(""));
      drum.hub.setAttribute("d", HL.poly(HL.ringAt(P, HL.circ(hub, 16), H)));
    }
    const live = this.fired !== null;
    if (live !== drum.live) {
      drum.live = live;
      drum.trefoil.setAttribute("class", live ? "nf hi" : "nf");
      drum.hub.setAttribute("class", live ? "nf hi" : "nf");
    }
  }

  _drawDetonator(now) {
    const det   = this.det;
    const lift  = HL.tval(det.tw, now);
    const press = Math.max(0, this.plunger.x);
    const key   = `${lift.toFixed(3)}:${press.toFixed(3)}`;
    if (key !== det.drawn) {
      det.drawn = key;
      const [, , w, dd, h] = NukeFigure.BOX;
      const [rr, stroke]   = NukeFigure.ROD;
      const [hl, ht, hz]   = NukeFigure.HANDLE;
      const P              = this._shifted(det.x, det.y, lift);
      const top            = h + 1.5 + stroke * press;
      HL.put(det.el, HL.prism(P, this.front, this._screenBox(-w, -dd, w, dd, 1.2), this._screenBox(-w + 0.8, -dd + 0.8, w - 0.8, dd - 0.8, 0.8), 0, h));
      HL.put(det.rod, HL.prism(P, this.front, HL.circ(rr, 24), null, h, top));
      HL.put(det.handle, HL.prism(P, this.front, this._screenBox(-hl, -ht, hl, ht, 0.7), this._screenBox(-hl + 0.4, -ht + 0.4, hl - 0.4, ht - 0.4, 0.4), top, top + hz));
      HL.place(det.lamp, P(...this._onScreen(w - 1.6, dd - 1.6), h));
    }
    const cls = this.fired !== null ? "dot" : now % NukeFigure.BLINK_MS < NukeFigure.BLINK_MS * 0.7 ? "dot m" : "dot off";
    if (cls !== det.cls) {
      det.cls = cls;
      det.lamp.setAttribute("class", cls);
    }
  }

  _drawCloud(now) {
    const g    = HL.tval(this.cloud, now);
    const lift = HL.tval(this.drum.tw, now);
    const key  = `${g.toFixed(3)}:${lift.toFixed(3)}`;
    if (key === this.cloudDrawn) return;
    this.cloudDrawn = key;
    if (g < 0.03) {
      HL.put(this.stem, { sil: "", crease: "" });
      HL.put(this.cap, { sil: "", crease: "" });
      return;
    }
    const [, , , H]                 = NukeFigure.DRUM;
    const [stemR, capR, rise0, rise1] = NukeFigure.CLOUD;
    const P                         = this._shifted(this.drum.x, this.drum.y, lift);
    const swell                     = 0.35 + 0.65 * g;
    const z0                        = H + rise0 * g;
    const z1                        = H + rise1 * g;
    HL.put(this.stem, HL.prism(P, this.front, HL.circ(stemR * swell, 24), null, H, z0 + 1));
    HL.put(this.cap, HL.prism(P, this.front, HL.circ(capR * swell, 40), HL.circ((capR - 1.5) * swell, 40), z0, z1));
  }

  _drawWave(now) {
    if (this.wave === null) return;
    const s = (now - this.wave) / NukeFigure.WAVE_MS;
    if (s >= 1 || HL.reducedMotion()) {
      this.wave = null;
      this.ripple.setAttribute("d", "");
      return;
    }
    const [w0, w1] = NukeFigure.WAVE;
    const P        = this._shifted(this.drum.x, this.drum.y, 0);
    this.ripple.setAttribute("d", HL.poly(HL.ringAt(P, HL.circ(HL.lerp(w0, w1, s), 72), 0.2)));
  }

  _move(p) {
    this._choose(this.parts[HairlineFigureBase.nearest(this.parts.map((part) => part.restX), p[0])].k);
  }

  setState(state) {
    const firing = !!state.firing;
    if (firing === this.firing) return;
    const now   = performance.now();
    this.firing = firing;
    if (firing) {
      this.released = null;
      if (this.fired === null) {
        this.fired     = now;
        this.down      = false;
        this.plunger.k = 160;
        this.plunger.c = 14;
        this.plunger.t = 0;
      }
    } else {
      this.released = now;
    }
    this.loop.wake();
  }

  _retarget(now) {
    for (const part of this.parts) {
      const on = this.chosen === part.k;
      HL.tset(part.tw, on ? this.amount : 0, now, 0);
      for (const el of part.sils) el.sil.classList.toggle("hi", on);
    }
    this.loop.wake();
  }
}

class CoresFigure extends HairlineFigureBase {
  static RANGE  = [2, 4, 7];
  static CELL   = 10;
  static FOOT   = 7.4;
  static BASE   = 1.6;
  static RISE   = 26;
  static BUSY   = 50;
  static SPAN   = [372, 280];
  static SAMPLE = [35, 80, 12, 60, 95, 20, 48, 70];

  constructor({ stage, svg }, value) {
    super(svg, value, 2.7);
    this.loads = CoresFigure.SAMPLE.slice();
    this.count = this.loads.length;
    this._layout();
    this._start(stage, svg);
    this._retarget(performance.now());
  }

  _height(load) {
    return CoresFigure.BASE + (CoresFigure.RISE * HL.clamp(load, 0, 100)) / 100;
  }

  _layout() {
    this.g.replaceChildren();
    const n     = this.count;
    this.cols   = Math.max(1, Math.ceil(Math.sqrt(n * 2)));
    this.rows   = Math.max(1, Math.ceil(n / this.cols));
    this.width  = this.cols * CoresFigure.CELL;
    this.depth  = this.rows * CoresFigure.CELL;
    const peak  = CoresFigure.BASE + CoresFigure.RISE + CoresFigure.RANGE[2];
    const pts   = [[-4, -4, -4], [this.width + 4, this.depth + 4, -4], [this.width + 4, -4, -4], [-4, this.depth + 4, -4], [0, 0, peak], [this.width, this.depth, peak]];
    this.C.S    = 1;
    const unit  = HL.proj(this.C);
    const xs    = pts.map(([x, y, z]) => unit(x, y, z)[0]);
    const ys    = pts.map(([x, y, z]) => unit(x, y, z)[1]);
    this.C.S    = Math.min(CoresFigure.SPAN[0] / (Math.max(...xs) - Math.min(...xs)), CoresFigure.SPAN[1] / (Math.max(...ys) - Math.min(...ys)));
    this._camera(pts, 166);
    this._plinth(-4, -4, this.width + 4, this.depth + 4, 7, 4);
    const z       = this._height(CoresFigure.BUSY);
    const corners = [[-2, -2], [this.width + 2, -2], [this.width + 2, this.depth + 2], [-2, this.depth + 2]];
    HL.mk("path", { d: HL.poly(corners.map(([x, y]) => this.P(x, y, z))), class: "dash nf" }, this.g);
    const inset = (CoresFigure.CELL - CoresFigure.FOOT) / 2;
    this.pillars = [];
    for (let k = 0; k < n; k++) {
      const i             = k % this.cols;
      const j             = Math.floor(k / this.cols);
      const x0            = i * CoresFigure.CELL + inset;
      const y0            = j * CoresFigure.CELL + inset;
      const [ring, inner] = HL.rings(x0, y0, x0 + CoresFigure.FOOT, y0 + CoresFigure.FOOT, 1.8, 0.7);
      const at            = this.P(x0 + CoresFigure.FOOT / 2, y0 + CoresFigure.FOOT / 2, 0);
      this.pillars.push({ k, i, j, ring, inner, at, h: HL.tween(this._height(this.loads[k] || 0), 520), tw: HL.tween(0), drawn: null, busy: null, el: null });
    }
    this.pillars.sort((a, b) => a.i + a.j - (b.i + b.j));
    for (const pillar of this.pillars) pillar.el = HL.solid(this.g);
  }

  _tick(dt, now) {
    let moving = false;
    const busyAt = this._height(CoresFigure.BUSY) - 1e-6;
    for (const pillar of this.pillars) {
      const h    = HL.tval(pillar.h, now);
      const lift = HL.tval(pillar.tw, now);
      if (!HL.tdone(pillar.h, now) || !HL.tdone(pillar.tw, now)) moving = true;
      const key = `${h.toFixed(2)}:${lift.toFixed(2)}`;
      if (key !== pillar.drawn) {
        pillar.drawn = key;
        HL.put(pillar.el, HL.prism(this.P, this.front, pillar.ring, pillar.inner, lift, lift + h));
      }
      const busy = pillar.h.to >= busyAt;
      if (busy !== pillar.busy) {
        pillar.busy = busy;
        pillar.el.cr.setAttribute("class", busy ? "nf hi" : "nf lo");
      }
    }
    return moving;
  }

  _move(p) {
    let best = null;
    let near = Infinity;
    for (const pillar of this.pillars) {
      const d = Math.hypot(pillar.at[0] - p[0], pillar.at[1] - p[1]);
      if (d < near) {
        near = d;
        best = pillar;
      }
    }
    if (best) this._choose(best.k);
  }

  setState(state) {
    if (!Array.isArray(state.cores)) throw new Error("cores figure: state.cores must be an array of busy percentages");
    const loads = state.cores.map((u) => HL.clamp(Number(u) || 0, 0, 100));
    const now   = performance.now();
    this.loads  = loads;
    if (loads.length !== this.count) {
      this.count  = Math.max(1, loads.length);
      this.chosen = null;
      this._layout();
    } else {
      for (const pillar of this.pillars) HL.tset(pillar.h, this._height(loads[pillar.k]), now, pillar.k * 12);
    }
    this.loop.wake();
  }

  _retarget(now) {
    for (const pillar of this.pillars) {
      const on = this.chosen === pillar.k;
      HL.tset(pillar.tw, on ? this.amount : 0, now, 0);
      pillar.el.sil.classList.toggle("hi", on);
    }
    this.loop.wake();
  }
}

class GpuWireFigure extends HairlineFigureBase {
  static RANGE    = [3, 5, 8];
  static PLINTH   = [2, -21, 18, 21];
  static SOCKET   = [6.5, -18, 13.5, 18, 1.4];
  static CARD     = [8, -16, 12, 16, 16];
  static FANS     = [[-8, 8, 5.4], [8, 8, 5.4]];
  static HEIGHT   = 32;
  static INLET    = -40;
  static SPIN     = [0.6, 14];
  static RATE     = [2.6, 0.22];
  static SPEED    = [0.35, 1.5];
  static FLASH_MS = 160;
  static SAMPLE   = { util: 55, power: 0.55 };

  constructor({ stage, svg }, value) {
    super(svg, value, 5.6);
    this.util    = GpuWireFigure.SAMPLE.util / 100;
    this.energy  = GpuWireFigure.SAMPLE.power;
    this.spin    = HL.spring(this._spinFor(this.util), { k: 6, c: 5, eps: 0.01 });
    this.flow    = HL.spring(this.energy, { k: 10, c: 6, eps: 0.002 });
    this.angle   = 0;
    this.packets = [];
    this.next    = 0;
    this.flash   = 0;
    this.lit     = null;
    this._camera(this._extent(), 160);
    const [x0, y0, x1, y1] = GpuWireFigure.PLINTH;
    this._plinth(x0, y0, x1, y1, 5, 3);
    this._buildWire();
    this._buildCard();
    this.parts = [this.card];
    this._start(stage, svg);
    this._retarget(performance.now());
  }

  _spinFor(util) {
    const [idle, full] = GpuWireFigure.SPIN;
    return idle + (full - idle) * util;
  }

  _extent() {
    const [x0, y0, x1, y1]         = GpuWireFigure.PLINTH;
    const [cx0, cy0, cx1, cy1, ch] = GpuWireFigure.CARD;
    const lift                     = GpuWireFigure.RANGE[2];
    const mid                      = (cx0 + cx1) / 2;
    return [[x0, y0, -3], [x1, y1, -3], [x1, y0, -3], [x0, y1, -3], [cx0, cy0, ch + lift], [cx1, cy1, ch + lift], [mid, GpuWireFigure.INLET, GpuWireFigure.HEIGHT], [mid, 0, GpuWireFigure.HEIGHT]];
  }

  _buildWire() {
    const [cx0, , cx1, , ch] = GpuWireFigure.CARD;
    const mid                = (cx0 + cx1) / 2;
    const pts                = [[mid, GpuWireFigure.INLET, GpuWireFigure.HEIGHT], [mid, 0, GpuWireFigure.HEIGHT], [mid, 0, ch + 0.5]];
    const cum                = [0];
    for (let i = 1; i < pts.length; i++) cum.push(cum[i - 1] + Math.hypot(pts[i][0] - pts[i - 1][0], pts[i][1] - pts[i - 1][1], pts[i][2] - pts[i - 1][2]));
    this.wire = { pts, cum };
    HL.mk("path", { d: HL.open(pts.map(([x, y, z]) => this.P(x, y, z))), class: "nf lo" }, this.g);
    this.packetLayer = HL.mk("g", {}, this.g);
  }

  _alongWire(f) {
    const { pts, cum } = this.wire;
    const s            = HL.clamp(f, 0, 1) * cum[cum.length - 1];
    let i              = 1;
    while (i < cum.length - 1 && cum[i] < s) i++;
    const t = (s - cum[i - 1]) / (cum[i] - cum[i - 1]);
    return [0, 1, 2].map((k) => HL.lerp(pts[i - 1][k], pts[i][k], t));
  }

  _buildCard() {
    const [sx0, sy0, sx1, sy1, sh] = GpuWireFigure.SOCKET;
    const [x0, y0, x1, y1]         = GpuWireFigure.CARD;
    const group                    = HL.mk("g", {}, this.g);
    HL.put(HL.solid(group), HL.prism(this.P, this.front, ...HL.rings(sx0, sy0, sx1, sy1, 0.9, 0.5), 0, sh));
    const [ring, inner] = HL.rings(x0, y0, x1, y1, 1.1, 0.5);
    const el            = HL.solid(group);
    this.card = { k: 0, ring, inner, el, fans: HL.mk("path", { class: "nf lo" }, group), led: HL.flatDot(group, this.C, 0.9, "dot off"), lift: 0, tw: HL.tween(0), drawn: NaN, restX: this.P((x0 + x1) / 2, (y0 + y1) / 2, 0)[0] };
  }

  _tick(dt, now) {
    HL.stepS(this.spin, dt);
    HL.stepS(this.flow, dt);
    this.angle = (this.angle + this.spin.x * dt) % (Math.PI * 2);
    this._advance(this.parts, now);
    this._drawFans();
    this._flow(dt, now);
    return true;
  }

  _draw(card, lift) {
    const [x0, y0, x1, y1, h] = GpuWireFigure.CARD;
    card.lift                 = lift;
    HL.put(card.el, HL.prism(this.P, this.front, card.ring, card.inner, lift, lift + h));
    HL.place(card.led, this.P((x0 + x1) / 2, y1 - 2.4, lift + h));
  }

  _drawFans() {
    const card           = this.card;
    const [, y0, x1, y1] = GpuWireFigure.CARD;
    const mid            = (y0 + y1) / 2;
    const at             = (cy, cz, a, radius) => this.P(x1, cy + radius * Math.cos(a), cz + radius * Math.sin(a));
    let d                = "";
    for (const [fy, fz, R] of GpuWireFigure.FANS) {
      const cy = mid + fy;
      const cz = card.lift + fz;
      d       += HairlineGeometry.faceCircle(this.P, x1, cy, cz, R);
      for (let j = 0; j < 3; j++) {
        const a = this.angle + (j * Math.PI * 2) / 3;
        d      += HL.seg(at(cy, cz, a, 1.1), at(cy, cz, a + 0.5, R * 0.82));
      }
    }
    card.fans.setAttribute("d", d);
  }

  _flow(dt, now) {
    const e     = HL.clamp(this.flow.x, 0, 1);
    const speed = HL.lerp(GpuWireFigure.SPEED[0], GpuWireFigure.SPEED[1], e);
    let arrived = false;
    for (const packet of this.packets) {
      packet.s += speed * dt;
      if (packet.s >= 1) {
        arrived = true;
        packet.el.remove();
      }
    }
    if (arrived) this.flash = now + GpuWireFigure.FLASH_MS;
    this.packets = this.packets.filter((packet) => packet.s < 1);
    if (now >= this.next) {
      this.next = now + HL.lerp(GpuWireFigure.RATE[0], GpuWireFigure.RATE[1], e) * 1000;
      this.packets.push({ s: 0, el: HL.flatDot(this.packetLayer, this.C, 1.1, "dot") });
    }
    for (const packet of this.packets) HL.place(packet.el, this.P(...this._alongWire(packet.s)));
    const lit = now < this.flash ? "dot" : this.util >= 0.5 ? "dot m" : "dot off";
    if (lit !== this.lit) {
      this.lit = lit;
      this.card.led.setAttribute("class", lit);
    }
  }

  _move() {
    this._choose(0);
  }

  setState(state) {
    const util = HL.clamp(Number(state.util) || 0, 0, 100) / 100;
    if (!Number.isFinite(util)) throw new Error("gpuwire figure: state.util must be a percentage");
    this.util   = util;
    this.energy = Number.isFinite(state.power) ? HL.clamp(state.power, 0, 1) : util;
    this.spin.t = this._spinFor(util);
    this.flow.t = this.energy;
    this.loop.wake();
  }

  _retarget(now) {
    const on = this.chosen === 0;
    HL.tset(this.card.tw, on ? this.amount : 0, now, 0);
    this.card.el.sil.classList.toggle("hi", on);
    this.loop.wake();
  }
}

class GuillotineFigure extends HairlineFigureBase {
  static RANGE    = [2, 4, 7];
  static PLINTH   = [-16, -15, 16, 15];
  static SERVER   = [-4.5, -3.8, 4.5, 3.8, 15];
  static POSTS    = [-9.5, 9.5];
  static POST     = [0.9, 30];
  static BAR      = 2;
  static BLADE    = [0.6, 7, 8, 3.2];
  static TOP      = 20;
  static APART    = 2.4;
  static RISE_MS  = 1800;
  static HOLD_MS  = 900;
  static DROP_MS  = 260;
  static SPLIT_MS = 420;
  static OPEN_MS  = 1100;
  static JOIN_MS  = 500;

  constructor({ stage, svg }, value) {
    super(svg, value, 6);
    this.phase = "rise";
    this.t0    = performance.now();
    this.blade = 0;
    this.down  = false;
    this.gap   = HL.tween(0, GuillotineFigure.SPLIT_MS);
    this.drawn = null;
    this._camera(this._extent(), 162);
    const [x0, y0, x1, y1] = GuillotineFigure.PLINTH;
    this._plinth(x0, y0, x1, y1, 5, 3);
    this._buildFrame();
    this.parts = [this.server];
    this._start(stage, svg);
    this._retarget(performance.now());
  }

  _extent() {
    const [x0, y0, x1, y1]  = GuillotineFigure.PLINTH;
    const [sx0, sy0, sx1, sy1, sh] = GuillotineFigure.SERVER;
    const [pw, ph]          = GuillotineFigure.POST;
    const [pa, pb]          = GuillotineFigure.POSTS;
    const crown             = ph + GuillotineFigure.BAR;
    const lift              = GuillotineFigure.RANGE[2];
    return [[x0, y0, -3], [x1, y1, -3], [x1, y0, -3], [x0, y1, -3], [-pw, pa - pw, crown], [pw, pb + pw, crown], [sx0, sy0, sh + lift], [sx1, sy1, sh + lift]];
  }

  _buildFrame() {
    const [pw, ph] = GuillotineFigure.POST;
    const [pa, pb] = GuillotineFigure.POSTS;
    HL.put(HL.solid(this.g), HL.prism(this.P, this.front, ...HL.rings(-pw, pa - pw, pw, pa + pw, 0.4, 0.2), 0, ph));
    const group  = HL.mk("g", {}, this.g);
    const left   = HL.solid(group);
    const bladeG = HL.mk("g", {}, group);
    const right  = HL.solid(group);
    this.server  = { k: 0, left, right, vents: HL.mk("path", { class: "nf lo" }, group), led: HL.flatDot(group, this.C, 0.9, "dot m"), tw: HL.tween(0), drawn: NaN, restX: this.P(0, 0, 0)[0] };
    this.server.el = right;
    this.bladeEl   = HL.solid(bladeG);
    this.bladeEdge = HL.mk("path", { class: "nf lo" }, bladeG);
    HL.put(HL.solid(this.g), HL.prism(this.P, this.front, ...HL.rings(-pw, pb - pw, pw, pb + pw, 0.4, 0.2), 0, ph));
    HL.put(HL.solid(this.g), HL.prism(this.P, this.front, ...HL.rings(-pw, pa - pw, pw, pb + pw, 0.4, 0.2), ph, ph + GuillotineFigure.BAR));
  }

  _tick(dt, now) {
    this._phase(now);
    const lift = HL.tval(this.server.tw, now);
    const gap  = HL.tval(this.gap, now);
    const key  = `${lift.toFixed(2)}:${gap.toFixed(3)}:${this.blade.toFixed(2)}`;
    if (key !== this.drawn) {
      this.drawn = key;
      this._drawServer(lift, gap);
      this._drawBlade(this.blade);
    }
    return true;
  }

  _phase(now) {
    const t     = now - this.t0;
    const quick = HL.reducedMotion();
    switch (this.phase) {
      case "rise":
        this.blade = GuillotineFigure.TOP * (quick ? 1 : HL.EASE_LIFT(t / GuillotineFigure.RISE_MS));
        if (t >= GuillotineFigure.RISE_MS || quick) { this.phase = "hold"; this.t0 = now; this.blade = GuillotineFigure.TOP; }
        break;
      case "hold":
        if (t >= GuillotineFigure.HOLD_MS) { this.phase = "drop"; this.t0 = now; }
        break;
      case "drop": {
        const s    = quick ? 1 : Math.min(1, t / GuillotineFigure.DROP_MS);
        this.blade = GuillotineFigure.TOP * (1 - s * s);
        if (s >= 1) { this.phase = "open"; this.t0 = now; HL.tset(this.gap, 1, now, 0); }
        break;
      }
      case "open":
        if (t >= GuillotineFigure.OPEN_MS && !this.down) { this.phase = "join"; this.t0 = now; HL.tset(this.gap, 0, now, 0); }
        break;
      case "join":
        if (t >= GuillotineFigure.JOIN_MS) { this.phase = "rise"; this.t0 = now; }
        break;
      default:
        break;
    }
  }

  _drawServer(lift, gap) {
    const server              = this.server;
    const [x0, y0, x1, y1, h] = GuillotineFigure.SERVER;
    const a                   = GuillotineFigure.APART * gap;
    HL.put(server.left, HL.prism(this.P, this.front, ...HL.rings(x0 - a, y0, -a, y1, 1, 0.5), lift, lift + h));
    HL.put(server.right, HL.prism(this.P, this.front, ...HL.rings(a, y0, x1 + a, y1, 1, 0.5), lift, lift + h));
    server.vents.setAttribute("d", [3.4, 6.4, 9.4].map((z) => HL.seg(this.P(x0 - a + 1.4, y1, lift + z), this.P(-a - 0.4, y1, lift + z)) + HL.seg(this.P(a + 0.4, y1, lift + z), this.P(x1 + a - 1.4, y1, lift + z))).join(""));
    HL.place(server.led, this.P(x1 + a - 2, y1 - 2, lift + h));
  }

  _drawBlade(z) {
    const [bt, bw, bh, slant] = GuillotineFigure.BLADE;
    const face = (x) => [[x, -bw, z + slant], [x, bw, z], [x, bw, z + bh], [x, -bw, z + bh]].map(([px, py, pz]) => this.P(px, py, pz));
    const far  = face(-bt);
    const near = face(bt);
    HL.put(this.bladeEl, { sil: HL.poly(HL.hull(far.concat(near))), crease: HL.poly(near) });
    this.bladeEdge.setAttribute("d", HL.seg(near[0], near[1]));
  }

  _move() {
    this._choose(0);
  }

  setState(state) {
    this.down = !!state.down;
    this.loop.wake();
  }

  _retarget(now) {
    const on = this.chosen === 0;
    HL.tset(this.server.tw, on ? this.amount : 0, now, 0);
    this.server.left.sil.classList.toggle("hi", on);
    this.server.right.sil.classList.toggle("hi", on);
    this.loop.wake();
  }
}

class ChipsFigure extends HairlineFigureBase {
  static RANGE   = [1.5, 3, 5];
  static TABLE   = 36;
  static CHIP    = [3.4, 1.05];
  static POT     = 12;
  static STACKS  = [[-4.6, 0], [4.6, 0]];
  static ANGLES  = [Math.PI * 1.1667, Math.PI * 1.8333, Math.PI * 0.5];
  static ROD     = [20, 0.7];
  static HEAD    = [7, 1, 2.6];
  static KNOB    = [1.3, 1.8];
  static SCOOP   = 0.35;
  static REACH   = [9, 25];
  static PERIOD  = 12.8;
  static TIMES   = [1.2, 2.4, 3.6];
  static FLIGHT  = 0.9;
  static STAGGER = 0.28;
  static ARC     = 10;
  static FULL    = 0.3;
  static MAX     = 4;
  static LOOSE   = [[25, 10, 2], [20.5, -11.5, 1], [27, -7.5, 1]];
  static BURST   = [2.2, 0.3, 0.2, 60];

  constructor({ stage, svg }, value) {
    super(svg, value, 4.1);
    this.alarm  = false;
    this.counts = [2, 1, 1];
    this.clock  = 0;
    this.potKey = null;
    this.bursts = [null, null];
    this._camera(this._extent(), 170);
    this._buildTable();
    this._buildSticks();
    this.parts = this.sticks;
    this._start(stage, svg);
    this._retarget(performance.now());
  }

  _extent() {
    const reach = ChipsFigure.REACH[1] + ChipsFigure.ROD[0];
    const r     = ChipsFigure.TABLE;
    const tips  = ChipsFigure.ANGLES.map((a) => [reach * Math.cos(a), reach * Math.sin(a), 2]);
    return [[-r, 0, -3], [r, 0, -3], [0, -r, -3], [0, r, -3], [0, 0, ChipsFigure.POT * ChipsFigure.CHIP[1] + ChipsFigure.ARC]].concat(tips);
  }

  _buildTable() {
    const r = ChipsFigure.TABLE;
    HL.put(HL.solid(this.g), HL.prism(this.P, this.front, HL.circ(r, 96), HL.circ(r - 2.4, 96), -3, 0));
    HL.mk("path", { d: HL.poly(HL.ringAt(this.P, HL.circ(r - 7, 96), 0.1)), class: "dash nf" }, this.g);
  }

  _buildSticks() {
    const layers = [HL.mk("g", {}, this.g), null, null];
    this.potLayer = HL.mk("g", {}, this.g);
    layers[1]     = HL.mk("g", {}, this.g);
    layers[2]     = HL.mk("g", {}, this.g);
    this.flight   = HL.mk("g", {}, this.g);
    this.pot      = Array.from({ length: ChipsFigure.POT }, () => HL.solid(this.potLayer));
    this.sticks   = ChipsFigure.ANGLES.map((a, k) => {
      const dir   = [Math.cos(a), Math.sin(a)];
      const side  = [-Math.sin(a), Math.cos(a)];
      const group = layers[k];
      this._loose(group, dir, side);
      const under = dir[0] + dir[1] > 0;
      const tray  = under ? HL.mk("g", {}, group) : null;
      const rod   = HL.solid(group);
      const head  = HL.solid(group);
      const knob  = HL.solid(group);
      const dot   = HL.flatDot(group, this.C, 0.7, k === 2 ? "dot" : "dot off");
      const bed   = under ? tray : HL.mk("g", {}, group);
      const chips = Array.from({ length: ChipsFigure.MAX }, () => HL.solid(bed));
      const home  = ChipsFigure.REACH[1];
      return { k, dir, side, group, bed, rod, head, knob, dot, chips, el: rod, offset: (k * ChipsFigure.PERIOD) / 3, pick: null, tw: HL.tween(0), drawn: NaN, restX: this.P(dir[0] * home, dir[1] * home, 0)[0], restY: this.P(dir[0] * home, dir[1] * home, 0)[1] };
    });
  }

  _loose(group, dir, side) {
    for (const [along, across, count] of ChipsFigure.LOOSE) {
      const x = dir[0] * along + side[0] * across;
      const y = dir[1] * along + side[1] * across;
      for (let level = 0; level < count; level++) this._chip(HL.solid(group), [x, y, level * ChipsFigure.CHIP[1]], 0, dir, side, false);
    }
  }

  _box(cx, cy, dir, side, along, across, radius) {
    const corners = [[1, 1], [-1, 1], [-1, -1], [1, -1]].map(([a, b]) => [cx + dir[0] * along * a + side[0] * across * b, cy + dir[1] * along * a + side[1] * across * b]);
    return HairlineGeometry.samples(HL.fillet(corners, [radius, radius, radius, radius], 3));
  }

  _chip(el, c, phi, dir, side, hi) {
    const [R, T] = ChipsFigure.CHIP;
    const cp     = Math.cos(phi);
    const sp     = Math.sin(phi);
    const w      = [cp * dir[0], cp * dir[1], sp];
    const n      = [-sp * dir[0], -sp * dir[1], cp];
    const ring   = (radius, drop) => Array.from({ length: 24 }, (_, i) => {
      const t = (i / 24) * Math.PI * 2;
      const u = Math.cos(t) * radius;
      const v = Math.sin(t) * radius;
      return this.P(c[0] + u * side[0] + v * w[0] - drop * n[0], c[1] + u * side[1] + v * w[1] - drop * n[1], c[2] + v * w[2] - drop * n[2]);
    });
    const top    = ring(R, 0);
    const bottom = ring(R, T);
    HL.put(el, { sil: HL.poly(HL.hull(top.concat(bottom))), crease: HL.poly(top) + HL.poly(ring(R * 0.58, 0)) });
    el.sil.classList.toggle("hi", !!hi);
  }

  _hideChip(el) {
    HL.put(el, { sil: "", crease: "" });
  }

  _tick(dt, now) {
    this.clock += dt;
    this._advance(this.sticks, now);
    const out = this.sticks.map((stick) => this._stick(stick));
    this._pot(ChipsFigure.POT - out.reduce((s, n) => s + n, 0));
    return true;
  }

  _draw(stick, lift) {
    stick.lift = lift;
  }

  _stick(stick) {
    const [t0, t1, t2]   = ChipsFigure.TIMES;
    const [near, far]    = ChipsFigure.REACH;
    const t              = (this.clock + stick.offset) % ChipsFigure.PERIOD;
    const n              = this.counts[stick.k];
    const lift           = stick.lift || 0;
    const hi             = this.alarm && stick.k === 2;
    const ease           = (u) => { const v = HL.clamp(u, 0, 1); return v * v * (3 - 2 * v); };
    let head             = far;
    if (t < t0) head = HL.lerp(far, near, ease(t / t0));
    else if (t < t1) head = HL.lerp(near, far, ease((t - t0) / (t1 - t0)));
    this._rake(stick, head, lift, hi);
    if (t < t0) stick.pick = null;
    else if (!stick.pick) stick.pick = Array.from({ length: n }, () => this._landing(true));

    let out = 0;
    for (let i = 0; i < ChipsFigure.MAX; i++) {
      const el = stick.chips[i];
      if (i >= n || t < t0) { this._hideChip(el); continue; }
      const start = t2 + i * ChipsFigure.STAGGER;
      const z0    = i * ChipsFigure.CHIP[1];
      if (t < t2 || t < start) {
        const r     = t < t1 ? head - 5 : far - 5;
        const at    = [stick.dir[0] * r, stick.dir[1] * r, z0];
        const grab  = ease((t - t0) / ChipsFigure.SCOOP);
        const from  = stick.pick && stick.pick[i] ? stick.pick[i] : at;
        const c     = grab >= 1 ? at : [HL.lerp(from[0], at[0], grab), HL.lerp(from[1], at[1], grab), HL.lerp(from[2], at[2], grab) + 2.5 * grab * (1 - grab)];
        if (el.g.parentNode !== stick.bed) stick.bed.appendChild(el.g);
        this._chip(el, c, 0, stick.dir, stick.side, hi);
        out++;
        continue;
      }
      const s = (t - start) / ChipsFigure.FLIGHT;
      if (s >= 1) {
        if (el.flying) { el.flying = false; this._burst(); }
        this._hideChip(el);
        continue;
      }
      el.flying = true;
      const from   = [stick.dir[0] * (far - 5), stick.dir[1] * (far - 5), z0];
      const target = this._landing();
      const c      = [HL.lerp(from[0], target[0], s), HL.lerp(from[1], target[1], s), HL.lerp(from[2], target[2], s) + ChipsFigure.ARC * 4 * s * (1 - s)];
      if (el.g.parentNode !== this.flight) this.flight.appendChild(el.g);
      this._chip(el, c, s * Math.PI * 4, [-stick.dir[0], -stick.dir[1]], stick.side, hi);
      out++;
    }
    return out;
  }

  _rake(stick, head, lift, hi) {
    const [length, half]     = ChipsFigure.ROD;
    const [span, thick, tall] = ChipsFigure.HEAD;
    const { dir, side }      = stick;
    const mid                = head + length / 2;
    const z                  = 0.9 + lift;
    HL.put(stick.rod, HL.prism(this.P, this.front, this._box(dir[0] * mid, dir[1] * mid, dir, side, length / 2, half, 0.5), null, z, z + 1));
    HL.put(stick.head, HL.prism(this.P, this.front, this._box(dir[0] * head, dir[1] * head, dir, side, thick, span, 0.5), this._box(dir[0] * head, dir[1] * head, dir, side, thick - 0.3, span - 0.4, 0.3), z, z + tall));
    const [kr, kh]           = ChipsFigure.KNOB;
    const kx                 = dir[0] * (head + length - kr);
    const ky                 = dir[1] * (head + length - kr);
    HL.put(stick.knob, HL.prism(this._shifted(kx, ky, 0), this.front, HL.circ(kr, 20), HL.circ(kr - 0.5, 20), z - 0.3, z - 0.3 + kh));
    HL.place(stick.dot, this.P(kx, ky, z - 0.3 + kh));
    const lit = hi || this.chosen === stick.k;
    for (const part of [stick.rod, stick.head, stick.knob]) part.sil.classList.toggle("hi", lit);
  }

  _landing(take) {
    const counts = this.potCounts || [ChipsFigure.POT / 2, ChipsFigure.POT / 2];
    const which  = take ? (counts[0] >= counts[1] ? 0 : 1) : (counts[0] <= counts[1] ? 0 : 1);
    const [x, y] = ChipsFigure.STACKS[which];
    if (take) counts[which] = Math.max(0, counts[which] - 1);
    return [x, y, counts[which] * (ChipsFigure.CHIP[1] + this._gap(which))];
  }

  _burst() {
    const counts = this.potCounts || [0, 0];
    const which  = counts[0] <= counts[1] ? 0 : 1;
    if (!HL.reducedMotion()) this.bursts[which] = this.clock;
  }

  _gap(which) {
    const t0 = this.bursts[which];
    if (t0 === null) return 0;
    const [gap, rise, hold, g] = ChipsFigure.BURST;
    const t = this.clock - t0;
    if (t < rise) { const u = t / rise; return gap * (1 - (1 - u) * (1 - u)); }
    if (t < rise + hold) return gap;
    const fall = t - rise - hold;
    const z    = gap - 0.5 * g * fall * fall;
    if (z <= 0) { this.bursts[which] = null; return 0; }
    return z;
  }

  _pot(count) {
    const total = HL.clamp(Math.round(count), 0, ChipsFigure.POT);
    const gaps  = [this._gap(0), this._gap(1)];
    const key   = `${total}:${gaps[0].toFixed(2)}:${gaps[1].toFixed(2)}`;
    if (key === this.potKey) return;
    this.potKey    = key;
    const a        = Math.ceil(total / 2);
    const b        = total - a;
    this.potCounts = [a, b];
    const dir      = [1, 0];
    const side     = [0, 1];
    this.pot.forEach((el, i) => {
      const inA = i < a;
      const inB = !inA && i < a + b;
      if (!inA && !inB) { this._hideChip(el); return; }
      const [x, y] = ChipsFigure.STACKS[inA ? 0 : 1];
      const level  = inA ? i : i - a;
      this._chip(el, [x, y, level * (ChipsFigure.CHIP[1] + gaps[inA ? 0 : 1])], 0, dir, side, false);
    });
  }

  _move(p) {
    let best = 0;
    let near = Infinity;
    for (const stick of this.sticks) {
      const d = Math.hypot(stick.restX - p[0], stick.restY - p[1]);
      if (d < near) { near = d; best = stick.k; }
    }
    this._choose(best);
  }

  setState(state) {
    const mine   = Math.max(0, Number(state.mine) || 0);
    const others = Math.max(0, Number(state.others) || 0);
    if (!Number.isFinite(mine + others)) throw new Error("chips figure: state.mine and state.others must be numbers");
    const pull   = (share) => 1 + Math.round(HL.clamp(share / ChipsFigure.FULL, 0, 1) * (ChipsFigure.MAX - 1));
    const theirs = pull(others);
    const first  = Math.max(1, Math.round(theirs / 2));
    this.counts  = [first, Math.max(1, theirs - first), pull(mine)];
    this.alarm   = !!state.alarm;
    this.loop.wake();
  }

  _retarget(now) {
    for (const stick of this.sticks) {
      HL.tset(stick.tw, this.chosen === stick.k ? this.amount : 0, now, 0);
      stick.drawn = NaN;
    }
    this.loop.wake();
  }
}

class DeskCalendarFigure extends HairlineFigureBase {
  static RANGE   = [8, 14, 24];
  static SLOTS   = 6;
  static WIDTH   = 32;
  static LENGTH  = 24;
  static SLOPE   = (22 * Math.PI) / 180;
  static BOARD   = 1.2;
  static MARGIN  = 1.4;
  static PAGE    = 0.12;
  static BARS    = [5.4, 3.1, 1.5];
  static INSET   = 3;
  static RINGS   = [-10.5, -3.5, 3.5, 10.5];
  static STEP_MS = 2600;
  static HOLD_MS = 6000;

  static sample() {
    return Array.from({ length: 30 }, (_, day) => ({
      slots: Array.from({ length: DeskCalendarFigure.SLOTS }, (_, slot) => {
        const weekday = day % 7 < 5;
        const mine    = weekday && slot >= 2 && slot <= 4 ? 0.55 + 0.3 * Math.sin(day + slot) : 0.25 + 0.2 * Math.sin(day * 1.7 + slot);
        const others  = 0.15 + 0.15 * Math.cos(day * 0.9 + slot * 1.3);
        return { mine: HL.clamp(mine, 0, 0.85), others: HL.clamp(others, 0, 1 - HL.clamp(mine, 0, 0.85)) };
      }),
    }));
  }

  constructor({ stage, svg }, value) {
    super(svg, value, 5.0);
    this.days  = DeskCalendarFigure.sample();
    this.ridge = (DeskCalendarFigure.LENGTH + DeskCalendarFigure.MARGIN) * Math.cos(DeskCalendarFigure.SLOPE);
    this.pos   = HL.spring(0, { k: this.amount, c: 2 * Math.sqrt(this.amount), eps: 0.002 });
    this.next  = 0;
    this.drawn = NaN;
    this._camera(this._extent(), 160);
    this._build();
    this._start(stage, svg);
    this._retarget();
  }

  _extent() {
    const half  = DeskCalendarFigure.WIDTH / 2 + 3;
    const depth = this.ridge * Math.tan(DeskCalendarFigure.SLOPE) + 4;
    const box   = [[-half, -depth], [half, -depth], [-half, depth], [half, depth]].map(([x, y]) => [x, y, -2.5]);
    return box.concat([[-half, 0, this.ridge + DeskCalendarFigure.LENGTH], [half, 0, this.ridge + DeskCalendarFigure.LENGTH]]);
  }

  _build() {
    const half  = DeskCalendarFigure.WIDTH / 2 + 3;
    const depth = this.ridge * Math.tan(DeskCalendarFigure.SLOPE) + 4;
    this._plinth(-half, -depth, half, depth, 3, 2.5);

    this.backBoard  = HL.mk("path", { class: "sil" }, this.g);
    this.backStack  = HL.mk("path", { class: "sil" }, this.g);
    this.flipBack   = HL.mk("g", {}, this.g);
    this.frontBoard = HL.mk("path", { class: "sil" }, this.g);
    this.frontStack = HL.mk("path", { class: "sil" }, this.g);
    this.face       = this._buildFace(this.g);
    this.flipFront  = HL.mk("g", {}, this.g);
    this.flip       = HL.mk("g", {}, this.flipFront);
    this.flipPage   = HL.mk("path", { class: "sil" }, this.flip);
    this.flipFace   = this._buildFace(this.flip);
    this.rings      = HL.mk("path", { class: "nf" }, this.g);
  }

  _buildFace(parent) {
    const group  = HL.mk("g", {}, parent);
    const header = HL.mk("path", { class: "nf lo" }, group);
    const bars   = Array.from({ length: DeskCalendarFigure.SLOTS }, () => ({
      track  : HL.mk("path", { class: "nf lo" }, group),
      others : HL.mk("path", { class: "nf" }, group),
      mine   : HL.mk("path", { class: "nf hi" }, group),
    }));
    return { group, header, bars };
  }

  _tick(dt, now) {
    this._ambient(now);
    HL.stepS(this.pos, dt);
    if (this.pos.x !== this.drawn) {
      this.drawn = this.pos.x;
      this._draw(this.pos.x);
    }
    return true;
  }

  _ambient(now) {
    if (this.chosen !== null || now < this.next) return;
    const last = this.days.length - 1;
    if (this.pos.t >= last) {
      this.pos.t = 0;
      this.next  = now + DeskCalendarFigure.HOLD_MS;
      return;
    }
    this.pos.t = Math.round(this.pos.t) + 1;
    this.next  = now + (this.pos.t >= last ? DeskCalendarFigure.HOLD_MS : DeskCalendarFigure.STEP_MS);
  }

  _draw(pos) {
    const count    = this.days.length;
    const day      = HL.clamp(Math.floor(pos), 0, count - 1);
    const turn     = pos - day;
    const flipping = turn > 0.002 && day < count - 1;
    const top      = flipping ? day + 1 : day;
    const front    = (count - top) * DeskCalendarFigure.PAGE;
    const back     = day * DeskCalendarFigure.PAGE;
    const slope    = DeskCalendarFigure.SLOPE;
    const half     = DeskCalendarFigure.WIDTH / 2;
    const edge     = half + DeskCalendarFigure.MARGIN;
    const length   = DeskCalendarFigure.LENGTH + DeskCalendarFigure.MARGIN;
    const fore     = this._pageAt(slope);
    const rear     = this._pageAt(2 * Math.PI - slope);

    this.backBoard.setAttribute("d", this._box(rear, -edge, edge, 0, length, 0, DeskCalendarFigure.BOARD));
    this.backStack.setAttribute("d", back > 0 ? this._box(rear, -half, half, 0.6, DeskCalendarFigure.LENGTH, -back, 0) : "");
    this.frontBoard.setAttribute("d", this._box(fore, -edge, edge, 0, length, -DeskCalendarFigure.BOARD, 0));
    this.frontStack.setAttribute("d", this._box(fore, -half, half, 0.6, DeskCalendarFigure.LENGTH, 0, front));
    this._drawFace(this.face, fore, front, this.days[top]);

    const theta  = slope + turn * (2 * Math.PI - 2 * slope);
    const page   = this._pageAt(theta);
    const home   = theta < Math.PI ? this.flipFront : this.flipBack;
    const offset = HL.lerp(front, -back - DeskCalendarFigure.PAGE, turn);
    this.flipPage.setAttribute("d", flipping ? this._box(page, -half, half, 0.6, DeskCalendarFigure.LENGTH, offset, offset + DeskCalendarFigure.PAGE) : "");
    if (flipping && Math.cos(theta) + 0.816 * Math.sin(theta) > 0) this._drawFace(this.flipFace, page, offset + DeskCalendarFigure.PAGE, this.days[day]);
    else this._clearFace(this.flipFace);
    if (this.flip.parentNode !== home) home.appendChild(this.flip);

    this.rings.setAttribute("d", DeskCalendarFigure.RINGS.map((u) => HL.poly(Array.from({ length: 20 }, (_, k) => this.P(u, 1.3 * Math.cos((2 * Math.PI * k) / 20), this.ridge + 0.4 + 1.3 * Math.sin((2 * Math.PI * k) / 20))))).join(""));
  }

  _pageAt(theta) {
    const down   = [Math.sin(theta), -Math.cos(theta)];
    const normal = [Math.cos(theta), Math.sin(theta)];
    return (u, v, n) => this.P(u, v * down[0] + n * normal[0], this.ridge + v * down[1] + n * normal[1]);
  }

  _box(at, u0, u1, v0, v1, n0, n1) {
    const corners = [];
    for (const u of [u0, u1]) for (const v of [v0, v1]) for (const n of [n0, n1]) corners.push(at(u, v, n));
    return HL.poly(HL.hull(corners));
  }

  _drawFace(face, at, n, day) {
    const half             = DeskCalendarFigure.WIDTH / 2;
    const [first, pitch, h] = DeskCalendarFigure.BARS;
    const u0               = -half + DeskCalendarFigure.INSET;
    const span             = 2 * (half - DeskCalendarFigure.INSET);
    const rect             = (a, b, v) => (b - a < 0.3 ? "" : HL.poly([at(a, v, n), at(b, v, n), at(b, v + h, n), at(a, v + h, n)]));
    face.header.setAttribute("d", HL.seg(at(-half + 1.4, 3, n), at(half - 1.4, 3, n)));
    day.slots.forEach((slot, s) => {
      const v     = first + s * pitch;
      const mine  = u0 + span * HL.clamp(slot.mine, 0, 1);
      const both  = u0 + span * HL.clamp(slot.mine + slot.others, 0, 1);
      face.bars[s].track.setAttribute("d", rect(u0, u0 + span, v));
      face.bars[s].mine.setAttribute("d", rect(u0, mine, v));
      face.bars[s].others.setAttribute("d", rect(mine, both, v));
    });
  }

  _clearFace(face) {
    face.header.setAttribute("d", "");
    for (const bar of face.bars) {
      bar.track.setAttribute("d", "");
      bar.mine.setAttribute("d", "");
      bar.others.setAttribute("d", "");
    }
  }

  _move(p) {
    const half = DeskCalendarFigure.WIDTH / 2;
    const x0   = this.P(-half, 0, this.ridge)[0];
    const x1   = this.P(half, 0, this.ridge)[0];
    this._choose(Math.round(HL.clamp((p[0] - x0) / (x1 - x0), 0, 1) * (this.days.length - 1)));
  }

  setState(state) {
    if (!Array.isArray(state.days) || !state.days.length) throw new Error("calendar figure: state.days must list at least one day");
    this.days  = state.days;
    this.drawn = NaN;
    if (this.pos.t > this.days.length - 1) this.pos.t = this.days.length - 1;
    this._retarget();
  }

  _retarget() {
    this.pos.k = this.amount;
    this.pos.c = 2 * Math.sqrt(this.amount);
    if (this.chosen !== null) this.pos.t = this.chosen;
    this.loop.wake();
  }
}

class GpuBaysFigure extends HairlineFigureBase {
  static RANGE     = [3, 6, 10];
  static NODES     = 4;
  static GPUS      = 4;
  static PITCH     = 12;
  static SLOT      = [4.6, 2.5];
  static LENGTH    = 7.6;
  static THICK     = 2.8;
  static HEIGHT    = 5.8;
  static FAN       = 1.9;
  static LID       = 0.9;
  static LEAVE     = 13;
  static SPIN      = 1.4;
  static CHURN_MS  = 2800;
  static ARRIVE_MS = 450;
  static TRAVEL_MS = 1100;
  static REST_LIFT = 0.5;
  static OFFLINE   = [1, 3, 0, 2];
  static DEFAULT   = { free: [[0, 1], [2, 3], [3, 0], [2, 1]], offline: 2 };

  constructor({ stage, svg }, value) {
    super(svg, value, 3.9);
    this.next = 0;
    this._camera(this._extent(), 148);
    this._plinth(-GpuBaysFigure.PITCH / 2 - 1.5, -GpuBaysFigure.PITCH / 2 - 1.5, this._span(GpuBaysFigure.NODES) + 1.5, this._span(GpuBaysFigure.GPUS) + 1.5, 4, 3);
    this._buildBays();
    this._seed();
    this._start(stage, svg);
    this._retarget(performance.now());
  }

  _span(count) {
    return (count - 0.5) * GpuBaysFigure.PITCH;
  }

  _extent() {
    const x0  = -GpuBaysFigure.PITCH / 2 - 1.5;
    const x1  = this._span(GpuBaysFigure.NODES) + 1.5;
    const y1  = this._span(GpuBaysFigure.GPUS) + 1.5;
    const top = GpuBaysFigure.HEIGHT + GpuBaysFigure.RANGE[2];
    return [[x0, x0, -3], [x1, y1, -3], [x1, x0, -3], [x0, y1, -3], [x0, x0, top], [x1, y1, top]];
  }

  _buildBays() {
    const cells = [];
    for (let i = 0; i < GpuBaysFigure.NODES; i++) for (let j = 0; j < GpuBaysFigure.GPUS; j++) cells.push([i, j]);
    cells.sort((a, b) => a[0] + a[1] - (b[0] + b[1]) || a[0] - b[0]);

    const [su, sv] = GpuBaysFigure.SLOT;
    const l        = GpuBaysFigure.LENGTH / 2;
    const t        = GpuBaysFigure.THICK / 2;
    this.bays      = cells.map(([i, j], k) => {
      const cx    = i * GpuBaysFigure.PITCH;
      const cy    = j * GpuBaysFigure.PITCH;
      const group = HL.mk("g", {}, this.g);
      return {
        k, i, j, cx, cy,
        kind     : "card",
        socket   : HL.mk("path", { class: "nf lo" }, group),
        dot      : HL.flatDot(group, this.C, 0.8, "dot off"),
        lid      : HL.solid(group),
        mark     : HL.mk("path", { class: "nf lo dash" }, group),
        card     : HL.solid(group),
        fan      : HL.mk("path", { class: "nf lo" }, group),
        ring     : HL.rrect(cx - su, cy - sv, cx + su, cy + sv, 1.2, 4),
        lidRing  : HL.rings(cx - su + 0.6, cy - sv + 0.6, cx + su - 0.6, cy + sv - 0.6, 0.9, 0.5),
        cardRing : HL.rings(cx - l, cy - t, cx + l, cy + t, 0.8, 0.5),
        lift     : HL.tween(0),
        out      : HL.tween(0, GpuBaysFigure.TRAVEL_MS),
        shut     : HL.tween(0),
        phase    : k * 0.9,
        drawn    : "",
        anchor   : this.P(cx, cy, GpuBaysFigure.HEIGHT / 2),
      };
    });
    this.byCell = new Map(this.bays.map((bay) => [`${bay.i},${bay.j}`, bay]));
  }

  _seed() {
    const offline = this._offlineOrder().slice(0, GpuBaysFigure.DEFAULT.offline);
    for (const bay of offline) this._setKind(bay, "offline", true);
    for (const [i, j] of GpuBaysFigure.DEFAULT.free) this._setKind(this.byCell.get(`${i},${j}`), "free", true);
    this.rest = this._restBay();
  }

  _offlineOrder() {
    const order = [];
    for (const i of GpuBaysFigure.OFFLINE) for (let j = GpuBaysFigure.GPUS - 1; j >= 0; j--) order.push(this.byCell.get(`${i},${j}`));
    return order;
  }

  _setKind(bay, kind, instant) {
    const now = instant ? -1e9 : performance.now();
    bay.kind  = kind;
    HL.tset(bay.out, kind === "card" ? 0 : 1, now, 0);
    HL.tset(bay.shut, kind === "offline" ? 1 : 0, now, 0);
  }

  _restBay() {
    const middle = [(GpuBaysFigure.NODES - 1) / 2, (GpuBaysFigure.GPUS - 1) / 2];
    const free   = this.bays.filter((bay) => bay.kind === "free");
    if (!free.length) return null;
    free.sort((a, b) => Math.hypot(a.i - middle[0], a.j - middle[1]) - Math.hypot(b.i - middle[0], b.j - middle[1]));
    return free[0].k;
  }

  _tick(dt, now) {
    if (now >= this.next) {
      if (this.next) this._churn(now);
      this.next = now + GpuBaysFigure.CHURN_MS;
    }
    for (const bay of this.bays) {
      bay.phase  = (bay.phase + GpuBaysFigure.SPIN * dt) % (Math.PI * 2);
      const lift = HL.tval(bay.lift, now);
      const out  = HL.tval(bay.out, now);
      const shut = HL.tval(bay.shut, now);
      const key  = `${lift}|${out}|${shut}`;
      if (key !== bay.drawn) {
        bay.drawn = key;
        this._draw(bay, lift, out, shut);
      }
      this._drawFan(bay, lift, out);
    }
    return true;
  }

  _churn(now) {
    const ready = (bay) => bay.k !== this.chosen && HL.tdone(bay.out, now);
    const busy  = this.bays.filter((bay) => bay.kind === "card" && ready(bay));
    const open  = this.bays.filter((bay) => bay.kind === "free" && bay.k !== this.rest && ready(bay));
    if (!busy.length || !open.length) return;

    const leaving  = busy[Math.floor(Math.random() * busy.length)];
    const arriving = open[Math.floor(Math.random() * open.length)];
    leaving.kind   = "free";
    arriving.kind  = "card";
    HL.tset(leaving.out, 1, now, 0);
    HL.tset(arriving.out, 0, now, GpuBaysFigure.ARRIVE_MS);
    this._retarget(now);
  }

  _draw(bay, lift, out, shut) {
    const ringZ = lift * out * (1 - shut);
    bay.socket.setAttribute("d", HL.poly(HL.ringAt(this.P, bay.ring, ringZ)));
    HL.place(bay.dot, this.P(bay.cx, bay.cy, ringZ));

    const lidZ            = lift * shut;
    const [lring, linner] = bay.lidRing;
    const u               = GpuBaysFigure.SLOT[0] - 1.4;
    const v               = GpuBaysFigure.SLOT[1] - 1.1;
    const top             = lidZ + GpuBaysFigure.LID * shut;
    HL.put(bay.lid, shut < 0.05 ? { sil: "", crease: "" } : HL.prism(this.P, this.front, lring, linner, lidZ, top));
    bay.mark.setAttribute("d", shut < 0.05 ? "" : HL.seg(this.P(bay.cx - u, bay.cy - v, top), this.P(bay.cx + u, bay.cy + v, top)) + HL.seg(this.P(bay.cx + u, bay.cy - v, top), this.P(bay.cx - u, bay.cy + v, top)));

    const [ring, inner] = bay.cardRing;
    const base          = lift + out * GpuBaysFigure.LEAVE;
    const height        = GpuBaysFigure.HEIGHT * (1 - out);
    HL.put(bay.card, height < 0.25 ? { sil: "", crease: "" } : HL.prism(this.P, this.front, ring, inner, base, base + height));
  }

  _drawFan(bay, lift, out) {
    const r = GpuBaysFigure.FAN * (1 - out);
    if (r < 0.5) {
      bay.fan.setAttribute("d", "");
      return;
    }
    const base = lift + out * GpuBaysFigure.LEAVE;
    const face = bay.cy + GpuBaysFigure.THICK / 2;
    const cz   = base + GpuBaysFigure.HEIGHT * (1 - out) * 0.5;
    const at   = (a, radius) => this.P(bay.cx + radius * Math.cos(a), face, cz + radius * Math.sin(a));
    let d      = HL.poly(Array.from({ length: 24 }, (_, k) => at((k / 24) * Math.PI * 2, r)));
    for (let blade = 0; blade < 3; blade++) {
      const a = bay.phase + (blade * Math.PI * 2) / 3;
      d      += HL.seg(at(a, r * 0.2), at(a + 0.45, r * 0.8));
    }
    bay.fan.setAttribute("d", d);
  }

  _move(p) {
    let best = 0;
    let gap  = Infinity;
    for (const bay of this.bays) {
      const dist = Math.hypot(bay.anchor[0] - p[0], bay.anchor[1] - p[1]);
      if (dist < gap) {
        gap  = dist;
        best = bay.k;
      }
    }
    this._choose(best);
  }

  setState(state) {
    const valid = state && [state.free, state.unavailable, state.capacity].every(Number.isFinite) && state.capacity > 0 && state.free >= 0 && state.unavailable >= 0;
    if (!valid) throw new Error("bays figure: state needs finite free >= 0, unavailable >= 0 and capacity > 0");

    const count   = this.bays.length;
    const offline = Math.min(count, Math.round((count * state.unavailable) / state.capacity));
    let free      = Math.min(count - offline, Math.round((count * state.free) / state.capacity));
    if (state.free > 0 && free === 0 && offline < count) free = 1;

    const shut = new Set(this._offlineOrder().slice(0, offline));
    for (const bay of this.bays) {
      if (shut.has(bay) && bay.kind !== "offline") this._setKind(bay, "offline", false);
      if (!shut.has(bay) && bay.kind === "offline") this._setKind(bay, "card", false);
    }

    const open    = this.bays.filter((bay) => bay.kind === "free");
    const busy    = this.bays.filter((bay) => bay.kind === "card");
    const shuffle = (list) => list.map((bay) => [Math.random(), bay]).sort((a, b) => a[0] - b[0]).map(([, bay]) => bay);
    if (open.length > free) for (const bay of shuffle(open).slice(0, open.length - free)) this._setKind(bay, "card", false);
    if (open.length < free) for (const bay of shuffle(busy).slice(0, free - open.length)) this._setKind(bay, "free", false);

    if (this.rest === null || this.bays[this.rest].kind !== "free") this.rest = this._restBay();
    this._retarget(performance.now());
  }

  _retarget(now) {
    const anchor = this.chosen === null ? this.rest : this.chosen;
    for (const bay of this.bays) {
      const target = this.chosen === null ? (bay.k === this.rest ? this.amount * GpuBaysFigure.REST_LIFT : 0) : bay.k === this.chosen ? this.amount : 0;
      HL.tset(bay.lift, target, now, 0);
      const lit = bay.k === anchor;
      bay.card.sil.classList.toggle("hi", lit && bay.kind === "card");
      bay.socket.setAttribute("class", lit && bay.kind === "free" ? "nf hi" : "nf lo");
      bay.lid.sil.setAttribute("class", lit && bay.kind === "offline" ? "sil hi" : "sil lo");
      bay.dot.setAttribute("class", bay.kind === "free" ? "dot m" : "dot off");
    }
    this.loop.wake();
  }
}

class ClusterAisleFigure extends HairlineFigureBase {
  static RANGE     = [6, 10, 14];
  static RACKS     = 3;
  static SLOTS     = 4;
  static GPUS      = 4;
  static WIDTH     = 17;
  static DEPTH     = 17;
  static HEIGHT    = 35.5;
  static GAP       = 5;
  static INSET     = 1.6;
  static FLOOR     = 3.4;
  static NODE      = 5.8;
  static PITCH     = 7.6;
  static BEZEL     = 0.5;
  static SCALE     = 3.05;
  static FAN       = 3.1;
  static FANS      = [0.3, 0.72];
  static BLADES    = 3;
  static SPIN      = [0.35, 4.2];
  static CHURN     = 2.8;
  static LED_X     = 2;
  static LED_PITCH = 1.9;
  static CARD      = [2.3, 3.6];
  static REST      = 6;
  static REST_PULL = 0.5;
  static FRONT     = 3;
  static CABLE     = 7;
  static BACK      = 1.8;
  static INLET     = -10;
  static TRAVEL    = 1.6;
  static PACKET    = 1.3;
  static DEFAULT   = { online: true, used: 31, total: 44, unavailable: 4, mine: 1 };

  constructor({ stage, svg }, value) {
    super(svg, value, ClusterAisleFigure.SCALE);
    this.online = true;
    this.clock  = 0;
    this.next   = ClusterAisleFigure.CHURN;
    this.length = ClusterAisleFigure.RACKS * (ClusterAisleFigure.WIDTH + ClusterAisleFigure.GAP) - ClusterAisleFigure.GAP;
    this.spin   = HL.spring(0, { k: 3, c: 3.5, eps: 0.01 });
    this.packet = null;
    this._camera(this._extent(), 168);
    this._plinth(-6, -5, this.length + 6, ClusterAisleFigure.DEPTH + ClusterAisleFigure.RANGE[2] + ClusterAisleFigure.FRONT, 5, 4);
    this._build();
    this._apply(ClusterAisleFigure.DEFAULT);
    this._start(stage, svg);
    this._retarget(performance.now());
  }

  _extent() {
    const front = ClusterAisleFigure.DEPTH + ClusterAisleFigure.RANGE[2] + ClusterAisleFigure.FRONT;
    const top   = ClusterAisleFigure.HEIGHT + ClusterAisleFigure.CABLE;
    return [[-6, -5, -4], [this.length + 6, front, -4], [this.length + 6, -5, -4], [-6, front, -4], [ClusterAisleFigure.INLET, ClusterAisleFigure.BACK, top], [this.length, ClusterAisleFigure.DEPTH, top]];
  }

  _build() {
    this.racks   = [];
    this.drawers = [];
    for (let r = 0; r < ClusterAisleFigure.RACKS; r++) {
      const x0            = r * (ClusterAisleFigure.WIDTH + ClusterAisleFigure.GAP);
      const [ring, inner] = HL.rings(x0, 0, x0 + ClusterAisleFigure.WIDTH, ClusterAisleFigure.DEPTH, 1.6, 1.1);
      const el            = HL.solid(this.g);
      HL.put(el, HL.prism(this.P, this.front, ring, inner, 0, ClusterAisleFigure.HEIGHT));
      const fans          = HL.mk("path", { class: "nf lo" }, this.g);
      this.racks.push({ r, x0, el, fans, phases: ClusterAisleFigure.FANS.map((_, j) => r * 1.3 + j * 0.9) });
      for (let s = 0; s < ClusterAisleFigure.SLOTS; s++) this.drawers.push(this._drawer(s, x0));
    }
    this.cable = HL.mk("path", { class: "nf lo", d: this._cable() }, this.g);
    this.dot   = HL.mk("circle", { r: 0, class: "dot" }, this.g);
  }

  _cable() {
    const y     = ClusterAisleFigure.BACK;
    const z     = ClusterAisleFigure.HEIGHT + ClusterAisleFigure.CABLE;
    const ends  = this.racks.map((rack) => rack.x0 + ClusterAisleFigure.WIDTH / 2);
    const drops = ends.map((x) => HL.seg(this.P(x, y, z), this.P(x, y, ClusterAisleFigure.HEIGHT))).join("");
    return HL.open([this.P(ClusterAisleFigure.INLET, y, z), this.P(ends[ends.length - 1], y, z)]) + drops;
  }

  _drawer(s, x0) {
    const k     = this.drawers.length;
    const z0    = ClusterAisleFigure.FLOOR + s * ClusterAisleFigure.PITCH;
    const group = HL.mk("g", {}, this.g);
    const el    = HL.solid(group);
    const leds  = Array.from({ length: ClusterAisleFigure.GPUS }, () => HL.mk("circle", { r: 0.95, class: "dot off" }, group));
    const rest  = this.P(x0 + ClusterAisleFigure.WIDTH / 2, ClusterAisleFigure.DEPTH, z0 + ClusterAisleFigure.NODE / 2);
    return { k, rank: (k * 5) % (ClusterAisleFigure.RACKS * ClusterAisleFigure.SLOTS), x0: x0 + ClusterAisleFigure.INSET, x1: x0 + ClusterAisleFigure.WIDTH - ClusterAisleFigure.INSET, z0, z1: z0 + ClusterAisleFigure.NODE, el, leds, rest, alloc: 0, mine: false, parked: false, tw: HL.tween(0), drawn: NaN };
  }

  _apply(state) {
    if (typeof state.online !== "boolean") throw new Error("cluster figure: state.online must be a boolean");
    for (const key of ["used", "total", "unavailable", "mine"]) {
      if (!Number.isFinite(state[key]) || state[key] < 0) throw new Error(`cluster figure: state.${key} must be a non-negative number`);
    }

    const count  = this.drawers.length;
    const all    = state.total + state.unavailable;
    this._park(all ? Math.round((count * state.unavailable) / all) : count);

    const live   = this.drawers.filter((d) => !d.parked);
    const mine   = Math.min(Math.round(state.mine), live.length);
    this._own(mine);

    const share  = state.total ? Math.min(1, state.used / state.total) : 0;
    const others = Math.max(0, Math.round(live.length * ClusterAisleFigure.GPUS * share) - mine * ClusterAisleFigure.GPUS);
    this._fill(others);

    const [idle, full] = ClusterAisleFigure.SPIN;
    this.online        = state.online;
    this.spin.t        = state.online ? idle + (full - idle) * share : 0;
    this.rest          = this._restDrawer();
    if (!state.online) this._drop();
    this._paint();
  }

  _park(n) {
    const parked = this.drawers.filter((d) => d.parked);
    for (const d of parked.slice(n)) d.parked = false;
    const spare  = this.drawers.filter((d) => !d.parked).sort((a, b) => Number(a.mine) - Number(b.mine) || a.alloc - b.alloc || a.rank - b.rank);
    for (const d of spare.slice(0, Math.max(0, n - parked.length))) {
      d.parked = true;
      d.mine   = false;
      d.alloc  = 0;
    }
  }

  _own(m) {
    const owned = this.drawers.filter((d) => d.mine);
    for (const d of owned.slice(m)) {
      d.mine  = false;
      d.alloc = ClusterAisleFigure.GPUS;
    }
    const free  = this.drawers.filter((d) => !d.parked && !d.mine).sort((a, b) => b.alloc - a.alloc || a.rank - b.rank);
    for (const d of free.slice(0, Math.max(0, m - owned.length))) {
      d.mine  = true;
      d.alloc = 0;
    }
  }

  _fill(target) {
    const pool = this.drawers.filter((d) => !d.parked && !d.mine);
    const room = pool.length * ClusterAisleFigure.GPUS;
    let delta  = Math.min(target, room) - pool.reduce((sum, d) => sum + d.alloc, 0);
    while (delta > 0) {
      this._pick(pool.filter((d) => d.alloc < ClusterAisleFigure.GPUS)).alloc += 1;
      delta -= 1;
    }
    while (delta < 0) {
      this._pick(pool.filter((d) => d.alloc > 0)).alloc -= 1;
      delta += 1;
    }
  }

  _pick(list) {
    return list[Math.floor(Math.random() * list.length)];
  }

  _restDrawer() {
    const mine = this.drawers.filter((d) => d.mine).sort((a, b) => a.rank - b.rank);
    return mine.length ? mine[0].k : ClusterAisleFigure.REST;
  }

  _drop() {
    this.packet = null;
    this.dot.setAttribute("r", "0");
  }

  _paint() {
    for (const d of this.drawers) d.leds.forEach((led, i) => led.setAttribute("class", this._led(d, i)));
  }

  _led(d, i) {
    if (!this.online || d.parked) return "dot off";
    if (d.mine) return "dot";
    return i < d.alloc ? "dot m" : "dot off";
  }

  _tick(dt, now) {
    this._advance(this.drawers, now);
    this.clock += dt;
    if (this.packet) this._carry(dt);
    else if (this.online && this.clock >= this.next) this._churn();
    HL.stepS(this.spin, dt);
    for (const rack of this.racks) this._drawFans(rack, dt);
    return true;
  }

  _churn() {
    this.next  = this.clock + ClusterAisleFigure.CHURN * (0.85 + 0.3 * Math.random());
    const pool = this.drawers.filter((d) => !d.parked && !d.mine);
    const from = pool.filter((d) => d.alloc > 0);
    if (!from.length) return;
    const a    = this._pick(from);
    const to   = pool.filter((d) => d !== a && d.alloc < ClusterAisleFigure.GPUS);
    if (!to.length) return;
    const b    = this._pick(to);
    const g    = Math.min(a.alloc, ClusterAisleFigure.GPUS - b.alloc, 1 + Math.floor(Math.random() * 2));
    const rack = this.racks[Math.floor(b.k / ClusterAisleFigure.SLOTS)];

    this.packet = { a, b, g, x: rack.x0 + ClusterAisleFigure.WIDTH / 2, t: 0 };
  }

  _carry(dt) {
    const packet = this.packet;
    packet.t     = Math.min(1, packet.t + dt / ClusterAisleFigure.TRAVEL);
    const ease   = packet.t * packet.t * (3 - 2 * packet.t);
    const run    = packet.x - ClusterAisleFigure.INLET;
    const along  = ease * (run + ClusterAisleFigure.CABLE);
    const y      = ClusterAisleFigure.BACK;
    const z      = ClusterAisleFigure.HEIGHT + ClusterAisleFigure.CABLE;
    const point  = along <= run ? [ClusterAisleFigure.INLET + along, y, z] : [packet.x, y, z - (along - run)];
    HL.place(this.dot, this.P(...point));
    this.dot.setAttribute("r", String(ClusterAisleFigure.PACKET));
    if (packet.t < 1) return;

    this._drop();
    this._land(packet);
  }

  _land({ a, b, g }) {
    if (a.parked || a.mine || b.parked || b.mine) return;
    const moved = Math.min(g, a.alloc, ClusterAisleFigure.GPUS - b.alloc);
    a.alloc    -= moved;
    b.alloc    += moved;
    this._paint();
  }

  _drawFans(rack, dt) {
    const cx = rack.x0 + ClusterAisleFigure.WIDTH / 2;
    const r  = ClusterAisleFigure.FAN;
    let d    = "";
    rack.phases.forEach((phase, j) => {
      const turn     = (phase + this.spin.x * dt) % (Math.PI * 2);
      const cy       = ClusterAisleFigure.DEPTH * ClusterAisleFigure.FANS[j];
      const at       = (a, radius) => this.P(cx + radius * Math.cos(a), cy + radius * Math.sin(a), ClusterAisleFigure.HEIGHT);
      rack.phases[j] = turn;
      d             += HL.poly(Array.from({ length: 28 }, (_, i) => at((i / 28) * Math.PI * 2, r)));
      for (let b = 0; b < ClusterAisleFigure.BLADES; b++) {
        const a = turn + (b * Math.PI * 2) / ClusterAisleFigure.BLADES;
        d      += HL.seg(at(a, 0.6), at(a + 0.6, r * 0.82));
      }
    });
    rack.fans.setAttribute("d", d);
  }

  _draw(d, out) {
    const y1            = ClusterAisleFigure.DEPTH + ClusterAisleFigure.BEZEL + out;
    const open          = out > 1.2;
    const [ring, inner] = HL.rings(d.x0, ClusterAisleFigure.DEPTH, d.x1, y1, 0.8, 0.6);
    const shape         = HL.prism(this.P, this.front, ring, open ? inner : null, d.z0, d.z1);
    const zm            = (d.z0 + d.z1) / 2;
    const handle        = HL.seg(this.P(d.x1 - 3.4, y1, zm), this.P(d.x1 - 1.4, y1, zm));
    HL.put(d.el, { sil: shape.sil, crease: shape.crease + handle + this._cards(d, y1) });
    d.leds.forEach((led, i) => HL.place(led, this.P(d.x0 + ClusterAisleFigure.LED_X + i * ClusterAisleFigure.LED_PITCH, y1, zm)));
  }

  _cards(d, y1) {
    const [w, l] = ClusterAisleFigure.CARD;
    const front  = y1 - 0.9;
    const back   = Math.max(ClusterAisleFigure.DEPTH + 0.4, front - l);
    if (front - back < 0.6) return "";
    const span   = d.x1 - d.x0;
    let path     = "";
    for (let i = 0; i < ClusterAisleFigure.GPUS; i++) {
      const cx = d.x0 + (span * (i + 0.5)) / ClusterAisleFigure.GPUS;
      path    += HL.poly([[cx - w / 2, back], [cx + w / 2, back], [cx + w / 2, front], [cx - w / 2, front]].map(([x, y]) => this.P(x, y, d.z1)));
    }
    return path;
  }

  _move(p) {
    let best = 0;
    let gap  = Infinity;
    for (const d of this.drawers) {
      const g = Math.hypot(d.rest[0] - p[0], d.rest[1] - p[1]);
      if (g >= gap) continue;
      gap  = g;
      best = d.k;
    }
    this._choose(best);
  }

  setState(state) {
    this._apply(state);
    this._retarget(performance.now());
  }

  _lit() {
    return this.chosen === null ? this.rest : this.chosen;
  }

  _retarget(now) {
    const lit = this._lit();
    for (const d of this.drawers) {
      const target = d.k !== lit ? 0 : this.chosen === null ? this.amount * ClusterAisleFigure.REST_PULL : this.amount;
      HL.tset(d.tw, target, now, 0);
      d.el.sil.classList.toggle("hi", d.k === lit);
      d.el.sil.classList.toggle("lo", d.parked && d.k !== lit);
      d.el.sil.classList.toggle("dash", d.parked && d.k !== lit);
    }
    this.loop.wake();
  }
}

class HourglassFigure extends HairlineFigureBase {
  static RANGE   = [1.5, 2.5, 4];
  static HALF    = 15;
  static BULB    = 9.6;
  static SWELL   = 2.15;
  static ROUND   = 0.55;
  static NECK    = 1.1;
  static INSET   = 0.9;
  static CAP_R   = 11.6;
  static CAP_H   = 2.6;
  static CAP_LIP = 1.2;
  static POST_R  = 10.6;
  static POST    = 0.75;
  static PLINTH  = 15;
  static FILL    = 0.7;
  static PEAK    = 4.5;
  static TIP     = 1.6;
  static RING    = 32;
  static SLICES  = 12;
  static PERIOD  = 9;
  static PAUSE   = 0.5;
  static TURN    = 1.4;
  static RAISE   = 6;
  static STRATA  = 3;
  static SETTLE  = 0.7;
  static REST    = 0.42;
  static SCALE   = 4.4;

  constructor({ stage, svg }, value) {
    super(svg, value, HourglassFigure.SCALE);
    this.axis   = [Math.SQRT1_2, Math.SQRT1_2, 0];
    this.centre = HourglassFigure.CAP_H + HourglassFigure.HALF;
    this.period = HourglassFigure.PERIOD;
    this.table  = this._volumes();
    this.total  = this._volumeAt(HourglassFigure.FILL);
    this.full   = this._levelFor(this._volumeAt(1) - this.total);
    this.mode   = "flow";
    this.clock  = HourglassFigure.REST * this._flowTime();
    this.turns  = 0;
    this.up     = 1;
    this.lift   = HL.tween(0);
    this.order  = "";
    this._camera(this._extent(), 160);
    this._buildPlinth();
    this._buildParts();
    this.restHull = this._restHull();
    this._start(stage, svg);
    this._retarget(performance.now());
  }

  _radius(s) {
    return HourglassFigure.NECK + (HourglassFigure.BULB - HourglassFigure.NECK) * Math.sin(s * HourglassFigure.SWELL) ** HourglassFigure.ROUND;
  }

  _inner(s) {
    return Math.max(0.25, this._radius(s) - HourglassFigure.INSET);
  }

  _volumes() {
    const steps = 240;
    const table = [0];
    for (let i = 1; i <= steps; i++) {
      const r0 = this._inner((i - 1) / steps);
      const r1 = this._inner(i / steps);
      table.push(table[i - 1] + ((r0 * r0 + r1 * r1) / 2) / steps);
    }
    return table;
  }

  _volumeAt(s) {
    const steps = this.table.length - 1;
    const x     = HL.clamp(s, 0, 1) * steps;
    const i     = Math.min(steps - 1, Math.floor(x));
    return HL.lerp(this.table[i], this.table[i + 1], x - i);
  }

  _levelFor(volume) {
    const steps = this.table.length - 1;
    if (volume <= 0) return 0;
    if (volume >= this.table[steps]) return 1;
    let i = 0;
    while (this.table[i + 1] < volume) i++;
    return (i + (volume - this.table[i]) / (this.table[i + 1] - this.table[i])) / steps;
  }

  _flowTime() {
    return Math.max(3, this.period - HourglassFigure.PAUSE - HourglassFigure.TURN - HourglassFigure.SETTLE);
  }

  _extent() {
    const top   = 2 * (HourglassFigure.CAP_H + HourglassFigure.HALF);
    const reach = HourglassFigure.HALF + HourglassFigure.CAP_H;
    const plate = HourglassFigure.PLINTH * Math.SQRT1_2;
    const back  = HourglassFigure.CAP_R * Math.SQRT1_2;
    const high  = this.centre + HourglassFigure.RAISE;
    return [[plate, -plate, -3], [-plate, plate, -3], [plate, plate, -3], [-plate, -plate, -3], [-back, -back, top], [reach * Math.SQRT1_2, -reach * Math.SQRT1_2, high], [-reach * Math.SQRT1_2, reach * Math.SQRT1_2, high]];
  }

  _buildPlinth() {
    const R = HourglassFigure.PLINTH;
    HL.put(HL.solid(this.g), HL.prism(this.P, this.front, HL.circ(R, 72), HL.circ(R - 2, 72), -3, 0));
    HL.mk("path", { d: HL.poly(HL.ringAt(this.P, HL.circ(HourglassFigure.CAP_R + 1.6, 64), 0)), class: "nf lo" }, this.g);
  }

  _buildParts() {
    this.layer  = HL.mk("g", {}, this.g);
    this.caps   = [1, -1].map((sign) => ({ sign, el: HL.solid(this.layer) }));
    this.posts  = [1, -1].map((side) => ({ side, el: HL.solid(this.layer) }));
    this.sands  = [1, -1].map((sign) => ({ sign, el: HL.solid(this.layer) }));
    this.stream = HL.mk("path", { class: "nf" }, this.layer);
    this.glass  = HL.mk("path", { class: "nf" }, this.layer);
    this.glint  = HL.mk("path", { class: "nf lo" }, this.layer);
  }

  _restHull() {
    const points = [];
    const to     = this._projector(0, 0);
    for (const sign of [1, -1]) {
      const end = sign * (HourglassFigure.HALF + HourglassFigure.CAP_H);
      points.push(...this._ring(to, HourglassFigure.CAP_R, end));
    }
    return HL.hull(points);
  }

  _projector(phi, lift) {
    const [dx, dy] = this.axis;
    const c        = Math.cos(phi);
    const s        = Math.sin(phi);
    return (a, b, w) => {
      const along = dx * a + dy * b;
      const cx    = dy * w;
      const cy    = -dx * w;
      const cz    = dx * b - dy * a;
      const x     = a * c + cx * s + dx * along * (1 - c);
      const y     = b * c + cy * s + dy * along * (1 - c);
      const z     = w * c + cz * s;
      return this.P(x, y, z + this.centre + lift);
    };
  }

  _turned(phi, vector) {
    const [dx, dy]  = this.axis;
    const [a, b, w] = vector;
    const c         = Math.cos(phi);
    const s         = Math.sin(phi);
    const along     = dx * a + dy * b;
    return [a * c + dy * w * s + dx * along * (1 - c), b * c - dx * w * s + dy * along * (1 - c), w * c + (dx * b - dy * a) * s];
  }

  _ring(to, r, w) {
    return HL.circ(r, HourglassFigure.RING).map((q) => to(q.u, q.v, w));
  }

  _facing(phi, normal) {
    const n    = this._turned(phi, normal);
    const zf   = Math.sqrt(1 - this.C.k * this.C.k);
    const view = [Math.sin(this.C.az) * zf, Math.cos(this.C.az) * zf, this.C.k];
    return n[0] * view[0] + n[1] * view[1] + n[2] * view[2];
  }

  setState(state) {
    if (!state || typeof state.wait_s !== "number" || !Number.isFinite(state.wait_s) || state.wait_s < 0) throw new Error("hourglass figure: state.wait_s must be a non-negative number of seconds");
    const share = this.mode === "flow" ? this.clock / this._flowTime() : 0;
    this.period = HL.clamp(5 + 3 * Math.log2(1 + state.wait_s / 300), 5, 20);
    if (this.mode === "flow") this.clock = share * this._flowTime();
    this.loop.wake();
  }

  _tick(dt, now) {
    if (!HL.reducedMotion()) this._step(dt);
    this._draw(now);
    return true;
  }

  _step(dt) {
    this.clock += dt;
    const lengths = { flow: this._flowTime(), pause: HourglassFigure.PAUSE, turn: HourglassFigure.TURN, settle: HourglassFigure.SETTLE };
    const next    = { flow: "pause", pause: "turn", turn: "settle", settle: "flow" };
    while (this.clock >= lengths[this.mode]) {
      this.clock -= lengths[this.mode];
      if (this.mode === "turn") {
        this.turns += 1;
        this.up     = -this.up;
      }
      this.mode = next[this.mode];
    }
  }

  _ease(t) {
    return t * t * (3 - 2 * t);
  }

  _phase() {
    if (this.mode === "turn") {
      const t = this.clock / HourglassFigure.TURN;
      return { phi: (this.turns + this._ease(t)) * Math.PI, progress: 1, raise: HourglassFigure.RAISE * Math.sin(Math.PI * t) };
    }
    if (this.mode === "settle") return { phi: this.turns * Math.PI, progress: 0, settle: this._ease(this.clock / HourglassFigure.SETTLE) };
    if (this.mode === "pause") return { phi: this.turns * Math.PI, progress: 1 };
    return { phi: this.turns * Math.PI, progress: this.clock / this._flowTime() };
  }

  _bodies(phase) {
    const upper = this.up;
    const lower = -this.up;
    if (phase.settle !== undefined) {
      const t = phase.settle;
      return { [upper]: { lo: HL.lerp(this.full, 0, t), hi: HL.lerp(1, HourglassFigure.FILL, t), peak: HL.lerp(HourglassFigure.PEAK, 0, t) }, [lower]: null };
    }
    const p      = HL.clamp(phase.progress, 0, 1);
    const top    = this._levelFor(this.total * (1 - p));
    const bottom = this._levelFor(this._volumeAt(1) - this.total * p);
    const peak   = HourglassFigure.PEAK * Math.min(1, p / 0.08);
    return { [upper]: top > 0.004 ? { lo: 0, hi: top, peak: 0 } : null, [lower]: p > 0.002 ? { lo: bottom, hi: 1, peak } : null };
  }

  _draw(now) {
    const phase   = this._phase();
    const lift    = HL.tval(this.lift, now) + (phase.raise || 0);
    const to      = this._projector(phase.phi, lift);
    const bodies  = this._bodies(phase);
    const flowing = this.mode === "flow" && bodies[this.up] !== null;

    for (const cap of this.caps) this._drawCap(cap, to, phase.phi);
    for (const post of this.posts) this._drawPost(post, to);
    for (const sand of this.sands) this._drawSand(sand, to, phase.phi, bodies[sand.sign]);
    this._drawGlass(to, phase.phi);
    this._drawStream(to, flowing ? bodies[-this.up] : undefined);
    this._paint(phase.phi, flowing);
  }

  _drawCap(cap, to, phi) {
    const inner = cap.sign * HourglassFigure.HALF;
    const outer = cap.sign * (HourglassFigure.HALF + HourglassFigure.CAP_H);
    const sil   = HL.poly(HL.hull(this._ring(to, HourglassFigure.CAP_R, inner).concat(this._ring(to, HourglassFigure.CAP_R, outer))));
    const face  = this._facing(phi, [0, 0, cap.sign]) > 0 ? outer : inner;
    const sign  = face === outer ? cap.sign : -cap.sign;
    const lip   = HL.circ(HourglassFigure.CAP_R - HourglassFigure.CAP_LIP, HourglassFigure.RING * 2);
    const front = HL.run(lip, (q) => this._facing(phi, [q.nu, q.nv, 0]) >= 0 && this._facing(phi, [0, 0, sign]) > 0);
    HL.put(cap.el, { sil, crease: HL.open(front.map((q) => to(q.u, q.v, face))) });
  }

  _drawPost(post, to) {
    const offset = post.side * HourglassFigure.POST_R * Math.SQRT1_2;
    const ring   = HL.circ(HourglassFigure.POST, 12);
    const at     = (w) => ring.map((q) => to(offset + q.u, -offset + q.v, w));
    HL.put(post.el, { sil: HL.poly(HL.hull(at(-HourglassFigure.HALF).concat(at(HourglassFigure.HALF)))), crease: "" });
  }

  _drawSand(sand, to, phi, body) {
    if (!body || body.hi - body.lo < 0.004) {
      HL.put(sand.el, { sil: "", crease: "" });
      return;
    }
    const points = [];
    const count  = Math.max(2, Math.ceil(HourglassFigure.SLICES * (body.hi - body.lo)) + 1);
    for (let k = 0; k < count; k++) {
      const s = HL.lerp(body.lo, body.hi, k / (count - 1));
      points.push(...this._ring(to, this._inner(s), sand.sign * s * HourglassFigure.HALF));
    }
    if (body.peak > 0.05) {
      const apex = Math.max(0.03, body.lo - body.peak / HourglassFigure.HALF);
      points.push(...this._ring(to, Math.min(HourglassFigure.TIP, this._inner(apex)), sand.sign * apex * HourglassFigure.HALF));
    }
    const surface = body.lo === 0 && this._facing(phi, [0, 0, sand.sign]) > 0 ? HL.poly(this._ring(to, this._inner(body.hi), sand.sign * body.hi * HourglassFigure.HALF)) : "";
    HL.put(sand.el, { sil: HL.poly(HL.hull(points)), crease: surface + this._strata(to, phi, sand.sign, body) });
  }

  _strata(to, phi, sign, body) {
    let d = "";
    for (let k = 1; k <= HourglassFigure.STRATA; k++) {
      const s = HL.lerp(body.lo, body.hi, k / (HourglassFigure.STRATA + 1));
      const r = this._inner(s) - 0.4;
      if (r < 1.2) continue;
      const front = HL.run(HL.circ(r, HourglassFigure.RING), (q) => this._facing(phi, [q.nu, q.nv, 0]) >= 0);
      d += HL.open(front.map((q) => to(q.u, q.v, sign * s * HourglassFigure.HALF)));
    }
    return d;
  }

  _drawGlass(to, phi) {
    let d     = "";
    let glint = "";
    for (const sign of [1, -1]) {
      const points = [];
      for (let k = 0; k <= HourglassFigure.SLICES; k++) {
        const s = k / HourglassFigure.SLICES;
        points.push(...this._ring(to, this._radius(s), sign * s * HourglassFigure.HALF));
      }
      d += HL.poly(HL.hull(points));
      const line = [];
      for (let k = 0; k <= 8; k++) {
        const s = HL.lerp(0.38, 0.86, k / 8);
        const r = this._radius(s) - 0.9;
        line.push(to(-r * 0.97, r * 0.26, sign * s * HourglassFigure.HALF));
      }
      glint += HL.open(line);
    }
    this.glass.setAttribute("d", d);
    this.glint.setAttribute("d", glint);
  }

  _drawStream(to, pile) {
    if (pile === undefined) {
      this.stream.setAttribute("d", "");
      return;
    }
    const sign = -this.up;
    const end  = pile ? Math.max(0.03, pile.lo - pile.peak / HourglassFigure.HALF) : 1;
    this.stream.setAttribute("d", HL.seg(to(0, 0, 0), to(0, 0, sign * end * HourglassFigure.HALF)));
  }

  _paint(phi, flowing) {
    const upper  = this._turned(phi, [0, 0, 1])[2] >= 0 ? 1 : -1;
    const lit    = this.chosen === null ? (flowing ? "stream" : "sand") : "glass";
    const held   = this.mode === "settle" ? this.up : -this.up;
    const key    = `${upper}|${lit}|${held}`;
    if (key === this.order) return;
    this.order   = key;
    const cap    = (sign) => this.caps.find((c) => c.sign === sign).el.g;
    const sand   = (sign) => this.sands.find((c) => c.sign === sign).el.g;
    for (const node of [cap(-upper), this.posts[0].el.g, this.posts[1].el.g, sand(-upper), this.stream, sand(upper), this.glass, this.glint, cap(upper)]) this.layer.appendChild(node);
    this.stream.setAttribute("class", lit === "stream" ? "nf hi" : "nf");
    this.glass.setAttribute("class", lit === "glass" ? "nf hi" : "nf");
    for (const s of this.sands) s.el.sil.classList.toggle("hi", lit === "sand" && s.sign === held);
  }

  _move(p) {
    this._choose(HairlineGeometry.inside(this.restHull, p) ? 0 : null);
  }

  _retarget(now) {
    HL.tset(this.lift, this.chosen === null ? 0 : this.amount, now, 0);
    this.order = "";
    this.loop.wake();
  }
}

class QueueLineFigure extends HairlineFigureBase {
  static RANGE   = [3, 5, 8];
  static SCALE   = 4.3;
  static DEFAULT = { pending: 27, mine: 1 };
  static SLOTS   = 14;
  static FULL    = 40;
  static SPACING = 6.8;
  static TURN    = 6.5;
  static HALF    = 13;
  static END     = 26;
  static HEAD    = -22;
  static PUCK    = 2.6;
  static PUCK_H  = 3.2;
  static BASE    = 1.5;
  static POLE    = 0.45;
  static CAP     = 0.85;
  static POST_H  = 7;
  static ROPE_Z  = 6.3;
  static SAG     = 1.6;
  static GPU     = [-44, -1, -30, 14];
  static GPU_H   = 6;
  static SOCKET  = [-34, 6.5];
  static FAN     = [-40, 6.5, 3.4];
  static EVERY   = 2.5;
  static SLIDE   = 900;
  static WAVE    = 45;
  static EXIT    = 1500;
  static HOP     = 4;
  static SPIN    = [1.2, 9];
  static REST    = 0.5;

  constructor({ stage, svg }, value) {
    super(svg, value, QueueLineFigure.SCALE);
    this.data     = QueueLineFigure.DEFAULT;
    this.pucks    = [];
    this.leaving  = [];
    this.serial   = 0;
    this.clock    = 0;
    this.fanAngle = 0;
    this.kicked   = -1e9;
    this.orderKey = "";

    this._camera(this._extent(), 164);
    this._plinth(QueueLineFigure.GPU[0] - 4, -QueueLineFigure.TURN * 2 - 4, QueueLineFigure.END + 4, QueueLineFigure.TURN * 2 + 4, 6, 3);
    this.scene    = HL.mk("g", {}, this.g);
    this.path     = this._buildPath();
    this.statics  = [...this._buildPosts(), ...this._buildRopes()];
    this.gpu      = this._buildGpu();
    this.puckRing = [HL.circ(QueueLineFigure.PUCK, 28), HL.circ(QueueLineFigure.PUCK - 0.6, 28)];

    this._sync(performance.now(), true);
    this._start(stage, svg);
    this._retarget(performance.now());
  }

  _extent() {
    const x0  = QueueLineFigure.GPU[0] - 4;
    const x1  = QueueLineFigure.END + 4;
    const y   = QueueLineFigure.TURN * 2 + 4;
    const top = QueueLineFigure.POST_H + 1;
    return [[x0, -y, -3], [x1, y, -3], [x1, -y, -3], [x0, y, -3], [-QueueLineFigure.END, -QueueLineFigure.TURN * 2, top], [QueueLineFigure.SOCKET[0], QueueLineFigure.SOCKET[1], QueueLineFigure.GPU_H + QueueLineFigure.RANGE[2] + QueueLineFigure.PUCK_H]];
  }

  _buildPath() {
    const half = QueueLineFigure.HALF;
    const r    = QueueLineFigure.TURN;
    const line = (a, b) => ({ kind: "line", a, b, length: Math.hypot(b[0] - a[0], b[1] - a[1]) });
    const arc  = (c, from, to) => ({ kind: "arc", c, from, to, length: Math.abs(to - from) * r });
    return [
      line([QueueLineFigure.HEAD, r], [half, r]),
      arc([half, 0], Math.PI / 2, -Math.PI / 2),
      line([half, -r], [-QueueLineFigure.END + 1.5, -r]),
    ];
  }

  _buildPosts() {
    const seen = new Map();
    for (const points of this._lines()) {
      for (const [x, y] of points) seen.set(`${x}|${y}`, [x, y]);
    }

    const parts = [[QueueLineFigure.BASE, 0, 0.5], [QueueLineFigure.POLE, 0.5, QueueLineFigure.POST_H], [QueueLineFigure.CAP, QueueLineFigure.POST_H, QueueLineFigure.POST_H + 0.8]];
    return [...seen.values()].map(([x, y]) => {
      const group = HL.mk("g", {}, this.scene);
      for (const [r, z0, z1] of parts) HL.put(HL.solid(group), HL.prism(this._shifted(x, y, 0), this.front, HL.circ(r, 20), null, z0, z1));
      return { id: `post ${x} ${y}`, group, depth: x + y };
    });
  }

  _buildRopes() {
    const ropes = [];
    for (const points of this._lines()) {
      for (let k = 1; k < points.length; k++) {
        const a     = points[k - 1];
        const b     = points[k];
        const line  = Array.from({ length: 11 }, (_, j) => {
          const t = j / 10;
          return this.P(HL.lerp(a[0], b[0], t), HL.lerp(a[1], b[1], t), QueueLineFigure.ROPE_Z - 4 * QueueLineFigure.SAG * t * (1 - t));
        });
        const group = HL.mk("g", {}, this.scene);
        HL.mk("path", { d: HL.open(line), class: "nf sil" }, group);
        ropes.push({ id: `rope ${a} ${b}`, group, depth: (a[0] + b[0] + a[1] + b[1]) / 2 });
      }
    }
    return ropes;
  }

  _lines() {
    const row = 2 * QueueLineFigure.TURN;
    const end = QueueLineFigure.END;
    return [
      [[-end, -row], [0, -row], [end, -row]],
      [[-end, 0], [-QueueLineFigure.TURN, 0], [QueueLineFigure.HALF, 0]],
      [[-end, row], [0, row], [end, row]],
      [[end, -row], [end, 0], [end, row]],
    ];
  }

  _buildGpu() {
    const [x0, y0, x1, y1] = QueueLineFigure.GPU;
    const [ring, inner]    = HL.rings(x0, y0, x1, y1, 2.4, 1.1);
    const group            = HL.mk("g", {}, this.scene);
    const el               = HL.solid(group);
    const rims             = HL.mk("path", { class: "nf lo" }, group);
    const blades           = HL.mk("path", { class: "nf" }, group);
    const led              = HL.flatDot(group, this.C, 0.9, "dot m");
    return { id: "gpu", group, el, ring, inner, rims, blades, led, tw: HL.tween(0), drawn: NaN, depth: (x0 + x1 + y0 + y1) / 2 };
  }

  setState(state) {
    if (state === null || typeof state !== "object") throw new Error("queueline figure: state must be an object with pending and mine");
    for (const key of ["pending", "mine"]) {
      if (!Number.isFinite(state[key]) || state[key] < 0) throw new Error(`queueline figure: state.${key} must be a non-negative number, got ${state[key]}`);
    }

    const now = performance.now();
    this.data = { pending: state.pending, mine: state.mine };
    this._sync(now, false);
    if (typeof this.chosen === "number" && this.chosen >= this.pucks.length) this.chosen = null;
    this._retarget(now);
    this._tick(0, now);
  }

  _sync(now, instant) {
    const filled = this._filled(this.data);
    while (this.pucks.length < filled) this._spawn(now, instant);
    while (this.pucks.length > filled) this._drop(this.pucks.pop(), now);
    this._mark();
  }

  _spawn(now, instant) {
    const u     = this.pucks.length * QueueLineFigure.SPACING;
    const group = HL.mk("g", {}, this.scene);
    const puck  = { id: `puck ${this.serial++}`, group, el: HL.solid(group), dot: null, mine: false, from: instant ? u : u + QueueLineFigure.SPACING, to: u, travel: HL.tween(instant ? 1 : 0, QueueLineFigure.SLIDE), grow: HL.tween(instant ? 1 : 0), tw: HL.tween(0), exit: null, kicked: false, drawn: "", depth: 0 };
    if (!instant) {
      HL.tset(puck.travel, 1, now, 0);
      HL.tset(puck.grow, 1, now, 0);
    }
    this.pucks.push(puck);
  }

  _drop(puck, now) {
    puck.from   = puck.to;
    puck.travel = HL.tween(1);
    HL.tset(puck.grow, 0, now, 0);
    HL.tset(puck.tw, 0, now, 0);
    puck.el.sil.classList.remove("hi");
    this.leaving.push(puck);
  }

  _mark() {
    const target = Math.min(Math.round(this.data.mine), this.pucks.length);
    let marked   = this.pucks.filter((puck) => puck.mine).length;
    for (let k = this.pucks.length - 1; k >= 0 && marked > target; k--) {
      if (!this.pucks[k].mine) continue;
      this._setMine(this.pucks[k], false);
      marked--;
    }
    for (let k = this.pucks.length - 1; k >= 0 && marked < target; k--) {
      if (this.pucks[k].mine) continue;
      this._setMine(this.pucks[k], true);
      marked++;
    }
  }

  _setMine(puck, mine) {
    puck.mine  = mine;
    puck.drawn = "";
    if (mine && !puck.dot) puck.dot = HL.flatDot(puck.group, this.C, 0.85, "dot");
    if (!mine && puck.dot) {
      puck.dot.remove();
      puck.dot = null;
    }
  }

  _tick(dt, now) {
    this.clock += dt;
    if (this.clock >= QueueLineFigure.EVERY) {
      this.clock -= QueueLineFigure.EVERY;
      this._step(now);
    }

    for (const puck of this.pucks) this._draw(puck, now);
    for (const puck of [...this.leaving]) this._draw(puck, now);
    this._drawGpu(dt, now);
    this._order();
    return true;
  }

  _step(now) {
    if (!this.pucks.length) return;

    const head = this.pucks.shift();
    head.exit  = now;
    HL.tset(head.tw, 0, now, 0);
    head.el.sil.classList.remove("hi");
    this.leaving.push(head);

    this.pucks.forEach((puck, k) => {
      puck.from   = this._u(puck, now);
      puck.to     = k * QueueLineFigure.SPACING;
      puck.travel = HL.tween(0, QueueLineFigure.SLIDE);
      HL.tset(puck.travel, 1, now, k * QueueLineFigure.WAVE);
    });

    if (this.pucks.length < this._filled(this.data)) this._spawn(now, false);
    this._mark();
    this._retarget(now);
  }

  _filled(data) {
    const pending = Math.round(data.pending);
    if (pending <= 0) return 0;
    return Math.min(QueueLineFigure.SLOTS, Math.ceil((pending * QueueLineFigure.SLOTS) / QueueLineFigure.FULL));
  }

  _draw(puck, now) {
    let pose;
    if (puck.exit !== null) {
      pose = this._exitPose(puck, now);
      if (pose.done) return this._forget(puck);
      if (pose.onGpu && !puck.kicked) {
        puck.kicked = true;
        this.kicked = now;
      }
    } else {
      const [x, y] = this._at(this._u(puck, now));
      const grow   = HL.tval(puck.grow, now);
      if (grow <= 0.001 && HL.tdone(puck.grow, now) && this.leaving.includes(puck)) return this._forget(puck);
      pose = { x, y, z: HL.tval(puck.tw, now), h: QueueLineFigure.PUCK_H * grow, onGpu: false };
    }

    puck.depth = pose.onGpu ? this.gpu.depth + 1 : pose.x + pose.y;
    const key  = `${pose.x}|${pose.y}|${pose.z}|${pose.h}|${puck.mine}`;
    if (key === puck.drawn) return;
    puck.drawn = key;

    const [ring, inner] = this.puckRing;
    const at            = this._shifted(pose.x, pose.y, 0);
    HL.put(puck.el, pose.h < 0.2 ? { sil: "", crease: "" } : HL.prism(at, this.front, ring, inner, pose.z, pose.z + pose.h));
    if (puck.dot) {
      puck.dot.style.visibility = pose.h < 0.6 ? "hidden" : "";
      HL.place(puck.dot, at(0, 0, pose.z + pose.h));
    }
  }

  _u(puck, now) {
    return HL.lerp(puck.from, puck.to, HL.tval(puck.travel, now));
  }

  _exitPose(puck, now) {
    const e        = HL.clamp((now - puck.exit) / QueueLineFigure.EXIT, 0, 1);
    const ease     = (s) => s * s * (3 - 2 * s);
    const top      = this._gpuLift(now) + QueueLineFigure.GPU_H;
    const near     = QueueLineFigure.GPU[2] + QueueLineFigure.PUCK + 0.6;
    const [sx, sy] = QueueLineFigure.SOCKET;
    if (e < 0.5) return { x: HL.lerp(QueueLineFigure.HEAD, near, ease(e / 0.5)), y: sy, z: 0, h: QueueLineFigure.PUCK_H, onGpu: false, done: false };
    if (e < 0.75) {
      const s = ease((e - 0.5) / 0.25);
      return { x: HL.lerp(near, sx, s), y: sy, z: HL.lerp(0, top, s) + QueueLineFigure.HOP * Math.sin(Math.PI * s), h: QueueLineFigure.PUCK_H, onGpu: true, done: false };
    }
    const s = ease((e - 0.75) / 0.25);
    return { x: sx, y: sy, z: top, h: QueueLineFigure.PUCK_H * (1 - s), onGpu: true, done: e >= 1 };
  }

  _forget(puck) {
    puck.group.remove();
    this.leaving = this.leaving.filter((other) => other !== puck);
  }

  _drawGpu(dt, now) {
    const gpu         = this.gpu;
    const lift        = this._gpuLift(now);
    const top         = lift + QueueLineFigure.GPU_H;
    const [fx, fy, r] = QueueLineFigure.FAN;
    const [sx, sy]    = QueueLineFigure.SOCKET;
    const [idle, hot] = QueueLineFigure.SPIN;
    const boost       = Math.exp(-(now - this.kicked) / 1400);
    this.fanAngle     = (this.fanAngle + (idle + (hot - idle) * boost) * dt) % (Math.PI * 2);

    if (gpu.drawn !== lift) {
      gpu.drawn = lift;
      HL.put(gpu.el, HL.prism(this.P, this.front, gpu.ring, gpu.inner, lift, top));
      gpu.rims.setAttribute("d", HL.poly(HL.ringAt(this._shifted(fx, fy, 0), HL.circ(r, 32), top)) + HL.poly(HL.ringAt(this._shifted(sx, sy, 0), HL.circ(QueueLineFigure.PUCK + 0.5, 32), top)));
      HL.place(gpu.led, this.P(QueueLineFigure.GPU[0] + 2.4, QueueLineFigure.GPU[3] - 2.4, top));
    }

    const blades = [];
    for (let b = 0; b < 3; b++) {
      const a = this.fanAngle + (b * 2 * Math.PI) / 3;
      blades.push(HL.seg(this.P(fx, fy, top), this.P(fx + r * 0.82 * Math.cos(a), fy + r * 0.82 * Math.sin(a), top)));
    }
    gpu.blades.setAttribute("d", blades.join(""));
    gpu.led.setAttribute("class", boost > 0.35 ? "dot" : "dot m");
  }

  _gpuLift(now) {
    return HL.tval(this.gpu.tw, now);
  }

  _order() {
    const items = [...this.statics, this.gpu, ...this.pucks, ...this.leaving].sort((a, b) => a.depth - b.depth);
    const key   = items.map((item) => item.id).join(",");
    if (key === this.orderKey) return;
    this.orderKey = key;
    for (const item of items) this.scene.appendChild(item.group);
  }

  _move(p) {
    const gpu    = this.P(QueueLineFigure.FAN[0], QueueLineFigure.FAN[1], QueueLineFigure.GPU_H);
    let best     = "gpu";
    let distance = Math.hypot(gpu[0] - p[0], gpu[1] - p[1]);
    this.pucks.forEach((_, k) => {
      const [x, y] = this._at(k * QueueLineFigure.SPACING);
      const q      = this.P(x, y, QueueLineFigure.PUCK_H);
      const d      = Math.hypot(q[0] - p[0], q[1] - p[1]);
      if (d < distance) {
        distance = d;
        best     = k;
      }
    });
    this._choose(best);
  }

  _at(u) {
    let left   = Math.max(0, u);
    const last = this.path[this.path.length - 1];
    for (const part of this.path) {
      if (left > part.length && part !== last) {
        left -= part.length;
        continue;
      }
      const t = Math.min(1, left / part.length);
      if (part.kind === "line") return [HL.lerp(part.a[0], part.b[0], t), HL.lerp(part.a[1], part.b[1], t)];
      const angle = HL.lerp(part.from, part.to, t);
      return [part.c[0] + QueueLineFigure.TURN * Math.cos(angle), part.c[1] + QueueLineFigure.TURN * Math.sin(angle)];
    }
    throw new Error("queueline figure: empty path");
  }

  _retarget(now) {
    const anchor = this.chosen === null ? (this.pucks.length ? 0 : "gpu") : this.chosen;
    const lift   = this.chosen === null ? this.amount * QueueLineFigure.REST : this.amount;
    this.pucks.forEach((puck, k) => {
      HL.tset(puck.tw, k === anchor ? lift : 0, now, 0);
      puck.el.sil.classList.toggle("hi", k === anchor);
    });
    HL.tset(this.gpu.tw, anchor === "gpu" ? lift : 0, now, 0);
    this.gpu.el.sil.classList.toggle("hi", anchor === "gpu");
    this.loop.wake();
  }
}

class TomosarFigures {
  static entry(Figure, label) {
    return { mount: (els, value) => new Figure(els, value), label, range: Figure.RANGE };
  }

  static CATALOG = {
    voxels:     TomosarFigures.entry(VoxelColumnFigure, "A forest-plot column cut into height bins, wide at the ground and again in the canopy. The pointer's height picks a bin and it slides out of the column."),
    covariance: TomosarFigures.entry(CovarianceFigure, "A six by six covariance matrix as a field of tiles, tallest on the diagonal. The tile under the pointer rises together with its mirror across the diagonal."),
    power:      TomosarFigures.entry(PowerCupFigure, "A predicted profile as a column of discs beside a measuring glass marked with the reference total. The pointer's height picks a bin: the bins below it have drained into the glass and the picked one is pouring, so the fill is the power integrated so far."),
    moments:    TomosarFigures.entry(MomentsBeamFigure, "A profile laid along a beam as bars of power, resting on a fulcrum. The fulcrum follows the pointer and the beam tips toward the heavier side, settling level only at the centroid; two marks span one spread either side of it."),
    coherence:  TomosarFigures.entry(CoherencePhasorFigure, "A profile column with one phasor spoke per bin, each turned by its steering phase, beside one dial per pass whose needle is the coherence the profile re-synthesises and whose dashed needle is the reference. The pointer picks a pass: its dial lifts and the spokes fan out to that wavenumber, the wider the fan the shorter the needle."),
    capon:      TomosarFigures.entry(CaponCycleFigure, "The Capon cycle: the predicted profile, the covariance it synthesises with its loaded diagonal, and the re-estimated spectrum filling in inside the dashed reference. The pointer's height steers the beamformer up the column and every bin below it is estimated."),
    folds:      TomosarFigures.entry(CvFoldsFigure, "A drum cut into five cross-validation folds, each numbered with dots. The pointer's angle picks a fold and it slides out as the held-out one."),
    ablation:   TomosarFigures.entry(AblationTowerFigure, "A stacking-block tower of nine levels. The pointer's height picks a level and its middle block slides out, the way an ablation removes one component."),
    slices:     TomosarFigures.entry(SliceLoafFigure, "A tomogram block cut into eleven slices whose tops follow the canopy. The pointer picks a slice and it slides out of the block with its neighbours."),
    normalize:  TomosarFigures.entry(NormalizationFigure, "Twelve bars of very uneven raw amplitude before a plate marked with the interquartile band. Under the pointer the bars shrink to their log-scaled values."),
    slots:      TomosarFigures.entry(GaussianSlotsFigure, "Three Gaussian slots, each a tray of fins tracing one component; the middle slot has collapsed flat. The pointer picks a slot and its component rises."),
    tracks:     TomosarFigures.entry(FlightTracksFigure, "Six flight tracks stacked above a ground scene, an aircraft riding one with its line of sight to the ground. The pointer picks the track and moves along it."),
    tree:       TomosarFigures.entry(ExpressionTreeFigure, "An expression tree laid out on a board, operators as blocks and leaves as discs. The pointer picks a node and its whole subtree lifts off the board."),
    gpus:       TomosarFigures.entry(GpuShelfFigure, "Six GPU cards standing in a chassis, each with two fans and a status light. The pointer picks a card and it rises out of its slot."),
    guard:      TomosarFigures.entry(GpuGuardFigure, "A fenced yard of GPU card slots with a gate in the front fence. Another user's process, a puck, patrols the path outside and bumps the shut gate; during an intrusion the gate swings open and the puck rolls in to the card it invaded. The pointer picks a card and it rises."),
    canopy:     TomosarFigures.entry(CanopyPlotFigure, "A forest plot of twenty-five trees, one emergent above the rest. Under the pointer the crowns lift off their trunks, separating canopy from ground."),
    backbone:   TomosarFigures.entry(BackboneBenchFigure, "A test bench for the backbone zoo: an input patch, a socket and an output dish of Gaussian-slot pins on the front lane, and one cartridge per family on the shelf behind (a U block, a grid of tokens, a pyramid, a ridged slab, a single column). The pointer picks a cartridge, it hops into the socket, and the output pins settle to what it predicts."),
    repo:       TomosarFigures.entry(RepoCityFigure, "The repository as a city: one district per top-level folder, block heights following its size in lines. The pointer picks a district and its blocks rise."),
    landscape:  TomosarFigures.entry(LossLandscapeFigure, "A loss surface of pillars with a ball resting in its minimum. The ball follows the pointer across the surface and rolls back down to the minimum when it leaves."),
    surface:    TomosarFigures.entry(GaussianSurfaceFigure, "A surface drawn as ridgelines with two Gaussian bumps, one tall and narrow, one low and wide, riding a dashed straight track across it. The pointer pulls the nearer bump along the track and the other keeps its distance."),
    balance:    TomosarFigures.entry(BalanceFigure, "A balance weighing run A against run B, its pans numbered with dots. The pointer's side tips the beam, and the heavier pan lights."),
    profileae:  TomosarFigures.entry(ProfileAutoencoderFigure, "A profile autoencoder as a stack of round plates, narrowing to the latent and widening again. The pointer's height picks a layer and the stack opens above it."),
    imageae:    TomosarFigures.entry(ImageAutoencoderFigure, "An image autoencoder as a stack of square plates, narrowing to the latent and widening again. The pointer's height picks a layer and the stack opens above it."),
    embed:      TomosarFigures.entry(JepaEmbeddingFigure, "JEPA in this project: the backbone on the left reads an image tile and grows a predicted embedding comb; the frozen profile autoencoder on the right encodes the true profile into the target comb. The pointer runs training from left to right and the predicted comb settles onto the target."),
    podium:     TomosarFigures.entry(PodiumFigure, "A podium of five ranks, each step numbered with dots. The pointer picks a step and it rises with its neighbours."),
    tiles:      TomosarFigures.entry(MetricTilesFigure, "A metric map as a field of tiles with a hot spot and a fold seam. The pointer picks a tile and the region around it rises."),
    transect:   TomosarFigures.entry(TransectFigure, "Nine vertical profiles standing along a dashed transect line, each a column of discs tracing ground and canopy. The pointer picks a profile and it slides out of the line."),
    film:       TomosarFigures.entry(FilmStripFigure, "Inference stamps as frames on a dated rail, each holding a profile that sharpens from the first stamp to the latest. The pointer picks a frame and it rises."),
    tray:       TomosarFigures.entry(ReportTrayFigure, "A loose stack of printed plots on a tray. The pointer's height picks a sheet and it slides out of the stack."),
    unrolled:   TomosarFigures.entry(UnrolledFigure, "Seven unrolled stages in a row. The stages run so far stand at heights that climb and level off like a convergence curve, the rest wait as stubs. The pointer picks how far the unrolling has run and the stages grow or fall back in turn."),
    jepa:       TomosarFigures.entry(JepaMasksFigure, "A board of image patches with a few masked flat. A two by two target block follows the pointer and lifts out of its context."),
    shelf:      TomosarFigures.entry(CheckpointShelfFigure, "Checkpoints standing on a shelf as cartridges, the best one pulled forward. The pointer picks a cartridge and it slides out."),
    dial:       TomosarFigures.entry(LrDialFigure, "A learning-rate dial with a detent at each decade. The pointer's angle turns the knob and it settles on the nearest detent."),
    aperture:   TomosarFigures.entry(ApertureFigure, "An aircraft on a straight track above a scene with one point target, its beam outlined on the ground. The stretch of track that sees the target lights while the aircraft passes over it."),
    slc:        TomosarFigures.entry(SlcStackFigure, "A stack of eight SLC images, each carrying fringes that grow denser with its baseline. The pointer's height picks an image and the stack opens above it."),
    threshold:  TomosarFigures.entry(ThresholdFigure, "A field of pixel activity pillars cut by a dashed threshold plane. The pointer's height moves the plane and the part of each pillar above it lights."),
    sorted:     TomosarFigures.entry(SortedSlotsFigure, "Four label slots on a rail, each a stem with a disc at its height and numbered with dots. Toward one side they sit in network order, toward the other they hop into height order."),
    pull:       TomosarFigures.entry(DataPullFigure, "Two belts between the cluster rack and the local machine, crates going up on one and coming back on the other. The pointer picks a lane and it runs faster."),
    scheduler:  TomosarFigures.entry(SchedulerFigure, "A cluster rack with four node sockets on its top and a staircase of steps leading up to it. Running jobs stand as crates in the sockets, waiting jobs stand on the steps, and the waiting job nearest the front climbs toward the rack. The pointer picks the rack or a step and what stands there lifts."),
    pylons:     TomosarFigures.entry(LrzPylonsFigure, "A line of pylons, one per LRZ service, strung together by two cables with a lamp on every top. A disrupted service jumps in place and lights its lamp, and the cables beside it hang slack. A bright packet runs along the cables from pylon to pylon, out on the front cable and back on the rear one, and stops at a pylon that is down. The pointer picks a pylon and it grows taller."),
    sampler:    TomosarFigures.entry(PatchSamplerFigure, "A scene of tiles carrying interferometric fringes, with a batch of patches stacked on a tray beside it. The pointer picks a tile and that patch lifts out of the scene, leaving its hole behind."),
    feed:       TomosarFigures.entry(FeedLineFigure, "A DataLoader feeding a GPU: one belt per worker carries crates to a rail, a prefetch tray holds the batches waiting, and the GPU at the end draws them in while its fans spin with its load. The pointer picks a worker, the tray or the GPU and it lifts."),
    field:      TomosarFigures.entry(ReceptiveFieldFigure, "A tiled input under a lamp on a pole with one collar per layer. The pointer picks a layer, the lamp rises to it, and the patch of input it lights widens: the receptive field of that layer."),
    watchdog:   TomosarFigures.entry(WatchdogFigure, "A camera on a pole used as a searchlight, sweeping its beam around a ring of four targets for CPU, load, RAM and disk, each a bullseye puck standing taller the nearer its reading is to the alert limit. The sweep slows over each target and the target in the light takes the bright edge; on a target with an active alert the beam stops for a few seconds, turns solid and bright, then sweeps on. The pointer picks a target and the camera turns to it."),
    notify:     TomosarFigures.entry(NotifyFigure, "A server and a phone in its dock. An envelope arcs from the server into the phone and a new notification card slides in at the top of its screen, pushing the older ones down. The pointer picks the server or the phone and it lifts."),
    nuke:       TomosarFigures.entry(NukeFigure, "A nuclear charge on a plinth: a drum with hazard bands and a radiation trefoil on its lid and a plunger detonator wired to it. When the nuke fires the plunger goes down, a pulse runs along the wire, a mushroom cloud rises from the drum and a shockwave ring sweeps the plinth; once the dust settles the cloud sinks and the plunger rises. The pointer picks the detonator or the drum and it lifts."),
    cores:      TomosarFigures.entry(CoresFigure, "The processor's cores as a field of pillars on a plinth, each standing as tall as that core is busy, with a dashed plane at the height where a core counts as dispatched; the pillars that reach above it take a bright rim. The pointer picks a core and it lifts."),
    gpuwire:    TomosarFigures.entry(GpuWireFigure, "A graphics card standing in its slot, fed by a power cable that drops in from above. Its fans spin faster the busier the GPU is, and packets of energy run along the cable the more power it draws, each one flashing the card's light as it lands. The pointer lifts the card out of its slot."),
    guillotine: TomosarFigures.entry(GuillotineFigure, "A server tower standing under a guillotine. The blade climbs its frame, hangs for a moment and drops, and the tower splits in two halves that slide apart before closing up again for the next stroke; once the front end has been killed the halves stay apart. The pointer lifts the server."),
    chips:      TomosarFigures.entry(ChipsFigure, "A round table with a pot of poker chips in the middle and three croupier rakes reaching in from the edge, one per user with yours marked bright. Each rake slides in, drags chips to its side and lets them go, and the chips toss themselves back into the pot one by one, flipping like coins. The more a user stalls the machine, the more chips its rake takes; during an alarm your rake turns bright. The pointer picks a rake and it lifts off the felt."),
    calendar:   TomosarFigures.entry(DeskCalendarFigure, "A desk calendar of the last thirty days, one page per day, each page carrying that day's six four-hour slots as bars: your share of the GPUs bright, everyone else's after it, the idle rest an empty track. The pages turn slowly a day at a time, rest on today and riffle back; the pointer's position across the calendar picks a day."),
    bays:       TomosarFigures.entry(GpuBaysFigure, "The cluster's GPUs as a board of bays, four nodes of four. An allocated bay holds a card with a spinning fan, a free bay is an empty socket, and a bay on a drained or down node is shut under a crossed lid; every few seconds one card lifts out of its bay and another drops into a free one. The pointer picks a bay and it rises."),
    cluster:    TomosarFigures.entry(ClusterAisleFigure, "Three GPU racks in an aisle, each holding four node drawers with one light per A100: your jobs bright, other users' jobs dim, free GPUs dark, drained nodes parked dark. Jobs end and start across the drawers while the fans on the rack tops spin with the cluster's load; the pointer picks a drawer and it slides out to show its four GPUs."),
    hourglass:  TomosarFigures.entry(HourglassFigure, "An hourglass on a round plinth, its sand running from the upper bulb into a pile in the lower one; when the top runs dry it turns over and starts again. The longer jobs wait in the queue, the slower the sand runs, and the pointer lifts the glass off its stand."),
    queueline:  TomosarFigures.entry(QueueLineFigure, "Jobs waiting for a GPU as pucks in a roped serpentine queue, your own marked with a bright dot. Every few seconds the head of the line hops into the GPU at the exit and the rest step forward one place; the pointer picks a puck and it lifts."),
  };
}
