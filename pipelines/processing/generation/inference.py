"""Inference stage over preprocessed SAR stacks: overview plots and value distributions.

Reads the ``dataset.json`` layout written by the preprocessing pipeline, renders the
stack overview figures and the amplitude/phase distribution report, and exposes a
scheduler that walks every preprocessing trial under a runs directory.
"""

from __future__ import annotations

import gc
from pathlib import Path

from pipelines.processing.generation.distributions    import StackDistributionAnalyzer
from pipelines.processing.generation.plots            import StackPlotter
from pipelines.shared.orchestration.session_scheduler import SequentialSessionScheduler
from tools.data.io                                    import FileIO
from tools.monitoring.logger                          import Logger


class StackInferencePipeline:
    """Plots and profiles one preprocessed stack run directory.

    Attributes:
        run_dir: Preprocessing run directory holding ``data/`` and ``images/``.
        data_dir: The ``data/`` subdirectory carrying the layout and the .npy artifacts.
        logger: Logger the plotting and distribution stages write through.
    """

    LAYOUT_FILENAME = "dataset.json"

    def __init__(self, run_dir: Path, logger: Logger) -> None:
        """Binds the pipeline to a preprocessing run directory.

        Args:
            run_dir: Run directory produced by the preprocessing pipeline.
            logger: Logger for section and progress output.
        """
        self.run_dir  = Path(run_dir)
        self.data_dir = self.run_dir / "data"
        self.logger   = logger

        self.logger.section("[Pre-Processing Inference]")
        self.logger.subsection(f"Run directory : {self.run_dir}")

    def _layout(self) -> dict:
        """Returns the dataset layout dictionary written by preprocessing."""
        return FileIO.load_json(self.data_dir / self.LAYOUT_FILENAME)

    def _plot(self, layout: dict) -> dict[str, Path]:
        """Renders the stack overview figures declared by the layout.

        Args:
            layout: Dataset layout mapping artifact names to paths relative to ``data/``.

        Returns:
            Mapping from figure name to the saved PNG path.
        """
        artifacts = layout["artifacts"]

        plotter = StackPlotter(
            run_directory      = self.run_dir,
            max_amplitude_clip = float(layout["max_amplitude_clip"]),
            logger             = self.logger,
        )

        return plotter.run(
            primary_path        = self.data_dir / artifacts["primary"],
            secondaries_path    = self.data_dir / artifacts["secondaries"],
            interferograms_path = self.data_dir / artifacts["interferograms"],
            dem_path            = self.data_dir / artifacts["dem_full"],
            pass_labels         = layout.get("pass_labels"),
        )

    def _analyze_distributions(self, layout: dict) -> dict[str, Path]:
        """Profiles the value distributions of the SLC, interferogram and DEM arrays.

        Args:
            layout: Dataset layout mapping artifact names to paths relative to ``data/``.

        Returns:
            Mapping from artifact name to the saved distribution figure or JSON path.
        """
        artifacts = layout["artifacts"]

        analyzer = StackDistributionAnalyzer(
            run_directory                = self.run_dir,
            interferogram_amplitude_clip = float(layout["max_amplitude_clip"]),
            logger                       = self.logger,
        )

        return analyzer.run(
            primary_path        = self.data_dir / artifacts["primary"],
            secondaries_path    = self.data_dir / artifacts["secondaries"],
            interferograms_path = self.data_dir / artifacts["interferograms"],
            dem_path            = self.data_dir / artifacts["dem_full"],
            pass_labels         = layout.get("pass_labels"),
        )

    def run(self) -> dict[str, Path]:
        """Runs the plotting and distribution stages for the run directory.

        Returns:
            Dictionary with the images directory, the run directory, the number of
            figures written and the path of the value-distributions JSON.
        """
        layout        = self._layout()
        saved         = self._plot(layout)
        distributions = self._analyze_distributions(layout)

        gc.collect()

        self.logger.section("[Pre-Processing Inference Completed]")

        return {
            "images"             : self.run_dir / "images",
            "run_directory"      : self.run_dir,
            "figures"            : len(saved),
            "distributions_json" : distributions["value_distributions_json"],
        }


class StackInferenceTrialCollector:
    """Resolves the preprocessing trial directories that inference should visit.

    Attributes:
        runs_dir: Directory holding one subdirectory per preprocessing trial.
        run_tags: Explicit trial names; empty means discover every valid trial.
        logger: Logger used to report the collected trials.
    """

    def __init__(self, runs_dir: Path, run_tags: list[str], logger: Logger) -> None:
        """Binds the collector to a runs directory and an optional tag filter.

        Args:
            runs_dir: Directory holding the preprocessing trial subdirectories.
            run_tags: Trial names to restrict to; empty enables discovery.
            logger: Logger for the collection report.
        """
        self.runs_dir = Path(runs_dir)
        self.run_tags = run_tags
        self.logger   = logger

    def _discover_tags(self) -> list[str]:
        """Returns the configured tags, or every subdirectory carrying a dataset layout."""
        if self.run_tags:
            return list(self.run_tags)

        return [
            entry.name
            for entry in sorted(self.runs_dir.iterdir())
            if entry.is_dir() and (entry / "data" / StackInferencePipeline.LAYOUT_FILENAME).exists()
        ]

    def collect(self) -> list[Path]:
        """Returns the run directories of every requested preprocessing trial.

        Returns:
            List of trial run directories, in discovery order.

        Raises:
            FileNotFoundError: If a requested tag has no dataset layout on disk.
        """
        self.logger.section("Collecting preprocessing trials")

        run_dirs = []
        for tag in self._discover_tags():
            run_dir = self.runs_dir / tag

            if not (run_dir / "data" / StackInferencePipeline.LAYOUT_FILENAME).exists():
                raise FileNotFoundError(f"No data/{StackInferencePipeline.LAYOUT_FILENAME} under {run_dir}; cannot run preprocessing inference for trial '{tag}'.")

            self.logger.info(tag)
            run_dirs.append(run_dir)

        if not run_dirs:
            self.logger.error(f"No preprocessing trials found under {self.runs_dir}")

        return run_dirs


class StackInferenceSession:
    """One schedulable unit of preprocessing inference over a single run directory.

    Attributes:
        run_dir: Preprocessing run directory this session processes.
    """

    def __init__(self, run_dir: Path) -> None:
        """Binds the session to a preprocessing run directory."""
        self.run_dir = Path(run_dir)

    def execute(self) -> dict[str, Path]:
        """Creates the session logger and runs the stack inference pipeline.

        Returns:
            The result dictionary returned by ``StackInferencePipeline.run``.
        """
        log_dir = self.run_dir / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)

        logger = Logger(log_dir=str(log_dir), name="preprocessing_inference", level="INFO")

        return StackInferencePipeline(self.run_dir, logger=logger).run()


def run_stack_inference_session(session: StackInferenceSession) -> dict[str, Path]:
    """Module-level entry point so a session can be dispatched by a scheduler."""
    return session.execute()


class PreprocessingInferenceScheduler(SequentialSessionScheduler):
    """Runs preprocessing inference sequentially over every collected trial.

    Attributes:
        config: Entry configuration carrying ``runs_dir`` and ``run_tags``.
    """

    EMPTY_MESSAGE = "No preprocessing trials to infer"
    SESSION_NOUN  = "trials"

    def __init__(self, config, logger: Logger) -> None:
        """Binds the scheduler to the preprocessing-inference entry configuration.

        Args:
            config: Entry configuration exposing ``runs_dir`` and ``run_tags``.
            logger: Logger shared with the base scheduler.
        """
        super().__init__(logger)
        self.config = config

    def _sessions(self) -> list[StackInferenceSession]:
        """Returns one session per collected preprocessing trial."""
        run_dirs = StackInferenceTrialCollector(Path(self.config.runs_dir), list(self.config.run_tags), self.logger).collect()
        return [StackInferenceSession(run_dir) for run_dir in run_dirs]

    def _session_runner(self):
        """Returns the callable that executes one session."""
        return run_stack_inference_session

    def _result_key(self, session) -> str:
        """Returns the trial name used to key this session's results."""
        return session.run_dir.name

    def _completion_message(self, session) -> str:
        """Returns the log line announcing that a trial finished."""
        return f"[Trial] {session.run_dir.name} completed"
