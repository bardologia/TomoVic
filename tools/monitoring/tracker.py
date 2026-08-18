"""Thin wrapper around a TensorBoard writer with scoped tags and a global step.

Provides scalar, metric-group, figure, histogram and CUDA-memory logging that
degrades to a no-op when no writer is attached, so callers need no branching.
"""

from __future__ import annotations

from contextlib import contextmanager
from typing     import Any, Mapping, Optional

import numpy as np
import torch


class Tracker:
    """Logs training telemetry to a TensorBoard writer under nestable tag scopes.

    Attributes:
        writer: SummaryWriter-like object, or None to disable all logging.
        debug: Flag reserved for verbose logging behaviour by callers.
    """

    def __init__(self, writer=None, debug: bool = False) -> None:
        """Initializes the tracker with an optional writer, step 0 and no scopes.

        Args:
            writer: SummaryWriter-like object exposing add_scalar, add_figure,
                add_histogram, flush and close; None disables logging.
            debug: Debug flag stored for callers to consult.
        """
        self.writer  = writer
        self.debug   = debug
        self._step   = 0
        self._scopes = []

    @property
    def active(self) -> bool:
        """Whether a writer is attached and logging calls will reach TensorBoard."""
        return self.writer is not None

    def set_step(self, step: int) -> None:
        """Sets the global step used when a logging call omits one."""
        self._step = int(step)

    def advance(self, n: int = 1) -> int:
        """Advances the global step by n and returns the new value."""
        self._step += n
        return self._step

    @contextmanager
    def scope(self, name: str):
        """Yields this tracker with name pushed as a slash-separated tag prefix.

        Args:
            name: Prefix segment prepended to every tag logged inside the block.

        Yields:
            This tracker, so logging calls inside the block inherit the prefix.
        """
        self._scopes.append(str(name))
        try:
            yield self
        finally:
            self._scopes.pop()

    def _tag(self, tag: str) -> str:
        """Returns the tag joined to the active scope stack with slashes."""
        return "/".join([*self._scopes, str(tag)])

    def _resolve(self, step: Optional[int]) -> int:
        """Returns the explicit step when given, otherwise the tracker's global step."""
        return self._step if step is None else int(step)

    def _emit(self, method: str, tag: str, payload: Any, step: Optional[int], **kwargs: Any) -> None:
        """Forwards a scoped, step-resolved payload to the named writer method."""
        if self.writer is None:
            return
        getattr(self.writer, method)(self._tag(tag), payload, self._resolve(step), **kwargs)

    def log_scalar(self, tag, value, step=None) -> None:
        """Logs one scalar under the scoped tag.

        Args:
            tag: Tag suffix appended to the active scope.
            value: Value coerced to float before writing.
            step: Step to log at; defaults to the tracker's global step.
        """
        self._emit("add_scalar", tag, float(value), step)

    def log_metrics(self, prefix, values: Mapping[str, Any], step=None) -> None:
        """Logs every float-convertible entry of a mapping under 'prefix/key'.

        Args:
            prefix: Group name placed before each key.
            values: Mapping of metric name to value; entries that do not convert
                to float are skipped.
            step: Step to log at; defaults to the tracker's global step.
        """
        for k, v in values.items():
            try:
                self._emit("add_scalar", f"{prefix}/{k}", float(v), step)
            except (TypeError, ValueError):
                continue

    def log_staged(self, group, values: Mapping[str, Any], stage, step=None) -> None:
        """Logs a mapping under 'group/key/stage' so stages share a chart per key.

        Args:
            group: Group name placed first in the tag.
            values: Mapping of metric name to value; non-numeric entries are skipped.
            stage: Stage name placed last in the tag, such as train or val.
            step: Step to log at; defaults to the tracker's global step.
        """
        for k, v in values.items():
            try:
                self._emit("add_scalar", f"{group}/{k}/{stage}", float(v), step)
            except (TypeError, ValueError):
                continue

    def log_figure(self, tag, figure, step=None) -> None:
        """Logs a matplotlib figure under the scoped tag and closes it."""
        self._emit("add_figure", tag, figure, step, close=True)

    def log_histogram(self, tag, values, step=None, bins="auto") -> None:
        """Logs a histogram of an array-like, ignoring writer-side binning failures.

        Args:
            tag: Tag suffix appended to the active scope.
            values: Array-like of any shape; flattened and cast to float32.
            step: Step to log at; defaults to the tracker's global step.
            bins: Binning strategy forwarded to the writer.
        """
        v = np.asarray(values).ravel().astype(np.float32)
        try:
            self._emit("add_histogram", tag, v, step, bins=bins)
        except (ValueError, RuntimeError):
            pass

    def log_memory(self, step=None, device=None) -> None:
        """Logs peak CUDA allocated memory in GB, or does nothing without CUDA.

        Args:
            step: Step to log at; defaults to the tracker's global step.
            device: CUDA device to query; defaults to the current device.
        """
        if self.writer is None or not torch.cuda.is_available():
            return

        dev = device if device is not None else torch.cuda.current_device()
        self.log_scalar("system/gpu_peak_alloc_gb", torch.cuda.max_memory_allocated(dev) / 1024 ** 3, step)

    def flush(self) -> None:
        """Flushes the writer's pending events when one is attached."""
        if self.writer is not None:
            self.writer.flush()

    def close(self) -> None:
        """Closes the writer when one is attached."""
        if self.writer is not None:
            self.writer.close()


class NullTracker(Tracker):
    """Tracker with no writer, so every logging call is a no-op."""

    def __init__(self, debug: bool = False) -> None:
        """Initializes a tracker whose writer is permanently None."""
        super().__init__(writer=None, debug=debug)
