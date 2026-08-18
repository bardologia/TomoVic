"""Scalar coercion guards and scoring helpers for reported metrics.

Provides the guards that keep non-numeric or non-finite entries out of the
metric tables and the coefficient of determination used by the parameter
extraction metrics.
"""

from __future__ import annotations

import math
import numbers

from typing import Any

import numpy as np


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


class R2:
    """Coefficient of determination computed along one axis."""

    EPSILON = 1e-12

    @staticmethod
    def pixel_map(pred: np.ndarray, ref: np.ndarray, axis: int) -> np.ndarray:
        """Returns the per-pixel coefficient of determination of a prediction.

        Args:
            pred: Predicted values with the reduced dimension along axis.
            ref: Reference values of the same shape.
            axis: Dimension the residual and total sums are taken over, usually
                the elevation axis of a profile stack.

        Returns:
            Float32 array with axis removed, holding 1 - SS_res / SS_tot.
        """
        ref_mean = ref.mean(axis=axis, keepdims=True, dtype=np.float64)

        ss_res = ((pred - ref) ** 2).sum(axis=axis, dtype=np.float64)
        ss_tot = ((ref - ref_mean) ** 2).sum(axis=axis, dtype=np.float64)

        return (1.0 - ss_res / (ss_tot + R2.EPSILON)).astype(np.float32)
