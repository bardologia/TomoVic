"use strict";

class ResultsView {
  constructor(listEl, detailEl) {
    this.listEl    = listEl;
    this.detailEl  = detailEl;
    this.pathForm  = document.getElementById("results-path-form");
    this.pathInput = document.getElementById("results-path-input");

    this.root      = null;
    this.activeRel = null;
    this.expanded  = new Set();
    this.loaded    = false;

    this.sources     = ResultsSources.all();
    this.catalog     = null;
    this.view        = "folder";
    this.filter      = "";
    this.size        = localStorage.getItem("results-size") || "m";
    this.columns     = Number(localStorage.getItem("results-columns") || 2);
    this.folderData  = null;
    this.galleryData = null;
    this.compare     = [];
    this.figures     = [];
    this.lightboxAt  = -1;

    this.lightbox      = document.getElementById("lightbox");
    this.lightboxImg   = document.getElementById("lightbox-img");
    this.lightboxCap   = document.getElementById("lightbox-cap");
    this.lightboxCount = document.getElementById("lightbox-count");
    this.lightboxPrev  = document.getElementById("lightbox-prev");
    this.lightboxNext  = document.getElementById("lightbox-next");

    this.lightbox.addEventListener("click", () => this._closeLightbox());
    this.lightboxPrev.addEventListener("click", (ev) => { ev.stopPropagation(); this._stepLightbox(-1); });
    this.lightboxNext.addEventListener("click", (ev) => { ev.stopPropagation(); this._stepLightbox(1); });

    document.addEventListener("keydown", (ev) => {
      if (this.lightbox.hidden) return;
      if (ev.key === "Escape")     this._closeLightbox();
      if (ev.key === "ArrowLeft")  this._stepLightbox(-1);
      if (ev.key === "ArrowRight") this._stepLightbox(1);
    });

    this.pathForm.addEventListener("submit", (ev) => {
      ev.preventDefault();
      const path = this.pathInput.value.trim();
      if (path) this.open(path);
    });

    window.addEventListener("resize", () => this._positionIndex());
  }

  enter() {
    if (this.loaded) {
      this.loadCatalog();
      return;
    }
    this.loaded = true;

    this._renderSidebar();
    this.loadCatalog();

    const recents = this._recents();
    if (recents.length) {
      this.pathInput.value = recents[0];
      this.open(recents[0]);
    } else {
      this.detailEl.innerHTML = `<div class="res-empty">Point the sidebar at your datasets and runs folders, then pick a dataset, parameter extraction or run &mdash; or paste any run directory above and press Open.</div>`;
    }
  }

  async loadCatalog() {
    if (!this.sources.datasets && !this.sources.logs) {
      this.catalog = null;
      this._renderSidebar();
      return;
    }

    const data = await Api.get(`/api/results/catalog?datasets=${encodeURIComponent(this.sources.datasets)}&logs=${encodeURIComponent(this.sources.logs)}`);

    this.catalog = data.ok ? data : null;
    this._renderSidebar();
  }

  async open(path) {
    this.detailEl.innerHTML = `<div class="res-empty">Loading&hellip;</div>`;

    const data = await Api.get(`/api/results/tree?path=${encodeURIComponent(path)}`);

    if (!data.ok) {
      this.root = null;
      this._renderSidebar();
      this.detailEl.innerHTML = `<div class="res-empty">${SharedCharts.esc(data.error || "Could not open this path.")}</div>`;
      return;
    }

    this.root            = data;
    this.pathInput.value = data.root;
    this._remember(data.root);

    this.expanded = new Set([""]);

    this.view        = "folder";
    this.filter      = "";
    this.galleryData = null;
    this.compare     = this._loadCompare();

    this._renderSidebar();
    this.selectFolder("");
  }

  close() {
    this.root        = null;
    this.activeRel   = null;
    this.folderData  = null;
    this.galleryData = null;
    this.pathInput.value = "";
    this.detailEl.innerHTML = `<div class="res-empty">Pick a dataset, parameter extraction or run.</div>`;
    this._renderSidebar();
  }

  async selectFolder(rel) {
    this.activeRel = rel;
    this.view      = "folder";
    this._renderSidebar();

    const data = await Api.get(`/api/results/folder?root=${encodeURIComponent(this.root.root)}&rel=${encodeURIComponent(rel)}`);

    if (!data.ok) {
      this.detailEl.innerHTML = `<div class="res-empty">${SharedCharts.esc(data.error || "Could not load this folder.")}</div>`;
      return;
    }

    this.folderData = data;
    this._renderDetail();
  }

  async showView(view) {
    this.view = view;

    if (view === "all" && !this.galleryData) {
      const data = await Api.get(`/api/results/gallery?root=${encodeURIComponent(this.root.root)}`);

      if (!data.ok) {
        this.galleryData = null;
        this.detailEl.innerHTML = `<div class="res-empty">${SharedCharts.esc(data.error || "Could not load the gallery.")}</div>`;
        return;
      }

      this.galleryData = data;
    }

    this._renderDetail();
  }

  _renderSidebar() {
    this.listEl.innerHTML = "";
    this._renderSources();

    if (this.catalog) {
      const datasets = this.catalog.datasets;
      this._renderGroupHead("Datasets", datasets.items.length);
      if (datasets.error && this.sources.datasets) this._renderNote(datasets.error, true);
      if (!datasets.error && !datasets.items.length) this._renderNote("no datasets found", false);
      datasets.items.forEach((dataset) => {
        this._renderEntry(dataset.name, dataset.path, "preprocess", 0);

        const active = this.root && (this.root.root === dataset.path || dataset.params.some((param) => param.path === this.root.root));
        if (active) dataset.params.forEach((param) => this._renderEntry(param.name, param.path, "params", 1));
      });

      const runs = this.catalog.runs;
      this._renderGroupHead("Runs", runs.items.length);
      if (runs.error && this.sources.logs) this._renderNote(runs.error, true);
      if (!runs.error && !runs.items.length) this._renderNote("no runs found", false);
      runs.items.forEach((run) => this._renderEntry(run.name, run.path, run.stage, 0));
    }

    if (this.root && !this._inCatalog(this.root.root)) {
      this._renderGroupHead("Opened path", "");
      this._renderEntry(this.root.name, this.root.root, this.root.stage, 0);
    }
  }

  _renderSources() {
    const box = document.createElement("form");
    box.className = "res-src";
    box.innerHTML =
      `<div class="res-src__head">Sources</div>` +
      `<label>Datasets dir<input id="res-src-datasets" type="text" value="${SharedCharts.esc(this.sources.datasets)}" placeholder="/path/to/datasets" spellcheck="false" autocomplete="off" /></label>` +
      `<label>Runs dir<input id="res-src-logs" type="text" value="${SharedCharts.esc(this.sources.logs)}" placeholder="/path/to/runs" spellcheck="false" autocomplete="off" /></label>` +
      `<button type="submit" class="btn btn--mini">Apply</button>`;

    box.addEventListener("submit", (ev) => {
      ev.preventDefault();
      this.sources = {
        datasets : box.querySelector("#res-src-datasets").value.trim(),
        logs     : box.querySelector("#res-src-logs").value.trim(),
      };
      ResultsSources.save(this.sources);
      this.loadCatalog();
    });

    this.listEl.appendChild(box);
  }

  _renderGroupHead(title, count) {
    const head = document.createElement("div");
    head.className = "run-group__head";
    head.innerHTML = `<span>${SharedCharts.esc(title)}</span><span class="run-group__count">${count}</span>`;
    this.listEl.appendChild(head);
  }

  _renderNote(text, isError) {
    const note = document.createElement("div");
    note.className = "res-cat__note" + (isError ? " res-cat__note--err" : "");
    note.textContent = text;
    this.listEl.appendChild(note);
  }

  _renderEntry(name, path, stage, depth) {
    const isOpen = this.root && this.root.root === path;

    const row = document.createElement("button");
    row.type = "button";
    row.className = "res-cat__row" + (isOpen ? " is-open" : "") + (isOpen && this.activeRel === "" && this.view === "folder" ? " is-active" : "");
    row.style.paddingLeft = `${8 + depth * 14}px`;
    row.title = path;
    row.innerHTML = `<span class="res-cat__name">${SharedCharts.esc(name)}</span><span class="res-cat__stage">${SharedCharts.esc(stage)}</span>`;
    row.addEventListener("click", () => isOpen ? this.close() : this.open(path));
    this.listEl.appendChild(row);

    if (isOpen) this.root.tree.children.forEach((child) => this._renderNode(child, depth + 1));
  }

  _inCatalog(path) {
    if (!this.catalog) return false;
    if (this.catalog.runs.items.some((run) => run.path === path)) return true;
    return this.catalog.datasets.items.some((dataset) => dataset.path === path || dataset.params.some((param) => param.path === path));
  }

  _renderNode(node, depth) {
    const total   = node.counts.markdown + node.counts.images + node.counts.animations + node.counts.configs + (node.counts.logs || 0);
    const isOpen  = this.expanded.has(node.rel);
    const hasKids = node.children.length > 0;

    const row = document.createElement("div");
    row.className = "res-tree__row" + (hasKids && isOpen ? " is-open" : "") + (node.rel === this.activeRel && this.view === "folder" ? " is-active" : "");
    row.style.paddingLeft = `${8 + depth * 14}px`;

    const name = document.createElement("span");
    name.className = "res-tree__name";
    name.textContent = node.rel === "" ? "/" : node.name;
    row.appendChild(name);

    if (total) {
      const badge = document.createElement("span");
      badge.className = "res-tree__count";
      badge.textContent = total;
      row.appendChild(badge);
    }

    row.addEventListener("click", () => {
      if (hasKids) {
        if (isOpen) this.expanded.delete(node.rel);
        else this.expanded.add(node.rel);
      }
      this.selectFolder(node.rel);
    });
    this.listEl.appendChild(row);

    if (isOpen) node.children.forEach((child) => this._renderNode(child, depth + 1));
  }

  _renderDetail() {
    this.detailEl.innerHTML = this._toolbarHtml() + `<div class="res-body" id="res-body" data-size="${this.size}"></div>`;
    this._bindToolbar();
    this._renderBody();
  }

  _renderBody() {
    const body = this.detailEl.querySelector("#res-body");
    if (!body) return;

    let html = "";
    if (this.view === "folder")  html = this._folderHtml();
    if (this.view === "all")     html = this._galleryHtml();
    if (this.view === "compare") html = this._compareHtml();

    body.innerHTML = `<div class="res-main">${html}</div>`;

    if (this.view === "folder") {
      this._fillMarkdown(body);
      this._fillConfigs(body);
      this._fillLogs(body);
    }

    if (this.view !== "compare") this._buildIndex(body);

    this._collectFigures(body);
    this._bindBody(body);
  }

  _buildIndex(body) {
    const sections = [...body.querySelectorAll(".res-section")];
    if (sections.length < 2) return;

    const nav = document.createElement("nav");
    nav.setAttribute("aria-label", "Section index");

    if (this.view === "folder") {
      nav.className = "res-index res-index--book";
      this._buildBookIndex(nav, sections);
    } else {
      nav.className = "res-index";
      this._buildChipIndex(nav, sections);
    }

    if (!nav.children.length) return;

    body.appendChild(nav);
    this._positionIndex();
  }

  _buildChipIndex(nav, sections) {
    sections.forEach((section, index) => {
      const cap = section.querySelector(".res-section__cap");
      if (!cap) return;

      section.id   = `res-sec-${index}`;
      const source = cap.querySelector("button") || cap;
      const tally  = cap.querySelector("span");

      nav.appendChild(this._indexLink(
        this._indexLabel(source.textContent),
        tally ? tally.textContent.trim() : "",
        () => section.scrollIntoView({ behavior: "smooth", block: "start" }),
        false,
        false,
      ));
    });
  }

  _buildBookIndex(nav, sections) {
    sections.forEach((section, index) => {
      const cap = section.querySelector(".res-section__cap");
      if (!cap || section.querySelector(".res-cfg")) return;

      section.id   = `res-sec-${index}`;
      const source = cap.querySelector("button") || cap;
      const tally  = cap.querySelector("span");
      const heads  = [...section.querySelectorAll(".res-md h2, .res-md h3")].filter((h) => h.textContent.trim());

      const tree = [];
      heads.forEach((h, hi) => {
        h.id = `res-sec-${index}-h${hi}`;
        h.classList.add("res-index__anchor");

        const last = tree[tree.length - 1];
        if (h.tagName === "H3" && last && last.head.tagName === "H2") last.children.push(h);
        else tree.push({ head: h, children: [] });
      });

      const subGroups = tree.map((node) => {
        const label = this._headingLink(node.head, true);
        const deep  = node.children.map((child) => this._headingLink(child, true, true));
        return this._indexGroup(label, deep);
      });

      const mainLabel = this._indexLink(
        this._indexLabel(source.textContent),
        tally ? tally.textContent.trim() : "",
        () => section.scrollIntoView({ behavior: "smooth", block: "start" }),
        false,
        false,
      );

      const mainGroup = this._indexGroup(mainLabel, subGroups, true);
      if (subGroups.length) mainGroup.classList.add("res-index__group--wide");
      nav.appendChild(mainGroup);
    });
  }

  _headingLink(head, isSub, isDeep = false) {
    return this._indexLink(
      head.textContent.trim(),
      "",
      () => head.scrollIntoView({ behavior: "smooth", block: "start" }),
      isSub,
      isDeep || head.tagName === "H3",
    );
  }

  _indexGroup(label, children, open = false) {
    const group = document.createElement("div");
    group.className = "res-index__group" + (open && children.length ? " is-open" : "");

    const head = document.createElement("div");
    head.className = "res-index__grouphead";

    const caret = document.createElement("button");
    caret.type      = "button";
    caret.className = "res-index__caret" + (children.length ? (open ? " is-open" : "") : " res-index__caret--none");
    caret.textContent = "▸";
    if (children.length) caret.addEventListener("click", () => {
      caret.classList.toggle("is-open", group.classList.toggle("is-open"));
      this._positionIndex();
    });

    head.appendChild(caret);
    head.appendChild(label);
    group.appendChild(head);

    if (children.length) {
      const subs = document.createElement("div");
      subs.className = "res-index__subs";
      children.forEach((child) => subs.appendChild(child));
      group.appendChild(subs);
    }

    return group;
  }

  _indexLabel(text) {
    const clean = text.replace(/\s+\d+(\s+of\s+\d+)?\s*$/, "").trim();
    return this._relLabel(clean) || "section";
  }

  _relLabel(rel) {
    const roots = ["figures", "images", "animations"];

    let best = -1;
    let mlen = 0;
    roots.forEach((root) => {
      const at = rel.lastIndexOf(`${root}/`);
      if (at > best) { best = at; mlen = root.length + 1; }
    });

    if (best !== -1) return rel.slice(best + mlen) || rel.slice(best, best + mlen - 1);
    if (roots.some((root) => rel === root || rel.endsWith(`/${root}`))) return rel.slice(rel.lastIndexOf("/") + 1);

    return rel;
  }

  _indexLink(label, count, onClick, isSub, isDeep) {
    const link = document.createElement("button");
    link.type      = "button";
    link.className = "res-index__link" + (isSub ? " res-index__link--sub" : "") + (isDeep ? " res-index__link--deep" : "");
    link.innerHTML = `${SharedCharts.esc(label)}${count ? `<span>${SharedCharts.esc(count)}</span>` : ""}`;
    link.addEventListener("click", onClick);
    return link;
  }

  _positionIndex() {
    const nav = this.detailEl.querySelector(".res-index");
    const bar = this.detailEl.querySelector(".res-bar");
    if (!nav || !bar) return;

    nav.style.top = `${bar.offsetHeight + 12}px`;

    const margin = bar.offsetHeight + 12;
    this.detailEl.querySelectorAll(".res-section, .res-index__anchor").forEach((el) => {
      el.style.scrollMarginTop = `${margin}px`;
    });
  }

  _toolbarHtml() {
    const crumbs = this._crumbsHtml();
    const count  = this.compare.length;

    return (
      `<div class="res-bar">` +
      `<div class="res-bar__row">${crumbs}<span class="res-stamp is-active is-single">${SharedCharts.esc(this.root.stage)}</span></div>` +
      `<div class="res-bar__row res-bar__row--controls">` +
      `<div class="res-views" role="group" aria-label="Result views">` +
      `<button type="button" data-view="folder" class="${this.view === "folder" ? "is-active" : ""}">Folder</button>` +
      `<button type="button" data-view="all" class="${this.view === "all" ? "is-active" : ""}">All plots</button>` +
      `<button type="button" data-view="compare" class="${this.view === "compare" ? "is-active" : ""}">Compare <span id="res-compare-count">${count}</span></button>` +
      `</div>` +
      `<input type="search" class="res-filter" id="res-filter" placeholder="Filter plots by name" value="${SharedCharts.esc(this.filter)}" spellcheck="false" />` +
      `<div class="res-sizes" id="res-sizes" role="group" aria-label="Thumbnail size" ${this.view === "compare" ? "hidden" : ""}>` +
      ["s", "m", "l"].map((s) => `<button type="button" data-size="${s}" class="${this.size === s ? "is-active" : ""}">${s.toUpperCase()}</button>`).join("") +
      `</div>` +
      `<div class="res-sizes" id="res-cols" role="group" aria-label="Compare columns" ${this.view === "compare" ? "" : "hidden"}>` +
      [1, 2, 3, 4].map((n) => `<button type="button" data-cols="${n}" class="${this.columns === n ? "is-active" : ""}">${n}</button>`).join("") +
      `</div>` +
      `</div></div>`
    );
  }

  _crumbsHtml() {
    let html = `<nav class="res-crumbs" aria-label="Folder path">`;
    html += `<button type="button" data-rel="">${SharedCharts.esc(this.root.name)}</button>`;

    if (this.view === "folder" && this.activeRel) {
      const parts = this.activeRel.split("/");
      parts.forEach((part, index) => {
        const rel = parts.slice(0, index + 1).join("/");
        html += `<span class="res-crumbs__sep">/</span><button type="button" data-rel="${SharedCharts.esc(rel)}">${SharedCharts.esc(part)}</button>`;
      });
    }

    if (this.view === "all")     html += `<span class="res-crumbs__sep">/</span><span class="res-crumbs__here">all plots</span>`;
    if (this.view === "compare") html += `<span class="res-crumbs__sep">/</span><span class="res-crumbs__here">compare</span>`;

    html += `</nav>`;
    return html;
  }

  _bindToolbar() {
    this.detailEl.querySelectorAll(".res-views button").forEach((btn) => {
      btn.addEventListener("click", () => this.showView(btn.dataset.view));
    });

    this.detailEl.querySelectorAll(".res-crumbs button").forEach((btn) => {
      btn.addEventListener("click", () => this.selectFolder(btn.dataset.rel));
    });

    const filter = this.detailEl.querySelector("#res-filter");
    filter.addEventListener("input", () => {
      this.filter = filter.value.trim().toLowerCase();
      this._renderBody();
    });

    this.detailEl.querySelectorAll("#res-sizes button").forEach((btn) => {
      btn.addEventListener("click", () => {
        this.size = btn.dataset.size;
        localStorage.setItem("results-size", this.size);
        this.detailEl.querySelectorAll("#res-sizes button").forEach((b) => b.classList.toggle("is-active", b === btn));
        this.detailEl.querySelector("#res-body").dataset.size = this.size;
      });
    });

    this.detailEl.querySelectorAll("#res-cols button").forEach((btn) => {
      btn.addEventListener("click", () => {
        this.columns = Number(btn.dataset.cols);
        localStorage.setItem("results-columns", String(this.columns));
        this.detailEl.querySelectorAll("#res-cols button").forEach((b) => b.classList.toggle("is-active", b === btn));
        const grid = this.detailEl.querySelector(".res-compare__grid");
        if (grid) grid.style.gridTemplateColumns = `repeat(${this.columns}, 1fr)`;
      });
    });
  }

  _folderHtml() {
    const data = this.folderData;
    let html   = `<p class="res-path">${SharedCharts.esc(data.abs)}</p>`;

    data.markdown.forEach((md, index) => {
      html += `<section class="res-section">`;
      html += `<h4 class="res-section__cap">${SharedCharts.esc(md.name)}</h4>`;
      html += `<article class="res-md" data-md="${index}"></article>`;
      html += `</section>`;
    });

    const images     = this._applyFilter(data.images);
    const animations = this._applyFilter(data.animations);

    if (images.length)     html += this._sectionHtml("Plots", images, "img", data.rel, data.images.length);
    if (animations.length) html += this._sectionHtml("Animations", animations, "gif", data.rel, data.animations.length);

    if (this.filter && !images.length && data.images.length)         html += `<section class="res-section"><h4 class="res-section__cap">Plots</h4><div class="res-empty res-empty--tight">No plot matches the filter.</div></section>`;
    if (this.filter && !animations.length && data.animations.length) html += `<section class="res-section"><h4 class="res-section__cap">Animations</h4><div class="res-empty res-empty--tight">No animation matches the filter.</div></section>`;

    if (data.configs.length) {
      html += `<section class="res-section"><h4 class="res-section__cap">Configs <span>${data.configs.length}</span></h4>`;
      data.configs.forEach((cfg, index) => {
        html += `<details class="res-cfg"${data.configs.length === 1 ? " open" : ""}>`;
        html += `<summary>${SharedCharts.esc(cfg.name)}</summary>`;
        html += `<pre><code data-cfg="${index}"></code></pre>`;
        html += `</details>`;
      });
      html += `</section>`;
    }

    if (data.logs.length) {
      html += `<section class="res-section"><h4 class="res-section__cap">Logs <span>${data.logs.length}</span></h4>`;
      data.logs.forEach((log, index) => {
        html += `<details class="res-cfg res-cfg--log"${data.logs.length === 1 ? " open" : ""}>`;
        html += `<summary>${SharedCharts.esc(log.name)} <span class="res-cfg__size">${this._size(log.size)}</span></summary>`;
        html += `<pre class="res-log"><code data-log="${index}"></code></pre>`;
        html += `</details>`;
      });
      html += `</section>`;
    }

    if (data.other.length) {
      html += `<section class="res-section"><h4 class="res-section__cap">Other files <span>${data.other.length}</span></h4><ul class="res-files">`;
      data.other.forEach((file) => {
        html += `<li><span>${SharedCharts.esc(file.name)}</span><span>${this._size(file.size)}</span></li>`;
      });
      html += `</ul></section>`;
    }

    if (!data.markdown.length && !data.images.length && !data.animations.length && !data.configs.length && !data.logs.length && !data.other.length) {
      html += `<div class="res-empty">This folder holds no files. Pick a subfolder on the left.</div>`;
    }

    return html;
  }

  _galleryHtml() {
    const groups = this.galleryData.groups;
    let total    = 0;
    let html     = "";

    groups.forEach((group) => {
      const items = this._applyFilter(group.images);
      if (!items.length) return;

      total += items.length;
      const label = group.rel === "" ? "/" : this._relLabel(group.rel);

      html += `<section class="res-section">`;
      html += `<h4 class="res-section__cap res-section__cap--link"><button type="button" data-rel="${SharedCharts.esc(group.rel)}" title="Open this folder">${SharedCharts.esc(label)}</button> <span>${items.length}</span></h4>`;
      html += `<div class="res-grid">${items.map((item) => this._figHtml(item, group.rel, item.kind)).join("")}</div>`;
      html += `</section>`;
    });

    if (!groups.length) return `<div class="res-empty">No plots found anywhere under this run.</div>`;
    if (!total)         return `<div class="res-empty">No plot matches the filter.</div>`;

    return `<p class="res-gallery__sum">${total} of ${this.galleryData.total} plots across the whole run.</p>` + html;
  }

  _compareHtml() {
    const items = this._applyFilter(this.compare);

    if (!this.compare.length) {
      return `<div class="res-empty">Nothing pinned for comparison yet. Hover any figure in the Folder or All plots view and press <code>+</code> to add it to this grid.</div>`;
    }
    if (!items.length) {
      return `<div class="res-empty">No pinned plot matches the filter.</div>`;
    }

    const tiles = items.map((item) =>
      `<figure class="res-fig res-fig--cmp" data-url="${item.url}" data-name="${SharedCharts.esc(item.name)}" data-rel="${SharedCharts.esc(item.rel)}">` +
      `<button type="button" class="res-pin is-on" data-url="${item.url}" title="Remove from compare">&minus;</button>` +
      `<img src="${item.url}" alt="${SharedCharts.esc(item.name)}" loading="lazy" />` +
      `<figcaption><span class="res-fig__dir">${SharedCharts.esc(item.rel === "" ? "/" : item.rel)}</span>${SharedCharts.esc(item.name)}</figcaption>` +
      `</figure>`
    ).join("");

    return (
      `<div class="res-compare__head">` +
      `<p class="res-gallery__sum">${this.compare.length} pinned plot${this.compare.length === 1 ? "" : "s"}, shown side by side.</p>` +
      `<button type="button" class="btn btn--mini" id="res-compare-clear">Clear all</button>` +
      `</div>` +
      `<div class="res-compare__grid" style="grid-template-columns: repeat(${this.columns}, 1fr)">${tiles}</div>`
    );
  }

  _figHtml(item, rel, kind) {
    const pinned = this._isPinned(item.url);
    return (
      `<figure class="res-fig${kind === "gif" ? " res-fig--gif" : ""}" data-url="${item.url}" data-name="${SharedCharts.esc(item.name)}" data-rel="${SharedCharts.esc(rel)}">` +
      `<button type="button" class="res-pin${pinned ? " is-on" : ""}" data-url="${item.url}" title="${pinned ? "Remove from compare" : "Add to compare"}">${pinned ? "&minus;" : "+"}</button>` +
      `<img src="${item.url}" alt="${SharedCharts.esc(item.name)}" loading="lazy" />` +
      `<figcaption>${SharedCharts.esc(item.name)}</figcaption>` +
      `</figure>`
    );
  }

  _sectionHtml(title, items, kind, rel, totalCount) {
    const figs  = items.map((item) => this._figHtml(item, rel, kind)).join("");
    const count = this.filter && items.length !== totalCount ? `${items.length} of ${totalCount}` : `${totalCount}`;

    return (
      `<section class="res-section">` +
      `<h4 class="res-section__cap">${SharedCharts.esc(title)} <span>${count}</span></h4>` +
      `<div class="res-grid${kind === "gif" ? " res-grid--gif" : ""}">${figs}</div>` +
      `</section>`
    );
  }

  _applyFilter(items) {
    if (!this.filter) return items;
    return items.filter((item) => item.name.toLowerCase().includes(this.filter));
  }

  _fillMarkdown(body) {
    const data = this.folderData;

    body.querySelectorAll(".res-md").forEach((el) => {
      const md = data.markdown[Number(el.dataset.md)];

      el.innerHTML = window.marked.parse(md.text);
      this._gridify(el, data.rel);

      el.querySelectorAll("img").forEach((img) => {
        const src = img.getAttribute("src") || "";
        if (!src.startsWith("/") && !src.startsWith("http") && !src.startsWith("data:")) {
          img.src = this._mediaUrl(data.abs, src);
        }
        img.loading = "lazy";
      });

      el.querySelectorAll("a").forEach((a) => {
        const href = a.getAttribute("href") || "";
        if (!href.startsWith("/") && !href.startsWith("http") && !href.startsWith("#")) {
          a.href = this._mediaUrl(data.abs, href);
        }
        a.target = "_blank";
        a.rel = "noopener";
      });
    });
  }

  _fillConfigs(body) {
    body.querySelectorAll("code[data-cfg]").forEach((code) => {
      const cfg = this.folderData.configs[Number(code.dataset.cfg)];
      code.textContent = cfg.kind === "json" ? this._prettyJson(cfg.text) : cfg.text;
    });
  }

  _fillLogs(body) {
    body.querySelectorAll("code[data-log]").forEach((code) => {
      code.textContent = this.folderData.logs[Number(code.dataset.log)].text;
    });
  }

  _collectFigures(body) {
    this.figures = [...body.querySelectorAll(".res-fig")].map((fig) => ({
      url  : fig.dataset.url,
      name : fig.dataset.name,
      rel  : fig.dataset.rel || "",
    }));
  }

  _bindBody(body) {
    body.querySelectorAll(".res-fig").forEach((fig, index) => {
      fig.addEventListener("click", () => this._openLightbox(index));
    });

    body.querySelectorAll(".res-pin").forEach((pin) => {
      pin.addEventListener("click", (ev) => {
        ev.stopPropagation();
        const fig = pin.closest(".res-fig");
        this._togglePin({ url: fig.dataset.url, name: fig.dataset.name, rel: fig.dataset.rel || "" });
      });
    });

    body.querySelectorAll(".res-section__cap--link button").forEach((btn) => {
      btn.addEventListener("click", () => this.selectFolder(btn.dataset.rel));
    });

    const clear = body.querySelector("#res-compare-clear");
    if (clear) clear.addEventListener("click", () => {
      this.compare = [];
      this._persistCompare();
      this._renderBody();
    });
  }

  _gridify(el, rel) {
    const isImgPara = (node) =>
      node && node.tagName === "P" && node.children.length === 1 && node.children[0].tagName === "IMG" && !node.textContent.trim();

    let node = el.firstElementChild;
    while (node) {
      if (!isImgPara(node)) {
        node = node.nextElementSibling;
        continue;
      }

      const run = [node];
      let next = node.nextElementSibling;
      while (isImgPara(next)) {
        run.push(next);
        next = next.nextElementSibling;
      }

      const grid = document.createElement("div");
      grid.className = "res-grid res-grid--md";
      node.before(grid);

      run.forEach((para) => {
        const img   = para.children[0];
        const src   = img.getAttribute("src") || "";
        const isGif = src.toLowerCase().endsWith(".gif");
        const name  = img.alt || src.split("/").pop();
        const url   = src.startsWith("/") || src.startsWith("http") || src.startsWith("data:") ? src : this._mediaUrl(this.folderData.abs, src);

        const fig = document.createElement("figure");
        fig.className   = "res-fig" + (isGif ? " res-fig--gif" : "");
        fig.dataset.url  = url;
        fig.dataset.name = name;
        fig.dataset.rel  = rel;

        const pinned = this._isPinned(url);
        const pin    = document.createElement("button");
        pin.type        = "button";
        pin.className   = "res-pin" + (pinned ? " is-on" : "");
        pin.dataset.url = url;
        pin.title       = pinned ? "Remove from compare" : "Add to compare";
        pin.innerHTML   = pinned ? "&minus;" : "+";

        const cap = document.createElement("figcaption");
        cap.textContent = name;

        fig.append(pin, img, cap);
        grid.appendChild(fig);
        para.remove();
      });

      node = grid.nextElementSibling;
    }
  }

  _isPinned(url) {
    return this.compare.some((item) => item.url === url);
  }

  _togglePin(item) {
    if (this._isPinned(item.url)) this.compare = this.compare.filter((it) => it.url !== item.url);
    else                          this.compare = [...this.compare, item];

    this._persistCompare();

    const count = this.detailEl.querySelector("#res-compare-count");
    if (count) count.textContent = this.compare.length;

    if (this.view === "compare") {
      this._renderBody();
      return;
    }

    this.detailEl.querySelectorAll(`.res-pin[data-url="${CSS.escape(item.url)}"]`).forEach((pin) => {
      const pinned = this._isPinned(item.url);
      pin.classList.toggle("is-on", pinned);
      pin.innerHTML = pinned ? "&minus;" : "+";
      pin.title     = pinned ? "Remove from compare" : "Add to compare";
    });
  }

  _loadCompare() {
    try {
      return JSON.parse(localStorage.getItem(`results-compare:${this.root.root}`) || "[]");
    } catch (e) {
      return [];
    }
  }

  _persistCompare() {
    localStorage.setItem(`results-compare:${this.root.root}`, JSON.stringify(this.compare));
  }

  _decodeRelative(relative) {
    return /%(?![0-9A-Fa-f]{2})/.test(relative) ? relative : decodeURIComponent(relative);
  }

  _mediaUrl(folderAbs, relative) {
    return "/resultsmedia?root=" + encodeURIComponent(this.root.root) + "&path=" + encodeURIComponent(folderAbs + "/" + this._decodeRelative(relative));
  }

  _prettyJson(text) {
    try {
      return JSON.stringify(JSON.parse(text), null, 2);
    } catch (e) {
      return text;
    }
  }

  _recents() {
    try {
      return JSON.parse(localStorage.getItem("results-recents") || "[]");
    } catch (e) {
      return [];
    }
  }

  _remember(path) {
    const recents = [path, ...this._recents().filter((p) => p !== path)].slice(0, 8);
    localStorage.setItem("results-recents", JSON.stringify(recents));
  }

  _size(bytes) {
    if (bytes >= 1073741824) return (bytes / 1073741824).toFixed(1) + " GB";
    if (bytes >= 1048576)    return (bytes / 1048576).toFixed(1) + " MB";
    if (bytes >= 1024)       return (bytes / 1024).toFixed(1) + " KB";
    return bytes + " B";
  }

  _openLightbox(index) {
    this.lightboxAt = index;
    this._showLightbox();
    this.lightbox.hidden = false;
  }

  _stepLightbox(step) {
    if (!this.figures.length) return;
    this.lightboxAt = (this.lightboxAt + step + this.figures.length) % this.figures.length;
    this._showLightbox();
  }

  _showLightbox() {
    const fig = this.figures[this.lightboxAt];
    if (!fig) return;

    this.lightboxImg.src         = fig.url;
    this.lightboxCap.textContent = fig.rel && fig.rel !== "" ? `${fig.rel} / ${fig.name}` : fig.name;

    this.lightboxCount.textContent = `${this.lightboxAt + 1} / ${this.figures.length}`;
    this.lightboxPrev.hidden       = this.figures.length < 2;
    this.lightboxNext.hidden       = this.figures.length < 2;
    this.lightboxCount.hidden      = this.figures.length < 2;
  }

  _closeLightbox() {
    if (this.lightbox.hidden) return;
    this.lightbox.hidden = true;
    this.lightboxImg.src = "";
  }

}

window.ResultsView = ResultsView;
