"use strict";

class FigureScanner {
  static SELECTOR    = "canvas, img, svg";
  static MIN_WIDTH   = 56;
  static MIN_HEIGHT  = 40;
  static HEADINGS    = ".cube-panel-title, .fl-card__head b, .sc-row__title, .res-section__cap, .ms-card__head h3, h3, h4";
  static CARDS       = ".ms-card, .fl-card, .nrm-chart, .sc-row, .res-section, .cube-panel, .cube-view, article, section";
  static CARD_CAP    = 32;
  static LABEL_CAP   = 48;
  static SUFFIX      = /\.(png|jpe?g|gif|svg|webp)$/i;

  constructor(page) {
    this.page = page;
  }

  static text(node) {
    const own = [...node.childNodes].filter((child) => child.nodeType === 3).map((child) => child.textContent).join(" ").trim();
    return own || node.textContent.trim();
  }

  static skip(el) {
    if (el.closest("[data-nofig]")) return true;
    if (el.tagName === "CANVAS" && (!el.width || !el.height)) return true;
    if (el.tagName === "IMG" && !el.naturalWidth) return true;

    const rect = el.getBoundingClientRect();
    return rect.width < FigureScanner.MIN_WIDTH || rect.height < FigureScanner.MIN_HEIGHT;
  }

  _named(el) {
    const marked = el.closest("[data-fig]");
    return marked ? marked.dataset.fig.trim() : "";
  }

  _label(el) {
    const named = el.getAttribute("alt") || el.getAttribute("aria-label") || "";
    if (named.trim()) return named;

    const figure  = el.closest("figure");
    const caption = figure ? figure.querySelector("figcaption") : null;
    if (caption && FigureScanner.text(caption)) return FigureScanner.text(caption);

    return this._heading(el) || el.id || el.tagName.toLowerCase();
  }

  _heading(el) {
    let node = el;

    while (node && node !== this.page) {
      let sibling = node.previousElementSibling;

      while (sibling) {
        const head = sibling.matches(FigureScanner.HEADINGS) ? sibling : sibling.querySelector(FigureScanner.HEADINGS);
        if (head && FigureScanner.text(head)) return FigureScanner.text(head);
        sibling = sibling.previousElementSibling;
      }

      node = node.parentElement;
    }

    return "";
  }

  _card(el) {
    const card = el.closest(FigureScanner.CARDS);
    if (!card) return "";

    const head = card.querySelector(FigureScanner.HEADINGS);
    return head ? FigureScanner.text(head) : "";
  }

  scan() {
    const taken = new Map();
    const found = [];

    this.page.querySelectorAll(FigureScanner.SELECTOR).forEach((el) => {
      if (FigureScanner.skip(el)) return;

      const named = this._named(el);
      const card  = this._card(el).trim();
      const label = named || this._label(el).trim();
      const short = FigureExport.slug(label.replace(FigureScanner.SUFFIX, ""), FigureScanner.LABEL_CAP).toLowerCase();
      const group = named ? "" : FigureExport.slug(card, FigureScanner.CARD_CAP).toLowerCase();
      const stem  = (short.includes(group) ? [short] : [group, short]).filter(Boolean).join("_") || "figure";
      const seen  = (taken.get(stem) || 0) + 1;
      const rect  = el.getBoundingClientRect();

      taken.set(stem, seen);
      found.push({
        el,
        card,
        label,
        stem   : seen > 1 ? `${stem}_${seen}` : stem,
        width  : Math.round(rect.width),
        height : Math.round(rect.height),
      });
    });

    return found;
  }
}


class FigureHover {
  static HIDE_MS = 140;
  static GAP     = 6;
  static SIZE    = 26;
  static EDGE    = 4;
  static MARK    = "is-fighover";
  static GLYPH   = "&darr;";

  constructor(onSave) {
    this.onSave    = onSave;
    this.page      = null;
    this.target    = null;
    this.timer     = null;
    this.suspended = false;

    this.button = document.createElement("button");
    this.button.type      = "button";
    this.button.className = "figsave";
    this.button.title     = "Save this figure as PNG";
    this.button.innerHTML = FigureHover.GLYPH;
    this.button.setAttribute("aria-label", "Save this figure as PNG");
    this.button.hidden = true;
    document.body.appendChild(this.button);

    this.button.addEventListener("pointerenter", () => this._hold());
    this.button.addEventListener("pointerleave", () => this._schedule());
    this.button.addEventListener("click", () => {
      if (this.target) this.onSave(this.target);
    });

    this._onOver  = (ev) => this._over(ev);
    this._onOut   = (ev) => this._out(ev);
    this._onShift = () => this.place();

    window.addEventListener("scroll", this._onShift, true);
    window.addEventListener("resize", this._onShift);
  }

  attach(page) {
    this.detach();
    this.page = page;
    page.addEventListener("pointerover", this._onOver);
    page.addEventListener("pointerout", this._onOut);
  }

  detach() {
    if (this.page) {
      this.page.removeEventListener("pointerover", this._onOver);
      this.page.removeEventListener("pointerout", this._onOut);
    }

    this.page = null;
    this.hide();
  }

  suspend(state) {
    this.suspended = state;
    if (state) this.hide();
  }

  _over(ev) {
    if (this.suspended || !ev.target.closest) return;

    const el = ev.target.closest(FigureScanner.SELECTOR);
    if (!el || FigureScanner.skip(el)) return;

    this._hold();
    this._untarget();

    this.target = el;
    el.classList.add(FigureHover.MARK);
    this.button.hidden = false;
    this.place();
  }

  _untarget() {
    if (this.target) this.target.classList.remove(FigureHover.MARK);
    this.target = null;
  }

  _out(ev) {
    const to = ev.relatedTarget;
    if (to && (to === this.button || this.button.contains(to))) return;
    if (to && this.target && this.target.contains(to)) return;
    this._schedule();
  }

  _hold() {
    if (this.timer !== null) clearTimeout(this.timer);
    this.timer = null;
  }

  _schedule() {
    this._hold();
    this.timer = setTimeout(() => this.hide(), FigureHover.HIDE_MS);
  }

  place() {
    if (this.button.hidden || !this.target) return;

    const rect = this.target.getBoundingClientRect();
    if (!rect.width || rect.bottom < 0 || rect.top > window.innerHeight) {
      this.hide();
      return;
    }

    const size    = FigureHover.SIZE;
    const gap     = FigureHover.GAP;
    const beside  = rect.right + gap;
    const outside = beside + size <= window.innerWidth - FigureHover.EDGE;
    const top     = outside ? rect.top : rect.top + gap;

    this.button.style.left = `${outside ? beside : rect.right - size - gap}px`;
    this.button.style.top  = `${Math.min(Math.max(FigureHover.EDGE, top), Math.max(FigureHover.EDGE, rect.bottom - size))}px`;
  }

  hide() {
    this._hold();
    this.button.hidden = true;
    this._untarget();
  }
}


class FigureDock {
  static RESCAN_MS = 260;
  static TAG_CAP   = 48;
  static MARK      = "is-figmark";

  constructor() {
    this.route     = "";
    this.page      = null;
    this.tagFor    = null;
    this.figures   = [];
    this.picked    = new Set();
    this.timer     = null;
    this.observer  = null;
    this.marked    = null;

    this.dock = document.createElement("div");
    this.dock.className = "figdock";
    this.dock.hidden    = true;
    this.dock.innerHTML = `
      <button type="button" class="figdock__all" title="Save every figure on this view as one ZIP">
        <span class="figdock__glyph">&darr;</span><span class="figdock__label">Save figures</span><span class="figdock__count"></span>
      </button>
      <button type="button" class="figdock__list" title="Pick which figures to save" aria-label="Pick which figures to save">&hellip;</button>`;

    this.panel = document.createElement("section");
    this.panel.className = "figpanel";
    this.panel.hidden    = true;
    this.panel.setAttribute("aria-label", "Figures on this view");
    this.panel.innerHTML = `
      <header class="figpanel__head">
        <h3 class="cube-panel-title">Figures on this view</h3>
        <span class="figpanel__tag"></span>
        <button type="button" class="figpanel__close" aria-label="Close">&times;</button>
      </header>
      <div class="figpanel__tools">
        <button type="button" class="btn btn--mini figpanel__pick" data-pick="all">Select all</button>
        <button type="button" class="btn btn--mini figpanel__pick" data-pick="none">Select none</button>
        <span class="figpanel__sum"></span>
        <button type="button" class="btn btn--mini figpanel__zip">Save selected</button>
      </div>
      <ul class="figpanel__list"></ul>`;

    document.body.appendChild(this.dock);
    document.body.appendChild(this.panel);

    this.refs = {
      all   : this.dock.querySelector(".figdock__all"),
      list  : this.dock.querySelector(".figdock__list"),
      count : this.dock.querySelector(".figdock__count"),
      tag   : this.panel.querySelector(".figpanel__tag"),
      sum   : this.panel.querySelector(".figpanel__sum"),
      zip   : this.panel.querySelector(".figpanel__zip"),
      rows  : this.panel.querySelector(".figpanel__list"),
    };

    this.hover = new FigureHover((el) => this._saveOne(el));

    this.refs.all.addEventListener("click", () => this._saveAll());
    this.refs.list.addEventListener("click", () => this._togglePanel());
    this.refs.zip.addEventListener("click", () => this._savePicked());
    this.panel.querySelector(".figpanel__close").addEventListener("click", () => this._closePanel());
    this.panel.querySelectorAll(".figpanel__pick").forEach((btn) => {
      btn.addEventListener("click", () => this._pickAll(btn.dataset.pick === "all"));
    });

    document.addEventListener("keydown", (ev) => {
      if (ev.key === "Escape" && !this.panel.hidden) this._closePanel();
    });
  }

  mount(route, page, tagFor) {
    if (this.route === route && this.page === page) {
      this.refresh();
      return;
    }

    this.unmount();
    this.route  = route;
    this.page   = page;
    this.tagFor = tagFor;

    this.hover.attach(page);
    this.observer = new MutationObserver(() => this._schedule());
    this.observer.observe(page, { childList: true, subtree: true, attributes: true, attributeFilter: ["hidden", "src", "data-fig"] });

    this.refresh();
  }

  unmount() {
    if (this.observer) this.observer.disconnect();
    if (this.timer !== null) clearTimeout(this.timer);

    this.observer = null;
    this.timer    = null;
    this.route    = "";
    this.page     = null;
    this.tagFor   = null;
    this.figures  = [];
    this.picked.clear();

    this._mark(null);
    this._closePanel();
    this.hover.detach();
    this.dock.hidden = true;
  }

  _schedule() {
    if (this.timer !== null) clearTimeout(this.timer);
    this.timer = setTimeout(() => this.refresh(), FigureDock.RESCAN_MS);
  }

  _tag() {
    const tag = this.tagFor ? this.tagFor() : "";
    return FigureExport.slug(tag || "", FigureDock.TAG_CAP);
  }

  _name(figure, tag) {
    return `${[this.route, tag, figure.stem].filter(Boolean).join("_")}.png`;
  }

  refresh() {
    if (!this.page) return;

    const tag = this._tag();
    this.figures = new FigureScanner(this.page).scan().map((figure) => ({ ...figure, name: this._name(figure, tag) }));

    const names = new Set(this.figures.map((figure) => figure.name));
    [...this.picked].forEach((name) => {
      if (!names.has(name)) this.picked.delete(name);
    });

    this.dock.hidden = this.figures.length === 0;
    this.refs.count.textContent = this.figures.length ? String(this.figures.length) : "";
    this.refs.tag.textContent = [this.route, tag].filter(Boolean).join(" · ");

    if (!this.figures.length) this._closePanel();
    if (!this.panel.hidden) this._renderRows();
  }

  _renderRows() {
    const groups = [];

    this.figures.forEach((figure) => {
      const head = figure.card || "";
      const last = groups[groups.length - 1];
      if (last && last.head === head) last.rows.push(figure);
      else groups.push({ head, rows: [figure] });
    });

    this.refs.rows.innerHTML = "";
    groups.forEach((group) => {
      if (group.head) {
        const head = document.createElement("li");
        head.className   = "figpanel__group";
        head.textContent = group.head;
        this.refs.rows.appendChild(head);
      }
      group.rows.forEach((figure) => this.refs.rows.appendChild(this._row(figure)));
    });

    this._renderSummary();
  }

  _row(figure) {
    const row = document.createElement("li");
    row.className = "figrow";

    const box = document.createElement("input");
    box.type    = "checkbox";
    box.checked = this.picked.has(figure.name);
    box.addEventListener("change", () => {
      if (box.checked) this.picked.add(figure.name);
      else this.picked.delete(figure.name);
      this._renderSummary();
    });

    const label = document.createElement("button");
    label.type      = "button";
    label.className = "figrow__label";
    label.title     = figure.name;
    label.textContent = figure.label || figure.stem;
    label.addEventListener("click", () => this._reveal(figure));
    label.addEventListener("pointerenter", () => this._mark(figure.el));
    label.addEventListener("pointerleave", () => this._mark(null));

    const size = document.createElement("span");
    size.className   = "figrow__size";
    size.textContent = `${figure.width}×${figure.height}`;

    const save = document.createElement("button");
    save.type      = "button";
    save.className = "btn btn--mini";
    save.textContent = "PNG";
    save.addEventListener("click", () => this._saveFigure(figure));

    row.append(box, label, size, save);
    return row;
  }

  _renderSummary() {
    const count = this.picked.size;
    this.refs.sum.textContent = `${count} of ${this.figures.length} selected`;
    this.refs.zip.disabled = count === 0;
  }

  _pickAll(state) {
    this.picked.clear();
    if (state) this.figures.forEach((figure) => this.picked.add(figure.name));

    this.refs.rows.querySelectorAll("input[type=checkbox]").forEach((box) => { box.checked = state; });
    this._renderSummary();
  }

  _mark(el) {
    if (this.marked) this.marked.classList.remove(FigureDock.MARK);
    this.marked = el;
    if (el) el.classList.add(FigureDock.MARK);
  }

  _reveal(figure) {
    figure.el.scrollIntoView({ block: "center", behavior: window.REDUCED_MOTION ? "auto" : "smooth" });
    this._mark(figure.el);
    setTimeout(() => this._mark(null), 1400);
  }

  _togglePanel() {
    if (this.panel.hidden) this._openPanel();
    else this._closePanel();
  }

  _openPanel() {
    this.refresh();
    this.panel.hidden = false;
    this.hover.suspend(true);
    this._renderRows();
  }

  _closePanel() {
    this.panel.hidden = true;
    this.hover.suspend(false);
    this._mark(null);
  }

  async _saveOne(el) {
    const figure = this.figures.find((entry) => entry.el === el);
    if (figure) {
      await this._saveFigure(figure);
      return;
    }

    this.refresh();
    const rescanned = this.figures.find((entry) => entry.el === el);
    if (rescanned) await this._saveFigure(rescanned);
    else Toast.show("That figure is not ready to save yet.", "warn");
  }

  async _saveFigure(figure) {
    const done = await FigureExport.saveElement(figure.el, figure.name).catch(() => false);
    if (done) Toast.show(`Saved ${figure.name}`, "ok");
    else Toast.show(`Could not read ${figure.label || figure.stem}.`, "error");
  }

  _zipName() {
    const tag = this._tag();
    return `${[this.route, tag, "figures"].filter(Boolean).join("_")}.zip`;
  }

  async _saveBatch(jobs) {
    if (!jobs.length) {
      Toast.show("No figure on this view to save.", "warn");
      return;
    }

    Toast.show(`Packing ${jobs.length} figure${jobs.length === 1 ? "" : "s"}…`);
    const saved = await FigureExport.saveZip(this._zipName(), jobs);

    if (saved) Toast.show(`Saved ${saved} figure${saved === 1 ? "" : "s"} to ${this._zipName()}`, "ok");
    else Toast.show("None of the figures could be read.", "error");
  }

  _saveAll() {
    this.refresh();
    this._saveBatch(this.figures);
  }

  _savePicked() {
    this._saveBatch(this.figures.filter((figure) => this.picked.has(figure.name)));
  }
}


window.FigureScanner = FigureScanner;
window.FigureHover   = FigureHover;
window.FigureDock    = FigureDock;
