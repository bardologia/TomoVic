"""Builders for the Markdown reports emitted by inference and comparison runs.

Provides scalar formatting, a column-aligned pipe-table builder and a document
accumulator covering headings, paragraphs, key-value tables and images.
"""

from __future__ import annotations

import math

from pathlib import Path
from typing  import Any, Iterable, Mapping, Optional, Sequence


class ScalarFormatter:
    """Renders metric values as compact table cells.

    Attributes:
        EMPTY: Placeholder written in place of a missing value.
    """

    EMPTY = "—"

    @staticmethod
    def format_scalar(value: Any, precision: int = 5, adaptive: bool = False, empty: str = EMPTY) -> str:
        """Renders a scalar, sequence or None as a table cell.

        Args:
            value: Value to render; sequences are joined with commas.
            precision: Significant digits used for floats.
            adaptive: Switches floats to scientific notation outside [1e-3, 1e4).
            empty: String returned when value is None.

        Returns:
            The rendered cell text.
        """
        if value is None:
            return empty

        if isinstance(value, float):
            if adaptive and (abs(value) >= 1e4 or 0 < abs(value) < 1e-3):
                return f"{value:.4e}"
            return f"{value:.{precision}g}"

        if isinstance(value, (list, tuple)):
            return ", ".join(str(x) for x in value)

        return str(value)

    @staticmethod
    def with_std(cell: str, std: float | None) -> str:
        """Appends a '± std' term to a cell, or returns it unchanged when std is absent."""
        if std is None or not math.isfinite(std):
            return cell

        return f"{cell} ± {ScalarFormatter.format_scalar(std)}"


class MarkdownTable:
    """Accumulates rows and renders them as a width-aligned Markdown pipe table.

    Attributes:
        columns: Header labels.
        align: Per-column alignment, one of left, center or right.
        rows: Rendered cell strings, one list per row.
        EMPTY: Placeholder written for missing cells.
    """

    EMPTY = "—"

    def __init__(self, columns: Sequence[Any], align: Optional[Sequence[str]] = None) -> None:
        """Initializes an empty table.

        Args:
            columns: Header labels, stringified.
            align: Per-column alignment; defaults to left for every column.
        """
        self.columns = [str(c) for c in columns]
        self.align   = list(align) if align is not None else ["left"] * len(self.columns)
        self.rows    = []

    def add_row(self, *cells: Any) -> "MarkdownTable":
        """Appends one row, padding short rows and rendering None as the placeholder.

        Args:
            *cells: Cell values in column order; missing trailing cells are padded.

        Returns:
            This table, for chaining.
        """
        padded = list(cells) + [None] * (len(self.columns) - len(cells))
        self.rows.append([self.EMPTY if c is None else str(c) for c in padded])
        return self

    def add_rows(self, rows: Iterable[Sequence[Any]]) -> "MarkdownTable":
        """Appends several rows and returns this table, for chaining."""
        for row in rows:
            self.add_row(*row)
        return self

    def is_empty(self) -> bool:
        """Returns whether no rows have been added yet."""
        return not self.rows

    def _widths(self) -> list[int]:
        """Returns the per-column character widths, at least three each."""
        widths = [max(3, len(c)) for c in self.columns]
        for row in self.rows:
            widths = [max(w, len(cell)) for w, cell in zip(widths, row)]
        return widths

    def _separator(self, width: int, align: str) -> str:
        """Returns the dash rule for one column, carrying its alignment colons."""
        if align == "right":
            return "-" * (width - 1) + ":"
        if align == "center":
            return ":" + "-" * (width - 2) + ":"
        return "-" * width

    def _aligned(self, cell: str, width: int, align: str) -> str:
        """Returns the cell padded to width under the given alignment."""
        if align == "right":
            return f"{cell:>{width}}"
        if align == "center":
            return f"{cell:^{width}}"
        return f"{cell:<{width}}"

    def _row_line(self, cells: Sequence[str], widths: Sequence[int]) -> str:
        """Returns one pipe-delimited table line built from padded cells."""
        body = " | ".join(self._aligned(c, w, a) for c, w, a in zip(cells, widths, self.align))
        return f"| {body} |"

    def render(self) -> list[str]:
        """Returns the header, separator and body lines of the table."""
        widths    = self._widths()
        separator = "| " + " | ".join(self._separator(w, a) for w, a in zip(widths, self.align)) + " |"

        lines  = [self._row_line(self.columns, widths), separator]
        lines += [self._row_line(row, widths) for row in self.rows]
        return lines


class MarkdownDoc:
    """Accumulates Markdown lines into a document that can be rendered or saved.

    Attributes:
        lines: Markdown lines gathered so far.
    """

    def __init__(self, title: Optional[str] = None) -> None:
        """Initializes an empty document, optionally opening with a level-1 heading."""
        self.lines: list[str] = []
        if title is not None:
            self.heading(title, level=1)

    def heading(self, text: str, level: int = 1) -> "MarkdownDoc":
        """Appends a heading at the given level and returns this document, for chaining."""
        if self.lines:
            self.lines.append("")
        self.lines.append(f"{'#' * level} {text}")
        self.lines.append("")
        return self

    def paragraph(self, text: str) -> "MarkdownDoc":
        """Appends a paragraph followed by a blank line and returns this document."""
        self.lines.append(str(text))
        self.lines.append("")
        return self

    def raw(self, text: str) -> "MarkdownDoc":
        """Appends a line verbatim, with no trailing blank line, and returns this document."""
        self.lines.append(str(text))
        return self

    def blank(self) -> "MarkdownDoc":
        """Appends a blank line and returns this document, for chaining."""
        self.lines.append("")
        return self

    def bold_kv(self, key: str, value: Any) -> "MarkdownDoc":
        """Appends a bold key with its code-formatted value and returns this document."""
        self.lines.append(f"**{key}:** `{value}`")
        return self

    def kv_table(self, items: Mapping[str, Any] | Iterable[tuple], header: Sequence[str] = ("Key", "Value"), code_keys: bool = True) -> "MarkdownDoc":
        """Appends a two-column table built from key-value pairs.

        Args:
            items: Mapping or iterable of (key, value) pairs.
            header: Column labels for the key and value columns.
            code_keys: Wraps each key in backticks when True.

        Returns:
            This document, for chaining.
        """
        table = MarkdownTable(header)
        pairs = items.items() if isinstance(items, Mapping) else items

        for k, v in pairs:
            key = f"`{k}`" if code_keys else str(k)
            table.add_row(key, v)

        return self.table(table)

    def table(self, table: MarkdownTable) -> "MarkdownDoc":
        """Appends a rendered table plus a blank line and returns this document."""
        self.lines.extend(table.render())
        self.lines.append("")
        return self

    def image(self, alt: str, path: Any) -> "MarkdownDoc":
        """Appends an image reference with alt text and returns this document."""
        self.lines.append(f"![{alt}]({path})")
        self.lines.append("")
        return self

    def render(self) -> str:
        """Returns the document as one right-stripped string ending in a newline."""
        return "\n".join(self.lines).rstrip() + "\n"

    def save(self, path: Any) -> Path:
        """Writes the rendered document as UTF-8, creating parents, and returns the path."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.render(), encoding="utf-8")
        return path
