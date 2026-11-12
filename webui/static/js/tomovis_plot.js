"use strict";

class TomoVisAxesDialog {
  static ROWS = [
    ["x_label", "X label", "text"],
    ["z_label", "Z label", "text"],
    ["x_min",   "X min",   "number"],
    ["x_max",   "X max",   "number"],
    ["z_min",   "Z min",   "number"],
    ["z_max",   "Z max",   "number"],
  ];

  constructor(ctx, request) {
    this.ctx     = ctx;
    this.request = request;
    this.fields  = {};
    this.modal   = null;
  }

  build() {
    const request = this.request;
    this.modal = new TomoVisModal({ title: request.title, className: "tv-axes-dialog", buttons: ["OK", "Cancel"], escape: "Cancel", layer: this.ctx.layer });

    const grid = TomoVisInput.el("div", "tv-axes-dialog__grid");
    for (const [key, label, kind] of TomoVisAxesDialog.ROWS) {
      const view = kind === "text" ? this.lineField(request.values[key]) : this.numberField(request.values[key]);
      view.el.dataset.field = key;
      this.fields[key] = { kind, view };
      grid.append(TomoVisInput.el("label", "tv-label", label), view.el);
    }
    this.modal.body.append(grid);
  }

  lineField(text) {
    const view = this.ctx.kit.local("line", { onReturn: () => this.modal.close("OK") });
    view.set({ text, enabled: true });
    return view;
  }

  numberField(value) {
    const request = this.request;
    const view    = this.ctx.kit.local("doubleSpin", { decimals: request.decimals, step: request.step, onReturn: () => this.modal.close("OK") });
    view.set({ decimals: request.decimals, minimum: request.range[0], maximum: request.range[1], singleStep: request.step, value, enabled: true });
    return view;
  }

  values() {
    const values = {};
    for (const [key, field] of Object.entries(this.fields)) values[key] = field.kind === "text" ? field.view.input.value : field.view.value;
    return values;
  }

  async run() {
    this.build();
    const answer = this.modal.open();
    const first  = this.fields.x_label.view.input;
    first.focus({ preventScroll: true });
    first.setSelectionRange(first.value.length, first.value.length);
    if (await answer !== "OK") return { accepted: false };
    return { accepted: true, values: this.values() };
  }
}

class TomoVisPlotTab {
  static SPIN_WIDTH   = 180;
  static BUTTON_WIDTH = 100;
  static BUTTON_HINT  = 80;
  static SLIDER_MIN   = 200;
  static SPACER       = 5;
  static SPACING      = 6;
  static ROW_HEIGHT   = 39;
  static CHECK_SIZE   = [14, 15];

  constructor(root, ctx) {
    this.root     = root;
    this.ctx      = ctx;
    this.controls = {};

    root.classList.add("tv-plot");
    this.figureHost = TomoVisInput.el("div", "tv-plot__figure");
    this.row        = TomoVisInput.el("div", "tv-plot__controls");
    this.stretch    = TomoVisInput.el("span", "tv-stretch");
    root.append(this.figureHost, this.row);

    this.figure = new MplFigureView(this.figureHost, ctx, "plot", { persistent: true });
    this.build();
    this.observeRow();
    ctx.bus.on("snapshot", () => this.layoutRow());
    ctx.dialogs.register("axes", (request, context) => new TomoVisAxesDialog(context, request).run());
  }

  label(text) {
    const width = Math.max(...text.split("\n").map((line) => QtFontMetrics.labelWidth(line, QtFontMetrics.WINDOW)));
    return { el: this.ctx.kit.local("label", { text }).el, hint: () => width, height: TomoVisPlotTab.ROW_HEIGHT };
  }

  bound(kind, name, options, cell) {
    const view = this.ctx.kit.bound(kind, name, options);
    this.controls[name] = view;
    return { el: view.el, ...cell };
  }

  check(name) {
    const [width, height] = TomoVisPlotTab.CHECK_SIZE;
    return this.bound("checkbox", name, {}, { hint: () => width, height });
  }

  button(name, text) {
    return this.bound("button", name, { text, maxWidth: TomoVisPlotTab.BUTTON_WIDTH }, { hint: () => TomoVisPlotTab.BUTTON_HINT, max: TomoVisPlotTab.BUTTON_WIDTH, height: 28 });
  }

  build() {
    const names  = this.ctx.tables.plot_colormaps.names;
    const spacer = { el: TomoVisInput.el("span", "tv-plot__spacer"), hint: () => TomoVisPlotTab.SPACER, max: TomoVisPlotTab.SPACER, empty: true, height: 0 };

    this.cells = [
      this.label("Normalize"),
      this.check("tab2ChkBox1"),
      this.label("Histogram\nequalization"),
      this.check("tab2ChkBox2"),
      this.bound("slider", "tab2Slider", {}, { hint: () => TomoVisPlotTab.SLIDER_MIN, floor: TomoVisPlotTab.SLIDER_MIN, expansive: true, height: 15 }),
      spacer,
      this.label("Colormap"),
      this.bound("combo", "tab2ComboBox", { items: names, qtFont: QtFontMetrics.APP, styleSheet: true }, { hint: () => this.controls.tab2ComboBox.sizeHint(), height: 32 }),
      this.label("X [m]"),
      this.check("tab2ChkBox3"),
      this.bound("doubleSpin", "tab2SpinBox", { maxWidth: TomoVisPlotTab.SPIN_WIDTH, decimals: 2, step: 1 }, { hint: () => this.controls.tab2SpinBox.sizeHint(QtFontMetrics.WINDOW), max: TomoVisPlotTab.SPIN_WIDTH, height: 29 }),
      this.label("Full View"),
      this.check("tab2ChkBox4"),
      this.button("tab2AxesButton", "Axes"),
      this.button("tab2PlotButton", "Plot"),
      this.button("tab2ClearButton", "Clear"),
      { el: this.stretch, hint: () => 0, expansive: true, empty: true, height: 0 },
    ];
    this.row.append(...this.cells.map((cell) => cell.el));
  }

  observeRow() {
    this.rowWatch = new ResizeObserver(() => this.layoutRow());
    this.rowWatch.observe(this.row);
  }

  layoutRow() {
    const width = this.row.clientWidth;
    if (width <= 0) return;
    const chain = this.cells.map((cell) => new QtLayoutStruct({ sizeHint: cell.hint(), minimumSize: cell.hint(), maximumSize: cell.max || QtLayoutStruct.MAX, expansive: Boolean(cell.expansive), empty: Boolean(cell.empty), spacing: TomoVisPlotTab.SPACING }));
    QtLayoutEngine.geomCalc(chain, 0, chain.length, 0, width);
    this.cells.forEach((cell, i) => {
      const box  = chain[i];
      const item = Math.min(box.size, cell.max || QtLayoutStruct.MAX);
      const top  = Math.trunc((TomoVisPlotTab.ROW_HEIGHT - cell.height) / 2);

      cell.el.style.left   = `${box.pos + Math.trunc((box.size - item) / 2)}px`;
      cell.el.style.top    = `${top}px`;
      cell.el.style.width  = `${Math.max(item, cell.floor || 0)}px`;
      cell.el.style.height = `${cell.height}px`;
    });
  }

  activate() {
    this.figure.measure();
  }

  deactivate() {}
}

window.TomoVisAxesDialog = TomoVisAxesDialog;
window.TomoVisPlotTab    = TomoVisPlotTab;
