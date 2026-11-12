"use strict";

class MplColors {
  static CSS4    = "aliceblue:f0f8ff,antiquewhite:faebd7,aqua:00ffff,aquamarine:7fffd4,azure:f0ffff,beige:f5f5dc,bisque:ffe4c4,black:000000,blanchedalmond:ffebcd,blue:0000ff,blueviolet:8a2be2,brown:a52a2a,burlywood:deb887,cadetblue:5f9ea0,chartreuse:7fff00,chocolate:d2691e,coral:ff7f50,cornflowerblue:6495ed,cornsilk:fff8dc,crimson:dc143c,cyan:00ffff,darkblue:00008b,darkcyan:008b8b,darkgoldenrod:b8860b,darkgray:a9a9a9,darkgreen:006400,darkgrey:a9a9a9,darkkhaki:bdb76b,darkmagenta:8b008b,darkolivegreen:556b2f,darkorange:ff8c00,darkorchid:9932cc,darkred:8b0000,darksalmon:e9967a,darkseagreen:8fbc8f,darkslateblue:483d8b,darkslategray:2f4f4f,darkslategrey:2f4f4f,darkturquoise:00ced1,darkviolet:9400d3,deeppink:ff1493,deepskyblue:00bfff,dimgray:696969,dimgrey:696969,dodgerblue:1e90ff,firebrick:b22222,floralwhite:fffaf0,forestgreen:228b22,fuchsia:ff00ff,gainsboro:dcdcdc,ghostwhite:f8f8ff,gold:ffd700,goldenrod:daa520,gray:808080,green:008000,greenyellow:adff2f,grey:808080,honeydew:f0fff0,hotpink:ff69b4,indianred:cd5c5c,indigo:4b0082,ivory:fffff0,khaki:f0e68c,lavender:e6e6fa,lavenderblush:fff0f5,lawngreen:7cfc00,lemonchiffon:fffacd,lightblue:add8e6,lightcoral:f08080,lightcyan:e0ffff,lightgoldenrodyellow:fafad2,lightgray:d3d3d3,lightgreen:90ee90,lightgrey:d3d3d3,lightpink:ffb6c1,lightsalmon:ffa07a,lightseagreen:20b2aa,lightskyblue:87cefa,lightslategray:778899,lightslategrey:778899,lightsteelblue:b0c4de,lightyellow:ffffe0,lime:00ff00,limegreen:32cd32,linen:faf0e6,magenta:ff00ff,maroon:800000,mediumaquamarine:66cdaa,mediumblue:0000cd,mediumorchid:ba55d3,mediumpurple:9370db,mediumseagreen:3cb371,mediumslateblue:7b68ee,mediumspringgreen:00fa9a,mediumturquoise:48d1cc,mediumvioletred:c71585,midnightblue:191970,mintcream:f5fffa,mistyrose:ffe4e1,moccasin:ffe4b5,navajowhite:ffdead,navy:000080,oldlace:fdf5e6,olive:808000,olivedrab:6b8e23,orange:ffa500,orangered:ff4500,orchid:da70d6,palegoldenrod:eee8aa,palegreen:98fb98,paleturquoise:afeeee,palevioletred:db7093,papayawhip:ffefd5,peachpuff:ffdab9,peru:cd853f,pink:ffc0cb,plum:dda0dd,powderblue:b0e0e6,purple:800080,rebeccapurple:663399,red:ff0000,rosybrown:bc8f8f,royalblue:4169e1,saddlebrown:8b4513,salmon:fa8072,sandybrown:f4a460,seagreen:2e8b57,seashell:fff5ee,sienna:a0522d,silver:c0c0c0,skyblue:87ceeb,slateblue:6a5acd,slategray:708090,slategrey:708090,snow:fffafa,springgreen:00ff7f,steelblue:4682b4,tan:d2b48c,teal:008080,thistle:d8bfd8,tomato:ff6347,turquoise:40e0d0,violet:ee82ee,wheat:f5deb3,white:ffffff,whitesmoke:f5f5f5,yellow:ffff00,yellowgreen:9acd32";
  static TABLEAU = "tab:blue:1f77b4,tab:orange:ff7f0e,tab:green:2ca02c,tab:red:d62728,tab:purple:9467bd,tab:brown:8c564b,tab:pink:e377c2,tab:gray:7f7f7f,tab:grey:7f7f7f,tab:olive:bcbd22,tab:cyan:17becf";
  static CYCLE   = ["1f77b4", "ff7f0e", "2ca02c", "d62728", "9467bd", "8c564b", "e377c2", "7f7f7f", "bcbd22", "17becf"];
  static BASE    = { b: [0, 0, 1], g: [0, 0.5, 0], r: [1, 0, 0], c: [0, 0.75, 0.75], m: [0.75, 0, 0.75], y: [0.75, 0.75, 0], k: [0, 0, 0], w: [1, 1, 1] };
  static INVALID = [0, 0, 0, 0];
  static names   = null;

  static table() {
    if (MplColors.names) return MplColors.names;
    const names = new Map();
    for (const entry of `${MplColors.CSS4},${MplColors.TABLEAU}`.split(",")) {
      const cut = entry.lastIndexOf(":");
      names.set(entry.slice(0, cut), entry.slice(cut + 1));
    }
    MplColors.names = names;
    return names;
  }

  static fromHex(hex) {
    if (hex.length === 3 || hex.length === 4) return [...hex].map((digit) => parseInt(digit, 16) / 15).concat(hex.length === 3 ? [1] : []);
    const out = [];
    for (let i = 0; i < hex.length; i += 2) out.push(parseInt(hex.slice(i, i + 2), 16) / 255);
    return hex.length === 6 ? out.concat([1]) : out;
  }

  static toRgba(text) {
    if (text.toLowerCase() === "none") return [0, 0, 0, 0];
    if (/^C[0-9]+$/.test(text)) return MplColors.fromHex(MplColors.CYCLE[Number(text.slice(1)) % MplColors.CYCLE.length]);
    if (text in MplColors.BASE) return [...MplColors.BASE[text], 1];

    const table = MplColors.table();
    const named = table.get(text) || (text.length !== 1 ? table.get(text.toLowerCase()) : undefined);
    if (named) return MplColors.fromHex(named);
    if (/^xkcd:/i.test(text)) return "unknown";

    if (/^#[a-fA-F0-9]+$/.test(text)) return [3, 4, 6, 8].includes(text.length - 1) ? MplColors.fromHex(text.slice(1)) : null;
    if (text.trim() === "" || !/^\s*[+-]?(\d+\.?\d*(e[+-]?\d+)?|\.\d+(e[+-]?\d+)?)\s*$/i.test(text)) return null;
    const gray = Number(text);
    return gray >= 0 && gray <= 1 ? [gray, gray, gray, 1] : null;
  }

  static quantize(rgba) {
    return rgba.map((value) => Math.round(value * 65535) / 65535);
  }

  static pyRound(value) {
    const floor = Math.floor(value);
    const diff  = value - floor;
    if (diff > 0.5) return floor + 1;
    if (diff < 0.5) return floor;
    return floor % 2 === 0 ? floor : floor + 1;
  }

  static toHex(rgba) {
    return `#${rgba.map((value) => MplColors.pyRound(value * 255).toString(16).padStart(2, "0")).join("")}`;
  }

  static to255(rgba) {
    return rgba.map((value) => Math.round(value * 255));
  }

  static same(a, b) {
    if (!a || !b) return a === b;
    return a.every((value, i) => Math.round(value * 65535) === Math.round(b[i] * 65535));
  }
}

class MplDoubleValidator {
  static NUMBER = /^[+-]?(\d+\.?\d*|\.\d+)(e[+-]?\d+)?$/;

  validate(text) {
    let buff            = "";
    let lastWasExponent = false;
    let lastWasDigit    = false;
    let exponents       = 0;
    let points          = 0;

    for (let i = 0; i < text.length; i += 1) {
      const c = text[i] === "E" ? "e" : text[i];
      if (c >= "0" && c <= "9") {
        lastWasDigit = true;
      } else {
        if (c === ".") {
          points += 1;
          if (points > 1) return "Invalid";
        } else if (c === "+" || c === "-") {
          if (i !== 0 && !lastWasExponent) return "Invalid";
        } else if (c === ",") {
          if (!lastWasDigit || points > 0) return "Invalid";
        } else if (c === "e") {
          exponents += 1;
          if (exponents > 1) return "Invalid";
        } else {
          return "Invalid";
        }
        lastWasDigit = false;
      }
      lastWasExponent = c === "e";
      if (c !== ",") buff += c;
    }

    if (buff === "") return "Intermediate";
    if (!MplDoubleValidator.NUMBER.test(buff) || !Number.isFinite(Number(buff))) return "Intermediate";
    return "Acceptable";
  }
}

class MplSpinBox extends QtDoubleSpinBoxView {
  typed() {
    if (this.validate(this.input.value)[0] !== "Invalid") return;
    this.input.value = this.before.text;
    this.input.setSelectionRange(this.before.start, this.before.end);
  }
}

class MplModelessDialog extends TomoVisModal {
  open() {
    this.layer.append(this.el);
    this.center();
    const target = this.el.querySelector("input, select, button, [tabindex='0']") || this.el;
    target.focus({ preventScroll: true });
    return new Promise((resolve) => { this.resolve = resolve; });
  }

  key(event) {
    if (event.key === "Escape") {
      event.preventDefault();
      event.stopPropagation();
      this.close(this.escape);
      return;
    }
    if (event.key === "Tab") this.trapFocus(event);
  }
}

class MplWindow extends MplModelessDialog {
  static SCREENED = ["pointerdown", "mousedown", "click", "dblclick", "contextmenu", "wheel"];

  constructor(options) {
    super(options);
    this.el.classList.add("tv-mpl-window");
    this.el.setAttribute("aria-modal", "false");

    this.closeBox       = TomoVisInput.el("button", "tv-mpl-window__close", "\u00d7");
    this.closeBox.type  = "button";
    this.closeBox.title = "Close";
    this.closeBox.setAttribute("aria-label", "Close");
    this.closeBox.addEventListener("pointerdown", (event) => event.stopPropagation());
    this.closeBox.addEventListener("click", () => this.close("Close"));
    this.titleBar.append(this.closeBox);

    for (const type of MplWindow.SCREENED) this.el.addEventListener(type, (event) => this.screen(event), { capture: true, passive: false });
    this.el.addEventListener("pointerup", () => requestAnimationFrame(() => this.raise()), true);
  }

  blocked() {
    return TomoVisModal.isOpen();
  }

  screen(event) {
    if (!this.blocked()) return;
    if (this.titleBar.contains(event.target) && !this.closeBox.contains(event.target)) return;
    event.preventDefault();
    event.stopPropagation();
  }

  raise() {
    if (!this.el.isConnected || this.blocked() || this.layer.lastElementChild === this.el) return;
    this.layer.append(this.el);
  }
}

class MplRubberBand {
  constructor(canvas) {
    this.canvas  = canvas;
    this.context = canvas.getContext("2d");
    this.dpr     = 1;
  }

  resize(width, height, dpr) {
    const pixelWidth  = Math.round(width * dpr);
    const pixelHeight = Math.round(height * dpr);
    if (this.canvas.width === pixelWidth && this.canvas.height === pixelHeight && this.dpr === dpr) return;
    this.dpr                 = dpr;
    this.canvas.width        = pixelWidth;
    this.canvas.height       = pixelHeight;
    this.canvas.style.width  = `${width}px`;
    this.canvas.style.height = `${height}px`;
  }

  clear() {
    this.context.clearRect(0, 0, this.canvas.width, this.canvas.height);
  }

  draw(message, frameHeight, dpr) {
    this.clear();
    if (message.x0 === -1 && message.y0 === -1 && message.x1 === -1 && message.y1 === -1) return;

    const rect = [message.x0, frameHeight - message.y0, message.x1 - message.x0, (frameHeight - message.y1) - (frameHeight - message.y0)].map(Math.trunc);
    const [x0, y0, w, h] = rect.map((value) => Math.trunc(value / dpr));
    const x1 = x0 + w;
    const y1 = y0 + h;
    const ctx = this.context;

    ctx.save();
    ctx.lineWidth = 1;
    ctx.setLineDash([3, 3]);
    for (const [color, offset] of [["#000000", 0], ["#ffffff", 3]]) {
      ctx.strokeStyle    = color;
      ctx.lineDashOffset = offset;
      for (const [ax, ay, bx, by] of [[x0, y0, x0, y1], [x0, y0, x1, y0], [x0, y1, x1, y1], [x1, y0, x1, y1]]) {
        ctx.beginPath();
        ctx.moveTo(ax * dpr + 0.5, ay * dpr + 0.5);
        ctx.lineTo(bx * dpr + 0.5, by * dpr + 0.5);
        ctx.stroke();
      }
    }
    ctx.restore();
  }
}

class MplToolbar {
  static ICONS = "/static/img/tomovis/mpl/";
  static ITEMS = [
    ["Home", "Reset original view", "home", "home"],
    ["Back", "Back to previous view", "back", "back"],
    ["Forward", "Forward to next view", "forward", "forward"],
    null,
    ["Pan", "Left button pans, Right button zooms\nx/y fixes axis, CTRL fixes aspect", "move", "pan"],
    ["Zoom", "Zoom to rectangle\nx/y fixes axis", "zoom_to_rect", "zoom"],
    ["Subplots", "Configure subplots", "subplots", "configure_subplots"],
    ["Customize", "Edit axis, curve and image parameters", "qt4_editor_options", "edit_parameters"],
    null,
    ["Save", "Save the figure", "filesave", "save_figure"],
  ];

  constructor(view) {
    this.view    = view;
    this.mode    = "";
    this.buttons = {};
    this.el      = TomoVisInput.el("div", "tv-mpl-toolbar");
    this.el.setAttribute("role", "toolbar");

    for (const item of MplToolbar.ITEMS) {
      if (!item) {
        this.el.append(TomoVisInput.el("span", "tv-mpl-toolbar__sep"));
        continue;
      }
      const [text, tooltip, image, method] = item;
      const button = TomoVisInput.noFocusButton(TomoVisInput.el("button", "tv-mpl-tool"));
      const icon   = TomoVisInput.el("img", "tv-mpl-tool__icon");
      button.type           = "button";
      button.title          = tooltip;
      button.dataset.method = method;
      button.setAttribute("aria-label", text);
      icon.src = `${MplToolbar.ICONS}${image}.svg`;
      icon.alt = "";
      button.append(icon);
      button.addEventListener("click", () => this.view.toolbarAction(method));
      this.buttons[method] = button;
      this.el.append(button);
    }
    for (const method of ["pan", "zoom"]) this.buttons[method].setAttribute("aria-pressed", "false");

    this.label = TomoVisInput.el("div", "tv-mpl-toolbar__message");
    this.label.setAttribute("aria-live", "off");
    this.el.append(this.label);
    this.reset();
  }

  reset() {
    this.setHistory(false, false);
    this.setMode("");
    this.setMessage("");
  }

  setMessage(text) {
    this.label.textContent = text;
  }

  setHistory(back, forward) {
    this.buttons.back.disabled    = !back;
    this.buttons.forward.disabled = !forward;
  }

  setMode(mode) {
    this.mode = mode === "NONE" ? "" : mode;
    for (const [method, name] of [["pan", "PAN"], ["zoom", "ZOOM"]]) {
      const on = this.mode === name;
      this.buttons[method].classList.toggle("is-checked", on);
      this.buttons[method].setAttribute("aria-pressed", String(on));
    }
  }

  echo(method) {
    const name = method === "pan" ? "PAN" : "ZOOM";
    this.setMode(this.mode === name ? "" : name);
  }
}

class MplAxesChooser {
  static async choose(ctx, axes) {
    const modal = new TomoVisModal({ title: "Customize", className: "tv-mpl-chooser", buttons: ["OK", "Cancel"], escape: "Cancel", layer: ctx.layer });
    const combo = ctx.kit.local("combo", { items: axes.map((entry) => entry.title) });
    combo.set({ index: 0, enabled: true });
    combo.el.addEventListener("keydown", (event) => {
      if (event.key === "Enter" && !combo.popup) modal.close("OK");
    }, { capture: true });
    modal.body.append(TomoVisInput.el("label", "tv-label", "Select Axes:"), combo.el);

    const answer = modal.open();
    combo.el.focus({ preventScroll: true });
    if (await answer !== "OK") return null;
    return axes[combo.index].index;
  }
}

class MplExportValuesWindow extends MplWindow {
  constructor(layer, text) {
    super({ title: "", className: "tv-mpl-export", buttons: [], layer, escape: "Close" });
    this.text            = TomoVisInput.el("textarea", "tv-mpl-export__text");
    this.text.readOnly   = true;
    this.text.spellcheck = false;
    this.text.value      = text;
    this.body.append(this.text);
  }

  open() {
    this.layer.append(this.el);
    this.center();
    if (!this.blocked()) this.text.focus({ preventScroll: true });
    return new Promise((resolve) => { this.resolve = resolve; });
  }
}

class MplSubplotDialog {
  constructor(view) {
    this.view      = view;
    this.ctx       = view.ctx;
    this.spinboxes = {};
    this.pending   = {};
    this.modal     = null;
  }

  async run() {
    const header = await this.view.op("subplots_open");
    if (!header) return;
    this.build(header.result);
    this.apply(header.result, true);
    const closed = this.modal.open();
    this.closeButton.focus({ preventScroll: true });
    await closed;
  }

  build(state) {
    this.modal = new TomoVisModal({ title: "", className: "tv-mpl-subplots", buttons: [], escape: "Close", layer: this.ctx.layer });
    const columns = TomoVisInput.el("div", "tv-mpl-subplots__columns");
    const actions = {
      "Export values" : () => this.exportValues(),
      "Tight layout"  : () => this.change("subplots_tight", {}),
      "Reset"         : () => this.change("subplots_reset", {}),
      "Close"         : () => this.modal.close("Close"),
    };

    for (const group of state.groups) {
      const column = TomoVisInput.el("div", "tv-mpl-subplots__column");
      const box    = this.ctx.kit.local("group", { title: group.title });
      const form   = TomoVisInput.el("div", "tv-mpl-form");
      for (const name of group.names) {
        const spin = new MplSpinBox(this.ctx.kit, "doubleSpin", null, { decimals: 3, step: 0.005, onChange: (value) => this.set(name, value) });
        this.spinboxes[name] = spin;
        form.append(TomoVisInput.el("label", "tv-label tv-mpl-form__label", name), spin.el);
      }
      box.body.append(form);
      column.append(box.el);
      for (const text of group.buttons) {
        const button = TomoVisInput.el("button", "tv-button", text);
        button.type = "button";
        button.addEventListener("click", actions[text]);
        if (text === "Close") this.closeButton = button;
        column.append(button);
      }
      columns.append(column);
    }
    this.modal.body.append(columns);
  }

  apply(state, force) {
    for (const [name, spin] of Object.entries(this.spinboxes)) {
      const [minimum, maximum] = state.ranges[name];
      const update = { minimum, maximum, decimals: 3 };
      if (force || !this.pending[name]) update.value = state.values[name];
      spin.set(update);
    }
  }

  set(name, value) {
    this.pending[name] = (this.pending[name] || 0) + 1;
    this.view.op("subplots_set", { name, value }, { coalesce: `figure:${this.view.id}:subplots:${name}` }).then((header) => {
      this.pending[name] -= 1;
      if (header) this.apply(header.result, false);
    }, (error) => {
      this.pending[name] -= 1;
      this.ctx.session.raiseUnreported(error);
    });
  }

  change(op, payload) {
    this.view.op(op, payload).then((header) => {
      if (header) this.apply(header.result, true);
    }, (error) => this.ctx.session.raiseUnreported(error));
  }

  exportValues() {
    this.view.op("subplots_export").then((header) => {
      if (header) this.view.showExportValues(header.result.text);
    }, (error) => this.ctx.session.raiseUnreported(error));
  }
}

class MplFormLayout {
  constructor(ctx, form, onEdit) {
    this.ctx      = ctx;
    this.form     = form;
    this.onEdit   = onEdit;
    this.sections = [];
    this.floats   = [];
    this.el       = this.build();
  }

  build() {
    const root  = TomoVisInput.el("div", "tv-mpl-formdialog");
    const tabs  = TomoVisInput.el("div", "tv-mpl-tabs");
    const pages = TomoVisInput.el("div", "tv-mpl-pages");
    tabs.setAttribute("role", "tablist");

    this.form.sections.forEach((section, index) => {
      const tab    = TomoVisInput.el("button", "tv-tab", section.title);
      const page   = TomoVisInput.el("div", "tv-mpl-page");
      const widget = section.kind === "combo" ? this.comboWidget(section) : this.formWidget(section.fields);
      tab.type = "button";
      tab.setAttribute("role", "tab");
      tab.addEventListener("click", () => this.showTab(index));
      page.append(widget.el);
      this.sections.push({ section, tab, page, forms: widget.forms });
      tabs.append(tab);
      pages.append(page);
    });
    root.append(tabs, pages);
    this.showTab(0);
    return root;
  }

  showTab(index) {
    this.sections.forEach((entry, i) => {
      const on = i === index;
      entry.tab.classList.toggle("is-current", on);
      entry.tab.setAttribute("aria-selected", String(on));
      entry.page.hidden = !on;
    });
  }

  comboWidget(section) {
    const wrap  = TomoVisInput.el("div", "tv-mpl-combowidget");
    const stack = TomoVisInput.el("div", "tv-mpl-combowidget__stack");
    const forms = section.pages.map((page) => this.formWidget(page.fields).forms[0]);
    const combo = this.ctx.kit.local("combo", { items: section.pages.map((page) => page.title), onChange: (index) => this.showPage(forms, index) });
    combo.set({ index: 0, enabled: true });
    forms.forEach((form) => stack.append(form.el));
    this.showPage(forms, 0);
    wrap.append(combo.el, stack);
    return { el: wrap, forms };
  }

  showPage(forms, index) {
    forms.forEach((form, i) => { form.el.hidden = i !== index; });
  }

  formWidget(fields) {
    const grid   = TomoVisInput.el("div", "tv-mpl-form");
    const values = [];
    for (const field of fields) {
      if (field.kind === "separator") {
        grid.append(TomoVisInput.el("span", "tv-mpl-form__label tv-mpl-form__sep", " "), TomoVisInput.el("span", "tv-mpl-form__sep", " "));
        continue;
      }
      if (field.kind === "comment") {
        grid.append(this.comment(field.value));
        continue;
      }
      const widget = this.field(field);
      values.push(widget);
      grid.append(TomoVisInput.el("label", "tv-label tv-mpl-form__label", field.label), widget.el);
    }
    const form = { el: grid, values: () => values.map((widget) => widget.value()) };
    return { el: grid, forms: [form] };
  }

  comment(value) {
    const row  = TomoVisInput.el("div", "tv-mpl-form__comment");
    const bold = /^<b>(.*)<\/b>$/.exec(value);
    if (bold) row.append(TomoVisInput.el("b", "", bold[1]));
    else row.textContent = value;
    return row;
  }

  field(field) {
    if (field.kind === "bool") {
      const view = this.ctx.kit.local("checkbox", {});
      view.set({ checked: field.value, enabled: true });
      return { el: view.el, value: () => view.checked };
    }
    if (field.kind === "choice") {
      const view = this.ctx.kit.local("combo", { items: field.choices });
      view.set({ index: field.value, enabled: true });
      return { el: view.el, value: () => view.index };
    }
    if (field.kind === "int") {
      const view = this.ctx.kit.local("spin", {});
      view.set({ minimum: -1e9, maximum: 1e9, value: field.value, enabled: true });
      return { el: view.el, value: () => view.value };
    }
    if (field.kind === "color") return this.colorField(field);

    const view = this.ctx.kit.local("line", { onChange: () => this.onEdit() });
    view.set({ text: field.value, enabled: true });
    view.el.classList.add("tv-mpl-form__line");
    if (field.kind === "float") {
      view.validator = new MplDoubleValidator();
      this.floats.push(view);
      view.input.setSelectionRange(0, 0);
    }
    return { el: view.el, value: () => view.input.value };
  }

  colorField(field) {
    const row    = TomoVisInput.el("span", "tv-mpl-color");
    const line   = this.ctx.kit.local("line", { onReturn: () => this.colorEdited(state) });
    const button = TomoVisInput.el("button", "tv-mpl-color__button");
    const swatch = TomoVisInput.el("span", "tv-mpl-color__swatch");
    const state  = { line, swatch, color: MplColors.quantize(MplColors.toRgba(field.value)) };

    line.set({ text: field.value, enabled: true });
    line.el.classList.add("tv-mpl-form__line");
    line.input.addEventListener("blur", () => this.colorEdited(state));
    button.type = "button";
    button.setAttribute("aria-label", "Choose color");
    button.append(swatch);
    button.addEventListener("click", () => this.chooseColor(state));
    this.paintSwatch(state);
    row.append(line.el, button);
    return { el: row, value: () => line.input.value };
  }

  paintSwatch(state) {
    const [r, g, b, a] = MplColors.to255(state.color || MplColors.INVALID);
    state.swatch.style.background = `rgba(${r}, ${g}, ${b}, ${a / 255})`;
  }

  setColor(state, color) {
    if (MplColors.same(color, state.color)) return;
    state.color = color;
    this.paintSwatch(state);
    state.line.set({ text: MplColors.toHex(color || MplColors.INVALID) });
  }

  colorEdited(state) {
    const parsed = MplColors.toRgba(state.line.input.value);
    if (parsed === "unknown") return;
    this.setColor(state, parsed ? MplColors.quantize(parsed) : null);
  }

  async chooseColor(state) {
    const initial = MplColors.to255(state.color || MplColors.INVALID);
    const chosen  = await this.ctx.dialogs.color({ initial, title: "", alpha: true });
    if (chosen.accepted) this.setColor(state, chosen.color.map((value) => value / 255));
  }

  valid() {
    return this.floats.every((view) => view.validate(view.input.value) === "Acceptable");
  }

  values() {
    return this.sections.map((entry) => entry.section.kind === "combo" ? entry.forms.map((form) => form.values()) : entry.forms[0].values());
  }
}

class MplFigureOptionsDialog {
  constructor(view, axes, form) {
    this.view   = view;
    this.ctx    = view.ctx;
    this.axes   = axes;
    this.modal  = new MplModelessDialog({ title: form.title, className: "tv-mpl-options", buttons: [], escape: "Cancel", layer: this.ctx.layer });
    this.layout = new MplFormLayout(this.ctx, form, () => this.updateButtons());
    this.closed = false;

    const footer = TomoVisInput.el("div", "tv-modal__buttons");
    this.buttons = {};
    for (const text of ["OK", "Cancel", "Apply"]) {
      const button = TomoVisInput.el("button", "tv-button", text);
      button.type = "button";
      this.buttons[text] = button;
      footer.append(button);
    }
    this.buttons.OK.addEventListener("click", () => this.accept());
    this.buttons.Cancel.addEventListener("click", () => this.close());
    this.buttons.Apply.addEventListener("click", () => this.apply());
    this.modal.body.append(this.layout.el);
    this.modal.el.append(footer);
    this.updateButtons();
  }

  open() {
    const closed = this.modal.open();
    closed.then(() => { this.closed = true; });
    return closed;
  }

  updateButtons() {
    const valid = this.layout.valid();
    this.buttons.OK.disabled    = !valid;
    this.buttons.Apply.disabled = !valid;
  }

  apply() {
    return this.view.op("options_apply", { axes: this.axes, values: this.layout.values() }).catch((error) => this.ctx.session.raiseUnreported(error));
  }

  accept() {
    this.apply();
    this.close();
  }

  close() {
    if (!this.closed) this.modal.close("Cancel");
  }
}

class MplFigureView {
  static TOOLBAR_OPS      = new Set(["home", "back", "forward", "pan", "zoom"]);
  static TOOLBAR_MESSAGES = new Set(["message", "history_buttons", "navigate_mode"]);
  static IGNORED_MESSAGES = new Set(["resize", "figure_label"]);
  static OWNED_KEYS       = new Set(["ctrl+s", "ctrl+f", "F1", " ", "ArrowUp", "ArrowDown", "ArrowLeft", "ArrowRight", "PageUp", "PageDown", "Home", "End", "Backspace"]);
  static MODIFIERS        = { Control: "ctrl", Alt: "alt", Shift: "shift", Meta: "meta" };

  constructor(root, ctx, figureId, { toolbar = true, focusable = false, size = null, attach = true, persistent = false, onClose = null } = {}) {
    this.root       = root;
    this.ctx        = ctx;
    this.id         = figureId;
    this.focusable  = focusable;
    this.fixed      = size;
    this.persistent = persistent;
    this.onClose    = onClose;
    this.attached   = false;
    this.disposed   = false;
    this.sid        = null;
    this.sent       = null;
    this.mode       = "full";
    this.drawing    = Promise.resolve();
    this.frames     = 0;
    this.options    = null;
    this.exported   = null;

    this.el      = TomoVisInput.el("div", "tv-mpl");
    this.toolbar = toolbar ? new MplToolbar(this) : null;
    this.wrap    = TomoVisInput.el("div", "tv-mpl-canvaswrap");
    this.canvas  = TomoVisInput.el("canvas", "tv-mpl-canvas");
    this.band    = new MplRubberBand(TomoVisInput.el("canvas", "tv-mpl-rubberband"));
    this.context = this.canvas.getContext("2d");
    this.context.imageSmoothingEnabled = false;
    this.wrap.dataset.figure = figureId;
    this.wrap.append(this.canvas, this.band.canvas);
    if (this.toolbar) this.el.append(this.toolbar.el);
    this.el.append(this.wrap);
    this.applySize();
    root.append(this.el);

    this.bindPointer();
    if (focusable) this.bindKeys();
    this.handlers = {
      figure   : ctx.bus.on("figure", (payload) => { if (payload.id === this.id) this.apply(payload); }),
      resync   : ctx.bus.on("resync", () => this.refresh()),
      snapshot : ctx.bus.on("snapshot", () => this.follow()),
    };
    this.onWindowResize = () => this.measure();
    this.onFullScreen   = () => this.applySize();
    window.addEventListener("resize", this.onWindowResize);
    document.addEventListener("fullscreenchange", this.onFullScreen);
    this.observer = new ResizeObserver(() => this.measure());
    this.observer.observe(this.wrap);
    if (attach) this.attach();
  }

  fullScreen() {
    return document.fullscreenElement === this.el;
  }

  applySize() {
    const fixed = Boolean(this.fixed) && !this.fullScreen();
    this.wrap.classList.toggle("tv-mpl-canvaswrap--fixed", fixed);
    this.wrap.style.width  = fixed ? `${this.fixed[0]}px` : "";
    this.wrap.style.height = fixed ? `${this.fixed[1]}px` : "";
  }

  attach() {
    this.attached = true;
    this.sid      = this.ctx.session.sid;
    this.sent     = null;
    if (this.toolbar) this.toolbar.reset();
    this.measure();
  }

  detach() {
    this.attached = false;
    this.sent     = null;
    if (this.toolbar) this.toolbar.reset();
    this.band.clear();
    this.context.clearRect(0, 0, this.canvas.width, this.canvas.height);
    if (this.options) this.options.close();
  }

  follow() {
    if (this.attached && this.ctx.session.sid !== this.sid) this.sessionChanged();
  }

  sessionChanged() {
    if (this.persistent) this.attach();
    else this.detach();
  }

  live() {
    if (!this.attached || this.disposed) return false;
    if (this.ctx.session.sid !== this.sid) this.sessionChanged();
    return this.attached;
  }

  ratio() {
    return this.sent ? this.sent.dpr : (window.devicePixelRatio || 1);
  }

  measure() {
    if (!this.attached || this.disposed) return;
    const dpr    = window.devicePixelRatio || 1;
    const fixed  = this.fixed && !this.fullScreen();
    const width  = fixed ? this.fixed[0] : this.wrap.clientWidth;
    const height = fixed ? this.fixed[1] : this.wrap.clientHeight;
    if (width < 1 || height < 1) return;

    this.band.resize(width, height, dpr);
    if (this.sent && this.sent.width === width && this.sent.height === height && this.sent.dpr === dpr) return;
    this.sent = { width, height, dpr };
    this.op("resize", { width, height, dpr }, { coalesce: `figure:${this.id}:resize` }).catch((error) => this.ctx.session.raiseUnreported(error));
  }

  refresh() {
    if (!this.attached) return;
    this.op("refresh").catch((error) => this.ctx.session.raiseUnreported(error));
  }

  op(name, payload = {}, options = {}) {
    if (!this.live()) return Promise.resolve(null);
    return this.ctx.session.figure(this.id, name, payload, options);
  }

  apply({ messages, frames }) {
    for (const message of messages) {
      if (MplFigureView.TOOLBAR_MESSAGES.has(message.type)) {
        if (this.toolbar) this.toolbarMessage(message);
      } else if (message.type === "image_mode") {
        this.mode = message.mode;
      } else if (message.type === "frame") {
        this.drawFrame(frames[message.blob], this.mode);
      } else if (message.type === "cursor") {
        this.wrap.style.cursor = message.cursor;
      } else if (message.type === "rubberband") {
        this.band.draw(message, this.canvas.height, this.ratio());
      } else if (message.type === "save") {
        this.saveFigure();
      } else if (message.type === "full_screen_toggle") {
        this.fullScreenToggle();
      } else if (message.type === "close") {
        this.closeWindow();
      } else if (!MplFigureView.IGNORED_MESSAGES.has(message.type)) {
        throw new Error(`TomoVis figure ${this.id} received an unknown message ${message.type}`);
      }
    }
  }

  fullScreenToggle() {
    const change = this.fullScreen() ? document.exitFullscreen() : this.el.requestFullscreen();
    change.catch((error) => this.ctx.session.raiseUnreported(error));
  }

  closeWindow() {
    if (this.fullScreen()) document.exitFullscreen().catch((error) => this.ctx.session.raiseUnreported(error));
    this.detach();
    if (this.onClose) this.onClose();
  }

  toolbarMessage(message) {
    if (message.type === "message") this.toolbar.setMessage(message.message);
    else if (message.type === "history_buttons") this.toolbar.setHistory(message.Back, message.Forward);
    else this.toolbar.setMode(message.mode);
  }

  drawFrame(blob, mode) {
    const decoded = createImageBitmap(blob, { colorSpaceConversion: "none" });
    this.drawing  = this.drawing.then(() => decoded).then((bitmap) => this.paint(bitmap, mode)).catch((error) => {
      setTimeout(() => { throw error; });
    });
  }

  paint(bitmap, mode) {
    if (this.disposed) return;
    const ratio = this.ratio();
    if (mode === "full") {
      if (this.canvas.width !== bitmap.width || this.canvas.height !== bitmap.height) {
        this.canvas.width  = bitmap.width;
        this.canvas.height = bitmap.height;
        this.context.imageSmoothingEnabled = false;
      } else {
        this.context.clearRect(0, 0, this.canvas.width, this.canvas.height);
      }
      this.canvas.style.width  = `${bitmap.width / ratio}px`;
      this.canvas.style.height = `${bitmap.height / ratio}px`;
    }
    this.context.drawImage(bitmap, 0, 0);
    bitmap.close();
    this.frames += 1;
  }

  bindPointer() {
    const wrap = this.wrap;
    wrap.addEventListener("pointerdown", (event) => wrap.setPointerCapture(event.pointerId));
    wrap.addEventListener("mousedown", (event) => this.press(event));
    wrap.addEventListener("mouseup", (event) => this.mouse(event, "button_release"));
    wrap.addEventListener("mousemove", (event) => this.mouse(event, "motion_notify"));
    wrap.addEventListener("mouseenter", (event) => this.mouse(event, "figure_enter"));
    wrap.addEventListener("mouseleave", (event) => this.mouse(event, "figure_leave"));
    wrap.addEventListener("wheel", (event) => this.wheel(event), { passive: true });
    wrap.addEventListener("contextmenu", (event) => event.preventDefault());
    wrap.addEventListener("dragstart", (event) => event.preventDefault());
  }

  press(event) {
    event.preventDefault();
    if (this.focusable) this.wrap.focus({ preventScroll: true });
    this.mouse(event, event.detail > 1 && event.detail % 2 === 0 ? "dblclick" : "button_press");
  }

  wheel(event) {
    const step = TomoVisInput.angleDelta(event).y / 120;
    if (step) this.mouse(event, "scroll", step);
  }

  static modifiers(event) {
    const mods = [];
    if (event.ctrlKey) mods.push("ctrl");
    if (event.altKey) mods.push("alt");
    if (event.shiftKey) mods.push("shift");
    if (event.metaKey) mods.push("meta");
    return mods;
  }

  mouse(event, type, step = 0) {
    const rect = this.canvas.getBoundingClientRect();
    const dpr  = this.ratio();
    const data = {
      type,
      x         : Math.floor(event.clientX - rect.left) * dpr,
      y         : Math.floor(event.clientY - rect.top) * dpr,
      button    : event.button,
      buttons   : event.buttons,
      modifiers : MplFigureView.modifiers(event),
    };
    if (type === "scroll") data.step = step;
    const options = type === "motion_notify" ? { coalesce: `figure:${this.id}:motion` } : {};
    this.op("mouse", { event: data }, options).catch((error) => this.ctx.session.raiseUnreported(error));
  }

  bindKeys() {
    this.wrap.tabIndex = 0;
    this.wrap.addEventListener("keydown", (event) => this.key(event, "key_press"));
    this.wrap.addEventListener("keyup", (event) => this.key(event, "key_release"));
  }

  static keyString(event) {
    if (["Tab", "Unidentified", "Process"].includes(event.key)) return null;
    const own  = MplFigureView.MODIFIERS[event.key];
    const mods = [];
    if (event.ctrlKey && own !== "ctrl") mods.push("ctrl+");
    if (event.altKey && own !== "alt") mods.push("alt+");
    if (event.shiftKey && own !== "shift" && event.key.length !== 1) mods.push("shift+");
    if (event.metaKey && own !== "meta") mods.push("meta+");
    return `${mods.join("")}k${event.key}`;
  }

  key(event, type) {
    const key = MplFigureView.keyString(event);
    if (key === null) return;
    const plain = !event.ctrlKey && !event.metaKey && !event.altKey;
    const typed = plain && event.key.length === 1;
    if (typed || MplFigureView.OWNED_KEYS.has(plain ? event.key : key.replace("k", "").toLowerCase())) event.preventDefault();
    this.op("key", { event: { type, key } }).catch((error) => this.ctx.session.raiseUnreported(error));
  }

  toolbarAction(method) {
    if (MplFigureView.TOOLBAR_OPS.has(method)) {
      if (method === "pan" || method === "zoom") this.toolbar.echo(method);
      this.op("toolbar", { name: method }).catch((error) => this.ctx.session.raiseUnreported(error));
    } else if (method === "configure_subplots") {
      new MplSubplotDialog(this).run().catch((error) => this.ctx.session.raiseUnreported(error));
    } else if (method === "edit_parameters") {
      this.editParameters().catch((error) => this.ctx.session.raiseUnreported(error));
    } else if (method === "save_figure") {
      this.saveFigure();
    }
  }

  showExportValues(text) {
    if (this.exported) this.exported.close("Close");
    this.exported = new MplExportValuesWindow(this.ctx.layer, text);
    this.exported.open();
  }

  async editParameters() {
    const listed = await this.op("options_axes");
    if (!listed) return;
    const axes = listed.result.axes;
    if (axes.length === 0) return;

    const index = axes.length === 1 ? axes[0].index : await MplAxesChooser.choose(this.ctx, axes);
    if (index === null) return;
    const opened = await this.op("options_form", { axes: index });
    if (!opened) return;
    if (this.options) this.options.close();
    this.options = new MplFigureOptionsDialog(this, index, opened.result);
    this.options.open();
  }

  saveFigure() {
    this.save().catch((error) => this.ctx.session.raiseUnreported(error));
  }

  async save() {
    const started = await this.op("save_start");
    if (!started) return;
    const start  = started.result;
    const chosen = await this.ctx.dialogs.file({ mode: "save", title: start.title, filters: start.filters, selected_filter: start.selected_filter, directory: start.directory, file: start.file });
    if (!chosen.accepted || !chosen.path) return;
    await this.op("save", { path: chosen.path });
  }

  dispose() {
    this.disposed = true;
    this.attached = false;
    this.observer.disconnect();
    window.removeEventListener("resize", this.onWindowResize);
    document.removeEventListener("fullscreenchange", this.onFullScreen);
    for (const [topic, fn] of Object.entries(this.handlers)) this.ctx.bus.off(topic, fn);
    if (this.options) this.options.close();
    if (this.exported) this.exported.close("Close");
    this.el.remove();
  }
}

window.MplColors              = MplColors;
window.MplDoubleValidator     = MplDoubleValidator;
window.MplSpinBox             = MplSpinBox;
window.MplModelessDialog      = MplModelessDialog;
window.MplRubberBand          = MplRubberBand;
window.MplToolbar             = MplToolbar;
window.MplAxesChooser         = MplAxesChooser;
window.MplWindow              = MplWindow;
window.MplExportValuesWindow  = MplExportValuesWindow;
window.MplSubplotDialog       = MplSubplotDialog;
window.MplFormLayout          = MplFormLayout;
window.MplFigureOptionsDialog = MplFigureOptionsDialog;
window.MplFigureView          = MplFigureView;
