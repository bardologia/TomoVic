"""Watch of the TomoVis router that reports every successful TomoVis import to the bridge.

The router calls ``before`` ahead of a window event and ``observe`` right after
the window drained, still under the page's lock. A file dialog of an import is
remembered when its request is drained; when a later ``dialog_result`` answers
that request, the window holds a new cube and no "Import error" or "Open
error" box came out, the import succeeded and the bridge registers it. No
TomoVis code changes for this.
"""

from __future__ import annotations

import traceback
from pathlib import Path

from bridge.dataset_bridge import DatasetBridge
from lru_cache             import LruCache
from web_logger            import WebLogger


class TomoVisImportWatch:
    """Detects successful TomoVis imports from the window events.

    Attributes:
        bridge         : Dataset bridge receiving the imports.
        logger         : Console logger.
        requests       : TomoVis window sid to {token, kind} of its last file request, None after a request that is not an import.
        FILTER_KINDS   : Name filter of an open-mode file dialog to the import kind it belongs to.
        FAILURE_TITLES : Titles of the critical boxes TomoVis shows when an import or a session open failed.
        CAPACITY       : Number of windows whose last file request is remembered.
    """

    FILTER_KINDS   = {"FuSAR Tomo (*.hd5)": "hd5", "UAVSAR Tomo (*.h5)": "h5", "Numpy (*.npy)": "npy", "RAT file (*.rat)": "rat", "Visualizer (*.hd5)": "session"}
    FAILURE_TITLES = ("Import error", "Open error")
    CAPACITY       = 64

    def __init__(self, bridge: DatasetBridge, logger: WebLogger) -> None:
        """Stores the bridge.

        Args:
            bridge : Dataset bridge.
            logger : Console logger.
        """

        self.bridge   = bridge
        self.logger   = logger
        self.requests = LruCache(self.CAPACITY)

    def before(self, window) -> object:
        """Returns the cube the window holds before an event, compared by identity afterwards.

        Args:
            window : The TomoVis window.

        Returns:
            ``window.data``.
        """

        return window.data

    def answered(self, sid: str, event, before, window, dialogs: list) -> tuple[str, str] | None:
        """Says whether an event completed an import.

        Args:
            sid     : TomoVis window session id.
            event   : The event the window handled.
            before  : ``window.data`` before the event.
            window  : The TomoVis window.
            dialogs : Dialog requests the event produced.

        Returns:
            (kind, path) of a successful import, None otherwise.
        """

        if not isinstance(event, dict) or event.get("type") != "dialog_result":
            return None

        request = self.requests.get(sid)
        if request is None or request["token"] != event.get("token"):
            return None
        self.requests.put(sid, None)

        if event.get("accepted") is not True or not isinstance(event.get("path"), str) or not event["path"]:
            return None
        if window.data is None or window.data is before:
            return None
        if any(dialog["kind"] == "message" and dialog["level"] == "critical" and dialog["title"] in self.FAILURE_TITLES for dialog in dialogs):
            return None
        return request["kind"], event["path"]

    def remember(self, sid: str, dialogs: list) -> None:
        """Records the file requests an event produced; the latest per window wins.

        Args:
            sid     : TomoVis window session id.
            dialogs : Dialog requests the event produced.
        """

        for dialog in dialogs:
            if "token" not in dialog:
                continue
            kind = None
            if dialog["kind"] == "file" and dialog["mode"] == "open" and dialog["filters"] and dialog["filters"][0] in self.FILTER_KINDS:
                kind = self.FILTER_KINDS[dialog["filters"][0]]
            self.requests.put(sid, None if kind is None else {"token": dialog["token"], "kind": kind})

    def observe(self, sid: str, event, before, window, dialogs: list) -> None:
        """Reports a successful import to the bridge, then remembers the file requests of this event.

        A registration error never breaks the TomoVis answer: it is logged with
        its traceback and kept as the bridge's ``bridge_error``, which GET
        current returns and the pages show.

        Args:
            sid     : TomoVis window session id.
            event   : The event the window handled.
            before  : ``window.data`` before the event.
            window  : The TomoVis window.
            dialogs : Dialog requests the event produced.
        """

        imported = self.answered(sid, event, before, window, dialogs)
        if imported is not None:
            kind, path = imported
            try:
                self.bridge.tomovis_imported(sid, kind, path)
            except Exception as error:
                self.logger.error(f"bridge: registering the TomoVis import {path} failed: {error}\n{traceback.format_exc()}")
                self.bridge.bridge_error = f"TomoVis opened {Path(path).name}, but the TomoVic tools could not take it: {error}"

        self.remember(sid, dialogs)
