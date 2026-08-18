"use strict";

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
      `<div class="utable__row utable__row--head"><span>user</span><span title="summed over all the user's processes; 100% = one full core">cpu%</span><span title="memory attributed to the user: proportional set size for your own processes, private resident for other users, so shared pages are not double-counted">ram</span><span title="share of used RAM (total minus available)">ram%</span><span class="utable__gpu" title="GPU memory the user has allocated across all CUDA devices">gpu mem</span><span title="CUDA devices the user holds memory on">gpus</span><span title="processes owned by the user">procs</span><span title="open login sessions">ssh</span></div>` +
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

    this.gpuEls = [];
    this.cpuDial = null;
    this.ramTank = null;
    this.swapTank = null;
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

    this.els.board.innerHTML =
      `<section class="sboard sboard--strip" aria-label="Server controls">` +
      `<div class="strip__seg">` +
      `<span class="wd__label">server</span></div>` +
      `<i class="strip__div" aria-hidden="true"></i>` +
      `<div class="strip__actions">` +
      `<button type="button" class="strip__btn" id="sb-detach" title="Detach the backend from your terminal (retroactive nohup): all monitors survive SSH logout">keep-alive: --</button>` +
      `<button type="button" class="strip__btn" id="sb-kill-ui" title="Stop ONLY this web console's server process: running and detached jobs survive and are re-adopted on the next start, but queued launches die with it">kill front end</button>` +
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
      `<button type="button" class="strip__btn" id="sb-ntf-test" title="Send a test notification to the topic now">test</button>` +
      `<button type="button" class="strip__btn" id="sb-ntf-save" title="Save topic and server">save</button>` +
      `<button type="button" class="strip__btn" id="sb-ntf-toggle" title="Toggle job start/end notifications">notify: --</button>` +
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

      this.usersTable.markup() +
      this.processTable.markup(sys.user) +
      this.jobsList.markup();

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
    this.coreEls = [...this.els.board.querySelectorAll(".cpu__cell")];

    this._wireNuke();
    this._wireDetach();
    this._wireKillUi();
    this._ntfSeeded = false;
    this._wireNotify();

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
      const ok = window.confirm("Kill the front end: this stops ONLY the web console server. Running jobs keep going and are re-adopted on the next start; queued launches are lost. Continue?");
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

  _update(sys) {
    window.serverScene.feed(sys);
    this._renderDetach(sys.server);
    this._renderNotify(sys.notify);
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
