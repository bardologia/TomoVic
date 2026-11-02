"use strict";

class StreamSubscription {
  constructor(hub, jobId, unit, handler) {
    this.hub     = hub;
    this.jobId   = jobId;
    this.unit    = unit;
    this.handler = handler;
    this.closed  = false;
  }

  get key() {
    return StreamHub.keyOf(this.jobId, this.unit);
  }

  close() {
    this.hub.unsubscribe(this);
  }
}


class StreamKey {
  constructor(jobId, unit) {
    this.jobId  = jobId;
    this.unit   = unit;
    this.lastId = -1;
    this.subs   = new Set();
  }

  get viewers() {
    return [...this.subs].filter((sub) => !sub.closed);
  }

  deliver(data) {
    this.viewers.forEach((sub) => sub.handler(data));
  }
}


class StreamHub {
  static RETRY_MS = 3000;

  static instance() {
    if (!StreamHub.page) StreamHub.page = new StreamHub();
    return StreamHub.page;
  }

  static keyOf(jobId, unit) {
    return unit == null ? jobId : `${jobId}/${unit}`;
  }

  static channelId() {
    const bytes = crypto.getRandomValues(new Uint8Array(12));
    return Array.from(bytes, (b) => b.toString(16).padStart(2, "0")).join("");
  }

  constructor() {
    this.channel = StreamHub.channelId();
    this.source  = null;
    this.open    = false;
    this.boot    = null;
    this.keys    = new Map();
    this.retry   = null;
  }

  get connected() {
    return this.open;
  }

  subscribe(jobId, unit, handler) {
    const sub   = new StreamSubscription(this, jobId, unit, handler);
    const fresh = !this.keys.has(sub.key);
    if (fresh) this.keys.set(sub.key, new StreamKey(jobId, unit));

    const key = this.keys.get(sub.key);
    key.subs.add(sub);

    if (!this.source) this._connect();
    else if (this.open && fresh) this._announce(key);
    return sub;
  }

  unsubscribe(sub) {
    if (sub.closed) return;
    sub.closed = true;

    const key = this.keys.get(sub.key);
    if (!key || !key.subs.has(sub)) return;
    key.subs.delete(sub);
    if (key.subs.size) return;

    this.keys.delete(sub.key);
    if (this.open) Api.post(`/api/stream/${this.channel}/unsubscribe`, { job_id: key.jobId, unit: key.unit });
    if (!this.keys.size) this._disconnect();
  }

  _connect() {
    clearTimeout(this.retry);
    this.retry  = null;
    this.source = new EventSource(`/api/stream?channel=${this.channel}`);
    this.source.onmessage = (ev) => this._onMessage(ev);
    this.source.onerror   = () => this._onError();
  }

  _onMessage(ev) {
    let data;
    try {
      data = JSON.parse(ev.data);
    } catch (e) {
      return;
    }

    if (data.type === "hello") {
      this._onHello(data);
      return;
    }
    if (data.type === "truncated") {
      this._broadcast(data);
      return;
    }

    const key = this.keys.get(data.key);
    if (!key) return;
    if (data.id != null) key.lastId = data.id;
    key.deliver(data);
  }

  _onHello(data) {
    const restarted = this.boot !== null && this.boot !== data.boot;
    this.boot = data.boot;
    this.open = true;

    this.keys.forEach((key) => {
      if (restarted) key.lastId = -1;
      this._announce(key);
    });
  }

  _announce(key) {
    Api.post(`/api/stream/${this.channel}/subscribe`, { job_id: key.jobId, unit: key.unit, after: key.lastId }).then((res) => {
      if (res.ok || res.stale || this.keys.get(StreamHub.keyOf(key.jobId, key.unit)) !== key) return;
      key.deliver({ type: "unavailable", error: res.error || "subscription refused" });
    });
  }

  _broadcast(data) {
    this.keys.forEach((key) => key.deliver(data));
  }

  _onError() {
    const closed = this.source !== null && this.source.readyState === EventSource.CLOSED;

    if (this.open) {
      this.open = false;
      this._broadcast({ type: "link", state: "lost" });
    }
    if (!closed) return;

    this._dropSource();
    if (this.keys.size && !this.retry) {
      this.retry = setTimeout(() => {
        this.retry = null;
        if (this.keys.size && !this.source) this._connect();
      }, StreamHub.RETRY_MS);
    }
  }

  _disconnect() {
    clearTimeout(this.retry);
    this.retry = null;
    this.open  = false;
    this._dropSource();
  }

  _dropSource() {
    if (!this.source) return;
    this.source.close();
    this.source = null;
  }
}

window.StreamHub = StreamHub;
