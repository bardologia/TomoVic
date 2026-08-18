"use strict";

const REDUCED_MOTION = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

class CanvasBase {
  constructor(canvas) {
    this.canvas = canvas;
    this.ctx = canvas.getContext("2d");
    this.dpr = Math.min(window.devicePixelRatio || 1, 2);
    this.w = 0;
    this.h = 0;
    this._resize = this._resize.bind(this);
    window.addEventListener("resize", this._resize);
    if (window.ResizeObserver) {
      this._observer = new ResizeObserver(() => this._resize());
      this._observer.observe(this.canvas);
    }
    this._resize();
  }

  _resize() {
    const rect = this.canvas.getBoundingClientRect();
    if (rect.width < 2 || rect.height < 2) return;
    this.w = Math.max(1, rect.width);
    this.h = Math.max(1, rect.height);
    this.canvas.width = this.w * this.dpr;
    this.canvas.height = this.h * this.dpr;
    this.ctx.setTransform(this.dpr, 0, 0, this.dpr, 0, 0);
    this.onResize();
  }

  resize() {
    this._resize();
  }

  dispose() {
    window.removeEventListener("resize", this._resize);
    if (this._observer) this._observer.disconnect();
    if (this._raf != null) {
      cancelAnimationFrame(this._raf);
      this._raf = null;
    }
  }

  onResize() {}
}

window.CanvasBase = CanvasBase;
window.REDUCED_MOTION = REDUCED_MOTION;
