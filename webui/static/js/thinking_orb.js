"use strict";

class OrbClock {
  static now() {
    return performance.now() / 1000;
  }
}

class OrbSubstrate {
  static isDark(element) {
    return getComputedStyle(element).getPropertyValue("--orb-theme").trim() === "dark";
  }
}

class ThinkingOrbElement extends HTMLElement {
  static STATES = ["working", "searching", "solving", "listening", "connecting", "weaving", "composing", "breathing", "shaping"];
  static SIZES  = [20, 64];
  static LABELS = { working: "Working", searching: "Searching", solving: "Solving", listening: "Listening", connecting: "Connecting", weaving: "Weaving", composing: "Composing", breathing: "Thinking", shaping: "Shaping" };

  static get observedAttributes() {
    return ["state", "size", "theme", "speed", "paused"];
  }

  constructor() {
    super();
    this._canvas  = document.createElement("canvas");
    this._raf     = null;
    this._visible = true;
    this._loop    = this._loop.bind(this);
    this._onVis   = this._onVis.bind(this);
  }

  get state() {
    const state = this.getAttribute("state") || "working";
    if (!ThinkingOrbElement.STATES.includes(state)) throw new Error(`thinking-orb: unknown state "${state}"`);
    return state;
  }

  get size() {
    const size = Number(this.getAttribute("size") || 20);
    if (!ThinkingOrbElement.SIZES.includes(size)) throw new Error(`thinking-orb: size must be 20 or 64, got "${this.getAttribute("size")}"`);
    return size;
  }

  get dark() {
    const theme = this.getAttribute("theme") || "auto";
    if (theme === "dark") return true;
    if (theme === "light") return false;
    return OrbSubstrate.isDark(this);
  }

  connectedCallback() {
    if (!this._canvas.isConnected) this.appendChild(this._canvas);
    if (!this.hasAttribute("aria-hidden")) {
      this.setAttribute("role", "img");
      if (!this.hasAttribute("aria-label")) this.setAttribute("aria-label", ThinkingOrbElement.LABELS[this.state]);
    }
    this._io = new IntersectionObserver(([entry]) => {
      this._visible = entry.isIntersecting;
      this._sync();
    });
    this._io.observe(this);
    document.addEventListener("visibilitychange", this._onVis);
    this._configure();
    this._startCycle();
  }

  disconnectedCallback() {
    this._stop();
    clearInterval(this._cycleTimer);
    if (this._io) this._io.disconnect();
    document.removeEventListener("visibilitychange", this._onVis);
  }

  _startCycle() {
    const seconds = Number(this.getAttribute("cycle") || 0);
    if (seconds > 0 && !window.REDUCED_MOTION) this._cycleTimer = setInterval(() => this._fadeToNext(), seconds * 1000);
  }

  _fadeToNext() {
    if (document.visibilityState === "hidden" || !this._visible) return;
    this.classList.add("is-fading");
    setTimeout(() => {
      const states = ThinkingOrbElement.STATES;
      this.setAttribute("state", states[(states.indexOf(this.state) + 1) % states.length]);
      this.classList.remove("is-fading");
    }, 260);
  }

  attributeChangedCallback() {
    if (this.isConnected) this._configure();
  }

  _configure() {
    const size  = this.size;
    const dpr   = Math.min(2, window.devicePixelRatio || 1);
    const p     = window.ThinkingOrbsEngine.resolvePreset(this.state, size);
    this._dpr   = dpr;
    this._px    = size;
    this._draw  = window.ThinkingOrbsEngine.MODE_DRAWS[p.mode];
    this._opts  = p.opts;
    this._speed = p.speed * Number(this.getAttribute("speed") || 1);
    this._ink   = this.dark;
    this._canvas.width  = Math.round(size * dpr);
    this._canvas.height = Math.round(size * dpr);
    this._canvas.style.width  = `${size}px`;
    this._canvas.style.height = `${size}px`;
    this._ctx = this._canvas.getContext("2d");
    this._frame(window.REDUCED_MOTION ? 0.6 : OrbClock.now() * this._speed);
    this._sync();
  }

  _frame(t) {
    this._ctx.setTransform(this._dpr, 0, 0, this._dpr, 0, 0);
    this._ctx.clearRect(0, 0, this._px, this._px);
    this._draw(this._ctx, this._px, t, this._ink, this._opts);
  }

  _loop() {
    this._frame(OrbClock.now() * this._speed);
    this._raf = requestAnimationFrame(this._loop);
  }

  _onVis() {
    this._sync();
  }

  _stop() {
    if (this._raf != null) cancelAnimationFrame(this._raf);
    this._raf = null;
  }

  _sync() {
    const run = this.isConnected && this._visible && document.visibilityState !== "hidden" && !this.hasAttribute("paused") && !window.REDUCED_MOTION;
    if (run && this._raf == null) this._raf = requestAnimationFrame(this._loop);
    if (!run) this._stop();
  }
}

class BackdropOrb {
  static HOLD_S  = 14;
  static FADE_S  = 2.4;
  static SPEED   = 0.45;
  static SKIP    = ["working", "shaping"];
  static DENSITY = { composing: 2 };
  static DOT     = 0.6;
  static FRAME_S = 1 / 30;

  constructor(canvas) {
    this.canvas  = canvas;
    this.ctx     = canvas.getContext("2d");
    this.states  = ThinkingOrbElement.STATES.filter((state) => !BackdropOrb.SKIP.includes(state));
    this.presets = Object.fromEntries(this.states.map((state) => [state, this._preset(state)]));
    this.index   = Math.floor(Math.random() * this.states.length);
    this.since   = OrbClock.now();
    this.last    = 0;
    this._loop   = this._loop.bind(this);

    new ResizeObserver(() => this._measure()).observe(canvas);
    this._measure();

    if (window.REDUCED_MOTION) this._draw(this.since);
    else requestAnimationFrame(this._loop);
  }

  _preset(state) {
    const engine = window.ThinkingOrbsEngine;
    const base   = engine.resolvePreset(state, 64);
    const opts   = engine.scaleRadii(engine.scaleCounts(base.opts, BackdropOrb.DENSITY[state] || 3), BackdropOrb.DOT);
    return { draw: engine.MODE_DRAWS[base.mode], speed: base.speed * BackdropOrb.SPEED, opts };
  }

  _measure() {
    this.dpr = Math.min(2, window.devicePixelRatio || 1);
    this.px  = this.canvas.clientWidth;
    this.ink = OrbSubstrate.isDark(this.canvas);
    this.canvas.width  = Math.round(this.px * this.dpr);
    this.canvas.height = Math.round(this.px * this.dpr);
    if (window.REDUCED_MOTION) this._draw(this.since);
  }

  _advance(now) {
    if (now - this.since < BackdropOrb.HOLD_S + BackdropOrb.FADE_S) return;
    this.index = (this.index + 1) % this.states.length;
    this.since = now;
  }

  _paint(state, now, alpha) {
    const preset = this.presets[state];
    this.ctx.globalAlpha = alpha;
    preset.draw(this.ctx, this.px, window.REDUCED_MOTION ? 0.6 : now * preset.speed, this.ink, preset.opts);
  }

  _draw(now) {
    const f    = Math.min(1, Math.max(0, (now - this.since - BackdropOrb.HOLD_S) / BackdropOrb.FADE_S));
    const mix  = f * f * (3 - 2 * f);
    const next = this.states[(this.index + 1) % this.states.length];

    this.ctx.setTransform(this.dpr, 0, 0, this.dpr, 0, 0);
    this.ctx.clearRect(0, 0, this.px, this.px);
    if (mix < 1) this._paint(this.states[this.index], now, 1 - mix);
    if (mix > 0) this._paint(next, now, mix);
    this.ctx.globalAlpha = 1;
  }

  _loop() {
    const now = OrbClock.now();
    if (now - this.last >= BackdropOrb.FRAME_S) {
      this.last = now;
      this._advance(now);
      this._draw(now);
    }
    requestAnimationFrame(this._loop);
  }
}

class ThinkingOrb {
  static html(state, size = 20, label = "") {
    const aria = label ? ` aria-label="${SharedCharts.esc(label)}"` : "";
    return `<thinking-orb state="${state}" size="${size}"${aria}></thinking-orb>`;
  }

  static busy(state, text, size = 20) {
    return `<span class="orb-busy">${ThinkingOrb.html(state, size)}<span>${SharedCharts.esc(text)}</span></span>`;
  }

  static panel(state, text) {
    return `<div class="orb-panel">${ThinkingOrb.html(state, 64)}<span class="orb-panel__text">${SharedCharts.esc(text)}</span></div>`;
  }
}

customElements.define("thinking-orb", ThinkingOrbElement);
window.ThinkingOrb = ThinkingOrb;
window.BackdropOrb = BackdropOrb;
