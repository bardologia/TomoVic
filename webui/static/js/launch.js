"use strict";

class RailRunModeBlock {

  constructor(view, followSelect) {
    this.view         = view;
    this.followSelect = followSelect;
    this.detachEl     = null;
    this.targetEl     = null;
    this.toggle       = null;
    this.hint         = null;
    this.localBtn     = null;
    this.tbyBtn       = null;
    this.fieldsEl     = null;
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

  _targetBlock() {
    const block = document.createElement("div");
    block.className = "rail-block";
    block.innerHTML = `<span class="rail-block__label">Target</span>`;

    const row = document.createElement("div");
    row.className = "rail-target";

    this.localBtn = document.createElement("button");
    this.localBtn.type = "button";
    this.localBtn.className = "chip";
    this.localBtn.textContent = "This machine";
    this.localBtn.addEventListener("click", () => this._pick("local"));

    this.tbyBtn = document.createElement("button");
    this.tbyBtn.type = "button";
    this.tbyBtn.className = "chip";
    this.tbyBtn.textContent = "Terrabyte";
    this.tbyBtn.addEventListener("click", () => this._pick("terrabyte"));

    row.append(this.localBtn, this.tbyBtn);
    block.appendChild(row);
    block.appendChild(this._fieldsBlock());
    return block;
  }

  _fieldsBlock() {
    const fields = document.createElement("div");
    fields.className = "rail-tby";
    fields.hidden = true;
    fields.innerHTML =
      `<label class="rail-tby__field"><span>GPUs / job</span><input id="tby-gpus" type="number" min="0" max="4"></label>` +
      `<label class="rail-tby__field"><span>Walltime</span><input id="tby-time" type="text"></label>` +
      `<label class="rail-tby__field"><span>Partition</span><select id="tby-partition"></select></label>` +
      `<label class="rail-tby__field"><span>Account</span><input id="tby-account" type="text" placeholder="none (hpda-c)"></label>` +
      `<label class="rail-tby__field rail-tby__field--check"><input id="tby-sweep" type="checkbox"><span>Fan out trials (subrun &times; seed units packed into node-sized bundle jobs that queue them over an in-job GPU pool; benchmark and cross-validation also chain a prepare job before and a compare job after)</span></label>` +
      `<label class="rail-tby__field"><span>Bundle jobs</span><input id="tby-bundles" type="number" min="1" title="bundles x GPUs per job is capped at 16 GPUs per sweep"></label>` +
      `<label class="rail-tby__field"><span>Unit limit</span><input id="tby-limit" type="number" min="0" placeholder="all"></label>` +
      `<p class="rail-detach__hint">Jobs are submitted over SSH from the pushed state of main. Paths are translated to the cluster; overrides pointing at machine-local data are rejected. The local GPU picker is ignored: SLURM assigns GPUs per job via --gres.</p>`;

    fields.addEventListener("change", (event) => {
      const map = { "tby-gpus": "gpus", "tby-time": "time", "tby-partition": "partition", "tby-account": "account", "tby-bundles": "bundles", "tby-limit": "limit" };
      const slot = map[event.target.id];
      if (slot) this.view.slurm[slot] = event.target.value;
      if (event.target.id === "tby-sweep") this.view.sweepManual = event.target.checked;
      this.view._refresh();
    });

    this.fieldsEl = fields;
    return fields;
  }

  async _pick(name) {
    if (name === "terrabyte" && !this.view.tbyInfo && !(await this.view._loadTbyInfo())) return;

    this.view.target = name;
    this.view._refresh();
  }

  paintFields() {
    if (!this.fieldsEl || !this.view.tbyInfo) return;

    const options = this.view.tbyInfo.partitions.map((p) => `<option value="${p}"${p === this.view.slurm.partition ? " selected" : ""}>${p}</option>`).join("");
    this.fieldsEl.querySelector("#tby-partition").innerHTML = options;
    this.fieldsEl.querySelector("#tby-gpus").value          = this.view.slurm.gpus;
    this.fieldsEl.querySelector("#tby-time").value          = this.view.slurm.time;
    this.fieldsEl.querySelector("#tby-account").value       = this.view.slurm.account;
    this.fieldsEl.querySelector("#tby-bundles").value       = this.view.slurm.bundles;
    this.fieldsEl.querySelector("#tby-limit").value         = this.view.slurm.limit;
  }

  paint() {
    const detach = this.view.detach;
    const tby    = this.view.target === "terrabyte";

    this.toggle.classList.toggle("is-on", detach);
    this.toggle.setAttribute("aria-checked", String(detach));
    this.toggle.disabled = tby;
    this.hint.textContent = detach
      ? "The run survives a lost connection or a console restart. Output goes to logs/<script>_<stamp>.out in the repo."
      : "Output streams to this console. The run dies if the console server goes down.";

    if (this.followSelect) {
      this.followSelect.disabled = tby || detach;
      this.followSelect.title = detach ? "unavailable for detached runs" : "";
      if (detach) this.followSelect.value = "";
    }

    this.localBtn.classList.toggle("is-active", !tby);
    this.tbyBtn.classList.toggle("is-active", tby);
    this.fieldsEl.hidden = !tby;
    this.fieldsEl.querySelector("#tby-sweep").checked = this.view._effectiveSweep();

    if (this.view.scheduleBtn && !this.view.launching) this.view.scheduleBtn.disabled = tby;

    const page = document.querySelector('[data-page="launch"]');
    if (page) page.classList.toggle("is-tby-target", tby);
  }

  build() {
    this.detachEl = this._detachBlock();
    this.targetEl = this._targetBlock();
    this.paintFields();
    return { detach: this.detachEl, target: this.targetEl };
  }
}


class LaunchView extends ConfigForm {

  static FOLLOW_INFER = {
    train_backbone:             "infer_backbone",
    train_profile_autoencoder:  "infer_profile_autoencoder",
    train_image_autoencoder:    "infer_image_autoencoder",
    train_unrolled:             "infer_unrolled",
    train_dual:                 "infer_dual",
  };

  static MODEL_KEY_TYPE = {
    train_backbone:             "backbone",
    train_profile_autoencoder:  "profile_autoencoder",
    train_image_autoencoder:    "image_autoencoder",
    train_jepa:                 "jepa",
  };

  static JEPA_MEANINGS = {
    profile_only: {
      title  : "JEPA · backbone + profile autoencoder",
      label  : "Backbone + profile autoencoder",
      summary: "Predicts the profile embedding from the raw image stack, then decodes it back to normalized profiles through the profile autoencoder decoder. Select a profile autoencoder run; leave the image autoencoder unset.",
      flow   : [
        { kind: "input",  glyph: "stack",   label: "Image stack",          sub: "primary · secondaries · interferograms" },
        { kind: "model",  glyph: "net",     label: "Backbone",             sub: "predictor" },
        { kind: "latent", glyph: "vector",  label: "Normalized embeddings" },
        { kind: "model",  glyph: "decoder", label: "Profile AE decoder",   sub: "frozen / fine-tuned" },
        { kind: "output", glyph: "curve",   label: "Normalized profiles" },
      ],
    },
    image_only: {
      title  : "JEPA · image autoencoder + backbone",
      label  : "Image autoencoder + backbone",
      summary: "Encodes the image stack with the image autoencoder front-end, then the backbone maps that latent straight to the Gaussian-mixture profile parameters. Select an image autoencoder run; leave the profile autoencoder unset.",
      flow   : [
        { kind: "input",  glyph: "stack",   label: "Image stack",        sub: "primary · secondaries · interferograms" },
        { kind: "model",  glyph: "encoder", label: "Image AE encoder",   sub: "frozen / fine-tuned" },
        { kind: "latent", glyph: "vector",  label: "Image embedding",    sub: "2D latent" },
        { kind: "model",  glyph: "net",     label: "Backbone",           sub: "predictor" },
        { kind: "output", glyph: "params",  label: "Params array",       sub: "amp, μ, σ, amp, μ, σ, …" },
      ],
    },
    image_profile: {
      title  : "JEPA · image autoencoder + backbone + profile autoencoder",
      label  : "Image autoencoder + backbone + profile autoencoder",
      summary: "Encodes the image stack with the image autoencoder front-end, the backbone predicts the profile embedding from that latent, and the profile autoencoder decoder reconstructs the normalized profiles. Select both an image and a profile autoencoder run.",
      flow   : [
        { kind: "input",  glyph: "stack",   label: "Image stack",          sub: "primary · secondaries · interferograms" },
        { kind: "model",  glyph: "encoder", label: "Image AE encoder",     sub: "frozen / fine-tuned" },
        { kind: "latent", glyph: "vector",  label: "Image embedding",      sub: "2D latent" },
        { kind: "model",  glyph: "net",     label: "Backbone",             sub: "predictor" },
        { kind: "latent", glyph: "vector",  label: "Normalized embeddings" },
        { kind: "model",  glyph: "decoder", label: "Profile AE decoder",   sub: "frozen / fine-tuned" },
        { kind: "output", glyph: "curve",   label: "Normalized profiles" },
      ],
    },
  };

  static MODEL_MEANINGS = {
    backbone: {
      title  : "Backbone",
      summary: "Supervised regression that maps the SAR image stack straight to the Gaussian-mixture profile parameters.",
      flow   : [
        { kind: "input",  glyph: "stack",  label: "Image stack",  sub: "primary · secondaries · interferograms" },
        { kind: "model",  glyph: "net",    label: "Backbone",     sub: "supervised network" },
        { kind: "output", glyph: "params", label: "Params array", sub: "amp, μ, σ, amp, μ, σ, …" },
      ],
    },
    profile_autoencoder: {
      title  : "Profile autoencoder",
      summary: "Learns the latent profile (output) space: encodes the fitted normalized profiles into embeddings and reconstructs them.",
      flow   : [
        { kind: "input",  glyph: "curve",   label: "Normalized profiles", sub: "fitted targets" },
        { kind: "model",  glyph: "encoder", label: "Encoder" },
        { kind: "latent", glyph: "vector",  label: "Normalized embeddings" },
        { kind: "model",  glyph: "decoder", label: "Decoder" },
        { kind: "output", glyph: "curve",   label: "Reconstructed profiles" },
      ],
    },
    image_autoencoder: {
      title  : "Image autoencoder",
      summary: "Learns the latent input space: encodes the SAR image stack into a 2D embedding and reconstructs it. The encoder later serves as a JEPA front-end.",
      flow   : [
        { kind: "input",  glyph: "stack",   label: "Image stack",            sub: "primary · secondaries · interferograms" },
        { kind: "model",  glyph: "encoder", label: "Encoder" },
        { kind: "latent", glyph: "vector",  label: "Image embedding",        sub: "2D latent" },
        { kind: "model",  glyph: "decoder", label: "Decoder" },
        { kind: "output", glyph: "stack",   label: "Reconstructed stack" },
      ],
    },
    jepa: LaunchView.JEPA_MEANINGS.profile_only,
  };

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
    extract_params: {
      title  : "Extract Parameters",
      summary: "Fits a per-pixel Gaussian mixture to the Capon tomogram to build the supervised profile-parameter targets.",
      flow   : [
        { kind: "input",  glyph: "cube",   label: "Capon tomogram",      sub: "reflectivity profiles" },
        { kind: "model",  glyph: "fit",    label: "Gaussian-mixture fit", tag: "operation", sub: "per pixel" },
        { kind: "output", glyph: "params", label: "Params array",        sub: "amp, μ, σ, amp, μ, σ, …" },
      ],
    },
    inject_external_params: {
      title  : "Inject External Parameters",
      summary: "Imports Gaussian parameter cubes fitted outside this codebase and writes them into a dataset as a normal parameter run, so a model can train against a collaborator's fit.",
      flow   : [
        { kind: "input",  glyph: "params", label: "External RAT cubes",  sub: "one per azimuth/range window" },
        { kind: "model",  glyph: "fit",    label: "Reorder and stitch",  tag: "operation", sub: "onto the dataset crop" },
        { kind: "output", glyph: "params", label: "Params array",        sub: "amp, μ, σ, amp, μ, σ, …" },
      ],
    },
    infer: {
      title  : "Inference",
      summary: "Runs a trained model over the image stack with a sliding window, stitches the predicted cube, and renders reports.",
      flow   : [
        { kind: "input",  glyph: "run",    label: "Trained run",      sub: "checkpoint + image stack" },
        { kind: "model",  glyph: "net",    label: "Predict",          sub: "sliding window" },
        { kind: "calc",   glyph: "cube",   label: "Stitched cube",    sub: "predicted profiles" },
        { kind: "output", glyph: "report", label: "Reports & figures", sub: "metrics · plots · animations" },
      ],
    },
  };

  static SLURM_DEFAULT_KEYS = ["gpus", "cpus", "mem", "time", "partition", "account", "bundles"];

  static SWEEP_DEFAULT_ENTRIES = ["benchmark", "cross_validate"];

  constructor(runConsole, project) {
    super();
    this.runConsole = runConsole;
    this.project = project;
    this.key = null;
    this.detail = null;
    this.config = null;
    this.modelEndpoint = null;
    this.builder = null;
    this.detach = true;
    this.cmdEl = null;
    this.manifestEl = null;
    this.launchBtn = null;
    this.scheduleBtn = null;
    this.saveBtn = null;
    this.active = false;
    this.loadSeq = 0;
    this.target = "local";
    this.sweepManual = null;
    this.copyBase = null;
    this.copyRun = "";
    this.copyLoadSeq = 0;
    this.copyTimer = null;
    this.slurm = { limit: "" };
    this.tbyInfo = null;
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
    this.modelFamilies = null;
    this.modelHeads    = null;
    this.modelEndpoint = null;
    this.layoutEl      = null;
    this.navHost       = null;
    this.pinsEl        = null;
    this.nomatchEl     = null;
    this.countEl       = null;
    this.builder       = null;
    this.detach        = true;
    this.target        = "local";
    this.sweepManual   = null;
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

    if (this._usesModelPanels(cfg)) {
      const endpoint = this._modelFamiliesEndpoint();
      const models   = await Api.get(endpoint);
      if (seq !== this.loadSeq) return;
      this.modelEndpoint = endpoint;
      this.modelFamilies = (models && models.families) || [];
      this.modelHeads    = (models && models.heads) || [];
    }

    this._renderConfig(cfg);
    this._refresh();
  }

  _usesModelPanels(cfg) {
    return cfg.layout.sections.some((section) => section.panels.some((panel) => panel.kind === "special" && panel.panel !== "experiment_builder"));
  }

  _activeTrainingType() {
    if (LaunchView.MODEL_KEY_TYPE[this.key]) return LaunchView.MODEL_KEY_TYPE[this.key];

    const typeTab = this.config ? this.config.layout.type_tab : null;
    if (typeTab) {
      const leaf = this.byPath.get(typeTab.field);
      if (leaf) return this._effective(leaf);
    }

    return "backbone";
  }

  _modelFamiliesEndpoint() {
    const type = this._activeTrainingType();
    if (type === "image_autoencoder")   return "/api/image-autoencoders";
    if (type === "profile_autoencoder") return "/api/profile-autoencoders";
    return "/api/backbones";
  }

  async _reloadModelsForType() {
    if (!this.config || !this._usesModelPanels(this.config)) return;

    const endpoint = this._modelFamiliesEndpoint();
    if (endpoint === this.modelEndpoint) return;

    const seq    = this.loadSeq;
    const models = await Api.get(endpoint);
    if (seq !== this.loadSeq) return;

    this.modelEndpoint = endpoint;
    this.modelFamilies = (models && models.families) || [];
    this.modelHeads    = (models && models.heads) || [];

    const dirty         = this.dirty;
    const activeSection = this.activeSection;
    const detach        = this.detach;
    const target        = this.target;
    const sweepManual   = this.sweepManual;
    this._resetState();
    this.dirty         = dirty;
    this.activeSection = activeSection;
    this.detach        = detach;
    this.target        = target;
    this.sweepManual   = sweepManual;
    this._renderConfig(this.config);
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
        this._paintTypeCard(value);
        this._reloadModelsForType();
      });
      host.appendChild(tab);
    });

    paint();

    return () => {
      paint();
      this._paintTypeCard(this._effective(leaf));
      this._reloadModelsForType();
    };
  }

  _buildModelCard(meaning) {
    const card = document.createElement("section");
    card.className = "modelcard";
    card.id = "launch-model-card";
    this.modelCardEl = card;
    this._paintModelCard(meaning);
    return card;
  }

  _buildJepaModesCard() {
    const card = document.createElement("section");
    card.className = "modelcard";
    card.id = "launch-model-card";
    this.modelCardEl = card;
    this._paintJepaModesCard();
    return card;
  }

  _paintTypeCard(value) {
    if (value === "jepa") this._paintJepaModesCard();
    else                  this._paintModelCard(LaunchView.MODEL_MEANINGS[value]);
  }

  _paintJepaModesCard() {
    const card = this.modelCardEl;
    if (!card) return;
    card.hidden = false;

    const modes = [
      LaunchView.JEPA_MEANINGS.profile_only,
      LaunchView.JEPA_MEANINGS.image_only,
      LaunchView.JEPA_MEANINGS.image_profile,
    ];

    const rows = modes.map((mode) =>
      `<div class="modelmode">` +
      `<div class="modelmode__head"><span class="modelmode__label">${mode.label}</span>` +
      `<span class="modelmode__sub">${mode.summary}</span></div>` +
      `<div class="modelflow">${this._modelDiagram(mode.flow)}</div></div>`
    ).join("");

    card.innerHTML =
      `<div class="modelcard__head"><span class="modelcard__kicker">What JEPA can do</span>` +
      `<p class="modelcard__summary">JEPA trains in three modes, selected by which autoencoder runs you provide. All three possibilities are shown below.</p></div>` +
      `<div class="modelmodes">${rows}</div>`;
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

    if (glyph === "net") {
      const s = 84, x = cx - s / 2, y = cy - s / 2, lx = cx - 18, rx = cx + 18, rows = [cy - 22, cy, cy + 22];
      let lines = "", dots = "";
      rows.forEach((ly) => rows.forEach((ry) => { lines += `<line x1="${lx}" y1="${ly}" x2="${rx}" y2="${ry}" stroke="#fff" stroke-width="0.8" opacity="0.32"/>`; }));
      rows.forEach((ry) => { dots += `<circle cx="${lx}" cy="${ry}" r="4" fill="#fff"/><circle cx="${rx}" cy="${ry}" r="4" fill="#fff"/>`; });
      return `<g><rect x="${x}" y="${y}" width="${s}" height="${s}" rx="11" fill="${color}"/>${lines}${dots}</g>`;
    }

    if (glyph === "encoder" || glyph === "decoder") {
      const hw = 36, lh = glyph === "encoder" ? 44 : 18, rh = glyph === "encoder" ? 18 : 44;
      const pts = `${cx - hw},${cy - lh} ${cx + hw},${cy - rh} ${cx + hw},${cy + rh} ${cx - hw},${cy + lh}`;
      let dots = "";
      [-14, 0, 14].forEach((dx) => { dots += `<circle cx="${cx + dx}" cy="${cy}" r="3.4" fill="#fff" opacity="0.85"/>`; });
      return `<g><polygon points="${pts}" fill="${color}"/>${dots}</g>`;
    }

    if (glyph === "vector") {
      const w = 32, h = 88, x = cx - w / 2, y = cy - h / 2, cells = 5, ch = h / cells;
      let segs = "";
      for (let k = 1; k < cells; k++) segs += `<line x1="${x}" y1="${y + ch * k}" x2="${x + w}" y2="${y + ch * k}" stroke="${color}" stroke-width="1" opacity="0.5"/>`;
      return `<g><rect x="${x}" y="${y}" width="${w}" height="${h}" rx="4" fill="${tint}" stroke="${color}" stroke-width="1.6"/>${segs}</g>`;
    }

    if (glyph === "params") {
      const cw = 15, h = 34, y = cy - h / 2, xs = [0, 18, 36, 61, 79, 97].map((o) => cx - 56 + o), op = [1, 0.7, 0.45, 1, 0.7, 0.45];
      let cells = "";
      xs.forEach((x, k) => { cells += `<rect x="${x}" y="${y}" width="${cw}" height="${h}" rx="3" fill="${color}" opacity="${op[k]}"/>`; });
      cells += `<text x="${cx + 64}" y="${cy + 6}" font-family="JetBrains Mono, monospace" font-size="18" fill="${color}">…</text>`;
      return `<g>${cells}</g>`;
    }

    if (glyph === "curve") {
      const ax = cx - 38, ay0 = cy - 32, ay1 = cy + 28, axr = cx + 38;
      const axis  = `<path d="M${ax} ${ay0} L${ax} ${ay1} L${axr} ${ay1}" fill="none" stroke="${color}" stroke-width="1.2" opacity="0.4"/>`;
      const curve = `<path d="M${ax + 4} ${ay1 - 2} C ${cx - 16} ${ay1 - 2}, ${cx - 11} ${cy - 30}, ${cx} ${cy - 30} C ${cx + 11} ${cy - 30}, ${cx + 16} ${ay1 - 2}, ${axr - 4} ${ay1 - 2} Z" fill="${tint}" stroke="${color}" stroke-width="2"/>`;
      return `<g>${axis}${curve}</g>`;
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

    if (glyph === "fit") {
      const s = 84;
      const curve = `<path d="M${cx - 28} ${cy + 22} C ${cx - 12} ${cy + 22}, ${cx - 8} ${cy - 20}, ${cx} ${cy - 20} C ${cx + 8} ${cy - 20}, ${cx + 12} ${cy + 22}, ${cx + 28} ${cy + 22}" fill="none" stroke="#fff" stroke-width="1.8" opacity="0.9"/>`;
      let dots = "";
      [[-16, 8], [-4, -12], [9, -7], [19, 12]].forEach(([dx, dy]) => { dots += `<circle cx="${cx + dx}" cy="${cy + dy}" r="2.2" fill="#fff" opacity="0.85"/>`; });
      return `<g><rect x="${cx - s / 2}" y="${cy - s / 2}" width="${s}" height="${s}" rx="11" fill="${color}"/>${curve}${dots}</g>`;
    }

    if (glyph === "run") {
      const s = 78, x = cx - s / 2, y = cy - s / 2, lx = cx - 16, rx = cx + 16, rows = [cy - 18, cy, cy + 18];
      let lines = "", dots = "";
      rows.forEach((ly) => rows.forEach((ry) => { lines += `<line x1="${lx}" y1="${ly}" x2="${rx}" y2="${ry}" stroke="${color}" stroke-width="0.8" opacity="0.3"/>`; }));
      rows.forEach((ry) => { dots += `<circle cx="${lx}" cy="${ry}" r="3.4" fill="${color}"/><circle cx="${rx}" cy="${ry}" r="3.4" fill="${color}"/>`; });
      const badge = `<circle cx="${cx + 28}" cy="${cy - 28}" r="9" fill="${color}"/><path d="M${cx + 23.5} ${cy - 28} l3 3 l5 -6" fill="none" stroke="#fff" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>`;
      return `<g><rect x="${x}" y="${y}" width="${s}" height="${s}" rx="10" fill="${tint}" stroke="${color}" stroke-width="1.6"/>${lines}${dots}${badge}</g>`;
    }

    if (glyph === "report") {
      const w = 52, h = 66, x = cx - w / 2, y = cy - h / 2;
      let lines = "";
      [-18, -10, -2].forEach((dy) => { lines += `<line x1="${cx - 16}" y1="${cy + dy}" x2="${cx + 16}" y2="${cy + dy}" stroke="${color}" stroke-width="1.3" opacity="0.55"/>`; });
      let bars = "";
      [[-16, 14], [-4, 22], [8, 11]].forEach(([dx, bh]) => { bars += `<rect x="${cx + dx}" y="${cy + 26 - bh}" width="7" height="${bh}" rx="1.5" fill="${color}" opacity="0.85"/>`; });
      return `<g><rect x="${x}" y="${y}" width="${w}" height="${h}" rx="4" fill="${tint}" stroke="${color}" stroke-width="1.6"/>${lines}${bars}</g>`;
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

  _followBlock() {
    if (!this.detail || !LaunchView.FOLLOW_INFER[this.detail.key]) return null;

    const block = document.createElement("div");
    block.className = "rail-block";
    block.innerHTML = `<span class="rail-block__label">After run</span>`;

    const select = document.createElement("select");
    select.className = "run-select";
    select.id = "launch-follow";
    [["", "nothing"], [LaunchView.FOLLOW_INFER[this.detail.key], "Inference"]].forEach(([value, label]) => {
      const opt = document.createElement("option");
      opt.value = value;
      opt.textContent = label;
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

  _paintTbyFields() {
    if (this.runMode) this.runMode.paintFields();
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
    const follow = this._followBlock();

    this.runMode = new RailRunModeBlock(this, follow ? follow.querySelector("select") : null);
    const runMode = this.runMode.build();

    host.appendChild(interp);
    if (follow) host.appendChild(follow);
    host.appendChild(runMode.detach);
    host.appendChild(runMode.target);
    host.appendChild(this._copyBlock());
    host.appendChild(this._commandBlock());
    host.appendChild(this._manifestBlock());
    host.appendChild(this._actionsBlock());

    this._refresh();
  }

  async _loadTbyInfo() {
    const info = await Api.get("/api/terrabyte/launch-info");

    if (info.error || !Array.isArray(info.partitions) || !info.defaults || !LaunchView.SLURM_DEFAULT_KEYS.every((key) => key in info.defaults)) {
      Toast.show(`Terrabyte launch info unavailable (${info.error || "malformed response"}); target unchanged`, "error");
      return false;
    }

    this.tbyInfo = info;
    this.slurm   = {
      gpus      : String(info.defaults.gpus),
      cpus      : String(info.defaults.cpus),
      mem       : String(info.defaults.mem),
      time      : String(info.defaults.time),
      partition : String(info.defaults.partition),
      account   : String(info.defaults.account),
      bundles   : String(info.defaults.bundles),
      limit     : this.slurm.limit,
    };

    this._paintTbyFields();
    return true;
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

    const modelType = LaunchView.MODEL_KEY_TYPE[this.key] || (typeLeaf ? this._effective(typeLeaf) : null);
    const meaning   = (modelType && LaunchView.MODEL_MEANINGS[modelType]) || LaunchView.PROCESS_MEANINGS[this.key] || null;

    if (modelType === "jepa") host.appendChild(this._buildJepaModesCard());
    else if (meaning)         host.appendChild(this._buildModelCard(meaning));

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
      const verb = this.target === "terrabyte" ? (this._effectiveSweep() ? "Submit sweep to terrabyte" : "Submit to terrabyte") : "Launch run";
      this.launchBtn.innerHTML = n
        ? `&#9654;&nbsp; ${verb} <small>${n} override${n > 1 ? "s" : ""}</small>`
        : `&#9654;&nbsp; ${verb} <small>all defaults</small>`;
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
    if (this.builder) this.builder.refreshFromView();
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

  _effectiveSweep() {
    if (this.sweepManual !== null) return this.sweepManual;
    if (this.detail && LaunchView.SWEEP_DEFAULT_ENTRIES.includes(this.detail.key)) return true;
    return "trials_mode" in this.dirty || "trials_enabled" in this.dirty;
  }

  async _launchTerrabyte(queue) {
    if (queue) {
      Toast.show("Terrabyte jobs cannot be queued locally — SLURM does the queueing. Submit now, or switch the target to this machine.", "warn");
      return;
    }

    const payload = {
      script_key: this.detail.key,
      overrides: { ...this.dirty },
      resources: {
        gpus      : Number(this.slurm.gpus),
        cpus      : Number(this.slurm.cpus),
        mem       : Number(this.slurm.mem),
        time      : this.slurm.time,
        partition : this.slurm.partition,
        account   : this.slurm.account || null,
        bundles   : Number(this.slurm.bundles) || 1,
      },
      sweep: this._effectiveSweep(),
      limit: Number(this.slurm.limit) || 0,
    };

    const res  = await Api.post("/api/terrabyte/launch", payload);
    const jobs = res.jobs || [];

    if (!res.ok && !jobs.length) {
      Toast.show(res.error || "Terrabyte submission failed", "error");
      return;
    }

    if (!res.ok) {
      Toast.show(`Sweep failed partway: ${jobs.length} job${jobs.length > 1 ? "s are" : " is"} already live on terrabyte · ${res.error || "submission failed"}`, "warn");
    } else if (res.deferred) {
      Toast.show(`Uploading ${res.transfers.length} path${res.transfers.length > 1 ? "s" : ""} to SCRATCH — the job submits automatically once the transfer lands`, "ok");
    } else {
      Toast.show(jobs.length === 1 ? `Submitted job ${jobs[0]} to terrabyte` : `Submitted ${jobs.length} jobs to terrabyte`, "ok");
    }

    if (res.console_job_id) {
      if (window.router) window.router.go("console");
      await this.runConsole.refresh();
      this.runConsole.open(res.console_job_id);
      return;
    }

    if (window.router) window.router.go("terrabyte");
  }

  async _launch(queue) {
    if (!this.detail || this.launching) return;
    const interp = document.getElementById("launch-interpreter").value;
    const followEl = document.getElementById("launch-follow");
    const follow = this.detach ? "" : (followEl ? followEl.value : "");

    this.launching = true;
    if (this.launchBtn) this.launchBtn.disabled = true;
    if (this.scheduleBtn) this.scheduleBtn.disabled = true;
    try {
      if (this.target === "terrabyte") {
        await this._launchTerrabyte(queue);
      } else {
        await this.runConsole.launch(this.detail.key, interp, this.detail.title, { ...this.dirty }, follow, this.detach, queue);
      }
    } finally {
      this.launching = false;
      if (this.launchBtn) this.launchBtn.disabled = false;
      if (this.scheduleBtn) this.scheduleBtn.disabled = this.target === "terrabyte";
    }
  }

  async _save() {
    if (!this.detail || this.saving) return;
    const name = window.prompt("Name this saved run (optional):", "");
    if (name === null) return;

    const interp = document.getElementById("launch-interpreter").value;
    const followEl = document.getElementById("launch-follow");
    const follow = this.detach ? "" : (followEl ? followEl.value : "");

    this.saving = true;
    if (this.saveBtn) this.saveBtn.disabled = true;
    try {
      const res = await Api.post("/api/saved-runs", { script_key: this.detail.key, title: this.detail.title, name: name.trim(), interpreter: interp, overrides: { ...this.dirty }, follow_up: follow || null, detach: this.detach });
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
