"use strict";

class ConfigBrowser {
  constructor(listEl, detailEl, searchEl) {
    this.listEl   = listEl;
    this.detailEl = detailEl;
    this.searchEl = searchEl;
    this.wrapEl   = document.getElementById("config-search-wrap");
    this.metaEl   = document.getElementById("config-meta");

    this.groups   = [];
    this.flat     = [];
    this.activeId = null;
    this.query    = "";
    this.open     = new Set();

    this._bindSearch();
    this._bindKeys();
  }

  async load() {
    const data = await Api.get("/api/configs");

    if (data.error) {
      this.groups = [];
      this.flat   = [];
      this.listEl.innerHTML = `<div class="clist__empty">Could not load configurations: ${SharedCharts.esc(String(data.error))}</div>`;
      return;
    }

    this.groups = data.groups || [];
    this.flat   = [];

    this.groups.forEach((g) => {
      g.classes.forEach((c) => {
        this.flat.push({ id: `${c.module || g.module}::${c.name}`, group: g.title, groupDesc: g.desc, module: c.module || g.module, name: c.name, desc: c.desc, fields: c.fields });
      });
    });

    this._restoreState();
    this._renderList();
    this._renderMeta();

    const remembered = this.flat.find((c) => c.id === this.activeId);
    const first      = remembered || this.flat[0];
    if (first) this._select(first.id, false);
  }

  _bindSearch() {
    this.searchEl.addEventListener("input", () => {
      this.query = this.searchEl.value.trim().toLowerCase();
      if (this.wrapEl) this.wrapEl.classList.toggle("is-typing", this.searchEl.value.length > 0);
      this._renderList();
      this._renderMeta();
      this._reselect();
    });

    this.searchEl.addEventListener("focus", () => { if (this.wrapEl) this.wrapEl.classList.add("is-typing"); });
    this.searchEl.addEventListener("blur",  () => { if (this.wrapEl) this.wrapEl.classList.toggle("is-typing", this.searchEl.value.length > 0); });
  }

  _bindKeys() {
    document.addEventListener("keydown", (e) => {
      if (e.key !== "/" || e.metaKey || e.ctrlKey || e.altKey) return;
      if (!this._pageActive()) return;
      const t = e.target;
      if (t && (t.tagName === "INPUT" || t.tagName === "TEXTAREA" || t.tagName === "SELECT" || t.isContentEditable)) return;
      e.preventDefault();
      this.searchEl.focus();
      this.searchEl.select();
    });

    this.searchEl.addEventListener("keydown", (e) => {
      if (e.key === "Escape") {
        this.searchEl.value = "";
        this.searchEl.dispatchEvent(new Event("input"));
        this.searchEl.blur();
        return;
      }
      if (e.key === "ArrowDown" || e.key === "ArrowUp") {
        e.preventDefault();
        this._step(e.key === "ArrowDown" ? 1 : -1);
      }
      if (e.key === "Enter") {
        const visible = this._visibleClasses();
        if (visible.length) this._select(visible[0].id);
      }
    });
  }

  _pageActive() {
    const page = document.querySelector('.page[data-page="configuration"]');
    return page && page.classList.contains("is-active");
  }

  _step(dir) {
    const visible = this._visibleClasses();
    if (!visible.length) return;
    const idx  = visible.findIndex((c) => c.id === this.activeId);
    const next = visible[Math.min(visible.length - 1, Math.max(0, idx + dir))];
    if (next) this._select(next.id);
  }

  _restoreState() {
    let openTitles = null;
    let activeId   = null;
    try {
      openTitles = JSON.parse(localStorage.getItem("dlr.config.open") || "null");
      activeId   = localStorage.getItem("dlr.config.active");
    } catch (e) {
      openTitles = null;
    }

    const titles = this.groups.map((g) => g.title);
    this.open    = new Set(Array.isArray(openTitles) ? openTitles.filter((t) => titles.includes(t)) : []);
    if (activeId && this.flat.some((c) => c.id === activeId)) this.activeId = activeId;
  }

  _persistState() {
    try {
      localStorage.setItem("dlr.config.open", JSON.stringify([...this.open]));
      if (this.activeId) localStorage.setItem("dlr.config.active", this.activeId);
    } catch (e) {}
  }

  _matchText(s) {
    return this.query && String(s || "").toLowerCase().includes(this.query);
  }

  _matchField(f) {
    if (!this.query) return true;
    return this._matchText(f.name) || this._matchText(f.type) || this._matchText(f.default) || this._matchText(f.desc);
  }

  _classNameMatch(c) {
    return this._matchText(c.name) || this._matchText(c.group) || this._matchText(c.module) || this._matchText(c.desc);
  }

  _classMatch(c) {
    if (!this.query) return true;
    return this._classNameMatch(c) || c.fields.some((f) => this._matchField(f));
  }

  _visibleClasses() {
    return this.flat.filter((c) => this._classMatch(c));
  }

  _visibleFields(c) {
    if (!this.query || this._classNameMatch(c)) return c.fields;
    return c.fields.filter((f) => this._matchField(f));
  }

  _renderList() {
    this.listEl.innerHTML = "";
    const visible = this._visibleClasses();

    if (!visible.length) {
      this.listEl.innerHTML = `<div class="clist__empty">Nothing matches &ldquo;${SharedCharts.esc(this.searchEl.value.trim())}&rdquo;.</div>`;
      return;
    }

    this.groups.forEach((g) => {
      const classes = visible.filter((c) => c.group === g.title);
      if (!classes.length) return;

      const isOpen = this.query ? true : this.open.has(g.title);
      const grp    = document.createElement("div");
      grp.className = "cgroup" + (isOpen ? " is-open" : "");

      const head = document.createElement("button");
      head.className = "cgroup__head";
      head.setAttribute("aria-expanded", String(isOpen));
      head.innerHTML = `<span class="cgroup__chev" aria-hidden="true"></span><span class="cgroup__title">${SharedCharts.esc(g.title)}</span><span class="cgroup__count">${classes.length}</span>`;
      head.addEventListener("click", () => this._toggleGroup(g.title));
      grp.appendChild(head);

      const items = document.createElement("div");
      items.className = "cgroup__items";
      const inner    = document.createElement("div");
      inner.className = "cgroup__inner";

      classes.forEach((c) => {
        const count = this._visibleFields(c).length;
        const item  = document.createElement("button");
        item.className  = "clist__item";
        item.dataset.id = c.id;
        item.innerHTML  = `<span class="clist__name">${this._mark(c.name)}</span><span class="clist__count">${count}</span>`;
        item.addEventListener("click", () => this._select(c.id));
        inner.appendChild(item);
      });

      items.appendChild(inner);
      grp.appendChild(items);
      this.listEl.appendChild(grp);
    });

    this._markActive();
  }

  _renderMeta() {
    if (!this.metaEl) return;

    if (!this.query) {
      const fields = this.flat.reduce((n, c) => n + c.fields.length, 0);
      this.metaEl.textContent = `${this.flat.length} configs · ${fields} fields · ${this.groups.length} modules`;
      this.metaEl.classList.remove("is-match");
      return;
    }

    const visible = this._visibleClasses();
    const fields  = visible.reduce((n, c) => n + this._visibleFields(c).length, 0);
    this.metaEl.textContent = visible.length ? `${fields} field${fields === 1 ? "" : "s"} in ${visible.length} config${visible.length === 1 ? "" : "s"}` : "no matches";
    this.metaEl.classList.add("is-match");
  }

  _toggleGroup(title) {
    if (this.query) return;
    if (this.open.has(title)) this.open.delete(title);
    else this.open.add(title);
    this._persistState();
    this._renderList();
  }

  _reselect() {
    const visible = this._visibleClasses();

    if (!visible.length) {
      this.detailEl.innerHTML = `<div class="cdetail__empty"><p>No config or field matches &ldquo;${SharedCharts.esc(this.searchEl.value.trim())}&rdquo;.</p><button class="btn btn--mini" id="config-clear-search">Clear search</button></div>`;
      const clear = document.getElementById("config-clear-search");
      if (clear) clear.addEventListener("click", () => {
        this.searchEl.value = "";
        this.searchEl.dispatchEvent(new Event("input"));
      });
      this.activeId = null;
      return;
    }

    if (!visible.find((c) => c.id === this.activeId)) this._select(visible[0].id, false);
    else this._renderDetail();
  }

  _select(id, expand = true) {
    this.activeId = id;
    const cls = this.flat.find((c) => c.id === id);
    if (expand && cls && !this.query && !this.open.has(cls.group)) {
      this.open.add(cls.group);
      this._renderList();
    }
    this._persistState();
    this._markActive();
    this._renderDetail();
  }

  _markActive() {
    this.listEl.querySelectorAll(".clist__item").forEach((b) => b.classList.toggle("is-active", b.dataset.id === this.activeId));
  }

  _kind(d) {
    const v = String(d == null ? "" : d);
    if (v === "required") return "required";
    if (v === "None") return "none";
    if (v === "True" || v === "False") return "bool";
    if (/^-?(\d|\.\d)/.test(v)) return "num";
    if (/^["']/.test(v)) return "str";
    return "expr";
  }

  _row(f) {
    const kind = this._kind(f.default);
    const cell = kind === "required" ? `<span class="ctable__required">required</span>` : `<code class="ctable__default is-${kind}">${this._mark(f.default)}</code>`;
    const desc = f.desc ? `<span class="ctable__fdesc">${this._mark(f.desc)}</span>` : "";
    return (
      `<div class="ctable__row">` +
      `<span class="ctable__field"><span class="ctable__fname">${this._mark(f.name)}</span>${desc}</span>` +
      `<code class="ctable__type">${this._mark(f.type)}</code>` +
      cell +
      `</div>`
    );
  }

  _groupLabel(fields) {
    if (fields.length < 2) return null;
    const lists  = fields.map((f) => String(f.name).split("_"));
    const common = lists[0].filter((t) => lists.every((l) => l.includes(t)));
    return common.length ? common.join(" ") : null;
  }

  _renderDetail() {
    const cls = this.flat.find((c) => c.id === this.activeId);
    if (!cls) return;

    const fields = this._visibleFields(cls);
    const runs   = [];

    fields.forEach((f) => {
      const g    = f.group || 0;
      const last = runs[runs.length - 1];
      if (last && last.g === g) last.fields.push(f);
      else runs.push({ g, fields: [f] });
    });

    let rows = "";
    if (runs.length > 1) {
      runs.forEach((run) => {
        const tag = this._groupLabel(run.fields);
        rows +=
          `<div class="ctable__group is-c${run.g % 6}">` +
          (tag ? `<div class="ctable__gtag">${SharedCharts.esc(tag)}</div>` : "") +
          run.fields.map((f) => this._row(f)).join("") +
          `</div>`;
      });
    } else {
      rows = fields.map((f) => this._row(f)).join("");
    }

    this.detailEl.innerHTML =
      `<div class="cdetail__head">` +
      `<div><span class="cdetail__module">${SharedCharts.esc(cls.group)}</span>` +
      (cls.groupDesc ? `<p class="cdetail__sectiondesc">${SharedCharts.esc(cls.groupDesc)}</p>` : "") +
      `<h3 class="cdetail__name">${SharedCharts.esc(cls.name)}</h3>` +
      `<div class="cdetail__path">configuration/${SharedCharts.esc(cls.module)}.py</div>` +
      (cls.desc ? `<p class="cdetail__desc">${this._mark(cls.desc)}</p>` : "") +
      `</div>` +
      `<span class="cdetail__count">${this.query && fields.length !== cls.fields.length ? `${fields.length} of ${cls.fields.length} fields` : `${fields.length} field${fields.length === 1 ? "" : "s"}`}</span>` +
      `</div>` +
      `<div class="ctable">` +
      `<div class="ctable__head"><span>Field</span><span>Type</span><span>Default</span></div>` +
      rows +
      `</div>`;

    this.detailEl.classList.remove("is-swap");
    void this.detailEl.offsetWidth;
    this.detailEl.classList.add("is-swap");
  }

  _mark(text) {
    const raw  = String(text == null ? "" : text);
    const safe = SharedCharts.esc(raw);
    if (!this.query) return safe;

    const idx = raw.toLowerCase().indexOf(this.query);
    if (idx < 0) return safe;

    const end = idx + this.query.length;
    return SharedCharts.esc(raw.slice(0, idx)) + "<mark>" + SharedCharts.esc(raw.slice(idx, end)) + "</mark>" + SharedCharts.esc(raw.slice(end));
  }
}

window.ConfigBrowser = ConfigBrowser;
