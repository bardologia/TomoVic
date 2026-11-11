"use strict";

class TomoVisSlicerScript {
  static FILTER = "HDF5 (*.hd5)";
  static SIZE   = [800, 600];

  constructor(root, ctx) {
    this.root    = root;
    this.ctx     = ctx;
    this.loading = false;

    root.classList.add("tv-script-slicer");
    const head = TomoVisInput.el("div", "tv-script-slicer__head");
    head.append(TomoVisInput.el("h3", "tv-script-slicer__title", "SlicerMatplotlib.py"), TomoVisInput.el("p", "tv-script-slicer__lead", "Every range slice of an .hd5 tomogram with a range attribute, each column normalised to 0..1. Click the figure, then press j for the previous slice and k for the next."));

    const row = TomoVisInput.el("div", "tv-row tv-script-slicer__file");
    this.path = ctx.kit.local("line", { placeholder: "/path/to/tomogram.hd5", onReturn: () => this.load() });
    this.path.set({ text: "", enabled: true });
    this.path.el.classList.add("tv-script-slicer__path");
    this.browseButton = this.button("Browse", () => this.browse());
    this.loadButton   = this.button("Load", () => this.load());
    row.append(TomoVisInput.el("label", "tv-label", "File"), this.path.el, this.browseButton, this.loadButton);

    this.error = TomoVisInput.el("div", "tv-script-slicer__error");
    this.error.setAttribute("role", "alert");
    this.error.hidden = true;

    this.figureHost = TomoVisInput.el("div", "tv-script-slicer__figure");
    this.empty      = TomoVisInput.el("div", "tv-script-slicer__empty", "Load an .hd5 tomogram to open the SlicerMatplotlib figure.");
    this.figureHost.hidden = true;
    root.append(head, row, this.error, this.empty, this.figureHost);
    this.figure = new MplFigureView(this.figureHost, ctx, "script_slicer", { focusable: true, size: TomoVisSlicerScript.SIZE, attach: false });
  }

  button(text, action) {
    const button = TomoVisInput.plainPushButton(TomoVisInput.el("button", "tv-button", text));
    button.type = "button";
    button.addEventListener("click", action);
    return button;
  }

  async browse() {
    const chosen = await this.ctx.dialogs.file({ mode: "open", title: "Open File", filters: [TomoVisSlicerScript.FILTER], selected_filter: TomoVisSlicerScript.FILTER, directory: null, file: null });
    if (!chosen.accepted) return;
    this.path.set({ text: chosen.path });
    this.load();
  }

  showError(text) {
    this.error.textContent = text;
    this.error.hidden      = !text;
  }

  async load() {
    const path = this.path.input.value.trim();
    if (!path) {
      this.showError("Choose an .hd5 file first.");
      return;
    }
    if (this.loading) return;

    this.loading = true;
    this.loadButton.disabled = true;
    this.showError("");
    try {
      await this.ctx.session.scriptSlicer(path);
      this.empty.hidden      = true;
      this.figureHost.hidden = false;
      this.figure.attach();
      this.figure.wrap.focus({ preventScroll: true });
    } catch (error) {
      this.showError(error.message);
      this.ctx.session.raiseUnreported(error);
    } finally {
      this.loading = false;
      this.loadButton.disabled = false;
    }
  }

  activate() {
    this.figure.measure();
  }

  deactivate() {}
}

window.TomoVisSlicerScript = TomoVisSlicerScript;
