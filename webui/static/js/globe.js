"use strict";

class TomogramGlobe {
  static CESIUM_VERSION = "1.144.0";
  static IMAGERY_URL = "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}";
  static IMAGERY_CREDIT = "Esri, Maxar, Earthstar Geographics, and the GIS User Community";

  constructor(refs, host) {
    this.host = host;
    this.sourceEl = refs.source;
    this.colorEl = refs.color;
    this.thrEl = refs.thr;
    this.thrLabel = refs.thrLabel;
    this.thrValEl = refs.thrVal;
    this.maxEl = refs.max;
    this.exaggEl = refs.exagg;
    this.liftEl = refs.lift;
    this.clampEl = refs.clamp;
    this.pointsEl = refs.points;
    this.tracksEl = refs.tracks;
    this.reframeEl = refs.reframe;
    this.atEl = refs.at;
    this.container = refs.container;

    this.source = "pred";
    this.colorBy = "mu";
    this.available = false;
    this.points = null;
    this.total = 0;
    this.shown = 0;
    this.muRange = null;
    this.flown = false;
    this.loader = null;
    this.viewer = null;
    this.collection = null;
    this.trackLayer = null;
    this.debounceTimer = null;
    this.token = 0;

    this.sourceEl.querySelectorAll(".cube-space").forEach((btn) => {
      btn.addEventListener("click", () => this._setSource(btn.dataset.source));
    });
    this.colorEl.querySelectorAll(".cube-space").forEach((btn) => {
      btn.addEventListener("click", () => this._setColor(btn.dataset.color));
    });

    this.thrEl.addEventListener("input", () => this._onThreshold());
    this.maxEl.addEventListener("change", () => this._fetch());
    this.exaggEl.addEventListener("change", () => this._redraw());
    this.liftEl.addEventListener("change", () => this._redraw());
    this.clampEl.addEventListener("change", () => this._redraw());
    this.pointsEl.addEventListener("change", () => this._onPointsToggle());
    this.tracksEl.addEventListener("change", () => this._onTracksToggle());
    this.reframeEl.addEventListener("click", () => this._flyToScene(true));
  }

  configure(meta) {
    const sources = this._sources(meta);
    this.available = !!meta.globe && sources.length > 0;
    if (!sources.includes(this.source)) this.source = sources[0] || "pred";

    const hasTracks = !!(meta.globe && meta.globe.tracks);
    this.tracksEl.disabled = !hasTracks;
    this.tracksEl.title = hasTracks ? "" : (meta.globe && meta.globe.tracks_note) || "no track selection stored for this stamp";

    this.points = null;
    this.muRange = null;
    this.shown = 0;
    this.flown = false;
    if (this.collection) {
      this.collection.removeAll();
      this.trackLayer.removeAll();
      this.viewer.scene.requestRender();
    }
    this._syncThresholdLabel();
  }

  _sources(meta = this.host.meta) {
    const out = meta.params ? meta.params.sources.slice() : [];
    if (meta.sources.includes("reduced")) out.push("reduced");
    return out;
  }

  _isParam() {
    return this.source === "pred" || this.source === "gt";
  }

  _ampMin() {
    return TomogramCloud.ampFloor(this.host.meta, this.source, Number(this.thrEl.value) / 100);
  }

  _maxPoints() {
    const value = Math.floor(Number(this.maxEl.value));
    if (!Number.isFinite(value) || value < 0) return 60000;
    return value;
  }

  _syncThresholdLabel() {
    const meta = this.host.meta;
    if (!meta || (this._isParam() && !meta.params)) return;
    this.thrLabel.textContent = this._isParam() ? "amp ≥" : "int ≥";
    this.thrValEl.textContent = this.host._fmt(this._ampMin());
  }

  _syncBtns() {
    const sources = this._sources();
    this.sourceEl.querySelectorAll(".cube-space").forEach((btn) => {
      btn.classList.toggle("is-active", btn.dataset.source === this.source);
      btn.disabled = !sources.includes(btn.dataset.source);
    });
    this.colorEl.querySelectorAll(".cube-space").forEach((btn) => {
      btn.classList.toggle("is-active", btn.dataset.color === this.colorBy);
    });
  }

  _setSource(source) {
    if (source === this.source) return;
    if (!this._sources().includes(source)) {
      Toast.show(TomogramCloud.MISSING[source] || "This source is not available.", "warn");
      return;
    }
    this.source = source;
    this._syncBtns();
    this._syncThresholdLabel();
    this._fetch();
  }

  _setColor(colorBy) {
    if (colorBy === this.colorBy) return;
    this.colorBy = colorBy;
    this._syncBtns();
    this._redraw();
  }

  _onThreshold() {
    this._syncThresholdLabel();
    clearTimeout(this.debounceTimer);
    this.debounceTimer = setTimeout(() => this._fetch(), 250);
  }

  _ensureCesium() {
    if (this.loader) return this.loader;

    const base = `https://cdn.jsdelivr.net/npm/cesium@${TomogramGlobe.CESIUM_VERSION}/Build/Cesium/`;
    window.CESIUM_BASE_URL = base;

    const css = document.createElement("link");
    css.rel = "stylesheet";
    css.href = `${base}Widgets/widgets.css`;
    document.head.appendChild(css);

    this.loader = new Promise((resolve, reject) => {
      const script = document.createElement("script");
      script.src = `${base}Cesium.js`;
      script.onload = () => resolve();
      script.onerror = () => {
        this.loader = null;
        reject(new Error("CesiumJS failed to load"));
      };
      document.head.appendChild(script);
    });
    return this.loader;
  }

  _ensureViewer() {
    if (this.viewer) return;

    const provider = new Cesium.UrlTemplateImageryProvider({
      url: TomogramGlobe.IMAGERY_URL,
      credit: TomogramGlobe.IMAGERY_CREDIT,
      maximumLevel: 19,
    });

    this.viewer = new Cesium.Viewer(this.container, {
      baseLayer: new Cesium.ImageryLayer(provider),
      baseLayerPicker: false,
      geocoder: false,
      homeButton: false,
      sceneModePicker: false,
      navigationHelpButton: false,
      animation: false,
      timeline: false,
      fullscreenButton: false,
      infoBox: false,
      selectionIndicator: false,
      requestRenderMode: true,
      maximumRenderTimeChange: Infinity,
    });

    this.viewer.scene.globe.baseColor = Cesium.Color.fromCssColorString("#10151a");
    this.collection = this.viewer.scene.primitives.add(new Cesium.PointPrimitiveCollection());
    this.collection.show = this.pointsEl.checked;
    this.trackLayer = this.viewer.scene.primitives.add(new Cesium.PrimitiveCollection());
  }

  _onPointsToggle() {
    if (!this.collection) return;
    this.collection.show = this.pointsEl.checked;
    this.viewer.scene.requestRender();
  }

  _onTracksToggle() {
    if (!this.viewer) return;
    this._redrawTracks();
    this._syncStatus();
    this._flyToScene(true);
    this.viewer.scene.requestRender();
  }

  async _fetch() {
    if (!this.available || !this.viewer) return;

    const url = `/api/cubes/globe_points?id=${encodeURIComponent(this.host.selectedId)}&source=${this.source}` +
      `&amp_min=${this._ampMin()}&max=${this._maxPoints()}`;

    this.token += 1;
    const token = this.token;

    let raw;
    try {
      const res = await fetch(url);
      if (!res.ok) return;
      raw = new Float32Array(await res.arrayBuffer());
    } catch (e) {
      return;
    }
    if (token !== this.token) return;

    this.points = raw.subarray(4);
    this.total = raw[1];
    this.muRange = TomogramCloud.sampleRange(this.points, 3, 5);
    this._redraw();
  }

  _sceneRadius(globe) {
    const [west, south, east, north] = globe.bbox;
    const midLat = (south + north) / 2;

    const extentEast = (east - west) * 111320.0 * Math.cos(midLat * Math.PI / 180);
    const extentNorth = (north - south) * 110574.0;
    return Math.max(0.5 * Math.max(extentEast, extentNorth), 100.0);
  }

  _lift(globe) {
    return Number(this.liftEl.value || 0) - (this.clampEl.checked ? globe.base_height : 0);
  }

  _place(offset, anchor, up, lift) {
    return new Cesium.Cartesian3(
      anchor.x + offset[0] + up.x * lift,
      anchor.y + offset[1] + up.y * lift,
      anchor.z + offset[2] + up.z * lift,
    );
  }

  _flyToScene(animate) {
    if (!this.viewer || !this.host.meta || !this.host.meta.globe) return;

    const globe = this.host.meta.globe;
    const radius = this._sceneRadius(globe);

    const anchor = new Cesium.Cartesian3(globe.anchor_ecef[0], globe.anchor_ecef[1], globe.anchor_ecef[2]);
    const up = Cesium.Ellipsoid.WGS84.geodeticSurfaceNormal(anchor, new Cesium.Cartesian3());
    const lift = this._lift(globe);

    let center = new Cesium.Cartesian3(anchor.x + up.x * lift, anchor.y + up.y * lift, anchor.z + up.z * lift);
    let sphere = radius;

    if (this.tracksEl.checked && globe.tracks) {
      const apex = this._place(globe.tracks.beam.apex, anchor, up, lift);
      const gap = Cesium.Cartesian3.distance(center, apex);
      if (gap > sphere) {
        const grown = (gap + sphere) / 2;
        const shift = (grown - sphere) / gap;
        center = new Cesium.Cartesian3(
          center.x + (apex.x - center.x) * shift,
          center.y + (apex.y - center.y) * shift,
          center.z + (apex.z - center.z) * shift,
        );
        sphere = grown;
      }
    }

    this.viewer.camera.flyToBoundingSphere(new Cesium.BoundingSphere(center, sphere), {
      offset: new Cesium.HeadingPitchRange(0, Cesium.Math.toRadians(-32), sphere * 3.4),
      duration: animate ? 1.2 : 0,
    });
  }

  _redraw() {
    if (!this.viewer || !this.points || this.host.view !== "globe") return;

    const meta = this.host.meta;
    const globe = meta.globe;
    const rows = this.points;

    const anchor = new Cesium.Cartesian3(globe.anchor_ecef[0], globe.anchor_ecef[1], globe.anchor_ecef[2]);
    const up = Cesium.Ellipsoid.WGS84.geodeticSurfaceNormal(anchor, new Cesium.Cartesian3());
    const lift = this._lift(globe);
    const exagg = Number(this.exaggEl.value || 1);

    const [muLo, muHi] = this.muRange || [meta.x_min, meta.x_max];
    const muSpan = (muHi - muLo) || 1;

    const logAmp = this._isParam();
    let ampLo, ampHi;
    if (logAmp) {
      ampLo = Math.log(Math.max(meta.params.threshold, 1e-6));
      ampHi = Math.log(Math.max(meta.params.ranges.amp[1], meta.params.threshold * 10));
    } else {
      [ampLo, ampHi] = meta.intensity[this.source];
    }

    this.collection.removeAll();

    for (let i = 0; i < rows.length; i += 5) {
      const mu = rows[i + 3];
      const amp = rows[i + 4];
      const t = this.colorBy === "amp"
        ? ((logAmp ? Math.log(Math.max(amp, 1e-6)) : amp) - ampLo) / Math.max(ampHi - ampLo, 1e-6)
        : (mu - muLo) / muSpan;
      const rgb = TomogramCloud.palette(t);

      const upComp = rows[i] * up.x + rows[i + 1] * up.y + rows[i + 2] * up.z;
      const rise = upComp * (exagg - 1) + lift;

      this.collection.add({
        position: new Cesium.Cartesian3(
          anchor.x + rows[i] + up.x * rise,
          anchor.y + rows[i + 1] + up.y * rise,
          anchor.z + rows[i + 2] + up.z * rise,
        ),
        color: Cesium.Color.fromBytes(rgb[0], rgb[1], rgb[2], 255),
        pixelSize: 2.5,
      });
    }

    if (!this.flown) {
      this._flyToScene(false);
      this.flown = true;
    }

    this.shown = rows.length / 5;
    this._redrawTracks();
    this._syncStatus();
    this.viewer.scene.requestRender();
  }

  _syncStatus() {
    if (!this.host.meta || !this.host.meta.globe) return;
    const globe = this.host.meta.globe;
    const exagg = Number(this.exaggEl.value || 1);
    const exaggNote = exagg > 1 ? ` · height ${exagg}×` : "";

    let trackNote = globe.tracks ? "" : ` · ${globe.tracks_note}`;
    if (this.tracksEl.checked && globe.tracks) {
      const beam = globe.tracks.beam;
      trackNote = ` · ${globe.tracks.labels.length} tracks · look ${beam.look_near_deg.toFixed(1)}-${beam.look_far_deg.toFixed(1)}°`;
    }

    this.atEl.textContent = `${this.shown.toLocaleString()} of ${Math.round(this.total).toLocaleString()} scatterers${exaggNote}${trackNote} · corner fit ±${globe.residual_rms_m.toFixed(1)} m · ctrl+drag tilts · Esri World Imagery`;
  }

  _redrawTracks() {
    if (!this.trackLayer) return;
    this.trackLayer.removeAll();

    const meta = this.host.meta;
    if (!meta || !meta.globe || !meta.globe.tracks || !this.tracksEl.checked) return;

    const globe = meta.globe;
    const tracks = globe.tracks;
    const anchor = new Cesium.Cartesian3(globe.anchor_ecef[0], globe.anchor_ecef[1], globe.anchor_ecef[2]);
    const up = Cesium.Ellipsoid.WGS84.geodeticSurfaceNormal(anchor, new Cesium.Cartesian3());
    const lift = this._lift(globe);

    const refColor = Cesium.Color.fromCssColorString("#ffd166");
    const secColor = Cesium.Color.fromCssColorString("#63d1f4").withAlpha(0.6);
    const beamColor = Cesium.Color.fromCssColorString("#ffd166").withAlpha(0.85);

    const lines = this.trackLayer.add(new Cesium.PolylineCollection());
    let refLine = null;

    tracks.lines.forEach((line, i) => {
      const positions = line.map((offset) => this._place(offset, anchor, up, lift));
      const isRef = tracks.labels[i] === tracks.reference;
      if (isRef) refLine = positions;
      lines.add({ positions, width: isRef ? 3 : 1.5, material: Cesium.Material.fromType("Color", { color: isRef ? refColor : secColor }) });
    });

    const apex = this._place(tracks.beam.apex, anchor, up, lift);
    const near = this._place(tracks.beam.near, anchor, up, lift);
    const far = this._place(tracks.beam.far, anchor, up, lift);

    lines.add({ positions: [apex, near], width: 2, material: Cesium.Material.fromType("Color", { color: beamColor }) });
    lines.add({ positions: [apex, far], width: 2, material: Cesium.Material.fromType("Color", { color: beamColor }) });
    lines.add({ positions: [near, far], width: 2, material: Cesium.Material.fromType("Color", { color: beamColor.withAlpha(0.5) }) });

    this.trackLayer.add(this._meshPrimitive([apex, near, far], Cesium.Color.fromCssColorString("#ffd166").withAlpha(0.18)));

    if (refLine) this._addPlaneGlyph(apex, refLine, up);
  }

  _addPlaneGlyph(apex, refLine, up) {
    const first = refLine[0];
    const last = refLine[refLine.length - 1];
    const forward = Cesium.Cartesian3.normalize(Cesium.Cartesian3.subtract(last, first, new Cesium.Cartesian3()), new Cesium.Cartesian3());
    const right = Cesium.Cartesian3.normalize(Cesium.Cartesian3.cross(forward, up, new Cesium.Cartesian3()), new Cesium.Cartesian3());
    const size = Math.max(0.05 * this.host.meta.globe.tracks.beam.slant_near_m, 25.0);

    const local = [
      [1.15, 0.0, 0.0], [-1.0, -0.12, 0.0], [-1.0, 0.12, 0.0],
      [1.15, 0.0, 0.0], [-1.0, 0.0, 0.12], [-1.0, 0.0, -0.12],
      [0.45, 0.0, 0.0], [-0.25, -1.0, 0.0], [-0.25, 1.0, 0.0],
      [-0.65, 0.0, 0.0], [-1.05, -0.45, 0.0], [-1.05, 0.45, 0.0],
      [-0.65, 0.0, 0.0], [-1.05, 0.0, 0.0], [-1.05, 0.0, 0.4],
    ];

    const vertices = local.map(([f, r, u]) => new Cesium.Cartesian3(
      apex.x + size * (f * forward.x + r * right.x + u * up.x),
      apex.y + size * (f * forward.y + r * right.y + u * up.y),
      apex.z + size * (f * forward.z + r * right.z + u * up.z),
    ));

    this.trackLayer.add(this._meshPrimitive(vertices, Cesium.Color.fromCssColorString("#ffd166")));
  }

  _meshPrimitive(vertices, color) {
    const values = new Float64Array(vertices.length * 3);
    vertices.forEach((vertex, i) => {
      values[3 * i] = vertex.x;
      values[3 * i + 1] = vertex.y;
      values[3 * i + 2] = vertex.z;
    });

    const indices = new Uint16Array(vertices.length);
    for (let i = 0; i < indices.length; i += 1) indices[i] = i;

    const geometry = new Cesium.Geometry({
      attributes: {
        position: new Cesium.GeometryAttribute({
          componentDatatype: Cesium.ComponentDatatype.DOUBLE,
          componentsPerAttribute: 3,
          values,
        }),
      },
      indices,
      primitiveType: Cesium.PrimitiveType.TRIANGLES,
      boundingSphere: Cesium.BoundingSphere.fromVertices(Array.from(values)),
    });

    return new Cesium.Primitive({
      geometryInstances: new Cesium.GeometryInstance({
        geometry,
        attributes: { color: Cesium.ColorGeometryInstanceAttribute.fromColor(color) },
      }),
      appearance: new Cesium.PerInstanceColorAppearance({
        flat: true,
        translucent: color.alpha < 1.0,
        renderState: { cull: { enabled: false } },
      }),
      asynchronous: false,
    });
  }

  render() {
    this._syncBtns();
    this._syncThresholdLabel();

    this._ensureCesium()
      .then(() => {
        this._ensureViewer();
        this.viewer.resize();
        if (!this.points) this._fetch();
        else this._redraw();
      })
      .catch(() => {
        this.atEl.textContent = "CesiumJS could not be loaded — the globe needs internet access.";
      });
  }
}
