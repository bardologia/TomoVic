"use strict";

class AnimatedGauge extends CanvasBase {

  constructor(canvas, opts, tuning) {
    super(canvas);
    this.min    = opts.min != null ? opts.min : tuning.min;
    this.max    = opts.max != null ? opts.max : tuning.max;
    this.ease   = tuning.ease;
    this.settle = tuning.settle;
    this.v      = this.min;
    this.t      = this.min;
    this.peak   = this.min;
    this.peakAt = 0;
    this._raf   = null;
    this._tick  = this._tick.bind(this);
  }

  onResize() {
    if (this._ready) this._draw();
  }

  range(max) {
    if (max != null && max > this.min && max !== this.max) this.max = max;
  }

  set(value) {
    const now = performance.now();
    const v   = Math.max(this.min, Math.min(this.max, value == null ? this.min : value));

    if (v >= this.peak || now - this.peakAt > 60000) { this.peak = v; this.peakAt = now; }
    this.t = v;

    if (REDUCED_MOTION) { this.v = v; this._draw(); return; }
    if (this._raf == null) this._raf = requestAnimationFrame(this._tick);
  }

  _tick() {
    this.v += (this.t - this.v) * this.ease;
    if (Math.abs(this.t - this.v) < (this.max - this.min) * this.settle) {
      this.v    = this.t;
      this._raf = null;
      this._draw();
      return;
    }
    this._draw();
    this._raf = requestAnimationFrame(this._tick);
  }
}

class DialGauge extends AnimatedGauge {

  constructor(canvas, opts) {
    super(canvas, opts, { min: 0, max: 100, ease: 0.14, settle: 0.0005 });
    this.label  = opts.label || "";
    this.unit   = opts.unit || "";
    this.color  = opts.color || "111, 155, 255";
    this.zones  = opts.zones || [];
    this.majors = opts.majors != null ? opts.majors : 5;
    this.minors = opts.minors != null ? opts.minors : 4;
    this.digits = opts.digits != null ? opts.digits : 0;
    this.big    = !!opts.big;
    this.a0     = -Math.PI * 1.2;
    this.a1     = Math.PI * 0.2;
    this._ready = true;
    this._draw();
  }

  _angle(v) {
    return this.a0 + ((v - this.min) / (this.max - this.min)) * (this.a1 - this.a0);
  }

  _arc(ctx, cx, cy, r, from, to, color, lw, glow) {
    ctx.beginPath();
    ctx.arc(cx, cy, r, from, to);
    ctx.strokeStyle = color;
    ctx.lineWidth   = lw;
    if (glow) { ctx.shadowColor = glow; ctx.shadowBlur = 8; }
    ctx.stroke();
    ctx.shadowBlur = 0;
  }

  _draw() {
    if (this.w < 30 || this.h < 30) return;
    const ctx = this.ctx;
    const w   = this.w;
    const h   = this.h;
    ctx.clearRect(0, 0, w, h);

    const r  = Math.min((w - 14) / 2, (h - 12) / 1.60);
    const cx = w / 2;
    const cy = 7 + r;
    const lw = Math.max(2.5, r * 0.075);

    this._arc(ctx, cx, cy, r, this.a0, this.a1, "rgba(255, 255, 255, 0.08)", lw, null);
    this.zones.forEach((z) => {
      this._arc(ctx, cx, cy, r + lw * 0.85, this._angle(z.from), this._angle(z.to), `rgba(${z.color}, 0.75)`, Math.max(1.5, lw * 0.38), null);
    });
    if (this.v > this.min) {
      this._arc(ctx, cx, cy, r, this.a0, this._angle(this.v), `rgba(${this.color}, 0.9)`, lw, `rgba(${this.color}, 0.5)`);
    }

    const steps = this.majors * this.minors;
    for (let i = 0; i <= steps; i++) {
      const major = i % this.minors === 0;
      const a     = this.a0 + (i / steps) * (this.a1 - this.a0);
      const r0    = r * (major ? 0.74 : 0.80);
      const r1    = r * 0.88;
      ctx.beginPath();
      ctx.moveTo(cx + Math.cos(a) * r0, cy + Math.sin(a) * r0);
      ctx.lineTo(cx + Math.cos(a) * r1, cy + Math.sin(a) * r1);
      ctx.strokeStyle = major ? "rgba(220, 235, 245, 0.55)" : "rgba(220, 235, 245, 0.22)";
      ctx.lineWidth   = major ? 1.4 : 1;
      ctx.stroke();
    }

    ctx.font         = `500 ${this.big ? 9 : 8}px 'JetBrains Mono', ui-monospace, monospace`;
    ctx.textAlign    = "center";
    ctx.textBaseline = "middle";
    ctx.fillStyle    = "rgba(220, 235, 245, 0.45)";
    for (let m = 0; m <= this.majors; m++) {
      const val = this.min + (m / this.majors) * (this.max - this.min);
      const a   = this._angle(val);
      ctx.fillText(String(Math.round(val)), cx + Math.cos(a) * r * 0.60, cy + Math.sin(a) * r * 0.60);
    }

    if (this.peak > this.v + (this.max - this.min) * 0.01) {
      const pa = this._angle(this.peak);
      ctx.beginPath();
      ctx.moveTo(cx + Math.cos(pa) * r * 0.90, cy + Math.sin(pa) * r * 0.90);
      ctx.lineTo(cx + Math.cos(pa) * r * 1.00, cy + Math.sin(pa) * r * 1.00);
      ctx.strokeStyle = "rgba(251, 191, 36, 0.9)";
      ctx.lineWidth   = 1.6;
      ctx.stroke();
    }

    const na = this._angle(this.v);
    ctx.beginPath();
    ctx.moveTo(cx - Math.cos(na) * r * 0.16, cy - Math.sin(na) * r * 0.16);
    ctx.lineTo(cx + Math.cos(na) * r * 0.72, cy + Math.sin(na) * r * 0.72);
    ctx.strokeStyle = "rgba(230, 240, 246, 0.95)";
    ctx.lineWidth   = this.big ? 1.9 : 1.5;
    ctx.shadowColor = `rgba(${this.color}, 0.7)`;
    ctx.shadowBlur  = 7;
    ctx.stroke();
    ctx.shadowBlur = 0;

    ctx.beginPath();
    ctx.arc(cx, cy, Math.max(2.4, r * 0.07), 0, Math.PI * 2);
    ctx.fillStyle   = "#10161c";
    ctx.strokeStyle = "rgba(220, 235, 245, 0.7)";
    ctx.lineWidth   = 1.2;
    ctx.fill();
    ctx.stroke();

    const vy   = cy + r * (this.big ? 0.40 : 0.42);
    const vtxt = `${this.v.toFixed(this.digits)}${this.unit}`;
    ctx.font      = `600 ${this.big ? 19 : 12}px 'JetBrains Mono', ui-monospace, monospace`;
    ctx.fillStyle = "rgba(230, 240, 246, 0.95)";
    ctx.fillText(vtxt, cx, vy);

    ctx.font      = `600 ${this.big ? 8.5 : 7.5}px 'JetBrains Mono', ui-monospace, monospace`;
    ctx.fillStyle = "rgba(158, 173, 181, 0.85)";
    ctx.fillText(this.label, cx, this.big ? cy - r * 0.34 : vy + 12);
  }
}

class LinearMeter extends AnimatedGauge {

  constructor(canvas, opts) {
    super(canvas, opts, { min: 0, max: 100, ease: 0.14, settle: 0.0005 });
    this.label  = opts.label || "";
    this.unit   = opts.unit || "";
    this.color  = opts.color || "111, 155, 255";
    this.zones  = opts.zones || [];
    this.digits = opts.digits != null ? opts.digits : 0;
    this._ready = true;
    this._draw();
  }

  _x(v, x0, x1) {
    return x0 + ((v - this.min) / (this.max - this.min)) * (x1 - x0);
  }

  _draw() {
    if (this.w < 60 || this.h < 30) return;
    const ctx = this.ctx;
    const w   = this.w;
    const h   = this.h;
    ctx.clearRect(0, 0, w, h);

    const x0 = 2;
    const x1 = w - 2;
    const ty = h - 12;

    ctx.font         = "600 8px 'JetBrains Mono', ui-monospace, monospace";
    ctx.textAlign    = "left";
    ctx.textBaseline = "middle";
    ctx.fillStyle    = "rgba(158, 173, 181, 0.85)";
    ctx.fillText(this.label, x0, 7);

    ctx.font      = "600 12.5px 'JetBrains Mono', ui-monospace, monospace";
    ctx.textAlign = "right";
    ctx.fillStyle = "rgba(230, 240, 246, 0.95)";
    ctx.fillText(`${this.v.toFixed(this.digits)}${this.unit}`, x1, 8);

    this.zones.forEach((z) => {
      ctx.beginPath();
      ctx.moveTo(this._x(z.from, x0, x1), ty - 7);
      ctx.lineTo(this._x(z.to, x0, x1), ty - 7);
      ctx.strokeStyle = `rgba(${z.color}, 0.75)`;
      ctx.lineWidth   = 2.5;
      ctx.stroke();
    });

    ctx.beginPath();
    ctx.moveTo(x0, ty);
    ctx.lineTo(x1, ty);
    ctx.strokeStyle = "rgba(255, 255, 255, 0.14)";
    ctx.lineWidth   = 2;
    ctx.stroke();

    if (this.v > this.min) {
      ctx.beginPath();
      ctx.moveTo(x0, ty);
      ctx.lineTo(this._x(this.v, x0, x1), ty);
      ctx.strokeStyle = `rgba(${this.color}, 0.6)`;
      ctx.lineWidth   = 2;
      ctx.shadowColor = `rgba(${this.color}, 0.5)`;
      ctx.shadowBlur  = 6;
      ctx.stroke();
      ctx.shadowBlur = 0;
    }

    for (let i = 0; i <= 10; i++) {
      const tx    = x0 + (i / 10) * (x1 - x0);
      const major = i % 5 === 0;
      ctx.beginPath();
      ctx.moveTo(tx, ty + 3);
      ctx.lineTo(tx, ty + (major ? 9 : 6));
      ctx.strokeStyle = major ? "rgba(220, 235, 245, 0.45)" : "rgba(220, 235, 245, 0.22)";
      ctx.lineWidth   = 1;
      ctx.stroke();
    }

    if (this.peak > this.v + (this.max - this.min) * 0.01) {
      const px = this._x(this.peak, x0, x1);
      ctx.beginPath();
      ctx.moveTo(px, ty - 9);
      ctx.lineTo(px, ty - 3);
      ctx.strokeStyle = "rgba(251, 191, 36, 0.9)";
      ctx.lineWidth   = 1.6;
      ctx.stroke();
    }

    const nx = this._x(this.v, x0, x1);
    ctx.beginPath();
    ctx.moveTo(nx, ty - 9);
    ctx.lineTo(nx, ty + 4);
    ctx.strokeStyle = "rgba(230, 240, 246, 0.95)";
    ctx.lineWidth   = 1.8;
    ctx.shadowColor = `rgba(${this.color}, 0.7)`;
    ctx.shadowBlur  = 7;
    ctx.stroke();
    ctx.shadowBlur = 0;
  }
}

class TankGauge extends AnimatedGauge {

  constructor(canvas, opts) {
    super(canvas, opts, { min: 0, max: 1, ease: 0.14, settle: 0.0006 });
    this.color  = opts.color || "45, 212, 191";
    this._ready = true;
    this._draw();
  }

  _draw() {
    if (this.w < 20 || this.h < 40) return;
    const ctx = this.ctx;
    const w   = this.w;
    const h   = this.h;
    ctx.clearRect(0, 0, w, h);

    const x0 = 3;
    const y0 = 3;
    const tw = w - 16;
    const th = h - 6;

    ctx.beginPath();
    ctx.roundRect(x0, y0, tw, th, 3);
    ctx.strokeStyle = "rgba(220, 235, 245, 0.22)";
    ctx.lineWidth   = 1;
    ctx.stroke();

    for (let i = 1; i < 10; i++) {
      const gy    = y0 + th - (i / 10) * th;
      const major = i % 5 === 0;
      ctx.beginPath();
      ctx.moveTo(x0 + tw + 2, gy);
      ctx.lineTo(x0 + tw + (major ? 9 : 5), gy);
      ctx.strokeStyle = major ? "rgba(220, 235, 245, 0.40)" : "rgba(220, 235, 245, 0.18)";
      ctx.lineWidth   = 1;
      ctx.stroke();
    }

    const fh = this.v * (th - 2);
    const fy = y0 + th - 1 - fh;
    if (fh > 0.5) {
      const grad = ctx.createLinearGradient(0, fy, 0, y0 + th);
      grad.addColorStop(0, `rgba(${this.color}, 0.42)`);
      grad.addColorStop(1, `rgba(${this.color}, 0.14)`);
      ctx.beginPath();
      ctx.roundRect(x0 + 1.5, fy, tw - 3, fh, 2);
      ctx.fillStyle = grad;
      ctx.fill();

      ctx.beginPath();
      ctx.moveTo(x0 + 2, fy);
      ctx.lineTo(x0 + tw - 2, fy);
      ctx.strokeStyle = `rgba(${this.color}, 0.95)`;
      ctx.lineWidth   = 1.4;
      ctx.shadowColor = `rgba(${this.color}, 0.6)`;
      ctx.shadowBlur  = 6;
      ctx.stroke();
      ctx.shadowBlur = 0;
    }

    const pct  = Math.round(this.v * 100);
    const high = fy < y0 + 16;
    ctx.font         = "600 9.5px 'JetBrains Mono', ui-monospace, monospace";
    ctx.textAlign    = "center";
    ctx.textBaseline = "middle";
    ctx.fillStyle    = "rgba(230, 240, 246, 0.9)";
    ctx.fillText(`${pct}%`, x0 + tw / 2, high ? fy + 12 : fy - 9);
  }
}

class SegMeter extends AnimatedGauge {

  constructor(canvas, opts) {
    super(canvas, opts, { min: 0, max: 1, ease: 0.16, settle: 0.0006 });
    this.color   = opts.color || "45, 212, 191";
    this.redFrom = opts.redFrom != null ? opts.redFrom : 0.92;
    this._ready  = true;
    this._draw();
  }

  _draw() {
    if (this.w < 30 || this.h < 6) return;
    const ctx = this.ctx;
    const w   = this.w;
    const h   = this.h;
    ctx.clearRect(0, 0, w, h);

    const gap  = 2;
    const segs = Math.max(16, Math.min(56, Math.floor(w / 14)));
    const sw   = (w - (segs - 1) * gap) / segs;
    const lit  = this.v * segs;

    for (let i = 0; i < segs; i++) {
      const x    = i * (sw + gap);
      const on   = i + 1 <= lit ? 1 : Math.max(0, lit - i);
      const red  = (i + 1) / segs > this.redFrom;
      const tint = red ? "248, 113, 113" : this.color;
      const a    = on > 0 ? 0.25 + 0.65 * on : 0.10;

      if (on > 0.5 && i + 1 >= Math.floor(lit)) {
        ctx.shadowColor = `rgba(${tint}, 0.6)`;
        ctx.shadowBlur  = 5;
      }
      ctx.fillStyle = on > 0 ? `rgba(${tint}, ${a.toFixed(3)})` : `rgba(220, 235, 245, ${a.toFixed(3)})`;
      ctx.fillRect(x, 1, sw, h - 2);
      ctx.shadowBlur = 0;
    }
  }
}

window.DialGauge   = DialGauge;
window.LinearMeter = LinearMeter;
window.TankGauge = TankGauge;
window.SegMeter  = SegMeter;
