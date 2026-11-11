"""Per-page TomoVis sessions: one copied window, or the script figures, per browser page.

The store is a small LRU under a lock; every request on one entry holds the
entry's own lock, so the events of one page run strictly in order while other
pages proceed. Each window holds one cube, so the capacity bounds the memory
the TomoVis page can take on the console host.
"""

from __future__ import annotations

import secrets
import threading
from collections import OrderedDict

from tomovis.figure_host import TomoVisFigure
from tomovis.window      import TomoVisWindow
from web_logger          import WebLogger


class TomoVisSessionEntry:
    """One page session.

    Attributes:
        sid     : Session id (32 hex characters).
        kind    : "window" or "scripts".
        lock    : Serialises the requests of this page.
        window  : The TomoVis window, None for a scripts session.
        figures : Figure id to TomoVisFigure for figures outside the window (export window, script figure).
        scripts : Loaded script data keyed by script name.
    """

    def __init__(self, sid: str, kind: str, window: TomoVisWindow | None) -> None:
        """Creates the entry.

        Args:
            sid    : Session id.
            kind   : "window" or "scripts".
            window : The window of a window session.
        """

        self.sid     = sid
        self.kind    = kind
        self.lock    = threading.Lock()
        self.window  = window
        self.figures = {}
        self.scripts = {}

    def figure(self, name: str) -> TomoVisFigure:
        """Returns a figure of this session by id.

        Raises:
            KeyError : If the session has no figure with that id.
        """

        if self.window is not None and name in self.window.figures():
            return self.window.figures()[name]
        return self.figures[name]


class TomoVisSessions:
    """LRU store of page sessions.

    Attributes:
        CAPACITY : Default maximum number of live sessions.
        KINDS    : Session kinds the store opens.
        logger   : Console logger.
        capacity : Maximum number of live sessions of this store.
        entries  : Session id to entry, least recently used first.
        lock     : Guards ``entries``.
    """

    CAPACITY = 4
    KINDS    = ("window", "scripts")

    def __init__(self, logger: WebLogger, capacity: int = CAPACITY) -> None:
        """Creates an empty store.

        Args:
            logger   : Console logger.
            capacity : Maximum number of sessions kept.
        """

        self.logger   = logger
        self.capacity = capacity
        self.entries  = OrderedDict()
        self.lock     = threading.Lock()

    def create(self, kind: str, webgl2: bool) -> TomoVisSessionEntry:
        """Opens a session, dropping the least recently used one beyond the capacity.

        Args:
            kind   : "window" or "scripts".
            webgl2 : Whether the browser offers WebGL2 (the 3D tab exists).

        Returns:
            The new entry.

        Raises:
            ValueError : For an unknown kind.
        """

        if kind not in self.KINDS:
            raise ValueError(f"unknown session kind '{kind}'")

        sid    = secrets.token_hex(16)
        window = TomoVisWindow(self.logger, has3d=webgl2) if kind == "window" else None
        if window is not None:
            window.drain()
        entry = TomoVisSessionEntry(sid, kind, window)

        with self.lock:
            self.entries[sid] = entry
            while len(self.entries) > self.capacity:
                dropped, _ = self.entries.popitem(last=False)
                self.logger.info(f"TomoVis: closed the least recently used page session {dropped[:8]}")
        return entry

    def get(self, sid: str) -> TomoVisSessionEntry:
        """Returns a session and marks it most recently used.

        Raises:
            KeyError : If the session does not exist (closed or dropped).
        """

        with self.lock:
            entry = self.entries[sid]
            self.entries.move_to_end(sid)
            return entry

    def close(self, sid: str) -> None:
        """Drops a session; an unknown id is ignored, as a page may close twice."""

        with self.lock:
            self.entries.pop(sid, None)
