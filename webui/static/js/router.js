"use strict";

class Router {
  constructor(onChange) {
    this.onChange = onChange;
    this.pages = {};
    document.querySelectorAll(".page").forEach((p) => {
      this.pages[p.dataset.page] = p;
    });
    this.links = [...document.querySelectorAll("[data-route]")];
    this.groups = [...document.querySelectorAll(".nav__group")];
    this.navAlias = { launch: "scripts", ablation: "scripts" };
    this.current = null;

    window.addEventListener("hashchange", () => this._sync());
  }

  start() {
    this._sync();
  }

  go(route) {
    window.location.hash = `#/${route}`;
  }

  _parse() {
    const raw = (window.location.hash || "").replace(/^#\/?/, "").trim();
    const [page, ...rest] = raw.split("/");
    if (this.pages[page]) return { page, param: rest.join("/") || null };
    return { page: "home", param: null };
  }

  _sync() {
    const { page, param } = this._parse();
    const key = `${page}/${param || ""}`;
    if (key === this.current) return;
    this.current = key;

    Object.entries(this.pages).forEach(([id, el]) => {
      el.classList.toggle("is-active", id === page);
    });

    const navTarget = this.navAlias[page] || page;
    this.links.forEach((a) => a.classList.toggle("is-current", a.dataset.route === navTarget));

    const link  = this.links.find((a) => a.dataset.route === navTarget);
    const group = link ? link.closest(".nav__group") : null;
    this.groups.forEach((g) => {
      g.classList.toggle("is-current", g === group);
      g.classList.toggle("is-open", g === group);
    });

    window.scrollTo({ top: 0, behavior: "instant" in window ? "instant" : "auto" });
    this._animateIn(this.pages[page]);

    if (this.onChange) this.onChange(page, param);
  }

  _animateIn(page) {
    if (!page || window.REDUCED_MOTION || !window.gsap) return;
    const blocks = page.querySelectorAll(".page__head, .page__head > *, .eq-tabs, .eq-grid, .flow, .master, .filter-row, .script-grid, .console, .launch__top, .launch__rail, .launch__main");
    const targets = blocks.length ? blocks : [page];
    window.gsap.fromTo(
      targets,
      { opacity: 0, y: 18 },
      { opacity: 1, y: 0, duration: 0.5, ease: "power3.out", stagger: 0.05, overwrite: true }
    );
  }
}

window.Router = Router;
