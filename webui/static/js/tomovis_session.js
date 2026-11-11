"use strict";

class TomoVisBus {
  constructor() {
    this.handlers = new Map();
  }

  on(topic, fn) {
    if (!this.handlers.has(topic)) this.handlers.set(topic, []);
    this.handlers.get(topic).push(fn);
    return fn;
  }

  off(topic, fn) {
    const list = this.handlers.get(topic);
    if (!list) return;
    const index = list.indexOf(fn);
    if (index >= 0) list.splice(index, 1);
  }

  emit(topic, payload) {
    const list = this.handlers.get(topic);
    if (!list) return;
    for (const fn of [...list]) {
      try {
        fn(payload);
      } catch (error) {
        setTimeout(() => { throw error; });
      }
    }
  }
}

class TomoVisEnvelope {
  static MAGIC = "TVE1";

  static decode(buffer) {
    const bytes = new Uint8Array(buffer);
    const magic = String.fromCharCode(bytes[0], bytes[1], bytes[2], bytes[3]);
    if (magic !== TomoVisEnvelope.MAGIC) throw new Error(`TomoVis envelope magic is ${JSON.stringify(magic)}, expected ${TomoVisEnvelope.MAGIC}`);

    const length = new DataView(buffer).getUint32(4, true);
    const header = JSON.parse(new TextDecoder("utf-8").decode(bytes.subarray(8, 8 + length)));
    const blobs  = {};
    const meta   = {};

    for (const blob of header.blobs || []) {
      meta[blob.name]  = blob;
      blobs[blob.name] = TomoVisEnvelope.view(buffer, blob);
    }
    return { header, blobs, meta };
  }

  static view(buffer, blob) {
    if (blob.kind === "png") return new Blob([new Uint8Array(buffer, blob.offset, blob.nbytes)], { type: "image/png" });
    if (blob.dtype === "uint8") return new Uint8Array(buffer, blob.offset, blob.nbytes);
    if (blob.dtype === "float32") {
      if (blob.offset % 4 === 0) return new Float32Array(buffer, blob.offset, blob.nbytes / 4);
      return new Float32Array(buffer.slice(blob.offset, blob.offset + blob.nbytes));
    }
    throw new Error(`TomoVis envelope blob ${blob.name} has unsupported dtype ${blob.dtype}`);
  }
}

class TomoVisSessionError extends Error {
  constructor(status, message) {
    super(message);
    this.status = status;
  }
}

class TomoVisSession {
  static BUSY_DELAY_MS = 250;
  static ROOT          = "/api/tomovis";

  constructor(bus) {
    this.bus        = bus;
    this.kind       = null;
    this.webgl2     = false;
    this._sid       = null;
    this._snapshot  = null;
    this.seq        = 0;
    this.queue      = [];
    this.inFlight   = null;
    this.busy       = false;
    this.busyTimer  = null;
    this.dialogSink = null;
    this.onExpired  = null;
    this.closed     = false;
  }

  get sid() {
    return this._sid;
  }

  get snapshot() {
    return this._snapshot;
  }

  async open({ kind, webgl2 }) {
    this.kind   = kind;
    this.webgl2 = Boolean(webgl2);
    this.closed = false;

    const decoded = await this._binary(`${TomoVisSession.ROOT}/session`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ kind, webgl2: this.webgl2 }) });
    this._sid = decoded.header.sid;
    this._applyWindow(decoded);
    this._pump();
    return this._snapshot;
  }

  send(event, { coalesce } = {}) {
    const owner = event.widget || (event.type === "tab" ? "tabWidget" : null);
    return this._enqueue({ route: "event", body: { event }, coalesce, widget: owner, apply: (decoded) => this._applyWindow(decoded) });
  }

  figure(id, op, payload = {}, { coalesce } = {}) {
    return this._enqueue({ route: "figure", body: { figure: id, op, ...payload }, coalesce, widget: null, apply: (decoded) => this._applyFigure(decoded) });
  }

  scriptSlicer(path) {
    return this._enqueue({ route: "script/slicer", body: { path }, coalesce: null, widget: null, apply: (decoded) => this._applyFigure(decoded) });
  }

  async fetchVolume(serial) {
    const decoded = await this._binary(`${TomoVisSession.ROOT}/volume?sid=${encodeURIComponent(this._sid)}&serial=${encodeURIComponent(serial)}`, { method: "GET" });
    return { shape: decoded.header.shape, serial: decoded.header.serial, data: decoded.blobs.volume };
  }

  async scriptVolume(path) {
    const decoded = await this._binary(`${TomoVisSession.ROOT}/script/volume?sid=${encodeURIComponent(this._sid)}&path=${encodeURIComponent(path)}`, { method: "GET" });
    return { header: decoded.header, volume1: decoded.blobs.volume_1, volume2: decoded.blobs.volume_2 };
  }

  listDir(path, patterns = []) {
    const query = new URLSearchParams({ path: path || "" });
    for (const pattern of patterns) query.append("pattern", pattern);
    return Api.get(`${TomoVisSession.ROOT}/fs?${query.toString()}`);
  }

  writeFile(path, blob, kind) {
    const type = kind === "image" ? "image/png" : "application/octet-stream";
    const body = blob.type === type ? blob : new Blob([blob], { type });
    const query = new URLSearchParams({ sid: this._sid, path, kind });
    return Api.postBlob(`${TomoVisSession.ROOT}/write?${query.toString()}`, body);
  }

  exportHdf5(payload) {
    return Api.post(`${TomoVisSession.ROOT}/export_hdf5`, { sid: this._sid, ...payload });
  }

  log(lines) {
    return Api.post(`${TomoVisSession.ROOT}/log`, { sid: this._sid, lines });
  }

  pending(widget) {
    let count = this.queue.filter((item) => item.widget === widget).length;
    if (this.inFlight && this.inFlight.widget === widget) count += 1;
    return count;
  }

  idle() {
    return !this.inFlight && this.queue.length === 0;
  }

  close() {
    if (!this._sid || this.closed) return;
    this.closed = true;
    navigator.sendBeacon(`${TomoVisSession.ROOT}/close`, new Blob([JSON.stringify({ sid: this._sid })], { type: "application/json" }));
    this._drop("TomoVis session closed");
  }

  _drop(reason) {
    const dropped     = this.queue.splice(0, this.queue.length);
    const error       = new TomoVisSessionError(0, reason);
    error.reported    = true;
    dropped.forEach((item) => item.waiters.forEach((w) => w.reject(error)));
  }

  _enqueue(item) {
    return new Promise((resolve, reject) => {
      item.waiters = [{ resolve, reject }];
      const tail   = this.queue[this.queue.length - 1];

      if (item.coalesce === "tick") {
        const queued = this.queue.find((other) => other.coalesce === "tick");
        if (queued) {
          queued.waiters.push(...item.waiters);
          return;
        }
      } else if (item.coalesce && tail && tail.coalesce === item.coalesce) {
        item.waiters.unshift(...tail.waiters);
        this.queue[this.queue.length - 1] = item;
        return;
      }

      this.queue.push(item);
      this._pump();
    });
  }

  async _pump() {
    if (this.inFlight || this.queue.length === 0 || !this._sid) return;

    const item    = this.queue.shift();
    this.inFlight = item;
    this._armBusy();

    this.seq += 1;
    const seq  = this.seq;
    const body = { sid: this._sid, seq, ...item.body };

    let decoded = null;
    let failure = null;
    try {
      decoded = await this._binary(`${TomoVisSession.ROOT}/${item.route}`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
    } catch (error) {
      failure = error;
    }

    this.inFlight = null;
    if (decoded) {
      this._applySafely(item, decoded);
      item.waiters.forEach((w) => w.resolve(decoded.header));
    } else {
      this._fail(failure, item);
      item.waiters.forEach((w) => w.reject(failure));
    }

    this._settleBusy();
    this._pump();
  }

  _applySafely(item, decoded) {
    try {
      item.apply(decoded);
    } catch (error) {
      setTimeout(() => { throw error; });
    }
  }

  _fail(error, item) {
    const status   = error instanceof TomoVisSessionError ? error.status : 0;
    error.reported = true;

    if (status === 404 && this.onExpired) {
      this._drop("TomoVis session expired");
      this.onExpired();
      return;
    }

    Toast.show(`TomoVis: ${error.message}`, "error");
    this.bus.emit("resync", {});
    if (this.kind === "window" && !(item.body.event && item.body.event.type === "sync")) this.send({ type: "sync" }).catch((failure) => this.raiseUnreported(failure));
  }

  raiseUnreported(error) {
    if (!error.reported) throw error;
  }

  async _binary(url, init) {
    let res;
    try {
      res = await fetch(url, init);
    } catch (error) {
      throw new TomoVisSessionError(0, "backend unreachable");
    }

    if (!res.ok) {
      const data = await res.json().catch(() => null);
      throw new TomoVisSessionError(res.status, (data && data.error) ? data.error : `request failed with status ${res.status}`);
    }
    return TomoVisEnvelope.decode(await res.arrayBuffer());
  }

  _applyWindow(decoded) {
    const { header, blobs, meta } = decoded;

    const views = {};
    for (const [name, blobName] of Object.entries(header.views || {})) {
      views[name] = { array: blobs[blobName], shape: meta[blobName].shape, dtype: meta[blobName].dtype };
    }
    if (Object.keys(views).length) this.bus.emit("views", views);

    if (header.snapshot) {
      const previous = this._snapshot;
      this._snapshot = header.snapshot;
      this.bus.emit("snapshot", { snapshot: header.snapshot, previous });
    }

    for (const [id, messages] of Object.entries(header.figures || {})) {
      this.bus.emit("figure", { id, messages, frames: this._frames(messages, blobs) });
    }

    this._reportErrors(header);
    this._dialogs(header.dialogs);
  }

  _applyFigure(decoded) {
    const { header, blobs } = decoded;
    if (header.messages && header.messages.length) this.bus.emit("figure", { id: header.figure, messages: header.messages, frames: this._frames(header.messages, blobs) });
    this._reportErrors(header);
    this._dialogs(header.dialogs);
  }

  _frames(messages, blobs) {
    const frames = {};
    for (const message of messages) {
      if (message.type === "frame") frames[message.blob] = blobs[message.blob];
    }
    return frames;
  }

  _reportErrors(header) {
    for (const error of header.slot_errors || []) console.warn(`TomoVis slot error ${error.type}: ${error.message}`);
  }

  _dialogs(requests) {
    if (!requests || requests.length === 0) return;
    if (!this.dialogSink) throw new Error("TomoVis session received dialog requests without a dialog sink");
    this.dialogSink(requests);
  }

  _armBusy() {
    if (this.busyTimer || this.busy) return;
    this.busyTimer = setTimeout(() => {
      this.busyTimer = null;
      this.busy      = true;
      this.bus.emit("busy", { busy: true });
    }, TomoVisSession.BUSY_DELAY_MS);
  }

  _settleBusy() {
    if (!this.idle()) return;
    clearTimeout(this.busyTimer);
    this.busyTimer = null;
    if (!this.busy) return;
    this.busy = false;
    this.bus.emit("busy", { busy: false });
  }
}

class TomoVisTimerDriver {
  constructor(session, bus) {
    this.session  = session;
    this.bus      = bus;
    this.handle   = null;
    this.interval = 0;
    this.listener = bus.on("snapshot", ({ snapshot }) => this.follow(snapshot));
  }

  follow(snapshot) {
    const timer = snapshot && snapshot.controls ? snapshot.controls.tab1Timer : null;
    if (!timer) return;

    if (!timer.active) {
      this.stop();
      return;
    }
    if (this.handle && this.interval === timer.interval) return;

    this.stop();
    this.interval = timer.interval;
    this.handle   = setInterval(() => this.tick(), timer.interval);
  }

  tick() {
    this.session.send({ type: "tick" }, { coalesce: "tick" }).catch((error) => {
      this.stop();
      this.session.raiseUnreported(error);
    });
  }

  stop() {
    if (this.handle) clearInterval(this.handle);
    this.handle   = null;
    this.interval = 0;
  }

  dispose() {
    this.stop();
    this.bus.off("snapshot", this.listener);
  }
}

window.TomoVisBus          = TomoVisBus;
window.TomoVisEnvelope     = TomoVisEnvelope;
window.TomoVisSessionError = TomoVisSessionError;
window.TomoVisSession      = TomoVisSession;
window.TomoVisTimerDriver  = TomoVisTimerDriver;
