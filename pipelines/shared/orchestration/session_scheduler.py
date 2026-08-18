"""Base scheduler that dispatches pipeline sessions one at a time.

Subclasses supply the session list, the callable that executes one session and
the labels used for result keys and log messages; the base class runs them
through a single-worker process pool and reports the collected outputs.
"""

from __future__ import annotations

from tools.monitoring.logger  import Logger
from tools.orchestration.pool import ProcessPoolRunner


class SequentialSessionScheduler:
    """Runs subclass-defined sessions sequentially in a one-worker pool.

    Attributes:
        EMPTY_MESSAGE: Error text raised when no session is planned, or None to
            allow an empty run.
        SESSION_NOUN: Plural noun used in the dispatch log line.
        logger: Logger receiving the dispatch and completion output.
    """

    EMPTY_MESSAGE : str | None = None
    SESSION_NOUN  : str        = "sessions"

    def __init__(self, logger: Logger) -> None:
        """Stores the logger used for dispatch and completion reporting."""
        self.logger = logger

    def _sessions(self) -> list:
        """Returns the sessions to dispatch; implemented by subclasses."""
        raise NotImplementedError

    def _session_runner(self):
        """Returns the callable executing one session; implemented by subclasses."""
        raise NotImplementedError

    def _result_key(self, session) -> str:
        """Returns the result-dict key for a session; implemented by subclasses."""
        raise NotImplementedError

    def _completion_message(self, session) -> str:
        """Returns the section title logged when a session finishes."""
        raise NotImplementedError

    def _outputs_table(self, outputs: dict) -> dict:
        """Returns the session outputs with paths stringified for logging."""
        return {name: str(path) for name, path in outputs.items()}

    def run(self) -> dict:
        """Dispatches every session sequentially and collects their outputs.

        Returns:
            Mapping from each session's result key to the outputs dict its
            runner produced.

        Raises:
            RuntimeError: If no session is planned and EMPTY_MESSAGE is set.
        """
        sessions = self._sessions()
        if not sessions and self.EMPTY_MESSAGE is not None:
            raise RuntimeError(self.EMPTY_MESSAGE)

        self.logger.subsection(f"Dispatching {len(sessions)} {self.SESSION_NOUN} sequentially")

        runner    = ProcessPoolRunner(logger=self.logger, max_workers=1)
        completed = runner.run(sessions, self._session_runner(), self._result_key)

        results = {}
        for session, outputs in completed:
            results[self._result_key(session)] = outputs
            self.logger.section(self._completion_message(session))
            self.logger.kv_table(self._outputs_table(outputs), title="Outputs")

        return results
