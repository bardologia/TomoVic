"use strict";

class SharedCharts {
  static FAMILY_COLORS = { amp: "#6f9bff", mu: "#2dd4bf", sigma: "#fbbf24" };
  static FAMILY_LABELS = { amp: "amplitude", mu: "mean height", sigma: "width" };
  static SERIES_COLORS = { pred: "#6f9bff", gt: "#eef2f5", raw: "#9ca3af", perturbed: "#f87171" };

  static gradientGrid(container, data, selectedChannel) {
    const cellHtml = (family, label, cell, share, head) => {
      const cap = head
        ? `<figcaption class="ms-cellhead"><i style="background:${SharedCharts.FAMILY_COLORS[family]}"></i>${family} &middot; ${(share * 100).toFixed(1)}%</figcaption>`
        : "";
      if (!cell) {
        return `<figure class="ms-cell">${cap}<div class="ms-cell--dead"><span>0</span></div></figure>`;
      }
      const img = `
        <span class="ms-cell__frame">
          <img src="data:image/png;base64,${cell}" alt="${SharedCharts.esc(`${family} sensitivity to ${label}`)}" />
          ${SharedCharts.dot(data.center, data.patch)}
        </span>`;
      return head
        ? `<figure class="ms-cell">${cap}${img}</figure>`
        : `<figure class="ms-cell">${img}<figcaption>${(share * 100).toFixed(1)}%</figcaption></figure>`;
    };

    if (selectedChannel >= 0) {
      const label = data.channels[selectedChannel];

      container.className = "ms-gridone";
      container.style.gridTemplateColumns = "";
      container.innerHTML = data.families.map((f) => cellHtml(f.family, label, f.cells[selectedChannel], f.shares[selectedChannel], true)).join("");
      return;
    }

    container.className = "ms-grid";
    container.style.gridTemplateColumns = `92px repeat(${data.channels.length}, minmax(58px, 150px))`;

    const cells = [`<span class="ms-grid__corner"></span>`];
    data.channels.forEach((label) => cells.push(`<span class="ms-grid__col">${SharedCharts.esc(label)}</span>`));

    data.families.forEach((f) => {
      cells.push(`<span class="ms-grid__row"><i style="background:${SharedCharts.FAMILY_COLORS[f.family]}"></i>${f.family}</span>`);
      data.channels.forEach((label, index) => cells.push(cellHtml(f.family, label, f.cells[index], f.shares[index], false)));
    });

    container.innerHTML = cells.join("");
  }

  static familyBars(barsEl, legendEl, channels, families, deadNote) {
    const colors = SharedCharts.FAMILY_COLORS;
    const labels = SharedCharts.FAMILY_LABELS;
    const peak   = Math.max(1e-9, ...families.filter((f) => !f.dead).flatMap((f) => f.shares));

    barsEl.innerHTML = channels.map((label, index) => {
      const cols = families.map((f) => {
        const share  = f.shares[index];
        const height = f.dead ? 0 : Math.max(2, (share / peak) * 100);
        const title  = `${labels[f.family]} · ${label}: ${(share * 100).toFixed(1)}%`;
        return `<i style="height:${height.toFixed(1)}%;background:${colors[f.family]}" title="${SharedCharts.esc(title)}"></i>`;
      }).join("");
      return `<div class="ms-bars__group"><div class="ms-bars__cols">${cols}</div><span class="ms-bars__label">${SharedCharts.esc(label)}</span></div>`;
    }).join("");

    legendEl.innerHTML = families.map((f) =>
      `<span><i style="background:${colors[f.family]}"></i>${f.family} — ${labels[f.family]}${f.dead ? ` (${deadNote})` : ""}</span>`
    ).join("");
  }

  static ablationRows(container, channels, basePower, extras) {
    const peak = Math.max(1e-12, ...channels.map((c) => c.delta_mse));

    container.innerHTML = channels.map((c) => {
      const width = Math.max(1.5, (c.delta_mse / peak) * 100).toFixed(1);
      const rel   = basePower > 0 ? ` &middot; ${((c.delta_mse / basePower) * 100).toFixed(2)}% of power` : "";
      const extra = extras ? extras(c) : "";
      return `
        <div class="ms-abl__row">
          <span class="ms-abl__label" title="${SharedCharts.esc(c.label)}">${SharedCharts.esc(c.label)}</span>
          <span class="ms-abl__bar"><span class="ms-abl__track"><i style="width:${width}%"></i></span><em>curve MSE ${c.delta_mse.toExponential(2)}${rel}${extra}</em></span>
        </div>`;
    }).join("");
  }

  static vitalsTable(summaryEl, tableEl, out, opts = {}) {
    const s       = out.summary;
    const flagged = s.flagged ? `<b>${s.flagged} flagged</b> (nonfinite, mostly zero, or &gt;25% dead channels)` : "none flagged";
    summaryEl.innerHTML = `${s.n_layers} live layers &middot; ${s.total_params.toLocaleString("en-US")} parameters &middot; ${flagged}`;

    const head = `<thead><tr>
      <th>#</th><th class="ms-slots__key">LAYER</th><th class="ms-vitals__type">TYPE</th><th>OUT</th><th>PARAMS</th>
      <th>ZERO %</th><th>DEAD CH</th><th>EFF CH %</th><th>MAX |ACT|</th><th class="ms-vitals__flags">FLAGS</th>
    </tr></thead>`;

    const rows = out.entries.map((e, index) => {
      const dead    = e.dead === null ? "&ndash;" : `${e.dead}/${e.channels}`;
      const eff     = e.eff_frac === null ? "&ndash;" : (e.eff_frac * 100).toFixed(0);
      const classes = [e.flags.length ? "is-flagged" : "", e.name === opts.currentLayer ? "is-current" : ""].filter(Boolean).join(" ");
      return `
        <tr class="${classes}" data-layer="${SharedCharts.esc(e.name)}">
          <td>${index + 1}</td>
          <td class="ms-slots__key" title="${SharedCharts.esc(e.name)}">${SharedCharts.esc(e.name)}</td>
          <td class="ms-vitals__type">${SharedCharts.esc(e.type)}</td>
          <td>${(e.shape || []).join("&times;")}</td>
          <td>${e.params.toLocaleString("en-US")}</td>
          <td>${(e.zero_frac * 100).toFixed(1)}</td>
          <td>${dead}</td>
          <td>${eff}</td>
          <td>${SharedCharts.fmt(e.max_abs)}</td>
          <td class="ms-vitals__flags">${SharedCharts.esc(e.flags.join(", "))}</td>
        </tr>`;
    });

    tableEl.innerHTML = `${head}<tbody>${rows.join("")}</tbody>`;
    tableEl.classList.toggle("is-static", !opts.onPick);

    if (!opts.onPick) return;
    tableEl.querySelectorAll("tr[data-layer]").forEach((row) => {
      row.addEventListener("click", () => opts.onPick(row.dataset.layer));
    });
  }

  static lineChart(canvas, xAxis, series, opts = {}) {
    if (!canvas.dataset.chartW) {
      canvas.dataset.chartW = canvas.width;
      canvas.dataset.chartH = canvas.height;
    }

    const baseW = parseInt(canvas.dataset.chartW, 10);
    const baseH = parseInt(canvas.dataset.chartH, 10);
    const dpr   = window.devicePixelRatio || 1;

    canvas.style.width  = "100%";
    canvas.style.height = `${baseH}px`;

    const W = canvas.clientWidth || baseW;
    const H = baseH;

    canvas.width  = Math.round(W * dpr);
    canvas.height = Math.round(H * dpr);

    const ctx = canvas.getContext("2d");
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, W, H);

    const all = series.flatMap((s) => s.values).filter((v) => Number.isFinite(v));
    if (!all.length) return;

    const top  = all.reduce((m, v) => (v > m ? v : m), -Infinity);
    const lo   = all.reduce((m, v) => (v < m ? v : m), 0);
    const span = top - lo;
    const hi   = span > 0 ? top + 0.05 * span : lo + 1;
    const x0 = xAxis[0];
    const x1 = xAxis[xAxis.length - 1];

    const pad = { l: 52, r: 12, t: 10, b: 24 };
    const px  = (x) => pad.l + ((x - x0) / (x1 - x0)) * (W - pad.l - pad.r);
    const py  = (v) => H - pad.b - ((v - lo) / (hi - lo)) * (H - pad.t - pad.b);

    ctx.font = "600 10px JetBrains Mono, monospace";

    for (let tick = 0; tick <= 4; tick += 1) {
      const v = lo + ((hi - lo) * tick) / 4;
      const y = py(v);

      ctx.strokeStyle = "rgba(220, 235, 245, 0.1)";
      ctx.lineWidth   = 1;
      ctx.beginPath();
      ctx.moveTo(pad.l, y);
      ctx.lineTo(W - pad.r, y);
      ctx.stroke();

      ctx.fillStyle = "rgba(214, 223, 228, 0.98)";
      ctx.textAlign = "right";
      ctx.fillText(SharedCharts.fmt(v), pad.l - 6, y + 3);
    }

    const xUnit = opts.xUnit === undefined ? " m" : (opts.xUnit ? ` ${opts.xUnit}` : "");

    [[x0, "left"], [(x0 + x1) / 2, "center"], [x1, "right"]].forEach(([x, align]) => {
      ctx.fillStyle = "rgba(214, 223, 228, 0.98)";
      ctx.textAlign = align;
      ctx.fillText(`${SharedCharts.fmt(x)}${xUnit}`, px(x), H - 8);
    });

    ctx.strokeStyle = "rgba(139, 155, 168, 0.9)";
    ctx.lineWidth   = 1;
    ctx.beginPath();
    ctx.moveTo(pad.l, pad.t);
    ctx.lineTo(pad.l, H - pad.b);
    ctx.lineTo(W - pad.r, H - pad.b);
    ctx.stroke();

    series.forEach((s) => {
      ctx.strokeStyle = s.color;
      ctx.lineWidth   = s.width;
      ctx.lineJoin    = "round";
      ctx.beginPath();
      let pen = false;
      s.values.forEach((v, i) => {
        if (!Number.isFinite(v)) {
          pen = false;
          return;
        }
        const x = px(xAxis[i]);
        const y = py(v);
        if (pen) ctx.lineTo(x, y); else ctx.moveTo(x, y);
        pen = true;
      });
      ctx.stroke();
    });

    if (Number.isFinite(opts.marker) && opts.marker >= Math.min(x0, x1) && opts.marker <= Math.max(x0, x1)) {
      ctx.strokeStyle = "#fb7185";
      ctx.lineWidth   = 1;
      ctx.setLineDash([4, 3]);
      ctx.beginPath();
      ctx.moveTo(px(opts.marker), pad.t);
      ctx.lineTo(px(opts.marker), H - pad.b);
      ctx.stroke();
      ctx.setLineDash([]);
    }

    ctx.textAlign = "left";
    const entryWidths = series.map((s) => 16 + ctx.measureText(s.label).width + 14);
    let legendX = W - pad.r - entryWidths.reduce((acc, w) => acc + w, 0);
    const legendY = pad.t + 8;

    series.forEach((s, index) => {
      ctx.strokeStyle = s.color;
      ctx.lineWidth   = 2;
      ctx.beginPath();
      ctx.moveTo(legendX, legendY);
      ctx.lineTo(legendX + 10, legendY);
      ctx.stroke();

      ctx.fillStyle = "rgba(232, 238, 241, 0.98)";
      ctx.fillText(s.label, legendX + 14, legendY + 3);
      legendX += entryWidths[index];
    });
  }

  static esc(text) {
    return String(text == null ? "" : text).replace(/[&<>"']/g, (ch) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[ch]));
  }

  static fmt(v) {
    if (v === 0) return "0";
    const abs = Math.abs(v);
    return abs >= 1e4 || abs < 1e-2 ? v.toExponential(1) : Number(v.toPrecision(3)).toString();
  }

  static dot(center, patch) {
    const left = (((center[1] + 0.5) / patch[1]) * 100).toFixed(1);
    const top  = (((center[0] + 0.5) / patch[0]) * 100).toFixed(1);
    return `<i class="ms-cell__dot" style="left:${left}%;top:${top}%"></i>`;
  }

  static chip(label, active, onPick) {
    const chip = document.createElement("button");
    chip.type = "button";
    chip.className = "ms-chipbtn" + (active ? " is-active" : "");
    chip.textContent = label;
    chip.addEventListener("click", onPick);
    return chip;
  }
}

class TimeStrip {
  static AXIS_H = 18;
  static GAP_BUCKETS = 2.5;

  static points(samples, key) {
    return samples.map((sample) => ({ t: sample.t, v: sample[key] }));
  }

  static ticks(view, plotW) {
    const start = view.now - view.window_s;
    const ticks = [];

    if (view.window_s > 86400) {
      const cursor = new Date(start * 1000);
      cursor.setHours(24, 0, 0, 0);
      const days = [];
      while (cursor.getTime() / 1000 <= view.now) {
        days.push(cursor.getTime() / 1000);
        cursor.setDate(cursor.getDate() + 1);
      }
      const every = Math.max(1, Math.ceil((days.length * 42) / Math.max(1, plotW)));
      days.forEach((t, i) => {
        const date = new Date(t * 1000);
        ticks.push({ t, label: i % every === 0 ? `${String(date.getDate()).padStart(2, "0")}.${String(date.getMonth() + 1).padStart(2, "0")}` : null });
      });
    } else {
      const step = view.window_s > 7200 ? 3 * 3600 : 900;
      for (let t = Math.ceil(start / step) * step; t <= view.now; t += step) {
        const date = new Date(t * 1000);
        ticks.push({ t, label: `${String(date.getHours()).padStart(2, "0")}:${String(date.getMinutes()).padStart(2, "0")}` });
      }
    }
    return ticks;
  }

  static niceMax(value) {
    const exp  = Math.pow(10, Math.floor(Math.log10(value)));
    const step = [1, 2, 2.5, 5, 10].find((m) => m * exp >= value);
    return step * exp;
  }

  static format(value) {
    if (value >= 100) return String(Math.round(value));
    if (value >= 10) return value.toFixed(0);
    if (value >= 1) return value.toFixed(1).replace(/\.0$/, "");
    return value.toFixed(2).replace(/0+$/, "").replace(/\.$/, "");
  }

  static draw(canvas, view, tracks, opts = {}) {
    canvas._strip = { view, tracks, opts };
    TimeStrip._hoverOnce(canvas);

    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    const w = canvas.clientWidth;
    const h = canvas.clientHeight;
    if (!w || !h) return;
    if (canvas.width !== Math.round(w * dpr) || canvas.height !== Math.round(h * dpr)) {
      canvas.width = Math.round(w * dpr);
      canvas.height = Math.round(h * dpr);
    }

    const ctx = canvas.getContext("2d");
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, w, h);

    const values = tracks.flatMap((track) => track.points.map((point) => point.v)).filter((v) => Number.isFinite(v));
    const yMax = Number.isFinite(opts.yMax) && opts.yMax > 0 ? opts.yMax : TimeStrip.niceMax(Math.max(1, ...values));
    const unit = opts.unit || "";
    const gapS = Number.isFinite(opts.gapS) ? opts.gapS : (view.bucket_s || 300) * TimeStrip.GAP_BUCKETS;

    ctx.font = "600 10px ui-monospace, SFMono-Regular, monospace";
    const ticksY = [0, yMax / 4, yMax / 2, (3 * yMax) / 4, yMax];
    const gutter = Math.ceil(Math.max(...ticksY.map((v) => ctx.measureText(TimeStrip.format(v)).width))) + 8;

    const left  = gutter;
    const top   = 20;
    const plotH = h - TimeStrip.AXIS_H - top;
    const start = view.now - view.window_s;
    const px = (t) => left + ((t - start) / view.window_s) * (w - left - 4);
    const py = (v) => top + plotH - Math.min(1, Math.max(0, v / yMax)) * plotH;

    ctx.fillStyle = "rgba(6, 10, 14, 0.55)";
    ctx.fillRect(left, top, w - left - 2, plotH);

    ctx.textBaseline = "middle";
    ctx.textAlign = "right";
    ticksY.forEach((v, i) => {
      const y = Math.round(py(v)) + 0.5;
      ctx.strokeStyle = i === 0 ? "rgba(220, 235, 245, 0.22)" : "rgba(220, 235, 245, 0.08)";
      ctx.setLineDash(i === 0 ? [] : [2, 4]);
      ctx.beginPath();
      ctx.moveTo(left, y);
      ctx.lineTo(w - 2, y);
      ctx.stroke();
      if (i % 2 === 1) return;
      ctx.fillStyle = "rgba(220, 235, 245, 0.86)";
      ctx.fillText(TimeStrip.format(v), left - 5, y);
    });
    ctx.setLineDash([]);
    if (unit) {
      ctx.textAlign = "left";
      ctx.textBaseline = "top";
      ctx.fillStyle = "rgba(220, 235, 245, 0.82)";
      ctx.fillText(unit.trim(), 0, 0);
    }

    ctx.textBaseline = "top";
    TimeStrip.ticks(view, w - left).forEach(({ t, label }) => {
      const x = Math.round(px(t)) + 0.5;
      ctx.strokeStyle = "rgba(220, 235, 245, 0.07)";
      ctx.beginPath();
      ctx.moveTo(x, top);
      ctx.lineTo(x, top + plotH);
      ctx.stroke();
      if (!label) return;
      ctx.fillStyle = "rgba(220, 235, 245, 0.85)";
      ctx.textAlign = x > w - 24 ? "right" : "center";
      ctx.fillText(label, Math.min(x, w - 1), top + plotH + 4);
    });

    ctx.save();
    ctx.beginPath();
    ctx.rect(left, top - 2, w - left, plotH + 4);
    ctx.clip();
    tracks.forEach((track) => TimeStrip.trace(ctx, track, px, py, top + plotH, gapS));
    ctx.restore();

    if (canvas._cursor != null && values.length) TimeStrip._readout(ctx, canvas._cursor, view, tracks, unit, { left, top, plotH, w, px, start });
  }

  static _hoverOnce(canvas) {
    if (canvas._hoverWired) return;
    canvas._hoverWired = true;
    const redraw = () => {
      const strip = canvas._strip;
      TimeStrip.draw(canvas, strip.view, strip.tracks, strip.opts);
    };
    canvas.addEventListener("mousemove", (event) => {
      canvas._cursor = event.clientX - canvas.getBoundingClientRect().left;
      redraw();
    });
    canvas.addEventListener("mouseleave", () => {
      canvas._cursor = null;
      redraw();
    });
  }

  static _readout(ctx, cursorX, view, tracks, unit, frame) {
    if (cursorX < frame.left) return;
    const t = frame.start + ((cursorX - frame.left) / (frame.w - frame.left - 4)) * view.window_s;
    const x = Math.round(frame.px(t)) + 0.5;

    ctx.strokeStyle = "rgba(220, 235, 245, 0.35)";
    ctx.beginPath();
    ctx.moveTo(x, frame.top);
    ctx.lineTo(x, frame.top + frame.plotH);
    ctx.stroke();

    const date  = new Date(t * 1000);
    const stamp = view.window_s > 86400 ? `${String(date.getDate()).padStart(2, "0")}.${String(date.getMonth() + 1).padStart(2, "0")} ${String(date.getHours()).padStart(2, "0")}:${String(date.getMinutes()).padStart(2, "0")}` : `${String(date.getHours()).padStart(2, "0")}:${String(date.getMinutes()).padStart(2, "0")}`;
    const lines = [{ text: stamp, color: "220, 235, 245" }];
    tracks.forEach((track) => {
      const near = TimeStrip._nearest(track.points, t, (view.bucket_s || 300) * TimeStrip.GAP_BUCKETS);
      lines.push({ text: `${track.label || ""} ${near == null ? "--" : TimeStrip.format(near) + unit}`.trim(), color: track.color });
    });

    const boxW = Math.max(...lines.map((line) => ctx.measureText(line.text).width)) + 12;
    const boxH = lines.length * 13 + 6;
    const boxX = x + 8 + boxW > frame.w ? x - 8 - boxW : x + 8;
    ctx.fillStyle = "rgba(6, 10, 14, 0.92)";
    ctx.fillRect(boxX, frame.top + 2, boxW, boxH);
    ctx.strokeStyle = "rgba(220, 235, 245, 0.18)";
    ctx.strokeRect(boxX + 0.5, frame.top + 2.5, boxW - 1, boxH - 1);
    ctx.textAlign = "left";
    ctx.textBaseline = "top";
    lines.forEach((line, i) => {
      ctx.fillStyle = `rgba(${line.color}, 0.95)`;
      ctx.fillText(line.text, boxX + 6, frame.top + 6 + i * 13);
    });
  }

  static _nearest(points, t, reach) {
    let best = null;
    let gap = Infinity;
    points.forEach((point) => {
      if (!Number.isFinite(point.v)) return;
      const d = Math.abs(point.t - t);
      if (d < gap) {
        gap = d;
        best = point.v;
      }
    });
    return gap <= reach ? best : null;
  }

  static segments(points, gapS) {
    const runs = [];
    let run = [];

    points.forEach((point) => {
      if (!Number.isFinite(point.v)) {
        run = [];
        return;
      }
      const last = run[run.length - 1];
      if (last && point.t - last.t > gapS) run = [];
      if (!run.length) runs.push(run);
      run.push(point);
    });
    return runs.filter((segment) => segment.length);
  }

  static trace(ctx, track, px, py, plotH, gapS) {
    const runs = TimeStrip.segments(track.points, gapS);
    const width = track.width || 1.3;

    runs.forEach((segment) => {
      if (track.fill && segment.length > 1) {
        ctx.beginPath();
        ctx.moveTo(px(segment[0].t), plotH);
        segment.forEach((point) => ctx.lineTo(px(point.t), py(point.v)));
        ctx.lineTo(px(segment[segment.length - 1].t), plotH);
        ctx.closePath();
        ctx.fillStyle = `rgba(${track.color}, 0.12)`;
        ctx.fill();
      }

      ctx.beginPath();
      segment.forEach((point, i) => {
        const x = px(point.t);
        const y = py(point.v);
        if (i === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
      });
      ctx.strokeStyle = `rgba(${track.color}, 0.9)`;
      ctx.lineWidth = width;
      ctx.stroke();
    });

    if (!track.dots) return;
    ctx.fillStyle = `rgba(${track.color}, 0.95)`;
    track.points.filter((point) => Number.isFinite(point.v)).forEach((point) => {
      ctx.beginPath();
      ctx.arc(px(point.t), py(point.v), 2, 0, Math.PI * 2);
      ctx.fill();
    });
  }
}

window.SharedCharts = SharedCharts;
window.TimeStrip = TimeStrip;
