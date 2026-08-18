"""Base class for multi-stage pipelines with on-disk stage bookkeeping.

Owns the run directory layout (``<log_base_dir>/<run_tag>/pipeline``), persists
the resolved configuration next to it, and records per-stage status in
``state.json`` so a rerun can see what already finished.
"""

from __future__ import annotations

from pathlib import Path

from tools.data.io            import FileIO
from tools.monitoring.logger  import Logger
from tools.runtime.config_cli import ConfigCli
from tools.runtime.run_tag    import RunTag


class StagedPipeline:
    """Owns the run directory, logger and stage state of a staged pipeline.

    Attributes:
        config: Entry configuration for the pipeline.
        entry_script: Path of the entry script that launched the pipeline.
        run_tag: Timestamp-style tag naming the run directory.
        run_dir: Root directory of the run under the configured log base.
        pipeline_dir: Subdirectory holding pipeline logs and state.
        state_path: Path of the JSON file recording per-stage status.
        logger: Logger writing into the pipeline directory.
        state: Stage bookkeeping loaded from disk or freshly initialised.
    """

    LOGGER_NAME = "staged_pipeline"

    def __init__(self, config, entry_script: Path) -> None:
        """Prepares the run directory, saves the resolved config and loads state.

        Args:
            config: Entry configuration carrying ``run_tag`` and path settings.
            entry_script: Path of the entry script that launched the pipeline.
        """
        self.config       = config
        self.entry_script = entry_script
        self.run_tag      = config.run_tag or RunTag.now()

        self.run_dir      = Path(config.paths.log_base_dir) / self.run_tag
        self.pipeline_dir = self.run_dir / "pipeline"
        self.state_path   = self.pipeline_dir / "state.json"

        FileIO.ensure_dir(self.pipeline_dir)
        ConfigCli.save_resolved(config, self.pipeline_dir / "resolved_config.json")

        self.logger = Logger(log_dir=str(self.pipeline_dir), name=self.LOGGER_NAME)
        self.state  = self._recorded_state()

    def _recorded_state(self) -> dict:
        """Returns the stage state read from disk, or an empty state if absent."""
        if not self.state_path.is_file():
            return {"run_tag": self.run_tag, "stages": {}}

        return {"run_tag": self.run_tag, "stages": FileIO.load_json(self.state_path)["stages"]}

    def _mark_stage(self, stage_name: str, status: str) -> None:
        """Records a stage's status with a timestamp and flushes state to disk."""
        self.state["stages"][stage_name] = {
            "status"    : status,
            "timestamp" : RunTag.timestamp(),
        }

        FileIO.save_json(self.state, self.state_path, indent=2)
