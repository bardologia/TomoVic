"use strict";

class Api {

  static async probe(url, timeoutMs = 0, signal = null) {
    const controller = timeoutMs > 0 ? new AbortController() : null;
    const timer = controller ? setTimeout(() => controller.abort(), timeoutMs) : null;
    try {
      const effectiveSignal = signal || (controller ? controller.signal : null);
      const res  = await fetch(url, effectiveSignal ? { signal: effectiveSignal } : {});
      const data = await res.json().catch(() => null);
      return { status: res.status, data };
    } catch (e) {
      return { status: 0, data: null, timedOut: Boolean(controller && controller.signal.aborted) };
    } finally {
      if (timer) clearTimeout(timer);
    }
  }

  static async get(url, timeoutMs = 0, signal = null) {
    const probe = await Api.probe(url, timeoutMs, signal);
    if (probe.timedOut) return { error: `no answer from the console within ${Math.round(timeoutMs / 1000)} s` };
    if (!probe.status) return { error: "backend unreachable" };
    if (probe.status >= 500) return { error: `server ${probe.status}` };
    if (probe.status >= 400) return (probe.data && probe.data.error) ? probe.data : { error: `request failed with status ${probe.status}` };
    return (probe.data !== null && probe.data !== undefined) ? probe.data : { error: `malformed response from ${url}` };
  }

  static async post(url, body) {
    try {
      const res = await fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body || {}),
      });
      const data = await res.json().catch(() => null);
      if (!res.ok) {
        return (data && typeof data === "object")
          ? { ok: false, ...data }
          : { ok: false, error: `request failed with status ${res.status}` };
      }
      return data || { ok: true };
    } catch (e) {
      return { ok: false, error: "backend unreachable" };
    }
  }

  static async postBlob(url, blob) {
    try {
      const res = await fetch(url, {
        method: "POST",
        headers: { "Content-Type": blob.type || "application/octet-stream" },
        body: blob,
      });
      const data = await res.json().catch(() => null);
      if (!res.ok) {
        return (data && typeof data === "object")
          ? { ok: false, ...data }
          : { ok: false, error: `request failed with status ${res.status}` };
      }
      return data || { ok: true };
    } catch (e) {
      return { ok: false, error: "backend unreachable" };
    }
  }
}


class Format {

  static duration(seconds) {
    if (seconds == null || !Number.isFinite(seconds)) return "0s";
    const total = Math.max(0, Math.round(seconds));
    const h = Math.floor(total / 3600);
    const m = Math.floor((total % 3600) / 60);
    if (h) return `${h}h ${String(m).padStart(2, "0")}m`;
    if (m) return `${m}m`;
    return `${total}s`;
  }

  static progressBits(p) {
    if (!p) return [];
    const done = (p.done || 0) + (p.failed || 0);
    const total = p.total || 0;
    const pct = total > 0 ? Math.round((100 * done) / total) : 0;
    const bits = [`${done}/${total}`, `${pct}%`];
    if (p.eta_s != null && Number.isFinite(p.eta_s)) {
      bits.push(`ETA ${Format.duration(p.eta_s)}`);
      if (p.finish_at && typeof p.finish_at === "string" && p.finish_at.length >= 16) {
        bits.push(`≈ ${p.finish_at.slice(11, 16)}`);
      }
    } else if (done < total) {
      bits.push("estimating ETA");
    }
    if (p.failed) bits.push(`${p.failed} FAILED`);
    return bits;
  }
}


class Toast {
  static HOLD_MS = 3200;

  static show(message, kind) {
    const el = document.getElementById("toast");
    if (!el) return;
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
