"use strict";

class AnimatedGauge extends CanvasBase {

  constructor(canvas, opts, tuning) {
    super(canvas);
    this.min    = opts.min != null ? opts.min : tuning.min;
    this.max    = opts.max != null ? opts.max : tuning.max;
    this.k      = tuning.k || 0;
    this.c      = tuning.c || 0;
    this.ease   = tuning.ease;
    this.settle = tuning.settle;
    this.v      = this.min;
    this.t      = this.min;
    this.vel    = 0;
    this.peak   = this.min;
    this.peakAt = 0;
    this._raf   = null;
    this._last  = 0;
    this._tick  = this._tick.bind(this);
    if (document.fonts && document.fonts.ready) document.fonts.ready.then(() => { if (this._ready && this.ctx) this._draw(); });
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

    if (REDUCED_MOTION) { this.v = v; this.vel = 0; this._draw(); return; }
    this._wake();
  }

  _wake() {
    if (this._raf != null) return;
    this._last = performance.now();
    this._raf  = requestAnimationFrame(this._tick);
  }

  _live() {
    return false;
  }

  _tick(now) {
    const dt   = Math.min(0.05, Math.max(0.001, (now - this._last) / 1000));
    this._last = now;
    if (this.k) {
      const n = Math.max(1, Math.ceil(dt * 240));
      const h = dt / n;
      for (let i = 0; i < n; i++) {
        this.vel += (-this.k * (this.v - this.t) - this.c * this.vel) * h;
        this.v   += this.vel * h;
      }
    } else {
      this.v += (this.t - this.v) * this.ease;
    }
    const span   = this.max - this.min;
    const landed = Math.abs(this.t - this.v) < span * this.settle && Math.abs(this.vel) < span * this.settle * 12;
    if (landed) { this.v = this.t; this.vel = 0; }
    this._draw();
    if (landed && !this._live()) { this._raf = null; return; }
    this._raf = requestAnimationFrame(this._tick);
  }
}

class DialGauge extends AnimatedGauge {

  static TRAIL    = 24;
  static SWEEP_MS = 720;

  constructor(canvas, opts) {
    super(canvas, opts, { min: 0, max: 100, k: 90, c: 13, settle: 0.0005 });
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
    this.trail  = [];
    this.swept  = false;
    this.held   = null;
    this._sweep = null;
    this._ready = true;
    this._draw();
  }

  set(value) {
    if (!this.swept) {
      this.swept = true;
      if (!REDUCED_MOTION) {
        this.held   = value;
        this.t      = this.max;
        this._sweep = setTimeout(() => {
          const v     = this.held;
          this.held   = null;
          this._sweep = null;
          this._note(v);
          super.set(v);
        }, DialGauge.SWEEP_MS);
        this._wake();
        return;
      }
    }
    if (this.held !== null) { this.held = value; return; }
    this._note(value);
    super.set(value);
  }

  _note(value) {
    if (value == null) return;
    this.trail.push(Math.max(this.min, Math.min(this.max, value)));
    if (this.trail.length > DialGauge.TRAIL) this.trail.shift();
  }

  dispose() {
    clearTimeout(this._sweep);
    super.dispose();
  }

  _alarm() {
    if (!this.zones.length) return false;
    return this.v >= this.zones[this.zones.length - 1].from;
  }

  _live() {
    return !REDUCED_MOTION && this._alarm();
  }

  _angle(v) {
    return this.a0 + ((v - this.min) / (this.max - this.min)) * (this.a1 - this.a0);
  }

  _arc(ctx, cx, cy, r, from, to, color, lw) {
    ctx.beginPath();
    ctx.arc(cx, cy, r, from, to);
    ctx.strokeStyle = color;
    ctx.lineWidth   = lw;
    ctx.stroke();
  }

  _ray(ctx, cx, cy, a, r0, r1, color, lw) {
    ctx.beginPath();
    ctx.moveTo(cx + Math.cos(a) * r0, cy + Math.sin(a) * r0);
    ctx.lineTo(cx + Math.cos(a) * r1, cy + Math.sin(a) * r1);
    ctx.strokeStyle = color;
    ctx.lineWidth   = lw;
    ctx.stroke();
  }

  _draw() {
    if (this.w < 30 || this.h < 30) return;
    const ctx = this.ctx;
    const w   = this.w;
    const h   = this.h;
    ctx.clearRect(0, 0, w, h);

    const big    = this.big;
    const r      = Math.max(12, Math.min((w - (big ? 54 : 40)) / 2, (h - (big ? 44 : 36)) / 1.588));
    const cx     = w / 2;
    const cy     = r + (big ? 27 : 22);
    const alarm  = this._alarm();
    const breath = alarm && !REDUCED_MOTION ? 0.5 + 0.5 * Math.sin(performance.now() / 260) : 1;
    const ink    = "220, 235, 245";

    ctx.beginPath();
    ctx.arc(cx, cy, r * 0.97, 0, Math.PI * 2);
    ctx.fillStyle = "rgba(6, 10, 14, 0.72)";
    ctx.fill();
    ctx.strokeStyle = `rgba(${ink}, 0.16)`;
    ctx.lineWidth   = 1;
    ctx.stroke();
    ctx.beginPath();
    ctx.arc(cx, cy, r * 0.89, 0, Math.PI * 2);
    ctx.strokeStyle = `rgba(${ink}, 0.07)`;
    ctx.stroke();

    const lw = Math.max(1.5, r * 0.04);
    this._arc(ctx, cx, cy, r, this.a0, this.a1, `rgba(${ink}, 0.14)`, 1);
    if (this.v > this.min) this._arc(ctx, cx, cy, r, this.a0, this._angle(this.v), `rgba(${this.color}, 0.9)`, lw);

    this.zones.forEach((z, i) => {
      const hot = alarm && i === this.zones.length - 1;
      this._arc(ctx, cx, cy, r + 4, this._angle(z.from), this._angle(z.to), `rgba(${z.color}, ${hot ? 0.45 + 0.55 * breath : 0.7})`, hot ? 2.2 : 1.4);
    });

    const steps = this.majors * this.minors;
    for (let i = 0; i <= steps; i++) {
      const major = i % this.minors === 0;
      const a     = this.a0 + (i / steps) * (this.a1 - this.a0);
      this._ray(ctx, cx, cy, a, r + 7, r + (major ? 12 : 9), `rgba(${ink}, ${major ? 0.55 : 0.22})`, major ? 1.2 : 1);
    }

    ctx.font         = `600 ${big ? 8.5 : 7.5}px 'JetBrains Mono', ui-monospace, monospace`;
    ctx.textAlign    = "center";
    ctx.textBaseline = "middle";
    ctx.fillStyle    = `rgba(${ink}, 0.78)`;
    for (let m = 0; m <= this.majors; m++) {
      const val = this.min + (m / this.majors) * (this.max - this.min);
      const a   = this._angle(val);
      ctx.fillText(String(Math.round(val)), cx + Math.cos(a) * (r + 19), cy + Math.sin(a) * (r + 19) + 0.5);
    }

    if (this.peak > this.v + (this.max - this.min) * 0.01) {
      this._ray(ctx, cx, cy, this._angle(this.peak), r - 7, r - 2, "rgba(251, 191, 36, 0.9)", 1.4);
    }

    const n = this.trail.length;
    this.trail.forEach((val, i) => {
      const age = (n - 1 - i) / Math.max(1, DialGauge.TRAIL - 1);
      this._ray(ctx, cx, cy, this._angle(val), r * 0.34, r * 0.76, `rgba(${ink}, ${(0.11 * (1 - age)).toFixed(3)})`, 1);
    });

    const na = this._angle(this.v);
    this._ray(ctx, cx, cy, na, -r * 0.12, r * 0.78, `rgba(230, 240, 246, 0.96)`, big ? 1.7 : 1.4);

    const hub   = Math.max(2.6, r * 0.07);
    const alert = alarm ? this.zones[this.zones.length - 1].color : null;
    ctx.beginPath();
    ctx.arc(cx, cy, hub, 0, Math.PI * 2);
    ctx.fillStyle   = "rgba(6, 10, 14, 0.95)";
    ctx.strokeStyle = alert ? `rgba(${alert}, ${0.5 + 0.5 * breath})` : `rgba(${ink}, 0.8)`;
    ctx.lineWidth   = 1.2;
    ctx.fill();
    ctx.stroke();

    const vy = cy + r * 0.42;
    ctx.font      = `600 ${big ? 16 : 12}px 'JetBrains Mono', ui-monospace, monospace`;
    ctx.fillStyle = "rgba(230, 240, 246, 0.96)";
    ctx.fillText(`${this.v.toFixed(this.digits)}${this.unit}`, cx, vy);

    ctx.font      = `600 ${big ? 7.5 : 7}px 'JetBrains Mono', ui-monospace, monospace`;
    ctx.fillStyle = "rgba(158, 173, 181, 0.9)";
    ctx.fillText(this.label, cx, vy + (big ? 13 : 11));
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

    ctx.font         = "700 8px 'JetBrains Mono', ui-monospace, monospace";
    ctx.textAlign    = "left";
    ctx.textBaseline = "middle";
    ctx.fillStyle    = "rgba(158, 173, 181, 0.95)";
    ctx.fillText(this.label, x0, 7);

    ctx.font      = "700 12.5px 'JetBrains Mono', ui-monospace, monospace";
    ctx.textAlign = "right";
    ctx.fillStyle = "rgba(230, 240, 246, 0.98)";
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
    ctx.font         = "700 9.5px 'JetBrains Mono', ui-monospace, monospace";
    ctx.textAlign    = "center";
    ctx.textBaseline = "middle";
    ctx.fillStyle    = "rgba(230, 240, 246, 0.97)";
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
