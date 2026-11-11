"use strict";

class TomoVisSlicerTab {
  static VIEWS     = ["imv1_1", "imv1_2", "imv2_1", "imv2_2"];
  static VALIDATOR = "-?[0-9]+[.]?[0-9]{,4}";
  static FIELDS    = [["Ax", "tab1QLineEdit1"], ["Ay", "tab1QLineEdit2"], ["Angle [°]", "tab1QLineEdit3"], ["Length", "tab1QLineEdit4"], ["Pos x", "tab1QLineEdit5"], ["Pos y", "tab1QLineEdit6"]];

  constructor(root, ctx) {
    this.root       = root;
    this.ctx        = ctx;
    this.active     = false;
    this.views      = {};
    this.applied    = {};
    this.arrays     = {};
    this.roiSerial  = null;
    this.roiView    = null;
    this.roiPending = 0;
    this.lineView   = null;

    this.build();
    this.buildItems();
    ctx.bus.on("views", (views) => this.receiveViews(views));
    ctx.bus.on("snapshot", ({ snapshot }) => this.render(snapshot));
    if (ctx.session.snapshot) this.render(ctx.session.snapshot);
  }

  build() {
    const kit = this.ctx.kit;
    const el  = TomoVisInput.el;
    this.root.classList.add("tv-slicer");

    this.stacks = [el("div", "tv-slicer__stack"), el("div", "tv-slicer__stack")];
    this.stacks[0].dataset.stack = "imv1";
    this.stacks[1].dataset.stack = "imv2";
    TomoVisSlicerTab.VIEWS.forEach((name, i) => {
      const host = el("div", "tv-slicer__pane");
      host.dataset.view = name;
      this.stacks[i < 2 ? 0 : 1].append(host);
      this.views[name]   = new PgImageView(this.ctx, host, { name: "ImageView" });
      this.applied[name] = -1;
    });

    this.chkBox  = kit.bound("checkbox", "tab1ChkBox");
    this.slider  = kit.bound("slider", "tab1Slider", { minWidth: 400 });
    this.spinBox = kit.bound("spin", "tab1SpinBox", { maxWidth: 180 });
    this.play    = kit.bound("button", "tab1PlayButton", { icon: "/static/img/tomovis/play.png", ariaLabel: "Play" });
    this.combo   = kit.bound("combo", "tab1ComboBox", { items: this.ctx.tables.colortables.names });
    this.slider.el.classList.add("tv-slicer__slider");
    this.play.el.classList.add("tv-slicer__play");

    const row1 = el("div", "tv-row tv-slicer__row");
    row1.append(el("span", "tv-label", "Slices (Automatic):"), this.chkBox.el, this.slider.el, this.spinBox.el, this.play.el, el("span", "tv-label", "Colormap"), this.combo.el, el("span", "tv-stretch"));

    const row2 = el("div", "tv-row tv-slicer__row tv-slicer__roi");
    row2.append(el("span", "tv-label", "ROI (Manual):"));
    this.fields = TomoVisSlicerTab.FIELDS.map(([label, name]) => {
      const view = kit.bound("line", name, { validator: TomoVisSlicerTab.VALIDATOR, maxWidth: 90 });
      view.el.classList.add("tv-slicer__field");
      row2.append(el("span", "tv-label", label), view.el);
      return view;
    });
    this.setButton  = kit.bound("button", "tab1SetButton", { text: "Set", maxWidth: 100 });
    this.plotButton = kit.bound("button", "tab1PlotButton", { text: "Plot", maxWidth: 100 });
    row2.append(el("span", "tv-stretch"), this.setButton.el, this.plotButton.el);

    this.root.replaceChildren(this.stacks[0], this.stacks[1], row1, row2);
  }

  buildItems() {
    this.roi = new PgLineSegmentRoi([[0, 0], [50, 64]], {
      pen            : { color: [255, 255, 255], width: 3 },
      hoverPen       : { color: [255, 255, 255], width: 3 },
      handlePen      : [255, 255, 255],
      handleHoverPen : [255, 255, 0],
      translateSnap  : true,
      removable      : false,
    });
    this.roi.sigRegionChanged.connect(() => this.roiMoved(false));
    this.roi.sigRegionChangeFinished.connect(() => this.roiMoved(true));

    this.sliceLine = new PgInfiniteLine({ pos: 0, angle: 0, pen: { color: "w", width: 3 } });
    this.views.imv1_1.addItem(this.sliceLine);
    this.sliceLine.hide();
    this.lineView = "imv1_1";
  }

  activate() {
    this.active = true;
    for (const view of Object.values(this.views)) {
      for (const scene of [view.scene, view.histogram.view, view.roiPlot.view]) scene.update();
    }
  }

  deactivate() {
    this.active = false;
  }

  receiveViews(views) {
    for (const [name, payload] of Object.entries(views)) {
      if (this.views[name]) this.arrays[name] = payload;
    }
  }

  render(snapshot) {
    this.renderStacks(snapshot.controls);
    this.renderViews(snapshot.views);
    this.renderRoi(snapshot.controls.roi_1);
    this.renderSliceLine(snapshot.controls.slice_line);
  }

  renderStacks(controls) {
    for (const [stack, key] of [[this.stacks[0], "imv1"], [this.stacks[1], "imv2"]]) {
      const current = controls[key].current;
      for (const pane of stack.children) pane.classList.toggle("is-current", pane.dataset.view === current);
    }
  }

  renderViews(states) {
    for (const name of TomoVisSlicerTab.VIEWS) {
      const state   = states[name];
      const payload = this.arrays[name];
      if (state.apply_serial === this.applied[name] && !payload) continue;
      this.applyView(this.views[name], state, payload);
      this.applied[name] = state.apply_serial;
      delete this.arrays[name];
    }
  }

  applyView(view, state, payload) {
    if (!state.has_image) {
      if (view.image !== null) view.clear();
    } else if (payload) {
      view.setImage(payload.array, payload.shape, payload.dtype);
    }
    if (state.colortable !== null && state.colortable !== undefined) view.setColorMap(this.ctx.tables.colortables.tables[state.colortable]);
    if (state.level_mode !== view.histogram.levelMode) view.setLevelMode(state.level_mode);
    if (state.histogram_range) view.setHistogramRange(state.histogram_range[0], state.histogram_range[1]);
    if (state.level_mode === "mono") view.setLevels({ min: state.levels[0], max: state.levels[1] });
    else view.setLevels({ rgba: state.levels });
  }

  dragging() {
    return this.roi.isMoving || this.roi.handles.some((h) => h.item.isMoving);
  }

  renderRoi(state) {
    if (state.view !== this.roiView) {
      if (state.view === null) {
        if (this.roi.vb) this.roi.vb.removeItem(this.roi);
      } else {
        this.views[state.view].addItem(this.roi);
      }
      this.roiView = state.view;
    }
    const serialChanged = state.serial !== this.roiSerial;
    const differs       = JSON.stringify(this.roi.clientState()) !== JSON.stringify({ pos: state.pos, size: state.size, angle: state.angle, handles: state.handles });
    if (serialChanged || (differs && !this.dragging() && this.roiPending === 0)) this.roi.applyServerState(state);
    this.roiSerial = state.serial;
  }

  renderSliceLine(state) {
    if (state.view !== this.lineView) {
      if (state.view === null) {
        if (this.sliceLine.vb) this.sliceLine.vb.removeItem(this.sliceLine);
      } else {
        this.views[state.view].addItem(this.sliceLine);
      }
      this.lineView = state.view;
    }
    this.sliceLine.setPos(state.value);
    if (state.visible !== this.sliceLine.visible) {
      if (state.visible) this.sliceLine.show();
      else this.sliceLine.hide();
    }
  }

  roiMoved(finish) {
    if (!this.ctx.session.snapshot || this.roiView === null) return;
    const event = { type: "roi", state: this.roi.clientState(), free_handle_moved: Boolean(this.roi.freeHandleMoved), finish };
    this.roiPending += 1;
    this.ctx.session.send(event, { coalesce: "roi" }).catch((error) => this.ctx.session.raiseUnreported(error)).finally(() => {
      this.roiPending -= 1;
    });
  }
}

window.TomoVisSlicerTab = TomoVisSlicerTab;
