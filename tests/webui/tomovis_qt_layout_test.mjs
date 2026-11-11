import assert from "node:assert";
import fs from "node:fs";
import path from "node:path";
import vm from "node:vm";
import { fileURLToPath } from "node:url";

const here    = path.dirname(fileURLToPath(import.meta.url));
const webui   = path.join(here, "..", "..", "webui");
const fixture = JSON.parse(fs.readFileSync(path.join(here, "fixtures", "tomovis_qt_layout", "layout.json"), "utf-8"));

class QtLayoutSandbox {
  constructor() {
    const context = { console, Math, JSON, Array, Object, Number, String, Map, Set, Error };
    context.window = context;
    vm.createContext(context);
    vm.runInContext(fs.readFileSync(path.join(webui, "static", "js", "tomovis_widgets.js"), "utf-8"), context, { filename: "tomovis_widgets.js" });
    this.context = context;
  }

  splitter() {
    return new this.context.QtSplitterModel(2, [{ minimum: 101, hint: 232 }, { minimum: 40, hint: 30, hidden: true }]);
  }

  stacks(steps) {
    const chain = steps.map((pane) => new this.context.QtLayoutStruct({ sizeHint: Math.max(pane.sizeHint, pane.minimumSizeHint), minimumSize: pane.minimumSizeHint, expansive: true, empty: false, spacing: 6 }));
    this.context.QtLayoutEngine.geomCalc(chain, 0, chain.length, 0, steps[0].height + steps[1].height + 6);
    return chain.map((data) => data.size);
  }
}

class QtLayoutSuite {
  constructor() {
    this.sandbox = new QtLayoutSandbox();
    this.passed  = 0;
  }

  test(name, fn) {
    fn();
    this.passed += 1;
  }

  allSteps() {
    return [...Object.values(fixture.roi).flat(), ...fixture.norm, ...fixture.drags];
  }

  distribution() {
    for (const step of this.allSteps()) {
      const got = this.sandbox.stacks([step.imv1_1, step.imv2_1]);
      assert.deepStrictEqual(got, [step.imv1_1.height, step.imv2_1.height], `${step.label} at ${step.window}`);
    }
  }

  showPlot(model, height) {
    model.setSizes([Math.trunc(height * 0.6), Math.trunc(height * 0.4)]);
    model.setHidden(1, false);
    return 232 + Math.max(model.items[1].size, model.items[1].minimum);
  }

  drags() {
    const model  = this.sandbox.splitter();
    const steps  = fixture.drags;
    const pressY = fixture.press_y;
    let   hint   = 232;

    model.setLength(340);
    hint = this.showPlot(model, 340);
    model.setLength(steps[0].imv1_1.height);
    assert.deepStrictEqual(model.sizes(), steps[0].imv1_1.sizes, "roi_on");
    assert.strictEqual(hint, steps[0].imv1_1.sizeHint, "roi_on hint");

    for (const step of steps.slice(1)) {
      if (step.dy !== undefined) {
        const press = model.handleTop(1) + pressY;
        for (let k = 1; k <= fixture.steps; k += 1) model.moveSplitter(press + Math.round(step.dy * k / fixture.steps) - pressY, 1);
      } else if (step.label === "slice_5") {
        model.setSizes([Math.trunc(model.length * 0.6), Math.trunc(model.length * 0.4)]);
      } else if (step.label === "roi_off") {
        model.setHidden(1, true);
        hint = 232;
      } else if (step.label === "roi_on_again") {
        hint = this.showPlot(model, model.length);
      }
      model.setLength(step.imv1_1.height);
      assert.deepStrictEqual(model.sizes(), step.imv1_1.sizes, step.label);
      assert.strictEqual(hint, step.imv1_1.sizeHint, `${step.label} hint`);
    }
  }

  roiToggles() {
    for (const [size, steps] of Object.entries(fixture.roi)) {
      const models = { imv1_1: this.sandbox.splitter(), imv2_1: this.sandbox.splitter() };
      const hints  = { imv1_1: 232, imv2_1: 232 };
      const height = { imv1_1: steps[0].imv1_1.height, imv2_1: steps[0].imv2_1.height };
      for (const name of Object.keys(models)) models[name].setLength(height[name]);

      for (const step of steps.slice(1)) {
        const name  = step.label.startsWith("top") ? "imv1_1" : "imv2_1";
        const model = models[name];
        if (model.items[1].hidden) hints[name] = this.showPlot(model, height[name]);
        else {
          model.setHidden(1, true);
          hints[name] = 232;
        }
        const panes = ["imv1_1", "imv2_1"].map((pane) => ({ height: step[pane].height, sizeHint: hints[pane], minimumSizeHint: models[pane].items[1].hidden ? 101 : 143 }));
        const sizes = this.sandbox.stacks(panes);
        ["imv1_1", "imv2_1"].forEach((pane, i) => {
          height[pane] = sizes[i];
          models[pane].setLength(sizes[i]);
          assert.strictEqual(hints[pane], step[pane].sizeHint, `${size} ${step.label} ${pane} hint`);
          assert.strictEqual(sizes[i], step[pane].height, `${size} ${step.label} ${pane} height`);
          assert.deepStrictEqual(models[pane].sizes(), step[pane].sizes, `${size} ${step.label} ${pane} sizes`);
        });
      }
    }
  }

  run() {
    this.test("qGeomCalc shares the Slicer stacks as QVBoxLayout did at every recorded step", () => this.distribution());
    this.test("QSplitter drags, collapses, resizes and setSizes give the recorded sizes", () => this.drags());
    this.test("ROI toggles cache the splitter hint and resize both panes as recorded", () => this.roiToggles());
    console.log(`all ${this.passed} passing`);
  }
}

new QtLayoutSuite().run();
