"use strict";

class TileLogPanel {
  static ERROR_RE = /Traceback \(most recent call last\)|^\s*[\w.]*(?:Error|Exception|Interrupt)(?::|$)|\bERROR\b|\bCRITICAL\b|\bFAILED\b|CUDA out of memory|Segmentation fault|core dumped/;

  constructor(tile) {
    this.tile  = tile;
    this.hits  = [];
    this.index = 0;

    this.el = document.createElement("div");
    this.el.className = "console-tile__log";
    this.el.hidden = true;

    this.note = document.createElement("span");
    this.note.className = "console-tile__lognote";

    this.jump = document.createElement("button");
    this.jump.className = "btn btn--mini";
    this.jump.textContent = "Next error";
    this.jump.addEventListener("click", () => this.jumpError());

    this.reload = document.createElement("button");
    this.reload.className = "btn btn--mini";
    this.reload.textContent = "Reload";
    this.reload.addEventListener("click", () => this.load());

    const head = document.createElement("div");
    head.className = "console-tile__loghead";
    head.append(this.note, this.jump, this.reload);

    this.body = document.createElement("pre");
    this.body.className = "console-tile__logbody";

    this.el.append(head, this.body);
  }

  get showing() {
    return !this.el.hidden;
  }

  toggle() {
    const showing = this.el.hidden;

    this.el.hidden = !showing;
    this.tile.logBtn.classList.toggle("is-active", showing);
    this.tile._showPanels();

    if (showing) this.load();
    else this.tile.fit();
  }

  async load() {
    this.note.textContent = "reading…";

    const suffix = this.tile.selectedUnit != null ? `?unit=${this.tile.selectedUnit}` : "";
    const probe = await Api.probe(`/api/jobs/${this.tile.job.job_id}/log${suffix}`);
    const data  = probe.data;

    if (!probe.status) {
      this._fail("backend unreachable");
      return;
    }

    if (probe.status === 404) {
      this._fail("the running console server has no /api/jobs/<id>/log route, restart it to pick up the current code");
      return;
    }

    if (!data || !data.ok) {
      this._fail((data && data.error) || `could not read the log file (HTTP ${probe.status})`);
      return;
    }

    if (!data.available) {
      this._fail(data.reason);
      return;
    }

    this._paint(data);
  }

  _fail(note) {
    this.body.textContent = "";
    this.note.textContent = note;
    this.jump.disabled    = true;
  }

  _paint(data) {
    const lines = data.text.split("\n");

    this.body.textContent = "";
    this.hits = [];

    lines.forEach((line) => {
      const el = document.createElement("span");
      el.className = "console-tile__logline";
      el.textContent = line || " ";
      if (TileLogPanel.ERROR_RE.test(line)) {
        el.classList.add("is-error");
        this.hits.push(el);
      }
      this.body.appendChild(el);
    });

    const bits = [data.path, `${Math.round(data.size / 1024)} KB`];
    if (data.truncated) bits.push(`last ${Math.round(data.shown / 1024)} KB shown`);
    bits.push(this.hits.length ? `${this.hits.length} error lines` : "no error lines");

    this.note.textContent = bits.join(" · ");
    this.note.title = data.path;
    this.jump.disabled = !this.hits.length;
    this.index = this.hits.length - 1;

    if (this.hits.length) this.hits[this.index].scrollIntoView({ block: "center" });
    else this.body.scrollTop = this.body.scrollHeight;
  }

  jumpError() {
    if (!this.hits.length) return;
    this.index = (this.index + 1) % this.hits.length;
    this.hits[this.index].scrollIntoView({ block: "center" });
  }
}

class TileUnitPicker {
  static FILTER_MIN = 8;

  constructor(tile) {
    this.tile  = tile;
    this.query = "";

    this.el = document.createElement("div");
    this.el.className = "console-tile__units";
    this.el.hidden = true;

    this.btn = document.createElement("button");
    this.btn.className = "console-tile__unitpick is-pipeline";
    this.btn.addEventListener("click", () => this._toggleMenu());

    this.btnLabel = document.createElement("span");
    this.btnLabel.className = "console-tile__unitname";
    this.btnLabel.textContent = "pipeline";
    this.btn.appendChild(this.btnLabel);

    this.count = document.createElement("span");
    this.count.className = "console-tile__unitcount";

    this.menu = document.createElement("div");
    this.menu.className = "console-tile__unitmenu";
    this.menu.hidden = true;
    this.menu.addEventListener("keydown", (ev) => {
      if (ev.key === "Escape") this._closeMenu();
    });

    this.filter = document.createElement("input");
    this.filter.className = "console-tile__unitfilter";
    this.filter.type = "text";
    this.filter.placeholder = "filter sub-runs…";
    this.filter.spellcheck = false;
    this.filter.autocomplete = "off";
    this.filter.hidden = true;
    this.filter.addEventListener("input", () => {
      this.query = this.filter.value.trim().toLowerCase();
      this._renderMenu();
    });

    this.body = document.createElement("div");
    this.body.className = "console-tile__unitbody";

    this.menu.append(this.filter, this.body);
    this.el.append(this.btn, this.count, this.menu);

    this._docClick = (ev) => {
      if (!this.el.contains(ev.target)) this._closeMenu();
    };
  }

  rebuild() {
    this.el.hidden = !this.tile.units.length;

    if (!this.tile.units.length) {
      if (this.tile.selectedUnit != null) this.tile._selectUnit(null);
      return;
    }

    if (this.tile.selectedUnit != null && this.tile.selectedUnit >= this.tile.units.length) this.tile._selectUnit(null);

    this.count.textContent = `${this.tile.units.length} sub-runs`;
    this.filter.hidden = this.tile.units.length < TileUnitPicker.FILTER_MIN;
    this._paintButton();
    if (!this.menu.hidden) this._renderMenu();
  }

  _status(unit) {
    const ended = this.tile.job.status !== "running";
    return ended && (unit.status === "running" || unit.status === "queued") ? "stale" : unit.status;
  }

  _labels() {
    const counts = new Map();
    this.tile.units.forEach((u) => counts.set(u.name, (counts.get(u.name) || 0) + 1));

    return this.tile.units.map((u) => {
      if (counts.get(u.name) < 2) return u.name;
      const stem = (u.log.split("/").pop() || "").replace(/\.[^.]*$/, "");
      const extra = stem.startsWith(u.name) ? stem.slice(u.name.length).replace(/^_+/, "") : stem;
      return extra ? `${u.name} · ${extra}` : u.name;
    });
  }

  _tree() {
    const parts = this.tile.units.map((u) => u.log.split("/").filter(Boolean));
    const depth = Math.min(...parts.map((p) => p.length - 1));

    let root = 0;
    while (root < depth && parts.every((p) => p[root] === parts[0][root])) root += 1;

    const tree = { dirs: new Map(), units: [] };
    parts.forEach((p, i) => {
      let node = tree;
      p.slice(root, -1).forEach((seg) => {
        if (!node.dirs.has(seg)) node.dirs.set(seg, { dirs: new Map(), units: [] });
        node = node.dirs.get(seg);
      });
      node.units.push(i);
    });

    this._collapseLoners(tree);
    return tree;
  }

  _collapseLoners(node) {
    for (const [seg, child] of Array.from(node.dirs)) {
      this._collapseLoners(child);
      if (child.units.length === 1 && !child.dirs.size) {
        node.dirs.delete(seg);
        node.units.push(child.units[0]);
      }
    }
    node.units.sort((a, b) => a - b);
  }

  _matches(index, labels) {
    if (!this.query) return true;
    return labels[index].toLowerCase().includes(this.query) || this.tile.units[index].log.toLowerCase().includes(this.query);
  }

  _nodeMatches(node, labels) {
    if (node.units.some((i) => this._matches(i, labels))) return true;
    return Array.from(node.dirs.values()).some((child) => this._nodeMatches(child, labels));
  }

  _renderMenu() {
    const scroll = this.menu.scrollTop;
    const labels = this._labels();

    this.body.innerHTML = "";
    this.body.appendChild(this._row("pipeline", null, null, 0));
    this._renderNode(this._tree(), 0, labels);
    this.menu.scrollTop = scroll;
  }

  _renderNode(node, depth, labels) {
    node.units.forEach((i) => {
      if (!this._matches(i, labels)) return;
      this.body.appendChild(this._row(labels[i], i, this.tile.units[i], depth));
    });

    Array.from(node.dirs.keys()).sort().forEach((seg) => {
      let name = seg;
      let child = node.dirs.get(seg);
      while (child.dirs.size === 1 && !child.units.length) {
        const [nextSeg, nextChild] = child.dirs.entries().next().value;
        name = `${name}/${nextSeg}`;
        child = nextChild;
      }
      if (!this._nodeMatches(child, labels)) return;

      const head = document.createElement("div");
      head.className = "console-tile__unitdir";
      head.style.paddingLeft = `${10 + depth * 14}px`;
      head.textContent = name;
      this.body.appendChild(head);

      this._renderNode(child, depth + 1, labels);
    });
  }

  _row(label, index, unit, depth) {
    const status = unit ? this._status(unit) : "pipeline";

    const el = document.createElement("button");
    el.className = `console-tile__unitrow is-${status}`;
    el.style.paddingLeft = `${10 + depth * 14}px`;
    el.classList.toggle("is-selected", index === this.tile.selectedUnit);
    el.title = unit ? unit.log : `main log of ${this.tile.job.script}`;

    const name = document.createElement("span");
    name.className = "console-tile__unitname";
    name.textContent = label;

    const meta = document.createElement("span");
    meta.className = "console-tile__unitmeta";
    meta.textContent = unit
      ? [status, unit.gpu != null ? `GPU ${unit.gpu}` : "", unit.duration_s != null ? Format.duration(unit.duration_s) : ""].filter(Boolean).join(" · ")
      : "main log";

    el.append(name, meta);
    el.addEventListener("click", () => {
      this._closeMenu();
      this.tile._selectUnit(index);
    });
    return el;
  }

  _paintButton() {
    const unit = this.tile.selectedUnit != null ? this.tile.units[this.tile.selectedUnit] : null;
    const status = unit ? this._status(unit) : "pipeline";

    this.btn.className = `console-tile__unitpick is-${status}`;
    this.btn.classList.toggle("is-open", !this.menu.hidden);
    this.btnLabel.textContent = unit ? this._labels()[this.tile.selectedUnit] : "pipeline";
    this.btn.title = unit ? unit.log : `main log of ${this.tile.job.script}`;
  }

  _toggleMenu() {
    if (this.menu.hidden) this._openMenu();
    else this._closeMenu();
  }

  _openMenu() {
    this.menu.hidden = false;
    this.btn.classList.add("is-open");
    this._renderMenu();
    document.addEventListener("mousedown", this._docClick);
    if (!this.filter.hidden) this.filter.focus();
  }

  _closeMenu() {
    this.menu.hidden = true;
    this.btn.classList.remove("is-open");
    document.removeEventListener("mousedown", this._docClick);
  }
}


class ConsoleTile {
  static POLL_MS = 4000;

  constructor(job, manager, host) {
    this.job = job;
    this.manager = manager;
    this.source = null;
    this.opened = false;

    this.root = document.createElement("div");
    this.root.className = "console-tile";

    const bar = document.createElement("div");
    bar.className = "console-tile__bar";

    this.desc = job.description || "";

    this.nameEl = document.createElement("span");
    this.nameEl.className = "console-tile__name";
    this.nameEl.textContent = job.script;
    this.nameEl.title = job.command;

    this.metaEl = document.createElement("span");
    this.metaEl.className = "console-tile__meta";
    this.metaEl.textContent = this._meta(this._baseMeta(job));
    if (this.desc) this.metaEl.title = this.desc;

    this.badgeEl = document.createElement("span");
    this.badgeEl.className = `badge badge--${job.status}`;
    this.badgeEl.textContent = job.status;

    this.logBtn = document.createElement("button");
    this.logBtn.className = "btn btn--mini";
    this.logBtn.textContent = ".out";
    this.logBtn.hidden = true;
    this.logBtn.title = "Read the log file as plain text, live frames flattened, jumped to the last error";
    this.logBtn.addEventListener("click", () => this.log.toggle());

    this.stopBtn = document.createElement("button");
    this.stopBtn.className = "btn btn--mini btn--danger";
    this.stopBtn.addEventListener("click", () => this._stop());

    this.closeBtn = document.createElement("button");
    this.closeBtn.className = "btn btn--mini";
    this.closeBtn.textContent = "Close";
    this.closeBtn.addEventListener("click", () => this.manager.close(this.job.job_id));

    bar.append(this.nameEl, this.metaEl, this.badgeEl, this.logBtn, this.stopBtn, this.closeBtn);

    this.pollTimer = null;

    this.progWrap = document.createElement("div");
    this.progWrap.className = "console-tile__progress";
    this.progWrap.hidden = true;

    this.progFill = document.createElement("i");
    this.progFill.className = "console-tile__pfill";

    const progTrack = document.createElement("span");
    progTrack.className = "console-tile__ptrack";
    progTrack.appendChild(this.progFill);

    this.progText = document.createElement("span");
    this.progText.className = "console-tile__ptext";

    this.progWrap.append(progTrack, this.progText);

    this.units = [];
    this.unitsSig = null;
    this.selectedUnit = null;
    this.unitTerm = null;
    this.unitFit = null;
    this.unitSource = null;
    this.unitOpened = false;
    this.picker = new TileUnitPicker(this);

    this.unitEl = document.createElement("div");
    this.unitEl.className = "console-tile__out";
    this.unitEl.hidden = true;

    this.log = new TileLogPanel(this);

    this.outEl = document.createElement("div");
    this.outEl.className = "console-tile__out";

    this.root.append(bar, this.progWrap, this.picker.el, this.log.el, this.outEl, this.unitEl);
    host.appendChild(this.root);

    const main = this._makeTerm();
    this.term = main.term;
    this.fitAddon = main.fit;

    this.logBtn.hidden = !job.log_path;

    this.setStatus(job.status);
    this._connect();
    if (job.status !== "running") this._pollProgress();
  }

  _makeTerm() {
    const term = new Terminal({
      cols: 120,
      rows: 24,
      convertEol: true,
      disableStdin: true,
      cursorBlink: false,
      cursorInactiveStyle: "none",
      scrollback: 10000,
      fontFamily: '"JetBrains Mono", ui-monospace, "SF Mono", Menlo, monospace',
      fontSize: 12,
      lineHeight: 1.25,
      theme: {
        background: "#0e1216",
        foreground: "#dde4e7",
        cursor: "#0e1216",
        selectionBackground: "#2a3a52",
      },
    });
    const fit = new FitAddon.FitAddon();
    term.loadAddon(fit);
    return { term, fit };
  }

  _connect() {
    this.source = new EventSource(`/api/jobs/${this.job.job_id}/stream`);
    this.source.onmessage = (ev) => this._onEvent(ev);
    this.source.onerror = () => this._disconnect();
  }

  _disconnect() {
    if (this.source) {
      this.source.close();
      this.source = null;
    }
  }

  _onEvent(ev) {
    let data;
    try {
      data = JSON.parse(ev.data);
    } catch (e) {
      return;
    }

    if (data.type === "chunk") {
      this.term.write(data.data);
    } else if (data.type === "line") {
      this.term.writeln(data.text);
    } else if (data.type === "status") {
      if (data.status === "running") {
        this._note(this._runNote(data), data.adopted && !data.log ? "33" : "36");
        this.metaEl.textContent = this._meta(data.adopted ? `pid ${data.pid} · adopted` : data.detached ? `pid ${data.pid} · detached` : `pid ${data.pid}`);
        if (data.log) {
          this.job.log_path = data.log;
          this.logBtn.hidden = false;
        }
        this.setStatus("running");
      } else if (data.status === "scheduled") {
        this._note(`scheduled to run after ${data.after || "the current job"}`, "33");
      } else if (data.status === "queued") {
        this._note(`queued at position ${data.position} — ${this._queueBlocker(data.blocker)}`, "33");
        this.setStatus("queued");
      } else if (data.status === "cancelled") {
        this._note("cancelled before start", "33");
        this.setStatus("cancelled");
        this.manager.refresh();
      } else {
        this._note(`process ${data.status} (exit ${data.code})`, data.code === 0 ? "36" : "31");
        this.setStatus(data.status);
        this.manager.refresh();
      }
    } else if (data.type === "end") {
      this._disconnect();
    }
  }

  _queueBlocker(blocker) {
    if (!blocker) return "starts when the previous job ends";
    const what = blocker.adopted ? "adopted process" : "job";
    const pid  = blocker.pid ? ` (pid ${blocker.pid})` : "";
    return `held by ${what} ${blocker.script}${pid} — starts when it ends`;
  }

  _runNote(data) {
    const kind = data.adopted ? "adopted process already running under your user" : data.detached ? "running detached" : "process started";
    if (!data.adopted && !data.detached) return `${kind} (pid ${data.pid})`;
    if (data.log) return `${kind} (pid ${data.pid}) — following ${data.log}, stop still kills it`;
    return `${kind} (pid ${data.pid}) — output is not captured, stop still kills it`;
  }

  _meta(base) {
    return this.desc ? `${base} · ${this.desc}` : base;
  }

  _baseMeta(job) {
    return job.pid ? `pid ${job.pid}` : "queued";
  }

  _stop() {
    if (this.job.status === "running") {
      const elapsed = Format.duration((Date.now() - Date.parse(this.job.started)) / 1000);
      if (!window.confirm(`Stop ${this.job.script}?\n\nIt has been running for ${elapsed}. The process group is signalled at once and everything since the last checkpoint is lost.`)) return;
    }
    this.manager.stop(this.job.job_id);
  }

  _note(text, color, term) {
    (term || this.term).write(`\r\n\x1b[2;${color}m── ${text} ──\x1b[0m\r\n`);
  }

  setStatus(status) {
    this.job.status = status;
    this.badgeEl.className = `badge badge--${status}`;
    this.badgeEl.textContent = status;
    this.stopBtn.textContent = status === "scheduled" || status === "queued" ? "Cancel" : "Stop";
    this.stopBtn.disabled = status !== "running" && status !== "scheduled" && status !== "queued";

    if (this.units.length) {
      this.unitsSig = null;
      this.picker.rebuild();
    }

    if (status === "running") this._watchProgress();
    else {
      const hadTimer = Boolean(this.pollTimer);
      this._unwatchProgress();
      if (hadTimer) this._pollProgress();
    }
  }

  _watchProgress() {
    if (this.pollTimer) return;
    this._pollProgress();
    this.pollTimer = setInterval(() => this._pollProgress(), ConsoleTile.POLL_MS);
  }

  _unwatchProgress() {
    clearInterval(this.pollTimer);
    this.pollTimer = null;
  }

  async _pollProgress() {
    const data = await Api.get(`/api/jobs/${this.job.job_id}/progress`);

    const prog = data && data.ok && data.progress;
    if (!prog) return;
    if (prog.units) this._renderUnits(prog.units);
    if (!prog.total) return;
    this._renderProgress(prog);
  }

  _renderUnits(units) {
    this.units = units;
    const sig = units.map((u) => `${u.log}\u0000${u.status}`).join("\u0001");
    if (sig === this.unitsSig) return;
    this.unitsSig = sig;
    this.picker.rebuild();
  }

  _selectUnit(index) {
    if (index === this.selectedUnit) return;

    this.selectedUnit = index;
    this._closeUnitStream();
    if (index != null) this._openUnitStream(index);

    this.logBtn.hidden = !this.job.log_path && index == null;
    if (this.log.showing) this.log.load();

    this._showPanels();
    this.picker._paintButton();
    this.fit();
  }

  _showPanels() {
    const logShowing = this.log.showing;
    this.outEl.hidden = logShowing || this.selectedUnit != null;
    this.unitEl.hidden = logShowing || this.selectedUnit == null;
  }

  _openUnitStream(index) {
    if (!this.unitTerm) {
      const aux = this._makeTerm();
      this.unitTerm = aux.term;
      this.unitFit = aux.fit;
    }

    this.unitTerm.reset();
    this.unitSource = new EventSource(`/api/jobs/${this.job.job_id}/stream?unit=${index}`);
    this.unitSource.onmessage = (ev) => this._onUnitEvent(ev);
    this.unitSource.onerror = () => this._closeUnitStream();
  }

  _closeUnitStream() {
    if (this.unitSource) {
      this.unitSource.close();
      this.unitSource = null;
    }
  }

  _onUnitEvent(ev) {
    let data;
    try {
      data = JSON.parse(ev.data);
    } catch (e) {
      return;
    }

    if (data.type === "chunk") {
      this.unitTerm.write(data.data);
    } else if (data.type === "unit") {
      this._note(`${data.name} — following ${data.log}`, "36", this.unitTerm);
    } else if (data.type === "status") {
      if (data.missing) this._note("not started yet — no log file, reopen once it is running", "33", this.unitTerm);
      else this._note(`unit ${data.status}${data.code != null ? ` (exit ${data.code})` : ""}`, data.status === "done" ? "36" : data.status === "failed" ? "31" : "33", this.unitTerm);
    } else if (data.type === "end") {
      this._closeUnitStream();
    }
  }

  _renderProgress(p) {
    const done = p.done + p.failed;
    const bits = [`${done}/${p.total} units`];
    if (p.eta_s != null) bits.push(`avg ${Format.duration(p.average_s)}/unit`, `ETA ${Format.duration(p.eta_s)}`, `finish ≈ ${p.finish_at.slice(11, 16)}`);
    else if (done < p.total) bits.push("estimating ETA");
    if (p.failed) bits.push(`${p.failed} FAILED`);
    if (p.running && p.running.length) bits.push(`${p.running.length} running now`);

    this.progWrap.hidden = false;
    this.progFill.style.width = `${Math.round((100 * done) / p.total)}%`;
    this.progFill.classList.toggle("is-failing", p.failed > 0);
    this.progText.textContent = bits.join(" · ");
    this.progText.title = p.failed ? `failed: ${p.failed_units.join(", ")}` : (p.running || []).map((r) => r.name).join("\n");
  }

  fit() {
    if (this.log.showing) return;

    if (this.selectedUnit == null) this._fitInto(this.term, this.fitAddon, this.outEl, "opened");
    else if (this.unitTerm) this._fitInto(this.unitTerm, this.unitFit, this.unitEl, "unitOpened");
  }

  _fitInto(term, fitAddon, host, openedFlag) {
    const w = host.clientWidth;
    const h = host.clientHeight;
    if (!w || !h) return;

    if (!this[openedFlag]) {
      term.open(host);
      this[openedFlag] = true;
    }

    let font = Math.max(8, Math.min(16, (w - 16) / 72));
    term.options.fontSize = font;

    let dims = fitAddon.proposeDimensions();
    if (dims && dims.cols && dims.cols < 120) {
      font = Math.max(7, (font * dims.cols) / 120);
      term.options.fontSize = font;
      dims = fitAddon.proposeDimensions();
    }
    if (!dims || !dims.cols || !dims.rows) return;

    term.resize(Math.min(120, dims.cols), Math.max(2, dims.rows));
    term.scrollToBottom();
  }

  dispose() {
    this._disconnect();
    this.picker._closeMenu();
    this._closeUnitStream();
    this._unwatchProgress();
    this.term.dispose();
    if (this.unitTerm) this.unitTerm.dispose();
    this.root.remove();
  }
}


class RunConsole {
  static LIST_POLL_MS = 5000;

  constructor(refs) {
    this.listEl = refs.list;
    this.tilesEl = refs.tiles;
    this.hintEl = refs.hint;
    this.jobs = [];
    this.listError = null;
    this.tiles = new Map();
    this.dismissed = new Set();
    this._fitTimer = null;

    window.addEventListener("resize", () => this._queueFit());
    setInterval(() => {
      if (document.hidden) return;
      if (this.listError || this.jobs.some((j) => RunConsole.isLive(j))) this.refresh();
    }, RunConsole.LIST_POLL_MS);
  }

  static isLive(job) {
    return job.status === "running";
  }

  async refresh() {
    const data = await Api.get("/api/jobs");

    if (data.error) {
      this.listError = data.error;
      this._renderList();
      return;
    }

    this.listError = null;
    this.jobs = data.jobs;
    this.jobs
      .filter((j) => RunConsole.isLive(j) && !this.dismissed.has(j.job_id) && !this.tiles.has(j.job_id))
      .forEach((j) => this.open(j.job_id));
    this._renderList();
  }

  async launch(scriptKey, interpreter, label, overrides, followUp, detach, queue) {
    const res = await Api.post("/api/run", { script_key: scriptKey, interpreter, overrides: overrides || {}, follow_up: followUp || null, detach: !!detach, queue: !!queue });
    if (!res.ok) {
      Toast.show(res.error || (queue ? "Schedule failed" : "Launch failed"), "error");
      return null;
    }
    Toast.show(res.queued ? `Scheduled ${label || scriptKey} to run after the current job` : `Launched ${label || scriptKey}`, "ok");
    if (window.router) window.router.go("console");
    await this.refresh();
    this.open(res.job_id);
    return res.job_id;
  }

  open(jobId) {
    if (this.tiles.has(jobId)) return;
    const job = this.jobs.find((j) => j.job_id === jobId);
    if (!job) return;
    this.dismissed.delete(jobId);
    this.tiles.set(jobId, new ConsoleTile(job, this, this.tilesEl));
    this._layout();
    this._renderList();
  }

  close(jobId) {
    const tile = this.tiles.get(jobId);
    if (!tile) return;
    tile.dispose();
    this.tiles.delete(jobId);
    this.dismissed.add(jobId);
    this._layout();
    this._renderList();
  }

  toggle(jobId) {
    if (this.tiles.has(jobId)) this.close(jobId);
    else this.open(jobId);
  }

  async stop(jobId) {
    const res = await Api.post(`/api/jobs/${jobId}/stop`, {});
    if (res.ok) Toast.show("Stop signal sent", "ok");
    else Toast.show(res.error || "Could not stop", "error");
  }

  onShow() {
    this._queueFit();
  }

  _layout() {
    const n = this.tiles.size;
    this.hintEl.style.display = n ? "none" : "flex";
    const cols = n <= 1 ? 1 : n <= 4 ? 2 : 3;
    const rows = Math.max(1, Math.ceil(n / cols));
    this.tilesEl.style.gridTemplateColumns = `repeat(${cols}, minmax(0, 1fr))`;
    this.tilesEl.style.gridTemplateRows = `repeat(${rows}, minmax(0, 1fr))`;
    this._queueFit();
  }

  _queueFit() {
    clearTimeout(this._fitTimer);
    this._fitTimer = setTimeout(() => this.tiles.forEach((t) => t.fit()), 120);
  }

  _renderList() {
    this.listEl.innerHTML = "";

    if (this.listError) {
      const failed = document.createElement("li");
      failed.className = "job-list__error";
      failed.textContent = `job list unavailable — ${this.listError}`;
      this.listEl.appendChild(failed);
    }

    if (!this.jobs.length) {
      const empty = document.createElement("li");
      empty.className = "job-list__empty";
      empty.textContent = "No jobs yet.";
      this.listEl.appendChild(empty);
      return;
    }

    const followers = new Map();
    this.jobs.forEach((j) => {
      if (j.follow_of) followers.set(j.follow_of, j);
    });

    this.jobs.forEach((job) => {
      if (job.follow_of) return;
      const item = document.createElement("li");
      item.className = "job-item" + (this.tiles.has(job.job_id) ? " is-active" : "");
      const prog = job.progress && job.progress.total ? job.progress : null;
      const progBits = prog ? Format.progressBits(prog).join(" · ") : "";
      const progLine = prog
        ? `<div class="job-item__prog" title="${SharedCharts.esc(progBits)}"><span class="job-item__pbar"><i style="width:${Math.round((100 * (prog.done + prog.failed)) / prog.total)}%" class="${prog.failed ? "is-failing" : ""}"></i></span>${SharedCharts.esc(progBits)}</div>`
        : "";
      item.innerHTML =
        `<div class="job-item__top"><span class="job-item__name">${SharedCharts.esc(job.script)}</span>` +
        `<span class="badge badge--${SharedCharts.esc(job.status)}">${SharedCharts.esc(job.status)}</span></div>` +
        (job.description ? `<div class="job-item__desc" title="${SharedCharts.esc(job.description)}">${SharedCharts.esc(job.description)}</div>` : "") +
        progLine +
        `<div class="job-item__meta">${SharedCharts.esc(job.started.replace("T", " "))}${job.pid ? ` · pid ${SharedCharts.esc(String(job.pid))}` : ""}</div>`;
      item.addEventListener("click", () => this.toggle(job.job_id));

      const next = followers.get(job.job_id);
      if (next) {
        const sub = document.createElement("div");
        sub.className = "job-item__follow" + (this.tiles.has(next.job_id) ? " is-active" : "");
        sub.title = next.description || "";
        sub.innerHTML =
          `<span class="job-item__arrow" aria-hidden="true">&#8627;</span>` +
          `<span class="job-item__name">${SharedCharts.esc(next.script)}</span>` +
          `<span class="badge badge--${SharedCharts.esc(next.status)}">${SharedCharts.esc(next.status)}</span>`;
        sub.addEventListener("click", (ev) => {
          ev.stopPropagation();
          this.toggle(next.job_id);
        });
        item.appendChild(sub);
      }

      this.listEl.appendChild(item);
    });
  }
}

window.RunConsole = RunConsole;
