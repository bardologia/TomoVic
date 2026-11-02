import assert from "node:assert";
import fs from "node:fs";
import path from "node:path";
import vm from "node:vm";
import { fileURLToPath } from "node:url";

const here   = path.dirname(fileURLToPath(import.meta.url));
const source = fs.readFileSync(path.join(here, "..", "..", "webui", "static", "js", "stream_hub.js"), "utf-8");

class FakeEventSource {
  static CONNECTING = 0;
  static OPEN       = 1;
  static CLOSED     = 2;
  static opened     = [];

  constructor(url) {
    this.url        = url;
    this.readyState = FakeEventSource.CONNECTING;
    this.closed     = false;
    this.onmessage  = null;
    this.onerror    = null;
    FakeEventSource.opened.push(this);
  }

  hello(boot) {
    this.readyState = FakeEventSource.OPEN;
    this.message({ type: "hello", channel: "x", boot });
  }

  message(data) {
    this.onmessage({ data: JSON.stringify(data) });
  }

  fail(terminal) {
    this.readyState = terminal ? FakeEventSource.CLOSED : FakeEventSource.CONNECTING;
    this.onerror();
  }

  close() {
    this.closed     = true;
    this.readyState = FakeEventSource.CLOSED;
  }
}

const posts = [];
let   answer = () => ({ ok: true });

const sandbox = {
  window      : {},
  crypto      : { getRandomValues: (array) => array.fill(7) },
  EventSource : FakeEventSource,
  Api         : { post: async (url, body) => { posts.push({ url, body }); return answer(url, body); } },
  setTimeout, clearTimeout, JSON, Map, Set, Array, Uint8Array, Promise, console,
};
vm.createContext(sandbox);
vm.runInContext(source, sandbox);

const StreamHub = sandbox.window.StreamHub;
const tick      = () => new Promise((resolve) => setImmediate(resolve));

const fresh = () => {
  FakeEventSource.opened.length = 0;
  posts.length = 0;
  answer = () => ({ ok: true });
  return new StreamHub();
};

const current = () => FakeEventSource.opened[FakeEventSource.opened.length - 1];

const tests = {
  async "the first subscription opens the single channel and announces after hello"() {
    const hub   = fresh();
    const seen  = [];
    const sub   = hub.subscribe("job-1", null, (e) => seen.push(e));

    assert.equal(FakeEventSource.opened.length, 1);
    assert.equal(current().url, `/api/stream?channel=${hub.channel}`);
    assert.equal(posts.length, 0, "nothing is announced before the hello frame");

    current().hello("boot-a");
    await tick();
    assert.deepEqual(posts, [{ url: `/api/stream/${hub.channel}/subscribe`, body: { job_id: "job-1", unit: null, after: -1 } }]);
    assert.equal(hub.connected, true);
    assert.equal(sub.key, "job-1");
  },

  async "events are routed by key and the last id is remembered per subscription"() {
    const hub = fresh();
    const a   = [];
    const b   = [];
    hub.subscribe("job-a", null, (e) => a.push(e));
    hub.subscribe("job-b", 2,    (e) => b.push(e));
    current().hello("boot-a");
    await tick();

    current().message({ key: "job-a", type: "chunk", data: "A", id: 5 });
    current().message({ key: "job-b/2", type: "chunk", data: "B", id: 1 });
    current().message({ key: "job-zzz", type: "chunk", data: "nobody", id: 9 });

    assert.deepEqual(a.map((e) => e.data), ["A"]);
    assert.deepEqual(b.map((e) => e.data), ["B"]);
    assert.equal(hub.keys.get("job-a").lastId, 5);
    assert.equal(hub.keys.get("job-b/2").lastId, 1);
  },

  async "a second subscription on an open channel is announced at once"() {
    const hub = fresh();
    hub.subscribe("job-a", null, () => {});
    current().hello("boot-a");
    await tick();
    posts.length = 0;

    hub.subscribe("job-a", 3, () => {});
    await tick();

    assert.equal(FakeEventSource.opened.length, 1, "no second connection");
    assert.deepEqual(posts.map((p) => p.body), [{ job_id: "job-a", unit: 3, after: -1 }]);
  },

  async "closing the last subscription posts unsubscribe and drops the connection"() {
    const hub = fresh();
    const sub = hub.subscribe("job-a", null, () => {});
    current().hello("boot-a");
    await tick();
    posts.length = 0;

    sub.close();
    await tick();

    assert.deepEqual(posts, [{ url: `/api/stream/${hub.channel}/unsubscribe`, body: { job_id: "job-a", unit: null } }]);
    assert.equal(current().closed, true);
    assert.equal(hub.source, null);
    assert.equal(hub.connected, false);
    assert.equal(sub.closed, true);

    sub.close();
    assert.equal(posts.length, 1, "closing twice posts once");
  },

  async "a dropped connection notifies every subscription once and re-announces from the last id after hello"() {
    const hub  = fresh();
    const seen = [];
    hub.subscribe("job-a", null, (e) => seen.push(e));
    current().hello("boot-a");
    await tick();
    current().message({ key: "job-a", type: "chunk", data: "x", id: 42 });
    posts.length = 0;

    current().fail(false);
    current().fail(false);
    assert.deepEqual(seen.filter((e) => e.type === "link"), [{ type: "link", state: "lost" }]);
    assert.equal(hub.connected, false);
    assert.equal(FakeEventSource.opened.length, 1, "the browser's own retry is left to the EventSource");

    current().hello("boot-a");
    await tick();
    assert.deepEqual(posts.map((p) => p.body), [{ job_id: "job-a", unit: null, after: 42 }]);
  },

  async "a restarted server resets every last id so the replay starts over"() {
    const hub = fresh();
    hub.subscribe("job-a", null, () => {});
    current().hello("boot-a");
    await tick();
    current().message({ key: "job-a", type: "chunk", data: "x", id: 42 });
    posts.length = 0;

    current().fail(false);
    current().hello("boot-b");
    await tick();

    assert.deepEqual(posts.map((p) => p.body), [{ job_id: "job-a", unit: null, after: -1 }]);
  },

  async "a terminally closed connection is reopened after the retry delay while subscriptions remain"() {
    StreamHub.RETRY_MS = 5;
    const hub = fresh();
    hub.subscribe("job-a", null, () => {});
    current().hello("boot-a");
    await tick();

    current().fail(true);
    assert.equal(hub.source, null);
    await new Promise((resolve) => setTimeout(resolve, 20));

    assert.equal(FakeEventSource.opened.length, 2, "a new EventSource was opened");
    assert.equal(FakeEventSource.opened[0].closed, true);
    StreamHub.RETRY_MS = 3000;
  },

  async "a refused subscription reaches its handler as unavailable, a stale channel does not"() {
    const hub  = fresh();
    const seen = [];
    answer = (url, body) => (body.job_id === "ghost" ? { ok: false, error: "unknown job" } : { ok: false, error: "unknown channel", stale: true });
    hub.subscribe("ghost", null, (e) => seen.push(e));
    hub.subscribe("later", null, (e) => seen.push(e));
    current().hello("boot-a");
    await tick();
    await tick();

    assert.deepEqual(seen, [{ type: "unavailable", error: "unknown job" }]);
  },

  async "a truncation marker fans out to every subscription"() {
    const hub = fresh();
    const a   = [];
    const b   = [];
    hub.subscribe("job-a", null, (e) => a.push(e));
    hub.subscribe("job-b", null, (e) => b.push(e));
    current().hello("boot-a");
    await tick();

    current().message({ key: null, type: "truncated", dropped: 12 });

    assert.deepEqual(a, [{ key: null, type: "truncated", dropped: 12 }]);
    assert.deepEqual(b, [{ key: null, type: "truncated", dropped: 12 }]);
  },

  async "two viewers of one key share a single server subscription and both receive its events"() {
    const hub   = fresh();
    const tile  = [];
    const tuner = [];
    const a     = hub.subscribe("job-a", null, (e) => tile.push(e));
    current().hello("boot-a");
    await tick();
    const b = hub.subscribe("job-a", null, (e) => tuner.push(e));
    await tick();

    assert.equal(posts.filter((p) => p.url.endsWith("/subscribe")).length, 1, "the key is announced once");
    current().message({ key: "job-a", type: "chunk", data: "x", id: 1 });
    assert.deepEqual(tile.map((e) => e.data), ["x"]);
    assert.deepEqual(tuner.map((e) => e.data), ["x"]);
    assert.equal(a.closed, false);

    posts.length = 0;
    a.close();
    assert.equal(posts.length, 0, "the key stays subscribed while a viewer remains");
    current().message({ key: "job-a", type: "chunk", data: "y", id: 2 });
    assert.deepEqual(tile.map((e) => e.data), ["x"], "a closed viewer hears nothing more");
    assert.deepEqual(tuner.map((e) => e.data), ["x", "y"]);

    b.close();
    await tick();
    assert.deepEqual(posts.map((p) => p.url.split("/").pop()), ["unsubscribe"]);
    assert.equal(hub.source, null, "the channel closes with the last viewer");
  },

  async "a viewer closing itself inside its handler does not disturb the other viewers of the key"() {
    const hub  = fresh();
    const seen = [];
    const self = hub.subscribe("job-a", null, (e) => { seen.push("self:" + e.type); if (e.type === "end") self.close(); });
    hub.subscribe("job-a", null, (e) => seen.push("other:" + e.type));
    current().hello("boot-a");
    await tick();

    current().message({ key: "job-a", type: "end", id: 3 });

    assert.deepEqual(seen, ["self:end", "other:end"]);
    assert.equal(hub.keys.get("job-a").subs.size, 1);
    assert.equal(hub.connected, true);
  },

  async "malformed frames are ignored"() {
    const hub  = fresh();
    const seen = [];
    hub.subscribe("job-a", null, (e) => seen.push(e));
    current().hello("boot-a");
    await tick();

    current().onmessage({ data: "{not json" });
    assert.deepEqual(seen, []);
  },
};

let failed = 0;
for (const [name, run] of Object.entries(tests)) {
  try {
    await run();
    console.log(`ok   ${name}`);
  } catch (error) {
    failed += 1;
    console.log(`FAIL ${name}\n     ${error.message}`);
  }
}
console.log(failed ? `${failed} failing` : `all ${Object.keys(tests).length} passing`);
process.exit(failed ? 1 : 0);
