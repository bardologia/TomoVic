"""Coloured timestamped console logger for the web UI server."""

from __future__ import annotations

import sys
import threading
from collections import deque
from datetime    import datetime


class WebLogger:
    """Prints levelled, timestamped console lines with optional ANSI colour.

    Every line is also kept in a bounded in-memory ring so the browser can show
    the server's own log without access to the terminal it runs in.

    Attributes:
        name    : Logger name kept for identification by the owning component.
        enabled : Whether ANSI colour codes are emitted, true only on a TTY.
        ring    : Recent log records, oldest first, capped at RING_LIMIT.
        lock    : Guards the ring against concurrent writers and readers.
    """


    COLORS = {
        "INFO"  : "\033[36m",
        "OK"    : "\033[32m",
        "WARN"  : "\033[33m",
        "ERROR" : "\033[31m",
        "MUTED" : "\033[90m",
    }
    RESET      = "\033[0m"
    RING_LIMIT = 400

    def __init__(self, name: str = "webui") -> None:
        """Stores the logger name and enables colour only when stdout is a TTY.

        Args:
            name : Identifier of the component owning this logger.
        """

        self.name    = name
        self.enabled = sys.stdout.isatty()
        self.ring    = deque(maxlen=self.RING_LIMIT)
        self.lock    = threading.Lock()

    def recent(self, limit: int = 200) -> list[dict]:
        """Returns the newest ring records, oldest first.

        Args:
            limit : Maximum number of records to return.

        Returns:
            Records with "time" (HH:MM:SS), "level" and "message" keys.
        """

        with self.lock:
            records = list(self.ring)
        return records[-max(1, limit):]

    def _emit(self, level: str, message: str) -> None:
        """Prints one timestamped line at the given level and records it in the ring.

        Args:
            level   : Level key selecting the colour, printed in the line prefix.
            message : Text appended after the prefix.
        """

        stamp = datetime.now().strftime("%H:%M:%S")
        color = self.COLORS.get(level, "") if self.enabled else ""
        reset = self.RESET if self.enabled else ""
        line  = f"{color}[{stamp}] {level:<5}{reset} {message}"

        with self.lock:
            self.ring.append({"time": stamp, "level": level, "message": message})

        print(line, flush=True)

    def info(self, message: str) -> None:
        """Logs an informational message."""

        self._emit("INFO", message)

    def ok(self, message: str) -> None:
        """Logs a success message."""

        self._emit("OK", message)

    def warning(self, message: str) -> None:
        """Logs a warning message."""

        self._emit("WARN", message)

    def error(self, message: str) -> None:
        """Logs an error message."""

        self._emit("ERROR", message)

    def muted(self, message: str) -> None:
        """Logs a de-emphasised message."""

        self._emit("MUTED", message)

    def banner(self, title: str, lines: list[str]) -> None:
        """Prints a titled banner followed by one info line per entry.

        Args:
            title : Banner heading placed between the rules.
            lines : Detail lines printed below the banner.
        """

        width = max([len(title)] + [len(item) for item in lines]) + 4
        bar   = "=" * width
        self._emit("OK", bar)
        self._emit("OK", f"  {title}")
        self._emit("OK", bar)
        for item in lines:
            self._emit("INFO", f"  {item}")
