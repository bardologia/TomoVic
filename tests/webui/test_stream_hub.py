"""Tests for the page-wide live-output channel and its routes.

Covers the tagging sink, the channel's queue with truncation and close
sentinel, subscription attach, replace, detach and prune, the hub's channel
registry across reconnects, the subscribe and unsubscribe results for main
streams and unit tails, the SSE pump with its hello frame and keepalives, the
POST route validation, and a real process manager job followed end to end
through a channel.
"""

from __future__ import annotations

import json
import sys
import threading
import time
from unittest.mock import MagicMock

import pytest

from process_manager          import JobStream
from routers.dispatch         import HttpExchange
from routers.launch_routers   import JobRouter
from stream_hub               import ChannelSink, StreamChannel, StreamHub

from tests.webui.conftest import FakeHandler, SLEEP_LONG


class BrokenPipe:
    """Output stream standing in for a socket whose peer has gone away."""

    def write(self, data: bytes) -> int:
        """Raises the broken pipe a dead client socket raises."""
        raise BrokenPipeError

    def flush(self) -> None:
        """Flushing a dead socket is a no-op here."""
        return


class FakeBackend:
    """Job backend stub handing out prepared main streams and unit tails.

    Attributes:
        streams : Main streams keyed by job id.
        units   : Unit tail results keyed by (job id, unit index).
    """

    def __init__(self) -> None:
        """Starts with no jobs."""
        self.streams = {}
        self.units   = {}

    def get_stream(self, job_id: str):
        """Returns the main stream of a job, or None for an unknown job."""
        return self.streams.get(job_id)

    def unit_stream(self, job_id: str, index: int) -> dict:
        """Returns the prepared unit tail result, or the lookup error."""
        return self.units.get((job_id, index), {"ok": False, "error": f"unit index {index} is out of range"})


@pytest.fixture
def logger():
    """Returns a logger stub recording warnings."""
    return MagicMock()


@pytest.fixture
def hub(logger):
    """Returns a hub over the stub logger."""
    return StreamHub(logger)


def drain(channel: StreamChannel) -> list[dict]:
    """Returns every event queued on a channel without waiting."""
    events = []
    while True:
        event = channel.next(0)
        if event is None:
            return events
        events.append(event)


def unit_tail(logger, *chunks: str) -> dict:
    """Returns a unit tail result whose stream already carries its header and the given chunks."""
    stream = JobStream(logger)
    stream.publish({"type": "unit", "name": "seed0", "log": "/x/seed0.log", "status": "running", "gpu": 0})
    for chunk in chunks:
        stream.publish({"type": "chunk", "data": chunk})
    return {"ok": True, "stream": stream, "stop": threading.Event()}


def test_sink_tags_events_with_its_key_and_flags_the_end(logger):
    """A sink prefixes every event with the subscription key and remembers having seen the end event."""
    channel = StreamChannel("ch", logger)
    sink    = ChannelSink(channel, "job-1")

    sink.put_nowait({"type": "chunk", "data": "a", "id": 1})
    assert sink.ended is False

    sink.put_nowait({"type": "end", "id": 2})
    assert sink.ended is True

    assert drain(channel) == [{"key": "job-1", "type": "chunk", "data": "a", "id": 1}, {"key": "job-1", "type": "end", "id": 2}]


def test_a_full_channel_is_truncated_with_a_marker_and_keeps_flowing(logger, monkeypatch):
    """Offering past the queue limit drains the queue, records the loss in a marker and delivers the new event."""
    monkeypatch.setattr(StreamChannel, "QUEUE_LIMIT", 3)
    channel = StreamChannel("ch", logger)

    for index in range(3):
        channel.offer({"key": "a", "type": "chunk", "data": str(index)})
    channel.offer({"key": "b", "type": "chunk", "data": "late"})

    events = drain(channel)

    assert events[0] == {"key": None, "type": "truncated", "dropped": 3}
    assert events[1] == {"key": "b", "type": "chunk", "data": "late"}
    assert channel.dropped == 3
    assert "fell 3 events behind" in logger.warning.call_args.args[0]


def test_attach_replays_the_buffer_after_the_given_id_and_tags_live_events(logger):
    """Attaching a stream replays only the buffered events newer than `after`, then forwards live ones."""
    channel = StreamChannel("ch", logger)
    stream  = JobStream(logger)
    for index in range(3):
        stream.publish({"type": "chunk", "data": f"old {index}"})

    channel.attach("job-1", stream, None, after=2)
    stream.publish({"type": "chunk", "data": "live"})

    events = drain(channel)

    assert [event["data"] for event in events] == ["old 2", "live"]
    assert {event["key"] for event in events} == {"job-1"}
    assert [event["id"] for event in events] == [3, 4]


def test_attaching_the_same_key_again_releases_the_previous_subscription(logger):
    """Re-subscribing a key detaches the earlier sink from its stream and sets its tail's stop event."""
    channel = StreamChannel("ch", logger)
    first   = JobStream(logger)
    second  = JobStream(logger)
    stop    = threading.Event()

    channel.attach("job-1/0", first, stop, -1)
    channel.attach("job-1/0", second, None, -1)
    first.publish({"type": "chunk", "data": "stale"})
    second.publish({"type": "chunk", "data": "fresh"})

    assert stop.is_set()
    assert first.subscribers == []
    assert [event["data"] for event in drain(channel)] == ["fresh"]


def test_detach_releases_and_reports_whether_the_key_was_attached(logger):
    """Detaching an attached key releases it and returns True; an unknown key returns False."""
    channel = StreamChannel("ch", logger)
    stream  = JobStream(logger)
    stop    = threading.Event()

    channel.attach("job-1/2", stream, stop, -1)

    assert channel.detach("job-1/2") is True
    assert channel.detach("job-1/2") is False
    assert stop.is_set()
    assert stream.subscribers == []


def test_prune_releases_only_the_subscriptions_whose_stream_ended(logger):
    """Pruning drops the keys whose sink saw the end event and leaves the live ones attached."""
    channel = StreamChannel("ch", logger)
    ended   = JobStream(logger)
    live    = JobStream(logger)

    channel.attach("done", ended, None, -1)
    channel.attach("live", live, None, -1)
    ended.publish({"type": "end"})

    assert channel.prune() == ["done"]
    assert set(channel.subscriptions) == {"live"}
    assert ended.subscribers == []
    assert live.subscribers  == [channel.subscriptions["live"].sink]


def test_close_releases_everything_and_queues_the_sentinel_even_when_full(logger, monkeypatch):
    """Closing releases every subscription and makes room for the close sentinel on a full queue."""
    monkeypatch.setattr(StreamChannel, "QUEUE_LIMIT", 2)
    channel = StreamChannel("ch", logger)
    stream  = JobStream(logger)
    stop    = threading.Event()

    channel.attach("job-1/0", stream, stop, -1)
    channel.offer({"key": "x", "type": "chunk", "data": "1"})
    channel.offer({"key": "x", "type": "chunk", "data": "2"})
    channel.close()

    assert channel.closed is True
    assert channel.subscriptions == {}
    assert stop.is_set()
    assert stream.subscribers == []
    assert drain(channel)[-1] is StreamChannel.CLOSE


def test_opening_the_same_channel_id_again_closes_the_one_left_behind(hub):
    """A reconnecting page gets a fresh channel while the stale one is closed and its subscriptions released."""
    stream = JobStream(hub.logger)
    stale  = hub.open("page-1")
    stale.attach("job-1", stream, None, -1)

    fresh = hub.open("page-1")

    assert hub.channel("page-1") is fresh
    assert stale.closed is True
    assert stream.subscribers == []
    assert drain(stale) == [StreamChannel.CLOSE]
    assert fresh.subscriptions == {}


def test_release_closes_only_the_channel_that_is_still_current(hub):
    """Releasing a replaced channel leaves the current one untouched; releasing the current one removes it."""
    stale = hub.open("page-1")
    fresh = hub.open("page-1")

    hub.release(stale)
    assert hub.channel("page-1") is fresh
    assert fresh.closed is False

    hub.release(fresh)
    assert hub.channel("page-1") is None
    assert fresh.closed is True


def test_subscribe_on_an_unknown_channel_is_refused_as_stale(hub):
    """Subscribing or unsubscribing before the channel exists reports a stale channel so the page retries after its hello."""
    backend = FakeBackend()

    assert hub.subscribe("missing", backend, "job-1", None, -1) == {"ok": False, "error": "unknown channel", "stale": True}
    assert hub.unsubscribe("missing", "job-1", None)            == {"ok": False, "error": "unknown channel", "stale": True}


def test_subscribe_main_stream_replays_after_the_given_id(hub):
    """Subscribing a job's main stream attaches it under the job id and honours `after`."""
    backend = FakeBackend()
    stream  = JobStream(hub.logger)
    backend.streams["job-1"] = stream
    for index in range(4):
        stream.publish({"type": "chunk", "data": f"c{index}"})

    channel = hub.open("page-1")
    result  = hub.subscribe("page-1", backend, "job-1", None, 2)

    assert result == {"ok": True, "key": "job-1"}
    assert [event["data"] for event in drain(channel)] == ["c2", "c3"]


def test_subscribe_unknown_job_reports_the_error(hub):
    """A job the backend does not know is refused without touching the channel."""
    channel = hub.open("page-1")

    assert hub.subscribe("page-1", FakeBackend(), "job-x", None, -1) == {"ok": False, "error": "unknown job"}
    assert channel.subscriptions == {}


def test_subscribe_unit_tail_ignores_after_and_releases_on_unsubscribe(hub):
    """A unit tail replays from its top whatever `after` says, and unsubscribing stops the tail."""
    backend = FakeBackend()
    tail    = unit_tail(hub.logger, "line 1", "line 2")
    backend.units[("job-1", 3)] = tail

    channel = hub.open("page-1")
    result  = hub.subscribe("page-1", backend, "job-1", 3, 99)
    events  = drain(channel)

    assert result == {"ok": True, "key": "job-1/3"}
    assert [event["type"] for event in events] == ["unit", "chunk", "chunk"]
    assert all(event["key"] == "job-1/3" for event in events)

    assert hub.unsubscribe("page-1", "job-1", 3) == {"ok": True, "key": "job-1/3", "attached": True}
    assert tail["stop"].is_set()
    assert tail["stream"].subscribers == []


def test_subscribe_unit_lookup_error_is_passed_through(hub):
    """The backend's unit lookup error is the subscribe result."""
    hub.open("page-1")

    result = hub.subscribe("page-1", FakeBackend(), "job-1", 7, -1)

    assert result == {"ok": False, "error": "unit index 7 is out of range"}


def test_subscribe_prunes_ended_keys_first(hub):
    """An ended subscription the page never released is dropped when the page subscribes again."""
    backend = FakeBackend()
    ended   = JobStream(hub.logger)
    live    = JobStream(hub.logger)
    backend.streams.update({"done": ended, "live": live})

    channel = hub.open("page-1")
    hub.subscribe("page-1", backend, "done", None, -1)
    ended.publish({"type": "end"})
    hub.subscribe("page-1", backend, "live", None, -1)

    assert set(channel.subscriptions) == {"live"}
    assert ended.subscribers == []


def pump_in_thread(router: JobRouter, handler: FakeHandler) -> threading.Thread:
    """Runs the channel route in a daemon thread and returns it."""
    exchange = HttpExchange.of(handler)
    worker   = threading.Thread(target=router.stream, args=(exchange,), daemon=True)
    worker.start()
    return worker


def frames(handler: FakeHandler) -> list:
    """Returns the SSE frames written so far: decoded data payloads, or the raw comment lines."""
    out = []
    for block in handler.wfile.getvalue().decode("utf-8").split("\n\n"):
        if block.startswith("data: "):
            out.append(json.loads(block[6:]))
        elif block:
            out.append(block)
    return out


def wait_until(predicate, timeout: float = 3.0) -> bool:
    """Polls `predicate` until it holds or the timeout passes."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return predicate()


def test_stream_route_requires_the_channel_parameter(hub):
    """A channel request without the channel id is a 400."""
    router  = JobRouter(None, None, None, hub)
    handler = FakeHandler("GET", "/api/stream")

    router.stream(HttpExchange.of(handler))

    assert handler.status == 400
    assert handler.payload()["error"] == "missing channel parameter"
    assert hub.channels == {}


def test_stream_route_sends_hello_then_tagged_events_until_the_channel_closes(hub):
    """The pump opens the channel, writes the hello frame with the boot token, forwards tagged events and exits on close."""
    router  = JobRouter(None, None, None, hub)
    backend = FakeBackend()
    stream  = JobStream(hub.logger)
    backend.streams["job-1"] = stream
    handler = FakeHandler("GET", "/api/stream?channel=page-1")

    worker = pump_in_thread(router, handler)
    assert wait_until(lambda: hub.channel("page-1") is not None)

    hub.subscribe("page-1", backend, "job-1", None, -1)
    stream.publish({"type": "chunk", "data": "hello world"})
    stream.publish({"type": "end"})
    assert wait_until(lambda: len(frames(handler)) == 3)

    hub.channel("page-1").close()
    worker.join(timeout=3)

    assert not worker.is_alive()
    assert handler.status == 200
    assert handler.sent["Content-Type"] == "text/event-stream"
    assert frames(handler) == [
        {"type": "hello", "channel": "page-1", "boot": hub.boot},
        {"key": "job-1", "type": "chunk", "data": "hello world", "id": 1},
        {"key": "job-1", "type": "end", "id": 2},
    ]
    assert hub.channel("page-1") is None


def test_stream_route_writes_keepalive_comments_while_silent(hub, monkeypatch):
    """After KEEPALIVE_S of silence the pump writes a keepalive comment instead of closing."""
    monkeypatch.setattr(JobRouter, "KEEPALIVE_S", 0.05)
    router  = JobRouter(None, None, None, hub)
    handler = FakeHandler("GET", "/api/stream?channel=page-1")

    worker = pump_in_thread(router, handler)
    assert wait_until(lambda: ": keepalive" in frames(handler))

    hub.channel("page-1").close()
    worker.join(timeout=3)

    assert not worker.is_alive()


def test_stream_route_reconnect_replaces_the_channel_and_ends_the_old_pump(hub):
    """A second connection under the same channel id ends the first pump and keeps the new channel open."""
    router = JobRouter(None, None, None, hub)
    first  = FakeHandler("GET", "/api/stream?channel=page-1")
    second = FakeHandler("GET", "/api/stream?channel=page-1")

    pump_a = pump_in_thread(router, first)
    assert wait_until(lambda: hub.channel("page-1") is not None)
    stale = hub.channel("page-1")

    pump_b = pump_in_thread(router, second)
    pump_a.join(timeout=3)

    assert not pump_a.is_alive()
    assert hub.channel("page-1") is not stale
    assert hub.channel("page-1").closed is False
    assert pump_b.is_alive()

    hub.channel("page-1").close()
    pump_b.join(timeout=3)
    assert not pump_b.is_alive()


def test_stream_route_releases_the_channel_when_the_client_breaks_the_pipe(hub):
    """A broken pipe while writing ends the pump and releases the channel and its subscriptions."""
    router  = JobRouter(None, None, None, hub)
    backend = FakeBackend()
    stream  = JobStream(hub.logger)
    backend.streams["job-1"] = stream
    handler = FakeHandler("GET", "/api/stream?channel=page-1")

    worker = pump_in_thread(router, handler)
    assert wait_until(lambda: hub.channel("page-1") is not None)
    hub.subscribe("page-1", backend, "job-1", None, -1)

    handler.wfile = BrokenPipe()
    stream.publish({"type": "chunk", "data": "x"})
    worker.join(timeout=3)

    assert not worker.is_alive()
    assert hub.channel("page-1") is None
    assert stream.subscribers == []


def post(router: JobRouter, path: str, body: dict) -> FakeHandler:
    """Sends a JSON POST through the router's table and returns the handler holding the answer."""
    handler  = FakeHandler("POST", path, json.dumps(body).encode("utf-8"), {"Content-Type": "application/json"})
    exchange = HttpExchange.of(handler)
    exchange.read_body()
    assert router.handle(exchange)
    return handler


def test_subscribe_route_validates_the_body(hub):
    """A missing job id, a non-integer unit or a non-integer after are answered with 400."""
    router = JobRouter(None, None, None, hub)
    hub.open("page-1")

    assert post(router, "/api/stream/page-1/subscribe", {"unit": None}).status == 400
    assert post(router, "/api/stream/page-1/subscribe", {"job_id": "job-1", "unit": "2"}).status == 400
    assert post(router, "/api/stream/page-1/subscribe", {"job_id": "job-1", "unit": True}).status == 400
    assert post(router, "/api/stream/page-1/subscribe", {"job_id": "job-1", "after": "7"}).status == 400
    assert post(router, "/api/stream/page-1/unsubscribe", {"job_id": ""}).status == 400
    assert hub.channel("page-1").subscriptions == {}


def test_subscribe_and_unsubscribe_routes_answer_404_for_an_unknown_channel(hub):
    """Channel routes on a channel the hub does not hold answer 404 flagged stale."""
    router = JobRouter(None, None, None, hub)

    subscribed   = post(router, "/api/stream/ghost/subscribe",   {"job_id": "job-1"})
    unsubscribed = post(router, "/api/stream/ghost/unsubscribe", {"job_id": "job-1"})

    assert subscribed.status == 404 and subscribed.payload()["stale"] is True
    assert unsubscribed.status == 404 and unsubscribed.payload()["stale"] is True


def test_subscribe_route_attaches_through_the_process_manager(hub):
    """A job id subscribes through the local process manager backend."""
    local   = FakeBackend()
    local.streams["0f3c88aa9911"] = JobStream(hub.logger)
    router  = JobRouter(None, local, None, hub)
    channel = hub.open("page-1")

    plain = post(router, "/api/stream/page-1/subscribe", {"job_id": "0f3c88aa9911", "unit": None, "after": -1})

    assert plain.status == 200 and plain.payload() == {"ok": True, "key": "0f3c88aa9911"}
    assert set(channel.subscriptions) == {"0f3c88aa9911"}
    assert len(local.streams["0f3c88aa9911"].subscribers) == 1


def test_unsubscribe_route_detaches_and_reports_the_attachment(hub):
    """Unsubscribing an attached key answers attached True, a second time attached False."""
    backend = FakeBackend()
    backend.streams["job-1"] = JobStream(hub.logger)
    router = JobRouter(None, backend, None, hub)
    hub.open("page-1")
    post(router, "/api/stream/page-1/subscribe", {"job_id": "job-1"})

    first  = post(router, "/api/stream/page-1/unsubscribe", {"job_id": "job-1"})
    second = post(router, "/api/stream/page-1/unsubscribe", {"job_id": "job-1"})

    assert first.payload()  == {"ok": True, "key": "job-1", "attached": True}
    assert second.payload() == {"ok": True, "key": "job-1", "attached": False}
    assert backend.streams["job-1"].subscribers == []


def test_a_real_job_is_followed_end_to_end_through_a_channel(make_manager):
    """A launched process's output and end event reach the channel tagged with its job id, and the key prunes."""
    manager = make_manager({"echo": "print('channel hello', flush=True)\n", "sleep_long": SLEEP_LONG})
    hub     = StreamHub(manager.logger)
    router  = JobRouter(None, manager, None, hub)
    handler = FakeHandler("GET", "/api/stream?channel=page-1")

    worker = pump_in_thread(router, handler)
    assert wait_until(lambda: hub.channel("page-1") is not None)

    job_id = manager.launch("echo", sys.executable)["job_id"]
    assert hub.subscribe("page-1", manager, job_id, None, -1) == {"ok": True, "key": job_id}
    assert wait_until(lambda: any(frame.get("type") == "end" for frame in frames(handler) if isinstance(frame, dict)), timeout=15)

    events = [frame for frame in frames(handler) if isinstance(frame, dict) and frame.get("key") == job_id]
    text   = "".join(event.get("data", "") for event in events if event["type"] == "chunk")

    assert "channel hello" in text
    assert events[-1]["type"] == "end"
    assert any(event["type"] == "status" and event.get("status") == "finished" for event in events)

    hub.subscribe("page-1", manager, "nobody", None, -1)
    assert hub.channel("page-1").subscriptions == {}

    hub.channel("page-1").close()
    worker.join(timeout=3)
    assert not worker.is_alive()
