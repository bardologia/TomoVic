/*!
 * hairline figures drawer, terminal, plug, riffle, loupe, sieve, elevator, slow, cabinet, dish, router, patch, phosphor: src/figures/*.ts (and riffle-geometry.ts) with types stripped by node:module stripTypeScriptTypes and imports read from the HL kernel global; source otherwise unchanged except terminal, turned 90 degrees about the vertical to face right (its slab-to-world mappings W3 and P2 send u to -y and w to +x, and its facing test flips the sign of the u term), vendored from
 * https://github.com/lucasmarkes/hairline at bc782244216620434b14736df1d74daed2d05046 (@lucasmarkes/hairline 0.3.0)
 *
 * MIT License
 *
 * Copyright (c) 2026 Lucas Marques
 *
 * Permission is hereby granted, free of charge, to any person obtaining a copy
 * of this software and associated documentation files (the "Software"), to deal
 * in the Software without restriction, including without limitation the rights
 * to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
 * copies of the Software, and to permit persons to whom the Software is
 * furnished to do so, subject to the following conditions:
 *
 * The above copyright notice and this permission notice shall be included in all
 * copies or substantial portions of the Software.
 *
 * THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
 * IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
 * FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
 * AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
 * LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
 * OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
 * SOFTWARE.
 */
(function () {
  "use strict";
  const { Cam, circ, clamp, disposer, extremes, facing, fillet, fit, flatDot, hull, lerp, mk, open, place, pointer, poly, prism, proj, put, r2, rad, reducedMotion, reflect, register, ringAt, rings, rrect, run, seg, solid, spring, stepS, tdone, tset, tval, tween, unproj } = HL;
  const TABLE = {
    drawer: [12, 22, 34],
    terminal: [1, 2, 3.5],
    plug: [0.35, 0.6, 0.9],
    riffle: [0, 40, 90],
    loupe: [1.3, 1.8, 2.6],
    sieve: [6, 14, 24],
    elevator: [40, 100, 220],
    slow: [0.6, 0.2, 0.05],
    cabinet: [1.5, 3, 5],
    dish: [30, 50, 70],
    router: [0.5, 1.5, 3],
    patch: [1, 2.5, 5],
    phosphor: [150, 520, 1500]
  };

  const drawer = (() => {
    /**
     * Drawer: a filing cabinet of three deep drawers on a plinth, each front with
     * a bar pull. The pointer's height picks a drawer; it slides out on its
     * runners and shows its inside, two dim dividers running back and nothing
     * between them. The others close. At rest the middle drawer stands a quarter
     * out, its front bright. The slider is how far a drawer comes out.
     *
     * The pattern: one of many, as Sieve's. A tween per drawer on how far it is
     * out. The pick puts the pointer on each front's plane where it stands at
     * rest, which moves only with the slider, never with the drawer on screen.
     * Only a drawer whose tween moved is drawn again.
     */

    const N = 3, W = 54, D = 60, Z0 = 5, M = 3, PITCH = 26, G = 1.6, FT = 2.4; // drawers, carcass width and depth, plinth, margin round the fronts, a drawer's pitch, the gap between fronts, a front's thickness
    const T = 1.3, IN = 3.2, LOW = 2.2, HIGH = 3.6, DIV = 2.6, S = 2.1;       // a wall's thickness, the box's inset from its front's sides, below its front's foot and its top, how far the dividers sit under the walls, scale
    const ZB = Z0 + M, H = ZB + N * PITCH + M, REST = 0.7;                     // the lowest front's foot, the carcass's top, the rest pull as a share of the slider's

    /** On a front's face, the samples whose edge meets its top or its right side: they lie inside the silhouette. */
    const inner = (q        ) => 0.375 * q.nu + 0.307 * q.nv > 0;

    /** A plate standing in the x-z plane, from y0 back to y1 front: its silhouette, and the crease of its front face. */
    function slab(P           , ring      , inset      , y0        , y1        ) {
      const at = (r      , y        ) => r.map((q)       => P(q.u, y, q.v));
      return { sil: poly(hull(at(ring, y0).concat(at(ring, y1)))), crease: open(at(run(inset, inner), y1)) };
    }



    const mount              = ({ stage, svg, read }, value) => {
      const bag = disposer();
      const MAX = TABLE.drawer[2];
      const C = Cam(45, 0.5, S);
      // The carcass, and the top and bottom drawers out as far as the slider goes, each mirrored through the
      // carcass's middle: the cabinet stands in the middle of the frame, and the farthest pull still fits.
      const out = D + MAX + FT, ext         = [[0, 0, 0], [W, 0, 0], [0, 0, H], [W, 0, H], [W, D, 0], [0, out, ZB], [0, out, H - M], [W, out, ZB]];
      fit(C, ext.concat(ext.map(([x, y, z])       => [W - x, D - y, H - z])), 200, 166);
      const P = proj(C), front = facing(C);
      const g = mk("g", {}, svg);

      // The plinth, set back under the carcass, then the carcass.
      const [pr, pi] = rings(3, 3, W - 3, D - 3, 2.4, 1);
      put(solid(g), prism(P, front, pr, pi, 0, Z0));
      const [cr, ci] = rings(0, 0, W, D, 3, 1.4);
      put(solid(g), prism(P, front, cr, ci, Z0, H));

      const x0 = M + IN, x1 = W - M - IN, xs = [x0 + (x1 - x0) / 3, x0 + (2 * (x1 - x0)) / 3];
      const onFace = (r      , y        ) => poly(r.map((q)       => P(q.u, y, q.v)));
      // Each drawer's opening on the carcass's face: hidden by its front, seen above its box when it is out.
      mk("path", { class: "nf lo", d: Array.from({ length: N }, (_, k) => {
        const z = ZB + k * PITCH + G / 2;
        return onFace(rrect(x0 - 0.8, z + LOW - 0.8, x1 + 0.8, z + PITCH - G - HIGH + 1.4, 0.8, 2), D);
      }).join("") }, g);

      // Bottom to top: the camera looks down, so a lower drawer never covers a higher one.
      // In a drawer, back to front: its floor, left wall, dividers, right wall, the box's outline, its front, its pull.
      const drawers           = Array.from({ length: N }, (_, k) => {
        const z0 = ZB + k * PITCH + G / 2, z1 = z0 + PITCH - G, dg = mk("g", {}, g);
        const parts = [0, 1, 2, 3].map(() => mk("path", { class: "lo" }, dg));
        parts.push(mk("path", { class: "nf sil" }, dg));
        return { z0, z1, parts, front: solid(dg), pull: solid(dg), drawn: NaN };
      });
      const face = (d        ) => rrect(M, d.z0, W - M, d.z1, 1.6, 4), faceIn = (d        ) => rrect(M + 1, d.z0 + 1, W - M - 1, d.z1 - 1, 1, 4);

      /** A box from y0 to y1 with a rounded footprint, standing from z0 to z1: its silhouette. */
      const box = (a        , b        , y0        , y1        , z0        , z1        , r        ) =>
        y1 - y0 < 0.05 ? "" : prism(P, front, rrect(a, y0, b, y1, r, 3), null, z0, z1).sil;

      function draw(d        , o        ) {
        if (o === d.drawn) return;
        d.drawn = o;
        const zb = d.z0 + LOW, zt = d.z1 - HIGH, yb = D + o, yf = yb + FT;
        const [floor, left, divs, right, outline] = d.parts;
        floor.setAttribute("d", box(x0, x1, D, yb, zb, zb + T, 0.6));
        left.setAttribute("d", box(x0, x0 + T, D, yb, zb + T, zt, 0.5));
        divs.setAttribute("d", xs.map((x) => box(x - 0.5, x + 0.5, D, yb, zb + T, zt - DIV, 0.4)).join(""));
        right.setAttribute("d", box(x1 - T, x1, D, yb, zb + T, zt, 0.5));
        outline.setAttribute("d", box(x0, x1, D, yb, zb, zt, 0.8));
        put(d.front, slab(P, face(d), faceIn(d), yb, yf));
        const zp = (d.z0 + d.z1) / 2, xm = W / 2;
        const [br, bi] = rings(xm - 9, yf, xm + 9, yf + 2.6, 1.3, 0.6);
        put(d.pull, prism(P, front, br, bi, zp - 1.3, zp + 1.3));
      }

      const tw = drawers.map(() => tween(0));
      const B = register(stage, (_dt, now) => {
        let m = false;
        drawers.forEach((d, k) => { draw(d, tval(tw[k], now)); if (!tdone(tw[k], now)) m = true; });
        return m;
      });
      bag.add(B.unregister);

      let pull = value, picked = -2;
      /** Opens drawer f, counted from the bottom, and closes the rest; -1 puts the cabinet back to rest. */
      function choose(f        , now        ) {
        if (f === picked) return;
        picked = f;
        const a = f < 0 ? 1 : f;
        tw.forEach((t, k) => tset(t, k === a ? (f < 0 ? pull * REST : pull) : 0, now, 0));
        drawers.forEach((d, k) => d.front.sil.classList.toggle("hi", k === a));
        read.textContent = f < 0 ? "rest" : `drawer ${N - f} · 0`;
        B.wake();
      }
      tw[1] = tween(pull * REST);
      choose(-1, -1e9);
      drawers.forEach((d, k) => draw(d, tval(tw[k], 0)));

      /** The world x and z under screen point p on the upright plane y = yf: the projection, inverted. */
      const c = Math.cos(C.az), s = Math.sin(C.az), zf = Math.sqrt(1 - C.k * C.k);
      const onFront = (p      , yf        )       => { const x = (p[0] - C.ox) / (C.S * c) + (yf * s) / c; return [x, ((x * s + yf * c) * C.k - (p[1] - C.oy) / C.S) / zf]; };
      /** The drawer under p: first on each front where it stands at rest, top down as a higher drawer covers a lower one;
       * off every front, the nearest middle in z on the closed front. */
      function pick(p      ) {
        for (let k = N - 1; k >= 0; k--) {
          const [x, z] = onFront(p, D + FT + (k === 1 ? pull * REST : 0)), d = drawers[k];
          if (x >= M && x <= W - M && z >= d.z0 && z <= d.z1) return k;
        }
        const z = onFront(p, D + FT)[1];
        return drawers.reduce((best, d, k) => (Math.abs(z - (d.z0 + d.z1) / 2) < Math.abs(z - (drawers[best].z0 + drawers[best].z1) / 2) ? k : best), 0);
      }

      bag.add(pointer(stage, { move: (p) => choose(pick(p), performance.now()), leave: () => choose(-1, performance.now()) }));
      bag.add(() => svg.replaceChildren());

      return {
        set: (v) => { pull = v; const f = picked; picked = -2; choose(f, performance.now()); },
        destroy: bag.dispose,
      };
    };
    return { mount, label: "A filing cabinet of three drawers: the pointer's height picks one, it slides out, and inside are two dividers and nothing between them.", rest: "rest", range: [12, 22, 34] };
  })();

  const terminal = (() => {
    /**
     * Terminal: a terminal window floating upright as a thin rounded slab. A title
     * bar with its three round buttons across the top, a prompt bar across the
     * foot with a chevron and a block cursor, and between them the output: rows
     * of rounded bars, indented and of different lengths, as code and logs are.
     * The pointer's height scrolls back through twenty-four lines of history on a
     * spring; lines leaving the top pass in behind the title bar, and new ones
     * come up from behind the prompt bar, cut where they meet it. The line under the
     * pointer lifts off the slab, and its neighbours less, each on its own spring.
     * At rest the window is scrolled back half a line and one long line is caught
     * lifted, bright. The slider is how far the lift spreads, in lines.
     *
     * The slab stands in the x–z plane and faces +y, so the figure draws in its
     * own frame: u across, v up, w out of the face, P2(u, v, w) = P(u, w, v).
     * The pattern: scrub and pick. One spring for the scroll, a spring per line
     * for its lift, a falloff by distance, and a hit test on the rest planes.
     */

    const N = 24, V = 7, G = 11, T = 2.1, LH = 1.8, CH = 3.9, LIFT = 5.5, HB = 3.4, SLAB = 3;
    const W = 150, TB = 17, PB = 17, PAD = 11, IN = 2.5, FIRST = 37;
    const VB = PB, VA = PB + V * G, H = VA + TB, E = 4;
    /** The history, oldest first: an indent in cells, then each token's length in cells. */
    const HIST = [
      "0 5 12", "2 7 3 9", "2 14", "4 6 10", "4 18", "2 3", "0 2", "0 2 6 8",
      "0 26", "0 20", "0 11 4", "2 9 12", "2 5 3 7", "4 16", "4 8 8", "2 4",
      "0 3 14", "0 24", "0 30", "0 17", "2 6 11", "2 13", "0 9 5", "0 4 7",
    ];
    /** Rest: scrolled back part way into a line, with line 18 lifted and its neighbours following. */
    const REST_TOP = N - V - 2.6, REST_LINE = 18, REST_R = 2;

    /** The share of the full lift a line takes, d lines from the one under the pointer: all of it there, none past R. */
    const falloff = (d        , R        ) => clamp(1 - d / R, 0, 1);
    const smooth = (t        ) => t * t * (3 - 2 * t);
    /** A ring sample faces the camera: its normal, in the slab's u–v plane, against the view direction (x .612, z .5). */
    const front = (q        ) => -0.612 * q.nu + 0.5 * q.nv > 0;
    /** A ring cut to the window between the bars: whatever lies past a bar is pressed flat against it. */
    const cut = (ring      )       => ring.map((q) => ({ ...q, v: clamp(q.v, VB, VA) }));





    const mount              = ({ stage, svg, read }, value) => {
      const bag = disposer();
      const C = Cam(45, 0.5, 1.62);
      const W3 = (u        , v        , w        )                           => [w, W - u, v];
      fit(C, [W3(0, 0, -SLAB), W3(W, 0, -SLAB), W3(0, H, -SLAB), W3(W, H, -SLAB), W3(W, 0, HB + 2.8), W3(0, H, HB + 1.3), W3(PAD, VA - 4, LIFT + LH)], 200, 166);
      const P = proj(C), P2 = (u        , v        , w        ) => P(w, W - u, v);
      let R = value, over       = null, lit            = [];

      const g = mk("g", {}, svg);
      const [sr, si] = rings(0, 0, W, H, 9, 2);
      put(solid(g), prism(P2, front, sr, si, -SLAB, 0));

      // The history, oldest (highest) first. Each token is a pill, cut to the window as it is drawn.
      const rows        = HIST.map((s, j) => {
        const [ind, ...tok] = s.split(" ").map(Number), segs        = [];
        let at = ind;
        for (const n of tok) {
          const x0 = PAD + at * CH;
          segs.push({ x0, x1: x0 + n * CH - 1.4, el: solid(g) });
          at += n + 1;
        }
        return { j, segs, sp: spring(0, { eps: 0.01 }), drawn: "" };
      });

      // The prompt bar, its chevron (two strokes joined into one shape) and the block cursor, painted after the
      // lines as the title bar is: a line coming up out of it rises from behind it, cut flat inside it.
      const [pr, pi] = rings(IN, IN, W - IN, VB, 6, 1.4);
      put(solid(g), prism(P2, front, pr, pi, 0, HB));
      const cy = (IN + VB) / 2;
      const chev = fillet([[0, 6.2], [8.5, 0], [0, -6.2], [0, -3.1], [4.25, 0], [0, 3.1]], [0.9, 1.1, 0.9, 0.5, 0.6, 0.5]);
      const chevEl = mk("path", { d: poly(chev.map(([x, y]) => P2(PAD + x, cy + y, HB))), class: "nf" }, g);
      const [kr, ki] = rings(PAD + 13, cy - 5.2, PAD + 13 + CH * 1.5, cy + 5.2, 1.2, 0.8);
      const cursor = solid(g);
      put(cursor, prism(P2, front, kr, ki, HB, HB + 2.8));

      // The title bar and its buttons, painted after the lines: a line going up passes in behind it.
      const [tr, ti] = rings(IN, VA, W - IN, H - IN, 6, 1.4);
      put(solid(g), prism(P2, front, tr, ti, 0, HB));
      for (let i = 0; i < 3; i++) {
        const cx = PAD + i * 8.5, cv = (VA + H - IN) / 2;
        const [r, ri] = rings(cx - 2.8, cv - 2.8, cx + 2.8, cv + 2.8, 2.8, 0.8);
        put(solid(g), prism(P2, front, r, ri, HB, HB + 1.3));
      }

      /** Row j with the window scrolled to `top` lines: cut to the window, and lifted less as it nears either bar. */
      function drawRow(rw     , top        ) {
        const key = top + "|" + rw.sp.x;
        if (key === rw.drawn) return;
        rw.drawn = key;
        const vc = VA - (rw.j - top + 0.5) * G, v0 = Math.max(vc - T, VB), v1 = Math.min(vc + T, VA);
        const env = smooth(clamp((VA - vc - T) / E, 0, 1)) * smooth(clamp((vc - T - VB) / E, 0, 1));
        const w0 = rw.sp.x * env;
        for (const s of rw.segs) {
          if (v1 - v0 < 0.05) { put(s.el, { sil: "", crease: "" }); continue; }
          const ring = cut(rrect(s.x0, vc - T, s.x1, vc + T, T, 4)), inner = cut(rrect(s.x0 + 0.7, vc - T + 0.7, s.x1 - 0.7, vc + T - 0.7, T - 0.7, 4));
          put(s.el, prism(P2, front, ring, inner, w0, w0 + LH));
        }
      }

      function light(els           ) {
        for (const el of lit) el.classList.remove("hi");
        lit = els;
        for (const el of lit) el.classList.add("hi");
      }

      const top = spring(REST_TOP, { eps: 0.002 });
      const B = register(stage, (dt) => {
        let m = stepS(top, dt);
        for (const rw of rows) { if (stepS(rw.sp, dt)) m = true; drawRow(rw, top.x); }
        return m;
      });
      bag.add(B.unregister);

      /** The slab-frame point [u, v] under a screen point, on the plane w. */
      function onFace([sx, sy]      , w        )       {
        const o = P2(0, 0, w), a = P2(1, 0, w), b = P2(0, 1, w);
        const ax = a[0] - o[0], ay = a[1] - o[1], bx = b[0] - o[0], by = b[1] - o[1], det = ax * by - ay * bx;
        return [((sx - o[0]) * by - (sy - o[1]) * bx) / det, (ax * (sy - o[1]) - ay * (sx - o[0])) / det];
      }
      /** Where the pointer is, on the rest planes, nearest first: "prompt", a depth down the rows from 0 to 1, or null off the window. */
      function hit(p      )       {
        const qb = onFace(p, HB), inU = (q      ) => q[0] > IN && q[0] < W - IN;
        if (inU(qb) && qb[1] > IN && qb[1] < VB) return "prompt";
        if (inU(qb) && qb[1] > VA && qb[1] < H - IN) return 0;
        const q = onFace(p, 0);
        if (q[0] < 0 || q[0] > W || q[1] < 0 || q[1] > H) return null;
        return q[1] <= VB ? "prompt" : clamp((VA - G / 2 - q[1]) / ((V - 1) * G), 0, 1);
      }

      function retarget() {
        let t        , c        , r = R;
        if (over === null) { t = REST_TOP; c = REST_LINE; r = REST_R; read.textContent = "rest"; }
        else if (over === "prompt") { t = N - V; c = -1; read.textContent = "prompt"; }
        else {
          // The pointer runs over the row centres; the column scrolls with it, and the line nearest it is taken, kept clear of both bars.
          t = over * (N - V);
          c = clamp(Math.round(over * (N - 1)), Math.ceil(t), Math.floor(t + V - 1));
          read.textContent = "line " + (FIRST + c);
        }
        top.t = t;
        for (const rw of rows) rw.sp.t = c < 0 ? 0 : LIFT * falloff(Math.abs(rw.j - c), r);
        light(c < 0 ? [cursor.sil, chevEl] : rows[c].segs.map((s) => s.el.sil));
        B.wake();
      }
      retarget();
      for (const rw of rows) rw.sp.x = rw.sp.t;

      bag.add(pointer(stage, {
        move: (p) => { over = hit(p); retarget(); },
        leave: () => { over = null; retarget(); },
      }));
      bag.add(() => svg.replaceChildren());

      return {
        set: (v) => { R = v; if (over !== null) retarget(); },
        destroy: bag.dispose,
      };
    };
    return { mount, label: "A terminal window: the pointer's height scrolls back through its history, and the line under it lifts off the screen.", rest: "rest", range: [1, 2, 3.5] };
  })();

  const plug = (() => {
    /**
     * Plug: a wall plate with a socket, and a plug lying on the floor at the end
     * of a cord that curves away out of the frame. The pointer draws the plug up
     * toward the socket on a spring, and the cord pays out behind it. It never
     * seats: it stops short, and falls back when the pointer leaves. At rest it
     * lies on the floor, its two pins bright, the socket's holes bare. The slider
     * is how much of the way to the socket the plug can come.
     *
     * The pattern: follow a position. One spring on how far along its way the
     * plug is, set from where the pointer falls on the screen line from the
     * plug's rest to the socket, which never moves. Where the plug is and how far
     * it has turned to face the wall are both read from that one number.
     */

    const PT = 3, PH = 21, ZC = 30, PR = 7, B = 1.4;           // the plate: thickness, half its side, the socket's height, corner radius, crease inset
    const HOLE = 2.6, HS = 8, RECESS = 13;                     // the socket: hole radius, the holes' offset from its centre, the recess round them
    const BW = 11, BH = 6.5, BR = 4.5, BL = 18;                // the plug's body: half width, half height, corner radius, length
    const PIN = 2, PL = 11, SL = 7, S0 = 4.6, S1 = 3, CR = 1.8; // pin radius, pin length, the sleeve's length and two radii, the cord's radius
    const REST       = [48, 8], YAW = 100, TURN = 0.7, S = 2.8; // the pins' face on the floor, its heading, the share of the way the turn takes, scale
    const EDGE = 398;                                          // where the cord leaves the picture: the viewBox's right edge, less a stroke
    const ss = (t        ) => t * t * (3 - 2 * t);

    /** Cuts the loops an inner offset makes where the cord bends tighter than its radius on screen. */
    function untangle(L        )         {
      for (let i = 0; i < L.length - 3; i++) for (let j = L.length - 2; j > i + 1; j--) {
        const p = L[i], q = L[i + 1], r = L[j], s = L[j + 1];
        const e0 = q[0] - p[0], e1 = q[1] - p[1], f0 = s[0] - r[0], f1 = s[1] - r[1], g0 = r[0] - p[0], g1 = r[1] - p[1], d = e0 * f1 - e1 * f0;
        if (!d) continue;
        const t = (g0 * f1 - g1 * f0) / d, u = (g0 * e1 - g1 * e0) / d;
        if (t > 0 && t < 1 && u > 0 && u < 1) { L.splice(i + 1, j - i, [p[0] + t * e0, p[1] + t * e1]); break; }
      }
      return L;
    }

    /** A screen line up to where it first crosses x = X, ending on it. */
    function upTo(L        , X        )         {
      const i = L.findIndex((p) => p[0] > X);
      if (i < 1) return i < 0 ? L : [];
      const p = L[i - 1], q = L[i], f = (X - p[0]) / (q[0] - p[0]);
      return [...L.slice(0, i), [X, p[1] + (q[1] - p[1]) * f]];
    }

    /** The cord's outline: its screen centre line offset by its radius, the plug's end a round cut, the far end cut off at x = X with no line across it, as the frame would. */
    function tube(Q                 , rho        , X        )         {
      const n = Q.length, A         = [], Bk         = [];
      for (let i = 0; i < n; i++) {
        const a = Q[Math.max(i - 1, 0)], c = Q[i], b = Q[Math.min(i + 1, n - 1)];
        let tx = b[0] - a[0], ty = b[1] - a[1];
        const l = Math.hypot(tx, ty) || 1; tx /= l; ty /= l;
        A.push([c[0] - ty * rho, c[1] + tx * rho]); Bk.push([c[0] + ty * rho, c[1] - tx * rho]);
      }
      const cap = (c      ) => { const o         = []; for (let k = 7; k >= 1; k--) { const t = (Math.PI * k) / 8; o.push([c[0] + rho * Math.cos(t), c[1] + rho * 0.5 * Math.sin(t)]); } return o; };
      return open([...upTo(untangle(Bk), X).reverse(), ...cap(Q[0]), ...upTo(untangle(A), X)]);
    }

    /** Where the plug is s of the way to the socket: the centre of its pins' face, its heading (w) and its width (u). Up is up. */
    function pose(s        )                                {
      const th = rad(lerp(YAW, 180, ss(clamp(s / TURN, 0, 1))));
      return {
        c: [lerp(REST[0], PL, s), lerp(REST[1], 0, s), lerp(BH, ZC, Math.sin((s * Math.PI) / 2))],
        w: [Math.cos(th), Math.sin(th), 0],
        u: [-Math.sin(th), Math.cos(th), 0],
      };
    }

    const mount              = ({ stage, svg, read }, value) => {
      const bag = disposer();
      const C = Cam(45, 0.5, S), zf = Math.sqrt(1 - C.k * C.k);
      /** Toward the camera: a face whose normal has a positive dot with this is seen. */
      const V       = [Math.sin(C.az) * zf, Math.cos(C.az) * zf, C.k];
      const dot = (a      , b      ) => a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
      /** A point in the plug's own frame: a across, b up, d along its heading from the pins' face. */
      const at = (o                         , a        , b        , d        )       =>
        [o.c[0] + a * o.u[0] + d * o.w[0], o.c[1] + a * o.u[1] + d * o.w[1], o.c[2] + b];

      // The camera is fitted to the plate and the plug at both ends of its way.
      const ext         = [];
      for (const x of [0, -PT]) for (const y of [-PH, PH]) for (const z of [ZC - PH, ZC + PH]) ext.push([x, y, z]);
      for (const s of [0, 1]) { const o = pose(s); for (const a of [-BW, BW]) for (const b of [-BH, BH]) for (const d of [PL, -BL - SL]) ext.push(at(o, a, b, d)); }
      fit(C, ext, 200, 166);
      const P = proj(C), Pv = (p      ) => P(p[0], p[1], p[2]);

      // The plate: a thin slab on the wall, its face toward +x, the recess and two holes cut into it.
      const g = mk("g", {}, svg);
      const face = rrect(-PH, ZC - PH, PH, ZC + PH, PR, 6), lip = rrect(-PH + B, ZC - PH + B, PH - B, ZC + PH - B, PR - B, 6);
      put(solid(g), {
        sil: poly(hull(face.map((q) => P(0, q.u, q.v)).concat(face.map((q) => P(-PT, q.u, q.v))))),
        crease: open(run(lip, (q) => q.nu * V[1] + q.nv * V[2] > 0).map((q) => P(0, q.u, q.v))),
      });
      mk("path", { class: "nf lo", d: poly(circ(RECESS, 48).map((q) => P(0, q.u, ZC + q.v))) }, g);
      mk("path", { class: "nf", d: [-HS, HS].map((y) => poly(circ(HOLE, 16).map((q) => P(0, y + q.u, ZC + q.v)))).join("") }, g);

      // The plug, back to front as it lies; the order turns over with it.
      const pg = mk("g", {}, svg);
      const cord = mk("path", { class: "sil" }, pg), sleeve = mk("path", { class: "sil" }, pg), body = solid(pg), pins = mk("path", { class: "sil hi" }, pg);
      const s0 = circ(S0, 16), s1 = circ(S1, 16);
      /** An end rounded over rr: the cross-section f(inset) in four steps, from the face at d inward along dir. */
      const rounded = (f                     , rr        , d        , dir        ) =>
        [0, 30, 60, 90].map((a)                 => [f(rr * (1 - Math.sin(rad(a)))), d + dir * rr * (1 - Math.cos(rad(a)))]);
      const box = (k        ) => rrect(-BW + k, -BH + k, BW - k, BH - k, BR - k), rod = (k        ) => circ(PIN - k, 12);
      const inner = box(2), shell = [...rounded(box, 2, 0, -1), ...rounded(box, 2, -BL, 1)], prong = [[rod(0), 0]                  , ...rounded(rod, PIN * 0.8, PL, -1)];
      /** The silhouette of a solid swept through cross-sections, each a ring at a distance along the heading, a0 across. */
      const sweep = (o                         , parts                       , a0 = 0) =>
        poly(hull(parts.flatMap(([r, d]) => r.map((q) => Pv(at(o, a0 + q.u, q.v, d))))));

      // The cord's floor end, past the frame's right edge, and the floor point it bends round; neither moves.
      // The cord is drawn only up to just inside that edge, so it runs out of the picture without leaving the viewBox.
      const end       = [...unproj(C, 440, 150, CR), CR], bend       = [REST[0] + 18, REST[1] - 52, CR];
      let front = true, drawn = NaN;
      const sp = spring(0, { eps: 0.002 });

      function draw() {
        if (sp.x === drawn) return;
        drawn = sp.x;
        const o = pose(sp.x), pinsFace = dot(o.w, V) > 0, vu = dot(o.u, V);
        if (pinsFace !== front) { front = pinsFace; pg.append(...(front ? [cord, sleeve, body.g, pins] : [pins, body.g, cord, sleeve])); }
        const dEnd = front ? 0 : -BL;
        put(body, {
          sil: sweep(o, shell),
          crease: open(run(inner, (q) => q.nu * vu + q.nv * V[2] > 0).map((q) => Pv(at(o, q.u, q.v, dEnd)))),
        });
        pins.setAttribute("d", [-HS, HS].map((a) => sweep(o, prong, a)).join(""));
        sleeve.setAttribute("d", sweep(o, [[s0, -BL], [s1, -BL - SL]]));
        // The cord: a cubic from inside the sleeve's end, leaving along the plug's heading, round the bend to the floor end.
        const t0 = at(o, 0, 0, -BL - SL + 2), t1 = at(o, 0, 0, -BL - SL - 26), Q         = [];
        for (let i = 0; i <= 40; i++) {
          const t = i / 40, a = (1 - t) ** 3, b = 3 * (1 - t) ** 2 * t, c = 3 * (1 - t) * t * t, d = t ** 3;
          Q.push(P(a * t0[0] + b * t1[0] + c * bend[0] + d * end[0], a * t0[1] + b * t1[1] + c * bend[1] + d * end[1], a * t0[2] + b * t1[2] + c * bend[2] + d * end[2]));
        }
        cord.setAttribute("d", tube(Q, CR * S, EDGE));
      }

      const loop = register(stage, (dt) => { const m = stepS(sp, dt); draw(); return m; });
      bag.add(loop.unregister);

      // The line the pointer is read along: from the pins' face at rest to the socket, on screen. Neither moves.
      const A = Pv(pose(0).c), Bs = P(0, 0, ZC), ab       = [Bs[0] - A[0], Bs[1] - A[1]], ab2 = ab[0] * ab[0] + ab[1] * ab[1];
      let pull = value, along = -1;
      function retarget() {
        sp.t = along < 0 ? 0 : Math.min(along, pull);
        // the gap from the pins' tips to the socket, read from the target, never the pose on screen
        const o = pose(sp.t), tip = at(o, 0, 0, PL);
        read.textContent = along < 0 ? "rest" : `gap ${Math.round(Math.hypot(tip[0], tip[1], tip[2] - ZC))} · 0 V`;
        loop.wake();
      }
      retarget();
      draw();

      bag.add(pointer(stage, {
        move: (p) => { along = clamp(((p[0] - A[0]) * ab[0] + (p[1] - A[1]) * ab[1]) / ab2, 0, 1); retarget(); },
        leave: () => { along = -1; retarget(); },
      }));
      bag.add(() => svg.replaceChildren());

      return { set: (v) => { pull = v; retarget(); }, destroy: bag.dispose };
    };
    return { mount, label: "A wall socket and a plug lying on the floor at the end of its cord: the pointer draws the plug up toward the socket, and it stops short of it.", rest: "rest", range: [0.35, 0.6, 0.9] };
  })();

  const riffle = (() => {
    /**
     * Riffle's drawing, with no DOM: the camera, the tray and a card in any pose,
     * as path strings. The engine (riffle.ts) writes these into its svg on every
     * frame.
     */

    const N = 8, W = 84, H = 54, G = 13, TW = 22, TH = 7, TABS = [6, 31, 56], TK = 1.4;
    const REST = -12, BACK = -24, FWD = 20, LIFT = 16;
    const X0 = -5, X1 = W + 5, Y0 = -9, Y1 = (N - 1) * G + 9, WH = 20, WR = 6, WT = 2.4;

    /** The camera, fitted to the tray with a card lifted, so nothing leaves the frame in any pose. */
    function camera()         {
      const C = Cam(45, 0.5, 1.62);
      fit(C, [[X0, Y0, 0], [X1, Y1, -8], [X1, Y0, 0], [X0, Y1, 0], [X0, Y0, H + TH], [X1, Y0, H + TH + LIFT]], 200, 166);
      return C;
    }

    /** The tray's outline and the rim's inner edge. */
    const trayRings = ()                               => ({
      outer: rrect(X0, Y0, X1, Y1, WR, 6),
      inner: rrect(X0 + WT, Y0 + WT, X1 - WT, Y1 - WT, WR - WT, 6),
    });

    /** A run of points ordered left to right on screen. */
    const LR = (pts        ) => (pts[0][0] <= pts[pts.length - 1][0] ? pts : pts.slice().reverse());

    /**
     * The tray's paths, which never move. `far` is painted before the cards, `near`
     * after them; each entry is [d, class].
     */
    function tray(P           , front                        , outer      , inner      ) {
      // far half: body, the rim's inner edge, and the floor seam along the far walls
      const far                     = [
        [poly(hull(ringAt(P, outer, 0).concat(ringAt(P, outer, WH)))), "sil"],
        [poly(ringAt(P, inner, WH)), "nf"],
        [open(ringAt(P, run(inner, (q) => !front(q)), 2.5)), "nf lo"],
      ];
      // near half: one opaque piece from the rim's inner edge down to the floor
      const iF = LR(ringAt(P, run(inner, front), WH)), oT = LR(ringAt(P, run(outer, front), WH)), oB = LR(ringAt(P, run(outer, front), 0));
      // a finger pull, set into the front
      const hx = (X0 + X1) / 2, onFront = (ring      ) => ring.map((q) => P(q.u, Y1, q.v));
      const near                     = [
        [poly([...iF, oT[oT.length - 1], ...oB.slice().reverse(), oT[0]]), "fo"],
        [open(oT), "nf lo"],
        [open(iF), "nf"],
        [open([oT[0], ...oB, oT[oT.length - 1]]), "nf sil"],
        [poly(onFront(rrect(hx - 11, 6.5, hx + 11, 12.5, 3, 5))), "nf"],
        [poly(onFront(rrect(hx - 9.4, 8, hx + 9.4, 11, 1.5, 5))), "nf lo"],
      ];
      return { far, near };
    }

    /**
     * Card i, back to front: its number (8 at the back), which of the three tab
     * positions it takes, and its filleted outline, drawn upright in its own plane.
     */
    function card(i        ) {
      const n = N - i, t0 = TABS[(N - 1 - i) % 3];
      const shape = fillet(
        [[0, 0], [W, 0], [W, H], [t0 + TW, H], [t0 + TW, H + TH], [t0, H + TH], [t0, H], [0, H]],
        [1, 1, 3.2, 1.8, 2.4, 2.4, 1.8, 3.2],
      );
      return { n, t0, shape };
    }



    /**
     * Card i leaning th degrees (negative leans back) and lifted by `lift`: its
     * back edge, face, heading and rules as paths, and where each of the eight
     * punches of its number sits, in a 4 × 2 grid on the tab.
     */
    function pose(P           , i        , t0        , shape                 , th        , lift        )           {
      const yb = i * G, s = Math.sin(rad(th)), c = Math.cos(rad(th));
      const w = (u        , v        ) => P(u, yb + v * s, v * c + lift);
      const wb = (u        , v        ) => P(u, yb + v * s - TK * c, v * c + TK * s + lift);
      const punch         = [];
      for (let k = 0; k < 8; k++) punch.push(w(t0 + TW / 2 + ((k % 4) - 1.5) * 3.6, H + TH / 2 + (0.5 - Math.floor(k / 4)) * 2.8));
      return {
        back: poly(shape.map((p) => wb(p[0], p[1]))),
        face: poly(shape.map((p) => w(p[0], p[1]))),
        head: seg(w(6, H - 11), w(W - 6, H - 11)),
        rules: [H - 18, H - 25, H - 32, H - 39].map((v) => seg(w(6, v), w(W - 6, v))).join(""),
        punch,
      };
    }

    /** The fitted camera, its projector and facing test, and the tray's rings: what both the engine and the still start from. */
    function scene() {
      const C = camera();
      return { C, P: proj(C), front: facing(C), ...trayRings() };
    }


    /**
     * Riffle (Fig 9.1) — a rounded tray holding eight cards. The card under the pointer stands up and lifts; the ones in front
     * lean forward and the ones behind lean back, staggered outwards from it on
     * the 700ms lift curve. A discrete figure, so every card runs on tweens.
     *
     * Selection never reads the posed cards: it comes from static oblique bands
     * along the resting top edges, so a card moving out from under the pointer
     * can't flip the choice back and forth. The bands are geometry only; nothing
     * draws them. The stage is a focusable group; the arrow keys walk the cards
     * and the read-out names the one pulled by its number.
     *
     * The drawing itself — camera, tray, a card in any pose — is pure and lives in
     * riffle-geometry.ts; this file is the DOM, the tweens and the input.
     */









    const mount = ({ stage, svg, read }           , value        )               => {
      const bag = disposer();
      let stag = value;

      const { P, front, outer, inner } = scene();
      const paths = tray(P, front, outer, inner);

      const g = mk("g", {}, svg);
      reflect(svg, g, P, front, outer, 0, 14);
      for (const [d, cls] of paths.far) mk("path", { d, class: cls }, g);

      const cards         = [];
      for (let i = 0; i < N; i++) {
        const { n, t0, shape } = card(i);
        const grp = mk("g", {}, g);
        const back = mk("path", { class: "lo" }, grp), face = mk("path", { class: "sil" }, grp);
        const head = mk("path", { class: "nf" }, grp), rules = mk("path", { class: "nf lo" }, grp);
        // the card's number, punched in a 4 × 2 grid on its tab
        const punch                     = [];
        for (let k = 0; k < 8; k++) punch.push(mk("circle", { r: 1.05, class: "dot " + (k === n - 1 ? "m" : "off") }, grp));
        cards.push({ n, t0, shape, back, face, head, rules, punch, a: tween(REST), z: tween(0) });
      }

      for (const [d, cls] of paths.near) mk("path", { d, class: cls }, g);

      // hit bands: oblique strips along the RESTING top edges. They never move.
      const top = (i        ) => P(W / 2, i * G + H * Math.sin(rad(REST)), H * Math.cos(rad(REST)));
      const c0 = top(0), c1 = top(1), d = [c1[0] - c0[0], c1[1] - c0[1]];
      const px0 = P(0, 0, 0), px1 = P(1, 0, 0), ex = [px1[0] - px0[0], px1[1] - px0[1]];
      const HALF = W / 2 + 6, det = d[0] * ex[1] - d[1] * ex[0];

      /** The card whose band holds the point, in the band's own (s, r) coordinates; -1 outside. */
      function hit([x, y]      ) {
        const qx = x - c0[0], qy = y - c0[1];
        const s = (qx * ex[1] - qy * ex[0]) / det, r = (d[0] * qy - d[1] * qx) / det;
        if (Math.abs(r) > HALF || s < -0.5 || s > N + 1) return -1;
        return clamp(Math.round(s), 0, N - 1);
      }

      function draw(i        , th        , lift        ) {
        const cd = cards[i], q = pose(P, i, cd.t0, cd.shape, th, lift);
        cd.back.setAttribute("d", q.back);
        cd.face.setAttribute("d", q.face);
        cd.head.setAttribute("d", q.head);
        cd.rules.setAttribute("d", q.rules);
        cd.punch.forEach((el, k) => place(el, q.punch[k]));
      }

      const B = register(stage, (_dt, now) => {
        let moving = false;
        cards.forEach((cd, i) => { draw(i, tval(cd.a, now), tval(cd.z, now)); if (!tdone(cd.a, now) || !tdone(cd.z, now)) moving = true; });
        return moving;
      });
      bag.add(B.unregister);

      let act = -1;
      const caption = (a        ) => (a < 0 ? "rest" : String(N - a).padStart(2, "0"));
      /** Pulls card a (-1 puts them all back). The stagger spreads out from the card pulled, or the one let go. */
      function setActive(a        ) {
        if (a === act) return;
        const now = performance.now(), from = a >= 0 ? a : act;
        act = a;
        cards.forEach((cd, i) => {
          const delay = Math.abs(i - from) * stag;
          const th = a < 0 ? REST : i < a ? BACK : i > a ? FWD : 0;
          tset(cd.a, th, now, delay); tset(cd.z, a === i ? LIFT : 0, now, delay);
          cd.face.classList.toggle("hi", i === a); cd.head.classList.toggle("hi", i === a); cd.punch[cd.n - 1].classList.toggle("m", i !== a);
        });
        read.textContent = caption(a);
        B.wake();
      }

      bag.add(pointer(stage, { move: (p) => setActive(hit(p)), leave: () => setActive(-1) }));
      bag.on(stage, "keydown", (e) => {
        if (e.key === "ArrowLeft" || e.key === "ArrowDown") { setActive(act < 0 ? N - 1 : Math.min(N - 1, act + 1)); e.preventDefault(); }
        else if (e.key === "ArrowRight" || e.key === "ArrowUp") { setActive(act < 0 ? N - 1 : Math.max(0, act - 1)); e.preventDefault(); }
        // Escape puts a pulled card back and claims the key; at rest it passes on to the page.
        else if (e.key === "Escape" && act >= 0) { setActive(-1); e.preventDefault(); }
      });
      bag.on(stage, "blur", () => setActive(-1));
      bag.add(() => svg.replaceChildren());

      return {
        set: (v) => { stag = v; },
        destroy: bag.dispose,
      };
    };
    return { mount, label: "A tray of eight cards. Hover or use the arrow keys to pull a card.", rest: "rest", range: [0, 40, 90] };
  })();

  const loupe = (() => {
    /**
     * Loupe: a stand loupe on three legs over a ruled sheet with nothing written
     * on it. The pointer drags the loupe across the sheet on a spring. Under the
     * glass the rules are drawn again, larger, and there is nothing between them.
     * At rest the glass straddles the margin where the rules start, so their ends
     * land inside it well away from where the runs outside it would put them;
     * its thin rim is the bright mark. The slider is the magnification.
     *
     * The pattern: follow a position. Two springs hold the point of the sheet the
     * eye sees through the glass's centre, set from the pointer on the sheet's
     * plane, which never moves; the loupe stands where its glass covers that
     * point. The glass shows the sheet there enlarged, cut to the lens by
     * arithmetic, not by a clip. Past the sheet's near edges the feet stand on
     * the table, so the glass reaches every rule.
     */

    const SW = 124, SD = 92, ST = 2.4;                  // the sheet: width, depth, thickness
    const ROWS = 7, Y0 = 13, DY = 11, ML = 26, MR = 12; // its rules: how many, the first one's y, their pitch, the left margin they start at, the right one
    const R = 27, LZ = 20, RIM = 1.2, GLASS = R - 1.4;  // the loupe: ring radius, height of its underside, ring depth, glass radius
    const LEGS = [45, 165, 285], FOOT = 35, PAD = 1.8, REST       = [ML + 9, 46], S = 2.1;

    const mount              = ({ stage, svg, read }, value) => {
      const bag = disposer();
      const C = Cam(45, 0.5, S), top = LZ + RIM;
      const feet = LEGS.map((a)       => [Math.cos((a * Math.PI) / 180), Math.sin((a * Math.PI) / 180)]);
      /** From the point the eye sees to the loupe's centre: the glass stands this far in front of it. */
      const [bx, by] = unproj(C, ...proj(C)(0, 0, 0), top);
      // The frame holds the rest pose; the reach still fits inside it (see the far and near corners).
      const ext         = [[0, 0, -ST], [SW, 0, -ST], [0, SD, -ST], [SW, SD, -ST]];
      for (const q of circ(R, 16)) ext.push([REST[0] + bx + q.u, REST[1] + by + q.v, top]);
      fit(C, ext, 200, 166);
      const P = proj(C), front = facing(C);
      const g = mk("g", {}, svg);

      // The sheet, then its rules lying on it.
      const [so, si] = rings(0, 0, SW, SD, 6, 1.4);
      put(solid(g), prism(P, front, so, si, -ST, 0));
      const rowY = (i        ) => Y0 + i * DY;
      /** The lines on the sheet: the margin, then the rules that start at it. */
      const lines                      = [[[ML, Y0 - 7], [ML, rowY(ROWS - 1) + 7]], ...Array.from({ length: ROWS }, (_, i)               => [[ML, rowY(i)], [SW - MR, rowY(i)]])];
      mk("path", { class: "nf lo", d: lines.map(([p, q]) => seg(P(p[0], p[1], 0), P(q[0], q[1], 0))).join("") }, g);

      // The loupe: three legs, a thin ring round the glass, a glint on it, the sheet seen through it.
      const legs = mk("path", { class: "nf" }, g);
      const rim = solid(g);
      const glint = mk("path", { class: "nf lo" }, g);
      const seen = mk("path", { class: "nf sil" }, g);
      const shine = circ(GLASS * 0.72, 64).slice(26, 36);
      const ring = circ(R, 64), lens = circ(GLASS, 64), edge = rrect(0, 0, SW, SD, 6, 12), pad = circ(PAD, 12);
      /** A foot on the sheet stands on its top; one past its edge, on the table under it. */
      const floor = (x        , y        ) => (x >= 0 && x <= SW && y >= 0 && y <= SD ? 0 : -ST);

      const sx = spring(REST[0]), sy = spring(REST[1]), mag = spring(value);
      let cx = NaN, cy = NaN, dm = NaN;
      function draw() {
        if (sx.x === cx && sy.x === cy && mag.x === dm) return;
        const moved = sx.x !== cx || sy.x !== cy;
        cx = sx.x; cy = sy.x; dm = mag.x;
        const dx = cx + bx, dy = cy + by;
        if (moved) {
          const at = (q                          , z        ) => P(dx + q.u, dy + q.v, z);
          legs.setAttribute("d", feet.map(([c, s]) => {
            const fx = dx + c * FOOT, fy = dy + s * FOOT;
            const z = floor(fx, fy);
            return seg(P(fx, fy, z), P(dx + c * (R - 1), dy + s * (R - 1), LZ)) + poly(pad.map((q) => P(fx + q.u, fy + q.v, z)));
          }).join(""));
          put(rim, { sil: poly(hull(ring.map((q) => at(q, LZ)).concat(ring.map((q) => at(q, top))))), crease: poly(lens.map((q) => at(q, top))) });
          glint.setAttribute("d", open(shine.map((q) => at(q, top))));
        }
        // A line on the sheet, enlarged about the point the eye sees through the
        // glass's centre, and kept where it falls inside the glass.
        const r = GLASS - 1;
        const cut = (p      , q      ) => {
          const a0 = (p[0] - cx) * dm, a1 = (p[1] - cy) * dm, e0 = (q[0] - p[0]) * dm, e1 = (q[1] - p[1]) * dm;
          const A = e0 * e0 + e1 * e1, B = a0 * e0 + a1 * e1, D = B * B - A * (a0 * a0 + a1 * a1 - r * r);
          if (D <= 0) return "";
          const t0 = Math.max(0, (-B - Math.sqrt(D)) / A), t1 = Math.min(1, (-B + Math.sqrt(D)) / A);
          return t1 > t0 ? seg(P(dx + a0 + e0 * t0, dy + a1 + e1 * t0, top), P(dx + a0 + e0 * t1, dy + a1 + e1 * t1, top)) : "";
        };
        let d = edge.map((q, i) => cut([q.u, q.v], [edge[(i + 1) % edge.length].u, edge[(i + 1) % edge.length].v])).join("");
        for (const [p, q] of lines) d += cut(p, q);
        seen.setAttribute("d", d);
      }

      const loop = register(stage, (dt) => { const a = stepS(sx, dt), b = stepS(sy, dt), c = stepS(mag, dt); draw(); return a || b || c; });
      bag.add(loop.unregister);
      rim.sil.classList.add("hi");
      read.textContent = "rest";
      draw();

      bag.add(pointer(stage, {
        move: (p) => {
          // the pointer on the sheet's plane, which never moves: the glass comes to cover the point under it
          const [x, y] = unproj(C, p[0], p[1], 0);
          sx.t = clamp(x, ML, SW - MR); sy.t = clamp(y, Y0, rowY(ROWS - 1));
          read.textContent = `row ${Math.round((sy.t - Y0) / DY) + 1} · 0`;
          loop.wake();
        },
        leave: () => { sx.t = REST[0]; sy.t = REST[1]; read.textContent = "rest"; loop.wake(); },
      }));
      bag.add(() => svg.replaceChildren());

      return { set: (v) => { mag.t = v; loop.wake(); }, destroy: bag.dispose };
    };
    return { mount, label: "A stand loupe over a blank ruled sheet: the pointer drags it across, and the rules pass enlarged under the glass with nothing between them.", rest: "rest", range: [1.3, 1.8, 2.6] };
  })();

  const sieve = (() => {
    /**
     * Sieve: three test sieves stacked over a pan, standing a little apart. The
     * pointer's height picks a sieve; it rises clear of the one below, the ones
     * above it ride up with it, and each mesh is bare. At rest the stack is parted
     * under the middle sieve, whose rim is bright. The slider is the gap.
     *
     * The pattern: one of many. A tween for the gap under each sieve, staggered
     * outwards from the one picked. The pick is read from the sieves' rest
     * heights, which move only with the slider, never from the stack on screen.
     */

    const N = 3, R = 36, H = 11, PAN = 8, WALL = 2.6, SEAT = 2, FLOOR = 1.6; // sieves, radius, a sieve's height, the pan's, wall, closed gap, the mesh above a sieve's foot
    const CHORDS = [-22, -11, 0, 11, 22], STEP = 40, S = 2.35, REST = 0.8, RIDE = 0.6; // mesh chords, stagger ms, scale, the rest gap and the gap above a pick, as shares of the gap

    /** The gap under sieve i when sieve f is picked (-1 for rest: the stack parted under the middle one). */
    const under = (f        , i        , gap        ) => {
      const a = f < 0 ? 1 : f;
      return i === a ? (f < 0 ? gap * REST : gap) : f >= 0 && i === a + 1 ? gap * RIDE : SEAT;
    };

    const mount              = ({ stage, svg, read }, value) => {
      const bag = disposer();
      const [, MID, MAX] = TABLE.sieve;
      const C = Cam(45, 0.5, S);
      // The tallest pose (a lower sieve picked at the widest gap) and the rest stack at the default gap. The box
      // runs as far below the rest stack's middle as the tallest top is above it: rest sits in the middle, and the tallest still fits.
      const tall = PAN + N * H + SEAT + MAX * (1 + RIDE), rest = PAN + N * H + 2 * SEAT + MID * REST;
      const ext         = [];
      for (const [x, y] of [[-R, 0], [R, 0], [0, -R], [0, R]]) ext.push([x, y, rest - tall], [x, y, tall]);
      fit(C, ext, 200, 166);
      const P = proj(C), y0 = P(0, 0, 0)[1];
      const rise = (z        ) => P(0, 0, z)[1] - y0;
      const outer = circ(R, 72), inner = circ(R - WALL, 72);
      const g = mk("g", {}, svg);

      // The pan, then the sieves bottom to top: each a drum, its mouth, and its mesh seen through the mouth.
      const drum = (z0        , z1        )         => hull(outer.map((q) => P(q.u, q.v, z0)).concat(outer.map((q) => P(q.u, q.v, z1))));
      put(solid(g), { sil: poly(drum(0, PAN)), crease: poly(inner.map((q) => P(q.u, q.v, PAN))) });
      const parts = Array.from({ length: N }, () => ({ s: solid(g), mesh: mk("path", { class: "nf lo" }, g) }));

      /** The runs of a line on the floor at zf that show through the mouth at zm. */
      const through = (pts                 , zf        , zm        )           => {
        const runs           = [[]];
        for (const [u, v] of pts) {
          const s = P(u, v, zf), m = unproj(C, s[0], s[1], zm);
          if (Math.hypot(u, v) < R - WALL && Math.hypot(m[0], m[1]) < R - WALL) runs[runs.length - 1].push(s);
          else if (runs[runs.length - 1].length) runs.push([]);
        }
        return runs.filter((r) => r.length > 1);
      };
      // The mesh: chords both ways, and the floor's edge, begun at the front so its far run is one piece.
      const chord = (a      , b      )         => Array.from({ length: 29 }, (_, k) => [a[0] + ((b[0] - a[0]) * k) / 28, a[1] + ((b[1] - a[1]) * k) / 28]);
      const lines = CHORDS.flatMap((c) => [chord([c, -R], [c, R]), chord([-R, c], [R, c])]);
      lines.push(Array.from({ length: 73 }, (_, k) => { const t = Math.PI / 4 + (k / 72) * Math.PI * 2, r = R - WALL - 0.05; return [r * Math.cos(t), r * Math.sin(t)]; }));

      // A sieve standing on the ground, drawn once. What shows through the mouth depends only on the mouth's
      // height over the mesh, so a sieve at any height is this, moved up the screen.
      const body = drum(0, H), mouth = inner.map((q) => P(q.u, q.v, H)), mesh = lines.flatMap((l) => through(l, FLOOR, H));
      const up = (pts                 , dy        ) => pts.map((p)       => [p[0], p[1] + dy]);

      const gaps = Array.from({ length: N }, () => tween(SEAT));
      const drawn = gaps.map(() => NaN);
      let picked = -2, gap = value;
      function draw(now        ) {
        let z = PAN;
        gaps.forEach((t, i) => {
          z += tval(t, now);
          if (z !== drawn[i]) {
            drawn[i] = z;
            const dy = rise(z);
            put(parts[i].s, { sil: poly(up(body, dy)), crease: poly(up(mouth, dy)) });
            parts[i].mesh.setAttribute("d", mesh.map((r) => open(up(r, dy))).join(""));
          }
          z += H;
        });
      }

      const loop = register(stage, (_dt, now) => { draw(now); return gaps.some((t) => !tdone(t, now)); });
      bag.add(loop.unregister);

      /** Sets every gap for a pick, f being the sieve picked, or -1 for rest. */
      function choose(f        , now        ) {
        if (f === picked) return;
        picked = f;
        const a = f < 0 ? 1 : f;
        gaps.forEach((t, i) => tset(t, under(f, i, gap), now, Math.abs(i - a) * STEP));
        parts.forEach((p, i) => p.s.sil.classList.toggle("hi", i === a));
        read.textContent = f < 0 ? "rest" : `sieve ${N - f} · 0`;
        loop.wake();
      }
      choose(-1, -1e9);
      draw(0);

      /** The rest stack's middles on screen, bottom to top: what the pointer's height is read against. */
      const bands = () => { let z = PAN; return gaps.map((_, i) => { z += under(-1, i, gap); const y = P(0, 0, z + H / 2)[1]; z += H; return y; }); };
      let mids = bands();
      const pick = (p      ) => mids.reduce((best, y, i) => (Math.abs(p[1] - y) < Math.abs(p[1] - mids[best]) ? i : best), 0);

      bag.add(pointer(stage, { move: (p) => choose(pick(p), performance.now()), leave: () => choose(-1, performance.now()) }));
      bag.add(() => svg.replaceChildren());

      return {
        set: (v) => { gap = v; mids = bands(); const f = picked; picked = -2; choose(f, performance.now()); },
        destroy: bag.dispose,
      };
    };
    return { mount, label: "Three test sieves stacked over a pan: the pointer's height picks one, it rises clear of the stack, and every mesh is bare.", rest: "rest", range: [6, 14, 24] };
  })();

  const elevator = (() => {
    /**
     * Elevator: an open shaft, two walls at its back, the car inside it on two
     * guide rails, and four floors running off to the right of it, one landing
     * in front of the car's door on each. A rope runs from the car's crosshead
     * up through the head slab, over the traction sheave and down to a
     * counterweight that falls as the car rises. The pointer's height on the stage
     * picks a floor; the car travels there on a spring, through every floor in
     * between, and the floor it is bound for takes the bright stroke. At rest the
     * car is caught between the first and the second floor, bright. The slider is
     * the car's spring stiffness: stiffer travels faster.
     *
     * The pattern: scrub and pick. A spring for where the car is, a choice read
     * from the fixed floors, never from the car on screen.
     */



    const SX = 32, SY = 34, FH = 36, CH = 25, T = 2.5, NF = 4, TOP = 3 * FH + CH + 7;
    const CAR      = [5, 7, 28, 27], RX = 16.5, CW      = [-8, 11, -2, 23], CWH = 17;
    const WALL = 2;
    /** The plinth: under the shaft, and under the floors where they run back past the shaft's wall, no further. */
    const BASE = fillet([[-16, -2], [33, -2], [33, -56], [76, -56], [76, 38], [-16, 38]], [3, 2, 4, 6, 6, 6]);
    /** A floor's outline: the plate to the right of the shaft and the landing in front of the car's door, as one L. */
    const FLOOR = fillet([[33, -56], [72, -56], [72, -6], [43, -6], [43, 34], [33, 34]], [4, 4, 4, 3, 3, 3]);
    const CWX = (CW[0] + CW[2]) / 2, SR = (RX - CWX) / 2;
    /** The sheave's centre. */
    const SC       = [CWX + SR, SY / 2, TOP + 3 + SR + 2];
    const REST_Z = 1.5 * FH - 4;
    const NAMES = ["ground", "floor 1", "floor 2", "floor 3"];

    const mount              = ({ stage, svg, read }, value) => {
      const bag = disposer();
      const C = Cam(45, 0.5, 1.3);
      fit(C, [[-16, -56, -8], [76, 38, -8], [76, -56, -8], [-16, 38, -8], [SC[0], SC[1], SC[2] + SR]], 200, 166);
      const P = proj(C), front = facing(C);
      const g = mk("g", {}, svg);
      const block = (box     , r        , b        , z0        , z1        ) => { const [o, i] = rings(...box, r, b); put(solid(g), prism(P, front, o, i, z0, z1)); };
      const line = (cls        ) => mk("path", { class: cls }, g);
      // A slab on any outline, convex or not: its silhouette is the far run of the
      // top joined to the near run of the underside; the top's near run is the crease.
      const slab = (pts        , z0        , z1        ) => {
        const n = pts.length, near = pts.map((p, i) => { const q = pts[(i + 1) % n]; return q[1] - p[1] - (q[0] - p[0]) > 0; });
        const runOf = (want         ) => {
          const s = near.findIndex((f, i) => f === want && near[(i + n - 1) % n] !== want), out         = [];
          for (let i = s; near[i % n] === want; i++) out.push(pts[i % n]);
          return out.concat([pts[(s + out.length) % n]]);
        };
        const at = (r        , z        ) => r.map((p) => P(p[0], p[1], z)), back = runOf(false), fore = runOf(true);
        const sil = mk("path", { class: "sil", d: poly(at(back, z1).concat(at(fore, z0))) }, g);
        mk("path", { class: "nf lo", d: open(at(fore, z1)) }, g);
        return sil;
      };

      // The plinth, the shaft's two back walls, then back to front: the far rail,
      // the counterweight and its rope, the car, the near rail.
      slab(BASE, -8, -T);
      block([-14 - WALL, -WALL, -14, SY], 1, 0.5, -T, TOP);
      block([-14, -WALL, SX, 0], 1, 0.5, -T, TOP);
      block([RX - 1.3, 3, RX + 1.3, 5.4], 0.8, 0.5, -T, TOP);
      const [cwo, cwi] = rings(...CW, 1.6, 0.8);
      const cw = solid(g), cwBands = line("nf lo"), cwRope = line("nf");
      const [co, ci] = rings(...CAR, 2.4, 1.1);
      const car = solid(g), door = line("nf"), split = line("nf lo");
      const [ho, hi] = rings(RX - 1.7, 5.4, RX + 1.7, 28.6, 0.8, 0.5);
      const head = solid(g), rope = line("nf");
      block([RX - 1.3, 28.6, RX + 1.3, 31], 0.8, 0.5, -T, TOP);

      // The head slab, the machine behind the sheave, the ropes up to it, the sheave.
      block([-14 - WALL, -WALL, SX + 1, SY + 1], 4, 1.4, TOP, TOP + 3);
      block([CWX + 2, 4, RX - 2, SY / 2 - 3], 2, 1, TOP + 3, SC[2] + 4);
      mk("path", { class: "nf", d: seg(P(RX, SY / 2, TOP + 3), P(RX, SY / 2, SC[2])) + seg(P(CWX, SY / 2, TOP + 3), P(CWX, SY / 2, SC[2])) }, g);
      const disc = (y        , r        ) => circ(r, 28).map((q) => P(SC[0] + q.u, y, SC[2] + q.v));
      put(solid(g), { sil: poly(hull(disc(SY / 2 - 1.8, SR).concat(disc(SY / 2 + 1.8, SR)))), crease: poly(disc(SY / 2 + 1.8, SR - 1.4)) });
      const spokes = line("nf lo");
      mk("path", { class: "nf lo", d: poly(disc(SY / 2 + 1.8, 2.6)) }, g);

      // The floors, bottom to top: each an L-shaped slab, two columns at its
      // right holding up the next, and its number in dots on the landing by the door.
      const lands                                                            = [];
      for (let f = 0; f < NF; f++) {
        const z = f * FH, sil = slab(FLOOR, z - T, z);
        if (f < NF - 1) for (const y of [-53, -15]) block([62, y, 68, y + 6], 1.5, 0.8, z, z + FH - T);
        const dots                      = [];
        for (let k = 0; k <= f; k++) { const d = flatDot(g, C, 0.8, "dot off"); place(d, P(37, CAR[1] - 3 - k * 3, z)); dots.push(d); }
        lands.push({ sil, dots });
      }

      const sp = spring(REST_Z, { k: value, c: 1.8 * Math.sqrt(value) });
      let drawn = NaN, chosen                = null;

      function draw(z        ) {
        const zc = 3 * FH - z + 6, mid = (CAR[1] + CAR[3]) / 2;
        put(cw, prism(P, front, cwo, cwi, zc, zc + CWH));
        cwBands.setAttribute("d", [5, 9, 13].map((v) => seg(P(CW[0] + 0.6, CW[3], zc + v), P(CW[2] - 0.6, CW[3], zc + v))).join(""));
        cwRope.setAttribute("d", seg(P(CWX, SY / 2, zc + CWH), P(CWX, SY / 2, TOP)));
        put(car, prism(P, front, co, ci, z, z + CH));
        door.setAttribute("d", poly(rrect(CAR[1] + 3.5, z + 1.2, CAR[3] - 3.5, z + CH - 4, 1.2, 4).map((q) => P(CAR[2], q.u, q.v))));
        split.setAttribute("d", seg(P(CAR[2], mid, z + 1.2), P(CAR[2], mid, z + CH - 4)));
        put(head, prism(P, front, ho, hi, z + CH, z + CH + 2.4));
        rope.setAttribute("d", seg(P(RX, SY / 2, z + CH + 2.4), P(RX, SY / 2, TOP)));
        // the sheave turns as the rope runs over it
        const a = z / SR, y = SY / 2 + 1.8, at = (t        , r        ) => P(SC[0] + Math.cos(t) * r, y, SC[2] + Math.sin(t) * r);
        spokes.setAttribute("d", [0, 1, 2, 3, 4, 5].map((k) => seg(at(a + k * Math.PI / 3, 2.6), at(a + k * Math.PI / 3, SR - 1.4))).join(""));
      }

      const B = register(stage, (dt) => {
        const m = stepS(sp, dt);
        if (sp.x !== drawn) { drawn = sp.x; draw(sp.x); }
        return m;
      });
      bag.add(B.unregister);

      // The floor under the pointer: its height read on the fixed column of the car's door, against the floors, which never move.
      const base = P(CAR[2], SY / 2, 0)[1], perZ = base - P(CAR[2], SY / 2, 1)[1];
      const pick = (p      ) => clamp(Math.floor(((base - p[1]) / perZ + 8) / FH), 0, NF - 1);

      function choose(f        ) {
        if (f === chosen) return;
        chosen = f;
        sp.t = f < 0 ? REST_Z : f * FH;
        car.sil.classList.toggle("hi", f < 0);
        lands.forEach((l, i) => {
          l.sil.classList.toggle("hi", i === f);
          l.dots.forEach((d) => d.setAttribute("class", i === f ? "dot m" : "dot off"));
        });
        read.textContent = f < 0 ? "rest" : NAMES[f];
        B.wake();
      }
      choose(-1);

      bag.add(pointer(stage, { move: (p) => choose(pick(p)), leave: () => choose(-1) }));
      bag.add(() => svg.replaceChildren());

      return {
        set: (v) => { sp.k = v; sp.c = 1.8 * Math.sqrt(v); B.wake(); },
        destroy: bag.dispose,
      };
    };
    return { mount, label: "Four floors beside an open shaft. The pointer's height picks a floor, and the car travels there through the ones between.", rest: "rest", range: [40, 100, 220] };
  })();

  const slow = (() => {
    /**
     * Fig 9.5, Slow — hover dilates the clock. Crates ride a belt through a gate,
     * growing in at one end and out at the other, each lid carrying its serial as
     * a 3 × 3 dot code. Hovering never stops the world: it springs the clock's
     * rate down to the slider's value, so everything keeps moving, just slowly
     * enough to read. The crate nearest the pointer lifts and its serial goes to
     * the read-out. The gate's two posts and lintel are depth-sorted with the
     * crates, and brighten as a crate passes under them. Ported from the study's `#slow`
     * (design/lab-hairline/cartilha-v2.html).
     *
     * Ambient: the loop runs every frame while the stage is on screen (the stage
     * puts it to sleep offscreen). Under reduced motion the resting rate is 0, so
     * the belt stands still until hovered, when it creeps at the slider's rate.
     */

    const L = 210, BW = 26, BT = 5, CUBE = 15, NC = 6, SPEED = 1 / 9, GATE = L * 0.62, GH = 38;




    /** How big a crate is at belt position u (0..1): smoothstep in over the first 8%, out over the last. */
    const size = (u        ) => { const a = clamp(Math.min(u, 1 - u) / 0.08, 0, 1); return a * a * (3 - 2 * a); };

    /**
     * How lit the gate is by a crate at x: a cos² swell, full under the lintel. It
     * rises over half the gap between crates (about .75s at full speed) and falls
     * over half that once the crate is through (about .37s), so the gate breathes
     * in and lets go. Read off the belt, not a timer, so it slows with the clock.
     */
    const RISE = L / NC / 2, FALL = RISE / 2;
    const glow = (x        ) => {
      const d = x - GATE, w = d < 0 ? RISE : FALL;
      return Math.abs(d) >= w ? 0 : Math.cos((Math.PI / 2) * (Math.abs(d) / w)) ** 2;
    };

    const mount              = ({ stage, svg, read }, value) => {
      const bag = disposer();
      let slow = value, over              = null, clock = 2.4;
      const rate = spring(1, { eps: 0.002 });
      const C = Cam(45, 0.5, 1.8);
      fit(C, [[0, 0, 0], [L, BW, 0], [L, 0, 0], [0, BW, 0], [0, 0, GH], [GATE, -8, GH]], 200, 168);
      const P = proj(C), front = facing(C);
      const g = mk("g", {}, svg);
      const [bR, bI] = rings(0, 0, L, BW, 5, 1.3);
      put(solid(g), prism(P, front, bR, bI, 0, BT));
      const slats = mk("path", { class: "nf lo" }, g);
      // crates and the gate share one layer, re-sorted by depth (x + y at 45°) every frame
      const layer = mk("g", {}, g);
      const pool          = [];
      for (let j = 0; j < NC; j++) {
        const el        = { ...solid(layer), dots: [] };
        for (let k = 0; k < 9; k++) el.dots.push(flatDot(el.g, C, 1, "dot off"));
        pool.push(el);
      }
      // the lintel's key is past both posts and every crate under it, so it paints last among its neighbours
      const gate = ([[-8, -3, 0, GH - 4, GATE - 5.5], [BW + 3, BW + 8, 0, GH - 4, GATE + BW + 5.5], [-8, BW + 8, GH - 4, GH, GATE + BW + 8.5]]         )
        .map(([y0, y1, z0, z1, key]) => {
          const el = solid(layer), [rg, ig] = rings(GATE - 1.6, y0, GATE + 1.6, y1, 1.4, 0.6);
          put(el, prism(P, front, rg, ig, z0, z1));
          // the glow is driven every frame from the belt; the stroke's CSS transition would only lag it
          el.sil.style.transition = "none";
          return { el, key };
        });
      const lifts = Array.from({ length: NC }, () => spring(0, { eps: 0.03 }));
      let hot = -1, order = "", gatePct = 0;

      const B = register(stage, (dt) => {
        let m = stepS(rate, dt);
        const base = reducedMotion() ? 0 : 1;
        if (!over) rate.t = base;
        clock += dt * rate.x;
        const items         = [];
        for (let j = 0; j < NC; j++) {
          const q = j / NC + clock * SPEED, u = q - Math.floor(q), lap = Math.floor(q);
          items.push({ j, x: u * L, s: size(u), serial: 141 + lap * NC + j });
        }
        // nearest crate to the pointer, on the belt plane
        let want = -1;
        if (over) {
          let best = 34;
          for (const it of items) if (it.s > 0.6 && Math.abs(it.x - over[0]) < best) { best = Math.abs(it.x - over[0]); want = it.j; }
        }
        hot = want;
        lifts.forEach((sp, j) => { sp.t = j === hot ? 11 : 0; if (stepS(sp, dt)) m = true; });
        items.sort((a, b) => a.x - b.x);
        let gateGlow = 0, hotSerial = 0;
        // stable ids, so the layer is only re-appended when the order actually changes
        const draw                                                         = gate.map((p, i) => ({ id: "g" + i, key: p.key, g: p.el.g }));
        items.forEach((it, k) => {
          const el = pool[k], sz = CUBE * it.s, x0 = it.x - sz / 2, x1 = it.x + sz / 2, y0 = BW / 2 - sz / 2, y1 = BW / 2 + sz / 2;
          const z0 = BT + lifts[it.j].x, z1 = z0 + sz;
          draw.push({ id: k, key: it.x + BW / 2, g: el.g });
          if (sz < 0.3) { el.g.setAttribute("visibility", "hidden"); return; }
          el.g.removeAttribute("visibility");
          const [rg, ig] = rings(x0, y0, x1, y1, 2.6 * it.s, 0.9 * it.s);
          put(el, prism(P, front, rg, ig, z0, z1));
          const isHot = it.j === hot;
          el.sil.classList.toggle("hi", isHot);
          // the serial, as a 3 × 3 code on the lid (bit 0 top-left)
          const pitch = sz * 0.2, rr = r2(0.55 * it.s * C.S);
          el.dots.forEach((d, b) => {
            place(d, P(it.x + ((b % 3) - 1) * pitch, BW / 2 + (Math.floor(b / 3) - 1) * pitch, z1));
            d.setAttribute("rx", String(rr)); d.setAttribute("ry", String(r2(rr * C.k)));
            d.setAttribute("class", (it.serial >> b) & 1 ? (isHot ? "dot" : "dot m") : "dot off");
          });
          if (isHot) hotSerial = it.serial;
          gateGlow = Math.max(gateGlow, glow(it.x) * it.s);
        });
        draw.sort((a, b) => a.key - b.key);
        const sig = draw.map((d) => d.id).join();
        if (sig !== order) { order = sig; draw.forEach((d) => layer.appendChild(d.g)); }
        // the edge colour mixed toward the lit one; written only when the percent changes
        const pct = Math.round(gateGlow * 100);
        if (pct !== gatePct) {
          gatePct = pct;
          const stroke = pct ? `color-mix(in srgb, var(--hl-hi) ${pct}%, var(--hl-edge))` : "";
          gate.forEach((p) => { p.el.sil.style.stroke = stroke; });
        }
        const off = (((clock * SPEED * L) % 21) + 21) % 21, sl           = [];
        for (let x = off; x < L; x += 21) if (x > 5 && x < L - 5) sl.push(seg(P(x, 4, BT), P(x, BW - 4, BT)));
        slats.setAttribute("d", sl.join(""));
        read.textContent = `rate ${rate.x.toFixed(2)}×` + (hot >= 0 ? ` · #${String(hotSerial).padStart(4, "0")}` : "");
        // The study asks for every frame. Under reduced motion at rest the belt is
        // stopped, so the frame would repeat itself: sleep until input or a change
        // of preference wakes it (both do). Visually the same.
        if (reducedMotion() && !over && rate.x === 0) return m;
        return true;
      });
      bag.add(B.unregister);
      bag.add(pointer(stage, {
        move: (p) => { over = unproj(C, p[0], p[1], BT); rate.t = slow; B.wake(); },
        leave: () => { over = null; B.wake(); },
      }));
      bag.add(() => svg.replaceChildren());
      return { set: (v) => { slow = v; if (over) rate.t = v; B.wake(); }, destroy: bag.dispose };
    };
    return { mount, label: "Crates riding a belt through a gate. Hovering slows the clock without stopping it.", rest: "rate 1.00×", range: [0.6, 0.2, 0.05] };
  })();

  const cabinet = (() => {
    /**
     * Cabinet: a server rack of twelve 1U blades between two drilled rails, on a
     * plinth. Each blade is a chassis behind a faceplate: ears with pull handles
     * on the rails, four drive bays, a vent and a status lamp. The pointer's
     * height is read on the rack's closed front, and the blades near it slide out
     * along their rails, the farther the less, each on its own spring; the one
     * under it comes all the way and its lamp lights. At rest the last update has
     * stopped part-way: blade 7 half out and lit, a few others caught on the way.
     * The slider is the reach, in blades.
     *
     * The pattern: a continuous field, as Keyboard's, over a stack: a spring per
     * blade, a falloff by distance, a hit test on the rest pose's planes.
     */

    const N = 12, U = 10.4, BH = 9.6, W = 84, EAR = 4, FT = 2, D = 44, OUT = 26;
    const X0 = -10, X1 = W + 10, Z0 = 6, ZB = 11, ZT = ZB + (N - 1) * U + BH, H = ZT + 6;
    /** Where the last update stopped: blade 7 half out, its neighbours and two others caught on their way. */
    const REST = [0, 0, 0.2, 0, 0, 0.3, 0.58, 0.26, 0, 0, 0.13, 0];
    const LIT = 6;

    /** The share of full travel a blade comes out, u reaches from the pointer: all of it under the pointer, none past the reach. */
    const falloff = (u        ) => (u >= 1 ? 0 : (1 - u) * (1 - u));
    /** On a plate's front face, the samples whose edge meets its top or its right side: they lie inside the silhouette. */
    const inner = (q        ) => 0.375 * q.nu + 0.307 * q.nv > 0;

    /** A plate standing in the x-z plane, from y0 back to y1 front: its silhouette, and the crease of its front face. */
    function slab(P           , ring      , inset             , y0        , y1        ) {
      const at = (r      , y        ) => r.map((q)       => P(q.u, y, q.v));
      return { sil: poly(hull(at(ring, y0).concat(at(ring, y1)))), crease: inset ? open(at(run(inset, inner), y1)) : "" };
    }








    const mount              = ({ stage, svg, read }, value) => {
      const bag = disposer();
      const C = Cam(45, 0.5, 1.5);
      const yo = D + FT + OUT;
      fit(C, [[X0, 0, 0], [X1, 0, H], [X1, D, 0], [X0, 0, H], [-EAR, yo, ZB], [-EAR, yo, ZT], [W + EAR, yo, ZB]], 200, 166);
      const P = proj(C), front = facing(C);
      let R = value, over                = null, lit               = null;

      const g = mk("g", {}, svg);
      // the plinth, set back under the cabinet, then the cabinet itself
      const [pr, pi] = rings(X0 + 3, 3, X1 - 3, D - 3, 3, 1.2);
      put(solid(g), prism(P, front, pr, pi, 0, Z0));
      const [br, bi] = rings(X0, 0, X1, D, 3.5, 1.6);
      put(solid(g), prism(P, front, br, bi, Z0, H));
      // its front: the opening's edge round the rails, a hole in each rail for every U; and the side panel's inset
      const onFront = (r      ) => r.map((q)       => P(q.u, D, q.v)), onSide = (r      ) => r.map((q)       => P(X1, q.u, q.v));
      mk("path", { d: poly(onFront(rrect(-7.6, ZB - 2.2, W + 7.6, ZT + 2.2, 2, 4))) + poly(onSide(rrect(5, Z0 + 7, D - 5, H - 7, 3, 4))), class: "lo nf" }, g);
      for (let i = 0; i < N; i++) for (const x of [-5.8, W + 5.8]) {
        place(mk("circle", { r: 0.75, class: "dot off" }, g), P(x, D, ZB + i * U + BH / 2));
      }

      // Bottom to top: the camera looks down, so a lower blade can never cover a higher one.
      const blades          = [];
      for (let i = 0; i < N; i++) {
        const z = ZB + i * U, gi = mk("g", {}, g);
        blades.push({
          i, z,
          body: rrect(0, z + 0.4, W, z + BH - 0.4, 1.6, 4),
          face: rrect(-EAR, z, W + EAR, z + BH, 2, 4),
          faceIn: rrect(-EAR + 0.8, z + 0.8, W + EAR - 0.8, z + BH - 0.8, 1.2, 4),
          chassis: solid(gi), plate: solid(gi),
          marks: mk("path", { class: "lo nf" }, gi),
          lamp: mk("circle", { r: 1.1, class: "dot off" }, gi),
          sp: spring(OUT * REST[i], { eps: 0.02 }), drawn: NaN,
        });
      }

      /** Blade b's faceplate marks, drawn on its front at y: two handles, four bays, a vent. */
      function marks(b       , y        ) {
        const z = b.z, F = (r      ) => poly(r.map((q)       => P(q.u, y, q.v)));
        let d = F(rrect(-3.4, z + 2, -1.2, z + BH - 2, 1, 3)) + F(rrect(W + 1.2, z + 2, W + 3.4, z + BH - 2, 1, 3));
        for (let k = 0; k < 4; k++) d += F(rrect(4 + k * 10.6, z + 2, 13.8 + k * 10.6, z + BH - 2, 1, 3));
        for (let k = 0; k < 8; k++) d += seg(P(50 + k * 2.6, y, z + 2.5), P(50 + k * 2.6, y, z + BH - 2.5));
        return d;
      }

      function drawBlade(b       ) {
        const o = b.sp.x;
        if (o === b.drawn) return;
        b.drawn = o;
        const yf = D + o + FT, zm = b.z + BH / 2;
        const ch = slab(P, b.body, null, D, D + o + 0.5);
        // the slide: where the chassis's side rides out along its rail
        put(b.chassis, { sil: ch.sil, crease: seg(P(W, D, zm), P(W, D + o, zm)) });
        put(b.plate, slab(P, b.face, b.faceIn, D + o, yf));
        b.marks.setAttribute("d", marks(b, yf));
        place(b.lamp, P(W - 5, yf, zm));
      }

      function light(b       ) {
        if (b === lit) return;
        if (lit) { lit.plate.sil.classList.remove("hi"); lit.lamp.setAttribute("class", "dot off"); }
        lit = b;
        lit.plate.sil.classList.add("hi");
        lit.lamp.setAttribute("class", "dot");
      }

      const B = register(stage, (dt) => {
        let m = false;
        for (const b of blades) { if (stepS(b.sp, dt)) m = true; drawBlade(b); }
        return m;
      });
      bag.add(B.unregister);

      // The hit test: the pointer is put on the rack's planes with every blade home, which never move.
      const o0 = P(0, 0, 0), E = [P(1, 0, 0), P(0, 1, 0), P(0, 0, 1)].map((p) => [p[0] - o0[0], p[1] - o0[1]]);
      /** The world point under screen point p on the plane where coordinate `axis` is c. */
      function onPlane(p      , axis        , c        )       {
        const [a, k] = [0, 1, 2].filter((n) => n !== axis), ea = E[a], ek = E[k];
        const rx = p[0] - o0[0] - c * E[axis][0], ry = p[1] - o0[1] - c * E[axis][1], det = ea[0] * ek[1] - ea[1] * ek[0];
        const w       = [0, 0, 0];
        w[axis] = c; w[a] = (rx * ek[1] - ry * ek[0]) / det; w[k] = (ea[0] * ry - ea[1] * rx) / det;
        return w;
      }
      /** The pointer's height, in blades from the bottom one, or null off the rack: first on each faceplate where it
       * stands at rest, top down as a higher blade covers a lower one; then on the closed front, and the side panel. */
      function hit(p      )                {
        for (let i = N - 1; i >= 0; i--) {
          const q = onPlane(p, 1, D + FT + OUT * REST[i]), z = (q[2] - ZB - BH / 2) / U;
          if (q[0] >= -EAR && q[0] <= W + EAR && Math.abs(z - i) <= 0.5) return z;
        }
        const f = onPlane(p, 1, D + FT), s = onPlane(p, 0, X1);
        let z                = null;
        if (f[0] >= X0 - OUT - 4 && f[0] <= X1 && f[2] >= -OUT * 0.8 && f[2] <= H) z = f[2];
        else if (s[1] >= 0 && s[1] <= D && s[2] >= 0 && s[2] <= H + 4) z = s[2];
        return z === null ? null : clamp((z - ZB - BH / 2) / U, 0, N - 1);
      }

      function retarget() {
        if (over === null) {
          for (const b of blades) b.sp.t = OUT * REST[b.i];
          light(blades[LIT]); read.textContent = "rest";
        } else {
          for (const b of blades) b.sp.t = OUT * falloff(Math.max(0, Math.abs(b.i - over) - 0.5) / R);
          const a = Math.round(over);
          light(blades[a]); read.textContent = "blade " + (a + 1);
        }
        B.wake();
      }
      light(blades[LIT]);

      bag.add(pointer(stage, {
        move: (p) => { over = hit(p); retarget(); },
        leave: () => { over = null; retarget(); },
      }));
      bag.add(() => svg.replaceChildren());

      return {
        set: (v) => { R = v; if (over !== null) retarget(); },
        destroy: bag.dispose,
      };
    };
    return { mount, label: "A rack of twelve blades: the pointer's height pulls the nearest ones out on their rails, the farther the less.", rest: "rest", range: [1.5, 3, 5] };
  })();

  const dish = (() => {
    /**
     * Dish: a parabolic dish on a two-axis gimbal. A base plate engraved with an
     * azimuth scale, a turntable with an index dot, and a yoke whose two arms hold
     * the elevation axis; the dish hangs on it by two trunnions at its rim, with a
     * feed horn on three struts at its focus. The pointer aims the dish, as if it
     * stood in front of the screen: azimuth and elevation each ride a spring. The
     * bowl's outline is computed at every pose: the rim circle projected, and the
     * hull of the rim and the back. The reach is clamped so the dish always shows
     * its inside. At rest it looks off to the right, rim bright. The slider is the
     * azimuth reach, in degrees; elevation reaches half of it.
     *
     * The pattern: a continuous aim. Two springs, a clamped reach, a hit test that
     * reads only the pointer, and a paint order fixed by separating planes.
     */

    const R = 26, FOC = 17, SK = 1.4, DEP = (R * R) / (4 * FOC), ZE = 46, W = 31, T = 5, ZB = 10, ZY = 16;
    const AZ0 = 45, EL0 = 40, REST = [-20, 30], PIV       = [0, 0, ZE];
    const ax = (p      , q      , s        )       => [p[0] + q[0] * s, p[1] + q[1] * s, p[2] + q[2] * s];
    const dot3 = (p      , q      ) => p[0] * q[0] + p[1] * q[1] + p[2] * q[2];


    /** An aim's frame: h and e on the ground (e is the elevation axis), a the dish's axis, u the rim's up. */
    function frame(th        , ph        )        {
      const t = rad(th), f = rad(ph), c = Math.cos(f), s = Math.sin(f);
      const h       = [Math.cos(t), Math.sin(t), 0], e       = [-Math.sin(t), Math.cos(t), 0];
      return { th, h, e, a: [h[0] * c, h[1] * c, s], u: [-h[0] * s, -h[1] * s, c] };
    }
    /** A point of the dish: `along` its axis from the rim's centre, rho out from it at angle psi. */
    const onDish = (F       , along        , rho        , psi        ) => ax(ax(ax(PIV, F.a, along), F.e, rho * Math.cos(psi)), F.u, rho * Math.sin(psi));
    /** A circle of n points about centre c, in the plane of x and y. */
    const disc = (c      , x      , y      , r        , n        ) => Array.from({ length: n }, (_, i) => ax(ax(c, x, r * Math.cos((2 * Math.PI * i) / n)), y, r * Math.sin((2 * Math.PI * i) / n)));
    /** A ring drawn in the (h, e) frame turned onto the ground. */
    const turn = (ring      , F       )       => ring.map((q) => ({
      u: q.u * F.h[0] + q.v * F.e[0], v: q.u * F.h[1] + q.v * F.e[1], nu: q.nu * F.h[0] + q.nv * F.e[0], nv: q.nu * F.h[1] + q.nv * F.e[1],
    }));







    const mount              = ({ stage, svg, read }, value) => {
      const bag = disposer();
      let reach = value, over              = null;

      // Fitted to the four corners of the widest reach, and rest, so nothing leaves the frame.
      const C = Cam(45, 0.5, 2.5), pts         = [[-30, -30, 0], [30, 30, 0], [30, -30, 0], [-30, 30, 0]];
      for (const [th, ph] of [[-25, 5], [-25, 75], [115, 5], [115, 75], REST]) {
        const F = frame(th, ph);
        pts.push(...disc(PIV, F.e, F.u, R, 16), onDish(F, FOC - DEP + 3, 0, 0));
        for (const s of [-1, 1]) pts.push(ax(ax(PIV, F.e, s * (W + T / 2)), [0, 0, 1], 6));
      }
      fit(C, pts, 200, 166);
      const P = proj(C), front = facing(C), Pv = (q      ) => P(q[0], q[1], q[2]);
      // the direction toward the camera, from the projection itself
      const o = P(0, 0, 0), cx = P(1, 0, 0), cy = P(0, 1, 0), cz = P(0, 0, 1);
      const r1 = [cx[0] - o[0], cy[0] - o[0], cz[0] - o[0]], r2 = [cx[1] - o[1], cy[1] - o[1], cz[1] - o[1]];
      const cross       = [r1[1] * r2[2] - r1[2] * r2[1], r1[2] * r2[0] - r1[0] * r2[2], r1[0] * r2[1] - r1[1] * r2[0]];
      const vl = Math.hypot(...cross) * Math.sign(cross[2]);
      const VD = cross.map((x) => x / vl)        ;

      // Static, back to front: the base, its azimuth scale, the turntable.
      const g = mk("g", {}, svg);
      const [br, bi] = rings(-30, -30, 30, 30, 9, 2);
      put(solid(g), prism(P, front, br, bi, 0, 5));
      for (let i = 0; i < 36; i++) {
        const t = (i / 36) * 2 * Math.PI, r = i % 9 === 0 ? 26.5 : 25.5;
        place(flatDot(g, C, i % 9 === 0 ? 0.75 : 0.5, "dot off"), P(r * Math.cos(t), r * Math.sin(t), 5));
      }
      put(solid(g), prism(P, front, circ(20, 48), circ(18.8, 48), 5, ZB));
      const index = flatDot(g, C, 0.8, "dot m");

      // Turning with the azimuth: the yoke's beam, then each side's arm, bearing and trunnion, in an order set per frame.
      const beam = solid(g);
      const yb = W + T / 2 + 1, [bmr, bmi] = rings(-9, -yb, 9, yb, 4, 1.4);
      const dishG = mk("g", {}, g);
      const sides         = [-1, 1].map((s) => {
        const sg = mk("g", {}, g);
        return {
          s, g: sg, near: null,
          ring: mk("path", { class: "nf" }, sg), arm: solid(sg), trun: mk("path", { class: "sil" }, sg),
          foot: rrect(-8, s * W - T / 2, 8, s * W + T / 2, 2.5, 4),
          top: rrect(-5.5, s * W - T / 2, 5.5, s * W + T / 2, 2.5, 4),
          inner: rrect(-4.5, s * W - T / 2 + 1, 4.5, s * W + T / 2 - 1, 1.5, 4),
        };
      });

      // The dish: its outline, a panel seam and the hub at its vertex seen through the aperture, the rim, the struts, the feed.
      const outline = mk("path", { class: "sil" }, dishG), seam = mk("path", { class: "nf lo" }, dishG), hubR = mk("path", { class: "nf lo" }, dishG);
      const rim = mk("path", { class: "nf hi" }, dishG), struts = mk("path", { class: "nf" }, dishG);
      const feed = solid(dishG);
      const BACK = [0, 0.35, 0.6, 0.78, 0.9, 0.97, 1];

      /** The seam at rho: the run of it seen through the aperture, its ends cut where the sight line meets the rim. */
      function seen(F       , rho        , n        ) {
        const along = (rho * rho) / (4 * FOC) - DEP, t = -along / dot3(F.a, VD), q         = [], s           = [];
        for (let i = 0; i < n; i++) {
          q.push(onDish(F, along, rho, (2 * Math.PI * i) / n));
          const hit = ax(q[i], VD, t);
          s.push(R - Math.hypot(hit[0] - PIV[0], hit[1] - PIV[1], hit[2] - PIV[2]));
        }
        if (s.every((x) => x > 0)) return poly(q.map(Pv));
        const i0 = s.findIndex((x, i) => x > 0 && s[(i + n - 1) % n] <= 0);
        if (i0 < 0) return "";
        const cut = (i        , j        ) => Pv(ax(q[i], [q[j][0] - q[i][0], q[j][1] - q[i][1], q[j][2] - q[i][2]], s[i] / (s[i] - s[j])));
        const out = [cut((i0 + n - 1) % n, i0)];
        let i = i0;
        while (s[i] > 0) { out.push(Pv(q[i])); i = (i + 1) % n; }
        out.push(cut((i + n - 1) % n, i));
        return open(out);
      }

      let drawn = "";
      function draw(th        , ph        ) {
        const key = th.toFixed(3) + "," + ph.toFixed(3);
        if (key === drawn) return;
        drawn = key;
        const F = frame(th, ph);
        place(index, P(18 * F.h[0], 18 * F.h[1], ZB));
        put(beam, prism(P, front, turn(bmr, F), turn(bmi, F), ZB, ZY));
        // a side whose outer face looks at the camera paints after the dish, inside out; the other before it, outside in
        for (const sd of sides) {
          const near = sd.s * dot3(F.e, VD) > 0;
          if (near !== sd.near) {
            sd.near = near;
            if (near) { sd.g.append(sd.trun, sd.arm.g, sd.ring); dishG.after(sd.g); }
            else { sd.g.append(sd.ring, sd.arm.g, sd.trun); dishG.before(sd.g); }
          }
          put(sd.arm, {
            sil: poly(hull(ringAt(P, turn(sd.foot, F), ZY).concat(ringAt(P, turn(sd.top, F), ZE + 6)))),
            crease: open(ringAt(P, run(turn(sd.inner, F), front), ZE + 6)),
          });
          const zz       = [0, 0, 1], out = ax(PIV, F.e, sd.s * (W + T / 2));
          sd.ring.setAttribute("d", poly(disc(out, F.h, zz, 3.4, 24).map(Pv)));
          sd.trun.setAttribute("d", poly(hull(disc(ax(PIV, F.e, sd.s * R), F.h, zz, 2.2, 16).concat(disc(ax(PIV, F.e, sd.s * (W - T / 2)), F.h, zz, 2.2, 16)).map(Pv))));
        }
        // the bowl: its outline is the hull of the rim and the back, a skin SK thick; the rim is all seen, as the reach keeps the inside to the camera
        const lip = disc(PIV, F.e, F.u, R, 72), back         = [];
        for (const f of BACK) for (let i = 0; i < 40; i++) back.push(onDish(F, (f * f * R * R) / (4 * FOC) - DEP - SK, f * R, (2 * Math.PI * i) / 40));
        outline.setAttribute("d", poly(hull(lip.concat(back).map(Pv))));
        seam.setAttribute("d", seen(F, 0.62 * R, 48));
        hubR.setAttribute("d", seen(F, 3.2, 20));
        rim.setAttribute("d", poly(lip.map(Pv)));
        const mouth = onDish(F, FOC - DEP - 3, 0, 0), tail = onDish(F, FOC - DEP + 3, 0, 0);
        struts.setAttribute("d", [90, 210, 330].map((d) => seg(Pv(onDish(F, 0, R, rad(d))), Pv(mouth))).join(""));
        put(feed, {
          sil: poly(hull(disc(mouth, F.e, F.u, 3.6, 16).concat(disc(tail, F.e, F.u, 2.4, 16)).map(Pv))),
          crease: poly(disc(tail, F.e, F.u, 1.3, 16).map(Pv)),
        });
      }

      const az = spring(REST[0], { eps: 0.01 }), el = spring(REST[1], { eps: 0.01 });
      const B = register(stage, (dt) => {
        const a = stepS(az, dt), b = stepS(el, dt);
        draw(az.x, el.x);
        return a || b;
      });
      bag.add(B.unregister);

      // The aim reads only the pointer's offset from the axis on screen, never what is drawn: nothing can flicker.
      const hub = P(0, 0, ZE);
      function retarget() {
        if (over) {
          az.t = AZ0 - reach * Math.tanh((over[0] - hub[0]) / 120);
          el.t = EL0 + (reach / 2) * Math.tanh((hub[1] - over[1]) / 90);
          read.textContent = `az ${Math.round((az.t + 360) % 360)} · el ${Math.round(el.t)}`;
        } else { az.t = REST[0]; el.t = REST[1]; read.textContent = "rest"; }
        B.wake();
      }

      bag.add(pointer(stage, {
        move: (p) => { over = p; retarget(); },
        leave: () => { over = null; retarget(); },
      }));
      bag.add(() => svg.replaceChildren());

      return {
        set: (v) => { reach = v; if (over) retarget(); },
        destroy: bag.dispose,
      };
    };
    return { mount, label: "A parabolic dish on a two-axis gimbal: the pointer aims it, and it follows on a spring.", rest: "rest", range: [30, 50, 70] };
  })();

  const router = (() => {
    /**
     * Router: a low wifi router with a row of status lights along its front edge
     * and four antennas standing on swivel bosses along its back. Each antenna is a
     * tapered rod that leans in its own upright plane, square to the line of sight,
     * so the four never touch and always paint in the same order. The pointer pulls
     * each one toward itself on its own spring: the nearest reaches all the way
     * for it, the others less the further away they are. At rest they stand as they
     * were left, the last one tilted out and bright. The slider is the spread, in
     * antennas.
     *
     * The pattern: a continuous aim over a row of parts. A spring per antenna, a
     * falloff by distance with a floor, a clamped lean, and a hit test on the
     * antennas' fixed pivots.
     */

    const X1 = 124, Y1 = 58, H = 14, T = 3, BR = 13;
    const XS = [18, 48, 78, 108], YB = 11, KH = 5, KR = 4.6, L = 56, R0 = 3.3, R1 = 2.1, ELBOW = 0.21;
    const STOP = R1 + 1, MAX = 44, REST = [-9, 3, -4, 32], LIT0 = 3;
    const D = [Math.SQRT1_2, -Math.SQRT1_2];

    /** The share of its reach an antenna takes, u pivots further from the pointer than the nearest one: all of it, down to a floor R pivots on. */
    const falloff = (u        , R        ) => clamp(1 - u / R, 0.1, 1);

    /** Antenna i's axis, `l` along it, leaning th degrees in its plane (positive leans right on screen). */
    const along = (i        , th        , l        )       => {
      const s = Math.sin(rad(th)), c = Math.cos(rad(th));
      return [XS[i] + D[0] * s * l, YB + D[1] * s * l, H + KH - 1 + c * l];
    };



    const mount              = ({ stage, svg, read }, value) => {
      const bag = disposer();
      let R = value, over              = null, lit             = null;

      // Fitted to the body and to every antenna at both ends of its lean, so nothing leaves the frame.
      const C = Cam(45, 0.5, 1.78), pts         = [[0, 0, 0], [X1, Y1, 0], [X1, 0, 0], [0, Y1, 0]];
      XS.forEach((_, i) => { for (const th of [-MAX, 0, MAX]) pts.push(along(i, th, L + R1)); });
      fit(C, pts, 200, 166);
      const P = proj(C), front = facing(C), Pv = (q      ) => P(q[0], q[1], q[2]);
      const o = P(0, 0, 0), dd = P(D[0], D[1], 0), zz = P(0, 0, 1);
      const SH = Math.hypot(dd[0] - o[0], dd[1] - o[1]), SZ = o[1] - zz[1];

      // The body: a low shell, narrower at its top than at its foot, and the status lights along its front.
      const g = mk("g", {}, svg);
      const foot = rrect(0, 0, X1, Y1, BR, 6), top = rrect(T, T, X1 - T, Y1 - T, BR - T, 6);
      const inner = rrect(T + 1.6, T + 1.6, X1 - T - 1.6, Y1 - T - 1.6, BR - T - 1.6, 6);
      put(solid(g), { sil: poly(hull(ringAt(P, foot, 0).concat(ringAt(P, top, H)))), crease: open(ringAt(P, run(inner, front), H)) });
      for (let k = 0; k < 6; k++) {
        const z = H * 0.56, y = Y1 - T * (z / H) + 0.1;
        place(mk("circle", { r: 1.05, class: k === 0 ? "dot m" : "dot off" }, g), P(34 + k * 9, y, z));
      }
      // a vent grille across the front of the lid, in staggered rows
      for (let j = 0; j < 3; j++) for (let k = 0; k < 13 - (j % 2); k++) place(flatDot(g, C, 0.5, "dot off"), P(26 + (j % 2) * 3 + k * 6, 29 + j * 5.5, H));

      // Back to front: each antenna's boss, then the antenna. Every antenna leans in a plane x + y = const, so the order never changes.
      const ants        = XS.map((x, i) => {
        const boss = solid(g);
        const shift = (ring      )       => ring.map((q) => ({ ...q, u: q.u + x, v: q.v + YB }));
        put(boss, prism(P, front, shift(circ(KR, 16)), shift(circ(KR - 1.1, 16)), H, H + KH));
        return { i, el: solid(g), sp: spring(REST[i], { eps: 0.05 }), drawn: NaN, piv: Pv(along(i, 0, 0)) };
      });
      const gap = Math.abs(ants[1].piv[0] - ants[0].piv[0]) / SH;

      /** A disc of screen points about p, r world units across. */
      const disc = (p      , r        )         => Array.from({ length: 20 }, (_, k)       => [p[0] + r * SH * Math.cos((k * Math.PI) / 10), p[1] + r * SH * Math.sin((k * Math.PI) / 10)]);
      function drawAnt(a     ) {
        const th = a.sp.x;
        if (th === a.drawn) return;
        a.drawn = th;
        const b = Pv(along(a.i, th, 0)), t = Pv(along(a.i, th, L)), e = Pv(along(a.i, th, L * ELBOW));
        const len = Math.hypot(t[0] - b[0], t[1] - b[1]), n = [-(t[1] - b[1]) / len, (t[0] - b[0]) / len];
        const w = lerp(R0, R1, ELBOW) * SH - 1.1;
        put(a.el, {
          sil: poly(hull(disc(b, R0).concat(disc(t, R1)))),
          crease: seg([e[0] + n[0] * w, e[1] + n[1] * w], [e[0] - n[0] * w, e[1] - n[1] * w]),
        });
      }
      function light(a     ) {
        if (a === lit) return;
        lit?.el.sil.classList.remove("hi");
        lit = a;
        a.el.sil.classList.add("hi");
      }

      const B = register(stage, (dt) => {
        let m = false;
        for (const a of ants) { if (stepS(a.sp, dt)) m = true; drawAnt(a); }
        return m;
      });
      bag.add(B.unregister);

      /**
       * Each antenna aims at the pointer from its fixed pivot, in its own plane. A
       * pointer within reach is raised onto the circle the tip sweeps, so a tip
       * stops just short of it and never passes it: two antennas either side of
       * the pointer meet over it, and never cross.
       */
      function retarget() {
        if (!over) {
          ants.forEach((a, i) => { a.sp.t = REST[i]; });
          light(ants[LIT0]); read.textContent = "rest";
        } else {
          const at = over;
          const dxs = ants.map((a) => (at[0] - a.piv[0]) / SH), d0 = Math.min(...dxs.map(Math.abs));
          const near = ants[dxs.findIndex((d) => Math.abs(d) === d0)];
          ants.forEach((a, i) => {
            const dx = Math.sign(dxs[i]) * Math.max(Math.abs(dxs[i]) - STOP, 0), hz = Math.max((a.piv[1] - at[1]) / SZ, Math.sqrt(Math.max(L * L - dx * dx, 0)), 0);
            const aim = (Math.atan2(dx, hz) * 180) / Math.PI;
            a.sp.t = clamp(aim, -MAX, MAX) * falloff((Math.abs(dxs[i]) - d0) / gap, R);
          });
          light(near);
          read.textContent = `antenna ${near.i + 1} · ${Math.round(Math.abs(near.sp.t))}°`;
        }
        B.wake();
      }
      light(ants[LIT0]);

      bag.add(pointer(stage, {
        move: (p) => { over = p; retarget(); },
        leave: () => { over = null; retarget(); },
      }));
      bag.add(() => svg.replaceChildren());

      return {
        set: (v) => { R = v; if (over) retarget(); },
        destroy: bag.dispose,
      };
    };
    return { mount, label: "A wifi router whose antennas lean toward the pointer, the nearest the most and the others less the further away.", rest: "rest", range: [0.5, 1.5, 3] };
  })();

  const patch = (() => {
    /**
     * Patch: a 2U rack patch panel, its face plate running out past a shallow body
     * into two rack ears, each with two screw slots. Twenty-four RJ45 jacks sit in
     * two modules of six by two, each jack a rectangle with the latch's notch on
     * top. Twenty-one hold a plug, a tapered boot and a short cable: the top row's
     * cables rise, the bottom row's hang. The pointer is put on the plane of the
     * plugs at rest; the cable under it lifts, its plug half out of the jack, and
     * its neighbours lean away from it, less the further away, each on its own
     * springs. At rest, port 08 is caught half out, bright. The slider is the
     * falloff radius, in ports.
     *
     * The pattern: a continuous field over discrete parts, as Keyboard's: a spring
     * per number, a falloff by distance, a hit test on a fixed plane at rest.
     */

    const NC = 12, PITCH = 15, GAP = 8, EAR = 15, MAR = 5, H = 44, T = 2.6, DEEP = 18;
    const X0 = EAR + MAR, W = 2 * X0 + NC * PITCH + GAP, ZT = 30, ZB = 12.5;
    const JW = 5, JH = 4.2, NW = 1.9, NH = 1.7, JD = 2.4;
    const PW = 4.3, PH = 3.5, PL = 4, BL = 5, CR = 1.8, OUT = 6, LEAN = 10, LZ = 7, LIFT = 9;
    const EMPTY = [2, 10, 18], REST = 7, HIT_Y = 2.5;
    /** Small irregularities, so no two cables at rest hang alike: [x, z] at the tip. */
    const JIT = (p        )       => [((p * 7) % 5) - 2, ((p * 11) % 7) - 3];

    /** The share of the full lean a cable takes, d ports from the one lifted: all of it next door, none past R more. */
    const falloff = (d        , R        ) => (d === 0 ? 0 : clamp(1 - (d - 1) / R, 0, 1));







    /** A closed tube round a run of screen points, w wide each side, with a round cap at each end. */
    function tube(q                 , w        )         {
      const n = q.length, L         = [], Rt         = [], nrm         = [];
      for (let i = 0; i < n; i++) {
        const a = q[Math.max(0, i - 1)], b = q[Math.min(n - 1, i + 1)], l = Math.hypot(b[0] - a[0], b[1] - a[1]) || 1;
        const t       = [(b[0] - a[0]) / l, (b[1] - a[1]) / l];
        nrm.push(t);
        L.push([q[i][0] - t[1] * w, q[i][1] + t[0] * w]); Rt.push([q[i][0] + t[1] * w, q[i][1] - t[0] * w]);
      }
      const cap = (c      , t      , s        )         => {
        const out         = [];
        for (let k = 1; k < 6; k++) {
          const th = (k / 6) * Math.PI, cs = Math.cos(th), sn = Math.sin(th);
          out.push([c[0] + s * w * (-t[1] * cs + t[0] * sn), c[1] + s * w * (t[0] * cs + t[1] * sn)]);
        }
        return out;
      };
      return poly([...L, ...cap(q[n - 1], nrm[n - 1], 1), ...Rt.reverse(), ...cap(q[0], nrm[0], -1)]);
    }

    const mount              = ({ stage, svg, read }, value) => {
      const bag = disposer();
      const S = 1.5, C = Cam(45, 0.5, S);
      const tipZ = ZT + 27 + LIFT + LZ, lowZ = ZB - 26 - LZ;
      fit(C, [[0, -DEEP, H], [W, -DEEP, H], [0, 0, 0], [W, 0, 0], [X0, 34, tipZ], [W - X0, 34, lowZ], [X0, 34, lowZ]], 200, 166);
      const P = proj(C), front = facing(C);
      let R = value, over = -1, lit              = null;

      /** A ring standing in the x–z plane, projected at depth y; `seen` keeps the sides of a solid along y that face the camera. */
      const at = (ring      , cx        , y        , cz        ) => ring.map((q) => P(cx + q.u, y, cz + q.v));
      const seen = (q        ) => 0.612 * q.nu + 0.5 * q.nv > 0;
      const slab = (ring      , inner      , cx        , cz        , y0        , y1        ) => ({
        sil: poly(hull(at(ring, cx, y0, cz).concat(at(ring, cx, y1, cz)))),
        crease: open(at(run(inner, seen), cx, y1, cz)),
      });

      const g = mk("g", {}, svg);
      // the body behind the plate, narrower than it, so the plate's ends stand out as ears
      const [br, bi] = rings(EAR + 2, -DEEP, W - EAR - 2, -T, 3, 1.6);
      put(solid(g), prism(P, front, br, bi, 3, H - 3));
      put(solid(g), slab(rrect(0, 0, W, H, 3, 4), rrect(0.7, 0.7, W - 0.7, H - 0.7, 2.3, 4), 0, 0, -T, 0));
      const flat = (ring      )         => ring.map((q) => [q.u, q.v]);
      const face = (pts        , cls        ) => mk("path", { d: poly(pts.map(([x, z]) => P(x, 0, z))), class: cls }, g);
      for (const ex of [EAR / 2 + 1, W - EAR / 2 - 1]) for (const ez of [8, H - 8]) {
        face(flat(rrect(ex - 3.4, ez - 1.5, ex + 3.4, ez + 1.5, 1.5, 3)), "nf");
      }

      const ports = []          ;
      for (let p = 0; p < 2 * NC; p++) {
        const r = p < NC ? 0 : 1, c = p % NC;
        ports.push({ p, r, c, cx: X0 + (c + 0.5) * PITCH + (c >= 6 ? GAP : 0), cz: r ? ZB : ZT, full: !EMPTY.includes(p) }        );
      }
      // two modules, six by two
      for (const m of [0, 6]) {
        const a = ports[m].cx - PITCH / 2 + 1, b = ports[m + 5].cx + PITCH / 2 - 1;
        face(flat(rrect(a, ZB - JH - 3, b, ZT + JH + NH + 2.6, 2.4, 4)), "lo nf");
      }
      // each jack: its opening with the latch's notch, and the far wall seen through it
      const jack = fillet([[-JW, -JH], [JW, -JH], [JW, JH], [NW, JH], [NW, JH + NH], [-NW, JH + NH], [-NW, JH], [-JW, JH]], [1, 1, 1, 0.4, 0.5, 0.5, 0.4, 1]);
      for (const pt of ports) {
        const { cx, cz } = pt, d = JD;
        pt.jack = face(jack.map(([u, v])       => [cx + u, cz + v]), "nf");
        mk("path", { d: open(([[-JW + d, JH], [-JW + d, -JH + 0.816 * d], [JW, -JH + 0.816 * d]]          ).map(([u, v]) => P(cx + u, 0, cz + v))), class: "lo nf" }, g);
      }

      // plugs and boots, then the cables in front of them, each painted left to right
      const plugG = mk("g", {}, g), cabG = mk("g", {}, g);
      const plug = rrect(-PW, -PH, PW, PH, 1.2, 3), plugIn = rrect(-PW + 0.7, -PH + 0.7, PW - 0.7, PH - 0.7, 0.6, 3);
      const bootA = rrect(-3.7, -3, 3.7, 3, 1.6, 3), bootB = rrect(-2.4, -2.4, 2.4, 2.4, 2.3, 3);
      const order = ports.slice().sort((a, b) => a.c - b.c || a.r - b.r);
      for (const pt of order) {
        pt.pull = spring(0, { eps: 0.002 }); pt.lx = spring(0, { eps: 0.01 }); pt.lz = spring(0, { eps: 0.01 });
        if (!pt.full) continue;
        pt.plug = solid(plugG); pt.latch = mk("path", { class: "lo nf" }, pt.plug.g); pt.boot = solid(plugG);
        pt.cable = mk("path", { class: "sil" }, cabG);
        pt.drawn = "";
      }

      function drawPort(pt      ) {
        const k = pt.pull.x, lx = pt.lx.x, lz = pt.lz.x, key = [k, lx, lz].map((v) => v.toFixed(3)).join();
        if (key === pt.drawn) return;
        pt.drawn = key;
        const { cx, cz, r, p } = pt, y1 = PL + OUT * k, y2 = y1 + BL, up = r ? -1 : 1, [jx, jz] = JIT(p);
        put(pt.plug, slab(plug, plugIn, cx, cz, 0, y1));
        pt.latch.setAttribute("d", seg(P(cx, 0.6, cz + PH), P(cx, y1 - 0.8, cz + PH)));
        put(pt.boot, { sil: poly(hull(at(bootA, cx, y1, cz).concat(at(bootB, cx, y2, cz)))), crease: "" });
        // the cable: out of the boot along y, then bending up (top row) or down (bottom row)
        // a rising cable leaves its boot upwards, so it climbs between two jacks; a hanging one sags out first
        const out = r ? 6 : 2, lean = r ? 2 : 3;
        const p0       = [cx, y2 - 1.5, cz], p1       = r ? [cx + 0.5, y2 + out + 4 * k, cz] : [cx, y2 + 1 + 2 * k, cz + 6];
        const p3       = [cx + lean + jx + lx, y2 + out + 1 + LIFT * k, cz + up * (24 + jz) + lz + LIFT * k], p2       = [p3[0] - 0.6, p3[1] - 1, p3[2] - up * 12];
        const q         = [];
        for (let i = 0; i <= 16; i++) {
          const s = i / 16, a = (1 - s) ** 3, b = 3 * (1 - s) ** 2 * s, c = 3 * (1 - s) * s * s, d = s ** 3;
          q.push(P(...([0, 1, 2].map((j) => a * p0[j] + b * p1[j] + c * p2[j] + d * p3[j])        )));
        }
        pt.cable.setAttribute("d", tube(q, CR * S));
      }

      /** Each port's targets, from the port lifted, a radius in ports and a share of the full answer. */
      function aim(a        , radius        , depth        ) {
        const A = ports[a];
        for (const pt of ports) {
          const dx = pt.c - A.c, dr = pt.r - A.r, d = Math.hypot(dx, dr), f = falloff(d, radius) * depth;
          pt.pull.t = pt === A ? depth : 0;
          pt.lx.t = d ? clamp((dx / d) * f * LEAN, -LEAN, LEAN) : 0;
          pt.lz.t = d ? clamp((-dr / d) * f * LZ, -LZ, LZ) : 0;
        }
      }
      function light(pt      ) {
        if (pt === lit) return;
        const mark = (q      , on         ) => (q.full ? [q.plug.sil, q.boot.sil, q.cable] : [q.jack]).forEach((el) => el.classList.toggle("hi", on));
        if (lit) mark(lit, false);
        lit = pt;
        mark(pt, true);
      }
      aim(REST, 1.6, 0.55);
      for (const pt of ports) for (const s of [pt.pull, pt.lx, pt.lz]) s.x = s.t;
      light(ports[REST]);
      read.textContent = "rest";

      const B = register(stage, (dt) => {
        let m = false;
        for (const pt of ports) {
          for (const s of [pt.pull, pt.lx, pt.lz]) if (stepS(s, dt)) m = true;
          if (pt.full) drawPort(pt);
        }
        return m;
      });
      bag.add(B.unregister);

      // The plane of the plugs at rest, y = HIT_Y: it never moves, so a cable lifting cannot change the pick.
      const o = P(0, HIT_Y, 0), ux = P(1, HIT_Y, 0), uz = P(0, HIT_Y, 1);
      const ex = [ux[0] - o[0], ux[1] - o[1]], ez = [uz[0] - o[0], uz[1] - o[1]], det = ex[0] * ez[1] - ex[1] * ez[0];
      function hit([sx, sy]      ) {
        const qx = sx - o[0], qy = sy - o[1], x = (qx * ez[1] - qy * ez[0]) / det, z = (ex[0] * qy - ex[1] * qx) / det;
        if (x < X0 - 2 || x > W - X0 + 2 || z < ZB - JH - 6 || z > ZT + JH + 8) return -1;
        let best = -1, bd = Infinity;
        for (const pt of ports) {
          const dd = Math.abs(pt.cx - x) + (Math.abs(pt.cz - z) > (ZT - ZB) / 2 ? 1e3 : 0);
          if (dd < bd) { bd = dd; best = pt.p; }
        }
        return best;
      }

      function retarget() {
        if (over >= 0) { aim(over, R, 1); light(ports[over]); read.textContent = "port " + String(over + 1).padStart(2, "0"); }
        else { aim(REST, 1.6, 0.55); light(ports[REST]); read.textContent = "rest"; }
        B.wake();
      }

      bag.add(pointer(stage, {
        move: (p) => { const h = hit(p); if (h !== over) { over = h; retarget(); } },
        leave: () => { over = -1; retarget(); },
      }));
      bag.add(() => svg.replaceChildren());

      return {
        set: (v) => { R = v; if (over >= 0) retarget(); },
        destroy: bag.dispose,
      };
    };
    return { mount, label: "A patch panel of twenty-four ports: the cable under the pointer lifts, and its neighbours lean away, less the further away.", rest: "rest", range: [1, 2.5, 5] };
  })();

  const phosphor = (() => {
    /**
     * Phosphor (Fig 9.4): a 7 × 7 dot matrix you can paint on. Each dot holds an
     * intensity that decays with persistence τ (the slider, in ms). At idle a
     * loop of frames, seven row bytes each, excites the dots; the pointer
     * excites them instead, and the loop fades back in 1.2s after it leaves.
     * Ambient: the tick always asks for another frame, so it runs whenever the
     * stage is on screen and the shared observer puts it to sleep when it isn't.
     * Ported from the study's `#phosphor` (design/lab-hairline/cartilha-v2.html).
     */

    const N = 7, PITCH = 10, M = 8, EXT = M * 2 + PITCH * (N - 1), T = 5, R = 2.5, DROP = 15, BT = 4, BO = 7;
    /** The loop, seven row bytes per frame (MSB = left column): a ripple out from the centre, a pause, a diagonal sweep, a pause. */
    const LOOP = [
      [0, 0, 0, 8, 0, 0, 0], [0, 0, 8, 20, 8, 0, 0], [0, 28, 34, 34, 34, 28, 0], [28, 34, 65, 65, 65, 34, 28], [65, 0, 0, 0, 0, 0, 65],
      [0, 0, 0, 0, 0, 0, 0], [0, 0, 0, 0, 0, 0, 0],
      [64, 0, 0, 0, 0, 0, 0], [32, 64, 0, 0, 0, 0, 0], [16, 32, 64, 0, 0, 0, 0], [8, 16, 32, 64, 0, 0, 0], [4, 8, 16, 32, 64, 0, 0], [2, 4, 8, 16, 32, 64, 0], [1, 2, 4, 8, 16, 32, 64],
      [0, 1, 2, 4, 8, 16, 32], [0, 0, 1, 2, 4, 8, 16], [0, 0, 0, 1, 2, 4, 8], [0, 0, 0, 0, 1, 2, 4], [0, 0, 0, 0, 0, 1, 2], [0, 0, 0, 0, 0, 0, 1],
      [0, 0, 0, 0, 0, 0, 0], [0, 0, 0, 0, 0, 0, 0],
    ];
    const FRAME_MS = 110;
    /** The loop waits this long after the pointer leaves, then fades its gain in over RAMP. */
    const RESUME = 1200, RAMP = 400;
    /** A painted dot at full, its four neighbours at this share. */
    const SPLASH                                      = [[0, 0, 1], [1, 0, 0.45], [-1, 0, 0.45], [0, 1, 0.45], [0, -1, 0.45]];

    const lit = (f        , r        , c        ) => (LOOP[f][r] >> (N - 1 - c)) & 1;

    const mount              = ({ stage, svg, read }, value) => {
      const bag = disposer();
      let tau = value, clock = 0, lastFrame = -1, leftAt = -1e9, painting = false;
      let prev              = null;

      const C = Cam(45, 0.5, 2.12), ZB = -DROP - BT;
      fit(C, [[-BO, -BO, ZB], [EXT + BO, EXT + BO, ZB - 6], [EXT + BO, -BO, ZB], [-BO, EXT + BO, ZB], [0, 0, T]], 200, 160);
      const P = proj(C), front = facing(C);
      const g = mk("g", {}, svg);

      // base plate, its reflection, then the dashed drops, then the tile over them
      const [br, bi] = rings(-BO, -BO, EXT + BO, EXT + BO, 11, 1.8);
      reflect(svg, g, P, front, br, ZB, 12);
      put(solid(g), prism(P, front, br, bi, ZB, -DROP));
      const [tr, ti] = rings(0, 0, EXT, EXT, 7, 1.3);
      mk("path", { d: extremes(P, tr).map((q) => seg(P(q.u, q.v, 0), P(q.u, q.v, -DROP))).join(""), class: "nf dash" }, g);
      put(solid(g), prism(P, front, tr, ti, 0, T));
      mk("path", { d: poly(ringAt(P, rrect(3.5, 3.5, EXT - 3.5, EXT - 3.5, 4.5, 5), T)), class: "nf lo" }, g);

      const I = new Float32Array(N * N);
      const dots                      = [];
      for (let r = 0; r < N; r++) for (let c = 0; c < N; c++) {
        const d = flatDot(g, C, R, "dot");
        place(d, P(M + c * PITCH, M + r * PITCH, T));
        dots.push(d);
      }

      /** Lights the cell nearest a point on the tile, and its neighbours less, never dimming what is brighter. */
      function excite(x        , y        , amt        ) {
        const c = Math.round((x - M) / PITCH), r = Math.round((y - M) / PITCH);
        for (const [dr, dc, k] of SPLASH) {
          const rr = r + dr, cc = c + dc;
          if (rr < 0 || rr >= N || cc < 0 || cc >= N) continue;
          I[rr * N + cc] = Math.max(I[rr * N + cc], amt * k);
        }
      }

      const B = register(stage, (dt, now) => {
        if (reducedMotion() && !painting) {
          // no loop: settle on a composed still, the ripple's widest ring
          for (let i = 0; i < N * N; i++) I[i] = Math.max(I[i] * Math.exp((-dt * 1000) / tau), lit(3, Math.floor(i / N), i % N) * 0.8);
        } else {
          const decay = Math.exp((-dt * 1000) / tau);
          for (let i = 0; i < N * N; i++) I[i] *= decay;
          const gain = painting ? 0 : clamp((now - leftAt - RESUME) / RAMP, 0, 1);
          if (gain > 0) {
            clock += dt * 1000;
            const f = Math.floor(clock / FRAME_MS) % LOOP.length;
            if (f !== lastFrame) {
              lastFrame = f;
              for (let r = 0; r < N; r++) for (let c = 0; c < N; c++) if (lit(f, r, c)) I[r * N + c] = Math.max(I[r * N + c], gain);
            }
            read.textContent = `loop · ${String(f + 1).padStart(2, "0")}/${LOOP.length}`;
          } else read.textContent = painting ? "paint" : "afterglow";
        }
        for (let i = 0; i < N * N; i++) dots[i].setAttribute("opacity", (0.14 + 0.86 * clamp(I[i], 0, 1)).toFixed(3));
        return true;
      });
      bag.add(B.unregister);

      bag.add(pointer(stage, {
        move: (p) => {
          painting = true;
          const q = unproj(C, p[0], p[1], T);
          // fill in between moves, so a fast stroke leaves a line rather than dots
          if (prev) {
            const n = Math.ceil(Math.hypot(q[0] - prev[0], q[1] - prev[1]) / 3);
            for (let k = 1; k <= n; k++) excite(lerp(prev[0], q[0], k / n), lerp(prev[1], q[1], k / n), 1);
          } else excite(q[0], q[1], 1);
          prev = q;
          B.wake();
        },
        // the resume is a timestamp the tick reads, not a timer, so re-entering or tearing down has nothing to cancel
        leave: () => { painting = false; prev = null; leftAt = performance.now(); clock = 0; lastFrame = -1; B.wake(); },
      }));

      bag.add(() => svg.replaceChildren());
      return { set: (v) => { tau = v; }, destroy: bag.dispose };
    };
    return { mount, label: "A seven by seven dot matrix on a floating tile that plays a loop, and fades like phosphor where you paint it.", rest: "loop", range: [150, 520, 1500] };
  })();

  window.HairlineStock = { drawer, terminal, plug, riffle, loupe, sieve, elevator, slow, cabinet, dish, router, patch, phosphor };
})();
