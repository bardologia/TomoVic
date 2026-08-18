"""Markdown metric table rendering with per-group best-value highlighting.

Used by the comparison reports that rank trials within families (for example
one Gaussian-order family or one multilook window) rather than globally.
"""

from __future__ import annotations

from typing import Callable, Hashable

from tools.reporting.markdown import MarkdownTable, ScalarFormatter
from tools.metrics.scoring    import FiniteScalar


class MetricTableRenderer:
    """Renders rows of metric-carrying objects into a markdown table."""

    DIRECTION_ARROW = {"higher": " ↑", "lower": " ↓", None: ""}

    @staticmethod
    def _best_values(rows: list, metric_columns: list, orientation: dict, group_of: Callable) -> dict:
        """Returns the extreme value per (group, metric) pair.

        Args:
            rows: Objects exposing a `metrics` mapping.
            metric_columns: (metric key, column label) pairs to scan.
            orientation: Maps a metric key to 'higher', 'lower', or None when
                the metric has no preferred direction.
            group_of: Maps a row to the group its best value is scoped to.

        Returns:
            Mapping from (group, metric key) to the best finite value found.
        """
        best: dict = {}

        for row in rows:
            group = group_of(row)
            for key, _ in metric_columns:
                direction = orientation.get(key)
                value     = FiniteScalar.coerce(row.metrics.get(key))

                if direction is None or value is None:
                    continue

                current = best.get((group, key))
                if current is None:
                    best[(group, key)] = value
                else:
                    best[(group, key)] = max(current, value) if direction == "higher" else min(current, value)

        return best

    @staticmethod
    def render(
        rows           : list,
        leading        : list[tuple[str, Callable]],
        metric_columns : list[tuple[str, str]],
        orientation    : dict,
        group_of       : Callable[[object], Hashable] | None = None,
        precision      : int = 4,
    ) -> list[str]:
        """Renders the table, bolding the best cell per metric within each group.

        Args:
            rows: Objects exposing a `metrics` mapping, one per table row.
            leading: (header, cell function) pairs for the non-metric columns.
            metric_columns: (metric key, column label) pairs for the metric columns.
            orientation: Maps a metric key to 'higher', 'lower', or None.
            group_of: Maps a row to the group its best value competes within;
                all rows share one group when omitted.
            precision: Number of significant digits used to format values.

        Returns:
            Markdown lines of the rendered table.
        """
        grouping = group_of if group_of is not None else (lambda row: 0)
        best     = MetricTableRenderer._best_values(rows, metric_columns, orientation, grouping)

        headers  = [header for header, _ in leading]
        headers += [f"{label}{MetricTableRenderer.DIRECTION_ARROW[orientation.get(key)]}" for key, label in metric_columns]

        table = MarkdownTable(headers)

        for row in rows:
            cells = [cell_fn(row) for _, cell_fn in leading]
            group = grouping(row)

            for key, _ in metric_columns:
                value  = row.metrics.get(key)
                cell   = ScalarFormatter.format_scalar(value, precision=precision)
                finite = FiniteScalar.coerce(value)
                mark   = best.get((group, key))

                if mark is not None and finite is not None and finite == mark:
                    cell = f"**{cell}**"

                cells.append(cell)

            table.add_row(*cells)

        return table.render()
