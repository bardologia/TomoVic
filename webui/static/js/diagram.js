"use strict";

class ModelDiagram {
  static C = {
    accent: "#1d4fd8",
    accent2: "#0f766e",
    boxStroke: "#1d4fd8",
    boxFill: "rgba(29,79,216,0.06)",
    ioStroke: "#9aa196",
    ioFill: "#ffffff",
    flow: "rgba(125,133,139,0.85)",
    skip: "rgba(15,118,110,0.55)",
  };

  static render(model) {
    return this.build(model).network;
  }

  static build(model) {
    const bp = this._blueprint(model);
    const blocks = {};
    bp.blocks.forEach((b) => { blocks[b.id] = b; });
    const network =
      `<figure class="dgm-net"><div class="dgm-frame dgm-frame--net">${bp.network}</div>` +
      `<figcaption class="dgm-hint">Click any block to zoom into its operations</figcaption></figure>`;
    return { network, blocks };
  }

  static blockSvg(def) {
    return this._block(def);
  }

  static KEYSPEC = {
    unet_skip:     { skipKind: "resmaxpool", type: "unet" },
    convnext_unet: { skipKind: "convnext", type: "unet" },
    dense_unet:    { skipKind: "dense",    type: "unet" },
    multires_unet: { skipKind: "respath",  type: "unet" },
    u2net:         { skipKind: "rsu",      type: "unet" },
    nafnet:        { skipKind: "nafnet",   type: "unet" },
    segformer:     { skipKind: "pyramid",  type: "segformer" },
    deeplabv3plus: { skipKind: "lowlevel", type: "deeplab" },
    hrnet:         { skipKind: "branch",   type: "hrnet" },
    fpn:           { skipKind: "lateral",  type: "fpn" },
    pixel_mlp:     { skipKind: "none",     type: "stack" },
    local_cnn:     { skipKind: "none",     type: "stack" },
  };

  static spec(model) {
    const skip = (model.skip || "").toLowerCase();
    let skipKind = "concat";
    if (skip.includes("attention")) skipKind = "attention";
    else if (skip.includes("nested")) skipKind = "nested";
    else if (skip.includes("additive")) skipKind = "additive";
    else if (skip.includes("residual")) skipKind = "residual";
    else if (skip.includes("token")) skipKind = "tokens";
    const head = (model.head || "").toLowerCase();
    let heads = 1;
    if (head.includes("3 ")) heads = 3;
    else if (head.includes("k ")) heads = "K";
    const isT = (model.family || "").toLowerCase().startsWith("transformer");
    let type = isT ? "transformer" : "unet";

    const over = this.KEYSPEC[model.key];
    if (over) { skipKind = over.skipKind; type = over.type; }

    const actMap = { relu: "ReLU", leaky_relu: "LeakyReLU", gelu: "GELU", silu: "SiLU", simplegate: "SimpleGate" };
    const normMap = { batch: "BatchNorm", instance: "InstanceNorm", group: "GroupNorm", layer: "LayerNorm", layernorm: "LayerNorm", l2: "L2 Norm", none: null };
    const act = (model.activation || "relu").toLowerCase();
    const norm = (model.normalization || "batch").toLowerCase();
    return { skipKind, heads, type, key: model.key, act: actMap[act] || "ReLU", norm: normMap[norm] !== undefined ? normMap[norm] : "BatchNorm" };
  }

  /* ---------- primitives ---------- */

  static _defs() {
    const C = this.C;
    return (
      `<defs>` +
      `<marker id="tipm" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="5" markerHeight="5" orient="auto-start-reverse"><path d="M0,2 L8,5 L0,8" fill="none" stroke="${C.flow}" stroke-width="1.4"/></marker>` +
      `<marker id="tip2" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="5" markerHeight="5" orient="auto-start-reverse"><path d="M0,2 L8,5 L0,8" fill="none" stroke="${C.skip}" stroke-width="1.4"/></marker>` +
      `</defs>`
    );
  }

  static _node(x, y, w, h, label, sub, variant, t, pick, subId, subT, flow) {
    const C = this.C;
    const isLat  = variant === "latent";
    const isLoss = variant === "loss";
    const isProc = variant === "proc";
    const stroke = variant === "io" ? C.ioStroke : isLat ? C.accent : isLoss ? C.accent2 : isProc ? "#9aa196" : C.boxStroke;
    const fill   = variant === "io" ? C.ioFill   : isLat ? C.accent : isLoss ? "rgba(15,118,110,0.10)" : isProc ? "rgba(125,133,139,0.07)" : C.boxFill;
    const sw     = isLat ? 1.7 : 1.4;
    const cx = x + w / 2;
    const delay = t.toFixed(2);
    const mainStyle = isLat ? ` style="fill:#ffffff"` : "";
    const subParts = [];
    if (subT != null) subParts.push(`animation-delay:${subT.toFixed(2)}s`);
    if (isLat) subParts.push("fill:rgba(255,255,255,0.86)");
    const subStyle = subParts.length ? ` style="${subParts.join(";")}"` : "";
    let text;
    if (sub) {
      text =
        `<text x="${cx}" y="${y + h / 2 - 3}" class="dgm-t"${mainStyle}>${label}</text>` +
        `<text x="${cx}" y="${y + h / 2 + 11}" class="dgm-s"${subStyle}>${sub}</text>`;
    } else {
      text = `<text x="${cx}" y="${y + h / 2 + 4}" class="dgm-t"${mainStyle}>${label}</text>`;
    }
    let cls = "dgm-block", data = "";
    if (pick) {
      cls += " dgm-pick";
      data = ` data-block="${pick}"`;
      if (flow) data += ` data-flow="${flow}"`;
    }
    else if (subId) { cls += " dgm-pick dgm-sub"; data = ` data-subblock="${subId}"`; }
    return (
      `<g class="${cls}"${data} style="animation-delay:${delay}s">` +
      `<rect x="${x}" y="${y}" width="${w}" height="${h}" rx="7" fill="${fill}" stroke="${stroke}" stroke-width="${sw}"/>` +
      text +
      `</g>`
    );
  }

  static _profileGlyph(cx, cy, opts, t) {
    const C = opts.out ? this.C.accent2 : this.C.accent;
    const W = 74, H = 48;
    const x = cx - W / 2, y = cy - H / 2;
    const delay = t.toFixed(2);
    const pad = 9;
    const x0 = x + pad, x1 = x + W - pad, baseY = y + H - 9, amp = H - 20;
    const pts = [];
    const N = 28;
    for (let i = 0; i <= N; i++) {
      const u = i / N;
      const v = Math.exp(-Math.pow((u - 0.40) / 0.15, 2)) + 0.55 * Math.exp(-Math.pow((u - 0.74) / 0.10, 2));
      const px = x0 + (x1 - x0) * u;
      const py = baseY - Math.min(v, 1.05) * amp;
      pts.push(`${px.toFixed(1)},${py.toFixed(1)}`);
    }
    const card = `<rect x="${x}" y="${y}" width="${W}" height="${H}" rx="6" fill="${this.C.ioFill}" stroke="${C}" stroke-width="1.5"/>`;
    const axis = `<line x1="${x0}" y1="${baseY}" x2="${x1}" y2="${baseY}" stroke="${C}" stroke-width="0.6" opacity="0.45"/>`;
    const wave = `<polyline points="${pts.join(' ')}" fill="none" stroke="${C}" stroke-width="1.7"/>`;
    const lab =
      `<text x="${cx}" y="${y - 14}" class="dgm-t">${opts.label}</text>` +
      `<text x="${cx}" y="${y - 3}" class="dgm-s">${opts.sub}</text>`;
    return `<g class="dgm-block" style="animation-delay:${delay}s">${card}${axis}${wave}${lab}</g>`;
  }

  static _gridStack(cx, cy, opts, t) {
    const C = opts.out ? this.C.accent2 : this.C.accent;
    const S = 46;
    const off = 4;
    const delay = t.toFixed(2);
    let layers = "";
    for (let i = 3; i >= 1; i--) {
      const lx = cx - S / 2 + i * off;
      const ly = cy - S / 2 - i * off;
      layers += `<rect x="${lx}" y="${ly}" width="${S}" height="${S}" rx="3" fill="${this.C.ioFill}" stroke="${C}" stroke-width="1" opacity="${0.3 + (3 - i) * 0.12}"/>`;
    }
    const fx = cx - S / 2;
    const fy = cy - S / 2;
    let grid = `<rect x="${fx}" y="${fy}" width="${S}" height="${S}" rx="3" fill="${this.C.ioFill}" stroke="${C}" stroke-width="1.5"/>`;
    for (let k = 1; k < 6; k++) {
      const p = (S / 6) * k;
      grid += `<line x1="${fx + p}" y1="${fy}" x2="${fx + p}" y2="${fy + S}" stroke="${C}" stroke-width="0.5" opacity="0.4"/>`;
      grid += `<line x1="${fx}" y1="${fy + p}" x2="${fx + S}" y2="${fy + p}" stroke="${C}" stroke-width="0.5" opacity="0.4"/>`;
    }
    const lab =
      `<text x="${cx}" y="${cy - S / 2 - 30}" class="dgm-t">${opts.label}</text>` +
      `<text x="${cx}" y="${cy - S / 2 - 17}" class="dgm-s">${opts.sub}</text>`;
    const attr = opts.pick ? ` data-block="${opts.pick}" class="dgm-block dgm-pick"` : ` class="dgm-block"`;
    return `<g${attr} style="animation-delay:${delay}s">${layers}${grid}${lab}</g>`;
  }

  static _sum(cx, cy, sym, t, r) {
    const C = this.C;
    const rad = r || 13;
    const delay = t.toFixed(2);
    return (
      `<g class="dgm-block" style="animation-delay:${delay}s">` +
      `<circle cx="${cx}" cy="${cy}" r="${rad}" fill="${C.ioFill}" stroke="${C.accent2}" stroke-width="1.4"/>` +
      `<text x="${cx}" y="${cy + 4.5}" class="dgm-sum">${sym}</text></g>`
    );
  }

  static _arrow(x1, y1, x2, y2, second, idx) {
    const C = this.C;
    const base = second ? C.skip : C.flow;
    const lit = second ? C.accent2 : C.accent;
    const delay = (idx * 0.025 + 0.1).toFixed(2);
    return (
      `<line class="dgm-link" style="animation-delay:${delay}s" x1="${x1}" y1="${y1}" x2="${x2}" y2="${y2}" stroke="${base}" stroke-width="1.4"/>` +
      `<line class="dgm-flow" x1="${x1}" y1="${y1}" x2="${x2}" y2="${y2}" stroke="${lit}"/>`
    );
  }

  static _path(points, second, t) {
    const C = this.C;
    const base = second ? C.skip : C.flow;
    const lit = second ? C.accent2 : C.accent;
    const delay = t.toFixed(2);
    const flowDelay = (t + 0.3).toFixed(2);
    const cls = second ? "dgm-skip" : "dgm-link";
    const d = points.map((p) => `${p[0]},${p[1]}`).join(" ");
    return (
      `<polyline class="${cls}" style="animation-delay:${delay}s" points="${d}" fill="none" stroke="${base}" stroke-width="1.4"/>` +
      `<polyline class="dgm-flow" style="animation-delay:0s,${flowDelay}s" points="${d}" fill="none" stroke="${lit}"/>`
    );
  }

  static _label(x, y, text, second, anchor, t) {
    const parts = [];
    if (anchor) parts.push(`text-anchor:${anchor}`);
    if (t != null) parts.push(`animation-delay:${t.toFixed(2)}s`);
    const a = parts.length ? ` style="${parts.join(";")}"` : "";
    return `<text x="${x}" y="${y}"${a} class="${second ? "dgm-lbl" : "dgm-lbl dgm-lbl--flow"}">${text}</text>`;
  }

  /* ---------- network (orthogonal U) ---------- */

  static _network(g) {
    const W = 800;
    const mid = W / 2;
    const vOff = { 1: 240, 2: 205, 3: 170, 4: 135 };
    const rowY = (r) => (r === 0 ? 66 : 210 + (r - 1) * 76);
    const bw = 156, bh = 52, bbw = 188, gw = 50;

    const box = {};
    g.nodes.forEach((n) => {
      const grid = n.type === "grid";
      const w = grid ? gw : n.col === "center" ? bbw : bw;
      const h = grid ? gw : bh;
      const off = vOff[n.row] || vOff[1];
      const cx = n.col === "center" ? mid : n.col === "left" ? mid - off : mid + off;
      const cy = n.yPix != null ? n.yPix : rowY(n.row);
      box[n.id] = { x: cx - w / 2, y: cy - h / 2, w, h, cx, cy };
    });

    const ord = {};
    g.nodes.forEach((n, i) => { ord[n.id] = i; });
    const step = 0.14;
    const settle = g.nodes.length * step + 0.2;

    let edges = "";
    let labels = "";
    let sk = 0;
    g.edges.forEach((e) => {
      const a = box[e.from];
      const b = box[e.to];
      const second = e.kind === "skip";
      const t = second ? settle + 0.7 + sk++ * 0.12 : Math.max(ord[e.to] * step - 0.07, 0.05);
      let pts;
      if (e.route === "V") {
        const y1 = b.cy > a.cy ? a.y + a.h : a.y;
        const y2 = b.cy > a.cy ? b.y : b.y + b.h;
        const my = (y1 + y2) / 2;
        if (a.cx === b.cx) pts = [[a.cx, y1], [b.cx, y2]];
        else pts = [[a.cx, y1], [a.cx, my], [b.cx, my], [b.cx, y2]];
        edges += this._path(pts, second, t);
        if (e.label) labels += this._label(a.cx + 10, (a.y + a.h + b.y) / 2 + 3, e.label, second, "start", t);
      } else if (e.route === "H") {
        if (b.cx > a.cx) pts = [[a.x + a.w, a.cy], [b.x, b.cy]];
        else pts = [[a.x, a.cy], [b.x + b.w, b.cy]];
        edges += this._path(pts, second, t);
        if (e.label) labels += this._label((a.x + a.w + b.x) / 2, a.cy - 13, e.label, second, null, t);
        if (e.deco) edges += this._deco((a.x + a.w + b.x) / 2, a.cy, b.x, e.deco, t + 0.15);
      } else if (e.route === "VH") {
        pts = [[a.cx, a.y + a.h], [a.cx, b.cy], [b.x, b.cy]];
        edges += this._path(pts, second, t);
      } else if (e.route === "HV") {
        pts = [[a.x + a.w, a.cy], [b.cx, a.cy], [b.cx, b.y + b.h]];
        edges += this._path(pts, second, t);
      }
    });

    let nodes = "";
    g.nodes.forEach((n, i) => {
      const b = box[n.id];
      const t = i * step;
      if (n.type === "grid") nodes += this._gridStack(b.cx, b.cy, { label: n.label, sub: n.sub, out: n.out, pick: n.block }, t);
      else nodes += this._node(b.x, b.y, b.w, b.h, n.label, n.sub, n.variant || "op", t, n.block, null, settle + i * 0.05, n._flin != null ? `${n._flin};${n._flout};${n._fup}` : null);
    });

    const H = rowY(g.rows) + bh / 2 + 30;
    return `<svg class="dgm dgm--net" viewBox="0 0 ${W} ${H}" preserveAspectRatio="xMidYMid meet" role="img">${this._defs()}${edges}${labels}${nodes}</svg>`;
  }

  static _deco(mx, cy, endX, kind, t) {
    const C = this.C;
    const delay = t.toFixed(2);
    if (kind === "gate") {
      return (
        `<g class="dgm-skip" style="animation-delay:${delay}s">` +
        `<path d="M${mx - 9},${cy} L${mx},${cy - 9} L${mx + 9},${cy} L${mx},${cy + 9} Z" fill="${C.ioFill}" stroke="${C.accent2}" stroke-width="1.2"/>` +
        `<text x="${mx}" y="${cy + 3}" class="dgm-deco">AG</text></g>`
      );
    }
    if (kind === "add") {
      return `<g class="dgm-skip" style="animation-delay:${delay}s"><circle cx="${endX - 18}" cy="${cy}" r="9" fill="${C.ioFill}" stroke="${C.accent2}" stroke-width="1.2"/><text x="${endX - 18}" y="${cy + 4}" class="dgm-sum">+</text></g>`;
    }
    if (kind === "dots") {
      return `<g class="dgm-skip" style="animation-delay:${delay}s"><circle cx="${mx - 13}" cy="${cy}" r="4.5" fill="${C.ioFill}" stroke="${C.accent2}" stroke-width="1.1"/><circle cx="${mx + 13}" cy="${cy}" r="4.5" fill="${C.ioFill}" stroke="${C.accent2}" stroke-width="1.1"/></g>`;
    }
    return "";
  }

  /* ---------- block detail ---------- */

  static _block(block) {
    if (block.fan) return this._fan(block);
    if (block.horizontal) return this._blockH(block);

    const ops = block.ops;
    const up = block.upward;
    const wb = 208;
    const W = 392;
    const x0 = block.shortcuts && block.shortcuts.length ? 24 : (W - wb) / 2;
    const cx = x0 + wb / 2;
    const gap = 15;
    const topPad = 22;
    let out = "";

    const hs = ops.map((op) => (op.kind === "sum" || op.kind === "mul" || op.kind === "cat" ? 26 : op.kind === "io" ? 32 : 34));
    const off = [];
    let c = 0;
    ops.forEach((op, i) => { off[i] = c; c += hs[i] + gap; });
    const totalH = c - gap;

    const ys = ops.map((op, i) => {
      const yTop = up ? topPad + (totalH - off[i] - hs[i]) : topPad + off[i];
      return { y: yTop, h: hs[i] };
    });

    const ins  = block.flowIn  ? [].concat(block.flowIn)  : [up ? "bottom" : "top"];
    const outs = block.flowOut ? [].concat(block.flowOut) : [up ? "top" : "bottom"];

    const startV  = up ? "bottom" : "top";
    const slotX   = (i, side) => {
      const isNode = ops[i].kind === "sum" || ops[i].kind === "mul" || ops[i].kind === "cat";
      return side === "left" ? (isNode ? cx - 13 : x0) : (isNode ? cx + 13 : x0 + wb);
    };
    const mergeIdx = (() => {
      const k = ops.findIndex((op) => op.kind === "cat" || (op.label || "").toLowerCase().includes("concat"));
      return k >= 0 ? k : 0;
    })();

    const inN  = (side) => Math.min((block.flowInN  && block.flowInN[side])  || 1, 4);
    const outN = (side) => Math.min((block.flowOutN && block.flowOutN[side]) || 1, 4);
    const spread = (n, i, step) => (i - (n - 1) / 2) * step;

    const first = ys[0];
    ins.forEach((side) => {
      if (side === startV) {
        const n = inN(side);
        for (let i = 0; i < n; i++) {
          const ox = spread(n, i, 16);
          if (side === "bottom") out += this._arrow(cx + ox, first.y + first.h + 18, cx + ox, first.y + first.h, false, 0);
          else out += this._arrow(cx + ox, first.y - 18, cx + ox, first.y, false, 0);
        }
      } else {
        const eSide = side === "right" ? "right" : "left";
        const ex    = slotX(mergeIdx, eSide);
        const eCy   = ys[mergeIdx].y + ys[mergeIdx].h / 2;
        const n     = inN(side);
        for (let i = 0; i < n; i++) {
          const oy = spread(n, i, 10);
          if (eSide === "left") out += this._arrow(ex - 18, eCy + oy, ex, eCy + oy, false, 0);
          else out += this._arrow(ex + 18, eCy + oy, ex, eCy + oy, false, 0);
        }
      }
    });

    const last   = ys[ops.length - 1];
    const lastCy = last.y + last.h / 2;
    let endDrawn = false;
    outs.forEach((side) => {
      if (side === "top" || side === "bottom") {
        if (endDrawn) return;
        endDrawn = true;
        const n = outN(side);
        for (let i = 0; i < n; i++) {
          const ox = spread(n, i, 16);
          if (up) out += this._arrow(cx + ox, last.y, cx + ox, last.y - 18, false, ops.length);
          else out += this._arrow(cx + ox, last.y + last.h, cx + ox, last.y + last.h + 18, false, ops.length);
        }
      } else {
        const eSide = side === "right" ? "right" : "left";
        const ex    = slotX(ops.length - 1, eSide);
        const n     = outN(side);
        for (let i = 0; i < n; i++) {
          const oy = spread(n, i, 10);
          if (eSide === "right") out += this._arrow(ex, lastCy + oy, ex + 18, lastCy + oy, false, ops.length);
          else out += this._arrow(ex, lastCy + oy, ex - 18, lastCy + oy, false, ops.length);
        }
      }
    });

    for (let i = 0; i < ops.length - 1; i++) {
      const a = ys[i], b = ys[i + 1];
      if (a.y < b.y) out += this._arrow(cx, a.y + a.h, cx, b.y, false, i + 1);
      else out += this._arrow(cx, a.y, cx, b.y + b.h, false, i + 1);
    }

    ops.forEach((op, i) => {
      const slot = ys[i];
      if (op.kind === "sum") out += this._sum(cx, slot.y + slot.h / 2, "+", i * 0.03);
      else if (op.kind === "mul") out += this._sum(cx, slot.y + slot.h / 2, "x", i * 0.03);
      else if (op.kind === "cat") {
        out += this._sum(cx, slot.y + slot.h / 2, "||", i * 0.03);
        out += this._label(cx + 22, slot.y + slot.h / 2 + 3, op.label, false, "start", i * 0.03);
      }
      else out += this._node(x0, slot.y, wb, slot.h, op.label, op.sub, op.kind === "io" ? "io" : "op", i * 0.03, null, op.block);
    });

    const rightX = x0 + wb + 48;
    (block.shortcuts || []).forEach((sc, k) => {
      const target = ys[sc.to];
      const ty = target.y + target.h / 2;
      const fromOp   = sc.from === "top" ? null : ops[sc.from];
      const fromNode = fromOp != null && (fromOp.kind === "sum" || fromOp.kind === "mul" || fromOp.kind === "cat");
      let startX, startY;
      if (sc.from === "top") {
        startX = cx;
        startY = up ? first.y + first.h + 12 : 12;
      } else if (fromNode) {
        startX = cx;
        startY = up ? ys[sc.from].y - 8 : ys[sc.from].y + ys[sc.from].h + 8;
      } else {
        startX = x0 + wb;
        startY = ys[sc.from].y + ys[sc.from].h / 2;
      }
      const tKind = ops[sc.to].kind;
      const endX = tKind === "sum" || tKind === "mul" || tKind === "cat" ? cx + 13 : x0 + wb;
      const tSc = k * 0.03 + 0.18;
      out += this._path([[startX, startY], [rightX, startY], [rightX, ty], [endX, ty]], true, tSc);
      if (sc.op) out += this._skipOp(rightX, (startY + ty) / 2, sc.op, tSc + 0.05);
      else out += this._label(rightX + 8, (startY + ty) / 2 + 3, sc.label, true, "start");
    });

    const vOut = outs.some((s) => s === "top" || s === "bottom");
    const H = topPad + totalH + (((!up && vOut) || ins.includes("bottom")) ? 26 : 10);
    return `<svg class="dgm" viewBox="0 0 ${W} ${H}" preserveAspectRatio="xMidYMid meet" role="img">${this._defs()}${out}</svg>`;
  }

  static _blockH(block) {
    const ops = block.ops;
    const ins  = block.flowIn  ? [].concat(block.flowIn)  : ["left"];
    const outs = block.flowOut ? [].concat(block.flowOut) : ["right"];
    const hasSc  = !!(block.shortcuts && block.shortcuts.length);
    const vIn    = ins.find((s) => s === "top" || s === "bottom");
    const scSide = vIn === "bottom" ? "top" : "bottom";
    const topNeed = (hasSc && scSide === "top") ? 40 : ((ins.includes("top") || outs.includes("top")) ? 22 : 0);
    const hb = 64, gap = 20, rowCy = 46 + topNeed, wb = 126, sumW = 32;
    let x = 18;
    const xs = [];
    let out = "";

    ops.forEach((op) => {
      const isNode = op.kind === "sum" || op.kind === "mul" || op.kind === "cat";
      if (isNode) {
        xs.push({ cx: x + sumW / 2, w: sumW, node: true });
        x += sumW + gap;
      } else {
        xs.push({ x, cx: x + wb / 2, w: wb });
        x += wb + gap;
      }
    });

    const inN  = (side) => Math.min((block.flowInN  && block.flowInN[side])  || 1, 4);
    const outN = (side) => Math.min((block.flowOutN && block.flowOutN[side]) || 1, 4);
    const spread = (n, i, step) => (i - (n - 1) / 2) * step;

    const firstCx = xs[0].cx;
    let leftIn = false;
    ins.forEach((side) => {
      if (side === "top" || side === "bottom") {
        const n = inN(side);
        for (let i = 0; i < n; i++) {
          const ox = spread(n, i, 18);
          if (side === "top") out += this._arrow(firstCx + ox, rowCy - hb / 2 - 18, firstCx + ox, rowCy - hb / 2, false, 0);
          else out += this._arrow(firstCx + ox, rowCy + hb / 2 + 18, firstCx + ox, rowCy + hb / 2, false, 0);
        }
      } else if (!leftIn) {
        leftIn = true;
        const n = inN("left");
        const firstNode = xs[0].node;
        const endX = firstNode ? xs[0].cx - 15 : 16;
        for (let i = 0; i < n; i++) {
          const oy = spread(n, i, firstNode ? 8 : 14);
          out += this._arrow(3, rowCy + oy, endX, rowCy + oy, false, 0);
        }
      }
    });

    for (let i = 0; i < ops.length - 1; i++) {
      const a = xs[i], b = xs[i + 1];
      const ax = a.node ? a.cx + a.w / 2 : a.x + a.w;
      const bx = b.node ? b.cx - b.w / 2 : b.x;
      out += this._arrow(ax, rowCy, bx, rowCy, false, i + 1);
    }

    const lastS  = xs[xs.length - 1];
    const lastCx = lastS.cx;
    const lastRight = lastS.node ? lastS.cx + lastS.w / 2 : lastS.x + lastS.w;
    let rightOut = false;
    outs.forEach((side) => {
      if (side === "top" || side === "bottom") {
        const n = outN(side);
        for (let i = 0; i < n; i++) {
          const ox = spread(n, i, 18);
          if (side === "top") out += this._arrow(lastCx + ox, rowCy - hb / 2, lastCx + ox, rowCy - hb / 2 - 18, false, ops.length);
          else out += this._arrow(lastCx + ox, rowCy + hb / 2, lastCx + ox, rowCy + hb / 2 + 18, false, ops.length);
        }
      } else if (!rightOut) {
        rightOut = true;
        const n = outN("right");
        for (let i = 0; i < n; i++) {
          const oy = spread(n, i, 14);
          out += this._arrow(lastRight, rowCy + oy, lastRight + 14, rowCy + oy, false, ops.length);
        }
      }
    });

    ops.forEach((op, i) => {
      const s = xs[i];
      if (op.kind === "sum") out += this._sum(s.cx, rowCy, "+", i * 0.03, 15);
      else if (op.kind === "mul") out += this._sum(s.cx, rowCy, "x", i * 0.03, 15);
      else if (op.kind === "cat") {
        out += this._sum(s.cx, rowCy, "||", i * 0.03, 15);
        out += this._label(s.cx, rowCy + hb / 2 + 12, op.label, false, "middle", i * 0.03);
      }
      else out += this._node(s.x, rowCy - hb / 2, s.w, hb, op.label, op.sub, op.kind === "io" ? "io" : "op", i * 0.03, null, op.block);
    });

    const chanY = scSide === "top" ? rowCy - hb / 2 - 26 : rowCy + hb / 2 + 26;
    (block.shortcuts || []).forEach((sc, k) => {
      const sumCx  = xs[sc.to].cx;
      const fromOp   = sc.from === "top" ? null : ops[sc.from];
      const fromNode = fromOp != null && (fromOp.kind === "sum" || fromOp.kind === "mul" || fromOp.kind === "cat");
      const startX = sc.from === "top" ? 12 : fromNode ? xs[sc.from].cx + 23 : xs[sc.from].cx;
      const startY = sc.from === "top" ? rowCy : fromNode ? rowCy : (scSide === "top" ? rowCy - hb / 2 : rowCy + hb / 2);
      const innerY = scSide === "top" ? rowCy - 15 : rowCy + 15;
      out += this._path([[startX, startY], [startX, chanY], [sumCx, chanY], [sumCx, innerY]], true, k * 0.03 + 0.18);
      if (sc.op) out += this._skipOp((startX + sumCx) / 2, chanY, sc.op, k * 0.03 + 0.23);
      else out += this._label((startX + sumCx) / 2, scSide === "top" ? chanY - 6 : chanY + 12, sc.label, true);
    });

    const W = x - gap + (outs.includes("right") || outs.includes("left") ? 24 : 18);
    let H = (hasSc && scSide === "bottom") ? chanY + 22 : rowCy + hb / 2 + 14;
    if (ins.includes("bottom") || outs.includes("bottom")) H = Math.max(H, rowCy + hb / 2 + 24);
    return `<svg class="dgm dgm--h" style="--natw:${W}px" viewBox="0 0 ${W} ${H}" preserveAspectRatio="xMidYMid meet" role="img">${this._defs()}${out}</svg>`;
  }

  static _skipOp(cx, cy, label, t) {
    const C = this.C;
    const bw = 70, bh = 22;
    return (
      `<g class="dgm-block" style="animation-delay:${t.toFixed(2)}s">` +
      `<rect x="${cx - bw / 2}" y="${cy - bh / 2}" width="${bw}" height="${bh}" rx="5" fill="${C.ioFill}" stroke="${C.accent2}" stroke-width="1.2"/>` +
      `<text x="${cx}" y="${cy + 3.5}" class="dgm-s">${label}</text>` +
      `</g>`
    );
  }

  static _fan(block) {
    const labels = block.fan.slice(0, 3);
    const up = block.upward;
    const W = 336, wb = 92, hb = 32, cx = W / 2, inH = 30, outH = 26, vgap = 28, bgap = 14;
    let out = "";

    let y = 14;
    const P = {};
    const order = up ? ["out", "branch", "in"] : ["in", "branch", "out"];
    order.forEach((k) => {
      if (k === "in") { P.in = y; y += inH + vgap; }
      else if (k === "branch") { P.branch = y; y += hb + (up ? vgap : bgap); }
      else { P.out = y; y += outH + (up ? bgap : vgap); }
    });
    const H = y;

    out += this._node(cx - 96, P.in, 192, inH, block.inLabel, block.inSub, "io", 0);

    const branchesBelowInput = P.branch > P.in;
    const hubY = branchesBelowInput ? P.in + inH + 12 : P.in - 12;
    out += this._arrow(cx, branchesBelowInput ? P.in + inH : P.in, cx, hubY, false, 1);

    const slotW = wb + 14;
    const startX = cx - ((labels.length - 1) * slotW) / 2;
    labels.forEach((lab, i) => {
      const bCx = startX + i * slotW;
      const bx = bCx - wb / 2;
      out += this._path([[cx, hubY], [bCx, hubY], [bCx, branchesBelowInput ? P.branch : P.branch + hb]], false, (2 + i) * 0.03 + 0.18);
      out += this._node(bx, P.branch, wb, hb, lab.t, lab.sub, "op", (2 + i) * 0.03);
      if (P.out > P.branch) out += this._arrow(bCx, P.branch + hb, bCx, P.out, false, 5 + i);
      else out += this._arrow(bCx, P.branch, bCx, P.out + outH, false, 5 + i);
      out += this._node(bx, P.out, wb, outH, lab.out, null, "io", (5 + i) * 0.03);
    });

    return `<svg class="dgm" viewBox="0 0 ${W} ${H}" preserveAspectRatio="xMidYMid meet" role="img">${this._defs()}${out}</svg>`;
  }

  /* ---------- op helpers ---------- */

  static _o = {
    conv: (a, b) => ({ label: "Conv 3x3", sub: a ? `${a} -> ${b}` : undefined }),
    norm: (name) => ({ label: name }),
    act: (name) => ({ label: name }),
    pool: () => ({ label: "MaxPool 2x2", sub: "down" }),
    up: () => ({ label: "Up-conv 2x2", sub: "up" }),
    cat: (label) => ({ label: label || "concat skip", kind: "cat" }),
    sum: () => ({ label: "+", kind: "sum" }),
    mul: () => ({ kind: "mul" }),
    io: (label, sub) => ({ label, sub, kind: "io" }),
    txt: (label, sub) => ({ label, sub }),
  };

  static _na(s) {
    return s.norm ? [this._o.norm(s.norm), this._o.act(s.act)] : [this._o.act(s.act)];
  }

  /* ---------- per-model blueprints ---------- */

  static _uGraph(o) {
    const sh = o.shapes;
    const nodes = [
      { id: "in", col: "left", row: 0, type: "grid", label: "input", sub: sh[0] },
      { id: "e1", col: "left", row: 1, label: o.enc, sub: sh[1], block: "enc" },
      { id: "e2", col: "left", row: 2, label: o.enc, sub: sh[2], block: "enc" },
      { id: "e3", col: "left", row: 3, label: o.enc, sub: sh[3], block: "enc" },
      { id: "e4", col: "left", row: 4, label: o.enc, sub: sh[4], block: "enc" },
      { id: "bn", col: "center", row: 5, label: o.bott, sub: sh[5], block: "bridge" },
      { id: "d4", col: "right", row: 4, label: o.dec, sub: sh[6], block: "dec" },
      { id: "d3", col: "right", row: 3, label: o.dec, sub: sh[7], block: "dec" },
      { id: "d2", col: "right", row: 2, label: o.dec, sub: sh[8], block: "dec" },
      { id: "d1", col: "right", row: 1, label: o.dec, sub: sh[9], block: "dec" },
      { id: "hd", col: "right", yPix: 132, label: "Output head", sub: o.headSub, block: "head" },
      { id: "out", col: "right", row: 0, type: "grid", out: true, label: "params", sub: sh[10] },
    ];
    const edges = [
      { from: "in", to: "e1", route: "V" },
      { from: "e1", to: "e2", route: "V" },
      { from: "e2", to: "e3", route: "V" },
      { from: "e3", to: "e4", route: "V" },
      { from: "e4", to: "bn", route: "VH" },
      { from: "bn", to: "d4", route: "HV" },
      { from: "d4", to: "d3", route: "V" },
      { from: "d3", to: "d2", route: "V" },
      { from: "d2", to: "d1", route: "V" },
      { from: "d1", to: "hd", route: "V" },
      { from: "hd", to: "out", route: "V" },
      { from: "e1", to: "d1", route: "H", kind: "skip", label: o.skip, deco: o.deco },
      { from: "e2", to: "d2", route: "H", kind: "skip", label: o.skip, deco: o.deco },
      { from: "e3", to: "d3", route: "H", kind: "skip", label: o.skip, deco: o.deco },
      { from: "e4", to: "d4", route: "H", kind: "skip", label: o.skip, deco: o.deco },
    ];
    return { nodes, edges, rows: 5 };
  }

  static _headBlock(s) {
    const o = this._o;
    if (s.key === "nafnet") {
      return { id: "head", title: "Output head", caption: "3x3 conv to params", ops: [o.txt("Conv 3x3", "w -> 3K"), o.io("params", "3K x P x P")] };
    }
    if (s.heads === 3 || s.heads === "K") {
      const labs = s.heads === 3
        ? [{ t: "PixelMLP", sub: "amp", out: "a" }, { t: "PixelMLP", sub: "mean", out: "mu" }, { t: "PixelMLP", sub: "spread", out: "sig" }]
        : [{ t: "PixelMLP", sub: "k=1", out: "a,mu,s" }, { t: "PixelMLP", sub: "k=2", out: "a,mu,s" }, { t: "PixelMLP", sub: "k=K", out: "a,mu,s" }];
      return { id: "head", title: s.heads === 3 ? "Per-type heads" : "Per-Gaussian heads", fan: labs, inLabel: "decoder features", inSub: "d1 : F1 x P x P" };
    }
    return { id: "head", title: "Output head", caption: "1x1 conv to params", ops: [o.txt("Conv 1x1", "F1 -> 3K"), o.io("params", "3K x P x P")] };
  }

  static _blocks(s) {
    const o = this._o;
    const na = this._na(s);
    const head1 = this._headBlock(s);

    if (s.type === "transformer") {
      const mhsa = s.key === "swin_unet" ? "W-MSA" : "Multi-head attn";
      const txBlock = { id: "tx", title: "Transformer block", caption: "attention then MLP, each residual", ops: [o.txt("LayerNorm"), o.txt(mhsa), o.sum(), o.txt("LayerNorm"), o.txt("MLP", "GELU"), o.sum(), o.io("output")], shortcuts: [{ from: "top", to: 2, label: "res" }, { from: 2, to: 5, label: "res" }] };
      const down = s.key === "swin_unet" ? o.txt("Patch merge", "down") : o.txt("Down-sample", "down");
      const up = s.key === "unetr" ? o.txt("Deconv 2x2", "up") : s.key === "swin_unet" ? o.txt("Patch expand", "up") : o.txt("Upsample", "up");
      const txOp = { label: "Transformer block", sub: "x N", block: "tx" };
      const enc = { id: "enc", title: "Encoder block", caption: "downsample, then transformer block", ops: [down, txOp, o.io("output")] };
      const bridge = { id: "bridge", title: "Bridge", caption: "deepest transformer block", ops: [{ label: "Transformer", sub: "x N", block: "tx" }, o.io("output")] };
      const convref = { id: "convref", title: "Conv block", caption: "double 3x3 conv, each norm-act", ops: [o.conv("2F", "F"), ...na, o.conv("F", "F"), ...na, o.io("output")] };
      const decRefine = s.key === "transunet" ? o.txt("Conv 3x3") : s.key === "unetr" ? { label: "Conv block", sub: "double 3x3", block: "convref" } : { label: "Transformer block", block: "tx" };
      const dec = { id: "dec", title: "Decoder block", caption: "upsample, fuse skip, refine", ops: [up, o.cat(), decRefine, o.io("output")] };
      const out = [enc, bridge, txBlock, dec, head1];
      if (s.key === "unetr") out.push(convref);
      return out;
    }

    if (s.skipKind === "resmaxpool") {
      const enc = { id: "enc", title: "Encoder block", caption: "residual block, then 2x2 max-pool", ops: [...na, o.conv("Cin", "F"), ...na, o.conv("F", "F"), o.sum(), o.pool(), o.io("output", "F x H/2")], shortcuts: [{ from: "top", to: na.length * 2 + 2, label: "Proj", op: "Conv 1x1" }] };
      const bridge = { id: "bridge", title: "Bridge", caption: "residual bottleneck", ops: [...na, o.conv("F", "2F"), ...na, o.conv("2F", "2F"), o.sum(), o.io("output", "2F x H")], shortcuts: [{ from: "top", to: na.length * 2 + 2, label: "Proj", op: "Conv 1x1" }] };
      const dec = { id: "dec", title: "Decoder block", caption: "up-conv, concat, residual block", ops: [o.up(), o.cat(), ...na, o.conv("2F", "F"), ...na, o.conv("F", "F"), o.sum(), o.io("output", "F x 2H")], shortcuts: [{ from: 1, to: na.length * 2 + 4, label: "Proj", op: "Conv 1x1" }] };
      return [enc, bridge, dec, head1];
    }

    if (s.skipKind === "residual") {
      const enc = { id: "enc", title: "Encoder block", caption: "pre-activation residual block, stride-2 downsampling", ops: [...na, { label: "Conv 3x3 s2", sub: "Cin -> F, down" }, ...na, o.conv("F", "F"), o.sum(), o.io("output", "F x H/2")], shortcuts: [{ from: "top", to: na.length * 2 + 2, label: "Proj", op: "Conv 1x1 s2" }] };
      const enc0 = { id: "enc0", title: "Encoder block (first unit)", caption: "first unit operates on the raw input: no leading norm-act, stride 1", ops: [{ label: "Conv 3x3", sub: "Cin -> F" }, ...na, o.conv("F", "F"), o.sum(), o.io("output", "F x H")], shortcuts: [{ from: "top", to: na.length + 2, label: "Proj", op: "Conv 1x1" }] };
      const bridge = { id: "bridge", title: "Bridge", caption: "residual bottleneck, stride-2 downsampling", ops: [...na, { label: "Conv 3x3 s2", sub: "F -> 2F, down" }, ...na, o.conv("2F", "2F"), o.sum(), o.io("output", "2F x H/2")], shortcuts: [{ from: "top", to: na.length * 2 + 2, label: "Proj", op: "Conv 1x1 s2" }] };
      const dec = { id: "dec", title: "Decoder block", caption: "up-conv, concat, residual block", ops: [o.up(), o.cat(), ...na, o.conv("2F", "F"), ...na, o.conv("F", "F"), o.sum(), o.io("output", "F x 2H")], shortcuts: [{ from: 1, to: na.length * 2 + 4, label: "Proj", op: "Conv 1x1" }] };
      return [enc, enc0, bridge, dec, head1];
    }

    if (s.skipKind === "convnext") {
      const cn = { id: "cnx", title: "ConvNeXt block", caption: "depthwise large kernel, inverted bottleneck, layer scale, residual", ops: [o.txt("DWConv 7x7", "per-channel"), o.txt("LayerNorm"), o.txt("Linear", "C -> 4C"), o.txt("GELU"), o.txt("Linear", "4C -> C"), o.txt("Layer Scale", "gamma"), o.txt("DropPath"), o.sum(), o.io("output")], shortcuts: [{ from: "top", to: 7, label: "residual" }] };
      const cnOp = { label: "ConvNeXt block", sub: "x N", block: "cnx" };
      const enc = { id: "enc", title: "Encoder stage", caption: "1x1 project, ConvNeXt blocks, then LN + strided conv down", ops: [o.txt("Conv 1x1", "project"), cnOp, o.txt("LayerNorm"), o.txt("Conv 2x2 s2", "down"), o.io("output", "F x H/2")] };
      const bridge = { id: "bridge", title: "Bottleneck", caption: "deepest ConvNeXt stage", ops: [o.txt("Conv 1x1", "project"), { label: "ConvNeXt block", sub: "x N", block: "cnx" }, o.io("output", "rF x H")] };
      const dec = { id: "dec", title: "Decoder stage", caption: "deconv up, concat skip, ConvNeXt blocks", ops: [o.txt("ConvT 2x2", "up"), o.cat(), { label: "Conv 1x1", sub: "project" }, { label: "ConvNeXt block", sub: "x N", block: "cnx" }, o.io("output", "F x 2H")] };
      return [enc, bridge, cn, dec, head1];
    }

    if (s.skipKind === "dense") {
      const dl = { id: "dl", title: "Dense layer", caption: "norm, act, 3x3 conv emitting g new channels", ops: [...na, o.txt("Conv 3x3", "-> g"), o.io("g new ch")] };
      const db = { id: "db", title: "Dense block", caption: "each layer sees all preceding features; outputs L*g new channels", ops: [o.io("input x"), { label: "Dense layer", sub: "concat all prior", block: "dl" }, o.cat("concat growing"), { label: "Dense layer", sub: "x L total", block: "dl" }, o.io("new features", "L*g ch")] };
      const dbOp = { label: "Dense block", sub: "L layers", block: "db" };
      const enc = { id: "enc", title: "Down block", caption: "dense block, concat to input (skip), transition down", ops: [dbOp, o.cat(), o.txt("Conv 1x1"), o.pool(), o.io("output", "C x H/2")] };
      const bridge = { id: "bridge", title: "Bottleneck", caption: "dense block emitting only new features", ops: [{ label: "Dense block", sub: "Lb layers", block: "db" }, o.io("new features", "g*Lb x H")] };
      const dec = { id: "dec", title: "Up block", caption: "transposed conv up, concat skip, dense block (new features)", ops: [o.txt("ConvT 2x2", "up"), o.cat(), { label: "Dense block", sub: "L layers", block: "db" }, o.io("new features", "g*L x 2H")] };
      return [enc, bridge, dl, db, dec, head1];
    }

    if (s.skipKind === "respath") {
      const mrb = { id: "mrb", title: "MultiRes block", caption: "three chained 3x3 convs (RF 3/5/7), concat, 1x1 shortcut sum", ops: [o.txt("Conv 3x3", "W/6"), o.txt("Conv 3x3", "W/3"), o.txt("Conv 3x3", "W/2"), o.cat("concat RF 3,5,7"), o.txt("Norm"), o.sum(), o.txt(s.act), o.io("output", "W ch")], shortcuts: [{ from: "top", to: 5, label: "Conv 1x1", op: "Conv 1x1" }] };
      const rp = { id: "rp", title: "ResPath", caption: "conv 3x3 + 1x1 shortcut, repeated (n_levels - i units)", ops: [o.io("skip x"), o.txt("Conv 3x3"), o.sum(), o.txt(s.act), { label: "repeat", sub: "x (n-i)" }, o.io("refined skip")], shortcuts: [{ from: 0, to: 2, label: "Conv 1x1", op: "Conv 1x1" }] };
      const mrbOp = { label: "MultiRes block", block: "mrb" };
      const enc = { id: "enc", title: "Encoder block", caption: "MultiRes block, ResPath on skip, then max-pool", ops: [mrbOp, { label: "ResPath", sub: "on skip", block: "rp" }, o.pool(), o.io("output", "F x H/2")] };
      const bridge = { id: "bridge", title: "Bridge", caption: "deepest MultiRes block", ops: [{ label: "MultiRes block", block: "mrb" }, o.io("output", "Fb x H")] };
      const dec = { id: "dec", title: "Decoder block", caption: "up-conv, concat ResPath skip, MultiRes block", ops: [o.up(), o.cat(), { label: "MultiRes block", block: "mrb" }, o.io("output", "F x 2H")] };
      return [enc, bridge, mrb, rp, dec, head1];
    }

    if (s.skipKind === "rsu") {
      const rsu = { id: "rsu", title: "RSU mini U-Net", caption: "conv in, internal encoder convs + pools, dilated bottom, decoder concat, residual add", ops: [o.txt("Conv 3x3", "-> Cout"), { label: "encoder convs", sub: "+ pool, x(L-1)" }, o.txt("Conv 3x3", "dilation 2"), { label: "decoder convs", sub: "concat + up" }, o.sum(), o.io("output")], shortcuts: [{ from: 0, to: 4, label: "residual" }] };
      const rsud = { id: "rsud", title: "Dilated RSU bridge", caption: "no pooling; dilations 1,2,4 then bottom 8, decoder concat, residual add", ops: [o.txt("Conv 3x3", "-> Cout"), { label: "convs d=1,2,4", sub: "no pool" }, o.txt("Conv 3x3", "dilation 8"), { label: "decoder convs", sub: "concat" }, o.sum(), o.io("output")], shortcuts: [{ from: 0, to: 4, label: "residual" }] };
      const enc = { id: "enc", title: "Encoder stage", caption: "RSU block, then max-pool", ops: [{ label: "RSU", sub: "height L", block: "rsu" }, o.pool(), o.io("output", "F x H/2")] };
      const bridge = { id: "bridge", title: "Bridge", caption: "dilated RSU at coarsest resolution", ops: [{ label: "Dilated RSU", sub: "d 1,2,4,8", block: "rsud" }, o.io("output", "Fb x H")] };
      const dec = { id: "dec", title: "Decoder stage", caption: "upsample, concat skip, RSU block", ops: [o.up(), o.cat(), { label: "RSU", sub: "height L", block: "rsu" }, o.io("output", "F x 2H")] };
      return [enc, bridge, rsu, rsud, dec, head1];
    }

    if (s.skipKind === "nafnet") {
      const nafblk = {
        id: "nafblk", title: "NAFBlock",
        caption: "two zero-initialised residual branches; SimpleGate is the only nonlinearity",
        ops: [
          o.txt("LayerNorm"),
          o.txt("Conv 1x1", "C -> 2C"),
          o.txt("DWConv 3x3", "per-channel"),
          o.txt("SimpleGate", "split-half multiply"),
          o.txt("SCA", "pool + 1x1, scale"),
          o.txt("Conv 1x1", "-> C"),
          o.sum(),
          o.txt("LayerNorm"),
          o.txt("Conv 1x1", "C -> 2C"),
          o.txt("SimpleGate"),
          o.txt("Conv 1x1", "-> C"),
          o.sum(),
          o.io("output"),
        ],
        shortcuts: [{ from: "top", to: 6, label: "beta res" }, { from: 6, to: 11, label: "gamma res" }],
      };
      const enc = { id: "enc", title: "Encoder stage", caption: "NAFBlocks, then stride-2 conv doubling channels", ops: [{ label: "NAFBlock", sub: "x N", block: "nafblk" }, o.txt("Conv 2x2 s2", "down, C -> 2C"), o.io("output", "2C x H/2")] };
      const bridge = { id: "bridge", title: "Middle stack", caption: "deepest NAFBlocks at width x 16", ops: [{ label: "NAFBlock", sub: "x 12", block: "nafblk" }, o.io("output", "16w x H")] };
      const dec = { id: "dec", title: "Decoder stage", caption: "1x1 conv + PixelShuffle up, add encoder skip, NAFBlocks", ops: [o.txt("Conv 1x1", "C -> 2C"), o.txt("PixelShuffle 2", "up, -> C/2"), o.sum(), { label: "NAFBlock", sub: "x N", block: "nafblk" }, o.io("output", "C/2 x 2H")], shortcuts: [{ from: "top", to: 2, label: "encoder skip" }] };
      return [enc, bridge, nafblk, dec, head1];
    }

    if (s.skipKind === "additive") {
      const enc = { id: "enc", title: "Encoder block", caption: "residual conv, then downsample", ops: [o.conv("Cin", "F"), ...na, o.conv("F", "F"), o.sum(), o.pool(), o.io("output", "F x H/2")], shortcuts: [{ from: "top", to: na.length + 2, label: "skip" }] };
      const bridge = { id: "bridge", title: "Bridge", caption: "bottleneck conv", ops: [o.conv("F", "2F"), ...na, o.conv("2F", "2F"), ...na, o.io("output", "2F x H")] };
      const dec = { id: "dec", title: "Decoder block", caption: "reduce, up-conv, add encoder skip", ops: [o.txt("Conv 1x1", "C -> C/4"), o.txt("ConvT 3x3", "up"), o.txt("Conv 1x1", "C/4 -> C"), o.sum(), o.io("output", "F x 2H")], shortcuts: [{ from: "top", to: 3, label: "encoder skip" }] };
      return [enc, bridge, dec, head1];
    }

    const enc = { id: "enc", title: "Encoder block", caption: "double conv, then 2x2 max-pool", ops: [o.conv("Cin", "F"), ...na, o.conv("F", "F"), ...na, o.pool(), o.io("output", "F x H/2")] };
    const bridge = { id: "bridge", title: "Bridge", caption: "bottleneck double conv", ops: [o.conv("F", "2F"), ...na, o.conv("2F", "2F"), ...na, o.io("output", "2F x H")] };

    if (s.skipKind === "attention") {
      const dec = { id: "dec", title: "Decoder block", caption: "attention-gate skip, up-conv, concat, double conv", ops: [{ label: "Attention gate", sub: "on skip", block: "attn" }, o.up(), o.cat(), o.conv("2F", "F"), ...na, o.conv("F", "F"), ...na, o.io("output", "F x 2H")] };
      const gate = { id: "attn", title: "Attention gate", caption: "gate the skip with the coarse decoder feature", ops: [o.io("gate g + skip x", "coarse g, skip x"), o.txt("W_g: Conv 1x1", "on coarse gate"), o.txt("W_x: Conv 2x2 s2", "downsample skip"), o.sum(), o.txt("ReLU"), o.txt("psi: Conv 1x1", "-> 1 ch"), o.txt("Sigmoid", "in [0,1]"), o.txt("Upsample", "to skip res"), o.mul(), o.txt("W_out: Conv 1x1", "+ norm"), o.io("gated skip")], shortcuts: [{ from: 0, to: 8, label: "skip x (full res)" }] };
      return [enc, bridge, dec, gate, head1];
    }

    if (s.skipKind === "nested") {
      const dec = { id: "dec", title: "Dense node", caption: "fuse dense skips, double conv", ops: [o.io("concat dense inputs", "up + same level"), o.conv("", ""), ...na, o.conv("", ""), o.io("node X(i,j)")] };
      return [enc, bridge, dec, head1];
    }

    const decPlain = { id: "dec", title: "Decoder block", caption: "up-conv, concat skip, double conv", ops: [o.up(), o.cat(), o.conv("2F", "F"), ...na, o.conv("F", "F"), ...na, o.io("output", "F x 2H")] };
    return [enc, bridge, decPlain, head1];
  }

  static _blueprint(model) {
    const s = this.spec(model);
    if (s.type === "segformer") return this._bpSegformer(s);
    if (s.type === "deeplab") return this._bpDeepLab(s);
    if (s.type === "hrnet") return this._bpHRNet(s);
    if (s.type === "fpn") return this._bpFPN(s);
    if (s.type === "stack") return this._bpStack(s);

    const cnnShapes = ["Cin x P x P", "F1 x P/2 x P/2", "F2 x P/4 x P/4", "F3 x P/8 x P/8", "F4 x P/16 x P/16", "Fb x P/16 x P/16", "F4 x P/8 x P/8", "F3 x P/4 x P/4", "F2 x P/2 x P/2", "F1 x P x P", "3K x P x P"];
    const txShapes = ["Cin x P x P", "D1 x N1", "D2 x N2", "D3 x N3", "D4 x N4", "Db x N4", "D4 x N3", "D3 x N2", "D2 x N1", "D1 x N1", "3K x P x P"];
    const headSub = s.heads === 3 ? "3 x PixelMLP" : s.heads === "K" ? "K x PixelMLP" : s.key === "nafnet" ? "3x3 conv" : "1x1 conv";

    const labels = {
      unet: { enc: "Encoder", dec: "Decoder", bott: "Bridge", skip: "concat" },
      resunet: { enc: "Residual encoder", dec: "Residual decoder", bott: "Residual bridge", skip: "concat" },
      unet_skip: { enc: "Residual encoder", dec: "Residual decoder", bott: "Residual bridge", skip: "concat" },
      attention_unet: { enc: "Encoder", dec: "Decoder", bott: "Bridge", skip: "concat", deco: "gate" },
      unetplusplus: { enc: "Encoder", dec: "Dense node", bott: "Bridge", skip: "dense", deco: "dots" },
      linknet: { enc: "Residual encoder", dec: "Decoder", bott: "Bridge", skip: "add", deco: "add" },
      swin_unet: { enc: "Swin encoder", dec: "Swin decoder", bott: "Swin bridge", skip: "concat" },
      transunet: { enc: "ViT encoder", dec: "CNN decoder", bott: "ViT bridge", skip: "skip" },
      unetr: { enc: "ViT encoder", dec: "Deconv decoder", bott: "ViT bridge", skip: "skip" },
      nafnet: { enc: "NAF stage", dec: "NAF stage", bott: "Middle stack", skip: "add", deco: "add" },
      convnext_unet: { enc: "ConvNeXt stage", dec: "ConvNeXt stage", bott: "Bottleneck", skip: "concat" },
      dense_unet: { enc: "Dense down", dec: "Dense up", bott: "Bottleneck", skip: "dense concat" },
      multires_unet: { enc: "MultiRes block", dec: "MultiRes block", bott: "MultiRes bridge", skip: "ResPath" },
      u2net: { enc: "RSU stage", dec: "RSU stage", bott: "Dilated RSU", skip: "concat" },
    };

    const o = labels[s.key] || labels.unet;
    o.headSub = headSub;
    o.shapes = s.type === "transformer" ? txShapes : cnnShapes;
    const blocks = this._blocks(s);
    const graph = this._uGraph(o);
    if (s.skipKind === "residual") graph.nodes.find((n) => n.id === "e1").block = "enc0";
    this._applyOrientation(graph, blocks);
    return { network: this._network(graph), blocks };
  }

  /* ---------- block orientation standard ---------- */

  static _applyOrientation(g, blocks) {
    const nodeById = {};
    g.nodes.forEach((n) => {
      nodeById[n.id] = n;
      n._ocx = n.cx != null ? n.cx : (n.col === "left" ? -1 : n.col === "right" ? 1 : 0);
      n._ocy = n.cy != null ? n.cy : (n.yPix != null ? n.yPix : (n.row === 0 ? 66 : 210 + ((n.row || 1) - 1) * 76));
    });

    const ptSide = (n, pt) => {
      const w = n.type === "grid" ? 50 : (n.w || 150);
      if (Math.abs(pt[0] - (n._ocx - w / 2)) <= 1) return "left";
      if (Math.abs(pt[0] - (n._ocx + w / 2)) <= 1) return "right";
      return pt[1] <= n._ocy ? "top" : "bottom";
    };

    const sidesOf = (e) => {
      const a = nodeById[e.from], b = nodeById[e.to];
      const r = e.route || "auto";
      const hPair = () => (b._ocx >= a._ocx ? ["right", "left"] : ["left", "right"]);
      const vPair = () => (b._ocy >= a._ocy ? ["bottom", "top"] : ["top", "bottom"]);
      if (r === "H") return hPair();
      if (r === "V") return vPair();
      if (r === "HV") return [hPair()[0], vPair()[1]];
      if (r === "VH") return [vPair()[0], hPair()[1]];
      if (r === "P") {
        const sf = e.fromPt ? ptSide(a, e.fromPt) : (e.fromSide || "right");
        const st = e.toPt ? ptSide(b, e.toPt) : (e.toSide || "left");
        return [sf, st];
      }
      return Math.abs(b._ocx - a._ocx) >= Math.abs(b._ocy - a._ocy) ? hPair() : vPair();
    };

    const inAll = {}, outAll = {}, inMain = {}, outMain = {};
    const bump = (store, id, side) => {
      const c = store[id] = store[id] || { top: 0, bottom: 0, left: 0, right: 0 };
      c[side]++;
    };

    g.edges.forEach((e) => {
      const [sf, st] = sidesOf(e);
      bump(outAll, e.from, sf);
      bump(inAll, e.to, st);
      if (e.kind !== "skip") {
        bump(outMain, e.from, sf);
        bump(inMain, e.to, st);
      }
    });

    const agg = (store) => {
      const out = {};
      g.nodes.forEach((n) => {
        if (!n.block) return;
        const c = store[n.id];
        if (!c) return;
        const t = out[n.block] = out[n.block] || { top: 0, bottom: 0, left: 0, right: 0 };
        ["top", "bottom", "left", "right"].forEach((s) => { t[s] += c[s]; });
      });
      return out;
    };
    const aggMax = (store) => {
      const out = {};
      g.nodes.forEach((n) => {
        if (!n.block) return;
        const c = store[n.id];
        if (!c) return;
        const t = out[n.block] = out[n.block] || { top: 0, bottom: 0, left: 0, right: 0 };
        ["top", "bottom", "left", "right"].forEach((s) => { t[s] = Math.max(t[s], c[s]); });
      });
      return out;
    };
    const inAllAgg = agg(inAll), outAllAgg = agg(outAll), inMainAgg = agg(inMain), outMainAgg = agg(outMain);
    const inMaxAgg = aggMax(inAll), outMaxAgg = aggMax(outAll);

    const pick = (c, axisSides, fallback) => {
      if (!c) return fallback;
      const best = Math.max(c.top, c.bottom, c.left, c.right);
      if (best === 0) return fallback;
      const winners = ["top", "bottom", "left", "right"].filter((s) => c[s] === best);
      const onAxis = winners.filter((s) => axisSides.includes(s));
      return (onAxis[0] || winners[0]);
    };

    const sideSet = (all, primary) => {
      const sides = ["top", "bottom", "left", "right"].filter((s) => all && all[s] > 0);
      sides.sort((a, b) => all[b] - all[a]);
      return [primary, ...sides.filter((s) => s !== primary)];
    };

    const orderFmt = (all, main) => {
      if (!all) return "";
      const sides = ["top", "bottom", "left", "right"].filter((s) => all[s] > 0);
      sides.sort((a, b) => (((main && main[b]) || 0) - ((main && main[a]) || 0)) || (all[b] - all[a]));
      return sides.map((s) => `${s}:${all[s]}`).join(",");
    };
    g.nodes.forEach((n) => {
      if (!n.block) return;
      n._flin  = orderFmt(inAll[n.id], inMain[n.id]);
      n._flout = orderFmt(outAll[n.id], outMain[n.id]);
      n._fup   = n._flin.startsWith("bottom") ? 1 : 0;
    });

    blocks.forEach((b) => {
      const allIn = inAllAgg[b.id], allOut = outAllAgg[b.id];
      if (!allIn && !allOut) return;
      const t = { top: 0, bottom: 0, left: 0, right: 0 };
      ["top", "bottom", "left", "right"].forEach((s) => { t[s] = (allIn ? allIn[s] : 0) + (allOut ? allOut[s] : 0); });
      if (!b.fan) b.horizontal = (t.left + t.right) >= (t.top + t.bottom);
      const axis = b.horizontal && !b.fan ? ["left", "right"] : ["top", "bottom"];
      const primIn  = pick(inMainAgg[b.id] || allIn, axis, b.horizontal && !b.fan ? "left" : "top");
      const primOut = pick(outMainAgg[b.id] || allOut, axis, b.horizontal && !b.fan ? "right" : "bottom");
      b.flowIn  = sideSet(allIn, primIn);
      b.flowOut = sideSet(allOut, primOut);
      b.flowInN  = inMaxAgg[b.id] || null;
      b.flowOutN = outMaxAgg[b.id] || null;
      if (!b.horizontal || b.fan) b.upward = primIn === "bottom" || (primIn !== "top" && primOut === "top");
    });
  }

  /* ---------- custom-layout networks ---------- */

  static _netCustom(g) {
    const W = g.width;
    const ord = {};
    g.nodes.forEach((n, i) => { ord[n.id] = i; });
    const box = {};
    g.nodes.forEach((n) => {
      const grid = n.type === "grid";
      const prof = n.type === "profile";
      const w = grid ? 50 : prof ? 74 : (n.w || 150);
      const h = grid ? 50 : prof ? 48 : (n.h || 50);
      box[n.id] = { x: n.cx - w / 2, y: n.cy - h / 2, w, h, cx: n.cx, cy: n.cy };
    });

    const step = 0.12;
    const settle = g.nodes.length * step + 0.2;
    let edges = "", labels = "", sk = 0;
    g.edges.forEach((e) => {
      const a = box[e.from], b = box[e.to];
      const second = e.kind === "skip";
      const t = second ? settle + 0.5 + sk++ * 0.1 : Math.max(ord[e.to] * step - 0.05, 0.05);
      let pts;
      const route = e.route || "auto";
      const hPts = () => {
        const x1 = b.cx >= a.cx ? a.x + a.w : a.x;
        const x2 = b.cx >= a.cx ? b.x : b.x + b.w;
        if (a.cy === b.cy) return [[x1, a.cy], [x2, b.cy]];
        const mx = (x1 + x2) / 2;
        return [[x1, a.cy], [mx, a.cy], [mx, b.cy], [x2, b.cy]];
      };
      const vPts = () => {
        const y1 = b.cy >= a.cy ? a.y + a.h : a.y;
        const y2 = b.cy >= a.cy ? b.y : b.y + b.h;
        if (a.cx === b.cx) return [[a.cx, y1], [b.cx, y2]];
        const my = (y1 + y2) / 2;
        return [[a.cx, y1], [a.cx, my], [b.cx, my], [b.cx, y2]];
      };
      if (route === "H") {
        pts = hPts();
      } else if (route === "V") {
        pts = vPts();
      } else if (route === "HV") {
        const sx = b.cx >= a.cx ? a.x + a.w : a.x;
        const ex = b.cx;
        pts = [[sx, a.cy], [ex, a.cy], [ex, b.cy >= a.cy ? b.y : b.y + b.h]];
      } else if (route === "VH") {
        const sy = b.cy >= a.cy ? a.y + a.h : a.y;
        pts = [[a.cx, sy], [a.cx, b.cy], [b.cx >= a.cx ? b.x : b.x + b.w, b.cy]];
      } else if (route === "P") {
        const side = (bb, sd) => sd === "top" ? [bb.cx, bb.y] : sd === "bottom" ? [bb.cx, bb.y + bb.h] : sd === "left" ? [bb.x, bb.cy] : [bb.x + bb.w, bb.cy];
        const start = e.fromPt || side(a, e.fromSide || "right");
        const end   = e.toPt || side(b, e.toSide || "left");
        pts = [start, ...(e.via || []), end];
      } else {
        const dx = Math.abs(b.cx - a.cx), dy = Math.abs(b.cy - a.cy);
        pts = dx >= dy ? hPts() : vPts();
      }
      edges += this._path(pts, second, t);
      if (e.label) {
        let bi = 0, bl = -1;
        for (let i = 0; i < pts.length - 1; i++) {
          const L = Math.abs(pts[i + 1][0] - pts[i][0]) + Math.abs(pts[i + 1][1] - pts[i][1]);
          if (L > bl) { bl = L; bi = i; }
        }
        const mx = (pts[bi][0] + pts[bi + 1][0]) / 2;
        const my = (pts[bi][1] + pts[bi + 1][1]) / 2;
        if (pts[bi][0] === pts[bi + 1][0]) labels += this._label(mx + 8, my + 3, e.label, second, "start", t);
        else labels += this._label(mx, my - 6, e.label, second, "middle", t);
      }
    });

    let nodes = "";
    g.nodes.forEach((n, i) => {
      const b = box[n.id];
      const t = i * step;
      if (n.type === "grid") nodes += this._gridStack(b.cx, b.cy, { label: n.label, sub: n.sub, out: n.out, pick: n.block }, t);
      else if (n.type === "profile") nodes += this._profileGlyph(b.cx, b.cy, { label: n.label, sub: n.sub, out: n.out }, t);
      else nodes += this._node(b.x, b.y, b.w, b.h, n.label, n.sub, n.variant || "op", t, n.block, null, settle + i * 0.05, n._flin != null ? `${n._flin};${n._flout};${n._fup}` : null);
    });

    return `<svg class="dgm dgm--net" viewBox="0 0 ${W} ${g.height}" preserveAspectRatio="xMidYMid meet" role="img">${this._defs()}${edges}${labels}${nodes}</svg>`;
  }

  static _bpStack(s) {
    const o = this._o;
    const na = this._na(s);
    const isMlp = s.key === "pixel_mlp";
    const W = 860, y = 130;

    const trunkLabel = isMlp ? "MLP layer" : "ConvBlock";
    const trunkSub1  = isMlp ? "F, RF stays 1x1" : "F, RF +4 px";
    const nodes = [
      { id: "in",  type: "grid", cx: 95,  cy: y, label: "input", sub: "Cin x P x P" },
      { id: "t1",  cx: 250, cy: y, w: 150, label: trunkLabel, sub: trunkSub1, block: "trunk" },
      { id: "t2",  cx: 420, cy: y, w: 150, label: trunkLabel, sub: isMlp ? "x L total" : "x B total", block: "trunk" },
      { id: "hd",  cx: 590, cy: y, w: 140, label: "Output head", sub: "1x1 conv", block: "head" },
      { id: "out", type: "grid", cx: 750, cy: y, out: true, label: "params", sub: "3K x P x P" },
    ];
    const edges = [
      { from: "in", to: "t1", route: "H" },
      { from: "t1", to: "t2", route: "H", label: "full res" },
      { from: "t2", to: "hd", route: "H", label: "full res" },
      { from: "hd", to: "out", route: "H" },
    ];

    const trunk = isMlp
      ? { id: "trunk", title: "Pixel MLP layer", caption: "1x1 conv, norm, act; the receptive field stays a single pixel at any depth", ops: [o.txt("Conv 1x1", "C -> F"), ...na, o.txt("Dropout2d"), o.io("output", "F x P x P")] }
      : { id: "trunk", title: "ConvBlock", caption: "double 3x3 conv at full resolution; the receptive field grows 4 px per block", ops: [o.conv("C", "F"), ...na, o.conv("F", "F"), ...na, o.io("output", "F x P x P")] };

    const blocks = [trunk, this._headBlock(s)];
    this._applyOrientation({ nodes, edges }, blocks);
    return { network: this._netCustom({ nodes, edges, width: W, height: 240 }), blocks };
  }

  static _bpSegformer(s) {
    const o = this._o;
    const headSub = s.heads === 3 ? "3 x PixelMLP" : s.heads === "K" ? "K x PixelMLP" : "1x1 conv";
    const W = 860;
    const encX = 150, projX = 370, fuseX = 600, outX = 780;
    const ys = [144, 229, 314, 399];
    const stages = ["P/4", "P/8", "P/16", "P/32"];
    const nodes = [
      { id: "in", type: "grid", cx: encX, cy: 70, label: "input", sub: "Cin x P x P" },
    ];
    stages.forEach((r, i) => {
      nodes.push({ id: "s" + i, cx: encX, cy: ys[i], w: 170, label: "Stage " + (i + 1), sub: "embed + tx, " + r, block: "enc" });
      nodes.push({ id: "p" + i, cx: projX, cy: ys[i], w: 150, label: "Conv 1x1", sub: "-> Dc, up P/4", block: "proj" });
    });
    nodes.push({ id: "fuse", cx: fuseX, cy: 272, w: 150, h: 130, label: "Concat + fuse", sub: "4 x Dc -> Dc", block: "fuse" });
    nodes.push({ id: "head", cx: outX, cy: 174, w: 130, label: "Output head", sub: headSub, block: "head" });
    nodes.push({ id: "out", type: "grid", cx: outX, cy: 70, out: true, label: "params", sub: "3K x P x P" });

    const edges = [
      { from: "in", to: "s0", route: "V" },
      { from: "s0", to: "s1", route: "V" }, { from: "s1", to: "s2", route: "V" }, { from: "s2", to: "s3", route: "V" },
    ];
    stages.forEach((_, i) => {
      edges.push({ from: "s" + i, to: "p" + i, route: "H" });
    });
    edges.push({ from: "p0", to: "fuse", route: "P", via: [[480, 144], [480, 222]], toPt: [525, 222] });
    edges.push({ from: "p1", to: "fuse", route: "P", via: [[497, 229], [497, 252]], toPt: [525, 252] });
    edges.push({ from: "p2", to: "fuse", route: "P", via: [[497, 314], [497, 292]], toPt: [525, 292] });
    edges.push({ from: "p3", to: "fuse", route: "P", via: [[480, 399], [480, 322]], toPt: [525, 322] });
    edges.push({ from: "fuse", to: "head", route: "P", via: [[780, 272]], toPt: [780, 199], toSide: "bottom" });
    edges.push({ from: "head", to: "out", route: "V" });

    const blocks = [
      { id: "enc", title: "Encoder stage", caption: "overlapping patch embed, then transformer blocks", ops: [o.txt("OverlapPatchEmbed", "strided conv"), o.txt("LayerNorm"), { label: "SegFormer block", sub: "x depth", block: "tx" }, o.io("output", "D x h x w")] },
      { id: "tx", title: "SegFormer block", caption: "efficient attention then MixFFN, each pre-norm residual", ops: [o.txt("LayerNorm"), { label: "Efficient attn", sub: "spatial-reduce KV", block: "attn" }, o.sum(), o.txt("LayerNorm"), { label: "MixFFN", sub: "DWConv 3x3", block: "ffn" }, o.sum(), o.io("output")], shortcuts: [{ from: "top", to: 2, label: "residual" }, { from: 2, to: 5, label: "residual" }] },
      { id: "attn", title: "Efficient self-attention", caption: "keys/values spatially reduced before attention", ops: [o.io("tokens x"), o.txt("SR conv", "stride R"), o.txt("LayerNorm"), o.txt("Multi-head attn", "Q=x, KV=reduced"), o.io("output")], shortcuts: [{ from: 0, to: 3, label: "query Q" }] },
      { id: "ffn", title: "MixFFN", caption: "depthwise conv injects positional signal", ops: [o.txt("Conv 1x1", "C -> hC"), o.txt("DWConv 3x3"), o.txt("GELU"), o.txt("Conv 1x1", "hC -> C"), o.io("output")] },
      { id: "proj", title: "Stage projection", caption: "1x1 conv to decoder width, upsample to P/4", ops: [o.txt("Conv 1x1", "D -> Dc"), o.txt("Upsample", "bilinear -> P/4"), o.io("output", "Dc x P/4")] },
      { id: "fuse", title: "Fuse", caption: "concat all four scales, 1x1 fuse", ops: [o.cat("concat 4 x Dc"), o.txt("Conv 1x1", "4Dc -> Dc"), o.txt("BatchNorm"), o.txt(s.act), o.txt("Upsample", "-> P"), o.io("output", "Dc x P")] },
      this._headBlock(s),
    ];
    this._applyOrientation({ nodes, edges }, blocks);
    return { network: this._netCustom({ nodes, edges, width: W, height: 455 }), blocks };
  }

  static _bpDeepLab(s) {
    const o = this._o;
    const headSub = s.heads === 3 ? "3 x PixelMLP" : s.heads === "K" ? "K x PixelMLP" : "1x1 conv";
    const W = 820;
    const encX = 140, midX = 400, decX = 620, headX = 755;
    const ys = [144, 224, 304, 384];
    const nodes = [
      { id: "in", type: "grid", cx: encX, cy: 70, label: "input", sub: "Cin x P x P" },
      { id: "stem", cx: encX, cy: ys[0], w: 150, label: "Stem", sub: "conv s2, P/2", block: "stem" },
      { id: "s1", cx: encX, cy: ys[1], w: 150, label: "Residual stage", sub: "low-level, P/2", block: "enc" },
      { id: "s2", cx: encX, cy: ys[2], w: 150, label: "Residual stage", sub: "P/4", block: "enc" },
      { id: "s3", cx: encX, cy: ys[3], w: 150, label: "Residual stage", sub: "P/8", block: "enc" },
      { id: "low", cx: midX, cy: ys[1], w: 150, label: "Conv 1x1", sub: "low-level proj", block: "low" },
      { id: "aspp", cx: midX, cy: ys[3], w: 150, h: 56, label: "ASPP", sub: "multi-rate context", block: "aspp" },
      { id: "dec", cx: decX, cy: ys[2], w: 150, h: 56, label: "Decoder", sub: "concat + 2x conv", block: "dec" },
      { id: "head", cx: headX, cy: 174, w: 130, label: "Output head", sub: headSub, block: "head" },
      { id: "out", type: "grid", cx: headX, cy: 70, out: true, label: "params", sub: "3K x P x P" },
    ];
    const edges = [
      { from: "in", to: "stem", route: "V" },
      { from: "stem", to: "s1", route: "V" }, { from: "s1", to: "s2", route: "V" }, { from: "s2", to: "s3", route: "V" },
      { from: "s3", to: "aspp", route: "H" },
      { from: "s1", to: "low", route: "H", kind: "skip", label: "low-level" },
      { from: "low", to: "dec", route: "P", via: [[decX, ys[1]]], toSide: "top", kind: "skip" },
      { from: "aspp", to: "dec", route: "P", via: [[decX, ys[3]]], toSide: "bottom" },
      { from: "dec", to: "head", route: "P", via: [[headX, ys[2]]], toPt: [headX, 199] },
      { from: "head", to: "out", route: "V" },
    ];
    const blocks = [
      { id: "stem", title: "Stem", caption: "stride-2 conv halves the input", ops: [o.txt("Conv 3x3 s2", "down"), ...this._na(s), o.io("output", "F1 x P/2")] },
      { id: "enc", title: "Residual stage", caption: "ResUNet residual block (+ pool between deeper stages)", ops: [...this._na(s), o.conv("Cin", "F"), ...this._na(s), o.conv("F", "F"), o.sum(), o.io("output")], shortcuts: [{ from: "top", to: this._na(s).length * 2 + 2, label: "Proj", op: "Conv 1x1" }] },
      { id: "aspp", title: "ASPP", caption: "parallel dilated branches plus image pooling, concat then project", ops: [o.io("encoder features"), { label: "Branches x5", sub: "1x1, r=1,2,4, pool", block: "asppb" }, o.cat("concat branches"), o.txt("Conv 1x1", "project + dropout"), o.io("output", "F4/2 x P/8")] },
      { id: "asppb", title: "ASPP branches", caption: "five parallel context branches at one resolution", ops: [o.txt("Conv 1x1"), o.txt("Conv 3x3", "dilation 1"), o.txt("Conv 3x3", "dilation 2"), o.txt("Conv 3x3", "dilation 4"), o.txt("Image pool", "GAP, 1x1, GN, act, up"), o.io("5 branch maps")] },
      { id: "low", title: "Low-level projection", caption: "1x1 conv reduces stride-2 features", ops: [o.txt("Conv 1x1", "F1 -> F1/2"), ...this._na(s), o.io("output", "low-level")] },
      { id: "dec", title: "Decoder", caption: "upsample ASPP, concat low-level, refine, upsample to full res", ops: [o.txt("Upsample", "ASPP -> P/2"), o.cat(), o.txt("Conv 3x3"), o.txt("Conv 3x3"), o.txt("Upsample", "-> P"), o.io("output", "F4/2 x P")] },
      this._headBlock(s),
    ];
    this._applyOrientation({ nodes, edges }, blocks);
    return { network: this._netCustom({ nodes, edges, width: W, height: 455 }), blocks };
  }

  static _bpHRNet(s) {
    const o = this._o;
    const headSub = s.heads === 3 ? "3 x PixelMLP" : s.heads === "K" ? "K x PixelMLP" : "1x1 conv";
    const W = 860;
    const rows = [144, 264, 384];
    const stemX = 140, s2X = 310, exX = 430, s3X = 550, fuseX = 740;
    const nodes = [
      { id: "in", type: "grid", cx: stemX, cy: 70, label: "input", sub: "Cin x P x P" },
      { id: "stem", cx: stemX, cy: rows[0], w: 140, label: "Stem", sub: "residual, P, C", block: "stem" },
      { id: "b0s2", cx: s2X, cy: rows[0], w: 130, label: "Branch P", sub: "residual, C", block: "stage" },
      { id: "b1s2", cx: s2X, cy: rows[1], w: 130, label: "Branch P/2", sub: "residual, 2C", block: "stage" },
      { id: "ex", cx: exX, cy: (rows[0] + rows[1]) / 2, w: 80, h: rows[1] - rows[0] + 50, label: "Fuse", sub: "exchange", block: "fuse" },
      { id: "b0s3", cx: s3X, cy: rows[0], w: 130, label: "Branch P", sub: "residual, C", block: "stage" },
      { id: "b1s3", cx: s3X, cy: rows[1], w: 130, label: "Branch P/2", sub: "residual, 2C", block: "stage" },
      { id: "b2s3", cx: s3X, cy: rows[2], w: 130, label: "Branch P/4", sub: "residual, 4C", block: "stage" },
      { id: "fuse", cx: fuseX, cy: rows[1], w: 150, h: 64, label: "Upsample concat", sub: "all -> P, fuse 3x3", block: "head_fuse" },
      { id: "head", cx: fuseX, cy: 154, w: 130, label: "Output head", sub: headSub, block: "head" },
      { id: "out", type: "grid", cx: fuseX, cy: 70, out: true, label: "params", sub: "3K x P x P" },
    ];
    const edges = [
      { from: "in", to: "stem", route: "V" },
      { from: "stem", to: "b0s2", route: "H" },
      { from: "stem", to: "b1s2", route: "P", fromSide: "bottom", via: [[stemX, rows[1]]], label: "stride 2" },
      { from: "b0s2", to: "ex", route: "P", toPt: [exX - 40, rows[0]] },
      { from: "b1s2", to: "ex", route: "P", toPt: [exX - 40, rows[1]] },
      { from: "ex", to: "b0s3", route: "P", fromPt: [exX + 40, rows[0]] },
      { from: "ex", to: "b1s3", route: "P", fromPt: [exX + 40, rows[1]] },
      { from: "ex", to: "b2s3", route: "P", fromSide: "bottom", via: [[exX, rows[2]]], label: "stride 2" },
      { from: "b0s3", to: "fuse", route: "P", via: [[625, rows[0]], [625, rows[1] - 20]], toPt: [665, rows[1] - 20], kind: "skip" },
      { from: "b1s3", to: "fuse", route: "H", kind: "skip" },
      { from: "b2s3", to: "fuse", route: "P", via: [[640, rows[2]], [640, rows[1] + 20]], toPt: [665, rows[1] + 20], kind: "skip" },
      { from: "fuse", to: "head", route: "V" },
      { from: "head", to: "out", route: "V" },
    ];
    const blocks = [
      { id: "stem", title: "Stem", caption: "residual block, full-resolution branch at C", ops: [...this._na(s), o.conv("Cin", "C"), ...this._na(s), o.conv("C", "C"), o.sum(), o.io("output", "C x P")], shortcuts: [{ from: "top", to: this._na(s).length * 2 + 2, label: "Proj", op: "Conv 1x1" }] },
      { id: "stage", title: "Stage block", caption: "residual blocks per branch at its resolution", ops: [{ label: "Residual block", sub: "x blocks_per_stage" }, o.io("output")] },
      { id: "fuse", title: "Branch fusion", caption: "every branch becomes the sum of all branches resampled to its resolution", ops: [o.io("all branches"), { label: "Down branch", sub: "3x3 stride 2" }, { label: "Up branch", sub: "1x1 + bilinear" }, o.sum(), o.txt(s.act), o.io("fused branch")] },
      { id: "head_fuse", title: "Fusion head", caption: "upsample all branches to full res, concat, fuse 3x3", ops: [o.txt("Upsample", "all -> P"), o.cat("concat branches"), o.txt("Conv 3x3"), ...this._na(s), o.io("output", "2C x P")] },
      this._headBlock(s),
    ];
    this._applyOrientation({ nodes, edges }, blocks);
    return { network: this._netCustom({ nodes, edges, width: W, height: 450 }), blocks };
  }

  static _bpFPN(s) {
    const o = this._o;
    const headSub = s.heads === 3 ? "3 x PixelMLP" : s.heads === "K" ? "K x PixelMLP" : "1x1 conv";
    const W = 860;
    const upX = 150, downX = 370, segX = 565, fuseX = 770;
    const ys = [144, 234, 324, 414];
    const levels = ["P", "P/2", "P/4", "P/8"];
    const nodes = [{ id: "in", type: "grid", cx: upX, cy: 70, label: "input", sub: "Cin x P x P" }];
    levels.forEach((r, i) => {
      nodes.push({ id: "c" + i, cx: upX, cy: ys[i], w: 150, label: "Residual stage", sub: r, block: "enc" });
      nodes.push({ id: "p" + i, cx: downX, cy: ys[i], w: 150, label: "Pyramid " + r, sub: "1x1 + add + 3x3", block: "topdown" });
      nodes.push({ id: "g" + i, cx: segX, cy: ys[i], w: 130, label: "Seg block", sub: i === 0 ? "conv only" : i + "x up", block: "seg" });
    });
    nodes.push({ id: "fuse", cx: fuseX, cy: 279, w: 140, h: 130, label: "Sum + fuse", sub: "4 levels -> Cp", block: "fuse" });
    nodes.push({ id: "head", cx: fuseX, cy: 164, w: 130, label: "Output head", sub: headSub, block: "head" });
    nodes.push({ id: "out", type: "grid", cx: fuseX, cy: 70, out: true, label: "params", sub: "3K x P x P" });

    const edges = [{ from: "in", to: "c0", route: "V" }];
    levels.forEach((_, i) => {
      if (i < levels.length - 1) edges.push({ from: "c" + i, to: "c" + (i + 1), route: "V", label: "pool" });
      edges.push({ from: "c" + i, to: "p" + i, route: "H", label: i === 0 ? "lateral" : null });
      if (i < levels.length - 1) edges.push({ from: "p" + (i + 1), to: "p" + i, route: "V", kind: "skip", label: i === 0 ? "up + add" : null });
      edges.push({ from: "p" + i, to: "g" + i, route: "H" });
    });
    edges.push({ from: "g0", to: "fuse", route: "P", via: [[655, ys[0]], [655, 224]], toPt: [700, 224] });
    edges.push({ from: "g1", to: "fuse", route: "P", via: [[672, ys[1]], [672, 261]], toPt: [700, 261] });
    edges.push({ from: "g2", to: "fuse", route: "P", via: [[672, ys[2]], [672, 297]], toPt: [700, 297] });
    edges.push({ from: "g3", to: "fuse", route: "P", via: [[655, ys[3]], [655, 334]], toPt: [700, 334] });
    edges.push({ from: "fuse", to: "head", route: "V" });
    edges.push({ from: "head", to: "out", route: "V" });

    const blocks = [
      { id: "enc", title: "Bottom-up stage", caption: "residual block (pool between levels)", ops: [...this._na(s), o.conv("Cin", "F"), ...this._na(s), o.conv("F", "F"), o.sum(), o.io("output")], shortcuts: [{ from: "top", to: this._na(s).length * 2 + 2, label: "Proj", op: "Conv 1x1" }] },
      { id: "topdown", title: "Top-down pathway", caption: "lateral 1x1 plus upsampled coarser level, smooth 3x3", ops: [o.txt("Conv 1x1", "lateral -> Cp"), o.sum(), o.txt("Conv 3x3", "smooth"), o.io("pyramid level", "Cp")], shortcuts: [{ from: "top", to: 1, label: "up(p_i+1)", op: "Upsample" }] },
      { id: "seg", title: "Segmentation block", caption: "N = log2(stride/target) interleaved stages: conv stack then 2x upsample; shallowest level is conv-only", ops: [{ label: "Conv 3x3", sub: "x convs_per_stage" }, ...this._na(s), o.txt("Upsample 2x", "x N stages"), o.io("output", "Cp x P")] },
      { id: "fuse", title: "Sum + fuse", caption: "sum the four pyramid levels, fuse, dropout", ops: [o.sum(), o.txt("Conv 3x3"), ...this._na(s), o.txt("Dropout"), o.io("output", "Cp x P")] },
      this._headBlock(s),
    ];
    this._applyOrientation({ nodes, edges }, blocks);
    return { network: this._netCustom({ nodes, edges, width: W, height: 475 }), blocks };
  }

  /* ---------- autoencoders ---------- */

  static buildAE(model, kind) {
    const spec = this._aeSpec(model, kind);
    const blocks = {};
    spec.blocks.forEach((b) => { blocks[b.id] = b; });
    const network =
      `<figure class="dgm-net"><div class="dgm-frame dgm-frame--net">${this._aeNetwork(spec)}</div>` +
      `<figcaption class="dgm-hint">Click any block to zoom into its operations</figcaption></figure>`;
    return { network, blocks };
  }

  static _aeNetwork(spec) {
    const image = spec.io === "image";
    const inNode = image
      ? { id: "in", type: "grid", cx: 165, cy: 74, label: "input", sub: spec.inSub }
      : { id: "in", type: "profile", cx: 165, cy: 74, label: spec.inLabel, sub: spec.inSub };
    const outNode = image
      ? { id: "out", type: "grid", cx: 555, cy: 74, out: true, label: "reconstruction", sub: spec.outSub }
      : { id: "out", type: "profile", cx: 555, cy: 74, out: true, label: spec.outLabel, sub: spec.outSub };

    const enc    = { id: "enc", cx: 165, cy: 212, w: 158, h: 66, label: "Encoder", sub: spec.encSub, block: "enc" };
    const latent = { id: "latent", cx: 360, cy: 350, w: 152, h: 56, variant: "latent", label: spec.zLabel, sub: spec.zSub, block: "latent" };
    const dec    = { id: "dec", cx: 555, cy: 212, w: 158, h: 66, label: "Decoder", sub: spec.decSub, block: "dec" };

    const nodes = [inNode, enc, latent, dec, outNode];
    const edges = [
      { from: "in", to: "enc", route: "V" },
      { from: "enc", to: "latent", route: "VH", label: "compress" },
      { from: "latent", to: "dec", route: "HV", label: "reconstruct" },
      { from: "dec", to: "out", route: "V" },
    ];
    this._applyOrientation({ nodes, edges }, spec.blocks);
    return this._netCustom({ nodes, edges, width: 720, height: 432 });
  }

  static _aeSpec(model, kind) {
    const o = this._o;
    const s = this.spec(model);
    const na = this._na(s);
    const norm = s.norm || "Norm";
    const act = s.act;
    const image = kind === "image_autoencoder";

    const latent = (zLabel, zSub) => ({
      id: "latent", title: "Embedding",
      caption: image
        ? "the compressed 2D code: the encoder output and decoder input; the trained encoder seeds the JEPA image front-end"
        : "the compressed code: the encoder output and decoder input; the trained encoder defines the JEPA target space",
      ops: image
        ? [o.io("encoder features"), o.txt("Conv 1x1", "-> embedding"), o.io(zLabel, zSub)]
        : [o.io("encoder output"), o.txt("LayerNorm", "normalize z"), o.io(zLabel, zSub)],
    });

    if (!image) {
      const base = { io: "profile", inLabel: "Profile", inSub: "1 x 256", outLabel: "Reconstruction", outSub: "1 x 256", zLabel: "Embedding", zSub: "24-d" };
      const zEnd = o.io("embedding z", "24-d");
      const zStart = o.io("embedding z", "24-d");
      const inIo = o.io("profile", "1 x 256");
      const outIo = o.io("profile", "1 x 256");

      if (model.key === "mlp_ae") {
        const dl = { id: "mlpd", title: "Dense layer", caption: "linear projection, activation, dropout", ops: [o.txt("Linear", "-> 512"), o.act(act), o.txt("Dropout"), o.io("output")] };
        const enc = { id: "enc", title: "Encoder", caption: "stacked dense layers compress the flat profile, then a linear projects to the embedding", ops: [inIo, { label: "Dense layer", sub: "x4", block: "mlpd" }, o.txt("Linear", "512 -> 24"), zEnd] };
        const dec = { id: "dec", title: "Decoder", caption: "mirror of the encoder: expand from the embedding back to the profile", ops: [zStart, o.txt("Linear", "24 -> 512"), { label: "Dense layer", sub: "x4", block: "mlpd" }, o.txt("Linear", "512 -> 256"), outIo] };
        return { ...base, encSub: "Linear x4, 512", decSub: "Linear x4, 512", blocks: [enc, dec, dl, latent(base.zLabel, base.zSub)] };
      }

      if (model.key === "conv1d_ae") {
        const enc = { id: "enc", title: "Encoder", caption: "two 1D convolutions over the range axis, global pool, then project to the embedding", ops: [inIo, o.txt("Conv1d k5", "1 -> 192"), o.act(act), o.txt("Conv1d k5", "192 -> 192"), o.act(act), o.txt("Global avg-pool", "-> 1"), o.txt("Linear", "192 -> 24"), zEnd] };
        const dec = { id: "dec", title: "Decoder", caption: "expand the embedding to a sequence, then two 1D convolutions back to the profile", ops: [zStart, o.txt("Linear", "24 -> 192 x 256"), o.txt("Reshape", "192 x 256"), o.txt("Conv1d k5", "192 -> 192"), o.act(act), o.txt("Conv1d k5", "192 -> 1"), outIo] };
        return { ...base, encSub: "Conv k5 x2", decSub: "Conv k5 x2", blocks: [enc, dec, latent(base.zLabel, base.zSub)] };
      }

      if (model.key === "transformer1d_ae") {
        const txl = { id: "txl", title: "Transformer layer", caption: "attention over a single token, so it reduces to a value-output projection, then feed-forward, each with a residual add and post-norm", ops: [o.txt("Self-attention", "1 token"), o.sum(), o.txt("LayerNorm"), o.txt("FFN", "192 -> 384 -> 192, GELU"), o.sum(), o.txt("LayerNorm"), o.io("output")], shortcuts: [{ from: "top", to: 1, label: "res" }, { from: 2, to: 4, label: "res" }] };
        const enc = { id: "enc", title: "Encoder", caption: "embed the whole profile into one token, run the transformer stack, then project to the embedding", ops: [inIo, o.txt("Linear", "256 -> 192"), { label: "Transformer layer", sub: "x3", block: "txl" }, o.txt("Linear", "192 -> 24"), zEnd] };
        const dec = { id: "dec", title: "Decoder", caption: "mirror of the encoder: one token, transformer stack, then project to the profile", ops: [zStart, o.txt("Linear", "24 -> 192"), { label: "Transformer layer", sub: "x3", block: "txl" }, o.txt("Linear", "192 -> 256"), outIo] };
        return { ...base, encSub: "Transformer x3", decSub: "Transformer x3", blocks: [enc, dec, txl, latent(base.zLabel, base.zSub)] };
      }

      if (model.key === "resmlp_ae") {
        const rmb = { id: "rmb", title: "Residual MLP block", caption: "pre-norm two-layer MLP with a residual skip", ops: [o.txt("LayerNorm"), o.txt("Linear", "384 -> 384"), o.act(act), o.txt("Linear", "384 -> 384"), o.sum(), o.io("output")], shortcuts: [{ from: "top", to: 4, label: "residual" }] };
        const enc = { id: "enc", title: "Encoder", caption: "embed the profile, refine through residual MLP blocks, project to the embedding", ops: [inIo, o.txt("Linear", "256 -> 384"), { label: "Residual MLP block", sub: "x3", block: "rmb" }, o.txt("Linear", "384 -> 24"), zEnd] };
        const dec = { id: "dec", title: "Decoder", caption: "mirror of the encoder back to the profile", ops: [zStart, o.txt("Linear", "24 -> 384"), { label: "Residual MLP block", sub: "x3", block: "rmb" }, o.txt("Linear", "384 -> 256"), outIo] };
        return { ...base, encSub: "ResMLP x3, 384", decSub: "ResMLP x3, 384", blocks: [enc, dec, rmb, latent(base.zLabel, base.zSub)] };
      }

      if (model.key === "tcn_ae") {
        const drb = { id: "drb", title: "Dilated residual block", caption: "two dilated 3x3 convs with a residual add; dilation grows as 2^i", ops: [o.txt("Conv1d k3", "d=2^i"), o.act(act), o.txt("Dropout"), o.txt("Conv1d k3", "d=2^i"), o.sum(), o.act(act), o.io("output")], shortcuts: [{ from: "top", to: 4, label: "residual" }] };
        const enc = { id: "enc", title: "Encoder", caption: "stem conv, dilated residual stack growing the receptive field, global pool, project", ops: [inIo, o.txt("Conv1d k3", "1 -> 128"), { label: "Dilated residual", sub: "x4, d=1,2,4,8", block: "drb" }, o.txt("Global avg-pool", "-> 1"), o.txt("Linear", "128 -> 24"), zEnd] };
        const dec = { id: "dec", title: "Decoder", caption: "expand to a sequence, mirror dilated residual stack, conv back to the profile", ops: [zStart, o.txt("Linear", "24 -> 128 x 256"), o.txt("Reshape", "128 x 256"), { label: "Dilated residual", sub: "x4", block: "drb" }, o.txt("Conv1d k3", "128 -> 1"), outIo] };
        return { ...base, encSub: "Dilated x4", decSub: "Dilated x4", blocks: [enc, dec, drb, latent(base.zLabel, base.zSub)] };
      }

      if (model.key === "gru_ae") {
        const enc = { id: "enc", title: "Encoder", caption: "a bidirectional GRU sweeps the profile; the final hidden state is projected to the embedding", ops: [inIo, o.txt("Reshape", "256 x 1"), { label: "BiGRU", sub: "2 layers, h=224", block: "grub" }, o.txt("Last hidden", "2 x 224"), o.txt("Linear", "448 -> 24"), zEnd] };
        const dec = { id: "dec", title: "Decoder", caption: "broadcast the embedding over the sequence and unroll a GRU back to the profile", ops: [zStart, o.txt("Linear", "24 -> 224"), o.txt("Expand", "256 x 224"), { label: "GRU", sub: "2 layers, h=224", block: "grud" }, o.txt("Linear", "224 -> 1"), outIo] };
        const grub = { id: "grub", title: "Bidirectional GRU", caption: "two stacked bidirectional GRU layers read the sequence both ways", ops: [o.txt("GRU layer", "forward + backward"), o.txt("GRU layer", "forward + backward"), o.io("hidden states")] };
        const grud = { id: "grud", title: "GRU decoder", caption: "two stacked unidirectional GRU layers unroll the embedding", ops: [o.txt("GRU layer"), o.txt("GRU layer"), o.io("output sequence", "256 x 224")] };
        return { ...base, encSub: "BiGRU x2", decSub: "GRU x2", blocks: [enc, dec, grub, grud, latent(base.zLabel, base.zSub)] };
      }

      if (model.key === "cnn_attn_ae") {
        const txb = { id: "txb", title: "Transformer block", caption: "pre-norm self-attention then feed-forward, each with a residual add", ops: [o.txt("LayerNorm"), o.txt("Multi-head attn", "4 heads"), o.sum(), o.txt("LayerNorm"), o.txt("FFN", "192 -> 768 -> 192, GELU"), o.sum(), o.io("output")], shortcuts: [{ from: "top", to: 2, label: "residual" }, { from: 2, to: 5, label: "residual" }] };
        const enc = { id: "enc", title: "Encoder", caption: "conv stem, tokenize into patches, relate tokens with attention, pool and project", ops: [inIo, o.txt("Conv1d k5", "1 -> 32"), o.act(act), o.txt("Tokenize", "patch 8 -> 32 tokens"), o.txt("+ Pos embed"), { label: "Transformer block", sub: "x2", block: "txb" }, o.txt("Mean pool", "over tokens"), o.txt("Linear", "192 -> 24"), zEnd] };
        const dec = { id: "dec", title: "Decoder", caption: "broadcast over tokens, attention, then map tokens back to the profile", ops: [zStart, o.txt("Linear", "24 -> 192"), o.txt("Expand", "32 tokens"), o.txt("+ Pos embed"), { label: "Transformer block", sub: "x2", block: "txb" }, o.txt("Linear", "-> patch 8"), o.txt("Reshape + Linear", "-> 256"), outIo] };
        return { ...base, encSub: "Tokens + attn x2", decSub: "Attn x2", blocks: [enc, dec, txb, latent(base.zLabel, base.zSub)] };
      }
    }

    const base = { io: "image", inSub: "Cin x H x W", outSub: "Cin x H x W", zLabel: "2D embedding" };
    const inIo = o.io("image stack", "Cin x H x W");
    const outIo = o.io("reconstruction", "Cin x H x W");

    if (model.key === "conv2d_ae") {
      const zSub = "24 x H x W";
      const cb = { id: "cb", title: "Conv block", caption: "two 3x3 convolutions, each followed by normalization and activation", ops: [o.conv("Cin", "C"), ...na, o.conv("C", "C"), ...na, o.io("output")] };
      const enc = { id: "enc", title: "Encoder", caption: "stacked double-conv blocks, then a 1x1 to the embedding; strided downsample stages are inserted when downsample_factor > 1", ops: [inIo, { label: "Conv block", sub: "x2", block: "cb" }, o.txt("Conv 1x1", "-> 24 ch"), o.io("2D embedding", zSub)] };
      const dec = { id: "dec", title: "Decoder", caption: "project from the embedding, refine with conv blocks, 1x1 back to the stack (upsample stages mirror any encoder downsampling)", ops: [o.io("2D embedding", zSub), o.txt("Conv 1x1", "24 -> C"), { label: "Conv block", sub: "refine", block: "cb" }, o.txt("Conv 1x1", "C -> Cin"), outIo] };
      return { ...base, zSub, encSub: "Conv blocks x2", decSub: "Conv blocks", blocks: [enc, dec, cb, latent(base.zLabel, zSub)] };
    }

    if (model.key === "resnet2d_ae") {
      const zSub = "24 x H/2 x W/2";
      const rb = { id: "rb", title: "Residual block", caption: "pre-activation residual block with a 1x1 projection shortcut", ops: [...na, o.conv("Cin", "C"), ...na, o.conv("C", "C"), o.sum(), o.io("output")], shortcuts: [{ from: "top", to: na.length * 2 + 2, label: "Proj", op: "Conv 1x1" }] };
      const rdown = { id: "rdown", title: "Downsample stage", caption: "a stride-2 residual block doubles channels and halves resolution", ops: [{ label: "Residual block s2", sub: "down, x2 ch" }, o.io("output", "2C x H/2")] };
      const rup = { id: "rup", title: "Upsample stage", caption: "transposed conv doubles resolution and halves channels, then a residual block", ops: [o.txt("ConvT 2x2", "up, C/2"), { label: "Residual block", block: "rb" }, o.io("output")] };
      const enc = { id: "enc", title: "Encoder", caption: "residual blocks, a stride-2 downsample stage, then a 1x1 to the embedding", ops: [inIo, { label: "Residual block", sub: "x2", block: "rb" }, { label: "Downsample", sub: "stride 2", block: "rdown" }, o.txt("Conv 1x1", "-> 24 ch"), o.io("2D embedding", zSub)] };
      const dec = { id: "dec", title: "Decoder", caption: "project, an upsample stage, refine residual blocks, 1x1 back to the stack", ops: [o.io("2D embedding", zSub), o.txt("Conv 1x1", "24 -> C"), { label: "Upsample", sub: "x1", block: "rup" }, { label: "Residual block", sub: "refine", block: "rb" }, o.txt("Conv 1x1", "C -> Cin"), outIo] };
      return { ...base, zSub, encSub: "Residual, /2", decSub: "Residual, up", blocks: [enc, dec, rb, rdown, rup, latent(base.zLabel, zSub)] };
    }

    if (model.key === "convnext2d_ae") {
      const zSub = "24 x H/2 x W/2";
      const cnx = { id: "cnx", title: "ConvNeXt block", caption: "depthwise 7x7, layer norm, inverted-bottleneck MLP, layer scale, residual", ops: [o.txt("DWConv 7x7", "per-channel"), o.txt("LayerNorm"), o.txt("Linear", "C -> 4C"), o.act("GELU"), o.txt("Linear", "4C -> C"), o.txt("Layer Scale", "gamma"), o.sum(), o.io("output")], shortcuts: [{ from: "top", to: 6, label: "residual" }] };
      const cndown = { id: "cndown", title: "Downsample stage", caption: "channel layer norm, strided 2x2 conv, then ConvNeXt blocks", ops: [o.txt("LayerNorm"), o.txt("Conv 2x2 s2", "down, x2 ch"), { label: "ConvNeXt block", sub: "x2", block: "cnx" }, o.io("output", "2C x H/2")] };
      const cnup = { id: "cnup", title: "Upsample stage", caption: "transposed conv up, then ConvNeXt blocks", ops: [o.txt("ConvT 2x2", "up, C/2"), { label: "ConvNeXt block", block: "cnx" }, o.io("output")] };
      const enc = { id: "enc", title: "Encoder", caption: "3x3 stem, ConvNeXt blocks, a stride-2 downsample stage, then a 1x1 to the embedding", ops: [inIo, o.txt("Conv 3x3", "stem -> C"), { label: "ConvNeXt block", sub: "x2", block: "cnx" }, { label: "Downsample", sub: "stride 2", block: "cndown" }, o.txt("Conv 1x1", "-> 24 ch"), o.io("2D embedding", zSub)] };
      const dec = { id: "dec", title: "Decoder", caption: "project, an upsample stage, refine ConvNeXt blocks, 1x1 back to the stack", ops: [o.io("2D embedding", zSub), o.txt("Conv 1x1", "24 -> C"), { label: "Upsample", sub: "x1", block: "cnup" }, { label: "ConvNeXt block", sub: "refine", block: "cnx" }, o.txt("Conv 1x1", "C -> Cin"), outIo] };
      return { ...base, zSub, encSub: "ConvNeXt, /2", decSub: "ConvNeXt, up", blocks: [enc, dec, cnx, cndown, cnup, latent(base.zLabel, zSub)] };
    }

    if (model.key === "dilated2d_ae") {
      const zSub = "24 x H x W";
      const drb = { id: "drb", title: "Dilated residual block", caption: "two dilated 3x3 convs with a residual add; no downsampling, dilation grows as 2^i", ops: [o.txt("Conv 3x3", "d=2^i"), o.txt(norm), o.act(act), o.txt("Conv 3x3", "d=2^i"), o.txt(norm), o.sum(), o.act(act), o.io("output")], shortcuts: [{ from: "top", to: 5, label: "residual" }] };
      const enc = { id: "enc", title: "Encoder", caption: "3x3 stem, dilated residual stack at full resolution, then a 1x1 to the embedding", ops: [inIo, o.txt("Conv 3x3", "stem -> C"), ...na, { label: "Dilated residual", sub: "x3, d=1,2,4", block: "drb" }, o.txt("Conv 1x1", "-> 24 ch"), o.io("2D embedding", zSub)] };
      const dec = { id: "dec", title: "Decoder", caption: "project, mirror the dilated residual stack, 1x1 back to the stack; resolution never changes", ops: [o.io("2D embedding", zSub), o.txt("Conv 1x1", "24 -> C"), { label: "Dilated residual", sub: "x3", block: "drb" }, o.txt("Conv 1x1", "C -> Cin"), outIo] };
      return { ...base, zSub, encSub: "Dilated x3, full res", decSub: "Dilated x3", blocks: [enc, dec, drb, latent(base.zLabel, zSub)] };
    }

    const zSub = "24 x H/8 x W/8";
    const vtb = { id: "vtb", title: "Transformer block", caption: "pre-norm self-attention then MLP, each with a residual add", ops: [o.txt("LayerNorm"), o.txt("Multi-head attn", "6 heads"), o.sum(), o.txt("LayerNorm"), o.txt("MLP", "D -> 4D -> D, GELU"), o.sum(), o.io("output")], shortcuts: [{ from: "top", to: 2, label: "residual" }, { from: 2, to: 5, label: "residual" }] };
    const enc = { id: "enc", title: "Encoder", caption: "patch-embed into tokens, add convolutional positional encoding, transformer blocks, then a 1x1 to the embedding", ops: [inIo, o.txt("PatchEmbed", "conv s8 -> tokens"), o.txt("LayerNorm"), o.txt("Pos encode", "DWConv 3x3"), { label: "Transformer block", sub: "x4", block: "vtb" }, o.txt("LayerNorm"), o.txt("Conv 1x1", "-> 24 ch"), o.io("2D embedding", zSub)] };
    const dec = { id: "dec", title: "Decoder", caption: "project to tokens, positional encoding, transformer blocks, then un-patch back to the stack", ops: [o.io("2D embedding", zSub), o.txt("Conv 1x1", "24 -> D"), o.txt("Pos encode", "DWConv 3x3"), { label: "Transformer block", sub: "x4", block: "vtb" }, o.txt("LayerNorm"), o.txt("Unpatch", "ConvT s8"), outIo] };
    return { ...base, zSub, encSub: "Patch + Tx x4", decSub: "Tx x4 + unpatch", blocks: [enc, dec, vtb, latent(base.zLabel, zSub)] };
  }

  /* ---------- JEPA composites ---------- */

  static buildJepa(model) {
    const bp = model.key === "jepa_image"   ? this._jepaImage()
             : model.key === "jepa_profile" ? this._jepaProfile()
             :                                this._jepaFull();
    const blocks = {};
    bp.blocks.forEach((b) => { blocks[b.id] = b; });
    const network =
      `<figure class="dgm-net dgm-net--wide"><div class="dgm-frame dgm-frame--net">${bp.network}</div>` +
      `<figcaption class="dgm-hint">Click any subsystem to expand its full architecture</figcaption></figure>`;
    return { network, blocks };
  }

  static _prefix(blocks, p) {
    const idmap = {};
    blocks.forEach((b) => { idmap[b.id] = p + b.id; });
    return blocks.map((b) => {
      const nb = Object.assign({}, b, { id: p + b.id });
      if (b.ops) nb.ops = b.ops.map((op) => (op.block && idmap[op.block]) ? Object.assign({}, op, { block: idmap[op.block] }) : op);
      return nb;
    });
  }

  static _jepaBackboneBlocks(inLabel, inSub, outLabel, outSub, headCaption) {
    const o = this._o;
    const s = this.spec({ key: "resunet", skip: "residual", head: "single", family: "resunet", activation: "relu", normalization: "batch" });
    const raw = this._blocks(s).filter((b) => ["enc", "bridge", "dec"].includes(b.id));
    const blocks = this._prefix(raw, "bb_");
    blocks.push({ id: "bb_head", title: "Output head", caption: headCaption, ops: [o.txt("Conv 1x1", outSub), o.io(outLabel, outSub)] });
    const wrapper = {
      id: "backbone", title: "Backbone predictor — ResU-Net",
      caption: "the supervised backbone (default ResU-Net; any backbone-zoo model can be swapped in) maps the input grid to a dense per-pixel output",
      ops: [
        o.io(inLabel, inSub),
        { label: "Encoder stage", sub: "x4, residual + downsample", block: "bb_enc" },
        { label: "Bridge", sub: "residual bottleneck", block: "bb_bridge" },
        { label: "Decoder stage", sub: "x4, up-conv + skip concat", block: "bb_dec" },
        { label: "Output head", sub: outSub, block: "bb_head" },
        o.io(outLabel, outSub),
      ],
    };
    return [wrapper, ...blocks];
  }

  static _jepaImageEncBlocks() {
    const spec = this._aeSpec({ key: "conv2d_ae", skip: "2D conv encoder/decoder", head: "Conv to 2D embedding", activation: "gelu", normalization: "batch" }, "image_autoencoder");
    const enc  = spec.blocks.find((b) => b.id === "enc");
    const cb   = spec.blocks.find((b) => b.id === "cb");
    const pref = this._prefix([enc, cb], "img_");
    const encB = pref.find((b) => b.id === "img_enc");
    encB.title   = "Image AE encoder (front-end)";
    encB.caption = "the pretrained image-autoencoder encoder (default Conv2D; any image-AE-zoo model), frozen or fine-tuned; encode_features returns the encoded stack at the input resolution to feed the backbone";
    return pref;
  }

  static _jepaProfileBlocks() {
    const spec = this._aeSpec({ key: "mlp_ae", skip: "Symmetric MLP", head: "Dense to embedding", activation: "gelu", normalization: "none" }, "autoencoder");
    const enc  = spec.blocks.find((b) => b.id === "enc");
    const dec  = spec.blocks.find((b) => b.id === "dec");
    const mlpd = spec.blocks.find((b) => b.id === "mlpd");
    const pref = this._prefix([enc, dec, mlpd], "prof_");
    const encB = pref.find((b) => b.id === "prof_enc");
    encB.title   = "Profile AE encoder (target)";
    encB.caption = "the pretrained profile-autoencoder encoder (default MLP; any profile-AE-zoo model) defines the target space; run under stop-grad (or as an EMA copy) on the reconstructed GT profile to produce z*";
    const decB = pref.find((b) => b.id === "prof_dec");
    decB.title   = "Profile AE decoder (curve recon)";
    decB.caption = "the pretrained profile-autoencoder decoder maps the predicted embedding back to a profile for the reconstruction loss";
    return pref;
  }

  static _jepaImage() {
    const bb = this._jepaBackboneBlocks("encoded stack", "Dimg x P x P", "Gaussian params", "3K x P x P", "1x1 conv to the 3K Gaussian parameters");
    const img = this._jepaImageEncBlocks();
    const blocks = [...img, ...bb];
    const nodes = [
      { id: "in", type: "grid", cx: 95, cy: 150, label: "input stack", sub: "Cin x P x P" },
      { id: "imgenc", cx: 312, cy: 150, w: 196, h: 66, label: "Image AE encoder", sub: "frozen front-end", block: "img_enc" },
      { id: "feat", cx: 528, cy: 150, w: 156, h: 54, variant: "io", label: "encoded stack", sub: "Dimg x P x P" },
      { id: "bb", cx: 736, cy: 150, w: 184, h: 66, label: "Backbone", sub: "ResU-Net predictor", block: "backbone" },
      { id: "params", cx: 952, cy: 150, w: 156, h: 54, variant: "io", label: "Gaussian params", sub: "3K x P x P" },
      { id: "ploss", cx: 1130, cy: 150, w: 152, h: 60, variant: "loss", label: "Parameter L1", sub: "vs GT params" },
      { id: "gt", cx: 1130, cy: 312, w: 156, h: 54, variant: "io", label: "GT params", sub: "3K x P x P" },
    ];
    const edges = [
      { from: "in", to: "imgenc", route: "H" }, { from: "imgenc", to: "feat", route: "H" }, { from: "feat", to: "bb", route: "H" },
      { from: "bb", to: "params", route: "H" }, { from: "params", to: "ploss", route: "H" },
      { from: "gt", to: "ploss", route: "V", label: "target" },
    ];
    return { network: this._netCustom({ nodes, edges, width: 1240, height: 392 }), blocks };
  }

  static _jepaProfile() {
    const bb = this._jepaBackboneBlocks("input stack", "Cin x P x P", "z_hat", "D x P x P", "1x1 conv to the D-dim predicted embedding z_hat");
    const prof = this._jepaProfileBlocks();
    const blocks = [...bb, ...prof];
    const nodes = [
      { id: "in", type: "grid", cx: 95, cy: 90, label: "input stack", sub: "Cin x P x P" },
      { id: "bb", cx: 380, cy: 90, w: 204, h: 66, label: "Backbone", sub: "ResU-Net -> z_hat", block: "backbone" },
      { id: "zhat", cx: 920, cy: 90, w: 162, h: 54, variant: "latent", label: "z_hat", sub: "predicted, D" },

      { id: "profdec", cx: 920, cy: 232, w: 196, h: 64, label: "Profile AE decoder", sub: "curve recon", block: "prof_dec" },
      { id: "curvehat", cx: 920, cy: 360, w: 160, h: 54, variant: "io", label: "recon profile", sub: "L x P x P" },

      { id: "gt", cx: 95, cy: 490, w: 178, h: 54, variant: "io", label: "GT Gaussian params", sub: "3K x P x P" },
      { id: "recon", cx: 305, cy: 490, w: 164, h: 60, variant: "proc", label: "Reconstruct curve", sub: "GaussianCurve" },
      { id: "gtcurve", cx: 508, cy: 490, w: 156, h: 54, variant: "io", label: "GT profile", sub: "L x P x P" },
      { id: "profenc", cx: 710, cy: 490, w: 192, h: 66, label: "Profile AE encoder", sub: "stop-grad / EMA", block: "prof_enc" },
      { id: "zstar", cx: 920, cy: 490, w: 162, h: 54, variant: "latent", label: "z*", sub: "target, D" },

      { id: "embloss", cx: 1190, cy: 90, w: 172, h: 62, variant: "loss", label: "Embedding MSE", sub: "z_hat vs z*" },
      { id: "curveloss", cx: 1190, cy: 360, w: 172, h: 60, variant: "loss", label: "Curve recon", sub: "vs GT profile" },
    ];
    const edges = [
      { from: "in", to: "bb", route: "H" }, { from: "bb", to: "zhat", route: "H" },
      { from: "gt", to: "recon", route: "H" }, { from: "recon", to: "gtcurve", route: "H" }, { from: "gtcurve", to: "profenc", route: "H" }, { from: "profenc", to: "zstar", route: "H" },
      { from: "zhat", to: "profdec", route: "V" }, { from: "profdec", to: "curvehat", route: "V" },
      { from: "zhat", to: "embloss", route: "H" },
      { from: "curvehat", to: "curveloss", route: "H" },
      { from: "zstar", to: "embloss", route: "P", kind: "skip", fromSide: "right", via: [[1070, 490], [1070, 90]], toPt: [1104, 90] },
      { from: "gtcurve", to: "curveloss", route: "P", kind: "skip", fromSide: "bottom", via: [[508, 565], [1140, 565]], toPt: [1140, 390] },
    ];
    return { network: this._netCustom({ nodes, edges, width: 1330, height: 600 }), blocks };
  }

  static _jepaFull() {
    const bb = this._jepaBackboneBlocks("encoded stack", "Dimg x P x P", "z_hat", "D x P x P", "1x1 conv to the D-dim predicted embedding z_hat");
    const img = this._jepaImageEncBlocks();
    const prof = this._jepaProfileBlocks();
    const blocks = [...img, ...bb, ...prof];
    const nodes = [
      { id: "in", type: "grid", cx: 90, cy: 90, label: "input stack", sub: "Cin x P x P" },
      { id: "imgenc", cx: 285, cy: 90, w: 190, h: 64, label: "Image AE encoder", sub: "front-end", block: "img_enc" },
      { id: "feat", cx: 478, cy: 90, w: 152, h: 52, variant: "io", label: "encoded stack", sub: "Dimg x P x P" },
      { id: "bb", cx: 658, cy: 90, w: 178, h: 64, label: "Backbone", sub: "ResU-Net -> z_hat", block: "backbone" },
      { id: "zhat", cx: 920, cy: 90, w: 158, h: 52, variant: "latent", label: "z_hat", sub: "predicted, D" },

      { id: "profdec", cx: 920, cy: 232, w: 192, h: 62, label: "Profile AE decoder", sub: "curve recon", block: "prof_dec" },
      { id: "curvehat", cx: 920, cy: 360, w: 156, h: 52, variant: "io", label: "recon profile", sub: "L x P x P" },

      { id: "gt", cx: 90, cy: 490, w: 172, h: 54, variant: "io", label: "GT Gaussian params", sub: "3K x P x P" },
      { id: "recon", cx: 290, cy: 490, w: 158, h: 58, variant: "proc", label: "Reconstruct curve", sub: "GaussianCurve" },
      { id: "gtcurve", cx: 478, cy: 490, w: 150, h: 52, variant: "io", label: "GT profile", sub: "L x P x P" },
      { id: "profenc", cx: 662, cy: 490, w: 190, h: 64, label: "Profile AE encoder", sub: "stop-grad / EMA", block: "prof_enc" },
      { id: "zstar", cx: 920, cy: 490, w: 158, h: 52, variant: "latent", label: "z*", sub: "target, D" },

      { id: "embloss", cx: 1190, cy: 90, w: 172, h: 62, variant: "loss", label: "Embedding MSE", sub: "z_hat vs z*" },
      { id: "curveloss", cx: 1190, cy: 360, w: 172, h: 60, variant: "loss", label: "Curve recon", sub: "vs GT profile" },
    ];
    const edges = [
      { from: "in", to: "imgenc", route: "H" }, { from: "imgenc", to: "feat", route: "H" }, { from: "feat", to: "bb", route: "H" }, { from: "bb", to: "zhat", route: "H" },
      { from: "gt", to: "recon", route: "H" }, { from: "recon", to: "gtcurve", route: "H" }, { from: "gtcurve", to: "profenc", route: "H" }, { from: "profenc", to: "zstar", route: "H" },
      { from: "zhat", to: "profdec", route: "V" }, { from: "profdec", to: "curvehat", route: "V" },
      { from: "zhat", to: "embloss", route: "H" },
      { from: "curvehat", to: "curveloss", route: "H" },
      { from: "zstar", to: "embloss", route: "P", kind: "skip", fromSide: "right", via: [[1070, 490], [1070, 90]], toPt: [1104, 90] },
      { from: "gtcurve", to: "curveloss", route: "P", kind: "skip", fromSide: "bottom", via: [[478, 565], [1140, 565]], toPt: [1140, 390] },
    ];
    return { network: this._netCustom({ nodes, edges, width: 1330, height: 600 }), blocks };
  }
}

window.ModelDiagram = ModelDiagram;
