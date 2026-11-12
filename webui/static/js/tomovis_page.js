"use strict";

class TomoVisStatusLine {
  constructor(ctx, element) {
    this.element = element;
    ctx.bus.on("status", ({ text }) => this.show(text));
  }

  show(text) {
    this.element.textContent = text || "";
  }
}

class TomoVisMenuBar {
  static IMPORT_ACTIONS  = ["openFUSAR", "openRAT", "openUAVSAR", "openNpy"];
  static CHANNEL_ACTIONS = ["allChMenu", "ch1Menu", "ch2Menu", "ch3Menu"];
  static ITEM_CHROME     = 8;

  constructor(ctx, element) {
    this.ctx     = ctx;
    this.element = element;
    this.titles  = [...element.querySelectorAll(".tv-menubar__item")];
    this.menu    = null;
    this.openKey = null;

    this.titles.forEach((title) => {
      title.style.width = `${QtFontMetrics.sizeWidth(title.textContent, QtFontMetrics.WINDOW) + TomoVisMenuBar.ITEM_CHROME}px`;
      title.addEventListener("pointerdown", (event) => {
        if (event.button !== 0) return;
        event.preventDefault();
        if (this.openKey === title.dataset.menu) this.closeMenu();
        else this.open(title.dataset.menu, false);
      });
      title.addEventListener("pointerenter", () => {
        if (this.openKey && this.openKey !== title.dataset.menu) this.open(title.dataset.menu, false);
      });
      title.addEventListener("keydown", (event) => this.titleKey(event, title));
    });
    element.addEventListener("pointerdown", (event) => {
      if (!event.target.closest(".tv-menubar__item")) this.closeMenu();
    });
    ctx.bus.on("snapshot", () => this.refresh());
  }

  controls() {
    const snapshot = this.ctx.session.snapshot;
    if (!snapshot) throw new Error("TomoVis menu bar opened before the first snapshot");
    return snapshot.controls;
  }

  action(name) {
    const control = this.controls()[name];
    if (!control) throw new Error(`TomoVis snapshot has no action ${name}`);
    return {
      text      : control.text,
      shortcut  : control.shortcut || "",
      statusTip : control.statusTip || "",
      enabled   : control.enabled,
      checkable : Boolean(control.checkable),
      checked   : Boolean(control.checked),
      onTrigger : () => this.trigger(name),
    };
  }

  items(key) {
    const controls = this.controls();
    if (key === "file") {
      const importMenu = controls.importMenu;
      return [
        this.action("openFile"),
        this.action("saveFile"),
        { separator: true },
        { text: importMenu ? importMenu.title : "Import", enabled: importMenu ? importMenu.enabled : true, submenu: TomoVisMenuBar.IMPORT_ACTIONS.map((name) => this.action(name)) },
      ];
    }
    const channels = TomoVisMenuBar.CHANNEL_ACTIONS.map((name) => ({ ...this.action(name), checkable: true, radio: true }));
    return [{ text: controls.ChMenu.title, enabled: controls.ChMenu.enabled, submenu: channels }];
  }

  trigger(name) {
    this.ctx.session.send({ type: "trigger", widget: name }).catch((error) => this.ctx.session.raiseUnreported(error));
  }

  open(key, keyboard) {
    if (!this.ctx.session.snapshot) return;
    this.closeMenu();
    const title = this.titles.find((t) => t.dataset.menu === key);
    this.openKey = key;
    title.classList.add("is-open");
    title.setAttribute("aria-expanded", "true");

    this.menu = new TomoVisMenu(this.ctx, this.items(key), { onClose: () => this.closed(title), ignore: this.element });
    this.menu.onKeyOut = (direction) => this.step(direction);
    this.menu.openBelow(title);
    if (keyboard) this.menu.first();
  }

  closed(title) {
    title.classList.remove("is-open");
    title.setAttribute("aria-expanded", "false");
    this.openKey = null;
    this.menu    = null;
  }

  closeMenu() {
    if (this.menu) this.menu.close();
  }

  step(direction) {
    const index = this.titles.findIndex((t) => t.dataset.menu === this.openKey);
    const next  = this.titles[(index + (direction === "right" ? 1 : -1) + this.titles.length) % this.titles.length];
    this.open(next.dataset.menu, true);
  }

  titleKey(event, title) {
    if (event.key === "Enter" || event.key === " " || event.key === "ArrowDown") {
      event.preventDefault();
      this.open(title.dataset.menu, true);
    } else if (event.key === "ArrowRight" || event.key === "ArrowLeft") {
      event.preventDefault();
      const index = this.titles.indexOf(title);
      const next  = this.titles[(index + (event.key === "ArrowRight" ? 1 : -1) + this.titles.length) % this.titles.length];
      next.focus();
    }
  }

  refresh() {
    if (this.menu && this.menu.isOpen && !this.menu.child) this.menu.setItems(this.items(this.openKey));
  }
}

class TomoVisTabStrip {
  static TAB_HSPACE = 25;

  constructor(ctx, element, panels, has3d) {
    this.ctx     = ctx;
    this.element = element;
    this.tabs    = [...element.querySelectorAll(".tv-tab")];
    this.panels  = panels;
    this.current = 0;

    if (!has3d) {
      this.tabs[3].hidden   = true;
      this.panels[3].hidden = true;
      this.tabs.length      = 3;
      this.panels.length    = 3;
    }

    this.tabs.forEach((tab, index) => {
      tab.style.width = `${QtFontMetrics.sizeWidth(tab.textContent, QtFontMetrics.WINDOW) + TomoVisTabStrip.TAB_HSPACE}px`;
      tab.addEventListener("click", () => this.choose(index));
      tab.addEventListener("keydown", (event) => this.key(event));
    });
    element.addEventListener("wheel", (event) => this.wheel(event), { passive: false });
    ctx.bus.on("snapshot", ({ snapshot }) => this.follow(snapshot));
    this.render();
  }

  choose(index) {
    if (index === this.current) return;
    this.show(index);
    this.ctx.session.send({ type: "tab", index }).catch((error) => this.ctx.session.raiseUnreported(error));
  }

  step(offset) {
    const next = this.current + offset;
    if (next < 0 || next >= this.tabs.length) return;
    this.choose(next);
  }

  key(event) {
    const moves = { ArrowRight: 1, ArrowLeft: -1 };
    if (!(event.key in moves)) return;
    event.preventDefault();
    this.step(moves[event.key]);
    this.tabs[this.current].focus();
  }

  overTabs(event) {
    const first = this.tabs[0].getBoundingClientRect();
    const last  = this.tabs[this.tabs.length - 1].getBoundingClientRect();
    return event.clientX >= first.left && event.clientX < last.right && event.clientY >= Math.min(first.top, last.top) && event.clientY < Math.max(first.bottom, last.bottom);
  }

  wheel(event) {
    if (!this.overTabs(event)) return;
    event.preventDefault();
    const delta = Math.abs(event.deltaX) > Math.abs(event.deltaY) ? event.deltaX : event.deltaY;
    this.step(delta < 0 ? -1 : 1);
  }

  follow(snapshot) {
    const index = snapshot.controls.tabWidget.index;
    if (this.ctx.session.pending("tabWidget")) return;
    if (index !== this.current) this.show(index);
  }

  show(index) {
    this.current = index;
    this.render();
    this.ctx.bus.emit("tab", { index });
  }

  render() {
    this.tabs.forEach((tab, i) => {
      const on = i === this.current;
      tab.classList.toggle("is-current", on);
      tab.setAttribute("aria-selected", String(on));
      tab.tabIndex = on ? 0 : -1;
    });
    this.panels.forEach((panel, i) => panel.classList.toggle("is-current", i === this.current));
  }
}

class TomoVisShortcuts {
  static KEYS = { o: "Ctrl+O", s: "Ctrl+S", f: "Ctrl+F" };

  constructor(ctx) {
    this.ctx      = ctx;
    this.attached = false;
    this.handler  = (event) => this.keydown(event);
  }

  attach() {
    if (this.attached) return;
    document.addEventListener("keydown", this.handler, true);
    this.attached = true;
  }

  detach() {
    if (!this.attached) return;
    document.removeEventListener("keydown", this.handler, true);
    this.attached = false;
  }

  keydown(event) {
    if (!(event.ctrlKey || event.metaKey) || event.altKey || event.shiftKey) return;
    const keys = TomoVisShortcuts.KEYS[event.key.toLowerCase()];
    if (!keys) return;
    event.preventDefault();
    if (TomoVisModal.isOpen() || !this.ctx.session.sid || this.popupOpen()) return;
    event.stopPropagation();
    this.ctx.session.send({ type: "shortcut", keys }).catch((error) => this.ctx.session.raiseUnreported(error));
  }

  popupOpen() {
    return Boolean(TomoVisMenu.root) || Boolean(this.ctx.layer.querySelector(".tv-combo__popup"));
  }
}

class TomoVisPageBase {
  static probeWebGL2() {
    const canvas = document.createElement("canvas");
    const gl     = canvas.getContext("webgl2");
    if (!gl) return false;
    const lose = gl.getExtension("WEBGL_lose_context");
    if (lose) lose.loseContext();
    return true;
  }

  constructor(root, layer) {
    this.root    = root;
    this.layer   = layer;
    this.active  = false;
    this.ready   = null;
    this.ctx     = null;
    this.webgl2  = false;
    window.addEventListener("pagehide", () => {
      if (this.ctx) this.ctx.session.close();
    });
  }

  context() {
    const bus     = new TomoVisBus();
    const ctx     = { bus, layer: this.layer, page: this, tables: null };
    ctx.session   = new TomoVisSession(bus);
    ctx.kit       = new TomoVisWidgets(ctx);
    ctx.dialogs   = new TomoVisDialogs(ctx);
    ctx.session.dialogSink = (requests) => ctx.dialogs.enqueue(requests);
    return ctx;
  }

  async tables() {
    const tables = await Api.get(`${TomoVisSession.ROOT}/tables`);
    if (tables.error) throw new Error(tables.error);
    return { ...tables, webgl2: this.webgl2 };
  }

  enter() {
    this.active = true;
    if (!this.ready) this.ready = this.start().catch((error) => this.failed(error));
    this.ready.then((ok) => {
      if (ok && this.active) this.shown();
    });
  }

  leave() {
    if (!this.active) return;
    this.active = false;
    if (this.ctx) this.hidden();
  }

  failed(error) {
    this.ready = null;
    Toast.show(`TomoVis could not start: ${error.message}`, "error");
    this.report(`TomoVis could not start: ${error.message}`);
    return false;
  }

  report() {}
}

class TomoVisPage extends TomoVisPageBase {
  static TITLE = "TomoVis";

  constructor(root) {
    super(root, root.querySelector("#tv-layer"));
    this.window     = root.querySelector("#tv-window");
    this.busyOrb    = root.querySelector("#tv-busy");
    this.statusEl   = root.querySelector("#tv-status");
    this.panels     = ["#tv-panel-slicer", "#tv-panel-plot", "#tv-panel-profile", "#tv-panel-3d"].map((id) => root.querySelector(id));
    this.views      = [];
    this.current    = -1;
    this.savedTitle = null;
    this.shell      = null;
    this.bridge     = new TomoVisBridge(this, root.querySelector("#tvb-caption"));
  }

  enter() {
    if (!this.active) {
      this.savedTitle = document.title;
      document.title  = TomoVisPage.TITLE;
    }
    document.body.classList.add("is-tomovis-page");
    super.enter();
  }

  leave() {
    if (!this.active) return;
    document.title = this.savedTitle;
    document.body.classList.remove("is-tomovis-page");
    super.leave();
  }

  setup() {
    this.webgl2 = TomoVisPageBase.probeWebGL2();
    this.ctx    = this.context();
    const ctx   = this.ctx;

    this.status    = new TomoVisStatusLine(ctx, this.statusEl);
    this.menubar   = new TomoVisMenuBar(ctx, this.root.querySelector("#tv-menubar"));
    this.tabs      = new TomoVisTabStrip(ctx, this.root.querySelector("#tv-tabs"), [...this.panels], this.webgl2);
    this.shortcuts = new TomoVisShortcuts(ctx);
    this.timer     = new TomoVisTimerDriver(ctx.session, ctx.bus);

    ctx.session.onExpired = () => this.expired();
    ctx.bus.on("busy", ({ busy }) => { this.busyOrb.hidden = !busy; });
    ctx.bus.on("tab", ({ index }) => this.switchView(index));
    this.shell = ctx;
  }

  async start() {
    if (!this.shell) this.setup();
    const ctx = this.ctx;
    ctx.dialogs.activate();
    ctx.tables = await this.tables();
    await ctx.session.open({ kind: "window", webgl2: this.webgl2 });
    this.bridge.attach(ctx);
    this.statusEl.textContent = "";

    this.views = [
      new window.TomoVisSlicerTab(this.panels[0], ctx),
      new window.TomoVisPlotTab(this.panels[1], ctx),
      new window.TomoVisProfileTab(this.panels[2], ctx),
      this.webgl2 ? new window.TomoVisVolumeTab(this.panels[3], ctx) : null,
    ];
    this.current = -1;
    return true;
  }

  shown() {
    this.ctx.dialogs.activate();
    this.shortcuts.attach();
    this.switchView(this.tabs.current);
    this.ctx.bus.emit("page", { active: true });
    this.bridge.shown();
  }

  hidden() {
    this.bridge.hidden();
    this.shortcuts.detach();
    if (TomoVisMenu.root) TomoVisMenu.root.close();
    const view = this.views[this.current];
    if (view) view.deactivate();
    this.current = -1;
    this.ctx.bus.emit("status", { text: "" });
    this.ctx.bus.emit("page", { active: false });
  }

  switchView(index) {
    if (!this.active || this.views.length === 0 || index === this.current) return;
    const previous = this.views[this.current];
    if (previous) previous.deactivate();
    this.current = index;
    const next = this.views[index];
    if (next) next.activate();
  }

  async expired() {
    Toast.show("TomoVis session expired; a new window was opened.", "warn");
    await this.ctx.session.open({ kind: "window", webgl2: this.webgl2 });
    this.bridge.check("expired");
  }

  report(text) {
    this.statusEl.textContent = text;
  }
}

class TomoVisScriptsPage extends TomoVisPageBase {
  constructor(root) {
    super(root, root.querySelector("#tv-scripts-layer"));
    this.slicerRoot = root.querySelector("#tv-script-slicer");
    this.volumeRoot = root.querySelector("#tv-script-volume");
    this.views      = [];
    this.bridge     = new TomoVisScriptsBridge(this, document.getElementById("tvs-dataset-bar"));
  }

  async start() {
    this.webgl2 = TomoVisPageBase.probeWebGL2();
    this.ctx    = this.context();
    const ctx   = this.ctx;
    ctx.session.onExpired = () => this.expired();
    ctx.dialogs.activate();
    ctx.tables = await this.tables();
    await ctx.session.open({ kind: "scripts", webgl2: this.webgl2 });

    this.views = [new window.TomoVisSlicerScript(this.slicerRoot, ctx), new window.TomoVisVolumeScript(this.volumeRoot, ctx)];
    return true;
  }

  shown() {
    this.ctx.dialogs.activate();
    this.views.forEach((view) => view.activate());
    this.ctx.bus.emit("page", { active: true });
    this.bridge.shown();
  }

  hidden() {
    if (TomoVisMenu.root) TomoVisMenu.root.close();
    this.views.forEach((view) => view.deactivate());
    this.ctx.bus.emit("page", { active: false });
  }

  async expired() {
    Toast.show("TomoVis scripts session expired; a new one was opened.", "warn");
    await this.ctx.session.open({ kind: "scripts", webgl2: this.webgl2 });
  }

  failed(error) {
    this.ctx = null;
    return super.failed(error);
  }

  report(text) {
    this.slicerRoot.textContent = text;
  }
}

window.TomoVisStatusLine  = TomoVisStatusLine;
window.TomoVisMenuBar     = TomoVisMenuBar;
window.TomoVisTabStrip    = TomoVisTabStrip;
window.TomoVisShortcuts   = TomoVisShortcuts;
window.TomoVisPageBase    = TomoVisPageBase;
window.TomoVisPage        = TomoVisPage;
window.TomoVisScriptsPage = TomoVisScriptsPage;
