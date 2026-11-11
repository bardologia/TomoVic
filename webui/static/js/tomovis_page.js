"use strict";

class TomoVisPage {
  constructor(root) {
    this.root   = root;
    this.active = false;
  }

  enter() {
    this.active = true;
  }

  leave() {
    this.active = false;
  }
}

class TomoVisScriptsPage {
  constructor(root) {
    this.root   = root;
    this.active = false;
  }

  enter() {
    this.active = true;
  }

  leave() {
    this.active = false;
  }
}

window.TomoVisPage        = TomoVisPage;
window.TomoVisScriptsPage = TomoVisScriptsPage;
