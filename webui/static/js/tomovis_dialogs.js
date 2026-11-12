"use strict";

class TomoVisModal {
  static stack = [];

  constructor({ title = "", className = "", buttons = [], layer = null, escape = "Cancel", defaultButton = null } = {}) {
    this.layer   = layer || TomoVisDialogs.current.ctx.layer;
    this.escape  = escape;
    this.resolve = null;
    this.result  = null;

    this.scrim = TomoVisInput.el("div", "tv-modal__scrim");
    this.el    = TomoVisInput.el("div", `tv-modal ${className}`.trim());
    this.el.setAttribute("role", "dialog");
    this.el.setAttribute("aria-modal", "true");
    this.el.tabIndex = -1;

    this.titleBar = TomoVisInput.el("div", "tv-modal__title", title);
    this.body     = TomoVisInput.el("div", "tv-modal__body");
    this.footer   = TomoVisInput.el("div", "tv-modal__buttons");
    this.el.append(this.titleBar, this.body);
    this.buttons  = {};

    for (const spec of buttons) {
      const label  = typeof spec === "string" ? spec : spec.text;
      const button = TomoVisInput.el("button", "tv-button", label);
      button.type = "button";
      button.addEventListener("click", () => this.close(label));
      this.buttons[label] = button;
      this.footer.append(button);
    }
    if (buttons.length) this.el.append(this.footer);
    this.defaultButton = defaultButton || (typeof buttons[0] === "string" ? buttons[0] : (buttons[0] ? buttons[0].text : null));

    this.titleBar.addEventListener("pointerdown", (event) => this.dragStart(event));
    this.el.addEventListener("keydown", (event) => this.key(event));
  }

  setTitle(title) {
    this.titleBar.textContent = title;
  }

  open() {
    TomoVisModal.stack.push(this);
    this.layer.append(this.scrim, this.el);
    this.center();
    const target = (this.defaultButton && this.buttons[this.defaultButton]) || this.el.querySelector("input, select, button, [tabindex='0']") || this.el;
    target.focus({ preventScroll: true });
    return new Promise((resolve) => { this.resolve = resolve; });
  }

  center() {
    const layerRect = this.layer.getBoundingClientRect();
    const view      = TomoVisInput.viewport();
    const left      = Math.max(layerRect.left, 0);
    const top       = Math.max(layerRect.top, 0);
    const right     = Math.min(layerRect.right, view.width);
    const bottom    = Math.min(layerRect.bottom, view.height);
    const rect      = this.el.getBoundingClientRect();
    const x         = left + Math.max(0, (right - left - rect.width) / 2);
    const y         = top + Math.max(0, (bottom - top - rect.height) / 2);
    this.el.style.left = `${x - layerRect.left}px`;
    this.el.style.top  = `${y - layerRect.top}px`;
  }

  close(result) {
    const index = TomoVisModal.stack.indexOf(this);
    if (index >= 0) TomoVisModal.stack.splice(index, 1);
    this.scrim.remove();
    this.el.remove();
    this.result = result;
    if (this.resolve) this.resolve(result);
    this.resolve = null;
  }

  isTop() {
    return TomoVisModal.stack[TomoVisModal.stack.length - 1] === this;
  }

  key(event) {
    if (!this.isTop()) return;
    if (event.key === "Escape") {
      event.preventDefault();
      event.stopPropagation();
      this.close(this.escape);
      return;
    }
    if (event.key === "Tab") this.trapFocus(event);
  }

  trapFocus(event) {
    const nodes = [...this.el.querySelectorAll("input, button, select, textarea, [tabindex='0']")].filter((node) => !node.disabled && node.offsetParent !== null);
    if (nodes.length === 0) return;
    const first = nodes[0];
    const last  = nodes[nodes.length - 1];
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first.focus();
    }
  }

  dragStart(event) {
    if (event.button !== 0) return;
    event.preventDefault();
    const startX = event.clientX;
    const startY = event.clientY;
    const left   = parseFloat(this.el.style.left) || 0;
    const top    = parseFloat(this.el.style.top) || 0;
    const move   = (e) => {
      this.el.style.left = `${left + e.clientX - startX}px`;
      this.el.style.top  = `${top + e.clientY - startY}px`;
    };
    const stop = () => {
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", stop);
    };
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", stop);
  }

  static isOpen() {
    return TomoVisModal.stack.length > 0;
  }
}

class TomoVisMessageBox {
  static ICONS = {
    information : '<svg viewBox="0 0 32 32" aria-hidden="true"><circle cx="16" cy="16" r="14" fill="#5b8def"/><rect x="14.2" y="13" width="3.6" height="11" fill="#fff"/><circle cx="16" cy="9" r="2.2" fill="#fff"/></svg>',
    warning     : '<svg viewBox="0 0 32 32" aria-hidden="true"><path d="M16 2.5 31 29H1z" fill="#f6d33c" stroke="#1d1d1d" stroke-width="1.5" stroke-linejoin="round"/><rect x="14.3" y="11" width="3.4" height="10" fill="#1d1d1d"/><circle cx="16" cy="24.6" r="1.9" fill="#1d1d1d"/></svg>',
    critical    : '<svg viewBox="0 0 32 32" aria-hidden="true"><circle cx="16" cy="16" r="14" fill="#e5484d"/><path d="M10.5 10.5l11 11M21.5 10.5l-11 11" stroke="#fff" stroke-width="3.4" stroke-linecap="round"/></svg>',
    question    : '<svg viewBox="0 0 32 32" aria-hidden="true"><circle cx="16" cy="16" r="14" fill="#5b8def"/><text x="16" y="22.5" text-anchor="middle" font-size="18" font-weight="700" font-family="sans-serif" fill="#fff">?</text></svg>',
  };

  static show({ level = "information", title = "", text = "", buttons = ["OK"], escape = null, defaultButton = null, layer = null } = {}) {
    const modal = new TomoVisModal({ title, className: "tv-messagebox", buttons, layer, escape: escape || (buttons.length === 1 ? buttons[0] : buttons[buttons.length - 1]), defaultButton });
    const icon  = TomoVisInput.el("div", `tv-messagebox__icon is-${level}`);
    icon.innerHTML = TomoVisMessageBox.ICONS[level];
    modal.el.dataset.level = level;
    modal.body.append(icon, TomoVisInput.el("div", "tv-messagebox__text", text));
    return modal.open();
  }
}

class TomoVisFileDialog {
  static STORAGE_KEY = "tomovis.lastDir";
  static COLUMNS     = [["name", "Name"], ["size", "Size"], ["mtime", "Date Modified"]];

  static open(request) {
    return new TomoVisFileDialog(request).run();
  }

  static lastDir() {
    try {
      return window.localStorage.getItem(TomoVisFileDialog.STORAGE_KEY);
    } catch (error) {
      return null;
    }
  }

  static rememberDir(dir) {
    try {
      window.localStorage.setItem(TomoVisFileDialog.STORAGE_KEY, dir);
    } catch (error) {
      return;
    }
  }

  static parseFilter(filter) {
    const match = /\(([^)]*)\)\s*$/.exec(filter);
    return match ? match[1].split(/\s+/).filter(Boolean) : ["*"];
  }

  static joinPath(dir, name) {
    if (name.startsWith("/")) return TomoVisFileDialog.normalize(name);
    return TomoVisFileDialog.normalize(`${dir.replace(/\/+$/, "")}/${name}`);
  }

  static normalize(path) {
    const parts = [];
    for (const part of path.split("/")) {
      if (part === "" || part === ".") continue;
      if (part === "..") parts.pop();
      else parts.push(part);
    }
    return `/${parts.join("/")}`;
  }

  static split(path) {
    const clean = TomoVisFileDialog.normalize(path);
    const index = clean.lastIndexOf("/");
    return { dir: index <= 0 ? "/" : clean.slice(0, index), name: clean.slice(index + 1) };
  }

  static formatSize(bytes) {
    if (bytes < 1024) return `${bytes} bytes`;
    const units = ["KiB", "MiB", "GiB", "TiB", "PiB"];
    let value = bytes / 1024;
    let unit  = 0;
    while (value >= 1024 && unit < units.length - 1) {
      value /= 1024;
      unit += 1;
    }
    return `${value.toFixed(2)} ${units[unit]}`;
  }

  static formatTime(seconds) {
    const date = new Date(seconds * 1000);
    return date.toLocaleString(undefined, { year: "2-digit", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" });
  }

  constructor({ mode = "open", title = "", filters = [], selected_filter = null, directory = null, file = null, session = null, layer = null }) {
    this.mode     = mode;
    this.title    = title;
    this.filters  = filters.length ? filters : ["All Files (*)"];
    this.filter   = selected_filter && this.filters.includes(selected_filter) ? selected_filter : this.filters[0];
    this.start    = directory || TomoVisFileDialog.lastDir() || "";
    this.file     = file || "";
    this.session  = session || TomoVisDialogs.current.ctx.session;
    this.kit      = TomoVisDialogs.current.ctx.kit;
    this.layer    = layer || TomoVisDialogs.current.ctx.layer;
    this.dir      = null;
    this.home     = null;
    this.parent   = null;
    this.entries  = [];
    this.selected = -1;
    this.history  = [];
    this.future   = [];
    this.sortKey  = "name";
    this.sortAsc  = true;
    this.ticket   = 0;
  }

  async run() {
    this.modal = new TomoVisModal({ title: this.title, className: "tv-filedialog", layer: this.layer, escape: null });
    this.build();
    const opened = this.modal.open();
    const ticket = this.ticket + 1;
    const shown  = await this.navigate(this.start, false);
    if (!shown && this.ticket === ticket) await this.navigate("", false);
    this.nameField.focus();
    const result = await opened;
    return result || { accepted: false, path: null, filter: this.filter };
  }

  build() {
    const body = this.modal.body;

    const top = TomoVisInput.el("div", "tv-filedialog__top");
    top.append(TomoVisInput.el("label", "tv-label", "Look in:"));
    this.lookIn = TomoVisInput.el("input", "tv-line tv-filedialog__lookin");
    this.lookIn.type       = "text";
    this.lookIn.spellcheck = false;
    this.lookInEdited = false;
    this.lookIn.addEventListener("input", () => { this.lookInEdited = true; });
    this.lookIn.addEventListener("keydown", (event) => {
      if (event.key !== "Enter") return;
      event.preventDefault();
      this.lookInEdited = false;
      this.navigate(this.lookIn.value.trim(), true);
    });
    this.backButton    = this.toolButton("Back", "tv-filedialog__back", () => this.back());
    this.forwardButton = this.toolButton("Forward", "tv-filedialog__forward", () => this.forward());
    this.parentButton  = this.toolButton("Parent Directory", "tv-filedialog__parent", () => this.toParent());
    top.append(this.lookIn, this.backButton, this.forwardButton, this.parentButton);

    this.listWrap = TomoVisInput.el("div", "tv-filedialog__list");
    this.table    = TomoVisInput.el("table", "tv-filedialog__table");
    const head    = TomoVisInput.el("thead");
    const headRow = TomoVisInput.el("tr");
    this.headers  = {};
    for (const [key, label] of TomoVisFileDialog.COLUMNS) {
      const th = TomoVisInput.el("th", `tv-filedialog__col--${key}`, label);
      th.addEventListener("click", () => this.sortBy(key));
      this.headers[key] = th;
      headRow.append(th);
    }
    head.append(headRow);
    this.tbody = TomoVisInput.el("tbody");
    this.table.append(head, this.tbody);
    this.table.tabIndex = 0;
    this.table.addEventListener("keydown", (event) => this.listKey(event));
    this.listWrap.append(this.table);

    const grid = TomoVisInput.el("div", "tv-filedialog__grid");
    this.nameField = TomoVisInput.el("input", "tv-line tv-filedialog__name");
    this.nameField.type       = "text";
    this.nameField.spellcheck = false;
    this.nameField.value      = this.file;
    this.nameField.addEventListener("input", () => this.updateAccept());
    this.nameField.addEventListener("keydown", (event) => {
      if (event.key !== "Enter") return;
      event.preventDefault();
      this.accept();
    });

    this.acceptButton = TomoVisInput.el("button", "tv-button tv-filedialog__accept", this.mode === "save" ? "Save" : "Open");
    this.acceptButton.type = "button";
    this.acceptButton.addEventListener("click", () => this.accept());

    this.filterCombo = this.kit.local("combo", { items: this.filters, onChange: (index) => this.changeFilter(index) });
    this.filterCombo.set({ index: this.filters.indexOf(this.filter), enabled: true });
    this.filterCombo.el.classList.add("tv-filedialog__filter");

    const cancel = TomoVisInput.el("button", "tv-button tv-filedialog__cancel", "Cancel");
    cancel.type = "button";
    cancel.addEventListener("click", () => this.modal.close({ accepted: false, path: null, filter: this.filter }));

    const nameLabel   = TomoVisInput.el("label", "tv-label", this.mode === "save" ? "File name:" : "File name:");
    const filterLabel = TomoVisInput.el("label", "tv-label", "Files of type:");
    grid.append(nameLabel, this.nameField, this.acceptButton, filterLabel, this.filterCombo.el, cancel);

    body.append(top, this.listWrap, grid);
    this.modal.escape = { accepted: false, path: null, filter: this.filter };
    this.updateAccept();
    this.updateNav();
  }

  toolButton(label, className, action) {
    const button = TomoVisInput.el("button", `tv-button tv-button--tool ${className}`);
    button.type = "button";
    button.title = label;
    button.setAttribute("aria-label", label);
    button.addEventListener("click", action);
    return button;
  }

  patterns() {
    return TomoVisFileDialog.parseFilter(this.filter);
  }

  async navigate(path, record) {
    this.ticket  += 1;
    const ticket  = this.ticket;
    const listing = await this.session.listDir(path, this.patterns());
    if (ticket !== this.ticket) return false;
    if (!listing || listing.ok === false || listing.error) {
      this.lookIn.classList.add("is-invalid");
      setTimeout(() => this.lookIn.classList.remove("is-invalid"), 900);
      if (this.dir !== null) this.lookIn.value = this.dir;
      return false;
    }

    if (record && this.dir !== null && this.dir !== listing.path) {
      this.history.push(this.dir);
      this.future = [];
    }
    this.dir     = listing.path;
    this.parent  = listing.parent;
    this.home    = listing.home;
    this.entries = listing.entries;
    this.selected = -1;
    if (!this.lookInEdited) this.lookIn.value = this.dir;
    this.modal.el.dataset.dir     = this.dir;
    this.modal.el.dataset.listing = `${this.dir}|${this.filter}`;
    this.renderList();
    this.updateNav();
    return true;
  }

  async back() {
    if (!this.history.length) return;
    const target = this.history.pop();
    const from   = this.dir;
    if (await this.navigate(target, false)) this.future.push(from);
    this.updateNav();
  }

  async forward() {
    if (!this.future.length) return;
    const target = this.future.pop();
    const from   = this.dir;
    if (await this.navigate(target, false)) this.history.push(from);
    this.updateNav();
  }

  toParent() {
    if (this.parent) this.navigate(this.parent, true);
  }

  updateNav() {
    this.backButton.disabled    = this.history.length === 0;
    this.forwardButton.disabled = this.future.length === 0;
    this.parentButton.disabled  = !this.parent;
  }

  changeFilter(index) {
    this.filter = this.filters[index];
    this.modal.escape = { accepted: false, path: null, filter: this.filter };
    if (this.dir !== null) this.navigate(this.dir, false);
  }

  sortBy(key) {
    if (this.sortKey === key) this.sortAsc = !this.sortAsc;
    else {
      this.sortKey = key;
      this.sortAsc = true;
    }
    this.renderList();
  }

  sorted() {
    const sign = this.sortAsc ? 1 : -1;
    const key  = this.sortKey;
    return [...this.entries].sort((a, b) => {
      if (a.dir !== b.dir) return a.dir ? -1 : 1;
      if (key === "name") return sign * a.name.localeCompare(b.name, undefined, { sensitivity: "base" });
      const diff = (a[key] || 0) - (b[key] || 0);
      return diff !== 0 ? sign * diff : a.name.localeCompare(b.name, undefined, { sensitivity: "base" });
    });
  }

  renderList() {
    this.view = this.sorted();
    this.tbody.replaceChildren();
    this.rows = this.view.map((entry, i) => {
      const row  = TomoVisInput.el("tr", entry.dir ? "is-dir" : "is-file");
      const name = TomoVisInput.el("td", "tv-filedialog__cell--name");
      name.append(TomoVisInput.el("span", entry.dir ? "tv-filedialog__icon is-dir" : "tv-filedialog__icon is-file"), TomoVisInput.el("span", "", entry.name));
      row.append(name, TomoVisInput.el("td", "tv-filedialog__cell--size", entry.dir ? "" : TomoVisFileDialog.formatSize(entry.size)), TomoVisInput.el("td", "tv-filedialog__cell--mtime", TomoVisFileDialog.formatTime(entry.mtime)));
      row.addEventListener("click", () => this.select(i));
      row.addEventListener("dblclick", () => this.openEntry(i));
      this.tbody.append(row);
      return row;
    });
    for (const [key, th] of Object.entries(this.headers)) {
      th.classList.toggle("is-sorted", key === this.sortKey);
      th.classList.toggle("is-desc", key === this.sortKey && !this.sortAsc);
    }
    this.listWrap.scrollTop = 0;
  }

  select(i) {
    this.selected = i;
    this.rows.forEach((row, k) => row.classList.toggle("is-selected", k === i));
    const entry = this.view[i];
    if (entry && !entry.dir) {
      this.nameField.value = entry.name;
      this.updateAccept();
    }
    if (this.rows[i]) this.rows[i].scrollIntoView({ block: "nearest" });
  }

  openEntry(i) {
    const entry = this.view[i];
    if (!entry) return;
    if (entry.dir) {
      this.navigate(TomoVisFileDialog.joinPath(this.dir, entry.name), true);
      return;
    }
    this.nameField.value = entry.name;
    this.accept();
  }

  listKey(event) {
    if (!this.rows || this.rows.length === 0) return;
    if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      event.preventDefault();
      const step = event.key === "ArrowDown" ? 1 : -1;
      this.select(Math.max(0, Math.min(this.rows.length - 1, this.selected + step)));
    } else if (event.key === "Enter") {
      event.preventDefault();
      if (this.selected >= 0) this.openEntry(this.selected);
    } else if (event.key === "Backspace") {
      event.preventDefault();
      this.toParent();
    }
  }

  updateAccept() {
    this.acceptButton.disabled = this.nameField.value.trim() === "";
  }

  resolveTyped(text) {
    if (text === "~") return this.home;
    if (text.startsWith("~/")) return TomoVisFileDialog.joinPath(this.home, text.slice(2));
    return TomoVisFileDialog.joinPath(this.dir, text);
  }

  async lookup(path) {
    const { dir, name } = TomoVisFileDialog.split(path);
    if (path === "/") return { exists: true, dir: true };
    const listing = await this.session.listDir(dir, ["*"]);
    if (!listing || listing.ok === false || listing.error) return { exists: false, dir: false };
    const entry = listing.entries.find((e) => e.name === name);
    return entry ? { exists: true, dir: entry.dir } : { exists: false, dir: false };
  }

  async accept() {
    const text = this.nameField.value.trim();
    if (!text || this.dir === null) return;
    const path  = this.resolveTyped(text);
    const found = await this.lookup(path);

    if (found.dir) {
      if (await this.navigate(path, true)) {
        this.nameField.value = "";
        this.updateAccept();
      }
      return;
    }

    const name = TomoVisFileDialog.split(path).name;
    if (this.mode === "open" && !found.exists) {
      await TomoVisMessageBox.show({ level: "warning", title: this.title, text: `${name}\nFile not found.\nPlease verify the correct file name was given.`, layer: this.layer });
      this.nameField.focus();
      return;
    }
    if (this.mode === "save" && found.exists) {
      const answer = await TomoVisMessageBox.show({ level: "warning", title: this.title, text: `${name} already exists.\nDo you want to replace it?`, buttons: ["Yes", "No"], escape: "No", defaultButton: "No", layer: this.layer });
      if (answer !== "Yes") {
        this.nameField.focus();
        return;
      }
    }

    TomoVisFileDialog.rememberDir(TomoVisFileDialog.split(path).dir);
    this.modal.close({ accepted: true, path, filter: this.filter });
  }
}

class TomoVisColorDialog {
  static TITLE       = "Select Color";
  static STORAGE_KEY = "tomovis.customColors";

  static getColor(options = {}) {
    return new TomoVisColorDialog(options).run();
  }

  static standardColors() {
    const colors = [];
    for (let g = 0; g < 4; g += 1) {
      for (let r = 0; r < 4; r += 1) {
        for (let b = 0; b < 3; b += 1) colors.push([Math.floor(r * 255 / 3), Math.floor(g * 255 / 3), Math.floor(b * 255 / 2)]);
      }
    }
    return colors;
  }

  static storedCustom() {
    const white = Array.from({ length: 16 }, () => [255, 255, 255]);
    let stored;
    try {
      stored = JSON.parse(window.localStorage.getItem(TomoVisColorDialog.STORAGE_KEY));
    } catch (error) {
      return white;
    }
    const valid = Array.isArray(stored) && stored.length === 16 && stored.every((color) => Array.isArray(color) && color.length === 3 && color.every((v) => Number.isInteger(v) && v >= 0 && v <= 255));
    return valid ? stored : white;
  }

  static rememberCustom() {
    try {
      window.localStorage.setItem(TomoVisColorDialog.STORAGE_KEY, JSON.stringify(TomoVisColorDialog.custom));
    } catch (error) {
      return;
    }
  }

  static custom = this.storedCustom();

  static rgbToHsv(r, g, b) {
    const max = Math.max(r, g, b);
    const min = Math.min(r, g, b);
    const delta = max - min;
    const v = max;
    const s = max === 0 ? 0 : Math.round(255 * delta / max);
    if (delta === 0) return [-1, s, v];
    let h;
    if (max === r) h = 60 * (((g - b) / delta) % 6);
    else if (max === g) h = 60 * ((b - r) / delta + 2);
    else h = 60 * ((r - g) / delta + 4);
    if (h < 0) h += 360;
    return [Math.round(h) % 360, s, v];
  }

  static hsvToRgb(h, s, v) {
    if (h < 0 || s === 0) return [v, v, v];
    const sat = s / 255;
    const val = v / 255;
    const c   = val * sat;
    const hp  = (h % 360) / 60;
    const x   = c * (1 - Math.abs((hp % 2) - 1));
    const table = [[c, x, 0], [x, c, 0], [0, c, x], [0, x, c], [x, 0, c], [c, 0, x]];
    const [r1, g1, b1] = table[Math.floor(hp) % 6];
    const m = val - c;
    return [Math.round((r1 + m) * 255), Math.round((g1 + m) * 255), Math.round((b1 + m) * 255)];
  }

  constructor({ initial = [255, 255, 255, 255], title = "", alpha = true, live = null, layer = null } = {}) {
    this.initial = [initial[0], initial[1], initial[2], initial.length > 3 ? initial[3] : 255];
    this.title   = title || TomoVisColorDialog.TITLE;
    this.alpha   = alpha;
    this.live    = live;
    this.layer   = layer || TomoVisDialogs.current.ctx.layer;
    this.kit     = TomoVisDialogs.current.ctx.kit;
    this.rgb     = this.initial.slice(0, 3);
    this.a       = this.initial[3];
    const [h, s, v] = TomoVisColorDialog.rgbToHsv(...this.rgb);
    this.hsv     = [h, s, v];
    this.lastHue = h < 0 ? 0 : h;
    this.fields  = {};
  }

  async run() {
    this.modal = new TomoVisModal({ title: this.title, className: "tv-colordialog", buttons: ["OK", "Cancel"], layer: this.layer });
    this.build();
    this.sync(null);
    const answer = await this.modal.open();
    if (answer === "OK") return { accepted: true, color: [...this.rgb, this.a] };
    if (this.live) this.live([...this.initial]);
    return { accepted: false, color: [...this.initial] };
  }

  build() {
    const body  = this.modal.body;
    const left  = TomoVisInput.el("div", "tv-colordialog__left");
    const right = TomoVisInput.el("div", "tv-colordialog__right");

    left.append(TomoVisInput.el("div", "tv-label", "Basic colors"));
    left.append(this.well(TomoVisColorDialog.standardColors(), 6, 8, false));
    if (window.EyeDropper) {
      const pick = TomoVisInput.el("button", "tv-button", "Pick Screen Color");
      pick.type = "button";
      pick.addEventListener("click", () => this.pickScreen());
      left.append(pick);
    }
    left.append(TomoVisInput.el("div", "tv-label", "Custom colors"));
    this.customWell = this.well(TomoVisColorDialog.custom, 2, 8, true);
    left.append(this.customWell);
    const add = TomoVisInput.el("button", "tv-button", "Add to Custom Colors");
    add.type = "button";
    add.addEventListener("click", () => this.addCustom());
    left.append(add);

    const pickers = TomoVisInput.el("div", "tv-colordialog__pickers");
    this.field  = TomoVisInput.el("canvas", "tv-colordialog__field");
    this.field.width  = 360;
    this.field.height = 256;
    this.strip  = TomoVisInput.el("canvas", "tv-colordialog__strip");
    this.strip.width  = 20;
    this.strip.height = 256;
    this.cross  = TomoVisInput.el("span", "tv-colordialog__cross");
    this.arrow  = TomoVisInput.el("span", "tv-colordialog__arrow");
    const fieldWrap = TomoVisInput.el("span", "tv-colordialog__fieldwrap");
    fieldWrap.append(this.field, this.cross);
    const stripWrap = TomoVisInput.el("span", "tv-colordialog__stripwrap");
    stripWrap.append(this.strip, this.arrow);
    pickers.append(fieldWrap, stripWrap);
    this.paintField();
    this.drag(this.field, (x, y) => this.pickField(x, y));
    this.drag(this.strip, (x, y) => this.pickStrip(y));

    const shower = TomoVisInput.el("div", "tv-colordialog__shower");
    this.swatch = TomoVisInput.el("span", "tv-colordialog__swatch");
    const grid  = TomoVisInput.el("div", "tv-colordialog__fields");
    const spec  = [["hue", "Hue:", 0, 359], ["red", "Red:", 0, 255], ["sat", "Sat:", 0, 255], ["green", "Green:", 0, 255], ["val", "Val:", 0, 255], ["blue", "Blue:", 0, 255]];
    for (const [key, label, min, max] of spec) {
      const spin = this.kit.local("spin", { onChange: (value) => this.edit(key, value) });
      spin.set({ enabled: true, minimum: min, maximum: max, value: 0 });
      this.fields[key] = spin;
      grid.append(TomoVisInput.el("label", "tv-label", label), spin.el);
    }
    if (this.alpha) {
      const spin = this.kit.local("spin", { onChange: (value) => this.edit("alpha", value) });
      spin.set({ enabled: true, minimum: 0, maximum: 255, value: this.a });
      this.fields.alpha = spin;
      const label = TomoVisInput.el("label", "tv-label tv-colordialog__alphalabel", "Alpha channel:");
      grid.append(label, spin.el);
    }
    this.html = this.kit.local("line", { validator: "#?[0-9a-fA-F]{0,6}", onChange: (text) => this.editHtml(text) });
    this.html.set({ enabled: true, text: "" });
    grid.append(TomoVisInput.el("label", "tv-label", "HTML:"), this.html.el);
    shower.append(this.swatch, grid);

    right.append(pickers, shower);
    body.append(left, right);
  }

  well(colors, rows, cols, custom) {
    const grid = TomoVisInput.el("div", "tv-colordialog__well");
    grid.style.gridTemplateColumns = `repeat(${cols}, 1fr)`;
    for (let row = 0; row < rows; row += 1) {
      for (let col = 0; col < cols; col += 1) {
        const index = row + col * rows;
        const cell  = TomoVisInput.el("button", "tv-colordialog__cell");
        cell.type = "button";
        cell.dataset.index = String(index);
        cell.style.gridRow    = String(row + 1);
        cell.style.gridColumn = String(col + 1);
        const paint = () => { cell.style.background = `rgb(${colors[index].join(",")})`; };
        paint();
        cell.paint = paint;
        cell.addEventListener("click", () => {
          if (custom) this.customIndex = index;
          grid.querySelectorAll(".is-selected").forEach((node) => node.classList.remove("is-selected"));
          cell.classList.add("is-selected");
          this.setRgb([...colors[index]], null);
        });
        grid.append(cell);
      }
    }
    return grid;
  }

  addCustom() {
    const index = this.customIndex === undefined ? (this.nextCustom || 0) : this.customIndex;
    TomoVisColorDialog.custom[index] = [...this.rgb];
    TomoVisColorDialog.rememberCustom();
    this.nextCustom  = (index + 1) % 16;
    this.customIndex = undefined;
    this.customWell.querySelectorAll(".tv-colordialog__cell").forEach((cell) => cell.paint());
  }

  async pickScreen() {
    const picked = await new window.EyeDropper().open().catch(() => null);
    if (!picked) return;
    const hex = picked.sRGBHex.replace("#", "");
    this.setRgb([parseInt(hex.slice(0, 2), 16), parseInt(hex.slice(2, 4), 16), parseInt(hex.slice(4, 6), 16)], null);
  }

  drag(canvas, pick) {
    canvas.addEventListener("pointerdown", (event) => {
      if (event.button !== 0) return;
      canvas.setPointerCapture(event.pointerId);
      const at = (e) => {
        const rect = canvas.getBoundingClientRect();
        pick(Math.max(0, Math.min(rect.width - 1, e.clientX - rect.left)) / Math.max(1, rect.width - 1), Math.max(0, Math.min(rect.height - 1, e.clientY - rect.top)) / Math.max(1, rect.height - 1));
      };
      at(event);
      const move = (e) => at(e);
      const up   = () => {
        canvas.removeEventListener("pointermove", move);
        canvas.removeEventListener("pointerup", up);
      };
      canvas.addEventListener("pointermove", move);
      canvas.addEventListener("pointerup", up);
    });
  }

  paintField() {
    const ctx   = this.field.getContext("2d");
    const image = ctx.createImageData(this.field.width, this.field.height);
    for (let y = 0; y < this.field.height; y += 1) {
      for (let x = 0; x < this.field.width; x += 1) {
        const hue = Math.round(360 - x * 360 / (this.field.width - 1)) % 360;
        const sat = Math.round(255 - y * 255 / (this.field.height - 1));
        const [r, g, b] = TomoVisColorDialog.hsvToRgb(hue, sat, 200);
        const k = 4 * (y * this.field.width + x);
        image.data[k] = r;
        image.data[k + 1] = g;
        image.data[k + 2] = b;
        image.data[k + 3] = 255;
      }
    }
    ctx.putImageData(image, 0, 0);
  }

  paintStrip() {
    const ctx   = this.strip.getContext("2d");
    const image = ctx.createImageData(this.strip.width, this.strip.height);
    const hue   = this.hsv[0] < 0 ? this.lastHue : this.hsv[0];
    for (let y = 0; y < this.strip.height; y += 1) {
      const [r, g, b] = TomoVisColorDialog.hsvToRgb(hue, this.hsv[1], Math.round(255 - y * 255 / (this.strip.height - 1)));
      for (let x = 0; x < this.strip.width; x += 1) {
        const k = 4 * (y * this.strip.width + x);
        image.data[k] = r;
        image.data[k + 1] = g;
        image.data[k + 2] = b;
        image.data[k + 3] = 255;
      }
    }
    ctx.putImageData(image, 0, 0);
  }

  pickField(fx, fy) {
    const hue = Math.round(360 - fx * 360) % 360;
    const sat = Math.round(255 - fy * 255);
    this.setHsv([hue, sat, this.hsv[2]], null);
  }

  pickStrip(fy) {
    const hue = this.hsv[0] < 0 ? this.lastHue : this.hsv[0];
    this.setHsv([hue, this.hsv[1], Math.round(255 - fy * 255)], null);
  }

  edit(key, value) {
    if (key === "alpha") {
      this.a = value;
      this.sync("alpha");
      return;
    }
    if (key === "red" || key === "green" || key === "blue") {
      const rgb = [...this.rgb];
      rgb[{ red: 0, green: 1, blue: 2 }[key]] = value;
      this.setRgb(rgb, key);
      return;
    }
    const hsv = [this.hsv[0] < 0 ? this.lastHue : this.hsv[0], this.hsv[1], this.hsv[2]];
    hsv[{ hue: 0, sat: 1, val: 2 }[key]] = value;
    this.setHsv(hsv, key);
  }

  editHtml(text) {
    const hex = text.replace("#", "");
    if (hex.length !== 6) return;
    this.setRgb([parseInt(hex.slice(0, 2), 16), parseInt(hex.slice(2, 4), 16), parseInt(hex.slice(4, 6), 16)], "html");
  }

  setRgb(rgb, source) {
    this.rgb = rgb;
    this.hsv = TomoVisColorDialog.rgbToHsv(...rgb);
    if (this.hsv[0] >= 0) this.lastHue = this.hsv[0];
    this.sync(source);
  }

  setHsv(hsv, source) {
    this.hsv = hsv;
    this.lastHue = hsv[0];
    this.rgb = TomoVisColorDialog.hsvToRgb(...hsv);
    this.sync(source);
  }

  sync(source) {
    const hue   = this.hsv[0] < 0 ? this.lastHue : this.hsv[0];
    const value = { hue, sat: this.hsv[1], val: this.hsv[2], red: this.rgb[0], green: this.rgb[1], blue: this.rgb[2], alpha: this.a };
    for (const [key, spin] of Object.entries(this.fields)) {
      if (key !== source) spin.set({ value: value[key] });
    }
    const hex = `#${this.rgb.map((c) => c.toString(16).padStart(2, "0")).join("")}`;
    if (source !== "html") this.html.set({ text: hex });

    this.swatch.style.background = `rgba(${this.rgb.join(",")},${this.a / 255})`;
    this.cross.style.left = `${(360 - hue) / 360 * 100}%`;
    this.cross.style.top  = `${(255 - this.hsv[1]) / 255 * 100}%`;
    this.arrow.style.top  = `${(255 - this.hsv[2]) / 255 * 100}%`;
    this.paintStrip();
    if (this.live && source !== undefined) this.live([...this.rgb, this.a]);
  }
}

class TomoVisDialogs {
  static current = null;

  constructor(ctx) {
    this.ctx      = ctx;
    this.handlers = new Map();
    this.chain    = Promise.resolve();
  }

  activate() {
    TomoVisDialogs.current = this;
  }

  register(kind, handler) {
    this.handlers.set(kind, handler);
  }

  enqueue(requests) {
    for (const request of requests) {
      this.chain = this.chain.then(() => this.run(request)).catch((error) => {
        setTimeout(() => { throw error; });
      });
    }
    return this.chain;
  }

  message({ level = "information", title = "", text = "", buttons = ["OK"] } = {}) {
    return TomoVisMessageBox.show({ level, title, text, buttons, layer: this.ctx.layer });
  }

  file(request) {
    return TomoVisFileDialog.open({ ...request, session: this.ctx.session, layer: this.ctx.layer });
  }

  color(options) {
    return TomoVisColorDialog.getColor({ ...options, layer: this.ctx.layer });
  }

  async run(request) {
    this.activate();
    if (request.kind === "message") {
      await this.message(request);
      return null;
    }

    let result;
    if (request.kind === "file") {
      const chosen = await this.file(request);
      result = chosen.accepted ? { accepted: true, path: chosen.path } : { accepted: false };
    } else {
      const handler = this.handlers.get(request.kind);
      if (!handler) throw new Error(`TomoVis has no dialog handler for kind ${request.kind}`);
      result = await handler(request, this.ctx);
    }

    if (request.token) await this.ctx.session.send({ type: "dialog_result", token: request.token, ...result }).catch((error) => this.ctx.session.raiseUnreported(error));
    return result;
  }
}

window.TomoVisModal       = TomoVisModal;
window.TomoVisMessageBox  = TomoVisMessageBox;
window.TomoVisFileDialog  = TomoVisFileDialog;
window.TomoVisColorDialog = TomoVisColorDialog;
window.TomoVisDialogs     = TomoVisDialogs;
