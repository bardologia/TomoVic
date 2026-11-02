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
      `<div class="utable__row utable__row--head"><span>user</span><span title="summed over all the user's processes; 100% = one full core">cpu%</span><span title="share of the last 10 s the user's own tasks spent waiting for cpu / ram / disk, read from the user's cgroup pressure files">stall c/m/d</span><span title="memory attributed to the user: proportional set size for your own processes, private resident for other users, so shared pages are not double-counted">ram</span><span title="share of used RAM (total minus available), same base as the neighbour impact panel">ram%</span><span class="utable__gpu" title="GPU memory the user has allocated across all CUDA devices">gpu mem</span><span title="CUDA devices the user holds memory on">gpus</span><span title="processes owned by the user">procs</span><span title="open login sessions">ssh</span></div>` +
      `<div class="utable__body" id="sb-users"></div>` +
      `</div>` +
      `</section>`
    );
  }

  render(users, slices) {
    const body = document.getElementById("sb-users");
    const stallByUid = new Map(slices.map((row) => [row.uid, row.stall]));
    const n = document.getElementById("sb-users-n");
    if (!body) return;
    if (n) n.textContent = `${users.length} user${users.length === 1 ? "" : "s"}`;

    if (!users.length) {
      body.innerHTML = `<div class="sboard__empty">${ThinkingOrb.busy("listening", "measuring user activity…")}</div>`;
      return;
    }

    body.innerHTML = users.map((u) => {
      const cls = u.cpu >= 100 ? "is-hot" : u.cpu >= 25 ? "is-mid" : "";
      const gpus = (u.gpus || []).length ? u.gpus.join(",") : "--";
      const stall = stallByUid.get(u.uid) || null;
      return (
        `<div class="utable__row${u.me ? " is-me" : ""}">` +
        `<span class="utable__user">${SharedCharts.esc(u.user)}${u.me ? `<i class="utable__me">you</i>` : ""}</span>` +
        `<span class="utable__cpu ${cls}">${u.cpu.toFixed(1)}</span>` +
        `<span class="utable__stall${stall && Math.max(stall.cpu, stall.mem, stall.io) >= 20 ? " is-hot" : stall && Math.max(stall.cpu, stall.mem, stall.io) >= 5 ? " is-mid" : ""}">${stall ? `${stall.cpu.toFixed(0)}/${stall.mem.toFixed(0)}/${stall.io.toFixed(0)}` : "--"}</span>` +
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
      `<div class="jobs__body">` +
      `<ul class="sboard__jobs" id="sb-jobs"><li class="sboard__empty">no runs yet</li></ul>` +
      `<div class="jobs__figure"><div class="fig-fill">${HairlineFigure.html("scheduler", 'id="sb-jobs-figure" aria-hidden="true"')}</div></div>` +
      `</div>` +
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
    return `<li class="sboard__job ${cls}${follow ? " sboard__job--follow" : ""}">${mark}${job.status === "running" ? ThinkingOrb.html("working", 20, "running") : `<span class="sboard__jdot" aria-hidden="true"></span>`}<span class="sboard__jname">${name}</span>${prog}<span class="sboard__jstate">${SharedCharts.esc(job.status)}</span></li>`;
  }

  render(jobs) {
    const list = document.getElementById("sb-jobs");
    const n = document.getElementById("sb-jobs-n");
    if (!list) return;

    const running = jobs.filter((j) => j.status === "running").length;
    if (n) n.textContent = running > 0 ? `${running} running` : String(jobs.length);
    this._syncFigure(jobs);

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

  _syncFigure(jobs) {
    const figure = document.getElementById("sb-jobs-figure");
    if (!figure) return;

    const running = jobs.filter((j) => j.status === "running");
    const waiting = jobs.filter((j) => j.status === "queued" || j.status === "scheduled");
    figure.state = {
      jobs: running.map((j) => ({ id: j.job_id, running: true, position: null, of: null }))
        .concat(waiting.map((j, i) => ({ id: j.job_id, running: false, position: i + 1, of: waiting.length }))),
    };
  }
}

class GpuActivityTimeline {
  static ROW_MIN = 30;
  static ROW_MAX = 80;
  static ROW_GAP = 8;
  static AXIS_H  = 18;
  static LABEL_W = 46;
  static MINE    = "111, 155, 255";
  static OTHERS  = "251, 191, 36";
  static UNKNOWN = "45, 212, 191";

  constructor(canvas, readout) {
    this.canvas = canvas;
    this.readout = readout;
    this.state = null;
    this.geom = null;
    this.rows = [];
    this.idle = readout ? readout.textContent : "";

    if (canvas) {
      canvas.addEventListener("mousemove", (event) => this._hover(event));
      canvas.addEventListener("mouseleave", () => this._blur());
    }
  }

  render(state) {
    this.state = state;
    if (!this.canvas || !state) return;

    const rows = Math.max(1, (state.gpus || []).length);
    const gaps = GpuActivityTimeline.AXIS_H + (rows - 1) * GpuActivityTimeline.ROW_GAP;
    this.canvas.parentElement.style.minHeight = `${gaps + rows * GpuActivityTimeline.ROW_MIN}px`;
    this.canvas.parentElement.style.maxHeight = `${gaps + rows * GpuActivityTimeline.ROW_MAX}px`;
    this.draw();
  }

  _segments(bucket) {
    const segs = [];
    if (bucket.mine > 0) segs.push({ color: GpuActivityTimeline.MINE, share: bucket.mine });
    if (bucket.others > 0) segs.push({ color: GpuActivityTimeline.OTHERS, share: bucket.others });
    if (!segs.length && bucket.busy > 0) segs.push({ color: GpuActivityTimeline.UNKNOWN, share: bucket.busy });
    return segs;
  }

  _hourTicks() {
    const g = this.geom;
    const ticks = [];

    for (let t = Math.ceil(g.start / 3600) * 3600; t <= g.now; t += 3600) {
      const date = new Date(t * 1000);
      if (date.getHours() % 3 !== 0) continue;
      ticks.push({ t, label: `${String(date.getHours()).padStart(2, "0")}:00` });
    }
    return ticks;
  }

  _dayTicks() {
    const g = this.geom;
    const midnights = [];
    const cursor = new Date(g.start * 1000);
    cursor.setHours(24, 0, 0, 0);

    while (cursor.getTime() / 1000 <= g.now) {
      midnights.push(cursor.getTime() / 1000);
      cursor.setDate(cursor.getDate() + 1);
    }

    const every = Math.max(1, Math.ceil((midnights.length * 40) / Math.max(1, g.plotW)));
    return midnights.map((t, index) => {
      const date = new Date(t * 1000);
      const label = index % every === 0 ? `${String(date.getDate()).padStart(2, "0")}.${String(date.getMonth() + 1).padStart(2, "0")}` : null;
      return { t, label };
    });
  }

  _axis(ctx, w, top, bottom) {
    const g = this.geom;
    ctx.font = "600 9px ui-monospace, SFMono-Regular, monospace";
    ctx.textBaseline = "top";

    const ticks = g.window > 86400 ? this._dayTicks() : this._hourTicks();
    ticks.forEach(({ t, label }) => {
      const x = Math.round(g.plotX + ((t - g.start) / g.window) * g.plotW) + 0.5;
      ctx.strokeStyle = "rgba(220, 235, 245, 0.12)";
      ctx.beginPath();
      ctx.moveTo(x, top);
      ctx.lineTo(x, bottom);
      ctx.stroke();

      if (!label) return;
      ctx.fillStyle = "rgba(220, 235, 245, 0.81)";
      ctx.textAlign = x > w - 20 ? "right" : "center";
      ctx.fillText(label, Math.min(x, w - 1), bottom + 5);
    });
  }

  draw() {
    const cv = this.canvas;
    const state = this.state;
    if (!cv || !state) return;

    const w = cv.clientWidth;
    const h = cv.clientHeight;
    if (!w || !h) return;

    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    if (cv.width !== Math.round(w * dpr) || cv.height !== Math.round(h * dpr)) {
      cv.width = Math.round(w * dpr);
      cv.height = Math.round(h * dpr);
    }

    const ctx = cv.getContext("2d");
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, w, h);

    const gpus = state.gpus || [];
    const plotX = GpuActivityTimeline.LABEL_W;
    this.geom = {
      start:  state.now - state.window_s,
      now:    state.now,
      window: state.window_s,
      bucket: state.bucket_s,
      plotX,
      plotW:  Math.max(1, w - plotX - 2),
    };
    this.rows = [];

    if (!gpus.length) {
      ctx.fillStyle = "rgba(220, 235, 245, 0.8)";
      ctx.font = "600 11px ui-monospace, SFMono-Regular, monospace";
      ctx.textAlign = "left";
      ctx.textBaseline = "middle";
      ctx.fillText("no GPU activity recorded yet", 2, h / 2);
      return;
    }

    const gaps  = (gpus.length - 1) * GpuActivityTimeline.ROW_GAP;
    const rowH  = Math.min(GpuActivityTimeline.ROW_MAX, Math.max(GpuActivityTimeline.ROW_MIN, (h - GpuActivityTimeline.AXIS_H - gaps) / gpus.length));
    const top   = 0;

    gpus.forEach((gpu, index) => {
      const y = top + index * (rowH + GpuActivityTimeline.ROW_GAP);
      this.rows.push({ y, h: rowH, gpu });

      ctx.fillStyle = "rgba(220, 235, 245, 0.06)";
      ctx.fillRect(plotX, y, this.geom.plotW, rowH);

      ctx.fillStyle = "rgba(220, 235, 245, 0.86)";
      ctx.font = "600 10px ui-monospace, SFMono-Regular, monospace";
      ctx.textAlign = "left";
      ctx.textBaseline = "middle";
      ctx.fillText(`gpu ${gpu.index}`, 0, y + rowH / 2);

      (gpu.buckets || []).forEach((bucket) => {
        if (bucket.t + this.geom.bucket < this.geom.start) return;

        const x0 = plotX + ((bucket.t - this.geom.start) / this.geom.window) * this.geom.plotW;
        const bw = Math.max(1.5, (this.geom.bucket / this.geom.window) * this.geom.plotW);
        const segs = this._segments(bucket);

        segs.forEach((seg, s) => {
          const sh = rowH / segs.length;
          ctx.fillStyle = `rgba(${seg.color}, ${(0.3 + 0.65 * seg.share).toFixed(3)})`;
          ctx.fillRect(x0, y + s * sh, bw, sh);
        });
      });

      ctx.strokeStyle = "rgba(220, 235, 245, 0.10)";
      ctx.lineWidth = 1;
      ctx.strokeRect(plotX + 0.5, y + 0.5, this.geom.plotW - 1, rowH - 1);
    });

    this._axis(ctx, w, top, top + gpus.length * rowH + gaps);
  }

  _hover(event) {
    if (!this.readout || !this.geom || !this.rows.length) return;

    const box = this.canvas.getBoundingClientRect();
    const x = event.clientX - box.left;
    const y = event.clientY - box.top;

    const row = this.rows.find((r) => y >= r.y && y <= r.y + r.h);
    if (!row || x < this.geom.plotX) return this._blur();

    const when = this.geom.start + ((x - this.geom.plotX) / this.geom.plotW) * this.geom.window;
    const bucket = (row.gpu.buckets || []).find((b) => when >= b.t && when < b.t + this.geom.bucket);
    const date = new Date(Math.round(when) * 1000);
    const time = date.toTimeString().slice(0, 5);
    const clock = this.geom.window > 86400 ? `${String(date.getDate()).padStart(2, "0")}.${String(date.getMonth() + 1).padStart(2, "0")} ${time}` : time;

    if (!bucket) {
      this.readout.textContent = `${clock} · gpu ${row.gpu.index} · no record`;
      return;
    }

    const who = (bucket.holders || []).join(", ");
    this.readout.textContent = bucket.busy > 0
      ? `${clock} · gpu ${row.gpu.index} · busy ${Math.round(100 * bucket.busy)}% · util ${bucket.util}% · ${who || "owner unknown"}`
      : `${clock} · gpu ${row.gpu.index} · idle`;
  }

  _blur() {
    if (this.readout) this.readout.textContent = this.idle;
  }
}

class GpuHeatmapCalendar {
  static SLOT_H  = 9;
  static ROW_GAP = 16;
  static LABEL_W = 46;
  static AXIS_H  = 16;
  static SLOTS   = 6;
  static MINE    = "111, 155, 255";
  static OTHERS  = "251, 191, 36";

  constructor(canvas, readout) {
    this.canvas = canvas;
    this.readout = readout;
    this.state = null;
    this.cells = [];
    this.idle = readout ? readout.textContent : "";

    if (canvas) {
      canvas.addEventListener("mousemove", (event) => this._hover(event));
      canvas.addEventListener("mouseleave", () => this._blur());
    }
  }

  render(state) {
    this.state = state;
    if (!this.canvas || !state) return;

    const rows = Math.max(1, (state.gpus || []).length);
    const tall = GpuHeatmapCalendar.AXIS_H + rows * (GpuHeatmapCalendar.SLOTS * GpuHeatmapCalendar.SLOT_H + GpuHeatmapCalendar.ROW_GAP);
    this.canvas.style.height = `${Math.max(96, tall)}px`;
    this.draw();
  }

  _days(state) {
    const first = new Date((state.now - state.window_s) * 1000);
    first.setHours(0, 0, 0, 0);
    const days = [];
    const cursor = new Date(first);
    while (cursor.getTime() / 1000 <= state.now) {
      days.push(cursor.getTime() / 1000);
      cursor.setDate(cursor.getDate() + 1);
    }
    return days;
  }

  draw() {
    const cv = this.canvas;
    const state = this.state;
    if (!cv || !state) return;

    const w = cv.clientWidth;
    const h = cv.clientHeight;
    if (!w || !h) return;

    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    if (cv.width !== Math.round(w * dpr) || cv.height !== Math.round(h * dpr)) {
      cv.width = Math.round(w * dpr);
      cv.height = Math.round(h * dpr);
    }

    const ctx = cv.getContext("2d");
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, w, h);
    this.cells = [];

    const gpus = state.gpus || [];
    if (!gpus.length) {
      ctx.fillStyle = "rgba(220, 235, 245, 0.8)";
      ctx.font = "600 11px ui-monospace, SFMono-Regular, monospace";
      ctx.textAlign = "left";
      ctx.textBaseline = "middle";
      ctx.fillText("no GPU activity recorded yet", 2, h / 2);
      return;
    }

    const days = this._days(state);
    const plotX = GpuHeatmapCalendar.LABEL_W;
    const plotW = Math.max(1, w - plotX - 2);
    const cellW = plotW / days.length;
    const slotH = GpuHeatmapCalendar.SLOT_H;
    const rowH = GpuHeatmapCalendar.SLOTS * slotH;

    gpus.forEach((gpu, row) => {
      const y0 = row * (rowH + GpuHeatmapCalendar.ROW_GAP);

      ctx.fillStyle = "rgba(220, 235, 245, 0.86)";
      ctx.font = "600 10px ui-monospace, SFMono-Regular, monospace";
      ctx.textAlign = "left";
      ctx.textBaseline = "middle";
      ctx.fillText(`gpu ${gpu.index}`, 0, y0 + rowH / 2);

      ctx.fillStyle = "rgba(220, 235, 245, 0.04)";
      ctx.fillRect(plotX, y0, plotW, rowH);

      (gpu.buckets || []).forEach((bucket) => {
        const day = Math.floor((bucket.t - days[0]) / 86400);
        if (day < 0 || day >= days.length) return;

        const slot = Math.min(GpuHeatmapCalendar.SLOTS - 1, Math.floor(new Date(bucket.t * 1000).getHours() / 4));
        const x = plotX + day * cellW;
        const y = y0 + slot * slotH;

        if (bucket.busy > 0) {
          const color = bucket.others > bucket.mine ? GpuHeatmapCalendar.OTHERS : GpuHeatmapCalendar.MINE;
          ctx.fillStyle = `rgba(${color}, ${(0.14 + 0.8 * bucket.busy).toFixed(3)})`;
          ctx.fillRect(x + 0.5, y + 0.5, Math.max(1, cellW - 1), slotH - 1);
        }

        this.cells.push({ x, y, w: cellW, h: slotH, gpu, bucket });
      });

      ctx.strokeStyle = "rgba(220, 235, 245, 0.10)";
      ctx.lineWidth = 1;
      ctx.strokeRect(plotX + 0.5, y0 + 0.5, plotW - 1, rowH - 1);
    });

    const bottom = gpus.length * (rowH + GpuHeatmapCalendar.ROW_GAP) - GpuHeatmapCalendar.ROW_GAP;
    ctx.font = "600 9px ui-monospace, SFMono-Regular, monospace";
    ctx.textBaseline = "top";
    const every = Math.max(1, Math.ceil((days.length * 40) / plotW));
    days.forEach((t, index) => {
      if (index % every !== 0) return;
      const date = new Date(t * 1000);
      const x = plotX + index * cellW;
      ctx.fillStyle = "rgba(220, 235, 245, 0.81)";
      ctx.textAlign = x > w - 24 ? "right" : "left";
      ctx.fillText(`${String(date.getDate()).padStart(2, "0")}.${String(date.getMonth() + 1).padStart(2, "0")}`, Math.min(x, w - 1), bottom + 5);
    });
  }

  figureDays() {
    const gpus  = this.state.gpus || [];
    const first = this._days(this.state);
    const days  = first.map(() => Array.from({ length: GpuHeatmapCalendar.SLOTS }, () => ({ mine: 0, others: 0 })));

    for (const gpu of gpus) {
      for (const bucket of gpu.buckets || []) {
        const day = Math.floor((bucket.t - first[0]) / 86400);
        if (day < 0 || day >= days.length) continue;

        const slot              = Math.min(GpuHeatmapCalendar.SLOTS - 1, Math.floor(new Date(bucket.t * 1000).getHours() / 4));
        days[day][slot].mine   += bucket.mine / gpus.length;
        days[day][slot].others += bucket.others / gpus.length;
      }
    }

    return days.map((slots) => ({ slots: slots.map((slot) => ({ mine: Math.round(slot.mine * 100) / 100, others: Math.round(slot.others * 100) / 100 })) }));
  }

  _hover(event) {
    if (!this.readout || !this.cells.length) return;

    const box = this.canvas.getBoundingClientRect();
    const x = event.clientX - box.left;
    const y = event.clientY - box.top;
    const cell = this.cells.find((c) => x >= c.x && x < c.x + c.w && y >= c.y && y < c.y + c.h);
    if (!cell) return this._blur();

    const clock = (d) => `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
    const start = new Date(cell.bucket.t * 1000);
    const end = new Date((cell.bucket.t + 4 * 3600) * 1000);
    const label = `${String(start.getDate()).padStart(2, "0")}.${String(start.getMonth() + 1).padStart(2, "0")} ${clock(start)}-${clock(end)}`;
    const who = (cell.bucket.holders || []).join(", ");
    this.readout.textContent = cell.bucket.busy > 0
      ? `${label} · gpu ${cell.gpu.index} · busy ${Math.round(100 * cell.bucket.busy)}% · you ${Math.round(100 * cell.bucket.mine)}% · others ${Math.round(100 * cell.bucket.others)}%${who ? ` · ${who}` : ""}`
      : `${label} · gpu ${cell.gpu.index} · idle`;
  }

  _blur() {
    if (this.readout) this.readout.textContent = this.idle;
  }
}

class HostHistoryPanel {
  static COLORS = { cpu: "111, 155, 255", ram: "45, 212, 191", rx: "167, 139, 250", tx: "251, 191, 36" };

  constructor() {
    this.state = null;
  }

  render(state) {
    this.state = state;
    this.draw();
  }

  draw() {
    const state = this.state;
    const cpuCv = document.getElementById("sb-hh-cpu");
    const netCv = document.getElementById("sb-hh-net");
    if (!state || !cpuCv || !netCv) return;

    const host = state.host || [];
    TimeStrip.draw(cpuCv, state, [
      { points: TimeStrip.points(host, "cpu"), color: HostHistoryPanel.COLORS.cpu, label: "cpu" },
      { points: TimeStrip.points(host, "ram"), color: HostHistoryPanel.COLORS.ram, label: "ram" },
    ], { yMax: 100, unit: "%" });

    const netMax = TimeStrip.niceMax(Math.max(0.5, ...host.map((s) => Math.max(s.rx || 0, s.tx || 0))));
    TimeStrip.draw(netCv, state, [
      { points: TimeStrip.points(host, "rx"), color: HostHistoryPanel.COLORS.rx, label: "in" },
      { points: TimeStrip.points(host, "tx"), color: HostHistoryPanel.COLORS.tx, label: "out" },
    ], { yMax: netMax, unit: " MB/s" });
  }
}

class AlertShelf {
  static SHOW_MS  = 90000;
  static EVENT_MS = 600000;

  constructor() {
    this.seen = new Map();
    this.keys = [];
    this.box  = null;
  }

  wire(box, reopen) {
    this.box = box;
    box.addEventListener("click", (event) => {
      if (event.target.closest(".alert__dismiss")) this.dismiss();
    });
    reopen.addEventListener("click", () => this.reopen());
  }

  render(alerts) {
    if (!this.box) return;
    const now   = Date.now();
    const items = this._items(alerts, now);
    this.keys   = items.map((item) => item.key);
    items.forEach((item) => {
      if (!this.seen.has(item.key)) this.seen.set(item.key, now);
    });

    const fresh = items.filter((item) => now - this.seen.get(item.key) < AlertShelf.SHOW_MS);
    if (!fresh.length) {
      this.box.hidden = true;
      this.box.innerHTML = "";
      return;
    }

    const left   = Math.max(...fresh.map((item) => AlertShelf.SHOW_MS - (now - this.seen.get(item.key))));
    const active = (alerts.active || []).length;
    this.box.hidden = false;
    this.box.innerHTML =
      `<header class="sboard__cap"><span>alerts</span><span class="alert__head"><span class="sboard__n">${active} active · hides in ${Math.ceil(left / 1000)} s</span><button type="button" class="alert__dismiss" title="Hide now; the watchdog count reopens them">dismiss</button></span></header>` +
      `<div class="alert__list">${fresh.map((item) => item.html).join("")}</div>`;
  }

  _items(alerts, now) {
    const active = (alerts.active || []).map((a) => ({
      key: `${a.kind}|${a.level}|${a.since}`,
      html: `<span class="alert alert--${a.level === "danger" ? "danger" : "warn"}">${SharedCharts.esc(a.message)}</span>`,
    }));
    const events = (alerts.events || [])
      .filter((e) => now - new Date(e.time).getTime() < AlertShelf.EVENT_MS)
      .slice(-3)
      .map((e) => ({
        key: `event|${e.time}|${e.kind}`,
        html: `<span class="alert alert--event"><b>${SharedCharts.esc(e.time.replace("T", " "))}</b> ${SharedCharts.esc(e.message)}</span>`,
      }));
    return active.concat(events);
  }

  dismiss() {
    this.keys.forEach((key) => this.seen.set(key, 0));
    this.box.hidden = true;
  }

  reopen() {
    const now = Date.now();
    this.keys.forEach((key) => this.seen.set(key, now));
  }
}

class StatusBoard {
  static POLL_MS      = 1000;
  static AWAY_EVERY   = 10;
  static SHRINK_TICKS = 10;
  static MISSING_RETRY_MS = 10000;

  constructor(els) {
    this.els = els;
    this.built = false;
    this.gpuEls = [];
    this.cpuDial = null;
    this.impactMeters = null;
    this.histMax = 144;
    this.gpuCount = 0;
    this.shrunkTicks = 0;
    this.ticks = 0;
    this.usersTable = new UsersTable();
    this.processTable = new ProcessTable();
    this.jobsList = new JobsList();
    this.activity = null;
    this._activityState = null;
    this._heatState = null;
    this._activityRange = "day";
    this.hostPanel = new HostHistoryPanel();
    this._hhRange = "day";
    this._hostHour = null;
    this.heatmap = null;
    this.alertShelf = new AlertShelf();
    this._missingStamp = 0;
  }

  start() {
    this._poll();
    setInterval(() => this._tick(), StatusBoard.POLL_MS);
    this._pollJobs();
    setInterval(() => { if (this._showing()) this._pollJobs(); }, 5000);
    this._pollActivity();
    setInterval(() => { if (this._showing()) this._pollActivity(); }, 60000);
    this._pollServerLog();
    setInterval(() => { if (this._showing()) this._pollServerLog(); }, 5000);
    this._pollHostHistory();
    setInterval(() => { if (this._showing()) this._pollHostHistory(); }, 60000);
    this._pollHostHour();
    setInterval(() => { if (this._showing()) this._pollHostHour(); }, 30000);
    this._pollHeatmap();
    setInterval(() => { if (this._showing()) this._pollHeatmap(); }, 300000);
    new ResizeObserver(() => this._redrawCharts()).observe(this.els.board);
  }

  _tick() {
    if (document.visibilityState !== "visible") return;
    this.ticks += 1;
    if (this._showing() || this.ticks % StatusBoard.AWAY_EVERY === 0) this._poll();
    if (this._showing()) this._pollMissing();
  }

  _pollMissing() {
    const now = Date.now();
    if (now - this._missingStamp < StatusBoard.MISSING_RETRY_MS) return;
    this._missingStamp = now;
    if (!this._activityState) this._pollActivity();
    if (!this._heatState) this._pollHeatmap();
    if (!this.hostPanel.state) this._pollHostHistory();
  }

  _redrawCharts() {
    if (this.activity) this.activity.draw();
    if (this.heatmap) this.heatmap.draw();
    this.hostPanel.draw();
  }

  _showing() {
    if (document.visibilityState !== "visible") return false;
    return !!(this.els.board && this.els.board.closest(".page.is-active"));
  }

  async _pollActivity() {
    if (this._serverDown) return;
    const range = this._activityRange;
    const data = await Api.get(`/api/gpu-activity?range=${range}`);
    if (data.error || range !== this._activityRange) return;

    this._activityState = data;
    this._renderActivity();
  }

  _renderActivity() {
    const state = this._activityState;
    if (!this.activity || !state) return;

    const gpus = state.gpus || [];
    const blocks = state.bucket_s >= 3600 ? `${Math.round(state.bucket_s / 3600)} h blocks` : `${Math.round(state.bucket_s / 60)} min blocks`;
    this._txt("sb-act-n", `${gpus.length} device${gpus.length === 1 ? "" : "s"} &middot; ${blocks}`);
    this.activity.render(state);
  }

  _wireActivityRanges() {
    const wrap = document.getElementById("sb-act-ranges");
    if (!wrap) return;

    const buttons = [...wrap.querySelectorAll("button[data-range]")];
    buttons.forEach((button) => {
      button.classList.toggle("is-on", button.dataset.range === this._activityRange);
      button.addEventListener("click", () => {
        if (this._activityRange === button.dataset.range) return;

        this._activityRange = button.dataset.range;
        buttons.forEach((other) => other.classList.toggle("is-on", other === button));
        this._pollActivity();
      });
    });
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

  async _pollHeatmap() {
    if (this._serverDown) return;
    const data = await Api.get("/api/gpu-activity?range=month");
    if (data.error) return;

    this._heatState = data;
    this._renderHeatmap();
  }

  _renderHeatmap() {
    const state = this._heatState;
    if (!this.heatmap || !state) return;

    const gpus = (state.gpus || []).length;
    this._txt("sb-heat-n", `${gpus} device${gpus === 1 ? "" : "s"} &middot; 4 h cells`);
    this.heatmap.render(state);

    const figure = document.getElementById("sb-heat-figure");
    if (!figure) return;
    const days = this.heatmap.figureDays();
    const key  = JSON.stringify(days);
    if (key === this._heatFigureKey && figure.state) return;
    this._heatFigureKey = key;
    figure.state        = { days };
  }

  async _pollHostHistory() {
    if (this._serverDown) return;
    const range = this._hhRange;
    const data = await Api.get(`/api/host-history?range=${range}`);
    if (data.error || range !== this._hhRange) return;

    const points = (data.host || []).length;
    this._txt("sb-hh-n", `${points} point${points === 1 ? "" : "s"}`);
    this.hostPanel.render(data);
  }

  async _pollHostHour() {
    if (this._serverDown) return;
    const data = await Api.get("/api/host-history?range=hour");
    if (data.error) return;

    this._hostHour = {};
    (data.gpus || []).forEach((g) => { this._hostHour[String(g.index)] = g.buckets || []; });
  }

  _wireHostRanges() {
    const wrap = document.getElementById("sb-hh-ranges");
    if (!wrap) return;

    const buttons = [...wrap.querySelectorAll("button[data-range]")];
    buttons.forEach((button) => {
      button.classList.toggle("is-on", button.dataset.range === this._hhRange);
      button.addEventListener("click", () => {
        if (this._hhRange === button.dataset.range) return;

        this._hhRange = button.dataset.range;
        buttons.forEach((other) => other.classList.toggle("is-on", other === button));
        this._pollHostHistory();
      });
    });
  }

  async _pollJobs() {
    if (this._serverDown) return;
    const data = await Api.get("/api/jobs");
    if (data.error) return;

    this.jobsList.render(data.jobs);
  }

  async _pollServerLog() {
    if (this._serverDown) return;
    const data = await Api.get("/api/server-log?limit=150");
    if (data.error) return;

    const box = document.getElementById("sb-srvlog");
    if (!box) return;

    const lines = data.lines || [];
    this._txt("sb-srvlog-n", `${lines.length} recent lines`);

    const atBottom = box.scrollHeight - box.scrollTop - box.clientHeight < 40;
    box.innerHTML = lines.length
      ? lines.map((l) =>
          `<div class="srvlog__line is-${SharedCharts.esc(String(l.level || "").toLowerCase())}">` +
          `<span class="srvlog__time">${SharedCharts.esc(l.time)}</span>` +
          `<span class="srvlog__lvl">${SharedCharts.esc(l.level)}</span>` +
          `<span class="srvlog__msg">${SharedCharts.esc(l.message)}</span></div>`
        ).join("")
      : `<div class="sboard__empty">the server has logged nothing yet</div>`;
    if (atBottom) box.scrollTop = box.scrollHeight;
  }

  _disposeGauges() {
    this.gpuEls.forEach((card) => [card.dialU, card.meterT, card.meterP, card.vseg].forEach((gauge) => gauge.dispose()));
    if (this.cpuDial) this.cpuDial.dispose();
    Object.values(this.impactMeters || {}).forEach((meter) => meter.dispose());

    this.gpuEls = [];
    this.cpuDial = null;
    this.impactMeters = null;
  }

  _build(sys) {
    this._disposeGauges();
    this.built = true;
    const gpus = sys.gpus || [];
    const cores = (sys.cpu && sys.cpu.cores) || [];
    this.gpuCount = gpus.length;
    this.gpuIndices = gpus.map((g, i) => (g.index != null ? g.index : i));

    const gpuCards = gpus.length
      ? gpus.map((g, i) =>
          `<article class="gcard" data-gpu="${i}">` +
          `<header class="gcard__head"><span class="gcard__idx">gpu ${g.index != null ? g.index : i}</span><span class="gcard__name">${SharedCharts.esc(g.name || "unknown")}</span><span class="gcard__who"></span></header>` +
          `<div class="gcard__cluster">` +
          `<canvas class="gdial gdial--big gdial--util"></canvas>` +
          `<canvas class="gcard__graph"></canvas>` +
          `<div class="gcard__live" title="fans spin with utilisation, the cable carries power draw"><div class="fig-fill">${HairlineFigure.html("gpuwire", 'class="gcard__wire" aria-hidden="true"')}</div></div>` +
          `</div>` +
          `<div class="gcard__meters">` +
          `<canvas class="gmeter gmeter--temp"></canvas>` +
          `<canvas class="gmeter gmeter--power"></canvas>` +
          `</div>` +
          `<canvas class="gcard__health" title="last hour &middot; temperature (amber, &deg;C) and power (violet, % of limit)"></canvas>` +
          `<div class="gcard__vramrow"><span class="gcard__vlabel">vram</span><canvas class="gseg"></canvas><span class="gcard__vram">--</span></div>` +
          `<footer class="gcard__foot"><span class="gcard__temp">--</span><span class="gcard__power">--</span><span class="gcard__legend"><i class="lg lg--util"></i>util<i class="lg lg--vram"></i>vram</span></footer>` +
          `</article>`
        ).join("")
      : `<div class="sboard__empty">${sys.gpus_known ? "no CUDA devices visible to the backend" : "nvidia-smi is not answering, GPU occupancy is unknown"}</div>`;
    const gpuShelf = gpus.length % 2 === 1 ? `<div class="gcard gcard--shelf">${HairlineFigure.html("gpus", 'class="gcard__figure" id="sb-gpu-shelf" aria-hidden="true"')}</div>` : "";

    const lim = (sys.alerts && sys.alerts.limits) || {};
    const limitCells = [
      [lim.cpu_alert != null ? `${Math.round(lim.cpu_alert)}%` : "--", "cpu alert"],
      [lim.load_ratio != null ? `${lim.load_ratio.toFixed(1)} / core` : "--", "load limit"],
      [lim.ram_warn != null ? `${Math.round(lim.ram_warn)}%` : "--", "ram warn"],
      [lim.ram_kill != null ? `${Math.round(lim.ram_kill)}%` : "--", "ram kill"],
      [lim.mine_share != null ? `${Math.round(lim.mine_share * 100)}%` : "--", "own ram share"],
      [lim.disk_warn != null ? `&lt;${Math.round(lim.disk_warn)}% free` : "--", "disk warn"],
      [lim.interval != null ? `${Math.round(lim.interval)} s` : "--", "interval"],
      [lim.cooldown != null ? `${Math.round(lim.cooldown)} s` : "--", "kill cooldown"],
    ].map(([v, k]) => `<div class="ctl__tile"><dt>${k}</dt><dd>${v}</dd></div>`).join("");

    this.els.board.innerHTML =
      `<section class="sboard sboard--impactbanner" id="sb-impact-banner" aria-label="Neighbour impact alarm" hidden></section>` +

      `<section class="sboard sboard--alerts" id="sb-alerts" aria-label="Alerts" hidden></section>` +


      `<div class="sboard__strips">` +

      `<section class="sboard sboard--ctl" aria-label="Resource watchdog">` +
      `<header class="sboard__cap"><span class="ctl__title"><i class="wd__light" id="sb-wd-light" aria-hidden="true"></i>watchdog</span><span class="ctl__state"><span class="wd__mode" id="sb-wd-mode">--</span><button type="button" class="wd__status" id="sb-wd-status" title="Show the alerts again">--</button></span></header>` +
      `<dl class="ctl__tiles">${limitCells}</dl>` +
      `<div class="ctl__figure"><div class="fig-fill">${HairlineFigure.html("watchdog", 'id="sb-wd-figure" autopilot="off" aria-hidden="true"')}</div></div>` +
      `<div class="ctl__actions">` +
      `<button type="button" class="impact__arm" id="sb-detach" title="Detach the backend from your terminal AND login session (retroactive nohup + own systemd scope with lingering): monitors and running jobs survive SSH logout, session cleanup and stray SIGTERMs; only SIGKILL or the kill front end button stop it">keep-alive: --</button>` +
      `<select class="ntf__input impact__level" id="sb-impact-politeness" aria-label="launch politeness" title="Priority every local launch starts under: off runs at nice 0, polite at nice 10 with best-effort I/O 7, background at nice 19 with idle I/O. Applies to the next launch; running jobs keep theirs."><option value="off">launch: off</option><option value="polite">launch: polite</option><option value="background">launch: background</option></select>` +
      `<button type="button" class="impact__arm" id="sb-impact-throttle" title="When on, the first alarm that blames you drops every process of yours to nice 19 and idle I/O (the console itself is spared). Priorities can only be lowered, so a throttled job stays throttled until it ends.">auto-throttle: --</button>` +
      `<button type="button" class="impact__arm" id="sb-impact-arm" title="When armed, auto-nukes all your processes if you slow other users too much">auto-nuke: --</button>` +
      `</div>` +
      `</section>` +

      `<section class="sboard sboard--ctl sboard--notify" aria-label="Job notifications">` +
      `<header class="sboard__cap"><span class="ctl__title"><i class="wd__light" id="sb-ntf-light" aria-hidden="true"></i>notify</span><span class="ctl__state"><span class="wd__mode" id="sb-ntf-mode">--</span></span></header>` +
      `<div class="ntf__body">` +
      `<div class="ntf__side">` +
      `<div class="ctl__fields">` +
      `<label class="ctl__field"><span class="ntf__key">ntfy topic</span><input class="ntf__input" id="sb-ntf-topic" type="text" placeholder="pick-a-secret-topic" spellcheck="false" autocomplete="off"></label>` +
      `<label class="ctl__field"><span class="ntf__key">server</span><input class="ntf__input" id="sb-ntf-server" type="text" spellcheck="false" autocomplete="off"></label>` +
      `</div>` +
      `<p class="ctl__hint" title="Install the ntfy app (or open ntfy.sh in a browser) and subscribe to the same topic. Every job notifies when it starts and when it ends — direct launches, queued runs and follow-ups alike. Fan-out experiments additionally push the first ETA, 25/50/75% progress milestones and per-unit failures. Failures arrive high-priority.">push to your phone when a job starts, progresses and ends</p>` +
      `</div>` +
      `<div class="ctl__figure ntf__figure"><div class="fig-fill">${HairlineFigure.html("notify", 'id="sb-ntf-figure" aria-hidden="true"')}</div></div>` +
      `</div>` +
      `<div class="ctl__actions">` +
      `<button type="button" class="impact__arm" id="sb-ntf-test" title="Send a test notification to the topic now">test</button>` +
      `<button type="button" class="impact__arm" id="sb-ntf-save" title="Save topic and server">save</button>` +
      `<button type="button" class="impact__arm" id="sb-ntf-toggle" title="Toggle job start/end notifications">notify: --</button>` +
      `</div>` +
      `</section>` +

      `<section class="sboard sboard--ctl sboard--nuke" aria-label="Kill switches">` +
      `<header class="sboard__cap"><span class="ctl__title"><i class="wd__light" id="sb-nuke-light" aria-hidden="true"></i>kill switches</span><span class="ctl__state"><span class="wd__mode is-off" id="sb-nuke-mode">ready</span></span></header>` +
      `<div class="kill__pair">` +
      `<div class="kill__cell">` +
      `<div class="ctl__figure nuke__figure"><div class="fig-fill">${HairlineFigure.html("nuke", 'id="sb-nuke-figure" aria-hidden="true"')}</div></div>` +
      `<p class="ctl__hint" title="SIGTERM, then SIGKILL after a grace period, for every process running under your user on this machine. Only the web console itself is spared, so detached monitors and queued launches die with the rest.">every process of yours on this machine; the web UI is spared</p>` +
      `<button type="button" class="wd__nuke" id="sb-nuke" title="Kill every process running under your user on this machine">` +
      `<span class="wd__nuke-sym" aria-hidden="true">&#9762;</span><span class="wd__nuke-txt">NUKE</span>` +
      `</button>` +
      `</div>` +
      `<div class="kill__cell">` +
      `<div class="ctl__figure kill__figure"><div class="fig-fill">${HairlineFigure.html("guillotine", 'id="sb-kill-figure" aria-hidden="true"')}</div></div>` +
      `<p class="ctl__hint" title="Stops every web console server of this project, this one and any instance left behind by earlier keep-alive launches. Running and detached jobs survive and are re-adopted on the next start; queued launches and watchdogs die with the console.">stops every web console of this project; running jobs survive and are re-adopted on restart</p>` +
      `<button type="button" class="impact__arm kill__btn" id="sb-kill-ui" title="Stop EVERY web console server of this project, this one and any instance left behind by earlier keep-alive launches: running and detached jobs survive and are re-adopted on the next start, but queued launches and watchdogs die with them">kill front end</button>` +
      `</div>` +
      `</div>` +
      `</section>` +

      `</div>` +


      `<section class="sboard sboard--gpus" aria-label="CUDA devices">` +
      `<div class="sboard__gputop">` +
      `<div class="gpudeck">` +
      `<header class="sboard__cap"><span>cuda devices</span><span class="sboard__n">${gpus.length}</span></header>` +
      `<div class="sboard__gpugrid">${gpuCards}${gpuShelf}</div>` +
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
      `<div class="cpu__figure" title="one pillar per core, as tall as that core is busy; the dashed plane is the dispatch line at 50%"><div class="fig-fill">${HairlineFigure.html("cores", 'id="sb-cores-figure" aria-hidden="true"')}</div></div>` +
      `</section>` +

      `</div>` +
      `</section>` +


      `<section class="sboard sboard--sysres" aria-label="Memory and storage">` +
      `<header class="sboard__cap"><span>storage</span><span class="sboard__n" id="sb-disk-total"></span></header>` +
      `<div class="sysres__grid">` +
      `<div class="sysres__info">` +
      `<div class="sboard__metric"><span class="sboard__path" id="sb-disk-path"></span><span id="sb-disk-txt">--</span></div>` +
      `<div class="bar"><i class="bar__fill" id="sb-disk-bar"></i></div>` +
      `<div class="sboard__metric"><span>free &middot; all users</span><span id="sb-disk-free">--</span></div>` +
      `<div class="sboard__metric"><span class="sboard__path" id="sb-disk-user-path">${SharedCharts.esc(sys.user || "user")} &middot; total</span><span id="sb-disk-user">--</span></div>` +
      `<div class="bar"><i class="bar__fill bar__fill--user" id="sb-disk-user-bar"></i></div>` +
      `<div class="sboard__metric"><span class="sboard__path" id="sb-disk-repo-path">repo root</span><span id="sb-disk-repo">--</span></div>` +
      `<div class="bar"><i class="bar__fill bar__fill--repo" id="sb-disk-repo-bar"></i></div>` +
      `</div>` +
      `<div class="sysres__figure"><div class="fig-fill">${HairlineFigure.html("riffle", 'aria-hidden="true"')}</div></div>` +
      `<div class="sysres__rule"><span>memory</span><span class="sboard__n" id="sb-mem-total"></span></div>` +
      `<div class="sysres__info">` +
      `<div class="sboard__metric"><span>ram</span><span id="sb-ram-txt">--</span></div>` +
      `<div class="bar"><i class="bar__fill bar__fill--ram" id="sb-ram-bar"></i></div>` +
      `<div class="sboard__metric"><span>swap</span><span id="sb-swap-txt">--</span></div>` +
      `<div class="bar"><i class="bar__fill bar__fill--swap" id="sb-swap-bar"></i></div>` +
      `<canvas class="sboard__graph sboard__graph--mem" id="sb-mem-graph"></canvas>` +
      `</div>` +
      `<div class="sysres__figure"><div class="fig-fill">${HairlineFigure.html("cabinet", 'aria-hidden="true"')}</div></div>` +
      `</div>` +
      `</section>` +

      `<section class="sboard sboard--gpuhist" aria-label="GPU activity timeline">` +
      `<header class="sboard__cap"><span>gpu activity</span>` +
      `<span class="gpuhist__ranges" id="sb-act-ranges" role="group" aria-label="Activity window">` +
      `<button type="button" class="gpuhist__range" data-range="day">day</button>` +
      `<button type="button" class="gpuhist__range" data-range="week">week</button>` +
      `<button type="button" class="gpuhist__range" data-range="month">month</button>` +
      `</span>` +
      `<span class="sboard__n" id="sb-act-n">--</span></header>` +
      `<div class="gpuhist__figure"><div class="fig-fill">${HairlineFigure.html("patch", 'aria-hidden="true"')}</div></div>` +
      `<div class="gpuhist__plot"><canvas class="gpuhist__canvas" id="sb-act-graph"></canvas></div>` +
      `<div class="gpuhist__foot">` +
      `<span class="gpuhist__legend"><i class="lg lg--mine"></i>you<i class="lg lg--others"></i>others<i class="lg lg--idle"></i>idle</span>` +
      `<span class="gpuhist__read" id="sb-act-read">hover a block</span>` +
      `</div>` +
      `</section>` +

      `<section class="sboard sboard--impact" aria-label="Neighbour impact">` +
      `<header class="sboard__cap"><span>neighbour impact</span><i class="impact__light" id="sb-impact-light" aria-hidden="true"></i><span class="sboard__n" id="sb-impact-verdict">--</span></header>` +
      `<p class="impact__lede" id="sb-impact-lede">${ThinkingOrb.busy("listening", "reading every user's stall from their cgroup slice…")}</p>` +
      `<div class="impact__grid">` +
      `<div class="impact__cell"><canvas class="gmeter gmeter--impact" id="sb-impact-mem-meter"></canvas><span class="impact__share" id="sb-impact-mem-share">your share --</span><div class="bar bar--share"><i class="bar__fill bar__fill--share" id="sb-impact-mem-share-bar"></i></div></div>` +
      `<div class="impact__cell"><canvas class="gmeter gmeter--impact" id="sb-impact-io-meter"></canvas><span class="impact__share" id="sb-impact-io-share">your share --</span><div class="bar bar--share"><i class="bar__fill bar__fill--share" id="sb-impact-io-share-bar"></i></div></div>` +
      `<div class="impact__cell"><canvas class="gmeter gmeter--impact" id="sb-impact-cpu-meter"></canvas><span class="impact__share" id="sb-impact-cpu-share">your share --</span><div class="bar bar--share"><i class="bar__fill bar__fill--share" id="sb-impact-cpu-share-bar"></i></div></div>` +
      `</div>` +
      `<div class="impact__foot">` +
      `<dl class="impact__stats">` +
      `<div><dt id="sb-impact-swap">--</dt><dd>swap out</dd></div>` +
      `<div><dt id="sb-impact-iorate">--</dt><dd>disk busy</dd></div>` +
      `<div><dt id="sb-impact-mine">--</dt><dd>your procs</dd></div>` +
      `<div><dt id="sb-impact-top">--</dt><dd>top ram user</dd></div>` +
      `<div><dt id="sb-impact-stalled">--</dt><dd>users stalled</dd></div>` +
      `</dl>` +
      HairlineFigure.html("chips", 'class="impact__figure" id="sb-impact-balance" aria-hidden="true"') +
      `</div>` +
      `</section>` +

      `<section class="sboard sboard--impactlog" id="sb-impact-log" aria-label="Neighbour impact alarms" hidden></section>` +


      `<section class="sboard sboard--hosthist" aria-label="Host history">` +
      `<header class="sboard__cap"><span>host history</span>` +
      `<span class="gpuhist__ranges" id="sb-hh-ranges" role="group" aria-label="History window">` +
      `<button type="button" class="gpuhist__range" data-range="hour">hour</button>` +
      `<button type="button" class="gpuhist__range" data-range="day">day</button>` +
      `<button type="button" class="gpuhist__range" data-range="week">week</button>` +
      `<button type="button" class="gpuhist__range" data-range="month">month</button>` +
      `</span>` +
      `<span class="sboard__n" id="sb-hh-n">--</span></header>` +
      `<div class="hosthist__grid">` +
      `<div class="hosthist__figure hosthist__figure--left"><div class="fig-fill">${HairlineFigure.html("phosphor", 'autopilot="off" aria-hidden="true"')}</div></div>` +
      `<div class="hosthist__cell hosthist__cell--cpu"><span class="hosthist__cap"><i class="lg lg--util"></i>cpu %<i class="lg lg--vram"></i>ram %</span><canvas class="hosthist__canvas" id="sb-hh-cpu"></canvas></div>` +
      `<div class="hosthist__cell hosthist__cell--net"><span class="hosthist__cap"><i class="lg lg--rx"></i>net in<i class="lg lg--tx"></i>net out</span><canvas class="hosthist__canvas" id="sb-hh-net"></canvas></div>` +
      `<div class="hosthist__figure hosthist__figure--right"><div class="fig-fill">${HairlineFigure.html("router", 'aria-hidden="true"')}</div></div>` +
      `</div>` +
      `</section>` +

      this.jobsList.markup() +

      `<section class="sboard sboard--figure sboard--srvfig" aria-hidden="true"><div class="fig-fill">${HairlineFigure.html("terminal", 'aria-hidden="true"')}</div></section>` +

      `<section class="sboard sboard--srvlog" aria-label="Server internals">` +
      `<header class="sboard__cap"><span>server internals</span><span class="sboard__n" id="sb-srvlog-n">--</span></header>` +
      `<div class="srvlog" id="sb-srvlog"><div class="sboard__empty">${ThinkingOrb.busy("listening", "reading the server log…")}</div></div>` +
      `</section>` +

      `<section class="sboard sboard--heatcal" aria-label="GPU month heatmap">` +
      `<header class="sboard__cap"><span>gpu heatmap &middot; 30 days</span><span class="sboard__n" id="sb-heat-n">--</span></header>` +
      `<div class="heatcal__grid">` +
      `<div class="heatcal__main">` +
      `<canvas class="heatcal__canvas" id="sb-heat-graph"></canvas>` +
      `<div class="gpuhist__foot">` +
      `<span class="gpuhist__legend"><i class="lg lg--mine"></i>you<i class="lg lg--others"></i>others<i class="lg lg--idle"></i>idle</span>` +
      `<span class="gpuhist__read" id="sb-heat-read">hover a cell &middot; rows are 4 h slots, columns are days</span>` +
      `</div>` +
      `</div>` +
      `<div class="heatcal__figure"><div class="fig-fill">${HairlineFigure.html("calendar", 'id="sb-heat-figure" autopilot="off" aria-hidden="true"')}</div></div>` +
      `</div>` +
      `</section>` +
      this.usersTable.markup() +
      this.processTable.markup(sys.user);

    this.gpuEls = [...this.els.board.querySelectorAll(".gcard[data-gpu]")].map((card, i) => ({
      vramTxt: card.querySelector(".gcard__vram"),
      health: card.querySelector(".gcard__health"),
      temp: card.querySelector(".gcard__temp"),
      who: card.querySelector(".gcard__who"),
      power: card.querySelector(".gcard__power"),
      graph: card.querySelector(".gcard__graph"),
      wire: card.querySelector(".gcard__wire"),
      dialU: new window.DialGauge(card.querySelector(".gdial--util"), { big: true, label: "UTIL %", color: "111, 155, 255", majors: 5, minors: 4 }),
      meterT: new window.LinearMeter(card.querySelector(".gmeter--temp"), { min: 20, max: 100, label: "TEMP °C", color: "45, 212, 191", zones: [{ from: 70, to: 85, color: "251, 191, 36" }, { from: 85, to: 100, color: "248, 113, 113" }] }),
      meterP: new window.LinearMeter(card.querySelector(".gmeter--power"), { max: (gpus[i] && gpus[i].power_limit) || 250, label: "POWER W", color: "167, 139, 250" }),
      vseg: new window.SegMeter(card.querySelector(".gseg"), { color: "45, 212, 191" }),
    }));

    this.cpuDial = new window.DialGauge(document.getElementById("sb-cpu-dial"), { big: true, label: "BUSY %", color: "111, 155, 255", majors: 5, minors: 4, zones: [{ from: 75, to: 90, color: "251, 191, 36" }, { from: 90, to: 100, color: "248, 113, 113" }] });

    this.impactMeters = {
      mem: new window.LinearMeter(document.getElementById("sb-impact-mem-meter"), { label: "NEIGHBOUR MEM STALL %", color: "111, 155, 255", zones: [{ from: 10, to: 30, color: "251, 191, 36" }, { from: 30, to: 100, color: "248, 113, 113" }] }),
      io:  new window.LinearMeter(document.getElementById("sb-impact-io-meter"),  { label: "NEIGHBOUR DISK STALL %", color: "111, 155, 255", zones: [{ from: 20, to: 50, color: "251, 191, 36" }, { from: 50, to: 100, color: "248, 113, 113" }] }),
      cpu: new window.LinearMeter(document.getElementById("sb-impact-cpu-meter"), { label: "NEIGHBOUR CPU STALL %", color: "111, 155, 255", zones: [{ from: 20, to: 50, color: "251, 191, 36" }, { from: 50, to: 100, color: "248, 113, 113" }] }),
    };
    this.activity = new GpuActivityTimeline(document.getElementById("sb-act-graph"), document.getElementById("sb-act-read"));
    this._wireActivityRanges();
    this._renderActivity();
    this._wireHostRanges();
    this.hostPanel.draw();
    this.heatmap = new GpuHeatmapCalendar(document.getElementById("sb-heat-graph"), document.getElementById("sb-heat-read"));
    this._renderHeatmap();
    this._pollServerLog();

    this.alertShelf.wire(document.getElementById("sb-alerts"), document.getElementById("sb-wd-status"));
    this._wireNuke();
    this._wireImpactArm();
    this._wireImpactPoliteness();
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

    const figure = document.getElementById("sb-nuke-figure");
    const light  = document.getElementById("sb-nuke-light");
    const mode   = document.getElementById("sb-nuke-mode");
    const fire   = (on) => {
      if (figure) figure.state = { firing: on };
      if (light) light.classList.toggle("is-danger", on);
      if (mode) {
        mode.textContent = on ? "firing" : "ready";
        mode.classList.toggle("is-danger", on);
      }
    };

    btn.addEventListener("click", async () => {
      const ok = window.confirm("NUKE: this kills EVERY process running under your user on this machine (pipeline runs, shells, jobs). The web UI is spared. Continue?");
      if (!ok) return;

      btn.disabled = true;
      btn.classList.add("is-firing");
      fire(true);
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
        fire(false);
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
          if (res.shield_error) Toast.show(`backend detached (pid ${res.pid}) but the session shield is incomplete: ${res.shield_error}`, "warn");
          else Toast.show(`backend detached and shielded in ${res.scope} (pid ${res.pid}) — survives logout, session cleanup and SIGTERM, log: ${res.log_path}`, "ok");
          this._renderDetach(res);
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
    const partial = srv.detached && srv.shield_error;
    btn.textContent = srv.detached ? (partial ? "keep-alive: PARTIAL" : "keep-alive: ON") : "keep-alive: off";
    btn.classList.toggle("is-safe", !!srv.detached && !partial);
    btn.classList.toggle("is-warn", !!partial);
    btn.disabled = !!srv.detached;
    if (partial) btn.title = `backend detached (pid ${srv.pid}) but the session shield is incomplete: ${srv.shield_error} — output continues in ${srv.log_path}`;
    else if (srv.detached) btn.title = `backend shielded in ${srv.scope} (pid ${srv.pid}) — survives logout, session cleanup and SIGTERM; output continues in ${srv.log_path}`;
  }

  _wireKillUi() {
    const btn = document.getElementById("sb-kill-ui");
    if (!btn) return;

    btn.addEventListener("click", async () => {
      const ok = window.confirm("Kill the front end: this stops EVERY web console server of this project, this one and any other instance still running. Running jobs keep going and are re-adopted on the next start; queued launches are lost. Continue?");
      if (!ok) return;

      btn.disabled = true;
      try {
        const res = await Api.post("/api/system/shutdown");
        if (res && res.ok) {
          this._serverDown = true;
          btn.textContent = "front end: down";
          btn.classList.add("is-armed");
          const figure = document.getElementById("sb-kill-figure");
          if (figure) figure.state = { down: true };
          const others = res.siblings.length ? `, plus ${res.siblings.length} other instance(s): pids ${res.siblings.join(", ")}` : "";
          Toast.show(`front end stopped (pid ${res.pid}${others}); running jobs keep going; restart it from the terminal (webui/run.sh)`, "ok");
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

    const figure = document.getElementById("sb-ntf-figure");
    if (figure && (!figure.state || figure.state.armed !== on)) figure.state = { armed: on };

    if (!this._ntfSeeded) {
      this._ntfSeeded = true;
      const topic = document.getElementById("sb-ntf-topic");
      const server = document.getElementById("sb-ntf-server");
      if (topic) topic.value = ntf.topic || "";
      if (server) server.value = ntf.server || "";
    }
  }

  _wireImpactPoliteness() {
    const select = document.getElementById("sb-impact-politeness");
    const toggle = document.getElementById("sb-impact-throttle");
    const send = async (payload, control) => {
      control.disabled = true;
      try {
        const res = await Api.post("/api/impact/politeness", payload);
        if (res && res.ok) {
          this._politeness = res;
          Toast.show(`launch politeness ${res.level} (${res.label}), auto-throttle ${res.auto_throttle ? "on" : "off"}`, "ok");
        } else {
          Toast.show(`politeness update failed: ${(res && res.error) || "unknown error"}`, "error");
        }
      } catch (e) {
        Toast.show("politeness update failed: network error", "error");
      } finally {
        control.disabled = false;
      }
    };
    if (select) select.addEventListener("change", () => send({ level: select.value }, select));
    if (toggle) toggle.addEventListener("click", () => send({ auto_throttle: !(this._politeness || {}).auto_throttle }, toggle));
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
    this._renderWatchdog(sys.alerts || {});
    this._renderWatchdogFigure(sys.alerts || {}, sys);
    this._renderAlerts(sys.alerts || {});
    this._renderImpact(sys.impact || {});
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
      if (el.wire) el.wire.state = { util, power: g.power_limit && g.power != null ? Math.max(0, Math.min(1, g.power / g.power_limit)) : undefined };
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

      const hh = (this._hostHour || {})[String(g.index != null ? g.index : i)] || [];
      if (el.health && hh.length > 1) {
        this._spark(el.health, [
          { data: hh.map((b) => b.temp || 0), color: "251, 191, 36", fill: 0.05 },
          { data: hh.map((b) => (g.power_limit ? (100 * (b.power || 0)) / g.power_limit : 0)), color: "167, 139, 250", fill: 0.05 },
        ], 120);
      }
    });

    this._renderShelf(gpus);

    if (this.cpuDial) this.cpuDial.set(cpu.total || 0);
    const load = cpu.load || [];
    ["sb-load1", "sb-load5", "sb-load15"].forEach((id, i) => {
      const el = document.getElementById(id);
      if (el && load[i] != null) el.textContent = load[i].toFixed(1);
    });
    const cores  = cpu.cores || [];
    const pillars = document.getElementById("sb-cores-figure");
    if (pillars && cores.length) pillars.state = { cores: cores.map((u) => Math.round(u)) };

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
      this._bar("sb-ram-bar", (100 * used) / mem.total);
      this._txt("sb-ram-txt", `<b>${ByteFormat.gb(used)}</b> / ${ByteFormat.gb(mem.total)} GB`);
      this._txt("sb-mem-total", `${ByteFormat.tb(mem.total)}`);
      const swapUsed = (mem.swap_total || 0) - (mem.swap_free || 0);
      this._bar("sb-swap-bar", mem.swap_total ? (100 * swapUsed) / mem.swap_total : 0);
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
      this._txt("sb-disk-user", disk.user_used != null ? `<b>${ByteFormat.tb(disk.user_used)}</b>` : ThinkingOrb.busy("searching", "scanning…"));
      this._bar("sb-disk-user-bar", disk.user_used ? (100 * disk.user_used) / disk.total : 0);

      const repoPath = document.getElementById("sb-disk-repo-path");
      if (repoPath && disk.repo_path) repoPath.title = disk.repo_path;
      this._txt("sb-disk-repo", disk.repo_used != null ? `<b>${ByteFormat.tb(disk.repo_used)}</b>` : ThinkingOrb.busy("searching", "scanning…"));
      this._bar("sb-disk-repo-bar", disk.repo_used ? (100 * disk.repo_used) / disk.total : 0);
    }

    this.usersTable.render(sys.users || [], ((sys.impact || {}).signals || {}).users || []);
    this.processTable.render(sys.procs || []);
  }

  _renderShelf(gpus) {
    const shelf = document.getElementById("sb-gpu-shelf");
    if (!shelf || !gpus.length) return;

    const devices = gpus.map((g) => ({ holder: g.mine ? "mine" : g.others ? "others" : g.stale ? "stale" : "idle", util: Math.round(g.util || 0) }));
    const key     = JSON.stringify(devices);
    if (key === this._shelfKey && shelf.state) return;
    this._shelfKey = key;
    shelf.state    = { devices };
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

  _renderWatchdogFigure(alerts, sys) {
    const figure = document.getElementById("sb-wd-figure");
    const lim    = alerts.limits;
    if (!figure || !lim) return;

    const cpu    = sys.cpu || {};
    const mem    = sys.mem || {};
    const disk   = sys.disk || {};
    const kinds  = new Set((alerts.active || []).map((alert) => alert.kind));
    const ratio  = cpu.count ? (cpu.load || [0])[0] / cpu.count : 0;
    const levels = [(cpu.total || 0) / 100, (0.8 * ratio) / lim.load_ratio, mem.total ? 1 - mem.available / mem.total : 0, disk.total ? 1 - disk.free / disk.total : 0];
    const limits = [lim.cpu_alert / 100, 0.8, lim.ram_warn / 100, 1 - lim.disk_warn / 100];
    const alert  = [kinds.has("cpu"), kinds.has("load"), kinds.has("ram") || kinds.has("ram_foreign"), kinds.has("disk")];
    const state  = { armed: !!alerts.armed, gauges: levels.map((level, k) => ({ level: Math.round(level * 100) / 100, limit: limits[k], alert: alert[k] })) };
    const key    = JSON.stringify(state);
    if (key === this._watchdogKey && figure.state) return;
    this._watchdogKey = key;
    figure.state      = state;
  }

  _renderAlerts(alerts) {
    this.alertShelf.render(alerts);
  }

  _renderImpact(impact) {
    const sources    = impact.sources || {};
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

    const pol    = impact.politeness || null;
    const select = document.getElementById("sb-impact-politeness");
    const toggle = document.getElementById("sb-impact-throttle");
    if (pol) {
      this._politeness = pol;
      if (select && !select.disabled && document.activeElement !== select) select.value = pol.level;
      if (toggle) {
        toggle.textContent = `auto-throttle: ${pol.auto_throttle ? "on" : "off"}`;
        toggle.classList.toggle("is-safe", !!pol.auto_throttle);
      }
    }
    const throttled = impact.throttled || [];

    const missing = [];
    if (sources.psi === false)    missing.push("the kernel exposes no /proc/pressure");
    if (sources.cgroup === false) missing.push("the host has no per-user cgroup slices");

    const mem  = sig.mem || {};
    const io   = sig.io || {};
    const cpu  = sig.cpu || {};
    const swap = sig.swap || {};
    const near = sig.others || {};
    const own  = (sig.mine || {}).stall || {};

    const contended = new Set(contention.map((a) => a.kind));
    const gauge = (kind, res, who) => {
      const meter = (this.impactMeters || {})[kind];
      if (meter) meter.set(who.stall || 0);
      const shareId  = `sb-impact-${kind}-share`;
      const sharePct = (res.mine_share || 0) * 100;
      const worst    = who.user ? ` &middot; worst ${SharedCharts.esc(who.user)} <b>${(who.stall || 0).toFixed(0)}</b>%` : " &middot; no neighbour";
      this._txt(shareId, `your share <b>${sharePct.toFixed(0)}</b>%${worst}`);
      const shareEl = document.getElementById(shareId);
      if (shareEl) shareEl.classList.toggle("is-dominant", !!res.dominant && contended.has(kind));
      this._bar(`${shareId}-bar`, sharePct);
    };
    gauge("mem", mem, near.mem || {});
    gauge("io",  io,  near.io  || {});
    gauge("cpu", cpu, near.cpu || {});
    this._renderBalance(own, near, mine.length > 0);

    const stalled = Math.max(0, ...["cpu", "mem", "io"].map((k) => (near[k] || {}).n || 0));
    this._txt("sb-impact-swap", `<b>${(swap.out_mbs || 0).toFixed(1)}</b> MB/s`);
    this._txt("sb-impact-iorate", `<b>${(io.util || 0).toFixed(0)}</b> %`);
    this._txt("sb-impact-mine", `<b>${(sig.mine || {}).nproc || 0}</b> &middot; ${((sig.mine || {}).mem_gb || 0).toFixed(1)}G`);
    this._txt("sb-impact-stalled", `<b>${stalled}</b> &middot; of ${Math.max(0, (sig.users || []).length - 1)}`);

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
    if (missing.length) culprit = "off";
    if (light) light.className = `impact__light is-${culprit}`;
    if (verdict) {
      verdict.textContent = missing.length ? "unavailable" : mine.length ? "you are the cause" : leak ? "ram climbing" : others.length ? "busy, not you" : "all clear";
    }
    if (lede) {
      lede.textContent = missing.length
        ? `Cannot measure neighbour stall: ${missing.join("; ")}.`
        : mine.length
          ? (throttled.length
              ? `Other users' tasks are stalling on the resources flagged below, and you are their dominant consumer. Your jobs were dropped to nice 19 and idle I/O after the ${throttled.join(", ")} alarm.`
              : "Other users' tasks are stalling on the resources flagged below, and you are their dominant consumer.")
          : leak
            ? "No neighbour is stalling yet, but a process of yours is steadily accumulating RAM. See below."
            : others.length
              ? (top && !top.is_mine
                  ? `Other users are stalling, but you are not the dominant consumer. The largest RAM holder is ${top.user} (${(top.mem_gb || 0).toFixed(0)} GB, ${top.nproc} procs).`
                  : "Other users are stalling, but you are not the dominant consumer.")
              : sources.slice === false
                ? "No neighbour is stalling. This console runs outside your user slice, so jobs launched here are not charged to you."
                : "No neighbour is stalling: no other user's tasks are waiting for CPU, memory or disk.";
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

  _renderBalance(own, near, alarm) {
    const balance = document.getElementById("sb-impact-balance");
    if (!balance) return;

    const worst = (read) => Math.max(0, ...["cpu", "mem", "io"].map((k) => (read(k) || 0) / 100));
    const mine   = worst((k) => own[k]);
    const others = worst((k) => (near[k] || {}).stall);
    const state = { mine: Math.round(mine * 1000) / 1000, others: Math.round(others * 1000) / 1000, alarm };
    const key   = JSON.stringify(state);
    if (key === this._balanceKey && balance.state) return;
    this._balanceKey = key;
    balance.state    = state;
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
    Toast.show(critical ? "NEIGHBOUR IMPACT: you are badly slowing other users" : "Neighbour impact: you are slowing other users", "error");
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

  _spark(cv, series, maxSamples) {
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

    const step = w / ((maxSamples || this.histMax) - 1);
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
