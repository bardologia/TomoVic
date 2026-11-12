"use strict";

class DatasetBridgeError extends Error {
  constructor(message, piece = null) {
    super(message);
    this.name  = "DatasetBridgeError";
    this.piece = piece;
  }
}

class DatasetWords {
  static STANDIN_TITLE = "Top view of the tomogram (stand-in for the primary SLC)";
  static PRIMARY_TITLE = "Primary SLC amplitude";
  static COMBINED      = "All channels combined (square root of the summed power)";
  static TOOL_TITLES   = {
    cube        : "The Cube page needs",
    slices      : "The Slices page needs",
    cube_globe  : "The Globe needs",
    cube_passes : "The Passes view needs",
    cube_pauli  : "The Pauli view needs",
  };

  static list(items) {
    if (items.length < 2) return items.join("");
    return `${items.slice(0, -1).join(", ")} and ${items[items.length - 1]}`;
  }

  static labels(dataset, keys) {
    return DatasetWords.list(keys.map((key) => dataset.pieces[key].label));
  }

  static title(tool, dataset) {
    const labels = DatasetWords.labels(dataset, dataset.tools[tool].missing);
    if (tool === "cube" || tool === "slices") return `${DatasetWords.TOOL_TITLES[tool]} ${labels} for ${dataset.name}.`;
    return `${DatasetWords.TOOL_TITLES[tool]} ${labels}.`;
  }

  static percent(dataset) {
    return Math.max(0, Math.min(100, Math.round(dataset.progress * 100)));
  }

  static chip(dataset) {
    const missing = dataset.tools.cube.missing;
    if (dataset.state === "error") return "Error";
    if (dataset.state === "preparing") return `Preparing ${DatasetWords.percent(dataset)}%`;
    if (dataset.tools.cube.ready || !missing.length) return "Ready";
    if (missing.length === 1) return `Needs ${dataset.pieces[missing[0]].label}`;
    return `Needs ${missing.length} pieces`;
  }

  static tone(dataset) {
    if (dataset.state === "error") return "error";
    if (dataset.state === "preparing") return "preparing";
    return dataset.tools.cube.ready ? "ready" : "missing";
  }

  static channel(choice) {
    return choice === "combined" ? DatasetWords.COMBINED : `Channel ${Number(choice) + 1}`;
  }

  static metres(value) {
    return `${Number(value.toPrecision(6))} m`;
  }

  static bytes(count) {
    if (count >= 1024 ** 3) return `${(count / 1024 ** 3).toFixed(1)} GB`;
    if (count >= 1024 ** 2) return `${Math.round(count / 1024 ** 2)} MB`;
    return `${Math.max(1, Math.round(count / 1024))} KB`;
  }

  static value(key, piece) {
    const value = piece.value;
    if (key === "tomogram") return `${value.shape.join(" x ")} ${value.dtype}`;
    if (key === "channel") return value === null ? "single channel" : DatasetWords.channel(value);
    if (key === "height_range") return `${DatasetWords.metres(value[0])} to ${DatasetWords.metres(value[1])}`;
    if (key === "primary") return { "stand-in": "top view of the tomogram", file: "linked file", run: "from preprocessing" }[value.kind];
    if (key === "spacing") return `${DatasetWords.metres(value[0])} azimuth x ${DatasetWords.metres(value[1])} range`;
    if (key === "geometry") return value.geometry_field ? "with a geometry field" : "without a geometry field";
    if (key === "passes") return `${value.secondaries} secondaries${value.interferograms ? " with interferograms" : ""}`;
    if (key === "polarimetry") return `multilook window ${value.window[0]} x ${value.window[1]}`;
    if (key === "params") return value.tags.join(", ");
    return "present";
  }

  static summary(key, piece) {
    if (!piece.present) return piece.note || "missing";
    const origin = piece.origin && piece.origin !== "preprocessing" && piece.origin !== "single channel" ? ` (${piece.origin})` : "";
    return `${DatasetWords.value(key, piece)}${origin}`;
  }
}

class DatasetLayer {
  static stack = [];

  constructor(className, label) {
    this.root     = document.createElement("div");
    this.ignore   = [];
    this.onClosed = null;
    this.outside  = (ev) => this._onOutside(ev);
    this.escape   = (ev) => this._onEscape(ev);

    this.root.className = `ds-layer ${className}`;
    this.root.setAttribute("role", "dialog");
    this.root.setAttribute("aria-label", label);
    this.root.addEventListener("keydown", (ev) => this._onKey(ev));
  }

  static top() {
    return DatasetLayer.stack[DatasetLayer.stack.length - 1] || null;
  }

  show() {
    document.body.appendChild(this.root);
    DatasetLayer.stack.push(this);
    document.addEventListener("mousedown", this.outside, true);
    document.addEventListener("keydown", this.escape);
  }

  _onKey(ev) {
    ev.stopPropagation();
    if (ev.key === "Escape" && DatasetLayer.top() === this) this.close();
  }

  _onEscape(ev) {
    if (ev.key === "Escape" && DatasetLayer.top() === this) this.close();
  }

  _onOutside(ev) {
    if (!this.dismissable() || DatasetLayer.top() !== this) return;
    if (this.root.contains(ev.target) || this.ignore.some((el) => el.contains(ev.target))) return;
    this.close();
  }

  dismissable() {
    return true;
  }

  close() {
    if (!this.root.isConnected) return;
    this.root.remove();
    DatasetLayer.stack = DatasetLayer.stack.filter((layer) => layer !== this);
    document.removeEventListener("mousedown", this.outside, true);
    document.removeEventListener("keydown", this.escape);
    if (this.onClosed) this.onClosed();
  }
}

class DatasetFilePicker extends DatasetLayer {
  static KEY = "dataset-picker-dir";

  constructor(mode, title) {
    super("ds-picker", title);
    this.mode     = mode;
    this.dir      = "";
    this.parent   = null;
    this.selected = null;
    this.resolve  = null;
    this.listSeq  = 0;
    this.typed    = false;

    this.root.innerHTML = `
      <div class="ds-picker__box">
        <h3 class="ds-picker__title"></h3>
        <div class="ds-picker__bar">
          <button type="button" class="btn btn--mini ds-picker__up">Up</button>
          <input type="text" class="ds-input ds-picker__path" spellcheck="false" autocomplete="off" aria-label="Folder or file path" />
        </div>
        <p class="ds-picker__error" role="alert" hidden></p>
        <ul class="ds-picker__list" role="listbox" aria-label="Folder content"></ul>
        <div class="ds-picker__foot">
          <button type="button" class="btn btn--mini ds-picker__cancel">Cancel</button>
          <button type="button" class="btn btn--primary ds-picker__accept"></button>
        </div>
      </div>`;

    this.titleEl  = this.root.querySelector(".ds-picker__title");
    this.pathEl   = this.root.querySelector(".ds-picker__path");
    this.errorEl  = this.root.querySelector(".ds-picker__error");
    this.listEl   = this.root.querySelector(".ds-picker__list");
    this.acceptEl = this.root.querySelector(".ds-picker__accept");

    this.titleEl.textContent  = title;
    this.acceptEl.textContent = mode === "file" ? "Pick a .npy file" : "Use this folder";

    this.root.querySelector(".ds-picker__up").addEventListener("click", () => this._up());
    this.root.querySelector(".ds-picker__cancel").addEventListener("click", () => this.close());
    this.acceptEl.addEventListener("click", () => this._accept());
    this.pathEl.addEventListener("keydown", (ev) => this._onPathKey(ev));
    this.pathEl.addEventListener("input", () => { this.typed = true; });
  }

  static pick({ mode = "file", title = "" } = {}) {
    return new DatasetFilePicker(mode, title || (mode === "file" ? "Pick a .npy file" : "Pick a folder")).open();
  }

  static stored() {
    try {
      return localStorage.getItem(DatasetFilePicker.KEY) || "";
    } catch (e) {
      return "";
    }
  }

  static remember(dir) {
    try {
      localStorage.setItem(DatasetFilePicker.KEY, dir);
    } catch (e) {
      return;
    }
  }

  static join(dir, name) {
    return `${dir.replace(/\/+$/, "")}/${name}`;
  }

  static parentOf(path) {
    const cut = path.replace(/\/+$/, "").lastIndexOf("/");
    return cut > 0 ? path.slice(0, cut) : "/";
  }

  dismissable() {
    return false;
  }

  open() {
    this.show();
    this._list(DatasetFilePicker.stored(), true);
    this.pathEl.focus();
    return new Promise((resolve) => { this.resolve = resolve; });
  }

  async _list(path, fallback = false) {
    const seq     = ++this.listSeq;
    const pattern = this.mode === "file" ? "&pattern=*.npy" : "";
    this.typed    = false;
    const listing = await Api.get(`/api/tomovis/fs?path=${encodeURIComponent(path)}${pattern}`);
    if (seq !== this.listSeq) return;

    if (listing.error || listing.ok === false) {
      if (fallback && path) {
        this._list("", false);
        return;
      }
      this._showError(listing.error);
      return;
    }

    this.dir      = listing.path;
    this.parent   = listing.parent;
    this.selected = null;
    if (!this.typed) this.pathEl.value = listing.path;
    this._showError("");
    this._render(listing.entries);
  }

  _showError(text) {
    this.errorEl.textContent = text;
    this.errorEl.hidden      = !text;
  }

  _render(entries) {
    const shown = this.mode === "file" ? entries : entries.filter((entry) => entry.dir);
    this.listEl.innerHTML = "";

    shown.forEach((entry) => {
      const item = document.createElement("li");
      item.className   = `ds-picker__entry${entry.dir ? " is-dir" : ""}`;
      item.textContent = entry.dir ? `${entry.name}/` : entry.name;
      item.setAttribute("role", "option");
      item.dataset.name = entry.name;
      item.addEventListener("click", () => this._onEntry(entry, item));
      if (!entry.dir) item.addEventListener("dblclick", () => this._accept());
      this.listEl.appendChild(item);
    });

    if (!shown.length) {
      const empty = document.createElement("li");
      empty.className   = "ds-picker__empty";
      empty.textContent = this.mode === "file" ? "No folders or .npy files here." : "No folders here.";
      this.listEl.appendChild(empty);
    }
  }

  _onEntry(entry, item) {
    const path = DatasetFilePicker.join(this.dir, entry.name);
    if (entry.dir) {
      this._list(path);
      return;
    }

    this.selected = path;
    this.pathEl.value = path;
    this.listEl.querySelectorAll(".ds-picker__entry").forEach((el) => el.classList.toggle("is-selected", el === item));
  }

  _onPathKey(ev) {
    if (ev.key !== "Enter") return;
    ev.preventDefault();
    const typed = this.pathEl.value.trim();
    if (this.mode === "file" && /\.npy$/i.test(typed)) this._accept();
    else if (typed) this._list(typed);
  }

  _up() {
    if (this.parent) this._list(this.parent);
  }

  _accept() {
    const typed = this.pathEl.value.trim();
    const path  = this.mode === "file" ? (typed || this.selected) : (typed || this.dir);

    if (!path || (this.mode === "file" && path === this.dir)) {
      this._showError("Pick a file in the list or type its path.");
      return;
    }

    DatasetFilePicker.remember(this.mode === "file" ? DatasetFilePicker.parentOf(path) : path);
    const resolve = this.resolve;
    this.resolve = null;
    this.close();
    resolve(path);
  }

  close() {
    super.close();
    if (this.resolve) {
      const resolve = this.resolve;
      this.resolve = null;
      resolve(null);
    }
  }
}

class DatasetCompleter {
  constructor(bridge, id, keys, { title = "", onDone = null, compact = false } = {}) {
    this.bridge  = bridge;
    this.id      = id;
    this.keys    = keys;
    this.title   = title;
    this.onDone  = onDone;
    this.compact = compact;
    this.closer  = null;
    this.dataset = null;

    this.root = document.createElement("div");
    this.root.className = `ds-completer${compact ? " ds-completer--compact" : ""}`;
    this.root.addEventListener("keydown", (ev) => ev.stopPropagation());
  }

  static launchButton(bridge, dataset, launch) {
    const tool = dataset.tools[launch.script];
    const btn  = DatasetCompleter.button(launch.label, "ds-launch");

    btn.disabled = !tool.ready;
    btn.title    = tool.ready ? `Open the ${tool.label} launch page with ${dataset.name} filled in` : (tool.missing.length ? `Needs ${DatasetWords.labels(dataset, tool.missing)}` : tool.note);
    btn.addEventListener("click", () => bridge.launch(launch, dataset.name));
    return btn;
  }

  static button(label, extra = "") {
    const btn = document.createElement("button");
    btn.type        = "button";
    btn.className   = `btn btn--mini${extra ? ` ${extra}` : ""}`;
    btn.textContent = label;
    return btn;
  }

  static input(label, value = "", type = "number") {
    const input = document.createElement("input");
    input.type         = type;
    input.className    = `ds-input ds-input--${type}`;
    input.placeholder  = label;
    input.spellcheck   = false;
    input.autocomplete = "off";
    input.value        = value;
    input.setAttribute("aria-label", label);
    if (type === "number") input.step = "any";
    return input;
  }

  static number(text) {
    return String(text).trim() === "" ? null : Number(text);
  }

  mount(host) {
    host.innerHTML = "";
    host.appendChild(this.root);
  }

  async load() {
    this.root.innerHTML = `<p class="ds-completer__wait">Reading the dataset&hellip;</p>`;
    try {
      this.render(await this.bridge.dataset(this.id));
    } catch (error) {
      this.root.innerHTML = "";
      this.root.appendChild(this._alert(error.message));
    }
  }

  _alert(text) {
    const alert = document.createElement("p");
    alert.className   = "ds-row__error";
    alert.textContent = text;
    alert.setAttribute("role", "alert");
    return alert;
  }

  _note(text, className) {
    const note = document.createElement("p");
    note.className   = className;
    note.textContent = text;
    return note;
  }

  render(dataset) {
    this.dataset = dataset;
    this.root.innerHTML = "";

    if (!this.compact && this.title) {
      const title = document.createElement("h3");
      title.className   = "ds-completer__title";
      title.textContent = this.title;
      this.root.appendChild(title);
    }
    if (!this.compact && dataset.origin === "run") this.root.appendChild(this._note(`${dataset.name} is a TomoVic run. The bridge never writes into run folders.`, "ds-completer__head"));
    if (dataset.state === "preparing") this.root.appendChild(this._note(`Preparing for the TomoVic tools: ${dataset.stage || "waiting"} ${DatasetWords.percent(dataset)}%`, "ds-completer__head"));

    this.keys.forEach((key) => this.root.appendChild(this._row(key)));

    if (!this.compact && dataset.origin === "import") this.root.appendChild(this._note(`Added pieces are stored in ${dataset.folder}. Your files are linked, not copied.`, "ds-completer__foot"));
  }

  _row(key) {
    const piece = this.dataset.pieces[key];
    const row   = document.createElement("div");
    const form  = document.createElement("div");

    row.className    = `ds-row${piece.present ? " is-present" : " is-missing"}`;
    row.dataset.piece = key;
    form.className   = "ds-row__form";

    if (!this.compact) {
      const head = document.createElement("div");
      head.className = "ds-row__head";
      head.innerHTML = `<span class="ds-row__label"></span><span class="ds-row__status"></span>`;
      head.querySelector(".ds-row__label").textContent  = piece.label;
      head.querySelector(".ds-row__status").textContent = DatasetWords.summary(key, piece);
      row.appendChild(head);
      if (piece.problem) row.appendChild(this._note(piece.problem, "ds-row__problem"));
    }

    row.appendChild(form);
    if (piece.addable) this._form(key, form, row);
    if (piece.launch) form.appendChild(DatasetCompleter.launchButton(this.bridge, this.dataset, piece.launch));
    if (!piece.addable && !piece.launch && piece.note) form.appendChild(this._note(piece.note, "ds-row__note"));

    const error = this._alert("");
    error.hidden = true;
    row.appendChild(error);
    return row;
  }

  _form(key, form, row) {
    const forms = {
      height_range : () => this._pairForm(form, row, key, ["low", "high"], ["lower height (m)", "upper height (m)"]),
      spacing      : () => this._pairForm(form, row, key, ["azimuth", "range"], ["azimuth spacing (m)", "range spacing (m)"]),
      channel      : () => this._channelForm(form, row),
      primary      : () => this._primaryForm(form, row),
      dem          : () => this._fileForm(form, row, key),
      geometry     : () => this._geometryForm(form, row),
      passes       : () => this._passesForm(form, row),
      polarimetry  : () => this._polarimetryForm(form, row),
      params       : () => this._paramsForm(form, row),
    };
    forms[key]();
  }

  _onEnter(inputs, submit) {
    inputs.forEach((input) => input.addEventListener("keydown", (ev) => {
      if (ev.key !== "Enter") return;
      ev.preventDefault();
      submit();
    }));
  }

  _pairForm(form, row, key, names, labels) {
    const piece  = this.dataset.pieces[key];
    const inputs = names.map((name, i) => DatasetCompleter.input(labels[i], piece.present ? String(piece.value[i]) : ""));
    const save   = DatasetCompleter.button("Save", "ds-save");
    const submit = () => this._submit(key, Object.fromEntries(names.map((name, i) => [name, DatasetCompleter.number(inputs[i].value)])), row);

    inputs.forEach((input) => form.appendChild(input));
    form.appendChild(save);
    save.addEventListener("click", submit);
    this._onEnter(inputs, submit);
  }

  _channelForm(form, row) {
    const select = document.createElement("select");
    const save   = DatasetCompleter.button("Save", "ds-save");

    select.className = "cube-mselect ds-select";
    select.setAttribute("aria-label", "Channel the TomoVic tools show");
    this.dataset.channel.choices.forEach((choice) => {
      const option = document.createElement("option");
      option.value       = String(choice);
      option.textContent = DatasetWords.channel(choice);
      select.appendChild(option);
    });
    select.value = String(this.dataset.channel.chosen);

    form.append(select, save);
    save.addEventListener("click", () => this._submit("channel", { choice: select.value === "combined" ? "combined" : Number(select.value) }, row));
  }

  async _pickInto(input, mode, title) {
    const path = await DatasetFilePicker.pick({ mode, title });
    if (path) input.value = path;
    return path;
  }

  _primaryForm(form, row) {
    const pick    = DatasetCompleter.button("Pick a .npy file", "ds-pick");
    const standin = DatasetCompleter.button("Build a stand-in from the cube", "ds-standin");

    form.append(pick, standin);
    pick.addEventListener("click", async () => {
      const path = await DatasetFilePicker.pick({ mode: "file", title: `${this.dataset.pieces.primary.label} for ${this.dataset.name}` });
      if (path) this._submit("primary", { from: "file", path }, row);
    });
    standin.addEventListener("click", () => this._submit("primary", { from: "cube" }, row));
  }

  _fileForm(form, row, key) {
    const pick = DatasetCompleter.button("Pick a .npy file", "ds-pick");

    form.appendChild(pick);
    pick.addEventListener("click", async () => {
      const path = await DatasetFilePicker.pick({ mode: "file", title: `${this.dataset.pieces[key].label} for ${this.dataset.name}` });
      if (path) this._submit(key, { path }, row);
    });
  }

  _geometryForm(form, row) {
    const copy = DatasetCompleter.button("Copy geometry from a run", "ds-geometry");

    form.appendChild(copy);
    copy.addEventListener("click", async () => {
      const run = await DatasetFilePicker.pick({ mode: "folder", title: "Copy geometry from a run" });
      if (run) this._submit("geometry", { run }, row);
    });
  }

  _pathField(form, label) {
    const input = DatasetCompleter.input(label, "", "text");
    const pick  = DatasetCompleter.button("Pick a .npy file", "ds-pick");

    pick.title = label;
    pick.addEventListener("click", () => this._pickInto(input, "file", label));
    form.append(input, pick);
    return input;
  }

  _passesForm(form, row) {
    const secondaries    = this._pathField(form, "secondaries .npy (passes x azimuth x range)");
    const interferograms = this._pathField(form, "interferograms .npy (optional)");
    const save           = DatasetCompleter.button("Save", "ds-save");
    const submit         = () => this._submit("passes", { secondaries: secondaries.value.trim(), interferograms: interferograms.value.trim() || null }, row);

    form.appendChild(save);
    save.addEventListener("click", submit);
    this._onEnter([secondaries, interferograms], submit);
  }

  _polarimetryForm(form, row) {
    const path   = this._pathField(form, "polarimetric primary .npy (3 x azimuth x range)");
    const winAz  = DatasetCompleter.input("window azimuth", "1");
    const winRg  = DatasetCompleter.input("window range", "1");
    const save   = DatasetCompleter.button("Save", "ds-save");
    const submit = () => this._submit("polarimetry", { path: path.value.trim(), window: [DatasetCompleter.number(winAz.value), DatasetCompleter.number(winRg.value)] }, row);

    winAz.step = "1";
    winRg.step = "1";
    form.append(winAz, winRg, save);
    save.addEventListener("click", submit);
    this._onEnter([path, winAz, winRg], submit);
  }

  _paramsForm(form, row) {
    const add = DatasetCompleter.button("Add a parameter run folder", "ds-params");

    form.appendChild(add);
    add.addEventListener("click", async () => {
      const path = await DatasetFilePicker.pick({ mode: "folder", title: "Add a parameter run folder" });
      if (path) this._submit("params", { path }, row);
    });
  }

  _busy(row, busy) {
    row.classList.toggle("is-busy", busy);
    row.querySelectorAll("button, input, select").forEach((el) => {
      if (busy) {
        el.dataset.wasDisabled = el.disabled ? "1" : "";
        el.disabled = true;
      } else {
        el.disabled = el.dataset.wasDisabled === "1";
      }
    });
  }

  async _submit(key, fields, row) {
    const error = row.querySelector(".ds-row__error");
    error.hidden = true;
    this._busy(row, true);

    let dataset = null;
    try {
      dataset = await this.bridge.add(this.id, key, fields);
    } catch (failure) {
      this._busy(row, false);
      error.textContent = failure.message;
      error.hidden      = false;
      return;
    }

    this._busy(row, false);
    if (this.keys.every((piece) => dataset.pieces[piece].present)) this._done(dataset);
    else this.render(dataset);
  }

  _done(dataset) {
    this.render(dataset);
    if (this.closer) this.closer();
    if (this.onDone) this.onDone(dataset);
  }
}

class DatasetPopover extends DatasetLayer {
  constructor(completer) {
    super("ds-popover", completer.title || "Add what is missing");
    this.completer = completer;

    this.root.innerHTML = `
      <button type="button" class="ds-layer__close" aria-label="Close">&times;</button>
      <div class="ds-popover__body"></div>`;
    this.root.querySelector(".ds-layer__close").addEventListener("click", () => this.close());

    completer.mount(this.root.querySelector(".ds-popover__body"));
    completer.closer = () => this.close();
  }
}

class DatasetCard extends DatasetLayer {
  static openCard = null;
  static RECENT   = 6;

  constructor(bridge, anchor, placement) {
    super("ds-card", "Current dataset");
    this.bridge    = bridge;
    this.anchor    = anchor;
    this.placement = placement;
    this.mark      = null;
    this.ignore    = [anchor];
    this.onCurrent = () => this._sync(false);
    this.onResize  = () => this._place();

    this.root.innerHTML = `
      <header class="ds-card__head">
        <div class="ds-card__heading">
          <p class="ds-card__kicker">Current dataset</p>
          <h3 class="ds-card__name"></h3>
        </div>
        <button type="button" class="ds-layer__close" aria-label="Close">&times;</button>
      </header>
      <div class="ds-card__body"></div>
      <section class="ds-card__section">
        <h4 class="ds-card__h">Recent datasets</h4>
        <ul class="ds-recent"></ul>
      </section>
      <footer class="ds-card__foot">
        <button type="button" class="btn btn--mini ds-card__results">Open folder in Results</button>
      </footer>`;

    this.nameEl    = this.root.querySelector(".ds-card__name");
    this.bodyEl    = this.root.querySelector(".ds-card__body");
    this.recentEl  = this.root.querySelector(".ds-recent");
    this.resultsEl = this.root.querySelector(".ds-card__results");

    this.root.querySelector(".ds-layer__close").addEventListener("click", () => this.close());
    this.resultsEl.addEventListener("click", () => this._openResults());
  }

  static toggle(bridge, anchor, placement) {
    const open = DatasetCard.openCard;
    if (open) open.close();
    if (open && open.anchor === anchor) return;

    DatasetCard.openCard = new DatasetCard(bridge, anchor, placement);
    DatasetCard.openCard.open();
  }

  open() {
    this.show();
    this.bridge.on("current", this.onCurrent);
    this.bridge.on("dataset", this.onCurrent);
    window.addEventListener("resize", this.onResize);
    this.onClosed = () => {
      this.bridge.off("current", this.onCurrent);
      this.bridge.off("dataset", this.onCurrent);
      window.removeEventListener("resize", this.onResize);
      if (DatasetCard.openCard === this) DatasetCard.openCard = null;
    };
    this._sync(true);
  }

  _current() {
    return this.bridge.state ? this.bridge.state.current : null;
  }

  _sync(force) {
    const current = this._current();
    const mark    = current ? `${current.id}|${current.revision}|${current.state}` : "";
    if (!force && mark === this.mark) return;

    this.mark = mark;
    this._render(current);
    this._loadRecent();
    this._place();
  }

  _fact(list, term, text) {
    const dt = document.createElement("dt");
    const dd = document.createElement("dd");
    dt.textContent = term;
    dd.textContent = text;
    list.append(dt, dd);
  }

  _render(current) {
    this.bodyEl.innerHTML = "";
    this.nameEl.textContent  = current ? current.name : "None";
    this.resultsEl.hidden    = !current;

    if (!current) {
      this.bodyEl.appendChild(this._text(DatasetIndicator.EMPTY, "ds-card__empty"));
      return;
    }

    const facts = document.createElement("dl");
    facts.className = "ds-card__facts";
    this._fact(facts, "Folder", current.folder);
    this._fact(facts, "Source", current.source.path);
    this._fact(facts, "Origin", current.origin_label);
    if (current.cube) this._fact(facts, "Cube", `${current.cube.shape.join(" x ")} ${current.cube.dtype}, ${DatasetWords.bytes(current.cube.bytes)}`);
    this._fact(facts, "State", current.state === "error" ? `Error: ${current.error}` : DatasetWords.chip(current));
    this.bodyEl.appendChild(facts);

    this.bodyEl.appendChild(this._piecesSection(current));
    this.bodyEl.appendChild(this._toolsSection(current));
  }

  _text(text, className) {
    const p = document.createElement("p");
    p.className   = className;
    p.textContent = text;
    return p;
  }

  _section(title) {
    const section = document.createElement("section");
    const head    = document.createElement("h4");
    section.className = "ds-card__section";
    head.className    = "ds-card__h";
    head.textContent  = title;
    section.appendChild(head);
    return section;
  }

  _piecesSection(dataset) {
    const section = this._section("Pieces");
    const list    = document.createElement("ul");
    list.className = "ds-pieces";
    Object.keys(dataset.pieces).forEach((key) => list.appendChild(this._pieceRow(dataset, key)));
    section.appendChild(list);
    return section;
  }

  _actionLabel(key, piece) {
    if (key === "primary" && piece.present && piece.value.kind === "stand-in") return "Replace with the primary SLC";
    return piece.present ? "Change" : "Add";
  }

  _pieceRow(dataset, key) {
    const piece   = dataset.pieces[key];
    const row     = document.createElement("li");
    const actions = document.createElement("span");
    const form    = document.createElement("div");

    row.className     = `ds-piece${piece.present ? " is-present" : " is-missing"}`;
    row.dataset.piece = key;
    row.innerHTML     = `<span class="ds-piece__mark" aria-hidden="true"></span><span class="ds-piece__label"></span><span class="ds-piece__value"></span>`;
    row.querySelector(".ds-piece__label").textContent = piece.label;
    row.querySelector(".ds-piece__value").textContent = DatasetWords.summary(key, piece);
    actions.className = "ds-piece__actions";
    form.className    = "ds-piece__form";
    form.hidden       = true;
    row.appendChild(actions);
    if (piece.problem) row.appendChild(this._text(piece.problem, "ds-row__problem"));
    if (piece.present && piece.note) row.appendChild(this._text(piece.note, "ds-tool__note"));
    row.appendChild(form);

    if (piece.addable && dataset.state !== "error") {
      const toggle = DatasetCompleter.button(this._actionLabel(key, piece), "ds-piece__toggle");
      toggle.addEventListener("click", () => this._toggleForm(dataset, key, form));
      actions.appendChild(toggle);
    } else if (piece.launch) {
      actions.appendChild(DatasetCompleter.launchButton(this.bridge, dataset, piece.launch));
    }
    return row;
  }

  _toggleForm(dataset, key, form) {
    form.hidden = !form.hidden;
    if (form.hidden) {
      form.innerHTML = "";
      this._place();
      return;
    }

    const completer = new DatasetCompleter(this.bridge, dataset.id, [key], { compact: true });
    completer.mount(form);
    completer.render(dataset);
    this._place();
  }

  _toolsSection(dataset) {
    const section = this._section("TomoVic tools");
    const keys    = Object.keys(dataset.tools);
    section.appendChild(this._toolList(dataset, keys.filter((key) => !key.startsWith("tomovis"))));

    const head = document.createElement("h4");
    head.className   = "ds-card__h";
    head.textContent = "TomoVis";
    section.appendChild(head);
    section.appendChild(this._toolList(dataset, keys.filter((key) => key.startsWith("tomovis"))));
    return section;
  }

  _toolStatus(dataset, tool) {
    if (tool.ready) return "Ready";
    if (tool.missing.length) return `needs ${DatasetWords.labels(dataset, tool.missing)}`;
    return tool.note ? "" : "not ready yet";
  }

  _toolList(dataset, keys) {
    const list = document.createElement("ul");
    list.className = "ds-tools";

    keys.forEach((key) => {
      const tool = dataset.tools[key];
      const row  = document.createElement("li");
      row.className    = `ds-tool${tool.ready ? " is-ready" : ""}`;
      row.dataset.tool = key;
      row.innerHTML    = `<span class="ds-tool__label"></span><span class="ds-tool__status"></span>`;
      row.querySelector(".ds-tool__label").textContent  = tool.label;
      row.querySelector(".ds-tool__status").textContent = this._toolStatus(dataset, tool);
      if (tool.note) row.appendChild(this._text(tool.note, "ds-tool__note"));
      list.appendChild(row);
    });
    return list;
  }

  async _loadRecent() {
    let payload = null;
    try {
      payload = await this.bridge.datasets(ResultsSources.runs());
    } catch (error) {
      this.recentEl.innerHTML = "";
      const item = document.createElement("li");
      item.className   = "ds-row__error";
      item.textContent = error.message;
      item.setAttribute("role", "alert");
      this.recentEl.appendChild(item);
      return;
    }

    this.recentEl.innerHTML = "";
    payload.datasets.slice(0, DatasetCard.RECENT).forEach((dataset) => this.recentEl.appendChild(this._recentRow(dataset, payload.current_id)));
    if (!payload.datasets.length) this.recentEl.appendChild(this._text("No dataset was opened yet.", "ds-card__empty"));
    this._place();
  }

  _recentRow(dataset, currentId) {
    const row = document.createElement("li");
    row.className  = `ds-recent__row${dataset.id === currentId ? " is-current" : ""}`;
    row.title      = dataset.id;
    row.innerHTML  = `<span class="ds-recent__name"></span><span class="ds-recent__origin"></span><span class="ds-recent__state"></span>`;
    row.querySelector(".ds-recent__name").textContent   = dataset.name;
    row.querySelector(".ds-recent__origin").textContent = dataset.origin_label;
    row.querySelector(".ds-recent__state").textContent  = dataset.id === currentId ? "current" : DatasetWords.chip(dataset);

    if (dataset.id !== currentId) {
      const use = DatasetCompleter.button("Use", "ds-use");
      use.addEventListener("click", () => this.bridge.use(dataset.id).catch((error) => Toast.show(error.message, "error")));
      row.appendChild(use);
    }
    return row;
  }

  _openResults() {
    const current = this._current();
    this.close();
    if (current) this.bridge.openIn("results", current.folder);
  }

  _place() {
    if (!this.root.isConnected) return;

    const margin = 12;
    const rect   = this.anchor.getBoundingClientRect();
    const box    = this.root.getBoundingClientRect();
    let   left   = rect.left;
    let   top    = rect.bottom + 8;

    if (this.placement === "right") {
      left = this.anchor.closest(".ds-indicator").getBoundingClientRect().right + 18;
      top  = rect.bottom - box.height;
    } else if (top + box.height > innerHeight - margin) {
      top = rect.top - 8 - box.height;
    }

    this.root.style.left = `${Math.max(margin, Math.min(left, innerWidth - box.width - margin))}px`;
    this.root.style.top  = `${Math.max(margin, Math.min(top, innerHeight - box.height - margin))}px`;
  }
}

class DatasetIndicator {
  static EMPTY = "No current dataset. Open a run in Cube or import a file in TomoVis.";
  static LINKS = [["cube", "Open in Cube"], ["slices", "Open in Slices"], ["tomovis", "Open in TomoVis"]];

  constructor(bridge, host, { variant, page = null }) {
    this.bridge  = bridge;
    this.host    = host;
    this.variant = variant;
    this.page    = page;
    this.notice  = null;
    this.state   = null;

    this.root = document.createElement("div");
    this.root.className = `ds-indicator ds-indicator--${variant}`;
    this.root.innerHTML = [
      `<span class="ds-indicator__dot" aria-hidden="true"></span>`,
      `<span class="ds-indicator__label">Current dataset</span>`,
      `<span class="ds-indicator__name"></span>`,
      `<span class="ds-indicator__origin"></span>`,
      `<span class="ds-indicator__state"></span>`,
      `<span class="ds-indicator__links"></span>`,
      `<span class="ds-indicator__notice" hidden></span>`,
    ].join("");

    this.nameEl   = this.root.querySelector(".ds-indicator__name");
    this.originEl = this.root.querySelector(".ds-indicator__origin");
    this.stateEl  = this.root.querySelector(".ds-indicator__state");
    this.linksEl  = this.root.querySelector(".ds-indicator__links");
    this.noticeEl = this.root.querySelector(".ds-indicator__notice");

    this.links   = DatasetIndicator.LINKS.filter(([tool]) => tool !== page).map(([tool, label]) => this._link(label, { open: tool }, () => this._open(tool)));
    this.details = this._link("Details", { details: "" }, () => DatasetCard.toggle(this.bridge, this.details, variant === "nav" ? "right" : "below"));

    host.appendChild(this.root);
  }

  _link(label, data, run) {
    const btn = document.createElement("button");
    btn.type        = "button";
    btn.className   = "ds-link";
    btn.textContent = label;
    Object.entries(data).forEach(([key, value]) => { btn.dataset[key] = value; });
    btn.addEventListener("click", () => run());
    this.linksEl.appendChild(btn);
    return btn;
  }

  _open(tool) {
    const current = this.state && this.state.current;
    if (!current) return;
    this.bridge.openIn(tool, current.id).catch((error) => Toast.show(error.message, "error"));
  }

  setNotice(notice) {
    this.notice = notice;
    this._paintNotice();
  }

  render(state) {
    const current = state ? state.current : null;
    const here    = this.page || this.bridge.route;

    this.state = state;
    this.root.dataset.tone = current ? DatasetWords.tone(current) : "empty";
    this.root.classList.toggle("is-empty", !current);

    this.nameEl.textContent   = current ? current.name : (state ? DatasetIndicator.EMPTY : "");
    this.nameEl.title         = current ? current.id : "";
    this.originEl.textContent = current ? current.origin_label : "";
    this.stateEl.textContent  = current ? DatasetWords.chip(current) : "";
    this.stateEl.title        = current && current.state === "error" ? current.error : "";
    this.originEl.hidden      = !current;
    this.stateEl.hidden       = !current;
    this.linksEl.hidden       = !current;
    this.links.forEach((btn) => { btn.hidden = btn.dataset.open === here; });

    this._paintNotice();
  }

  _fallbackNotice() {
    const current = this.state ? this.state.current : null;
    if (this.bridge.failure) return { text: `The console did not answer: ${this.bridge.failure}`, actions: [] };
    if (this.state && this.state.bridge_error) return { text: this.state.bridge_error, actions: [] };
    if (current && current.state === "error") return { text: current.error, actions: [] };
    return null;
  }

  _paintNotice() {
    const notice = this.notice || this._fallbackNotice();
    this.noticeEl.innerHTML = "";
    this.noticeEl.hidden    = !notice;
    if (!notice) return;

    const text = document.createElement("span");
    text.className   = "ds-indicator__text";
    text.textContent = notice.text;
    text.title       = notice.text;
    this.noticeEl.appendChild(text);

    (notice.actions || []).forEach((action) => {
      const btn = document.createElement("button");
      btn.type        = "button";
      btn.className   = "ds-link ds-link--action";
      btn.textContent = action.label;
      btn.addEventListener("click", () => Promise.resolve().then(() => action.run()).catch((error) => Toast.show(error.message, "error")));
      this.noticeEl.appendChild(btn);
    });
  }
}

class DatasetBridge {
  static ROOT    = "/api/workspace";
  static POLL_MS = 500;

  constructor() {
    this.handlers     = { current: new Set(), dataset: new Set() };
    this.indicators   = [];
    this.navIndicator = null;
    this.state        = null;
    this.key          = null;
    this.announced    = null;
    this.seq          = 0;
    this.applied      = 0;
    this.route        = null;
    this.failure      = "";
    this.pollTimer    = null;

    window.addEventListener("focus", () => this.refresh());
    document.addEventListener("visibilitychange", () => {
      if (document.visibilityState === "visible") this.refresh();
    });
  }

  static sleep(ms) {
    return new Promise((resolve) => setTimeout(resolve, ms));
  }

  on(topic, handler) {
    this.handlers[topic].add(handler);
  }

  off(topic, handler) {
    this.handlers[topic].delete(handler);
  }

  _emit(topic, payload) {
    [...this.handlers[topic]].forEach((handler) => handler(payload));
  }

  async _get(path) {
    const data = await Api.get(`${DatasetBridge.ROOT}/${path}`);
    if (data.error || data.ok === false) throw new DatasetBridgeError(data.error, data.piece || null);
    return data;
  }

  async _post(path, body) {
    const data = await Api.post(`${DatasetBridge.ROOT}/${path}`, body);
    if (!data.ok) throw new DatasetBridgeError(data.error, data.piece || null);
    return data;
  }

  _key(state) {
    const current = state.current;
    return [state.serial, state.set_by, current ? current.id : "", current ? current.revision : "", current ? current.state : "", state.bridge_error].join("|");
  }

  _paint() {
    this.indicators.forEach((indicator) => indicator.render(this.state));
  }

  _schedulePoll() {
    const current = this.state ? this.state.current : null;
    if (!current || current.state !== "preparing" || this.pollTimer) return;
    this.pollTimer = setTimeout(() => {
      this.pollTimer = null;
      this.refresh();
    }, DatasetBridge.POLL_MS);
  }

  _announce(dataset) {
    const mark = `${dataset.id}|${dataset.revision}|${dataset.state}`;
    if (mark === this.announced) return;
    this.announced = mark;
    this._emit("dataset", { dataset });
  }

  _apply(state, seq, force = false) {
    if (seq < this.applied) return;

    const previous = this.state ? this.state.current : null;
    const key      = this._key(state);
    const changed  = force || key !== this.key;

    this.applied = seq;
    this.state   = state;
    this.key     = key;
    this.failure = "";
    this._paint();
    this._schedulePoll();
    if (!changed) return;

    this._emit("current", { state });
    if (previous && state.current && previous.id === state.current.id && previous.revision !== state.current.revision) this._announce(state.current);
  }

  _fail(error) {
    this.failure = error.message;
    this._paint();
  }

  async current(sid = null) {
    const seq   = ++this.seq;
    const state = await this._get(`current${sid ? `?sid=${encodeURIComponent(sid)}` : ""}`);
    this._apply(state, seq);
    return state;
  }

  refresh() {
    return this.current().catch((error) => this._fail(error));
  }

  async dataset(id) {
    return (await this._get(`dataset?id=${encodeURIComponent(id)}`)).dataset;
  }

  async datasets(base = "") {
    return this._get(`datasets?base=${encodeURIComponent(base)}`);
  }

  async stripEntries(base) {
    try {
      const payload = await this.datasets(base);
      return { entries: payload.datasets.filter((dataset) => !dataset.under_base).map((dataset) => dataset.strip), datasets: payload.datasets, error: "" };
    } catch (error) {
      return { entries: [], datasets: [], error: error.message };
    }
  }

  async use(id) {
    const answer = await this._post("current", { id });
    const seq    = ++this.seq;
    const before = this.state || { workspace: "", bridge_error: "" };
    this._apply({ ok: true, workspace: before.workspace, serial: answer.serial, set_by: answer.set_by, current: answer.current, bridge_error: before.bridge_error }, seq, true);
    return answer;
  }

  async add(id, piece, fields) {
    const answer = await this._post("add", { id, piece, ...fields });
    this._announce(answer.dataset);
    if (this.state && this.state.current && this.state.current.id === id) await this.refresh();
    return answer.dataset;
  }

  async waitReady(id, onProgress = null) {
    let dataset = await this.dataset(id);
    while (dataset.state === "preparing") {
      if (onProgress) onProgress(dataset);
      await DatasetBridge.sleep(DatasetBridge.POLL_MS);
      dataset = await this.dataset(id);
    }
    return dataset;
  }

  async openIn(tool, id) {
    if (tool === "results") {
      window.app.resultsView.showFolder(id);
      window.router.go("results");
      return;
    }
    await this.use(id);
    window.router.go(tool);
  }

  launch(launch, name) {
    window.app.launchView.pendingImport = { name, script: launch.script, overrides: launch.overrides };
    if (window.location.hash === `#/launch/${launch.script}`) window.app.launchView.show(launch.script);
    else window.router.go(`launch/${launch.script}`);
  }

  complete(id, pieceKeys, { host = null, title = "", onDone = null, compact = false, dataset = null } = {}) {
    const completer = new DatasetCompleter(this, id, pieceKeys, { title, onDone, compact });
    if (host) completer.mount(host);
    else new DatasetPopover(completer).show();

    if (dataset) completer.render(dataset);
    else completer.load();
    return completer;
  }

  mountIndicator(host, { variant, page = null }) {
    const indicator = new DatasetIndicator(this, host, { variant, page });
    this.indicators.push(indicator);
    if (variant === "nav") this.navIndicator = indicator;
    indicator.render(this.state);
    return indicator;
  }

  routed(route) {
    this.route = route;
    this._paint();
    this.refresh();
  }
}

window.DatasetBridge      = DatasetBridge;
window.DatasetBridgeError = DatasetBridgeError;
window.DatasetWords       = DatasetWords;
window.DatasetIndicator   = DatasetIndicator;
window.DatasetCard        = DatasetCard;
window.DatasetCompleter   = DatasetCompleter;
window.DatasetFilePicker  = DatasetFilePicker;
