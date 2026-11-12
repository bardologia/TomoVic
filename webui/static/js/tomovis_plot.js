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
  static SLIDER_MIN   = 200;

  constructor(root, ctx) {
    this.root     = root;
    this.ctx      = ctx;
    this.controls = {};

    root.classList.add("tv-plot");
    this.figureHost = TomoVisInput.el("div", "tv-plot__figure");
    this.row        = TomoVisInput.el("div", "tv-row tv-plot__controls");
    this.stretch    = TomoVisInput.el("span", "tv-stretch");
    root.append(this.figureHost, this.row);

    this.figure = new MplFigureView(this.figureHost, ctx, "plot", { persistent: true });
    this.build();
    this.observeRow();
    ctx.dialogs.register("axes", (request, context) => new TomoVisAxesDialog(context, request).run());
  }

  label(text) {
    return this.ctx.kit.local("label", { text }).el;
  }

  bound(kind, name, options = {}) {
    const view = this.ctx.kit.bound(kind, name, options);
    this.controls[name] = view;
    return view.el;
  }

  build() {
    const names  = this.ctx.tables.plot_colormaps.names;
    const spacer = TomoVisInput.el("span", "tv-plot__spacer");
    const button = { maxWidth: TomoVisPlotTab.BUTTON_WIDTH };

    this.row.append(
      this.label("Normalize"),
      this.bound("checkbox", "tab2ChkBox1"),
      this.label("Histogram\nequalization"),
      this.bound("checkbox", "tab2ChkBox2"),
      this.bound("slider", "tab2Slider"),
      spacer,
      this.label("Colormap"),
      this.bound("combo", "tab2ComboBox", { items: names }),
      this.label("X [m]"),
      this.bound("checkbox", "tab2ChkBox3"),
      this.bound("doubleSpin", "tab2SpinBox", { maxWidth: TomoVisPlotTab.SPIN_WIDTH, decimals: 2, step: 1 }),
      this.label("Full View"),
      this.bound("checkbox", "tab2ChkBox4"),
      this.bound("button", "tab2AxesButton", { text: "Axes", ...button }),
      this.bound("button", "tab2PlotButton", { text: "Plot", ...button }),
      this.bound("button", "tab2ClearButton", { text: "Clear", ...button }),
      this.stretch,
    );
  }

  observeRow() {
    const slider  = this.controls.tab2Slider.el;
    this.rowWatch = new ResizeObserver(() => this.fitSlider());
    this.rowWatch.observe(this.row);
    for (const child of this.row.children) if (child !== slider && child !== this.stretch) this.rowWatch.observe(child);
  }

  fitSlider() {
    const slider = this.controls.tab2Slider.el;
    const style  = getComputedStyle(this.row);
    const width  = this.row.clientWidth - parseFloat(style.paddingLeft) - parseFloat(style.paddingRight);
    if (width <= 0) return;

    let taken = parseFloat(style.columnGap) * (this.row.children.length - 1) + parseFloat(getComputedStyle(this.stretch).marginLeft);
    for (const child of this.row.children) if (child !== slider && child !== this.stretch) taken += child.getBoundingClientRect().width;
    slider.style.marginRight = `${Math.min(0, width - taken - TomoVisPlotTab.SLIDER_MIN)}px`;
  }

  activate() {
    this.figure.measure();
  }

  deactivate() {}
}

window.TomoVisAxesDialog = TomoVisAxesDialog;
window.TomoVisPlotTab    = TomoVisPlotTab;
