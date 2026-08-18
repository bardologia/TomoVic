"""Scalar coercion guards for reported metrics.

Provides the guards that keep non-numeric or non-finite entries out of the
metric tables.
"""

from __future__ import annotations

import math
import numbers

from typing import Any


class FiniteScalar:
    """Guards that admit only finite real numbers into metric computations."""

    @staticmethod
    def is_finite_number(value: Any) -> bool:
        """Returns whether a value is a finite real number, excluding booleans."""
        if isinstance(value, bool):
            return False
        if not isinstance(value, numbers.Real):
            return False
        return math.isfinite(float(value))

    @staticmethod
    def coerce(value: Any) -> float | None:
        """Returns the value as a float, or None when it is not a finite real number."""
        if FiniteScalar.is_finite_number(value):
            return float(value)
        return None
