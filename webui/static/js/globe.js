"use strict";

class TomogramGlobe {
  static CESIUM_VERSION = "1.144.0";
  static IMAGERY_URL = "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}";
  static IMAGERY_CREDIT = "Esri, Maxar, Earthstar Geographics, and the GIS User Community";
  static CACHE_LIMIT = 8;
  static VIEW_PITCH_DEG = -32;
  static VIEW_RANGE_FACTOR = 3.4;
  static FLIGHT_PERIOD_MS = 12000;

  constructor(refs, host) {
    this.host = host;
    this.colorEl = refs.color;
    this.thrEl = refs.thr;
    this.thrValEl = refs.thrVal;
    this.maxEl = refs.max;
    this.cutAxisEl = refs.cutAxis;
    this.cutPosEl = refs.cutPos;
    this.cutSweepEl = refs.cutSweep;
    this.exaggEl = refs.exagg;
    this.liftEl = refs.lift;
    this.clampEl = refs.clamp;
    this.pointsEl = refs.points;
    this.tracksEl = refs.tracks;
    this.flyEl = refs.fly;
    this.reframeEl = refs.reframe;
    this.atEl = refs.at;
    this.container = refs.container;
    this.stageEl = refs.stage;
    this.tour = new GlobeTour(refs.tour, this);

    this.source = "full";
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
    this.loadTimer = null;
    this.cache = new Map();
    this.inFlight = new Set();
    this.prefetchAborts = [];
    this.token = 0;
    this.flightBasis = null;
    this.flightGroup = null;
    this.flightFrame = null;
    this.flightT0 = null;
    this.pointAlong = null;
    this.alongOrder = null;
    this.shownUpTo = -1;
    this.cutLayer = null;
    this.cutDir = null;
    this.cutAlong = null;
    this.cutOrder = null;
    this.cutRange = null;
    this.cutShownUpTo = -1;
    this.cutPlane = null;
    this.cutBase = 0;
    this.sweepFrame = null;
    this.sweepT0 = null;
    this.flightPeriod = TomogramGlobe.FLIGHT_PERIOD_MS;

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
    this.flyEl.addEventListener("change", () => this._onFlyToggle());
    this.reframeEl.addEventListener("click", () => this._flyToScene(true));
    this.cutAxisEl.addEventListener("change", () => this._onCutAxis());
    this.cutPosEl.addEventListener("input", () => this._onCutPos());
    this.cutSweepEl.addEventListener("change", () => this._onCutSweep());
  }

  configure(meta) {
    this.available = !!meta.globe && meta.sources.includes("full");
    this.source = this.host.srcFor();
    if (meta.globe_defaults) this.maxEl.value = meta.globe_defaults.max_points;

    const hasTracks = !!(meta.globe && meta.globe.tracks);
    this.tracksEl.disabled = !hasTracks;
    this.tracksEl.title = hasTracks ? "" : (meta.globe && meta.globe.tracks_note) || "no track selection stored for this stamp";
    this.flyEl.disabled = !hasTracks;
    if (!hasTracks) this.flyEl.checked = false;

    this._stopSweep();
    this.flightPeriod = TomogramGlobe.FLIGHT_PERIOD_MS;
    this.cutDir = null;
    this.cutAlong = null;
    this.cutOrder = null;
    this.cutRange = null;
    this.cutShownUpTo = -1;
    this.cutPlane = null;
    if (this.cutLayer) this.cutLayer.removeAll();

    this._stopFlight();
    this._abortPrefetch();
    this.cache.clear();
    this.inFlight = new Set();
    this.points = null;
    this.muRange = null;
    this.shown = 0;
    this.flown = false;
    this.flightBasis = null;
    this.pointAlong = null;
    this.alongOrder = null;
    this.shownUpTo = -1;
    if (this.collection) {
      this.collection.removeAll();
      this.trackLayer.removeAll();
      this.flightGroup = null;
      this.viewer.scene.requestRender();
    }
    this._syncThresholdLabel();
    this.tour.sync();
  }

  _ampMin(source = this.source) {
    const frac = Number(this.thrEl.value) / 100;
    const defaults = this.host.meta.globe_defaults;
    if (frac === 0 && defaults && defaults.amp_min[source] !== undefined) return defaults.amp_min[source];
    return TomogramCloud.ampFloor(this.host.meta, source, frac);
  }

  _maxPoints() {
    const value = Math.floor(Number(this.maxEl.value));
    if (!Number.isFinite(value) || value < 0) return this.host.meta.globe_defaults.max_points;
    return value;
  }

  _syncThresholdLabel() {
    if (!this.host.meta) return;
    this.thrValEl.textContent = this.host._fmt(this._ampMin());
  }

  _syncBtns() {
    this.colorEl.querySelectorAll(".cube-space").forEach((btn) => {
      btn.classList.toggle("is-active", btn.dataset.color === this.colorBy);
    });
  }

  _setColor(colorBy) {
    if (colorBy === this.colorBy) return;
    this.colorBy = colorBy;
    this._syncBtns();
    this._redraw();
  }

  _onThreshold() {
    this._syncThresholdLabel();
    this._abortPrefetch();
    clearTimeout(this.debounceTimer);
    this.debounceTimer = setTimeout(() => this._fetch(), 250);
  }

  _abortPrefetch() {
    this.prefetchAborts.forEach((controller) => controller.abort());
    this.prefetchAborts = [];
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
      contextOptions: { webgl: { preserveDrawingBuffer: true } },
    });

    this.viewer.scene.globe.baseColor = Cesium.Color.fromCssColorString("#10151a");
    this.collection = this.viewer.scene.primitives.add(new Cesium.PointPrimitiveCollection());
    this.collection.show = this.pointsEl.checked;
    this.trackLayer = this.viewer.scene.primitives.add(new Cesium.PrimitiveCollection());
    this.cutLayer = this.viewer.scene.primitives.add(new Cesium.PrimitiveCollection());
  }

  _onPointsToggle() {
    if (!this.collection) return;
    this.collection.show = this.pointsEl.checked;
    this.viewer.scene.requestRender();
  }

  _onTracksToggle() {
    if (!this.tracksEl.checked) this.flyEl.checked = false;
    if (!this.viewer) return;
    this._redrawTracks();
    this._syncStatus();
    this._flyToScene(true);
    this.viewer.scene.requestRender();
  }

  _onFlyToggle() {
    if (this.flyEl.checked && this.cutAxisEl.value !== "off") {
      this.cutAxisEl.value = "off";
      this.cutSweepEl.checked = false;
      this._stopSweep();
      this._rebuildCut();
    }
    if (this.flyEl.checked && !this.tracksEl.checked) {
      this.tracksEl.checked = true;
      this._onTracksToggle();
      return;
    }
    if (!this.viewer) return;
    this._redrawTracks();
    this._syncStatus();
    this.viewer.scene.requestRender();
  }

  _onCutAxis() {
    if (this.cutAxisEl.value !== "off" && this.flyEl.checked) {
      this.flyEl.checked = false;
      this._redrawTracks();
    }
    if (this.cutAxisEl.value === "off") {
      this.cutSweepEl.checked = false;
      this._stopSweep();
    }
    this._rebuildCut();
    this._syncStatus();
  }

  _onCutPos() {
    this._applyCut();
    this._syncStatus();
  }

  _onCutSweep() {
    if (this.cutSweepEl.checked && this.cutAxisEl.value === "off") {
      this.cutAxisEl.value = "east";
      this._onCutAxis();
    }
    if (this.cutSweepEl.checked) this._startSweep();
    else this._stopSweep();
  }

  _startSweep() {
    this._stopSweep();
    this.sweepFrame = requestAnimationFrame((now) => this._sweepStep(now));
  }

  _stopSweep() {
    if (this.sweepFrame !== null) cancelAnimationFrame(this.sweepFrame);
    this.sweepFrame = null;
    this.sweepT0 = null;
  }

  _sweepStep(now) {
    if (this.host.view !== "globe" || !this.cutSweepEl.checked || this.cutAxisEl.value === "off" || !this.cutOrder) {
      this._stopSweep();
      return;
    }

    if (this.sweepT0 === null) this.sweepT0 = now - (Number(this.cutPosEl.value) / 100) * (TomogramCloud.SWEEP_MS / 2);
    const phase = ((now - this.sweepT0) % TomogramCloud.SWEEP_MS) / TomogramCloud.SWEEP_MS;
    const tri = phase < 0.5 ? phase * 2 : 2 - phase * 2;

    this.cutPosEl.value = String(Math.round(tri * 100));
    this._applyCut();
    this._syncStatus();
    this.sweepFrame = requestAnimationFrame((next) => this._sweepStep(next));
  }

  sceneFrame() {
    const globe = this.host.meta.globe;
    const anchor = new Cesium.Cartesian3(globe.anchor_ecef[0], globe.anchor_ecef[1], globe.anchor_ecef[2]);
    const enu = Cesium.Transforms.eastNorthUpToFixedFrame(anchor);
    const column = (i) => Cesium.Cartesian3.fromCartesian4(Cesium.Matrix4.getColumn(enu, i, new Cesium.Cartesian4()), new Cesium.Cartesian3());
    const vec = (a) => new Cesium.Cartesian3(a[0], a[1], a[2]);
    return { anchor, east: column(0), north: column(1), up: column(2), azimuth: vec(globe.axes.azimuth), range: vec(globe.axes.range) };
  }

  _planeSpans(frame, dir) {
    const ref = Math.abs(Cesium.Cartesian3.dot(dir, frame.up)) > 0.9 ? frame.north : frame.up;
    const span1 = Cesium.Cartesian3.normalize(Cesium.Cartesian3.cross(dir, ref, new Cesium.Cartesian3()), new Cesium.Cartesian3());
    const span2 = Cesium.Cartesian3.normalize(Cesium.Cartesian3.cross(dir, span1, new Cesium.Cartesian3()), new Cesium.Cartesian3());
    return [span1, span2];
  }

  _rebuildCut() {
    if (this.cutLayer) this.cutLayer.removeAll();
    this.cutDir = null;
    this.cutAlong = null;
    this.cutOrder = null;
    this.cutRange = null;
    this.cutShownUpTo = -1;
    this.cutPlane = null;

    if (!this.viewer || !this.points || !this.collection.length) return;

    const axis = this.cutAxisEl.value;
    if (axis === "off") {
      for (let i = 0; i < this.collection.length; i += 1) this.collection.get(i).show = true;
      this.viewer.scene.requestRender();
      return;
    }

    const frame = this.sceneFrame();
    const dir = frame[axis === "height" ? "up" : axis];
    const [span1, span2] = this._planeSpans(frame, dir);

    const n = this.collection.length;
    this.cutAlong = new Float32Array(n);
    let lo = Infinity, hi = -Infinity;
    let lo1 = Infinity, hi1 = -Infinity;
    let lo2 = Infinity, hi2 = -Infinity;

    for (let i = 0; i < n; i += 1) {
      const p = this.collection.get(i).position;
      const dx = p.x - frame.anchor.x, dy = p.y - frame.anchor.y, dz = p.z - frame.anchor.z;

      const a = dx * dir.x + dy * dir.y + dz * dir.z;
      const b = dx * span1.x + dy * span1.y + dz * span1.z;
      const c = dx * span2.x + dy * span2.y + dz * span2.z;

      this.cutAlong[i] = a;
      if (a < lo) lo = a;
      if (a > hi) hi = a;
      if (b < lo1) lo1 = b;
      if (b > hi1) hi1 = b;
      if (c < lo2) lo2 = c;
      if (c > hi2) hi2 = c;

      this.collection.get(i).show = true;
    }

    this.cutDir = dir;
    this.cutRange = hi > lo ? [lo, hi] : [lo, lo + 1];
    this.cutOrder = this._alongOrder(this.cutAlong);
    this.cutShownUpTo = n - 1;
    this.cutBase = this.cutRange[0];
    this._buildCutPlane(frame, dir, span1, span2, [lo1, hi1], [lo2, hi2]);
    this._applyCut();
    if (this.cutSweepEl.checked && this.sweepFrame === null) this._startSweep();
  }

  _buildCutPlane(frame, dir, span1, span2, ext1, ext2) {
    const pad1 = Math.max(0.05 * (ext1[1] - ext1[0]), 10.0);
    const pad2 = Math.max(0.05 * (ext2[1] - ext2[0]), 10.0);
    const corners = [
      [ext1[0] - pad1, ext2[0] - pad2], [ext1[1] + pad1, ext2[0] - pad2],
      [ext1[1] + pad1, ext2[1] + pad2], [ext1[0] - pad1, ext2[1] + pad2],
    ];

    const point = ([b, c]) => new Cesium.Cartesian3(
      frame.anchor.x + dir.x * this.cutBase + span1.x * b + span2.x * c,
      frame.anchor.y + dir.y * this.cutBase + span1.y * b + span2.y * c,
      frame.anchor.z + dir.z * this.cutBase + span1.z * b + span2.z * c,
    );

    const quad = corners.map(point);
    const mesh = this.cutLayer.add(this._meshPrimitive([quad[0], quad[1], quad[2], quad[0], quad[2], quad[3]], Cesium.Color.fromCssColorString("#ffd166").withAlpha(0.14)));

    const edges = this.cutLayer.add(new Cesium.PolylineCollection());
    edges.add({ positions: [...quad, quad[0]], width: 1.5, material: Cesium.Material.fromType("Color", { color: Cesium.Color.fromCssColorString("#ffd166").withAlpha(0.7) }) });

    this.cutPlane = [mesh, edges];
  }

  _cutThreshold() {
    const frac = Number(this.cutPosEl.value) / 100;
    return this.cutRange[0] + frac * (this.cutRange[1] - this.cutRange[0]);
  }

  _applyCut() {
    if (!this.viewer || !this.cutOrder || !this.cutPlane) return;

    const s = this._cutThreshold();
    const order = this.cutOrder;
    const along = this.cutAlong;

    while (this.cutShownUpTo + 1 < order.length && along[order[this.cutShownUpTo + 1]] <= s) {
      this.cutShownUpTo += 1;
      this.collection.get(order[this.cutShownUpTo]).show = true;
    }
    while (this.cutShownUpTo >= 0 && along[order[this.cutShownUpTo]] > s) {
      this.collection.get(order[this.cutShownUpTo]).show = false;
      this.cutShownUpTo -= 1;
    }

    const shift = Cesium.Cartesian3.multiplyByScalar(this.cutDir, s - this.cutBase, new Cesium.Cartesian3());
    const matrix = Cesium.Matrix4.fromTranslation(shift);
    this.cutPlane.forEach((item) => { item.modelMatrix = matrix; });
    this.viewer.scene.requestRender();
  }

  _url(source) {
    return `/api/cubes/globe_points?id=${encodeURIComponent(this.host.selectedId)}&source=${source}` +
      `&amp_min=${this._ampMin(source)}&max=${this._maxPoints()}`;
  }

  _load(url, signal = null) {
    if (this.cache.has(url)) {
      const entry = this.cache.get(url);
      this.cache.delete(url);
      this.cache.set(url, entry);
      return entry;
    }

    this.inFlight.add(url);
    const entry = fetch(url, signal ? { signal } : undefined)
      .then((res) => {
        if (!res.ok) throw new Error(`globe points request failed with status ${res.status}`);
        return res.arrayBuffer();
      })
      .then((buffer) => new Float32Array(buffer))
      .catch((err) => {
        this.cache.delete(url);
        throw err;
      })
      .finally(() => this.inFlight.delete(url));

    this.cache.set(url, entry);
    while (this.cache.size > TomogramGlobe.CACHE_LIMIT) this.cache.delete(this.cache.keys().next().value);
    return entry;
  }

  _setLoading(on) {
    clearTimeout(this.loadTimer);
    this.loadTimer = null;

    if (!on) {
      this.stageEl.classList.remove("is-loading");
      this.atEl.classList.remove("is-loading");
      return;
    }

    this.loadTimer = setTimeout(() => {
      this.stageEl.classList.add("is-loading");
      this.atEl.classList.add("is-loading");
      this.atEl.textContent = "loading scatterers…";
    }, 120);
  }

  _prefetch() {
    if (!this.host.paramActive) return;
    const other = this.source === "param" ? "full" : "param";
    const url = this._url(other);
    if (this.cache.has(url) || this.inFlight.has(url)) return;

    const controller = new AbortController();
    this.prefetchAborts.push(controller);
    this._load(url, controller.signal).catch(() => {});
  }

  async _fetch() {
    if (!this.available || !this.viewer) return;

    this.token += 1;
    const token = this.token;
    this._setLoading(true);

    let raw;
    try {
      raw = await this._load(this._url(this.source));
    } catch (e) {
      if (token !== this.token) return;
      this._setLoading(false);
      this.atEl.textContent = "the scatterers could not be loaded";
      return;
    }
    if (token !== this.token) return;
    this._setLoading(false);

    this.points = raw.subarray(4);
    this.total = raw[1];
    this.muRange = TomogramCloud.sampleRange(this.points, 3, 5);
    this._redraw();
    this._prefetch();
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

  sceneSphere() {
    const globe = this.host.meta.globe;

    const anchor = new Cesium.Cartesian3(globe.anchor_ecef[0], globe.anchor_ecef[1], globe.anchor_ecef[2]);
    const up = Cesium.Ellipsoid.WGS84.geodeticSurfaceNormal(anchor, new Cesium.Cartesian3());
    const lift = this._lift(globe);

    let center = new Cesium.Cartesian3(anchor.x + up.x * lift, anchor.y + up.y * lift, anchor.z + up.z * lift);
    let sphere = this._sceneRadius(globe);

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

    return new Cesium.BoundingSphere(center, sphere);
  }

  _flyToScene(animate) {
    if (!this.viewer || !this.host.meta || !this.host.meta.globe) return;

    this.tour.stop();
    const sphere = this.sceneSphere();

    this.viewer.camera.flyToBoundingSphere(sphere, {
      offset: new Cesium.HeadingPitchRange(0, Cesium.Math.toRadians(TomogramGlobe.VIEW_PITCH_DEG), sphere.radius * TomogramGlobe.VIEW_RANGE_FACTOR),
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

    const [ampLo, ampHi] = meta.intensity[this.source];

    this.collection.removeAll();
    this.flightBasis = globe.tracks ? this._flightBasis(globe, anchor, up, lift) : null;
    this.pointAlong = this.flightBasis ? new Float32Array(rows.length / 5) : null;

    for (let i = 0; i < rows.length; i += 5) {
      const mu = rows[i + 3];
      const amp = rows[i + 4];
      const t = this.colorBy === "amp"
        ? (amp - ampLo) / Math.max(ampHi - ampLo, 1e-6)
        : (mu - muLo) / muSpan;
      const rgb = TomogramCloud.palette(t);

      const upComp = rows[i] * up.x + rows[i + 1] * up.y + rows[i + 2] * up.z;
      const rise = upComp * (exagg - 1) + lift;

      const position = new Cesium.Cartesian3(
        anchor.x + rows[i] + up.x * rise,
        anchor.y + rows[i + 1] + up.y * rise,
        anchor.z + rows[i + 2] + up.z * rise,
      );

      if (this.pointAlong) {
        const basis = this.flightBasis;
        this.pointAlong[i / 5] = (position.x - basis.first.x) * basis.forward.x
          + (position.y - basis.first.y) * basis.forward.y
          + (position.z - basis.first.z) * basis.forward.z;
      }

      this.collection.add({
        position,
        color: Cesium.Color.fromBytes(rgb[0], rgb[1], rgb[2], 255),
        pixelSize: 2.5,
      });
    }

    this.alongOrder = this.pointAlong ? this._alongOrder(this.pointAlong) : null;
    this.shownUpTo = this.pointAlong ? this.collection.length - 1 : -1;

    if (!this.flown) {
      this._flyToScene(false);
      this.flown = true;
    }

    this.shown = rows.length / 5;
    this._rebuildCut();
    this._redrawTracks();
    this._syncStatus();
    this.viewer.scene.requestRender();
  }

  _alongOrder(along) {
    const order = new Int32Array(along.length);
    for (let i = 0; i < order.length; i += 1) order[i] = i;
    return order.sort((a, b) => along[a] - along[b]);
  }

  _syncStatus() {
    if (!this.host.meta || !this.host.meta.globe) return;
    const globe = this.host.meta.globe;
    const exagg = Number(this.exaggEl.value || 1);
    const exaggNote = exagg > 1 ? ` · height ${exagg}×` : "";

    const cutActive = this.cutAxisEl.value !== "off" && this.cutOrder;
    const cutNote = cutActive ? ` · cut ${this.cutAxisEl.value} @ ${this.cutPosEl.value}%` : "";
    const curtainActive = this.flyEl.checked && this.flightFrame !== null && this.pointAlong;
    const visible = cutActive ? this.cutShownUpTo + 1 : curtainActive ? this.shownUpTo + 1 : this.shown;

    let trackNote = globe.tracks ? "" : ` · ${globe.tracks_note}`;
    if (this.tracksEl.checked && globe.tracks) {
      const beam = globe.tracks.beam;
      trackNote = ` · ${globe.tracks.labels.length} tracks · look ${beam.look_near_deg.toFixed(1)}-${beam.look_far_deg.toFixed(1)}°`;
      if (this.flyEl.checked) trackNote += " · flight loop";
    }

    this.atEl.textContent = `${visible.toLocaleString()} of ${Math.round(this.total).toLocaleString()} voxels${exaggNote}${cutNote}${trackNote} · corner fit ±${globe.residual_rms_m.toFixed(1)} m · ctrl+drag tilts · Esri World Imagery`;
  }

  _redrawTracks() {
    this._stopFlight();
    if (!this.trackLayer) return;
    this.trackLayer.removeAll();
    this.flightGroup = null;

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

    const beamLines = this.trackLayer.add(new Cesium.PolylineCollection());
    beamLines.add({ positions: [apex, near], width: 2, material: Cesium.Material.fromType("Color", { color: beamColor }) });
    beamLines.add({ positions: [apex, far], width: 2, material: Cesium.Material.fromType("Color", { color: beamColor }) });
    beamLines.add({ positions: [near, far], width: 2, material: Cesium.Material.fromType("Color", { color: beamColor.withAlpha(0.5) }) });

    const swath = this.trackLayer.add(this._meshPrimitive([apex, near, far], Cesium.Color.fromCssColorString("#ffd166").withAlpha(0.18)));

    let glyph = null;
    if (refLine) glyph = this._addPlaneGlyph(apex, refLine, up);

    this.flightGroup = [beamLines, swath, glyph].filter(Boolean);

    if (this.flyEl.checked && this.flightBasis) this._startFlight();
  }

  _flightBasis(globe, anchor, up, lift) {
    const tracks = globe.tracks;
    const refIdx = tracks.labels.indexOf(tracks.reference);
    if (refIdx < 0) return null;

    const line = tracks.lines[refIdx];
    const first = this._place(line[0], anchor, up, lift);
    const last = this._place(line[line.length - 1], anchor, up, lift);

    const span = Cesium.Cartesian3.subtract(last, first, new Cesium.Cartesian3());
    const length = Cesium.Cartesian3.magnitude(span);
    if (length < 1.0) return null;
    const forward = Cesium.Cartesian3.divideByScalar(span, length, new Cesium.Cartesian3());

    const apex = this._place(tracks.beam.apex, anchor, up, lift);
    const apexAlong = Cesium.Cartesian3.dot(Cesium.Cartesian3.subtract(apex, first, new Cesium.Cartesian3()), forward);

    return { first, forward, length, apexAlong };
  }

  _startFlight() {
    this.flightT0 = null;
    this._setAllPoints(false);
    this.flightFrame = requestAnimationFrame((now) => this._flightStep(now));
  }

  _setAllPoints(show) {
    if (!this.collection || !this.pointAlong) return;
    for (let i = 0; i < this.collection.length; i += 1) this.collection.get(i).show = show;
    this.shownUpTo = show ? this.collection.length - 1 : -1;
  }

  _stopFlight() {
    if (this.flightFrame !== null) {
      cancelAnimationFrame(this.flightFrame);
      this.flightFrame = null;
    }
    this.flightT0 = null;

    this._setAllPoints(true);
    if (this.flightGroup) {
      this.flightGroup.forEach((item) => { item.modelMatrix = Cesium.Matrix4.clone(Cesium.Matrix4.IDENTITY); });
    }
    if (this.cutOrder) {
      this.cutShownUpTo = this.cutOrder.length - 1;
      this._applyCut();
    }
    if (this.viewer) this.viewer.scene.requestRender();
  }

  leave() {
    this._stopSweep();
    this._stopFlight();
    this.tour.stop();
  }

  _flightStep(now) {
    if (this.host.view !== "globe" || !this.flightBasis || !this.flightGroup) {
      this._stopFlight();
      return;
    }

    if (this.flightT0 === null) this.flightT0 = now;
    const frac = ((now - this.flightT0) % this.flightPeriod) / this.flightPeriod;
    const t = Math.min(frac / 0.85, 1.0);
    const s = this.flightBasis.length * t;

    const shift = Cesium.Cartesian3.multiplyByScalar(this.flightBasis.forward, s - this.flightBasis.apexAlong, new Cesium.Cartesian3());
    const matrix = Cesium.Matrix4.fromTranslation(shift);
    this.flightGroup.forEach((item) => { item.modelMatrix = matrix; });

    if (this.pointAlong && this.collection.show) this._advanceCurtain(s);

    this.viewer.scene.requestRender();
    this.flightFrame = requestAnimationFrame((next) => this._flightStep(next));
  }

  _advanceCurtain(s) {
    const order = this.alongOrder;

    if (this.shownUpTo >= 0 && this.pointAlong[order[this.shownUpTo]] > s) {
      for (let i = 0; i <= this.shownUpTo; i += 1) this.collection.get(order[i]).show = false;
      this.shownUpTo = -1;
    }

    while (this.shownUpTo + 1 < order.length && this.pointAlong[order[this.shownUpTo + 1]] <= s) {
      this.shownUpTo += 1;
      this.collection.get(order[this.shownUpTo]).show = true;
    }
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

    return this.trackLayer.add(this._meshPrimitive(vertices, Cesium.Color.fromCssColorString("#ffd166")));
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
        if (this.cutSweepEl.checked && this.sweepFrame === null) this._startSweep();
      })
      .catch(() => {
        this.atEl.textContent = "CesiumJS could not be loaded — the globe needs internet access.";
      });
  }
}
