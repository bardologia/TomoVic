"use strict";

class ConfigForm {
  static TYPE_REFRESH_MS = 120;

  constructor() {
    this.dirty         = {};
    this.controls      = {};
    this.dependents    = {};
    this.states        = [];
    this.gates         = [];
    this.repainters    = [];
    this.sections      = [];
    this.pairs         = [];
    this.pairBase      = new Map();
    this.byPath        = new Map();
    this.activeSection = null;
    this.query         = "";
    this._section      = null;
    this.config        = null;
    this.layoutEl      = null;
    this.navHost       = null;
    this.pinsEl        = null;
    this.nomatchEl     = null;
    this.countEl       = null;
    this.refreshTimer  = null;
    this.shellCache    = new Map();
  }

  _buildToolbar(cfg) {
    const bar = document.createElement("div");
    bar.className = "cfg-toolbar";

    const search = document.createElement("input");
    search.className = "cfg-search";
    search.type = "search";
    search.placeholder = `Filter ${cfg.leaves.length} fields...`;
    search.spellcheck = false;
    search.addEventListener("input", () => {
      this.query = search.value.trim().toLowerCase();
      this._applyVisibility();
    });

    const count = document.createElement("span");
    count.className = "cfg-toolbar__count";
    this.countEl = count;

    const reset = document.createElement("button");
    reset.className = "btn btn--mini";
    reset.textContent = "Reset all";
    reset.addEventListener("click", () => this._resetAll());

    bar.appendChild(search);
    bar.appendChild(count);

    bar.appendChild(reset);
    return bar;
  }

  applyRunConfig(values) {
    const changed = [];
    const skipped = [];
    const locked  = [];

    this.dirty = {};

    Object.entries(values).forEach(([path, value]) => {
      const leaf = this.byPath.get(path);
      if (!leaf) {
        skipped.push(path);
        return;
      }
      if (value === leaf.value) return;
      if (!leaf.editable) {
        locked.push(path);
        return;
      }
      this.dirty[path] = value;
      changed.push([path, value]);
    });

    Object.values(this.controls).forEach((c) => c.reset());
    changed.forEach(([path, value]) => this._fireDependents(path, value));
    this._refresh();

    return { applied: changed.length, skipped, locked };
  }

  _buildPins(pinned) {
    const panel = document.createElement("section");
    panel.className = "launch-pins";

    const head = document.createElement("header");
    head.className = "launch-pins__head";
    head.innerHTML = `<h3 class="launch-pins__name">Run essentials</h3><span class="launch-pins__hint">check these before every launch</span>`;

    const grid = document.createElement("div");
    grid.className = "launch-pins__grid";
    pinned.forEach((leaf) => grid.appendChild(this._buildRow(leaf, "essentials", true)));

    panel.appendChild(head);
    panel.appendChild(grid);
    this.pinsEl = panel;
    return panel;
  }

  _renderLayout(host, cfg) {
    const layout = cfg.layout;
    this.byPath  = new Map(cfg.leaves.map((leaf) => [leaf.path, leaf]));

    this.shellCache.clear();

    const wrap = document.createElement("div");
    wrap.className = "launch-layout";
    if (layout.mode === "single") wrap.classList.add("launch-layout--single");
    this.layoutEl = wrap;

    const nav = document.createElement("nav");
    nav.className = "secnav";
    nav.setAttribute("aria-label", "Configuration sections");
    this.navHost = nav;

    const main = document.createElement("div");
    main.className = "secmain";

    const declared = [];
    if (layout.essentials.length) {
      declared.push({ key: "essentials", title: "Essentials", panels: null });
    }
    layout.sections.forEach((section) => declared.push(section));

    declared.forEach((section) => {
      this._section = section.key;

      const el = document.createElement("section");
      el.className = "launch-section";
      el.dataset.section = section.key;

      const title = document.createElement("h3");
      title.className = "launch-section__title";
      title.textContent = section.title;
      el.appendChild(title);

      const body = document.createElement("div");
      body.className = "launch-section__body";
      el.appendChild(body);

      if (section.panels === null) {
        body.appendChild(this._buildPins(layout.essentials.map((entry) => this.byPath.get(entry.path))));
      } else {
        section.panels.forEach((panel) => {
          const built = this._buildPanel(panel);
          if (built) body.appendChild(built);
        });
      }

      const record = { key: section.key, title: section.title, when: section.when || null, el, navBtn: null, badge: null };

      if (layout.mode === "sections") {
        const btn = document.createElement("button");
        btn.type = "button";
        btn.className = "secnav__item";
        const badge = document.createElement("span");
        badge.className = "edit-badge";
        badge.hidden = true;
        btn.innerHTML = `<span class="secnav__name">${section.title}</span>`;
        btn.appendChild(badge);
        btn.addEventListener("click", () => this._navigate(record.key));
        record.navBtn = btn;
        record.badge = badge;
        nav.appendChild(btn);
      }

      main.appendChild(el);
      this.sections.push(record);
    });

    wrap.appendChild(main);
    if (layout.mode === "sections") wrap.appendChild(nav);

    const empty = document.createElement("p");
    empty.className = "cfg-note launch-nomatch";
    empty.textContent = "No fields match this filter.";
    empty.hidden = true;
    this.nomatchEl = empty;
    main.appendChild(empty);

    host.appendChild(wrap);
    this._setActiveSection(this.activeSection || this.sections[0].key);
  }

  _buildPanel(panel) {
    if (panel.kind === "hidden") return null;
    if (panel.kind === "special") return this._buildSpecialPanel(panel);
    if (panel.kind === "pair") return this._buildPairPanel(panel);
    return this._buildFieldsPanel(panel);
  }

  _buildSpecialPanel(panel) {
    return this._buildPathsPanel(panel.panel, panel.fields);
  }

  _buildPathsPanel(title, paths) {
    const groups = [{ title: null, fields: paths.map((path) => ({ path })) }];
    return this._buildFieldsPanel({ kind: "fields", title, groups });
  }

  _buildFieldsPanel(panel) {
    const el = document.createElement("section");
    el.className = "cfg-panel";
    el.dataset.cols = String(Math.min(panel.groups.length, 4));

    if (panel.title) {
      const head = document.createElement("header");
      head.className = "cfg-panel__head";
      head.innerHTML = `<h4 class="cfg-panel__name">${panel.title}</h4>`;
      el.appendChild(head);
    }

    if (panel.note) el.appendChild(this._buildPanelNote(panel.note));

    el.appendChild(this._buildGroups(panel.groups));
    return el;
  }

  _buildPanelNote(text) {
    const note = document.createElement("p");
    note.className = "cfg-panel__note";
    note.textContent = text;
    return note;
  }

  _buildGroups(groups, pathMap = null) {
    const body = document.createElement("div");
    body.className = "cfg-panel__groups";

    groups.forEach((group) => {
      const groupEl = document.createElement("div");
      groupEl.className = "field-group";
      if (group.title) {
        const heading = document.createElement("div");
        heading.className = "field-group__title";
        heading.textContent = group.title;
        groupEl.appendChild(heading);
      }
      const inner = document.createElement("div");
      inner.className = "field-group__grid";
      group.fields.forEach((entry) => this._buildEntry(entry, inner, pathMap));
      groupEl.appendChild(inner);
      body.appendChild(groupEl);
    });

    return body;
  }

  _mapPath(path, pathMap) {
    return pathMap ? pathMap.override + path.slice(pathMap.base.length) : path;
  }

  _buildEntry(entry, host, pathMap) {
    if (entry.gateOn) {
      this._buildValueGate(entry, host, pathMap);
      return;
    }

    if (!entry.gate) {
      host.appendChild(this._buildRow(this.byPath.get(this._mapPath(entry.path, pathMap)), this._section));
      return;
    }

    const lead = this.byPath.get(this._mapPath(entry.gate, pathMap));
    const cell = document.createElement("div");
    cell.className = "band-block";

    cell.appendChild(this._buildGateRow(lead, this._gateLabel(this._shortName(lead))));

    const gatedRows = [];
    entry.fields.forEach((sub) => {
      const leaf = this.byPath.get(this._mapPath(sub.path, pathMap));
      const short = this._shortName(leaf);
      const row = short.startsWith("weight_") ? this._buildWeightRow(leaf) : this._buildRow(leaf, this._section);
      row.classList.add("cfg-edit__row--dependent");
      cell.appendChild(row);
      gatedRows.push(this.states[this.states.length - 1]);
    });

    this.gates.push({ leaf: lead, states: gatedRows });
    host.appendChild(cell);
  }

  _buildValueGate(entry, host, pathMap) {
    const condition = { ...entry.gateOn, field: this._mapPath(entry.gateOn.field, pathMap) };
    const lead      = this.byPath.get(condition.field);

    const start = this.states.length;
    entry.fields.forEach((sub) => this._buildEntry(sub, host, pathMap));

    const states = this.states.slice(start);
    states.forEach(({ row }) => row.classList.add("cfg-edit__row--dependent"));

    this.gates.push({ leaf: lead, states, test: () => !this._conditionFails(condition) });
  }

  _gateLabel(short) {
    if (short.startsWith("use_")) return short.slice(4);
    if (short !== "enabled" && short.endsWith("_enabled")) return short.slice(0, -"_enabled".length);
    return short;
  }

  _shortName(leaf) {
    return leaf.section ? leaf.path.slice(leaf.section.length + 1) : leaf.path;
  }

  _buildPairPanel(panel) {
    const el = document.createElement("section");
    el.className = "cfg-panel cfg-panel--pair";

    const head = document.createElement("header");
    head.className = "cfg-panel__head";
    head.innerHTML = `<h4 class="cfg-panel__name">${panel.title}</h4><span class="cfg-panel__hint">${panel.base} · overridden per-field by ${panel.override}</span>`;
    el.appendChild(head);

    if (panel.note) el.appendChild(this._buildPanelNote(panel.note));

    el.appendChild(this._buildGroups(panel.groups));

    const override = document.createElement("div");
    override.className = "pair-override";

    const toggle = document.createElement("button");
    toggle.type = "button";
    toggle.className = "pair-override__head";
    toggle.setAttribute("aria-expanded", "false");
    const badge = document.createElement("span");
    badge.className = "edit-badge";
    toggle.innerHTML = `<span class="pair-override__chev">&rsaquo;</span><h4 class="pair-override__name">${panel.override} overrides</h4>`;
    toggle.appendChild(badge);

    const note = document.createElement("p");
    note.className = "pair-override__note";
    note.textContent = `Fields where both stages share a default inherit ${panel.base} edits; editing here pins the ${panel.override} value.`;

    const startAt = this.states.length;
    const body = this._buildGroups(panel.groups, { base: panel.base, override: panel.override });
    body.classList.add("pair-override__body");
    body.hidden = true;

    const record = { base: panel.base, override: panel.override, badge, body, toggle, container: override, open: false, states: this.states.slice(startAt) };

    const inheritPath = panel.base.split(".").slice(0, -1).concat("inherit").join(".");
    record.states.forEach(({ leaf }) => {
      this.pairBase.set(leaf.path, { base: panel.base + leaf.path.slice(panel.override.length), inherit: inheritPath });
    });
    toggle.addEventListener("click", () => {
      record.open = !record.open;
      this._applyVisibility();
    });
    this.pairs.push(record);

    override.appendChild(toggle);
    override.appendChild(note);
    override.appendChild(body);
    el.appendChild(override);
    return el;
  }

  _buildRow(leaf, sectionKey, pinned = false) {
    const short = this._shortName(leaf);

    const row = document.createElement("div");
    row.className = "cfg-edit__row";
    row.title = `--${leaf.path}`;

    const label = document.createElement("div");
    label.className = "cfg-edit__name";
    label.textContent = short;
    label.title = `${leaf.type} · --${leaf.path}`;
    row.appendChild(label);

    let control;
    const spec    = leaf.editable ? this._widgetSpec(leaf) : null;
    const kind    = spec ? spec.kind : null;
    const choices = Array.isArray(leaf.choices) && leaf.choices.length ? leaf.choices : (kind === "choice" ? spec.options : null);
    if (kind === "multi" && window.MultiValueField) {
      control = new window.MultiValueField(this, leaf, spec).build();
      row.classList.add("cfg-edit__row--board");
    } else if (kind === "dataset" && window.DatasetPicker) {
      control = new window.DatasetPicker(this, leaf, spec).build();
      row.classList.add(spec.multi ? "cfg-edit__row--board" : "cfg-edit__row--wide");
    } else if (choices) {
      control = this._choiceControl(leaf, choices, spec ? spec.default_label : null);
      row.classList.add("cfg-edit__row--choice");
    } else if (!leaf.editable) {
      control = this._textControl(leaf);
      control.input.disabled = true;
      control.input.classList.add("is-locked");
      control.input.title = "not overridable from the command line";
    } else if (leaf.type === "bool") {
      control = this._switchControl(leaf);
      row.classList.add("cfg-edit__row--bool");
    } else if (leaf.type === "int" || leaf.type === "float") {
      control = new window.NumberField(this, leaf, short, kind === "number" ? spec : null).build();
      row.classList.add("cfg-edit__row--num");
    } else {
      control = this._textControl(leaf);
    }

    row.appendChild(control.el);
    this.controls[leaf.path] = { leaf, reset: control.reset, input: control.input, setInactive: control.setInactive };
    this.states.push({ leaf, row, sectionKey: sectionKey !== undefined ? sectionKey : this._section, pinned });
    return row;
  }

  _buildGateRow(lead, label) {
    const row = document.createElement("div");
    row.className = "cfg-edit__row cfg-edit__row--bool cfg-edit__row--gate";
    row.title = `--${lead.path}`;

    const name = document.createElement("div");
    name.className = "cfg-edit__name";
    name.textContent = label;
    row.appendChild(name);

    const toggle = this._switchControl(lead);
    row.appendChild(toggle.el);
    this.controls[lead.path] = { leaf: lead, reset: toggle.reset, input: toggle.input };
    this.states.push({ leaf: lead, row, sectionKey: this._section });
    return row;
  }

  _buildWeightRow(weight) {
    const row = document.createElement("div");
    row.className = "cfg-edit__row cfg-edit__row--dependent cfg-edit__row--gateweight";
    row.title = `--${weight.path}`;

    const name = document.createElement("div");
    name.className = "cfg-edit__name";
    name.textContent = "weight";
    row.appendChild(name);

    const control = this._numberControl(weight);
    control.input.title = `--${weight.path}`;
    row.appendChild(control.input);

    this.controls[weight.path] = { leaf: weight, reset: control.reset, input: control.input };
    this.states.push({ leaf: weight, row, sectionKey: this._section });
    return row;
  }

  _widgetSpec(leaf) {
    if (!this.config || !this.config.layout) return null;
    return this.config.layout.widgets[leaf.path] || null;
  }

  _effective(leaf) {
    if (this.dirty[leaf.path] !== undefined) return this.dirty[leaf.path];
    const inherited = this._inherited(leaf);
    return inherited !== undefined ? inherited : leaf.value;
  }

  _inherited(leaf) {
    if (!this.pairBase || this.dirty[leaf.path] !== undefined) return undefined;

    const link = this.pairBase.get(leaf.path);
    if (!link) return undefined;

    const inheritLeaf = this.byPath.get(link.inherit);
    if (inheritLeaf && (this.dirty[link.inherit] !== undefined ? this.dirty[link.inherit] : inheritLeaf.value) !== "True") return undefined;

    const base = this.byPath.get(link.base);
    if (!base || leaf.value !== base.value) return undefined;

    return this.dirty[link.base];
  }

  _leafByPath(path) {
    return this.byPath.get(path) || null;
  }

  _choiceControl(leaf, choices, defaultLabel = null) {
    const select = document.createElement("select");
    select.className = "cfg-edit__input picker__select";

    const current   = String(leaf.value);
    const effective = String(this._effective(leaf));
    const options   = [...new Set([current, effective, ...choices].filter((value) => choices.includes(value) || value === current || value === effective))];
    options.forEach((value) => {
      const opt = document.createElement("option");
      opt.value = value;
      opt.textContent = value === "default" && defaultLabel ? defaultLabel : value;
      select.appendChild(opt);
    });
    select.value = effective;
    select.classList.toggle("is-dirty", this.dirty[leaf.path] !== undefined);

    select.addEventListener("change", () => {
      select.classList.toggle("is-dirty", select.value !== leaf.value);
      this._setValue(leaf, select.value);
      this._fireDependents(leaf.path, select.value);
    });

    const reset = () => {
      select.value = String(this._effective(leaf));
      select.classList.toggle("is-dirty", this.dirty[leaf.path] !== undefined);
    };
    return { el: select, input: select, reset };
  }

  _onDependency(path, fn) {
    (this.dependents[path] = this.dependents[path] || []).push(fn);
  }

  _fireDependents(path, value) {
    (this.dependents[path] || []).forEach((fn) => fn(value));
  }

  _setValue(leaf, value, defer) {
    const changed = value !== leaf.value || this._inherited(leaf) !== undefined;
    if (changed) this.dirty[leaf.path] = value;
    else delete this.dirty[leaf.path];
    this._runRefresh(defer);
  }

  _unsetValue(leaf, defer) {
    delete this.dirty[leaf.path];
    this._runRefresh(defer);
  }

  _runRefresh(defer) {
    clearTimeout(this.refreshTimer);
    if (!defer) {
      this.refreshTimer = null;
      this._refresh();
      return;
    }
    this.refreshTimer = setTimeout(() => this._refresh(), ConfigForm.TYPE_REFRESH_MS);
  }

  _textControl(leaf) {
    const input = document.createElement("input");
    input.className = "cfg-edit__input";
    input.value = this._effective(leaf);
    input.spellcheck = false;
    input.classList.toggle("is-dirty", this.dirty[leaf.path] !== undefined);
    input.addEventListener("input", () => {
      input.classList.toggle("is-dirty", input.value !== leaf.value);
      this._setValue(leaf, input.value, true);
      this._fireDependents(leaf.path, input.value);
    });
    const reset = () => {
      input.value = this._effective(leaf);
      input.classList.toggle("is-dirty", this.dirty[leaf.path] !== undefined);
    };
    return { el: input, input, reset };
  }

  _numberControl(leaf) {
    const input = document.createElement("input");
    input.className = "cfg-edit__input";
    input.type = "number";
    input.step = leaf.type === "int" ? "1" : "any";
    input.value = this._effective(leaf);
    input.spellcheck = false;
    input.classList.toggle("is-dirty", this.dirty[leaf.path] !== undefined);
    input.addEventListener("input", () => this.applyTypedInput(leaf, input));
    const reset = () => {
      input.value = this._effective(leaf);
      input.classList.toggle("is-dirty", this.dirty[leaf.path] !== undefined);
      input.classList.remove("is-invalid");
    };
    return { el: input, input, reset };
  }

  applyTypedInput(leaf, input) {
    const empty   = input.value === "";
    const invalid = !empty && leaf.type === "int" && !/^-?\d+$/.test(input.value);

    input.classList.toggle("is-dirty", !empty && input.value !== leaf.value);
    input.classList.toggle("is-invalid", invalid);
    input.title = invalid ? "not a whole number; this field takes an integer" : "";

    if (empty || invalid) this._unsetValue(leaf, true);
    else this._setValue(leaf, input.value, true);
  }

  _switchControl(leaf) {
    const toggle = document.createElement("button");
    toggle.type = "button";
    toggle.className = "switch";
    toggle.setAttribute("role", "switch");
    toggle.innerHTML = `<span class="switch__knob"></span>`;

    const paint = () => {
      const on = this._effective(leaf) === "True";
      toggle.classList.toggle("is-on", on);
      toggle.classList.toggle("is-dirty", this.dirty[leaf.path] !== undefined);
      toggle.setAttribute("aria-checked", String(on));
    };
    toggle.addEventListener("click", () => {
      const next = this._effective(leaf) === "True" ? "False" : "True";
      this._setValue(leaf, next);
      paint();
    });
    paint();

    const reset = () => paint();
    return { el: toggle, input: toggle, reset };
  }

  static shellToken(value) {
    const raw = String(value);
    return /^[\w@%+=:,./-]+$/.test(raw) ? raw : `'${raw.replace(/'/g, `'\\''`)}'`;
  }

  _commandLine(base, join) {
    let text = base;
    Object.entries(this.dirty).forEach(([path, value]) => {
      text += `${join}--${path} ${ConfigForm.shellToken(value)}`;
    });
    if (this.detach) text += `${join}--detach`;
    return text;
  }

  _resetField(path) {
    const control = this.controls[path];
    delete this.dirty[path];
    if (control) control.reset();
    this._refresh();
  }

  _resetAll() {
    this.dirty = {};
    Object.values(this.controls).forEach((c) => c.reset());
    this._refresh();
  }

  _navigate(key) {
    this._setActiveSection(key);
  }

  _conditionFails(condition) {
    const leaf = this.byPath.get(condition.field);
    if (!leaf) return false;

    const value = String(this._effective(leaf));
    if (condition.in) return !condition.in.includes(value);

    const isSet = value !== "" && value !== "None";
    return isSet !== condition.set;
  }

  _whenHolds(when) {
    const conditions = Array.isArray(when) ? when : [when];
    return conditions.every((condition) => !this._conditionFails(condition));
  }

  _sectionHidden(section) {
    if (!section.when) return false;
    return !this._whenHolds(section.when);
  }

  _setActiveSection(key) {
    const target = this.sections.find((section) => section.key === key && !this._sectionHidden(section));
    const fallback = this.sections.find((section) => !this._sectionHidden(section));
    this.activeSection = (target || fallback || this.sections[0]).key;

    this.sections.forEach((section) => {
      if (section.navBtn) section.navBtn.classList.toggle("is-active", section.key === this.activeSection);
    });
    this._applyVisibility();
  }

  _refreshGates() {
    this.states.forEach(({ row }) => {
      delete row.dataset.gated;
    });

    this.gates.forEach((gate) => {
      const open = gate.test ? gate.test() : this._effective(gate.leaf) === "True";
      if (!open) gate.states.forEach(({ row }) => (row.dataset.gated = "1"));
    });

    this.repainters.forEach((paint) => paint());

    if (this.activeSection) {
      const active = this.sections.find((section) => section.key === this.activeSection);
      if (active && this._sectionHidden(active)) {
        this._setActiveSection(this.sections.find((section) => !this._sectionHidden(section)).key);
        return;
      }
    }

    this._applyVisibility();
  }

  _applyVisibility() {
    const searching = Boolean(this.query);
    if (this.layoutEl) this.layoutEl.classList.toggle("is-searching", searching);

    this.states.forEach(({ leaf, row }) => {
      const matchesQuery = !searching || leaf.path.toLowerCase().includes(this.query);
      row.hidden = !matchesQuery || row.dataset.gated === "1";
    });

    this.pairs.forEach((pair) => {
      if (pair.container) pair.container.hidden = false;
      const wantOpen = pair.open || (searching && pair.states.some(({ row }) => !row.hidden));
      pair.body.hidden = !wantOpen;
      pair.toggle.setAttribute("aria-expanded", String(wantOpen));
      pair.toggle.classList.toggle("is-open", wantOpen);
    });

    this._sweepShells(true);

    let anyVisible = false;
    this.sections.forEach((section) => {
      const whenHidden = this._sectionHidden(section);
      const hasRows    = this.states.some(({ row, sectionKey }) => sectionKey === section.key && !row.hidden);
      if (section.navBtn) section.navBtn.hidden = whenHidden;

      const single = this.config && this.config.layout && this.config.layout.mode === "single";
      const show   = !whenHidden && (searching ? hasRows : (single || section.key === this.activeSection));
      section.el.hidden = !show;
      anyVisible = anyVisible || (show && (!searching || hasRows));
    });

    if (this.nomatchEl) this.nomatchEl.hidden = !searching || anyVisible;
  }

  _shellsFor(row) {
    const cached = this.shellCache.get(row);
    if (cached) return cached;

    const shells = [];
    for (let el = row.parentElement; el && el !== this.layoutEl; el = el.parentElement) {
      if (el.classList.contains("band-block") || el.classList.contains("field-group") || el.classList.contains("cfg-panel")) shells.push(el);
    }

    this.shellCache.set(row, shells);
    return shells;
  }

  _sweepShells(on) {
    if (!this.layoutEl) return;

    const filled = new Map();
    this.states.forEach(({ row }) => {
      this._shellsFor(row).forEach((shell) => filled.set(shell, (filled.get(shell) || false) || !row.hidden));
    });

    filled.forEach((visible, shell) => {
      shell.style.display = on && !visible ? "none" : "";
    });
  }

  _refreshPairs() {
    this.pairs.forEach((pair) => {
      pair.states.forEach(({ leaf, row }) => {
        row.classList.toggle("is-inherited", this._inherited(leaf) !== undefined);

        const control = this.controls[leaf.path];
        if (control && this.dirty[leaf.path] === undefined && document.activeElement !== control.input) control.reset();
      });

      const differ = pair.states.filter(({ leaf }) => {
        const base = this.byPath.get(pair.base + leaf.path.slice(pair.override.length));
        return base && this._effective(leaf) !== this._effective(base);
      }).length;
      pair.badge.hidden = differ === 0;
      pair.badge.textContent = differ ? `${differ} differ` : "";
    });
  }

  _refreshBadges() {
    const counts = new Map();
    this.states.forEach(({ leaf, sectionKey }) => {
      if (this.dirty[leaf.path] !== undefined) counts.set(sectionKey, (counts.get(sectionKey) || 0) + 1);
    });

    this.sections.forEach((section) => {
      if (!section.badge) return;
      const n = counts.get(section.key) || 0;
      section.badge.hidden = n === 0;
      section.badge.textContent = n ? `${n}` : "";
    });

    this._refreshPairs();
  }
}

window.ConfigForm = ConfigForm;
