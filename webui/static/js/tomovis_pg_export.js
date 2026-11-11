"use strict";

class PgSvgContext {
  constructor(measure) {
    this.measure    = measure;
    this.parts      = [];
    this.defs       = [];
    this.ids        = 0;
    this.stack      = [];
    this.path       = [];
    this.scaling    = false;
    this.state      = { m: [1, 0, 0, 1, 0, 0], clip: null, strokeStyle: "#000", fillStyle: "#000", lineWidth: 1, font: "10px sans-serif", textAlign: "start", textBaseline: "alphabetic", globalAlpha: 1, dash: [] };
    this.imageSmoothingEnabled    = false;
    this.globalCompositeOperation = "source-over";
  }

  get strokeStyle() { return this.state.strokeStyle; }
  set strokeStyle(v) { this.state.strokeStyle = v; }
  get fillStyle() { return this.state.fillStyle; }
  set fillStyle(v) { this.state.fillStyle = v; }
  get lineWidth() { return this.state.lineWidth; }
  set lineWidth(v) { this.state.lineWidth = v; }
  get font() { return this.state.font; }
  set font(v) { this.state.font = v; }
  get textAlign() { return this.state.textAlign; }
  set textAlign(v) { this.state.textAlign = v; }
  get textBaseline() { return this.state.textBaseline; }
  set textBaseline(v) { this.state.textBaseline = v; }
  get globalAlpha() { return this.state.globalAlpha; }
  set globalAlpha(v) { this.state.globalAlpha = v; }

  save() {
    this.stack.push({ ...this.state, m: this.state.m.slice(), dash: this.state.dash.slice() });
  }

  restore() {
    if (this.stack.length) this.state = this.stack.pop();
  }

  setTransform(a, b, c, d, e, f) {
    this.state.m = [a, b, c, d, e, f];
  }

  transform(a, b, c, d, e, f) {
    const [A, B, C, D, E, F] = this.state.m;
    this.state.m = [A * a + C * b, B * a + D * b, A * c + C * d, B * c + D * d, A * e + C * f + E, B * e + D * f + F];
  }

  translate(x, y) {
    this.transform(1, 0, 0, 1, x, y);
  }

  scale(x, y) {
    this.transform(x, 0, 0, y, 0, 0);
  }

  rotate(a) {
    this.transform(Math.cos(a), Math.sin(a), -Math.sin(a), Math.cos(a), 0, 0);
  }

  setLineDash(dash) {
    this.state.dash = dash.slice();
  }

  measureText(text) {
    this.measure.font = this.state.font;
    return this.measure.measureText(text);
  }

  createLinearGradient(x0, y0, x1, y1) {
    const id   = `g${this.ids += 1}`;
    const grad = { id, x0, y0, x1, y1, stops: [], m: this.state.m.slice(), addColorStop(offset, color) { this.stops.push([offset, color]); } };
    return grad;
  }

  createPattern() {
    return null;
  }

  beginPath() {
    this.path = [];
  }

  moveTo(x, y) {
    this.path.push(`M${x} ${y}`);
  }

  lineTo(x, y) {
    this.path.push(`L${x} ${y}`);
  }

  closePath() {
    this.path.push("Z");
  }

  rect(x, y, w, h) {
    this.path.push(`M${x} ${y}L${x + w} ${y}L${x + w} ${y + h}L${x} ${y + h}Z`);
  }

  matrix() {
    return `matrix(${this.state.m.join(" ")})`;
  }

  clip() {
    const id = `c${this.ids += 1}`;
    this.defs.push(`<clipPath id="${id}"><path d="${this.path.join("")}" transform="${this.matrix()}"/></clipPath>`);
    this.state.clip = id;
  }

  clipAttr() {
    return this.state.clip ? ` clip-path="url(#${this.state.clip})"` : "";
  }

  paint(style) {
    if (style === null || style === undefined) return "none";
    if (typeof style === "object" && style.stops) {
      const stops = style.stops.map(([o, c]) => `<stop offset="${o}" stop-color="${c}"/>`).join("");
      this.defs.push(`<linearGradient id="${style.id}" gradientUnits="userSpaceOnUse" x1="${style.x0}" y1="${style.y0}" x2="${style.x1}" y2="${style.y1}" gradientTransform="matrix(${style.m.join(" ")})">${stops}</linearGradient>`);
      return `url(#${style.id})`;
    }
    return String(style);
  }

  strokeAttrs() {
    const effect = this.scaling ? "" : ' vector-effect="non-scaling-stroke"';
    const dash   = this.state.dash.length ? ` stroke-dasharray="${this.state.dash.join(" ")}"` : "";
    return `stroke="${this.paint(this.state.strokeStyle)}" stroke-width="${this.state.lineWidth}" fill="none"${dash}${effect}`;
  }

  stroke() {
    if (!this.path.length) return;
    this.parts.push(`<path d="${this.path.join("")}" transform="${this.matrix()}" ${this.strokeAttrs()} opacity="${this.state.globalAlpha}"${this.clipAttr()}/>`);
  }

  fill() {
    if (!this.path.length || this.state.fillStyle === null) return;
    this.parts.push(`<path d="${this.path.join("")}" transform="${this.matrix()}" fill="${this.paint(this.state.fillStyle)}" stroke="none" opacity="${this.state.globalAlpha}"${this.clipAttr()}/>`);
  }

  fillRect(x, y, w, h) {
    if (this.state.fillStyle === null) return;
    this.parts.push(`<rect x="${x}" y="${y}" width="${w}" height="${h}" transform="${this.matrix()}" fill="${this.paint(this.state.fillStyle)}" opacity="${this.state.globalAlpha}"${this.clipAttr()}/>`);
  }

  strokeRect(x, y, w, h) {
    this.parts.push(`<rect x="${x}" y="${y}" width="${w}" height="${h}" transform="${this.matrix()}" ${this.strokeAttrs()}${this.clipAttr()}/>`);
  }

  clearRect() {}

  drawImage(source, x, y, w, h) {
    const href = source.toDataURL("image/png");
    this.parts.push(`<image x="${x}" y="${y}" width="${w}" height="${h}" preserveAspectRatio="none" transform="${this.matrix()}" xlink:href="${href}"${this.clipAttr()}/>`);
  }

  fillText(text, x, y) {
    const anchor   = { left: "start", start: "start", right: "end", end: "end", center: "middle" }[this.state.textAlign] || "start";
    const baseline = this.state.textBaseline === "middle" ? "central" : "auto";
    const match    = /(\d+(?:\.\d+)?)px\s+(.*)/.exec(this.state.font);
    const size     = match ? match[1] : "10";
    const family   = match ? match[2].replace(/"/g, "'") : "sans-serif";
    const escaped  = String(text).replace(/&/g, "&amp;").replace(/</g, "&lt;");
    this.parts.push(`<text x="${x}" y="${y}" transform="${this.matrix()}" fill="${this.paint(this.state.fillStyle)}" font-size="${size}" font-family="${family}" text-anchor="${anchor}" dominant-baseline="${baseline}"${this.clipAttr()}>${escaped}</text>`);
  }

  document(width, height, background) {
    const header = `<?xml version="1.0" encoding="UTF-8" standalone="no"?>\n<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink"  version="1.2" baseProfile="tiny" viewBox ="0 0 ${Math.trunc(width)} ${Math.trunc(height)}">\n<title>pyqtgraph SVG export</title>\n<desc>Generated with Qt and pyqtgraph</desc>\n<style>\n    image {\n        image-rendering: crisp-edges;\n        image-rendering: -moz-crisp-edges;\n        image-rendering: pixelated;\n    }\n</style>\n`;
    const hex  = `#${background.slice(0, 3).map((v) => v.toString(16).padStart(2, "0")).join("")}`;
    const back = `<rect width="100%" height="100%" fill="${hex}" fill-opacity="${background[3] / 255}" />\n`;
    return `${header}${back}<defs>\n${this.defs.join("\n")}\n</defs>\n<g>\n${this.parts.join("\n")}\n</g>\n</svg>\n`;
  }
}

class PgExporter {
  static allowCopy = false;

  constructor(dialog, target) {
    this.dialog = dialog;
    this.ctx    = dialog.ctx;
    this.target = target;
    this.params = [];
  }

  scene() {
    return this.dialog.scene;
  }

  sourceRect() {
    if (this.target.kind === "scene") return { x: 0, y: 0, w: this.scene().width, h: this.scene().height };
    return { ...this.target.rect() };
  }

  targetRect() {
    return this.sourceRect();
  }

  param(name) {
    return this.params.find((p) => p.name === name);
  }

  value(name) {
    return this.param(name).value;
  }

  setValue(name, value) {
    const p = this.param(name);
    p.value = value;
    if (p.view) p.view.set(p.type === "bool" ? { checked: value } : (p.type === "list" ? { index: p.limits.indexOf(value) } : { value }));
  }

  parameterChanged() {}

  isPlot() {
    return this.target.kind === "plot";
  }

  log(text) {
    this.ctx.session.log([text]);
  }

  async saveDialog(filters) {
    const chosen = await this.ctx.dialogs.file({ mode: "save", title: "Save As", filters, selected_filter: filters[0], directory: PgExportDialog.lastDirectory, file: null });
    if (!chosen.accepted || !chosen.path) return null;
    let fileName = chosen.path;
    PgExportDialog.lastDirectory = fileName.slice(0, fileName.lastIndexOf("/")) || "/";
    const ext      = (fileName.match(/\.([^./]*)$/) || [null, ""])[1].toLowerCase();
    const selected = /\*\.(\w+)\b/.exec(chosen.filter || filters[0]);
    if (selected && ext !== selected[1].toLowerCase()) fileName = `${fileName}.${selected[1].toLowerCase()}`;
    return fileName;
  }

  async write(fileName, blob, kind) {
    const result = await this.ctx.session.writeFile(fileName, blob, kind);
    if (!result.ok) this.log(`Export to ${fileName} failed: ${result.error}`);
    return result;
  }

  renderCanvas(width, height, background, antialias) {
    const canvas  = document.createElement("canvas");
    canvas.width  = width;
    canvas.height = height;
    const ctx     = canvas.getContext("2d");
    ctx.imageSmoothingEnabled = antialias;
    if (background[3] > 0) {
      ctx.fillStyle = PgPen.css(background);
      ctx.fillRect(0, 0, width, height);
    }
    const sr = this.sourceRect();
    if (sr.w === 0 || sr.h === 0) return canvas;
    ctx.setTransform(width / sr.w, 0, 0, height / sr.h, -sr.x * width / sr.w, -sr.y * height / sr.h);
    ctx.beginPath();
    ctx.rect(sr.x, sr.y, sr.w, sr.h);
    ctx.clip();
    this.scene().sigPrepareForPaint.emit();
    this.scene().paintScene(ctx, { background: null, overlays: false });
    return canvas;
  }
}

class PgImageExporter extends PgExporter {
  static NAME      = "Image File (PNG, TIF, JPG, ...)";
  static allowCopy = true;
  static FILTERS   = ["*.png", "*.tif", "*.jpg", "*.bmp", "*.cur", "*.icns", "*.ico", "*.jpeg", "*.pbm", "*.pgm", "*.ppm", "*.tiff", "*.wbmp", "*.webp", "*.xbm", "*.xpm"];

  constructor(dialog, target) {
    super(dialog, target);
    const tr = this.targetRect();
    this.params = [
      { name: "width", type: "int", value: Math.trunc(tr.w), limits: [0, null] },
      { name: "height", type: "int", value: Math.trunc(tr.h), limits: [0, null] },
      { name: "antialias", type: "bool", value: true },
      { name: "background", type: "color", value: this.scene().background.slice() },
      { name: "invertValue", type: "bool", value: false },
    ];
  }

  parameterChanged(name) {
    const sr = this.sourceRect();
    if (name === "width") this.setValue("height", Math.trunc(this.value("width") * (sr.h / sr.w)));
    else if (name === "height") this.setValue("width", Math.trunc(this.value("height") * (sr.w / sr.h)));
  }

  render() {
    const w = Math.trunc(this.value("width"));
    const h = Math.trunc(this.value("height"));
    if (w === 0 || h === 0) throw new Error(`Cannot export image with size=0 (requested export size is ${w}x${h})`);
    const canvas = this.renderCanvas(w, h, this.value("background"), this.value("antialias"));
    if (this.value("invertValue")) {
      const ctx  = canvas.getContext("2d");
      const data = ctx.getImageData(0, 0, w, h);
      const px   = data.data;
      for (let i = 0; i < px.length; i += 4) {
        const mn = Math.min(px[i], px[i + 1], px[i + 2]);
        const mx = Math.max(px[i], px[i + 1], px[i + 2]);
        const d  = (255 - mx) - mn;
        px[i] = (px[i] + d) & 255;
        px[i + 1] = (px[i + 1] + d) & 255;
        px[i + 2] = (px[i + 2] + d) & 255;
      }
      ctx.putImageData(data, 0, 0);
    }
    return canvas;
  }

  async export(copy = false) {
    if (copy) {
      const blob = await FigureExport.canvasBlob(this.render());
      await navigator.clipboard.write([new ClipboardItem({ "image/png": blob })]);
      return;
    }
    const fileName = await this.saveDialog(PgImageExporter.FILTERS);
    if (!fileName) return;
    const blob = await FigureExport.canvasBlob(this.render());
    await this.write(fileName, blob, "image");
  }
}

class PgSvgExporter extends PgExporter {
  static NAME      = "Scalable Vector Graphics (SVG)";
  static allowCopy = true;

  constructor(dialog, target) {
    super(dialog, target);
    const tr = this.targetRect();
    this.params = [
      { name: "background", type: "color", value: this.scene().background.slice() },
      { name: "width", type: "float", value: tr.w, limits: [0, null] },
      { name: "height", type: "float", value: tr.h, limits: [0, null] },
      { name: "scaling stroke", type: "bool", value: false, tip: "If False, strokes are non-scaling, which means that they appear the same width on screen regardless of how they are scaled or how the view is zoomed." },
    ];
  }

  parameterChanged(name) {
    const sr = this.sourceRect();
    if (name === "width") this.setValue("height", this.value("width") * (sr.h / sr.w));
    else if (name === "height") this.setValue("width", this.value("height") * (sr.w / sr.h));
  }

  xml() {
    const measure = document.createElement("canvas").getContext("2d");
    const svg     = new PgSvgContext(measure);
    svg.scaling   = this.value("scaling stroke");
    const sr      = this.sourceRect();
    const w       = this.value("width");
    const h       = this.value("height");
    svg.setTransform(w / sr.w, 0, 0, h / sr.h, -sr.x * w / sr.w, -sr.y * h / sr.h);
    svg.beginPath();
    svg.rect(sr.x, sr.y, sr.w, sr.h);
    svg.clip();
    this.scene().sigPrepareForPaint.emit();
    this.scene().paintScene(svg, { background: null, overlays: false });
    return svg.document(w, h, this.value("background"));
  }

  async export(copy = false) {
    if (copy) {
      await navigator.clipboard.writeText(this.xml());
      return;
    }
    const fileName = await this.saveDialog(["Scalable Vector Graphics (*.svg)"]);
    if (!fileName) return;
    await this.write(fileName, new Blob([this.xml()], { type: "application/octet-stream" }), "bytes");
  }
}

class PgCsvExporter extends PgExporter {
  static NAME = "CSV of original plot data";

  constructor(dialog, target) {
    super(dialog, target);
    this.params = [
      { name: "separator", type: "list", value: "comma", limits: ["comma", "tab"] },
      { name: "precision", type: "int", value: 10, limits: [0, null] },
      { name: "columnMode", type: "list", value: "(x,y) per plot", limits: ["(x,y) per plot", "(x,y,y,y) for all plots"] },
    ];
  }

  static positional(value, precision) {
    if (!Number.isFinite(value)) return Number.isNaN(value) ? "nan" : (value > 0 ? "inf" : "-inf");
    let s = String(Math.abs(value));
    if (s.includes("e")) s = PgFormat.fixed(Math.abs(value), 40).replace(/0+$/, "");
    const [int, frac = ""] = s.split(".");
    let out;
    if (frac.length > precision) out = PgFormat.fixed(Math.abs(value), precision).replace(/0+$/, "");
    else out = `${int}.${frac}`;
    if (!out.includes(".")) out += ".";
    return `${value < 0 || Object.is(value, -0) ? "-" : ""}${out}`;
  }

  text() {
    const header = [];
    const data   = [];
    const all    = this.value("columnMode") === "(x,y) per plot";
    this.target.plot.curves.forEach((curve, index) => {
      const [x, y] = curve.getData();
      if (!x || x.length === 0) return;
      const tag = String(index).padStart(4, "0");
      if (all || index === 0) {
        header.push(`x${tag}`, `y${tag}`);
        data.push(x, y);
      } else {
        header.push(`y${tag}`);
        data.push(y);
      }
    });
    const sep  = this.value("separator") === "comma" ? "," : "\t";
    const rows = [header.join(sep)];
    const n    = Math.max(0, ...data.map((col) => col.length));
    for (let i = 0; i < n; i += 1) rows.push(data.map((col) => (i < col.length ? PgCsvExporter.positional(col[i], this.value("precision")) : "")).join(sep));
    return `${rows.join("\r\n")}\r\n`;
  }

  async export() {
    if (!this.isPlot()) {
      this.log("TypeError: Must have a PlotItem selected for CSV export.");
      return;
    }
    const fileName = await this.saveDialog(["*.csv", "*.tsv"]);
    if (!fileName) return;
    await this.write(fileName, new Blob([this.text()], { type: "application/octet-stream" }), "bytes");
  }
}

class PgHdf5Exporter extends PgExporter {
  static NAME = "HDF5 Export: plot (x,y)";

  constructor(dialog, target) {
    super(dialog, target);
    this.params = [
      { name: "Name", type: "str", value: "Export" },
      { name: "columnMode", type: "list", value: "(x,y) per plot", limits: ["(x,y) per plot", "(x,y,y,y) for all plots"] },
    ];
  }

  async export() {
    if (!this.isPlot()) {
      this.log("Exception: Must have a PlotItem selected for HDF5 export.");
      return;
    }
    const fileName = await this.saveDialog(["*.h5", "*.hdf", "*.hd5"]);
    if (!fileName) return;
    const curves = this.target.plot.curves.map((curve) => {
      const [x, y] = curve.displayData();
      return { x, y };
    });
    const result = await this.ctx.session.exportHdf5({ path: fileName, name: this.value("Name"), column_mode: this.value("columnMode"), curves });
    if (!result.ok) this.log(`HDF5 export to ${fileName} failed: ${result.error}`);
  }
}

class PgMatplotlibExporter extends PgExporter {
  static NAME        = "Matplotlib Window";
  static FIGURE_SIZE = [500, 400];

  constructor(dialog, target) {
    super(dialog, target);
    this.params = null;
  }

  static rgbaF(color) {
    return [color[0] / 255, color[1] / 255, color[2] / 255, color[3] / 255];
  }

  plotSpec() {
    const plot = this.target.plot;
    const vr   = plot.vb.viewRange();
    return {
      curves: plot.curves.map((item) => {
        const [x, y] = item.displayData();
        const pen    = item.curve.pen;
        return {
          x,
          y,
          pen         : { color: PgMatplotlibExporter.rgbaF(pen.color), width: pen.width, style: "solid" },
          symbol      : null,
          symbolSize  : 10,
          symbolPen   : PgMatplotlibExporter.rgbaF([200, 200, 200, 255]),
          symbolBrush : PgMatplotlibExporter.rgbaF([50, 50, 150, 255]),
        };
      }),
      xlabel : "",
      ylabel : "",
      title  : "",
      xrange : vr[0],
      yrange : vr[1],
    };
  }

  async export() {
    if (!this.isPlot()) {
      this.log("Exception: MatplotlibExporter currently only works with PlotItem");
      return;
    }
    if (typeof window.MplFigureView !== "function") throw new Error("Matplotlib Window export needs MplFigureView from tomovis_mpl.js");
    const modal = new TomoVisModal({ title: "Matplotlib Window", className: "tv-pg-mplwindow", buttons: ["Close"], escape: "Close", layer: this.ctx.layer });
    const host  = TomoVisInput.el("div", "tv-pg-mplwindow__figure");
    modal.body.append(host);
    await this.ctx.session.figure("export", "export_matplotlib", { plot: this.plotSpec() });
    const view  = new window.MplFigureView(host, this.ctx, "export", { size: PgMatplotlibExporter.FIGURE_SIZE });
    await modal.open();
    view.dispose();
  }
}

class PgExportDialog {
  static EXPORTERS     = [PgCsvExporter, PgHdf5Exporter, PgImageExporter, PgMatplotlibExporter, PgSvgExporter];
  static lastDirectory = null;

  static open(ctx, scene, view) {
    if (!scene.exportDialog) scene.exportDialog = new PgExportDialog(ctx, scene);
    scene.exportDialog.show(view);
  }

  constructor(ctx, scene) {
    this.ctx       = ctx;
    this.scene     = scene;
    this.el        = null;
    this.selected  = null;
    this.format    = 0;
    this.exporter  = null;
    this.selectBox = null;
    this.overlay   = (c) => this.paintSelectBox(c);
  }

  targets() {
    const list = [{ kind: "scene", label: "Entire Scene", depth: 0, rect: () => ({ x: 0, y: 0, w: this.scene.width, h: this.scene.height }) }];
    for (const widget of this.scene.widgets) {
      if (widget instanceof PgRoiPlot) {
        list.push({ kind: "plot", label: "Plot", depth: 1, plot: widget, rect: () => ({ x: 0, y: 0, w: this.scene.width, h: this.scene.height }) });
        list.push({ kind: "viewbox", label: "ViewBox", depth: 2, view: widget.vb, rect: () => ({ ...widget.vb.rect }) });
      } else if (widget instanceof PgViewBox && !this.scene.widgets.some((w) => w instanceof PgRoiPlot && w.vb === widget)) {
        list.push({ kind: "viewbox", label: "ViewBox", depth: 1, view: widget, rect: () => ({ ...widget.rect }) });
      }
    }
    return list;
  }

  build() {
    const el    = TomoVisInput.el;
    this.el     = el("div", "tv-modal tv-pg-export");
    this.el.setAttribute("role", "dialog");
    this.title  = el("div", "tv-modal__title", "Export");
    const body  = el("div", "tv-modal__body");
    this.tree   = el("div", "tv-pg-export__tree");
    this.list   = el("div", "tv-pg-export__formats");
    this.params = el("div", "tv-pg-export__params");
    const buttons = el("div", "tv-pg-export__buttons");
    this.copyBtn   = el("button", "tv-button", "Copy");
    this.exportBtn = el("button", "tv-button", "Export");
    this.closeBtn  = el("button", "tv-button", "Close");
    for (const b of [this.copyBtn, this.exportBtn, this.closeBtn]) b.type = "button";
    buttons.append(this.copyBtn, this.exportBtn, this.closeBtn);
    body.append(el("span", "tv-label", "Item to export:"), this.tree, el("span", "tv-label", "Export format"), this.list, el("span", "tv-label", "Export options"), this.params, buttons);
    this.el.append(this.title, body);
    this.copyBtn.addEventListener("click", () => this.run(true));
    this.exportBtn.addEventListener("click", () => this.run(false));
    this.closeBtn.addEventListener("click", () => this.close());
    this.title.addEventListener("pointerdown", (event) => this.dragStart(event));
    this.el.addEventListener("keydown", (event) => {
      if (event.key === "Escape") this.close();
    });
  }

  dragStart(event) {
    if (event.button !== 0) return;
    event.preventDefault();
    const sx   = event.clientX;
    const sy   = event.clientY;
    const left = parseFloat(this.el.style.left) || 0;
    const top  = parseFloat(this.el.style.top) || 0;
    const move = (e) => {
      this.el.style.left = `${left + e.clientX - sx}px`;
      this.el.style.top  = `${top + e.clientY - sy}px`;
    };
    const stop = () => {
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", stop);
    };
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", stop);
  }

  show(view) {
    const first = this.el === null;
    if (first) this.build();
    this.items = this.targets();
    let select = this.items[0];
    if (view) {
      const plot = this.items.find((t) => t.kind === "plot" && t.plot.vb === view);
      select = plot || this.items.find((t) => t.view === view) || this.items[0];
    }
    this.renderTree(select);
    if (!this.el.isConnected) this.ctx.layer.append(this.el);
    if (first) {
      const layer = this.ctx.layer.getBoundingClientRect();
      const rect  = this.el.getBoundingClientRect();
      this.el.style.left = `${Math.max(0, (Math.min(layer.width, window.innerWidth) - rect.width) / 2)}px`;
      this.el.style.top  = `${Math.max(0, (Math.min(layer.height, window.innerHeight) - rect.height) / 2 + window.scrollY - layer.top)}px`;
    }
    if (!this.scene.overlays.includes(this.overlay)) this.scene.overlays.push(this.overlay);
    this.selectBoxVisible = true;
    this.scene.update();
  }

  renderTree(select) {
    this.tree.replaceChildren();
    this.items.forEach((target) => {
      const row = TomoVisInput.el("div", `tv-pg-export__row${target.depth === 1 ? " tv-pg-export__row--child" : ""}${target.depth === 2 ? " tv-pg-export__row--grandchild" : ""}`, target.label);
      row.addEventListener("click", () => this.selectItem(target));
      target.row = row;
      this.tree.append(row);
    });
    this.selectItem(select);
  }

  selectItem(target) {
    this.selected = target;
    for (const t of this.items) t.row.classList.toggle("is-selected", t === target);
    this.selectBoxVisible = true;
    this.scene.update();
    this.format = 0;
    this.renderFormats();
  }

  renderFormats() {
    this.list.replaceChildren();
    PgExportDialog.EXPORTERS.forEach((cls, i) => {
      const row = TomoVisInput.el("div", `tv-pg-export__row${i === this.format ? " is-selected" : ""}`, cls.NAME);
      row.addEventListener("click", () => {
        this.format = i;
        this.renderFormats();
      });
      this.list.append(row);
    });
    const cls     = PgExportDialog.EXPORTERS[this.format];
    this.exporter = new cls(this, this.selected);
    this.copyBtn.disabled = !cls.allowCopy;
    this.renderParams();
  }

  renderParams() {
    this.params.replaceChildren();
    if (!this.exporter.params) return;
    const kit = this.ctx.kit;
    for (const p of this.exporter.params) {
      const row = TomoVisInput.el("div", "tv-pg-export__param");
      row.append(TomoVisInput.el("span", "tv-label", p.name));
      let view;
      if (p.type === "int" || p.type === "float") {
        view = kit.local(p.type === "int" ? "spin" : "doubleSpin", { decimals: p.type === "float" ? 3 : 0, onChange: (value) => {
          p.value = value;
          this.exporter.parameterChanged(p.name);
        } });
        view.set({ minimum: p.limits[0], maximum: 2147483647, value: p.value });
      } else if (p.type === "bool") {
        view = kit.local("checkbox", { onChange: (checked) => {
          p.value = checked;
          this.exporter.parameterChanged(p.name);
        } });
        view.set({ checked: p.value });
        if (p.tip) view.el.title = p.tip;
      } else if (p.type === "list") {
        view = kit.local("combo", { items: p.limits, onChange: (index) => {
          p.value = p.limits[index];
          this.exporter.parameterChanged(p.name);
        } });
        view.set({ index: p.limits.indexOf(p.value) });
      } else if (p.type === "str") {
        view = kit.local("line", { onChange: (text) => {
          p.value = text;
        } });
        view.set({ text: p.value });
      } else if (p.type === "color") {
        const button = TomoVisInput.el("button", "tv-pg-export__colorbtn");
        button.type = "button";
        const paint = () => {
          button.style.background = PgPen.css(p.value);
        };
        paint();
        button.addEventListener("click", async () => {
          const result = await this.ctx.dialogs.color({ initial: p.value.slice(), title: "Select Color", alpha: true, live: (color) => {
            p.value = color.slice();
            paint();
          } });
          p.value = result.color ? result.color.slice() : p.value;
          paint();
        });
        view = { el: button, set: () => paint() };
      }
      p.view = view;
      row.append(view.el);
      this.params.append(row);
    }
  }

  paintSelectBox(ctx) {
    if (!this.selectBoxVisible || !this.selected) return;
    const r = this.selected.rect();
    ctx.save();
    ctx.strokeStyle = "rgb(255, 255, 0)";
    ctx.lineWidth   = 3;
    ctx.setLineDash([12, 6]);
    ctx.strokeRect(r.x, r.y, r.w, r.h);
    ctx.restore();
  }

  async run(copy) {
    this.selectBoxVisible = false;
    this.scene.update();
    await this.exporter.export(copy);
  }

  close() {
    this.selectBoxVisible = false;
    this.scene.update();
    if (this.el && this.el.isConnected) this.el.remove();
  }
}

window.PgSvgContext         = PgSvgContext;
window.PgExporter           = PgExporter;
window.PgImageExporter      = PgImageExporter;
window.PgSvgExporter        = PgSvgExporter;
window.PgCsvExporter        = PgCsvExporter;
window.PgHdf5Exporter       = PgHdf5Exporter;
window.PgMatplotlibExporter = PgMatplotlibExporter;
window.PgExportDialog       = PgExportDialog;
