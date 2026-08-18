"use strict";

class EquationView {
  constructor(tabsEl, gridEl) {
    this.tabsEl   = tabsEl;
    this.gridEl   = gridEl;
    this.groups   = [];
    this.active   = 0;
    this.rendered = new Map();
  }

  async load() {
    const data  = await Api.get("/api/equations");
    this.groups = data.groups || [];
    this._renderTabs();
    this._select(0);
  }

  _renderTabs() {
    this.tabsEl.innerHTML = "";
    this.groups.forEach((group, i) => {
      const tab = document.createElement("button");
      tab.className = "eq-tab" + (i === 0 ? " is-active" : "");
      tab.innerHTML = `${SharedCharts.esc(group.group)}<span class="eq-tab__count">${group.items.length}</span>`;
      tab.addEventListener("click", () => this._select(i));
      this.tabsEl.appendChild(tab);
    });
  }

  _select(index) {
    this.active = index;
    [...this.tabsEl.children].forEach((t, i) => t.classList.toggle("is-active", i === index));
    this._renderGroup(index);
  }

  _renderGroup(index) {
    const group = this.groups[index];
    if (!group) return;

    this.gridEl.innerHTML = "";

    const blurb = document.createElement("p");
    blurb.className   = "eq-blurb";
    blurb.textContent = group.blurb || "";
    this.gridEl.appendChild(blurb);

    let cards = this.rendered.get(index);
    if (!cards) {
      cards = group.items.map((item, i) => this._buildCard(item, i));
      this.rendered.set(index, cards);
    }

    const grid = document.createElement("div");
    grid.className = "eq-cards";
    cards.forEach((c) => grid.appendChild(c));
    this.gridEl.appendChild(grid);

    window.revealScan();
  }

  _buildCard(item, i) {
    const card = document.createElement("div");
    card.className = "eq-card reveal";
    card.style.transitionDelay = `${Math.min(i * 0.04, 0.4)}s`;

    const step = String(i + 1).padStart(2, "0");

    card.appendChild(this._buildFace(item, step, "eq-card__base", false));
    card.appendChild(this._buildFace(item, step, "eq-card__zoom", true));

    return card;
  }

  _buildFace(item, step, className, detailed) {
    const face     = document.createElement("div");
    face.className = className;

    const head       = document.createElement("div");
    head.className   = "eq-card__head";
    const badge      = document.createElement("span");
    badge.className   = "eq-card__step";
    badge.textContent = step;
    const title       = document.createElement("h3");
    title.className   = "eq-card__title";
    title.textContent = item.title;
    head.appendChild(badge);
    head.appendChild(title);

    const tex       = document.createElement("div");
    tex.className   = "eq-card__tex";
    this._typeset(tex, item.tex, true);

    const note       = document.createElement("p");
    note.className   = "eq-card__note";
    note.textContent = item.note;

    face.appendChild(head);
    face.appendChild(tex);
    face.appendChild(note);

    if (detailed && item.vars && item.vars.length) {
      const vars     = document.createElement("div");
      vars.className = "eq-card__vars";

      item.vars.forEach((v) => {
        const row     = document.createElement("div");
        row.className = "eq-var";
        const sym     = document.createElement("span");
        sym.className = "eq-var__sym";
        this._typeset(sym, v.sym, false);
        const desc       = document.createElement("span");
        desc.className   = "eq-var__desc";
        desc.textContent = v.desc;
        row.appendChild(sym);
        row.appendChild(desc);
        vars.appendChild(row);
      });

      face.appendChild(vars);
    }

    return face;
  }

  _stack(tex) {
    if (tex.indexOf("\\qquad") < 0) return tex;
    const parts = tex.split(/,?\s*\\qquad\s*/).filter((p) => p.trim().length);
    if (parts.length < 2) return tex;
    return "\\begin{gathered}" + parts.join(" \\\\[0.55em] ") + "\\end{gathered}";
  }

  _typeset(el, tex, display) {
    const source = display ? this._stack(tex) : tex;

    MathJaxTypesetter.render(el, tex, display, source).then((node) => {
      if (node && display) this._fit(el);
    });
  }

  _fit(el) {
    requestAnimationFrame(() => {
      if (el.scrollWidth <= el.clientWidth + 1) return;
      const card = el.closest(".eq-card");
      if (card) card.classList.add("eq-card--wide");
      requestAnimationFrame(() => {
        if (el.scrollWidth <= el.clientWidth + 1) return;
        const svg = el.querySelector("svg");
        if (svg) {
          svg.style.maxWidth = "100%";
          svg.style.height = "auto";
        }
      });
    });
  }

}

window.EquationView = EquationView;
