"""Multiplexed live-output channel shared by every viewer on one console page.

A browser page opens a single server-sent-events connection and subscribes the
job streams it wants to follow over it, so the per-origin connection budget of
HTTP/1.1 is never spent on one connection per console tile. ChannelSink tags the
events of one subscribed JobStream with its key on the way in, StreamChannel
owns the outgoing queue and the subscriptions of one connection, and StreamHub
keeps the channels by id and attaches and detaches subscriptions on request.
"""

from __future__ import annotations

import queue
import threading
import uuid

from process_manager import JobStream
from web_logger      import WebLogger


class ChannelSink:
    """Subscriber of one JobStream that forwards its events into a channel under a key.

    Attributes:
        channel : Channel the tagged events are offered to.
        key     : Subscription key carried by every event, the job id or ``<job id>/<unit index>``.
        ended   : Whether the stream has published its end event through this sink.
    """

    def __init__(self, channel: StreamChannel, key: str) -> None:
        """Binds the sink to its channel and key."""
        self.channel = channel
        self.key     = key
        self.ended   = False

    def put_nowait(self, event: dict) -> None:
        """Offers one stream event to the channel tagged with the key, never blocking and never raising."""
        if event.get("type") == "end":
            self.ended = True

        self.channel.offer({"key": self.key, **event})


class ChannelSubscription:
    """One job or unit stream attached to a channel.

    Attributes:
        stream : Stream the sink is attached to.
        sink   : Sink receiving the stream's events.
        stop   : Event ending a unit tail when set, None for a job's main stream.
    """

    def __init__(self, stream: JobStream, sink: ChannelSink, stop: threading.Event | None) -> None:
        """Records the stream, its sink and the optional tail stop event."""
        self.stream = stream
        self.sink   = sink
        self.stop   = stop

    def release(self) -> None:
        """Detaches the sink from the stream and ends the unit tail if there is one."""
        self.stream.unsubscribe(self.sink)

        if self.stop is not None:
            self.stop.set()


class StreamChannel:
    """Outgoing event queue and subscription table of one server-sent-events connection.

    A viewer that cannot keep up is truncated rather than allowed to stall the
    publishers: the queue is emptied, a channel-level marker records how many
    events were lost, and delivery resumes.

    Attributes:
        channel_id    : Identifier the page chose for the connection.
        logger        : Console logger warning about truncations.
        events        : Outgoing queue of tagged events, capped at QUEUE_LIMIT.
        subscriptions : Attached streams keyed by subscription key.
        dropped       : Total events dropped by truncations on this channel.
        closed        : Whether the channel has been closed.
    """

    QUEUE_LIMIT = 8000
    CLOSE       = {"type": "close"}

    def __init__(self, channel_id: str, logger: WebLogger) -> None:
        """Creates an empty channel.

        Args:
            channel_id : Identifier the page chose for the connection.
            logger     : Console logger for truncation warnings.
        """
        self.channel_id    = channel_id
        self.logger        = logger
        self.events        = queue.Queue(maxsize=self.QUEUE_LIMIT)
        self.subscriptions = {}
        self.dropped       = 0
        self.closed        = False
        self.offer_lock    = threading.Lock()
        self.lock          = threading.Lock()

    def offer(self, event: dict) -> None:
        """Queues one tagged event, truncating the queue with a marker when it is full.

        Args:
            event : Tagged stream event, carrying the subscription key under ``key``.
        """
        with self.offer_lock:
            try:
                self.events.put_nowait(event)
                return
            except queue.Full:
                pass

            dropped       = self._drain()
            self.dropped += dropped
            self.events.put_nowait({"key": None, "type": "truncated", "dropped": dropped})
            self.events.put_nowait(event)

        self.logger.warning(f"a console channel fell {dropped} events behind and was truncated; the on-disk logs keep the full output")

    def _drain(self) -> int:
        """Empties the outgoing queue and returns how many events it held."""
        dropped = 0

        while True:
            try:
                self.events.get_nowait()
                dropped += 1
            except queue.Empty:
                return dropped

    def next(self, timeout: float) -> dict | None:
        """Returns the next outgoing event, or None when none arrived within `timeout` seconds."""
        try:
            return self.events.get(timeout=timeout)
        except queue.Empty:
            return None

    def attach(self, key: str, stream: JobStream, stop: threading.Event | None, after: int) -> None:
        """Subscribes a stream under `key`, replacing any subscription that key already holds.

        Args:
            key    : Subscription key the forwarded events carry.
            stream : Stream to follow.
            stop   : Event ending the stream's tail on release, None for a job's main stream.
            after  : Last event id the viewer already holds, -1 to replay the whole buffer.
        """
        sink = ChannelSink(self, key)

        with self.lock:
            previous                = self.subscriptions.pop(key, None)
            self.subscriptions[key] = ChannelSubscription(stream, sink, stop)

        if previous is not None:
            previous.release()

        stream.attach(sink, after)

    def detach(self, key: str) -> bool:
        """Releases the subscription under `key`, returning whether there was one."""
        with self.lock:
            subscription = self.subscriptions.pop(key, None)

        if subscription is None:
            return False

        subscription.release()
        return True

    def prune(self) -> list[str]:
        """Releases every subscription whose stream has ended and returns their keys."""
        with self.lock:
            ended = [key for key, subscription in self.subscriptions.items() if subscription.sink.ended]
            gone  = [self.subscriptions.pop(key) for key in ended]

        for subscription in gone:
            subscription.release()

        return ended

    def close(self) -> None:
        """Releases every subscription and wakes the pump with the close sentinel."""
        with self.lock:
            subscriptions      = list(self.subscriptions.values())
            self.subscriptions = {}
            self.closed        = True

        for subscription in subscriptions:
            subscription.release()

        with self.offer_lock:
            try:
                self.events.put_nowait(self.CLOSE)
            except queue.Full:
                self._drain()
                self.events.put_nowait(self.CLOSE)


class StreamHub:
    """Registry of the open channels, attaching job streams to them on request.

    Attributes:
        logger   : Console logger handed to every channel.
        boot     : Token identifying this server process, so a page can tell a restart from a dropped connection.
        channels : Open channels keyed by channel id.
    """

    def __init__(self, logger: WebLogger) -> None:
        """Creates a hub with no channels."""
        self.logger   = logger
        self.boot     = uuid.uuid4().hex
        self.channels = {}
        self.lock     = threading.Lock()

    def open(self, channel_id: str) -> StreamChannel:
        """Opens a fresh channel under `channel_id`, closing the one a reconnecting page left behind.

        Args:
            channel_id : Identifier the page chose for its connection.

        Returns:
            The new, empty channel.
        """
        channel = StreamChannel(channel_id, self.logger)

        with self.lock:
            previous                  = self.channels.get(channel_id)
            self.channels[channel_id] = channel

        if previous is not None:
            previous.close()

        return channel

    def channel(self, channel_id: str) -> StreamChannel | None:
        """Returns the open channel under `channel_id`, or None."""
        with self.lock:
            return self.channels.get(channel_id)

    @staticmethod
    def key_of(job_id: str, unit: int | None) -> str:
        """Returns the subscription key of a job's main stream or of one of its units."""
        return job_id if unit is None else f"{job_id}/{unit}"

    def subscribe(self, channel_id: str, backend, job_id: str, unit: int | None, after: int) -> dict:
        """Attaches a job's main stream or one unit tail to a channel.

        A unit tail is a fresh stream on every subscription, so `after` only
        applies to a job's main stream and a unit always replays from its top.

        Args:
            channel_id : Channel the page opened.
            backend    : Job backend owning the job, local process manager or cluster manager.
            job_id     : Console job id.
            unit       : Unit index in the job's fan-out registry, None for the main stream.
            after      : Last event id the page already holds for the main stream, -1 for none.

        Returns:
            Dictionary with ``ok`` and the subscription ``key``; ``ok`` False with an
            ``error`` for an unknown channel (also flagged ``stale``), an unknown job or
            a unit that cannot be resolved.
        """
        channel = self.channel(channel_id)

        if channel is None:
            return {"ok": False, "error": "unknown channel", "stale": True}

        channel.prune()
        key = self.key_of(job_id, unit)

        if unit is None:
            stream = backend.get_stream(job_id)
            if stream is None:
                return {"ok": False, "error": "unknown job"}
            channel.attach(key, stream, None, after)
            return {"ok": True, "key": key}

        opened = backend.unit_stream(job_id, unit)
        if not opened.get("ok"):
            return opened

        channel.attach(key, opened["stream"], opened["stop"], -1)
        return {"ok": True, "key": key}

    def unsubscribe(self, channel_id: str, job_id: str, unit: int | None) -> dict:
        """Detaches a job's main stream or one unit tail from a channel.

        Args:
            channel_id : Channel the page opened.
            job_id     : Console job id.
            unit       : Unit index, None for the main stream.

        Returns:
            Dictionary with ``ok``, the ``key`` and whether the key was ``attached``;
            ``ok`` False with an ``error`` for an unknown channel (flagged ``stale``).
        """
        channel = self.channel(channel_id)

        if channel is None:
            return {"ok": False, "error": "unknown channel", "stale": True}

        key      = self.key_of(job_id, unit)
        attached = channel.detach(key)
        channel.prune()

        return {"ok": True, "key": key, "attached": attached}

    def release(self, channel: StreamChannel) -> None:
        """Closes a channel whose connection ended, unless a reconnect already replaced it."""
        with self.lock:
            current = self.channels.get(channel.channel_id) is channel
            if current:
                del self.channels[channel.channel_id]

        if current:
            channel.close()
