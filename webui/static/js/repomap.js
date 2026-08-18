"use strict";

class WireRouter {
  constructor(boxes, edges, bounds) {
    this.boxes   = boxes;
    this.edges   = edges;
    this.W       = bounds.w;
    this.H       = bounds.h;
    this.routes  = [];
    this.faceUse = {};
    this.pairs   = {};
    Object.values(this.boxes).forEach((b) => { b.cx = b.x + b.w / 2; b.cy = b.y + b.h / 2; });
  }

  _bands() {
    this.cols = {};
    this.rows = {};
    Object.values(this.boxes).forEach((b) => {
      const c = this.cols[b.col] || (this.cols[b.col] = { L: Infinity, R: -Infinity });
      c.L = Math.min(c.L, b.x); c.R = Math.max(c.R, b.x + b.w);
      const r = this.rows[b.row] || (this.rows[b.row] = { T: Infinity, B: -Infinity });
      r.T = Math.min(r.T, b.y); r.B = Math.max(r.B, b.y + b.h);
    });
    this.colKeys = Object.keys(this.cols).map(Number).sort((p, q) => p - q);
    this.rowKeys = Object.keys(this.rows).map(Number).sort((p, q) => p - q);
  }

  _corridors() {
    this.vcorr = [];
    this.hcorr = [];
    for (let i = 0; i <= this.colKeys.length; i++) {
      const lo = i === 0 ? 8 : this.cols[this.colKeys[i - 1]].R + 6;
      const hi = i === this.colKeys.length ? this.W - 8 : this.cols[this.colKeys[i]].L - 6;
      this.vcorr.push({ lo, hi, members: [] });
    }
    for (let j = 0; j <= this.rowKeys.length; j++) {
      const lo = j === 0 ? 8 : this.rows[this.rowKeys[j - 1]].B + 6;
      const hi = j === this.rowKeys.length ? this.H - 8 : this.rows[this.rowKeys[j]].T - 6;
      this.hcorr.push({ lo, hi, members: [] });
    }
  }

  _face(b, f) {
    if (f === "R") return { x: b.x + b.w, y: b.cy };
    if (f === "L") return { x: b.x,       y: b.cy };
    if (f === "B") return { x: b.cx, y: b.y + b.h };
    return { x: b.cx, y: b.y };
  }

  _candidates(a, b) {
    const cands = [];
    const dc = b.col - a.col, dr = b.row - a.row;

    if (dr === 0)            cands.push({ kind: "straight", fa: dc >= 0 ? "R" : "L", fb: dc >= 0 ? "L" : "R" });
    if (dc === 0 && dr !== 0) cands.push({ kind: "straight", fa: dr > 0 ? "B" : "T", fb: dr > 0 ? "T" : "B" });

    if (dc !== 0 && dr !== 0) {
      cands.push({ kind: "hv", fa: dc > 0 ? "R" : "L", fb: dr > 0 ? "T" : "B" });
      cands.push({ kind: "vh", fa: dr > 0 ? "B" : "T", fb: dc > 0 ? "L" : "R" });
    }

    this.vcorr.forEach((c, i) => {
      const mid = (c.lo + c.hi) / 2;
      cands.push({ kind: "zv", corr: i, fa: mid >= a.cx ? "R" : "L", fb: mid >= b.cx ? "R" : "L" });
    });
    this.hcorr.forEach((c, j) => {
      const mid = (c.lo + c.hi) / 2;
      cands.push({ kind: "zh", corr: j, fa: mid >= a.cy ? "B" : "T", fb: mid >= b.cy ? "B" : "T" });
    });

    return cands;
  }

  _pts(cand, a, b) {
    const pa = this._face(a, cand.fa), pb = this._face(b, cand.fb);
    if (cand.kind === "straight") return [pa, pb];
    if (cand.kind === "hv")       return [pa, { x: pb.x, y: pa.y }, pb];
    if (cand.kind === "vh")       return [pa, { x: pa.x, y: pb.y }, pb];
    if (cand.kind === "zv") {
      const c = this.vcorr[cand.corr], m = (c.lo + c.hi) / 2;
      return [pa, { x: m, y: pa.y }, { x: m, y: pb.y }, pb];
    }
    const c = this.hcorr[cand.corr], m = (c.lo + c.hi) / 2;
    return [pa, { x: pa.x, y: m }, { x: pb.x, y: m }, pb];
  }

  _length(pts) {
    let L = 0;
    for (let i = 1; i < pts.length; i++) L += Math.abs(pts[i].x - pts[i - 1].x) + Math.abs(pts[i].y - pts[i - 1].y);
    return L;
  }

  _segHitsBox(p0, p1, b) {
    const x0 = b.x + 3, y0 = b.y + 3, x1 = b.x + b.w - 3, y1 = b.y + b.h - 3;
    const dx = p1.x - p0.x, dy = p1.y - p0.y;
    let t0 = 0.02, t1 = 0.98, ok = true;
    [[-dx, p0.x - x0], [dx, x1 - p0.x], [-dy, p0.y - y0], [dy, y1 - p0.y]].forEach(([p, q]) => {
      if (!ok) return;
      if (Math.abs(p) < 1e-9) { if (q < 0) ok = false; return; }
      const t = q / p;
      if (p < 0) { if (t > t0) t0 = t; }
      else       { if (t < t1) t1 = t; }
    });
    return ok && t0 < t1;
  }

  _hitCount(pts, skipA, skipB) {
    let n = 0;
    for (let i = 1; i < pts.length; i++) {
      Object.entries(this.boxes).forEach(([id, b]) => {
        if (id === skipA || id === skipB) return;
        if (this._segHitsBox(pts[i - 1], pts[i], b)) n++;
      });
    }
    return n;
  }

  _crossCount(pa, pb) {
    let n = 0;
    const ori = (p, q, r) => Math.sign((q.x - p.x) * (r.y - p.y) - (q.y - p.y) * (r.x - p.x));
    for (let i = 1; i < pa.length; i++) {
      for (let j = 1; j < pb.length; j++) {
        const a0 = pa[i - 1], a1 = pa[i], b0 = pb[j - 1], b1 = pb[j];
        const o1 = ori(a0, a1, b0), o2 = ori(a0, a1, b1), o3 = ori(b0, b1, a0), o4 = ori(b0, b1, a1);
        if (o1 !== o2 && o3 !== o4 && o1 !== 0 && o2 !== 0 && o3 !== 0 && o4 !== 0) n++;
      }
    }
    return n;
  }

  _faceCost(id, f, dir) {
    const u = this.faceUse[id + "|" + f];
    if (!u) return 0;
    const opp = dir === "out" ? u.in : u.out;
    return (opp ? 170 : 0) + (u.in + u.out) * 14;
  }

  _corrCost(corr, lo, hi) {
    let n = 0;
    corr.members.forEach(({ r }) => {
      const p1 = r.pts[1], p2 = r.pts[2];
      const mlo = Math.min(p1.x === p2.x ? p1.y : p1.x, p1.x === p2.x ? p2.y : p2.x);
      const mhi = Math.max(p1.x === p2.x ? p1.y : p1.x, p1.x === p2.x ? p2.y : p2.x);
      if (Math.min(hi, mhi) - Math.max(lo, mlo) > -10) n++;
    });
    return n * 28;
  }

  _evaluate(cand, a, b, e) {
    const pts   = this._pts(cand, a, b);
    const bends = cand.kind === "straight" ? 0 : (cand.kind === "hv" || cand.kind === "vh") ? 1 : 2;

    let cost = bends * 120;
    cost += this._length(pts) * 0.12;
    cost += this._hitCount(pts, e.from, e.to) * 900;
    cost += this._faceCost(e.from, cand.fa, "out");
    cost += this._faceCost(e.to,   cand.fb, "in");

    if (cand.kind === "zv") cost += this._corrCost(this.vcorr[cand.corr], Math.min(pts[1].y, pts[2].y), Math.max(pts[1].y, pts[2].y)) + ((cand.corr === 0 || cand.corr === this.vcorr.length - 1) ? 18 : 0);
    if (cand.kind === "zh") cost += this._corrCost(this.hcorr[cand.corr], Math.min(pts[1].x, pts[2].x), Math.max(pts[1].x, pts[2].x)) + ((cand.corr === 0 || cand.corr === this.hcorr.length - 1) ? 18 : 0);

    this.routes.forEach((r) => { cost += this._crossCount(pts, r.pts) * 34; });
    return { cand, pts, cost };
  }

  _commit(it, ev) {
    const r  = { e: it.e, a: it.a, b: it.b, cand: ev.cand, pts: ev.pts, aligned: ev.cand.kind === "straight" };
    const fa = it.e.from + "|" + ev.cand.fa;
    const fb = it.e.to   + "|" + ev.cand.fb;
    (this.faceUse[fa] = this.faceUse[fa] || { in: 0, out: 0 }).out += 1;
    (this.faceUse[fb] = this.faceUse[fb] || { in: 0, out: 0 }).in  += 1;
    if (ev.cand.kind === "zv") { r.corr = this.vcorr[ev.cand.corr]; r.corr.members.push({ r }); }
    if (ev.cand.kind === "zh") { r.corr = this.hcorr[ev.cand.corr]; r.corr.members.push({ r }); }
    this.routes.push(r);
  }

  _routeEdges() {
    const items = [];
    (this.edges || []).forEach((e) => {
      const a = this.boxes[e.from], b = this.boxes[e.to];
      if (!a || !b) return;
      this.pairs[e.from + ">" + e.to] = true;
      items.push({ e, a, b });
    });

    const rest = [];
    items.forEach((it) => {
      const st  = this._candidates(it.a, it.b).find((c) => c.kind === "straight");
      const pts = st ? this._pts(st, it.a, it.b) : null;
      if (pts && this._hitCount(pts, it.e.from, it.e.to) === 0) this._commit(it, { cand: st, pts });
      else rest.push(it);
    });

    rest.sort((p, q) => (Math.abs(p.b.cx - p.a.cx) + Math.abs(p.b.cy - p.a.cy)) - (Math.abs(q.b.cx - q.a.cx) + Math.abs(q.b.cy - q.a.cy)));
    rest.forEach((it) => {
      let best = null;
      this._candidates(it.a, it.b).forEach((c) => {
        if (c.kind === "straight") return;
        const ev = this._evaluate(c, it.a, it.b, it.e);
        if (!best || ev.cost < best.cost) best = ev;
      });
      if (best) this._commit(it, best);
    });

    this.routes.forEach((r) => {
      if (r.aligned && this.pairs[r.e.to + ">" + r.e.from]) r.recip = String(r.e.from) < String(r.e.to) ? -1 : 1;
    });
  }

  _headKey(r, end) {
    const pts  = end === "a" ? r.pts : [...r.pts].reverse();
    const f    = end === "a" ? r.cand.fa : r.cand.fb;
    const side = f === "L" || f === "R";
    for (let i = 1; i < pts.length; i++) {
      if (side  && Math.abs(pts[i].y - pts[0].y) > 0.5) return pts[i].y;
      if (!side && Math.abs(pts[i].x - pts[0].x) > 0.5) return pts[i].x;
    }
    const far = pts[pts.length - 1];
    return side ? far.y : far.x;
  }

  _setEnd(r, end, c, v) {
    const pts = r.pts, n = pts.length;
    if (end === "a") { pts[0][c] = v; if (n > 2) pts[1][c] = v; }
    else             { pts[n - 1][c] = v; if (n > 2) pts[n - 2][c] = v; }
  }

  _fanFaces() {
    const groups = {}, reserved = {};

    this.routes.forEach((r) => {
      if (r.aligned) {
        if (r.recip) {
          const off = 7 * r.recip;
          if (r.cand.fa === "L" || r.cand.fa === "R") { r.pts[0].y += off; r.pts[1].y += off; }
          else                                        { r.pts[0].x += off; r.pts[1].x += off; }
        }
        reserved[r.e.from + "|" + r.cand.fa] = true;
        reserved[r.e.to   + "|" + r.cand.fb] = true;
        return;
      }
      const ka = r.e.from + "|" + r.cand.fa;
      const kb = r.e.to   + "|" + r.cand.fb;
      (groups[ka] = groups[ka] || []).push({ r, end: "a", key: this._headKey(r, "a") });
      (groups[kb] = groups[kb] || []).push({ r, end: "b", key: this._headKey(r, "b") });
    });

    Object.entries(groups).forEach(([gk, list]) => {
      list.sort((p, q) => p.key - q.key);
      const face  = gk.slice(gk.indexOf("|") + 1);
      const horiz = face === "L" || face === "R";
      const n = list.length, keepCenter = !!reserved[gk];
      list.forEach((item, i) => {
        const bx   = item.end === "a" ? item.r.a : item.r.b;
        const span = horiz ? bx.h : bx.w;
        const m    = Math.min(horiz ? 13 : 16, span / 2 - 2);
        const frac = n === 1 ? (keepCenter ? 0.72 : 0.5) : (keepCenter ? 0.08 + 0.84 * (i / (n - 1)) : i / (n - 1));
        const v    = (horiz ? bx.y : bx.x) + m + (span - 2 * m) * frac;
        this._setEnd(item.r, item.end, horiz ? "y" : "x", v);
      });
    });
  }

  _assignLanes() {
    const lane = (corr, vert) => {
      if (!corr.members.length) return;
      const members = corr.members.map(({ r }) => {
        const p1 = r.pts[1], p2 = r.pts[2];
        const lo  = vert ? Math.min(p1.y, p2.y) : Math.min(p1.x, p2.x);
        const hi  = vert ? Math.max(p1.y, p2.y) : Math.max(p1.x, p2.x);
        const key = vert ? r.pts[0].x + r.pts[3].x : r.pts[0].y + r.pts[3].y;
        return { r, lo, hi, key };
      });

      members.sort((p, q) => p.lo - q.lo);
      const lanes = [];
      members.forEach((m) => {
        let L = lanes.find((l) => l.hi <= m.lo - 10);
        if (!L) { L = { items: [], hi: -Infinity }; lanes.push(L); }
        L.items.push(m); L.hi = Math.max(L.hi, m.hi);
      });

      lanes.forEach((l) => { l.key = l.items.reduce((s, m) => s + m.key, 0) / l.items.length; });
      lanes.sort((p, q) => p.key - q.key);
      const mid  = (corr.lo + corr.hi) / 2;
      const step = lanes.length > 1 ? Math.min(11, (corr.hi - corr.lo - 8) / (lanes.length - 1)) : 0;
      lanes.forEach((l, k) => {
        const pos = Math.max(corr.lo + 3, Math.min(corr.hi - 3, mid + (k - (lanes.length - 1) / 2) * step));
        const c   = vert ? "x" : "y";
        l.items.forEach((m) => { m.r.pts[1][c] = pos; m.r.pts[2][c] = pos; });
      });
    };

    this.vcorr.forEach((c) => lane(c, true));
    this.hcorr.forEach((c) => lane(c, false));
  }

  _nudgeSeg(s, delta) {
    const r = s.r, n = r.pts.length;
    if (n === 2) return false;
    const c = s.horiz ? "y" : "x";

    if (s.i === 1 || s.i === n - 1) {
      const end  = s.i === 1 ? "a" : "b";
      const f    = end === "a" ? r.cand.fa : r.cand.fb;
      const side = f === "L" || f === "R";
      if (side !== s.horiz) return false;
      const bx = end === "a" ? r.a : r.b;
      const lo = (s.horiz ? bx.y : bx.x) + 8;
      const hi = (s.horiz ? bx.y + bx.h : bx.x + bx.w) - 8;
      const pt = end === "a" ? r.pts[0] : r.pts[n - 1];
      const v  = pt[c] + delta;
      if (v < lo || v > hi) return false;
      this._setEnd(r, end, c, v);
      return true;
    }

    if (r.corr) {
      const v = r.pts[1][c] + delta;
      if (v < r.corr.lo + 3 || v > r.corr.hi - 3) return false;
      r.pts[1][c] = v; r.pts[2][c] = v;
      return true;
    }
    return false;
  }

  _separate() {
    for (let pass = 0; pass < 4; pass++) {
      let moved = false;
      const segs = [];
      this.routes.forEach((r) => {
        for (let i = 1; i < r.pts.length; i++) {
          const a = r.pts[i - 1], b = r.pts[i];
          const horiz = Math.abs(a.y - b.y) < 0.5, vert = Math.abs(a.x - b.x) < 0.5;
          if (horiz === vert) continue;
          segs.push({ r, i, horiz,
                      lo: horiz ? Math.min(a.x, b.x) : Math.min(a.y, b.y),
                      hi: horiz ? Math.max(a.x, b.x) : Math.max(a.y, b.y),
                      perp: horiz ? a.y : a.x });
        }
      });

      for (let i = 0; i < segs.length; i++) {
        for (let j = i + 1; j < segs.length; j++) {
          const s1 = segs[i], s2 = segs[j];
          if (s1.r === s2.r || s1.horiz !== s2.horiz) continue;
          const gap = Math.abs(s1.perp - s2.perp);
          if (gap >= 8 || Math.min(s1.hi, s2.hi) - Math.max(s1.lo, s2.lo) < 10) continue;
          const dir = s2.perp >= s1.perp ? 1 : -1;
          const d   = 8.5 - gap;
          if (this._nudgeSeg(s2, dir * d))       { s2.perp += dir * d; moved = true; }
          else if (this._nudgeSeg(s1, -dir * d)) { s1.perp -= dir * d; moved = true; }
        }
      }
      if (!moved) break;
    }
  }

  _dedupe() {
    const taken = {};
    const key = (id, pt) => id + "|" + Math.round(pt.x) + "|" + Math.round(pt.y);
    this.routes.forEach((r) => {
      if (r.aligned) { taken[key(r.e.from, r.pts[0])] = true; taken[key(r.e.to, r.pts[r.pts.length - 1])] = true; }
    });
    this.routes.forEach((r) => {
      if (r.aligned) return;
      [["a", r.e.from, r.cand.fa, r.pts[0]], ["b", r.e.to, r.cand.fb, r.pts[r.pts.length - 1]]].forEach(([end, id, f, pt]) => {
        const c = (f === "L" || f === "R") ? "y" : "x";
        let guard = 0;
        while (taken[key(id, pt)] && guard < 24) { this._setEnd(r, end, c, pt[c] + 6); guard++; }
        taken[key(id, pt)] = true;
      });
    });
  }

  _geoms() {
    return this.routes.map((r) => {
      const pts = r.pts;
      let d = `M ${pts[0].x} ${pts[0].y}`;
      for (let i = 1; i < pts.length; i++) d += ` L ${pts[i].x} ${pts[i].y}`;

      let bi = 1, bl = -1;
      for (let i = 1; i < pts.length; i++) {
        const L = Math.abs(pts[i].x - pts[i - 1].x) + Math.abs(pts[i].y - pts[i - 1].y);
        if (L > bl) { bl = L; bi = i; }
      }

      return { e: r.e, from: r.e.from, to: r.e.to, fcol: r.a.col, tcol: r.b.col,
               d, mx: (pts[bi - 1].x + pts[bi].x) / 2, my: (pts[bi - 1].y + pts[bi].y) / 2 };
    });
  }

  route() {
    this._bands();
    this._corridors();
    this._routeEdges();
    this._fanFaces();
    this._assignLanes();
    this._separate();
    this._dedupe();
    return this._geoms();
  }
}

class RepoMapView {
  constructor(root) {
    this.root     = root;
    this.folders  = [];
    this.folder   = null;
    this.diagram  = null;
    this.loaded   = false;
    this.selNode  = null;
    this.ro       = null;
    this.rafId    = null;
    this.wireEls  = [];
    this.labelEls = [];
    this.trace    = { on: false, col: -1, timer: null };

    this.ROLE_COLORS = {
      entry        : "#6d28d9",
      orchestrator : "#1d4fd8",
      config       : "#b45309",
      transform    : "#0e7490",
      model        : "#be185d",
      data         : "#15803d",
      io           : "#0f766e",
      metric       : "#c2410c",
      external     : "#64748b",
    };
    this.ROLE_LABELS = {
      entry        : "Entry",
      orchestrator : "Orchestrator",
      config       : "Config",
      transform    : "Transform",
      model        : "Model",
      data         : "Data",
      io           : "I/O",
      metric       : "Metric",
      external     : "External",
    };
    this.ROLE_ORDER = ["entry", "orchestrator", "config", "transform", "model", "data", "io", "metric", "external"];
  }

  async enter() {
    if (!this.loaded) { await this.load(); return; }
    this._redraw();
  }

  async load() {
    const data = await Api.get("/api/repomap");
    if (!data || data.error) { this._empty("Backend unreachable."); return; }
    this.folders = data.folders || [];
    this.loaded  = true;
    if (!this.folders.length) { this._empty("No repo map data yet."); return; }
    this._buildShell();
    this._selectFolder(this.folders[0].folder);
  }

  _empty(msg) {
    this.root.innerHTML = `<div class="rm-empty">${SharedCharts.esc(msg)}</div>`;
  }

  _buildShell() {
    this.root.innerHTML = "";
    this.root.classList.add("rm");

    this.foldersEl = document.createElement("div");
    this.foldersEl.className = "rm__folders";
    this.foldersEl.setAttribute("role", "tablist");
    this.foldersEl.setAttribute("aria-label", "Subsystems");
    this.folders.forEach((f) => {
      const b = document.createElement("button");
      b.className   = "rm-folder";
      b.dataset.key = f.folder;
      b.setAttribute("role", "tab");
      b.innerHTML   = `<span class="rm-folder__name">${SharedCharts.esc(f.title)}</span><span class="rm-folder__n">${f.diagrams.length}</span>`;
      b.addEventListener("click", () => this._selectFolder(f.folder));
      this.foldersEl.appendChild(b);
    });

    this.panel = document.createElement("div");
    this.panel.className = "rm__panel";
    this.panel.innerHTML = `
      <div class="rm__head">
        <div class="rm__subtabs" role="tablist" aria-label="Stages"></div>
        <div class="rm__tools">
          <button class="rm-tool rm-tool--labels" type="button" title="Show every data-exchange label at once (otherwise hover a class to reveal its labels)">
            <span class="rm-tool__ic">&#8801;</span><span class="rm-tool__lb">Labels</span>
          </button>
          <button class="rm-tool rm-tool--trace" type="button" title="Animate the data flow through the pipeline">
            <span class="rm-tool__ic">&#9654;</span><span class="rm-tool__lb">Trace flow</span>
          </button>
        </div>
      </div>
      <div class="rm__title">
        <h3 class="rm__stage-name"></h3>
        <a class="rm__entry" target="_blank" rel="noopener"></a>
      </div>
      <div class="rm__stage">
        <div class="rm__legend"></div>
        <div class="rm-graph">
          <div class="rm-canvas">
            <svg class="rm-wires" aria-hidden="true"><defs>
              <marker id="rm-arrow" viewBox="0 0 10 10" refX="8.5" refY="5" markerWidth="6.5" markerHeight="6.5" orient="auto-start-reverse">
                <path d="M0,1 L9,5 L0,9" fill="none" stroke="context-stroke" stroke-width="1.5"></path>
              </marker></defs>
            </svg>
            <div class="rm-cols"></div>
            <div class="rm-labels"></div>
          </div>
        </div>
      </div>
      <div class="rm__ledger"></div>`;

    this.subtabsEl = this.panel.querySelector(".rm__subtabs");
    this.labelsBtn = this.panel.querySelector(".rm-tool--labels");
    this.traceBtn  = this.panel.querySelector(".rm-tool--trace");
    this.nameEl    = this.panel.querySelector(".rm__stage-name");
    this.entryEl   = this.panel.querySelector(".rm__entry");
    this.legendEl  = this.panel.querySelector(".rm__legend");
    this.graphEl   = this.panel.querySelector(".rm-graph");
    this.canvasEl  = this.panel.querySelector(".rm-canvas");
    this.wiresEl   = this.panel.querySelector(".rm-wires");
    this.colsEl    = this.panel.querySelector(".rm-cols");
    this.labelsEl  = this.panel.querySelector(".rm-labels");
    this.ledgerEl  = this.panel.querySelector(".rm__ledger");

    this.traceBtn.addEventListener("click", () => this._toggleTrace());
    this.labelsBtn.addEventListener("click", () => {
      const on = this.canvasEl.classList.toggle("rm-showlabels");
      this.labelsBtn.classList.toggle("is-on", on);
    });

    this.root.appendChild(this.foldersEl);
    this.root.appendChild(this.panel);

    if (window.ResizeObserver) {
      this.ro = new ResizeObserver(() => this._scheduleWires());
      this.ro.observe(this.graphEl);
    }
    window.addEventListener("resize", () => this._scheduleWires());
  }

  _selectFolder(key) {
    this.folder = this.folders.find((f) => f.folder === key) || this.folders[0];
    [...this.foldersEl.children].forEach((b) => b.classList.toggle("is-active", b.dataset.key === this.folder.folder));

    this.subtabsEl.innerHTML = "";
    this.folder.diagrams.forEach((d) => {
      const b = document.createElement("button");
      b.className   = "rm-sub";
      b.dataset.key = d.key;
      b.textContent = d.stage;
      b.setAttribute("role", "tab");
      b.addEventListener("click", () => this._selectDiagram(d.key));
      this.subtabsEl.appendChild(b);
    });

    this._selectDiagram(this.folder.diagrams[0].key);
  }

  _selectDiagram(key) {
    this._stopTrace();
    this.diagram = this.folder.diagrams.find((d) => d.key === key) || this.folder.diagrams[0];
    this.selNode = null;
    [...this.subtabsEl.children].forEach((b) => b.classList.toggle("is-active", b.dataset.key === this.diagram.key));

    this.nameEl.textContent  = this.diagram.title;

    if (this.diagram.entry) {
      this.entryEl.style.display = "";
      this.entryEl.textContent   = this.diagram.entry;
      this.entryEl.href          = "#/scripts";
    } else {
      this.entryEl.style.display = "none";
    }

    this._buildLegend();
    this._buildNodes();
    this._buildLedger();
    this._redraw();
  }

  _buildLegend() {
    this.legendEl.innerHTML = "";
    const present = new Set(this.diagram.nodes.map((n) => n.role));
    this.ROLE_ORDER.filter((r) => present.has(r)).forEach((role) => {
      const item = document.createElement("span");
      item.className = "rm-leg";
      item.style.setProperty("--role", this.ROLE_COLORS[role]);
      item.innerHTML = `<i></i>${SharedCharts.esc(this.ROLE_LABELS[role])}`;
      this.legendEl.appendChild(item);
    });
  }

  _buildNodes() {
    this.colsEl.innerHTML   = "";
    this.labelsEl.innerHTML = "";
    this.nodeById = {};

    const ncol = this.diagram.ncol || (this.diagram.nodes.reduce((m, n) => Math.max(m, n.col || 0), 0) + 1);
    const nrow = this.diagram.nrow || (this.diagram.nodes.reduce((m, n) => Math.max(m, n.row || 0), 0) + 1);
    this.colsEl.style.setProperty("--ncol", ncol);
    this.colsEl.style.setProperty("--nrow", nrow);
    this.colsEl.style.setProperty("--rm-hgap", ncol >= 6 ? "40px" : "64px");

    this.diagram.nodes.forEach((n) => {
      const el = document.createElement("div");
      el.className   = "rm-node rm-node--" + n.role;
      el.dataset.id  = n.id;
      el.dataset.col = String(n.col || 0);
      el.dataset.row = String(n.row || 0);
      el.style.gridColumn = String((n.col || 0) + 1);
      el.style.gridRow    = String((n.row || 0) + 1);
      el.style.setProperty("--role", this.ROLE_COLORS[n.role] || this.ROLE_COLORS.external);

      const io = [];
      if (n.writes && n.writes.length) io.push(`<span class="rm-io rm-io--w" title="writes ${SharedCharts.esc(n.writes.join(", "))}">out ${n.writes.length}</span>`);
      if (n.reads && n.reads.length)   io.push(`<span class="rm-io rm-io--r" title="reads ${SharedCharts.esc(n.reads.join(", "))}">in ${n.reads.length}</span>`);

      el.innerHTML =
        `<div class="rm-node__top"><span class="rm-node__role">${SharedCharts.esc(this.ROLE_LABELS[n.role] || n.role)}</span><span class="rm-node__io">${io.join("")}</span></div>` +
        `<h4 class="rm-node__name">${SharedCharts.esc(n.label)}</h4>` +
        `<p class="rm-node__fn" title="${SharedCharts.esc(n.fn)}">${SharedCharts.esc(n.fn)}</p>` +
        `<code class="rm-node__mod">${SharedCharts.esc(n.module)}</code>`;

      el.addEventListener("click", () => this._focusNode(n.id));
      el.addEventListener("mouseenter", () => this._hoverNode(n.id, true));
      el.addEventListener("mouseleave", () => this._hoverNode(n.id, false));
      this.colsEl.appendChild(el);
      this.nodeById[n.id] = el;
    });
  }

  _buildLedger() {
    const arts = this.diagram.artifacts || [];
    if (!arts.length) { this.ledgerEl.innerHTML = ""; return; }

    const rows = arts.map((a) => {
      const cross = a.scope === "cross" ? `<span class="rm-tag rm-tag--cross">cross-pipeline</span>` : "";
      const cons  = (a.consumers || []).map((c) => SharedCharts.esc(c)).join(", ") || "&mdash;";
      return `<tr data-producer="${SharedCharts.esc(a.producer)}" data-consumers="${SharedCharts.esc((a.consumers || []).join("|"))}">
        <td class="rm-led__name"><code>${SharedCharts.esc(a.name)}</code>${cross}</td>
        <td class="rm-led__fmt">${SharedCharts.esc(a.fmt || "")}</td>
        <td class="rm-led__by">${SharedCharts.esc(a.producer)}</td>
        <td class="rm-led__to">${cons}</td>
        <td class="rm-led__desc">${SharedCharts.esc(a.desc || "")}</td>
      </tr>`;
    }).join("");

    this.ledgerEl.classList.remove("is-open");
    this.ledgerEl.innerHTML = `
      <button class="rm-led__toggle" type="button" aria-expanded="false">
        <span class="rm-led__chev">&#9656;</span>
        <span class="rm-led__lbl">Artifact ledger</span>
        <span class="rm-led__count">${arts.length}</span>
        <span class="rm-led__sub">what each stage saves and who reads it</span>
      </button>
      <div class="rm-led__body" hidden>
        <div class="rm-led__scroll"><table class="rm-led">
          <thead><tr><th>Artifact</th><th>Format</th><th>Written by</th><th>Read by</th><th>Holds</th></tr></thead>
          <tbody>${rows}</tbody>
        </table></div>
      </div>`;

    const toggle = this.ledgerEl.querySelector(".rm-led__toggle");
    const body   = this.ledgerEl.querySelector(".rm-led__body");
    toggle.addEventListener("click", () => {
      const open = body.hasAttribute("hidden");
      if (open) body.removeAttribute("hidden"); else body.setAttribute("hidden", "");
      toggle.setAttribute("aria-expanded", String(open));
      this.ledgerEl.classList.toggle("is-open", open);
    });

    this.ledgerEl.querySelectorAll("tbody tr").forEach((tr) => {
      tr.addEventListener("mouseenter", () => this._highlightArtifact(tr));
      tr.addEventListener("mouseleave", () => this._clearHighlight());
    });
  }

  _focusNode(id) {
    if (this.selNode === id) { this.selNode = null; this._clearHighlight(); return; }
    this.selNode = id;
    const incident = new Set([id]);
    (this.diagram.edges || []).forEach((e) => {
      if (e.from === id || e.to === id) { incident.add(e.from); incident.add(e.to); }
    });
    this.canvasEl.classList.add("is-focused");
    Object.entries(this.nodeById).forEach(([nid, el]) => el.classList.toggle("is-dim", !incident.has(nid)));
    this.wireEls.forEach((w) => {
      const on = w.from === id || w.to === id;
      w.base.classList.toggle("is-lit", on);
      w.base.classList.toggle("is-dim", !on);
      w.flow.classList.toggle("is-dim", !on);
    });
    this.labelEls.forEach((l) => {
      const on = l.from === id || l.to === id;
      l.el.classList.toggle("is-lit", on);
      l.el.classList.toggle("is-dim", !on);
    });
  }

  _hoverNode(id, on) {
    if (this.selNode || this.trace.on) return;
    this.labelEls.forEach((l) => {
      if (l.from === id || l.to === id) l.el.classList.toggle("is-show", on);
    });
    this.wireEls.forEach((w) => {
      if (w.from === id || w.to === id) w.base.classList.toggle("is-lit", on);
    });
  }

  _highlightArtifact(tr) {
    const names = new Set();
    if (tr.dataset.producer) names.add(tr.dataset.producer);
    (tr.dataset.consumers ? tr.dataset.consumers.split("|") : []).forEach((n) => names.add(n));
    this.canvasEl.classList.add("is-focused");
    this.diagram.nodes.forEach((n) => {
      const hit = names.has(n.label) || names.has(n.id);
      const el  = this.nodeById[n.id];
      if (el) el.classList.toggle("is-dim", !hit);
    });
  }

  _clearHighlight() {
    if (this.selNode) return;
    this.canvasEl.classList.remove("is-focused");
    Object.values(this.nodeById).forEach((el) => el.classList.remove("is-dim"));
    this.wireEls.forEach((w) => { w.base.classList.remove("is-lit", "is-dim"); w.flow.classList.remove("is-dim"); });
    this.labelEls.forEach((l) => l.el.classList.remove("is-lit", "is-dim", "is-show"));
  }

  _scheduleWires() {
    if (this.rafId) cancelAnimationFrame(this.rafId);
    this.rafId = requestAnimationFrame(() => this._drawWires());
  }

  _redraw() {
    requestAnimationFrame(() => requestAnimationFrame(() => this._drawWires()));
  }

  _drawWires() {
    if (!this.diagram || !this.canvasEl) return;
    const w = this.canvasEl.offsetWidth;
    const h = this.canvasEl.offsetHeight;
    if (!w || !h) return;

    this.wiresEl.setAttribute("width", w);
    this.wiresEl.setAttribute("height", h);
    this.wiresEl.setAttribute("viewBox", `0 0 ${w} ${h}`);

    const defs = this.wiresEl.querySelector("defs");
    this.wiresEl.innerHTML = "";
    this.wiresEl.appendChild(defs);
    this.labelsEl.innerHTML = "";
    this.wireEls  = [];
    this.labelEls = [];

    const crect = this.canvasEl.getBoundingClientRect();
    const boxes = {};
    this.diagram.nodes.forEach((n) => {
      const el = this.nodeById[n.id];
      if (!el) return;
      const r = el.getBoundingClientRect();
      boxes[n.id] = { x: r.left - crect.left, y: r.top - crect.top, w: r.width, h: r.height,
                      col: Number(el.dataset.col), row: Number(el.dataset.row) };
    });
    const roleOf = (id) => { const n = this.diagram.nodes.find((nn) => nn.id === id); return n ? n.role : "external"; };

    const bounds = { w: Math.max(w, this.colsEl.scrollWidth), h: Math.max(h, this.colsEl.scrollHeight) };
    const routes = new WireRouter(boxes, this.diagram.edges || [], bounds).route();

    routes.forEach((r) => {
      const color = this.ROLE_COLORS[roleOf(r.from)] || this.ROLE_COLORS.external;

      const base = this._path(r.d, "rm-wire", color);
      base.setAttribute("marker-end", "url(#rm-arrow)");
      const flow = this._path(r.d, "rm-flow", color);
      this.wiresEl.appendChild(base);
      this.wiresEl.appendChild(flow);
      this.wireEls.push({ base, flow, from: r.from, to: r.to, fcol: r.fcol, tcol: r.tcol });

      if (r.e.label) {
        const lab = document.createElement("span");
        lab.className   = "rm-elabel rm-elabel--" + (r.e.kind || "data");
        lab.style.left  = r.mx + "px";
        lab.style.top   = r.my + "px";
        lab.textContent = r.e.label;
        this.labelsEl.appendChild(lab);
        this.labelEls.push({ el: lab, from: r.from, to: r.to, tcol: r.tcol });
      }
    });

    if (this.selNode) { const s = this.selNode; this.selNode = null; this._focusNode(s); }
  }

  _path(d, cls, color) {
    const p = document.createElementNS("http://www.w3.org/2000/svg", "path");
    p.setAttribute("d", d);
    p.setAttribute("class", cls);
    p.setAttribute("stroke", color);
    return p;
  }

  _toggleTrace() {
    if (this.trace.on) { this._stopTrace(); return; }
    if (window.REDUCED_MOTION) { this._revealAll(); return; }
    this.trace.on  = true;
    this.trace.col = -1;
    this.traceBtn.classList.add("is-on");
    this.traceBtn.querySelector(".rm-tool__ic").innerHTML = "&#10073;&#10073;";
    this.traceBtn.querySelector(".rm-tool__lb").textContent = "Stop";
    this.canvasEl.classList.add("is-tracing");
    Object.values(this.nodeById).forEach((el) => el.classList.remove("is-lit", "is-active"));
    this.wireEls.forEach((w) => { w.flow.classList.remove("is-flow"); w.base.classList.remove("is-lit"); });
    this._traceStep();
  }

  _traceStep() {
    const maxCol = this.diagram.nodes.reduce((m, n) => Math.max(m, n.col || 0), 0);
    this.trace.col += 1;
    const c = this.trace.col;

    Object.values(this.nodeById).forEach((el) => el.classList.remove("is-active"));
    this.diagram.nodes.forEach((n) => {
      if ((n.col || 0) <= c) this.nodeById[n.id].classList.add("is-lit");
      if ((n.col || 0) === c) this.nodeById[n.id].classList.add("is-active");
    });
    this.wireEls.forEach((w) => {
      const flowing = w.tcol <= c && w.fcol < c + 1;
      w.flow.classList.toggle("is-flow", flowing);
      w.base.classList.toggle("is-lit", flowing);
    });
    this.labelEls.forEach((l) => l.el.classList.toggle("is-lit", l.tcol <= c));

    if (c >= maxCol) { this.trace.timer = setTimeout(() => this._stopTrace(), 1500); return; }
    this.trace.timer = setTimeout(() => this._traceStep(), 840);
  }

  _revealAll() {
    Object.values(this.nodeById).forEach((el) => el.classList.add("is-lit"));
    this.wireEls.forEach((w) => w.base.classList.add("is-lit"));
  }

  _stopTrace() {
    this.trace.on = false;
    if (this.trace.timer) { clearTimeout(this.trace.timer); this.trace.timer = null; }
    if (this.traceBtn) {
      this.traceBtn.classList.remove("is-on");
      this.traceBtn.querySelector(".rm-tool__ic").innerHTML = "&#9654;";
      this.traceBtn.querySelector(".rm-tool__lb").textContent = "Trace flow";
    }
    if (!this.canvasEl) return;
    this.canvasEl.classList.remove("is-tracing");
    Object.values(this.nodeById || {}).forEach((el) => el.classList.remove("is-lit", "is-active"));
    this.wireEls.forEach((w) => { w.flow.classList.remove("is-flow"); w.base.classList.remove("is-lit"); });
    this.labelEls.forEach((l) => l.el.classList.remove("is-lit"));
  }

}

window.RepoMapView = RepoMapView;
