"use strict";

class RunStrip {
  static FILTER_MIN = 7;
  static ROOT_LABEL = "runs";

  constructor(container, opts = {}) {
    this.container  = container;
    this.opts       = opts;
    this.entries    = [];
    this.filter     = "";
    this.openGroups = new Set();
    this.seeded     = false;

    this.container.classList.add("run-strip");
    this.container.innerHTML = `
      <div class="run-strip__bar" hidden>
        <input type="text" class="run-strip__filter" placeholder="filter runs&hellip;" spellcheck="false" autocomplete="off" />
        <span class="run-strip__total"></span>
      </div>
      <div class="run-strip__tree"></div>`;

    this.bar   = this.container.querySelector(".run-strip__bar");
    this.input = this.container.querySelector(".run-strip__filter");
    this.total = this.container.querySelector(".run-strip__total");
    this.tree  = this.container.querySelector(".run-strip__tree");

    this.input.addEventListener("input", () => {
      this.filter = this.input.value.trim().toLowerCase();
      this._paint();
    });
  }

  static prettyStamp(stamp) {
    const m = /^(\d{4})(\d{2})(\d{2})_(\d{2})(\d{2})(\d{2})$/.exec(stamp || "");
    if (!m) return stamp || "";
    return `${m[1]}-${m[2]}-${m[3]} ${m[4]}:${m[5]}`;
  }

  static parseName(name) {
    const m      = /^(.*)_(\d{8}_\d{6})(?:_(.+))?$/.exec(name || "");
    const base   = m ? m[1] : (name || "");
    const when   = m ? RunStrip.prettyStamp(m[2]) : "";
    const suffix = m && m[3] ? m[3] : "";
    return { tokens: base.split("-").filter(Boolean), when, suffix };
  }

  static nameHtml(name) {
    const parts  = RunStrip.parseName(name);
    const tokens = parts.tokens.map((tok, i) => `<span class="run-name__tok${i === 0 ? " run-name__tok--model" : ""}">${SharedCharts.esc(tok)}</span>`);
    return `<span class="run-name">${tokens.join(`<span class="run-name__sep">-</span>`)}</span>`;
  }

  static metaHtml(entry) {
    const parts  = RunStrip.parseName(entry.run);
    const pieces = [];

    if (parts.when)   pieces.push(`<span class="cube-run__when">${SharedCharts.esc(parts.when)}</span>`);
    if (entry.stamp)  pieces.push(`<span class="cube-run__when">cube ${SharedCharts.esc(RunStrip.prettyStamp(entry.stamp))}</span>`);
    if (parts.suffix) pieces.push(`<span class="cube-run__badge">${SharedCharts.esc(parts.suffix)}</span>`);

    if (!pieces.length) return "";
    return `<span class="cube-run__meta">${pieces.join("")}</span>`;
  }

  open(group)  { this.openGroups.add(group); }
  close(group) { this.openGroups.delete(group); }

  _stateFor(entry) {
    return this.opts.stateFor ? this.opts.stateFor(entry) : false;
  }

  _matches(entry) {
    if (!this.filter) return true;
    return `${entry.group}/${entry.run} ${entry.stamp || ""}`.toLowerCase().includes(this.filter);
  }

  _buildTree() {
    const root = { name: "", rel: "", dirs: new Map(), entries: [] };

    this.entries.forEach((entry) => {
      const parts = entry.group === "." ? [RunStrip.ROOT_LABEL] : entry.group.split("/");
      let   node  = root;
      let   rel   = "";

      parts.forEach((part, i) => {
        rel = entry.group === "." && i === 0 ? "." : (rel ? `${rel}/${part}` : part);
        if (!node.dirs.has(rel)) node.dirs.set(rel, { name: part, rel, dirs: new Map(), entries: [] });
        node = node.dirs.get(rel);
      });

      node.entries.push(entry);
    });

    return root;
  }

  _countTree(node) {
    node.shown  = node.entries.filter((entry) => this._matches(entry)).length;
    node.picked = node.entries.filter((entry) => this._stateFor(entry)).length;

    node.dirs.forEach((dir) => {
      this._countTree(dir);
      node.shown  += dir.shown;
      node.picked += dir.picked;
    });
  }

  _row(entry, depth) {
    const state = this._stateFor(entry);
    const tag   = this.opts.onPick ? "button" : "div";
    const row   = document.createElement(tag);

    if (tag === "button") row.type = "button";
    row.className = "cube-run" + (this.opts.rowClass ? ` ${this.opts.rowClass}` : "") + (state ? " is-active" : "");
    row.title     = entry.id;
    row.style.paddingLeft = `${9 + depth * 18}px`;

    const main = document.createElement("span");
    main.className = "cube-run__main";
    main.innerHTML = RunStrip.nameHtml(entry.run) + RunStrip.metaHtml(entry);
    row.appendChild(main);

    if (this.opts.extras) {
      const extras = document.createElement("span");
      extras.className = "cube-run__extras";
      this.opts.extras(entry).forEach((node) => extras.appendChild(node));
      row.appendChild(extras);
    }

    if (this.opts.onPick) row.addEventListener("click", () => this.opts.onPick(entry));

    return row;
  }

  _dirRow(node, depth, isOpen) {
    const picked = node.picked;
    const count  = this.opts.multi && picked ? `${picked}/${node.shown}` : `${node.shown}`;

    const row = document.createElement("button");
    row.type      = "button";
    row.className = "run-tree__dir" + (isOpen ? " is-open" : "") + (picked ? " is-current" : "");
    row.title     = node.rel === "." ? RunStrip.ROOT_LABEL : node.rel;
    row.style.paddingLeft = `${9 + depth * 18}px`;
    row.innerHTML =
      `<span class="run-tree__chev" aria-hidden="true"></span>` +
      `<span class="run-tree__name">${SharedCharts.esc(node.name)}</span>` +
      `<span class="run-tree__count">${SharedCharts.esc(count)}</span>`;
    row.addEventListener("click", () => {
      if (this.openGroups.has(node.rel)) this.openGroups.delete(node.rel);
      else this.openGroups.add(node.rel);
      this._paint();
    });

    return row;
  }

  _renderNode(node, depth, host) {
    const dirs = [...node.dirs.values()].sort((a, b) => a.name.localeCompare(b.name));

    dirs.forEach((dir) => {
      if (this.filter && !dir.shown) return;

      const isOpen = this.filter ? true : this.openGroups.has(dir.rel);
      host.appendChild(this._dirRow(dir, depth, isOpen));
      if (isOpen) this._renderNode(dir, depth + 1, host);
    });

    node.entries.filter((entry) => this._matches(entry)).forEach((entry) => host.appendChild(this._row(entry, depth)));
  }

  _paint() {
    const root = this._buildTree();
    this._countTree(root);

    this.tree.innerHTML = "";
    this._renderNode(root, 0, this.tree);

    const shown = root.shown;
    if (this.filter && !shown) {
      const note = document.createElement("p");
      note.className   = "run-strip__empty";
      note.textContent = "no runs match the filter";
      this.tree.appendChild(note);
    }

    this.tree.hidden       = !this.entries.length;
    this.bar.hidden        = this.entries.length < RunStrip.FILTER_MIN && !this.filter;
    this.total.textContent = this.filter ? `${shown} / ${this.entries.length} runs` : `${this.entries.length} runs`;
  }

  _seed() {
    this.entries.forEach((entry) => {
      if (!this._stateFor(entry)) return;
      if (entry.group === ".") { this.openGroups.add("."); return; }
      const parts = entry.group.split("/");
      let   rel   = "";
      parts.forEach((part) => {
        rel = rel ? `${rel}/${part}` : part;
        this.openGroups.add(rel);
      });
    });

    let node = this._buildTree();
    while (node.dirs.size === 1 && !node.entries.length) {
      node = node.dirs.values().next().value;
      this.openGroups.add(node.rel);
    }
  }

  repaint() {
    this._paint();
  }

  render(entries) {
    this.entries = entries || [];

    if (!this.seeded && this.entries.length) {
      this.seeded = true;
      this._seed();
    }

    this._paint();
  }
}
