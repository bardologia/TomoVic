"""Tests covering the TensorBoard Tracker: step bookkeeping, scope tagging, scalar and histogram logging, and the null variant."""

from __future__ import annotations

import numpy as np
import pytest

from tools.monitoring.tracker import Tracker, NullTracker


class RecordingWriter:
    """TensorBoard writer stub capturing every write.

    Attributes:
        scalars: Tuples of (tag, value, step).
        histograms: Tuples of (tag, values array, step, bins).
        figures: Tuples of (tag, figure, step, close).
        flushed: Number of flush calls.
        closed: Number of close calls.
    """
    def __init__(self):
        """Creates the empty capture buffers and counters."""
        self.scalars    = []
        self.histograms = []
        self.figures    = []
        self.flushed    = 0
        self.closed     = 0

    def add_scalar(self, tag, value, step):
        """Records a scalar write."""
        self.scalars.append((tag, value, step))

    def add_histogram(self, tag, values, step, bins="auto"):
        """Records a histogram write, storing the values as an array."""
        self.histograms.append((tag, np.asarray(values), step, bins))

    def add_figure(self, tag, figure, step, close=True):
        """Records a figure write together with its close flag."""
        self.figures.append((tag, figure, step, close))

    def flush(self):
        """Counts a flush."""
        self.flushed += 1

    def close(self):
        """Counts a close."""
        self.closed += 1


def test_active_false_without_writer():
    """Verifies a tracker without a writer reports itself inactive."""
    assert Tracker().active is False


def test_active_true_with_writer():
    """Verifies a tracker holding a writer reports itself active."""
    assert Tracker(writer=RecordingWriter()).active is True


def test_set_step_and_advance():
    """Verifies set_step fixes the step and advance moves it by the given amount."""
    t = Tracker()
    t.set_step(10)

    assert t._step      == 10
    assert t.advance()  == 11
    assert t.advance(4) == 15
    assert t._step      == 15


def test_set_step_casts_to_int():
    """Verifies a float step is truncated to an integer."""
    t = Tracker()
    t.set_step(3.9)

    assert t._step == 3


def test_scope_nesting_and_tagging():
    """Verifies nested scopes prefix tags with slashes and unwind on exit."""
    t = Tracker()

    assert t._tag("x") == "x"

    with t.scope("a"):
        assert t._tag("x") == "a/x"
        with t.scope("b"):
            assert t._tag("x") == "a/b/x"
        assert t._tag("x") == "a/x"

    assert t._tag("x") == "x"
    assert t._scopes   == []


def test_scope_pops_on_exception():
    """Verifies a scope is popped even when the body raises."""
    t = Tracker()
    with pytest.raises(RuntimeError):
        with t.scope("a"):
            raise RuntimeError("boom")

    assert t._scopes == []


def test_resolve_step_default_and_override():
    """Verifies step resolution falls back to the current step unless one is passed."""
    t = Tracker()
    t.set_step(7)

    assert t._resolve(None) == 7
    assert t._resolve(2)    == 2


def test_log_scalar_records_exact_value():
    """Verifies a scalar reaches the writer with its tag, value, and current step."""
    w = RecordingWriter()
    t = Tracker(writer=w)
    t.set_step(3)
    t.log_scalar("loss", 0.5)

    assert w.scalars == [("loss", 0.5, 3)]


def test_log_scalar_casts_to_float():
    """Verifies integer scalars are cast to float before the write."""
    w = RecordingWriter()
    t = Tracker(writer=w)
    t.log_scalar("n", 4, step=1)

    tag, value, step = w.scalars[0]

    assert isinstance(value, float)
    assert value == 4.0


def test_log_scalar_explicit_step_overrides():
    """Verifies an explicit step wins over the tracker's current step."""
    w = RecordingWriter()
    t = Tracker(writer=w)
    t.set_step(100)
    t.log_scalar("m", 1.0, step=9)

    assert w.scalars[0] == ("m", 1.0, 9)


def test_log_scalar_uses_scope_in_tag():
    """Verifies the active scope is prefixed onto the scalar tag."""
    w = RecordingWriter()
    t = Tracker(writer=w)
    with t.scope("train"):
        t.log_scalar("loss", 0.2, step=0)

    assert w.scalars[0][0] == "train/loss"


def test_log_metrics_prefixes_and_records_all():
    """Verifies every metric in a batch is written under the shared prefix and step."""
    w = RecordingWriter()
    t = Tracker(writer=w)
    t.log_metrics("sys", {"a": 1.0, "b": 2.0}, step=5)

    recorded = {(tag, val) for tag, val, _ in w.scalars}

    assert ("sys/a", 1.0) in recorded
    assert ("sys/b", 2.0) in recorded
    assert all(step == 5 for _, _, step in w.scalars)


def test_log_metrics_skips_unconvertible():
    """Verifies metrics that cannot become floats are dropped instead of raising."""
    w = RecordingWriter()
    t = Tracker(writer=w)
    t.log_metrics("sys", {"good": 3.0, "bad": "not_a_number", "none": None}, step=0)

    tags = [tag for tag, _, _ in w.scalars]

    assert tags == ["sys/good"]


def test_log_histogram_records_float32_array():
    """Verifies histogram values are flattened to a float32 array with automatic binning."""
    w = RecordingWriter()
    t = Tracker(writer=w)
    t.log_histogram("weights", [[1, 2], [3, 4]], step=2)

    tag, values, step, bins = w.histograms[0]

    assert tag == "weights"
    assert values.dtype == np.float32
    assert values.tolist() == [1.0, 2.0, 3.0, 4.0]
    assert step == 2
    assert bins == "auto"


def test_log_figure_delegates_with_close():
    """Verifies figures are forwarded unchanged with the close flag set."""
    w = RecordingWriter()
    t = Tracker(writer=w)

    sentinel = object()
    t.log_figure("recon/px0", sentinel, step=4)

    tag, figure, step, close = w.figures[0]

    assert tag    == "recon/px0"
    assert figure is sentinel
    assert step   == 4
    assert close  is True


def test_inactive_tracker_records_nothing():
    """Verifies logging on a writer-less tracker is a silent no-op."""
    t = Tracker()
    t.log_scalar("loss", 1.0)
    t.log_metrics("sys", {"a": 1.0})
    t.log_histogram("h", [1, 2, 3])


def test_flush_and_close_delegate():
    """Verifies flush and close are forwarded to the writer once each."""
    w = RecordingWriter()
    t = Tracker(writer=w)
    t.flush()
    t.close()

    assert w.flushed == 1
    assert w.closed  == 1


def test_flush_and_close_noop_without_writer():
    """Verifies flush and close are safe without a writer."""
    t = Tracker()
    t.flush()
    t.close()


def test_null_tracker_is_inactive():
    """Verifies NullTracker is an inactive Tracker that accepts every call."""
    nt = NullTracker()

    assert nt.active is False
    assert isinstance(nt, Tracker)

    nt.log_scalar("x", 1.0)
    nt.flush()
    nt.close()
