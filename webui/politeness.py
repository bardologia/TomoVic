"""Launch-time priority of console jobs and the runtime throttle of running ones.

JobPoliteness keeps the persisted politeness level and renders the nice and
ionice prefix every local launch starts under. JobThrottle lowers the CPU and
I/O priority of every process this user owns, sparing the console's own line,
for the contention monitor to call when this user is found slowing the
neighbours. Both only ever lower priority, which an unprivileged user may do;
neither can raise it back, so a throttled job stays throttled until it ends.
The automatic throttle is off until it is switched on from the Home page,
because it lowers every process this user owns on the machine, including jobs
another console started.
"""

from __future__ import annotations

import json
import subprocess
import threading

from web_logger import WebLogger


class JobPoliteness:
    """Persisted politeness level and the command prefix it stands for.

    A console without a settings file launches at the "polite" level with the
    automatic throttle off; switching the throttle on is an explicit choice.

    Attributes:
        paths    : Project paths supplying the logs directory the settings live in.
        logger   : Console logger for configuration changes.
        lock     : Guards the settings.
        path     : Settings file under the logs directory.
        settings : Current "level" and "auto_throttle" flag.
    """

    SETTINGS_NAME = "politeness.json"
    LEVELS        = {
        "off"        : {"nice": 0,  "io_class": None, "io_level": None, "label": "no nice, no ionice"},
        "polite"     : {"nice": 10, "io_class": 2,    "io_level": 7,    "label": "nice 10, ionice best-effort 7"},
        "background" : {"nice": 19, "io_class": 3,    "io_level": None, "label": "nice 19, ionice idle"},
    }
    DEFAULTS      = {"level": "polite", "auto_throttle": False}

    def __init__(self, paths, logger: WebLogger) -> None:
        """Resolves the settings file and loads the persisted level.

        Args:
            paths  : Project paths supplying the logs directory.
            logger : Console logger for configuration changes.
        """
        self.paths    = paths
        self.logger   = logger
        self.lock     = threading.Lock()
        self.path     = paths.logs_dir / self.SETTINGS_NAME
        self.settings = self._load()

    def _load(self) -> dict:
        """Returns the persisted settings, or the defaults when no settings file exists.

        Raises:
            KeyError   : The file lacks one of the settings keys.
            ValueError : The file names a level that does not exist.
        """
        if not self.path.exists():
            return dict(self.DEFAULTS)

        loaded = json.loads(self.path.read_text())
        level  = loaded["level"]
        if level not in self.LEVELS:
            raise ValueError(f"{self.path} names unknown politeness level {level!r}")
        return {"level": level, "auto_throttle": bool(loaded["auto_throttle"])}

    def level(self) -> str:
        """Returns the current level name."""
        with self.lock:
            return self.settings["level"]

    def auto_throttle(self) -> bool:
        """Returns whether running jobs are throttled automatically when this user slows the neighbours."""
        with self.lock:
            return self.settings["auto_throttle"]

    def prefix(self) -> list[str]:
        """Returns the argv prefix a local launch starts under for the current level.

        Returns:
            Empty list for "off", otherwise `nice -n <value>` followed by the
            `ionice` class and, for the best-effort class, its level.
        """
        spec = self.LEVELS[self.level()]
        if spec["nice"] == 0:
            return []

        argv = ["nice", "-n", str(spec["nice"]), "ionice", "-c", str(spec["io_class"])]
        if spec["io_level"] is not None:
            argv += ["-n", str(spec["io_level"])]
        return argv

    def state(self) -> dict:
        """Returns the settings with the level's description, the rendered prefix and the settings path."""
        with self.lock:
            settings = dict(self.settings)
        spec = self.LEVELS[settings["level"]]
        return {**settings, "nice": spec["nice"], "label": spec["label"], "prefix": " ".join(self.prefix()), "levels": list(self.LEVELS), "settings_path": str(self.path)}

    def configure(self, payload: dict) -> dict:
        """Validates and persists a new level and auto-throttle flag.

        Args:
            payload : Request body with "level" and "auto_throttle"; a missing key keeps its current value.

        Returns:
            The new state under an "ok" flag, or an "ok" of False with an
            "error" when the level is unknown.
        """
        with self.lock:
            current = dict(self.settings)

        level    = str(payload.get("level", current["level"]))
        throttle = bool(payload.get("auto_throttle", current["auto_throttle"]))

        if level not in self.LEVELS:
            return {"ok": False, "error": f"unknown politeness level {level!r}; choose one of {', '.join(self.LEVELS)}"}

        with self.lock:
            self.settings = {"level": level, "auto_throttle": throttle}
            self._persist()

        self.logger.ok(f"politeness set to {level} ({self.LEVELS[level]['label']}), auto-throttle {'on' if throttle else 'off'}")
        return {"ok": True, **self.state()}

    def _persist(self) -> None:
        """Writes the current settings to the settings file, creating its directory."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.settings, indent=2) + "\n")


class JobThrottle:
    """Drops every process of this user to the lowest CPU and I/O priority, sparing the console.

    Attributes:
        nuke   : Process nuke whose target enumeration names this user's processes minus the console's own line.
        logger : Console logger for the outcome.
    """

    NICE      = 19
    IO_CLASS  = 3
    TIMEOUT_S = 15.0

    def __init__(self, nuke, logger: WebLogger) -> None:
        """Records the nuke used for enumeration and the logger."""
        self.nuke   = nuke
        self.logger = logger

    def _run(self, argv: list[str]) -> tuple[int, str]:
        """Runs one priority command and returns its exit code with the tail of its stderr.

        Args:
            argv : Command line of `renice` or `ionice`.

        Returns:
            Tuple of the exit code (127 when the binary is missing or timed out)
            and the last stderr line, empty on success.
        """
        try:
            done = subprocess.run(argv, capture_output=True, text=True, timeout=self.TIMEOUT_S)
        except (OSError, subprocess.TimeoutExpired) as exc:
            return 127, str(exc)

        lines = done.stderr.strip().splitlines()
        return done.returncode, (lines[-1] if lines else "")

    def apply(self) -> dict:
        """Renices and ionices every target process once.

        Returns:
            Mapping with "ok" when both commands exited cleanly, "processes", the
            number of pids targeted, the "renice" and "ionice" exit codes, and
            "error", the stderr tail of the failing command or an empty string.
        """
        targets = self.nuke.targets()
        if not targets:
            self.logger.muted("throttle requested, no processes to lower")
            return {"ok": True, "processes": 0, "renice": 0, "ionice": 0, "error": ""}

        pids           = [str(pid) for pid in targets]
        renice, err_r  = self._run(["renice", "-n", str(self.NICE), "-p", *pids])
        ionice, err_i  = self._run(["ionice", "-c", str(self.IO_CLASS), "-p", *pids])
        error          = err_r or err_i
        ok             = renice == 0 and ionice == 0

        if ok:
            self.logger.warning(f"THROTTLE: {len(targets)} user processes dropped to nice {self.NICE} and idle I/O")
        else:
            self.logger.error(f"THROTTLE failed on {len(targets)} processes (renice {renice}, ionice {ionice}): {error}")

        return {"ok": ok, "processes": len(targets), "renice": renice, "ionice": ionice, "error": error}
