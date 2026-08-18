"""Launching of processing and analysis entry points from the console.

Resolves the interpreter of an entry point and hands the run to the process
manager either immediately or through the queue.
"""

from __future__ import annotations

from process_manager        import ProcessManager
from project_paths          import ProjectPaths
from script_config_resolver import ScriptConfigResolver
from web_logger             import WebLogger


class RunLauncher:
    """Validates interpreters and launches console runs.

    Attributes:
        paths: Project paths providing entry points and interpreter discovery.
        logger: Console logger.
        resolver: Config resolver used to read an entry's defaults.
        processes: Process manager executing or queueing the run.
    """

    def __init__(self, paths: ProjectPaths, logger: WebLogger, resolver: ScriptConfigResolver, processes: ProcessManager) -> None:
        """Stores the paths, logger, resolver and process manager."""
        self.paths     = paths
        self.logger    = logger
        self.resolver  = resolver
        self.processes = processes

    def preferred_interpreter(self, script_key: str = "") -> str:
        """Returns the interpreter preferred for an entry point among the discovered ones."""
        interpreters = self.paths.discover_interpreters()
        return self.paths.preferred_interpreter(interpreters, script_key)

    def interpreter_error(self, interpreter: str) -> str:
        """Returns an error message when the interpreter is not one of the discovered ones."""
        if any(item["path"] == interpreter for item in self.paths.discover_interpreters()):
            return ""
        return f"unknown interpreter '{interpreter}'; pick one of the environments listed by the console"

    def execute(self, key: str, interpreter: str, overrides: dict, follow_up: str | None, detach: bool, queue: bool) -> dict:
        """Launches or queues an entry point.

        Args:
            key: Entry-point key to run.
            interpreter: Python interpreter to run it under.
            overrides: Config leaf overrides passed on the command line.
            follow_up: Entry point to run once this one succeeds, or None.
            detach: Whether the run survives the console process.
            queue: Whether to enqueue the run instead of starting it immediately.

        Returns:
            The process manager's launch result, or a failed result when the interpreter
            is unknown.
        """
        error = self.interpreter_error(interpreter)
        if error:
            return {"ok": False, "error": error}

        if queue:
            return self.processes.enqueue(key, interpreter, overrides, follow_up, detach)

        return self.processes.launch(key, interpreter, overrides, follow_up, detach)
