"use strict";

class VispyPyError extends Error {
  constructor(type, message) {
    super(message);
    this.pyType = type;
  }

  get line() {
    return `${this.pyType}: ${this.message}`;
  }

  get traceback() {
    const frames = String(this.stack).split("\n").filter((frame) => frame.trim().startsWith("at ")).map((frame) => `  ${frame.trim()}`).reverse();
    return ["Traceback (most recent call last):", ...frames, this.line].join("\n");
  }

  chain(next) {
    return `${this.traceback}\n\nDuring handling of the above exception, another exception occurred:\n\n${next.traceback}`;
  }

  static reminder(count) {
    return count === 2 ** Math.floor(Math.log2(count));
  }
}

class VispyPyFormat {
  static float(value) {
    if (Number.isNaN(value)) return "nan";
    if (value === Infinity) return "inf";
    if (value === -Infinity) return "-inf";
    if (value === 0) return Object.is(value, -0) ? "-0.0" : "0.0";

    const [mantissa, exponentText] = value.toExponential().split("e");
    const exponent = Number(exponentText);
    const negative = mantissa.startsWith("-");
    const digits   = mantissa.replace("-", "").replace(".", "");
    const sign     = negative ? "-" : "";

    if (exponent < -4 || exponent >= 16) {
      const fraction = digits.length > 1 ? `.${digits.slice(1)}` : "";
      const power    = `${exponent < 0 ? "-" : "+"}${String(Math.abs(exponent)).padStart(2, "0")}`;
      return `${sign}${digits[0]}${fraction}e${power}`;
    }
    if (exponent < 0) return `${sign}0.${"0".repeat(-exponent - 1)}${digits}`;
    const whole    = digits.slice(0, exponent + 1).padEnd(exponent + 1, "0");
    const fraction = digits.slice(exponent + 1);
    return `${sign}${whole}.${fraction || "0"}`;
  }

  static fixed(value, decimals) {
    if (Number.isNaN(value)) return "nan";
    if (!Number.isFinite(value)) return value > 0 ? "inf" : "-inf";

    const sign      = value < 0 || Object.is(value, -0) ? "-" : "";
    const magnitude = Math.abs(value);
    const exact     = magnitude.toFixed(decimals + 25);
    const kept      = exact.slice(0, exact.length - 25);
    const rest      = exact.slice(exact.length - 25);
    let text        = magnitude.toFixed(decimals);

    if (/^50*$/.test(rest) && Number(kept.replace(".", "").slice(-1)) % 2 === 0) text = kept.endsWith(".") ? kept.slice(0, -1) : kept;
    return `${sign}${text}`;
  }

  static sequence(values, kind) {
    if (kind === "int-tuple") return `(${values.map((v) => String(v)).join(", ")})`;
    const body = values.map((v) => VispyPyFormat.float(v)).join(", ");
    return kind === "list" ? `[${body}]` : `(${body})`;
  }
}

class VispyMatrix {
  static DEG = Math.PI / 180;

  static identity() {
    const m = new Float64Array(16);
    m[0] = m[5] = m[10] = m[15] = 1;
    return m;
  }

  static from(rows) {
    const m = new Float64Array(16);
    for (let r = 0; r < 4; r += 1) for (let c = 0; c < 4; c += 1) m[r * 4 + c] = rows[r][c];
    return m;
  }

  static multiply(a, b) {
    const out = new Float64Array(16);
    for (let r = 0; r < 4; r += 1) {
      for (let c = 0; c < 4; c += 1) {
        let sum = 0;
        for (let k = 0; k < 4; k += 1) sum += a[r * 4 + k] * b[k * 4 + c];
        out[r * 4 + c] = sum;
      }
    }
    return out;
  }

  static multiDot(list) {
    return list.reduce((acc, m) => VispyMatrix.multiply(acc, m));
  }

  static transpose(m) {
    const out = new Float64Array(16);
    for (let r = 0; r < 4; r += 1) for (let c = 0; c < 4; c += 1) out[c * 4 + r] = m[r * 4 + c];
    return out;
  }

  static translate([x, y, z]) {
    return VispyMatrix.from([[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 0], [x, y, z, 1]]);
  }

  static scale([x, y, z]) {
    return VispyMatrix.from([[x, 0, 0, 0], [0, y, 0, 0], [0, 0, z, 0], [0, 0, 0, 1]]);
  }

  static rotate(angle, axis) {
    const radians = angle * VispyMatrix.DEG;
    const norm    = Math.hypot(axis[0], axis[1], axis[2]);
    const [x, y, z] = [axis[0] / norm, axis[1] / norm, axis[2] / norm];
    const c  = Math.cos(radians);
    const s  = Math.sin(radians);
    const cx = (1 - c) * x;
    const cy = (1 - c) * y;
    const cz = (1 - c) * z;
    const rows = [
      [cx * x + c, cy * x - z * s, cz * x + y * s, 0],
      [cx * y + z * s, cy * y + c, cz * y - x * s, 0],
      [cx * z - y * s, cy * z + x * s, cz * z + c, 0],
      [0, 0, 0, 1],
    ];
    return VispyMatrix.transpose(VispyMatrix.from(rows));
  }

  static ortho(left, right, bottom, top, znear, zfar) {
    const m = new Float64Array(16);
    m[0]  = Math.fround(2.0 / (right - left));
    m[12] = Math.fround(-(right + left) / (right - left));
    m[5]  = Math.fround(2.0 / (top - bottom));
    m[13] = Math.fround(-(top + bottom) / (top - bottom));
    m[10] = Math.fround(-2.0 / (zfar - znear));
    m[14] = Math.fround(-(zfar + znear) / (zfar - znear));
    m[15] = 1.0;
    return m;
  }

  static frustum(left, right, bottom, top, znear, zfar) {
    const m = new Float64Array(16);
    m[0]  = Math.fround(2.0 * znear / (right - left));
    m[8]  = Math.fround((right + left) / (right - left));
    m[5]  = Math.fround(2.0 * znear / (top - bottom));
    m[9]  = Math.fround((top + bottom) / (top - bottom));
    m[10] = Math.fround(-(zfar + znear) / (zfar - znear));
    m[14] = Math.fround(-2.0 * znear * zfar / (zfar - znear));
    m[11] = -1.0;
    return m;
  }

  static perspective(fovy, aspect, znear, zfar) {
    const h = Math.tan(fovy / 360.0 * Math.PI) * znear;
    const w = h * aspect;
    return VispyMatrix.frustum(-w, w, -h, h, znear, zfar);
  }

  static solve(a, b) {
    const n = 4;
    const m = a.map((row, i) => [...row, b[i]]);
    for (let col = 0; col < n; col += 1) {
      let pivot = col;
      for (let r = col + 1; r < n; r += 1) if (Math.abs(m[r][col]) > Math.abs(m[pivot][col])) pivot = r;
      [m[col], m[pivot]] = [m[pivot], m[col]];
      for (let r = col + 1; r < n; r += 1) {
        const f = m[r][col] / m[col][col];
        for (let c = col; c <= n; c += 1) m[r][c] -= f * m[col][c];
      }
    }
    const x = new Array(n).fill(0);
    for (let r = n - 1; r >= 0; r -= 1) {
      let sum = m[r][n];
      for (let c = r + 1; c < n; c += 1) sum -= m[r][c] * x[c];
      x[r] = sum / m[r][r];
    }
    return x;
  }

  static affineMap(points1, points2) {
    const a    = points1.map((p) => [p[0], p[1], p[2], 1]);
    const b    = points2.map((p) => [p[0], p[1], p[2], 1]);
    const rows = [[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]];
    for (let i = 0; i < 3; i += 1) rows[i] = VispyMatrix.solve(a, b.map((row) => row[i]));
    return VispyMatrix.from(rows);
  }

  static inverse(m) {
    const a   = [];
    for (let r = 0; r < 4; r += 1) a.push([m[r * 4], m[r * 4 + 1], m[r * 4 + 2], m[r * 4 + 3], r === 0 ? 1 : 0, r === 1 ? 1 : 0, r === 2 ? 1 : 0, r === 3 ? 1 : 0]);
    for (let col = 0; col < 4; col += 1) {
      let pivot = col;
      for (let r = col + 1; r < 4; r += 1) if (Math.abs(a[r][col]) > Math.abs(a[pivot][col])) pivot = r;
      [a[col], a[pivot]] = [a[pivot], a[col]];
      const p = a[col][col];
      for (let c = 0; c < 8; c += 1) a[col][c] /= p;
      for (let r = 0; r < 4; r += 1) {
        if (r === col) continue;
        const f = a[r][col];
        for (let c = 0; c < 8; c += 1) a[r][c] -= f * a[col][c];
      }
    }
    const out = new Float64Array(16);
    for (let r = 0; r < 4; r += 1) for (let c = 0; c < 4; c += 1) out[r * 4 + c] = a[r][c + 4];
    return out;
  }

  static map(m, [x, y, z]) {
    const out = [0, 0, 0, 0];
    const v   = [x, y, z, 1];
    for (let c = 0; c < 4; c += 1) out[c] = v[0] * m[c] + v[1] * m[4 + c] + v[2] * m[8 + c] + v[3] * m[12 + c];
    return out;
  }

  static dot3(m3, v) {
    return [0, 1, 2].map((r) => m3[r * 4] * v[0] + m3[r * 4 + 1] * v[1] + m3[r * 4 + 2] * v[2]);
  }

  static viewboxMapping([w, h]) {
    return VispyMatrix.from([[w / 2, 0, 0, 0], [0, -h / 2, 0, 0], [0, 0, 1, 0], [w / 2, h / 2, 0, 1]]);
  }

  static float32(m) {
    return Float32Array.from(m);
  }
}

class VispyQuaternion {
  constructor(w = 1, x = 0, y = 0, z = 0, normalize = true) {
    this.w = Number(w);
    this.x = Number(x);
    this.y = Number(y);
    this.z = Number(z);
    if (normalize) this.normalizeInPlace();
  }

  copy() {
    return new VispyQuaternion(this.w, this.x, this.y, this.z, false);
  }

  norm() {
    return Math.pow(this.w ** 2 + this.x ** 2 + this.y ** 2 + this.z ** 2, 0.5);
  }

  normalizeInPlace() {
    const length = this.norm();
    if (!length) throw new VispyPyError("ValueError", "Quaternion cannot have 0-length.");
    this.w /= length;
    this.x /= length;
    this.y /= length;
    this.z /= length;
  }

  normalize() {
    const next = this.copy();
    next.normalizeInPlace();
    return next;
  }

  conjugate() {
    const next = this.copy();
    next.x *= -1;
    next.y *= -1;
    next.z *= -1;
    return next;
  }

  inverse() {
    const next = this.conjugate();
    const tmp  = this.norm() ** 2;
    next.w /= tmp;
    next.x /= tmp;
    next.y /= tmp;
    next.z /= tmp;
    return next;
  }

  multiply(q2) {
    const q1   = this;
    const next = new VispyQuaternion();
    next.w = q1.w * q2.w - q1.x * q2.x - q1.y * q2.y - q1.z * q2.z;
    next.x = q1.w * q2.x + q1.x * q2.w + q1.y * q2.z - q1.z * q2.y;
    next.y = q1.w * q2.y + q1.y * q2.w + q1.z * q2.x - q1.x * q2.z;
    next.z = q1.w * q2.z + q1.z * q2.w + q1.x * q2.y - q1.y * q2.x;
    return next;
  }

  rotatePoint(p) {
    const point = new VispyQuaternion(0, p[0], p[1], p[2], false);
    const q1    = this.normalize();
    const q2    = this.inverse();
    const r     = q1.multiply(point).multiply(q2);
    return [r.x, r.y, r.z];
  }

  axisAngle() {
    const angle = 2 * Math.acos(Math.max(Math.min(this.w, 1.0), -1.0));
    const scale = Math.pow(this.x ** 2 + this.y ** 2 + this.z ** 2, 0.5);
    if (scale) return [angle, this.x / scale, this.y / scale, this.z / scale];
    return [angle, 1, 0, 0];
  }

  static fromAxisAngle(angle, ax, ay, az) {
    let a = angle;
    while (a < 0) a += Math.PI * 2;
    const half = a / 2.0;
    const s    = Math.sin(half);
    return new VispyQuaternion(Math.cos(half), ax * s, ay * s, az * s);
  }

  toArray() {
    return [this.w, this.x, this.y, this.z];
  }
}

class VispyCycle {
  constructor(items) {
    this.items = items;
    this.index = 0;
  }

  next() {
    const item = this.items[this.index];
    this.index = (this.index + 1) % this.items.length;
    return item;
  }
}

class VispyColormap {
  static serial = 0;

  constructor(entry, kind) {
    this.name  = entry.name;
    this.kind  = kind;
    this.cls   = entry.class;
    this.es300 = entry.es300;
    this.lut   = entry.lut ? VispyColormap.decode(entry.lut) : null;
    VispyColormap.serial += 1;
    this.address = `0x7f${(0x3a5c10 + VispyColormap.serial * 0x2f1b).toString(16).padStart(6, "0")}b0`;
  }

  static decode(text) {
    const binary = atob(text);
    const bytes  = new Uint8Array(binary.length);
    for (let i = 0; i < binary.length; i += 1) bytes[i] = binary.charCodeAt(i);
    return new Float32Array(bytes.buffer);
  }

  repr() {
    if (this.kind === "opaque") return this.name;
    return `<Visualizer.visualizer.Volume.initTranslucentColormaps.<locals>.${this.cls} object at ${this.address}>`;
  }

  sample(t) {
    if (!this.lut) throw new Error(`VispyColormap ${this.name} has no lookup table`);
    const n = this.lut.length / 4;
    const p = Math.min(Math.max(t, 0), 1) * n - 0.5;
    const i = Math.floor(p);
    const f = p - i;
    const a = Math.min(Math.max(i, 0), n - 1);
    const b = Math.min(Math.max(i + 1, 0), n - 1);
    return [0, 1, 2, 3].map((c) => this.lut[a * 4 + c] * (1 - f) + this.lut[b * 4 + c] * f);
  }
}

class VispyColormaps {
  static URL     = "/static/data/tomovis_vispy_colormaps.json";
  static pending = null;

  constructor(document) {
    this.vispy       = document.vispy;
    this.names       = document.opaque.map((entry) => entry.name);
    this.entries     = new Map(document.opaque.map((entry) => [entry.name, entry]));
    this.translucent = document.translucent;
    this.cache       = new Map();
  }

  static load() {
    if (!VispyColormaps.pending) {
      VispyColormaps.pending = Api.get(VispyColormaps.URL).then((document) => {
        if (document.error) {
          VispyColormaps.pending = null;
          throw new Error(`vispy colormaps could not be loaded: ${document.error}`);
        }
        return new VispyColormaps(document);
      });
    }
    return VispyColormaps.pending;
  }

  get(name) {
    if (!this.cache.has(name)) {
      const entry = this.entries.get(name);
      if (!entry) throw new VispyPyError("KeyError", `colormap name ${name} not found`);
      this.cache.set(name, new VispyColormap(entry, "opaque"));
    }
    return this.cache.get(name);
  }

  translucentMaps() {
    return this.translucent.map((entry) => new VispyColormap(entry, "translucent"));
  }

  resolve(cmap) {
    return typeof cmap === "string" ? this.get(cmap) : cmap;
  }
}

class VispyCameraBase {
  static ZOOM_FACTOR = 0.007;
  static STATE_PROPS = ["scale_factor", "center", "fov"];
  static DIMS        = { "+z": [[0, 0, 1], [0, 1, 0]], "-z": [[0, 0, -1], [0, 1, 0]], "+y": [[0, 1, 0], [1, 0, 0]], "-y": [[0, -1, 0], [1, 0, 0]], "+x": [[1, 0, 0], [0, 0, 1]], "-x": [[-1, 0, 0], [0, 0, 1]] };

  constructor({ fov = 60.0, name = null, interactive = true, flip = null, up = "+z" } = {}) {
    this.name            = name;
    this.viewbox         = null;
    this.resetting       = false;
    this.setRangeArgs    = null;
    this.xlim            = null;
    this.ylim            = null;
    this.zlim            = null;
    this.defaultState    = null;
    this._fov            = 0.0;
    this._center         = null;
    this.depthValue      = 1e6;
    this.interactive     = Boolean(interactive);
    this.eventValue      = null;
    this.distance        = null;
    this.actualDistance  = 0.0;
    this.transform       = VispyMatrix.identity();
    this.projection      = VispyMatrix.identity();
    this.clipTransform   = VispyMatrix.identity();
    this.sceneTransform  = VispyMatrix.identity();
    this.flip            = flip || [false, false, false];
    this.flipFactors     = this.flip.map((x) => 1 - (x ? 1 : 0) * 2);
    this.up              = up;
    this._scaleFactor    = null;
    this.fov             = fov;
  }

  get stateProps() {
    return VispyCameraBase.STATE_PROPS;
  }

  get fov() {
    return this._fov;
  }

  set fov(value) {
    const fov = Number(value);
    if (fov < 0 || fov > 180) throw new VispyPyError("ValueError", "fov must be 0 <= fov <= 180.");
    this._fov = fov;
    this.viewChanged();
  }

  get center() {
    return this._center || { value: [0, 0, 0], kind: "int-tuple" };
  }

  set center(val) {
    const value  = val.value || val;
    const center = value.length === 2 ? [Number(value[0]), Number(value[1]), 0.0] : value.map(Number);
    if (value.length !== 2 && value.length !== 3) throw new VispyPyError("ValueError", "Center must be a 2 or 3 element tuple");
    if (this._center && this._center.kind !== "list" && this._center.value.every((v, i) => v === center[i])) return;
    this._center = { value: center, kind: "tuple" };
    this.viewChanged();
  }

  get scaleFactor() {
    return this._scaleFactor;
  }

  set scaleFactor(value) {
    if (value === null) throw new VispyPyError("TypeError", "float() argument must be a string or a real number, not 'NoneType'");
    const scale = Math.abs(Number(value));
    if (scale === this._scaleFactor) return;
    this._scaleFactor = scale;
    this.viewChanged();
  }

  dimVectors() {
    const [up, forward] = VispyCameraBase.DIMS[this.up];
    const right = [forward[1] * up[2] - forward[2] * up[1], forward[2] * up[0] - forward[0] * up[2], forward[0] * up[1] - forward[1] * up[0]];
    return [up, forward, right];
  }

  viewboxSet(viewbox) {
    this.viewbox = viewbox;
  }

  viewboxUnset() {
    this.viewbox = null;
  }

  blockUpdates(fn) {
    const previous = this.resetting;
    this.resetting = true;
    try {
      fn();
    } finally {
      this.resetting = previous;
    }
  }

  setRange({ x = null, y = null, z = null, margin = 0.05 } = {}) {
    const init = this.xlim === null;
    let bounds = [x, y, z].map((b) => (b === null ? null : [Number(b[0]), Number(b[1])]));

    if (this.viewbox === null) {
      this.setRangeArgs = { x: bounds[0], y: bounds[1], z: bounds[2], margin };
      return;
    }

    this.blockUpdates(() => {
      if (bounds.every((b) => b === null)) bounds = this.viewbox.sceneBounds();
      else bounds = bounds.map((b, i) => (b === null ? this.viewbox.sceneBounds(i) : b));

      const ranges  = bounds.map((b) => b[1] - b[0]);
      const margins = ranges.map((r) => (r * margin) || 0.1);
      const limits  = bounds.map((b, i) => [b[0] - margins[i], b[1] + margins[i]]);
      [this.xlim, this.ylim, this.zlim] = limits;
      if (!init || this._center === null) this._center = { value: bounds.map((b, i) => b[0] + ranges[i] / 2), kind: "list" };
      this.applyRange(init);
    });
    this.viewChanged();
  }

  applyRange(init) {
    if (init && this._scaleFactor !== null) return;

    const [w, h] = this.viewbox.size;
    if (w === 0 || h === 0) return;

    let rx = this.xlim[1] - this.xlim[0];
    let ry = this.ylim[1] - this.ylim[0];
    let rz = this.zlim[1] - this.zlim[0];
    if (w / h > 1) {
      rx /= w / h;
      ry /= w / h;
    } else {
      rz /= h / w;
    }

    const rxs = Math.pow(rx ** 2 + ry ** 2, 0.5);
    const rys = Math.pow(rx ** 2 + ry ** 2 + rz ** 2, 0.5);
    this.scaleFactor = Math.max(rxs, rys) * 1.04;
  }

  reset() {
    this.setState(this.defaultState);
  }

  setDefaultState() {
    this.defaultState = this.getState();
  }

  getState() {
    const state = {};
    for (const key of this.stateProps) state[key] = this.stateValue(key);
    return state;
  }

  stateValue(key) {
    if (key === "scale_factor") return this._scaleFactor;
    if (key === "center") return this.center;
    if (key === "fov") return this._fov;
    throw new VispyPyError("KeyError", `Not a valid camera state property '${key}'`);
  }

  applyStateValue(key, value) {
    if (key === "scale_factor") this.scaleFactor = value;
    else if (key === "center") this.center = value;
    else if (key === "fov") this.fov = value;
    else throw new VispyPyError("KeyError", `Not a valid camera state property '${key}'`);
  }

  setState(state) {
    const values = state || {};
    this.blockUpdates(() => {
      for (const [key, value] of Object.entries(values)) {
        if (!this.stateProps.includes(key)) throw new VispyPyError("KeyError", `Not a valid camera state property '${key}'`);
        this.applyStateValue(key, value);
      }
    });
    this.viewChanged();
  }

  viewChanged() {
    if (this.resetting) return;
    if (this.viewbox) {
      if (this.xlim === null) this.setRange(this.setRangeArgs || {});
      if (this.defaultState === null) this.setDefaultState();
      this.updateTransform();
    }
  }

  viewboxMouseEvent(event) {
    if (event.type === "mouse_wheel") {
      if (this._scaleFactor === null) throw new VispyPyError("TypeError", "unsupported operand type(s) for *=: 'NoneType' and 'float'");
      const s = Math.pow(1.1, -event.delta[1]);
      this._scaleFactor *= s;
      if (this.distance !== null) this.distance *= s;
      this.viewChanged();
    }
  }

  viewboxKeyEvent(event) {
    if (event.key === "Backspace") this.reset();
  }

  viewboxResizeEvent() {
    this.viewChanged();
  }

  updateTransform() {
    if (this.viewbox === null || this.resetting) return;
    if (this._scaleFactor === null) throw new VispyPyError("TypeError", "unsupported operand type(s) for *=: 'NoneType' and 'float'");

    let fx = this._scaleFactor;
    let fy = this._scaleFactor;
    const [w, h] = this.viewbox.size;
    if (w === 0 || h === 0) return;
    if (w / h > 1) fx *= w / h;
    else fy *= h / w;

    this.updateProjection(fx, fy);
    this.clipTransform  = VispyMatrix.multiply(VispyMatrix.inverse(this.transform), this.projection);
    this.sceneTransform = VispyMatrix.multiply(this.clipTransform, VispyMatrix.viewboxMapping(this.viewbox.size));
    this.viewbox.sceneChanged(this);
  }

  updateProjection(fx, fy) {
    const fov  = Math.max(0.01, this._fov);
    const dist = fy / (2 * Math.tan(fov * VispyMatrix.DEG / 2));
    const val  = Math.sqrt(this.depthValue);
    this.projection = VispyMatrix.perspective(fov, fx / fy, dist / val, dist * val);
  }
}

class VispyRotationCamera extends VispyCameraBase {
  constructor(options = {}) {
    super(options);
    this.actualDistance = 0.0;
    this.eventValue     = null;
    this.translateSpeed = 1.0;
  }

  static typeName(value) {
    if (typeof value === "number") return "float";
    if (Array.isArray(value)) return value.pyKind || "tuple";
    return "NoneType";
  }

  static index(value, i) {
    if (!Array.isArray(value)) throw new VispyPyError("TypeError", `'${VispyRotationCamera.typeName(value)}' object is not subscriptable`);
    return value[i];
  }

  static length(value) {
    if (!Array.isArray(value)) throw new VispyPyError("TypeError", `object of type '${VispyRotationCamera.typeName(value)}' has no len()`);
    return value.length;
  }

  static pair(a, b) {
    const value = [a, b];
    value.pyKind = "tuple";
    return value;
  }

  viewboxMouseEvent(event) {
    if (event.handled || !this.interactive) return;

    super.viewboxMouseEvent(event);

    if (event.type === "mouse_release") {
      this.eventValue = null;
    } else if (event.type === "mouse_press") {
      event.handled = true;
    } else if (event.type === "mouse_move") {
      if (event.pressEvent === null) return;
      if (event.buttons.includes(1) && event.buttons.includes(2)) return;

      const modifiers = event.mouseEvent.modifiers;
      const p1        = event.mouseEvent.pressEvent.pos;
      const p2        = event.mouseEvent.pos;
      const d         = [p2[0] - p1[0], p2[1] - p1[1]];
      const shift     = modifiers.includes("shift");

      if (event.buttons.includes(1) && modifiers.length === 0) {
        this.updateRotation(event);
      } else if (event.buttons.includes(2) && modifiers.length === 0) {
        if (this.eventValue === null) this.eventValue = VispyRotationCamera.pair(this._scaleFactor, this.distance);
        const zoomy = Math.pow(1 + VispyCameraBase.ZOOM_FACTOR, d[1]);
        this.scaleFactor = VispyRotationCamera.index(this.eventValue, 0) * zoomy;
        if (this.distance !== null) this.distance = VispyRotationCamera.index(this.eventValue, 1) * zoomy;
        this.viewChanged();
      } else if (event.buttons.includes(1) && shift) {
        const norm = (this.viewbox.size[0] + this.viewbox.size[1]) / 2;
        if (this.eventValue === null || VispyRotationCamera.length(this.eventValue) === 2) {
          const center = this.center;
          this.eventValue = [...center.value];
          this.eventValue.pyKind = center.kind === "list" ? "list" : "tuple";
        }
        const dist = [(p1[0] - p2[0]) / norm * this._scaleFactor, (p1[1] - p2[1]) / norm * this._scaleFactor];
        dist[1] *= -1;
        let [dx, dy, dz] = this.distToTrans(dist);
        const ff = this.flipFactors;
        const [up, forward, right] = this.dimVectors();
        const moved = [0, 1, 2].map((i) => right[i] * dx + forward[i] * dy + up[i] * dz);
        [dx, dy, dz] = [ff[0] * moved[0], ff[1] * moved[1], moved[2] * ff[2]];
        const c = this.eventValue;
        this.center = [c[0] + dx, c[1] + dy, c[2] + dz];
      } else if (event.buttons.includes(2) && shift) {
        if (this.eventValue === null) this.eventValue = this._fov;
        if (typeof this.eventValue !== "number") throw new VispyPyError("TypeError", `unsupported operand type(s) for -: '${VispyRotationCamera.typeName(this.eventValue)}' and 'float'`);
        const fov = this.eventValue - d[1] / 5.0;
        this.fov = Math.min(180.0, Math.max(0.0, fov));
      }
    }
  }

  updateProjection(fx, fy) {
    const d = this.depthValue;
    if (this._fov === 0) {
      this.projection     = VispyMatrix.ortho(-0.5 * fx, 0.5 * fx, -0.5 * fy, 0.5 * fy, -d, d);
      this.actualDistance = this.distance || 0.0;
    } else {
      const fov  = Math.max(0.01, this._fov);
      let dist   = fy / (2 * Math.tan(fov * VispyMatrix.DEG / 2));
      dist       = this.distance || dist;
      this.actualDistance = dist;
      const val  = Math.sqrt(d * 10);
      this.projection = VispyMatrix.perspective(fov, fx / fy, dist / val, dist * val);
    }
    this.updateCameraPos();
  }

  updateCameraPos() {
    const [up, forward, right] = this.dimVectors();
    const pp1   = [[0, 0, 0], [0, 0, -1], [1, 0, 0], [0, 1, 0]];
    const pp2   = [[0, 0, 0], forward, right, up];
    const pos   = forward.map((v) => -this.actualDistance * v);
    const scale = this.flipFactors.map((a) => 1.0 / a);

    this.transform = VispyMatrix.multiDot([
      VispyMatrix.transpose(VispyMatrix.affineMap(pp1, pp2)),
      VispyMatrix.translate(pos),
      this.rotationTransform(),
      VispyMatrix.scale(scale),
      VispyMatrix.translate(this.center.value),
    ]);
  }
}

class VispyTurntableCamera extends VispyRotationCamera {
  static STATE_PROPS = [...VispyCameraBase.STATE_PROPS, "elevation", "azimuth", "roll"];

  constructor({ fov = 45.0, elevation = 30.0, azimuth = 30.0, roll = 0.0, distance = null, translateSpeed = 1.0, ...options } = {}) {
    super({ fov, ...options });
    this._azimuth   = azimuth;
    this._elevation = elevation;
    this._roll      = roll;
    this.azimuth    = azimuth;
    this.elevation  = elevation;
    this.roll       = roll;
    this.distance   = distance;
    this.translateSpeed = translateSpeed;
  }

  get stateProps() {
    return VispyTurntableCamera.STATE_PROPS;
  }

  get elevation() {
    return this._elevation;
  }

  set elevation(value) {
    const elev = Math.min(90, Math.max(-90, Number(value)));
    if (elev === this._elevation) return;
    this._elevation = elev;
    this.viewChanged();
  }

  get azimuth() {
    return this._azimuth;
  }

  set azimuth(value) {
    let azim = Number(value);
    while (azim < -180) azim += 360;
    while (azim > 180) azim -= 360;
    if (azim === this._azimuth) return;
    this._azimuth = azim;
    this.viewChanged();
  }

  get roll() {
    return this._roll;
  }

  set roll(value) {
    let roll = Number(value);
    while (roll < -180) roll += 360;
    while (roll > 180) roll -= 360;
    if (roll === this._roll) return;
    this._roll = roll;
    this.viewChanged();
  }

  stateValue(key) {
    if (key === "elevation") return this._elevation;
    if (key === "azimuth") return this._azimuth;
    if (key === "roll") return this._roll;
    return super.stateValue(key);
  }

  applyStateValue(key, value) {
    if (key === "elevation") this.elevation = value;
    else if (key === "azimuth") this.azimuth = value;
    else if (key === "roll") this.roll = value;
    else super.applyStateValue(key, value);
  }

  updateRotation(event) {
    const p1 = event.mouseEvent.pressEvent.pos;
    const p2 = event.mouseEvent.pos;
    if (this.eventValue === null) this.eventValue = VispyRotationCamera.pair(this.azimuth, this.elevation);
    this.azimuth   = VispyRotationCamera.index(this.eventValue, 0) - (p2[0] - p1[0]) * 0.5;
    this.elevation = VispyRotationCamera.index(this.eventValue, 1) + (p2[1] - p1[1]) * 0.5;
  }

  rotationTransform() {
    const [up, forward, right] = this.dimVectors();
    return VispyMatrix.multiDot([
      VispyMatrix.rotate(this.elevation, right.map((v) => -v)),
      VispyMatrix.rotate(this.azimuth, up),
      VispyMatrix.rotate(this.roll, forward),
    ]);
  }

  distToTrans(dist) {
    const [sro, saz, sel] = [this.roll, this.azimuth, this.elevation].map((a) => Math.sin(a * Math.PI / 180));
    const [cro, caz, cel] = [this.roll, this.azimuth, this.elevation].map((a) => Math.cos(a * Math.PI / 180));
    const [d0, d1] = dist;
    const dx = (+d0 * (cro * caz + sro * sel * saz) + d1 * (sro * caz - cro * sel * saz)) * this.translateSpeed;
    const dy = (+d0 * (cro * saz - sro * sel * caz) + d1 * (sro * saz + cro * sel * caz)) * this.translateSpeed;
    const dz = (-d0 * sro * cel + d1 * cro * cel) * this.translateSpeed;
    return [dx, dy, dz];
  }
}

class VispyArcballCamera extends VispyRotationCamera {
  static STATE_PROPS = [...VispyCameraBase.STATE_PROPS, "_quaternion"];

  constructor({ fov = 45.0, distance = null, translateSpeed = 1.0, ...options } = {}) {
    super({ fov, ...options });
    this.quaternion     = new VispyQuaternion();
    this.distance       = distance;
    this.translateSpeed = translateSpeed;
  }

  get stateProps() {
    return VispyArcballCamera.STATE_PROPS;
  }

  stateValue(key) {
    if (key === "_quaternion") return this.quaternion;
    return super.stateValue(key);
  }

  applyStateValue(key, value) {
    if (key === "_quaternion") this.quaternion = value;
    else super.applyStateValue(key, value);
  }

  static arcball([x0, y0], [w, h]) {
    if (x0 === null || y0 === null) throw new VispyPyError("TypeError", "unsupported operand type(s) for *: 'float' and 'NoneType'");
    const r = (w + h) / 2.0;
    const x = -(2.0 * x0 - w) / r;
    const y = (2.0 * y0 - h) / r;
    const n = Math.sqrt(x * x + y * y);
    return n > 1.0 ? [0.0, x / n, y / n, 0.0] : [0.0, x, y, Math.sqrt(1.0 - n * n)];
  }

  updateRotation(event) {
    const p2 = [event.pos[0], event.pos[1]];
    if (this.eventValue === null) this.eventValue = p2;
    const wh = this.viewbox.size;
    const p1 = [VispyRotationCamera.index(this.eventValue, 0), this.eventValue.length > 1 ? this.eventValue[1] : null];
    this.quaternion = new VispyQuaternion(...VispyArcballCamera.arcball(p2, wh)).multiply(new VispyQuaternion(...VispyArcballCamera.arcball(p1, wh))).multiply(this.quaternion);
    this.eventValue = p2;
    this.viewChanged();
  }

  rotationTransform() {
    const [rot, x, y, z] = this.quaternion.axisAngle();
    return VispyMatrix.rotate(180 * rot / Math.PI, [x, z, y]);
  }

  distToTrans(dist) {
    const [rot, x, y, z] = this.quaternion.axisAngle();
    const tr = VispyMatrix.multiply(VispyMatrix.identity(), VispyMatrix.rotate(180 * rot / Math.PI, [x, y, z]));
    const [dx, dz, dy] = VispyMatrix.dot3(tr, [dist[0], dist[1], 0.0]).map((v) => v * this.translateSpeed);
    return [dx, dy, dz];
  }

  dimVectors() {
    return [[0, 0, 1], [0, 1, 0], [1, 0, 0]];
  }
}

class VispyTimer {
  constructor(interval, callback, onError) {
    this.interval = interval;
    this.callback = callback;
    this.onError  = onError;
    this.handle   = null;
    this.last     = 0;
    this.errors   = 0;
  }

  get running() {
    return this.handle !== null;
  }

  start() {
    if (this.handle !== null) return;
    this.last   = performance.now();
    this.handle = setInterval(() => this.fire(), this.interval * 1000);
  }

  fire() {
    const now = performance.now();
    const dt  = (now - this.last) / 1000;
    this.last = now;
    this.emit(dt);
  }

  emit(dt) {
    try {
      this.callback({ dt });
    } catch (error) {
      this.errors += 1;
      this.onError(error, this.errors);
    }
  }

  stop() {
    if (this.handle !== null) clearInterval(this.handle);
    this.handle = null;
  }
}

class VispyFlyCamera extends VispyCameraBase {
  static STATE_PROPS = [...VispyCameraBase.STATE_PROPS, "rotation1", "rotation2"];

  constructor({ fov = 60, timerError = null, ...options } = {}) {
    super({ fov, ...options });
    this.speed            = [0, 0, 0, 0, 0, 0];
    this.brake            = [0, 0, 0, 0, 0, 0];
    this.acc              = [0, 0, 0, 0, 0, 0];
    this.distance         = null;
    this.autoRoll         = true;
    this._rotation1       = new VispyQuaternion();
    this._rotation2       = new VispyQuaternion();
    this.eventValue       = null;
    this.updateFromMouse  = false;
    this.keymap           = {
      Up: [+1, 1], Down: [-1, 1], Right: [+1, 2], Left: [-1, 2],
      W: [+1, 1], S: [-1, 1], D: [+1, 2], A: [-1, 2],
      F: [+1, 3], C: [-1, 3], I: [+1, 4], K: [-1, 4],
      L: [+1, 5], J: [-1, 5], Q: [+1, 6], E: [-1, 6],
      Space: [0, 1, 2, 3],
    };
    this.timer = new VispyTimer(0.01, (event) => this.onTimer(event), (error, count) => (timerError ? timerError(error, count) : null));
  }

  get stateProps() {
    return VispyFlyCamera.STATE_PROPS;
  }

  get rotation() {
    return this._rotation2.multiply(this._rotation1).normalize();
  }

  get rotation1() {
    return this._rotation1;
  }

  set rotation1(value) {
    this._rotation1 = value.normalize();
  }

  get rotation2() {
    return this._rotation2;
  }

  set rotation2(value) {
    this._rotation2 = value.normalize();
  }

  stateValue(key) {
    if (key === "rotation1") return this._rotation1;
    if (key === "rotation2") return this._rotation2;
    return super.stateValue(key);
  }

  applyStateValue(key, value) {
    if (key === "rotation1") this.rotation1 = value;
    else if (key === "rotation2") this.rotation2 = value;
    else super.applyStateValue(key, value);
  }

  applyRange() {
    this.speed = this.speed.map((v) => v * 0.0);

    const [w, h] = this.viewbox.size;
    const [x1, y1, z1] = [this.xlim[0], this.ylim[0], this.zlim[0]];
    let rx = this.xlim[1] - x1;
    let ry = this.ylim[1] - y1;
    let rz = this.zlim[1] - z1;
    if (w / h > 1) {
      rx /= w / h;
      ry /= w / h;
    } else {
      rz /= h / w;
    }

    this._scaleFactor = Math.max(rx, ry, rz) / 3.0;
    const margin      = (rx + ry + rz) / 3 * 0.1;
    this._center      = { value: [x1 - margin, y1 - margin, z1 + margin], kind: "tuple" };

    let yaw     = 45 * this.flipFactors[0];
    const pitch = -90 - 20 * this.flipFactors[2];
    if (this.flipFactors[1] < 0) yaw += 90 * Math.sign(this.flipFactors[0]);

    const q1 = VispyQuaternion.fromAxisAngle(pitch * Math.PI / 180, 1, 0, 0);
    const q2 = VispyQuaternion.fromAxisAngle(0 * Math.PI / 180, 0, 1, 0);
    const q3 = VispyQuaternion.fromAxisAngle(yaw * Math.PI / 180, 0, 0, 1);
    this._rotation1 = q1.multiply(q2).multiply(q3).normalize();
    this._rotation2 = new VispyQuaternion();
    this.viewChanged();
  }

  directions() {
    const rotation = this.rotation.inverse();
    const unit     = (p) => {
      const length = Math.pow(p[0] ** 2 + p[1] ** 2 + p[2] ** 2, 0.5);
      return p.map((v) => v / length);
    };
    return [[0, 0, -1], [1, 0, 0], [-1, 0, 0], [0, 1, 0]].map((p) => unit(rotation.rotatePoint(p)));
  }

  onTimer(event) {
    const relSpeed = event.dt;
    const relAcc   = 0.1;
    const [pf, pr, pl, pu] = this.directions();

    this.speed = this.speed.map((v, i) => v + this.acc[i] * relAcc);
    const reduce = [0.05, 0.05, 0.05, 0.1, 0.1, 0.1].map((r, i) => (this.brake[i] > 0 ? 0.2 : r));
    this.speed = this.speed.map((v, i) => v - v * reduce[i]);
    if (Math.max(...this.speed.map(Math.abs)) < 0.05) this.speed = this.speed.map((v) => v * 0.0);

    if (this.speed.slice(0, 3).some((v) => v !== 0)) {
      if (this._scaleFactor === null) throw new VispyPyError("TypeError", "unsupported operand type(s) for *: 'float' and 'NoneType'");
      const dv = this.flipFactors.map((d) => 1.0 / d);
      const vf = pf.map((p, i) => p * dv[i] * relSpeed * this._scaleFactor);
      const vr = pr.map((p, i) => p * dv[i] * relSpeed * this._scaleFactor);
      const vu = pu.map((p, i) => p * dv[i] * relSpeed * this._scaleFactor);
      const center = (this._center ? this._center.value : [0, 0, 0]).map(Math.fround);
      const moved  = center.map((c, i) => Math.fround(c + (this.speed[0] * vf[i] + this.speed[1] * vr[i] + this.speed[2] * vu[i])));
      this._center = { value: moved, kind: "float32-tuple" };
    }

    let rollAngle = 0;
    if (this.speed.slice(3).some((v) => v !== 0)) {
      const gain   = [1.0, 1.5, 1.0].map((g) => g * 3 * Math.PI / 180);
      const angles = this.speed.slice(3).map((v, i) => v * gain[i]);
      const q1 = VispyQuaternion.fromAxisAngle(angles[0], -1, 0, 0);
      const q2 = VispyQuaternion.fromAxisAngle(angles[1], 0, 1, 0);
      const q3 = VispyQuaternion.fromAxisAngle(angles[2], 0, 0, -1);
      const q  = q1.multiply(q2).multiply(q3);
      this._rotation1 = q.multiply(this._rotation1).normalize();
    }

    if (this.autoRoll) {
      const axis = { x: [1, 0, 0], y: [0, 1, 0], z: [0, 0, 1] }[this.up[1]];
      const up   = axis.map((v) => v * (this.up[0] === "+" ? 1 : -1));
      const angle = (p1, p2) => Math.acos(p1[0] * p2[0] + p1[1] * p2[1] + p1[2] * p2[2]);
      const ar = angle(pr, up);
      const al = angle(pl, up);
      const af = angle(pf, up);
      rollAngle  = Math.sin(0.5 * (al - ar));
      rollAngle *= Math.abs(Math.sin(af));
      if (Math.abs(rollAngle) < 0.05) rollAngle = 0;
      if (rollAngle) {
        rollAngle = Math.sign(rollAngle) * Math.pow(Math.abs(rollAngle), 0.5);
        const correction = 1.0 * rollAngle * Math.PI / 180;
        const q = VispyQuaternion.fromAxisAngle(correction, 0, 0, 1);
        this._rotation1 = q.multiply(this._rotation1).normalize();
      }
    }

    if (this.speed.some((v) => v !== 0) || rollAngle || this.updateFromMouse) {
      this.updateFromMouse = false;
      this.viewChanged();
    }
  }

  viewboxKeyEvent(event) {
    super.viewboxKeyEvent(event);

    if (event.handled || !this.interactive) return;
    if (!this.timer.running) this.timer.start();

    const valDims = this.keymap[event.key];
    if (!valDims) return;
    let val = valDims[0];
    let vec = this.acc;
    if (val === 0) {
      vec = this.brake;
      val = 1;
    }
    if (event.type === "key_release") val = 0;
    for (const dim of valDims.slice(1)) vec[dim - 1] = val * 1.0;
    event.handled = true;
  }

  viewboxMouseEvent(event) {
    super.viewboxMouseEvent(event);

    if (event.handled || !this.interactive) return;

    if (event.type === "mouse_wheel") {
      const modifiers = event.mouseEvent.modifiers;
      if (modifiers.length === 0) {
        this.speed[0] += 0.5 * event.delta[1];
      } else if (modifiers.includes("shift")) {
        const s = Math.pow(1.1, -event.delta[1]);
        this.scaleFactor = this._scaleFactor / s;
        this.print(`scale factor: ${VispyPyFormat.fixed(this._scaleFactor, 1)} units/s`);
      }
      return;
    }

    if (event.type === "mouse_press") event.handled = true;

    if (event.type === "mouse_release") {
      this.eventValue = null;
      this._rotation1 = this._rotation2.multiply(this._rotation1).normalize();
      this._rotation2 = new VispyQuaternion();
      event.handled   = true;
    } else if (!this.timer.running) {
      this.timer.start();
    }

    if (event.type === "mouse_move") {
      if (event.pressEvent === null) return;
      if (event.buttons.length === 0) return;

      const modifiers = event.mouseEvent.modifiers;
      const pos1      = event.mouseEvent.pressEvent.pos;
      const pos2      = event.mouseEvent.pos;
      const [w, h]    = this.viewbox.size;

      if (event.buttons.includes(1) && modifiers.length === 0) {
        let dAz = -(pos2[0] - pos1[0]) / w;
        let dEl = +(pos2[1] - pos1[1]) / h;
        dAz *= -0.5 * Math.PI;
        dEl *= +0.5 * Math.PI;
        const qAz = VispyQuaternion.fromAxisAngle(dAz, 0, 1, 0);
        const qEl = VispyQuaternion.fromAxisAngle(dEl, 1, 0, 0);
        this._rotation2 = qEl.normalize().multiply(qAz).normalize();
        event.handled = true;
      } else if (event.buttons.includes(2) && modifiers.includes("control")) {
        if (this.eventValue === null) this.eventValue = this._fov;
        throw new VispyPyError("AttributeError", "'SceneMouseEvent' object has no attribute 'map_to_canvas'");
      }
    }

    this.updateFromMouse = true;
  }

  print(line) {
    if (this.viewbox) this.viewbox.canvas.print(line);
  }

  updateProjection(fx, fy) {
    super.updateProjection(fx, fy);

    const [angleRad, ax, ay, az] = this.rotation.axisAngle();
    const angle = angleRad * 180 / Math.PI;
    let tr = VispyMatrix.identity();
    tr = VispyMatrix.multiply(tr, VispyMatrix.rotate(-angle, [ax, ay, az]));
    tr = VispyMatrix.multiply(tr, VispyMatrix.scale(this.flipFactors.map((a) => 1.0 / a)));
    tr = VispyMatrix.multiply(tr, VispyMatrix.translate(this._center ? this._center.value : [0, 0, 0]));
    this.transform = tr;
  }

  dispose() {
    this.timer.stop();
  }
}

class VispyViewBox {
  static DEFAULT_SIZE = [10, 10];

  constructor(canvas, { pos = [0, 0], size = VispyViewBox.DEFAULT_SIZE, interactive = true, fill = false } = {}) {
    this.canvas      = canvas;
    this.pos         = [...pos];
    this.size        = [...size];
    this.interactive = interactive;
    this.fill        = fill;
    this.visible     = true;
    this.bgcolor     = null;
    this.cameraRef   = null;
    this.visuals     = [];
    this.cameras     = [];
  }

  get camera() {
    return this.cameraRef;
  }

  set camera(camera) {
    if (!this.cameras.includes(camera)) this.addCamera(camera);
    if (this.cameraRef !== null) this.cameraRef.viewboxUnset(this);
    this.cameraRef = camera;
    if (camera !== null) camera.viewboxSet(this);
    camera.viewChanged();
  }

  addCamera(camera) {
    this.cameras.push(camera);
    this.canvas.connectKeys(camera);
  }

  addVisual(visual) {
    this.visuals.push(visual);
  }

  sceneBounds(dim = null) {
    const bounds = [[Infinity, -Infinity], [Infinity, -Infinity], [Infinity, -Infinity]];
    for (const visual of this.visuals) {
      for (const axis of [0, 1, 2]) {
        if (dim !== null && dim !== axis) continue;
        const b = visual.bounds(axis);
        bounds[axis] = [Math.min(bounds[axis][0], b[0]), Math.max(bounds[axis][1], b[1])];
      }
    }
    for (const axis of [0, 1, 2]) if (!Number.isFinite(bounds[axis][0]) || !Number.isFinite(bounds[axis][1])) bounds[axis] = [-1, 1];
    return dim === null ? bounds : bounds[dim];
  }

  setSize(size) {
    if (size[0] === this.size[0] && size[1] === this.size[1]) return;
    this.size = [...size];
    if (this.cameraRef) this.cameraRef.viewboxResizeEvent();
  }

  setPos(pos) {
    this.pos = [...pos];
    this.canvas.update();
  }

  sceneChanged() {
    this.canvas.update();
  }

  mapToCanvas(pos) {
    return [pos[0] + this.pos[0], pos[1] + this.pos[1]];
  }

  mapVisualToCanvas(point) {
    const p = VispyMatrix.map(this.cameraRef.sceneTransform, point);
    return [(p[0] / p[3]) + this.pos[0], (p[1] / p[3]) + this.pos[1], p[2] / p[3]];
  }

  mouseEvent(event) {
    if (this.cameraRef) this.cameraRef.viewboxMouseEvent(event);
  }
}

class VispySceneMouseEvent {
  constructor(mouseEvent, view) {
    this.mouseEvent = mouseEvent;
    this.view       = view;
    this.type       = mouseEvent.type;
    this.handled    = false;
  }

  get pos() {
    return [this.mouseEvent.pos[0] - this.view.pos[0], this.mouseEvent.pos[1] - this.view.pos[1]];
  }

  get pressEvent() {
    if (this.mouseEvent.pressEvent === null) return null;
    return new VispySceneMouseEvent(this.mouseEvent.pressEvent, this.view);
  }

  get buttons() {
    return this.mouseEvent.buttons;
  }

  get delta() {
    return this.mouseEvent.delta;
  }
}

class VispySceneCanvas {
  static MOVE_THROTTLE_MS = 10;
  static BUTTONS          = { 0: 1, 1: 3, 2: 2 };

  constructor(element, { size = [800, 600], log = null, fullscreenTarget = null, embedded = true } = {}) {
    this.element          = element;
    this.size             = [...size];
    this.log              = log;
    this.fullscreenTarget = fullscreenTarget;
    this.embedded         = embedded;
    this.fullscreen       = false;
    this.closed           = false;
    this.views            = [];
    this.keyTargets       = [];
    this.handlers         = { draw: [], resize: [], key_press: [], key_release: [] };
    this.mouseData        = { pressEvent: null, lastEvent: null };
    this.mouseHandler     = null;
    this.lastMove         = -Infinity;
    this.heldButtons      = [];
    this.renderer         = null;
    this.frame            = null;
    this.shown            = false;
    this.dirty            = true;
    this.listeners        = [];
    this.connect("key_press", (event) => this.interactiveKeys(event), "SceneCanvas.keys_check");
  }

  connect(type, fn, label = "handler") {
    this.handlers[type].unshift({ fn, label });
  }

  connectKeys(camera) {
    if (this.keyTargets.includes(camera)) return;
    this.keyTargets.push(camera);
    const label = `${camera.constructor.name.replace(/^Vispy/, "")}.viewbox_key_event`;
    this.connect("key_press", (event) => camera.viewboxKeyEvent(event), label);
    this.connect("key_release", (event) => camera.viewboxKeyEvent(event), label);
  }

  addView(options) {
    const view = new VispyViewBox(this, options);
    this.views.push(view);
    return view;
  }

  print(line) {
    if (this.log) this.log([line]);
  }

  invoke(fn, event, label) {
    try {
      fn(event);
    } catch (error) {
      if (!(error instanceof VispyPyError)) throw error;
      this.print(`WARNING: ${error.traceback}`);
      this.print(`ERROR: Invoking ${label}`);
    }
  }

  emit(type, event, eventClass) {
    for (const { fn, label } of [...this.handlers[type]]) this.invoke(fn, event, `${label} for ${eventClass}`);
  }

  interactiveKeys(event) {
    if (event.key === null) return;
    const name = event.key.toLowerCase();
    if (name === "f11") this.toggleFullscreen();
  }

  toggleFullscreen() {
    this.fullscreen = !this.fullscreen;
    if (this.embedded || !this.fullscreenTarget) return;
    if (this.fullscreen && document.fullscreenElement !== this.fullscreenTarget) this.fullscreenTarget.requestFullscreen().catch((error) => this.print(`ERROR: fullscreen: ${error.message}`));
    if (!this.fullscreen && document.fullscreenElement === this.fullscreenTarget) document.exitFullscreen();
  }

  mouseEvent(type, fields) {
    return { type, pos: fields.pos, button: fields.button ?? null, buttons: fields.buttons || [], modifiers: fields.modifiers || [], delta: fields.delta || [0, 0], pressEvent: this.mouseData.pressEvent, lastEvent: this.mouseData.lastEvent, handled: false };
  }

  route(event) {
    const deliver = event.type === "mouse_press" || event.type === "mouse_wheel";
    let picked    = this.mouseHandler;
    if (picked === null && deliver) picked = this.pick(event.pos);
    if (picked === null) return;

    const sceneEvent = new VispySceneMouseEvent(event, picked);
    try {
      if (picked === this.mouseHandler) {
        if (event.type === "mouse_release") this.mouseHandler = null;
        picked.mouseEvent(sceneEvent);
      } else {
        picked.mouseEvent(sceneEvent);
        if (sceneEvent.handled && event.type === "mouse_press") this.mouseHandler = picked;
      }
    } catch (error) {
      if (!(error instanceof VispyPyError)) throw error;
      const escaped = new VispyPyError("TypeError", `SceneMouseEvent type '${event.type}' has no scale`);
      this.print(`WARNING: ${error.chain(escaped)}`);
      this.print("ERROR: Invoking SceneCanvas._process_mouse_event for MouseEvent");
      return;
    }
    event.handled = sceneEvent.handled;
  }

  pick(pos) {
    for (let i = this.views.length - 1; i >= 0; i -= 1) {
      const view = this.views[i];
      if (!view.interactive || !view.visible) continue;
      if (pos[0] >= view.pos[0] && pos[1] >= view.pos[1] && pos[0] < view.pos[0] + view.size[0] && pos[1] < view.pos[1] + view.size[1]) return view;
    }
    return null;
  }

  mousePress(fields) {
    const event = this.mouseEvent("mouse_press", fields);
    this.route(event);
    if (this.mouseData.pressEvent === null) this.mouseData.pressEvent = event;
    this.mouseData.lastEvent = event;
    return event;
  }

  mouseDoubleClick(fields) {
    const event = this.mouseEvent("mouse_double_click", fields);
    this.mouseData.lastEvent = event;
    return event;
  }

  mouseMove(fields, now = null) {
    if (now !== null) {
      if (now - this.lastMove < VispySceneCanvas.MOVE_THROTTLE_MS) return null;
      this.lastMove = now;
    }
    const event = this.mouseEvent("mouse_move", fields);
    if (this.mouseData.pressEvent !== null) event.button = this.mouseData.pressEvent.button;
    this.route(event);
    this.mouseData.lastEvent = event;
    return event;
  }

  mouseRelease(fields) {
    const event = this.mouseEvent("mouse_release", fields);
    this.route(event);
    if (this.mouseData.pressEvent && this.mouseData.pressEvent.button === event.button) this.mouseData.pressEvent = null;
    this.mouseData.lastEvent = event;
    return event;
  }

  mouseWheel(fields) {
    const event = { type: "mouse_wheel", pos: fields.pos, button: null, buttons: fields.buttons || [], modifiers: fields.modifiers || [], delta: fields.delta, pressEvent: null, lastEvent: null, handled: false };
    this.route(event);
    return event;
  }

  keyPress(fields) {
    const event = { type: "key_press", key: fields.key, text: fields.text || "", modifiers: fields.modifiers || [], handled: false };
    this.emit("key_press", event, "KeyEvent");
    return event;
  }

  keyRelease(fields) {
    const event = { type: "key_release", key: fields.key, text: fields.text || "", modifiers: fields.modifiers || [], handled: false };
    this.emit("key_release", event, "KeyEvent");
    return event;
  }

  setSize(size) {
    if (size[0] === this.size[0] && size[1] === this.size[1]) return;
    this.size = [...size];
    this.emit("resize", { size: this.size }, "ResizeEvent");
    this.layout();
    this.update();
  }

  layout() {
    for (const view of this.views) if (view.fill) view.setSize(this.size);
  }

  update() {
    this.dirty = true;
    if (!this.shown || this.frame !== null || typeof requestAnimationFrame !== "function") return;
    this.frame = requestAnimationFrame(() => this.draw());
  }

  show(shown) {
    this.shown = shown;
    if (shown && this.dirty) this.update();
  }

  draw() {
    this.frame = null;
    if (!this.shown) return;
    this.dirty = false;
    this.emit("draw", {}, "DrawEvent");
    if (this.renderer) this.renderer.render(this);
  }

  attachDom() {
    const el   = this.element;
    const on   = (target, type, fn, options) => {
      target.addEventListener(type, fn, options);
      this.listeners.push([target, type, fn, options]);
    };
    const move = (event) => this.domMove(event);
    const up   = (event) => this.domUp(event);

    on(el, "mousedown", (event) => this.domDown(event, move, up));
    on(el, "wheel", (event) => this.domWheel(event), { passive: false });
    on(el, "contextmenu", (event) => event.preventDefault());
    on(el, "keydown", (event) => this.domKey(event, "press"));
    on(el, "keyup", (event) => this.domKey(event, "release"));
    on(el, "mousemove", (event) => {
      if (this.heldButtons.length === 0) this.domMove(event);
    });
  }

  domPos(event) {
    const rect = this.element.getBoundingClientRect();
    return [event.clientX - rect.left, event.clientY - rect.top];
  }

  static modifiers(event) {
    const mods = [];
    if (event.shiftKey) mods.push("shift");
    if (event.ctrlKey) mods.push("control");
    if (event.altKey) mods.push("alt");
    if (event.metaKey) mods.push("meta");
    return mods;
  }

  static buttonList(mask) {
    const list = [];
    if (mask & 1) list.push(1);
    if (mask & 2) list.push(2);
    if (mask & 4) list.push(3);
    return list;
  }

  domDown(event, move, up) {
    const button = VispySceneCanvas.BUTTONS[event.button];
    if (button === undefined) return;
    event.preventDefault();
    this.element.focus({ preventScroll: true });

    if (this.heldButtons.length === 0) {
      window.addEventListener("mousemove", move, true);
      window.addEventListener("mouseup", up, true);
      this.dragListeners = [move, up];
    }
    if (!this.heldButtons.includes(button)) this.heldButtons.push(button);

    const fields = { pos: this.domPos(event), button, buttons: VispySceneCanvas.buttonList(event.buttons), modifiers: VispySceneCanvas.modifiers(event) };
    if (event.detail > 1 && event.detail % 2 === 0) this.mouseDoubleClick(fields);
    else this.mousePress(fields);
  }

  domMove(event) {
    this.mouseMove({ pos: this.domPos(event), buttons: VispySceneCanvas.buttonList(event.buttons), modifiers: VispySceneCanvas.modifiers(event) }, performance.now());
  }

  domUp(event) {
    const button = VispySceneCanvas.BUTTONS[event.button];
    if (button === undefined) return;
    this.heldButtons = this.heldButtons.filter((b) => b !== button);
    this.mouseRelease({ pos: this.domPos(event), button, buttons: VispySceneCanvas.buttonList(event.buttons), modifiers: VispySceneCanvas.modifiers(event) });
    if (this.heldButtons.length === 0 && this.dragListeners) {
      window.removeEventListener("mousemove", this.dragListeners[0], true);
      window.removeEventListener("mouseup", this.dragListeners[1], true);
      this.dragListeners = null;
    }
  }

  domWheel(event) {
    event.preventDefault();
    this.element.focus({ preventScroll: true });
    const angle = TomoVisInput.angleDelta(event);
    this.mouseWheel({ pos: this.domPos(event), delta: [angle.x / 120.0, angle.y / 120.0], buttons: VispySceneCanvas.buttonList(event.buttons), modifiers: VispySceneCanvas.modifiers(event) });
  }

  static keyName(event) {
    const named = { ArrowUp: "Up", ArrowDown: "Down", ArrowLeft: "Left", ArrowRight: "Right", " ": "Space", Backspace: "Backspace", Escape: "Escape", Enter: "Enter", Tab: "Tab", Delete: "Delete", Insert: "Insert", Home: "Home", End: "End", PageUp: "PageUp", PageDown: "PageDown", Shift: "Shift", Control: "Control", Alt: "Alt", Meta: "Meta" };
    if (named[event.key]) return named[event.key];
    if (/^F\d{1,2}$/.test(event.key)) return event.key;
    if (event.key.length === 1) {
      const code = event.key.toUpperCase().charCodeAt(0);
      if (code >= 32 && code <= 127) return event.key.toUpperCase();
    }
    return null;
  }

  domKey(event, kind) {
    if (event.key === "Tab") return;
    const key     = VispySceneCanvas.keyName(event);
    const chorded = event.ctrlKey || event.metaKey || event.altKey;
    if (!chorded && !(event.key === "F11" && this.embedded)) event.preventDefault();
    const fields = { key, text: event.key.length === 1 ? event.key : "", modifiers: VispySceneCanvas.modifiers(event) };
    if (kind === "press") this.keyPress(fields);
    else this.keyRelease(fields);
  }

  dispose() {
    if (this.frame !== null) cancelAnimationFrame(this.frame);
    this.frame = null;
    for (const [target, type, fn, options] of this.listeners) target.removeEventListener(type, fn, options);
    this.listeners = [];
    if (this.dragListeners) {
      window.removeEventListener("mousemove", this.dragListeners[0], true);
      window.removeEventListener("mouseup", this.dragListeners[1], true);
    }
    for (const camera of this.keyTargets) if (camera.dispose) camera.dispose();
    if (this.renderer) this.renderer.dispose();
  }
}

class VispyVolumeVisual {
  constructor(vol, shape, { clim = null, method = "mip", threshold = null, relativeStepSize = 0.8, cmap = "grays", gamma = 1.0, colormaps }) {
    this.shape            = [...shape];
    this.colormaps        = colormaps;
    this.gamma            = gamma;
    this._cmap            = colormaps.resolve(cmap);
    this.visible          = true;
    this.texture          = null;
    this.textureDirty     = true;
    this.setData(vol, clim);
    this.method           = method;
    this.relativeStepSize = relativeStepSize;
    this.threshold        = threshold !== null ? threshold : VispyVolumeVisual.mean(vol);
  }

  static mean(vol) {
    let sum = 0;
    for (let i = 0; i < vol.length; i += 1) sum += vol[i];
    return Math.fround(sum / vol.length);
  }

  static limits(vol) {
    let lo = Infinity;
    let hi = -Infinity;
    for (let i = 0; i < vol.length; i += 1) {
      if (vol[i] < lo) lo = vol[i];
      if (vol[i] > hi) hi = vol[i];
    }
    return [lo, hi];
  }

  setData(vol, clim) {
    const limits = clim === null ? VispyVolumeVisual.limits(vol) : clim;
    this.clim    = [Number(limits[0]), Number(limits[1])];
    this.scaled  = new Float32Array(vol.length);
    if (this.clim[0] !== this.clim[1]) {
      const lo    = Math.fround(this.clim[0]);
      const scale = Math.fround(1 / (this.clim[1] - this.clim[0]));
      for (let i = 0; i < vol.length; i += 1) this.scaled[i] = Math.fround(Math.fround(vol[i] - lo) * scale);
      this.climNormalized = [0, 1];
    } else {
      this.scaled.set(vol);
      this.climNormalized = [0, Infinity];
    }
    this.textureDirty = true;
  }

  get cmap() {
    return this._cmap;
  }

  set cmap(value) {
    this._cmap = this.colormaps.resolve(value);
  }

  get threshold() {
    return this._threshold;
  }

  set threshold(value) {
    this._threshold = Number(value);
  }

  get method() {
    return this._method;
  }

  set method(value) {
    if (!VispyVolumeRenderer.METHODS.includes(value)) throw new VispyPyError("ValueError", `Volume render method should be in ${JSON.stringify(VispyVolumeRenderer.METHODS)}, not '${value}'`);
    this._method = value;
  }

  bounds(axis) {
    return [0, this.shape[this.shape.length - 1 - axis]];
  }
}

class VispyVolumeRenderer {
  static METHODS = ["mip", "translucent", "iso", "additive"];
  static INDICES = [2, 6, 0, 4, 5, 6, 7, 2, 3, 0, 1, 5, 3, 7];

  static VERTEX = `#version 300 es
precision highp float;
in vec3 a_position;
uniform mat4 u_visual_to_clip;
uniform mat4 u_clip_to_visual;
out vec3 v_position;
out vec4 v_nearpos;
out vec4 v_farpos;
void main() {
    v_position = a_position;
    vec4 pos_in_cam = u_visual_to_clip * vec4(v_position, 1.0);
    pos_in_cam.z = -pos_in_cam.w;
    v_nearpos = u_clip_to_visual * pos_in_cam;
    pos_in_cam.z = pos_in_cam.w;
    v_farpos = u_clip_to_visual * pos_in_cam;
    gl_Position = u_visual_to_clip * vec4(v_position, 1.0);
}`;

  static SNIPPETS = {
    mip: {
      before: `
        float maxval = u_mip_cutoff;
        int maxi = -1;`,
      inside: `
                if ( val > maxval ) {
                    maxval = val;
                    maxi = iter;
                    if ( maxval >= clim.y ) {
                        iter = nsteps;
                    }
                }`,
      after: `
        if ( maxi > -1 ) {
            vec3 start_loc_refine = start_loc + step * (float(maxi) - 0.5);
            loc = start_loc_refine;
            vec3 max_loc_tex = start_loc_refine;
            vec3 small_step = step * 0.1;
            vec4 maxcolor = get_data(start_loc + step * float(maxi));
            for (int i=0; i<10; i++) {
                vec4 scolor = get_data(loc);
                float val = colorToVal(scolor);
                if ( val > maxval) {
                    maxval = val;
                    maxcolor = scolor;
                    max_loc_tex = start_loc_refine + (small_step * float(i));
                }
                loc += small_step;
            }
            frag_depth_point = max_loc_tex * u_shape;
            fragColor = applyColormap(maxcolor);
        } else {
            discard;
        }`,
    },
    translucent: {
      before: `
        vec4 integrated_color = vec4(0., 0., 0., 0.);`,
      inside: `
                color = applyColormap(color);
                float a1 = integrated_color.a;
                float a2 = color.a * (1.0 - a1);
                float alpha = max(a1 + a2, 0.001);
                integrated_color *= a1 / alpha;
                integrated_color += color * a2 / alpha;
                integrated_color.a = alpha;
                if( alpha > 0.99 ){
                    iter = nsteps;
                }`,
      after: `
        fragColor = integrated_color;`,
    },
    additive: {
      before: `
        vec4 integrated_color = vec4(0., 0., 0., 0.);`,
      inside: `
                color = applyColormap(color);
                integrated_color = 1.0 - (1.0 - integrated_color) * (1.0 - color);`,
      after: `
        fragColor = integrated_color;`,
    },
    iso: {
      before: `
        vec4 color3 = vec4(0.0);
        vec3 dstep = 1.5 / u_shape;
        fragColor = vec4(0.0);
        bool discard_fragment = true;`,
      inside: `
                if (val > u_threshold-0.2) {
                    vec3 iloc = loc - step;
                    for (int i=0; i<10; i++) {
                        color = get_data(iloc);
                        if (colorToVal(color) > u_threshold) {
                            color = calculateColor(color, iloc, dstep);
                            fragColor = applyColormap(color);
                            frag_depth_point = iloc * u_shape;
                            discard_fragment = false;
                            iter = nsteps;
                            break;
                        }
                        iloc += step * 0.1;
                    }
                }`,
      after: `
        if (discard_fragment)
            discard;`,
    },
  };

  static fragment(method, cmap) {
    const snippet = VispyVolumeRenderer.SNIPPETS[method];
    return `#version 300 es
precision highp float;
precision highp int;
precision highp sampler3D;
precision highp sampler2D;
uniform highp sampler3D u_volumetex;
uniform vec3 u_shape;
uniform vec2 clim;
uniform float gamma;
uniform float u_threshold;
uniform float u_relative_step_size;
uniform float u_mip_cutoff;
uniform int u_rgb_mode;
uniform mat4 u_visual_to_clip;
in vec3 v_position;
in vec4 v_nearpos;
in vec4 v_farpos;
out vec4 fragColor;

const vec4 u_ambient = vec4(0.2, 0.2, 0.2, 1.0);
const vec4 u_diffuse = vec4(0.8, 0.2, 0.2, 1.0);
const vec4 u_specular = vec4(1.0, 1.0, 1.0, 1.0);
const float u_shininess = 40.0;

vec3 view_ray;

${cmap.es300}

vec4 get_data(vec3 texcoord) {
    float v = texture(u_volumetex, texcoord).r;
    return vec4(v, v, v, 1.0);
}

float colorToVal(vec4 color) {
    if (u_rgb_mode == 1)
        return dot(color.rgb, vec3(0.2126, 0.7152, 0.0722)) * color.a;
    return color.r;
}

vec4 applyColormap(vec4 color) {
    color.rgb = clamp(color.rgb, min(clim.x, clim.y), max(clim.x, clim.y));
    color.rgb = (color.rgb - clim.x) / (clim.y - clim.x);
    color.rgb = pow(color.rgb, vec3(gamma));
    if (u_rgb_mode == 1) {
        return color;
    }
    return vispy_cmap(color.r);
}

vec4 calculateColor(vec4 betterColor, vec3 loc, vec3 step) {
    vec4 color1;
    vec4 color2;
    vec3 V = normalize(view_ray);
    vec3 N;
    color1 = get_data(loc+vec3(-step[0],0.0,0.0) );
    color2 = get_data(loc+vec3(step[0],0.0,0.0) );
    N[0] = colorToVal(color1) - colorToVal(color2);
    betterColor = max(max(color1, color2),betterColor);
    color1 = get_data(loc+vec3(0.0,-step[1],0.0) );
    color2 = get_data(loc+vec3(0.0,step[1],0.0) );
    N[1] = colorToVal(color1) - colorToVal(color2);
    betterColor = max(max(color1, color2),betterColor);
    color1 = get_data(loc+vec3(0.0,0.0,-step[2]) );
    color2 = get_data(loc+vec3(0.0,0.0,step[2]) );
    N[2] = colorToVal(color1) - colorToVal(color2);
    betterColor = max(max(color1, color2),betterColor);
    float gm = length(N);
    N = normalize(N);
    float Nselect = float(dot(N,V) > 0.0);
    N = (2.0*Nselect - 1.0) * N;
    color1 = betterColor;
    color2 = color1;
    vec4 ambient_color = vec4(0.0, 0.0, 0.0, 0.0);
    vec4 diffuse_color = vec4(0.0, 0.0, 0.0, 0.0);
    vec4 specular_color = vec4(0.0, 0.0, 0.0, 0.0);
    vec4 final_color;
    int nlights = 1;
    for (int i=0; i<nlights; i++) {
        vec3 L = normalize(view_ray);
        float lightEnabled = float( length(L) > 0.0 );
        L = normalize(L+(1.0-lightEnabled));
        float lambertTerm = clamp( dot(N,L), 0.0, 1.0 );
        vec3 H = normalize(L+V);
        float specularTerm = pow( max(dot(H,N),0.0), u_shininess);
        float mask1 = lightEnabled;
        ambient_color +=  mask1 * u_ambient;
        diffuse_color +=  mask1 * lambertTerm;
        specular_color += mask1 * specularTerm * u_specular;
    }
    final_color = color2 * ( ambient_color + diffuse_color) + specular_color;
    final_color.a = color2.a;
    return final_color;
}

void main() {
    vec3 farpos = v_farpos.xyz / v_farpos.w;
    vec3 nearpos = v_nearpos.xyz / v_nearpos.w;
    view_ray = normalize(farpos.xyz - nearpos.xyz);
    vec3 frag_depth_point;

    float distance = dot(nearpos-v_position, view_ray);
    distance = max(distance, min((-0.5 - v_position.x) / view_ray.x,
                            (u_shape.x - 0.5 - v_position.x) / view_ray.x));
    distance = max(distance, min((-0.5 - v_position.y) / view_ray.y,
                            (u_shape.y - 0.5 - v_position.y) / view_ray.y));
    distance = max(distance, min((-0.5 - v_position.z) / view_ray.z,
                            (u_shape.z - 0.5 - v_position.z) / view_ray.z));
    vec3 front = v_position + view_ray * distance;
    int nsteps = int(-distance / u_relative_step_size + 0.5);
    float f_nsteps = float(nsteps);
    if( nsteps < 1 )
        discard;
    vec3 step = ((v_position - front) / u_shape) / f_nsteps;
    vec3 start_loc = (front + 0.5) / u_shape;
    frag_depth_point = front;
${snippet.before}

    vec3 loc = start_loc;
    int iter = 0;
    bool texture_sampled = false;
    while (iter < nsteps) {
        for (iter=iter; iter<nsteps; iter++) {
            {
                vec4 color = get_data(loc);
                float val = colorToVal(color);
                texture_sampled = true;
${snippet.inside}
            }
            loc += step;
        }
    }

    if (!texture_sampled)
        discard;
${snippet.after}

    vec4 frag_depth_vector = vec4(frag_depth_point, 1.0);
    vec4 iproj = u_visual_to_clip * frag_depth_vector;
    iproj.z /= iproj.w;
    gl_FragDepth = (iproj.z+1.0)/2.0;
}`;
  }

  constructor(element) {
    this.element  = element;
    this.gl       = element.getContext("webgl2", { alpha: false, antialias: false, depth: true, preserveDrawingBuffer: true, premultipliedAlpha: false });
    if (!this.gl) throw new Error("WebGL2 is not available for the 3D view");
    this.floatLinear = Boolean(this.gl.getExtension("OES_texture_float_linear"));
    this.programs = new Map();
    this.luts     = new Map();
    this.uploaded = new Set();
    this.gizmos   = new Set();
    this.failures = new Map();
    this.lost     = false;
    this.disposed = false;
    this.canvas   = null;
    this.setupGeometry();

    element.addEventListener("webglcontextlost", (event) => {
      event.preventDefault();
      this.lost = true;
    });
    element.addEventListener("webglcontextrestored", () => this.restore());
  }

  restore() {
    if (this.disposed) return;
    this.floatLinear = Boolean(this.gl.getExtension("OES_texture_float_linear"));
    this.programs.clear();
    this.luts.clear();
    for (const visual of this.uploaded) {
      visual.texture      = null;
      visual.textureDirty = true;
    }
    for (const gizmo of this.gizmos) gizmo.state = null;
    this.uploaded.clear();
    this.setupGeometry();
    this.lost = false;
    if (this.canvas) this.canvas.update();
  }

  compile(type, source) {
    const gl     = this.gl;
    const shader = gl.createShader(type);
    gl.shaderSource(shader, source);
    gl.compileShader(shader);
    if (!gl.getShaderParameter(shader, gl.COMPILE_STATUS)) throw new Error(`3D shader compile failed: ${gl.getShaderInfoLog(shader)}`);
    return shader;
  }

  link(vertex, fragment, attributes = []) {
    const gl      = this.gl;
    const program = gl.createProgram();
    gl.attachShader(program, this.compile(gl.VERTEX_SHADER, vertex));
    gl.attachShader(program, this.compile(gl.FRAGMENT_SHADER, fragment));
    attributes.forEach((name, index) => gl.bindAttribLocation(program, index, name));
    gl.linkProgram(program);
    if (!gl.getProgramParameter(program, gl.LINK_STATUS)) throw new Error(`3D shader link failed: ${gl.getProgramInfoLog(program)}`);
    return program;
  }

  setupGeometry() {
    const gl = this.gl;
    this.vao = gl.createVertexArray();
    this.positionBuffer = gl.createBuffer();
    this.indexBuffer    = gl.createBuffer();
    gl.bindVertexArray(this.vao);
    gl.bindBuffer(gl.ARRAY_BUFFER, this.positionBuffer);
    gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER, this.indexBuffer);
    gl.bufferData(gl.ELEMENT_ARRAY_BUFFER, new Uint16Array(VispyVolumeRenderer.INDICES), gl.STATIC_DRAW);
    gl.enableVertexAttribArray(0);
    gl.vertexAttribPointer(0, 3, gl.FLOAT, false, 0, 0);
    gl.bindVertexArray(null);
  }

  program(method, cmap) {
    const key = `${method}|${cmap.kind}|${cmap.name}`;
    if (!this.programs.has(key)) {
      const gl      = this.gl;
      const program = this.link(VispyVolumeRenderer.VERTEX, VispyVolumeRenderer.fragment(method, cmap), ["a_position"]);
      const names = ["u_volumetex", "texture2D_LUT", "u_shape", "clim", "gamma", "u_threshold", "u_relative_step_size", "u_mip_cutoff", "u_rgb_mode", "u_visual_to_clip", "u_clip_to_visual"];
      const uniforms = {};
      for (const name of names) uniforms[name] = gl.getUniformLocation(program, name);
      this.programs.set(key, { program, uniforms });
    }
    return this.programs.get(key);
  }

  lut(cmap) {
    if (!this.luts.has(cmap)) {
      const gl      = this.gl;
      const texture = gl.createTexture();
      const n       = cmap.lut.length / 4;
      gl.bindTexture(gl.TEXTURE_2D, texture);
      gl.pixelStorei(gl.UNPACK_ALIGNMENT, 1);
      gl.texImage2D(gl.TEXTURE_2D, 0, this.floatLinear ? gl.RGBA32F : gl.RGBA16F, 1, n, 0, gl.RGBA, gl.FLOAT, cmap.lut);
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR);
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR);
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
      this.luts.set(cmap, texture);
    }
    return this.luts.get(cmap);
  }

  upload(visual) {
    const gl = this.gl;
    if (visual.texture && !visual.textureDirty) return visual.texture;
    if (visual.texture) gl.deleteTexture(visual.texture);
    const [nz, ny, nx] = visual.shape;
    const limit = gl.getParameter(gl.MAX_3D_TEXTURE_SIZE);
    if (Math.max(nx, ny, nz) > limit) throw new VispyPyError("RuntimeError", `Volume of shape (${nz}, ${ny}, ${nx}) exceeds the GL 3D texture size limit ${limit}`);
    const texture = gl.createTexture();
    gl.bindTexture(gl.TEXTURE_3D, texture);
    gl.pixelStorei(gl.UNPACK_ALIGNMENT, 1);
    gl.texImage3D(gl.TEXTURE_3D, 0, this.floatLinear ? gl.R32F : gl.R16F, nx, ny, nz, 0, gl.RED, gl.FLOAT, visual.scaled);
    gl.texParameteri(gl.TEXTURE_3D, gl.TEXTURE_MIN_FILTER, gl.LINEAR);
    gl.texParameteri(gl.TEXTURE_3D, gl.TEXTURE_MAG_FILTER, gl.LINEAR);
    gl.texParameteri(gl.TEXTURE_3D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
    gl.texParameteri(gl.TEXTURE_3D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
    gl.texParameteri(gl.TEXTURE_3D, gl.TEXTURE_WRAP_R, gl.CLAMP_TO_EDGE);
    visual.texture      = texture;
    visual.textureDirty = false;
    this.uploaded.add(visual);
    return texture;
  }

  cube(visual) {
    const [nz, ny, nx] = visual.shape;
    const [x0, x1] = [-0.5, nx - 0.5];
    const [y0, y1] = [-0.5, ny - 0.5];
    const [z0, z1] = [-0.5, nz - 0.5];
    return new Float32Array([x0, y0, z0, x1, y0, z0, x0, y1, z0, x1, y1, z0, x0, y0, z1, x1, y0, z1, x0, y1, z1, x1, y1, z1]);
  }

  resize(canvas) {
    const ratio  = window.devicePixelRatio || 1;
    const width  = Math.max(1, Math.round(canvas.size[0] * ratio));
    const height = Math.max(1, Math.round(canvas.size[1] * ratio));
    if (this.element.width !== width) this.element.width = width;
    if (this.element.height !== height) this.element.height = height;
    return ratio;
  }

  render(canvas) {
    this.canvas = canvas;
    if (this.lost) return;
    const gl    = this.gl;
    const ratio = this.resize(canvas);

    gl.viewport(0, 0, this.element.width, this.element.height);
    gl.disable(gl.SCISSOR_TEST);
    gl.clearColor(0, 0, 0, 1);
    gl.depthMask(true);
    gl.clearDepth(1);
    gl.clear(gl.COLOR_BUFFER_BIT | gl.DEPTH_BUFFER_BIT);

    for (const view of canvas.views) {
      if (!view.visible || !view.camera) continue;
      const x = Math.round(view.pos[0] * ratio);
      const y = Math.round((canvas.size[1] - view.pos[1] - view.size[1]) * ratio);
      const w = Math.round(view.size[0] * ratio);
      const h = Math.round(view.size[1] * ratio);
      gl.viewport(x, y, w, h);
      gl.enable(gl.SCISSOR_TEST);
      gl.scissor(x, y, w, h);
      for (const visual of view.visuals) {
        if (!visual.visible) continue;
        try {
          if (visual instanceof VispyVolumeVisual) this.drawVolume(visual, view.camera);
          else visual.draw(this, view.camera);
        } catch (error) {
          if (!(error instanceof VispyPyError)) throw error;
          this.failed(canvas, visual, error);
        }
      }
      gl.disable(gl.SCISSOR_TEST);
    }
  }

  failed(canvas, visual, error) {
    const count = (this.failures.get(visual) || 0) + 1;
    this.failures.set(visual, count);
    const name = visual instanceof VispyVolumeVisual ? "Volume" : "XYZAxis";
    if (count === 1) canvas.print(`ERROR: Drawing node ${name}: ${error.line}`);
    else if (VispyPyError.reminder(count)) canvas.print(`ERROR: Drawing node ${name} repeat ${count}`);
  }

  translucentState() {
    const gl = this.gl;
    gl.enable(gl.DEPTH_TEST);
    gl.depthFunc(gl.LESS);
    gl.disable(gl.CULL_FACE);
    gl.enable(gl.BLEND);
    gl.blendEquation(gl.FUNC_ADD);
    gl.blendFuncSeparate(gl.SRC_ALPHA, gl.ONE_MINUS_SRC_ALPHA, gl.ZERO, gl.ONE);
  }

  drawVolume(visual, camera) {
    const gl = this.gl;
    const { program, uniforms } = this.program(visual.method, visual.cmap);

    this.translucentState();
    gl.useProgram(program);
    gl.activeTexture(gl.TEXTURE0);
    gl.bindTexture(gl.TEXTURE_3D, this.upload(visual));
    gl.uniform1i(uniforms.u_volumetex, 0);
    if (visual.cmap.lut) {
      gl.activeTexture(gl.TEXTURE1);
      gl.bindTexture(gl.TEXTURE_2D, this.lut(visual.cmap));
      gl.uniform1i(uniforms.texture2D_LUT, 1);
    }

    const [nz, ny, nx] = visual.shape;
    gl.uniform3f(uniforms.u_shape, nx, ny, nz);
    gl.uniform2f(uniforms.clim, visual.climNormalized[0], visual.climNormalized[1]);
    gl.uniform1f(uniforms.gamma, visual.gamma);
    gl.uniform1f(uniforms.u_threshold, visual.threshold);
    gl.uniform1f(uniforms.u_relative_step_size, visual.relativeStepSize);
    gl.uniform1f(uniforms.u_mip_cutoff, -3.4028234663852886e38);
    gl.uniform1i(uniforms.u_rgb_mode, 0);
    gl.uniformMatrix4fv(uniforms.u_visual_to_clip, false, VispyMatrix.float32(camera.clipTransform));
    gl.uniformMatrix4fv(uniforms.u_clip_to_visual, false, VispyMatrix.float32(VispyMatrix.inverse(camera.clipTransform)));

    gl.bindVertexArray(this.vao);
    gl.bindBuffer(gl.ARRAY_BUFFER, this.positionBuffer);
    gl.bufferData(gl.ARRAY_BUFFER, this.cube(visual), gl.DYNAMIC_DRAW);
    gl.drawElements(gl.TRIANGLE_STRIP, VispyVolumeRenderer.INDICES.length, gl.UNSIGNED_SHORT, 0);
    gl.bindVertexArray(null);
  }

  release(visual) {
    if (visual.texture) this.gl.deleteTexture(visual.texture);
    visual.texture = null;
  }

  dispose() {
    const gl = this.gl;
    this.disposed = true;
    for (const visual of this.uploaded) this.release(visual);
    for (const { program } of this.programs.values()) gl.deleteProgram(program);
    for (const texture of this.luts.values()) gl.deleteTexture(texture);
    this.programs.clear();
    this.luts.clear();
    const lose = gl.getExtension("WEBGL_lose_context");
    if (lose) lose.loseContext();
  }
}

class VispyAxisGizmo {
  static POSITIONS = new Float32Array([0, 0, 0, 1, 0, 0, 0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0, 1]);
  static COLORS    = new Float32Array([1, 0, 0, 1, 1, 0, 0, 1, 0, 1, 0, 1, 0, 1, 0, 1, 0, 0, 1, 1, 0, 0, 1, 1]);

  static VERTEX = `#version 300 es
precision highp float;
in vec3 a_position;
in vec4 a_color;
uniform mat4 u_visual_to_clip;
out vec4 v_color;
void main() {
    gl_Position = u_visual_to_clip * vec4(a_position, 1.0);
    v_color = a_color;
}`;

  static FRAGMENT = `#version 300 es
precision highp float;
in vec4 v_color;
out vec4 fragColor;
void main() {
    fragColor = v_color;
}`;

  constructor() {
    this.visible = true;
    this.state   = null;
  }

  bounds(axis) {
    return [0, 1];
  }

  setup(renderer) {
    const gl      = renderer.gl;
    const program = renderer.link(VispyAxisGizmo.VERTEX, VispyAxisGizmo.FRAGMENT, ["a_position", "a_color"]);
    const vao     = gl.createVertexArray();
    gl.bindVertexArray(vao);
    const positions = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, positions);
    gl.bufferData(gl.ARRAY_BUFFER, VispyAxisGizmo.POSITIONS, gl.STATIC_DRAW);
    const position = gl.getAttribLocation(program, "a_position");
    gl.enableVertexAttribArray(position);
    gl.vertexAttribPointer(position, 3, gl.FLOAT, false, 0, 0);
    const colors = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, colors);
    gl.bufferData(gl.ARRAY_BUFFER, VispyAxisGizmo.COLORS, gl.STATIC_DRAW);
    const color = gl.getAttribLocation(program, "a_color");
    gl.enableVertexAttribArray(color);
    gl.vertexAttribPointer(color, 4, gl.FLOAT, false, 0, 0);
    gl.bindVertexArray(null);
    this.state = { program, vao, matrix: gl.getUniformLocation(program, "u_visual_to_clip") };
    renderer.gizmos.add(this);
  }

  draw(renderer, camera) {
    const gl = renderer.gl;
    if (!this.state) this.setup(renderer);
    renderer.translucentState();
    gl.lineWidth(1);
    gl.useProgram(this.state.program);
    gl.uniformMatrix4fv(this.state.matrix, false, VispyMatrix.float32(camera.clipTransform));
    gl.bindVertexArray(this.state.vao);
    gl.drawArrays(gl.LINES, 0, 6);
    gl.bindVertexArray(null);
  }
}

window.VispyPyError         = VispyPyError;
window.VispyPyFormat        = VispyPyFormat;
window.VispyMatrix          = VispyMatrix;
window.VispyQuaternion      = VispyQuaternion;
window.VispyCycle           = VispyCycle;
window.VispyColormap        = VispyColormap;
window.VispyColormaps       = VispyColormaps;
window.VispyCameraBase      = VispyCameraBase;
window.VispyRotationCamera  = VispyRotationCamera;
window.VispyTurntableCamera = VispyTurntableCamera;
window.VispyArcballCamera   = VispyArcballCamera;
window.VispyTimer           = VispyTimer;
window.VispyFlyCamera       = VispyFlyCamera;
window.VispyViewBox         = VispyViewBox;
window.VispySceneMouseEvent = VispySceneMouseEvent;
window.VispySceneCanvas     = VispySceneCanvas;
window.VispyVolumeVisual    = VispyVolumeVisual;
window.VispyVolumeRenderer  = VispyVolumeRenderer;
window.VispyAxisGizmo       = VispyAxisGizmo;
