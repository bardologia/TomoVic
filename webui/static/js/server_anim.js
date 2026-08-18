"use strict";

class ServerScene extends CanvasBase {

  constructor(canvas) {
    super(canvas);
    this.t     = 0;
    this.frame = 0;
    this.ink   = "200, 214, 224";
    this.blue  = "111, 155, 255";
    this.teal  = "45, 212, 191";
    this.amber = "251, 191, 36";
    this.red   = "248, 113, 113";

    this.load       = 0.15;
    this.loadTarget = 0.15;
    this.alert      = 0;
    this.fed        = false;
    this.waveMax    = 90;
    this.barsMax    = 14;
    this.wave       = [];
    this.packets    = [];
    this.units      = ["cpu", "ram", "gpu"].map((label, i) => this._makeUnit(label, label, 0.12 + 0.08 * i));

    if (REDUCED_MOTION) {
      this.t = 3;
      this._draw();
    } else {
      this._loop = this._loop.bind(this);
      requestAnimationFrame(this._loop);
    }
  }

  onResize() {
    if (REDUCED_MOTION && this.units) this._draw();
  }

  _makeUnit(key, label, v) {
    return { key, label, v, target: v, bars: Array.from({ length: this.barsMax }, () => v), fanA: Math.random() * 6, alert: 0, hot: false, mine: false, others: false };
  }

  feed(sys) {
    const cpu    = sys.cpu || {};
    const mem    = sys.mem || {};
    const gpus   = sys.gpus || [];
    const alerts = sys.alerts || {};

    const levels = {};
    (alerts.active || []).forEach((a) => {
      const unit  = a.kind === "ram" || a.kind === "ram_kill" || a.kind === "ram_foreign" ? "ram" : "cpu";
      const lvl   = a.level === "danger" ? 2 : 1;
      levels[unit] = Math.max(levels[unit] || 0, lvl);
    });

    const defs = [
      { key: "cpu", label: "cpu", target: (cpu.total || 0) / 100, alert: levels.cpu || 0, hot: false },
      { key: "ram", label: "ram", target: mem.total ? (mem.total - mem.available) / mem.total : 0, alert: levels.ram || 0, hot: false },
    ];
    gpus.forEach((g, i) => {
      const lvl = g.temp >= 85 ? 2 : g.temp >= 70 ? 1 : 0;
      defs.push({ key: `gpu${i}`, label: `gpu${g.index != null ? g.index : i}`, target: (g.util || 0) / 100, alert: lvl, hot: g.temp >= 70, mine: !!g.mine, others: !!g.others, stale: !!g.stale });
    });

    if (!this.fed || defs.length !== this.units.length) {
      const old  = new Map(this.units.map((u) => [u.key, u]));
      this.units = defs.map((d) => old.get(d.key) || this._makeUnit(d.key, d.label, d.target));
    }
    defs.forEach((d, i) => {
      const u  = this.units[i];
      u.label  = d.label;
      u.target = Math.max(0, Math.min(1, d.target));
      u.alert  = d.alert;
      u.hot    = d.hot;
      u.mine   = !!d.mine;
      u.others = !!d.others;
      u.stale  = !!d.stale;
    });

    this.loadTarget = Math.max(0, Math.min(1, (cpu.total || 0) / 100));
    this.alert      = Math.max(0, ...this.units.map((u) => u.alert));
    this.othersOn   = this.units.some((u) => u.others);
    this.mineOn     = this.units.some((u) => u.mine);
    this.staleOn    = this.units.some((u) => u.stale);
    this.fed        = true;

    if (REDUCED_MOTION) {
      this.load = this.loadTarget;
      this.units.forEach((u) => { u.v = u.target; u.bars = u.bars.map(() => u.target); });
      this.wave.push(this.loadTarget);
      if (this.wave.length > this.waveMax) this.wave.shift();
      this._draw();
    }
  }

  _tint(level) {
    return level >= 2 ? this.red : level === 1 ? this.amber : this.blue;
  }

  _draw() {
    if (this.w < 60 || this.h < 60 || this.canvas.offsetParent === null) return;
    const ctx = this.ctx;
    const w   = this.w;
    const h   = this.h;
    ctx.clearRect(0, 0, w, h);

    const rackX = w * 0.42;
    const rackW = w * 0.55;
    this._rack(ctx, rackX, 10, rackW, h - 20);
    this._wave(ctx, 6, 8, rackX - 22, h * 0.52);
    this._lanes(ctx, 6, rackX - 14, h);
  }

  _rack(ctx, rx, ry, rw, rh) {
    const occ   = this.othersOn ? this.red : this.mineOn ? this.blue : this.staleOn ? this.amber : null;
    const tint  = this.alert ? this._tint(this.alert) : occ || this._tint(this.alert);
    const pulse = this.alert ? 0.3 * (0.5 + 0.5 * Math.sin(this.t * (this.alert >= 2 ? 9 : 4))) : 0;

    ctx.strokeStyle = this.alert || occ ? `rgba(${tint}, ${0.4 + pulse})` : `rgba(${this.ink}, 0.45)`;
    ctx.lineWidth   = 1.2;
    this._round(ctx, rx - 7, ry - 7, rw + 14, rh + 14, 5);
    ctx.stroke();

    const gap = 5;
    const uh  = (rh - gap * (this.units.length - 1)) / this.units.length;
    this.units.forEach((u, i) => this._unit(ctx, u, rx, ry + i * (uh + gap), rw, uh));
  }

  _unit(ctx, u, ux, uy, uw, uh) {
    const occ  = u.others ? this.red : u.mine ? this.blue : u.stale ? this.amber : null;
    const tint = u.alert ? this._tint(u.alert) : occ || this._tint(u.alert);
    const fg   = occ ? "255, 255, 255" : this.ink;

    if (occ) {
      ctx.fillStyle = `rgba(${occ}, 0.9)`;
      this._round(ctx, ux, uy, uw, uh, 3);
      ctx.fill();
    }

    ctx.strokeStyle = u.alert || occ ? `rgba(${tint}, 0.5)` : `rgba(${this.ink}, 0.35)`;
    ctx.lineWidth   = 1;
    this._round(ctx, ux, uy, uw, uh, 3);
    ctx.stroke();

    const cy = uy + uh / 2;

    let led = Math.sin(this.t * (2 + u.v * 9) + u.fanA * 3) > -0.3 ? 0.9 : 0.3;
    if (u.alert === 1) led = 0.9;
    if (u.alert >= 2) led = 0.5 + 0.5 * Math.sin(this.t * 10);
    ctx.beginPath();
    ctx.arc(ux + 10, cy, 2.6, 0, Math.PI * 2);
    ctx.fillStyle = occ ? `rgba(${fg}, ${led})` : `rgba(${tint}, ${led})`;
    ctx.fill();

    ctx.font         = "600 8.5px ui-monospace, SFMono-Regular, Menlo, monospace";
    ctx.textBaseline = "middle";
    ctx.textAlign    = "left";
    ctx.fillStyle    = `rgba(${fg}, ${occ ? 0.9 : 0.55})`;
    ctx.fillText(u.label, ux + 19, cy + 0.5);

    const bx0 = ux + 52;
    const bx1 = ux + uw - 54;
    const bw  = (bx1 - bx0) / u.bars.length;
    u.bars.forEach((v, k) => {
      const bh = Math.max(1.5, v * (uh - 9));
      ctx.fillStyle = occ ? `rgba(${fg}, ${0.3 + 0.5 * v})` : `rgba(${u.alert ? tint : this.blue}, ${0.15 + 0.55 * v})`;
      ctx.fillRect(bx0 + k * bw, uy + uh - 4.5 - bh, bw - 2, bh);
    });

    ctx.textAlign = "right";
    ctx.fillStyle = `rgba(${fg}, ${occ ? 0.95 : 0.7})`;
    ctx.fillText(`${Math.round(u.v * 100)}%`, ux + uw - 29, cy + 0.5);

    const fx = ux + uw - 15;
    const fr = Math.min(7.5, uh * 0.3);
    ctx.strokeStyle = occ ? `rgba(${fg}, 0.7)` : u.hot ? `rgba(${this.red}, 0.55)` : `rgba(${this.ink}, 0.4)`;
    ctx.beginPath();
    ctx.arc(fx, cy, fr, 0, Math.PI * 2);
    ctx.stroke();
    for (let s = 0; s < 3; s++) {
      const a = u.fanA + (s * Math.PI * 2) / 3;
      ctx.beginPath();
      ctx.moveTo(fx, cy);
      ctx.lineTo(fx + Math.cos(a) * fr * 0.85, cy + Math.sin(a) * fr * 0.85);
      ctx.stroke();
    }
  }

  _wave(ctx, x0, y0, x1, y1) {
    const tint = this._tint(this.alert);

    ctx.font         = "600 8.5px ui-monospace, SFMono-Regular, Menlo, monospace";
    ctx.textBaseline = "top";
    ctx.textAlign    = "left";
    ctx.fillStyle    = `rgba(${this.ink}, 0.45)`;
    ctx.fillText("cpu load", x0 + 2, y0);
    ctx.textAlign = "right";
    ctx.fillStyle = this.alert ? `rgba(${tint}, 0.85)` : `rgba(${this.ink}, 0.7)`;
    ctx.fillText(`${Math.round(this.load * 100)}%`, x1 - 2, y0);

    const gy0 = y0 + 14;
    const gh  = y1 - gy0;

    ctx.strokeStyle = `rgba(${this.ink}, 0.10)`;
    ctx.lineWidth   = 1;
    [0, 0.5, 1].forEach((f) => {
      const y = Math.round(gy0 + gh * f) + 0.5;
      ctx.beginPath();
      ctx.moveTo(x0, y);
      ctx.lineTo(x1, y);
      ctx.stroke();
    });

    const d = this.wave;
    if (d.length < 2) return;

    const step = (x1 - x0) / (this.waveMax - 1);
    const sx   = x1 - (d.length - 1) * step;
    ctx.beginPath();
    d.forEach((v, i) => {
      const x = sx + i * step;
      const y = gy0 + gh - v * gh;
      if (i === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    });
    ctx.strokeStyle = `rgba(${this.alert ? tint : this.blue}, 0.85)`;
    ctx.lineWidth   = 1.4;
    ctx.stroke();
    ctx.lineTo(x1, gy0 + gh);
    ctx.lineTo(sx, gy0 + gh);
    ctx.closePath();
    ctx.fillStyle = `rgba(${this.alert ? tint : this.blue}, 0.10)`;
    ctx.fill();
  }

  _lanes(ctx, x0, x1, h) {
    const lanes = [h * 0.72, h * 0.87];

    ctx.save();
    ctx.setLineDash([2, 5]);
    ctx.strokeStyle = `rgba(${this.ink}, 0.20)`;
    ctx.lineWidth   = 1;
    lanes.forEach((y) => {
      ctx.beginPath();
      ctx.moveTo(x0, y);
      ctx.lineTo(x1, y);
      ctx.stroke();
    });
    ctx.restore();

    this.packets.forEach((pk) => {
      const span = x1 - x0 - 6;
      const x    = pk.lane === 0 ? x0 + 3 + pk.p * span : x1 - 3 - pk.p * span;
      const y    = lanes[pk.lane];
      const tint = pk.lane === 0 ? this.blue : this.teal;
      const edge = Math.min(1, Math.min(pk.p, 1 - pk.p) * 8);

      ctx.beginPath();
      ctx.arc(x, y, 2.1, 0, Math.PI * 2);
      ctx.fillStyle = `rgba(${tint}, ${0.85 * edge})`;
      ctx.fill();
    });
  }

  _round(ctx, x, y, w, h, r) {
    ctx.beginPath();
    ctx.moveTo(x + r, y);
    ctx.arcTo(x + w, y, x + w, y + h, r);
    ctx.arcTo(x + w, y + h, x, y + h, r);
    ctx.arcTo(x, y + h, x, y, r);
    ctx.arcTo(x, y, x + w, y, r);
    ctx.closePath();
  }

  _loop() {
    this.t     += 0.016;
    this.frame += 1;

    this.load += (this.loadTarget - this.load) * 0.05;
    this.units.forEach((u) => {
      u.v    += (u.target - u.v) * 0.06;
      u.fanA += 0.016 * (1.5 + u.v * 14 + (u.hot ? 5 : 0));
    });

    if (this.frame % 3 === 0) {
      this.wave.push(Math.max(0, Math.min(1, this.load + (Math.random() - 0.5) * 0.05)));
      if (this.wave.length > this.waveMax) this.wave.shift();
    }
    if (this.frame % 7 === 0) {
      this.units.forEach((u) => {
        u.bars.push(Math.max(0.04, Math.min(1, u.v + (Math.random() - 0.5) * 0.25)));
        if (u.bars.length > this.barsMax) u.bars.shift();
      });
    }

    if (this.packets.length < 22 && Math.random() < 0.02 + this.load * 0.12) {
      this.packets.push({ p: 0, lane: Math.random() < 0.6 ? 0 : 1, speed: 0.004 + this.load * 0.01 + Math.random() * 0.003 });
    }
    this.packets = this.packets.filter((pk) => (pk.p += pk.speed) <= 1);

    requestAnimationFrame(this._loop);
    this._draw();
  }
}

window.ServerScene = ServerScene;
