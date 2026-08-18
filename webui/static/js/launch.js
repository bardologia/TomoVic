"use strict";

class RailRunModeBlock {

  constructor(view) {
    this.view     = view;
    this.detachEl = null;
    this.toggle   = null;
    this.hint     = null;
  }

  _detachBlock() {
    const block = document.createElement("div");
    block.className = "rail-block";
    block.innerHTML = `<span class="rail-block__label">Execution</span>`;

    const row = document.createElement("div");
    row.className = "rail-detach";

    this.toggle = document.createElement("button");
    this.toggle.type = "button";
    this.toggle.className = "switch";
    this.toggle.setAttribute("role", "switch");
    this.toggle.innerHTML = `<span class="switch__knob"></span>`;
    this.toggle.addEventListener("click", () => {
      this.view.detach = !this.view.detach;
      this.view._refresh();
    });

    const label = document.createElement("span");
    label.className = "rail-detach__label";
    label.textContent = "Detach from server";

    this.hint = document.createElement("p");
    this.hint.className = "rail-detach__hint";

    row.append(this.toggle, label);
    block.append(row, this.hint);
    return block;
  }

  paint() {
    const detach = this.view.detach;

    this.toggle.classList.toggle("is-on", detach);
    this.toggle.setAttribute("aria-checked", String(detach));
    this.hint.textContent = detach
      ? "The run survives a lost connection or a console restart. Output goes to logs/<script>_<stamp>.out in the repo."
      : "Output streams to this console. The run dies if the console server goes down.";

    if (this.view.scheduleBtn && !this.view.launching) this.view.scheduleBtn.disabled = false;
  }

  build() {
    this.detachEl = this._detachBlock();
    return { detach: this.detachEl };
  }
}


class LaunchView extends ConfigForm {

  static MODEL_COLORS = { input: "#1d4fd8", model: "#16191b", latent: "#a16207", output: "#0f766e", calc: "#7c3aed" };

  static MODEL_TAGS = { input: "input", model: "network", latent: "latent", output: "output", calc: "result" };

  static PROCESS_MEANINGS = {
    pre_process: {
      title  : "Pre-process",
      summary: "Ingests the raw F-SAR products, beamforms the full-stack Capon tomogram, and forms the interferometric image stack.",
      flow   : [
        { kind: "input", glyph: "stack", label: "Raw F-SAR products", sub: "single-look complex stack" },
        { kind: "model", glyph: "beam",  label: "Beamform", tag: "operation", sub: "Capon + interferograms" },
        [
          { kind: "output", glyph: "cube",  label: "Capon tomogram", sub: "full stack" },
          { kind: "output", glyph: "stack", label: "Image stack",    sub: "primary · secondaries · interferograms" },
        ],
      ],
    },
  };

  constructor(runConsole, project) {
    super();
    this.runConsole = runConsole;
    this.project = project;
    this.key = null;
    this.detail = null;
    this.config = null;
    this.detach = true;
    this.cmdEl = null;
    this.manifestEl = null;
    this.launchBtn = null;
    this.scheduleBtn = null;
    this.saveBtn = null;
    this.active = false;
    this.loadSeq = 0;
    this.copyBase = null;
    this.copyRun = "";
    this.copyLoadSeq = 0;
    this.copyTimer = null;
    this.runMode = null;
    this._wireTabs();
    this._wireKeys();
  }

  _resetState() {
    this.dirty         = {};
    this.controls      = {};
    this.dependents    = {};
    this.states        = [];
    this.gates         = [];
    this.repainters    = [];
    this.sections      = [];
    this.pairs         = [];
    this.pairBase      = new Map();
    this.byPath        = new Map();
    this.activeSection = null;
    this.query         = "";
    this.layoutEl      = null;
    this.navHost       = null;
    this.pinsEl        = null;
    this.nomatchEl     = null;
    this.countEl       = null;
    this.detach        = true;
  }

  async show(param) {
    this.active = true;
    const [key, section] = param.split("/");

    if (key === this.key && this.config) {
      if (section) this._setActiveSection(section);
      return;
    }

    const seq = ++this.loadSeq;
    this.key = key;
    this.detail = null;
    this.config = null;
    this._resetState();
    this.activeSection = section || null;

    this._renderSkeleton();

    const detail = await Api.get(`/api/scripts/${key}`);
    if (seq !== this.loadSeq) return;
    if (detail.error) {
      Toast.show("Could not load script", "error");
      window.router.go("scripts");
      return;
    }
    this.detail = detail;
    this._renderHead(detail);
    this._renderRail();
    this._renderSource(detail);
    this._setPane("config");

    const cfg = await Api.get(`/api/scripts/${key}/config`);
    if (seq !== this.loadSeq) return;
    if (!cfg.ok) {
      this._renderConfigError(cfg.error || "could not resolve configuration");
      return;
    }
    this.config = cfg;

    this._renderConfig(cfg);
    this._refresh();
  }

  leave() {
    this.active = false;
  }

  _renderSkeleton() {
    document.getElementById("launch-kicker").textContent = "";
    document.getElementById("launch-variants").innerHTML = "";
    document.getElementById("launch-title").textContent = "Loading...";
    document.getElementById("launch-purpose").textContent = "";
    document.getElementById("launch-facts").innerHTML = "";
    document.getElementById("launch-rail").innerHTML = "";

    const host = document.getElementById("launch-config");
    host.innerHTML = "";
    const wall = document.createElement("div");
    wall.className = "launch-skeleton";
    for (let i = 0; i < 4; i++) {
      const block = document.createElement("div");
      block.className = "launch-skeleton__panel";
      wall.appendChild(block);
    }
    host.appendChild(wall);
  }

  _renderHead(d) {
    this._renderVariants(d);
    document.getElementById("launch-kicker").textContent = d.group_title ? `${d.group_title} · ${d.file}` : `${d.category} · ${d.file}`;
    document.getElementById("launch-title").textContent = d.title;
    document.getElementById("launch-purpose").textContent = d.purpose;
    this._renderFacts();
  }

  _renderVariants(d) {
    const host = document.getElementById("launch-variants");
    host.innerHTML = "";

    const variants = d.variants || [];
    if (variants.length < 2) {
      host.hidden = true;
      return;
    }
    host.hidden = false;

    variants.forEach((v) => {
      const tab = document.createElement("button");
      tab.type = "button";
      tab.className = "launch__variant" + (v.key === d.key ? " is-active" : "");
      tab.setAttribute("role", "tab");
      tab.setAttribute("aria-selected", String(v.key === d.key));
      tab.textContent = v.label;
      if (v.key !== d.key) tab.addEventListener("click", () => window.router.go(`launch/${v.key}`));
      host.appendChild(tab);
    });
  }

  _renderTypeTab(spec, leaf) {
    const host = document.getElementById("launch-variants");
    host.hidden = false;
    host.innerHTML = "";

    const paint = () => {
      const value = this._effective(leaf);
      [...host.children].forEach((child) => child.classList.toggle("is-active", child.dataset.value === value));
    };

    spec.options.forEach(([value, label]) => {
      const tab = document.createElement("button");
      tab.type = "button";
      tab.className = "launch__variant";
      tab.dataset.value = value;
      tab.setAttribute("role", "tab");
      tab.textContent = label;
      tab.addEventListener("click", () => {
        this._setValue(leaf, value);
        paint();
      });
      host.appendChild(tab);
    });

    paint();

    return () => paint();
  }

  _buildModelCard(meaning) {
    const card = document.createElement("section");
    card.className = "modelcard";
    card.id = "launch-model-card";
    this.modelCardEl = card;
    this._paintModelCard(meaning);
    return card;
  }

  _paintModelCard(meaning) {
    const card = this.modelCardEl;
    if (!card) return;
    if (!meaning) {
      card.hidden = true;
      return;
    }
    card.hidden = false;

    card.innerHTML =
      `<div class="modelcard__head"><span class="modelcard__kicker">What ${meaning.title} does</span>` +
      `<p class="modelcard__summary">${meaning.summary}</p></div>` +
      `<div class="modelflow">${this._modelDiagram(meaning.flow)}</div>`;
  }

  _modelDiagram(flow) {
    const SLOT = 200, PAD = 26, BH = 164, GH = 44, TOP = 14;
    const columns = flow.map((col) => (Array.isArray(col) ? col : [col]));
    const maxM    = columns.reduce((m, col) => Math.max(m, col.length), 1);
    const width   = columns.length * SLOT + PAD * 2;
    const height  = TOP * 2 + maxM * BH;

    const laid = columns.map((col, i) => {
      const cx       = PAD + i * SLOT + SLOT / 2;
      const groupTop = TOP + (maxM * BH - col.length * BH) / 2;
      return col.map((node, j) => ({ node, cx, cy: groupTop + j * BH + GH + 8 }));
    });

    let links = "";
    for (let i = 1; i < laid.length; i++) {
      laid[i - 1].forEach((src) => laid[i].forEach((tgt) => {
        const x1 = src.cx + 54, x2 = tgt.cx - 54, mx = (x1 + x2) / 2;
        links += `<path class="mflow-link" d="M${x1} ${src.cy} C ${mx} ${src.cy}, ${mx} ${tgt.cy}, ${x2} ${tgt.cy}" fill="none" marker-end="url(#mflow-arrow)"/>`;
      }));
    }

    let nodes = "";
    laid.flat().forEach(({ node, cx, cy }) => {
      const color = LaunchView.MODEL_COLORS[node.kind] || "#16191b";
      nodes += this._glyph(node.glyph, cx, cy, color) + this._caption(node, cx, cy, color, SLOT);
    });

    return `<svg class="mflow-svg" width="${width}" height="${height}" viewBox="0 0 ${width} ${height}" role="img" aria-label="data flow">` +
      `<defs><marker id="mflow-arrow" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">` +
      `<path d="M0 0L10 5L0 10z" fill="#9aa196"/></marker></defs>` +
      links + nodes + `</svg>`;
  }

  _caption(node, cx, cy, color, slot) {
    const tag = node.tag || LaunchView.MODEL_TAGS[node.kind] || node.kind;
    const sub = node.sub ? `<span class="mflow-sub">${node.sub}</span>` : "";
    const w   = slot - 28;
    return `<foreignObject x="${cx - w / 2}" y="${cy + 50}" width="${w}" height="64">` +
      `<div xmlns="http://www.w3.org/1999/xhtml" class="mflow-cap">` +
      `<span class="mflow-tag" style="color:${color}">${tag}</span>` +
      `<span class="mflow-name">${node.label}</span>${sub}</div></foreignObject>`;
  }

  _glyph(glyph, cx, cy, color) {
    const tint = color + "14";

    if (glyph === "stack") {
      const w = 52, h = 58, x = cx - w / 2, y = cy - h / 2;
      let rows = "";
      [18, 32, 46].forEach((dy) => { rows += `<line x1="${x + 10}" y1="${y + dy}" x2="${x + w - 10}" y2="${y + dy}" stroke="${color}" stroke-width="1" opacity="0.45"/>`; });
      return `<g fill="${tint}" stroke="${color}" stroke-width="1.6">` +
        `<rect x="${x + 14}" y="${y - 14}" width="${w}" height="${h}" rx="4" opacity="0.4"/>` +
        `<rect x="${x + 7}"  y="${y - 7}"  width="${w}" height="${h}" rx="4" opacity="0.7"/>` +
        `<rect x="${x}"      y="${y}"      width="${w}" height="${h}" rx="4"/>${rows}</g>`;
    }

    if (glyph === "cube") {
      const u = 26;
      const top   = `<polygon points="${cx},${cy - 28} ${cx + u},${cy - 13} ${cx},${cy + 2} ${cx - u},${cy - 13}" fill="${color}" opacity="0.20"/>`;
      const left  = `<polygon points="${cx - u},${cy - 13} ${cx},${cy + 2} ${cx},${cy + 32} ${cx - u},${cy + 17}" fill="${color}" opacity="0.11"/>`;
      const right = `<polygon points="${cx + u},${cy - 13} ${cx},${cy + 2} ${cx},${cy + 32} ${cx + u},${cy + 17}" fill="${color}" opacity="0.05"/>`;
      return `<g stroke="${color}" stroke-width="1.5" stroke-linejoin="round">${top}${left}${right}</g>`;
    }

    if (glyph === "beam") {
      const s = 84;
      let arcs = "";
      [16, 28, 40].forEach((r, k) => { arcs += `<path d="M${cx - 24} ${cy - r} A ${r} ${r} 0 0 1 ${cx - 24} ${cy + r}" fill="none" stroke="#fff" stroke-width="1.6" opacity="${0.5 - k * 0.12}"/>`; });
      return `<g><rect x="${cx - s / 2}" y="${cy - s / 2}" width="${s}" height="${s}" rx="11" fill="${color}"/>${arcs}<circle cx="${cx - 24}" cy="${cy}" r="3.2" fill="#fff"/></g>`;
    }

    const r = 30;
    return `<rect x="${cx - r}" y="${cy - r}" width="${r * 2}" height="${r * 2}" rx="6" fill="${tint}" stroke="${color}" stroke-width="1.6"/>`;
  }

  _renderFacts() {
    const host = document.getElementById("launch-facts");
    host.innerHTML = "";
    const facts = [["entry config", this.detail.config_class || "none"]];
    if (this.config) {
      facts.push(["fields", String(this.config.leaves.length)]);
      facts.push(["sections", String(this.sections.length)]);
    }
    facts.forEach(([term, value]) => {
      const dt = document.createElement("dt");
      dt.textContent = term;
      const dd = document.createElement("dd");
      dd.textContent = value;
      host.appendChild(dt);
      host.appendChild(dd);
    });
  }

  _interpreterBlock() {
    const block = document.createElement("div");
    block.className = "rail-block";
    block.innerHTML = `<span class="rail-block__label">Interpreter</span>`;

    const select = document.createElement("select");
    select.className = "run-select";
    select.id = "launch-interpreter";
    (this.project.interpreters || []).forEach((it) => {
      const opt = document.createElement("option");
      opt.value = it.path;
      opt.textContent = `${it.label}  ·  ${it.path}`;
      if (it.path === this.detail.preferred) opt.selected = true;
      select.appendChild(opt);
    });

    block.appendChild(select);
    return block;
  }

  _commandBlock() {
    const block = document.createElement("div");
    block.className = "rail-block";

    const head = document.createElement("div");
    head.className = "rail-block__row";
    head.innerHTML = `<span class="rail-block__label">Command</span>`;

    const copy = document.createElement("button");
    copy.className = "btn btn--mini";
    copy.textContent = "Copy";
    copy.addEventListener("click", () => {
      navigator.clipboard.writeText(this._commandText()).then(() => Toast.show("Command copied", "ok"));
    });
    head.appendChild(copy);

    const code = document.createElement("code");
    code.className = "rail-command";
    this.cmdEl = code;

    block.appendChild(head);
    block.appendChild(code);
    return block;
  }

  _manifestBlock() {
    const block = document.createElement("div");
    block.className = "rail-block";
    block.innerHTML = `<span class="rail-block__label">Overrides</span>`;

    const list = document.createElement("div");
    list.className = "rail-manifest";
    this.manifestEl = list;

    block.appendChild(list);
    return block;
  }

  _copyBlock() {
    const block = document.createElement("div");
    block.className = "rail-block";
    block.innerHTML = `<span class="rail-block__label">Copy from run</span>`;

    const dir = document.createElement("input");
    dir.className = "cfg-edit__input rail-copy__dir";
    dir.spellcheck = false;
    dir.placeholder = "runs directory";
    dir.value = this.copyBase !== null ? this.copyBase : ResultsSources.runs();

    const select = document.createElement("select");
    select.className = "run-select";

    const note = document.createElement("span");
    note.className = "picker__note";

    const apply = document.createElement("button");
    apply.className = "btn btn--ghost rail-copy";
    apply.textContent = "Copy configs";
    apply.title = "Replace every field with the selected run's resolved config, so you only change what should differ";
    apply.disabled = true;

    dir.addEventListener("input", () => {
      this.copyBase = dir.value;
      clearTimeout(this.copyTimer);
      this.copyTimer = setTimeout(() => this._loadCopyRuns(select, note, apply), 350);
    });
    select.addEventListener("change", () => {
      this.copyRun = select.value;
      apply.disabled = !select.value;
    });
    apply.addEventListener("click", () => this._copyFromRun(select.value, apply));

    block.append(dir, select, note, apply);
    this._loadCopyRuns(select, note, apply);
    return block;
  }

  async _loadCopyRuns(select, note, apply) {
    const base = this.copyBase !== null ? this.copyBase : ResultsSources.runs();
    const seq  = ++this.copyLoadSeq;

    note.textContent = "listing...";
    const res = await Api.get(`/api/run-config/runs?base=${encodeURIComponent(base)}`);
    if (seq !== this.copyLoadSeq) return;

    select.innerHTML = "";
    if (!res.ok) {
      note.textContent = res.error || "could not list runs";
      apply.disabled = true;
      return;
    }

    const runs = res.runs || [];
    note.textContent = runs.length ? `${runs.length} run${runs.length > 1 ? "s" : ""} with a stored config` : "no runs with a stored config here";

    const blank = document.createElement("option");
    blank.value = "";
    blank.textContent = runs.length ? "select a run..." : "no runs found";
    select.appendChild(blank);

    runs.forEach((run) => {
      const opt = document.createElement("option");
      opt.value = run.path;
      opt.textContent = run.name;
      if (run.path === this.copyRun) opt.selected = true;
      select.appendChild(opt);
    });

    apply.disabled = !select.value;
  }

  async _copyFromRun(path, apply) {
    if (!path) return;

    apply.disabled = true;
    try {
      const res = await Api.get(`/api/run-config?path=${encodeURIComponent(path)}`);
      if (!res.ok) {
        Toast.show(res.error || "Could not read the run's config", "error");
        return;
      }

      const outcome = this.applyRunConfig(res.config);
      const parts   = [`Copied ${res.run}: ${outcome.applied} override${outcome.applied === 1 ? "" : "s"} set`];
      if (outcome.locked.length) parts.push(`${outcome.locked.length} locked field${outcome.locked.length === 1 ? "" : "s"} kept`);
      if (outcome.skipped.length) parts.push(`${outcome.skipped.length} unknown key${outcome.skipped.length === 1 ? "" : "s"} skipped: ${outcome.skipped.slice(0, 4).join(", ")}${outcome.skipped.length > 4 ? ", ..." : ""}`);
      Toast.show(parts.join(" · "), outcome.skipped.length || outcome.locked.length ? "warn" : "ok");
    } finally {
      apply.disabled = false;
    }
  }

  _actionsBlock() {
    const block = document.createElement("div");
    block.className = "rail-block rail-block--actions";

    const launch = document.createElement("button");
    launch.className = "btn btn--primary rail-launch";
    launch.addEventListener("click", () => this._launch(false));
    this.launchBtn = launch;

    const schedule = document.createElement("button");
    schedule.className = "btn btn--ghost rail-schedule";
    schedule.title = "Queue this exact configuration to launch when the currently running job (and any earlier queued runs) end";
    schedule.addEventListener("click", () => this._launch(true));
    this.scheduleBtn = schedule;

    const save = document.createElement("button");
    save.className = "btn btn--ghost rail-save";
    save.title = "Store this exact configuration in the Saved tab, to launch or schedule any time later";
    save.addEventListener("click", () => this._save());
    this.saveBtn = save;

    block.append(launch, schedule, save);
    return block;
  }

  _renderRail() {
    const host = document.getElementById("launch-rail");
    host.innerHTML = "";

    this.cmdEl       = null;
    this.manifestEl  = null;
    this.launchBtn   = null;
    this.scheduleBtn = null;
    this.saveBtn     = null;
    this.runMode     = null;

    const interp = this._interpreterBlock();

    this.runMode = new RailRunModeBlock(this);
    const runMode = this.runMode.build();

    host.appendChild(interp);
    host.appendChild(runMode.detach);
    host.appendChild(this._copyBlock());
    host.appendChild(this._commandBlock());
    host.appendChild(this._manifestBlock());
    host.appendChild(this._actionsBlock());

    this._refresh();
  }

  _renderConfigError(message) {
    const host = document.getElementById("launch-config");
    host.innerHTML = "";
    const panel = document.createElement("div");
    panel.className = "launch-error";
    const text = document.createElement("pre");
    text.className = "launch-error__text";
    text.textContent = message;
    const retry = document.createElement("button");
    retry.className = "btn btn--ghost";
    retry.textContent = "Retry resolution";
    retry.addEventListener("click", () => this.show(this.key));
    panel.appendChild(text);
    panel.appendChild(retry);
    host.appendChild(panel);
  }

  _renderConfig(cfg) {
    const host = document.getElementById("launch-config");
    host.innerHTML = "";

    if (!cfg.leaves.length) {
      host.innerHTML = `<p class="cfg-note">${cfg.config_class} exposes no configuration fields.</p>`;
      return;
    }

    this.byPath = new Map(cfg.leaves.map((leaf) => [leaf.path, leaf]));

    const typeTab  = cfg.layout.type_tab || null;
    const typeLeaf = typeTab ? this.byPath.get(typeTab.field) : null;

    const meaning = LaunchView.PROCESS_MEANINGS[this.key] || null;

    if (meaning) host.appendChild(this._buildModelCard(meaning));

    host.appendChild(this._buildToolbar(cfg));

    if (typeLeaf) {
      const repaint = this._renderTypeTab(typeTab, typeLeaf);
      this.controls[typeLeaf.path] = { leaf: typeLeaf, reset: repaint };
    }

    this._renderLayout(host, cfg);

    this._renderFacts();
  }

  _navigate(key) {
    window.history.replaceState(null, "", `#/launch/${this.key}/${key}`);
    this._setActiveSection(key);
  }

  _commandText() {
    if (!this.detail) return "";
    return this._commandLine(this.detail.command, " ");
  }

  _refresh() {
    if (this.runMode) this.runMode.paint();

    const n = Object.keys(this.dirty).length;

    if (this.cmdEl) this.cmdEl.textContent = this._commandText();
    if (this.countEl) this.countEl.textContent = n ? `${n} override${n > 1 ? "s" : ""}` : "all defaults";

    if (this.launchBtn) {
      this.launchBtn.classList.toggle("is-armed", n > 0);
      this.launchBtn.innerHTML = n
        ? `&#9654;&nbsp; Launch run <small>${n} override${n > 1 ? "s" : ""}</small>`
        : `&#9654;&nbsp; Launch run <small>all defaults</small>`;
    }

    if (this.scheduleBtn) {
      this.scheduleBtn.classList.toggle("is-armed", n > 0);
      this.scheduleBtn.innerHTML = n
        ? `&#8627;&nbsp; Schedule after current <small>${n} override${n > 1 ? "s" : ""}</small>`
        : `&#8627;&nbsp; Schedule after current <small>all defaults</small>`;
    }

    if (this.saveBtn) {
      this.saveBtn.classList.toggle("is-armed", n > 0);
      this.saveBtn.innerHTML = n
        ? `&#10515;&nbsp; Save for later <small>${n} override${n > 1 ? "s" : ""}</small>`
        : `&#10515;&nbsp; Save for later <small>all defaults</small>`;
    }

    if (this.manifestEl) this._renderManifest();
    this._refreshBadges();
    this._refreshGates();
  }

  _renderManifest() {
    this.manifestEl.innerHTML = "";
    const entries = Object.entries(this.dirty);

    if (!entries.length) {
      const empty = document.createElement("p");
      empty.className = "rail-manifest__empty";
      empty.textContent = "No overrides. Every field launches at its default.";
      this.manifestEl.appendChild(empty);
      return;
    }

    entries.forEach(([path, value]) => {
      const control = this.controls[path];
      const item = document.createElement("button");
      item.type = "button";
      item.className = "rail-override";
      item.title = "Remove override";
      const from = control ? control.leaf.value : "";
      item.innerHTML =
        `<span class="rail-override__path">${SharedCharts.esc(path)}</span>` +
        `<span class="rail-override__change">${SharedCharts.esc(from)} &rarr; <b>${SharedCharts.esc(value)}</b></span>` +
        `<span class="rail-override__x" aria-hidden="true">&times;</span>`;
      item.addEventListener("click", () => this._resetField(path));
      this.manifestEl.appendChild(item);
    });
  }

  async _launch(queue) {
    if (!this.detail || this.launching) return;
    const interp = document.getElementById("launch-interpreter").value;

    this.launching = true;
    if (this.launchBtn) this.launchBtn.disabled = true;
    if (this.scheduleBtn) this.scheduleBtn.disabled = true;
    try {
      await this.runConsole.launch(this.detail.key, interp, this.detail.title, { ...this.dirty }, "", this.detach, queue);
    } finally {
      this.launching = false;
      if (this.launchBtn) this.launchBtn.disabled = false;
      if (this.scheduleBtn) this.scheduleBtn.disabled = false;
    }
  }

  async _save() {
    if (!this.detail || this.saving) return;
    const name = window.prompt("Name this saved run (optional):", "");
    if (name === null) return;

    const interp = document.getElementById("launch-interpreter").value;

    this.saving = true;
    if (this.saveBtn) this.saveBtn.disabled = true;
    try {
      const res = await Api.post("/api/saved-runs", { script_key: this.detail.key, title: this.detail.title, name: name.trim(), interpreter: interp, overrides: { ...this.dirty }, follow_up: null, detach: this.detach });
      if (!res.ok) {
        Toast.show(res.error || "Save failed", "error");
        return;
      }
      Toast.show(`Saved ${res.entry.name || this.detail.title} to the Saved tab`, "ok");
    } finally {
      this.saving = false;
      if (this.saveBtn) this.saveBtn.disabled = false;
    }
  }

  _renderSource(d) {
    const code = document.getElementById("launch-source-code");
    code.textContent = d.source;
    code.className = "language-python";
    if (window.hljs) {
      try {
        window.hljs.highlightElement(code);
      } catch (e) {}
    }
  }

  _setPane(pane) {
    document.querySelectorAll(".launch__tab").forEach((t) => {
      const active = t.dataset.pane === pane;
      t.classList.toggle("is-active", active);
      t.setAttribute("aria-selected", String(active));
    });
    document.getElementById("launch-config").classList.toggle("is-active", pane === "config");
    document.getElementById("launch-source").classList.toggle("is-active", pane === "source");
  }

  _wireTabs() {
    document.querySelectorAll(".launch__tab").forEach((t) => {
      t.addEventListener("click", () => this._setPane(t.dataset.pane));
    });
  }

  _wireKeys() {
    document.addEventListener("keydown", (e) => {
      if (e.key !== "Escape" || !this.active) return;
      if (["INPUT", "SELECT", "TEXTAREA"].includes(document.activeElement.tagName)) {
        document.activeElement.blur();
        return;
      }
      window.router.go("scripts");
    });
  }
}

window.LaunchView = LaunchView;
