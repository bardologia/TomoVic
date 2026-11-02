"""Tests for the sequential session scheduler's per-session completion reporting."""

from __future__ import annotations

import pytest

from pipelines.shared.orchestration.session_scheduler import SequentialSessionScheduler

from tests.conftest import RecordingLogger


class EchoSession:
    """Picklable session runner returning one output path per session, failing on the session named 'broken'."""

    def __call__(self, session: str) -> dict:
        """Returns the session's output mapping, or raises for the broken session."""
        if session == "broken":
            raise RuntimeError("session broken failed")

        return {"report": f"/out/{session}/report.md"}


class EchoScheduler(SequentialSessionScheduler):
    """Scheduler over a fixed list of named sessions."""

    def __init__(self, logger, sessions: list[str]) -> None:
        """Stores the sessions to dispatch."""
        super().__init__(logger)
        self.planned = sessions

    def _sessions(self) -> list:
        """Returns the fixed session names."""
        return self.planned

    def _session_runner(self):
        """Returns the picklable echo runner."""
        return EchoSession()

    def _result_key(self, session) -> str:
        """Keys each result by the session name."""
        return session

    def _completion_message(self, session) -> str:
        """Names the finished session."""
        return f"[Session] {session} completed"


def test_each_session_is_reported_when_it_finishes_with_its_own_duration():
    """Every session's completion line and outputs table follow its own job line, carry no section timing and name the session's duration."""
    logger  = RecordingLogger()
    results = EchoScheduler(logger, ["a", "b"]).run()

    lines = [message for level, message in logger.messages if level == "subsection"]

    assert results == {"a": {"report": "/out/a/report.md"}, "b": {"report": "/out/b/report.md"}}
    assert [level for level, _ in logger.messages if level == "section"] == []
    assert lines[1].startswith("Job a completed")
    assert lines[2].startswith("[Session] a completed in ")
    assert lines[3].startswith("Job b completed")
    assert lines[4].startswith("[Session] b completed in ")


def test_outputs_of_finished_sessions_are_logged_before_a_later_session_fails():
    """A session that raises stops the run, but the session finished before it has already been reported."""
    logger = RecordingLogger()

    with pytest.raises(RuntimeError, match="session broken failed"):
        EchoScheduler(logger, ["a", "broken"]).run()

    assert any(level == "subsection" and message.startswith("[Session] a completed in ") for level, message in logger.messages)
