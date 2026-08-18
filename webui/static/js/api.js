"use strict";

class Api {

  static async probe(url) {
    try {
      const res  = await fetch(url);
      const data = await res.json().catch(() => null);
      return { status: res.status, data };
    } catch (e) {
      return { status: 0, data: null };
    }
  }

  static async get(url) {
    const probe = await Api.probe(url);
    if (!probe.status) return { error: "backend unreachable" };
    if (probe.status >= 500) return { error: `server ${probe.status}` };
    return probe.data || { error: `malformed response from ${url}` };
  }

  static async post(url, body) {
    try {
      const res = await fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body || {}),
      });
      return await res.json();
    } catch (e) {
      return { ok: false, error: "backend unreachable" };
    }
  }
}


class Format {

  static duration(seconds) {
    const total = Math.max(0, Math.round(seconds));
    const h = Math.floor(total / 3600);
    const m = Math.floor((total % 3600) / 60);
    if (h) return `${h}h ${String(m).padStart(2, "0")}m`;
    if (m) return `${m}m`;
    return `${total}s`;
  }

  static progressBits(p) {
    const done = p.done + p.failed;
    const pct = Math.round((100 * done) / p.total);
    const bits = [`${done}/${p.total}`, `${pct}%`];
    if (p.eta_s != null) bits.push(`ETA ${Format.duration(p.eta_s)}`, `≈ ${p.finish_at.slice(11, 16)}`);
    else if (done < p.total) bits.push("estimating ETA");
    if (p.failed) bits.push(`${p.failed} FAILED`);
    return bits;
  }
}


class Toast {
  static HOLD_MS = 3200;

  static show(message, kind) {
    const el = document.getElementById("toast");
    el.textContent = message;
    el.className = "toast is-show" + (kind ? ` is-${kind}` : "");

    clearTimeout(Toast.timer);
    Toast.timer = setTimeout(() => {
      el.className = "toast";
    }, Toast.HOLD_MS);
  }
}

window.Api    = Api;
window.Format = Format;
window.Toast  = Toast;
