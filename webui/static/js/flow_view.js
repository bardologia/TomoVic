"use strict";

class FlowView {
  constructor(root) {
    this.root    = root;
    this.flows   = [];
    this.flow    = null;
    this.cursor  = -1;
    this.shown   = -1;
    this.playing = false;
    this.timer   = null;
    this.iterTimer = null;
    this.loaded  = false;
    this.lineSeq = 0;
    this.groups  = [];
    this.lastAnimate = true;

    this.COLOR = { measured: "#6ea8ff", intermediate: "#f5b971", calculated: "#4fd6c4", final: "#c4a3ff" };
    this.ROLES = ["measured", "intermediate", "calculated", "final"];

    this.SLOTW = "28%";
    this.SLOTS = { s0: "1.5%", s1: "36%", s2: "70.5%", enter: "102%", exit: "-30%" };
    this.LSLOT = [
      { op: 0.65, scale: 0.85 },
      { op: 0.80, scale: 0.92 },
      { op: 1.00, scale: 1.00 },
      { op: 0.00, scale: 0.80 },
      { op: 0.00, scale: 0.80 },
    ];
    this.LTOPS = [10, 24, 38, 50, 58];
    this.stackTimer = null;

  }

  async load() {
    if (this.loaded) return;
    this.loaded = true;
    const data = await Api.get("/api/flows");
    if (!data || data.error) {
      this.loaded = false;
      this.root.innerHTML = `<p class="cube-hint">${SharedCharts.esc((data && data.error) || "flows unavailable")}</p>`;
      return;
    }
    this.flows = data.flows || [];
    this._buildShell();
    if (this.flows.length) this._selectFlow(this.flows[0].key);
  }

  _buildShell() {
    this.root.innerHTML = "";
    this.root.classList.add("cine");

    const bar = document.createElement("div");
    bar.className = "cine__bar";
    this.selEl = document.createElement("div");
    this.selEl.className = "cine__pick";
    this.flows.forEach((f) => {
      const b = document.createElement("button");
      b.className = "cine__pickbtn";
      b.textContent = f.name;
      b.dataset.key = f.key;
      b.addEventListener("click", () => this._selectFlow(f.key));
      this.selEl.appendChild(b);
    });
    const legend = document.createElement("div");
    legend.className = "cine__legend";
    this.ROLES.forEach((role) => {
      const item = document.createElement("span");
      item.className = "cine__leg cine__leg--" + role;
      item.innerHTML = `<i></i>${role}`;
      legend.appendChild(item);
    });
    bar.appendChild(this.selEl);
    bar.appendChild(legend);

    this.stage = document.createElement("div");
    this.stage.className = "cine__stage";
    this.stage.innerHTML = `
      <svg class="cine__wires"><defs>
        <marker id="cine-arrow" viewBox="0 0 10 10" refX="8.5" refY="5" markerWidth="5" markerHeight="5" orient="auto">
          <path d="M0,0 L10,5 L0,10 z" fill="context-stroke"></path>
        </marker></defs></svg>
      <div class="cine__head">
        <span class="cine__stepno"></span>
        <div class="cine__headtxt"><h3 class="cine__title"></h3><span class="cine__phase"></span></div>
      </div>
      <div class="cine__trail"></div>
      <div class="cine__scene"></div>
      <p class="cine__note"></p>`;

    this.stepNo  = this.stage.querySelector(".cine__stepno");
    this.headEl  = this.stage.querySelector(".cine__head");
    this.titleEl = this.stage.querySelector(".cine__title");
    this.phaseEl = this.stage.querySelector(".cine__phase");
    this.trailEl = this.stage.querySelector(".cine__trail");
    this.sceneEl = this.stage.querySelector(".cine__scene");
    this.noteEl  = this.stage.querySelector(".cine__note");

    this.ctrl = document.createElement("div");
    this.ctrl.className = "cine__ctrl";
    this.ctrl.innerHTML = `
      <button class="cine__btn" data-act="restart" title="Restart">&#8635;</button>
      <button class="cine__btn" data-act="prev" title="Previous step">&#9664;</button>
      <button class="cine__btn cine__btn--play" data-act="play" title="Play / pause">&#9654;</button>
      <button class="cine__btn" data-act="next" title="Next step">&#9654;&#9654;</button>
      <div class="cine__track"><div class="cine__trackfill"></div></div>
      <span class="cine__count">--</span>
      <button class="cine__btn cine__btn--full" data-act="full" title="Full screen">&#9974;</button>`;
    this.ctrl.querySelectorAll(".cine__btn").forEach((b) => b.addEventListener("click", () => this._onCtrl(b.dataset.act)));
    this.trackFill = this.ctrl.querySelector(".cine__trackfill");
    this.countEl   = this.ctrl.querySelector(".cine__count");
    this.playBtn   = this.ctrl.querySelector(".cine__btn--play");

    document.addEventListener("fullscreenchange", () => {
      this.stage.classList.toggle("is-full", document.fullscreenElement === this.stage);
    });

    this.root.appendChild(bar);
    this.root.appendChild(this.stage);
    this.root.appendChild(this.ctrl);
  }

  _selectFlow(key) {
    this._pause();
    this.flow = this.flows.find((f) => f.key === key) || this.flows[0];
    [...this.selEl.children].forEach((b) => b.classList.toggle("is-active", b.dataset.key === this.flow.key));
    this.byId = {};
    this.flow.nodes.forEach((n) => (this.byId[n.id] = n));
    this._buildTrail();
    this._reset();
  }

  _buildTrail() {
    this.trailEl.innerHTML = "";
    this.flow.steps.forEach((step, i) => {
      if (i) { const con = document.createElement("span"); con.className = "cine__trailcon"; this.trailEl.appendChild(con); }
      const out = this.byId[step.outputs[step.outputs.length - 1]] || this.byId[step.outputs[0]];
      const chip = document.createElement("span");
      chip.className = "cine__chip cine__chip--" + (out ? out.role : "intermediate");
      chip.dataset.step = i;
      this.trailEl.appendChild(chip);
      if (out) { chip.style.color = this.COLOR[out.role]; this._typeset(chip, out.tex, false); }
      chip.addEventListener("click", () => { this._pause(); this._go(i); });
    });
  }

  _reset() {
    this._pause();
    clearTimeout(this.iterTimer);
    clearTimeout(this.stackTimer);
    this.cursor = -1;
    this.shown  = -1;
    this.groups.forEach((g) => this._killSketchLoop(g));
    this.groups = [];
    this.sceneEl.innerHTML = "";
    this.stepNo.textContent  = "00";
    this.titleEl.textContent = this.flow.name;
    this.phaseEl.textContent = "press play to walk the pipeline step by step";
    this.noteEl.textContent  = this.flow.blurb;
    [...this.trailEl.querySelectorAll(".cine__chip")].forEach((c) => c.classList.remove("is-done", "is-active"));
    this._progress();
  }

  _onCtrl(act) {
    if (act === "restart") return this._reset();
    if (act === "prev")    { this._pause(); return this._go(Math.max(-1, this.cursor - 1)); }
    if (act === "next")    { this._pause(); return this._go(Math.min(this.flow.steps.length - 1, this.cursor + 1)); }
    if (act === "play")    return this.playing ? this._pause() : this._play();
    if (act === "full")    {
      if (document.fullscreenElement === this.stage) document.exitFullscreen && document.exitFullscreen();
      else this.stage.requestFullscreen && this.stage.requestFullscreen().catch(() => {});
    }
  }

  _play() {
    if (this.cursor >= this.flow.steps.length - 1) this._reset();
    this.playing = true;
    this.playBtn.innerHTML = "&#10073;&#10073;";
    this.playBtn.classList.add("is-on");
    this._tick(this.cursor < 0 ? 800 : 0);
  }

  _pause() {
    this.playing = false;
    if (this.playBtn) { this.playBtn.innerHTML = "&#9654;"; this.playBtn.classList.remove("is-on"); }
    clearTimeout(this.timer);
  }

  _tick(delay) {
    if (!this.playing) return;
    if (this.cursor >= this.flow.steps.length - 1) return this._pause();
    this.timer = setTimeout(() => {
      this._go(this.cursor + 1);
      const step  = this.flow.steps[this.cursor];
      const lines = step ? (step.lines || []).length : 1;
      const base  = step && step.iterative ? 4200 : 3000;
      this._tick(base + Math.max(0, lines - 1) * 1900);
    }, delay || 0);
  }

  _go(i) {
    if (i < 0) return this._reset();
    const reduced = window.REDUCED_MOTION;
    const slide   = !reduced && Math.abs(i - this.shown) === 1 && this.groups.length > 0;
    this.lastAnimate = !reduced;
    this.cursor = i;
    this._renderWindow(i, slide);
    this.shown = i;
    this._setHead(this.flow.steps[i], i, !reduced);
    this._setTrail(i);
    this._progress();
  }

  _renderWindow(c, slide) {
    clearTimeout(this.iterTimer);
    clearTimeout(this.stackTimer);
    const N    = this.flow.steps.length;
    const want = [c - 1, c, c + 1].filter((x) => x >= 0 && x < N);
    const have = new Map(this.groups.map((g) => [g.i, g]));

    const keep = want.map((si) => {
      let g = have.get(si);
      if (!g) { g = this._buildGroup(si); this._setGeom(g, si > this.shown ? "enter" : "exit", 0, false); }
      return g;
    });

    this.groups.forEach((g) => {
      if (want.indexOf(g.i) >= 0) return;
      this._setGeom(g, g.i < c ? "exit" : "enter", 0, slide);
      this._removeLater(g, slide);
    });

    const place = () => keep.forEach((g) => {
      const off = g.i - c;
      g.el.classList.toggle("is-current", off === 0);
      this._setGeom(g, off < 0 ? "s0" : off > 0 ? "s2" : "s1", off > 0 ? 0.45 : 1, slide);
      this._setTip(g, off <= 0, slide);
      if (off === 0) {
        g.ready.then(() => setTimeout(() => {
          if (this.cursor !== g.i) return;
          this._stackRun(g);
          if (g.step.iterative && g.iterEl) this._iterRun(g.step, g.iterEl, this.lastAnimate);
        }, slide ? 720 : 0));
      } else {
        if (g.step.iterative && g.iterEl) this._iterIdle(g.step, g.iterEl);
      }
    });
    if (slide) requestAnimationFrame(place); else place();

    this.groups = keep;
  }

  _buildGroup(i) {
    const step    = this.flow.steps[i];
    const grp     = document.createElement("div");
    grp.className = "cine__grp";
    grp.dataset.step = i;

    const sk = FlowSketches.CATALOG[step.id] || null;
    let tip = null, sketchSvg = null;
    if (sk) {
      tip = document.createElement("div");
      tip.className = "cine__gtip";
      tip.innerHTML = `<div class="cine__gsketch"></div><p class="cine__gtiptext">${SharedCharts.esc(sk.tip)}</p>`;
      sketchSvg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
      sketchSvg.setAttribute("viewBox", "0 0 240 150");
      sketchSvg.classList.add("cine__skl");
      try { if (sk.build) sk.build(sketchSvg); } catch (e) {}
      tip.querySelector(".cine__gsketch").appendChild(sketchSvg);
    }

    const eq = document.createElement("div");
    eq.className = "cine__eq";

    const lines = [];
    (step.lines || []).forEach((terms) => {
      const line = document.createElement("div");
      line.className = "cine__line";
      const uid = ++this.lineSeq;
      lines.push({ line, terms, uid });
      eq.appendChild(line);
    });

    let iterEl = null;
    if (step.iterative) { iterEl = document.createElement("div"); iterEl.className = "cine__giter"; eq.appendChild(iterEl); }

    if (tip) grp.appendChild(tip);
    grp.appendChild(eq);
    this.sceneEl.appendChild(grp);

    const ready = Promise.all(lines.map(({ line, terms, uid }) =>
      this._typeset(line, this._composeLine(terms, uid), true).then(() => this._colorize(terms, uid))));

    if (tip) tip.style.opacity = "0";
    const group = { el: grp, step, i, lines, iterEl, tipEl: tip, sketchSvg, sketchAnim: sk ? sk.anim : null, sketchLoop: null, stackK: 0, tipShown: false };
    if (lines.length > 1 && !window.REDUCED_MOTION && window.gsap) {
      eq.classList.add("is-stack");
      this._stackPlace(group, false);
    }
    if (iterEl) this._iterIdle(step, iterEl);
    group.ready = ready.then(() => {
      if (this.lastAnimate) this._writeIn(group);
    });
    return group;
  }

  _setTip(group, shown, slide) {
    if (!group.tipEl || group.tipShown === shown) return;
    group.tipShown = shown;
    const el = group.tipEl;
    if (!window.gsap || window.REDUCED_MOTION) { el.style.opacity = shown ? "1" : "0"; return; }
    if (shown) {
      window.gsap.fromTo(el, { opacity: 0, y: 10 }, { opacity: 1, y: 0, duration: 0.5, delay: slide ? 0.62 : 0.2, ease: "power2.out" });
      if (group.sketchSvg && group.sketchAnim && !window.REDUCED_MOTION) {
        this._killSketchLoop(group);
        try { group.sketchLoop = group.sketchAnim(group.sketchSvg, window.gsap); } catch (e) { group.sketchLoop = null; }
      }
    } else {
      window.gsap.to(el, { opacity: 0, y: 0, duration: 0.25 });
      this._killSketchLoop(group);
    }
  }

  _killSketchLoop(group) {
    if (!group) return;
    if (group.sketchLoop) { try { group.sketchLoop.kill(); } catch (e) {} group.sketchLoop = null; }
    if (group.sketchSvg) group.sketchSvg.querySelectorAll("[data-loop]").forEach((e) => e.remove());
  }

  _writeIn(group) {
    if (!window.gsap) return;
    const svgs = group.el.querySelectorAll(".cine__line svg");
    window.gsap.fromTo(svgs, { opacity: 0, y: 10 }, { opacity: 1, y: 0, duration: 0.5, stagger: 0.08, ease: "power2.out" });
  }

  _setGeom(group, slot, op, animate) {
    const left = this.SLOTS[slot];
    group.el.style.width = this.SLOTW;
    if (animate && window.gsap) window.gsap.to(group.el, { left: left, opacity: op, duration: 0.62, ease: "power3.inOut" });
    else { group.el.style.left = left; group.el.style.opacity = op; }
  }

  _stackRun(group) {
    clearTimeout(this.stackTimer);
    if (group.lines.length < 2 || !this.lastAnimate || !window.gsap) return;
    this.stackTimer = setTimeout(() => this._stackAdvance(group), 1500);
  }

  _stackAdvance(group) {
    if (this.cursor !== group.i || !group.el.isConnected) return;
    if (group.stackK >= group.lines.length - 1) return;
    group.stackK += 1;
    this._stackPlace(group, true);
    this.stackTimer = setTimeout(() => this._stackAdvance(group), 2100);
  }

  _stackPlace(group, animate) {
    group.lines.forEach(({ line }, li) => {
      const o = Math.max(0, Math.min(4, li - group.stackK + 2));
      const s = this.LSLOT[o];
      const props = { top: this.LTOPS[o] + "%", yPercent: -50, scale: s.scale, opacity: s.op };
      if (animate) window.gsap.to(line, Object.assign(props, { duration: 0.6, ease: "power3.inOut" }));
      else window.gsap.set(line, props);
    });
  }

  _removeLater(group, animate) {
    this._killSketchLoop(group);
    const el = group.el;
    if (animate) setTimeout(() => el.remove(), 700);
    else el.remove();
  }

  _composeLine(terms, uid) {
    return terms.map((t, ti) => (t.role ? `\\cssId{flx-${uid}-${ti}-${t.id}}{${t.tex}}` : t.tex)).join(" ");
  }

  _colorize(terms, uid) {
    terms.forEach((t, ti) => {
      if (!t.role) return;
      const el = document.getElementById(`flx-${uid}-${ti}-${t.id}`);
      if (el) el.style.color = this.COLOR[t.role] || "#e7edf0";
    });
  }

  _setHead(step, i, animate) {
    const set = () => {
      this.stepNo.textContent  = String(i + 1).padStart(2, "0");
      this.titleEl.innerHTML   = SharedCharts.esc(step.title) + (step.iterative ? ` <span class="cine__loop">iterative</span>` : "");
      this.phaseEl.textContent = step.phase ? "phase " + step.phase : "";
      this.noteEl.textContent  = step.note || "";
    };
    if (animate && window.gsap) window.gsap.fromTo([this.headEl, this.noteEl], { opacity: 0, y: 6 }, { opacity: 1, y: 0, duration: 0.4, onStart: set });
    else set();
  }

  _setTrail(i) {
    [...this.trailEl.querySelectorAll(".cine__chip")].forEach((c) => {
      const s = Number(c.dataset.step);
      c.classList.toggle("is-done", s < i);
      c.classList.toggle("is-active", s === i);
    });
  }

  _iterIdle(step, el) {
    if (!el) return;
    const it = step.iterative;
    const unit = it.unit || "t";
    el.className = "cine__giter is-on is-idle";
    el.innerHTML = `<span class="cine__iterlab">iterating</span><span class="cine__itercount">${SharedCharts.esc(unit)} = 1 &hellip; ${it.steps}</span>`;
  }

  _iterRun(step, el, animate) {
    if (!el) return;
    const it = step.iterative;
    const unit = it.unit || "t";
    const sym  = it.symbol || "x";
    el.className = "cine__giter is-on";
    el.innerHTML = `<span class="cine__iterlab">iterating</span><span class="cine__itercount"></span><span class="cine__iterval"></span>`;
    const cnt = el.querySelector(".cine__itercount");
    const val = el.querySelector(".cine__iterval");
    const trace = it.trace || [];
    const last  = trace.length ? trace[trace.length - 1] : "";
    if (!animate || !trace.length) { cnt.textContent = `${unit} = ${it.steps}`; val.textContent = `${sym} → ${last}`; return; }
    let k = 0;
    clearTimeout(this.iterTimer);
    const tick = () => {
      if (!el.isConnected) return;
      const frac = trace.length > 1 ? k / (trace.length - 1) : 1;
      cnt.textContent = `${unit} = ${Math.round(1 + frac * (it.steps - 1))}`;
      val.textContent = `${sym} → ${trace[Math.min(k, trace.length - 1)]}`;
      val.classList.remove("is-bump"); void val.offsetWidth; val.classList.add("is-bump");
      k += 1;
      if (k < trace.length) this.iterTimer = setTimeout(tick, 460);
    };
    tick();
  }

  _progress() {
    const n = this.flow.steps.length;
    this.countEl.textContent   = `${Math.max(0, this.cursor + 1)} / ${n}`;
    this.trackFill.style.width = `${((this.cursor + 1) / n) * 100}%`;
  }

  _typeset(el, tex, display) {
    return MathJaxTypesetter.render(el, tex, display);
  }

}

window.FlowView = FlowView;
