"""Flattening of ANSI terminal output into plain scrollback text.

Replays the cursor movement and erase sequences emitted by Rich progress
displays so a captured log file can be rendered as static text in the web UI.
"""

from __future__ import annotations

import re


class AnsiTranscript:
    """Virtual terminal screen that replays ANSI escapes into plain lines.

    Attributes:
        lines: Screen buffer, one list of single characters per row.
        row: Zero-based index of the row the cursor sits on.
        col: Zero-based column the cursor sits on within the current row.
    """

    CSI  = re.compile(r"\x1b\[([0-9;:?]*)[ -/]*([@-~])")
    OSC  = re.compile(r"\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)")
    LONE = re.compile(r"\x1b[@-Z\\-_]")
    MOVE = re.compile(r"\x1b\[[0-9;:?]*[ -/]*[@-GJK]")
    CTRL = re.compile(r"[\x00-\x09\x0b-\x1f]")

    def __init__(self) -> None:
        """Creates an empty one-row screen with the cursor at the origin."""
        self.lines = [[]]
        self.row   = 0
        self.col   = 0

    def _put(self, run: str) -> None:
        """Writes printable text at the cursor, honouring newline, return and tab."""
        for char in run:
            if char == "\n":
                self.row += 1
                self.col  = 0
                while len(self.lines) <= self.row:
                    self.lines.append([])
            elif char == "\r":
                self.col = 0
            elif char == "\t":
                self.col += 8 - (self.col % 8)
            elif ord(char) >= 32:
                line = self.lines[self.row]
                while len(line) < self.col:
                    line.append(" ")
                if self.col < len(line):
                    line[self.col] = char
                else:
                    line.append(char)
                self.col += 1

    def _count(self, params: str, default: int = 1) -> int:
        """Returns the first numeric escape parameter, or ``default`` when absent."""
        head = params.split(";")[0]
        return int(head) if head.isdigit() else default

    def _erase_line(self, params: str) -> None:
        """Applies an EL erase to the current row: to end, to start, or whole line."""
        mode = self._count(params, 0)
        line = self.lines[self.row]

        if mode == 0:
            del line[self.col :]
        elif mode == 1:
            for index in range(min(self.col + 1, len(line))):
                line[index] = " "
        else:
            line.clear()

    def _erase_display(self, params: str) -> None:
        """Applies an ED erase: below the cursor for mode 0, otherwise full reset."""
        mode = self._count(params, 0)

        if mode == 0:
            del self.lines[self.row + 1 :]
            del self.lines[self.row][self.col :]
            return

        self.lines = [[]]
        self.row   = 0
        self.col   = 0

    def _move(self, params: str, final: str) -> None:
        """Moves the cursor for the CUU/CUD/CUF/CUB/CNL/CPL/CHA escape ``final``."""
        count = self._count(params)

        if final == "A":
            self.row = max(0, self.row - count)
        elif final in ("B", "E"):
            self.row += count
            while len(self.lines) <= self.row:
                self.lines.append([])
        elif final == "C":
            self.col += count
        elif final == "D":
            self.col = max(0, self.col - count)
        elif final == "F":
            self.row = max(0, self.row - count)

        if final in ("E", "F"):
            self.col = 0
        elif final == "G":
            self.col = max(0, self._count(params) - 1)

    def _control(self, params: str, final: str) -> None:
        """Dispatches one CSI sequence to erase or cursor handling, ignoring private modes."""
        if params.startswith("?"):
            return

        if final == "K":
            self._erase_line(params)
        elif final == "J":
            self._erase_display(params)
        elif final in ("A", "B", "C", "D", "E", "F", "G"):
            self._move(params, final)

    def _colours_only(self, text: str) -> str | None:
        """Returns the stripped text when it carries only colour escapes, else ``None``."""
        if self.MOVE.search(text) is not None:
            return None

        plain = self.CSI.sub("", text)
        if self.CTRL.search(plain) is not None:
            return None

        return "\n".join(line.rstrip() for line in plain.split("\n"))

    def flatten(self, text: str) -> str:
        """Returns ``text`` rendered as plain scrollback with escape sequences applied.

        Colour-only input is stripped directly; input containing cursor motion or
        erase sequences is replayed onto the screen buffer first.

        Args:
            text: Raw terminal output, possibly containing ANSI escape sequences.

        Returns:
            Newline-joined plain text with trailing whitespace removed per line.
        """
        text  = self.LONE.sub("", self.OSC.sub("", text))
        plain = self._colours_only(text)

        if plain is not None:
            return plain

        cursor = 0

        for match in self.CSI.finditer(text):
            self._put(text[cursor : match.start()])
            self._control(match.group(1), match.group(2))
            cursor = match.end()

        self._put(text[cursor:])

        return "\n".join("".join(line).rstrip() for line in self.lines)
