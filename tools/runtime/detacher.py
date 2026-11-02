"""Relaunch of an entry point as a hangup-immune background process.

When --detach is present the script re-execs itself in a new session with its
output redirected to a timestamped log, so long runs survive the terminal that
started them.
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
from pathlib import Path

from tools.runtime.cuda_mask import InheritedCudaMask
from tools.runtime.run_tag   import RunTag


class Detacher:
    """Re-execs the running script detached from its controlling terminal.

    Attributes:
        log_dir  : Directory the detached process's output log is written to.
        ENV_FLAG : Environment variable marking an already-detached process.
        OUT_ENV     : Environment variable handing the detached child its output log path; the child removes it, so its own subprocesses never inherit it.
        FLAGS       : Command-line flags that request detachment.
        output_path : Output log path of this process when it is the detached child, named in every Logger header; None otherwise.
    """

    ENV_FLAG = "TOMOSAR_DETACHED"
    OUT_ENV  = "TOMOSAR_DETACHED_OUT"
    FLAGS    = ("--detach", "--nohup")

    output_path : str | None = None

    def __init__(self, log_dir: str = "logs") -> None:
        """Initializes the detacher with the directory that receives output logs."""
        self.log_dir = Path(log_dir)

    def requested(self, argv: list[str] | None = None) -> bool:
        """Returns whether a detach flag is present in the given or process arguments."""
        argv = sys.argv[1:] if argv is None else argv
        return any(flag in argv for flag in self.FLAGS)

    def active(self) -> bool:
        """Returns whether this process is already the detached child."""
        return os.environ.get(self.ENV_FLAG) == "1"

    def ensure(self) -> None:
        """Detaches the process when requested, or arms the child against hangups.

        In the detached child SIGHUP is ignored, the output log path is taken
        out of the environment into output_path, so the queue workers and pool
        children the child starts do not name the child's .out file as their
        own, and control returns. In the parent
        the script is relaunched in a new session with output appended to
        logs/<script>_<stamp>.out, and the parent then exits. The child's
        environment restores the CUDA mask the parent inherited before pinning
        itself, so the re-exec resolves --gpu against the original device set,
        and carries the output log path in OUT_ENV for the child's log headers.

        Raises:
            SystemExit : In the parent, with status 0, once the child is running.
        """
        if self.active():
            signal.signal(signal.SIGHUP, signal.SIG_IGN)
            Detacher.output_path = os.environ.pop(self.OUT_ENV, Detacher.output_path)
            return

        if not self.requested():
            return

        self.log_dir.mkdir(parents=True, exist_ok=True)

        stamp    = RunTag.now()
        name     = Path(sys.argv[0]).stem
        log_path = self.log_dir / f"{name}_{stamp}.out"

        env                     = InheritedCudaMask.restored()
        env[self.ENV_FLAG]      = "1"
        env[self.OUT_ENV]       = str(log_path.resolve())
        env["PYTHONUNBUFFERED"] = "1"
        env.setdefault("FORCE_COLOR", "1")
        env.setdefault("COLUMNS", "120")

        with open(log_path, "ab") as sink:
            process = subprocess.Popen(
                [sys.executable, "-u", *sys.argv],
                cwd               = os.getcwd(),
                stdout            = sink,
                stderr            = subprocess.STDOUT,
                stdin             = subprocess.DEVNULL,
                env               = env,
                start_new_session = True,
            )

        print(f"detached {name} as pid {process.pid}, immune to hangup")
        print(f"output: {log_path}")
        print(f"follow: tail -f {log_path}")

        raise SystemExit(0)
