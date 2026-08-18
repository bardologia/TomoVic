"use strict";

class ScriptPanel {
  static SECTIONS = [
    { category: "Data",        blurb: "From raw F-SAR products to training targets: beamform the stacks, fit the Gaussian targets, or import externally fitted parameter cubes." },
    { category: "Training",    blurb: "Train one stage end to end, fan an experiment ladder across GPUs, or run the cumulative feature ablation." },
    { category: "Inference",   blurb: "Turn trained checkpoints into stitched cubes, metrics, and reports." },
    { category: "Analysis",    blurb: "Post-hoc work on finished runs: rebuild trial reports, diagnose trained models, and collect artifacts for publication." },
    { category: "Experiments", blurb: "Structured studies with their own orchestration: benchmarks, cross-validation, sweeps, and tuning." },
  ];
  static TOPIC_ORDER  = ["trials", "diagnostics", "exports"];
  static TOPIC_TITLES = {
    trials      : "Rebuild and compare trials",
    diagnostics : "Model diagnostics",
    exports     : "Exports and collections",
  };

  constructor(refs) {
    this.gridEl   = refs.grid;
    this.filterEl = refs.filters;
    this.scripts  = [];
    this.items    = [];
    this.filter   = "All";
    this.query    = "";
  }

  _items() {
    const items  = [];
    const groups = new Map();

    this.scripts.forEach((s) => {
      if (s.group) {
        if (groups.has(s.group)) {
          groups.get(s.group).hay.push(s.title, s.purpose, s.file, s.key);
          return;
        }
        const variants = s.variants || [];
        const item = {
          key      : s.group,
          href     : `#/launch/${variants[0] ? variants[0].key : s.key}`,
          category : s.group_category || s.category,
          title    : s.group_title || s.title,
          purpose  : s.group_purpose || s.purpose,
          file     : s.file,
          foot     : `${variants.length} stages`,
          hay      : [s.group_purpose || "", ...variants.map((v) => v.label), s.title, s.purpose, s.file, s.key],
          variants,
          topic    : s.topic,
          ablation : false,
        };
        groups.set(s.group, item);
        items.push(item);
        return;
      }

      items.push({
        key      : s.key,
        href     : `#/launch/${s.key}`,
        category : s.category,
        title    : s.title,
        purpose  : s.purpose,
        file     : s.file,
        foot     : s.config_class || "no entry config",
        hay      : [s.title, s.purpose, s.file, s.key],
        variants : [],
        topic    : s.topic,
        ablation : false,
      });
    });

    const train = items.findIndex((it) => it.category === "Training");
    items.splice(train < 0 ? items.length : train + 1, 0, this._ablationItem());
    return items;
  }

  _ablationItem() {
    return {
      key      : "ablation",
      href     : "#/ablation",
      category : "Training",
      title    : "Ablation Study",
      purpose  : "Cumulative ablation of the backbone: train the full model and degrade one selected feature at a time, in order, down to the baseline.",
      file     : "main/training/train_backbone.py",
      foot     : "feature regression",
      hay      : ["Ablation Study", "cumulative ablation feature regression baseline", "main/training/train_backbone.py"],
      variants : [],
      topic    : null,
      ablation : true,
    };
  }

  _renderFilters() {
    this.filterEl.innerHTML = "";

    const search = document.createElement("input");
    search.type        = "search";
    search.className   = "script-search";
    search.placeholder = "search scripts…";
    search.setAttribute("aria-label", "Search scripts");
    search.addEventListener("input", () => {
      this.query = search.value.trim().toLowerCase();
      this._renderSections();
    });
    this.filterEl.appendChild(search);

    const counts = new Map();
    this.items.forEach((it) => counts.set(it.category, (counts.get(it.category) || 0) + 1));

    ["All", ...ScriptPanel.SECTIONS.map((sec) => sec.category)].forEach((cat) => {
      const chip = document.createElement("button");
      chip.type      = "button";
      chip.className = "chip" + (cat === this.filter ? " is-active" : "");
      chip.innerHTML = `${cat} <b>${cat === "All" ? this.items.length : (counts.get(cat) || 0)}</b>`;
      chip.addEventListener("click", () => {
        this.filter = cat;
        [...this.filterEl.querySelectorAll(".chip")].forEach((c) => c.classList.toggle("is-active", c === chip));
        this._renderSections();
      });
      this.filterEl.appendChild(chip);
    });
  }

  _matches(item) {
    if (this.filter !== "All" && item.category !== this.filter) return false;
    if (!this.query) return true;

    const hay = item.hay.join(" ").toLowerCase();
    return this.query.split(/\s+/).every((term) => hay.includes(term));
  }

  _renderSections() {
    this.gridEl.innerHTML = "";
    this.delay = 0;

    let shown = 0;
    ScriptPanel.SECTIONS.forEach((sec) => {
      const items = this.items.filter((it) => it.category === sec.category && this._matches(it));
      if (!items.length) return;
      shown += items.length;

      const section = document.createElement("section");
      section.className = "script-section";
      section.innerHTML =
        `<div class="script-section__head">` +
        `<h3 class="script-section__title">${sec.category}</h3>` +
        `<span class="script-section__count">${items.length} ${items.length === 1 ? "entry point" : "entry points"}</span>` +
        `</div>` +
        `<p class="script-section__blurb">${sec.blurb}</p>`;

      const topics = new Set(items.map((it) => it.topic).filter(Boolean));
      if (topics.size > 1) {
        ScriptPanel.TOPIC_ORDER.forEach((topic) => {
          const subset = items.filter((it) => it.topic === topic);
          if (!subset.length) return;
          const head = document.createElement("h4");
          head.className   = "script-section__topic";
          head.textContent = ScriptPanel.TOPIC_TITLES[topic];
          section.appendChild(head);
          section.appendChild(this._grid(subset));
        });
      } else {
        section.appendChild(this._grid(items));
      }

      this.gridEl.appendChild(section);
    });

    if (!shown) this.gridEl.innerHTML = `<p class="cube-hint">No entry points match this search.</p>`;

    window.revealScan();
  }

  _grid(items) {
    const grid = document.createElement("div");
    grid.className = "script-grid";
    items.forEach((item) => grid.appendChild(this._card(item)));
    return grid;
  }

  _card(item) {
    const card = document.createElement("a");
    card.className = "script-card" + (this.query ? "" : " reveal") + (item.ablation ? " script-card--ablation" : "");
    card.href      = item.href;
    if (!this.query) card.style.transitionDelay = `${Math.min(this.delay, 10) * 0.04}s`;
    this.delay += 1;

    const variants = item.variants.map((v) =>
      `<span class="script-card__variant" data-key="${v.key}">${SharedCharts.esc(v.label)}</span>`
    ).join("");

    card.innerHTML =
      `<span class="script-card__glow"></span>` +
      `<div class="script-card__top"><span class="script-card__cat">${SharedCharts.esc(item.category)}</span>` +
      `<span class="script-card__file">${SharedCharts.esc(item.file)}</span></div>` +
      `<h3 class="script-card__title">${SharedCharts.esc(item.title)}</h3>` +
      `<p class="script-card__purpose" title="${SharedCharts.esc(item.purpose)}">${SharedCharts.esc(item.purpose)}</p>` +
      (variants ? `<div class="script-card__variants">${variants}</div>` : "") +
      `<div class="script-card__foot"><span>${SharedCharts.esc(item.foot)}</span>` +
      `<span class="arrow">configure &rarr;</span></div>`;

    card.querySelectorAll(".script-card__variant").forEach((chip) => {
      chip.addEventListener("click", (ev) => {
        ev.preventDefault();
        ev.stopPropagation();
        window.router.go(`launch/${chip.dataset.key}`);
      });
    });

    return card;
  }

  async load() {
    const data = await Api.get("/api/scripts");

    if (data.error) {
      this.gridEl.textContent = `Could not load scripts: ${data.error}`;
      return;
    }

    this.scripts = data.scripts || [];
    this.items   = this._items();
    this._renderFilters();
    this._renderSections();
  }
}

window.ScriptPanel = ScriptPanel;
