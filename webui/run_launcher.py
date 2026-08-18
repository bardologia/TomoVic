"""Launching of training and analysis entry points from the console.

Resolves the interpreter and the TensorBoard log directory of an entry point,
hands the run to the process manager either immediately or through the queue, and
starts TensorBoard for training runs in the background.
"""

from __future__ import annotations

import threading
from pathlib import Path

from process_manager        import ProcessManager
from project_paths          import ProjectPaths
from script_config_resolver import ScriptConfigResolver
from tensorboard_manager    import TensorboardManager
from web_logger             import WebLogger


class RunLauncher:
    """Validates interpreters, resolves log directories and launches console runs.

    Attributes:
        paths: Project paths providing entry points and interpreter discovery.
        logger: Console logger.
        resolver: Config resolver used to read an entry's default log directory.
        processes: Process manager executing or queueing the run.
        tensorboard: TensorBoard manager started for training entry points.
    """

    def __init__(self, paths: ProjectPaths, logger: WebLogger, resolver: ScriptConfigResolver, processes: ProcessManager, tensorboard: TensorboardManager) -> None:
        """Stores the paths, logger, resolver, process manager and TensorBoard manager."""
        self.paths       = paths
        self.logger      = logger
        self.resolver    = resolver
        self.processes   = processes
        self.tensorboard = tensorboard

    def preferred_interpreter(self, script_key: str = "") -> str:
        """Returns the interpreter preferred for an entry point among the discovered ones."""
        interpreters = self.paths.discover_interpreters()
        return self.paths.preferred_interpreter(interpreters, script_key)

    def interpreter_error(self, interpreter: str) -> str:
        """Returns an error message when the interpreter is not one of the discovered ones."""
        if any(item["path"] == interpreter for item in self.paths.discover_interpreters()):
            return ""
        return f"unknown interpreter '{interpreter}'; pick one of the environments listed by the console"

    def training_logdir(self, key: str, overrides: dict, interpreter: str) -> str | None:
        """Returns the TensorBoard log directory an entry point will write to.

        Takes the first log-directory config leaf that the launch overrides set, and
        otherwise falls back to the value resolved from the entry's config defaults.

        Args:
            key: Entry-point key.
            overrides: Config leaf overrides chosen for this launch.
            interpreter: Interpreter used to resolve the entry's config defaults.

        Returns:
            The log directory, or None when the entry writes no TensorBoard logs or its
            config cannot be resolved.
        """
        leaf_keys = self.tensorboard.logdir_keys(key)
        if not leaf_keys:
            return None

        for leaf in leaf_keys:
            value = (overrides or {}).get(leaf)
            if value:
                return str(value)

        resolved = self.resolver.resolve(key, interpreter)
        if not resolved.get("ok"):
            return None

        leaves = {item["path"]: item["value"] for item in resolved["leaves"]}
        for leaf in leaf_keys:
            if leaves.get(leaf):
                return str(leaves[leaf])

        return None

    def runs_root(self, key: str, interpreter: str) -> str | None:
        """Returns the parent of an entry point's default log directory, or None."""
        logdir = self.training_logdir(key, {}, interpreter)
        if not logdir:
            return None
        return str(Path(logdir).parent)

    def _autostart_tensorboard(self, key: str, overrides: dict, interpreter: str) -> None:
        """Ensures a TensorBoard instance for the launched run, logging any failure."""
        try:
            logdir = self.training_logdir(key, overrides, interpreter)
            if logdir:
                self.tensorboard.ensure(logdir, interpreter)
        except Exception as exc:
            self.logger.error(f"tensorboard autostart failed: {exc}")

    def execute(self, key: str, interpreter: str, overrides: dict, follow_up: str | None, detach: bool, queue: bool) -> dict:
        """Launches or queues an entry point and starts TensorBoard for training runs.

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
            result = self.processes.enqueue(key, interpreter, overrides, follow_up, detach)
        else:
            result = self.processes.launch(key, interpreter, overrides, follow_up, detach)

        if result.get("ok") and self.tensorboard.logdir_keys(key):
            threading.Thread(target=self._autostart_tensorboard, args=(key, overrides, interpreter), daemon=True).start()

        return result
