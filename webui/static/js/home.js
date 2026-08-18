"use strict";

class GpuWeekPanel {
  static DAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"];

  static dayOptions() {
    return GpuWeekPanel.DAYS.map((day, index) => `<option value="${index}">${day.slice(0, 3)}</option>`).join("");
  }

  static hourOptions() {
    return Array.from({ length: 24 }, (_, hour) => `<option value="${hour}">${String(hour).padStart(2, "0")}:00</option>`).join("");
  }

  static gpuTokens(raw) {
    return String(raw || "")
      .split(/[\s,]+/)
      .filter((token) => token.length);
  }

  static parseGpus(raw) {
    return GpuWeekPanel.gpuTokens(raw)
      .map(Number)
      .filter(Number.isFinite);
  }

  static badGpuTokens(raw) {
    return GpuWeekPanel.gpuTokens(raw).filter((token) => !Number.isFinite(Number(token)));
  }

  constructor() {
    this.state = null;
    this.seeded = false;
  }

  wire() {
    const save = document.getElementById("sb-sch-save");
    const toggle = document.getElementById("sb-sch-toggle");
    const greedy = document.getElementById("sb-sch-greedy");
    const charity = document.getElementById("sb-sch-charity");
    if (!save || !toggle || !greedy || !charity) return;

    save.addEventListener("click", () => this._submit((this.state || {}).enabled, (this.state || {}).greedy, (this.state || {}).charity));
    toggle.addEventListener("click", () => this._submit(!(this.state || {}).enabled, (this.state || {}).greedy, (this.state || {}).charity));
    greedy.addEventListener("click", () => this._submit((this.state || {}).enabled, !(this.state || {}).greedy, (this.state || {}).charity));
    charity.addEventListener("click", () => this._submit((this.state || {}).enabled, (this.state || {}).greedy, !(this.state || {}).charity));
  }

  _value(id) {
    const el = document.getElementById(id);
    return el ? Number(el.value) : 0;
  }

  _raw(id) {
    const el = document.getElementById(id);
    return el ? el.value : "";
  }

  async _submit(enabled, greedy, charity) {
    const fields = [
      ["sb-sch-weekday", "weekday"],
      ["sb-sch-night", "night"],
      ["sb-sch-weekend", "weekend"],
    ];
    for (const [id, label] of fields) {
      const bad = GpuWeekPanel.badGpuTokens(this._raw(id));
      const el  = document.getElementById(id);
      if (el) el.classList.toggle("is-bad", !!bad.length);
      if (bad.length) {
        Toast.show(`${label} pool is not numeric: ${bad.join(", ")}`, "error");
        return;
      }
    }

    const payload = {
      enabled: !!enabled,
      greedy: !!greedy,
      charity: !!charity,
      weekday_gpus: GpuWeekPanel.parseGpus(this._raw("sb-sch-weekday")),
      night_gpus: GpuWeekPanel.parseGpus(this._raw("sb-sch-night")),
      weekend_gpus: GpuWeekPanel.parseGpus(this._raw("sb-sch-weekend")),
      start_day: this._value("sb-sch-startday"),
      start_hour: this._value("sb-sch-starthour"),
      end_day: this._value("sb-sch-endday"),
      end_hour: this._value("sb-sch-endhour"),
      night_start_hour: this._value("sb-sch-nightstart"),
      night_end_hour: this._value("sb-sch-nightend"),
    };

    const res = await Api.post("/api/gpu-schedule", payload);
    if (!res || !res.ok) {
      Toast.show(`schedule rejected: ${(res && res.error) || "network error"}`, "error");
      return;
    }

    this.seeded = false;
    this.render(res);
    Toast.show(res.enabled ? `GPU week schedule on — ${res.phase} pool ${res.gpus_now.join(",")} applies now` : "GPU week schedule off", res.enabled ? "ok" : "warn");
  }

  render(state) {
    if (!state) return;
    this.state = state;

    const light = document.getElementById("sb-sch-light");
    const mode = document.getElementById("sb-sch-mode");
    const toggle = document.getElementById("sb-sch-toggle");
    const greedy = document.getElementById("sb-sch-greedy");
    const charity = document.getElementById("sb-sch-charity");
    const hint = document.getElementById("sb-sch-hint");
    const on = !!state.enabled;
    const waiting = state.waiting || [];

    if (light) light.classList.toggle("is-armed", on);
    if (mode) {
      mode.textContent = on ? state.phase : "off";
      mode.classList.toggle("is-off", !on);
    }
    if (toggle) {
      toggle.textContent = on ? "schedule: ON" : "schedule: off";
      toggle.classList.toggle("is-safe", on);
    }
    if (greedy) {
      greedy.textContent = state.greedy ? "greedy: ON" : "greedy: off";
      greedy.classList.toggle("is-safe", !!state.greedy && on);
      greedy.disabled = !on;
    }
    if (charity) {
      charity.textContent = state.charity ? "charity: ON" : "charity: off";
      charity.classList.toggle("is-safe", !!state.charity && !!state.greedy && on);
      charity.disabled = !on || !state.greedy;
    }
    if (hint) {
      const chase = waiting.length
        ? state.greedy
          ? state.napping
            ? ` · ${waiting.join(",")} stay out while charity naps`
            : ` · ${waiting.join(",")} busy elsewhere, retrying every 10 min`
          : ` · ${waiting.join(",")} were busy at the switch, greedy off so they stay out`
        : "";
      const gave = state.napping && state.last_charity
        ? ` · charity opened gpu ${state.last_charity.gpu} for ${(state.last_charity.users || []).join(",")}, greedy naps until ${String(state.nap_until).slice(11, 16)}`
        : "";
      hint.textContent = on
        ? `${state.phase} now — running fan-outs use ${state.gpus_now.join(",")}${chase}${gave} · night ${state.night_window} · weekend ${state.window}`
        : `off — night would be ${state.night_window}, weekend ${state.window}`;
    }

    if (this.seeded) return;
    this.seeded = true;

    const set = (id, value) => {
      const el = document.getElementById(id);
      if (el) el.value = value;
    };

    set("sb-sch-weekday", (state.weekday_gpus || []).join(","));
    set("sb-sch-night", (state.night_gpus || []).join(","));
    set("sb-sch-weekend", (state.weekend_gpus || []).join(","));
    set("sb-sch-startday", state.start_day);
    set("sb-sch-starthour", state.start_hour);
    set("sb-sch-endday", state.end_day);
    set("sb-sch-endhour", state.end_hour);
    set("sb-sch-nightstart", state.night_start_hour);
    set("sb-sch-nightend", state.night_end_hour);
  }
}

class ByteFormat {

  static gb(bytes) {
    return (bytes / 1073741824).toFixed(1);
  }

  static mb(bytes) {
    const gb = bytes / 1073741824;
    if (gb >= 1) return `${gb.toFixed(1)}G`;
    return `${Math.round(bytes / 1048576)}M`;
  }

  static tb(bytes) {
    const tb = bytes / 1099511627776;
    return tb >= 1 ? `${tb.toFixed(2)} TB` : `${ByteFormat.gb(bytes)} GB`;
  }
}

class UsersTable {

  markup() {
    return (
      `<section class="sboard sboard--users" aria-label="Active users">` +
      `<header class="sboard__cap"><span>active users</span><span class="sboard__n" id="sb-users-n">--</span></header>` +
      `<div class="utable">` +
      `<div class="utable__row utable__row--head"><span>user</span><span title="summed over all the user's processes; 100% = one full core">cpu%</span><span title="memory attributed to the user: proportional set size for your own processes, private resident for other users, so shared pages are not double-counted">ram</span><span title="share of used RAM (total minus available), same base as the neighbour impact panel">ram%</span><span class="utable__gpu" title="GPU memory the user has allocated across all CUDA devices">gpu mem</span><span title="CUDA devices the user holds memory on">gpus</span><span title="processes owned by the user">procs</span><span title="open login sessions">ssh</span></div>` +
      `<div class="utable__body" id="sb-users"></div>` +
      `</div>` +
      `</section>`
    );
  }

  render(users) {
    const body = document.getElementById("sb-users");
    const n = document.getElementById("sb-users-n");
    if (!body) return;
    if (n) n.textContent = `${users.length} user${users.length === 1 ? "" : "s"}`;

    if (!users.length) {
      body.innerHTML = `<div class="sboard__empty">measuring user activity&hellip;</div>`;
      return;
    }

    body.innerHTML = users.map((u) => {
      const cls = u.cpu >= 100 ? "is-hot" : u.cpu >= 25 ? "is-mid" : "";
      const gpus = (u.gpus || []).length ? u.gpus.join(",") : "--";
      return (
        `<div class="utable__row${u.me ? " is-me" : ""}">` +
        `<span class="utable__user">${SharedCharts.esc(u.user)}${u.me ? `<i class="utable__me">you</i>` : ""}</span>` +
        `<span class="utable__cpu ${cls}">${u.cpu.toFixed(1)}</span>` +
        `<span>${ByteFormat.mb(u.mem)}</span>` +
        `<span class="utable__share">${u.mem_share.toFixed(1)}%</span>` +
        `<span class="utable__gpu">${u.gpu_mem ? ByteFormat.mb(u.gpu_mem * 1048576) : "--"}</span>` +
        `<span class="utable__gpus">${gpus}</span>` +
        `<span>${u.nproc}</span>` +
        `<span class="utable__sess">${u.sessions || "--"}</span>` +
        `</div>`
      );
    }).join("");
  }
}

class ProcessTable {

  markup(user) {
    return (
      `<section class="sboard sboard--procs" aria-label="Processes">` +
      `<header class="sboard__cap"><span>processes &middot; ${SharedCharts.esc(user || "user")}</span><span class="sboard__n" id="sb-proc-n"></span></header>` +
      `<div class="ptable">` +
      `<div class="ptable__row ptable__row--head"><span>pid</span><span>cpu%</span><span title="proportional set size: shared pages split across the processes mapping them, so these rows sum to real memory use (unlike RSS, which double-counts shared pages)">mem</span><span class="ptable__gpu">gpu</span><span title="threads currently open in the process">thr</span><span>s</span><span>command</span></div>` +
      `<div class="ptable__body" id="sb-procs"></div>` +
      `</div>` +
      `</section>`
    );
  }

  render(procs) {
    const body = document.getElementById("sb-procs");
    const n = document.getElementById("sb-proc-n");
    if (!body) return;
    if (n) n.textContent = String(procs.length);

    if (!procs.length) {
      body.innerHTML = `<div class="sboard__empty">no processes</div>`;
      return;
    }

    body.innerHTML = procs.map((p) => {
      const cls = p.cpu >= 100 ? "is-hot" : p.cpu >= 25 ? "is-mid" : "";
      const run = p.state === "R" ? " is-run" : "";
      return (
        `<div class="ptable__row${run}">` +
        `<span class="ptable__pid">${p.pid}</span>` +
        `<span class="ptable__cpu ${cls}">${p.cpu.toFixed(1)}</span>` +
        `<span>${ByteFormat.mb(p.pss != null ? p.pss : p.rss)}</span>` +
        `<span class="ptable__gpu">${p.gpu ? ByteFormat.mb(p.gpu * 1048576) : "--"}</span>` +
        `<span class="ptable__thr">${p.threads != null ? p.threads : "--"}</span>` +
        `<span class="ptable__state">${SharedCharts.esc(p.state)}</span>` +
        `<span class="ptable__cmd" title="${SharedCharts.esc(p.cmd)}">${SharedCharts.esc(p.cmd)}</span>` +
        `</div>`
      );
    }).join("");
  }
}

class JobsList {

  markup() {
    return (
      `<section class="sboard sboard--jobs" aria-label="Jobs">` +
      `<header class="sboard__cap"><span>jobs</span><span class="sboard__n" id="sb-jobs-n">0</span></header>` +
      `<ul class="sboard__jobs" id="sb-jobs"><li class="sboard__empty">no runs yet</li></ul>` +
      `</section>`
    );
  }

  _row(job, follow) {
    const name = SharedCharts.esc(job.script || String(job.command || "").split(" ")[0].split("/").pop() || "job");
    const cls =
      job.status === "running" ? "is-run" :
      job.status === "failed" ? "is-fail" :
      job.status === "scheduled" || job.status === "queued" ? "is-sched" :
      job.status === "cancelled" ? "is-cancel" : "is-done";
    const mark = follow ? `<span class="sboard__jarrow" aria-hidden="true">&#8627;</span>` : "";
    const prog = job.progress && job.progress.total
      ? `<span class="sboard__jprog${job.progress.failed ? " is-failing" : ""}">${SharedCharts.esc(Format.progressBits(job.progress).join(" · "))}</span>`
      : "";
    return `<li class="sboard__job ${cls}${follow ? " sboard__job--follow" : ""}">${mark}<span class="sboard__jdot" aria-hidden="true"></span><span class="sboard__jname">${name}</span>${prog}<span class="sboard__jstate">${SharedCharts.esc(job.status)}</span></li>`;
  }

  render(jobs) {
    const list = document.getElementById("sb-jobs");
    const n = document.getElementById("sb-jobs-n");
    if (!list) return;

    const running = jobs.filter((j) => j.status === "running").length;
    if (n) n.textContent = running > 0 ? `${running} running` : String(jobs.length);

    if (!jobs.length) {
      list.innerHTML = `<li class="sboard__empty">no runs yet</li>`;
      return;
    }

    const followers = new Map();
    jobs.forEach((j) => {
      if (j.follow_of) followers.set(j.follow_of, j);
    });

    list.innerHTML = jobs.filter((j) => !j.follow_of).slice(0, 8).map((j) => {
      const next = followers.get(j.job_id);
      return this._row(j, false) + (next ? this._row(next, true) : "");
    }).join("");
  }
}

class StatusBoard {
  static POLL_MS      = 1000;
  static AWAY_EVERY   = 10;
  static SHRINK_TICKS = 10;

  constructor(els) {
    this.els = els;
    this.built = false;
    this.gpuEls = [];
    this.coreEls = [];
    this.cpuDial = null;
    this.ramTank = null;
    this.swapTank = null;
    this.impactMeters = null;
    this.histMax = 144;
    this.gpuCount = 0;
    this.shrunkTicks = 0;
    this.ticks = 0;
    this.usersTable = new UsersTable();
    this.processTable = new ProcessTable();
    this.jobsList = new JobsList();
  }

  start() {
    this._poll();
    setInterval(() => this._tick(), StatusBoard.POLL_MS);
    this._pollJobs();
    setInterval(() => { if (this._showing()) this._pollJobs(); }, 5000);
    this._pollGuardHistory();
    setInterval(() => { if (this._showing()) this._pollGuardHistory(); }, 20000);
  }

  _tick() {
    if (document.visibilityState !== "visible") return;
    this.ticks += 1;
    if (this._showing() || this.ticks % StatusBoard.AWAY_EVERY === 0) this._poll();
  }

  _showing() {
    if (document.visibilityState !== "visible") return false;
    return !!(this.els.board && this.els.board.closest(".page.is-active"));
  }

  async _pollGuardHistory() {
    if (this._serverDown) return;
    const data = await Api.get("/api/gpu-guard/history?limit=100");
    if (data.error) return;

    this._guardHistory = data;
    this._renderGuardPanel();
  }

  async _poll() {
    if (this._serverDown) return;
    if (this._polling) return;
    this._polling = true;

    let sys;
    try {
      sys = await Api.get("/api/system");
    } finally {
      this._polling = false;
    }

    if (!sys || sys.error) return;
    if (this._needsRebuild((sys.gpus || []).length)) this._build(sys);
    this._update(sys);
  }

  _needsRebuild(gpus) {
    if (!this.built || gpus > this.gpuCount) {
      this.shrunkTicks = 0;
      return true;
    }
    if (gpus === this.gpuCount) {
      this.shrunkTicks = 0;
      return false;
    }

    this.shrunkTicks += 1;
    if (this.shrunkTicks < StatusBoard.SHRINK_TICKS) return false;

    this.shrunkTicks = 0;
    return true;
  }

  async _pollJobs() {
    if (this._serverDown) return;
    const data = await Api.get("/api/jobs");
    if (data.error) return;

    this.jobsList.render(data.jobs);
  }

  _disposeGauges() {
    this.gpuEls.forEach((card) => [card.dialU, card.meterT, card.meterP, card.vseg].forEach((gauge) => gauge.dispose()));
    [this.cpuDial, this.ramTank, this.swapTank].forEach((gauge) => { if (gauge) gauge.dispose(); });
    Object.values(this.impactMeters || {}).forEach((meter) => meter.dispose());

    this.gpuEls = [];
    this.cpuDial = null;
    this.ramTank = null;
    this.swapTank = null;
    this.impactMeters = null;
  }

  _build(sys) {
    this._disposeGauges();
    this.built = true;
    const gpus = sys.gpus || [];
    const cores = (sys.cpu && sys.cpu.cores) || [];
    this.gpuCount = gpus.length;

    const gpuCards = gpus.length
      ? gpus.map((g, i) =>
          `<article class="gcard" data-gpu="${i}">` +
          `<header class="gcard__head"><span class="gcard__idx">gpu ${g.index != null ? g.index : i}</span><span class="gcard__name">${SharedCharts.esc(g.name || "unknown")}</span><span class="gcard__who"></span></header>` +
          `<div class="gcard__cluster">` +
          `<canvas class="gdial gdial--big gdial--util"></canvas>` +
          `<canvas class="gcard__graph"></canvas>` +
          `</div>` +
          `<div class="gcard__meters">` +
          `<canvas class="gmeter gmeter--temp"></canvas>` +
          `<canvas class="gmeter gmeter--power"></canvas>` +
          `</div>` +
          `<div class="gcard__vramrow"><span class="gcard__vlabel">vram</span><canvas class="gseg"></canvas><span class="gcard__vram">--</span></div>` +
          `<footer class="gcard__foot"><span class="gcard__temp">--</span><span class="gcard__power">--</span><span class="gcard__legend"><i class="lg lg--util"></i>util<i class="lg lg--vram"></i>vram</span></footer>` +
          `</article>`
        ).join("")
      : `<div class="sboard__empty">${sys.gpus_known ? "no CUDA devices visible to the backend" : "nvidia-smi is not answering, GPU occupancy is unknown"}</div>`;

    const coreCells = cores.map((_, i) => `<i class="cpu__cell" data-core="${i}" title="core ${i}"></i>`).join("");

    const lim = (sys.alerts && sys.alerts.limits) || {};
    const limitCells = [
      [lim.cpu_alert != null ? `${Math.round(lim.cpu_alert)}%` : "--", "cpu alert"],
      [lim.load_ratio != null ? `${lim.load_ratio.toFixed(1)} / core` : "--", "load limit"],
      [lim.ram_warn != null ? `${Math.round(lim.ram_warn)}%` : "--", "ram warn"],
      [lim.ram_kill != null ? `${Math.round(lim.ram_kill)}%` : "--", "ram kill"],
      [lim.mine_share != null ? `${Math.round(lim.mine_share * 100)}%` : "--", "own ram share"],
      [lim.interval != null ? `${Math.round(lim.interval)} s` : "--", "interval"],
      [lim.cooldown != null ? `${Math.round(lim.cooldown)} s` : "--", "kill cooldown"],
    ].map(([v, k]) => `<div><dt>${v}</dt><dd>${k}</dd></div>`).join("");

    this.els.board.innerHTML =
      `<section class="sboard sboard--impactbanner" id="sb-impact-banner" aria-label="Neighbour impact alarm" hidden></section>` +

      `<section class="sboard sboard--alerts" id="sb-alerts" aria-label="Alerts" hidden></section>` +

      `<section class="sboard sboard--gpualarm" id="sb-gpu-guard" aria-label="GPU intrusion alarm" hidden></section>` +

      `<section class="sboard sboard--strip" aria-label="Resource watchdog">` +
      `<div class="strip__seg">` +
      `<i class="wd__light" id="sb-wd-light" aria-hidden="true"></i><span class="wd__label">watchdog</span><span class="wd__mode" id="sb-wd-mode">--</span></div>` +
      `<i class="strip__div" aria-hidden="true"></i>` +
      `<span class="wd__status" id="sb-wd-status">--</span>` +
      `<i class="strip__div" aria-hidden="true"></i>` +
      `<dl class="wd__limits">${limitCells}</dl>` +
      `<div class="strip__actions">` +
      `<button type="button" class="impact__arm" id="sb-detach" title="Detach the backend from your terminal (retroactive nohup): RAM protection and all monitors survive SSH logout">keep-alive: --</button>` +
      `<button type="button" class="impact__arm" id="sb-impact-arm" title="When armed, auto-nukes all your processes if you slow other users too much">auto-nuke: --</button>` +
      `<button type="button" class="impact__arm" id="sb-kill-ui" title="Stop ONLY this web console's server process: running and detached jobs survive and are re-adopted on the next start, but queued launches, watchdogs and TensorBoard viewers die with it">kill front end</button>` +
      `<button type="button" class="wd__nuke" id="sb-nuke" title="Kill every process running under your user">` +
      `<span class="wd__nuke-sym" aria-hidden="true">&#9762;</span><span class="wd__nuke-txt">NUKE</span>` +
      `</button>` +
      `</div>` +
      `</section>` +

      `<section class="sboard sboard--strip sboard--ntf" aria-label="Job notifications">` +
      `<div class="strip__seg">` +
      `<i class="wd__light" id="sb-ntf-light" aria-hidden="true"></i><span class="wd__label">notify</span><span class="wd__mode" id="sb-ntf-mode">--</span></div>` +
      `<i class="strip__div" aria-hidden="true"></i>` +
      `<label class="ntf__field"><span class="ntf__key">ntfy topic</span><input class="ntf__input" id="sb-ntf-topic" type="text" placeholder="pick-a-secret-topic" spellcheck="false" autocomplete="off"></label>` +
      `<label class="ntf__field"><span class="ntf__key">server</span><input class="ntf__input ntf__input--server" id="sb-ntf-server" type="text" spellcheck="false" autocomplete="off"></label>` +
      `<span class="ntf__hint" title="Install the ntfy app (or open ntfy.sh in a browser) and subscribe to the same topic. Every job notifies when it starts and when it ends — direct launches, queued runs and follow-ups alike. Fan-out experiments additionally push the first ETA, 25/50/75% progress milestones and per-unit failures. Failures arrive high-priority.">push to your phone when a job starts, progresses and ends</span>` +
      `<div class="strip__actions">` +
      `<button type="button" class="impact__arm" id="sb-ntf-test" title="Send a test notification to the topic now">test</button>` +
      `<button type="button" class="impact__arm" id="sb-ntf-save" title="Save topic and server">save</button>` +
      `<button type="button" class="impact__arm" id="sb-ntf-toggle" title="Toggle job start/end notifications">notify: --</button>` +
      `</div>` +
      `</section>` +

      `<section class="sboard sboard--strip sboard--sched" aria-label="GPU week schedule">` +
      `<div class="strip__seg">` +
      `<i class="wd__light" id="sb-sch-light" aria-hidden="true"></i><span class="wd__label">gpu week</span><span class="wd__mode" id="sb-sch-mode">--</span></div>` +
      `<i class="strip__div" aria-hidden="true"></i>` +
      `<label class="ntf__field"><span class="ntf__key">weekday</span><input class="ntf__input ntf__input--gpus" id="sb-sch-weekday" type="text" placeholder="2,3" spellcheck="false" autocomplete="off"></label>` +
      `<label class="ntf__field"><span class="ntf__key">night</span><input class="ntf__input ntf__input--gpus" id="sb-sch-night" type="text" placeholder="0,1,2,3" spellcheck="false" autocomplete="off"></label>` +
      `<label class="ntf__field"><span class="ntf__key">weekend</span><input class="ntf__input ntf__input--gpus" id="sb-sch-weekend" type="text" placeholder="0,1,2,3" spellcheck="false" autocomplete="off"></label>` +
      `<i class="strip__div" aria-hidden="true"></i>` +
      `<label class="ntf__field"><span class="ntf__key">night from</span><select class="ntf__input ntf__input--hour" id="sb-sch-nightstart">${GpuWeekPanel.hourOptions()}</select><span class="ntf__key">to</span><select class="ntf__input ntf__input--hour" id="sb-sch-nightend">${GpuWeekPanel.hourOptions()}</select></label>` +
      `<label class="ntf__field"><span class="ntf__key">weekend from</span><select class="ntf__input ntf__input--day" id="sb-sch-startday">${GpuWeekPanel.dayOptions()}</select><select class="ntf__input ntf__input--hour" id="sb-sch-starthour">${GpuWeekPanel.hourOptions()}</select></label>` +
      `<label class="ntf__field"><span class="ntf__key">to</span><select class="ntf__input ntf__input--day" id="sb-sch-endday">${GpuWeekPanel.dayOptions()}</select><select class="ntf__input ntf__input--hour" id="sb-sch-endhour">${GpuWeekPanel.hourOptions()}</select></label>` +
      `<span class="ntf__hint" id="sb-sch-hint" title="Running fan-outs are moved onto the pool of the phase they cross into: the weekend window wins, otherwise the night pool applies between the night hours and the weekday pool covers the rest. A GPU another user is computing on is never taken. Only the switch is automatic: a manual resize from a console tile stands until the next switch.">--</span>` +
      `<div class="strip__actions">` +
      `<button type="button" class="impact__arm" id="sb-sch-greedy" title="Greedy mode: a GPU held by someone else at the switch is re-checked every 10 minutes and picked up once it frees, until the phase pool is whole. Off, the switch takes whatever is free at that moment and nothing changes it afterwards but you.">greedy: --</button>` +
      `<button type="button" class="impact__arm" id="sb-sch-charity" title="Charity mode: when someone's run bounces off your full GPUs (their process joined a GPU you hold and died while no GPU on the machine was free), one of your GPUs is freed for their retry (it opens once the unit in flight finishes) and greedy sleeps for 4 hours so it is not taken back. One GPU per nap, and no job is ever left without a GPU.">charity: --</button>` +
      `<button type="button" class="impact__arm" id="sb-sch-save" title="Save the weekday, night and weekend GPU pools">save</button>` +
      `<button type="button" class="impact__arm" id="sb-sch-toggle" title="Toggle the automatic weekday/night/weekend GPU switch">schedule: --</button>` +
      `</div>` +
      `</section>` +

      `<section class="sboard sboard--gpus" aria-label="CUDA devices">` +
      `<div class="sboard__gputop">` +
      `<div class="gpudeck">` +
      `<header class="sboard__cap"><span>cuda devices</span><span class="sboard__n">${gpus.length}</span></header>` +
      `<div class="sboard__gpugrid">${gpuCards}</div>` +
      `</div>` +

      `<section class="sboard sboard--cpu" aria-label="Processor">` +
      `<header class="sboard__cap"><span>processor</span><span class="sboard__n">${sys.cpu ? sys.cpu.count : 0} cores</span></header>` +
      `<div class="cpu__top">` +
      `<canvas class="gdial gdial--cpu" id="sb-cpu-dial"></canvas>` +
      `<div class="cpu__side">` +
      `<dl class="cpu__load"><div><dt id="sb-load1">--</dt><dd>load 1m</dd></div><div><dt id="sb-load5">--</dt><dd>5m</dd></div><div><dt id="sb-load15">--</dt><dd>15m</dd></div></dl>` +
      `<div class="sboard__metric"><span>avg usage</span><span id="sb-cpu-avg">--</span></div>` +
      `<div class="bar"><i class="bar__fill" id="sb-cpu-bar"></i></div>` +
      `<div class="sboard__metric"><span>active cores</span><span id="sb-cpu-active">--</span></div>` +
      `<div class="bar"><i class="bar__fill bar__fill--cores" id="sb-cores-bar"></i></div>` +
      `</div>` +
      `</div>` +
      `<canvas class="sboard__graph" id="sb-cpu-graph"></canvas>` +
      `<div class="cpu__grid" id="sb-cores">${coreCells}</div>` +
      `</section>` +

      `</div>` +
      `</section>` +

      `<section class="sboard sboard--mem" aria-label="Memory">` +
      `<header class="sboard__cap"><span>memory</span><span class="sboard__n" id="sb-mem-total"></span></header>` +
      `<div class="mem__tanks">` +
      `<div class="mem__tank"><canvas class="gtank" id="sb-ram-tank"></canvas><span class="mem__tlabel">ram</span><span class="mem__tval" id="sb-ram-txt">--</span></div>` +
      `<div class="mem__tank"><canvas class="gtank" id="sb-swap-tank"></canvas><span class="mem__tlabel">swap</span><span class="mem__tval" id="sb-swap-txt">--</span></div>` +
      `</div>` +
      `<canvas class="sboard__graph sboard__graph--mem" id="sb-mem-graph"></canvas>` +
      `</section>` +

      `<section class="sboard sboard--disk" aria-label="Storage">` +
      `<header class="sboard__cap"><span>storage</span><span class="sboard__n" id="sb-disk-total"></span></header>` +
      `<div class="sboard__metric"><span class="sboard__path" id="sb-disk-path"></span><span id="sb-disk-txt">--</span></div>` +
      `<div class="bar"><i class="bar__fill" id="sb-disk-bar"></i></div>` +
      `<div class="sboard__metric"><span>free &middot; all users</span><span id="sb-disk-free">--</span></div>` +
      `<div class="sboard__metric"><span class="sboard__path" id="sb-disk-user-path">${SharedCharts.esc(sys.user || "user")} &middot; total</span><span id="sb-disk-user">--</span></div>` +
      `<div class="bar"><i class="bar__fill bar__fill--user" id="sb-disk-user-bar"></i></div>` +
      `<div class="sboard__metric"><span class="sboard__path" id="sb-disk-repo-path">dlr root</span><span id="sb-disk-repo">--</span></div>` +
      `<div class="bar"><i class="bar__fill bar__fill--repo" id="sb-disk-repo-bar"></i></div>` +
      `</section>` +

      `<section class="sboard sboard--impact" aria-label="Neighbour impact">` +
      `<header class="sboard__cap"><span>neighbour impact</span><i class="impact__light" id="sb-impact-light" aria-hidden="true"></i><span class="sboard__n" id="sb-impact-verdict">--</span></header>` +
      `<p class="impact__lede" id="sb-impact-lede">measuring whether your jobs stall other users&hellip;</p>` +
      `<div class="impact__grid">` +
      `<div class="impact__cell"><canvas class="gmeter gmeter--impact" id="sb-impact-mem-meter"></canvas><span class="impact__share" id="sb-impact-mem-share">your share --</span><div class="bar bar--share"><i class="bar__fill bar__fill--share" id="sb-impact-mem-share-bar"></i></div></div>` +
      `<div class="impact__cell"><canvas class="gmeter gmeter--impact" id="sb-impact-io-meter"></canvas><span class="impact__share" id="sb-impact-io-share">your share --</span><div class="bar bar--share"><i class="bar__fill bar__fill--share" id="sb-impact-io-share-bar"></i></div></div>` +
      `<div class="impact__cell"><canvas class="gmeter gmeter--impact" id="sb-impact-cpu-meter"></canvas><span class="impact__share" id="sb-impact-cpu-share">your share --</span><div class="bar bar--share"><i class="bar__fill bar__fill--share" id="sb-impact-cpu-share-bar"></i></div></div>` +
      `</div>` +
      `<dl class="impact__stats">` +
      `<div><dt id="sb-impact-swap">--</dt><dd>swap out</dd></div>` +
      `<div><dt id="sb-impact-iorate">--</dt><dd>disk busy</dd></div>` +
      `<div><dt id="sb-impact-mine">--</dt><dd>your procs</dd></div>` +
      `<div><dt id="sb-impact-top">--</dt><dd>top ram user</dd></div>` +
      `</dl>` +
      `</section>` +

      `<section class="sboard sboard--impactlog" id="sb-impact-log" aria-label="Neighbour impact alarms" hidden></section>` +

      this.usersTable.markup() +
      this.processTable.markup(sys.user) +
      this.jobsList.markup() +

      `<section class="sboard sboard--gpuguard" id="sb-gpu-guard-panel" aria-label="GPU guard"></section>`;

    this.gpuEls = [...this.els.board.querySelectorAll(".gcard")].map((card, i) => ({
      vramTxt: card.querySelector(".gcard__vram"),
      temp: card.querySelector(".gcard__temp"),
      who: card.querySelector(".gcard__who"),
      power: card.querySelector(".gcard__power"),
      graph: card.querySelector(".gcard__graph"),
      dialU: new window.DialGauge(card.querySelector(".gdial--util"), { big: true, label: "UTIL %", color: "111, 155, 255", majors: 5, minors: 4 }),
      meterT: new window.LinearMeter(card.querySelector(".gmeter--temp"), { min: 20, max: 100, label: "TEMP °C", color: "45, 212, 191", zones: [{ from: 70, to: 85, color: "251, 191, 36" }, { from: 85, to: 100, color: "248, 113, 113" }] }),
      meterP: new window.LinearMeter(card.querySelector(".gmeter--power"), { max: (gpus[i] && gpus[i].power_limit) || 250, label: "POWER W", color: "167, 139, 250" }),
      vseg: new window.SegMeter(card.querySelector(".gseg"), { color: "45, 212, 191" }),
    }));

    this.cpuDial = new window.DialGauge(document.getElementById("sb-cpu-dial"), { big: true, label: "BUSY %", color: "111, 155, 255", majors: 5, minors: 4, zones: [{ from: 75, to: 90, color: "251, 191, 36" }, { from: 90, to: 100, color: "248, 113, 113" }] });
    this.ramTank = new window.TankGauge(document.getElementById("sb-ram-tank"), { color: "45, 212, 191" });
    this.swapTank = new window.TankGauge(document.getElementById("sb-swap-tank"), { color: "167, 139, 250" });

    this.impactMeters = {
      mem: new window.LinearMeter(document.getElementById("sb-impact-mem-meter"), { label: "MEM STALL %", color: "111, 155, 255", zones: [{ from: 10, to: 25, color: "251, 191, 36" }, { from: 25, to: 100, color: "248, 113, 113" }] }),
      io:  new window.LinearMeter(document.getElementById("sb-impact-io-meter"),  { label: "DISK STALL %", color: "111, 155, 255", zones: [{ from: 25, to: 60, color: "251, 191, 36" }, { from: 60, to: 100, color: "248, 113, 113" }] }),
      cpu: new window.LinearMeter(document.getElementById("sb-impact-cpu-meter"), { label: "CPU STALL %", color: "111, 155, 255", zones: [{ from: 40, to: 70, color: "251, 191, 36" }, { from: 70, to: 100, color: "248, 113, 113" }] }),
    };
    this.coreEls = [...this.els.board.querySelectorAll(".cpu__cell")];

    this._wireNuke();
    this._wireImpactArm();
    this._wireDetach();
    this._wireKillUi();
    this._ntfSeeded = false;
    this._wireNotify();

    this.schedule = new GpuWeekPanel();
    this.schedule.wire();

    if (!window.REDUCED_MOTION && window.gsap) {
      gsap.from(this.els.board.querySelectorAll(".sboard"), { opacity: 0, y: 16, duration: 0.7, stagger: 0.08, ease: "expo.out" });
    }
  }

  _wireNuke() {
    const btn = document.getElementById("sb-nuke");
    if (!btn) return;

    btn.addEventListener("click", async () => {
      const ok = window.confirm("NUKE: this kills EVERY process running under your user (training runs, shells, jobs). The web UI is spared. Continue?");
      if (!ok) return;

      btn.disabled = true;
      btn.classList.add("is-firing");
      try {
        const res = await Api.post("/api/system/nuke");
        if (res && res.ok) {
          Toast.show(`nuke: terminated ${res.signalled}, force-killed ${res.killed}`, "ok");
        } else {
          Toast.show(`nuke failed: ${(res && res.error) || "unknown error"}`, "error");
        }
      } catch (e) {
        Toast.show("nuke failed: network error", "error");
      } finally {
        btn.disabled = false;
        btn.classList.remove("is-firing");
      }
    });
  }

  _wireDetach() {
    const btn = document.getElementById("sb-detach");
    if (!btn) return;

    btn.addEventListener("click", async () => {
      btn.disabled = true;
      try {
        const res = await Api.post("/api/system/detach");
        if (res && res.ok) {
          Toast.show(`backend detached from the terminal (pid ${res.pid}) — protection survives SSH logout, log: ${res.log_path}`, "ok");
          this._renderDetach({ detached: true, pid: res.pid, log_path: res.log_path });
        } else {
          Toast.show(`detach failed: ${(res && res.error) || "unknown error"}`, "error");
          btn.disabled = false;
        }
      } catch (e) {
        Toast.show("detach failed: network error", "error");
        btn.disabled = false;
      }
    });
  }

  _renderDetach(srv) {
    const btn = document.getElementById("sb-detach");
    if (!btn || !srv) return;
    btn.textContent = srv.detached ? "keep-alive: ON" : "keep-alive: off";
    btn.classList.toggle("is-safe", !!srv.detached);
    btn.disabled = !!srv.detached;
    if (srv.detached) btn.title = `backend detached (pid ${srv.pid}) — output continues in ${srv.log_path}`;
  }

  _wireKillUi() {
    const btn = document.getElementById("sb-kill-ui");
    if (!btn) return;

    btn.addEventListener("click", async () => {
      const ok = window.confirm("Kill the front end: this stops ONLY the web console server. Running jobs keep going and are re-adopted on the next start; queued launches and TensorBoard viewers are lost. Continue?");
      if (!ok) return;

      btn.disabled = true;
      try {
        const res = await Api.post("/api/system/shutdown");
        if (res && res.ok) {
          this._serverDown = true;
          btn.textContent = "front end: down";
          btn.classList.add("is-armed");
          Toast.show(`front end stopped (pid ${res.pid}) — running jobs keep going; restart it from the terminal (webui/run.sh)`, "ok");
        } else {
          Toast.show(`shutdown failed: ${(res && res.error) || "unknown error"}`, "error");
          btn.disabled = false;
        }
      } catch (e) {
        Toast.show("shutdown failed: network error", "error");
        btn.disabled = false;
      }
    });
  }

  _wireNotify() {
    const save   = document.getElementById("sb-ntf-save");
    const toggle = document.getElementById("sb-ntf-toggle");
    const test   = document.getElementById("sb-ntf-test");
    if (!save || !toggle || !test) return;

    const submit = async (enabled) => {
      const topic = document.getElementById("sb-ntf-topic");
      const server = document.getElementById("sb-ntf-server");
      const payload = {
        enabled,
        topic: topic ? topic.value.trim() : "",
        server: server ? server.value.trim() : "",
      };
      const res = await Api.post("/api/notify/config", payload);
      if (res && res.ok) {
        this._ntfSeeded = false;
        this._renderNotify(res);
        Toast.show(`notifications ${res.enabled ? "on" : "off"} — settings saved`, "ok");
      } else {
        Toast.show(`notify settings rejected: ${(res && res.error) || "network error"}`, "error");
      }
    };

    save.addEventListener("click", () => submit(!!(this._ntfState || {}).enabled));
    toggle.addEventListener("click", () => submit(!(this._ntfState || {}).enabled));

    test.addEventListener("click", async () => {
      test.disabled = true;
      try {
        const res = await Api.post("/api/notify/test");
        if (res && res.ok) Toast.show("test notification sent — check your device", "ok");
        else Toast.show(`test failed: ${(res && res.error) || "network error"}`, "error");
      } finally {
        test.disabled = false;
      }
    });
  }

  _renderNotify(ntf) {
    if (!ntf) return;
    this._ntfState = ntf;

    const light  = document.getElementById("sb-ntf-light");
    const mode   = document.getElementById("sb-ntf-mode");
    const toggle = document.getElementById("sb-ntf-toggle");
    const on     = !!ntf.enabled;
    if (light) light.classList.toggle("is-armed", on);
    if (mode) {
      mode.textContent = on ? "armed" : "off";
      mode.classList.toggle("is-off", !on);
    }
    if (toggle) {
      toggle.textContent = on ? "notify: ON" : "notify: off";
      toggle.classList.toggle("is-safe", on);
    }

    if (!this._ntfSeeded) {
      this._ntfSeeded = true;
      const topic = document.getElementById("sb-ntf-topic");
      const server = document.getElementById("sb-ntf-server");
      if (topic) topic.value = ntf.topic || "";
      if (server) server.value = ntf.server || "";
    }
  }

  _wireImpactArm() {
    const btn = document.getElementById("sb-impact-arm");
    if (!btn) return;

    btn.addEventListener("click", async () => {
      const arming = !this._autoNuke;
      if (arming) {
        const ok = window.confirm("ARM AUTO-NUKE: if your jobs slow other users too much (severe memory/disk stalling that you are the dominant cause of, sustained ~30s), this will SIGTERM/SIGKILL every process running under your user, sparing only the web UI. Arm it?");
        if (!ok) return;
      }
      btn.disabled = true;
      try {
        const res = await Api.post("/api/impact/arm", { armed: arming });
        if (res && typeof res.auto_nuke === "boolean") {
          this._autoNuke = res.auto_nuke;
          Toast.show(`auto-nuke ${res.auto_nuke ? "armed" : "disarmed"}`, res.auto_nuke ? "warn" : "ok");
        }
      } catch (e) {
        Toast.show("auto-nuke toggle failed: network error", "error");
      } finally {
        btn.disabled = false;
      }
    });
  }

  _update(sys) {
    window.serverScene.feed(sys);
    this._renderWatchdog(sys.alerts || {});
    this._renderAlerts(sys.alerts || {});
    this._renderImpact(sys.impact || {});
    this._renderGpuGuard(sys.gpu_guard || {});
    this._renderDetach(sys.server);
    this._renderNotify(sys.notify);
    if (this.schedule) this.schedule.render(sys.gpu_schedule);
    const cpu = sys.cpu || {};
    const mem = sys.mem || {};
    const disk = sys.disk || {};
    const gpus = sys.gpus || [];
    const hist = sys.history || {};
    const gpuHist = hist.gpus || {};
    this.histMax = hist.max_samples || this.histMax;

    if (this.els.host) this.els.host.textContent = sys.host || "server";
    if (this.els.sum) {
      const bits = [];
      if (sys.uptime) bits.push(`up ${this._uptime(sys.uptime)}`);
      if (cpu.count) bits.push(`${cpu.count} cores`);
      bits.push(sys.gpus_known ? `${gpus.length} CUDA device${gpus.length === 1 ? "" : "s"}` : "CUDA devices unknown");
      if (mem.total) bits.push(`${ByteFormat.tb(mem.total)} ram`);
      this.els.sum.textContent = bits.join(" · ");
    }

    gpus.forEach((g, i) => {
      const el = this.gpuEls[i];
      const h = gpuHist[String(g.index != null ? g.index : i)] || { util: [], mem: [] };
      if (!el) return;
      const util = g.util != null ? g.util : 0;
      const memPct = g.mem_total ? (100 * g.mem_used) / g.mem_total : 0;

      el.dialU.set(util);
      el.meterT.set(g.temp);
      if (g.power_limit) el.meterP.range(g.power_limit);
      el.meterP.set(g.power);
      el.vseg.set(memPct / 100);
      el.vramTxt.innerHTML = `<b>${ByteFormat.gb(g.mem_used * 1048576)}</b> / ${ByteFormat.gb(g.mem_total * 1048576)} GB`;
      el.temp.textContent = g.temp != null ? `${Math.round(g.temp)}°C` : "--";
      el.temp.className = "gcard__temp" + (g.temp >= 85 ? " is-danger" : g.temp >= 70 ? " is-warn" : "");

      const holders = (g.holders || []).join(", ");
      if (holders) {
        el.who.textContent = holders;
        el.who.className = "gcard__who " + (g.others ? "is-others" : "is-mine");
      } else if (g.stale) {
        el.who.textContent = "stale memory";
        el.who.className = "gcard__who is-stale";
      } else {
        el.who.textContent = "";
        el.who.className = "gcard__who";
      }
      el.power.textContent = g.power != null ? `${Math.round(g.power)}${g.power_limit ? ` / ${Math.round(g.power_limit)}` : ""} W` : "--";
      this._spark(el.graph, [
        { data: h.mem, color: "45, 212, 191", fill: 0.08 },
        { data: h.util, color: "111, 155, 255", fill: 0.14 },
      ]);
    });

    if (this.cpuDial) this.cpuDial.set(cpu.total || 0);
    const load = cpu.load || [];
    ["sb-load1", "sb-load5", "sb-load15"].forEach((id, i) => {
      const el = document.getElementById(id);
      if (el && load[i] != null) el.textContent = load[i].toFixed(1);
    });
    const cores = cpu.cores || [];
    cores.forEach((u, i) => {
      const cell = this.coreEls[i];
      if (!cell) return;
      const a = 0.06 + Math.min(1, u / 100) * 0.84;
      cell.style.background = `rgba(111, 155, 255, ${a.toFixed(3)})`;
      cell.title = `core ${i} · ${Math.round(u)}%`;
    });

    if (cores.length) {
      const avg    = cores.reduce((s, u) => s + u, 0) / cores.length;
      const active = cores.filter((u) => u >= 50).length;
      this._bar("sb-cpu-bar", avg);
      this._bar("sb-cores-bar", (100 * active) / cores.length);
      this._txt("sb-cpu-avg", `<b>${avg.toFixed(1)}</b> %`);
      this._txt("sb-cpu-active", `<b>${active}</b> / ${cores.length} dispatched`);
    }
    this._spark(document.getElementById("sb-cpu-graph"), [{ data: hist.cpu || [], color: "111, 155, 255", fill: 0.14 }]);

    if (mem.total) {
      const used = mem.total - mem.available;
      this.ramTank.set(used / mem.total);
      this._txt("sb-ram-txt", `<b>${ByteFormat.gb(used)}</b> / ${ByteFormat.gb(mem.total)} GB`);
      this._txt("sb-mem-total", `${ByteFormat.tb(mem.total)}`);
      const swapUsed = (mem.swap_total || 0) - (mem.swap_free || 0);
      this.swapTank.set(mem.swap_total ? swapUsed / mem.swap_total : 0);
      this._txt("sb-swap-txt", mem.swap_total ? `<b>${ByteFormat.gb(swapUsed)}</b> / ${ByteFormat.gb(mem.swap_total)} GB` : "none");
      this._spark(document.getElementById("sb-mem-graph"), [{ data: hist.ram || [], color: "45, 212, 191", fill: 0.10 }]);
    }

    if (disk.total) {
      this._bar("sb-disk-bar", (100 * disk.used) / disk.total);
      this._txt("sb-disk-txt", `<b>${ByteFormat.tb(disk.used)}</b> / ${ByteFormat.tb(disk.total)}`);
      this._txt("sb-disk-total", ByteFormat.tb(disk.total));
      this._txt("sb-disk-free", `<b>${ByteFormat.tb(disk.free)}</b>`);
      const path = document.getElementById("sb-disk-path");
      if (path) path.textContent = disk.path || "";

      const userPath = document.getElementById("sb-disk-user-path");
      if (userPath && disk.user_path) userPath.title = disk.user_path;
      this._txt("sb-disk-user", disk.user_used != null ? `<b>${ByteFormat.tb(disk.user_used)}</b>` : "scanning&hellip;");
      this._bar("sb-disk-user-bar", disk.user_used ? (100 * disk.user_used) / disk.total : 0);

      const repoPath = document.getElementById("sb-disk-repo-path");
      if (repoPath && disk.repo_path) repoPath.title = disk.repo_path;
      this._txt("sb-disk-repo", disk.repo_used != null ? `<b>${ByteFormat.tb(disk.repo_used)}</b>` : "scanning&hellip;");
      this._bar("sb-disk-repo-bar", disk.repo_used ? (100 * disk.repo_used) / disk.total : 0);
    }

    this.usersTable.render(sys.users || []);
    this.processTable.render(sys.procs || []);
  }

  _renderWatchdog(alerts) {
    const light = document.getElementById("sb-wd-light");
    const mode = document.getElementById("sb-wd-mode");
    const status = document.getElementById("sb-wd-status");
    if (!light || !mode || !status) return;

    const armed = !!alerts.armed;
    const active = (alerts.active || []).length;

    light.classList.toggle("is-armed", armed);
    mode.textContent = armed ? "armed" : "offline";
    mode.classList.toggle("is-off", !armed);
    status.textContent = active ? `${active} active alert${active === 1 ? "" : "s"}` : "all clear";
    status.classList.toggle("is-alert", active > 0);
  }

  _renderAlerts(alerts) {
    const box = document.getElementById("sb-alerts");
    if (!box) return;

    const active = alerts.active || [];
    const events = (alerts.events || []).slice(-3);
    if (!active.length && !events.length) {
      box.hidden = true;
      box.innerHTML = "";
      return;
    }

    const chips = active.map((a) =>
      `<span class="alert alert--${a.level === "danger" ? "danger" : "warn"}">${SharedCharts.esc(a.message)}</span>`
    ).join("");
    const log = events.map((e) =>
      `<span class="alert alert--event"><b>${SharedCharts.esc(e.time.replace("T", " "))}</b> ${SharedCharts.esc(e.message)}</span>`
    ).join("");

    box.hidden = false;
    box.innerHTML = `<header class="sboard__cap"><span>alerts</span><span class="sboard__n">${active.length} active</span></header><div class="alert__list">${chips}${log}</div>`;
  }

  _renderImpact(impact) {
    const sig        = impact.signals || {};
    const active     = impact.active || [];
    const leak       = active.find((a) => a.kind === "leak");
    const contention = active.filter((a) => a.kind !== "leak");
    const mine       = contention.filter((a) => a.mine);
    const others     = contention.filter((a) => !a.mine);

    this._autoNuke = !!impact.auto_nuke;
    const armBtn = document.getElementById("sb-impact-arm");
    if (armBtn) {
      armBtn.textContent = this._autoNuke ? "auto-nuke: ARMED" : "auto-nuke: off";
      armBtn.classList.toggle("is-armed", this._autoNuke);
    }

    const psi  = sig.psi || {};
    const mem  = sig.mem || {};
    const io   = sig.io || {};
    const cpu  = sig.cpu || {};
    const swap = sig.swap || {};

    const contended = new Set(contention.map((a) => a.kind));
    const gauge = (kind, psiVal, shareVal) => {
      const meter = (this.impactMeters || {})[kind];
      if (meter) meter.set(psiVal || 0);
      const shareId  = `sb-impact-${kind}-share`;
      const sharePct = (shareVal || 0) * 100;
      this._txt(shareId, `your share <b>${sharePct.toFixed(0)}</b>%`);
      const shareEl = document.getElementById(shareId);
      if (shareEl) shareEl.classList.toggle("is-dominant", sharePct >= 50 && contended.has(kind));
      this._bar(`${shareId}-bar`, sharePct);
    };
    gauge("mem", (psi.mem || {}).some, mem.mine_share);
    gauge("io",  (psi.io  || {}).some, io.mine_share);
    gauge("cpu", (psi.cpu || {}).some, cpu.mine_share);

    this._txt("sb-impact-swap", `<b>${(swap.out_mbs || 0).toFixed(1)}</b> MB/s`);
    this._txt("sb-impact-iorate", `<b>${(io.util || 0).toFixed(0)}</b> %`);
    this._txt("sb-impact-mine", `<b>${(sig.mine || {}).nproc || 0}</b> &middot; ${((sig.mine || {}).mem_gb || 0).toFixed(1)}G`);

    const top = sig.top;
    const topEl = document.getElementById("sb-impact-top");
    if (topEl) {
      topEl.innerHTML = top ? `<b>${SharedCharts.esc(top.user)}</b> &middot; ${(top.mem_gb || 0).toFixed(1)}G` : "--";
      topEl.classList.toggle("is-other", !!(top && !top.is_mine));
    }

    const light   = document.getElementById("sb-impact-light");
    const verdict = document.getElementById("sb-impact-verdict");
    const lede    = document.getElementById("sb-impact-lede");
    let culprit = mine.some((a) => a.level === "danger") ? "danger" : mine.length ? "warn" : "clear";
    if (culprit === "clear" && leak) culprit = "warn";
    if (light) light.className = `impact__light is-${culprit}`;
    if (verdict) {
      verdict.textContent = mine.length ? "you are the cause" : leak ? "ram climbing" : others.length ? "busy, not you" : "all clear";
    }
    if (lede) {
      lede.textContent = mine.length
        ? "Your jobs are stalling other users on the resources flagged below."
        : leak
          ? "No contention yet, but a process of yours is steadily accumulating RAM — see below."
          : others.length
            ? (top && !top.is_mine
                ? `The server is contended, but not by you — dominant consumer is ${top.user} (${(top.mem_gb || 0).toFixed(0)} GB, ${top.nproc} procs).`
                : "The server is contended, but your jobs are not the dominant cause.")
            : "No contention: other users are not being slowed by your jobs.";
    }

    const logBox = document.getElementById("sb-impact-log");
    if (logBox) {
      const cards = active.map((a) =>
        `<div class="impact__alarm impact__alarm--${a.level === "danger" ? "danger" : "warn"}${a.mine ? " is-mine" : ""}">` +
        `<span class="impact__alarm-tag">${a.mine ? "you" : "others"} &middot; ${SharedCharts.esc(a.kind)}</span>` +
        `<span class="impact__alarm-msg">${SharedCharts.esc(a.message)}</span></div>`
      ).join("");
      const events = (impact.events || []).slice(-3).reverse().map((e) =>
        `<div class="impact__alarm impact__alarm--${e.kind === "auto_nuke" ? "danger" : "warn"} is-event">` +
        `<span class="impact__alarm-tag">${SharedCharts.esc(e.time.replace("T", " "))} &middot; ${SharedCharts.esc(e.kind)}</span>` +
        `<span class="impact__alarm-msg">${SharedCharts.esc(e.message)}</span></div>`
      ).join("");
      const content = cards + events;
      logBox.hidden = !content;
      logBox.innerHTML = content
        ? `<header class="sboard__cap"><span>neighbour impact &middot; alarms &amp; history</span><span class="sboard__n">${active.length} active</span></header><div class="impact__alarmgrid">${content}</div>`
        : "";
    }

    const banner = document.getElementById("sb-impact-banner");
    if (banner) {
      if (mine.length) {
        const worst = mine.some((a) => a.level === "danger") ? "danger" : "warn";
        banner.hidden = false;
        banner.className = `sboard sboard--impactbanner is-${worst}`;
        banner.innerHTML =
          `<span class="impactbanner__sym" aria-hidden="true">&#9888;</span>` +
          `<div class="impactbanner__body"><span class="impactbanner__head">you are slowing other users</span>` +
          mine.map((a) => `<span class="impactbanner__line">${SharedCharts.esc(a.message)}</span>`).join("") +
          `</div>`;
        if (!this._impactWasFiring) { this._impactWasFiring = true; this._alarm(worst === "danger"); }
      } else {
        banner.hidden = true;
        banner.innerHTML = "";
        this._impactWasFiring = false;
      }
    }
  }

  _renderGpuGuard(guard) {
    this._guardState = guard;
    this._renderGuardPanel();

    const box = document.getElementById("sb-gpu-guard");
    if (!box) return;

    if (typeof guard.count === "number") {
      if (this._guardCount == null) this._guardCount = guard.count;
      else if (guard.count > this._guardCount) { this._guardCount = guard.count; this._alarm(false); this._pollGuardHistory(); }
    }
    if (typeof guard.critical === "number") {
      if (this._critCount == null) this._critCount = guard.critical;
      else if (guard.critical > this._critCount) { this._critCount = guard.critical; this._alarm(true); this._pollGuardHistory(); }
    }

    const active = guard.active || [];
    const gpus = guard.gpus || [];
    const events = (guard.events || []).slice(-5).reverse();
    const crit = active.filter((a) => a.status === "critical").length;

    if (!active.length && !events.length) {
      box.hidden = true;
      box.innerHTML = "";
      box.classList.remove("is-firing", "is-critical");
      return;
    }

    const context = gpus.length
      ? `<div class="alarm__sect"><span class="alarm__sect-cap">contested devices</span>` +
        `<div class="gpuctx">` + gpus.map((g) => {
          const who = g.free ? "free" : (g.holders || []).map((h) => SharedCharts.esc(h.user)).join(", ");
          const kind = g.free ? "is-free" : g.others ? (g.mine ? "is-clash" : "is-others") : "is-mine";
          return `<span class="gpuctx__cell ${kind}" title="gpu ${g.index} &middot; ${Math.round(g.util || 0)}% util">gpu ${g.index} &middot; ${who}</span>`;
        }).join("") + `</div></div>`
      : "";

    const cards = active.map((a) => {
      if (a.status === "critical") {
        const dead = SharedCharts.esc((a.dead_pids || a.mine_pids || []).join(", "));
        return (
          `<div class="aint aint--critical">` +
          `<span class="aint__sev">&#9760; critical</span>` +
          `<div class="aint__main">` +
          `<span class="aint__head">gpu ${a.gpu_index}<i>${SharedCharts.esc(a.gpu_name || "")}</i></span>` +
          `<span class="aint__detail">your pid(s) <b>${dead}</b> died after <b>${SharedCharts.esc(a.user)}</b> (pid ${a.pid}) invaded</span>` +
          `</div></div>`
        );
      }
      return (
        `<div class="aint aint--danger">` +
        `<span class="aint__sev">intrusion</span>` +
        `<div class="aint__main">` +
        `<span class="aint__head">gpu ${a.gpu_index}<i>${SharedCharts.esc(a.gpu_name || "")}</i></span>` +
        `<span class="aint__detail">intruder <b>${SharedCharts.esc(a.user)}</b> &middot; pid ${a.pid} &middot; ${Math.round(a.mem_mib)} MiB &middot; clashes with your pids ${SharedCharts.esc((a.mine_pids || []).join(", "))}</span>` +
        `</div></div>`
      );
    }).join("");
    const activeSect = cards
      ? `<div class="alarm__sect"><span class="alarm__sect-cap">live intrusions</span><div class="alarm__active">${cards}</div></div>`
      : "";

    const log = events.map((e) => {
      const stamp = (e.critical_at || e.since || "").replace("T", " ");
      const tag = e.status === "critical" ? `<b class="alert__crit">killed</b>` : `<b>seen</b>`;
      return `<span class="alarm__evt">${tag}<span class="alarm__evt-time">${SharedCharts.esc(stamp)}</span><span>${SharedCharts.esc(e.user)} &middot; gpu ${e.gpu_index} &middot; pid ${e.pid}</span></span>`;
    }).join("");
    const logSect = log
      ? `<div class="alarm__sect"><span class="alarm__sect-cap">recent events</span><div class="alarm__log">${log}</div></div>`
      : "";

    box.hidden = false;
    box.classList.toggle("is-firing", active.length > 0);
    box.classList.toggle("is-critical", crit > 0);
    const cap = crit ? `${crit} critical &middot; ${active.length} active` : `${active.length} active`;
    box.innerHTML =
      `<div class="alarm__bar">` +
      `<span class="alarm__beacon" aria-hidden="true"></span>` +
      `<span class="alarm__title">gpu intrusion ${active.length ? "detected" : "log"}</span>` +
      `<span class="alarm__count">${cap}</span>` +
      `</div>` +
      `<span class="alarm__sweep" aria-hidden="true"></span>` +
      `${context}${activeSect}${logSect}`;
  }

  _renderGuardPanel() {
    const panel = document.getElementById("sb-gpu-guard-panel");
    if (!panel) return;

    const g = this._guardState || {};
    const h = this._guardHistory || {};
    const active = (g.active || []);
    const crit = active.filter((a) => a.status === "critical").length;
    const total = h.total != null ? h.total : (g.count || 0);

    let statusTxt, statusCls;
    if (crit) { statusTxt = `${crit} critical`; statusCls = "is-critical"; }
    else if (active.length) { statusTxt = `${active.length} active`; statusCls = "is-active"; }
    else if (g.armed) { statusTxt = "all clear"; statusCls = "is-clear"; }
    else { statusTxt = "offline"; statusCls = "is-off"; }

    const records = h.records || [];
    const rows = records.length
      ? records.map((r) => {
          const kind = r.kind === "critical" ? "critical" : "intrusion";
          const stamp = (r.critical_at || r.detected_at || "").replace("T", " ");
          const intr = r.intruder || {};
          const gpu = r.gpu || {};
          const label = kind === "critical" ? "process killed" : "intrusion";
          const extra = kind === "critical" && r.dead_pids ? ` (your pid ${SharedCharts.esc(r.dead_pids.join(", "))} died)` : "";
          return (
            `<div class="ghist__row is-${kind}" title="${SharedCharts.esc(this._guardCtx(r.all_gpus))}">` +
            `<span class="ghist__time">${SharedCharts.esc(stamp)}</span>` +
            `<span class="ghist__kind">${label}</span>` +
            `<span class="ghist__user">${SharedCharts.esc(intr.user || "?")}</span>` +
            `<span class="ghist__gpu">gpu ${gpu.index != null ? gpu.index : "?"}</span>` +
            `<span class="ghist__mem">${intr.mem_mib != null ? Math.round(intr.mem_mib) + " MiB" : "--"}</span>` +
            `<span class="ghist__cmd" title="${SharedCharts.esc(intr.cmd || "")}">${SharedCharts.esc(intr.cmd || "")}${extra}</span>` +
            `</div>`
          );
        }).join("")
      : `<div class="sboard__empty">no infractions on record</div>`;

    panel.innerHTML =
      `<header class="sboard__cap"><span>gpu guard</span>` +
      `<span class="ggd__status ${statusCls}"><i class="ggd__light"></i>${statusTxt}</span></header>` +
      `<div class="ghist__meta"><span>${total} infraction${total === 1 ? "" : "s"} on record</span><span class="ghist__path" title="${SharedCharts.esc(h.log_path || "")}">${SharedCharts.esc(h.log_path || "")}</span></div>` +
      `<div class="ghist"><div class="ghist__row ghist__row--head"><span>time</span><span>event</span><span>user</span><span>gpu</span><span>mem</span><span>command</span></div><div class="ghist__body">${rows}</div></div>`;
  }

  _guardCtx(gpus) {
    if (!gpus || !gpus.length) return "";
    return "context · " + gpus.map((x) => {
      const who = x.free ? "free" : (x.mine && x.others ? "you+others" : (x.mine ? "you" : ((x.holders || [])[0] || {}).user || "others"));
      return `gpu${x.index}:${who}`;
    }).join("  ");
  }

  _audioContext() {
    const Ctx = window.AudioContext || window.webkitAudioContext;
    if (!Ctx) return null;
    this._actx = this._actx || new Ctx();

    if (this._actx.state === "suspended" && !this._resumeHooked) {
      this._resumeHooked = true;
      const resume = () => {
        this._actx.resume();
        document.removeEventListener("pointerdown", resume);
        document.removeEventListener("keydown", resume);
      };
      document.addEventListener("pointerdown", resume);
      document.addEventListener("keydown", resume);
      this._actx.resume();
    }

    return this._actx;
  }

  _alarm(critical) {
    Toast.show(critical ? "CRITICAL: your process died after a GPU intrusion" : "GPU intrusion: another user is on a GPU you are using", "error");
    try {
      const ctx = this._audioContext();
      if (!ctx) return;
      const t0 = ctx.currentTime;
      const beeps = critical ? [0, 0.16, 0.32, 0.48, 0.64] : [0, 0.2, 0.4];
      const freq = critical ? 1320 : 880;
      beeps.forEach((dt) => {
        const osc = ctx.createOscillator();
        const gain = ctx.createGain();
        osc.type = "square";
        osc.frequency.setValueAtTime(freq, t0 + dt);
        gain.gain.setValueAtTime(0.0001, t0 + dt);
        gain.gain.exponentialRampToValueAtTime(0.25, t0 + dt + 0.02);
        gain.gain.exponentialRampToValueAtTime(0.0001, t0 + dt + 0.13);
        osc.connect(gain);
        gain.connect(ctx.destination);
        osc.start(t0 + dt);
        osc.stop(t0 + dt + 0.15);
      });
    } catch (e) {}
  }

  _spark(cv, series) {
    if (!cv) return;
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    const w = cv.clientWidth;
    const h = cv.clientHeight;
    if (!w || !h) return;
    if (cv.width !== Math.round(w * dpr) || cv.height !== Math.round(h * dpr)) {
      cv.width = Math.round(w * dpr);
      cv.height = Math.round(h * dpr);
    }
    const ctx = cv.getContext("2d");
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, w, h);

    ctx.fillStyle = "rgba(6, 10, 14, 0.55)";
    ctx.fillRect(0, 0, w, h);
    ctx.strokeStyle = "rgba(220, 235, 245, 0.10)";
    ctx.lineWidth = 1;
    ctx.strokeRect(0.5, 0.5, w - 1, h - 1);

    ctx.setLineDash([1, 4]);
    ctx.strokeStyle = "rgba(220, 235, 245, 0.16)";
    [0.25, 0.5, 0.75].forEach((f) => {
      const y = Math.round(h * f) + 0.5;
      ctx.beginPath();
      ctx.moveTo(2, y);
      ctx.lineTo(w - 2, y);
      ctx.stroke();
    });
    const cols = Math.max(4, Math.round(w / 46));
    for (let c = 1; c < cols; c++) {
      const x = Math.round((c / cols) * w) + 0.5;
      ctx.beginPath();
      ctx.moveTo(x, 2);
      ctx.lineTo(x, h - 2);
      ctx.stroke();
    }
    ctx.setLineDash([]);

    const step = w / (this.histMax - 1);
    series.forEach((s) => {
      const d = s.data;
      if (d.length < 2) return;
      const x0 = w - (d.length - 1) * step;
      const py = (v) => h - 2.5 - (v / 100) * (h - 5);

      ctx.beginPath();
      d.forEach((v, i) => {
        const x = x0 + i * step;
        if (i === 0) ctx.moveTo(x, py(v));
        else ctx.lineTo(x, py(v));
      });
      ctx.strokeStyle = `rgba(${s.color}, 0.95)`;
      ctx.lineWidth = 1.4;
      ctx.shadowColor = `rgba(${s.color}, 0.55)`;
      ctx.shadowBlur = 6;
      ctx.stroke();
      ctx.shadowBlur = 0;

      ctx.lineTo(w, h);
      ctx.lineTo(x0, h);
      ctx.closePath();
      ctx.fillStyle = `rgba(${s.color}, ${s.fill})`;
      ctx.fill();

      const hy = py(d[d.length - 1]);
      ctx.beginPath();
      ctx.arc(w - 2.5, hy, 2.2, 0, Math.PI * 2);
      ctx.fillStyle = `rgba(${s.color}, 1)`;
      ctx.shadowColor = `rgba(${s.color}, 0.9)`;
      ctx.shadowBlur = 8;
      ctx.fill();
      ctx.shadowBlur = 0;
    });
  }

  _bar(id, pct) {
    const el = document.getElementById(id);
    if (!el) return;
    el.style.width = `${Math.max(0, Math.min(100, pct))}%`;
    el.classList.toggle("is-hot", pct >= 90);
  }

  _txt(id, html) {
    const el = document.getElementById(id);
    if (el) el.innerHTML = html;
  }

  _uptime(sec) {
    const d = Math.floor(sec / 86400);
    const h = Math.floor((sec % 86400) / 3600);
    const m = Math.floor((sec % 3600) / 60);
    if (d > 0) return `${d}d ${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}`;
    return `${h}:${String(m).padStart(2, "0")}`;
  }
}

window.StatusBoard = StatusBoard;
