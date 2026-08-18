"""Discovery and selection of run directories for the analysis entry points.

Finds run directories by the marker file they contain, prints them as a table,
and resolves a selection either from an explicit filter, an interactive prompt,
or by taking all of them when stdin is not a terminal. Subclasses adapt the
discovery and the table to reports and TensorBoard event files.
"""

from __future__ import annotations

import sys
from pathlib import Path


class RunSelector:
    """Selects run directories that contain a given marker file.

    Attributes:
        runs_dir: Root searched recursively for runs.
        marker: File or directory name identifying a run.
        logger: Logger used for the run table and selection messages.
        action: Verb shown in the interactive prompt.
    """

    def __init__(self, runs_dir: Path, marker: str, logger, action: str = "process") -> None:
        """Initializes the selector.

        Args:
            runs_dir: Root searched recursively for runs.
            marker: File name whose presence marks a run directory.
            logger: Logger for the run table and selection messages.
            action: Verb used in the interactive prompt.
        """
        self.runs_dir = Path(runs_dir)
        self.marker   = marker
        self.logger   = logger
        self.action   = action

    def _discover(self) -> list[Path]:
        """Returns the sorted directories holding the marker file.

        Raises:
            FileNotFoundError: If the runs root is missing or holds no marker.
        """
        if not self.runs_dir.is_dir():
            raise FileNotFoundError(f"Runs directory does not exist: {self.runs_dir}")

        checkpoints = self.runs_dir.rglob(self.marker)
        run_dirs    = sorted({path.parent for path in checkpoints if path.is_file()})

        if not run_dirs:
            raise FileNotFoundError(f"No '{self.marker}' found in any directory under {self.runs_dir}")

        return run_dirs

    def _present(self, run_dirs: list[Path]) -> None:
        """Logs a numbered table of the runs with each checkpoint's size in MB."""
        rows = []
        for index, run_dir in enumerate(run_dirs, start=1):
            checkpoint = run_dir / self.marker
            size_mb    = checkpoint.stat().st_size / (1024 * 1024)
            rows.append({
                "#"          : index,
                "Run"        : str(run_dir.relative_to(self.runs_dir)),
                "Checkpoint" : f"{size_mb:,.1f} MB",
            })

        self.logger.metrics_table(rows, columns=["#", "Run", "Checkpoint"], title=f"Runs under {self.runs_dir}")

    def _prompt(self, run_dirs: list[Path]) -> list[Path]:
        """Asks the operator which listed runs to use and returns them."""
        raw       = input(f"Select run(s) to {self.action} [1-{len(run_dirs)}, comma-separated, or 'all']: ").strip()
        selection = self._parse(raw, run_dirs)

        self.logger.ok(f"Selected {len(selection)} run(s): {', '.join(run_dir.name for run_dir in selection)}")
        return selection

    def _parse(self, raw: str, run_dirs: list[Path]) -> list[Path]:
        """Turns a prompt answer into the runs it names.

        Args:
            raw: Answer text; empty, 'all' or '*' select every run, otherwise a
                comma or space separated list of 1-based indices.
            run_dirs: Runs as listed in the table.

        Returns:
            The selected runs, deduplicated and in listing order.

        Raises:
            ValueError: If a token is not a number or falls outside the listing.
        """
        if raw == "" or raw.lower() in ("all", "*"):
            return run_dirs

        indices = []
        for token in raw.replace(",", " ").split():
            if not token.isdigit():
                raise ValueError(f"Invalid selection token '{token}'; expected run numbers 1-{len(run_dirs)} or 'all'")

            index = int(token)
            if index < 1 or index > len(run_dirs):
                raise ValueError(f"Selection {index} is out of range 1-{len(run_dirs)}")

            indices.append(index)

        ordered = sorted(dict.fromkeys(indices))
        return [run_dirs[index - 1] for index in ordered]

    def _nested(self, run_dirs: list[Path], name: str) -> list[Path]:
        """Returns the runs living beneath a directory of the given name."""
        nested = [run_dir for run_dir in run_dirs if run_dir.parent.name == name or str(run_dir.relative_to(self.runs_dir)).startswith(f"{name}/")]

        if nested:
            self.logger.ok(f"'{name}' expanded to {len(nested)} nested run(s)")
        return nested

    def _lookup(self, run_dirs: list[Path], names: list[str]) -> list[Path]:
        """Resolves run names or relative paths, expanding parent names to their runs.

        Names that resolve ambiguously across runs are not matched directly and
        fall through to the nested expansion.

        Args:
            run_dirs: Discovered runs.
            names: Run names or paths relative to the runs root.

        Returns:
            The matched runs, deduplicated and in resolution order.

        Raises:
            FileNotFoundError: If a name matches neither a run nor a parent
                directory holding runs.
        """
        by_key    = {}
        ambiguous = set()
        for run_dir in run_dirs:
            for key in (run_dir.name, str(run_dir.relative_to(self.runs_dir))):
                if key in by_key and by_key[key] != run_dir:
                    ambiguous.add(key)
                by_key[key] = run_dir

        for key in ambiguous:
            del by_key[key]

        selection = []
        for name in names:
            run_dir = by_key.get(name)
            if run_dir is not None:
                selection.append(run_dir)
                continue

            nested = self._nested(run_dirs, name)
            if not nested:
                raise FileNotFoundError(f"No run '{name}' with '{self.marker}' under {self.runs_dir}, and no nested runs beneath a directory of that name")
            selection.extend(nested)

        ordered = list(dict.fromkeys(selection))
        self.logger.ok(f"Selected {len(ordered)} run(s): {', '.join(str(run_dir.relative_to(self.runs_dir)) for run_dir in ordered)}")
        return ordered

    def select(self) -> list[Path]:
        """Discovers and lists the runs, then returns the ones chosen at the prompt."""
        run_dirs = self._discover()
        self._present(run_dirs)
        return self._prompt(run_dirs)

    def filter(self, names: list[str]) -> list[Path]:
        """Discovers and lists the runs, then returns the ones matching the given names."""
        run_dirs = self._discover()
        self._present(run_dirs)
        return self._lookup(run_dirs, names)

    def all(self) -> list[Path]:
        """Discovers and lists the runs, then returns every one of them."""
        run_dirs = self._discover()
        self._present(run_dirs)
        self.logger.ok(f"Selected all {len(run_dirs)} run(s)")
        return run_dirs

    def resolve(self, run_filter: list[str] | None) -> list[Path]:
        """Resolves the runs to process from the filter, the terminal, or all of them.

        Args:
            run_filter: Explicit run names, or None or empty to fall back to the
                interactive prompt on a terminal and to every run otherwise.

        Returns:
            The selected run directories.
        """
        if run_filter:
            return self.filter(run_filter)
        if sys.stdin.isatty():
            return self.select()

        return self.all()


class ReportRunSelector(RunSelector):
    """Selects runs by the Markdown reports under their inference directory.

    Attributes:
        report_filename: Report file name looked for inside each inference output.
    """

    def __init__(self, runs_dir: Path, inference_dirname: str, report_filename: str, logger) -> None:
        """Initializes the selector for report collection.

        Args:
            runs_dir: Root searched recursively for runs.
            inference_dirname: Directory inside a run holding the inference outputs.
            report_filename: Report file name marking a usable inference output.
            logger: Logger for the run table and selection messages.
        """
        super().__init__(runs_dir, inference_dirname, logger, action="collect")
        self.report_filename = report_filename

    def _discover(self) -> list[Path]:
        """Returns the sorted runs holding at least one report.

        Raises:
            FileNotFoundError: If the runs root is missing or holds no report.
        """
        if not self.runs_dir.is_dir():
            raise FileNotFoundError(f"Runs directory does not exist: {self.runs_dir}")

        reports  = self.runs_dir.rglob(f"{self.marker}/*/{self.report_filename}")
        run_dirs = sorted({path.parent.parent.parent for path in reports if path.is_file()})

        if not run_dirs:
            raise FileNotFoundError(f"No '{self.report_filename}' found in any '{self.marker}' output under {self.runs_dir}")

        return run_dirs

    def _present(self, run_dirs: list[Path]) -> None:
        """Logs a numbered table of the runs with their report count and newest stamp."""
        rows = []
        for index, run_dir in enumerate(run_dirs, start=1):
            reports = sorted(path for path in (run_dir / self.marker).glob(f"*/{self.report_filename}") if path.is_file())
            rows.append({
                "#"       : index,
                "Run"     : str(run_dir.relative_to(self.runs_dir)),
                "Reports" : f"{len(reports)} report(s), latest {reports[-1].parent.name}",
            })

        self.logger.metrics_table(rows, columns=["#", "Run", "Reports"], title=f"Runs under {self.runs_dir}")


class TensorboardRunSelector(RunSelector):
    """Selects runs by the TensorBoard event files under their log directory.

    Attributes:
        EVENT_PATTERN: Glob matching TensorBoard event files.
    """

    EVENT_PATTERN = "events.out.tfevents.*"

    def __init__(self, runs_dir: Path, tensorboard_dirname: str, logger) -> None:
        """Initializes the selector for TensorBoard export.

        Args:
            runs_dir: Root searched recursively for runs.
            tensorboard_dirname: Directory inside a run holding the event files.
            logger: Logger for the run table and selection messages.
        """
        super().__init__(runs_dir, tensorboard_dirname, logger, action="export")

    def _discover(self) -> list[Path]:
        """Returns the sorted runs holding at least one event file.

        Raises:
            FileNotFoundError: If the runs root is missing or holds no event file.
        """
        if not self.runs_dir.is_dir():
            raise FileNotFoundError(f"Runs directory does not exist: {self.runs_dir}")

        events   = self.runs_dir.rglob(f"{self.marker}/{self.EVENT_PATTERN}")
        run_dirs = sorted({path.parent.parent for path in events if path.is_file()})

        if not run_dirs:
            raise FileNotFoundError(f"No '{self.marker}' directory with event files found under {self.runs_dir}")

        return run_dirs

    def _present(self, run_dirs: list[Path]) -> None:
        """Logs a numbered table of the runs with their event-file count and total size."""
        rows = []
        for index, run_dir in enumerate(run_dirs, start=1):
            events  = [path for path in (run_dir / self.marker).glob(self.EVENT_PATTERN) if path.is_file()]
            size_mb = sum(path.stat().st_size for path in events) / (1024 * 1024)
            rows.append({
                "#"      : index,
                "Run"    : str(run_dir.relative_to(self.runs_dir)),
                "Events" : f"{len(events)} file(s), {size_mb:,.1f} MB",
            })

        self.logger.metrics_table(rows, columns=["#", "Run", "Events"], title=f"Runs under {self.runs_dir}")
