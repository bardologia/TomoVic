"use strict";

class ProcessAnimator {
  static SCENES = {
    processing: { T: 122, scale: 0.62, chapters: [
      { t0: 0,   name: "SLC stack",        fn: "_prGeo" },
      { t0: 14,  name: "Capon tomogram",   fn: "_prCapon" },
      { t0: 56,  name: "Worker pool",      fn: "_prWorkers" },
      { t0: 62,  name: "Interferograms",   fn: "_prIfg" },
      { t0: 92,  name: "DEM deramp",       fn: "_prDem" },
      { t0: 101, name: "Artifacts",        fn: "_prArtifacts" },
    ]},
    param: { T: 88, scale: 1, chapters: [
      { t0: 0,    name: "Pre-clean & normalize" },
      { t0: 15.5, name: "Local maxima" },
      { t0: 24.5, name: "min_dist pruning" },
      { t0: 33,   name: "Prominence" },
      { t0: 47,   name: "Adam sigma fits" },
      { t0: 62,   name: "Order selection" },
      { t0: 66,   name: "mu-sort & pad" },
      { t0: 74,   name: "Raw vs model" },
      { t0: 80,   name: "R² & full scene" },
    ]},
    dataset: { T: 118, scale: 1, chapters: [
      { t0: 0,   name: "Crop & split" },
      { t0: 16,  name: "Patch grid" },
      { t0: 44,  name: "Channel tensor" },
      { t0: 62,  name: "Augmentation" },
      { t0: 80,  name: "Normalization" },
      { t0: 104, name: "DataLoaders" },
    ]},
    training: { T: 199, scale: 1, chapters: [
      { t0: 0,   name: "Clamps & losses",   fn: "_trIntro" },
      { t0: 36,  name: "Optimizer step",    fn: "_trStep" },
      { t0: 66,  name: "LR schedule",       fn: "_trSched" },
      { t0: 90,  name: "Loss curriculum",   fn: "_trCurr" },
      { t0: 115, name: "Gradient clipping", fn: "_trClip" },
      { t0: 129, name: "mu-sort matching",  fn: "_trMatch" },
      { t0: 146, name: "Weight decay",      fn: "_trReg" },
      { t0: 158, name: "Dropout",           fn: "_trDrop" },
      { t0: 170, name: "Early stopping",    fn: "_trStop" },
      { t0: 182, name: "Training replay",   fn: "_trEnd" },
    ]},
    inference: { T: 124, scale: 1, still: 89, chapters: [
      { t0: 0,   name: "Checkpoint load",    fn: "_infLoad" },
      { t0: 14,  name: "Window grid",        fn: "_infGrid" },
      { t0: 30,  name: "Forward pass",       fn: "_infForward" },
      { t0: 46,  name: "Curve scoring",      fn: "_infScore" },
      { t0: 66,  name: "Overlap-add stitch", fn: "_infStitch" },
      { t0: 96,  name: "Metric maps",        fn: "_infMaps" },
      { t0: 106, name: "Global metrics",     fn: "_infMetrics" },
      { t0: 117, name: "Report",             fn: "_infReport" },
    ]},
    tuning: { T: 96, scale: 1, chapters: [
      { t0: 0,  name: "Search space",  fn: "_tuSpace" },
      { t0: 10, name: "Random warmup", fn: "_tuAccum" },
      { t0: 26, name: "TPE model",     fn: "_tuTpe" },
      { t0: 44, name: "Trial run",     fn: "_tuTrial" },
      { t0: 64, name: "Parallel GPUs", fn: "_tuParallel" },
      { t0: 76, name: "Chunk resume",  fn: "_tuHandoff" },
      { t0: 88, name: "Best export",   fn: "_tuExport" },
    ]},
  };

  constructor(canvas, caption) {
    this.canvas = canvas;
    this.ctx = canvas.getContext("2d");
    this.caption = caption;
    this.dpr = Math.min(window.devicePixelRatio || 1, 2);
    this.raf = null;
    this.t = 0;
    this.key = null;
    this.speed = 1;
    this.manual = false;
    this.onProgress = null;
    this.reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    this._loop = this._loop.bind(this);
    window.addEventListener("resize", () => { if (this.key) { this._resize(); this._draw(); } });
  }

  start(key) {
    this.key = key;
    this.t = 0;
    this.manual = false;
    this.stop();
    this._resize();
    if (this.reduced) { this.t = 6; this._draw(); this._notify(); return; }
    this.play();
  }

  play() {
    if (this.raf || !this.key) return;
    if (this.reduced) this.manual = true;
    this.raf = requestAnimationFrame(this._loop);
    this._notify();
  }

  pause() {
    this.stop();
    this._notify();
  }

  toggle() { if (this.raf) this.pause(); else this.play(); }

  playing() { return this.raf !== null; }

  stop() {
    if (this.raf) cancelAnimationFrame(this.raf);
    this.raf = null;
    this._last = undefined;
  }

  close() {
    this.stop();
    this.key = null;
  }

  sceneDef() { return ProcessAnimator.SCENES[this.key] || null; }

  duration() {
    const def = this.sceneDef();
    return def ? def.T / def.scale : 0;
  }

  position() {
    const dur = this.duration();
    return dur ? this.t % dur : 0;
  }

  chapterIndex() {
    const def = this.sceneDef();
    if (!def) return 0;
    const tt = this.position() * def.scale;
    let idx = 0;
    def.chapters.forEach((c, i) => { if (tt >= c.t0) idx = i; });
    return idx;
  }

  seek(tDisplay) {
    const dur = this.duration();
    if (!dur) return;
    this.t = Math.min(Math.max(0, tDisplay), dur - 1e-4);
    if (!this.raf) this._draw();
    this._notify();
  }

  seekChapter(i) {
    const def = this.sceneDef();
    if (!def) return;
    const c = def.chapters[Math.min(Math.max(0, i), def.chapters.length - 1)];
    this.seek(c.t0 / def.scale);
  }

  _notify() {
    if (this.onProgress) this.onProgress(this.position(), this.chapterIndex(), this.playing());
  }

  _resize() {
    this.w = Math.max(1, this.canvas.clientWidth);
    this.h = Math.max(1, this.canvas.clientHeight);
    this.canvas.width = this.w * this.dpr;
    this.canvas.height = this.h * this.dpr;
    this.ctx.setTransform(this.dpr, 0, 0, this.dpr, 0, 0);
  }

  _loop(now) {
    const dt = this._last === undefined ? 1 / 60 : Math.min(0.05, (now - this._last) / 1000);
    this._last = now;
    this.t += dt * this.speed;
    this._draw();
    this._notify();
    this.raf = requestAnimationFrame(this._loop);
  }

  _draw() {
    this.ctx.clearRect(0, 0, this.w, this.h);
    const fn = this["_" + this.key];
    if (fn) fn.call(this); else this._generic();
  }

  _dispatch(key, d) {
    const def = ProcessAnimator.SCENES[key];
    let tt = (this.t * def.scale) % def.T;
    if (this.reduced && !this.manual && def.still !== undefined) tt = def.still;
    let c = def.chapters[0];
    def.chapters.forEach((ch) => { if (ch.fn && tt >= ch.t0) c = ch; });
    this[c.fn](tt - c.t0, d);
  }

  /* ---------- helpers ---------- */

  _cap(text) { if (this.caption) this.caption.textContent = text; }
  _ease(p) { return p < 0 ? 0 : p > 1 ? 1 : 1 - Math.pow(1 - p, 3); }
  _lerp(a, b, p) { return a + (b - a) * p; }

  _grid(pad) { this._axes(pad, "elevation", "power"); }

  _axes(pad, xlab, ylab) {
    const { ctx, w, h } = this;
    ctx.strokeStyle = "rgba(120,200,220,0.08)";
    ctx.lineWidth = 1;
    for (let i = 0; i <= 4; i++) {
      const y = pad.t + ((h - pad.t - pad.b) / 4) * i;
      ctx.beginPath(); ctx.moveTo(pad.l, y); ctx.lineTo(w - pad.r, y); ctx.stroke();
    }
    for (let i = 0; i <= 6; i++) {
      const x = pad.l + ((w - pad.l - pad.r) / 6) * i;
      ctx.beginPath(); ctx.moveTo(x, pad.t); ctx.lineTo(x, h - pad.b); ctx.stroke();
    }
    ctx.fillStyle = "rgba(143,176,170,0.8)";
    ctx.font = "11px 'IBM Plex Mono', monospace";
    ctx.fillText(ylab, pad.l - 38, pad.t + 10);
    ctx.fillText(xlab, w - pad.r - ctx.measureText(xlab).width, h - 8);
  }

  _curvePath(params, fn, px, py) {
    const ctx = this.ctx, N = 140;
    ctx.beginPath();
    for (let i = 0; i <= N; i++) {
      const x = i / N, sx = px(x), sy = py(fn(params, x));
      i ? ctx.lineTo(sx, sy) : ctx.moveTo(sx, sy);
    }
  }

  _tex(tex, px, color) {
    const key = tex + "|" + px + "|" + color;
    const C   = ProcessAnimator._eqCache || (ProcessAnimator._eqCache = {});

    let e = C[key];
    if (e) return e;
    e = C[key] = { ready: false, failed: false, img: null, w: 0, h: 0 };
    if (!(window.MathJax && window.MathJax.tex2svg)) { delete C[key]; return e; }

    try {
      const node = window.MathJax.tex2svg(tex, { display: true });
      const svg  = node.querySelector("svg");
      svg.setAttribute("color", color);

      const vb  = svg.viewBox.baseVal;
      const exH = parseFloat(svg.getAttribute("height")) || 2;
      e.h = exH * px * 0.5;
      e.w = e.h * vb.width / vb.height;
      svg.setAttribute("height", (e.h * 3) + "px");
      svg.setAttribute("width", (e.w * 3) + "px");

      const img   = new Image();
      img.onload  = () => { e.img = img; e.ready = true; if (this.raf === null && this.key) this._draw(); };
      img.onerror = () => { e.failed = true; };
      img.src     = "data:image/svg+xml;charset=utf-8," + encodeURIComponent(new XMLSerializer().serializeToString(svg));
    } catch (err) { e.failed = true; }
    return e;
  }

  _texDraw(tex, x, y, px, o) {
    o = o || {};
    const a = o.alpha === undefined ? 1 : o.alpha < 0 ? 0 : o.alpha > 1 ? 1 : o.alpha;
    if (a <= 0) return null;

    const e = this._tex(tex, px, o.color || "rgba(191,232,226,0.95)");
    if (!e.ready) return null;

    let dx = x;
    if (o.align === "center") dx = x - e.w / 2;
    else if (o.align === "right") dx = x - e.w;

    const ctx = this.ctx;
    ctx.save();
    ctx.globalAlpha *= a;
    ctx.drawImage(e.img, dx, y, e.w, e.h);
    ctx.restore();
    return { x: dx, y, w: e.w, h: e.h };
  }

  /* ---------- parameter extraction: Gaussian fit ---------- */

  _param() {
    const { ctx, w, h } = this;
    const pad = { l: 46, r: 16, t: 18, b: 30 };
    const px = (x) => pad.l + x * (w - pad.l - pad.r);
    const maxY = 1.35;

    const comps = [{ a: 0.62, mu: 0.30, s: 0.055 }, { a: 0.95, mu: 0.55, s: 0.06 }, { a: 0.40, mu: 0.78, s: 0.045 }];
    const clean = (x) => comps.reduce((y, p) => y + p.a * Math.exp(-((x - p.mu) ** 2) / (2 * p.s * p.s)), 0);
    const noise = (x) => 0.05 * Math.sin(x * 147.3) + 0.04 * Math.sin(x * 89.7 + 1.3) + 0.03 * Math.sin(x * 233.1 + 2.1) + 0.02 * Math.sin(x * 401.7 + 0.6) + 0.025;
    const target = (x) => Math.max(0, clean(x) + noise(x));
    const mix = (ps, x) => ps.reduce((y, p) => y + p.a * Math.exp(-((x - p.mu) ** 2) / (2 * p.s * p.s)), 0);
    const NS = 240;
    const TRUNC = 212;
    const ys = [];
    for (let i = 0; i <= NS; i++) ys.push(target(i / NS));
    const rawMax  = Math.max(...ys);
    const thrZ    = 0.25 * rawMax;
    const ysClean = ys.map((v, i) => (i >= TRUNC || v < thrZ) ? 0 : v);
    const smo = ysClean.slice();
    const maxProf = Math.max(...smo);
    const thrP = 0.05 * maxProf;
    const H_SPAN = 40;
    const dh = H_SPAN / NS;
    const sigmaGuess = (k) => Math.max(2 * dh, H_SPAN / (8 * k));
    const minDistSamples = (k) => Math.max(1, Math.round(sigmaGuess(k) / dh));
    const minD = minDistSamples(5);

    const maximaAll = [];
    for (let i = 1; i < NS; i++) {
      if (smo[i] > smo[i - 1] && smo[i] >= smo[i + 1] && smo[i] >= thrZ) {
        const hp = smo[i];
        let l = i, lm = hp;
        while (l > 0) { l--; if (smo[l] > hp) break; if (smo[l] < lm) lm = smo[l]; }
        let r = i, rm = hp;
        while (r < NS) { r++; if (smo[r] > hp) break; if (smo[r] < rm) rm = smo[r]; }
        maximaAll.push({ i, x: i / NS, y: hp, prom: hp - Math.max(lm, rm), base: Math.max(lm, rm), lx: l / NS, rx: r / NS });
      }
    }
    const byHeight = [...maximaAll].sort((p, q) => q.y - p.y);
    const distKept = [];
    const distDropped = [];
    byHeight.forEach((m) => {
      if (distKept.some((k) => Math.abs(k.i - m.i) < minD)) distDropped.push(m);
      else distKept.push(m);
    });
    const maxima = [...distKept].sort((p, q) => p.x - q.x);
    const ranked = [...maxima].sort((p, q) => q.prom - p.prom);
    const kept = ranked.filter((m) => m.prom >= thrP).slice(0, 5);
    const cands = ranked.slice(0, 5).map((m) => {
      const near = comps.find((c) => Math.abs(c.mu - m.x) < 0.05);
      return { mu: m.x, a: m.y, s: near ? near.s : 0.015 };
    });
    while (cands.length < 5) {
      const used = cands.map((c) => Math.round(c.mu * NS));
      let bi = 0, bv = -1;
      for (let i = 0; i <= NS; i++) {
        if (used.some((u) => Math.abs(u - i) < minD)) continue;
        if (smo[i] > bv) { bv = smo[i]; bi = i; }
      }
      cands.push({ mu: bi / NS, a: Math.max(bv, 0.05), s: 0.015 });
    }

    const T = 88.0, tt = this.t % T;
    const FIT = 3.0, FITS0 = 47.0;
    const SEL0 = FITS0 + 5 * FIT;
    const SORT0 = SEL0 + 4.0;
    const FINAL0 = SORT0 + 8.0;
    const R2_0 = FINAL0 + 6.0;
    const CODA0 = R2_0 + 6.0;

    const normP  = tt < 13.0 ? 0 : tt < 15.5 ? this._ease((tt - 13.0) / 2.0) : 1;
    const topVal = this._lerp(maxY, 1.15 * maxProf, normP);
    const py     = (v) => pad.t + (1 - Math.min(1, Math.max(0, v) / topVal)) * (h - pad.t - pad.b);

    if (tt < SORT0) {
      this._axes(pad, "elevation", tt >= 13.0 ? "normalized power" : "power");

      const truncX = px(TRUNC / NS);
      if (tt < 13.0) {
        const trZ   = tt >= 5.5 && tt < 8.0 ? this._ease((tt - 5.5) / 1.0) : tt >= 8.0 ? 1 : 0;
        const thrZf = tt >= 2.5 && tt < 5.5 ? this._ease((tt - 2.5) / 2.0) : tt >= 5.5 ? 1 : 0;
        const dispV = (i) => { let v = ys[i]; if (v < thrZ) v = this._lerp(v, 0, thrZf); if (i >= TRUNC) v = this._lerp(v, 0, trZ); return v; };
        ctx.beginPath();
        for (let i = 0; i <= NS; i++) { const sx = px(i / NS), sy = py(dispV(i)); i ? ctx.lineTo(sx, sy) : ctx.moveTo(sx, sy); }
        ctx.lineTo(px(1), py(0)); ctx.lineTo(px(0), py(0)); ctx.closePath();
        ctx.fillStyle = "rgba(140,168,182,0.14)"; ctx.fill();
        ctx.beginPath();
        for (let i = 0; i <= NS; i++) { const sx = px(i / NS), sy = py(dispV(i)); i ? ctx.lineTo(sx, sy) : ctx.moveTo(sx, sy); }
        ctx.strokeStyle = "rgba(150,176,182,0.6)"; ctx.lineWidth = 1.2; ctx.stroke();
      }

      if (tt >= 5.5 && tt < 8.0) {
        const sw = this._ease(Math.min(1, (tt - 5.5) / 1.0));
        const gx = this._lerp(w - pad.r, truncX, sw);
        ctx.strokeStyle = "rgba(255,207,107,0.85)"; ctx.lineWidth = 1.6;
        ctx.beginPath(); ctx.moveTo(gx, pad.t); ctx.lineTo(gx, h - pad.b); ctx.stroke();
        ctx.fillStyle = "rgba(255,207,107,0.9)"; ctx.font = "11px 'IBM Plex Mono', monospace";
        ctx.fillText("truncation_index", Math.max(pad.l + 4, gx - 116), pad.t + 14);
      }

      if (tt >= 13.0 && !(tt >= 15.5 && tt < 22.0) && !(tt >= 24.5 && tt < 30.9)) {
        ctx.beginPath();
        for (let i = 0; i <= NS; i++) { const sx = px(i / NS), sy = py(smo[i]); i ? ctx.lineTo(sx, sy) : ctx.moveTo(sx, sy); }
        ctx.lineTo(px(1), py(0)); ctx.lineTo(px(0), py(0)); ctx.closePath();
        ctx.fillStyle = "rgba(53,230,208,0.07)"; ctx.fill();

        ctx.beginPath();
        for (let i = 0; i <= NS; i++) { const sx = px(i / NS), sy = py(smo[i]); i ? ctx.lineTo(sx, sy) : ctx.moveTo(sx, sy); }
        ctx.strokeStyle = "rgba(53,230,208,0.85)"; ctx.lineWidth = 2; ctx.stroke();
      }
    }

    const S0v = (k) => sigmaGuess(k) / H_SPAN;
    const LAM = 5e-3;
    const mse = (m) => {
      let e = 0;
      for (let i = 0; i <= 80; i++) { const x = i / 80; const d = mix(m, x) - target(x); e += d * d; }
      return e / 81;
    };
    const finalModel = (k) => cands.slice(0, k).map((c) => ({ a: c.a, mu: c.mu, s: c.s }));
    const meanA = (k) => cands.slice(0, k).reduce((s, c) => s + c.a, 0) / k;
    const pen = (k) => LAM * k * meanA(k);
    const J = (k) => mse(finalModel(k)) + pen(k);
    const bestK = [1, 2, 3, 4, 5].reduce((b, k) => (J(k) < J(b) ? k : b), 1);

    const drawPeak = (c, rank, lit) => {
      ctx.strokeStyle = `rgba(124,255,155,${lit ? 0.4 : 0.18})`; ctx.setLineDash([2, 3]); ctx.lineWidth = 1;
      ctx.beginPath(); ctx.moveTo(px(c.mu), py(0)); ctx.lineTo(px(c.mu), py(c.a)); ctx.stroke(); ctx.setLineDash([]);
      ctx.fillStyle = lit ? "#7cff9b" : "rgba(124,255,155,0.35)";
      ctx.beginPath(); ctx.arc(px(c.mu), py(c.a), lit ? 4.5 : 3, 0, 7); ctx.fill();
      ctx.fillStyle = lit ? "#7cff9b" : "rgba(124,255,155,0.5)";
      ctx.font = "10px 'IBM Plex Mono', monospace";
      ctx.fillText(String(rank + 1), px(c.mu) - 3, py(c.a) - 9);
    };

    const drawChart = (done, highlight, dim) => {
      if (done < 1) return;
      ctx.save(); if (dim) ctx.globalAlpha = 0.4;
      const cw = 232, ch = 132, cxp = w - pad.r - cw - 12, cyp = pad.t + 14;
      ctx.fillStyle = "rgba(4,7,10,0.78)"; ctx.fillRect(cxp - 12, cyp - 22, cw + 24, ch + 66);
      ctx.strokeStyle = "rgba(120,200,220,0.28)"; ctx.lineWidth = 1; ctx.strokeRect(cxp - 12, cyp - 22, cw + 24, ch + 66);
      this._texDraw("J(K)=\\mathrm{MSE}+\\lambda\\sum_k a_k", cxp - 2, cyp - 20, 14, { align: "left", color: "rgba(178,206,200,0.95)" });
      const jmax = J(1) * 1.12;
      for (let k = 1; k <= Math.min(done, 5); k++) {
        const bw2 = 30, bx = cxp + (k - 1) * (bw2 + 14) + 4;
        const mseH = (mse(finalModel(k)) / jmax) * ch;
        const penH = (pen(k) / jmax) * ch;
        ctx.fillStyle = "rgba(53,230,208,0.65)";
        ctx.fillRect(bx, cyp + ch - mseH, bw2, mseH);
        ctx.fillStyle = "rgba(255,207,107,0.75)";
        ctx.fillRect(bx, cyp + ch - mseH - penH, bw2, penH);
        if (highlight && k === bestK) {
          ctx.strokeStyle = "#7cff9b"; ctx.lineWidth = 2;
          ctx.strokeRect(bx - 3, cyp + ch - mseH - penH - 3, bw2 + 6, mseH + penH + 6);
          ctx.fillStyle = "#7cff9b"; ctx.fillText("K*", bx + 9, cyp + ch - mseH - penH - 10);
        }
        ctx.fillStyle = "rgba(143,176,170,0.95)";
        ctx.fillText("K" + k, bx + 8, cyp + ch + 17);
      }
      const ly = cyp + ch + 38;
      ctx.fillStyle = "rgba(53,230,208,0.75)"; ctx.fillRect(cxp - 2, ly - 10, 11, 11);
      ctx.fillStyle = "rgba(143,176,170,0.95)"; ctx.fillText("mse", cxp + 15, ly);
      ctx.fillStyle = "rgba(255,207,107,0.8)"; ctx.fillRect(cxp + 64, ly - 10, 11, 11);
      ctx.fillStyle = "rgba(143,176,170,0.95)"; ctx.fillText("λ·Σa", cxp + 81, ly);
      ctx.restore();
    };

    let model = null, iter = 0, caption = "", done = 0, highlight = false, modelDashed = false;

    if (tt < 2.5) {
      caption = "Input: one elevation profile from the beamformed tomogram  ·  |tomogram| for one azimuth-range pixel";
    } else if (tt < FITS0) {
      const thrY = py(thrZ);
      const inZoom = (tt >= 13.0 && tt < 15.5) || (tt >= 15.5 && tt < 22.0) || (tt >= 24.5 && tt < 30.9);
      if (!inZoom) {
        ctx.strokeStyle = "rgba(255,207,107,0.55)"; ctx.setLineDash([6, 4]); ctx.lineWidth = 1.2;
        ctx.beginPath(); ctx.moveTo(pad.l, thrY); ctx.lineTo(w - pad.r, thrY); ctx.stroke(); ctx.setLineDash([]);
        ctx.fillStyle = "rgba(255,207,107,0.75)"; ctx.font = "11px 'IBM Plex Mono', monospace";
        ctx.fillText("0.25 × max", w - pad.r - 78, thrY - 6);
      }

      const dot = (m, color, rad, alpha) => {
        ctx.save(); ctx.globalAlpha = alpha == null ? 1 : alpha;
        ctx.fillStyle = color; ctx.beginPath(); ctx.arc(px(m.x), py(m.y), rad, 0, 7); ctx.fill(); ctx.restore();
      };

      const drawBracket = (m, withValue) => {
        ctx.strokeStyle = "rgba(255,207,107,0.6)"; ctx.setLineDash([4, 3]); ctx.lineWidth = 1.2;
        ctx.beginPath(); ctx.moveTo(px(m.lx), py(m.base)); ctx.lineTo(px(m.rx), py(m.base)); ctx.stroke(); ctx.setLineDash([]);
        ctx.strokeStyle = "#ffcf6b"; ctx.lineWidth = 2;
        ctx.beginPath(); ctx.moveTo(px(m.x), py(m.base)); ctx.lineTo(px(m.x), py(m.y)); ctx.stroke();
        ctx.beginPath(); ctx.moveTo(px(m.x) - 5, py(m.y)); ctx.lineTo(px(m.x) + 5, py(m.y)); ctx.stroke();
        ctx.beginPath(); ctx.moveTo(px(m.x) - 5, py(m.base)); ctx.lineTo(px(m.x) + 5, py(m.base)); ctx.stroke();
        dot(m, "#ffcf6b", 4.5);
        if (withValue) {
          ctx.fillStyle = "#ffcf6b"; ctx.font = "12px 'IBM Plex Mono', monospace";
          ctx.fillText("prom = " + m.prom.toFixed(2), Math.min(px(m.x) + 10, w - 116), py((m.y + m.base) / 2));
        }
      };

      if (tt < 5.5) {
        caption = "Pre-clean 1/2: samples below threshold_factor × max (0.25) are zeroed out  ·  the baseline between lobes collapses to zero";
      } else if (tt < 8.0) {
        caption = "Pre-clean 2/2: high-elevation samples beyond truncation_index = 170 are zeroed";
      } else if (tt < 13.0) {
        const ga = this._ease(Math.min(1, (tt - 8.5) / 0.8));
        if (ga > 0) {
          const bw6 = Math.min(260, w * 0.27), bh6 = 86;
          const bx6 = w - pad.r - bw6 - 14, by6 = pad.t + 30;
          ctx.save(); ctx.globalAlpha = ga;
          ctx.fillStyle = "rgba(7,12,17,0.94)"; ctx.fillRect(bx6, by6, bw6, bh6);
          ctx.strokeStyle = "rgba(255,107,125,0.55)"; ctx.lineWidth = 1.3; ctx.strokeRect(bx6, by6, bw6, bh6);
          const thY6 = by6 + bh6 - 12 - bh6 * 0.34;
          ctx.strokeStyle = "rgba(255,207,107,0.7)"; ctx.setLineDash([4, 3]); ctx.lineWidth = 1.1;
          ctx.beginPath(); ctx.moveTo(bx6 + 6, thY6); ctx.lineTo(bx6 + bw6 - 6, thY6); ctx.stroke(); ctx.setLineDash([]);
          ctx.beginPath();
          for (let i = 0; i <= 70; i++) {
            const xx = bx6 + 8 + (i / 70) * (bw6 - 16);
            const yy = by6 + bh6 - 12 - Math.abs(noise(i / 70)) * bh6 * 1.4;
            i ? ctx.lineTo(xx, yy) : ctx.moveTo(xx, yy);
          }
          ctx.strokeStyle = "rgba(255,107,125,0.85)"; ctx.lineWidth = 1.4; ctx.stroke();
          ctx.font = "11px 'IBM Plex Mono', monospace";
          ctx.fillStyle = "rgba(255,207,107,0.85)"; ctx.fillText("5e-2", bx6 + bw6 - 40, thY6 - 5);
          ctx.fillStyle = "rgba(255,107,125,0.9)"; ctx.fillText("neighbour pixel · max ≤ 5e-2 → skipped", bx6 + 8, by6 - 8);
          ctx.fillStyle = "rgba(94,114,128,0.95)"; ctx.fillText("output stays all-zero", bx6 + 8, by6 + bh6 + 16);
          ctx.fillStyle = "#7cff9b"; ctx.font = "12px 'IBM Plex Mono', monospace";
          ctx.fillText("max > 5e-2 ✓ fitted", pad.l + 10, pad.t + 36);
          ctx.restore();
        }
        caption = "Activity gate: a pixel is fitted only if its profile max exceeds activity_threshold (5e-2)  ·  inactive pixels keep zeros";
      } else if (tt < 15.5) {
        const tn = tt - 13.0;
        const pmaxV = Math.max(...smo);
        const yMax = py(pmaxV);
        ctx.strokeStyle = "rgba(53,230,208,0.7)"; ctx.setLineDash([5, 4]); ctx.lineWidth = 1.2;
        ctx.beginPath(); ctx.moveTo(pad.l, yMax); ctx.lineTo(w - pad.r, yMax); ctx.stroke(); ctx.setLineDash([]);
        ctx.fillStyle = "rgba(53,230,208,0.9)"; ctx.font = "11px 'IBM Plex Mono', monospace";
        ctx.fillText("peak value", pad.l + 6, yMax - 6);
        const relab = this._ease(Math.min(1, Math.max(0, (tn - 0.8) / 1.2)));
        if (relab > 0) {
          ctx.save(); ctx.globalAlpha = relab;
          ctx.fillStyle = "rgba(124,255,155,0.85)"; ctx.font = "11px 'IBM Plex Mono', monospace";
          ctx.fillText("1.0", pad.l - 26, yMax + 4);
          ctx.fillText("0.0", pad.l - 26, py(0) + 4);
          ctx.restore();
        }
        this._texDraw("\\tilde{\\gamma}(\\xi)=\\dfrac{\\gamma(\\xi)}{\\max_\\xi \\gamma(\\xi)}", w - pad.r - 8, pad.t + 2, 14, { align: "right", alpha: relab, color: "rgba(53,230,208,0.95)" });
        caption = tn < 1.6 ? "Re-scale to max 1: each active profile is divided by its own maximum, so the peak rises to 1.0" : "The fit and its loss are defined on this normalized profile  (γ̃ = γ / max γ)";
      } else if (tt < 22.0) {
        const ts2 = tt - 15.5;
        const refI = ranked[0] ? ranked[0].i : Math.round(0.55 * NS);
        const negI = Math.max(2, refI - 8);
        const posI = refI;
        let focusI = negI, leftOk = null, rightOk = null, verdict = null, z = 1;
        if (ts2 < 0.9) { z = this._ease(ts2 / 0.9); }
        else if (ts2 < 1.9) { leftOk = smo[negI - 1] < smo[negI]; }
        else if (ts2 < 3.1) { leftOk = smo[negI - 1] < smo[negI]; rightOk = smo[negI + 1] < smo[negI]; verdict = leftOk && rightOk ? "max" : "not"; }
        else if (ts2 < 4.0) { focusI = Math.round(this._lerp(negI, posI, this._ease((ts2 - 3.1) / 0.9))); }
        else if (ts2 < 5.0) { focusI = posI; leftOk = smo[posI - 1] < smo[posI]; }
        else if (ts2 < 5.9) { focusI = posI; leftOk = smo[posI - 1] < smo[posI]; rightOk = smo[posI + 1] < smo[posI]; verdict = leftOk && rightOk ? "max" : "not"; }
        else { focusI = posI; verdict = "max"; z = 1 - this._ease((ts2 - 5.9) / 0.6); }

        const halfW = 6 / NS;
        let lo2 = Infinity, hi2 = -Infinity;
        for (let j = Math.max(0, focusI - 6); j <= Math.min(NS, focusI + 6); j++) { lo2 = Math.min(lo2, smo[j]); hi2 = Math.max(hi2, smo[j]); }
        const spanL = Math.max(1e-4, hi2 - lo2);
        const vx0 = this._lerp(0, focusI / NS - halfW, z);
        const vx1 = this._lerp(1, focusI / NS + halfW, z);
        const vy0 = this._lerp(0, lo2 - spanL * 0.45, z);
        const vy1 = this._lerp(topVal, hi2 + spanL * 0.55, z);
        const zx = (x) => pad.l + ((x - vx0) / (vx1 - vx0)) * (w - pad.l - pad.r);
        const zy = (v) => pad.t + (1 - (v - vy0) / (vy1 - vy0)) * (h - pad.t - pad.b);

        ctx.save();
        ctx.beginPath(); ctx.rect(pad.l, pad.t, w - pad.l - pad.r, h - pad.t - pad.b); ctx.clip();

        ctx.beginPath();
        for (let i = 0; i <= NS; i++) { const X = zx(i / NS), Y = zy(smo[i]); i ? ctx.lineTo(X, Y) : ctx.moveTo(X, Y); }
        ctx.lineTo(w - pad.r, h - pad.b); ctx.lineTo(pad.l, h - pad.b); ctx.closePath();
        ctx.fillStyle = "rgba(53,230,208,0.07)"; ctx.fill();
        ctx.beginPath();
        for (let i = 0; i <= NS; i++) { const X = zx(i / NS), Y = zy(smo[i]); i ? ctx.lineTo(X, Y) : ctx.moveTo(X, Y); }
        ctx.strokeStyle = "rgba(53,230,208,0.85)"; ctx.lineWidth = 2; ctx.stroke();

        if (z > 0.3) {
          for (let j = 0; j <= NS; j++) {
            const X = zx(j / NS);
            if (X < pad.l - 12 || X > w - pad.r + 12) continue;
            ctx.fillStyle = `rgba(230,247,243,${0.4 * z})`;
            ctx.beginPath(); ctx.arc(X, zy(smo[j]), 3.2, 0, 7); ctx.fill();
          }
          if (leftOk != null || verdict) {
            ctx.strokeStyle = `rgba(53,230,208,${0.45 * z})`; ctx.setLineDash([5, 4]); ctx.lineWidth = 1.1;
            ctx.beginPath(); ctx.moveTo(pad.l, zy(smo[focusI])); ctx.lineTo(w - pad.r, zy(smo[focusI])); ctx.stroke(); ctx.setLineDash([]);
          }
        }

        const pt = (j, color, r) => { ctx.fillStyle = color; ctx.beginPath(); ctx.arc(zx(j / NS), zy(smo[j]), r, 0, 7); ctx.fill(); };
        pt(focusI, "#35e6d0", 6.5);
        if (z > 0.5) {
          pt(focusI - 1, "#ffcf6b", 5.5);
          pt(focusI + 1, "#ffcf6b", 5.5);
          ctx.font = "13px 'IBM Plex Mono', monospace";
          if (leftOk != null) {
            ctx.fillStyle = leftOk ? "#7cff9b" : "#ff6b7d";
            ctx.fillText(leftOk ? "lower" : "higher", zx((focusI - 1) / NS) - 46, zy(smo[focusI - 1]) + (leftOk ? 36 : -24));
          }
          if (rightOk != null) {
            ctx.fillStyle = rightOk ? "#7cff9b" : "#ff6b7d";
            ctx.fillText(rightOk ? "lower" : "higher", zx((focusI + 1) / NS) + 2, zy(smo[focusI + 1]) + (rightOk ? 36 : -24));
          }
          if (verdict) {
            ctx.fillStyle = verdict === "max" ? "#7cff9b" : "#ff6b7d";
            ctx.font = "14px 'IBM Plex Mono', monospace";
            const label = verdict === "max" ? "LOCAL MAXIMUM" : "not a maximum";
            ctx.fillText(label, zx(focusI / NS) - 54, zy(smo[focusI]) - 24);
          }
        }
        if (verdict === "max" && z < 0.5) pt(focusI, "#7cff9b", 4.5);
        ctx.restore();

        if (ts2 < 0.9) caption = "Local maxima: zoom into the curve, sample by sample";
        else if (ts2 < 1.9) caption = "Is the LEFT neighbour lower than the sample?  yes";
        else if (ts2 < 3.1) caption = "Is the RIGHT neighbour lower?  No, the curve keeps rising  →  not a maximum";
        else if (ts2 < 4.0) caption = "Slide along the samples toward the top of the lobe";
        else if (ts2 < 5.0) caption = "Again: is the LEFT neighbour lower?  yes";
        else if (ts2 < 5.9) caption = "The RIGHT neighbour is lower too  →  this sample is a LOCAL MAXIMUM";
        else caption = "Zoom back out  ·  the maximum is kept";
      } else if (tt < 24.5) {
        const scanP = Math.min(1, (tt - 22.0) / 2.3);
        const ci = Math.max(0, Math.min(NS, Math.round(scanP * NS)));
        maximaAll.forEach((m) => { if (m.x <= scanP) dot(m, "rgba(230,247,243,0.9)", 3.5); });
        ctx.fillStyle = "#35e6d0";
        ctx.beginPath(); ctx.arc(px(ci / NS), py(smo[ci]), 5.5, 0, 7); ctx.fill();
        ctx.strokeStyle = "rgba(53,230,208,0.4)"; ctx.lineWidth = 1.4;
        ctx.beginPath(); ctx.arc(px(ci / NS), py(smo[ci]), 9.5, 0, 7); ctx.stroke();
        caption = `Sweep the same test across all samples  ·  ${maximaAll.filter((m) => m.x <= scanP).length} local maxima found`;
      } else if (tt < 33.0) {
        const ts4 = tt - 24.5;
        const axisY = h - pad.b;
        const demoDrop = distDropped[0] || null;
        const demoKeep = demoDrop ? distKept.find((k) => Math.abs(k.i - demoDrop.i) < minD) : null;
        const hasDemo = !!(demoDrop && demoKeep);

        const range = (kpt, lit) => {
          const halfPx = px(minD / NS) - px(0);
          const cx2 = px(kpt.i / NS);
          const x1 = Math.max(pad.l, cx2 - halfPx), x2 = Math.min(w - pad.r, cx2 + halfPx);
          ctx.fillStyle = `rgba(124,255,155,${lit ? 0.2 : 0.09})`;
          ctx.fillRect(x1, axisY - 7, x2 - x1, 7);
          ctx.strokeStyle = `rgba(124,255,155,${lit ? 0.95 : 0.4})`; ctx.lineWidth = 1.6;
          ctx.beginPath(); ctx.moveTo(x1, axisY); ctx.lineTo(x2, axisY); ctx.stroke();
          ctx.beginPath(); ctx.moveTo(x1, axisY - 10); ctx.lineTo(x1, axisY); ctx.stroke();
          ctx.beginPath(); ctx.moveTo(x2, axisY - 10); ctx.lineTo(x2, axisY); ctx.stroke();
        };
        const crossAt = (X, Y) => {
          ctx.strokeStyle = "rgba(255,107,125,0.95)"; ctx.lineWidth = 1.8;
          ctx.beginPath(); ctx.moveTo(X - 5, Y - 5); ctx.lineTo(X + 5, Y + 5); ctx.stroke();
          ctx.beginPath(); ctx.moveTo(X - 5, Y + 5); ctx.lineTo(X + 5, Y - 5); ctx.stroke();
        };

        if (hasDemo && ts4 < 6.4) {
          let z;
          if (ts4 < 1.0) z = this._ease(ts4 / 1.0);
          else if (ts4 < 5.6) z = 1;
          else z = 1 - this._ease((ts4 - 5.6) / 0.8);

          const midI = (demoDrop.i + demoKeep.i) / 2;
          const halfN = Math.max(Math.abs(demoDrop.i - demoKeep.i), minD) * 1.7;
          const j0 = Math.max(0, Math.round(midI - halfN)), j1 = Math.min(NS, Math.round(midI + halfN));
          let lo2 = Infinity, hi2 = -Infinity;
          for (let j = j0; j <= j1; j++) { lo2 = Math.min(lo2, smo[j]); hi2 = Math.max(hi2, smo[j]); }
          const spanL = Math.max(1e-4, hi2 - lo2);
          const vx0 = this._lerp(0, (midI - halfN) / NS, z);
          const vx1 = this._lerp(1, (midI + halfN) / NS, z);
          const vy0 = this._lerp(0, lo2 - spanL * 0.55, z);
          const vy1 = this._lerp(topVal, hi2 + spanL * 0.65, z);
          const zx = (x) => pad.l + ((x - vx0) / (vx1 - vx0)) * (w - pad.l - pad.r);
          const zy = (v) => pad.t + (1 - (v - vy0) / (vy1 - vy0)) * (h - pad.t - pad.b);

          ctx.save();
          ctx.beginPath(); ctx.rect(pad.l, pad.t, w - pad.l - pad.r, h - pad.t - pad.b); ctx.clip();
          ctx.beginPath();
          for (let i = 0; i <= NS; i++) { const X = zx(i / NS), Y = zy(smo[i]); i ? ctx.lineTo(X, Y) : ctx.moveTo(X, Y); }
          ctx.lineTo(w - pad.r, h - pad.b); ctx.lineTo(pad.l, h - pad.b); ctx.closePath();
          ctx.fillStyle = "rgba(53,230,208,0.07)"; ctx.fill();
          ctx.beginPath();
          for (let i = 0; i <= NS; i++) { const X = zx(i / NS), Y = zy(smo[i]); i ? ctx.lineTo(X, Y) : ctx.moveTo(X, Y); }
          ctx.strokeStyle = "rgba(53,230,208,0.85)"; ctx.lineWidth = 2; ctx.stroke();

          if (z > 0.3) {
            for (let j = 0; j <= NS; j++) {
              const X = zx(j / NS);
              if (X < pad.l - 12 || X > w - pad.r + 12) continue;
              ctx.fillStyle = `rgba(230,247,243,${0.32 * z})`;
              ctx.beginPath(); ctx.arc(X, zy(smo[j]), 3, 0, 7); ctx.fill();
            }
          }
          const regP = this._ease(Math.min(1, Math.max(0, (ts4 - 1.0) / 1.2)));
          if (regP > 0 && z > 0.4) {
            const rx1 = zx((demoKeep.i - minD * regP) / NS);
            const rx2 = zx((demoKeep.i + minD * regP) / NS);
            ctx.fillStyle = `rgba(124,255,155,${0.05 * z})`;
            ctx.fillRect(rx1, pad.t, rx2 - rx1, h - pad.t - pad.b);
            const byy = h - pad.b - 18;
            ctx.strokeStyle = `rgba(124,255,155,${0.85 * z})`; ctx.lineWidth = 1.5;
            ctx.beginPath(); ctx.moveTo(rx1, byy); ctx.lineTo(rx2, byy); ctx.stroke();
            ctx.beginPath(); ctx.moveTo(rx1, byy - 5); ctx.lineTo(rx1, byy + 5); ctx.stroke();
            ctx.beginPath(); ctx.moveTo(rx2, byy - 5); ctx.lineTo(rx2, byy + 5); ctx.stroke();
            if (regP >= 1) {
              ctx.save(); ctx.textAlign = "center";
              ctx.fillStyle = `rgba(124,255,155,${0.9 * z})`; ctx.font = "12px 'IBM Plex Mono', monospace";
              ctx.fillText(`± min_dist = ${minD} samples`, (rx1 + rx2) / 2, byy - 12);
              ctx.restore();
            }
          }

          if (ts4 > 2.2 && z > 0.4) {
            const redP = (ts4 - 2.2) / 1.2;
            for (let j = Math.max(0, demoKeep.i - minD + 1); j <= Math.min(NS, demoKeep.i + minD - 1); j++) {
              if (j === demoKeep.i) continue;
              const dN = Math.abs(j - demoKeep.i) / minD;
              const aP = Math.min(1, Math.max(0, (redP - dN * 0.7) / 0.3));
              if (aP <= 0) continue;
              ctx.fillStyle = `rgba(255,107,125,${0.8 * aP * z})`;
              ctx.beginPath(); ctx.arc(zx(j / NS), zy(smo[j]), 3.4, 0, 7); ctx.fill();
            }
          }

          ctx.fillStyle = "#7cff9b"; ctx.beginPath(); ctx.arc(zx(demoKeep.i / NS), zy(demoKeep.y), 6.5, 0, 7); ctx.fill();

          const remP = Math.min(1, Math.max(0, (ts4 - 3.8) / 0.9));
          const dropA = 1 - remP * 0.8;
          ctx.fillStyle = ts4 < 2.4 ? `rgba(255,207,107,${z})` : `rgba(255,107,125,${dropA * Math.max(z, 0.4)})`;
          ctx.beginPath(); ctx.arc(zx(demoDrop.i / NS), zy(demoDrop.y), ts4 < 2.4 ? 5.5 : 6, 0, 7); ctx.fill();
          if (ts4 > 3.8) crossAt(zx(demoDrop.i / NS), zy(demoDrop.y));
          ctx.restore();

          if (ts4 < 1.0) caption = "Zoom on a maximum that is about to be removed";
          else if (ts4 < 2.2) caption = "The kept peak claims ± min_dist samples around itself";
          else if (ts4 < 3.8) caption = "Every sample inside the region is too close to the peak";
          else if (ts4 < 5.6) caption = "The weaker maximum falls inside the region  →  removed";
          else caption = "Zoom back out";
        } else {
          maximaAll.forEach((m) => dot(m, "rgba(230,247,243,0.5)", 2.5));
          const start = hasDemo ? 6.4 : 0.3;
          const per = 1.9 / Math.max(1, distKept.length);
          const upto = Math.min(distKept.length - 1, Math.floor((ts4 - start) / per));
          for (let j = 0; j <= upto; j++) {
            dot(distKept[j], "#7cff9b", 4);
            range(distKept[j], j === upto);
          }
          distDropped.forEach((m) => {
            const within = distKept.slice(0, upto + 1).some((k) => Math.abs(k.i - m.i) < minD);
            if (within) crossAt(px(m.x), py(m.y));
          });
          caption = "Each kept peak claims ± min_dist samples on the axis  ·  crowded weaker maxima are removed";
        }
      } else if (tt < 41.5) {
        maxima.forEach((m) => dot(m, "rgba(230,247,243,0.3)", 2.5));
        const d = ranked.find((m) => Math.abs(m.x - 0.30) < 0.05) || ranked[0];
        if (d) {
          const ts3 = tt - 33.0;
          const iP = Math.round(d.x * NS), iL = Math.round(d.lx * NS), iR = Math.round(d.rx * NS);
          const argmin = (a, b) => { let mi = Math.min(a, b), mv = Infinity; for (let j = Math.min(a, b); j <= Math.max(a, b); j++) if (smo[j] < mv) { mv = smo[j]; mi = j; } return mi; };

          const ring = (alpha) => {
            ctx.save(); ctx.globalAlpha = alpha;
            ctx.strokeStyle = "#7cff9b"; ctx.lineWidth = 1.6;
            ctx.beginPath(); ctx.arc(px(d.x), py(d.y), 8 + Math.sin(this.t * 5) * 1.6, 0, 7); ctx.stroke();
            ctx.restore();
          };
          const walk = (fromI, toI, p) => {
            const cur = Math.round(this._lerp(fromI, toI, p));
            const step = fromI < toI ? 1 : -1;
            ctx.strokeStyle = "rgba(255,207,107,0.85)"; ctx.lineWidth = 2.2;
            ctx.beginPath();
            for (let j = fromI; step > 0 ? j <= cur : j >= cur; j += step) {
              const sx = px(j / NS), sy = py(smo[j]);
              j === fromI ? ctx.moveTo(sx, sy) : ctx.lineTo(sx, sy);
            }
            ctx.stroke();
            ctx.fillStyle = "#ffcf6b"; ctx.beginPath(); ctx.arc(px(cur / NS), py(smo[cur]), 4.5, 0, 7); ctx.fill();
            return cur;
          };
          const baseMark = (idx, label, lit) => {
            ctx.strokeStyle = lit ? "#7cff9b" : "rgba(255,207,107,0.85)"; ctx.lineWidth = 1.6;
            ctx.beginPath(); ctx.arc(px(idx / NS), py(smo[idx]), 5, 0, 7); ctx.stroke();
            ctx.fillStyle = lit ? "#7cff9b" : "rgba(255,207,107,0.85)"; ctx.font = "11px 'IBM Plex Mono', monospace";
            ctx.fillText(label, px(idx / NS) - 24, py(smo[idx]) + 19);
          };

          ring(1);
          if (ts3 < 1.2) {
            caption = "Measure prominence: take one local maximum";
          } else if (ts3 < 3.7) {
            const p = (ts3 - 1.2) / 2.5;
            const cur = walk(iP, iL, this._ease(p));
            baseMark(argmin(iP, cur), "min", false);
            caption = "Walk LEFT along the curve until a higher point (or the edge)  ·  track the lowest value";
          } else if (ts3 < 6.2) {
            walk(iP, iL, 1);
            baseMark(argmin(iP, iL), "left min", false);
            const p = (ts3 - 3.7) / 2.5;
            const cur = walk(iP, iR, this._ease(p));
            baseMark(argmin(iP, cur), "min", false);
            caption = "Walk RIGHT  ·  the next lobe rises higher, so the walk stops there";
          } else if (ts3 < 7.5) {
            walk(iP, iL, 1); walk(iP, iR, 1);
            const li = argmin(iP, iL), ri = argmin(iP, iR);
            const baseIsLeft = smo[li] >= smo[ri];
            baseMark(li, "left min", baseIsLeft);
            baseMark(ri, "right min", !baseIsLeft);
            ctx.strokeStyle = "rgba(124,255,155,0.5)"; ctx.setLineDash([4, 3]);
            ctx.beginPath(); ctx.moveTo(px(d.lx), py(d.base)); ctx.lineTo(px(d.rx), py(d.base)); ctx.stroke(); ctx.setLineDash([]);
            caption = "Base = the HIGHER of the two minima";
          } else {
            ctx.save(); ctx.globalAlpha = 0.35; walk(iP, iL, 1); walk(iP, iR, 1); ctx.restore();
            drawBracket(d, true);
            this._texDraw("\\mathrm{prom}=\\gamma_{\\mathrm{peak}}-\\gamma_{\\mathrm{base}}", w - pad.r - 8, pad.t + 2, 14, { align: "right", alpha: this._ease(Math.min(1, (ts3 - 7.5) / 0.8)), color: "rgba(255,207,107,0.95)" });
            caption = "Prominence = peak height − base  ·  how much the peak stands out";
          }
        }
      } else if (tt < 44.5) {
        maxima.forEach((m) => dot(m, "rgba(230,247,243,0.45)", 2.5));
        const seq = ranked.slice(0, Math.min(8, ranked.length)).sort((p, q) => p.x - q.x);
        if (seq.length) {
          const per = 2.8 / seq.length;
          const upto = Math.min(seq.length - 1, Math.floor((tt - 41.5) / per));
          for (let j = 0; j <= upto; j++) drawBracket(seq[j], j === upto);
        }
        caption = "Same measurement swept across every local maximum";
      } else {
        const fade = Math.min(1, (tt - 44.5) / 1.2);
        maxima.forEach((m) => {
          const ki = kept.indexOf(m);
          if (ki >= 0) {
            dot(m, "#7cff9b", 4.5);
            ctx.fillStyle = "#7cff9b"; ctx.font = "11px 'IBM Plex Mono', monospace";
            ctx.fillText(String(ki + 1), px(m.x) - 3, py(m.y) - 10);
          } else {
            dot(m, "rgba(255,107,125,0.7)", 2.5, 1 - fade * 0.85);
          }
        });
        caption = "scipy find_peaks: keep prominence ≥ 0.05 × max, ranked by prominence  ·  too few peaks? residual argmax fills the seeds";
      }
    } else if (tt < SEL0) {
      const k = Math.min(5, Math.floor((tt - FITS0) / FIT) + 1);
      const segT = (tt - FITS0) % FIT;
      const HOLD = 0.8;
      const guessing = segT < HOLD;
      const prog = guessing ? 0 : this._ease(Math.min(1, (segT - HOLD) / (FIT - HOLD - 0.25)));
      const DIVISOR = 4.0;
      const S0base  = S0v(5);
      const S0      = S0base / DIVISOR;
      done = k - 1;
      model = cands.slice(0, k).map((c, i) => {
        const pk = this._ease(Math.min(1, Math.max(0, prog * 1.25 - i * 0.06)));
        return { a: c.a, mu: c.mu, s: this._lerp(S0, c.s, pk) };
      });
      modelDashed = guessing;
      iter = guessing ? 0 : Math.round(prog * 3000);
      cands.slice(0, k).forEach((c) => {
        ctx.strokeStyle = "rgba(124,255,155,0.85)"; ctx.lineWidth = 1.6;
        ctx.beginPath(); ctx.moveTo(px(c.mu) - 7, py(c.a)); ctx.lineTo(px(c.mu) + 7, py(c.a)); ctx.stroke();
        ctx.setLineDash([2, 3]); ctx.lineWidth = 1; ctx.strokeStyle = "rgba(124,255,155,0.5)";
        ctx.beginPath(); ctx.moveTo(px(c.mu), py(0)); ctx.lineTo(px(c.mu), py(c.a)); ctx.stroke(); ctx.setLineDash([]);
        ctx.fillStyle = "#7cff9b"; ctx.beginPath(); ctx.arc(px(c.mu), py(c.a), 3.5, 0, 7); ctx.fill();
      });
      if (!guessing) {
        const sbHi = (H_SPAN / 2) / H_SPAN, sbLo = dh / H_SPAN;
        cands.slice(0, k).forEach((c) => {
          const yw = py(c.a * 0.607);
          ctx.strokeStyle = "rgba(255,207,107,0.4)"; ctx.lineWidth = 1;
          ctx.beginPath(); ctx.moveTo(px(Math.max(0, c.mu - sbHi)), yw - 8); ctx.lineTo(px(Math.max(0, c.mu - sbHi)), yw + 8); ctx.stroke();
          ctx.beginPath(); ctx.moveTo(px(Math.min(1, c.mu + sbHi)), yw - 8); ctx.lineTo(px(Math.min(1, c.mu + sbHi)), yw + 8); ctx.stroke();
        });
      }
      const fitFade = this._ease(Math.min(1, (tt - FITS0) / 0.6));
      const lgX = pad.l + 8, lgY = pad.t + 58;
      ctx.save(); ctx.globalAlpha = fitFade;
      ctx.fillStyle = "rgba(4,7,10,0.78)"; ctx.fillRect(lgX - 6, lgY - 14, 96, 40);
      ctx.strokeStyle = "rgba(120,200,220,0.22)"; ctx.lineWidth = 1; ctx.strokeRect(lgX - 6, lgY - 14, 96, 40);
      ctx.font = "12px 'IBM Plex Mono', monospace";
      ctx.fillStyle = "#7cff9b"; ctx.fillText("a, μ fixed", lgX, lgY + 1);
      ctx.fillStyle = "#ffcf6b"; ctx.fillText("σ →", lgX, lgY + 18);
      ctx.restore();
      const eqCx = (pad.l + 78 + (w - pad.r - 256)) / 2;
      this._texDraw("\\hat{\\gamma}(\\xi)=\\sum_{k=1}^{K} a_k\\,e^{-(\\xi-\\mu_k)^2/2\\sigma_k^2}", eqCx, pad.t + 2, 16, { align: "center", alpha: fitFade, color: "rgba(53,230,208,0.95)" });
      const s0Alpha = fitFade * (1 - this._ease(Math.min(1, Math.max(0, (tt - 52.0) / 1.5))));
      const upAlpha = fitFade * this._ease(Math.min(1, Math.max(0, (tt - 53.0) / 1.5)));
      if (s0Alpha > 0.01) {
        this._texDraw("\\sigma_{\\mathrm{base}}=\\max\\!\\left(2\\,\\Delta\\xi,\\;\\tfrac{h_{\\mathrm{span}}}{8K_{\\max}}\\right)", eqCx, pad.t + 62, 14, { align: "center", alpha: s0Alpha, color: "rgba(255,207,107,0.95)" });
        this._texDraw("\\sigma_0=\\sigma_{\\mathrm{base}}/d,\\;\\,d=4", pad.l + 6, pad.t + 26, 12, { align: "left", alpha: s0Alpha, color: "rgba(124,255,155,0.95)" });
      }
      if (upAlpha > 0.01) {
        const upX = pad.l + 6, upY = pad.t + 104;
        ctx.save(); ctx.globalAlpha = upAlpha;
        ctx.fillStyle = "rgba(4,7,10,0.7)"; ctx.fillRect(upX - 6, upY - 16, 250, 96);
        ctx.strokeStyle = "rgba(120,200,220,0.18)"; ctx.lineWidth = 1; ctx.strokeRect(upX - 6, upY - 16, 250, 96);
        ctx.restore();
        this._texDraw("g=\\partial\\mathcal{L}/\\partial\\sigma\\;\\;(a,\\mu\\ \\text{fixed})", upX, upY, 11, { align: "left", alpha: upAlpha, color: "rgba(143,176,170,0.95)" });
        this._texDraw("m\\leftarrow\\beta_1 m+(1-\\beta_1)\\,g", upX, upY + 18, 12, { align: "left", alpha: upAlpha, color: "rgba(53,230,208,0.9)" });
        this._texDraw("v\\leftarrow\\beta_2 v+(1-\\beta_2)\\,g^2", upX, upY + 38, 12, { align: "left", alpha: upAlpha, color: "rgba(53,230,208,0.9)" });
        this._texDraw("\\sigma\\leftarrow\\mathrm{clip}\\!\\left(\\sigma-\\eta\\,\\tfrac{\\hat{m}}{\\sqrt{\\hat{v}}+\\epsilon},\\;[\\sigma_{\\min},\\sigma_{\\max}]\\right)", upX, upY + 58, 13, { align: "left", alpha: upAlpha, color: "rgba(255,207,107,0.95)" });
      }
      if (guessing) {
        const divP = this._ease(Math.min(1, segT / HOLD));
        const half = this._lerp(S0base, S0, divP);
        ctx.font = "13px 'IBM Plex Mono', monospace";
        cands.slice(0, k).forEach((c, ci) => {
          const yb = py(c.a * 0.607);
          const bx1 = px(c.mu - S0base), bx2 = px(c.mu + S0base);
          ctx.strokeStyle = "rgba(255,207,107,0.35)"; ctx.lineWidth = 1.2;
          ctx.beginPath(); ctx.moveTo(bx1, yb); ctx.lineTo(bx2, yb); ctx.stroke();
          ctx.beginPath(); ctx.moveTo(bx1, yb - 5); ctx.lineTo(bx1, yb + 5); ctx.stroke();
          ctx.beginPath(); ctx.moveTo(bx2, yb - 5); ctx.lineTo(bx2, yb + 5); ctx.stroke();
          const x1 = px(c.mu - half), x2 = px(c.mu + half);
          ctx.strokeStyle = "#ffcf6b"; ctx.lineWidth = 1.6;
          ctx.beginPath(); ctx.moveTo(x1, yb); ctx.lineTo(x2, yb); ctx.stroke();
          ctx.beginPath(); ctx.moveTo(x1, yb - 5); ctx.lineTo(x1, yb + 5); ctx.stroke();
          ctx.beginPath(); ctx.moveTo(x2, yb - 5); ctx.lineTo(x2, yb + 5); ctx.stroke();
          ctx.save(); ctx.textAlign = "center";
          ctx.fillStyle = "#ffcf6b"; ctx.fillText("σ₀", px(c.mu), yb + 19);
          if (ci === 0) { ctx.fillStyle = "rgba(255,207,107,0.6)"; ctx.fillText("σ_base", (bx1 + bx2) / 2, yb - 9); }
          ctx.restore();
        });
        caption = `K = ${k}  ·  ONE shared init at K_max = 5: σ_base = max(2·Δξ, h_span/40) = ${sigmaGuess(5).toFixed(1)} m, σ₀ = σ_base / 4 = ${(sigmaGuess(5) / DIVISOR).toFixed(2)} m  ·  first ${k} seed${k > 1 ? "s" : ""} reused`;
      } else if (k === 2 && prog < 0.45) {
        caption = "σ is clipped to [Δξ, h_span/2] during the fit";
      } else {
        caption = `Sigma-only Adam fit with K = ${k}  ·  μ & amplitude frozen, σ adjusts from the guess`;
      }
      if (prog >= 1) done = k;
    } else if (tt < SORT0) {
      done = 5; highlight = true;
      model = finalModel(bestK);
      cands.forEach((c, r) => drawPeak(c, r, r < bestK));
      caption = `Order selection  ·  J(K) = MSE + λ·Σa, λ = 5e-3  →  K* = ${bestK}`;
    } else if (tt < FINAL0) {
      const ts = tt - SORT0;
      const KMAX = 5;
      const act = cands.slice(0, bestK);
      const order = act.map((c, i) => ({ i, mu: c.mu })).sort((p, q) => p.mu - q.mu);

      const gapH = 14, gapV = 16;
      const swH = Math.min(152, (w - 90 - (KMAX - 1) * gapH) / KMAX);
      const shH = 68;
      const stackH = bestK * shH + (bestK - 1) * gapV;
      const yV0 = Math.max(30, (h - stackH) / 2 - 10);
      const yV = (j) => yV0 + j * (shH + gapV);
      const totalRow = KMAX * swH + (KMAX - 1) * gapH;
      const xH0 = (w - totalRow) / 2;
      const xH = (j) => xH0 + j * (swH + gapH);
      const yRow = h / 2 - shH / 2;

      const card = (x, y, lines, dim, tag, alpha, hlLine) => {
        ctx.save();
        ctx.globalAlpha = alpha == null ? 1 : alpha;
        ctx.fillStyle = "rgba(7,12,17,0.96)";
        ctx.strokeStyle = dim ? "rgba(255,107,125,0.35)" : "#35e6d0";
        ctx.lineWidth = 1.4;
        ctx.beginPath();
        if (ctx.roundRect) ctx.roundRect(x, y, swH, shH, 8); else ctx.rect(x, y, swH, shH);
        ctx.fill(); ctx.stroke();
        ctx.font = "12px 'IBM Plex Mono', monospace";
        lines.forEach((ln, i2) => {
          if (i2 === hlLine) ctx.fillStyle = "#7cff9b";
          else ctx.fillStyle = dim ? "rgba(255,107,125,0.5)" : "rgba(230,247,243,0.95)";
          ctx.fillText(ln, x + 11, y + 19 + i2 * 16);
        });
        if (tag) { ctx.fillStyle = "#7cff9b"; ctx.fillText(tag, x + swH - 27, y + 16); }
        ctx.restore();
      };

      const appear = (r) => Math.min(1, Math.max(0, (ts - 0.25 - r * 0.4) / 0.6));
      const SORTSTART = 2.3, FLY = 2.0, STAG = 0.25;
      const cardP = (k) => this._ease(Math.min(1, Math.max(0, (ts - SORTSTART - k * STAG) / FLY)));
      const allLanded = ts >= SORTSTART + (bestK - 1) * STAG + FLY;
      const slotsA = Math.min(1, Math.max(0, (ts - (SORTSTART - 0.5)) / 0.6));
      const padA = Math.min(1, Math.max(0, (ts - 6.0) / 1.0));

      if (slotsA > 0) {
        for (let j = 0; j < KMAX; j++) {
          ctx.save(); ctx.globalAlpha = slotsA;
          ctx.strokeStyle = "rgba(120,200,220,0.3)"; ctx.setLineDash([5, 5]); ctx.lineWidth = 1.1;
          ctx.strokeRect(xH(j), yRow, swH, shH); ctx.setLineDash([]);
          ctx.fillStyle = "rgba(143,176,170,0.75)"; ctx.font = "11px 'IBM Plex Mono', monospace";
          ctx.fillText("slot " + (j + 1), xH(j) + 4, yRow + shH + 17);
          ctx.restore();
        }
      }

      if (allLanded) {
        ctx.fillStyle = "rgba(124,255,155,0.85)"; ctx.font = "12px 'IBM Plex Mono', monospace";
        ctx.fillText("μ ascending →", xH0 + 2, yRow - 18);
      }

      act.forEach((c, fitRank) => {
        const slotIdx = order.findIndex((o) => o.i === fitRank);
        const p = cardP(fitRank);
        const x = this._lerp(w / 2 - swH / 2, xH(slotIdx), p);
        const y = this._lerp(yV(fitRank), yRow, p) - Math.sin(Math.PI * p) * 34;
        const muM = (-20 + c.mu * 100).toFixed(1);
        const sM = (c.s * 100).toFixed(1);
        const flying = p > 0 && p < 1;
        card(x, y, [`a = ${c.a.toFixed(2)}`, `μ = ${muM} m`, `σ = ${sM} m`], false, "#" + (fitRank + 1), appear(fitRank), flying ? 1 : -1);

        const landT = SORTSTART + fitRank * STAG + FLY;
        const since = ts - landT;
        if (since > 0 && since < 0.45) {
          ctx.save(); ctx.globalAlpha = 1 - since / 0.45;
          ctx.strokeStyle = "#7cff9b"; ctx.lineWidth = 2;
          ctx.beginPath();
          if (ctx.roundRect) ctx.roundRect(xH(slotIdx) - 4, yRow - 4, swH + 8, shH + 8, 10); else ctx.rect(xH(slotIdx) - 4, yRow - 4, swH + 8, shH + 8);
          ctx.stroke(); ctx.restore();
        }
      });

      if (padA > 0) {
        for (let j = bestK; j < KMAX; j++) {
          const rise = (1 - padA) * 12;
          card(xH(j), yRow + rise, ["a = 0", "μ = -", "σ = -"], true, null, padA);
        }
      }

      if (ts < SORTSTART) caption = "Fitted parameter sets [a, μ, σ]  ·  stacked in prominence order";
      else if (ts < 5.8) caption = "Sorting by ascending μ (the highlighted key)  ·  inactive sets (a ≤ 0.05) sort last  ·  each set flies to its slot";
      else caption = "Padding to K_max = 5  ·  inactive slots zeroed (a = 0)  ·  final per-pixel array";
    }

    if (tt >= FINAL0 && tt < R2_0) {
      const tf = tt - FINAL0;
      this._axes(pad, "elevation", "normalized power");
      const fm = finalModel(bestK);

      const plotT = pad.t, plotB = h - pad.b;
      const midY = (plotT + plotB) / 2;
      const q = this._ease(Math.min(1, Math.max(0, (tf - 3.8) / 1.4)));
      const y1T = this._lerp(midY - 10, plotB, q);
      const y0B = this._lerp(midY + 10, plotT, q);
      const mapY = (v, y0, y1) => y0 + (1 - Math.min(1, Math.max(0, v) / topVal)) * (y1 - y0);

      ctx.beginPath();
      for (let i = 0; i <= NS; i++) { const X = px(i / NS), Y = mapY(ys[i], plotT, y1T); i ? ctx.lineTo(X, Y) : ctx.moveTo(X, Y); }
      ctx.strokeStyle = `rgba(150,176,182,${this._lerp(0.85, 0.55, q)})`;
      ctx.lineWidth = 1.3; ctx.stroke();

      const r = this._ease(Math.min(1, Math.max(0, (tf - 0.8) / 2.2)));
      const upTo = Math.round(r * NS);
      if (r > 0) {
        fm.forEach((c) => {
          ctx.beginPath();
          for (let i = 0; i <= upTo; i++) { const X = px(i / NS), Y = mapY(mix([c], i / NS), y0B, plotB); i ? ctx.lineTo(X, Y) : ctx.moveTo(X, Y); }
          ctx.strokeStyle = "rgba(53,230,208,0.25)"; ctx.lineWidth = 1; ctx.stroke();
        });
        ctx.beginPath();
        for (let i = 0; i <= upTo; i++) { const X = px(i / NS), Y = mapY(mix(fm, i / NS), y0B, plotB); i ? ctx.lineTo(X, Y) : ctx.moveTo(X, Y); }
        ctx.strokeStyle = "#35e6d0"; ctx.lineWidth = 2.2;
        ctx.shadowColor = "rgba(53,230,208,0.5)"; ctx.shadowBlur = 6;
        ctx.stroke(); ctx.shadowBlur = 0;

        if (r < 1) {
          const fx = px(upTo / NS);
          ctx.strokeStyle = "rgba(255,207,107,0.55)"; ctx.setLineDash([3, 4]); ctx.lineWidth = 1.1;
          ctx.beginPath(); ctx.moveTo(fx, mapY(ys[upTo], plotT, y1T)); ctx.lineTo(fx, mapY(mix(fm, upTo / NS), y0B, plotB)); ctx.stroke();
          ctx.setLineDash([]);
          ctx.fillStyle = "#ffcf6b"; ctx.beginPath(); ctx.arc(fx, mapY(mix(fm, upTo / NS), y0B, plotB), 4, 0, 7); ctx.fill();
        }
      }

      ctx.font = "12px 'IBM Plex Mono', monospace";
      ctx.fillStyle = "rgba(150,176,182,0.9)";
      ctx.fillText("raw", pad.l + 92, plotT + 18);
      if (r > 0.05) {
        ctx.fillStyle = "rgba(53,230,208,0.9)";
        ctx.fillText("model", pad.l + 92, this._lerp(midY + 26, plotT + 36, q));
      }

      if (tf < 0.8) caption = "The raw noisy profile, kept on top";
      else if (tf < 3.6) caption = "Below it, the modeled profile is traced from the fitted parameters";
      else if (tf < 5.2) caption = "Overlap the two in the middle";
      else caption = `raw vs model  ·  ${NS} noisy samples  →  3 × K* = ${3 * bestK} parameters`;
    }

    if (tt >= R2_0 && tt < CODA0) {
      const tr = tt - R2_0;
      this._axes(pad, "elevation", "normalized power");
      const fm = finalModel(bestK);
      const plotT = pad.t, plotB = h - pad.b;
      const mapY = (v) => plotT + (1 - Math.min(1, Math.max(0, v) / topVal)) * (plotB - plotT);

      const collapse = this._ease(Math.min(1, Math.max(0, (tr - 1.5) / 1.5)));
      const profA = 1 - collapse;

      if (profA > 0.02) {
        ctx.save(); ctx.globalAlpha = profA;
        ctx.beginPath();
        for (let i = 0; i <= NS; i++) { const X = px(i / NS), Y = mapY(ys[i]); i ? ctx.lineTo(X, Y) : ctx.moveTo(X, Y); }
        ctx.lineTo(px(NS / NS), mapY(mix(fm, 1)));
        for (let i = NS; i >= 0; i--) { ctx.lineTo(px(i / NS), mapY(mix(fm, i / NS))); }
        ctx.closePath();
        ctx.fillStyle = "rgba(255,107,125,0.18)"; ctx.fill();
        ctx.beginPath();
        for (let i = 0; i <= NS; i++) { const X = px(i / NS), Y = mapY(ys[i]); i ? ctx.lineTo(X, Y) : ctx.moveTo(X, Y); }
        ctx.strokeStyle = "rgba(150,176,182,0.7)"; ctx.lineWidth = 1.3; ctx.stroke();
        ctx.beginPath();
        for (let i = 0; i <= NS; i++) { const X = px(i / NS), Y = mapY(mix(fm, i / NS)); i ? ctx.lineTo(X, Y) : ctx.moveTo(X, Y); }
        ctx.strokeStyle = "#35e6d0"; ctx.lineWidth = 2; ctx.stroke();
        ctx.restore();
      }

      if (tr >= 1.5 && tr < 4.5) {
        const ssr = this._ease(Math.min(1, (tr - 1.7) / 1.0));
        const bx = px(0.30), bw = 30, baseY = mapY(0), topY = mapY(topVal * 0.78);
        ctx.fillStyle = "rgba(255,107,125,0.6)"; ctx.fillRect(bx, this._lerp(baseY, topY, ssr * 0.62), bw, this._lerp(0, baseY - topY, ssr) * 0.62);
        ctx.fillStyle = "rgba(230,247,243,0.55)"; ctx.fillRect(bx + 50, this._lerp(baseY, topY, ssr), bw, this._lerp(0, baseY - topY, ssr));
        ctx.font = "11px 'IBM Plex Mono', monospace";
        ctx.fillStyle = "rgba(255,107,125,0.9)"; ctx.fillText("SS_res", bx - 4, baseY + 16);
        ctx.fillStyle = "rgba(230,247,243,0.8)"; ctx.fillText("SS_tot", bx + 46, baseY + 16);
        const r2A = Math.min(this._ease(Math.min(1, (tr - 1.6) / 0.6)), 1 - this._ease(Math.min(1, Math.max(0, (tr - 4.1) / 0.4))));
        this._texDraw("R^2=1-\\dfrac{\\sum_i (\\hat{\\gamma}_i-\\gamma_i)^2}{\\sum_i (\\gamma_i-\\bar{\\gamma})^2}", px(0.42), plotT + 4, 15, { align: "left", alpha: r2A, color: "rgba(230,247,243,0.95)" });
      }

      if (tr >= 3.0) {
        const ap = this._ease(Math.min(1, (tr - 3.0) / 0.8));
        ctx.save(); ctx.globalAlpha = ap; ctx.textAlign = "center";
        ctx.font = "15px 'IBM Plex Mono', monospace"; ctx.fillStyle = "#7cff9b";
        ctx.fillText("R² = 0.97 (example)", w / 2, plotT + (plotB - plotT) * 0.32);
        ctx.restore();
      }

      if (tr >= 4.5) {
        const gp = this._ease(Math.min(1, (tr - 4.5) / 1.0));
        const cols = 8, rows = 4, s = 22, gx0 = w / 2 - (cols * s) / 2, gy0 = plotT + (plotB - plotT) * 0.42;
        const r2demo = [0.97, 0.94, 0.91, 0.88, 0.62, 0.96, 0.93, 0.85, 0.90, 0.95, 0.71, 0.40, 0.92, 0.97, 0.89, 0.83, 0.95, 0.55, 0.94, 0.91, 0.87, 0.96, 0.92, -0.1, 0.93, 0.90, 0.78, 0.95, 0.88, 0.97, 0.91, 0.64];
        for (let j = 0; j < cols * rows; j++) {
          const ci = j % cols, ri = Math.floor(j / cols);
          if (ci + ri * cols > gp * cols * rows) continue;
          this._paramHeatTile(gx0 + ci * s, gy0 + ri * s, s - 2, r2demo[j]);
        }
        ctx.font = "11px 'IBM Plex Mono', monospace"; ctx.fillStyle = "rgba(143,176,170,0.85)";
        ctx.save(); ctx.textAlign = "center";
        ctx.fillText("R² map  ·  Az × R", w / 2, gy0 + rows * s + 16);
        ctx.restore();
      }

      if (tr < 1.5) caption = "Quality metric: how well does the model explain the measured profile?";
      else if (tr < 4.5) caption = "R² = 1 − SS_res / SS_tot  ·  per pixel, on the raw amplitude scale";
      else caption = "R² = 0.97 here (example)  ·  aggregated into mean / median / percentile maps";
    }

    if (tt >= CODA0) {
      const tc = tt - CODA0;
      const fm = finalModel(bestK);
      const cols = 14, rows = 8, s = Math.min(20, (w - 80) / cols), gx0 = (w - cols * s) / 2, gy0 = (h - rows * s) / 2 - 6;
      const fill = this._ease(Math.min(1, tc / 1.5));
      const total = cols * rows;
      const shown = Math.round(fill * total);

      for (let j = 0; j < total; j++) {
        if (j >= shown) continue;
        const ci = j % cols, ri = Math.floor(j / cols);
        const gx = gx0 + ci * s, gy = gy0 + ri * s;
        ctx.fillStyle = "rgba(7,12,17,0.9)"; ctx.fillRect(gx + 1, gy + 1, s - 2, s - 2);
        ctx.strokeStyle = "rgba(53,230,208,0.25)"; ctx.lineWidth = 0.8; ctx.strokeRect(gx + 1, gy + 1, s - 2, s - 2);
        ctx.strokeStyle = "rgba(53,230,208,0.7)"; ctx.lineWidth = 1; ctx.beginPath();
        for (let g = 0; g <= 6; g++) { const gxx = gx + 3 + (g / 6) * (s - 6), gyy = gy + s - 3 - mix(fm, g / 6) / topVal * (s - 6); g ? ctx.lineTo(gxx, gyy) : ctx.moveTo(gxx, gyy); }
        ctx.stroke();
      }

      const cnt = Math.round(this._ease(Math.min(1, tc / 1.8)) * 4.7);
      ctx.font = "13px 'IBM Plex Mono', monospace"; ctx.save(); ctx.textAlign = "center";
      ctx.fillStyle = "rgba(124,255,155,0.95)";
      ctx.fillText(`${cnt.toFixed(1)} M profiles`, w / 2, gy0 + rows * s + 22);
      ctx.restore();
      caption = "This runs independently for every azimuth × range pixel  ·  millions of profiles  ·  output (3·K_max, Az, R)";
    }

    if (model) {
      model.forEach((p) => {
        this._curvePath([p], mix, px, py);
        ctx.strokeStyle = "rgba(53,230,208,0.28)"; ctx.lineWidth = 1; ctx.stroke();
      });
      this._curvePath(model, mix, px, py);
      if (modelDashed) ctx.setLineDash([7, 6]);
      ctx.strokeStyle = "#35e6d0"; ctx.lineWidth = 2.4; ctx.shadowColor = "rgba(53,230,208,0.6)"; ctx.shadowBlur = 8;
      ctx.stroke(); ctx.shadowBlur = 0; ctx.setLineDash([]);
    }
    drawChart(done, highlight, tt >= FITS0 && tt < SEL0);
    if (model && iter) {
      this._cap(caption + `   step ${iter} / 3000  ·  Adam (lr 0.2, β₁ 0.95)  ·  loss ↓`);
    } else {
      this._cap(caption);
    }
  }

  _paramHeatTile(x, y, s, r2) {
    const ctx = this.ctx;
    const v = Math.min(1, Math.max(0, (r2 - 0.5) / 0.5));
    let col;
    if (r2 < 0.5) col = "rgba(255,107,125,0.8)";
    else if (v < 0.6) col = "rgba(255,207,107,0.8)";
    else col = "rgba(124,255,155,0.8)";
    ctx.fillStyle = col; ctx.fillRect(x, y, s, s);
    ctx.strokeStyle = "rgba(4,7,10,0.6)"; ctx.lineWidth = 1; ctx.strokeRect(x, y, s, s);
  }

  /* ---------- processing: SLC stack -> interferogram layers -> DEM deramp -> Capon tomogram ---------- */

  _prSetup() {
    if (this._pr) return this._pr;

    const N = 5;
    const B = [0, 8, 16, 24, 32];
    const KZ = B.map((b) => b * 0.0075);
    const ZMIN = -20, ZMAX = 80, NZ = 220;
    const FRV = 1.05;

    const c01 = (v) => Math.min(1, Math.max(0, v));
    const frac = (v) => v - Math.floor(v);
    const rnd = (i) => frac(Math.sin(i * 127.1 + 311.7) * 43758.5453);
    const lp = (a, b, p) => a + (b - a) * p;

    const dem = (x) => 14 * Math.exp(-((x - 0.6) ** 2) / 0.045) + 8 * x - 3;
    const vegP = (x, y) => c01(0.55 * Math.sin(x * 9.3 + 1.7) + 0.45 * Math.sin(x * 21.1 + y * 5.3 + 0.4) + 0.35 * Math.sin(y * 7.9 + x * 13.7 + 0.6));
    const veg = (x, y) => 17 * vegP(x, y);
    const demR = (x, y) => -2 + 16 * x + 8 * y;
    const hgtR = (x, y) => demR(x, y) + 0.55 * veg(x, y);
    const wrap = (p) => p - 6.2832 * Math.round(p / 6.2832);
    const psi = (i, j) => rnd(i * 131 + j * 71) * 6.2832;
    const phCol = (phi, a) => {
      const s = 0.5 + 0.5 * Math.sin(phi);
      return `rgba(${Math.round(lp(48, 255, s))},${Math.round(lp(212, 207, s))},${Math.round(lp(196, 107, s))},${a})`;
    };

    const cmul = (a, b) => [a[0] * b[0] - a[1] * b[1], a[0] * b[1] + a[1] * b[0]];
    const cadd = (a, b) => [a[0] + b[0], a[1] + b[1]];
    const cconj = (a) => [a[0], -a[1]];
    const steer = (z) => KZ.map((k) => [Math.cos(k * z), Math.sin(k * z)]);
    const buildR = (sources, s2) => {
      const M = Array.from({ length: N }, () => Array.from({ length: N }, () => [0, 0]));
      sources.forEach((s) => {
        const a = steer(s.z);
        for (let i = 0; i < N; i++) for (let j = 0; j < N; j++) M[i][j] = cadd(M[i][j], cmul([s.p, 0], cmul(a[i], cconj(a[j]))));
      });
      for (let i = 0; i < N; i++) M[i][i] = cadd(M[i][i], [s2, 0]);
      return M;
    };
    const cinv = (M) => {
      const n = M.length;
      const A = M.map((row, i) => row.map((cv) => [cv[0], cv[1]]).concat(Array.from({ length: n }, (_, j) => [i === j ? 1 : 0, 0])));
      for (let col = 0; col < n; col++) {
        let piv = col;
        for (let r = col + 1; r < n; r++) if (Math.hypot(A[r][col][0], A[r][col][1]) > Math.hypot(A[piv][col][0], A[piv][col][1])) piv = r;
        const tmp = A[col]; A[col] = A[piv]; A[piv] = tmp;
        const dv = A[col][col], den = dv[0] * dv[0] + dv[1] * dv[1];
        for (let j = 0; j < 2 * n; j++) {
          const v = A[col][j];
          A[col][j] = [(v[0] * dv[0] + v[1] * dv[1]) / den, (v[1] * dv[0] - v[0] * dv[1]) / den];
        }
        for (let r = 0; r < n; r++) {
          if (r === col) continue;
          const f = A[r][col];
          if (!f[0] && !f[1]) continue;
          for (let j = 0; j < 2 * n; j++) A[r][j] = cadd(A[r][j], cmul([-f[0], -f[1]], A[col][j]));
        }
      }
      return A.map((row) => row.slice(n));
    };
    const quad = (Mi, a) => {
      let s = [0, 0];
      for (let i = 0; i < N; i++) for (let j = 0; j < N; j++) s = cadd(s, cmul(cconj(a[i]), cmul(Mi[i][j], a[j])));
      return Math.max(s[0], 1e-9);
    };

    const R = buildR([{ z: 0, p: 1.0 }, { z: 18, p: 0.55 }], 0.06);
    const Ri = cinv(R);
    const capS = [], bartS = [];
    for (let zi = 0; zi < NZ; zi++) {
      const z = ZMIN + (zi / (NZ - 1)) * (ZMAX - ZMIN);
      const a = steer(z);
      capS.push(1 / quad(Ri, a));
      bartS.push(quad(R, a) / (N * N));
    }
    const capM = Math.max(...capS), bartM = Math.max(...bartS);
    for (let zi = 0; zi < NZ; zi++) { capS[zi] /= capM; bartS[zi] /= bartM; }

    const Rmax = Math.hypot(R[0][0][0], R[0][0][1]);
    const Rmag = R.map((row) => row.map((cv) => Math.hypot(cv[0], cv[1]) / Rmax));
    const Rrow = R[0].map((cv) => -Math.atan2(cv[1], cv[0]));

    const TC = 96, TZ = 110;
    const buildTomoCv = (sub) => {
      const sel = sub || [0, 1, 2, 3, 4];
      const ns = sel.length;
      const subSteer = (z) => sel.map((k) => [Math.cos(KZ[k] * z), Math.sin(KZ[k] * z)]);
      const subR = (sources, s2) => {
        const M = Array.from({ length: ns }, () => Array.from({ length: ns }, () => [0, 0]));
        sources.forEach((s) => {
          const a = subSteer(s.z);
          for (let i = 0; i < ns; i++) for (let j = 0; j < ns; j++) M[i][j] = cadd(M[i][j], cmul([s.p, 0], cmul(a[i], cconj(a[j]))));
        });
        for (let i = 0; i < ns; i++) M[i][i] = cadd(M[i][i], [s2, 0]);
        return M;
      };
      const subQuad = (Mi, a) => {
        let s = [0, 0];
        for (let i = 0; i < ns; i++) for (let j = 0; j < ns; j++) s = cadd(s, cmul(cconj(a[i]), cmul(Mi[i][j], a[j])));
        return Math.max(s[0], 1e-9);
      };
      const tomo = [];
      let tmax = 0;
      for (let ci = 0; ci < TC; ci++) {
        const x = ci / (TC - 1);
        const vg = veg(x, 0.5);
        const src = [{ z: dem(x), p: 0.85 + 0.3 * rnd(ci * 3.7) }];
        if (vg > 5) src.push({ z: dem(x) + vg, p: 0.45 + 0.3 * vegP(x, 0.5) });
        const Rc = cinv(subR(src, 0.07));
        const col = [];
        for (let zi = 0; zi < TZ; zi++) {
          const z = ZMIN + (zi / (TZ - 1)) * (ZMAX - ZMIN);
          const p = 1 / subQuad(Rc, subSteer(z));
          col.push(p);
          if (p > tmax) tmax = p;
        }
        tomo.push(col);
      }
      const cv = document.createElement("canvas");
      cv.width = TC; cv.height = TZ;
      const tctx = cv.getContext("2d");
      const img = tctx.createImageData(TC, TZ);
      for (let ci = 0; ci < TC; ci++) {
        for (let zi = 0; zi < TZ; zi++) {
          const v = Math.pow(tomo[ci][zi] / tmax, 0.6);
          const o = ((TZ - 1 - zi) * TC + ci) * 4;
          img.data[o] = 53; img.data[o + 1] = 230; img.data[o + 2] = 208;
          img.data[o + 3] = Math.round(235 * v);
        }
      }
      tctx.putImageData(img, 0, 0);
      return cv;
    };
    const tomoCv        = buildTomoCv([0, 1, 2, 3, 4]);
    const tomoCvReduced = buildTomoCv([0, 2, 4]);

    this._pr = { N, B, KZ, ZMIN, ZMAX, NZ, FRV, c01, rnd, dem, vegP, veg, demR, hgtR, wrap, psi, phCol, steer, capS, bartS, Rmag, Rrow, TC, TZ, tomoCv, tomoCvReduced };
    return this._pr;
  }

  _prSheet(x, y, wpx, hpx, shear, cell, fn, alpha, border) {
    const { ctx } = this;
    ctx.save();
    ctx.globalAlpha = alpha;
    ctx.translate(x, y);
    ctx.transform(1, -0.10 * shear, 0.62 * shear, 1 - 0.52 * shear, 0, 0);
    const nx = Math.max(1, Math.round(wpx / cell)), ny = Math.max(1, Math.round(hpx / cell));
    for (let j = 0; j < ny; j++) {
      for (let i = 0; i < nx; i++) {
        ctx.fillStyle = fn(i, j, nx, ny);
        ctx.fillRect(i * cell, j * cell, cell - 1, cell - 1);
      }
    }
    ctx.strokeStyle = border; ctx.lineWidth = 1.3;
    ctx.strokeRect(-1, -1, nx * cell + 1, ny * cell + 1);
    ctx.restore();
  }

  _prChip(txt, x, y, color, alpha) {
    const { ctx } = this;
    ctx.font = "14px 'IBM Plex Mono', monospace";
    const tw = ctx.measureText(txt).width + 24;
    if (alpha <= 0) return tw;
    ctx.save(); ctx.globalAlpha = alpha;
    ctx.fillStyle = "rgba(7,12,17,0.94)"; ctx.strokeStyle = color; ctx.lineWidth = 1.2;
    ctx.beginPath();
    if (ctx.roundRect) ctx.roundRect(x, y - 18, tw, 28, 7); else ctx.rect(x, y - 18, tw, 28);
    ctx.fill(); ctx.stroke();
    ctx.fillStyle = color; ctx.fillText(txt, x + 12, y + 2);
    ctx.restore();
    return tw;
  }

  _prLand(x, y, wpx, hpx, amp, zfn, cfn, alpha, border) {
    const { ctx } = this;
    if (alpha <= 0) return;
    const NXL = 40, NYL = 16;
    const skew = Math.min(26, wpx * 0.08);
    const dx = (wpx - skew) / NXL;
    const rowH = hpx / NYL;
    ctx.save();
    ctx.globalAlpha = alpha;
    for (let j = 0; j <= NYL; j++) {
      const v = j / NYL;
      const xr = x + skew * (1 - v);
      const yr = y + j * rowH;
      const pts = [];
      for (let i = 0; i <= NXL; i++) pts.push([xr + i * dx, yr - amp * zfn(i / NXL, v)]);
      ctx.beginPath();
      ctx.moveTo(pts[0][0], pts[0][1]);
      for (let i = 1; i <= NXL; i++) ctx.lineTo(pts[i][0], pts[i][1]);
      ctx.lineTo(pts[NXL][0], yr + rowH * 1.7);
      ctx.lineTo(pts[0][0], yr + rowH * 1.7);
      ctx.closePath();
      ctx.fillStyle = "rgba(4,7,10,0.93)";
      ctx.fill();
      ctx.lineWidth = 1.4;
      for (let i = 0; i < NXL; i++) {
        ctx.strokeStyle = cfn(i / NXL, v);
        ctx.beginPath();
        ctx.moveTo(pts[i][0], pts[i][1]);
        ctx.lineTo(pts[i + 1][0], pts[i + 1][1]);
        ctx.stroke();
      }
    }
    if (border) {
      ctx.strokeStyle = border; ctx.lineWidth = 1.2;
      ctx.beginPath();
      ctx.moveTo(x + skew, y);
      ctx.lineTo(x, y + hpx);
      ctx.lineTo(x + wpx - skew, y + hpx);
      ctx.lineTo(x + wpx, y);
      ctx.stroke();
    }
    ctx.restore();
  }

  _prPlate(x, y, txt, color) {
    const { ctx } = this;
    ctx.font = "14px 'IBM Plex Mono', monospace";
    const tw = ctx.measureText(txt).width;
    ctx.fillStyle = "rgba(7,12,17,0.92)";
    ctx.strokeStyle = "rgba(120,200,220,0.30)"; ctx.lineWidth = 1.1;
    ctx.beginPath();
    if (ctx.roundRect) ctx.roundRect(x - 12, y - 16, tw + 24, 31, 7); else ctx.rect(x - 12, y - 16, tw + 24, 31);
    ctx.fill(); ctx.stroke();
    ctx.fillStyle = color;
    ctx.fillText(txt, x, y + 5);
    return tw;
  }

  _processing() { this._dispatch("processing", this._prSetup()); }

  _prGeo(ts, d) {
    const { ctx, w, h } = this;
    const c01 = d.c01;

    const gL = 64, gR = w * 0.52;
    const gy0 = h - 64;
    const hs = (h * 0.26) / 40;
    const gy = (x) => gy0 - (d.dem(x) + 5) * hs;

    const tA = this._ease(c01(ts / 1.2));
    ctx.beginPath();
    ctx.moveTo(gL, gy0 + 20);
    for (let i = 0; i <= 90; i++) { const x = i / 90; ctx.lineTo(gL + x * (gR - gL), gy(x)); }
    ctx.lineTo(gR, gy0 + 20); ctx.closePath();
    ctx.fillStyle = `rgba(53,230,208,${0.07 * tA})`; ctx.fill();
    ctx.beginPath();
    for (let i = 0; i <= 90; i++) { const x = i / 90, X = gL + x * (gR - gL), Y = gy(x); i ? ctx.lineTo(X, Y) : ctx.moveTo(X, Y); }
    ctx.strokeStyle = `rgba(170,196,200,${0.8 * tA})`; ctx.lineWidth = 1.4; ctx.stroke();

    for (let i = 0; i <= 46; i++) {
      const x = i / 46;
      const v = d.vegP(x, 0.5);
      if (v < 0.45) continue;
      const X = gL + x * (gR - gL);
      const yG = gy(x), yT = yG - d.veg(x, 0.5) * hs;
      ctx.strokeStyle = `rgba(124,255,155,${0.45 * tA})`; ctx.lineWidth = 1.2;
      ctx.beginPath(); ctx.moveTo(X, yG); ctx.lineTo(X, yT + 7); ctx.stroke();
      ctx.fillStyle = `rgba(124,255,155,${(0.22 + 0.3 * v) * tA})`;
      ctx.beginPath(); ctx.moveTo(X, yT); ctx.lineTo(X - 4.5, yT + 11); ctx.lineTo(X + 4.5, yT + 11); ctx.closePath(); ctx.fill();
    }
    ctx.fillStyle = `rgba(206,229,223,${0.9 * tA})`; ctx.font = "13px 'IBM Plex Mono', monospace";
    ctx.fillText("range ->", gR - 64, gy0 + 16);

    const ladX = gL + 16;
    const plY = (i) => h * 0.26 + (d.N - 1 - i) * 23;
    const flightP = c01((ts - 1.6) / 6.5);
    const fx0 = gL + 296, fx1 = gR - 18;
    const plX = (i) => fx0 + flightP * (fx1 - fx0) - i * 13;

    for (let i = 0; i < d.N; i++) {
      const ap = this._ease(c01((ts - 0.6 - i * 0.35) / 0.5));
      if (ap <= 0) continue;
      ctx.save(); ctx.globalAlpha = ap;
      ctx.strokeStyle = "rgba(255,207,107,0.7)"; ctx.lineWidth = 1.2;
      ctx.beginPath(); ctx.moveTo(ladX, plY(i) - 5); ctx.lineTo(ladX, plY(i) + 5); ctx.stroke();
      ctx.font = "13px 'IBM Plex Mono', monospace";
      ctx.fillStyle = i === 0 ? "#35e6d0" : "rgba(214,234,229,0.95)";
      ctx.fillText(i === 0 ? "s0 · primary" : `s${i} · secondary track`, ladX + 10, plY(i) + 4);
      ctx.restore();
    }
    if (ts >= 2.6) {
      const ba = this._ease(c01((ts - 2.6) / 0.7));
      ctx.save(); ctx.globalAlpha = ba;
      ctx.strokeStyle = "rgba(255,207,107,0.7)"; ctx.lineWidth = 1.2;
      ctx.beginPath(); ctx.moveTo(ladX - 8, plY(0)); ctx.lineTo(ladX - 8, plY(d.N - 1)); ctx.stroke();
      ctx.fillStyle = "rgba(255,207,107,0.95)"; ctx.font = "12px 'IBM Plex Mono', monospace";
      const blbl = "baseline ↑";
      const blw = ctx.measureText(blbl).width;
      ctx.save(); ctx.translate(ladX - 14, (plY(0) + plY(d.N - 1)) / 2 + blw / 2); ctx.rotate(-Math.PI / 2); ctx.fillText(blbl, 0, 0); ctx.restore();
      ctx.restore();
    }

    if (ts >= 1.6 && flightP < 1) {
      const aa = this._ease(c01((ts - 1.6) / 0.6));
      ctx.save(); ctx.globalAlpha = aa;
      ctx.strokeStyle = "rgba(124,255,155,0.8)"; ctx.fillStyle = "rgba(124,255,155,0.9)";
      ctx.lineWidth = 1.4;
      const ay0 = h * 0.26 - 32;
      const arrX = gL + 168;
      ctx.beginPath(); ctx.moveTo(arrX - 6, ay0); ctx.lineTo(arrX + 110, ay0); ctx.stroke();
      ctx.beginPath(); ctx.moveTo(arrX + 110, ay0); ctx.lineTo(arrX + 102, ay0 - 4); ctx.lineTo(arrX + 102, ay0 + 4); ctx.closePath(); ctx.fill();
      ctx.font = "13px 'IBM Plex Mono', monospace";
      ctx.fillText("flight · azimuth", arrX + 120, ay0 + 4);
      ctx.restore();
    }

    for (let i = 0; i < d.N; i++) {
      const ap = this._ease(c01((ts - 0.6 - i * 0.35) / 0.5));
      if (ap <= 0) continue;
      const X = plX(i), Y = plY(i);
      if (flightP > 0 && flightP < 1) {
        for (let q = 0; q < 2; q++) {
          const pp = (this.t * 0.8 + i * 0.23 + q * 0.5) % 1;
          const rr = pp * 120;
          ctx.strokeStyle = `rgba(53,230,208,${0.55 * (1 - pp) * ap})`;
          ctx.lineWidth = 1.5;
          ctx.beginPath(); ctx.arc(X, Y, rr, Math.PI * 0.10, Math.PI * 0.52); ctx.stroke();
        }
      }
      ctx.save(); ctx.globalAlpha = ap;
      for (let q = 1; q <= 3; q++) {
        ctx.fillStyle = `rgba(150,200,210,${0.35 - q * 0.09})`;
        ctx.fillRect(X - 12 - q * 9, Y - 1, 5, 2);
      }
      ctx.fillStyle = i === 0 ? "#35e6d0" : "rgba(200,222,226,0.95)";
      ctx.beginPath();
      ctx.moveTo(X + 10, Y); ctx.lineTo(X - 7, Y - 4.5); ctx.lineTo(X - 2.5, Y); ctx.lineTo(X - 7, Y + 4.5);
      ctx.closePath(); ctx.fill();
      ctx.restore();
    }

    const shW = Math.min(330, w * 0.28), shH = Math.min(170, h * 0.32);
    const stX = w * 0.56;
    const stY = Math.max(36, h * 0.5 - (shH * 1.68 + 56) / 2);
    const dyS = shH * 0.30;
    for (let i = d.N - 1; i >= 0; i--) {
      const ap = this._ease(c01((ts - 1.8 - i * 0.25) / 0.6));
      if (ap <= 0) continue;
      const reg = i === 0 ? 1 : this._ease(c01((ts - 8.4 - i * 0.35) / 0.8));
      const ox = i === 0 ? 0 : (d.rnd(i * 17.3) * 2 - 1) * 30 * (1 - reg);
      const oy = i === 0 ? 0 : (d.rnd(i * 31.7) * 2 - 1) * 9 * (1 - reg);
      const y = stY + (d.N - 1 - i) * dyS;
      this._prSheet(stX + ox, y + oy, shW, shH, 1, 9, (ii, jj, nx) => {
        if (ii > flightP * nx) return "rgba(120,200,220,0.05)";
        if (flightP < 1 && ii === Math.floor(flightP * nx)) return "rgba(230,247,243,0.9)";
        return d.phCol(d.psi(ii + i * 57, jj + i * 13), 0.8);
      }, ap, i === 0 ? "rgba(53,230,208,0.9)" : "rgba(120,200,220,0.45)");
      if (ap > 0.5) {
        ctx.save(); ctx.globalAlpha = ap;
        ctx.font = "13px 'IBM Plex Mono', monospace";
        ctx.fillStyle = i === 0 ? "#35e6d0" : "rgba(214,234,229,0.95)";
        ctx.fillText("s" + i, stX + ox + shW + 0.62 * shH * 0.48 + 10, y + oy + shH * 0.24 + 4);
        if (i > 0 && reg >= 1 && ts < 11.2) {
          ctx.fillStyle = "#7cff9b";
          ctx.fillText("✓", stX + shW + 0.62 * shH * 0.48 + 38, y + shH * 0.24 + 4);
        }
        ctx.restore();
      }
    }
    if (ts >= 10.2) {
      const ch1 = "full stack -> ground truth";
      const ch2 = "full stack -> model inputs";
      ctx.font = "14px 'IBM Plex Mono', monospace";
      const chW = Math.max(ctx.measureText(ch1).width, ctx.measureText(ch2).width) + 24;
      const chx = Math.min(stX + 6, w - chW - 14);
      const chy = stY + (d.N - 1) * dyS + shH * 0.48 + 38;
      this._prChip(ch1, chx, chy, "#ffcf6b", c01((ts - 10.2) / 0.6));
      this._prChip(ch2, chx, chy + 38, "#35e6d0", c01((ts - 10.9) / 0.6));
    }

    let cap;
    if (ts < 1.6) cap = "Pipeline order: full-stack tomogram FIRST  ·  interferograms LAST  ·  here we follow that execution order";
    else if (ts < 4.8) cap = "Upstream of this pipeline: F-SAR focuses & co-registers the SLCs  ·  we start from the finished stack";
    else if (ts < 8.2) cap = "Several passes on vertically offset tracks (5 drawn, illustrative)  ·  same scene, different phase patterns";
    else if (ts < 10.8) cap = "Co-registration is done upstream  ·  each secondary already sits on the primary pixel grid";
    else cap = "full stack -> ground-truth tomogram AND model inputs  ·  secondaries selected later at training  ·  phase carries the height";
    this._cap(cap);
  }

  _prIfg(ts, d) {
    const { ctx, w, h } = this;
    const c01 = d.c01;

    const layW = Math.min(460, w * 0.345), layH = Math.min(170, h * 0.31);
    const yLay = h * 0.49;
    const xL0 = w * 0.15, xR0 = w * 0.85 - layW;
    const xC = w / 2 - layW / 2;
    const ampS = 7.2, ampR = 1.25;
    const FAST0 = 16.4, FASTD = 1.8;

    const zS = (k) => (u, v) => d.wrap(d.psi(Math.round(u * 40), Math.round(v * 18) + 100) + k * (2.4 + d.FRV * d.hgtR(u, v))) + Math.PI;
    const cSp = (zfn) => (u, v) => d.phCol(zfn(u, v) - Math.PI, 0.9);
    const zR = (u, v) => 2.4 + d.FRV * d.hgtR(u, v);
    const cR = (k) => (u, v) => d.phCol(-k * zR(u, v), 0.95);
    const conjF = ts < 6.6 ? 0 : ts < 7.6 ? this._ease(c01((ts - 6.6) / 1.0)) : 1;
    const zS1 = (u, v) => d.wrap((d.psi(Math.round(u * 40), Math.round(v * 18) + 100) + 2.4 + d.FRV * d.hgtR(u, v)) * (1 - 2 * conjF)) + Math.PI;

    const msW = 110, msH = 56, msX = 46, msY = 64, msDy = 19;
    const goneT = [0.3, 0.9, FAST0, FAST0 + FASTD, FAST0 + 2 * FASTD];
    for (let i = d.N - 1; i >= 0; i--) {
      const slotY = msY + (d.N - 1 - i) * msDy;
      if (ts < goneT[i]) {
        this._prSheet(msX, slotY, msW, msH, 1, 10, (ii, jj) => d.phCol(d.psi(ii + i * 57, jj + i * 13), 0.7), 0.55, "rgba(120,200,220,0.35)");
      } else {
        ctx.save();
        ctx.translate(msX, slotY);
        ctx.transform(1, -0.10, 0.62, 0.48, 0, 0);
        ctx.strokeStyle = "rgba(120,200,220,0.25)"; ctx.setLineDash([4, 4]); ctx.lineWidth = 1;
        ctx.strokeRect(0, 0, msW, msH);
        ctx.setLineDash([]); ctx.restore();
      }
    }
    ctx.font = "13px 'IBM Plex Mono', monospace";
    ctx.fillStyle = "rgba(206,229,223,0.7)";
    ctx.fillText("SLC stack", msX, msY + (d.N - 1) * msDy + msH * 0.48 + 24);

    const p0 = this._ease(c01((ts - 0.3) / 1.4));
    const p1 = this._ease(c01((ts - 0.9) / 1.4));
    const rise = this._ease(c01((ts - 2.5) / 1.5));
    const sp = this._ease(c01((ts - 9.7) / 3.0));
    const xL = this._lerp(this._lerp(msX, xL0, p0), xC, sp);
    const xR = this._lerp(this._lerp(msX, xR0, p1), xC, sp);
    const merged = ts >= 12.7;

    const srcA = merged ? Math.max(0, 1 - (ts - 12.7) / 0.6) : 1;
    if (srcA > 0) {
      const drawOne = (p, x, k, clip, zfn) => {
        if (p <= 0) return;
        const Y = this._lerp(msY + (d.N - 1 - k) * msDy, yLay, p);
        const W = this._lerp(msW, layW, p), H = this._lerp(msH, layH, p);
        if (p < 1) {
          this._prSheet(x, Y, W, H, 1 - p, 8, (i, j, mx, my) => d.phCol(zfn(i / mx, j / my) - Math.PI, 0.8), srcA, "rgba(120,200,220,0.55)");
          return;
        }
        ctx.save();
        if (clip) { ctx.beginPath(); ctx.rect(clip[0], 0, clip[1] - clip[0], h); ctx.clip(); }
        if (rise < 1) this._prSheet(x, Y, W, H, 0, 8, (i, j, mx, my) => d.phCol(zfn(i / mx, j / my) - Math.PI, 0.8), srcA * (1 - rise), "rgba(120,200,220,0.4)");
        if (rise > 0) this._prLand(x, Y, W, H, ampS * rise, zfn, cSp(zfn), srcA, k === 0 ? "rgba(53,230,208,0.55)" : "rgba(120,200,220,0.45)");
        ctx.restore();
      };
      drawOne(p0, xL, 0, sp > 0 ? [0, Math.max(xR, xC)] : null, zS(0));
      drawOne(p1, xR, 1, sp > 0 ? [Math.min(xL + layW, xC + layW), w] : null, zS1);
      if (rise >= 1 && ts < 9.7) {
        this._prPlate(xL0 + 12, yLay + layH + 34, "arg(s₀) · primary", "#35e6d0");
        this._prPlate(xR0 + 12, yLay + layH + 34, conjF > 0.5 ? "arg(s₁*) · conjugated" : "arg(s₁) · secondary", conjF > 0.5 ? "#ffcf6b" : "rgba(206,229,223,0.95)");
      }
    }

    if (sp > 0 && ts < 15.5) {
      const ox0 = Math.max(xR, xC), ox1 = Math.min(xL + layW, xC + layW);
      if (ox1 > ox0 + 2) {
        ctx.save();
        ctx.beginPath(); ctx.rect(ox0, 0, ox1 - ox0, h); ctx.clip();
        this._prLand(xC, yLay, layW, layH, ampR, zR, cR(1), 1, "rgba(124,255,155,0.6)");
        ctx.restore();
        if (sp < 1) {
          for (let k = 0; k < 14; k++) {
            const yy = yLay - 34 + d.rnd(k * 9.1 + Math.floor(this.t * 8)) * (layH + 54);
            const ee = k % 2 ? ox0 : ox1;
            ctx.fillStyle = `rgba(230,247,243,${0.5 + 0.4 * Math.sin(this.t * 11 + k)})`;
            ctx.fillRect(ee - 1, yy, 3, 3);
          }
        }
      }
      if (merged) {
        const mqa = Math.min(1, (ts - 12.7) / 0.6);
        const eqB = this._texDraw("\\Delta\\varphi=\\arg(s_0 s_1^{*})\\propto k_z\\xi", xC + 12, yLay + layH + 22, 15, { color: "#7cff9b", alpha: mqa });
        ctx.save(); ctx.globalAlpha = mqa * 0.85;
        ctx.font = "12px 'IBM Plex Mono', monospace"; ctx.fillStyle = "rgba(206,229,223,0.9)";
        ctx.fillText("random phase cancels, the height term survives", xC + 12 + (eqB ? eqB.w + 16 : 210), yLay + layH + 42);
        ctx.restore();
      }
    }

    const slotW = Math.min(170, w / 6.4), slotH = 50;
    const ampT = ampR * (slotW / layW);
    const slotX = (q) => w - slotW - 185;
    const slotY = (q) => Math.max(40, h * 0.5 - 178) + q * 92;
    const drawIfgAt = (k, x, y, W, H, amp, alpha) => this._prLand(x, y, W, H, amp, zR, cR(k), alpha, "rgba(124,255,155,0.5)");
    const landedAt = (k) => (k === 1 ? FAST0 : FAST0 + (k - 1) * FASTD);

    if (ts >= 15.6) {
      for (let q = 0; q < 4; q++) {
        if (ts >= landedAt(q + 1)) continue;
        ctx.strokeStyle = "rgba(120,200,220,0.3)"; ctx.setLineDash([5, 5]); ctx.lineWidth = 1;
        ctx.strokeRect(slotX(q), slotY(q), slotW, slotH);
        ctx.setLineDash([]);
      }
    }
    for (let k = 1; k <= 4; k++) {
      if (ts < landedAt(k)) continue;
      drawIfgAt(k, slotX(k - 1), slotY(k - 1), slotW, slotH, ampT, 1);
      ctx.font = "13px 'IBM Plex Mono', monospace";
      ctx.fillStyle = "rgba(230,247,243,0.9)";
      ctx.fillText(`ifg ${k} · long baseline`, slotX(k - 1) + slotW + 14, slotY(k - 1) + slotH / 2 + 5);
    }
    if (ts >= 15.5 && ts < FAST0) {
      const p = this._ease((ts - 15.5) / 0.9);
      drawIfgAt(1, this._lerp(xC, slotX(0), p), this._lerp(yLay, slotY(0), p), this._lerp(layW, slotW, p), this._lerp(layH, slotH, p), this._lerp(ampR, ampT, p), 1);
    }

    if (ts >= FAST0 && ts < FAST0 + 3 * FASTD) {
      const k = Math.min(4, 2 + Math.floor((ts - FAST0) / FASTD));
      const tk = ts - FAST0 - (k - 2) * FASTD;
      const Wm = Math.min(290, layW * 0.74), Hm = layH * 0.72;
      const xM = w / 2 - Wm / 2, yM = yLay + 10;
      const ampSm = ampS * (Wm / layW), ampRm = ampR * (Wm / layW);
      if (tk < 1.2) {
        const mp = this._ease(c01(tk / 0.75));
        const off = (1 - mp) * (Wm * 0.78 + 30);
        const xls = xM - off, xrs = xM + off;
        const o0 = Math.max(xrs, xM), o1 = Math.min(xls + Wm, xM + Wm);
        const sA2 = tk < 0.85 ? 1 : Math.max(0, 1 - (tk - 0.85) / 0.3);
        if (sA2 > 0) {
          ctx.save(); ctx.beginPath(); ctx.rect(0, 0, o0, h); ctx.clip();
          this._prLand(xls, yM, Wm, Hm, ampSm, zS(0), cSp(zS(0)), sA2, "rgba(53,230,208,0.5)");
          ctx.restore();
          ctx.save(); ctx.beginPath(); ctx.rect(o1, 0, w - o1, h); ctx.clip();
          this._prLand(xrs, yM, Wm, Hm, ampSm, zS(k), cSp(zS(k)), sA2, "rgba(120,200,220,0.45)");
          ctx.restore();
        }
        if (o1 > o0 + 2) {
          ctx.save(); ctx.beginPath(); ctx.rect(o0, 0, o1 - o0, h); ctx.clip();
          drawIfgAt(k, xM, yM, Wm, Hm, ampRm, 1);
          ctx.restore();
        }
        this._prPlate(xM + 12, yM - ampSm * 6.6 - 18, `s₀·s${["", "₁", "₂", "₃", "₄"][k]}*  ·  longer baseline`, "#35e6d0");
      } else {
        const p = this._ease(c01((tk - 1.2) / 0.55));
        drawIfgAt(k, this._lerp(xM, slotX(k - 1), p), this._lerp(yM, slotY(k - 1), p), this._lerp(Wm, slotW, p), this._lerp(Hm, slotH, p), this._lerp(ampRm, ampT, p), 1);
      }
    }

    if (ts >= 5.2 && ts < 13.8) {
      const tp = ts - 5.2;
      const ia = this._ease(c01(tp / 0.6)) * this._ease(c01((13.8 - ts) / 0.6));
      const u0 = 0.62, v0 = 0.44;
      const lsk = Math.min(26, layW * 0.08);
      const a0 = zS(0)(u0, v0) - Math.PI;
      const a1 = zS(1)(u0, v0) - Math.PI;
      const mergeP = sp;
      const conjP = this._ease(c01((tp - 1.4) / 1.0));
      const angB = this._lerp(a1, -a1, conjP);

      const icW = Math.min(500, w * 0.46), icH = 142;
      const icX = w / 2 - icW / 2, icY = 22;
      const ancX = (xx) => xx + lsk * (1 - v0) + u0 * (layW - lsk);

      const ring = (X, Y, al) => {
        ctx.save(); ctx.globalAlpha = ia * al;
        ctx.strokeStyle = "#ffcf6b"; ctx.lineWidth = 1.6;
        ctx.beginPath(); ctx.arc(X, Y, 7 + Math.sin(this.t * 5) * 1.5, 0, 7); ctx.stroke();
        ctx.restore();
      };
      const conn = (X, Y, fx2, al) => {
        ctx.save(); ctx.globalAlpha = ia * al;
        ctx.strokeStyle = "rgba(255,207,107,0.35)"; ctx.setLineDash([3, 4]); ctx.lineWidth = 1;
        ctx.beginPath(); ctx.moveTo(X, Y - 9); ctx.lineTo(icX + icW * fx2, icY + icH); ctx.stroke();
        ctx.setLineDash([]); ctx.restore();
      };
      if (srcA > 0.05) {
        const pxA = ancX(xL), pyA = yLay + v0 * layH - ampS * zS(0)(u0, v0);
        const pxB = ancX(xR), pyB = yLay + v0 * layH - ampS * zS1(u0, v0);
        ring(pxA, pyA, srcA); ring(pxB, pyB, srcA);
        conn(pxA, pyA, this._lerp(0.32, 0.5, mergeP), srcA);
        conn(pxB, pyB, this._lerp(0.68, 0.5, mergeP), srcA);
      }
      if (merged) {
        const mra = Math.min(1, (ts - 12.7) / 0.6);
        const pxR = ancX(xC), pyR = yLay + v0 * layH - ampR * zR(u0, v0);
        ring(pxR, pyR, mra);
        conn(pxR, pyR, 0.5, mra);
      }

      ctx.save(); ctx.globalAlpha = ia;
      ctx.fillStyle = "rgba(4,7,10,0.92)";
      ctx.strokeStyle = "rgba(120,200,220,0.3)"; ctx.lineWidth = 1.2;
      ctx.beginPath();
      if (ctx.roundRect) ctx.roundRect(icX, icY, icW, icH, 9); else ctx.rect(icX, icY, icW, icH);
      ctx.fill(); ctx.stroke();

      const cyc = icY + 74, rr = 33;
      const cxA = this._lerp(icX + icW * 0.30, icX + icW * 0.5, mergeP);
      const cxB = this._lerp(icX + icW * 0.70, icX + icW * 0.5, mergeP);

      const circ = (X, lbl, lblCol, la2) => {
        ctx.strokeStyle = "rgba(120,200,220,0.4)"; ctx.lineWidth = 1.2;
        ctx.beginPath(); ctx.arc(X, cyc, rr, 0, 7); ctx.stroke();
        if (la2 == null || la2 > 0.03) {
          ctx.save();
          if (la2 != null) ctx.globalAlpha = ctx.globalAlpha * la2;
          ctx.font = "15px 'IBM Plex Mono', monospace";
          ctx.fillStyle = lblCol;
          ctx.fillText(lbl, X - ctx.measureText(lbl).width / 2, cyc + rr + 20);
          ctx.restore();
        }
      };
      const arr = (X, ang, color, al, dash) => {
        ctx.save(); ctx.globalAlpha = ia * al;
        ctx.strokeStyle = color; ctx.lineWidth = 2;
        if (dash) ctx.setLineDash([3, 3]);
        ctx.beginPath(); ctx.moveTo(X, cyc); ctx.lineTo(X + rr * 0.86 * Math.cos(ang), cyc - rr * 0.86 * Math.sin(ang)); ctx.stroke();
        ctx.setLineDash([]);
        ctx.fillStyle = color;
        ctx.beginPath(); ctx.arc(X + rr * 0.86 * Math.cos(ang), cyc - rr * 0.86 * Math.sin(ang), 3, 0, 7); ctx.fill();
        ctx.restore();
      };

      if (mergeP < 1) {
        circ(cxA, "s₀", "#35e6d0", 1 - mergeP);
        circ(cxB, conjP > 0.5 ? "s₁*" : "s₁", "rgba(206,229,223,0.95)", 1 - mergeP);
        arr(cxA, a0, "#35e6d0", 1 - mergeP, false);
        arr(cxB, angB, "rgba(196,221,215,0.95)", 1 - mergeP, false);
        if (conjP > 0 && conjP < 1) arr(cxB, a1, "rgba(196,221,215,0.5)", 0.5, true);
      } else {
        circ(cxA, "s₀·s₁*", "#7cff9b");
      }
      if (mergeP > 0) arr(icX + icW * 0.5, a0 - a1, "#7cff9b", mergeP, false);
      ctx.font = "14px 'IBM Plex Mono', monospace";
      ctx.fillStyle = "rgba(230,247,243,0.9)";
      const ft = tp < 1.4 ? "two phasors · angles φ₀ and φ₁" : tp < 2.6 ? "conjugate mirrors the angle:  φ₁ -> −φ₁" : ts < 9.7 ? "ready to multiply · the angles will ADD" : mergeP < 1 ? "merging in sync with the landscapes · φ₀ + (−φ₁)" : "one phasor per pixel · its angle is Δφ = φ₀ − φ₁";
      ctx.fillText(ft, icX + 14, icY + 18);
      ctx.restore();
    }

    const CLIP0 = FAST0 + 3 * FASTD;
    if (ts >= CLIP0 && ts < 28.2) {
      const ca = this._ease(c01((ts - CLIP0) / 0.6)) * this._ease(c01((28.2 - ts) / 0.6));
      const hbW = 300, hbH = 116;
      const hbX = 250, hbY = h * 0.5 - hbH / 2 + 6;
      const baseY = hbY + hbH - 22;
      const nB = 28;
      const clipP = this._ease(c01((ts - CLIP0 - 0.8) / 1.4));
      const clipY = baseY - (hbH - 40) * (1.25 / 1.7);
      ctx.save(); ctx.globalAlpha = ca;
      ctx.fillStyle = "rgba(7,12,17,0.94)";
      ctx.strokeStyle = "rgba(120,200,220,0.3)"; ctx.lineWidth = 1.2;
      ctx.beginPath();
      if (ctx.roundRect) ctx.roundRect(hbX, hbY, hbW, hbH, 9); else ctx.rect(hbX, hbY, hbW, hbH);
      ctx.fill(); ctx.stroke();
      for (let b = 0; b < nB; b++) {
        const xb = hbX + 18 + b * ((hbW - 36) / nB);
        let amp = 0.4 + 0.55 * Math.abs(Math.sin(b * 1.7 + 0.6) * Math.cos(b * 0.9));
        const spike = d.rnd(b * 3.1) > 0.84;
        if (spike) amp = 1.62;
        const clipped = spike && clipP > 0;
        const drawAmp = clipped ? this._lerp(amp, 1.25, clipP) : amp;
        const bh = (hbH - 40) * (drawAmp / 1.7);
        ctx.fillStyle = clipped ? "rgba(255,107,125,0.85)" : spike ? "rgba(255,207,107,0.85)" : "rgba(53,230,208,0.6)";
        ctx.fillRect(xb, baseY - bh, (hbW - 36) / nB - 2, bh);
      }
      if (clipP > 0) {
        ctx.strokeStyle = "#ffcf6b"; ctx.lineWidth = 1.4; ctx.setLineDash([5, 4]);
        ctx.beginPath(); ctx.moveTo(hbX + 12, clipY); ctx.lineTo(hbX + hbW - 12, clipY); ctx.stroke();
        ctx.setLineDash([]);
        ctx.fillStyle = "#ffcf6b"; ctx.font = "13px 'IBM Plex Mono', monospace";
        ctx.fillText("clip = 1.25", hbX + hbW - 110, clipY - 6);
      }
      ctx.fillStyle = "rgba(214,234,229,0.95)"; ctx.font = "13px 'IBM Plex Mono', monospace";
      ctx.fillText("|secondary| amplitude", hbX + 12, hbY - 8);
      this._texDraw("\\mathrm{ifg}_i=\\frac{A\\,s_0 s_i^{*}}{|s_0 s_i^{*}|}", hbX + hbW / 2, hbY - 64, 16, { align: "center", color: "#7cff9b", alpha: ca });
      if (clipP >= 1) {
        const cbm = this._tex("A=\\mathrm{clip}(|s|,0,1.25)", 15, "#ffcf6b");
        const cbw = cbm.ready ? cbm.w : 150, cbh = cbm.ready ? cbm.h : 28;
        const cby = Math.max(clipY + 18, hbY + hbH * 0.5);
        const cbx = hbX - 20 - cbw;
        ctx.fillStyle = "rgba(7,12,17,0.92)";
        ctx.strokeStyle = "rgba(120,200,220,0.30)"; ctx.lineWidth = 1.1;
        ctx.beginPath();
        if (ctx.roundRect) ctx.roundRect(cbx - 12, cby - cbh / 2 - 6, cbw + 24, cbh + 12, 7); else ctx.rect(cbx - 12, cby - cbh / 2 - 6, cbw + 24, cbh + 12);
        ctx.fill(); ctx.stroke();
        ctx.strokeStyle = "rgba(255,207,107,0.4)"; ctx.setLineDash([4, 4]); ctx.lineWidth = 1;
        ctx.beginPath(); ctx.moveTo(cbx + cbw + 12, cby); ctx.lineTo(hbX, clipY); ctx.stroke(); ctx.setLineDash([]);
        this._texDraw("A=\\mathrm{clip}(|s|,0,1.25)", cbx, cby - cbh / 2 + 4, 15, { color: "#ffcf6b", alpha: ca });
      }
      ctx.restore();
    }

    let cap;
    if (ts < 2.5) cap = "Interferogram formation  ·  pull the primary and one secondary out of the stack";
    else if (ts < 4.6) cap = "Plot each pixel's phase as HEIGHT  ->  a phase landscape  ·  both are jagged speckle, structure invisible";
    else if (ts < 6.6) cap = "Zoom into ONE pixel  ·  each image stores a complex phasor with phase φ";
    else if (ts < 7.8) cap = "Conjugating flips the phase:  s\u2081 -> s\u2081*  ·  multiplying by it SUBTRACTS the angle";
    else if (ts < 9.7) cap = "s\u2080·s\u2081*  ->  one phasor whose angle is the phase DIFFERENCE \u03c6\u2080 \u2212 \u03c6\u2081";
    else if (ts < 12.7) cap = "Slide the landscapes together and subtract  ·  the shared topographic phase cancels";
    else if (ts < 15.5) cap = "A smooth landscape remains: Δφ ∝ kz·ξ  ·  the colour bands are interference fringes";
    else if (ts < FAST0) cap = "Store interferogram 1  ·  now the same product runs against every other secondary";
    else if (ts < FAST0 + 3 * FASTD) {
      cap = "s\u2080·s\u2096*  ·  larger baseline -> phase climbs faster (more fringe bands)";
    }
    else if (ts < CLIP0) cap = "ifg\u1d62 = A · s\u2080s\u1d62*/|s\u2080s\u1d62*|  ·  4 raw interferograms — still shaped by topography";
    else if (ts < 28.2) cap = "The amplitude weight A is clipped: A = clip(|s|, 0, 1.25)  ·  bright corner reflectors capped";
    else cap = "interferograms  ·  amplitude-weighted unit phasors, ready for DEM deramping";
    this._cap(cap);
  }

  _prDem(ts, d) {
    const { ctx, w, h } = this;
    const c01 = d.c01;

    const layW = Math.min(440, w * 0.345), layH = Math.min(165, h * 0.30);
    const yLay = h * 0.50;
    const xI = w * 0.12, xD = w * 0.88 - layW;
    const xCc = w / 2 - layW / 2;
    const lsk = Math.min(26, layW * 0.08);
    const ampR = 1.25, ampRes = 3.4;

    const demNeg = ts < 1.4 ? 0 : ts < 2.2 ? this._ease(c01((ts - 1.4) / 0.8)) : 1;
    const zIfg = (u, v) => 2.4 + d.FRV * d.hgtR(u, v);
    const cIfg = (u, v) => d.phCol(-zIfg(u, v), 0.95);
    const zDem = (u, v) => (2.4 + d.FRV * d.demR(u, v)) * (1 - 2 * demNeg);
    const cDem = (u, v) => d.phCol(-zDem(u, v), 0.95);
    const zRes = (u, v) => d.FRV * 0.55 * d.veg(u, v);
    const cRes = (k) => (u, v) => d.phCol(-k * zRes(u, v), 0.95);

    const thumbs = ts >= 6.4;
    const thA = thumbs ? this._ease(c01((ts - 6.4) / 0.7)) : 0;
    const mainA = 1 - thA;

    const spC = this._ease(c01((ts - 1.2) / 2.6));
    const mergedC = ts >= 3.8;
    const srcAc = mergedC ? Math.max(0, 1 - (ts - 3.8) / 0.5) : 1;
    const xId = this._lerp(xI, xCc, spC);
    const xRd = this._lerp(xD, xCc, spC);

    if (mainA > 0.02) {
      const ifgA = this._ease(c01(ts / 0.6)) * mainA;
      const dA = this._ease(c01((ts - 0.5) / 0.8)) * mainA;
      const ox0 = Math.max(xRd, xCc), ox1 = Math.min(xId + layW, xCc + layW);

      if (srcAc > 0) {
        ctx.save();
        if (spC > 0) { ctx.beginPath(); ctx.rect(0, 0, ox0, h); ctx.clip(); }
        this._prLand(xId, yLay, layW, layH, ampR, zIfg, cIfg, ifgA * srcAc, "rgba(53,230,208,0.55)");
        ctx.restore();
        if (dA > 0) {
          ctx.save();
          if (spC > 0) { ctx.beginPath(); ctx.rect(ox1, 0, w - ox1, h); ctx.clip(); }
          this._prLand(xRd, yLay, layW, layH, ampR, zDem, cDem, dA * srcAc, "rgba(255,207,107,0.7)");
          ctx.restore();
        }
        if (spC < 0.25) {
          ctx.save(); ctx.globalAlpha = ifgA * srcAc;
          this._prPlate(xId + 12, yLay + layH + 34, "interferogram 1 · raw", "rgba(206,229,223,0.95)");
          ctx.restore();
          if (dA > 0) {
            const dpa = dA * srcAc;
            const ddx = xRd + 12, ddy = yLay + layH + 22;
            const ddm = this._tex("\\tilde{s}_i=s_i\\,e^{\\,j\\varphi_{\\mathrm{DEM}}}", 15, "#ffcf6b");
            const ddw = ddm.ready ? ddm.w : 170, ddh = ddm.ready ? ddm.h : 28;
            ctx.save(); ctx.globalAlpha = dpa;
            ctx.fillStyle = "rgba(7,12,17,0.92)";
            ctx.strokeStyle = "rgba(120,200,220,0.30)"; ctx.lineWidth = 1.1;
            ctx.beginPath();
            if (ctx.roundRect) ctx.roundRect(ddx - 12, ddy - 6, ddw + 24, ddh + 12, 7); else ctx.rect(ddx - 12, ddy - 6, ddw + 24, ddh + 12);
            ctx.fill(); ctx.stroke();
            this._texDraw("\\tilde{s}_i=s_i\\,e^{\\,j\\varphi_{\\mathrm{DEM}}}", ddx, ddy, 15, { color: "#ffcf6b", alpha: dpa });
            ctx.restore();
          }
        }
      }

      if (spC > 0 && ox1 > ox0 + 2) {
        ctx.save();
        ctx.beginPath(); ctx.rect(ox0, 0, ox1 - ox0, h); ctx.clip();
        this._prLand(xCc, yLay, layW, layH, ampRes, zRes, cRes(1), mainA, "rgba(124,255,155,0.6)");
        ctx.restore();
        if (spC < 1) {
          for (let k = 0; k < 14; k++) {
            const yy = yLay - 34 + d.rnd(k * 9.1 + Math.floor(this.t * 8)) * (layH + 54);
            const ee = k % 2 ? ox0 : ox1;
            ctx.fillStyle = `rgba(230,247,243,${(0.5 + 0.4 * Math.sin(this.t * 11 + k)) * mainA})`;
            ctx.fillRect(ee - 1, yy, 3, 3);
          }
        }
        if (mergedC) {
          const dqb = this._texDraw("\\Delta\\varphi-\\varphi_{\\mathrm{DEM}}", xCc + 12, yLay + layH + 22, 15, { color: "#7cff9b", alpha: mainA });
          ctx.save(); ctx.globalAlpha = mainA * 0.85;
          ctx.font = "12px 'IBM Plex Mono', monospace"; ctx.fillStyle = "rgba(206,229,223,0.9)";
          ctx.fillText("residual · height above the DEM", xCc + 12 + (dqb ? dqb.w + 16 : 150), yLay + layH + 42);
          ctx.restore();
        }
      }

      if (ts >= 1.0 && ts < 5.8) {
        const ia2 = this._ease(c01((ts - 1.0) / 0.5)) * this._ease(c01((5.8 - ts) / 0.5));
        const u0 = 0.62, v0 = 0.44;
        const aI = d.wrap(-(2.4 + d.FRV * d.hgtR(u0, v0)));
        const aD0 = d.wrap(-(2.4 + d.FRV * d.demR(u0, v0)));
        const negP = this._ease(c01((ts - 1.4) / 0.8));
        const angD = this._lerp(aD0, -aD0, negP);
        const aRes = d.wrap(aI - aD0);
        const mP = spC;
        const icW = Math.min(500, w * 0.46), icH = 142;
        const icX = w / 2 - icW / 2, icY = 22;
        const ancX = (xx) => xx + lsk * (1 - v0) + u0 * (layW - lsk);

        const ring = (X, Y, al) => {
          ctx.save(); ctx.globalAlpha = ia2 * al;
          ctx.strokeStyle = "#ffcf6b"; ctx.lineWidth = 1.6;
          ctx.beginPath(); ctx.arc(X, Y, 7 + Math.sin(this.t * 5) * 1.5, 0, 7); ctx.stroke();
          ctx.restore();
        };
        const conn = (X, Y, fx3, al) => {
          ctx.save(); ctx.globalAlpha = ia2 * al;
          ctx.strokeStyle = "rgba(255,207,107,0.35)"; ctx.setLineDash([3, 4]); ctx.lineWidth = 1;
          ctx.beginPath(); ctx.moveTo(X, Y - 9); ctx.lineTo(icX + icW * fx3, icY + icH); ctx.stroke();
          ctx.setLineDash([]); ctx.restore();
        };
        if (srcAc > 0.05) {
          const pxI2 = ancX(xId), pyI2 = yLay + v0 * layH - ampR * zIfg(u0, v0);
          ring(pxI2, pyI2, srcAc);
          conn(pxI2, pyI2, this._lerp(0.32, 0.5, mP), srcAc);
          if (dA > 0.05) {
            const pxD = ancX(xRd), pyD = yLay + v0 * layH - ampR * zDem(u0, v0);
            ring(pxD, pyD, srcAc);
            conn(pxD, pyD, this._lerp(0.68, 0.5, mP), srcAc);
          }
        }
        if (mergedC) {
          const mra = Math.min(1, (ts - 3.8) / 0.5);
          const pxR = ancX(xCc), pyR = yLay + v0 * layH - ampRes * zRes(u0, v0);
          ring(pxR, pyR, mra);
          conn(pxR, pyR, 0.5, mra);
        }

        ctx.save(); ctx.globalAlpha = ia2;
        ctx.fillStyle = "rgba(4,7,10,0.92)";
        ctx.strokeStyle = "rgba(120,200,220,0.3)"; ctx.lineWidth = 1.2;
        ctx.beginPath();
        if (ctx.roundRect) ctx.roundRect(icX, icY, icW, icH, 9); else ctx.rect(icX, icY, icW, icH);
        ctx.fill(); ctx.stroke();

        const cyc = icY + 74, rr = 33;
        const cxA = this._lerp(icX + icW * 0.30, icX + icW * 0.5, mP);
        const cxB = this._lerp(icX + icW * 0.70, icX + icW * 0.5, mP);
        const circ = (X, lbl, lblCol, la2) => {
          ctx.strokeStyle = "rgba(120,200,220,0.4)"; ctx.lineWidth = 1.2;
          ctx.beginPath(); ctx.arc(X, cyc, rr, 0, 7); ctx.stroke();
          if (la2 == null || la2 > 0.03) {
            ctx.save();
            if (la2 != null) ctx.globalAlpha = ctx.globalAlpha * la2;
            ctx.font = "15px 'IBM Plex Mono', monospace";
            ctx.fillStyle = lblCol;
            ctx.fillText(lbl, X - ctx.measureText(lbl).width / 2, cyc + rr + 20);
            ctx.restore();
          }
        };
        const arr = (X, ang, color, al, dash) => {
          ctx.save(); ctx.globalAlpha = ia2 * al;
          ctx.strokeStyle = color; ctx.lineWidth = 2;
          if (dash) ctx.setLineDash([3, 3]);
          ctx.beginPath(); ctx.moveTo(X, cyc); ctx.lineTo(X + rr * 0.86 * Math.cos(ang), cyc - rr * 0.86 * Math.sin(ang)); ctx.stroke();
          ctx.setLineDash([]);
          ctx.fillStyle = color;
          ctx.beginPath(); ctx.arc(X + rr * 0.86 * Math.cos(ang), cyc - rr * 0.86 * Math.sin(ang), 3, 0, 7); ctx.fill();
          ctx.restore();
        };

        if (mP < 1) {
          circ(cxA, "Δφ", "#35e6d0", 1 - mP);
          circ(cxB, negP > 0.5 ? "−φ_DEM" : "φ_DEM", "#ffcf6b", 1 - mP);
          arr(cxA, aI, "#35e6d0", 1 - mP, false);
          arr(cxB, angD, "#ffcf6b", 1 - mP, false);
          if (negP > 0 && negP < 1) arr(cxB, aD0, "rgba(255,207,107,0.5)", 0.5, true);
        } else {
          circ(cxA, "Δφ − φ_DEM", "#7cff9b");
        }
        if (mP > 0) arr(icX + icW * 0.5, aRes, "#7cff9b", mP, false);
        ctx.font = "14px 'IBM Plex Mono', monospace";
        ctx.fillStyle = "rgba(230,247,243,0.9)";
        if (mP >= 1) {
          ctx.fillText("left over:", icX + 14, icY + 18);
          const fb2 = this._texDraw("k_z(\\xi-z_{\\mathrm{DEM}})", icX + 108, icY + 6, 14, { color: "#7cff9b", alpha: ia2 });
          ctx.fillText("— canopy here", icX + 108 + (fb2 ? fb2.w + 16 : 150), icY + 18);
        } else {
          const ft2 = ts < 1.6 ? "the SAME pixel in both layers · two phasors" : ts < 2.4 ? "negate the DEM phase:  φ_DEM -> −φ_DEM" : "subtracting in sync with the merge · Δφ + (−φ_DEM)";
          ctx.fillText(ft2, icX + 14, icY + 18);
        }
        ctx.restore();
      }

      if (mergedC && !thumbs && ts >= 4.4) {
        const ha = this._ease(c01((ts - 4.4) / 0.6)) * mainA;
        const vB = 0.6;
        let uB = 0.5, best = -1, uF = 0.5, worst = 99;
        for (let q = 7; q <= 19; q++) {
          const u = q / 20;
          const vv = d.vegP(u, vB);
          if (vv > best) { best = vv; uB = u; }
          if (vv < worst) { worst = vv; uF = u; }
        }
        const bx = xCc + lsk * (1 - vB) + uB * (layW - lsk);
        const by = yLay + vB * layH - ampRes * zRes(uB, vB);
        const fx2 = xCc + lsk * (1 - vB) + uF * (layW - lsk);
        const fy2 = yLay + vB * layH - ampRes * zRes(uF, vB);
        const lx = Math.min(xCc + layW + 50, w - 260);
        const lyB = yLay - 4, lyF = yLay + 44;
        ctx.save(); ctx.globalAlpha = ha;
        ctx.font = "14px 'IBM Plex Mono', monospace";
        ctx.strokeStyle = "#7cff9b"; ctx.lineWidth = 1.4;
        ctx.beginPath(); ctx.arc(bx, by, 6 + Math.sin(this.t * 4) * 1.5, 0, 7); ctx.stroke();
        ctx.strokeStyle = "rgba(124,255,155,0.5)"; ctx.setLineDash([3, 4]); ctx.lineWidth = 1.1;
        ctx.beginPath(); ctx.moveTo(bx + 9, by - 4); ctx.lineTo(lx - 10, lyB); ctx.stroke();
        ctx.setLineDash([]);
        ctx.fillStyle = "#7cff9b";
        ctx.fillText("canopy bump · survives", lx, lyB + 4);
        ctx.strokeStyle = "rgba(196,221,215,0.85)"; ctx.lineWidth = 1.2;
        ctx.beginPath(); ctx.arc(fx2, fy2, 5, 0, 7); ctx.stroke();
        ctx.strokeStyle = "rgba(196,221,215,0.45)"; ctx.setLineDash([3, 4]); ctx.lineWidth = 1.1;
        ctx.beginPath(); ctx.moveTo(fx2 + 8, fy2 + 2); ctx.lineTo(lx - 10, lyF); ctx.stroke();
        ctx.setLineDash([]);
        ctx.fillStyle = "rgba(206,229,223,0.95)";
        ctx.fillText("flat plain · scene == DEM -> 0", lx, lyF + 4);
        ctx.restore();
      }
    }

    if (thumbs) {
      const slotW = Math.min(170, w / 6.4), slotH = 50;
      const svY0 = Math.max(36, h * 0.5 - 178);
      const sx = w / 2 - (slotW + 170) / 2;
      ctx.font = "14px 'IBM Plex Mono', monospace";
      const cw2 = ctx.measureText("interferograms.npy · (N, Az, Rg)").width + 24;
      this._prChip("interferograms.npy · (N, Az, Rg)", w / 2 - cw2 / 2, Math.max(22, svY0 - 36), "#7cff9b", this._ease(c01((ts - 7.4) / 0.7)));
      for (let k = 1; k <= 4; k++) {
        const ka = this._ease(c01((ts - 6.5 - (k - 1) * 0.25) / 0.5));
        if (ka <= 0) continue;
        const sy3 = svY0 + (k - 1) * 92;
        this._prLand(sx, sy3, slotW, slotH, ampRes * 0.55, zRes, cRes(k), ka, "rgba(124,255,155,0.5)");
        ctx.save(); ctx.globalAlpha = ka;
        ctx.font = "14px 'IBM Plex Mono', monospace";
        ctx.fillStyle = "rgba(230,247,243,0.95)";
        ctx.fillText(`ifg ${k} · deramped`, sx + slotW + 16, sy3 + slotH / 2 + 5);
        ctx.restore();
      }
    }

    let cap;
    if (ts < 1.0) cap = "Phase correction  ·  fsar_phadem predicts the DEM phase screen  ·  drawn as a phase landscape too";
    else if (ts < 3.8) cap = "The DEM phase is a smooth RAMP  ·  pure geometry from fsar_phadem, no measurement";
    else if (ts < 4.4) cap = "Slide the landscapes together  ·  wherever the scene matches the DEM, the phase flattens to zero";
    else if (ts < 6.4) cap = "Only the canopy structure above the DEM survives  ·  this becomes one of the model's input channels";
    else cap = "interferogram.py: s\u0303\u1d62 = s\u1d62·exp(j\u03c6_DEM) BEFORE the product  ·  4 deramped interferograms";
    this._cap(cap);
  }

  _prCapon(ts, d) {
    const { ctx, w, h } = this;
    const c01 = d.c01;

    const pad = { l: 250, r: 36, t: 52, b: 46 };
    const plotW = w - pad.l - pad.r, plotH = h - pad.t - pad.b;
    const pxZ = (z) => pad.l + ((z - d.ZMIN) / (d.ZMAX - d.ZMIN)) * plotW;
    const pyP = (v) => pad.t + (1 - c01(v)) * plotH;
    const bartAt = (z) => d.bartS[Math.max(0, Math.min(d.NZ - 1, Math.round(((z - d.ZMIN) / 100) * (d.NZ - 1))))];

    const A2 = 3.5, A3 = 7.5, A4 = 8.6, A5 = 10.8, B0 = 12.3, B2 = 14.2, B3 = 17.2, B4 = 19.2, C0 = 22.7, C2 = 27.2, D0 = 30.2;
    const tomoP = this._ease(c01((ts - D0) / 0.8));

    const scW = Math.min(340, w * 0.30), scH = Math.min(230, h * 0.44);
    const scX = w * 0.06, scY = h * 0.54 - scH / 2;
    const cpx = scX + scW * 0.55, cpy = scY + scH * 0.5;
    const ww = 96, wh = 48;
    const cs = 38;
    const mX = w * 0.66, mY = h * 0.54 - (d.N * cs) / 2;
    const vx = w * 0.40, vy0 = mY + 6;
    const lgx = w * 0.46, lgy = mY + 8, lc = 27;
    const mcs = 17, mmx = w - pad.r - 5 * mcs - 6, mmy = 96;

    const lkv = (k, i) => 0.55 + k * 1.1 + d.KZ[i] * (10 + k * 2.5) + (d.rnd(i * 3.1 + k * 7.7) - 0.5) * 0.4;
    const cellArrow = (x, y, sz, ang, color, lw) => {
      ctx.strokeStyle = color; ctx.lineWidth = lw || 1.5;
      ctx.beginPath();
      ctx.moveTo(x + sz / 2, y + sz / 2);
      ctx.lineTo(x + sz / 2 + sz * 0.38 * Math.cos(ang), y + sz / 2 - sz * 0.38 * Math.sin(ang));
      ctx.stroke();
    };
    const layerTile = (x, y, cell, alpha, k, withCells) => {
      ctx.save(); ctx.globalAlpha = alpha;
      ctx.fillStyle = "rgba(7,12,17,0.85)";
      ctx.fillRect(x - 2, y - 2, cell * 5 + 4, cell * 5 + 4);
      if (withCells) {
        for (let i = 0; i < 5; i++) {
          for (let j = 0; j < 5; j++) {
            const X = x + j * cell, Y = y + i * cell;
            ctx.fillStyle = "rgba(53,230,208,0.16)";
            ctx.fillRect(X, Y, cell - 2, cell - 2);
            if (cell > 13) cellArrow(X, Y, cell - 2, lkv(k, i) - lkv(k, j), "rgba(230,247,243,0.85)", 1.2);
          }
        }
      }
      ctx.strokeStyle = "rgba(120,200,220,0.65)"; ctx.lineWidth = 1.3;
      ctx.strokeRect(x - 2, y - 2, cell * 5 + 4, cell * 5 + 4);
      ctx.restore();
    };

    const nL = ts < 7.4 ? 0 : ts < 8.55 ? 1 : ts < A4 ? 2 : ts < A5 ? 2 + Math.round(198 * Math.pow(c01((ts - A4) / 2.0), 2)) : 200;
    const accBuild = this._ease(c01((ts - 6.7) / 1.2));
    const rAcc = 0.54 * accBuild + 0.46 * c01((nL - 2) / 198);


    if (ts < B0) {
      const ia = this._ease(c01(ts / 0.9)) * this._ease(c01((B0 - ts) / 0.5));
      const sc = 8;
      const snx = Math.round(scW / sc), sny = Math.round(scH / sc);
      const magAt = (x, y, i, j) => {
        let v = 0.45 + 0.3 * Math.sin(x * 13.1 + Math.sin(y * 7.2) * 2.2) * Math.cos(y * 9.4 + Math.sin(x * 5.1) * 1.6);
        if (d.rnd(i * 131 + j * 57) > 0.96) v += 0.4;
        return c01(v);
      };
      ctx.save(); ctx.globalAlpha = ia;
      for (let j = 0; j < sny; j++) {
        for (let i = 0; i < snx; i++) {
          ctx.fillStyle = `rgba(53,230,208,${0.06 + magAt(i / snx, j / sny, i, j) * 0.30})`;
          ctx.fillRect(scX + i * sc, scY + j * sc, sc - 1, sc - 1);
        }
      }
      ctx.strokeStyle = "rgba(120,200,220,0.45)"; ctx.lineWidth = 1.3;
      ctx.strokeRect(scX, scY, scW, scH);
      ctx.font = "13px 'IBM Plex Mono', monospace";
      ctx.fillStyle = "rgba(214,234,229,0.95)";
      ctx.fillText("|SLC| scene", scX, scY - 10);

      if (ts >= 1.2) {
        const wa = this._ease(c01((ts - 1.2) / 0.8));
        ctx.save(); ctx.globalAlpha = wa * ia;
        ctx.fillStyle = "rgba(4,7,10,0.55)";
        ctx.fillRect(scX, scY, scW, scH);
        for (let j = 0; j < sny; j++) {
          for (let i = 0; i < snx; i++) {
            const X = scX + i * sc, Y = scY + j * sc;
            if (X < cpx - ww / 2 || X > cpx + ww / 2 - sc || Y < cpy - wh / 2 || Y > cpy + wh / 2 - sc) continue;
            ctx.fillStyle = `rgba(53,230,208,${0.10 + magAt(i / snx, j / sny, i, j) * 0.45})`;
            ctx.fillRect(X, Y, sc - 1, sc - 1);
          }
        }
        ctx.strokeStyle = "#ffcf6b"; ctx.lineWidth = 1.6;
        ctx.strokeRect(cpx - ww / 2, cpy - wh / 2, ww, wh);
        ctx.fillStyle = "#ffcf6b"; ctx.font = "13px 'IBM Plex Mono', monospace";
        ctx.fillText("win [20,10] · 200 samp", cpx - ww / 2, cpy + wh / 2 + 16);
        ctx.restore();
      }

      ctx.restore();
      ctx.save(); ctx.globalAlpha = ia;
      if (accBuild < 1) {
        ctx.save(); ctx.globalAlpha = ia * (1 - accBuild);
        ctx.strokeStyle = "rgba(120,200,220,0.4)"; ctx.setLineDash([5, 5]); ctx.lineWidth = 1.2;
        ctx.strokeRect(mX - 4, mY - 4, d.N * cs + 6, d.N * cs + 6);
        ctx.setLineDash([]);
        if (nL === 0) {
          ctx.font = "14px 'IBM Plex Mono', monospace";
          ctx.fillStyle = "rgba(214,234,229,0.95)";
          ctx.fillText("R · waiting for looks", mX - 4, mY - 14);
        }
        ctx.restore();
      }
      if (accBuild > 0.001) {
        const stackN = Math.max(0, Math.min(4, nL - 1));
        for (let q = stackN; q >= 1; q--) layerTile(mX + q * 4, mY - q * 4, cs, (0.45 - q * 0.07) * accBuild, 0, false);
        for (let i = 0; i < d.N; i++) {
          for (let j = 0; j < d.N; j++) {
            ctx.fillStyle = `rgba(53,230,208,${(0.08 + 0.45 * d.Rmag[i][j]) * rAcc})`;
            ctx.fillRect(mX + j * cs, mY + i * cs, cs - 2, cs - 2);
            if (nL <= 2) {
              ctx.save(); ctx.globalAlpha = ia * accBuild;
              cellArrow(mX + j * cs, mY + i * cs, cs - 2, lkv(0, i) - lkv(0, j), "rgba(230,247,243,0.7)", 1.2);
              ctx.restore();
            }
          }
        }
        ctx.save(); ctx.globalAlpha = ia * accBuild;
        ctx.strokeStyle = "rgba(120,200,220,0.5)"; ctx.lineWidth = 1.2;
        ctx.strokeRect(mX - 4, mY - 4, d.N * cs + 6, d.N * cs + 6);
        ctx.restore();
        ctx.save(); ctx.globalAlpha = ia * accBuild;
        ctx.font = "13px 'IBM Plex Mono', monospace";
        ctx.fillStyle = "rgba(206,229,223,0.95)";
        for (let i = 0; i < d.N; i++) {
          ctx.fillText("s" + i, mX - 26, mY + i * cs + cs / 2 + 4);
          ctx.fillText("s" + i, mX + i * cs + cs / 2 - 7, mY + d.N * cs + 18);
        }
        ctx.font = "15px 'IBM Plex Mono', monospace";
        ctx.fillStyle = "#e6f7f3";
        ctx.fillText(`l = ${nL} / 200 samples`, mX, mY + d.N * cs + 40);
        ctx.restore();
        if (ts >= A5) {
          const ha = this._ease(c01((ts - A5) / 0.5));
          ctx.save(); ctx.globalAlpha = ha * ia;
          ctx.font = "17px 'IBM Plex Mono', monospace";
          ctx.fillStyle = "#ffcf6b";
          ctx.fillText("÷ L  ->  R", mX + 5 * cs * 0.32, mY - 16);
          ctx.strokeStyle = "#ffcf6b"; ctx.lineWidth = 1.8;
          ctx.strokeRect(mX + 3 * cs - 2, mY + 1 * cs - 2, cs, cs);
          ctx.strokeRect(mX + 1 * cs - 2, mY + 3 * cs - 2, cs, cs);
          ctx.font = "14px 'IBM Plex Mono', monospace";
          ctx.fillText("R is Hermitian:", mX - 26, mY + d.N * cs + 64);
          this._texDraw("\\hat{R}_{ij}=\\hat{R}_{ji}^{*}", mX + 116, mY + d.N * cs + 52, 14, { color: "#ffcf6b", alpha: ha * ia });
          ctx.restore();
        }
      }
      ctx.restore();

      if (ts >= A2 && ts < A3) {
        const ta = ts - A2;
        ctx.save(); ctx.globalAlpha = ia;
        const ringA = this._ease(c01(ta / 0.4));
        ctx.strokeStyle = `rgba(255,207,107,${0.95 * ringA})`; ctx.lineWidth = 1.7;
        ctx.beginPath(); ctx.arc(cpx + 10, cpy - 6, 6 + Math.sin(this.t * 5) * 1.4, 0, 7); ctx.stroke();
        for (let i = 0; i < d.N; i++) {
          const fp = this._ease(c01((ta - 0.4 - i * 0.07) / 0.55));
          if (fp <= 0) continue;
          const X = this._lerp(cpx + 10, vx, fp), Y = this._lerp(cpy - 6, vy0 + i * (lc + 2), fp);
          ctx.fillStyle = "rgba(7,12,17,0.9)";
          ctx.fillRect(X, Y, lc - 2, lc - 2);
          ctx.strokeStyle = "rgba(53,230,208,0.8)"; ctx.lineWidth = 1.2;
          ctx.strokeRect(X, Y, lc - 2, lc - 2);
          if (fp >= 1 && ta >= 1.1) cellArrow(X, Y, lc - 2, lkv(0, i), "#e6f7f3", 1.6);
          if (fp >= 1) {
            ctx.font = "13px 'IBM Plex Mono', monospace";
            ctx.fillStyle = "rgba(206,229,223,0.95)";
            ctx.fillText("s" + i, vx - 22, Y + 15);
          }
        }
        if (ta >= 1.1) {
          ctx.font = "15px 'IBM Plex Mono', monospace";
          ctx.fillStyle = "#e6f7f3";
          ctx.fillText("y", vx + 6, vy0 - 12);
        }
        const rha = this._ease(c01((ta - 1.8) / 0.5));
        if (rha > 0 && ta < 3.2) {
          ctx.save(); ctx.globalAlpha = ia * rha;
          for (let j = 0; j < 5; j++) {
            const X = lgx + j * lc, Y = lgy - lc - 8;
            ctx.fillStyle = "rgba(7,12,17,0.9)";
            ctx.fillRect(X, Y, lc - 2, lc - 2);
            ctx.strokeStyle = "rgba(150,200,210,0.7)"; ctx.lineWidth = 1.1;
            ctx.strokeRect(X, Y, lc - 2, lc - 2);
            cellArrow(X, Y, lc - 2, -lkv(0, j), "#e6f7f3", 1.4);
          }
          ctx.font = "15px 'IBM Plex Mono', monospace";
          ctx.fillStyle = "#e6f7f3";
          ctx.fillText("yᴴ", lgx + 5 * lc + 8, lgy - lc + 8);
          ctx.restore();
        }
        if (ta >= 1.9 && ta < 3.2) {
          ctx.font = "20px 'IBM Plex Mono', monospace";
          ctx.fillStyle = "#ffcf6b";
          ctx.fillText("\u00d7", (vx + lc + lgx) / 2 - 6, vy0 + 2.5 * (lc + 2));
        }
        if (ta >= 2.5 && ta < 3.2) {
          this._texDraw("\\mathrm{cell}(i,j)=y_i\\,y_j^{*}", lgx + 6, lgy + 5 * lc + 20, 14, { color: "#7cff9b", alpha: ia });
        }
        if (ta >= 2.3 && ta < 3.2) {
          const nC = Math.min(25, Math.floor((ta - 2.3) / 0.032));
          for (let idx = 0; idx < nC; idx++) {
            const i = Math.floor(idx / 5), j = idx % 5;
            const X = lgx + j * lc, Y = lgy + i * lc;
            ctx.fillStyle = "rgba(53,230,208,0.18)";
            ctx.fillRect(X, Y, lc - 2, lc - 2);
            cellArrow(X, Y, lc - 2, lkv(0, i) - lkv(0, j), "rgba(230,247,243,0.85)", 1.2);
          }
          ctx.strokeStyle = "rgba(124,255,155,0.7)"; ctx.lineWidth = 1.3;
          ctx.strokeRect(lgx - 2, lgy - 2, lc * 5 + 4, lc * 5 + 4);
        } else if (ta >= 3.2) {
          const flp = this._ease(c01((ta - 3.2) / 0.8));
          const X = this._lerp(lgx, mX + 4, flp), Y = this._lerp(lgy, mY - 4, flp);
          layerTile(X, Y, this._lerp(lc, cs, flp), 1 - flp * 0.25, 0, true);
        }
        ctx.restore();
      } else if (ts >= A3 && ts < A4) {
        const ta2 = ts - A3;
        ctx.save(); ctx.globalAlpha = ia;
        if (ta2 < 0.8) {
          ctx.strokeStyle = "rgba(255,207,107,0.95)"; ctx.lineWidth = 1.7;
          ctx.beginPath(); ctx.arc(cpx - 16, cpy + 9, 6, 0, 7); ctx.stroke();
        }
        for (let i = 0; i < d.N; i++) {
          const fp = this._ease(c01((ta2 - 0.10 - i * 0.04) / 0.3));
          if (fp <= 0) continue;
          const X = this._lerp(cpx - 16, vx, fp), Y = this._lerp(cpy + 9, vy0 + i * (lc + 2), fp);
          ctx.fillStyle = "rgba(7,12,17,0.9)";
          ctx.fillRect(X, Y, lc - 2, lc - 2);
          ctx.strokeStyle = "rgba(53,230,208,0.8)"; ctx.lineWidth = 1.2;
          ctx.strokeRect(X, Y, lc - 2, lc - 2);
          if (fp >= 1) cellArrow(X, Y, lc - 2, lkv(1, i), "#e6f7f3", 1.6);
        }
        if (ta2 >= 0.5 && ta2 < 0.8) {
          const nC = Math.min(25, Math.floor((ta2 - 0.5) / 0.012));
          for (let idx = 0; idx < nC; idx++) {
            const i = Math.floor(idx / 5), j = idx % 5;
            const X = lgx + j * lc, Y = lgy + i * lc;
            ctx.fillStyle = "rgba(53,230,208,0.18)";
            ctx.fillRect(X, Y, lc - 2, lc - 2);
            cellArrow(X, Y, lc - 2, lkv(1, i) - lkv(1, j), "rgba(230,247,243,0.85)", 1.2);
          }
        } else if (ta2 >= 0.8) {
          const flp = this._ease(c01((ta2 - 0.8) / 0.3));
          layerTile(this._lerp(lgx, mX + 8, flp), this._lerp(lgy, mY - 8, flp), this._lerp(lc, cs, flp), 1 - flp * 0.25, 1, true);
        }
        ctx.restore();
      }

      if (ts >= A4 && ts < A5) {
        for (let q = 0; q < 3; q++) {
          const tline = (ts - A4) * 4.2 + q / 3;
          const fp = tline % 1;
          const seed = Math.floor(tline) * 3 + q;
          const sxF = cpx - ww / 2 + d.rnd(seed * 3.3) * ww;
          const syF = cpy - wh / 2 + d.rnd(seed * 7.9) * wh;
          const X = this._lerp(sxF, mX + 10, this._ease(fp));
          const Y = this._lerp(syF, mY - 8, this._ease(fp)) - Math.sin(Math.PI * fp) * 40;
          ctx.save(); ctx.globalAlpha = (1 - fp) * 0.9 * ia;
          ctx.strokeStyle = "#ffcf6b"; ctx.lineWidth = 1.3;
          ctx.strokeRect(X, Y, 26, 26);
          ctx.beginPath(); ctx.moveTo(X, Y + 26); ctx.lineTo(X + 26, Y); ctx.stroke();
          ctx.restore();
        }
      }
    }

    let xi = null, mode = null;
    if (ts >= B2 && ts < B3) { xi = 0; mode = "bf"; }
    else if (ts >= B3 && ts < B4) { xi = this._lerp(0, 40, this._ease(c01((ts - B3) / 0.6))); mode = "bf"; }
    else if (ts >= B4 && ts < C0) { xi = d.ZMIN + this._ease(c01((ts - B4 - 0.2) / 2.9)) * 100; mode = "bf"; }
    else if (ts >= C0 && ts < C2) { xi = d.ZMIN + this._ease(c01((ts - C0 - 0.3) / 3.6)) * 100; mode = "cp"; }

    if (ts >= B0 && tomoP < 1) {
      const axA = this._ease(c01((ts - B0) / 0.8)) * (1 - tomoP);
      ctx.save(); ctx.globalAlpha = axA;
      ctx.strokeStyle = "rgba(120,200,220,0.10)"; ctx.lineWidth = 1;
      for (let i = 0; i <= 4; i++) {
        const y = pad.t + (plotH / 4) * i;
        ctx.beginPath(); ctx.moveTo(pad.l, y); ctx.lineTo(w - pad.r, y); ctx.stroke();
      }
      for (let z = -20; z <= 80; z += 20) {
        const X = pxZ(z);
        ctx.strokeStyle = "rgba(120,200,220,0.10)";
        ctx.beginPath(); ctx.moveTo(X, pad.t); ctx.lineTo(X, h - pad.b); ctx.stroke();
        ctx.fillStyle = "rgba(214,234,229,0.95)"; ctx.font = "13px 'IBM Plex Mono', monospace";
        ctx.fillText(String(z), X - 8, h - pad.b + 18);
      }
      ctx.fillStyle = "rgba(214,234,229,0.95)"; ctx.font = "13px 'IBM Plex Mono', monospace";
      ctx.fillText("elevation ξ [m]", w - pad.r - 102, h - pad.b + 34);
      ctx.fillText("power", pad.l + 8, pad.t + 14);
      if (xi != null) {
        const X = pxZ(xi);
        ctx.strokeStyle = "rgba(255,207,107,0.7)"; ctx.lineWidth = 1.3;
        ctx.beginPath(); ctx.moveTo(X, pad.t); ctx.lineTo(X, h - pad.b); ctx.stroke();
        ctx.fillStyle = "#ffcf6b";
        ctx.beginPath(); ctx.moveTo(X, h - pad.b - 1); ctx.lineTo(X - 5, h - pad.b + 8); ctx.lineTo(X + 5, h - pad.b + 8); ctx.closePath(); ctx.fill();
        if (ts >= B4) {
          ctx.font = "14px 'IBM Plex Mono', monospace";
          ctx.fillText(`ξ = ${xi.toFixed(0)} m`, Math.min(X + 8, w - pad.r - 76), pad.t + 32);
        }
      }
      ctx.restore();
    }

    if (ts >= B0 && ts < C0 + 0.5 && tomoP < 1) {
      const mmA = this._ease(c01((ts - B0) / 0.6)) * (ts < C0 ? 1 : Math.max(0, 1 - (ts - C0) / 0.5));
      ctx.save(); ctx.globalAlpha = mmA;
      for (let i = 0; i < d.N; i++) {
        for (let j = 0; j < d.N; j++) {
          ctx.fillStyle = `rgba(53,230,208,${0.10 + 0.40 * d.Rmag[i][j]})`;
          ctx.fillRect(mmx + j * mcs, mmy + i * mcs, mcs - 1, mcs - 1);
        }
      }
      ctx.strokeStyle = "rgba(120,200,220,0.45)"; ctx.lineWidth = 1.1;
      ctx.strokeRect(mmx - 2, mmy - 2, 5 * mcs + 3, 5 * mcs + 3);
      if (ts < B2 + 0.8) {
        ctx.strokeStyle = "#7cff9b"; ctx.lineWidth = 1.5;
        ctx.strokeRect(mmx - 2, mmy - 2, 5 * mcs + 3, mcs + 2);
      }
      ctx.font = "14px 'IBM Plex Mono', monospace";
      ctx.fillStyle = "#e6f7f3";
      ctx.fillText("R", mmx - 16, mmy + 2.5 * mcs + 4);
      ctx.restore();
    }

    if (ts >= B0 && ts < C2 && tomoP < 1) {
      const ca = this._ease(c01((ts - B0) / 0.7)) * this._ease(c01((C2 - ts) / 0.5));
      const stXc = 200, rC = 21;
      const cyI = (i) => pad.t + 32 + i * 68;
      ctx.save(); ctx.globalAlpha = ca;
      ctx.font = "13px 'IBM Plex Mono', monospace";
      ctx.strokeStyle = "#e6f7f3"; ctx.lineWidth = 2;
      ctx.beginPath(); ctx.moveTo(24, pad.t - 24); ctx.lineTo(44, pad.t - 24); ctx.stroke();
      ctx.fillStyle = "#e6f7f3";
      ctx.fillText("measured · from R", 50, pad.t - 19);
      ctx.strokeStyle = "#7cff9b";
      ctx.beginPath(); ctx.moveTo(24, pad.t - 8); ctx.lineTo(44, pad.t - 8); ctx.stroke();
      ctx.fillStyle = "#7cff9b";
      ctx.fillText("predicted · a(ξ)", 50, pad.t - 3);
      for (let i = 0; i < d.N; i++) {
        const cy = cyI(i);
        ctx.strokeStyle = "rgba(120,200,220,0.45)"; ctx.lineWidth = 1.2;
        ctx.beginPath(); ctx.arc(stXc, cy, rC, 0, 7); ctx.stroke();
        if (ts >= B2 + 0.4 && xi != null) {
          const angP2 = d.KZ[i] * xi, angM2 = d.Rrow[i];
          const dfA = Math.atan2(Math.sin(angP2 - angM2), Math.cos(angP2 - angM2));
          const good = Math.abs(dfA) < 0.7;
          ctx.fillStyle = good ? "rgba(124,255,155,0.30)" : "rgba(255,107,125,0.25)";
          ctx.beginPath(); ctx.moveTo(stXc, cy);
          ctx.arc(stXc, cy, rC * 0.8, -angM2, -angM2 - dfA, dfA > 0);
          ctx.closePath(); ctx.fill();
          ctx.font = "15px 'IBM Plex Mono', monospace";
          ctx.fillStyle = good ? "#7cff9b" : "#ff6b7d";
          ctx.fillText(good ? "\u2713" : "\u2717", stXc + rC + 10, cy + 5);
        }
        ctx.font = "13px 'IBM Plex Mono', monospace";
        ctx.fillStyle = "rgba(214,234,229,0.95)";
        ctx.fillText(`s${i}`, stXc - 7, cy - rC - 7);
        const maA = this._ease(c01((ts - B0 - 0.4 - i * 0.16) / 0.5));
        if (maA > 0 && maA < 1) {
          ctx.save(); ctx.globalAlpha = ca * (1 - maA) * 0.6;
          ctx.strokeStyle = "#e6f7f3"; ctx.lineWidth = 1.1; ctx.setLineDash([3, 4]);
          ctx.beginPath();
          ctx.moveTo(mmx + i * mcs + mcs / 2, mmy + mcs / 2);
          ctx.lineTo(stXc, cy);
          ctx.stroke(); ctx.setLineDash([]);
          ctx.restore();
        }
        if (maA > 0) {
          ctx.save(); ctx.globalAlpha = ca * maA;
          ctx.strokeStyle = "#e6f7f3"; ctx.lineWidth = 2;
          ctx.beginPath(); ctx.moveTo(stXc, cy);
          ctx.lineTo(stXc + rC * 0.66 * Math.cos(d.Rrow[i]), cy - rC * 0.66 * Math.sin(d.Rrow[i]));
          ctx.stroke();
          ctx.restore();
        }
        if (ts >= B2 && xi != null) {
          const ppA = this._ease(c01((ts - B2) / 0.5));
          const ang = d.KZ[i] * xi;
          ctx.save(); ctx.globalAlpha = ca * ppA;
          ctx.strokeStyle = "#7cff9b"; ctx.lineWidth = 2;
          ctx.beginPath(); ctx.moveTo(stXc, cy);
          ctx.lineTo(stXc + rC * 0.92 * Math.cos(ang), cy - rC * 0.92 * Math.sin(ang));
          ctx.stroke();
          ctx.fillStyle = "#7cff9b";
          ctx.beginPath(); ctx.arc(stXc + rC * 0.92 * Math.cos(ang), cy - rC * 0.92 * Math.sin(ang), 2.6, 0, 7); ctx.fill();
          ctx.restore();
        }
      }
      if (ts >= B2 && xi != null) {
        const sc2 = bartAt(xi);
        const bx2 = w - pad.r - 266, bw3 = 150, by3 = 224;
        ctx.font = "13px 'IBM Plex Mono', monospace";
        ctx.fillStyle = "#e6f7f3";
        ctx.fillText("illustrative match score", bx2, by3 - 8);
        ctx.strokeStyle = "rgba(120,200,220,0.5)"; ctx.lineWidth = 1.1;
        ctx.strokeRect(bx2, by3, bw3, 13);
        ctx.fillStyle = `rgba(${Math.round(255 - sc2 * 131)},${Math.round(107 + sc2 * 148)},${Math.round(125 + sc2 * 30)},0.85)`;
        ctx.fillRect(bx2 + 1, by3 + 1, (bw3 - 2) * sc2, 11);
        ctx.fillStyle = "#e6f7f3";
        ctx.fillText(`P(ξ) = ${sc2.toFixed(2)}`, bx2 + bw3 + 12, by3 + 12);
      }
      if (ts >= B2 + 0.8 && ts < B3) {
        ctx.fillStyle = "#7cff9b"; ctx.font = "15px 'IBM Plex Mono', monospace";
        ctx.fillText("patterns ALIGN ✓", w - pad.r - 266, 268);
      } else if (ts >= B3 + 0.7 && ts < B4) {
        ctx.fillStyle = "#ff6b7d"; ctx.font = "15px 'IBM Plex Mono', monospace";
        ctx.fillText("patterns DISAGREE ✗", w - pad.r - 266, 268);
      }
      ctx.restore();
    }

    if (tomoP < 1 && ts >= 6.7 && ts < B0) {
      const rpA = this._ease(c01((ts - 6.7) / 0.6)) * this._ease(c01((B0 - ts) / 0.4));
      const rpx = mX - 26, rpy = mY - 72;
      this._texDraw("\\hat{\\mathbf{R}}=\\frac{1}{L}\\sum_{l}\\mathbf{s}_l\\mathbf{s}_l^{H}", rpx, rpy, 16, { color: "#35e6d0", alpha: rpA });
    }

    if (ts >= B0 && tomoP < 1) {
      const specA = 1 - tomoP;
      const trace = (spec, frac, color, lw, glow) => {
        if (frac <= 0) return;
        const n2 = Math.round(c01(frac) * (d.NZ - 1));
        ctx.beginPath();
        for (let zi = 0; zi <= n2; zi++) {
          const X = pad.l + (zi / (d.NZ - 1)) * plotW, Y = pyP(spec[zi] * 0.92);
          zi ? ctx.lineTo(X, Y) : ctx.moveTo(X, Y);
        }
        ctx.strokeStyle = color; ctx.lineWidth = lw;
        if (glow) { ctx.shadowColor = "rgba(53,230,208,0.5)"; ctx.shadowBlur = 7; }
        ctx.stroke(); ctx.shadowBlur = 0;
      };
      ctx.save(); ctx.globalAlpha = specA;

      const bfFrac = ts >= C0 ? 1 : (mode === "bf" && ts >= B4 ? (xi - d.ZMIN) / 100 : 0);
      const cpFrac = ts >= C2 ? 1 : (mode === "cp" ? (xi - d.ZMIN) / 100 : 0);
      trace(d.bartS, bfFrac, ts >= C0 ? "rgba(196,221,215,0.45)" : "rgba(214,234,229,0.95)", 2, false);
      trace(d.capS, cpFrac, "#35e6d0", 2.2, true);

      if (ts >= B2 + 0.6) {
        const pp = this._ease(c01((ts - B2 - 0.6) / 0.8));
        const X = pxZ(0), Y = pyP(bartAt(0) * 0.92 * pp);
        ctx.strokeStyle = "rgba(124,255,155,0.5)"; ctx.lineWidth = 1.2;
        ctx.beginPath(); ctx.moveTo(X, h - pad.b); ctx.lineTo(X, Y); ctx.stroke();
        ctx.fillStyle = "#7cff9b";
        ctx.beginPath(); ctx.arc(X, Y, 4.5, 0, 7); ctx.fill();
        if (pp >= 1 && ts < B4 + 1.5) {
          ctx.font = "14px 'IBM Plex Mono', monospace";
          ctx.fillText("P(0) · strong", X + 10, Y - 8);
        }
      }
      if (ts >= B3 + 0.8) {
        const pp = this._ease(c01((ts - B3 - 0.8) / 0.6));
        const X = pxZ(40), Y = pyP(bartAt(40) * 0.92 * pp);
        ctx.fillStyle = "#ff6b7d";
        ctx.beginPath(); ctx.arc(X, Y, 4.5, 0, 7); ctx.fill();
        if (pp >= 1 && ts < B4 + 1.5) {
          ctx.font = "14px 'IBM Plex Mono', monospace";
          ctx.fillText("P(40) ≈ 0", X - 104, Y - 10);
        }
      }

      if (ts >= B4 + 2.6 && ts < C0) {
        ctx.fillStyle = "#e6f7f3"; ctx.font = "14px 'IBM Plex Mono', monospace";
        ctx.fillText("one WIDE lobe · ground + canopy blurred", Math.min(pxZ(26), w - 370), pyP(0.62));
      }
      if (ts >= C2) {
        const aa = this._ease(c01((ts - C2) / 0.8));
        ctx.save(); ctx.globalAlpha = aa * specA;
        [0, 18].forEach((z) => {
          const X = pxZ(z);
          ctx.strokeStyle = "rgba(124,255,155,0.6)"; ctx.setLineDash([5, 4]); ctx.lineWidth = 1.2;
          ctx.beginPath(); ctx.moveTo(X, pad.t + 6); ctx.lineTo(X, h - pad.b); ctx.stroke(); ctx.setLineDash([]);
        });
        const bY = pyP(0.30);
        ctx.strokeStyle = "rgba(255,207,107,0.85)"; ctx.lineWidth = 1.3;
        ctx.beginPath(); ctx.moveTo(pxZ(0), bY); ctx.lineTo(pxZ(18), bY); ctx.stroke();
        ctx.beginPath(); ctx.moveTo(pxZ(0), bY - 5); ctx.lineTo(pxZ(0), bY + 5); ctx.stroke();
        ctx.beginPath(); ctx.moveTo(pxZ(18), bY - 5); ctx.lineTo(pxZ(18), bY + 5); ctx.stroke();
        ctx.fillStyle = "#ffcf6b"; ctx.font = "14px 'IBM Plex Mono', monospace";
        ctx.save(); ctx.textAlign = "center";
        ctx.fillText("Δξ = 18 m", pxZ(9), bY + 24);
        ctx.restore();
        const lbW = 360, lbX = w - pad.r - lbW - 14, lbY = pad.t + 18, lbH = 152;
        ctx.fillStyle = "rgba(7,12,17,0.94)";
        ctx.strokeStyle = "rgba(120,200,220,0.35)"; ctx.lineWidth = 1.2;
        ctx.beginPath();
        if (ctx.roundRect) ctx.roundRect(lbX, lbY, lbW, lbH, 9); else ctx.rect(lbX, lbY, lbW, lbH);
        ctx.fill(); ctx.stroke();
        ctx.font = "11px 'IBM Plex Mono', monospace";
        ctx.fillStyle = "#5e7280";
        ctx.fillText("illustrative two-target demo", lbX + 16, lbY + 22);
        ctx.font = "14px 'IBM Plex Mono', monospace";
        ctx.fillStyle = "#7cff9b";
        ctx.fillText("ground peak  ·  ξ = 0 m", lbX + 16, lbY + 46);
        ctx.fillText("canopy peak  ·  ξ = +18 m", lbX + 16, lbY + 68);
        ctx.fillStyle = "#ffcf6b";
        ctx.fillText("Rayleigh limit:", lbX + 16, lbY + 94);
        this._texDraw("\\delta\\xi=\\frac{\\lambda r_0}{2\\,\\Delta b}", lbX + 142, lbY + 78, 13, { color: "#ffcf6b", alpha: aa * specA });
        ctx.fillStyle = "#e6f7f3";
        ctx.fillText("peaks < Rayleigh  ->  super-resolved", lbX + 16, lbY + 132);
        ctx.restore();
      }
      ctx.restore();
    }

    if (tomoP < 1 && ts >= B0) {
      const ta3 = this._ease(c01((ts - B0) / 0.6)) * (1 - tomoP);
      const tbW = 162, tbX = 12, tbH = 170, tbY = h - tbH - 8;
      const footY = tbY + tbH - 28;
      ctx.save(); ctx.globalAlpha = ta3;
      ctx.fillStyle = "rgba(7,12,17,0.94)";
      ctx.strokeStyle = "rgba(120,200,220,0.35)"; ctx.lineWidth = 1.2;
      ctx.beginPath();
      if (ctx.roundRect) ctx.roundRect(tbX, tbY, tbW, tbH, 9); else ctx.rect(tbX, tbY, tbW, tbH);
      ctx.fill(); ctx.stroke();
      const rows3 = [
        ["\\mathbf{a}(\\xi)_i=e^{\\,j\\frac{4\\pi}{\\lambda}b_i\\xi/r_0}", ts < B4, "#7cff9b"],
        ["P=\\mathbf{a}^{H}\\hat{\\mathbf{R}}\\,\\mathbf{a}", ts >= B4 && ts < C0, "rgba(206,229,223,0.95)"],
        ["P(\\xi)=\\dfrac{1}{\\mathbf{a}^{H}\\hat{\\mathbf{R}}^{-1}\\mathbf{a}}", ts >= C0, "#35e6d0"],
      ];
      rows3.forEach(([tex3, act3, col3], i3) => {
        const ry = tbY + 14 + i3 * 38;
        const ra = ta3 * (act3 ? 1 : 0.4);
        if (act3) {
          ctx.save(); ctx.globalAlpha = ra * 0.16;
          ctx.fillStyle = col3;
          if (ctx.roundRect) { ctx.beginPath(); ctx.roundRect(tbX + 6, ry - 2, tbW - 12, 34, 5); ctx.fill(); } else ctx.fillRect(tbX + 6, ry - 2, tbW - 12, 34);
          ctx.restore();
          ctx.save(); ctx.globalAlpha = ra;
          ctx.fillStyle = col3;
          ctx.fillRect(tbX + 8, ry + 2, 3, 26);
          ctx.restore();
        }
        this._texDraw(tex3, tbX + 20, ry + 2, 14, { color: act3 ? col3 : "rgba(206,229,223,0.8)", alpha: ra });
      });
      ctx.save(); ctx.globalAlpha = ta3 * 0.45;
      ctx.strokeStyle = "rgba(120,200,220,0.5)"; ctx.lineWidth = 1;
      ctx.beginPath(); ctx.moveTo(tbX + 12, footY - 10); ctx.lineTo(tbX + tbW - 12, footY - 10); ctx.stroke();
      ctx.restore();
      ctx.save(); ctx.globalAlpha = ta3 * 0.6;
      ctx.font = "11px 'IBM Plex Mono', monospace"; ctx.fillStyle = "#ffcf6b";
      ctx.fillText("PyRat tomo.fusartomo", tbX + 12, footY + 8);
      ctx.restore();
      ctx.restore();
    }

    const TR0 = 36.0;
    const drawTomo = (cv, X, Y, W, H, frac, scanCol) => {
      const shown = Math.max(1, Math.round(frac * d.TC));
      ctx.imageSmoothingEnabled = false;
      ctx.drawImage(cv, 0, 0, shown, d.TZ, X, Y, (shown / d.TC) * W, H);
      ctx.imageSmoothingEnabled = true;
      ctx.strokeStyle = "rgba(120,200,220,0.35)"; ctx.lineWidth = 1.2;
      ctx.strokeRect(X, Y, W, H);
      if (frac < 1 && scanCol) {
        const fx = X + frac * W;
        ctx.strokeStyle = scanCol; ctx.lineWidth = 1.6;
        ctx.beginPath(); ctx.moveTo(fx, Y); ctx.lineTo(fx, Y + H); ctx.stroke();
      }
    };

    if (tomoP > 0 && ts < TR0) {
      const build = this._ease(c01((ts - D0 - 0.6) / 3.2));
      ctx.save(); ctx.globalAlpha = tomoP;
      drawTomo(d.tomoCv, pad.l, pad.t, plotW, plotH, build, "#7cff9b");
      ctx.font = "13px 'IBM Plex Mono', monospace";
      ctx.fillStyle = "rgba(214,234,229,0.95)";
      ctx.fillText("range ->", w - pad.r - 64, h - pad.b + 18);
      ctx.save(); ctx.translate(pad.l - 18, pad.t + 110); ctx.rotate(-Math.PI / 2);
      ctx.fillText("elevation  -20 .. 80 m", 0, 0); ctx.restore();
      if (build >= 1) {
        const la = this._ease(c01((ts - D0 - 4.2) / 0.7));
        ctx.save(); ctx.globalAlpha = la * tomoP;
        ctx.strokeStyle = "rgba(255,207,107,0.55)"; ctx.setLineDash([4, 4]); ctx.lineWidth = 1.2;
        ctx.beginPath();
        for (let i = 0; i <= 70; i++) {
          const x = i / 70;
          const Y = pad.t + (1 - (d.dem(x) - d.ZMIN) / (d.ZMAX - d.ZMIN)) * plotH;
          i ? ctx.lineTo(pad.l + x * plotW, Y) : ctx.moveTo(pad.l + x * plotW, Y);
        }
        ctx.stroke(); ctx.setLineDash([]);
        ctx.fillStyle = "#ffcf6b";
        ctx.fillText("DEM ground line", pad.l + plotW * 0.04, pad.t + (1 - (d.dem(0.08) - d.ZMIN) / 100) * plotH - 8);
        ctx.restore();
      }
      ctx.restore();
    }

    if (ts >= TR0) {
      const e1 = ts - TR0;
      const tw2 = Math.min(360, w * 0.34), th2 = Math.min(180, h * 0.36);
      const tlX = w * 0.10, tlY = h * 0.24;
      const blX = w * 0.10, blY = h * 0.24 + th2 + 64;
      const shrink = this._ease(c01(e1 / 1.5));
      const fX = this._lerp(pad.l, tlX, shrink);
      const fY = this._lerp(pad.t, tlY, shrink);
      const fW = this._lerp(plotW, tw2, shrink);
      const fH = this._lerp(plotH, th2, shrink);
      ctx.save();
      drawTomo(d.tomoCv, fX, fY, fW, fH, 1, null);
      if (shrink >= 1) {
        this._prChip("tomogram_full · (H, Az, Rg) · param_tag · ground truth", tlX, tlY - 12, "#7cff9b", c01((e1 - 1.5) / 0.5));
      }
      const rb = this._ease(c01((e1 - 1.5) / 2.5));
      if (rb > 0) {
        drawTomo(d.tomoCvReduced, blX, blY, tw2, th2, rb, "#7cff9b");
        if (rb >= 1) this._prChip("Capon (reduced) · (H, Az, Rg) · re-synthesised at inference", blX, blY - 12, "#35e6d0", c01((e1 - 4.0) / 0.5));
      }
      if (e1 >= 4.0) {
        const ca2 = this._ease(c01((e1 - 4.0) / 0.6));
        ctx.save(); ctx.globalAlpha = ca2;
        ctx.font = "13px 'IBM Plex Mono', monospace";
        const cxN = tlX + tw2 + 24;
        ctx.fillStyle = "#ffcf6b";
        ctx.fillText("resolution reference", cxN, tlY + th2 / 2);
        ctx.fillText("few-pass scenario the model faces", cxN, blY + th2 / 2);
        ctx.restore();
      }
      ctx.restore();
    }

    let cap;
    if (ts < A2) cap = "Capon on the FULL stack  ·  select = \"*\" (all passes)  ·  Boxcar window 20 x 10";
    else if (ts < 5.7) cap = "ONE sample = ONE window pixel  ·  y holds 5 complex numbers: the same pixel seen by the passes";
    else if (ts < A3) cap = "Multiply: cell (i, j) = y\u1d62·y\u2c7c*  ·  the phase RELATION between pass i and pass j  ->  one 5x5 layer";
    else if (ts < A4) cap = "Second sample: different absolute phase, the SAME relative pattern — that is what averaging keeps";
    else if (ts < A5) cap = "Sweep the window: 200 samples  ->  averaged into the covariance R (effective looks are fewer — windows overlap)";
    else if (ts < B0) cap = "Divide by L  ->  R  ·  Hermitian, and its first ROW holds the measured pass-to-pass phase pattern";
    else if (ts < B2) cap = "Pull the MEASURED pattern out of R (white arrows)  ·  now guess a height and compare";
    else if (ts < B3) cap = "Candidate ξ = 0 m: the predicted pattern (green) ALIGNS with the measurement  ->  strong P(0)";
    else if (ts < B4) cap = "Candidate ξ = 40 m: prediction and measurement DISAGREE  ->  P(40) ≈ 0 · nothing at 40 m";
    else if (ts < C0) cap = "Now sweep EVERY height — that is beamforming  ·  but the lobe is wide: a short aperture blurs";
    else if (ts < C2) cap = "Capon: keep gain 1 at ξ and MINIMISE all other heights  ->  leakage suppressed, peaks sharpen";
    else if (ts < D0) cap = "Ground and canopy resolved below the Rayleigh limit (illustrative two-target demo)";
    else if (ts < TR0) cap = "Repeated for every pixel: tomogram (H, Az, Rg)  ·  height_range = [-20, 80] m  ->  tomogram_full";
    else if (ts < TR0 + 4.0) cap = "Pre-processing beamforms ONCE (full stack)  ·  the few-pass Capon baseline is re-synthesised at inference";
    else cap = "full = ground-truth resolution reference  ·  reduced Capon = the operational few-pass baseline at inference";
    this._cap(cap);
  }

  _prCard(x, y, cw, ch, title, sub, color, alpha) {
    const { ctx } = this;
    if (alpha <= 0) return;
    ctx.save(); ctx.globalAlpha = alpha;
    ctx.fillStyle = "rgba(7,12,17,0.94)";
    ctx.strokeStyle = color; ctx.lineWidth = 1.3;
    ctx.beginPath();
    if (ctx.roundRect) ctx.roundRect(x, y, cw, ch, 8); else ctx.rect(x, y, cw, ch);
    ctx.fill(); ctx.stroke();
    ctx.fillStyle = color; ctx.fillRect(x, y + 6, 3, ch - 12);
    ctx.font = "12px 'IBM Plex Mono', monospace";
    ctx.fillStyle = color;
    ctx.fillText(title, x + 12, y + 22);
    ctx.font = "11px 'IBM Plex Mono', monospace";
    ctx.fillStyle = "rgba(147,167,180,0.95)";
    ctx.fillText(sub, x + 12, y + 40);
    ctx.restore();
  }

  _prWorkers(ts, d) {
    const { ctx, w, h } = this;
    const c01 = d.c01;

    const M = 5, P = 3;
    const cropX = w * 0.12, cropY = h * 0.14, cropW = w * 0.76, cropH = 56;
    const subW = cropW / M;

    const appear = this._ease(c01(ts / 0.6));
    ctx.save(); ctx.globalAlpha = appear;
    for (let s2 = 0; s2 < M; s2++) {
      ctx.fillStyle = `rgba(53,230,208,${0.10 + 0.05 * (s2 % 2)})`;
      ctx.fillRect(cropX + s2 * subW, cropY, subW - 1, cropH);
    }
    ctx.strokeStyle = "rgba(120,200,220,0.5)"; ctx.lineWidth = 1.3;
    ctx.strokeRect(cropX, cropY, cropW, cropH);
    ctx.font = "13px 'IBM Plex Mono', monospace";
    ctx.fillStyle = "rgba(214,234,229,0.95)";
    ctx.fillText("azimuth crop · W_az", cropX, cropY - 10);
    ctx.restore();

    const cut = this._ease(c01((ts - 0.4) / 1.1));
    if (cut > 0) {
      ctx.save(); ctx.globalAlpha = cut;
      ctx.strokeStyle = "#ffcf6b"; ctx.lineWidth = 1.3; ctx.setLineDash([5, 4]);
      for (let s2 = 1; s2 < M; s2++) {
        const X = cropX + s2 * subW;
        ctx.beginPath(); ctx.moveTo(X, cropY - 6); ctx.lineTo(X, cropY + cropH + 6); ctx.stroke();
      }
      ctx.setLineDash([]);
      ctx.fillStyle = "#ffcf6b"; ctx.font = "12px 'IBM Plex Mono', monospace";
      ctx.fillText("W_max = 1000 lines", cropX + cropW - 150, cropY + cropH + 22);
      ctx.restore();
    }

    const wkY = h * 0.46, wkW = w * 0.135, wkH = 58;
    const wkGap = (w - 2 * cropX - P * wkW) / (P - 1);
    const wkX = (i) => cropX + i * (wkW + wkGap);

    for (let s2 = 0; s2 < M; s2++) {
      const dp = this._ease(c01((ts - 1.5 - s2 * 0.12) / 0.7));
      if (dp <= 0) continue;
      const slot = s2 % P;
      const queued = s2 >= P;
      const qoff = queued ? wkH + 16 : 0;
      const sx = cropX + s2 * subW + subW / 2;
      const tx = wkX(slot) + wkW / 2;
      const X = this._lerp(sx, tx, dp);
      const Y = this._lerp(cropY + cropH / 2, wkY + wkH / 2, dp) + qoff;
      ctx.save(); ctx.globalAlpha = queued ? dp * 0.5 : dp;
      ctx.fillStyle = "rgba(7,12,17,0.92)";
      ctx.strokeStyle = queued ? "rgba(53,230,208,0.55)" : "#35e6d0"; ctx.lineWidth = 1.3;
      const bw = this._lerp(subW - 6, wkW, dp), bh = this._lerp(cropH, queued ? wkH - 14 : wkH, dp);
      ctx.beginPath();
      if (ctx.roundRect) ctx.roundRect(X - bw / 2, Y - bh / 2, bw, bh, 7); else ctx.rect(X - bw / 2, Y - bh / 2, bw, bh);
      ctx.fill(); ctx.stroke();
      if (dp >= 1) {
        ctx.font = "12px 'IBM Plex Mono', monospace";
        ctx.fillStyle = queued ? "rgba(53,230,208,0.7)" : "#35e6d0";
        if (queued) {
          ctx.fillText(`#${String(s2).padStart(4, "0")} · queued`, X - bw / 2 + 8, Y + 4);
        } else {
          ctx.fillText(`PyRatJob #${String(s2).padStart(4, "0")}`, X - bw / 2 + 8, Y - 2);
          ctx.fillStyle = "rgba(147,167,180,0.9)";
          ctx.fillText("running", X - bw / 2 + 8, Y + 14);
        }
      }
      ctx.restore();
    }
    if (ts >= 2.2) {
      ctx.save(); ctx.globalAlpha = this._ease(c01((ts - 2.2) / 0.5));
      ctx.font = "13px 'IBM Plex Mono', monospace";
      ctx.fillStyle = "rgba(214,234,229,0.95)";
      ctx.fillText("fewest-waves worker x thread plan, threads ≤ 16 (spawn)", cropX, wkY - 14);
      ctx.restore();
    }

    const stackY = h * 0.80, stackW = w * 0.42, stackX = w / 2 - stackW / 2, stackH = 46;
    const partW = stackW / M;
    for (let s2 = 0; s2 < M; s2++) {
      const ep = this._ease(c01((ts - 3.0 - s2 * 0.1) / 0.8));
      if (ep <= 0) continue;
      const slot = s2 % P;
      const sx = wkX(slot) + wkW / 2;
      const tx = stackX + s2 * partW + partW / 2;
      const X = this._lerp(sx, tx, ep);
      const Y = this._lerp(wkY + wkH, stackY + stackH / 2, ep);
      const conc = this._ease(c01((ts - 4.5) / 1.3));
      ctx.save(); ctx.globalAlpha = ep;
      ctx.fillStyle = `rgba(124,255,155,${0.18 + 0.10 * (s2 % 2)})`;
      const fx = this._lerp(X - partW / 2 + 3, stackX + s2 * partW, conc);
      ctx.fillRect(fx, Y - stackH / 2, partW - (conc < 1 ? 6 : 1), stackH);
      ctx.strokeStyle = "#7cff9b"; ctx.lineWidth = 1.2;
      ctx.strokeRect(fx, Y - stackH / 2, partW - (conc < 1 ? 6 : 1), stackH);
      if (ep >= 1 && conc < 0.6) {
        ctx.font = "10px 'IBM Plex Mono', monospace";
        ctx.fillStyle = "#7cff9b";
        ctx.fillText("partial.h5", fx + 4, Y + 4);
      }
      ctx.restore();
    }
    const conc = this._ease(c01((ts - 4.5) / 1.3));
    if (conc > 0) {
      ctx.save(); ctx.globalAlpha = conc;
      ctx.font = "13px 'IBM Plex Mono', monospace";
      ctx.fillStyle = "rgba(214,234,229,0.95)";
      ctx.fillText("HDF5 partials {DEM, tomogram} -> concatenated along azimuth", stackX, stackY - 16);
      if (conc < 1) {
        ctx.strokeStyle = "#7cff9b"; ctx.lineWidth = 1.4;
        for (let s2 = 1; s2 < M; s2++) {
          const X = stackX + s2 * partW;
          ctx.globalAlpha = conc * (0.5 + 0.5 * Math.sin(this.t * 8 + s2));
          ctx.beginPath(); ctx.moveTo(X, stackY - 4); ctx.lineTo(X, stackY + stackH + 4); ctx.stroke();
        }
      }
      ctx.restore();
    }

    let cap;
    if (ts < 1.5) cap = "One Capon job would blow PyRat's memory  ·  split the azimuth crop into M = ceil(W_az / W_max) subsections";
    else if (ts < 3.0) cap = "Each subsection -> one PyRatJob  ·  a core budget (effort high = 80% of cores) picks the worker x thread plan with the fewest waves";
    else if (ts < 4.5) cap = "(PyRat holds GDAL + Qt in process globals -> every call must run in its own subprocess)";
    else cap = "Workers write HDF5 partials {DEM, tomogram}  ·  reassembled along azimuth -> one array";
    this._cap(cap);
  }

  _prArtifacts(ts, d) {
    const { ctx, w, h } = this;
    const c01 = d.c01;

    const frX = w * 0.06, frY = h * 0.12, frW = w * 0.88, frH = h * 0.62;
    const fa = this._ease(c01(ts / 0.8));
    ctx.save(); ctx.globalAlpha = fa;
    ctx.fillStyle = "rgba(4,7,10,0.55)";
    ctx.strokeStyle = "rgba(120,200,220,0.3)"; ctx.lineWidth = 1.2;
    ctx.beginPath();
    if (ctx.roundRect) ctx.roundRect(frX, frY, frW, frH, 10); else ctx.rect(frX, frY, frW, frH);
    ctx.fill(); ctx.stroke();
    ctx.font = "14px 'IBM Plex Mono', monospace";
    ctx.fillStyle = "rgba(214,234,229,0.95)";
    ctx.fillText("data directory · 6 artifacts", frX + 16, frY - 10);
    ctx.restore();

    const cards = [
      ["tomogram_full", "(H,Az,Rg) · param_tag", "#7cff9b"],
            ["dem_full", "(Az,Rg) · param_tag", "#ffcf6b"],
            ["primary", "(Az,Rg) cplx · tomo_tag", "#35e6d0"],
      ["secondaries", "(Ns,Az,Rg) cplx", "#35e6d0"],
      ["interferograms", "(Ns,Az,Rg) cplx", "#35e6d0"],
      ["track_profiles", "(Nt,Az) h+v · npz", "#ffcf6b"],
    ];
    const cols = 4, cw = (frW - 40) / cols, ch = 56;
    const gx = frX + 20, gy = frY + 28;
    cards.forEach(([title, sub, color], i) => {
      const row = Math.floor(i / cols), col = i % cols;
      const ca = this._ease(c01((ts - 4.0 - i * 1.0) / 0.7));
      this._prCard(gx + col * cw, gy + row * (ch + 16), cw - 8, ch, title, sub, color, ca);
    });

    const jsA = this._ease(c01((ts - 13.0) / 0.8));
    if (jsA > 0) {
      const jx = frX + 20, jy = gy + 2 * (ch + 16), jw = frW - 40, jh = 70;
      ctx.save(); ctx.globalAlpha = jsA;
      ctx.fillStyle = "rgba(7,12,17,0.94)";
      ctx.strokeStyle = "#7cff9b"; ctx.lineWidth = 1.3;
      ctx.beginPath();
      if (ctx.roundRect) ctx.roundRect(jx, jy, jw, jh, 8); else ctx.rect(jx, jy, jw, jh);
      ctx.fill(); ctx.stroke();
      ctx.font = "13px 'IBM Plex Mono', monospace";
      ctx.fillStyle = "#7cff9b";
      ctx.fillText("dataset.json", jx + 14, jy + 22);
      const keys = ["{ global_crop", "dataset_type", "tomogram_tag", "parameter_tag", "pass_labels", "artifacts{...} }"];
      const nk = Math.min(keys.length, Math.floor((ts - 13.5) / 0.8) + 1);
      ctx.font = "12px 'IBM Plex Mono', monospace";
      ctx.fillStyle = "rgba(147,167,180,0.95)";
      for (let k = 0; k < nk; k++) ctx.fillText(keys[k], jx + 14 + (k % 3) * (jw / 3), jy + 44 + Math.floor(k / 3) * 20);
      ctx.restore();

      if (ts >= 18.0) {
        const pa = this._ease(c01((ts - 18.0) / 0.8));
        ctx.save(); ctx.globalAlpha = pa * 0.6;
        ctx.font = "12px 'IBM Plex Mono', monospace";
        ctx.fillStyle = "#5e7280";
        ctx.fillText("config_state.json  +  baselines.json  +  meta_<stage>.txt", jx + 14, jy + jh + 16);
        ctx.restore();
      }
    }

    let cap;
    if (ts < 4.0) cap = "Six artifacts per run  ·  tomogram, DEM, three complex stacks, and per-azimuth track profiles";
    else if (ts < 13.0) cap = "tomogram_full = ground-truth reference (param_tag)  ·  inputs hold ALL passes, secondaries selected at training";
    else if (ts < 18.0) cap = "A self-describing dataset.json records the crop, tags, pass labels, and every filename";
    else cap = "...alongside config_state.json, baselines.json + per-stage meta_*.txt  ·  overview plots render last";
    this._cap(cap);
  }


  /* ---------- dataset: crop/split -> patch grid -> tensors -> normalize -> augment -> loaders ---------- */

  _dataset() {
    const { ctx, w, h } = this;
    const T = 118, tt = this.t % T;
    const c01 = (v) => Math.min(1, Math.max(0, v));
    const frac = (v) => v - Math.floor(v);
    const rnd = (i) => frac(Math.sin(i * 127.1 + 311.7) * 43758.5453);
    const tex = (ix, iy) => {
      let v = 0.42 + 0.3 * Math.sin(ix * 0.31 + Math.sin(iy * 0.17) * 2.1) * Math.cos(iy * 0.23 + Math.sin(ix * 0.11) * 1.7);
      v += 0.16 * Math.sin(ix * 1.3 + iy * 0.9) * Math.sin(ix * 0.7 - iy * 1.1);
      if (rnd(ix * 131 + iy * 57) > 0.965) v += 0.5;
      return Math.min(1, Math.max(0.05, v));
    };
    const field = (x, y, wd, ht, alpha, cell, map) => {
      const nx = Math.max(1, Math.floor(wd / cell)), ny = Math.max(1, Math.floor(ht / cell));
      for (let j = 0; j < ny; j++) {
        for (let i = 0; i < nx; i++) {
          const m = map ? map(i, j) : [i, j];
          ctx.fillStyle = `rgba(53,230,208,${(0.05 + tex(m[0], m[1]) * 0.3) * alpha})`;
          ctx.fillRect(x + i * cell, y + j * cell, cell - 1, cell - 1);
        }
      }
    };
    const fringes = (x, y, wd, ht, alpha, ph) => {
      const cell = 5, nx = Math.max(1, Math.floor(wd / cell)), ny = Math.max(1, Math.floor(ht / cell));
      for (let j = 0; j < ny; j++) {
        for (let i = 0; i < nx; i++) {
          const v = 0.5 + 0.5 * Math.sin((i + j * 1.7) * 0.42 + ph * 1.9);
          ctx.fillStyle = `rgba(255,207,107,${(0.05 + v * 0.32) * alpha})`;
          ctx.fillRect(x + i * cell, y + j * cell, cell - 1, cell - 1);
        }
      }
    };
    const label = (txt, x, y, color, size) => {
      ctx.fillStyle = color || "rgba(206,228,222,0.9)";
      ctx.font = `${size || 13}px 'IBM Plex Mono', monospace`;
      ctx.fillText(txt, x, y);
    };
    const centerLabel = (txt, cx2, y, color, size) => {
      ctx.font = `${size || 13}px 'IBM Plex Mono', monospace`;
      const tw2 = ctx.measureText(txt).width;
      ctx.fillStyle = color || "rgba(206,228,222,0.9)";
      ctx.fillText(txt, cx2 - tw2 / 2, y);
    };
    const chip = (txt, x, y, color, alpha, size) => {
      const fs3 = size || 13;
      ctx.font = `${fs3}px 'IBM Plex Mono', monospace`;
      const tw = ctx.measureText(txt).width + 20;
      if (alpha != null && alpha <= 0) return tw;
      ctx.save(); ctx.globalAlpha = alpha == null ? 1 : alpha;
      ctx.fillStyle = "rgba(7,12,17,0.92)"; ctx.strokeStyle = color; ctx.lineWidth = 1.2;
      const ch4 = fs3 + 11;
      ctx.beginPath();
      if (ctx.roundRect) ctx.roundRect(x, y - ch4 + 8, tw, ch4, 6); else ctx.rect(x, y - ch4 + 8, tw, ch4);
      ctx.fill(); ctx.stroke();
      ctx.fillStyle = color; ctx.font = `${fs3}px 'IBM Plex Mono', monospace`; ctx.fillText(txt, x + 10, y + 1);
      ctx.restore();
      return tw;
    };
    const arrow = (x1, y1, x2, y2, color) => {
      ctx.strokeStyle = color; ctx.fillStyle = color; ctx.lineWidth = 1.6;
      ctx.beginPath(); ctx.moveTo(x1, y1); ctx.lineTo(x2, y2); ctx.stroke();
      const a = Math.atan2(y2 - y1, x2 - x1);
      ctx.beginPath(); ctx.moveTo(x2, y2);
      ctx.lineTo(x2 - 7 * Math.cos(a - 0.4), y2 - 7 * Math.sin(a - 0.4));
      ctx.lineTo(x2 - 7 * Math.cos(a + 0.4), y2 - 7 * Math.sin(a + 0.4));
      ctx.closePath(); ctx.fill();
    };

    const elbow = (pts, color) => {
      ctx.strokeStyle = color; ctx.fillStyle = color; ctx.lineWidth = 1.8;
      ctx.beginPath(); ctx.moveTo(pts[0][0], pts[0][1]);
      for (let i = 1; i < pts.length; i++) ctx.lineTo(pts[i][0], pts[i][1]);
      ctx.stroke();
      const x2 = pts[pts.length - 1][0], y2 = pts[pts.length - 1][1];
      const x1 = pts[pts.length - 2][0], y1 = pts[pts.length - 2][1];
      const a = Math.atan2(y2 - y1, x2 - x1);
      ctx.beginPath(); ctx.moveTo(x2, y2);
      ctx.lineTo(x2 - 7 * Math.cos(a - 0.4), y2 - 7 * Math.sin(a - 0.4));
      ctx.lineTo(x2 - 7 * Math.cos(a + 0.4), y2 - 7 * Math.sin(a + 0.4));
      ctx.closePath(); ctx.fill();
    };

    const A1 = 16.0, A2 = 44.0, A3 = 62.0, A4 = 80.0, A5 = 104.0;
    let caption = "";

    if (tt < A1) {
      const sx = 64, sy = 46, sw2 = w * 0.58, sh2 = h - 110;
      const born = this._ease(c01(tt / 1.6));
      field(sx, sy, sw2 * born, sh2, 0.85, 7);
      ctx.strokeStyle = "rgba(120,200,220,0.45)"; ctx.lineWidth = 1.4;
      ctx.strokeRect(sx, sy, sw2, sh2);
      centerLabel("azimuth ->", sx + sw2 / 2, sy + sh2 + 22);
      ctx.save(); ctx.translate(sx - 14, sy + sh2 / 2 + 32); ctx.rotate(-Math.PI / 2); label("range ->", 0, 0); ctx.restore();

      const ax = sx + sw2 + 40;
      const atW = w - ax - 44;
      const arts = [
        { n: "primary", d: "1 reference pass (PS02)", c: "#35e6d0" },
        { n: "secondaries", d: "selected aligned passes", c: "rgba(178,204,210,0.95)" },
        { n: "interferograms", d: "selected complex interferograms", c: "#ffcf6b" },
        { n: "parameters", d: "GMM targets · param pipeline", c: "#7cff9b" },
        { n: "dem_full", d: "optional channel · off here", c: "rgba(178,204,210,0.95)" },
      ];
      const atY = sy + 12;
      const tA = c01((tt - 0.4) / 0.6);
      if (tA > 0) {
        ctx.save(); ctx.globalAlpha = tA;
        ctx.fillStyle = "rgba(7,12,17,0.9)";
        ctx.strokeStyle = "rgba(120,200,220,0.3)"; ctx.lineWidth = 1.2;
        ctx.beginPath();
        if (ctx.roundRect) ctx.roundRect(ax - 14, atY - 24, atW + 28, 5 * 42 + 88, 10); else ctx.rect(ax - 14, atY - 24, atW + 28, 5 * 42 + 88);
        ctx.fill(); ctx.stroke();
        label("input artifacts", ax, atY, "#e6f7f3", 15);
        ctx.strokeStyle = "rgba(120,200,220,0.25)";
        ctx.beginPath(); ctx.moveTo(ax - 4, atY + 12); ctx.lineTo(ax + atW + 4, atY + 12); ctx.stroke();
        ctx.restore();
      }
      arts.forEach((r, i) => {
        const ra = this._ease(c01((tt - 0.8 - i * 0.35) / 0.5));
        if (ra <= 0) return;
        const yR = atY + 38 + i * 42;
        ctx.save(); ctx.globalAlpha = ra;
        ctx.fillStyle = r.c;
        ctx.beginPath(); ctx.arc(ax + 5, yR - 5, 3, 0, 7); ctx.fill();
        label(r.n, ax + 18, yR, r.c, 14);
        label(r.d, ax + 18, yR + 16, "rgba(206,228,222,0.85)", 12);
        ctx.restore();
      });
      if (tt > 2.8) label("memory-mapped · nothing loaded", ax, atY + 38 + 5 * 42 + 6, "rgba(206,228,222,0.85)", 12);

      const x70 = sx + sw2 * 0.800, x85 = sx + sw2 * 0.900;
      if (tt >= 2.2 && tt < 3.6) {
        const gp = this._ease(c01((tt - 2.2) / 1.2));
        ctx.strokeStyle = `rgba(255,207,107,${0.85 * gp})`; ctx.setLineDash([7, 5]); ctx.lineWidth = 1.6;
        ctx.strokeRect(sx - 7, sy - 7, sw2 + 14, sh2 + 14);
        ctx.setLineDash([]);
        label("global crop (from dataset.json)", sx, sy + sh2 + 44, "rgba(255,207,107,0.9)");
      }
      if (tt >= 3.6) {
        ctx.strokeStyle = "rgba(255,207,107,0.55)"; ctx.setLineDash([7, 5]); ctx.lineWidth = 1.4;
        ctx.strokeRect(sx - 7, sy - 7, sw2 + 14, sh2 + 14);
        ctx.setLineDash([]);
        const p1 = this._ease(c01((tt - 3.6) / 2.4));
        const cx1 = sx + (x70 - sx) * p1;
        ctx.fillStyle = "rgba(53,230,208,0.10)"; ctx.fillRect(sx, sy, cx1 - sx, sh2);
        ctx.strokeStyle = "#35e6d0"; ctx.lineWidth = 1.6;
        ctx.beginPath(); ctx.moveTo(cx1, sy); ctx.lineTo(cx1, sy + sh2); ctx.stroke();
        if (p1 >= 1) {
          centerLabel("train 1000–13000", sx + (x70 - sx) / 2, sy - 28, "#35e6d0", 13);
          centerLabel("≈ 80%", sx + (x70 - sx) / 2, sy - 12, "rgba(206,228,222,0.7)", 12);
        }
      }
      if (tt >= 6.6) {
        const p2 = this._ease(c01((tt - 6.6) / 1.8));
        const cx2 = x70 + (x85 - x70) * p2;
        ctx.fillStyle = "rgba(255,207,107,0.10)"; ctx.fillRect(x70, sy, cx2 - x70, sh2);
        ctx.strokeStyle = "#ffcf6b"; ctx.lineWidth = 1.6;
        ctx.beginPath(); ctx.moveTo(cx2, sy); ctx.lineTo(cx2, sy + sh2); ctx.stroke();
        if (p2 >= 1) {
          ctx.fillStyle = "rgba(124,255,155,0.08)"; ctx.fillRect(x85, sy, sx + sw2 - x85, sh2);
          centerLabel("val 13000–14500", (x70 + x85) / 2, sy - 44, "#ffcf6b", 13);
          centerLabel("≈ 10%", (x70 + x85) / 2, sy - 28, "rgba(206,228,222,0.7)", 12);
          centerLabel("test 14500–16000", (x85 + sx + sw2) / 2, sy - 76, "#7cff9b", 13);
          centerLabel("≈ 10%", (x85 + sx + sw2) / 2, sy - 60, "rgba(206,228,222,0.7)", 12);
        }
      }
      if (tt >= 9.6 && tt < 12.2) {
        const gp = this._ease(c01((tt - 9.6) / 1.2));
        ctx.save(); ctx.globalAlpha = gp;
        label("global crop is read from dataset.json  ·  splits are carved out of it", sx, sy + sh2 + 44, "rgba(255,207,107,0.9)");
        label("default ratios 70/15/15 · production uses explicit bounds", sx, sy + sh2 + 62, "rgba(206,228,222,0.7)", 12);
        ctx.restore();
      }
      if (tt >= 12.2) {
        const pulse = 0.5 + 0.5 * Math.sin(this.t * 4);
        ctx.strokeStyle = `rgba(53,230,208,${0.45 + 0.45 * pulse})`; ctx.lineWidth = 2.2;
        ctx.strokeRect(sx, sy, x70 - sx, sh2);
        const rp = this._ease(c01((tt - 12.6) / 2.0));
        if (rp > 0) {
          const bw5 = (x70 - sx) * 0.62, bh5 = sh2 * 0.32;
          const bx5 = sx + ((x70 - sx) - bw5) / 2, by5 = sy + sh2 * 0.42;
          ctx.save(); ctx.globalAlpha = rp;
          ctx.fillStyle = "rgba(4,7,10,0.9)"; ctx.fillRect(bx5 - 8, by5 - 26, bw5 + 16, bh5 + 52);
          field(bx5, by5, bw5, bh5, 0.95, 7);
          ctx.strokeStyle = "#35e6d0"; ctx.lineWidth = 1.6; ctx.strokeRect(bx5, by5, bw5, bh5);
          centerLabel("inputs_split (n_passes, az, rg)", bx5 + bw5 / 2, by5 + bh5 + 18, "#35e6d0", 13);
          centerLabel("materialized into one RAM buffer", bx5 + bw5 / 2, by5 - 12, "rgba(206,228,222,0.9)", 12);
          ctx.restore();
        }
      }

      if (tt < 3.6) caption = "The processed artifacts are opened as memory-mapped files  ·  the data stays on disk";
      else if (tt < 6.6) caption = "The scene is split along azimuth  ·  production uses explicit bounds, train az 1000–13000 (≈80%)";
      else if (tt < 9.6) caption = "val az 13000–14500 (≈10%)  ·  test az 14500–16000 (≈10%)  ·  three disjoint azimuth windows";
      else if (tt < 12.2) caption = "The global crop is fixed (from dataset.json)  ·  each split maps into its local frame";
      else caption = "Loading the train window  ·  1 primary + 4 secondaries + 4 interferograms copied into one stacked RAM buffer";
    } else if (tt < A2) {
      const ts = tt - A1;
      const kk = Math.min((w - 380) / 336, (h - 130) / 146);
      const gx = 64, gy = 70;
      const gw = 336 * kk, gh = 146 * kk, ps = 64 * kk, st = 32 * kk;
      const padL = 8 * kk, padT = 7 * kk;
      const fx = gx + gw + 48;

      field(gx, gy, gw, gh, 0.55, 7);
      ctx.strokeStyle = "rgba(120,200,220,0.5)"; ctx.lineWidth = 1.4; ctx.strokeRect(gx, gy, gw, gh);
      label("train split   W = 336   H = 146", gx, 38, "rgba(206,228,222,0.95)", 14);

      const mirrorBands = (alpha) => {
        const nxs = Math.floor(gw / 7), nys = Math.floor(gh / 7);
        field(gx - padL, gy, padL, gh, alpha, 7, (i, j) => [Math.floor(padL / 7) - i, j]);
        field(gx + gw, gy, padL, gh, alpha, 7, (i, j) => [nxs - 1 - i, j]);
        field(gx, gy - padT, gw, padT, alpha, 7, (i, j) => [i, Math.floor(padT / 7) - j]);
        field(gx, gy + gh, gw, padT, alpha, 7, (i, j) => [i, nys - 1 - j]);
        ctx.strokeStyle = `rgba(53,230,208,${0.8 * Math.min(1, alpha * 2)})`; ctx.setLineDash([6, 4]); ctx.lineWidth = 1.4;
        ctx.strokeRect(gx - padL, gy - padT, gw + 2 * padL, gh + 2 * padT);
        ctx.setLineDash([]);
      };

      if (ts < 3.6) {
        const gp = this._ease(c01(ts / 1.4));
        ctx.fillStyle = "rgba(124,255,155,0.10)"; ctx.fillRect(gx, gy, ps * gp, ps * gp);
        ctx.strokeStyle = "#7cff9b"; ctx.lineWidth = 2; ctx.strokeRect(gx, gy, ps * gp, ps * gp);
        if (gp >= 1) {
          arrow(gx + 4, gy + ps + 18, gx + ps - 4, gy + ps + 18, "#7cff9b");
          arrow(gx + ps - 4, gy + ps + 18, gx + 4, gy + ps + 18, "#7cff9b");
        }
        label("patch = 64 x 64 px", fx, 104, "#7cff9b", 14);
        label("the window anchors at", fx, 138, "rgba(206,228,222,0.9)", 14);
        label("the grid origin", fx, 160, "rgba(206,228,222,0.9)", 14);
        caption = "Patches are 64 x 64 pixels  ·  the first window sits at the grid origin";
      } else if (ts < 8.2) {
        const sp = this._ease(c01((ts - 3.6) / 1.6));
        const x2 = gx + st * sp;
        ctx.strokeStyle = "rgba(124,255,155,0.8)"; ctx.lineWidth = 1.6; ctx.strokeRect(gx, gy, ps, ps);
        ctx.fillStyle = "rgba(255,207,107,0.18)"; ctx.fillRect(x2, gy, gx + ps - x2, ps);
        ctx.strokeStyle = "#35e6d0"; ctx.lineWidth = 2; ctx.strokeRect(x2, gy, ps, ps);
        arrow(gx + 2, gy + ps + 18, gx + st, gy + ps + 18, "#ffcf6b");
        label("stride = 32", fx, 104, "#ffcf6b", 14);
        if (sp >= 1) {
          label("overlap = 64 - 32", fx, 138, "rgba(206,228,222,0.9)", 14);
          label("        = 32 px (50%)", fx, 160, "rgba(206,228,222,0.9)", 14);
        }
        caption = "Stride 32  ·  the next window starts half a patch later, so neighbours overlap by 50%";
      } else if (ts < 14.6) {
        const k = Math.min(9, Math.floor((ts - 8.2) / 0.55));
        for (let i = 0; i < k; i++) {
          ctx.strokeStyle = "rgba(124,255,155,0.22)"; ctx.lineWidth = 1.2;
          ctx.strokeRect(gx + i * st, gy, ps, ps);
        }
        const xk = gx + k * st;
        ctx.strokeStyle = "#7cff9b"; ctx.lineWidth = 2; ctx.strokeRect(xk, gy, ps, ps);
        label(`window ${k + 1} / 10`, gx, gy + gh + padT + 28, "#7cff9b", 14);
        const over = xk + ps - (gx + gw);
        if (over > 0) {
          ctx.fillStyle = "rgba(255,107,125,0.22)"; ctx.fillRect(gx + gw, gy, over, ps);
          ctx.strokeStyle = "rgba(255,107,125,0.8)"; ctx.lineWidth = 1.4; ctx.strokeRect(gx + gw, gy, over, ps);
        }
        this._texDraw("n_h=\\left\\lceil\\frac{336-64}{32}\\right\\rceil+1=10", fx, 96, 15, { color: "rgba(230,247,243,0.95)" });
        if (ts > 11.7) this._texDraw("n_v=\\left\\lceil\\frac{146-64}{32}\\right\\rceil+1=4", fx, 150, 15, { color: "rgba(230,247,243,0.95)", alpha: c01((ts - 11.7) / 0.5) });
        if (over > 0) label("last window: +16 px overshoot", fx, 216, "#ff6b7d", 14);
        caption = k < 9 ? "Counting windows along each axis  ·  round up (size - patch) / stride, then add one" : "The last window overshoots the scene edge  ->  the grid is larger than the scene";
      } else if (ts < 24.0) {
        const pp = this._ease(c01((ts - 14.6) / 1.4));
        mirrorBands(0.5 * pp);
        this._texDraw("\\mathrm{pad}=\\bigl(p+(n-1)s\\bigr)-\\mathrm{size}", fx, 96, 15, { color: "#ffcf6b", alpha: pp });
        this._texDraw("\\mathrm{pad}_h=16\\to 8\\,|\\,8", fx, 132, 14, { color: "#ffcf6b", alpha: pp });
        this._texDraw("\\mathrm{pad}_v=14\\to 7\\,|\\,7", fx, 158, 14, { color: "#ffcf6b", alpha: pp });
        label("symmetric padding (mirror)", fx, 198, "#e6f7f3", 14);
        label("edge pixels mirrored outward", fx, 220, "rgba(206,228,222,0.95)", 13);
        const ziP = ts < 22.0 ? this._ease(c01((ts - 16.2) / 0.8)) : 1 - this._ease(c01((ts - 22.0) / 0.8));
        if (ziP > 0) {
          const pw3 = Math.min(250, (gw + 2 * padL - 56) / 3);
          const ph3 = Math.min(252, gh - 8);
          const py3 = gy + (gh - ph3) / 2;
          const panels = [
            { kind: "side", title: "left edge", ax: gx, ay2: gy + gh * 0.55 },
            { kind: "top", title: "top edge", ax: gx + gw * 0.5, ay2: gy },
            { kind: "corner", title: "corner", ax: gx - padL, ay2: gy - padT },
          ];
          panels.forEach((pn, i) => {
            const txp = gx + 12 + i * (pw3 + 16);
            const x0 = this._lerp(pn.ax, txp, ziP), y0 = this._lerp(pn.ay2, py3, ziP);
            const wI = Math.max(10, pw3 * ziP), hI = Math.max(10, ph3 * ziP);
            ctx.save();
            ctx.globalAlpha = Math.min(1, ziP * 1.5);
            ctx.fillStyle = "rgba(4,7,10,0.96)";
            ctx.fillRect(x0, y0, wI, hI);
            ctx.strokeStyle = "#35e6d0"; ctx.lineWidth = 1.5; ctx.strokeRect(x0, y0, wI, hI);
            if (ziP > 0.85) {
              ctx.beginPath(); ctx.rect(x0, y0, wI, hI); ctx.clip();
              const c0 = pn.kind === "top" ? 0 : -2;
              const r0 = pn.kind === "side" ? 0 : -2;
              const c1 = pn.kind === "top" ? 5 : (pn.kind === "side" ? 4 : 3);
              const r1 = pn.kind === "side" ? 6 : 3;
              const ncol = c1 - c0, nrow = r1 - r0;
              const CZ = Math.min(28, Math.floor((pw3 - 26) / ncol), Math.floor((ph3 - 64) / nrow));
              const ox = x0 + (pw3 - ncol * CZ) / 2 - c0 * CZ;
              const oy = y0 + 44 + (ph3 - 64 - nrow * CZ) / 2 - r0 * CZ;
              for (let r = r0; r < r1; r++) {
                for (let c = c0; c < c1; c++) {
                  const sc = (c >= 0 ? c : -1 - c) + (pn.kind === "top" ? 8 : 0);
                  const sr = (r >= 0 ? r : -1 - r) + (pn.kind === "side" ? 6 : 0);
                  const v = tex(sc, sr);
                  const X = ox + c * CZ, Y = oy + r * CZ;
                  ctx.fillStyle = `rgba(53,230,208,${0.08 + v * 0.34})`;
                  ctx.fillRect(X + 1, Y + 1, CZ - 2, CZ - 2);
                  if (c < 0 || r < 0) { ctx.strokeStyle = "rgba(255,207,107,0.55)"; ctx.lineWidth = 1; ctx.strokeRect(X + 1, Y + 1, CZ - 2, CZ - 2); }
                }
              }
              ctx.strokeStyle = "#35e6d0"; ctx.setLineDash([5, 4]); ctx.lineWidth = 2;
              if (c0 < 0) { ctx.beginPath(); ctx.moveTo(ox, oy + r0 * CZ - 6); ctx.lineTo(ox, oy + r1 * CZ + 6); ctx.stroke(); }
              if (r0 < 0) { ctx.beginPath(); ctx.moveTo(ox + c0 * CZ - 6, oy); ctx.lineTo(ox + c1 * CZ + 6, oy); ctx.stroke(); }
              ctx.setLineDash([]);
              const cc = (c, r) => [ox + c * CZ + CZ / 2, oy + r * CZ + CZ / 2];
              if (pn.kind === "side") {
                const a1 = cc(0, 1), b1 = cc(-1, 1);
                elbow([[a1[0], a1[1]], [a1[0], a1[1] - CZ * 0.95], [b1[0], b1[1] - CZ * 0.95], [b1[0], b1[1] - 7]], "#7cff9b");
              } else if (pn.kind === "top") {
                const a1 = cc(1, 0), b1 = cc(1, -1);
                elbow([[a1[0], a1[1]], [a1[0] + CZ * 0.95, a1[1]], [a1[0] + CZ * 0.95, b1[1]], [b1[0] + 7, b1[1]]], "#7cff9b");
              } else {
                const a1 = cc(0, 0), b1 = cc(-1, -1);
                elbow([[a1[0], a1[1]], [a1[0], b1[1]], [b1[0] + 7, b1[1]]], "#7cff9b");
              }
              centerLabel(pn.title, x0 + pw3 / 2, y0 + 26, "#ffcf6b", 14);
            }
            ctx.restore();
          });
        }
        if (ts >= 23.0) {
          ctx.strokeStyle = "rgba(124,255,155,0.8)"; ctx.lineWidth = 1.6;
          ctx.strokeRect(gx - padL, gy - padT, ps, ps);
          ctx.strokeStyle = "#7cff9b"; ctx.lineWidth = 2;
          ctx.strokeRect(gx - padL + 9 * st, gy - padT, ps, ps);
          label("grid recentred: starts half the padding before the scene, ends flush", gx, gy + gh + padT + 28, "rgba(124,255,155,0.85)", 13);
        }
        if (ts < 16.2) caption = "Reflective padding  ·  split evenly between both sides  ·  mirrored real texture, no zeros";
        else if (ts < 22.8) caption = "Zoomed in  ·  pixels are mirrored across the edge, padding never invents data";
        else caption = "The grid is recentred  ·  it starts half the padding before the scene and ends flush";
      } else {
        mirrorBands(0.5);
        const shown = Math.min(40, Math.floor(((ts - 24.0) / 2.4) * 40) + 1);
        for (let n = 0; n < shown; n++) {
          const iv = Math.floor(n / 10), ih2 = n % 10;
          const x = gx - padL + ih2 * st, y = gy - padT + iv * st;
          ctx.strokeStyle = n === shown - 1 ? "#7cff9b" : "rgba(124,255,155,0.16)";
          ctx.lineWidth = n === shown - 1 ? 2 : 1;
          ctx.strokeRect(x, y, ps, ps);
          ctx.fillStyle = "rgba(124,255,155,0.55)";
          ctx.beginPath(); ctx.arc(x + ps / 2, y + ps / 2, 1.8, 0, 7); ctx.fill();
        }
        label("total patches", fx, 104, "#e6f7f3", 14);
        label("= n_v x n_h = 40", fx, 126, "#e6f7f3", 14);
        label(`placed: ${shown} / 40`, fx, 148, "#7cff9b", 14);
        label("coords precomputed once:", fx, 182, "rgba(206,228,222,0.95)", 13);
        label("(row range, col range, padding)", fx, 204, "rgba(206,228,222,0.95)", 13);
        caption = "Every patch coordinate is precomputed once  ·  extracting a patch is just a slice plus optional padding";
      }
    } else if (tt < A3) {
      const ts = tt - A2;
      const bs = Math.min(h - 195, 235, Math.max(140, w - 830));
      const px0 = 70, py0 = 70;

      if (ts < 2.1) {
        const msx = 64, msy = 52, msw = 230, msh = 100;
        field(msx, msy, msw, msh, 0.4, 6);
        ctx.strokeStyle = "rgba(120,200,220,0.4)"; ctx.lineWidth = 1.2; ctx.strokeRect(msx, msy, msw, msh);
        label("patch grid", msx, msy - 12);
      }
      const zp = this._ease(c01(ts / 2.0));
      const zx = this._lerp(132, px0, zp), zy = this._lerp(78, py0, zp);
      const zs = this._lerp(32, bs, zp);
      field(zx, zy, zs, zs, 0.9, 6, (i, j) => [i + 11, j + 4]);
      ctx.strokeStyle = "#7cff9b"; ctx.lineWidth = 2; ctx.strokeRect(zx, zy, zs, zs);
      if (ts >= 2.2) label("complex patch  (9, 64, 64)", px0, py0 - 16, "#7cff9b", 14);

      const cw = 92, chh = 70, step = 50, ggap = 30;
      const cx0 = px0 + bs + 80;
      const cy0 = py0 - 10;
      const tag = (x, y, txt, color) => {
        ctx.fillStyle = "rgba(4,7,10,0.92)";
        ctx.strokeStyle = color; ctx.lineWidth = 1;
        const tw3 = ctx.measureText ? 10 + txt.length * 7 : 30;
        ctx.beginPath();
        if (ctx.roundRect) ctx.roundRect(x, y, tw3, 17, 4); else ctx.rect(x, y, tw3, 17);
        ctx.fill(); ctx.stroke();
        label(txt, x + 5, y + 13, color, 11);
      };
      const inGroups = [
        { n: 1, name: "mag · primary", kind: "mag", t0: 2.4, color: "#35e6d0" },
        { n: 4, name: "mag · secondaries", kind: "mag2", t0: 4.2, color: "rgba(178,204,210,0.95)" },
        { n: 4, name: "phase · interferograms", kind: "ph", t0: 7.0, color: "#ffcf6b" },
      ];
      let gx2 = cx0;
      inGroups.forEach((g) => { g.x = gx2; g.w = (g.n - 1) * step + cw; gx2 += g.w + ggap; });
      const rowEnd = gx2 - ggap;

      if (ts >= 2.4) elbow([[px0 + bs + 8, py0 + bs * 0.25], [px0 + bs + 44, py0 + bs * 0.25], [px0 + bs + 44, cy0 + chh / 2], [cx0 - 14, cy0 + chh / 2]], "rgba(53,230,208,0.75)");
      inGroups.forEach((g, gi) => {
        for (let k = 0; k < g.n; k++) {
          const ap = this._ease(c01((ts - g.t0 - k * 0.5) / 0.7));
          if (ap <= 0) continue;
          const x = this._lerp(px0 + bs - cw, g.x + k * step, ap);
          const y = cy0 + k * 6;
          ctx.save(); ctx.globalAlpha = ap;
          ctx.fillStyle = "rgba(7,12,17,0.95)";
          ctx.strokeStyle = g.color; ctx.lineWidth = 1.3;
          ctx.beginPath();
          if (ctx.roundRect) ctx.roundRect(x, y, cw, chh, 7); else ctx.rect(x, y, cw, chh);
          ctx.fill(); ctx.stroke();
          if (g.kind === "ph") fringes(x + 6, y + 6, cw - 12, chh - 12, 0.85, k * 1.4);
          else field(x + 6, y + 6, cw - 12, chh - 12, g.kind === "mag" ? 0.9 : 0.5, 5, (i, j) => [i + 11 + k * 9 + gi * 17, j + 4 + k * 5]);
          ctx.restore();
        }
        const gDone = this._ease(c01((ts - g.t0 - (g.n - 1) * 0.5 - 0.4) / 0.5));
        if (gDone > 0) {
          ctx.save(); ctx.globalAlpha = gDone;
          centerLabel(g.name, g.x + g.w / 2, cy0 + chh + 18 + 20, g.color, 13);
          ctx.restore();
        }
      });

      const dghost = ts < 9.0 ? this._ease(c01((ts - 9.0) / 0.6)) : 1 - this._ease(c01((ts - 9.6) / 0.6));
      if (dghost > 0) {
        const dgx = rowEnd + ggap, dgy = cy0;
        ctx.save(); ctx.globalAlpha = 0.3 * dghost;
        ctx.fillStyle = "rgba(7,12,17,0.95)";
        ctx.strokeStyle = "rgba(178,204,210,0.95)"; ctx.lineWidth = 1.3; ctx.setLineDash([5, 4]);
        ctx.beginPath();
        if (ctx.roundRect) ctx.roundRect(dgx, dgy, cw, chh, 7); else ctx.rect(dgx, dgy, cw, chh);
        ctx.fill(); ctx.stroke(); ctx.setLineDash([]);
        field(dgx + 6, dgy + 6, cw - 12, chh - 12, 0.4, 5, (i, j) => [i + 51, j + 9]);
        centerLabel("dem · ZSCORE (use_dem off)", dgx + cw / 2, dgy + chh + 38, "rgba(178,204,210,0.95)", 12);
        ctx.restore();
      }

      const byy = cy0 + chh + 18 + 38;
      if (ts >= 10.0) {
        const ba = c01((ts - 10.0) / 0.8);
        const bx1 = cx0 - 8, bx2 = rowEnd + 8;
        ctx.save(); ctx.globalAlpha = ba;
        ctx.strokeStyle = "#35e6d0"; ctx.lineWidth = 1.4;
        ctx.beginPath(); ctx.moveTo(bx1, byy); ctx.lineTo(bx2, byy); ctx.stroke();
        ctx.beginPath(); ctx.moveTo(bx1, byy - 6); ctx.lineTo(bx1, byy); ctx.stroke();
        ctx.beginPath(); ctx.moveTo(bx2, byy - 6); ctx.lineTo(bx2, byy); ctx.stroke();
        centerLabel("input tensor [C = 1 + 4 + 4 = 9, 64, 64]  float32", (bx1 + bx2) / 2, byy + 22, "#35e6d0", 14);
        ctx.restore();
      }

      if (ts >= 12.0) {
        const chh2 = 62;
        const gy0 = byy + 78;
        elbow([[px0 + bs + 8, py0 + bs * 0.75], [px0 + bs + 44, py0 + bs * 0.75], [px0 + bs + 44, gy0 + 31], [cx0 - 14, gy0 + 31]], "rgba(124,255,155,0.75)");
        const setW = 2 * step + cw;
        const roles = ["a", "mu", "sig"];
        for (let s = 0; s < 3; s++) {
          const setX = cx0 + s * (setW + 26);
          const sa = this._ease(c01((ts - 12.0 - s * 0.8) / 0.6));
          if (sa > 0) {
            ctx.save(); ctx.globalAlpha = sa;
            centerLabel("G" + (s + 1), setX + setW / 2, gy0 - 12, "#7cff9b", 13);
            ctx.restore();
          }
          roles.forEach((nm, k) => {
            const ap = this._ease(c01((ts - 12.0 - (s * 3 + k) * 0.3) / 0.6));
            if (ap <= 0) return;
            const x = this._lerp(px0 + bs - cw, setX + k * step, ap);
            const y = gy0 + k * 5;
            ctx.save(); ctx.globalAlpha = ap;
            ctx.fillStyle = "rgba(7,12,17,0.95)"; ctx.strokeStyle = "#7cff9b"; ctx.lineWidth = 1.3;
            ctx.beginPath();
            if (ctx.roundRect) ctx.roundRect(x, y, cw, chh2, 7); else ctx.rect(x, y, cw, chh2);
            ctx.fill(); ctx.stroke();
            field(x + 6, y + 6, cw - 12, chh2 - 12, 0.5, 5, (i, j) => [i + 30 + (s * 3 + k) * 9, j + 13]);
            tag(x + 6, y + 6, nm, "#7cff9b");
            ctx.restore();
          });
        }
        if (ts >= 14.6) {
          const dx = cx0 + 3 * setW + 2 * 26 + 14;
          for (let d = 0; d < 3; d++) {
            ctx.fillStyle = "rgba(124,255,155,0.7)";
            ctx.beginPath(); ctx.arc(dx + d * 12, gy0 + chh2 / 2, 2.5, 0, 7); ctx.fill();
          }
        }
        if (ts >= 15.2) {
          const ba2 = c01((ts - 15.2) / 0.8);
          const gx1 = cx0 - 8, gx3 = cx0 + 3 * setW + 2 * 26 + 8;
          const gyy = gy0 + chh2 + 10 + 16;
          ctx.save(); ctx.globalAlpha = ba2;
          ctx.strokeStyle = "#7cff9b"; ctx.lineWidth = 1.4;
          ctx.beginPath(); ctx.moveTo(gx1, gyy); ctx.lineTo(gx3, gyy); ctx.stroke();
          ctx.beginPath(); ctx.moveTo(gx1, gyy - 6); ctx.lineTo(gx1, gyy); ctx.stroke();
          ctx.beginPath(); ctx.moveTo(gx3, gyy - 6); ctx.lineTo(gx3, gyy); ctx.stroke();
          centerLabel("gt tensor [3K, 64, 64]  float32  ·  K sets of (a, mu, sigma)", (gx1 + gx3) / 2, gyy + 22, "#7cff9b", 14);
          ctx.restore();
        }
      }

      if (ts < 2.2) caption = "Fetching one sample slices a 9-layer window out of the memory-mapped stack";
      else if (ts < 4.2) caption = "Primary pass  ·  its magnitude becomes channel 0";
      else if (ts < 7.0) caption = "Secondary passes  ·  one magnitude channel per pass";
      else if (ts < 10.0) caption = "Interferograms  ·  one phase channel each";
      else if (ts < 12.0) caption = "1 + 4 + 4 = 9 channels written into a single tensor";
      else caption = "Targets repeat (a, mu, sigma) for each Gaussian  ->  3K layers of 64 x 64";
    } else if (tt < A4) {
      const ts = tt - A3;
      const as2 = Math.min(h - 250, 240);
      const ay = (h - as2) / 2 + 34;
      const bridge = this._ease(c01((ts - 16.0) / 1.6));
      const axL = this._lerp(w / 2 - as2 - 80, 64, bridge), axR = this._lerp(w / 2 + 80, w / 2 + 40, bridge);
      const appear = this._ease(c01(ts / 1.0));
      const aprog = (t0, dur) => (ts < t0 ? 0 : ts < t0 + dur ? this._ease((ts - t0) / dur) : 1);
      const fH = aprog(2.2, 1.2);
      const fV = aprog(5.8, 1.2);
      const rQ = aprog(9.4, 1.4);
      const noiseA = aprog(13.0, 1.0);
      const sxF = Math.cos(Math.PI * fH);
      const syF = Math.cos(Math.PI * fV);
      const ang = (rQ * Math.PI) / 2;
      const gv = (v) => (Math.abs(v) < 0.02 ? 0.02 : v);

      const mark = (i, j, nq) => (i < nq * 0.24 && j > nq * 0.3) || (j > nq * 0.74 && i < nq * 0.6);
      const drawPatch = (x, baseFn, markCol, borderCol, nA) => {
        ctx.save(); ctx.globalAlpha = appear;
        ctx.beginPath(); ctx.rect(x - 1, ay - 1, as2 + 2, as2 + 2); ctx.clip();
        ctx.translate(x + as2 / 2, ay + as2 / 2);
        ctx.rotate(ang);
        ctx.scale(gv(sxF), gv(syF));
        ctx.translate(-as2 / 2, -as2 / 2);
        const cell = 8, nq = Math.floor(as2 / cell);
        for (let j = 0; j < nq; j++) {
          for (let i = 0; i < nq; i++) {
            ctx.fillStyle = mark(i, j, nq) ? markCol : baseFn(tex(i + 4, j + 7));
            ctx.fillRect(i * cell, j * cell, cell - 1, cell - 1);
          }
        }
        if (nA > 0) {
          for (let k = 0; k < 90; k++) {
            const nx3 = rnd(k * 7.3) * (as2 - 4), ny3 = rnd(k * 13.7) * (as2 - 4);
            const tw2 = 0.75 + 0.25 * Math.sin(this.t * 9 + k * 1.7);
            ctx.fillStyle = `rgba(230,247,243,${0.55 * nA * tw2})`;
            ctx.fillRect(nx3, ny3, 2, 2);
          }
        }
        ctx.restore();
        ctx.save(); ctx.globalAlpha = appear;
        ctx.strokeStyle = borderCol; ctx.lineWidth = 1.6;
        ctx.strokeRect(x, ay, as2, as2);
        ctx.restore();
      };

      drawPatch(axL, (v) => `rgba(53,230,208,${0.06 + v * 0.3})`, "rgba(230,247,243,0.85)", "#35e6d0", noiseA);
      drawPatch(axR, (v) => `rgba(124,255,155,${0.05 + v * 0.26})`, "rgba(124,255,155,0.9)", "#7cff9b", 0);

      const xf = (x, px, py) => {
        const cx2 = x + as2 / 2, cy2 = ay + as2 / 2;
        const dx = (px - as2 / 2) * gv(sxF), dy = (py - as2 / 2) * gv(syF);
        return [cx2 + dx * Math.cos(ang) - dy * Math.sin(ang), cy2 + dx * Math.sin(ang) + dy * Math.cos(ang)];
      };
      const axes = (x) => {
        ctx.save(); ctx.globalAlpha = appear;
        const col = "rgba(206,228,222,0.8)";
        const lab = (pA, pB, txt) => {
          const mx = (pA[0] + pB[0]) / 2, my = (pA[1] + pB[1]) / 2;
          let nx = -(pB[1] - pA[1]), ny = pB[0] - pA[0];
          const dl = Math.hypot(nx, ny) || 1;
          nx /= dl; ny /= dl;
          const vx = mx - (x + as2 / 2), vy = my - (ay + as2 / 2);
          if (nx * vx + ny * vy < 0) { nx = -nx; ny = -ny; }
          centerLabel(txt, mx + nx * 44, my + ny * 44 + 4, col, 13);
        };
        const p1 = xf(x, 6, as2 + 12), p2 = xf(x, as2 - 6, as2 + 12);
        arrow(p1[0], p1[1], p2[0], p2[1], col);
        lab(p1, p2, "azimuth");
        const q1 = xf(x, -12, as2 - 6), q2 = xf(x, -12, 6);
        arrow(q1[0], q1[1], q2[0], q2[1], col);
        lab(q1, q2, "range");
        ctx.restore();
      };
      axes(axL); axes(axR);
      label("input tensor", axL, ay - 72, "#35e6d0", 16);
      label("target parameters", axR, ay - 72, "#7cff9b", 16);

      const gates = [
        { txt: "flip H · 0.31 < 0.5 ✓", col: "#7cff9b", t0: 1.4 },
        { txt: "flip V · 0.27 < 0.5 ✓", col: "#7cff9b", t0: 5.0 },
        { txt: "rotate 90 · p 0 · demo", col: "rgba(206,228,222,0.9)", t0: 8.6 },
        { txt: "noise · 0.11 < 0.25 ✓", col: "#ffcf6b", t0: 12.4 },
      ];
      let gxp = w / 2 - 450;
      gates.forEach((g) => { gxp += chip(g.txt, gxp, 40, g.col, c01((ts - g.t0) / 0.5), 15) + 18; });

      const nEqA = ts < 16.0 ? c01((ts - 12.4) / 0.5) : 1 - this._ease(c01((ts - 16.0) / 0.8));
      if (nEqA > 0) this._texDraw("x'=x+\\varepsilon,\\;\\varepsilon\\sim\\mathcal{N}(0,\\,0.01^2)", w / 2, ay - 44, 15, { color: "#ffcf6b", align: "center", alpha: nEqA });

      const noteY = ay + as2 + 78;
      if (ts >= 1.4 && ts < 5.0) centerLabel("the same flip is applied to input and target", w / 2, noteY, "#7cff9b", 15);
      else if (ts >= 5.0 && ts < 8.6) centerLabel("same vertical mirror on both", w / 2, noteY, "#7cff9b", 15);
      else if (ts >= 8.6 && ts < 12.4) centerLabel("the quarter-turn rotates both together", w / 2, noteY, "rgba(206,228,222,0.95)", 15);
      else if (ts >= 12.4 && ts < 16.0) centerLabel("noise lands on the normalized input only  ·  target unchanged", w / 2, noteY, "#ffcf6b", 15);
      else if (ts >= 16.0) centerLabel("the augmented pair docks into normalization", w / 2, noteY, "#35e6d0", 15);

      if (ts < 1.4) caption = "Augmentation, training split only  ·  an independent random draw gates each transform";
      else if (ts < 5.0) caption = "Horizontal flip  ·  one draw flips the input and the target together";
      else if (ts < 8.6) caption = "Vertical flip  ·  the same mirror is applied to input and target";
      else if (ts < 12.4) caption = "Rotation by quarter turns on both  ·  disabled in this configuration, shown for illustration";
      else if (ts < 16.0) caption = "Gaussian noise (std 0.01, normalized units) gates at p = 0.25  ·  it lands AFTER normalization, targets stay exact";
      else caption = "Augmented pair ready  ·  next it is normalized, then the 0.01 noise is added on the normalized channels";
    } else if (tt < A5) {
      const ts = tt - A4;

      const provA = ts < 5.0 ? 1 : 1 - this._ease(c01((ts - 5.0) / 0.8));
      if (provA > 0) {
        const pw6 = Math.min(280, w * 0.32), ph6 = Math.min(190, h - 220);
        const py6 = (h - ph6) / 2 - 6;
        const lpx = w / 2 - pw6 - 60, rpx = w / 2 + 60;
        ctx.save(); ctx.globalAlpha = provA;
        centerLabel("two fitting regimes", w / 2, py6 - 56, "#e6f7f3", 16);

        const cell6 = 13, nx6 = Math.floor(pw6 / cell6), ny6 = Math.floor(ph6 / cell6);
        const litFrac = c01(ts / 2.2) * 0.45;
        for (let j = 0; j < ny6; j++) {
          for (let i = 0; i < nx6; i++) {
            const lit = rnd(i * 31 + j * 57) < litFrac;
            ctx.fillStyle = lit ? "rgba(53,230,208,0.7)" : "rgba(120,200,220,0.12)";
            ctx.fillRect(lpx + i * cell6, py6 + j * cell6, cell6 - 2, cell6 - 2);
          }
        }
        ctx.strokeStyle = "rgba(53,230,208,0.5)"; ctx.lineWidth = 1.4; ctx.strokeRect(lpx - 4, py6 - 4, pw6 + 8, ph6 + 8);
        centerLabel("input stats", lpx + pw6 / 2, py6 - 28, "#35e6d0", 14);
        centerLabel("≤ 4,000 patches · seed 42 · batches of 512", lpx + pw6 / 2, py6 + ph6 + 26, "rgba(206,228,222,0.85)", 12);

        field(rpx, py6, pw6, ph6, 0.0, 7);
        const gate = this._ease(c01((ts - 2.5) / 2.0));
        for (let j = 0; j < ny6; j++) {
          for (let i = 0; i < nx6; i++) {
            const gated = rnd(i * 17 + j * 91) < 0.4;
            const al = gated ? this._lerp(1, 0.12, gate) : 1;
            const v = tex(i + 30, j + 9);
            ctx.fillStyle = `rgba(124,255,155,${(0.06 + v * 0.3) * al})`;
            ctx.fillRect(rpx + i * cell6, py6 + j * cell6, cell6 - 2, cell6 - 2);
          }
        }
        ctx.strokeStyle = "rgba(124,255,155,0.6)"; ctx.lineWidth = 1.4; ctx.strokeRect(rpx - 4, py6 - 4, pw6 + 8, ph6 + 8);
        centerLabel("output stats", rpx + pw6 / 2, py6 - 28, "#7cff9b", 14);
        centerLabel("full GT parameter array", rpx + pw6 / 2, py6 + ph6 + 26, "rgba(206,228,222,0.85)", 12);
        if (gate > 0) chip("a > 0.01", rpx + pw6 / 2 - 40, py6 + ph6 / 2 + 8, "#ffcf6b", gate, 14);
        if (ts >= 2.5) {
          const gA2 = c01((ts - 2.5) / 0.6);
          (this._texDraw("a,\\mu,\\sigma:\\;\\text{only where}\\;a_k>0.01", w / 2, py6 + ph6 + 40, 14, { color: "rgba(206,228,222,0.9)", align: "center", alpha: gA2 }) ? null : centerLabel("a, mu, sigma: only where a > 0.01", w / 2, py6 + ph6 + 50, "rgba(206,228,222,0.85)", 12));
        }
        ctx.restore();
      }

      const lanes = [
        { g: "pass/mag", sub: "z-score + log1p", tag: "patches", c: "#35e6d0", kind: "log", mu0: 0.44, sg0: 0.18,
          raw: (x, b) => (Math.exp(-x * 5.4) * (1 + 0.25 * Math.sin(b * 1.7))) / 1.25,
          log: (x, b) => (Math.exp(-((x - 0.44) ** 2) / 0.06) * (1 + 0.12 * Math.sin(b * 2.3))) / 1.12 },
        { g: "ifg/phase", sub: "z-score", tag: "patches", c: "#ffcf6b", kind: "phase" },
        { g: "out/amp", sub: "z-score + log1p", tag: "full array", c: "#7cff9b", kind: "log", mu0: 0.45, sg0: 0.17,
          raw: (x, b) => Math.exp(-x * 5.0) * (1 + 0.2 * Math.sin(b * 1.9)),
          log: (x, b) => Math.exp(-((x - 0.45) ** 2) / 0.055) * (1 + 0.1 * Math.sin(b * 2.1)) },
        { g: "out/mu", sub: "z-score", tag: "full array", c: "#7cff9b", kind: "plain", mu0: 0.55, sg0: 0.22,
          raw: (x, b) => 0.55 + 0.35 * Math.sin(x * 7.1 + 0.6) * Math.sin(x * 3.3 + 1.9) + 0.08 * Math.sin(b * 2.7) },
        { g: "out/sigma", sub: "z-score + log1p", tag: "full array", c: "#7cff9b", kind: "log", mu0: 0.42, sg0: 0.17,
          raw: (x, b) => (Math.exp(-((x - 0.14) ** 2) / 0.012) + 0.45 * Math.exp(-x * 2.6)) / 1.45,
          log: (x, b) => Math.exp(-((x - 0.42) ** 2) / 0.05) * (1 + 0.1 * Math.sin(b * 1.7)) },
      ];

      const lt = ts - 2.0;
      if (lt >= 3.0) {
        const y0L = 64;
        const gGap = 16;
        const LH = (h - y0L - 36 - gGap) / 5;
        const laneY = (i) => y0L + i * LH + (i >= 2 ? gGap : 0);
        const hdW = Math.min(300, w * 0.24);
        const hdX = 50;
        const pX = hdX + hdW + 76;
        const pW = w - pX - 96;
        const groups = [{ y0: y0L, n: 2, c: "#35e6d0", txt: "input stats" }, { y0: laneY(2) - 10, n: 3, c: "#7cff9b", txt: "output stats" }];
        groups.forEach((gr) => {
          const ga = this._ease(c01((lt - 3.0) / 0.6));
          if (ga <= 0) return;
          ctx.save(); ctx.globalAlpha = ga * 0.9;
          ctx.strokeStyle = gr.c; ctx.lineWidth = 1.4;
          ctx.beginPath(); ctx.moveTo(hdX, gr.y0 + 3); ctx.lineTo(hdX + hdW, gr.y0 + 3); ctx.stroke();
          label(gr.txt, hdX, gr.y0 - 6, gr.c, 12);
          ctx.restore();
        });
        lanes.forEach((ln, i) => {
          const la = this._ease(c01((lt - 3.0 - i * 0.6) / 0.6));
          if (la <= 0) return;
          const u = lt - 4.0 - i * 0.6;
          const settled = u > 9.0;
          const yT = laneY(i);
          const yM = yT + (LH - 12) / 2 + 4;
          ctx.save(); ctx.globalAlpha = settled ? la * 0.7 : la;

          ctx.fillStyle = "rgba(7,12,17,0.95)";
          ctx.strokeStyle = "rgba(120,200,220,0.3)"; ctx.lineWidth = 1.2;
          ctx.beginPath();
          if (ctx.roundRect) ctx.roundRect(hdX, yT + 6, hdW, LH - 18, 8); else ctx.rect(hdX, yT + 6, hdW, LH - 18);
          ctx.fill(); ctx.stroke();
          ctx.fillStyle = ln.c;
          ctx.fillRect(hdX, yT + 6, 4, LH - 18);
          label(ln.g, hdX + 18, yM - 5, ln.c, 15);
          label(ln.sub, hdX + 18, yM + 14, "rgba(206,228,222,0.85)", 12);
          label(ln.tag, hdX + hdW - 70, yT + 20, ln.tag === "patches" ? "#35e6d0" : "#7cff9b", 11);

          elbow([[hdX + hdW + 8, yM], [pX - 14, yM]], "rgba(206,228,222,0.55)");

          ctx.strokeStyle = "rgba(120,200,220,0.22)"; ctx.lineWidth = 1;
          ctx.strokeRect(pX - 6, yT + 6, pW + 12, LH - 18);

          const hb = yT + LH - 22;
          const hh3 = LH - 42;
          if (ln.kind === "phase") {
            const sq = this._ease(c01((u - 5.5) / 3.0));
            const sw5 = this._lerp(pW * 0.94, (pW * 0.94) / 1.814, sq);
            const x5 = pX + (pW - sw5) / 2;
            const sh5 = Math.min(22, hh3);
            const sy5 = yT + (LH - 10 - sh5) / 2 + 4;
            const gA = this._ease(c01(u / 1.6));
            ctx.save(); ctx.globalAlpha = (settled ? la * 0.7 : la) * gA;
            for (let qq = 0; qq < 60; qq++) {
              const v = 0.5 + 0.5 * Math.sin((qq / 60) * Math.PI * 4 - Math.PI);
              ctx.fillStyle = sq < 0.5 ? `rgba(255,207,107,${0.12 + v * 0.5})` : `rgba(124,255,155,${0.12 + v * 0.5})`;
              ctx.fillRect(x5 + (qq / 60) * sw5, sy5, sw5 / 60 + 0.5, sh5);
            }
            ctx.strokeStyle = sq < 0.5 ? "rgba(255,207,107,0.6)" : "rgba(124,255,155,0.7)";
            ctx.lineWidth = 1.2; ctx.strokeRect(x5, sy5, sw5, sh5);
            label(sq < 0.5 ? "-pi" : "-1.73", x5 + 4, sy5 - 5, sq < 0.5 ? "#ffcf6b" : "#7cff9b", 12);
            label(sq < 0.5 ? "+pi" : "+1.73", x5 + sw5 - 38, sy5 - 5, sq < 0.5 ? "#ffcf6b" : "#7cff9b", 12);
            this._texDraw("\\varphi\\mapsto(\\varphi-\\mu_\\varphi)/\\sigma_\\varphi", x5, sy5 + sh5 + 6, 14, { color: "rgba(255,207,107,0.9)" }) || label("(φ - μ) / σ", x5, sy5 + sh5 + 18, "rgba(255,207,107,0.85)", 12);
            label("fitted stats, like every slot", x5 + 168, sy5 + sh5 + 18, "rgba(255,207,107,0.85)", 12);
            ctx.restore();
          } else {
            const NB2 = 40;
            const m2 = ln.kind === "log" ? this._ease(c01((u - 2.2) / 1.8)) : 0;
            const mp2 = this._ease(c01((u - 4.8) / 1.2));
            const q3 = this._ease(c01((u - 6.8) / 1.6));
            const inputLane = ln.c === "#35e6d0";
            const MU = ln.mu0, SG = ln.sg0;
            const zx = (v) => this._lerp(v, 0.5 + (v - MU) / (4 * SG), q3);
            ctx.save();
            ctx.globalAlpha = settled ? la * 0.7 : la;
            ctx.beginPath(); ctx.rect(pX - 1, yT + 6, pW + 2, LH - 18); ctx.clip();
            ctx.strokeStyle = "rgba(120,200,220,0.3)"; ctx.lineWidth = 1;
            ctx.beginPath(); ctx.moveTo(pX, hb); ctx.lineTo(pX + pW, hb); ctx.stroke();
            for (let b = 0; b < NB2; b++) {
              const xN = b / NB2;
              const rvv = c01(ln.raw(xN, b));
              const lvv = ln.kind === "log" ? c01(ln.log(xN, b)) : rvv;
              const g2 = this._ease(c01((u - b * 0.02) / 1.2));
              const bh2 = this._lerp(rvv, lvv, m2) * hh3 * g2;
              const xs3 = zx(xN);
              const bw3 = this._lerp(1, 1 / (4 * SG), q3) * (pW / NB2) - 2;
              if (inputLane) ctx.fillStyle = `rgba(${Math.round(53 + q3 * 71)},${Math.round(230 + q3 * 25)},${Math.round(208 - q3 * 53)},0.55)`;
              else ctx.fillStyle = "rgba(124,255,155,0.55)";
              ctx.fillRect(pX + xs3 * pW, hb - bh2, bw3, bh2);
            }
            if (mp2 > 0) {
              ctx.save(); ctx.globalAlpha *= mp2;
              const xMu = pX + zx(MU) * pW;
              ctx.strokeStyle = "rgba(255,207,107,0.9)"; ctx.lineWidth = 1.4;
              ctx.beginPath(); ctx.moveTo(xMu, hb - hh3); ctx.lineTo(xMu, hb); ctx.stroke();
              ctx.strokeStyle = "rgba(255,207,107,0.7)"; ctx.setLineDash([4, 3]); ctx.lineWidth = 1.2;
              [MU - SG, MU + SG].forEach((v) => {
                const xv = pX + zx(v) * pW;
                ctx.beginPath(); ctx.moveTo(xv, hb - hh3); ctx.lineTo(xv, hb); ctx.stroke();
              });
              ctx.setLineDash([]);
              if (q3 > 0.6) {
                ctx.fillStyle = "rgba(255,207,107,0.85)"; ctx.font = "10px 'IBM Plex Mono', monospace";
                ctx.fillText("0", xMu - 3, hb - hh3 - 3);
              }
              ctx.restore();
            }
            ctx.restore();
            if (q3 > 0.6) {
              ctx.save(); ctx.globalAlpha = la * c01((q3 - 0.6) / 0.4);
              label("0 ± 1", pX + pW + 10, yM + 5, "#7cff9b", 13);
              ctx.restore();
            }
          }
          ctx.restore();
        });
        const logA = ts < 11.0 ? c01((ts - 8.5) / 0.6) : 1 - this._ease(c01((ts - 11.0) / 0.5));
        if (logA > 0) this._texDraw("x\\mapsto\\log(1+x)", w / 2, 12, 15, { color: "#35e6d0", align: "center", alpha: logA });
        const mmA = ts < 20.5 ? c01((ts - 11.6) / 0.6) : 1 - this._ease(c01((ts - 20.5) / 0.5));
        if (mmA > 0) this._texDraw("\\hat{x}=\\frac{x-\\mu}{\\sigma}", w / 2, 8, 15, { color: "rgba(230,247,243,0.95)", align: "center", alpha: mmA });
      }

      if (ts < 2.5) caption = "Two regimes  ·  input stats sample patches, output stats read the whole parameter array";
      else if (ts < 5.0) caption = "All three output pools — amp, mu and sigma — keep only active Gaussians (a > 0.01)";
      else if (ts < 8.5) caption = "Normalization runs last, after augmentation  ·  input stats are fit on up to 4,000 train patches (seed 42, batches of 512)";
      else if (ts < 11.5) caption = "Log transform first where the data is heavy-tailed: magnitude, amplitude and sigma";
      else if (ts < 15.5) caption = "Per-slot statistics: the fitted mean recentres, the std rescales  ·  phase is z-scored too, no fixed ÷ pi";
      else if (ts < 20.5) caption = "Every lane lands at mean 0, std 1  ·  the same z-score recipe for inputs and outputs";
      else caption = "Offsets and scales are saved with the run and reused for val/test  ·  output stats keep only active Gaussians (a > 0.01)";
    } else {
      const ts = tt - A5;
      const cw3 = 66, chh = 54, gap = 22;
      const rowY = 92;
      const slot = (i) => w / 2 - 4 * (cw3 + gap) + gap / 2 + i * (cw3 + gap);
      const perm = [5, 2, 7, 0, 3, 6, 1, 4];
      const shf = this._ease(c01((ts - 2.6) / 1.8));
      const stk = this._ease(c01((ts - 5.2) / 1.8));
      const bY = h / 2 + 30;
      const sxI = w * 0.07, sxA = w * 0.36, sxB = w * 0.65;

      for (let i = 0; i < 8; i++) {
        const ap = this._ease(c01((ts - i * 0.18) / 0.6));
        if (ap <= 0) continue;
        const xs = this._lerp(slot(i), slot(perm[i]), shf);
        const x = this._lerp(xs, sxI + i * 6, stk);
        const y = this._lerp(rowY, bY - i * 5, stk);
        const wd = this._lerp(cw3, 120, stk), ht = this._lerp(chh, 46, stk);
        ctx.save(); ctx.globalAlpha = ap;
        ctx.fillStyle = "rgba(7,12,17,0.95)";
        ctx.strokeStyle = "rgba(53,230,208,0.55)";
        ctx.lineWidth = 1.3;
        ctx.setLineDash([5, 4]);
        ctx.beginPath();
        if (ctx.roundRect) ctx.roundRect(x, y, wd, ht, 7); else ctx.rect(x, y, wd, ht);
        ctx.fill(); ctx.stroke();
        ctx.setLineDash([]);
        centerLabel("idx " + i, x + wd / 2, y + ht / 2 + 5, "rgba(230,247,243,0.9)", stk > 0.5 ? 12 : 14);
        ctx.restore();
      }
      if (ts < 5.0) {
        label("patch indices", slot(0), rowY - 34);
        centerLabel("indices + grid coords only  ·  no pixels in memory", w / 2, rowY + chh + 32, "rgba(206,228,222,0.95)");
      }

      for (let i = 0; i < 8; i++) {
        const p = this._ease(c01((ts - 6.4 - i * 0.25) / 0.8));
        if (p <= 0) continue;
        const x0 = sxI + i * 6, y0 = bY - i * 5;
        const xa = this._lerp(x0, sxA + i * 6, p);
        const xb = this._lerp(x0, sxB + i * 6, p);
        const wd2 = this._lerp(120, 150, p), ht2 = this._lerp(46, 54, p);
        ctx.save(); ctx.globalAlpha = Math.min(1, p * 1.4);
        ctx.fillStyle = "rgba(7,12,17,0.95)"; ctx.strokeStyle = "#35e6d0"; ctx.lineWidth = 1.3;
        ctx.beginPath();
        if (ctx.roundRect) ctx.roundRect(xa, y0, wd2, ht2, 7); else ctx.rect(xa, y0, wd2, ht2);
        ctx.fill(); ctx.stroke();
        field(xa + 5, y0 + 5, wd2 - 10, ht2 - 10, 0.6 * p, 6, (i2, j2) => [i2 + i * 13, j2 + i * 7]);
        ctx.restore();
        ctx.save(); ctx.globalAlpha = Math.min(1, p * 1.4);
        ctx.fillStyle = "rgba(7,12,17,0.95)"; ctx.strokeStyle = "#7cff9b"; ctx.lineWidth = 1.3;
        ctx.beginPath();
        if (ctx.roundRect) ctx.roundRect(xb, y0, wd2, ht2, 7); else ctx.rect(xb, y0, wd2, ht2);
        ctx.fill(); ctx.stroke();
        const cell = 6;
        const nx4 = Math.max(1, Math.floor((wd2 - 10) / cell)), ny4 = Math.max(1, Math.floor((ht2 - 10) / cell));
        for (let j = 0; j < ny4; j++) {
          for (let i3 = 0; i3 < nx4; i3++) {
            const v = tex(i3 + 30 + i * 9, j + 13);
            ctx.fillStyle = `rgba(124,255,155,${(0.05 + v * 0.28) * 0.9 * p})`;
            ctx.fillRect(xb + 5 + i3 * cell, y0 + 5 + j * cell, cell - 1, cell - 1);
          }
        }
        ctx.restore();
      }

      const doneP = this._ease(c01((ts - 9.2) / 0.8));
      if (doneP > 0) {
        ctx.save(); ctx.globalAlpha = doneP;
        centerLabel("one batch · 8 samples drawn (B = 256 in production)", w / 2, bY - 82, "rgba(230,247,243,0.95)", 15);
        centerLabel("patch indices", sxI + 81, bY + 90, "rgba(206,228,222,0.95)", 14);
        centerLabel("inputs [B, 9, 64, 64]", sxA + 96, bY + 90, "#35e6d0", 14);
        centerLabel("normalized", sxA + 96, bY + 110, "rgba(206,228,222,0.9)", 12);
        centerLabel("targets [B, 3K, 64, 64]", sxB + 96, bY + 90, "#7cff9b", 14);
        centerLabel("normalized", sxB + 96, bY + 110, "rgba(206,228,222,0.9)", 12);
        ctx.restore();
      }
      const ca = c01((ts - 10.0) / 0.8);
      const loaders = [
        { t: "train · shuffled · drop last", c: "#35e6d0" },
        { t: "val · in order · keep all", c: "rgba(178,204,210,0.95)" },
        { t: "test · in order · keep all", c: "rgba(178,204,210,0.95)" },
        { t: "4 workers · prefetch 8 · pinned memory", c: "#ffcf6b" },
      ];
      const lcGap = 14;
      const lcW = loaders.map((l) => chip(l.t, 0, 0, l.c, 0, 12));
      const lcTotal = lcW.reduce((s, v) => s + v, 0) + lcGap * (loaders.length - 1);
      let lcx = (w - lcTotal) / 2;
      loaders.forEach((l, i) => { chip(l.t, lcx, h - 40, l.c, ca, 12); lcx += lcW[i] + lcGap; });
      if (ts >= 10.8) {
        const aEnd = Math.min(sxB + 230, w - 86);
        arrow(sxB + 200, bY + 24, aEnd, bY + 24, "#7cff9b");
        label("training", aEnd + 8, bY + 29, "#7cff9b", 14);
      }

      if (ts < 2.6) caption = "The dataset stores only indices and grid coordinates  ·  no patch pixels are in memory";
      else if (ts < 5.2) caption = "The training order is reshuffled every epoch";
      else if (ts < 9.2) caption = "4 persistent workers slice, pad and normalize on the fly (prefetch 8)  ·  each index yields an input and a target";
      else caption = "One batch consolidated  ·  indices, normalized inputs, normalized targets  ·  the three loaders feed training";
    }

    this._cap(caption);
  }

  /* ---------- training: step anatomy, warmup + cosine LR, grad clipper, loss curriculum ---------- */

  _trSetup() {
    if (this._tr) return this._tr;

    const target  = [{ a: 0.9, mu: 0.40, s: 0.06 }, { a: 0.55, mu: 0.68, s: 0.05 }, { a: 0.32, mu: 0.16, s: 0.045 }];
    const predRaw = [{ a: 0.72, mu: 0.47, s: 0.09 }, { a: 0.44, mu: 0.61, s: 0.075 }, { a: 0.26, mu: 0.21, s: 0.06 }];
    const mix     = (ps, x) => ps.reduce((y, p) => y + p.a * Math.exp(-((x - p.mu) ** 2) / (2 * p.s * p.s)), 0);

    const norms = [];
    for (let i = 0; i < 360; i++) {
      let v = 0.58 + 0.15 * Math.sin(i * 0.83) + 0.10 * Math.sin(i * 2.17 + 1.1) + 0.06 * Math.sin(i * 4.91 + 0.4);
      if (i % 37 === 21) v = 2.6 + 0.9 * Math.sin(i * 1.3);
      if (i % 53 === 11) v = 1.9 + 0.5 * Math.sin(i * 0.7);
      norms.push(Math.max(0.08, v));
    }
    const p95 = norms.map((_, i) => {
      const win = norms.slice(Math.max(0, i - 199), i + 1).slice().sort((a, b) => a - b);
      return win[Math.floor(0.95 * (win.length - 1))];
    });

    const BASE = 1e-3, ETA = 1e-6, E = 100, SPE = 40, WS = 200, S0 = 0.1;
    const cosF  = (e)  => ETA / BASE + 0.5 * (1 - ETA / BASE) * (1 + Math.cos(Math.PI * Math.min(1, e / E)));
    const warmF = (st) => st >= WS ? 1 : S0 + (1 - S0) * (st / WS);
    const lrAt  = (st) => BASE * cosF(Math.floor(st / SPE)) * warmF(st);

    const lossAt = (e) => {
      const wig = 0.012 * Math.sin(e * 1.7) + 0.008 * Math.sin(e * 3.1 + 0.7);
      if (e < 50) return 0.075 + 0.62 * Math.exp(-e / 13) + wig * (0.3 + Math.exp(-e / 13));
      return 0.030 + 0.105 * Math.exp(-(e - 50) / 11) + wig * 0.6;
    };

    const trainL = (e) => 0.050 + 0.55 * Math.exp(-e / 5.5) + 0.008 * Math.sin(e * 1.9) + 0.006 * Math.sin(e * 3.7 + 1);
    const valL   = (e) => 0.085 + 0.58 * Math.exp(-e / 5.0) + 0.0035 * Math.pow(Math.max(0, e - 11), 1.45) + 0.006 * Math.sin(e * 1.3 + 2) + 0.004 * Math.sin(e * 2.9);
    const ES_E = 30;
    const patAt = [];
    let esBestE = 0, esBestV = Infinity, esStopE = ES_E;
    {
      let pc = 0;
      for (let e = 0; e <= ES_E; e++) {
        const v = valL(e);
        if (v < esBestV - 0.001) { esBestV = v; esBestE = e; pc = 0; }
        else pc++;
        patAt.push(pc);
        if (pc >= 15 && esStopE === ES_E) esStopE = e;
      }
    }

    const regG = (x) => 0.55 + 0.25 * Math.sin(6.0 * x - 1.2);
    const regPts = [];
    for (let i = 0; i < 12; i++) {
      const x = 0.04 + (i / 11) * 0.92;
      const n = 0.085 * Math.sin(i * 12.9 + 3) + 0.065 * Math.sin(i * 31.7);
      regPts.push({ x, n, y: regG(x) + n });
    }

    this._tr = { target, predRaw, mix, norms, p95, BASE, ETA, E, SPE, WS, cosF, warmF, lrAt, lossAt, trainL, valL, patAt, esBestE, esBestV, esStopE, ES_E, regG, regPts };
    return this._tr;
  }

  _training() { this._dispatch("training", this._trSetup()); }

  _trTag(txt) {
    const { ctx, h } = this;
    ctx.save();
    ctx.fillStyle = "#35e6d0";
    ctx.fillRect(12, h - 19, 3, 12);
    ctx.font = "11px 'IBM Plex Mono', monospace";
    ctx.fillStyle = "rgba(143,176,170,0.85)";
    ctx.fillText(txt, 21, h - 9);
    ctx.restore();
  }

  _eqDraw(parts, x0, y, size, alphaMul) {
    const ctx = this.ctx;
    let cx = x0;
    parts.forEach((p2) => {
      const pa = (p2.a === undefined ? 1 : p2.a) * (alphaMul === undefined ? 1 : alphaMul);
      if (pa <= 0) return;
      ctx.save();
      ctx.globalAlpha = pa;
      ctx.font = `${p2.up ? "" : "italic "}${p2.sub ? Math.round(size * 0.64) : size}px Georgia, 'Times New Roman', serif`;
      ctx.fillStyle = p2.c || "rgba(230,247,243,0.95)";
      ctx.fillText(p2.t, cx, y + (p2.sub ? size * 0.28 : 0));
      cx += ctx.measureText(p2.t).width + (p2.pad || 2);
      ctx.restore();
    });
    return cx;
  }

  _trChip(x, y, bw, bh, text, opts) {
    const ctx = this.ctx;
    const o = opts || {};
    const col = o.color || "#35e6d0";
    const active = !!o.active;
    const alpha = o.alpha == null ? 1 : o.alpha;
    if (alpha <= 0) return;
    ctx.save();
    ctx.globalAlpha = alpha;
    ctx.fillStyle = "rgba(7,12,17,0.95)";
    ctx.strokeStyle = active ? col : "rgba(120,200,220,0.32)";
    ctx.lineWidth = active ? 1.8 : 1.3;
    ctx.beginPath();
    if (ctx.roundRect) ctx.roundRect(x, y, bw, bh, 7); else ctx.rect(x, y, bw, bh);
    if (active) { ctx.shadowColor = col; ctx.shadowBlur = 8; }
    ctx.fill(); ctx.shadowBlur = 0; ctx.stroke();
    ctx.font = "12px 'IBM Plex Mono', monospace";
    ctx.fillStyle = active ? col : "rgba(230,247,243,0.82)";
    ctx.fillText(text, x + (bw - ctx.measureText(text).width) / 2, y + bh / 2 + 4);
    ctx.restore();
  }

  _trArrow(x0, y0, x1, y1, color, alpha) {
    const ctx = this.ctx;
    if (alpha != null && alpha <= 0) return;
    ctx.save();
    if (alpha != null) ctx.globalAlpha = alpha;
    ctx.strokeStyle = color; ctx.fillStyle = color; ctx.lineWidth = 1.8;
    ctx.beginPath(); ctx.moveTo(x0, y0); ctx.lineTo(x1, y1); ctx.stroke();
    const ang = Math.atan2(y1 - y0, x1 - x0);
    ctx.beginPath();
    ctx.moveTo(x1, y1);
    ctx.lineTo(x1 - 7 * Math.cos(ang - 0.42), y1 - 7 * Math.sin(ang - 0.42));
    ctx.lineTo(x1 - 7 * Math.cos(ang + 0.42), y1 - 7 * Math.sin(ang + 0.42));
    ctx.closePath(); ctx.fill();
    ctx.restore();
  }

  _trTraceUpTo(fn, x0, x1, frac, opts) {
    const ctx = this.ctx;
    const o = opts || {};
    const N = o.n || 120;
    const upN = Math.max(0, Math.round(N * Math.min(1, Math.max(0, frac))));
    if (upN <= 0) return;
    ctx.save();
    ctx.beginPath();
    for (let i = 0; i <= upN; i++) {
      const x = i / N, sx = x0 + x * (x1 - x0), sy = fn(x);
      i ? ctx.lineTo(sx, sy) : ctx.moveTo(sx, sy);
    }
    ctx.strokeStyle = o.color || "#35e6d0";
    ctx.lineWidth = o.lw || 2;
    if (o.glow) { ctx.shadowColor = o.color || "#35e6d0"; ctx.shadowBlur = o.glow; }
    ctx.stroke(); ctx.shadowBlur = 0;
    ctx.restore();
  }

  _trIntro(ts, d) {
    const { ctx, w, h } = this;
    this._trTag("DENORM · CLAMP · LOSSES");
    const pad = { l: 46, r: 16, t: 18, b: 30 };
    const px = (x) => pad.l + x * (w - pad.l - pad.r);
    const py = (v) => pad.t + (1 - Math.min(1, v / 1.3)) * (h - pad.t - pad.b);
    this._grid(pad);

    const gt = d.target, pred = d.predRaw;
    const inClamp = ts < 26.0;
    const inLoss = ts >= 26.0;

    ctx.save();
    ctx.globalAlpha = 0.10;
    this._curvePath(gt, d.mix, px, py);
    ctx.strokeStyle = "rgba(150,176,182,0.55)"; ctx.lineWidth = 1.4; ctx.setLineDash([5, 4]); ctx.stroke(); ctx.setLineDash([]);
    ctx.restore();

    const slotL1 = gt.map((g, i) => Math.abs(g.a - pred[i].a) + Math.abs(g.mu - pred[i].mu) + Math.abs(g.s - pred[i].s));
    let mseRun = 0, upto = 0;
    const NSW = 40;

    if (inClamp) {
      const chipY = 50;
      const chips = [
        { t: "denormalize_output", t0: 0.3, a0: 0.3, a1: 5.6 },
        { t: "clamp_gaussian_params", t0: 0.8, a0: 5.6, a1: 22.0 },
        { t: "normalize_output", t0: 1.3, a0: 22.0, a1: 26.0 },
      ];
      ctx.font = "12px 'IBM Plex Mono', monospace";
      const widths = chips.map((c) => ctx.measureText(c.t).width + 24);
      const totW = widths.reduce((s, v) => s + v, 0) + 2 * 46;
      let cx0 = (w - totW) / 2;
      chips.forEach((c, i) => {
        const ca = Math.min(1, Math.max(0, (ts - c.t0) / 0.5));
        const activeC = ts >= c.a0 && ts < c.a1;
        if (ca > 0) {
          ctx.save(); ctx.globalAlpha = ca;
          ctx.fillStyle = "rgba(7,12,17,0.95)";
          ctx.strokeStyle = activeC ? "#7cff9b" : "rgba(120,200,220,0.35)";
          ctx.lineWidth = 1.4;
          ctx.beginPath();
          if (ctx.roundRect) ctx.roundRect(cx0, chipY - 17, widths[i], 26, 7); else ctx.rect(cx0, chipY - 17, widths[i], 26);
          ctx.fill(); ctx.stroke();
          ctx.fillStyle = activeC ? "#7cff9b" : "rgba(230,247,243,0.85)";
          ctx.fillText(c.t, cx0 + 12, chipY);
          if (i < 2) {
            const ax0 = cx0 + widths[i] + 9, ax1 = cx0 + widths[i] + 38;
            ctx.strokeStyle = "rgba(143,176,170,0.9)"; ctx.fillStyle = "rgba(143,176,170,0.9)"; ctx.lineWidth = 1.8;
            ctx.beginPath(); ctx.moveTo(ax0, chipY - 4); ctx.lineTo(ax1 - 6, chipY - 4); ctx.stroke();
            ctx.beginPath(); ctx.moveTo(ax1, chipY - 4); ctx.lineTo(ax1 - 8, chipY - 9); ctx.lineTo(ax1 - 8, chipY + 1); ctx.closePath(); ctx.fill();
          }
          ctx.restore();
        }
        cx0 += widths[i] + 46;
      });

      const ctr = (txt, x, y) => ctx.fillText(txt, x - ctx.measureText(txt).width / 2, y);

      const morph = (rowsM, t0, fromHead, toHead, dec, stag, dur) => {
        const pa = Math.min(1, Math.max(0, (ts - (t0 - 0.3)) / 0.4));
        if (pa <= 0) return;
        const bx = w / 2 - 340, bw2 = 680, by = 96, bh = h - 140;
        ctx.save(); ctx.globalAlpha = pa;
        ctx.fillStyle = "rgba(4,7,10,0.92)";
        ctx.strokeStyle = "rgba(120,200,220,0.3)"; ctx.lineWidth = 1.3;
        ctx.beginPath();
        if (ctx.roundRect) ctx.roundRect(bx, by, bw2, bh, 10); else ctx.rect(bx, by, bw2, bh);
        ctx.fill(); ctx.stroke();
        ctx.font = "14px 'IBM Plex Mono', monospace";
        ctx.fillStyle = "rgba(143,176,170,0.95)";
        ctx.fillText(fromHead, bx + 130, by + 30);
        ctx.fillText(toHead, bx + 470, by + 30);
        ctx.strokeStyle = "rgba(120,200,220,0.15)";
        ctx.beginPath(); ctx.moveTo(bx + 18, by + 44); ctx.lineTo(bx + bw2 - 18, by + 44); ctx.stroke();
        rowsM.forEach((r, ri) => {
          const a0 = Math.min(1, Math.max(0, (ts - t0 - ri * stag) / 0.5));
          if (a0 <= 0) return;
          const y = by + 84 + ri * Math.max(70, (bh - 116) / 3);
          const mp = this._ease(Math.min(1, Math.max(0, (ts - t0 - 1.0 - ri * stag) / dur)));
          const val = this._lerp(r.v0, r.v1, mp);
          ctx.save(); ctx.globalAlpha = pa * a0;
          ctx.font = "16px 'IBM Plex Mono', monospace";
          ctx.fillStyle = "rgba(143,176,170,0.9)";
          ctx.fillText(r.k, bx + 36, y);
          ctx.fillStyle = "rgba(230,247,243,0.9)";
          ctx.fillText(`${r.v0.toFixed(2)}${r.u0}`, bx + 130, y);
          ctx.strokeStyle = "rgba(143,176,170,0.85)"; ctx.fillStyle = "rgba(143,176,170,0.85)"; ctx.lineWidth = 2;
          ctx.beginPath(); ctx.moveTo(bx + 330, y - 5); ctx.lineTo(bx + 408, y - 5); ctx.stroke();
          ctx.beginPath(); ctx.moveTo(bx + 418, y - 5); ctx.lineTo(bx + 406, y - 12); ctx.lineTo(bx + 406, y + 2); ctx.closePath(); ctx.fill();
          if (mp > 0) {
            ctx.fillStyle = mp >= 1 ? "#7cff9b" : "#ffcf6b";
            ctx.fillText(`${val.toFixed(dec)}${r.u1}`, bx + 470, y);
          }
          ctx.restore();
        });
        ctx.restore();
      };

      if (ts >= 0.5 && ts < 5.6) {
        morph([
          { k: "a",     v0: -0.84, v1: -300.0, u0: "", u1: "" },
          { k: "mu",    v0: 2.31,  v1: 131.0,  u0: "", u1: " m" },
          { k: "sigma", v0: -1.07, v1: -12.5,  u0: "", u1: " m" },
        ], 0.8, "normalized", "physical", 1, 0.7, 1.8);
      }

      const rows2 = [
        { k: "a",     lo: "0",              hi: "amp_max = 1000",  raw: -0.30, pr: -300.0, pc: 0.0,   u: "",   t0: 5.6 },
        { k: "mu",    lo: "x_min = -20 m",  hi: "x_max = 100 m",   raw: 1.26,  pr: 131.0,  pc: 100.0, u: " m", t0: 8.6 },
        { k: "sigma", lo: "x_step/2 = 0.6", hi: "x_range/2 = 60",  raw: -0.22, pr: -12.5,  pc: 0.6,   u: " m", t0: 11.6 },
      ];
      const rx0 = w / 2 - 260, rx1 = w / 2 + 260;
      const rowsFade = ts < 14.6 ? 1 : Math.max(0, 1 - (ts - 14.6) / 0.5);
      if (ts >= 5.6 && rowsFade > 0) {
        ctx.save(); ctx.globalAlpha = rowsFade;
        ctx.font = "11px 'IBM Plex Mono', monospace"; ctx.fillStyle = "#5e7280";
        const subl = "bounds from dataset metadata (example values)";
        ctx.fillText(subl, w / 2 - ctx.measureText(subl).width / 2, h - pad.b - 6);
        ctx.restore();
      }
      if (ts >= 5.6 && rowsFade > 0) rows2.forEach((r, ri) => {
        const ra = Math.min(1, Math.max(0, (ts - r.t0) / 0.4)) * rowsFade;
        if (ra <= 0) return;
        const focus = ts >= r.t0 && (ri === 2 ? ts < 14.6 : ts < rows2[ri + 1].t0);
        const y = h * 0.29 + ri * h * 0.215;
        ctx.save(); ctx.globalAlpha = ra * (focus ? 1 : 0.55);
        ctx.strokeStyle = focus ? "rgba(230,247,243,0.7)" : "rgba(143,176,170,0.45)"; ctx.lineWidth = 1.3;
        ctx.beginPath(); ctx.moveTo(rx0, y); ctx.lineTo(rx1, y); ctx.stroke();
        ctx.beginPath(); ctx.moveTo(rx0, y - 9); ctx.lineTo(rx0, y + 9); ctx.stroke();
        ctx.beginPath(); ctx.moveTo(rx1, y - 9); ctx.lineTo(rx1, y + 9); ctx.stroke();
        ctx.font = "15px 'IBM Plex Mono', monospace";
        ctx.fillStyle = focus ? "#ffcf6b" : "rgba(230,247,243,0.9)";
        ctx.fillText(r.k, r.raw > 1 ? rx0 - 86 : rx1 + 34, y + 5);
        ctx.font = "12px 'IBM Plex Mono', monospace";
        ctx.fillStyle = "rgba(143,176,170,0.85)";
        ctr(r.lo, rx0, y + 26);
        ctr(r.hi, rx1, y + 26);

        const xOf = (v) => rx0 + Math.min(1.45, Math.max(-0.45, v)) * (rx1 - rx0);
        const da = Math.min(1, Math.max(0, (ts - r.t0 - 0.7) / 0.3));
        if (da <= 0) { ctx.restore(); return; }
        const cp = this._ease(Math.min(1, Math.max(0, (ts - r.t0 - 1.7) / 1.0)));
        const vNow = this._lerp(r.raw, Math.min(1, Math.max(0, r.raw)), cp);
        const pNow = this._lerp(r.pr, r.pc, cp);
        ctx.save(); ctx.globalAlpha = ra * (focus ? 1 : 0.55) * da;
        if (cp < 1 && cp > 0) {
          ctx.strokeStyle = "rgba(255,107,125,0.5)"; ctx.setLineDash([3, 3]); ctx.lineWidth = 1.2;
          ctx.beginPath(); ctx.moveTo(xOf(r.raw), y); ctx.lineTo(xOf(vNow), y); ctx.stroke(); ctx.setLineDash([]);
        }
        ctx.fillStyle = cp >= 1 ? "#7cff9b" : "#ff6b7d";
        ctx.beginPath(); ctx.arc(xOf(vNow), y, 6, 0, 7); ctx.fill();
        if (focus && cp <= 0) {
          ctx.strokeStyle = "rgba(255,107,125,0.85)"; ctx.lineWidth = 1.6;
          ctx.beginPath(); ctx.arc(xOf(r.raw), y, 12 + Math.sin(this.t * 5) * 1.6, 0, 7); ctx.stroke();
        }
        ctx.font = "13px 'IBM Plex Mono', monospace";
        if (cp >= 1) {
          ctx.fillStyle = "#7cff9b";
          ctr(`clamped: ${r.pc.toFixed(1)}${r.u}`, xOf(vNow), y - 19);
        } else if (cp <= 0) {
          ctx.fillStyle = "#ff6b7d";
          ctr(`out of range: ${r.pr.toFixed(1)}${r.u}`, xOf(r.raw), y - 19);
        } else {
          ctx.fillStyle = "#ffcf6b";
          ctr(`${pNow.toFixed(1)}${r.u}`, xOf(vNow), y - 19);
        }
        ctx.restore();
        ctx.restore();
      });

      if (ts >= 14.8 && ts < 22.0) {
        const la = Math.min(1, (ts - 14.8) / 0.5);
        const panels = [
          { x0: 70,         x1: w / 2 - 30, title: "hard clamp",                slope: 0.0,  oc: "#ff6b7d", dv: "0" },
          { x0: w / 2 + 30, x1: w - 70,     title: "leaky clamp  ·  slope 0.01", slope: 0.35, oc: "#7cff9b", dv: "0.01" },
        ];
        const fy0 = 92, fy1 = h * 0.62;
        const dy0 = fy1 + 20, dy1 = fy1 + 20 + h * 0.14;
        const fP = this._ease(Math.min(1, Math.max(0, (ts - 15.0) / 1.2)));
        const dotP = this._ease(Math.min(1, Math.max(0, (ts - 16.4) / 1.6)));
        const dP = this._ease(Math.min(1, Math.max(0, (ts - 18.2) / 1.2)));
        const hl = Math.min(1, Math.max(0, (ts - 19.6) / 0.6));
        const backP = this._ease(Math.min(1, Math.max(0, (ts - 19.8) / 1.2)));
        ctx.save(); ctx.globalAlpha = la;
        panels.forEach((pn, pi) => {
          const xT = (v) => pn.x0 + (v / 1.7) * (pn.x1 - pn.x0);
          const yF = (v) => fy1 - (v / 1.3) * (fy1 - fy0);
          const yD = (v) => (dy1 - 9) - v / 1.25 * (dy1 - dy0 - 16);
          const fn = (x) => x <= 1 ? x : 1 + pn.slope * (x - 1);
          const dfn = (x) => x <= 1 ? 1 : pn.slope;

          ctx.font = "13px 'IBM Plex Mono', monospace";
          ctx.fillStyle = "rgba(230,247,243,0.92)";
          ctx.fillText(pn.title, pn.x0, fy0 - 10);

          ctx.strokeStyle = "rgba(120,200,220,0.22)"; ctx.lineWidth = 1;
          ctx.strokeRect(pn.x0, fy0, pn.x1 - pn.x0, fy1 - fy0);
          ctx.setLineDash([4, 4]);
          ctx.strokeStyle = "rgba(255,207,107,0.5)";
          ctx.beginPath(); ctx.moveTo(xT(1), fy0); ctx.lineTo(xT(1), dy1); ctx.stroke();
          ctx.setLineDash([]);
          ctx.font = "11px 'IBM Plex Mono', monospace";
          ctx.fillStyle = "rgba(255,207,107,0.85)";
          ctx.fillText("bound", xT(1) + 6, fy1 - 8);

          if (hl > 0) {
            ctx.save(); ctx.globalAlpha = la * hl * (0.10 + 0.05 * Math.sin(this.t * 3));
            ctx.fillStyle = pn.oc;
            ctx.fillRect(xT(1), fy0, pn.x1 - xT(1), dy1 - fy0);
            ctx.restore();
          }

          if (fP > 0) {
            const drawTo = 1.7 * fP;
            const segs = [
              { a: 0, b: 1, c: "#35e6d0", lw: 2.6 },
              { a: 1, b: 1.7, c: pn.oc, lw: 3.4 },
            ];
            segs.forEach((sg) => {
              const bEnd = Math.min(sg.b, drawTo);
              if (bEnd <= sg.a) return;
              ctx.beginPath();
              ctx.moveTo(xT(sg.a), yF(fn(sg.a)));
              ctx.lineTo(xT(bEnd), yF(fn(bEnd)));
              ctx.strokeStyle = sg.c; ctx.lineWidth = sg.lw;
              ctx.shadowColor = sg.c; ctx.shadowBlur = 6; ctx.stroke(); ctx.shadowBlur = 0;
            });
          }

          if (dotP > 0) {
            let xq = this._lerp(0.55, 1.5, dotP);
            let frozen = false;
            if (pi === 1 && backP > 0) xq = this._lerp(1.5, 1.0, backP);
            if (pi === 0 && backP > 0) frozen = true;
            const Y = yF(fn(xq));
            ctx.strokeStyle = "rgba(255,207,107,0.4)"; ctx.lineWidth = 1;
            ctx.beginPath(); ctx.moveTo(xT(xq), fy0); ctx.lineTo(xT(xq), fy1); ctx.stroke();
            const dc = xq > 1.001 ? pn.oc : "#e6f7f3";
            ctx.fillStyle = dc;
            ctx.beginPath(); ctx.arc(xT(xq), Y, 6, 0, 7); ctx.fill();
            if (frozen) {
              ctx.strokeStyle = "#ff6b7d"; ctx.lineWidth = 2.4;
              const X = xT(xq);
              ctx.beginPath(); ctx.moveTo(X - 8, Y - 18); ctx.lineTo(X + 8, Y - 34); ctx.stroke();
              ctx.beginPath(); ctx.moveTo(X - 8, Y - 34); ctx.lineTo(X + 8, Y - 18); ctx.stroke();
            }
            if (pi === 1 && backP > 0 && backP < 1) {
              const X = xT(xq);
              ctx.strokeStyle = "#7cff9b"; ctx.fillStyle = "#7cff9b"; ctx.lineWidth = 2;
              ctx.beginPath(); ctx.moveTo(X + 30, Y - 18); ctx.lineTo(X + 10, Y - 5); ctx.stroke();
              ctx.beginPath(); ctx.moveTo(X + 10, Y - 5);
              ctx.lineTo(X + 19, Y - 7); ctx.lineTo(X + 14, Y - 15); ctx.closePath(); ctx.fill();
            }
          }

          if (dP > 0) {
            ctx.strokeStyle = "rgba(120,200,220,0.18)"; ctx.lineWidth = 1;
            ctx.strokeRect(pn.x0, dy0, pn.x1 - pn.x0, dy1 - dy0);
            ctx.strokeStyle = "rgba(150,176,182,0.5)"; ctx.setLineDash([3, 4]); ctx.lineWidth = 1;
            ctx.beginPath(); ctx.moveTo(pn.x0, yD(0)); ctx.lineTo(pn.x1, yD(0)); ctx.stroke();
            ctx.setLineDash([]);
            ctx.font = "11px 'IBM Plex Mono', monospace";
            ctx.fillStyle = "rgba(150,176,182,0.8)";
            ctx.fillText("0", pn.x0 - 12, yD(0) + 4);
            const drawTo = 1.7 * dP;
            ctx.beginPath();
            ctx.moveTo(xT(0), yD(1));
            ctx.lineTo(xT(Math.min(1, drawTo)), yD(1));
            if (drawTo > 1) {
              ctx.lineTo(xT(1), yD(dfn(1.01)));
              ctx.lineTo(xT(drawTo), yD(dfn(1.01)));
            }
            ctx.strokeStyle = pn.oc; ctx.lineWidth = 2.6; ctx.stroke();
            if (dP >= 1) {
              ctx.font = "13px 'IBM Plex Mono', monospace";
              ctx.fillStyle = pn.oc;
              ctx.fillText(pn.dv, xT(1.32), yD(pn.slope) - 10);
            }
          }
        });
        ctx.font = "11px 'IBM Plex Mono', monospace";
        ctx.fillStyle = "rgba(143,176,170,0.85)";
        if (dP > 0) ctx.fillText("gradient  d(out)/d(raw)", 70, dy1 + 16);
        ctx.restore();
      }

      if (ts >= 21.9) {
        morph([
          { k: "a",     v0: 0.0,   v1: -0.42, u0: "",   u1: "" },
          { k: "mu",    v0: 100.0, v1: 1.78,  u0: " m", u1: "" },
          { k: "sigma", v0: 0.6,   v1: -0.93, u0: " m", u1: "" },
        ], 22.1, "physical (clamped)", "normalized", 2, 0.6, 1.6);
      }
    }

    if (inLoss) {
      const ap = this._ease((ts - 26.0) / 0.6);
      const pL = { x0: 18, x1: w / 2 - 10 };
      const pR = { x0: w / 2 + 10, x1: w - 18 };
      const pTop = 64, pBot = h - 38;
      const G = "#7cff9b";

      ctx.save(); ctx.globalAlpha = ap;
      [pL, pR].forEach((pn, i) => {
        ctx.fillStyle = "rgba(4,7,10,0.9)";
        ctx.strokeStyle = "rgba(120,200,220,0.25)"; ctx.lineWidth = 1.2;
        ctx.beginPath();
        if (ctx.roundRect) ctx.roundRect(pn.x0, pTop, pn.x1 - pn.x0, pBot - pTop, 10); else ctx.rect(pn.x0, pTop, pn.x1 - pn.x0, pBot - pTop);
        ctx.fill(); ctx.stroke();
        ctx.font = "12px 'IBM Plex Mono', monospace";
        ctx.fillStyle = "rgba(230,247,243,0.9)";
        ctx.fillText(i === 0 ? "parameter space" : "curve space", pn.x0 + 14, pTop - 8);
      });
      ctx.restore();

      const eqA = Math.min(1, Math.max(0, (ts - 26.8) / 0.6));
      ctx.save(); ctx.globalAlpha = eqA * ap;
      ctx.font = "14px 'IBM Plex Mono', monospace";
      ctx.fillStyle = "#ffcf6b";
      ctx.fillText("L1 param loss", pL.x0 + 16, pTop + 30);
      ctx.fillText("MSE curve loss", pR.x0 + 16, pTop + 30);
      ctx.restore();

      const ranges = [
        { k: "a",     max: 1.0  },
        { k: "mu",    max: 1.0  },
        { k: "sigma", max: 0.15 },
      ];
      const PC = ["#ff6b7d", "#ffcf6b", "#7aa2ff"];
      const tx0 = pL.x0 + 118, tx1 = pL.x1 - 64;
      const blockStep = (pBot - 16 - 68 - (pTop + 44)) / 2;
      const yS = [pTop + 44, pTop + 44 + blockStep, pTop + 44 + 2 * blockStep];
      ctx.save(); ctx.globalAlpha = ap;
      ctx.strokeStyle = "rgba(120,200,220,0.25)"; ctx.setLineDash([4, 5]); ctx.lineWidth = 1;
      [1, 2].forEach((k) => {
        const sy = (yS[k - 1] + 68 + yS[k]) / 2 + 6;
        ctx.beginPath(); ctx.moveTo(pL.x0 + 12, sy); ctx.lineTo(pL.x1 - 12, sy); ctx.stroke();
      });
      ctx.setLineDash([]); ctx.restore();
      gt.forEach((g, i) => {
        const p = pred[i];
        const y0 = yS[i];
        const hd = Math.min(1, Math.max(0, (ts - 27.6 - i * 0.3) / 0.5));
        if (hd <= 0) return;
        ctx.save(); ctx.globalAlpha = hd;
        ctx.font = "14px 'IBM Plex Mono', monospace";
        ctx.fillStyle = G; ctx.fillText(`slot ${i + 1}`, pL.x0 + 14, y0 + 38);

        ranges.forEach((r, ri) => {
          const ra = Math.min(1, Math.max(0, (ts - 27.8 - (i * 3 + ri) * 0.3) / 0.4));
          if (ra <= 0) return;
          const y = y0 + ri * 34;
          const gv = [g.a, g.mu, g.s][ri], pv = [p.a, p.mu, p.s][ri];
          const X = (v) => tx0 + (v / r.max) * (tx1 - tx0);
          ctx.save(); ctx.globalAlpha = hd * ra;
          ctx.font = "13px 'IBM Plex Mono', monospace";
          ctx.fillStyle = PC[ri]; ctx.fillText(r.k, pL.x0 + 76, y + 4);
          ctx.strokeStyle = "rgba(120,200,220,0.14)"; ctx.lineWidth = 1;
          ctx.beginPath(); ctx.moveTo(tx0, y); ctx.lineTo(tx1, y); ctx.stroke();
          const gp = this._ease(Math.min(1, Math.max(0, (ts - 28.3 - (i * 3 + ri) * 0.3) / 0.5)));
          if (gp > 0) {
            ctx.strokeStyle = PC[ri]; ctx.lineWidth = 3;
            ctx.beginPath(); ctx.moveTo(X(gv), y); ctx.lineTo(X(this._lerp(gv, pv, gp)), y); ctx.stroke();
          }
          ctx.fillStyle = "rgba(230,247,243,0.95)";
          ctx.beginPath(); ctx.arc(X(gv), y, 3.8, 0, 7); ctx.fill();
          ctx.fillStyle = "#35e6d0";
          ctx.beginPath(); ctx.arc(X(pv), y, 3.8, 0, 7); ctx.fill();
          if (gp >= 1) {
            ctx.fillStyle = PC[ri]; ctx.font = "13px 'IBM Plex Mono', monospace";
            ctx.fillText(Math.abs(gv - pv).toFixed(2), tx1 + 14, y + 4);
          }
          ctx.restore();
        });
        ctx.restore();
      });

      const prA = Math.min(1, Math.max(0, (ts - 31.4) / 0.5));
      if (prA > 0) {
        ctx.save(); ctx.globalAlpha = prA;
        ctx.font = "13px 'IBM Plex Mono', monospace";
        ctx.fillStyle = G;
        const rtot = `param_l1 = ${(slotL1[0] + slotL1[1] + slotL1[2]).toFixed(2)}`;
        ctx.fillText(rtot, pL.x1 - ctx.measureText(rtot).width - 14, pTop + 30);
        ctx.restore();
      }

      const cx0 = pR.x0 + 20, cx1 = pR.x1 - 20;
      const cy0 = pTop + 56, cy1 = pBot - 50;
      const pxc = (x) => cx0 + x * (cx1 - cx0);
      const pyc = (v) => cy0 + (1 - Math.min(1, v / 1.3)) * (cy1 - cy0);
      const cvA = this._ease(Math.min(1, Math.max(0, (ts - 31.8) / 0.8)));
      if (cvA > 0) {
        ctx.save(); ctx.globalAlpha = cvA;
        ctx.beginPath();
        for (let i = 0; i <= 120; i++) {
          const x = i / 120;
          i ? ctx.lineTo(pxc(x), pyc(d.mix(gt, x))) : ctx.moveTo(pxc(x), pyc(d.mix(gt, x)));
        }
        ctx.strokeStyle = "rgba(150,176,182,0.55)"; ctx.lineWidth = 1.3; ctx.setLineDash([5, 4]); ctx.stroke(); ctx.setLineDash([]);
        ctx.beginPath();
        for (let i = 0; i <= Math.round(120 * cvA); i++) {
          const x = i / 120;
          i ? ctx.lineTo(pxc(x), pyc(d.mix(pred, x))) : ctx.moveTo(pxc(x), pyc(d.mix(pred, x)));
        }
        ctx.strokeStyle = "#35e6d0"; ctx.lineWidth = 2; ctx.shadowColor = "rgba(53,230,208,0.5)"; ctx.shadowBlur = 6; ctx.stroke(); ctx.shadowBlur = 0;
        ctx.restore();
      }

      if (ts >= 32.8) {
        const sp = Math.min(1, (ts - 32.8) / 2.8);
        const xs = sp;
        upto = Math.floor(xs * NSW);
        ctx.save(); ctx.globalAlpha = 1;
        const NF = 120;
        const nUp = Math.max(1, Math.round(NF * xs));
        ctx.beginPath();
        for (let i = 0; i <= nUp; i++) {
          const x = i / NF;
          i ? ctx.lineTo(pxc(x), pyc(d.mix(gt, x))) : ctx.moveTo(pxc(x), pyc(d.mix(gt, x)));
        }
        for (let i = nUp; i >= 0; i--) {
          const x = i / NF;
          ctx.lineTo(pxc(x), pyc(d.mix(pred, x)));
        }
        ctx.closePath();
        ctx.fillStyle = "rgba(255,107,125,0.12)"; ctx.fill();

        let acc = 0;
        const NI = Math.max(1, Math.round(160 * xs));
        for (let i = 0; i <= NI; i++) {
          const x = (i / NI) * xs;
          const dv = d.mix(pred, x) - d.mix(gt, x);
          acc += dv * dv;
        }
        mseRun = acc / (NI + 1);

        if (sp < 1) {
          ctx.strokeStyle = "rgba(255,207,107,0.7)"; ctx.lineWidth = 1.2;
          ctx.beginPath(); ctx.moveTo(pxc(xs), cy0); ctx.lineTo(pxc(xs), cy1); ctx.stroke();
        }
        ctx.font = "13px 'IBM Plex Mono', monospace";
        ctx.fillStyle = sp >= 1 ? G : "rgba(255,207,107,0.95)";
        ctx.fillText(sp >= 1 ? `mse = ${mseRun.toFixed(3)}` : `running mse = ${mseRun.toFixed(3)}  ·  ${upto + 1}/${NSW + 1}`, pR.x0 + 14, pBot - 16);
        ctx.restore();
      }
    }

    if (ts < 5.6) this._cap("denormalize_output  ·  the net speaks in normalized units  ·  converted to physical [a, mu (m), sigma (m)] first");
    else if (ts < 8.6) this._cap("clamp a in PHYSICAL units:  negative power is impossible -> raised to 0  ·  above amp_max -> capped");
    else if (ts < 11.6) this._cap("clamp mu:  a peak outside the physical axis [x_min, x_max] is pulled back to the nearest edge");
    else if (ts < 14.8) this._cap("clamp sigma:  width below x_step/2 is sharper than the sampling -> raised  ·  above x_range/2 -> capped");
    else if (ts < 16.4) this._cap("Hard clamp vs leaky clamp  ·  identical inside the bounds");
    else if (ts < 18.2) this._cap("Drive the same raw value past the bound:  hard flatlines  ·  leaky keeps rising at slope 0.01");
    else if (ts < 19.8) this._cap("Underneath, the derivative:  hard -> 0  ·  leaky -> 0.01");
    else if (ts < 22.0) this._cap("Gradient 0 = stuck forever (x)  ·  gradient 0.01 pulls the stray back inside the bounds");
    else if (ts < 26.0) this._cap("normalize_output  ·  the clamped physical values return to normalized space  ·  the loss only sees plausible params");
    else if (ts < 27.8) this._cap("Two ways to grade the same prediction  ·  parameter space vs curve space  ·  side by side");
    else if (ts < 31.4) this._cap("L_param reads [a, mu, sigma] slot against slot  ·  plain numbers, no reconstruction");
    else if (ts < 32.8) this._cap(`param_l1 = ${(slotL1[0] + slotL1[1] + slotL1[2]).toFixed(2)}  ·  now the curve view: reconstruct the prediction and compare shapes`);
    else if (ts < 35.8) this._cap(`L_mse sweeps the height axis  ·  each (ŷ - y)² joins the running mean  ·  ${upto + 1}/${NSW + 1}`);
    else this._cap(`Same prediction, two scores: param_l1 = ${(slotL1[0] + slotL1[1] + slotL1[2]).toFixed(2)}, mse = ${mseRun.toFixed(3)}  ·  the curriculum trains on params first`);
  }

  _trStep(ts, d) {
    const { ctx, w, h } = this;
    this._trTag("STEP ANATOMY");

    const A = 2;
    const railNodes = ["forward", "loss", "÷ A", "backward"];
    const railY = Math.round(h * 0.30);
    const nodeW = Math.min(150, (w - 80 - 3 * 26) / 4);
    const nodeH = 38;
    const railX0 = (w - (4 * nodeW + 3 * 26)) / 2;
    const nodeX = (i) => railX0 + i * (nodeW + 26);

    const dockY = Math.round(h * 0.60);
    const dockNodes = ["clip", "record norm", "optimizer.step", "zero_grad"];
    const dockW = Math.min(140, (w - 70 - 3 * 16) / 4);
    const dockH = 34;
    const dockX0 = (w - (4 * dockW + 3 * 16)) / 2;
    const dockX = (i) => dockX0 + i * (dockW + 16);

    let batchIdx = 1, gstep = 0;
    if (ts >= 14.5) { batchIdx = 2; gstep = 1; }
    if (ts >= 25.0) { batchIdx = (Math.floor((ts - 25.0) * 2) % 2) + 1; }

    const boundary = (ts >= 14.5 && ts < 25.0) || (ts >= 25.0 && batchIdx === 2);
    const dockOpen = this._ease(Math.min(1, Math.max(0, (ts - 14.5) / 1.0)));

    let tokenStage = -1, tokenP = 0;
    const cyc = (a, b) => this._ease(Math.min(1, Math.max(0, (ts - a) / (b - a))));
    if (ts >= 3.0 && ts < 7.5) { tokenStage = 0; tokenP = cyc(3.0, 7.5); }
    else if (ts >= 7.5 && ts < 11.0) { tokenStage = 1; tokenP = cyc(7.5, 11.0); }
    else if (ts >= 11.0 && ts < 14.5) { tokenStage = 3; tokenP = cyc(11.0, 14.5); }
    else if (ts >= 14.5 && ts < 18.0) { tokenStage = 3; tokenP = cyc(14.5, 18.0); }
    else if (ts >= 28.0) { const lp = ((ts - 28.0) % 1.4) / 1.4; tokenStage = Math.floor(lp * 4); tokenP = (lp * 4) % 1; }

    const skel = this._ease(Math.min(1, ts / 1.6));
    const ampOn = ts >= 3.0;
    const ampReg = { x0: nodeX(0) - 8, x1: nodeX(2) + nodeW + 8, y0: railY - 14, y1: railY + nodeH + 14 };

    if (ampOn) {
      const aa = this._ease(Math.min(1, (ts - 3.0) / 0.8)) * 0.9;
      ctx.save(); ctx.globalAlpha = aa;
      ctx.fillStyle = "rgba(53,230,208,0.06)";
      ctx.strokeStyle = "rgba(53,230,208,0.35)"; ctx.setLineDash([5, 4]); ctx.lineWidth = 1.2;
      ctx.beginPath();
      if (ctx.roundRect) ctx.roundRect(ampReg.x0, ampReg.y0, ampReg.x1 - ampReg.x0, ampReg.y1 - ampReg.y0, 9); else ctx.rect(ampReg.x0, ampReg.y0, ampReg.x1 - ampReg.x0, ampReg.y1 - ampReg.y0);
      ctx.fill(); ctx.stroke(); ctx.setLineDash([]);
      ctx.font = "11px 'IBM Plex Mono', monospace"; ctx.fillStyle = "rgba(53,230,208,0.9)";
      ctx.fillText("torch.autocast(bfloat16)  ·  use_amp (default off)", ampReg.x0 + 6, ampReg.y0 - 6);
      ctx.restore();
    }

    for (let i = 0; i < 3; i++) {
      this._trArrow(nodeX(i) + nodeW, railY + nodeH / 2, nodeX(i + 1) - 6, railY + nodeH / 2, "rgba(143,176,170,0.8)", skel);
    }
    railNodes.forEach((nm, i) => {
      const lit = tokenStage === i && tokenP < 1;
      this._trChip(nodeX(i), railY, nodeW, nodeH, nm, { active: lit, color: "#35e6d0", alpha: skel });
    });

    if (ts >= 8.0 && ts < 11.5) {
      const da = this._ease(Math.min(1, (ts - 8.0) / 0.6));
      const cx = nodeX(2) + nodeW / 2;
      const dv = ts < 9.0 ? "1.00" : (1 / A).toFixed(2);
      ctx.save(); ctx.globalAlpha = da;
      ctx.font = "12px 'IBM Plex Mono', monospace"; ctx.fillStyle = dv === "1.00" ? "#ffcf6b" : "#7cff9b";
      ctx.fillText(`${dv}  (A = ${A})`, cx - 34, railY - 6);
      ctx.restore();
    }

    if (ts >= 8.4 && ts < 13.6) {
      const ea = this._ease(Math.min(1, (ts - 8.4) / 0.7)) * (1 - this._ease(Math.min(1, Math.max(0, (ts - 12.6) / 1.0))));
      this._texDraw("\\mathcal{L}\\leftarrow\\mathcal{L}/A", w / 2, railY + nodeH + 16, 15, { align: "center", alpha: ea, color: "rgba(124,255,155,0.95)" });
    }

    if (ts >= 11.0 && ts < 18.0) {
      const accFull = ts < 14.5 ? (batchIdx) / A : 1;
      const bx = nodeX(3) + 4, by = railY + nodeH + 8, bw = nodeW - 8, bh = 8;
      ctx.save();
      ctx.strokeStyle = "rgba(120,200,220,0.4)"; ctx.lineWidth = 1; ctx.strokeRect(bx, by, bw, bh);
      ctx.fillStyle = "rgba(124,255,155,0.7)"; ctx.fillRect(bx + 1, by + 1, (bw - 2) * Math.min(1, accFull), bh - 2);
      ctx.font = "10px 'IBM Plex Mono', monospace"; ctx.fillStyle = "rgba(143,176,170,0.85)";
      ctx.fillText("grads accumulate", bx, by + bh + 12);
      ctx.restore();
    }

    if (ts >= 11.0) {
      const la = this._ease(Math.min(1, (ts - 11.0) / 0.5));
      ctx.save(); ctx.globalAlpha = la * 0.9;
      ctx.font = "11px 'IBM Plex Mono', monospace"; ctx.fillStyle = "rgba(143,176,170,0.85)";
      ctx.fillText("loss.backward()", nodeX(3), railY - 6);
      ctx.restore();
    }

    if (ts >= 13.5) {
      const ga = this._ease(Math.min(1, (ts - 13.5) / 0.8));
      const cx = (nodeX(3) + nodeW / 2);
      ctx.save(); ctx.globalAlpha = ga;
      ctx.font = "12px 'IBM Plex Mono', monospace";
      ctx.fillStyle = boundary ? "#7cff9b" : "rgba(143,176,170,0.85)";
      const gtxt = "(batch_idx + 1) % A == 0  or  last batch";
      ctx.fillText(gtxt, w / 2 - ctx.measureText(gtxt).width / 2, (railY + nodeH + dockY) / 2 + 2);
      ctx.restore();
    }

    if (dockOpen > 0) {
      const yOff = (1 - dockOpen) * 24;
      ctx.save(); ctx.globalAlpha = dockOpen;
      const seqHit = (i) => this._ease(Math.min(1, Math.max(0, (ts - 18.0 - i * 0.8) / 0.6)));
      for (let i = 0; i < 3; i++) {
        this._trArrow(dockX(i) + dockW, dockY + dockH / 2 - yOff, dockX(i + 1) - 4, dockY + dockH / 2 - yOff, "rgba(143,176,170,0.7)", dockOpen * seqHit(i + 1));
      }
      dockNodes.forEach((nm, i) => {
        const lit = ts >= 18.0 + i * 0.8 && ts < 18.0 + i * 0.8 + 1.4;
        this._trChip(dockX(i), dockY - yOff, dockW, dockH, nm, { active: lit, color: i === 0 ? "#ffcf6b" : "#7cff9b", alpha: dockOpen });
      });

      ctx.restore();
    } else {
      ctx.save(); ctx.globalAlpha = 0.4;
      ctx.strokeStyle = "rgba(120,200,220,0.18)"; ctx.setLineDash([4, 4]); ctx.lineWidth = 1;
      for (let i = 0; i < 4; i++) {
        ctx.beginPath();
        if (ctx.roundRect) ctx.roundRect(dockX(i), dockY, dockW, dockH, 7); else ctx.rect(dockX(i), dockY, dockW, dockH);
        ctx.stroke();
      }
      ctx.setLineDash([]);
      ctx.font = "11px 'IBM Plex Mono', monospace"; ctx.fillStyle = "rgba(94,114,128,0.9)";
      ctx.fillText("conditional update — opens on a boundary", dockX0, dockY - 8);
      ctx.restore();
    }

    if (ts >= 18.5) {
      const wa = this._ease(Math.min(1, (ts - 18.5) / 1.4));
      const panX = dockX(2) + dockW / 2;
      const panTop = dockY + dockH + 6;
      const cxm = Math.min(panX, w * 0.44);
      ctx.save(); ctx.globalAlpha = wa;
      ctx.strokeStyle = "rgba(124,255,155,0.45)"; ctx.lineWidth = 1.4;
      ctx.beginPath(); ctx.moveTo(panX, dockY + dockH); ctx.lineTo(panX, panTop + 1); ctx.stroke();
      ctx.fillStyle = "rgba(124,255,155,0.85)"; ctx.font = "10px 'IBM Plex Mono', monospace";
      const htxt = "inside optimizer.step → AdamW (decoupled weight decay)";
      ctx.fillText(htxt, cxm - ctx.measureText(htxt).width / 2, panTop + 6);
      ctx.restore();
      this._texDraw("\\hat m_t=\\tfrac{m_t}{1-\\beta_1^{t}},\\ \\hat v_t=\\tfrac{v_t}{1-\\beta_2^{t}}", cxm, panTop + 8, 11, { align: "center", alpha: wa, color: "rgba(143,176,170,0.9)" });
      this._texDraw("\\theta\\leftarrow\\theta-\\eta\\,(\\,\\tfrac{\\hat m_t}{\\sqrt{\\hat v_t}+\\epsilon}+\\lambda\\theta\\,)", cxm, panTop + 24, 14, { align: "center", alpha: wa, color: "rgba(124,255,155,0.95)" });
      ctx.save(); ctx.globalAlpha = wa;
      ctx.font = "10px 'IBM Plex Mono', monospace"; ctx.fillStyle = "#7e8c94";
      const ctag = "β1=0.9 · β2=0.999 · ε=1e-8 · λ=0.1 · per-group η";
      ctx.fillText(ctag, cxm - ctx.measureText(ctag).width / 2, panTop + 64);
      ctx.restore();
    }

    if (ts >= 25.0) {
      const wm = Math.sin(this.t * 8) > 0;
      const sm = Math.sin(this.t * 0.8) > 0;
      const ry = h - 54, ry2 = h - 30;
      ctx.save();
      ctx.font = "11px 'IBM Plex Mono', monospace";
      ctx.fillStyle = "rgba(53,230,208,0.9)";
      ctx.fillText("warmup.step()  ·  every mini-batch", 24, ry);
      ctx.fillStyle = wm ? "#35e6d0" : "rgba(53,230,208,0.25)";
      ctx.beginPath(); ctx.arc(w - 40, ry - 4, 5, 0, 7); ctx.fill();
      ctx.fillStyle = "rgba(124,255,155,0.9)";
      ctx.fillText("scheduler.step()  ·  once per epoch", 24, ry2);
      ctx.fillStyle = sm ? "#7cff9b" : "rgba(124,255,155,0.25)";
      ctx.beginPath(); ctx.arc(w - 40, ry2 - 4, 5, 0, 7); ctx.fill();
      ctx.restore();
    }

    if (tokenStage >= 0 && tokenStage < 4) {
      const tx = nodeX(tokenStage) + tokenP * nodeW;
      const ty = railY + nodeH / 2;
      ctx.save();
      ctx.fillStyle = "#7cff9b"; ctx.shadowColor = "#7cff9b"; ctx.shadowBlur = 10;
      ctx.beginPath(); ctx.arc(tx, ty, 6, 0, 7); ctx.fill();
      ctx.shadowBlur = 0; ctx.restore();
    }

    {
      ctx.save();
      ctx.font = "11px 'IBM Plex Mono', monospace";
      ctx.textAlign = "right";
      ctx.fillStyle = "rgba(230,247,243,0.92)";
      ctx.fillText(`batch ${batchIdx}`, w - 18, 22);
      ctx.fillText(`global_step ${gstep}`, w - 18, 38);
      ctx.fillStyle = "#5e7280";
      ctx.fillText(`A = ${A} (example)`, w - 18, 54);
      ctx.textAlign = "left";
      ctx.restore();
    }

    if (ts < 3.0) this._cap("One optimizer step, in order  ·  the epoch loop just calls this, batch after batch");
    else if (ts < 7.5) this._cap("Forward under torch.autocast(bfloat16)  ·  use_amp gates the half-precision region (default off)");
    else if (ts < 11.0) this._cap("loss = criterion(pred, gt)  ·  then loss /= accumulation_steps  ·  grads shrink so A batches sum to one true step");
    else if (ts < 14.5) this._cap("loss.backward()  ·  on a non-boundary batch the step ENDS here — grads just accumulate");
    else if (ts < 18.0) this._cap("Boundary reached: (batch_idx + 1) % A == 0 (or last batch)  ·  now the real update fires");
    else if (ts < 25.0) this._cap("clip (max_grad_norm = 1.0) -> record norm -> optimizer.step -> zero_grad  ·  a non-finite loss aborts BEFORE the step");
    else if (ts < 28.0) this._cap("Two clocks: warmup steps every mini-batch  ·  the LR scheduler steps once per epoch");
    else this._cap("That is one step  ·  repeat per batch, then validate every 5 epochs  ·  next: the schedules these clocks drive");
  }

  _trSched(ts, d) {
    const { ctx, w, h } = this;
    this._trTag("LR SCHEDULE");
    const pad = { l: 52, r: 16, t: 18, b: 30 };
    this._axes(pad, "step", "lr");
    const TOT = d.E * d.SPE;
    const yMax = d.BASE * 1.12;
    const pyL = (v) => pad.t + (1 - Math.min(1, v / yMax)) * (h - pad.t - pad.b);

    let upTo, view;
    if (ts < 2.6) { upTo = 0; view = 320; }
    else if (ts < 8.2) { upTo = this._ease((ts - 2.6) / 5.6) * 320; view = 320; }
    else if (ts < 9.0) { upTo = 320; view = 320; }
    else if (ts < 15) { upTo = 320 + this._ease((ts - 9) / 6) * (TOT - 320); view = Math.min(TOT, Math.max(320, upTo * 1.12)); }
    else { upTo = TOT; view = TOT; }
    const pxS = (st) => pad.l + (st / view) * (w - pad.l - pad.r);

    ctx.strokeStyle = "rgba(150,176,182,0.5)"; ctx.setLineDash([6, 4]); ctx.lineWidth = 1.2;
    ctx.beginPath(); ctx.moveTo(pad.l, pyL(d.BASE)); ctx.lineTo(w - pad.r, pyL(d.BASE)); ctx.stroke(); ctx.setLineDash([]);
    ctx.fillStyle = "rgba(150,176,182,0.85)"; ctx.font = "11px 'IBM Plex Mono', monospace";
    ctx.fillText("base_lr = 1e-3", (ts >= 15 ? pxS(d.WS) : pad.l) + 8, pyL(d.BASE) - 6);

    if (view <= 1200) {
      const xw = pxS(d.WS);
      ctx.fillStyle = "rgba(255,207,107,0.06)";
      ctx.fillRect(pad.l, pad.t, xw - pad.l, h - pad.t - pad.b);
      ctx.strokeStyle = "rgba(255,207,107,0.4)"; ctx.setLineDash([4, 4]);
      ctx.beginPath(); ctx.moveTo(xw, pad.t); ctx.lineTo(xw, h - pad.b); ctx.stroke(); ctx.setLineDash([]);
      ctx.fillStyle = "rgba(255,207,107,0.85)";
      ctx.fillText("warmup_steps = 200", pad.l + 8, h - pad.b - 10);
    }

    if (ts >= 15) {
      const ra = this._ease((ts - 15) / 0.8);
      const xW = pxS(d.WS), xM = pxS(50 * d.SPE);
      ctx.save(); ctx.globalAlpha = ra;
      ctx.fillStyle = "rgba(255,207,107,0.10)"; ctx.fillRect(pad.l, pad.t, xW - pad.l, h - pad.t - pad.b);
      ctx.fillStyle = "rgba(53,230,208,0.06)";  ctx.fillRect(xW, pad.t, xM - xW, h - pad.t - pad.b);
      ctx.fillStyle = "rgba(124,255,155,0.045)"; ctx.fillRect(xM, pad.t, w - pad.r - xM, h - pad.t - pad.b);
      ctx.strokeStyle = "rgba(120,200,220,0.3)"; ctx.setLineDash([4, 4]); ctx.lineWidth = 1;
      ctx.beginPath(); ctx.moveTo(xW, pad.t); ctx.lineTo(xW, h - pad.b); ctx.stroke();
      ctx.beginPath(); ctx.moveTo(xM, pad.t); ctx.lineTo(xM, h - pad.b); ctx.stroke();
      ctx.setLineDash([]);
      ctx.font = "11px 'IBM Plex Mono', monospace";
      ctx.fillStyle = "rgba(255,207,107,0.9)";
      ctx.save(); ctx.translate(pad.l + (xW - pad.l) / 2 + 4, pad.t + 62); ctx.rotate(-Math.PI / 2); ctx.fillText("warmup", 0, 0); ctx.restore();
      ctx.fillStyle = "rgba(53,230,208,0.9)";
      let lb = "high lr  ·  coarse structure";
      ctx.fillText(lb, xW + (xM - xW) / 2 - ctx.measureText(lb).width / 2, pad.t + 14);
      ctx.fillStyle = "rgba(124,255,155,0.9)";
      lb = "low lr  ·  fine convergence";
      ctx.fillText(lb, xM + (w - pad.r - xM) / 2 - ctx.measureText(lb).width / 2, pad.t + 14);
      ctx.restore();
    }

    if (upTo > 0) {
      const N = 280;
      ctx.beginPath();
      for (let i = 0; i <= N; i++) {
        const st = (i / N) * upTo;
        const X = pxS(st), Y = pyL(d.lrAt(st));
        i ? ctx.lineTo(X, Y) : ctx.moveTo(X, Y);
      }
      ctx.strokeStyle = "#35e6d0"; ctx.lineWidth = 2.2; ctx.shadowColor = "rgba(53,230,208,0.5)"; ctx.shadowBlur = 7; ctx.stroke(); ctx.shadowBlur = 0;
      if (upTo < TOT) { ctx.fillStyle = "#7cff9b"; ctx.beginPath(); ctx.arc(pxS(upTo), pyL(d.lrAt(upTo)), 4.5, 0, 7); ctx.fill(); }
    }

    if (ts >= 2.6 && view <= 1200) {
      ctx.fillStyle = "#ffcf6b"; ctx.beginPath(); ctx.arc(pxS(0), pyL(d.BASE * 0.1), 4, 0, 7); ctx.fill();
    }
    if (upTo >= d.WS && view <= 1200) {
      ctx.fillStyle = "#7cff9b"; ctx.beginPath(); ctx.arc(pxS(d.WS), pyL(d.lrAt(d.WS)), 4.5, 0, 7); ctx.fill();
      ctx.font = "11px 'IBM Plex Mono', monospace";
      ctx.fillText("factor = 1.0", pxS(d.WS) + 10, pyL(d.lrAt(d.WS)) - 10);
    }

    let cap;
    if (ts < 2.6) cap = "Learning-rate schedule  ·  effective lr = base_lr x cosine(epoch) x warmup(step)  ·  two multiplicative factors";
    else if (ts < 5.4) cap = "Warmup ramp  ·  factor = 0.1 + 0.9 * step/200  ·  linear, ticked once per batch  ·  protects the first AdamW updates";
    else if (ts < 9.0) cap = "At step 200 warmup.is_finished()  ·  the factor locks at 1.0 and the epoch scheduler takes over";
    else if (ts < 15) cap = "Zoom out  ·  cosine annealing: lr = eta_min + (base - eta_min)(1 + cos(pi epoch/100))/2  ·  stepped once per epoch";
    else if (ts < 23.2) {
      if (!this._lrPace) {
        const NQ = 600, arr = [0];
        for (let i = 1; i <= NQ; i++) {
          const sq = (i / NQ) * (TOT - 1);
          arr.push(arr[i - 1] + 1 / Math.max(d.lrAt(sq), d.BASE * 0.15));
        }
        this._lrPace = arr;
      }
      const pace = this._lrPace, NQ = pace.length - 1;
      const q = Math.min(1, (ts - 15) / 8.0) * pace[NQ];
      let qlo = 0, qhi = NQ;
      while (qlo < qhi) { const m = (qlo + qhi) >> 1; if (pace[m] < q) qlo = m + 1; else qhi = m; }
      const st = (qlo / NQ) * (TOT - 1);
      const ep = Math.floor(st / d.SPE);
      const X = pxS(st), Y = pyL(d.lrAt(st));
      ctx.fillStyle = "#7cff9b"; ctx.beginPath(); ctx.arc(X, Y, 5.5, 0, 7); ctx.fill();
      ctx.strokeStyle = "rgba(124,255,155,0.5)"; ctx.lineWidth = 1.4;
      ctx.beginPath(); ctx.arc(X, Y, 10 + Math.sin(this.t * 5) * 1.5, 0, 7); ctx.stroke();
      ctx.font = "12px 'IBM Plex Mono', monospace"; ctx.fillStyle = "#7cff9b";
      ctx.fillText(`epoch ${ep}  ·  lr ${d.lrAt(st).toExponential(1)}`, Math.min(X + 16, w - pad.r - 190), Math.max(pad.t + 16, Y - 16));
      const zone = ep < 5 ? "warmup: stabilising the first updates" : ep < 50 ? "high-lr half: big steps, coarse structure" : "low-lr half: small steps, fine detail";
      cap = `The dot moves at the speed of the lr  ·  epoch ${ep}/100  ·  ${zone}`;
    } else {
      const yE = pyL(d.ETA);
      ctx.strokeStyle = "rgba(255,207,107,0.55)"; ctx.setLineDash([6, 4]); ctx.lineWidth = 1.2;
      ctx.beginPath(); ctx.moveTo(pad.l, yE); ctx.lineTo(w - pad.r, yE); ctx.stroke(); ctx.setLineDash([]);
      ctx.fillStyle = "rgba(255,207,107,0.9)"; ctx.font = "11px 'IBM Plex Mono', monospace";
      ctx.fillText("eta_min = 1e-6", w - pad.r - 108, yE - 8);
      cap = "Anneals to eta_min = 1e-6 over T_max = 100 epochs  ·  the best epoch's weights are saved to the checkpoint";
    }

    if (ts >= 2.8 && ts < 8.4) {
      const fa = this._ease(Math.min(1, (ts - 2.8) / 0.6)) * (1 - this._ease(Math.min(1, Math.max(0, (ts - 7.6) / 0.8))));
      this._texDraw("\\text{factor}=0.1+0.9\\,\\tfrac{t}{200}", w / 2, pad.t + 4, 15, { align: "center", alpha: fa, color: "rgba(255,207,107,0.95)" });
    }
    if (ts >= 9.2 && ts < 14.8) {
      const ca = this._ease(Math.min(1, (ts - 9.2) / 0.7)) * (1 - this._ease(Math.min(1, Math.max(0, (ts - 13.8) / 0.9))));
      this._texDraw("\\eta_t=\\eta_{\\min}+\\tfrac{1}{2}(\\eta_0-\\eta_{\\min})\\left(1+\\cos\\tfrac{\\pi t}{T}\\right)", w / 2, pad.t + 4, 15, { align: "center", alpha: ca, color: "rgba(53,230,208,0.95)" });
    }
    this._cap(cap);
  }

  _trClip(ts, d) {
    const { ctx, w, h } = this;
    this._trTag("GRADIENT CLIPPER");
    const pad = { l: 52, r: 16, t: 18, b: 30 };
    this._axes(pad, "optimizer step", "|g|");
    const yMax = 3.4;
    const pyN = (v) => pad.t + (1 - Math.min(1, v / yMax)) * (h - pad.t - pad.b);

    const WIN = 72, RATE = 13, F0 = 6.4, F1 = 13.2;
    let head;
    if (ts < F0) head = ts * RATE;
    else if (ts < F1) head = F0 * RATE;
    else head = F0 * RATE + (ts - F1) * RATE;
    head = Math.min(head, d.norms.length - 1);
    const lo = Math.max(0, head - WIN);
    const pxN = (i) => pad.l + ((i - lo) / WIN) * (w - pad.l - pad.r);

    const thr = 1.0, demoI = 58, demoV = d.norms[demoI];
    const thrOn = ts >= 3.2;
    const clipActive = ts >= F1;

    if (thrOn) {
      const rev = this._ease((ts - 3.2) / 1.2);
      ctx.strokeStyle = "rgba(255,207,107,0.75)"; ctx.setLineDash([6, 4]); ctx.lineWidth = 1.4;
      ctx.beginPath(); ctx.moveTo(pad.l, pyN(thr)); ctx.lineTo(pad.l + rev * (w - pad.l - pad.r), pyN(thr)); ctx.stroke(); ctx.setLineDash([]);
      if (rev >= 1) {
        ctx.fillStyle = "rgba(255,207,107,0.9)"; ctx.font = "11px 'IBM Plex Mono', monospace";
        ctx.fillText("max_grad_norm = 1.0", w - pad.r - 136, pyN(thr) - 7);
      }
    }

    for (let i = Math.ceil(lo); i <= Math.floor(head); i++) {
      let v = d.norms[i], ghost = null;
      if (i === demoI && ts >= 8.2) {
        const p = this._ease(Math.min(1, (ts - 8.2) / 1.6));
        ghost = demoV; v = this._lerp(demoV, thr, p);
      } else if (clipActive && v > thr) {
        ghost = v; v = thr;
      }
      const X = pxN(i);
      if (ghost != null && ghost > v + 1e-6) {
        ctx.strokeStyle = "rgba(255,107,125,0.5)"; ctx.setLineDash([3, 3]); ctx.lineWidth = 1.2;
        ctx.beginPath(); ctx.moveTo(X, pyN(v)); ctx.lineTo(X, pyN(ghost)); ctx.stroke(); ctx.setLineDash([]);
        ctx.fillStyle = "rgba(255,107,125,0.7)";
        ctx.beginPath(); ctx.arc(X, pyN(ghost), 2.5, 0, 7); ctx.fill();
      }
      const clipped = ghost != null && v <= thr + 1e-3;
      const hot = thrOn && v > thr + 1e-3;
      ctx.strokeStyle = clipped ? "rgba(124,255,155,0.8)" : "rgba(53,230,208,0.5)";
      ctx.lineWidth = 2;
      ctx.beginPath(); ctx.moveTo(X, pyN(0)); ctx.lineTo(X, pyN(v)); ctx.stroke();
      ctx.fillStyle = hot ? "#ff6b7d" : clipped ? "#7cff9b" : "#35e6d0";
      ctx.beginPath(); ctx.arc(X, pyN(v), 2.6, 0, 7); ctx.fill();
    }

    if (ts >= F0 && ts < F1) {
      const p = ts < 8.2 ? 0 : this._ease(Math.min(1, (ts - 8.2) / 1.6));
      const vNow = this._lerp(demoV, thr, p);
      const X = pxN(demoI);
      ctx.strokeStyle = "rgba(255,207,107,0.9)"; ctx.lineWidth = 1.6;
      ctx.beginPath(); ctx.arc(X, pyN(vNow), 9 + Math.sin(this.t * 5) * 1.5, 0, 7); ctx.stroke();
      ctx.font = "12px 'IBM Plex Mono', monospace";
      if (ts < 8.2) {
        ctx.fillStyle = "#ff6b7d";
        ctx.fillText(`|g| = ${demoV.toFixed(2)} > 1.0`, X + 14, pyN(demoV) - 4);
      } else {
        ctx.fillStyle = "#ffcf6b";
        ctx.fillText(`1.0 / (${demoV.toFixed(2)} + 1e-6) = ${(thr / demoV).toFixed(2)}  (example)`, Math.min(X + 14, w - 250), pyN(demoV) - 4);
        if (p >= 1) {
          ctx.fillStyle = "#7cff9b";
          ctx.fillText("norm_after = 1.00", X + 14, pyN(thr) + 20);
        }
      }
    }

    if (ts >= 4.4) {
      const ha = this._ease(Math.min(1, (ts - 4.4) / 0.8));
      this._texDraw("g\\leftarrow g\\cdot\\min\\!\\left(1,\\;\\frac{c}{\\lVert g\\rVert_2+\\epsilon}\\right)", w / 2, pad.t + 2, 15, { align: "center", alpha: ha, color: "rgba(255,207,107,0.95)" });
    }

    if (ts < 3.2) this._cap("Gradient clipper  ·  right after backward, on the boundary batch  ·  global L2 norm over every parameter gradient");
    else if (ts < F0) this._cap("clip_mode = fixed  ·  threshold max_grad_norm = 1.0  ·  norms above 100 raise an exploding-gradient warning");
    else if (ts < 8.2) this._cap(`A spike lands  ·  |g| = ${demoV.toFixed(2)} exceeds the threshold  ·  unchecked it would wreck the update`);
    else if (ts < 10.4) this._cap("Every grad tensor is multiplied in-place by the scale  ·  direction preserved, magnitude capped");
    else if (ts < F1) this._cap("norm_before, norm_after, clip_ratio, threshold  ->  logged to the tracker every optimizer step");
    else this._cap("Stream continues  ·  spikes ride the fixed threshold, healthy steps pass untouched  ·  adaptive modes (p95 / mean+2sd of a 200-step window) also exist");
  }

  _trCurr(ts, d) {
    const { ctx, w, h } = this;
    this._trTag("LOSS CURRICULUM");
    const panW = 196;
    const pad = { l: 52, r: panW + 30, t: 18, b: 30 };
    const padL = { l: 52, r: 16, t: 18, b: 30 };
    const pxE = (e) => pad.l + (e / 100) * (w - pad.l - pad.r);
    const pyV = (v) => pad.t + (1 - Math.min(1, v / 0.85)) * (h - pad.t - pad.b);

    const Z0 = 11.6, ZOUT0 = 20.6;
    let zp = 0;
    if (ts >= Z0 && ts < ZOUT0) zp = this._ease(Math.min(1, (ts - Z0) / 1.0));
    else if (ts >= ZOUT0) zp = 1 - this._ease(Math.min(1, (ts - ZOUT0) / 1.0));

    let eUp;
    if (ts < 3.8) eUp = this._ease(ts / 3.8) * 49.5;
    else if (ts < 21.6) eUp = 49.9;
    else eUp = 50 + this._ease((ts - 21.6) / 4.6) * 50;

    const bandL = pxE(42), bandR = pxE(62);
    const fOf = (e) => e < 50 ? d.cosF(e) : d.cosF(e - 50) * Math.min(1, 0.1 + 0.9 * (e - 50) / 5);

    if (zp < 1) {
      ctx.save();
      ctx.globalAlpha = 1 - zp;

      this._axes(pad, "epoch", "loss");

      if (ts >= 3.8) {
        const X = pxE(50);
        ctx.strokeStyle = "rgba(255,207,107,0.7)"; ctx.setLineDash([6, 4]); ctx.lineWidth = 1.4;
        ctx.beginPath(); ctx.moveTo(X, pad.t); ctx.lineTo(X, h - pad.b); ctx.stroke(); ctx.setLineDash([]);
        ctx.fillStyle = "rgba(255,207,107,0.9)"; ctx.font = "11px 'IBM Plex Mono', monospace";
        ctx.fillText("swap_epoch = 50", X + 8, pad.t + 14);
        ctx.fillStyle = "#5e7280";
        ctx.fillText("(example)", X + 8, pad.t + 28);
      }

      const NL = 300;
      ctx.beginPath();
      let started = false;
      for (let i = 0; i <= NL; i++) {
        const e = (i / NL) * 100;
        if (e > eUp) break;
        const X = pxE(e), Y = pyV(d.lossAt(e));
        started ? ctx.lineTo(X, Y) : ctx.moveTo(X, Y); started = true;
      }
      ctx.strokeStyle = "#35e6d0"; ctx.lineWidth = 2.2; ctx.shadowColor = "rgba(53,230,208,0.5)"; ctx.shadowBlur = 7; ctx.stroke(); ctx.shadowBlur = 0;
      const eTip = Math.min(eUp, 100);
      ctx.fillStyle = "#7cff9b"; ctx.beginPath(); ctx.arc(pxE(eTip), pyV(d.lossAt(eTip)), 4, 0, 7); ctx.fill();
      ctx.restore();
    }

    if (ts >= 10.8 && zp < 1 && ts < ZOUT0) {
      const ba = Math.min(1, (ts - 10.8) / 0.5);
      const rxA = this._lerp(bandL, padL.l, zp);
      const rxB = this._lerp(bandR, w - padL.r, zp);
      ctx.save(); ctx.globalAlpha = ba * (1 - zp * 0.5);
      ctx.strokeStyle = "#ffcf6b"; ctx.setLineDash([7, 5]); ctx.lineWidth = 1.6;
      ctx.strokeRect(rxA, pad.t + 4, rxB - rxA, h - pad.t - pad.b - 8);
      ctx.setLineDash([]);
      ctx.fillStyle = "#ffcf6b"; ctx.font = "11px 'IBM Plex Mono', monospace";
      ctx.fillText("zoom", rxA + 6, pad.t + 20);
      ctx.restore();
    }

    if (zp < 1) {
      ctx.save();
      ctx.globalAlpha = 1 - zp;

      const terms = [
        { name: "param_l1",         w: "1.0", p1: true,  p2: true },
        { name: "mse_curve",        w: "1.0", p1: false, p2: true },
        { name: "cosine_curve",     w: "0.5", p1: false, p2: true },
        { name: "covariance_match", w: "0.0", p1: false, p2: false },
        { name: "moments",          w: "0.0", p1: false, p2: false },
      ];
      const swapP = ts < 6.6 ? 0 : this._ease(Math.min(1, (ts - 6.6) / 1.6));
      const bx = w - panW - 16, by = 30, rh = 31;
      ctx.fillStyle = "rgba(4,7,10,0.86)"; ctx.fillRect(bx - 10, by - 20, panW + 18, terms.length * rh + 48);
      ctx.strokeStyle = "rgba(120,200,220,0.28)"; ctx.strokeRect(bx - 10, by - 20, panW + 18, terms.length * rh + 48);
      ctx.fillStyle = "rgba(143,176,170,0.95)"; ctx.font = "11px 'IBM Plex Mono', monospace";
      ctx.fillText(swapP < 0.5 ? "loss = curriculum.warmup" : "loss = curriculum.complete", bx, by - 6);
      terms.forEach((t2, i) => {
        const act = this._lerp(t2.p1 ? 1 : 0, t2.p2 ? 1 : 0, swapP);
        const y = by + 4 + i * rh;
        ctx.save();
        ctx.globalAlpha = (0.4 + 0.6 * act) * (1 - zp);
        ctx.fillStyle = "rgba(7,12,17,0.96)";
        ctx.strokeStyle = act > 0.5 ? "#35e6d0" : "rgba(124,160,176,0.4)";
        ctx.lineWidth = 1.3;
        ctx.beginPath();
        if (ctx.roundRect) ctx.roundRect(bx, y, panW - 4, rh - 7, 5); else ctx.rect(bx, y, panW - 4, rh - 7);
        ctx.fill(); ctx.stroke();
        ctx.font = "12px 'IBM Plex Mono', monospace";
        ctx.fillStyle = act > 0.5 ? "rgba(230,247,243,0.95)" : "rgba(124,160,176,0.55)";
        ctx.fillText(t2.name, bx + 9, y + 16);
        const tag = act > 0.5 ? "a=" + t2.w : "off";
        ctx.fillStyle = act > 0.5 ? "#7cff9b" : "rgba(124,160,176,0.55)";
        ctx.fillText(tag, bx + panW - 13 - ctx.measureText(tag).width, y + 16);
        ctx.restore();
      });
      ctx.font = "11px 'IBM Plex Mono', monospace";
      ctx.fillStyle = swapP < 0.5 ? "rgba(143,176,170,0.75)" : "rgba(124,255,155,0.85)";
      ctx.fillText("matcher: sort_gt_by_mu", bx, by + 4 + terms.length * rh + 11);

      {
        const a1 = Math.min(1, Math.max(0, (ts - 0.6) / 0.6));
        if (a1 > 0) {
          const fy = h - pad.b - 24;
          const fx = pad.l + 14;
          const tex = this._tex("\\mathcal{L}=w_a\\mathcal{L}_a+w_{\\mu}\\mathcal{L}_{\\mu}+w_{\\sigma}\\mathcal{L}_{\\sigma}", 15, "rgba(230,247,243,0.95)");
          const ea = a1 * (1 - zp);
          if (tex.ready) {
            ctx.save(); ctx.globalAlpha = ea;
            ctx.fillStyle = "rgba(4,7,10,0.88)";
            ctx.fillRect(fx - 8, fy - tex.h - 4, tex.w + 60, tex.h + 12);
            ctx.restore();
            this._texDraw("\\mathcal{L}=w_a\\mathcal{L}_a+w_{\\mu}\\mathcal{L}_{\\mu}+w_{\\sigma}\\mathcal{L}_{\\sigma}", fx, fy - tex.h, 15, { alpha: ea, color: "rgba(230,247,243,0.95)" });
            ctx.save(); ctx.globalAlpha = ea;
            ctx.font = "11px 'IBM Plex Mono', monospace"; ctx.fillStyle = "#5e7280";
            ctx.fillText("(example)", fx + tex.w + 8, fy - 3);
            ctx.restore();
          }
        }
      }

      if (ts >= 9.4 && ts < ZOUT0) {
        const items = [
          "early_stopping.reset()",
          "lr_scheduler.reset(offset = 50)",
          "warmup.reset()  ·  re-armed",
          "Adam moments cleared",
          "checkpoint baseline reset",
        ];
        const x0 = pad.l + 14, y0 = pad.t + 26;
        ctx.font = "11px 'IBM Plex Mono', monospace";
        ctx.fillStyle = "rgba(4,7,10,0.8)";
        ctx.fillRect(x0 - 8, y0 - 16, 246, items.length * 18 + 12);
        items.forEach((s, i) => {
          const a = Math.min(1, Math.max(0, (ts - 9.4 - i * 0.35) / 0.4));
          if (a <= 0) return;
          ctx.save(); ctx.globalAlpha = a * (1 - zp);
          ctx.fillStyle = "#7cff9b"; ctx.fillText("✓", x0, y0 + i * 18);
          ctx.fillStyle = "rgba(230,247,243,0.9)"; ctx.fillText(s, x0 + 16, y0 + i * 18);
          ctx.restore();
        });
      }
      ctx.restore();
    }

    if (zp > 0) {
      ctx.save();
      ctx.globalAlpha = zp;

      this._axes(padL, "epoch", "lr factor");
      const e0 = 42, e1 = 62;
      const zx = (e) => padL.l + ((e - e0) / (e1 - e0)) * (w - padL.l - padL.r);
      const zy = (f) => padL.t + (1 - Math.min(1, f / 1.1)) * (h - padL.t - padL.b);

      ctx.font = "11px 'IBM Plex Mono', monospace";
      for (let e = 45; e <= 60; e += 5) {
        ctx.strokeStyle = "rgba(120,200,220,0.10)"; ctx.lineWidth = 1;
        ctx.beginPath(); ctx.moveTo(zx(e), padL.t); ctx.lineTo(zx(e), h - padL.b); ctx.stroke();
        ctx.fillStyle = "rgba(143,176,170,0.6)";
        ctx.fillText(String(e), zx(e) - 7, h - padL.b + 14);
      }
      ctx.strokeStyle = "rgba(120,200,220,0.2)"; ctx.setLineDash([4, 4]); ctx.lineWidth = 1;
      ctx.beginPath(); ctx.moveTo(padL.l, zy(1)); ctx.lineTo(w - padL.r, zy(1)); ctx.stroke();
      ctx.beginPath(); ctx.moveTo(padL.l, zy(0.1)); ctx.lineTo(w - padL.r, zy(0.1)); ctx.stroke();
      ctx.setLineDash([]);
      ctx.fillStyle = "rgba(143,176,170,0.8)";
      ctx.fillText("1.0", padL.l - 30, zy(1) + 4);
      ctx.fillText("0.1", padL.l - 30, zy(0.1) + 4);

      const tsLR = ts - (Z0 + 1.0);
      const preP  = this._ease(Math.min(1, Math.max(0, tsLR / 1.6)));
      const dropP = this._ease(Math.min(1, Math.max(0, (tsLR - 2.6) / 1.0)));
      const postP = this._ease(Math.min(1, Math.max(0, (tsLR - 4.4) / 2.6)));
      const ePre  = this._lerp(e0, 49.99, preP);
      const ePost = this._lerp(50, e1, postP);

      if (preP > 0) {
        ctx.beginPath();
        for (let i = 0; i <= 100; i++) {
          const e = this._lerp(e0, ePre, i / 100);
          const X = zx(e), Y = zy(fOf(e));
          i ? ctx.lineTo(X, Y) : ctx.moveTo(X, Y);
        }
        ctx.strokeStyle = "#35e6d0"; ctx.lineWidth = 2.4; ctx.shadowColor = "rgba(53,230,208,0.5)"; ctx.shadowBlur = 7; ctx.stroke(); ctx.shadowBlur = 0;
      }
      if (dropP > 0) {
        ctx.strokeStyle = "rgba(255,207,107,0.85)"; ctx.setLineDash([6, 5]); ctx.lineWidth = 1.5;
        ctx.beginPath(); ctx.moveTo(zx(50), padL.t); ctx.lineTo(zx(50), h - padL.b); ctx.stroke(); ctx.setLineDash([]);
        ctx.fillStyle = "#ffcf6b"; ctx.font = "12px 'IBM Plex Mono', monospace";
        ctx.fillText("lr_scheduler.reset(epoch_offset = 50)", padL.l + 14, padL.t + 40);
        ctx.font = "11px 'IBM Plex Mono', monospace";
        ctx.strokeStyle = "rgba(255,107,125,0.9)"; ctx.lineWidth = 2.4;
        ctx.beginPath(); ctx.moveTo(zx(50), zy(fOf(49.99))); ctx.lineTo(zx(50), zy(this._lerp(fOf(49.99), 0.1, dropP))); ctx.stroke();
        if (dropP >= 1) {
          ctx.fillStyle = "#ff6b7d"; ctx.font = "12px 'IBM Plex Mono', monospace";
          const dtxt = "factor -> 0.1";
          ctx.fillText(dtxt, zx(50) - 12 - ctx.measureText(dtxt).width, zy(0.13));
          ctx.font = "11px 'IBM Plex Mono', monospace";
        }
      }

      if (postP > 0) {
        ctx.beginPath();
        for (let i = 0; i <= 100; i++) {
          const e = this._lerp(50, ePost, i / 100);
          const X = zx(e), Y = zy(fOf(e));
          i ? ctx.lineTo(X, Y) : ctx.moveTo(X, Y);
        }
        ctx.strokeStyle = "#7cff9b"; ctx.lineWidth = 2.4; ctx.shadowColor = "rgba(124,255,155,0.45)"; ctx.shadowBlur = 7; ctx.stroke(); ctx.shadowBlur = 0;
        if (ePost >= 55) {
          ctx.fillStyle = "rgba(124,255,155,0.9)";
          ctx.fillText("warmup re-ramp: 200 steps", zx(52.3), zy(0.48));
        }
        if (ePost >= 60) {
          ctx.fillStyle = "rgba(124,255,155,0.9)";
          ctx.fillText("fresh cosine", zx(56.5), zy(1) + 18);
        }
      }

      if (preP > 0) {
        let penE = ePre, penF = fOf(ePre);
        if (postP > 0) { penE = ePost; penF = fOf(ePost); }
        else if (dropP > 0) { penE = 50; penF = this._lerp(fOf(49.99), 0.1, dropP); }
        ctx.fillStyle = postP > 0 ? "#7cff9b" : "#35e6d0";
        ctx.beginPath(); ctx.arc(zx(penE), zy(penF), 5, 0, 7); ctx.fill();
      }

      ctx.restore();
    }

    if (ts < 3.8) this._cap("Loss curriculum  ·  phase 1: param_l1 on matched [a, mu, sigma] sets  ·  direct parameter supervision");
    else if (ts < 6.6) this._cap("epoch == swap_epoch  ->  CurriculumController.maybe_swap() fires");
    else if (ts < 9.4) this._cap("criterion.set_curriculum(complete)  ·  param_l1 stays in the formula  ·  mse_curve and cosine_curve join it");
    else if (ts < 10.8) this._cap("Resets cascade  ·  early stopping, lr scheduler, warmup, optimizer moments, checkpoint baseline (new loss scale)");
    else if (ts < 12.6) this._cap("Zooming into the learning-rate schedule around the swap epoch");
    else if (ts < 15.2) this._cap("The cosine glides down toward epoch 50  ·  by the swap it sits at 0.5 x base");
    else if (ts < 17.0) this._cap("reset(epoch_offset = 50) rewinds the clock  ·  warmup re-arms at factor 0.1, so lr jumps to 0.1 x base (not 0.1 x the pre-swap lr)");
    else if (ts < 20.6) this._cap("It re-ramps over 200 steps — about 5 epochs at this demo's batch count — then a fresh cosine anneals the complete objective");
    else if (ts < 21.6) this._cap("Zoom back out  ·  training continues under the new loss");
    else this._cap("A small bump only — the weighted sum is normalised by the weights  ·  then it settles below the phase-1 floor");
  }

  _trMatch(ts, d) {
    const { ctx, w, h } = this;
    this._trTag("PARAM ORDERING");
    const slots = [
      { a: 0.55, mu: 9,  s: 2.1 },
      { a: 0.90, mu: 2,  s: 1.6 },
      { a: 0,    mu: 0,  s: 0   },
      { a: 0.40, mu: 18, s: 1.2 },
    ];
    const dest = [1, 0, 3, 2];
    const preds = [
      { a: 0.86, mu: 2.4,  s: 1.5 },
      { a: 0.51, mu: 8.5,  s: 2.3 },
      { a: 0.37, mu: 17.4, s: 1.4 },
      { a: 0.03, mu: 11.2, s: 3.0 },
    ];

    const K = 4, gap = 16;
    const cw = Math.min(150, (w - 90 - (K - 1) * gap) / K);
    const chh = 64;
    const rowX = (j) => (w - (K * cw + (K - 1) * gap)) / 2 + j * (cw + gap);
    const yGt = Math.round(h * 0.10), yPr = Math.round(h * 0.52);

    const card = (x, y, lines, dim, tag, alpha) => {
      ctx.save();
      ctx.globalAlpha = alpha == null ? 1 : alpha;
      ctx.fillStyle = "rgba(7,12,17,0.96)";
      ctx.strokeStyle = dim ? "rgba(124,160,176,0.4)" : "#35e6d0";
      ctx.lineWidth = 1.4;
      ctx.beginPath();
      if (ctx.roundRect) ctx.roundRect(x, y, cw, chh, 8); else ctx.rect(x, y, cw, chh);
      ctx.fill(); ctx.stroke();
      ctx.font = "12px 'IBM Plex Mono', monospace";
      lines.forEach((ln, i2) => {
        ctx.fillStyle = dim ? "rgba(124,160,176,0.55)" : "rgba(230,247,243,0.95)";
        ctx.fillText(ln, x + 11, y + 19 + i2 * 16);
      });
      if (tag) { ctx.fillStyle = "#7cff9b"; ctx.fillText(tag, x + cw - 27, y + 16); }
      ctx.restore();
    };

    const appear = (i) => Math.min(1, Math.max(0, (ts - 0.4 - i * 0.35) / 0.6));
    const sortP = this._ease(Math.min(1, Math.max(0, (ts - 4.5) / 2.0)));
    const prA = Math.min(1, Math.max(0, (ts - 7.0) / 0.9));

    ctx.font = "11px 'IBM Plex Mono', monospace";
    ctx.fillStyle = "rgba(143,176,170,0.9)";
    ctx.fillText(sortP >= 1 ? "gt sorted  ·  mu ascending, inactive last" : "gt gaussians  ·  slot order as stored", rowX(0), yGt - 12);

    slots.forEach((s2, i) => {
      const x = this._lerp(rowX(i), rowX(dest[i]), sortP);
      const active = s2.a > 1e-3;
      const lines = active
        ? [`a  = ${s2.a.toFixed(2)}`, `mu = ${s2.mu.toFixed(1)} m`, `s  = ${s2.s.toFixed(1)} m`]
        : ["a  = 0", "mu = -", "s  = -"];
      card(x, yGt, lines, !active, null, appear(i));
      if (ts >= 2.2 && ts < 7.0) {
        const ka = Math.min(1, Math.max(0, (ts - 2.2 - i * 0.3) / 0.5));
        if (ka > 0) {
          ctx.save(); ctx.globalAlpha = ka;
          ctx.fillStyle = active ? "#ffcf6b" : "#ff6b7d";
          ctx.font = "11px 'IBM Plex Mono', monospace";
          ctx.fillText(active ? `key = ${s2.mu.toFixed(1)}` : "key = inf", x + 8, yGt + chh + 16);
          ctx.restore();
        }
      }
    });

    if (prA > 0) {
      ctx.save(); ctx.globalAlpha = prA;
      ctx.fillStyle = "rgba(143,176,170,0.9)"; ctx.font = "11px 'IBM Plex Mono', monospace";
      ctx.fillText("model output slots  ·  fixed order", rowX(0), yPr + chh + 18);
      ctx.restore();
      preds.forEach((p, j) => {
        const lines = [`a  = ${p.a.toFixed(2)}`, `mu = ${p.mu.toFixed(1)} m`, `s  = ${p.s.toFixed(1)} m`];
        card(rowX(j), yPr, lines, j === 3, "#" + (j + 1), prA);
      });
    }

    if (ts >= 7.6) {
      for (let j = 0; j < 3; j++) {
        const la = Math.min(1, Math.max(0, (ts - 7.6 - j * 0.3) / 0.5));
        if (la <= 0) continue;
        const x = rowX(j) + cw / 2;
        ctx.save(); ctx.globalAlpha = la;
        ctx.strokeStyle = "rgba(124,255,155,0.7)"; ctx.fillStyle = "#7cff9b";
        ctx.setLineDash([4, 3]); ctx.lineWidth = 1.4;
        ctx.beginPath(); ctx.moveTo(x, yGt + chh + 6); ctx.lineTo(x, yPr - 20); ctx.stroke(); ctx.setLineDash([]);
        ctx.beginPath();
        ctx.moveTo(x, yPr - 8); ctx.lineTo(x - 4, yPr - 16); ctx.lineTo(x + 4, yPr - 16);
        ctx.closePath(); ctx.fill();
        ctx.font = "11px 'IBM Plex Mono', monospace";
        ctx.fillText("l1", x + 6, (yGt + chh + yPr - 18) / 2 + 4);
        ctx.restore();
      }
    }

    if (ts >= 9.6) {
      const ma = Math.min(1, (ts - 9.6) / 0.6);
      const bx4 = rowX(3);
      ctx.save(); ctx.globalAlpha = ma;
      ctx.strokeStyle = "#ffcf6b"; ctx.lineWidth = 1.3;
      ctx.strokeRect(bx4 + 6, yGt + 7, cw - 12, 17);
      ctx.fillStyle = "#ffcf6b"; ctx.font = "11px 'IBM Plex Mono', monospace";
      ctx.fillText("inactive: amp <= amp_zero_thr", bx4 - 48, yGt - 8);

      const sa = Math.min(1, Math.max(0, (ts - 10.4) / 0.6));
      if (sa > 0) {
        ctx.save(); ctx.globalAlpha = ma * sa;

        const xe4 = bx4 + cw;
        const links = [
          { row: 0, off: 8,  c: "#7cff9b", masked: false, lbl: "l1" },
          { row: 1, off: 20, c: "#ff6b7d", masked: true,  lbl: "masked" },
          { row: 2, off: 32, c: "#ff6b7d", masked: true,  lbl: "masked" },
        ];
        links.forEach((lk, li) => {
          const lp = Math.min(1, Math.max(0, (ts - 10.5 - li * 0.35) / 0.4));
          if (lp <= 0) return;
          const yA = yGt + 14 + lk.row * 16;
          const yB = yPr + 14 + lk.row * 16;
          const xb = xe4 + lk.off;
          ctx.save(); ctx.globalAlpha = ma * sa * lp;
          ctx.strokeStyle = lk.c; ctx.fillStyle = lk.c; ctx.lineWidth = lk.masked ? 1.5 : 1.7;
          if (!lk.masked) ctx.setLineDash([4, 3]);
          ctx.beginPath();
          ctx.moveTo(xe4, yA); ctx.lineTo(xb, yA);
          ctx.lineTo(xb, yB); ctx.lineTo(xe4 + 6, yB);
          ctx.stroke(); ctx.setLineDash([]);
          ctx.beginPath();
          ctx.moveTo(xe4, yB); ctx.lineTo(xe4 + 7, yB - 4); ctx.lineTo(xe4 + 7, yB + 4);
          ctx.closePath(); ctx.fill();
          if (lk.masked) {
            const my = (yA + yB) / 2;
            ctx.lineWidth = 1.8;
            ctx.beginPath(); ctx.moveTo(xb - 5, my - 5); ctx.lineTo(xb + 5, my + 5); ctx.stroke();
            ctx.beginPath(); ctx.moveTo(xb - 5, my + 5); ctx.lineTo(xb + 5, my - 5); ctx.stroke();
          }
          ctx.restore();
        });

        const la2 = Math.min(1, Math.max(0, (ts - 11.6) / 0.5));
        if (la2 > 0) {
          ctx.save(); ctx.globalAlpha = ma * la2;
          ctx.font = "11px 'IBM Plex Mono', monospace";
          const midY = (yGt + yPr) / 2;
          ctx.fillStyle = "#7cff9b";
          ctx.fillText("l1", xe4 + 42, midY + 18);
          ctx.fillStyle = "#ff6b7d";
          ctx.fillText("masked", xe4 + 42, midY + 34);
          ctx.fillText("masked", xe4 + 42, midY + 50);
          ctx.restore();
        }

        for (let ri = 1; ri <= 2; ri++) {
          const sy = yPr + 15 + ri * 16;
          ctx.strokeStyle = "rgba(255,107,125,0.9)"; ctx.lineWidth = 1.6;
          ctx.beginPath(); ctx.moveTo(bx4 + 9, sy); ctx.lineTo(bx4 + cw - 32, sy); ctx.stroke();
        }
        ctx.restore();
      }
      ctx.restore();
    }

    if (ts >= 13) {
      const fa = Math.min(1, (ts - 13) / 0.8);
      const axL = rowX(0) + 10, axR = rowX(3) + cw - 10;
      const yAx = Math.round(h * 0.90);
      const AMP = 52;
      const xMu = (mu) => axL + (mu / 20) * (axR - axL);
      const prof = (mu) => preds.slice(0, 3).reduce((v, p) => v + p.a * Math.exp(-((mu - p.mu) ** 2) / (2 * (p.s * 0.7) ** 2)), 0);
      ctx.save(); ctx.globalAlpha = fa;
      ctx.strokeStyle = "rgba(143,176,170,0.6)"; ctx.lineWidth = 1.2;
      ctx.beginPath(); ctx.moveTo(axL, yAx); ctx.lineTo(axR, yAx); ctx.stroke();
      ctx.fillStyle = "rgba(143,176,170,0.85)"; ctx.font = "11px 'IBM Plex Mono', monospace";
      ctx.fillText("mu ->", axR + 8, yAx + 4);
      ctx.beginPath();
      for (let i = 0; i <= 160; i++) {
        const mu = (i / 160) * 20;
        const X = xMu(mu), Y = yAx - prof(mu) * AMP;
        i ? ctx.lineTo(X, Y) : ctx.moveTo(X, Y);
      }
      ctx.lineTo(axR, yAx); ctx.lineTo(axL, yAx); ctx.closePath();
      ctx.fillStyle = "rgba(53,230,208,0.08)"; ctx.fill();
      ctx.beginPath();
      for (let i = 0; i <= 160; i++) {
        const mu = (i / 160) * 20;
        const X = xMu(mu), Y = yAx - prof(mu) * AMP;
        i ? ctx.lineTo(X, Y) : ctx.moveTo(X, Y);
      }
      ctx.strokeStyle = "#35e6d0"; ctx.lineWidth = 1.8; ctx.stroke();
      const layers = ["ground", "volume", "canopy"];
      preds.slice(0, 3).forEach((p, j) => {
        const aa = Math.min(1, Math.max(0, (ts - 13.4 - j * 0.5) / 0.5));
        if (aa <= 0) return;
        const yPk = yAx - prof(p.mu) * AMP;
        ctx.save(); ctx.globalAlpha = aa * fa;
        ctx.strokeStyle = "rgba(124,255,155,0.7)"; ctx.lineWidth = 1.3;
        ctx.beginPath(); ctx.moveTo(rowX(j) + cw / 2, yPr + chh + 4); ctx.lineTo(xMu(p.mu), yPk - 7); ctx.stroke();
        ctx.fillStyle = "#7cff9b";
        ctx.beginPath(); ctx.arc(xMu(p.mu), yPk, 3.5, 0, 7); ctx.fill();
        ctx.font = "11px 'IBM Plex Mono', monospace";
        ctx.fillText("#" + (j + 1), xMu(p.mu) + 8, yPk + 4);
        ctx.fillText(layers[j], xMu(p.mu) - ctx.measureText(layers[j]).width / 2, yAx + 16);
        ctx.restore();
      });
      ctx.restore();
    }

    if (ts < 2.2) this._cap("ParamMatcher  ·  strategy = sort_gt_by_mu  ·  gt gaussians arrive in arbitrary slot order");
    else if (ts < 4.5) this._cap("sort key = mu where amp > 1e-3, else inf  ·  inactive slots sink to the end");
    else if (ts < 7.0) this._cap("torch.argsort + gather along the gaussian axis  ·  gt in mu-ascending order, every pixel, every batch");
    else if (ts < 9.6) this._cap("Param loss is slot-by-slot  ·  pred slot k is always graded against the k-th lowest scatterer");
    else if (ts < 13) this._cap("gt amp = 0 gates the slot: mu and sigma drop out of the loss  ·  the a term IS still graded, pulling pred a -> 0");
    else this._cap("The fixed target order induces ordered predictions  ·  each output channel specialises in one height layer");
  }

  _trReg(ts, d) {
    const { ctx, w, h } = this;
    this._trTag("WEIGHT DECAY");
    const pad = { l: 52, r: 16, t: 18, b: 30 };
    this._axes(pad, "epoch", "loss");
    const ux = (q) => pad.l + q * (w - pad.l - pad.r);
    const uy = (v) => pad.t + (1 - Math.min(1, v / 0.95)) * (h - pad.t - pad.b);

    const trF = (q) => 0.10 + 0.62 * Math.exp(-q * 5.5) + 0.012 * Math.sin(q * 40);
    const vaBad = (q) => 0.16 + 0.66 * Math.exp(-q * 5) + 1.05 * Math.pow(Math.max(0, q - 0.30), 1.35) + 0.010 * Math.sin(q * 31);
    const vaGood = (q) => 0.175 + 0.62 * Math.exp(-q * 4.6) + 0.045 * q + 0.010 * Math.sin(q * 27 + 1);

    const draw = (fn, to, color, lw) => {
      if (to <= 0) return;
      ctx.beginPath();
      let first = true;
      for (let q = 0; q <= to; q += 0.005) {
        const X = ux(q), Y = uy(fn(q));
        first ? ctx.moveTo(X, Y) : ctx.lineTo(X, Y); first = false;
      }
      ctx.strokeStyle = color; ctx.lineWidth = lw;
      ctx.shadowColor = color; ctx.shadowBlur = 5; ctx.stroke(); ctx.shadowBlur = 0;
    };

    const t1 = this._ease(Math.min(1, Math.max(0, ts / 1.6)));
    const t2 = this._ease(Math.min(1, Math.max(0, (ts - 1.5) / 2.8)));
    const t3 = this._ease(Math.min(1, Math.max(0, (ts - 5.6) / 2.6)));

    if (t2 > 0.32) {
      ctx.fillStyle = "rgba(255,107,125,0.07)";
      ctx.fillRect(ux(0.32), pad.t, ux(Math.min(t2, 1)) - ux(0.32), h - pad.t - pad.b);
    }

    draw(trF, t1, "rgba(53,230,208,0.85)", 2);
    draw(vaBad, t2, "#ffcf6b", 2.4);
    draw(vaGood, t3, "#7cff9b", 2.4);

    ctx.font = "11px 'IBM Plex Mono', monospace"; ctx.fillStyle = "#5e7280";
    ctx.fillText("illustrative", w - pad.r - ctx.measureText("illustrative").width, h - pad.b - 6);

    ctx.font = "13px 'IBM Plex Mono', monospace";
    ctx.fillStyle = "rgba(53,230,208,0.95)"; ctx.fillText("train", pad.l + 14, pad.t + 20);
    if (ts >= 1.5) { ctx.fillStyle = "#ffcf6b"; ctx.fillText("val  ·  no regularisation", pad.l + 14, pad.t + 40); }
    if (ts >= 5.6) { ctx.fillStyle = "#7cff9b"; ctx.fillText("val  ·  weight_decay = 0.1", pad.l + 14, pad.t + 60); }

    if (t2 >= 1 && ts < 5.6) {
      ctx.fillStyle = "#ff6b7d"; ctx.font = "13px 'IBM Plex Mono', monospace";
      ctx.fillText("val turns up  ->  overfitting", ux(0.50), uy(vaBad(0.78)) - 18);
    }

    if (ts >= 4.8) {
      const ca = Math.min(1, (ts - 4.8) / 0.5);
      ctx.save(); ctx.globalAlpha = ca;
      ctx.fillStyle = "rgba(7,12,17,0.95)";
      ctx.strokeStyle = "#7cff9b"; ctx.lineWidth = 1.3;
      const txt = "AdamW  ·  weight_decay = 0.1";
      ctx.font = "12px 'IBM Plex Mono', monospace";
      const tw = ctx.measureText(txt).width + 22;
      ctx.beginPath();
      if (ctx.roundRect) ctx.roundRect(w - pad.r - tw - 10, pad.t + 8, tw, 26, 7); else ctx.rect(w - pad.r - tw - 10, pad.t + 8, tw, 26);
      ctx.fill(); ctx.stroke();
      ctx.fillStyle = "#7cff9b";
      ctx.fillText(txt, w - pad.r - tw + 1, pad.t + 25);
      ctx.restore();
      this._texDraw("\\theta\\leftarrow\\theta-\\eta\\lambda\\theta", w - pad.r - 12, pad.t + 38, 14, { align: "right", alpha: ca, color: "rgba(124,255,155,0.95)" });
    }

    if (ts >= 9.4) {
      const ga = Math.min(1, (ts - 9.4) / 0.6);
      const gx = ux(0.965);
      const y1 = uy(vaBad(0.965)), y2 = uy(vaGood(0.965));
      ctx.save(); ctx.globalAlpha = ga;
      ctx.strokeStyle = "#ff6b7d"; ctx.fillStyle = "#ff6b7d"; ctx.lineWidth = 1.6;
      ctx.beginPath(); ctx.moveTo(gx, y1 + 6); ctx.lineTo(gx, y2 - 6); ctx.stroke();
      ctx.beginPath(); ctx.moveTo(gx, y1); ctx.lineTo(gx - 4, y1 + 7); ctx.lineTo(gx + 4, y1 + 7); ctx.closePath(); ctx.fill();
      ctx.beginPath(); ctx.moveTo(gx, y2); ctx.lineTo(gx - 4, y2 - 7); ctx.lineTo(gx + 4, y2 - 7); ctx.closePath(); ctx.fill();
      ctx.font = "12px 'IBM Plex Mono', monospace";
      ctx.fillText("the gap is", gx - 96, (y1 + y2) / 2 - 4);
      ctx.fillText("overfitting", gx - 96, (y1 + y2) / 2 + 12);
      ctx.restore();
    }

    if (ts < 1.5) this._cap("Regularisation  ·  overfitting is invisible in the fit — it shows up in the LOSS CURVES");
    else if (ts < 4.8) this._cap("Train keeps falling forever  ·  val falls, bottoms out, then climbs FAST: the model is memorising noise");
    else if (ts < 5.6) this._cap("Same training, one change: weight decay switched on");
    else if (ts < 9.4) this._cap("AdamW shrinks every weight a little each step  ·  the val curve never turns up");
    else this._cap("The gap between the two val curves is pure overfitting, removed  ·  dropout attacks it from another angle — next");
  }

  _trDrop(ts, d) {
    const { ctx, w, h } = this;
    this._trTag("MODEL KNOB · DROPOUT");
    const cols = [
      { x: w * 0.16, n: 4 },
      { x: w * 0.385, n: 7 },
      { x: w * 0.615, n: 7 },
      { x: w * 0.84, n: 4 },
    ];
    const ny = (c, r) => h * 0.5 + (r - (cols[c].n - 1) / 2) * h * 0.105;

    let pass = 0, maskA = 0, evalMode = false, scaling = false;
    if (ts >= 2.0 && ts < 5.0) { pass = 1; maskA = Math.min(1, (ts - 2.0) / 0.7); }
    else if (ts >= 5.0 && ts < 7.5) { pass = 2; maskA = Math.min(1, (ts - 5.0) / 0.7); }
    else if (ts >= 7.5 && ts < 10.0) { pass = 2; maskA = 1; scaling = ts >= 7.9; }
    else if (ts >= 10.0) { pass = 0; maskA = 1 - Math.min(1, (ts - 10.0) / 0.8); evalMode = true; }

    const dropped = (c, r) => {
      if (pass === 0 || c === 0 || c === 3) return false;
      return Math.sin(pass * 7.3 + (c * 5 + r) * 3.37) > 0.25;
    };
    const strongEdge = (c, r, r2) => Math.sin(c * 3.1 + r * 5.7 + r2 * 2.3) > 0.45;

    const e1 = evalMode ? ts - 10.0 : 0;
    const conc = evalMode ? Math.min(1, Math.max(0, (e1 - 2.5) / 2.2)) : 0;

    const bld = (c) => this._ease(Math.min(1, Math.max(0, (ts - 0.3 - c * 0.5) / 0.7)));
    const flowing = ts >= 2.0;

    for (let c = 0; c < 3; c++) {
      const ea = Math.min(bld(c), bld(c + 1));
      if (ea <= 0) continue;
      for (let r = 0; r < cols[c].n; r++) {
        for (let r2 = 0; r2 < cols[c + 1].n; r2++) {
          const cut = (dropped(c, r) || dropped(c + 1, r2)) ? maskA : 0;
          if (cut >= 1) continue;
          const phase = (r * 7 + r2 * 3 + c * 5) * 4;
          let alpha, lw, flow;
          if (evalMode) {
            const strong = strongEdge(c, r, r2);
            if (strong) { alpha = 0.20 + 0.30 * conc; lw = 1.6 + 1.0 * conc; flow = true; }
            else { alpha = this._lerp(0.22, 0.07, conc); lw = 1.6; flow = conc < 0.85; }
          } else {
            alpha = 0.22 * (1 - cut);
            lw = 1.8;
            flow = flowing;
          }
          ctx.save();
          ctx.globalAlpha = ea * alpha;
          ctx.strokeStyle = "#35e6d0";
          ctx.lineWidth = lw;
          if (flow) {
            ctx.setLineDash([6, 12]);
            ctx.lineDashOffset = -(this.t * 70 + phase);
          }
          ctx.beginPath(); ctx.moveTo(cols[c].x, ny(c, r)); ctx.lineTo(cols[c + 1].x, ny(c + 1, r2)); ctx.stroke();
          ctx.setLineDash([]);
          ctx.restore();
        }
      }
    }

    for (let c = 0; c < 4; c++) {
      const na = bld(c);
      if (na <= 0) continue;
      for (let r = 0; r < cols[c].n; r++) {
        const isDrop = dropped(c, r);
        const dim = isDrop ? maskA : 0;
        ctx.save(); ctx.globalAlpha = na;
        if (dim > 0.02) {
          ctx.globalAlpha = na * (1 - dim);
          ctx.fillStyle = "#35e6d0";
          ctx.beginPath(); ctx.arc(cols[c].x, ny(c, r), 8, 0, 7); ctx.fill();
          ctx.globalAlpha = na * dim;
          ctx.strokeStyle = "rgba(255,107,125,0.9)"; ctx.lineWidth = 1.8;
          ctx.beginPath(); ctx.arc(cols[c].x, ny(c, r), 8, 0, 7); ctx.stroke();
        } else {
          ctx.fillStyle = evalMode && maskA <= 0 ? "#7cff9b" : "#35e6d0";
          ctx.beginPath(); ctx.arc(cols[c].x, ny(c, r), 8, 0, 7); ctx.fill();
        }
        if (scaling && !isDrop && (c === 1 || c === 2)) {
          ctx.save(); ctx.globalAlpha = na * Math.min(1, (ts - 7.9) / 0.5);
          ctx.font = "9px 'IBM Plex Mono', monospace";
          ctx.fillStyle = "#ffcf6b";
          ctx.fillText("x1/(1-p)", cols[c].x + 11, ny(c, r) + 3);
          ctx.restore();
        }
        ctx.restore();
      }
    }

    {
      let chipTxt, chipCol;
      if (ts < 2.0) { chipTxt = null; }
      else if (!evalMode) { chipTxt = `training  ·  forward pass #${pass}`; chipCol = "#ffcf6b"; }
      else { chipTxt = "model.eval()  ·  dropout off"; chipCol = "#7cff9b"; }
      if (chipTxt) {
        ctx.font = "12px 'IBM Plex Mono', monospace";
        const tw = ctx.measureText(chipTxt).width + 22;
        const bx = w - tw - 26, by = 28;
        ctx.fillStyle = "rgba(7,12,17,0.95)";
        ctx.strokeStyle = chipCol; ctx.lineWidth = 1.3;
        ctx.beginPath();
        if (ctx.roundRect) ctx.roundRect(bx, by - 17, tw, 26, 7); else ctx.rect(bx, by - 17, tw, 26);
        ctx.fill(); ctx.stroke();
        ctx.fillStyle = chipCol;
        ctx.fillText(chipTxt, bx + 11, by);
      }
    }

    if (ts < 2.0) this._cap("A model-level regulariser (default p = 0.0, off) — shown for completeness, not run by default");
    else if (ts < 5.0) this._cap("Training forward pass: dropped channels (outlined) output 0  ·  their connections are severed for this pass");
    else if (ts < 7.5) this._cap("A FRESH mask every forward pass  ·  co-adaptation breaks: features must be redundant and robust");
    else if (ts < 10.0) this._cap("Kept channels are scaled by 1/(1-p)  ·  the layer's expected output stays unchanged");
    else if (ts < 11.0) this._cap("model.eval(): dropout off  ·  the signal flows through EVERY connection at once");
    else this._cap("Training under dropout left strong, redundant paths  ·  the full net concentrates on them — an averaged ensemble");
  }

  _trStop(ts, d) {
    const { ctx, w, h } = this;
    this._trTag("EARLY STOPPING");
    const pad = { l: 52, r: 16, t: 18, b: 30 };
    this._axes(pad, "epoch", "loss");
    const pxE = (e) => pad.l + (e / d.ES_E) * (w - pad.l - pad.r);
    const pyV = (v) => pad.t + (1 - Math.min(1, v / 0.8)) * (h - pad.t - pad.b);

    const pe = Math.min(d.esStopE, (ts / 5.5) * d.esStopE);
    const drawCurve = (fn, to, color, lw, dash) => {
      ctx.beginPath();
      let started = false;
      for (let i = 0; i <= 300; i++) {
        const e = (i / 300) * d.ES_E;
        if (e > to) break;
        const X = pxE(e), Y = pyV(fn(e));
        started ? ctx.lineTo(X, Y) : ctx.moveTo(X, Y); started = true;
      }
      ctx.strokeStyle = color; ctx.lineWidth = lw;
      if (dash) ctx.setLineDash(dash);
      ctx.stroke(); ctx.setLineDash([]);
    };

    drawCurve(d.trainL, pe, "rgba(53,230,208,0.85)", 2);
    drawCurve(d.valL, pe, "#ffcf6b", 2.2);

    ctx.font = "11px 'IBM Plex Mono', monospace";
    ctx.fillStyle = "rgba(53,230,208,0.9)"; ctx.fillText("train", pad.l + 12, pad.t + 16);
    ctx.fillStyle = "#ffcf6b"; ctx.fillText("val", pad.l + 12, pad.t + 32);

    const eNow = Math.floor(pe);
    if (eNow >= d.esBestE) {
      const bx = pxE(d.esBestE), by = pyV(d.valL(d.esBestE));
      ctx.strokeStyle = "rgba(124,255,155,0.4)"; ctx.setLineDash([3, 4]); ctx.lineWidth = 1;
      ctx.beginPath(); ctx.moveTo(bx, by + 6); ctx.lineTo(bx, h - pad.b); ctx.stroke(); ctx.setLineDash([]);
      ctx.fillStyle = "#7cff9b";
      ctx.beginPath(); ctx.arc(bx, by, 5, 0, 7); ctx.fill();
      ctx.fillText(`best @ ${d.esBestE}`, bx - 28, h - pad.b + 14);
    }

    const pc = d.patAt[Math.min(eNow, d.ES_E)] || 0;
    if (eNow > d.esBestE && ts < 7.0) {
      ctx.font = "13px 'IBM Plex Mono', monospace";
      ctx.fillStyle = pc >= 15 ? "#ff6b7d" : "#ffcf6b";
      const ptxt = `patience ${Math.min(pc, 15)} / 15`;
      ctx.fillText(ptxt, (w - ctx.measureText(ptxt).width) / 2, pad.t + 20);
      ctx.font = "11px 'IBM Plex Mono', monospace";
    }

    if (ts >= 5.5) {
      const la = Math.min(1, (ts - 5.5) / 0.5);
      ctx.save(); ctx.globalAlpha = la;
      ctx.strokeStyle = "rgba(255,107,125,0.9)"; ctx.setLineDash([6, 5]); ctx.lineWidth = 1.6;
      ctx.beginPath(); ctx.moveTo(pxE(d.esStopE), pad.t); ctx.lineTo(pxE(d.esStopE), h - pad.b); ctx.stroke(); ctx.setLineDash([]);
      ctx.fillStyle = "#ff6b7d"; ctx.font = "12px 'IBM Plex Mono', monospace";
      ctx.fillText(`early stop @ ${d.esStopE}`, pxE(d.esStopE) - 116, pad.t + 16);
      ctx.font = "11px 'IBM Plex Mono', monospace";
      ctx.restore();
    }

    if (ts >= 7.0) {
      const ga = Math.min(1, (ts - 7.0) / 0.8);
      ctx.save(); ctx.globalAlpha = ga * 0.55;
      [[d.valL, "rgba(255,107,125,0.7)", 1.6], [d.trainL, "rgba(53,230,208,0.45)", 1.3]].forEach(([fn, color, lw]) => {
        ctx.beginPath();
        for (let i = 0; i <= 100; i++) {
          const e = this._lerp(d.esStopE, d.ES_E, i / 100);
          const X = pxE(e), Y = pyV(fn(e));
          i ? ctx.lineTo(X, Y) : ctx.moveTo(X, Y);
        }
        ctx.strokeStyle = color; ctx.lineWidth = lw;
        ctx.setLineDash([4, 4]); ctx.stroke(); ctx.setLineDash([]);
      });
      ctx.restore();
    }

    if (ts >= 9.0) {
      const ra = Math.min(1, (ts - 9.0) / 0.7);
      ctx.save(); ctx.globalAlpha = ra;
      ctx.strokeStyle = "#7cff9b"; ctx.lineWidth = 1.6;
      ctx.beginPath(); ctx.arc(pxE(d.esBestE), pyV(d.valL(d.esBestE)), 11 + Math.sin(this.t * 4) * 2, 0, 7); ctx.stroke();
      ctx.font = "13px 'IBM Plex Mono', monospace"; ctx.fillStyle = "#7cff9b";
      const rtxt = `restore_best = True  ->  checkpoint @ epoch ${d.esBestE}`;
      ctx.fillText(rtxt, (w - ctx.measureText(rtxt).width) / 2, pad.t + 20);
      ctx.restore();
    }

    if (ts < 3.0) this._cap("Early stopping  ·  train every epoch  ·  val (and the patience counter) every 5 epochs  ·  any new best resets the counter");
    else if (ts < 4.4) this._cap("Train keeps improving  ·  val follows it down — until it doesn't");
    else if (ts < 5.5) this._cap(`Past the best epoch every non-improving epoch raises the counter  ·  patience ${Math.min(pc, 15)}/15`);
    else if (ts < 7.0) this._cap("15 epochs without a new best  ->  EarlyStopping fires and the loop breaks");
    else if (ts < 9.0) this._cap("The dashed tail is what was skipped  ·  train would keep falling while val only climbs — overfitting");
    else this._cap(`restore_best = True  ->  the model rolls back to the epoch-${d.esBestE} checkpoint before anything is saved`);
  }

  _trEnd(ts, d) {
    const { ctx, w, h } = this;
    this._trTag("TRAINING REPLAY");
    const eP = Math.min(100, (ts / 14.0) * 100);

    const qs = [
      { x0: 16, y0: 34, x1: w / 2 - 8, y1: h / 2 - 8, title: "LR" },
      { x0: w / 2 + 8, y0: 34, x1: w - 16, y1: h / 2 - 8, title: "Loss" },
      { x0: 16, y0: h / 2 + 14, x1: w / 2 - 8, y1: h - 26, title: "Prediction vs GT" },
      { x0: w / 2 + 8, y0: h / 2 + 14, x1: w - 16, y1: h - 26, title: "Prediction ordering rate" },
    ];

    const lrF = (e) => (e < 5 ? (0.1 + 0.9 * e / 5) : 1) * (e < 50 ? d.cosF(e) : d.cosF(e - 50) * Math.min(1, 0.1 + 0.9 * (e - 50) / 5));
    const ordF = (e) => e < 50 ? 100 * (1 - Math.exp(-e / 13)) : 100;

    const ap = this._ease(Math.min(1, ts / 0.7));
    ctx.save(); ctx.globalAlpha = ap;
    qs.forEach((q) => {
      ctx.fillStyle = "rgba(4,7,10,0.85)";
      ctx.strokeStyle = "rgba(120,200,220,0.22)"; ctx.lineWidth = 1.1;
      ctx.beginPath();
      if (ctx.roundRect) ctx.roundRect(q.x0, q.y0, q.x1 - q.x0, q.y1 - q.y0, 8); else ctx.rect(q.x0, q.y0, q.x1 - q.x0, q.y1 - q.y0);
      ctx.fill(); ctx.stroke();
      ctx.font = "13px 'IBM Plex Mono', monospace";
      ctx.fillStyle = "rgba(230,247,243,0.95)";
      ctx.fillText(q.title, q.x0 + 12, q.y0 + 19);
    });
    ctx.restore();
    if (ap < 1) { this._cap("Training replay  ·  the whole run on one screen"); return; }

    const qx = (q, e) => q.x0 + 14 + (e / 100) * (q.x1 - q.x0 - 28);
    const qy = (q, v, vmax) => (q.y0 + 30) + (1 - Math.min(1, v / vmax)) * (q.y1 - q.y0 - 44);

    const swapLine = (q) => {
      if (eP < 50) return;
      ctx.strokeStyle = "rgba(255,207,107,0.45)"; ctx.setLineDash([4, 4]); ctx.lineWidth = 1;
      ctx.beginPath(); ctx.moveTo(qx(q, 50), q.y0 + 24); ctx.lineTo(qx(q, 50), q.y1 - 10); ctx.stroke();
      ctx.setLineDash([]);
    };

    const trace = (q, fn, vmax, color, lw) => {
      ctx.beginPath();
      let first = true;
      for (let e = 0; e <= eP; e += 0.4) {
        const X = qx(q, e), Y = qy(q, fn(e), vmax);
        first ? ctx.moveTo(X, Y) : ctx.lineTo(X, Y); first = false;
      }
      ctx.strokeStyle = color; ctx.lineWidth = lw; ctx.stroke();
    };

    swapLine(qs[0]);
    trace(qs[0], lrF, 1.08, "#35e6d0", 1.8);

    swapLine(qs[1]);
    trace(qs[1], (e) => d.lossAt(e), 0.85, "rgba(53,230,208,0.9)", 1.6);
    {
      const q = qs[1], valF = (e) => d.lossAt(e) * 1.16 + 0.018;
      ctx.fillStyle = "#ffcf6b";
      for (let e = 5; e <= 100; e += 5) {
        if (e > eP) break;
        ctx.beginPath(); ctx.arc(qx(q, e), qy(q, valF(e), 0.85), 2.6, 0, 7); ctx.fill();
      }
      if (eP >= 100) { ctx.beginPath(); ctx.arc(qx(q, 100), qy(q, valF(100), 0.85), 2.6, 0, 7); ctx.fill(); }
    }
    ctx.font = "10px 'IBM Plex Mono', monospace";
    ctx.fillStyle = "rgba(53,230,208,0.9)"; ctx.fillText("train", qs[1].x1 - 84, qs[1].y0 + 18);
    ctx.fillStyle = "#ffcf6b"; ctx.fillText("val", qs[1].x1 - 38, qs[1].y0 + 18);
    ctx.fillStyle = "#5e7280";
    ctx.fillText("val + checkpoint + early-stop: every 5 epochs", qs[1].x0 + 12, qs[1].y1 - 8);

    {
      const q = qs[2];
      const cMu = this._ease(Math.min(1, eP / 38));
      const cAS = eP < 50
        ? 0.55 * this._ease(eP / 50)
        : 0.55 + 0.45 * this._ease(Math.min(1, (eP - 50) / 30));
      const pr = d.target.map((p, i) => ({
        a: this._lerp(d.predRaw[i].a, p.a, cAS),
        mu: this._lerp(d.predRaw[i].mu, p.mu, cMu),
        s: this._lerp(d.predRaw[i].s, p.s, cAS),
      }));
      const cx = (x) => q.x0 + 14 + x * (q.x1 - q.x0 - 28);
      const cy = (v) => (q.y0 + 28) + (1 - Math.min(1, v / 1.25)) * (q.y1 - q.y0 - 40);
      ctx.beginPath();
      for (let i = 0; i <= 100; i++) {
        const x = i / 100;
        i ? ctx.lineTo(cx(x), cy(d.mix(d.target, x))) : ctx.moveTo(cx(x), cy(d.mix(d.target, x)));
      }
      ctx.strokeStyle = "rgba(150,176,182,0.5)"; ctx.lineWidth = 1.2; ctx.setLineDash([4, 4]); ctx.stroke(); ctx.setLineDash([]);
      ctx.beginPath();
      for (let i = 0; i <= 100; i++) {
        const x = i / 100;
        i ? ctx.lineTo(cx(x), cy(d.mix(pr, x))) : ctx.moveTo(cx(x), cy(d.mix(pr, x)));
      }
      ctx.strokeStyle = "#35e6d0"; ctx.lineWidth = 1.8;
      ctx.shadowColor = "rgba(53,230,208,0.5)"; ctx.shadowBlur = 5; ctx.stroke(); ctx.shadowBlur = 0;
    }

    {
      const q = qs[3];
      swapLine(q);
      trace(q, ordF, 108, "#7cff9b", 1.8);
      if (eP >= 50) {
        ctx.fillStyle = "#7cff9b";
        ctx.beginPath(); ctx.arc(qx(q, 50), qy(q, 100, 108), 4, 0, 7); ctx.fill();
        ctx.font = "11px 'IBM Plex Mono', monospace";
        ctx.fillText("100% @ swap", qx(q, 50) + 8, qy(q, 100, 108) + 14);
      }
      ctx.font = "10px 'IBM Plex Mono', monospace";
      ctx.fillStyle = "rgba(143,176,170,0.8)";
      ctx.fillText("% of pixels with mu-sorted slots", q.x0 + 12, q.y1 - 8);
    }

    ctx.font = "13px 'IBM Plex Mono', monospace";
    ctx.fillStyle = "rgba(230,247,243,0.95)";
    const eTxt = `epoch ${Math.floor(eP)} / 100`;
    ctx.fillText(eTxt, (w - ctx.measureText(eTxt).width) / 2, 22);

    if (ts < 14.0) {
      if (eP < 50) this._cap(`Training replay  ·  epoch ${Math.floor(eP)}/100  ·  param_l1 phase: mu locks in fast, amp & sigma lag behind`);
      else this._cap(`Training replay  ·  epoch ${Math.floor(eP)}/100  ·  complete loss: amp & sigma snap onto the target`);
    }
    else if (ts < 17.0) this._cap("The ordering rate hits 100% right at the curriculum swap — the sorted targets taught the net its output order");
    else this._cap("Best checkpoint ships: model weights + the elevation axis  ·  next stop: the inference pipeline");
  }

  /* ---------- inference: sliding window + stitch ---------- */

  _infSetup() {
    if (this._inf) return this._inf;

    const grid = { W: 336, H: 146, ph: 64, pw: 64, st: 32, n_v: 4, n_h: 10, padT: 7, padL: 8, nPatch: 40 };

    const P = grid.pw;
    const hann1d = new Float32Array(P);
    for (let i = 0; i < P; i++) hann1d[i] = Math.max(1e-3, 0.5 - 0.5 * Math.cos(2 * Math.PI * (i + 0.5) / P));
    const tri1d = new Float32Array(P);
    for (let i = 0; i < P; i++) tri1d[i] = Math.max(1e-3, 1 - Math.abs((i + 0.5) / P * 2 - 1));
    const hann2d = (i, j) => hann1d[i] * hann1d[j];

    const target  = [{ a: 0.9, mu: 0.40, s: 0.06 }, { a: 0.55, mu: 0.68, s: 0.05 }, { a: 0.0, mu: 0.16, s: 0.045 }];
    const predRaw = [{ a: 0.78, mu: 0.43, s: 0.075 }, { a: 0.47, mu: 0.64, s: 0.062 }, { a: 0.05, mu: 0.30, s: 0.10 }];
    const gtSort  = [{ a: 0.55, mu: 0.68, s: 0.05 }, { a: 0.9, mu: 0.40, s: 0.06 }, { a: 0.0, mu: 0.16, s: 0.045 }];
    const mix     = (ps, x) => ps.reduce((y, p) => y + Math.max(0, p.a) * Math.exp(-((x - p.mu) ** 2) / (2 * p.s * p.s + 1e-8)), 0);

    const frac = (v) => v - Math.floor(v);
    const c01 = (v) => Math.min(1, Math.max(0, v));
    const rnd = (i) => frac(Math.sin(i * 127.1 + 311.7) * 43758.5453);
    const tex = (ix, iy) => {
      let v = 0.42 + 0.3 * Math.sin(ix * 0.31 + Math.sin(iy * 0.17) * 2.1) * Math.cos(iy * 0.23 + Math.sin(ix * 0.11) * 1.7);
      v += 0.16 * Math.sin(ix * 1.3 + iy * 0.9) * Math.sin(ix * 0.7 - iy * 1.1);
      if (rnd(ix * 131 + iy * 57) > 0.965) v += 0.5;
      return Math.min(1, Math.max(0.05, v));
    };

    const places = [];
    for (let iv = 0; iv < grid.n_v; iv++) for (let ih = 0; ih < grid.n_h; ih++) places.push({ iv, ih, v0: iv * grid.st, h0: ih * grid.st });

    const NZ = 220;
    const scal = { r2: 0.962, rmse: 0.097, psnr: 28.4, mae: 0.061, mse: 0.011, cos: 0.994, peak: 1, mseP: 0.0094, maeP: 0.061, r2P: 0.971, cosP: 0.994, r2map: 0.94, mseMap: 0.011, ssimE: 0.93, ssimR: 0.88, ssimA: 0.90, order: 0.91, epoch: 87, bestE: 72, bestV: 0.0312, applied: 128, batch: 8 };

    const sections = ["1 Run summary", "2 Headline metrics", "3 Metric tables", "4 Profiles", "5 Pixel maps", "6 Gaussian analysis", "7 Tomogram slices", "8 SSIM curves", "9 Animations", "10 Notes"];

    this._inf = { grid, hann1d, tri1d, hann2d, target, predRaw, gtSort, mix, frac, c01, rnd, tex, places, NZ, scal, sections };
    return this._inf;
  }

  _inference() { this._dispatch("inference", this._infSetup()); }

  _infChip(txt, x, y, color, alpha, size) {
    const ctx = this.ctx;
    const fs = size || 13;
    ctx.font = `${fs}px 'IBM Plex Mono', monospace`;
    const tw = ctx.measureText(txt).width + 20;
    if (alpha != null && alpha <= 0) return tw;
    ctx.save(); ctx.globalAlpha = alpha == null ? 1 : alpha;
    ctx.fillStyle = "rgba(7,12,17,0.92)"; ctx.strokeStyle = color; ctx.lineWidth = 1.2;
    const ch = fs + 11;
    ctx.beginPath();
    if (ctx.roundRect) ctx.roundRect(x, y - ch + 8, tw, ch, 6); else ctx.rect(x, y - ch + 8, tw, ch);
    ctx.fill(); ctx.stroke();
    ctx.fillStyle = color; ctx.fillText(txt, x + 10, y + 1);
    ctx.restore();
    return tw;
  }

  _infArrow(x1, y1, x2, y2, color, alpha) {
    const ctx = this.ctx;
    if (alpha != null && alpha <= 0) return;
    ctx.save(); if (alpha != null) ctx.globalAlpha = alpha;
    ctx.strokeStyle = color; ctx.fillStyle = color; ctx.lineWidth = 1.6;
    ctx.beginPath(); ctx.moveTo(x1, y1); ctx.lineTo(x2, y2); ctx.stroke();
    const a = Math.atan2(y2 - y1, x2 - x1);
    ctx.beginPath(); ctx.moveTo(x2, y2);
    ctx.lineTo(x2 - 7 * Math.cos(a - 0.4), y2 - 7 * Math.sin(a - 0.4));
    ctx.lineTo(x2 - 7 * Math.cos(a + 0.4), y2 - 7 * Math.sin(a + 0.4));
    ctx.closePath(); ctx.fill(); ctx.restore();
  }

  _infText(txt, x, y, color, size) {
    const ctx = this.ctx;
    ctx.fillStyle = color || "rgba(206,228,222,0.9)";
    ctx.font = `${size || 13}px 'IBM Plex Mono', monospace`;
    ctx.fillText(txt, x, y);
  }

  _infNet(cx, cy, scale, a, emaP, sweepX) {
    const ctx = this.ctx;
    if (a <= 0) return;
    const cols = [3, 4, 4, 2];
    const dx = 34 * scale, dy = 22 * scale;
    const xs = cols.map((_, i) => cx + (i - 1.5) * dx);
    const node = [];
    cols.forEach((n, ci) => {
      const ys = [];
      for (let r = 0; r < n; r++) ys.push(cy + (r - (n - 1) / 2) * dy);
      node.push(ys);
    });
    ctx.save(); ctx.globalAlpha = a;
    ctx.strokeStyle = "rgba(53,230,208,0.18)"; ctx.lineWidth = 1;
    for (let ci = 0; ci < cols.length - 1; ci++) {
      node[ci].forEach((y0) => node[ci + 1].forEach((y1) => { ctx.beginPath(); ctx.moveTo(xs[ci], y0); ctx.lineTo(xs[ci + 1], y1); ctx.stroke(); }));
    }
    node.forEach((ys, ci) => ys.forEach((y) => {
      let col = "#35e6d0";
      if (emaP != null && ci > 0 && ci < 3) {
        const px = xs[ci];
        const sw2 = px < (sweepX == null ? -1e9 : sweepX) ? 1 : 0;
        if (sw2) col = "#ffcf6b";
      }
      ctx.beginPath(); ctx.arc(xs[ci], y, 4 * scale, 0, 7); ctx.fillStyle = col; ctx.fill();
    }));
    ctx.restore();
  }

  _infField(x, y, wd, ht, cell, valFn, rgb, alpha) {
    const ctx = this.ctx;
    const nx = Math.max(1, Math.floor(wd / cell)), ny = Math.max(1, Math.floor(ht / cell));
    for (let j = 0; j < ny; j++) {
      for (let i = 0; i < nx; i++) {
        const v = valFn(i, j, nx, ny);
        if (v <= 0) continue;
        ctx.fillStyle = `rgba(${rgb[0]},${rgb[1]},${rgb[2]},${Math.min(1, v) * alpha})`;
        ctx.fillRect(x + i * cell, y + j * cell, cell - 0.5, cell - 0.5);
      }
    }
  }

  _infHeat(x, y, cell, nx, ny, valFn, ramp, alpha) {
    const ctx = this.ctx;
    for (let j = 0; j < ny; j++) {
      for (let i = 0; i < nx; i++) {
        const v = Math.min(1, Math.max(0, valFn(i, j)));
        const c = ramp(v);
        ctx.fillStyle = `rgba(${c[0]},${c[1]},${c[2]},${alpha})`;
        ctx.fillRect(x + i * cell, y + j * cell, cell - 0.4, cell - 0.4);
      }
    }
  }

  _infTile(d, x, y, sz, params, rgb, alpha) {
    const ctx = this.ctx;
    const n = 8, cell = sz / n;
    for (let j = 0; j < n; j++) {
      for (let i = 0; i < n; i++) {
        const xx = (i + 0.5) / n;
        const v = Math.min(1, d.mix(params, xx) * (0.55 + 0.5 * d.tex(i + 3, j + 2)));
        ctx.fillStyle = `rgba(${rgb[0]},${rgb[1]},${rgb[2]},${(0.06 + v * 0.5) * alpha})`;
        ctx.fillRect(x + i * cell, y + j * cell, cell - 0.4, cell - 0.4);
      }
    }
  }

  _infLoad(ts, d) {
    const { ctx, w, h } = this;
    this._trTag("LOAD");
    const c01 = d.c01;
    const dim = ts > 13.0 ? this._lerp(1, 0.3, this._ease(c01((ts - 13.0) / 1.0))) : 1;
    ctx.save(); ctx.globalAlpha = dim;

    const cardW = 290, cardH = 196, cx = w * 0.30 - cardW / 2, cy = h / 2 - cardH / 2;
    const ca = this._ease(c01(ts / 1.0));
    if (ca > 0) {
      ctx.save(); ctx.globalAlpha = ca * dim;
      ctx.fillStyle = "rgba(7,12,17,0.92)"; ctx.strokeStyle = "rgba(120,200,220,0.4)"; ctx.lineWidth = 1.3;
      ctx.beginPath();
      if (ctx.roundRect) ctx.roundRect(cx, cy, cardW, cardH, 10); else ctx.rect(cx, cy, cardW, cardH);
      ctx.fill(); ctx.stroke();
      this._infText("best_model.pt", cx + 16, cy + 26, "#e6f7f3", 15);
      ctx.strokeStyle = "rgba(120,200,220,0.25)"; ctx.beginPath(); ctx.moveTo(cx + 12, cy + 36); ctx.lineTo(cx + cardW - 12, cy + 36); ctx.stroke();
      ctx.restore();
    }
    const rows = [
      ["epoch", "87  (example)"],
      ["best_epoch", "72  (example)"],
      ["best_val_loss", "0.0312  (example)"],
      ["params", "[state_dict]"],
      ["x_axis", "220 bins  (example)"],
    ];
    rows.forEach((r, i) => {
      const ra = this._ease(c01((ts - 0.6 - i * 0.35) / 0.5));
      if (ra <= 0) return;
      const yR = cy + 60 + i * 27;
      ctx.save(); ctx.globalAlpha = ra * dim;
      this._infText(r[0], cx + 16, yR, "rgba(206,228,222,0.9)", 13);
      this._infText(r[1], cx + 150, yR, "#35e6d0", 13);
      ctx.restore();
    });

    const netX = w * 0.74, netY = h / 2 - 8;
    const na = this._ease(c01((ts - 2.0) / 1.2));
    const sweepX = ts >= 4.0 ? this._lerp(netX - 60, netX + 60, this._ease(c01((ts - 4.0) / 4.0))) : -1e9;
    const loadActive = ts >= 4.0 && ts < 9.0;
    this._infNet(netX, netY, 1.25, na * dim, loadActive ? 1 : null, ts >= 4.0 ? sweepX : null);

    if (na > 0 && ts < 9.0) {
      const la = this._ease(c01((ts - 2.4) / 0.8));
      this._infArrow(cx + cardW + 6, netY, netX - 70, netY, "rgba(53,230,208,0.7)", la * dim);
      this._infText("load_state_dict", cx + cardW + 14, netY - 10, "rgba(143,176,170,0.9)", 12);
    }

    if (ts >= 4.0 && ts < 9.5) {
      const cnt = Math.round(this._ease(c01((ts - 4.0) / 4.0)) * 128);
      const ea = this._ease(c01((ts - 4.0) / 0.6));
      ctx.save(); ctx.globalAlpha = ea * dim;
      this._infText(`params  ->  layers`, netX - 70, netY + 70, "rgba(53,230,208,0.9)", 12);
      this._infText(`${cnt} parameter tensors restored`, netX - 70, netY + 88, "rgba(53,230,208,0.9)", 13);
      ctx.restore();
    }

    if (ts >= 9.0) {
      const ea = this._ease(c01((ts - 9.0) / 0.6));
      this._infChip("model.eval()", netX - 60, netY - 70, "#7cff9b", ea * dim);
      this._infChip("Stats", netX - 60, netY - 42, "rgba(120,200,220,0.5)", this._ease(c01((ts - 9.4) / 0.6)) * dim);
      this._infChip("ModelWrapper", netX + 4, netY - 42, "rgba(120,200,220,0.5)", this._ease(c01((ts - 9.6) / 0.6)) * dim);
      this._infText("denormalize · clamp on every call", netX - 60, netY + 60, "rgba(143,176,170,0.85)", 11);
    }
    ctx.restore();

    if (ts >= 11.5) {
      ctx.save();
      ctx.font = "15px 'IBM Plex Mono', monospace";
      const emTxt = "eval-mode model ready";
      this._infText(emTxt, w * 0.30 - ctx.measureText(emTxt).width / 2, h / 2 + cardH / 2 + 30, "#e6f7f3", 15);
      ctx.restore();
    }

    if (ts < 2.0) this._cap("Inference loads a finished training run  ·  best_model.pt");
    else if (ts < 4.0) this._cap("Rebuild the architecture  ·  load_state_dict restores the trained weights");
    else if (ts < 9.0) this._cap("Weights stream into every layer  ·  128 parameter tensors restored");
    else if (ts < 11.5) this._cap("The trained model is rebuilt, ready to score");
    else this._cap("model.eval()  ·  wrapped to denormalize + clamp every prediction");
  }

  _infGrid(ts, d) {
    const { ctx, w, h } = this;
    this._trTag("PREDICT · grid");
    const c01 = d.c01, g = d.grid;
    const kk = Math.min((w * 0.6 - 40) / g.W, (h - 110) / g.H);
    const gx = 56, gy = 64, gw = g.W * kk, gh = g.H * kk, ps = g.ph * kk, st = g.st * kk;
    const padL = g.padL * kk, padT = g.padT * kk;
    const fx = gx + gw + 44;

    const born = this._ease(c01(ts / 2.0));
    this._infField(gx, gy, gw * born, gh, 7, (i, j) => 0.05 + d.tex(i, j) * 0.3, [53, 230, 208], 0.9);
    ctx.strokeStyle = "rgba(120,200,220,0.5)"; ctx.lineWidth = 1.4; ctx.strokeRect(gx, gy, gw, gh);
    this._infText("azimuth ->", gx + gw / 2 - 30, gy + gh + 22, "rgba(143,176,170,0.85)", 12);
    ctx.save(); ctx.translate(gx - 14, gy + gh / 2 + 24); ctx.rotate(-Math.PI / 2); this._infText("range ->", 0, 0, "rgba(143,176,170,0.85)", 12); ctx.restore();

    if (ts >= 2.5) {
      const pp = this._ease(c01((ts - 2.5) / 1.4));
      ctx.strokeStyle = `rgba(53,230,208,${0.8 * pp})`; ctx.setLineDash([6, 4]); ctx.lineWidth = 1.4;
      ctx.strokeRect(gx - padL, gy - padT, gw + 2 * padL, gh + 2 * padT); ctx.setLineDash([]);
      this._infText("reflective pad  v:7|7  h:8|8", gx, gy + gh + 40, "rgba(53,230,208,0.9)", 12);
    }

    if (ts >= 6.0) {
      const k = Math.min(g.nPatch, Math.floor((ts - 6.0) / 0.14) + 1);
      for (let n = 0; n < k; n++) {
        const p = d.places[n];
        const px = gx + p.h0 * kk, py = gy + p.v0 * kk;
        ctx.fillStyle = "rgba(124,255,155,0.05)"; ctx.fillRect(px, py, ps, ps);
        ctx.strokeStyle = n === k - 1 ? "#7cff9b" : "rgba(124,255,155,0.28)"; ctx.lineWidth = n === k - 1 ? 2 : 1.1;
        ctx.strokeRect(px, py, ps, ps);
        const over = px + ps - (gx + gw);
        if (over > 0) { ctx.fillStyle = "rgba(255,107,125,0.2)"; ctx.fillRect(gx + gw, py, over, ps); }
      }
      this._infText(`patch ${k} / 40`, gx, gy - 14, "#7cff9b", 13);
    }

    const cardA = this._ease(c01((ts - 11.0) / 1.2));
    if (cardA > 0) {
      ctx.save(); ctx.globalAlpha = cardA;
      const rows = [
        ["split", "test"], ["scene", "336 × 146  (example)"], ["patch", "64 × 64"],
        ["stride", "32  (50% overlap)"], ["grid", "n_v 4 × n_h 10"], ["patches", "40"], ["batch", "shuffle = False"],
      ];
      ctx.fillStyle = "rgba(7,12,17,0.9)"; ctx.strokeStyle = "rgba(120,200,220,0.3)"; ctx.lineWidth = 1.2;
      ctx.beginPath();
      if (ctx.roundRect) ctx.roundRect(fx - 12, gy - 6, w - fx - 30, rows.length * 26 + 38, 10); else ctx.rect(fx - 12, gy - 6, w - fx - 30, rows.length * 26 + 38);
      ctx.fill(); ctx.stroke();
      this._infText("test split", fx, gy + 16, "#e6f7f3", 15);
      rows.forEach((r, i) => {
        const yR = gy + 44 + i * 26;
        this._infText(r[0], fx, yR, "rgba(206,228,222,0.85)", 13);
        this._infText(r[1], fx + 110, yR, "#35e6d0", 13);
      });
      ctx.restore();
    }

    if (ts < 2.5) this._cap("The test split is one continuous SAR scene  ·  336 × 146 pixels");
    else if (ts < 6.0) this._cap("Reflective padding rings the scene so edge patches never invent data");
    else if (ts < 12.0) this._cap("A 64 × 64 window strides by 32  ·  neighbours overlap 50% in both axes");
    else this._cap("40 overlapping patches  ·  n_v 4 × n_h 10  ·  fed in order, shuffle = False");
  }

  _infForward(ts, d) {
    const { ctx, w, h } = this;
    this._trTag("PREDICT · GPU");
    const c01 = d.c01, g = d.grid;
    const kk = Math.min((w * 0.32 - 40) / g.W, (h - 130) / g.H);
    const gx = 48, gy = 70, gw = g.W * kk, gh = g.H * kk, ps = g.ph * kk;

    this._infField(gx, gy, gw, gh, 6, (i, j) => 0.05 + d.tex(i, j) * 0.22, [53, 230, 208], 0.4);
    ctx.strokeStyle = "rgba(120,200,220,0.35)"; ctx.lineWidth = 1.2; ctx.strokeRect(gx, gy, gw, gh);

    const netX = w * 0.56, netY = h / 2 - 4;
    this._infNet(netX, netY, 1.2, 1, null, null);

    const lift = this._ease(c01(ts / 3.0));
    const batchN = 8;
    for (let n = 0; n < batchN; n++) {
      const p = d.places[n + 4];
      const ax = gx + p.h0 * kk, ay = gy + p.v0 * kk;
      const tx = netX - 110, ty = netY - 60 + (n % 4) * 30;
      const bx = this._lerp(ax, tx, lift), by = this._lerp(ay, ty, lift);
      ctx.fillStyle = "rgba(124,255,155,0.12)"; ctx.fillRect(bx, by, ps, ps);
      ctx.strokeStyle = "#7cff9b"; ctx.lineWidth = 1.4; ctx.strokeRect(bx, by, ps, ps);
    }
    this._infText("batch B = 8 patches  (example)", netX - 130, netY + 92, "#7cff9b", 12);
    this._infText("device = cuda", netX - 130, netY + 108, "rgba(143,176,170,0.85)", 12);

    if (ts >= 3.0) {
      const pulse = 0.5 + 0.5 * Math.sin(this.t * 6);
      ctx.strokeStyle = `rgba(53,230,208,${0.3 + 0.5 * pulse})`; ctx.lineWidth = 2;
      ctx.beginPath(); ctx.moveTo(netX - 40, netY); ctx.lineTo(netX + 40, netY); ctx.stroke();
      this._eqDraw([{ t: "pred_params = model(images)", up: true, c: "#35e6d0" }], netX - 70, netY - 86, 15, this._ease(c01((ts - 3.0) / 0.8)));
    }

    const ro = w - 250;
    if (ts >= 3.5) {
      const ra = this._ease(c01((ts - 3.5) / 1.0));
      ctx.save(); ctx.globalAlpha = ra;
      this._infText("pred_params (denorm)", ro, gy + 4, "#e6f7f3", 13);
      const params = ["a₀ μ₀ σ₀", "a₁ μ₁ σ₁", "a₂ μ₂ σ₂"];
      params.forEach((p, i) => this._infText(p, ro, gy + 30 + i * 22, "#35e6d0", 13));
      ctx.restore();
    }

    if (ts >= 7.0) {
      const ca = this._ease(c01((ts - 7.0) / 0.8));
      this._infChip("denormalize_output", ro, gy + 120, "#7cff9b", ca);
      this._infChip("clamp_gaussian_params", ro, gy + 150, "#7cff9b", this._ease(c01((ts - 7.4) / 0.8)));
      const clp = this._ease(c01((ts - 8.0) / 2.0));
      const bx = ro, by = gy + 178, bw = 150, bhh = 12;
      const raw = bw * (1.35 - 0.35 * clp);
      ctx.strokeStyle = "rgba(120,200,220,0.4)"; ctx.lineWidth = 1; ctx.strokeRect(bx, by, bw, bhh);
      ctx.fillStyle = "rgba(53,230,208,0.6)"; ctx.fillRect(bx, by, Math.min(bw, raw), bhh);
      if (raw > bw) { ctx.fillStyle = "rgba(255,107,125,0.55)"; ctx.fillRect(bx + bw, by, raw - bw, bhh); }
      ctx.strokeStyle = "#ff6b7d"; ctx.lineWidth = 1.6; ctx.beginPath(); ctx.moveTo(bx + bw, by - 3); ctx.lineTo(bx + bw, by + bhh + 3); ctx.stroke();
      this._infText("a ∈ [0, amp_max]", ro, by + 28, "rgba(206,228,222,0.85)", 11);
      this._infText("µ, σ → physical range", ro, by + 44, "rgba(206,228,222,0.85)", 11);
    }

    if (ts >= 11.0) {
      const ga = this._ease(c01((ts - 11.0) / 0.8));
      ctx.save(); ctx.globalAlpha = ga;
      this._infText("GT params denormalised too", netX - 80, netY + 130, "#ffcf6b", 12);
      this._infChip("metrics fan out → CPU pool ×80", netX - 80, netY + 158, "rgba(255,207,107,0.6)", ga, 11);
      ctx.restore();
    }

    if (ts < 3.0) this._cap("Patches are batched and sent to the GPU  ·  device = cuda");
    else if (ts < 7.0) this._cap("pred_params = model(images)  ·  three Gaussians per pixel: a, µ, σ");
    else if (ts < 11.0) this._cap("Outputs are denormalised, then clamped: a ≥ 0, µ and σ to physical range");
    else this._cap("Ground-truth params are denormalised too  ·  scoring fans out to a CPU pool");
  }

  _infScore(ts, d) {
    const { ctx, w, h } = this;
    this._trTag("PREDICT · score");
    const c01 = d.c01;
    const pad = { l: 46, r: 16, t: 26, b: 34 };
    const px = (x) => pad.l + x * (w - pad.l - pad.r);
    const py = (v) => pad.t + (1 - Math.min(1, v / 1.05)) * (h - pad.t - pad.b);
    this._grid(pad);

    if (ts < 4.0) {
      const slotsGT = [{ mu: 0.40, a: 0.9 }, { mu: 0.68, a: 0.55 }, { mu: 0.16, a: 0.0 }];
      const sorted = [{ mu: 0.16, a: 0.0, lab: "+∞" }, { mu: 0.40, a: 0.9 }, { mu: 0.68, a: 0.55 }];
      const reord = [2, 0, 1];
      const mv = this._ease(c01((ts - 1.0) / 2.0));
      slotsGT.forEach((s, i) => {
        const fromX = px(0.16) + i * 110;
        const toIdx = reord[i];
        const toX = px(0.16) + toIdx * 110;
        const x = this._lerp(fromX, toX, mv);
        const inactive = s.a < 1e-3;
        const lab = inactive ? "GT μ +∞" : `GT μ=${s.mu.toFixed(2)}`;
        this._infChip(lab, x, pad.t + 28, inactive ? "rgba(143,176,170,0.7)" : "#ffcf6b", 1, 12);
      });
      this._infText("GT slots sorted by µ  ·  inactive → +∞", pad.l, h - 44, "#ffcf6b", 12);
      this._infText("pred left unsorted", w - 220, h - 44, "#35e6d0", 12);
      this._cap("Before scoring, GT slots are sorted by µ  ·  inactive Gaussians go to +∞");
      return;
    }

    const reveal = this._ease(c01((ts - 4.0) / 3.0));
    [["#ffcf6b", d.gtSort], ["#35e6d0", d.predRaw]].forEach(([col, ps]) => {
      ctx.save(); ctx.globalAlpha = 0.4 * reveal;
      ps.forEach((p) => {
        if (p.a < 1e-3) return;
        this._curvePath([p], d.mix, px, py);
        ctx.strokeStyle = col; ctx.lineWidth = 1; ctx.stroke();
      });
      ctx.restore();
    });
    ctx.save(); ctx.globalAlpha = reveal;
    this._curvePath(d.gtSort, d.mix, px, py); ctx.strokeStyle = "#ffcf6b"; ctx.lineWidth = 2; ctx.setLineDash([6, 4]); ctx.stroke(); ctx.setLineDash([]);
    this._curvePath(d.predRaw, d.mix, px, py); ctx.strokeStyle = "#35e6d0"; ctx.lineWidth = 2.2; ctx.stroke();
    ctx.restore();

    this._texDraw("f(z)=\\sum_{k=1}^{K}a_k\\,e^{-(z-\\mu_k)^2/2\\sigma_k^2}", pad.l + 8, pad.t + 2, 16, { alpha: this._ease(c01((ts - 4.5) / 1.0)), color: "rgba(230,247,243,0.95)" });

    if (ts >= 9.0) {
      const da = this._ease(c01((ts - 9.0) / 1.0));
      ctx.save(); ctx.globalAlpha = 0.3 * da;
      ctx.beginPath();
      const N = 80;
      for (let i = 0; i <= N; i++) { const x = i / N; const sx = px(x); i ? ctx.lineTo(sx, py(d.mix(d.predRaw, x))) : ctx.moveTo(sx, py(d.mix(d.predRaw, x))); }
      for (let i = N; i >= 0; i--) { const x = i / N; ctx.lineTo(px(x), py(d.mix(d.gtSort, x))); }
      ctx.closePath(); ctx.fillStyle = "#ff6b7d"; ctx.fill();
      ctx.restore();

      const mets = [["MSE", "0.0094"], ["MAE", "0.061"], ["R²", "0.971"], ["cos", "0.994"], ["Δpeak", "1 bin"]];
      const mcol0 = px(0.6), mcolW = 112;
      mets.forEach((m, i) => {
        const ma = this._ease(c01((ts - 9.5 - i * 0.3) / 0.6));
        if (ma <= 0) return;
        const x = mcol0 + (i % 2) * mcolW, y = pad.t + 24 + Math.floor(i / 2) * 24;
        ctx.save(); ctx.globalAlpha = ma;
        this._infText(`${m[0]} ${m[1]}`, x, y, "#7cff9b", 12);
        ctx.restore();
      });
      const exA = this._ease(c01((ts - 10.0) / 0.6));
      if (exA > 0) { ctx.save(); ctx.globalAlpha = exA; this._infText("(example values)", mcol0, pad.t + 24 + 3 * 24, "rgba(143,176,170,0.6)", 10); ctx.restore(); }
    }

    if (ts >= 14.0) {
      const za = this._ease(c01((ts - 14.0) / 1.5));
      const gxg = w - 170, gyg = h - 120, cz = 9;
      ctx.save(); ctx.globalAlpha = za;
      for (let r = 0; r < 6; r++) for (let cc = 0; cc < 10; cc++) {
        const lit = d.rnd(r * 17 + cc * 3 + Math.floor(this.t * 2)) > 0.4;
        ctx.fillStyle = lit ? "rgba(124,255,155,0.55)" : "rgba(124,255,155,0.12)";
        ctx.fillRect(gxg + cc * cz, gyg + r * cz, cz - 1, cz - 1);
      }
      ctx.save();
      ctx.font = "11px 'IBM Plex Mono', monospace";
      const ppTxt = "ProcessPoolExecutor · 80 workers";
      this._infText(ppTxt, gxg + 10 * cz - ctx.measureText(ppTxt).width, gyg - 8, "rgba(143,176,170,0.85)", 11);
      ctx.restore();
      ctx.restore();
    }

    this._infText("pred", pad.l + 8, h - 24, "#35e6d0", 12);
    this._infText("GT", pad.l + 64, h - 24, "#ffcf6b", 12);

    if (ts < 9.0) this._cap("Each slot's a, µ, σ reconstructs an elevation curve via the Gaussian mixture");
    else if (ts < 14.0) this._cap("Per pixel: MSE, MAE, R², cosine, peak-index error between pred and GT curves");
    else this._cap("Every pixel of every patch is scored in parallel across the CPU pool");
  }

  _infStitch(ts, d) {
    const { ctx, w, h } = this;
    this._trTag("STITCH · overlap-add");
    const c01 = d.c01, g = d.grid;

    if (ts < 5.0) {
      const pad = { l: 46, r: w * 0.5, t: 30, b: 40 };
      const px = (x) => pad.l + x * (w - pad.l - pad.r);
      const py = (v) => pad.t + (1 - v) * (h - pad.t - pad.b);
      ctx.strokeStyle = "rgba(120,200,220,0.12)"; ctx.lineWidth = 1;
      ctx.beginPath(); ctx.moveTo(pad.l, py(0)); ctx.lineTo(w - pad.r, py(0)); ctx.stroke();
      const up = this._ease(c01(ts / 2.5));
      const N = Math.round(up * 64);
      ctx.beginPath();
      for (let i = 0; i <= N; i++) { const x = i / 64; const sx = px(x), sy = py(d.hann1d[Math.min(63, i)]); i ? ctx.lineTo(sx, sy) : ctx.moveTo(sx, sy); }
      ctx.strokeStyle = "#35e6d0"; ctx.lineWidth = 2.4; ctx.stroke();
      this._infText("1-D Hann profile", pad.l, pad.t - 6, "#e6f7f3", 13);
      this._infText("zero at both edges", px(0.0) - 10, py(0) + 18, "rgba(255,107,125,0.9)", 11);
      this._texDraw("w(i)=\\tfrac{1}{2}-\\tfrac{1}{2}\\cos\\!\\left(\\tfrac{2\\pi(i+1/2)}{P}\\right)", pad.l + 6, pad.t + 16, 15, { alpha: this._ease(c01((ts - 1.0) / 1.0)), color: "#35e6d0" });

      if (ts >= 2.0) {
        const ha = this._ease(c01((ts - 2.0) / 1.5));
        const hx = w * 0.56, hy = pad.t + 4, cell = (h - pad.t - pad.b) / 40;
        ctx.save(); ctx.globalAlpha = ha;
        this._infHeat(hx, hy, cell, 40, 40, (i, j) => d.hann1d[Math.floor(i / 40 * 64)] * d.hann1d[Math.floor(j / 40 * 64)], (v) => [53, 230, 208], 1);
        ctx.strokeStyle = "rgba(120,200,220,0.4)"; ctx.lineWidth = 1; ctx.strokeRect(hx, hy, cell * 40, cell * 40);
        this._texDraw("W_{2D}=w_v\\otimes w_h", hx, hy - 22, 15, { color: "rgba(230,247,243,0.95)" });
        ctx.restore();
      }
      this._cap("The stitch weight is a real 2-D Hann window — a raised cosine, zero at the patch edges");
      return;
    }

    if (ts < 10.0) {
      const s = ts - 5.0;
      const kk = 2.4;
      const ps = g.ph * kk, ox = w / 2 - ps, oy = h / 2 - ps * 0.7;
      const block = [[0, 0], [1, 0], [0, 1], [1, 1]];
      const drop = this._ease(c01(s / 2.5));
      block.forEach((b, i) => {
        const pa = this._ease(c01((s - i * 0.3) / 0.6));
        if (pa <= 0) return;
        const bx = ox + b[0] * g.st * kk, by = oy + b[1] * g.st * kk;
        ctx.save(); ctx.globalAlpha = pa;
        this._infTile(d, bx, by, ps, i % 2 ? d.predRaw : d.target, [53, 230, 208], 1);
        ctx.strokeStyle = "rgba(53,230,208,0.5)"; ctx.lineWidth = 1; ctx.strokeRect(bx, by, ps, ps);
        ctx.restore();
      });
      if (s >= 2.0) {
        const sa = (0.5 + 0.5 * Math.sin(this.t * 6)) * this._ease(c01((s - 2.0) / 1.0));
        const mx = ox + g.st * kk, my = oy + g.st * kk;
        ctx.fillStyle = `rgba(255,107,125,${0.35 * sa})`;
        ctx.fillRect(mx, oy, g.st * kk, ps + g.st * kk);
        ctx.fillRect(ox, my, ps + g.st * kk, g.st * kk);
        ctx.strokeStyle = `rgba(255,107,125,${0.9})`; ctx.lineWidth = 2;
        ctx.beginPath(); ctx.moveTo(mx, oy); ctx.lineTo(mx, oy + ps + g.st * kk); ctx.stroke();
        ctx.beginPath(); ctx.moveTo(ox, my); ctx.lineTo(ox + ps + g.st * kk, my); ctx.stroke();
        this._infText("seams: overlaps double-counted", ox, oy - 12, "#ff6b7d", 13);
      }
      this._infText("window = uniform", ox, oy + ps * 2 + 20, "rgba(143,176,170,0.85)", 12);
      this._cap("Plain averaging double-counts the overlaps  ·  hard seams appear at every patch boundary");
      return;
    }

    if (ts < 20.0) {
      const s = ts - 10.0;
      const pw3 = g.W, ph3 = g.H;
      const cell = Math.min((w / 2 - 80) / (pw3 + 2 * g.padL), (h - 150) / (ph3 + 2 * g.padT));
      const panW = (pw3 + 2 * g.padL) * cell, panH = (ph3 + 2 * g.padT) * cell;
      const ax = 50, ay = 64, wx = w / 2 + 30, wy = 64;
      const k = Math.min(g.nPatch, Math.floor(s / 0.22) + 1);

      const accum = (px2, py2, label, col, rgb, weightOnly) => {
        ctx.fillStyle = "rgba(4,7,10,0.85)"; ctx.fillRect(px2, py2, panW, panH);
        ctx.strokeStyle = "rgba(120,200,220,0.25)"; ctx.lineWidth = 1; ctx.strokeRect(px2, py2, panW, panH);
        const buf = {};
        for (let n = 0; n < k; n++) {
          const p = d.places[n];
          for (let jj = 0; jj < g.ph; jj += 4) for (let ii = 0; ii < g.pw; ii += 4) {
            const gi = p.h0 + ii, gj = p.v0 + jj;
            const wv = d.hann2d(ii, jj);
            const key = gi + "_" + gj;
            const add = weightOnly ? wv : wv * (0.4 + 0.6 * d.tex(ii / 4 + p.ih, jj / 4 + p.iv));
            buf[key] = (buf[key] || 0) + add;
          }
        }
        const norm = weightOnly ? 2.2 : 1.6;
        Object.keys(buf).forEach((key) => {
          const parts = key.split("_"); const gi = +parts[0], gj = +parts[1];
          const v = Math.min(1, buf[key] / norm);
          ctx.fillStyle = `rgba(${rgb[0]},${rgb[1]},${rgb[2]},${0.1 + v * 0.85})`;
          ctx.fillRect(px2 + gi * cell, py2 + gj * cell, 4 * cell, 4 * cell);
        });
        this._infText(label, px2, py2 - 8, col, 14);
      };

      accum(ax, ay, "A   accumulator", "#35e6d0", [53, 230, 208], false);
      accum(wx, wy, "W   weight", "#ffcf6b", [255, 207, 107], true);

      this._texDraw("A\\mathrel{+}=p\\cdot w", ax, ay + panH + 14, 16, { color: "#35e6d0" });
      this._texDraw("W\\mathrel{+}=w", wx, wy + panH + 14, 16, { color: "#ffcf6b" });
      ctx.save();
      ctx.font = "13px 'IBM Plex Mono', monospace";
      const pcTxt = `patch ${k} / 40`;
      this._infText(pcTxt, (ax + panW + wx) / 2 - ctx.measureText(pcTxt).width / 2, ay + panH / 2 + 4, "#7cff9b", 13);
      ctx.restore();

      this._cap("Overlap-add: each patch contributes A += p·w to the sum and W += w to the weight");
      return;
    }

    if (ts < 26.0) {
      const s = ts - 20.0;
      const pw3 = g.W, ph3 = g.H;
      const cell = Math.min((w / 3 - 50) / pw3, (h - 150) / ph3);
      const panW = pw3 * cell, panH = ph3 * cell;
      const x0 = 30, x1 = w / 2 - panW / 2, x2 = w - panW - 30, yy = 70;
      const sweep = this._ease(c01(s / 3.5));

      const drawPanel = (px2, valFn, rgb, label, col) => {
        ctx.fillStyle = "rgba(4,7,10,0.85)"; ctx.fillRect(px2, yy, panW, panH);
        this._infField(px2, yy, panW, panH, Math.max(3, cell * 2), (i, j, nx, ny) => valFn(i / nx, j / ny), rgb, 0.9);
        ctx.strokeStyle = "rgba(120,200,220,0.25)"; ctx.lineWidth = 1; ctx.strokeRect(px2, yy, panW, panH);
        this._infText(label, px2, yy - 8, col, 13);
      };

      const seamV = (u, v) => {
        const su = Math.abs(((u * 10) % 1) - 0.5) < 0.06 ? 1 : 0;
        return su;
      };
      drawPanel(x0, (u, v) => 0.3 + 0.5 * d.tex(u * 30, v * 14) + seamV(u, v) * 0.6 * (1 - sweep), [53, 230, 208], "A", "#35e6d0");
      drawPanel(x1, (u, v) => 0.3 + 0.5 * (0.5 + 0.5 * Math.cos((u * 9 + 0.5) * 2 * Math.PI * 0.5)), [255, 207, 107], "W", "#ffcf6b");

      ctx.fillStyle = "rgba(4,7,10,0.85)"; ctx.fillRect(x2, yy, panW, panH);
      this._infField(x2, yy, panW, panH, Math.max(3, cell * 2), (i, j, nx, ny) => {
        const u = i / nx, v = j / ny;
        const done = u < sweep ? 1 : 0;
        const seam = seamV(u, v) * 0.6 * (1 - done);
        return 0.35 + 0.45 * d.tex(u * 30, v * 14) + seam;
      }, [124, 255, 155], 0.95);
      ctx.strokeStyle = "rgba(120,200,220,0.25)"; ctx.lineWidth = 1; ctx.strokeRect(x2, yy, panW, panH);
      const swX = x2 + panW * sweep;
      if (sweep > 0 && sweep < 1) { ctx.strokeStyle = "#7cff9b"; ctx.lineWidth = 2; ctx.beginPath(); ctx.moveTo(swX, yy); ctx.lineTo(swX, yy + panH); ctx.stroke(); }
      this._infText("Ĉ = A / W", x2, yy - 8, "#7cff9b", 13);

      const ceqBox = this._texDraw("\\hat{C}=\\dfrac{A}{\\max(W,1)}", w / 2, yy + panH + 20, 16, { align: "center", color: "#7cff9b" });
      const ceqB = ceqBox ? ceqBox.y + ceqBox.h + 18 : yy + panH + 78;
      this._infText("safe divide where W = 0", w / 2 - 78, ceqB, "rgba(143,176,170,0.85)", 11);

      this._cap("Divide the sum by the accumulated weight  ·  Ĉ = A / W  ·  the seams vanish");
      return;
    }

    const s = ts - 26.0;
    const g2 = d.grid;
    const cell = Math.min((w * 0.42) / (g2.W + 2 * g2.padL), (h - 150) / (g2.H + 2 * g2.padT));
    const fx = 60, fy = 70;
    const fullW = (g2.W + 2 * g2.padL) * cell, fullH = (g2.H + 2 * g2.padT) * cell;
    const trim = this._ease(c01(s / 2.0));
    const ix = fx + g2.padL * cell * trim, iy = fy + g2.padT * cell * trim;
    const iw = fullW - 2 * g2.padL * cell * trim, ih2 = fullH - 2 * g2.padT * cell * trim;
    this._infField(ix, iy, iw, ih2, Math.max(3, cell * 2), (i, j, nx, ny) => 0.35 + 0.45 * d.tex(i / nx * 30, j / ny * 14), [124, 255, 155], 0.9);
    ctx.strokeStyle = "rgba(255,207,107,0.7)"; ctx.setLineDash([6, 4]); ctx.lineWidth = 1.4; ctx.strokeRect(ix, iy, iw, ih2); ctx.setLineDash([]);
    this._infText("trim pad  v:7|7  h:8|8", fx, fy - 10, "#ffcf6b", 12);

    const rx = fx + fullW + 50;
    const cubes = ["pred_curves", "gt_curves", "params_pred", "params_gt", "pixel_maps ×5"];
    cubes.forEach((c, i) => {
      const ca = this._ease(c01((s - 1.0 - i * 0.3) / 0.6));
      if (ca <= 0) return;
      this._infChip(c, rx, fy + 10 + i * 30, i < 4 ? "#7cff9b" : "#35e6d0", ca, 12);
    });
    if (s >= 3.0) {
      this._infText("large cubes → memmap on disk", rx, fy + 10 + 5 * 30 + 16, "rgba(143,176,170,0.85)", 11);
      this._infText("9 cubes saved (save_cubes=True)", rx, fy + 10 + 5 * 30 + 32, "rgba(143,176,170,0.85)", 11);
    }

    if (s >= 1.5) {
      const wins = ["hann", "triangular", "uniform"];
      wins.forEach((wk, i) => {
        const active = i === 0;
        this._infChip(wk, fx + i * 96, fy + fullH + 26, active ? "#7cff9b" : "rgba(120,200,220,0.4)", 1, 11);
      });
      this._infText("default = hann", fx, fy + fullH + 50, "#7cff9b", 11);
    }

    this._cap("Trim the padding  ·  four cubes + five metric maps stitched  ·  window = hann (default)");
  }

  _infMaps(ts, d) {
    const { ctx, w, h } = this;
    this._trTag("METRICS · maps");
    const c01 = d.c01, g = d.grid;
    const maps = [
      { n: "MSE", ramp: (v) => [Math.round(20 + v * 235), Math.round(v * 90), Math.round(40 + v * 60)] },
      { n: "MAE", ramp: (v) => [Math.round(20 + v * 235), Math.round(v * 90), Math.round(40 + v * 60)] },
      { n: "R²", ramp: (v) => [Math.round(255 - v * 200), Math.round(60 + v * 195), Math.round(60)] },
      { n: "cos", ramp: (v) => [Math.round(53 + v * 70), Math.round(180 + v * 75), 155] },
      { n: "peak", ramp: (v) => [Math.round(20 + v * 235), Math.round(v * 90), Math.round(40 + v * 60)] },
    ];
    const cell = Math.min((w - 100) / 5 / g.W, (h - 160) / g.H) * 1.0;
    const mw = g.W * cell, mh = g.H * cell;
    const gap = (w - 5 * mw) / 6;
    maps.forEach((m, i) => {
      const ma = this._ease(c01((ts - i * 0.35) / 0.7));
      if (ma <= 0) return;
      const mx = gap + i * (mw + gap), my = 64;
      ctx.save(); ctx.globalAlpha = ma;
      const valFn = (ii, jj) => {
        let v = 0.5 + 0.4 * d.tex(ii * 1.4 + i * 9, jj * 1.4);
        if (i === 2) v = 0.7 + 0.25 * d.tex(ii + 3, jj + 5);
        return v;
      };
      this._infHeat(mx, my, Math.max(2, cell), Math.floor(mw / Math.max(2, cell)), Math.floor(mh / Math.max(2, cell)), valFn, m.ramp, 0.92);
      ctx.strokeStyle = "rgba(120,200,220,0.3)"; ctx.lineWidth = 1; ctx.strokeRect(mx, my, mw, mh);
      this._infText(m.n, mx, my - 8, "#e6f7f3", 13);
      ctx.restore();
    });

    if (ts >= 3.0) {
      const da = this._ease(c01((ts - 3.0) / 1.0));
      const swX = gap + this._ease(c01((ts - 3.0) / 2.5)) * (w - 2 * gap);
      if (ts < 6.0) { ctx.strokeStyle = `rgba(124,255,155,${0.5 * da})`; ctx.lineWidth = 2; ctx.beginPath(); ctx.moveTo(swX, 60); ctx.lineTo(swX, 64 + mh + 6); ctx.stroke(); }
      this._infText("maps weighted by the same Hann window, then divided by pixel_w", gap, 64 + mh + 30, "rgba(206,228,222,0.85)", 12);
    }

    if (ts >= 6.0) {
      const stats = ["R̄² 0.94", "MSĒ 0.011"];
      stats.forEach((st, i) => this._infText(st + "  (example)", gap + i * 200, 64 + mh + 54, "#7cff9b", 12));
    }

    if (ts < 3.0) this._cap("Five per-pixel maps fall out of the stitch: MSE, MAE, R², cosine, peak error");
    else if (ts < 6.0) this._cap("The maps use the same Hann weighting, then divide by accumulated pixel weight");
    else this._cap("Mean pixel R² ≈ 0.94  ·  spatial structure of the error is now visible");
  }

  _infMetrics(ts, d) {
    const { ctx, w, h } = this;
    this._trTag("METRICS · suite");
    const c01 = d.c01, sc = d.scal;

    const tiles = [["R²", sc.r2.toFixed(3)], ["RMSE", sc.rmse.toFixed(3)], ["PSNR", sc.psnr.toFixed(1) + " dB"], ["MAE", sc.mae.toFixed(3)]];
    const tw = 150, th = 60, tg = (w - 4 * tw) / 5, ty = 56;
    tiles.forEach((t, i) => {
      const ta = this._ease(c01((ts - i * 0.25) / 0.6));
      if (ta <= 0) return;
      const tx = tg + i * (tw + tg);
      ctx.save(); ctx.globalAlpha = ta;
      ctx.fillStyle = "rgba(7,12,17,0.92)"; ctx.strokeStyle = "rgba(53,230,208,0.4)"; ctx.lineWidth = 1.3;
      ctx.beginPath();
      if (ctx.roundRect) ctx.roundRect(tx, ty, tw, th, 8); else ctx.rect(tx, ty, tw, th);
      ctx.fill(); ctx.stroke();
      this._infText(t[0], tx + 12, ty + 22, "rgba(143,176,170,0.85)", 12);
      const cnt = this._ease(c01((ts - i * 0.25) / 1.2));
      this._infText(t[1], tx + 12, ty + 46, "#e6f7f3", 18);
      this._infText("(example)", tx + tw - 58, ty + 20, "rgba(143,176,170,0.5)", 9);
      ctx.restore();
    });

    if (ts >= 3.0) {
      const sa = this._ease(c01((ts - 3.0) / 0.8));
      const axes = [["elevation", sc.ssimE], ["range", sc.ssimR], ["azimuth", sc.ssimA]];
      const bx = tg, by = 150, bw = 200;
      this._infText("SSIM", bx, by - 6, "#e6f7f3", 13);
      axes.forEach((a, i) => {
        ctx.save(); ctx.globalAlpha = sa;
        const yR = by + 14 + i * 24;
        this._infText(a[0], bx, yR, "rgba(206,228,222,0.85)", 12);
        ctx.fillStyle = "rgba(120,200,220,0.15)"; ctx.fillRect(bx + 90, yR - 9, bw, 11);
        ctx.fillStyle = "#35e6d0"; ctx.fillRect(bx + 90, yR - 9, bw * a[1] * this._ease(c01((ts - 3.0 - i * 0.2) / 0.8)), 11);
        this._infText(a[1].toFixed(2), bx + 90 + bw + 8, yR, "#35e6d0", 12);
        ctx.restore();
      });
      this._infText("adaptive win_size ≤ 7, parallel", bx, by + 14 + 3 * 24 + 4, "rgba(143,176,170,0.85)", 11);
    }

    if (ts >= 6.0) {
      const oa = this._ease(c01((ts - 6.0) / 0.8));
      const ox = w * 0.5, oy = 150;
      ctx.save(); ctx.globalAlpha = oa;
      for (let i = 0; i < 3; i++) this._infChip(`slot ${i}`, ox + i * 70, oy + 4, "#ffcf6b", 1, 11);
      this._infText(`µ ordering rate  ${sc.order.toFixed(2)}  (example)`, ox, oy + 36, "#e6f7f3", 13);
      ctx.fillStyle = "rgba(120,200,220,0.15)"; ctx.fillRect(ox, oy + 44, 220, 10);
      ctx.fillStyle = "#7cff9b"; ctx.fillRect(ox, oy + 44, 220 * sc.order, 10);
      this._infText("permutation consensus  ·  brute-force K≤4 · Hungarian K≥5", ox, oy + 74, "rgba(206,228,222,0.85)", 11);
      ctx.restore();
    }

    if (ts >= 9.0) {
      const la = this._ease(c01((ts - 9.0) / 0.8));
      const list = ["per-Gaussian µ/σ MAE & RMSE", "slot-µ mean & std", "placeholder P / R / F1", "per-elevation MAE/RMSE/R²/CE"];
      ctx.save(); ctx.globalAlpha = la * 0.7;
      this._infText("~30 metric groups → metrics.json", tg, h - 90, "#e6f7f3", 13);
      list.forEach((l, i) => this._infText("· " + l, tg, h - 68 + i * 16, "rgba(143,176,170,0.8)", 11));
      ctx.restore();
    }

    if (ts < 3.0) this._cap("Global suite on the stitched cubes: R², RMSE, PSNR, MAE");
    else if (ts < 6.0) this._cap("SSIM is measured across elevation, range and azimuth slices");
    else if (ts < 9.0) this._cap("µ-ordering rate and permutation consensus test whether slot roles stayed stable");
    else this._cap("~30 metric groups in total  ·  all written to metrics.json");
  }

  _infReport(ts, d) {
    const { ctx, w, h } = this;
    this._trTag("REPORT");
    const c01 = d.c01;
    const docX = 50, docY = 56, docW = w * 0.42, docH = h - 110;
    const da = this._ease(c01(ts / 1.0));
    ctx.save(); ctx.globalAlpha = da;
    ctx.fillStyle = "rgba(7,12,17,0.92)"; ctx.strokeStyle = "rgba(120,200,220,0.4)"; ctx.lineWidth = 1.3;
    ctx.beginPath();
    if (ctx.roundRect) ctx.roundRect(docX, docY, docW, docH, 10); else ctx.rect(docX, docY, docW, docH);
    ctx.fill(); ctx.stroke();
    ctx.fillStyle = "rgba(53,230,208,0.12)"; ctx.fillRect(docX, docY, docW, 30);
    this._infText("# TomoSAR Inference Report", docX + 14, docY + 20, "#e6f7f3", 14);
    ctx.restore();

    d.sections.forEach((sec, i) => {
      const sa = this._ease(c01((ts - 0.6 - i * 0.22) / 0.5));
      if (sa <= 0) return;
      const yR = docY + 50 + i * 26;
      ctx.save(); ctx.globalAlpha = sa;
      ctx.fillStyle = "#7cff9b"; ctx.beginPath(); ctx.arc(docX + 18, yR - 4, 3, 0, 7); ctx.fill();
      this._infText(sec, docX + 30, yR, "rgba(206,228,222,0.9)", 12);
      ctx.restore();
    });

    if (ts >= 3.0) {
      const fa = this._ease(c01((ts - 3.0) / 1.5));
      const fx = docX + docW + 40, fy = docY;
      const cols = 4, rows = 5, fw = 52, fh = 38, fg = 10;
      let n = 0;
      for (let r = 0; r < rows; r++) for (let c = 0; c < cols; c++) {
        const fa2 = this._ease(c01((ts - 3.0 - n * 0.06) / 0.5));
        if (fa2 <= 0) { n++; continue; }
        const x = fx + c * (fw + fg), y = fy + r * (fh + fg);
        ctx.save(); ctx.globalAlpha = fa2;
        ctx.fillStyle = `rgba(53,230,208,${0.08 + d.rnd(n * 7) * 0.18})`; ctx.fillRect(x, y, fw, fh);
        ctx.strokeStyle = "rgba(120,200,220,0.3)"; ctx.lineWidth = 1; ctx.strokeRect(x, y, fw, fh);
        if (n === 0) {
          const pulse = 0.5 + 0.5 * Math.sin(this.t * 4);
          ctx.fillStyle = `rgba(124,255,155,${0.2 + 0.4 * pulse})`; ctx.fillRect(x + 8, y + 8, fw - 16, fh - 16);
        }
        ctx.restore();
        n++;
      }
      this._infText("~20 figures  ·  one walk-through GIF", fx, fy + rows * (fh + fg) + 10, "rgba(143,176,170,0.85)", 11);
    }

    if (ts >= 5.5) {
      const oa = this._ease(c01((ts - 5.5) / 0.8));
      const ox = docX + docW + 40, oy = docY + 5 * (38 + 10) + 36;
      ["report.md", "metrics.json", "cubes/"].forEach((c, i) => this._infChip(c, ox + i * 110, oy, "#7cff9b", oa, 11));
    }

    if (ts < 3.0) this._cap("A 10-section Markdown report is assembled: summary, metrics, profiles, maps…");
    else if (ts < 5.5) this._cap("~20 publication figures plus volumetric walk-through GIFs");
    else this._cap("report.md · metrics.json · 9 cubes  ·  the run is fully reproducible");
  }

  /* ---------- tuning: Optuna trial search ---------- */

  _tuSetup() {
    const frac = (v) => v - Math.floor(v);
    const rnd = (i) => frac(Math.sin(i * 127.1 + 311.7) * 43758.5453);
    const c01 = (v) => Math.min(1, Math.max(0, v));
    const basin = { x: 0.66, y: 0.40 };
    const lossField = (x, y) => {
      const d2 = (x - basin.x) * (x - basin.x) + (y - basin.y) * (y - basin.y);
      const bowl = 0.62 * Math.exp(-d2 / 0.085);
      const ripple = 0.06 * Math.sin(x * 7.1 + 1.3) * Math.cos(y * 6.3 + 0.7);
      return c01(0.78 - bowl + ripple);
    };
    const trials = [];
    const N = 100;
    for (let i = 0; i < N; i++) {
      const ux = rnd(2 * i + 0.5);
      const uy = rnd(2 * i + 1.5);
      const pull = i < 8 ? 0 : this._ease((i - 8) / 64) * 0.82;
      const jx = (rnd(3 * i + 7.3) - 0.5) * 0.16;
      const jy = (rnd(3 * i + 11.7) - 0.5) * 0.16;
      const x = c01(this._lerp(ux, basin.x + jx, pull));
      const y = c01(this._lerp(uy, basin.y + jy, pull));
      const loss = c01(lossField(x, y) + (rnd(5 * i + 2.1) - 0.5) * 0.07);
      const k = 0.06 + (1 - loss) * 0.16 + rnd(7 * i + 3.3) * 0.03;
      const floor = loss * 0.92 + 0.03;
      const start = 0.86 + rnd(9 * i + 4.4) * 0.12;
      const curve = [];
      for (let e = 0; e <= 30; e++) curve.push(c01(floor + (start - floor) * Math.exp(-k * e) + (rnd(i * 53 + e * 13) - 0.5) * 0.012));
      trials.push({ x, y, loss, lr: x, wd: y, curve, k, floor, start, pruned: false, pruneEpoch: 30 });
    }
    let bestP1Idx = 8;
    for (let i = 8; i < N; i++) if (trials[i].loss < trials[bestP1Idx].loss) bestP1Idx = i;
    const liveIdx = [];
    for (let i = 0; i < N; i++) if (i !== bestP1Idx) liveIdx.push(i);
    const heroIdx = [bestP1Idx, liveIdx[10], liveIdx[24], liveIdx[40]];
    const medianAt = (epoch, set) => {
      const vals = set.map((ix) => trials[ix].curve[epoch]).sort((a, b) => a - b);
      return vals[Math.floor(vals.length / 2)];
    };
    const median = [];
    for (let e = 0; e <= 30; e++) median.push(medianAt(e, heroIdx));
    heroIdx.forEach((ix, slot) => {
      if (slot === 0) return;
      const t = trials[ix];
      let cut = 30;
      for (let e = 9; e <= 30; e++) { if (t.curve[e] > median[e] + 0.015) { cut = e; break; } }
      if (slot === 1 || slot === 2) { t.pruned = true; t.pruneEpoch = slot === 1 ? Math.min(cut, 14) : Math.min(Math.max(cut, 19), 22); }
    });
    const lrTicks = ["1e-5", "1e-4", "1e-3", "1e-2"];
    const wdTicks = ["1e-6", "1e-4", "1e-2", "1e-1"];
    const dims = [
      ["encoder_lr", "[1e-5, 1e-2]", "log", "#35e6d0"],
      ["bottleneck_lr", "[1e-5, 1e-2]", "log", "#35e6d0"],
      ["decoder_lr", "[1e-5, 1e-2]", "log", "#35e6d0"],
      ["output_head_lr", "[1e-5, 1e-2]", "log", "#35e6d0"],
      ["encoder_wd", "[1e-6, 1e-1]", "log", "#ffcf6b"],
      ["bottleneck_wd", "[1e-6, 1e-1]", "log", "#ffcf6b"],
      ["decoder_wd", "[1e-6, 1e-1]", "log", "#ffcf6b"],
      ["output_head_wd", "[1e-6, 1e-1]", "log", "#ffcf6b"],
      ["dropout", "[0.0, 0.5]", "linear", "rgba(206,228,222,0.9)"],
    ];
    const p1json = [
      ["encoder_lr", "3.1e-4"], ["bottleneck_lr", "8.7e-4"], ["decoder_lr", "1.2e-4"],
      ["output_head_lr", "4.5e-4"], ["encoder_wd", "2.0e-5"], ["dropout", "0.18"],
    ];
    const p2dims = [
      ["features", ["[32,64,128,256]", "[64,128,256,512]", "[48,96,192,384]", "[64,128,256,512,1024]"], 1],
      ["bottleneck_factor", ["1", "2", "4"], 1],
      ["activation", ["relu", "leaky_relu", "gelu", "silu"], 2],
      ["normalization", ["batch", "instance", "group"], 0],
      ["upsample_mode", ["convtranspose", "bilinear"], 0],
    ];
    this._tu = { trials, basin, bestP1Idx, heroIdx, median, lrTicks, wdTicks, dims, p1json, p2dims };
  }

  _tuLossColor(loss, alpha) {
    const a = alpha == null ? 1 : alpha;
    const hi = [255, 107, 125], mid = [255, 207, 107], lo = [124, 255, 155];
    const m = (x, p) => x === 0 ? Math.round(this._lerp(mid[p], hi[p], (loss - 0.5) / 0.5)) : Math.round(this._lerp(lo[p], mid[p], loss / 0.5));
    const s = loss >= 0.5 ? 0 : 1;
    return `rgba(${m(s, 0)},${m(s, 1)},${m(s, 2)},${a})`;
  }

  _tuColorbar(x, y, ww, alpha) {
    const ctx = this.ctx;
    ctx.save(); ctx.globalAlpha = alpha == null ? 1 : alpha;
    const steps = 40;
    for (let i = 0; i < steps; i++) {
      ctx.fillStyle = this._tuLossColor(1 - i / (steps - 1), 1);
      ctx.fillRect(x + (i / steps) * ww, y, ww / steps + 1, 8);
    }
    ctx.strokeStyle = "rgba(143,176,170,0.4)"; ctx.lineWidth = 1; ctx.strokeRect(x, y, ww, 8);
    ctx.fillStyle = "rgba(143,176,170,0.85)"; ctx.font = "11px 'IBM Plex Mono', monospace";
    ctx.fillText("val loss  high → low", x, y - 6);
    ctx.restore();
  }

  _tuChip(x, y, txt, color, alpha, size) {
    const ctx = this.ctx, fs = size || 13;
    ctx.font = `${fs}px 'IBM Plex Mono', monospace`;
    const tw = ctx.measureText(txt).width + 20;
    if (alpha != null && alpha <= 0) return tw;
    ctx.save(); ctx.globalAlpha = alpha == null ? 1 : alpha;
    const ch = fs + 11;
    ctx.fillStyle = "rgba(7,12,17,0.92)"; ctx.strokeStyle = color; ctx.lineWidth = 1.2;
    ctx.beginPath();
    if (ctx.roundRect) ctx.roundRect(x, y - ch + 8, tw, ch, 6); else ctx.rect(x, y - ch + 8, tw, ch);
    ctx.fill(); ctx.stroke();
    ctx.fillStyle = color; ctx.fillText(txt, x + 10, y + 1);
    ctx.restore();
    return tw;
  }

  _tuArrow(x1, y1, x2, y2, color) {
    const ctx = this.ctx;
    ctx.strokeStyle = color; ctx.fillStyle = color; ctx.lineWidth = 1.6;
    ctx.beginPath(); ctx.moveTo(x1, y1); ctx.lineTo(x2, y2); ctx.stroke();
    const a = Math.atan2(y2 - y1, x2 - x1);
    ctx.beginPath(); ctx.moveTo(x2, y2);
    ctx.lineTo(x2 - 7 * Math.cos(a - 0.4), y2 - 7 * Math.sin(a - 0.4));
    ctx.lineTo(x2 - 7 * Math.cos(a + 0.4), y2 - 7 * Math.sin(a + 0.4));
    ctx.closePath(); ctx.fill();
  }

  _tuJsonCard(x, y, ww, title, rows, accent, alpha) {
    const ctx = this.ctx;
    ctx.save(); ctx.globalAlpha = alpha == null ? 1 : alpha;
    const hh = 30 + rows.length * 20 + 8;
    ctx.fillStyle = "rgba(7,12,17,0.94)"; ctx.strokeStyle = accent; ctx.lineWidth = 1.3;
    ctx.beginPath();
    if (ctx.roundRect) ctx.roundRect(x, y, ww, hh, 10); else ctx.rect(x, y, ww, hh);
    ctx.fill(); ctx.stroke();
    ctx.fillStyle = accent; ctx.font = "14px 'IBM Plex Mono', monospace"; ctx.fillText(title, x + 12, y + 20);
    ctx.strokeStyle = "rgba(120,200,220,0.2)"; ctx.beginPath(); ctx.moveTo(x + 8, y + 28); ctx.lineTo(x + ww - 8, y + 28); ctx.stroke();
    ctx.font = "12px 'IBM Plex Mono', monospace";
    rows.forEach((r, i) => {
      const ry = y + 46 + i * 20;
      ctx.fillStyle = "rgba(206,228,222,0.78)"; ctx.fillText(r[0], x + 12, ry);
      ctx.fillStyle = r[2] || "rgba(124,255,155,0.92)";
      ctx.fillText(r[1], x + ww - 12 - ctx.measureText(r[1]).width, ry);
    });
    ctx.restore();
    return hh;
  }

  _tuDensity(points, bw, x) {
    let s = 0;
    for (let i = 0; i < points.length; i++) { const d = (x - points[i]) / bw; s += Math.exp(-0.5 * d * d); }
    return s / (points.length * bw * Math.sqrt(2 * Math.PI));
  }

  _tuStill() {
    const { ctx, w, h } = this;
    if (!this._tu) this._tuSetup();
    const tu = this._tu;
    const pad = { l: 46, r: 16, t: 22, b: 34 };
    const plW = w * 0.52;
    const px = (x) => pad.l + x * (plW - pad.l - pad.r);
    const py = (y) => pad.t + y * (h - pad.t - pad.b);
    ctx.strokeStyle = "rgba(120,200,220,0.08)"; ctx.lineWidth = 1;
    for (let i = 0; i <= 4; i++) { const yy = pad.t + ((h - pad.t - pad.b) / 4) * i; ctx.beginPath(); ctx.moveTo(pad.l, yy); ctx.lineTo(plW - pad.r, yy); ctx.stroke(); }
    for (let i = 0; i <= 4; i++) { const xx = pad.l + ((plW - pad.l - pad.r) / 4) * i; ctx.beginPath(); ctx.moveTo(xx, pad.t); ctx.lineTo(xx, h - pad.b); ctx.stroke(); }
    ctx.fillStyle = "rgba(143,176,170,0.8)"; ctx.font = "11px 'IBM Plex Mono', monospace";
    ctx.fillText("log₁₀ learning rate", pad.l, h - 10);
    ctx.save(); ctx.translate(pad.l - 32, pad.t + 70); ctx.rotate(-Math.PI / 2); ctx.fillText("log₁₀ weight decay", 0, 0); ctx.restore();
    for (let i = 8; i < 56; i++) {
      const t = tu.trials[i];
      ctx.beginPath(); ctx.arc(px(t.x), py(t.y), 3.4, 0, 7);
      ctx.fillStyle = this._tuLossColor(t.loss, 0.8); ctx.fill();
    }
    const b = tu.trials[tu.bestP1Idx];
    ctx.strokeStyle = "#7cff9b"; ctx.lineWidth = 1.6;
    ctx.beginPath(); ctx.arc(px(b.x), py(b.y), 9, 0, 7); ctx.stroke();
    ctx.beginPath(); ctx.moveTo(px(b.x) - 13, py(b.y)); ctx.lineTo(px(b.x) + 13, py(b.y)); ctx.moveTo(px(b.x), py(b.y) - 13); ctx.lineTo(px(b.x), py(b.y) + 13); ctx.stroke();
    ctx.fillStyle = "#7cff9b"; ctx.fillText("Phase-1 best", px(b.x) + 14, py(b.y) - 12);
    this._tuColorbar(plW - 134, h - 22, 120, 0.9);
    this._texDraw("x^{*}=\\arg\\max_x\\,\\tfrac{l(x)}{g(x)}", pad.l + 6, pad.t + 6, 15, { color: "rgba(124,255,155,0.95)" });
    const bx = plW + 24;
    ctx.fillStyle = "#e6f7f3"; ctx.font = "14px 'IBM Plex Mono', monospace"; ctx.fillText("Phase 2 · architecture", bx, pad.t + 14);
    tu.p2dims.slice(0, 3).forEach((d, i) => {
      const ry = pad.t + 50 + i * 36;
      ctx.fillStyle = "rgba(143,176,170,0.85)"; ctx.font = "11px 'IBM Plex Mono', monospace"; ctx.fillText(d[0], bx, ry - 17);
      let cx = bx;
      d[1].slice(0, 3).forEach((c, j) => { cx += this._tuChip(cx, ry, c, j === d[2] ? "#7cff9b" : "rgba(143,176,170,0.6)", 1, 11) + 6; });
    });
    const cy = h - 56;
    this._tuChip(bx, cy, "best_config.json", "#7cff9b", 1, 13);
    this._tuArrow(bx + 150, cy - 4, bx + 196, cy - 4, "#7cff9b");
    this._tuChip(bx + 200, cy, "Training", "#7cff9b", 1, 13);
    this._cap("Optuna two-phase search  ·  TPE sampler, MedianPruner  ·  best_config.json → training");
  }

  _tuPlane(px, py, plW, born, upTo, dim) {
    const { ctx, h } = this;
    const pad = { l: 46, r: 16, t: 22, b: 34 };
    ctx.save(); ctx.globalAlpha = born;
    ctx.strokeStyle = "rgba(120,200,220,0.08)"; ctx.lineWidth = 1;
    for (let i = 0; i <= 4; i++) { const yy = pad.t + ((h - pad.t - pad.b) / 4) * i; ctx.beginPath(); ctx.moveTo(pad.l, yy); ctx.lineTo(plW - pad.r, yy); ctx.stroke(); }
    for (let i = 0; i <= 4; i++) { const xx = pad.l + ((plW - pad.l - pad.r) / 4) * i; ctx.beginPath(); ctx.moveTo(xx, pad.t); ctx.lineTo(xx, h - pad.b); ctx.stroke(); }
    if (plW >= 300) {
      ctx.fillStyle = "rgba(143,176,170,0.8)"; ctx.font = "11px 'IBM Plex Mono', monospace";
      this._tu.lrTicks.forEach((tk, i) => ctx.fillText(tk, pad.l + (i / 3) * (plW - pad.l - pad.r) - 12, h - 18));
      ctx.fillText("log₁₀ learning rate", plW - pad.r - 116, h - 6);
      ctx.save(); ctx.translate(pad.l - 32, pad.t + 70); ctx.rotate(-Math.PI / 2); ctx.fillText("log₁₀ weight decay", 0, 0); ctx.restore();
    }
    ctx.restore();
  }

  _tuSpace(ts) {
    const { ctx, w, h } = this;
    const tu = this._tu;
    const plW = w * 0.56;
    const pad = { l: 46, r: 16, t: 22, b: 34 };
    const px = (x) => pad.l + x * (plW - pad.l - pad.r);
    const py = (y) => pad.t + y * (h - pad.t - pad.b);
    this._tuPlane(px, py, plW, this._ease(ts / 1.6));
    const cx = plW + 26, cw = w - cx - 18;
    const ca = this._ease((ts - 0.6) / 0.6);
    if (ca > 0) {
      ctx.save(); ctx.globalAlpha = ca;
      ctx.fillStyle = "rgba(7,12,17,0.92)"; ctx.strokeStyle = "rgba(120,200,220,0.3)"; ctx.lineWidth = 1.2;
      ctx.beginPath();
      if (ctx.roundRect) ctx.roundRect(cx - 12, pad.t - 6, cw + 24, 9 * 26 + 64, 10); else ctx.rect(cx - 12, pad.t - 6, cw + 24, 9 * 26 + 64);
      ctx.fill(); ctx.stroke();
      ctx.fillStyle = "#e6f7f3"; ctx.font = "14px 'IBM Plex Mono', monospace"; ctx.fillText("search space · Phase 1", cx, pad.t + 12);
      ctx.strokeStyle = "rgba(120,200,220,0.22)"; ctx.beginPath(); ctx.moveTo(cx - 4, pad.t + 20); ctx.lineTo(cx + cw, pad.t + 20); ctx.stroke();
      ctx.restore();
    }
    tu.dims.forEach((d, i) => {
      const ra = this._ease((ts - 1.6 - i * 0.4) / 0.5);
      if (ra <= 0) return;
      const ry = pad.t + 42 + i * 26;
      ctx.save(); ctx.globalAlpha = ra;
      ctx.beginPath(); ctx.arc(cx + 4, ry - 4, 3.2, 0, 7); ctx.fillStyle = d[3]; ctx.fill();
      ctx.fillStyle = "rgba(206,228,222,0.9)"; ctx.font = "12px 'IBM Plex Mono', monospace"; ctx.fillText(d[0], cx + 14, ry);
      ctx.fillStyle = "rgba(143,176,170,0.7)";
      ctx.fillText(d[1], cx + 134, ry); ctx.fillText(d[2], cx + cw - 8 - ctx.measureText(d[2]).width, ry);
      ctx.restore();
    });
    if (ts >= 6.5) {
      const fa = this._ease((ts - 6.5) / 0.6);
      this._tuChip(cx, pad.t + 9 * 26 + 50, "9-D space · 8 of 9 in log scale", "#ffcf6b", fa, 12);
    }
    if (ts >= 8.5) {
      const pa = 0.4 + 0.4 * Math.sin(this.t * 4);
      ctx.beginPath(); ctx.arc(px(tu.basin.x), py(tu.basin.y), 4, 0, 7); ctx.fillStyle = this._tuLossColor(0.3, pa); ctx.fill();
    }
    const ea = this._ease((ts - 2.4) / 0.7);
    if (ea > 0) {
      this._texDraw("\\log_{10}\\eta\\sim\\mathcal{U}(-5,-2)", pad.l + 8, pad.t + 8, 15, { alpha: ea, color: "rgba(53,230,208,0.92)" });
      this._texDraw("\\log_{10}\\lambda\\sim\\mathcal{U}(-6,-1)", pad.l + 8, pad.t + 34, 15, { alpha: ea, color: "rgba(255,207,107,0.92)" });
    }
    if (ts < 1.6) this._cap("Hyperparameter search  ·  Optuna study, objective = minimise validation loss");
    else if (ts < 6.5) this._cap("Phase 1 — learning + regularisation  ·  4 per-group lr, 4 per-group wd, dropout");
    else if (ts < 8.5) this._cap("Eight of nine dimensions sampled in log scale  ·  projected onto the lr–wd plane");
    else this._cap("Each point is one trial  ·  a full training run scored by its best validation loss");
  }

  _tuAccum(ts) {
    const { ctx, w, h } = this;
    const tu = this._tu;
    const plW = w;
    const pad = { l: 46, r: 16, t: 22, b: 34 };
    const px = (x) => pad.l + x * (plW - pad.l - pad.r);
    const py = (y) => pad.t + y * (h - pad.t - pad.b);
    this._tuPlane(px, py, plW, 1);
    const shown = ts < 8 ? Math.min(8, Math.floor(ts / 1.0) + 1) : ts < 10 ? 8 : Math.min(20, 8 + Math.floor((ts - 10) / 0.5));
    for (let i = 0; i < shown; i++) {
      const t = tu.trials[i];
      const pop = this._ease(i < 8 ? (ts - i * 1.0) / 0.5 : (ts - 10 - (i - 8) * 0.5) / 0.4);
      if (pop <= 0) continue;
      const r = (3.2 + (1 - t.loss) * 2.4) * pop;
      ctx.beginPath(); ctx.arc(px(t.x), py(t.y), r, 0, 7); ctx.fillStyle = this._tuLossColor(t.loss, 0.85); ctx.fill();
      if (pop < 1) { ctx.strokeStyle = this._tuLossColor(t.loss, (1 - pop) * 0.6); ctx.lineWidth = 1.2; ctx.beginPath(); ctx.arc(px(t.x), py(t.y), r + 6 * (1 - pop), 0, 7); ctx.stroke(); }
    }
    if (ts >= 8 && ts < 10.5) {
      const sw = this._ease((ts - 8) / 1.0);
      ctx.strokeStyle = "rgba(255,207,107,0.7)"; ctx.setLineDash([5, 4]); ctx.lineWidth = 1.4;
      const gx = pad.l + sw * (plW - pad.l - pad.r);
      ctx.beginPath(); ctx.moveTo(gx, pad.t); ctx.lineTo(gx, h - pad.b); ctx.stroke(); ctx.setLineDash([]);
      ctx.fillStyle = "rgba(255,207,107,0.9)"; ctx.font = "11px 'IBM Plex Mono', monospace"; ctx.fillText("warmup complete", Math.max(pad.l + 4, gx - 110), pad.t + 14);
    }
    this._tuChip(pad.l + 4, pad.t + 16, `trial ${Math.min(shown, 100)} / 100`, "#35e6d0", 1, 12);
    this._tuColorbar(w - 168, h - 26, 130, 1);
    if (ts < 8) this._cap("First 8 trials are random  ·  TPESampler warms up before it models  (n_startup_trials = 8)");
    else if (ts < 10) this._cap("8 random trials done  ·  enough history to build a model");
    else this._cap("Trial 9 onward  ·  the sampler starts to exploit what it has learned");
  }

  _tuTpe(ts) {
    const { ctx, w, h } = this;
    const tu = this._tu;
    const pad = { l: 46, r: 16, t: 22, b: 34 };
    const px = (x) => pad.l + x * (w - pad.l - pad.r);
    const axisY = h * 0.42;
    const slide = this._ease(ts / 3.0);
    const set = [];
    for (let i = 0; i < 20; i++) set.push(tu.trials[i]);
    const lossThr = 0.42;
    const good = [], bad = [];
    set.forEach((t) => (t.loss <= lossThr ? good : bad).push(t));
    ctx.strokeStyle = "rgba(120,200,220,0.25)"; ctx.lineWidth = 1.2;
    ctx.beginPath(); ctx.moveTo(pad.l, axisY); ctx.lineTo(w - pad.r, axisY); ctx.stroke();
    ctx.fillStyle = "rgba(143,176,170,0.8)"; ctx.font = "11px 'IBM Plex Mono', monospace";
    tu.lrTicks.forEach((tk, i) => ctx.fillText(tk, pad.l + (i / 3) * (w - pad.l - pad.r) - 12, axisY + 18));
    ctx.fillText("log₁₀ learning rate", w - pad.r - 116, h - 10);
    set.forEach((t) => {
      const ty = this._lerp(pad.t + t.y * (h - pad.t - pad.b), axisY - 4, slide);
      const isGood = t.loss <= lossThr;
      const lift = ts >= 3 && ts < 7 ? this._ease((ts - 3) / 2.0) : ts >= 7 ? 1 : 0;
      const yy = isGood ? ty - lift * 18 : ty;
      const dim = !isGood && ts >= 3 ? 1 - 0.5 * lift : 1;
      ctx.beginPath(); ctx.arc(px(t.x), yy, 3.4, 0, 7);
      ctx.fillStyle = isGood && ts >= 3 ? `rgba(124,255,155,${0.85 * dim})` : this._tuLossColor(t.loss, 0.7 * dim);
      ctx.fill();
    });
    if (ts >= 7) {
      const da = this._ease((ts - 7) / 1.5);
      const bw = 0.05;
      const lpts = good.map((t) => t.x), gpts = bad.map((t) => t.x);
      let maxd = 0;
      for (let i = 0; i <= 60; i++) { const x = i / 60; maxd = Math.max(maxd, this._tuDensity(lpts, bw, x), this._tuDensity(gpts, bw, x)); }
      const dh = 78;
      const dy = (v) => axisY + 28 + dh - (v / maxd) * dh;
      ctx.save(); ctx.globalAlpha = da;
      ctx.beginPath();
      for (let i = 0; i <= 60; i++) { const x = i / 60, sx = px(x), sy = dy(this._tuDensity(gpts, bw, x)); i ? ctx.lineTo(sx, sy) : ctx.moveTo(sx, sy); }
      ctx.strokeStyle = "rgba(143,176,170,0.7)"; ctx.lineWidth = 1.2; ctx.stroke();
      ctx.beginPath();
      for (let i = 0; i <= 60; i++) { const x = i / 60, sx = px(x), sy = dy(this._tuDensity(lpts, bw, x)); i ? ctx.lineTo(sx, sy) : ctx.moveTo(sx, sy); }
      ctx.lineTo(px(1), dy(0)); ctx.lineTo(px(0), dy(0)); ctx.closePath();
      ctx.fillStyle = "rgba(53,230,208,0.10)"; ctx.fill();
      ctx.beginPath();
      for (let i = 0; i <= 60; i++) { const x = i / 60, sx = px(x), sy = dy(this._tuDensity(lpts, bw, x)); i ? ctx.lineTo(sx, sy) : ctx.moveTo(sx, sy); }
      ctx.strokeStyle = "rgba(53,230,208,0.9)"; ctx.lineWidth = 2; ctx.stroke();
      ctx.fillStyle = "rgba(53,230,208,0.9)"; ctx.font = "12px 'IBM Plex Mono', monospace"; ctx.fillText("l(lr) good", px(0.78), axisY + 44);
      ctx.fillStyle = "rgba(143,176,170,0.8)"; ctx.fillText("g(lr) rest", px(0.12), axisY + 44);
      ctx.restore();
      this._texDraw("l(x)=p(x\\mid y<y^{*})", pad.l + 4, pad.t + 4, 14, { alpha: da, color: "rgba(53,230,208,0.92)" });
      this._texDraw("g(x)=p(x\\mid y\\geq y^{*})", pad.l + 4, pad.t + 28, 14, { alpha: da, color: "rgba(143,176,170,0.9)" });
      if (ts >= 11.5) {
        const sel = this._ease((ts - 11.5) / 2.0);
        let bx = 0.5, bv = -1;
        for (let i = 0; i <= 60; i++) { const x = i / 60, r = this._tuDensity(lpts, bw, x) / (this._tuDensity(gpts, bw, x) + 0.4); if (r > bv) { bv = r; bx = x; } }
        const cand = px(this._lerp(0.2, bx, sel));
        this._texDraw("x^{*}=\\arg\\max_x\\,\\frac{l(x)}{g(x)}", w - pad.r - 4, pad.t + 4, 16, { align: "right", alpha: sel, color: "rgba(124,255,155,0.95)" });
        ctx.strokeStyle = "rgba(53,230,208,0.85)"; ctx.lineWidth = 1.4; ctx.setLineDash([4, 3]);
        ctx.beginPath(); ctx.moveTo(cand, axisY - 26); ctx.lineTo(cand, dy(0)); ctx.stroke(); ctx.setLineDash([]);
        if (sel >= 0.95) {
          ctx.beginPath(); ctx.arc(cand, axisY - 4, 5, 0, 7); ctx.fillStyle = "#7cff9b"; ctx.fill();
          ctx.strokeStyle = "#35e6d0"; ctx.lineWidth = 1.6; ctx.beginPath(); ctx.arc(cand, axisY - 4, 9, 0, 7); ctx.stroke();
          ctx.fillStyle = "rgba(143,176,170,0.55)"; ctx.font = "11px 'IBM Plex Mono', monospace"; ctx.fillText("random would spray ↔", px(0.12), axisY - 30);
        }
      }
    }
    if (ts >= 15.5) {
      const za = this._ease((ts - 15.5) / 1.0);
      this._tuChip(pad.l + 4, h - 16, "multivariate = True · seed = 42", "#35e6d0", za, 11);
    }
    if (ts < 3) this._cap("TPE looks at every completed trial and its loss");
    else if (ts < 7) this._cap("Split the trials by loss  ·  the best fraction (good) versus the rest (bad)");
    else if (ts < 11.5) this._cap("Fit a density to each group  ·  l(lr) for good trials, g(lr) for the rest");
    else if (ts < 15.5) this._cap("Draw the next lr where good is likely and bad is not  ·  this is TPE, not random search");
    else this._cap("Repeated each trial  ·  the search concentrates where the model predicts low loss");
  }

  _tuTrial(ts) {
    const { ctx, w, h } = this;
    const tu = this._tu;
    const pad = { l: 56, r: 18, t: 24, b: 38 };
    const ex = (e) => pad.l + (e / 30) * (w - pad.l - pad.r);
    const ly = (v) => pad.t + (1 - Math.min(1, Math.max(0, v))) * (h - pad.t - pad.b);
    const zoom = this._ease(ts / 2.5);
    ctx.save(); ctx.globalAlpha = zoom;
    ctx.strokeStyle = "rgba(120,200,220,0.08)"; ctx.lineWidth = 1;
    for (let i = 0; i <= 4; i++) { const yy = pad.t + ((h - pad.t - pad.b) / 4) * i; ctx.beginPath(); ctx.moveTo(pad.l, yy); ctx.lineTo(w - pad.r, yy); ctx.stroke(); }
    ctx.fillStyle = "rgba(143,176,170,0.8)"; ctx.font = "11px 'IBM Plex Mono', monospace";
    for (let e = 0; e <= 30; e += 6) ctx.fillText(String(e), ex(e) - 4, h - 22);
    ctx.fillText("epoch  0..30", w - pad.r - 92, h - 8);
    ctx.save(); ctx.translate(pad.l - 40, pad.t + 50); ctx.rotate(-Math.PI / 2); ctx.fillText("val loss", 0, 0); ctx.restore();
    ctx.restore();
    const hero = tu.heroIdx;
    const warm = ts >= 6.5;
    if (warm) {
      const wa = this._ease((ts - 6.5) / 1.0);
      ctx.save(); ctx.globalAlpha = 0.5 * wa; ctx.fillStyle = "rgba(255,207,107,0.10)"; ctx.fillRect(pad.l, pad.t, ex(8) - pad.l, h - pad.t - pad.b); ctx.restore();
      ctx.fillStyle = `rgba(255,207,107,${0.8 * wa})`; ctx.font = "11px 'IBM Plex Mono', monospace"; ctx.fillText("warmup (n_warmup_steps = 8)", pad.l + 4, pad.t + 14);
    }
    const drawCurve = (ix, slot) => {
      const t = tu.trials[ix];
      const lead = slot === 0 ? (ts - 2.5) / 4.0 : (ts - 6.5) / 3.5;
      const reveal = Math.max(0, Math.min(1, lead));
      let last = t.pruned ? t.pruneEpoch : 30;
      if (slot >= 1 && ts < 10) last = 30;
      const upTo = Math.max(1, Math.round(reveal * last));
      const pruneNow = t.pruned && ts >= (slot === 1 ? 10 : 15);
      const drawEnd = pruneNow ? Math.min(upTo, t.pruneEpoch) : upTo;
      ctx.beginPath();
      for (let e = 0; e <= drawEnd; e++) { const sx = ex(e), sy = ly(t.curve[e]); e ? ctx.lineTo(sx, sy) : ctx.moveTo(sx, sy); }
      if (slot === 0) { ctx.strokeStyle = "rgba(53,230,208,0.9)"; ctx.lineWidth = 2.2; ctx.shadowColor = "rgba(53,230,208,0.5)"; ctx.shadowBlur = 6; }
      else { ctx.strokeStyle = pruneNow ? "rgba(255,107,125,0.85)" : "rgba(143,176,170,0.65)"; ctx.lineWidth = 1.3; }
      ctx.stroke(); ctx.shadowBlur = 0;
      if (slot === 0 && reveal >= 1) {
        let mi = 0; for (let e = 1; e <= 30; e++) if (t.curve[e] < t.curve[mi]) mi = e;
        ctx.beginPath(); ctx.arc(ex(mi), ly(t.curve[mi]), 4, 0, 7); ctx.fillStyle = "#7cff9b"; ctx.fill();
        ctx.fillStyle = "rgba(124,255,155,0.9)"; ctx.font = "11px 'IBM Plex Mono', monospace"; ctx.fillText("best epoch", ex(mi) + 6, ly(t.curve[mi]) - 6);
      }
      if (pruneNow && drawEnd >= t.pruneEpoch) {
        const sx = ex(t.pruneEpoch), sy = ly(t.curve[t.pruneEpoch]);
        ctx.strokeStyle = "#ff6b7d"; ctx.lineWidth = 1.6;
        ctx.beginPath(); ctx.moveTo(sx - 4, sy - 4); ctx.lineTo(sx + 4, sy + 4); ctx.moveTo(sx + 4, sy - 4); ctx.lineTo(sx - 4, sy + 4); ctx.stroke();
        ctx.fillStyle = "rgba(255,107,125,0.9)"; ctx.font = "11px 'IBM Plex Mono', monospace"; ctx.fillText(`pruned @ epoch ${t.pruneEpoch}  (example)`, Math.min(sx + 8, w - 200), sy - 12);
        ctx.strokeStyle = "rgba(255,107,125,0.3)"; ctx.lineWidth = 1; ctx.setLineDash([2, 3]); ctx.beginPath();
        for (let e = t.pruneEpoch; e <= 30; e++) { const xx = ex(e), yy = ly(t.curve[e]); e === t.pruneEpoch ? ctx.moveTo(xx, yy) : ctx.lineTo(xx, yy); }
        ctx.stroke(); ctx.setLineDash([]);
      }
    };
    drawCurve(hero[0], 0);
    if (ts >= 6.5) { drawCurve(hero[1], 1); drawCurve(hero[2], 2); drawCurve(hero[3], 3); }
    if (ts >= 6.5) {
      const ma = this._ease((ts - 6.5) / 1.5);
      ctx.save(); ctx.globalAlpha = ma;
      ctx.strokeStyle = "rgba(255,207,107,0.9)"; ctx.lineWidth = 1.4; ctx.setLineDash([6, 4]);
      ctx.beginPath();
      for (let e = 8; e <= 30; e++) { const sx = ex(e), sy = ly(tu.median[e]); e === 8 ? ctx.moveTo(sx, sy) : ctx.lineTo(sx, sy); }
      ctx.stroke(); ctx.setLineDash([]);
      ctx.fillStyle = "rgba(255,207,107,0.9)"; ctx.font = "11px 'IBM Plex Mono', monospace"; ctx.fillText("running median", ex(16), ly(tu.median[16]) + 18);
      ctx.restore();
      this._texDraw("\\mathrm{prune\\ if}\\;\\;y_t>\\mathrm{median}\\{y_t^{(i)}\\}", w - pad.r - 4, pad.t + 4, 15, { align: "right", alpha: ma, color: "rgba(255,207,107,0.92)" });
    }
    if (ts >= 4 && ts < 6.5) {
      ctx.fillStyle = "rgba(143,176,170,0.85)"; ctx.font = "11px 'IBM Plex Mono', monospace"; ctx.fillText("early stopping · patience = 8", ex(20), pad.t + 14);
    }
    if (ts < 2.5) this._cap("Open one trial  ·  it is a full 30-epoch training run of the model");
    else if (ts < 6.5) this._cap("Validation loss reported each epoch  ·  the score is its best epoch  (early-stop patience 8)");
    else if (ts < 10) this._cap("MedianPruner watches every trial's reported loss  ·  compares against the running median");
    else if (ts < 15) this._cap("Loss above the median after warmup is pruned mid-training  ·  remaining epochs never run");
    else if (ts < 18) this._cap("Pruning is per-epoch and median-based  ·  not a fixed rate  ·  it makes 100-trial searches affordable");
    else this._cap("Back to the study  ·  red = pruned early, kept = ran to completion or early-stop");
  }

  _tuParallel(ts) {
    const { ctx, w, h } = this;
    const lanes = 4;
    const lx = 40, lw = w * 0.52;
    const laneH = (h - 70) / lanes;
    const dbx = lx + lw + 60, dby = h * 0.34, dbw = 96, dbh = h * 0.36;
    let inStudy = 0;
    for (let g = 0; g < lanes; g++) {
      const ly = 40 + g * laneH;
      const born = this._ease(ts / 2.0);
      ctx.save(); ctx.globalAlpha = born;
      ctx.strokeStyle = "rgba(120,200,220,0.2)"; ctx.lineWidth = 1.1;
      ctx.beginPath(); ctx.moveTo(lx, ly + laneH * 0.5); ctx.lineTo(lx + lw, ly + laneH * 0.5); ctx.stroke();
      ctx.fillStyle = "rgba(206,228,222,0.85)"; ctx.font = "12px 'IBM Plex Mono', monospace"; ctx.fillText(`GPU ${g} · 25 trials`, lx, ly + 8);
      ctx.restore();
      if (ts >= 2.5) {
        const rate = 0.55 + g * 0.13;
        const nchip = Math.min(8, Math.floor((ts - 2.5) * rate));
        for (let c = 0; c < nchip; c++) {
          const cx = lx + 96 + c * ((lw - 96) / 8);
          const cy = ly + laneH * 0.5;
          ctx.beginPath(); ctx.arc(cx, cy, 4, 0, 7); ctx.fillStyle = "rgba(53,230,208,0.8)"; ctx.fill();
          inStudy++;
          if (c === nchip - 1 && ts >= 2.5) { this._tuArrow(cx, cy, dbx, dby + dbh * 0.5, "rgba(53,230,208,0.4)"); }
        }
      }
    }
    ctx.fillStyle = "rgba(7,12,17,0.94)"; ctx.strokeStyle = "rgba(124,255,155,0.6)"; ctx.lineWidth = 1.4;
    ctx.beginPath();
    if (ctx.roundRect) ctx.roundRect(dbx, dby, dbw, dbh, 8); else ctx.rect(dbx, dby, dbw, dbh);
    ctx.fill(); ctx.stroke();
    ctx.fillStyle = "rgba(124,255,155,0.9)"; ctx.font = "12px 'IBM Plex Mono', monospace"; ctx.fillText("optuna.db", dbx + 8, dby + 22); ctx.fillText("(SQLite)", dbx + 8, dby + 40);
    ctx.fillStyle = "rgba(206,228,222,0.85)"; ctx.fillText(`trials: ${Math.min(inStudy, 100)}`, dbx + 8, dby + dbh - 12);
    if (ts >= 7.0 && ts < 10.5) {
      const ph = this._ease((ts - 7.0) / 1.5);
      const sx = lx + lw * 0.5, sy = 40 + 1 * laneH + laneH * 0.5;
      const tx = this._lerp(sx, dbx, ph), ty = this._lerp(sy, dby + dbh * 0.5, ph);
      ctx.beginPath(); ctx.arc(tx, ty, 4, 0, 7); ctx.strokeStyle = "rgba(255,207,107,0.9)"; ctx.lineWidth = 1.4; ctx.setLineDash([3, 3]); ctx.stroke(); ctx.setLineDash([]);
      ctx.fillStyle = "rgba(255,207,107,0.85)"; ctx.font = "11px 'IBM Plex Mono', monospace"; ctx.fillText("phantom loss", tx + 6, ty - 6);
    }
    if (ts < 2.5) this._cap("100 trials are split across 4 GPUs  ·  ~25 trials per worker");
    else if (ts < 7) this._cap("Four worker subprocesses, one shared SQLite study  (load_if_exists)");
    else if (ts < 10.5) this._cap("constant_liar posts a placeholder loss for running trials  ·  workers explore different regions");
    else this._cap("The study grows as all four workers report  ·  the sampler sees everyone's results");
  }

  _tuHandoff(ts) {
    const { ctx, w, h } = this;
    const tu = this._tu;
    const pad = { l: 46, r: 16, t: 22, b: 34 };
    const shrink = ts >= 5 ? this._ease((ts - 5) / 2.0) : 0;
    const plW = this._lerp(w * 0.52, 150, shrink);
    const px = (x) => pad.l + x * (plW - pad.l - pad.r);
    const py = (y) => pad.t + y * (this._lerp(h - pad.t - pad.b, 60, shrink));
    this._tuPlane(px, py, plW, 1 - shrink * 0.6);
    for (let i = 8; i < 56; i++) {
      const t = tu.trials[i];
      ctx.beginPath(); ctx.arc(px(t.x), py(t.y), 3.2 * (1 - shrink * 0.4), 0, 7); ctx.fillStyle = this._tuLossColor(t.loss, (0.8) * (1 - shrink * 0.5)); ctx.fill();
    }
    const b = tu.trials[tu.bestP1Idx];
    const halo = 0.5 + 0.5 * Math.sin(this.t * 4);
    ctx.strokeStyle = `rgba(124,255,155,${0.6 + 0.4 * halo})`; ctx.lineWidth = 1.6;
    ctx.beginPath(); ctx.arc(px(b.x), py(b.y), 9, 0, 7); ctx.stroke();
    ctx.beginPath(); ctx.moveTo(px(b.x) - 13, py(b.y)); ctx.lineTo(px(b.x) + 13, py(b.y)); ctx.moveTo(px(b.x), py(b.y) - 13); ctx.lineTo(px(b.x), py(b.y) + 13); ctx.stroke();
    if (ts < 2.5) { ctx.fillStyle = "#7cff9b"; ctx.font = "11px 'IBM Plex Mono', monospace"; ctx.fillText("Phase-1 best · trial 73 · val_loss 0.0412 (example)", Math.min(px(b.x) + 14, w - 320), py(b.y) - 12); }
    if (ts >= 2.5 && ts < 6) {
      const ja = this._ease((ts - 2.5) / 1.0);
      this._tuJsonCard(w * 0.5, pad.t + 10, w * 0.46, "phase1_best.json", tu.p1json.map((r) => [r[0], r[1], "rgba(124,255,155,0.9)"]), "#7cff9b", ja);
    }
    if (ts >= 5) {
      const fa = this._ease((ts - 5) / 1.0);
      this._tuChip(10, 16, "Phase-1 best · FROZEN ⊟", "#ffcf6b", fa, 12);
    }
    if (ts >= 7) {
      const ba = this._ease((ts - 7) / 0.8);
      ctx.save(); ctx.globalAlpha = ba;
      const bx = w * 0.5, by = pad.t + 24;
      ctx.fillStyle = "#e6f7f3"; ctx.font = "14px 'IBM Plex Mono', monospace"; ctx.fillText("Phase 2 · architecture", bx, by - 4);
      tu.p2dims.forEach((d, i) => {
        const ry = by + 32 + i * 36;
        ctx.fillStyle = "rgba(143,176,170,0.85)"; ctx.font = "11px 'IBM Plex Mono', monospace"; ctx.fillText(d[0], bx, ry - 17);
        let cx = bx;
        const lock = ts >= 11;
        d[1].forEach((c, j) => {
          const chosen = j === d[2];
          const col = chosen && (lock || Math.floor(this.t * 3) % d[1].length === j) ? "#7cff9b" : "rgba(143,176,170,0.55)";
          const lbl = c.length > 14 ? c.slice(0, 13) + "…" : c;
          const cw2 = this._tuChip(cx, ry, lbl, col, 0, 11);
          if (cx + cw2 > w - 24) return;
          cx += this._tuChip(cx, ry, lbl, col, 1, 11) + 5;
        });
      });
      ctx.restore();
    }
    if (ts < 2.5) this._cap("Phase 1 done  ·  pick the trial with the lowest validation loss");
    else if (ts < 5) this._cap("Best learning + regularisation params are decoded and saved to phase1_best.json");
    else if (ts < 7) this._cap("These params are now frozen  ·  Phase 2 holds them fixed and searches architecture");
    else if (ts < 11) this._cap("Phase 2 — architecture search  ·  5 categorical choices, same TPE + pruner");
    else this._cap("Phase-2 best architecture found  ·  trial 88 · val_loss 0.0389  (example)");
  }

  _tuExport(ts) {
    const { ctx, w, h } = this;
    const tu = this._tu;
    const merge = this._ease(ts / 3.0);
    const cx = w * 0.30, cy = h * 0.22;
    if (ts < 3) {
      this._tuChip(this._lerp(20, cx - 60, merge), this._lerp(h * 0.3, cy, merge), "phase1_best", "#ffcf6b", 1 - merge * 0.5, 12);
      this._tuChip(this._lerp(w - 160, cx + 60, merge), this._lerp(h * 0.6, cy, merge), "phase2_best", "#7cff9b", 1 - merge * 0.5, 12);
    }
    const ja = ts >= 1.5 ? this._ease((ts - 1.5) / 1.0) : 0;
    if (ja > 0) {
      this._tuJsonCard(cx - 110, cy, 240, "best_config.json", [
        ["model", "UNet", "rgba(124,255,155,0.9)"],
        ["phase1_val_loss", "0.0412", "rgba(143,176,170,0.8)"],
        ["phase2_val_loss", "0.0389", "rgba(143,176,170,0.8)"],
        ["params", "{ lr, wd, features… }", "rgba(206,228,222,0.8)"],
      ], "#7cff9b", ja);
    }
    if (ts >= 3) {
      const aa = this._ease((ts - 3) / 1.0);
      const tnx = w * 0.74, tny = cy + 50;
      this._tuArrow(cx + 134, cy + 50, tnx - 10, tny, `rgba(124,255,155,${aa})`);
      const pulse = ts >= 4 ? 0.5 + 0.5 * Math.sin(this.t * 4) : 0;
      ctx.save(); ctx.globalAlpha = aa;
      ctx.fillStyle = "rgba(7,12,17,0.94)"; ctx.strokeStyle = `rgba(124,255,155,${0.6 + 0.4 * pulse})`; ctx.lineWidth = 1.5;
      ctx.beginPath();
      if (ctx.roundRect) ctx.roundRect(tnx, tny - 22, 130, 44, 9); else ctx.rect(tnx, tny - 22, 130, 44);
      ctx.fill(); ctx.stroke();
      ctx.fillStyle = "#7cff9b"; ctx.font = "13px 'IBM Plex Mono', monospace"; ctx.fillText("Training", tnx + 14, tny - 2); ctx.fillText("pipeline", tnx + 14, tny + 14);
      ctx.restore();
    }
    if (ts >= 5.5) {
      const sa = this._ease((ts - 5.5) / 1.0);
      this._tuChip(cx - 110, h - 70, "tuning_results.json · status DONE · p1 0.0412 · p2 0.0389", "#35e6d0", sa, 11);
    }
    if (ts >= 7) {
      const ra = this._ease((ts - 7) / 0.8);
      this._tuChip(cx - 110, h - 36, "100 trials × 2 phases × 10 models · pruned trials stop early", "rgba(206,228,222,0.9)", ra, 12);
    }
    if (ts < 3) this._cap("Phase-1 and Phase-2 bests merge into best_config.json");
    else if (ts < 5.5) this._cap("best_config.json is what the Training pipeline consumes  ·  tuned, ready to train");
    else if (ts < 7) this._cap("A tuning_results.json summary is written per model");
    else this._cap("The whole study runs for every model in the registry");
  }

  _tuning() {
    if (!this._tu) this._tuSetup();
    if (this.reduced && !this.manual) { this._tuStill(); return; }
    this._dispatch("tuning");
  }

  _generic() { this._cap("Process"); }
}

window.ProcessAnimator = ProcessAnimator;
