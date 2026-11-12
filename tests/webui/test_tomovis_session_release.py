"""Tests that a TomoVis page session frees its window as soon as it leaves the store.

A window's Qt stand-in signals form reference cycles, so without an explicit
release the cube stays in memory until the cyclic garbage collector runs. Both
ways a session leaves the store, ``close`` and the LRU drop in ``create``, must
free the window before they return, without the test calling ``gc`` itself.
"""

from __future__ import annotations

import weakref

import numpy as np

from tests.webui.conftest  import REPO_ROOT
from tomovis.session_store import TomoVisSessions
from web_logger            import WebLogger

INPUTS = REPO_ROOT / "tests" / "webui" / "fixtures" / "tomovis" / "inputs"


class LoadedSession:
    """Opens a window session and imports a cube into it, as the page does."""

    def __init__(self, sessions: TomoVisSessions) -> None:
        """Opens the session and imports npy_real.npy through File > Import > npy.

        Args:
            sessions : Store the session is opened in.
        """

        self.entry = sessions.create("window", True)
        window     = self.entry.window
        window.handle({"type": "trigger", "widget": "openNpy"})
        token = window.dialogs.pendingToken()
        window.drain()
        window.handle({"type": "dialog_result", "token": token, "accepted": True, "path": str(INPUTS / "npy_real.npy")})
        window.drain()

    def references(self) -> tuple[weakref.ref, weakref.ref]:
        """Returns weak references to the window and to its cube."""

        return weakref.ref(self.entry.window), weakref.ref(self.entry.window.data)


def test_close_releases_the_window_at_once():
    """After close() the window and its cube are gone and the entry holds no window."""

    sessions      = TomoVisSessions(WebLogger("release-test"))
    loaded        = LoadedSession(sessions)
    window, cube  = loaded.references()

    assert isinstance(cube(), np.ndarray)
    sessions.close(loaded.entry.sid)

    assert window() is None and cube() is None
    assert loaded.entry.window is None and loaded.entry.figures == {}


def test_the_lru_drop_releases_the_oldest_window_at_once():
    """Opening one session beyond the capacity frees the least recently used window before create() returns."""

    sessions     = TomoVisSessions(WebLogger("release-test"), capacity=1)
    loaded       = LoadedSession(sessions)
    window, cube = loaded.references()

    newer = sessions.create("window", True)

    assert window() is None and cube() is None
    assert loaded.entry.window is None
    assert newer.window is not None and list(sessions.entries) == [newer.sid]


def test_closing_twice_is_harmless():
    """A page that closes twice (pagehide after an explicit close) is answered without error."""

    sessions = TomoVisSessions(WebLogger("release-test"))
    loaded   = LoadedSession(sessions)

    sessions.close(loaded.entry.sid)
    sessions.close(loaded.entry.sid)

    assert sessions.entries == {}
