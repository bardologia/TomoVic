"use strict";

class TomoScene extends CanvasBase {

  constructor(canvas) {
    super(canvas);
    this.t      = 0;
    this.frame  = 0;
    this.blue   = "111, 155, 255";
    this.ink    = "214, 226, 236";

    this.nTracks    = 4;
    this.fronts     = [];
    this.planes     = [];
    this.terrain    = [];
    this.scatterers = [];

    this._seed();

    if (REDUCED_MOTION) {
      this.t = 8;
      this._emit(0.55);
      this.fronts[0].r = this._maxRange() * 0.45;
      this._emit(0.55);
      this.fronts[1].r = this._maxRange() * 0.75;
      this._draw();
    } else {
      this._loop = this._loop.bind(this);
      requestAnimationFrame(this._loop);
    }
  }

  onResize() {
    this._seed();
    if (REDUCED_MOTION && this.terrain.length) this._draw();
  }

  _designH() {
    return Math.min(this.h, window.innerHeight || this.h);
  }

  _trackY(i) {
    return this._designH() * (0.10 + 0.045 * i);
  }

  _groundY(x) {
    let y = this._designH() * 0.86;
    for (const wave of this.terrain) y += Math.sin(x * wave.f + wave.p) * wave.a;
    return y;
  }

  _maxRange() {
    return Math.hypot(this.w, this._designH());
  }

  _seed() {
    const dh = this._designH();

    this.terrain = [
      { f: 0.004 + Math.random() * 0.002, p: Math.random() * 6, a: dh * 0.012 },
      { f: 0.011 + Math.random() * 0.004, p: Math.random() * 6, a: dh * 0.006 },
    ];

    this.planes = [];
    for (let i = 0; i < this.nTracks; i++) {
      this.planes.push({ track: i, offset: Math.random() * (this.w + 80), speed: 0.45 + i * 0.06 });
    }

    const count     = Math.round(this.w / 26);
    this.scatterers = [];
    for (let i = 0; i < count; i++) {
      const x = (this.w / count) * (i + 0.5) + (Math.random() - 0.5) * 10;
      this.scatterers.push({ x, height: 6 + Math.random() * dh * 0.05, lit: 0 });
    }

    this.fronts = [];
  }

  _emit(fraction = null) {
    const plane = this.planes[Math.floor(Math.random() * this.planes.length)];
    const x     = fraction != null ? this.w * fraction : -40 + ((this.t * 60 * plane.speed + plane.offset) % (this.w + 80));
    this.fronts.push({ cx: x, cy: this._trackY(plane.track), r: 4 });
  }

  _draw() {
    const ctx = this.ctx;
    ctx.clearRect(0, 0, this.w, this.h);

    this._drawTracks(ctx);
    this._drawFronts(ctx);
    this._drawGround(ctx);
  }

  _drawTracks(ctx) {
    ctx.save();
    ctx.setLineDash([3, 9]);
    ctx.lineWidth   = 1;
    ctx.strokeStyle = `rgba(${this.blue}, 0.12)`;
    for (let i = 0; i < this.nTracks; i++) {
      const y = this._trackY(i);
      ctx.beginPath();
      ctx.moveTo(0, y);
      ctx.lineTo(this.w, y);
      ctx.stroke();
    }
    ctx.restore();

    for (const plane of this.planes) {
      const x = -40 + ((this.t * 60 * plane.speed + plane.offset) % (this.w + 80));
      const y = this._trackY(plane.track);
      ctx.beginPath();
      ctx.moveTo(x + 7, y);
      ctx.lineTo(x - 5, y - 3.5);
      ctx.lineTo(x - 5, y + 3.5);
      ctx.closePath();
      ctx.fillStyle = `rgba(${this.blue}, 0.45)`;
      ctx.fill();
    }
  }

  _drawFronts(ctx) {
    const maxR = this._maxRange();
    ctx.lineWidth = 1.1;
    for (const front of this.fronts) {
      const fade = Math.max(0, 1 - front.r / maxR);
      ctx.beginPath();
      ctx.arc(front.cx, front.cy, front.r, Math.PI * 0.16, Math.PI * 0.84);
      ctx.strokeStyle = `rgba(${this.blue}, ${0.16 * fade})`;
      ctx.stroke();
      ctx.beginPath();
      ctx.arc(front.cx, front.cy, front.r * 0.92, Math.PI * 0.22, Math.PI * 0.78);
      ctx.strokeStyle = `rgba(${this.blue}, ${0.07 * fade})`;
      ctx.stroke();
    }
  }

  _drawGround(ctx) {
    ctx.beginPath();
    for (let x = 0; x <= this.w; x += 8) {
      const y = this._groundY(x);
      if (x === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    }
    ctx.strokeStyle = `rgba(${this.ink}, 0.18)`;
    ctx.lineWidth   = 1.2;
    ctx.stroke();

    for (const s of this.scatterers) {
      const gy   = this._groundY(s.x);
      const tipY = gy - s.height;
      ctx.beginPath();
      ctx.moveTo(s.x, gy);
      ctx.lineTo(s.x, tipY);
      ctx.strokeStyle = `rgba(${this.ink}, ${0.10 + 0.20 * s.lit})`;
      ctx.lineWidth   = 1;
      ctx.stroke();

      ctx.beginPath();
      ctx.arc(s.x, tipY, 1.6 + s.lit * 1.8, 0, Math.PI * 2);
      ctx.fillStyle = `rgba(${this.blue}, ${0.15 + 0.75 * s.lit})`;
      ctx.fill();

      if (s.lit > 0.05) {
        ctx.beginPath();
        ctx.arc(s.x, tipY, 5 * s.lit + 2, 0, Math.PI * 2);
        ctx.fillStyle = `rgba(${this.blue}, ${0.10 * s.lit})`;
        ctx.fill();
      }
    }
  }

  _loop() {
    this.t     += 0.016;
    this.frame += 1;

    if (this.frame % 120 === 0 && this.fronts.length < 6) this._emit();

    const maxR = this._maxRange();
    for (const front of this.fronts) front.r += 2.2;
    this.fronts = this.fronts.filter((front) => front.r < maxR);

    for (const s of this.scatterers) {
      const tipY = this._groundY(s.x) - s.height;
      for (const front of this.fronts) {
        const d = Math.hypot(s.x - front.cx, tipY - front.cy);
        if (Math.abs(d - front.r) < 12) s.lit = 1;
      }
      s.lit *= 0.96;
    }

    requestAnimationFrame(this._loop);
    this._draw();
  }
}

window.TomoScene = TomoScene;
