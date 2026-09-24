"use strict";

class TomogramVolume {
  static VIRIDIS = [[68, 1, 84], [59, 82, 139], [33, 145, 140], [94, 201, 98], [253, 231, 37]];
  static COOLWARM = [[59, 76, 192], [144, 178, 254], [221, 221, 221], [246, 153, 122], [180, 4, 38]];
  static MAX_DIM = 192;

  static VERTEX_SRC = `#version 300 es
    const vec2 corners[3] = vec2[3](vec2(-1.0, -1.0), vec2(3.0, -1.0), vec2(-1.0, 3.0));
    out vec2 vNdc;
    void main() {
      vNdc = corners[gl_VertexID];
      gl_Position = vec4(corners[gl_VertexID], 0.0, 1.0);
    }`;

  static FRAGMENT_SRC = `#version 300 es
    precision highp float;
    precision highp sampler3D;

    in vec2 vNdc;
    out vec4 outColor;

    uniform sampler3D uVolume;
    uniform sampler2D uLut;
    uniform vec3 uEye;
    uniform vec3 uRight;
    uniform vec3 uUp;
    uniform vec3 uForward;
    uniform vec3 uHalf;
    uniform vec3 uClipMin;
    uniform vec3 uClipMax;
    uniform float uAspect;
    uniform float uTfLo;
    uniform float uTfHi;
    uniform float uOpacity;
    uniform int uSteps;

    vec2 boxHit(vec3 origin, vec3 dir, vec3 lo, vec3 hi) {
      vec3 inv = 1.0 / dir;
      vec3 t0 = (lo - origin) * inv;
      vec3 t1 = (hi - origin) * inv;
      vec3 tmin = min(t0, t1);
      vec3 tmax = max(t0, t1);
      return vec2(max(max(tmin.x, tmin.y), tmin.z), min(min(tmax.x, tmax.y), tmax.z));
    }

    void main() {
      vec3 dir = normalize(uForward + vNdc.x * uAspect * uRight + vNdc.y * uUp);

      vec3 lo = -uHalf + 2.0 * uHalf * uClipMin;
      vec3 hi = -uHalf + 2.0 * uHalf * uClipMax;

      vec2 hit = boxHit(uEye, dir, lo, hi);
      if (hit.y <= max(hit.x, 0.0)) { outColor = vec4(0.0); return; }

      float tNear = max(hit.x, 0.0);
      float span = hit.y - tNear;
      float dt = span / float(uSteps);

      vec3 color = vec3(0.0);
      float alpha = 0.0;

      for (int i = 0; i < 768; i++) {
        if (i >= uSteps) break;
        vec3 p = uEye + dir * (tNear + (float(i) + 0.5) * dt);
        vec3 tc = (p + uHalf) / (2.0 * uHalf);
        float v = texture(uVolume, tc).r;

        float a = smoothstep(uTfLo, uTfHi, v) * uOpacity * dt * 90.0;
        a = clamp(a, 0.0, 1.0);
        vec3 c = texture(uLut, vec2(v, 0.5)).rgb;

        color += (1.0 - alpha) * a * c;
        alpha += (1.0 - alpha) * a;
        if (alpha > 0.97) break;
      }

      outColor = vec4(color, alpha);
    }`;

  constructor(refs, host) {
    this.host = host;
    this.loEl = refs.lo;
    this.hiEl = refs.hi;
    this.opacityEl = refs.opacity;
    this.stepsEl = refs.steps;
    this.clipAxisEl = refs.clipAxis;
    this.clipPosEl = refs.clipPos;
    this.atEl = refs.at;
    this.canvas = refs.canvas;

    this.source = "full";
    this.volume = null;
    this.volumeKey = null;
    this.token = 0;
    this.failed = false;

    this.yaw = 0.7;
    this.pitch = 0.55;
    this.zoom = 1.0;
    this.dragging = null;

    this.gl = null;
    this.program = null;
    this.uniforms = null;
    this.texture = null;
    this.lut = null;
    this.lutDiverging = null;

    [this.loEl, this.hiEl, this.opacityEl, this.clipPosEl].forEach((el) => {
      el.addEventListener("input", () => this._draw());
    });
    this.stepsEl.addEventListener("change", () => this._draw());
    this.clipAxisEl.addEventListener("change", () => this._draw());

    this.canvas.addEventListener("mousedown", (ev) => { this.dragging = { x: ev.clientX, y: ev.clientY }; });
    window.addEventListener("mousemove", (ev) => this._onDrag(ev));
    window.addEventListener("mouseup", () => { this.dragging = null; });
    this.canvas.addEventListener("wheel", (ev) => this._onWheel(ev), { passive: false });
    this.canvas.addEventListener("dblclick", () => this._resetView());
  }

  get available() {
    return !this.failed;
  }

  configure(meta) {
    this.source = this.host.srcFor();
    this.volume = null;
    this.volumeKey = null;
    this._resetView(false);
  }

  render() {
    if (!this._ensureGl()) return;
    this.source = this.host.srcFor();
    if (!this.volume || this.volumeKey !== `${this.host.selectedId}|${this.source}`) this._fetch();
    else this._draw();
  }

  _ensureGl() {
    if (this.gl) return true;
    if (this.failed) return false;

    const gl = this.canvas.getContext("webgl2", { alpha: true, antialias: false });
    if (!gl) {
      this.failed = true;
      this.atEl.textContent = "WebGL2 is not available in this browser; the volume view is disabled.";
      return false;
    }

    const compile = (type, src) => {
      const shader = gl.createShader(type);
      gl.shaderSource(shader, src);
      gl.compileShader(shader);
      if (!gl.getShaderParameter(shader, gl.COMPILE_STATUS)) throw new Error(gl.getShaderInfoLog(shader));
      return shader;
    };

    try {
      const program = gl.createProgram();
      gl.attachShader(program, compile(gl.VERTEX_SHADER, TomogramVolume.VERTEX_SRC));
      gl.attachShader(program, compile(gl.FRAGMENT_SHADER, TomogramVolume.FRAGMENT_SRC));
      gl.linkProgram(program);
      if (!gl.getProgramParameter(program, gl.LINK_STATUS)) throw new Error(gl.getProgramInfoLog(program));

      this.gl = gl;
      this.program = program;
      this.uniforms = {};
      ["uVolume", "uLut", "uEye", "uRight", "uUp", "uForward", "uHalf", "uClipMin", "uClipMax", "uAspect", "uTfLo", "uTfHi", "uOpacity", "uSteps"].forEach((name) => {
        this.uniforms[name] = gl.getUniformLocation(program, name);
      });

      this.lut = this._makeLut(gl, TomogramVolume.VIRIDIS);
      this.lutDiverging = this._makeLut(gl, TomogramVolume.COOLWARM);
      gl.bindVertexArray(gl.createVertexArray());
    } catch (error) {
      this.failed = true;
      this.atEl.textContent = `Volume renderer initialisation failed: ${error.message}`;
      return false;
    }

    return true;
  }

  _makeLut(gl, stops) {
    const data = new Uint8Array(256 * 3);
    for (let i = 0; i < 256; i++) {
      const x = (i / 255) * (stops.length - 1);
      const k = Math.min(stops.length - 2, Math.floor(x));
      const f = x - k;
      for (let c = 0; c < 3; c++) data[i * 3 + c] = Math.round(stops[k][c] + (stops[k + 1][c] - stops[k][c]) * f);
    }

    const texture = gl.createTexture();
    gl.bindTexture(gl.TEXTURE_2D, texture);
    gl.pixelStorei(gl.UNPACK_ALIGNMENT, 1);
    gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGB8, 256, 1, 0, gl.RGB, gl.UNSIGNED_BYTE, data);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
    return texture;
  }

  async _fetch() {
    this.token += 1;
    const token = this.token;
    this.atEl.textContent = "Streaming volume…";

    try {
      const res = await fetch(`/api/cubes/volume?id=${encodeURIComponent(this.host.selectedId)}&source=${this.source}&max=${TomogramVolume.MAX_DIM}`);
      if (!res.ok || token !== this.token) return;

      const buffer = await res.arrayBuffer();
      if (token !== this.token) return;

      const header = new Float32Array(buffer, 0, 8);
      this.volume = {
        dims      : [header[0], header[1], header[2]].map((v) => Math.round(v)),
        diverging : header[3] > 0.5,
        vmin      : header[4],
        vmax      : header[5],
        voxels    : new Uint8Array(buffer, 32),
      };
      this.volumeKey = `${this.host.selectedId}|${this.source}`;
      this._uploadVolume();
      this._draw();
    } catch (error) {
      this.atEl.textContent = "Volume fetch failed.";
    }
  }

  _uploadVolume() {
    const gl = this.gl;
    const [nElev, nAz, nRg] = this.volume.dims;

    if (this.texture) gl.deleteTexture(this.texture);
    this.texture = gl.createTexture();
    gl.bindTexture(gl.TEXTURE_3D, this.texture);
    gl.pixelStorei(gl.UNPACK_ALIGNMENT, 1);
    gl.texImage3D(gl.TEXTURE_3D, 0, gl.R8, nRg, nAz, nElev, 0, gl.RED, gl.UNSIGNED_BYTE, this.volume.voxels);
    gl.texParameteri(gl.TEXTURE_3D, gl.TEXTURE_MIN_FILTER, gl.LINEAR);
    gl.texParameteri(gl.TEXTURE_3D, gl.TEXTURE_MAG_FILTER, gl.LINEAR);
    gl.texParameteri(gl.TEXTURE_3D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
    gl.texParameteri(gl.TEXTURE_3D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
    gl.texParameteri(gl.TEXTURE_3D, gl.TEXTURE_WRAP_R, gl.CLAMP_TO_EDGE);
  }

  _onDrag(ev) {
    if (!this.dragging) return;
    this.yaw += (ev.clientX - this.dragging.x) * 0.008;
    this.pitch = Math.min(1.45, Math.max(-1.45, this.pitch + (ev.clientY - this.dragging.y) * 0.006));
    this.dragging = { x: ev.clientX, y: ev.clientY };
    this._draw();
  }

  _onWheel(ev) {
    ev.preventDefault();
    this.zoom = Math.min(6, Math.max(0.35, this.zoom * (ev.deltaY > 0 ? 0.92 : 1.09)));
    this._draw();
  }

  _resetView(draw = true) {
    this.yaw = 0.7;
    this.pitch = 0.55;
    this.zoom = 1.0;
    if (draw) this._draw();
  }

  _clip() {
    const axis = this.clipAxisEl.value;
    const frac = Number(this.clipPosEl.value) / 100;
    const min = [0, 0, 0];
    const max = [1, 1, 1];

    if (axis === "rg") max[0] = frac;
    else if (axis === "az") max[1] = frac;
    else if (axis === "elev") max[2] = frac;

    return { min, max };
  }

  _draw() {
    if (!this.gl || !this.volume || this.host.view !== "volume") return;

    const gl = this.gl;
    const stage = this.canvas.parentElement;
    const dpr = Math.min(window.devicePixelRatio || 1, 1.5);
    const w = Math.max(320, stage.clientWidth);
    const h = Math.max(320, Math.round(window.innerHeight * 0.62));

    if (this.canvas.width !== Math.round(w * dpr) || this.canvas.height !== Math.round(h * dpr)) {
      this.canvas.width = Math.round(w * dpr);
      this.canvas.height = Math.round(h * dpr);
      this.canvas.style.height = `${h}px`;
    }

    const [nElev, nAz, nRg] = this.volume.dims;
    const longest = Math.max(nElev, nAz, nRg);
    const half = [nRg / longest * 0.5, nAz / longest * 0.5, nElev / longest * 0.5];

    const distance = 1.9 / this.zoom;
    const cosP = Math.cos(this.pitch);
    const eye = [
      distance * cosP * Math.sin(this.yaw),
      distance * cosP * Math.cos(this.yaw),
      distance * Math.sin(this.pitch),
    ];

    const forward = eye.map((v) => -v / distance);
    const worldUp = [0, 0, 1];
    const right = [
      forward[1] * worldUp[2] - forward[2] * worldUp[1],
      forward[2] * worldUp[0] - forward[0] * worldUp[2],
      forward[0] * worldUp[1] - forward[1] * worldUp[0],
    ];
    const rLen = Math.hypot(...right) || 1;
    right.forEach((v, i) => { right[i] = v / rLen; });
    const up = [
      right[1] * forward[2] - right[2] * forward[1],
      right[2] * forward[0] - right[0] * forward[2],
      right[0] * forward[1] - right[1] * forward[0],
    ];

    const clip = this._clip();
    const fov = Math.tan((38 * Math.PI) / 360);
    const steps = Number(this.stepsEl.value) || 256;

    gl.viewport(0, 0, this.canvas.width, this.canvas.height);
    gl.clearColor(0.055, 0.07, 0.086, 1.0);
    gl.clear(gl.COLOR_BUFFER_BIT);
    gl.useProgram(this.program);

    gl.activeTexture(gl.TEXTURE0);
    gl.bindTexture(gl.TEXTURE_3D, this.texture);
    gl.uniform1i(this.uniforms.uVolume, 0);

    gl.activeTexture(gl.TEXTURE1);
    gl.bindTexture(gl.TEXTURE_2D, this.volume.diverging ? this.lutDiverging : this.lut);
    gl.uniform1i(this.uniforms.uLut, 1);

    gl.uniform3fv(this.uniforms.uEye, eye);
    gl.uniform3fv(this.uniforms.uRight, right.map((v) => v * fov));
    gl.uniform3fv(this.uniforms.uUp, up.map((v) => v * fov));
    gl.uniform3fv(this.uniforms.uForward, forward);
    gl.uniform3fv(this.uniforms.uHalf, half);
    gl.uniform3fv(this.uniforms.uClipMin, clip.min);
    gl.uniform3fv(this.uniforms.uClipMax, clip.max);
    gl.uniform1f(this.uniforms.uAspect, this.canvas.width / this.canvas.height);
    gl.uniform1f(this.uniforms.uTfLo, Number(this.loEl.value) / 100);
    gl.uniform1f(this.uniforms.uTfHi, Math.max(Number(this.loEl.value) / 100 + 0.01, Number(this.hiEl.value) / 100));
    gl.uniform1f(this.uniforms.uOpacity, Number(this.opacityEl.value) / 100);
    gl.uniform1i(this.uniforms.uSteps, Math.min(768, steps));

    gl.drawArrays(gl.TRIANGLES, 0, 3);

    const clipNote = this.clipAxisEl.value === "off" ? "" : ` · clip ${this.clipAxisEl.value} @ ${this.clipPosEl.value}%`;
    const range = `${this.host._fmt(this.volume.vmin)} … ${this.host._fmt(this.volume.vmax)}`;
    this.atEl.textContent = `${nRg}×${nAz}×${nElev} voxels · intensity ${range}${clipNote} · drag to orbit · wheel to zoom · double-click to reset`;
  }
}

window.TomogramVolume = TomogramVolume;
