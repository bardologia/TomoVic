"""Per-page TomoVis sessions: one copied window, or the script figures, per browser page.

A TomoVis window keeps its cube, ROI, plots and controls until the user
closes it, however many other windows open. The store therefore keeps a
session until its page closes it (the page's close beacon), and drops a
session only when its page has sent no request and no heartbeat for
``IDLE_LIMIT`` seconds, which happens only when the page is gone without
closing (a crashed or killed tab). An open page sends a heartbeat every
minute, also while it is hidden. Every request on one entry holds the
entry's own lock, so the events of one page run strictly in order while
other pages proceed. A closed or dropped session releases its window at once
instead of waiting for the cyclic garbage collector, because a window's
signal connections form reference cycles.
"""

from __future__ import annotations

import gc
import secrets
import threading
import time

from tomovis.figure_host import TomoVisFigure
from tomovis.window      import TomoVisConsole, TomoVisWindow
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
        seen    : time.monotonic() of the page's last request or heartbeat, in seconds.
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
        self.seen    = time.monotonic()

    def figure(self, name: str) -> TomoVisFigure:
        """Returns a figure of this session by id.

        Raises:
            KeyError : If the session has no figure with that id.
        """

        if self.window is not None and name in self.window.figures():
            return self.window.figures()[name]
        return self.figures[name]


class TomoVisSessions:
    """Store of page sessions, kept until their page closes or stops sending heartbeats.

    Attributes:
        IDLE_LIMIT : Default seconds without a request or heartbeat after which a session's page counts as gone.
        KINDS      : Session kinds the store opens.
        GL_OK      : has_usable_opengl()'s message for a usable context; WebGL2 is version 2.0 and has no profiles (QSurfaceFormat.NoProfile = 0).
        GL_FAILED  : has_usable_opengl()'s message when the context cannot be created.
        logger     : Console logger.
        idle_limit : Seconds without a request or heartbeat after which this store drops a session.
        entries    : Session id to entry.
        lock       : Guards ``entries``.
    """

    IDLE_LIMIT = 1200.0
    KINDS      = ("window", "scripts")
    GL_OK      = "OpenGL context OK, version=(2, 0), profile=0"
    GL_FAILED  = "QOpenGLContext.create() failed"

    def __init__(self, logger: WebLogger, idle_limit: float = IDLE_LIMIT) -> None:
        """Creates an empty store.

        Args:
            logger     : Console logger.
            idle_limit : Seconds without a request or heartbeat after which a session is dropped.
        """

        self.logger     = logger
        self.idle_limit = idle_limit
        self.entries    = {}
        self.lock       = threading.Lock()

    def printOpenGlCheck(self, webgl2: bool) -> None:
        """Prints has_usable_opengl()'s message as visualizer.py does when it is imported (F-153).

        The browser's WebGL2 probe stands in for the Qt offscreen context
        check, and every window session stands for one start of TomoVis.

        Args:
            webgl2 : Whether the browser could create a WebGL2 context.
        """

        TomoVisConsole(self.logger).print(self.GL_OK if webgl2 else self.GL_FAILED)

    def dropGone(self) -> list[TomoVisSessionEntry]:
        """Removes the sessions whose page sent nothing for longer than the idle limit; the caller holds ``lock``.

        Returns:
            The removed entries, which the caller releases once it has let go of ``lock``.
        """

        now  = time.monotonic()
        gone = [sid for sid, entry in self.entries.items() if now - entry.seen > self.idle_limit]
        for sid in gone:
            self.logger.info(f"TomoVis: closed the page session {sid[:8]}, whose page sent nothing for {self.idle_limit:.0f} s")
        return [self.entries.pop(sid) for sid in gone]

    def create(self, kind: str, webgl2: bool) -> TomoVisSessionEntry:
        """Opens a session after dropping the sessions whose page is gone.

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
        window = None
        if kind == "window":
            self.printOpenGlCheck(webgl2)
            window = TomoVisWindow(self.logger, has3d=webgl2)
            window.drain()
        entry = TomoVisSessionEntry(sid, kind, window)

        with self.lock:
            dropped           = self.dropGone()
            self.entries[sid] = entry

        for old in dropped:
            self.release(old)
        return entry

    def get(self, sid: str) -> TomoVisSessionEntry:
        """Returns a session and records that its page is alive.

        Raises:
            KeyError : If the session does not exist (closed or dropped).
        """

        with self.lock:
            entry      = self.entries[sid]
            entry.seen = time.monotonic()
            return entry

    def close(self, sid: str) -> None:
        """Drops a session and releases it; an unknown id is ignored, as a page may close twice."""

        with self.lock:
            entry = self.entries.pop(sid, None)
        if entry is not None:
            self.release(entry)

    def release(self, entry: TomoVisSessionEntry) -> None:
        """Frees a session that left the store: its window, figures and script data, then collects the cycles they formed.

        Runs outside the store lock. It waits for a request still running on
        the entry, so that request finishes with the window it started with.

        Args:
            entry : Entry already removed from ``entries``.
        """

        with entry.lock:
            entry.window = None
            entry.figures.clear()
            entry.scripts.clear()
        gc.collect()
