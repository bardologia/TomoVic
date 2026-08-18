"use strict";

class PipelineTransport {
  constructor(animator) {
    this.animator = animator;
    this.root     = document.getElementById("proc-transport");
    this.timeline = document.getElementById("proc-timeline");
    this.playBtn  = document.getElementById("proc-play");
    this.prevBtn  = document.getElementById("proc-prev");
    this.nextBtn  = document.getElementById("proc-next");
    this.speedBtn = document.getElementById("proc-speed");
    this.chapEl   = document.getElementById("proc-chapter");
    this.timeEl   = document.getElementById("proc-time");

    this.def       = null;
    this.segs      = [];
    this.speeds    = [1, 1.5, 2, 0.5];
    this.speedIdx  = 0;
    this.hoverName = null;
    this.lastTime  = "";

    this.animator.onProgress = (pos, idx, playing) => this._update(pos, idx, playing);
    this._wire();
  }

  bind() {
    this.def = this.animator.sceneDef();
    this._buildSegments();
    this._update(this.animator.position(), this.animator.chapterIndex(), this.animator.playing());
  }

  prevChapter() {
    const idx = this.animator.chapterIndex();
    const c   = this.def.chapters[idx];
    const into = this.animator.position() - c.t0 / this.def.scale;
    this.animator.seekChapter(into > 2 ? idx : idx - 1);
  }

  nextChapter() {
    this.animator.seekChapter(this.animator.chapterIndex() + 1);
  }

  cycleSpeed() {
    this.speedIdx = (this.speedIdx + 1) % this.speeds.length;
    this.animator.speed = this.speeds[this.speedIdx];
    this.speedBtn.textContent = this.speeds[this.speedIdx] + "x";
  }

  handleKey(e) {
    if (e.key === " ") { e.preventDefault(); this.animator.toggle(); }
    else if (e.key === "ArrowLeft") { e.preventDefault(); this.prevChapter(); }
    else if (e.key === "ArrowRight") { e.preventDefault(); this.nextChapter(); }
  }

  _wire() {
    this.playBtn.addEventListener("click", () => this.animator.toggle());
    this.prevBtn.addEventListener("click", () => this.prevChapter());
    this.nextBtn.addEventListener("click", () => this.nextChapter());
    this.speedBtn.addEventListener("click", () => this.cycleSpeed());

    this.timeline.addEventListener("pointerdown", (e) => {
      e.preventDefault();
      this.timeline.setPointerCapture(e.pointerId);
      this.timeline.classList.add("is-scrubbing");
      this.wasPlaying = this.animator.playing();
      this.animator.pause();
      this.animator.seek(this._timeAt(e.clientX));
    });
    this.timeline.addEventListener("pointermove", (e) => {
      if (this.timeline.classList.contains("is-scrubbing")) this.animator.seek(this._timeAt(e.clientX));
    });
    this.timeline.addEventListener("pointerup", (e) => {
      this.timeline.releasePointerCapture(e.pointerId);
      this.timeline.classList.remove("is-scrubbing");
      if (this.wasPlaying) this.animator.play();
    });
  }

  _buildSegments() {
    this.timeline.innerHTML = "";
    this.segs = [];

    const chs = this.def.chapters;
    chs.forEach((c, i) => {
      const t1  = i + 1 < chs.length ? chs[i + 1].t0 : this.def.T;
      const seg = document.createElement("div");
      seg.className = "proc-timeline__seg";
      seg.style.flexGrow = String(t1 - c.t0);
      seg.title = c.name;
      seg.insertAdjacentHTML("beforeend", '<div class="proc-timeline__fill"></div>');
      seg.addEventListener("mouseenter", () => { this.hoverName = c.name; this.chapEl.textContent = c.name; });
      seg.addEventListener("mouseleave", () => { this.hoverName = null; });
      this.timeline.appendChild(seg);
      this.segs.push({ el: seg, fill: seg.firstChild, t0: c.t0, t1 });
    });
  }

  _timeAt(clientX) {
    for (let i = 0; i < this.segs.length; i++) {
      const s = this.segs[i], r = s.el.getBoundingClientRect();
      if (clientX <= r.right || i === this.segs.length - 1) {
        const frac = Math.min(1, Math.max(0, (clientX - r.left) / Math.max(1, r.width)));
        return (s.t0 + frac * (s.t1 - s.t0)) / this.def.scale;
      }
    }
    return 0;
  }

  _update(pos, idx, playing) {
    if (!this.def) return;
    this.root.classList.toggle("is-playing", playing);
    this.playBtn.setAttribute("aria-label", playing ? "Pause" : "Play");

    const tt = pos * this.def.scale;
    this.segs.forEach((s, i) => {
      s.el.classList.toggle("is-active", i === idx);
      s.el.classList.toggle("is-done", i < idx);
      const frac = i < idx ? 1 : i > idx ? 0 : (tt - s.t0) / (s.t1 - s.t0);
      s.fill.style.width = (frac * 100).toFixed(2) + "%";
    });

    if (!this.hoverName) this.chapEl.textContent = this.def.chapters[idx].name;
    const txt = this._fmt(pos) + " / " + this._fmt(this.animator.duration());
    if (txt !== this.lastTime) { this.lastTime = txt; this.timeEl.textContent = txt; }
  }

  _fmt(s) {
    const m = Math.floor(s / 60), r = Math.floor(s % 60);
    return m + ":" + String(r).padStart(2, "0");
  }
}

class PipelineFlow {
  constructor(hostEl) {
    this.hostEl = hostEl;
    this.pipelines = [];
    this.animator = null;
    this.transport = null;
    this._wireModal();
  }

  async load() {
    const data = await Api.get("/api/pipelines");
    this.pipelines = data.pipelines || [];
    this._render();
  }

  _render() {
    this.hostEl.innerHTML = "";

    this.pipelines.forEach((p, i) => {
      const row = document.createElement("div");
      row.className = "flow-row flow-row--play reveal";
      row.style.transitionDelay = `${i * 0.05}s`;

      const lead = document.createElement("div");
      lead.className = "flow-row__lead";

      const idx = String(i + 1).padStart(2, "0");
      let runHtml = "";
      if (p.script) {
        runHtml = `<button class="flow-row__run" data-script="${p.script}">main/${p.script}.py &rarr;</button>`;
      } else {
        runHtml = `<span class="flow-row__nomap">built into training</span>`;
      }

      lead.innerHTML =
        `<span class="flow-row__idx">${idx}</span>` +
        `<div class="flow-row__body"><h3 class="flow-row__name">${p.name}</h3>` +
        `<p class="flow-row__blurb">${p.blurb}</p>${runHtml}</div>`;

      const stages = document.createElement("div");
      stages.className = "flow-row__stages";
      p.stages.forEach((s, j) => {
        if (j > 0) {
          const arrow = document.createElement("span");
          arrow.className = "stage-arrow";
          arrow.textContent = "→";
          stages.appendChild(arrow);
        }
        const chip = document.createElement("span");
        chip.className = "stage";
        chip.style.transitionDelay = `${j * 0.07}s`;
        chip.textContent = s;
        stages.appendChild(chip);
      });

      const hasScene = window.ProcessAnimator && window.ProcessAnimator.SCENES[p.key];
      if (hasScene) {
        const play = document.createElement("span");
        play.className = "flow-row__play";
        play.innerHTML = "&#9658; watch the process";
        stages.appendChild(play);
      }

      row.appendChild(lead);
      row.appendChild(stages);
      if (hasScene) {
        row.addEventListener("click", (e) => {
          if (e.target.closest(".flow-row__run")) return;
          this._openProcess(p);
        });
      }
      this.hostEl.appendChild(row);
    });

    this.hostEl.querySelectorAll(".flow-row__run").forEach((btn) => {
      btn.addEventListener("click", (e) => {
        e.stopPropagation();
        if (window.router) window.router.go(`launch/${btn.dataset.script}`);
      });
    });

    window.revealScan();
  }

  _openProcess(p) {
    const modal = document.getElementById("proc-modal");
    document.getElementById("proc-kicker").textContent = p.script ? `main/${p.script}.py` : "pipeline";
    document.getElementById("proc-title").textContent = p.name + " pipeline";

    const stages = document.getElementById("proc-stages");
    stages.innerHTML = "";
    p.stages.forEach((s, j) => {
      if (j > 0) stages.insertAdjacentHTML("beforeend", '<span class="stage-arrow">→</span>');
      stages.insertAdjacentHTML("beforeend", `<span class="stage">${s}</span>`);
    });

    modal.classList.add("is-open");
    modal.setAttribute("aria-hidden", "false");

    if (!this.animator) {
      this.animator = new window.ProcessAnimator(document.getElementById("proc-canvas"), document.getElementById("proc-caption"));
      this.transport = new PipelineTransport(this.animator);
    }
    requestAnimationFrame(() => {
      this.animator.start(p.key);
      this.transport.bind();
    });
  }

  _closeProcess() {
    const modal = document.getElementById("proc-modal");
    modal.classList.remove("is-open");
    modal.setAttribute("aria-hidden", "true");
    if (this.animator) this.animator.close();
  }

  _wireModal() {
    document.getElementById("proc-close").addEventListener("click", () => this._closeProcess());
    document.getElementById("proc-scrim").addEventListener("click", () => this._closeProcess());
    document.addEventListener("keydown", (e) => {
      if (!document.getElementById("proc-modal").classList.contains("is-open")) return;
      if (e.key === "Escape") { this._closeProcess(); return; }
      if (this.transport) this.transport.handleKey(e);
    });
  }
}

window.PipelineFlow = PipelineFlow;
