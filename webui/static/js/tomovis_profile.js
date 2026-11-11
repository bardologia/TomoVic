"use strict";

class TomoVisProfileTab {
  static BUTTON_WIDTH = 100;

  constructor(root, ctx) {
    this.root = root;
    this.ctx  = ctx;

    root.classList.add("tv-profile");
    this.figureHost = TomoVisInput.el("div", "tv-profile__figure");
    this.row        = TomoVisInput.el("div", "tv-row tv-profile__controls");
    root.append(this.figureHost, this.row);

    this.figure = new MplFigureView(this.figureHost, ctx, "profile", { persistent: true });
    this.clear  = ctx.kit.bound("button", "tab3ClearButton", { text: "Clear", maxWidth: TomoVisProfileTab.BUTTON_WIDTH });
    this.row.append(TomoVisInput.el("span", "tv-stretch"), this.clear.el);
  }

  activate() {
    this.figure.measure();
  }

  deactivate() {}
}

window.TomoVisProfileTab = TomoVisProfileTab;
