"use strict";

class SharedCharts {
  static FAMILY_COLORS = { amp: "#1d4fd8", mu: "#0f766e", sigma: "#a16207" };
  static FAMILY_LABELS = { amp: "amplitude", mu: "mean height", sigma: "width" };
  static SERIES_COLORS = { pred: "#1d4fd8", gt: "#16191b", raw: "#9ca3af", perturbed: "#b91c1c" };

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

    ctx.font = "10px JetBrains Mono, monospace";

    for (let tick = 0; tick <= 4; tick += 1) {
      const v = lo + ((hi - lo) * tick) / 4;
      const y = py(v);

      ctx.strokeStyle = "rgba(22, 25, 27, 0.07)";
      ctx.lineWidth   = 1;
      ctx.beginPath();
      ctx.moveTo(pad.l, y);
      ctx.lineTo(W - pad.r, y);
      ctx.stroke();

      ctx.fillStyle = "rgba(125, 133, 139, 0.95)";
      ctx.textAlign = "right";
      ctx.fillText(SharedCharts.fmt(v), pad.l - 6, y + 3);
    }

    const xUnit = opts.xUnit === undefined ? " m" : (opts.xUnit ? ` ${opts.xUnit}` : "");

    [[x0, "left"], [(x0 + x1) / 2, "center"], [x1, "right"]].forEach(([x, align]) => {
      ctx.fillStyle = "rgba(125, 133, 139, 0.95)";
      ctx.textAlign = align;
      ctx.fillText(`${SharedCharts.fmt(x)}${xUnit}`, px(x), H - 8);
    });

    ctx.strokeStyle = "rgba(154, 161, 150, 0.8)";
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
      ctx.strokeStyle = "#e11d48";
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

      ctx.fillStyle = "rgba(63, 71, 76, 0.95)";
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

window.SharedCharts = SharedCharts;
