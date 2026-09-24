"use strict";

class RevealObserver {
  constructor() {
    this.io = new IntersectionObserver(
      (entries) => {
        entries.forEach((e) => {
          if (e.isIntersecting) {
            e.target.classList.add("is-in");
            this.io.unobserve(e.target);
          }
        });
      },
      { threshold: 0.1, rootMargin: "0px 0px -6% 0px" }
    );
  }

  scan() {
    document.querySelectorAll(".reveal:not(.is-in)").forEach((el) => this.io.observe(el));
  }
}

class App {
  constructor() {
    this.project = null;
    this.scenes = [];
    this.reveal = new RevealObserver();
    window.revealScan = () => this.reveal.scan();
  }

  async init() {
    this._initScenes();
    this._initNav();
    await this._loadProject();
    this._initComponents();
    this._initRouter();
    this.reveal.scan();
  }

  _initNav() {
    const nav = document.getElementById("nav");
    if (!nav) return;
    const edge = document.querySelector(".nav-edge");
    nav.querySelectorAll("a[data-route]").forEach((a) => {
      a.addEventListener("click", () => {
        a.blur();
        nav.classList.add("is-dismissed");
      });
    });
    nav.querySelectorAll(".nav__grouphead").forEach((head) => {
      head.addEventListener("click", () => {
        const group = head.closest(".nav__group");
        const open  = group.classList.contains("is-open");
        nav.querySelectorAll(".nav__group").forEach((g) => g.classList.toggle("is-open", g === group && !open));
      });
    });
    if (edge) edge.addEventListener("mouseenter", () => nav.classList.remove("is-dismissed"));
  }

  _initScenes() {
    const radar = document.getElementById("radar");
    const server = document.getElementById("server-anim");

    if (radar) this.scenes.push(new window.TomoScene(radar));

    if (server) {
      window.serverScene = new window.ServerScene(server);
      this.scenes.push(window.serverScene);
    }
  }

  async _loadProject() {
    const project = await Api.get("/api/project");

    if (project.error) {
      this.project = { interpreters: [], counts: {} };
      this._setStatus(false);
      this._retryProject();
      return;
    }

    this.project = project;
    this._setStatus(true);
    this._initStatus();
  }

  _retryProject() {
    setTimeout(async () => {
      const project = await Api.get("/api/project");
      if (project.error) {
        this._retryProject();
        return;
      }

      this.project = project;
      if (this.launchView) this.launchView.project = project;
      this._setStatus(true);
      this._initStatus();
    }, 3000);
  }

  _setStatus(ok) {
    const wrap = document.getElementById("nav-status");
    const text = document.getElementById("status-text");
    wrap.classList.toggle("is-ok", ok);
    wrap.classList.toggle("is-down", !ok);
    text.textContent = ok ? "backend live" : "offline";
  }

  _initStatus() {
    const footRoot = document.getElementById("footer-root");
    if (footRoot) footRoot.textContent = this.project.repo_root || "";

    this.statusBoard = new window.StatusBoard({
      host: document.getElementById("status-host"),
      sum: document.getElementById("status-sum"),
      board: document.getElementById("status-board"),
    });
    this.statusBoard.start();
  }

  _initComponents() {
    this.runConsole = new window.RunConsole({
      list: document.getElementById("job-list"),
      tiles: document.getElementById("console-tiles"),
      hint: document.getElementById("console-hint"),
    });
    this.runConsole.refresh();

    this.scriptPanel = new window.ScriptPanel({
      grid: document.getElementById("script-grid"),
      filters: document.getElementById("script-filters"),
    });
    this.scriptPanel.load();
    window.scriptPanel = this.scriptPanel;

    this.launchView = new window.LaunchView(this.runConsole, this.project || {});

    this.savedRunsView = new window.SavedRunsView(this.runConsole, document.getElementById("saved-grid"));

    this.repoMap = new window.RepoMapView(document.getElementById("repomap"));

    this.configBrowser = new window.ConfigBrowser(
      document.getElementById("config-list"),
      document.getElementById("config-detail"),
      document.getElementById("config-search")
    );
    this.configBrowser.load();

    this.resultsView = new window.ResultsView(
      document.getElementById("results-list"),
      document.getElementById("results-detail")
    );

    this.tomogramView = new window.TomogramView({
      strip         : document.getElementById("cube-strip"),
      stage         : document.getElementById("cube-stage"),
      deck          : document.getElementById("cube-deck"),
      topdown       : document.getElementById("cube-topdown"),
      cross         : document.getElementById("cube-cross"),
      coords        : document.getElementById("cube-coords"),
      back          : document.getElementById("cube-back"),
      hint          : document.getElementById("cube-hint"),
      slices        : document.getElementById("cube-slices"),
      slicesAt      : document.getElementById("cube-slices-at"),
      sources       : document.getElementById("cube-sources"),
      profiles      : document.getElementById("cube-profiles"),
      profAt        : document.getElementById("cube-prof-at"),
      profMixWrap   : document.getElementById("cube-prof-mix-wrap"),
      profMix       : document.getElementById("cube-prof-mix"),
      profMetrics   : document.getElementById("cube-prof-metrics"),
      progress      : document.getElementById("cube-progress"),
      progressFill  : document.getElementById("cube-progress-fill"),
      progressLabel : document.getElementById("cube-progress-label"),
      paramRow      : document.getElementById("cube-param-row"),
      paramSel      : document.getElementById("cube-param-tag"),
      slots         : document.getElementById("cube-slots"),
      slotsBody     : document.getElementById("cube-slots-body"),
      srcGroups     : [...document.querySelectorAll('[data-page="cube"] .cube-srcsel')],
      cutStacks     : [...document.querySelectorAll('[data-page="cube"] .cube-cutgroup__stack')],
      spaceBtns     : [...document.querySelectorAll(".cube-space[data-space]")],
      profModeBtns  : [...document.querySelectorAll("#cube-prof-mode .cube-space")],
      modeBtns      : [...document.querySelectorAll(".cube-mode[data-view]")],
      views         : [...document.querySelectorAll(".cube-view[data-view]")],
      transect      : {
        at      : document.getElementById("cube-transect-at"),
        undo    : document.getElementById("cube-transect-undo"),
        clear   : document.getElementById("cube-transect-clear"),
        print   : document.getElementById("cube-transect-print"),
        download: document.getElementById("cube-transect-download"),
        name    : document.getElementById("cube-transect-name"),
        save    : document.getElementById("cube-transect-save"),
        saved   : document.getElementById("cube-transect-saved"),
        remove  : document.getElementById("cube-transect-delete"),
        map     : document.getElementById("cube-transect-map"),
        overlay : document.getElementById("cube-transect-overlay"),
        grid    : document.getElementById("cube-transect-grid"),
        panels  : [...document.querySelectorAll("#cube-transect-grid .cube-eplane")].map((root) => ({
          root,
          source : root.dataset.source,
          canvas : root.querySelector("canvas"),
        })),
      },
      cloud         : {
        source    : document.getElementById("cube-cloud-source"),
        color     : document.getElementById("cube-cloud-color"),
        thr       : document.getElementById("cube-cloud-thr"),
        thrLabel  : document.getElementById("cube-cloud-thr-label"),
        thrVal    : document.getElementById("cube-cloud-thr-val"),
        max       : document.getElementById("cube-cloud-max"),
        cutAxis   : document.getElementById("cube-cloud-cut-axis"),
        cutPos    : document.getElementById("cube-cloud-cut-pos"),
        cutSweep  : document.getElementById("cube-cloud-cut-sweep"),
        demWrap   : document.getElementById("cube-cloud-dem-wrap"),
        dem       : document.getElementById("cube-cloud-dem"),
        scaleWrap : document.getElementById("cube-cloud-scale-wrap"),
        scale     : document.getElementById("cube-cloud-scale"),
        at        : document.getElementById("cube-cloud-at"),
        canvas    : document.getElementById("cube-cloud-canvas"),
      },
      volume        : {
        lo       : document.getElementById("cube-volume-lo"),
        hi       : document.getElementById("cube-volume-hi"),
        opacity  : document.getElementById("cube-volume-opacity"),
        steps    : document.getElementById("cube-volume-steps"),
        clipAxis : document.getElementById("cube-volume-clip-axis"),
        clipPos  : document.getElementById("cube-volume-clip-pos"),
        at       : document.getElementById("cube-volume-at"),
        canvas   : document.getElementById("cube-volume-canvas"),
      },
      globe         : {
        source    : document.getElementById("cube-globe-source"),
        color     : document.getElementById("cube-globe-color"),
        thr       : document.getElementById("cube-globe-thr"),
        thrLabel  : document.getElementById("cube-globe-thr-label"),
        thrVal    : document.getElementById("cube-globe-thr-val"),
        max       : document.getElementById("cube-globe-max"),
        cutAxis   : document.getElementById("cube-globe-cut-axis"),
        cutPos    : document.getElementById("cube-globe-cut-pos"),
        cutSweep  : document.getElementById("cube-globe-cut-sweep"),
        exagg     : document.getElementById("cube-globe-exagg"),
        lift      : document.getElementById("cube-globe-lift"),
        clamp     : document.getElementById("cube-globe-clamp"),
        points    : document.getElementById("cube-globe-points"),
        tracks    : document.getElementById("cube-globe-tracks"),
        fly       : document.getElementById("cube-globe-fly"),
        reframe   : document.getElementById("cube-globe-reframe"),
        full      : document.getElementById("cube-globe-full"),
        at        : document.getElementById("cube-globe-at"),
        container : document.getElementById("cube-globe-container"),
        stage     : document.getElementById("cube-globe-stage"),
        tour      : {
          move   : document.getElementById("cube-globe-move"),
          secs   : document.getElementById("cube-globe-secs"),
          play   : document.getElementById("cube-globe-play"),
          record : document.getElementById("cube-globe-record"),
        },
      },
      figures       : { root: document.getElementById("cube-figures") },
      passes        : {
        kind   : document.getElementById("cube-pass-kind"),
        play   : document.getElementById("cube-pass-play"),
        input  : document.getElementById("cube-pass-input"),
        range  : document.getElementById("cube-pass-range"),
        at     : document.getElementById("cube-pass-at"),
        media  : document.getElementById("cube-pass-media"),
        canvas : document.getElementById("cube-pass-canvas"),
        cbar   : document.getElementById("cube-pass-cbar"),
        min    : document.getElementById("cube-pass-min"),
        max    : document.getElementById("cube-pass-max"),
      },
      linkBtn       : document.getElementById("cube-link"),
      story         : {
        toggle : document.getElementById("cube-story-toggle"),
        panel  : document.getElementById("cube-story"),
        name   : document.getElementById("cube-story-name"),
        add    : document.getElementById("cube-story-add"),
        play   : document.getElementById("cube-story-play"),
        export : document.getElementById("cube-story-export"),
        clear  : document.getElementById("cube-story-clear"),
        hint   : document.getElementById("cube-story-hint"),
        list   : document.getElementById("cube-story-list"),
      },
      cmapSel       : document.getElementById("cube-cmap"),
      demWrap       : document.getElementById("cube-dem-wrap"),
      demChk        : document.getElementById("cube-dem"),
      jumpAz        : document.getElementById("cube-jump-az"),
      jumpRg        : document.getElementById("cube-jump-rg"),
      jumpGo        : document.getElementById("cube-jump-go"),
      jumpPrint     : document.getElementById("cube-jump-print"),
      jumpDownload  : document.getElementById("cube-jump-download"),
      jumpCsv       : document.getElementById("cube-jump-csv"),
      jumpAzRange   : document.getElementById("cube-jump-az-range"),
      jumpRgRange   : document.getElementById("cube-jump-rg-range"),
      sweeps        : ["elevation", "azimuth", "range"].map((axis) => {
        const grid = document.getElementById(`cube-${axis}-grid`);
        return {
          axis,
          grid,
          at     : document.getElementById(`cube-${axis}-at`),
          fill   : document.getElementById(`cube-${axis}-fill`),
          input  : document.getElementById(`cube-${axis}-input`),
          range  : document.getElementById(`cube-${axis}-range`),
          play   : document.getElementById(`cube-${axis}-play`),
          panels : [...grid.querySelectorAll(".cube-eplane")].map((root) => ({
            root,
            source : root.dataset.source,
            canvas : root.querySelector("canvas"),
          })),
        };
      }),
      panels        : [...document.querySelectorAll(".cube-slice")].map((root) => ({
        root,
        axis   : root.dataset.axis,
        source : root.dataset.source,
        canvas : root.querySelector("canvas"),
        ref    : root.querySelector(".cube-ref"),
        metric : root.querySelector(".cube-slice__metric"),
      })),
      profPanels    : [...document.querySelectorAll(".cube-prof")].map((root) => ({
        root,
        source : root.dataset.source,
        canvas : root.querySelector("canvas"),
      })),
    });
    window.tomogramView = this.tomogramView;

    this.sliceCollectorView = new window.SliceCollectorView({
      strip       : document.getElementById("sc-strip"),
      hint        : document.getElementById("sc-hint"),
      stage       : document.getElementById("sc-stage"),
      azInput     : document.getElementById("sc-az"),
      rgInput     : document.getElementById("sc-rg"),
      azRange     : document.getElementById("sc-az-range"),
      rgRange     : document.getElementById("sc-rg-range"),
      addBtn      : document.getElementById("sc-add"),
      clearBtn    : document.getElementById("sc-clear"),
      points      : document.getElementById("sc-points"),
      axesWrap    : document.getElementById("sc-axes"),
      sourcesWrap : document.getElementById("sc-sources"),
      spaceWrap   : document.getElementById("sc-space"),
      sharedWrap  : document.getElementById("sc-shared"),
      cmapSel     : document.getElementById("sc-cmap"),
      nameInput   : document.getElementById("sc-name"),
      collectBtn  : document.getElementById("sc-collect"),
      msg         : document.getElementById("sc-msg"),
      rows        : document.getElementById("sc-rows"),
    });

    this.figureDock = new window.FigureDock();
    window.figureDock = this.figureDock;
  }

  _figureTabs() {
    return {
      cube    : this.tomogramView,
      slices  : this.sliceCollectorView,
      results : this.resultsView,
    };
  }

  _mountFigures(route) {
    const view = this._figureTabs()[route];
    const page = document.querySelector(`.page[data-page="${route}"]`);

    if (!view || !page) {
      this.figureDock.unmount();
      return;
    }

    this.figureDock.mount(route, page, () => view.figureTag());
  }

  _initRouter() {
    this.router = new window.Router((route, param) => this._onRoute(route, param));
    window.router = this.router;
    this.router.start();
  }

  _onRoute(route, param) {
    if (route === "home") {
      requestAnimationFrame(() => this.scenes.forEach((s) => s.resize && s.resize()));
    }
    if (route === "launch") {
      if (param) this.launchView.show(param);
      else this.router.go("scripts");
    } else {
      this.launchView.leave();
    }
    if (route === "saved") this.savedRunsView.enter();
    if (route === "repomap") this.repoMap.enter();
    if (route === "results") this.resultsView.enter();
    if (route === "cube") this.tomogramView.enter(param);
    else this.tomogramView.leave();
    if (route === "slices") this.sliceCollectorView.enter();
    if (route === "console") this.runConsole.onShow();
    this._mountFigures(route);
    setTimeout(() => this.reveal.scan(), 60);
  }
}

document.addEventListener("DOMContentLoaded", () => new App().init());
