"use strict";

class PgPlotDataItem {
  constructor(plot, pen) {
    this.plot     = plot;
    this.curve    = new PgPlotCurve({ pen });
    this.rawX     = [];
    this.rawY     = [];
    this.visible  = true;
    this.curve.owner = this;
  }

  setData(x, y, pen) {
    this.rawX = Array.from(x);
    this.rawY = Array.from(y);
    if (pen !== undefined) this.curve.setPen(pen);
    this.refresh();
  }

  name() {
    return null;
  }

  getData() {
    return [this.rawX, this.rawY];
  }

  setVisible(visible) {
    this.visible       = visible;
    this.curve.visible = visible;
    if (this.plot.vb) this.plot.vb.itemBoundsChanged(this.curve);
  }

  static fourier(x, y) {
    const dx      = x.slice(1).map((v, i) => v - x[i]);
    const uniform = !dx.some((d) => Math.abs(d - dx[0]) > Math.abs(dx[0]) / 1000.0);
    let xs        = x;
    let ys        = y;
    if (!uniform) {
      xs = PgImageItem.linspace(x[0], x[x.length - 1], x.length);
      ys = xs.map((v) => PgPlotDataItem.interp(v, x, y));
    }
    const n    = ys.length;
    const half = Math.floor(n / 2) + 1;
    const d    = (xs[xs.length - 1] - xs[0]) / (xs.length - 1);
    const fx   = [];
    const fy   = [];
    for (let k = 0; k < half; k += 1) {
      let re = 0;
      let im = 0;
      for (let t = 0; t < n; t += 1) {
        const a = (-2 * Math.PI * k * t) / n;
        re += ys[t] * Math.cos(a);
        im += ys[t] * Math.sin(a);
      }
      fx.push(k / (n * d));
      fy.push(Math.hypot(re / n, im / n));
    }
    return [fx, fy];
  }

  static interp(v, x, y) {
    if (v <= x[0]) return y[0];
    if (v >= x[x.length - 1]) return y[y.length - 1];
    let i = 1;
    while (x[i] < v) i += 1;
    const f = (v - x[i - 1]) / (x[i] - x[i - 1]);
    return y[i - 1] + (y[i] - y[i - 1]) * f;
  }

  displayData() {
    const o = this.plot.opts;
    let x   = this.rawX.slice();
    let y   = this.rawY.slice();
    if (x.length === 0) return [x, y];
    if (o.subtractMean) {
      const mean = y.reduce((a, b) => a + b, 0) / y.length;
      y = y.map((v) => v - mean);
    }
    if (o.fft && x.length > 1) {
      [x, y] = PgPlotDataItem.fourier(x, y);
      if (o.logX) {
        x = x.slice(1);
        y = y.slice(1);
      }
    }
    if (o.derivative) {
      y = this.rawY.slice(1).map((v, i) => (v - this.rawY[i]) / (this.rawX[i + 1] - this.rawX[i]));
      x = x.slice(0, -1);
    }
    if (o.phasemap) {
      x = this.rawY.slice(0, -1);
      y = this.rawY.slice(1).map((v, i) => (v - this.rawY[i]) / (this.rawX[i + 1] - this.rawX[i]));
    }
    if (o.logX) x = x.map((v) => (v > 0 ? Math.log10(v) : NaN));
    if (o.logY) y = y.map((v) => (v > 0 ? Math.log10(v) : NaN));

    if (o.clipToView && this.plot.vb && x.length > 1) {
      const vr = this.plot.vb.viewRect();
      let i0   = 0;
      let i1   = x.length;
      while (i0 < x.length && x[i0] < vr.x) i0 += 1;
      while (i1 > 0 && x[i1 - 1] > vr.x + vr.w) i1 -= 1;
      i0 = Math.max(0, i0 - 1);
      i1 = Math.min(x.length, i1 + 1);
      x  = x.slice(i0, i1);
      y  = y.slice(i0, i1);
    }
    let ds = o.downsample ? o.downsampleFactor : 1;
    if (o.downsample && o.autoDownsample && this.plot.vb && x.length > 1) {
      const vr    = this.plot.vb.viewRect();
      const dx    = (x[x.length - 1] - x[0]) / (x.length - 1);
      const x0    = (vr.x - x[0]) / dx;
      const x1    = (vr.x + vr.w - x[0]) / dx;
      const width = this.plot.vb.width();
      if (width !== 0) ds = Math.trunc(Math.max(1, Math.trunc((x1 - x0) / (width * 5.0))));
    }
    if (ds > 1) [x, y] = PgPlotDataItem.downsample(x, y, ds, o.downsampleMethod);
    return [x, y];
  }

  static downsample(x, y, ds, method) {
    if (method === "subsample") return [x.filter((_, i) => i % ds === 0), y.filter((_, i) => i % ds === 0)];
    const n = Math.floor(x.length / ds);
    if (method === "mean") {
      const xs = [];
      const ys = [];
      for (let i = 0; i < n; i += 1) {
        xs.push(x[i * ds]);
        ys.push(y.slice(i * ds, (i + 1) * ds).reduce((a, b) => a + b, 0) / ds);
      }
      return [xs, ys];
    }
    const xs = [];
    const ys = [];
    for (let i = 0; i < n; i += 1) {
      const chunk = y.slice(i * ds, (i + 1) * ds);
      xs.push(x[i * ds], x[i * ds]);
      ys.push(Math.min(...chunk), Math.max(...chunk));
    }
    return [xs, ys];
  }

  refresh() {
    const [x, y] = this.displayData();
    this.curve.setData(x, y);
  }
}

class PgRoiPlot {
  constructor(ctx, host, name) {
    this.ctx       = ctx;
    this.host      = host;
    this.view      = new PgGraphicsView(host, { onLayout: (w, h) => this.layout(w, h), className: "tv-pg-plot" });
    this.vb        = new PgViewBox({ name });
    this.vb.attach(this.view);
    this.left      = new PgAxisItem("left", { linkView: this.vb });
    this.bottom    = new PgAxisItem("bottom", { linkView: this.vb });
    this.items     = [];
    this.curves    = [];
    this.mouseHovering = false;
    this.autoBtn   = { visible: false, rect: { x: 0, y: 0, w: 14, h: 14 } };
    this.opts = {
      fft: false, subtractMean: false, logX: false, logY: false, derivative: false, phasemap: false,
      downsample: false, downsampleFactor: 1, autoDownsample: true, downsampleMethod: "peak", clipToView: false,
      maxTraces: false, maxTracesCount: 0, forgetTraces: false,
      average: false, alphaGroup: true, autoAlpha: false, alpha: 1000,
      xGrid: false, yGrid: false, gridAlpha: 128, points: true, autoPoints: true,
    };
    this.view.addWidget(this.vb);
    this.view.addWidget(this.left);
    this.view.addWidget(this.bottom);
    this.view.addWidget(this);
    this.vb.parentMenus = [{ text: "Plot Options", submenu: () => this.optionsMenu() }];
    for (const axis of [this.left, this.bottom]) axis.sigSizeChanged.connect(() => requestAnimationFrame(() => this.layout(this.view.width, this.view.height)));
    this.vb.sigStateChanged.connect(() => this.updateButtons());
    this.vb.sigRangeChanged.connect(() => {
      if (this.opts.clipToView || (this.opts.downsample && this.opts.autoDownsample)) this.curves.forEach((c) => c.refresh());
    });
  }

  layout(w, h) {
    const leftW   = this.left.visible ? Math.round(this.left.preferredWidth()) : 0;
    const bottomH = this.bottom.visible ? Math.round(this.bottom.preferredHeight() * 10) / 10 : 0;
    const vbW     = Math.max(0, w - 2 - leftW);
    const vbH     = Math.max(0, h - 2 - bottomH);
    this.left.setGeometry(1, 1, leftW, vbH);
    this.vb.setGeometry(1 + leftW, 1, vbW, vbH);
    this.bottom.setGeometry(1 + leftW, 1 + vbH, vbW, bottomH);
    this.autoBtn.rect = { x: 1, y: h - 1 - 14, w: 14, h: 14 };
    this.left.linkedViewChanged(this.vb);
    this.bottom.linkedViewChanged(this.vb);
    this.view.update();
  }

  hideAxis(name) {
    const axis = name === "left" ? this.left : this.bottom;
    axis.visible = false;
    this.layout(this.view.width, this.view.height);
  }

  showAxis(name) {
    const axis = name === "left" ? this.left : this.bottom;
    axis.visible = true;
    this.layout(this.view.width, this.view.height);
  }

  setMouseEnabled(x, y) {
    this.vb.setMouseEnabled(x, y);
  }

  plot() {
    const item = new PgPlotDataItem(this, "w");
    this.items.push(item);
    this.curves.push(item);
    this.vb.addItem(item.curve);
    this.applyCurveOptions(item);
    return item;
  }

  removeCurve(item) {
    this.vb.removeItem(item.curve);
    this.items  = this.items.filter((it) => it !== item);
    this.curves = this.curves.filter((it) => it !== item);
  }

  applyCurveOptions(item) {
    const [alpha] = this.alphaState();
    item.curve.alpha = alpha * alpha;
    item.refresh();
  }

  alphaState() {
    let alpha = this.opts.alpha / 1000;
    let auto  = this.opts.autoAlpha;
    if (auto) alpha = 1.0;
    if (!this.opts.alphaGroup) {
      auto  = false;
      alpha = 1.0;
    }
    return [alpha, auto];
  }

  updateAll() {
    for (const item of this.curves) this.applyCurveOptions(item);
    this.vb.update();
  }

  transformsChanged() {
    this.left.logMode   = this.opts.logY;
    this.bottom.logMode = this.opts.logX;
    this.updateAll();
    this.vb.enableAutoRange();
  }

  updateGrid() {
    this.bottom.grid = this.opts.xGrid ? this.opts.gridAlpha : false;
    this.left.grid   = this.opts.yGrid ? this.opts.gridAlpha : false;
    this.view.update();
  }

  updateDecimation() {
    if (!this.opts.maxTraces) {
      for (const item of this.curves) item.setVisible(true);
      return;
    }
    const n = this.opts.maxTracesCount;
    if (this.opts.forgetTraces) {
      for (const item of this.curves.slice(0, Math.max(0, this.curves.length - n))) this.removeCurve(item);
    }
    [...this.curves].reverse().forEach((item, i) => item.setVisible(i < n));
  }

  optionsMenu() {
    const kit = this.ctx.kit;
    const o   = this.opts;
    const box = (rows) => {
      const root = TomoVisInput.el("div", "tv-pg-plotopts");
      for (const row of rows) root.append(row);
      for (const name of ["pointerdown", "click", "keydown"]) root.addEventListener(name, (e) => e.stopPropagation());
      return root;
    };
    const check = (text, key, after) => {
      const view = kit.local("checkbox", { text, onChange: (checked) => {
        o[key] = checked;
        after();
      } });
      view.set({ checked: o[key] });
      return view.el;
    };
    const transforms = box([
      check("Power Spectrum (FFT)", "fft", () => this.transformsChanged()),
      check("Subtract Mean", "subtractMean", () => this.transformsChanged()),
      check("Log X", "logX", () => this.transformsChanged()),
      check("Log Y", "logY", () => this.transformsChanged()),
      check("dy/dx", "derivative", () => this.transformsChanged()),
      check("Y vs. Y'", "phasemap", () => this.transformsChanged()),
    ]);

    const dsSpin = kit.local("spin", { onChange: (value) => {
      o.downsampleFactor = value;
      this.updateAll();
    } });
    dsSpin.set({ minimum: 1, maximum: 100000, value: o.downsampleFactor });
    const dsRow = TomoVisInput.el("span", "tv-pg-plotopts__row");
    dsRow.append(dsSpin.el, TomoVisInput.el("span", "tv-label", "x"), check("Auto", "autoDownsample", () => this.updateAll()));
    const group  = `tv-pg-ds-${Math.random().toString(36).slice(2)}`;
    const radio  = (text, method) => {
      const view = kit.local("radio", { group, text, onChange: () => {
        o.downsampleMethod = method;
        this.updateAll();
      } });
      view.set({ checked: o.downsampleMethod === method });
      return view.el;
    };
    const tracesSpin = kit.local("spin", { onChange: (value) => {
      o.maxTracesCount = value;
      this.updateDecimation();
    } });
    tracesSpin.set({ minimum: 0, maximum: 99, value: o.maxTracesCount });
    const tracesRow = TomoVisInput.el("span", "tv-pg-plotopts__row");
    tracesRow.append(check("Max Traces:", "maxTraces", () => this.updateDecimation()), tracesSpin.el);
    const downsample = box([
      check("Downsample", "downsample", () => this.updateAll()),
      dsRow,
      radio("Subsample", "subsample"),
      radio("Mean", "mean"),
      radio("Peak", "peak"),
      check("Clip to View", "clipToView", () => this.updateAll()),
      tracesRow,
      check("Forget hidden traces", "forgetTraces", () => this.updateDecimation()),
    ]);

    const average = box([check("Average", "average", () => this.updateAll()), TomoVisInput.el("div", "tv-pg-plotopts__list")]);

    const alphaSlider = kit.local("slider", { onChange: (value) => {
      o.alpha = value;
      this.updateAll();
    } });
    alphaSlider.set({ minimum: 0, maximum: 1000, value: o.alpha });
    const alphaRow = TomoVisInput.el("span", "tv-pg-plotopts__row");
    alphaRow.append(check("Auto", "autoAlpha", () => this.updateAll()), alphaSlider.el);
    const alpha = box([check("Alpha", "alphaGroup", () => this.updateAll()), alphaRow]);

    const gridSlider = kit.local("slider", { onChange: (value) => {
      o.gridAlpha = value;
      this.updateGrid();
    } });
    gridSlider.set({ minimum: 0, maximum: 255, value: o.gridAlpha });
    const gridRow = TomoVisInput.el("span", "tv-pg-plotopts__row");
    gridRow.append(TomoVisInput.el("span", "tv-label", "Opacity"), gridSlider.el);
    const grid = box([check("Show X Grid", "xGrid", () => this.updateGrid()), check("Show Y Grid", "yGrid", () => this.updateGrid()), gridRow]);

    const points = box([check("Points", "points", () => this.updateAll()), check("Auto", "autoPoints", () => this.updateAll())]);

    return [
      { text: "Transforms", submenu: [{ widget: transforms }] },
      { text: "Downsample", submenu: [{ widget: downsample }] },
      { text: "Average", submenu: [{ widget: average }] },
      { text: "Alpha", submenu: [{ widget: alpha }] },
      { text: "Grid", submenu: [{ widget: grid }] },
      { text: "Points", submenu: [{ widget: points }] },
    ];
  }

  updateButtons() {
    const show = this.mouseHovering && !this.vb.autoRangeEnabled().every((v) => v !== false);
    if (show !== this.autoBtn.visible) {
      this.autoBtn.visible = show;
      this.view.update();
    }
  }

  hit(x, y) {
    const r = this.autoBtn.rect;
    return this.autoBtn.visible && x >= r.x && x < r.x + r.w && y >= r.y && y < r.y + r.h;
  }

  hitRect(x0, y0, x1, y1) {
    const r = this.autoBtn.rect;
    return this.autoBtn.visible && x1 >= r.x && x0 < r.x + r.w && y1 >= r.y && y0 < r.y + r.h;
  }

  sceneItems() {
    return [{ item: this.hoverTracker(), z: -1000 }, ...(this.autoBtn.visible ? [{ item: this, z: 1000 }] : [])];
  }

  hoverTracker() {
    if (!this.tracker) {
      this.tracker = {
        hit        : (x, y) => x >= 0 && y >= 0 && x < this.view.width && y < this.view.height,
        hitRect    : () => false,
        hoverEvent : (ev) => {
          this.mouseHovering = !ev.isExit();
          this.updateButtons();
        },
      };
    }
    return this.tracker;
  }

  mouseClickEvent(ev) {
    if (ev.button !== "left") return;
    ev.accept();
    this.vb.enableAutoRange();
    this.autoBtn.visible = false;
    this.view.update();
  }

  paint(ctx) {
    if (!this.autoBtn.visible) return;
    const r = this.autoBtn.rect;
    ctx.save();
    ctx.fillStyle = "rgba(255, 255, 255, 0.85)";
    ctx.font = "bold 12px 'Noto Sans', 'DejaVu Sans', sans-serif";
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    ctx.fillText("A", r.x + r.w / 2, r.y + r.h / 2 + 1);
    ctx.restore();
  }
}

class PgNormalizePanel {
  constructor(ctx, imageView) {
    this.ctx       = ctx;
    this.imageView = imageView;
    const kit      = ctx.kit;
    const group    = `tv-pg-norm-${Math.random().toString(36).slice(2)}`;
    this.el        = TomoVisInput.el("fieldset", "tv-pg-normgroup");
    this.el.append(TomoVisInput.el("legend", "tv-pg-normgroup__title", "Normalization"));
    const grid     = TomoVisInput.el("div", "tv-pg-normgroup__grid");
    this.el.append(grid);

    this.divide    = kit.local("radio", { group, text: "Divide", onChange: () => this.imageView.normRadioChanged() });
    this.subtract  = kit.local("radio", { group, text: "Subtract", onChange: () => this.imageView.normRadioChanged() });
    this.off       = kit.local("radio", { group, text: "Off", onChange: () => this.imageView.normRadioChanged() });
    this.roiCheck  = kit.local("checkbox", { text: "ROI", onChange: () => this.imageView.updateNorm() });
    this.frame     = kit.local("checkbox", { text: "Frame", onChange: () => this.imageView.updateNorm() });
    this.timeRange = kit.local("checkbox", { text: "Time range", onChange: () => this.imageView.updateNorm() });
    this.blur      = ["X", "Y", "T"].map(() => kit.local("doubleSpin", { decimals: 2 }));
    this.off.set({ checked: true });
    this.blur.forEach((spin) => spin.set({ minimum: 0, maximum: 99.99, value: 0 }));

    const cell = (node, col, row, span = 1) => {
      node.style.gridColumn = `${col + 1} / span ${span}`;
      node.style.gridRow    = `${row + 1}`;
      grid.append(node);
    };
    const bold = (text) => TomoVisInput.el("span", "tv-label tv-pg-normgroup__head", text);
    const right = (text) => TomoVisInput.el("span", "tv-label tv-pg-normgroup__right", text);
    cell(bold("Operation:"), 0, 0);
    cell(this.divide.el, 1, 0);
    cell(this.subtract.el, 2, 0);
    cell(this.off.el, 3, 0);
    cell(bold("Mean:"), 0, 1);
    cell(this.roiCheck.el, 1, 1);
    cell(this.frame.el, 2, 1);
    cell(this.timeRange.el, 3, 1);
    cell(bold("Blur:"), 0, 2);
    cell(right("X"), 1, 2);
    cell(this.blur[0].el, 2, 2);
    cell(right("Y"), 3, 2);
    cell(this.blur[1].el, 4, 2);
    cell(right("T"), 5, 2);
    cell(this.blur[2].el, 6, 2);
    this.el.hidden = true;
  }

  operation() {
    if (this.off.checked) return "off";
    if (this.divide.checked) return "divide";
    if (this.subtract.checked) return "subtract";
    return "off";
  }
}

class PgImageView {
  constructor(ctx, host, { name = "ImageView" } = {}) {
    this.ctx       = ctx;
    this.name      = name;
    this.image     = null;
    this.imageDisp = null;
    this.axes      = {};
    this.imageLevels = null;
    this.levelMin  = null;
    this.levelMax  = null;
    this.roiCurves = [];
    this.menu      = null;
    this.normChecked = false;

    this.el        = TomoVisInput.el("div", "tv-pg-imageview");
    this.splitter  = TomoVisInput.el("div", "tv-pg-splitter");
    this.main      = TomoVisInput.el("div", "tv-pg-main");
    this.gvHost    = TomoVisInput.el("div", "tv-pg-gv");
    this.histHost  = TomoVisInput.el("div", "tv-pg-hist");
    this.handle    = TomoVisInput.el("div", "tv-pg-splitter__handle");
    this.plotHost  = TomoVisInput.el("div", "tv-pg-roiplot");
    this.roiBtn    = TomoVisInput.el("button", "tv-button tv-pg-btn", "ROI");
    this.menuBtn   = TomoVisInput.el("button", "tv-button tv-pg-btn", "Menu");
    this.roiBtn.type  = "button";
    this.menuBtn.type = "button";
    this.roiBtn.setAttribute("aria-pressed", "false");
    this.main.append(this.gvHost, this.histHost, this.roiBtn, this.menuBtn);
    this.splitter.append(this.main, this.handle, this.plotHost);
    this.el.append(this.splitter);
    host.append(this.el);

    this.scene     = new PgGraphicsView(this.gvHost, { className: "tv-pg-main-canvas", onLayout: (w, h) => this.view.setGeometry(0, 0, w, h) });
    this.view      = new PgViewBox({ name });
    this.view.attach(this.scene);
    this.view.setAspectLocked(true);
    this.view.invertY();
    this.scene.addWidget(this.view);

    this.roi = new PgRectRoi(10);
    this.roi.setZValue(20);
    this.view.addItem(this.roi);
    this.roi.hide();
    this.normRoi = new PgRectRoi(10);
    this.normRoi.setPen("y");
    this.normRoi.setZValue(20);
    this.view.addItem(this.normRoi);
    this.normRoi.hide();

    this.imageItem = new PgImageItem();
    this.view.addItem(this.imageItem);

    this.histogram = new PgHistogramLut(ctx, this.histHost, this.imageItem);
    this.roiPlot   = new PgRoiPlot(ctx, this.plotHost, `${name}_ROI`);
    this.roiPlot.hideAxis("left");
    this.norm      = new PgNormalizePanel(ctx, this);
    this.el.append(this.norm.el);

    this.roiBtn.addEventListener("click", () => {
      const on = this.roiBtn.getAttribute("aria-pressed") !== "true";
      this.roiBtn.setAttribute("aria-pressed", String(on));
      this.roiBtn.classList.toggle("is-checked", on);
      this.roiClicked();
    });
    this.menuBtn.addEventListener("click", (event) => this.menuClicked(event));
    this.roi.sigRegionChanged.connect(() => this.roiChanged());
    this.normRoi.sigRegionChangeFinished.connect(() => this.updateNorm());

    for (const scene of [this.scene, this.histogram.view, this.roiPlot.view]) scene.exportEntry = (view) => this.exportEntry(scene, view);
    this.roiClicked();
  }

  get roiChecked() {
    return this.roiBtn.getAttribute("aria-pressed") === "true";
  }

  addItem(item, ignoreBounds = false) {
    this.view.addItem(item, ignoreBounds);
  }

  removeItem(item) {
    this.view.removeItem(item);
  }

  setImage(array, shape, dtype) {
    this.image     = { data: array, shape: shape.slice(), dtype };
    this.imageDisp = null;
    if (shape.length === 2) this.axes = { t: null, x: 0, y: 1, c: null };
    else if (shape[2] <= 4) this.axes = { t: null, x: 0, y: 1, c: 2 };
    else this.axes = { t: 0, x: 1, y: 2, c: null };
    this.updateImage(false);
    if (this.roiChecked) this.roiChanged();
    this.roiClicked();
  }

  clear() {
    this.image = null;
    this.imageItem.clear();
  }

  setLevels(args) {
    this.histogram.setLevels(args);
  }

  setHistogramRange(mn, mx) {
    this.histogram.setHistogramRange(mn, mx);
  }

  setColorMap(colors) {
    const pos = colors.map((_, i) => i * (1 / (colors.length - 1)));
    pos[pos.length - 1] = 1.0;
    this.histogram.gradient.setColorMap(pos, colors.map((c) => [c[0], c[1], c[2], 255]));
  }

  setLevelMode(mode) {
    this.histogram.setLevelMode(mode);
  }

  autoLevels() {
    this.histogram.setLevels({ rgba: this.imageLevels });
  }

  getProcessedImage() {
    if (this.imageDisp === null) {
      this.imageDisp   = this.normalize(this.image);
      this.imageLevels = this.quickMinMax(this.imageDisp);
      this.levelMin    = Math.min(...this.imageLevels.map((l) => l[0]));
      this.levelMax    = Math.max(...this.imageLevels.map((l) => l[1]));
    }
    return this.imageDisp;
  }

  quickMinMax(image) {
    const nch = image.shape.length === 3 ? image.shape[2] : 1;
    const out = [];
    for (let c = 0; c < nch; c += 1) {
      let mn = Infinity;
      let mx = -Infinity;
      for (let i = c; i < image.data.length; i += nch) {
        const v = image.data[i];
        if (Number.isNaN(v)) continue;
        if (v < mn) mn = v;
        if (v > mx) mx = v;
      }
      out.push(image.data.length === 0 ? [0, 0] : [mn, mx]);
    }
    return this.axes.c === null ? [out[0]] : out;
  }

  normalize(image) {
    const op = this.norm.operation();
    if (op === "off") return image;
    const div   = op === "divide";
    const shape = image.shape;
    const norm  = Float32Array.from(image.data);
    const f     = Math.fround;
    const apply = (index, n) => {
      norm[index] = div ? f(norm[index] / n) : f(norm[index] - n);
    };
    if (shape.length === 3) {
      const [w, h, c] = shape;
      if (this.norm.timeRange.checked) {
        const ref = new Float64Array(h * c);
        for (let k = 0; k < h * c; k += 1) ref[k] = image.data[k];
        for (let x = 0; x < w; x += 1) {
          for (let k = 0; k < h * c; k += 1) apply(x * h * c + k, f(ref[k]));
        }
      }
      if (this.norm.frame.checked) {
        for (let x = 0; x < w; x += 1) {
          let sum = 0;
          for (let k = 0; k < h * c; k += 1) sum += image.data[x * h * c + k];
          const mean = f(sum / (h * c));
          for (let k = 0; k < h * c; k += 1) apply(x * h * c + k, mean);
        }
      }
      if (this.norm.roiCheck.checked) {
        const params = this.normRoi.getAffineSliceParams();
        for (let x = 0; x < w; x += 1) {
          const sub = new Float32Array(h * c);
          for (let k = 0; k < h * c; k += 1) sub[k] = norm[x * h * c + k];
          const region = PgAffineSlice.affineSlice2d(sub, [h, c], params.shape, params.vectors, params.origin);
          const mean   = region.data.length ? region.data.reduce((a, b) => a + b, 0) / region.data.length : NaN;
          for (let k = 0; k < h * c; k += 1) apply(x * h * c + k, f(mean));
        }
      }
    }
    return { data: norm, shape: shape.slice(), dtype: "float32" };
  }

  normRadioChanged() {
    this.imageDisp = null;
    this.updateImage();
    this.autoLevels();
    this.roiChanged();
  }

  updateNorm() {
    if (this.norm.roiCheck.checked) this.normRoi.show();
    else this.normRoi.hide();
    if (this.norm.operation() !== "off") {
      this.imageDisp = null;
      this.updateImage();
      this.autoLevels();
      this.roiChanged();
    }
  }

  normToggled(visible) {
    this.norm.el.hidden = !visible;
    if (visible && this.norm.roiCheck.checked) this.normRoi.show();
    else this.normRoi.hide();
  }

  updateImage(autoHistogramRange = true) {
    if (this.image === null) return;
    const image = this.getProcessedImage();
    if (autoHistogramRange) this.histogram.setHistogramRange(this.levelMin, this.levelMax);
    this.imageItem.setImage(image.data, image.shape, image.dtype);
  }

  roiClicked() {
    if (this.roiChecked) {
      this.roi.show();
      this.roiPlot.setMouseEnabled(true, true);
      this.splitter.classList.add("is-split");
      this.roiChanged();
      for (const c of this.roiCurves) c.setVisible(true);
      this.roiPlot.showAxis("left");
    } else {
      this.roi.hide();
      this.roiPlot.setMouseEnabled(false, false);
      for (const c of this.roiCurves) c.setVisible(false);
      this.roiPlot.hideAxis("left");
      this.splitter.classList.remove("is-split");
    }
    this.roiPlot.view.update();
  }

  roiChanged() {
    if (this.image === null) return;
    const image  = this.getProcessedImage();
    const region = this.roi.getArrayRegion(image.data, image.shape);
    const [nx, ny] = region.shape;
    const nch    = region.shape.length === 3 ? region.shape[2] : 1;
    const xvals  = [];
    for (let i = 0; i < nx; i += 1) {
      const dx = region.coords[i * ny] - region.coords[0];
      const dy = region.coords[nx * ny + i * ny] - region.coords[nx * ny];
      xvals.push(Math.sqrt(dx * dx + dy * dy));
    }
    const means = [];
    for (let c = 0; c < nch; c += 1) {
      const m = [];
      for (let i = 0; i < nx; i += 1) {
        let sum = 0;
        for (let j = 0; j < ny; j += 1) sum += region.data[(i * ny + j) * nch + c];
        m.push(sum / ny);
      }
      means.push(m);
    }
    const colors = nch === 1 ? ["w"] : ["r", "g", "b", "w"];
    const plots  = means.map((m, c) => [xvals, m, colors[c]]);
    while (plots.length < this.roiCurves.length) this.roiPlot.removeCurve(this.roiCurves.pop());
    while (plots.length > this.roiCurves.length) this.roiCurves.push(this.roiPlot.plot());
    plots.forEach(([x, y, pen], i) => this.roiCurves[i].setData(x, y, pen));
  }

  menuClicked(event) {
    const items = [
      { text: "Normalization", checkable: true, checked: this.normChecked, onTrigger: (checked) => {
        this.normChecked = checked;
        this.normToggled(checked);
      } },
      { text: "Export", onTrigger: () => this.exportClicked() },
    ];
    this.menu = this.ctx.kit.menu(items);
    this.menu.openAt(event.clientX, event.clientY);
  }

  async exportClicked() {
    const chosen = await this.ctx.dialogs.file({ mode: "save", title: "Save As", filters: ["All Files (*)"], selected_filter: "All Files (*)", directory: null, file: null });
    if (!chosen.accepted || !chosen.path) return;
    await this.export(chosen.path);
  }

  async export(fileName) {
    if (!this.imageItem.image) return;
    const canvas = this.imageItem.toCanvas();
    const blob   = await new Promise((resolve) => canvas.toBlob(resolve, "image/png"));
    const result = await this.ctx.session.writeFile(fileName, blob, "image");
    if (!result.ok) this.ctx.session.log([`ImageView export of ${fileName} wrote nothing: ${result.error}`]);
  }

  exportEntry(scene, view) {
    return { text: "Export...", onTrigger: () => PgExportDialog.open(this.ctx, scene, view) };
  }
}

window.PgPlotDataItem   = PgPlotDataItem;
window.PgRoiPlot        = PgRoiPlot;
window.PgNormalizePanel = PgNormalizePanel;
window.PgImageView      = PgImageView;
