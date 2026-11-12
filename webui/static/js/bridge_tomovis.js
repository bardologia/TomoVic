"use strict";

class TomoVisBridge {
  static RETRY_MS     = 300;
  static PREPARING_MS = 500;
  static TOLERANCE    = 1e-9;
  static FUSAR_FILTER = "FuSAR Tomo (*.hd5)";

  static preparing(dataset) {
    const parts = [dataset.stage, `${Math.round(dataset.progress * 100)}%`].filter(Boolean);
    return { text: `Preparing for the TomoVic tools: ${parts.join(" ")}`, actions: [] };
  }

  constructor(page, caption) {
    this.page      = page;
    this.caption   = caption;
    this.bridge    = window.datasetBridge;
    this.indicator = this.bridge.mountIndicator(caption, { variant: "caption", page: "tomovis" });
    this.ctx       = null;
    this.reason    = null;
    this.serial    = null;
    this.running   = false;
    this.again     = false;
    this.timer     = null;
    this.forced    = null;
    this.refused   = null;
  }

  attach(ctx) {
    if (this.ctx === ctx) return;
    this.ctx = ctx;
    ctx.bus.on("snapshot", ({ snapshot, previous }) => this.snapshot(snapshot, previous));
    this.bridge.on("current", ({ state }) => this.followed(state));
    this.bridge.on("dataset", () => this.changed());
  }

  snapshot(snapshot, previous) {
    if (!previous) return;
    const answered = Boolean(previous.pending_dialog) && !snapshot.pending_dialog;
    const reshaped = JSON.stringify(previous.attributes.data_shape) !== JSON.stringify(snapshot.attributes.data_shape);
    if (answered || reshaped) this.check("snapshot");
  }

  followed(state) {
    this.render(state);
    if (this.page.active) this.check("current");
  }

  changed() {
    if (this.page.active) this.check("current");
  }

  shown() {
    return this.check("shown");
  }

  hidden() {
    clearTimeout(this.timer);
    this.timer = null;
  }

  render(state) {
    this.caption.hidden = !(state.current || state.bridge_error);
  }

  blocked() {
    const session = this.ctx.session;
    return TomoVisModal.isOpen() || !session.idle() || Boolean(session.snapshot.pending_dialog);
  }

  later(ms) {
    clearTimeout(this.timer);
    this.timer = setTimeout(() => {
      this.timer = null;
      if (this.page.active) this.check("retry");
    }, ms);
  }

  attempt(dataset) {
    return `${this.serial}|${dataset.id}#${dataset.tomovis.revision}`;
  }

  wanted(state) {
    const dataset = state.current;
    if (!dataset || !dataset.tomovis.ready) return false;
    if (this.forced === dataset.id) return true;
    return state.tomovis.open && this.refused !== this.attempt(dataset);
  }

  async open(dataset) {
    const session = this.ctx.session;
    const sink    = session.dialogSink;
    let   token   = null;
    let   answer  = null;
    this.forced   = null;

    session.dialogSink = (requests) => {
      const mine = requests.find((r) => r.kind === "file" && r.mode === "open" && r.filters[0] === TomoVisBridge.FUSAR_FILTER);
      if (mine) token = mine.token;
      const rest = requests.filter((r) => r !== mine);
      if (rest.length) sink(rest);
    };
    try {
      answer = await session.send({ type: "trigger", widget: "openFUSAR" }).catch((error) => session.raiseUnreported(error));
    } finally {
      session.dialogSink = sink;
    }
    if (!answer) return this.bridge.current(session.sid);

    if (!token) {
      this.refused = this.attempt(dataset);
      Toast.show(`TomoVis could not open ${dataset.name}: it did not offer its hd5 import.`, "error");
      return this.bridge.current(session.sid);
    }

    const result = await session.send({ type: "dialog_result", token, accepted: true, path: dataset.tomovis.link }).catch((error) => session.raiseUnreported(error));
    if (!result) return this.bridge.current(session.sid);
    if (result.dialogs.some((d) => d.kind === "message" && d.level === "critical")) this.refused = this.attempt(dataset);
    else Toast.show(`TomoVis opened ${dataset.name}, the current dataset.`, "ok");
    return this.bridge.current(session.sid);
  }

  differs(wanted, shown) {
    return wanted.some((value, i) => Math.abs(value - shown[i]) > TomoVisBridge.TOLERANCE * Math.max(Math.abs(value), Math.abs(shown[i])));
  }

  async use(dataset) {
    this.refused = null;
    await this.bridge.use(dataset.id);
    await this.check("use");
  }

  async useHeights(dataset) {
    this.refused = null;
    this.forced  = dataset.id;
    await this.bridge.use(dataset.id);
    await this.check("heights");
  }

  complete(dataset, piece) {
    return this.bridge.complete(dataset.id, [piece], { onDone: () => this.check("added") });
  }

  notice(state) {
    const dataset = state.current;
    if (state.bridge_error) return { text: state.bridge_error, actions: [] };
    if (!dataset) return null;
    if (dataset.state === "preparing") return TomoVisBridge.preparing(dataset);
    if (!dataset.tomovis.ready && dataset.pieces.tomogram.problem) return { text: `TomoVis cannot open ${dataset.name}: ${dataset.pieces.tomogram.problem}.`, actions: [] };
    if (!dataset.tomovis.ready && dataset.error) return { text: dataset.error, actions: [] };

    const held = state.tomovis.held;
    if (!held) return { text: `${dataset.name} is not open in this window.`, actions: [{ label: "Open in TomoVis", run: () => this.use(dataset) }] };
    if (held.id !== dataset.id) return { text: `This window shows ${held.name}. Current dataset: ${dataset.name}.`, actions: [{ label: `Open ${dataset.name} here`, run: () => this.use(dataset) }] };

    const heights = dataset.pieces.height_range;
    const spacing = dataset.pieces.spacing;
    const run     = dataset.origin === "run";
    if (heights.present && this.differs(heights.value, this.ctx.session.snapshot.attributes.z_range)) return { text: "TomoVis opened this file with its own axes.", actions: [{ label: "Use the dataset heights", run: () => this.useHeights(dataset) }] };
    if (!heights.present && !run) return { text: "Elevation is shown in samples.", actions: [{ label: "Add height range", run: () => this.complete(dataset, "height_range") }] };
    if (!spacing.present && run) return { text: "This run has no pixel spacing; distances are shown in pixels.", actions: [] };
    if (!spacing.present) return { text: "Distances are shown in pixels.", actions: [{ label: "Add pixel spacing", run: () => this.complete(dataset, "spacing") }] };
    return null;
  }

  async pass() {
    if (!this.page.active) return;
    if (this.blocked()) {
      this.later(TomoVisBridge.RETRY_MS);
      return;
    }

    let state = await this.bridge.current(this.ctx.session.sid);
    this.serial = state.serial;
    if (this.forced && (!state.current || state.current.id !== this.forced)) this.forced = null;
    if (this.wanted(state)) {
      if (!this.page.active) return;
      if (this.blocked()) {
        this.later(TomoVisBridge.RETRY_MS);
        return;
      }
      state = await this.open(state.current);
    }

    this.render(state);
    this.indicator.setNotice(this.notice(state));
    if (state.current && state.current.state === "preparing") this.later(TomoVisBridge.PREPARING_MS);
  }

  async check(reason) {
    this.reason = reason;
    this.again  = true;
    if (this.running) return;
    this.running = true;
    try {
      while (this.again) {
        this.again = false;
        await this.pass();
      }
    } finally {
      this.running = false;
    }
  }
}

class TomoVisScriptsBridge {
  static LARGE_BYTES = 512 * 1024 * 1024;

  constructor(page, bar) {
    this.page      = page;
    this.bar       = bar;
    this.bridge    = window.datasetBridge;
    this.indicator = this.bridge.mountIndicator(bar, { variant: "bar", page: "tomovis_scripts" });
    this.filled    = null;
    this.bridge.on("current", ({ state }) => this.followed(state));
  }

  followed(state) {
    if (this.page.active) this.follow(state);
  }

  async shown() {
    this.follow(await this.bridge.current());
  }

  fill(link, force) {
    for (const view of this.page.views) {
      const text = view.path.input.value;
      if (force || text === "" || text === this.filled) view.path.set({ text: link });
    }
    this.filled = link;
  }

  size(bytes) {
    if (bytes >= 1024 * 1024 * 1024) return `${(bytes / (1024 * 1024 * 1024)).toFixed(1)} GB`;
    return `${Math.round(bytes / (1024 * 1024))} MB`;
  }

  complete(dataset) {
    return this.bridge.complete(dataset.id, ["height_range"], { onDone: () => this.shown() });
  }

  notice(dataset) {
    if (!dataset) return null;
    if (dataset.state === "preparing") return TomoVisBridge.preparing(dataset);

    const large   = dataset.cube !== null && dataset.cube.bytes > TomoVisScriptsBridge.LARGE_BYTES;
    const warning = large ? `This cube is ${this.size(dataset.cube.bytes)}; both scripts read it whole and the volume script sends it to the browser.` : "";
    const heights = dataset.pieces.height_range;
    if (dataset.tomovis.scripts_ready) return { text: warning, actions: [{ label: "Use the current dataset", run: () => this.fill(dataset.tomovis.scripts_link, true) }] };
    if (!heights.present) return { text: ["The scripts need the height range.", warning].filter(Boolean).join(" "), actions: heights.addable ? [{ label: "Add height range", run: () => this.complete(dataset) }] : [] };
    return warning ? { text: warning, actions: [] } : null;
  }

  follow(state) {
    const dataset = state.current;
    if (state.set_by === "tomovic" && dataset && dataset.tomovis.scripts_ready) this.fill(dataset.tomovis.scripts_link, false);
    this.indicator.setNotice(this.notice(dataset));
  }
}

window.TomoVisBridge        = TomoVisBridge;
window.TomoVisScriptsBridge = TomoVisScriptsBridge;
